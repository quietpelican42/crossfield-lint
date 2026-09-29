"""The runtime checker is ground truth. Every fixture must produce the same
(validator, validated_field, read_field, kind) findings whether reached
through the static AST checker or through check_model() on the imported
class.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from conftest import import_fixture, models_in
from crossfield_lint.model import Finding, Kind
from crossfield_lint.runtime import check_model
from crossfield_lint.static import check_paths

FixturePath = Callable[[str], Path]

FIXTURES = [
    "basic_get",
    "basic_bracket",
    "alias",
    "wildcard",
    "multi_target",
    "modes",
    "annotated_validator",
    "functional_call_validator",
    "base_settings",
    "inheritance",
    "unknown_field",
    "aliased_data",
    "negative_controls",
]


def _signature(findings: list[Finding]) -> list[tuple[Kind, str, str, str]]:
    return sorted((f.kind, f.validator, f.validated_field, f.read_field) for f in findings)


@pytest.mark.parametrize("fixture_name", FIXTURES)
def test_static_agrees_with_runtime(fixture_path: FixturePath, fixture_name: str) -> None:
    static_result = check_paths([str(fixture_path(fixture_name))])
    module = import_fixture(fixture_name)

    runtime_findings: list[Finding] = []
    for model in models_in(module).values():
        runtime_findings.extend(check_model(model))

    assert _signature(static_result.findings) == _signature(runtime_findings), fixture_name
