"""AST-based checker: finds pydantic v2 field validators that read
`info.data` for a field that is not yet validated, without importing the
code being checked.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from crossfield_lint.model import FieldInfo, Finding, ModelInfo
from crossfield_lint.analysis import classify_read
from crossfield_lint.reads import collect_reads, find_info_param_name
from crossfield_lint.resolve import EXTERNAL_PREFIX, ROOT, RawClass, discover_files, parse_file


@dataclass
class AnalysisResult:
    findings: list[Finding]
    models_checked: int
    files_with_errors: list[tuple[str, str]]
    """(file, message) for files that could not be parsed at all."""


class _InconsistentMRO(Exception):
    pass


def _c3_merge(sequences: list[list[str]]) -> list[str]:
    seqs = [list(s) for s in sequences if s]
    result: list[str] = []
    while seqs:
        candidate = None
        for seq in seqs:
            head = seq[0]
            if not any(head in s[1:] for s in seqs):
                candidate = head
                break
        if candidate is None:
            raise _InconsistentMRO()
        result.append(candidate)
        seqs = [s[1:] if s and s[0] == candidate else s for s in seqs]
        seqs = [s for s in seqs if s]
    return result


def _mro(key: str, classes: dict[str, RawClass], memo: dict[str, list[str]]) -> list[str]:
    if key in memo:
        return memo[key]
    memo[key] = [key]  # break cycles defensively
    raw = classes[key]
    resolvable_bases = [b for b in raw.base_refs if b in classes]
    if not resolvable_bases:
        memo[key] = [key]
        return memo[key]
    try:
        parents_mro = [_mro(b, classes, memo) for b in resolvable_bases]
        merged = _c3_merge([*parents_mro, resolvable_bases])
    except _InconsistentMRO:
        merged = resolvable_bases  # best-effort fallback, still deterministic
    memo[key] = [key, *merged]
    return memo[key]


def _has_unresolved_ancestor(
    key: str, classes: dict[str, RawClass], cache: dict[str, bool]
) -> bool:
    if key in cache:
        return cache[key]
    cache[key] = False  # break cycles
    raw = classes[key]
    result = False
    for b in raw.base_refs:
        if b == ROOT:
            continue
        if b.startswith(EXTERNAL_PREFIX):
            result = True
            break
        if b not in classes:
            result = True
            break
        if _has_unresolved_ancestor(b, classes, cache):
            result = True
            break
    cache[key] = result
    return result


FuncNode = ast.FunctionDef | ast.AsyncFunctionDef


def _build_model_info(
    key: str, classes: dict[str, RawClass]
) -> tuple[ModelInfo, dict[str, list[FuncNode]]]:
    mro_keys = _mro(key, classes, {})
    field_order_classes = list(reversed(mro_keys))

    fields: dict[str, FieldInfo] = {}
    field_order: list[str] = []
    field_annotated: dict[str, list[FuncNode]] = {}
    order = 0
    for ck in field_order_classes:
        raw = classes[ck]
        for f in raw.own_fields:
            if f.name not in fields:
                fields[f.name] = FieldInfo(name=f.name, alias=f.alias, order=order)
                field_order.append(f.name)
                order += 1
            else:
                fields[f.name] = FieldInfo(name=f.name, alias=f.alias, order=fields[f.name].order)
            field_annotated[f.name] = f.annotated_validator_funcs

    bases_resolved = not _has_unresolved_ancestor(key, classes, {})
    model_info = ModelInfo(
        qualname=key,
        fields=fields,
        field_order=field_order,
        bases_resolved=bases_resolved,
    )
    return model_info, field_annotated


def _effective_validators(key: str, classes: dict[str, RawClass]) -> dict[str, tuple[str, list[str]]]:
    """name -> (defining_class_key, target_fields), most-derived wins."""
    mro_keys = _mro(key, classes, {})
    result: dict[str, tuple[str, list[str]]] = {}
    for ck in mro_keys:  # cls-first order: first occurrence wins
        raw = classes[ck]
        for name, v in raw.own_validators.items():
            if name not in result and v.targets is not None:
                result[name] = (ck, v.targets)
    return result


def _is_model(key: str, classes: dict[str, RawClass], cache: dict[str, bool | None]) -> bool:
    if key in cache and cache[key] is not None:
        return bool(cache[key])
    cache[key] = False  # provisional, breaks cycles
    raw = classes.get(key)
    if raw is None:
        return False
    result = False
    for b in raw.base_refs:
        if b == ROOT:
            result = True
            break
        if b in classes and _is_model(b, classes, cache):
            result = True
            break
    cache[key] = result
    return result


def _analyze_model(key: str, classes: dict[str, RawClass]) -> list[Finding]:
    model_info, field_annotated = _build_model_info(key, classes)
    findings: list[Finding] = []

    for name, (defining_key, targets) in _effective_validators(key, classes).items():
        raw = classes[defining_key]
        node = raw.own_validators[name].node
        info_param = find_info_param_name(node)
        if info_param is None:
            continue
        expand = list(model_info.field_order) if "*" in targets else targets
        reads = collect_reads(node, info_param)
        for target in expand:
            if target not in model_info.fields:
                continue
            for read in reads:
                finding, _note = classify_read(
                    model_info, target, read, validator_name=name, file=raw.file
                )
                if finding is not None:
                    findings.append(finding)

    for field_name, funcs in field_annotated.items():
        if field_name not in model_info.fields:
            continue
        for func_node in funcs:
            info_param = find_info_param_name(func_node)
            if info_param is None:
                continue
            reads = collect_reads(func_node, info_param)
            file = classes[key].file  # best available approximation
            for read in reads:
                finding, _note = classify_read(
                    model_info,
                    field_name,
                    read,
                    validator_name=getattr(func_node, "name", "<validator>"),
                    file=file,
                )
                if finding is not None:
                    findings.append(finding)

    return findings


def check_source(source: str, filename: str = "<source>") -> list[Finding]:
    """Check a single in-memory source string (no cross-file resolution)."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / (Path(filename).name if filename != "<source>" else "module.py")
        path.write_text(source, encoding="utf-8")
        result = check_paths([str(path)])
        return result.findings


def check_paths(paths: list[str]) -> AnalysisResult:
    files = discover_files(paths)
    if not files:
        return AnalysisResult(findings=[], models_checked=0, files_with_errors=[])

    root = Path(paths[0]).resolve()
    if root.is_file():
        root = root.parent

    classes: dict[str, RawClass] = {}
    files_with_errors: list[tuple[str, str]] = []

    for f in files:
        _module_name, raw_classes, _import_map, err = parse_file(f, root)
        if err is not None:
            files_with_errors.append((str(f), str(err)))
            continue
        for rc in raw_classes:
            classes[rc.key] = rc

    is_model_cache: dict[str, bool | None] = {}
    model_keys = [k for k in classes if _is_model(k, classes, is_model_cache)]

    findings: list[Finding] = []
    for key in sorted(model_keys):
        findings.extend(_analyze_model(key, classes))

    return AnalysisResult(
        findings=findings, models_checked=len(model_keys), files_with_errors=files_with_errors
    )
