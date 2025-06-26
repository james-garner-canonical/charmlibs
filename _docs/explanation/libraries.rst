Libraries
=========

There are two kinds of two kinds of charm library.

#. A library may either be a relation library or not.

    * Relation libraries allow charms to interact with other charms over a defined Juju relation. Using a relation library will therefore require adding a specific relation to your ``charmcraft.yaml`` and integrating your charm with another charm after deploying them both.

    * Non-relation libraries cover all other use cases for libraries, including general-purpose charming helpers and sharing team-specific code between charms. These libraries may work with your charm in a standalone way. Alternatively, they may provide functionality that relies on a connection to another charm, using a relation library.

#. A library may be distributed either as a Python package or as a single-file module on Charmhub.

    * A Python package is included in your charm's ``pyproject.toml`` or ``requirements.txt``. ``charmcraft pack`` will build these libraries and install them into a virtual environment which is distributed with your packed charm.

    * A Charmhub hosted library should be included in your charm's ``charmcraft.yaml`` and vendored into your codebase after fetching the library with ``charmcraft fetch-libs``. These libraries are included directly in your packed charm.
