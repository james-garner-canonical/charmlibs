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
import typing
from typing import Any

from . import _client

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from typing_extensions import Self


@dataclasses.dataclass
class SnapInfo:
    name: str
    channel: str
    revision: int
    version: str
    classic: bool

    @classmethod
    def _from_dict(cls, info_dict: dict[str, Any]) -> Self:
        return cls(
            name=info_dict['name'],
            channel=info_dict['channel'],
            revision=int(info_dict['revision']),
            version=info_dict['version'],
            classic=info_dict['confinement'] == 'classic',
        )


# Info/List
def info(name: str) -> SnapInfo:
    """Get information about a snap."""
    info_dict = _client.get(f'/v2/snaps/{name}')
    assert isinstance(info_dict, dict)
    return SnapInfo._from_dict(info_dict)


def list_snaps() -> list[SnapInfo]:
    """List all installed snaps."""
    info_dicts = _client.get('/v2/snaps')
    assert isinstance(info_dicts, list)
    return [SnapInfo._from_dict(info_dict) for info_dict in info_dicts]


# Configuration
def get(snap: str, *keys: str) -> dict[str, Any]:
    """Get snap configuration."""
    params = {'keys': ','.join(keys)} if keys else None
    config = _client.get(f'/v2/snaps/{snap}/conf', query=params)
    assert isinstance(config, dict)
    return config


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


def unalias(snap: str, alias_name: str) -> None:
    """Remove an alias."""
    data = {'action': 'unalias', 'snap': snap, 'alias': alias_name}
    _client.post('/v2/aliases', body=data)


def list_aliases() -> Mapping[str, Iterable[str]]:
    """List all aliases."""
    aliases = _client.get('/v2/aliases')
    assert isinstance(aliases, dict)
    return aliases


# Interfaces
def connect(plug_snap: str, plug_name: str, slot_snap: str, slot_name: str) -> None:
    """Connect a plug to a slot."""
    data = {
        'action': 'connect',
        'plugs': [{'snap': plug_snap, 'plug': plug_name}],
        'slots': [{'snap': slot_snap, 'slot': slot_name}],
    }
    _client.post('/v2/interfaces', body=data)


def disconnect(plug_snap: str, plug_name: str, slot_snap: str, slot_name: str) -> None:
    """Disconnect a plug from a slot."""
    data = {
        'action': 'disconnect',
        'plugs': [{'snap': plug_snap, 'plug': plug_name}],
        'slots': [{'snap': slot_snap, 'slot': slot_name}],
    }
    _client.post('/v2/interfaces', body=data)


# Install/Remove/Refresh
def install(
    name: str, channel: str | None = None, revision: int | None = None, classic: bool = False
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
    _client.post(f'/v2/snaps/{name}', body=data)


def remove(name: str, purge: bool = False) -> None:
    """Remove a snap."""
    data: dict[str, Any] = {'action': 'remove'}
    if purge:
        data['purge'] = True
    _client.post(f'/v2/snaps/{name}', body=data)


def refresh(name: str, channel: str | None = None, revision: int | None = None) -> None:
    """Refresh a snap."""
    if channel is not None and revision is not None:
        raise ValueError('Only one of channel or revision may be specified')
    data = {'action': 'refresh'}
    if channel:
        data['channel'] = channel
    if revision:
        data['revision'] = str(revision)
    _client.post(f'/v2/snaps/{name}', body=data)


# Services
def start(services: Iterable[str]) -> None:
    """Start snap services."""
    data = {'action': 'start', 'names': list(services)}
    _client.post('/v2/apps', body=data)


def stop(services: Iterable[str]) -> None:
    """Stop snap services."""
    data = {'action': 'stop', 'names': list(services)}
    _client.post('/v2/apps', body=data)


def restart(services: Iterable[str]) -> None:
    """Restart snap services."""
    data = {'action': 'restart', 'names': list(services)}
    _client.post('/v2/apps', body=data)


def list_services(snap: str | None = None) -> list[dict[str, Any]]:
    """List snap services."""
    params = {'select': 'service'}
    if snap:
        params['names'] = snap
    services = _client.get('/v2/apps', query=params)
    assert isinstance(services, list)
    return services
