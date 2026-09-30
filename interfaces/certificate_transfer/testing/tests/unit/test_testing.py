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
import ops.testing
import pytest

import _juju
import provider_charm
import requirer_charm

# The aliased form keeps these on separate lines, which a namespace package split across
# two distributions needs for pyright to resolve both halves.
from charmlibs.interfaces import certificate_transfer as certificate_transfer
from charmlibs.interfaces import certificate_transfer_testing as certificate_transfer_testing
from charmlibs.interfaces.certificate_transfer_testing import _raw

JUJU_NETWORK_KEYS = {'egress-subnets', 'ingress-address', 'private-address'}

ROOT = '-----BEGIN CERTIFICATE-----\nroot\n-----END CERTIFICATE-----'
INTERMEDIATE = '-----BEGIN CERTIFICATE-----\nintermediate\n-----END CERTIFICATE-----'


def _interface_keys(databag: typing.Mapping[str, str]) -> set[str]:
    """Return only the interface's own keys, excluding Juju's network ones."""
    return set(databag) - JUJU_NETWORK_KEYS


def _transferred(relation: ops.testing.Relation) -> set[str] | None:
    """The certificates the stand-in provider has published, straight off the wire.

    Looks in both of the interface's wire formats, and returns ``None`` where the stand-in
    has written neither. Nothing else in this repository reads a databag this way; that is
    the point of the package.
    """
    if 'certificates' in relation.local_app_data:
        return set(json.loads(relation.local_app_data['certificates']))
    if 'chain' in relation.local_unit_data:
        return set(json.loads(relation.local_unit_data['chain']))
    return None


def _wire_version(relation: ops.testing.Relation) -> int | None:
    """Which of the interface's two formats the stand-in wrote in, or ``None`` for neither."""
    if 'certificates' in relation.local_app_data:
        return 1
    if 'chain' in relation.local_unit_data:
        return 0
    return None


# ---------------------------------------------------------------- construction & identity


def test_provider_and_requirer_are_callable_with_no_arguments():
    """OP093: both must be callable with no arguments, defaulting to the happy path."""
    assert certificate_transfer_testing.provider() is not None
    assert certificate_transfer_testing.requirer() is not None


@pytest.mark.parametrize(
    'function', [certificate_transfer_testing.provider, certificate_transfer_testing.requirer]
)
def test_every_argument_is_keyword_only(function: typing.Callable[..., typing.Any]):
    """OP093: all arguments must be optional and keyword-only."""
    with pytest.raises(TypeError):
        function('certificates')


@pytest.mark.parametrize(
    ('function', 'name'),
    [
        (certificate_transfer_testing.provider, 'certificate-transfer-provider'),
        (certificate_transfer_testing.requirer, 'certificate-transfer-requirer'),
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
    assert endpoints == {'certificates': {'interface': 'certificate_transfer'}}


@pytest.mark.parametrize(
    'function', [certificate_transfer_testing.provider, certificate_transfer_testing.requirer]
)
def test_the_result_is_a_charm_data(function: typing.Callable[..., typing.Any]):
    """The shape OP089 specifies: charm type, metadata, and the package's mocking."""
    data: certificate_transfer_testing.CharmData[ops.CharmBase] = function()
    assert isinstance(data, certificate_transfer_testing.CharmData)
    assert issubclass(data.charm_type, ops.CharmBase)
    assert data.mocking is certificate_transfer_testing.mocked


@pytest.mark.parametrize(
    'function', [certificate_transfer_testing.provider, certificate_transfer_testing.requirer]
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
    'function', [certificate_transfer_testing.provider, certificate_transfer_testing.requirer]
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
        data.meta[role]['certificates'] = {}
    with pytest.raises(TypeError):
        data.meta[role]['certificates']['interface'] = 'x'
    other = function()
    assert other.meta == data.meta
    assert other.meta[role]['certificates'] == {'interface': 'certificate_transfer'}


def test_the_stand_in_charm_classes_are_private():
    """Nothing a test does with a stand-in needs the concrete class."""
    for data in (certificate_transfer_testing.provider(), certificate_transfer_testing.requirer()):
        assert data.charm_type.__name__ in ('_ProviderCharm', '_RequirerCharm')
        assert data.charm_type.__module__ == (
            'charmlibs.interfaces.certificate_transfer_testing._testing'
        )
        assert not hasattr(certificate_transfer_testing, data.charm_type.__name__)


# ------------------------------------------------------------------ argument validation


@pytest.mark.parametrize(
    'function', [certificate_transfer_testing.provider, certificate_transfer_testing.requirer]
)
def test_rejects_a_version_the_interface_does_not_have(function: typing.Callable[..., typing.Any]):
    """Misuse raises early, at call time, rather than quietly writing the wrong format."""
    with pytest.raises(ValueError, match='not a version'):
        function(interface_version=typing.cast('typing.Any', 2))


def test_requirer_rejects_no_version_at_all():
    """A requirer always has a version; v0's is spelled by writing nothing, not by None."""
    with pytest.raises(ValueError, match='not a version'):
        certificate_transfer_testing.requirer(interface_version=typing.cast('typing.Any', None))


def test_provider_accepts_deciding_the_version_for_itself(juju: _juju.Juju, mocked: None):
    """None is the default, and is distinct from being told to use v1."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    decided = juju.deploy(certificate_transfer_testing.provider(), app='decided')
    juju.integrate(app, decided)
    forced = juju.deploy(certificate_transfer_testing.provider(interface_version=1), app='forced')
    juju.integrate(app, forced)
    juju.settle()
    for stand_in in (decided, forced):
        (relation,) = _juju.relations(stand_in.leader.state, 'certificates')
        assert _wire_version(relation) == 1


def test_provider_accepts_having_nothing_to_transfer():
    """Distinct from the default: this provider answers, and its answer is empty."""
    assert certificate_transfer_testing.provider(certificates=[]) is not None
    assert certificate_transfer_testing.provider() is not None


def test_provider_normalises_its_certificate_iterable(juju: _juju.Juju, mocked: None):
    """A stand-in is deployed any number of times, so a one-shot iterator must not be
    consumed once.
    """
    data = certificate_transfer_testing.provider(certificates=iter([ROOT]))
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    first = juju.deploy(data, app='first')
    juju.integrate(app, first)
    second = juju.deploy(data, app='second')
    juju.integrate(app, second)
    juju.settle()
    for stand_in in (first, second):
        (relation,) = _juju.relations(stand_in.leader.state, 'certificates')
        assert _transferred(relation) == {ROOT}


# ------------------------------------------------- the stand-in provider: what it writes


def test_provider_derives_the_format_from_what_the_charm_published(juju: _juju.Juju, mocked: None):
    """The conformance test OP093 requires, as far as this interface has one.

    ``certificate_transfer`` is a one-way interface: the provider writes first, so there is
    nothing to derive the *certificates* from -- they come from the stand-in's arguments.
    What is derived is the *format* they are written in: v1 where the charm advertised
    ``version: 1``, v0 where it did not, exactly as the real provider library decides.
    """
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(certificate_transfer_testing.provider())
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _juju.relations(ca.leader.state, 'certificates')
    # The charm under test is a leader, so it advertised version 1, and is answered in v1.
    assert relation.remote_app_data.get('version') == '1'
    assert _wire_version(relation) == 1


def test_provider_reconciles_when_its_certificates_change(juju: _juju.Juju, mocked: None):
    """The other conformance test OP093 requires: the old answer is gone.

    The provider writes first on this interface, so "what the charm asks for" is the
    stand-in's own arguments. Replacing the stand-in -- the fallback OP093 documents for
    behaviour with no config shape -- leaves only what the replacement transfers.
    """
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    before = juju.deploy(
        certificate_transfer_testing.provider(certificates=[ROOT, INTERMEDIATE]), app='ca'
    )
    juju.integrate(app, before)
    juju.settle()
    (relation,) = _juju.relations(before.leader.state, 'certificates')
    assert _transferred(relation) == {ROOT, INTERMEDIATE}
    after = juju.deploy(certificate_transfer_testing.provider(certificates=[ROOT]), app='new-ca')
    juju.integrate(app, after)
    juju.settle()
    (relation,) = _juju.relations(after.leader.state, 'certificates')
    assert _transferred(relation) == {ROOT}


def test_provider_answers_each_relation_independently(juju: _juju.Juju, mocked: None):
    """A stand-in integrated with several applications writes each relation's own databag."""
    ca = juju.deploy(certificate_transfer_testing.provider(certificates=[ROOT]))
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    other = juju.deploy(requirer_charm.RequirerCharm, app='other', meta=requirer_charm.META)
    juju.integrate(app, ca)
    juju.integrate(other, ca)
    juju.settle()
    answers = {
        relation.remote_app_name: _transferred(relation)
        for relation in _juju.relations(ca.leader.state, 'certificates')
    }
    assert answers == {'requirer': {ROOT}, 'other': {ROOT}}


def test_provider_transfers_the_certificates_it_was_given(juju: _juju.Juju, mocked: None):
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(certificate_transfer_testing.provider(certificates=[ROOT, INTERMEDIATE]))
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _juju.relations(ca.leader.state, 'certificates')
    assert _transferred(relation) == {ROOT, INTERMEDIATE}


def test_provider_with_nothing_to_transfer_publishes_an_empty_answer(
    juju: _juju.Juju, mocked: None
):
    """Not the same as having nothing to say -- in v1 this is an answer, and it is empty."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(certificate_transfer_testing.provider(certificates=[]))
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _juju.relations(ca.leader.state, 'certificates')
    assert _transferred(relation) == set()


def test_provider_with_nothing_to_transfer_writes_nothing_in_v0(juju: _juju.Juju, mocked: None):
    """v0 has no way to say "none": ``ca`` and ``certificate`` are single required strings."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(certificate_transfer_testing.provider(certificates=[], interface_version=0))
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _juju.relations(ca.leader.state, 'certificates')
    assert _transferred(relation) is None
    assert not _interface_keys(relation.local_app_data)
    assert not _interface_keys(relation.local_unit_data)


def test_provider_forced_to_v0_writes_the_unit_databag(juju: _juju.Juju, mocked: None):
    """``interface_version=0`` models an old provider charm, answered in the v0 format."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(certificate_transfer_testing.provider(interface_version=0))
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _juju.relations(ca.leader.state, 'certificates')
    assert _wire_version(relation) == 0
    assert _transferred(relation) == set(_raw.CA_CERTS[:1])
    # And the v1 half of the conversation is not there.
    assert not _interface_keys(relation.local_app_data)


def test_provider_respond_false_writes_nothing(juju: _juju.Juju, mocked: None):
    """OP093: a stand-in that joins the relation but writes nothing."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(certificate_transfer_testing.provider(respond=False))
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _juju.relations(ca.leader.state, 'certificates')
    assert not _interface_keys(relation.local_app_data)
    assert not _interface_keys(relation.local_unit_data)
    # The charm advertised its version; nobody answered.
    assert relation.remote_app_data.get('version') == '1'


def test_provider_writes_nothing_until_it_is_leader(juju: _juju.Juju, mocked: None):
    """Transferring is leader-only, so a non-leader unit of the stand-in writes nothing."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(certificate_transfer_testing.provider(), num_units=2)
    juju.integrate(app, ca)
    juju.settle()
    non_leader = ca.units[1]
    (relation,) = _juju.relations(non_leader.state, 'certificates')
    assert not _interface_keys(relation.local_app_data)
    assert not _interface_keys(relation.local_unit_data)


def test_provider_writes_the_certificates_as_a_set(juju: _juju.Juju, mocked: None):
    """The interface carries a set: every certificate given is on the wire, once."""
    app = juju.deploy(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    ca = juju.deploy(certificate_transfer_testing.provider(certificates=[INTERMEDIATE, ROOT]))
    juju.integrate(app, ca)
    juju.settle()
    (relation,) = _juju.relations(ca.leader.state, 'certificates')
    written = json.loads(relation.local_app_data['certificates'])
    assert sorted(written) == sorted([ROOT, INTERMEDIATE])


# ------------------------------------------------- the stand-in requirer: what it writes


def test_requirer_advertises_its_version(juju: _juju.Juju, mocked: None):
    """The requirer speaks first, so it always writes: there is nothing to wait for."""
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    client = juju.deploy(certificate_transfer_testing.requirer())
    juju.integrate(app, client)
    juju.settle()
    (relation,) = _juju.relations(client.leader.state, 'certificates')
    assert relation.local_app_data == {'version': '1'}
    assert set(relation.local_unit_data) <= JUJU_NETWORK_KEYS


def test_requirer_v0_advertises_nothing(juju: _juju.Juju, mocked: None):
    """An absent version key *is* how v0 is spelled -- a stand-in that would not write."""
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    client = juju.deploy(certificate_transfer_testing.requirer(interface_version=0))
    juju.integrate(app, client)
    juju.settle()
    (relation,) = _juju.relations(client.leader.state, 'certificates')
    assert not _interface_keys(relation.local_app_data)
    assert set(relation.local_unit_data) <= JUJU_NETWORK_KEYS


def test_requirer_respond_false_writes_nothing(juju: _juju.Juju, mocked: None):
    """OP093: a stand-in that joins the relation but writes nothing."""
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    client = juju.deploy(certificate_transfer_testing.requirer(respond=False))
    juju.integrate(app, client)
    juju.settle()
    (relation,) = _juju.relations(client.leader.state, 'certificates')
    assert not _interface_keys(relation.local_app_data)
    assert set(relation.local_unit_data) <= JUJU_NETWORK_KEYS


def test_requirer_writes_nothing_until_it_is_leader(juju: _juju.Juju, mocked: None):
    """The version lives in the application databag, which only the leader writes."""
    app = juju.deploy(provider_charm.ProviderCharm, meta=provider_charm.META)
    client = juju.deploy(certificate_transfer_testing.requirer(), num_units=2)
    juju.integrate(app, client)
    juju.settle()
    non_leader = client.units[1]
    (relation,) = _juju.relations(non_leader.state, 'certificates')
    assert not _interface_keys(relation.local_app_data)
    assert set(relation.local_unit_data) <= JUJU_NETWORK_KEYS
