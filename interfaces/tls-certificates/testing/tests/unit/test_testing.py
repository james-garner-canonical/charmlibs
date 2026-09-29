# Copyright 2026 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the stand-in charms' own contract, as OP093 specifies it.

These read relation data directly, which a charm test should never do -- the point of the
package is that charm tests don't have to. Here it is the subject.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import typing

import ops
import ops.testing
import pytest

import provider_charm
import requirer_charm
from charmlibs.interfaces import tls_certificates as tls_certificates
from charmlibs.interfaces import tls_certificates_testing as tls_certificates_testing

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

    import _juju

JUJU_NETWORK_KEYS = {"egress-subnets", "ingress-address", "private-address"}
_Scope: typing.TypeAlias = "typing.Literal[tls_certificates.Mode.APP, tls_certificates.Mode.UNIT]"


# ---------------------------------------------------------------- construction & identity


def test_provider_and_requirer_are_callable_with_no_arguments():
    """OP093: both must be callable with no arguments, defaulting to the happy path."""
    assert tls_certificates_testing.provider() is not None
    assert tls_certificates_testing.requirer() is not None


@pytest.mark.parametrize(
    "function", [tls_certificates_testing.provider, tls_certificates_testing.requirer]
)
def test_every_argument_is_keyword_only(function: typing.Callable[..., typing.Any]):
    """OP093: all arguments must be optional and keyword-only."""
    with pytest.raises(TypeError):
        function("certificates")


@pytest.mark.parametrize(
    ("function", "name"),
    [
        (tls_certificates_testing.provider, "tls-certificates-provider"),
        (tls_certificates_testing.requirer, "tls-certificates-requirer"),
    ],
)
def test_the_stand_ins_metadata(function: typing.Callable[..., typing.Any], name: str):
    """OP093: meta names the library and role, and declares exactly one endpoint."""
    data = function()
    assert data.meta["name"] == name
    endpoints = {
        endpoint: spec
        for role in ("provides", "requires")
        for endpoint, spec in data.meta.get(role, {}).items()
    }
    assert endpoints == {"certificates": {"interface": "tls-certificates"}}


@pytest.mark.parametrize(
    "function", [tls_certificates_testing.provider, tls_certificates_testing.requirer]
)
def test_the_result_is_a_charm_data(function: typing.Callable[..., typing.Any]):
    """The shape OP089 specifies: charm type, metadata, and the package's mocking."""
    data: tls_certificates_testing.CharmData[ops.CharmBase] = function()
    assert isinstance(data, tls_certificates_testing.CharmData)
    assert issubclass(data.charm_type, ops.CharmBase)
    assert data.mocking is tls_certificates_testing.mocked


@pytest.mark.parametrize(
    "function", [tls_certificates_testing.provider, tls_certificates_testing.requirer]
)
def test_the_result_is_immutable_and_reusable(function: typing.Callable[..., typing.Any]):
    """OP093: a single result may be deployed any number of times, behaving identically."""
    data = function()
    assert dataclasses.is_dataclass(data)
    with pytest.raises(dataclasses.FrozenInstanceError):
        data.meta = {}  # pyright: ignore[reportAttributeAccessIssue]
    # Two calls with equal arguments produce distinct but interchangeable results.
    assert function() is not function()


def test_the_stand_in_charm_classes_are_private():
    """Nothing a test does with a stand-in needs the concrete class."""
    for data in (tls_certificates_testing.provider(), tls_certificates_testing.requirer()):
        assert data.charm_type.__name__ in ("_ProviderCharm", "_RequirerCharm")
        assert (
            data.charm_type.__module__ == "charmlibs.interfaces.tls_certificates_testing._testing"
        )
        assert not hasattr(tls_certificates_testing, data.charm_type.__name__)


def test_requirer_request_arguments_are_validated():
    """Mirror the pairing rules the library enforces on a real requirer's own arguments.

    The annotations already rule some of these out, but a caller without a type checker can
    still pass them, so they must be checked at runtime too -- APP_AND_UNIT as a key would
    otherwise reach the databag. OP093: invalid arguments raise ValueError at call time.
    """
    request = tls_certificates.CertificateRequestAttributes(common_name="example.com")
    by_mode: dict[_Scope, list[tls_certificates.CertificateRequestAttributes]] = {
        tls_certificates.Mode.UNIT: [request]
    }
    function = tls_certificates_testing.requirer
    with pytest.raises(ValueError, match="mutually exclusive"):
        function(certificate_requests=[request], certificate_requests_by_mode=by_mode)
    with pytest.raises(ValueError, match=r"only valid when mode is Mode\.APP_AND_UNIT"):
        function(certificate_requests_by_mode=by_mode)
    with pytest.raises(ValueError, match=r"must not be given when mode is Mode\.APP_AND_UNIT"):
        function(
            mode=tls_certificates.Mode.APP_AND_UNIT,
            certificate_requests=[request],
        )
    with pytest.raises(ValueError, match=r"keys must be Mode\.APP or Mode\.UNIT"):
        function(
            mode=tls_certificates.Mode.APP_AND_UNIT,
            certificate_requests_by_mode={  # pyright: ignore[reportArgumentType]
                tls_certificates.Mode.APP_AND_UNIT: [request]
            },
        )
    with pytest.raises(ValueError, match="mode must be"):
        function(mode="unit")  # pyright: ignore[reportArgumentType]


def test_requirer_normalises_its_request_iterables(juju: _juju.Juju, mocked: None):
    """A stand-in is deployed any number of times, so a one-shot iterator must not be
    consumed once.
    """
    requests = [tls_certificates.CertificateRequestAttributes(common_name="example.com")]
    data = tls_certificates_testing.requirer(certificate_requests=iter(requests))
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    first = juju.deploy(data, app="first")
    juju.integrate(app, first)
    second = juju.deploy(data, app="second")
    juju.integrate(app, second)
    juju.settle()
    for stand_in in (first, second):
        (relation,) = _relations(stand_in.leader.state)
        assert _common_names(relation.local_unit_data) == {"example.com"}


# ------------------------------------------------------------------------------- Outcome

_Outcome = tls_certificates_testing.Outcome
"""Alias, because the assertions below compare several outcomes per line."""


def test_outcome_no_argument_constructors_are_singletons():
    """Outcome.issued() is Outcome.issued(): no reason for two instances to ever differ."""
    assert tls_certificates_testing.Outcome.issued() is tls_certificates_testing.Outcome.issued()
    assert (
        tls_certificates_testing.Outcome.renewing() is tls_certificates_testing.Outcome.renewing()
    )
    assert tls_certificates_testing.Outcome.expired() is tls_certificates_testing.Outcome.expired()
    assert tls_certificates_testing.Outcome.revoked() is tls_certificates_testing.Outcome.revoked()


def test_outcome_denied_constructs_fresh_each_call():
    """Unlike the others, denied() carries per-call arguments, so it can't be a singleton."""
    assert (
        tls_certificates_testing.Outcome.denied() is not tls_certificates_testing.Outcome.denied()
    )


def test_outcome_equality():
    assert _Outcome.denied() == _Outcome.denied()
    assert _Outcome.issued() == _Outcome.issued()
    assert _Outcome.issued() != _Outcome.denied()
    assert _Outcome.issued() != _Outcome.renewing()
    assert _Outcome.denied(
        code=tls_certificates.CertificateRequestErrorCode.DOMAIN_NOT_ALLOWED
    ) != _Outcome.denied(code=tls_certificates.CertificateRequestErrorCode.IP_NOT_ALLOWED)
    assert _Outcome.denied(message="a") != _Outcome.denied(message="b")
    assert _Outcome.denied(reason="a") != _Outcome.denied(reason="b")
    assert _Outcome.issued() != object()
    assert _Outcome.issued().__eq__(object()) is NotImplemented


def test_outcome_hash_is_consistent_with_equality():
    assert hash(_Outcome.denied()) == hash(_Outcome.denied())
    assert hash(_Outcome.issued()) == hash(_Outcome.issued())
    seen = {_Outcome.issued(), _Outcome.denied(), _Outcome.denied()}
    assert seen == {_Outcome.issued(), _Outcome.denied()}


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (tls_certificates_testing.Outcome.issued(), "Outcome.issued()"),
        (tls_certificates_testing.Outcome.renewing(), "Outcome.renewing()"),
        (tls_certificates_testing.Outcome.expired(), "Outcome.expired()"),
        (tls_certificates_testing.Outcome.revoked(), "Outcome.revoked()"),
        (tls_certificates_testing.Outcome.denied(), "Outcome.denied()"),
        (
            tls_certificates_testing.Outcome.denied(
                code=tls_certificates.CertificateRequestErrorCode.SERVER_NOT_AVAILABLE,
                message="the server is unavailable",
                reason="maintenance",
            ),
            "Outcome.denied(code=CertificateRequestErrorCode.SERVER_NOT_AVAILABLE, "
            "message='the server is unavailable', reason='maintenance')",
        ),
    ],
    ids=["issued", "renewing", "expired", "revoked", "denied-defaults", "denied-customised"],
)
def test_outcome_repr(outcome: tls_certificates_testing.Outcome, expected: str):
    assert repr(outcome) == expected


@pytest.mark.parametrize(
    "outcome",
    [
        tls_certificates_testing.Outcome.issued(),
        tls_certificates_testing.Outcome.renewing(),
        tls_certificates_testing.Outcome.expired(),
        tls_certificates_testing.Outcome.revoked(),
    ],
    ids=["issued", "renewing", "expired", "revoked"],
)
def test_outcome_fields_are_none_for_every_non_denied_outcome(
    outcome: tls_certificates_testing.Outcome,
):
    assert outcome.code is None
    assert outcome.message is None
    assert outcome.reason is None


def test_outcome_denied_fields_are_readable():
    outcome = tls_certificates_testing.Outcome.denied(
        code=tls_certificates.CertificateRequestErrorCode.WILDCARD_NOT_ALLOWED,
        message="no wildcards",
        reason="policy",
    )
    assert outcome.code is tls_certificates.CertificateRequestErrorCode.WILDCARD_NOT_ALLOWED
    assert outcome.message == "no wildcards"
    assert outcome.reason == "policy"


# ------------------------------------------------- the stand-in provider: what it writes


def test_provider_derives_its_answer_from_what_the_charm_published(juju: _juju.Juju, mocked: None):
    """The conformance test OP093 requires: two charms asking for different things.

    A provider that ignored the charm's relation data and wrote canned values would satisfy
    every other clause of the spec while reintroducing exactly the silent mismatches the
    package exists to prevent. This is the one property that can't be checked by reading a
    signature.
    """
    first = [tls_certificates.CertificateRequestAttributes(common_name="first.example.com")]
    second = [
        tls_certificates.CertificateRequestAttributes(common_name="second.example.com"),
        tls_certificates.CertificateRequestAttributes(common_name="third.example.com"),
    ]
    ca = juju.deploy(tls_certificates_testing.provider())
    published: list[set[str]] = []
    for name, requests in (("first", first), ("second", second)):
        app = juju.deploy(_charm_requesting(requests), app=name, meta=requirer_charm.META)
        juju.integrate(app, ca)
        juju.settle()
        (relation,) = (r for r in _relations(ca.leader.state) if r.remote_app_name == name)
        certificates = json.loads(relation.local_app_data["certificates"])
        published.append({
            tls_certificates.Certificate.from_string(c["certificate"]).common_name
            for c in certificates
        })
    assert published[0] == {"first.example.com"}
    assert published[1] == {"second.example.com", "third.example.com"}
    assert published[0] != published[1]


def test_provider_reconciles_when_the_charm_changes_what_it_asks_for(
    juju: _juju.Juju, mocked: None
):
    """The other conformance test OP093 requires: the answer to the old request is gone.

    The charm rotates its key, which withdraws its requests and publishes new ones; the
    stand-in drops the answers to the withdrawn requests, which is what the real provider's
    library does.
    """
    app = juju.deploy(requirer_charm.RotatingRequirerCharm, meta=requirer_charm.ROTATING_META)
    ca = juju.deploy(tls_certificates_testing.provider())
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _relations(ca.leader.state)
    answered = {
        entry["certificate_signing_request"]
        for entry in json.loads(relation.local_app_data["certificates"])
    }
    assert answered
    # The charm rotates: old requests withdrawn, new ones sent.
    juju.dispatch(app.leader, "action:rotate-key")
    juju.settle()
    (relation,) = _relations(ca.leader.state)
    now = {
        entry["certificate_signing_request"]
        for entry in json.loads(relation.local_app_data["certificates"])
    }
    assert now
    assert now.isdisjoint(answered)  # the old answers are gone


def test_provider_publishes_a_real_chain(juju: _juju.Juju, mocked: None):
    """Leaf to root, signed by a genuine CA, so chain verification succeeds."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(tls_certificates_testing.provider())
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _relations(ca.leader.state)
    for entry in json.loads(relation.local_app_data["certificates"]):
        chain = entry["chain"]
        assert chain[0].strip() == entry["certificate"].strip()
        assert chain[-1].strip() == entry["ca"].strip()
        assert tls_certificates.chain_has_valid_order(chain)


def test_provider_answers_a_ca_request_with_a_ca_certificate(juju: _juju.Juju, mocked: None):
    """The library matches on both the databag's ca flag and BasicConstraints."""
    requests = [
        tls_certificates.CertificateRequestAttributes(common_name="ca.example.com", is_ca=True)
    ]
    app = juju.deploy(_charm_requesting(requests), meta=requirer_charm.META)
    ca = juju.deploy(tls_certificates_testing.provider())
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _relations(ca.leader.state)
    entry = json.loads(relation.local_app_data["certificates"])[0]
    assert tls_certificates.Certificate.from_string(entry["certificate"]).is_ca


def test_a_re_request_is_distinguishable_from_the_request_it_replaces(
    juju: _juju.Juju, mocked: None
):
    """The wire-format property that every renewal test rests on.

    The library tells requests apart by the unique identifier in the subject name, and
    ``mocked`` replaces that identifier with a sequence rather than a constant. Were it ever
    a constant, a re-request would be byte-identical to the request it replaces: the provider
    would see a request it had already answered, keep the stale certificate, and every
    renewal test would still pass while exercising nothing. This is the guard for that.
    """
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(
        tls_certificates_testing.provider(outcome=tls_certificates_testing.Outcome.renewing())
    )
    juju.integrate(app, ca)
    juju.settle()
    # The renewal completed, so the charm's current requests are the re-requests, and the
    # stand-in's answers are to those -- distinct from the stale first answers, which the
    # stand-in dropped when the requests were withdrawn.
    (relation,) = _relations(ca.leader.state)
    answered = {
        entry["certificate_signing_request"]
        for entry in json.loads(relation.local_app_data["certificates"])
    }
    requested = {
        entry["certificate_signing_request"]
        for databag in (relation.remote_app_data, *relation.remote_units_data.values())
        for entry in json.loads(databag.get("certificate_signing_requests", "[]"))
    }
    assert answered
    assert answered == requested  # every current request is answered ...
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    # ... and the certificates are fresh, not the stale first issue.
    now = datetime.datetime.now(datetime.timezone.utc)
    for certificate in assigned:
        start, end = (
            certificate.certificate.validity_start_time,
            certificate.certificate.expiry_time,
        )
        assert now < start + (end - start) * 0.5


def test_outcome_denied(juju: _juju.Juju, mocked: None):
    requests = [tls_certificates.CertificateRequestAttributes(common_name="example.com")]
    app = juju.deploy(_charm_requesting(requests), meta=requirer_charm.META)
    ca = juju.deploy(
        tls_certificates_testing.provider(
            outcome=tls_certificates_testing.Outcome.denied(
                code=tls_certificates.CertificateRequestErrorCode.DOMAIN_NOT_ALLOWED,
                message="that domain is not allowed",
                reason="policy",
            )
        )
    )
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _relations(ca.leader.state)
    databag = relation.local_app_data
    # The request is still in the charm's databag -- it asked -- but there's no certificate.
    assert "certificates" not in databag
    errors = json.loads(databag["request_errors"])
    assert len(errors) == 1
    code = tls_certificates.CertificateRequestErrorCode.DOMAIN_NOT_ALLOWED
    assert errors[0]["error"]["code"] == code.value
    assert errors[0]["error"]["name"] == code.name
    assert errors[0]["error"]["message"] == "that domain is not allowed"
    assert errors[0]["error"]["reason"] == "policy"


def test_outcome_denied_defaults(juju: _juju.Juju, mocked: None):
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(
        tls_certificates_testing.provider(outcome=tls_certificates_testing.Outcome.denied())
    )
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _relations(ca.leader.state)
    errors = json.loads(relation.local_app_data["request_errors"])
    code = tls_certificates.CertificateRequestErrorCode.OTHER
    assert all(e["error"]["code"] == code.value for e in errors)


def test_outcome_callable_selects_per_request(juju: _juju.Juju, mocked: None):
    """Mixed outcomes in one relation: a provider that refuses one domain serves the others."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(
        tls_certificates_testing.provider(
            outcome=lambda request: (
                tls_certificates_testing.Outcome.denied()
                if request.common_name.startswith("egg")
                else tls_certificates_testing.Outcome.issued()
            )
        )
    )
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _relations(ca.leader.state)
    databag = relation.local_app_data
    issued = {
        tls_certificates.Certificate.from_string(c["certificate"]).common_name
        for c in json.loads(databag["certificates"])
    }
    denied = {
        tls_certificates.CertificateSigningRequest.from_string(e["csr"]).common_name
        for e in json.loads(databag["request_errors"])
    }
    assert issued == {"example.com"}
    assert denied == {"eggsample.com"}


def test_outcome_callable_receives_the_charms_attributes(juju: _juju.Juju, mocked: None):
    """Reconstructed from the wire, so the callable selects on the request not the format."""
    seen: list[tls_certificates.CertificateRequestAttributes] = []

    def choose(
        request: tls_certificates.CertificateRequestAttributes,
    ) -> tls_certificates_testing.Outcome:
        seen.append(request)
        return tls_certificates_testing.Outcome.issued()

    requests = [
        tls_certificates.CertificateRequestAttributes(
            common_name="example.com", sans_dns={"a.example.com"}, organization="Canonical"
        )
    ]
    app = juju.deploy(_charm_requesting(requests), meta=requirer_charm.META)
    ca = juju.deploy(tls_certificates_testing.provider(outcome=choose))
    juju.integrate(app, ca)
    juju.settle()
    assert len(seen) == 1
    assert seen[0].common_name == "example.com"
    assert seen[0].sans_dns == {"a.example.com"}
    assert seen[0].organization == "Canonical"


def test_outcome_callable_must_return_an_outcome(juju: _juju.Juju, mocked: None):
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(
        tls_certificates_testing.provider(
            outcome=lambda _: "issued",  # pyright: ignore[reportArgumentType]
        )
    )
    juju.integrate(app, ca)
    # The stand-in raises inside its own dispatch, which ops.testing reports as an
    # uncaught charm error; the TypeError is the cause.
    with pytest.raises(ops.testing.errors.UncaughtCharmError) as excinfo:
        juju.settle()
    assert isinstance(excinfo.value.__cause__, TypeError)
    assert "not a tls_certificates_testing.Outcome" in str(excinfo.value.__cause__)


def test_outcome_renewing_is_past_the_libraries_threshold(juju: _juju.Juju, mocked: None):
    certificate = _first_certificate(
        juju,
        tls_certificates_testing.provider(outcome=tls_certificates_testing.Outcome.renewing()),
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    start, end = certificate.validity_start_time, certificate.expiry_time
    # min(0.99, default 0.9 + 0.05); past the threshold, but not yet expired.
    threshold = start + (end - start) * 0.95
    assert threshold <= now < end


@pytest.mark.parametrize("renewal_relative_time", [0.51, 0.9, 0.95, 1.0])
def test_outcome_renewing_covers_every_legal_renewal_relative_time(
    renewal_relative_time: float, juju: _juju.Juju, mocked: None
):
    """No coupling to the charm's renewal_relative_time, because the library caps it.

    That is why there is no argument here for the test author to get silently wrong.
    """
    from charmlibs.interfaces.tls_certificates import _tls_certificates as internal

    certificate = _first_certificate(
        juju,
        tls_certificates_testing.provider(outcome=tls_certificates_testing.Outcome.renewing()),
    )
    threshold = internal._renewal_safety_threshold(renewal_relative_time)
    now = datetime.datetime.now(datetime.timezone.utc)
    start, end = certificate.validity_start_time, certificate.expiry_time
    assert start + (end - start) * threshold <= now < end


def test_outcome_expired(juju: _juju.Juju, mocked: None):
    certificate = _one_certificate(
        juju, tls_certificates_testing.provider(outcome=tls_certificates_testing.Outcome.expired())
    )
    assert certificate.expiry_time < datetime.datetime.now(datetime.timezone.utc)


@pytest.mark.parametrize(
    "outcome",
    [
        tls_certificates_testing.Outcome.renewing(),
        tls_certificates_testing.Outcome.expired(),
    ],
    ids=["renewing", "expired"],
)
def test_back_dating_keeps_the_chain_and_the_key_binding(
    outcome: tls_certificates_testing.Outcome, juju: _juju.Juju, mocked: None
):
    """Back-dating rebuilds the certificate by hand, so this is worth checking.

    Checked on the first thing the stand-in published, which for ``renewing`` is the
    back-dated certificate rather than the fresh one it issues after the re-request.
    """
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(tls_certificates_testing.provider(outcome=outcome))
    juju.integrate(app, ca)
    entries: list[dict[str, typing.Any]] = []
    for dispatch in juju.settle():
        if dispatch.unit.app is ca and not entries:
            for relation in _relations(dispatch.state):
                entries = json.loads(relation.local_app_data.get("certificates", "[]"))
    assert entries
    for entry in entries:
        certificate = tls_certificates.Certificate.from_string(entry["certificate"])
        csr = tls_certificates.CertificateSigningRequest.from_string(
            entry["certificate_signing_request"]
        )
        assert csr.matches_certificate(certificate)
        assert tls_certificates.chain_has_valid_order(entry["chain"])


def test_outcome_revoked(juju: _juju.Juju, mocked: None):
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(
        tls_certificates_testing.provider(outcome=tls_certificates_testing.Outcome.revoked())
    )
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _relations(ca.leader.state)
    entries = json.loads(relation.local_app_data["certificates"])
    assert entries
    assert all(e["revoked"] is True for e in entries)


def test_provider_validity_is_configurable(juju: _juju.Juju, mocked: None):
    certificate = _one_certificate(
        juju, tls_certificates_testing.provider(validity=datetime.timedelta(days=7))
    )
    span = certificate.expiry_time - certificate.validity_start_time
    assert span == datetime.timedelta(days=7)


def test_capabilities_absent_by_default(juju: _juju.Juju, mocked: None):
    """Absent means "not advertised yet", which is distinct from an empty object."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(tls_certificates_testing.provider())
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _relations(ca.leader.state)
    assert "capabilities" not in relation.local_app_data


def test_capabilities_are_published_when_given(juju: _juju.Juju, mocked: None):
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(
        tls_certificates_testing.provider(
            capabilities=tls_certificates.ProviderCapabilities(supports_wildcard_dns=False)
        )
    )
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _relations(ca.leader.state)
    published = json.loads(relation.local_app_data["capabilities"])
    # advertised-as-unsupported (False) must survive as distinct from unspecified (None)
    assert published["supports_wildcard_dns"] is False


def test_capabilities_are_published_before_any_answer(juju: _juju.Juju, mocked: None):
    """A provider can advertise before it answers anything."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(
        tls_certificates_testing.provider(
            capabilities=tls_certificates.ProviderCapabilities(),
            outcome=tls_certificates_testing.Outcome.denied(),
        )
    )
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _relations(ca.leader.state)
    databag = relation.local_app_data
    assert "capabilities" in databag
    assert "certificates" not in databag


def test_provider_respond_false_writes_nothing(juju: _juju.Juju, mocked: None):
    """OP093: a stand-in that joins the relation but writes nothing."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(tls_certificates_testing.provider(respond=False))
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _relations(ca.leader.state)
    assert not _interface_keys(relation.local_app_data)
    # The charm asked; nobody answered.
    assert "certificate_signing_requests" in relation.remote_units_data[0]


# ------------------------------------------------- the stand-in requirer: what it writes


def test_requirer_writes_its_requests_to_the_unit_databag_by_default(
    juju: _juju.Juju, mocked: None
):
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    workload = juju.deploy(tls_certificates_testing.requirer())
    juju.integrate(app, workload)
    juju.settle()
    (relation,) = _relations(workload.leader.state)
    assert "certificate_signing_requests" in relation.local_unit_data
    assert not _interface_keys(relation.local_app_data)


def test_requirer_mode_app(juju: _juju.Juju, mocked: None):
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    workload = juju.deploy(tls_certificates_testing.requirer(mode=tls_certificates.Mode.APP))
    juju.integrate(app, workload)
    juju.settle()
    (relation,) = _relations(workload.leader.state)
    assert "certificate_signing_requests" in relation.local_app_data
    assert set(relation.local_unit_data) <= JUJU_NETWORK_KEYS


def test_requirer_mode_app_and_unit_splits_the_requests(juju: _juju.Juju, mocked: None):
    app_request = tls_certificates.CertificateRequestAttributes(common_name="app.example.com")
    unit_request = tls_certificates.CertificateRequestAttributes(common_name="unit.example.com")
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    workload = juju.deploy(
        tls_certificates_testing.requirer(
            mode=tls_certificates.Mode.APP_AND_UNIT,
            certificate_requests_by_mode={
                tls_certificates.Mode.APP: [app_request],
                tls_certificates.Mode.UNIT: [unit_request],
            },
        )
    )
    juju.integrate(app, workload)
    juju.settle()
    (relation,) = _relations(workload.leader.state)
    assert _common_names(relation.local_app_data) == {"app.example.com"}
    assert _common_names(relation.local_unit_data) == {"unit.example.com"}


def test_requirer_mode_app_and_unit_defaults_to_one_request_per_scope(
    juju: _juju.Juju, mocked: None
):
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    workload = juju.deploy(
        tls_certificates_testing.requirer(mode=tls_certificates.Mode.APP_AND_UNIT)
    )
    juju.integrate(app, workload)
    juju.settle()
    (relation,) = _relations(workload.leader.state)
    app_names = _common_names(relation.local_app_data)
    unit_names = _common_names(relation.local_unit_data)
    assert app_names
    assert unit_names
    assert app_names.isdisjoint(unit_names)  # distinct, as the library requires


def test_requirer_mode_app_and_unit_accepts_a_single_scope(juju: _juju.Juju, mocked: None):
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    workload = juju.deploy(
        tls_certificates_testing.requirer(
            mode=tls_certificates.Mode.APP_AND_UNIT,
            certificate_requests_by_mode={
                tls_certificates.Mode.UNIT: [
                    tls_certificates.CertificateRequestAttributes(common_name="unit.example.com")
                ]
            },
        )
    )
    juju.integrate(app, workload)
    juju.settle()
    (relation,) = _relations(workload.leader.state)
    assert _common_names(relation.local_unit_data) == {"unit.example.com"}
    assert not _interface_keys(relation.local_app_data)


def test_requirer_signs_with_its_own_key(juju: _juju.Juju, mocked: None):
    key = tls_certificates.PrivateKey.generate()
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    workload = juju.deploy(tls_certificates_testing.requirer(private_key=key))
    juju.integrate(app, workload)
    juju.settle()
    (relation,) = _relations(workload.leader.state)
    entries = json.loads(relation.local_unit_data["certificate_signing_requests"])
    for entry in entries:
        csr = tls_certificates.CertificateSigningRequest.from_string(
            entry["certificate_signing_request"]
        )
        assert csr.matches_private_key(key)


def test_requirer_flags_a_ca_request(juju: _juju.Juju, mocked: None):
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    workload = juju.deploy(
        tls_certificates_testing.requirer(
            certificate_requests=[
                tls_certificates.CertificateRequestAttributes(
                    common_name="ca.example.com", is_ca=True
                )
            ]
        )
    )
    juju.integrate(app, workload)
    juju.settle()
    (relation,) = _relations(workload.leader.state)
    entries = json.loads(relation.local_unit_data["certificate_signing_requests"])
    assert entries[0]["ca"] is True


def test_requirer_respond_false_writes_nothing(juju: _juju.Juju, mocked: None):
    """OP093: a stand-in that joins the relation but writes nothing."""
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    workload = juju.deploy(tls_certificates_testing.requirer(respond=False))
    juju.integrate(app, workload)
    juju.settle()
    (relation,) = _relations(workload.leader.state)
    assert not _interface_keys(relation.local_app_data)
    assert set(relation.local_unit_data) <= JUJU_NETWORK_KEYS


def test_requirer_reconciles_when_its_requests_change(juju: _juju.Juju, mocked: None):
    """The stand-in requirer derives nothing, but its library still reconciles: requests it
    no longer makes are removed from the relation, which is what a real requirer's library
    does when its configuration changes.

    There is no public way to change a deployed stand-in's arguments, so this deploys a
    replacement -- the fallback OP093 documents for behaviour with no config shape.
    """
    keep = tls_certificates.CertificateRequestAttributes(common_name="keep.example.com")
    drop = tls_certificates.CertificateRequestAttributes(common_name="drop.example.com")
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    before = juju.deploy(
        tls_certificates_testing.requirer(certificate_requests=[keep, drop]), app="workload"
    )
    juju.integrate(app, before)
    juju.settle()
    (relation,) = _relations(before.leader.state)
    assert _common_names(relation.local_unit_data) == {"keep.example.com", "drop.example.com"}
    # Replacing the application is the documented fallback; the new stand-in asks only for
    # what it was given, and the charm drops the certificate for the request that has gone.
    after = juju.deploy(
        tls_certificates_testing.requirer(certificate_requests=[keep]), app="replacement"
    )
    juju.integrate(app, after)
    juju.settle()
    (relation,) = _relations(after.leader.state)
    assert _common_names(relation.local_unit_data) == {"keep.example.com"}


# --------------------------------------------------------------------------------- helpers


def _charm_requesting(
    requests: list[tls_certificates.CertificateRequestAttributes],
) -> type[ops.CharmBase]:
    """Return a requirer charm class asking for exactly ``requests``."""

    class Charm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.certificates = tls_certificates.TLSCertificatesRequiresV4(
                charm=self,
                relationship_name="certificates",
                certificate_requests=requests,
            )

    return Charm


def _one_certificate(
    juju: _juju.Juju, data: tls_certificates_testing.CharmData[ops.CharmBase]
) -> tls_certificates.Certificate:
    """Deploy a one-request charm against the stand-in and return the certificate issued."""
    requests = [tls_certificates.CertificateRequestAttributes(common_name="example.com")]
    app = juju.deploy(_charm_requesting(requests), meta=requirer_charm.META)
    ca = juju.deploy(data)
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _relations(ca.leader.state)
    entries = json.loads(relation.local_app_data["certificates"])
    assert len(entries) == 1
    return tls_certificates.Certificate.from_string(entries[0]["certificate"])


def _first_certificate(
    juju: _juju.Juju, data: tls_certificates_testing.CharmData[ops.CharmBase]
) -> tls_certificates.Certificate:
    """Like ``_one_certificate``, but the *first* certificate the stand-in issued.

    For outcomes that apply only once, such as ``renewing``: by the time the model settles,
    the charm has re-requested and holds a fresh certificate, so the one under test is found
    in the trace instead.
    """
    requests = [tls_certificates.CertificateRequestAttributes(common_name="example.com")]
    app = juju.deploy(_charm_requesting(requests), meta=requirer_charm.META)
    ca = juju.deploy(data)
    juju.integrate(app, ca)
    for dispatch in juju.settle():
        if dispatch.unit.app is not ca:
            continue
        for relation in _relations(dispatch.state):
            if "certificates" in relation.local_app_data:
                (entry,) = json.loads(relation.local_app_data["certificates"])
                return tls_certificates.Certificate.from_string(entry["certificate"])
    raise AssertionError("the stand-in issued nothing")


def _relations(state: ops.testing.State) -> list[ops.testing.Relation]:
    """The state's ``certificates`` relations, typed as the non-peer relations they are."""
    relations = state.get_relations("certificates")
    assert all(isinstance(r, ops.testing.Relation) for r in relations)
    return typing.cast("list[ops.testing.Relation]", list(relations))


def _interface_keys(databag: typing.Mapping[str, str]) -> set[str]:
    """Return only the interface's own keys, excluding Juju's network ones."""
    return set(databag) - JUJU_NETWORK_KEYS


def _common_names(databag: typing.Mapping[str, str]) -> set[str]:
    """Return the common names of the certificate requests in a requirer databag."""
    entries: Iterable[dict[str, str]] = json.loads(
        databag.get("certificate_signing_requests", "[]")
    )
    return {
        tls_certificates.CertificateSigningRequest.from_string(
            entry["certificate_signing_request"]
        ).common_name
        for entry in entries
    }
