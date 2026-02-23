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

import time
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import quote

import requests_unixsocket

from . import _errors

_SOCKET_PATH = '/run/snapd.socket'


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make a request to the snapd API."""
    url = f'http+unix://{quote(_SOCKET_PATH, safe="")}{path}'
    kwargs = {}
    if params:
        kwargs['params'] = params
    if body:
        kwargs['json'] = body
    response = requests_unixsocket.Session().request(method, url, **kwargs)
    result = response.json()
    _raise(response.status_code, result.get('result', {}))
    response.raise_for_status()
    return result


def _raise(status_code: int, result: dict[str, str]) -> None:
    if status_code == 400:
        kind = result.get('kind')
        if kind == 'snap-already-installed':
            raise _errors.SnapAlreadyInstalledError(result.get('value'))
        if kind == 'option-not-found':
            raise KeyError(result.get('value'))
    elif status_code == 404:
        kind = result.get('kind')
        if kind == 'snap-not-found':
            raise _errors.SnapNotFoundError(result.get('value'))


def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    """GET request, returns result directly."""
    result = _request('GET', path, params=params)
    return result['result']


def _post(path: str, body: dict[str, Any] | None = None) -> str:
    """POST request, returns change ID for async operations."""
    result = _request('POST', path, body=body)
    return result['change']


def _put(path: str, body: dict[str, Any] | None = None) -> Any:
    """PUT request, returns result directly."""
    result = _request('PUT', path, body=body)
    return result['result']


def _wait(change_id: str, timeout: int = 30) -> dict:
    """Wait for an async change to complete."""
    start = time.time()
    while time.time() - start < timeout:
        change = _get(f'/v2/changes/{change_id}')
        if change['status'] in ('Done', 'Error', 'Aborted'):
            if change['status'] == 'Error':
                raise RuntimeError(f'Change {change_id} failed: {change.get("err")}')
            return change
        time.sleep(0.5)
    raise TimeoutError(f'Change {change_id} did not complete in {timeout}s')


# Info/List
def info(name: str) -> dict:
    """Get information about a snap."""
    return _get(f'/v2/snaps/{name}')


def list_snaps() -> list[dict]:
    """List all installed snaps."""
    return _get('/v2/snaps')


# Configuration
def get(name: str, keys: Iterable[str] | None = None) -> dict[str, Any]:
    """Get snap configuration."""
    params = {'keys': ','.join(keys)} if keys else None
    return _get(f'/v2/snaps/{name}/conf', params=params)


def set(name: str, config: Mapping[str, Any]):  # noqa: A001
    """Set snap configuration. Waits for completion."""
    change_id = _put(f'/v2/snaps/{name}/conf', body=config)
    if change_id is not None:
        _wait(change_id)


def unset(name: str, keys: Iterable[str]) -> dict[str, Any]:
    """Unset snap configuration keys. Waits for completion."""
    config = dict.fromkeys(keys)
    change_id = _put(f'/v2/snaps/{name}/conf', body=config)
    return _wait(change_id) if change_id else {}


# Aliases
def alias(snap: str, app: str, alias_name: str) -> dict:
    """Create an alias for a snap app. Waits for completion."""
    data = {'action': 'alias', 'snap': snap, 'app': app, 'alias': alias_name}
    change_id = _post('/v2/aliases', body=data)
    return _wait(change_id)


def unalias(snap: str, alias_name: str) -> dict:
    """Remove an alias. Waits for completion."""
    data = {'action': 'unalias', 'snap': snap, 'alias': alias_name}
    change_id = _post('/v2/aliases', body=data)
    return _wait(change_id)


def list_aliases() -> dict:
    """List all aliases."""
    return _get('/v2/aliases')


# Interfaces
def connect(plug_snap: str, plug_name: str, slot_snap: str, slot_name: str) -> dict:
    """Connect a plug to a slot. Waits for completion."""
    data = {
        'action': 'connect',
        'plugs': [{'snap': plug_snap, 'plug': plug_name}],
        'slots': [{'snap': slot_snap, 'slot': slot_name}],
    }
    change_id = _post('/v2/interfaces', body=data)
    return _wait(change_id)


def disconnect(plug_snap: str, plug_name: str, slot_snap: str, slot_name: str) -> dict:
    """Disconnect a plug from a slot. Waits for completion."""
    data = {
        'action': 'disconnect',
        'plugs': [{'snap': plug_snap, 'plug': plug_name}],
        'slots': [{'snap': slot_snap, 'slot': slot_name}],
    }
    change_id = _post('/v2/interfaces', body=data)
    return _wait(change_id)


# Install/Remove/Refresh
def install(name: str, channel: str | None = None, revision: int | None = None, classic: bool = False) -> dict:
    """Install a snap. Waits for completion."""
    if channel is not None and revision is not None:
        raise ValueError('Only one of channel or revision may be specified')
    data = {'action': 'install'}
    if channel:
        data['channel'] = channel
    if revision:
        data['revision'] = str(revision)
    if classic:
        data['classic'] = True
    change_id = _post(f'/v2/snaps/{name}', body=data)
    return _wait(change_id)


def remove(name: str, purge: bool = False) -> dict:
    """Remove a snap. Waits for completion."""
    data = {'action': 'remove'}
    if purge:
        data['purge'] = True
    change_id = _post(f'/v2/snaps/{name}', body=data)
    return _wait(change_id)


def refresh(name: str, channel: str | None = None, revision: int | None = None) -> dict:
    """Refresh a snap. Waits for completion."""
    if channel is not None and revision is not None:
        raise ValueError('Only one of channel or revision may be specified')
    data = {'action': 'refresh'}
    if channel:
        data['channel'] = channel
    if revision:
        data['revision'] = str(revision)
    change_id = _post(f'/v2/snaps/{name}', body=data)
    return _wait(change_id)


# Services
def start(services: list[str]) -> dict:
    """Start snap services. Waits for completion."""
    data = {'action': 'start', 'names': services}
    change_id = _post('/v2/apps', body=data)
    return _wait(change_id)


def stop(services: list[str]) -> dict:
    """Stop snap services. Waits for completion."""
    data = {'action': 'stop', 'names': services}
    change_id = _post('/v2/apps', body=data)
    return _wait(change_id)


def restart(services: list[str]) -> dict:
    """Restart snap services. Waits for completion."""
    data = {'action': 'restart', 'names': services}
    change_id = _post('/v2/apps', body=data)
    return _wait(change_id)


def list_services(snap: str | None = None) -> list[dict]:
    """List snap services."""
    params = {'select': 'service'}
    if snap:
        params['names'] = snap
    return _get('/v2/apps', params=params)
