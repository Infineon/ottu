Development Setup
=================

This guide describes how to set up a local development environment for ottu,
run validation checks, build documentation, and prepare releases.

Tools Installation
------------------

Install uv:

.. code-block:: bash

   curl -LsSf https://astral.sh/uv/install.sh | sh

Install project tooling:

.. code-block:: bash

   uv sync --all-groups --all-extras

You can also install a partial set of tools for development, testing, and documentation if
you are working on a specific part of the project.

See `uv sync <https://docs.astral.sh/uv/reference/cli/#uv-sync>`_ for details on *groups* and *extras*,
and explore the ``pyproject.toml`` file for the specific groups defined for this project.

Build and Run
--------------

Build and run the utility (in the uv environment):

.. code-block:: bash

   uv run ottu --help

Add and Run Tests
-----------------

Add new tests under ``tests/`` (for example, ``tests/test_cli.py``).

Run the test suite:

.. code-block:: bash

   uv run pytest

Generate the coverage report using:

.. code-block:: bash

   uv run pytest --cov=ottu --cov-report=term-missing --cov-report=html

The HTML coverage report is generated under ``htmlcov/index.html`` and can be opened in your browser.

Add Documentation
--------------------

Add or update documentation under ``docs/``.

Generate the documentation (from the root directory):

.. code-block:: bash

   uv run -- make -C docs html

You can then view the generated HTML documentation in your browser locally by opening ``docs/build/html/index.html``.

Automatic Docs Build
~~~~~~~~~~~~~~~~~~~~

To avoid manually rebuilding docs after each change, use `sphinx-autobuild`:

.. code-block:: bash

   uv run -- sphinx-autobuild docs docs/build/html

This will start a local web server (typically at ``http://127.0.0.1:8000``)
and automatically rebuild the documentation whenever you save changes to the source files.

Pre-Commit and Push
-------------------

Ensure you have the following tools installed:

- `Node.js <https://nodejs.org/>`_ 20+
- `npm <https://www.npmjs.com/>`_

Install the pre-commit hook used by this repository:

.. code-block:: bash

   uv run pre-commit install --hook-type commit-msg

This hook helps ensure the following conventions before you push changes:

- :ref:`Commit message format <conventions-commit-message-format>`
- :ref:`Code format <conventions-code-format>`
- :ref:`Code style and lint conventions <conventions-code-style-lint>`
- :ref:`Type checking <conventions-type-checking>`
- Code spelling via ``codespell``

Package Publish
---------------

The ``publish`` CI workflow automatically publishes releases to `PyPI <https://pypi.org/project/ottu/>`_ when a semver ``x.y.z`` (no ``v`` prefix) tag is pushed:

.. code-block:: bash

   git tag 1.0.0
   git push origin 1.0.0

The workflow runs checks (format, lint, type, tests), builds the distribution, and publishes to `PyPI <https://pypi.org/project/ottu/>`_.

Local Dry Run
~~~~~~~~~~~~~

To inspect the built distribution without publishing:

.. code-block:: bash

   uv build
   tar tzf dist/*.tar.gz   # source dist contents
   unzip -l dist/*.whl     # wheel contents

To do a full publish dry run locally, set a `PyPI <https://pypi.org/>`_ API token (scoped to the project):

.. code-block:: bash

   export UV_PUBLISH_TOKEN=pypi-<your-token>
   uv publish --dry-run