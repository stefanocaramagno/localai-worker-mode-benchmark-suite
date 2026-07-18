#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
SITE_CONFIG="${SITE_CONFIG:-config/reporting/site/REPORTING_SITE.json}"
REPORTING_INDEX="${REPORTING_INDEX:-}"
OUTPUT_ROOT="${OUTPUT_ROOT:-}"
SITE_ID="${SITE_ID:-}"
STRICT="${STRICT:-false}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      REPO_ROOT="$2"
      shift 2
      ;;
    --site-config)
      SITE_CONFIG="$2"
      shift 2
      ;;
    --reporting-index)
      REPORTING_INDEX="$2"
      shift 2
      ;;
    --output-root)
      OUTPUT_ROOT="$2"
      shift 2
      ;;
    --site-id)
      SITE_ID="$2"
      shift 2
      ;;
    --strict)
      STRICT="true"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

resolve_path() {
  local base="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    echo ""
  elif [[ "$value" = /* ]]; then
    echo "$value"
  else
    echo "$base/$value"
  fi
}

SITE_CONFIG_PATH="$(resolve_path "$REPO_ROOT" "$SITE_CONFIG")"
SCRIPT_PATH="$REPO_ROOT/scripts/analysis/generate-reporting-site.py"

if [[ ! -f "$SITE_CONFIG_PATH" ]]; then
  echo "Reporting-site config not found: $SITE_CONFIG_PATH" >&2
  exit 1
fi
if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "Reporting-site generator not found: $SCRIPT_PATH" >&2
  exit 1
fi

ARGS=(
  "$SCRIPT_PATH"
  --repo-root "$REPO_ROOT"
  --site-config "$SITE_CONFIG_PATH"
)

if [[ -n "$REPORTING_INDEX" ]]; then
  ARGS+=(--reporting-index "$(resolve_path "$REPO_ROOT" "$REPORTING_INDEX")")
fi
if [[ -n "$OUTPUT_ROOT" ]]; then
  ARGS+=(--output-root "$(resolve_path "$REPO_ROOT" "$OUTPUT_ROOT")")
fi
if [[ -n "$SITE_ID" ]]; then
  ARGS+=(--site-id "$SITE_ID")
fi
if [[ "$STRICT" == "true" || "$STRICT" == "1" || "$STRICT" == "yes" ]]; then
  ARGS+=(--strict)
fi

echo "============================================="
echo " LocalAI Reporting Site Launcher"
echo "============================================="
echo "Repository     : $REPO_ROOT"
echo "Site config    : $SITE_CONFIG_PATH"
echo "Reporting index: ${REPORTING_INDEX:-site config default}"
echo "Output root    : ${OUTPUT_ROOT:-site config default}"
echo "Site ID        : ${SITE_ID:-auto-generated}"
echo "Strict mode    : $STRICT"
echo ""

python "${ARGS[@]}"

echo ""
echo "Reporting site completed."
