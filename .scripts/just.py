#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

# ruff: noqa: I001  # tomllib is first-party in 3.11+

# Copyright 2025 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Single-file implementation of every charmlibs `just` recipe.

Usage: `.scripts/just.py <recipe> [args...]`. Each recipe mirrors the matching script in
`.scripts/recipes/`; this file exists to compare the one-script-per-recipe layout against a
single dispatcher. Run `.scripts/just.py help` to list the available recipes.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import IO

# `.scripts/just.py` -> repo root is two parents up.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST_REQUIREMENTS = REPO_ROOT / 'test-requirements.txt'
COVERAGE_RCFILE = REPO_ROOT / 'pyproject.toml'

# Lower bound of a `requires-python` specifier (see `_requires_python_minimum`).
_REQUIRES_PYTHON_LOWER_BOUND = re.compile(
    r'(?:>=|~=)'  # a `>=` or `~=` operator: the ones that set a lower bound
    r'\s*'  # optional whitespace between the operator and the version
    r'(\d+\.\d+)'  # capture just `major.minor`, stopping before any patch component
)

# Each integration substrate skips the tests marked as only applying to the other substrate.
_INTEGRATION_LABELS = {'k8s': 'not machine_only', 'machine': 'not k8s_only'}

# Source a package's functional test setup.sh/teardown.sh around the test command, mirroring
# `.scripts/recipes/_functional.sh`. The command is substituted in place of `@@COMMAND@@`.
_FUNCTIONAL_WRAPPER = """\
set -xueo pipefail
if [ -e tests/functional/setup.sh ]; then
    source ./tests/functional/setup.sh
fi
set +e  # Allow the command to fail.
@@COMMAND@@
returncode=$?
set -e  # Exit on error again.
if [ -e tests/functional/teardown.sh ]; then
    source ./tests/functional/teardown.sh
fi
exit "$returncode"
"""

_BOLD = '\033[1m'
_NORMAL = '\033[0m'
_CYAN = '\033[36m'


# --- Shared helpers ------------------------------------------------------------------------------


def _package_parser(description: str | None) -> argparse.ArgumentParser:
    """Return an `ArgumentParser` with the common `--python` and `package` arguments."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--python', default=None)
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    return parser


def _resolve_python(package: str, python: str | None) -> str:
    """Return the Python version to test `package` with.

    If `python` is `None`, return the higher of 3.10 and the package's minimum Python version.
    """
    if python:
        return python
    minimum = _requires_python_minimum(REPO_ROOT / package)
    return max('3.10', minimum, key=lambda s: tuple(int(p) for p in s.split('.')))


def _run(
    cmd: Sequence[str | pathlib.Path],
    *,
    cwd: pathlib.Path = REPO_ROOT,
    env: dict[str, str] | None = None,
    check: bool = True,
    stdout: IO[str] | None = None,
) -> int:
    """Echo and run a command, returning its exit code."""
    env = dict(os.environ if env is None else env)
    env.pop('VIRTUAL_ENV', None)  # Don't propagate script's ephemeral venv.
    print([str(part) for part in cmd], file=sys.stderr, flush=True)
    returncode = subprocess.call(cmd, cwd=cwd, env=env, stdout=stdout)
    if check and returncode != 0:
        sys.exit(returncode)
    return returncode


def _uv_cmd(
    args: Sequence[str | pathlib.Path],
    *,
    pkg_dir: pathlib.Path,
    python: str,
    groups: Sequence[str] = (),
) -> list[str | pathlib.Path]:
    """Build a `uv run ... <args>` command list to be executed in `pkg_dir`."""
    cmd: list[str | pathlib.Path] = [
        'uv',
        'run',
        '--with-requirements',
        TEST_REQUIREMENTS,
        '--python',
        python,
    ]
    if (pkg_dir / 'uv.lock').exists():
        cmd.append('--locked')
    available = _dependency_groups(pkg_dir)
    for group in groups:
        if group in available:
            cmd.extend(['--group', group])
    return [*cmd, *args]


def _uv_run(
    args: Sequence[str | pathlib.Path],
    *,
    pkg_dir: pathlib.Path,
    python: str,
    groups: Sequence[str] = (),
    env: dict[str, str] | None = None,
    check: bool = True,
    stdout: IO[str] | None = None,
) -> int:
    """Run `uv run ... <args>` in `pkg_dir`, returning the exit code."""
    cmd = _uv_cmd(args, pkg_dir=pkg_dir, python=python, groups=groups)
    return _run(cmd, cwd=pkg_dir, env=env, check=check, stdout=stdout)


def _dependency_groups(pkg_dir: pathlib.Path) -> set[str]:
    """Return the PEP 735 dependency group names declared in `pyproject.toml`."""
    pyproject_toml = tomllib.loads((pkg_dir / 'pyproject.toml').read_text())
    return set(pyproject_toml.get('dependency-groups', ()))


def _requires_python_minimum(pkg_dir: pathlib.Path) -> str:
    """Return the `major.minor` lower bound of `pkg_dir`'s `requires-python`, e.g. `'3.10'`."""
    pyproject_toml = tomllib.loads((pkg_dir / 'pyproject.toml').read_text())
    requires_python = pyproject_toml.get('project', {})['requires-python']
    match = _REQUIRES_PYTHON_LOWER_BOUND.search(requires_python)
    assert match is not None
    return match.group(1)


def _coverage_env() -> dict[str, str]:
    """Return the environment with `COVERAGE_RCFILE` pointing at the repo `pyproject.toml`."""
    return {**os.environ, 'COVERAGE_RCFILE': str(COVERAGE_RCFILE)}


def _run_coverage(
    package: str, suite: str, python: str, pytest_args: list[str], *, functional: bool = False
) -> None:
    """Run `coverage run -m pytest` then `coverage report` for a package's test suite.

    When `functional` is set, the commands are wrapped so that the package's
    `tests/functional/setup.sh` and `teardown.sh` are sourced around them.
    """
    pkg_dir = REPO_ROOT / package
    data_file_arg = f'--data-file=.report/coverage-{suite}-{python}.db'
    run_cmd = _uv_cmd(
        [
            *('coverage', 'run', data_file_arg, '--source=src', '-m'),
            *('pytest', '--tb=native', '-vv', f'tests/{suite}', *pytest_args),
        ],
        pkg_dir=pkg_dir,
        python=python,
        groups=[suite],
    )
    report_cmd = _uv_cmd(
        ['coverage', 'report', data_file_arg], pkg_dir=pkg_dir, python=python, groups=[suite]
    )
    if functional:
        joined = f'{_shlex_join(run_cmd)} && {_shlex_join(report_cmd)}'
        script = _FUNCTIONAL_WRAPPER.replace('@@COMMAND@@', joined)
        _run(['bash', '-c', script], cwd=pkg_dir, env=_coverage_env())
    else:
        _run(run_cmd, cwd=pkg_dir, env=_coverage_env())
        _run(report_cmd, cwd=pkg_dir, env=_coverage_env())


def _shlex_join(cmd: Sequence[str | pathlib.Path]) -> str:
    """Quote and join a command list into a single shell-safe string."""
    return shlex.join(str(part) for part in cmd)


def _fast_lint(path: str) -> int:
    """Run `ruff check` and `ruff format --diff`, returning the number of failing commands.

    The `ruff check --diff` output (the fixes that would resolve `ruff check` issues) is printed
    for information, but never counts as a failure.
    """
    ruff = ['uv', 'run', '--only-group=fast-lint', 'ruff']
    failures = 0
    if _run([*ruff, 'check', path], check=False) != 0:
        _run([*ruff, 'check', '--diff', path], check=False)
        failures += 1
    if _run([*ruff, 'format', '--diff', path], check=False) != 0:
        failures += 1
    return failures


def _static_check(package: str, python: str, pyright_args: Sequence[str]) -> int:
    """Run `pyright` for a package against the given Python version, returning its exit code."""
    return _uv_run(
        [
            *('--with', 'pytest-interface-tester'),
            *('pyright', f'--pythonversion={python}', *pyright_args),
        ],
        pkg_dir=REPO_ROOT / package,
        python=python,
        groups=['lint', 'unit', 'functional', 'integration'],
        check=False,
    )


# --- Recipes -------------------------------------------------------------------------------------


def help_(argv: list[str]) -> int:
    """Describe usage and list the available recipes."""
    argparse.ArgumentParser(description=help_.__doc__).parse_args(argv)
    print('All recipes require `uv` to be available.\n')
    print('Available recipes:')
    width = max(len(name) for name in RECIPES)
    for name, func in RECIPES.items():
        summary = (func.__doc__ or '').splitlines()[0] if func.__doc__ else ''
        print(f'    {name:<{width}}  {summary}')
    return 0


def init(argv: list[str]) -> int:
    """Scaffold a new charmlibs package interactively (forwards extra args to cookiecutter)."""
    parser = argparse.ArgumentParser(description=init.__doc__)
    parser.add_argument(
        '--interface',
        action='store_true',
        help='Scaffold a charmlibs.interfaces package instead of a general charmlibs package.',
    )
    args, cookiecutter_args = parser.parse_known_args(argv)
    if args.interface:
        print(
            f'✨{_BOLD}IMPORTANT{_NORMAL}✨ The project name should be the canonical interface'
            f' name, as used in {_CYAN}charmcraft.yaml{_NORMAL} files.'
        )
    else:
        print(
            f'✨{_BOLD}IMPORTANT{_NORMAL}✨ The project name should be the import package name,'
            f' without the {_CYAN}charmlibs.{_NORMAL} namespace.'
        )
    print('You can press enter to accept the default, shown in brackets.')
    template = REPO_ROOT / '.template'
    cmd = ['uvx', 'cookiecutter']
    if args.interface:
        cmd.extend(['--output-dir', 'interfaces'])
    cmd.append(template.name)
    if args.interface:
        cmd.append('_interface=True')
    cmd.extend(cookiecutter_args)
    _run(cmd, env={**os.environ, 'CHARMLIBS_TEMPLATE': str(template.resolve())})
    return 0


def fast_lint(argv: list[str]) -> int:
    """Run `ruff`, failing afterwards if any errors are found."""
    parser = argparse.ArgumentParser(description=fast_lint.__doc__)
    parser.add_argument('path', nargs='?', default='.', help='Path to lint, defaults to the repo.')
    args = parser.parse_args(argv)
    return _fast_lint(args.path)


def check(argv: list[str]) -> int:
    """`lint`, `unit` test, and build the `docs` for a package."""
    args = _package_parser(check.__doc__).parse_args(argv)
    python = _resolve_python(args.package, args.python)
    failures = lint([args.package, '--python', python])
    if failures:
        sys.exit(failures)
    _run_coverage(args.package, 'unit', python, ['-rA'])
    _run(['just', 'docs', 'html', args.package])
    return 0


def format_(argv: list[str]) -> int:
    """Run `ruff check --fix` and `ruff format`, modifying files in place."""
    parser = argparse.ArgumentParser(description=format_.__doc__)
    parser.add_argument(
        'path', nargs='?', default='.', help='Path to format, defaults to the repo.'
    )
    args = parser.parse_args(argv)
    ruff = ['uv', 'run', '--only-group=fast-lint', 'ruff']
    _run([*ruff, 'format', args.path])
    _run([*ruff, 'check', '--fix', args.path])
    return 0


def add(argv: list[str]) -> int:
    """Run `uv add` for a package, respecting repo-level version constraints.

    Example: `add pathops 'pydantic>=2'` adds a constrained dependency to pathops.
    """
    parser = argparse.ArgumentParser(description=add.__doc__)
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    args, uv_args = parser.parse_known_args(argv)
    cmd = ['uv', 'add', '--constraints', TEST_REQUIREMENTS, *uv_args]
    _run(cmd, cwd=REPO_ROOT / args.package)
    return 0


def lint(argv: list[str]) -> int:
    """Run linting (`ruff`) and static analysis (`pyright`) for a package."""
    args, pyright_args = _package_parser(lint.__doc__).parse_known_args(argv)
    python = _resolve_python(args.package, args.python)
    failures = _fast_lint(args.package)
    if _static_check(args.package, python, pyright_args) != 0:
        failures += 1
    return failures


def static(argv: list[str]) -> int:
    """Run `pyright` static analysis for a package."""
    args, pyright_args = _package_parser(static.__doc__).parse_known_args(argv)
    python = _resolve_python(args.package, args.python)
    return _static_check(args.package, python, pyright_args)


def unit(argv: list[str]) -> int:
    """Run unit tests with `coverage` for a package."""
    args, pytest_args = _package_parser(unit.__doc__).parse_known_args(argv)
    python = _resolve_python(args.package, args.python)
    _run_coverage(args.package, 'unit', python, pytest_args or ['-rA'])
    return 0


def functional(argv: list[str]) -> int:
    """Run functional tests with `coverage` for a package."""
    args, pytest_args = _package_parser(functional.__doc__).parse_known_args(argv)
    python = _resolve_python(args.package, args.python)
    _run_coverage(args.package, 'functional', python, pytest_args or ['-rA'], functional=True)
    return 0


def combine_coverage(argv: list[str]) -> int:
    """Combine a package's `coverage` reports."""
    args = _package_parser(combine_coverage.__doc__).parse_args(argv)
    python = _resolve_python(args.package, args.python)
    pkg_dir = REPO_ROOT / args.package
    data_files = [
        f
        for test_id in ('unit', 'functional', 'juju')
        if (pkg_dir / (f := f'.report/coverage-{test_id}-{python}.db')).exists()
    ]

    def uv(cmd: list[str]) -> None:
        _uv_run(cmd, pkg_dir=pkg_dir, python=python, env=_coverage_env())

    # Combine reports and generate XML.
    data_file_arg = f'--data-file=.report/coverage-all-{python}.db'
    uv(['coverage', 'combine', '--keep', data_file_arg, *data_files])
    uv(['coverage', 'xml', data_file_arg, '-o', f'.report/coverage-all-{python}.xml'])
    # Rebuild the HTML report from scratch (let coverage recreate the directory).
    html_dir = f'.report/htmlcov-all-{python}'
    shutil.rmtree(pkg_dir / html_dir, ignore_errors=True)
    uv(['coverage', 'html', data_file_arg, '--show-contexts', f'--directory={html_dir}'])
    # Print the report last.
    uv(['coverage', 'report', data_file_arg])
    return 0


def _pack(substrate: str, argv: list[str]) -> int:
    """Pack the package's integration-test charm(s) for the given substrate."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--tag',
        default=os.environ.get('CHARMLIBS_TAG', ''),
        help='Value for the CHARMLIBS_TAG environment var (defaults to $CHARMLIBS_TAG).',
    )
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    args, pack_args = parser.parse_known_args(argv)
    integration_dir = REPO_ROOT / args.package / 'tests' / 'integration'
    env = {**os.environ, 'CHARMLIBS_SUBSTRATE': substrate, 'CHARMLIBS_TAG': args.tag}
    return _run(['./pack.sh', *pack_args], cwd=integration_dir, env=env)


def pack_k8s(argv: list[str]) -> int:
    """Pack Kubernetes charm(s) for a package's Juju integration tests."""
    return _pack('k8s', argv)


def pack_machine(argv: list[str]) -> int:
    """Pack machine charm(s) for a package's Juju integration tests."""
    return _pack('machine', argv)


def _integration(substrate: str, argv: list[str]) -> int:
    """Run the package's Juju integration tests for the given substrate."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--tag',
        default=os.environ.get('CHARMLIBS_TAG', ''),
        help='Value for the CHARMLIBS_TAG environment var (defaults to $CHARMLIBS_TAG).',
    )
    parser.add_argument('--python', default=None)
    parser.add_argument('package', help='Path from the repo root to the package, e.g. `pathops`.')
    args, pytest_args = parser.parse_known_args(argv)
    python = _resolve_python(args.package, args.python)
    pkg_dir = REPO_ROOT / args.package
    env = {**os.environ, 'CHARMLIBS_SUBSTRATE': substrate, 'CHARMLIBS_TAG': args.tag}
    cmd = [
        *('pytest', '--tb=native', '-vv'),
        *('-m', _INTEGRATION_LABELS[substrate]),
        'tests/integration',
        *(pytest_args or ['-rA']),
    ]
    return _uv_run(cmd, pkg_dir=pkg_dir, python=python, groups=['integration'], env=env)


def integration_k8s(argv: list[str]) -> int:
    """Run a package's Kubernetes Juju integration tests."""
    return _integration('k8s', argv)


def integration_machine(argv: list[str]) -> int:
    """Run a package's machine Juju integration tests."""
    return _integration('machine', argv)


def interfaces_json(argv: list[str]) -> int:
    """Generate `interfaces/index.json` from the interface libraries."""
    argparse.ArgumentParser(description=interfaces_json.__doc__).parse_args(argv)  # supports `-h`
    outputs = [
        'name',
        'version',
        'lib',
        'lib_url',
        'docs_url',
        'summary',
        'description',
        'tags',
        'status',
    ]
    cmd: list[str | pathlib.Path] = ['.scripts/ls.py', 'interfaces', '--indent-json']
    for output in outputs:
        cmd.extend(['--output', output])
    with (REPO_ROOT / 'interfaces' / 'index.json').open('w') as f:
        _run(cmd, stdout=f)
    return 0


def scripts_unit(argv: list[str]) -> int:
    """Run the unit tests for the repository tooling in `.scripts/`."""
    tests = ('.scripts/tests', '.scripts/recipes/tests')
    _run([
        *('uv', 'run', '--with-requirements', TEST_REQUIREMENTS, '--python', '3.12'),
        *('pytest', '--tb=native', '-vv', *tests, *(argv or ['-rA'])),
    ])
    return 0


# Recipe name (as in the justfile) -> handler. Order matches the justfile, which `help` mirrors.
RECIPES: dict[str, Callable[[list[str]], int]] = {
    'help': help_,
    'init': init,
    'fast-lint': fast_lint,
    'check': check,
    'format': format_,
    'add': add,
    'lint': lint,
    'static': static,
    'unit': unit,
    'functional': functional,
    'combine-coverage': combine_coverage,
    'pack-k8s': pack_k8s,
    'pack-machine': pack_machine,
    'integration-k8s': integration_k8s,
    'integration-machine': integration_machine,
    'interfaces-json': interfaces_json,
    'scripts-unit': scripts_unit,
}


def main(argv: list[str]) -> int:
    """Dispatch `argv` to the named recipe, returning its exit code."""
    if not argv or argv[0] in ('-h', '--help'):
        return help_([])
    name, *rest = argv
    func = RECIPES.get(name)
    if func is None:
        print(f'Unknown recipe: {name!r}\n', file=sys.stderr)
        help_([])
        return 2
    return func(rest)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
