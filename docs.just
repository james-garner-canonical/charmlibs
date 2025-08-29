set working-directory := '.docs'

build_dir := env('READTHEDOCS_OUTPUT', '_build')

[doc('Build the docs.')]
html:
    #!/usr/bin/env -S uv run --script --no-project
    import pathlib, subprocess
    root = pathlib.Path('{{justfile_directory()}}')
    *packages, last = [
        *sorted(p.name for p in root.glob(r'[a-z]*') if p.is_dir() and p.name != 'interfaces'),
        *sorted(f'interfaces/{p.name}' for p in (root / 'interfaces').glob(r'[a-z]*') if p.is_dir()),
    ]
    uvx = [
        'uvx',
        '--from', 'sphinx',
        '--with-requirements', '.sphinx/requirements.txt',
    ]
    sphinx = [
        'sphinx-build',
        '-T', '-W', '--keep-going',
        '-b', 'dirhtml',
        '-d', '_build/doctrees',
        '-D', 'language=en',
    ]
    targets = ['.', '{{build_dir}}/html']
    for package in packages:
        cmd = [
            *uvx,
            '--with', f'../{package}',
            *sphinx,
            '-D', f'package={package}',
            '-D', 'suppress_warnings=ref.ref,ref.doc,myst.xref_missing',
            *targets,
        ]
        print(cmd)
        subprocess.check_call(cmd)
    package = last
    cmd = [
        *uvx,
        '--with', f'../{package}',
        *sphinx,
        '-D', f'package={package}',
        *targets,
    ]
    print(cmd)
    subprocess.check_call(cmd)

[doc('Watch, build, and serve the docs.')]
run:
    uvx --with-requirements=.sphinx/requirements.txt --from=sphinx \
        sphinx-autobuild --watch .. --ignore '**/generated/*' -b dirhtml . '{{build_dir}}/html'

[doc('Check links.')]
linkcheck:
    uvx --with-requirements=.sphinx/requirements.txt --from=sphinx \
        sphinx-build -b linkcheck . '{{build_dir}}'

[doc('Check spelling.')]
spelling: html
    uvx pyspelling -c .sphinx/spellingcheck.yaml -j $(nproc)

[doc('Remove files created by building the docs.')]
clean:
    git clean -fx '{{build_dir}}'
    rm -rf .sphinx/.doctrees
    rm -rf .sphinx/node_modules/
    rm -rf .sphinx/styles
    rm -rf .sphinx/vale.ini
    rm -rf reference/charmlibs
    rm -rf reference/generated

[doc('Run `pyright` for local sphinx extensions.')]
ext-static *pyrightargs:
    uvx --with-requirements=.sphinx/requirements.txt --with=pytest \
        pyright {{pyrightargs}} extensions

[doc('Run unit tests with `coverage` for local sphinx extensions.')]
ext-unit +flags='-rA':
    uvx --with-requirements=.sphinx/requirements.txt --with=pytest \
        coverage run --omit='test_*.py' -m pytest --tb=native -vv {{flags}} extensions
    uvx coverage report
