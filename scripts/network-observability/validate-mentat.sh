#!/usr/bin/env bash
set -euo pipefail

PROFILE_CONFIG=""
ACTION="validate"
KUBECONFIG_PATH=""
OUTPUT_ROOT=""
RUN_ID=""
DRY_RUN="0"
SKIP_PROMETHEUS_QUERY="0"
WRITE_LATEST_ALIASES="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-config) PROFILE_CONFIG="$2"; shift 2 ;;
    --action) ACTION="$2"; shift 2 ;;
    --kubeconfig) KUBECONFIG_PATH="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --dry-run) DRY_RUN="1"; shift ;;
    --skip-prometheus-query) SKIP_PROMETHEUS_QUERY="1"; shift ;;
    --write-latest-aliases) WRITE_LATEST_ALIASES="1"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNNER="$SCRIPT_DIR/validate-mentat.py"

if [[ ! -f "$RUNNER" ]]; then
  echo "Mentat network observability runner not found: $RUNNER" >&2
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "Neither python3 nor python is available in PATH." >&2
  exit 1
fi

[[ -n "$PROFILE_CONFIG" ]] || PROFILE_CONFIG="$REPO_ROOT/config/network-observability/profiles/NO_MENTAT_C9.json"

ARGS=(
  "$RUNNER"
  "--repo-root" "$REPO_ROOT"
  "--profile-config" "$PROFILE_CONFIG"
  "--action" "$ACTION"
)

[[ -n "$KUBECONFIG_PATH" ]] && ARGS+=("--kubeconfig" "$KUBECONFIG_PATH")
[[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
[[ -n "$RUN_ID" ]] && ARGS+=("--run-id" "$RUN_ID")
[[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
[[ "$SKIP_PROMETHEUS_QUERY" == "1" ]] && ARGS+=("--skip-prometheus-query")
[[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")

printf '%s\n' "==============================================="
printf '%s\n' " Mentat network observability"
printf '%s\n' "==============================================="
printf 'Repository : %s\n' "$REPO_ROOT"
printf 'Profile    : %s\n' "$PROFILE_CONFIG"
printf 'Action     : %s\n' "$ACTION"
printf 'Dry run    : %s\n\n' "$DRY_RUN"

exec "$PYTHON_CMD" "${ARGS[@]}"
