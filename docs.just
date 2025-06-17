set working-directory := '_docs'
_docs_build_location := env('READTHEDOCS_OUTPUT', '_build')

[doc('Build the docs.')]
html:
    uvx --with-requirements=.sphinx/requirements.txt --from=sphinx \
        sphinx-build -T -W --keep-going -b dirhtml -d _build/doctrees -D language=en . '{{_docs_build_location}}/html'

[doc('Watch, build, and serve the docs.')]
run:
    uvx --with-requirements=.sphinx/requirements.txt --from=sphinx \
        sphinx-autobuild --watch .. --ignore '**/generated/*' -b dirhtml . '{{_docs_build_location}}/html'

[doc('Check links.')]
linkcheck:
    uvx --with-requirements=.sphinx/requirements.txt --from=sphinx \
        sphinx-build -b linkcheck . '{{_docs_build_location}}'

[doc('Check spelling.')]
spellcheck:
    uvx pyspelling -c .sphinx/spellingcheck.yaml -j $(nproc)

[doc('Remove files created by building the docs.')]
clean:
    git clean -fx '{{_docs_build_location}}'
    rm -rf .sphinx/.doctrees
    rm -rf .sphinx/node_modules/
    rm -rf .sphinx/styles
    rm -rf .sphinx/vale.ini
    rm -rf reference/generated
