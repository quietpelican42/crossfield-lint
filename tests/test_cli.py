from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest

from crossfield_lint.cli import main

FixturePath = Callable[[str], Path]


def test_exit_0_on_clean(fixture_path: FixturePath, capsys: pytest.CaptureFixture[str]) -> None:
    code = main([str(fixture_path("negative_controls"))])
    assert code == 0


def test_exit_1_on_findings(fixture_path: FixturePath, capsys: pytest.CaptureFixture[str]) -> None:
    code = main([str(fixture_path("basic_get"))])
    assert code == 1


def test_exit_2_on_missing_path(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["/no/such/path/at/all"])
    assert code == 2


def test_exit_2_on_syntax_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "broken.py"
    bad.write_text("def(:\n")
    code = main([str(bad)])
    assert code == 2


def test_json_output_shape(fixture_path: FixturePath, capsys: pytest.CaptureFixture[str]) -> None:
    code = main([str(fixture_path("basic_get")), "--format", "json"])
    assert code == 1
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["models_checked"] == 1
    assert len(payload["findings"]) >= 1
    finding = payload["findings"][0]
    assert set(finding) >= {
        "kind",
        "severity",
        "model",
        "validator",
        "validated_field",
        "read_field",
        "file",
        "line",
        "col",
        "message",
    }


def test_text_output_format(fixture_path: FixturePath, capsys: pytest.CaptureFixture[str]) -> None:
    code = main([str(fixture_path("basic_get"))])
    assert code == 1
    out = capsys.readouterr().out
    assert "not-yet-validated" in out
    assert ":" in out.splitlines()[0]
