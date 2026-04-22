#!/usr/bin/env bash
set -euo pipefail

PROFILE_CONFIG=""
FAMILY="all"
OUTPUT_ROOT=""
RESULTS_ROOT=""
DRY_RUN=false

print_usage() {
  cat <<'USAGE'
Usage:
  ./start-technical-diagnosis.sh [options]

Options:
  --profile-config PATH | -ProfileConfig PATH
  --family worker-count|workload|models|placement|all | -Family VALUE
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

validate_family() {
  case "$1" in
    worker-count|workload|models|placement|all) ;;
    *)
      echo "Famiglia non supportata: $1" >&2
      exit 1
      ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-config|-ProfileConfig)
      PROFILE_CONFIG="$2"
      shift 2
      ;;
    --family|-Family)
      FAMILY="$2"
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

validate_family "$FAMILY"
PYTHON_CMD="$(resolve_python_command)"
REPO_ROOT="$(resolve_repo_root)"
source "$REPO_ROOT/scripts/load/lib/bash/run-convention.sh"

if [[ -n "$RESULTS_ROOT" ]]; then
  REPO_ROOT="$RESULTS_ROOT"
fi

if [[ -z "$PROFILE_CONFIG" ]]; then
  PROFILE_CONFIG="$REPO_ROOT/config/technical-diagnosis/TD1.json"
fi

if [[ ! -f "$PROFILE_CONFIG" ]]; then
  echo "Il file di profilo diagnosi non esiste: $PROFILE_CONFIG" >&2
  exit 1
fi

DIAGNOSIS_OUTPUT_ROOT_REL="$($PYTHON_CMD - <<'PY' "$PROFILE_CONFIG"
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8-sig') as fh:
    data = json.load(fh)
print(data['outputRoot'])
PY
)"

if [[ -z "$OUTPUT_ROOT" ]]; then
  OUTPUT_ROOT="$REPO_ROOT/$DIAGNOSIS_OUTPUT_ROOT_REL"
fi

mkdir -p -- "$OUTPUT_ROOT"
RUN_TIMESTAMP_UTC="$(rc_build_timestamp_utc)"
DIAGNOSIS_ID="$(rc_build_run_id "analysis" "diagnosis" "$FAMILY" "NA" "$RUN_TIMESTAMP_UTC")"
OUTPUT_JSON="$OUTPUT_ROOT/${DIAGNOSIS_ID}_diagnosis.json"
OUTPUT_TEXT="$OUTPUT_ROOT/${DIAGNOSIS_ID}_diagnosis.txt"
PYTHON_SCRIPT="$REPO_ROOT/scripts/analysis/generate-technical-diagnosis.py"

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
  echo "Lo script di diagnosi non esiste: $PYTHON_SCRIPT" >&2
  exit 1
fi

CMD=(
  "$PYTHON_CMD" "$PYTHON_SCRIPT"
  --repo-root "$REPO_ROOT"
  --profile-config "$PROFILE_CONFIG"
  --family "$FAMILY"
  --output-json "$OUTPUT_JSON"
  --output-text "$OUTPUT_TEXT"
  --diagnosis-id "$DIAGNOSIS_ID"
)

echo "============================================="
echo " Initial Technical Diagnosis Launcher"
echo "============================================="
echo "Repository            : $REPO_ROOT"
echo "Profile config        : $PROFILE_CONFIG"
echo "Family scope          : $FAMILY"
echo "Diagnosis ID          : $DIAGNOSIS_ID"
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
  echo "DRY RUN completato. Nessuna diagnosi eseguita."
  exit 0
fi

"${CMD[@]}"
