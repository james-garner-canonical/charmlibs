---
myst:
  html_meta:
    description: Write the schema that describes an interface's relation data, and share it with the interface library that implements it.
---

(how-to-write-an-interface-schema)=
# How to write an interface schema

Every interface definition should be accompanied by a `schema.py`, which describes how the serialized relation data on the wire is transformed into meaningful objects.
This document explains how to format the schema.
To learn how to design the relation data format, read  {ref}`design-relation-interfaces`.

## Name all four databags

A relation has four databags, and a schema must account for every one of them, using exactly these names:

| Name | Databag |
|------|---------|
| `ProviderAppData` | The provider's application databag. |
| `ProviderUnitData` | The provider's unit databag. |
| `RequirerAppData` | The requirer's application databag. |
| `RequirerUnitData` | The requirer's unit databag. |

Any that aren't used by a specific interface must be explicitly set to `None`, like this:

```py
class ProviderAppData:
    ....

ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
```

Each model that isn't `None` must be a class that can be passed to [`ops.Relation.load`](https://canonical.com/juju/docs/ops/latest/reference/ops-module/#ops.Relation.load) and successfully load all permitted relation data for this interface.
It's common to use a [Pydantic](https://docs.pydantic.dev/) `BaseModel` subclass, but a standard library dataclass works if you want to avoid the dependency.

```py
import pydantic


class Receiver(pydantic.BaseModel):
    """A single endpoint the provider is listening on."""

    protocol: str
    url: str


class ProviderAppData(pydantic.BaseModel):
    """The provider's application databag."""

    receivers: list[Receiver] | None = pydantic.Field(
        default=None,
        description='Endpoints the provider accepts traces on.',
        examples=[[{'protocol': 'otlp_http', 'url': 'http://tempo:4318'}]],
    )
```

The `ProviderAppData` class can then be used to deserialize the relation data:

```py
data = event.relation.load(ProviderAppData, event.app)
```

Fill in `description` and `examples` on each field. They are the source for what gets rendered in the interface's reference documentation.

## Say how the values are encoded, if it isn't JSON

`ops` decodes each databag value as JSON by default.
If that describes your interface, you don't need to do anything extra here.
If you use a different format, for example writing strings as bare (rather than JSON-encoded) strings, you'll need to define custom encode and decoder functions.

If you define them as `__juju_encoder__` and `__juju_decoder__` on the databag model, then Charmlibs CI will automatically pass them through to `Relation.load` when validating the schema, like this:

```py
data = event.relation.load(ProviderAppData, event.app, decoder=ProviderAppData.__juju_decoder__)
relation.save(data, self.app, encoder=ProviderAppData.__juju_encoder__)
```

If all four databags use the same encoder and decoder, you can reduce repetition by defining them on a common base class.
For example, this base class defines a decoder that passes the databag value through unmodified, because its values are string which it 'encodes' by passing them through unmodified as well (setting `''` for `None`, which erases the value from the databag).

```py
class _BareStringDatabag:
    @staticmethod
    def __juju_decoder__(value: str) -> str:
        """Pass Juju's string through unmodified to be decoded by individual field validators."""
        return value

    @staticmethod
    def __juju_encoder__(value: str | None) -> str:
        """Convert `None` to "", erasing the value; Ops will error on a non-string."""
        return '' if value is None else value
```

### Databags with mixed encodings

Some databags have mixed encodings, for example using JSON encoding for lists and objects, but writing strings without encoding.
This can be handled today using Pydantic's `field_validator` and `field_serializer` decorators to determine per-field behaviour.
Decorated methods are called automatically for the appropriate fields when Ops creates or serializes a Pydantic model.

```py
class ProviderAppData(_BareStringDatabag, pydantic.BaseModel):
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

`ConfigDict(strict=True, ...)` matters more than it looks.
Without it Pydantic quietly coerces, so
an `int` field turns `'06379'` into `6379` and writes back `'6379'`, and a `bool` field turns
`'True'` into `True` and writes back `'true'`. Type a field `str` unless the wire genuinely holds
something structured, and give enum fields `Field(strict=False)` so they still accept their own wire
string. `populate_by_name=True` is what lets a charm write `secret_tls=...` rather than the
hyphenated alias, which is not a valid Python keyword.

Two types to avoid in a databag model: `pydantic.SecretStr` serializes as `'**********'`, so it
needs a serializer returning `value.get_secret_value()` or the mask goes on the wire; and
`pathlib.Path` normalises away a trailing slash -- if that's important store a validated `str` instead.

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

## Validate your work

CI checks the schema of every interface against the format described here. To check as you work:

```bash
just interface-schemas                   # Check all interfaces.
just interface-schemas tls-certificates  # Check named interfaces.
```

```{note}
Only the latest version of each interface is checked. Older versions are kept for reference and are not held to this format.
```
