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

phase_require_python_command() {
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

phase_load_profile() {
  local profile_file="$1"
  local python_cmd
  python_cmd="$(phase_require_python_command)"

  mapfile -t PHASE_PROFILE_VALUES < <("$python_cmd" - "$profile_file" <<'PY'
import json
import sys
from pathlib import Path

profile_path = Path(sys.argv[1])
required = [
    "profileId",
    "description",
    "warmUpEnabled",
    "warmUpDuration",
    "warmUpUsersMode",
    "warmUpSpawnRateMode",
    "startupModelCheckDuringWarmUp",
    "startupModelCheckDuringMeasurement",
    "warmUpCsvSuffix",
    "phaseManifestSuffix",
]
with profile_path.open("r", encoding="utf-8-sig") as fh:
    data = json.load(fh)
missing = [key for key in required if key not in data]
if missing:
    print(
        f"The warm-up/measurement profile file '{profile_path}' does not contain the required properties: {', '.join(missing)}.",
        file=sys.stderr,
    )
    sys.exit(1)
print(str(profile_path))
for key in required:
    print(str(data[key]))
PY
)

  PHASE_PROFILE_FILE_RESOLVED="${PHASE_PROFILE_VALUES[0]}"
  PHASE_PROFILE_ID="${PHASE_PROFILE_VALUES[1]}"
  PHASE_PROFILE_DESCRIPTION="${PHASE_PROFILE_VALUES[2]}"
  PHASE_PROFILE_WARMUP_ENABLED="${PHASE_PROFILE_VALUES[3]}"
  PHASE_PROFILE_WARMUP_DURATION="${PHASE_PROFILE_VALUES[4]}"
  PHASE_PROFILE_WARMUP_USERS_MODE="${PHASE_PROFILE_VALUES[5]}"
  PHASE_PROFILE_WARMUP_SPAWN_RATE_MODE="${PHASE_PROFILE_VALUES[6]}"
  PHASE_PROFILE_STARTUP_CHECK_WARMUP="${PHASE_PROFILE_VALUES[7]}"
  PHASE_PROFILE_STARTUP_CHECK_MEASUREMENT="${PHASE_PROFILE_VALUES[8]}"
  PHASE_PROFILE_WARMUP_CSV_SUFFIX="${PHASE_PROFILE_VALUES[9]}"
  PHASE_PROFILE_MANIFEST_SUFFIX="${PHASE_PROFILE_VALUES[10]}"
}

phase_repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd -- "$script_dir/../../../.." && pwd
}

phase_resolve_plan() {
  local measurement_users="$1"
  local measurement_spawn_rate="$2"
  local scenario_measurement_duration="$3"
  local measurement_csv_prefix="$4"
  local warmup_duration_override="${5:-}"
  local measurement_duration_override="${6:-}"
  local skip_warmup="${7:-false}"

  PHASE_MEASUREMENT_USERS="$measurement_users"
  PHASE_MEASUREMENT_SPAWN_RATE="$measurement_spawn_rate"
  PHASE_MEASUREMENT_DURATION="$scenario_measurement_duration"

  if [[ -n "$measurement_duration_override" ]]; then
    PHASE_MEASUREMENT_DURATION="$measurement_duration_override"
  fi

  PHASE_WARMUP_ENABLED_EFFECTIVE="$PHASE_PROFILE_WARMUP_ENABLED"
  if [[ "$skip_warmup" == "true" ]]; then
    PHASE_WARMUP_ENABLED_EFFECTIVE="false"
  fi

  PHASE_WARMUP_DURATION="$PHASE_PROFILE_WARMUP_DURATION"
  if [[ -n "$warmup_duration_override" ]]; then
    PHASE_WARMUP_DURATION="$warmup_duration_override"
  fi

  case "$PHASE_PROFILE_WARMUP_USERS_MODE" in
    match_measurement)
      PHASE_WARMUP_USERS="$PHASE_MEASUREMENT_USERS"
      ;;
    *)
      echo "Unsupported warm-up users mode: $PHASE_PROFILE_WARMUP_USERS_MODE" >&2
      exit 1
      ;;
  esac

  case "$PHASE_PROFILE_WARMUP_SPAWN_RATE_MODE" in
    match_measurement)
      PHASE_WARMUP_SPAWN_RATE="$PHASE_MEASUREMENT_SPAWN_RATE"
      ;;
    *)
      echo "Unsupported warm-up spawn-rate mode: $PHASE_PROFILE_WARMUP_SPAWN_RATE_MODE" >&2
      exit 1
      ;;
  esac

  PHASE_MEASUREMENT_CSV_PREFIX="$measurement_csv_prefix"
  PHASE_WARMUP_CSV_PREFIX="${measurement_csv_prefix}${PHASE_PROFILE_WARMUP_CSV_SUFFIX}"
  PHASE_MANIFEST_PATH="${measurement_csv_prefix}${PHASE_PROFILE_MANIFEST_SUFFIX}"
}

phase_write_manifest() {
  local output_path="$1"
  local python_cmd
  python_cmd="$(phase_require_python_command)"

  "$python_cmd" - "$output_path" \
    "$PHASE_PROFILE_FILE_RESOLVED" "$PHASE_PROFILE_ID" "$PHASE_PROFILE_DESCRIPTION" \
    "$PHASE_WARMUP_ENABLED_EFFECTIVE" "$PHASE_WARMUP_DURATION" "$PHASE_WARMUP_USERS" "$PHASE_WARMUP_SPAWN_RATE" \
    "$PHASE_PROFILE_STARTUP_CHECK_WARMUP" "$PHASE_WARMUP_CSV_PREFIX" \
    "$PHASE_MEASUREMENT_DURATION" "$PHASE_MEASUREMENT_USERS" "$PHASE_MEASUREMENT_SPAWN_RATE" \
    "$PHASE_PROFILE_STARTUP_CHECK_MEASUREMENT" "$PHASE_MEASUREMENT_CSV_PREFIX" "$(phase_repo_root)" <<'PY'
import json
import re
import sys
from pathlib import Path

output_path = Path(sys.argv[1])
repo_root = Path(sys.argv[16]).resolve()

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
    "phaseProfile": {
        "profileFile": repo_relative(sys.argv[2]),
        "profileId": sys.argv[3],
        "description": sys.argv[4],
    },
    "warmUp": {
        "enabled": sys.argv[5].lower() == "true",
        "duration": sys.argv[6],
        "users": int(sys.argv[7]),
        "spawnRate": int(sys.argv[8]),
        "startupModelCheckEnabled": sys.argv[9].lower() == "true",
        "csvPrefix": repo_relative(sys.argv[10]),
    },
    "measurement": {
        "duration": sys.argv[11],
        "users": int(sys.argv[12]),
        "spawnRate": int(sys.argv[13]),
        "startupModelCheckEnabled": sys.argv[14].lower() == "true",
        "csvPrefix": repo_relative(sys.argv[15]),
    },
}
output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8-sig")
PY
  normalize_artifact_file "$output_path"
}
