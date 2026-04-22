#!/usr/bin/env bash
set -euo pipefail

rc_require_python_command() {
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

rc_load_convention() {
  local convention_file="$1"
  local py
  py="$(rc_require_python_command)"

  mapfile -t RC_VALUES < <("$py" - "$convention_file" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
with path.open("r", encoding="utf-8-sig") as fh:
    data = json.load(fh)

convention_id = data.get("conventionId") or data.get("runConventionId")
version = data.get("version")
run_id_pattern = data.get("runIdPattern") or data.get("runIdFormat")
metadata_file_pattern = data.get("metadataFilePattern") or data.get("runManifestSuffix")
csv_prefix_pattern = data.get("csvPrefixPattern") or data.get("csvPrefixFormat")

missing = []
if not convention_id:
    missing.append("conventionId|runConventionId")
if not version:
    missing.append("version")
if not run_id_pattern:
    missing.append("runIdPattern|runIdFormat")
if not metadata_file_pattern:
    missing.append("metadataFilePattern|runManifestSuffix")
if not csv_prefix_pattern:
    missing.append("csvPrefixPattern|csvPrefixFormat")

if missing:
    print(f"Il file di convenzione '{path}' non contiene le proprietà obbligatorie: {', '.join(missing)}.", file=sys.stderr)
    sys.exit(1)

print(str(path))
print(str(convention_id))
print(str(version))
print(str(run_id_pattern))
print(str(metadata_file_pattern))
print(str(csv_prefix_pattern))
PY
)

  RC_FILE_RESOLVED="${RC_VALUES[0]}"
  RC_CONVENTION_ID="${RC_VALUES[1]}"
  RC_CONVENTION_VERSION="${RC_VALUES[2]}"
  RC_RUN_ID_PATTERN="${RC_VALUES[3]}"
  RC_METADATA_FILE_PATTERN="${RC_VALUES[4]}"
  RC_CSV_PREFIX_PATTERN="${RC_VALUES[5]}"
}

rc_validate_component() {
  local component_name="$1"
  local component_value="$2"
  if [[ ! "$component_value" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "Errore: il componente '$component_name' contiene caratteri non ammessi: $component_value" >&2
    exit 1
  fi
}

rc_build_timestamp_utc() {
  date -u +"%Y%m%dT%H%M%SZ"
}

rc_build_run_id() {
  local track="$1"
  local family="$2"
  local scenario="$3"
  local replica="$4"
  local timestamp_utc="$5"

  rc_validate_component "track" "$track"
  rc_validate_component "family" "$family"
  rc_validate_component "scenario" "$scenario"
  rc_validate_component "replica" "$replica"
  rc_validate_component "timestampUtc" "$timestamp_utc"

  printf '%s_%s_%s_%s_%s' "$track" "$family" "$scenario" "$replica" "$timestamp_utc"
}

rc_build_csv_prefix() {
  local output_dir="$1"
  local run_id="$2"
  printf '%s/%s' "$output_dir" "$run_id"
}

rc_build_metadata_path() {
  local csv_prefix="$1"
  printf '%s_run.json' "$csv_prefix"
}

rc_write_run_metadata() {
  local output_path="$1"
  local run_id="$2"
  local created_at_utc="$3"
  local track="$4"
  local family="$5"
  local scenario="$6"
  local replica="$7"
  local output_dir="$8"
  local csv_prefix="$9"
  local context_json="${10}"
  local py
  py="$(rc_require_python_command)"

  "$py" - "$output_path" "$RC_FILE_RESOLVED" "$RC_CONVENTION_ID" "$RC_CONVENTION_VERSION" \
    "$RC_RUN_ID_PATTERN" "$RC_METADATA_FILE_PATTERN" "$RC_CSV_PREFIX_PATTERN" \
    "$run_id" "$created_at_utc" "$track" "$family" "$scenario" "$replica" \
    "$output_dir" "$csv_prefix" "$context_json" <<'PY'
import json
import sys
from pathlib import Path

output_path = Path(sys.argv[1])
context_payload = json.loads(sys.argv[16])
payload = {
    "runConvention": {
        "conventionFile": sys.argv[2],
        "conventionId": sys.argv[3],
        "version": sys.argv[4],
        "runIdPattern": sys.argv[5],
        "metadataFilePattern": sys.argv[6],
        "csvPrefixPattern": sys.argv[7],
    },
    "run": {
        "runId": sys.argv[8],
        "createdAtUtc": sys.argv[9],
        "track": sys.argv[10],
        "family": sys.argv[11],
        "scenario": sys.argv[12],
        "replica": sys.argv[13],
        "outputDir": sys.argv[14],
        "csvPrefix": sys.argv[15],
    },
    "context": context_payload,
}
output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8-sig")
PY
}
