# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for the stand-in charms' own contract, as OP093 specifies it.

These read relation data directly, which a charm test should never do -- the point of the
package is that charm tests don't have to. Here it is the subject.
"""

from __future__ import annotations

import dataclasses
import typing

import ops
import pytest

import _juju
import provider_charm
import requirer_charm

# The aliased form keeps these on separate lines, which a namespace package split across
# two distributions needs for pyright to resolve both halves.
from charmlibs.interfaces import {{ cookiecutter.__pkg }} as {{ cookiecutter.__pkg }}
from charmlibs.interfaces import {{ cookiecutter.__pkg }}_testing as {{ cookiecutter.__pkg }}_testing

JUJU_NETWORK_KEYS = {'egress-subnets', 'ingress-address', 'private-address'}


def _interface_keys(databag: typing.Mapping[str, str]) -> set[str]:
    """Return only the interface's own keys, excluding Juju's network ones."""
    return set(databag) - JUJU_NETWORK_KEYS


# ---------------------------------------------------------------- construction & identity


def test_provider_and_requirer_are_callable_with_no_arguments():
    """OP093: both must be callable with no arguments, defaulting to the happy path."""
    assert {{ cookiecutter.__pkg }}_testing.provider() is not None
    assert {{ cookiecutter.__pkg }}_testing.requirer() is not None


@pytest.mark.parametrize(
    'function', [{{ cookiecutter.__pkg }}_testing.provider, {{ cookiecutter.__pkg }}_testing.requirer]
)
def test_every_argument_is_keyword_only(function: typing.Callable[..., typing.Any]):
    """OP093: all arguments must be optional and keyword-only."""
    with pytest.raises(TypeError):
        function('endpoint')


@pytest.mark.parametrize(
    ('function', 'name'),
    [
        ({{ cookiecutter.__pkg }}_testing.provider, '{{ cookiecutter.project_slug }}-provider'),
        ({{ cookiecutter.__pkg }}_testing.requirer, '{{ cookiecutter.project_slug }}-requirer'),
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
    assert endpoints == {'endpoint': {'interface': '{{ cookiecutter.project_slug }}'}}


@pytest.mark.parametrize(
    'function', [{{ cookiecutter.__pkg }}_testing.provider, {{ cookiecutter.__pkg }}_testing.requirer]
)
def test_the_result_is_a_charm_data(function: typing.Callable[..., typing.Any]):
    """The shape OP089 specifies: charm type, metadata, and the package's mocking."""
    data: {{ cookiecutter.__pkg }}_testing.CharmData[ops.CharmBase] = function()
    assert isinstance(data, {{ cookiecutter.__pkg }}_testing.CharmData)
    assert issubclass(data.charm_type, ops.CharmBase)
    assert data.mocking is {{ cookiecutter.__pkg }}_testing.mocked


@pytest.mark.parametrize(
    'function', [{{ cookiecutter.__pkg }}_testing.provider, {{ cookiecutter.__pkg }}_testing.requirer]
)
def test_the_result_is_immutable_and_reusable(function: typing.Callable[..., typing.Any]):
    """OP093: a single result may be deployed any number of times, behaving identically."""
    data = function()
    assert dataclasses.is_dataclass(data)
    with pytest.raises(dataclasses.FrozenInstanceError):
        data.meta = {}  # pyright: ignore[reportAttributeAccessIssue]
    # Two calls with equal arguments produce distinct but interchangeable results.
    assert function() is not function()


@pytest.mark.parametrize(
    'function', [{{ cookiecutter.__pkg }}_testing.provider, {{ cookiecutter.__pkg }}_testing.requirer]
)
def test_the_metadata_is_deeply_frozen(function: typing.Callable[..., typing.Any]):
    """OP093: meta can't be changed through one result and so affect every other result."""
    data = function()
    role = 'provides' if 'provides' in data.meta else 'requires'
    with pytest.raises(TypeError):
        data.meta['name'] = 'x'
    with pytest.raises(TypeError):
        data.meta[role] = {}
    with pytest.raises(TypeError):
        data.meta[role]['endpoint'] = {}
    with pytest.raises(TypeError):
        data.meta[role]['endpoint']['interface'] = 'x'
    other = function()
    assert other.meta == data.meta
    assert other.meta[role]['endpoint'] == {'interface': '{{ cookiecutter.project_slug }}'}


def test_the_stand_in_charm_classes_are_private():
    """Nothing a test does with a stand-in needs the concrete class."""
    for data in ({{ cookiecutter.__pkg }}_testing.provider(), {{ cookiecutter.__pkg }}_testing.requirer()):
        assert data.charm_type.__name__ in ('_ProviderCharm', '_RequirerCharm')
        assert data.charm_type.__module__ == (
            '{{ cookiecutter.__import_pkg }}_testing._testing'
        )
        assert not hasattr({{ cookiecutter.__pkg }}_testing, data.charm_type.__name__)


# ------------------------------------------------------------------ argument validation

# FIXME: add a test per argument you give provider() and requirer(): that an invalid
# value raises ValueError at call time, and that a valid one changes what the stand-in
# writes. OP093 requires invalid arguments to raise when the function is called, not when
# the stand-in is deployed.


# ------------------------------------------------- the stand-in provider: what it writes


def test_provider_deploys_integrates_and_settles(juju: _juju.Juju, mocked: None):
    """The scaffold's stand-in writes nothing yet, so the model settles immediately.

    FIXME: once the stand-in answers, assert on what it writes here -- through the
    library's accessors where you can, and on the stand-in's own state
    (``remote.leader.state``) where the wire format is the subject.
    """
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    remote = juju.deploy({{ cookiecutter.__pkg }}_testing.provider())
    juju.integrate(app, remote)
    juju.settle()
    (relation,) = _juju.relations(remote.leader.state, 'endpoint')
    assert not _interface_keys(relation.local_app_data)
    assert not _interface_keys(relation.local_unit_data)


def test_provider_respond_false_writes_nothing(juju: _juju.Juju, mocked: None):
    """OP093: a stand-in that joins the relation but writes nothing."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    remote = juju.deploy({{ cookiecutter.__pkg }}_testing.provider(respond=False))
    juju.integrate(app, remote)
    juju.settle()
    (relation,) = _juju.relations(remote.leader.state, 'endpoint')
    assert not _interface_keys(relation.local_app_data)
    assert not _interface_keys(relation.local_unit_data)


@pytest.mark.skip(reason='FIXME: implement the stand-in provider, then this.')
def test_provider_derives_its_answer_from_what_the_charm_published():
    """The conformance test OP093 requires: two charms asking for different things.

    A stand-in that ignored the charm's relation data and wrote canned values would
    satisfy every other clause of the spec while reintroducing exactly the silent
    mismatches the package exists to prevent. This is the one property that can't be
    checked by reading a signature, so every testing package must have this test: deploy
    two charms that ask for different things, integrate both with one stand-in, and
    assert that the stand-in's data differs accordingly. Delete this test instead if this
    role's stand-in writes *first*, since then there is nothing to derive from.
    """


@pytest.mark.skip(reason='FIXME: implement the stand-in provider, then this.')
def test_provider_reconciles_when_the_charm_changes_what_it_asks_for():
    """The other conformance test OP093 requires: the answer to the old request is gone.

    Make the charm under test change what it asks for -- a config change is the usual
    way -- settle, and assert that the stand-in's answer to the old request is gone,
    while the answers still warranted remain.
    """


# ------------------------------------------------- the stand-in requirer: what it writes


def test_requirer_deploys_integrates_and_settles(juju: _juju.Juju, mocked: None):
    """The scaffold's stand-in writes nothing yet, so the model settles immediately.

    FIXME: as for the provider test above.
    """
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    remote = juju.deploy({{ cookiecutter.__pkg }}_testing.requirer())
    juju.integrate(app, remote)
    juju.settle()
    (relation,) = _juju.relations(remote.leader.state, 'endpoint')
    assert not _interface_keys(relation.local_app_data)
    assert not _interface_keys(relation.local_unit_data)


def test_requirer_respond_false_writes_nothing(juju: _juju.Juju, mocked: None):
    """OP093: a stand-in that joins the relation but writes nothing."""
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    remote = juju.deploy({{ cookiecutter.__pkg }}_testing.requirer(respond=False))
    juju.integrate(app, remote)
    juju.settle()
    (relation,) = _juju.relations(remote.leader.state, 'endpoint')
    assert not _interface_keys(relation.local_app_data)
    assert not _interface_keys(relation.local_unit_data)


@pytest.mark.skip(reason='FIXME: implement the stand-in requirer, then this.')
def test_requirer_derives_its_request_from_what_the_charm_published():
    """The conformance test OP093 requires, where the charm writes first.

    Delete this test if the requirer writes *first* on this interface -- the usual case
    for a request-response interface -- since then there is nothing to derive from, and
    the request comes from ``requirer()``'s arguments.
    """


@pytest.mark.skip(reason='FIXME: implement the stand-in requirer, then this.')
def test_requirer_reconciles_when_the_charm_changes_what_it_publishes():
    """The other conformance test OP093 requires: stale data is removed.

    Where the stand-in's data derives from the charm's, change what the charm publishes,
    settle, and assert the stale answer is gone. Where the stand-in writes first, test
    instead that its library reconciles its own writes when its arguments change -- by
    deploying a replacement stand-in, the fallback OP093 documents for behaviour with no
    config shape.
    """
