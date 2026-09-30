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
import json
import typing

import ops
import pytest

import _juju
import provider_charm
import requirer_charm

# The aliased form keeps these on separate lines, which a namespace package split across
# two distributions needs for pyright to resolve both halves.
from charmlibs.interfaces import tracing as tracing
from charmlibs.interfaces import tracing_testing as tracing_testing

JUJU_NETWORK_KEYS = {'egress-subnets', 'ingress-address', 'private-address'}


def _wire(databag: typing.Mapping[str, str]) -> typing.Any:
    """The ``receivers`` value a databag carries, or ``None`` if it carries none."""
    raw = databag.get('receivers')
    return None if raw is None else json.loads(raw)


def _protocol_names(receivers: typing.Any) -> list[str]:
    """The protocol names in a provider's published receiver list."""
    return [receiver['protocol']['name'] for receiver in receivers]


def _interface_keys(databag: typing.Mapping[str, str]) -> set[str]:
    """Return only the interface's own keys, excluding Juju's network ones."""
    return set(databag) - JUJU_NETWORK_KEYS


def _charm_requesting(protocols: list[tracing.ReceiverProtocol]) -> type[ops.CharmBase]:
    """Return a requirer charm class asking for exactly ``protocols``."""

    class Charm(ops.CharmBase):
        def __init__(self, framework: ops.Framework):
            super().__init__(framework)
            self.tracing = tracing.TracingEndpointRequirer(self, protocols=protocols)

    return Charm


# ---------------------------------------------------------------- construction & identity


def test_provider_and_requirer_are_callable_with_no_arguments():
    """OP093: both must be callable with no arguments, defaulting to the happy path."""
    assert tracing_testing.provider() is not None
    assert tracing_testing.requirer() is not None


@pytest.mark.parametrize('function', [tracing_testing.provider, tracing_testing.requirer])
def test_every_argument_is_keyword_only(function: typing.Callable[..., typing.Any]):
    """OP093: all arguments must be optional and keyword-only."""
    with pytest.raises(TypeError):
        function('tracing')


@pytest.mark.parametrize(
    ('function', 'name'),
    [
        (tracing_testing.provider, 'tracing-provider'),
        (tracing_testing.requirer, 'tracing-requirer'),
    ],
)
def test_the_stand_ins_metadata(function: typing.Callable[..., typing.Any], name: str):
    """OP093: meta names the library and role, and declares exactly one endpoint."""
    data = function()
    assert data.meta['name'] == name
    endpoints = {
        endpoint: spec
        for role in ('provides', 'requires')
        for endpoint, spec in data.meta.get(role, {}).items()
    }
    assert endpoints == {'tracing': {'interface': 'tracing'}}


@pytest.mark.parametrize('function', [tracing_testing.provider, tracing_testing.requirer])
def test_the_result_is_a_charm_data(function: typing.Callable[..., typing.Any]):
    """The shape OP089 specifies: charm type, metadata, and the package's mocking."""
    data: tracing_testing.CharmData[ops.CharmBase] = function()
    assert isinstance(data, tracing_testing.CharmData)
    assert issubclass(data.charm_type, ops.CharmBase)
    assert data.mocking is tracing_testing.mocked


@pytest.mark.parametrize('function', [tracing_testing.provider, tracing_testing.requirer])
def test_the_result_is_immutable_and_reusable(function: typing.Callable[..., typing.Any]):
    """OP093: a single result may be deployed any number of times, behaving identically."""
    data = function()
    assert dataclasses.is_dataclass(data)
    with pytest.raises(dataclasses.FrozenInstanceError):
        data.meta = {}  # pyright: ignore[reportAttributeAccessIssue]
    # Two calls with equal arguments produce distinct but interchangeable results.
    assert function() is not function()


@pytest.mark.parametrize('function', [tracing_testing.provider, tracing_testing.requirer])
def test_the_metadata_is_deeply_frozen(function: typing.Callable[..., typing.Any]):
    """OP093: meta can't be changed through one result and so affect every other result."""
    data = function()
    role = 'provides' if 'provides' in data.meta else 'requires'
    with pytest.raises(TypeError):
        data.meta['name'] = 'x'
    with pytest.raises(TypeError):
        data.meta[role] = {}
    with pytest.raises(TypeError):
        data.meta[role]['tracing'] = {}
    with pytest.raises(TypeError):
        data.meta[role]['tracing']['interface'] = 'x'
    other = function()
    assert other.meta == data.meta
    assert other.meta[role]['tracing'] == {'interface': 'tracing'}


def test_the_stand_in_charm_classes_are_private():
    """Nothing a test does with a stand-in needs the concrete class."""
    for data in (tracing_testing.provider(), tracing_testing.requirer()):
        assert data.charm_type.__name__ in ('_ProviderCharm', '_RequirerCharm')
        assert data.charm_type.__module__ == 'charmlibs.interfaces.tracing_testing._testing'
        assert not hasattr(tracing_testing, data.charm_type.__name__)


# ------------------------------------------------------------------ argument validation


def test_provider_rejects_a_protocol_the_interface_does_not_define():
    """Misuse raises early, at call time, rather than quietly answering nothing."""
    with pytest.raises(ValueError, match='does not define'):
        tracing_testing.provider(
            supported_protocols=['otlp_http', typing.cast('typing.Any', 'smoke_signals')]
        )


def test_requirer_rejects_a_protocol_the_interface_does_not_define():
    with pytest.raises(ValueError, match='does not define'):
        tracing_testing.requirer(protocols=[typing.cast('typing.Any', 'smoke_signals')])


def test_requirer_rejects_an_empty_request():
    """``request_protocols`` rejects one too -- a requirer that wants nothing doesn't write."""
    with pytest.raises(ValueError, match='at least one protocol'):
        tracing_testing.requirer(protocols=[])


def test_provider_accepts_supporting_nothing():
    """Distinct from the default: this provider answers, and its answer is empty."""
    assert tracing_testing.provider(supported_protocols=[]) is not None
    assert tracing_testing.provider() is not None


def test_provider_normalises_its_protocol_iterable(juju: _juju.Juju, mocked: None):
    """A stand-in is deployed any number of times, so a one-shot iterator must not be
    consumed once.
    """
    protocols: list[tracing.ReceiverProtocol] = ['otlp_http']
    data = tracing_testing.provider(supported_protocols=iter(protocols))
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    first = juju.deploy(data, app='first')
    juju.integrate(app, first)
    second = juju.deploy(data, app='second')
    juju.integrate(app, second)
    juju.settle()
    for stand_in in (first, second):
        (relation,) = _juju.relations(stand_in.leader.state, 'tracing')
        assert _protocol_names(_wire(relation.local_app_data)) == ['otlp_http']


# ------------------------------------------------- the stand-in provider: what it writes


def test_provider_derives_its_answer_from_what_the_charm_published(juju: _juju.Juju, mocked: None):
    """The conformance test OP093 requires: two charms asking for different things.

    A provider that ignored the charm's relation data and wrote canned values would satisfy
    every other clause of the spec while reintroducing exactly the silent mismatches the
    package exists to prevent. This is the one property that can't be checked by reading a
    signature.
    """
    published: list[list[str]] = []
    for name, protocols in (
        ('first', ['otlp_http']),
        ('second', ['zipkin', 'jaeger_grpc']),
    ):
        # One stand-in per model: the provider aggregates over every relation on its
        # endpoint, so two charms in one model would be answered with the union.
        with _juju.Juju() as model:
            tempo = model.deploy(tracing_testing.provider())
            app = model.deploy(
                _charm_requesting(typing.cast('list[tracing.ReceiverProtocol]', protocols)),
                app=name,
                meta=requirer_charm.META,
            )
            model.integrate(app, tempo)
            model.settle()
            (relation,) = _juju.relations(tempo.leader.state, 'tracing')
            published.append(_protocol_names(_wire(relation.local_app_data)))
    assert published[0] == ['otlp_http']
    assert published[1] == ['jaeger_grpc', 'zipkin']
    assert published[0] != published[1]


def test_provider_reconciles_when_the_charm_changes_what_it_asks_for(
    juju: _juju.Juju, mocked: None
):
    """The other conformance test OP093 requires: the answer to the old request is gone.

    The charm re-requests on ``update-status`` -- the example charm asks for whatever its
    config names -- and the stand-in drops the receiver for the protocol that is no longer
    asked for, which is what the real provider's library does.
    """
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    tempo = juju.deploy(tracing_testing.provider())
    juju.integrate(app, tempo)
    juju.settle()
    (relation,) = _juju.relations(tempo.leader.state, 'tracing')
    assert _protocol_names(_wire(relation.local_app_data)) == ['otlp_http', 'zipkin']
    # The charm now asks for otlp_http alone.
    juju.config(app, {'protocols': 'otlp_http'})
    juju.settle()
    (relation,) = _juju.relations(tempo.leader.state, 'tracing')
    assert _protocol_names(_wire(relation.local_app_data)) == ['otlp_http']


def test_provider_answers_each_relation_independently(juju: _juju.Juju, mocked: None):
    """A stand-in integrated with several applications writes each relation's own databag.

    The library's provider API aggregates the protocols requested across every relation
    and publishes the union to each -- which is what a real provider does, since its
    receivers serve every requirer at once. What stays independent is the databag itself:
    each relation carries the stand-in's own answer, derived from what was asked.
    """
    tempo = juju.deploy(tracing_testing.provider())
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    other = juju.deploy(_charm_requesting(['zipkin']), app='other', meta=requirer_charm.META)
    juju.integrate(app, tempo)
    juju.integrate(other, tempo)
    juju.settle()
    answers = {
        relation.remote_app_name: _protocol_names(_wire(relation.local_app_data))
        for relation in _juju.relations(tempo.leader.state, 'tracing')
    }
    # The union of both requests, on each relation.
    assert answers == {
        'requirer': ['otlp_http', 'zipkin'],
        'other': ['otlp_http', 'zipkin'],
    }


def test_provider_answers_only_the_protocols_it_supports(juju: _juju.Juju, mocked: None):
    """A provider answers with the protocols it has and omits the rest."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    tempo = juju.deploy(tracing_testing.provider(supported_protocols=['otlp_http']))
    juju.integrate(app, tempo)
    juju.settle()
    (relation,) = _juju.relations(tempo.leader.state, 'tracing')
    assert _protocol_names(_wire(relation.local_app_data)) == ['otlp_http']


def test_provider_supporting_nothing_publishes_an_empty_answer(juju: _juju.Juju, mocked: None):
    """Not the same as having nothing to answer -- this is an answer, and it is empty.

    A requirer can tell the two apart: ``is_ready`` is false where nothing was published,
    and true where an empty receiver list was.
    """
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    tempo = juju.deploy(tracing_testing.provider(supported_protocols=[]))
    juju.integrate(app, tempo)
    juju.settle()
    (relation,) = _juju.relations(tempo.leader.state, 'tracing')
    assert _wire(relation.local_app_data) == []


def test_provider_urls_carry_the_host_port_and_scheme(juju: _juju.Juju, mocked: None):
    """Each protocol on its usual port; https for the HTTP protocols when tls=True."""
    app = juju.deploy(
        _charm_requesting(['otlp_http', 'otlp_grpc', 'zipkin']), meta=requirer_charm.META
    )
    tempo = juju.deploy(tracing_testing.provider(host='tempo.example.org', tls=True))
    juju.integrate(app, tempo)
    juju.settle()
    (relation,) = _juju.relations(tempo.leader.state, 'tracing')
    urls = {
        receiver['protocol']['name']: receiver['url']
        for receiver in _wire(relation.local_app_data)
    }
    assert urls == {
        # gRPC URLs carry no scheme, as the interface requires.
        'otlp_grpc': 'tempo.example.org:4317',
        'otlp_http': 'https://tempo.example.org:4318',
        'zipkin': 'https://tempo.example.org:9411',
    }


def test_provider_respond_false_writes_nothing(juju: _juju.Juju, mocked: None):
    """OP093: a stand-in that joins the relation but writes nothing."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    tempo = juju.deploy(tracing_testing.provider(respond=False))
    juju.integrate(app, tempo)
    juju.settle()
    (relation,) = _juju.relations(tempo.leader.state, 'tracing')
    assert not _interface_keys(relation.local_app_data)
    # The charm asked; nobody answered.
    assert _wire(relation.remote_app_data) == requirer_charm.PROTOCOLS


def test_provider_writes_nothing_until_the_charm_asks(juju: _juju.Juju, mocked: None):
    """A stand-in deployed incidentally, while the test is about something else, is not
    obstructed: with nothing published to answer, it writes nothing.
    """
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    tempo = juju.deploy(tracing_testing.provider())
    juju.integrate(app, tempo)
    # Settle only the stand-in's side of the integration events: the charm under test has
    # not run yet, so there is no request on the wire.
    for _ in range(3):
        unit, name, factory = juju._queue.popleft()
        if unit.app is tempo:
            juju._run(unit, name, factory)
        else:
            juju._queue.append((unit, name, factory))
    (relation,) = _juju.relations(tempo.leader.state, 'tracing')
    assert not _interface_keys(relation.local_app_data)


# ------------------------------------------------- the stand-in requirer: what it writes


def test_requirer_writes_its_request_to_the_application_databag(juju: _juju.Juju, mocked: None):
    """``tracing`` requirers write to the application databag only."""
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    workload = juju.deploy(tracing_testing.requirer())
    juju.integrate(app, workload)
    juju.settle()
    (relation,) = _juju.relations(workload.leader.state, 'tracing')
    assert _wire(relation.local_app_data) == ['otlp_http']
    assert set(relation.local_unit_data) <= JUJU_NETWORK_KEYS


def test_requirer_asks_for_the_protocols_it_was_given(juju: _juju.Juju, mocked: None):
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    workload = juju.deploy(tracing_testing.requirer(protocols=['zipkin', 'otlp_grpc']))
    juju.integrate(app, workload)
    juju.settle()
    (relation,) = _juju.relations(workload.leader.state, 'tracing')
    assert _wire(relation.local_app_data) == ['zipkin', 'otlp_grpc']


def test_requirer_respond_false_writes_nothing(juju: _juju.Juju, mocked: None):
    """OP093: a stand-in that joins the relation but writes nothing."""
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    workload = juju.deploy(tracing_testing.requirer(respond=False))
    juju.integrate(app, workload)
    juju.settle()
    (relation,) = _juju.relations(workload.leader.state, 'tracing')
    assert not _interface_keys(relation.local_app_data)
    assert set(relation.local_unit_data) <= JUJU_NETWORK_KEYS


def test_requirer_reconciles_when_its_request_changes(juju: _juju.Juju, mocked: None):
    """The stand-in requirer derives nothing, but its library still reconciles: protocols
    it no longer asks for are removed from the relation, which is what a real requirer's
    library does when its configuration changes.

    There is no public way to change a deployed stand-in's arguments, so this deploys a
    replacement -- the fallback OP093 documents for behaviour with no config shape.
    """
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    before = juju.deploy(
        tracing_testing.requirer(protocols=['otlp_http', 'zipkin']), app='workload'
    )
    juju.integrate(app, before)
    juju.settle()
    (relation,) = _juju.relations(before.leader.state, 'tracing')
    assert _wire(relation.local_app_data) == ['otlp_http', 'zipkin']
    # Replacing the application is the documented fallback; the new stand-in asks only for
    # what it was given.
    after = juju.deploy(tracing_testing.requirer(protocols=['zipkin']), app='replacement')
    juju.integrate(app, after)
    juju.settle()
    (relation,) = _juju.relations(after.leader.state, 'tracing')
    assert _wire(relation.local_app_data) == ['zipkin']
