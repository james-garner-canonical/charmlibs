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

"""Snap log operations, implemented as calls to the snapd REST API's /v2/logs endpoint."""

from __future__ import annotations

import dataclasses
import datetime
import logging
import sys
from typing import Any

from . import _client

logger = logging.getLogger(__name__)


# /v2/logs


@dataclasses.dataclass
class LogEntry:
    timestamp: datetime.datetime
    message: str
    sid: str
    pid: int


def logs(*snaps: str, num_lines: int = 10) -> list[LogEntry]:
    query: dict[str, Any] = {'n': num_lines}
    if snaps:
        query['names'] = ','.join(snaps)
    result = _client.get('/v2/logs', query=query)
    # A log entry looks like:
    # {'timestamp': '2026-02-27T03:01:19.488008Z',
    #  'message': 'QMP: {"timestamp": {"seconds": 1772161279, "microseconds": 487649}, "event": "RTC_CHANGE", "data": {"offset": 0, "qom-path": "/machine/unattached/device[7]/rtc"}}',  # noqa: E501
    #  'sid': 'multipassd',
    #  'pid': '135506'}]
    # The snap CLI presents this as:
    # 2026-02-27T16:01:19+13:00 multipassd[135506]: QMP: {"timestamp": {"seconds": 1772161279, "microseconds": 487649}, "event": "RTC_CHANGE", "data": {"offset": 0, "qom-path": "/machine/unattached/device[7]/rtc"}}  # noqa: E501
    # We preserve the separate fields by parsing to a dataclass.
    assert isinstance(result, list)
    log_entries: list[LogEntry] = []
    for obj in result:
        try:
            log_entry = LogEntry(
                timestamp=_parse_timestamp(obj['timestamp']),
                message=obj['message'],
                sid=obj['sid'],
                pid=int(obj['pid']),
            )
            log_entries.append(log_entry)
        except (KeyError, TypeError, ValueError) as e:  # noqa: PERF203
            logger.warning('Skipping log entry with unexpected format: %r (error: %r)', obj, e)
    return log_entries


def _parse_timestamp(timestamp: str) -> datetime.datetime:
    if sys.version_info >= (3, 11):
        return datetime.datetime.fromisoformat(timestamp)
    # Python 3.10 can't parse the fractional seconds with fromisoformat.
    # We parse the format manually here for Ubuntu 22.04 based charms.
    #
    # The snapd version that comes with Ubuntu 22.04 emits Z-suffixed timestamps, e.g.
    # 2026-02-27T03:01:19.488008Z
    #
    # Note: Newer snapd versions emit RFC3339 timestamps with timezone offsets, but we don't
    # need to handle them here since they're covered by fromisoformat in Python 3.11+.
    dt, ms = timestamp.removesuffix('Z').split('.')
    base = datetime.datetime.fromisoformat(dt).replace(tzinfo=datetime.timezone.utc)
    # datetime.timedelta only supports microsecond precision (first 6 digits of fractional seconds).
    # Snapd timestamps may have higher precision (truncated) or fewer than 6 digits (right-padded
    # with zeros). E.g. '.13454' is 134540 µs, not 13454 µs. This matches fromisoformat in 3.11+.
    microseconds = datetime.timedelta(microseconds=int(ms[:6].ljust(6, '0')))
    return base + microseconds
