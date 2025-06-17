# Put it first so that "make" without argument is like "make help".
help:
	@echo "\n" \
        "------------------------------------------------------------- \n" \
        "* watch, build and serve the documentation:  make run \n" \
        "* only build:                                make html \n" \
        "* clean full environment:                    make clean \n" \
        "------------------------------------------------------------- \n"

.PHONY: html run clean install linkcheck

run:
	uvx --from=rust-just just docs run

html:
	uvx --from=rust-just just docs html

clean:
	uvx --from=rust-just just docs clean

SPHINXDIR = .sphinx
VENVDIR = $(SPHINXDIR)/venv
VENV = $(VENVDIR)/bin/activate

$(VENVDIR):
	python3 -c "import venv" || \
        (echo "You must install python3-venv before you can build the documentation."; exit 1)
	@echo "... setting up virtualenv"
	python3 -m venv $(VENVDIR)
	. $(VENV); pip install $(PIPOPTS) --require-virtualenv \
	    --upgrade -r $(SPHINXDIR)/requirements.txt \
            --log $(VENVDIR)/pip_install.log
	@test ! -f $(VENVDIR)/pip_list.txt || \
            mv $(VENVDIR)/pip_list.txt $(VENVDIR)/pip_list.txt.bak
	@. $(VENV); pip list --local --format=freeze > $(VENVDIR)/pip_list.txt
	@touch $(VENVDIR)

install: $(VENVDIR)

linkcheck: install
	. $(VENV) ; $(SPHINXBUILD) -b linkcheck "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) || { grep --color -F "[broken]" "$(BUILDDIR)/output.txt"; exit 1; }
	exit 0
