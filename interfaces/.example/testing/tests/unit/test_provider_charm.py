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

These are the tests a charm author would write, so they only use the package's public API
and never read relation data. The stand-in's own contract is tested in
``test_testing.py``.
"""

from __future__ import annotations

import typing

import ops
import ops.testing

import provider_charm
from charmlibs.interfaces import example_interface_testing as example_interface_testing

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
    """Nobody is asking for anything, so nothing happens."""
    app = _deploy(juju)
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
    # FIXME: Assert something about the charm.


def test_the_happy_path(juju: _juju.Juju, mocked: None):
    """The whole conversation, with nothing to keep in agreement with the charm."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(example_interface_testing.requirer()))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.


def test_a_silent_requirer_asks_for_nothing(juju: _juju.Juju, mocked: None):
    """respond=False: the stand-in joins the relation and writes nothing."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(example_interface_testing.requirer(respond=False)))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
    # FIXME: Assert something about the charm -- it should report waiting, not failing.


def test_relation_variant(juju: _juju.Juju, mocked: None):
    """Test the provider charm against a requirer asking for something non-default."""
    # FIXME: construct the stand-in with some non-default argument, once the library has
    # one.
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(example_interface_testing.requirer()))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.


def test_several_requirers_on_one_endpoint(juju: _juju.Juju, mocked: None):
    """A stand-in stands for one application, so aggregating over several takes one each.

    FIXME: delete this test if the library supports only one remote per endpoint.
    """
    app = _deploy(juju)
    workloads = [
        juju.deploy(example_interface_testing.requirer(), app=f'workload-{n}') for n in range(2)
    ]
    for workload in workloads:
        juju.integrate(app, workload)
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.


def test_a_later_turn_of_the_conversation(juju: _juju.Juju, mocked: None):
    """The requirer asks for something different, and the charm's answer follows.

    There is no public way to change a deployed stand-in's arguments, so this deploys a
    replacement -- the fallback OP093 documents for behaviour with no config shape.
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy(example_interface_testing.requirer(), app='workload'))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.
    replacement = juju.deploy(example_interface_testing.requirer(), app='replacement')
    juju.integrate(app, replacement)
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.
