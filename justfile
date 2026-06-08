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

help *args:
    @.scripts/recipes/help.py "$@"

init *args:
    @.scripts/recipes/init.py "$@"

fast-lint *args:
    @.scripts/recipes/fast_lint.py "$@"

check *args:
    @.scripts/recipes/check.py "$@"

format *args:
    @.scripts/recipes/format.py "$@"

add *args:
    @.scripts/recipes/add.py "$@"

lint *args:
    @.scripts/recipes/lint.py "$@"

static *args:
    @.scripts/recipes/static.py "$@"

unit *args:
    @.scripts/recipes/unit.py "$@"

functional *args:
    @.scripts/recipes/functional.py "$@"

combine-coverage *args:
    @.scripts/recipes/combine_coverage.py "$@"

pack-k8s *args:
    @.scripts/recipes/pack_k8s.py "$@"

pack-machine *args:
    @.scripts/recipes/pack_machine.py "$@"

integration-k8s *args:
    @.scripts/recipes/integration_k8s.py "$@"

integration-machine *args:
    @.scripts/recipes/integration_machine.py "$@"

interfaces-json *args:
    @.scripts/recipes/interfaces_json.py "$@"

scripts-unit *args:
    @.scripts/recipes/scripts_unit.py "$@"
