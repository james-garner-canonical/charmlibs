# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for the testing CA used to sign issued certificates.

The CA key must stay distinct from any requirer key. Signing with the requirer's own key
produces a certificate whose chain cannot verify against the published CA, and nothing in
the library checks this, so it fails silently.
"""

import json

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import charmlibs.interfaces.tls_certificates as tls_certificates
import charmlibs.interfaces.tls_certificates_testing as tls_certificates_testing
from charmlibs.interfaces.tls_certificates_testing import _testing


def _verified_by_ca(certificate: tls_certificates.Certificate) -> bool:
    """Return whether the testing CA's public key really signed this certificate."""
    cert = certificate._cert
    ca_public_key = _testing._CA_CERT._cert.public_key()
    assert isinstance(ca_public_key, rsa.RSAPublicKey)  # the testing CA is RSA
    algorithm = cert.signature_hash_algorithm
    assert algorithm is not None
    try:
        ca_public_key.verify(
            cert.signature, cert.tbs_certificate_bytes, padding.PKCS1v15(), algorithm
        )
    except InvalidSignature:
        return False
    return True


def test_ca_cert_is_a_real_ca():
    assert _testing._CA_CERT.is_ca  # BasicConstraints CA:TRUE


def test_ca_cert_matches_ca_key():
    assert _testing._CA_CERT.matches_private_key(_testing._CA_KEY)


def test_ca_key_is_not_the_requirer_key():
    assert _testing._CA_KEY != tls_certificates_testing.DEFAULT_PRIVATE_KEY
    assert not _testing._CA_CERT.matches_private_key(tls_certificates_testing.DEFAULT_PRIVATE_KEY)


@pytest.mark.parametrize(
    "private_key",
    [
        pytest.param(tls_certificates_testing.DEFAULT_PRIVATE_KEY, id="default-key"),
        pytest.param(tls_certificates.PrivateKey.generate(), id="caller-supplied-key"),
    ],
)
def test_issued_certificates_chain_to_the_ca(private_key: tls_certificates.PrivateKey):
    """A caller-supplied requirer key must not break the chain."""
    csr = _testing._split_requests([_testing._REQUEST], key=private_key)[0].csr
    certificate = _testing._sign(csr)
    assert _verified_by_ca(certificate)
    assert certificate.matches_private_key(private_key)  # still bound to the requirer


def test_provider_fixture_publishes_a_real_ca():
    rel = tls_certificates_testing.relation_for_provider(
        "foo", private_key=tls_certificates.PrivateKey.generate()
    )
    published = json.loads(rel.local_app_data["certificates"])[0]
    assert tls_certificates.Certificate.from_string(published["ca"]).is_ca
    assert _verified_by_ca(tls_certificates.Certificate.from_string(published["certificate"]))


def test_requirer_fixture_publishes_a_real_ca():
    rel = tls_certificates_testing.relation_for_requirer("foo")
    published = json.loads(rel.remote_app_data["certificates"])[0]
    assert tls_certificates.Certificate.from_string(published["ca"]).is_ca
    assert _verified_by_ca(tls_certificates.Certificate.from_string(published["certificate"]))
