#!/usr/bin/env bash
set -euo pipefail

CYCLE_CONFIG=""
PROFILE_CONFIG=""
ACTION="capture"
STAGE=""
KUBECONFIG_PATH=""
NAMESPACE=""
MEASUREMENT_CSV_PREFIX=""
OUTPUT_ROOT=""
OBSERVABILITY_ID=""
DRY_RUN="0"
SKIP_CLUSTER_VALIDATION_GATE="0"
SKIP_APPLICATION_DEPLOYMENT_GATE="0"
WRITE_LATEST_ALIASES="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cycle-config) CYCLE_CONFIG="$2"; shift 2 ;;
    --profile-config) PROFILE_CONFIG="$2"; shift 2 ;;
    --action) ACTION="$2"; shift 2 ;;
    --stage) STAGE="$2"; shift 2 ;;
    --kubeconfig) KUBECONFIG_PATH="$2"; shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --measurement-csv-prefix) MEASUREMENT_CSV_PREFIX="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --observability-id) OBSERVABILITY_ID="$2"; shift 2 ;;
    --dry-run) DRY_RUN="1"; shift ;;
    --skip-cluster-validation-gate) SKIP_CLUSTER_VALIDATION_GATE="1"; shift ;;
    --skip-application-deployment-gate) SKIP_APPLICATION_DEPLOYMENT_GATE="1"; shift ;;
    --write-latest-aliases) WRITE_LATEST_ALIASES="1"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RUNNER="$SCRIPT_DIR/run-minimal-observability.py"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "Neither python3 nor python is available in PATH." >&2
  exit 1
fi

[[ -n "$CYCLE_CONFIG" ]] || CYCLE_CONFIG="$REPO_ROOT/config/experimental-cycles/C1.json"

ARGS=(
  "$RUNNER"
  "--repo-root" "$REPO_ROOT"
  "--cycle-config" "$CYCLE_CONFIG"
  "--action" "$ACTION"
)

[[ -n "$PROFILE_CONFIG" ]] && ARGS+=("--profile-config" "$PROFILE_CONFIG")
[[ -n "$STAGE" ]] && ARGS+=("--stage" "$STAGE")
[[ -n "$KUBECONFIG_PATH" ]] && ARGS+=("--kubeconfig" "$KUBECONFIG_PATH")
[[ -n "$NAMESPACE" ]] && ARGS+=("--namespace" "$NAMESPACE")
[[ -n "$MEASUREMENT_CSV_PREFIX" ]] && ARGS+=("--measurement-csv-prefix" "$MEASUREMENT_CSV_PREFIX")
[[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
[[ -n "$OBSERVABILITY_ID" ]] && ARGS+=("--observability-id" "$OBSERVABILITY_ID")
[[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
[[ "$SKIP_CLUSTER_VALIDATION_GATE" == "1" ]] && ARGS+=("--skip-cluster-validation-gate")
[[ "$SKIP_APPLICATION_DEPLOYMENT_GATE" == "1" ]] && ARGS+=("--skip-application-deployment-gate")
[[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")

exec "$PYTHON_CMD" "${ARGS[@]}"
