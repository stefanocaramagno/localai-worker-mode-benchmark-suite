#!/usr/bin/env bash
set -euo pipefail

PROFILE_CONFIG=""
KUBECONFIG_PATH=""
NAMESPACE_OVERRIDE=""
OUTPUT_PREFIX=""
BASE_URL=""
MODEL=""

print_usage() {
  cat <<'USAGE'
Usage:
  ./invoke-benchmark-precheck.sh [options]

Options:
  --profile-config PATH | -ProfileConfig PATH
  --kubeconfig PATH | -Kubeconfig PATH
  --namespace NAME | -Namespace NAME
  --output-prefix PREFIX | -OutputPrefix PREFIX
  --base-url URL | -BaseUrl URL
  --model NAME | -Model NAME
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

print_standalone_endpoint_guidance() {
  local base_url="${1:-}"
  echo
  echo "Questo script di pre-check non crea automaticamente il port-forward Kubernetes." >&2
  echo "Il BaseUrl specificato deve essere già raggiungibile prima dell'esecuzione dello script standalone." >&2
  echo "Se stai eseguendo la pipeline tramite i launcher principali e usi http://localhost:8080, il port-forward viene gestito automaticamente a livello di launcher." >&2
  echo "Se invece stai eseguendo direttamente questo script standalone, prepara prima l'endpoint oppure crea manualmente il port-forward verso service/localai-server." >&2
  echo
  if [[ -n "$base_url" ]]; then
    echo "BaseUrl richiesto: $base_url" >&2
  fi
}

resolve_repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd -- "$script_dir/../../.." && pwd
}

load_profile() {
  local profile_file="$1"
  local python_cmd
  python_cmd="$(require_python_command)"

  mapfile -t PROFILE_VALUES < <("$python_cmd" - "$profile_file" <<'PY'
import json
import sys
from pathlib import Path

profile_path = Path(sys.argv[1])
required = [
    "profileId",
    "description",
    "kubeconfig",
    "namespace",
    "expectedReadyNodes",
    "expectedWorkerNodes",
    "allowedPodPhases",
    "minimumNamespacePods",
    "criticalWaitingReasons",
    "maxTotalRestartsInNamespace",
    "requireMetricsApi",
    "maxNodeCpuPercent",
    "maxNodeMemoryPercent",
    "defaultOutputRoot",
]
with profile_path.open("r", encoding="utf-8-sig") as fh:
    data = json.load(fh)
missing = [key for key in required if key not in data]
if missing:
    print(
        f"Il file di profilo '{profile_path}' non contiene le proprietà obbligatorie: {', '.join(missing)}.",
        file=sys.stderr,
    )
    sys.exit(1)
print(str(profile_path))
for key in required:
    value = data[key]
    if isinstance(value, (list, dict)):
        print(json.dumps(value, separators=(",", ":")))
    else:
        print(str(value))
PY
)

  PROFILE_FILE_RESOLVED="${PROFILE_VALUES[0]}"
  PROFILE_ID="${PROFILE_VALUES[1]}"
  PROFILE_DESCRIPTION="${PROFILE_VALUES[2]}"
  PROFILE_KUBECONFIG_REL="${PROFILE_VALUES[3]}"
  PROFILE_NAMESPACE="${PROFILE_VALUES[4]}"
  PROFILE_EXPECTED_READY_NODES_JSON="${PROFILE_VALUES[5]}"
  PROFILE_EXPECTED_WORKER_NODES_JSON="${PROFILE_VALUES[6]}"
  PROFILE_ALLOWED_POD_PHASES_JSON="${PROFILE_VALUES[7]}"
  PROFILE_MINIMUM_NAMESPACE_PODS="${PROFILE_VALUES[8]}"
  PROFILE_CRITICAL_WAITING_REASONS_JSON="${PROFILE_VALUES[9]}"
  PROFILE_MAX_TOTAL_RESTARTS="${PROFILE_VALUES[10]}"
  PROFILE_REQUIRE_METRICS_API="${PROFILE_VALUES[11]}"
  PROFILE_MAX_NODE_CPU_PERCENT="${PROFILE_VALUES[12]}"
  PROFILE_MAX_NODE_MEMORY_PERCENT="${PROFILE_VALUES[13]}"
  PROFILE_DEFAULT_OUTPUT_ROOT_REL="${PROFILE_VALUES[14]}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-config|-ProfileConfig)
      PROFILE_CONFIG="$2"
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
    --output-prefix|-OutputPrefix)
      OUTPUT_PREFIX="$2"
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

if [[ -z "$PROFILE_CONFIG" ]]; then
  PROFILE_CONFIG="$REPO_ROOT/config/precheck/TC1.json"
fi

if [[ ! -f "$PROFILE_CONFIG" ]]; then
  echo "Il file di profilo del pre-check non esiste: $PROFILE_CONFIG" >&2
  exit 1
fi

require_command kubectl
require_command curl
PYTHON_CMD="$(require_python_command)"
load_profile "$PROFILE_CONFIG"

if [[ -z "$KUBECONFIG_PATH" ]]; then
  KUBECONFIG_PATH="$REPO_ROOT/$PROFILE_KUBECONFIG_REL"
fi

if [[ -z "$NAMESPACE_OVERRIDE" ]]; then
  NAMESPACE_OVERRIDE="$PROFILE_NAMESPACE"
fi

if [[ ! -f "$KUBECONFIG_PATH" ]]; then
  echo "Il file kubeconfig specificato non esiste: $KUBECONFIG_PATH" >&2
  exit 1
fi

if [[ -n "$BASE_URL" ]]; then
  print_standalone_endpoint_guidance "$BASE_URL"
fi

if [[ -z "$OUTPUT_PREFIX" ]]; then
  OUTPUT_DIRECTORY="$REPO_ROOT/$PROFILE_DEFAULT_OUTPUT_ROOT_REL"
  mkdir -p -- "$OUTPUT_DIRECTORY"
  OUTPUT_PREFIX="$OUTPUT_DIRECTORY/precheck"
else
  OUTPUT_DIRECTORY="$(dirname -- "$OUTPUT_PREFIX")"
  mkdir -p -- "$OUTPUT_DIRECTORY"
fi

PRECHECK_JSON_PATH="${OUTPUT_PREFIX}_precheck.json"
PRECHECK_TEXT_PATH="${OUTPUT_PREFIX}_precheck.txt"

NODES_JSON_FILE="$(mktemp)"
NAMESPACE_JSON_FILE="$(mktemp)"
PODS_JSON_FILE="$(mktemp)"
TOP_NODES_FILE="$(mktemp)"
TOP_PODS_FILE="$(mktemp)"
MODELS_JSON_FILE="$(mktemp)"
trap 'rm -f "$NODES_JSON_FILE" "$NAMESPACE_JSON_FILE" "$PODS_JSON_FILE" "$TOP_NODES_FILE" "$TOP_PODS_FILE" "$MODELS_JSON_FILE"' EXIT

if ! kubectl --kubeconfig "$KUBECONFIG_PATH" get nodes -o json > "$NODES_JSON_FILE"; then
  echo "Impossibile interrogare il cluster tramite kubectl get nodes." >&2
  exit 1
fi

if ! kubectl --kubeconfig "$KUBECONFIG_PATH" get namespace "$NAMESPACE_OVERRIDE" -o json > "$NAMESPACE_JSON_FILE"; then
  echo "Impossibile ottenere il namespace '$NAMESPACE_OVERRIDE'." >&2
  exit 1
fi

if ! kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -n "$NAMESPACE_OVERRIDE" -o json > "$PODS_JSON_FILE"; then
  echo "Impossibile ottenere i pod del namespace '$NAMESPACE_OVERRIDE'." >&2
  exit 1
fi

NAMESPACE_POD_COUNT="$("$PYTHON_CMD" - "$PODS_JSON_FILE" <<'PY'
import json
import sys
from pathlib import Path

pods_path = Path(sys.argv[1])
payload = json.loads(pods_path.read_text(encoding="utf-8-sig"))
print(len(payload.get("items", [])))
PY
)"

if [[ "$PROFILE_REQUIRE_METRICS_API" == "True" || "$PROFILE_REQUIRE_METRICS_API" == "true" ]]; then
  if ! kubectl --kubeconfig "$KUBECONFIG_PATH" top nodes --no-headers > "$TOP_NODES_FILE"; then
    echo "Il comando 'kubectl top nodes' non è disponibile o non restituisce dati." >&2
    exit 1
  fi

  if [[ "$NAMESPACE_POD_COUNT" -gt 0 ]]; then
    if ! kubectl --kubeconfig "$KUBECONFIG_PATH" top pods -n "$NAMESPACE_OVERRIDE" --no-headers > "$TOP_PODS_FILE" 2>/dev/null; then
      echo "Il comando 'kubectl top pods -n $NAMESPACE_OVERRIDE' non è disponibile o non restituisce dati." >&2
      exit 1
    fi
  else
    : > "$TOP_PODS_FILE"
  fi
fi

if [[ -n "$BASE_URL" ]]; then
  if ! curl -fsS "$BASE_URL/v1/models" -o "$MODELS_JSON_FILE"; then
    echo
    echo "Impossibile ottenere una risposta valida da $BASE_URL/v1/models durante il pre-check." >&2
    print_standalone_endpoint_guidance "$BASE_URL"
    exit 1
  fi
fi

if ! "$PYTHON_CMD" - "$PROFILE_FILE_RESOLVED" "$KUBECONFIG_PATH" "$NAMESPACE_OVERRIDE" "$OUTPUT_PREFIX" "$PRECHECK_JSON_PATH" "$PRECHECK_TEXT_PATH" "$BASE_URL" "$MODEL" "$NODES_JSON_FILE" "$NAMESPACE_JSON_FILE" "$PODS_JSON_FILE" "$TOP_NODES_FILE" "$TOP_PODS_FILE" "$MODELS_JSON_FILE" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

profile_path = Path(sys.argv[1])
kubeconfig_path = sys.argv[2]
namespace_name = sys.argv[3]
output_prefix = sys.argv[4]
json_path = Path(sys.argv[5])
text_path = Path(sys.argv[6])
base_url = sys.argv[7]
model_name = sys.argv[8]
nodes_path = Path(sys.argv[9])
namespace_path = Path(sys.argv[10])
pods_path = Path(sys.argv[11])
top_nodes_path = Path(sys.argv[12])
top_pods_path = Path(sys.argv[13])
models_path = Path(sys.argv[14])

profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
nodes_payload = json.loads(nodes_path.read_text(encoding="utf-8-sig"))
namespace_payload = json.loads(namespace_path.read_text(encoding="utf-8-sig"))
pods_payload = json.loads(pods_path.read_text(encoding="utf-8-sig"))

require_metrics = bool(profile.get("requireMetricsApi", False))
timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
checks = []
failures = []


def add_check(name, success, details):
    checks.append({"name": name, "success": success, "details": details})
    if not success:
        failures.append(name)


expected_ready_nodes = list(profile.get("expectedReadyNodes", []))
expected_worker_nodes = set(profile.get("expectedWorkerNodes", []))
node_items = nodes_payload.get("items", [])
node_map = {}
for item in node_items:
    metadata = item.get("metadata") or {}
    status = item.get("status") or {}
    node_name = metadata.get("name")
    conditions = status.get("conditions") or []
    ready_status = None
    for condition in conditions:
        if condition.get("type") == "Ready":
            ready_status = condition.get("status")
            break
    node_map[node_name] = {
        "ready": ready_status == "True",
        "labels": metadata.get("labels") or {},
    }

missing_nodes = [name for name in expected_ready_nodes if name not in node_map]
not_ready_nodes = [name for name in expected_ready_nodes if name in node_map and not node_map[name]["ready"]]
add_check(
    "cluster_nodes_ready",
    not missing_nodes and not not_ready_nodes,
    {
        "expectedReadyNodes": expected_ready_nodes,
        "missingNodes": missing_nodes,
        "notReadyNodes": not_ready_nodes,
        "discoveredNodes": sorted([name for name in node_map.keys() if name]),
    },
)

namespace_phase = (namespace_payload.get("status") or {}).get("phase")
add_check(
    "namespace_active",
    namespace_phase == "Active",
    {
        "namespace": namespace_name,
        "phase": namespace_phase,
    },
)

allowed_phases = set(profile.get("allowedPodPhases", []))
minimum_namespace_pods = int(profile.get("minimumNamespacePods", 0))
critical_waiting_reasons = set(profile.get("criticalWaitingReasons", []))
max_total_restarts = int(profile.get("maxTotalRestartsInNamespace", 0))
pod_items = pods_payload.get("items", [])
namespace_pod_count = len(pod_items)
invalid_phase_pods = []
critical_waiting = []
total_restarts = 0
worker_pod_nodes = {}
for item in pod_items:
    metadata = item.get("metadata") or {}
    status = item.get("status") or {}
    pod_name = metadata.get("name")
    phase = status.get("phase")
    spec_node = (item.get("spec") or {}).get("nodeName")
    if phase not in allowed_phases:
        invalid_phase_pods.append({"pod": pod_name, "phase": phase})
    for collection_name in ("containerStatuses", "initContainerStatuses"):
        for container_status in status.get(collection_name) or []:
            total_restarts += int(container_status.get("restartCount") or 0)
            state = container_status.get("state") or {}
            waiting = state.get("waiting") or {}
            reason = waiting.get("reason")
            if reason in critical_waiting_reasons:
                critical_waiting.append(
                    {
                        "pod": pod_name,
                        "container": container_status.get("name"),
                        "reason": reason,
                    }
                )
    if pod_name and pod_name.startswith("localai-rpc-") and spec_node:
        worker_pod_nodes[pod_name] = spec_node

namespace_pods_healthy = (
    namespace_pod_count >= minimum_namespace_pods
    and not invalid_phase_pods
    and not critical_waiting
    and total_restarts <= max_total_restarts
)

namespace_pods_details = {
    "namespace": namespace_name,
    "minimumNamespacePods": minimum_namespace_pods,
    "podCount": namespace_pod_count,
    "hasMinimumNamespacePods": namespace_pod_count >= minimum_namespace_pods,
    "invalidPhasePods": invalid_phase_pods,
    "criticalWaiting": critical_waiting,
    "totalRestarts": total_restarts,
    "maxTotalRestarts": max_total_restarts,
    "note": None,
}
if namespace_pod_count == 0:
    namespace_pods_healthy = False
    namespace_pods_details["note"] = (
        f"Namespace '{namespace_name}' exists but currently contains no workload pods. "
        f"Minimum required pods: {minimum_namespace_pods}."
    )

add_check("namespace_pods_healthy", namespace_pods_healthy, namespace_pods_details)

worker_nodes_observed = sorted(set(worker_pod_nodes.values()))
worker_nodes_outside_expected = [name for name in worker_nodes_observed if name not in expected_worker_nodes]
add_check(
    "worker_nodes_expected",
    not worker_nodes_outside_expected,
    {
        "expectedWorkerNodes": sorted(expected_worker_nodes),
        "observedWorkerPodNodes": worker_pod_nodes,
        "unexpectedWorkerNodes": worker_nodes_outside_expected,
    },
)

node_metrics = []
namespace_pod_metrics = []
if require_metrics:
    top_nodes_lines = [line.strip() for line in top_nodes_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    top_pods_lines = [line.strip() for line in top_pods_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    for line in top_nodes_lines:
        parts = line.split()
        if len(parts) >= 5:
            cpu_percent = int(parts[2].rstrip("%"))
            memory_percent = int(parts[4].rstrip("%"))
            node_metrics.append(
                {
                    "name": parts[0],
                    "cpu": parts[1],
                    "cpuPercent": cpu_percent,
                    "memory": parts[3],
                    "memoryPercent": memory_percent,
                }
            )
    for line in top_pods_lines:
        parts = line.split()
        if len(parts) >= 3:
            namespace_pod_metrics.append(
                {
                    "pod": parts[0],
                    "cpu": parts[1],
                    "memory": parts[2],
                }
            )
    max_cpu_percent = max((entry["cpuPercent"] for entry in node_metrics), default=0)
    max_memory_percent = max((entry["memoryPercent"] for entry in node_metrics), default=0)
    add_check(
        "metrics_api_and_capacity",
        max_cpu_percent <= int(profile.get("maxNodeCpuPercent", 100)) and max_memory_percent <= int(profile.get("maxNodeMemoryPercent", 100)),
        {
            "maxNodeCpuPercent": max_cpu_percent,
            "maxAllowedNodeCpuPercent": int(profile.get("maxNodeCpuPercent", 100)),
            "maxNodeMemoryPercent": max_memory_percent,
            "maxAllowedNodeMemoryPercent": int(profile.get("maxNodeMemoryPercent", 100)),
            "nodeMetricsCount": len(node_metrics),
            "namespacePodMetricsCount": len(namespace_pod_metrics),
            "note": None if namespace_pod_metrics else f"No pod-level metrics were collected for namespace '{namespace_name}'.",
        },
    )

model_check_details = {
    "baseUrl": base_url or None,
    "requiredModel": model_name or None,
    "availableModels": [],
    "guidance": None,
}
model_check_success = True
if base_url:
    models_payload = json.loads(models_path.read_text(encoding="utf-8-sig"))
    available_models = []
    for item in models_payload.get("data", []):
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            available_models.append(item["id"])
    model_check_details["availableModels"] = available_models
    if model_name:
        model_check_success = model_name in available_models
    if not model_check_success:
        model_check_details["guidance"] = (
            "Questo script di pre-check non crea automaticamente il port-forward Kubernetes. "
            "Il BaseUrl specificato deve essere già raggiungibile prima dell'esecuzione dello script standalone. "
            "Se stai eseguendo la pipeline tramite i launcher principali e usi http://localhost:8080, il port-forward viene gestito automaticamente a livello di launcher. "
            "Se invece stai eseguendo direttamente questo script standalone, prepara prima l'endpoint oppure crea manualmente il port-forward verso service/localai-server."
        )
add_check("service_endpoint_and_model", model_check_success, model_check_details)

success = not failures
result_payload = {
    "profile": {
        "profileFile": str(profile_path),
        "profileId": profile.get("profileId"),
        "description": profile.get("description"),
    },
    "execution": {
        "timestampUtc": timestamp_utc,
        "kubeconfig": kubeconfig_path,
        "namespace": namespace_name,
        "outputPrefix": output_prefix,
        "baseUrl": base_url or None,
        "model": model_name or None,
    },
    "summary": {
        "success": success,
        "failedChecks": failures,
        "checkCount": len(checks),
    },
    "checks": checks,
}
json_path.write_text(json.dumps(result_payload, indent=2) + "\n", encoding="utf-8-sig")

summary_lines = [
    "=============================================",
    " Benchmark Technical Pre-Check",
    "=============================================",
    f"Profile ID          : {profile.get('profileId')}",
    f"Timestamp (UTC)     : {timestamp_utc}",
    f"Kubeconfig          : {kubeconfig_path}",
    f"Namespace           : {namespace_name}",
    f"Base URL            : {base_url or '-'}",
    f"Model               : {model_name or '-'}",
    f"JSON report         : {json_path}",
    f"Overall result      : {'PASS' if success else 'FAIL'}",
    "",
    "Checks:",
]
for check in checks:
    status = "PASS" if check["success"] else "FAIL"
    summary_lines.append(f" - {check['name']}: {status}")
if failures:
    summary_lines.extend(["", "Failed checks:"])
    for failed in failures:
        summary_lines.append(f" - {failed}")
text_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8-sig")
print("\n".join(summary_lines))
if not success:
    sys.exit(1)
PY
then
  exit 1
fi
