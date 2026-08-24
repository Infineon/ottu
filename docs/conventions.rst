Conventions
===========

This section summarizes the project conventions for commit messages, code
formatting, linting, and type checking. Following these conventions helps keep
changes consistent and ensures CI validations pass.

.. _conventions-commit-message-format:

Commit Message Format
---------------------

This project follows a `MicroPython-inspired commit <https://github.com/micropython/micropython/blob/master/CODECONVENTIONS.md#git-commit-conventions>`_ style rather than the default Conventional Commits preset.

Commit headers should look like:

.. code-block:: text

   path/to/file: Capitalized sentence description.

Examples:

.. code-block:: text

   docs: Fix something.
   README: Add command.
   ottu/cli: Improve timeout handling.

The subject should:

- start with a capital letter
- be written as a sentence
- end with a period
- be kept short and descriptive
- A detailed description can be added in the body of the commit message, separated by a blank line.

Signed-off-by Requirement
~~~~~~~~~~~~~~~~~~~~~~~~~

All commits must include a ``Signed-off-by:`` trailer.

Example:

.. code-block:: text

   docs: Fix something.

   Signed-off-by: Jane Doe <jane@example.com>

Use:

.. code-block:: bash

   git commit -s -m "docs: Fix something."

This requirement is enforced by `commitlint <https://commitlint.js.org/>`_.

.. _conventions-code-format:

Code Format
-----------

Ruff format is the canonical formatting standard for Python files in this
project. See `Ruff formatter style guide <https://docs.astral.sh/ruff/formatter/#style-guide>`_.

- Scope: Python source and test files.
- Style baseline: Black-compatible formatting behavior.

.. _conventions-code-style-lint:

Code Style and Lint Conventions
-------------------------------

This project uses Ruff for both formatting and linting. The enforced
conventions come from the following rule families configured in
``pyproject.toml``:

- ``E`` and ``W``: pycodestyle (`PEP 8 <https://peps.python.org/pep-0008/>`_ style and warning conventions)
- ``F``: Pyflakes (logical issues such as unused imports/variables)
- ``I``: isort conventions (import ordering and grouping)
- ``UP``: pyupgrade conventions (modern Python syntax/style)

.. _conventions-type-checking:

Type Checking
-------------

Type checking is enforced with `mypy <https://mypy.readthedocs.io/>`_.

- Scope: ``ottu`` package files.
- Policy baseline: strict mode (``strict = true``) configured in ``[tool.mypy]``.

For strict mode details, see the mypy
`strict mode reference <https://mypy.readthedocs.io/en/stable/existing_code.html#introduce-stricter-options>`_.

.. _version-format:

Version Format
--------------

This project uses `Semantic Versioning <https://semver.org/>`_ for release
tags. Non-release builds may include additional generated suffixes that capture
build metadata or VCS state.

Release Tags
~~~~~~~~~~~~

- Format: ``x.y.z``
- Convention: no ``v`` prefix
- Purpose: published releases

Development and Build Variants
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- May include build metadata or VCS-derived identifiers
- Are expected for local, CI, or unreleased development builds
- Do not change the release tag convention for published versions

Examples
~~~~~~~~

.. code-block:: text

    1.0.0
    1.2.3+build.5
    0.1.dev40+g17ec99211.d20260824

In practice, use plain ``x.y.z`` tags for releases and expect suffixed variants
for development or generated builds.







