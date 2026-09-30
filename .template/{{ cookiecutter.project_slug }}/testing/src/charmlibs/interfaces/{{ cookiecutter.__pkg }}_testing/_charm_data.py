# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""A placeholder for OP089's ``ops.testing.CharmData``.

``ops.testing.CharmData`` doesn't exist in a released ``ops`` yet. This module defines a
private placeholder with the same shape, so that :func:`provider` and :func:`requirer` can
return it today. When OP089 lands, this becomes an alias of ``ops.testing.CharmData`` and
the module is deleted.
"""

from __future__ import annotations

import collections.abc
import dataclasses
import types
import typing

import ops

if typing.TYPE_CHECKING:
    import contextlib
    from collections.abc import Callable, Mapping, Sequence

CharmType = typing.TypeVar('CharmType', bound=ops.CharmBase)


# A dataclass in the public API, which this package otherwise avoids: acceptable here
# because the class is a placeholder for an ops.testing type, and OP089 specifies that
# shape. It will become an alias of ops.testing.CharmData, not a type of our own.
@dataclasses.dataclass(frozen=True)
class CharmData(typing.Generic[CharmType]):
    """Placeholder for OP089's ``ops.testing.CharmData``.

    Everything ``Juju.deploy`` needs to deploy a charm that is not read from disk: the
    charm class, its ``charmcraft.yaml``-shaped metadata (including any config options and
    actions), and the mocking scope to open around each of the application's dispatches.

    ``meta`` is frozen on construction, all the way down: nested mappings become read-only
    mappings and lists become tuples. This stops a change to one result's metadata from
    affecting every other result that shares it.
    """

    charm_type: type[CharmType]
    meta: Mapping[str, typing.Any]
    mocking: Callable[..., contextlib.AbstractContextManager[None]] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'meta', _freeze(self.meta))


def _freeze(value: object) -> object:
    if isinstance(value, collections.abc.Mapping):
        mapping = typing.cast('Mapping[object, object]', value)
        return types.MappingProxyType({k: _freeze(v) for k, v in mapping.items()})
    if isinstance(value, (list, tuple)):
        items = typing.cast('Sequence[object]', value)
        return tuple(_freeze(v) for v in items)
    return value
