---
myst:
  html_meta:
    description: Write the schema that describes an interface's relation data, and share it with the interface library that implements it.
---

(how-to-write-an-interface-schema)=
# How to write an interface schema

Every interface in the monorepo can declare a `schema.py`, which describes the relation data the interface carries. The schema is the machine-readable counterpart to the prose in the interface's `README.md`: the README says what each side is expected to do, and the schema says exactly what goes in the databags.

CI checks the schema of every interface against the format described here. To check as you work:

```bash
just interface-schemas              # every interface
just interface-schemas tls-certificates
```

```{note}
Only the latest version of each interface is checked. Older versions are kept for reference and are not held to this format.
```

## Name all four databags

A relation has four databags, and a schema must account for every one of them, using exactly these names:

| Name | Databag |
|------|---------|
| `ProviderAppData` | The provider's application databag. |
| `ProviderUnitData` | The provider's unit databag. |
| `RequirerAppData` | The requirer's application databag. |
| `RequirerUnitData` | The requirer's unit databag. |

Most interfaces only use one or two of them. Set the rest to `None`, which says the databag is always empty:

```py
ProviderAppData = TracingProviderData
ProviderUnitData = None
RequirerAppData = TracingRequirerData
RequirerUnitData = None
```

Declaring all four, rather than letting an absent name mean "empty", means an empty databag is a decision someone made and a reviewer can see — and it means a misspelled name is an error rather than a silently empty databag.

Keep the four together in this order at the end of the module, so the whole wire format can be read at a glance. If a model already has one of the four names, it is the declaration and needs no entry in the block.

Each model that isn't `None` must be a [Pydantic](https://docs.pydantic.dev/) `BaseModel` subclass or a standard library dataclass, because those are the two shapes [`ops.Relation.load`](https://canonical.com/juju/docs/ops/latest/reference/ops-module/#ops.Relation.load) and `ops.Relation.save` accept. Field names must match the keys in the databag, or carry an alias that does:

```py
from pydantic import BaseModel, Field, Json


class Receiver(BaseModel):
    """A single endpoint the provider is listening on."""

    protocol: str
    url: str


class ProviderAppData(BaseModel):
    """The provider's application databag."""

    receivers: Json[list[Receiver]] | None = Field(
        default=None,
        description='Endpoints the provider accepts traces on.',
        examples=[[{'protocol': 'otlp_http', 'url': 'http://tempo:4318'}]],
    )
```

Charms then read and write the databag with the model directly:

```py
data = event.relation.load(ProviderAppData, event.app)
```

```{important}
Don't annotate a field with `pydantic.Json`. `Relation.load` decodes each databag value before
handing it to the model, and `Relation.save` encodes what the model gives back, so a `Json` field
is decoded twice: it receives an already-decoded value and rejects it, and it can't be constructed
from a real value in order to be saved. Annotate the decoded type instead — `list[Receiver]`, not
`Json[list[Receiver]]`. CI rejects `Json` annotations.
```

Fill in `description` and `examples` on each field. They are the source for what gets rendered in the interface's reference documentation, and they are the only explanation a charm author gets when reading the schema on its own.

Follow {ref}`design-relation-interfaces` when deciding what the fields should be — no mandatory top-level fields, no field reuse, stable collection ordering, and so on. Those rules are about the wire format itself; this guide is only about how to express it.

## Say how the values are encoded, if it isn't JSON

`ops` encodes each databag value as JSON, and most interfaces are happy with that: `Relation.load`
runs `json.loads` over every value and `Relation.save` runs `json.dumps`. If that describes your
interface, there is nothing to do.

Some interfaces put bare strings in the databag instead — most of the data-platform family does,
because `charms.data_platform_libs.data_interfaces` writes them that way. `json.loads` raises on
`10.73.32.13:2379`, and `json.dumps` would write it back wrapped in quotes. Those interfaces say so
by giving their models a `__juju_decoder__`/`__juju_encoder__` pair. With more than one model, put
it on a shared base class; with one model, define the two methods on the model itself:

```py
class _BareStringDatabag(BaseModel):
    """Base class for databag models that don't strictly JSON encode all entries."""

    @staticmethod
    def __juju_decoder__(value: str) -> str:
        """Pass Juju's string through unmodified to be decoded by individual field validators."""
        return value

    @staticmethod
    def __juju_encoder__(value: str | None) -> str:
        """Convert `None` to "", erasing the value; Ops will error on a non-string."""
        return '' if value is None else value
```

Define both or neither — a codec describes both directions. `ops` does not read these names yet, so
charms and libraries pass them explicitly:

```py
data = event.relation.load(ProviderAppData, event.app, decoder=ProviderAppData.__juju_decoder__)
relation.save(data, self.app, encoder=ProviderAppData.__juju_encoder__)
```

They are `staticmethod`s rather than properties because `Relation.load` is handed the class, not an
instance, so the codec has to be reachable from the class.

### Then let each field decode itself

Passing values through unchanged is what makes a databag that mixes encodings work: each value
reaches the model as the string Juju is holding, so a field that really does carry encoded JSON can
say so while its neighbours stay plain.

```py
class ProviderAppData(_BareStringDatabag):
    """The provider's application databag."""

    model_config = ConfigDict(strict=True, populate_by_name=True)

    endpoints: str | None = Field(default=None, description='A bare string.')
    requested_secrets: list[str] | None = Field(
        default=None, alias='requested-secrets', description='A JSON array on the wire.'
    )

    @field_validator('requested_secrets', mode='before')
    @classmethod
    def _load_json(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value  # __init__ argument was already deserialized.
        return json.loads(value)

    @field_serializer('requested_secrets')
    def _dump_json(self, value: object) -> str | None:
        if value is None:
            return None
        return json.dumps(value)
```

Both halves are needed. The validator handles loading; without the serializer, saving hands `ops` a
list and raises `RelationDataTypeError`. The validator passes non-strings through so that a charm
can build the model from real values in order to save it — that is the flaw `pydantic.Json` has.

`ConfigDict(strict=True, ...)` matters more than it looks. Without it Pydantic quietly coerces, so
an `int` field turns `'06379'` into `6379` and writes back `'6379'`, and a `bool` field turns
`'True'` into `True` and writes back `'true'`. Type a field `str` unless the wire genuinely holds
something structured, and give enum fields `Field(strict=False)` so they still accept their own wire
string. `populate_by_name=True` is what lets a charm write `secret_tls=...` rather than the
hyphenated alias, which is not a valid Python keyword.

Two types to avoid in a databag model: `pydantic.SecretStr` serializes as `'**********'`, so it
needs a serializer returning `value.get_secret_value()` or the mask goes on the wire; and
`pathlib.Path` normalises away a trailing slash, so store a validated `str` instead.

## Depend on Pydantic and the standard library only

A schema is imported with Pydantic and the standard library available, and nothing else. Keeping it that way is what lets the schema be read on its own, by tooling and by people, and lets a library adopt it as its own databag models without dragging in test dependencies.

In particular, schemas must not import `interface_tester`. Earlier schemas wrapped their models in `ProviderSchema` and `RequirerSchema` classes inheriting from `pytest-interface-tester`'s `DataBagSchema`. That format is retired, and CI rejects both names.

If a model you already have is named something else, alias it in the block rather than renaming it — especially when the existing name is part of a library's public API.

(interface-schema-in-library)=
## Share the schema with the library

When an interface has a library in this repo, the schema and the library's databag models describe the same wire format, and keeping two copies in step is a job nobody wants. Instead, put the models in the library as `_schema.py` and symlink the interface's `schema.py` at it:

```text
interfaces/<interface>/
├── interface/
│   └── v<N>/
│       └── schema.py -> ../../src/charmlibs/interfaces/<interface>/_schema.py
└── src/charmlibs/interfaces/<interface>/
    ├── _schema.py            # the models, and the source of truth
    └── _<interface>.py       # the library, importing from ._schema
```

```bash
cd interfaces/<interface>/interface/v<N>
ln -s ../../src/charmlibs/interfaces/<interface>/_schema.py schema.py
```

The module keeps its underscore prefix because the models are not usually part of the library's public API — charm authors use the library's classes, not its databag models. Export them only if charm authors have a reason to construct them.

This arrangement is recommended but optional. An interface with no library in this repo just keeps its models in `schema.py`, and an existing library can adopt the symlink whenever it suits its maintainers.

```{seealso}
{ref}`design-relation-interfaces`
```
