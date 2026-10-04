#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _functions: ensure_installed and ensure_vitality_hint.

Tests are ordered to minimise snap install/remove churn.  All tests that need
the snap *installed* run first, then install-from-removed tests, then error
paths, with the classic-confinement tests grouped together.
"""

import subprocess

import pytest

from charmlibs.snap import _errors, _functions, _snapd_apps, _snapd_conf
from charmlibs.snap import _snapd_snaps as _snapd
from conftest import ensure_installed_local, ensure_installed_store, ensure_removed, list_channels

# The smallest classic-confined snap in the store, used wherever a test needs classic
# confinement rather than a particular snap. Published by snapd:
# https://github.com/canonical/snapd/tree/master/tests/lib/snaps
_CLASSIC_SNAP = 'test-snapd-classic-confinement'

# Snapd's own test snap: its two open channels on the latest track hold different revisions,
# so switching channel also switches revision. latest/candidate and latest/beta are closed
# and absent from the channel map, so the alternate channel here is edge.
_SNAP = 'test-snapd-tools'
_CHANNEL = 'latest/stable'
_ALT_CHANNEL = 'latest/edge'

# hello-world is the one snap whose channels all carry the *same* revision, which is the
# precondition for test_ensure_installed_same_revision_different_channel_switches_tracking below.
# It is used for that test alone; everything else here uses _SNAP.
_SHARED_REVISION_SNAP = 'hello-world'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# ---------------------------------------------------------------------------
# snap INSTALLED — no-op / refresh paths (snap stays present)
# ---------------------------------------------------------------------------


def test_ensure_installed_revision_no_op_if_same_revision():
    ensure_installed_store(_SNAP)
    current_revision = _snapd.list_one(_SNAP).revision
    result = _functions.ensure_installed(_SNAP, revision=int(current_revision))
    assert result is False


def test_ensure_installed_revision_no_op_if_same_revision_and_update_true():
    # update is ignored when a revision is specified: the revision fully determines which
    # revision to be on, so there's nothing to update to.
    ensure_installed_store(_SNAP)
    current_revision = _snapd.list_one(_SNAP).revision
    result = _functions.ensure_installed(_SNAP, revision=int(current_revision), update=True)
    assert result is False


def test_ensure_installed_revision_refreshes_on_different_revision():
    # The target revision is taken from the alternate channel rather than by subtracting one
    # from the installed revision: adjacent revision numbers need not exist in the store.
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    other_revision = list_channels(_SNAP)[_ALT_CHANNEL].revision
    assert _snapd.list_one(_SNAP).revision != other_revision
    did_something = _functions.ensure_installed(_SNAP, revision=int(other_revision))
    assert did_something is True
    assert _snapd.list_one(_SNAP).revision == other_revision


def test_ensure_installed_no_op_update_false():
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    result = _functions.ensure_installed(_SNAP, channel=_CHANNEL, update=False)
    assert result is False


def test_ensure_installed_no_op_normalized_channel():
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    result = _functions.ensure_installed(_SNAP, channel='latest', update=False)
    assert result is False


def test_ensure_installed_no_op_stable_normalized():
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    result = _functions.ensure_installed(_SNAP, channel='stable', update=False)
    assert result is False


def test_ensure_installed_refreshes_on_different_channel():
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    did_something = _functions.ensure_installed(_SNAP, channel=_ALT_CHANNEL)
    assert did_something is True
    assert _snapd.list_one(_SNAP).tracking == _ALT_CHANNEL


def test_ensure_installed_no_updates_available_returns_false():
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    # Already up-to-date — no updates available.
    result = _functions.ensure_installed(_SNAP, channel=_CHANNEL)
    assert result is False


# ---------------------------------------------------------------------------
# INSTALL — tests that install from a removed state
# ---------------------------------------------------------------------------


def test_ensure_installed_revision_installs_if_not_present():
    ensure_removed(_SNAP)
    revision = list_channels(_SNAP)[_ALT_CHANNEL].revision
    did_something = _functions.ensure_installed(_SNAP, revision=int(revision))
    assert did_something is True
    assert _snapd.list_one(_SNAP).revision == revision


def test_ensure_installed_revision_without_channel_tracks_latest_stable():
    # Installing by revision alone always tracks latest/stable, whichever channel the revision
    # was found on. Recorded here because it means the next refresh -- including an automatic
    # one -- moves the snap to latest/stable's revision.
    ensure_removed(_SNAP)
    revision = list_channels(_SNAP)[_ALT_CHANNEL].revision
    _functions.ensure_installed(_SNAP, revision=int(revision))
    info = _snapd.list_one(_SNAP)
    assert info.revision == revision
    # Tracks the default channel even though the revision came from the alternate one.
    assert info.tracking == _CHANNEL


def test_ensure_installed_channel_and_revision_installs_and_tracks_channel():
    ensure_removed(_SNAP)
    edge = list_channels(_SNAP)[_ALT_CHANNEL].revision
    did_something = _functions.ensure_installed(_SNAP, channel=_ALT_CHANNEL, revision=edge)
    assert did_something is True
    info = _snapd.list_one(_SNAP)
    assert info.revision == edge
    assert info.tracking == _ALT_CHANNEL


def test_ensure_installed_channel_and_revision_no_op_when_already_matching():
    ensure_removed(_SNAP)
    edge = list_channels(_SNAP)[_ALT_CHANNEL].revision
    _functions.ensure_installed(_SNAP, channel=_ALT_CHANNEL, revision=edge)
    result = _functions.ensure_installed(_SNAP, channel=_ALT_CHANNEL, revision=edge)
    assert result is False


def test_ensure_installed_same_revision_different_channel_switches_tracking():
    # When the revision is already installed but the snap tracks the wrong channel,
    # ensure_installed still refreshes -- snapd moves the tracking channel without changing
    # the revision.
    #
    # This needs one revision that is on two channels at once, so it cannot use _SNAP, whose
    # channels deliberately hold different revisions. hello-world is kept solely for this.
    snap_name = _SHARED_REVISION_SNAP
    channels = list_channels(snap_name)
    revision = channels['latest/edge'].revision
    if channels['latest/stable'].revision != revision:
        pytest.skip('latest/stable and latest/edge are on different revisions')
    ensure_removed(snap_name)
    _functions.ensure_installed(snap_name, channel=_ALT_CHANNEL, revision=revision)
    did_something = _functions.ensure_installed(snap_name, channel=_CHANNEL, revision=revision)
    assert did_something is True
    info = _snapd.list_one(snap_name)
    assert info.revision == revision
    assert info.tracking == _CHANNEL


def test_ensure_installed_installs_if_not_present():
    ensure_removed(_SNAP)
    did_something = _functions.ensure_installed(_SNAP)
    assert did_something is True
    assert _snapd.list_one(_SNAP).name == _SNAP


def test_ensure_installed_installs_at_default_channel():
    ensure_removed(_SNAP)
    _functions.ensure_installed(_SNAP)
    assert _snapd.list_one(_SNAP).tracking == _CHANNEL


def test_ensure_installed_installs_at_specified_channel():
    ensure_removed(_SNAP)
    _functions.ensure_installed(_SNAP, channel=_ALT_CHANNEL)
    assert _snapd.list_one(_SNAP).tracking == _ALT_CHANNEL


# ---------------------------------------------------------------------------
# error paths (snap removed)
# ---------------------------------------------------------------------------


def test_ensure_installed_bad_channel_raises():
    ensure_removed(_SNAP)
    with pytest.raises(_errors.APIError):
        _functions.ensure_installed(_SNAP, channel='not/a/real/channel')


def test_ensure_installed_revision_bad_revision_raises():
    ensure_removed(_SNAP)
    with pytest.raises(_errors.RevisionNotAvailableError):
        _functions.ensure_installed(_SNAP, revision=99999999)


def test_ensure_installed_revision_not_on_channel_raises():
    # The revision exists, but not on the requested channel: reported as a channel error.
    ensure_removed(_SNAP)
    absent_from_channel = int(list_channels(_SNAP)[_ALT_CHANNEL].revision)
    with pytest.raises(_errors.ChannelNotAvailableError):
        _functions.ensure_installed(_SNAP, channel=_CHANNEL, revision=absent_from_channel)


# ---------------------------------------------------------------------------
# classic confinement — grouped to minimise churn
# ---------------------------------------------------------------------------


def test_ensure_installed_revision_installs_classic():
    ensure_removed(_CLASSIC_SNAP)
    channels = list_channels(_CLASSIC_SNAP)
    channel = 'latest/stable' if 'latest/stable' in channels else next(iter(channels))
    revision = channels[channel].revision
    _functions.ensure_installed(_CLASSIC_SNAP, channel=channel, revision=revision, classic=True)
    info = _snapd.list_one(_CLASSIC_SNAP)
    assert info.classic is True
    assert info.revision == revision


def test_ensure_installed_needs_classic_raises():
    ensure_removed(_CLASSIC_SNAP)
    with pytest.raises(_errors.NeedsClassicError):
        _functions.ensure_installed(_CLASSIC_SNAP)


def test_ensure_installed_installs_classic():
    ensure_removed(_CLASSIC_SNAP)
    _functions.ensure_installed(_CLASSIC_SNAP, classic=True)
    assert _snapd.list_one(_CLASSIC_SNAP).classic is True


# ---------------------------------------------------------------------------
# Error paths that don't require any specific snap state
# ---------------------------------------------------------------------------


def test_ensure_installed_bad_snap_name_raises():
    # ensure_installed() finds the snap isn't installed and goes on to install it, so the
    # store is what reports the name as missing -- not the local check that got there first.
    with pytest.raises(_errors.NotInStoreError) as ctx:
        _functions.ensure_installed(_ABSENT_SNAP)
    assert type(ctx.value) is _errors.NotInStoreError


# ---------------------------------------------------------------------------
# ensure_installed with channel='' — treated as no channel (empty string is falsy)
# ---------------------------------------------------------------------------


def test_ensure_installed_empty_channel_installs_on_default_channel() -> None:
    ensure_removed(_SNAP)
    did_something = _functions.ensure_installed(_SNAP, channel='')
    assert did_something is True
    assert _snapd.list_one(_SNAP).tracking == _CHANNEL


def test_ensure_installed_empty_channel_refreshes_when_installed() -> None:
    # channel='' is falsy, so ensure_installed skips the channel-mismatch branch
    # and falls through to the update-check refresh (no-op here).
    ensure_installed_store(_SNAP, channel=_CHANNEL)
    result = _functions.ensure_installed(_SNAP, channel='')
    assert result is False


# ---------------------------------------------------------------------------
# ensure_vitality_hint — system configuration, so each test starts and ends unset
# ---------------------------------------------------------------------------

_VITALITY_HINT = 'resilience.vitality-hint'
_SERVICE_SNAP = 'test-service-snap'
_SERVICE_UNIT = f'snap.{_SERVICE_SNAP}.daemon.service'


@pytest.fixture
def unset_vitality_hint():
    _snapd_conf.unset('system', _VITALITY_HINT)
    yield
    _snapd_conf.unset('system', _VITALITY_HINT)


def _vitality_hint() -> str | None:
    try:
        return _snapd_conf.get_one('system', _VITALITY_HINT)
    except _errors.OptionNotFoundError:
        return None


def _systemctl_show(prop: str) -> str:
    cmd = ['systemctl', 'show', '-p', prop, '--value', _SERVICE_UNIT]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_sets_unset_option():
    assert _vitality_hint() is None
    did_something = _functions.ensure_vitality_hint(_ABSENT_SNAP)
    assert did_something is True
    assert _vitality_hint() == _ABSENT_SNAP


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_replaces_empty_string():
    _snapd_conf.set('system', {_VITALITY_HINT: ''})
    did_something = _functions.ensure_vitality_hint(_ABSENT_SNAP)
    assert did_something is True
    assert _vitality_hint() == _ABSENT_SNAP


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_appends_after_existing_snaps():
    _snapd_conf.set('system', {_VITALITY_HINT: 'foo,bar'})
    did_something = _functions.ensure_vitality_hint(_ABSENT_SNAP)
    assert did_something is True
    assert _vitality_hint() == f'foo,bar,{_ABSENT_SNAP}'


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_no_op_if_already_listed():
    _snapd_conf.set('system', {_VITALITY_HINT: f'foo,{_ABSENT_SNAP},bar'})
    did_something = _functions.ensure_vitality_hint(_ABSENT_SNAP)
    assert did_something is False
    assert _vitality_hint() == f'foo,{_ABSENT_SNAP},bar'


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_snapd_raises():
    with pytest.raises(_errors.ChangeError, match='snapd snap vitality cannot be changed'):
        _functions.ensure_vitality_hint('snapd')
    assert _vitality_hint() is None


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_invalid_snap_name_raises():
    with pytest.raises(_errors.ChangeError, match='invalid snap name'):
        _functions.ensure_vitality_hint('Not-A-Valid-Name')
    assert _vitality_hint() is None


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_more_than_100_snaps_raises():
    _snapd_conf.set('system', {_VITALITY_HINT: ','.join(f'snap{i}' for i in range(100))})
    with pytest.raises(_errors.ChangeError, match='cannot set more than 100 snaps'):
        _functions.ensure_vitality_hint(_ABSENT_SNAP)


@pytest.mark.usefixtures('unset_vitality_hint')
def test_ensure_vitality_hint_rewrites_running_service_without_restarting_it():
    # The docstring's claim: the unit gets OOMScoreAdjust=-900+rank straight away, but the
    # running process is left alone, so the caller must restart it for the score to apply.
    ensure_installed_local(_SERVICE_SNAP)
    _snapd_apps.start(_SERVICE_SNAP, enable=True)
    _snapd_conf.set('system', {_VITALITY_HINT: 'foo'})
    pid = _systemctl_show('MainPID')
    assert _systemctl_show('OOMScoreAdjust') == '0'
    did_something = _functions.ensure_vitality_hint(_SERVICE_SNAP)
    assert did_something is True
    assert _systemctl_show('OOMScoreAdjust') == '-898'  # Second in the list.
    assert _systemctl_show('MainPID') == pid
    _snapd_apps.stop(_SERVICE_SNAP, disable=True)
