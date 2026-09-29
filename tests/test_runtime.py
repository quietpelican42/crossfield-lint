from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from conftest import import_fixture, models_in
from crossfield_lint.model import Finding, Kind
from crossfield_lint.runtime import check_model

FixturePath = Callable[[str], Path]


def _kinds(findings: list[Finding]) -> set[tuple[Kind, str, str]]:
    return {(f.kind, f.validated_field, f.read_field) for f in findings}


def test_check_model_rejects_non_model() -> None:
    with pytest.raises(TypeError):
        check_model(int)


def test_basic_get_runtime_agrees_and_reproduces() -> None:
    module = import_fixture("basic_get")
    m_cls = module.M
    findings = check_model(m_cls)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in _kinds(findings)

    # Prove the silent no-op for real: constructing the model does not raise.
    instance = m_cls(a="x", b="y")
    assert instance.a == "x" and instance.b == "y"


def test_basic_bracket_runtime_raises_keyerror() -> None:
    module = import_fixture("basic_bracket")
    m_cls = module.M
    findings = check_model(m_cls)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in _kinds(findings)
    # pydantic-core does not wrap KeyError as a ValidationError -- it
    # propagates as a raw KeyError straight out of model construction.
    with pytest.raises(KeyError):
        m_cls(a="x", b="y")


def test_alias_runtime_agrees_and_reproduces() -> None:
    module = import_fixture("alias")
    m_cls = module.M
    findings = check_model(m_cls)
    assert (Kind.ALIAS_KEYED, "a", "bAlias") in _kinds(findings)
    # The alias-keyed read returns None even though 'b' *was* validated
    # (it's declared before 'a').
    instance = m_cls(bAlias="y", a="x")
    assert instance.a == "x"


def test_wildcard_runtime_agrees() -> None:
    module = import_fixture("wildcard")
    m_cls = module.M
    findings = check_model(m_cls)
    kinds = _kinds(findings)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in kinds
    assert (Kind.NOT_YET_VALIDATED, "c", "b") not in kinds
    m_cls(a="1", b="2", c="3")  # does not raise; 'a' silently saw None for 'b'


def test_multi_target_runtime_agrees() -> None:
    module = import_fixture("multi_target")
    m_cls = module.M
    findings = check_model(m_cls)
    kinds = _kinds(findings)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in kinds
    assert (Kind.NOT_YET_VALIDATED, "c", "b") not in kinds


def test_modes_runtime_agrees() -> None:
    module = import_fixture("modes")
    for cls_name in ("MBefore", "MWrap", "MPlain"):
        m_cls = getattr(module, cls_name)
        findings = check_model(m_cls)
        assert (Kind.NOT_YET_VALIDATED, "a", "b") in _kinds(findings), cls_name
        m_cls(a="x", b="y")  # does not raise for any mode


def test_annotated_validator_runtime_agrees() -> None:
    module = import_fixture("annotated_validator")
    m_cls = module.M
    findings = check_model(m_cls)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in _kinds(findings)
    m_cls(a="x", b="y")  # does not raise; silently saw None for 'b'


def test_inheritance_runtime_agrees() -> None:
    module = import_fixture("inheritance")
    child_cls = module.Child
    override_cls = module.Override
    child_kinds = _kinds(check_model(child_cls))
    assert (Kind.NOT_YET_VALIDATED, "c1", "p1") not in child_kinds
    assert (Kind.NOT_YET_VALIDATED, "c1", "c2") in child_kinds
    override_kinds = _kinds(check_model(override_cls))
    assert (Kind.NOT_YET_VALIDATED, "o1", "p1") not in override_kinds
    assert (Kind.NOT_YET_VALIDATED, "o1", "p2") not in override_kinds


def test_unknown_field_runtime_agrees() -> None:
    module = import_fixture("unknown_field")
    m_cls = module.M
    findings = check_model(m_cls)
    assert (Kind.UNKNOWN_FIELD, "b", "aa") in _kinds(findings)
    m_cls(a="x", b="y")  # does not raise; the typo'd read just returns None


def test_aliased_data_runtime_agrees() -> None:
    module = import_fixture("aliased_data")
    m_cls = module.M
    findings = check_model(m_cls)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in _kinds(findings)
    with pytest.raises(KeyError):
        m_cls(a="x", b="y")


def test_functional_call_validator_runtime_agrees() -> None:
    module = import_fixture("functional_call_validator")
    m_cls = module.M
    findings = check_model(m_cls)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in _kinds(findings)
    m_cls(a="x", b="y")  # does not raise; silently saw None for 'b'


def test_base_settings_runtime_agrees() -> None:
    module = import_fixture("base_settings")
    settings_cls = module.Settings
    findings = check_model(settings_cls)
    assert (Kind.NOT_YET_VALIDATED, "a", "b") in _kinds(findings)


def test_negative_controls_runtime_clean() -> None:
    module = import_fixture("negative_controls")
    for name, model in models_in(module).items():
        findings = check_model(model)
        assert findings == [], f"{name} should have no findings, got {findings}"
