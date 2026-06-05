#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_aliases: alias, unalias."""

import subprocess

import pytest

from charmlibs.snap import _errors, _snapd_aliases
from conftest import ensure_installed, ensure_removed

_SNAP = 'lxd'
_APP = 'lxc'
_ALIAS = 'test-functional-lxc-alias'

# A snap name that is never installed — used for error paths where any absent
# snap produces the same error response, avoiding unnecessary remove operations.
_ABSENT_SNAP = 'this-snap-does-not-exist-xyz-abc-123'


def _cleanup_alias() -> None:
    """Remove the test alias if it exists, ignoring errors."""
    try:
        _snapd_aliases.unalias(_ALIAS)
    except Exception:  # noqa: S110
        pass


def _alias_exists() -> bool:
    result = subprocess.check_output(['snap', 'aliases'], text=True)
    return any(
        line.split()[:3] == [f'{_SNAP}.{_APP}', _ALIAS, 'manual'] for line in result.splitlines()
    )


# ---------------------------------------------------------------------------
# alias (lxd installed)
# ---------------------------------------------------------------------------


def test_alias_creates_alias():
    ensure_installed(_SNAP)
    _cleanup_alias()
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    assert _alias_exists()
    _cleanup_alias()


def test_alias_nonexistent_app_raises_snap_change_error():
    # Aliasing to an app that doesn't exist fails as an async change error.
    ensure_installed(_SNAP)
    _cleanup_alias()
    with pytest.raises(_errors.ChangeError):
        _snapd_aliases.alias(_SNAP, 'nonexistent-app', _ALIAS)
    _cleanup_alias()


def test_alias_is_idempotent():
    # Calling alias() again with the same snap, app, and alias name succeeds silently.
    ensure_installed(_SNAP)
    _cleanup_alias()
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)  # second call — no error
    assert _alias_exists()
    _cleanup_alias()


def test_alias_reassigns_within_same_snap():
    # Calling alias() with the same alias name but a different app of the same snap
    # silently reassigns the alias — no error raised.
    ensure_installed(_SNAP)
    _cleanup_alias()
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    _snapd_aliases.alias(_SNAP, 'lxd', _ALIAS)  # different app, same snap — no error
    _cleanup_alias()


def test_alias_name_conflicts_with_snap_command_namespace():
    # Using a snap's own name as the alias name conflicts with its command namespace.
    ensure_installed(_SNAP)
    _cleanup_alias()
    with pytest.raises(_errors.ChangeError) as ctx:
        _snapd_aliases.alias(_SNAP, _APP, _SNAP)  # alias name = 'lxd'
    assert 'conflicts with the command namespace' in ctx.value.message


# ---------------------------------------------------------------------------
# unalias (lxd installed)
# ---------------------------------------------------------------------------


def test_unalias_removes_alias():
    ensure_installed(_SNAP)
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    assert _alias_exists()
    _snapd_aliases.unalias(_ALIAS)
    assert not _alias_exists()


def test_unalias_nonexistent_alias_raises():
    # Unaliasing an alias that doesn't exist raises a base Error (no kind).
    ensure_installed(_SNAP)
    _cleanup_alias()
    with pytest.raises(_errors.Error) as ctx:
        _snapd_aliases.unalias(_ALIAS)
    assert not ctx.value.kind
    assert 'cannot find' in ctx.value.message or _ALIAS in ctx.value.message


# ---------------------------------------------------------------------------
# _list_aliases (lxd installed)
# ---------------------------------------------------------------------------


def test_list_aliases_returns_dict():
    ensure_installed(_SNAP)
    aliases = _snapd_aliases._list_aliases()
    assert isinstance(aliases, dict)


def test_list_aliases_includes_created_alias():
    ensure_installed(_SNAP)
    _cleanup_alias()
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    aliases = _snapd_aliases._list_aliases()
    assert _SNAP in aliases
    _cleanup_alias()


# ---------------------------------------------------------------------------
# hello-world installed (test cross-snap alias conflicts)
# ---------------------------------------------------------------------------


def test_alias_duplicate_name_different_snap_raises():
    # An alias name already claimed by another snap raises ChangeError.
    ensure_installed(_SNAP)
    ensure_installed('hello-world')
    _cleanup_alias()
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    with pytest.raises(_errors.ChangeError) as ctx:
        _snapd_aliases.alias('hello-world', 'hello-world', _ALIAS)
    assert 'already enabled for' in ctx.value.message
    _cleanup_alias()


# ---------------------------------------------------------------------------
# not-installed snap (uses a never-installed name to avoid churn)
# ---------------------------------------------------------------------------


def test_alias_not_installed_snap_raises():
    with pytest.raises(_errors.NotInstalledError) as ctx:
        _snapd_aliases.alias(_ABSENT_SNAP, 'hello', 'test-not-installed-alias')
    assert ctx.value.kind == 'snap-not-installed'


# ---------------------------------------------------------------------------
# unalias after snap removed — last because it removes lxd
# ---------------------------------------------------------------------------


def test_unalias_after_snap_removed_raises():
    # Aliases don't survive snap removal; unaliasing after removal raises the same error
    # as attempting to remove an alias that was never created.
    ensure_installed(_SNAP)
    _cleanup_alias()
    _snapd_aliases.alias(_SNAP, _APP, _ALIAS)
    ensure_removed(_SNAP)
    with pytest.raises(_errors.APIError) as ctx:
        _snapd_aliases.unalias(_ALIAS)
    assert not ctx.value.kind
    assert 'cannot find' in ctx.value.message
