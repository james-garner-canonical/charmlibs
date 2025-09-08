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
