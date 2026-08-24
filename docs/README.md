# ottu documentation

The ottu documentation can be found at:

    https://ottu.readthedocs.io/en/latest/

The documentation you see there is generated from the files in the docs tree:

    https://github.com/infineon/ottu/tree/main/docs

Each release generates a new version of the documentation, based on the version number (semver) `x.y.z`. For example, for version `0.1.0`, the docs can be found at:

    https://ottu.readthedocs.io/en/0.1.0/


## Building the docs locally

If you're making changes to the documentation, you may want to build the
documentation locally so that you can preview your changes.

Install uv (if needed):

    curl -LsSf https://astral.sh/uv/install.sh | sh

Install project and docs dependencies with uv:

    uv sync --group docs

From the root directory, build the docs:

    uv run -- make -C docs html

You'll find the index page at `ottu/docs/build/html/index.html`.

### Autobuild

For a more convenient development experience, you can use `sphinx-autobuild`
to automatically rebuild and serve the documentation when you make changes:

    uv sync --group docs-dev

Then run from the `docs` directory:

    uv run -- sphinx-autobuild docs docs/build/html

This will start a local web server (typically at `http://127.0.0.1:8000`)
and automatically rebuild the documentation whenever you save changes to the source files.

## Publishing to ReadTheDocs

The ottu documentation is hosted on ReadTheDocs. 

Read the Docs is already configured to rebuild the documentation on the following events:

 - A new release is published on GitHub
 - A new commit is pushed to the `main` branch
 - A pull request is opened against the `main` branch

## Managing the ReadTheDocs project

This project is hosted under the Infineon Makers ReadTheDocs team account.
If you need to access the ReadTheDocs project settings, please contact the maintainers of this repository.
