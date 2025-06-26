Libraries
=========

There are two kinds of two kinds of charm library.

#. A library may either be a relation library or not.

    * Relation libraries allow charms to interact with other charms over a defined Juju relation. Using a relation library will therefore require adding a specific relation to your ``charmcraft.yaml`` and integrating your charm with another charm after deploying them both.

    * Non-relation libraries cover all other use cases for libraries, including general-purpose charming helpers and sharing team-specific code between charms. These libraries may work with your charm in a standalone way. Alternatively, they may provide functionality that relies on a connection to another charm, using a relation library.

#. A library may be distributed either as a Python package or as a single-file module on Charmhub.

    * You should list Python packages in ``pyproject.toml`` or ``requirements.txt``. ``charmcraft pack`` will build these libraries and install them into a virtual environment which is distributed with your packed charm.

    * You should list Charmhub-hosted libraries in ``charmcraft.yaml``, then run ``charmcraft fetch-libs`` to fetch the libraries. Make sure to commit the fetched libraries into version control, so that your codebase vendors the libraries. These libraries are included directly in your packed charm.
