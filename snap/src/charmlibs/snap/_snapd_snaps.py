# Copyright 2021 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Snap operations implemented as direct calls to the snapd REST API."""

from __future__ import annotations

import logging
import typing
from typing import Any, Literal

from . import _client, _errors, _utils

if typing.TYPE_CHECKING:
    from typing_extensions import Self


logger = logging.getLogger(__name__)

# /v2/snaps/{snap}


class Info:
    def __init__(
        self,
        name: str,
        classic: bool,
        channel: str,
        revision: int | str,
        version: str,
    ):
        self._name = name
        self._classic = classic
        self._channel = _utils._normalize_channel(channel)
        self._revision = str(revision)
        self._version = version

    @classmethod
    def _from_dict(cls, info_dict: dict[str, str]) -> Self:
        return cls(
            name=info_dict['name'],
            channel=info_dict['channel'],
            revision=info_dict['revision'],
            version=info_dict['version'],
            classic=info_dict['confinement'] == 'classic',
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def classic(self) -> bool:
        return self._classic

    @property
    def channel(self) -> str:
        return self._channel

    @property
    def revision(self) -> str:
        return self._revision

    @property
    def version(self) -> str:
        return self._version


@typing.overload
def info(snap: str, *, missing_ok: Literal[False] = False) -> Info: ...
@typing.overload
def info(snap: str, *, missing_ok: Literal[True]) -> Info | None: ...
def info(snap: str, *, missing_ok: bool = False) -> Info | None:
    """Get information about an installed snap.

    This function implements the semantics of the `snap list` command,
    restricted to a single snap.

    Args:
        snap: the name of the snap.
        missing_ok: if ``True``, return ``None`` if the snap is not installed.
            if ``False`` (default), raise ``SnapNotFoundError`` instead.

    Returns:
        An Info object with information about the snap,
            or None if the snap is not installed and missing_ok is ``True``.

    Raises:
        SnapNotFoundError: if the snap is not installed and ``missing_ok`` is ``False``.
        SnapError: (or a subtype) if the information could not be retrieved for another reason.
    """
    try:
        info_dict = _client.get(f'/v2/snaps/{snap}')
    except _errors.SnapNotFoundError:
        if missing_ok:
            return None
        raise
    assert isinstance(info_dict, dict)
    return Info._from_dict(info_dict)


@typing.overload
def install(snap: str, *, channel: str, revision: None = None, classic: bool = False) -> bool: ...
@typing.overload
def install(
    snap: str, *, channel: None = None, revision: int | str, classic: bool = False
) -> bool: ...
@typing.overload
def install(
    snap: str, *, channel: None = None, revision: None = None, classic: bool = False
) -> bool: ...
def install(
    snap: str,
    *,
    channel: str | None = None,
    revision: int | str | None = None,
    classic: bool = False,
) -> bool:
    """Install a snap.

    Returns:
        True if the snap was installed, False if it was already installed.

    Raises:
        ValueError: if both channel and revision are specified.
        SnapNotFoundError: if the snap does not exist in the store.
        SnapRevisionNotAvailableError: if the specified revision is not available.
        SnapChannelNotAvailableError: if the specified channel is not available.
        SnapNeedsClassicError: if the snap requires classic confinement and ``classic`` is not set.
        SnapError: (or a subtype) if the snap could not be installed for another reason.
    """
    if channel is not None and revision is not None:
        # NOTE: Revision silently takes precedence over channel in the snapd API.
        # The CLI instead returns an error if the specified revision doesn't exist on that channel.
        raise ValueError('Only one of channel or revision may be specified')
    data: dict[str, Any] = {'action': 'install'}
    if channel:
        data['channel'] = channel
    if revision:
        data['revision'] = str(revision)
    if classic:
        data['classic'] = True
    # NOTE: Unlike the API, the CLI doesn't error if it's already installed (just prints a msg).
    try:
        _client.post(f'/v2/snaps/{snap}', body=data)
    except _errors._SnapAlreadyInstalledError:
        return False
    return True


def remove(snap: str, *, purge: bool = False) -> bool:
    """Remove a snap.

    Returns:
        True if the snap was removed, False if it was not installed.

    Raises:
        SnapError: (or a subtype) if the snap could not be removed as requested.
    """
    data: dict[str, Any] = {'action': 'remove'}
    if purge:
        data['purge'] = True
    # NOTE: Unlike the API, the CLI doesn't error if the snap isn't installed (just prints a msg).
    try:
        _client.post(f'/v2/snaps/{snap}', body=data)
    except _errors.SnapNotInstalledError:
        return False
    return True


@typing.overload
def refresh(snap: str, channel: str, *, revision: None = None) -> bool: ...
@typing.overload
def refresh(snap: str, channel: None = None, *, revision: int | str) -> bool: ...
@typing.overload
def refresh(snap: str, channel: None = None, *, revision: None = None) -> bool: ...
def refresh(
    snap: str,
    channel: str | None = None,
    *,
    revision: int | str | None = None,
) -> bool:
    """Refresh a snap.

    Returns:
        True if the snap was refreshed, False if no updates were available.

    Raises:
        ValueError: if both channel and revision are specified.
        SnapRevisionNotAvailableError: if the specified revision is not available.
        SnapChannelNotAvailableError: if the specified channel is not available.
        SnapError: (or a subtype) if the snap could not be refreshed for another reason.
    """
    if channel is not None and revision is not None:
        # NOTE: Revision silently takes precedence over channel in the snapd API.
        # The CLI instead returns an error if the specified revision doesn't exist on that channel.
        raise ValueError('Only one of channel or revision may be specified')
    data = {'action': 'refresh'}
    if channel:
        data['channel'] = channel
    if revision:
        data['revision'] = str(revision)
    # NOTE: Unlike the API, the CLI doesn't error if there are no updates (just prints a msg).
    try:
        _client.post(f'/v2/snaps/{snap}', body=data)
    except _errors._SnapNoUpdatesAvailableError:
        return False
    return True
