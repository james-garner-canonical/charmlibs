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

import typing
from typing import Any

if typing.TYPE_CHECKING:
    from typing_extensions import Self


class SnapError(Exception):
    def __init__(
        self, message: str, *, kind: str, value: str, code: int | None, status: str | None
    ):
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.value = value
        self.code = code
        self.status = status

    def __repr__(self) -> str:
        return f'{type(self).__name__}({self.message!r}, kind={self.kind!r}, value={self.value!r}, code={self.code!r}, status={self.status!r})'  # noqa: E501


class SnapAPIError(SnapError):
    """Raised when the snapd API returns an error that doesn't match a more specific type."""


class SnapAlreadyInstalledError(SnapError):
    pass


class SnapNotFoundError(SnapError):
    pass


class SnapNeedsClassicError(SnapError):
    pass


class SnapNoUpdatesAvailableError(SnapError):
    pass


class SnapOptionNotFoundError(SnapError):
    pass


class SnapChangeError(SnapError):
    @classmethod
    def _from_change_dict(cls, change_dict: dict[str, Any]) -> Self:
        # e.g. {'id': '54', 'kind': 'alias', 'summary': 'Setup alias "foo" => "s" for snap "firefox"', 'status': 'Error', 'tasks': [{'id': '932', 'kind': 'alias', 'summary': 'Setup manual alias "foo" => "s" for snap "firefox"', 'status': 'Error', 'log': ['2026-02-24T15:42:28+13:00 ERROR cannot enable alias "foo" for "firefox", target application "s" does not exist'], 'progress': {'label': '', 'done': 1, 'total': 1}, 'spawn-time': '2026-02-24T15:42:28.408659003+13:00', 'ready-time': '2026-02-24T15:42:28.439434757+13:00', 'data': {'affected-snaps': ['firefox']}}], 'ready': True, 'err': 'cannot perform the following tasks:\n- Setup manual alias "foo" => "s" for snap "firefox" (cannot enable alias "foo" for "firefox", target application "s" does not exist)', 'spawn-time': '2026-02-24T15:42:28.408698036+13:00', 'ready-time': '2026-02-24T15:42:28.439435568+13:00'}  # noqa: E501
        return cls(
            message=change_dict.get('err', ''),
            kind=change_dict.get('kind', ''),
            value=change_dict.get('id', ''),
            code=None,
            status=change_dict.get('status'),
        )
