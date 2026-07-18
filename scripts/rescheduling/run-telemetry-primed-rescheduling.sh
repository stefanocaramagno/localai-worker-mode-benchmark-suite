#!/usr/bin/env bash
set -euo pipefail

PROFILE_CONFIG=""
SCENARIO_CONFIG=""
ACTION="execute"
KUBECONFIG_PATH=""
OUTPUT_ROOT=""
RUN_ID=""
DRY_RUN="0"
SKIP_TELEMETRY_PRIMING="0"
SKIP_ANNOTATION_GATE="0"
SKIP_POST_RESTART_STABILIZATION="0"
WRITE_LATEST_ALIASES="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-config|-ProfileConfig) PROFILE_CONFIG="${2:?Missing value for --profile-config}"; shift 2 ;;
    --scenario-config|-ScenarioConfig) SCENARIO_CONFIG="${2:?Missing value for --scenario-config}"; shift 2 ;;
    --action|-Action) ACTION="${2:?Missing value for --action}"; shift 2 ;;
    --kubeconfig|-Kubeconfig) KUBECONFIG_PATH="${2:?Missing value for --kubeconfig}"; shift 2 ;;
    --output-root|-OutputRoot) OUTPUT_ROOT="${2:?Missing value for --output-root}"; shift 2 ;;
    --run-id|-RunId) RUN_ID="${2:?Missing value for --run-id}"; shift 2 ;;
    --dry-run|-DryRun) DRY_RUN="1"; shift ;;
    --skip-telemetry-priming|-SkipTelemetryPriming) SKIP_TELEMETRY_PRIMING="1"; shift ;;
    --skip-annotation-gate|-SkipAnnotationGate) SKIP_ANNOTATION_GATE="1"; shift ;;
    --skip-post-restart-stabilization|-SkipPostRestartStabilization) SKIP_POST_RESTART_STABILIZATION="1"; shift ;;
    --write-latest-aliases|-WriteLatestAliases) WRITE_LATEST_ALIASES="1"; shift ;;
    --help|-h|-Help)
      echo "Usage: ./run-telemetry-primed-rescheduling.sh [--profile-config <path>] [--scenario-config <path>] [--action plan|capture|execute|restart|validate] [--kubeconfig <path>] [--dry-run]"
      exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
RUNNER="$SCRIPT_DIR/run-telemetry-primed-rescheduling.py"

if [[ ! -f "$RUNNER" ]]; then
  echo "Telemetry-primed rescheduling runner not found: $RUNNER" >&2
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

[[ -n "$PROFILE_CONFIG" ]] || PROFILE_CONFIG="$REPO_ROOT/config/rescheduling/profiles/RS_C8_RESOURCE_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json"

ARGS=(
  "$RUNNER"
  "--repo-root" "$REPO_ROOT"
  "--profile-config" "$PROFILE_CONFIG"
  "--action" "$ACTION"
)

[[ -n "$SCENARIO_CONFIG" ]] && ARGS+=("--scenario-config" "$SCENARIO_CONFIG")
[[ -n "$KUBECONFIG_PATH" ]] && ARGS+=("--kubeconfig" "$KUBECONFIG_PATH")
[[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
[[ -n "$RUN_ID" ]] && ARGS+=("--run-id" "$RUN_ID")
[[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
[[ "$SKIP_TELEMETRY_PRIMING" == "1" ]] && ARGS+=("--skip-telemetry-priming")
[[ "$SKIP_ANNOTATION_GATE" == "1" ]] && ARGS+=("--skip-annotation-gate")
[[ "$SKIP_POST_RESTART_STABILIZATION" == "1" ]] && ARGS+=("--skip-post-restart-stabilization")
[[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")

printf '%s\n' "==============================================="
printf '%s\n' " telemetry-primed rescheduling"
printf '%s\n' "==============================================="
printf 'Repository : %s\n' "$REPO_ROOT"
printf 'Profile    : %s\n' "$PROFILE_CONFIG"
printf 'Action     : %s\n' "$ACTION"
printf 'Dry run    : %s\n\n' "$DRY_RUN"

exec "$PYTHON_CMD" "${ARGS[@]}"
