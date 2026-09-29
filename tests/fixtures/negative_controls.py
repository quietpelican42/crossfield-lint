"""Patterns that must NOT be flagged."""

from pydantic import BaseModel, ValidationInfo, field_validator, model_validator


class EarlierFields(BaseModel):
    a: str
    b: str
    c: str

    @field_validator("c")
    @classmethod
    def check_c(cls, v: str, info: ValidationInfo) -> str:
        # Both 'a' and 'b' are declared earlier -- always safe.
        x = info.data.get("a")
        y = info.data["b"]
        z = "a" in info.data
        return v


class AfterModelValidator(BaseModel):
    a: str
    b: str

    @model_validator(mode="after")
    def check(self) -> "AfterModelValidator":
        # Reading fields off self is fine regardless of declaration order:
        # by mode='after' every field has already been validated.
        _ = self.a
        _ = self.b
        return self


class BeforeModelValidator(BaseModel):
    a: str
    b: str

    @model_validator(mode="before")
    @classmethod
    def check(cls, data: object) -> object:
        # mode='before' model validators get the raw input, not info.data.
        return data


class UnrelatedDotData(BaseModel):
    a: str
    b: str
    payload: dict[str, int] = {}

    @field_validator("a")
    @classmethod
    def check_a(cls, v: str, info: ValidationInfo) -> str:
        # `.data` on something that is not the ValidationInfo parameter.
        # This is a different object entirely, not info.data.
        stash = {"data": {"b": 1}}
        also_fine = stash["data"].get("b")
        return v


class ContextNotData(BaseModel):
    a: str
    b: str

    @field_validator("a")
    @classmethod
    def check_a(cls, v: str, info: ValidationInfo) -> str:
        # info.context is a different attribute; must not be confused with
        # info.data.
        ctx = info.context
        return v
