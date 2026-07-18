#!/usr/bin/env bash
set -euo pipefail

RESULTS_ROOT="results"
JSON_OUTPUT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --results-root)
      RESULTS_ROOT="${2:?Missing value for --results-root}"
      shift 2
      ;;
    --json)
      JSON_OUTPUT=1
      shift
      ;;
    -h|--help)
      cat <<'HELP'
Usage: validate-artifact-portability.sh [--results-root results] [--json]

Validates generated artifacts for non-portable local path references.
HELP
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
VALIDATOR="$REPO_ROOT/scripts/common/artifact_portability.py"

if [[ ! -f "$VALIDATOR" ]]; then
  echo "Common artifact portability validator not found: $VALIDATOR" >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
ARGS=("$VALIDATOR" --repo-root "$REPO_ROOT" --results-root "$RESULTS_ROOT")
if [[ "$JSON_OUTPUT" == "1" ]]; then
  ARGS+=(--json)
fi

exec "$PYTHON_BIN" "${ARGS[@]}"
