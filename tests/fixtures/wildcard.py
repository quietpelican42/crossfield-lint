from pydantic import BaseModel, ValidationInfo, field_validator


class M(BaseModel):
    a: str
    b: str
    c: str

    @field_validator("*")
    @classmethod
    def check_all(cls, v: str, info: ValidationInfo) -> str:
        # Reading 'b' is broken when this runs for 'a' (b not validated yet)
        # but fine when it runs for 'c' (b already validated).
        seen_b = info.data.get("b")
        return v
