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

"""Unit tests for the .scripts/recipes scripts.

These mock out `_common.run` (and the `uv run` prefix) so we can assert how each recipe builds its
command and handles control flow, without invoking `uv`, `pytest`, or `coverage`.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import _common
import _coverage
import _integration
import _pack
import add
import check
import fast_lint
import functional
import help as help_recipe  # aliased: `help` shadows a builtin
import init
import interfaces_json
import lint
import pytest
import scripts_unit
import static

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

# --- _common.uv_run ----------------------------------------------------------------------------


def test_uv_run_builds_prefix_without_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = {}

    def fake_run(cmd, *, cwd=None, env=None, check=False, stdout=None):
        captured['cmd'] = list(cmd)
        captured['cwd'] = cwd
        return 0

    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "pkg"\n')
    monkeypatch.setattr(_common, 'run', fake_run)
    _common.uv_run(['pyright'], pkg_dir=tmp_path, python='3.11')
    cmd = captured['cmd']
    assert cmd[:2] == ['uv', 'run']
    assert '--with-requirements' in cmd
    assert cmd[cmd.index('--python') + 1] == '3.11'
    assert '--locked' not in cmd
    assert '--group' not in cmd
    assert cmd[-1] == 'pyright'  # args appended after the prefix
    assert captured['cwd'] == tmp_path


def test_uv_run_adds_lock_and_groups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / 'uv.lock').touch()
    (tmp_path / 'pyproject.toml').write_text('[dependency-groups]\nunit = []\nlint = []\n')
    captured = {}

    def fake_run(cmd, *, cwd=None, env=None, check=False, stdout=None):
        captured['cmd'] = list(cmd)
        return 0

    monkeypatch.setattr(_common, 'run', fake_run)
    _common.uv_run([], pkg_dir=tmp_path, python='3.10', groups=['unit', 'lint'])
    cmd = captured['cmd']
    assert '--locked' in cmd
    assert cmd.index('--locked') < cmd.index('--group')  # --locked precedes any group
    assert cmd.count('--group') == 2
    assert cmd[cmd.index('--group') + 1] == 'unit'


def test_uv_run_skips_undeclared_groups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / 'pyproject.toml').write_text('[dependency-groups]\nunit = []\n')
    captured = {}

    def fake_run(cmd, *, cwd=None, env=None, check=False, stdout=None):
        captured['cmd'] = list(cmd)
        return 0

    monkeypatch.setattr(_common, 'run', fake_run)
    _common.uv_run([], pkg_dir=tmp_path, python='3.10', groups=['unit', 'lint'])
    cmd = captured['cmd']
    assert cmd.count('--group') == 1  # only the declared `unit` group is passed
    assert cmd[cmd.index('--group') + 1] == 'unit'
    assert 'lint' not in cmd


def test_uv_run_skips_groups_when_none_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "pkg"\n')
    captured = {}

    def fake_run(cmd, *, cwd=None, env=None, check=False, stdout=None):
        captured['cmd'] = list(cmd)
        return 0

    monkeypatch.setattr(_common, 'run', fake_run)
    _common.uv_run([], pkg_dir=tmp_path, python='3.10', groups=['unit', 'lint'])
    assert '--group' not in captured['cmd']


# --- _common.resolve_python --------------------------------------------------------------------


def test_resolve_python_floors_at_3_10() -> None:
    # pathops supports `>=3.10`, so the 3.10 floor applies.
    assert _common.resolve_python('pathops', None) == '3.10'
    assert _common.resolve_python('pathops', '') == '3.10'


def test_resolve_python_uses_explicit_value() -> None:
    assert _common.resolve_python('pathops', '3.13') == '3.13'


def test_resolve_python_uses_default_when_package_minimum_is_lower(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (pkg / 'pyproject.toml').write_text('[project]\nrequires-python = ">=3.8"\n')
    monkeypatch.setattr(_common, 'REPO_ROOT', tmp_path)
    assert _common.resolve_python('pkg', None) == '3.10'


def test_resolve_python_uses_package_minimum_when_higher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (pkg / 'pyproject.toml').write_text('[project]\nrequires-python = ">=3.12,<4"\n')
    monkeypatch.setattr(_common, 'REPO_ROOT', tmp_path)
    assert _common.resolve_python('pkg', None) == '3.12'


@pytest.mark.parametrize(
    ('requires_python', 'expected'),
    [
        ('>=3.12', '3.12'),  # simple lower bound
        ('>= 3.12', '3.12'),  # whitespace after the operator
        ('>=3.12.4', '3.12'),  # patch component dropped
        ('>=3.12,<4', '3.12'),  # upper bound ignored
        ('~=3.12', '3.12'),  # compatible-release operator
    ],
)
def test_resolve_python_parses_lower_bound(
    requires_python: str,
    expected: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (pkg / 'pyproject.toml').write_text(f'[project]\nrequires-python = "{requires_python}"\n')
    monkeypatch.setattr(_common, 'REPO_ROOT', tmp_path)
    assert _common.resolve_python('pkg', None) == expected


# --- _common.run -------------------------------------------------------------------------------


def test_run_returns_command_exit_code(tmp_path: Path) -> None:
    assert _common.run(['true'], cwd=tmp_path) == 0
    assert _common.run(['false'], cwd=tmp_path, check=False) != 0


def test_run_check_exits_on_failure(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        _common.run(['false'], cwd=tmp_path, check=True)
    assert exc_info.value.code != 0


# --- _coverage.run_coverage --------------------------------------------------------------------


def test_run_coverage_builds_run_then_report(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_uv_run(args, *, pkg_dir, python, groups=(), env=None, check=True, stdout=None):
        calls.append((list(args), list(groups)))
        return 0

    monkeypatch.setattr(_common, 'uv_run', fake_uv_run)
    _coverage.run_coverage('pathops', 'unit', '3.11', ['-x'])
    assert len(calls) == 2
    (run_args, run_groups), (report_args, _) = calls
    assert run_args[:2] == ['coverage', 'run']
    assert '--data-file=.report/coverage-unit-3.11.db' in run_args
    assert '--source=src' in run_args
    assert 'tests/unit' in run_args
    assert run_args[-1] == '-x'  # forwarded pytest args come after tests/<suite>
    assert run_groups == ['unit']  # the suite is requested as a dependency group
    assert report_args[:2] == ['coverage', 'report']
    assert '--data-file=.report/coverage-unit-3.11.db' in report_args


def test_run_coverage_skips_report_when_tests_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_uv_run(args, *, pkg_dir, python, groups=(), env=None, check=True, stdout=None):
        calls.append(list(args))
        if check:
            sys.exit(5)  # check=True aborts the process on the failing test run
        return 5

    monkeypatch.setattr(_common, 'uv_run', fake_uv_run)
    with pytest.raises(SystemExit) as exc_info:
        _coverage.run_coverage('pathops', 'unit', '3.10', ['-rA'])
    assert exc_info.value.code == 5
    assert len(calls) == 1  # report step skipped, matching the old `set -e` behaviour


# --- _coverage.combine -------------------------------------------------------------------------


def test_combine_uses_only_existing_data_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = tmp_path / 'pkg' / '.report'
    report.mkdir(parents=True)
    (report / 'coverage-unit-3.10.db').touch()
    (report / 'coverage-juju-3.10.db').touch()
    # coverage-functional-3.10.db intentionally absent

    calls = []

    def fake_uv_run(args, *, pkg_dir, python, groups=(), env=None, check=True, stdout=None):
        calls.append(list(args))
        return 0

    monkeypatch.setattr(_common, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(_common, 'uv_run', fake_uv_run)
    _coverage.combine('pkg', '3.10')
    assert len(calls) == 4  # combine, xml, html, report
    combine_args = calls[0]
    assert '.report/coverage-unit-3.10.db' in combine_args
    assert '.report/coverage-juju-3.10.db' in combine_args
    assert '.report/coverage-functional-3.10.db' not in combine_args


# --- functional._main --------------------------------------------------------------------------


def test_functional_runs_coverage_through_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_run(cmd, *, cwd, env=None, check=False):
        captured['cmd'] = list(cmd)
        captured['cwd'] = cwd
        return 0

    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setattr(sys, 'argv', ['functional.py', '--python', '3.12', 'pathops', '-k', 'foo'])
    with pytest.raises(SystemExit) as exc_info:
        functional._main()
    assert exc_info.value.code == 0
    cmd = captured['cmd']
    assert cmd[0].endswith('_functional.sh')
    assert cmd[1].endswith('_coverage.py')
    assert cmd[2] == 'pathops'
    assert cmd[3] == 'functional'
    assert cmd[cmd.index('--python') + 1] == '3.12'
    assert '-k' in cmd
    assert 'foo' in cmd
    assert captured['cwd'] == _common.REPO_ROOT / 'pathops'


# --- fast_lint.fast_lint -----------------------------------------------------------------------


def _run_returning(codes: Sequence[int]) -> tuple[Callable[..., int], list[list[str]]]:
    """Build a fake `_common.run` that returns the given exit codes in order, recording calls."""
    calls = []
    iterator = iter(codes)

    def fake_run(cmd, *, cwd=None, env=None, check=False, stdout=None):
        calls.append(list(cmd))
        return next(iterator)

    return fake_run, calls


def test_fast_lint_counts_check_and_format_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    # ruff check, ruff check --diff, ruff format --diff -> only check and format count.
    fake_run, calls = _run_returning([1, 0, 1])
    monkeypatch.setattr(_common, 'run', fake_run)
    assert fast_lint.fast_lint('pathops') == 2
    assert len(calls) == 3
    assert calls[0][-2:] == ['check', 'pathops']
    assert calls[1][-3:] == ['check', '--diff', 'pathops']
    assert calls[2][-3:] == ['format', '--diff', 'pathops']


def test_fast_lint_ignores_check_diff_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    # When `ruff check` fails, the informational `ruff check --diff` runs but its non-zero exit
    # code must not count as a second failure.
    fake_run, calls = _run_returning([1, 1, 0])
    monkeypatch.setattr(_common, 'run', fake_run)
    assert fast_lint.fast_lint('pathops') == 1
    assert len(calls) == 3
    assert calls[1][-3:] == ['check', '--diff', 'pathops']


def test_fast_lint_skips_check_diff_when_check_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    # `ruff check --diff` is only informative when `ruff check` failed, so skip it otherwise.
    fake_run, calls = _run_returning([0, 0])
    monkeypatch.setattr(_common, 'run', fake_run)
    assert fast_lint.fast_lint('pathops') == 0
    assert len(calls) == 2
    assert calls[0][-2:] == ['check', 'pathops']
    assert calls[1][-3:] == ['format', '--diff', 'pathops']


# --- static.static -----------------------------------------------------------------------------


def test_static_builds_pyright_command(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_uv_run(args, *, pkg_dir, python, groups=(), env=None, check=True, stdout=None):
        captured['args'] = list(args)
        captured['pkg_dir'] = pkg_dir
        return 0

    monkeypatch.setattr(_common, 'uv_run', fake_uv_run)
    assert static.static('pathops', '3.11', ['--verifytypes']) == 0
    args = captured['args']
    assert args[args.index('--with') + 1] == 'pytest-interface-tester'
    assert 'pyright' in args
    assert '--pythonversion=3.11' in args
    assert args[-1] == '--verifytypes'
    assert captured['pkg_dir'] == _common.REPO_ROOT / 'pathops'


def test_static_requests_all_dependency_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_uv_run(args, *, pkg_dir, python, groups=(), env=None, check=True, stdout=None):
        captured['groups'] = list(groups)
        return 0

    monkeypatch.setattr(_common, 'uv_run', fake_uv_run)
    static.static('pathops', '3.10', [])
    assert captured['groups'] == ['lint', 'unit', 'functional', 'integration']


# --- lint._main --------------------------------------------------------------------------------


def test_lint_sums_fast_lint_and_static_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fast_lint, 'fast_lint', lambda package: 2)
    monkeypatch.setattr(static, 'static', lambda package, python, args: 1)
    monkeypatch.setattr(sys, 'argv', ['lint.py', '--python', '3.10', 'pathops'])
    with pytest.raises(SystemExit) as exc_info:
        lint._main()
    assert exc_info.value.code == 3  # 2 from fast_lint + 1 because static failed


def test_lint_passes_when_both_succeed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fast_lint, 'fast_lint', lambda package: 0)
    monkeypatch.setattr(static, 'static', lambda package, python, args: 0)
    monkeypatch.setattr(sys, 'argv', ['lint.py', 'pathops'])
    with pytest.raises(SystemExit) as exc_info:
        lint._main()
    assert exc_info.value.code == 0


# --- add._main ---------------------------------------------------------------------------------


def test_add_runs_uv_add_with_constraints(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_run(cmd, *, cwd, env=None, check=False):
        captured['cmd'] = list(cmd)
        captured['cwd'] = cwd
        return 0

    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setattr(sys, 'argv', ['add.py', 'pathops', 'pydantic>=2'])
    add._main()
    cmd = captured['cmd']
    assert cmd[:2] == ['uv', 'add']
    assert cmd[cmd.index('--constraints') + 1] == _common.TEST_REQUIREMENTS
    assert cmd[-1] == 'pydantic>=2'
    assert captured['cwd'] == _common.REPO_ROOT / 'pathops'


# --- _pack.main --------------------------------------------------------------------------------


def test_pack_runs_pack_script_with_substrate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_run(cmd, *, cwd, env=None, check=False):
        captured['cmd'] = list(cmd)
        captured['cwd'] = cwd
        captured['env'] = env
        return 0

    monkeypatch.setattr(_common, 'run', fake_run)
    with pytest.raises(SystemExit) as exc_info:
        _pack.main(['--k8s', '--tag=24.04', 'pathops'])
    assert exc_info.value.code == 0
    assert captured['cmd'] == ['./pack.sh']
    assert captured['cwd'] == _common.REPO_ROOT / 'pathops' / 'tests' / 'integration'
    assert captured['env']['CHARMLIBS_SUBSTRATE'] == 'k8s'
    assert captured['env']['CHARMLIBS_TAG'] == '24.04'


def test_pack_tag_defaults_to_charmlibs_tag_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_run(cmd, *, cwd, env=None, check=False):
        captured['env'] = env
        return 0

    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setenv('CHARMLIBS_TAG', '22.04')
    with pytest.raises(SystemExit):
        _pack.main(['--machine', 'pathops'])
    assert captured['env']['CHARMLIBS_SUBSTRATE'] == 'machine'
    assert captured['env']['CHARMLIBS_TAG'] == '22.04'  # taken from the env, not the (absent) flag


def test_pack_requires_a_substrate() -> None:
    with pytest.raises(SystemExit) as exc_info:
        _pack.main(['pathops'])  # neither --k8s nor --machine
    assert exc_info.value.code == 2  # argparse usage error


# --- _integration.main -------------------------------------------------------------------------


def test_integration_selects_marker_for_substrate(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_uv_run(args, *, pkg_dir, python, groups=(), env=None, check=True, stdout=None):
        captured['args'] = list(args)
        captured['pkg_dir'] = pkg_dir
        captured['env'] = env
        return 0

    monkeypatch.setattr(_common, 'uv_run', fake_uv_run)
    with pytest.raises(SystemExit) as exc_info:
        _integration.main(['--machine', 'pathops', '-x'])
    assert exc_info.value.code == 0
    args = captured['args']
    assert args[args.index('-m') + 1] == 'not k8s_only'
    assert 'tests/integration' in args
    assert args[-1] == '-x'  # forwarded pytest arg comes after tests/integration
    assert captured['env']['CHARMLIBS_SUBSTRATE'] == 'machine'
    assert captured['pkg_dir'] == _common.REPO_ROOT / 'pathops'


# --- scripts_unit._main ------------------------------------------------------------------------


def test_scripts_unit_runs_pytest_without_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_run(cmd, *, cwd=None, env=None, check=False, stdout=None):
        captured['cmd'] = list(cmd)
        return 0

    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setattr(sys, 'argv', ['scripts_unit.py'])
    scripts_unit._main()
    cmd = captured['cmd']
    assert cmd[:2] == ['uv', 'run']
    assert '--locked' not in cmd  # not a package recipe, so no lockfile pinning
    assert '--group' not in cmd
    assert cmd[cmd.index('--python') + 1] == '3.12'
    # test dirs precede the forwarded pytest args, which default to `-rA`
    assert cmd[-3:] == ['.scripts/tests', '.scripts/recipes/tests', '-rA']


# --- interfaces_json._main ---------------------------------------------------------------------


def test_interfaces_json_redirects_ls_output_to_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / 'interfaces').mkdir()
    captured = {}

    def fake_run(cmd, *, cwd=None, env=None, check=False, stdout=None):
        captured['cmd'] = list(cmd)
        captured['stdout'] = stdout
        return 0

    monkeypatch.setattr(_common, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setattr(sys, 'argv', ['interfaces_json.py'])
    interfaces_json._main()
    cmd = captured['cmd']
    assert cmd[:2] == ['.scripts/ls.py', 'interfaces']
    assert '--indent-json' in cmd
    assert cmd.count('--output') == 9
    assert captured['stdout'] is not None  # output redirected to the index file


# --- init._main --------------------------------------------------------------------------------


def test_init_prints_guidance_and_runs_cookiecutter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    captured = {}

    def fake_run(cmd, *, cwd=None, env=None, check=False, stdout=None):
        captured['cmd'] = list(cmd)
        captured['env'] = env
        return 0

    monkeypatch.setattr(_common, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setattr(sys, 'argv', ['init.py', '--no-input'])
    with pytest.raises(SystemExit) as exc_info:
        init._main()
    assert exc_info.value.code == 0
    cmd = captured['cmd']
    assert cmd[:3] == ['uvx', 'cookiecutter', '.template']
    assert cmd[-1] == '--no-input'  # forwarded to cookiecutter
    assert captured['env']['CHARMLIBS_TEMPLATE'] == str((tmp_path / '.template').resolve())
    printed = capsys.readouterr().out
    assert 'IMPORTANT' in printed
    assert 'charmlibs.' in printed


# --- help._summary / help._recipes -------------------------------------------------------------


def test_help_summary_reads_first_docstring_line(tmp_path: Path) -> None:
    script = tmp_path / 'foo.py'
    script.write_text('"""Do the foo thing.\n\nMore detail here.\n"""\n')
    assert help_recipe._summary(script) == 'Do the foo thing.'


def test_help_recipes_map_names_to_scripts_in_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recipes_dir = tmp_path / '.scripts' / 'recipes'
    recipes_dir.mkdir(parents=True)
    (recipes_dir / 'foo.py').write_text('"""Do the foo thing."""\n')
    (recipes_dir / 'pack_k8s.py').write_text('"""Pack it for k8s."""\n')
    (tmp_path / 'justfile').write_text(
        'set positional-arguments\n\n'
        '_short_help:\n    @echo hi\n\n'
        'foo *args:\n    @.scripts/recipes/foo.py "$@"\n\n'
        'pack-k8s *args:\n    @.scripts/recipes/pack_k8s.py "$@"\n'
    )
    monkeypatch.setattr(_common, 'REPO_ROOT', tmp_path)
    assert list(help_recipe._recipes()) == [
        ('foo', 'Do the foo thing.'),  # private `_short_help` is skipped
        ('pack-k8s', 'Pack it for k8s.'),  # hyphen -> underscore maps the name to its script
    ]


# --- check._main -------------------------------------------------------------------------------


def test_check_runs_lint_unit_docs_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None, env=None, check=True, stdout=None):
        calls.append(list(cmd))
        return 0

    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setattr(sys, 'argv', ['check.py', 'pathops'])
    check._main()
    assert len(calls) == 3
    assert str(calls[0][0]).endswith('lint.py') and calls[0][1] == 'pathops'
    assert str(calls[1][0]).endswith('unit.py') and calls[1][1] == 'pathops'
    assert calls[2] == ['just', 'docs', 'html', 'pathops']  # docs not yet migrated


def test_check_fails_fast_on_first_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None, env=None, check=True, stdout=None):
        calls.append(list(cmd))
        if check:
            sys.exit(1)  # the first step (lint) fails and run aborts
        return 1

    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setattr(sys, 'argv', ['check.py', 'pathops'])
    with pytest.raises(SystemExit) as exc_info:
        check._main()
    assert exc_info.value.code == 1
    assert len(calls) == 1  # stopped after lint failed, never ran unit or docs


def test_check_forwards_python_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(cmd, *, cwd=None, env=None, check=True, stdout=None):
        calls.append(list(cmd))
        return 0

    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setattr(sys, 'argv', ['check.py', 'pathops', '--python', '3.11'])
    check._main()
    assert calls[0][-2:] == ['--python', '3.11']  # forwarded to lint
    assert calls[1][-2:] == ['--python', '3.11']  # forwarded to unit
