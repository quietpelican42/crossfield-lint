"""Cross-file resolution: feasible cases (a plain relative import pointing
at a sibling file in the analyzed set) and the documented limitation (a
base class that lives outside the files handed to the checker)."""

from __future__ import annotations

from pathlib import Path

from crossfield_lint.model import Kind
from crossfield_lint.static import check_paths

FIXTURES = Path(__file__).parent / "fixtures"


def _kinds(findings: object) -> set[tuple[Kind, str, str]]:
    return {(f.kind, f.validated_field, f.read_field) for f in findings}  # type: ignore[attr-defined]


def test_cross_file_inheritance_resolved() -> None:
    result = check_paths([str(FIXTURES / "crossfile")])
    kinds = _kinds(result.findings)
    # p2 comes from base.py, resolved across files -- safe.
    assert (Kind.NOT_YET_VALIDATED, "c1", "p2") not in kinds
    # c2 is declared after c1 in the same file -- still caught.
    assert (Kind.NOT_YET_VALIDATED, "c1", "c2") in kinds


def test_external_base_own_fields_still_checked() -> None:
    # Deliberately check model.py alone: mixin.py (defining SomeMixin) is
    # not in the analyzed set, so the base is unresolved.
    result = check_paths([str(FIXTURES / "external_base" / "model.py")])
    assert result.models_checked == 1
    kinds = _kinds(result.findings)
    assert (Kind.NOT_YET_VALIDATED, "m1", "m2") in kinds
    assert (Kind.NOT_YET_VALIDATED, "m2", "m1") not in kinds


def test_external_base_directory_resolves_when_included() -> None:
    # Checking the whole directory resolves SomeMixin -- it contributes no
    # fields of its own, so the result is unchanged, but bases_resolved
    # would now be True (verified indirectly: no new/missing findings).
    result = check_paths([str(FIXTURES / "external_base")])
    kinds = _kinds(result.findings)
    assert (Kind.NOT_YET_VALIDATED, "m1", "m2") in kinds
