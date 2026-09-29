from __future__ import annotations

from pathlib import Path
from typing import Callable

from crossfield_lint.model import Finding, Kind
from crossfield_lint.static import check_paths

FixturePath = Callable[[str], Path]


def _kinds(findings: list[Finding]) -> set[tuple[Kind, str, str]]:
    return {(f.kind, f.validated_field, f.read_field) for f in findings}


def test_basic_get_flagged(fixture_path: FixturePath) -> None:
    result = check_paths([str(fixture_path("basic_get"))])
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in _kinds(result.findings)


def test_basic_bracket_flagged(fixture_path: FixturePath) -> None:
    result = check_paths([str(fixture_path("basic_bracket"))])
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in _kinds(result.findings)


def test_alias_keyed_flagged(fixture_path: FixturePath) -> None:
    result = check_paths([str(fixture_path("alias"))])
    kinds = _kinds(result.findings)
    assert (Kind.ALIAS_KEYED, "a", "bAlias") in kinds


def test_wildcard_flags_only_early_fields(fixture_path: FixturePath) -> None:
    result = check_paths([str(fixture_path("wildcard"))])
    kinds = _kinds(result.findings)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in kinds
    assert (Kind.NOT_YET_VALIDATED, "b", "b") in kinds  # reading itself, not yet set
    assert (Kind.NOT_YET_VALIDATED, "c", "b") not in kinds


def test_multi_target_flags_only_early_target(fixture_path: FixturePath) -> None:
    result = check_paths([str(fixture_path("multi_target"))])
    kinds = _kinds(result.findings)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in kinds
    assert (Kind.NOT_YET_VALIDATED, "c", "b") not in kinds


def test_all_modes_flagged_identically(fixture_path: FixturePath) -> None:
    result = check_paths([str(fixture_path("modes"))])
    kinds = _kinds(result.findings)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in kinds
    assert len(result.findings) == 3  # before, wrap, plain -- one each


def test_annotated_after_validator_flagged(fixture_path: FixturePath) -> None:
    result = check_paths([str(fixture_path("annotated_validator"))])
    kinds = _kinds(result.findings)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in kinds


def test_inheritance(fixture_path: FixturePath) -> None:
    result = check_paths([str(fixture_path("inheritance"))])
    kinds = _kinds(result.findings)
    # Child.check_c1: p1 is inherited (safe), c2 is declared after c1 (bad).
    assert (Kind.NOT_YET_VALIDATED, "c1", "p1") not in kinds
    assert (Kind.NOT_YET_VALIDATED, "c1", "c2") in kinds
    # Override.check_o1: p1 keeps its ancestor slot despite being
    # redeclared in the subclass -- still safe.
    assert (Kind.NOT_YET_VALIDATED, "o1", "p1") not in kinds
    assert (Kind.NOT_YET_VALIDATED, "o1", "p2") not in kinds


def test_unknown_field_flagged(fixture_path: FixturePath) -> None:
    result = check_paths([str(fixture_path("unknown_field"))])
    kinds = _kinds(result.findings)
    assert (Kind.UNKNOWN_FIELD, "b", "aa") in kinds


def test_aliased_data_variable_flagged(fixture_path: FixturePath) -> None:
    result = check_paths([str(fixture_path("aliased_data"))])
    kinds = _kinds(result.findings)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in kinds


def test_functional_call_validator_flagged(fixture_path: FixturePath) -> None:
    result = check_paths([str(fixture_path("functional_call_validator"))])
    kinds = _kinds(result.findings)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in kinds


def test_base_settings_recognized_as_model(fixture_path: FixturePath) -> None:
    result = check_paths([str(fixture_path("base_settings"))])
    assert result.models_checked == 1
    kinds = _kinds(result.findings)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in kinds


def test_negative_controls_clean(fixture_path: FixturePath) -> None:
    result = check_paths([str(fixture_path("negative_controls"))])
    assert result.findings == []


def test_models_checked_count(fixture_path: FixturePath) -> None:
    result = check_paths([str(fixture_path("inheritance"))])
    assert result.models_checked == 3  # Parent, Child, Override


def test_syntax_error_reported_not_crashed(tmp_path: Path) -> None:
    bad = tmp_path / "broken.py"
    bad.write_text("class Foo(BaseModel:\n    a: str\n")
    result = check_paths([str(bad)])
    assert result.files_with_errors
    assert result.findings == []
