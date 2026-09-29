from pydantic import BaseModel, ValidationInfo, ValidatorFunctionWrapHandler, field_validator


class MBefore(BaseModel):
    a: str
    b: str

    @field_validator("a", mode="before")
    @classmethod
    def check_a(cls, v: str, info: ValidationInfo) -> str:
        later = info.data.get("b")
        return v


class MWrap(BaseModel):
    a: str
    b: str

    @field_validator("a", mode="wrap")
    @classmethod
    def check_a(cls, v: str, handler: ValidatorFunctionWrapHandler, info: ValidationInfo) -> str:
        later = info.data.get("b")
        result: str = handler(v)
        return result


class MPlain(BaseModel):
    a: str
    b: str

    @field_validator("a", mode="plain")
    @classmethod
    def check_a(cls, v: str, info: ValidationInfo) -> str:
        later = info.data.get("b")
        return v
