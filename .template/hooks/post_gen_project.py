import json
import os
import pathlib
import sys
import warnings


TEMPFILE_VAR = 'TEMPFILE'
if not TEMPFILE_VAR in os.environ:
    warnings.warn(f'{TEMPFILE_VAR} not defined in environment! Make sure you run `cookiecutter` via `just`.')
    sys.exit()
tempfile_path = pathlib.Path(os.environ[TEMPFILE_VAR])
if not tempfile_path.is_file():
    warnings.warn(f'{TEMPFILE_VAR}={tempfile_path} is not a file!')
    sys.exit()
di = json.loads(tempfile_path.read_text())
for path, target in di.items():
    path = pathlib.Path(path)
    path.unlink()
    path.symlink_to(target)
