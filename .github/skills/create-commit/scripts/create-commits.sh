#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: create-commits.sh --plan FILE

The plan is tab-separated, one commit per line:
  SCOPE<TAB>SUBJECT<TAB>DESCRIPTION_FILE<TAB>FILE1,FILE2,...

Use '-' as DESCRIPTION_FILE when a commit body is not needed.
Blank lines and lines beginning with '#' are ignored.
EOF
}

plan_file=""

while (($# > 0)); do
    case "$1" in
        --plan)
            [[ $# -ge 2 ]] || { echo "--plan requires a value" >&2; exit 2; }
            plan_file="$2"
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

[[ -n "$plan_file" ]] || { echo "--plan is required" >&2; exit 2; }
[[ -f "$plan_file" ]] || { echo "Plan file does not exist: $plan_file" >&2; exit 1; }

git rev-parse --show-toplevel >/dev/null
git diff --cached --quiet || {
    echo "Staged changes already exist; unstage them before using a commit plan." >&2
    exit 1
}

repo_root=$(git rev-parse --show-toplevel)
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

scopes=()
subjects=()
description_files=()
file_groups=()
line_number=0

declare -A seen_files=()

while IFS=$'\t' read -r scope subject description_file files extra || [[ -n "$scope$subject$description_file$files$extra" ]]; do
    ((line_number += 1))
    [[ -z "$scope" || "${scope:0:1}" == "#" ]] && continue

    [[ -n "$scope" && -n "$subject" && -n "$files" && -z "$extra" ]] || {
        echo "Invalid plan line $line_number; expected four tab-separated fields." >&2
        exit 2
    }

    [[ "$description_file" == "-" ]] && description_file=""

    if [[ -n "$description_file" && ! -f "$description_file" ]]; then
        echo "Description file on line $line_number does not exist: $description_file" >&2
        exit 1
    fi

    IFS=',' read -r -a group_files <<< "$files"
    ((${#group_files[@]} > 0)) || {
        echo "No files listed on plan line $line_number." >&2
        exit 2
    }
    for file in "${group_files[@]}"; do
        [[ -n "$file" ]] || {
            echo "Empty file path on plan line $line_number." >&2
            exit 2
        }
        [[ -z "${seen_files[$file]+set}" ]] || {
            echo "File appears in more than one commit group: $file" >&2
            exit 2
        }
        seen_files["$file"]="$line_number"
        [[ -e "$repo_root/$file" ]] || {
            echo "Planned file does not exist: $file" >&2
            exit 1
        }
    done

    scopes+=("$scope")
    subjects+=("$subject")
    description_files+=("$description_file")
    file_groups+=("$files")
done < "$plan_file"

((${#scopes[@]} > 0)) || { echo "Plan contains no commit groups." >&2; exit 2; }

for index in "${!scopes[@]}"; do
    IFS=',' read -r -a group_files <<< "${file_groups[$index]}"
    git add -- "${group_files[@]}"

    commit_args=(
        --scope "${scopes[$index]}"
        --subject "${subjects[$index]}"
    )
    if [[ -n "${description_files[$index]}" ]]; then
        commit_args+=(--description-file "${description_files[$index]}")
    fi

    "$script_dir/create-commit.sh" "${commit_args[@]}"
done

printf 'Created %d commits from %s\n' "${#scopes[@]}" "$plan_file"
