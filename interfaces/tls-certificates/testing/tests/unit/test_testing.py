# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import dataclasses
import datetime
import json
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


def test_local_requirer_w_denied_request():
    issued = tls_certificates.CertificateRequestAttributes(common_name="issued.example.com")
    refused = tls_certificates.CertificateRequestAttributes(common_name="denied.example.com")
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        certificate_requests=[
            issued,
            tls_certificates_testing.denied(
                refused,
                code=tls_certificates.CertificateRequestErrorCode.DOMAIN_NOT_ALLOWED,
                message="that domain is not allowed",
            ),
        ],
    )
    # both requests are in the requirer's databag -- the charm asked for both
    csrs = json.loads(rel.local_unit_data["certificate_signing_requests"])
    assert len(csrs) == 2
    # but only the issued one got a certificate; the denied one got an error
    certs = json.loads(rel.remote_app_data["certificates"])
    assert len(certs) == 1
    errors = json.loads(rel.remote_app_data["request_errors"])
    assert len(errors) == 1
    code = tls_certificates.CertificateRequestErrorCode.DOMAIN_NOT_ALLOWED
    assert errors[0]["error"]["code"] == code.value
    assert errors[0]["error"]["name"] == code.name
    assert errors[0]["error"]["message"] == "that domain is not allowed"
    # the error is attached to the denied request's CSR, not the issued one's
    assert errors[0]["csr"].strip() != certs[0]["certificate_signing_request"].strip()
    assert {errors[0]["csr"].strip(), certs[0]["certificate_signing_request"].strip()} == {
        c["certificate_signing_request"].strip() for c in csrs
    }


def test_local_requirer_w_denied_request_and_response_false():
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        certificate_requests=[
            tls_certificates_testing.denied(
                tls_certificates.CertificateRequestAttributes(common_name="example.com")
            )
        ],
        response=False,
    )
    # response=False means nothing answered yet, error outcomes included
    assert "certificate_signing_requests" in rel.local_unit_data
    assert not rel.remote_app_data


def test_local_provider_w_denied_request():
    issued = tls_certificates.CertificateRequestAttributes(common_name="issued.example.com")
    refused = tls_certificates.CertificateRequestAttributes(common_name="denied.example.com")
    rel = tls_certificates_testing.relation_for_provider(
        "foo",
        certificate_requests=[issued, tls_certificates_testing.denied(refused)],
    )
    # the remote requirer asked for both
    csrs = json.loads(rel.remote_units_data[0]["certificate_signing_requests"])
    assert len(csrs) == 2
    # this charm has answered one with a certificate and one with an error
    assert len(json.loads(rel.local_app_data["certificates"])) == 1
    errors = json.loads(rel.local_app_data["request_errors"])
    assert len(errors) == 1
    code = tls_certificates.CertificateRequestErrorCode.OTHER  # denied()'s default
    assert errors[0]["error"]["code"] == code.value


def test_local_requirer_w_renewing_request():
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        certificate_requests=[
            tls_certificates_testing.renewing(
                tls_certificates.CertificateRequestAttributes(common_name="example.com")
            )
        ],
    )
    cert = tls_certificates.Certificate.from_string(
        json.loads(rel.remote_app_data["certificates"])[0]["certificate"]
    )
    # past the library's renewal safety threshold, but not yet expired
    now = datetime.datetime.now(datetime.timezone.utc)
    start, end = cert.validity_start_time, cert.expiry_time
    safety_threshold = start + (end - start) * 0.95  # min(0.99, default 0.9 + 0.05)
    assert safety_threshold <= now < end


def test_local_requirer_w_expired_request():
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        certificate_requests=[
            tls_certificates_testing.expired(
                tls_certificates.CertificateRequestAttributes(common_name="example.com")
            )
        ],
    )
    cert = tls_certificates.Certificate.from_string(
        json.loads(rel.remote_app_data["certificates"])[0]["certificate"]
    )
    assert cert.expiry_time < datetime.datetime.now(datetime.timezone.utc)


def test_aged_certificates_still_chain_and_match():
    """Back-dating must not break the signature chain or the key binding."""
    request = tls_certificates.CertificateRequestAttributes(common_name="example.com")
    for wrapper in (tls_certificates_testing.renewing, tls_certificates_testing.expired):
        rel = tls_certificates_testing.relation_for_requirer(
            "foo", certificate_requests=[wrapper(request)]
        )
        published = json.loads(rel.remote_app_data["certificates"])[0]
        cert = tls_certificates.Certificate.from_string(published["certificate"])
        csr = tls_certificates.CertificateSigningRequest.from_string(
            published["certificate_signing_request"]
        )
        assert cert.matches_private_key(tls_certificates_testing.DEFAULT_PRIVATE_KEY)
        assert csr.matches_certificate(cert)


def test_local_requirer_w_revoked_request():
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        certificate_requests=[
            tls_certificates_testing.revoked(
                tls_certificates.CertificateRequestAttributes(common_name="example.com")
            )
        ],
    )
    # the certificate is published as usual, but flagged revoked
    certs = json.loads(rel.remote_app_data["certificates"])
    assert len(certs) == 1
    assert certs[0]["revoked"] is True
    # an ordinary request is not
    rel = tls_certificates_testing.relation_for_requirer("foo")
    certs = json.loads(rel.remote_app_data["certificates"])
    assert certs[0].get("revoked") in (None, False)


def test_published_certificates_carry_a_valid_chain():
    for rel in (
        tls_certificates_testing.relation_for_requirer("foo").remote_app_data,
        tls_certificates_testing.relation_for_provider("foo").local_app_data,
    ):
        published = json.loads(rel["certificates"])[0]
        chain = published["chain"]
        # leaf to root: the issued certificate, then the CA that signed it
        assert chain[0].strip() == published["certificate"].strip()
        assert chain[-1].strip() == published["ca"].strip()
        assert tls_certificates.chain_has_valid_order(chain)


def test_local_requirer_w_ca_request():
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        certificate_requests=[
            tls_certificates.CertificateRequestAttributes(common_name="example.com", is_ca=True)
        ],
    )
    # the requirer's databag flags the request as a CA request ...
    csrs = json.loads(rel.local_unit_data["certificate_signing_requests"])
    assert csrs[0]["ca"] is True
    # ... and the provider answered with a CA certificate
    published = json.loads(rel.remote_app_data["certificates"])[0]
    assert tls_certificates.Certificate.from_string(published["certificate"]).is_ca
    # while an ordinary request gets a leaf certificate
    rel = tls_certificates_testing.relation_for_requirer("foo")
    assert json.loads(rel.local_unit_data["certificate_signing_requests"])[0]["ca"] is False
    published = json.loads(rel.remote_app_data["certificates"])[0]
    assert not tls_certificates.Certificate.from_string(published["certificate"]).is_ca


def test_local_requirer_wo_capabilities():
    rel = tls_certificates_testing.relation_for_requirer("foo")
    # absent means "the provider has not advertised yet" -- not an empty object
    assert "capabilities" not in rel.remote_app_data


def test_local_requirer_w_capabilities():
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        capabilities=tls_certificates.ProviderCapabilities(supports_wildcard_dns=False),
    )
    published = json.loads(rel.remote_app_data["capabilities"])
    # advertised-as-unsupported (False) must survive as distinct from unspecified (None)
    assert published["supports_wildcard_dns"] is False


def test_local_requirer_w_capabilities_and_response_false():
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        capabilities=tls_certificates.ProviderCapabilities(),
        response=False,
    )
    # a provider can advertise capabilities before it answers any requests
    assert "certificates" not in rel.remote_app_data
    assert "capabilities" in rel.remote_app_data


def test_respond_to_requests():
    rel = tls_certificates_testing.relation_for_requirer("foo", response=False)
    answered = tls_certificates_testing.respond_to_requests(rel)
    # a copy with the same identity, the requirer's side untouched
    assert answered is not rel
    assert (answered.id, answered.endpoint, answered.interface) == (
        rel.id,
        rel.endpoint,
        rel.interface,
    )
    assert answered.local_unit_data == rel.local_unit_data
    # and a certificate answering each CSR the requirer had on the relation
    csrs = json.loads(rel.local_unit_data["certificate_signing_requests"])
    certs = json.loads(answered.remote_app_data["certificates"])
    assert {c["certificate_signing_request"].strip() for c in certs} == {
        r["certificate_signing_request"].strip() for r in csrs
    }


def test_respond_to_requests_w_mode_app():
    rel = tls_certificates_testing.relation_for_requirer(
        "foo", mode=tls_certificates.Mode.APP, response=False
    )
    answered = tls_certificates_testing.respond_to_requests(rel)
    assert answered.local_app_data == rel.local_app_data
    assert "certificates" in answered.remote_app_data


def test_respond_to_requests_answers_ca_requests_with_ca_certificates():
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        certificate_requests=[
            tls_certificates.CertificateRequestAttributes(common_name="example.com", is_ca=True)
        ],
        response=False,
    )
    answered = tls_certificates_testing.respond_to_requests(rel)
    published = json.loads(answered.remote_app_data["certificates"])[0]
    assert tls_certificates.Certificate.from_string(published["certificate"]).is_ca


def test_respond_to_requests_wo_requests():
    rel = testing.Relation("foo", interface="tls-certificates")
    answered = tls_certificates_testing.respond_to_requests(rel)
    # no requests, so nothing to answer
    assert not answered.remote_app_data


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


def test_certificate_request_alias_covers_every_outcome():
    """The public alias must name everything ``certificate_requests`` accepts.

    Without it a caller can't annotate a mixed list, since the wrapper types are private.
    """
    request = tls_certificates.CertificateRequestAttributes(common_name="example.com")
    requests: list[tls_certificates_testing.CertificateRequest] = [
        request,
        tls_certificates_testing.denied(request),
        tls_certificates_testing.renewing(request),
        tls_certificates_testing.expired(request),
        tls_certificates_testing.revoked(request),
    ]
    assert set(typing.get_args(tls_certificates_testing.CertificateRequest)) == {
        type(item) for item in requests
    }


@pytest.mark.parametrize("renewal_relative_time", [0.51, 0.9, 0.95, 1.0])
def test_renewing_is_due_for_every_legal_renewal_relative_time(renewal_relative_time: float):
    """``renewing`` must back-date past the library's threshold without being told it.

    The library validates ``0.5 < renewal_relative_time <= 1.0`` and caps the threshold it
    derives from it, so one back-dating covers every value a charm can legally pass. That
    is why ``renewing`` takes no argument -- there is no coupling here to get wrong.
    """
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        certificate_requests=[
            tls_certificates_testing.renewing(
                tls_certificates.CertificateRequestAttributes(common_name="example.com")
            )
        ],
    )
    cert = tls_certificates.Certificate.from_string(
        json.loads(rel.remote_app_data["certificates"])[0]["certificate"]
    )
    threshold = tls_certificates._tls_certificates._renewal_safety_threshold(renewal_relative_time)
    now = datetime.datetime.now(datetime.timezone.utc)
    start, end = cert.validity_start_time, cert.expiry_time
    assert start + (end - start) * threshold <= now < end


def test_respond_to_requests_keeps_advertised_capabilities():
    """Answering requests must not un-advertise what the provider already said."""
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        capabilities=tls_certificates.ProviderCapabilities(supports_ip_sans=True),
        response=False,
    )
    answered = tls_certificates_testing.respond_to_requests(rel)
    assert "certificates" in answered.remote_app_data
    assert json.loads(answered.remote_app_data["capabilities"])["supports_ip_sans"] is True


def test_respond_to_requests_keeps_denied_requests_denied():
    """A request the provider refused must not quietly become an issued certificate."""
    issued = tls_certificates.CertificateRequestAttributes(common_name="issued.example.com")
    refused = tls_certificates.CertificateRequestAttributes(common_name="denied.example.com")
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        certificate_requests=[issued, tls_certificates_testing.denied(refused)],
    )
    answered = tls_certificates_testing.respond_to_requests(rel)
    certs = json.loads(answered.remote_app_data["certificates"])
    errors = json.loads(answered.remote_app_data["request_errors"])
    assert len(certs) == 1
    assert len(errors) == 1
    denied_csr = tls_certificates.CertificateSigningRequest.from_string(errors[0]["csr"])
    assert denied_csr.common_name == refused.common_name


def test_respond_to_requests_keeps_existing_certificates_as_they_are():
    """Revoked and back-dated certificates survive; they are answers, not gaps."""
    request = tls_certificates.CertificateRequestAttributes(common_name="example.com")
    for wrapper in (tls_certificates_testing.revoked, tls_certificates_testing.expired):
        rel = tls_certificates_testing.relation_for_requirer(
            "foo", certificate_requests=[wrapper(request)]
        )
        answered = tls_certificates_testing.respond_to_requests(rel)
        assert answered.remote_app_data["certificates"] == rel.remote_app_data["certificates"]


def test_respond_to_requests_is_idempotent():
    rel = tls_certificates_testing.relation_for_requirer("foo", response=False)
    once = tls_certificates_testing.respond_to_requests(rel)
    twice = tls_certificates_testing.respond_to_requests(once)
    assert twice.remote_app_data == once.remote_app_data


def test_respond_to_requests_drops_answers_to_withdrawn_requests():
    """The provider library removes certificates whose CSR is gone; so does this."""
    rel = tls_certificates_testing.relation_for_requirer("foo")
    assert json.loads(rel.remote_app_data["certificates"])
    withdrawn = dataclasses.replace(rel, local_unit_data={"certificate_signing_requests": "[]"})
    answered = tls_certificates_testing.respond_to_requests(withdrawn)
    assert not answered.remote_app_data


def test_respond_to_requests_rejects_a_provider_relation():
    """A provider charm's relation must raise, not silently lose the requests on it.

    The requests live on the remote side there, and the databag this function writes is
    the one holding them -- so answering would discard the simulated requirer's requests.
    """
    for mode in (tls_certificates.Mode.APP, tls_certificates.Mode.UNIT):
        rel = tls_certificates_testing.relation_for_provider("foo", mode=mode)
        with pytest.raises(ValueError, match="provider charm"):
            tls_certificates_testing.respond_to_requests(rel)


def test_respond_to_requests_treats_unreadable_provider_data_as_empty():
    """A relation whose provider databag isn't valid interface data still gets answered."""
    rel = tls_certificates_testing.relation_for_requirer("foo", response=False)
    rel = dataclasses.replace(rel, remote_app_data={"certificates": "not json"})
    answered = tls_certificates_testing.respond_to_requests(rel)
    csrs = json.loads(rel.local_unit_data["certificate_signing_requests"])
    assert len(json.loads(answered.remote_app_data["certificates"])) == len(csrs)


def test_local_provider_w_capabilities():
    """A provider charm can start with capabilities already in its own databag."""
    rel = tls_certificates_testing.relation_for_provider(
        "foo", capabilities=tls_certificates.ProviderCapabilities(provider_type="acme")
    )
    assert json.loads(rel.local_app_data["capabilities"])["provider_type"] == "acme"
    assert "certificates" in rel.local_app_data


def test_local_provider_w_capabilities_and_response_false():
    rel = tls_certificates_testing.relation_for_provider(
        "foo", capabilities=tls_certificates.ProviderCapabilities(), response=False
    )
    assert "capabilities" in rel.local_app_data
    assert "certificates" not in rel.local_app_data


def test_remote_app_name():
    for rel in (
        tls_certificates_testing.relation_for_requirer("foo", remote_app_name="ca"),
        tls_certificates_testing.relation_for_provider("foo", remote_app_name="ca"),
    ):
        assert rel.remote_app_name == "ca"
    # and the ops.testing default is unchanged when it isn't given
    assert tls_certificates_testing.relation_for_requirer("foo").remote_app_name == "remote"


def test_local_provider_w_several_remote_units():
    """Each requirer unit makes its own requests, and the provider answers all of them."""
    rel = tls_certificates_testing.relation_for_provider("foo", remote_unit_ids=[0, 1, 2])
    assert set(rel.remote_units_data) == {0, 1, 2}
    csrs = [
        entry["certificate_signing_request"]
        for databag in rel.remote_units_data.values()
        for entry in json.loads(databag["certificate_signing_requests"])
    ]
    # one request each, and no two units sent the same one
    assert len(csrs) == 3
    assert len(set(csrs)) == 3
    certs = json.loads(rel.local_app_data["certificates"])
    assert {c["certificate_signing_request"].strip() for c in certs} == {c.strip() for c in csrs}


def test_local_provider_w_several_remote_units_in_mode_app():
    """In APP mode the requests are app-scoped, but the extra units still exist."""
    rel = tls_certificates_testing.relation_for_provider(
        "foo", mode=tls_certificates.Mode.APP, remote_unit_ids=[0, 1]
    )
    assert set(rel.remote_units_data) == {0, 1}
    assert all(not databag for databag in rel.remote_units_data.values())
    assert "certificate_signing_requests" in rel.remote_app_data


def test_local_requirer_w_several_remote_units():
    """The provider writes only app data, so its extra units are there but empty."""
    rel = tls_certificates_testing.relation_for_requirer("foo", remote_unit_ids=[0, 1])
    assert set(rel.remote_units_data) == {0, 1}
    assert all(not databag for databag in rel.remote_units_data.values())
    assert "certificates" in rel.remote_app_data


def test_local_requirer_w_mode_app_and_unit():
    """Requests are split across the two databags, and both scopes get certificates."""
    app = tls_certificates.CertificateRequestAttributes(common_name="app.example.com")
    unit = tls_certificates.CertificateRequestAttributes(common_name="unit.example.com")
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        mode=tls_certificates.Mode.APP_AND_UNIT,
        certificate_requests_by_mode={
            tls_certificates.Mode.APP: [app],
            tls_certificates.Mode.UNIT: [unit],
        },
    )
    app_csrs = json.loads(rel.local_app_data["certificate_signing_requests"])
    unit_csrs = json.loads(rel.local_unit_data["certificate_signing_requests"])
    assert _common_names(app_csrs) == {app.common_name}
    assert _common_names(unit_csrs) == {unit.common_name}
    # the provider databag is app-scoped, so it answers both scopes together
    certs = json.loads(rel.remote_app_data["certificates"])
    assert {
        tls_certificates.Certificate.from_string(c["certificate"]).common_name for c in certs
    } == {app.common_name, unit.common_name}


def test_local_provider_w_mode_app_and_unit():
    app = tls_certificates.CertificateRequestAttributes(common_name="app.example.com")
    unit = tls_certificates.CertificateRequestAttributes(common_name="unit.example.com")
    rel = tls_certificates_testing.relation_for_provider(
        "foo",
        mode=tls_certificates.Mode.APP_AND_UNIT,
        certificate_requests_by_mode={
            tls_certificates.Mode.APP: [app],
            tls_certificates.Mode.UNIT: [unit],
        },
        remote_unit_ids=[0, 1],
    )
    assert _common_names(json.loads(rel.remote_app_data["certificate_signing_requests"])) == {
        app.common_name
    }
    for databag in rel.remote_units_data.values():
        assert _common_names(json.loads(databag["certificate_signing_requests"])) == {
            unit.common_name
        }
    # one app request plus one per unit
    assert len(json.loads(rel.local_app_data["certificates"])) == 3


def test_mode_app_and_unit_defaults_to_a_request_per_scope():
    rel = tls_certificates_testing.relation_for_requirer(
        "foo", mode=tls_certificates.Mode.APP_AND_UNIT
    )
    app_csrs = json.loads(rel.local_app_data["certificate_signing_requests"])
    unit_csrs = json.loads(rel.local_unit_data["certificate_signing_requests"])
    # distinct, as the library requires of APP_AND_UNIT requests
    assert _common_names(app_csrs).isdisjoint(_common_names(unit_csrs))


def test_mode_app_and_unit_accepts_a_single_scope():
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        mode=tls_certificates.Mode.APP_AND_UNIT,
        certificate_requests_by_mode={
            tls_certificates.Mode.UNIT: [
                tls_certificates.CertificateRequestAttributes(common_name="unit.example.com")
            ]
        },
    )
    assert "certificate_signing_requests" in rel.local_unit_data
    assert not rel.local_app_data


def test_mode_app_and_unit_takes_wrapped_requests():
    rel = tls_certificates_testing.relation_for_requirer(
        "foo",
        mode=tls_certificates.Mode.APP_AND_UNIT,
        certificate_requests_by_mode={
            tls_certificates.Mode.APP: [
                tls_certificates_testing.denied(
                    tls_certificates.CertificateRequestAttributes(common_name="app.example.com")
                )
            ],
            tls_certificates.Mode.UNIT: [
                tls_certificates.CertificateRequestAttributes(common_name="unit.example.com")
            ],
        },
    )
    assert len(json.loads(rel.remote_app_data["request_errors"])) == 1
    assert len(json.loads(rel.remote_app_data["certificates"])) == 1


@pytest.mark.parametrize(
    "relation",
    [
        tls_certificates_testing.relation_for_requirer,
        tls_certificates_testing.relation_for_provider,
    ],
    ids=["requirer", "provider"],
)
def test_request_arguments_are_validated(relation: typing.Callable[..., testing.Relation]):
    """Mirror the pairing rules the library enforces on the charm's own arguments."""
    request = tls_certificates.CertificateRequestAttributes(common_name="example.com")
    by_mode = {tls_certificates.Mode.UNIT: [request]}
    with pytest.raises(ValueError, match="mutually exclusive"):
        relation("foo", certificate_requests=[request], certificate_requests_by_mode=by_mode)
    with pytest.raises(ValueError, match=r"only valid when mode is Mode\.APP_AND_UNIT"):
        relation("foo", certificate_requests_by_mode=by_mode)
    with pytest.raises(ValueError, match=r"must not be given when mode is Mode\.APP_AND_UNIT"):
        relation(
            "foo",
            mode=tls_certificates.Mode.APP_AND_UNIT,
            certificate_requests=[request],
        )
    with pytest.raises(ValueError, match=r"keys must be Mode\.APP or Mode\.UNIT"):
        relation(
            "foo",
            mode=tls_certificates.Mode.APP_AND_UNIT,
            certificate_requests_by_mode={tls_certificates.Mode.APP_AND_UNIT: [request]},
        )


def test_private_key_secret_rejects_mode_app_and_unit():
    """One secret per scope, so the caller has to say which -- rather than silently get one."""
    with pytest.raises(ValueError, match=r"once with mode=Mode\.APP"):
        tls_certificates_testing.private_key_secret("foo", mode=tls_certificates.Mode.APP_AND_UNIT)


def _common_names(entries: list[dict[str, str]]) -> set[str]:
    return {
        tls_certificates.CertificateSigningRequest.from_string(
            entry["certificate_signing_request"]
        ).common_name
        for entry in entries
    }
