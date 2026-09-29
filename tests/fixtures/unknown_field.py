from pydantic import BaseModel, ValidationInfo, field_validator


class M(BaseModel):
    a: str
    b: str

    @field_validator("b")
    @classmethod
    def check_b(cls, v: str, info: ValidationInfo) -> str:
        # Typo: no field named "aa" on this model.
        typo = info.data.get("aa")
        return v
