from pydantic import BaseModel, ValidationInfo, field_validator


class M(BaseModel):
    a: str
    b: str

    @field_validator("a")
    @classmethod
    def check_a(cls, v: str, info: ValidationInfo) -> str:
        d = info.data
        later = d["b"]  # same bug, reached through an alias of info.data
        return v
