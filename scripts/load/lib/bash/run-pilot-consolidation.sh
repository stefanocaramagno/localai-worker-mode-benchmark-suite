#!/usr/bin/env bash
set -euo pipefail

pilot_consolidation_require_python_command() {
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

pilot_consolidation_load_profile() {
  local profile_file="$1"
  local python_cmd
  python_cmd="$(pilot_consolidation_require_python_command)"

  mapfile -t PILOT_CONSOLIDATION_PROFILE_VALUES < <("$python_cmd" - "$profile_file" <<'PY'
import json
import sys
from pathlib import Path

profile_path = Path(sys.argv[1])
required = [
    "profileId",
    "description",
    "outputRoot",
    "campaignManifestSuffix",
    "campaignTextSuffix",
    "stopOnFirstFailure",
    "precheckConfig",
    "phaseConfig",
    "protocolConfig",
    "clusterCaptureConfig",
    "metricSetConfig",
    "statisticalRigorConfig",
    "warmUpDuration",
    "measurementDuration",
    "families",
]
with profile_path.open("r", encoding="utf-8-sig") as fh:
    data = json.load(fh)
missing = [key for key in required if key not in data]
if missing:
    print(
        f"Il file di consolidamento '{profile_path}' non contiene le proprietà obbligatorie: {', '.join(missing)}.",
        file=sys.stderr,
    )
    sys.exit(1)
print(str(profile_path))
print(str(data["profileId"]))
print(str(data["description"]))
print(str(data["outputRoot"]))
print(str(data["campaignManifestSuffix"]))
print(str(data["campaignTextSuffix"]))
print(str(data["stopOnFirstFailure"]).lower())
print(str(data["precheckConfig"]))
print(str(data["phaseConfig"]))
print(str(data["protocolConfig"]))
print(str(data["clusterCaptureConfig"]))
print(str(data["metricSetConfig"]))
print(str(data["statisticalRigorConfig"]))
print(str(data["warmUpDuration"]))
print(str(data["measurementDuration"]))
print(json.dumps(data["families"], separators=(",", ":")))
PY
)

  PILOT_CONSOLIDATION_PROFILE_FILE_RESOLVED="${PILOT_CONSOLIDATION_PROFILE_VALUES[0]}"
  PILOT_CONSOLIDATION_PROFILE_ID="${PILOT_CONSOLIDATION_PROFILE_VALUES[1]}"
  PILOT_CONSOLIDATION_DESCRIPTION="${PILOT_CONSOLIDATION_PROFILE_VALUES[2]}"
  PILOT_CONSOLIDATION_OUTPUT_ROOT_REL="${PILOT_CONSOLIDATION_PROFILE_VALUES[3]}"
  PILOT_CONSOLIDATION_MANIFEST_SUFFIX="${PILOT_CONSOLIDATION_PROFILE_VALUES[4]}"
  PILOT_CONSOLIDATION_TEXT_SUFFIX="${PILOT_CONSOLIDATION_PROFILE_VALUES[5]}"
  PILOT_CONSOLIDATION_STOP_ON_FIRST_FAILURE="${PILOT_CONSOLIDATION_PROFILE_VALUES[6]}"
  PILOT_CONSOLIDATION_PRECHECK_CONFIG_REL="${PILOT_CONSOLIDATION_PROFILE_VALUES[7]}"
  PILOT_CONSOLIDATION_PHASE_CONFIG_REL="${PILOT_CONSOLIDATION_PROFILE_VALUES[8]}"
  PILOT_CONSOLIDATION_PROTOCOL_CONFIG_REL="${PILOT_CONSOLIDATION_PROFILE_VALUES[9]}"
  PILOT_CONSOLIDATION_CLUSTER_CAPTURE_CONFIG_REL="${PILOT_CONSOLIDATION_PROFILE_VALUES[10]}"
  PILOT_CONSOLIDATION_METRIC_SET_CONFIG_REL="${PILOT_CONSOLIDATION_PROFILE_VALUES[11]}"
  PILOT_CONSOLIDATION_STATISTICAL_RIGOR_CONFIG_REL="${PILOT_CONSOLIDATION_PROFILE_VALUES[12]}"
  PILOT_CONSOLIDATION_WARM_UP_DURATION="${PILOT_CONSOLIDATION_PROFILE_VALUES[13]}"
  PILOT_CONSOLIDATION_MEASUREMENT_DURATION="${PILOT_CONSOLIDATION_PROFILE_VALUES[14]}"
  PILOT_CONSOLIDATION_FAMILIES_JSON="${PILOT_CONSOLIDATION_PROFILE_VALUES[15]}"
}

pilot_consolidation_load_family() {
  local profile_file="$1"
  local family_name="$2"
  local python_cmd
  python_cmd="$(pilot_consolidation_require_python_command)"

  mapfile -t PILOT_CONSOLIDATION_FAMILY_VALUES < <("$python_cmd" - "$profile_file" "$family_name" <<'PY'
import json
import sys
from pathlib import Path

profile_path = Path(sys.argv[1])
family_name = sys.argv[2]

with profile_path.open("r", encoding="utf-8-sig") as fh:
    data = json.load(fh)

families = data.get("families", {})
if family_name not in families:
    print(f"La famiglia '{family_name}' non è definita nel profilo '{profile_path}'.", file=sys.stderr)
    sys.exit(1)

family = families[family_name]
required = ["launcherBash", "launcherPowerShell", "outputRoot", "scenarios", "replicas"]
missing = [key for key in required if key not in family]
if missing:
    print(
        f"La famiglia '{family_name}' nel profilo '{profile_path}' non contiene le proprietà obbligatorie: {', '.join(missing)}.",
        file=sys.stderr,
    )
    sys.exit(1)

print(str(family["launcherBash"]))
print(str(family["launcherPowerShell"]))
print(str(family["outputRoot"]))
print(json.dumps(family["scenarios"], separators=(",", ":")))
print(json.dumps(family["replicas"], separators=(",", ":")))
PY
)

  PILOT_CONSOLIDATION_FAMILY_LAUNCHER_BASH_REL="${PILOT_CONSOLIDATION_FAMILY_VALUES[0]}"
  PILOT_CONSOLIDATION_FAMILY_LAUNCHER_POWERSHELL_REL="${PILOT_CONSOLIDATION_FAMILY_VALUES[1]}"
  PILOT_CONSOLIDATION_FAMILY_OUTPUT_ROOT_REL="${PILOT_CONSOLIDATION_FAMILY_VALUES[2]}"
  PILOT_CONSOLIDATION_FAMILY_SCENARIOS_JSON="${PILOT_CONSOLIDATION_FAMILY_VALUES[3]}"
  PILOT_CONSOLIDATION_FAMILY_REPLICAS_JSON="${PILOT_CONSOLIDATION_FAMILY_VALUES[4]}"
}

pilot_consolidation_json_array_to_lines() {
  local json_array="$1"
  local python_cmd
  python_cmd="$(pilot_consolidation_require_python_command)"
  "$python_cmd" - "$json_array" <<'PY'
import json
import sys
for item in json.loads(sys.argv[1]):
    print(str(item))
PY
}

pilot_consolidation_write_manifest() {
  local output_path="$1"
  local manifest_json="$2"
  local python_cmd
  python_cmd="$(pilot_consolidation_require_python_command)"

  "$python_cmd" - "$output_path" "$manifest_json" <<'PY'
import json
import sys
from pathlib import Path

output_path = Path(sys.argv[1])
payload = json.loads(sys.argv[2])
output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8-sig")
PY
}

pilot_consolidation_write_text_report() {
  local output_path="$1"
  local text_payload="$2"
  printf '%s\n' "$text_payload" > "$output_path"
}
