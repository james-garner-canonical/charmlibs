# Plan v2: Per-library diataxis docs — preprocessor + fallback extension

Supersedes the Sphinx-extension-only approach from PLAN.md (tasks 1–7).

## Problem with the v1 approach

The v1 approach used a Sphinx extension with toctree globs. Glob toctrees that
match nothing cause Sphinx warnings (treated as errors with `-W`). To fix this,
the extension wrote placeholder files — but these placeholders appear as visible
entries in the sidebar. The glob warning (`toc.glob`) also proved unsuppressable
via Sphinx's `suppress_warnings` mechanism.

## New approach: preprocessor + include files + fallback extension

Split the work into two components:

1. **Preprocessor** (`_diataxis_docs` just recipe) — runs before any
   `sphinx-build`. Copies library docs into `.docs/`, generates include files
   with explicit toctree entries.

2. **Fallback Sphinx extension** (`diataxis_docs.py`) — runs at
   `builder-inited`. If the preprocessor's include files don't exist, writes
   placeholder fallbacks so `sphinx-build` alone still works.

### Build flow

```
just docs html [packages]
  → _diataxis_docs          # NEW: copy lib docs + write include files
  → _packages [packages]    # existing: per-package autodoc
  → sphinx-build             # existing: final build
```

### Include files

Six include files, all under `.docs/`:

| Include file | Included from | Glob equivalent |
|---|---|---|
| `tutorials/_lib-tutorials.md` | `tutorials/index.md` | `charmlibs/*`, `charmlibs/interfaces/*` |
| `how-to/_lib-howtos.md` | `how-to/index.md` | `charmlibs/*/*`, `charmlibs/interfaces/*/*` |
| `explanation/_lib-explanations.md` | `explanation/index.md` | `charmlibs/*/*`, `charmlibs/interfaces/*/*` |

Each include file contains a `{toctree}` block with explicit entries for
library docs that exist, or is empty if no libraries have docs for that
category. Empty include = nothing in the sidebar. No placeholders needed.

The preprocessor always writes all three include files (even empty ones) so
the fallback extension can detect "preprocessor ran, nothing to show" vs
"preprocessor didn't run" by checking file existence.

### Fallback behaviour

When `sphinx-build` runs without the preprocessor (e.g. during development),
the fallback extension writes include files containing a placeholder toctree
entry. This ensures the build succeeds with placeholder content visible —
similar to how skipping `_packages` gives a working build without reference
docs.

### Index files

The checked-in index files use `{include}` to pull in the generated toctree
entries:

```markdown
# How-to guides

```{toctree}
:maxdepth: 1

Design relation interfaces <design-relation-interfaces>
...static entries...
```

```{include} _lib-howtos.md
```
```

The index files build cleanly in both paths:
- Preprocessor ran → include files have real entries (or are empty)
- Preprocessor didn't run → fallback extension writes placeholder entries

### Generated file layout

Same as v1 — library docs are copied into the Sphinx source tree:

```
.docs/
├── tutorials/
│   ├── index.md                             # checked in, uses {include}
│   ├── _lib-tutorials.md                    # GENERATED (include file)
│   └── charmlibs/                           # GENERATED (lib docs)
│       └── interfaces/
│           └── tls-certificates.md
├── how-to/
│   ├── index.md                             # checked in, uses {include}
│   ├── _lib-howtos.md                       # GENERATED (include file)
│   └── charmlibs/                           # GENERATED (lib docs)
│       └── ...
├── explanation/
│   ├── index.md                             # checked in, uses {include}
│   ├── _lib-explanations.md                 # GENERATED (include file)
│   └── charmlibs/                           # GENERATED (lib docs)
│       └── interfaces/
│           └── tls-certificates/
│               ├── certificate-renewal.md
│               └── ...
```

## Alternatives considered

### 1. Sphinx extension only (v1, implemented then revised)

Used toctree globs with placeholder files written by the extension.

- **Pro**: single component, runs automatically
- **Con**: placeholders visible in sidebar; `toc.glob` warnings unsuppressable
- **Verdict**: replaced by this approach

### 2. Pure preprocessor (no extension)

All work in a just recipe, no Sphinx extension at all.

- **Pro**: simple, no Sphinx API interaction
- **Con**: `sphinx-build` alone fails (include files don't exist)
- **Verdict**: rejected — we want `sphinx-build` alone to produce a working
  (if incomplete) result

### 3. Sphinx extension + suppress `toc.glob`

Keep the glob approach, suppress the warning.

- **Pro**: simplest change from v1
- **Con**: `toc.glob` suppression didn't work (tested); may not be a valid
  Sphinx `suppress_warnings` type
- **Verdict**: not viable

### 4. Sphinx extension generating toctree entries in-place

Extension modifies the checked-in index files to inject toctree entries.

- **Pro**: no include files needed
- **Con**: dirty git diff after builds
- **Verdict**: rejected

### 5. Jinja templates for index files

Checked-in `.md.j2` templates rendered by preprocessor.

- **Pro**: static content visible in templates, dynamic parts clearly marked
- **Con**: moves index file content behind a template layer; harder for doc
  contributors to find and edit
- **Verdict**: less clean than the include approach for this use case

## Changes from v1

| File | v1 (current) | v2 (new) |
|---|---|---|
| `diataxis_docs.py` | Full extension: copy files + placeholder logic | Tiny fallback: write placeholder include files if missing |
| `tutorials/index.md` | Glob toctrees | `{include} _lib-tutorials.md` |
| `how-to/index.md` | Appended glob toctrees | Replace globs with `{include} _lib-howtos.md` |
| `explanation/index.md` | Appended glob toctrees | Replace globs with `{include} _lib-explanations.md` |
| `docs.just` | No preprocessor step | New `_diataxis_docs` recipe before `_packages` |
| `.gitignore` | `charmlibs/` covers generated dirs | Add `_lib-*.md` for include files |
| `test_diataxis_docs.py` | Tests extension logic | Tests preprocessor logic (moved out of extension) |

## Implementation tasks

### Task 1: Write preprocessor (`.docs/extensions/diataxis_docs.py` → reuse as library)

Extract the file-copying logic from the current extension into a `_main()`
function that can be called from both the just recipe and tests. The
preprocessor:

1. Scans packages for `docs/` directories
2. Copies files with H1 prefix and link rewriting
3. Writes include files with explicit toctree entries

### Task 2: Refactor extension to fallback-only

The extension becomes a small fallback: at `builder-inited`, write placeholder
include files for any that don't exist.

### Task 3: Update index files

Replace glob toctrees with `{include}` directives.

### Task 4: Add `_diataxis_docs` recipe to `docs.just`

New recipe that runs the preprocessor. Wire it as a dependency of `html`.

### Task 5: Update clean recipe and .gitignore

Add include files to both.

### Task 6: Update tests

Test the preprocessor logic (file copying, H1 prefix, link rewriting, include
file generation) and the fallback extension.

### Task 7: Validate both build paths

- `just docs html interfaces/tls-certificates` — full build with preprocessor
- Raw `sphinx-build` in `.docs/` — fallback with placeholders
- `just docs ext-static` — pyright clean
- `just docs ext-unit` — tests pass

## Validation commands

- `just docs html interfaces/tls-certificates` — full build
- `just docs ext-unit` — unit tests
- `just docs ext-static` — pyright
