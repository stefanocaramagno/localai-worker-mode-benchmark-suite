#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="."
CYCLE_CONFIG=""
PROFILE_CONFIG=""
KUBECONFIG_PATH=""
OUTPUT_ROOT=""
INJECTION_ID=""
ACTION="apply"
DRY_RUN=0
WRITE_LATEST_ALIASES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    --cycle-config) CYCLE_CONFIG="$2"; shift 2 ;;
    --profile-config) PROFILE_CONFIG="$2"; shift 2 ;;
    --kubeconfig) KUBECONFIG_PATH="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --injection-id) INJECTION_ID="$2"; shift 2 ;;
    --action) ACTION="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --write-latest-aliases) WRITE_LATEST_ALIASES=1; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$CYCLE_CONFIG" || -z "$PROFILE_CONFIG" || -z "$KUBECONFIG_PATH" || -z "$OUTPUT_ROOT" ]]; then
  echo "Missing required arguments." >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARGS=("$SCRIPT_DIR/apply-latency-profile.py" --repo-root "$REPO_ROOT" --cycle-config "$CYCLE_CONFIG" --profile-config "$PROFILE_CONFIG" --kubeconfig "$KUBECONFIG_PATH" --output-root "$OUTPUT_ROOT" --action "$ACTION")
if [[ -n "$INJECTION_ID" ]]; then ARGS+=(--injection-id "$INJECTION_ID"); fi
if [[ "$DRY_RUN" -eq 1 ]]; then ARGS+=(--dry-run); fi
if [[ "$WRITE_LATEST_ALIASES" -eq 1 ]]; then ARGS+=(--write-latest-aliases); fi

python "${ARGS[@]}"
