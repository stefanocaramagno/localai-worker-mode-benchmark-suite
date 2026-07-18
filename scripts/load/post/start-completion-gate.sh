#!/usr/bin/env bash
set -euo pipefail

PROFILE_CONFIG=""
CYCLE_CONFIG=""
DIAGNOSIS_JSON=""
OUTPUT_ROOT=""
REPOSITORY_ROOT=""
EVALUATION_ID=""
DRY_RUN="0"

print_usage() {
  cat <<'USAGE'
Usage:
  ./start-completion-gate.sh [options]

Options:
  --profile-config PATH | -ProfileConfig PATH
  --cycle-config PATH | -CycleConfig PATH
  --diagnosis-json PATH | -DiagnosisJson PATH
  --output-root PATH | -OutputRoot PATH
  --repository-root PATH | -RepositoryRoot PATH
  --evaluation-id VALUE | -EvaluationId VALUE
  --dry-run | -DryRun
  --help | -Help
USAGE
}

resolve_python_command() {
  if command -v python >/dev/null 2>&1 && python --version >/dev/null 2>&1; then
    printf '%s\n' python
    return 0
  fi
  if command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; then
    printf '%s\n' python3
    return 0
  fi
  echo "No compatible Python interpreter found in PATH. Expected 'python' or 'python3'." >&2
  exit 1
}

resolve_repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd -- "$script_dir/../../.." && pwd
}

resolve_profile_from_cycle() {
  local repo_root="$1"
  local cycle_config="$2"
  local py="$3"
  "$py" - "$repo_root" "$cycle_config" <<'PY'
import json
import sys
from pathlib import Path
repo = Path(sys.argv[1])
path = Path(sys.argv[2])
if not path.is_absolute():
    path = repo / path
with path.open('r', encoding='utf-8-sig') as fh:
    cycle = json.load(fh)
value = (
    (cycle.get('completionGate') or {}).get('completionGateProfilePath')
    or (cycle.get('providerBackedInfrastructure') or {}).get('completionGateProfilePath')
    or (cycle.get('pipelineProfiles') or {}).get('completionGate')
    or ''
)
print(value)
PY
}

read_json_value() {
  local file="$1"
  local expression="$2"
  local default_value="$3"
  local py="$4"
  "$py" - "$file" "$expression" "$default_value" <<'PY'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
expr = sys.argv[2]
default = sys.argv[3]
with path.open('r', encoding='utf-8-sig') as fh:
    data = json.load(fh)
cur = data
for part in expr.split('.'):
    if isinstance(cur, dict) and part in cur:
        cur = cur[part]
    else:
        cur = default
        break
print(cur if cur not in [None, ''] else default)
PY
}

find_latest_all_diagnosis() {
  local repo_root="$1"
  local py="$2"
  "$py" - "$repo_root" <<'PY'
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
repo = Path(sys.argv[1])
roots = [repo / 'results' / 'experimental-cycles' / 'C1' / 'diagnosis', repo / 'results' / 'diagnosis']
candidates = []
for root in roots:
    if not root.exists():
        continue
    for path in root.glob('*_diagnosis.json'):
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except Exception:
            continue
        if data.get('diagnosis', {}).get('familyScope') != 'all':
            continue
        created = data.get('diagnosis', {}).get('createdAtUtc')
        score = path.stat().st_mtime
        if created:
            try:
                score = datetime.fromisoformat(created.replace('Z', '+00:00')).timestamp()
            except Exception:
                pass
        else:
            match = re.search(r'(\d{8}T\d{6}Z)', path.name)
            if match:
                try:
                    score = datetime.strptime(match.group(1), '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).timestamp()
                except Exception:
                    pass
        candidates.append((score, path))
if not candidates:
    sys.exit(1)
print(str(max(candidates, key=lambda item: item[0])[1]))
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-config|-ProfileConfig) PROFILE_CONFIG="$2"; shift 2 ;;
    --cycle-config|-CycleConfig) CYCLE_CONFIG="$2"; shift 2 ;;
    --diagnosis-json|-DiagnosisJson) DIAGNOSIS_JSON="$2"; shift 2 ;;
    --output-root|-OutputRoot) OUTPUT_ROOT="$2"; shift 2 ;;
    --repository-root|-RepositoryRoot) REPOSITORY_ROOT="$2"; shift 2 ;;
    --evaluation-id|-EvaluationId) EVALUATION_ID="$2"; shift 2 ;;
    --dry-run|-DryRun) DRY_RUN="1"; shift ;;
    --help|-Help) print_usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; print_usage >&2; exit 1 ;;
  esac
done

PYTHON_CMD="$(resolve_python_command)"
REPO_ROOT="$(resolve_repo_root)"
source "$REPO_ROOT/scripts/load/lib/bash/run-convention.sh"
if [[ -n "$REPOSITORY_ROOT" ]]; then
  REPO_ROOT="$REPOSITORY_ROOT"
fi

if [[ -n "$CYCLE_CONFIG" && -z "$PROFILE_CONFIG" ]]; then
  PROFILE_CONFIG="$(resolve_profile_from_cycle "$REPO_ROOT" "$CYCLE_CONFIG" "$PYTHON_CMD")"
fi

if [[ -z "$PROFILE_CONFIG" ]]; then
  PROFILE_CONFIG="$REPO_ROOT/config/completion-gate/profiles/CG_C0_HISTORICAL_FIXED_CLUSTER.json"
elif [[ "$PROFILE_CONFIG" != /* ]]; then
  PROFILE_CONFIG="$REPO_ROOT/$PROFILE_CONFIG"
fi

if [[ -n "$CYCLE_CONFIG" && "$CYCLE_CONFIG" != /* ]]; then
  CYCLE_CONFIG="$REPO_ROOT/$CYCLE_CONFIG"
fi

if [[ ! -f "$PROFILE_CONFIG" ]]; then
  echo "Completion gate profile not found: $PROFILE_CONFIG" >&2
  exit 1
fi

SCHEMA_VERSION="$(read_json_value "$PROFILE_CONFIG" 'schemaVersion' '' "$PYTHON_CMD")"
if [[ "$SCHEMA_VERSION" != "completion-gate-profile/v1" && -z "$DIAGNOSIS_JSON" ]]; then
  if ! DIAGNOSIS_JSON="$(find_latest_all_diagnosis "$REPO_ROOT" "$PYTHON_CMD")"; then
    echo "Unable to find a technical diagnosis artifact automatically. Provide --diagnosis-json explicitly." >&2
    exit 1
  fi
fi

if [[ -n "$DIAGNOSIS_JSON" && "$DIAGNOSIS_JSON" != /* ]]; then
  DIAGNOSIS_JSON="$REPO_ROOT/$DIAGNOSIS_JSON"
fi
if [[ -n "$DIAGNOSIS_JSON" && ! -f "$DIAGNOSIS_JSON" ]]; then
  echo "Diagnosis JSON not found: $DIAGNOSIS_JSON" >&2
  exit 1
fi

OUTPUT_ROOT_REL="$(read_json_value "$PROFILE_CONFIG" 'outputRoot' 'results/experimental-cycles/C0/completion-gate' "$PYTHON_CMD")"
if [[ -z "$OUTPUT_ROOT" ]]; then
  if [[ "$OUTPUT_ROOT_REL" == /* ]]; then
    OUTPUT_ROOT="$OUTPUT_ROOT_REL"
  else
    OUTPUT_ROOT="$REPO_ROOT/$OUTPUT_ROOT_REL"
  fi
fi
mkdir -p -- "$OUTPUT_ROOT"

if [[ -z "$EVALUATION_ID" ]]; then
  RUN_TIMESTAMP_UTC="$(rc_build_timestamp_utc)"
  EVALUATION_ID="$(rc_build_run_id "analysis" "completion-gate" "all" "NA" "$RUN_TIMESTAMP_UTC")"
fi
MANIFEST_SUFFIX="$(read_json_value "$PROFILE_CONFIG" 'manifestSuffix' '_completion_gate.json' "$PYTHON_CMD")"
TEXT_SUFFIX="$(read_json_value "$PROFILE_CONFIG" 'textSuffix' '_completion_gate.txt' "$PYTHON_CMD")"
OUTPUT_JSON="$OUTPUT_ROOT/${EVALUATION_ID}${MANIFEST_SUFFIX}"
OUTPUT_TEXT="$OUTPUT_ROOT/${EVALUATION_ID}${TEXT_SUFFIX}"
PYTHON_SCRIPT="$REPO_ROOT/scripts/analysis/evaluate-completion-gate.py"

CMD=(
  "$PYTHON_CMD" "$PYTHON_SCRIPT"
  --profile-config "$PROFILE_CONFIG"
  --repo-root "$REPO_ROOT"
  --output-json "$OUTPUT_JSON"
  --output-text "$OUTPUT_TEXT"
  --evaluation-id "$EVALUATION_ID"
)
[[ -n "$CYCLE_CONFIG" ]] && CMD+=(--cycle-config "$CYCLE_CONFIG")
[[ -n "$DIAGNOSIS_JSON" ]] && CMD+=(--diagnosis-json "$DIAGNOSIS_JSON")
[[ "$DRY_RUN" == "1" ]] && CMD+=(--dry-run)

echo "============================================="
echo " Completion Gate Launcher"
echo "============================================="
echo "Repository        : $REPO_ROOT"
echo "Cycle config      : ${CYCLE_CONFIG:-not provided}"
echo "Profile config    : $PROFILE_CONFIG"
echo "Diagnosis JSON    : ${DIAGNOSIS_JSON:-auto-resolved by provider-aware profile}"
echo "Evaluation ID     : $EVALUATION_ID"
echo "Output JSON       : $OUTPUT_JSON"
echo "Output text       : $OUTPUT_TEXT"
echo
printf 'Command           :'
printf ' %q' "${CMD[@]}"
printf '\n\n'

if [[ "$DRY_RUN" == "1" ]]; then
  "${CMD[@]}"
  echo "Dry-run completed."
  exit 0
fi

"${CMD[@]}"
