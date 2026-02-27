# Copyright 2025 Canonical Ltd.
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

"""Opinionated library for performing snap operations, targeted at use in charm code.

Use :func:`ensure` to ensure that a snap is installed with the desired channel/revision.

Manually manage snap installation with :func:`install`, :func:`refresh`, and :func:`remove`.
Use :func:`info` to query the current state of an installed snap.

Also manage:

- Automatic refreshes with :func:`hold` and :func:`unhold`.
- Services with :func:`start`, :func:`stop`, and :func:`restart`.
- Config with :func:`config_get`, :func:`config_set`, and :func:`config_unset`.
- Connections between snaps with :func:`connect` and :func:`disconnect`.
- Application aliases with :func:`alias` and :func:`unalias`.

Exceptions
----------

All functions will raise a :class:`SnapError` subclass if the snapd API returns an error response.

Functions will raise specific subclasses where possible to allow callers to handle logical errors.
Check the documentation for each function for details on which exceptions it may raise.

The :class:`SnapAPIError` subclass will be raised if the snapd API returns a malformed response.
Callers will not be able to resolve this error directly, but may want to catch it for logging,
or to trigger retries if the error may be transient. If retries are not successful,
user intervention may be required.

A :class:`ConnectionError` indicates a failure to connect to the snapd socket at all. In this case
something is badly wrong with the system, and user intervention is almost certainly required.
"""

from ._errors import (
    SnapAlreadyInstalledError,
    SnapAPIError,
    SnapChangeError,
    SnapError,
    SnapNeedsClassicError,
    SnapNotFoundError,
    SnapNoUpdatesAvailableError,
    SnapOptionNotFoundError,
)
from ._functions import (
    ensure,
)
from ._snapd import (
    SnapInfo,
    alias,
    config_get,
    config_set,
    config_unset,
    connect,
    disconnect,
    hold,
    info,
    install,
    refresh,
    remove,
    restart,
    start,
    stop,
    unalias,
    unhold,
)
from ._version import __version__ as __version__

__all__ = [
    'SnapAPIError',
    'SnapAlreadyInstalledError',
    'SnapChangeError',
    'SnapError',
    'SnapInfo',
    'SnapNeedsClassicError',
    'SnapNoUpdatesAvailableError',
    'SnapNotFoundError',
    'SnapOptionNotFoundError',
    'alias',
    'config_get',
    'config_set',
    'config_unset',
    'connect',
    'disconnect',
    'ensure',
    'hold',
    'info',
    'install',
    'refresh',
    'remove',
    'restart',
    'start',
    'stop',
    'unalias',
    'unhold',
]
