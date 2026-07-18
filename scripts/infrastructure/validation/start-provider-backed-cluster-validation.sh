#!/usr/bin/env bash
set -euo pipefail

CYCLE_CONFIG=""
CLUSTER_VALIDATION_PROFILE=""
VALIDATION_PROFILE=""
KUBECONFIG_PATH=""
OUTPUT_ROOT=""
VALIDATION_ID=""
DRY_RUN="0"
SKIP_PREVALIDATION_GATE="0"
ALLOW_METRICS_WARNING="0"
WRITE_LATEST_ALIASES="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cycle-config) CYCLE_CONFIG="$2"; shift 2 ;;
    --cluster-validation-profile) CLUSTER_VALIDATION_PROFILE="$2"; shift 2 ;;
    --validation-profile) VALIDATION_PROFILE="$2"; shift 2 ;;
    --kubeconfig) KUBECONFIG_PATH="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --validation-id) VALIDATION_ID="$2"; shift 2 ;;
    --dry-run) DRY_RUN="1"; shift ;;
    --skip-prevalidation-gate|--skip-pre-validation-gate) SKIP_PREVALIDATION_GATE="1"; shift ;;
    --allow-metrics-warning) ALLOW_METRICS_WARNING="1"; shift ;;
    --write-latest-aliases) WRITE_LATEST_ALIASES="1"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/run-provider-backed-cluster-validation.py"

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
  echo "Provider-backed cluster validation runner not found: $PYTHON_SCRIPT" >&2
  exit 1
fi

if [[ -z "$CYCLE_CONFIG" ]]; then
  CYCLE_CONFIG="$REPO_ROOT/config/experimental-cycles/C1.json"
fi

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Neither python nor python3 is available in PATH." >&2
  exit 1
fi

ARGS=(
  "$PYTHON_SCRIPT"
  "--repo-root" "$REPO_ROOT"
  "--cycle-config" "$CYCLE_CONFIG"
)

[[ -n "$CLUSTER_VALIDATION_PROFILE" ]] && ARGS+=("--cluster-validation-profile" "$CLUSTER_VALIDATION_PROFILE")
[[ -n "$VALIDATION_PROFILE" ]] && ARGS+=("--validation-profile" "$VALIDATION_PROFILE")
[[ -n "$KUBECONFIG_PATH" ]] && ARGS+=("--kubeconfig" "$KUBECONFIG_PATH")
[[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
[[ -n "$VALIDATION_ID" ]] && ARGS+=("--validation-id" "$VALIDATION_ID")
[[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
[[ "$SKIP_PREVALIDATION_GATE" == "1" ]] && ARGS+=("--skip-prevalidation-gate")
[[ "$ALLOW_METRICS_WARNING" == "1" ]] && ARGS+=("--allow-metrics-warning")
[[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")

printf '%s\n' "==============================================="
printf '%s\n' " provider-backed cluster validation"
printf '%s\n' "==============================================="
printf 'Repository : %s\n' "$REPO_ROOT"
printf 'Cycle      : %s\n' "$CYCLE_CONFIG"
printf 'Dry run    : %s\n\n' "$DRY_RUN"

exec "$PYTHON_BIN" "${ARGS[@]}"
