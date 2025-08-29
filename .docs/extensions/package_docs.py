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

"""Generate automodule files and table of contents for packages."""

from __future__ import annotations

import pathlib
import shutil
import typing

####################
# Sphinx extension #
####################

if typing.TYPE_CHECKING:
    import sphinx.application

COMBINE_DOCS = '__combine__'


def setup(app: sphinx.application.Sphinx) -> dict[str, str | bool]:
    """Entrypoint for Sphinx extensions, connects generation code to Sphinx event."""
    app.connect('builder-inited', _builder_inited)
    app.connect('build-finished', _build_finished)
    app.add_config_value('package', default=None, rebuild='')
    print('setup')
    return {'version': '1.0.0', 'parallel_read_safe': False, 'parallel_write_safe': False}


def _builder_inited(app: sphinx.application.Sphinx) -> None:
    print('builder-inited start')
    _package_docs_rst(docs_dir=pathlib.Path(app.confdir), package=app.config.package)
    print('builder-inited end')


def _build_finished(app: sphinx.application.Sphinx, exception: Exception | None) -> None:
    print('build-finished start')
    if exception:
        print(exception)
        return
    _package_docs_html(build_dir=pathlib.Path(app.outdir), package=app.config.package)
    print('build-finished end')


########################
# rst generation logic #
########################

PACKAGE_DOCS_TEMPLATE = """
.. raw:: html

   <style>
      h1:before {{
         content: "{prefix}";
      }}
   </style>

{package}
{underline}
""".strip()
AUTOMODULE_SUFFIX_TEMPLATE = """

.. automodule:: {package}
""".rstrip()


def _package_docs_rst(docs_dir: pathlib.Path, package: str | None) -> None:
    if package == COMBINE_DOCS:
        return
    _generate_rst_files(docs_dir, exclude='interfaces', automodule_package=package)
    _generate_rst_files(docs_dir, subdir='interfaces', automodule_package=package)


def _generate_rst_files(
    docs_dir: pathlib.Path,
    subdir: str = '.',
    exclude: str | None = None,
    automodule_package: str | None = None,
) -> None:
    generated_dir = docs_dir / 'reference' / 'charmlibs' / subdir
    generated_dir.mkdir(exist_ok=True)
    # Any directory starting with a-z is assumed to be a package (except the interfaces directory)
    root = docs_dir.parent
    package_dir_names = sorted(
        path.name
        for path in (root / subdir).glob(r'[a-z]*')
        if path.is_dir() and path.name != exclude
    )
    for package_dir_name in package_dir_names:
        prefix = 'charmlibs.' if subdir == '.' else f'charmlibs.{subdir}.'
        package = package_dir_name.replace('-', '_')
        content = PACKAGE_DOCS_TEMPLATE.format(
            prefix=prefix, package=package, underline='=' * len(package)
        )
        if (root / subdir / package_dir_name) == root / automodule_package:
            content += AUTOMODULE_SUFFIX_TEMPLATE.format(package=package)
        _write_if_needed(path=generated_dir / f'{package}.rst', content=content)


def _write_if_needed(path: pathlib.Path, content: str) -> None:
    """Write to path only if contents are different.

    This allows sphinx-build to skip rebuilding pages that depend on the output of this extension
    if the output hasn't actually changed.
    """
    if not path.exists() or path.read_text() != content:
        path.write_text(content)


#######################
# html snapshot logic #
#######################


def _package_docs_html(build_dir: pathlib.Path, package: str | None) -> None:
    if package is None:
        return
    if package == COMBINE_DOCS:
        _combine_html(build_dir)
    else:
        _snapshot_html(build_dir, package)


def _snapshot_html(build_dir: pathlib.Path, package: str) -> None:
    html_dir = build_dir / 'reference' / 'charmlibs' / package
    snapshot_dir = build_dir / '_snapshot' / html_dir.relative_to(build_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(html_dir / 'index.html', snapshot_dir)


def _combine_html(build_dir: pathlib.Path) -> None:
    snapshot_dir = build_dir / '_snapshot'
    for dir_path, _, filenames in snapshot_dir.walk():
        for filename in filenames:
            src = dir_path / filename
            dst = build_dir / dir_path.relative_to(snapshot_dir) / filename
            shutil.copy(src, dst)
