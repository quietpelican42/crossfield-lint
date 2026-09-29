from pydantic import BaseModel, ValidationInfo, field_validator


class M(BaseModel):
    a: str
    b: str

    @field_validator("a")
    @classmethod
    def check_a(cls, v: str, info: ValidationInfo) -> str:
        # 'b' is declared after 'a' -- raises KeyError at runtime.
        later = info.data["b"]
        return v
