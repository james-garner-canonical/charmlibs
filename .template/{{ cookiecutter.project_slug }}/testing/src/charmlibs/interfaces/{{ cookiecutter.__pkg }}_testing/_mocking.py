# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The ``mocked`` context manager."""

from __future__ import annotations

import contextlib
import threading
import typing

# from charmlibs.interfaces.{{ cookiecutter.__pkg }} import _{{ cookiecutter.__pkg }} as _internal

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
              with {{ cookiecutter.__pkg }}_testing.mocked():
                  yield

    - **Around single-charm tests**, opened by the test itself, when the charm under test
      runs with ``ops.testing.Context``. Nothing ``Juju`` applies reaches a
      ``Context.run`` the test makes itself.

    Several libraries' scopes stack, in any order::

        with {{ cookiecutter.__pkg }}_testing.mocked(), other_testing.mocked():
            ...

    The scope is reentrant, so a fixture and the test that uses it may each open one, and
    nesting is harmless.

    This library mocks nothing today, so the scope only counts its own nesting. It is
    defined all the same, because every library must define one -- and because a library
    that starts mocking later can then do so without breaking the tests already written
    against it.
    """
    # FIXME: apply the library's mocks here, on entering the outermost scope only::
    #
    #     if _depth():  # already inside a scope, so the patches are already applied
    #         _state.depth = _depth() + 1
    #         try:
    #             yield
    #         finally:
    #             _state.depth = _depth() - 1
    #         return
    #     patch = unittest.mock.patch.object(_internal, 'something_slow_or_impure', ...)
    #     _state.depth = 1
    #     try:
    #         with patch:
    #             yield
    #     finally:
    #         _state.depth = _depth() - 1
    #
    # Only the library's own internals may be patched. Nothing defined outside the
    # library may be, so that charm code which doesn't pass through the library has no
    # side effects. Mocking can change what a charm's tests see, so reflect that in the
    # library's version: substantial changes to mocking warrant a minor bump rather than
    # a patch bump.
    _state.depth = _depth() + 1
    try:
        yield
    finally:
        _state.depth = _depth() - 1
