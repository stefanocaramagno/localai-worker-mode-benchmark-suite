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

BASELINE_CONFIG=""
REPLICA=""
BASE_URL=""
LOCUST_FILE=""
OUTPUT_ROOT=""
PRECHECK_CONFIG=""
KUBECONFIG_PATH=""
NAMESPACE=""
ADDITIONAL_NAMESPACES_OVERRIDE=""
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
  --benchmark-config PATH | -BenchmarkConfig PATH
  --baseline-config PATH | -BaselineConfig PATH    (legacy alias)
  --base-url URL | -BaseUrl URL
  --locust-file PATH | -LocustFile PATH
  --output-root PATH | -OutputRoot PATH
  --precheck-config PATH | -PrecheckConfig PATH
  --kubeconfig PATH | -Kubeconfig PATH
  --namespace NAME | -Namespace NAME
  --additional-namespaces LIST | -AdditionalNamespaces LIST
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
    echo "Error: required command is not available in PATH: $cmd" >&2
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
  echo "Error: unable to find python3 or python in PATH." >&2
  exit 1
}

resolve_repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd -- "$script_dir/../../.." && pwd
}


repo_portable_string() {
  local value="$1"
  local repo_root="${2:-$REPO_ROOT}"
  if [[ -z "$value" ]]; then
    printf '%s' "$value"
    return 0
  fi
  local root_backslash root_forward result
  root_backslash="${repo_root%/}"
  root_forward="${root_backslash//\\//}"
  result="$value"
  result="${result//$root_backslash/.}"
  result="${result//$root_forward/.}"
  printf '%s' "$result"
}

validate_replica() {
  case "$1" in
    A|B|C) ;;
    *)
      echo "Unsupported replica: $1" >&2
      exit 1
      ;;
  esac
}

load_json_file() {
  local json_file="$1"
  local required_keys_csv="$2"
  local python_cmd
  local json_output
  local required_count
  python_cmd="$(require_python_command)"

  if ! json_output="$($python_cmd - "$json_file" "$required_keys_csv" <<'PY'
import json
import sys
from pathlib import Path

json_path = Path(sys.argv[1])
required = [key for key in sys.argv[2].split(',') if key]
try:
    with json_path.open('r', encoding='utf-8-sig') as fh:
        data = json.load(fh)
except Exception as exc:
    print(f"Unable to read JSON file '{json_path}': {exc}", file=sys.stderr)
    sys.exit(1)
missing = [key for key in required if key not in data]
if missing:
    print(f"The JSON file '{json_path}' does not contain the required properties: {', '.join(missing)}.", file=sys.stderr)
    sys.exit(1)
print(str(json_path))
for key in required:
    value = data[key]
    if isinstance(value, (dict, list)):
      print(json.dumps(value, separators=(',', ':')))
    else:
      print(str(value))
PY
)"; then
    echo "Error: failed to load or validate JSON file: $json_file" >&2
    exit 1
  fi

  mapfile -t JSON_VALUES <<< "$json_output"
  required_count="$($(require_python_command) - "$required_keys_csv" <<'PY'
import sys
print(len([key for key in sys.argv[1].split(',') if key]) + 1)
PY
)"
  if (( ${#JSON_VALUES[@]} < required_count )); then
    echo "Error: JSON loader returned incomplete data for file: $json_file" >&2
    exit 1
  fi
}

print_artifact_list_from_json() {
  local artifacts_json="$1"
  local python_cmd
  python_cmd="$(require_python_command)"

  "$python_cmd" - "$artifacts_json" <<'PY'
import json
import sys
try:
    artifacts = json.loads(sys.argv[1])
except Exception:
    artifacts = []
for artifact in artifacts:
    print(f" - {artifact}")
PY
}

resolve_benchmark_namespaces() {
  local scenario_file="$1"
  local namespace_override="$2"
  local additional_override="$3"
  local python_cmd
  python_cmd="$(require_python_command)"

  mapfile -t BENCHMARK_NAMESPACE_VALUES < <("$python_cmd" - "$scenario_file" "$namespace_override" "$additional_override" <<'PY'
import json
import sys
from pathlib import Path

scenario_path = Path(sys.argv[1])
namespace_override = sys.argv[2].strip()
additional_override = sys.argv[3]
with scenario_path.open("r", encoding="utf-8-sig") as fh:
    payload = json.load(fh)

def add(target, value):
    if value is None:
        return
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, list):
        values = value
    else:
        values = [value]
    for item in values:
        text = str(item).strip()
        if text and text not in target:
            target.append(text)

namespaces = []
if namespace_override:
    add(namespaces, namespace_override)
elif payload.get("namespace"):
    add(namespaces, payload.get("namespace"))
elif isinstance(payload.get("applicationTopology"), dict) and payload["applicationTopology"].get("namespace"):
    add(namespaces, payload["applicationTopology"].get("namespace"))
elif isinstance(payload.get("tenancyVariant"), dict) and payload["tenancyVariant"].get("benchmarkNamespace"):
    add(namespaces, payload["tenancyVariant"].get("benchmarkNamespace"))
else:
    add(namespaces, "localai-benchmark")

add(namespaces, additional_override)
add(namespaces, payload.get("additionalNamespaces"))

for cluster in payload.get("tenantClusters") or []:
    if isinstance(cluster, dict):
        add(namespaces, cluster.get("namespace"))

topology = payload.get("applicationTopology") if isinstance(payload.get("applicationTopology"), dict) else {}
add(namespaces, topology.get("additionalNamespaces"))
for target in topology.get("additionalRolloutTargets") or []:
    if isinstance(target, dict):
        add(namespaces, target.get("namespace"))

primary = namespaces[0]
additional = [namespace for namespace in namespaces if namespace != primary]
print(primary)
print(",".join(additional))
print(json.dumps(namespaces, separators=(",", ":")))
PY
)

  NAMESPACE="${BENCHMARK_NAMESPACE_VALUES[0]}"
  ADDITIONAL_NAMESPACES_EFFECTIVE="${BENCHMARK_NAMESPACE_VALUES[1]}"
  BENCHMARK_NAMESPACES_JSON="${BENCHMARK_NAMESPACE_VALUES[2]}"
}

validate_measurement_target_requests() {
  local stats_csv_path="$1"
  local target_type="${2:-POST}"
  local target_name="${3:-POST /v1/chat/completions}"
  local python_cmd
  python_cmd="$(require_python_command)"
  "$python_cmd" - "$stats_csv_path" "$target_type" "$target_name" <<'PY'
import csv
import json
import sys
from pathlib import Path

stats_path = Path(sys.argv[1])
target_type = sys.argv[2]
target_name = sys.argv[3]
result = {
    "valid": False,
    "reason": "measurement_stats_csv_missing",
    "statsCsvPath": str(stats_path),
    "targetType": target_type,
    "targetName": target_name,
    "targetRequestCount": 0,
    "aggregatedRequestCount": 0,
}

def to_number(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None

if stats_path.exists():
    with stats_path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    target_row = None
    aggregated_row = None
    for row in rows:
        row_type = (row.get("Type") or "").strip()
        row_name = (row.get("Name") or "").strip()
        if row_name == "Aggregated":
            aggregated_row = row
        if row_type == target_type and row_name == target_name:
            target_row = row
    if aggregated_row is not None:
        aggregated_count = to_number(aggregated_row.get("Request Count"))
        if aggregated_count is not None:
            result["aggregatedRequestCount"] = int(round(aggregated_count))
    if target_row is None:
        result["reason"] = "measurement_missing_target_request_row"
    else:
        target_count = to_number(target_row.get("Request Count"))
        if target_count is None or target_count <= 0:
            result["reason"] = "measurement_produced_zero_valid_requests"
        else:
            result["valid"] = True
            result["reason"] = "measurement_contains_valid_target_requests"
            result["targetRequestCount"] = int(round(target_count))
print(json.dumps(result, separators=(",", ":")))
PY
}

write_measurement_unsupported_evidence() {
  local output_path="$1"
  local reason="$2"
  local validation_json="$3"
  local python_cmd
  python_cmd="$(require_python_command)"
  "$python_cmd" - "$BASELINE_FILE_RESOLVED" "$REPLICA" "$reason" "$validation_json" "$output_path" "$API_SMOKE_UNSUPPORTED_EXIT_CODE" <<'PY'
import json
import sys
from pathlib import Path

baseline_path = Path(sys.argv[1])
replica = sys.argv[2]
reason = sys.argv[3]
validation = json.loads(sys.argv[4])
output_path = Path(sys.argv[5])
unsupported_exit_code = int(sys.argv[6])
with baseline_path.open("r", encoding="utf-8-sig") as fh:
    baseline = json.load(fh)
latency_variant = baseline.get("latencyVariant") if isinstance(baseline.get("latencyVariant"), dict) else {}
scenario_family = baseline.get("family") or "provider-backed"
scenario_family_evidence_kind = str(scenario_family).replace("-", "_")
payload = {
    "family": scenario_family,
    "scenario": baseline.get("baselineId"),
    "scenarioId": baseline.get("baselineId"),
    "replica": replica,
    "status": "unsupported_under_current_constraints",
    "namespace": baseline.get("namespace"),
    "placementType": baseline.get("resolvedPlacementType"),
    "expectedWorkerCount": baseline.get("resolvedWorkerCount"),
    "reason": reason,
    "stage": "measurement_validation",
    "evidence": {
        "classificationRule": "locust_measurement_finished_without_valid_target_requests",
        "failureClass": "measurement_produced_no_valid_target_requests",
        "statsCsvPath": validation.get("statsCsvPath"),
        "targetType": validation.get("targetType"),
        "targetName": validation.get("targetName"),
        "targetRequestCount": validation.get("targetRequestCount", 0),
        "aggregatedRequestCount": validation.get("aggregatedRequestCount", 0),
        "locustExitCode": 0,
        "unsupportedExitCode": unsupported_exit_code,
    },
    "evidenceKinds": ["measurement_validation", reason, "no_valid_target_requests", scenario_family_evidence_kind],
    "schedulerEvidence": {},
    "diagnostics": [],
    "latencyVariant": latency_variant,
    "latencyProfileId": baseline.get("latencyProfileId") or latency_variant.get("latencyProfileId"),
    "timeoutSeconds": baseline.get("requestTimeoutSeconds"),
    "model": baseline.get("resolvedModelName"),
}
output_path.parent.mkdir(parents=True, exist_ok=True)
with output_path.open("w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
PY
  normalize_artifact_file "$output_path"
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
    echo "Invalid or unresolved Kubernetes target: $target" >&2
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
    *) echo "Invalid or unresolved Kubernetes target: $target" >&2; exit 1 ;;
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
    "$PHASE_WARMUP_DURATION" "$PHASE_MEASUREMENT_DURATION" "$REPO_ROOT" <<'PY'
import json
import re
import sys
from pathlib import Path

output_path = Path(sys.argv[1])
repo_root = Path(sys.argv[23]).resolve()

def repo_relative(value):
    if value is None:
        return value
    text = str(value)
    if not text.strip():
        return text
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s\"'<>|{}]+", text.strip()):
        return text
    normalized = text.replace("\\", "/")
    root = str(repo_root).replace("\\", "/").rstrip("/")
    if root:
        normalized = re.sub(re.escape(root), ".", normalized, flags=re.IGNORECASE)
    marker = "/localai-worker-mode-benchmark-suite/"
    marker_index = normalized.lower().find(marker)
    if marker_index >= 0:
        normalized = normalized[marker_index + len(marker):]
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized

payload = {
    "baselineConfig": repo_relative(sys.argv[2]),
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
        "topologyDir": repo_relative(sys.argv[14]),
        "serverManifest": repo_relative(sys.argv[15]),
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
  normalize_artifact_file "$output_path"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --replica|-Replica)
      REPLICA="$2"
      shift 2
      ;;
    --benchmark-config|-BenchmarkConfig|--baseline-config|-BaselineConfig)
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
    --additional-namespaces|-AdditionalNamespaces)
      ADDITIONAL_NAMESPACES_OVERRIDE="$2"
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
      echo "Unrecognized argument: $1" >&2
      print_usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$REPLICA" ]]; then
  echo "The Replica parameter is required." >&2
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
PRECHECK_CONFIG_PROVIDED=false
if [[ -n "$PRECHECK_CONFIG" ]]; then
  PRECHECK_CONFIG_PROVIDED=true
fi
[[ -n "$PHASE_CONFIG" ]] || PHASE_CONFIG="$REPO_ROOT/config/phases/profiles/WM_STANDARD_WARMUP_MEASUREMENT.json"
if [[ -z "$PROTOCOL_CONFIG" ]]; then
  PROTOCOL_CONFIG="$REPO_ROOT/config/protocol/profiles/EP_STANDARD_BENCHMARK_PROTOCOL.json"
fi

if [[ -z "$CLUSTER_CAPTURE_CONFIG" ]]; then
  CLUSTER_CAPTURE_CONFIG="$REPO_ROOT/config/cluster-capture/profiles/CS_STANDARD_CLUSTER_CAPTURE.json"
fi

if [[ -z "$METRIC_SET_CONFIG" ]]; then
  METRIC_SET_CONFIG="$REPO_ROOT/config/metric-set/profiles/MS_STANDARD_BENCHMARK_METRICS.json"
fi

PRECHECK_SCRIPT="$REPO_ROOT/scripts/validation/precheck/invoke-benchmark-precheck.sh"
CLUSTER_CAPTURE_SCRIPT="$REPO_ROOT/scripts/validation/cluster-side/collect-cluster-side-artifacts.sh"

[[ -f "$BASELINE_CONFIG" ]] || { echo "The benchmark configuration file does not exist: $BASELINE_CONFIG" >&2; exit 1; }
[[ -f "$LOCUST_FILE" ]] || { echo "The specified Locust file does not exist: $LOCUST_FILE" >&2; exit 1; }
if [[ "$SKIP_PRECHECK" != true && ! -f "$PRECHECK_SCRIPT" ]]; then echo "The pre-check script does not exist: $PRECHECK_SCRIPT" >&2; exit 1; fi
if [[ ! -f "$PHASE_HELPER" ]]; then echo "The phase helper script does not exist: $PHASE_HELPER" >&2; exit 1; fi
if [[ ! -f "$PHASE_CONFIG" ]]; then echo "The warm-up/measurement profile file does not exist: $PHASE_CONFIG" >&2; exit 1; fi
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
  echo "The API smoke script does not exist: $API_SMOKE_SCRIPT" >&2
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
resolve_benchmark_namespaces "$BASELINE_FILE_RESOLVED" "$NAMESPACE" "$ADDITIONAL_NAMESPACES_OVERRIDE"
BASELINE_PROVIDER_BOUND="$($(require_python_command) - "$BASELINE_FILE_RESOLVED" <<'PY_PROVIDER_BOUND'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
print('true' if payload.get('providerBindingId') or payload.get('infrastructureProfileId') else 'false')
PY_PROVIDER_BOUND
)"

mapfile -t BASELINE_EXECUTION_POLICY < <("$(require_python_command)" - "$BASELINE_FILE_RESOLVED" <<'PY_EXECUTION_POLICY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
latency_variant = payload.get('latencyVariant') if isinstance(payload.get('latencyVariant'), dict) else {}
print(str(payload.get('family') or ''))
print('true' if latency_variant.get('enabled') is True else 'false')
PY_EXECUTION_POLICY
)
SCENARIO_FAMILY="${BASELINE_EXECUTION_POLICY[0]:-}"
LATENCY_VARIANT_ENABLED="${BASELINE_EXECUTION_POLICY[1]:-false}"
API_SMOKE_UNSUPPORTED_EXIT_CODE=42
API_SMOKE_TIMEOUT_AS_UNSUPPORTED=false
if [[ "$SCENARIO_FAMILY" == "latency-injection" && "$LATENCY_VARIANT_ENABLED" == "true" ]]; then
  API_SMOKE_TIMEOUT_AS_UNSUPPORTED=true
fi

if [[ "$PRECHECK_CONFIG_PROVIDED" != true ]]; then
  BASELINE_PRECHECK_PYTHON_CMD="$(require_python_command)"
  BASELINE_PRECHECK_REL="$("$BASELINE_PRECHECK_PYTHON_CMD" - "$BASELINE_FILE_RESOLVED" <<'PY_BASELINE_PRECHECK'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
for key in ("precheckProfilePath", "precheckConfigPath", "precheckConfig"):
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        print(value.strip())
        break
PY_BASELINE_PRECHECK
)"
  if [[ -n "$BASELINE_PRECHECK_REL" ]]; then
    case "$BASELINE_PRECHECK_REL" in
      /*|[A-Za-z]:/*|[A-Za-z]:\\*) PRECHECK_CONFIG="$BASELINE_PRECHECK_REL" ;;
      *) PRECHECK_CONFIG="$REPO_ROOT/$BASELINE_PRECHECK_REL" ;;
    esac
  else
    PRECHECK_CONFIG="$REPO_ROOT/config/precheck/profiles/TC_C0_HISTORICAL_FIXED_CLUSTER.json"
  fi
fi

[[ -n "$BASE_URL" ]] || BASE_URL="$BASELINE_BASE_URL"
[[ -n "$OUTPUT_ROOT" ]] || OUTPUT_ROOT="$REPO_ROOT/$RESULTS_ROOT_REL"

MODEL_SCENARIO_FILE="$REPO_ROOT/config/scenarios/pilot/models/${MODEL_SCENARIO}.json"
WORKER_SCENARIO_FILE="$REPO_ROOT/config/scenarios/pilot/worker-count/${WORKER_SCENARIO}.json"
PLACEMENT_SCENARIO_FILE="$REPO_ROOT/config/scenarios/pilot/placement/${PLACEMENT_SCENARIO}.json"
if [[ "$BASELINE_PROVIDER_BOUND" == "true" ]]; then
  BASELINE_PLACEMENT_REL="$($(require_python_command) - "$BASELINE_FILE_RESOLVED" <<'PY_BASELINE_PLACEMENT'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
for key in ("placementScenarioPath", "placementProfilePath"):
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        print(value.strip())
        break
PY_BASELINE_PLACEMENT
)"
  if [[ -n "$BASELINE_PLACEMENT_REL" ]]; then
    case "$BASELINE_PLACEMENT_REL" in
      /*|[A-Za-z]:/*|[A-Za-z]:\\*) PLACEMENT_SCENARIO_FILE="$BASELINE_PLACEMENT_REL" ;;
      *) PLACEMENT_SCENARIO_FILE="$REPO_ROOT/$BASELINE_PLACEMENT_REL" ;;
    esac
  fi
fi
WORKLOAD_SCENARIO_FILE="$REPO_ROOT/config/scenarios/pilot/workload/${WORKLOAD_SCENARIO}.json"
for file in "$MODEL_SCENARIO_FILE" "$WORKER_SCENARIO_FILE" "$PLACEMENT_SCENARIO_FILE" "$WORKLOAD_SCENARIO_FILE"; do [[ -f "$file" ]] || { echo "Required scenario file not found: $file" >&2; exit 1; }; done

load_json_file "$MODEL_SCENARIO_FILE" "scenarioId,modelName,serverManifest"
[[ "${JSON_VALUES[1]}" == "$MODEL_SCENARIO" ]] || { echo "Baseline/model scenarioId mismatch." >&2; exit 1; }
[[ "${JSON_VALUES[2]}" == "$MODEL_NAME" ]] || { echo "Baseline/modelName mismatch." >&2; exit 1; }
if [[ "${JSON_VALUES[3]}" != "$SERVER_MANIFEST_REL" && "$BASELINE_PROVIDER_BOUND" != "true" ]]; then
  echo "Baseline/serverManifest mismatch." >&2
  exit 1
fi

load_json_file "$WORKER_SCENARIO_FILE" "scenarioId,workerCount"
[[ "${JSON_VALUES[1]}" == "$WORKER_SCENARIO" ]] || { echo "Baseline/worker scenarioId mismatch." >&2; exit 1; }
[[ "${JSON_VALUES[2]}" == "$WORKER_COUNT" ]] || { echo "Baseline/workerCount mismatch." >&2; exit 1; }

if [[ "$BASELINE_PROVIDER_BOUND" == "true" ]]; then
  PLACEMENT_IDENTIFIER="$($(require_python_command) - "$PLACEMENT_SCENARIO_FILE" <<'PY_PLACEMENT_IDENTIFIER'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
for key in ("scenarioId", "placementProfileId", "profileId"):
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        print(value.strip())
        break
PY_PLACEMENT_IDENTIFIER
)"
  BASELINE_PLACEMENT_PROFILE_ID="$($(require_python_command) - "$BASELINE_FILE_RESOLVED" <<'PY_BASELINE_PLACEMENT_ID'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
value = payload.get("placementProfileId")
print(value.strip() if isinstance(value, str) else "")
PY_BASELINE_PLACEMENT_ID
)"
  if [[ -z "$PLACEMENT_IDENTIFIER" ]]; then
    echo "The placement file does not contain scenarioId, placementProfileId, or profileId: $PLACEMENT_SCENARIO_FILE" >&2
    exit 1
  fi
  if [[ "$PLACEMENT_IDENTIFIER" != "$PLACEMENT_SCENARIO" && -n "$BASELINE_PLACEMENT_PROFILE_ID" && "$PLACEMENT_IDENTIFIER" != "$BASELINE_PLACEMENT_PROFILE_ID" ]]; then
    echo "Baseline/placement mismatch: $PLACEMENT_IDENTIFIER does not match $PLACEMENT_SCENARIO." >&2
    exit 1
  fi
else
  load_json_file "$PLACEMENT_SCENARIO_FILE" "scenarioId,placementType,topologyDir"
  [[ "${JSON_VALUES[1]}" == "$PLACEMENT_SCENARIO" ]] || { echo "Baseline/placement scenarioId mismatch." >&2; exit 1; }
  if [[ "${JSON_VALUES[2]}" != "$PLACEMENT_TYPE" ]]; then
    echo "Baseline/placementType mismatch." >&2
    exit 1
  fi
  if [[ "${JSON_VALUES[3]}" != "$TOPOLOGY_DIR_REL" ]]; then
    echo "Baseline/topologyDir mismatch." >&2
    exit 1
  fi
fi

load_json_file "$WORKLOAD_SCENARIO_FILE" "scenarioId,users,spawnRate,runTime"
[[ "${JSON_VALUES[1]}" == "$WORKLOAD_SCENARIO" ]] || { echo "Baseline/workload scenarioId mismatch." >&2; exit 1; }
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
OUTPUT_SUBDIR="$($(require_python_command) - "$BASELINE_FILE_RESOLVED" "$BASELINE_ID" <<'PY_OUTPUT_SUBDIR'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
baseline_id = sys.argv[2]
for key in ("outputSubdir", "benchmarkOutputSubdir"):
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        print(value.strip())
        break
else:
    print(f"{baseline_id}_official_locked")
PY_OUTPUT_SUBDIR
)"
OUTPUT_DIR="$OUTPUT_ROOT/$OUTPUT_SUBDIR"
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
  "--output-prefix" "$CSV_PREFIX"
)

if [[ -n "$KUBECONFIG_PATH" ]]; then PRECHECK_ARGS+=("--kubeconfig" "$KUBECONFIG_PATH"); fi
if [[ -n "$NAMESPACE" ]]; then PRECHECK_ARGS+=("--namespace" "$NAMESPACE"); fi

API_SMOKE_ARGS=(
  "bash"
  "$API_SMOKE_SCRIPT"
  "--base-url" "$BASE_URL"
  "--model" "$MODEL_NAME"
  "--request-timeout-seconds" "$REQUEST_TIMEOUT_SECONDS"
)
if [[ "$API_SMOKE_TIMEOUT_AS_UNSUPPORTED" == "true" ]]; then
  API_SMOKE_ARGS+=("--exit-unsupported-on-timeout" "--unsupported-exit-code" "$API_SMOKE_UNSUPPORTED_EXIT_CODE")
fi

PRECHECK_COMMAND_STR=""
if [[ "$SKIP_PRECHECK" != true ]]; then
  PRECHECK_COMMAND_STR="$(protocol_quote_command "bash" "$PRECHECK_SCRIPT" "${PRECHECK_ARGS[@]}")"
fi

API_SMOKE_COMMAND_STR=""
if [[ "$API_SMOKE_ENABLED" == "true" ]]; then
  API_SMOKE_COMMAND_STR="$(protocol_quote_command "${API_SMOKE_ARGS[@]}")"
fi

CLUSTER_CAPTURE_PRE_ARGS=(
  "bash"
  "$CLUSTER_CAPTURE_SCRIPT"
  "--profile-config" "$CLUSTER_CAPTURE_CONFIG"
  "--output-prefix" "$CLUSTER_CAPTURE_PRE_PREFIX"
  "--stage" "pre"
)

CLUSTER_CAPTURE_POST_ARGS=(
  "bash"
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

if [[ -n "${ADDITIONAL_NAMESPACES_EFFECTIVE:-}" ]]; then
  CLUSTER_CAPTURE_PRE_ARGS+=("--additional-namespaces" "${ADDITIONAL_NAMESPACES_EFFECTIVE}")
  CLUSTER_CAPTURE_POST_ARGS+=("--additional-namespaces" "${ADDITIONAL_NAMESPACES_EFFECTIVE}")
fi

CLUSTER_CAPTURE_PRE_COMMAND_STR="$(protocol_quote_command "${CLUSTER_CAPTURE_PRE_ARGS[@]}")"
CLUSTER_CAPTURE_POST_COMMAND_STR="$(protocol_quote_command "${CLUSTER_CAPTURE_POST_ARGS[@]}")"
CLUSTER_CAPTURE_PRE_ARTIFACTS_JSON="$(cluster_artifacts_json "$CLUSTER_CAPTURE_PRE_PREFIX" "$BENCHMARK_NAMESPACES_JSON")"
CLUSTER_CAPTURE_POST_ARTIFACTS_JSON="$(cluster_artifacts_json "$CLUSTER_CAPTURE_POST_PREFIX" "$BENCHMARK_NAMESPACES_JSON")"

metric_set_resolve_paths "$PHASE_MEASUREMENT_CSV_PREFIX"
METRIC_SET_CLIENT_SOURCE_ARTIFACTS_JSON="$(metric_set_client_artifacts_json "$PHASE_MEASUREMENT_CSV_PREFIX")"
METRIC_SET_CLUSTER_SOURCE_ARTIFACTS_JSON="$(metric_set_cluster_artifacts_json "$CLUSTER_CAPTURE_PRE_PREFIX" "$CLUSTER_CAPTURE_POST_PREFIX" "$BENCHMARK_NAMESPACES_JSON" "$CLUSTER_PROFILE_ARTIFACT_NAMES_JSON" "$CLUSTER_PROFILE_MANIFEST_SUFFIX" "$CLUSTER_PROFILE_TEXT_SUFFIX")"
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

echo "Recommended Kubernetes targets to apply before the run:"
for manifest in "${RECOMMENDED_APPLY_ORDER[@]}"; do echo " - $manifest"; done
echo
if [[ "$SKIP_PRECHECK" != true ]]; then
  echo "Pre-check command:"
  printf '%q' "bash"
  printf ' %q' "$PRECHECK_SCRIPT"
  for arg in "${PRECHECK_ARGS[@]}"; do printf ' %q' "$arg"; done
  printf '\n\n'
fi
echo "Cluster capture command (pre):"
printf "%s\n\n" "$CLUSTER_CAPTURE_PRE_COMMAND_STR"
echo "Cluster capture command (post):"
printf "%s\n\n" "$CLUSTER_CAPTURE_POST_COMMAND_STR"
if [[ "$API_SMOKE_ENABLED" == "true" ]]; then
  echo "API smoke command:"
  printf "%s\n\n" "$API_SMOKE_COMMAND_STR"
fi
if [[ "$PHASE_WARMUP_ENABLED_EFFECTIVE" == "true" ]]; then
  echo "Warm-up command:"
  printf 'locust'
  for arg in "${WARMUP_LOCUST_ARGS[@]}"; do printf ' %q' "$arg"; done
  printf '\n\n'
else
  echo "Warm-up                : disabled"
  echo
fi

echo "Measurement command:"
printf 'locust'
for arg in "${MEASUREMENT_LOCUST_ARGS[@]}"; do printf ' %q' "$arg"; done
printf '\n\n'

if [[ "$DRY_RUN" == true ]]; then
  echo "Expected cluster-side artifacts (pre):"
  print_artifact_list_from_json "$CLUSTER_CAPTURE_PRE_ARTIFACTS_JSON"
  echo "Expected cluster-side artifacts (post):"
  print_artifact_list_from_json "$CLUSTER_CAPTURE_POST_ARTIFACTS_JSON"
  echo "DRY RUN completed. No tests were executed."
  exit 0
fi

ensure_local_kubernetes_port_forward "$REPO_ROOT" "$BASE_URL" "$KUBECONFIG_PATH" "$NAMESPACE"

if [[ "$SKIP_PRECHECK" != true ]]; then
  bash "$PRECHECK_SCRIPT" "${PRECHECK_ARGS[@]}"
fi

"${CLUSTER_CAPTURE_PRE_ARGS[@]}"

if [[ "$API_SMOKE_ENABLED" == "true" ]]; then
  set +e
  "${API_SMOKE_ARGS[@]}"
  API_SMOKE_EXIT_CODE=$?
  set -e
  if [[ $API_SMOKE_EXIT_CODE -eq $API_SMOKE_UNSUPPORTED_EXIT_CODE && "$API_SMOKE_TIMEOUT_AS_UNSUPPORTED" == "true" ]]; then
    echo "API smoke finished with a controlled unsupported scenario (exit code $API_SMOKE_EXIT_CODE). Warm-up and measurement are skipped as experimental evidence." >&2
    exit "$API_SMOKE_EXIT_CODE"
  fi
  if [[ $API_SMOKE_EXIT_CODE -ne 0 ]]; then
    echo "API smoke finished with FAIL (exit code $API_SMOKE_EXIT_CODE). The run is stopped without executing warm-up or measurement." >&2
    exit "$API_SMOKE_EXIT_CODE"
  fi
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

MEASUREMENT_VALIDATION_JSON=""
if [[ $MEASUREMENT_EXIT_CODE -eq 0 && $POST_CAPTURE_EXIT_CODE -eq 0 ]]; then
  MEASUREMENT_STATS_CSV="${PHASE_MEASUREMENT_CSV_PREFIX}_stats.csv"
  MEASUREMENT_VALIDATION_JSON="$(validate_measurement_target_requests "$MEASUREMENT_STATS_CSV")"
  MEASUREMENT_VALID="$("$(require_python_command)" - "$MEASUREMENT_VALIDATION_JSON" <<'PY'
import json
import sys
print('true' if json.loads(sys.argv[1]).get('valid') else 'false')
PY
  )"
  if [[ "$MEASUREMENT_VALID" != "true" ]]; then
    MEASUREMENT_REASON="$("$(require_python_command)" - "$MEASUREMENT_VALIDATION_JSON" <<'PY'
import json
import sys
print(json.loads(sys.argv[1]).get('reason') or 'measurement_invalid')
PY
    )"
    if [[ "$API_SMOKE_TIMEOUT_AS_UNSUPPORTED" == "true" ]]; then
      UNSUPPORTED_JSON_PATH="${PHASE_MEASUREMENT_CSV_PREFIX}_unsupported.json"
      write_measurement_unsupported_evidence "$UNSUPPORTED_JSON_PATH" "$MEASUREMENT_REASON" "$MEASUREMENT_VALIDATION_JSON"
      echo "CONTROLLED UNSUPPORTED SCENARIO DETECTED." >&2
      echo "The Locust measurement completed without valid target requests for POST /v1/chat/completions." >&2
      echo "Reason: $MEASUREMENT_REASON." >&2
      echo "The generated CSV is retained as diagnostic evidence: $MEASUREMENT_STATS_CSV" >&2
      echo "Unsupported evidence: $UNSUPPORTED_JSON_PATH" >&2
      exit "$API_SMOKE_UNSUPPORTED_EXIT_CODE"
    fi
    echo "The Locust measurement completed without valid target requests." >&2
    echo "Reason: $MEASUREMENT_REASON." >&2
    echo "Measurement CSV: $MEASUREMENT_STATS_CSV" >&2
    exit 1
  fi
fi

echo
if [[ $MEASUREMENT_EXIT_CODE -eq 0 && $POST_CAPTURE_EXIT_CODE -eq 0 ]]; then
  echo "Run completed successfully."
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
  print_artifact_list_from_json "$CLUSTER_CAPTURE_PRE_ARTIFACTS_JSON"
  echo "Metric-set artifacts:"
  echo " - ${METRIC_SET_MANIFEST_PATH}"
  echo " - ${METRIC_SET_TEXT_PATH}"
  echo "Cluster-side artifacts (post):"
  print_artifact_list_from_json "$CLUSTER_CAPTURE_POST_ARTIFACTS_JSON"
  exit 0
else
  if [[ $MEASUREMENT_EXIT_CODE -ne 0 ]]; then
      exit $MEASUREMENT_EXIT_CODE
  fi
  echo "The final cluster-side collection finished with exit code $POST_CAPTURE_EXIT_CODE." >&2
  exit $POST_CAPTURE_EXIT_CODE
fi
