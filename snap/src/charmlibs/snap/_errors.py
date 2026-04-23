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

"""Logical error types for responses from the snapd API."""

from __future__ import annotations


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
    """Raised manually when the snapd API returns a response we don't understand.

    Callers will not be able to resolve this error directly, but may want to catch it for logging,
    or to trigger retries if the error may be transient. If retries are not successful,
    user intervention may be required.
    """


class SnapAlreadyInstalledError(SnapError):
    pass


class SnapNotFoundError(SnapError):
    pass


class SnapNeedsClassicError(SnapError):
    pass


class _SnapNoUpdatesAvailableError(SnapError):  # pyright: ignore[reportUnusedClass]
    """Raised via the API when a refresh is attempted but no updates are available.

    This class is private because the public refresh function suppresses this error,
    following the snap CLI's lead.
    """


class SnapOptionNotFoundError(SnapError):
    pass


class SnapChangeError(SnapError):
    pass
