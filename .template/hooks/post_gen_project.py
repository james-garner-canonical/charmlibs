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

"""Run by cookicutter after project generation to turn resolved symlinks back into symlinks."""

import json
import os
import pathlib
import sys
import warnings

TEMPFILE_VAR = 'TEMPFILE'
if TEMPFILE_VAR not in os.environ:
    warnings.warn(
        f'{TEMPFILE_VAR} not defined in environment! Make sure you run `cookiecutter` via `just`.',
        stacklevel=2,
    )
    sys.exit()
tempfile_path = pathlib.Path(os.environ[TEMPFILE_VAR])
if not tempfile_path.is_file():
    warnings.warn(f'{TEMPFILE_VAR}={tempfile_path} is not a file!', stacklevel=2)
    sys.exit()
di = json.loads(tempfile_path.read_text())
for path, target in di.items():
    path = pathlib.Path(path)
    path.unlink()
    path.symlink_to(target)
