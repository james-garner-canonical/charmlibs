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

"""Run by just before anything else to record which files are symlinks."""

import json
import os
import pathlib

template_root = pathlib.Path('.template', '{{ cookiecutter.project_slug }}')
di = {
    str(path.relative_to(template_root)): str(path.readlink())
    for path in template_root.rglob('*')
    if path.is_symlink()
}
pathlib.Path(os.environ['TEMPFILE']).write_text(json.dumps(di))
