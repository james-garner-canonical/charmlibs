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

"""Tests for a requirer charm holding a certificate in each of the library's two scopes.

Mode.APP_AND_UNIT is where the old API needed the most arrangement: one key secret per scope,
seeded with the key the fixture had signed both scopes' requests with. Deriving the answer
removes all of it -- the charm generates a key per scope itself, and the provider signs what
each scope published.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import ops
import ops.testing

import requirer_charm_app_and_unit as charm_module
from charmlibs.interfaces import tls_certificates as tls_certificates
from charmlibs.interfaces import tls_certificates_testing as tls_certificates_testing

if TYPE_CHECKING:
    import _juju


def _deploy(juju: _juju.Juju, num_units: int = 1) -> _juju.App:
    return juju.deploy(
        charm_module.AppAndUnitRequirerCharm, meta=charm_module.META, num_units=num_units
    )


def _ctx(unit: _juju.Unit) -> ops.testing.Context[charm_module.AppAndUnitRequirerCharm]:
    return ops.testing.Context(
        charm_module.AppAndUnitRequirerCharm, meta=charm_module.META, unit_id=unit.id
    )


def test_the_happy_path(juju: _juju.Juju, mocked: None):
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.testing.ActiveStatus)


def test_both_scopes_get_their_certificate(juju: _juju.Juju, mocked: None):
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        app_certs, app_key = manager.charm.certificates.get_assigned_certificates(
            tls_certificates.Mode.APP
        )
        unit_certs, unit_key = manager.charm.certificates.get_assigned_certificates(
            tls_certificates.Mode.UNIT
        )
    assert {c.certificate.common_name for c in app_certs} == {charm_module.APP_REQUEST.common_name}
    assert {c.certificate.common_name for c in unit_certs} == {
        charm_module.UNIT_REQUEST.common_name
    }
    # A separate key per scope, and each scope's certificates bound to its own key.
    assert app_key is not None
    assert unit_key is not None
    assert app_key != unit_key
    for certificate in app_certs:
        assert certificate.certificate.matches_private_key(app_key)
    for certificate in unit_certs:
        assert certificate.certificate.matches_private_key(unit_key)


def test_one_key_secret_per_scope(juju: _juju.Juju, mocked: None):
    """The library keeps a key per scope, which is why seeding them was awkward before."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    keys = [s for s in app.leader.state.secrets if s.label and "-private-key-" in s.label]
    assert len(keys) == 2
    assert {s.owner for s in keys} == {"app", "unit"}


def test_a_non_leader_holds_only_its_unit_certificate(juju: _juju.Juju, mocked: None):
    """A non-leader can act on the unit scope only, per the library's 1.10.1 fix.

    It can reach neither the application key nor the application certificates, and must not
    take the unit scope down with the application one.
    """
    app = _deploy(juju, num_units=2)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    non_leader = app.units[1]
    assert isinstance(non_leader.state.unit_status, ops.testing.ActiveStatus)
    ctx = _ctx(non_leader)
    with ctx(ctx.on.update_status(), non_leader.state) as manager:
        manager.run()
        unit_certs, unit_key = manager.charm.certificates.get_assigned_certificates(
            tls_certificates.Mode.UNIT
        )
        assert manager.charm.app_certs is None
    assert unit_key is not None
    assert {c.certificate.common_name for c in unit_certs} == {
        charm_module.UNIT_REQUEST.common_name
    }


def test_renewal_of_both_scopes(juju: _juju.Juju, mocked: None):
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
        app_certs, _ = manager.charm.certificates.get_assigned_certificates(
            tls_certificates.Mode.APP
        )
        unit_certs, _ = manager.charm.certificates.get_assigned_certificates(
            tls_certificates.Mode.UNIT
        )
    assert {c.certificate.common_name for c in app_certs} == {charm_module.APP_REQUEST.common_name}
    assert {c.certificate.common_name for c in unit_certs} == {
        charm_module.UNIT_REQUEST.common_name
    }
    # The renewal replaced the certificates: none of them is anywhere near its threshold.
    now = datetime.datetime.now(datetime.timezone.utc)
    for certificate in (*app_certs, *unit_certs):
        start, end = (
            certificate.certificate.validity_start_time,
            certificate.certificate.expiry_time,
        )
        assert now < start + (end - start) * 0.5
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)


def test_a_denied_application_request(juju: _juju.Juju, mocked: None):
    """Mixed outcomes across scopes: the unit certificate is issued, the app one refused."""
    app = _deploy(juju)
    juju.integrate(
        app,
        juju.deploy(
            tls_certificates_testing.provider(
                outcome=lambda request: (
                    tls_certificates_testing.Outcome.denied()
                    if request.common_name == charm_module.APP_REQUEST.common_name
                    else tls_certificates_testing.Outcome.issued()
                )
            )
        ),
    )
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        state_out = manager.run()
        app_certs, _ = manager.charm.certificates.get_assigned_certificates(
            tls_certificates.Mode.APP
        )
        unit_certs, _ = manager.charm.certificates.get_assigned_certificates(
            tls_certificates.Mode.UNIT
        )
        errors = manager.charm.certificates.get_request_errors()
    assert not app_certs
    assert {c.certificate.common_name for c in unit_certs} == {
        charm_module.UNIT_REQUEST.common_name
    }
    assert {e.certificate_signing_request.common_name for e in errors} == {
        charm_module.APP_REQUEST.common_name
    }
    assert isinstance(state_out.unit_status, ops.BlockedStatus)
