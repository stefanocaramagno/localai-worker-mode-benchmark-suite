#!/usr/bin/env bash
set -euo pipefail

cluster_require_python_command() {
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

cluster_load_profile() {
  local profile_file="$1"
  local python_cmd
  python_cmd="$(cluster_require_python_command)"

  mapfile -t CLUSTER_PROFILE_VALUES < <("$python_cmd" - "$profile_file" <<'PY'
import json
import sys
from pathlib import Path

profile_path = Path(sys.argv[1])
required = [
    "profileId",
    "description",
    "collectorScriptRelativePathBash",
    "collectorScriptRelativePathPowerShell",
    "preStageSuffix",
    "postStageSuffix",
    "manifestSuffix",
    "textSuffix",
    "artifacts",
]
with profile_path.open("r", encoding="utf-8-sig") as fh:
    data = json.load(fh)
missing = [key for key in required if key not in data]
if missing:
    print(
        f"Il file di cluster-side collection '{profile_path}' non contiene le proprietà obbligatorie: {', '.join(missing)}.",
        file=sys.stderr,
    )
    sys.exit(1)
print(str(profile_path))
print(str(data["profileId"]))
print(str(data["description"]))
print(str(data["collectorScriptRelativePathBash"]))
print(str(data["collectorScriptRelativePathPowerShell"]))
print(str(data["preStageSuffix"]))
print(str(data["postStageSuffix"]))
print(str(data["manifestSuffix"]))
print(str(data["textSuffix"]))
print(json.dumps(data["artifacts"], separators=(",", ":")))
PY
)

  CLUSTER_PROFILE_FILE_RESOLVED="${CLUSTER_PROFILE_VALUES[0]}"
  CLUSTER_PROFILE_ID="${CLUSTER_PROFILE_VALUES[1]}"
  CLUSTER_PROFILE_DESCRIPTION="${CLUSTER_PROFILE_VALUES[2]}"
  CLUSTER_PROFILE_COLLECTOR_SCRIPT_BASH_REL="${CLUSTER_PROFILE_VALUES[3]}"
  CLUSTER_PROFILE_COLLECTOR_SCRIPT_POWERSHELL_REL="${CLUSTER_PROFILE_VALUES[4]}"
  CLUSTER_PROFILE_PRE_STAGE_SUFFIX="${CLUSTER_PROFILE_VALUES[5]}"
  CLUSTER_PROFILE_POST_STAGE_SUFFIX="${CLUSTER_PROFILE_VALUES[6]}"
  CLUSTER_PROFILE_MANIFEST_SUFFIX="${CLUSTER_PROFILE_VALUES[7]}"
  CLUSTER_PROFILE_TEXT_SUFFIX="${CLUSTER_PROFILE_VALUES[8]}"
  CLUSTER_PROFILE_ARTIFACT_NAMES_JSON="${CLUSTER_PROFILE_VALUES[9]}"
}

cluster_resolve_stage_paths() {
  local measurement_csv_prefix="$1"
  CLUSTER_CAPTURE_PRE_PREFIX="${measurement_csv_prefix}${CLUSTER_PROFILE_PRE_STAGE_SUFFIX}"
  CLUSTER_CAPTURE_POST_PREFIX="${measurement_csv_prefix}${CLUSTER_PROFILE_POST_STAGE_SUFFIX}"
}

cluster_artifacts_json() {
  local stage_prefix="$1"
  local python_cmd
  python_cmd="$(cluster_require_python_command)"

  "$python_cmd" - "$stage_prefix" "$CLUSTER_PROFILE_ARTIFACT_NAMES_JSON" "$CLUSTER_PROFILE_MANIFEST_SUFFIX" "$CLUSTER_PROFILE_TEXT_SUFFIX" <<'PY'
import json
import sys

stage_prefix = sys.argv[1]
artifact_names = json.loads(sys.argv[2])
manifest_suffix = sys.argv[3]
text_suffix = sys.argv[4]
artifacts = [
    f"{stage_prefix}{manifest_suffix}",
    f"{stage_prefix}{text_suffix}",
]
for name in artifact_names:
    artifacts.append(f"{stage_prefix}_{name}")
print(json.dumps(artifacts, separators=(",", ":")))
PY
}
