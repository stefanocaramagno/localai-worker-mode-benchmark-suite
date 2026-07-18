#!/usr/bin/env bash
set -euo pipefail

CYCLE_CONFIG=""
PROVISIONING_PROFILE=""
ACTION="provision"
TOOL_PATH="proxmox-k3s"
PROVIDER_CONFIG=""
CLUSTER_LIFECYCLE_MODE=""
DESTROY_CLUSTER_AFTER_CYCLE=""
DRY_RUN="0"
CONFIRM_DELETE="0"
RUN_ID=""
OUTPUT_ROOT=""
WRITE_LATEST_ALIASES="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cycle-config) CYCLE_CONFIG="$2"; shift 2 ;;
    --provisioning-profile) PROVISIONING_PROFILE="$2"; shift 2 ;;
    --action) ACTION="$2"; shift 2 ;;
    --tool|--tool-path) TOOL_PATH="$2"; shift 2 ;;
    --provider-config) PROVIDER_CONFIG="$2"; shift 2 ;;
    --cluster-lifecycle-mode) CLUSTER_LIFECYCLE_MODE="$2"; shift 2 ;;
    --destroy-cluster-after-cycle) DESTROY_CLUSTER_AFTER_CYCLE="$2"; shift 2 ;;
    --dry-run) DRY_RUN="1"; shift ;;
    --confirm-delete) CONFIRM_DELETE="1"; shift ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --write-latest-aliases) WRITE_LATEST_ALIASES="1"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/run-provider-backed-provisioning.py"

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
  echo "Provider-backed provisioning runner not found: $PYTHON_SCRIPT" >&2
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
  "--tool-path" "$TOOL_PATH"
)

[[ -n "$PROVISIONING_PROFILE" ]] && ARGS+=("--provisioning-profile" "$PROVISIONING_PROFILE")
[[ -n "$PROVIDER_CONFIG" ]] && ARGS+=("--provider-config" "$PROVIDER_CONFIG")
[[ -n "$CLUSTER_LIFECYCLE_MODE" ]] && ARGS+=("--cluster-lifecycle-mode" "$CLUSTER_LIFECYCLE_MODE")
[[ -n "$DESTROY_CLUSTER_AFTER_CYCLE" ]] && ARGS+=("--destroy-cluster-after-cycle" "$DESTROY_CLUSTER_AFTER_CYCLE")
[[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
[[ "$CONFIRM_DELETE" == "1" ]] && ARGS+=("--confirm-delete")
[[ -n "$RUN_ID" ]] && ARGS+=("--run-id" "$RUN_ID")
[[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
[[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")

printf '%s\n' "==============================================="
printf '%s\n' " provider-backed provisioning integration"
printf '%s\n' "==============================================="
printf 'Repository : %s\n' "$REPO_ROOT"
printf 'Cycle      : %s\n' "$CYCLE_CONFIG"
printf 'Action     : %s\n' "$ACTION"
printf 'Tool       : %s\n' "$TOOL_PATH"
printf 'Dry run    : %s\n\n' "$DRY_RUN"

exec "$PYTHON_BIN" "${ARGS[@]}"
