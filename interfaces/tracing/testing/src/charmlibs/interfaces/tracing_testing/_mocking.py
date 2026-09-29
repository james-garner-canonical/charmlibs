# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The ``mocked`` context manager."""

from __future__ import annotations

import contextlib
import threading
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Iterator

# The nesting depth, so that only the outermost scope patches and un-patches. The patches
# themselves are process-wide, as ``unittest.mock.patch`` always is; the depth is kept
# per-thread so that a scope opened on one thread can't be closed by another.
_state = threading.local()


def _depth() -> int:
    return getattr(_state, 'depth', 0)


@contextlib.contextmanager
def mocked() -> Iterator[None]:
    """Mock out the library's internals for the duration of the context.

    The scope is opened for you in two of its three homes, and by the test itself in the
    third:

    - **Around the stand-in's dispatches**, by ``Juju``: it is the ``mocking`` of the
      ``CharmData`` that :func:`provider` and :func:`requirer` return.
    - **Around the charm under test's dispatches**, by ``Juju``'s default mocks -- or by
      the test itself where that isn't available, which is what a ``mocked`` fixture is
      for::

          @pytest.fixture()
          def mocked():
              with tracing_testing.mocked():
                  yield

    - **Around single-charm tests**, opened by the test itself, when the charm under test
      runs with ``ops.testing.Context``. Nothing ``Juju`` applies reaches a ``Context.run``
      the test makes itself.

    Several libraries' scopes stack, in any order::

        with tracing_testing.mocked(), tls_certificates_testing.mocked():
            ...

    The scope is reentrant, so a fixture and the test that uses it may each open one, and
    nesting is harmless.

    This library mocks nothing today: everything ``charmlibs.interfaces.tracing`` does is
    reading and writing relation data, which ``ops.testing`` already models, with no side
    effects and nothing slow enough to be worth replacing. The scope is defined all the
    same, because every library must define one -- and because a library that starts
    mocking later can then do so without breaking the tests already written against it.
    """
    _state.depth = _depth() + 1
    try:
        yield
    finally:
        _state.depth = _depth() - 1
