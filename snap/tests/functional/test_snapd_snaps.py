#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_snaps: info, install, remove, refresh.

Tests are ordered to minimise snap install/remove churn.  All tests that need
hello-world *installed* run first, then all tests that need it *removed*, then
tests that inherently install/remove as part of the test logic.
"""

import pytest

from charmlibs.snap import _errors
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import ensure_installed, ensure_removed

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# ---------------------------------------------------------------------------
# hello-world INSTALLED — tests that need the snap present
# ---------------------------------------------------------------------------


def test_info_installed():
    ensure_installed('hello-world')
    info = _snapd.info('hello-world')
    assert info.name == 'hello-world'
    assert info.channel
    assert info.revision
    assert info.version


def test_info_fields():
    ensure_installed('hello-world')
    info = _snapd.info('hello-world')
    assert info.classic is False


def test_install_already_installed_returns_false():
    ensure_installed('hello-world')
    result = _snapd.install('hello-world')
    assert result is False


def test_refresh_no_updates_returns_false():
    ensure_installed('hello-world', channel='latest/stable')
    result = _snapd.refresh('hello-world', channel='latest/stable')
    assert result is False
    assert _snapd.info('hello-world').channel == 'latest/stable'


def test_refresh_channel():
    ensure_installed('hello-world', channel='latest/stable')
    _snapd.refresh('hello-world', channel='latest/candidate')
    info = _snapd.info('hello-world')
    assert info.channel == 'latest/candidate'


def test_refresh_invalid_channel_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapChannelNotAvailableError) as ctx:
        _snapd.refresh('hello-world', channel='garbage')
    assert ctx.value.kind == 'snap-channel-not-available'


def test_refresh_revision_not_available_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapRevisionNotAvailableError) as ctx:
        _snapd.refresh('hello-world', revision=99999999)
    assert ctx.value.kind == 'snap-revision-not-available'


def test_remove():
    # Last test in the "installed" block — leaves hello-world removed for the next block.
    ensure_installed('hello-world')
    _snapd.remove('hello-world')
    assert _snapd.info('hello-world', missing_ok=True) is None


# ---------------------------------------------------------------------------
# hello-world REMOVED — tests that need the snap absent
# (after test_remove above, hello-world is already gone)
# ---------------------------------------------------------------------------


def test_info_missing_ok_false_raises_by_default():
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapNotFoundError) as ctx:
        _snapd.info('hello-world')
    assert ctx.value.kind == 'snap-not-found'


def test_info_missing_ok_true_returns_none():
    ensure_removed('hello-world')
    result = _snapd.info('hello-world', missing_ok=True)
    assert result is None


def test_remove_not_installed_returns_false():
    ensure_removed('hello-world')
    result = _snapd.remove('hello-world')
    assert result is False


def test_remove_purge_not_installed_returns_false():
    # purge=True on a non-installed snap behaves the same as purge=False: returns False.
    ensure_removed('hello-world')
    result = _snapd.remove('hello-world', purge=True)
    assert result is False


def test_refresh_not_installed_raises_base_snap_error():
    # The API returns an error with no 'kind' when refreshing a non-installed snap.
    # This is distinct from SnapNotFoundError; it's a base SnapError.
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapError) as ctx:
        _snapd.refresh('hello-world')
    # No kind is set -- the message contains "is not installed" but snapd omits the kind field.
    assert not ctx.value.kind
    assert 'not installed' in ctx.value.message


def test_install_invalid_channel_raises():
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapChannelNotAvailableError) as ctx:
        _snapd.install('hello-world', channel='garbage')
    assert ctx.value.kind == 'snap-channel-not-available'
    assert 'channel' in ctx.value.message or 'no snap revision' in ctx.value.message


def test_install_revision_not_available_raises():
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapRevisionNotAvailableError) as ctx:
        _snapd.install('hello-world', revision=99999999)
    assert ctx.value.kind == 'snap-revision-not-available'


# ---------------------------------------------------------------------------
# hello-world INSTALL operations — tests that install as part of the test
# ---------------------------------------------------------------------------


def test_install():
    ensure_removed('hello-world')
    _snapd.install('hello-world')
    info = _snapd.info('hello-world')
    assert info.name == 'hello-world'
    assert info.channel == 'latest/stable'


def test_install_channel():
    ensure_removed('hello-world')
    _snapd.install('hello-world', channel='latest/candidate')
    info = _snapd.info('hello-world')
    assert info.channel == 'latest/candidate'


def test_install_revision():
    ensure_removed('hello-world')
    # hello-world revision 28 is one behind the current 29.
    _snapd.install('hello-world', revision=28)
    info = _snapd.info('hello-world')
    assert info.revision == '28'


# ---------------------------------------------------------------------------
# charmcraft (classic) — grouped to minimise churn
# ---------------------------------------------------------------------------


def test_install_needs_classic_raises():
    ensure_removed('charmcraft')
    with pytest.raises(_errors.SnapNeedsClassicError) as ctx:
        _snapd.install('charmcraft')
    assert ctx.value.kind == 'snap-needs-classic'


def test_install_classic():
    ensure_removed('charmcraft')
    _snapd.install('charmcraft', classic=True)
    info = _snapd.info('charmcraft')
    assert info.classic is True


# ---------------------------------------------------------------------------
# Error paths that don't require any specific snap state
# ---------------------------------------------------------------------------


def test_install_nonexistent_snap_raises():
    with pytest.raises(_errors.SnapNotFoundError) as ctx:
        _snapd.install(_ABSENT_SNAP)
    assert ctx.value.kind == 'snap-not-found'
    assert ctx.value.value == _ABSENT_SNAP


def test_install_channel_and_revision_raises():
    with pytest.raises(ValueError):
        _snapd.install('hello-world', channel='latest/stable', revision=28)  # type: ignore[call-overload]


def test_refresh_channel_and_revision_raises():
    with pytest.raises(ValueError):
        _snapd.refresh('hello-world', channel='latest/stable', revision=28)  # type: ignore[call-overload]
