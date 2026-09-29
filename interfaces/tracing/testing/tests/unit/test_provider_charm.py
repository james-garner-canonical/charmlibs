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
sides need: ``TracingEndpointRequirer`` writes its request to the application databag, and
``TracingEndpointProvider.publish_receivers`` writes the answer there too.
"""

from __future__ import annotations

import typing

import ops
import ops.testing

import provider_charm
from charmlibs.interfaces import tracing as tracing
from charmlibs.interfaces import tracing_testing as tracing_testing

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


def test_no_relation(juju: _juju.Juju, mocked: None):
    """Nobody is asking for anything, so nothing is enabled."""
    app = _deploy(juju)
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.enabled is None


def test_the_happy_path(juju: _juju.Juju, mocked: None):
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tracing_testing.requirer()))
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.ActiveStatus)


def test_the_charm_answers_the_protocols_asked_for(juju: _juju.Juju, mocked: None):
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tracing_testing.requirer(protocols=['otlp_grpc'])))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.enabled == ['otlp_grpc']


def test_a_silent_requirer_asks_for_nothing(juju: _juju.Juju, mocked: None):
    """respond=False: the stand-in joins the relation and writes nothing."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tracing_testing.requirer(respond=False)))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.enabled is None


def test_a_non_leader_provider_answers_nothing(juju: _juju.Juju, mocked: None):
    """Publishing is leader-only, so a non-leader reads the request and does nothing."""
    app = _deploy(juju, num_units=2)
    juju.integrate(app, juju.deploy(tracing_testing.requirer()))
    juju.settle()
    non_leader = app.units[1]
    ctx = _ctx(non_leader)
    with ctx(ctx.on.update_status(), non_leader.state) as manager:
        manager.run()
        assert manager.charm.enabled == ['otlp_http']  # it read the request
    assert isinstance(non_leader.state.unit_status, ops.ActiveStatus)


def test_several_requirers_on_one_endpoint(juju: _juju.Juju, mocked: None):
    """A stand-in stands for one application, so aggregating over several takes one each."""
    app = _deploy(juju)
    pairs: list[tuple[str, tracing.ReceiverProtocol]] = [
        ('charm-traces', 'otlp_http'),
        ('workload-traces', 'otlp_grpc'),
    ]
    workloads = [
        juju.deploy(tracing_testing.requirer(protocols=[protocol]), app=name)
        for name, protocol in pairs
    ]
    for workload in workloads:
        juju.integrate(app, workload)
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.enabled == ['otlp_grpc', 'otlp_http']


def test_a_later_turn_of_the_conversation(juju: _juju.Juju, mocked: None):
    """The workload is reconfigured to send traces over gRPC instead.

    There is no public way to change a deployed stand-in's arguments, so this deploys a
    replacement -- the fallback OP093 documents for behaviour with no config shape.
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tracing_testing.requirer(), app='workload'))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.enabled == ['otlp_http']
    replacement = juju.deploy(tracing_testing.requirer(protocols=['otlp_grpc']), app='replacement')
    juju.integrate(app, replacement)
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.enabled == ['otlp_grpc', 'otlp_http']
