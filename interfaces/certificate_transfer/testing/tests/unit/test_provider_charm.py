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

Note that the harness makes unit 0 of each application the leader, which is what both
sides need: ``CertificateTransferRequires`` writes its version to the application databag,
and ``CertificateTransferProvides.add_certificates`` writes the answer there too.
"""

from __future__ import annotations

import typing

import ops
import ops.testing

import provider_charm
import requirer_charm
from charmlibs.interfaces import certificate_transfer_testing as certificate_transfer_testing

if typing.TYPE_CHECKING:
    import _juju


def _deploy(juju: _juju.Juju, num_units: int = 1) -> _juju.App:
    return juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META, num_units=num_units)


def _ctx(unit: _juju.Unit) -> ops.testing.Context[provider_charm.ProviderCharm]:
    return ops.testing.Context(
        provider_charm.ProviderCharm,
        meta=provider_charm.META,
        app_name=unit.app.name,
        unit_id=unit.id,
    )


def _read_back(
    state: ops.testing.State, endpoint: str = 'send-ca-cert', remote_app_name: str | None = None
) -> set[str]:
    """What a real requirer charm would see, by running one against the provider's databags.

    Reading the provider's relation data directly would mean knowing the wire format, and
    knowing which of the interface's two formats to look in. Running the library's own
    requirer over the same relation asks the question a charm author actually has -- "did
    this arrive?" -- and answers it the same way for both formats.
    """
    (relation,) = [
        r
        for r in state.relations
        if r.endpoint == endpoint
        and isinstance(r, ops.testing.Relation)
        and (remote_app_name is None or r.remote_app_name == remote_app_name)
    ]
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    # The two sides swap over: what the provider charm wrote locally is what the requirer
    # charm reads remotely, and vice versa.
    mirrored = ops.testing.Relation(
        'certificates',
        interface='certificate_transfer',
        remote_app_name='provider',
        local_app_data=dict(relation.remote_app_data),
        remote_app_data=dict(relation.local_app_data),
        remote_units_data={0: dict(relation.local_unit_data)},
    )
    with ctx(ctx.on.update_status(), ops.testing.State(leader=True, relations=[mirrored])) as m:
        m.run()
        return m.charm.certificates or set()


def test_no_relation(juju: _juju.Juju, mocked: None):
    """Nobody is asking, so there is nothing to transfer to -- but the charm still runs."""
    app = _deploy(juju)
    juju.dispatch(app.leader, 'update-status')
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.ActiveStatus)


def test_the_happy_path(juju: _juju.Juju, mocked: None):
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(certificate_transfer_testing.requirer()))
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.ActiveStatus)
    assert _read_back(app.leader.state) == {provider_charm.CA_CERT}


def test_the_charm_has_transferred(juju: _juju.Juju, mocked: None):
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(certificate_transfer_testing.requirer()))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.transferred is True


def test_a_silent_requirer_is_answered_in_the_v0_format(juju: _juju.Juju, mocked: None):
    """respond=False: the stand-in joins the relation and writes nothing.

    An absent ``version`` key is how v0 is spelled, so the provider library falls back to
    the v0 format -- which a modern requirer still reads.
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(certificate_transfer_testing.requirer(respond=False)))
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.ActiveStatus)
    assert _read_back(app.leader.state) == {provider_charm.CA_CERT}


def test_an_old_requirer_is_answered_in_the_v0_format(juju: _juju.Juju, mocked: None):
    """``interface_version=0`` models a requirer charm that predates v1 of the interface.

    It advertises nothing, so the charm under test keeps writing the v0 format, which is
    what the library's fallback exists for.
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(certificate_transfer_testing.requirer(interface_version=0)))
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.ActiveStatus)
    assert _read_back(app.leader.state) == {provider_charm.CA_CERT}


def test_a_non_leader_provider_transfers_nothing(juju: _juju.Juju, mocked: None):
    """Transferring is leader-only, so a non-leader reads the request and does nothing."""
    app = _deploy(juju, num_units=2)
    juju.integrate(app, juju.deploy(certificate_transfer_testing.requirer()))
    juju.settle()
    non_leader = app.units[1]
    assert isinstance(non_leader.state.unit_status, ops.ActiveStatus)
    # The leader wrote the certificates, and every unit can read them back.
    assert _read_back(app.leader.state) == {provider_charm.CA_CERT}
    ctx = _ctx(non_leader)
    with ctx(ctx.on.update_status(), non_leader.state) as manager:
        manager.run()
        assert manager.charm.transferred is False


def test_several_requirers_on_one_endpoint(juju: _juju.Juju, mocked: None):
    """A stand-in stands for one application, so several clients take one each."""
    app = _deploy(juju)
    clients = [
        juju.deploy(certificate_transfer_testing.requirer(), app=name)
        for name in ('workload', 'dashboard')
    ]
    for client in clients:
        juju.integrate(app, client)
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.ActiveStatus)
    for client in clients:
        assert _read_back(app.leader.state, remote_app_name=client.name) == {
            provider_charm.CA_CERT
        }
