# Agent instructions for charmlibs

## Overview

`charmlibs` is a monorepo of Python libraries for Juju charms.

**Key concepts:**

- **Juju** — Canonical's open-source orchestration engine. Deploys and manages applications on Kubernetes and bare-metal/VM clouds.
- **Charm** — a Python program that uses the [ops](https://documentation.ubuntu.com/ops/) framework to respond to Juju lifecycle events and manage a workload. Charms can be Kubernetes-based (using [Pebble](https://documentation.ubuntu.com/pebble/) to manage container processes) or machine-based.
- **Juju relation** — a named connection between two charms, backed by shared key-value stores called *databags*. Relations are how charms communicate and exchange structured configuration.
- **Charm library** — a reusable Python package that charm authors import. All libraries in this repo are distributed as Python packages on PyPI (not Charmhub-hosted single-file modules, which are a legacy distribution method).

**Two library categories:**

| Category | Namespace | Example package | Import |
|----------|-----------|-----------------|--------|
| General | `charmlibs` | `charmlibs-pathops` | `from charmlibs import pathops` |
| Interface | `charmlibs.interfaces` | `charmlibs-interfaces-tls-certificates` | `from charmlibs.interfaces import tls_certificates` |

General libraries live at the repo root (e.g. `pathops/`). Interface libraries live under `interfaces/` (for example, `interfaces/tls-certificates/`).

## Repo structure

```
charmlibs/
├── <library>/              # One directory per general library (e.g. pathops/, apt/, snap/)
│   ├── src/charmlibs/<library>/   # Source (namespace package)
│   ├── tests/
│   │   ├── unit/
│   │   ├── functional/     # Optional; omit directory to skip
│   │   └── integration/    # Optional; Juju-based tests
│   ├── pyproject.toml
│   ├── uv.lock             # Commit this
│   ├── README.md
│   └── CHANGELOG.md
├── interfaces/             # Interface libraries
│   └── <interface>/        # Named exactly as in charmcraft.yaml (e.g. tls-certificates)
│       ├── src/charmlibs/interfaces/<interface>/
│       ├── testing/        # Optional testing subpackage for charm unit tests
│       ├── pyproject.toml
│       └── ...
├── .docs/                  # Sphinx source for documentation.ubuntu.com/charmlibs
├── .template/              # Cookiecutter template used by `just init`
├── .github/workflows/      # CI: ci.yaml, test-package.yaml, test-interface.yaml, publish.yaml
├── justfile                # Task runner recipes
├── docs.just               # Docs-specific recipes
├── interface.just          # Interface-specific recipes
├── pyproject.toml          # Repo-level config: ruff, coverage, shared linting settings
└── test-requirements.txt   # Pinned versions of pytest, coverage, and other test tools
```

## Development workflow

### Prerequisites

`uv` and `just` are required. Verify they're available before proceeding:

```bash
uv --version && just --version
```

If either is missing, they can be installed like this:

```bash
sudo snap install --classic astral-uv   # installs uv
uv tool install rust-just               # installs just (once uv is available)
```

Run `just` or `just help` from anywhere in the repo to see all available commands. All `just` commands execute from the repo root regardless of where they're invoked.

### Inner loop

The command you'll run most often is:

```bash
just check <package>
```

This runs `just lint <package>`, `just unit <package>`, and `just docs html <package>`. **Run this before every commit on the affected package.**

The `<package>` argument is the path from the repo root, e.g. `pathops` or `interfaces/tls-certificates`.

### Command reference

| Command | Description |
|---------|-------------|
| `just check <package>` | Lint + unit tests + docs (the standard pre-commit check) |
| `just lint <package>` | ruff + codespell + pyright |
| `just fast-lint [path]` | ruff only, across the whole repo or a specific path |
| `just format [package]` | Auto-fix ruff and formatting errors |
| `just static <package>` | pyright only |
| `just unit <package>` | Run unit tests |
| `just functional <package>` | Run functional tests (may need external software available, or to be run with sudo -- and note that this probably indicates a test that's destructive to the local environment (e.g. adding or removing packages)). **Do not run functional tests directly on the host.** Use Workshop instead (see below). |
| `just pack-k8s <package>` | Pack K8s test charm(s) for integration tests, running the libraries `tests/integration/pack.sh` script with environment variables set |
| `just pack-machine <package>` | Pack machine test charm(s) for integration tests, as above |
| `just integration-k8s <package>` | Run Juju integration tests, excluding `pytest.mark.machine_only` tests |
| `just integration-machine <package>` | Run Juju integration tests against machine, excluding `pytest.mark.k8s_only` tests |
| `just docs html [packages]` | Build docs (including reference docs for all packages by default, or named ones -- run `just docs html -` to exclude all package reference docs (faster when working on docs only) |
| `just docs` | Alias for `just docs html` |
| `just add <package> <dep>` | Add a dependency to a library |
| `just init` | Scaffold a new general library |
| `just interface init` | Scaffold a new interface library |

Extra arguments to `just unit`, `just functional`, and `just integration-*` are passed through to pytest:

```bash
just unit pathops -x -k test_copy   # stop on first failure, filter by name
```

### Adding dependencies

**Always use `just add <package> <dep>` instead of calling `uv add` directly.** This applies repo-level version constraints from `test-requirements.txt`, which is necessary to keep the lockfile consistent:

```bash
just add pathops 'pydantic>=2'
just add interfaces/tls-certificates --requirements my-requirements.txt
```

## Test types

| Type | Command | What it tests | External requirements |
|------|---------|---------------|----------------------|
| Unit | `just unit <package>` | Logic with mocked externals | None |
| Functional | `just functional <package>` | Interaction with real external processes (not Juju) | Varies (for example, pebble, sudo) |
| Integration | `just integration-k8s/machine <package>` | Library in a real Juju deployment | charmcraft + Juju controller |

A test type is only executed if the corresponding `tests/` subdirectory exists. Remove a directory to skip that test type entirely.

Read more: [types of tests in the charmlibs monorepo](https://documentation.ubuntu.com/charmlibs/explanation/charmlibs-tests/).

### Running functional tests with Workshop

Functional tests often require `sudo` and may be destructive to the local environment (e.g. installing or removing system packages). **Never run functional tests directly on the host machine.** Always use [Workshop](https://snapcraft.io/workshop) to run them in an isolated container:

```bash
workshop run resolute -- functional <package>    # Ubuntu 26.04
workshop run noble -- functional <package>       # Ubuntu 24.04
workshop run jammy -- functional <package>       # Ubuntu 22.04
```

Workshop configs are defined in `.workshop/`. The `functional` action runs `sudo just functional "$@"` inside the VM. Extra pytest flags are passed through:

```bash
workshop run noble -- functional snap -x -k test_install
```

## Commit and PR conventions

**PRs are squash-merged.** The PR title becomes the single commit message on `main`. Branch commit messages are for local reference, and should follow conventional commits for clarity.

PR titles must follow [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/). When a PR affects a single library, use the distribution package name without the leading `charmlibs-` as the scope:

```
feat(pathops): add copytree and rmtree
fix(apt): handle multiarch package names correctly
chore(interfaces-tls-certificates): update to Pydantic v2
docs: improve tutorial for adding integration tests
```

**One PR should normally touch only one library.** The CI uses changed files to determine which packages to test and, on merge, which packages to publish.

### Versioning

- Libraries use semantic versioning (`MAJOR.MINOR.PATCH`).
- Dev versions (`X.Y.Z.devN`) are excluded from release CI — safe for in-progress work.
- When bumping to a non-dev version, you **must** also update `CHANGELOG.md`. CI will block the merge otherwise.
- The CI automatically publishes to PyPI on merge when a non-dev version bump is detected.

## Package anatomy

A typical general library looks like this:

```
pathops/
├── src/charmlibs/pathops/
│   ├── __init__.py         # Exports public API; module docstring appears in reference docs
│   ├── _pathops.py         # Private implementation module(s)
│   └── _version.py         # __version__ string (auto-generated)
├── tests/
│   ├── unit/
│   │   ├── conftest.py
│   │   └── test_*.py
│   ├── functional/
│   │   ├── setup.sh        # Sourced before tests (for example, start pebble)
│   │   ├── teardown.sh     # Sourced after tests (for example, kill pebble)
│   │   └── test_*.py
│   └── integration/
│       ├── pack.sh         # Script to pack test charms
│       ├── conftest.py     # Juju fixtures (jubilant)
│       ├── test_*.py
│       └── charms/         # Test charm source
├── pyproject.toml          # Package metadata, dependencies, tool config
├── uv.lock                 # Locked dependencies — commit this
├── README.md
└── CHANGELOG.md            # Must be updated before each release
```

The source uses a namespace package structure: `src/charmlibs/<name>/`. Public API is exported from `__init__.py` via `__all__`. Implementation lives in private submodules (prefixed with `_`). The module docstring in `__init__.py` appears as the top-level description in the generated reference docs.

## Interface libraries

Interface libraries manage the structured data that charms exchange over a Juju relation databag. Key differences from general libraries:

- Live under `interfaces/<interface-name>/`, named exactly as the interface name appears in `charmcraft.yaml`.
- Source under `src/charmlibs/interfaces/<interface_name>/`.
- Usually include a `testing/` subdirectory with a separate `charmlibs-interfaces-<name>-testing` package. This provides `relation_for_provider()` and `relation_for_requirer()` helpers for charm unit tests.
- Typically have unit and integration tests but no functional tests (all meaningful interaction is through Juju).
- Use `just interface init` to scaffold.

Read more: [how to design relation interfaces](https://documentation.ubuntu.com/charmlibs/how-to/design-relation-interfaces/), [how to provide relation data for charm tests](https://documentation.ubuntu.com/charmlibs/how-to/provide-relation-data-for-charm-tests/).

## Documentation

Reference docs are auto-generated from Python docstrings via Sphinx autodoc. The docs source lives in `.docs/`. Build reference docs for a specific package with:

```bash
just docs html pathops
```

This is also run as part of `just check`. The full docs site (all packages) is built with `just docs`.

When writing or editing docstrings in `__init__.py` or other public modules, remember they appear verbatim in the published reference at [documentation.ubuntu.com/charmlibs](https://documentation.ubuntu.com/charmlibs). Keep them informative for library users, not implementation notes.

### Importing docs from Discourse

Some charms keep their documentation on Discourse (discourse.charmhub.io). When migrating an interface library, you may want to bring that content into the library's `docs/` directory. There are two parts: **locating** the source topics (exploratory, done up front) and **migrating** them (a deterministic, disposable script).

#### Locate the source topics

This step is exploratory and can't be fully scripted:

1. Start from the charm's Charmhub page, e.g. `https://charmhub.io/<charm>`.
2. Follow the **"Help improve this document in the forum"** link at the bottom of the page — it points to the Discourse *root topic* for the charm's docs.
3. The root topic contains a table of contents linking each child topic. Charmhub renders the charm's docs from this structure, so it usually already encodes a diataxis-like layout (tutorial / how-to / explanation / reference) that you can carry over.
4. From the table of contents, build the `TOPICS` mapping used by the script below. Each topic's ID is the number in its Discourse URL (`https://discourse.charmhub.io/t/<slug>/<topic_id>`). Deciding each topic's diataxis category is the main judgment call.

Not every charm is a candidate. Some use a Read the Docs / Sphinx site instead of Discourse — that content isn't available through the Discourse JSON API, but it's easier to migrate anyway: copy the doc site's source files into the library's `docs/` directory and adapt them.

#### Migrate the topics

Fill in `TOPICS`, run the script, then review the output. The mechanical steps — fetch JSON, extract the raw markdown, resolve `upload://` image links — are deterministic; the steps that need judgment (categorisation, post-import editing) are captured as comments rather than code.

```python
# /// script
# requires-python = ">=3.12"
# ///
"""Import charm docs from Discourse into a library's docs/ directory.

Disposable: fill in LIB and TOPICS, run, review the output, then delete this
script and the downloaded JSON before merging.
"""

import json
import pathlib
import re
import time
import urllib.request

# Target library path, relative to the repo root.
LIB = pathlib.Path('interfaces/tls-certificates')

# JUDGMENT STEP: read the root topic's table of contents and map each child
# topic to its output file (which encodes the diataxis category) and title.
# topic_id -> (path relative to <LIB>/docs/, page title)
TOPICS: dict[int, tuple[str, str]] = {
    15537: ('tutorial.md', 'Getting Started'),
    15539: ('explanation/tls-certificates-interface.md', 'TLS Certificates Interface'),
    # ...
}

DOCS_DIR = LIB / 'docs'
JSON_DIR = DOCS_DIR / 'discourse-json'  # cache; delete after import


def fetch(topic_id: int) -> dict:
    """Download a Discourse topic as JSON, caching it under JSON_DIR."""
    url = f'https://discourse.charmhub.io/t/{topic_id}.json?include_raw=true'
    data = json.loads(urllib.request.urlopen(url, timeout=30).read())
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    (JSON_DIR / f'{topic_id}.json').write_text(json.dumps(data))
    time.sleep(2)  # rate-limit: be nice to Discourse
    return data


def resolve_images(raw: str, cooked: str) -> str:
    """Rewrite upload:// shortcodes to real URLs using the cooked HTML."""
    uploads = re.findall(r'upload://[^\s)]+', raw)
    img_urls = re.findall(r'<img[^>]+src=["\']([^"\'\s]+)', cooked)
    for upload, url in zip(uploads, img_urls):  # matched positionally
        raw = raw.replace(upload, url)
    # Strip Discourse's |WIDTHxHEIGHT suffix from image alt text.
    return re.sub(r'!\[([^\]]*?)\|\d+x\d+\]', r'![\1]', raw)


def main() -> None:
    for topic_id, (rel_path, _title) in TOPICS.items():
        post = fetch(topic_id)['post_stream']['posts'][0]
        markdown = resolve_images(post['raw'], post['cooked'])
        out = DOCS_DIR / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown)

    # MANUAL STEP: review and edit the imported markdown to fit charmlibs
    # conventions (add H1 titles and meta descriptions, fix cross-references,
    # confirm diataxis categorisation), then delete this script and JSON_DIR.


if __name__ == '__main__':
    main()
```

After running, do the manual review noted at the end of the script, then delete the script and the downloaded JSON before merging.

## Common pitfalls

- **Don't call `uv add` directly** — use `just add <package> <dep>` to respect repo-level constraints.
- **Don't bump the package you're working on to a non-dev version without updating `CHANGELOG.md`** — CI will block the merge.
- **Making changes to multiple libraries in the same PR** — the CI matrix runs per changed package, and review requirements are determined by `CODEOWNERS`.
- **Don't add unnecessary features or refactor code beyond what's asked** — this is a multi-team monorepo with careful versioning; unintended public API changes require major version bumps.

## External resources

| Resource | URL |
|----------|-----|
| charmlibs docs | .docs/index.md |
| ops (charm framework) | https://documentation.ubuntu.com/ops/ |
| ops.testing reference | https://documentation.ubuntu.com/ops/latest/reference/ops-testing/ |
| Juju docs | https://documentation.ubuntu.com/juju/latest/llms.txt |
| Charmcraft docs | https://documentation.ubuntu.com/charmcraft/stable/ |
| Jubilant (integration test client) | https://documentation.ubuntu.com/jubilant/ |
| Pebble | https://documentation.ubuntu.com/pebble/ |
| Concierge (CI Juju setup) | https://raw.githubusercontent.com/canonical/concierge/refs/heads/main/README.md |
