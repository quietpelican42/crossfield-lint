from pydantic import ValidationInfo, field_validator

from .base import Base


class Child(Base):
    c1: str
    c2: str

    @field_validator("c1")
    @classmethod
    def check_c1(cls, v: str, info: ValidationInfo) -> str:
        ok = info.data.get("p2")  # inherited from another file -- safe
        bad = info.data.get("c2")  # declared after c1 in this file -- broken
        return v
