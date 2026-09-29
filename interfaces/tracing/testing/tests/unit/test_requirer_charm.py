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
import requirer_charm_multi
from charmlibs.interfaces import tracing_testing as tracing_testing

if typing.TYPE_CHECKING:
    import _juju


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
    """Without a tracing relation there is nothing to be ready for."""
    app = _deploy(juju)
    juju.dispatch(app.leader, 'update-status')
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.BlockedStatus)


def test_the_happy_path(juju: _juju.Juju, mocked: None):
    """The whole conversation, with nothing to keep in agreement with the charm."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tracing_testing.provider()))
    juju.settle()
    assert isinstance(app.leader.state.unit_status, ops.ActiveStatus)


def test_the_charm_has_a_url_per_protocol(juju: _juju.Juju, mocked: None):
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tracing_testing.provider()))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.endpoints == {
            'otlp_http': 'http://tracing.example.com:4318',
            'zipkin': 'http://tracing.example.com:9411',
        }


def test_related_but_unanswered(juju: _juju.Juju, mocked: None):
    """The most common real intermediate state: asked, but nobody has answered.

    The charm should report blocked because the provider hasn't answered -- not because it
    failed to ask.
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tracing_testing.provider(respond=False)))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        state_out = manager.run()
        assert manager.charm.endpoints is None
    assert isinstance(state_out.unit_status, ops.BlockedStatus)


def test_provider_supports_only_some_protocols(juju: _juju.Juju, mocked: None):
    """A provider answers with the protocols it has and omits the rest."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tracing_testing.provider(supported_protocols=['otlp_http'])))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        state_out = manager.run()
        assert manager.charm.endpoints == {'otlp_http': 'http://tracing.example.com:4318'}
    assert isinstance(state_out.unit_status, ops.BlockedStatus)


def test_provider_supporting_none_of_them(juju: _juju.Juju, mocked: None):
    """An empty answer is still an answer: the charm is ready, with no endpoints."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tracing_testing.provider(supported_protocols=[])))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        state_out = manager.run()
        assert manager.charm.endpoints == {}
    assert isinstance(state_out.unit_status, ops.BlockedStatus)


def test_provider_behind_tls(juju: _juju.Juju, mocked: None):
    """``tls=True`` makes the HTTP protocols' URLs https, which charms often branch on."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tracing_testing.provider(tls=True)))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.endpoints == {
            'otlp_http': 'https://tracing.example.com:4318',
            'zipkin': 'https://tracing.example.com:9411',
        }


def test_provider_on_a_custom_host(juju: _juju.Juju, mocked: None):
    """``host`` is there for a charm that cares which address it was given."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tracing_testing.provider(host='tempo.example.org')))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.endpoints == {
            'otlp_http': 'http://tempo.example.org:4318',
            'zipkin': 'http://tempo.example.org:9411',
        }


def test_a_non_leader_requirer_never_asks_but_reads(juju: _juju.Juju, mocked: None):
    """A non-leader requirer can't write the request, but reads the leader's answer.

    The request lives in the application databag, which only the leader writes -- and the
    answer lives there too, which every unit may read.
    """
    app = _deploy(juju, num_units=2)
    juju.integrate(app, juju.deploy(tracing_testing.provider()))
    juju.settle()
    non_leader = app.units[1]
    ctx = _ctx(non_leader)
    with ctx(ctx.on.update_status(), non_leader.state) as manager:
        state_out = manager.run()
        assert manager.charm.endpoints == {
            'otlp_http': 'http://tracing.example.com:4318',
            'zipkin': 'http://tracing.example.com:9411',
        }
    assert isinstance(state_out.unit_status, ops.ActiveStatus)


def test_a_multi_unit_requirer_shares_one_request(juju: _juju.Juju, mocked: None):
    """The request lives in the application databag, so every unit reads the leader's."""
    app = _deploy(juju, num_units=3)
    juju.integrate(app, juju.deploy(tracing_testing.provider()))
    juju.settle()
    for unit in app.units:
        ctx = _ctx(unit)
        with ctx(ctx.on.update_status(), unit.state) as manager:
            manager.run()
            assert manager.charm.endpoints == {
                'otlp_http': 'http://tracing.example.com:4318',
                'zipkin': 'http://tracing.example.com:9411',
            }


def test_a_later_turn_of_the_conversation(juju: _juju.Juju, mocked: None):
    """The charm asks for something different, and the stand-in's answer follows.

    Here the charm is reconfigured to stop sending zipkin traces. The stand-in drops the
    receiver for the protocol that is no longer asked for, which is what a real provider
    does.
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(tracing_testing.provider()))
    juju.settle()
    juju.config(app, {'protocols': 'otlp_http'})
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.endpoints == {'otlp_http': 'http://tracing.example.com:4318'}


def test_several_providers_on_one_endpoint(juju: _juju.Juju, mocked: None):
    """A stand-in stands for one application, so several backends take one each."""
    app = juju.deploy(requirer_charm_multi.MultiRequirerCharm, meta=requirer_charm_multi.META)
    backends = [
        juju.deploy(tracing_testing.provider(host=f'{name}.example.com'), app=name)
        for name in ('tempo', 'jaeger')
    ]
    for backend in backends:
        juju.integrate(app, backend)
    juju.settle()
    ctx = ops.testing.Context(
        requirer_charm_multi.MultiRequirerCharm,
        meta=requirer_charm_multi.META,
        app_name=app.name,
        unit_id=app.leader.id,
    )
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
        assert manager.charm.endpoints == {
            'tempo': 'http://tempo.example.com:4318',
            'jaeger': 'http://jaeger.example.com:4318',
        }
