# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import types
import typing

import pytest
from ops import testing

import charmlibs.interfaces.tls_certificates as tls_certificates
import charmlibs.interfaces.tls_certificates_testing as tls_certificates_testing

JUJU_NETWORK_KEYS = {"egress-subnets", "ingress-address", "private-address"}
LIBID = tls_certificates._tls_certificates.LIBID


def test_local_provider():
    rel = tls_certificates_testing.relation_for_provider("foo")
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == "foo"
    assert rel.interface == "tls-certificates"
    # requests are made in unit mode by default
    assert not rel.remote_app_data
    assert 0 in rel.remote_units_data
    assert "certificate_signing_requests" in rel.remote_units_data[0]
    # certificates are delivered via app data unless response=False is passed
    assert rel.local_app_data
    assert "certificates" in rel.local_app_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.local_unit_data)


def test_local_provider_w_mode_app():
    rel = tls_certificates_testing.relation_for_provider("foo", mode=tls_certificates.Mode.APP)
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == "foo"
    assert rel.interface == "tls-certificates"
    # requests are made in app mode when specified
    assert "certificate_signing_requests" in rel.remote_app_data
    assert 0 in rel.remote_units_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.remote_units_data[0])
    # certificates are delivered via app data
    assert rel.local_app_data
    assert "certificates" in rel.local_app_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.local_unit_data)


def test_local_provider_w_response_false():
    rel = tls_certificates_testing.relation_for_provider("foo", response=False)
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == "foo"
    assert rel.interface == "tls-certificates"
    # requests are made in unit mode by default
    assert not rel.remote_app_data
    assert 0 in rel.remote_units_data
    assert "certificate_signing_requests" in rel.remote_units_data[0]
    # certificates are not provided with response=False
    assert not rel.local_app_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.local_unit_data)


def test_local_requirer():
    rel = tls_certificates_testing.relation_for_requirer("foo")
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == "foo"
    assert rel.interface == "tls-certificates"
    # requests are made in unit mode by default
    assert not rel.local_app_data
    assert "certificate_signing_requests" in rel.local_unit_data
    # certificates are delivered via app data unless response=False is passed
    assert rel.remote_app_data
    assert "certificates" in rel.remote_app_data
    assert 0 in rel.remote_units_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.remote_units_data[0])


def test_local_requirer_w_mode_app():
    rel = tls_certificates_testing.relation_for_requirer("foo", mode=tls_certificates.Mode.APP)
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == "foo"
    assert rel.interface == "tls-certificates"
    # requests are made in app mode when specified
    assert "certificate_signing_requests" in rel.local_app_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.local_unit_data)
    # certificates are delivered via app data unless response=False is passed
    assert rel.remote_app_data
    assert "certificates" in rel.remote_app_data
    assert 0 in rel.remote_units_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.remote_units_data[0])


def test_local_requirer_w_response_false():
    rel = tls_certificates_testing.relation_for_requirer("foo", response=False)
    assert isinstance(rel, testing.Relation)
    assert rel.endpoint == "foo"
    assert rel.interface == "tls-certificates"
    # requests are made in unit mode by default
    assert not rel.local_app_data
    assert "certificate_signing_requests" in rel.local_unit_data
    # certificates are not provided with response=False
    assert not rel.remote_app_data
    assert 0 in rel.remote_units_data
    assert all(k in JUJU_NETWORK_KEYS for k in rel.remote_units_data[0])


def test_private_key_secret():
    secret = tls_certificates_testing.private_key_secret("foo")
    assert isinstance(secret, testing.Secret)
    assert secret.owner == "unit"
    assert secret.label == f"{LIBID}-private-key-0-foo"
    assert secret.tracked_content == {
        "private-key": str(tls_certificates_testing.DEFAULT_PRIVATE_KEY)
    }


def test_private_key_secret_w_mode_app():
    secret = tls_certificates_testing.private_key_secret("foo", mode=tls_certificates.Mode.APP)
    assert secret.owner == "app"
    # the app label has no unit number, and an "-app-" infix distinguishing it from the
    # label older library versions used for a unit-owned secret
    assert secret.label == f"{LIBID}-private-key-app-foo"


def test_private_key_secret_w_unit_id():
    secret = tls_certificates_testing.private_key_secret("foo", unit_id=3)
    assert secret.label == f"{LIBID}-private-key-3-foo"


def test_private_key_secret_w_private_key():
    key = tls_certificates.PrivateKey.generate()
    assert key != tls_certificates_testing.DEFAULT_PRIVATE_KEY
    secret = tls_certificates_testing.private_key_secret("foo", private_key=key)
    assert secret.tracked_content == {"private-key": str(key)}


@pytest.mark.parametrize(
    ("mode", "unit_id"),
    [(tls_certificates.Mode.UNIT, 3), (tls_certificates.Mode.APP, 0)],
    ids=["unit", "app"],
)
def test_private_key_secret_label_matches_the_library(
    mode: typing.Literal[tls_certificates.Mode.UNIT, tls_certificates.Mode.APP],
    unit_id: int,
):
    """The label must be exactly what the library looks up, or the charm silently sees no key.

    Guards against the library changing `_get_private_key_secret_label` without this
    package following. The two are released in lockstep, so this test is the contract.
    """
    secret = tls_certificates_testing.private_key_secret("foo", mode=mode, unit_id=unit_id)
    # Call the library's own label derivation with a stand-in supplying the two
    # attributes it reads.
    stub = types.SimpleNamespace(relationship_name="foo", _get_unit_number=lambda: str(unit_id))
    expected = tls_certificates.TLSCertificatesRequiresV4._get_private_key_secret_label(
        stub,  # type: ignore[arg-type]
        mode,
    )
    assert secret.label == expected
