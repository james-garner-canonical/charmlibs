#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_snaps: info, install, remove, refresh, hold, unhold."""

import datetime

import pytest

from charmlibs.snap import _errors
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import ensure_installed, ensure_removed

# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


def test_info_installed():
    ensure_installed('hello-world')
    info = _snapd.info('hello-world')
    assert info.name == 'hello-world'
    assert info.channel
    assert info.revision
    assert info.version


def test_info_missing_ok_false_raises_by_default():
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapNotFoundError) as ctx:
        _snapd.info('hello-world')
    assert ctx.value.kind == 'snap-not-found'


def test_info_missing_ok_true_returns_none():
    ensure_removed('hello-world')
    result = _snapd.info('hello-world', missing_ok=True)
    assert result is None


def test_info_fields():
    ensure_installed('hello-world')
    info = _snapd.info('hello-world')
    assert info.classic is False
    assert info.hold is None


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


def test_install():
    ensure_removed('hello-world')
    _snapd.install('hello-world')
    info = _snapd.info('hello-world')
    assert info.name == 'hello-world'
    assert info.channel == 'latest/stable'


def test_install_already_installed_returns_false():
    ensure_installed('hello-world')
    result = _snapd.install('hello-world')
    assert result is False


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


def test_install_channel_and_revision_raises():
    with pytest.raises(ValueError):
        _snapd.install('hello-world', channel='latest/stable', revision=28)  # type: ignore[call-overload]


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


def test_remove():
    ensure_installed('hello-world')
    _snapd.remove('hello-world')
    assert _snapd.info('hello-world', missing_ok=True) is None


def test_remove_not_installed_returns_false():
    ensure_removed('hello-world')
    result = _snapd.remove('hello-world')
    assert result is False


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------


def test_refresh_channel():
    ensure_installed('hello-world', channel='latest/stable')
    _snapd.refresh('hello-world', channel='latest/candidate')
    info = _snapd.info('hello-world')
    assert info.channel == 'latest/candidate'


def test_refresh_no_updates_returns_false():
    ensure_installed('hello-world', channel='latest/stable')
    result = _snapd.refresh('hello-world', channel='latest/stable')
    assert result is False
    assert _snapd.info('hello-world').channel == 'latest/stable'


def test_refresh_not_installed_raises_base_snap_error():
    # The API returns an error with no 'kind' when refreshing a non-installed snap.
    # This is distinct from SnapNotFoundError; it's a base SnapError.
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapError) as ctx:
        _snapd.refresh('hello-world')
    # No kind is set -- the message contains "is not installed" but snapd omits the kind field.
    assert not ctx.value.kind
    assert 'not installed' in ctx.value.message


def test_refresh_channel_and_revision_raises():
    with pytest.raises(ValueError):
        _snapd.refresh('hello-world', channel='latest/stable', revision=28)  # type: ignore[call-overload]


# ---------------------------------------------------------------------------
# hold / unhold
# ---------------------------------------------------------------------------


def test_hold_with_duration():
    ensure_installed('hello-world')
    _snapd.hold('hello-world', duration=datetime.timedelta(days=2))
    info = _snapd.info('hello-world')
    assert info.hold is not None
    assert info.hold - datetime.datetime.now().astimezone() > datetime.timedelta(days=1)


def test_hold_forever():
    ensure_installed('hello-world')
    _snapd.hold('hello-world')
    info = _snapd.info('hello-world')
    # When held forever, snapd returns a far-future timestamp.
    assert info.hold is not None


def test_hold_not_installed_raises_snap_not_found_error():
    # hold() calls info() first, which raises SnapNotFoundError with a proper kind.
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapNotFoundError) as ctx:
        _snapd.hold('hello-world')
    assert ctx.value.kind == 'snap-not-found'


def test_unhold():
    ensure_installed('hello-world')
    _snapd.hold('hello-world')
    assert _snapd.info('hello-world').hold is not None
    _snapd.unhold('hello-world')
    assert _snapd.info('hello-world').hold is None


def test_unhold_not_installed_no_error():
    # unhold on a non-installed snap succeeds silently (async Done).
    ensure_removed('hello-world')
    _snapd.unhold('hello-world')  # should not raise


# ---------------------------------------------------------------------------
# install (additional error paths)
# ---------------------------------------------------------------------------


def test_install_nonexistent_snap_raises():
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapNotFoundError) as ctx:
        _snapd.install('this-snap-does-not-exist-xyz-abc-123')
    assert ctx.value.kind == 'snap-not-found'
    assert ctx.value.value == 'this-snap-does-not-exist-xyz-abc-123'


def test_install_invalid_channel_raises():
    # A non-existent channel raises SnapAPIError with kind 'snap-channel-not-available'.
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapAPIError) as ctx:
        _snapd.install('hello-world', channel='garbage')
    assert ctx.value.kind == 'snap-channel-not-available'
    assert 'channel' in ctx.value.message or 'no snap revision' in ctx.value.message


def test_install_revision_not_available_raises():
    ensure_removed('hello-world')
    with pytest.raises(_errors.SnapRevisionNotAvailableError) as ctx:
        _snapd.install('hello-world', revision=99999999)
    assert ctx.value.kind == 'snap-revision-not-available'


# ---------------------------------------------------------------------------
# refresh (additional error paths)
# ---------------------------------------------------------------------------


def test_refresh_invalid_channel_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapAPIError) as ctx:
        _snapd.refresh('hello-world', channel='garbage')
    assert ctx.value.kind == 'snap-channel-not-available'


def test_refresh_revision_not_available_raises():
    ensure_installed('hello-world')
    with pytest.raises(_errors.SnapRevisionNotAvailableError) as ctx:
        _snapd.refresh('hello-world', revision=99999999)
    assert ctx.value.kind == 'snap-revision-not-available'


# ---------------------------------------------------------------------------
# hold (additional)
# ---------------------------------------------------------------------------


def test_hold_already_held_no_error():
    # Holding an already-held snap is idempotent — no error is raised.
    ensure_installed('hello-world')
    _snapd.hold('hello-world')
    _snapd.hold('hello-world')  # second hold should not raise


# ---------------------------------------------------------------------------
# remove (additional)
# ---------------------------------------------------------------------------


def test_remove_purge_not_installed_returns_false():
    # purge=True on a non-installed snap behaves the same as purge=False: returns False.
    ensure_removed('hello-world')
    result = _snapd.remove('hello-world', purge=True)
    assert result is False


# ---------------------------------------------------------------------------
# _list_channels (error paths)
# ---------------------------------------------------------------------------


def test_list_channels_nonexistent_snap_raises():
    with pytest.raises(_errors.SnapNotFoundError) as ctx:
        _snapd._list_channels('this-snap-does-not-exist-xyz')
    assert ctx.value.kind == 'snap-not-found'
