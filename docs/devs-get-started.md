# Developer Getting Started

## Pre-requisites

Install uv (if you do not have it yet):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Build and run from the sources

Install project tooling:

```bash
uv sync --extra dev
```

Run the utility locally:

```bash
uv run ottu --help
```

## Add and run tests

Add new tests under `tests/` (for example, `tests/test_cli.py`).

Run the test suite:

```bash
uv run pytest
```

## Before Pushing your changes

Install the pre-commit hook used by this repository:

```bash
uv run pre-commit install --hook-type commit-msg
```

This ensures the CLI and tests run in the same managed environment, and commit
messages are checked locally before they are accepted.
