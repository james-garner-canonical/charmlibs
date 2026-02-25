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

from __future__ import annotations

import dataclasses
import datetime
import typing
from typing import Any, Literal

from . import _client, _errors

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from typing_extensions import Self


@dataclasses.dataclass
class SnapInfo:
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
            hold=info_dict.get('hold'),
        )


# Info/List


@typing.overload
def info(snap: str, *, missing_ok: Literal[False] = False) -> SnapInfo: ...
@typing.overload
def info(snap: str, *, missing_ok: Literal[True]) -> SnapInfo | None: ...
def info(snap: str, *, missing_ok: bool = False) -> SnapInfo | None:
    """Get information about an installed snap."""
    try:
        info_dict = _client.get(f'/v2/snaps/{snap}')
    except _errors.SnapNotFoundError:
        if missing_ok:
            return None
        raise
    assert isinstance(info_dict, dict)
    return SnapInfo._from_dict(info_dict)


def channels(snap: str) -> dict[str, SnapInfo]:
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
    return {k: SnapInfo._from_dict({'name': snap, 'channel': k, **v}) for k, v in channels.items()}


# Configuration


def get(snap: str, *keys: str) -> dict[str, Any]:
    """Get snap configuration."""
    params = {'keys': ','.join(keys)} if keys else None
    config = _client.get(f'/v2/snaps/{snap}/conf', query=params)
    assert isinstance(config, dict)
    return config


def get_one(snap: str, key: str) -> Any:
    """Get a single snap configuration key."""
    config = get(snap, key)
    return config[key]


def set(snap: str, config: dict[str, Any]) -> None:  # noqa: A001
    """Set snap configuration."""
    _client.put(f'/v2/snaps/{snap}/conf', body=config)


def unset(snap: str, key: str, *keys: str) -> None:
    """Unset snap configuration keys."""
    _client.put(f'/v2/snaps/{snap}/conf', body=dict.fromkeys((key, *keys)))


# Aliases


def alias(snap: str, app: str, alias_name: str) -> None:
    """Create an alias for a snap app."""
    data = {'action': 'alias', 'snap': snap, 'app': app, 'alias': alias_name}
    _client.post('/v2/aliases', body=data)


def unalias(alias_name: str) -> None:
    """Remove an alias."""
    data = {'action': 'unalias', 'alias': alias_name}
    _client.post('/v2/aliases', body=data)


# Interfaces


def connect(plug_snap: str, plug: str, slot_snap: str | None = None, slot: str | None = None, /) -> None:
    """Connect a snap and plug, to a target snap and slot."""
    data = {
        'action': 'connect',
        'plugs': [{'snap': plug_snap, 'plug': plug}],
        'slots': [{'snap': slot_snap or '', 'slot': slot or ''}],
    }
    _client.post('/v2/interfaces', body=data)


def disconnect(
    plug_or_slot_snap: str,
    plug_or_slot: str,
    slot_snap: str | None = None,
    slot: str | None = None,
    /,
    *,
    forget: bool = False,
) -> None:
    """Disconnect a plug from a slot."""
    data: dict[str, Any] = {'action': 'disconnect'}
    if slot_snap is None:
        assert slot is None
        # Called with 2 arguments, treat as as snap disconnect <snap>:<slot>
        data['plugs'] = [{'snap': '', 'plug': ''}]
        data['slots'] = [{'snap': plug_or_slot_snap, 'slot': plug_or_slot}]
    else:
        # Called with 3 or 4 arguments, treat as snap disconnect <snap>:<plug> <snap>:<slot>
        data['plugs'] = [{'snap': plug_or_slot_snap, 'plug': plug_or_slot}]
        data['slots'] = [{'snap': slot_snap, 'slot': slot or ''}]
    if forget:
        data['forget'] = True
    _client.post('/v2/interfaces', body=data)


# Install/Remove/Refresh


def install(
    snap: str, channel: str | None = None, revision: int | None = None, classic: bool = False
) -> None:
    """Install a snap."""
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


def remove(snap: str, purge: bool = False, missing_ok: bool = False) -> None:
    """Remove a snap."""
    data: dict[str, Any] = {'action': 'remove'}
    if purge:
        data['purge'] = True
    try:
        _client.post(f'/v2/snaps/{snap}', body=data)
    except _errors.SnapNotInstalledError:
        if not missing_ok:
            raise


def refresh(
    snap: str, channel: str | None = None, revision: int | None = None, no_updates_ok: bool = False
) -> bool:
    """Refresh a snap."""
    if channel is not None and revision is not None:
        raise ValueError('Only one of channel or revision may be specified')
    data = {'action': 'refresh'}
    if channel:
        data['channel'] = channel
    if revision:
        data['revision'] = str(revision)
    try:
        _client.post(f'/v2/snaps/{snap}', body=data)
    except _errors.SnapNoUpdatesAvailableError:
        if not no_updates_ok:
            raise


# Hold/Unhold


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


# Services


def start(snap: str, *services: str, enable: bool = False) -> None:
    """Start snap services."""
    names = [f'{snap}.{s}' for s in services] if services else [snap]
    data: dict[str, Any] = {'action': 'start', 'names': names}
    if enable:
        data['enable'] = True
    _client.post('/v2/apps', body=data)


def stop(snap: str, *services: str, disable: bool = False) -> None:
    """Stop snap services."""
    names = [f'{snap}.{s}' for s in services] if services else [snap]
    data: dict[str, Any] = {'action': 'stop', 'names': names}
    if disable:
        data['disable'] = True
    _client.post('/v2/apps', body=data)


def restart(snap: str, *services: str) -> None:
    """Restart snap services."""
    names = [f'{snap}.{s}' for s in services] if services else [snap]
    data: dict[str, Any] = {'action': 'restart', 'names': names}
    _client.post('/v2/apps', body=data)


# logs


def logs(*snaps: str, num_lines: int = 10) -> list[dict[str, Any]]:
    query: dict[str, Any] = {'n': num_lines}
    if snaps:
        query['names'] = ','.join(snaps)
    result = _client.get('/v2/logs', query=query)
    assert isinstance(result, list)
    return result


# List stuff, probably won't be part of the public API


def list_snaps() -> list[SnapInfo]:
    """List all installed snaps."""
    info_dicts = _client.get('/v2/snaps')
    assert isinstance(info_dicts, list)
    return [SnapInfo._from_dict(info_dict) for info_dict in info_dicts]


def list_aliases() -> Mapping[str, Iterable[str]]:
    """List all aliases."""
    aliases = _client.get('/v2/aliases')
    assert isinstance(aliases, dict)
    return aliases


def list_services(snap: str | None = None) -> list[dict[str, Any]]:
    """List snap services."""
    query = {'select': 'service'}
    if snap:
        query['names'] = snap
    services = _client.get('/v2/apps', query=query)
    assert isinstance(services, list)
    return services


def list_interfaces(snap: str | None = None) -> list[dict[str, Any]]:
    """List snap interfaces."""
    query = {'select': 'all', 'slots': 'true', 'plugs': 'true'}
    interfaces = _client.get('/v2/interfaces', query=query)
    assert isinstance(interfaces, list)
    if snap is None:
        return interfaces
    return [
        i
        for i in interfaces
        if any(p['snap'] == snap for p in i.get('plugs', []))
        or any(s['snap'] == snap for s in i.get('slots', []))
    ]
