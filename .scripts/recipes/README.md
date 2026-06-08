# `.scripts/recipes/`

Each recipe in the repository's `justfile` is a thin wrapper calling a script defined in this directory.

Each script uses a `uv` shebang line and [PEP 723](https://peps.python.org/pep-0723/) format metadata. `uv run --script` puts the script directory on the path, so sibling imports just work.

Run the unit tests defined in `tests/` with `just scripts-unit`.
