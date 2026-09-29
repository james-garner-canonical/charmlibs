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

"""Tests for a requirer charm whose certificate belongs to the application."""

from __future__ import annotations

from typing import TYPE_CHECKING

import ops
import ops.testing

import requirer_charm_app
from charmlibs.interfaces import tls_certificates_testing as tls_certificates_testing

if TYPE_CHECKING:
    import _juju

REQUESTED = {r.common_name for r in requirer_charm_app.REQUESTS}


def _deploy(juju: _juju.Juju, num_units: int = 1) -> _juju.App:
    return juju.deploy(
        requirer_charm_app.AppRequirerCharm, meta=requirer_charm_app.META, num_units=num_units
    )


def test_the_happy_path(juju: _juju.Juju, mocked: None):
    """An application-scoped requirer must be the leader, since it writes app data."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.testing.ActiveStatus)


def test_the_requests_are_application_scoped(juju: _juju.Juju, mocked: None):
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    ctx = ops.testing.Context(requirer_charm_app.AppRequirerCharm, meta=requirer_charm_app.META)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert {c.certificate.common_name for c in assigned} == REQUESTED


def test_the_key_secret_is_app_owned(juju: _juju.Juju, mocked: None):
    """Mode.APP keeps the key in an app-owned secret, at a distinct label.

    The library derives that label itself, so a test never has to name it -- but the owner is
    worth pinning, because it is what makes the key readable by a new leader.
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    keys = [s for s in app.leader.state.secrets if s.label and "-private-key-" in s.label]
    assert len(keys) == 1
    assert keys[0].owner == "app"
    assert "-private-key-app-" in (keys[0].label or "")


def test_a_non_leader_cannot_ask(juju: _juju.Juju, mocked: None):
    """An application-scoped requirer writes app data, which a non-leader cannot do.

    So it asks for nothing and gets nothing. This is otherwise invisible in the resulting
    state and easily mistaken for a bug in the charm.
    """
    app = _deploy(juju, num_units=2)
    juju.integrate(app, juju.deploy(tls_certificates_testing.provider()))
    juju.settle()
    non_leader = app.units[1]
    ctx = ops.testing.Context(
        requirer_charm_app.AppRequirerCharm, meta=requirer_charm_app.META, unit_id=1
    )
    with ctx(ctx.on.update_status(), non_leader.state) as manager:
        state_out = manager.run()
        assert manager.charm.certs is None
    assert isinstance(state_out.unit_status, ops.BlockedStatus)


def test_renewal(juju: _juju.Juju, mocked: None):
    app = _deploy(juju)
    juju.integrate(
        app,
        juju.deploy(
            tls_certificates_testing.provider(outcome=tls_certificates_testing.Outcome.renewing())
        ),
    )
    juju.settle()
    ctx = ops.testing.Context(requirer_charm_app.AppRequirerCharm, meta=requirer_charm_app.META)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        state_out = manager.run()
        assigned, _ = manager.charm.certificates.get_assigned_certificates()
    assert {c.certificate.common_name for c in assigned} == REQUESTED
    assert isinstance(state_out.unit_status, ops.testing.ActiveStatus)
