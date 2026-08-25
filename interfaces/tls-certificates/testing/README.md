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

- `certificate_requests` — the requests the requirer has made. Each entry is a bare `CertificateRequestAttributes` (answered with a certificate), or wrapped to describe that request's outcome: `denied(...)` for an error instead of a certificate, `renewing(...)` for a certificate late enough in its validity period that the library re-requests it on the next reconcile, `expired(...)` for one past it, or `revoked(...)` for one the provider has since revoked. A request with `is_ca=True` is answered with a CA certificate, and every issued certificate is published with its real chain (leaf to root). Mixed outcomes in one relation are fine, and every request appears on the requirer's side regardless of outcome — the charm asked, whatever the provider did about it. To make *all* certificates stale, wrap each request: `[renewing(r) for r in REQUESTS]`. If your charm passes a custom `renewal_relative_time` to the library, pass the same value to `renewing`.
- `mode` — whether the requirer's data is unit-scoped (`Mode.UNIT`, the default) or app-scoped (`Mode.APP`).
- `response=False` — populate only the requirer's side, for a request the provider hasn't answered yet.
- `private_key` (`relation_for_provider` only) — the key belonging to the simulated remote requirer. Defaults to `DEFAULT_PRIVATE_KEY`.

## The requirer's private key

A requirer's certificates are bound to its private key, so the fixture and the charm under test have to agree on it. How you arrange that depends on which of the library's two key modes your charm uses.

**If the library manages the key** (you don't pass `private_key` to `TLSCertificatesRequiresV4` — the recommended configuration), add `private_key_secret()` to your state, as above. It returns an `ops.testing.Secret` at the label the library itself uses, so the library adopts `DEFAULT_PRIVATE_KEY` as its own managed key through its normal lookup. Without it the library has no key at all and silently resolves **no certificates**.

Pass the same `endpoint` and `mode` you passed to `relation_for_requirer`, and set `unit_id` if your `ops.testing.Context` doesn't use the default unit `0` — in `Mode.UNIT` the secret label embeds the unit number, and a mismatch also shows up as "no certificates" rather than an error.

**If your charm manages its own key** (you pass `private_key=` to `TLSCertificatesRequiresV4`), do *not* use `private_key_secret()` — the library deletes its managed secret whenever the charm supplies a key. Instead make your charm use `DEFAULT_PRIVATE_KEY` in tests, through whatever seam your charm already uses to supply the key.

`relation_for_provider` needs none of this: `TLSCertificatesProvidesV4` doesn't manage a private key.

## Answering requests made during a test

`relation_for_requirer` is a static snapshot built before the charm runs, so it can't answer requests your charm makes *during* a test. Key rotation and certificate renewal both have this shape: the charm withdraws its old requests and writes new ones, which nothing has issued certificates for. `respond_to_requests` plays the provider's next move — it returns a copy of a relation with a certificate issued for every request currently on it:

```py
import dataclasses

state = ctx.run(ctx.on.update_status(), state)  # the charm rotates its key
relation = state.get_relations("certificates")[0]
relation = tls_certificates_testing.respond_to_requests(relation)
state = dataclasses.replace(state, relations={relation})
state = ctx.run(ctx.on.relation_changed(relation), state)  # the charm picks up the new certificates
```

It answers whatever requests are present, whichever key signed them, so it also serves charms that manage their own key — even ones starting from a bare `ops.testing.Relation` rather than `relation_for_requirer`.

Certificate renewal has the same shape: seed a relation with `renewing(...)` requests, reconcile once (the library withdraws them and re-requests), then `respond_to_requests` and reconcile again to watch the charm pick up the fresh certificates.

## The key material is not API

Only the symbol `DEFAULT_PRIVATE_KEY` is API — its value is not. The key, along with the testing CA's key and certificate, may be regenerated in any release. So don't write tests that depend on the bytes: in particular, don't snapshot-test raw relation data, which embeds the certificate signing requests and therefore the key. Assert on parsed values through the library's accessors instead — not having to touch the wire format is the point of this package.

Read more:
- [How to provide relation data for charm tests](https://canonical.com/juju/docs/charmlibs/how-to/provide-relation-data-for-charm-tests/)
- [Library reference](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/interfaces/tls-certificates/)
