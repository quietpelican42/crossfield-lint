from pydantic import BaseModel, ValidationInfo, field_validator


class Parent(BaseModel):
    p1: str
    p2: str


class Child(Parent):
    c1: str
    c2: str

    @field_validator("c1")
    @classmethod
    def check_c1(cls, v: str, info: ValidationInfo) -> str:
        # p1/p2 are inherited fields, always validated before any of
        # Child's own fields -- safe.
        ok = info.data.get("p1")
        # c2 is declared after c1 in this same class -- broken.
        bad = info.data.get("c2")
        return v


class Override(Parent):
    # Redeclaring p1 keeps its original (ancestor) position, ahead of any
    # new field this subclass declares.
    p1: str = "overridden"
    o1: str

    @field_validator("o1")
    @classmethod
    def check_o1(cls, v: str, info: ValidationInfo) -> str:
        ok = info.data.get("p1")  # still fine: p1 keeps its original slot
        ok2 = info.data.get("p2")
        return v
