(charm-libs)=
# Charm libraries

A charm library is a library developed for use in Juju charms. There are two major ways in which these libraries are categorised: the library's distribution method, and the library's purpose.

(charm-libs-distribution)=
## Library distribution

There are two ways of distributing charm libraries: either as a single-file module associated with a charm and hosted on Charmhub, or a standard Python package.

(charm-libs-python-packages)=
### Python package libraries

Python packages use standard formats for metadata like the package version and the package's dependencies. This allows for precise specification of the version of required package, as well as the specification of version ranges. This makes it possible for the tools used when packing a charm to resolve your charm's dependencies and their dependencies (and so on) into a concrete set of packages, a process called dependency resolution. In contrast, {ref}`Charmhub-hosted libraries <charm-libs-charmhub-hosted>` are vendored into your charm's codebase, and their dependencies (if any) are manually added to your charm's dependencies.

Include Python packages in your charm by listing their [distribution package name](https://packaging.python.org/en/latest/discussions/distribution-package-vs-import-package/#what-s-a-distribution-package) and any version constraints in your charm's dependencies, typically in `pyproject.toml` or `requirements.txt`. `charmcraft pack` will build these libraries and install them into a virtual environment which is distributed with your packed charm. In your charm code, import the library with its [import package name](https://packaging.python.org/en/latest/discussions/distribution-package-vs-import-package/#what-s-an-import-package).

For example, you might add `charmlibs-pathops>=1` to your dependencies, and then write `from charmlibs import pathops` in `charm.py`.

Read about {ref}`when and how to distribute your library as a Python package <how-to-python-package>`.

(charm-libs-charmhub-hosted)=
### Charmhub-hosted libraries

Charmhub-hosted libraries are categorised under the namespaces of specific charms. Some libraries use 'dummy' charms for this.

Each library is a single-file Python module. To use Charmhub-hosted libraries, list them in the {ref}`charm-libs section of charmcraft.yaml <charmcraft:charmcraft-yaml-key-charm-libs>` and then run {doc}`charmcraft fetch-libs <charmcraft:reference/commands/fetch-libs>`. This will download the libraries and place them in `lib/$charm/v$api-version/$lib-name.py`. These files should be committed into your charm's version control.

Charm libraries all have an API version and a patch version, broadly equivalent to the major and minor version in semantic versioning. If a library is specified by API version only, then rerunning `charmcraft fetch-libs` will update it if there has been a patch release.

It is recommended that Charmhub-hosted libraries have no additional dependencies, but some do. If a library depends on a Python package, it should be listed in the `PYDEPS` variable in the module itself. You will need to manually add these dependencies to your charm's Python dependencies. If a library depends on another Charmhub-hosted library, this should be specified in its documentation, and you will need to add this library to your charm via `charmcraft.yaml` and `charmcraft fetch-libs`.

The `lib` directory is added to the `PYTHONPATH` by the charm's `dispatch` script, so these libraries are imported in charm code as `$charm.v$api-version.$lib-name`.

For example, you might add this to your `charmcraft.yaml`:

```yaml
charm-libs:
  - lib: operator_libs_linux.snap
    version: "2"
```

And then in your charm code, you would write `from operator_libs_linux.v2 import snap`.

Read more about {doc}`how to manage Charmcraft-hosted libraries <charmcraft:howto/manage-libraries>`.

(charm-libs-purpose)=
## Library purpose

There are many different purposes for charm libraries, but *interface libraries* are a special kind of library for interacting with another charm over a defined Juju interface.

(charm-libs-interface)=
### Interface libraries

A Juju interface is a name associated with one of the endpoints that a charm provides or requires. For two charms to be integrated, they must each have an endpoint with the same interface, with one being a requirer and the other a provider. This information is used on Charmhub to show charm users which charms can be integrated with each other.

Under the hood, a relation between two charms typically involves exchanging data using the app and unit databags Juju provides for that relation. The recommended way to do this is for the creators of an interface to define an interface schema for the data exchanged, and to provide an interface library that can be used by charms providing or requiring the interface to produce data conforming with the interface schema.

To use an interface in your charm, add a requires or provides endpoint to your `charmcraft.yaml` for that interface. Then you'll need to find the interface library for that interface. A good place to start is the {ref}`interface libraries listing <interface-libs-listing>`. You can also visit `charmhub.io/interfaces/<interface name>`, which lists the charms that provide and require the interface. The Charmhub page may present developer documentation for the interface, but you can also look at other charms that implement the interface to see what library they used.

Read the [listing of interface charm libraries](general-libs-listing).

(charm-libs-general)=
### General libraries

This category covers all other use cases for libraries, including general-purpose charming helpers and sharing team-specific code between charms. Non-interface libraries may provide everything you need to use them out of the box, like [](pathops). Alternatively, they may rely or build on functionality provided via integration with another charm.

Read the [listing of general charm libraries](general-libs-listing).
