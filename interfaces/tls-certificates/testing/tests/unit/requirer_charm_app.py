# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Example requirer charm using Mode.APP.

The certificate belongs to the application rather than the unit: requests go in the app
databag, and only the leader manages the private key or can read it back. See
requirer_charm.py for the default Mode.UNIT configuration.
"""

import ops

import charmlibs.interfaces.tls_certificates as tls_certificates

META = {
    "name": "requirer",
    "requires": {"certificates": {"interface": "tls-certificates"}},
}
REQUESTS = [
    tls_certificates.CertificateRequestAttributes(common_name="example.com"),
    tls_certificates.CertificateRequestAttributes(common_name="eggsample.com"),
]


class AppRequirerCharm(ops.CharmBase):
    """A minimal requirer charm requesting certificates for the application."""

    certs: list[tls_certificates.Certificate] | None = None

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.certificates = tls_certificates.TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            certificate_requests=REQUESTS,
            mode=tls_certificates.Mode.APP,
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
