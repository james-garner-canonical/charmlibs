# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Example requirer charm that manages its own private key.

Passing `private_key` to `TLSCertificatesRequiresV4` is discouraged by the library, but
supported, and it behaves quite differently: the key is never persisted, the library deletes
any managed key secret it finds, and `regenerate_private_key`/`import_private_key` raise.

The key below is inlined so the charm is deterministic. It is deliberately NOT
`tls_certificates_testing.DEFAULT_PRIVATE_KEY`, so that tests have to opt in to making the
two agree. See requirer_charm.py for the recommended, library-managed configuration.
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
# Generated for this test charm only. Stands in for a key the charm sources itself, for
# example from Juju config or a user-supplied secret.
PRIVATE_KEY = tls_certificates.PrivateKey.from_string(
    """
-----BEGIN RSA PRIVATE KEY-----
MIIEpQIBAAKCAQEAtktRPkQe20DqMLddr9hrfs6tGB907moI+ZW44NBdGpLxWPVJ
t6XO808bdiCb14vfMRAhtLPVqvXUti/9DZKzSyTwYyNle4qZulWK496rzDd8rtoL
246iarKsyyz8jwlkIF5EPHf7wmIqsAP1G7Mziqz5Noc57g44o/aEYgfeWFe2vCAl
P8lup5Uq/MHrKfy8iUdHXCxEOMZfgKneqYlFlBD2M6m7Nvb3qETU8Fs7mscIRqdi
bjUYViWzgDvGTRbLLVoN/UFPYE6jj1AO+VNsZmDKzhkPxkkEucdM9ZBt5qRFKXCG
dNevMe8oVMlxwTzlwEyuoyrNV4ef4WIBaBtLBwIDAQABAoIBAFWzxSdL6WHU/AUZ
P/969NayHei4aUXpLf0A6eEvtIXYzYSwFQ808b2r1FJN9FZ62Nx9JAuLfImad32L
xCGMdaR/YlCJhJ13RNy4eMq2lfg1ofWmZ2q6fRtCk0AWD0rD9IHPL69qDT+O3VjR
E3wJXNL2jVeYbaDAqNpU/FoGLv9Cudk2HSxAB5N5fKuFIKb5KqqzHO6eS4HmxV2/
HS0NmMAFB10cF8fhlfRT/KU7V1aXPp8kqJoMncRN214rvvcVTEGB5iHUY7mHF43z
FZOrwmyd9EIC8fJfsQloyNxK1OewYVOvwtE/JxCJJDuwBJh4bkxwVjJIamaZzFjV
jc4lcAkCgYEA6VLQwy1ox1owj0jzs+kcBO6lYdgAvBiFOqBMIe2qbi0uMJ8tMywc
YlB7i93nDoXGdhJcOvI2J/jFrurTT3HVqldJL/egV3xqa81+JArnCD6KTeUB6MbQ
05sebozvFqSCh5RXHfGPYWL+RqwnzueCMjbWQApO4MFAfnT+pP3a1w0CgYEAyALf
R1TP+ad3okyniYzrtE58HI40gQ27ZXbRBXmvYjXoYqN8+yKQWsik5LnRBXVUJZKl
I8oWdEIPIp6SVs+nOzfO8umQ3qYkgG7ipae/IxH9tuW5Rb7wTKEMxUYxchdW6o6V
oLRjIVWZQncNGUmKH0TYC8BcqYCVBnbzB7OqZWMCgYEApqfTm4Wk0LfX9ZB7GeeI
bvFyyZd6tt+g0gZLOvTChl3ZHzujEmkQgRzRkk7WyiW9YvqsTCJTkmt77/ulIZrC
riAYk52BNtwUO5oU3nO3H8lkCk1n9reD05F5xCcAY6Dv5x2KuEWhT0NhMmOnL39n
HKzUjfuO6bS/d1Pjyz/Tf0UCgYEAnUgk7KL1KQ1YNnixBqmacJ+HWa05/IIf6xoU
JIocMM7Tfz2w+oujmMBPas30YKZzFVjMI+i235VS8ZZg3YNNrnOkecDR+0QLUDPi
ZwISfDGZoknj98S+koPS1w7rsxxHbQvS/hzcF0qIyotz8X6y7wPkINmUBHboubyw
QE44oKECgYEA6P25lh/oX1wNDTcAnxjPcHpOB0glq1aViX7S7o4SuuobaaHUO2Sh
bRB1bFf27afj1P5RqTZCKYKVKqa3v96hdLlV3HhtSyeykJXk+n68waLRdAhNrq/E
zOCx/Xp7JCsQsqWHcXjRDsH8DmRp1MnyjfFfNFn/rUvrWNaXmlkt6oY=
-----END RSA PRIVATE KEY-----
""".strip()
)


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
