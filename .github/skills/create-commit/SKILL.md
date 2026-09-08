---
name: create-commit
description: "Create a scoped signed-off Git commit using this repository's commitlint convention, with an optional extended description. Use when the user asks to commit changes, create a commit message, split changes into focused commits, or commit with a body."
argument-hint: '--scope "path/to/file" --subject "Capitalized sentence." [--description "..."] [--description-file FILE]'
user-invocable: true
---

# Create Commit

Create one focused Git commit using the repository's commitlint convention.
The bundled script validates the subject, requires staged changes, supports an
optional extended description, and invokes the repository hooks through
`git commit -s`.

## Commit Convention

The commit header must have this shape:

```text
scope: Capitalized sentence description.
```

Rules enforced by this skill:

- `scope` is required and normally identifies the changed file, module, or directory, for example `ottu/test`, `ottu/suite`, or `tests/test_test`.
- The subject must begin with an uppercase letter.
- The subject must end with a period.
- The complete header must be no longer than 78 characters.
- Every line of the optional extended description must be no longer than 78 characters.
- The commit includes a `Signed-off-by` trailer.
- The commit hook must pass; do not bypass it with `--no-verify`.

## Usage

Stage only the files for one logical change, then run:

```bash
./.github/skills/create-commit/scripts/create-commit.sh \
  --scope "ottu/test" \
  --subject "Use TestPathContext for selector resolution."
```

With an extended description:

```bash
./.github/skills/create-commit/scripts/create-commit.sh \
  --scope "ottu/suite" \
  --subject "Pass TestPathContext to Test creation." \
  --description "Centralize path-resolution context construction in Suite and pass the shared context to Test.from_inputs."
```

For a longer body, use a file:

```bash
./.github/skills/create-commit/scripts/create-commit.sh \
  --scope "tests/test_test" \
  --subject "Cover TestPathContext resolver API." \
  --description-file /tmp/commit-description.txt
```

`--description` and `--description-file` are mutually exclusive. The body is
optional and is placed after a blank line below the validated header.

## Multiple Focused Commits

When a branch contains several logical changes, use the bundled multi-commit
helper with a tab-separated plan file. Each line defines one commit:

```text
  scope<TAB>subject<TAB>description-file-or-`-`<TAB>file1,file2
```

For example:

```text
ottu/test<TAB>Use TestPathContext for selector resolution.<TAB>-<TAB>ottu/test.py
tests/test_test<TAB>Cover TestPathContext resolver API.<TAB>/tmp/test-body.txt<TAB>tests/test_test.py
ottu/suite<TAB>Pass TestPathContext to Test creation.<TAB>-<TAB>ottu/suite.py
```

Run it with:

```bash
./.github/skills/create-commit/scripts/create-commits.sh \
  --plan /tmp/ottu-commit-plan.tsv
```

The helper:

- Requires the index to be clean before starting.
- Stages only the files listed for the current group.
- Creates each commit through `create-commit.sh`, so every group gets the same header validation, hooks, and sign-off trailer.
- Refuses files that appear in more than one group.
- Leaves unrelated unstaged and untracked files untouched.
- Stops on the first failed validation or hook, leaving the current group staged for inspection.

Use one commit group when implementation and tests form one inseparable logical
change. Use separate groups when the repository convention treats their scopes
as independent reviewable changes.

## Procedure

1. Inspect `git status` and `git diff --cached`.
2. Stage only one coherent logical change.
3. Choose a scope matching the changed file or directory.
4. Write a capitalized sentence subject ending in a period.
5. Add `--description` or `--description-file` when the change needs context.
6. Run the bundled script.
7. The script validates the staged diff, creates a signed-off commit, and lets repository hooks run normally.
9. For several logical commits, prepare a plan file and run `create-commits.sh`.
8. Inspect `git show --stat --format=fuller HEAD` after the commit.

## Safety

- The script never stages files automatically.
- Unstaged changes are left untouched.
- Untracked files are not included unless explicitly staged first.
- The script refuses to commit when there are no staged changes.
- The script does not amend, reset, rebase, or force-push.
- Do not combine unrelated files merely to reduce the number of commits; create separate focused commits.

## Completion Checks

- [ ] The intended files were staged explicitly.
- [ ] The header matches `scope: Capitalized sentence.`.
- [ ] The header is at most 78 characters.
- [ ] Every extended-description line is at most 78 characters.
- [ ] The commit hook passes.
- [ ] The commit has a `Signed-off-by` trailer.
- [ ] Unrelated unstaged or untracked files remain untouched.
- [ ] Multi-commit plans assign each changed file to at most one commit group.
