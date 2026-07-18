#!/usr/bin/env bash
set -euo pipefail

CYCLE_CONFIG=""
APPLICATION_DEPLOYMENT_PROFILE=""
PLACEMENT_PROFILE_ID=""
PLACEMENT_PROFILE_PATH=""
OUTPUT_ROOT=""
RESOLUTION_ID=""
WRITE_LATEST_ALIASES="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cycle-config) CYCLE_CONFIG="$2"; shift 2 ;;
    --application-deployment-profile) APPLICATION_DEPLOYMENT_PROFILE="$2"; shift 2 ;;
    --placement-profile-id) PLACEMENT_PROFILE_ID="$2"; shift 2 ;;
    --placement-profile-path) PLACEMENT_PROFILE_PATH="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --resolution-id) RESOLUTION_ID="$2"; shift 2 ;;
    --write-latest-aliases) WRITE_LATEST_ALIASES="1"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/resolve-placement-profile.py"

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
  echo "Placement profile resolver not found: $PYTHON_SCRIPT" >&2
  exit 1
fi

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Neither python nor python3 is available in PATH." >&2
  exit 1
fi

ARGS=("$PYTHON_SCRIPT" "--repo-root" "$REPO_ROOT")
[[ -n "$CYCLE_CONFIG" ]] && ARGS+=("--cycle-config" "$CYCLE_CONFIG")
[[ -n "$APPLICATION_DEPLOYMENT_PROFILE" ]] && ARGS+=("--application-deployment-profile" "$APPLICATION_DEPLOYMENT_PROFILE")
[[ -n "$PLACEMENT_PROFILE_ID" ]] && ARGS+=("--placement-profile-id" "$PLACEMENT_PROFILE_ID")
[[ -n "$PLACEMENT_PROFILE_PATH" ]] && ARGS+=("--placement-profile-path" "$PLACEMENT_PROFILE_PATH")
[[ -n "$OUTPUT_ROOT" ]] && ARGS+=("--output-root" "$OUTPUT_ROOT")
[[ -n "$RESOLUTION_ID" ]] && ARGS+=("--resolution-id" "$RESOLUTION_ID")
[[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=("--write-latest-aliases")

printf '%s\n' "==============================================="
printf '%s\n' " placement profile resolver"
printf '%s\n' "==============================================="
printf 'Repository : %s\n\n' "$REPO_ROOT"

exec "$PYTHON_BIN" "${ARGS[@]}"
