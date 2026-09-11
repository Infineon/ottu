# Ottu sandbox project

This is a small, self-contained project for manually trying the Ottu CLI from
the repository checkout. It contains a `.ottu` project marker, an application
placeholder, three flat dummy test files, and three role-oriented test files
under `tests/role/`.
placeholder, three flat dummy test files, and three role-oriented test files
under `role_tests/`.

The current Ottu backend reports which test files it resolves and runs; these
files do not access hardware or execute test functions. They are deliberately
named without the `test_` prefix so the repository's pytest run does not collect
them as unit tests.

## Start here

From this directory, run the CLI from the repository checkout with:

```bash
cd tests/sandbox
uv run --project ../.. ottu run
```

This discovers every file under `tests/` and runs the six dummy test files.

Try the role-qualified fixtures with:

```bash
uv run --project ../.. ottu run \
  --device role=server,port=/dev/ttyUSB0 \
  --device role=client,port=/dev/ttyUSB1 \
  --device role=gateway,port=/dev/ttyUSB2 \
  server=tests/role/server.py \
  client=tests/role/client.py \
  gateway=tests/role/gateway.py
```

## Useful experiments

Run one test by name:
```bash
uv run --project ../.. ottu run tests/boot_check.py
```

Run a glob pattern:

```bash
uv run --project ../.. ottu run "tests/*_check.py"
```

Exclude one discovered test:

```bash
uv run --project ../.. ottu run --exclude tests/excluded_check.py
```

Split the discovered tests across two suite jobs:

```bash
uv run --project ../.. ottu run --jobs 2
```

Use an explicit project and working directory when running from the repository
root instead:

```bash
uv run ottu \
  --project-root tests/sandbox \
  --working-dir tests/sandbox \
  run --pattern "**/*.py"
```
