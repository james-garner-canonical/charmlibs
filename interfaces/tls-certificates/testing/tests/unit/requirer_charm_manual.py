# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Example requirer charm that manages its own private key.

Passing `private_key` to `TLSCertificatesRequiresV4` is discouraged by the library, but
supported, and it behaves quite differently: the key is never persisted, the library deletes
any managed key secret it finds, and `regenerate_private_key`/`import_private_key` raise.

The key is static so the charm is deterministic. It is deliberately NOT
`tls_certificates_testing.DEFAULT_PRIVATE_KEY`, so that tests have to opt in to making the
two agree. See requirer_charm.py for the recommended, library-managed configuration.
"""

import ops

import _keys
import charmlibs.interfaces.tls_certificates as tls_certificates

META = {
    "name": "requirer",
    "requires": {"certificates": {"interface": "tls-certificates"}},
}
REQUESTS = [
    tls_certificates.CertificateRequestAttributes(common_name="example.com"),
    tls_certificates.CertificateRequestAttributes(common_name="eggsample.com"),
]
# Generated for this test charm only. Stands in for a key the charm sources itself, for
# example from Juju config or a user-supplied secret.
PRIVATE_KEY = tls_certificates.PrivateKey.from_string(_keys.MANUAL_CHARM_KEY)


class ManualRequirerCharm(ops.CharmBase):
    """A minimal requirer charm that supplies its own private key."""

    certs: list[tls_certificates.Certificate] | None = None

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.certificates = tls_certificates.TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            certificate_requests=REQUESTS,
            private_key=PRIVATE_KEY,
        )
        framework.observe(self.on.update_status, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        """Handle relation changed event with certificates."""
        certs, _private_key = self.certificates.get_assigned_certificates()
        if not certs:
            self.unit.status = ops.BlockedStatus("TLS certificates not available")
            return
        self.certs = [c.certificate for c in certs]
        self.unit.status = ops.ActiveStatus("TLS ready")
