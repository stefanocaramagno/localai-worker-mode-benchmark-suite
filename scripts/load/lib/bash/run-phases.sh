#!/usr/bin/env bash
set -euo pipefail

phase_require_python_command() {
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
        f"Il file di profilo warm-up/misurazione '{profile_path}' non contiene le proprietà obbligatorie: {', '.join(missing)}.",
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
      echo "Modalità warm-up users non supportata: $PHASE_PROFILE_WARMUP_USERS_MODE" >&2
      exit 1
      ;;
  esac

  case "$PHASE_PROFILE_WARMUP_SPAWN_RATE_MODE" in
    match_measurement)
      PHASE_WARMUP_SPAWN_RATE="$PHASE_MEASUREMENT_SPAWN_RATE"
      ;;
    *)
      echo "Modalità warm-up spawn rate non supportata: $PHASE_PROFILE_WARMUP_SPAWN_RATE_MODE" >&2
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
    "$PHASE_PROFILE_STARTUP_CHECK_MEASUREMENT" "$PHASE_MEASUREMENT_CSV_PREFIX" <<'PY'
import json
import sys
from pathlib import Path

output_path = Path(sys.argv[1])
payload = {
    "phaseProfile": {
        "profileFile": sys.argv[2],
        "profileId": sys.argv[3],
        "description": sys.argv[4],
    },
    "warmUp": {
        "enabled": sys.argv[5].lower() == "true",
        "duration": sys.argv[6],
        "users": int(sys.argv[7]),
        "spawnRate": int(sys.argv[8]),
        "startupModelCheckEnabled": sys.argv[9].lower() == "true",
        "csvPrefix": sys.argv[10],
    },
    "measurement": {
        "duration": sys.argv[11],
        "users": int(sys.argv[12]),
        "spawnRate": int(sys.argv[13]),
        "startupModelCheckEnabled": sys.argv[14].lower() == "true",
        "csvPrefix": sys.argv[15],
    },
}
output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8-sig")
PY
}
