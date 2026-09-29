from pydantic import BaseModel, ValidationInfo, field_validator

from .mixin import SomeMixin


class M(SomeMixin, BaseModel):
    # When this file is checked on its own (not together with mixin.py),
    # SomeMixin is an unresolved base: bases_resolved is False for M. Its
    # own two fields, m1/m2, still have a known relative order because
    # they're both declared in this class's own body -- unresolved bases
    # only ever add fields *before* a class's own ones, never reorder them.
    m1: str
    m2: str

    @field_validator("m1")
    @classmethod
    def check_m1(cls, v: str, info: ValidationInfo) -> str:
        # m2 is declared after m1 in this same class -- still detectable.
        bad = info.data.get("m2")
        return v

    @field_validator("m2")
    @classmethod
    def check_m2(cls, v: str, info: ValidationInfo) -> str:
        # m1 is declared before m2 in this same class -- fine.
        ok = info.data.get("m1")
        return v
