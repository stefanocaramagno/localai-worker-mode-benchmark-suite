#!/usr/bin/env bash
set -euo pipefail

CYCLE_CONFIG=""
DEPLOYMENT_PROFILE=""
ACTION="deploy"
KUBECONFIG_PATH=""
OUTPUT_ROOT=""
DEPLOYMENT_ID=""
DRY_RUN="0"
SKIP_CLUSTER_VALIDATION_GATE="0"
SKIP_SMOKE_TEST="0"
BASE_URL=""
NO_PORT_FORWARD="0"
WRITE_LATEST_ALIASES="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cycle-config) CYCLE_CONFIG="$2"; shift 2 ;;
    --deployment-profile) DEPLOYMENT_PROFILE="$2"; shift 2 ;;
    --action) ACTION="$2"; shift 2 ;;
    --kubeconfig) KUBECONFIG_PATH="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --deployment-id) DEPLOYMENT_ID="$2"; shift 2 ;;
    --dry-run) DRY_RUN="1"; shift ;;
    --skip-cluster-validation-gate) SKIP_CLUSTER_VALIDATION_GATE="1"; shift ;;
    --skip-smoke-test) SKIP_SMOKE_TEST="1"; shift ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    --no-port-forward) NO_PORT_FORWARD="1"; shift ;;
    --write-latest-aliases) WRITE_LATEST_ALIASES="1"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/run-provider-backed-localai-deployment.py"

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
  echo "Provider-backed LocalAI deployment runner not found: $PYTHON_SCRIPT" >&2
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
  "--action" "$ACTION"
)

[[ -n "$DEPLOYMENT_PROFILE" ]] && ARGS+=("--deployment-profile" "$DEPLOYMENT_PROFILE")
[[ -n "$KUBECONFIG_PATH" ]] && ARGS+=("--kubeconfig" "$KUBECONFIG_PATH")
[[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
[[ -n "$DEPLOYMENT_ID" ]] && ARGS+=("--deployment-id" "$DEPLOYMENT_ID")
[[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
[[ "$SKIP_CLUSTER_VALIDATION_GATE" == "1" ]] && ARGS+=("--skip-cluster-validation-gate")
[[ "$SKIP_SMOKE_TEST" == "1" ]] && ARGS+=("--skip-smoke-test")
[[ -n "$BASE_URL" ]] && ARGS+=("--base-url" "$BASE_URL")
[[ "$NO_PORT_FORWARD" == "1" ]] && ARGS+=("--no-port-forward")
[[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")

printf '%s\n' "==============================================="
printf '%s\n' " provider-backed LocalAI deployment"
printf '%s\n' "==============================================="
printf 'Repository : %s\n' "$REPO_ROOT"
printf 'Cycle      : %s\n' "$CYCLE_CONFIG"
printf 'Action     : %s\n' "$ACTION"
printf 'Dry run    : %s\n\n' "$DRY_RUN"

exec "$PYTHON_BIN" "${ARGS[@]}"
