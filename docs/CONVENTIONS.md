# Conventions

## Commit message format

This project follows a [MicroPython-inspired commit](https://github.com/micropython/micropython/blob/master/CODECONVENTIONS.md#git-commit-conventions) style rather than the default Conventional Commits preset. 

Commit headers should look like:

```text
path/to/file: Capitalized sentence description.
```

Examples:

```text
docs: Fix something.
README: Add command.
ottu/cli: Improve timeout handling.
```

The subject should:

- start with a capital letter
- be written as a sentence
- end with a period
- be kept short and descriptive
- A detailed description can be added in the body of the commit message, separated by a blank line.

## Signed-off-by requirement

All commits must include a `Signed-off-by:` trailer.

Example:

```text
docs: Fix something.

Signed-off-by: Jane Doe <jane@example.com>
```

Use:

```bash
git commit -s -m "docs: Fix something."
```

This requirement is enforced by commitlint.

## Tool requirements

To run the commit message checks locally, install:

- Python
- uv (recommended) or pip
- Node.js 20+
- npm
- pre-commit

### Recommended setup with uv

```bash
uv sync --extra dev
uv run pre-commit install --hook-type commit-msg
```

### Manual setup without uv

```bash
python -m pip install pre-commit
npm install --save-dev @commitlint/cli @commitlint/config-conventional
pre-commit install --hook-type commit-msg
```

### Pip-only alternative for pre-commit

If you only want the local git hook and do not need the uv environment manager, you can install pre-commit directly with pip and register the hook:

```bash
python -m pip install pre-commit
pre-commit install --hook-type commit-msg
```

> commitlint requires Node 20+ in this project. Node 18 is too old for the dependency stack used by the current commitlint setup.
