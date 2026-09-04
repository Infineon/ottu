---
name: add-test-verify
description: 'Write pytest unit tests for the functions currently being worked on, run `uv run pytest`, and iterate until coverage is maximized. Use when the user asks to add tests, write unit tests, cover a new function, improve or increase test coverage, fix failing tests, or verify changes with pytest in this repo.'
argument-hint: 'Optional: file, module, or function to target (defaults to recently changed code)'
---

# Add Tests and Verify Coverage

Produces new/updated tests under `tests/`, a passing `uv run pytest` run, and a coverage report where every reachable line of the targeted code is covered or explicitly justified.

## When to Use

- New or modified functions in `ottu/` need unit tests
- Coverage for a module or function must be raised
- A change must be verified before commit or PR

## Procedure

### 1. Identify the target
- Use the user's argument if given. Otherwise infer from the active editor file and `git --no-pager diff` / `git --no-pager diff --cached`.
- Read the target source fully before writing tests. Never write tests from a guessed signature.
- List every branch: return paths, `if`/`else`, loops, exception handlers, early returns, CLI options/flags.

### 2. Inspect existing tests
- Test files live in `tests/`, named `test_<module>.py` (e.g. `tests/test_cli.py`).
- Match the existing style: plain `pytest` functions, `click.testing.CliRunner` for CLI commands, `tmp_path`/`monkeypatch` fixtures instead of real I/O or env mutation.
- Extend an existing test file when one matches the module; only create a new file when none exists.

### 3. Write the tests
- One assertion focus per test; name tests `test_<function>_<behavior>`.
- Cover, per target function: happy path, each branch, boundary/empty inputs, and error paths via `pytest.raises`.
- For CLI commands assert both `result.exit_code` and `result.output`.
- Do not modify source code to make tests pass unless a genuine bug is found — if one is, report it to the user before changing behavior.

### 4. Run
```bash
uv run pytest --cov-fail-under=90
```
Coverage is already wired via `addopts = "--cov=ottu --cov-report=xml --cov-report=term-missing"` in `pyproject.toml`, so the terminal output includes a `Missing` column. Total coverage must be **above 90%** — the run fails otherwise.

### 5. Iterate
Loop until the completion checks pass:
1. Fix failures first — diagnose the actual cause, do not retry the same test unchanged.
2. Read the `Missing` line numbers for the target module and map each to a source line.
3. Add a test that exercises those lines; re-run.
4. If a line is genuinely unreachable or not worth testing (defensive guard, `__main__` block), leave it and note why — do not add `# pragma: no cover` without asking the user.

Keep iterating while total coverage is at or below 90%. Stop when coverage is above 90% and only justified-uncovered lines remain, or when coverage stops improving across two consecutive rounds — in that case report the blocker instead of lowering the threshold.

### 6. Report
Summarize: tests added (with file links), pass/fail counts, coverage before → after for the target module, and any lines left uncovered with justification.

## Completion Checks

- [ ] `uv run pytest --cov-fail-under=90` exits 0
- [ ] Total coverage is above 90%
- [ ] Every new/changed function in the target has at least one test per branch
- [ ] Coverage for the target module improved, and remaining misses are justified in the summary
- [ ] No source behavior changed solely to satisfy a test
