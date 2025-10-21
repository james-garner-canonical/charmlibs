# interface-tests-v0

This branch of the `charmlibs` monorepo hosts `v0` of the `interface-tests` workflow.
This workflow can be used from your charm's repo to run the interface tests that are run against your charm in `charmlibs@main`.

To run the workflow on your `main` or feature branch, you could add a workflow like this:

```yaml
# .github/workflows/interface-tests.yaml

on:
  push:
    - 'main'

jobs:
  interfaces:
    uses: canonical/charmlibs/.github/workflows/interface-tests.yaml@interface-tests-v0
    with:
      charm: <your-charm-name>
```

Or add that job to an existing workflow.
If you have a charm monorepo, you can use the workflow in a matrix job like this:

```yaml
  interfaces:
    strategy:
      fail-fast: false
      matrix:
        charm: [<charm-one>, <charm-two>]
    uses: canonical/charmlibs/.github/workflows/interface-tests.yaml@interface-tests-v0
    with:
      charm: ${{ matrix.charm }}
```

To see how merging a specific PR would change your interface test results, you can run the workflow on PRs like this:

```yaml
on:
  pull_request:

jobs:
  interfaces:
    uses: canonical/charmlibs/.github/workflows/interface-tests.yaml@interface-tests-v0
    with:
      charm: <your-charm-name>
      charm-repo: ${{ github.event.pull_request.head.repo.full_name }}
      charm-branch: ${{ github.event.pull_request.head.ref }}
```

Or again, add that job to an existing workflow.

Visit the `main` branch of this repo for more information about charm libraries, or [read the docs](https://documentation.ubuntu.com/charmlibs).
