#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_logs: logs."""

import pytest

from charmlibs.snap import _errors, _snapd_logs
from conftest import ensure_installed

_SNAP = 'kube-proxy'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


# ---------------------------------------------------------------------------
# logs (kube-proxy installed)
# ---------------------------------------------------------------------------


def test_logs_returns_log_entries():
    ensure_installed(_SNAP, classic=True)
    entries = _snapd_logs.logs(_SNAP, num_lines=5)
    assert isinstance(entries, list)


def test_logs_entries_have_expected_fields():
    ensure_installed(_SNAP, classic=True)
    entries = _snapd_logs.logs(_SNAP, num_lines=5)
    for entry in entries:
        assert isinstance(entry, _snapd_logs.LogEntry)
        assert entry.timestamp
        assert isinstance(entry.message, str)
        assert isinstance(entry.sid, str)
        assert isinstance(entry.pid, int)


def test_logs_num_lines():
    # The num_lines parameter limits the number of results returned.
    ensure_installed(_SNAP, classic=True)
    entries = _snapd_logs.logs(_SNAP, num_lines=3)
    assert len(entries) <= 3


def test_logs_multiple_snaps():
    # Requesting logs for multiple snaps should not raise.
    ensure_installed(_SNAP, classic=True)
    ensure_installed('lxd')
    entries = _snapd_logs.logs(_SNAP, 'lxd', num_lines=10)
    assert isinstance(entries, list)


def test_logs_num_lines_zero_raises():
    # snapd rejects n=0 as invalid.
    ensure_installed(_SNAP, classic=True)
    with pytest.raises(_errors.APIError) as ctx:
        _snapd_logs.logs(_SNAP, num_lines=0)
    assert 'invalid value for n' in ctx.value.message


def test_logs_negative_num_lines():
    # snapd accepts negative num_lines without error.
    ensure_installed(_SNAP, classic=True)
    entries = _snapd_logs.logs(_SNAP, num_lines=-1)
    assert isinstance(entries, list)


def test_logs_no_snap_args():
    # Calling logs() with no snap arguments returns system-wide logs.
    entries = _snapd_logs.logs(num_lines=3)
    assert isinstance(entries, list)


# ---------------------------------------------------------------------------
# snap with no services (htop)
# ---------------------------------------------------------------------------


def test_logs_snap_with_no_services_raises():
    # A snap with no services raises AppNotFoundError.
    ensure_installed('htop')
    with pytest.raises(_errors.AppNotFoundError) as ctx:
        _snapd_logs.logs('htop')
    assert ctx.value.kind == 'app-not-found'


# ---------------------------------------------------------------------------
# not-installed snap (uses a never-installed name to avoid churn)
# ---------------------------------------------------------------------------


def test_logs_not_installed_snap_raises():
    # Requesting logs for an uninstalled snap raises NotFoundError.
    with pytest.raises(_errors.NotFoundError) as ctx:
        _snapd_logs.logs(_ABSENT_SNAP)
    assert ctx.value.kind == 'snap-not-found'
