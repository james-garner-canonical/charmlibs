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

"""High level helper functions that build on top of the basic snap operations."""

import logging

from . import _snapd

logger = logging.getLogger(__name__)


def ensure(
    snap: str, *, channel: str | None = None, revision: int | None = None, classic: bool = False
) -> bool:
    """Ensure that the specified snap is installed with the specified channel or revision.

    If neither is specified, ensure that it is installed at all, or install latest/stable if not.

    Returns:
        True if any action was taken (install or refresh), False otherwise.

    Raises:
        ValueError: if both channel and revision are specified.
        SnapError: (or a subtype) if the snap could not be installed or refreshed as requested.
    """
    if channel is not None and revision is not None:
        raise ValueError('Only one of channel or revision may be specified')
    logger.debug('ensure:Querying info for snap %r', snap)
    # Install if the snap is not already installed.
    info = _snapd.info(snap, missing_ok=True)
    if info is None:
        logger.debug('ensure:Snap %r is not installed: installing ...', snap)
        _snapd.install(snap, channel=channel, revision=revision, classic=classic)
        return True
    # Refresh is the snap installed with a different channel or revision than requested.
    different_channel = channel is not None and (
        _normalize_channel(info.channel) != _normalize_channel(channel)
    )
    different_revision = revision is not None and info.revision != revision
    if different_channel or different_revision:
        msg = 'ensure:Snap %r is installed with channel=%r and revision=%d but requested (channel=%r, revision=%r): refreshing ...'  # noqa: E501
        logger.debug(msg, snap, info.channel, info.revision, channel, revision)
        _snapd.refresh(snap, channel=channel, revision=revision)
        return True
    # Return False if no operations were performed.
    msg = 'ensure:Snap %r is already installed with classic=%s, channel=%r and revision=%d'
    logger.debug(msg, snap, info.classic, info.channel, info.revision)
    return False


def _normalize_channel(channel: str) -> str:
    """Normalize a snap channel string to the form "track/risk".

    Channels may be specified as track or risk only, or as "track/risk" or "track/risk/branch".
    Snapd uses default values internally, but will record the *requested* value in the snap info.
    This function normalizes channels with no "/" to the form "track/risk" for easier comparison.
    """
    if '/' not in channel:
        if channel not in ('edge', 'beta', 'candidate', 'stable'):
            # track only, append default risk
            return f'{channel}/stable'
        # risk only, prepend default track
        return f'latest/{channel}'
    return channel
