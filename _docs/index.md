# Charmlibs

```{toctree}
:maxdepth: 3
:hidden: false

how-to/index
reference/index
```

This is the Charm Tech team at Canonical's documentation website for charm libraries.
It hosts the documentation for the team's charm libraries that are distributed as Python packages,
as well as general documentation about charm libraries.

You can also read our {ref}`guidance on distributing charm libraries as Python packages <how-to-python-package>`.

If you're new to charms, see {ref}`Juju | Charm <juju:charm>`.

## Pathops

Pathops is a Python library providing
a {doc}`pathlib <python:library/pathlib>`-like interface
for Kubernetes charms
to interact with files in their workload container.
Charms can use [ContainerPath](pathops.ContainerPath) to interact with files in the workload container,
or [LocalPath](pathops.LocalPath) to interact with local files using the same API.
Code designed to work for both cases can use [PathProtocol](pathops.PathProtocol) in type annotations.

Pathops is [available on PyPI](https://pypi.org/project/charmlibs-pathops). Read the [Pathops reference documentation](pathops).
