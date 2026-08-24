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
import pytest

from charmlibs.interfaces import tls_certificates, tls_certificates_testing

import my_charm


def test_requirer_receives_certificates(monkeypatch: pytest.MonkeyPatch):
    # Make the charm's private key match the one the testing library signs with.
    monkeypatch.setattr(my_charm, "PRIVATE_KEY", tls_certificates_testing.DEFAULT_PRIVATE_KEY)
    ctx = ops.testing.Context(my_charm.MyRequirerCharm)
    relation = tls_certificates_testing.relation_for_requirer(
        "certificates",
        certificate_requests=[
            tls_certificates.CertificateRequestAttributes(common_name="example.com"),
        ],
    )
    state_out = ctx.run(ctx.on.update_status(), ops.testing.State(relations=[relation]))
    ...
```

The defaults describe a typical, fully answered relation: one certificate request for `example.com`, with the provider's signed certificate already in place. The remaining arguments are keyword-only:

- `certificate_requests` — the requests the requirer has made.
- `mode` — whether the requirer's data is unit-scoped (`Mode.UNIT`, the default) or app-scoped (`Mode.APP`).
- `response=False` — populate only the requirer's side, for a request the provider hasn't answered yet.
- `private_key` (`relation_for_provider` only) — the key used to generate the remote requirer's requests and to sign them. Defaults to `DEFAULT_PRIVATE_KEY`.

`relation_for_requirer` always uses `DEFAULT_PRIVATE_KEY`, since the requirer is the charm under test and needs to be able to match the returned certificates to its own requests.

Read more:
- [How to provide relation data for charm tests](https://canonical.com/juju/docs/charmlibs/how-to/provide-relation-data-for-charm-tests/)
- [Library reference](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/interfaces/tls-certificates/)
