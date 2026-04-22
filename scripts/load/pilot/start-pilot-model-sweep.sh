#!/usr/bin/env bash
set -euo pipefail

SCENARIO=""
REPLICA=""
BASE_URL="http://localhost:8080"
MODEL=""
PROMPT="Reply with only READY."
LOCUST_FILE=""
OUTPUT_ROOT=""
MODEL_SCENARIO_CONFIG_ROOT=""
WORKER_COUNT_SCENARIO_CONFIG_ROOT=""
PLACEMENT_SCENARIO_CONFIG_ROOT=""
WORKLOAD_SCENARIO_CONFIG_ROOT=""
BASELINE_CONFIG=""
PRECHECK_CONFIG=""
KUBECONFIG_PATH=""
NAMESPACE_OVERRIDE=""
SKIP_PRECHECK=false
PHASE_CONFIG=""
WARM_UP_DURATION_OVERRIDE=""
MEASUREMENT_DURATION_OVERRIDE=""
SKIP_WARM_UP=false
PROTOCOL_CONFIG=""
CLUSTER_CAPTURE_CONFIG=""
METRIC_SET_CONFIG=""
SKIP_API_SMOKE=false
AUTO_APPLY_K8S=false
DRY_RUN=false

print_usage() {
  cat <<'USAGE'
Usage:
  ./start-pilot-model-sweep.sh --scenario M1|M2|M3|M4 --replica A|B|C [options]

Options:
  --scenario VALUE | -Scenario VALUE
  --replica VALUE | -Replica VALUE
  --base-url URL | -BaseUrl URL
  --model NAME | -Model NAME
  --prompt TEXT | -Prompt TEXT
  --locust-file PATH | -LocustFile PATH
  --output-root PATH | -OutputRoot PATH
  --model-scenario-config-root PATH | -ModelScenarioConfigRoot PATH
  --worker-count-scenario-config-root PATH
  --placement-scenario-config-root PATH | -PlacementScenarioConfigRoot PATH
  --workload-scenario-config-root PATH | -WorkloadScenarioConfigRoot PATH
  --baseline-config PATH | -BaselineConfig PATH
  --precheck-config PATH | -PrecheckConfig PATH
  --kubeconfig PATH | -Kubeconfig PATH
  --namespace NAME | -Namespace NAME
  --skip-precheck | -SkipPrecheck
  --phase-config PATH | -PhaseConfig PATH
  --warm-up-duration VALUE | -WarmUpDuration VALUE
  --measurement-duration VALUE | -MeasurementDuration VALUE
  --skip-warm-up | -SkipWarmUp
  --protocol-config PATH | -ProtocolConfig PATH
  --cluster-capture-config PATH | -ClusterCaptureConfig PATH
  --metric-set-config PATH | -MetricSetConfig PATH
  --skip-api-smoke | -SkipApiSmoke
  --dry-run | -DryRun
  --help | -Help
USAGE
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Errore: il comando richiesto non è disponibile nel PATH: $cmd" >&2
    exit 1
  fi
}

require_python_command() {
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return 0
  fi

  if command -v python >/dev/null 2>&1; then
    echo "python"
    return 0
  fi

  echo "Errore: impossibile trovare python3 o python nel PATH." >&2
  exit 1
}

resolve_repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd -- "$script_dir/../../.." && pwd
}

validate_model_scenario() {
  case "$1" in
    M1|M2|M3|M4) ;;
    *)
      echo "Scenario modello non supportato: $1" >&2
      exit 1
      ;;
  esac
}

validate_replica() {
  case "$1" in
    A|B|C) ;;
    *)
      echo "Replica non supportata: $1" >&2
      exit 1
      ;;
  esac
}

get_json_properties() {
  local scenario_file="$1"
  local required_keys_csv="$2"
  local python_cmd
  python_cmd="$(require_python_command)"

  mapfile -t JSON_VALUES < <("$python_cmd" - "$scenario_file" "$required_keys_csv" <<'PY'
import json
import sys
from pathlib import Path

scenario_path = Path(sys.argv[1])
required = [key for key in sys.argv[2].split(',') if key]
with scenario_path.open('r', encoding='utf-8-sig') as fh:
    data = json.load(fh)
missing = [key for key in required if key not in data]
if missing:
    print(
        f"Il file di configurazione dello scenario '{scenario_path}' non contiene le proprietà obbligatorie: {', '.join(missing)}.",
        file=sys.stderr,
    )
    sys.exit(1)
print(str(scenario_path))
for key in required:
    print(str(data[key]))
PY
)
}

write_unsupported_model_artifacts() {
  local output_prefix="$1"
  local scenario="$2"
  local replica="$3"
  local model_name="$4"
  local timeout_seconds="$5"
  local reason="$6"
  local namespace="$7"
  local json_path="${output_prefix}_unsupported.json"
  local text_path="${output_prefix}_unsupported.txt"

  "$PYTHON_CMD" - "$json_path" "$scenario" "$replica" "$model_name" "$timeout_seconds" "$reason" "$namespace" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
payload = {
    "family": "model",
    "scenario": sys.argv[2],
    "replica": sys.argv[3],
    "status": "unsupported_under_current_constraints",
    "namespace": sys.argv[7],
    "model": sys.argv[4],
    "timeoutSeconds": int(sys.argv[5]),
    "reason": sys.argv[6],
    "evidence": "api_smoke_timeout",
}
out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY

  cat > "$text_path" <<EOF
=============================================
 Unsupported Scenario Report
=============================================
Family                : model
Scenario              : $scenario
Replica               : $replica
Status                : unsupported_under_current_constraints
Namespace             : $namespace
Model                 : $model_name
Timeout (s)           : $timeout_seconds
Reason                : $reason
EOF

  UNSUPPORTED_JSON_PATH="$json_path"
  UNSUPPORTED_TEXT_PATH="$text_path"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario|-Scenario) SCENARIO="$2"; shift 2 ;;
    --replica|-Replica) REPLICA="$2"; shift 2 ;;
    --base-url|-BaseUrl) BASE_URL="$2"; shift 2 ;;
    --model|-Model) MODEL="$2"; shift 2 ;;
    --prompt|-Prompt) PROMPT="$2"; shift 2 ;;
    --locust-file|-LocustFile) LOCUST_FILE="$2"; shift 2 ;;
    --output-root|-OutputRoot) OUTPUT_ROOT="$2"; shift 2 ;;
    --model-scenario-config-root|-ModelScenarioConfigRoot) MODEL_SCENARIO_CONFIG_ROOT="$2"; shift 2 ;;
    --worker-count-scenario-config-root|-WorkerCountScenarioConfigRoot) WORKER_COUNT_SCENARIO_CONFIG_ROOT="$2"; shift 2 ;;
    --placement-scenario-config-root|-PlacementScenarioConfigRoot) PLACEMENT_SCENARIO_CONFIG_ROOT="$2"; shift 2 ;;
    --workload-scenario-config-root|-WorkloadScenarioConfigRoot) WORKLOAD_SCENARIO_CONFIG_ROOT="$2"; shift 2 ;;
    --baseline-config|-BaselineConfig) BASELINE_CONFIG="$2"; shift 2 ;;
    --precheck-config|-PrecheckConfig) PRECHECK_CONFIG="$2"; shift 2 ;;
    --kubeconfig|-Kubeconfig) KUBECONFIG_PATH="$2"; shift 2 ;;
    --namespace|-Namespace) NAMESPACE_OVERRIDE="$2"; shift 2 ;;
    --skip-precheck|-SkipPrecheck) SKIP_PRECHECK=true; shift ;;
    --phase-config|-PhaseConfig) PHASE_CONFIG="$2"; shift 2 ;;
    --warm-up-duration|-WarmUpDuration) WARM_UP_DURATION_OVERRIDE="$2"; shift 2 ;;
    --measurement-duration|-MeasurementDuration) MEASUREMENT_DURATION_OVERRIDE="$2"; shift 2 ;;
    --skip-warm-up|-SkipWarmUp) SKIP_WARM_UP=true; shift ;;
    --protocol-config|-ProtocolConfig) PROTOCOL_CONFIG="$2"; shift 2 ;;
    --cluster-capture-config|-ClusterCaptureConfig) CLUSTER_CAPTURE_CONFIG="$2"; shift 2 ;;
    --metric-set-config|-MetricSetConfig) METRIC_SET_CONFIG="$2"; shift 2 ;;
    --skip-api-smoke|-SkipApiSmoke) SKIP_API_SMOKE=true; shift ;;
    --auto-apply-k8s|-AutoApplyK8s) AUTO_APPLY_K8S=true; shift ;;
    --dry-run|-DryRun) DRY_RUN=true; shift ;;
    --help|-Help) print_usage; exit 0 ;;
    *) echo "Argomento non riconosciuto: $1" >&2; print_usage >&2; exit 1 ;;
  esac
done

[[ -n "$SCENARIO" ]] || { echo "Il parametro Scenario è obbligatorio." >&2; print_usage >&2; exit 1; }
[[ -n "$REPLICA" ]] || { echo "Il parametro Replica è obbligatorio." >&2; print_usage >&2; exit 1; }
validate_model_scenario "$SCENARIO"
validate_replica "$REPLICA"
PYTHON_CMD="$(require_python_command)"

REPO_ROOT="$(resolve_repo_root)"
source "$REPO_ROOT/scripts/load/lib/bash/run-kubernetes-apply.sh"
source "$REPO_ROOT/scripts/load/lib/bash/run-port-forward.sh"
PHASE_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-phases.sh"
PROTOCOL_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-protocol.sh"
CLUSTER_CAPTURE_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-cluster-capture.sh"
METRIC_SET_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-metric-set.sh"

[[ -n "$LOCUST_FILE" ]] || LOCUST_FILE="$REPO_ROOT/load-tests/locust/locustfile.py"
[[ -n "$OUTPUT_ROOT" ]] || OUTPUT_ROOT="$REPO_ROOT/results/pilot/models"
[[ -n "$MODEL_SCENARIO_CONFIG_ROOT" ]] || MODEL_SCENARIO_CONFIG_ROOT="$REPO_ROOT/config/scenarios/pilot/models"
[[ -n "$WORKER_COUNT_SCENARIO_CONFIG_ROOT" ]] || WORKER_COUNT_SCENARIO_CONFIG_ROOT="$REPO_ROOT/config/scenarios/pilot/worker-count"
[[ -n "$PLACEMENT_SCENARIO_CONFIG_ROOT" ]] || PLACEMENT_SCENARIO_CONFIG_ROOT="$REPO_ROOT/config/scenarios/pilot/placement"
[[ -n "$WORKLOAD_SCENARIO_CONFIG_ROOT" ]] || WORKLOAD_SCENARIO_CONFIG_ROOT="$REPO_ROOT/config/scenarios/pilot/workload"
[[ -n "$BASELINE_CONFIG" ]] || BASELINE_CONFIG="$REPO_ROOT/config/scenarios/baseline/B0.json"
[[ -n "$PRECHECK_CONFIG" ]] || PRECHECK_CONFIG="$REPO_ROOT/config/precheck/TC1.json"
[[ -n "$PHASE_CONFIG" ]] || PHASE_CONFIG="$REPO_ROOT/config/phases/WM1.json"
[[ -n "$PROTOCOL_CONFIG" ]] || PROTOCOL_CONFIG="$REPO_ROOT/config/protocol/EP1.json"
[[ -n "$CLUSTER_CAPTURE_CONFIG" ]] || CLUSTER_CAPTURE_CONFIG="$REPO_ROOT/config/cluster-capture/CS1.json"
[[ -n "$METRIC_SET_CONFIG" ]] || METRIC_SET_CONFIG="$REPO_ROOT/config/metric-set/MS1.json"

PRECHECK_SCRIPT="$REPO_ROOT/scripts/validation/precheck/invoke-benchmark-precheck.sh"
CLUSTER_CAPTURE_SCRIPT="$REPO_ROOT/scripts/validation/cluster-side/collect-cluster-side-artifacts.sh"

[[ -f "$LOCUST_FILE" ]] || { echo "Il file Locust specificato non esiste: $LOCUST_FILE" >&2; exit 1; }
[[ -f "$BASELINE_CONFIG" ]] || { echo "Il file di baseline non esiste: $BASELINE_CONFIG" >&2; exit 1; }
if [[ "$SKIP_PRECHECK" != true && ! -f "$PRECHECK_SCRIPT" ]]; then echo "Lo script di pre-check non esiste: $PRECHECK_SCRIPT" >&2; exit 1; fi
[[ -f "$PHASE_HELPER" ]] || { echo "Lo script helper delle fasi non esiste: $PHASE_HELPER" >&2; exit 1; }
[[ -f "$PROTOCOL_HELPER" ]] || { echo "Lo script helper del protocollo non esiste: $PROTOCOL_HELPER" >&2; exit 1; }
[[ -f "$CLUSTER_CAPTURE_HELPER" ]] || { echo "Lo script helper della cluster-side collection non esiste: $CLUSTER_CAPTURE_HELPER" >&2; exit 1; }
[[ -f "$METRIC_SET_HELPER" ]] || { echo "Lo script helper del metric set non esiste: $METRIC_SET_HELPER" >&2; exit 1; }
[[ -f "$PHASE_CONFIG" ]] || { echo "Il file di profilo warm-up/misurazione non esiste: $PHASE_CONFIG" >&2; exit 1; }
[[ -f "$PROTOCOL_CONFIG" ]] || { echo "Il file di protocollo non esiste: $PROTOCOL_CONFIG" >&2; exit 1; }
[[ -f "$CLUSTER_CAPTURE_CONFIG" ]] || { echo "Il file di cluster-side collection non esiste: $CLUSTER_CAPTURE_CONFIG" >&2; exit 1; }
[[ -f "$METRIC_SET_CONFIG" ]] || { echo "Il file di metric set non esiste: $METRIC_SET_CONFIG" >&2; exit 1; }
[[ -f "$CLUSTER_CAPTURE_SCRIPT" ]] || { echo "Lo script di cluster-side collection non esiste: $CLUSTER_CAPTURE_SCRIPT" >&2; exit 1; }

if [[ "$DRY_RUN" != true ]]; then require_command locust; fi
source "$PHASE_HELPER"
source "$PROTOCOL_HELPER"
source "$CLUSTER_CAPTURE_HELPER"
source "$METRIC_SET_HELPER"
phase_load_profile "$PHASE_CONFIG"
protocol_load_profile "$PROTOCOL_CONFIG"
cluster_load_profile "$CLUSTER_CAPTURE_CONFIG"
metric_set_load_profile "$METRIC_SET_CONFIG"
API_SMOKE_SCRIPT="$REPO_ROOT/$PROTOCOL_API_SMOKE_SCRIPT_BASH_REL"
API_SMOKE_ENABLED="$PROTOCOL_API_SMOKE_ENABLED_DEFAULT"
if [[ "$SKIP_API_SMOKE" == "true" ]]; then API_SMOKE_ENABLED="false"; fi
if [[ "$API_SMOKE_ENABLED" == "true" && ! -f "$API_SMOKE_SCRIPT" ]]; then echo "Lo script di API smoke non esiste: $API_SMOKE_SCRIPT" >&2; exit 1; fi

MODEL_SCENARIO_FILE="$MODEL_SCENARIO_CONFIG_ROOT/${SCENARIO}.json"
[[ -f "$MODEL_SCENARIO_FILE" ]] || { echo "Il file di configurazione dello scenario non esiste: $MODEL_SCENARIO_FILE" >&2; exit 1; }
get_json_properties "$MODEL_SCENARIO_FILE" "scenarioId,purpose,modelName,outputSubdir,referenceBaselineId,serverManifest"
MODEL_SCENARIO_FILE_RESOLVED="${JSON_VALUES[0]}"
SCENARIO_ID="${JSON_VALUES[1]}"
PURPOSE="${JSON_VALUES[2]}"
RESOLVED_MODEL_FROM_FILE="${JSON_VALUES[3]}"
OUTPUT_SUBDIR="${JSON_VALUES[4]}"
REFERENCE_BASELINE_ID="${JSON_VALUES[5]}"
SERVER_MANIFEST_REL="${JSON_VALUES[6]}"

get_json_properties "$BASELINE_CONFIG" "baselineId,purpose,workerMode,workerScenario,resolvedWorkerCount,placementScenario,resolvedPlacementType,workloadScenario,resolvedWorkload,topologyDir,namespaceManifest,storageManifest,prompt,temperature,requestTimeoutSeconds"
BASELINE_CONFIG_FILE_RESOLVED="${JSON_VALUES[0]}"
BASELINE_ID="${JSON_VALUES[1]}"
BASELINE_PURPOSE="${JSON_VALUES[2]}"
BASELINE_WORKER_MODE="${JSON_VALUES[3]}"
BASELINE_WORKER_SCENARIO="${JSON_VALUES[4]}"
BASELINE_RESOLVED_WORKER_COUNT="${JSON_VALUES[5]}"
BASELINE_PLACEMENT_SCENARIO="${JSON_VALUES[6]}"
BASELINE_PLACEMENT_TYPE="${JSON_VALUES[7]}"
BASELINE_WORKLOAD_SCENARIO="${JSON_VALUES[8]}"
BASELINE_RESOLVED_WORKLOAD_JSON="${JSON_VALUES[9]}"
BASELINE_TOPOLOGY_DIR_REL="${JSON_VALUES[10]}"
BASELINE_NAMESPACE_MANIFEST_REL="${JSON_VALUES[11]}"
BASELINE_STORAGE_MANIFEST_REL="${JSON_VALUES[12]}"
BASELINE_PROMPT="${JSON_VALUES[13]}"
BASELINE_TEMPERATURE="${JSON_VALUES[14]}"
BASELINE_REQUEST_TIMEOUT_SECONDS="${JSON_VALUES[15]}"

if [[ "$REFERENCE_BASELINE_ID" != "$BASELINE_ID" ]]; then
  echo "Lo scenario model $SCENARIO richiede la baseline $REFERENCE_BASELINE_ID ma il file fornito espone $BASELINE_ID." >&2
  exit 1
fi

WORKER_SCENARIO_FILE="$WORKER_COUNT_SCENARIO_CONFIG_ROOT/${BASELINE_WORKER_SCENARIO}.json"
PLACEMENT_SCENARIO_FILE="$PLACEMENT_SCENARIO_CONFIG_ROOT/${BASELINE_PLACEMENT_SCENARIO}.json"
WORKLOAD_SCENARIO_FILE="$WORKLOAD_SCENARIO_CONFIG_ROOT/${BASELINE_WORKLOAD_SCENARIO}.json"

get_json_properties "$WORKER_SCENARIO_FILE" "scenarioId,purpose,workerCount,outputSubdir,referenceBaselineId"
WORKER_SCENARIO_FILE_RESOLVED="${JSON_VALUES[0]}"
WORKER_COUNT="${JSON_VALUES[3]}"
if [[ "${JSON_VALUES[1]}" != "$BASELINE_WORKER_SCENARIO" || "${JSON_VALUES[3]}" != "$BASELINE_RESOLVED_WORKER_COUNT" ]]; then
  echo "La baseline model non è coerente con lo scenario worker di riferimento." >&2
  exit 1
fi

get_json_properties "$PLACEMENT_SCENARIO_FILE" "scenarioId,placementType,topologyDir"
PLACEMENT_SCENARIO_FILE_RESOLVED="${JSON_VALUES[0]}"
TOPOLOGY_DIR_REL="${JSON_VALUES[3]}"
if [[ "${JSON_VALUES[1]}" != "$BASELINE_PLACEMENT_SCENARIO" || "${JSON_VALUES[2]}" != "$BASELINE_PLACEMENT_TYPE" || "${JSON_VALUES[3]}" != "$BASELINE_TOPOLOGY_DIR_REL" ]]; then
  echo "La baseline model non è coerente con lo scenario placement di riferimento." >&2
  exit 1
fi

get_json_properties "$WORKLOAD_SCENARIO_FILE" "scenarioId,purpose,users,spawnRate,runTime,outputSubdir"
WORKLOAD_SCENARIO_FILE_RESOLVED="${JSON_VALUES[0]}"
WORKLOAD_PURPOSE="${JSON_VALUES[2]}"
USERS="${JSON_VALUES[3]}"
SPAWN_RATE="${JSON_VALUES[4]}"
RUN_TIME="${JSON_VALUES[5]}"
if [[ "${JSON_VALUES[1]}" != "$BASELINE_WORKLOAD_SCENARIO" ]]; then
  echo "La baseline model non è coerente con lo scenario workload di riferimento." >&2
  exit 1
fi

if [[ -n "$MODEL" && "$MODEL" != "$RESOLVED_MODEL_FROM_FILE" ]]; then
  echo "Il model sweep è ancorato allo scenario $SCENARIO. Il modello richiesto ($MODEL) non coincide con il modello risolto dello scenario ($RESOLVED_MODEL_FROM_FILE)." >&2
  exit 1
fi
MODEL="$RESOLVED_MODEL_FROM_FILE"

if [[ -n "$PROMPT" && "$PROMPT" != "$BASELINE_PROMPT" ]]; then
  echo "Il model sweep è ancorato alla baseline $BASELINE_ID. Il prompt richiesto non coincide con il prompt fisso di baseline." >&2
  exit 1
fi
PROMPT="$BASELINE_PROMPT"

TOPOLOGY_ROOT="$REPO_ROOT/$BASELINE_TOPOLOGY_DIR_REL"
SERVER_MANIFEST="$REPO_ROOT/$SERVER_MANIFEST_REL"
NAMESPACE_MANIFEST="$REPO_ROOT/$BASELINE_NAMESPACE_MANIFEST_REL"
STORAGE_MANIFEST="$REPO_ROOT/$BASELINE_STORAGE_MANIFEST_REL"
SHARED_COMPOSITION_DIR="$REPO_ROOT/infra/k8s/compositions/shared/rpc-workers-services"
K8S_APPLY_TARGETS=(
  "$NAMESPACE_MANIFEST"
  "$SHARED_COMPOSITION_DIR"
  "$STORAGE_MANIFEST"
  "$TOPOLOGY_ROOT"
  "$SERVER_MANIFEST"
)
for target in "${K8S_APPLY_TARGETS[@]}"; do
  require_k8s_apply_target "$target"
done

OUTPUT_DIR="$OUTPUT_ROOT/$OUTPUT_SUBDIR"
mkdir -p -- "$OUTPUT_DIR"
RUN_ID="${SCENARIO}_run${REPLICA}"
CSV_PREFIX="$OUTPUT_DIR/$RUN_ID"

phase_resolve_plan "$USERS" "$SPAWN_RATE" "$RUN_TIME" "$CSV_PREFIX" "$WARM_UP_DURATION_OVERRIDE" "$MEASUREMENT_DURATION_OVERRIDE" "$SKIP_WARM_UP"
phase_write_manifest "$PHASE_MANIFEST_PATH"
protocol_resolve_paths "$PHASE_MEASUREMENT_CSV_PREFIX"
cluster_resolve_stage_paths "$PHASE_MEASUREMENT_CSV_PREFIX"

PRECHECK_ARGS=(
  "$PRECHECK_SCRIPT"
  "--profile-config" "$PRECHECK_CONFIG"
  "--output-prefix" "$CSV_PREFIX"
  "--base-url" "$BASE_URL"
)
if [[ -n "$MODEL" ]]; then PRECHECK_ARGS+=("--model" "$MODEL"); fi
if [[ -n "$KUBECONFIG_PATH" ]]; then PRECHECK_ARGS+=("--kubeconfig" "$KUBECONFIG_PATH"); fi
if [[ -n "$NAMESPACE_OVERRIDE" ]]; then PRECHECK_ARGS+=("--namespace" "$NAMESPACE_OVERRIDE"); fi

API_SMOKE_ARGS=(
  "$API_SMOKE_SCRIPT"
  "--base-url" "$BASE_URL"
  "--model" "$MODEL"
  "--request-timeout-seconds" "$BASELINE_REQUEST_TIMEOUT_SECONDS"
  "--exit-unsupported-on-timeout"
  "--unsupported-exit-code" "42"
)

PRECHECK_COMMAND_STR=""
if [[ "$SKIP_PRECHECK" != true ]]; then PRECHECK_COMMAND_STR="$(protocol_quote_command "${PRECHECK_ARGS[@]}")"; fi

API_SMOKE_COMMAND_STR=""
if [[ "$API_SMOKE_ENABLED" == "true" ]]; then API_SMOKE_COMMAND_STR="$(protocol_quote_command "${API_SMOKE_ARGS[@]}")"; fi

CLUSTER_CAPTURE_PRE_ARGS=(
  "$CLUSTER_CAPTURE_SCRIPT"
  "--profile-config" "$CLUSTER_CAPTURE_CONFIG"
  "--output-prefix" "$CLUSTER_CAPTURE_PRE_PREFIX"
  "--stage" "pre"
)

CLUSTER_CAPTURE_POST_ARGS=(
  "$CLUSTER_CAPTURE_SCRIPT"
  "--profile-config" "$CLUSTER_CAPTURE_CONFIG"
  "--output-prefix" "$CLUSTER_CAPTURE_POST_PREFIX"
  "--stage" "post"
)

if [[ -n "$KUBECONFIG_PATH" ]]; then
  CLUSTER_CAPTURE_PRE_ARGS+=("--kubeconfig" "$KUBECONFIG_PATH")
  CLUSTER_CAPTURE_POST_ARGS+=("--kubeconfig" "$KUBECONFIG_PATH")
fi

if [[ -n "${NAMESPACE_OVERRIDE:-}" ]]; then
  CLUSTER_CAPTURE_PRE_ARGS+=("--namespace" "$NAMESPACE_OVERRIDE")
  CLUSTER_CAPTURE_POST_ARGS+=("--namespace" "$NAMESPACE_OVERRIDE")
fi

CLUSTER_CAPTURE_PRE_COMMAND_STR="$(protocol_quote_command "${CLUSTER_CAPTURE_PRE_ARGS[@]}")"
CLUSTER_CAPTURE_POST_COMMAND_STR="$(protocol_quote_command "${CLUSTER_CAPTURE_POST_ARGS[@]}")"
CLUSTER_CAPTURE_PRE_ARTIFACTS_JSON="$(cluster_artifacts_json "$CLUSTER_CAPTURE_PRE_PREFIX")"
CLUSTER_CAPTURE_POST_ARTIFACTS_JSON="$(cluster_artifacts_json "$CLUSTER_CAPTURE_POST_PREFIX")"

metric_set_resolve_paths "$PHASE_MEASUREMENT_CSV_PREFIX"
METRIC_SET_CLIENT_SOURCE_ARTIFACTS_JSON="$(metric_set_client_artifacts_json "$PHASE_MEASUREMENT_CSV_PREFIX")"
METRIC_SET_CLUSTER_SOURCE_ARTIFACTS_JSON="$(metric_set_cluster_artifacts_json "$CLUSTER_CAPTURE_PRE_PREFIX" "$CLUSTER_CAPTURE_POST_PREFIX")"
metric_set_write_files "$METRIC_SET_MANIFEST_PATH" "$METRIC_SET_TEXT_PATH" "Start-PilotModelSweep" "$RUN_ID" "$PHASE_MEASUREMENT_CSV_PREFIX" "$METRIC_SET_CLIENT_SOURCE_ARTIFACTS_JSON" "$METRIC_SET_CLUSTER_SOURCE_ARTIFACTS_JSON"

export LOCALAI_MODEL="$MODEL"
export LOCALAI_PROMPT="$PROMPT"
export LOCALAI_REQUEST_TIMEOUT_SECONDS="$BASELINE_REQUEST_TIMEOUT_SECONDS"
export LOCALAI_TEMPERATURE="$BASELINE_TEMPERATURE"

WARMUP_LOCUST_ARGS=(
  "-f" "$LOCUST_FILE"
  "-H" "$BASE_URL"
  "--headless"
  "-u" "$PHASE_WARMUP_USERS"
  "-r" "$PHASE_WARMUP_SPAWN_RATE"
  "--run-time" "$PHASE_WARMUP_DURATION"
  "--csv" "$PHASE_WARMUP_CSV_PREFIX"
  "--csv-full-history"
)

MEASUREMENT_LOCUST_ARGS=(
  "-f" "$LOCUST_FILE"
  "-H" "$BASE_URL"
  "--headless"
  "-u" "$PHASE_MEASUREMENT_USERS"
  "-r" "$PHASE_MEASUREMENT_SPAWN_RATE"
  "--run-time" "$PHASE_MEASUREMENT_DURATION"
  "--csv" "$PHASE_MEASUREMENT_CSV_PREFIX"
  "--csv-full-history"
)

RECOMMENDED_APPLY_ORDER=(
  "$(describe_k8s_apply_command "$NAMESPACE_MANIFEST")"
  "$(describe_k8s_apply_command "$SHARED_COMPOSITION_DIR")"
  "$(describe_k8s_apply_command "$STORAGE_MANIFEST")"
  "$(describe_k8s_apply_command "$TOPOLOGY_ROOT")"
  "$(describe_k8s_apply_command "$SERVER_MANIFEST")"
)
DEPLOY_ORDER_JSON="$(protocol_json_array_from_lines "${RECOMMENDED_APPLY_ORDER[@]}")"
EXTRA_PROTOCOL_ARTIFACTS_JSON="$(protocol_json_array_from_lines "$PHASE_MANIFEST_PATH" "$METRIC_SET_MANIFEST_PATH" "$METRIC_SET_TEXT_PATH")"
WARMUP_COMMAND_STR=""
if [[ "$PHASE_WARMUP_ENABLED_EFFECTIVE" == "true" ]]; then
  WARMUP_COMMAND_STR="$(protocol_quote_command locust "${WARMUP_LOCUST_ARGS[@]}")"
fi
MEASUREMENT_COMMAND_STR="$(protocol_quote_command locust "${MEASUREMENT_LOCUST_ARGS[@]}")"
PRECHECK_JSON_PROTOCOL_PATH="${CSV_PREFIX}_precheck.json"
PRECHECK_TEXT_PROTOCOL_PATH="${CSV_PREFIX}_precheck.txt"
if [[ -n "${PRECHECK_JSON_PATH:-}" ]]; then PRECHECK_JSON_PROTOCOL_PATH="$PRECHECK_JSON_PATH"; fi
if [[ -n "${PRECHECK_TEXT_PATH:-}" ]]; then PRECHECK_TEXT_PROTOCOL_PATH="$PRECHECK_TEXT_PATH"; fi
protocol_write_files "$PROTOCOL_MANIFEST_PATH" "$PROTOCOL_TEXT_PATH" "Start-PilotModelSweep" "$RUN_ID" \
  "Ensure the namespace is in the expected state before applying manifests and running the benchmark." "$DEPLOY_ORDER_JSON" "$([[ "$SKIP_PRECHECK" == true ]] && echo false || echo true)" "$PRECHECK_COMMAND_STR" "$PRECHECK_JSON_PROTOCOL_PATH" "$PRECHECK_TEXT_PROTOCOL_PATH" \
  "$API_SMOKE_ENABLED" "$API_SMOKE_COMMAND_STR" "$MODEL" "$PHASE_WARMUP_ENABLED_EFFECTIVE" "$WARMUP_COMMAND_STR" "$PHASE_WARMUP_CSV_PREFIX" "$MEASUREMENT_COMMAND_STR" "$PHASE_MEASUREMENT_CSV_PREFIX" "$PHASE_MANIFEST_PATH" "$EXTRA_PROTOCOL_ARTIFACTS_JSON" "$([[ "$SKIP_PRECHECK" == true ]] && echo true || echo true)" "$CLUSTER_CAPTURE_PRE_COMMAND_STR" "$CLUSTER_CAPTURE_PRE_ARTIFACTS_JSON" "true" "$CLUSTER_CAPTURE_POST_COMMAND_STR" "$CLUSTER_CAPTURE_POST_ARTIFACTS_JSON"

echo "============================================="
echo " Official Pilot Model Sweep Launcher"
echo "============================================="
echo "Repository                   : $REPO_ROOT"
echo "Model scenario               : $SCENARIO"
echo "Replica                      : $REPLICA"
echo "Run ID                       : $RUN_ID"
echo "Purpose                      : $PURPOSE"
echo "Model cfg                    : $MODEL_SCENARIO_FILE_RESOLVED"
echo "Reference baseline           : $BASELINE_ID"
echo "Baseline config              : $BASELINE_CONFIG_FILE_RESOLVED"
echo "Baseline purpose             : $BASELINE_PURPOSE"
echo "Resolved model               : $MODEL"
echo "Fixed worker-count scenario  : $BASELINE_WORKER_SCENARIO"
echo "Worker-count cfg             : $WORKER_SCENARIO_FILE_RESOLVED"
echo "Worker count                 : $WORKER_COUNT"
echo "Fixed placement              : $BASELINE_PLACEMENT_SCENARIO ($BASELINE_PLACEMENT_TYPE)"
echo "Placement cfg                : $PLACEMENT_SCENARIO_FILE_RESOLVED"
echo "Fixed workload               : $BASELINE_WORKLOAD_SCENARIO"
echo "Workload cfg                 : $WORKLOAD_SCENARIO_FILE_RESOLVED"
echo "Workload purpose             : $WORKLOAD_PURPOSE"
echo "Scenario users               : $USERS"
echo "Scenario spawn rate          : $SPAWN_RATE"
echo "Scenario run time            : $RUN_TIME"
echo "Topology target              : $TOPOLOGY_ROOT"
echo "Server target                : $SERVER_MANIFEST"
echo "Base URL                     : $BASE_URL"
echo "Model                        : $MODEL"
echo "Prompt                       : $PROMPT"
echo "Temperature                  : $BASELINE_TEMPERATURE"
echo "Request timeout (s)          : $BASELINE_REQUEST_TIMEOUT_SECONDS"
echo "Locust file                  : $LOCUST_FILE"
echo "Output root                  : $OUTPUT_ROOT"
echo "Output dir                   : $OUTPUT_DIR"
echo "CSV prefix                   : $CSV_PREFIX"
echo "Phase profile                : $PHASE_PROFILE_FILE_RESOLVED"
echo "Warm-up enabled              : $PHASE_WARMUP_ENABLED_EFFECTIVE"
echo "Warm-up duration             : $PHASE_WARMUP_DURATION"
echo "Warm-up users                : $PHASE_WARMUP_USERS"
echo "Warm-up spawn rate           : $PHASE_WARMUP_SPAWN_RATE"
echo "Warm-up CSV prefix           : $PHASE_WARMUP_CSV_PREFIX"
echo "Measurement duration         : $PHASE_MEASUREMENT_DURATION"
echo "Measurement users            : $PHASE_MEASUREMENT_USERS"
echo "Measurement spawn rate       : $PHASE_MEASUREMENT_SPAWN_RATE"
echo "Measurement CSV prefix       : $PHASE_MEASUREMENT_CSV_PREFIX"
echo "Phase manifest               : $PHASE_MANIFEST_PATH"
echo "Protocol profile             : $PROTOCOL_PROFILE_FILE_RESOLVED"
echo "Protocol manifest            : $PROTOCOL_MANIFEST_PATH"
echo "Protocol text                : $PROTOCOL_TEXT_PATH"
echo "Cluster capture profile      : $CLUSTER_PROFILE_FILE_RESOLVED"
echo "Metric set profile           : $METRIC_SET_PROFILE_FILE_RESOLVED"
echo "Metric set manifest          : $METRIC_SET_MANIFEST_PATH"
echo "Metric set text              : $METRIC_SET_TEXT_PATH"
echo "Cluster pre prefix           : $CLUSTER_CAPTURE_PRE_PREFIX"
echo "Cluster post prefix          : $CLUSTER_CAPTURE_POST_PREFIX"
echo "Auto-apply Kubernetes        : $AUTO_APPLY_K8S"
echo

echo "Target Kubernetes raccomandati da applicare prima della run:"
for manifest in "${RECOMMENDED_APPLY_ORDER[@]}"; do
  echo " - $manifest"
done
echo

if [[ "$SKIP_PRECHECK" != true ]]; then
  echo "Comando pre-check:"
  echo "$PRECHECK_COMMAND_STR"
  echo
fi

echo "Comando cluster capture (pre):"
echo "$CLUSTER_CAPTURE_PRE_COMMAND_STR"
echo

echo "Comando cluster capture (post):"
echo "$CLUSTER_CAPTURE_POST_COMMAND_STR"
echo

if [[ "$API_SMOKE_ENABLED" == "true" ]]; then
  echo "Comando API smoke:"
  echo "$API_SMOKE_COMMAND_STR"
  echo
fi

if [[ "$PHASE_WARMUP_ENABLED_EFFECTIVE" == "true" ]]; then
  echo "Comando warm-up:"
  echo "locust ${WARMUP_LOCUST_ARGS[*]}"
  echo
else
  echo "Warm-up                : disabled"
  echo
fi

echo "Comando measurement:"
echo "locust ${MEASUREMENT_LOCUST_ARGS[*]}"
echo

if [[ "$DRY_RUN" == true ]]; then
  echo "DRY RUN completato. Nessun test eseguito."
  exit 0
fi

if [[ "$AUTO_APPLY_K8S" == true ]]; then
  echo "Applicazione automatica dei target Kubernetes raccomandati prima della run."
  for target in "${K8S_APPLY_TARGETS[@]}"; do
    invoke_k8s_apply_target "$target" "$KUBECONFIG_PATH"
  done
  ensure_local_kubernetes_port_forward "$REPO_ROOT" "$BASE_URL" "$KUBECONFIG_PATH" "$NAMESPACE_OVERRIDE"
  echo
fi

ensure_local_kubernetes_port_forward "$REPO_ROOT" "$BASE_URL" "$KUBECONFIG_PATH" "$NAMESPACE_OVERRIDE"

if [[ "$SKIP_PRECHECK" != true ]]; then
  "${PRECHECK_ARGS[@]}"
fi
if [[ "$API_SMOKE_ENABLED" == "true" ]]; then
  set +e
  "${API_SMOKE_ARGS[@]}"
  API_SMOKE_EXIT_CODE=$?
  set -e
  if [[ $API_SMOKE_EXIT_CODE -eq 42 ]]; then
    unsupported_reason="Scenario model non supportato operativamente sotto i vincoli correnti della baseline fissata: il modello '$MODEL' non ha restituito una risposta di smoke test entro ${BASELINE_REQUEST_TIMEOUT_SECONDS} secondi nella configurazione corrente di LocalAI worker mode."
    write_unsupported_model_artifacts "$CSV_PREFIX" "$SCENARIO" "$REPLICA" "$MODEL" "$BASELINE_REQUEST_TIMEOUT_SECONDS" "$unsupported_reason" "$NAMESPACE_OVERRIDE"
    echo
    echo "Scenario non supportato operativamente."
    echo "$unsupported_reason"
    echo "Report JSON            : $UNSUPPORTED_JSON_PATH"
    echo "Report text            : $UNSUPPORTED_TEXT_PATH"
    exit 42
  fi
  if [[ $API_SMOKE_EXIT_CODE -ne 0 ]]; then
    echo "API smoke terminato con FAIL (exit code $API_SMOKE_EXIT_CODE). La run viene interrotta senza eseguire warm-up o measurement." >&2
    exit $API_SMOKE_EXIT_CODE
  fi
fi
"${CLUSTER_CAPTURE_PRE_ARGS[@]}"
if [[ "$PHASE_WARMUP_ENABLED_EFFECTIVE" == "true" ]]; then
  export LOCALAI_STARTUP_MODEL_CHECK_ENABLED="$PHASE_WARMUP_STARTUP_MODEL_CHECK_ENABLED"
  locust "${WARMUP_LOCUST_ARGS[@]}"
fi
export LOCALAI_STARTUP_MODEL_CHECK_ENABLED="$PHASE_MEASUREMENT_STARTUP_MODEL_CHECK_ENABLED"
locust "${MEASUREMENT_LOCUST_ARGS[@]}"
EXIT_CODE=$?
"${CLUSTER_CAPTURE_POST_ARGS[@]}"
CLUSTER_CAPTURE_POST_EXIT_CODE=$?

echo
if [[ $EXIT_CODE -eq 0 && $CLUSTER_CAPTURE_POST_EXIT_CODE -eq 0 ]]; then
  echo "Run completata con successo."
  echo "File attesi:"
  if [[ "$PHASE_WARMUP_ENABLED_EFFECTIVE" == "true" ]]; then
    echo " - ${PHASE_WARMUP_CSV_PREFIX}_stats.csv"
    echo " - ${PHASE_WARMUP_CSV_PREFIX}_stats_history.csv"
    echo " - ${PHASE_WARMUP_CSV_PREFIX}_failures.csv"
    echo " - ${PHASE_WARMUP_CSV_PREFIX}_exceptions.csv"
  fi
  echo " - ${PHASE_MEASUREMENT_CSV_PREFIX}_stats.csv"
  echo " - ${PHASE_MEASUREMENT_CSV_PREFIX}_stats_history.csv"
  echo " - ${PHASE_MEASUREMENT_CSV_PREFIX}_failures.csv"
  echo " - ${PHASE_MEASUREMENT_CSV_PREFIX}_exceptions.csv"
  echo "Cluster-side artifacts (pre):"
  "$PYTHON_CMD" - <<'PY' "$CLUSTER_CAPTURE_PRE_ARTIFACTS_JSON"
import json,sys
for item in json.loads(sys.argv[1]):
    print(f" - {item}")
PY
  echo "Metric-set artifacts:"
  echo " - $METRIC_SET_MANIFEST_PATH"
  echo " - $METRIC_SET_TEXT_PATH"
  echo "Cluster-side artifacts (post):"
  "$PYTHON_CMD" - <<'PY' "$CLUSTER_CAPTURE_POST_ARTIFACTS_JSON"
import json,sys
for item in json.loads(sys.argv[1]):
    print(f" - {item}")
PY
  exit 0
fi

if [[ $EXIT_CODE -ne 0 ]]; then
  echo "La run Locust è terminata con exit code $EXIT_CODE." >&2
  exit $EXIT_CODE
fi

echo "La cluster-side collection finale è terminata con exit code $CLUSTER_CAPTURE_POST_EXIT_CODE." >&2
exit $CLUSTER_CAPTURE_POST_EXIT_CODE
