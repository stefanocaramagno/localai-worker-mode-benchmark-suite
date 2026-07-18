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

metric_set_require_python_command() {
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

metric_set_load_profile() {
  local profile_file="$1"
  local python_cmd
  python_cmd="$(metric_set_require_python_command)"

  mapfile -t METRIC_SET_PROFILE_VALUES < <("$python_cmd" - "$profile_file" <<'PY'
import json
import sys
from pathlib import Path

profile_path = Path(sys.argv[1])
required = [
    "profileId",
    "description",
    "clientMetrics",
    "clusterMetrics",
    "metricSetManifestSuffix",
    "metricSetTextSuffix",
]
with profile_path.open("r", encoding="utf-8-sig") as fh:
    data = json.load(fh)
missing = [key for key in required if key not in data]
if missing:
    print(
        f"The metric-set file '{profile_path}' does not contain the required properties: {', '.join(missing)}.",
        file=sys.stderr,
    )
    sys.exit(1)
print(str(profile_path))
print(str(data["profileId"]))
print(str(data["description"]))
print(json.dumps(data["clientMetrics"], separators=(",", ":")))
print(json.dumps(data["clusterMetrics"], separators=(",", ":")))
print(str(data["metricSetManifestSuffix"]))
print(str(data["metricSetTextSuffix"]))
PY
)

  METRIC_SET_PROFILE_FILE_RESOLVED="${METRIC_SET_PROFILE_VALUES[0]}"
  METRIC_SET_PROFILE_ID="${METRIC_SET_PROFILE_VALUES[1]}"
  METRIC_SET_PROFILE_DESCRIPTION="${METRIC_SET_PROFILE_VALUES[2]}"
  METRIC_SET_CLIENT_METRICS_JSON="${METRIC_SET_PROFILE_VALUES[3]}"
  METRIC_SET_CLUSTER_METRICS_JSON="${METRIC_SET_PROFILE_VALUES[4]}"
  METRIC_SET_MANIFEST_SUFFIX="${METRIC_SET_PROFILE_VALUES[5]}"
  METRIC_SET_TEXT_SUFFIX="${METRIC_SET_PROFILE_VALUES[6]}"
}

metric_set_resolve_paths() {
  local measurement_csv_prefix="$1"
  METRIC_SET_MANIFEST_PATH="${measurement_csv_prefix}${METRIC_SET_MANIFEST_SUFFIX}"
  METRIC_SET_TEXT_PATH="${measurement_csv_prefix}${METRIC_SET_TEXT_SUFFIX}"
}

metric_set_repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd -- "$script_dir/../../../.." && pwd
}

metric_set_json_array_from_lines() {
  local python_cmd
  python_cmd="$(metric_set_require_python_command)"
  "$python_cmd" - "$@" <<'PY'
import json
import sys
print(json.dumps(sys.argv[1:], separators=(",", ":")))
PY
}

metric_set_client_artifacts_json() {
  local measurement_csv_prefix="$1"
  metric_set_json_array_from_lines \
    "${measurement_csv_prefix}_stats.csv" \
    "${measurement_csv_prefix}_stats_history.csv" \
    "${measurement_csv_prefix}_failures.csv" \
    "${measurement_csv_prefix}_exceptions.csv"
}

metric_set_cluster_artifacts_json() {
  local pre_prefix="$1"
  local post_prefix="$2"
  local namespaces_json="${3:-[]}"
  local artifact_items_json="${4:-[]}"
  local manifest_suffix="${5:-_manifest.json}"
  local text_suffix="${6:-_summary.txt}"
  local python_cmd
  python_cmd="$(metric_set_require_python_command)"

  "$python_cmd" - "$pre_prefix" "$post_prefix" "$namespaces_json" "$artifact_items_json" "$manifest_suffix" "$text_suffix" <<'PY'
import json
import re
import sys

pre_prefix = sys.argv[1]
post_prefix = sys.argv[2]
try:
    namespaces = json.loads(sys.argv[3])
except Exception:
    namespaces = []
try:
    artifact_items = json.loads(sys.argv[4])
except Exception:
    artifact_items = []
manifest_suffix = sys.argv[5]
text_suffix = sys.argv[6]

if not namespaces:
    namespaces = ["localai-benchmark"]
primary_namespace = str(namespaces[0])

def safe_token(value):
    token = re.sub(r"[^a-z0-9._-]+", "-", str(value).strip().lower()).strip("-")
    return token or "namespace"

def default_items():
    return [
        {"outputSuffix": "nodes-wide.txt", "command": "kubectl get nodes -o wide"},
        {"outputSuffix": "nodes.json", "command": "kubectl get nodes -o json"},
        {"outputSuffix": "top-nodes.txt", "command": "kubectl top nodes"},
        {"outputSuffix": "pods-wide.txt", "command": "kubectl get pods -n {namespace} -o wide"},
        {"outputSuffix": "pods.json", "command": "kubectl get pods -n {namespace} -o json"},
        {"outputSuffix": "top-pods.txt", "command": "kubectl top pods -n {namespace}"},
        {"outputSuffix": "top-pods-containers.txt", "command": "kubectl top pods -n {namespace} --containers"},
        {"outputSuffix": "services.txt", "command": "kubectl get svc -n {namespace}"},
        {"outputSuffix": "events.txt", "command": "kubectl get events -n {namespace}"},
        {"outputSuffix": "events.json", "command": "kubectl get events -n {namespace} -o json"},
        {"outputSuffix": "pods-describe.txt", "command": "kubectl describe pods -n {namespace}"},
    ]

if not artifact_items:
    artifact_items = default_items()

def suffix_and_command(item):
    if isinstance(item, str):
        return item, ""
    return str(item.get("outputSuffix") or item.get("name") or ""), str(item.get("command") or "")

def stage_artifacts(prefix):
    artifacts = [f"{prefix}{manifest_suffix}", f"{prefix}{text_suffix}"]
    for item in artifact_items:
        output_suffix, command = suffix_and_command(item)
        if not output_suffix:
            continue
        if "{namespace}" in command:
            for namespace in namespaces:
                if str(namespace) == primary_namespace:
                    artifacts.append(f"{prefix}_{output_suffix}")
                else:
                    artifacts.append(f"{prefix}_{safe_token(namespace)}_{output_suffix}")
        else:
            artifacts.append(f"{prefix}_{output_suffix}")
    return artifacts

print(json.dumps(stage_artifacts(pre_prefix) + stage_artifacts(post_prefix), separators=(",", ":")))
PY
}

metric_set_write_files() {
  local manifest_path="$1"
  local text_path="$2"
  local launcher_name="$3"
  local run_id="$4"
  local measurement_csv_prefix="$5"
  local client_source_artifacts_json="$6"
  local cluster_source_artifacts_json="$7"
  local python_cmd
  python_cmd="$(metric_set_require_python_command)"

  "$python_cmd" - \
    "$manifest_path" \
    "$text_path" \
    "$METRIC_SET_PROFILE_FILE_RESOLVED" \
    "$METRIC_SET_PROFILE_ID" \
    "$METRIC_SET_PROFILE_DESCRIPTION" \
    "$METRIC_SET_CLIENT_METRICS_JSON" \
    "$METRIC_SET_CLUSTER_METRICS_JSON" \
    "$launcher_name" \
    "$run_id" \
    "$measurement_csv_prefix" \
    "$client_source_artifacts_json" \
    "$cluster_source_artifacts_json" \
    "$(metric_set_repo_root)" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
text_path = Path(sys.argv[2])
repo_root = Path(sys.argv[13]).resolve()

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
    "metricSetProfile": {
        "profileFile": profile_file,
        "profileId": profile_id,
        "description": description,
    },
    "launcher": launcher_name,
    "runId": run_id,
    "measurementCsvPrefix": measurement_csv_prefix,
    "minimumMetrics": {
        "clientSide": client_metrics,
        "clusterSide": cluster_metrics,
    },
    "sourceArtifacts": {
        "clientSide": client_source_artifacts,
        "clusterSide": cluster_source_artifacts,
    },
}
payload = normalize(payload)
manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8-sig")

profile_file = repo_relative(profile_file)
measurement_csv_prefix = repo_relative(measurement_csv_prefix)
client_source_artifacts = [repo_relative(item) for item in client_source_artifacts]
cluster_source_artifacts = [repo_relative(item) for item in cluster_source_artifacts]

lines = []
lines.append("=============================================")
lines.append(" Minimum Mandatory Metric Set")
lines.append("=============================================")
lines.append(f"Metric set profile : {profile_id}")
lines.append(f"Description        : {description}")
lines.append(f"Launcher           : {launcher_name}")
lines.append(f"Run ID             : {run_id}")
lines.append(f"Measurement prefix : {measurement_csv_prefix}")
lines.append("")
lines.append("Client-side metrics:")
for item in client_metrics:
    lines.append(f" - {item}")
lines.append("")
lines.append("Cluster-side metrics:")
for item in cluster_metrics:
    lines.append(f" - {item}")
lines.append("")
lines.append("Client-side source artifacts:")
for item in client_source_artifacts:
    lines.append(f" - {item}")
lines.append("")
lines.append("Cluster-side source artifacts:")
for item in cluster_source_artifacts:
    lines.append(f" - {item}")
text_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
PY
  normalize_artifact_file "$manifest_path"
  normalize_artifact_file "$text_path"
}
