# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The ``mocked`` context manager."""

from __future__ import annotations

import contextlib
import itertools
import threading
import typing
import unittest.mock

from charmlibs.interfaces import tls_certificates
from charmlibs.interfaces.tls_certificates import _tls_certificates as _internal

from . import _raw

if typing.TYPE_CHECKING:
    from collections.abc import Iterator

_MOCKED_KEY = tls_certificates.PrivateKey(raw=_raw.KEY)
"""The key the library gets instead of generating one, while ``mocked`` is active.

Deliberately not public. A test that wants to know which key the charm ended up with reads
it off the library (``get_assigned_certificates`` returns it), which works whether the key
came from here, from the charm, or from a rotation -- so no test needs to name this.
"""

# The nesting depth, so that only the outermost scope patches and un-patches. The patches
# themselves are process-wide, as ``unittest.mock.patch`` always is; the depth is kept
# per-thread so that a scope opened on one thread can't be closed by another.
_state = threading.local()


def _depth() -> int:
    return getattr(_state, "depth", 0)


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
              with tls_certificates_testing.mocked():
                  yield

    - **Around single-charm tests**, opened by the test itself, when the charm under test
      runs with ``ops.testing.Context``. Nothing ``Juju`` applies reaches a ``Context.run``
      the test makes itself.

    Several libraries' scopes stack, in any order::

        with tls_certificates_testing.mocked(), certificate_transfer_testing.mocked():
            ...

    What is mocked today is the library's private key generation, which is replaced with a
    pre-generated RSA key. Generating a 2048-bit key takes a noticeable fraction of a
    second, and a charm that lets the library manage its key generates one on its first
    reconcile and again on every rotation, so a suite of a few hundred state-transition
    tests otherwise spends most of its time on key generation. Nothing outside the library
    is patched: a charm that generates its own keys, through ``cryptography`` or anything
    else, is unaffected.

    The key is a real RSA key, so everything that depends on having one keeps working --
    signing, ``matches_private_key``, chain verification. The only observable difference is
    that a charm which lets the library manage its key gets the same key in every test. Key
    *rotation* still produces a distinct key: the mock returns a fresh key for each call
    after the first, so a test asserting that ``regenerate_private_key`` changed the key
    still tests something.

    The scope is reentrant, so a fixture and the test that uses it may each open one, and
    nesting is harmless.
    """
    if _depth():  # already inside a scope; nothing to do but count the nesting
        _state.depth = _depth() + 1
        try:
            yield
        finally:
            _state.depth = _depth() - 1
        return
    keys = _mocked_keys()
    serial_numbers = itertools.count(_FIRST_SERIAL_NUMBER)
    unique_identifiers = _mocked_unique_identifiers()
    _state.depth = 1
    try:
        with (
            unittest.mock.patch.object(
                tls_certificates.PrivateKey,
                "generate",
                # The signature the library calls it with, so a mistyped call still fails.
                side_effect=lambda key_size=2048, public_exponent=65537: next(keys),
            ),
            unittest.mock.patch.object(
                _internal, "_random_serial_number", side_effect=lambda: next(serial_numbers)
            ),
            unittest.mock.patch.object(
                _internal, "_unique_identifier", side_effect=lambda: next(unique_identifiers)
            ),
        ):
            yield
    finally:
        _state.depth = _depth() - 1


_FIRST_SERIAL_NUMBER = 1
"""Where the serial number sequence starts. Small, so that failures are readable."""


def _mocked_unique_identifiers() -> Iterator[str]:
    """Yield the identifiers the library puts in each request's subject name.

    Sequential rather than constant, and this is the one thing a replacement here must get
    right. The library uses this value to tell one request from another, so a constant would
    make a re-request -- what a key rotation or a renewal produces -- byte-identical to the
    request it replaces. The simulated provider would then see a request it had already
    answered and keep the stale certificate.
    """
    for n in itertools.count(1):
        # A valid version-4 UUID, so that anything parsing the subject name still works.
        yield f"00000000-0000-4000-8000-{n:012d}"


def _mocked_keys() -> Iterator[tls_certificates.PrivateKey]:
    """Yield the pre-generated key first, then freshly generated ones.

    The first call is the one that happens in almost every test -- a charm that lets the
    library manage its key generating it on its first reconcile -- and is the one worth
    making free. Later calls mean the charm asked for a *different* key, which is what
    ``regenerate_private_key`` does, so they must not return the same key again: a test
    asserting that rotation changed the key would then pass while testing nothing.
    """
    yield _MOCKED_KEY
    while True:
        yield _real_generate()


# Bound before any patching, so that the fallback path can't recurse into the mock.
_real_generate = tls_certificates.PrivateKey.generate
