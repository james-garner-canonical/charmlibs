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

import logging

from . import _errors, _snap, _utils

logger = logging.getLogger(__name__)


def ensure(
    snap: str, *, channel: str | None = None, revision: int | None = None, classic: bool = False
) -> None:
    if channel is not None and revision is not None:
        raise ValueError('Only one of channel or revision may be specified')
    try:
        logger.debug('ensure:Querying info for snap %r', snap)
        info = _snap.info(snap)
    except _errors.SnapNotFoundError:
        info = None
    if info is None:
        logger.debug('ensure:Snap %r is not installed: installing ...', snap)
        _snap.install(snap, channel=channel, revision=revision, classic=classic)
    elif info.classic != classic:
        msg = f'Snap {snap!r} is installed with classic={info.classic} but requested classic={classic}; this is most likely an error'  # noqa: E501
        logger.info('ensure:%s -> aborting', msg)
        raise ValueError(msg)
    elif (
        channel is not None
        and _utils.normalize_channel(info.channel) != _utils.normalize_channel(channel)
    ) or (revision is not None and info.revision != revision):
        msg = 'ensure:Snap %r is installed with channel=%r and revision=%d but requested (channel=%r, revision=%r): refreshing ...'  # noqa: E501
        logger.debug(msg, snap, info.channel, info.revision, channel, revision)
        _snap.refresh(snap, channel=channel, revision=revision)
    else:
        msg = 'ensure:Snap %r is already installed with classic=%s, channel=%r and revision=%d'
        logger.debug(msg, snap, info.classic, info.channel, info.revision)
