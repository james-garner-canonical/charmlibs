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


def normalize_channel(channel: str) -> str:
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
