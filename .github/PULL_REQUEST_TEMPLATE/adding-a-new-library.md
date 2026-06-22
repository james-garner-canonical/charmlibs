<!--
Template: Adding a new library to the charmlibs monorepo.

Read first:
https://documentation.ubuntu.com/charmlibs/how-to/python-package/#what-can-i-publish-under-the-charmlibs-namespace

To learn how to add a new library:
https://documentation.ubuntu.com/charmlibs/tutorial/
-->

## Library being added

- **New `charmlibs` package:** <!-- e.g. `charmlibs.uptime` / `charmlibs.interfaces.uptime` -->
- **Library type:** <!-- check one -->
  - [ ] General library (`charmlibs.<name>`, `just init`)
  - [ ] Interface library (`charmlibs.interfaces.<name>`, `just init --interface`)
- **Specification:** <!-- link to the spec / design doc -->

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

### Interface libraries only

<!-- Remove for general libraries. -->

- [ ] Directory name exactly matches the interface name as written in `charmcraft.yaml`.
- [ ] Interface metadata added under `interfaces/<name>/interface/` (readme, metadata, databag schema).
- [ ] Testing package added under `interfaces/<name>/testing/` exporting `relation_for_provider` and `relation_for_requirer` (see [how-to guide](https://documentation.ubuntu.com/charmlibs/how-to/provide-relation-data-for-charm-tests/)).

## Commit strategy

<!-- Update to match your work. -->

To make review easier, this first commit in this PR is purely the output of `just init`, and can safely be excluded from review.
