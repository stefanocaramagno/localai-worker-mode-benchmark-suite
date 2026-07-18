#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
PROFILE_CONFIG="${PROFILE_CONFIG:-config/reporting/profiles/RP_C0_HISTORICAL_FIXED_CLUSTER.json}"
OUTPUT_ROOT_FROM_ENV="${OUTPUT_ROOT:-}"
OUTPUT_ROOT="$OUTPUT_ROOT_FROM_ENV"
REPORTING_ID="${REPORTING_ID:-}"
ARCHIVE="${ARCHIVE:-false}"
ARCHIVE_CURRENT="${ARCHIVE_CURRENT:-false}"
FORCE_ARCHIVE="${FORCE_ARCHIVE:-false}"
SKIP_REPORTING_SITE_UPDATE="${SKIP_REPORTING_SITE_UPDATE:-false}"
UPDATE_REPORTING_SITE="${UPDATE_REPORTING_SITE:-false}"
OUTPUT_ROOT_EXPLICIT="false"
if [[ -n "$OUTPUT_ROOT_FROM_ENV" ]]; then
  OUTPUT_ROOT_EXPLICIT="true"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      REPO_ROOT="$2"
      shift 2
      ;;
    --profile-config)
      PROFILE_CONFIG="$2"
      shift 2
      ;;
    --output-root)
      OUTPUT_ROOT="$2"
      OUTPUT_ROOT_EXPLICIT="true"
      shift 2
      ;;
    --reporting-id)
      REPORTING_ID="$2"
      shift 2
      ;;
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
    --skip-reporting-site-update)
      SKIP_REPORTING_SITE_UPDATE="true"
      shift
      ;;
    --update-reporting-site)
      UPDATE_REPORTING_SITE="true"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

PROFILE_PATH="$PROFILE_CONFIG"
if [[ "$PROFILE_PATH" != /* ]]; then
  PROFILE_PATH="$REPO_ROOT/$PROFILE_PATH"
fi

if [[ ! -f "$PROFILE_PATH" ]]; then
  echo "Reporting profile not found: $PROFILE_PATH" >&2
  exit 1
fi

if [[ -z "$REPORTING_ID" ]] && [[ "$ARCHIVE_CURRENT" != "true" && "$ARCHIVE_CURRENT" != "1" && "$ARCHIVE_CURRENT" != "yes" ]]; then
  REPORTING_PREFIX="$(python - "$PROFILE_PATH" <<'PY_REPORTING_PREFIX'
import json
import sys
with open(sys.argv[1], 'r', encoding='utf-8-sig') as fh:
    data = json.load(fh)
cycle = str(data.get('cycleId') or '').strip()
prefix = str(data.get('reportingIdPrefix') or '').strip()
if not prefix:
    prefix = f"REP_{cycle}" if cycle else "REP_GENERAL"
print(prefix)
PY_REPORTING_PREFIX
)"
  REPORTING_ID="${REPORTING_PREFIX}_$(date -u +%Y%m%dT%H%M%SZ)"
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
UPDATE_REPORTING_SITE_EFFECTIVE="true"
if [[ "$SKIP_REPORTING_SITE_UPDATE" == "true" || "$SKIP_REPORTING_SITE_UPDATE" == "1" || "$SKIP_REPORTING_SITE_UPDATE" == "yes" ]]; then
  UPDATE_REPORTING_SITE_EFFECTIVE="false"
elif [[ "$OUTPUT_ROOT_EXPLICIT" == "true" && "$UPDATE_REPORTING_SITE" != "true" && "$UPDATE_REPORTING_SITE" != "1" && "$UPDATE_REPORTING_SITE" != "yes" ]]; then
  UPDATE_REPORTING_SITE_EFFECTIVE="false"
fi
echo "Update site     : $UPDATE_REPORTING_SITE_EFFECTIVE"
if [[ "$OUTPUT_ROOT_EXPLICIT" == "true" && "$SKIP_REPORTING_SITE_UPDATE" != "true" && "$SKIP_REPORTING_SITE_UPDATE" != "1" && "$SKIP_REPORTING_SITE_UPDATE" != "yes" && "$UPDATE_REPORTING_SITE" != "true" && "$UPDATE_REPORTING_SITE" != "1" && "$UPDATE_REPORTING_SITE" != "yes" ]]; then
  echo "Update reason   : skipped automatically because --output-root/OUTPUT_ROOT points to a non-canonical output location"
fi
echo ""

python "${ARGS[@]}"

if [[ "$UPDATE_REPORTING_SITE_EFFECTIVE" == "true" ]]; then
  echo ""
  echo "Updating reporting site entry point..."
  bash "$REPO_ROOT/scripts/load/post/start-reporting-site.sh" --repo-root "$REPO_ROOT"
fi

echo ""
echo "Reporting completed."
