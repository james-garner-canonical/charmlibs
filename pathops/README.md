# charmlibs-pathops

`pathops` provides a `pathlib`-like interface for local filesystem and workload container paths for Juju Charms.

To install, add `charmlibs-pathops` to your requirements. Then in your Python code, import as:

```py
from charmlibs import pathops
```

Check out the reference docs [here](https://canonical-charmlibs.readthedocs-hosted.com/reference/pathops/).

To get started, consider creating an attribute with the root directory for the local or remote paths you'll be working with.

```py
import ops
from charmlibs import pathops

class KubernetesCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        container = self.unit.get_container('container-name')
        self.root = pathops.ContainerPath('/', container=container)

# or

class MachineCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.root = pathops.LocalPath('/')
```

You can then write code that could be used by either charm, using the `pathops.PathProtocol` type, which describes the operations supported by both local and container paths.

```py
CONFIG_FILE_LOCATION = '/foo/bar'
CONFIG_FILE_CONTENTS = '...'

def write_config_file(root: pathops.PathProtocol) -> None:
    path = root / CONFIG_FILE_LOCATION
    path.write_text(CONFIG_FILE_CONTENTS)
```

For a Kubernetes charm, this also allows you to use the same API to work with paths in the charm container or the workload container.

```py
import ops
from charmlibs import pathops

class KubernetesCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.charm_root = pathops.LocalPath('/')
        container = self.unit.get_container('container-name')
        self.workload_root = pathops.ContainerPath('/', container=container)
        ...

    def copy_config(self):
        source = self.charm_root / 'foo/bar'
        dest = self.workload_root / 'foo/bar/baz'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())
```

`pathops` also provides a helper function for ensuring that a file is present with some specified content, which returns whether changes were made.

```py
import ops
from charmlibs import pathops

class KubernetesCharm(ops.CharmBase):
    ...

    def copy_config(self):
        changed = pathops.ensure_contents(
            path=self.workload_root / 'foo/bar/baz',
            source=(self.charm_root / 'foo/bar').read_bytes(),
        )
        if changed:
            # e.g. make workload reload config
            ...
```

`pathops.PathProtocol` provides a subset of the `pathlib.Path` API -- relative paths, hardlink and symlink manipulation, and `open` are unsupported.

A separate `chmod` method is also unsupported, as Pebble does not currently support this. `mkdir`, `write_bytes` and `write_text` instead provide the arguments `mode`, `user`, and `group` to set directory or file permissions and ownership.
