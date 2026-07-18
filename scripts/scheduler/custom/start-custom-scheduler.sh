#!/usr/bin/env bash
set -euo pipefail

PROFILE_CONFIG=""
ACTION="install"
KUBECONFIG_PATH=""
SCHEDULER_PLUGINS_ROOT=""
CHART_PATH=""
OUTPUT_ROOT=""
RUN_ID=""
DRY_RUN="0"
SKIP_VALIDATION="0"
SKIP_TEST_WORKLOAD="0"
KEEP_TEST_WORKLOAD="0"
WRITE_LATEST_ALIASES="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-config|-ProfileConfig) PROFILE_CONFIG="${2:?Missing value for --profile-config}"; shift 2 ;;
    --action|-Action) ACTION="${2:?Missing value for --action}"; shift 2 ;;
    --kubeconfig|-Kubeconfig) KUBECONFIG_PATH="${2:?Missing value for --kubeconfig}"; shift 2 ;;
    --scheduler-plugins-root|-SchedulerPluginsRoot) SCHEDULER_PLUGINS_ROOT="${2:?Missing value for --scheduler-plugins-root}"; shift 2 ;;
    --chart-path|-ChartPath) CHART_PATH="${2:?Missing value for --chart-path}"; shift 2 ;;
    --output-root|-OutputRoot) OUTPUT_ROOT="${2:?Missing value for --output-root}"; shift 2 ;;
    --run-id|-RunId) RUN_ID="${2:?Missing value for --run-id}"; shift 2 ;;
    --dry-run|-DryRun) DRY_RUN="1"; shift ;;
    --skip-validation|-SkipValidation) SKIP_VALIDATION="1"; shift ;;
    --skip-test-workload|-SkipTestWorkload) SKIP_TEST_WORKLOAD="1"; shift ;;
    --keep-test-workload|-KeepTestWorkload) KEEP_TEST_WORKLOAD="1"; shift ;;
    --write-latest-aliases|-WriteLatestAliases) WRITE_LATEST_ALIASES="1"; shift ;;
    --help|-h|-Help)
      echo "Usage: ./start-custom-scheduler.sh [--profile-config <path>] [--action plan|install|apply|capture|validate|uninstall] [--kubeconfig <path>] [--scheduler-plugins-root <path>] [--dry-run]"
      exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
RUNNER="$SCRIPT_DIR/run-custom-scheduler.py"

if [[ ! -f "$RUNNER" ]]; then
  echo "Custom scheduler runner not found: $RUNNER" >&2
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

[[ -n "$PROFILE_CONFIG" ]] || PROFILE_CONFIG="$REPO_ROOT/config/scheduler/profiles/CS_C8_LOADAWARE_SECOND_SCHEDULER.json"

ARGS=(
  "$RUNNER"
  "--repo-root" "$REPO_ROOT"
  "--profile-config" "$PROFILE_CONFIG"
  "--action" "$ACTION"
)

[[ -n "$KUBECONFIG_PATH" ]] && ARGS+=("--kubeconfig" "$KUBECONFIG_PATH")
[[ -n "$SCHEDULER_PLUGINS_ROOT" ]] && ARGS+=("--scheduler-plugins-root" "$SCHEDULER_PLUGINS_ROOT")
[[ -n "$CHART_PATH" ]] && ARGS+=("--chart-path" "$CHART_PATH")
[[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
[[ -n "$RUN_ID" ]] && ARGS+=("--run-id" "$RUN_ID")
[[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
[[ "$SKIP_VALIDATION" == "1" ]] && ARGS+=("--skip-validation")
[[ "$SKIP_TEST_WORKLOAD" == "1" ]] && ARGS+=("--skip-test-workload")
[[ "$KEEP_TEST_WORKLOAD" == "1" ]] && ARGS+=("--keep-test-workload")
[[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")

printf '%s\n' "==============================================="
printf '%s\n' " custom scheduler integration"
printf '%s\n' "==============================================="
printf 'Repository : %s\n' "$REPO_ROOT"
printf 'Profile    : %s\n' "$PROFILE_CONFIG"
printf 'Action     : %s\n' "$ACTION"
printf 'Dry run    : %s\n\n' "$DRY_RUN"

exec "$PYTHON_CMD" "${ARGS[@]}"
