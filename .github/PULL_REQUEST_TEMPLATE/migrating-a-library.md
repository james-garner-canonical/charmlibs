<!--
Template: Migrating an existing Charmhub-hosted library into the charmlibs monorepo.

Read first:
https://documentation.ubuntu.com/charmlibs/how-to/python-package/#what-can-i-publish-under-the-charmlibs-namespace

To learn how to migrate a library:
https://documentation.ubuntu.com/charmlibs/how-to/migrate/
-->

## Library being migrated

- **Charmhub-hosted library:** <!-- for example `charms.operator_libs_linux.v2.snap` -->
- **Charmhub-hosted library version:** <!-- for example `v2.1` -->
- **New `charmlibs` package:** <!-- for example `charmlibs.snap` / `charmlibs.interfaces.tls_certificates` -->
<!-- remove one -->
This is a general library (`charmlibs.<name>`, `just init`).
This is an interface library (`charmlibs.interfaces.<name>`, `just init --interface`).

## Migration status

This is a bug-for-bug migration of the Charmhub-hosted library:

- [ ] Package initialised with `just init` or `just init --interface`.
- [ ] Code migrated to `src/charmlibs/<name>/_<name>.py`.
- [ ] Public API exported from `__init__.py` with `__all__`.
- [ ] `LIB_ID`, `LIB_API`, `LIB_PATCH` removed (or retained with a note on why).
- [ ] Library version set for release (typically `1.0.0`).
- [ ] `PYDEPS` moved to `pyproject.toml` `dependencies` with appropriate constraints.
- [ ] Module docstring moved to `__init__.py` (this is rendered in the docs).
- [ ] Charmhub-hosted lib API/patch version documented in the private module's docstring.
- [ ] Unit tests migrated and passing, plus functional and integration tests as appropriate.
- [ ] Unnecessary files and directories created by `just init` have been removed, including `test_version.py`.
- [ ] Docs (if any) migrated to `<library path>/docs/`.
- [ ] `.docs/reference/libs.yaml` updated (new entry added, old Charmhub entry marked deprecated).

### Interface libraries only

<!-- Remove for general libraries. -->

- [ ] Directory name exactly matches the interface name as written in `charmcraft.yaml`.
- [ ] Interface metadata added (or updated if necessary), or an issue created and tracked to do this as a follow-up task.
- [ ] Testing package added under `interfaces/<name>/testing/` exporting `relation_for_provider` and `relation_for_requirer` (see [how-to guide](https://documentation.ubuntu.com/charmlibs/how-to/provide-relation-data-for-charm-tests/)), or an issue created and tracked to do this as a follow-up task.


## Commit strategy

To make review easier, this PR begins with a series of mechanical commits that can be easily excluded from review:

<!-- Update to match your work. -->

1. **Scaffolding** — output of `just init` or `just init --interface`.
2. **Lift and shift** — the existing Charmhub library source, tests, and docs copied to their new locations verbatim, providing a baseline for comparison with the original.
4. **Fix imports** — update import paths from `charms.<charm>.v<n>` to `charmlibs.<name>` (or `charmlibs.interfaces.<name>`) in code, tests and docs.
3. **Lint and format** — result of `just format` and `just lint`, with any necessary `pyproject.toml` config or ignores to avoid unwanted changes.
