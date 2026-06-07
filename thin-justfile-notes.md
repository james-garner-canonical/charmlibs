# Working notes: thin justfile + recipe scripts

> **Temporary file.** Lives on the `26-06+ci+thin-justfile` branch for other agents working on
> this effort. Delete before this work lands in `main`.

## Goal

Turn the `justfile` (and `interface.just` / `docs.just`) into a thin wrapper: one recipe per
public entry point, where each recipe just forwards to a Python script. Move all real logic out of
inline bash and into maintainable, testable Python.

## What we keep / fix

Keep about `just`:

- Common public interface runnable from anywhere in the repo (recipes resolve from `justfile_dir()`).
- No special syntax for passing extra args to recipes.

Fix about the current `justfile`:

- Inline bash scripts are hard to maintain -> move logic into Python.
- Recursive just-to-just calls are ugly -> become plain Python function calls / imports.
- Fancy defaults are ugly -> become argparse defaults.
- Bad arg quoting by default -> use `[positional-arguments]` + `"$@"` into the script's argv, and
  the script owns quoting via `subprocess` lists (never a shell string).

## Decisions

1. **Architecture: per-recipe entry scripts + a shared internal module.**
   Not a god script, not a package. Each public recipe maps to one greppable file. Shared logic
   lives in `_common.py`. No `pyproject` / lockfile for the scripts.

2. **Why no package is needed:** almost all shared logic is stdlib (`subprocess`, `pathlib`,
   `os.environ`). Third-party deps (PyYAML etc.) stay declared per-leaf-script in PEP 723 headers,
   so the thing that would justify a package (sharing deps via a lockfile) never bites.

3. **Sibling imports:** `uv run --script .scripts/recipes/foo.py` puts `.scripts/recipes/` on
   `sys.path[0]`, so `import _common` works. Therefore `_common.py` MUST live in the same directory
   as the scripts that import it.

4. **Layout:** new recipe-backing scripts go in `.scripts/recipes/`. A subdirectory (not a filename
   prefix) so `_common.py` has a home, the import surface is contained, and it's a down payment on a
   future `.scripts/` reorg (public utils vs internal CI vs special-purpose tools) rather than
   throwaway. Existing `.scripts/*.py` files are left untouched for now.

5. **Naming: underscores, not hyphens.** Recipe scripts must be importable (`_common` by all of
   them; composite recipes like `check`/`lint` importing their constituents). Existing scripts will
   be standardised on underscores in a future PR.

6. **PEP 723 gotcha:** keep `_common.py` stdlib-only. Anything needing a third-party dep stays in
   the leaf script that declares it in its own PEP 723 block.

## Rollout

- [ ] Proof-of-concept slice: migrate the coverage family (`unit`, `functional`, `_coverage`,
      `combine-coverage`) into `.scripts/recipes/` + `_common.py`. Confirm `just unit` / `just
      functional` parity, leave everything else untouched.
- [ ] If the ergonomics feel good, migrate the remaining recipes.
- [ ] Separate future PR: reorganise / rename existing `.scripts/` files (standardise on
      underscores, split public / internal-CI / special-purpose).
