---
myst:
  html_meta:
    description: Design the charm-facing API of an interface library, so that charms read and write relation data when they choose to, not when the library chooses.
---

(design-interface-library-apis)=
# How to design an interface library API
% Based on: OP083 - Relation Interface Design

An interface library contains two designs, and they are not the same design:

- The **relation data format** is the JSON that goes on the wire. It is a long-lived contract that outlives every charm revision reading it. The rules for it are in {ref}`design-relation-interfaces`.
- The **charm-facing API** is the classes, methods, and properties that charm authors import. This guide is about that.

When designing the charm-facing API of a new interface library, follow this high-level approach:

1. Write a plain class for each side of the relation, taking `ops.Model`.
2. Give it a way to check readiness, a way to read data, and a way to publish data.
3. Emit no events of your own, so that the charm decides when data is read and written.
4. Document the Juju events that the charm must route to your methods.
5. Ship tests demonstrating that bad remote data can't break the charm.

This guide provides rules for the charm-facing API.

```{note}
Apply this guide to new interface libraries, and to new major versions of existing ones.
A library that emits its own events isn't broken, and this isn't a requirement to rewrite it.
Bear in mind that removing an event class is a breaking change with no deprecation path, because charms import those classes to annotate their handlers.
```

## Why is it important to follow these rules?

Charm authors need to be able to learn one interface library and then use the next one.
Today, libraries differ in almost every dimension that a charm author touches: base class, constructor arguments, readiness API, and the names of the methods that read and write relation data.
Most of those differences are arbitrary, so any consistent choice is an improvement.

Beyond consistency, the rules protect two things.

**A charm's `__init__` must complete for the charm to observe any Juju event.**
A complex charm may construct a dozen library objects there, and your library can't know whether it's critical to that charm or incidental to it.
So a malformed databag from a remote application must never be able to put the whole charm into an error state.

**Timing belongs to the charm.**
A library that decides when to write has to hand the timing back piece by piece: through `refresh_event` parameters, through callbacks that it invokes at moments the charm didn't choose, and through observers registered on the charm's behalf that the charm can't see, opt out of, or order against its own reconcile.
A library that reads and writes only when it's called needs none of that.

## Don't emit custom events

An interface library should be a typed accessor over relation data.
The charm observes Juju's own events, and calls into the library from its own handlers.

So the library shouldn't:

- define event classes, declare an `ops.EventSource`, or expose `self.on`
- call `framework.observe` on the charm's behalf
- accept a `refresh_event` or `refresh_events` argument
- accept a callable in place of a value, to be called back at a time the library chooses

A custom event that the charm receives and then ignores communicates exactly one bit of information: something changed.
The charm then asks the library what the data is, which it could have done from a handler it already had.
Re-emitting an event also invites the charm to defer it, and deferring a re-emitted event defers a snapshot of data that has since moved on.
A library that reads the databag when it's called can't have that bug.

## Write a plain class

### Don't subclass `ops.Object`

`ops.Object` exists to provide `self.on`, and a place in the framework's object tree so that `StoredState` and deferral can find your object again.
A library that emits no events uses none of that, but still pays for it:

- You can't construct an `ops.Object` without a `Framework` or another `Object`, so the charm has to hand you the framework -- the wide argument you were trying to avoid.
- `Object.model` is just `self.framework.model`, which is no more access than you'd get by taking `ops.Model` directly.
- `Object.__init__` registers the object under a handle, so constructing two instances with the same key in one charm becomes an error, for a feature you don't use.

Write a plain class instead:

```py
class FooRequirer:
    """Requirer side of the foo interface."""

    def __init__(self, model: ops.Model, relation_name: str = 'foo') -> None:
        self._model = model
        self._relation_name = relation_name
```

### Take `ops.Model`

Take `ops.Model` as the first argument, rather than `ops.CharmBase`.

`ops.Model` covers everything an interface library needs: relations, the local application and unit, and Juju secrets.
`ops.CharmBase` adds only `charm.meta` and the event sources, which a library that emits no events doesn't need.

Don't try to be narrower than `ops.Model`.
`ops.RelationMapping` is a dead end: it exposes only `get`, `items`, `keys`, and `values`, and holds no reference back to the model.
A library that starts there and later needs a Juju secret can't reach one, and has to add a constructor argument that every existing caller must then pass.

### Name the value you need, don't take the charm

If you think you need the charm object, work out which value you actually need, and take that value instead.
For example, a library that takes the charm only to read `charm.meta.subordinate` should take a boolean:

```py
def __init__(self, model: ops.Model, *, is_subordinate: bool = False) -> None: ...
```

The test isn't "could I get this from the charm?", because you can get anything from the charm.
It's "what is the value, and can the charm pass me the value?"

### Don't take payload in the constructor

A value that parameterises how the library *reads* -- which protocols to accept, whether this charm is subordinate -- belongs in the constructor. It's part of what the object is.

A value that the library will *write to a databag* belongs in the publishing method.
Storing payload on the instance forces the library to decide when to write it, which reintroduces `refresh_event` under another name.
A constructor that takes a payload usually has to grow a method to force a rewrite as well, and both collapse into a single `publish(payload)`.

If a constructor argument is a callable, an event, or a list of events, it's nearly always a method argument in disguise.

(mode-switch-in-constructor)=
### Don't put a mode switch in the constructor

A constructor argument that changes what *other methods mean*, rather than what they operate on, is two classes wearing one name.

The test: if the docstring of method B has to mention constructor argument A, then A is a mode switch.
Prefer two classes, or move the choice to the call site, where the reader can see which behaviour they're getting.

### Check the relation name in `__init__`

`model.relations[name]` raises `KeyError` for an endpoint that the charm doesn't declare.
That's a programming error in the charm, and the constructor is the right place for it to surface, so do the lookup there and let it raise.

Everywhere else, use `model.relations.get(name, ())`, so that no later method has to handle a missing endpoint.

## Provide the methods

An interface library endpoint class is small, and nothing in it schedules anything.

Don't assume that the requirer reads and the provider writes.
That's only true of broadcast-metadata interfaces.
In a request-response interface, the requirer publishes the request and the provider reads it.

| Interface shape | Requirer | Provider |
| --- | --- | --- |
| Broadcast metadata: the provider publishes, the requirer consumes | `is_ready`, `get_data()` | `publish()` |
| Request-response: the requirer asks, the provider answers | `is_ready`, `get_data()`, `publish(request)` | `is_ready(relation)`, `get_requests()`, `publish(relation, response)` |

The full menu of methods:

| Method | Required? | When to provide it |
| --- | --- | --- |
| `is_ready` | Must | On whichever side consumes data that it didn't write |
| `get_data()` | Should | Whenever anything is read |
| `publish()` | Should | Whenever anything is written |
| `rich_status` | Should | See [Report why it isn't ready](#report-why-it-isnt-ready) |
| A named handshake write, such as `publish_version()` | Should | If the requirer declares anything -- see [When the requirer writes too](#when-the-requirer-writes-too) |
| `get_published(relation)` or `get_outstanding_requests()` | Should | Request-response providers -- see [Request and response](#request-and-response) |
| `clean_up(relation)` | Should | If the library creates anything outside the databag -- see [Libraries that do real work](#libraries-that-do-real-work) |
| An explicitly named charm-initiated mutation | Should | For example `regenerate_private_key()`. Name the verb; never `do_*` or `handle_*` |

(provide-is-ready)=
### Provide a readiness API

The library must provide an API that quickly determines whether the endpoint is ready for a particular purpose.
The contract is fixed. The readiness API:

- must be free of side effects
- must not raise because of relation data
- must return `False` when the endpoint isn't usable for its purpose, because the relevant databag is empty, couldn't be parsed, or is logically not ready

```py
@property
def is_ready(self) -> bool:
    """Whether the provider has published data that this library can use.

    Never raises, and has no side effects.
    """
    relations = self._model.relations.get(self._relation_name, ())
    if len(relations) != 1:
        return False
    relation = relations[0]
    if relation.app is None or not relation.data.get(relation.app):
        return False
    try:
        relation.load(FooData, relation.app, decoder=_decode)
    except (ValueError, TypeError):
        return False
    return True
```

`_decode` is the tolerant decoder from [Pass a decoder to `Relation.load`](#pass-a-decoder).
Three things in that body are easy to get wrong:

- **Check the raw databag before parsing.** Because the wire format forbids mandatory fields, an empty databag validates cleanly into an all-defaults model, so "nothing published yet" is only detectable before validation.
- **Catch `ValueError`, not `pydantic.ValidationError`.** `Relation.load` JSON-decodes the databag before pydantic sees it, so a value that isn't JSON arrives as a `json.JSONDecodeError`. Both are `ValueError` subclasses, and catching only the pydantic one lets the other escape.
- **Count the relations yourself**, rather than calling `model.get_relation(name)`, which raises rather than returning `False`.

The emphasis is on *usable*, not on *empty*.
If your interface has a state where the remote legitimately publishes nothing and the endpoint still works, then an empty databag isn't "not ready", and readiness should be `True`.
Decide which your interface is, and say so in the docstring.

The shape isn't fixed. Any of these is fine:

- simple requirer: an `is_ready` property
- application provider: `is_ready(relation)`
- per-unit provider: `is_ready(relation, remote_unit)`
- one attribute per function: `is_upstream_ready`, `is_direct_ready`
- one attribute per state: `is_request_ready`, `is_acknowledgement_ready`

Use the first two unless you have a reason not to, and see [Support one relation or many](#one-relation-or-many).

Readiness is allowed to assert things that the databag doesn't describe, such as that a secret it points at is readable, or that a field's value is one that this version of the library supports.
That's the "logically not ready" case, and it's why readiness isn't simply "is the databag non-empty".

Two more things that the readiness API must survive:

- **A second application related on a `limit: 1` endpoint.** A library can't enforce `limit: 1`, because that lives in the charm's `charmcraft.yaml`. Either catch the `ops.TooManyRelatedAppsError` that `model.get_relation(name)` raises, or avoid it as the example above does, by reading `model.relations.get(name, ())` and checking the count yourself. See [Support one relation or many](#one-relation-or-many).
- **Work that hasn't been done yet.** If your library generates a key and submits a request before anything is usable, readiness is `False` on a fresh unit until the charm has called your publishing method at least once. That's correct, and it's worth saying in the docstring.

```{warning}
Read secrets with `Secret.peek_content()`, never `Secret.get_content(refresh=True)`.
The `refresh` argument tells Juju to update the tracked revision -- a side effect, and one with consequences, because it's what makes Juju emit `secret-remove` for the superseded revision.
`peek_content()` reads the latest revision and changes nothing, which is what a probe wants.
```

```{tip}
Don't build a cache for databag reads.
`ops.RelationDataContent` is lazy and caches its contents, so reading the same databag twice in one hook is a single call to `relation-get`.
Juju secrets are different: `ops.Model.get_secret` issues a `secret-get` on every call and memoises nothing.
If your readiness API touches a secret, cache the `ops.Secret` on the instance for the duration of the hook.
```

(provide-get-data)=
### Read with `get_data()`

The recommended default is a strict getter: return the parsed data, and raise when there is none.

```py
def get_data(self) -> FooData:
    """Return the provider's data.

    Raises:
        FooNotReadyError: if no usable data has been published. Check `is_ready`
            first, or catch this.
    """
    relations = self._model.relations.get(self._relation_name, ())
    if len(relations) != 1:
        raise FooNotReadyError(self.rich_status)
    relation = relations[0]
    if relation.app is None or not relation.data.get(relation.app):
        raise FooNotReadyError(self.rich_status)
    try:
        return relation.load(FooData, relation.app, decoder=_decode)
    except (ValueError, TypeError) as e:
        logger.warning('Unparseable %s data: %s', self._relation_name, e)
        raise FooNotReadyError(self.rich_status) from e
```

```{note}
Each accessor in this guide is written to stand on its own, so `is_ready`, `get_data()`, `rich_status`, and `is_blocked` all repeat the same lookup and parse.
A real library will factor that out.
When you do, don't collapse the shared core to `-> FooData | None`: `rich_status` and `is_blocked` have to know *why* the parse failed, and a core that returns only `None` has thrown that away, so each of them ends up redoing the work anyway.
```

A total getter, `get_data() -> FooData | None`, is equally valid.
If you choose it, readiness collapses to `get_data() is not None`, and your status API becomes the only channel for telling a charm *why* the answer is `None`.

Two kinds of endpoint should always take the total shape:

- **A collection payload.** Return the empty collection, not `None`. {ref}`design-relation-interfaces` requires the empty databag to parse, so the parsed model can't distinguish "absent" from "empty" anyway. Note that readiness is then `bool(self.get_data())`, not `self.get_data() is not None`. Say which one your library uses.
- **An aggregating endpoint.** A getter that raises because of one bad relation can't return the other two. A single broken provider must not be able to empty a charm's whole trust store.

Pick one shape per library and be consistent within it.

(pass-a-decoder)=
#### Pass a decoder to `Relation.load`

`ops.Relation.load` and `ops.Relation.save` are the modern idioms for reading and writing databags.
Both JSON-encode every field by default, and `load` decodes the whole databag before filtering it down to your model's fields.
So a single value that isn't JSON fails the entire load, even one that your model would have ignored.

That isn't an edge case.
Juju writes `egress-subnets`, `ingress-address`, and `private-address` into every unit databag as bare strings, so reading a unit databag with the default decoder raises `json.JSONDecodeError` every time.
Application databags hit the same problem as soon as anything else writes a non-JSON value into them.

Pass a tolerant decoder, and let the field filter drop what isn't yours:

```py
def _decode(value: str) -> Any:
    """Decode one databag value, leaving anything that isn't JSON as a string."""
    try:
        return json.loads(value)
    except ValueError:
        return value


relation.load(FooData, unit, decoder=_decode)
```

The write side fails silently rather than loudly.
Since `encoder` defaults to `json.dumps`, adopting `save` for an existing wire format whose fields are bare strings writes every value JSON-quoted, and breaks every deployed remote.
Pass a matching encoder, and use the same pair on both sides:

```py
relation.save(data, self._model.app, encoder=lambda v: '' if v is None else str(v))
```

```{note}
`Relation.load` and `Relation.save` need `ops>=3`, and pydantic v2 for pydantic models.
If your library still supports pydantic v1, adopting them is a major version change on its own.
```

Two more things about `save` that are easy to be surprised by:

- **It's a total write for the fields it carries.** `save` writes every field of the model, erasing the ones that the dump omits. Republishing a model that carries only some of a databag's fields destroys the rest.
- **`Field(exclude=True)` makes a field unwritable, not just unpublished.** `save` builds its field list from `model_fields` but its values from `model_dump()`, so an excluded field is written as an erase.

(provide-publish)=
### Write with `publish()`

The library writes. It doesn't decide when.

```py
def publish(self, data: FooData) -> None:
    """Publish data to every application related on this endpoint.

    Does nothing if this unit isn't the leader, because this writes the
    application databag.
    """
    if not self._model.unit.is_leader():
        logger.debug('Not leader; skipping publish to %s', self._relation_name)
        return
    for relation in self._model.relations.get(self._relation_name, ()):
        relation.save(data, self._model.app)
```

Guard the leadership check inside the library.
Charm authors forget it, `ops` raises when they do, and the resulting error state isn't informative.

Guard *application* databag writes on leadership, not every write.
A library that writes the *unit* databag must not skip it on a follower, because every unit owns its own databag.

#### Take the whole payload, not a delta

A declarative `publish(data)` is a function of what the charm knows right now.
Incremental `add_*()` and `remove_*()` methods have to read back what they previously wrote, which makes the databag the source of truth for the library's own intent, and anything that touches the databag can corrupt it.

```{warning}
`Relation.save` updates the databag; it doesn't replace it.
It writes the fields that your model carries and leaves every other key alone.
So publishing an empty or shrunken payload doesn't remove keys that are no longer part of it -- you have to clear them yourself, and setting a key to `''` is how Juju deletes it.
Test the empty publish.
```

#### Sort collections on the way out

`Relation.save` calls `model_dump(mode='json')`, and pydantic serialises a `set` or `frozenset` in iteration order, which varies between processes.
The same set then produces a different databag string on every publish, waking every remote with a `relation-changed` for data that didn't change.
That's the spurious event that {ref}`design-relation-interfaces` tells you to avoid, and it arises from combining two rules that live on different pages: model collections as sets, and write them with `Relation.save`.

```py
@pydantic.field_serializer('certificates')
def _serialize_certificates(self, certificates: frozenset[str]) -> list[str]:
    return sorted(certificates)
```

Test this by publishing the same set several times and asserting that there's exactly one distinct databag value.

(when-the-requirer-writes-too)=
#### When the requirer writes too

If the requirer publishes anything -- a supported interface version, the protocols it accepts, a request -- then it needs a publishing method too, and that write becomes the charm's responsibility.
A library that used to make a handshake write from its own `relation-created` handler can no longer do so, and a charm that forgets the call may still work, silently, on a worse path.

So be loud about it:

- **Give it its own name**, such as `publish_version()` or `publish_request()`, rather than a bare `publish()`, so that a reader can see what's being declared.
- **Say in the docstring which Juju event it needs to run on.** `relation-created` is the usual answer for a handshake.
- **Put it in the usage example**, inside the reconcile handler, not in prose.
- **If forgetting it degrades silently, make the other side say so** in its readiness or status API.

(publish-may-raise)=
#### Publishing may raise on its arguments

The no-raise rule covers initialisation and readiness, and it exists to protect the charm from *remote* data.
Data that the charm passed in isn't remote data.

If the charm hands `publish()` a value that this interface can't represent, raise `ValueError`.
The charm is on the stack, at the call site, holding the value it got wrong, which is the best possible place for that error to appear.

This is what retires error-carrying events such as an `InvalidClientConfigEvent`: an event that reports a config the charm itself supplied only exists because the library owned the write timing, and so had no charm frame to raise into.

#### Make side effects idempotent

The charm may call your publishing method on every hook, including `update-status`.
That's only safe if the method is idempotent all the way down, including resources it creates outside the databag.

The trap is Juju secrets.
`ops.Application.add_secret` isn't idempotent: Juju rejects a second `secret-add` with a label already in use, and `ops` surfaces that as an untyped `ModelError`.
Create or update instead:

```py
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
A unit test can't catch this.
`ops.testing` doesn't model Juju's duplicate-label rejection: its `secret_add` adds a second secret with the same label and doesn't raise.
Assert on the number of secrets in the resulting state, and cover the real behaviour in an integration test.
```

(one-relation-or-many)=
### Support one relation or many

Choose one row of this table for your endpoint, and apply it to the readiness API, the getter, and the status accessor alike.
A no-argument status property on a provider with several relations has nowhere to put the answer.

| The endpoint is... | Readiness | Getter | Status |
| --- | --- | --- | --- |
| a requirer with `limit: 1` | `is_ready` property | `get_data()` | `rich_status` property |
| a requirer aggregating a collection | `is_ready(relation=None)` | `get_data()` (merged), plus `get_data_by_relation()` | `rich_status` property |
| an application provider | `is_ready(relation)` | `get_data(relation)` | `rich_status(relation)` |
| a per-unit provider | `is_ready(relation, remote_unit)` | `get_data(relation, remote_unit)` | `rich_status(relation, remote_unit)` |
| a requirer making several independent requests on one relation | `is_ready(request)` | `get_data(request)`, plus an aggregate if useful | `rich_status(request)` |
| a provider answering per request | `is_ready(request)` | `get_requests()` | `rich_status(request)` |

When the endpoint aggregates a collection, the merge is the API.
If the charm's question is "what is the whole set?", then the merged accessor is primary and the per-relation view is the extra.
Making the per-relation getter primary pushes the union loop into every consumer, and with it the decision about what one bad relation does to the result.
That's a semantic decision, and it belongs in the library.
Say in the docstring what happens when one relation's data is unusable: for a collection, the answer is almost always "it contributes nothing, and the rest still works".

Check the role assumption before you copy a row.
The first four rows assume that you're keyed on the relation, or on the relation plus a remote unit.
Ask what the smallest addressable unit of work is, and if it's neither of those, make it a first-class object and key your API on that.
Even where the address is a property of that object, still pass it explicitly: `publish(request, result)` reads better than `publish(result)` with the relation ID buried inside `result`.

Whatever you choose, don't silently pick one relation out of several.
Raising `ValueError`, and documenting the `limit: 1` expectation in the constructor docstring, is much better than `relations[0] if relations else None`.
Better still, take the relation as an argument as soon as more than one is possible.

```{important}
The readiness API can't report "you related two providers to a `limit: 1` endpoint", because it isn't allowed to raise.
It has to return `False` for a condition that isn't a data condition at all, with two perfectly valid databags in front of it.

With a strict getter, raise from the getter. With a total getter, your status accessor is the only channel left, so it must name this case explicitly:

    if len(relations) > 1:
        return f'{len(relations)} {self._relation_name} relations; expected at most one'
```

### Choose the write granularity

`publish(data)` writing to every relation is the right default when the payload is the same for every remote, such as metadata, endpoints, or capabilities.

Take the relation, `publish(relation, data)`, when the payload is a *function of the remote*: a certificate issued for one requirer's CSR, credentials minted for one consumer.
Writing per-remote data with an all-relations method is how a provider leaks one consumer's data to another.

The question to ask isn't "how many relations do I have?" but "does what I write depend on who I'm writing to?".
The question is about content, not encoding.
A provider that writes the same payload to everyone but negotiates a *wire format* per remote still has an all-relations `publish(data)`, because the negotiation is the library's business.

`publish(data, *, relation: ops.Relation | None = None)` is a reasonable third shape when the payload is normally the same for everyone, but the charm occasionally needs to target one relation.
Keep `relation` keyword-only, so that the common call stays `publish(data)`.

Sometimes a provider writes both broadcast fields and per-remote fields into the same application databag.
Don't solve this with two `save()`-based methods, because the broadcast write erases the per-remote fields.
Either expose one per-relation `publish(relation, ...)` that takes the whole payload, or make the broadcast method a read-modify-write that loads what you published on that relation, replaces only the broadcast fields, and saves the merged model.
Either way, say in the docstring which fields the method owns.

## Handle bad remote data

Neither constructing the endpoint object nor calling its readiness API may raise because of relation databag contents.

- **Don't load relation databags at construction time.** If you do, catch everything that `ops.Relation.load()` can raise.
- **Catch parse and validation errors in the readiness API** and return `False`.
- **Catch `ValueError`, not `pydantic.ValidationError`.** `Relation.load` JSON-decodes the databag before pydantic sees it, so a value that isn't JSON arrives as a `json.JSONDecodeError`. Both are `ValueError` subclasses, and catching only the pydantic one lets the other escape.

```{important}
This rule is scoped to databag contents, not to everything.
Exceptions are still the right way to report incorrect initialisation, such as a relation name that isn't in the charm's metadata, and transient errors, such as a hook command unexpectedly failing.
An `ops.ModelError` from a failing `relation-get` propagating out of the readiness API is correct: the charm goes into error, and Juju retries the hook.
What must never escape is a `ValidationError` because a remote application wrote something you didn't expect.

Catch the exceptions that the databag can cause.
Don't wrap the body in a bare `except Exception`, which converts a broken hook tool into a silent `False`.
```

```{warning}
Juju secrets are the exception.
If your readiness API reads a secret, it must catch `ops.SecretNotFoundError` and `ops.ModelError` and return `False`, because a `secret-get` that fails while a grant propagates is indistinguishable from one that fails because the secret was revoked.
This applies to secret reads, not to databag reads.
```

### Let the getter be strict

The no-raise rule applies to initialisation and readiness. The getter isn't one of them.

The readiness API is the safe probe that a charm can call unconditionally, anywhere, including inside `__init__` while wiring one library object into another.
The getter is where the library is allowed to be strict about what it hands back.
They answer different questions, so a library that has both isn't checking the same thing twice:

```py
if not self.foo.is_ready:
    self.unit.status = ops.WaitingStatus(f'foo not ready: {self.foo.rich_status}')
    return
try:
    use(self.foo.get_data())
except FooError as e:
    self.unit.status = ops.BlockedStatus(str(e))
```

Providing a strict getter and no readiness API is the case to avoid.
There's then no way for a charm to ask "is this usable?" without risking the exception, which is exactly what the readiness rule exists to prevent.

(report-why-it-isnt-ready)=
## Report why it isn't ready

Provide an API that reports advanced status.
The recommended shape is a read-only `rich_status` property returning a human-readable explanation, or `None` when there's nothing to report, plus a companion boolean saying whether the reason needs a human.

```py
@property
def rich_status(self) -> str | None:
    """Why the endpoint isn't usable, or None if there's nothing to report.

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
    except (ValueError, TypeError) as e:
        return f'unparseable {self._relation_name} data: {e}'
    return None


@property
def is_blocked(self) -> bool:
    """Whether the reason the endpoint isn't ready needs someone to change something.

    False while the endpoint is merely waiting for an exchange to complete, which will
    resolve on its own. True when a databag is malformed, a secret is unreadable, or the
    model is wired up in a way that this endpoint can't support.

    Never raises, and has no side effects.
    """
    relations = self._model.relations.get(self._relation_name, ())
    if len(relations) > 1:
        return True  # someone has to unrelate one of them
    if not relations:
        return False  # waiting to be related
    relation = relations[0]
    if relation.app is None or not relation.data.get(relation.app):
        return False  # waiting for the provider to publish
    try:
        relation.load(FooData, relation.app, decoder=_decode)
    except (ValueError, TypeError):
        return True  # the remote application published something unusable
    return False
```

In the charm:

```py
if not self.foo.is_ready:
    cls = ops.BlockedStatus if self.foo.is_blocked else ops.WaitingStatus
    self.unit.status = cls(f'foo not ready: {self.foo.rich_status}')
    return
```

The rules for this API:

- **The charm supplies the sentence, and the library supplies the clause.** Never set the unit status from inside a library, which doesn't know whether this endpoint being down means blocked, waiting, or merely degraded for this charm.

  ```text
  Waiting(ingress not ready: FQDN is missing)
  charm  ^^^^^^^^^^^^^^^^^^
  library                    ^^^^^^^^^^^^^^^
  ```

- **It must not raise.** A status accessor that raises while the charm is trying to explain an error is the worst possible time to raise.
- **The boolean is separate from the string.** Don't encode "someone must fix this" inside the prose with a prefix convention, which couples every consuming charm to your wording. Severity remains the charm's call; whether the situation will fix itself is the library's.
- **Report every problem you can see, not just the first one.** An operator who fixes one field, redeploys, waits, and then learns about the next field has been failed twice. Pydantic hands you the whole list of errors, so use it.
- **Don't build the status string out of validator output.** Interpolating a pydantic message couples every consuming charm's tests to your library's pydantic version. Write the clauses yourself, from fields you control.
- **`rich_status` isn't the negation of readiness.** An endpoint that aggregates several relations can be ready *and* have something to say, such as two providers working and a third publishing unusable data. For an aggregator, the charm-side shape is "block if not ready, and warn if ready with a status".

If your wire format already carries structured errors, surface them structurally, and keep `rich_status` as the human-readable summary alongside the structured accessor rather than instead of it.

```{caution}
A status API can only report what the library can observe.
If the provider can *reject* a request, and the interface has no field for saying so, then "rejected" and "not answered yet" are the same bytes on the wire.
No accessor can tell them apart, and the requirer waits forever.
That's a {ref}`relation data format <design-relation-interfaces>` decision, and it has to be made before this API exists.
```

(say-which-juju-events-you-need)=
## Say which Juju events you need

If your library has to act at a particular moment, rather than whenever the charm gets round to it, document the Juju events that the charm must route to you, in the class docstring, as a list.

A library that emits no events can't arrange its own timing, and the wiring lives in the charm.
What used to be a guarantee that the library enforced becomes a fact that the charm has to know, so the library's obligation is to state it, precisely, where the charm author will read it.

Not this:

```py
"""Call sync() regularly."""
```

This:

```py
class TlsCertificatesRequirer:
    """Requirer side of the tls-certificates interface.

    The charm must call :meth:`sync` from each of these Juju events:

    * ``<endpoint>-relation-created``
    * ``<endpoint>-relation-changed``
    * ``config-changed``
    * ``update-status``
    * ``secret-expired`` -- **required**; without it, certificates are never renewed

    and :meth:`clean_up` from ``<endpoint>-relation-broken``.
    """
```

Three cases where this matters:

- **A deadline.** A library can stamp a Juju secret expiry to schedule its own renewal wake-up, but only the charm can receive `secret-expired`. A charm that doesn't route it gets an outage weeks later, with no error at deploy time and no error in any hook.
- **A handshake write.** See [When the requirer writes too](#when-the-requirer-writes-too).
- **Removal.** Recomputation after a relation goes away is correct, but only if the charm observes `relation-broken`.

Put the list in the usage example too, not only in prose, because a charm author copies the example.
Where you can, make the missing wiring detectable: if a missed event degrades silently, your readiness or status API should be able to say so, rather than leaving the charm to discover it in production.

(request-and-response)=
## Handle request and response without events

A provider needs to know that a request has arrived so that it can act on it.
Without custom events, the provider doesn't get told. It looks:

```py
class FooProvider:
    def get_outstanding_requests(self) -> dict[int, FooRequest]:
        """Requests this application hasn't yet answered, keyed by relation ID.

        Empty on a non-leader unit, which can't read its own application databag.
        """
```

And in the charm:

```py
def _reconcile(self, _: ops.EventBase) -> None:
    for relation_id, request in self.foo.get_outstanding_requests().items():
        result = self._provision(request)
        self.foo.publish(self.model.get_relation('foo', relation_id), result)
```

Four things make this work.

**The charm observes Juju's own relation events.**
`relation-changed` fires when the requirer writes its request.
That's the same wake-up that the library would have used to emit a custom event, so the library was never a source of timing, only a relay.

**The difference is computed against durable state, not remembered.**
"Have I already provisioned this?" is answered by looking at what the provider already published, or at the workload itself, not by `StoredState` and not by "I received an event once".
That puts two requirements on you:

- **Your published response must identify the provisioned resource.** If the response carries a server-assigned ID, you can compute the difference. If it's empty, or carries only data derived from the request, you can't -- and the fix is in the wire format, not in the Python API.
- **Reading your own application databag requires leadership.** `relation.data[self.app]` raises `ops.RelationDataAccessError` on a non-leader unit, and guarding it makes the answer wrong rather than making the problem go away.

  So compute the difference inside the library, expose the result, and document what it does on a non-leader unit. Only the library knows the response format, so a `get_requests()` that returns every request forces every consuming charm to reimplement the join.

**Reconciliation must be idempotent, or guarded by a cheap check.**
A charm that reconciles re-enters the window on every hook, `update-status` included.
If your provisioning step is a non-idempotent create with a server-assigned identity, then a crash between "created" and "published" leaks a resource per hook until it succeeds.
Check that you can either make the create idempotent, with a client-supplied ID or an `IF NOT EXISTS`, or look the resource up from the request.

**Reconciliation creates and updates. It doesn't destroy.**
The absence of a relation and the *removal* of a relation are indistinguishable from `ops.Model`: during `relation-broken`, `model.get_relation(name)` returns `None`, exactly as it does before the relation ever existed.
So if your library owns durable state outside relation data, don't tear it down on the strength of an absence, because the same rule fires on `install` and on every pre-relation `config-changed`.
Note that idempotence is the wrong test here.
Deleting a private key is idempotent, and catastrophic. The right test is recoverability.

```{tip}
Removal of relation *data* comes free.
During `relation-broken`, `ops` has already dropped the departing relation from `model.relations`, so a handler that recomputes the union gets the post-removal set with nothing to remember and no snapshot to go stale.
A consumer that used to read `event.relation_id` and delete that relation's files becomes "rewrite the store from the current union", which also repairs a store that drifted for any other reason.
The prerequisite is that the charm observes `relation-broken`, so put it in your usage example.
```

(libraries-that-do-real-work)=
## Libraries that do real work

Not every interface library is a typed accessor.
A library may generate private keys, track certificate expiry, and decide when a certificate is close enough to expiry to renew.
Doing real work doesn't justify custom events. It justifies more than one method.

The library may own *what* to do, and the charm owns *when* it runs.
So `sync()` does the constructive work now, and the charm calls it from its own handlers.

Answer these three questions about your library.
Every "yes" adds one named method that the charm calls, and only that method.

**1. Departure.** *Does my library create durable state outside relation data -- a Juju secret, a file on disk, workload configuration -- that must be destroyed when the relation goes away?*

If yes, `sync()` must never destroy it, for the reason above: reconciliation can't tell "the relation was removed" from "there is no relation yet".
Add `clean_up(relation)`, document that the charm calls it from `relation-broken` with `event.relation`, and keep every destructive operation inside it.
Note that `relation-broken` also fires when the remote scales to zero, so `clean_up` must be safe for a relation that comes back.

If your library only writes relation data, the answer is no, because Juju removes the databag for you.

**2. Deadline.** *Does my library need to act at a wall-clock time that no relation event will coincide with, and is the consequence of missing it an outage rather than a delay?*

If yes, schedule the wake-up yourself where the platform allows it, for example by stamping a Juju secret expiry with `secret.set_info(expire=...)` so that Juju fires `secret-expired`.
Scheduling the wake-up is yours; receiving it isn't. So:

1. Name the hooks that the charm must route to `sync()`, as in [Say which Juju events you need](#say-which-juju-events-you-need).
2. Make the missed deadline visible. Your readiness or status API must be able to report that the deadline passed and nothing acted on it.

If the worst case of a late `sync()` is that something happens on the next hook instead of this one, the answer is no.

**3. Irreducible payload.** *Does a Juju hook hand my library a value that `ops` gives me no way to read back afterwards?*

The clear case is `ops.SecretRemoveEvent.revision`.
`ops` exposes `Secret.remove_revision(revision)` but no way to enumerate a secret's revisions, so that number exists in that hook and nowhere else.
If yes, apply the same test as for the charm object: take the values, not the event, and let the charm forward them.

```py
def on_secret_removed(self, secret: ops.Secret, revision: int) -> None: ...
```

Name these methods so that it's obvious which hook feeds them, and say so in the docstring.
If every value you need is readable from `ops.Model` at any time, the answer is no.

These questions name mechanisms, not intentions.
To claim all three, you have to name the durable resource, name the outage, and name the value that `ops` can't read back.
None of the three grants custom events, `ops.Object`, `ops.CharmBase`, or a wider constructor.

Be honest about the wiring, because it moves into the charm and becomes visible there:

```py
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

That's more `framework.observe` calls than the library used to make on the charm's behalf.
It's a good trade, because the charm can see its own wiring and order it against everything else it does, but it isn't free.

## Follow the naming conventions

There's no correct answer here, and that's why the rule matters: any consistent choice beats the status quo.
Across the interface libraries in this repository there are around ten different names for "read the remote data" and fourteen for "write my data", so a charm author who has learned one of these libraries has learned one of these libraries.

| Thing | Use | Not |
| --- | --- | --- |
| Provider class | `<Name>Provider` | `<Name>Provides` |
| Requirer class | `<Name>Requirer` | `<Name>Requires`, `<Name>Consumer` |
| Relation argument | `relation_name` | `relationship_name` |
| Readiness | `is_ready`, or `is_<state>` per state | `ready()`, `check_ready()`, bare adjectives |
| Read | `get_*` | bare nouns, `fetch_*` |
| Write | `publish*` | `update_*`, `set_*`, `submit_*`, `provide_*` |
| Default endpoint constant | `DEFAULT_RELATION_NAME` | `DEFAULT_INTEGRATION_NAME` |

The readiness row is about form, not about the word "ready".
The `is_` prefix and the boolean predicate are the convention; the noun is yours.
Where an endpoint has genuinely distinct readiness states that different charms consume, `is_client_created` alongside `is_ready` is the right answer, not a naming violation.

For the method names themselves:

- **When the endpoint exposes one payload, use `get_data()` and `publish()`.** The domain is already in the class name, so `FooRequirer.get_data()` is no less clear than `FooRequirer.get_foo()`.
- **When the endpoint exposes several distinct things, name them**, such as `get_certificates()` and `get_ca()`. Keep the `get_` prefix and the `publish` verb.

Pick one acronym casing per library, and apply it to the data models too.
Exporting both `OpenFGARequires` and `OpenfgaProviderAppData` is the problem; neither casing on its own is.

Don't put a version number in the class name.
The one constraint that used to justify it is gone: `ops.Object.handle_kind` is the class name, so renaming an `ops.Object` that emits events orphans deferred notices, but a plain class that emits nothing has no handle and can be renamed freely.

## Test the API

Ship unit tests demonstrating that the endpoint behaves as this guide requires.
Because the library is a function of the state, the tests are functions of the state, with no custom event, no `emitted_events`, and no deferral.

Readiness for good data:

```py
class MyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.foo = FooRequirer(self.model)


def test_is_ready_with_good_data():
    ctx = ops.testing.Context(MyCharm, meta=META)
    data = {'good': '"value"', 'some-future-thing': '"sss"'}
    relation = ops.testing.Relation('foo', remote_app_data=data)
    state = ops.testing.State(relations={relation})
    with ctx(ctx.on.relation_changed(relation), state) as manager:
        manager.run()
        assert manager.charm.foo.is_ready
```

Bad remote data, asserting readiness inside `__init__` so that the test covers both rules at once:

```py
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

Status, checking that the message contains the library's clause rather than matching a whole sentence, so that the test doesn't depend on the charm's wording or on pydantic's:

```py
def test_rich_status_explains_a_bad_field():
    ctx = ops.testing.Context(MyCharm, meta=META)
    relation = ops.testing.Relation('foo', remote_app_data={'host': '"fe80::1"'})
    state = ops.testing.State(relations={relation})
    state_out = ctx.run(ctx.on.relation_changed(relation), state)
    assert isinstance(state_out.unit_status, ops.BlockedStatus)
    assert 'host must be a domain name' in state_out.unit_status.message
```

Also test the empty publish, and test that publishing the same collection repeatedly produces one distinct databag value.
Neither is detectable from a single run.

## Rules at a glance

| Rule | Required? |
| --- | --- |
| Charm library initialisation must not raise because of databag contents | Must |
| The library must provide a readiness API | Must |
| Readiness must not raise because of relation data, must be free of side effects, and must be `False` when the endpoint isn't usable | Must |
| Ship tests demonstrating conformance to the above | Must |
| Document the Juju events that the charm must route to you | Must |
| Emit collections in a stable order | Must |
| Decouple the charm-facing API from the wire format | Should |
| Emit no custom events | Should |
| Don't subclass `ops.Object` | Should |
| Take `ops.Model`; no payload, callables, or mode switches in the constructor | Should |
| Use `<Name>Provider` and `<Name>Requirer`, `relation_name`, `get_*`, and `publish*` | Should |
| Pass a tolerant `decoder` to `Relation.load`, and catch `ValueError` | Should |
| Provide an API reporting advanced status | Should |

Read more: {ref}`design-relation-interfaces`, {ref}`how-to-provide-data-for-charm-tests`

Interface *upgrades* -- what may change in a published interface, and the rule that unit tests run against both old and new test vectors -- are covered in {ref}`design-relation-interfaces`, not here.
