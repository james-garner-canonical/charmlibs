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

import _common
import _coverage
import add
import combine_coverage
import fast_lint
import functional
import init
import integration
import interfaces_json
import lint
import pack
import pytest
import scripts_unit
import static

# --- _common.uv_run_prefix ---------------------------------------------------------------------


def test_uv_run_prefix_without_lock(tmp_path):
    cmd = _common.uv_run_prefix(tmp_path, '3.11')
    assert cmd[:2] == ['uv', 'run']
    assert '--with-requirements' in cmd
    assert cmd[cmd.index('--python') + 1] == '3.11'
    assert '--locked' not in cmd
    assert '--group' not in cmd


def test_uv_run_prefix_with_lock_and_groups(tmp_path):
    (tmp_path / 'uv.lock').touch()
    cmd = _common.uv_run_prefix(tmp_path, '3.10', groups=['unit', 'lint'])
    assert '--locked' in cmd
    assert cmd.index('--locked') < cmd.index('--group')  # --locked precedes any group
    assert cmd.count('--group') == 2
    assert cmd[cmd.index('--group') + 1] == 'unit'


# --- _common.resolve_python --------------------------------------------------------------------


def test_resolve_python_falls_back_to_default():
    assert _common.resolve_python('pathops', None) == _common.DEFAULT_PYTHON
    assert _common.resolve_python('pathops', '') == _common.DEFAULT_PYTHON


def test_resolve_python_uses_explicit_value():
    assert _common.resolve_python('pathops', '3.13') == '3.13'


# --- _common.run -------------------------------------------------------------------------------


def test_run_returns_command_exit_code(tmp_path):
    assert _common.run(['true'], cwd=tmp_path) == 0
    assert _common.run(['false'], cwd=tmp_path) != 0


def test_run_check_exits_on_failure(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        _common.run(['false'], cwd=tmp_path, check=True)
    assert exc_info.value.code != 0


# --- _coverage.run_coverage --------------------------------------------------------------------


def test_run_coverage_builds_run_then_report(monkeypatch):
    calls = []

    def fake_run(cmd, *, cwd, env=None, check=False):
        calls.append(list(cmd))
        return 0

    monkeypatch.setattr(_common, 'uv_run_prefix', lambda *a, **k: ['PREFIX'])
    monkeypatch.setattr(_common, 'run', fake_run)
    assert _coverage.run_coverage('pathops', 'unit', '3.11', ['-x']) == 0
    assert len(calls) == 2
    run_cmd, report_cmd = calls
    assert run_cmd[:3] == ['PREFIX', 'coverage', 'run']
    assert '--data-file=.report/coverage-unit-3.11.db' in run_cmd
    assert '--source=src' in run_cmd
    assert '-x' in run_cmd
    assert run_cmd[-1] == 'tests/unit'
    assert report_cmd[:3] == ['PREFIX', 'coverage', 'report']
    assert '--data-file=.report/coverage-unit-3.11.db' in report_cmd


def test_run_coverage_skips_report_when_tests_fail(monkeypatch):
    calls = []

    def fake_run(cmd, *, cwd, env=None, check=False):
        calls.append(list(cmd))
        return 5

    monkeypatch.setattr(_common, 'uv_run_prefix', lambda *a, **k: ['PREFIX'])
    monkeypatch.setattr(_common, 'run', fake_run)
    assert _coverage.run_coverage('pathops', 'unit', '3.10', ['-rA']) == 5
    assert len(calls) == 1  # report step skipped, matching the old `set -e` behaviour


# --- combine_coverage.combine ------------------------------------------------------------------


def test_combine_uses_only_existing_data_files(monkeypatch, tmp_path):
    report = tmp_path / 'pkg' / '.report'
    report.mkdir(parents=True)
    (report / 'coverage-unit-3.10.db').touch()
    (report / 'coverage-juju-3.10.db').touch()
    # coverage-functional-3.10.db intentionally absent

    calls = []

    def fake_run(cmd, *, cwd, env=None, check=False):
        calls.append(list(cmd))
        return 0

    monkeypatch.setattr(_common, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(_common, 'uv_run_prefix', lambda *a, **k: ['PREFIX'])
    monkeypatch.setattr(_common, 'run', fake_run)
    combine_coverage.combine('pkg', '3.10')
    assert len(calls) == 4  # combine, xml, html, report
    combine_cmd = calls[0]
    assert '.report/coverage-unit-3.10.db' in combine_cmd
    assert '.report/coverage-juju-3.10.db' in combine_cmd
    assert '.report/coverage-functional-3.10.db' not in combine_cmd


# --- functional._main --------------------------------------------------------------------------


def test_functional_runs_coverage_through_wrapper(monkeypatch):
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


def _run_returning(codes):
    """Build a fake `_common.run` that returns the given exit codes in order, recording calls."""
    calls = []
    iterator = iter(codes)

    def fake_run(cmd, *, cwd, env=None, check=False):
        calls.append(list(cmd))
        return next(iterator)

    return fake_run, calls


def test_fast_lint_counts_check_and_format_failures(monkeypatch):
    # ruff check, ruff check --diff, ruff format --diff -> only check and format count.
    fake_run, calls = _run_returning([1, 0, 1])
    monkeypatch.setattr(_common, 'run', fake_run)
    assert fast_lint.fast_lint('pathops') == 2
    assert len(calls) == 3
    assert calls[0][-2:] == ['check', 'pathops']
    assert calls[1][-3:] == ['check', '--diff', 'pathops']
    assert calls[2][-3:] == ['format', '--diff', 'pathops']


def test_fast_lint_ignores_check_diff_exit_code(monkeypatch):
    # A non-zero `ruff check --diff` (the informational diff) must not count as a failure.
    fake_run, _calls = _run_returning([0, 1, 0])
    monkeypatch.setattr(_common, 'run', fake_run)
    assert fast_lint.fast_lint('pathops') == 0


# --- static.static -----------------------------------------------------------------------------


def test_static_builds_pyright_command(monkeypatch):
    captured = {}

    def fake_run(cmd, *, cwd, env=None, check=False):
        captured['cmd'] = list(cmd)
        captured['cwd'] = cwd
        return 0

    monkeypatch.setattr(_common, 'uv_run_prefix', lambda *a, **k: ['PREFIX'])
    monkeypatch.setattr(_common, 'run', fake_run)
    assert static.static('pathops', '3.11', ['--verifytypes']) == 0
    cmd = captured['cmd']
    assert cmd[0] == 'PREFIX'
    assert cmd[cmd.index('--with') + 1] == 'pytest-interface-tester'
    assert 'pyright' in cmd
    assert '--pythonversion=3.11' in cmd
    assert cmd[-1] == '--verifytypes'
    assert captured['cwd'] == _common.REPO_ROOT / 'pathops'


def test_static_requests_all_dependency_groups(monkeypatch):
    captured = {}

    def fake_prefix(package_dir, python, *, groups=()):
        captured['groups'] = list(groups)
        return ['PREFIX']

    monkeypatch.setattr(_common, 'uv_run_prefix', fake_prefix)
    monkeypatch.setattr(_common, 'run', lambda *a, **k: 0)
    static.static('pathops', '3.10', [])
    assert captured['groups'] == ['lint', 'unit', 'functional', 'integration']


# --- lint._main --------------------------------------------------------------------------------


def test_lint_sums_fast_lint_and_static_failures(monkeypatch):
    monkeypatch.setattr(fast_lint, 'fast_lint', lambda package: 2)
    monkeypatch.setattr(static, 'static', lambda package, python, args: 1)
    monkeypatch.setattr(sys, 'argv', ['lint.py', '--python', '3.10', 'pathops'])
    with pytest.raises(SystemExit) as exc_info:
        lint._main()
    assert exc_info.value.code == 3  # 2 from fast_lint + 1 because static failed


def test_lint_passes_when_both_succeed(monkeypatch):
    monkeypatch.setattr(fast_lint, 'fast_lint', lambda package: 0)
    monkeypatch.setattr(static, 'static', lambda package, python, args: 0)
    monkeypatch.setattr(sys, 'argv', ['lint.py', 'pathops'])
    with pytest.raises(SystemExit) as exc_info:
        lint._main()
    assert exc_info.value.code == 0


# --- add._main ---------------------------------------------------------------------------------


def test_add_runs_uv_add_with_constraints(monkeypatch):
    captured = {}

    def fake_run(cmd, *, cwd, env=None, check=False):
        captured['cmd'] = list(cmd)
        captured['cwd'] = cwd
        return 0

    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setattr(sys, 'argv', ['add.py', 'pathops', 'pydantic>=2'])
    with pytest.raises(SystemExit) as exc_info:
        add._main()
    assert exc_info.value.code == 0
    cmd = captured['cmd']
    assert cmd[:2] == ['uv', 'add']
    assert cmd[cmd.index('--constraints') + 1] == str(_common.TEST_REQUIREMENTS)
    assert cmd[-1] == 'pydantic>=2'
    assert captured['cwd'] == _common.REPO_ROOT / 'pathops'


# --- pack._main --------------------------------------------------------------------------------


def test_pack_runs_pack_script_with_substrate_env(monkeypatch):
    captured = {}

    def fake_run(cmd, *, cwd, env=None, check=False):
        captured['cmd'] = list(cmd)
        captured['cwd'] = cwd
        captured['env'] = env
        return 0

    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setattr(sys, 'argv', ['pack.py', '--substrate=k8s', '--tag=24.04', 'pathops'])
    with pytest.raises(SystemExit) as exc_info:
        pack._main()
    assert exc_info.value.code == 0
    assert captured['cmd'] == ['./pack.sh']
    assert captured['cwd'] == _common.REPO_ROOT / 'pathops' / 'tests' / 'integration'
    assert captured['env']['CHARMLIBS_SUBSTRATE'] == 'k8s'
    assert captured['env']['CHARMLIBS_TAG'] == '24.04'


def test_pack_tag_defaults_to_charmlibs_tag_env(monkeypatch):
    captured = {}

    def fake_run(cmd, *, cwd, env=None, check=False):
        captured['env'] = env
        return 0

    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setenv('CHARMLIBS_TAG', '22.04')
    monkeypatch.setattr(sys, 'argv', ['pack.py', '--substrate=k8s', 'pathops'])
    with pytest.raises(SystemExit):
        pack._main()
    assert captured['env']['CHARMLIBS_TAG'] == '22.04'  # taken from the env, not the (absent) flag


# --- integration._main -------------------------------------------------------------------------


def test_integration_selects_marker_for_substrate(monkeypatch):
    captured = {}

    def fake_run(cmd, *, cwd, env=None, check=False):
        captured['cmd'] = list(cmd)
        captured['cwd'] = cwd
        captured['env'] = env
        return 0

    monkeypatch.setattr(_common, 'uv_run_prefix', lambda *a, **k: ['PREFIX'])
    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setattr(sys, 'argv', ['integration.py', '--substrate=machine', 'pathops', '-x'])
    with pytest.raises(SystemExit) as exc_info:
        integration._main()
    assert exc_info.value.code == 0
    cmd = captured['cmd']
    assert cmd[cmd.index('-m') + 1] == 'not k8s_only'
    assert 'tests/integration' in cmd
    assert cmd[-1] == '-x'  # forwarded pytest arg comes after tests/integration
    assert captured['env']['CHARMLIBS_SUBSTRATE'] == 'machine'
    assert captured['cwd'] == _common.REPO_ROOT / 'pathops'


# --- scripts_unit._main ------------------------------------------------------------------------


def test_scripts_unit_runs_pytest_without_locked(monkeypatch):
    captured = {}

    def fake_run(cmd, *, cwd, env=None, check=False):
        captured['cmd'] = list(cmd)
        captured['cwd'] = cwd
        return 0

    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setattr(sys, 'argv', ['scripts_unit.py', '--python', '3.11'])
    with pytest.raises(SystemExit) as exc_info:
        scripts_unit._main()
    assert exc_info.value.code == 0
    cmd = captured['cmd']
    assert cmd[:2] == ['uv', 'run']
    assert '--locked' not in cmd  # not a package recipe, so no lockfile pinning
    assert '--group' not in cmd
    assert cmd[cmd.index('--python') + 1] == '3.11'
    assert '-rA' in cmd  # default pytest args
    assert cmd[-2:] == ['.scripts/tests', '.scripts/recipes/tests']
    assert captured['cwd'] == _common.REPO_ROOT


# --- interfaces_json._main ---------------------------------------------------------------------


def test_interfaces_json_redirects_ls_output_to_file(monkeypatch, tmp_path):
    (tmp_path / 'interfaces').mkdir()
    captured = {}

    def fake_run(cmd, *, cwd, env=None, check=False, stdout=None):
        captured['cmd'] = list(cmd)
        captured['cwd'] = cwd
        captured['stdout'] = stdout
        return 0

    monkeypatch.setattr(_common, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(_common, 'run', fake_run)
    monkeypatch.setattr(sys, 'argv', ['interfaces_json.py'])
    with pytest.raises(SystemExit) as exc_info:
        interfaces_json._main()
    assert exc_info.value.code == 0
    cmd = captured['cmd']
    assert cmd[:2] == ['.scripts/ls.py', 'interfaces']
    assert '--indent-json' in cmd
    assert cmd.count('--output') == 9
    assert captured['stdout'] is not None  # output redirected to the index file
    assert captured['cwd'] == tmp_path


# --- init._main --------------------------------------------------------------------------------


def test_init_prints_guidance_and_runs_cookiecutter(monkeypatch, tmp_path, capsys):
    captured = {}

    def fake_run(cmd, *, cwd, env=None, check=False):
        captured['cmd'] = list(cmd)
        captured['cwd'] = cwd
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
    assert captured['cwd'] == tmp_path
    printed = capsys.readouterr().out
    assert 'IMPORTANT' in printed
    assert 'charmlibs.' in printed
