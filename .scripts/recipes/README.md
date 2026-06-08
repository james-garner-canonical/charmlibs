# `.scripts/recipes/`

Python scripts that back the `just` recipes. The `justfile` stays a thin wrapper: each public
recipe is a one-liner that forwards its arguments to the matching script here, so that all real
logic lives in maintainable, testable Python instead of inline bash. (The `docs.just` and
`interface.just` submodules are migrated separately.)

## Layout

- **Entry scripts** — one per public recipe (e.g. `lint.py`, `static.py`, `unit.py`, `functional.py`,
  `pack.py`, `integration.py`, `check.py`, `init.py`, `interfaces_json.py`, `scripts_unit.py`). Each
  is an executable [PEP 723](https://peps.python.org/pep-0723/) script with an
  `#!/usr/bin/env -S uv run --script --no-project` shebang, so the `justfile` can run it directly.
  Entry scripts are deliberately thin: parse args, then call into a shared module or a function
  defined alongside `_main`. Some scripts back more than one recipe by taking a flag — for example
  `pack.py` and `integration.py` take `--substrate=k8s|machine`.
- **Shared modules** — underscore-prefixed (`_common.py`, `_coverage.py`). Imported by the entry
  scripts; not invoked as recipes themselves. Entry scripts may also import each other: `lint.py`
  reuses `fast_lint.fast_lint` and `static.static`.
- **`_functional.sh`** — the one irreducible piece of bash (see below).

## Conventions

- **Underscores, not hyphens**, for every filename. The scripts import each other as sibling
  modules, and `combine-coverage.py` would not be importable.
- **Sibling imports work for free.** `uv run --script foo.py` puts this directory on `sys.path[0]`,
  so `import _common` just works — no package, `pyproject.toml`, or lockfile needed.
- **Keep `_common.py` stdlib-only.** Third-party dependencies (PyYAML, etc.) belong in the PEP 723
  block of the individual leaf script that needs them, never in a shared module. The moment a
  shared helper needs a third-party dep is the signal to promote this directory to a real
  `uv`-managed tool.
- **Argument forwarding.** Entry scripts take the `package` as a positional argument and forward
  any extra arguments to the underlying tool (e.g. pytest) via `parse_known_args`. The `justfile`
  uses `[positional-arguments]` and `"$@"` so quoting is preserved end to end.

## The Python version (`--python`)

`_common.resolve_python(package, python)` is the single home for choosing a Python version. For now
it falls back to `_common.DEFAULT_PYTHON` (`3.10`). It already takes `package` so that a planned
change can default to the package's own minimum supported version (read from its `pyproject.toml`
`requires-python`) instead of a hardcoded value. When that lands, the `justfile`'s `python` default
can become empty and resolution moves entirely into this function.

## `_functional.sh`

Functional tests need a package's `tests/functional/setup.sh` / `teardown.sh` to be *sourced* (not
executed) by a single long-lived shell: they export environment variables, set the umask, and
start/stop background processes (e.g. pebble) whose lifetime must span the whole test run. That
can't be reproduced from Python without re-implementing a shell, so `functional.py` runs
`_functional.sh` with the working directory set to the package, passing `_coverage.py` as the
command to run between setup and teardown.

## Tests

Unit tests live in `tests/` and run with `just scripts-unit`. They mock out `_common.run` (and the
`uv run` prefix) so the command construction and control flow can be checked without invoking `uv`,
`pytest`, or `coverage`.

> Do not run functional tests directly on the host — use Workshop (see the repo `AGENTS.md`).
