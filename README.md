# crossfield-lint

Finds pydantic v2 field validators that read `info.data` for a field that has not been validated yet.

```python
from pydantic import BaseModel, ValidationInfo, field_validator


class Order(BaseModel):
    subtotal: float
    tax_rate: float

    @field_validator("subtotal")
    @classmethod
    def check_subtotal(cls, v: float, info: ValidationInfo) -> float:
        rate = info.data.get("tax_rate")  # None: 'tax_rate' is declared after 'subtotal'
        ...
```

```
$ crossfield-lint order.py
order.py:9:15: [error] not-yet-validated: Order.check_subtotal: validating 'subtotal' reads
info.data['tax_rate'], but 'tax_rate' is declared after 'subtotal' and is not validated yet
(will be None/missing or raise KeyError)
```

## Why

Pydantic v2 validates fields in declaration order, and a `@field_validator`
can read sibling fields already validated through `info.data`. That's a
documented, useful pattern for cross-field checks -- but it silently breaks
the moment a field it depends on moves later, whether from a reorder, an
inherited-field override, or someone adding a new field in between. The
read doesn't raise: `.get()` returns `None` and validation carries on as if
the dependent field were absent. A `[...]` read does raise, but as a plain
`KeyError` straight out of model construction, not a `ValidationError`, so
it doesn't look like a validation bug at first glance.

Pydantic's own docs
([Validation data](https://docs.pydantic.dev/latest/concepts/validators/#validation-data))
name this exact trap: "As validation is performed in the order fields are
defined, you have to make sure you are not accessing a field that hasn't
been validated yet." Nothing enforces it. Checked directly against pydantic
2.13.5: `ruff` (all rules), `mypy --strict` with the pydantic plugin, and
`pylint` all stay silent on the example above. Two existing pydantic
linters were checked for overlap: `flake8-pydantic` (rules PYD001-PYD010)
covers `Field()` call shape and `__pydantic_config__` usage, not validator
data flow; `pylint-pydantic` only teaches pylint that pydantic models have
dynamic attributes, so it stops flagging false `no-member` errors. Neither
touches `info.data` ordering. Searching ruff's full rule list for
"pydantic" or "validator" turns up no rule about validator data flow either.

Measured: `python bench/noise_floor.py` against 15 real, unrelated GitHub
repositories (each pinned to a commit, cloned fresh) that use pydantic v2
field validators with `info.data`:

```
adrienneyager/dbt-loom                   models= 12 findings=0
BBC-Esq/VectorDB-Plugin                  models= 18 findings=0
compiler-explorer/explain                models= 13 findings=0
developmentseed/tipg                     models= 37 findings=0
dnotitia/smoothie-qwen                   models=  5 findings=0
galaxyproject/gravity                    models= 17 findings=0
immortal71/openoncology                  models= 29 findings=0
lemonyte/wastebin                        models=  1 findings=0
plantcad/genecad                         models=  3 findings=0
plexe-ai/plexe                           models=  3 findings=0
serkanyasr/agentic_rag_project           models= 15 findings=0
the-momentum/fhir-mcp-server             models= 14 findings=0
ton-studio/ton-labels                    models=  3 findings=0
zhai-lw/L3AC                             models=  4 findings=0
zornade/visura-api                       models=  3 findings=0

repos checked: 15/15 (skipped: 0)
total models checked: 177
total findings: 0
```

Zero findings across 177 models is a clean noise floor, not evidence the bug
never happens in the wild -- it means these particular repos happen to read
`info.data` correctly. Every distinct validator in the sample that reads
`info.data` (31 read expressions, by grep, across the 15 repos) was checked
by hand against its model's field order to confirm the zero findings were
genuine true negatives, not the checker silently skipping the class (see
Limitations for the one case, `pydantic_settings.BaseSettings`, that used to
do exactly that until it was fixed during this measurement -- before the
fix, several of these repos' config classes weren't analyzed at all).

## Installation

```sh
pip install crossfield-lint
```

## Usage

### CLI

```sh
crossfield-lint src/
crossfield-lint src/models.py --format json
```

### pre-commit

```yaml
repos:
  - repo: https://github.com/__GH_OWNER__/crossfield-lint
    rev: v0.1.0
    hooks:
      - id: crossfield-lint
```

### Runtime, against an already-imported model

```python
from crossfield_lint import check_model
from mymodels import Order

for finding in check_model(Order):
    print(finding.format_text())
```

`check_model` is also what to reach for in a test suite: assert a model has
no findings the same way you'd assert it has no lint errors.

## Reference

### CLI

```
crossfield-lint [--format text|json] PATH [PATH ...]
```

| Exit code | Meaning |
| --- | --- |
| `0` | Clean -- no findings. |
| `1` | Findings reported. |
| `2` | Could not analyse (bad path, or a file that failed to parse). |

### Python API

| Name | Description |
| --- | --- |
| `check_model(model_cls)` | Runtime checker. Takes an imported `BaseModel` (or `BaseSettings`) subclass, returns `list[Finding]`. |
| `check_paths(paths)` | Static checker. Takes a list of file/directory paths, returns an `AnalysisResult` (`.findings`, `.models_checked`, `.files_with_errors`). |
| `check_source(source, filename=...)` | Static checker over an in-memory string (no cross-file resolution). |
| `Finding` | One problematic read: `.kind`, `.severity`, `.model`, `.validator`, `.validated_field`, `.read_field`, `.file`, `.line`, `.col`, `.message`, `.as_dict()`, `.format_text()`. |
| `Kind` | `NOT_YET_VALIDATED`, `UNKNOWN_FIELD`, `ALIAS_KEYED`. |

## How it works

**Static checker** (`crossfield_lint.static`): parses every file with `ast`
(never imports the code). It finds `BaseModel`/`BaseSettings` subclasses,
resolves their base classes across files where the import is a plain
relative or same-tree absolute import, and computes each model's field
order with the same C3 linearization pydantic's metaclass uses -- verified
against real pydantic output for single inheritance, multiple inheritance,
diamond inheritance, and field overrides (an overridden field keeps its
ancestor's position; it does not move to where it's redeclared). It then
finds every `field_validator` (decorator or functional-call form),
`AfterValidator`/`BeforeValidator`/`WrapValidator`/`PlainValidator` in
`Annotated[...]`, resolves each one's target field(s) (including `'*'` and
multi-field lists), and walks each validator's body for `info.data[...]`,
`.get(...)`, `in info.data` and simple aliases (`d = info.data`). A read is
flagged if the field it names is not strictly earlier than the field being
validated, doesn't exist on the model at all, or matches a field's alias
instead of its attribute name. `model_validator` methods are never
inspected: `mode='after'` sees every field already validated, and
`mode='before'` receives the raw input, not `info.data`.

**Runtime checker** (`crossfield_lint.runtime`): the ground truth the
static checker is tested against. Given an already-imported model class, it
trusts pydantic's own `model_fields` (field order, aliases) and
`__pydantic_decorators__` (which functions are validators, and their target
fields) instead of recomputing them, and only uses `ast` (via
`inspect.getsource`) to find the `info.data` reads inside each validator's
body. Every fixture in the test suite is checked both ways and asserted
identical.

## Limitations

- **`mode` doesn't matter, on purpose.** `field_validator(mode=...)` in
  `before`/`after`/`wrap`/`plain` all see the same `info.data` contents
  (verified against pydantic 2.13.5) -- the set of fields validated so far,
  not "raw" vs "validated" data. The checker treats all four identically.
- **A dynamic key can't be resolved.** `info.data[some_variable]` or an
  f-string key isn't flagged either way; the checker only understands
  literal string keys.
- **Cross-file resolution is best-effort.** It follows plain relative
  imports (`from .base import Parent`) and absolute imports that land
  inside the files you pass it. It does not follow `sys.path` tricks, star
  imports, or namespace packages split across roots. A base class it can't
  resolve is not silently assumed safe: the class is still checked, but
  only reads of fields declared in that class's own body are checked for
  order (fields always validate after everything an unresolved base
  contributes, so that half is still sound); reads of a name the checker
  can't see declared anywhere are not reported as typos, since they might
  be real fields on the unresolved base.
- **A base class outside pydantic's tree is invisible.** If a class's only
  path to `BaseModel` runs through a base the checker can't resolve at all
  (not `pydantic.BaseModel`/`pydantic_settings.BaseSettings`, and not
  another class in the files you passed it), the checker can't tell it's a
  model and skips it silently. `BaseSettings` itself is recognized
  explicitly (verified: it validates fields the same way as `BaseModel`).
- **The `info` parameter must be named `info`, or annotated
  `ValidationInfo`/`FieldValidationInfo`.** That covers pydantic's own
  documented style and everything found in the noise-floor sample; a
  validator that renames it to something else with no annotation is
  invisible to the static checker.
- **Legacy `@validator` (v1-style) is out of scope.** It receives a
  `values: dict` parameter, not `info.data` -- a different API with its own
  failure modes, not this one.
- **A lambda passed to `AfterValidator`/etc. is not scanned.** Only a
  reference to a named function (in the same file, for the static checker)
  is resolved.
- **Legacy `validation_alias=AliasPath(...)`/`AliasChoices(...)` are not
  read.** Only a plain string alias is checked for the alias-keyed-read
  case.

## Compatibility

Run on Python 3.14.7 (this machine) against pydantic 2.13.5 and
pydantic-settings 2.x. CI (`.github/workflows/test.yml`) runs the same
suite on 3.11-3.14; those are "run in CI", not separately hand-verified
here.

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python -m mypy src tests --strict
.venv/bin/python bench/noise_floor.py   # downloads pinned repos into a gitignored cache
```

## License

MIT. See [LICENSE](LICENSE).
