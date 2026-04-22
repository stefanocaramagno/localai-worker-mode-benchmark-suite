#!/usr/bin/env bash
set -euo pipefail

SCENARIO=""
REPLICA=""
BASE_URL="http://localhost:8080"
MODEL="llama-3.2-1b-instruct:q4_k_m"
PROMPT="Reply with only READY."
LOCUST_FILE=""
OUTPUT_ROOT=""
SCENARIO_CONFIG_ROOT=""
BASELINE_CONFIG=""
DRY_RUN=false
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

print_usage() {
  cat <<'USAGE'
Usage:
  ./start-pilot-workload-sweep.sh --scenario WL1|WL2|WL3 --replica A|B|C [options]

Options:
  --scenario VALUE | -Scenario VALUE
  --replica VALUE | -Replica VALUE
  --base-url URL | -BaseUrl URL
  --model NAME | -Model NAME
  --prompt TEXT | -Prompt TEXT
  --locust-file PATH | -LocustFile PATH
  --output-root PATH | -OutputRoot PATH
  --scenario-config-root PATH | -ScenarioConfigRoot PATH
  --baseline-config PATH | -BaselineConfig PATH
  --dry-run | -DryRun
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

validate_scenario() {
  case "$1" in
    WL1|WL2|WL3) ;;
    *)
      echo "Scenario non supportato: $1" >&2
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

get_scenario_config() {
  local scenario_name="$1"
  local config_root="$2"
  local scenario_file="$config_root/${scenario_name}.json"

  if [[ ! -f "$scenario_file" ]]; then
    echo "Il file di configurazione dello scenario non esiste: $scenario_file" >&2
    exit 1
  fi

  local python_cmd
  python_cmd="$(require_python_command)"

  mapfile -t scenario_values < <("$python_cmd" - "$scenario_file" <<'PY'
import json
import sys
from pathlib import Path

scenario_path = Path(sys.argv[1])
required = ["scenarioId", "purpose", "users", "spawnRate", "runTime", "outputSubdir", "referenceBaselineId"]
with scenario_path.open("r", encoding="utf-8-sig") as fh:
    data = json.load(fh)
missing = [key for key in required if key not in data]
if missing:
    print(
        f"Il file di configurazione dello scenario '{scenario_path}' non contiene le proprietà obbligatorie: {', '.join(missing)}.",
        file=sys.stderr,
    )
    sys.exit(1)
print(str(scenario_path))
print(str(data["scenarioId"]))
print(str(data["purpose"]))
print(str(data["users"]))
print(str(data["spawnRate"]))
print(str(data["runTime"]))
print(str(data["outputSubdir"]))
print(str(data["referenceBaselineId"]))
PY
)

  SCENARIO_FILE="${scenario_values[0]}"
  SCENARIO_ID="${scenario_values[1]}"
  PURPOSE="${scenario_values[2]}"
  USERS="${scenario_values[3]}"
  SPAWN_RATE="${scenario_values[4]}"
  RUN_TIME="${scenario_values[5]}"
  OUTPUT_SUBDIR="${scenario_values[6]}"
  REFERENCE_BASELINE_ID="${scenario_values[7]}"
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
    print(f"Il file di configurazione dello scenario '{scenario_path}' non contiene le proprietà obbligatorie: {', '.join(missing)}.", file=sys.stderr)
    sys.exit(1)
print(str(scenario_path))
for key in required:
    print(str(data[key]))
PY
)
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario|-Scenario)
      SCENARIO="$2"
      shift 2
      ;;
    --replica|-Replica)
      REPLICA="$2"
      shift 2
      ;;
    --base-url|-BaseUrl)
      BASE_URL="$2"
      shift 2
      ;;
    --model|-Model)
      MODEL="$2"
      shift 2
      ;;
    --prompt|-Prompt)
      PROMPT="$2"
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
    --scenario-config-root|-ScenarioConfigRoot)
      SCENARIO_CONFIG_ROOT="$2"
      shift 2
      ;;
    --baseline-config|-BaselineConfig)
      BASELINE_CONFIG="$2"
      shift 2
      ;;
    --dry-run|-DryRun)
      DRY_RUN=true
      shift
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
      NAMESPACE_OVERRIDE="$2"
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

if [[ -z "$SCENARIO" ]]; then
  echo "Il parametro Scenario è obbligatorio." >&2
  print_usage >&2
  exit 1
fi

if [[ -z "$REPLICA" ]]; then
  echo "Il parametro Replica è obbligatorio." >&2
  print_usage >&2
  exit 1
fi

validate_scenario "$SCENARIO"
validate_replica "$REPLICA"

REPO_ROOT="$(resolve_repo_root)"
source "$REPO_ROOT/scripts/load/lib/bash/run-kubernetes-apply.sh"
source "$REPO_ROOT/scripts/load/lib/bash/run-port-forward.sh"
PHASE_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-phases.sh"
PROTOCOL_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-protocol.sh"
CLUSTER_CAPTURE_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-cluster-capture.sh"
METRIC_SET_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-metric-set.sh"

if [[ -z "$LOCUST_FILE" ]]; then
  LOCUST_FILE="$REPO_ROOT/load-tests/locust/locustfile.py"
fi

if [[ -z "$OUTPUT_ROOT" ]]; then
  OUTPUT_ROOT="$REPO_ROOT/results/pilot/workload"
fi

if [[ -z "$SCENARIO_CONFIG_ROOT" ]]; then
  SCENARIO_CONFIG_ROOT="$REPO_ROOT/config/scenarios/pilot/workload"
fi

if [[ -z "$BASELINE_CONFIG" ]]; then
  BASELINE_CONFIG="$REPO_ROOT/config/scenarios/baseline/B0.json"
fi

if [[ -z "$PRECHECK_CONFIG" ]]; then
  PRECHECK_CONFIG="$REPO_ROOT/config/precheck/TC1.json"
fi

if [[ -z "$PHASE_CONFIG" ]]; then
  PHASE_CONFIG="$REPO_ROOT/config/phases/WM1.json"
fi

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

if [[ ! -f "$LOCUST_FILE" ]]; then
  echo "Il file Locust specificato non esiste: $LOCUST_FILE" >&2
  exit 1
fi

if [[ ! -f "$BASELINE_CONFIG" ]]; then
  echo "Il file di baseline non esiste: $BASELINE_CONFIG" >&2
  exit 1
fi

if [[ "$SKIP_PRECHECK" != true && ! -f "$PRECHECK_SCRIPT" ]]; then
  echo "Lo script di pre-check non esiste: $PRECHECK_SCRIPT" >&2
  exit 1
fi

if [[ ! -f "$PHASE_HELPER" ]]; then
  echo "Lo script helper delle fasi non esiste: $PHASE_HELPER" >&2
  exit 1
fi

if [[ ! -f "$PHASE_CONFIG" ]]; then
  echo "Il file di profilo warm-up/misurazione non esiste: $PHASE_CONFIG" >&2
  exit 1
fi

if [[ ! -f "$PROTOCOL_HELPER" ]]; then
  echo "Lo script helper del protocollo non esiste: $PROTOCOL_HELPER" >&2
  exit 1
fi

if [[ ! -f "$CLUSTER_CAPTURE_HELPER" ]]; then
  echo "Lo script helper della cluster-side collection non esiste: $CLUSTER_CAPTURE_HELPER" >&2
  exit 1
fi

if [[ ! -f "$METRIC_SET_HELPER" ]]; then
  echo "Lo script helper del metric set non esiste: $METRIC_SET_HELPER" >&2
  exit 1
fi

if [[ ! -f "$METRIC_SET_CONFIG" ]]; then
  echo "Il file di metric set non esiste: $METRIC_SET_CONFIG" >&2
  exit 1
fi

if [[ ! -f "$PROTOCOL_CONFIG" ]]; then
  echo "Il file di protocollo non esiste: $PROTOCOL_CONFIG" >&2
  exit 1
fi

if [[ ! -f "$CLUSTER_CAPTURE_CONFIG" ]]; then
  echo "Il file di cluster-side collection non esiste: $CLUSTER_CAPTURE_CONFIG" >&2
  exit 1
fi

if [[ ! -f "$CLUSTER_CAPTURE_SCRIPT" ]]; then
  echo "Lo script di cluster-side collection non esiste: $CLUSTER_CAPTURE_SCRIPT" >&2
  exit 1
fi

if [[ "$DRY_RUN" != true ]]; then
  require_command locust
fi
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

get_scenario_config "$SCENARIO" "$SCENARIO_CONFIG_ROOT"
get_json_properties "$BASELINE_CONFIG" "baselineId,purpose,modelScenario,resolvedModelName,workerScenario,resolvedWorkerCount,placementScenario,resolvedPlacementType,topologyDir,serverManifest,namespaceManifest,storageManifest,prompt,temperature,requestTimeoutSeconds"
BASELINE_CONFIG_FILE_RESOLVED="${JSON_VALUES[0]}"
BASELINE_ID="${JSON_VALUES[1]}"
BASELINE_PURPOSE="${JSON_VALUES[2]}"
BASELINE_MODEL_SCENARIO="${JSON_VALUES[3]}"
BASELINE_MODEL_NAME="${JSON_VALUES[4]}"
BASELINE_WORKER_SCENARIO="${JSON_VALUES[5]}"
BASELINE_WORKER_COUNT="${JSON_VALUES[6]}"
BASELINE_PLACEMENT_SCENARIO="${JSON_VALUES[7]}"
BASELINE_PLACEMENT_TYPE="${JSON_VALUES[8]}"
BASELINE_TOPOLOGY_DIR_REL="${JSON_VALUES[9]}"
BASELINE_SERVER_MANIFEST_REL="${JSON_VALUES[10]}"
BASELINE_NAMESPACE_MANIFEST_REL="${JSON_VALUES[11]}"
BASELINE_STORAGE_MANIFEST_REL="${JSON_VALUES[12]}"
BASELINE_PROMPT="${JSON_VALUES[13]}"
BASELINE_TEMPERATURE="${JSON_VALUES[14]}"
BASELINE_REQUEST_TIMEOUT_SECONDS="${JSON_VALUES[15]}"

if [[ "$REFERENCE_BASELINE_ID" != "$BASELINE_ID" ]]; then
  echo "Lo scenario workload $SCENARIO richiede la baseline $REFERENCE_BASELINE_ID ma il file fornito espone $BASELINE_ID." >&2
  exit 1
fi

MODEL_SCENARIO_FILE="$REPO_ROOT/config/scenarios/pilot/models/${BASELINE_MODEL_SCENARIO}.json"
WORKER_SCENARIO_FILE="$REPO_ROOT/config/scenarios/pilot/worker-count/${BASELINE_WORKER_SCENARIO}.json"
PLACEMENT_SCENARIO_FILE="$REPO_ROOT/config/scenarios/pilot/placement/${BASELINE_PLACEMENT_SCENARIO}.json"

get_json_properties "$MODEL_SCENARIO_FILE" "scenarioId,modelName,serverManifest"
if [[ "${JSON_VALUES[1]}" != "$BASELINE_MODEL_SCENARIO" || "${JSON_VALUES[2]}" != "$BASELINE_MODEL_NAME" || "${JSON_VALUES[3]}" != "$BASELINE_SERVER_MANIFEST_REL" ]]; then
  echo "La baseline workload non è coerente con lo scenario model di riferimento." >&2
  exit 1
fi

get_json_properties "$WORKER_SCENARIO_FILE" "scenarioId,workerCount"
if [[ "${JSON_VALUES[1]}" != "$BASELINE_WORKER_SCENARIO" || "${JSON_VALUES[2]}" != "$BASELINE_WORKER_COUNT" ]]; then
  echo "La baseline workload non è coerente con lo scenario worker di riferimento." >&2
  exit 1
fi

get_json_properties "$PLACEMENT_SCENARIO_FILE" "scenarioId,placementType,topologyDir"
if [[ "${JSON_VALUES[1]}" != "$BASELINE_PLACEMENT_SCENARIO" || "${JSON_VALUES[2]}" != "$BASELINE_PLACEMENT_TYPE" || "${JSON_VALUES[3]}" != "$BASELINE_TOPOLOGY_DIR_REL" ]]; then
  echo "La baseline workload non è coerente con lo scenario placement di riferimento." >&2
  exit 1
fi

if [[ -n "$MODEL" && "$MODEL" != "$BASELINE_MODEL_NAME" ]]; then
  echo "Il workload sweep è ancorato alla baseline $BASELINE_ID. Il modello richiesto ($MODEL) non coincide con il modello fisso di baseline ($BASELINE_MODEL_NAME)." >&2
  exit 1
fi
MODEL="$BASELINE_MODEL_NAME"

if [[ -n "$PROMPT" && "$PROMPT" != "$BASELINE_PROMPT" ]]; then
  echo "Il workload sweep è ancorato alla baseline $BASELINE_ID. Il prompt richiesto non coincide con il prompt fisso di baseline." >&2
  exit 1
fi
PROMPT="$BASELINE_PROMPT"

TOPOLOGY_ROOT="$REPO_ROOT/$BASELINE_TOPOLOGY_DIR_REL"
SERVER_MANIFEST="$REPO_ROOT/$BASELINE_SERVER_MANIFEST_REL"
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
  "--model" "$MODEL"
)

if [[ -n "$KUBECONFIG_PATH" ]]; then
  PRECHECK_ARGS+=("--kubeconfig" "$KUBECONFIG_PATH")
fi

if [[ -n "$NAMESPACE_OVERRIDE" ]]; then
  PRECHECK_ARGS+=("--namespace" "$NAMESPACE_OVERRIDE")
fi

API_SMOKE_ARGS=(
  "$API_SMOKE_SCRIPT"
  "--base-url" "$BASE_URL"
  "--model" "$MODEL"
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

if [[ -n "${NAMESPACE_OVERRIDE:-}" ]]; then
  CLUSTER_CAPTURE_PRE_ARGS+=("--namespace" "${NAMESPACE_OVERRIDE}")
  CLUSTER_CAPTURE_POST_ARGS+=("--namespace" "${NAMESPACE_OVERRIDE}")
fi

CLUSTER_CAPTURE_PRE_COMMAND_STR="$(protocol_quote_command "${CLUSTER_CAPTURE_PRE_ARGS[@]}")"
CLUSTER_CAPTURE_POST_COMMAND_STR="$(protocol_quote_command "${CLUSTER_CAPTURE_POST_ARGS[@]}")"
CLUSTER_CAPTURE_PRE_ARTIFACTS_JSON="$(cluster_artifacts_json "$CLUSTER_CAPTURE_PRE_PREFIX")"
CLUSTER_CAPTURE_POST_ARTIFACTS_JSON="$(cluster_artifacts_json "$CLUSTER_CAPTURE_POST_PREFIX")"

metric_set_resolve_paths "$PHASE_MEASUREMENT_CSV_PREFIX"
METRIC_SET_CLIENT_SOURCE_ARTIFACTS_JSON="$(metric_set_client_artifacts_json "$PHASE_MEASUREMENT_CSV_PREFIX")"
METRIC_SET_CLUSTER_SOURCE_ARTIFACTS_JSON="$(metric_set_cluster_artifacts_json "$CLUSTER_CAPTURE_PRE_PREFIX" "$CLUSTER_CAPTURE_POST_PREFIX")"
metric_set_write_files "$METRIC_SET_MANIFEST_PATH" "$METRIC_SET_TEXT_PATH" "Start-PilotWorkloadSweep" "$RUN_ID" "$PHASE_MEASUREMENT_CSV_PREFIX" "$METRIC_SET_CLIENT_SOURCE_ARTIFACTS_JSON" "$METRIC_SET_CLUSTER_SOURCE_ARTIFACTS_JSON"

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
protocol_write_files "$PROTOCOL_MANIFEST_PATH" "$PROTOCOL_TEXT_PATH" "Start-PilotWorkloadSweep" "$RUN_ID" \
  "Ensure the namespace is in the expected state before applying manifests and running the benchmark." "$DEPLOY_ORDER_JSON" "$([[ "$SKIP_PRECHECK" == true ]] && echo false || echo true)" "$PRECHECK_COMMAND_STR" "$PRECHECK_JSON_PROTOCOL_PATH" "$PRECHECK_TEXT_PROTOCOL_PATH" \
  "$API_SMOKE_ENABLED" "$API_SMOKE_COMMAND_STR" "$MODEL" "$PHASE_WARMUP_ENABLED_EFFECTIVE" "$WARMUP_COMMAND_STR" "$PHASE_WARMUP_CSV_PREFIX" "$MEASUREMENT_COMMAND_STR" "$PHASE_MEASUREMENT_CSV_PREFIX" "$PHASE_MANIFEST_PATH" "$EXTRA_PROTOCOL_ARTIFACTS_JSON" "true" "$CLUSTER_CAPTURE_PRE_COMMAND_STR" "$CLUSTER_CAPTURE_PRE_ARTIFACTS_JSON" "true" "$CLUSTER_CAPTURE_POST_COMMAND_STR" "$CLUSTER_CAPTURE_POST_ARTIFACTS_JSON"

echo "============================================="
echo " Official Pilot Workload Sweep Launcher"
echo "============================================="
echo "Repository                   : $REPO_ROOT"
echo "Scenario                     : $SCENARIO"
echo "Replica                      : $REPLICA"
echo "Run ID                       : $RUN_ID"
echo "Purpose                      : $PURPOSE"
echo "Reference baseline           : $BASELINE_ID"
echo "Baseline config              : $BASELINE_CONFIG_FILE_RESOLVED"
echo "Baseline purpose             : $BASELINE_PURPOSE"
echo "Fixed model scenario         : $BASELINE_MODEL_SCENARIO"
echo "Fixed model                  : $MODEL"
echo "Fixed worker-count scenario  : $BASELINE_WORKER_SCENARIO"
echo "Fixed placement              : $BASELINE_PLACEMENT_SCENARIO ($BASELINE_PLACEMENT_TYPE)"
echo "Topology target              : $TOPOLOGY_ROOT"
echo "Server target                : $SERVER_MANIFEST"
echo "Scenario cfg                 : $SCENARIO_FILE"
echo "Scenario users               : $USERS"
echo "Scenario spawn rate          : $SPAWN_RATE"
echo "Scenario run time            : $RUN_TIME"
echo "Base URL                     : $BASE_URL"
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
  echo "$WARMUP_COMMAND_STR"
  echo
else
  echo "Warm-up                : disabled"
  echo
fi
echo "Comando measurement:"
echo "$MEASUREMENT_COMMAND_STR"
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
  "${API_SMOKE_ARGS[@]}"
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
  cluster_print_artifacts "$CLUSTER_CAPTURE_PRE_PREFIX"
  echo "Metric-set artifacts:"
  echo " - $METRIC_SET_MANIFEST_PATH"
  echo " - $METRIC_SET_TEXT_PATH"
  echo "Cluster-side artifacts (post):"
  cluster_print_artifacts "$CLUSTER_CAPTURE_POST_PREFIX"
  exit 0
else
  if [[ $EXIT_CODE -ne 0 ]]; then
    echo "La run Locust è terminata con exit code $EXIT_CODE."
    exit $EXIT_CODE
  fi
  echo "La cluster-side collection finale è terminata con exit code $CLUSTER_CAPTURE_POST_EXIT_CODE."
  exit $CLUSTER_CAPTURE_POST_EXIT_CODE
fi
