<!--
Template: Migrating an existing Charmhub-hosted library into the charmlibs monorepo.

Before opening this PR, please read the migration guide:
https://documentation.ubuntu.com/charmlibs/how-to/migrate/
-->

## Library being migrated

- **Charmhub library:** <!-- e.g. `charms.operator_libs_linux.v2.snap` -->
- **New `charmlibs` package:** <!-- e.g. `charmlibs.snap` / `charmlibs.interfaces.tls_certificates` -->
- **Library type:** <!-- check one -->
  - [ ] General library (`charmlibs.<name>`, `just init`)
  - [ ] Interface library (`charmlibs.interfaces.<name>`, `just init --interface`)

## Migration status

This is a bug-for-bug migration of Charmhub library version: <!-- e.g. `snap v2.1` -->.

- [ ] Package initialised with `just init` or `just init --interface`.
- [ ] Code migrated to `src/charmlibs/<name>/_<name>.py`.
- [ ] Public API exported from `__init__.py` with `__all__`.
- [ ] `LIB_ID`, `LIB_API`, `LIB_PATCH` removed (or retained with a note on why).
- [ ] `PYDEPS` moved to `pyproject.toml` `dependencies` with appropriate constraints.
- [ ] Module docstring moved to `__init__.py` (this is rendered in the docs).
- [ ] Charmhub lib API/patch version documented in the private module's docstring.
- [ ] Unit tests migrated and passing, plus functional and integration tests as appropriate.
- [ ] Unnecessary files and directories created by `just init` have been removed.
- [ ] Docs (if any) migrated to `<library path>/docs/`.
- [ ] Interface metadata added or updated as needed (if applicable).
- [ ] `.docs/reference/libs.yaml` updated (new entry added, old Charmhub entry marked deprecated).

## Commit strategy

To make review easier, this PR begins with a series of mechanical commits:

<!-- Update to match your work. -->

1. **Scaffolding** — output of `just init` or `just init --interface`.
2. **Lift and shift** — the existing Charmhub library source, tests, and docs copied to their new locations verbatim, providing a baseline for comparison with the original.
4. **Fix imports** — update import paths from `charms.<charm>.v<n>` to `charmlibs.<name>` (or `charmlibs.interfaces.<name>`) in code, tests and docs.
3. **Lint and format** — result of `just format` and `just lint`, with any necessary `pyproject.toml` config or ignores to avoid unwanted changes.
