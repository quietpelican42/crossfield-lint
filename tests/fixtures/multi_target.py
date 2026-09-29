from pydantic import BaseModel, ValidationInfo, field_validator


class M(BaseModel):
    a: str
    b: str
    c: str

    @field_validator("a", "c")
    @classmethod
    def check(cls, v: str, info: ValidationInfo) -> str:
        # Broken when validating 'a' (b not yet validated), fine when
        # validating 'c' (b already validated by then).
        seen_b = info.data.get("b")
        return v
