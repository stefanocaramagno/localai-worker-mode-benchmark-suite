#!/usr/bin/env bash
set -euo pipefail

CYCLE_CONFIG=""
EXECUTION_SCOPE="provisioning"
PROVISIONING_ACTION="provision"
TOOL_PATH="proxmox-k3s"
PROVIDER_CONFIG=""
CONFIRM_DELETE="0"
CLUSTER_VALIDATION_PROFILE=""
VALIDATION_PROFILE=""
SKIP_PREVALIDATION_GATE="0"
ALLOW_METRICS_WARNING="0"
DEPLOYMENT_PROFILE=""
DEPLOYMENT_ACTION="deploy"
SKIP_CLUSTER_VALIDATION_GATE="0"
SKIP_SMOKE_TEST="0"
BASE_URL=""
BENCHMARK_CONFIG=""
NO_PORT_FORWARD="0"
KUBECONFIG_PATH=""
DRY_RUN="0"
RUN_ID=""
OUTPUT_ROOT=""
WRITE_LATEST_ALIASES="0"
PLACEMENT_PROFILE_ID=""
PLACEMENT_PROFILE_PATH=""
MINIMAL_OBSERVABILITY_PROFILE=""
MINIMAL_OBSERVABILITY_ACTION="capture"
OBSERVABILITY_STAGE=""
MEASUREMENT_CSV_PREFIX=""
SKIP_APPLICATION_DEPLOYMENT_GATE="0"
REPORTING_PROFILE=""
REPORTING_ID=""
ARCHIVE_REPORTING="0"
ARCHIVE_CURRENT_REPORTING="0"
FORCE_ARCHIVE_REPORTING="0"
SKIP_REPORTING_SITE_UPDATE="0"
COMPLETION_GATE_PROFILE=""
DIAGNOSIS_JSON=""
EVALUATION_ID=""
FREEZE_PROFILE=""
FREEZE_ID=""
FORCE_FREEZE="0"
SKIP_COMPLETION_GATE_FOR_FREEZE="0"
BASELINE_REPLICAS="A"
SKIP_PROVISIONING="0"
SKIP_CLUSTER_VALIDATION_STEP="0"
SKIP_PLACEMENT_PROFILE_STEP="0"
SKIP_LOCALAI_DEPLOYMENT_STEP="0"
SKIP_MINIMAL_OBSERVABILITY_STEP="0"
SKIP_LATENCY_INJECTION="0"
SKIP_DEFAULT_SCHEDULER_VALIDATION="0"
SKIP_SCHEDULER_CAPTURE="0"
SKIP_TELEMETRY_PRIMING="0"
SKIP_CLUSTER_LENS_CAPTURE="0"
SKIP_BENCHMARK="0"
SKIP_DIAGNOSIS="0"
SKIP_REPORTING_STEP="0"
SKIP_COMPLETION_GATE_STEP="0"
SKIP_FREEZE_STEP="0"
CONTINUE_ON_FAILURE="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cycle-config) CYCLE_CONFIG="$2"; shift 2 ;;
    --execution-scope) EXECUTION_SCOPE="$2"; shift 2 ;;
    --provisioning-action) PROVISIONING_ACTION="$2"; shift 2 ;;
    --tool|--tool-path) TOOL_PATH="$2"; shift 2 ;;
    --provider-config) PROVIDER_CONFIG="$2"; shift 2 ;;
    --confirm-delete) CONFIRM_DELETE="1"; shift ;;
    --cluster-validation-profile) CLUSTER_VALIDATION_PROFILE="$2"; shift 2 ;;
    --validation-profile) VALIDATION_PROFILE="$2"; shift 2 ;;
    --skip-prevalidation-gate|--skip-pre-validation-gate) SKIP_PREVALIDATION_GATE="1"; shift ;;
    --allow-metrics-warning) ALLOW_METRICS_WARNING="1"; shift ;;
    --deployment-profile) DEPLOYMENT_PROFILE="$2"; shift 2 ;;
    --deployment-action) DEPLOYMENT_ACTION="$2"; shift 2 ;;
    --skip-cluster-validation-gate) SKIP_CLUSTER_VALIDATION_GATE="1"; shift ;;
    --skip-smoke-test) SKIP_SMOKE_TEST="1"; shift ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    --benchmark-config) BENCHMARK_CONFIG="$2"; shift 2 ;;
    --no-port-forward) NO_PORT_FORWARD="1"; shift ;;
    --kubeconfig) KUBECONFIG_PATH="$2"; shift 2 ;;
    --dry-run) DRY_RUN="1"; shift ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --placement-profile-id) PLACEMENT_PROFILE_ID="$2"; shift 2 ;;
    --placement-profile-path) PLACEMENT_PROFILE_PATH="$2"; shift 2 ;;
    --minimal-observability-profile) MINIMAL_OBSERVABILITY_PROFILE="$2"; shift 2 ;;
    --minimal-observability-action) MINIMAL_OBSERVABILITY_ACTION="$2"; shift 2 ;;
    --observability-stage) OBSERVABILITY_STAGE="$2"; shift 2 ;;
    --measurement-csv-prefix) MEASUREMENT_CSV_PREFIX="$2"; shift 2 ;;
    --skip-application-deployment-gate) SKIP_APPLICATION_DEPLOYMENT_GATE="1"; shift ;;
    --reporting-profile) REPORTING_PROFILE="$2"; shift 2 ;;
    --reporting-id) REPORTING_ID="$2"; shift 2 ;;
    --archive-reporting) ARCHIVE_REPORTING="1"; shift ;;
    --archive-current-reporting) ARCHIVE_CURRENT_REPORTING="1"; shift ;;
    --force-archive-reporting) FORCE_ARCHIVE_REPORTING="1"; shift ;;
    --skip-reporting-site-update) SKIP_REPORTING_SITE_UPDATE="1"; shift ;;
    --completion-gate-profile) COMPLETION_GATE_PROFILE="$2"; shift 2 ;;
    --diagnosis-json) DIAGNOSIS_JSON="$2"; shift 2 ;;
    --evaluation-id) EVALUATION_ID="$2"; shift 2 ;;
    --freeze-profile) FREEZE_PROFILE="$2"; shift 2 ;;
    --freeze-id) FREEZE_ID="$2"; shift 2 ;;
    --force-freeze) FORCE_FREEZE="1"; shift ;;
    --skip-completion-gate-for-freeze) SKIP_COMPLETION_GATE_FOR_FREEZE="1"; shift ;;
    --baseline-replicas) BASELINE_REPLICAS="$2"; shift 2 ;;
    --skip-provisioning) SKIP_PROVISIONING="1"; shift ;;
    --skip-cluster-validation-step) SKIP_CLUSTER_VALIDATION_STEP="1"; shift ;;
    --skip-placement-profile-step) SKIP_PLACEMENT_PROFILE_STEP="1"; shift ;;
    --skip-localai-deployment-step) SKIP_LOCALAI_DEPLOYMENT_STEP="1"; shift ;;
    --skip-minimal-observability-step) SKIP_MINIMAL_OBSERVABILITY_STEP="1"; shift ;;
    --skip-latency-injection) SKIP_LATENCY_INJECTION="1"; shift ;;
    --skip-default-scheduler-validation) SKIP_DEFAULT_SCHEDULER_VALIDATION="1"; shift ;;
    --skip-scheduler-capture) SKIP_SCHEDULER_CAPTURE="1"; shift ;;
    --skip-telemetry-priming) SKIP_TELEMETRY_PRIMING="1"; shift ;;
    --skip-cluster-lens-capture) SKIP_CLUSTER_LENS_CAPTURE="1"; shift ;;
    --skip-benchmark) SKIP_BENCHMARK="1"; shift ;;
    --skip-diagnosis) SKIP_DIAGNOSIS="1"; shift ;;
    --skip-reporting-step) SKIP_REPORTING_STEP="1"; shift ;;
    --skip-completion-gate-step) SKIP_COMPLETION_GATE_STEP="1"; shift ;;
    --skip-freeze-step) SKIP_FREEZE_STEP="1"; shift ;;
    --continue-on-failure) CONTINUE_ON_FAILURE="1"; shift ;;
    --write-latest-aliases) WRITE_LATEST_ALIASES="1"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROVISIONING_LAUNCHER="$REPO_ROOT/scripts/infrastructure/provision/start-provider-backed-provisioning.sh"
CLUSTER_VALIDATION_LAUNCHER="$REPO_ROOT/scripts/infrastructure/validation/start-provider-backed-cluster-validation.sh"
DEPLOYMENT_LAUNCHER="$REPO_ROOT/scripts/application/deployment/start-provider-backed-localai-deployment.sh"
PLACEMENT_PROFILE_LAUNCHER="$REPO_ROOT/scripts/placement/resolve-placement-profile.sh"
MINIMAL_OBSERVABILITY_LAUNCHER="$REPO_ROOT/scripts/observability/minimal/start-minimal-observability.sh"
REPORTING_LAUNCHER="$REPO_ROOT/scripts/load/post/start-reporting.sh"
COMPLETION_GATE_LAUNCHER="$REPO_ROOT/scripts/load/post/start-completion-gate.sh"
FREEZE_LAUNCHER="$REPO_ROOT/scripts/load/post/start-freeze-experimental-cycle.sh"
PROVIDER_BACKED_CYCLE_RUNNER="$REPO_ROOT/scripts/experimental-cycles/run-provider-backed-cycle.py"

if [[ -z "$CYCLE_CONFIG" ]]; then
  CYCLE_CONFIG="$REPO_ROOT/config/experimental-cycles/C1.json"
fi

printf '%s\n' "==============================================="
printf '%s\n' " experimental cycle launcher"
printf '%s\n' "==============================================="
printf 'Repository      : %s\n' "$REPO_ROOT"
printf 'Cycle           : %s\n' "$CYCLE_CONFIG"
printf 'Execution scope : %s\n\n' "$EXECUTION_SCOPE"

case "$EXECUTION_SCOPE" in
  provider-backed-cycle)
    [[ ! -f "$PROVIDER_BACKED_CYCLE_RUNNER" ]] && { echo "Provider-backed cycle runner not found: $PROVIDER_BACKED_CYCLE_RUNNER" >&2; exit 1; }
    if command -v python >/dev/null 2>&1; then
      PYTHON_BIN="python"
    elif command -v python3 >/dev/null 2>&1; then
      PYTHON_BIN="python3"
    else
      echo "No Python interpreter found in PATH." >&2
      exit 1
    fi
    ARGS=("$PROVIDER_BACKED_CYCLE_RUNNER" "--repo-root" "$REPO_ROOT" "--cycle-config" "$CYCLE_CONFIG" "--tool-path" "$TOOL_PATH" "--baseline-replicas" "$BASELINE_REPLICAS")
    [[ -n "$PROVIDER_CONFIG" ]] && ARGS+=("--provider-config" "$PROVIDER_CONFIG")
    [[ -n "$RUN_ID" ]] && ARGS+=("--run-id" "$RUN_ID")
    [[ -n "$BASE_URL" ]] && ARGS+=("--base-url" "$BASE_URL")
    [[ -n "$BENCHMARK_CONFIG" ]] && ARGS+=("--benchmark-config" "$BENCHMARK_CONFIG")
    [[ "$NO_PORT_FORWARD" == "1" ]] && ARGS+=("--no-port-forward")
    [[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
    [[ "$CONTINUE_ON_FAILURE" == "1" ]] && ARGS+=("--continue-on-failure")
    [[ "$ALLOW_METRICS_WARNING" == "1" ]] && ARGS+=("--allow-metrics-warning")
    [[ "$CONFIRM_DELETE" == "1" ]] && ARGS+=("--confirm-delete")
    [[ "$FORCE_FREEZE" == "1" ]] && ARGS+=("--force-freeze")
    [[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")
    [[ "$SKIP_PROVISIONING" == "1" ]] && ARGS+=("--skip-provisioning")
    [[ "$SKIP_CLUSTER_VALIDATION_STEP" == "1" ]] && ARGS+=("--skip-cluster-validation")
    [[ "$SKIP_PLACEMENT_PROFILE_STEP" == "1" ]] && ARGS+=("--skip-placement-profile")
    [[ "$SKIP_LOCALAI_DEPLOYMENT_STEP" == "1" ]] && ARGS+=("--skip-localai-deployment")
    [[ "$SKIP_SMOKE_TEST" == "1" ]] && ARGS+=("--skip-smoke-test")
    [[ "$SKIP_MINIMAL_OBSERVABILITY_STEP" == "1" ]] && ARGS+=("--skip-minimal-observability")
    [[ "$SKIP_LATENCY_INJECTION" == "1" ]] && ARGS+=("--skip-latency-injection")
    [[ "$SKIP_DEFAULT_SCHEDULER_VALIDATION" == "1" ]] && ARGS+=("--skip-default-scheduler-validation")
    [[ "$SKIP_SCHEDULER_CAPTURE" == "1" ]] && ARGS+=("--skip-scheduler-capture")
    [[ "$SKIP_TELEMETRY_PRIMING" == "1" ]] && ARGS+=("--skip-telemetry-priming")
    [[ "$SKIP_CLUSTER_LENS_CAPTURE" == "1" ]] && ARGS+=("--skip-cluster-lens-capture")
    [[ "$SKIP_BENCHMARK" == "1" ]] && ARGS+=("--skip-benchmark")
    [[ "$SKIP_DIAGNOSIS" == "1" ]] && ARGS+=("--skip-diagnosis")
    [[ "$SKIP_REPORTING_STEP" == "1" ]] && ARGS+=("--skip-reporting")
    [[ "$SKIP_COMPLETION_GATE_STEP" == "1" ]] && ARGS+=("--skip-completion-gate")
    [[ "$SKIP_FREEZE_STEP" == "1" ]] && ARGS+=("--skip-freeze")
    exec "$PYTHON_BIN" "${ARGS[@]}"
    ;;
  provisioning)
    [[ ! -f "$PROVISIONING_LAUNCHER" ]] && { echo "Provider-backed provisioning launcher not found: $PROVISIONING_LAUNCHER" >&2; exit 1; }
    ARGS=("--cycle-config" "$CYCLE_CONFIG" "--action" "$PROVISIONING_ACTION" "--tool" "$TOOL_PATH")
    [[ -n "$PROVIDER_CONFIG" ]] && ARGS+=("--provider-config" "$PROVIDER_CONFIG")
    [[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
    [[ "$CONFIRM_DELETE" == "1" ]] && ARGS+=("--confirm-delete")
    [[ -n "$RUN_ID" ]] && ARGS+=("--run-id" "$RUN_ID")
    [[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
    [[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")
    exec bash "$PROVISIONING_LAUNCHER" "${ARGS[@]}"
    ;;
  cluster-validation)
    [[ ! -f "$CLUSTER_VALIDATION_LAUNCHER" ]] && { echo "Provider-backed cluster validation launcher not found: $CLUSTER_VALIDATION_LAUNCHER" >&2; exit 1; }
    ARGS=("--cycle-config" "$CYCLE_CONFIG")
    [[ -n "$CLUSTER_VALIDATION_PROFILE" ]] && ARGS+=("--cluster-validation-profile" "$CLUSTER_VALIDATION_PROFILE")
    [[ -n "$VALIDATION_PROFILE" ]] && ARGS+=("--validation-profile" "$VALIDATION_PROFILE")
    [[ -n "$KUBECONFIG_PATH" ]] && ARGS+=("--kubeconfig" "$KUBECONFIG_PATH")
    [[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
    [[ -n "$RUN_ID" ]] && ARGS+=("--validation-id" "$RUN_ID")
    [[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
    [[ "$SKIP_PREVALIDATION_GATE" == "1" ]] && ARGS+=("--skip-prevalidation-gate")
    [[ "$ALLOW_METRICS_WARNING" == "1" ]] && ARGS+=("--allow-metrics-warning")
    [[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")
    exec bash "$CLUSTER_VALIDATION_LAUNCHER" "${ARGS[@]}"
    ;;
  placement-profile)
    [[ ! -f "$PLACEMENT_PROFILE_LAUNCHER" ]] && { echo "Placement profile launcher not found: $PLACEMENT_PROFILE_LAUNCHER" >&2; exit 1; }
    ARGS=()
    [[ -n "$CYCLE_CONFIG" ]] && ARGS+=("--cycle-config" "$CYCLE_CONFIG")
    [[ -n "$DEPLOYMENT_PROFILE" ]] && ARGS+=("--application-deployment-profile" "$DEPLOYMENT_PROFILE")
    [[ -n "$PLACEMENT_PROFILE_ID" ]] && ARGS+=("--placement-profile-id" "$PLACEMENT_PROFILE_ID")
    [[ -n "$PLACEMENT_PROFILE_PATH" ]] && ARGS+=("--placement-profile-path" "$PLACEMENT_PROFILE_PATH")
    [[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
    [[ -n "$RUN_ID" ]] && ARGS+=("--resolution-id" "$RUN_ID")
    [[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")
    exec bash "$PLACEMENT_PROFILE_LAUNCHER" "${ARGS[@]}"
    ;;
  minimal-observability)
    [[ ! -f "$MINIMAL_OBSERVABILITY_LAUNCHER" ]] && { echo "Minimal observability launcher not found: $MINIMAL_OBSERVABILITY_LAUNCHER" >&2; exit 1; }
    ARGS=("--cycle-config" "$CYCLE_CONFIG" "--action" "$MINIMAL_OBSERVABILITY_ACTION")
    [[ -n "$MINIMAL_OBSERVABILITY_PROFILE" ]] && ARGS+=("--profile-config" "$MINIMAL_OBSERVABILITY_PROFILE")
    [[ -n "$OBSERVABILITY_STAGE" ]] && ARGS+=("--stage" "$OBSERVABILITY_STAGE")
    [[ -n "$KUBECONFIG_PATH" ]] && ARGS+=("--kubeconfig" "$KUBECONFIG_PATH")
    [[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
    [[ -n "$RUN_ID" ]] && ARGS+=("--observability-id" "$RUN_ID")
    [[ -n "$MEASUREMENT_CSV_PREFIX" ]] && ARGS+=("--measurement-csv-prefix" "$MEASUREMENT_CSV_PREFIX")
    [[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
    [[ "$SKIP_CLUSTER_VALIDATION_GATE" == "1" ]] && ARGS+=("--skip-cluster-validation-gate")
    [[ "$SKIP_APPLICATION_DEPLOYMENT_GATE" == "1" ]] && ARGS+=("--skip-application-deployment-gate")
    [[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")
    exec bash "$MINIMAL_OBSERVABILITY_LAUNCHER" "${ARGS[@]}"
    ;;
  reporting)
    [[ ! -f "$REPORTING_LAUNCHER" ]] && { echo "Reporting launcher not found: $REPORTING_LAUNCHER" >&2; exit 1; }
    RESOLVED_REPORTING_PROFILE="$REPORTING_PROFILE"
    if [[ -z "$RESOLVED_REPORTING_PROFILE" ]]; then
      RESOLVED_REPORTING_PROFILE="$(python - "$CYCLE_CONFIG" <<'PY_RESOLVE_REPORTING_PROFILE'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8-sig") as fh:
    cycle = json.load(fh)
value = (
    (cycle.get("reporting") or {}).get("reportingProfilePath")
    or (cycle.get("providerBackedInfrastructure") or {}).get("reportingProfilePath")
    or (cycle.get("pipelineProfiles") or {}).get("reporting")
    or ""
)
print(value)
PY_RESOLVE_REPORTING_PROFILE
)"
    fi
    if [[ -z "$RESOLVED_REPORTING_PROFILE" ]]; then
      echo "Reporting profile path is not declared in the cycle profile and was not provided explicitly." >&2
      exit 1
    fi
    ARGS=("--repo-root" "$REPO_ROOT" "--profile-config" "$RESOLVED_REPORTING_PROFILE")
    [[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
    if [[ -n "$REPORTING_ID" ]]; then
      ARGS+=("--reporting-id" "$REPORTING_ID")
    elif [[ -n "$RUN_ID" ]]; then
      ARGS+=("--reporting-id" "$RUN_ID")
    fi
    [[ "$ARCHIVE_REPORTING" == "1" ]] && ARGS+=("--archive")
    [[ "$ARCHIVE_CURRENT_REPORTING" == "1" ]] && ARGS+=("--archive-current")
    [[ "$FORCE_ARCHIVE_REPORTING" == "1" ]] && ARGS+=("--force-archive")
    [[ "$SKIP_REPORTING_SITE_UPDATE" == "1" ]] && ARGS+=("--skip-reporting-site-update")
    exec bash "$REPORTING_LAUNCHER" "${ARGS[@]}"
    ;;
  completion-gate)
    [[ ! -f "$COMPLETION_GATE_LAUNCHER" ]] && { echo "Completion gate launcher not found: $COMPLETION_GATE_LAUNCHER" >&2; exit 1; }
    RESOLVED_COMPLETION_GATE_PROFILE="$COMPLETION_GATE_PROFILE"
    if [[ -z "$RESOLVED_COMPLETION_GATE_PROFILE" ]]; then
      RESOLVED_COMPLETION_GATE_PROFILE="$(python - "$CYCLE_CONFIG" <<'PY_RESOLVE_COMPLETION_PROFILE'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8-sig") as fh:
    cycle = json.load(fh)
value = (
    (cycle.get("completionGate") or {}).get("completionGateProfilePath")
    or (cycle.get("providerBackedInfrastructure") or {}).get("completionGateProfilePath")
    or (cycle.get("pipelineProfiles") or {}).get("completionGate")
    or ""
)
print(value)
PY_RESOLVE_COMPLETION_PROFILE
)"
    fi
    ARGS=("--cycle-config" "$CYCLE_CONFIG")
    [[ -n "$RESOLVED_COMPLETION_GATE_PROFILE" ]] && ARGS+=("--profile-config" "$RESOLVED_COMPLETION_GATE_PROFILE")
    [[ -n "$DIAGNOSIS_JSON" ]] && ARGS+=("--diagnosis-json" "$DIAGNOSIS_JSON")
    [[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
    if [[ -n "$EVALUATION_ID" ]]; then
      ARGS+=("--evaluation-id" "$EVALUATION_ID")
    elif [[ -n "$RUN_ID" ]]; then
      ARGS+=("--evaluation-id" "$RUN_ID")
    fi
    [[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
    exec bash "$COMPLETION_GATE_LAUNCHER" "${ARGS[@]}"
    ;;
  freeze)
    [[ ! -f "$FREEZE_LAUNCHER" ]] && { echo "Freeze launcher not found: $FREEZE_LAUNCHER" >&2; exit 1; }
    RESOLVED_FREEZE_PROFILE="$FREEZE_PROFILE"
    if [[ -z "$RESOLVED_FREEZE_PROFILE" ]]; then
      RESOLVED_FREEZE_PROFILE="$(python - "$CYCLE_CONFIG" <<'PY_RESOLVE_FREEZE_PROFILE'
import json
import sys
with open(sys.argv[1], "r", encoding="utf-8-sig") as fh:
    cycle = json.load(fh)
value = (
    (cycle.get("freeze") or {}).get("freezeProfilePath")
    or (cycle.get("freezeOutputs") or {}).get("freezeProfilePath")
    or (cycle.get("providerBackedInfrastructure") or {}).get("freezeProfilePath")
    or (cycle.get("pipelineProfiles") or {}).get("freeze")
    or ""
)
print(value)
PY_RESOLVE_FREEZE_PROFILE
)"
    fi
    ARGS=("--repo-root" "$REPO_ROOT" "--cycle-config" "$CYCLE_CONFIG")
    [[ -n "$RESOLVED_FREEZE_PROFILE" ]] && ARGS+=("--profile-config" "$RESOLVED_FREEZE_PROFILE")
    if [[ -n "$FREEZE_ID" ]]; then
      ARGS+=("--freeze-id" "$FREEZE_ID")
    elif [[ -n "$RUN_ID" ]]; then
      ARGS+=("--freeze-id" "$RUN_ID")
    fi
    [[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
    [[ "$FORCE_FREEZE" == "1" ]] && ARGS+=("--force")
    [[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
    [[ "$SKIP_COMPLETION_GATE_FOR_FREEZE" == "1" ]] && ARGS+=("--skip-completion-gate")
    [[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")
    exec bash "$FREEZE_LAUNCHER" "${ARGS[@]}"
    ;;
  localai-deployment)
    [[ ! -f "$DEPLOYMENT_LAUNCHER" ]] && { echo "Provider-backed LocalAI deployment launcher not found: $DEPLOYMENT_LAUNCHER" >&2; exit 1; }
    ARGS=("--cycle-config" "$CYCLE_CONFIG" "--action" "$DEPLOYMENT_ACTION")
    [[ -n "$DEPLOYMENT_PROFILE" ]] && ARGS+=("--deployment-profile" "$DEPLOYMENT_PROFILE")
    [[ -n "$KUBECONFIG_PATH" ]] && ARGS+=("--kubeconfig" "$KUBECONFIG_PATH")
    [[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
    [[ -n "$RUN_ID" ]] && ARGS+=("--deployment-id" "$RUN_ID")
    [[ "$DRY_RUN" == "1" ]] && ARGS+=("--dry-run")
    [[ "$SKIP_CLUSTER_VALIDATION_GATE" == "1" ]] && ARGS+=("--skip-cluster-validation-gate")
    [[ "$SKIP_SMOKE_TEST" == "1" ]] && ARGS+=("--skip-smoke-test")
    [[ -n "$BASE_URL" ]] && ARGS+=("--base-url" "$BASE_URL")
    [[ "$NO_PORT_FORWARD" == "1" ]] && ARGS+=("--no-port-forward")
    [[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")
    exec bash "$DEPLOYMENT_LAUNCHER" "${ARGS[@]}"
    ;;
  *)
    echo "Unsupported execution scope: $EXECUTION_SCOPE" >&2
    exit 2
    ;;
esac
