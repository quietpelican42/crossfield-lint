from pydantic import BaseModel, Field, ValidationInfo, field_validator


class M(BaseModel):
    b: str = Field(alias="bAlias")
    a: str

    @field_validator("a")
    @classmethod
    def check_a(cls, v: str, info: ValidationInfo) -> str:
        # info.data is keyed by attribute name ("b"), never by alias, even
        # though 'b' is declared (and thus already validated) before 'a'.
        wrong = info.data.get("bAlias")
        return v
