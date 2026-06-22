<!--
Template: Adding a new library to the charmlibs monorepo.

If you selected the wrong template, go back one page in your browser.

Read first:
https://documentation.ubuntu.com/charmlibs/how-to/python-package/#what-can-i-publish-under-the-charmlibs-namespace

To learn how to add a new library:
https://documentation.ubuntu.com/charmlibs/tutorial/
-->

## Library being added

- **New `charmlibs` package:** <!-- for example `charmlibs.uptime` / `charmlibs.interfaces.uptime` -->
- **Specification:** <!-- link to the spec / design doc -->

<!-- remove one -->
This is a general library (`charmlibs.<name>`, `just init`).
This is an interface library (`charmlibs.interfaces.<name>`, `just init --interface`).


## Checklist

- [ ] Package initialised with `just init` or `just init --interface`.
- [ ] Public API exported from `__init__.py` with `__all__`.
- [ ] Everything else is private, unless explicitly documented as public.
- [ ] Module docstring in `__init__.py` describes the package (rendered in the reference docs).
- [ ] Unit tests added and passing (`just unit <package>`).
- [ ] Functional tests added, or the `tests/functional` directory removed.
- [ ] Integration tests added, or the `tests/integration` directory removed.
- [ ] Unnecessary files and directories created by `just init` have been removed (for example `test_version.py` once real tests exist).
- [ ] Docs (tutorial / how-to / explanation) added under `<package>/docs/` if needed.
- [ ] `.docs/reference/libs.yaml` updated with a new entry (status, URLs, description, tags from `tags.yaml`).
- [ ] `CODEOWNERS` updated with a `/<package>/` entry for the owning team.
- [ ] `uv.lock` committed.
- [ ] `just check <package>` passes (lint + unit + docs).

<!-- remove section if this isn't an interface library -->
### Interface library specific items

- [ ] Directory name exactly matches the interface name as written in `charmcraft.yaml`.
- [ ] Interface metadata added under `interfaces/<name>/interface/` (readme, metadata, databag schema).
- [ ] Testing package added under `interfaces/<name>/testing/` exporting `relation_for_provider` and `relation_for_requirer` (see [how-to guide](https://documentation.ubuntu.com/charmlibs/how-to/provide-relation-data-for-charm-tests/)).

## Commit strategy

<!-- Describe how the work is split across commits in this PR. -->

The first commit in this PR is purely the output of `just init`. This commit can be excluded from the changes view (once verified), making it easy to se what changes were made on top of the template.
