mod interface  # load interface module to expose interface subcommands
mod docs  # load docs module to expose docs subcommands

set ignore-comments  # don't print comment lines in recipes

# set on the commandline as needed, e.g. `just package=pathops python=3.10 unit`
python := '3.10'
# for integration tests, e.g. `just tag=24.04 pack-k8s` `just tag=foo integration-machine`
tag := env('CHARMLIBS_TAG', '')

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
[positional-arguments]  # forward recipe args to the script as argv, so quoting is preserved
init *args:
    @'{{ justfile_dir() }}/.scripts/recipes/init.py' "$@"

[doc('Run `ruff`, failing afterwards if any errors are found.')]
fast-lint path='.':
    @'{{ justfile_dir() }}/.scripts/recipes/fast_lint.py' '{{ path }}'

[doc('`lint`, `unit` test, and build the `docs` for a package.')]
check package: (lint package) (unit package) (docs::html package)

[doc('Run `ruff check --fix` and `ruff --format`, modifying files in place.')]
format package='.':
    @'{{ justfile_dir() }}/.scripts/recipes/format.py' '{{ package }}'

[doc("Run `uv add` for package, respecting repo-level version constraints, e.g. `just add pathops 'pydantic>=2'`.")]
[positional-arguments]  # forward recipe args to the script as argv, so quoting is preserved
add package +args:
    @'{{ justfile_dir() }}/.scripts/recipes/add.py' "$@"

[doc('Run linting and static analysis for a specific package, e.g. `just python=3.10 lint interfaces/tls-certificates`.')]
[positional-arguments]  # forward recipe args to the script as argv, so quoting is preserved
lint package *pyright_args:
    @'{{ justfile_dir() }}/.scripts/recipes/lint.py' --python='{{ python }}' "$@"

[doc('Run package specific static analysis only, e.g. `just python=3.10 static pathops`.')]
[positional-arguments]  # forward recipe args to the script as argv, so quoting is preserved
static package *args:
    @'{{ justfile_dir() }}/.scripts/recipes/static.py' --python='{{ python }}' "$@"

[doc("Run unit tests with `coverage`, e.g. `just python=3.10 unit pathops`.")]
[positional-arguments]  # forward recipe args to the script as argv, so quoting is preserved
unit *args:
    @'{{ justfile_dir() }}/.scripts/recipes/unit.py' --python='{{ python }}' "$@"

[doc("Run functional tests with `coverage`, e.g. `just python=3.10 functional pathops`.")]
[positional-arguments]  # forward recipe args to the script as argv, so quoting is preserved
functional *args:
    @'{{ justfile_dir() }}/.scripts/recipes/functional.py' --python='{{ python }}' "$@"

[doc("Combine `coverage` reports, e.g. `just python=3.10 combine-coverage pathops`.")]
combine-coverage package:
    @'{{ justfile_dir() }}/.scripts/recipes/combine_coverage.py' --python='{{ python }}' '{{ package }}'

[doc("Execute pack script to pack Kubernetes charm(s) for Juju integration tests.")]
[positional-arguments]  # forward recipe args to the script as argv, so quoting is preserved
pack-k8s package *args:
    @'{{ justfile_dir() }}/.scripts/recipes/pack.py' --substrate=k8s --tag='{{ tag }}' "$@"

[doc("Execute pack script to pack machine charm(s) for Juju integration tests.")]
[positional-arguments]  # forward recipe args to the script as argv, so quoting is preserved
pack-machine package *args:
    @'{{ justfile_dir() }}/.scripts/recipes/pack.py' --substrate=machine --tag='{{ tag }}' "$@"

[doc("Run juju integration tests for packed k8s charm(s), setting CHARMLIBS_SUBSTRATE and CHARMLIBS_TAG, and selecting 'not machine_only'.")]
[positional-arguments]  # forward recipe args to the script as argv, so quoting is preserved
integration-k8s package *flags:
    @'{{ justfile_dir() }}/.scripts/recipes/integration.py' --substrate=k8s --tag='{{ tag }}' --python='{{ python }}' "$@"

[doc("Run juju integration tests for packed machine charm(s), setting CHARMLIBS_SUBSTRATE and CHARMLIBS_TAG, and selecting 'not k8s_only'.")]
[positional-arguments]  # forward recipe args to the script as argv, so quoting is preserved
integration-machine package *flags:
    @'{{ justfile_dir() }}/.scripts/recipes/integration.py' --substrate=machine --tag='{{ tag }}' --python='{{ python }}' "$@"

[doc("Make .interfaces.json file.")]
interfaces-json:
    @'{{ justfile_dir() }}/.scripts/recipes/interfaces_json.py'

[doc('Run unit tests for the repository tooling scripts in `.scripts/`.')]
[positional-arguments]  # forward recipe args to the script as argv, so quoting is preserved
scripts-unit *flags:
    @'{{ justfile_dir() }}/.scripts/recipes/scripts_unit.py' --python='{{ python }}' "$@"
