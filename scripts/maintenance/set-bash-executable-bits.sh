#!/usr/bin/env bash
set -euo pipefail

SKIP_GIT_INDEX=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-git-index|-SkipGitIndex)
      SKIP_GIT_INDEX=true
      shift
      ;;
    --help|-Help)
      cat <<'USAGE'
Usage:
  ./set-bash-executable-bits.sh [--skip-git-index]

Options:
  --skip-git-index | -SkipGitIndex
      Mark Bash scripts executable on the local filesystem only, without updating the Git index.
USAGE
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

inside_git_repository=false
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  inside_git_repository=true
fi

while IFS= read -r -d '' script; do
  chmod +x "$script"

  if [[ "$inside_git_repository" == true && "$SKIP_GIT_INDEX" != true ]]; then
    if git check-ignore -q -- "$script"; then
      echo "Skipped ignored Bash script: $script"
      continue
    fi

    git update-index --add --chmod=+x -- "$script"
  fi
done < <(find scripts -type f -name '*.sh' -print0 | sort -z)

if [[ "$SKIP_GIT_INDEX" == true ]]; then
  echo 'Bash scripts have been marked executable locally.'
else
  echo 'Bash scripts have been marked executable locally and in the Git index.'
fi
