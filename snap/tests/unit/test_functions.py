# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from charmlibs.snap import _functions, _snapd_conf
from charmlibs.snap import _snapd_snaps as _snapd
from charmlibs.snap._errors import BadResponseError, NotInstalledError, OptionNotFoundError


def make_info(
    tracking: str = 'latest/stable',
    revision: int | str = 29,
    classic: bool = False,
    hold: str | None = None,
) -> _snapd.InstalledInfo:
    return _snapd.InstalledInfo(
        name='hello-world',
        tracking=tracking,
        revision=revision,
        version='6.4',
        classic=classic,
        hold=hold,
    )


@dataclass
class MockSnapd:
    list_one: MagicMock
    install: MagicMock
    refresh: MagicMock


@pytest.fixture
def mock_snapd(monkeypatch: pytest.MonkeyPatch) -> MockSnapd:
    mocks = MockSnapd(list_one=MagicMock(), install=MagicMock(), refresh=MagicMock())
    monkeypatch.setattr(_snapd, 'list_one', mocks.list_one)
    monkeypatch.setattr(_snapd, 'install', mocks.install)
    monkeypatch.setattr(_snapd, 'refresh', mocks.refresh)
    return mocks


class TestGetInfo:
    def test_installed(self, mock_snapd: MockSnapd):
        expected = make_info()
        mock_snapd.list_one.return_value = expected
        result = _functions._installed_info('hello-world')
        mock_snapd.list_one.assert_called_once_with('hello-world')
        assert result is expected

    def test_not_installed_returns_none(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.side_effect = NotInstalledError(
            'snap "hello-world" is not installed',
            kind='snap-not-found',
            value='',
            status_code=404,
            status='Not Found',
        )
        result = _functions._installed_info('hello-world')
        assert result is None


class TestEnsureInstalledInstalls:
    def test_not_installed(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = None
        result = _functions.ensure_installed('hello-world')
        mock_snapd.install.assert_called_once_with(
            'hello-world', channel=None, revision=None, classic=False
        )
        assert result is True

    def test_not_installed_channel(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = None
        _functions.ensure_installed('hello-world', channel='edge')
        mock_snapd.install.assert_called_once_with(
            'hello-world', channel='edge', revision=None, classic=False
        )

    def test_not_installed_revision(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = None
        result = _functions.ensure_installed('hello-world', revision=5)
        mock_snapd.install.assert_called_once_with(
            'hello-world', channel=None, revision=5, classic=False
        )
        assert result is True

    def test_not_installed_channel_and_revision(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = None
        _functions.ensure_installed('hello-world', channel='edge', revision=5)
        mock_snapd.install.assert_called_once_with(
            'hello-world', channel='edge', revision=5, classic=False
        )

    def test_not_installed_classic(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = None
        _functions.ensure_installed('hello-world', classic=True)
        mock_snapd.install.assert_called_once_with(
            'hello-world', channel=None, revision=None, classic=True
        )


class TestEnsureInstalledChannel:
    def test_installed_different_channel(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        result = _functions.ensure_installed('hello-world', channel='edge')
        mock_snapd.refresh.assert_called_once_with(
            'hello-world', channel='edge', revision=None, classic=False
        )
        assert result is True

    def test_installed_same_channel_update_true(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        mock_snapd.refresh.return_value = True
        result = _functions.ensure_installed('hello-world', channel='latest/stable')
        mock_snapd.refresh.assert_called_once_with(
            'hello-world', channel='latest/stable', classic=False
        )
        assert result is True

    def test_installed_same_channel_update_false(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        result = _functions.ensure_installed('hello-world', channel='latest/stable', update=False)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_installed_no_channel_update_false(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info()
        result = _functions.ensure_installed('hello-world', update=False)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_installed_normalized_channel(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        result = _functions.ensure_installed('hello-world', channel='stable', update=False)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_risk_only_channel_inherits_track(self, mock_snapd: MockSnapd):
        # 'edge' resolves to '3.6/edge' for a snap on the 3.6 track, not to 'latest/edge',
        # so a snap already on '3.6/edge' is left alone rather than refreshed every call.
        mock_snapd.list_one.return_value = make_info(tracking='3.6/edge')
        result = _functions.ensure_installed('hello-world', channel='edge', update=False)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_risk_only_channel_inherits_track_when_different(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='3.6/stable')
        result = _functions.ensure_installed('hello-world', channel='edge')
        mock_snapd.refresh.assert_called_once_with(
            'hello-world', channel='edge', revision=None, classic=False
        )
        assert result is True

    def test_no_updates_available_returns_false(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        mock_snapd.refresh.return_value = False
        result = _functions.ensure_installed('hello-world', channel='latest/stable')
        assert result is False

    def test_empty_channel_treated_as_none(self, mock_snapd: MockSnapd):
        # channel='' is falsy, so it's treated the same as channel=None:
        # no channel-mismatch refresh, and with update=False no refresh at all.
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        result = _functions.ensure_installed('hello-world', channel='', update=False)
        mock_snapd.refresh.assert_not_called()
        assert result is False


class TestEnsureInstalledRevision:
    def test_installed_same_revision(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(revision=5)
        result = _functions.ensure_installed('hello-world', revision=5)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    @pytest.mark.parametrize('revision', [5, '5'])
    def test_revision_may_be_int_or_str(self, mock_snapd: MockSnapd, revision: int | str):
        mock_snapd.list_one.return_value = make_info(revision=5)
        result = _functions.ensure_installed('hello-world', revision=revision)
        mock_snapd.refresh.assert_not_called()
        assert result is False

    def test_installed_different_revision(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(revision=5)
        result = _functions.ensure_installed('hello-world', revision=6)
        mock_snapd.refresh.assert_called_once_with(
            'hello-world', channel=None, revision=6, classic=False
        )
        assert result is True

    def test_same_revision_different_channel_refreshes(self, mock_snapd: MockSnapd):
        # The revision is already installed, but the snap tracks the wrong channel, so it
        # still needs a refresh -- snapd moves the tracking channel without changing revision.
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable', revision=5)
        result = _functions.ensure_installed('hello-world', channel='edge', revision=5)
        mock_snapd.refresh.assert_called_once_with(
            'hello-world', channel='edge', revision=5, classic=False
        )
        assert result is True

    @pytest.mark.parametrize('update', [True, False])
    def test_update_ignored_when_revision_matches(self, mock_snapd: MockSnapd, update: bool):
        # A revision fully specifies what to install, so there's nothing to update to.
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable', revision=5)
        result = _functions.ensure_installed(
            'hello-world', channel='stable', revision=5, update=update
        )
        mock_snapd.refresh.assert_not_called()
        assert result is False


class TestEnsureInstalledClassic:
    def test_classic_passed_to_refresh(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        _functions.ensure_installed('hello-world', channel='edge', classic=True)
        assert mock_snapd.refresh.call_args.kwargs['classic'] is True

    def test_classic_passed_to_update_refresh(self, mock_snapd: MockSnapd):
        mock_snapd.list_one.return_value = make_info(tracking='latest/stable')
        _functions.ensure_installed('hello-world', channel='latest/stable', classic=True)
        assert mock_snapd.refresh.call_args.kwargs['classic'] is True


@dataclass
class MockConf:
    get_one: MagicMock
    set: MagicMock


@pytest.fixture
def mock_conf(monkeypatch: pytest.MonkeyPatch) -> MockConf:
    mocks = MockConf(get_one=MagicMock(), set=MagicMock())
    monkeypatch.setattr(_snapd_conf, 'get_one', mocks.get_one)
    monkeypatch.setattr(_snapd_conf, 'set', mocks.set)
    return mocks


class TestEnsureVitalityHint:
    def test_unset_adds_snap(self, mock_conf: MockConf):
        # Captured from snapd when the option has never been set (or was unset).
        mock_conf.get_one.side_effect = OptionNotFoundError(
            'snap "core" has no "resilience" configuration option',
            kind='option-not-found',
            value={'SnapName': 'core', 'Key': 'resilience'},
        )
        result = _functions.ensure_vitality_hint('foo')
        mock_conf.get_one.assert_called_once_with('system', 'resilience.vitality-hint')
        mock_conf.set.assert_called_once_with('system', {'resilience.vitality-hint': 'foo'})
        assert result is True

    def test_empty_string_adds_snap(self, mock_conf: MockConf):
        # snapd stores '' when the option is set to an empty string.
        mock_conf.get_one.return_value = ''
        result = _functions.ensure_vitality_hint('foo')
        mock_conf.set.assert_called_once_with('system', {'resilience.vitality-hint': 'foo'})
        assert result is True

    def test_appends_after_existing_snaps(self, mock_conf: MockConf):
        mock_conf.get_one.return_value = 'bar,baz'
        result = _functions.ensure_vitality_hint('foo')
        mock_conf.set.assert_called_once_with(
            'system', {'resilience.vitality-hint': 'bar,baz,foo'}
        )
        assert result is True

    @pytest.mark.parametrize('current', ['foo', 'foo,bar', 'bar,foo', 'bar,foo,baz'])
    def test_already_listed_is_no_op(self, mock_conf: MockConf, current: str):
        mock_conf.get_one.return_value = current
        result = _functions.ensure_vitality_hint('foo')
        mock_conf.set.assert_not_called()
        assert result is False

    def test_instance_name_is_distinct_from_snap_name(self, mock_conf: MockConf):
        mock_conf.get_one.return_value = 'foo'
        result = _functions.ensure_vitality_hint('foo_bar')
        mock_conf.set.assert_called_once_with(
            'system', {'resilience.vitality-hint': 'foo,foo_bar'}
        )
        assert result is True

    @pytest.mark.parametrize('snap', ['', ' ', 'foo,bar', ' foo', 'foo '])
    def test_invalid_snap_name_raises_before_request(self, mock_conf: MockConf, snap: str):
        with pytest.raises(ValueError, match='snap name'):
            _functions.ensure_vitality_hint(snap)
        mock_conf.get_one.assert_not_called()
        mock_conf.set.assert_not_called()

    def test_non_string_value_raises_bad_response(self, mock_conf: MockConf):
        mock_conf.get_one.return_value = {'foo': 1}
        with pytest.raises(BadResponseError):
            _functions.ensure_vitality_hint('foo')
        mock_conf.set.assert_not_called()
