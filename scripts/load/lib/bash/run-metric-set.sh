#!/usr/bin/env bash
set -euo pipefail

metric_set_require_python_command() {
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
        f"Il file di metric set '{profile_path}' non contiene le proprietà obbligatorie: {', '.join(missing)}.",
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
  metric_set_json_array_from_lines \
    "${pre_prefix}_manifest.json" \
    "${pre_prefix}_summary.txt" \
    "${pre_prefix}_nodes-wide.txt" \
    "${pre_prefix}_top-nodes.txt" \
    "${pre_prefix}_pods-wide.txt" \
    "${pre_prefix}_top-pods.txt" \
    "${pre_prefix}_services.txt" \
    "${pre_prefix}_events.txt" \
    "${pre_prefix}_pods-describe.txt" \
    "${post_prefix}_manifest.json" \
    "${post_prefix}_summary.txt" \
    "${post_prefix}_nodes-wide.txt" \
    "${post_prefix}_top-nodes.txt" \
    "${post_prefix}_pods-wide.txt" \
    "${post_prefix}_top-pods.txt" \
    "${post_prefix}_services.txt" \
    "${post_prefix}_events.txt" \
    "${post_prefix}_pods-describe.txt"
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
    "$cluster_source_artifacts_json" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
text_path = Path(sys.argv[2])
profile_file = sys.argv[3]
profile_id = sys.argv[4]
description = sys.argv[5]
client_metrics = json.loads(sys.argv[6])
cluster_metrics = json.loads(sys.argv[7])
launcher_name = sys.argv[8]
run_id = sys.argv[9]
measurement_csv_prefix = sys.argv[10]
client_source_artifacts = json.loads(sys.argv[11])
cluster_source_artifacts = json.loads(sys.argv[12])

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
manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8-sig")

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
}
