---
myst:
  html_meta:
    description: Design the charm-facing API of an interface library as a plain accessor over relation data, so that any charm can call it from its own event handlers.
---

(design-interface-library-apis)=
# How to design an interface library API
% Based on: OP083 - Relation Interface Design

When designing the charm-facing API of an interface library, follow this high-level approach:

1. Write a plain class for each side of the relation, constructed from `ops.Model`.
2. Provide a readiness check, a getter for the data that you read, and a method that publishes the data that you write.
3. Don't emit or observe events. Instead, tell the charm which Juju events to call you after.
4. Make sure that bad remote data can't put the charm into an error state, and ship tests that show it.

This guide provides rules for the charm-facing API. For the relation data format, see {ref}`design-relation-interfaces`.

```{note}
These rules apply to new interface libraries, and to new major versions of existing ones.
A library that doesn't follow them isn't broken, and doesn't need to be rewritten.
```

## Why is it important to follow these rules?

Charms handle events in different ways.
Some handle each Juju event separately, while others recompute everything from a single handler.
A library that observes events and emits its own has to choose the timing for every charm that uses it, and the result fits neither style well.
Charms end up observing custom events only to ask the library what changed, passing `refresh_event` arguments to hand some of the timing back, or copying relation data elsewhere so that they can use it outside the library's events.

A library that reads and writes only when it's called works with both styles, because the charm decides when to call it.

A charm's `__init__` must complete for the charm to handle any event, and a complex charm constructs many library objects there.
A library can't know whether it's critical to a particular charm, so malformed data from a remote application must never stop the charm from handling events.

Finally, charm authors use many interface libraries.
When the libraries agree on their shape and names, learning one teaches the next.

## General requirements

### Write a plain class

Don't subclass `ops.Object`.
It exists so that objects can emit and observe events and use `ops.StoredState`, none of which an interface library needs.
Being an `ops.Object` also means that the charm has to pass you the framework, and that constructing two objects with the same key raises an error.

Take `ops.Model` as the first argument.
It provides everything that an interface library needs: relations, the local application and unit, and Juju secrets.

```py
DEFAULT_RELATION_NAME = 'foo'


class FooRequirer:
    """Requirer side of the foo interface.

    The charm must declare the endpoint with ``limit: 1``.
    """

    def __init__(self, model: ops.Model, relation_name: str = DEFAULT_RELATION_NAME) -> None:
        if relation_name not in model.relations:
            raise KeyError(f'{relation_name!r} is not a relation endpoint of this charm')
        self._model = model
        self._relation_name = relation_name
```

In the charm:

```py
self.foo = FooRequirer(self.model)
```

Checking the relation name in the constructor is correct, even though it raises.
An undeclared endpoint is a mistake in the charm, not a problem with relation data, and it would fail in every hook.

Use constructor arguments only to configure how the library behaves.
If you need a value from the charm, take the value rather than the charm.
For example, take `is_subordinate: bool` rather than the charm object to read `charm.meta.subordinate`.
Don't take data to publish, events, or callbacks in the constructor.

### Don't emit or observe events

The library shouldn't define custom events, call `framework.observe`, or accept `refresh_event` arguments or callbacks.
The charm observes Juju events, and calls the library from its own handlers.

To make sure the charm calls the library at the right times, {ref}`tell the charm which events matter <interface-library-events>`.

### Require a recent `ops`

Read and write relation data with `ops.Relation.load` and `ops.Relation.save`, and require `ops>=3.8.1,<4`.
Before `ops` 3.8.1, `load` JSON-decoded every key in the databag, not just the fields of your data class.
That fails on any key that isn't JSON, including `ingress-address`, which Juju sets in every unit databag.

Read more: {ref}`python-package-deps`

## Provide the API

### Provide a readiness check

The library must provide a quick way for the charm to check whether the endpoint is ready to use.
The readiness check must:

- not raise because of relation data
- have no side effects
- return `False` when the data is missing, can't be parsed, or isn't usable

```py
class FooData(pydantic.BaseModel):
    host: str | None = None
    port: int | None = None


class FooRequirer:
    ...

    @property
    def is_ready(self) -> bool:
        """Whether the provider has published usable data. Never raises."""
        data, _ = self._load()
        return data is not None

    def _load(self) -> tuple[FooData | None, str | None]:
        relations = self._model.relations.get(self._relation_name, ())
        if not relations:
            return None, f'no {self._relation_name} relation'
        if len(relations) > 1:
            return None, f'{len(relations)} {self._relation_name} relations, expected one'
        relation = relations[0]
        if relation.app is None or not relation.data[relation.app]:
            return None, f'waiting for {self._relation_name} data'
        try:
            data = relation.load(FooData, relation.app)
        except ValueError as e:
            logger.warning('Invalid %s data: %s', self._relation_name, e)
            return None, f'invalid {self._relation_name} data'
        if data.host is None:
            return None, 'host is missing'
        return data, None
```

`_load` returns the reason along with the data, so that the getter and the {ref}`status API <interface-library-status>` can share it.

Some details to get right:

- Check for an empty databag before parsing. Because the data model has no mandatory fields, an empty databag parses successfully.
- Count the relations yourself. `model.get_relation()` raises `ops.TooManyRelatedAppsError` if a second application is related, and a library can't enforce `limit: 1`.
- If readiness depends on a Juju secret, read it with `Secret.peek_content()`, which doesn't change the revision that the charm tracks, and return `False` on `ops.SecretNotFoundError` or `ops.ModelError`.
- Don't add a cache for relation data. `ops` reads each databag once per hook. Note that `ops.Model.get_secret()` isn't cached.

The example is a property, because the endpoint has one relation.
A provider with many relations can use `is_ready(relation)` instead, and an endpoint that's ready for some purposes before others can provide one property per purpose, such as `is_upstream_ready`.

Test readiness with good data:

```py
META = {'name': 'consumer', 'requires': {'foo': {'interface': 'foo', 'limit': 1}}}


class MyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.foo = FooRequirer(self.model)


def test_is_ready_with_good_data():
    ctx = testing.Context(MyCharm, meta=META)
    relation = testing.Relation('foo', remote_app_data={'host': '"foo.example"', 'new': '"x"'})
    with ctx(ctx.on.relation_changed(relation), testing.State(relations={relation})) as mgr:
        assert mgr.charm.foo.is_ready
        assert mgr.charm.foo.get_data().host == 'foo.example'
```

### Read data with a getter

Provide a getter that returns the parsed data, and raises if there isn't any:

```py
class FooNotReadyError(Exception):
    """Raised by FooRequirer.get_data when no usable data is available."""


class FooRequirer:
    ...

    def get_data(self) -> FooData:
        """Return the provider's data.

        Raises:
            FooNotReadyError: if there's no usable data. Check ``is_ready`` first.
        """
        data, problem = self._load()
        if data is None:
            raise FooNotReadyError(problem)
        return data
```

The readiness check and the getter do different jobs.
The readiness check is safe to call anywhere, including in the charm's `__init__`.
The getter returns data that the charm can use without checking for `None`.

If the endpoint combines data from several relations, such as a set of trusted CA certificates, return the combined collection instead of raising.
A relation with unusable data should contribute nothing, so that one bad remote application can't affect data from the others.

Choose the arguments of the getter to match the endpoint:

| Endpoint | Readiness | Getter |
| --- | --- | --- |
| Requirer with `limit: 1` | `is_ready` | `get_data()` |
| Requirer that combines data from many relations | `is_ready` | `get_data()`, returning the combined data |
| Provider that reads data from each requirer | `is_ready(relation)` | `get_data(relation)` |

Never silently pick one relation out of several.

### Publish data

Provide a method that writes the whole payload:

```py
class FooProvider:
    ...

    def publish(self, data: FooData) -> None:
        """Publish data to every related application. Does nothing on a non-leader unit."""
        if not self._model.unit.is_leader():
            return
        for relation in self._model.relations.get(self._relation_name, ()):
            relation.save(data, self._model.app)
```

Follow these rules when writing data:

- **Check leadership before writing to the application databag.** Only the leader can write it, so skip the write on other units. Don't skip writes to the unit databag, which every unit owns.
- **Take the whole payload, not changes to it.** The charm calls `publish()` with everything that should be published, every time. Methods such as `add_endpoint()` and `remove_endpoint()` have to read back what they wrote, which makes the databag the record of the library's own state.
- **Know what `save` does.** `Relation.save` writes every field of the model, writes `None` as `null`, and leaves keys that aren't in the model alone.
- **Publish collections in a stable order.** Pydantic serialises a `set` or `frozenset` in an order that varies between processes, so the same data produces a different databag and wakes up the remote application with `relation-changed`. Sort collections when serialising:

  ```py
  @pydantic.field_serializer('endpoints')
  def _sorted(self, endpoints: frozenset[str]) -> list[str]:
      return sorted(endpoints)
  ```

- **Make it idempotent.** The charm may call `publish()` from any event. Anything that the method creates outside the databag must be safe to create again. For example, Juju rejects a second secret with the same label, so look up the secret by label before adding it.
- **Raise `ValueError` for bad arguments.** If the charm passes a value that the interface can't represent, raising is the most helpful thing to do, because the charm is on the stack.

If the published data depends on which application you're writing to, such as credentials for each requirer, take the relation: `publish(relation, data)`.

(interface-library-status)=
### Report why the endpoint isn't ready

The library should provide a way to explain why the endpoint isn't ready.
A property that returns a short explanation, or `None`, is a good default:

```py
class FooRequirer:
    ...

    @property
    def rich_status(self) -> str | None:
        """Why the endpoint isn't ready, or None if it is. Never raises."""
        _, problem = self._load()
        return problem
```

In the charm:

```py
if not self.foo.is_ready:
    self.unit.status = ops.WaitingStatus(f'foo not ready: {self.foo.rich_status}')
    return
```

The charm decides the status and the start of the message, and the library provides the explanation:

```text
Waiting(foo not ready: host is missing)
charm  ^^^^^^^^^^^^^^
library                ^^^^^^^^^^^^^^^
```

Don't set the unit status from the library, and don't raise from the status API.
Write the explanations yourself, rather than passing on validation error messages, which change between pydantic versions.
If some problems need an operator to act, such as data that can't be parsed, while others resolve themselves, such as waiting for the remote application, consider also providing a boolean that tells them apart, so that the charm can choose between blocked and waiting status.

Test that the explanation reaches the status, using the `ReconcilingCharm` from {ref}`interface-library-events`:

```py
def test_status_explains_what_is_missing():
    ctx = testing.Context(ReconcilingCharm, meta=META)
    relation = testing.Relation('foo', remote_app_data={'port': '80'})
    state = ctx.run(ctx.on.relation_changed(relation), testing.State(relations={relation}))
    assert isinstance(state.unit_status, ops.WaitingStatus)
    assert 'host is missing' in state.unit_status.message
```

(interface-library-events)=
### Tell the charm which events matter

The library should provide an `events` method that returns the Juju events that the charm should call the library after.
It takes the charm's `on` attribute, because the library doesn't hold the charm:

```py
class FooRequirer:
    ...

    def events(self, on: ops.CharmEvents) -> tuple[ops.BoundEvent, ...]:
        """Juju events after which the result of get_data may change."""
        relation = on[self._relation_name]
        return (relation.relation_changed, relation.relation_broken)
```

A charm that recomputes everything from one handler observes these events along with its own:

```py
class ReconcilingCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.foo = FooRequirer(self.model)
        for event in (self.on.config_changed, *self.foo.events(self.on)):
            framework.observe(event, self._reconcile)

    def _reconcile(self, _: ops.EventBase):
        if not self.foo.is_ready:
            self.unit.status = ops.WaitingStatus(f'foo not ready: {self.foo.rich_status}')
            return
        data = self.foo.get_data()
        ...
```

A charm that handles events separately observes them with a handler dedicated to the library:

```py
        for event in self.foo.events(self.on):
            framework.observe(event, self._on_foo_changed)
```

What to return depends on the side of the relation:

- **For data that the library reads**, return the events after which the getter may return something different. That's usually `relation-changed` and `relation-broken` for the endpoint. During `relation-broken`, `ops` already excludes the departing relation from `model.relations`, so recomputing gives the right answer.
- **For data that the library writes**, return the events after which the charm must publish again. That's usually only `relation-created`, because the charm already knows when its own data changes.
- **If the library depends on other events**, such as `secret-changed` for a secret shared over the relation, or `secret-expired` for a renewal deadline, include them. These events aren't specific to your library, so the charm's handler also runs for other secrets. Make sure your methods are safe to call at any time.

A library can change the events that it returns in a later version, and charms that loop over the result pick up the change without any code changes.

Some events need dedicated handling, such as cleaning up resources when a relation is removed.
Don't return those from `events`. Instead, document them in the class docstring.

Read more: {ref}`interface-library-real-work`

## Handle bad remote data

Constructing the library object and calling the readiness check must not raise because of relation data.
A status API, if you provide one, shouldn't raise either.

- **Don't load relation data in the constructor.** Load it when a method is called.
- **Catch `ValueError` around `Relation.load`.** This covers both values that aren't valid JSON and pydantic validation errors.
- **Let other exceptions propagate.** A mistake in the charm, such as an undeclared relation name, should fail loudly. So should a hook command that fails unexpectedly, such as `relation-get` raising `ops.ModelError`, because Juju retries the hook. Don't wrap the readiness check in `except Exception`.

The getter may raise, because the charm can check readiness first.

Test that bad data doesn't raise, by checking readiness in the charm's `__init__`:

```py
class MyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.foo = FooRequirer(self.model)
        assert not self.foo.is_ready


@pytest.mark.parametrize('data', [
    {},                     # nothing published yet
    {'host': 'not json'},   # not JSON
    {'host': '42'},         # wrong type
    {'port': '80'},         # host is missing
])
def test_bad_remote_data_does_not_raise(data: dict[str, str]):
    ctx = testing.Context(MyCharm, meta=META)
    relation = testing.Relation('foo', remote_app_data=data)
    ctx.run(ctx.on.relation_changed(relation), testing.State(relations={relation}))
```

## Common patterns

### Requests and responses

In some interfaces, the requirer publishes a request and the provider answers it.
Both sides then read and publish.

On the provider, include `relation-changed` in `events`, provide `get_requests()` to read the requests, and take the relation in `publish(relation, response)`.
To avoid repeating work, compare each request with the response already published on that relation, or with the state of the workload.
Don't keep a record of requests in `ops.StoredState`.
For this to work, the response must identify what was provided, and the comparison must run on the leader, because only the leader can read its own application databag.

(interface-library-real-work)=
### Libraries that do more than read and write

Some libraries do real work, such as generating private keys and renewing certificates.
They still shouldn't decide when that work happens:

- **Constructive work goes in one idempotent method**, such as `sync()`, which the charm calls after the events returned by `events`. If the work has a deadline, schedule a wake-up that Juju delivers, such as a secret expiry, and include `secret-expired` in `events`.
- **Destructive work goes in a separate method**, such as `clean_up(relation)`, which the charm calls from `relation-broken`. Never destroy resources in `sync()`: from inside a single event, a relation that was just removed looks the same as one that hasn't been created yet.
- **Values that only a particular event provides become method arguments.** For example, `secret-remove` provides the revision to remove, and nothing else does. Take the revision as an argument, and document which event the charm should call the method from.

## Follow the naming conventions

| Thing | Use | Not |
| --- | --- | --- |
| Classes | `<Name>Provider`, `<Name>Requirer` | `<Name>Provides`, `<Name>Requires`, `<Name>Consumer`, version numbers |
| Relation argument | `relation_name` | `relationship_name` |
| Default endpoint | `DEFAULT_RELATION_NAME` | |
| Readiness | `is_ready`, or `is_<purpose>_ready` | `ready()`, `check_ready()` |
| Read | `get_data()`, or `get_<thing>()` for several things | bare nouns, `fetch_*` |
| Write | `publish()`, or `publish_<thing>()` | `update_*`, `set_*`, `submit_*`, `provide_*` |
| Events | `events(on)` | |

Use one acronym casing for every name in the library, including the data models.

## Rules at a glance

| Rule | Required? |
| --- | --- |
| Constructing the library object doesn't raise because of relation data | Must |
| The library provides a readiness check | Must |
| The readiness check has no side effects, doesn't raise because of relation data, and returns `False` when the endpoint isn't usable | Must |
| Unit tests demonstrate the rules above | Must |
| Published collections are in a stable order ({ref}`design-relation-interfaces`) | Must |
| The library is a plain class constructed from `ops.Model` | Should |
| The library doesn't emit or observe events | Should |
| The library provides an `events` method | Should |
| The library provides a status API | Should |
| The library follows the naming conventions | Should |

Read more: {ref}`design-relation-interfaces`, {ref}`how-to-provide-data-for-charm-tests`
