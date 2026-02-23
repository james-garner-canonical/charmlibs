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

from . import _errors, _snap


def ensure(snap: str, channel: str | None = None, revision: int | None = None):
    if channel is not None and revision is not None:
        raise ValueError('Only one of channel or revision may be specified')
    try:
        info = _snap.info(snap)
    except _errors.SnapNotFoundError:
        info = None
    if info is None:
        _snap.install(snap, channel=channel, revision=revision)
    elif info['channel'] != channel and info['revision'] != str(revision):
        _snap.refresh(snap, channel=channel, revision=revision)
