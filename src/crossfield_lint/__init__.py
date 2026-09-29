"""Find pydantic v2 field validators that read info.data for a field that
has not been validated yet.

Two entry points:

- ``crossfield_lint.static``: an AST-based checker that never imports the
  target code. Use it from the CLI or a pre-commit hook.
- ``crossfield_lint.runtime.check_model``: inspects an already-imported
  ``pydantic.BaseModel`` subclass via its own ``__pydantic_decorators__`` and
  ``model_fields``. This is the ground truth the static checker is tested
  against.
"""

from crossfield_lint.model import Finding, Severity
from crossfield_lint.runtime import check_model
from crossfield_lint.static import check_paths, check_source

__all__ = [
    "Finding",
    "Severity",
    "check_model",
    "check_paths",
    "check_source",
]

__version__ = "0.1.0"
