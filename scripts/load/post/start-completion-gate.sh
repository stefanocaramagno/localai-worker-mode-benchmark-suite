#!/usr/bin/env bash
set -euo pipefail

PROFILE_CONFIG=""
DIAGNOSIS_JSON=""
OUTPUT_ROOT=""
RESULTS_ROOT=""
DRY_RUN=false

print_usage() {
  cat <<'USAGE'
Usage:
  ./start-completion-gate.sh [options]

Options:
  --profile-config PATH | -ProfileConfig PATH
  --diagnosis-json PATH | -DiagnosisJson PATH
  --output-root PATH | -OutputRoot PATH
  --results-root PATH | -ResultsRoot PATH
  --dry-run | -DryRun
  --help | -Help
USAGE
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Errore: il comando richiesto non è disponibile nel PATH: $cmd" >&2
    exit 1
  fi
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
  echo "Nessun interprete Python compatibile e disponibile nel PATH. Verificare la disponibilita' di 'python' oppure 'python3'." >&2
  exit 1
}

resolve_repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd -- "$script_dir/../../.." && pwd
}

find_latest_all_diagnosis() {
  local repo_root="$1"
  $PYTHON_CMD - <<'PY' "$repo_root"
import json
import sys
from pathlib import Path
repo_root = Path(sys.argv[1])
candidates = []
for path in (repo_root / "results" / "diagnosis").glob("*_diagnosis.json"):
    try:
        with path.open("r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        family_scope = data.get("diagnosis", {}).get("familyScope")
        if family_scope == "all":
            candidates.append(path)
    except Exception:
        continue
if not candidates:
    sys.exit(1)
latest = max(candidates, key=lambda p: p.stat().st_mtime)
print(str(latest))
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-config|-ProfileConfig)
      PROFILE_CONFIG="$2"
      shift 2
      ;;
    --diagnosis-json|-DiagnosisJson)
      DIAGNOSIS_JSON="$2"
      shift 2
      ;;
    --output-root|-OutputRoot)
      OUTPUT_ROOT="$2"
      shift 2
      ;;
    --results-root|-ResultsRoot)
      RESULTS_ROOT="$2"
      shift 2
      ;;
    --dry-run|-DryRun)
      DRY_RUN=true
      shift
      ;;
    --help|-Help)
      print_usage
      exit 0
      ;;
    *)
      echo "Argomento non riconosciuto: $1" >&2
      print_usage >&2
      exit 1
      ;;
  esac
done

PYTHON_CMD="$(resolve_python_command)"
REPO_ROOT="$(resolve_repo_root)"
source "$REPO_ROOT/scripts/load/lib/bash/run-convention.sh"

if [[ -n "$RESULTS_ROOT" ]]; then
  REPO_ROOT="$RESULTS_ROOT"
fi

if [[ -z "$PROFILE_CONFIG" ]]; then
  PROFILE_CONFIG="$REPO_ROOT/config/completion-gate/CG1.json"
fi

if [[ ! -f "$PROFILE_CONFIG" ]]; then
  echo "Il file di profilo completion gate non esiste: $PROFILE_CONFIG" >&2
  exit 1
fi

if [[ -z "$DIAGNOSIS_JSON" ]]; then
  if ! DIAGNOSIS_JSON="$(find_latest_all_diagnosis "$REPO_ROOT")"; then
    echo "Impossibile individuare automaticamente una diagnosi tecnica 'all' in results/diagnosis." >&2
    exit 1
  fi
fi

if [[ ! -f "$DIAGNOSIS_JSON" ]]; then
  echo "Il file di diagnosi non esiste: $DIAGNOSIS_JSON" >&2
  exit 1
fi

OUTPUT_ROOT_REL="$($PYTHON_CMD - <<'PY' "$PROFILE_CONFIG"
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8-sig') as fh:
    data = json.load(fh)
print(data['outputRoot'])
PY
)"

if [[ -z "$OUTPUT_ROOT" ]]; then
  OUTPUT_ROOT="$REPO_ROOT/$OUTPUT_ROOT_REL"
fi

mkdir -p -- "$OUTPUT_ROOT"
RUN_TIMESTAMP_UTC="$(rc_build_timestamp_utc)"
EVALUATION_ID="$(rc_build_run_id "analysis" "completion-gate" "all" "NA" "$RUN_TIMESTAMP_UTC")"
MANIFEST_SUFFIX="$($PYTHON_CMD - <<'PY' "$PROFILE_CONFIG"
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8-sig') as fh:
    data = json.load(fh)
print(data['manifestSuffix'])
PY
)"
TEXT_SUFFIX="$($PYTHON_CMD - <<'PY' "$PROFILE_CONFIG"
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8-sig') as fh:
    data = json.load(fh)
print(data['textSuffix'])
PY
)"
OUTPUT_JSON="$OUTPUT_ROOT/${EVALUATION_ID}${MANIFEST_SUFFIX}"
OUTPUT_TEXT="$OUTPUT_ROOT/${EVALUATION_ID}${TEXT_SUFFIX}"
PYTHON_SCRIPT="$REPO_ROOT/scripts/analysis/evaluate-completion-gate.py"

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
  echo "Lo script di evaluation non esiste: $PYTHON_SCRIPT" >&2
  exit 1
fi

CMD=(
  "$PYTHON_CMD" "$PYTHON_SCRIPT"
  --profile-config "$PROFILE_CONFIG"
  --diagnosis-json "$DIAGNOSIS_JSON"
  --output-json "$OUTPUT_JSON"
  --output-text "$OUTPUT_TEXT"
  --evaluation-id "$EVALUATION_ID"
)

echo "============================================="
echo " Completion Gate Launcher"
echo "============================================="
echo "Repository            : $REPO_ROOT"
echo "Profile config        : $PROFILE_CONFIG"
echo "Diagnosis JSON        : $DIAGNOSIS_JSON"
echo "Evaluation ID         : $EVALUATION_ID"
echo "Output JSON           : $OUTPUT_JSON"
echo "Output text           : $OUTPUT_TEXT"
echo "Python executable     : $PYTHON_CMD"
echo
printf 'Command               :'
for arg in "${CMD[@]}"; do
  printf ' %q' "$arg"
done
printf '\n\n'

if [[ "$DRY_RUN" == true ]]; then
  echo "DRY RUN completato. Nessuna evaluation eseguita."
  exit 0
fi

"${CMD[@]}"
