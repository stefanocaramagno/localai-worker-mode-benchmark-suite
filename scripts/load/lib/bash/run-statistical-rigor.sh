#!/usr/bin/env bash
set -euo pipefail

statistical_rigor_require_python_command() {
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

statistical_rigor_load_profile() {
  local profile_file="$1"
  local python_cmd
  python_cmd="$(statistical_rigor_require_python_command)"

  mapfile -t STATISTICAL_RIGOR_PROFILE_VALUES < <("$python_cmd" - "$profile_file" <<'PY'
import json
import sys
from pathlib import Path

profile_path = Path(sys.argv[1])
required = [
    "profileId",
    "description",
    "targetRequestType",
    "targetRequestName",
    "fallbackToAggregated",
    "requiredReplicaCount",
    "minimumSuccessfulReplicaCount",
    "coolDownBetweenReplicasSeconds",
    "coolDownBetweenScenariosSeconds",
    "stabilizationTimeoutSeconds",
    "stabilizationPollIntervalSeconds",
    "summaryManifestSuffix",
    "summaryTextSuffix",
    "trackedMetrics",
    "variabilityThresholds",
]
with profile_path.open("r", encoding="utf-8-sig") as fh:
    data = json.load(fh)
missing = [key for key in required if key not in data]
if missing:
    print(
        f"Il file di statistical rigor '{profile_path}' non contiene le proprietà obbligatorie: {', '.join(missing)}.",
        file=sys.stderr,
    )
    sys.exit(1)
print(str(profile_path))
print(str(data["profileId"]))
print(str(data["description"]))
print(str(data["targetRequestType"]))
print(str(data["targetRequestName"]))
print(str(data["fallbackToAggregated"]).lower())
print(str(data["requiredReplicaCount"]))
print(str(data["minimumSuccessfulReplicaCount"]))
print(str(data["coolDownBetweenReplicasSeconds"]))
print(str(data["coolDownBetweenScenariosSeconds"]))
print(str(data["stabilizationTimeoutSeconds"]))
print(str(data["stabilizationPollIntervalSeconds"]))
print(str(data["summaryManifestSuffix"]))
print(str(data["summaryTextSuffix"]))
print(json.dumps(data["trackedMetrics"], separators=(",", ":")))
print(json.dumps(data["variabilityThresholds"], separators=(",", ":")))
PY
)

  STATISTICAL_RIGOR_PROFILE_FILE_RESOLVED="${STATISTICAL_RIGOR_PROFILE_VALUES[0]}"
  STATISTICAL_RIGOR_PROFILE_ID="${STATISTICAL_RIGOR_PROFILE_VALUES[1]}"
  STATISTICAL_RIGOR_DESCRIPTION="${STATISTICAL_RIGOR_PROFILE_VALUES[2]}"
  STATISTICAL_RIGOR_TARGET_REQUEST_TYPE="${STATISTICAL_RIGOR_PROFILE_VALUES[3]}"
  STATISTICAL_RIGOR_TARGET_REQUEST_NAME="${STATISTICAL_RIGOR_PROFILE_VALUES[4]}"
  STATISTICAL_RIGOR_FALLBACK_TO_AGGREGATED="${STATISTICAL_RIGOR_PROFILE_VALUES[5]}"
  STATISTICAL_RIGOR_REQUIRED_REPLICA_COUNT="${STATISTICAL_RIGOR_PROFILE_VALUES[6]}"
  STATISTICAL_RIGOR_MINIMUM_SUCCESSFUL_REPLICA_COUNT="${STATISTICAL_RIGOR_PROFILE_VALUES[7]}"
  STATISTICAL_RIGOR_COOLDOWN_BETWEEN_REPLICAS_SECONDS="${STATISTICAL_RIGOR_PROFILE_VALUES[8]}"
  STATISTICAL_RIGOR_COOLDOWN_BETWEEN_SCENARIOS_SECONDS="${STATISTICAL_RIGOR_PROFILE_VALUES[9]}"
  STATISTICAL_RIGOR_STABILIZATION_TIMEOUT_SECONDS="${STATISTICAL_RIGOR_PROFILE_VALUES[10]}"
  STATISTICAL_RIGOR_STABILIZATION_POLL_INTERVAL_SECONDS="${STATISTICAL_RIGOR_PROFILE_VALUES[11]}"
  STATISTICAL_RIGOR_SUMMARY_MANIFEST_SUFFIX="${STATISTICAL_RIGOR_PROFILE_VALUES[12]}"
  STATISTICAL_RIGOR_SUMMARY_TEXT_SUFFIX="${STATISTICAL_RIGOR_PROFILE_VALUES[13]}"
  STATISTICAL_RIGOR_TRACKED_METRICS_JSON="${STATISTICAL_RIGOR_PROFILE_VALUES[14]}"
  STATISTICAL_RIGOR_VARIABILITY_THRESHOLDS_JSON="${STATISTICAL_RIGOR_PROFILE_VALUES[15]}"
}

statistical_rigor_find_measurement_stats() {
  local search_root="$1"
  local scenario="$2"
  local replica="$3"
  local min_mtime_epoch="${4:-}"
  local expected_file="${scenario}_run${replica}_stats.csv"
  local python_cmd
  python_cmd="$(statistical_rigor_require_python_command)"

  "$python_cmd" - "$search_root" "$expected_file" "$min_mtime_epoch" <<"PY"
import sys
from pathlib import Path

search_root = Path(sys.argv[1])
expected_file = sys.argv[2]
min_mtime_epoch = sys.argv[3].strip()
threshold = float(min_mtime_epoch) if min_mtime_epoch else None

if not search_root.exists():
    sys.exit(0)

matches = []
for path in search_root.rglob(expected_file):
    if not path.is_file():
        continue
    try:
        mtime = path.stat().st_mtime
    except OSError:
        continue
    if threshold is not None and mtime < threshold:
        continue
    matches.append((mtime, str(path)))

if matches:
    matches.sort(key=lambda item: (-item[0], item[1]))
    print(matches[0][1])
PY
}

statistical_rigor_build_entry_json() {
  local family_name="$1"
  local scenario="$2"
  local replica="$3"
  local status="$4"
  local exit_code="$5"
  local command_text="$6"
  local stats_csv_path="$7"
  local python_cmd
  python_cmd="$(statistical_rigor_require_python_command)"

  "$python_cmd" - "$family_name" "$scenario" "$replica" "$status" "$exit_code" "$command_text" "$stats_csv_path" <<'PY'
import json
import sys

payload = {
    "family": sys.argv[1],
    "scenario": sys.argv[2],
    "replica": sys.argv[3],
    "status": sys.argv[4],
    "exitCode": int(sys.argv[5]),
    "command": sys.argv[6],
    "statsCsvPath": sys.argv[7],
}
print(json.dumps(payload, separators=(",", ":")))
PY
}

statistical_rigor_summarize_campaign() {
  local entries_file="$1"
  local output_manifest_path="$2"
  local output_text_path="$3"
  local campaign_id="$4"
  local family_scope="$5"
  local created_at_utc="$6"
  local python_cmd
  python_cmd="$(statistical_rigor_require_python_command)"

  "$python_cmd" - \
    "$STATISTICAL_RIGOR_PROFILE_FILE_RESOLVED" \
    "$STATISTICAL_RIGOR_PROFILE_ID" \
    "$STATISTICAL_RIGOR_DESCRIPTION" \
    "$STATISTICAL_RIGOR_TARGET_REQUEST_TYPE" \
    "$STATISTICAL_RIGOR_TARGET_REQUEST_NAME" \
    "$STATISTICAL_RIGOR_FALLBACK_TO_AGGREGATED" \
    "$STATISTICAL_RIGOR_REQUIRED_REPLICA_COUNT" \
    "$STATISTICAL_RIGOR_MINIMUM_SUCCESSFUL_REPLICA_COUNT" \
    "$STATISTICAL_RIGOR_TRACKED_METRICS_JSON" \
    "$STATISTICAL_RIGOR_VARIABILITY_THRESHOLDS_JSON" \
    "$entries_file" \
    "$output_manifest_path" \
    "$output_text_path" \
    "$campaign_id" \
    "$family_scope" \
    "$created_at_utc" <<'PY'
import csv
import json
import math
import statistics
import sys
from pathlib import Path

(
    profile_file,
    profile_id,
    description,
    target_request_type,
    target_request_name,
    fallback_to_aggregated,
    required_replica_count,
    minimum_successful_replica_count,
    tracked_metrics_json,
    variability_thresholds_json,
    entries_file,
    output_manifest_path,
    output_text_path,
    campaign_id,
    family_scope,
    created_at_utc,
) = sys.argv[1:17]

required_replica_count = int(required_replica_count)
minimum_successful_replica_count = int(minimum_successful_replica_count)
fallback_to_aggregated = fallback_to_aggregated.lower() == "true"
tracked_metrics = json.loads(tracked_metrics_json)
variability_thresholds = json.loads(variability_thresholds_json)

entries = []
with Path(entries_file).open("r", encoding="utf-8-sig") as fh:
    for line in fh:
        line = line.strip()
        if line:
            entries.append(json.loads(line))

metric_key_map = {
    "request_count": "Request Count",
    "failure_count": "Failure Count",
    "mean_response_time_ms": "Average Response Time",
    "p50_response_time_ms": "50%",
    "p95_response_time_ms": "95%",
    "p99_response_time_ms": "99%",
    "throughput_rps": "Requests/s",
}

def to_number(value):
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def read_target_row(stats_csv_path: Path):
    if not stats_csv_path.exists():
        return None

    with stats_csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    target_row = None
    aggregated_row = None
    for row in rows:
        row_type = (row.get("Type") or "").strip()
        row_name = (row.get("Name") or "").strip()
        if row_type == target_request_type and row_name == target_request_name:
            target_row = row
            break
        if row_name == "Aggregated":
            aggregated_row = row

    if target_row is not None:
        return target_row, "target_request"
    if fallback_to_aggregated and aggregated_row is not None:
        return aggregated_row, "aggregated_fallback"
    return None

scenario_groups = {}
for entry in entries:
    key = (entry["family"], entry["scenario"])
    scenario_groups.setdefault(key, []).append(entry)

scenario_summaries = []
text_lines = []
text_lines.append("=============================================")
text_lines.append(" Statistical Rigor Summary")
text_lines.append("=============================================")
text_lines.append(f"Profile               : {profile_file}")
text_lines.append(f"Profile ID            : {profile_id}")
text_lines.append(f"Campaign ID           : {campaign_id}")
text_lines.append(f"Family scope          : {family_scope}")
text_lines.append(f"Created at UTC        : {created_at_utc}")
text_lines.append("")

for (family_name, scenario_name) in sorted(scenario_groups.keys()):
    group_entries = sorted(scenario_groups[(family_name, scenario_name)], key=lambda item: item["replica"])
    successful = []
    replica_rows = []

    for entry in group_entries:
        stats_path = Path(entry.get("statsCsvPath") or "")
        target = None
        source = None
        if entry["status"] == "success" and stats_path:
            result = read_target_row(stats_path)
            if result is not None:
                target, source = result

        replica_metrics = {}
        if target is not None:
            for metric_name in tracked_metrics:
                replica_metrics[metric_name] = to_number(target.get(metric_key_map[metric_name], 0))
            successful.append(replica_metrics)

        replica_rows.append({
            "replica": entry["replica"],
            "status": entry["status"],
            "exitCode": int(entry["exitCode"]),
            "statsCsvPath": str(stats_path) if stats_path else "",
            "metricSource": source,
            "metrics": replica_metrics,
        })

    aggregate = {}
    flags = []
    for metric_name in tracked_metrics:
        values = [row[metric_name] for row in successful if metric_name in row]
        if values:
            mean_value = statistics.fmean(values)
            stdev_value = statistics.stdev(values) if len(values) > 1 else 0.0
            cv_percent = 0.0 if mean_value == 0 else (stdev_value / mean_value) * 100.0
            aggregate[metric_name] = {
                "mean": mean_value,
                "min": min(values),
                "max": max(values),
                "stdev": stdev_value,
                "cvPercent": cv_percent,
            }
        else:
            aggregate[metric_name] = None

    successful_count = len(successful)
    if successful_count < minimum_successful_replica_count:
        flags.append({
            "code": "INSUFFICIENT_SUCCESSFUL_REPLICAS",
            "message": f"Successful replicas {successful_count} below minimum {minimum_successful_replica_count}."
        })

    mean_cv_threshold = variability_thresholds.get("mean_response_time_cv_percent")
    if aggregate.get("mean_response_time_ms") and mean_cv_threshold is not None:
        if aggregate["mean_response_time_ms"]["cvPercent"] > float(mean_cv_threshold):
            flags.append({
                "code": "HIGH_VARIABILITY_MEAN_RESPONSE_TIME",
                "message": f"Mean response time CV {aggregate['mean_response_time_ms']['cvPercent']:.2f}% above threshold {float(mean_cv_threshold):.2f}%.",
            })

    p95_cv_threshold = variability_thresholds.get("p95_response_time_cv_percent")
    if aggregate.get("p95_response_time_ms") and p95_cv_threshold is not None:
        if aggregate["p95_response_time_ms"]["cvPercent"] > float(p95_cv_threshold):
            flags.append({
                "code": "HIGH_VARIABILITY_P95_RESPONSE_TIME",
                "message": f"P95 response time CV {aggregate['p95_response_time_ms']['cvPercent']:.2f}% above threshold {float(p95_cv_threshold):.2f}%.",
            })

    throughput_cv_threshold = variability_thresholds.get("throughput_cv_percent")
    if aggregate.get("throughput_rps") and throughput_cv_threshold is not None:
        if aggregate["throughput_rps"]["cvPercent"] > float(throughput_cv_threshold):
            flags.append({
                "code": "HIGH_VARIABILITY_THROUGHPUT",
                "message": f"Throughput CV {aggregate['throughput_rps']['cvPercent']:.2f}% above threshold {float(throughput_cv_threshold):.2f}%.",
            })

    scenario_summary = {
        "family": family_name,
        "scenario": scenario_name,
        "requiredReplicaCount": required_replica_count,
        "minimumSuccessfulReplicaCount": minimum_successful_replica_count,
        "observedReplicaCount": len(group_entries),
        "successfulReplicaCount": successful_count,
        "replicas": replica_rows,
        "aggregate": aggregate,
        "flags": flags,
    }
    scenario_summaries.append(scenario_summary)

    text_lines.append(f"Family/Scenario       : {family_name}/{scenario_name}")
    text_lines.append(f"Observed replicas     : {len(group_entries)}")
    text_lines.append(f"Successful replicas   : {successful_count}")
    for metric_name in tracked_metrics:
        metric_agg = aggregate.get(metric_name)
        if metric_agg is not None:
            text_lines.append(
                f" - {metric_name}: mean={metric_agg['mean']:.4f} min={metric_agg['min']:.4f} max={metric_agg['max']:.4f} stdev={metric_agg['stdev']:.4f} cv%={metric_agg['cvPercent']:.2f}"
            )
    if flags:
        for flag in flags:
            text_lines.append(f" ! {flag['code']}: {flag['message']}")
    else:
        text_lines.append(" Flags                : none")
    text_lines.append("")

overall_status = "passed"
if any(summary["flags"] for summary in scenario_summaries):
    overall_status = "warning"
if any(summary["successfulReplicaCount"] < minimum_successful_replica_count for summary in scenario_summaries):
    overall_status = "failed"

payload = {
    "statisticalRigorProfile": {
        "profileFile": profile_file,
        "profileId": profile_id,
        "description": description,
        "targetRequestType": target_request_type,
        "targetRequestName": target_request_name,
        "fallbackToAggregated": fallback_to_aggregated,
        "trackedMetrics": tracked_metrics,
        "variabilityThresholds": variability_thresholds,
    },
    "campaign": {
        "campaignId": campaign_id,
        "familyScope": family_scope,
        "createdAtUtc": created_at_utc,
        "status": overall_status,
    },
    "scenarioSummaries": scenario_summaries,
}

Path(output_manifest_path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8-sig")
Path(output_text_path).write_text("\n".join(text_lines) + "\n", encoding="utf-8-sig")
PY
}
