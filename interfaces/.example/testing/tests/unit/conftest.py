# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared fixtures. Also the idiomatic shape of a charm repository's own conftest."""

from __future__ import annotations

import typing

import pytest

import _juju
from charmlibs.interfaces import example_interface_testing as example_interface_testing

if typing.TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture()
def mocked() -> Iterator[None]:
    """Open the library's mocking scope for the whole test, arrangement and act alike.

    The stand-ins get the scope from Juju, as their ``CharmData.mocking``. The charm under
    test gets no mocking from this harness, so tests wrap its dispatches themselves --
    which is what this fixture is for.
    """
    with example_interface_testing.mocked():
        yield


@pytest.fixture()
def juju() -> Iterator[_juju.Juju]:
    """A fresh model for one test."""
    with _juju.Juju() as model:
        yield model
