from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Callable

import pytest
from pydantic import BaseModel

FIXTURES = Path(__file__).parent / "fixtures"


def import_fixture(name: str) -> ModuleType:
    path = FIXTURES / f"{name}.py"
    mod_name = f"crossfield_lint_fixture_{name}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def models_in(module: ModuleType) -> dict[str, type[BaseModel]]:
    out: dict[str, type[BaseModel]] = {}
    for name, obj in vars(module).items():
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and obj is not BaseModel
            and obj.__module__ == module.__name__
        ):
            out[name] = obj
    return out


@pytest.fixture
def fixture_path() -> "Callable[[str], Path]":
    def _path(name: str) -> Path:
        return FIXTURES / f"{name}.py"

    return _path
