from typing import Annotated

from pydantic import AfterValidator, BaseModel, ValidationInfo


def check_a(v: str, info: ValidationInfo) -> str:
    # 'b' is declared after 'a'.
    later = info.data.get("b")
    return v


class M(BaseModel):
    a: Annotated[str, AfterValidator(check_a)]
    b: str
