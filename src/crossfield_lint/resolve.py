"""Project-wide class discovery and (best-effort) base-class resolution.

This never imports the analyzed code. It parses every `.py` file with
`ast`, builds a registry of module-level classes keyed by
`(dotted_module_name, class_name)`, and resolves `class Child(Parent):`
bases to entries in that registry when it can -- same file always, other
files in the same tree when the import is a plain `from .mod import X` /
`from pkg.mod import X` that points at one of the discovered files.

What it does not do (see README Limitations): resolve imports that go
through `sys.path` tricks, namespace packages spread across multiple
roots, star imports, or bases built from an installed third-party package
that lives outside the analyzed file set. Those bases are recorded as
"external" and the classes that depend on them are still analyzed, but
with `bases_resolved=False` (see `model.ModelInfo`).
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = "<BaseModel>"
EXTERNAL_PREFIX = "<external>:"

ClassKey = str  # "module.qualname" e.g. "pkg.sub.mod.MyModel"


@dataclass
class RawField:
    name: str
    alias: str | None
    annotated_validator_funcs: list[ast.FunctionDef | ast.AsyncFunctionDef] = field(
        default_factory=list
    )


@dataclass
class RawValidator:
    name: str
    targets: list[str] | None
    """None means the target field list could not be resolved statically
    (e.g. built from a variable) -- the validator is skipped."""
    node: ast.FunctionDef | ast.AsyncFunctionDef


@dataclass
class RawClass:
    key: ClassKey
    file: str
    lineno: int
    base_refs: list[str]
    """Each entry is a resolved ClassKey, ROOT, or an EXTERNAL_PREFIX-tagged
    string carrying the unresolved base's source text."""
    own_fields: list[RawField]
    own_validators: dict[str, RawValidator]


def _module_name_for(file: Path, root: Path) -> str:
    try:
        rel = file.resolve().relative_to(root.resolve())
    except ValueError:
        rel = Path(file.name)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else file.stem


def discover_files(paths: list[str]) -> list[Path]:
    skip_dirs = {
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".tox",
    }
    out: list[Path] = []
    for p in paths:
        pp = Path(p)
        if pp.is_file() and pp.suffix == ".py":
            out.append(pp)
        elif pp.is_dir():
            for dirpath, dirnames, filenames in os.walk(pp):
                dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
                for fname in filenames:
                    if fname.endswith(".py"):
                        out.append(Path(dirpath) / fname)
    return sorted(set(out))


def _get_call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_classvar(ann: ast.AST) -> bool:
    if isinstance(ann, ast.Subscript):
        return _get_call_name(ann.value) == "ClassVar"
    return _get_call_name(ann) == "ClassVar"


def _extract_alias(value: ast.AST | None) -> str | None:
    if not isinstance(value, ast.Call):
        return None
    if _get_call_name(value.func) != "Field":
        return None
    alias = None
    validation_alias = None
    for kw in value.keywords:
        if kw.arg == "alias" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            alias = kw.value.value
        if kw.arg == "validation_alias" and isinstance(kw.value, ast.Constant) and isinstance(
            kw.value.value, str
        ):
            validation_alias = kw.value.value
    return alias if alias is not None else validation_alias


def _extract_annotated_validators(
    ann: ast.AST, module_funcs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    if not isinstance(ann, ast.Subscript) or _get_call_name(ann.value) != "Annotated":
        return []
    sl = ann.slice
    items = list(sl.elts) if isinstance(sl, ast.Tuple) else []
    results: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for item in items[1:]:
        if not isinstance(item, ast.Call):
            continue
        fname = _get_call_name(item.func)
        if fname not in ("AfterValidator", "BeforeValidator", "WrapValidator", "PlainValidator"):
            continue
        if not item.args:
            continue
        arg0 = item.args[0]
        if isinstance(arg0, ast.Name) and arg0.id in module_funcs:
            results.append(module_funcs[arg0.id])
        # Lambdas and cross-file references are not resolved (documented
        # limitation) -- silently skipped rather than guessed at.
    return results


def _classify_decorators(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[bool, list[str] | None]:
    """Returns (is_model_validator, field_validator_targets_or_None).
    field_validator_targets is None if this isn't a field_validator, or if
    it is but its target list can't be read statically.
    """
    for dec in node.decorator_list:
        call = dec if isinstance(dec, ast.Call) else None
        name = _get_call_name(call.func) if call else _get_call_name(dec)
        if name == "model_validator":
            return True, None
        if name == "field_validator" and call is not None:
            targets: list[str] = []
            ok = True
            for a in call.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    targets.append(a.value)
                else:
                    ok = False
            return False, (targets if ok and targets else None)
    return False, None


def parse_file(path: Path, root: Path) -> tuple[str, list[RawClass], dict[str, tuple[str, str]], SyntaxError | None]:
    """Returns (module_name, raw_classes, import_map, syntax_error)."""
    module_name = _module_name_for(path, root)
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as e:
        return module_name, [], {}, (e if isinstance(e, SyntaxError) else SyntaxError(str(e)))

    import_map: dict[str, tuple[str, str]] = {}
    module_alias_map: dict[str, str] = {}

    def package_of(mod: str) -> str:
        return mod.rsplit(".", 1)[0] if "." in mod else ""

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                pkg = module_name
                for _ in range(node.level):
                    pkg = package_of(pkg)
                if node.module:
                    target_module = f"{pkg}.{node.module}" if pkg else node.module
                else:
                    target_module = pkg
            else:
                target_module = node.module or ""
            for imported in node.names:
                if imported.name == "*":
                    continue
                local = imported.asname or imported.name
                import_map[local] = (target_module, imported.name)
        elif isinstance(node, ast.Import):
            for imported in node.names:
                local = imported.asname or imported.name.split(".")[0]
                module_alias_map[local] = imported.name

    module_funcs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {
        n.name: n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    def is_root_base(top_level_module: str, name: str) -> bool:
        # BaseSettings (pydantic-settings) is a BaseModel subclass with the
        # exact same field-order / info.data mechanics -- verified against
        # a real pydantic-settings install, not assumed.
        return (top_level_module == "pydantic" and name == "BaseModel") or (
            top_level_module == "pydantic_settings" and name == "BaseSettings"
        )

    def resolve_base(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            if node.id in import_map:
                target_module, orig = import_map[node.id]
                if is_root_base(target_module.split(".")[0], orig):
                    return ROOT
                return f"{target_module}.{orig}"
            if node.id in ("BaseModel", "BaseSettings"):
                # Not imported under this name in the import map we saw, but
                # named exactly like a known pydantic root -- treat as the
                # root unless a same-named class is defined in this file.
                return ROOT
            # Same-file class (may or may not exist yet; validated later).
            return f"{module_name}.{node.id}"
        if isinstance(node, ast.Attribute):
            base_name = _get_call_name(node.value) if isinstance(node.value, (ast.Name,)) else None
            if base_name and base_name in module_alias_map:
                mod = module_alias_map[base_name]
                if is_root_base(mod.split(".")[0], node.attr):
                    return ROOT
                return f"{mod}.{node.attr}"
            return EXTERNAL_PREFIX + ast.unparse(node)
        return EXTERNAL_PREFIX + (ast.unparse(node) if hasattr(ast, "unparse") else "<expr>")

    classes: list[RawClass] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        base_refs = [resolve_base(b) for b in node.bases if not isinstance(b, ast.keyword)]
        own_fields: list[RawField] = []
        own_validators: dict[str, RawValidator] = {}
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                fname = stmt.target.id
                if fname == "model_config" or _is_classvar(stmt.annotation):
                    continue
                alias = _extract_alias(stmt.value)
                validators = _extract_annotated_validators(stmt.annotation, module_funcs)
                own_fields.append(RawField(name=fname, alias=alias, annotated_validator_funcs=validators))
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_model_val, targets = _classify_decorators(stmt)
                if is_model_val:
                    continue
                if targets is not None:
                    own_validators[stmt.name] = RawValidator(name=stmt.name, targets=targets, node=stmt)
            elif (
                isinstance(stmt, ast.Assign)
                and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name)
            ):
                # `_x = field_validator("f1", "f2", mode="after")(shared_fn)`
                # -- the functional-call form of field_validator, applying an
                # existing function instead of decorating a new one.
                attr_name = stmt.targets[0].id
                val = stmt.value
                if (
                    isinstance(val, ast.Call)
                    and isinstance(val.func, ast.Call)
                    and _get_call_name(val.func.func) == "field_validator"
                    and val.args
                ):
                    field_targets: list[str] = []
                    ok = True
                    for a in val.func.args:
                        if isinstance(a, ast.Constant) and isinstance(a.value, str):
                            field_targets.append(a.value)
                        else:
                            ok = False
                    ref = val.args[0]
                    if ok and field_targets and isinstance(ref, ast.Name) and ref.id in module_funcs:
                        own_validators[attr_name] = RawValidator(
                            name=attr_name, targets=field_targets, node=module_funcs[ref.id]
                        )
        classes.append(
            RawClass(
                key=f"{module_name}.{node.name}",
                file=str(path),
                lineno=node.lineno,
                base_refs=base_refs,
                own_fields=own_fields,
                own_validators=own_validators,
            )
        )
    return module_name, classes, import_map, None
