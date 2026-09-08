#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: create-commit.sh --scope SCOPE --subject SUBJECT [OPTIONS]

Required:
  --scope SCOPE                 File, module, or directory scope
  --subject SUBJECT             Capitalized sentence ending with a period

Optional:
  --description TEXT            Extended commit description
  --description-file FILE       Read the extended description from FILE
  -h, --help                    Show this help
EOF
}

scope=""
subject=""
description=""
description_file=""

while (($# > 0)); do
    case "$1" in
        --scope)
            [[ $# -ge 2 ]] || { echo "--scope requires a value" >&2; exit 2; }
            scope="$2"
            shift 2
            ;;
        --subject)
            [[ $# -ge 2 ]] || { echo "--subject requires a value" >&2; exit 2; }
            subject="$2"
            shift 2
            ;;
        --description)
            [[ $# -ge 2 ]] || { echo "--description requires a value" >&2; exit 2; }
            description="$2"
            shift 2
            ;;
        --description-file)
            [[ $# -ge 2 ]] || { echo "--description-file requires a value" >&2; exit 2; }
            description_file="$2"
            shift 2
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

[[ -n "$scope" ]] || { echo "--scope is required" >&2; exit 2; }
[[ -n "$subject" ]] || { echo "--subject is required" >&2; exit 2; }
[[ -z "$description" || -z "$description_file" ]] || {
    echo "--description and --description-file are mutually exclusive" >&2
    exit 2
}

[[ "$scope" =~ ^[A-Za-z0-9_./-]+$ ]] || {
    echo "--scope must contain only letters, numbers, '_', '.', '/', or '-'" >&2
    exit 2
}
[[ "$subject" =~ ^[A-Z] ]] || {
    echo "--subject must start with an uppercase letter" >&2
    exit 2
}
[[ "$subject" == *. ]] || {
    echo "--subject must end with a period" >&2
    exit 2
}

header="$scope: $subject"
(( ${#header} <= 78 )) || {
    printf 'Commit header is %d characters; maximum is 78.\n' "${#header}" >&2
    exit 2
}

validate_description() {
    local line line_number=0
    while IFS= read -r line || [[ -n "$line" ]]; do
        ((line_number += 1))
        if (( ${#line} > 78 )); then
            printf 'Commit description line %d is %d characters; maximum is 78.\n' \
                "$line_number" "${#line}" >&2
            return 2
        fi
    done <<< "$1"
}

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "Not inside a Git repository." >&2
    exit 1
}
cd "$repo_root"

git diff --cached --quiet && {
    echo "No staged changes found; stage one focused change first." >&2
    exit 1
}

git diff --cached --check

commit_args=(-s -m "$header")
if [[ -n "$description_file" ]]; then
    [[ -f "$description_file" ]] || {
        echo "Description file does not exist: $description_file" >&2
        exit 1
    }
    description=$(<"$description_file")
    validate_description "$description"
    commit_args+=(-m "$description")
elif [[ -n "$description" ]]; then
    validate_description "$description"
    commit_args+=(-m "$description")
fi

git commit "${commit_args[@]}"
printf 'Created commit: %s\n' "$(git rev-parse --short HEAD)"
