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

"""Tests from a requirer charm's perspective -- how a charm author would use the package.

These assert on the charm's state and on the library's accessors, never on relation data.
Not having to touch the wire format is the point of the package; test_testing.py is where
the wire format is the subject.

The charm here lets the library manage its private key, the recommended configuration. See
test_requirer_charm_manual.py for one that supplies its own.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import ops
import ops.testing

import requirer_charm
from charmlibs.interfaces import tls_certificates as tls_certificates
from charmlibs.interfaces import tls_certificates_testing as tls_certificates_testing

if TYPE_CHECKING:
    import _juju

REQUESTED = {r.common_name for r in requirer_charm.REQUESTS}


def _deploy(juju: _juju.Juju, num_units: int = 1) -> _juju.App:
    return juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META, num_units=num_units)


def _ctx(unit: _juju.Unit) -> ops.testing.Context[requirer_charm.RequirerCharm]:
    return ops.testing.Context(
        requirer_charm.RequirerCharm,
        meta=requirer_charm.META,
        app_name=unit.app.name,
        unit_id=unit.id,
    )


def test_no_relation(juju: _juju.Juju, mocked: None):
    """Sanity check: no relation, no certificates."""
    app = _deploy(juju)
    juju.dispatch(app.leader, "update-status")
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.BlockedStatus)


def test_the_happy_path(juju: _juju.Juju, mocked: None):
    """The whole conversation, with nothing to keep in agreement with the charm."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.testing.ActiveStatus)


def test_the_charm_holds_the_certificates_it_asked_for(juju: _juju.Juju, mocked: None):
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.certs is not None
        assert {c.common_name for c in manager.charm.certs} == REQUESTED


def test_related_but_unanswered(juju: _juju.Juju, mocked: None):
    """The most common real intermediate state: asked, but nobody has answered.

    The charm should report blocked because the provider hasn't answered -- not because it
    failed to ask.
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider(respond=False)))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        state_out = manager.run()
        csrs = manager.charm.certificates.get_csrs_from_requirer_relation_data()
        assigned, key = manager.charm.certificates.get_assigned_certificates()
    # The charm's requests made it to the relation, and it holds a key ...
    assert {c.certificate_signing_request.common_name for c in csrs} == REQUESTED
    assert key is not None
    # ... but nothing has been issued for them.
    assert not assigned
    assert isinstance(state_out.unit_status, ops.BlockedStatus)


def test_certificates_are_bound_to_the_charms_key(juju: _juju.Juju, mocked: None):
    """The property that makes the stand-in impossible to silently disagree with.

    The provider signed the requests the charm actually published, so the certificates match
    whatever key the charm used -- no key to seed, and no silent "no certificates".
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assigned, key = manager.charm.certificates.get_assigned_certificates()
    assert key is not None
    assert assigned
    for certificate in assigned:
        assert certificate.certificate.matches_private_key(key)
        assert certificate.certificate_signing_request.matches_certificate(certificate.certificate)


def test_the_settled_relation_is_stable(juju: _juju.Juju, mocked: None):
    """Repeated reconciles must not rewrite the relation or trip certificate renewal.

    Issued certificates start at 0% of their validity, well short of the library's renewal
    threshold. If that regressed -- by issuing nearly-expired certificates, say -- the
    library would withdraw the requests and replace them on the first reconcile, invalidating
    every test built on a settled relation staying settled.
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        first, _ = manager.charm.certificates.get_assigned_certificates()
    for unit in app.units:
        juju.dispatch(unit, "update-status")
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        state_out = manager.run()
        again, _ = manager.charm.certificates.get_assigned_certificates()
    assert {str(c.certificate) for c in again} == {str(c.certificate) for c in first}
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_key_rotation_round_trip(juju: _juju.Juju, mocked: None):
    """Rotate, re-request, have the provider answer, and check the binding moved."""
    app = juju.deploy(requirer_charm.RotatingRequirerCharm, meta=requirer_charm.ROTATING_META)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    ctx = ops.testing.Context(
        requirer_charm.RotatingRequirerCharm, meta=requirer_charm.ROTATING_META
    )
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assigned, before = manager.charm.certificates.get_assigned_certificates()
        assert len(assigned) == len(requirer_charm.REQUESTS)
    # The charm rotates inside the model: old requests withdrawn, new ones sent, and the
    # stand-in drops the old answers and answers the new requests.
    juju.dispatch(app.leader, "action:rotate-key")
    juju.settle()
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        state_out = manager.run()
        assigned, after = manager.charm.certificates.get_assigned_certificates()
    assert after is not None
    assert after != before
    assert {c.certificate.common_name for c in assigned} == REQUESTED
    assert before is not None
    for certificate in assigned:
        assert certificate.certificate.matches_private_key(after)
        assert not certificate.certificate.matches_private_key(before)
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_renewal_round_trip(juju: _juju.Juju, mocked: None):
    """A stale certificate, the library's safety net, and the provider's fresh answer.

    The stand-in applies ``renewing`` only to the first certificate it issues for each set
    of request attributes, so the renewal completes within one ``settle()``: the safety net
    re-requests, and the stand-in answers the fresh request normally.
    """
    app = _deploy(juju)
    juju.integrate(
        app,
        juju.deploy(
            tls_certificates_testing.provider(outcome=tls_certificates_testing.Outcome.renewing())
        ),
    )
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        state_out = manager.run()
        assigned, key = manager.charm.certificates.get_assigned_certificates()
    assert {c.certificate.common_name for c in assigned} == REQUESTED
    # The renewal replaced the certificate, not the key.
    assert key is not None
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)
    # And the certificate the charm ends up holding is fresh, not the stale one it was
    # first issued: it is nowhere near its renewal threshold.
    for certificate in assigned:
        start, end = (
            certificate.certificate.validity_start_time,
            certificate.certificate.expiry_time,
        )
        assert _now() < start + (end - start) * 0.5


def test_expired_certificates_are_not_renewed(juju: _juju.Juju, mocked: None):
    """The library's safety net stops at expiry, so a dead certificate stays assigned.

    Reaching this state means renewal did not happen, which is what the safety net exists to
    prevent -- so a test built on it is a resilience test, not normal operation. What the
    charm does about it is the charm's own decision.
    """
    app = _deploy(juju)
    juju.integrate(
        app,
        juju.deploy(
            tls_certificates_testing.provider(outcome=tls_certificates_testing.Outcome.expired())
        ),
    )
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert {c.certificate.common_name for c in assigned} == REQUESTED
    for certificate in assigned:
        assert certificate.certificate.expiry_time < _now()


def test_denied_requests_reach_the_charm(juju: _juju.Juju, mocked: None):
    """One issued, one denied: the realistic case, since a provider that refuses one domain
    still serves the others.
    """
    issued, refused = requirer_charm.REQUESTS
    code = tls_certificates.CertificateRequestErrorCode.DOMAIN_NOT_ALLOWED
    app = _deploy(juju)
    juju.integrate(
        app,
        juju.deploy(
            tls_certificates_testing.provider(
                outcome=lambda request: (
                    tls_certificates_testing.Outcome.denied(code=code, message="computer says no")
                    if request.common_name == refused.common_name
                    else tls_certificates_testing.Outcome.issued()
                )
            )
        ),
    )
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
        errors = manager.charm.certificates.get_request_errors()
        csrs = manager.charm.certificates.get_csrs_from_requirer_relation_data()
        refused_csr = next(
            c.certificate_signing_request
            for c in csrs
            if c.certificate_signing_request.common_name == refused.common_name
        )
        error = manager.charm.certificates.get_request_error(refused_csr)
    # The issued request is assigned as usual ...
    assert {c.certificate.common_name for c in assigned} == {issued.common_name}
    # ... and the denied one is reported as a request error.
    assert [e.certificate_signing_request.common_name for e in errors] == [refused.common_name]
    assert error is not None
    assert error.error.code == code.value
    assert error.error.message == "computer says no"


def test_revoking_a_certificate_removes_its_secret(juju: _juju.Juju, mocked: None):
    """The library removes a revoked certificate's Juju secret on its next reconcile."""
    app = _deploy(juju)
    juju.integrate(
        app,
        juju.deploy(
            tls_certificates_testing.provider(outcome=tls_certificates_testing.Outcome.revoked())
        ),
    )
    juju.settle()
    assert not _certificate_secrets(app.leader.state)


def test_a_ca_request_is_answered_with_a_ca_certificate(juju: _juju.Juju, mocked: None):
    """The library matches on the databag's ca flag and on BasicConstraints, so both agree."""
    request = tls_certificates.CertificateRequestAttributes(
        common_name="ca.example.com", is_ca=True
    )

    class CaCharm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.certificates = tls_certificates.TLSCertificatesRequiresV4(
                charm=self, relationship_name="certificates", certificate_requests=[request]
            )

    app = juju.deploy(CaCharm, meta=requirer_charm.META)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    ctx = ops.testing.Context(CaCharm, meta=requirer_charm.META)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert len(assigned) == 1
    assert assigned[0].certificate.common_name == request.common_name
    assert assigned[0].certificate.is_ca


def test_provider_capabilities_are_absent_by_default(juju: _juju.Juju, mocked: None):
    """No capabilities models a provider that hasn't advertised yet.

    Per the library's contract that means `None` -- "not known yet, defer" -- which is
    distinct from advertising an empty set.
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.certificates.get_provider_capabilities() is None


def test_provider_capabilities_reach_the_charm(juju: _juju.Juju, mocked: None):
    """All three field states survive: supported, advertised-as-unsupported, unspecified."""
    app = _deploy(juju)
    juju.integrate(
        app,
        juju.deploy(
            tls_certificates_testing.provider(
                capabilities=tls_certificates.ProviderCapabilities(
                    supports_ip_sans=True, supports_wildcard_dns=False
                )
            )
        ),
    )
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        capabilities = manager.charm.certificates.get_provider_capabilities()
    assert capabilities is not None
    assert capabilities.supports_ip_sans is True
    assert capabilities.supports_wildcard_dns is False
    assert capabilities.supports_subdomain is None  # unspecified, not a default


def test_capability_aware_requests_are_resolved_against_the_advertisement(
    juju: _juju.Juju, mocked: None
):
    """The callable form of certificate_requests sees what the stand-in advertised.

    The charm asks *first*, before the provider has advertised anything, so its first
    request is the one it makes for unknown capabilities. Once the provider has published,
    the charm sees the advertisement, withdraws that request and asks for what the
    capabilities allow -- and the stand-in answers that. All of it happens within
    ``settle()``, which is what a real deployment does too.
    """
    wildcard = tls_certificates.CertificateRequestAttributes(common_name="*.example.com")
    plain = tls_certificates.CertificateRequestAttributes(common_name="example.com")
    seen: list[tls_certificates.ProviderCapabilities | None] = []

    def choose(
        capabilities: tls_certificates.ProviderCapabilities | None,
    ) -> list[tls_certificates.CertificateRequestAttributes]:
        seen.append(capabilities)
        if capabilities is not None and capabilities.supports_wildcard_dns:
            return [wildcard]
        return [plain]

    class PickyCharm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.certificates = tls_certificates.TLSCertificatesRequiresV4(
                charm=self, relationship_name="certificates", certificate_requests=choose
            )

    app = juju.deploy(PickyCharm, meta=requirer_charm.META)
    juju.integrate(
        app,
        juju.deploy(
            tls_certificates_testing.provider(
                capabilities=tls_certificates.ProviderCapabilities(supports_wildcard_dns=True)
            )
        ),
    )
    juju.settle()
    ctx = ops.testing.Context(PickyCharm, meta=requirer_charm.META)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    # The callable saw the advertised capabilities ...
    assert seen
    assert any(c is not None and c.supports_wildcard_dns for c in seen)
    # ... chose the wildcard request, and that is what got a certificate.
    assert {c.certificate.common_name for c in assigned} == {wildcard.common_name}


def test_a_provider_that_advertises_nothing_gets_the_fallback_request(
    juju: _juju.Juju, mocked: None
):
    """Companion to the above: unknown capabilities, and the charm's conservative choice."""
    wildcard = tls_certificates.CertificateRequestAttributes(common_name="*.example.com")
    plain = tls_certificates.CertificateRequestAttributes(common_name="example.com")

    def choose(
        capabilities: tls_certificates.ProviderCapabilities | None,
    ) -> list[tls_certificates.CertificateRequestAttributes]:
        if capabilities is not None and capabilities.supports_wildcard_dns:
            return [wildcard]
        return [plain]

    class PickyCharm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.certificates = tls_certificates.TLSCertificatesRequiresV4(
                charm=self, relationship_name="certificates", certificate_requests=choose
            )

    app = juju.deploy(PickyCharm, meta=requirer_charm.META)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    ctx = ops.testing.Context(PickyCharm, meta=requirer_charm.META)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert {c.certificate.common_name for c in assigned} == {plain.common_name}


def test_a_multi_unit_requirer_gets_a_certificate_per_unit(juju: _juju.Juju, mocked: None):
    """The case the stand-in shape exists for: each unit asks, and each is answered."""
    app = _deploy(juju, num_units=3)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    for unit in app.units:
        assert isinstance(unit.state.unit_status, ops.testing.ActiveStatus)
        ctx = _ctx(unit)
        with ctx(ctx.on.update_status(), unit.state) as manager:
            manager.run()
            assigned, key = manager.charm.certificates.get_assigned_certificates()
        assert {c.certificate.common_name for c in assigned} == REQUESTED
        assert key is not None
        for certificate in assigned:
            assert certificate.certificate.matches_private_key(key)


def test_a_non_default_unit_finds_its_key(juju: _juju.Juju, mocked: None):
    """The library's unit-scoped key secret label embeds the unit number.

    Under the previous API this had to be told which unit to seed for, and a mismatch showed
    up as "no certificates" rather than an error. The charm creates its own key here, so
    there is nothing to tell.
    """
    app = _deploy(juju, num_units=4)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    unit = app.units[3]
    assert isinstance(unit.state.unit_status, ops.testing.ActiveStatus)
    ctx = _ctx(unit)
    with ctx(ctx.on.update_status(), unit.state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert {c.certificate.common_name for c in assigned} == REQUESTED


def test_several_endpoints_each_with_their_own_provider(juju: _juju.Juju, mocked: None):
    """A charm related to two certificate providers, one per endpoint."""
    meta = {
        "name": "requirer",
        "requires": {
            "internal-certs": {"interface": "tls-certificates"},
            "public-certs": {"interface": "tls-certificates"},
        },
    }

    class TwoEndpointCharm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.internal = tls_certificates.TLSCertificatesRequiresV4(
                charm=self,
                relationship_name="internal-certs",
                certificate_requests=[
                    tls_certificates.CertificateRequestAttributes(common_name="internal.example")
                ],
            )
            self.public = tls_certificates.TLSCertificatesRequiresV4(
                charm=self,
                relationship_name="public-certs",
                certificate_requests=[
                    tls_certificates.CertificateRequestAttributes(common_name="public.example")
                ],
            )

    app = juju.deploy(TwoEndpointCharm, meta=meta)
    # Written out one stand-in at a time, rather than looped, so a traceback points at the
    # stand-in that failed.
    internal = juju.deploy(tls_certificates_testing.provider(), app="internal-ca")
    juju.integrate((app, "internal-certs"), internal)
    public = juju.deploy(tls_certificates_testing.provider(), app="public-ca")
    juju.integrate((app, "public-certs"), public)
    juju.settle()
    ctx = ops.testing.Context(TwoEndpointCharm, meta=meta)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        internal_certs, _ = manager.charm.internal.get_assigned_certificates()
        public_certs, _ = manager.charm.public.get_assigned_certificates()
    assert {c.certificate.common_name for c in internal_certs} == {"internal.example"}
    assert {c.certificate.common_name for c in public_certs} == {"public.example"}


# --------------------------------------------------------------------------------- helpers


def _certificate_secrets(state: ops.testing.State) -> list[ops.testing.Secret]:
    """The secrets the library created to store assigned certificates.

    The private key secret shares the LIBID prefix, so filter on the library's own infix.
    """
    return [s for s in state.secrets if s.label and "-certificate-" in s.label]


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)
