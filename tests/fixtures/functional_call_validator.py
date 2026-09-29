"""The functional-call form of field_validator: applying an existing
function to a field list instead of decorating a new one. Found in real
code (e.g. galaxyproject/gravity) as a way to share one validator function
across several fields.
"""

from pydantic import BaseModel, ValidationInfo, field_validator


def shared_check(cls: type, v: str, info: ValidationInfo) -> str:
    # 'b' is declared after 'a'.
    later = info.data.get("b")
    return v


class M(BaseModel):
    a: str
    b: str

    _check_a = field_validator("a", mode="after")(shared_check)
