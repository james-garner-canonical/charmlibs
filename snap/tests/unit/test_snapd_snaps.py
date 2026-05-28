# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from charmlibs.snap import _snapd_snaps as _snapd
from charmlibs.snap._errors import (
    SnapError,
    SnapNotFoundError,
    SnapNotInstalledError,
    _SnapAlreadyInstalledError,
    _SnapNoUpdatesAvailableError,
)
from conftest import result_of

if TYPE_CHECKING:
    from conftest import MockClient


def _make_snap_not_found():
    return SnapNotFoundError(
        'snap "hello-world" is not installed',
        kind='snap-not-found',
        value='',
        status_code=404,
        status='Not Found',
    )


def _minimal_info_dict(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        'name': 'hello-world',
        'version': '6.4',
        'channel': 'latest/stable',
        'revision': '29',
        'confinement': 'strict',
    }
    base.update(overrides)
    return base


class TestInfoFromDict:
    def test_basic_fields(self):
        info = _snapd.Info._from_dict(_minimal_info_dict())
        assert info.name == 'hello-world'
        assert info.version == '6.4'
        assert info.channel == 'latest/stable'
        assert info.revision == '29'
        assert info.classic is False

    def test_revision_is_str(self):
        info = _snapd.Info._from_dict(_minimal_info_dict(revision='29'))
        assert isinstance(info.revision, str)
        assert info.revision == '29'

    def test_local_revision(self):
        info = _snapd.Info._from_dict(_minimal_info_dict(revision='x1'))
        assert info.revision == 'x1'

    def test_strict_not_classic(self):
        info = _snapd.Info._from_dict(_minimal_info_dict(confinement='strict'))
        assert info.classic is False

    def test_devmode_not_classic(self):
        info = _snapd.Info._from_dict(_minimal_info_dict(confinement='devmode'))
        assert info.classic is False

    def test_classic(self):
        info = _snapd.Info._from_dict(_minimal_info_dict(confinement='classic'))
        assert info.classic is True

    def test_extra_fields_ignored(self):
        d = _minimal_info_dict()
        d.update({
            'tracking-channel': 'latest/stable',
            'type': 'app',
            'devmode': False,
            'jailmode': False,
            'enabled': True,
            'status': 'active',
        })
        info = _snapd.Info._from_dict(d)
        assert info.name == 'hello-world'


class TestInfo:
    def test_info_installed(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snap_info_hello_world.json')
        info = _snapd.info('hello-world')
        assert info.name == 'hello-world'
        assert info.revision == '29'
        mock_client.get.assert_called_once_with('/v2/snaps/hello-world')

    def test_info_classic(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('snap_info_kube_proxy.json')
        info = _snapd.info('kube-proxy')
        assert info.classic is True

    def test_info_missing_ok_false(self, mock_client: MockClient):
        mock_client.get.side_effect = _make_snap_not_found()
        with pytest.raises(SnapNotFoundError):
            _snapd.info('hello-world')

    def test_info_missing_ok_true(self, mock_client: MockClient):
        mock_client.get.side_effect = _make_snap_not_found()
        result = _snapd.info('hello-world', missing_ok=True)
        assert result is None

    def test_info_other_error_propagates(self, mock_client: MockClient):
        mock_client.get.side_effect = SnapError(
            'internal error',
            kind='internal-error',
            value='',
            status_code=500,
            status='Internal Server Error',
        )
        with pytest.raises(SnapError):
            _snapd.info('hello-world', missing_ok=True)


class TestInstall:
    def test_install_minimal(self, mock_client: MockClient):
        result = _snapd.install('hello-world')
        mock_client.post.assert_called_once_with(
            '/v2/snaps/hello-world', body={'action': 'install'}
        )
        assert result is True

    def test_install_channel(self, mock_client: MockClient):
        _snapd.install('hello-world', channel='edge')
        body = mock_client.post.call_args.kwargs['body']
        assert body['channel'] == 'edge'

    def test_install_revision(self, mock_client: MockClient):
        _snapd.install('hello-world', revision=5)
        body = mock_client.post.call_args.kwargs['body']
        assert body['revision'] == '5'  # sent as string per snapd API convention

    def test_install_classic(self, mock_client: MockClient):
        _snapd.install('hello-world', classic=True)
        body = mock_client.post.call_args.kwargs['body']
        assert body['classic'] is True

    def test_install_both_raises(self, mock_client: MockClient):
        with pytest.raises(ValueError):
            _snapd.install('hello-world', channel='edge', revision=5)  # type: ignore[call-overload]
        mock_client.post.assert_not_called()

    def test_install_already_installed_returns_false(self, mock_client: MockClient):
        mock_client.post.side_effect = _SnapAlreadyInstalledError('', kind='', value='')
        result = _snapd.install('hello-world')
        assert result is False


class TestRemove:
    def test_remove(self, mock_client: MockClient):
        result = _snapd.remove('hello-world')
        mock_client.post.assert_called_once_with(
            '/v2/snaps/hello-world', body={'action': 'remove'}
        )
        assert result is True

    def test_remove_purge(self, mock_client: MockClient):
        _snapd.remove('hello-world', purge=True)
        body = mock_client.post.call_args.kwargs['body']
        assert body['purge'] is True

    def test_remove_not_installed_returns_false(self, mock_client: MockClient):
        mock_client.post.side_effect = SnapNotInstalledError(
            '', kind='snap-not-installed', value=''
        )
        result = _snapd.remove('hello-world')
        assert result is False


class TestRefresh:
    def test_refresh_minimal(self, mock_client: MockClient):
        result = _snapd.refresh('hello-world')
        body = mock_client.post.call_args.kwargs['body']
        assert body == {'action': 'refresh'}
        assert result is True

    def test_refresh_channel(self, mock_client: MockClient):
        _snapd.refresh('hello-world', channel='edge')
        body = mock_client.post.call_args.kwargs['body']
        assert body['channel'] == 'edge'

    def test_refresh_revision(self, mock_client: MockClient):
        _snapd.refresh('hello-world', revision=42)
        body = mock_client.post.call_args.kwargs['body']
        assert body['revision'] == '42'

    def test_refresh_both_raises(self, mock_client: MockClient):
        with pytest.raises(ValueError):
            _snapd.refresh('hello-world', channel='edge', revision=42)  # type: ignore[call-overload]

    def test_refresh_no_updates_returns_false(self, mock_client: MockClient):
        mock_client.post.side_effect = _SnapNoUpdatesAvailableError(
            'snap "hello-world" has no updates available',
            kind='snap-no-update-available',
            value='',
            status_code=400,
            status='Bad Request',
        )
        result = _snapd.refresh('hello-world')
        assert result is False


class TestRemoveAdditionalCases:
    def test_remove_purge_not_installed_returns_false(self, mock_client: MockClient):
        mock_client.post.side_effect = SnapNotInstalledError(
            'snap "hello-world" is not installed',
            kind='snap-not-installed',
            value='hello-world',
            status_code=404,
            status='Not Found',
        )
        result = _snapd.remove('hello-world', purge=True)
        assert result is False
