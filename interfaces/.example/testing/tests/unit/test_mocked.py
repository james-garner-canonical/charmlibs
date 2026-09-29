# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for the ``mocked`` context manager itself."""

import ops.testing
import pytest

import requirer_charm
from charmlibs.interfaces import example_interface_testing as example_interface_testing


def test_mocked_takes_no_arguments():
    """OP093 requires it to be callable with no arguments."""
    with example_interface_testing.mocked():
        pass


def test_mocked_is_reentrant():
    """A fixture and the test that uses it may each open a scope, and nesting is harmless."""
    with example_interface_testing.mocked():
        with example_interface_testing.mocked():
            with example_interface_testing.mocked():
                pass


def test_mocked_restores_on_exception():
    with pytest.raises(RuntimeError, match='boom'):
        with example_interface_testing.mocked():
            raise RuntimeError('boom')


def test_mocked_restores_on_exception_from_a_nested_scope():
    with pytest.raises(RuntimeError, match='boom'):
        with example_interface_testing.mocked():
            with example_interface_testing.mocked():
                raise RuntimeError('boom')


def test_mocked_scopes_stack():
    """Several libraries' scopes stack, in any order -- so two of this one must too."""
    with example_interface_testing.mocked(), example_interface_testing.mocked():
        pass


def test_the_scope_covers_the_charms_execution():
    """Mocking matters most while the charm runs, not only during arrangement.

    This library mocks nothing today, so there is nothing to observe here beyond the
    charm running unharmed inside the scope -- which is exactly what a library with
    nothing to mock must guarantee.
    """
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    with example_interface_testing.mocked():
        state_out = ctx.run(ctx.on.update_status(), ops.testing.State(leader=True))
    assert isinstance(state_out, ops.testing.State)
