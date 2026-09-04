#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: create-pr-and-auto-merge.sh --title TEXT --reviewer USERS_OR_TEAMS [OPTIONS]

Options:
  --title TEXT                 Pull request title (required)
  --reviewer USERS_OR_TEAMS    Reviewer login, team, or comma-separated list (required)
  --body TEXT                  Pull request body (default: empty)
  --base BRANCH                Target branch (default: main)
    --merge-method METHOD        merge, squash, or rebase (default: rebase)
  --no-push                    Do not push the current branch before creating the PR
  -h, --help                   Show this help
EOF
}

title=""
reviewer=""
body=""
base="main"
merge_method="rebase"
no_push=false

while (($# > 0)); do
    case "$1" in
        --title)
            [[ $# -ge 2 ]] || { echo "--title requires a value" >&2; exit 2; }
            title="$2"
            shift 2
            ;;
        --reviewer)
            [[ $# -ge 2 ]] || { echo "--reviewer requires a value" >&2; exit 2; }
            reviewer="$2"
            shift 2
            ;;
        --body)
            [[ $# -ge 2 ]] || { echo "--body requires a value" >&2; exit 2; }
            body="$2"
            shift 2
            ;;
        --base)
            [[ $# -ge 2 ]] || { echo "--base requires a value" >&2; exit 2; }
            base="$2"
            shift 2
            ;;
        --merge-method)
            [[ $# -ge 2 ]] || { echo "--merge-method requires a value" >&2; exit 2; }
            merge_method="$2"
            shift 2
            ;;
        --no-push)
            no_push=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

[[ -n "$title" ]] || { echo "--title is required" >&2; exit 2; }
[[ -n "$reviewer" ]] || { echo "--reviewer is required" >&2; exit 2; }
case "$merge_method" in
    merge|squash|rebase) ;;
    *) echo "--merge-method must be merge, squash, or rebase" >&2; exit 2 ;;
esac

git rev-parse --show-toplevel >/dev/null
git diff --quiet && git diff --cached --quiet || {
    echo "Working tree has uncommitted changes; commit or stash them first." >&2
    exit 1
}

branch=$(git branch --show-current)
[[ -n "$branch" ]] || { echo "Detached HEAD is not supported." >&2; exit 1; }
[[ "$branch" != "$base" ]] || {
    echo "Current branch '$branch' is the base branch; create a feature branch first." >&2
    exit 1
}

gh auth status >/dev/null

if [[ "$no_push" == false ]]; then
    git push --set-upstream origin "$branch"
fi

pr_url=$(gh pr create \
    --head "$branch" \
    --base "$base" \
    --title "$title" \
    --body "$body" \
    --reviewer "$reviewer")
printf 'Pull request: %s\n' "$pr_url"

gh pr merge "$pr_url" --auto "--$merge_method"
printf 'Auto-merge enabled using %s; GitHub will merge after required checks pass.\n' "$merge_method"
