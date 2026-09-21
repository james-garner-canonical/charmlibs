# charmlibs.interfaces.tls_certificates_testing

The `tls-certificates` testing library. Charms that use `tls-certificates` should use this library in their state-transition tests, so that they don't need to know the underlying relation data format.

To install, add `charmlibs-interfaces-tls-certificates[testing]` to your test dependencies — not `charmlibs-interfaces-tls-certificates-testing` directly, so that the testing package version always matches the library itself. Then in your Python code, import as:

```py
from charmlibs.interfaces import tls_certificates_testing
```

## Overview

There are two independent pieces of API.

`RemoteProvider` and `RemoteRequirer` stand in for the application on the other end of the relation. An instance is immutable, so it can live at module level and be shared between tests; each of its methods takes a `State` and returns a new one.

`mocked()` mocks out the library's internals — today, its private key generation — for the duration of a test. Every call that builds state or runs the charm must be inside a `mocked()` scope, and raises if it isn't.

The remote plays the *opposite* role to the charm under test: a requirer charm is tested with a `RemoteProvider`, and a provider charm with a `RemoteRequirer`.

## Testing a requirer charm

```py
import pytest
from ops import testing

from charmlibs.interfaces import tls_certificates_testing

import my_charm

CERTS = tls_certificates_testing.RemoteProvider("certificates")


@pytest.fixture()
def ctx():
    return testing.Context(my_charm.MyCharm)


@pytest.fixture()
def mocked():
    with tls_certificates_testing.mocked():
        yield


def test_requirer_receives_certificates(ctx: testing.Context, mocked: None):
    state_out = CERTS.integrate(ctx, testing.State.from_context(ctx))
    assert isinstance(state_out.unit_status, testing.ActiveStatus)
```

That single `integrate` call runs the whole conversation: it adds the relation, runs the charm for `relation-created`, `relation-joined` and `relation-changed` — during which the charm generates its key and publishes its certificate signing requests — then writes the provider's certificates, then runs the charm again so it picks them up.

**Nothing has to agree between the fixture and your charm.** The provider signs whatever your charm actually asked for, so there is no request list to keep in step and no private key to seed. This holds whether your charm lets the library manage its key (the recommended configuration) or passes `private_key=` itself.

### Stopping earlier

`integrate`'s `end` argument names the state you want the relation left in:

| `end` | the relation is left with… |
|---|---|
| `"integrated"` | the relation made, and your charm having asked |
| `"published"` | the above, plus the provider's certificates on the wire, not yet seen |
| `"received"` (default) | the above, plus your charm having reconciled — the settled relation |

```py
def test_blocked_while_waiting_for_certificates(ctx: testing.Context, mocked: None):
    st = CERTS.integrate(ctx, testing.State.from_context(ctx), end="integrated")
    state_out = ctx.run(ctx.on.update_status(), st)
    assert isinstance(state_out.unit_status, testing.BlockedStatus)
```

A relation that exists with *nothing* written at all is below `"integrated"`: that's a bare `ops.testing.Relation`, and needs nothing from this package. Build it with the remote's own attributes so the two agree:

```py
relation = testing.Relation(
    CERTS.endpoint, interface="tls-certificates", remote_app_name=CERTS.remote_app_name
)
```

### What the provider does with each request

`outcome` takes an `Outcome`, or a callable choosing one per request:

- `Outcome.ISSUED` (the default) — a certificate, valid from now.
- `Outcome.DENIED` — an error instead. Reaches your charm through `get_request_errors()`, `get_request_error()`, and the `certificate_denied` event. Customise it with `error_code`, `error_message` and `error_reason`.
- `Outcome.RENEWING` — a certificate far enough through its validity period that the library's renewal safety net re-requests it on your charm's next reconcile.
- `Outcome.EXPIRED` — a certificate whose validity period is entirely in the past, for testing what your charm does when renewal has *failed*. The library won't rescue it: the safety net stops at expiry.
- `Outcome.REVOKED` — a certificate flagged revoked, which makes the library remove its Juju secret.

The callable receives the `CertificateRequestAttributes` your charm asked for, so it can select on whatever distinguishes your requests:

```py
STRICT = tls_certificates_testing.RemoteProvider(
    "certificates",
    outcome=lambda request: (
        tls_certificates_testing.Outcome.DENIED
        if request.common_name.startswith("*")
        else tls_certificates_testing.Outcome.ISSUED
    ),
    error_code=tls_certificates.CertificateRequestErrorCode.WILDCARD_NOT_ALLOWED,
)
```

A request with `is_ca=True` is answered with a CA certificate, and every issued certificate is published with its real chain, leaf to root, signed by a genuine testing CA — so a charm that verifies chains properly is satisfied.

### Advertised capabilities

`capabilities` is what the provider has advertised about its certificate server. Leave it out and the provider hasn't advertised at all, which `get_provider_capabilities()` reports as `None` ("not known yet") — and which the capability-aware callable form of the library's `certificate_requests` is resolved against. Pass a `ProviderCapabilities`, even an empty one, to model a provider that has advertised:

```py
WILDCARDS = tls_certificates_testing.RemoteProvider(
    "certificates",
    capabilities=tls_certificates.ProviderCapabilities(supports_wildcard_dns=True),
)
```

Each field carries its own three-way meaning: `True` is supported, `False` is advertised-as-unsupported, and `None` is left unspecified.

## Later turns of the conversation

`publish` and `run_changed` are the two moves that drive every turn after the first — after a config change, a key rotation, a renewal, or anything else that makes your charm publish again:

```py
def test_key_rotation(ctx: testing.Context, mocked: None):
    st = CERTS.integrate(ctx, testing.State.from_context(ctx))
    with ctx(ctx.on.update_status(), st) as manager:
        manager.charm.certificates.regenerate_private_key()  # withdraws the old requests
        st = manager.run()
    st = CERTS.publish(st)               # the provider answers the new requests
    state_out = CERTS.run_changed(ctx, st)  # your charm picks the new certificates up
    assert isinstance(state_out.unit_status, testing.ActiveStatus)
```

`publish` recomputes the provider's data from the current state: it answers what your charm now asks for, keeps what it has already answered, and drops answers to requests your charm has withdrawn — which is what the real provider's library does. It's therefore idempotent, and needs no separate API for later turns.

Renewal is the same shape. Because a remote is immutable and depends only on its arguments and the state, two remotes for the same application are just two ways of answering:

```py
STALE = tls_certificates_testing.RemoteProvider("certificates", outcome=Outcome.RENEWING)
FRESH = tls_certificates_testing.RemoteProvider("certificates")


def test_renewal(ctx: testing.Context, mocked: None):
    st = STALE.integrate(ctx, testing.State.from_context(ctx))  # reconcile re-requests
    st = FRESH.publish(st)                                      # answered properly
    state_out = FRESH.run_changed(ctx, st)
```

## Other relation events

`get_relation` is the escape hatch for every event the other methods don't cover. Unlike them it doesn't need the `mocked()` scope, so it's also how assertions read the relation afterwards:

```py
def test_relation_broken(ctx: testing.Context, mocked: None):
    st = CERTS.integrate(ctx, testing.State.from_context(ctx))
    state_out = ctx.run(ctx.on.relation_broken(CERTS.get_relation(st)), st)
    assert isinstance(state_out.unit_status, testing.BlockedStatus)
```

The same approach covers `relation-departed` and the scale events.

## Testing a provider charm

A provider charm is tested with a `RemoteRequirer`. Here the remote writes first, so there's nothing to derive from your charm and the requests are ordinary fixture configuration:

```py
WORKLOAD = tls_certificates_testing.RemoteRequirer(
    "certificates",
    certificate_requests=[
        tls_certificates.CertificateRequestAttributes(common_name="workload.example.com")
    ],
)


def test_provider_issues_certificates(ctx: testing.Context, mocked: None):
    st = testing.State.from_context(ctx, leader=True)
    state_out = WORKLOAD.integrate(ctx, st)
    assert isinstance(state_out.unit_status, testing.ActiveStatus)
```

Note `leader=True`. `TLSCertificatesProvidesV4` writes to the application databag, so a non-leader provider charm answers nothing — which is invisible in the resulting state and easily mistaken for a bug in your charm.

`mode` mirrors the `mode` a real requirer would pass to `TLSCertificatesRequiresV4`: `Mode.UNIT` (the default) puts the requests in the remote unit's databag, `Mode.APP` in the remote application's, and `Mode.APP_AND_UNIT` splits them per `certificate_requests_by_mode`. `private_key` is the key the simulated requirer signs with; a provider charm never sees it, so it's rarely worth setting.

A provider charm may serve several requirer applications on one endpoint, so construct one remote per application:

```py
WORKERS = [
    tls_certificates_testing.RemoteRequirer("certificates", remote_app_name=f"worker{n}")
    for n in range(3)
]


@pytest.fixture()
def clustered(ctx: testing.Context, mocked: None):
    st = testing.State.from_context(ctx, leader=True)
    for worker in WORKERS:
        st = worker.integrate(ctx, st)
    return st
```

A *requirer* charm can have only one provider per endpoint: the library reads its relation with `Model.get_relation`, which raises when an endpoint carries more than one, so a second `RemoteProvider` on the same endpoint raises `ValueError` rather than building a state the charm can't survive. Several endpoints, one remote each, is fine.

`publish` recomputes the requirer's requests from `certificate_requests`, adding what isn't there and removing what this remote no longer asks for, so a test can change what the requirer wants and watch the charm reconcile. The certificates your charm has issued are left alone.

## What `mocked()` does

It replaces the library's private key generation with a pre-generated RSA key. Generating a 2048-bit key takes a noticeable fraction of a second, and a charm that lets the library manage its key generates one on its first reconcile and again on every rotation, so a suite of a few hundred state-transition tests would otherwise spend most of its time on key generation.

Nothing outside the library is patched, so a charm that generates its own keys — through `cryptography` or anything else — is unaffected. The key is a real RSA key, so everything that depends on having one keeps working: signing, `matches_private_key`, chain verification. The only observable difference is that a charm which lets the library manage its key gets the same key in every test.

Key *rotation* still produces a distinct key: the mock returns a fresh key for each call after the first, so a test asserting that `regenerate_private_key()` changed the key still tests something.

The scope is reentrant, so a fixture and the test that uses it may each open one, and several libraries' scopes stack in any order:

```py
@pytest.fixture()
def mocked():
    with (
        tls_certificates_testing.mocked(),
        certificate_transfer_testing.mocked(),
    ):
        yield
```

A test that needs the library mocked but has no interest in the relation can depend on the fixture alone.

The scope is required even though there is only one thing being mocked today, and would be required even if there were nothing: a library that didn't require it would break every test written against it on the day it started mocking. Requiring it from the start makes any future change to `mocked()` a non-breaking one.

## Limitations

**One remote unit.** The simulated remote application has exactly one unit, with unit ID 0. `integrate` fires `relation-joined` and `relation-changed` once, for that unit, and `publish` writes the remote application's databag and unit 0's. An interface that aggregates across the *units* of one remote application can't be fully exercised; aggregating across several remote *applications* on one endpoint can, with one remote per application.

**No scale events.** A unit joining or departing partway through a test isn't expressible through these methods. `get_relation` plus explicit `ctx.run` calls is the answer for now. `relation-departed` and `relation-broken` likewise.

**The secret-expiry renewal route.** `Outcome.RENEWING` reaches the library's renewal safety net, not its `secret-expired` path. The certificate's secret is created by the library as the charm runs, so a state built before the charm has run holds none and there is nothing to fire `ctx.on.secret_expired` at. Both routes withdraw the request and re-request, so the charm ends up in the same place; to exercise the secret-expiry route specifically, run the charm until it holds certificates and fire the event at the secret it created.

See the [library reference documentation](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/interfaces/tls-certificates) for more.
