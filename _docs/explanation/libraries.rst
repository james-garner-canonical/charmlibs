Libraries
=========

There are two kinds of two kinds of charm library.

#. A library may either be a relation library or not.

    * Relation libraries allow charms to interact with other charms over a defined Juju relation. Using a relation library will therefore require adding a specific relation to your ``charmcraft.yaml`` and integrating your charm with another charm after deploying them both.

    * Non-relation libraries cover all the other use cases for libraries, from general purpose charming helpers to sharing team specific code between charms. These libraries may work with your charm alone, or they may provide functionality that relies on being connected to another charm via a relation library.

#. A library may either be distributed as a Python package, or as a single file module via Charmhub.

    * A Python package is included in your charm's ``pyproject.toml`` or ``requirements.txt``. ``charmcraft pack`` will build these libraries and install them into a virtual environment which is distributed with your packed charm.

    * A Charmhub hosted library should be included in your charm's ``charmcraft.yaml`` and vendored into your codebase after fetching the library with ``charmcraft fetch-libs``. These libraries are included directly in your packed charm.
