# Tutorial

In this tutorial you'll add a new library to the `charmlibs` monorepo.

**What you'll need:**

- Your development machine.
- An internet connection.

**What you'll do:**

- Use the `charmlibs` repository tooling to add a new library from the template.
- Get familiar with the repository tooling that will test and release your library.
- Document your library and modify `CODEOWNERS` to get approval to add your library to the monorepo.

```{note}
Should you get stuck at any point: Don't hesitate to get in touch on [Matrix](https://matrix.to/#/#charmhub-charmdev:ubuntu.com) or [Discourse](https://discourse.charmhub.io/).
```

## Create a new library from the template

Head to your local copy of your fork of the `charmlibs` monorepo and ensure it's up-to-date, or:
- [Create a new fork](https://github.com/canonical/charmlibs/fork)
- Copy the SSH url for your fork (under `Code > Local > SSH`)
    - It should look like this: `git@github.com:<YOUR USERNAME>/charmlibs.git`
- Clone it with `git clone <YOUR SSH URL>`
    - You'll also want to [ensure you've set up your Github account with your SSH key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account)

In your local clone of your fork, create a new feature branch to add your library, for example:
```bash
git checkout -b feat/add-<YOUR LIBRARY NAME>-lib
```

From this point on, we'll need [uv](https://github.com/astral-sh/uv) for all our developer commands.
If you don't already have it installed, follow the [uv installation instructions](https://github.com/astral-sh/uv?tab=readme-ov-file#installation), or install the `snap`:
```bash
sudo snap install --classic astral-uv
```
This repository uses [just](https://github.com/casey/just) as a command runner. With `uv` installed, we can install `just` with:
```bash
uv tool install rust-just
```
Now you can run `just` from anywhere in the repository to see help on the available commands.
These commands can also be run from anywhere in the repository, as they're always executed in the repository root -- specifically, in the directory where the `justfile` is found.

Get started by running `just new <YOUR LIBRARY NAME>`, and provide the requested information interactively:
- the name of your library (without the `charmlibs-` prefix)
- the minimum Python version you'll support (e.g. `3.10` or `3.12`)
- the author information to display on PyPI (e.g. `The <YOUR TEAM NAME> team at Canonical`).

The author and minimum Python version information are easy to change in the generated `pyproject.toml` later, but if you change your library name you'll need to change it in a few other locations too, like the directory names (`<YOUR LIBRARY NAME>/src/charmlibs/<YOUR LIBRARY NAME>`) and the imports in your tests and test charms.

This will create a new directory for your library named accordingly.
The library itself just sets `__version__` to `0.0.0.dev0`, and the tests just check the version.

## Verifying the basics

Let's verify that your library has been scaffolded correctly.
Start by running `just lint <YOUR LIBRARY NAME>` from anywhere in the repository.
(`just` commands execute from the `justfile` directory, regardless of where they're run.)
This will run `ruff`, `codespell`, and `pyright` on your library, all of which should pass.
This will also create a `uv.lock` file in your library's directory, which should be included in version control.

Then run `just unit <YOUR LIBRARY NAME>` to verify that your unit tests pass, and `just functional <YOUR LIBRARY NAME>` to check the functional tests.
We'll talk more about Juju integration tests later.

You can also verify that everything looks right in an interactive session.
Run `uvx --with=path/to/<YOUR LIBRARY NAME> ipython --pdb` to start an interactive Python shell with your library installed, and then import it with:
```python
from charmlibs import <YOUR LIBRARY NAME>
```
You can then run `<YOUR LIBRARY NAME>.__version__` to see the initial `0.0.0.dev0` version string.

Assuming everything is working as expected, consider using `git add` with the newly created files and `git commit` them to have a clean starting point for future comparisons.
This should include the `uv.lock` file that was created by running `just` in this section.

## Add a feature

If you have already started prototyping your library, or are porting some existing code, this is a perfect time to add it to the library.
It's a good idea to start small, so you can verify that the basics are all working as expected.
In this tutorial, we'll add a function to return the library's version as a `packaging.version.Version` object, but feel free to follow along with your own code.

We'll start by adding the `packaging` dependency. From anywhere in the repository, run:
```bash
just add <YOUR LIBRARY NAME> packaging
```
If you committed the generated files previously, then a `git diff --stat` should now show that your `pyproject.toml` and `uv.lock` files have been updated.

Now we can add the code itself.
Under `src/charmlibs/<YOUR LIBRARY NAME>/__init__.py`, you'll find an `__init__.py` file.
This is the file that's executed when your library is imported.
In principle we can put all our library code here, but it's good practice to use separate files (modules) instead, so we can be more intentional about the public interface of our library.

In Python, names prefixed with a single underscore are private.
This isn't enforced technically (a user who knows your library layout can import private symbols), but semantically there are no stability guarantees when using private variables.
`charmlibs` follow semantic verisoning, so if we expose something publicly, we're promising to support it until at least our next major verson.
Let's add a private module where our feature implementation will live -- create the file `src/charmlibs/<YOUR LIBRRARY NAME>/_fancy_version.py`.

Copy the copyright header from your `__init__.py` file to your new module, and import our `packaging` dependency:
```python
import packaging.version
```
We'll also add a relative import for our package version:
```python
from . import _version
```
And finally add this function:
```python
def version():
    return packaging.version.Version(_version.__version__)
```
Consider running `just format` to make sure you have everything formatted correctly
You can confirm this with `just lint <YOUR LIBRARY NAME>`.

Currently, the `version` function isn't part of our package's public interface.
It *is* a public function, but it's hidden away from our users in a private module.
If it was intended to be private, it would be a good idea to name it `_version` instead, but in this case we want it to be public.
We'll expose it by adding a relative import in our `__init__.py`:
```python
from ._fancy_version import version
```
And adding `version` to `__all__`:
```python
__all__ = [
    'version',
]
```

You can try out your new function in an interactive shell like we did before.
In the next sections, we'll add tests to verify its behaviour more rigorously.

## Test your library

The `charmlibs` monorepo supports three distinct kinds of tests, and the template starts you off with a simple passing test for each:
- **tests/unit** These are lightweight tests of your library that are fast to run and don't require any additional setup. They typically mock out the external world so your tests are reproducible and side-effect free.
    - You can run these locally from anywhere in the repository with `just unit <YOUR LIBRARY DIRECTORY>`.
    - If you already have some functionality ready for your library, you can drop your tests in here straight away.
- **tests/functional** These test the behaviour of your library as it interacts with a real Ubuntu system (but not Juju).
    - You can run these locally from anywhere in the repository with `just functional <YOUR LIBRARY DIRECTORY>`, but be careful with this if the tests may make actual changes to your system (for example, the `apt` library's functional tests require `sudo` and will try to install packages).
    - You can customise how these are run in CI by editing the `tool.charmlibs.functional` table in your library's `pyproject.toml` (read more link).
    - If you don't think your library would benefit from functional tests, you can remove the `tests/functional` directory, and they will be skipped in CI.
- **tests/integration** These test the behaviour of your library in deployed charms running on a real Juju controller.
    - Juju integration tests are slow and can sometimes be a bit flaky, but they're a valuable test that your library works 'for real', and that you understand how it should be used in a charm, so they're worth keeping even if they stay pretty minimal.
    - You can customise how these are run in CI in a few different ways, which we'll go over later in this tutorial.

### Unit tests

Running `just unit <YOUR LIBRARY>` uses `pytest` to collect and run any tests defined under your library's `tests/unit` directory.
We'll add a test for our fancy version function to the existing `tests/unit/test_version.py` file.
If you're following along with your own library functionality, it would be better to make a new `test_<something>.py` module for your feature, or rename `test_version.py`.

We'll use `pytest.monkeypatch` to for our unit tests, so we need to add the `pytest` import for our type annotations among other things:
```python
import pytest

from charmlibs import <YOUR LIBRARY>
```

```{warning}
Don't add `pytest` to your `pyproject.toml`.

`just unit <YOUR LIBRARY>` will install and run a specific version of `pytest`, which may clash with the version added in your dependencies.
Instead, use `just` to run tests -- any extra arguments will be passed to `pytest`.
You can point your IDE to `<YOUR LIBRARY>/.venv` after running any of the test commands to have it use the correct virtual environment.
```

Then add a test like this:
```python
def test_fancy_version(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(<YOUR LIBRARY>, '__version__', '1.2.3.dev0')
    fancy_version = <YOUR LIBRARY>.version()
    assert str(fancy_version) == '1.2.3.dev0'
    assert fancy_version.major == 1
    assert fancy_version.minor == 2
    assert fancy_version.micro == 3
    assert fancy_version.is_devrelease
```

You can also use the `ops.testing` framework to write lightweight tests of your library in a charm.
This is particularly useful if your library observes any events or emits custom events.
For more on `ops.testing`, see:
- [ops.testing reference docs for custom events](ops.testing.CharmEvents.custom)
- [ops.testing how-to for testing that a custom event is emitted](https://documentation.ubuntu.com/ops/latest/howto/manage-libraries/#test-that-the-custom-event-is-emitted)

### Functional tests

In this repository, functional tests are essentially integration or end-to-end tests.
They differ from the tests labeled as integration tests in that they do not interact with a real Juju environment.
In contrast to unit tests, which typically mock out external concerns, functional tests interact with real systems, external processes, and networks.

A functional test for our fancy version function would look similar to the unit test, but we wouldn't mock out anything:
```python
def test_fancy_version(monkeypatch: pytest.MonkeyPatch):
    fancy_version = <YOUR LIBRARY>.version()
    assert str(fancy_version) == <YOUR LIBRARY>.__version__
```
As you can see, for this function, this might as well be a unit test.
Our fancy version function is a bad fit for functional tests, as it doesn't need to interact with any external processes.
In this case, the library's core functionality is well exercised by unit tests alone.
We'll use full Juju integration tests to ensure everything is working correctly in the charm context, but we'll drop the functional tests by removing the `tests/functional` directory.
The functional tests will then show as skipped in CI.

You may want to remove functional tests if your library is like our fancy version function.
You may also want to skip functional testing if your library only really makes sense in a charm context, and seems difficult to test outside it.
On the other hand, if your library does interact with or wrap some external process that can be tested outside a charm context, functional tests may be a good fit.
For example, `charmlibs-apt` wraps Ubuntu's `apt` command, and its functional tests install and uninstall real packages.
Another example is `charmlibs-pathops`, which provides a `pathlib`-like API for filesystem operations in charm workload containers via `pebble` -- its functional tests interact with a `pebble` server running on the local system, instead of in the charm context.
The motivation in both of these cases is that this is a lot faster than packing the library into a charm and deploying it on a Juju managed cloud, while fully exercising the interesting parts of these libraries.

Functional tests can be customised by editing this section of your library's `pyproject.toml` file (it has no effect if `tests/functional` is removed):
```toml
[tool.charmlibs.functional]
```
There are currently three supported variables:
- `ubuntu` is a list of Ubuntu bases, for example `["22.04", "24.04"]`.
    - This is used to run your functional tests in a matrix in CI, with the operating system set as `ubuntu@<YOUR VERSION>`.
    - It defaults to running once with `ubuntu@latest`.
    - If this is important for your library, consider using virtual machines to test against multiple bases locally.
- `pebble` is a list of [Pebble version tags](https://github.com/canonical/pebble/tags), for example `["v1.24.0"]`.
    - If specified, the Pebble version will be an additional row in the matrix your functional tests are run with, with the corresponding Pebble version installed.
    - By default, your tests are run once without Pebble installed.
    - For local testing, you'll need to install the version of Pebble that you want to test against yourself. You can then run `just functional-pebble <YOUR LIBRARY DIRECTORY>` instead of `just functional <YOUR LIBRARY DIRECTORY>` to have Pebble started and stopped before and after your tests.
- `sudo` is a `true` or `false` option, defaulting to `false`.
    - If it's `true`, your tests are run in CI with `sudo` permissions in their ephemeral runner.
    - If your tests require `sudo` privileges, you'll need to manage that locally yourself, for example by testing in a virtual machine.

If your library needs another piece of software like `pebble` installed for its functional tests, get in touch with us on [Matrix](https://matrix.to/#/#charmhub-charmdev:ubuntu.com) or open an issue about the option to install it in CI.

### Integration tests

Integration tests are the most complicated and most heavyweight part of the library testing story.
In its integration tests, your library will be packed into one or more charms, those charms will be deployed with Juju, and your tests will run against the deployed charms.
You can customise your integration tests in several ways, according to the needs of your library.
You'll determine whether it makes sense to test on both K8s and machine clouds, with one or more charms, and whether to rerun the integration tests with other permutations.

Your integration tests will be run in CI with a matrix of Juju substrates, and a list of `tags` defined in your `pyproject.toml` under:
```toml
[tool.charmlibs.integration]
```
The substrate (`k8s` or `machine`) determines the type of cloud bootstrapped by [concierge](https://github.com/canonical/concierge), and is exposed as an environment variable (`CHARMLIBS_SUBSTRATE`). The tag is also made available as an environment variable (`CHARMLIBS_TAG`), and is otherwise unused by the CI machinery. The default is to run once per substrate with no tag (`CHARMLIBS_TAG=`).

You can use `pytest` marks to declare certain tests to be run only with K8s charms or only with machine charms. If your library is intended for K8s or machine charms only, you should mark your tests accordingly -- you can mark an entire test module with, for example, `pytestmark = pytest.mark.k8s_only`, or use [pytest_collection_modifyitems](https://docs.pytest.org/en/latest/reference/reference.html#pytest.hookspec.pytest_collection_modifyitems) to ensure all your integration tests are marked. If no tests are collected for one substrate, it will be skipped in CI. (If no tests are collected for either substrate, there will be an error.)

After setting up the test environment with `concierge`, if your library has a `tests/integration/pack.sh` script, it will be executed. The template provides a script that packs a different minimal charm depending on the substrate, using symlinks to share common code and metadata, and resolving these before packing. You can modify this script to pack one or more charms to be deployed in your integration tests. Both `CHARMLIBS_SUBSTRATE` and `CHARMLIBS_TAG` are set when running `pack.sh`, which you can use to change what gets packed.

Let's add an integration test for our fancy version function.

We'll start by taking a look at the files that will make up our packed charm, under `tests/integration/charms`.
At the top level are directories for two test charms, with the directory name reflecting the substrate the charm is for: `k8s` and `machine`.
You'll also see some common files which are symlinked into the structure for our two test charms -- these symlinks are resolved by `pack.sh` before `charmcraft pack` is executed.
Taking a look inside one of the charm directories, you can see these symlinks, as well as a unique `charmcraft.yaml` file, and the usual `src/` directory.
There's also a directory named `package/`, which contains symlinks to your library code and metadata -- this is how your library is made available to the charms.
Under `src/`, you'll see a unique `charm.py` file, and a symlink to `common.py`.

This structure reflects the logic of `tests/integration/pack.sh`, which finds a directory under charms named `$CHARMLIBS_SUBSTRATE`, copies it to a temporary location for packing, resolving any symlinks, and packs the charm.
You're free to customise this script as you need to, but hopefully it's a good starting point.

Our fancy version function should work just as well in a K8s charm as in a machine charm, so we'll test on both substrates, and we won't mark any of our tests as `k8s_only` or `machine_only`.

We'll communicate with the library in our packed charm via a Juju action.
Open `tests/integration/charms/actions.yaml` and add a new action:
```yaml
fancy-lib-version:
```

We'll also need an observer for this action, which can be the same for both charms.
It will look a lot like the handler for `lib-version`, `_on_lib_version`, but we'll serialize the fancy version information as a JSON object so it can be passed over the wire to our test code.
Open `tests/integraton/charms/common.py` and add an observer for this action to the `Charm` class body (`json` is already imported):
```python
def _on_fancy_lib_version(self, event: ops.ActionEvent):
    logger.info('action [fancy-lib-version] called with params: %s', event.params)
    fancy_version = <YOUR LIBRARY NAME>.version()
    di = {
        attr: getattr(fancy_version, attr)
        for attr in dir(fancy_version)
        if not attr.startswith('_')
    }
    results = {'result': json.dumps(di)}
    event.set_results(results)
    logger.info('action [fancy-lib-version] set_results: %s', results)
```

Finally, we'll need a test to exercise this code. Open `tests/integration/test_version.py`, and add a new test:
```python
def test_fancy_lib_version(juju: jubilant.Juju, charm: str):
    result = juju.run(f'{charm}/0', 'fancy-lib-version')
    di = json.loads(result.results['result'])
    assert di['is_devrelease']== <YOUR LIBRARY NAME>.version().is_devrelease
```

You can test this locally by running `just pack-k8s <YOUR LIBRARY NAME>` and `just pack-machine <YOUR LIBRARY NAME>` to pack your K8s and machine charms, and then running `just integration-k8s <YOUR LIBRARY NAME>` and `just integration-machine <YOUR LIBRARY NAME>` to deploy the charms on your local Juju K8s and machine clouds and test them.
However, you may find it easier to run them in CI instead, which you can easily do by opening a pull request in the next section.

## Add your library to the `charmlibs` monorepo

To add your library to the `charmlibs` monorepo, you'll need to make a PR. However, there's one important step we must do first, namely adding an entry to the `CODEOWNERS` file for the new library.
Scan through `CODEOWNERS` and find the correct place to enter your library alphabetically.
Add a new line, starting with `/<YOUR LIBRARY NAME>/`, followed by a space, and then the name of the team or individuals who will own the library.
Ownership means they can approve PRs that change the files in your library directory -- code, metadata, tests, and so on.
The `canonical/charmlibs-maintainers` team has owner permissions for the whole repo, so they need to approve the initial PR adding the `CODEOWNERS` entry, and they can always approve changes.

Now you can open a PR.
The title should be `feat: add <YOUR LIBRARY NAME> library`.
Review will automatically be requested from `canonical/charmlibs-maintainers`.
Review of this PR will cover whether the name and purpose of the library is appropriate (for example, not redundant with an existing library), as well as the library's design and general code review.
This type of review will be repeated for major version bumps of your library, while all other releases will only require `CODEOWNERS` approval.

## Release your library

You'll probably want to initially add your library with a major version of 0.
In semantic versioning, this communicates that the API design is still in progress, so even when the library is released, you're free to make well-considered breaking changes before your 1.0 release.
You'll also probably want to start with a dev version -- a version number with a `devX` suffix, e.g. `0.1.2.dev3`.
Dev versions are excluded from the `charmlibs` monorepo's release CI, so they won't be released to PyPI.
This means you can make your initial PR and perhaps a few follow ups before your initial release.

To make a release, you'll first need to [set up trusted publishing on PyPI for your library](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).
Remember that the package name should be `charmlibs-<YOUR LIBRARY NAME>`.
The repository owner is `canonical`, the repository name is `charmlibs`, and the workflow name is `publish.yaml`.
You should also set this up on [test.pypi.org](https://test.pypi.org).
You can run the `publish` job manually to release to `test.pypi.org` before your real release.

When you're ready to make a release, make a PR that bumps your library's version to a non-dev version.
This will automatically trigger a release on merge.
Every release should be accompanied by an entry in your library's `CHANGELOG.md` with the following format:
```markdown
# A.B.C - N Month 20XX

...
```
That is, a heading with the version number, separated by spaces and a hyphen from the release date.
The body of the section should include a meaningful description of the changes in this release.
This could be a bulleted list of commits, or a short paragraph, or both.
