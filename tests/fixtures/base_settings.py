"""BaseSettings (pydantic-settings) is a BaseModel subclass with the same
field-order / info.data mechanics. Found in real code (application config
classes) far more often than a plain BaseModel for this exact pattern.
"""

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    a: str = "1"
    b: str = "2"

    @field_validator("a")
    @classmethod
    def check_a(cls, v: str, info: ValidationInfo) -> str:
        # 'b' is declared after 'a'.
        later = info.data.get("b")
        return v
