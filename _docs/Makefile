# Put it first so that "make" without argument is like "make help".
help:
	@echo "\n" \
        "------------------------------------------------------------- \n" \
        "* watch, build and serve the documentation:  make run \n" \
        "* only build:                                make html \n" \
        "* check links:                               make linkcheck \n" \
        "* clean full environment:                    make clean \n" \
        "------------------------------------------------------------- \n"

.PHONY: html run clean install linkcheck

run:
	uvx --from=rust-just just docs run

html:
	uvx --from=rust-just just docs html

linkcheck:
	uvx --from=rust-just just docs linkcheck

spellcheck:
	uvx --from=rust-just just docs spellcheck

clean:
	uvx --from=rust-just just docs clean
