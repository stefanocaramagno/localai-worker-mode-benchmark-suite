#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
PROFILE_CONFIG="${PROFILE_CONFIG:-config/reporting/RP1.json}"
OUTPUT_ROOT="${OUTPUT_ROOT:-}"
REPORTING_ID="${REPORTING_ID:-}"
ARCHIVE="${ARCHIVE:-false}"
ARCHIVE_CURRENT="${ARCHIVE_CURRENT:-false}"
FORCE_ARCHIVE="${FORCE_ARCHIVE:-false}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --archive)
      ARCHIVE="true"
      shift
      ;;
    --archive-current)
      ARCHIVE_CURRENT="true"
      shift
      ;;
    --force-archive)
      FORCE_ARCHIVE="true"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$REPORTING_ID" ]] && [[ "$ARCHIVE_CURRENT" != "true" && "$ARCHIVE_CURRENT" != "1" && "$ARCHIVE_CURRENT" != "yes" ]]; then
  REPORTING_ID="analysis_reporting_all_NA_$(date -u +%Y%m%dT%H%M%SZ)"
fi

PROFILE_PATH="$PROFILE_CONFIG"
if [[ "$PROFILE_PATH" != /* ]]; then
  PROFILE_PATH="$REPO_ROOT/$PROFILE_PATH"
fi

if [[ ! -f "$PROFILE_PATH" ]]; then
  echo "Reporting profile not found: $PROFILE_PATH" >&2
  exit 1
fi

OUTPUT_ROOT_SELECTION_MODE="explicit"
if [[ -z "$OUTPUT_ROOT" ]]; then
  OUTPUT_ROOT_SELECTION_MODE="profile outputRoot"
  OUTPUT_ROOT="$(python - "$PROFILE_PATH" <<'PY_PROFILE_OUTPUT_ROOT'
import json
import sys
with open(sys.argv[1], 'r', encoding='utf-8-sig') as fh:
    data = json.load(fh)
print(data.get('outputRoot', ''))
PY_PROFILE_OUTPUT_ROOT
)"
fi

if [[ -z "$OUTPUT_ROOT" ]]; then
  echo "Reporting output root is not defined. Set outputRoot in the reporting profile or set OUTPUT_ROOT explicitly." >&2
  exit 1
fi

OUTPUT_PATH="$OUTPUT_ROOT"
if [[ "$OUTPUT_PATH" != /* ]]; then
  OUTPUT_PATH="$REPO_ROOT/$OUTPUT_PATH"
fi

ARGS=(
  "$REPO_ROOT/scripts/analysis/generate-reporting.py"
  --repo-root "$REPO_ROOT"
  --profile-config "$PROFILE_PATH"
  --output-root "$OUTPUT_PATH"
)

if [[ -n "$REPORTING_ID" ]]; then
  ARGS+=(--reporting-id "$REPORTING_ID")
fi

if [[ "$ARCHIVE" == "true" || "$ARCHIVE" == "1" || "$ARCHIVE" == "yes" ]]; then
  ARGS+=(--archive)
fi
if [[ "$ARCHIVE_CURRENT" == "true" || "$ARCHIVE_CURRENT" == "1" || "$ARCHIVE_CURRENT" == "yes" ]]; then
  ARGS+=(--archive-current)
fi
if [[ "$FORCE_ARCHIVE" == "true" || "$FORCE_ARCHIVE" == "1" || "$FORCE_ARCHIVE" == "yes" ]]; then
  ARGS+=(--force-archive)
fi

echo "============================================="
echo " LocalAI Reporting and Visualization Launcher"
echo "============================================="
echo "Repository   : $REPO_ROOT"
echo "Profile      : $PROFILE_PATH"
echo "Output root  : $OUTPUT_PATH"
echo "Output source: $OUTPUT_ROOT_SELECTION_MODE"
echo "Reporting ID : ${REPORTING_ID:-current manifest}"
echo "Archive copy : $ARCHIVE"
echo "Archive current : $ARCHIVE_CURRENT"
echo "Force archive   : $FORCE_ARCHIVE"
echo ""

python "${ARGS[@]}"

echo ""
echo "Reporting phase completed."
