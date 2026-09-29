"""Turn raw `info.data` read sites into Findings, given a model's resolved
field order and aliases. Shared by the static and runtime checkers so the
two agree by construction on the classification rules; they differ only in
where the field order/aliases and the validator ASTs come from.
"""

from __future__ import annotations

from dataclasses import dataclass

from crossfield_lint.model import Finding, Kind, ModelInfo, Severity
from crossfield_lint.reads import ReadSite


@dataclass(frozen=True)
class Stats:
    dynamic_keys: int = 0
    """Reads whose key could not be resolved to a literal string."""

    skipped_unresolved_base: int = 0
    """Unknown-field checks skipped because the model has an unresolved
    base class, so completeness of the field set is not guaranteed."""


def classify_read(
    model: ModelInfo,
    validated_field: str,
    read: ReadSite,
    *,
    validator_name: str,
    file: str,
) -> tuple[Finding | None, str | None]:
    """Return (finding, note). `note` is one of "dynamic" or "unresolved"
    when no Finding is produced but the read was still noteworthy.
    """
    if read.key is None:
        return None, "dynamic"

    key = read.key

    # Alias-keyed read: `info.data` is always keyed by attribute name, never
    # by alias, regardless of how the model was constructed.
    for f in model.fields.values():
        if f.alias is not None and f.alias == key and f.name != key:
            return (
                Finding(
                    kind=Kind.ALIAS_KEYED,
                    severity=Severity.ERROR,
                    model=model.qualname,
                    validator=validator_name,
                    validated_field=validated_field,
                    read_field=key,
                    file=file,
                    line=read.lineno,
                    col=read.col,
                    message=(
                        f"{model.qualname}.{validator_name}: info.data is keyed by "
                        f"field name, not alias -- '{key}' is the alias of field "
                        f"'{f.name}'; use info.data[{f.name!r}]"
                    ),
                ),
                None,
            )

    if key not in model.fields:
        if not model.bases_resolved:
            return None, "unresolved"
        return (
            Finding(
                kind=Kind.UNKNOWN_FIELD,
                severity=Severity.ERROR,
                model=model.qualname,
                validator=validator_name,
                validated_field=validated_field,
                read_field=key,
                file=file,
                line=read.lineno,
                col=read.col,
                message=(
                    f"{model.qualname}.{validator_name}: info.data has no field "
                    f"'{key}' (not declared on this model or its bases)"
                ),
            ),
            None,
        )

    read_field = model.fields[key]
    validated = model.fields.get(validated_field)
    if validated is None:
        # Should not happen: validated_field always comes from model.field_order.
        return None, None

    if read_field.order >= validated.order:
        return (
            Finding(
                kind=Kind.NOT_YET_VALIDATED,
                severity=Severity.ERROR,
                model=model.qualname,
                validator=validator_name,
                validated_field=validated_field,
                read_field=key,
                file=file,
                line=read.lineno,
                col=read.col,
                message=(
                    f"{model.qualname}.{validator_name}: validating '{validated_field}' "
                    f"reads info.data[{key!r}], but '{key}' is declared "
                    f"{'at the same position as' if read_field.order == validated.order else 'after'} "
                    f"'{validated_field}' and is not validated yet (will be None/missing "
                    "or raise KeyError)"
                ),
            ),
            None,
        )

    return None, None
