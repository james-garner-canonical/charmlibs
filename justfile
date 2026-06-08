mod interface  # load interface module to expose interface subcommands
mod docs  # load docs module to expose docs subcommands

set ignore-comments  # don't print comment lines in recipes
set positional-arguments  # forward recipe args to scripts as argv ("$@"), so quoting is preserved

# this is the first recipe in the file, so it will run if just is called without a recipe
_short_help:
    @echo '{{BOLD}}Charmlibs is the Canonical charm libraries monorepo{{NORMAL}}'
    @echo ''
    @echo '{{BOLD}}List all commands with {{CYAN}}just help{{NORMAL}}{{BOLD}}, or:{{NORMAL}}'
    @echo '- Create a new package: {{CYAN}}just init{{NORMAL}} or {{CYAN}}just interface init{{NORMAL}}'
    @echo '- Run {{CYAN}}ruff{{NORMAL}} for all packages: {{CYAN}}just fast-lint{{NORMAL}}'
    @echo '- Lint, unit test, and build docs for a package: {{CYAN}}just check <package>{{NORMAL}}'
    @echo ''
    @echo '{{BOLD}}Run individual checks for a package:{{NORMAL}}'
    @echo '- {{CYAN}}just lint <package>{{NORMAL}} (fix errors with {{CYAN}}just format <package>{{NORMAL}})'
    @echo '- {{CYAN}}just unit <package>{{NORMAL}}'
    @echo '- {{CYAN}}just functional <package>{{NORMAL}} (may require additional software like {{CYAN}}pebble{{NORMAL}})'
    @echo ''
    @echo '{{BOLD}}Run integration tests{{NORMAL}} (requires a Juju controller and a cloud):'
    @echo '- Pack: {{CYAN}}just pack-k8s <package>{{NORMAL}} or {{CYAN}}just pack-machine <package>{{NORMAL}}'
    @echo '- Run: {{CYAN}}just integration-k8s <package>{{NORMAL}} or {{CYAN}}just integration-machine <package>{{NORMAL}}'
    @echo ''
    @echo '{{BOLD}}Build the docs: {{CYAN}}just docs{{NORMAL}}'
    @echo '- For specific packages only: {{CYAN}}just docs html <packages>{{NORMAL}}'

[doc('Describe usage and list the available recipes.')]
help:
    @echo 'All recipes require {{CYAN}}`uv`{{NORMAL}} to be available.'
    @just --list --unsorted --list-submodules

[doc('Create the files for a new charmlibs package interactively.')]
init *args:
    @.scripts/recipes/init.py "$@"

[doc('Run `ruff`, failing afterwards if any errors are found.')]
fast-lint *args:
    @.scripts/recipes/fast_lint.py "$@"

[doc('`lint`, `unit` test, and build the `docs` for a package.')]
check package: (lint package) (unit package) (docs::html package)

[doc('Run `ruff check --fix` and `ruff --format`, modifying files in place.')]
format *args:
    @.scripts/recipes/format.py "$@"

[doc("Run `uv add` for package, respecting repo-level version constraints, e.g. `just add pathops 'pydantic>=2'`.")]
add *args:
    @.scripts/recipes/add.py "$@"

[doc('Run linting and static analysis for a package, e.g. `just lint interfaces/tls-certificates`.')]
lint *args:
    @.scripts/recipes/lint.py "$@"

[doc('Run package specific static analysis only, e.g. `just static pathops`.')]
static *args:
    @.scripts/recipes/static.py "$@"

[doc("Run unit tests with `coverage`, e.g. `just unit pathops`.")]
unit *args:
    @.scripts/recipes/unit.py "$@"

[doc("Run functional tests with `coverage`, e.g. `just functional pathops`.")]
functional *args:
    @.scripts/recipes/functional.py "$@"

[doc("Combine `coverage` reports, e.g. `just combine-coverage pathops`.")]
combine-coverage *args:
    @.scripts/recipes/combine_coverage.py "$@"

[doc("Execute pack script to pack Kubernetes charm(s) for Juju integration tests.")]
pack-k8s *args:
    @.scripts/recipes/pack.py --substrate=k8s "$@"

[doc("Execute pack script to pack machine charm(s) for Juju integration tests.")]
pack-machine *args:
    @.scripts/recipes/pack.py --substrate=machine "$@"

[doc("Run juju integration tests for packed k8s charm(s), setting CHARMLIBS_SUBSTRATE and CHARMLIBS_TAG, and selecting 'not machine_only'.")]
integration-k8s *args:
    @.scripts/recipes/integration.py --substrate=k8s "$@"

[doc("Run juju integration tests for packed machine charm(s), setting CHARMLIBS_SUBSTRATE and CHARMLIBS_TAG, and selecting 'not k8s_only'.")]
integration-machine *args:
    @.scripts/recipes/integration.py --substrate=machine "$@"

[doc("Make .interfaces.json file.")]
interfaces-json:
    @.scripts/recipes/interfaces_json.py

[doc('Run unit tests for the repository tooling scripts in `.scripts/`.')]
scripts-unit *args:
    @.scripts/recipes/scripts_unit.py "$@"
