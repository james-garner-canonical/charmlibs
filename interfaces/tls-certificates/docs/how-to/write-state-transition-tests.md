---
myst:
  html_meta:
    description: Write state-transition tests for a charm that uses charmlibs.interfaces.tls_certificates, using the library's testing package.
---

# Write state-transition tests for your charm

The `tls-certificates` testing package stands in for the application on the other end of the relation while you test your charm, so that your tests never need to know the relation's wire format.

Add `charmlibs-interfaces-tls-certificates[testing]` to your test dependencies — not `charmlibs-interfaces-tls-certificates-testing` directly, so that the testing package version always matches the library itself. Then import it alongside the library:

```py
from charmlibs.interfaces import tls_certificates, tls_certificates_testing
```

This page covers what is specific to `tls-certificates`. For the shape shared by every `charmlibs.interfaces` testing package — the stand-in charm, deploying and integrating it, the positions a test can reach, when to open the `mocked()` scope, and the limitations they all share — read [how to use a testing package in state-transition tests](../../../../.docs/how-to/use-a-testing-package.md) first.

## Test a requirer charm

A requirer charm — one that asks for certificates — is tested with `provider()`:

```py
import pytest
from ops import testing

from charmlibs.interfaces import tls_certificates_testing

import my_charm


@pytest.fixture()
def juju():
    with testing.Juju() as juju:
        yield juju


def test_requirer_receives_certificates(juju: testing.Juju):
    app = juju.deploy(my_charm.MyCharm)
    ca = juju.deploy(tls_certificates_testing.provider())
    juju.integrate((app, "certificates"), ca)
    juju.settle()
    assert app.leader.state.unit_status == testing.ActiveStatus()
```

`settle()` runs the whole conversation: the charm generates its key and publishes its certificate signing requests, the stand-in signs them, and the charm picks the certificates up — all before control returns.

**Nothing has to agree between the stand-in and your charm.** The provider signs whatever your charm actually asked for, so there is no request list to keep in step and no private key to seed. This holds whether your charm lets the library manage its key (the recommended configuration) or passes `private_key=` itself.

The stand-in's endpoint is named `certificates`, and `Juju.integrate` resolves it unambiguously, since it is the stand-in's only one. Give your charm's endpoint as an `(app, endpoint)` tuple, as above, wherever your charm has more than one `tls-certificates` endpoint — and deploy one stand-in per endpoint:

```py
juju.integrate((app, "certs-for-a"), juju.deploy(tls_certificates_testing.provider(), app="ca-a"))
juju.integrate((app, "certs-for-b"), juju.deploy(tls_certificates_testing.provider(), app="ca-b"))
```

A requirer charm can have only **one provider per endpoint**: the library reads its relation with `Model.get_relation`, which raises when an endpoint carries more than one relation. Integrating a second stand-in to the same requirer endpoint doesn't fail at deploy time — it makes the charm under test fail when it runs, which is what a real second provider would do too.

A requirer charm in `Mode.APP` or `Mode.APP_AND_UNIT` writes its requests to the application databag, which a non-leader unit cannot do — so such a charm publishes nothing at all from its non-leader units, and only the leader's state shows the conversation.

## What the provider does with each request

`outcome` takes an `Outcome`, or a callable choosing one per request. `Outcome` is a class with five classmethod constructors, not an enumeration, so each is called:

- `Outcome.issued()` (the default) — a certificate, valid from now.
- `Outcome.denied()` — an error instead. Reaches your charm through `get_request_errors()`, `get_request_error()`, and the `certificate_denied` event. Customise it with `code`, `message` and `reason`.
- `Outcome.renewing()` — a certificate far enough through its validity period that the library's renewal safety net re-requests it on your charm's next reconcile.
- `Outcome.expired()` — a certificate whose validity period is entirely in the past, for testing what your charm does when renewal has *failed*. The library won't rescue it: the safety net stops at expiry.
- `Outcome.revoked()` — a certificate flagged revoked, which makes the library remove its Juju secret on the charm's next reconcile.

The callable receives the `CertificateRequestAttributes` your charm asked for, reconstructed from the request it actually published, so it can select on whatever distinguishes your requests:

```py
ca = juju.deploy(
    tls_certificates_testing.provider(
        outcome=lambda request: (
            tls_certificates_testing.Outcome.denied(
                code=tls_certificates.CertificateRequestErrorCode.WILDCARD_NOT_ALLOWED
            )
            if request.common_name.startswith("*")
            else tls_certificates_testing.Outcome.issued()
        ),
    )
)
```

A request with `is_ca=True` is answered with a CA certificate, and every issued certificate is published with its real chain, leaf to root, signed by a genuine testing CA — so a charm that verifies chains properly is satisfied.

`validity` sets how long issued certificates are valid for. It's rarely worth changing: `Outcome.renewing()` and `Outcome.expired()` express the interesting positions within the validity period without needing a specific length.

## Advertised capabilities

`capabilities` is what the provider has advertised about its certificate server. Leave it out and the provider hasn't advertised at all, which `get_provider_capabilities()` reports as `None` ("not known yet") — and which the capability-aware callable form of the library's `certificate_requests` is resolved against. Pass a `ProviderCapabilities`, even an empty one, to model a provider that has advertised:

```py
ca = juju.deploy(
    tls_certificates_testing.provider(
        capabilities=tls_certificates.ProviderCapabilities(supports_wildcard_dns=True),
    )
)
```

Each field carries its own three-way meaning: `True` is supported, `False` is advertised-as-unsupported, and `None` is left unspecified.

A charm whose requests *depend on the advertised capabilities* — the callable form of `certificate_requests` — asks first with capabilities still unknown, then withdraws that request and asks again once the provider has advertised. All of it happens within `settle()`: the stand-in drops its answer to the withdrawn request and answers the new one, so the settled state is the one your charm converges to in a real deployment.

## Renewal

`Outcome.renewing()` issues a certificate already due for renewal, so the library's safety net withdraws the request and re-requests on the charm's next reconcile. A real provider answers a fresh request with a fresh certificate, so the stand-in applies `renewing` only to the *first* certificate it issues for each set of request attributes — the re-request is answered normally, and the whole renewal completes within one `settle()`:

```py
def test_renewal(juju: testing.Juju):
    app = juju.deploy(my_charm.MyCharm)
    ca = juju.deploy(
        tls_certificates_testing.provider(outcome=tls_certificates_testing.Outcome.renewing())
    )
    juju.integrate((app, "certificates"), ca)
    juju.settle()
    # The charm has already re-requested and been answered with a fresh certificate.
    assert app.leader.state.unit_status == testing.ActiveStatus()
```

Key rotation has the same shape, with the rotation driven by something in the model — an action on your charm, or a config change — so that the stand-in sees its effects:

```py
def test_key_rotation(juju: testing.Juju):
    app = juju.deploy(my_charm.MyCharm)
    ca = juju.deploy(tls_certificates_testing.provider())
    juju.integrate((app, "certificates"), ca)
    juju.settle()
    # The charm rotates its key: old requests withdrawn, new ones sent.
    juju.config(app, {"key-size": "4096"})
    # The stand-in drops the old answers and signs the new requests.
    juju.settle()
    assert app.leader.state.unit_status == testing.ActiveStatus()
```

## Test a provider charm

A provider charm is tested with `requirer()`. Here the stand-in writes first, so there's nothing to derive from your charm and the requests are ordinary fixture configuration:

```py
def test_provider_issues_certificates(juju: testing.Juju):
    app = juju.deploy(my_charm.MyCharm)
    workload = juju.deploy(
        tls_certificates_testing.requirer(
            certificate_requests=[
                tls_certificates.CertificateRequestAttributes(common_name="workload.example.com")
            ],
        )
    )
    juju.integrate((app, "certificates"), workload)
    juju.settle()
    assert app.leader.state.unit_status == testing.ActiveStatus()
```

`TLSCertificatesProvidesV4` writes to the application databag, so only your charm's leader answers — a non-leader provider charm reads the requests and silently issues nothing, which is invisible in the resulting state and easily mistaken for a bug in your charm. Assert on the leader's state.

`mode` mirrors the `mode` a real requirer would pass to `TLSCertificatesRequiresV4`: `Mode.UNIT` (the default) puts the requests in the stand-in's unit databags, `Mode.APP` in its application databag, and `Mode.APP_AND_UNIT` splits them per `certificate_requests_by_mode`. The argument combinations follow the same pairing rules the library enforces on a real requirer, and a mismatch raises `ValueError` at call time. `private_key` is the key the stand-in signs its requests with; a provider charm never sees it, so it's rarely worth setting.

A provider charm may serve several requirer applications on one endpoint, so deploy one stand-in per application, with distinct application names:

```py
def test_a_cluster(juju: testing.Juju):
    app = juju.deploy(my_charm.MyCharm)
    for n in range(3):
        worker = juju.deploy(
            tls_certificates_testing.requirer(
                certificate_requests=[
                    tls_certificates.CertificateRequestAttributes(
                        common_name=f"worker{n}.example.com"
                    )
                ],
            ),
            app=f"worker{n}",
        )
        juju.integrate((app, "certificates"), worker)
    juju.settle()
    assert app.leader.state.unit_status == testing.ActiveStatus()
```

## What `mocked()` does for this library

It replaces the library's private key generation with a pre-generated RSA key. Generating a 2048-bit key takes a noticeable fraction of a second, and a charm that lets the library manage its key generates one on its first reconcile and again on every rotation, so a suite of a few hundred state-transition tests would otherwise spend most of its time on key generation.

It also replaces two values the library would otherwise draw at random — a new certificate's serial number, and the identifier that distinguishes one certificate request from another — with counters that restart for each scope. Both are *sequences*, never constants, and the distinction matters: the library tells requests apart by that identifier, so a constant would make a re-request identical to the request it replaces, and a renewal would look like a request that had already been answered.

**Certificates are still not reproducible between separately-arranged states.** Their validity dates come from the clock, which the library reads directly, and mocking that would mean mocking something outside the library — which would change the behaviour of charm code that never touches it. So two runs of the same arrangement agree only if they land in the same second. Assert on what the library reports rather than on certificate bytes, and use settling, not byte equality, to check that a certificate was not reissued.

Nothing outside the library is patched, so a charm that generates its own keys — through `cryptography` or anything else — is unaffected. The key is a real RSA key, so everything that depends on having one keeps working: signing, `matches_private_key`, chain verification. The only observable difference is that a charm which lets the library manage its key gets the same key in every test.

Key *rotation* still produces a distinct key: the mock returns a fresh key for each call after the first, so a test asserting that `regenerate_private_key()` changed the key still tests something.

## Limitation: the secret-expiry renewal route

`Outcome.renewing()` reaches the library's renewal safety net, not its `secret-expired` path. The certificate's secret is created by the library as the charm runs, so a state built before the charm has run holds none and there is nothing to fire `ctx.on.secret_expired` at. Both routes withdraw the request and re-request, so the charm ends up in the same place; to exercise the secret-expiry route specifically, let the model settle until the charm holds certificates, then run the event against the secret it created, in a single-charm `Context` test against the unit's state.

Read more:
- [Testing package reference](https://canonical.com/juju/docs/charmlibs/reference/testing/charmlibs-interfaces-tls-certificates-testing/)
- [Library reference](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/interfaces/tls-certificates/)
