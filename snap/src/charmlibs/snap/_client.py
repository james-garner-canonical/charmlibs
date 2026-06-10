# Copyright 2026 Canonical Ltd.
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
Errors are converted into :class:`Error` exceptions, with specific subclasses where possible.
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

from . import _client_sockets, _errors

if typing.TYPE_CHECKING:
    import http.client
    from collections.abc import Generator

logger = logging.getLogger(__name__)

# we need the powerful snapd socket
# defined in the snap application itself under dirs/dirs.go as SnapdSocket
_SOCKET_PATH = '/run/snapd.socket'
# TODO: a user facing way to set timeout? e.g. charmlibs.snap.set_timeouts(request=60, change=1800)
_REQUEST_TIMEOUT = 30
_CHANGE_TIMEOUT = 600  # 10 minutes in seconds
_POLL_INTERVAL = 0.1  # 100 milliseconds, the same as in snap clients


def get(path: str, query: dict[str, Any] | None = None, *, timeout: float | None = None):
    """GET request to snapd REST API."""
    return _resolve(_request('GET', path, query=query), timeout=timeout)


def post(path: str, body: dict[str, Any] | None = None, *, timeout: float | None = None):
    """POST request to snapd REST API."""
    return _resolve(_request('POST', path, body=body), timeout=timeout)


def put(path: str, body: dict[str, Any] | None = None, *, timeout: float | None = None):
    """PUT request to snapd REST API."""
    return _resolve(_request('PUT', path, body=body), timeout=timeout)


def _resolve(
    result: dict[str, Any] | list[dict[str, Any]] | _Change,
    *,
    timeout: float | None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Wait for an async change to complete, or return a synchronous result unchanged.

    The timeout only applies to async changes. If ``None``, :data:`_CHANGE_TIMEOUT` is used.
    """
    if isinstance(result, _Change):
        return result.wait(timeout=_CHANGE_TIMEOUT if timeout is None else timeout)
    return result


def _request(
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    log: bool = True,
) -> dict[str, Any] | list[dict[str, Any]] | _Change:
    """Make a JSON request to the snapd server with the given HTTP method and path.

    If query dict is provided, it is encoded and appended as a query string
    to the URL. If body dict is provided, it is serialied as JSON and used
    as the HTTP body (with Content-Type: "application/json"). The resulting
    body is decoded from JSON.

    This performs a single round-trip and does not block: an async response is
    returned as a :class:`_Change`, which the caller can :meth:`_Change.wait` on.
    """
    if log:
        logger.debug('_request(%r, %r, query=%r, body=%r)', method, path, query, body)
    headers = {'Accept': 'application/json'}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    else:
        data = None
    response = _request_raw(method, path, query=query, headers=headers, data=data)
    response_bytes = response.read()
    try:
        if path == '/v2/logs':
            # /v2/logs returns a stream of JSON objects separated by \n\x1e
            logs = [
                json.loads(s)
                for line in response_bytes.split(b'\n\x1e')
                if (s := line.decode().strip())
            ]
            if len(logs) == 1 and logs[0].get('type') == 'error':
                # Error responses are a single JSON object, which we wrapped in a list above.
                raise _make_error(logs[0])
            return logs
        # otherwise we expect a single JSON object
        response_dict: dict[str, Any] = json.loads(response_bytes)
    except json.JSONDecodeError as e:
        raise _errors.BadResponseError(
            message=f'Invalid JSON in response for path {path!r}: {e}',
            kind='charmlibs-snap',
            value=response_bytes.decode(errors='replace'),
            status_code=response.status,
            status=response.reason,
        ) from None
    if not isinstance(response_dict, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise _errors.BadResponseError(
            message=f"Unexpected response type {type(response_dict).__name__!r} for path {path!r}, expected a 'dict'",  # noqa: E501
            kind='charmlibs-snap',
            value=str(response_dict),
            status_code=response.status,
            status=response.reason,
        )
    try:
        match response_dict['type']:
            case 'error':
                raise _make_error(response_dict)
            case 'async':
                return _Change(response_dict['change'])
            case _:
                return response_dict['result']
    except KeyError as e:
        raise _errors.BadResponseError(
            message=f'Missing expected key {e} in response for path {path!r}',
            kind='charmlibs-snap',
            value=str(response_dict),
            status_code=response.status,
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
    request = urllib.request.Request(
        f'http://localhost{path}'
        + (f'?{urllib.parse.urlencode(query, doseq=True)}' if query else ''),
        method=method,
        headers=headers or {},
        data=data,
    )
    opener = urllib.request.OpenerDirector()
    opener.add_handler(_client_sockets.UnixSocketHandler(_SOCKET_PATH))
    opener.add_handler(urllib.request.HTTPRedirectHandler())
    # We need to handle HTTP errors ourselves, since the response body contains meaningful info.
    # opener.add_handler(urllib.request.HTTPDefaultErrorHandler())
    # opener.add_handler(urllib.request.HTTPErrorProcessor())
    try:
        return opener.open(request, timeout=_REQUEST_TIMEOUT)
    except TimeoutError:
        raise _errors.TimeoutError(
            f'Request to snapd timed out after {_REQUEST_TIMEOUT}s: {method} {path}',
            kind='charmlibs-snap-request-timeout',
            value='',
        ) from None
    except urllib.error.URLError as e:
        if e.args and isinstance(e.args[0], FileNotFoundError):
            raise _errors.ConnectionError(
                f'Could not connect to snapd: socket not found at {_SOCKET_PATH!r}',
                kind='charmlibs-snap-socket-not-found',
                value='',
            ) from None
        raise _errors.ConnectionError(
            str(e.reason),
            kind='charmlibs-snap-connection-error',
            value='',
        ) from e


class _Change:
    """An in-progress or completed async snapd change.

    Encapsulates a single change's id and last-known state, the logic to fetch its
    current status (:meth:`refresh`), and the polling loop to wait for completion
    (:meth:`wait`).
    """

    def __init__(self, change_id: str):
        self.change_id = change_id
        self.status: str | None = None
        self.data: dict[str, Any] = {}
        self.err: str = ''

    def refresh(self) -> None:
        """Fetch the current status of the change from snapd (a single round-trip)."""
        response = _request('GET', f'/v2/changes/{self.change_id}', log=False)
        if not isinstance(response, dict):
            raise _errors.BadResponseError(
                message=f'Unexpected response type {type(response).__name__} while waiting for change {self.change_id}',  # noqa: E501
                kind='charmlibs-snap',
                value=str(response),
            )
        self.status = response.get('status')
        self.data = response.get('data', {})
        self.err = response.get('err', '')

    def wait(self, timeout: float) -> dict[str, Any]:
        """Poll until the change completes, then return its data.

        The poll interval is 100 milliseconds, the same as in snap clients.

        Raises:
            ChangeError: If the change finishes in an error or unexpected status.
            TimeoutError: If the change does not complete within ``timeout`` seconds.
                Note that snapd continues running the change; the client has only
                stopped waiting for it.
        """
        logger.debug('_Change.wait(%r, timeout=%r)', self.change_id, timeout)
        deadline = time.monotonic() + timeout
        while True:
            if time.monotonic() > deadline:
                raise _errors.TimeoutError(
                    f'Timed out after {timeout}s waiting for snap change {self.change_id}',
                    kind='charmlibs-snap-change-timeout',
                    value=self.change_id,
                )
            self.refresh()
            match self.status:
                case 'Do' | 'Doing' | 'Undo' | 'Undoing':
                    time.sleep(_POLL_INTERVAL)
                    continue
                case 'Done':
                    return self.data
                case 'Wait':
                    logger.warning("snap change %s succeeded with status 'Wait'", self.change_id)
                    return self.data
                case 'Error':
                    raise _errors.ChangeError(
                        message=self.err,
                        kind='charmlibs-snap-change-error',
                        value=self.change_id,
                        status=self.status,
                    )
                case _:
                    raise _errors.ChangeError(
                        message=f'Unexpected status {self.status!r} for snap change {self.change_id}',  # noqa: E501
                        kind='charmlibs-snap-change-unknown',
                        value=self.change_id,
                        status=self.status,
                    )


def _make_error(response: dict[str, Any]) -> _errors.APIError:
    result = response.get('result', {})
    kind = result.get('kind', '')
    error_type = _errors._error_type_from_result_kind(kind)
    return error_type(
        result.get('message', ''),
        kind=kind,
        value=result.get('value', ''),
        status_code=response.get('status-code'),
        status=response.get('status'),
    )
