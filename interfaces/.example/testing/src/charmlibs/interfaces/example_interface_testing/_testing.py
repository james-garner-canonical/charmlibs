# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

from ops import testing

from charmlibs.interfaces import example_interface

_INTERFACE_NAME = 'example-interface'


def relation_for_requirer(
    # testing.Relation args:
    endpoint: str,
    # *,  # Additional arguments must be keyword only.
    # example_interface args:
    # ...
    # interface 'conversation' args:
    # response: bool = True,
) -> testing.Relation:
    return testing.Relation(endpoint, interface=_INTERFACE_NAME)


def relation_for_provider(
    # testing.Relation args:
    endpoint: str,
    # *,  # Additional arguments must be keyword only.
    # example_interface args:
    # ...
    # interface 'conversation' args:
    # response: bool = True,
) -> testing.Relation:
    return testing.Relation(endpoint, interface=_INTERFACE_NAME)
