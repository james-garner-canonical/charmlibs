# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportPrivateUsage=false

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from charmlibs.snap import _snapd_aliases
from charmlibs.snap._errors import SnapNotInstalledError
from conftest import result_of

if TYPE_CHECKING:
    from conftest import MockClient


class TestAlias:
    def test_alias(self, mock_client: MockClient):
        _snapd_aliases.alias('lxd', 'lxc', 'testlxc')
        mock_client.post.assert_called_once_with(
            '/v2/aliases',
            body={'action': 'alias', 'snap': 'lxd', 'app': 'lxc', 'alias': 'testlxc'},
        )

    def test_alias_not_installed_raises(self, mock_client: MockClient):
        mock_client.post.side_effect = SnapNotInstalledError(
            'snap "hello-world" is not installed',
            kind='snap-not-installed',
            value='hello-world',
            status_code=400,
            status='Bad Request',
        )
        with pytest.raises(SnapNotInstalledError):
            _snapd_aliases.alias('hello-world', 'hello', 'test-alias')


class TestUnalias:
    def test_unalias(self, mock_client: MockClient):
        _snapd_aliases.unalias('testlxc')
        mock_client.post.assert_called_once_with(
            '/v2/aliases',
            body={'action': 'unalias', 'alias': 'testlxc'},
        )

    def test_unalias_no_snap_or_app(self, mock_client: MockClient):
        _snapd_aliases.unalias('testlxc')
        body = mock_client.post.call_args.kwargs['body']
        assert 'snap' not in body
        assert 'app' not in body


class TestListAliases:
    def test_list_empty(self, mock_client: MockClient):
        mock_client.get.return_value = {}
        result = _snapd_aliases._list_aliases()
        assert result == {}

    def test_list_with_entry(self, mock_client: MockClient):
        mock_client.get.return_value = result_of('aliases_with_entry.json')
        result = _snapd_aliases._list_aliases()
        assert 'lxd' in result
        assert 'testlxc' in result['lxd']

    def test_list_endpoint(self, mock_client: MockClient):
        mock_client.get.return_value = {}
        _snapd_aliases._list_aliases()
        mock_client.get.assert_called_once_with('/v2/aliases')
