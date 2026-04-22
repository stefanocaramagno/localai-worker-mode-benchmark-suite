#!/usr/bin/env bash
set -euo pipefail

BASELINE_CONFIG=""
REPLICA=""
BASE_URL=""
LOCUST_FILE=""
OUTPUT_ROOT=""
PRECHECK_CONFIG=""
KUBECONFIG_PATH=""
NAMESPACE=""
SKIP_PRECHECK=false
PHASE_CONFIG=""
WARM_UP_DURATION_OVERRIDE=""
MEASUREMENT_DURATION_OVERRIDE=""
SKIP_WARM_UP=false
PROTOCOL_CONFIG=""
CLUSTER_CAPTURE_CONFIG=""
METRIC_SET_CONFIG=""
SKIP_API_SMOKE=false
DRY_RUN=false

print_usage() {
  cat <<'USAGE'
Usage:
  ./start-official-baseline.sh --replica A|B|C [options]

Options:
  --replica VALUE | -Replica VALUE
  --baseline-config PATH | -BaselineConfig PATH
  --base-url URL | -BaseUrl URL
  --locust-file PATH | -LocustFile PATH
  --output-root PATH | -OutputRoot PATH
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

validate_replica() {
  case "$1" in
    A|B|C) ;;
    *)
      echo "Replica non supportata: $1" >&2
      exit 1
      ;;
  esac
}

load_json_file() {
  local json_file="$1"
  local required_keys_csv="$2"
  local python_cmd
  python_cmd="$(require_python_command)"

  mapfile -t JSON_VALUES < <("$python_cmd" - "$json_file" "$required_keys_csv" <<'PY'
import json
import sys
from pathlib import Path

json_path = Path(sys.argv[1])
required = [key for key in sys.argv[2].split(',') if key]
with json_path.open('r', encoding='utf-8-sig') as fh:
    data = json.load(fh)
missing = [key for key in required if key not in data]
if missing:
    print(f"Il file JSON '{json_path}' non contiene le proprietà obbligatorie: {', '.join(missing)}.", file=sys.stderr)
    sys.exit(1)
print(str(json_path))
for key in required:
    value = data[key]
    if isinstance(value, (dict, list)):
      print(json.dumps(value, separators=(',', ':')))
    else:
      print(str(value))
PY
)
}

resolve_k8s_apply_target_type() {
  local target="$1"
  if [[ -f "$target" ]]; then
    echo file
    return 0
  fi
  if [[ -d "$target" && -f "$target/kustomization.yaml" ]]; then
    echo directory
    return 0
  fi
  echo invalid
}

require_k8s_apply_target() {
  local target="$1"
  local kind
  kind="$(resolve_k8s_apply_target_type "$target")"
  if [[ "$kind" == invalid ]]; then
    echo "Target Kubernetes non valido o non risolvibile: $target" >&2
    exit 1
  fi
}

describe_k8s_apply_command() {
  local target="$1"
  local kind
  kind="$(resolve_k8s_apply_target_type "$target")"
  case "$kind" in
    file) printf 'kubectl apply -f %q' "$target" ;;
    directory) printf 'kubectl apply -k %q' "$target" ;;
    *) echo "Target Kubernetes non valido o non risolvibile: $target" >&2; exit 1 ;;
  esac
}

write_run_lock_file() {
  local output_path="$1"
  local python_cmd
  python_cmd="$(require_python_command)"

  "$python_cmd" - "$output_path" \
    "$BASELINE_FILE_RESOLVED" "$BASELINE_ID" "$MODEL_SCENARIO" "$MODEL_NAME" \
    "$WORKER_SCENARIO" "$WORKER_COUNT" "$PLACEMENT_SCENARIO" "$PLACEMENT_TYPE" \
    "$WORKLOAD_SCENARIO" "$USERS" "$SPAWN_RATE" "$RUN_TIME" \
    "$TOPOLOGY_DIR_REL" "$SERVER_MANIFEST_REL" "$BASE_URL" "$PROMPT" \
    "$REQUEST_TIMEOUT_SECONDS" "$TEMPERATURE" "$RUN_ID" \
    "$PHASE_WARMUP_DURATION" "$PHASE_MEASUREMENT_DURATION" <<'PY'
import json
import sys
from pathlib import Path

output_path = Path(sys.argv[1])
payload = {
    "baselineConfig": sys.argv[2],
    "baselineId": sys.argv[3],
    "resolvedConfiguration": {
        "modelScenario": sys.argv[4],
        "modelName": sys.argv[5],
        "workerScenario": sys.argv[6],
        "workerCount": int(sys.argv[7]),
        "placementScenario": sys.argv[8],
        "placementType": sys.argv[9],
        "workloadScenario": sys.argv[10],
        "users": int(sys.argv[11]),
        "spawnRate": int(sys.argv[12]),
        "scenarioRunTime": sys.argv[13],
        "topologyDir": sys.argv[14],
        "serverManifest": sys.argv[15],
        "baseUrl": sys.argv[16],
        "prompt": sys.argv[17],
        "requestTimeoutSeconds": int(float(sys.argv[18])),
        "temperature": float(sys.argv[19]),
        "warmUpDuration": sys.argv[21],
        "measurementDuration": sys.argv[22],
    },
    "runId": sys.argv[20],
}
output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding='utf-8-sig')
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --replica|-Replica)
      REPLICA="$2"
      shift 2
      ;;
    --baseline-config|-BaselineConfig)
      BASELINE_CONFIG="$2"
      shift 2
      ;;
    --base-url|-BaseUrl)
      BASE_URL="$2"
      shift 2
      ;;
    --locust-file|-LocustFile)
      LOCUST_FILE="$2"
      shift 2
      ;;
    --output-root|-OutputRoot)
      OUTPUT_ROOT="$2"
      shift 2
      ;;
    --precheck-config|-PrecheckConfig)
      PRECHECK_CONFIG="$2"
      shift 2
      ;;
    --kubeconfig|-Kubeconfig)
      KUBECONFIG_PATH="$2"
      shift 2
      ;;
    --namespace|-Namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    --skip-precheck|-SkipPrecheck)
      SKIP_PRECHECK=true
      shift
      ;;
    --phase-config|-PhaseConfig)
      PHASE_CONFIG="$2"
      shift 2
      ;;
    --warm-up-duration|-WarmUpDuration)
      WARM_UP_DURATION_OVERRIDE="$2"
      shift 2
      ;;
    --measurement-duration|-MeasurementDuration)
      MEASUREMENT_DURATION_OVERRIDE="$2"
      shift 2
      ;;
    --skip-warm-up|-SkipWarmUp)
      SKIP_WARM_UP=true
      shift
      ;;
    --dry-run|-DryRun)
      DRY_RUN=true
      shift
      ;;
    --protocol-config|-ProtocolConfig)
      PROTOCOL_CONFIG="$2"
      shift 2
      ;;
    --cluster-capture-config|-ClusterCaptureConfig)
      CLUSTER_CAPTURE_CONFIG="$2"
      shift 2
      ;;
    --metric-set-config|-MetricSetConfig)
      METRIC_SET_CONFIG="$2"
      shift 2
      ;;
    --skip-api-smoke|-SkipApiSmoke)
      SKIP_API_SMOKE=true
      shift
      ;;
    --help|-Help)
      print_usage
      exit 0
      ;;
    *)
      echo "Argomento non riconosciuto: $1" >&2
      print_usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$REPLICA" ]]; then
  echo "Il parametro Replica è obbligatorio." >&2
  print_usage >&2
  exit 1
fi
validate_replica "$REPLICA"

REPO_ROOT="$(resolve_repo_root)"
source "$REPO_ROOT/scripts/load/lib/bash/run-kubernetes-apply.sh"
source "$REPO_ROOT/scripts/load/lib/bash/run-port-forward.sh"
PHASE_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-phases.sh"
PROTOCOL_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-protocol.sh"
CLUSTER_CAPTURE_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-cluster-capture.sh"
METRIC_SET_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-metric-set.sh"
[[ -n "$BASELINE_CONFIG" ]] || BASELINE_CONFIG="$REPO_ROOT/config/scenarios/baseline/B0.json"
[[ -n "$LOCUST_FILE" ]] || LOCUST_FILE="$REPO_ROOT/load-tests/locust/locustfile.py"
[[ -n "$PRECHECK_CONFIG" ]] || PRECHECK_CONFIG="$REPO_ROOT/config/precheck/TC1.json"
[[ -n "$PHASE_CONFIG" ]] || PHASE_CONFIG="$REPO_ROOT/config/phases/WM1.json"
if [[ -z "$PROTOCOL_CONFIG" ]]; then
  PROTOCOL_CONFIG="$REPO_ROOT/config/protocol/EP1.json"
fi

if [[ -z "$CLUSTER_CAPTURE_CONFIG" ]]; then
  CLUSTER_CAPTURE_CONFIG="$REPO_ROOT/config/cluster-capture/CS1.json"
fi

if [[ -z "$METRIC_SET_CONFIG" ]]; then
  METRIC_SET_CONFIG="$REPO_ROOT/config/metric-set/MS1.json"
fi

PRECHECK_SCRIPT="$REPO_ROOT/scripts/validation/precheck/invoke-benchmark-precheck.sh"
CLUSTER_CAPTURE_SCRIPT="$REPO_ROOT/scripts/validation/cluster-side/collect-cluster-side-artifacts.sh"

[[ -f "$BASELINE_CONFIG" ]] || { echo "Il file di baseline non esiste: $BASELINE_CONFIG" >&2; exit 1; }
[[ -f "$LOCUST_FILE" ]] || { echo "Il file Locust specificato non esiste: $LOCUST_FILE" >&2; exit 1; }
if [[ "$SKIP_PRECHECK" != true && ! -f "$PRECHECK_SCRIPT" ]]; then echo "Lo script di pre-check non esiste: $PRECHECK_SCRIPT" >&2; exit 1; fi
if [[ ! -f "$PHASE_HELPER" ]]; then echo "Lo script helper delle fasi non esiste: $PHASE_HELPER" >&2; exit 1; fi
if [[ ! -f "$PHASE_CONFIG" ]]; then echo "Il file di profilo warm-up/misurazione non esiste: $PHASE_CONFIG" >&2; exit 1; fi
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
if [[ "$SKIP_API_SMOKE" == "true" ]]; then
  API_SMOKE_ENABLED="false"
fi
if [[ "$API_SMOKE_ENABLED" == "true" && ! -f "$API_SMOKE_SCRIPT" ]]; then
  echo "Lo script di API smoke non esiste: $API_SMOKE_SCRIPT" >&2
  exit 1
fi

load_json_file "$BASELINE_CONFIG" "baselineId,purpose,modelScenario,resolvedModelName,workerScenario,resolvedWorkerCount,placementScenario,resolvedPlacementType,workloadScenario,topologyDir,serverManifest,namespaceManifest,storageManifest,baseUrl,prompt,temperature,requestTimeoutSeconds,resultsRoot"
BASELINE_FILE_RESOLVED="${JSON_VALUES[0]}"
BASELINE_ID="${JSON_VALUES[1]}"
PURPOSE="${JSON_VALUES[2]}"
MODEL_SCENARIO="${JSON_VALUES[3]}"
MODEL_NAME="${JSON_VALUES[4]}"
WORKER_SCENARIO="${JSON_VALUES[5]}"
WORKER_COUNT="${JSON_VALUES[6]}"
PLACEMENT_SCENARIO="${JSON_VALUES[7]}"
PLACEMENT_TYPE="${JSON_VALUES[8]}"
WORKLOAD_SCENARIO="${JSON_VALUES[9]}"
TOPOLOGY_DIR_REL="${JSON_VALUES[10]}"
SERVER_MANIFEST_REL="${JSON_VALUES[11]}"
NAMESPACE_MANIFEST_REL="${JSON_VALUES[12]}"
STORAGE_MANIFEST_REL="${JSON_VALUES[13]}"
BASELINE_BASE_URL="${JSON_VALUES[14]}"
PROMPT="${JSON_VALUES[15]}"
TEMPERATURE="${JSON_VALUES[16]}"
REQUEST_TIMEOUT_SECONDS="${JSON_VALUES[17]}"
RESULTS_ROOT_REL="${JSON_VALUES[18]}"

[[ -n "$BASE_URL" ]] || BASE_URL="$BASELINE_BASE_URL"
[[ -n "$OUTPUT_ROOT" ]] || OUTPUT_ROOT="$REPO_ROOT/$RESULTS_ROOT_REL"

MODEL_SCENARIO_FILE="$REPO_ROOT/config/scenarios/pilot/models/${MODEL_SCENARIO}.json"
WORKER_SCENARIO_FILE="$REPO_ROOT/config/scenarios/pilot/worker-count/${WORKER_SCENARIO}.json"
PLACEMENT_SCENARIO_FILE="$REPO_ROOT/config/scenarios/pilot/placement/${PLACEMENT_SCENARIO}.json"
WORKLOAD_SCENARIO_FILE="$REPO_ROOT/config/scenarios/pilot/workload/${WORKLOAD_SCENARIO}.json"
for file in "$MODEL_SCENARIO_FILE" "$WORKER_SCENARIO_FILE" "$PLACEMENT_SCENARIO_FILE" "$WORKLOAD_SCENARIO_FILE"; do [[ -f "$file" ]] || { echo "File di scenario richiesto non trovato: $file" >&2; exit 1; }; done

load_json_file "$MODEL_SCENARIO_FILE" "scenarioId,modelName,serverManifest"
[[ "${JSON_VALUES[1]}" == "$MODEL_SCENARIO" ]] || { echo "Incoerenza baseline/model scenarioId." >&2; exit 1; }
[[ "${JSON_VALUES[2]}" == "$MODEL_NAME" ]] || { echo "Incoerenza baseline/modelName." >&2; exit 1; }
[[ "${JSON_VALUES[3]}" == "$SERVER_MANIFEST_REL" ]] || { echo "Incoerenza baseline/serverManifest." >&2; exit 1; }

load_json_file "$WORKER_SCENARIO_FILE" "scenarioId,workerCount"
[[ "${JSON_VALUES[1]}" == "$WORKER_SCENARIO" ]] || { echo "Incoerenza baseline/worker scenarioId." >&2; exit 1; }
[[ "${JSON_VALUES[2]}" == "$WORKER_COUNT" ]] || { echo "Incoerenza baseline/workerCount." >&2; exit 1; }

load_json_file "$PLACEMENT_SCENARIO_FILE" "scenarioId,placementType,topologyDir"
[[ "${JSON_VALUES[1]}" == "$PLACEMENT_SCENARIO" ]] || { echo "Incoerenza baseline/placement scenarioId." >&2; exit 1; }
[[ "${JSON_VALUES[2]}" == "$PLACEMENT_TYPE" ]] || { echo "Incoerenza baseline/placementType." >&2; exit 1; }
[[ "${JSON_VALUES[3]}" == "$TOPOLOGY_DIR_REL" ]] || { echo "Incoerenza baseline/topologyDir." >&2; exit 1; }

load_json_file "$WORKLOAD_SCENARIO_FILE" "scenarioId,users,spawnRate,runTime"
[[ "${JSON_VALUES[1]}" == "$WORKLOAD_SCENARIO" ]] || { echo "Incoerenza baseline/workload scenarioId." >&2; exit 1; }
USERS="${JSON_VALUES[2]}"
SPAWN_RATE="${JSON_VALUES[3]}"
RUN_TIME="${JSON_VALUES[4]}"

TOPOLOGY_ROOT="$REPO_ROOT/$TOPOLOGY_DIR_REL"
SERVER_MANIFEST="$REPO_ROOT/$SERVER_MANIFEST_REL"
NAMESPACE_MANIFEST="$REPO_ROOT/$NAMESPACE_MANIFEST_REL"
STORAGE_MANIFEST="$REPO_ROOT/$STORAGE_MANIFEST_REL"
SHARED_COMPOSITION_DIR="$REPO_ROOT/infra/k8s/compositions/shared/rpc-workers-services"
K8S_APPLY_TARGETS=(
  "$NAMESPACE_MANIFEST"
  "$SHARED_COMPOSITION_DIR"
  "$STORAGE_MANIFEST"
  "$TOPOLOGY_ROOT"
  "$SERVER_MANIFEST"
)
for target in "${K8S_APPLY_TARGETS[@]}"; do require_k8s_apply_target "$target"; done

RUN_ID="${BASELINE_ID}_run${REPLICA}"
OUTPUT_DIR="$OUTPUT_ROOT/${BASELINE_ID}_official_locked"
mkdir -p -- "$OUTPUT_DIR"
CSV_PREFIX="$OUTPUT_DIR/$RUN_ID"

phase_resolve_plan "$USERS" "$SPAWN_RATE" "$RUN_TIME" "$CSV_PREFIX" "$WARM_UP_DURATION_OVERRIDE" "$MEASUREMENT_DURATION_OVERRIDE" "$SKIP_WARM_UP"
phase_write_manifest "$PHASE_MANIFEST_PATH"
protocol_resolve_paths "$PHASE_MEASUREMENT_CSV_PREFIX"
cluster_resolve_stage_paths "$PHASE_MEASUREMENT_CSV_PREFIX"

RUN_LOCK_FILE="$OUTPUT_DIR/${RUN_ID}_baseline-lock.json"
write_run_lock_file "$RUN_LOCK_FILE"
PRECHECK_JSON_PATH="${CSV_PREFIX}_precheck.json"
PRECHECK_TEXT_PATH="${CSV_PREFIX}_precheck.txt"

export LOCALAI_MODEL="$MODEL_NAME"
export LOCALAI_PROMPT="$PROMPT"
export LOCALAI_REQUEST_TIMEOUT_SECONDS="$REQUEST_TIMEOUT_SECONDS"
export LOCALAI_TEMPERATURE="$TEMPERATURE"

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

PRECHECK_ARGS=(
  "--profile-config" "$PRECHECK_CONFIG"
  "--base-url" "$BASE_URL"
  "--model" "$MODEL_NAME"
  "--output-json" "$PRECHECK_JSON_PATH"
  "--output-text" "$PRECHECK_TEXT_PATH"
)

if [[ -n "$KUBECONFIG_PATH" ]]; then PRECHECK_ARGS+=("--kubeconfig" "$KUBECONFIG_PATH"); fi
if [[ -n "$NAMESPACE" ]]; then PRECHECK_ARGS+=("--namespace" "$NAMESPACE"); fi

API_SMOKE_ARGS=(
  "$API_SMOKE_SCRIPT"
  "--base-url" "$BASE_URL"
  "--model" "$MODEL_NAME"
)

PRECHECK_COMMAND_STR=""
if [[ "$SKIP_PRECHECK" != true ]]; then
  PRECHECK_COMMAND_STR="$(protocol_quote_command "${PRECHECK_ARGS[@]}")"
fi

API_SMOKE_COMMAND_STR=""
if [[ "$API_SMOKE_ENABLED" == "true" ]]; then
  API_SMOKE_COMMAND_STR="$(protocol_quote_command "${API_SMOKE_ARGS[@]}")"
fi

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

if [[ -n "${NAMESPACE:-}" ]]; then
  CLUSTER_CAPTURE_PRE_ARGS+=("--namespace" "${NAMESPACE}")
  CLUSTER_CAPTURE_POST_ARGS+=("--namespace" "${NAMESPACE}")
fi

CLUSTER_CAPTURE_PRE_COMMAND_STR="$(protocol_quote_command "${CLUSTER_CAPTURE_PRE_ARGS[@]}")"
CLUSTER_CAPTURE_POST_COMMAND_STR="$(protocol_quote_command "${CLUSTER_CAPTURE_POST_ARGS[@]}")"
CLUSTER_CAPTURE_PRE_ARTIFACTS_JSON="$(cluster_artifacts_json "$CLUSTER_CAPTURE_PRE_PREFIX")"
CLUSTER_CAPTURE_POST_ARTIFACTS_JSON="$(cluster_artifacts_json "$CLUSTER_CAPTURE_POST_PREFIX")"

metric_set_resolve_paths "$PHASE_MEASUREMENT_CSV_PREFIX"
METRIC_SET_CLIENT_SOURCE_ARTIFACTS_JSON="$(metric_set_client_artifacts_json "$PHASE_MEASUREMENT_CSV_PREFIX")"
METRIC_SET_CLUSTER_SOURCE_ARTIFACTS_JSON="$(metric_set_cluster_artifacts_json "$CLUSTER_CAPTURE_PRE_PREFIX" "$CLUSTER_CAPTURE_POST_PREFIX")"
metric_set_write_files "$METRIC_SET_MANIFEST_PATH" "$METRIC_SET_TEXT_PATH" "Start-OfficialBaseline" "$RUN_ID" "$PHASE_MEASUREMENT_CSV_PREFIX" "$METRIC_SET_CLIENT_SOURCE_ARTIFACTS_JSON" "$METRIC_SET_CLUSTER_SOURCE_ARTIFACTS_JSON"

RECOMMENDED_APPLY_ORDER=(
  "$(describe_k8s_apply_command "$NAMESPACE_MANIFEST")"
  "$(describe_k8s_apply_command "$SHARED_COMPOSITION_DIR")"
  "$(describe_k8s_apply_command "$STORAGE_MANIFEST")"
  "$(describe_k8s_apply_command "$TOPOLOGY_ROOT")"
  "$(describe_k8s_apply_command "$SERVER_MANIFEST")"
)

DEPLOY_ORDER_JSON="$(protocol_json_array_from_lines "${RECOMMENDED_APPLY_ORDER[@]}")"
EXTRA_PROTOCOL_ARTIFACTS_JSON="$(protocol_json_array_from_lines "$PHASE_MANIFEST_PATH" "$RUN_LOCK_FILE" "$METRIC_SET_MANIFEST_PATH" "$METRIC_SET_TEXT_PATH")"
WARMUP_COMMAND_STR=""
if [[ "$PHASE_WARMUP_ENABLED_EFFECTIVE" == "true" ]]; then
  WARMUP_COMMAND_STR="$(protocol_quote_command locust "${WARMUP_LOCUST_ARGS[@]}")"
fi
MEASUREMENT_COMMAND_STR="$(protocol_quote_command locust "${MEASUREMENT_LOCUST_ARGS[@]}")"
PRECHECK_JSON_PROTOCOL_PATH="${CSV_PREFIX}_precheck.json"
PRECHECK_TEXT_PROTOCOL_PATH="${CSV_PREFIX}_precheck.txt"
if [[ -n "${PRECHECK_JSON_PATH:-}" ]]; then PRECHECK_JSON_PROTOCOL_PATH="$PRECHECK_JSON_PATH"; fi
if [[ -n "${PRECHECK_TEXT_PATH:-}" ]]; then PRECHECK_TEXT_PROTOCOL_PATH="$PRECHECK_TEXT_PATH"; fi
protocol_write_files "$PROTOCOL_MANIFEST_PATH" "$PROTOCOL_TEXT_PATH" "Start-OfficialBaseline" "$RUN_ID" \
  "Ensure the namespace is in the expected state before applying manifests and running the benchmark." "$DEPLOY_ORDER_JSON" "$([[ "$SKIP_PRECHECK" == true ]] && echo false || echo true)" "$PRECHECK_COMMAND_STR" "$PRECHECK_JSON_PROTOCOL_PATH" "$PRECHECK_TEXT_PROTOCOL_PATH" \
  "$API_SMOKE_ENABLED" "$API_SMOKE_COMMAND_STR" "$MODEL_NAME" "$PHASE_WARMUP_ENABLED_EFFECTIVE" "$WARMUP_COMMAND_STR" "$PHASE_WARMUP_CSV_PREFIX" "$MEASUREMENT_COMMAND_STR" "$PHASE_MEASUREMENT_CSV_PREFIX" "$PHASE_MANIFEST_PATH" "$EXTRA_PROTOCOL_ARTIFACTS_JSON" "$([[ "$SKIP_PRECHECK" == true ]] && echo true || echo true)" "$CLUSTER_CAPTURE_PRE_COMMAND_STR" "$CLUSTER_CAPTURE_PRE_ARTIFACTS_JSON" "true" "$CLUSTER_CAPTURE_POST_COMMAND_STR" "$CLUSTER_CAPTURE_POST_ARTIFACTS_JSON"

echo "============================================="
echo " Official Locked Baseline Launcher"
echo "============================================="
echo "Repository               : $REPO_ROOT"
echo "Baseline config          : $BASELINE_FILE_RESOLVED"
echo "Baseline ID              : $BASELINE_ID"
echo "Purpose                  : $PURPOSE"
echo "Replica                  : $REPLICA"
echo "Run ID                   : $RUN_ID"
echo "Model scenario           : $MODEL_SCENARIO"
echo "Resolved model           : $MODEL_NAME"
echo "Worker-count scenario    : $WORKER_SCENARIO"
echo "Worker count             : $WORKER_COUNT"
echo "Placement scenario       : $PLACEMENT_SCENARIO"
echo "Placement type           : $PLACEMENT_TYPE"
echo "Workload scenario        : $WORKLOAD_SCENARIO"
echo "Scenario users           : $USERS"
echo "Scenario spawn rate      : $SPAWN_RATE"
echo "Scenario run time        : $RUN_TIME"
echo "Topology target          : $TOPOLOGY_ROOT"
echo "Server target            : $SERVER_MANIFEST"
echo "Base URL                 : $BASE_URL"
echo "Prompt                   : $PROMPT"
echo "Temperature              : $TEMPERATURE"
echo "Request timeout (s)      : $REQUEST_TIMEOUT_SECONDS"
echo "Locust file              : $LOCUST_FILE"
echo "Output dir               : $OUTPUT_DIR"
echo "CSV prefix               : $CSV_PREFIX"
echo "Run lock file            : $RUN_LOCK_FILE"
echo "Phase profile            : $PHASE_PROFILE_FILE_RESOLVED"
echo "Warm-up enabled          : $PHASE_WARMUP_ENABLED_EFFECTIVE"
echo "Warm-up duration         : $PHASE_WARMUP_DURATION"
echo "Warm-up users            : $PHASE_WARMUP_USERS"
echo "Warm-up spawn rate       : $PHASE_WARMUP_SPAWN_RATE"
echo "Warm-up CSV prefix       : $PHASE_WARMUP_CSV_PREFIX"
echo "Measurement duration     : $PHASE_MEASUREMENT_DURATION"
echo "Measurement users        : $PHASE_MEASUREMENT_USERS"
echo "Measurement spawn rate   : $PHASE_MEASUREMENT_SPAWN_RATE"
echo "Measurement CSV prefix   : $PHASE_MEASUREMENT_CSV_PREFIX"
echo "Phase manifest           : $PHASE_MANIFEST_PATH"
echo "Protocol profile         : $PROTOCOL_PROFILE_FILE_RESOLVED"
echo "Protocol manifest        : $PROTOCOL_MANIFEST_PATH"
echo "Protocol text            : $PROTOCOL_TEXT_PATH"
echo "Cluster capture profile  : $CLUSTER_PROFILE_FILE_RESOLVED"
echo "Metric set profile       : $METRIC_SET_PROFILE_FILE_RESOLVED"
echo "Metric set manifest      : $METRIC_SET_MANIFEST_PATH"
echo "Metric set text          : $METRIC_SET_TEXT_PATH"
echo "Cluster pre prefix       : $CLUSTER_CAPTURE_PRE_PREFIX"
echo "Cluster post prefix      : $CLUSTER_CAPTURE_POST_PREFIX"
if [[ "$SKIP_PRECHECK" == true ]]; then echo "Pre-check                : disabled"; else echo "Pre-check                : $PRECHECK_CONFIG"; fi
echo

echo "Target Kubernetes raccomandati da applicare prima della run:"
for manifest in "${RECOMMENDED_APPLY_ORDER[@]}"; do echo " - $manifest"; done
echo
if [[ "$SKIP_PRECHECK" != true ]]; then
  echo "Comando pre-check:"
  printf '%q' "$REPO_ROOT/scripts/validation/precheck/invoke-benchmark-precheck.sh"
  for arg in "${PRECHECK_ARGS[@]}"; do printf ' %q' "$arg"; done
  printf '\n\n'
fi
echo "Comando cluster capture (pre):"
printf "%s\n\n" "$CLUSTER_CAPTURE_PRE_COMMAND_STR"
echo "Comando cluster capture (post):"
printf "%s\n\n" "$CLUSTER_CAPTURE_POST_COMMAND_STR"
if [[ "$API_SMOKE_ENABLED" == "true" ]]; then
  echo "Comando API smoke:"
  printf "%s\n\n" "$API_SMOKE_COMMAND_STR"
fi
if [[ "$PHASE_WARMUP_ENABLED_EFFECTIVE" == "true" ]]; then
  echo "Comando warm-up:"
  printf 'locust'
  for arg in "${WARMUP_LOCUST_ARGS[@]}"; do printf ' %q' "$arg"; done
  printf '\n\n'
else
  echo "Warm-up                : disabled"
  echo
fi

echo "Comando measurement:"
printf 'locust'
for arg in "${MEASUREMENT_LOCUST_ARGS[@]}"; do printf ' %q' "$arg"; done
printf '\n\n'

if [[ "$DRY_RUN" == true ]]; then
  echo "DRY RUN completato. Nessun test eseguito."
  exit 0
fi

ensure_local_kubernetes_port_forward "$REPO_ROOT" "$BASE_URL" "$KUBECONFIG_PATH" "$NAMESPACE_OVERRIDE"

if [[ "$SKIP_PRECHECK" != true ]]; then
  "$REPO_ROOT/scripts/validation/precheck/invoke-benchmark-precheck.sh" "${PRECHECK_ARGS[@]}"
fi

if [[ "$PHASE_WARMUP_ENABLED_EFFECTIVE" == "true" ]]; then
  export LOCALAI_STARTUP_MODEL_CHECK_ENABLED="$PHASE_PROFILE_STARTUP_CHECK_WARMUP"
  locust "${WARMUP_LOCUST_ARGS[@]}"
fi

export LOCALAI_STARTUP_MODEL_CHECK_ENABLED="$PHASE_PROFILE_STARTUP_CHECK_MEASUREMENT"
locust "${MEASUREMENT_LOCUST_ARGS[@]}"
MEASUREMENT_EXIT_CODE=$?

set +e
"${CLUSTER_CAPTURE_POST_ARGS[@]}"
POST_CAPTURE_EXIT_CODE=$?
set -e

echo
if [[ $MEASUREMENT_EXIT_CODE -eq 0 && $POST_CAPTURE_EXIT_CODE -eq 0 ]]; then
  echo "Run completata con successo."
  if [[ "$PHASE_WARMUP_ENABLED_EFFECTIVE" == "true" ]]; then
    echo "Warm-up artifacts:"
    echo " - ${PHASE_WARMUP_CSV_PREFIX}_stats.csv"
    echo " - ${PHASE_WARMUP_CSV_PREFIX}_stats_history.csv"
    echo " - ${PHASE_WARMUP_CSV_PREFIX}_failures.csv"
    echo " - ${PHASE_WARMUP_CSV_PREFIX}_exceptions.csv"
  fi
  echo "Measurement artifacts:"
  echo " - ${PHASE_MEASUREMENT_CSV_PREFIX}_stats.csv"
  echo " - ${PHASE_MEASUREMENT_CSV_PREFIX}_stats_history.csv"
  echo " - ${PHASE_MEASUREMENT_CSV_PREFIX}_failures.csv"
  echo " - ${PHASE_MEASUREMENT_CSV_PREFIX}_exceptions.csv"
  echo "Cluster-side artifacts (pre):"
  echo " - ${CLUSTER_CAPTURE_PRE_PREFIX}_manifest.json"
  echo " - ${CLUSTER_CAPTURE_PRE_PREFIX}_summary.txt"
  echo " - ${CLUSTER_CAPTURE_PRE_PREFIX}_nodes-wide.txt"
  echo " - ${CLUSTER_CAPTURE_PRE_PREFIX}_top-nodes.txt"
  echo " - ${CLUSTER_CAPTURE_PRE_PREFIX}_pods-wide.txt"
  echo " - ${CLUSTER_CAPTURE_PRE_PREFIX}_top-pods.txt"
  echo " - ${CLUSTER_CAPTURE_PRE_PREFIX}_services.txt"
  echo " - ${CLUSTER_CAPTURE_PRE_PREFIX}_events.txt"
  echo " - ${CLUSTER_CAPTURE_PRE_PREFIX}_pods-describe.txt"
  echo "Metric-set artifacts:"
  echo " - ${METRIC_SET_MANIFEST_PATH}"
  echo " - ${METRIC_SET_TEXT_PATH}"
  echo "Cluster-side artifacts (post):"
  echo " - ${CLUSTER_CAPTURE_POST_PREFIX}_manifest.json"
  echo " - ${CLUSTER_CAPTURE_POST_PREFIX}_summary.txt"
  echo " - ${CLUSTER_CAPTURE_POST_PREFIX}_nodes-wide.txt"
  echo " - ${CLUSTER_CAPTURE_POST_PREFIX}_top-nodes.txt"
  echo " - ${CLUSTER_CAPTURE_POST_PREFIX}_pods-wide.txt"
  echo " - ${CLUSTER_CAPTURE_POST_PREFIX}_top-pods.txt"
  echo " - ${CLUSTER_CAPTURE_POST_PREFIX}_services.txt"
  echo " - ${CLUSTER_CAPTURE_POST_PREFIX}_events.txt"
  echo " - ${CLUSTER_CAPTURE_POST_PREFIX}_pods-describe.txt"
  exit 0
else
  if [[ $MEASUREMENT_EXIT_CODE -ne 0 ]]; then
      exit $MEASUREMENT_EXIT_CODE
  fi
  echo "La cluster-side collection finale è terminata con exit code $POST_CAPTURE_EXIT_CODE." >&2
  exit $POST_CAPTURE_EXIT_CODE
fi
