# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

from ops import testing

# from charmlibs.interfaces import {{ cookiecutter.__pkg }}

_INTERFACE_NAME = '{{ cookiecutter.project_slug }}'


def relation_for_requirer(
    # testing.Relation args:
    endpoint: str,
    # *,  # Additional arguments must be keyword only.
    # {{ cookiecutter.__pkg }} args:
    # ...
    # interface 'conversation' args:
    # response: bool = True,
) -> testing.Relation:
    return testing.Relation(endpoint, interface=_INTERFACE_NAME)


def relation_for_provider(
    # testing.Relation args:
    endpoint: str,
    # *,  # Additional arguments must be keyword only.
    # {{ cookiecutter.__pkg }} args:
    # ...
    # interface 'conversation' args:
    # response: bool = True,
) -> testing.Relation:
    return testing.Relation(endpoint, interface=_INTERFACE_NAME)
