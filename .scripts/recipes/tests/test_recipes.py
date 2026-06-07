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
import combine_coverage
import functional
import pytest

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
