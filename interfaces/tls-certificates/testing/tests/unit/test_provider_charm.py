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

"""Tests from a provider charm's perspective, using the stand-in requirer.

Note that the harness makes unit 0 of each application the leader, which is what a provider
charm needs: ``TLSCertificatesProvidesV4`` writes to the application databag, so a
non-leader provider charm answers nothing.
"""

from __future__ import annotations

import json

import ops
import ops.testing

import _juju
import provider_charm
from charmlibs.interfaces import tls_certificates as tls_certificates
from charmlibs.interfaces import tls_certificates_testing as tls_certificates_testing

REQUEST = tls_certificates.CertificateRequestAttributes(common_name="workload.example.com")


def _deploy(juju: _juju.Juju, num_units: int = 1) -> _juju.App:
    return juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META, num_units=num_units)


def _ctx(unit: _juju.Unit) -> ops.testing.Context[provider_charm.ProviderCharm]:
    return ops.testing.Context(
        provider_charm.ProviderCharm, meta=provider_charm.META, unit_id=unit.id
    )


def test_no_relation(juju: _juju.Juju, mocked: None):
    app = _deploy(juju)
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.requests is None


def test_the_happy_path(juju: _juju.Juju, mocked: None):
    app = _deploy(juju)
    juju.integrate(
        app,
        juju.deploy(tls_certificates_testing.requirer(certificate_requests=[REQUEST])),
    )
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.testing.ActiveStatus)


def test_a_silent_requirer_asks_for_nothing(juju: _juju.Juju, mocked: None):
    """respond=False: the stand-in joins the relation and writes nothing."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tls_certificates_testing.requirer(respond=False)))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.requests is None
        assert not manager.charm.certificates.get_certificate_requests()


def test_received_means_the_charm_has_answered(juju: _juju.Juju, mocked: None):
    """The settled relation: nothing left outstanding, and a certificate issued."""
    app = _deploy(juju)
    juju.integrate(
        app,
        juju.deploy(tls_certificates_testing.requirer(certificate_requests=[REQUEST])),
    )
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        outstanding = manager.charm.certificates.get_outstanding_certificate_requests()
        issued = manager.charm.certificates.get_issued_certificates()
    assert not outstanding
    assert {c.certificate.common_name for c in issued} == {REQUEST.common_name}


def test_the_charm_sees_the_requests_it_was_sent(juju: _juju.Juju, mocked: None):
    app = _deploy(juju)
    juju.integrate(
        app,
        juju.deploy(tls_certificates_testing.requirer(certificate_requests=[REQUEST])),
    )
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.requests is not None
        assert {r.common_name for r in manager.charm.requests} == {REQUEST.common_name}


def test_the_issued_certificate_matches_the_request(juju: _juju.Juju, mocked: None):
    """The charm signed the request the stand-in actually made, key and all."""
    key = tls_certificates.PrivateKey.generate()
    app = _deploy(juju)
    juju.integrate(
        app,
        juju.deploy(
            tls_certificates_testing.requirer(certificate_requests=[REQUEST], private_key=key)
        ),
    )
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        issued = manager.charm.certificates.get_issued_certificates()
    assert issued
    for certificate in issued:
        assert certificate.certificate_signing_request.matches_certificate(certificate.certificate)
        assert certificate.certificate_signing_request.matches_private_key(key)


def test_a_non_leader_answers_nothing(juju: _juju.Juju, mocked: None):
    """A non-leader provider charm cannot write its application databag.

    It reads the requests and then silently issues nothing.
    """
    app = _deploy(juju, num_units=2)
    juju.integrate(
        app,
        juju.deploy(tls_certificates_testing.requirer(certificate_requests=[REQUEST])),
    )
    juju.settle()
    non_leader = app.units[1]
    ctx = _ctx(non_leader)
    with ctx(ctx.on.update_status(), non_leader.state) as manager:
        manager.run()
        assert manager.charm.requests is not None  # it read them
        assert not manager.charm.certificates.get_provider_certificates()  # but wrote nothing


def test_the_charm_publishes_its_capabilities(juju: _juju.Juju, mocked: None):
    """A provider charm advertises when it runs, so this needs no fixture argument."""
    app = _deploy(juju)
    workload = juju.deploy(tls_certificates_testing.requirer(certificate_requests=[REQUEST]))
    juju.integrate(app, workload)
    juju.settle()
    (relation,) = _juju.relations(workload.leader.state, "certificates")
    # Reading the databag because this is about what the charm wrote, not what it can read;
    # the library has no accessor for a provider's own advertised capabilities.
    published = json.loads(relation.remote_app_data["capabilities"])
    assert published["provider_type"] == provider_charm.CAPABILITIES.provider_type
    assert published["supports_ca_certificates"] is True


def test_a_multi_application_relation(juju: _juju.Juju, mocked: None):
    """Several requirer applications on one endpoint, one stand-in each."""
    app = _deploy(juju)
    workers = [
        juju.deploy(
            tls_certificates_testing.requirer(
                certificate_requests=[
                    tls_certificates.CertificateRequestAttributes(
                        common_name=f"worker{n}.example.com"
                    )
                ]
            ),
            app=f"worker{n}",
        )
        for n in range(3)
    ]
    for worker in workers:
        juju.integrate(app, worker)
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        issued = manager.charm.certificates.get_issued_certificates()
        outstanding = manager.charm.certificates.get_outstanding_certificate_requests()
    assert {c.certificate.common_name for c in issued} == {
        f"worker{n}.example.com" for n in range(3)
    }
    assert not outstanding
    # Each stand-in's relation is separate, and each holds only its own application's answer.
    for n, worker in enumerate(workers):
        (relation,) = worker.leader.state.get_relations("certificates")
        certificates = [c for c in issued if c.relation_id == relation.id]
        assert {c.certificate.common_name for c in certificates} == {f"worker{n}.example.com"}


def test_a_ca_request(juju: _juju.Juju, mocked: None):
    """The charm signs a CA request as a CA certificate."""
    app = _deploy(juju)
    juju.integrate(
        app,
        juju.deploy(
            tls_certificates_testing.requirer(
                certificate_requests=[
                    tls_certificates.CertificateRequestAttributes(
                        common_name="ca.example.com", is_ca=True
                    )
                ]
            )
        ),
    )
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        issued = manager.charm.certificates.get_issued_certificates()
    assert len(issued) == 1
    assert issued[0].certificate.is_ca


def test_an_app_scoped_requirer(juju: _juju.Juju, mocked: None):
    """Mode.APP puts the requests in the stand-in's *application* databag, and the charm
    reads both that and every remote unit's.
    """
    app = _deploy(juju)
    juju.integrate(
        app,
        juju.deploy(
            tls_certificates_testing.requirer(
                certificate_requests=[REQUEST], mode=tls_certificates.Mode.APP
            )
        ),
    )
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        issued = manager.charm.certificates.get_issued_certificates()
    assert {c.certificate.common_name for c in issued} == {REQUEST.common_name}


def test_an_app_and_unit_requirer(juju: _juju.Juju, mocked: None):
    """Both scopes' requests reach the charm, and it answers both."""
    app = _deploy(juju)
    juju.integrate(
        app,
        juju.deploy(tls_certificates_testing.requirer(mode=tls_certificates.Mode.APP_AND_UNIT)),
    )
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        issued = manager.charm.certificates.get_issued_certificates()
        outstanding = manager.charm.certificates.get_outstanding_certificate_requests()
    assert len(issued) == 2  # one application request, one unit request
    assert not outstanding
