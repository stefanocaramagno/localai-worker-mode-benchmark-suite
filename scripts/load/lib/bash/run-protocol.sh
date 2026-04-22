#!/usr/bin/env bash
set -euo pipefail

protocol_require_python_command() {
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

protocol_load_profile() {
  local profile_file="$1"
  local python_cmd
  python_cmd="$(protocol_require_python_command)"

  mapfile -t PROTOCOL_PROFILE_VALUES < <("$python_cmd" - "$profile_file" <<'PY'
import json
import sys
from pathlib import Path

profile_path = Path(sys.argv[1])
required = [
    "profileId",
    "description",
    "apiSmokeEnabledDefault",
    "apiSmokeScriptRelativePathBash",
    "apiSmokeScriptRelativePathPowerShell",
    "protocolManifestSuffix",
    "protocolTextSuffix",
    "steps",
]
with profile_path.open("r", encoding="utf-8-sig") as fh:
    data = json.load(fh)
missing = [key for key in required if key not in data]
if missing:
    print(
        f"Il file di protocollo '{profile_path}' non contiene le proprietà obbligatorie: {', '.join(missing)}.",
        file=sys.stderr,
    )
    sys.exit(1)
print(str(profile_path))
print(str(data["profileId"]))
print(str(data["description"]))
print(str(data["apiSmokeEnabledDefault"]).lower())
print(str(data["apiSmokeScriptRelativePathBash"]))
print(str(data["apiSmokeScriptRelativePathPowerShell"]))
print(str(data["protocolManifestSuffix"]))
print(str(data["protocolTextSuffix"]))
print(json.dumps(data["steps"], separators=(",", ":")))
PY
)

  PROTOCOL_PROFILE_FILE_RESOLVED="${PROTOCOL_PROFILE_VALUES[0]}"
  PROTOCOL_PROFILE_ID="${PROTOCOL_PROFILE_VALUES[1]}"
  PROTOCOL_PROFILE_DESCRIPTION="${PROTOCOL_PROFILE_VALUES[2]}"
  PROTOCOL_API_SMOKE_ENABLED_DEFAULT="${PROTOCOL_PROFILE_VALUES[3]}"
  PROTOCOL_API_SMOKE_SCRIPT_BASH_REL="${PROTOCOL_PROFILE_VALUES[4]}"
  PROTOCOL_API_SMOKE_SCRIPT_POWERSHELL_REL="${PROTOCOL_PROFILE_VALUES[5]}"
  PROTOCOL_MANIFEST_SUFFIX="${PROTOCOL_PROFILE_VALUES[6]}"
  PROTOCOL_TEXT_SUFFIX="${PROTOCOL_PROFILE_VALUES[7]}"
  PROTOCOL_STEPS_JSON="${PROTOCOL_PROFILE_VALUES[8]}"
}

protocol_resolve_paths() {
  local measurement_csv_prefix="$1"
  PROTOCOL_MANIFEST_PATH="${measurement_csv_prefix}${PROTOCOL_MANIFEST_SUFFIX}"
  PROTOCOL_TEXT_PATH="${measurement_csv_prefix}${PROTOCOL_TEXT_SUFFIX}"
}

protocol_quote_command() {
  local parts=()
  local quoted_arg=""

  for arg in "$@"; do
    printf -v quoted_arg '%q' "$arg"
    parts+=("$quoted_arg")
  done

  local IFS=' '
  printf '%s' "${parts[*]}"
}

protocol_json_array_from_lines() {
  local python_cmd
  python_cmd="$(protocol_require_python_command)"
  "$python_cmd" - "$@" <<'PY'
import json
import sys
print(json.dumps(sys.argv[1:], separators=(",", ":")))
PY
}

protocol_write_files() {
  local output_json_path="$1"
  local output_text_path="$2"
  local launcher_name="$3"
  local run_id="$4"
  local cleanup_note="$5"
  local deploy_order_json="$6"
  local precheck_enabled="$7"
  local precheck_command="$8"
  local precheck_json_path="$9"
  local precheck_text_path="${10}"
  local api_smoke_enabled="${11}"
  local api_smoke_command="${12}"
  local api_smoke_model="${13}"
  local warmup_enabled="${14}"
  local warmup_command="${15}"
  local warmup_csv_prefix="${16}"
  local measurement_command="${17}"
  local measurement_csv_prefix="${18}"
  local phase_manifest_path="${19}"
  local extra_artifacts_json="${20}"
  local cluster_collection_enabled="${21}"
  local cluster_collection_command="${22}"
  local cluster_collection_artifacts_json="${23}"
  local final_snapshot_enabled="${24}"
  local final_snapshot_command="${25}"
  local final_snapshot_artifacts_json="${26}"

  local python_cmd
  python_cmd="$(protocol_require_python_command)"

  "$python_cmd" - "$output_json_path" "$output_text_path" \
    "$PROTOCOL_PROFILE_FILE_RESOLVED" "$PROTOCOL_PROFILE_ID" "$PROTOCOL_PROFILE_DESCRIPTION" "$PROTOCOL_STEPS_JSON" \
    "$launcher_name" "$run_id" "$cleanup_note" "$deploy_order_json" \
    "$precheck_enabled" "$precheck_command" "$precheck_json_path" "$precheck_text_path" \
    "$api_smoke_enabled" "$api_smoke_command" "$api_smoke_model" \
    "$warmup_enabled" "$warmup_command" "$warmup_csv_prefix" \
    "$measurement_command" "$measurement_csv_prefix" "$phase_manifest_path" "$extra_artifacts_json" \
    "$cluster_collection_enabled" "$cluster_collection_command" "$cluster_collection_artifacts_json" \
    "$final_snapshot_enabled" "$final_snapshot_command" "$final_snapshot_artifacts_json" <<'PY'
import json
import sys
from pathlib import Path

output_json_path = Path(sys.argv[1])
output_text_path = Path(sys.argv[2])
profile_file = sys.argv[3]
profile_id = sys.argv[4]
description = sys.argv[5]
steps = json.loads(sys.argv[6])
launcher_name = sys.argv[7]
run_id = sys.argv[8]
cleanup_note = sys.argv[9]
deploy_order = json.loads(sys.argv[10])
precheck_enabled = sys.argv[11].lower() == "true"
precheck_command = sys.argv[12]
precheck_json = sys.argv[13]
precheck_text = sys.argv[14]
api_smoke_enabled = sys.argv[15].lower() == "true"
api_smoke_command = sys.argv[16]
api_smoke_model = sys.argv[17]
warmup_enabled = sys.argv[18].lower() == "true"
warmup_command = sys.argv[19]
warmup_csv_prefix = sys.argv[20]
measurement_command = sys.argv[21]
measurement_csv_prefix = sys.argv[22]
phase_manifest_path = sys.argv[23]
extra_artifacts = json.loads(sys.argv[24])
cluster_collection_enabled = sys.argv[25].lower() == "true"
cluster_collection_command = sys.argv[26]
cluster_collection_artifacts = json.loads(sys.argv[27])
final_snapshot_enabled = sys.argv[28].lower() == "true"
final_snapshot_command = sys.argv[29]
final_snapshot_artifacts = json.loads(sys.argv[30])

client_artifacts = []
if warmup_enabled and warmup_csv_prefix:
    client_artifacts.extend([
        f"{warmup_csv_prefix}_stats.csv",
        f"{warmup_csv_prefix}_stats_history.csv",
        f"{warmup_csv_prefix}_failures.csv",
        f"{warmup_csv_prefix}_exceptions.csv",
    ])
client_artifacts.extend([
    f"{measurement_csv_prefix}_stats.csv",
    f"{measurement_csv_prefix}_stats_history.csv",
    f"{measurement_csv_prefix}_failures.csv",
    f"{measurement_csv_prefix}_exceptions.csv",
])

payload = {
    "protocolProfile": {
        "profileFile": profile_file,
        "profileId": profile_id,
        "description": description,
        "steps": steps,
    },
    "launcher": launcher_name,
    "runId": run_id,
    "steps": {
        "cleanupControlled": {
            "required": True,
            "mode": "manual",
            "note": cleanup_note,
        },
        "deployScenario": {
            "required": True,
            "mode": "manual",
            "recommendedApplyOrder": deploy_order,
        },
        "technicalPrecheck": {
            "enabled": precheck_enabled,
            "mode": "automated",
            "command": precheck_command,
            "artifacts": {"json": precheck_json, "text": precheck_text},
        },
        "apiSmokeValidation": {
            "enabled": api_smoke_enabled,
            "mode": "automated",
            "command": api_smoke_command,
            "model": api_smoke_model,
        },
        "warmUp": {
            "enabled": warmup_enabled,
            "mode": "automated_optional",
            "command": warmup_command,
            "csvPrefix": warmup_csv_prefix,
        },
        "measurement": {
            "enabled": True,
            "mode": "automated",
            "command": measurement_command,
            "csvPrefix": measurement_csv_prefix,
        },
        "collectClientMetrics": {
            "enabled": True,
            "mode": "automatic_artifact",
            "artifacts": client_artifacts,
        },
        "collectClusterMetrics": {
            "enabled": cluster_collection_enabled,
            "mode": "automated_required",
            "command": cluster_collection_command,
            "artifacts": cluster_collection_artifacts,
        },
        "finalSnapshot": {
            "enabled": final_snapshot_enabled,
            "mode": "automated_required",
            "command": final_snapshot_command,
            "artifacts": final_snapshot_artifacts,
        },
        "cleanupOrRestore": {
            "enabled": False,
            "mode": "manual_placeholder",
            "note": "Placeholder for controlled cleanup or restore to baseline state.",
        },
    },
    "artifacts": {
        "phaseManifest": phase_manifest_path,
        "extra": extra_artifacts,
    },
}

output_json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8-sig")

lines = []
lines.append("=============================================")
lines.append(" Standard Execution Protocol")
lines.append("=============================================")
lines.append(f"Protocol profile : {profile_id}")
lines.append(f"Description      : {description}")
lines.append(f"Launcher         : {launcher_name}")
lines.append(f"Run ID           : {run_id}")
lines.append("")
lines.append("[S01] cleanup_controlled")
lines.append(f"  Note: {cleanup_note}")
lines.append("")
lines.append("[S02] deploy_scenario")
if deploy_order:
    lines.append("  Recommended apply order:")
    for item in deploy_order:
        lines.append(f"   - {item}")
else:
    lines.append("  Recommended apply order: not applicable for this launcher.")
lines.append("")
lines.append("[S03] technical_precheck")
lines.append(f"  Enabled: {str(precheck_enabled).lower()}")
if precheck_enabled:
    lines.append(f"  Command: {precheck_command}")
    lines.append(f"  JSON artifact: {precheck_json}")
    lines.append(f"  Text artifact: {precheck_text}")
lines.append("")
lines.append("[S04] api_smoke_validation")
lines.append(f"  Enabled: {str(api_smoke_enabled).lower()}")
if api_smoke_enabled:
    lines.append(f"  Command: {api_smoke_command}")
    lines.append(f"  Model: {api_smoke_model}")
lines.append("")
lines.append("[S05] warm_up")
lines.append(f"  Enabled: {str(warmup_enabled).lower()}")
if warmup_enabled:
    lines.append(f"  Command: {warmup_command}")
    lines.append(f"  CSV prefix: {warmup_csv_prefix}")
lines.append("")
lines.append("[S06] measurement")
lines.append(f"  Command: {measurement_command}")
lines.append(f"  CSV prefix: {measurement_csv_prefix}")
lines.append("")
lines.append("[S07] collect_client_metrics")
for artifact in client_artifacts:
    lines.append(f"   - {artifact}")
lines.append("")
lines.append("[S08] collect_cluster_metrics")
lines.append(f"  Enabled: {str(cluster_collection_enabled).lower()}")
if cluster_collection_enabled:
    lines.append(f"  Command: {cluster_collection_command}")
    for artifact in cluster_collection_artifacts:
        lines.append(f"   - {artifact}")
lines.append("")
lines.append("[S09] final_snapshot")
lines.append(f"  Enabled: {str(final_snapshot_enabled).lower()}")
if final_snapshot_enabled:
    lines.append(f"  Command: {final_snapshot_command}")
    for artifact in final_snapshot_artifacts:
        lines.append(f"   - {artifact}")
lines.append("")
lines.append("[S10] cleanup_or_restore")
lines.append("  Placeholder: apply controlled cleanup or restore policy.")
lines.append("")
lines.append(f"Phase manifest: {phase_manifest_path}")
if extra_artifacts:
    lines.append("Extra artifacts:")
    for artifact in extra_artifacts:
        lines.append(f" - {artifact}")
output_text_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
PY
}
