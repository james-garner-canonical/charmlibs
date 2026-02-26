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

"""Get, post, and put requests to the snapd REST API.

Synchronous results are returned directly, as basic Python types decoded from JSON.
Async operations are waited on until completion and then the final result is returned.
Errors are converted into :class:`SnapError` exceptions, with specific subclasses where possible.
"""

from __future__ import annotations

import json
import logging
import time
import typing
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import _errors, _socket_handler

if typing.TYPE_CHECKING:
    import http.client
    from collections.abc import Generator

logger = logging.getLogger(__name__)

# we need the powerful snapd socket
# defined in the snap application itself under dirs/dirs.go as SnapdSocket
_SOCKET_PATH = '/run/snapd.socket'


def _request(
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    log: bool = True,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Make a JSON request to the snapd server with the given HTTP method and path.

    If query dict is provided, it is encoded and appended as a query string
    to the URL. If body dict is provided, it is serialied as JSON and used
    as the HTTP body (with Content-Type: "application/json"). The resulting
    body is decoded from JSON.
    """
    if log:
        logger.debug('_request(%r, %r, query=%r, body=%r)', method, path, query, body)
    headers = {'Accept': 'application/json'}
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    response = _request_raw(method, path, query=query, headers=headers, data=data)
    response_bytes = response.read()
    try:
        # /v2/logs returns a stream of JSON objects separated by \n\x1e
        if path == '/v2/logs':
            return [
                json.loads(s)
                for line in response_bytes.split(b'\n\x1e')
                if (s := line.decode().strip())
            ]
        # otherwise we expect a single JSON object
        response_dict: dict[str, Any] = json.loads(response_bytes)
    except json.JSONDecodeError as e:
        raise _errors.SnapAPIError(
            message=f'Invalid JSON in response for path {path!r}: {e}',
            kind='charmlibs-snap',
            value=response_bytes.decode(errors='replace'),
            code=response.status,
            status=response.reason,
        ) from None
    if not isinstance(response_dict, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise _errors.SnapAPIError(
            message=f"Unexpected response type {type(response_dict).__name__!r} for path {path!r}, expected a 'dict'",  # noqa: E501
            kind='charmlibs-snap',
            value=str(response_dict),
            code=response.status,
            status=response.reason,
        )
    try:
        match response_dict['type']:
            case 'error':
                error_type = _error_type_from_result(response_dict['result'])
                raise _make_error(error_type, response_dict)
            case 'async':
                return _wait_for_change(change_id=response_dict['change'])
            case _:
                return response_dict['result']
    except KeyError as e:
        raise _errors.SnapAPIError(
            message=f'Missing expected key {e} in response for path {path!r}',
            kind='charmlibs-snap',
            value=str(response_dict),
            code=response.status,
            status=response.reason,
        ) from None


def _request_raw(
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    data: bytes | Generator[bytes, Any, Any] | None = None,
) -> http.client.HTTPResponse:
    """Make a request to the snapd server; return the raw HTTPResponse object."""
    assert path.startswith('/')
    url = f'http://localhost{path}'
    if query:
        url = f'{url}?{urllib.parse.urlencode(query, doseq=True)}'
    if headers is None:
        headers = {}
    opener = urllib.request.OpenerDirector()
    opener.add_handler(_socket_handler.UnixSocketHandler(_SOCKET_PATH))
    opener.add_handler(urllib.request.HTTPRedirectHandler())
    # We need to handle HTTP errors ourselves, since the response body contains meaningful info.
    # opener.add_handler(urllib.request.HTTPDefaultErrorHandler())
    # opener.add_handler(urllib.request.HTTPErrorProcessor())
    request = urllib.request.Request(url, method=method, data=data, headers=dict(headers))  # noqa: S310
    try:
        return opener.open(request, timeout=30.0)
    except urllib.error.URLError as e:
        if e.args and isinstance(e.args[0], FileNotFoundError):
            msg = f'Could not connect to server: socket not found at {_SOCKET_PATH!r}'
            raise ConnectionError(msg) from None
        raise ConnectionError(e.reason) from e


def _wait_for_change(change_id: str) -> dict[str, Any]:
    """Wait for an async change to complete.

    The poll time is 100 milliseconds, the same as in snap clients.
    """
    logger.debug('_wait_for_change(%r)', change_id)
    deadline = time.time() + 600  # 10 minute timeout
    while True:
        if time.time() > deadline:
            raise TimeoutError(f'timeout waiting for snap change: {change_id}')
        response = _request('GET', f'/v2/changes/{change_id}', log=False)
        if not isinstance(response, dict):
            raise _errors.SnapAPIError(
                message=f'Unexpected response type {type(response).__name__} while waiting for change {change_id}',  # noqa: E501
                kind='charmlibs-snap',
                value=str(response),
                code=None,
                status=None,
            )
        match response.get('status'):
            case 'Do' | 'Doing':
                time.sleep(0.1)
                continue
            case 'Done':
                return response.get('data', {})
            case 'Wait':
                logger.warning("snap change %s succeeded with status 'Wait'", change_id)
                return response.get('data', {})
            case _:
                # e.g.
                # {'id': '54',
                # 'kind': 'alias',
                # 'summary': 'Setup alias "foo" => "s" for snap "firefox"',
                # 'status': 'Error',
                # 'tasks': [{'id': '932',
                #   'kind': 'alias',
                #   'summary': 'Setup manual alias "foo" => "s" for snap "firefox"',
                #   'status': 'Error',
                #   'log': ['2026-02-24T15:42:28+13:00 ERROR cannot enable alias "foo" for "firefox", target application "s" does not exist'],  # noqa: E501
                #   'progress': {'label': '', 'done': 1, 'total': 1},
                #   'spawn-time': '2026-02-24T15:42:28.408659003+13:00',
                #   'ready-time': '2026-02-24T15:42:28.439434757+13:00',
                #   'data': {'affected-snaps': ['firefox']}}],
                # 'ready': True,
                # 'err': 'cannot perform the following tasks:\n- Setup manual alias "foo" => "s" for snap "firefox" (cannot enable alias "foo" for "firefox", target application "s" does not exist)',  # noqa: E501
                # 'spawn-time': '2026-02-24T15:42:28.408698036+13:00',
                # 'ready-time': '2026-02-24T15:42:28.439435568+13:00'}
                raise _errors.SnapChangeError(
                    message=response.get('err', ''),
                    kind=response.get('kind', ''),
                    value=response.get('id', ''),
                    code=None,
                    status=response.get('status'),
                )


def _error_type_from_result(result: dict[str, Any]) -> type[_errors.SnapError]:
    match result.get('kind'):
        case 'snap-already-installed':
            return _errors.SnapAlreadyInstalledError
        case 'option-not-found':
            return _errors.SnapOptionNotFoundError
        case 'snap-needs-classic':
            return _errors.SnapNeedsClassicError
        case 'snap-not-found' | 'snap-not-installed':
            return _errors.SnapNotFoundError
        case 'snap-no-update-available':
            return _errors.SnapNoUpdatesAvailableError
        case _:
            return _errors.SnapError


def _make_error(
    error_type: type[_errors.SnapError], response: dict[str, Any]
) -> _errors.SnapError:
    result = response.get('result', {})
    return error_type(
        message=result.get('message', ''),
        kind=result.get('kind', ''),
        value=result.get('value', ''),
        code=response.get('status-code'),
        status=response.get('status'),
    )


def get(path: str, query: dict[str, Any] | None = None):
    """GET request, returns result directly."""
    return _request('GET', path, query=query)


def post(path: str, body: dict[str, Any] | None = None):
    """POST request, returns change ID for async operations."""
    return _request('POST', path, body=body)


def put(path: str, body: dict[str, Any] | None = None):
    """PUT request, returns result directly."""
    return _request('PUT', path, body=body)
