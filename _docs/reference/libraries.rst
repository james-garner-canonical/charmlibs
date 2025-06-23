Libraries
=========

This page lists known libraries used in charming. The primary purpose of this listing is to help charm developers find and learn about the libraries in the charming ecosystem.

There are two kinds of two kinds of charm library.

#. A library may either be a relation library or not.

    * Relation libraries allow charms to interact with other charms over a defined Juju relation. Using a relation library will therefore require adding a specific relation to your ``charmcraft.yaml`` and integrating your charm with another charm after deploying them both.

    * Non-relation libraries cover all the other use cases for libraries, from general purpose charming helpers to sharing team specific code between charms. These libraries may work with your charm alone, or they may provide functionality that relies on being connected to another charm via a relation library.

#. A library may either be distributed as a Python package, or as a single file module via Charmhub.

    * A Python package is included in your charm's ``pyproject.toml`` or ``requirements.txt``. ``charmcraft pack`` will build these libraries and install them into a virtual environment which is distributed with your packed charm.

    * A Charmhub hosted library should be included in your charm's ``charmcraft.yaml`` and vendored into your codebase after fetching the library with ``charmcraft fetch-libs``. These libraries are included directly in your packed charm.

This page includes a table listing relation libraries, and a table listing non-relation libraries. Use the search box above each table to search in that specific table. Use your browser's search to search across both tables.

The status of a library is indicated by the leftmost column. There's a key below, also available on hover.

Non-relation libraries
----------------------

.. include:: generated/non-relation-libs-table.rst

Relation libraries
------------------

.. include:: generated/relation-libs-table.rst
