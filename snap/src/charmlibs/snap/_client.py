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

import http.client
import json
import logging
import socket
import sys
import time
import typing
import urllib.parse
import urllib.request
from typing import Any

from . import _errors

if typing.TYPE_CHECKING:
    from collections.abc import Generator

logger = logging.getLogger(__name__)

# we need the powerful snapd socket
# defined in the snap application itself under dirs/dirs.go as SnapdSocket
_SOCKET_PATH = '/run/snapd.socket'


class _NotProvided:
    pass


_NOT_PROVIDED = _NotProvided()


class _UnixSocketConnection(http.client.HTTPConnection):
    """Implementation of HTTPConnection that connects to a named Unix socket."""

    def __init__(self, host: str, socket_path: str, timeout: _NotProvided | float = _NOT_PROVIDED):
        if isinstance(timeout, _NotProvided):
            super().__init__(host)
        else:
            super().__init__(host, timeout=timeout)
        self._socket_path = socket_path

    def connect(self):
        """Override connect to use Unix socket (instead of TCP socket)."""
        if not hasattr(socket, 'AF_UNIX'):
            raise NotImplementedError(f'Unix sockets not supported on {sys.platform}')
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self._socket_path)
        if not isinstance(self.timeout, _NotProvided):
            self.sock.settimeout(self.timeout)


class _UnixSocketHandler(urllib.request.AbstractHTTPHandler):
    """Implementation of HTTPHandler that uses a named Unix socket."""

    def __init__(self, socket_path: str):
        super().__init__()
        self._socket_path = socket_path

    def http_open(self, req: urllib.request.Request):
        """Override http_open to use a Unix socket connection (instead of TCP)."""
        return self.do_open(
            _UnixSocketConnection,  # type:ignore
            req,
            socket_path=self._socket_path,
        )


def _request(
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    log: bool = True,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Make a JSON request to the server with the given HTTP method and path.

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
    response = _request_raw(method, path, query, headers, data)
    response_bytes = response.read()
    if path == '/v2/logs':
        return [
            json.loads(s)
            for line in response_bytes.split(b'\n\x1e')
            if (s := line.decode().strip())
        ]
    response_dict = json.loads(response_bytes)
    _raise_if_error(response_dict)
    if response_dict['type'] == 'async':
        result = _wait_for_change(change_id=response_dict['change'])
    else:
        result = response_dict['result']
    return result


def _request_raw(
    method: str,
    path: str,
    query: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    data: bytes | Generator[bytes, Any, Any] | None = None,
) -> http.client.HTTPResponse:
    """Make a request to the Pebble server; return the raw HTTPResponse object."""
    assert path.startswith('/')
    url = f'http://localhost{path}'
    if query:
        url = f'{url}?{urllib.parse.urlencode(query, doseq=True)}'
    if headers is None:
        headers = {}
    opener = urllib.request.OpenerDirector()
    opener.add_handler(_UnixSocketHandler(_SOCKET_PATH))
    # opener.add_handler(urllib.request.HTTPDefaultErrorHandler())
    # opener.add_handler(urllib.request.HTTPRedirectHandler())
    # opener.add_handler(urllib.request.HTTPErrorProcessor())
    request = urllib.request.Request(url, method=method, data=data, headers=dict(headers))  # noqa: S310
    reply = opener.open(request, timeout=30.0)
    # try:
    #     reply = opener.open(request, timeout=30.0)
    # except urllib.error.HTTPError as e:
    #     try:
    #         response: dict[str, Any] = json.loads(e.read())
    #     except (OSError, ValueError, KeyError) as e2:
    #         # Will only happen on read error or if we receive invalid JSON.
    #         response = {'message': f'{type(e2).__name__} - {e2}'}
    #     response['status-code'] = e.code
    #     response['status'] = e.reason
    #     raise _errors.SnapAPIError._from_response(response) from None
    # except urllib.error.URLError as e:
    #     if e.args and isinstance(e.args[0], FileNotFoundError):
    #         msg = f'Could not connect to server: socket not found at {_SOCKET_PATH!r}'
    #         raise ConnectionError(msg) from None
    #     raise ConnectionError(e.reason) from e
    return reply


def _wait_for_change(change_id: str, timeout: float = 300) -> dict[str, Any]:
    """Wait for an async change to complete.

    The poll time is 100 milliseconds, the same as in snap clients.
    """
    logger.debug('_wait_for_change(%r, timeout=%r)', change_id, timeout)
    deadline = time.time() + timeout
    while True:
        if time.time() > deadline:
            raise TimeoutError(f'timeout waiting for snap change {change_id}')
        response = _request('GET', f'/v2/changes/{change_id}', log=False)
        assert isinstance(response, dict)
        match response['status']:
            case 'Do' | 'Doing':
                time.sleep(0.1)
                continue
            case 'Done':
                return response.get('data', {})
            case 'Wait':
                logger.warning("snap change %s succeeded with status 'Wait'", change_id)
                return response.get('data', {})
            case _:
                raise _errors.SnapChangeError._from_change_dict(response)


def _raise_if_error(response: dict[str, Any]) -> None:
    if response['type'] != 'error':
        return
    result = response['result']
    match result.get('kind'):
        case 'snap-already-installed':
            raise _errors.SnapAlreadyInstalledError._from_response(response)
        case 'option-not-found':
            raise _errors.SnapOptionNotFoundError._from_response(response)
        case 'snap-needs-classic':
            raise _errors.SnapNeedsClassicError._from_response(response)
        case 'snap-not-found':
            raise _errors.SnapNotFoundError._from_response(response)
        case 'snap-not-installed':
            raise _errors.SnapNotInstalledError._from_response(response)
        case _:
            raise _errors.SnapAPIError._from_response(response)


def get(path: str, query: dict[str, Any] | None = None):
    """GET request, returns result directly."""
    return _request('GET', path, query=query)


def post(path: str, body: dict[str, Any] | None = None):
    """POST request, returns change ID for async operations."""
    return _request('POST', path, body=body)


def put(path: str, body: dict[str, Any] | None = None):
    """PUT request, returns result directly."""
    return _request('PUT', path, body=body)
