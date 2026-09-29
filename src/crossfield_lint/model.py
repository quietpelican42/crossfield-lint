"""Shared data types used by both the static and runtime checkers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """How confident a finding is."""

    ERROR = "error"
    """The read is provably wrong: a not-yet-validated field, an unknown
    field name, or a field indexed by its alias instead of its name."""

    WARNING = "warning"
    """Something worth a human look but not provably wrong (e.g. a dynamic
    key the checker cannot resolve)."""


class Kind(str, Enum):
    NOT_YET_VALIDATED = "not-yet-validated"
    """`info.data` is read for a field declared later than the field(s)
    being validated, so it is always missing at that point."""

    UNKNOWN_FIELD = "unknown-field"
    """`info.data` is read for a name that is not a field of the model at
    all (typo, or a field that was renamed/removed)."""

    ALIAS_KEYED = "alias-keyed"
    """`info.data` is read using a field's alias rather than its Python
    attribute name. `info.data` is always keyed by attribute name."""

    UNRESOLVED = "unresolved"
    """The checker could not determine whether the read is safe (dynamic
    key, or a base class it could not resolve). Not a finding by itself;
    surfaced only in verbose/debug output."""


@dataclass(frozen=True)
class Finding:
    """One problematic `info.data` read."""

    kind: Kind
    severity: Severity
    model: str
    """Qualified model class name, e.g. `pkg.mod.MyModel`."""

    validator: str
    """Name of the validator function."""

    validated_field: str
    """The field whose validator performs the read (the one being
    validated when the read happens)."""

    read_field: str
    """The field name/key that was read from `info.data`."""

    file: str
    line: int
    col: int
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "severity": self.severity.value,
            "model": self.model,
            "validator": self.validator,
            "validated_field": self.validated_field,
            "read_field": self.read_field,
            "file": self.file,
            "line": self.line,
            "col": self.col,
            "message": self.message,
        }

    def format_text(self) -> str:
        return (
            f"{self.file}:{self.line}:{self.col}: "
            f"[{self.severity.value}] {self.kind.value}: {self.message}"
        )


@dataclass
class FieldInfo:
    name: str
    alias: str | None = None
    order: int = 0
    """Position in the fully-resolved field order (0 = validated first)."""


@dataclass
class ModelInfo:
    qualname: str
    fields: dict[str, FieldInfo] = field(default_factory=dict)
    field_order: list[str] = field(default_factory=list)
    bases_resolved: bool = True
    """False if at least one base class could not be resolved to a known
    BaseModel subclass (e.g. imported from a third-party package). Field
    order and unknown-field checks are then best-effort only."""
