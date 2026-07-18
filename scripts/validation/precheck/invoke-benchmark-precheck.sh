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

print_standalone_endpoint_guidance() {
  local base_url="${1:-}"
  echo
  echo "This standalone pre-check script does not automatically create the Kubernetes port-forward." >&2
  echo "The specified BaseUrl must already be reachable before executing this standalone script." >&2
  echo "When running through the main launchers with http://localhost:8080, port-forwarding is managed automatically by the launcher layer." >&2
  echo "If you are running this standalone script directly, prepare the endpoint first or create the port-forward to service/localai-server manually." >&2
  echo
  if [[ -n "$base_url" ]]; then
    echo "Required BaseUrl: $base_url" >&2
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
        f"The profile file '{profile_path}' does not contain the required properties: {', '.join(missing)}.",
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
      echo "Unrecognized argument: $1" >&2
      print_usage >&2
      exit 1
      ;;
  esac
done

REPO_ROOT="$(resolve_repo_root)"

if [[ -z "$PROFILE_CONFIG" ]]; then
  PROFILE_CONFIG="$REPO_ROOT/config/precheck/profiles/TC_C0_HISTORICAL_FIXED_CLUSTER.json"
fi

if [[ ! -f "$PROFILE_CONFIG" ]]; then
  echo "The pre-check profile file does not exist: $PROFILE_CONFIG" >&2
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
  echo "The specified kubeconfig file does not exist: $KUBECONFIG_PATH" >&2
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
  echo "Unable to query the cluster using kubectl get nodes." >&2
  exit 1
fi

if ! kubectl --kubeconfig "$KUBECONFIG_PATH" get namespace "$NAMESPACE_OVERRIDE" -o json > "$NAMESPACE_JSON_FILE"; then
  echo "Unable to retrieve namespace '$NAMESPACE_OVERRIDE'." >&2
  exit 1
fi

if ! kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -n "$NAMESPACE_OVERRIDE" -o json > "$PODS_JSON_FILE"; then
  echo "Unable to retrieve pods for namespace '$NAMESPACE_OVERRIDE'." >&2
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
    echo "The 'kubectl top nodes' command is unavailable or returns no data." >&2
    exit 1
  fi

  if [[ "$NAMESPACE_POD_COUNT" -gt 0 ]]; then
    if ! kubectl --kubeconfig "$KUBECONFIG_PATH" top pods -n "$NAMESPACE_OVERRIDE" --no-headers > "$TOP_PODS_FILE" 2>/dev/null; then
      echo "The 'kubectl top pods -n $NAMESPACE_OVERRIDE' is unavailable or returns no data." >&2
      exit 1
    fi
  else
    : > "$TOP_PODS_FILE"
  fi
fi

if [[ -n "$BASE_URL" ]]; then
  if ! curl -fsS "$BASE_URL/v1/models" -o "$MODELS_JSON_FILE"; then
    echo
    echo "Unable to obtain a valid response from $BASE_URL/v1/models during the pre-check." >&2
    print_standalone_endpoint_guidance "$BASE_URL"
    exit 1
  fi
fi

if ! "$PYTHON_CMD" - "$PROFILE_FILE_RESOLVED" "$KUBECONFIG_PATH" "$NAMESPACE_OVERRIDE" "$OUTPUT_PREFIX" "$PRECHECK_JSON_PATH" "$PRECHECK_TEXT_PATH" "$BASE_URL" "$MODEL" "$NODES_JSON_FILE" "$NAMESPACE_JSON_FILE" "$PODS_JSON_FILE" "$TOP_NODES_FILE" "$TOP_PODS_FILE" "$MODELS_JSON_FILE" "$REPO_ROOT" <<'PY'
import json
import subprocess
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
repo_root = Path(sys.argv[15]).resolve()
sys.path.insert(0, str(repo_root / "scripts" / "common"))
from artifact_paths import normalize_artifact_payload, normalize_artifact_text

def repo_relative(value):
    if value is None:
        return value
    text = str(value)
    if not text.strip():
        return text
    normalised = text.replace("\\", "/")
    root = str(repo_root.resolve()).replace("\\", "/").rstrip("/")
    normalised_cmp = normalised.lower()
    root_cmp = root.lower()
    if normalised_cmp == root_cmp:
        return "."
    if normalised_cmp.startswith(root_cmp + "/"):
        return normalised[len(root) + 1:]
    marker = "/localai-worker-mode-benchmark-suite/"
    marker_index = normalised_cmp.find(marker)
    if marker_index >= 0:
        return normalised[marker_index + len(marker):]
    return text

def normalize_payload(value):
    if isinstance(value, dict):
        return {key: normalize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_payload(item) for item in value]
    if isinstance(value, str):
        return repo_relative(value)
    return value


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


def kubectl_json(*args):
    command = ["kubectl", "--kubeconfig", kubeconfig_path, *args, "-o", "json"]
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "kubectl command failed").strip())
    return json.loads(completed.stdout or "{}")


def analyse_namespace(namespace, pods, minimum_pods, allowed, critical_reasons):
    invalid_phase_pods = []
    critical_waiting = []
    not_ready_containers = []
    total_restarts = 0
    for item in pods:
        metadata = item.get("metadata") or {}
        status = item.get("status") or {}
        pod_name = metadata.get("name")
        phase = status.get("phase")
        if phase not in allowed:
            invalid_phase_pods.append({"pod": pod_name, "phase": phase})
        for collection_name in ("containerStatuses", "initContainerStatuses"):
            for container_status in status.get(collection_name) or []:
                total_restarts += int(container_status.get("restartCount") or 0)
                if collection_name == "containerStatuses" and not bool(container_status.get("ready", False)) and phase != "Succeeded":
                    not_ready_containers.append({"pod": pod_name, "container": container_status.get("name")})
                waiting = (container_status.get("state") or {}).get("waiting") or {}
                reason = waiting.get("reason")
                if reason in critical_reasons:
                    critical_waiting.append({"pod": pod_name, "container": container_status.get("name"), "reason": reason})
    return {
        "namespace": namespace,
        "podCount": len(pods),
        "minimumPods": minimum_pods,
        "invalidPhasePods": invalid_phase_pods,
        "invalidPhasePodsCount": len(invalid_phase_pods),
        "criticalWaiting": critical_waiting,
        "criticalWaitingCount": len(critical_waiting),
        "notReadyContainers": not_ready_containers,
        "notReadyContainersCount": len(not_ready_containers),
        "totalRestarts": total_restarts,
        "healthy": len(pods) >= minimum_pods and not invalid_phase_pods and not critical_waiting and not not_ready_containers,
    }


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
        if isinstance(item, dict) and isinstance(item.get("id", None), str):
            available_models.append(item["id"])
    model_check_details["availableModels"] = available_models
    if model_name:
        model_check_success = model_name in available_models
    if not model_check_success:
        model_check_details["guidance"] = (
            "This standalone pre-check script does not automatically create the Kubernetes port-forward. "
            "The specified BaseUrl must already be reachable before executing this standalone script. "
            "When running through the main launchers with http://localhost:8080, port-forwarding is managed automatically by the launcher layer. "
            "If you are running this standalone script directly, prepare the endpoint first or create the port-forward to service/localai-server manually."
        )

allowed_phases = set(profile.get("allowedPodPhases", []))
minimum_namespace_pods = int(profile.get("minimumNamespacePods", 0))
critical_waiting_reasons = set(profile.get("criticalWaitingReasons", []))
max_total_restarts = int(profile.get("maxTotalRestartsInNamespace", 0))
restart_tolerance_policy = profile.get("restartTolerancePolicy") or {}
treat_recovered_restarts_as_warning = bool(restart_tolerance_policy.get("treatRecoveredRestartsAsWarning", False))
max_recovered_restarts = int(restart_tolerance_policy.get("maxRecoveredRestartsInNamespace", max_total_restarts))
require_all_containers_ready_for_restart_tolerance = bool(restart_tolerance_policy.get("requireAllContainersReady", True))
require_service_endpoint_ready_for_restart_tolerance = bool(restart_tolerance_policy.get("requireServiceEndpointReady", True))

namespace_validation_policy = profile.get("namespaceValidationPolicy") or {}
additional_namespaces = [str(item).strip() for item in profile.get("additionalNamespaces", []) if str(item).strip() and str(item).strip() != namespace_name]
validate_additional_namespaces = bool(namespace_validation_policy.get("validateAdditionalNamespaces", bool(additional_namespaces)))
minimum_pods_per_additional_namespace = int(namespace_validation_policy.get("minimumPodsPerAdditionalNamespace", 1))
if validate_additional_namespaces:
    for additional_namespace in additional_namespaces:
        details = {
            "namespace": additional_namespace,
            "namespaceActive": False,
            "podCount": 0,
            "minimumPods": minimum_pods_per_additional_namespace,
            "error": None,
        }
        success = False
        try:
            additional_namespace_payload = kubectl_json("get", "namespace", additional_namespace)
            additional_pods_payload = kubectl_json("get", "pods", "-n", additional_namespace)
            details["namespaceActive"] = (additional_namespace_payload.get("status") or {}).get("phase") == "Active"
            analysed = analyse_namespace(
                additional_namespace,
                additional_pods_payload.get("items", []) or [],
                minimum_pods_per_additional_namespace,
                allowed_phases,
                critical_waiting_reasons,
            )
            details.update(analysed)
            success = bool(details.get("namespaceActive") and analysed.get("healthy"))
        except Exception as exc:
            details["error"] = str(exc)
        add_check(f"additional_namespace_healthy:{additional_namespace}", success, details)

pod_items = pods_payload.get("items", [])
namespace_pod_count = len(pod_items)
invalid_phase_pods = []
critical_waiting = []
not_ready_containers = []
restart_details = []
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
            container_restarts = int(container_status.get("restartCount") or 0)
            total_restarts += container_restarts
            if container_restarts > 0:
                restart_details.append(
                    {
                        "pod": pod_name,
                        "container": container_status.get("name"),
                        "restartCount": container_restarts,
                        "collection": collection_name,
                    }
                )
            if collection_name == "containerStatuses" and not bool(container_status.get("ready", False)) and phase != "Succeeded":
                not_ready_containers.append(
                    {
                        "pod": pod_name,
                        "container": container_status.get("name"),
                    }
                )
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

base_pods_healthy_ignoring_restarts = (
    namespace_pod_count >= minimum_namespace_pods
    and not invalid_phase_pods
    and not critical_waiting
)
all_containers_ready = not not_ready_containers
service_endpoint_condition_met = (not require_service_endpoint_ready_for_restart_tolerance) or model_check_success
containers_ready_condition_met = (not require_all_containers_ready_for_restart_tolerance) or all_containers_ready
restart_tolerance_applies = (
    treat_recovered_restarts_as_warning
    and total_restarts > max_total_restarts
    and total_restarts <= max_recovered_restarts
    and base_pods_healthy_ignoring_restarts
    and containers_ready_condition_met
    and service_endpoint_condition_met
)
namespace_pods_healthy = (
    (base_pods_healthy_ignoring_restarts and total_restarts <= max_total_restarts)
    or restart_tolerance_applies
)

if total_restarts <= max_total_restarts:
    restart_severity = "none_or_within_strict_threshold"
elif restart_tolerance_applies:
    restart_severity = "warning_recovered_restarts_within_tolerance"
else:
    restart_severity = "blocking_restarts_exceed_policy"

namespace_pods_details = {
    "namespace": namespace_name,
    "minimumNamespacePods": minimum_namespace_pods,
    "podCount": namespace_pod_count,
    "hasMinimumNamespacePods": namespace_pod_count >= minimum_namespace_pods,
    "invalidPhasePods": invalid_phase_pods,
    "invalidPhasePodsCount": len(invalid_phase_pods),
    "criticalWaiting": critical_waiting,
    "criticalWaitingCount": len(critical_waiting),
    "notReadyContainers": not_ready_containers,
    "notReadyContainersCount": len(not_ready_containers),
    "allContainersReady": all_containers_ready,
    "totalRestarts": total_restarts,
    "maxTotalRestarts": max_total_restarts,
    "restartTolerancePolicy": {
        "enabled": treat_recovered_restarts_as_warning,
        "maxRecoveredRestartsInNamespace": max_recovered_restarts,
        "requireAllContainersReady": require_all_containers_ready_for_restart_tolerance,
        "requireServiceEndpointReady": require_service_endpoint_ready_for_restart_tolerance,
    },
    "restartToleranceApplied": restart_tolerance_applies,
    "restartSeverity": restart_severity,
    "restartDetails": restart_details,
    "note": (
        "Recovered restarts were observed and retained as a warning because all pod health, readiness and service checks required by the profile are satisfied."
        if restart_tolerance_applies
        else None
    ),
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

add_check("service_endpoint_and_model", model_check_success, model_check_details)

success = not failures
result_payload = {
    "profile": {
        "profileFile": repo_relative(profile_path),
        "profileId": profile.get("profileId"),
        "description": profile.get("description"),
    },
    "execution": {
        "timestampUtc": timestamp_utc,
        "kubeconfig": kubeconfig_path,
        "namespace": namespace_name,
        "additionalNamespaces": additional_namespaces,
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
result_payload = normalize_artifact_payload(normalize_payload(result_payload), repo_root)
json_path.write_text(json.dumps(result_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8-sig")

summary_lines = [
    "=============================================",
    " Benchmark Technical Pre-Check",
    "=============================================",
    f"Profile ID          : {profile.get('profileId')}",
    f"Timestamp (UTC)     : {timestamp_utc}",
    f"Kubeconfig          : {repo_relative(kubeconfig_path)}",
    f"Namespace           : {namespace_name}",
    f"Additional namespaces: {', '.join(additional_namespaces) if additional_namespaces else '-'}",
    f"Base URL            : {base_url or '-'}",
    f"Model               : {model_name or '-'}",
    f"JSON report         : {repo_relative(json_path)}",
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
text_path.write_text(normalize_artifact_text("\n".join(summary_lines) + "\n", repo_root), encoding="utf-8-sig")
print("\n".join(summary_lines))
if not success:
    sys.exit(1)
PY
then
  exit 1
fi
