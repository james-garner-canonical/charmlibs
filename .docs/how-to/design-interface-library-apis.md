---
myst:
  html_meta:
    description: Design the charm-facing API of an interface library, so that charms can reconcile relation data instead of observing library events.
---

(design-interface-library-apis)=
# How to design an interface library API
% Based on: OP083 - Relation Interface Design

An interface library has two designs in it, and they are not the same design.

The first is the **relation data format**: the JSON that goes on the wire, which outlives every
charm revision that reads it. Rules for that are in {ref}`design-relation-interfaces`.

The second is the **charm-facing Python API**: the classes, methods and properties that charm
authors import. That is what this guide is about. It is easier to change than the wire format, but
it is what charmers actually experience, and today it varies so much between libraries that no two
of them can be learned once.

This guide recommends **reconciler-only** libraries: a typed accessor over relation data, with no
events of its own, where the charm decides when to read and when to write.

```{admonition} Which page covers what
:class: seealso
This page owns the charm-facing API: the readiness and no-raise guarantees, the constructor, the
method shapes and their names, and the tests that demonstrate conformance to them.

{ref}`design-relation-interfaces` owns the wire format, and also owns **interface upgrades** — what
may change in a published interface, and the rule that unit tests must run against both old and new
test vectors. Those rules are not restated here.
```

```{note}
This guide applies to **new interface libraries and new major versions** of existing ones. It is not
a declaration that shipped libraries must be rewritten. See [Scope](#scope).
```

## Why reconciler-only

Start with what charms actually do with the events that libraries emit today.

Across 750 charms mirrored from Charmhub, with 845 observations of a library-emitted event:

| What the handler does with the event object | Observations | Share |
| --- | --- | --- |
| Ignores it entirely | 348 | 41% |
| Only calls `.defer()`, or passes it straight on | 251 | 30% |
| Only reads Juju context (`relation`, `app`, `unit`) | 26 | 3% |
| **Reads a payload attribute from it** | **220** | **26%** |
| **Never reads the payload** | **625** | **74%** |

**74% of handlers never read the payload.** For three quarters of its uses, a custom event
communicates exactly one bit: *something changed*. The handler then goes and asks the library what
the data is — which it could have done from any handler it already had.

Two more figures point the same way:

- **69% of charms observe no library event at all** (515 of 748). The delta API is not the common
  case even among charms that use these libraries.
- **23 distinct Charmhub libraries expose a `refresh_event` or `refresh_events` constructor
  parameter** — among them `prometheus_scrape`, `loki_push_api`, `cos_agent`, `grafana_source`,
  `cert_handler` and `tls_certificates` v4.

That last one is the argument in miniature. `refresh_event` exists only because the library owns
the timing of its writes, and the charm needs a way to say *"…and republish then, too."* It is a
parameter whose entire purpose is to hand a piece of the timing back. Under reconciler-only there is
nothing to hand back: the charm calls `publish()` from its own handler, whenever it likes, and the
parameter does not exist.

`refresh_event` is the polite form of the problem. Two harsher ones turn up in the same corpus:

- **The library observes a charm lifecycle hook without asking.** `tls_certificates` v4's provider
  does `self.framework.observe(charm.on.update_status, self._configure)` in its constructor, and
  `_configure` revokes certificates and republishes capabilities. The charm cannot opt out, cannot
  order it against its own reconcile, and cannot see it by reading its own source.
- **The library takes a callback instead of a value.** `tls_certificates` v4's `certificate_requests`
  may be a `Callable`, because — in its own docstring's words — the request set "depends on relation
  data ... that isn't readable at construction time". So the library calls back into the charm, at
  times the charm does not choose, and a hand-written comment in the renewal path exists solely to
  remind the next reader that this code path also has to re-resolve it.

All three are the same bug: the constructor is the wrong place to hand a library something that is
only knowable inside a hook. Pass it to the method instead. **If a constructor argument is a
callable, an event, or a list of events, it is nearly always a method argument in disguise.**

There is a correctness argument alongside the ergonomic one. `.defer()` is called on a custom event
111 times in the corpus. Deferring a re-emitted event defers a *snapshot* of data that has since
moved on, and re-emits it in a later hook where it may be stale or wrong. A reconciler cannot have
this bug, because it reads the databag now rather than replaying what the databag said earlier.

```{tip}
If you have shipped an event-based library, none of this is a claim that it was a mistake. It is a
claim about what the accumulated evidence now shows, which nobody could see at the time.
```

(scope)=
## Scope

Apply this guide to:

- **new interface libraries**, and
- **new major versions** of existing interface libraries.

Do **not** read it as a requirement to rewrite a shipped library. A library that emits events is not
non-conformant; the events are simply not what a new library should reach for. Where a rule below is
marked MUST, that MUST comes from OP083 and applies to the API you are designing now, not
retroactively to APIs already published.

### What a major version costs, and what it does not

Be honest with yourself about the size of the change before you start.

Renaming is cheap: `<Name>Requires` to `<Name>Requirer` is a find-and-replace in each consumer, and
you can keep an alias for a deprecation window. **Deleting the event classes is not cheap, and there
is no alias for it.** Consumers import them for handler type annotations:

```python
def _on_openfga_store_created(self, event: OpenFGAStoreCreateEvent) -> None:
```

A class that no longer has a reason to exist cannot be forwarded. For `openfga` that is a hard break
for 7 of its 8 consumers, landing in the same bump as the rename. That is what a major version is
for — but plan the communication, not just the code.

```{admonition} Migrated libraries
:class: seealso
Most of `interfaces/` is a port of a Charmhub-hosted library that deliberately kept the old names so
that migration was a find-and-replace. **Treat a port as a port**: the rules here bind at its next
major version, not at the moment it lands in this repo. Changing the API and the distribution
mechanism in one step gives consumers two problems to debug at once.
```

Two conventions in this page:

- **MUST** marks a rule that OP083 states as a requirement. These are the ones that become
  gates in review.
- **SHOULD** marks a recommendation — from OP083's own weaker wording, or from consistency across
  this repo. Deviate when you have a reason, and say what it is.

"Reconciler only" is a SHOULD.

## Don't subclass `ops.Object`

**SHOULD.** A reconciler-only library has no reason to be an `ops.Object`, and being one costs
something.

`ops.Object` exists to give you two things: `self.on`, for emitting and observing events, and
participation in the framework's object tree so that `StoredState` and deferral can find you again.
A reconciler-only library uses neither. What it gets in exchange is not free:

```python
# ops/framework.py
class Object:
    def __init__(self, parent: Framework | Object, key: str | None):
        ...
        self.framework._track(self)

    @property
    def model(self) -> Model:
        return self.framework.model
```

- You **cannot construct** an `ops.Object` without a `Framework` or another `Object`. "Be an Object
  and use `self.model`" still means the charm hands you the framework — the wide argument you were
  trying to avoid taking.
- `Object.model` is literally `self.framework.model`. It is not access you could not have had by
  taking `ops.Model` directly.
- `__init__` calls `framework._track(self)`, registering your object under a handle keyed by the
  string you pass. You inherit handle-uniqueness constraints for a feature you do not use — two
  instances of your class constructed with the same key in one charm is now an error.

So write a plain class:

```python
class FooRequirer:
    """Requirer side of the foo interface."""

    def __init__(self, model: ops.Model, relation_name: str = 'foo') -> None:
        self._model = model
        self._relation_name = relation_name
```

In this repo, 25 of 30 endpoint classes are `ops.Object` and only 5 are not: both halves of
`istio_metadata`, both halves of `otlp`, and `k8s_backup_target`'s requirer. Several of the 25
inherit it through a library-internal base class — `AuthProxyRelation`, `ForwardAuthRelation`,
`OAuthRelation`, `_LdapInterface` — which is to say their authors did not necessarily choose it.

That is the status quo, not a precedent. `istio_metadata` and `otlp` are the ones to copy.

## Take the narrowest thing you need

**SHOULD.** Take `ops.Model`.

That is the recommendation, and the rest of this section is why — because "just take the charm" is
what almost every library does today, and the reasoning is what makes `ops.Model` a considered
choice rather than a different arbitrary one.

### What libraries actually need

Scanning what the 15 interface libraries in this repo really touch, and then the 170 distinct
Charmhub libraries that define an endpoint class:

| Need | In this repo | On Charmhub | Narrowest thing that provides it |
| --- | --- | --- | --- |
| Read remote databags | 15/15 (100%) | 130/170 (76%) | `ops.RelationMapping` |
| Write own databag, or call `is_leader()` | 15/15 (100%) | 164/170 (96%) | plus `ops.Application` / `ops.Unit` |
| Juju secrets | 4/15 (27%) | 30/170 (18%) | `ops.Model` — `get_secret` is Model-only |
| `charm.meta` | 1/15 (7%) | 22/170 (13%) | `ops.CharmBase` |

Which resolves to a narrowest sufficient constructor argument per library:

| Argument | In this repo | On Charmhub |
| --- | --- | --- |
| `ops.RelationMapping` + `ops.Application`/`ops.Unit` | 10 (67%) | 113 (66%) |
| `ops.Model` | 4 (27%) | 29 (17%) |
| `ops.CharmBase` | 1 (7%) | 22 (13%) |
| `ops.RelationMapping` alone | 0 | 1 (0.6%) |

Two readings fall out of this, and they pull in opposite directions.

`ops.CharmBase` — which **29 of 30** endpoint classes in this repo take as their first argument — is
almost never actually required. It is required only for `charm.meta`, and `charm.meta` is a symptom
rather than a need: of the 22 Charmhub libraries that touch it, **all 22 also observe events**, and
twelve of them also carry a `refresh_event` parameter. They are overwhelmingly aggregating libraries
that own their write timing. Not one reconciler-style library in the corpus needs `charm.meta`. The
rung that would require the charm object disappears along with the events.

`ops.RelationMapping` alone, meanwhile, is sufficient for **one library in 170**. Almost everything
writes its own databag or calls `is_leader()` at some point, usually because the provider half
shares a module with the requirer half.

### Why `ops.Model` and not something tighter

The tempting move is to start at the tightest rung — take `RelationMapping`, widen later if you need
more. **That does not work, and the reason is structural.** `ops.RelationMapping` is a dead end: its
public API is `get`/`items`/`keys`/`values`, and it holds no back-reference to the model.

```python
ops.RelationMapping.__init__(self, relations_meta, our_unit, backend, cache, broken_relation_id, ...)
```

A library that starts with `RelationMapping` and later needs a Juju secret cannot reach one. It has
to add a parameter, which every existing caller must then pass. That is source-compatible only in
the weak sense that old call sites still construct — while the new feature silently cannot work.
Starting narrow is a one-way door.

`ops.Model` has neither problem. It covers every rung a reconciler-only library actually uses —
relations, the local app and unit, secrets — so widening is never needed, and the only rung it
misses is the one no reconciler library wants. And it is one argument rather than two or three.

```python
# In the library
class FooRequirer:
    def __init__(self, model: ops.Model, relation_name: str = 'foo') -> None: ...


# In the charm
self.foo = FooRequirer(self.model)
```

### If you think you need the charm

Name the value you actually need, and take that instead.

The one library in this repo that touches `charm.meta` is `otlp`, and its entire use of the charm
object is:

```python
is_subordinate=charm.meta.subordinate,
```

That is a boolean. A boolean the charm knows, and can pass:

```python
# Instead of taking the charm to read one field off its metadata
def __init__(self, model: ops.Model, *, is_subordinate: bool = False) -> None: ...
```

The test is not "could I get this from the charm?" — you can get anything from the charm. It is
"what is the value, and can the charm hand me the value?"

### Don't take payload in the constructor

There is a second question after "can the charm hand me the value?", and it is *what is the value
for?*

- A value that parameterises how the library **reads** — which protocols to accept, whether this
  charm is subordinate — belongs in the constructor. It is part of what the object *is*. `otlp`'s
  `protocols` and `telemetries` are the good case.
- A value the library will **write to a databag** belongs in the publishing method, not in
  `__init__`.

Storing payload on the instance means the library has to decide when to write it — the timing
ownership this page exists to remove — and it reintroduces `refresh_event` under a new name.
`oauth`'s requirer takes `client_config` in its constructor, writes it from its own
`relation_created` handler, and then has to expose `update_client_config()` so the charm can force a
rewrite. **That pair is `refresh_event` with the halves swapped**, and both collapse into a single
`publish(config)`.

(mode-switch-in-constructor)=
### Don't put a mode switch in the constructor

A constructor argument that changes what *other methods mean* — rather than what they operate on —
is two classes wearing one name.

`tls_certificates` v4's `private_key` parameter is the case to study. Supplying it makes
`regenerate_private_key()` raise, makes `get_private_key_secret_id()` return `None`, and makes the
reconcile path start *deleting* the secrets it would otherwise create. None of that is discoverable
from the signature.

The test: **if the docstring of method B has to mention constructor argument A, then A is a mode
switch.** Prefer two classes, or move the choice to the call site — `sync(requests,
private_key=key)` — where the reader can see which behaviour they are getting.

## The methods

A reconciler-only endpoint class is small, and nothing in it schedules anything.

**Do not assume the requirer reads and the provider writes.** That describes only broadcast-metadata
interfaces. In a request/response interface the **requirer publishes the request and the provider
reads it** — and the page's own examples of "the event looks load-bearing" (`database_created`,
`openfga_store_created`, `certificate_creation_request`) are all of that second kind. Both sides
have the same four operations available; which ones a side needs depends on the interface's shape.

| Interface shape | Requirer | Provider |
| --- | --- | --- |
| Broadcast metadata — the provider publishes, the requirer consumes | `is_ready`, `get_data()` | `publish()` |
| Request/response — the requirer asks, the provider answers | `is_ready`, `get_data()`, `publish(request)` | `is_ready(relation)`, `get_requests()`, `publish(relation, response)` |

The full menu, with the strength of each:

| Method | Strength | When |
| --- | --- | --- |
| `is_ready` | **MUST** (OP083) | on whichever side consumes data it did not write |
| `get_data()` | SHOULD | whenever anything is read |
| `publish()` | SHOULD | whenever anything is written |
| a way to report *why* it is not ready | SHOULD | see [Report why it isn't ready](#report-why-it-isnt-ready) |
| `get_published(relation)` or `get_outstanding_requests()` | SHOULD | request/response providers — see [Request and response](#request-and-response-without-events) |
| `clean_up(relation)` | SHOULD | **if** the library creates anything outside the databag — see [Libraries that do real work](#libraries-that-do-real-work) |
| an explicitly named charm-initiated mutation | SHOULD | `regenerate_private_key()`, `renew(certificate)`. Name the verb; never `do_*` or `handle_*` |

Only `is_ready` is required. The rest are conventions, and this page recommends them because naming
them consistently is worth more than any individual name is.

(is-ready-must)=
### `is_ready` (MUST)

OP083 requires that a charm library "must provide an API that quickly determines if the endpoint is
'ready' for a particular purpose". The **contract** is fixed:

- free of side effects,
- **must not raise on relation data**, and
- returns `False` when the endpoint is not usable for its purpose: the relevant databag is empty,
  could not be parsed, or the library judges the data logically not ready.

```{note}
**The emphasis is on *usable*, not on *empty*.** If your interface has a state where the remote
legitimately publishes nothing and the endpoint still works — a backwards-compatibility default, an
all-optional request — then an empty databag is not "not ready", and `is_ready` should say `True`.
Taking "empty means `False`" literally is how you end up with a method whose docstring has to warn
the reader not to trust it. Decide which your interface is, and say so in the docstring.
```

The **shape** is deliberately not fixed. OP083 lists five sanctioned forms, and picking one of the
others keeps you conformant:

- simple requirer: an `.is_ready` property
- app provider: `.is_ready(relation: ops.Relation)`
- per-unit provider: `.is_ready(relation, remote_unit)`
- one attribute per function: `.is_upstream_ready`, `.is_direct_ready`
- one attribute per state: `.is_request_ready`, `.is_acknowledgement_ready`

This guide's examples use the first two — a property on a `limit: 1` requirer, a method taking the
relation on a provider — and recommend them as the default. See
[One relation or many](#one-relation-or-many).

```python
@property
def is_ready(self) -> bool:
    """Whether the provider has published data this library can use.

    Never raises, and has no side effects.
    """
    return self._load() is not None
```

**Don't over-engineer a cache for it — for databags.**

1. *Won't `is_ready` followed by `get_data()` cost two `relation-get` calls?* No.
   `ops.RelationDataContent` extends `LazyMapping`: it is not populated until accessed, `_load()`
   runs once, and the result is cached until explicitly invalidated. Reading the same databag twice
   in one hook is one hook tool call.
2. *Won't it parse twice?* Only if you let it. Relation data cannot change within a single Juju
   event, so caching the parsed model on the instance is sound if you measure a reason to. Absent
   that reason, a second `model_validate` is cheap.
3. *Does this extend to Juju secrets?* **No, and this is the trap.** `ops.Model.get_secret` issues a
   `secret-get` on every call and returns a fresh `Secret`; nothing is memoised on the model. So an
   `is_ready` that probes a secret and a getter that reads it are **two** hook tool calls, and a
   status accessor on the sad path makes three. If your `is_ready` touches a secret, caching the
   `Secret` on the instance for the duration of the hook is worth doing.

`is_ready` is also allowed to assert things the databag does not describe — that a secret it points
at is actually readable, say, or that a field's value is one this version of the library supports.
That is the "logically not ready" case, and it is why `is_ready` is not simply "is the databag
non-empty".

```{warning}
**Read secrets with `Secret.peek_content()`, never `Secret.get_content(refresh=True)`.** `refresh`
tells Juju to update the tracked revision — a side effect, which the MUST forbids, and one with hook
consequences: it is what makes Juju emit `secret-remove` for the superseded revision.
`get_content(refresh=False)` has no side effect but can return stale content after a rotation.
`peek_content()` reads the latest revision and changes nothing, which is exactly what a probe wants.
```

Two more things `is_ready` must survive:

- **`ops.TooManyRelatedAppsError`.** `model.get_relation(name)` raises it when a second application
  is related on an endpoint your library assumes is `limit: 1`. You cannot enforce `limit: 1` from a
  library — it lives in the charm's `charmcraft.yaml` — so catch it. See
  [One relation or many](#one-relation-or-many) for what to do next, because returning `False` here
  is a lie the charm needs help decoding.
- **Meaning "the work is done", not "the remote published", for a library that does work.** If your
  library generates a key and submits a request before anything is usable, `is_ready` is `False` on a
  fresh unit until the charm has called `sync()` at least once. That is correct, and worth saying in
  the docstring.

Worked test, adapted from OP083:

```python
# The charm under test
class MyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.foo = FooRequirer(self.model)


# The test
def test_is_ready_with_good_data():
    ctx = ops.testing.Context(MyCharm, meta=META)
    data = {'good': '"value"', 'some-future-thing': '"sss"'}
    relation = ops.testing.Relation('foo', remote_app_data=data)
    state = ops.testing.State(relations={relation})
    with ctx(ctx.on.relation_changed(relation), state) as manager:
        manager.run()
        assert manager.charm.foo.is_ready
```

Note what the test does *not* need: no custom event, no `emitted_events`, no deferral. The library
is a function of the state, so the test is a function of the state.

### `get_data()` (SHOULD)

**Recommended default: a strict getter.** Return the parsed data, and raise when there is none.

```python
def get_data(self) -> FooData:
    """Return the provider's data.

    Raises:
        FooNotReadyError: if no usable data has been published. Check `is_ready` first,
            or catch this.
    """
    data = self._load()
    if data is None:
        raise FooNotReadyError(self.rich_status)
    return data


def _decode(value: str) -> Any:
    """Decode one databag value, leaving anything that is not JSON as a string."""
    try:
        return json.loads(value)
    except ValueError:
        return value  # not ours; the field filter will drop it


def _load(self) -> FooData | None:
    relation = self._relation
    if relation is None or relation.app is None or not relation.data.get(relation.app):
        # Check the raw databag before parsing. Because the wire format forbids
        # mandatory fields, an empty databag validates cleanly into an all-defaults
        # model -- so "nothing published yet" is only detectable before validation.
        return None
    try:
        return relation.load(FooData, relation.app, decoder=_decode)
    except (ValueError, TypeError) as e:
        # Catch ValueError, not pydantic.ValidationError. Relation.load JSON-decodes
        # the databag before pydantic sees it, so a value that is not JSON arrives as
        # json.JSONDecodeError. Both are ValueError subclasses; catching only the
        # pydantic one lets the other escape, and is_ready MUST NOT raise.
        logger.warning('Ignoring unparseable %s data: %s', self._relation_name, e)
        return None
```

`is_ready` is then `self._load() is not None`, and it is genuinely load-bearing: it is the safe
probe, the getter is the strict one, and they answer different questions. See
[The getter is allowed to be strict](#getter-allowed-to-be-strict).

**A total getter — `get_data() -> FooData | None` — is equally conformant**, and several libraries
in this repo use it. If you take that shape, be aware that `is_ready` collapses to
`get_data() is not None`, and that you then have *no* channel for telling a charm why the answer is
`None` except your status API. Read [One relation or many](#one-relation-or-many) before choosing.

Pick one shape per library and be consistent within it.

#### Parsing: `Relation.load` and the codec

`ops.Relation.load` and `ops.Relation.save` are the modern idioms, and `otlp` uses them in this repo:

```python
load(self, cls: type[_T], src: Unit | Application, *args, decoder=None, **kwargs) -> _T
save(self, obj: object, dst: Unit | Application, *, encoder=None) -> None
```

`cls` is your databag model class and `src`/`dst` is the `ops.Unit` or `ops.Application` whose
databag to read or write.

````{warning}
**They JSON-encode every field by default, and `load` decodes the whole databag before it filters
down to your model's fields.** So *one* value that is not JSON fails the entire load — even a key
your model would have ignored.

That is not an edge case. **Juju writes `egress-subnets`, `ingress-address` and `private-address`
into every unit databag as bare strings**, so `relation.load(FooData, some_unit)` with the default
decoder raises `json.JSONDecodeError` on every real relation. One of OP083's five sanctioned
`is_ready` shapes is a per-unit provider; written to the default idiom, it cannot read a single unit
databag. App databags hit the same wall as soon as anything else writes a non-JSON value into them.

Pass a tolerant decoder, and let the field filter drop what is not yours:

```python
relation.load(FooData, unit, decoder=_decode)  # _decode as defined above
```

The write side is worse because it is silent. `encoder` defaults to `json.dumps`, so adopting `save`
for an **existing** wire format whose fields are bare strings writes every value JSON-quoted and
breaks every deployed remote. Pass a matching encoder, and use the same pair on both sides:

```python
relation.save(data, self._model.app, encoder=lambda v: '' if v is None else str(v))
```
````

```{note}
`Relation.load` and `Relation.save` need **`ops>=3`**, and pydantic v2 for pydantic models. If your
library still supports pydantic v1, adopting them is a major-version change on its own.
```

Two more things about `save` that are easy to be surprised by:

- **It is a total write.** `save` writes every field of the model, erasing the ones the dump omits.
  Republishing a model that carries only some of the fields in a databag destroys the rest. See
  [Write granularity](#write-granularity).
- **Pydantic's `Field(exclude=True)` makes a field unwritable, not just unpublished.** `save` builds
  its field list from `model_fields` but its values from `model_dump()`, so an excluded field is
  written as an erase. If a wire field is legitimately optional-but-real, do not exclude it.

### `publish()` (SHOULD)

The provider writes. It does not decide when.

```python
def publish(self, data: FooData) -> None:
    """Publish data to every application related on this endpoint.

    Does nothing if this unit is not the leader, because this writes the
    application databag.
    """
    if not self._model.unit.is_leader():
        logger.debug('Not leader; skipping publish to %s', self._relation_name)
        return
    for relation in self._model.relations.get(self._relation_name, ()):
        relation.save(data, self._model.app)
```

Guard the leadership check inside the library. Charm authors forget it, ops raises when they do, and
the resulting error state is not informative. `gateway_metadata`, `istio_metadata` and `otlp` all
guard it this way already.

**Guard *application*-databag writes on leadership, not every write.** A library that writes the
**unit** databag must not skip it on a follower — every unit owns its own databag, and a per-unit
provider that leader-guards its writes publishes nothing at all from its followers.

Note what is *not* in the constructor: no `refresh_event`, no `refresh_events`. The charm calls
`publish()` from whichever handler is right for it.

#### Take the whole payload, not a delta

`publish(data)` is not merely tidier than `add_*()` / `remove_*()`. It removes a class of bug:
incremental methods have to read back what they previously wrote, which makes the databag the source
of truth for the provider's own intent — and anything that touches the databag can corrupt it. A
declarative `publish()` is a function of what the charm knows right now.

```{warning}
**`Relation.save` updates the databag; it does not replace it.** It writes the fields your model
carries and leaves every other key alone. So a declarative `publish()` of an empty or shrunken
payload does *not* remove the keys that are no longer part of it — you have to clear them yourself,
and setting a key to `''` is how Juju deletes it. `certificate_transfer` has a live bug of exactly
this shape today: `remove_all_certificates()` on a legacy relation silently does nothing, and the
certificates stay on the wire. **Test the empty publish.**
```

#### Sort collections on the way out

`Relation.save` calls `model_dump(mode='json')`, and pydantic serialises a `set` or `frozenset` in
iteration order — which varies between processes. The same set produces a different databag string
on every publish, so every remote is woken by `relation-changed` for data that did not change. That
is precisely the spurious event {ref}`design-relation-interfaces` tells you to avoid, and it is a
live bug in a shipped library in this repo.

The two rules compose into a bug because they live on different pages: "model collections as sets"
plus "use `Relation.save`" equals an unstable wire order unless you add the serialiser.

```python
@pydantic.field_serializer('certificates')
def _serialize_certificates(self, certificates: frozenset[str]) -> list[str]:
    return sorted(certificates)
```

Test it by publishing the same set several times and asserting exactly one distinct databag value.
This is one of the few conformance properties a single run cannot detect.

(when-the-requirer-has-to-write-too)=
#### When the requirer has to write too

"The requirer reads, the provider writes" holds for most interfaces, but not all. If the requirer
publishes anything — a supported interface version, the protocols it accepts, a request — then it
needs a `publish*` method too, and reconciler-only makes that write the **charm's** responsibility
for the first time.

`certificate_transfer` is the sharp case. Its requirer must declare `version: 1`, or the provider
serves it the deprecated v0 format. The shipped library does that invisibly from its own
`relation_created` handler. Take the events away and a charm that forgets the call **still works** —
silently, on the worse path, with no error on either side.

So be loud about it:

- **Give it its own name** — `publish_version()`, `publish_request()` — not a bare `publish()`, so a
  reader can see what is being declared.
- **Say in the docstring which Juju event it needs to run on.** A library that emits no events cannot
  arrange its own timing, so the constraint has to be documented rather than implemented.
  `relation-created` is the usual answer for a handshake.
- **Put it in the usage example, inside the reconcile handler** — not in prose.
- **If forgetting it degrades silently, make the *other* side say so** in its `is_ready` or status
  API.

(publish-may-raise)=
#### `publish()` may raise on its arguments

The no-raise MUST covers initialisation and `is_ready`, and it exists to protect the charm from
**remote** data. Data the charm passed in is not remote data.

If the charm hands `publish()` a value this interface cannot represent, raise `ValueError`. The
charm is on the stack, at the call site, holding the value it got wrong — which is the best possible
place for that error to appear. This is the counterpart of
[the getter is allowed to be strict](#getter-allowed-to-be-strict).

It is also what retires error-carrying events. `oauth`'s `InvalidClientConfigEvent` reports a
config the *charm itself* supplied; it exists only because the library owned the write timing and so
had no charm frame to raise into. The tell is that the same `ClientConfigError`, from the same
internal method, propagates normally when the charm calls `update_client_config()` directly — one
error, two delivery mechanisms, chosen by code path. Give the write back to the charm and it is a
`ValueError` from `publish()`.

#### If `publish()` has side effects, make them idempotent

This page tells charms that `update-status` is a free retry. That is only true if `publish()` is
idempotent all the way down, including resources it creates outside the databag.

The trap is Juju secrets. **`ops.Application.add_secret` is not idempotent** — Juju rejects a second
`secret-add` with a label already in use, and ops surfaces that as an untyped `ModelError`. So do
not call `add_secret` from a method the charm may call on every hook. Create-or-update instead:

```python
try:
    secret = self._model.get_secret(label=label)
except ops.SecretNotFoundError:
    secret = self._model.app.add_secret(content, label=label)
    secret.grant(relation)
else:
    if secret.peek_content() != content:
        secret.set_content(content)  # a new revision, not a new secret
    secret.grant(relation)           # grant is idempotent
```

```{warning}
**A unit test cannot catch this.** `ops.testing` does not model Juju's duplicate-label rejection —
its `secret_add` adds a second `Secret` with the same label and does not raise. Assert on the number
of secrets in the resulting state instead, and cover the real behaviour in an integration test.
```

(one-relation-or-many)=
### One relation or many

OP083 already settles this for `is_ready`, by role. Mirror that split in the getter **and in the
status accessor** — a no-argument `rich_status` on a provider with N relations has nowhere to put
the answer.

| The endpoint is… | `is_ready` | Getter | Status |
| --- | --- | --- | --- |
| a requirer with `limit: 1` | `is_ready` property | `get_data()` | `rich_status` property |
| a requirer aggregating a collection | `is_ready(relation=None)` | `get_data() -> Collection` (merged), plus `get_data_by_relation() -> dict[int, Collection]` | `rich_status` property |
| an app provider | `is_ready(relation)` | `get_data(relation)` | `rich_status(relation)` |
| a per-unit provider | `is_ready(relation, remote_unit)` | `get_data(relation, remote_unit)` | `rich_status(relation, remote_unit)` |
| a requirer making several independent requests on one relation | `is_ready(request)` | `get_data(request)`, plus an aggregate if useful | `rich_status(request)` |
| a provider answering per request, where requests may arrive in the app *or* a unit databag | `is_ready(request)` | `get_requests() -> list[Request]` | `rich_status(request)` |

**When the endpoint aggregates a collection, the merge is the API.** If the charm's question is
"what is the whole set?" — a trust store, a list of endpoints to scrape — then the merged accessor is
primary and the per-relation view is the extra. Making the per-relation getter primary pushes the
union loop into every consumer, and with it the decision about what one bad relation does to the
result. That is a semantic decision, and it belongs in the library. `certificate_transfer` bears this
out: its primary read is the union, and the by-relation view was added later for the rare case.

Say in the docstring what happens when one relation's data is unusable. For a collection the answer
is almost always "it contributes nothing, and the rest still works" — a single broken provider must
not be able to empty the collection.

**Check the role assumption before you copy a row.** The first four rows assume you are keyed on the
relation, or the relation plus a remote unit. `tls-certificates` is keyed on neither: its requirer
makes several certificate requests on one `limit: 1` relation, satisfied at different times, so a
boolean property would have to answer for all of them at once; and its provider reads requests from
the remote app databag *and* every remote unit databag on the same relation, so it is an app
provider and a per-unit provider simultaneously.

**Ask what the smallest addressable unit of work is. If it is not a relation and not a remote unit,
make it a first-class object and key your API on that.** And where the address is a property of that
object, still pass it explicitly: `publish(request, result)` reads better than `publish(result)`
with the relation ID buried inside `result`.

**Whatever you choose, do not silently pick one relation out of several.**
`gateway_metadata` does `relations[0] if relations else None`, so a charm with two providers related
gets one of them, non-deterministically, with no way to notice. `istio_metadata` raises `ValueError`
instead, and documents the `limit: 1` expectation in its constructor docstring — that is the better
of the two. `tls-certificates` does the same thing by letting `model.get_relation()` raise
`TooManyRelatedAppsError`. Better still: take the relation as an argument the moment more than one
is possible.

```{important}
**`is_ready` cannot report "you related two providers to a `limit: 1` endpoint", because `is_ready`
may not raise.** It has to return `False` for a condition that is not a data condition at all — with
two perfectly valid databags in front of it.

If you took the strict getter, raise from the getter and let `is_ready` return `False`. If you took
the total getter, your status accessor is the *only* channel left, so it must name this case
explicitly:

    if len(relations) > 1:
        return f'{len(relations)} {self._relation_name} relations; expected at most one'

This is the strongest argument on the page for treating the status API as closer to a MUST than the
SHOULD that OP083 makes it.
```

(write-granularity)=
### Write granularity

`publish(data)` writing to every relation is the right default when the payload is the same for
every remote — metadata, endpoints, capabilities.

Take the relation, `publish(relation, data)`, when the payload is a **function of the remote**: a
certificate issued for one requirer's CSR, credentials minted for one consumer. Writing per-remote
data with an all-relations method is how a provider leaks one consumer's data to another.

The question to ask is not "how many relations do I have?" but "does what I write depend on who I am
writing to?".

**The question is about content, not encoding.** A provider that writes the same payload to everyone
but negotiates a *wire format* per remote — a legacy compatibility path, a capability the remote
declared — still has an all-relations `publish(data)`. The negotiation is the library's business, and
pushing it out into a per-relation loop in every consumer charm is the wrong trade.

`publish(data, *, relation: ops.Relation | None = None)` is a reasonable third shape when the payload
is normally the same for everyone but the charm occasionally needs to target one relation. Keep
`relation` keyword-only, so the common call stays `publish(data)`.

**Sometimes the answer is "both, in one databag".** A provider may write broadcast fields (server
URLs, capabilities) and per-remote fields (a minted credential, an allocated ID) into the same
application databag. `openfga` is one: `grpc_api_url`/`http_api_url` are identical for every remote,
while `store_id`/`token_secret_id` are minted per requirer.

Do **not** solve this with two `save()`-based methods. Because `Relation.save` writes every field of
the model you hand it, the broadcast write erases the per-remote fields — republishing new server
URLs writes `store_id` as the literal string `null`. Either:

- expose one per-relation `publish(relation, ...)` that takes the whole payload, and let the charm
  loop; or
- make the broadcast method a read-modify-write: load what you published on that relation, replace
  only the broadcast fields, save the merged model — noting that reading your own application
  databag [requires leadership](#request-and-response-without-events).

Whichever you pick, say in the docstring which fields the method owns.

(initialisation-and-is-ready-must-not-raise)=
## Initialisation and `is_ready` must not raise

**MUST.** OP083 states this twice, explicitly, and scopes it precisely:

> - charm object initialisation must not raise
> - charm object `.is_ready` must not raise

The reason is structural, not stylistic. A charm's `__init__` must complete for the charm to observe
*any* Juju event. A complex charm may construct a dozen library objects there. Your library's author
is not in a position to decide whether your library is critical to that charm or incidental to it —
so a malformed databag from a remote application must not be able to take the whole charm into
error.

Concretely:

- **Do not load relation databags at construction time.** If you do, catch everything
  `ops.Relation.load()` can raise.
- **Check the relation name in `__init__`, and let it raise there.** `model.relations[name]` raises
  `KeyError` for an endpoint the charm does not declare. That is a programming error, and the
  constructor is where it belongs — the no-raise MUST on initialisation is scoped to *databag
  contents*, so raising there is conformant, and it is what lets `is_ready` promise never to raise
  at all. Use `model.relations.get(name, ())` everywhere after that.
- **`is_ready` catches parse and validation errors** and returns `False`.
- **Exceptions are still right** for programming errors: a relation name that is not in the charm's
  metadata, a payload the charm passed to `publish()` that does not validate. Those are not remote
  data.

```{important}
"Must not raise" is scoped to **relation databag contents**, not to everything. OP083 is explicit
that exceptions "can and should be used to report incorrect initialization (e.g. wrong relation
name), or transient errors (hook command unexpectedly erroring out)". So an `ops.ModelError` from a
failing `relation-get` propagating out of `is_ready` is correct behaviour, not a violation — the
charm goes into error and Juju retries the hook. What must not escape is a `ValidationError` because
a remote application wrote something you did not expect.

Catch the exceptions the databag can cause. Do not wrap the body in a bare `except Exception`: that
converts a broken hook tool into a silent `False`, which is a much harder bug to find than an error
state.
```

```{admonition} Juju secrets are the exception to that exception
:class: warning
If `is_ready` reads a secret, it must catch `ops.SecretNotFoundError` and `ops.ModelError` and
return `False`. A `secret-get` that fails because a grant has not propagated yet is
indistinguishable, at the API, from one that fails because the secret was revoked — and `is_ready`
may not raise either way. Let the getter be the place where that failure surfaces if you want it to.

This is narrow. It applies to secret reads, not to databag reads, and it is not a licence for a bare
`except Exception`.
```

(getter-allowed-to-be-strict)=
### The getter is allowed to be strict — and that is the point

This is the most common objection to having both `is_ready` and a getter: *if the getter returns
`None` on bad data anyway, isn't `is_ready` just `get_data() is not None` with extra steps?*

The answer is that the no-raise guarantee is scoped to two places, and the getter is not one of
them. OP083's own advanced-status example has the getter raising and the charm catching:

```python
if not self.foo.is_ready:
    self.unit.status = ops.WaitingStatus(self.foo.rich_status)
try:
    host = self.foo.get_hostname()
    use(host)
except SomeException as e:
    self.unit.status = ops.BlockedStatus(str(e))
```

`is_ready` is the **safe probe** a charm can call unconditionally, anywhere, including inside
`__init__` while wiring one library object into another. The getter is where the library is allowed
to be strict about what it hands back. They are not two spellings of the same check.

So both shapes are conformant:

- **Strict getter** — `get_data() -> FooData`, raising on absent or unusable data. **Recommended
  default.** `is_ready` is then load-bearing rather than ceremony, the two methods answer genuinely
  different questions, and a charm that skips the probe gets an error state rather than a silent
  `None` it forgot to check. It is also the shape OP083's own example uses.
- **Total getter** — `get_data() -> FooData | None`. `is_ready` collapses to
  `get_data() is not None`. Legitimate, and common in this repo — but note that you have then given
  away the only channel for saying *why*, so your status API stops being optional in practice. See
  the note in [One relation or many](#one-relation-or-many).

Pick one per library and be consistent within it.

```{important}
**Two endpoints should not take the strict shape**, and for both the total getter is the better
answer:

- **A collection payload.** Return the empty collection, not `None`.
  {ref}`design-relation-interfaces` requires the empty databag to parse, so the parsed model cannot
  distinguish "absent" from "empty" anyway, and `set[str] | None` makes every call site write
  `or set()`. Note that `is_ready` is then `bool(self.get_data())`, **not**
  `self.get_data() is not None` — those are different one-liners, and a getter that returns an
  empty set would make the second one say `True` for an endpoint with nothing in it. Say which one
  your library uses.
- **An aggregating endpoint.** A getter that raises on one bad relation cannot return the other
  two. One broken provider must not be able to empty a charm's whole trust store.
```

### The live counter-example

`istio_metadata` in this repo is the case worth studying, because the MUST it misses is not the
obvious one.

```python
class IstioMetadataRequirer:
    def get_data(self) -> IstioMetadataAppData | None:
        relations = self.relations
        if len(relations) == 0:
            return None
        if len(relations) > 1:
            raise ValueError('Cannot get_info when more than one application is related.')
        ...
        return IstioMetadataAppData.model_validate(raw_data_dict)
```

- **`get_data()` raising is not, by itself, a violation.** Per the section above, the getter may be
  strict.
- **Providing no `.is_ready` at all is the violation.** There is no way for a charm to ask "is this
  usable?" without risking the exception — which is exactly the situation the MUST exists to prevent.
  A charm cannot safely probe this endpoint from `__init__`.

The fix is small: add the safe probe next to the strict getter.

```{note}
`istio_metadata` was written before this rule was written down anywhere charmers could read it.
Every counter-example on this page is here for the same reason. The point is the rule, not the
library.
```

Worked test for bad remote data, adapted from OP083:

```python
class MyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.foo = FooRequirer(self.model)
        assert not self.foo.is_ready


def test_bad_remote_data_does_not_raise():
    ctx = ops.testing.Context(MyCharm, meta=META)
    data = {'bad': '"data"', 'weird': '[{}, {}]'}
    relation = ops.testing.Relation('foo', remote_app_data=data)
    state = ops.testing.State(relations={relation})
    ctx.run(ctx.on.relation_changed(relation), state)  # must not raise
```

## Naming

**SHOULD.** There is no correct answer here, and that is why the rule matters: any consistent choice
beats the status quo.

Across the 30 endpoint classes in the 15 interface libraries in this repo:

| Dimension | Variants in use |
| --- | --- |
| Class name suffix | `Provider`=13, `Requirer`=11, `Requires`=3, `Provides`=2, `Consumer`=1 |
| Relation keyword argument | `relation_name`=24, `relationship_name`=4 |
| First constructor argument | `charm`=29, `relation_mapping`=1 |
| Base class | `ops.Object`=25, plain object=5 |
| Readiness API | none=21, `is_ready()`=4, `is_ready` property=3, `ready()`=1, `is_client_created()`=1 |

Beyond that there are roughly **ten different names for "read the remote data"** — `get_metadata`,
`get_data`, `get_backup_spec`, `get_store_info`, `get_provider_info`, `get_slos`, `get_config`,
`endpoints`, `get_all_certificates`, `get_assigned_certificates` — and roughly **fourteen for "write
my data"**, including `publish`, `publish_metadata`, `publish_data`, `provide_slos`, `submit_config`,
`update_relations_app_data`, `update_forward_auth_config` and `set_relation_certificate`.

A charmer who has learned one of these libraries has learned one of these libraries.

So:

| Thing | Use | Not |
| --- | --- | --- |
| Provider class | `<Name>Provider` | `<Name>Provides` |
| Requirer class | `<Name>Requirer` | `<Name>Requires`, `<Name>Consumer` |
| Relation argument | `relation_name` | `relationship_name` |
| Readiness | `is_ready`, or `is_<state>` per state | `ready()`, `check_ready()`, bare adjectives |
| Read | `get_*` | bare nouns, `fetch_*` |
| Write | `publish*` | `update_*`, `set_*`, `submit_*`, `provide_*` |
| Default endpoint constant | `DEFAULT_RELATION_NAME` | `DEFAULT_INTEGRATION_NAME` |

The readiness row is about **form**, not about the word "ready". The `is_` prefix and the boolean
predicate are the convention; the noun is yours. Where an endpoint has genuinely distinct readiness
states that different charms consume, "one attribute per state" is a
[sanctioned shape](#is-ready-must) and `is_client_created` alongside `is_ready` is the right answer,
not a naming violation. `oauth` is the real case: its provider metadata is usable by a charm acting
as an OAuth *resource server* long before any client is registered, so a single `is_ready` would
have to tell one of those two audiences something false. What is not negotiable is the contract —
boolean, no side effects, never raises.

Pick one acronym casing per library and apply it to the data models too. `openfga` exports both
`OpenFGARequires` and `OpenfgaProviderAppData`; neither is wrong, but having both is.

**Don't put a version number in the class name.** `tls-certificates` has
`TLSCertificatesRequiresV4` and `TLSCertificatesProvidesV4`; nothing else in this repo does this.
Note what the `4` is *not*: the interface is `tls-certificates` **v1**. The `4` was `LIBAPI` of the
Charmhub single-file library, and the Charmhub import path
(`charms.tls_certificates_interface.v4.tls_certificates`) already carried it — so the suffix was
redundant even then, and now it names a version that differs from the interface version printed
beside it.

There was one real constraint keeping it, and it is worth knowing because reconciler-only dissolves
it: `ops.Object.handle_kind` is the class name, so the class name is part of the handle path that
deferred notices are persisted under, across upgrades. Renaming an `ops.Object` that emits events
orphans deferred notices. **A plain class that emits nothing has no handle, and can be renamed
freely.**

### Generic or domain-specific method names

`get_data()` or `get_certificates()`? Both are fine, and the rule is about shape, not vocabulary:

- **When the endpoint exposes one payload, use `get_data()` and `publish()`.** The domain is already
  in the class name. `FooRequirer.get_data()` is not less clear than `FooRequirer.get_foo()`.
- **When the endpoint exposes several distinct things, name them** — `get_certificates()`,
  `get_ca()`. Keep the `get_` prefix and the `publish` verb.

What to avoid is a different verb per library for the same operation. `update_relations_app_data`
and `publish` do the same thing; only one of them can be guessed.

(report-why-it-isnt-ready)=
## Report why it isn't ready

**SHOULD.** OP083 says authors "are advised to provide" an API reporting advanced status, and
expressly declines to specify its shape, because the charming community has competing proposals in
flight.

This page does not close that question either. But leaving it entirely open is what pushes authors
back towards error-carrying events. So: **a recommended shape, not a required one.**

```{note}
Not every error-carrying event is a status-reporting gap. `oauth`'s `InvalidClientConfigEvent`
reports a config the *charm itself* passed in, and it exists only because the library owned the
write timing. That one is retired by
[`publish()` may raise on its arguments](#publish-may-raise), not by anything in
this section.
```

Recommended: a read-only property named `rich_status`, the name OP083's own example uses, returning
a human-readable explanation, or `None` when there is nothing to report — **plus a companion boolean
saying whether the reason needs a human**.

```{important}
**`rich_status` is not the negation of `is_ready`.** An endpoint that aggregates several relations
can be ready *and* have something to say: two providers working, a third publishing unusable data.
Returning `None` "because it is ready" throws away the only information the charm could have
surfaced. Let it speak, and let the charm decide whether that means blocked, waiting, or an active
message. For an aggregator the charm-side shape is *block if not ready, and warn if ready with a
status* — not the simple negation shown below.
```

```python
@property
def rich_status(self) -> str | None:
    """Why the endpoint is not usable, or None if there is nothing to report.

    Never raises, and has no side effects.
    """
    relations = self._model.relations.get(self._relation_name, ())
    if not relations:
        return f'no {self._relation_name} relation'
    if len(relations) > 1:
        return f'{len(relations)} {self._relation_name} relations; expected at most one'
    relation = relations[0]
    if relation.app is None or not relation.data.get(relation.app):
        return f'waiting for data on {self._relation_name}'
    try:
        relation.load(FooData, relation.app, decoder=_decode)
    except pydantic.ValidationError as e:
        # Report every problem, not just the first: an operator who fixes one field,
        # redeploys and waits only to learn about the next has been failed twice.
        return '; '.join(f'{".".join(str(p) for p in err["loc"])}: {err["msg"]}' for err in e.errors())
    except ValueError as e:
        return f'unparseable {self._relation_name} data: {e}'
    return None
```

```python
@property
def is_blocked(self) -> bool:
    """Whether the reason the endpoint is not ready needs someone to change something.

    False while the endpoint is merely waiting for an exchange to complete -- that will
    resolve on its own. True when a databag is malformed, a secret is unreadable, or the
    model is wired up in a way this endpoint cannot support.

    Never raises, and has no side effects.
    """
```

In the charm:

```python
if not self.foo.is_ready:
    cls = ops.BlockedStatus if self.foo.is_blocked else ops.WaitingStatus
    self.unit.status = cls(f'foo not ready: {self.foo.rich_status}')
    return
```

**Why the boolean earns its place.** Without it a charm cannot tell "the provider has not answered
yet" from "the provider's databag is malformed and someone must fix the other application" — the
strings are both non-empty and both prose. A charm following the obvious pattern hardcodes
`WaitingStatus`, so an endpoint blocked forever on an unreadable Juju secret sits in *waiting* and
never surfaces to an operator.

This is not the library choosing the status. **Severity is the charm's call and stays the charm's
call** — whether a broken `foo` blocks this charm, or merely degrades it, is something only the
charm knows. *Will this fix itself?* is a different question, and the library is the only thing that
can answer it.

Do not try to encode the distinction inside the string with a prefix convention. A charm that has to
`.startswith('blocked: ')` on your prose is coupled to your wording — the one part of the API this
section explicitly frames as human-readable and therefore free to change.

Two things this shape gets right, and they are the parts that are not negotiable:

- **The charm supplies the sentence, the library supplies the clause.** OP083 is explicit about the
  division:

  ```text
  Waiting(ingress not ready: FQDN is missing)
  charm  ^^^^^^^^^^^^^^^^^^
  library                    ^^^^^^^^^^^^^^^
  ```

  Never set the unit status from inside a library. The library does not know whether this endpoint
  being down means blocked, waiting or merely degraded for this charm.
- **It must not raise.** OP083 groups detailed status with `is_ready` when it says superficial API
  access must not raise on databag contents. A status accessor that raises while the charm is trying
  to explain an error is the worst possible time to raise.

The scope of this API is *logical validation failures*: not ready yet, unparseable databag, a
missing field that matters, a value out of range, a URL with a component the interface disallows.

**Report every problem you can see, not the first one.** Returning `e.errors()[0]['msg']` is the
easy thing and the wrong thing: an operator fixes one field, redeploys, waits, and learns about the
next. Pydantic hands you the whole list; use it, as the example above does.

```{admonition} Check that your wire format can express refusal
:class: caution
A status API can only report what the library can observe. If the provider can *reject* a request —
a `redirect_uri` its policy forbids, a certificate it will not issue — and the interface has no field
for saying so, then "rejected" and "not answered yet" are the same bytes on the wire. No accessor
can tell them apart, and the requirer waits forever.

That is a {ref}`relation data format <design-relation-interfaces>` decision, not a Python one, and it
has to be made **before** this API exists. `oauth` has this gap today.
```

**If your wire format already carries structured errors, surface them structurally.**
`tls-certificates` puts an error code enum on the wire; flattening that into a sentence throws away
the thing a charm might branch on — retry a transient code, block on a permanent one. Keep
`rich_status` as the human-readable summary *alongside* the structured accessor, not instead of it.

Worked test, adapted from OP083:

```python
def test_rich_status_explains_a_bad_field():
    ctx = ops.testing.Context(MyCharm, meta=META)
    relation = ops.testing.Relation('foo', remote_app_data={'host': '"fe80::1"'})
    state = ops.testing.State(relations={relation})
    state_out = ctx.run(ctx.on.relation_changed(relation), state)
    assert state_out.unit_status == ops.testing.BlockedStatus(
        'foo not ready: host must be a domain name'
    )
```

```{tip}
**Do not build the status string out of validator output.** The example above interpolates a
Pydantic message, which couples every consuming charm's tests to your library's Pydantic minor
version. Write the clauses yourself, from fields you control, and let the test assert a substring
rather than the whole sentence.
```

If `rich_status` and `is_blocked` do not fit your interface — you need one status per sub-function,
or machine-readable field names for an operator-facing action — deviate, and return a list of
structured issues instead. Name the type clearly and document it. Bear in mind the cost: a
per-library `Issue` type is exactly the fragmentation this page opens by complaining about, and it
only pays for itself once such a type lives somewhere shared. Until then, the pair above is the
recommendation because it needs no new type at all.

(request-and-response-without-events)=
## Request and response, without events

This is the objection that has to be answered, because it is the one case where the event genuinely
looks load-bearing. `database_created`, `openfga_store_created` and `certificate_creation_request`
all exist because the **provider** needs to know that a request arrived so it can act on it.

Under reconciler-only, the provider does not get told. It looks.

```python
class FooProvider:
    def get_outstanding_requests(self) -> dict[int, FooRequest]:
        """Requests this application has not yet answered, keyed by relation ID.

        Empty on a non-leader unit, which cannot read its own application databag.
        """
        ...
```

And the charm:

```python
def _reconcile(self, _: ops.EventBase) -> None:
    for relation_id, request in self.foo.get_outstanding_requests().items():
        result = self._provision(request)
        self.foo.publish(self.model.get_relation('foo', relation_id), result)
```

The four things that make this work:

1. **The charm observes Juju's own relation events**, not the library's. `relation_changed` fires
   when the requirer writes its request. That is the same wake-up the library would have used to
   emit its custom event — the library was never a source of timing, only a relay.

2. **The diff is computed against durable state, not remembered.** "Have I already provisioned
   this?" is answered by looking at what the provider already published, or at the workload itself.
   It is not answered by `StoredState`, and it is not answered by "I received an event once".

   That puts two requirements on you that the delta model did not.

   **Your published response must identify the provisioned resource.** If the response carries
   `store_id`, you can diff. If it is empty, or carries only data derived from the request, you
   cannot — and the fix is in the **wire format**, not in the Python API. `openfga` is the worked
   case: OpenFGA store names are not unique, so `POST /stores` with the same name creates a *second*
   store, and the only identity is the server-assigned ID the provider published. Add the identifier
   before you adopt this pattern.

   **Reading your own application databag requires leadership.** `relation.data[self.app]` raises
   `ops.RelationDataAccessError` on a non-leader unit. Guarding it does not make the problem go
   away — it makes the answer *wrong*, reporting a fully provisioned relation as outstanding purely
   because this unit is not the leader.

   So do the join **inside the library**, expose the result, and say what it does on a non-leader.
   Only the library knows the response format, so only the library can compute the diff correctly; a
   `get_requests()` that returns every request forces every consuming charm to reimplement it.
   Where the charm needs the raw read-back too, name it explicitly:

   ```python
   def get_published(self, relation: ops.Relation) -> FooResponse | None:
       """What this application published on this relation, or None.

       Always None on a non-leader unit, which cannot read its own application databag.
       """
   ```

3. **Reconciliation is idempotent, or guarded by a cheap check** — and a reconciler needs this
   *harder* than the delta model did. The delta model retried a failed provision at most once per
   request event. A reconciler re-enters the window on **every** hook, `update-status` included. If
   your provisioning step is a non-idempotent create with a server-assigned identity — `POST
   /stores`, `CREATE DATABASE` with a generated name — a crash between "created" and "published"
   leaks a resource *per hook* until it succeeds, not once.

   Before adopting this pattern, check that you can either make the create idempotent (a
   client-supplied ID, `IF NOT EXISTS`) or look the resource up from the request. If you can do
   neither, say so in the library docs rather than leaving the charm to find out.

4. **A reconciler creates and updates. It does not destroy.** Absence of a relation and *removal* of
   a relation are indistinguishable from `ops.Model`: during `relation-broken`,
   `model.get_relation(name)` returns `None`, exactly as it does before the relation ever existed —
   `ops.RelationMapping` skips the broken relation ID deliberately.

   So if your library owns durable state outside relation data — a Juju secret, a file, workload
   configuration — do **not** tear it down from the reconcile loop on the strength of an absence.
   The standing rule "no relation implies no private key" converges, and it also fires on `install`
   and on every pre-relation `config-changed`. Give teardown its own name and its own trigger; see
   [Libraries that do real work](#libraries-that-do-real-work).

   Note that idempotence is the wrong test for this. Deleting a private key *is* idempotent — delete
   twice equals delete once — and catastrophic. **The right test is recoverability.**

```{admonition} Removal, on the other hand, comes free
:class: seealso
The usual worry about dropping events is `certificates_removed` and its cousins: "the set shrank" is
a difference between two states, and a reconciler has no "before". It turns out not to need one.

**During `relation-broken`, `ops` has already dropped the departing relation from
`model.relations`.** So a handler that recomputes the union gets the post-removal set for free —
nothing to remember, nothing to diff, no snapshot to go stale. A consumer that used to read
`event.relation_id` and delete that relation's files becomes "rewrite the store from the current
union", which is strictly more robust: it also repairs a store that drifted for any other reason.

The prerequisite is the one thing to write into your usage example: **the charm has to observe
`relation-broken`**, which the library used to do on its behalf. This applies to data the reconciler
can recompute. State the library created *outside* the databag is the case above, and still needs
`clean_up()`.
```

What this buys, beyond dropping the event:

- **A missed or deferred event cannot lose a request.** In the delta model, a request that arrives
  while the provider is in error, or is deferred and then re-emitted with stale content, can be
  dropped silently. A reconciler re-derives the outstanding work on every hook, so the next hook
  fixes it.
- **`update-status` becomes a free retry.** The same reconcile loop runs; anything that failed
  earlier is retried without any special machinery.

The cost is honest: the provider charm must be written holistically, with one reconcile handler
rather than a handler per event type. That is the direction charm guidance is going anyway — the
single most common handler name in the corpus for these events is already `_reconcile`.

(libraries-that-do-real-work)=
## Libraries that do real work

Not every interface library is a typed accessor. `tls-certificates` generates private keys, tracks
certificate expiry, and decides when a certificate is close enough to expiry to renew. That is real
work with real timing, and pretending it is "just data access" would be dishonest.

**Doing real work does not buy you custom events. It buys you more than one method.**

- **The library may own *what* to do. The charm owns *when* it runs.** `sync()` does the constructive
  work now; the charm calls it from its own handlers.
- **Still no custom events**, and so no `refresh_events`, no callbacks, and no observers you register
  on the charm's behalf.
- **`sync()` is not the whole API.** Three things a reconciler cannot derive from `ops.Model` need
  their own entry points. Each is a named method the charm calls — never an event you emit.

### The three-question test

Answer these about your own library. Every "yes" adds one method, and only that method.

**1. Departure.** *Does my library create durable state outside relation data — a Juju secret, a file
on disk, workload configuration — that must be destroyed when the relation goes away?*

If yes, `sync()` must never destroy it, for the reason in
[Request and response](#request-and-response-without-events): a reconciler cannot tell "the relation
was removed" from "there is no relation yet". Add `clean_up(relation)`, document that the charm calls
it from `relation-broken` with `event.relation`, and keep every destructive operation inside it. Be
aware that `relation-broken` also fires when the remote merely scales to zero, so `clean_up` must be
safe for a relation that comes back.

If your library only writes relation data, the answer is **no** — Juju removes the databag for you.

**2. Deadline.** *Does my library need to act at a wall-clock time that no relation event will
coincide with, and is the consequence of missing it an outage rather than a delay?*

If yes, schedule the wake-up yourself where the platform allows it. `tls-certificates` does exactly
this: it stamps a Juju secret expiry on the certificate secret it writes
(`secret.set_info(expire=...)`), and Juju fires `secret-expired` at the renewal point. Scheduling the
wake-up is still yours. **Receiving it is not.** So:

1. **Name the hooks the charm must route to `sync()`, in your class docstring, as a list.** Not "call
   `sync()` regularly" — name them: `relation-created`, `relation-changed`, `config-changed`,
   `secret-expired`, `update-status`.
2. **Make the missed deadline visible.** Your readiness or status API must be able to report "the
   deadline has passed and nothing acted on it". A library that cannot detect its own un-wiring
   should not be reconciler-only.

If the worst case of a late `sync()` is that something happens on the next hook instead of this one,
the answer is **no**.

```{admonition} This is the one place reconciler-only trades a guarantee for discipline
:class: caution
Today `tls-certificates` sets the timer *and* registers the observer, in its own `__init__`, and no
charm can get that wrong. Under reconciler-only the observer moves into the charm — and a charm that
forgets to observe `secret-expired` gets a TLS outage weeks after its author's last deploy, with no
error at deploy time and no error in any hook. That is a real cost, and it is why point 2 above is
not optional. The mitigation is detection, not delegation.
```

**3. Irreducible payload.** *Does a Juju hook hand my library a value that ops gives me no way to
read back afterwards?*

The clear case is `ops.SecretRemoveEvent.revision`. ops exposes `Secret.remove_revision(revision)`
but no way to enumerate a secret's revisions, so that number exists in that hook and nowhere else.
Unhandled, superseded revisions of private-key material accumulate in the secret backend
indefinitely — a security problem, not a tidiness one.

If yes, apply the same test as for the charm object: take the **values**, not the event, and let the
charm forward them.

```python
def on_secret_removed(self, secret: ops.Secret, revision: int) -> None: ...
```

Name these methods so it is obvious which hook feeds them, and say so in the docstring. If every
value you need is readable from `ops.Model` at any time, the answer is **no**.

### What the carve-out does not grant

- **Not custom events.** All three answers are methods.
- **Not `ops.Object`.** None of the three needs `self.on`, `framework.observe`, `StoredState` or
  deferral.
- **Not `ops.CharmBase`.** All three take values the charm can pass.
- **Not a wider constructor.** Timing does not move into `__init__` under any of the three.

### Applying the test

`tls-certificates`' requirer answers **yes, yes, yes**: it owns private-key and certificate secrets
that must die with the relation; it must renew before expiry or the workload loses TLS; and it must
reap superseded secret revisions. Its API is `sync()`, `clean_up(relation)`, `on_secret_removed()`,
plus the ordinary readers and two explicitly named charm-driven mutators,
`regenerate_private_key()` and `import_private_key()`.

`certificate_transfer` answers **no, no, no**: it writes CA certificates to relation data and reads
them back. It is a typed accessor, and it gets `is_ready` / `get_data` / `publish`, full stop.

The questions name **mechanisms, not intentions** — that is what stops "my library does real work"
from being claimable by everyone. Question 1 is checkable by grepping for `add_secret`, file writes
and workload calls. Question 2 requires the consequence of lateness to be an *outage*, which excludes
"I would like to publish promptly". Question 3 names a specific gap in ops. To claim all three you
have to name the durable resource, name the outage, and name the value ops cannot read back.

### What this looks like from the charm

Be honest about the wiring, because it moves into the charm and becomes visible there:

```python
class MyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.tls = TlsCertificatesRequirer(self.model)
        for event in (
            self.on.config_changed,
            self.on.update_status,
            self.on.upgrade_charm,
            self.on.secret_expired,
            self.on['certificates'].relation_created,
            self.on['certificates'].relation_changed,
        ):
            framework.observe(event, self._reconcile)
        framework.observe(self.on['certificates'].relation_broken, self._on_broken)
        framework.observe(self.on.secret_remove, self._on_secret_remove)
```

That is more `framework.observe` calls in the charm than the library used to make on its behalf. It
is a good trade — the charm can *see* its own wiring, and can order it against everything else it
does — but it is not free, and "the charm calls it from a handler it already has" is only true for a
charm that already reconciles holistically.

### The payoff is deleted code, not just a shorter call site

Applying these rules to `tls-certificates` v4's eight-argument requirer constructor:

| Argument | Becomes | Why |
| --- | --- | --- |
| `charm` | `model: ops.Model` | Every use of the charm object is `model.get_secret`, `unit.add_secret` or `app`. No `charm.meta`, no `StoredState`. |
| `relationship_name` | `relation_name` | [Naming](#naming). |
| `certificate_requests` | gone — an argument to `sync(requests)` | And its `Callable` form goes with it. |
| `mode` | gone — a field on each request | |
| `refresh_events` | gone | |
| `private_key` | stays, reluctantly | It is a [mode switch](#mode-switch-in-constructor), and it should not be one. |
| `renewal_relative_time` | keyword on `sync()` | It is write-time policy with no meaning between calls. |
| `certificate_requests_by_mode` | gone | Falls out with `mode`. |

Collapsing `mode`, `certificate_requests` and `certificate_requests_by_mode` into "each request
carries its own mode" removes two validation functions, a mode map, three resolution helpers, an
enum member and six error paths that exist only to police the mutual exclusion between three
constructor arguments. **The constructor-width rule pays for itself in deleted validation code**, not
merely in a shorter call site.

## Before and after

```{admonition} Coming soon
:class: note
A full worked before/after — `certificate_transfer` rewritten to this shape, with the diff to two or
three real consumer charms — is being prepared and will land here. The figures it opens with: 33
charms import `certificate_transfer`, 22 observe its events, across 47 observations, **70% of which
never read the payload**.
```

## Rules at a glance

| Rule | Strength | Source |
| --- | --- | --- |
| Charm library initialisation must not raise **on databag contents** | **MUST** | OP083 `#### Handle bad remote data` |
| `is_ready` must not raise **on relation data**, must be free of side effects, must be `False` when the endpoint is not usable | **MUST** | OP083 `#### Provide .is_ready` |
| The library must provide a readiness API | **MUST** | OP083 `#### Provide .is_ready` |
| Ship tests that demonstrate conformance to the above | **MUST** | OP083 `### Testing` |
| Decouple the charm-facing API from the wire format | SHOULD | OP083 `### Charm library` preamble |
| Provide an advanced-status API | SHOULD | OP083 `#### Advanced status` (*advised*) |
| Reconciler-only: emit no custom events | SHOULD | this guide |
| Don't subclass `ops.Object` | SHOULD | this guide |
| Take `ops.Model`, not `ops.CharmBase`; no payload, callables or mode switches in the constructor | SHOULD | this guide |
| `<Name>Provider` / `<Name>Requirer`, `relation_name`, `get_*` / `publish*` | SHOULD | this guide |
| Pass a tolerant `decoder` to `Relation.load`, and catch `ValueError` | SHOULD | this guide |
| Emit collections in a stable order | **MUST** | {ref}`design-relation-interfaces` `### Collections` |

```{admonition} Two MUSTs whose scope is easy to over-read
:class: caution
Both no-raise MUSTs are scoped to **remote data**, not to everything. Raising in `__init__` for an
endpoint the charm does not declare is conformant and correct; so is letting an `ops.ModelError`
from a failed `relation-get` out of `is_ready`. What must never escape is an exception caused by
what a *remote application wrote*.
```

Read more: {ref}`design-relation-interfaces`,
{ref}`how-to-provide-data-for-charm-tests`

Interface **upgrades** — what may change in a published interface, and the cross-version test-vector
rule — are on {ref}`design-relation-interfaces`, not here.
