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

"""Magic numbers."""

import stat

DEFAULT_MKDIR_MODE = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
"""Pebble's default of 0o755 (493) 'drwxr-xr-x'.

Pathlib's default value is 0o777 (511) 'drwxrwxrwx'.
"""
assert DEFAULT_MKDIR_MODE == 0o755

DEFAULT_WRITE_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
"""Pebble's default of 0o644 (420) '-rw-r--r--'.

Pathlib's default value is 0o666 (438) '-rw-rw-rw-'.
"""
assert DEFAULT_WRITE_MODE == 0o644
