(how-to-add-library-docs)=
# How to add docs to a library

Each library in the charmlibs monorepo can include its own documentation — tutorials, how-to guides, and explanations — which are automatically included in the [charmlibs docs site](https://documentation.ubuntu.com/charmlibs).

This guide shows you how to add docs to your library package.

## Create the docs directory

Create a `docs/` directory in your library's root:

```text
mylib/
├── docs/
│   ├── tutorial.md
│   ├── how-to/
│   │   ├── deploy.md
│   │   └── configure.md
│   └── explanation/
│       └── architecture.md
├── src/
├── tests/
└── pyproject.toml
```

The three supported categories are:

| Category | Location | Notes |
|---|---|---|
| Tutorial | `docs/tutorial.md` or `docs/tutorial.rst` | One file only |
| How-to guides | `docs/how-to/*.md` or `docs/how-to/*.rst` | Multiple files |
| Explanations | `docs/explanation/*.md` or `docs/explanation/*.rst` | Multiple files |

Only these categories are discovered. Other directories under `docs/` are ignored.

## Write your docs

Each doc file must start with a top-level heading:

````markdown
# Getting Started

In this tutorial, you'll learn how to ...
````

The heading text is used as the page title in the docs site, prefixed with your library name. For example, a tutorial in `pathops/docs/tutorial.md` with heading `# Getting Started` will appear as **pathops: Getting Started** in the site navigation.

### Linking to other docs

Use relative links to reference other files in your library or in the repo. The build system rewrites these links automatically:

- Links to other docs files (tutorials, how-to guides, explanations, or `.docs/` pages) become internal Sphinx links.
- Links to any other repo files (source code, READMEs, etc.) become GitHub links pointing to the `main` branch.

For example, from `docs/how-to/deploy.md`:

```markdown
See the [architecture overview](../explanation/architecture.md) for background.

Check the [source code](../../src/charmlibs/mylib/_impl.py) for details.
```

## Build and preview

To build the docs and verify your changes:

```bash
just docs html mylib
```

This runs the preprocessor (which copies your docs into the Sphinx source tree) and builds the site. Your docs will appear under the corresponding category pages.

To build docs for all packages:

```bash
just docs
```
