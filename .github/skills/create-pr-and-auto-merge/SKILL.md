---
name: create-pr-and-auto-merge
description: 'Create a GitHub pull request from the current branch without interactive prompts, request reviewers, and enable automatic merging after required GitHub Actions checks pass.'
argument-hint: '--title "..." --reviewer "owner/team" [--body "..."] [--base main] [--merge-method rebase]'
user-invocable: true
---

# Create Pull Request and Auto-Merge

Create a pull request from the current branch using explicit `gh` arguments and
configure GitHub to merge it automatically after required status checks and
branch-protection requirements pass.

## Requirements

- Run from a Git repository.
- Authenticate `gh` before invoking the skill: `gh auth status`.
- The current branch must not be `main` or the configured base branch.
- The current branch should contain the intended commits.
- The repository must allow pull requests and auto-merge.

## Usage

Run the bundled script with a title and reviewer:

```bash
./.github/skills/create-pr-and-auto-merge/scripts/create-pr-and-auto-merge.sh \
  --title "Add configurable test discovery" \
  --reviewer "Infineon/epe-devops"
```

Optional arguments:

- `--body TEXT`: Pull request body. Defaults to an empty body.
- `--reviewer USERS_OR_TEAMS`: Reviewer login, team, or comma-separated list.
- `--base BRANCH`: Target branch. Defaults to `main`.
- `--merge-method METHOD`: `merge`, `squash`, or `rebase`. Defaults to `rebase`.
- `--no-push`: Do not push the current branch before creating the PR.

All options are passed explicitly. The script never opens an editor or waits
for interactive input.

## Procedure

1. Confirm the working tree and current branch are ready.
2. Confirm `gh auth status` succeeds.
3. Run the script with a non-empty `--title` and `--reviewer`.
4. The script pushes the branch unless `--no-push` is provided.
5. The script runs `gh pr create` with the current branch, title, body, base,
   and reviewer.
6. The script runs `gh pr merge --auto` with the selected merge method.
7. GitHub merges the PR automatically once required remote checks and branch
   protection rules pass.

The script prints the pull request URL and the auto-merge configuration result.
It does not use `gh pr checks --watch`, because auto-merge is handled by
GitHub after the command exits.
