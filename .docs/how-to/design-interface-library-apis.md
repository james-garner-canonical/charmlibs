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

## The methods

A reconciler-only endpoint class is small. The requirer reads; the provider writes; nothing
schedules anything.

| Side | Method | Strength |
| --- | --- | --- |
| Requirer | `is_ready` | **MUST** (OP083) |
| Requirer | `get_data()` | SHOULD |
| Provider | `publish()` | SHOULD |
| Either | a way to report *why* it is not ready | SHOULD — see [Report why it isn't ready](#report-why-it-isnt-ready) |

Only `is_ready` is required. The other two are conventions, and this page recommends them because
naming them consistently is worth more than any individual name is.

### `is_ready` (MUST)

OP083 requires that a charm library "must provide an API that quickly determines if the endpoint is
'ready' for a particular purpose". The **contract** is fixed:

- free of side effects,
- **must not raise**, and
- returns `False` when the relevant databag is empty, could not be parsed, or the library judges the
  data logically not ready.

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

**Don't over-engineer a cache for it.** Two worries come up here, and neither survives contact with
`ops`:

1. *Won't `is_ready` followed by `get_data()` cost two `relation-get` calls?* No.
   `ops.RelationDataContent` extends `LazyMapping`: it is not populated until accessed, `_load()`
   runs once, and the result is cached until explicitly invalidated. Reading the same databag twice
   in one hook is one hook tool call.
2. *Won't it parse twice?* Only if you let it. Relation data cannot change within a single Juju
   event, so caching the parsed model on the instance is sound if you measure a reason to. Absent
   that reason, a second `model_validate` is cheap.

`is_ready` is also allowed to assert things the databag does not describe — that a secret it points
at is actually readable, say, or that a field's value is one this version of the library supports.
That is the "logically not ready" case, and it is why `is_ready` is not simply "is the databag
non-empty".

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

Return the parsed data, or `None`:

```python
def get_data(self) -> FooData | None:
    """Return the provider's data, or None if it is absent or unusable."""
    return self._load()


def _load(self) -> FooData | None:
    relation = self._relation
    if relation is None or not relation.data.get(relation.app):
        return None
    try:
        return relation.load(FooData, relation.app)
    except pydantic.ValidationError:
        logger.warning('Ignoring unparseable %s data from %s', self._relation_name, relation.app)
        return None
```

`ops.Relation.load` is the modern parsing idiom, and the one to use:

```python
load(self, cls: type[_T], src: Unit | Application, *args, decoder=None, **kwargs) -> _T
```

`cls` is your databag model class and `src` is the `ops.Unit` or `ops.Application` whose databag to
read. `otlp` uses it in this repo; `relation.save(model, self._model.app)` is its counterpart for
writing.

**A strict getter is also allowed.** OP083's no-raise MUST covers initialisation and `is_ready`. It
does **not** cover the getter — see
[Initialisation and `is_ready` must not raise](#initialisation-and-is-ready-must-not-raise), which
explains why that asymmetry is deliberate rather than an oversight.

### `publish()` (SHOULD)

The provider writes. It does not decide when.

```python
def publish(self, data: FooData) -> None:
    """Publish data to every application related on this endpoint.

    Does nothing if this unit is not the leader.
    """
    if not self._model.unit.is_leader():
        logger.debug('Not leader; skipping publish to %s', self._relation_name)
        return
    for relation in self._model.relations[self._relation_name]:
        relation.save(data, self._model.app)
```

Guard the leadership check inside the library. Charm authors forget it, ops raises when they do, and
the resulting error state is not informative. `gateway_metadata`, `istio_metadata` and `otlp` all
guard it this way already.

Note what is *not* in the constructor: no `refresh_event`, no `refresh_events`. The charm calls
`publish()` from whichever handler is right for it.

(one-relation-or-many)=
### One relation or many

OP083 already settles this for `is_ready`, by role. Mirror that split in the getter:

| The endpoint is… | `is_ready` | Getter |
| --- | --- | --- |
| a requirer with `limit: 1` | `is_ready` property | `get_data() -> FooData \| None` |
| a requirer aggregating several relations | `is_ready(relation)` | `get_data(relation)`, plus `get_all_data() -> dict[int, FooData]` if aggregation is the point |
| an app provider | `is_ready(relation)` | `get_data(relation)` |
| a per-unit provider | `is_ready(relation, remote_unit)` | `get_data(relation, remote_unit)` |

**Whatever you choose, do not silently pick one relation out of several.**
`gateway_metadata` does `relations[0] if relations else None`, so a charm with two providers related
gets one of them, non-deterministically, with no way to notice. `istio_metadata` raises `ValueError`
instead, which is honest, and documents the `limit: 1` expectation in the constructor docstring —
that is the better of the two. Better still: take the relation as an argument the moment more than
one is possible.

### Write granularity

`publish(data)` writing to every relation is the right default when the payload is the same for
every remote — metadata, endpoints, capabilities.

Take the relation, `publish(relation, data)`, when the payload is a **function of the remote**: a
certificate issued for one requirer's CSR, credentials minted for one consumer. Writing per-remote
data with an all-relations method is how a provider leaks one consumer's data to another.

The question to ask is not "how many relations do I have?" but "does what I write depend on who I am
writing to?".

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
- **`is_ready` catches parse and validation errors** and returns `False`.
- **Exceptions are still right** for programming errors and transient failures: a relation name that
  is not in the charm's metadata, a hook tool that failed. Those are not remote data.

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

So both shapes are conformant, and the choice is yours:

- **Total getter** — `get_data() -> FooData | None`. Recommended default. `is_ready` is then a
  one-liner, `return self.get_data() is not None`, and stays worth having: it reads better at call
  sites, it is the safe thing to call in `__init__`, and it is where "logically not ready" lives.
- **Strict getter** — `get_data() -> FooData`, raising on absent or unusable data. Then `is_ready`
  is load-bearing, and a charm that skips it gets an error state.

Pick one per library and be consistent within it.

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
| Readiness | `is_ready` | `ready`, `is_client_created` |
| Read | `get_*` | bare nouns, `fetch_*` |
| Write | `publish*` | `update_*`, `set_*`, `submit_*`, `provide_*` |

**Don't put the interface version in the class name.** `tls-certificates` has
`TLSCertificatesRequiresV4` and `TLSCertificatesProvidesV4`; nothing else in this repo does this. The
package version carries the version, and a name that carries it too means every consumer's code
changes on a major bump even where nothing else did.

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
back towards error-carrying events — `oauth`'s `InvalidClientConfigEvent` exists precisely because
there was nowhere else to put the message. So: **a recommended shape, not a required one.**

Recommended: a read-only property named `rich_status`, the name OP083's own example uses, returning
a human-readable explanation or `None` when the endpoint is ready.

```python
@property
def rich_status(self) -> str | None:
    """Why the endpoint is not ready, or None if it is.

    Never raises, and has no side effects.
    """
    relation = self._relation
    if relation is None:
        return f'no {self._relation_name} relation'
    if not relation.data.get(relation.app):
        return f'waiting for data on {self._relation_name}'
    try:
        relation.load(FooData, relation.app)
    except pydantic.ValidationError as e:
        return f'invalid {self._relation_name} data: {e.errors()[0]["msg"]}'
    return None
```

In the charm:

```python
if not self.foo.is_ready:
    self.unit.status = ops.WaitingStatus(f'foo not ready: {self.foo.rich_status}')
    return
```

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

If `rich_status` does not fit your interface — you need structured errors, or one status per
sub-function — deviate. Provide *something*, name it clearly, and document what it returns.

## Request and response, without events

This is the objection that has to be answered, because it is the one case where the event genuinely
looks load-bearing. `database_created`, `openfga_store_created` and `certificate_creation_request`
all exist because the **provider** needs to know that a request arrived so it can act on it.

Under reconciler-only, the provider does not get told. It looks.

```python
class FooProvider:
    def get_requests(self) -> dict[int, FooRequest]:
        """Return the outstanding request on each relation, keyed by relation ID."""
        ...
```

And the charm:

```python
def _reconcile(self, _: ops.EventBase) -> None:
    for relation_id, request in self.foo.get_requests().items():
        if self._already_provisioned(request):
            continue
        result = self._provision(request)
        self.foo.publish(self.model.get_relation('foo', relation_id), result)
```

The three things that make this work:

1. **The charm observes Juju's own relation events**, not the library's. `relation_changed` fires
   when the requirer writes its request. That is the same wake-up the library would have used to
   emit its custom event — the library was never a source of timing, only a relay.
2. **The diff is computed against durable state, not remembered.** "Have I already provisioned
   this?" is answered by looking at what the provider already published, or at the workload itself.
   It is not answered by `StoredState`, and it is not answered by "I received an event once".
3. **Provisioning is idempotent, or guarded by a cheap check.** This is a requirement the delta model
   also had; it was just easier to forget it was there.

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

## Libraries that do real work

Not every interface library is a typed accessor. `tls-certificates` generates private keys, tracks
certificate expiry, and decides when a certificate is close enough to expiry to renew. That is real
work with real timing, and pretending it is "just data access" would be dishonest.

The position:

- **The library may own *what* to do. The charm owns *when* it runs.** Expose a single method — `sync()`,
  `reconcile()` — that does the work now, and let the charm call it from its own handlers.
- **Still no custom events, and so no `refresh_events`.** `tls_certificates` v4's requirer
  constructor is
  `charm, relationship_name, certificate_requests, mode, refresh_events, private_key,
  renewal_relative_time, certificate_requests_by_mode` — eight arguments, one of which exists purely
  to let the charm add timings the library did not think of. A `sync()` the charm calls needs no such
  parameter: the charm calls it from wherever it likes.
- **Wall-clock timing is the charm's problem, and always was.** A renewal deadline 30 days out
  cannot be delivered by a relation event. In the delta model it is delivered by `update-status`
  reaching the library through `refresh_events` — that is, by the charm, indirectly. Making it
  direct removes a layer, it does not add a requirement.

```{admonition} This section is provisional
:class: caution
The rules on this page were stress-tested against `tls-certificates` deliberately, because it is the
library most likely to break them. Treat this section as the current position rather than a settled
one, and say so if you hit a case it does not cover.
```

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
| Charm library initialisation must not raise on databag contents | **MUST** | OP083 `#### Handle bad remote data` |
| `is_ready` must not raise, must be free of side effects, must be `False` on empty/unparseable/not-logically-ready | **MUST** | OP083 `#### Provide .is_ready` |
| The library must provide a readiness API | **MUST** | OP083 `#### Provide .is_ready` |
| Ship tests that demonstrate conformance to the above | **MUST** | OP083 `### Testing` |
| Decouple the charm-facing API from the wire format | SHOULD | OP083 `### Charm library` preamble |
| Provide an advanced-status API | SHOULD | OP083 `#### Advanced status` (*advised*) |
| Reconciler-only: emit no custom events | SHOULD | this guide |
| Don't subclass `ops.Object` | SHOULD | this guide |
| Take `ops.Model`, not `ops.CharmBase` | SHOULD | this guide |
| `<Name>Provider` / `<Name>Requirer`, `relation_name`, `get_*` / `publish*` | SHOULD | this guide |

Read more: {ref}`design-relation-interfaces`,
{ref}`how-to-provide-data-for-charm-tests`

Interface **upgrades** — what may change in a published interface, and the cross-version test-vector
rule — are on {ref}`design-relation-interfaces`, not here.
