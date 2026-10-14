---
myst:
  html_meta:
    description: Design the charm-facing API of an interface library for charms that reconcile, as a plain accessor over relation data with no events of its own.
---

(design-interface-library-apis)=
# How to design an interface library API
% Based on: OP083 - Relation Interface Design

When designing the charm-facing API of an interface library, follow this high-level approach:

1. Write a plain class for each side of the relation, constructed from `ops.Model`.
2. Give charms their own types, and keep the relation data format private.
3. Provide a readiness check, getters named after the data that the charm uses, and methods that publish data when they're called, for the charm to call when it reconciles.
4. Start with the smallest API that lets charms do their job.
5. Don't emit or observe events. Instead, provide an `events` method, so that charms that handle each event separately can use the library too.
6. Make sure that bad remote data can't put the charm into an error state, and ship tests that show it.

This guide provides rules for the charm-facing API. For the relation data format, see {ref}`design-relation-interfaces`.

```{note}
These rules apply to new interface libraries, and to new major versions of existing ones.
A library that doesn't follow them isn't broken, and doesn't need to be rewritten.
```

The examples on this page implement a `foo` interface.
A provider publishes the endpoints where it serves its API, and creates a tenant in its workload for each requirer.
A requirer uses one of the endpoints, as its tenant.

## Why is it important to follow these rules?

Reconciling is the most reliable way to write a charm.
A Juju event tells the charm that something changed, but not what, so even a charm that handles each event separately ends up recomputing its state.
A reconciling charm does that directly: it observes the events it cares about with a single handler, reads all the state it needs, and writes everything that should change.

An interface library should fit into that handler.
A library that observes events and emits its own works against it.
The charm has to observe custom events that only say "something changed", pass `refresh_event` arguments to hand some of the timing back to the library, or copy relation data elsewhere so that it can use the data outside the library's events.
Deferred custom events add more paths again.
A library that reads and writes only when it's called has none of these problems.

Not every charm reconciles yet, so a library should also provide a way for a charm that handles each event separately to call it at the right times, without rewriting the charm.

The relation data format has to stay compatible with every version of the library on the other side of the relation, and carries details that only the library needs.
If charms use it directly, every change to the format is a change to every charm.

A charm's `__init__` must complete for the charm to handle any event, and a complex charm constructs many library objects there.
A library can't know whether it's critical to a particular charm, so malformed data from a remote application must never stop the charm from handling events.

Finally, charm authors use many interface libraries.
When the libraries agree on their shape and names, learning one teaches the next.

Read more: {ref}`Ops | Holistic vs delta charms <ops:holistic-vs-delta-charms>`

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
A setting is fine as long as each method means the same thing whatever its value, such as a scope that decides which databag the library writes to.
If a method's docstring has to explain how the method behaves differently depending on a constructor argument, use two objects, or move the choice to a method argument.

If you need a value from the charm, take the value rather than the charm.
For example, take `is_subordinate: bool` rather than the charm object to read `charm.meta.subordinate`.
Don't take data to publish, events, or callbacks in the constructor.

### Don't emit or observe events

The library shouldn't define custom events, call `framework.observe`, or accept `refresh_event` arguments or callbacks.
The charm observes Juju events, and calls the library from its own handlers.

(interface-library-reconcile)=
### Design for a reconciling charm

A reconciling charm calls the library from its reconcile handler, which it observes for every event it cares about, including the relation events for the library's endpoint:

```py
class ReconcilingCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.foo = FooRequirer(self.model)
        events = [
            self.on.config_changed,
            self.on['foo'].relation_changed,
            self.on['foo'].relation_broken,
        ]
        for event in events:
            framework.observe(event, self._reconcile)

    def _reconcile(self, _: ops.EventBase):
        if not self.foo.is_ready:
            self.unit.status = ops.WaitingStatus(f'foo not ready: {self.foo.rich_status}')
            return
        endpoint = self.foo.get_endpoint()
        tenant = self.foo.get_tenant()
        ...
```

Every method that the charm calls should be safe to call from any event, as often as the charm likes.
The rest of this guide shows how.

### Require a recent `ops`

Read and write relation data with `ops.Relation.load` and `ops.Relation.save`, and require `ops>=3.8.1,<4`.
Before `ops` 3.8.1, `load` JSON-decoded every key in the databag, not just the fields of your data model.
That fails on any key that isn't JSON, including `ingress-address`, which Juju sets in every unit databag.

Read more: {ref}`python-package-deps`

(interface-library-private-format)=
## Keep the relation data format private

The data model that you load and save describes the relation data format.
It has to follow the rules in {ref}`design-relation-interfaces`: every field is optional, collections are sets in a stable order, and old fields can't be reused.
It also carries details that only the library needs, such as a format version.
None of that is the charm's concern.

Keep the data model private, and give charms their own types that describe what they use.
Don't return the data model from a getter, or take it as an argument to `publish`.

### Give charms their own types

Write a plain class with read-only properties:

```py
PROTOCOLS = ('grpc', 'http')  # in order of preference


class FooEndpoint:
    """An endpoint where a foo provider serves its API."""

    def __init__(self, *, url: str, protocol: str = 'http') -> None:
        if protocol not in PROTOCOLS:
            raise ValueError(f'protocol must be one of {PROTOCOLS}, not {protocol!r}')
        self._url = url
        self._protocol = protocol

    @property
    def url(self) -> str:
        return self._url

    @property
    def protocol(self) -> str:
        return self._protocol

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FooEndpoint):
            return NotImplemented
        return (self.url, self.protocol) == (other.url, other.protocol)

    def __hash__(self) -> int:
        return hash((self.url, self.protocol))

    def __repr__(self) -> str:
        return f'FooEndpoint(url={self.url!r}, protocol={self.protocol!r})'
```

Follow these rules for charm-facing types:

- **Use a plain class.** A dataclass, named tuple, or pydantic model adds API that you didn't design, such as `dataclasses.astuple`, positional construction, or `model_dump`. Charms come to rely on it, and then you can't change it.
- **Make properties read-only.** The library doesn't write these objects back to the databag, so changing one would do nothing.
- **Take keyword-only constructor arguments**, so that you can add new ones with defaults later.
- **Decide on equality from the start.** If charms compare values or collect them in sets, define `__eq__` and `__hash__` together. Adding `__eq__` later, without `__hash__`, makes the class unhashable.
- **Validate in the constructor**, and raise `ValueError`, so that an invalid value can't exist.
- **Be stricter than the relation data format.** `url` is required here, even though it's optional on the wire, because the library never returns an endpoint without one.

### Convert in one place

Keep the data model and the conversion private:

```py
class _Endpoint(pydantic.BaseModel, frozen=True):
    url: str | None = None
    protocol: str | None = None


class _ProviderData(pydantic.BaseModel):
    version: int | None = None
    endpoints: frozenset[_Endpoint] | None = None

    @pydantic.field_serializer('endpoints')
    def _sorted(self, endpoints: frozenset[_Endpoint] | None) -> list[_Endpoint] | None:
        if endpoints is None:
            return None
        return sorted(endpoints, key=lambda e: (e.url or '', e.protocol or ''))


def _to_wire(endpoints: Iterable[FooEndpoint]) -> _ProviderData:
    wire = frozenset(_Endpoint(url=e.url, protocol=e.protocol) for e in endpoints)
    return _ProviderData(version=1, endpoints=wire)


def _from_wire(data: _ProviderData) -> frozenset[FooEndpoint]:
    # Skip endpoints that this version of the library can't use, rather than rejecting them all.
    return frozenset(
        FooEndpoint(url=e.url, protocol=e.protocol or 'http')
        for e in data.endpoints or ()
        if e.url and (e.protocol or 'http') in PROTOCOLS
    )
```

The conversion is the one place that knows about the relation data format, so it's where to:

- **Read older formats.** When the format changes, both versions convert to the same charm-facing type, and charms don't change.
- **Interpret missing values.** Here, a missing protocol means HTTP.
- **Skip what this version can't use**, such as a protocol added in a later version of the interface, without rejecting the rest.
- **Add and remove details that only the library needs**, such as a format version, request IDs, or the ID of a Juju secret. If the library shares data through a secret, give the charm the secret's content, not its ID.
- **Sort collections.** Pydantic serialises a set in an order that varies between processes, so without sorting, the same data produces a different databag and wakes up the remote application with `relation-changed`.

The testing package should take charm-facing values too, such as `relation_for_requirer('foo', endpoints=[...])`, and use the private conversion to build the relation data.
Because the testing package depends on an exact version of the library, it can use private names.

Read more: {ref}`how-to-provide-data-for-charm-tests`

## Provide the API

(interface-library-smallest-api)=
### Start with the smallest API

Provide the methods that charms need to do their job, and no more.
In the `foo` interface, a requirer needs `get_endpoint()` and `get_tenant()`, and a provider needs `publish()`, `get_outstanding_requests()`, and `publish_tenants()`.

It's tempting to also expose the data underneath, such as every endpoint that the provider offers, or every tenant created so far.
Wait until a charm needs it.
Adding a method later is a minor release, but removing one is a major release, and every public method is one that charms might come to depend on, instead of the one that you intended them to use.

When you do add a lower-level method, return the same charm-facing types, so that it's another view of the same data, rather than a second API.
Never expose the relation data format, even as a lower-level option.

### Provide a readiness check

The library must provide a quick way for the charm to check whether the endpoint is ready to use.
The readiness check must:

- not raise because of relation data
- have no side effects
- return `False` when the data is missing, can't be parsed, or isn't usable

```py
class FooRequirer:
    ...

    @property
    def is_ready(self) -> bool:
        """Whether there's a usable endpoint and a tenant. Never raises."""
        return self.rich_status is None

    def _load(self) -> tuple[tuple[frozenset[FooEndpoint], str] | None, str | None]:
        relations = self._model.relations.get(self._relation_name, ())
        if not relations:
            return None, f'no {self._relation_name} relation'
        if len(relations) > 1:
            return None, f'{len(relations)} {self._relation_name} relations, expected one'
        relation = relations[0]
        if relation.app is None or not relation.data[relation.app]:
            return None, f'waiting for {self._relation_name} data'
        try:
            data = relation.load(_ProviderData, relation.app)
            tenant = relation.load(_TenantData, relation.app).tenant
        except ValueError as e:
            logger.warning('Invalid %s data: %s', self._relation_name, e)
            return None, f'invalid {self._relation_name} data'
        endpoints = _from_wire(data)
        if not endpoints:
            return None, 'no usable endpoints'
        if not tenant:
            return None, 'waiting for a tenant'
        return (endpoints, tenant), None
```

`_load` returns the data, or the reason that it isn't ready.
The readiness check, the getters, and the {ref}`status API <interface-library-status>` all share it.

Some details to get right:

- Check for an empty databag before parsing. Because the data model has no mandatory fields, an empty databag parses successfully.
- Count the relations yourself. `model.get_relation()` raises `ops.TooManyRelatedAppsError` if a second application is related, and a library can't enforce `limit: 1`.
- If readiness depends on a Juju secret, read it with `Secret.peek_content()`, which doesn't change the revision that the charm tracks, and return `False` on `ops.SecretNotFoundError` or `ops.ModelError`.
- Don't add a cache for relation data. `ops` reads each databag once per hook. Note that `ops.Model.get_secret()` isn't cached.

The example is a property, because the requirer has one relation and one purpose.
Readiness can take arguments: a provider with many relations can use `is_ready(relation)`, and a library that makes several independent requests can use `is_ready(request)`.
An endpoint whose data is useful for different purposes at different times can provide one property per purpose, such as `is_upstream_ready`.
For a provider that answers requests, {ref}`the outstanding requests <interface-library-requests>` do the job of a readiness check.

Test readiness with good data:

```py
META = {'name': 'consumer', 'requires': {'foo': {'interface': 'foo', 'limit': 1}}}


class MyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.foo = FooRequirer(self.model)


def test_is_ready_with_good_data():
    ctx = testing.Context(MyCharm, meta=META)
    endpoints = [
        {'url': 'http://foo.example:4318'},
        {'url': 'grpc://foo.example:4317', 'protocol': 'grpc', 'new-field': 'x'},
    ]
    data = {'endpoints': json.dumps(endpoints), 'tenant': '"tenant-1"'}
    relation = testing.Relation('foo', remote_app_data=data)
    with ctx(ctx.on.relation_changed(relation), testing.State(relations={relation})) as mgr:
        assert mgr.charm.foo.is_ready
        assert mgr.charm.foo.get_endpoint() == FooEndpoint(
            url='grpc://foo.example:4317', protocol='grpc'
        )
        assert mgr.charm.foo.get_tenant() == 'tenant-1'
```

### Read data with getters

Name each getter after the data that the charm uses:

```py
class FooNotReadyError(Exception):
    """Raised by FooRequirer's getters when the endpoint isn't ready."""


class FooRequirer:
    ...

    def get_endpoint(self) -> FooEndpoint:
        """The endpoint to use: the most preferred protocol, then the first URL.

        Raises:
            FooNotReadyError: if the endpoint isn't ready. Check ``is_ready`` first.
        """
        loaded, problem = self._load()
        if loaded is None:
            raise FooNotReadyError(problem)
        endpoints, _ = loaded
        return min(endpoints, key=lambda e: (PROTOCOLS.index(e.protocol), e.url))

    def get_tenant(self) -> str:
        """The tenant that the provider created for this application.

        Raises:
            FooNotReadyError: if the endpoint isn't ready. Check ``is_ready`` first.
        """
        loaded, problem = self._load()
        if loaded is None:
            raise FooNotReadyError(problem)
        _, tenant = loaded
        return tenant
```

- **A getter that returns one value raises** when there's no value to return. The charm checks readiness first, and gets a value that it doesn't need to check for `None`.
- **A getter that returns a collection returns it empty** when there's nothing usable.
- **Make choices for the charm.** If the provider offers alternatives, as here, return the one to use, so that every charm doesn't implement the same choice.

The readiness check and the getters do different jobs.
The readiness check is safe to call anywhere, including in the charm's `__init__`.
The getters return data that the charm can use directly.

If the endpoint combines data from several relations, such as a set of trusted CA certificates, return the combined collection.
A relation with unusable data should contribute nothing, so that one bad remote application can't affect data from the others.

Choose the arguments of the getters to match the endpoint:

| Endpoint | Readiness | Getter |
| --- | --- | --- |
| Requirer with `limit: 1` | `is_ready` | `get_<thing>()` |
| Requirer that combines data from many relations | `is_ready` | `get_<thing>()`, returning the combined data |
| Provider that reads data from each requirer | `is_ready(relation)` | `get_<thing>(relation)` |

Never silently pick one relation out of several.

### Publish data

Provide a method that publishes data as soon as it's called:

```py
class FooProvider:
    ...

    def publish(self, endpoints: Iterable[FooEndpoint]) -> None:
        """Publish every endpoint that this provider serves, replacing what was published before.

        Does nothing on a non-leader unit.
        """
        data = _to_wire(endpoints)
        if not self._model.unit.is_leader():
            return
        for relation in self._model.relations.get(self._relation_name, ()):
            relation.save(data, self._model.app)
```

Follow these rules when publishing:

- **Write when called.** Don't provide methods such as `add_endpoint()` that change something in memory for a later call to publish. A charm that forgets the later call publishes nothing, and nothing tells it so.
- **Take the whole payload.** When what you publish is computed from what the charm passes in, as endpoints are, the charm calls `publish()` with everything that should be published, every time, and the library replaces what it published before. Don't provide methods such as `remove_endpoint()`, which would have to read back what the library wrote. Data that can't be computed again, such as a tenant, is different: see {ref}`interface-library-requests`.
- **Take charm-facing values.** Take charm-facing types, or plain keyword arguments for simple values. Never take the data model, a dictionary, or JSON.
- **Check leadership before writing to the application databag.** Only the leader can write it, so skip the write on other units. Don't skip writes to the unit databag, which every unit owns.
- **Raise `ValueError` for bad arguments.** If the charm passes a value that the interface can't represent, raising is the most helpful thing to do, because the charm is on the stack. Here, `FooEndpoint` raises when it's constructed.
- **Make it idempotent.** The charm may call `publish()` from any event. Anything that the method creates outside the databag must be safe to create again. For example, Juju rejects a second secret with the same label, so look up the secret by label before adding it.

Give each publishing method its own data model, with its own fields.
`save` writes every field of the model that it's given, writing `None` as `null`, and leaves other keys alone.
So `publish()` and `publish_tenants()` can write to the same databag without overwriting each other, but two methods that saved the same model would.
If two methods have to write the same fields, load what's there, change it, and save it.

Relation data that the charm writes doesn't reach Juju until the hook ends, and it's discarded if the hook fails.
Within the hook, reads return what was written, and `save` sends only the keys that changed, in one `relation-set` call.
So several writes in one hook are safe, and the remote application sees them as one change, but each write that changes something is a separate hook command.
Where one call can do the job, take everything in one call, as `publish_tenants()` does.

(interface-library-requests)=
### Answer requests

In the `foo` interface, every requirer needs a tenant, which the provider creates in its workload.
Creating a tenant can't be repeated: each attempt creates a different one.
So, unlike the endpoints, the charm can't pass every tenant to the library on every call.
What the library has published is the record of what was created, and it reads that back.

Give the provider a getter for the work that's still to do, and a method that publishes the results:

```py
class FooTenantRequest:
    """A requirer that's waiting for a tenant. Get these from FooProvider.get_outstanding_requests."""

    def __init__(self, relation: ops.Relation) -> None:
        self._relation = relation

    @property
    def requirer(self) -> str:
        """Name of the requiring application."""
        return self._relation.app.name if self._relation.app else ''

    ...  # __eq__, __hash__, and __repr__, comparing the relation ID


class _TenantData(pydantic.BaseModel):
    tenant: str | None = None


class FooProvider:
    ...

    def get_outstanding_requests(self) -> frozenset[FooTenantRequest]:
        """Requirers that don't have a tenant yet. Empty on a non-leader unit."""
        if not self._model.unit.is_leader():
            return frozenset()
        outstanding: set[FooTenantRequest] = set()
        for relation in self._model.relations.get(self._relation_name, ()):
            if relation.app is None:
                continue
            try:
                tenant = relation.load(_TenantData, self._model.app).tenant
            except ValueError:
                tenant = None
            if not tenant:
                outstanding.add(FooTenantRequest(relation))
        return frozenset(outstanding)

    def publish_tenants(self, tenants: Mapping[FooTenantRequest, str]) -> None:
        """Tell each requirer its tenant. Other requirers' tenants are left alone.

        Does nothing on a non-leader unit.
        """
        if not all(tenants.values()):
            raise ValueError('tenant names must not be empty')
        if not self._model.unit.is_leader():
            return
        for request, tenant in tenants.items():
            request._relation.save(_TenantData(tenant=tenant), self._model.app)
```

In the charm:

```py
def _reconcile(self, _: ops.EventBase):
    self.foo.publish(self._endpoints())
    tenants = {
        request: self._create_tenant(request.requirer)
        for request in self.foo.get_outstanding_requests()
    }
    self.foo.publish_tenants(tenants)
```

Follow these rules when answering requests:

- **Work out what's outstanding from what's published.** Compare the requests with the answers already in the databag, or with the state of the workload, not with a record kept in `ops.StoredState`. Only the leader can read its own application databag, so say what the getter does on other units.
- **Give the charm request objects, not relation IDs.** A request object knows where its answer goes, so the charm never handles relation IDs or request IDs. Expose what the charm needs to make a decision, such as the name of the requiring application.
- **Take a batch of answers, and leave other answers alone.** The charm answers every outstanding request in one call. Answers to other requests stay as they are.
- **Let the outstanding requests do the job of a readiness check.** The charm can call `get_outstanding_requests()` from any event, and an empty result means that there's nothing to do.
- **Clean up the workload when a requirer leaves.** When a relation is removed, its relation data goes with it, but the tenant in the workload doesn't. Deleting the tenant is destructive work. See {ref}`interface-library-real-work`.

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

The charm decides the status and the start of the message, and the library provides the explanation:

```text
Waiting(foo not ready: no usable endpoints)
charm  ^^^^^^^^^^^^^^
library                ^^^^^^^^^^^^^^^^^^^
```

Don't set the unit status from the library, and don't raise from the status API.
Write the explanations yourself, rather than passing on validation error messages, which change between pydantic versions.
If some problems need an operator to act, such as data that can't be parsed, while others resolve themselves, such as waiting for the remote application, consider also providing a boolean that tells them apart, so that the charm can choose between blocked and waiting status.

Test that the explanation reaches the status, using the `ReconcilingCharm` from {ref}`interface-library-reconcile`:

```py
def test_status_explains_what_is_missing():
    ctx = testing.Context(ReconcilingCharm, meta=META)
    endpoints = [{'url': 'quic://foo.example', 'protocol': 'quic'}]
    relation = testing.Relation('foo', remote_app_data={'endpoints': json.dumps(endpoints)})
    state = ctx.run(ctx.on.relation_changed(relation), testing.State(relations={relation}))
    assert isinstance(state.unit_status, ops.WaitingStatus)
    assert 'no usable endpoints' in state.unit_status.message
```

(interface-library-events)=
### Support charms that handle events separately

A charm that handles each event separately doesn't have a reconcile handler to call the library from.
So that it can use the library without switching to reconciling, the library should provide an `events` method that returns the Juju events after which the charm should call it.
The method takes the charm's `on` attribute, because the library doesn't hold the charm:

```py
class FooRequirer:
    ...

    def events(self, on: ops.CharmEvents) -> tuple[ops.BoundEvent, ...]:
        """Juju events after which the endpoint or tenant may change."""
        relation = on[self._relation_name]
        return (relation.relation_changed, relation.relation_broken)
```

The charm observes them with a handler dedicated to the library:

```py
class DeltaCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.foo = FooRequirer(self.model)
        for event in self.foo.events(self.on):
            framework.observe(event, self._on_foo_changed)

    def _on_foo_changed(self, _: ops.EventBase):
        if self.foo.is_ready:
            ...
```

What to return depends on the side of the relation:

- **For data that the library reads**, return the events after which the getters may return something different. That's usually `relation-changed` and `relation-broken` for the endpoint. During `relation-broken`, `ops` already excludes the departing relation from `model.relations`, so calling the getters gives the right answer.
- **For data that the library writes**, return the events after which the charm must publish again. That's usually only `relation-created`, because the charm already knows when its own data changes.
- **If the library depends on other events**, such as `secret-changed` for a secret shared over the relation, or `secret-expired` for a renewal deadline, include them.

Some of these events, such as `secret-changed`, aren't specific to your library.
If two libraries return the same event, the charm's handlers for both of them run.
This is another reason for every method to be safe to call from any event.

A library can change the events that it returns in a later version, and charms that loop over the result pick up the change without any code changes.
A reconciling charm doesn't need `events`, but can use it in a unit test to check that it observes everything the library relies on.

Some events need dedicated handling, such as cleaning up resources when a relation is removed.
Don't return those from `events`. Instead, document them in the class docstring.

Read more: {ref}`interface-library-real-work`

## Handle bad remote data

Constructing the library object and calling the readiness check must not raise because of relation data.
A status API, if you provide one, shouldn't raise either.

- **Don't load relation data in the constructor.** Load it when a method is called.
- **Catch `ValueError` around `Relation.load`.** This covers both values that aren't valid JSON and pydantic validation errors.
- **Guard the conversion too.** If the conversion parses values with another library, such as certificates with `cryptography`, catch that library's errors as well, and skip the item that doesn't parse. Catching `ValueError` around `Relation.load` isn't enough on its own.
- **Let other exceptions propagate.** A mistake in the charm, such as an undeclared relation name, should fail loudly. So should a hook command that fails unexpectedly, such as `relation-get` raising `ops.ModelError`, because Juju retries the hook. Don't wrap the readiness check in `except Exception`.

A getter that returns one value may raise, because the charm can check readiness first.

Test that bad data doesn't raise, by checking readiness in the charm's `__init__`:

```py
class MyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.foo = FooRequirer(self.model)
        assert not self.foo.is_ready


@pytest.mark.parametrize('data', [
    {},                                                                # nothing published yet
    {'endpoints': 'not json'},                                         # not JSON
    {'endpoints': '{"url": "http://foo.example"}'},                    # not a list
    {'endpoints': '[{"url": 42}]'},                                    # wrong type
    {'endpoints': '[{"url": "quic://foo.example", "protocol": "quic"}]'},  # nothing usable
    {'endpoints': '[{"url": "http://foo.example"}]'},                    # no tenant yet
])
def test_bad_remote_data_does_not_raise(data: dict[str, str]):
    ctx = testing.Context(MyCharm, meta=META)
    relation = testing.Relation('foo', remote_app_data=data)
    ctx.run(ctx.on.relation_changed(relation), testing.State(relations={relation}))
```

(interface-library-real-work)=
## Libraries that do more than read and write

Some libraries do real work, such as generating private keys and renewing certificates.
They still shouldn't decide when that work happens:

- **Constructive work goes in one idempotent method**, such as `sync()`, which a reconciling charm calls from its reconcile handler. If the work has a deadline, schedule a wake-up that Juju delivers, such as a secret expiry. Then say in the class docstring that the charm must observe `secret-expired`, and include it in `events`.
- **Destructive work that a missing relation triggers goes in a separate method**, such as `clean_up(relation)`, which the charm calls from `relation-broken`. Don't do this work in `sync()`: from inside a single event, a relation that was just removed looks the same as one that hasn't been created yet. Withdrawing something in response to data that is present, such as a request that a requirer removed, is safe in `sync()`.
- **Values that only a particular event provides become method arguments.** For example, `secret-remove` provides the revision to remove, and nothing else does. Take the revision as an argument, and document which event the charm should call the method from.

## Follow the naming conventions

| Thing | Use | Not |
| --- | --- | --- |
| Classes | `<Name>Provider`, `<Name>Requirer` | `<Name>Provides`, `<Name>Requires`, `<Name>Consumer`, version numbers |
| Charm-facing types | What the charm uses, such as `FooEndpoint` | Names of the relation data format, such as `FooAppData` or `FooDatabag` |
| Relation argument | `relation_name` | `relationship_name` |
| Default endpoint | `DEFAULT_RELATION_NAME` | |
| Readiness | `is_ready`, or `is_<purpose>_ready` | `ready()`, `check_ready()` |
| Read | `get_<thing>()`, named after what the charm uses | `get_data()`, bare nouns, `fetch_*` |
| Write | `publish()`, or `publish_<thing>()` for data that's published separately | `add_*`, `remove_*`, `update_*`, `set_*`, `submit_*`, `provide_*` |
| Work still to do | `get_outstanding_requests()` | |
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
| The relation data format is private, and charms use their own types | Should |
| The library starts with the smallest API that charms need | Should |
| Publishing methods write when they're called | Should |
| The library provides an `events` method for charms that don't reconcile | Should |
| The library provides a status API | Should |
| The library follows the naming conventions | Should |

Read more: {ref}`design-relation-interfaces`, {ref}`how-to-provide-data-for-charm-tests`
