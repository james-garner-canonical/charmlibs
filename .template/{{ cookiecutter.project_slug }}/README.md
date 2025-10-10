# charmlibs.{{ 'interfaces.' if cookiecutter._interface else '' }}{{ cookiecutter.project_slug.replace('-', '_') }}

The `{{ cookiecutter.project_slug }}` {{ 'interface ' if cookiecutter._interface else '' }}library.

To install, add `charmlibs-{{ 'interfaces-' if cookiecutter._interface else '' }}{{ cookiecutter.project_slug.replace('_', '-') }}` to your Python dependencies. Then in your Python code, import as:

```py
from charmlibs{{ '.interfaces' if cookiecutter._interface else '' }} import {{ cookiecutter.project_slug.replace('-', '_') }}
```

See the [reference documentation](https://documentation.ubuntu.com/charmlibs/reference/charmlibs/{{ 'interfaces/' if cookiecutter._interface else '' }}{{ cookiecutter.project_slug.replace('-', '_') }}) for more.
