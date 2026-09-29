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

"""Tests from a requirer charm's perspective, using the stand-in provider.

These are the tests a charm author would write, so they only use the package's public API
and never read relation data. The stand-in's own contract is tested in
``test_testing.py``.
"""

from __future__ import annotations

import typing

import ops
import ops.testing

import requirer_charm
from charmlibs.interfaces import {{ cookiecutter.__pkg }}_testing as {{ cookiecutter.__pkg }}_testing

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
    """Without a relation there is nothing to be ready for."""
    app = _deploy(juju)
    juju.dispatch(app.leader, 'update-status')
    juju.settle()
    # FIXME: Assert something about the charm -- it usually reports Blocked or Waiting.


def test_the_happy_path(juju: _juju.Juju, mocked: None):
    """The whole conversation, with nothing to keep in agreement with the charm."""
    app = _deploy(juju)
    juju.integrate(app, juju.deploy({{ cookiecutter.__pkg }}_testing.provider()))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.


def test_related_but_unanswered(juju: _juju.Juju, mocked: None):
    """The most common real intermediate state: asked, but nobody has answered.

    The charm should report blocked because the provider hasn't answered -- not because
    it failed to ask.
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy({{ cookiecutter.__pkg }}_testing.provider(respond=False)))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
    # FIXME: Assert something about the charm.


def test_relation_variant(juju: _juju.Juju, mocked: None):
    """Test the requirer charm against a provider behaving in some non-default way."""
    # FIXME: construct the stand-in with some non-default argument, once the library has
    # one.
    app = _deploy(juju)
    juju.integrate(app, juju.deploy({{ cookiecutter.__pkg }}_testing.provider()))
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.


def test_a_multi_unit_requirer(juju: _juju.Juju, mocked: None):
    """Only the leader writes application data, but every unit may read the answer."""
    app = _deploy(juju, num_units=2)
    juju.integrate(app, juju.deploy({{ cookiecutter.__pkg }}_testing.provider()))
    juju.settle()
    for unit in app.units:
        ctx = _ctx(unit)
        with ctx(ctx.on.update_status(), unit.state) as manager:
            manager.run()
        # FIXME: Assert something about the charm's use of the library object.


def test_a_later_turn_of_the_conversation(juju: _juju.Juju, mocked: None):
    """The charm asks for something different, and the stand-in's answer follows.

    A config change is the usual way to make the charm re-request; the stand-in drops the
    stale answer and writes the new one, which is what a real provider does.
    """
    app = _deploy(juju)
    juju.integrate(app, juju.deploy({{ cookiecutter.__pkg }}_testing.provider()))
    juju.settle()
    # FIXME: juju.config(app, {...}) to make the charm ask for something different.
    juju.settle()
    ctx = _ctx(app.leader)
    with ctx(ctx.on.update_status(), app.leader.state) as manager:
        manager.run()
    # FIXME: Assert something about the charm's use of the library object.
