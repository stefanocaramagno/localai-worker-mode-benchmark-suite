#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="."
CYCLE_CONFIG="config/experimental-cycles/C1.json"
PROFILE_CONFIG=""
FREEZE_ID=""
OUTPUT_ROOT=""
FORCE_FLAG=""
DRY_RUN_FLAG=""
SKIP_COMPLETION_GATE_FLAG=""
WRITE_LATEST_ALIASES_FLAG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      REPO_ROOT="$2"
      shift 2
      ;;
    --cycle-config)
      CYCLE_CONFIG="$2"
      shift 2
      ;;
    --profile-config)
      PROFILE_CONFIG="$2"
      shift 2
      ;;
    --freeze-id)
      FREEZE_ID="$2"
      shift 2
      ;;
    --output-root)
      OUTPUT_ROOT="$2"
      shift 2
      ;;
    --force)
      FORCE_FLAG="--force"
      shift
      ;;
    --dry-run)
      DRY_RUN_FLAG="--dry-run"
      shift
      ;;
    --skip-completion-gate)
      SKIP_COMPLETION_GATE_FLAG="--skip-completion-gate"
      shift
      ;;
    --write-latest-aliases)
      WRITE_LATEST_ALIASES_FLAG="--write-latest-aliases"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

SCRIPT_PATH="${REPO_ROOT}/scripts/analysis/freeze-experimental-cycle.py"

if [[ ! -f "${SCRIPT_PATH}" ]]; then
  echo "Freeze script not found: ${SCRIPT_PATH}" >&2
  exit 1
fi

ARGS=("-S" "${SCRIPT_PATH}" "--repo-root" "${REPO_ROOT}" "--cycle-config" "${CYCLE_CONFIG}")

[[ -n "${PROFILE_CONFIG}" ]] && ARGS+=("--profile-config" "${PROFILE_CONFIG}")
[[ -n "${FREEZE_ID}" ]] && ARGS+=("--freeze-id" "${FREEZE_ID}")
[[ -n "${OUTPUT_ROOT}" ]] && ARGS+=("--output-root" "${OUTPUT_ROOT}")
[[ -n "${FORCE_FLAG}" ]] && ARGS+=("${FORCE_FLAG}")
[[ -n "${DRY_RUN_FLAG}" ]] && ARGS+=("${DRY_RUN_FLAG}")
[[ -n "${SKIP_COMPLETION_GATE_FLAG}" ]] && ARGS+=("${SKIP_COMPLETION_GATE_FLAG}")
[[ -n "${WRITE_LATEST_ALIASES_FLAG}" ]] && ARGS+=("${WRITE_LATEST_ALIASES_FLAG}")

python3 "${ARGS[@]}"
