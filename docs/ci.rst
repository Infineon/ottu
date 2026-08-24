Continuous Integration
======================

This project enables a set of CI flows to:

- Standardize and validate commit, code, and documentation conventions.
- Validate functionality through unit tests and coverage.
- Automate package release and documentation publishing.

The CI flows are mostly run by GitHub Actions workflows under
:gh_main:`.github/workflows`.
The only exception is the publishing to Read the Docs via a dedicated workflow file
:gh_main:`.readthedocs.yaml`.

The summary of the CI flows is described below, grouped into:

 - Conventions
 - Testing
 - Documentation
 - Package release

Conventions Workflows
#####################

Commit Message Check
--------------------

- Workflow file: :gh_main:`.github/workflows/commit-check.yml`.
- Checks: commit message format and required sign-off trailer.
- Tooling: `commitlint <https://commitlint.js.org/>`_ with repository :gh_main:`commitlint.config.js`.
- Conventions enforced: See :doc:`conventions` for commit message format and sign-off requirements.

Format Check
-------------

- Workflow file: :gh_main:`.github/workflows/format-check.yml`.
- Checks: Python code formatting consistency.
- Tooling: `Ruff formatter <https://docs.astral.sh/ruff/formatter/>`_.
- Conventions enforced: See :doc:`conventions` for code formatting rules.

Lint and Type Check
-------------------

- Workflow file: :gh_main:`.github/workflows/lint.yml`.
- Checks: static lint issues and typing issues.
- Tooling: `Ruff linter <https://docs.astral.sh/ruff/linter/>`_ and `mypy <https://mypy.readthedocs.io/>`_.
- Conventions enforced: See :doc:`conventions` for linting and typing rules.

Spelling Check
--------------

- Workflow file: :gh_main:`.github/workflows/codespell.yml`.
- Checks: spelling mistakes in repository text files.
- Tooling: `codespell <https://github.com/codespell-project/codespell>`_.
- Conventions enforced: spelling quality and terms from ``[tool.codespell]`` configuration in ``pyproject.toml``.

Testing Workflows
##################

Tests and Coverage
-------------------

- Workflow file: :gh_main:`.github/workflows/tests.yml`.
- Checks: unit tests across supported Python versions. Additionally, it generates a coverage report and uploads it to `Coveralls.io <https://coveralls.io/>`_.
- Tooling: `pytest <https://docs.pytest.org/>`_.
- External integration: `Coveralls.io <https://coveralls.io/>`_.

Documentation Workflows
#######################

Link Check
----------

- Workflow file: :gh_main:`.github/workflows/links-check.yml`.
- Checks: broken links in repository content.
- Tooling: `Lychee <https://github.com/lycheeverse/lychee>`_ (reusable workflow).

Docs Build Check
----------------

- Workflow file: :gh_main:`.github/workflows/docs.yml`.
- Checks: documentation can be built successfully.
- Tooling: `sphinx-build <https://www.sphinx-doc.org/en/master/man/sphinx-build.html>`_.

Docs Publish
------------

- Workflow file: :gh_main:`.readthedocs.yaml`.
- Automates: builds and publishes the documentation to `Read The Docs <https://readthedocs.org/>`_ on:

    - A new release is published on GitHub
    - A new commit is pushed to the `main` branch
    - A pull request is opened against the `main` branch (for preview builds)

- Tooling: `sphinx-build <https://www.sphinx-doc.org/en/master/man/sphinx-build.html>`_ environment.
- External integration: `Read The Docs <https://readthedocs.org/>`_.

Package Release Workflows
#########################

Package Publish
---------------

- Workflow file: :gh_main:`.github/workflows/publish.yml`.
- Automates: build and publish the package on `PyPI <https://pypi.org/>`_ on a tag (semver `x.y.z`). Prior to publishing, the workflow runs all checks (format, lint, type, tests).
- Tooling: PyPI publish automation + (Ruff, mypy, pytest, package build).
- Conventions enforced: See :doc:`conventions` for version format and release tag requirements.
- External integration: `PyPI <https://pypi.org/>`_.

External Integrations
#####################

The external integrations require individual account and additional project setup in their respective platforms:

- `Read The Docs <https://readthedocs.org/>`_ for documentation hosting and publishing.
- `PyPI <https://pypi.org/>`_ for package hosting and publishing.
- `Coveralls.io <https://coveralls.io/>`_ for test coverage reporting.

Their accounts and access are managed by `Infineon Makers`, the maintainers of this repository.

If you need updates to the configuration of these integrations, please contact the maintainers.
