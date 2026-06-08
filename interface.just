set positional-arguments  # forward recipe args to scripts as argv ("$@"), so quoting is preserved

# this is the first recipe in the file, so it will run if just is called without a recipe
[doc('Show help for the interface recipes.')]
help:
    @just --list interface --unsorted

[doc('Create the files for a new charmlibs.interfaces package interactively.')]
init *args:
    @.scripts/recipes/init.py --interface "$@"
