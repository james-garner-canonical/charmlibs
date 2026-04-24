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

import dataclasses
import datetime
import logging
import typing
from typing import Any, Literal

from . import _client, _errors

if typing.TYPE_CHECKING:
    from typing_extensions import Self


logger = logging.getLogger(__name__)

# /v2/snaps/{snap}


@dataclasses.dataclass
class Info:
    name: str
    classic: bool
    channel: str
    revision: int
    version: str
    hold: str | None

    @classmethod
    def _from_dict(cls, info_dict: dict[str, Any]) -> Self:
        return cls(
            name=info_dict['name'],
            channel=info_dict['channel'],
            revision=int(info_dict['revision']),
            version=info_dict['version'],
            classic=info_dict['confinement'] == 'classic',
            # TODO: should we convert hold to a datetime.datetime?
            # see the functional tests for the code that would be involved
            # depends on both the Python version and the snapd version
            hold=info_dict.get('hold'),
        )


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


def install(
    snap: str,
    *,
    channel: str | None = None,
    revision: int | None = None,
    classic: bool = False,
) -> None:
    """Install a snap.

    Raises:
        ValueError: if both channel and revision are specified.
        SnapAlreadyInstalledError: if the snap is already installed.
        SnapError: (or a subtype) if the snap could not be installed as requested.
    """
    if channel is not None and revision is not None:
        raise ValueError('Only one of channel or revision may be specified')
    data: dict[str, Any] = {'action': 'install'}
    if channel:
        data['channel'] = channel
    if revision:
        data['revision'] = str(revision)
    if classic:
        data['classic'] = True
    _client.post(f'/v2/snaps/{snap}', body=data)


def remove(snap: str, *, purge: bool = False) -> None:
    """Remove a snap.

    Raises:
        SnapNotFoundError: if the snap is not installed.
        SnapError: (or a subtype) if the snap could not be removed as requested.
    """
    data: dict[str, Any] = {'action': 'remove'}
    if purge:
        data['purge'] = True
    _client.post(f'/v2/snaps/{snap}', body=data)


def refresh(snap: str, channel: str | None = None, revision: int | None = None) -> None:
    """Refresh a snap.

    Raises:
        ValueError: if both channel and revision are specified.
        SnapError: (or a subtype) if the snap could not be refreshed as requested.
    """
    if channel is not None and revision is not None:
        # Note: If we passed both, revision would silently take precedence over channel.
        raise ValueError('Only one of channel or revision may be specified')
    data = {'action': 'refresh'}
    if channel:
        data['channel'] = channel
    if revision:
        data['revision'] = str(revision)
    try:
        _client.post(f'/v2/snaps/{snap}', body=data)
    except _errors._SnapNoUpdatesAvailableError:
        pass  # Follow the snap CLI's lead and suppress this error.


def hold(snap: str, duration: datetime.timedelta | int | float | None = None) -> None:
    """Hold a snap to prevent it from being automatically refreshed.

    Does not prevent manual refreshes.
    """
    # https://forum.snapcraft.io/t/snapd-rest-api/17954
    if duration is None:
        until = 'forever'
    else:
        if isinstance(duration, datetime.timedelta):
            delta = duration
        else:
            delta = datetime.timedelta(seconds=duration)
        until = (datetime.datetime.now(datetime.timezone.utc) + delta).isoformat()
    data = {'action': 'hold', 'hold-level': 'general', 'time': until}
    _client.post(f'/v2/snaps/{snap}', body=data)


def unhold(snap: str) -> None:
    """Unhold a snap to allow it to be refreshed."""
    _client.post(f'/v2/snaps/{snap}', body={'action': 'unhold'})


def _list_snaps() -> list[Info]:  # pyright: ignore[reportUnusedFunction]
    """List all installed snaps."""
    info_dicts = _client.get('/v2/snaps')
    assert isinstance(info_dicts, list)
    return [Info._from_dict(info_dict) for info_dict in info_dicts]


# /v2/find


def _list_channels(snap: str) -> dict[str, Info]:  # pyright: ignore[reportUnusedFunction]
    """List information about all channels of a snap available in the store."""
    results = _client.get('/v2/find', query={'name': snap})
    assert isinstance(results, list)
    # API returns a list of results, or an error if there are no matches.
    # We'll have one result for an exact name match.
    result, *_ = results
    # A result has information like this:
    # {
    #     # ...
    #     'channels': {
    #         # ...
    #         'latest/stable': {
    #             'revision': '226',
    #             'confinement': 'classic',
    #             'version': '07258626',
    #             'channel': 'latest/stable',
    #             'epoch': {'read': [0], 'write': [0]},
    #             'size': 352374784,
    #             'released-at': '2026-02-19T23:54:26.844384Z'
    #         },
    #     },
    # }
    channels = result['channels']
    return {k: Info._from_dict({'name': snap, 'channel': k, **v}) for k, v in channels.items()}
