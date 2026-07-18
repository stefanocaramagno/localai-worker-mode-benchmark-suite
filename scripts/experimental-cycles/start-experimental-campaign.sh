#!/usr/bin/env bash
set -euo pipefail

CYCLE_CONFIG=""
TOOL_PATH="proxmox-k3s"
RUN_ID=""
BASELINE_REPLICAS=""
BASE_URL=""
DRY_RUN="0"
CONTINUE_ON_FAILURE="0"
ALLOW_METRICS_WARNING="0"
CONFIRM_DELETE="0"
FORCE_FREEZE="0"
WRITE_LATEST_ALIASES="0"
SKIP_PROVISIONING="0"
SKIP_CLUSTER_VALIDATION="0"
SKIP_PLACEMENT_PROFILE="0"
SKIP_LOCALAI_DEPLOYMENT="0"
SKIP_SMOKE_TEST="0"
SKIP_MINIMAL_OBSERVABILITY="0"
SKIP_LATENCY_INJECTION="0"
SKIP_DEFAULT_SCHEDULER_VALIDATION="0"
SKIP_SCHEDULER_CAPTURE="0"
SKIP_TELEMETRY_PRIMING="0"
SKIP_CLUSTER_LENS_CAPTURE="0"
SKIP_BENCHMARK="0"
SKIP_DIAGNOSIS="0"
SKIP_REPORTING="0"
SKIP_COMPLETION_GATE="0"
SKIP_FREEZE="0"
SKIP_DELETE="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cycle-config) CYCLE_CONFIG="$2"; shift 2 ;;
    --tool-path|--tool) TOOL_PATH="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --baseline-replicas) BASELINE_REPLICAS="$2"; shift 2 ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    --dry-run) DRY_RUN="1"; shift ;;
    --continue-on-failure) CONTINUE_ON_FAILURE="1"; shift ;;
    --allow-metrics-warning) ALLOW_METRICS_WARNING="1"; shift ;;
    --confirm-delete) CONFIRM_DELETE="1"; shift ;;
    --force-freeze) FORCE_FREEZE="1"; shift ;;
    --write-latest-aliases) WRITE_LATEST_ALIASES="1"; shift ;;
    --skip-provisioning) SKIP_PROVISIONING="1"; shift ;;
    --skip-cluster-validation) SKIP_CLUSTER_VALIDATION="1"; shift ;;
    --skip-placement-profile) SKIP_PLACEMENT_PROFILE="1"; shift ;;
    --skip-localai-deployment) SKIP_LOCALAI_DEPLOYMENT="1"; shift ;;
    --skip-smoke-test) SKIP_SMOKE_TEST="1"; shift ;;
    --skip-minimal-observability) SKIP_MINIMAL_OBSERVABILITY="1"; shift ;;
    --skip-latency-injection) SKIP_LATENCY_INJECTION="1"; shift ;;
    --skip-default-scheduler-validation) SKIP_DEFAULT_SCHEDULER_VALIDATION="1"; shift ;;
    --skip-scheduler-capture) SKIP_SCHEDULER_CAPTURE="1"; shift ;;
    --skip-telemetry-priming) SKIP_TELEMETRY_PRIMING="1"; shift ;;
    --skip-cluster-lens-capture) SKIP_CLUSTER_LENS_CAPTURE="1"; shift ;;
    --skip-benchmark) SKIP_BENCHMARK="1"; shift ;;
    --skip-diagnosis) SKIP_DIAGNOSIS="1"; shift ;;
    --skip-reporting) SKIP_REPORTING="1"; shift ;;
    --skip-completion-gate) SKIP_COMPLETION_GATE="1"; shift ;;
    --skip-freeze) SKIP_FREEZE="1"; shift ;;
    --skip-delete) SKIP_DELETE="1"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNNER="$REPO_ROOT/scripts/experimental-cycles/run-experimental-campaign.py"
[[ -f "$RUNNER" ]] || { echo "Experimental campaign runner not found: $RUNNER" >&2; exit 1; }
if [[ -z "$CYCLE_CONFIG" ]]; then CYCLE_CONFIG="$REPO_ROOT/config/experimental-cycles/C2.json"; fi
if command -v python3 >/dev/null 2>&1; then PYTHON_BIN="python3"; elif command -v python >/dev/null 2>&1; then PYTHON_BIN="python"; else echo "No Python interpreter found in PATH." >&2; exit 1; fi
ARGS=("$RUNNER" "--repo-root" "$REPO_ROOT" "--cycle-config" "$CYCLE_CONFIG" "--tool-path" "$TOOL_PATH")
[[ -n "$RUN_ID" ]] && ARGS+=("--run-id" "$RUN_ID")
[[ -n "$BASELINE_REPLICAS" ]] && ARGS+=("--baseline-replicas" "$BASELINE_REPLICAS")
[[ -n "$BASE_URL" ]] && ARGS+=("--base-url" "$BASE_URL")
[[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
[[ "$CONTINUE_ON_FAILURE" == "1" ]] && ARGS+=("--continue-on-failure")
[[ "$ALLOW_METRICS_WARNING" == "1" ]] && ARGS+=("--allow-metrics-warning")
[[ "$CONFIRM_DELETE" == "1" ]] && ARGS+=("--confirm-delete")
[[ "$FORCE_FREEZE" == "1" ]] && ARGS+=("--force-freeze")
[[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")
[[ "$SKIP_PROVISIONING" == "1" ]] && ARGS+=("--skip-provisioning")
[[ "$SKIP_CLUSTER_VALIDATION" == "1" ]] && ARGS+=("--skip-cluster-validation")
[[ "$SKIP_PLACEMENT_PROFILE" == "1" ]] && ARGS+=("--skip-placement-profile")
[[ "$SKIP_LOCALAI_DEPLOYMENT" == "1" ]] && ARGS+=("--skip-localai-deployment")
[[ "$SKIP_SMOKE_TEST" == "1" ]] && ARGS+=("--skip-smoke-test")
[[ "$SKIP_MINIMAL_OBSERVABILITY" == "1" ]] && ARGS+=("--skip-minimal-observability")
[[ "$SKIP_LATENCY_INJECTION" == "1" ]] && ARGS+=("--skip-latency-injection")
[[ "$SKIP_DEFAULT_SCHEDULER_VALIDATION" == "1" ]] && ARGS+=("--skip-default-scheduler-validation")
[[ "$SKIP_SCHEDULER_CAPTURE" == "1" ]] && ARGS+=("--skip-scheduler-capture")
[[ "$SKIP_TELEMETRY_PRIMING" == "1" ]] && ARGS+=("--skip-telemetry-priming")
[[ "$SKIP_CLUSTER_LENS_CAPTURE" == "1" ]] && ARGS+=("--skip-cluster-lens-capture")
[[ "$SKIP_BENCHMARK" == "1" ]] && ARGS+=("--skip-benchmark")
[[ "$SKIP_DIAGNOSIS" == "1" ]] && ARGS+=("--skip-diagnosis")
[[ "$SKIP_REPORTING" == "1" ]] && ARGS+=("--skip-reporting")
[[ "$SKIP_COMPLETION_GATE" == "1" ]] && ARGS+=("--skip-completion-gate")
[[ "$SKIP_FREEZE" == "1" ]] && ARGS+=("--skip-freeze")
[[ "$SKIP_DELETE" == "1" ]] && ARGS+=("--skip-delete")
exec "$PYTHON_BIN" "${ARGS[@]}"
