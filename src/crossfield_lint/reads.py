"""AST-level detection of `info.data` reads inside a validator function body.

Shared by the static checker (which parses source files without importing
them) and the runtime checker (which parses the source of an already-loaded
function via `inspect.getsource`, using pydantic's own metadata for field
order and aliases as ground truth).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class ReadSite:
    key: str | None
    """The literal string key read from `info.data`, or None if the key is
    not a literal (a variable, an f-string, a computed expression, ...) and
    so cannot be resolved statically."""

    lineno: int
    col: int


def find_info_param_name(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Pick the parameter that carries `ValidationInfo`.

    Convention first: pydantic's own docs and virtually all real code name
    it `info`. Falls back to a parameter whose annotation mentions
    `ValidationInfo` / `FieldValidationInfo` (the deprecated v2 alias) for
    the (rare) case where it is renamed.
    """
    args = func.args
    all_params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    for a in all_params:
        if a.arg == "info":
            return "info"
    for a in all_params:
        ann = a.annotation
        if ann is None:
            continue
        text = ast.unparse(ann) if hasattr(ast, "unparse") else ""
        if "ValidationInfo" in text:
            return a.arg
    return None


class _ReadCollector(ast.NodeVisitor):
    """Walks a function body top to bottom, tracking simple aliases of
    `info.data` (`d = info.data`) and collecting every subscript / `.get()`
    / containment-test read performed through the info-data expression or
    one of its aliases.
    """

    def __init__(self, info_param: str) -> None:
        self.info_param = info_param
        self.aliases: set[str] = set()
        self.reads: list[ReadSite] = []

    def _is_info_data(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Attribute) and node.attr == "data":
            return isinstance(node.value, ast.Name) and node.value.id == self.info_param
        if isinstance(node, ast.Name):
            return node.id in self.aliases
        return False

    @staticmethod
    def _literal_str(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def visit_Assign(self, node: ast.Assign) -> None:
        # Track `alias = info.data` (plain rebinding, not a subscript/copy
        # method). Anything else assigned to a name that was previously an
        # alias un-marks it.
        self.generic_visit(node)
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            if self._is_info_data(node.value):
                self.aliases.add(target)
            elif target in self.aliases:
                self.aliases.discard(target)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self.generic_visit(node)
        if self._is_info_data(node.value):
            key = self._literal_str(node.slice)
            self.reads.append(ReadSite(key, node.lineno, node.col_offset))

    def visit_Call(self, node: ast.Call) -> None:
        self.generic_visit(node)
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in ("get", "pop")
            and self._is_info_data(func.value)
        ):
            key = self._literal_str(node.args[0]) if node.args else None
            self.reads.append(ReadSite(key, node.lineno, node.col_offset))

    def visit_Compare(self, node: ast.Compare) -> None:
        self.generic_visit(node)
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.In, ast.NotIn)) and self._is_info_data(comparator):
                key = self._literal_str(node.left)
                self.reads.append(ReadSite(key, node.lineno, node.col_offset))


def collect_reads(
    func: ast.FunctionDef | ast.AsyncFunctionDef, info_param: str
) -> list[ReadSite]:
    collector = _ReadCollector(info_param)
    for stmt in func.body:
        collector.visit(stmt)
    return collector.reads
