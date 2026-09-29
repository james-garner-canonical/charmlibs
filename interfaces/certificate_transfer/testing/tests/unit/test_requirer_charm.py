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

A requirer charm is tested with a stand-in provider. These assert on the charm's state and
on the library's accessors, never on relation data. Not having to touch the wire format is
the point of the package; test_testing.py is where the wire format is the subject.
"""

from __future__ import annotations

import typing

import ops
import ops.testing

import requirer_charm
from charmlibs.interfaces import certificate_transfer_testing as certificate_transfer_testing
from charmlibs.interfaces.certificate_transfer_testing import _raw

if typing.TYPE_CHECKING:
    import _juju

ROOT = '-----BEGIN CERTIFICATE-----\nroot\n-----END CERTIFICATE-----'
INTERMEDIATE = '-----BEGIN CERTIFICATE-----\nintermediate\n-----END CERTIFICATE-----'


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
    """Without a relation there are no CA certificates to have."""
    app = _deploy(juju)
    juju.dispatch(app.leader, 'update-status')
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.BlockedStatus)


def test_the_happy_path(juju: _juju.Juju, mocked: None):
    """The whole conversation, with nothing to keep in agreement with the charm."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(certificate_transfer_testing.provider()))
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.ActiveStatus)


def test_the_charm_has_the_providers_certificates(juju: _juju.Juju, mocked: None):
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(certificate_transfer_testing.provider()))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.certificates == set(_raw.CA_CERTS[:1])


def test_related_but_unanswered(juju: _juju.Juju, mocked: None):
    """The most common real intermediate state: related, but nobody has transferred.

    The charm should report blocked because the provider hasn't transferred -- not because
    it failed to advertise its version.
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(certificate_transfer_testing.provider(respond=False)))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        state_out = manager.run()
        assert manager.charm.certificates is None
    assert isinstance(state_out.unit_status, ops.BlockedStatus)


def test_several_certificates(juju: _juju.Juju, mocked: None):
    """``certificates`` is the set the provider transfers; the charm gets all of it."""
    app = _deploy(juju)
    ca = juju.deploy(certificate_transfer_testing.provider(certificates=[ROOT, INTERMEDIATE]))
    juju.integrate(app, ca)
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.certificates == {ROOT, INTERMEDIATE}


def test_provider_has_nothing_to_transfer(juju: _juju.Juju, mocked: None):
    """An empty set is an answer, and it is empty -- not the same as no answer at all."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(certificate_transfer_testing.provider(certificates=[])))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        state_out = manager.run()
        assert manager.charm.certificates is None
    assert isinstance(state_out.unit_status, ops.BlockedStatus)


def test_old_provider_uses_the_v0_format(juju: _juju.Juju, mocked: None):
    """``interface_version=0`` models a provider charm that predates v1 of the interface.

    The library falls back to reading the provider's *unit* databag, so a modern requirer
    charm still gets its certificates. This is the one case a leader charm can't reach by
    itself, since it always advertises version 1.
    """
    app = _deploy(juju)
    ca = juju.deploy(certificate_transfer_testing.provider(interface_version=0))
    juju.integrate(app, ca)
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        state_out = manager.run()
        assert manager.charm.certificates == set(_raw.CA_CERTS[:1])
    assert isinstance(state_out.unit_status, ops.ActiveStatus)


def test_a_non_leader_requirer_is_answered_in_the_v0_format(juju: _juju.Juju, mocked: None):
    """A non-leader requirer can't advertise version 1, so it is taken for an old one.

    It still receives the certificates, through the same v0 fallback.
    """
    app = _deploy(juju, num_units=2)
    juju.integrate(app, juju.deploy(certificate_transfer_testing.provider()))
    juju.settle()
    non_leader = app.units[1]
    ctx = _ctx(non_leader)
    with ctx(ctx.on.update_status(), non_leader.state) as manager:
        state_out = manager.run()
        assert manager.charm.certificates == set(_raw.CA_CERTS[:1])
    assert isinstance(state_out.unit_status, ops.ActiveStatus)


def test_a_multi_unit_requirer_shares_one_answer(juju: _juju.Juju, mocked: None):
    """The certificates live in the provider's application databag, which every unit reads."""
    app = _deploy(juju, num_units=3)
    juju.integrate(app, juju.deploy(certificate_transfer_testing.provider()))
    juju.settle()
    for unit in app.units:
        ctx = _ctx(unit)
        with ctx(ctx.on.update_status(), unit.state) as manager:
            manager.run()
            assert manager.charm.certificates == set(_raw.CA_CERTS[:1])


def test_several_providers_on_one_endpoint(juju: _juju.Juju, mocked: None):
    """A stand-in stands for one application, so several issuers take one each."""
    app = _deploy(juju)
    issuers = [
        juju.deploy(certificate_transfer_testing.provider(certificates=[pem]), app=name)
        for name, pem in (('root-ca', ROOT), ('intermediate-ca', INTERMEDIATE))
    ]
    for issuer in issuers:
        juju.integrate(app, issuer)
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.certificates == {ROOT, INTERMEDIATE}


def test_a_later_turn_of_the_conversation(juju: _juju.Juju, mocked: None):
    """The provider rotates its CA, and the charm's trust store follows.

    There is no public way to change a deployed stand-in's arguments, so this deploys a
    replacement -- the fallback OP093 documents for behaviour with no config shape.
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(certificate_transfer_testing.provider(), app='ca'))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        before = manager.charm.certificates or set()
    rotated = juju.deploy(
        certificate_transfer_testing.provider(certificates=[ROOT]), app='rotated-ca'
    )
    juju.integrate(app, rotated)
    juju.settle()
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.certificates == before | {ROOT}
