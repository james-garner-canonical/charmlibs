# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Example requirer charm using Mode.APP_AND_UNIT.

The charm holds both an application certificate and a per-unit one, requested through
`certificate_requests_by_mode`. The library keeps a separate private key per scope, and
only the leader can touch the application half. See requirer_charm.py for the plain
Mode.UNIT configuration.
"""

from typing import Literal

import ops

import charmlibs.interfaces.tls_certificates as tls_certificates

META = {
    "name": "requirer",
    "requires": {"certificates": {"interface": "tls-certificates"}},
}
APP_REQUESTS = [tls_certificates.CertificateRequestAttributes(common_name="app.example.com")]
UNIT_REQUESTS = [tls_certificates.CertificateRequestAttributes(common_name="unit.example.com")]
REQUESTS_BY_MODE: dict[
    Literal[tls_certificates.Mode.APP, tls_certificates.Mode.UNIT],
    list[tls_certificates.CertificateRequestAttributes],
] = {
    tls_certificates.Mode.APP: APP_REQUESTS,
    tls_certificates.Mode.UNIT: UNIT_REQUESTS,
}


class AppAndUnitRequirerCharm(ops.CharmBase):
    """A minimal requirer charm requesting both application and unit certificates."""

    app_certs: list[tls_certificates.Certificate] | None = None
    unit_certs: list[tls_certificates.Certificate] | None = None

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.certificates = tls_certificates.TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            mode=tls_certificates.Mode.APP_AND_UNIT,
            certificate_requests_by_mode=REQUESTS_BY_MODE,
        )
        framework.observe(self.on.update_status, self._reconcile)

    def _reconcile(self, _: ops.EventBase) -> None:
        """Collect each scope's certificates separately, as the library reports them."""
        app_certs, _app_key = self.certificates.get_assigned_certificates(
            tls_certificates.Mode.APP
        )
        unit_certs, _unit_key = self.certificates.get_assigned_certificates(
            tls_certificates.Mode.UNIT
        )
        self.app_certs = [c.certificate for c in app_certs]
        self.unit_certs = [c.certificate for c in unit_certs]
        if not unit_certs:
            self.unit.status = ops.BlockedStatus("TLS certificates not available")
            return
        self.unit.status = ops.ActiveStatus("TLS ready")
