#!/usr/bin/env bash
set -euo pipefail
CYCLE_CONFIG=""
LIFECYCLE_POLICY=""
MODE=""
DESTROY_CLUSTER_AFTER_CYCLE=""
PROVIDER_CONFIG=""
TOOL_PATH="proxmox-k3s"
OUTPUT_ROOT=""
RUN_ID=""
WRITE_LATEST_ALIASES="0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --cycle-config) CYCLE_CONFIG="$2"; shift 2 ;;
    --lifecycle-policy) LIFECYCLE_POLICY="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --destroy-cluster-after-cycle) DESTROY_CLUSTER_AFTER_CYCLE="$2"; shift 2 ;;
    --provider-config) PROVIDER_CONFIG="$2"; shift 2 ;;
    --tool|--tool-path|-ToolPath) TOOL_PATH="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --write-latest-aliases) WRITE_LATEST_ALIASES="1"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/render-cluster-lifecycle-manifest.py"
if [[ -z "$CYCLE_CONFIG" ]]; then CYCLE_CONFIG="$REPO_ROOT/config/experimental-cycles/C1.json"; fi
if command -v python >/dev/null 2>&1; then PYTHON_BIN="python"; elif command -v python3 >/dev/null 2>&1; then PYTHON_BIN="python3"; else echo "Neither python nor python3 is available in PATH." >&2; exit 1; fi
ARGS=("$PYTHON_SCRIPT" "--repo-root" "$REPO_ROOT" "--cycle-config" "$CYCLE_CONFIG" "--tool-path" "$TOOL_PATH")
[[ -n "$LIFECYCLE_POLICY" ]] && ARGS+=("--lifecycle-policy" "$LIFECYCLE_POLICY")
[[ -n "$MODE" ]] && ARGS+=("--mode" "$MODE")
[[ -n "$DESTROY_CLUSTER_AFTER_CYCLE" ]] && ARGS+=("--destroy-cluster-after-cycle" "$DESTROY_CLUSTER_AFTER_CYCLE")
[[ -n "$PROVIDER_CONFIG" ]] && ARGS+=("--provider-config" "$PROVIDER_CONFIG")
[[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
[[ -n "$RUN_ID" ]] && ARGS+=("--run-id" "$RUN_ID")
[[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")
printf '%s
' "==============================================="
printf '%s
' " cluster lifecycle manifest renderer"
printf '%s
' "==============================================="
printf 'Repository : %s
' "$REPO_ROOT"
printf 'Cycle      : %s
' "$CYCLE_CONFIG"
printf 'Tool       : %s

' "$TOOL_PATH"
exec "$PYTHON_BIN" "${ARGS[@]}"
