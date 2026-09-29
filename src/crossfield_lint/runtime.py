"""Runtime checker: inspect an already-imported pydantic v2 model class.

This is the ground truth the static (AST) checker is tested against. It
trusts pydantic's own bookkeeping for field order and aliases
(`model_fields`, `__pydantic_decorators__`) instead of recomputing them, and
only uses AST parsing (via `inspect.getsource`) to find `info.data` reads
inside each validator function's body.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any

from pydantic import BaseModel

from crossfield_lint.model import Finding, FieldInfo, ModelInfo
from crossfield_lint.analysis import classify_read
from crossfield_lint.reads import collect_reads, find_info_param_name

try:
    from pydantic import AfterValidator, BeforeValidator, PlainValidator, WrapValidator

    _FUNCTIONAL_VALIDATOR_TYPES: tuple[type, ...] = (
        AfterValidator,
        BeforeValidator,
        PlainValidator,
        WrapValidator,
    )
except ImportError:  # pragma: no cover - pydantic is a required dependency
    _FUNCTIONAL_VALIDATOR_TYPES = ()


def _build_model_info(model_cls: type[BaseModel]) -> ModelInfo:
    fields: dict[str, FieldInfo] = {}
    for order, (name, finfo) in enumerate(model_cls.model_fields.items()):
        alias: str | None = None
        for candidate in (finfo.alias, finfo.validation_alias):
            if isinstance(candidate, str):
                alias = candidate
                break
        fields[name] = FieldInfo(name=name, alias=alias, order=order)
    return ModelInfo(
        qualname=f"{model_cls.__module__}.{model_cls.__qualname__}",
        fields=fields,
        field_order=list(fields.keys()),
        bases_resolved=True,
    )


def _unwrap(func: Any) -> Any:
    # Decorator.func for a field_validator is a bound classmethod; unwrap to
    # the plain function so inspect.getsource works on the definition.
    return getattr(func, "__func__", func)


def _parse_function(func: Any) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef | None, str, int]:
    """Return (FunctionDef node, source file, line offset) or (None, "", 0)
    if the source is unavailable (lambda, C extension, exec()'d code, ...).
    """
    try:
        source_file = inspect.getsourcefile(func) or "<unknown>"
        lines, start_lineno = inspect.getsourcelines(func)
    except (OSError, TypeError):
        return None, "<unknown>", 0
    source = textwrap.dedent("".join(lines))
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None, source_file, 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node, source_file, start_lineno - 1
    return None, source_file, 0


def check_model(model_cls: type) -> list[Finding]:
    """Check one already-imported `pydantic.BaseModel` subclass.

    Returns every `info.data` read that is provably wrong: a field that is
    not yet validated at that point, a name that is not a field at all, or
    a field indexed by its alias instead of its attribute name.
    """
    if not (isinstance(model_cls, type) and issubclass(model_cls, BaseModel)):
        raise TypeError(f"{model_cls!r} is not a pydantic BaseModel subclass")

    model_info = _build_model_info(model_cls)
    findings: list[Finding] = []

    decorators = model_cls.__pydantic_decorators__
    for name, dec in decorators.field_validators.items():
        raw_func = _unwrap(dec.func)
        func_node, source_file, offset = _parse_function(raw_func)
        if func_node is None:
            continue
        info_param = find_info_param_name(func_node)
        if info_param is None:
            continue
        targets = list(dec.info.fields)
        if "*" in targets:
            targets = list(model_info.field_order)
        reads = collect_reads(func_node, info_param)
        for target in targets:
            if target not in model_info.fields:
                continue
            for read in reads:
                finding, _note = classify_read(
                    model_info,
                    target,
                    read,
                    validator_name=name,
                    file=source_file,
                )
                if finding is not None:
                    findings.append(
                        Finding(
                            kind=finding.kind,
                            severity=finding.severity,
                            model=finding.model,
                            validator=finding.validator,
                            validated_field=finding.validated_field,
                            read_field=finding.read_field,
                            file=source_file,
                            line=finding.line + offset,
                            col=finding.col,
                            message=finding.message,
                        )
                    )

    if _FUNCTIONAL_VALIDATOR_TYPES:
        for field_name, finfo in model_cls.model_fields.items():
            for meta in getattr(finfo, "metadata", None) or ():
                if not isinstance(meta, _FUNCTIONAL_VALIDATOR_TYPES):
                    continue
                raw_func = getattr(meta, "func", None)
                if raw_func is None:
                    continue
                func_node, source_file, offset = _parse_function(raw_func)
                if func_node is None:
                    continue
                info_param = find_info_param_name(func_node)
                if info_param is None:
                    continue
                reads = collect_reads(func_node, info_param)
                for read in reads:
                    finding, _note = classify_read(
                        model_info,
                        field_name,
                        read,
                        validator_name=getattr(raw_func, "__name__", "<validator>"),
                        file=source_file,
                    )
                    if finding is not None:
                        findings.append(
                            Finding(
                                kind=finding.kind,
                                severity=finding.severity,
                                model=finding.model,
                                validator=finding.validator,
                                validated_field=finding.validated_field,
                                read_field=finding.read_field,
                                file=source_file,
                                line=finding.line + offset,
                                col=finding.col,
                                message=finding.message,
                            )
                        )

    return findings
