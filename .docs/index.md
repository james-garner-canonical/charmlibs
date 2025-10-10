---
relatedlinks: "[Ops](https://documentation.ubuntu.com/ops/), [Charmcraft](https://documentation.ubuntu.com/charmcraft/stable/), [Concierge](https://github.com/canonical/concierge), [Jubilant](https://documentation.ubuntu.com/jubilant/), [Juju](https://documentation.ubuntu.com/juju/3.6/), [Pebble](https://documentation.ubuntu.com/pebble/)"
---

# Charmlibs

```{toctree}
:maxdepth: 3
:hidden: false

tutorial
how-to/index
reference/index
explanation/index
```

`charmlibs` is the home of Canonical's charm libraries.

This site hosts reference documentation for {ref}`charmlibs<reference-charmlibs>` and {ref}`charmlibs.interfaces<reference-charmlibs-interfaces>` packages, as well as for {ref}`interfaces<reference-interfaces>`.
There's are also pages listing {ref}`general charm libraries<general-libs-listing>` and {ref}`charm interface libraries<interface-libs-listing>`, including `charmlibs` packages, legacy Charmhub-hosted libs, and everything in-between, where you can find out more about which libraries are recommended and where to get them.

To get started contributing your own library to the `charmlibs` monorepo, check out {doc}`the tutorial<tutorial>`.

You can also read our {ref}`guidance on distributing charm libraries<how-to-python-package>`.

If you're new to charms, see {ref}`Juju | Charm <juju:charm>`.

## In this documentation

````{grid} 1 1 2 2

```{grid-item-card} [Tutorial](tutorial)
**Start here:** Write your first charm library.
```

```{grid-item-card} [How-to guides](how-to/index)
**Step-by-step guides**
- {ref}`Distribute charm libraries <how-to-python-package>`
- Customize {ref}`functional <how-to-customize-functional-tests>` and {ref}`integration <how-to-customize-integration-tests>` tests in the `charmlibs` monorepo
```

````

````{grid} 1 1 2 2
:reverse:

```{grid-item-card} [Reference](reference/index)
**Technical information** 
- Listing of {ref}`general <general-libs-listing>` and {ref}`interface <interface-libs-listing>` charm libraries
- Library reference documentation for {ref}`charmlibs <reference-charmlibs>` and {ref}`charmlibs.interfaces <reference-charmlibs-interfaces>` packages
- {ref}`Interface documentation <reference-interfaces>`
```

```{grid-item-card} [Explanation](explanation/index)
**Discussion and clarification** of key topics
- {ref}`Charm libraries <charm-libs>`
- {ref}`Testing <charmlibs-tests>` and {ref}`publishing <charmlibs-publishing>` from the `charmlibs` monorepo
```

````

