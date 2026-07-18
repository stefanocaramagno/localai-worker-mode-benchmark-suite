#!/usr/bin/env bash
set -euo pipefail

artifact_portability_search_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
while [[ -n "$artifact_portability_search_dir" && "$artifact_portability_search_dir" != "/" ]]; do
  artifact_portability_candidate="$artifact_portability_search_dir/scripts/common/artifact-portability.sh"
  if [[ -f "$artifact_portability_candidate" ]]; then
    # shellcheck source=/dev/null
    source "$artifact_portability_candidate"
    break
  fi
  artifact_portability_search_dir="$(dirname "$artifact_portability_search_dir")"
done
unset artifact_portability_search_dir artifact_portability_candidate
COMMAND="create"
CONFIG_PATH=""
TOOL_PATH="proxmox-k3s"
OUTPUT_ROOT=""
RUN_ID=""
CYCLE_ID="C1"
CLUSTER_LIFECYCLE_MODE="reuse"
DESTROY_CLUSTER_AFTER_CYCLE="0"
DRY_RUN="0"
CONFIRM_DELETE="0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --command) COMMAND="$2"; shift 2 ;;
    --config|--config-path|-ConfigPath) CONFIG_PATH="$2"; shift 2 ;;
    --tool|--tool-path|-ToolPath) TOOL_PATH="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --cycle-id) CYCLE_ID="$2"; shift 2 ;;
    --cluster-lifecycle-mode) CLUSTER_LIFECYCLE_MODE="$2"; shift 2 ;;
    --destroy-cluster-after-cycle) DESTROY_CLUSTER_AFTER_CYCLE="1"; shift ;;
    --dry-run) DRY_RUN="1"; shift ;;
    --confirm-delete) CONFIRM_DELETE="1"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Neither python nor python3 is available; cannot write command manifest." >&2
  exit 1
fi
if [[ -z "$CONFIG_PATH" ]]; then CONFIG_PATH="$REPO_ROOT/config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml"; fi
if [[ -z "$OUTPUT_ROOT" ]]; then OUTPUT_ROOT="$REPO_ROOT/results/experimental-cycles/$CYCLE_ID/infrastructure/provisioning"; fi
if [[ -z "$RUN_ID" ]]; then RUN_ID="proxmox-k3s_${COMMAND//-/_}_$(date -u +%Y%m%dT%H%M%SZ)"; fi
if [[ ! -f "$CONFIG_PATH" ]]; then echo "The proxmox-k3s configuration file does not exist: $CONFIG_PATH" >&2; exit 1; fi
if [[ "$COMMAND" == "delete" && "$DRY_RUN" != "1" && "$CONFIRM_DELETE" != "1" ]]; then echo "The delete command is destructive. Re-run with --confirm-delete to explicitly confirm cluster deletion through the benchmark-suite wrapper." >&2; exit 2; fi
mkdir -p "$OUTPUT_ROOT"
LOG_PATH="$OUTPUT_ROOT/$RUN_ID.log"
MANIFEST_PATH="$OUTPUT_ROOT/$RUN_ID.command-manifest.json"
case "$COMMAND" in
  create) ARGS=("cluster" "create" "-c" "$CONFIG_PATH") ;;
  delete) ARGS=("cluster" "delete" "-c" "$CONFIG_PATH") ;;
  kubeconfig) ARGS=("cluster" "kubeconfig" "-c" "$CONFIG_PATH") ;;
  template-create) ARGS=("template" "create" "-c" "$CONFIG_PATH") ;;
  template-delete) ARGS=("template" "delete" "-c" "$CONFIG_PATH") ;;
  *) echo "Unsupported command: $COMMAND" >&2; exit 2 ;;
esac
printf '%s
' "==============================================="
printf '%s
' " proxmox-k3s standalone command launcher"
printf '%s
' "==============================================="
printf 'Repository : %s
' "$REPO_ROOT"
printf 'Tool       : %s
' "$TOOL_PATH"
printf 'Command    : %s
' "$COMMAND"
printf 'Config     : %s
' "$CONFIG_PATH"
printf 'Run ID     : %s
' "$RUN_ID"
printf 'Log file   : %s
' "$LOG_PATH"
printf 'Manifest   : %s
' "$MANIFEST_PATH"
printf 'Cycle      : %s
' "$CYCLE_ID"
printf 'Lifecycle  : %s
' "$CLUSTER_LIFECYCLE_MODE"
printf 'Destroy after cycle: %s
' "$DESTROY_CLUSTER_AFTER_CYCLE"
printf 'Dry run    : %s
' "$DRY_RUN"
printf 'Confirm delete: %s

' "$CONFIRM_DELETE"
PRINTABLE_COMMAND="$TOOL_PATH ${ARGS[*]}"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
STDIN_PROVIDED="0"
if [[ "$COMMAND" == "delete" && "$CONFIRM_DELETE" == "1" ]]; then STDIN_PROVIDED="1"; fi
write_manifest() {
  local status="$1"; local exit_code="$2"; local finished_at="$3"
  "$PYTHON_BIN" - "$MANIFEST_PATH" <<PYJSON
import json, sys
path = sys.argv[1]
payload = {
    "schemaVersion": "proxmox-k3s-command-manifest/v1",
    "manifestId": "$RUN_ID",
    "cycleId": "$CYCLE_ID",
    "command": "$COMMAND",
    "clusterLifecycleMode": "$CLUSTER_LIFECYCLE_MODE",
    "destroyClusterAfterCycle": "$DESTROY_CLUSTER_AFTER_CYCLE" == "1",
    "toolPath": "$TOOL_PATH",
    "configPath": "$CONFIG_PATH",
    "printableCommand": "$PRINTABLE_COMMAND",
    "logPath": "$LOG_PATH",
    "startedAtUtc": "$STARTED_AT",
    "finishedAtUtc": "$finished_at",
    "dryRun": "$DRY_RUN" == "1",
    "confirmDelete": "$CONFIRM_DELETE" == "1",
    "stdinProvided": "$STDIN_PROVIDED" == "1",
    "status": "$status",
    "exitCode": int("$exit_code")
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=4)
    f.write("\n")
PYJSON
  normalize_artifact_file "$MANIFEST_PATH"
}
if [[ "$DRY_RUN" == "1" ]]; then
  { echo "Dry-run only. Command not executed."; echo "Command: $PRINTABLE_COMMAND"; echo "GeneratedAtUtc: $STARTED_AT"; } | tee "$LOG_PATH"
  write_manifest "dry_run" "0" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  normalize_artifact_file "$LOG_PATH"
  exit 0
fi
{ echo "Command: $PRINTABLE_COMMAND"; echo "StartedAtUtc: $STARTED_AT"; echo "CycleId: $CYCLE_ID"; echo "ClusterLifecycleMode: $CLUSTER_LIFECYCLE_MODE"; echo "DestroyClusterAfterCycle: $DESTROY_CLUSTER_AFTER_CYCLE"; echo "StdinProvided: $STDIN_PROVIDED"; echo ""; } > "$LOG_PATH"
set +e
if [[ "$STDIN_PROVIDED" == "1" ]]; then
  printf 'y\n' | "$TOOL_PATH" "${ARGS[@]}" 2>&1 | tee -a "$LOG_PATH"
  EXIT_CODE=${PIPESTATUS[1]}
else
  "$TOOL_PATH" "${ARGS[@]}" 2>&1 | tee -a "$LOG_PATH"
  EXIT_CODE=${PIPESTATUS[0]}
fi
set -e
FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
{ echo ""; echo "FinishedAtUtc: $FINISHED_AT"; echo "ExitCode: $EXIT_CODE"; } >> "$LOG_PATH"
if [[ "$EXIT_CODE" -eq 0 ]]; then write_manifest "completed" "$EXIT_CODE" "$FINISHED_AT"; else write_manifest "failed" "$EXIT_CODE" "$FINISHED_AT"; fi
normalize_artifact_file "$LOG_PATH"
if [[ "$EXIT_CODE" -ne 0 ]]; then echo "proxmox-k3s command failed with exit code $EXIT_CODE. See log: $LOG_PATH" >&2; exit "$EXIT_CODE"; fi
