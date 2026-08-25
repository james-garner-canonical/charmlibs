# charmlibs.interfaces.tls_certificates_testing

The `tls-certificates` testing library. Charms that use `tls-certificates` should use this library in their state-transition tests, so that they don't need to know the underlying relation data format.

To install, add `charmlibs-interfaces-tls-certificates[testing]` to your test dependencies — not `charmlibs-interfaces-tls-certificates-testing` directly, so that the testing package version always matches the library itself. Then in your Python code, import as:

```py
from charmlibs.interfaces import tls_certificates_testing
```

## Usage

`relation_for_requirer` and `relation_for_provider` each return a fully populated `ops.testing.Relation`, ready to drop into your state-transition tests. Pass your charm's endpoint name as the first argument:

```py
import ops.testing

from charmlibs.interfaces import tls_certificates, tls_certificates_testing

import my_charm

REQUESTS = [tls_certificates.CertificateRequestAttributes(common_name="example.com")]


def test_requirer_receives_certificates():
    ctx = ops.testing.Context(my_charm.MyRequirerCharm)
    relation = tls_certificates_testing.relation_for_requirer(
        "certificates", certificate_requests=REQUESTS
    )
    secret = tls_certificates_testing.private_key_secret("certificates")
    state_in = ops.testing.State(relations=[relation], secrets=[secret])
    state_out = ctx.run(ctx.on.update_status(), state_in)
    ...
```

The defaults describe a typical, fully answered relation: one certificate request for `example.com`, with the provider's signed certificate already in place. The remaining arguments are keyword-only:

- `certificate_requests` — the requests the requirer has made. Each entry is a bare `CertificateRequestAttributes` (answered with a certificate), or wrapped to describe that request's outcome: `denied(...)` for an error instead of a certificate, `renewing(...)` for a certificate late enough in its validity period that the library re-requests it on the next reconcile, `expired(...)` for one past it, or `revoked(...)` for one the provider has since revoked. A request with `is_ca=True` is answered with a CA certificate, and every issued certificate is published with its real chain (leaf to root). Mixed outcomes in one relation are fine, and every request appears on the requirer's side regardless of outcome — the charm asked, whatever the provider did about it. To make *all* certificates stale, wrap each request: `[renewing(r) for r in REQUESTS]`. If your charm passes a custom `renewal_relative_time` to the library, pass the same value to `renewing`. The type of an entry — bare or wrapped — is `CertificateRequest`, for annotating mixed lists.
- `certificate_requests_by_mode` — the same, split per scope, for `Mode.APP_AND_UNIT`. See [Application and unit certificates](#application-and-unit-certificates).
- `mode` — whether the requirer's data is unit-scoped (`Mode.UNIT`, the default), app-scoped (`Mode.APP`), or both (`Mode.APP_AND_UNIT`).
- `capabilities` — a `ProviderCapabilities` object. On `relation_for_requirer` it's what the simulated provider has advertised; left out, the provider hasn't advertised and `get_provider_capabilities()` returns `None` ("not known yet"), and the capability-aware callable form of the library's `certificate_requests` is exercised the same way. On `relation_for_provider` it's what the charm under test has *already* published — for testing a provider that starts with stale capabilities in its own databag. A provider charm publishes its own capabilities when it runs, so leave it out unless that starting state matters.
- `remote_app_name` — the name of the application on the other end. Defaults to `ops.testing`'s own `"remote"`.
- `remote_unit_ids` — the unit numbers the remote application has. On `relation_for_provider` in `Mode.UNIT` and `Mode.APP_AND_UNIT`, each remote unit makes its own copy of the requests, so you can test a provider against a multi-unit requirer.
- `response=False` — populate only the side that writes first, for a request the other side hasn't answered yet (`capabilities` are still published if given).
- `private_key` (`relation_for_provider` only) — the key belonging to the simulated remote requirer. Defaults to `DEFAULT_PRIVATE_KEY`.

## Making a requirer fixture agree with your charm

A requirer's relation data is derived from the charm's own configuration, so two things have to agree between the fixture and the charm under test. Both fail **silently** if they don't: the library discards relation data it can't match, and your charm simply sees no certificates.

**The requests.** Pass the same `CertificateRequestAttributes` your charm passes to `TLSCertificatesRequiresV4`. On its next reconcile the library removes any request in the databag that doesn't match one of its own, and nothing has issued a certificate for the ones it writes in their place.

**The private key.** How you make it agree depends on which of the library's two key modes your charm uses.

*If the library manages the key* (you don't pass `private_key` to `TLSCertificatesRequiresV4` — the recommended configuration), add `private_key_secret()` to your state, as above. It returns an `ops.testing.Secret` at the label the library itself uses, so the library adopts `DEFAULT_PRIVATE_KEY` as its own managed key through its normal lookup. Without it the library has no key at all and silently resolves **no certificates**.

Pass the same `endpoint` and `mode` you passed to `relation_for_requirer`, and set `unit_id` if your `ops.testing.Context` doesn't use the default unit `0` — in `Mode.UNIT` the secret label embeds the unit number, and a mismatch also shows up as "no certificates" rather than an error.

*If your charm manages its own key* (you pass `private_key=` to `TLSCertificatesRequiresV4`), do *not* use `private_key_secret()` — the library deletes its managed secret whenever the charm supplies a key. Instead make your charm use `DEFAULT_PRIVATE_KEY` in tests, through whatever seam your charm already uses to supply the key.

`relation_for_provider` needs none of this: `TLSCertificatesProvidesV4` doesn't manage a private key.

### Or avoid both couplings

Start from a bare `ops.testing.Relation`, let the charm make its own requests with its own key, and have `respond_to_requests` answer whatever it asked for. Nothing has to agree, so nothing can silently disagree:

```py
import dataclasses

relation = ops.testing.Relation("certificates", interface="tls-certificates")
state = ops.testing.State(relations=[relation])

state = ctx.run(ctx.on.relation_changed(relation), state)  # the charm asks
relation = tls_certificates_testing.respond_to_requests(state.get_relations("certificates")[0])
state = dataclasses.replace(state, relations={relation})
state = ctx.run(ctx.on.relation_changed(relation), state)  # the charm has its certificates
```

The cost is an extra `ctx.run`, and a starting state that is empty rather than whatever you want to describe. Use `relation_for_requirer` when the starting state is the point of the test, and this when it isn't.

## Answering requests made during a test

`relation_for_requirer` is a static snapshot built before the charm runs, so it can't answer requests your charm makes *during* a test. Key rotation and certificate renewal both have this shape: the charm withdraws its old requests and writes new ones, which nothing has issued certificates for. `respond_to_requests` plays the provider's next move — it returns a copy of a relation with a certificate issued for every request on it that the provider hasn't already answered:

```py
import dataclasses

state = ctx.run(ctx.on.update_status(), state)  # the charm rotates its key
relation = state.get_relations("certificates")[0]
relation = tls_certificates_testing.respond_to_requests(relation)
state = dataclasses.replace(state, relations={relation})
state = ctx.run(ctx.on.relation_changed(relation), state)  # the charm picks up the new certificates
```

Anything the provider has already published stays as it is — advertised capabilities, errors from `denied(...)`, and existing certificates with their `renewing`/`expired`/`revoked` state — so it's safe to call on a fully populated relation, and safe to call repeatedly. Answers to requests the requirer has since withdrawn are dropped, as the provider library does too.

Certificate renewal has the same shape as key rotation: seed a relation with `renewing(...)` requests, reconcile once (the library withdraws them and re-requests), then `respond_to_requests` and reconcile again to watch the charm pick up the fresh certificates.

## Application and unit certificates

In `Mode.APP_AND_UNIT` the charm holds a certificate in each scope, requested through the library's `certificate_requests_by_mode`. Build the fixture with the same mapping, and seed a key secret for each scope — the library keeps one key per scope, and `relation_for_requirer` signs both scopes' requests with `DEFAULT_PRIVATE_KEY`:

```py
REQUESTS_BY_MODE = {
    tls_certificates.Mode.APP: [
        tls_certificates.CertificateRequestAttributes(common_name="app.example.com")
    ],
    tls_certificates.Mode.UNIT: [
        tls_certificates.CertificateRequestAttributes(common_name="unit.example.com")
    ],
}

relation = tls_certificates_testing.relation_for_requirer(
    "certificates",
    mode=tls_certificates.Mode.APP_AND_UNIT,
    certificate_requests_by_mode=REQUESTS_BY_MODE,
)
state = ops.testing.State(
    leader=True,
    relations=[relation],
    secrets=[
        tls_certificates_testing.private_key_secret("certificates", mode=tls_certificates.Mode.APP),
        tls_certificates_testing.private_key_secret("certificates", mode=tls_certificates.Mode.UNIT),
    ],
)
```

`private_key_secret` describes a single secret, so it doesn't accept `Mode.APP_AND_UNIT` — call it once per scope, as above. The app scope is leader-only, so `leader=True` is needed for the charm to see it.

`certificate_requests` and `certificate_requests_by_mode` are mutually exclusive, and each is valid only for the modes the library accepts it for; passing the wrong combination raises `ValueError` rather than quietly building a relation your charm could never have produced.

## The key material is not API

Only the symbol `DEFAULT_PRIVATE_KEY` is API — its value is not. The key, along with the testing CA's key and certificate, may be regenerated in any release. So don't write tests that depend on the bytes: in particular, don't snapshot-test raw relation data, which embeds the certificate signing requests and therefore the key. Assert on parsed values through the library's accessors instead — not having to touch the wire format is the point of this package.

Read more:
- [How to provide relation data for charm tests](https://canonical.com/juju/docs/charmlibs/how-to/provide-relation-data-for-charm-tests/)
- [Library reference](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/interfaces/tls-certificates/)
