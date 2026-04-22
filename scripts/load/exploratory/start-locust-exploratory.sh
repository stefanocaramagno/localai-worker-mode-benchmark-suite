#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://localhost:8080"
MODEL="llama-3.2-1b-instruct:q4_k_m"
USERS=1
SPAWN_RATE=1
RUN_TIME="1m"
CSV_PREFIX=""
LOCUST_FILE=""
TEMPERATURE="0.1"
REQUEST_TIMEOUT_SECONDS="120"
PROMPT="Reply with only READY."
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
DRY_RUN=false

print_usage() {
  cat <<'USAGE'
Usage:
  ./start-locust-exploratory.sh [options]

Options:
  --base-url URL | -BaseUrl URL
  --model NAME | -Model NAME
  --users N | -Users N
  --spawn-rate N | -SpawnRate N
  --run-time VALUE | -RunTime VALUE
  --csv-prefix PREFIX | -CsvPrefix PREFIX
  --locust-file PATH | -LocustFile PATH
  --temperature VALUE | -Temperature VALUE
  --request-timeout-seconds VALUE | -RequestTimeoutSeconds VALUE
  --prompt TEXT | -Prompt TEXT
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

resolve_repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd -- "$script_dir/../../.." && pwd
}

get_default_exploratory_csv_prefix() {
  local repository_root="$1"
  local scenario_users="$2"
  local scenario_spawn_rate="$3"
  local scenario_run_time="$4"

  if [[ "$scenario_users" == "1" && "$scenario_spawn_rate" == "1" && "$scenario_run_time" == "1m" ]]; then
    printf '%s/results/exploratory/E1_smoke_single_user/locust-smoke' "$repository_root"
    return
  fi

  if [[ "$scenario_users" == "2" && "$scenario_spawn_rate" == "1" && "$scenario_run_time" == "1m" ]]; then
    printf '%s/results/exploratory/E2_low_load_two_users/locust-low_load' "$repository_root"
    return
  fi

  if [[ "$scenario_users" == "4" && "$scenario_spawn_rate" == "2" && "$scenario_run_time" == "1m" ]]; then
    printf '%s/results/exploratory/E3_small_concurrency_four_users/locust-small_concurrency' "$repository_root"
    return
  fi

  printf '%s/results/exploratory/manual_run/locust-exploratory' "$repository_root"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url|-BaseUrl)
      BASE_URL="$2"
      shift 2
      ;;
    --model|-Model)
      MODEL="$2"
      shift 2
      ;;
    --users|-Users)
      USERS="$2"
      shift 2
      ;;
    --spawn-rate|-SpawnRate)
      SPAWN_RATE="$2"
      shift 2
      ;;
    --run-time|-RunTime)
      RUN_TIME="$2"
      shift 2
      ;;
    --csv-prefix|-CsvPrefix)
      CSV_PREFIX="$2"
      shift 2
      ;;
    --locust-file|-LocustFile)
      LOCUST_FILE="$2"
      shift 2
      ;;
    --temperature|-Temperature)
      TEMPERATURE="$2"
      shift 2
      ;;
    --request-timeout-seconds|-RequestTimeoutSeconds)
      REQUEST_TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --prompt|-Prompt)
      PROMPT="$2"
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
    --dry-run|-DryRun)
      DRY_RUN=true
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

REPO_ROOT="$(resolve_repo_root)"
source "$REPO_ROOT/scripts/load/lib/bash/run-kubernetes-apply.sh"
source "$REPO_ROOT/scripts/load/lib/bash/run-port-forward.sh"
PHASE_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-phases.sh"
PROTOCOL_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-protocol.sh"
CLUSTER_CAPTURE_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-cluster-capture.sh"
METRIC_SET_HELPER="$REPO_ROOT/scripts/load/lib/bash/run-metric-set.sh"

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

if [[ -z "$LOCUST_FILE" ]]; then
  LOCUST_FILE="$REPO_ROOT/load-tests/locust/locustfile.py"
fi

if [[ -z "$CSV_PREFIX" ]]; then
  CSV_PREFIX="$(get_default_exploratory_csv_prefix "$REPO_ROOT" "$USERS" "$SPAWN_RATE" "$RUN_TIME")"
fi

if [[ ! -f "$LOCUST_FILE" ]]; then
  echo "Il file Locust specificato non esiste: $LOCUST_FILE" >&2
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

CSV_DIRECTORY="$(dirname -- "$CSV_PREFIX")"
mkdir -p -- "$CSV_DIRECTORY"

RUN_ID="$(basename -- "$CSV_PREFIX")"
if [[ -z "$RUN_ID" ]]; then
  RUN_ID="locust-exploratory"
fi

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

if [[ -n "$MODEL" ]]; then
  PRECHECK_ARGS+=("--model" "$MODEL")
fi

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
metric_set_write_files "$METRIC_SET_MANIFEST_PATH" "$METRIC_SET_TEXT_PATH" "Start-LocustExploratory" "$RUN_ID" "$PHASE_MEASUREMENT_CSV_PREFIX" "$METRIC_SET_CLIENT_SOURCE_ARTIFACTS_JSON" "$METRIC_SET_CLUSTER_SOURCE_ARTIFACTS_JSON"

export LOCALAI_MODEL="$MODEL"
export LOCALAI_TEMPERATURE="$TEMPERATURE"
export LOCALAI_REQUEST_TIMEOUT_SECONDS="$REQUEST_TIMEOUT_SECONDS"
export LOCALAI_PROMPT="$PROMPT"

WARMUP_LOCUST_ARGS=(
  "-f" "$LOCUST_FILE"
  "--headless"
  "--host" "$BASE_URL"
  "-u" "$PHASE_WARMUP_USERS"
  "-r" "$PHASE_WARMUP_SPAWN_RATE"
  "-t" "$PHASE_WARMUP_DURATION"
  "--csv" "$PHASE_WARMUP_CSV_PREFIX"
  "--csv-full-history"
  "--only-summary"
)

MEASUREMENT_LOCUST_ARGS=(
  "-f" "$LOCUST_FILE"
  "--headless"
  "--host" "$BASE_URL"
  "-u" "$PHASE_MEASUREMENT_USERS"
  "-r" "$PHASE_MEASUREMENT_SPAWN_RATE"
  "-t" "$PHASE_MEASUREMENT_DURATION"
  "--csv" "$PHASE_MEASUREMENT_CSV_PREFIX"
  "--csv-full-history"
  "--only-summary"
)

DEPLOY_ORDER_JSON="[]"
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
protocol_write_files "$PROTOCOL_MANIFEST_PATH" "$PROTOCOL_TEXT_PATH" "Start-LocustExploratory" "$RUN_ID" \
  "Ensure the namespace is in the expected state before applying manifests and running the benchmark." "$DEPLOY_ORDER_JSON" "$([[ "$SKIP_PRECHECK" == true ]] && echo false || echo true)" "$PRECHECK_COMMAND_STR" "$PRECHECK_JSON_PROTOCOL_PATH" "$PRECHECK_TEXT_PROTOCOL_PATH" \
  "$API_SMOKE_ENABLED" "$API_SMOKE_COMMAND_STR" "$MODEL" "$PHASE_WARMUP_ENABLED_EFFECTIVE" "$WARMUP_COMMAND_STR" "$PHASE_WARMUP_CSV_PREFIX" "$MEASUREMENT_COMMAND_STR" "$PHASE_MEASUREMENT_CSV_PREFIX" "$PHASE_MANIFEST_PATH" "$EXTRA_PROTOCOL_ARTIFACTS_JSON" "$([[ "$SKIP_PRECHECK" == true ]] && echo true || echo true)" "$CLUSTER_CAPTURE_PRE_COMMAND_STR" "$CLUSTER_CAPTURE_PRE_ARTIFACTS_JSON" "true" "$CLUSTER_CAPTURE_POST_COMMAND_STR" "$CLUSTER_CAPTURE_POST_ARTIFACTS_JSON"

echo "============================================="
echo " Controlled Locust Validation - LocalAI"
echo "============================================="
echo "Repository               : $REPO_ROOT"
echo "Base URL                 : $BASE_URL"
echo "Model                    : $MODEL"
echo "Users                    : $USERS"
echo "Spawn rate               : $SPAWN_RATE"
echo "Scenario run time        : $RUN_TIME"
echo "Locust file              : $LOCUST_FILE"
echo "CSV prefix               : $CSV_PREFIX"
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
if [[ "$SKIP_PRECHECK" == true ]]; then
  echo "Pre-check                : disabled"
else
  echo "Pre-check                : $PRECHECK_CONFIG"
fi
echo
if [[ "$SKIP_PRECHECK" != true ]]; then
  echo "Comando pre-check:"
  printf %q "${PRECHECK_ARGS[0]}"
  for arg in "${PRECHECK_ARGS[@]:1}"; do
    printf " %q" "$arg"
  done
  printf "\n\n"
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
  for arg in "${WARMUP_LOCUST_ARGS[@]}"; do
    printf ' %q' "$arg"
  done
  printf '\n\n'
else
  echo "Warm-up                : disabled"
  echo
fi

echo "Comando measurement:"
printf 'locust'
for arg in "${MEASUREMENT_LOCUST_ARGS[@]}"; do
  printf ' %q' "$arg"
done
printf '\n\n'

if [[ "$DRY_RUN" == true ]]; then
  echo "DRY RUN completato. Nessun test eseguito."
  exit 0
fi

ensure_local_kubernetes_port_forward "$REPO_ROOT" "$BASE_URL" "$KUBECONFIG_PATH" "$NAMESPACE_OVERRIDE"

if [[ "$SKIP_PRECHECK" != true ]]; then
  "${PRECHECK_ARGS[@]}"
fi

if [[ "$API_SMOKE_ENABLED" == "true" ]]; then
  "${API_SMOKE_ARGS[@]}"
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
