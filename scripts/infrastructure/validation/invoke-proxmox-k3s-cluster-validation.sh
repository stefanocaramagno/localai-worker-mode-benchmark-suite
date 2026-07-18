#!/usr/bin/env bash
set -euo pipefail

PROFILE_CONFIG=""
KUBECONFIG_PATH=""
OUTPUT_ROOT=""
VALIDATION_ID=""
ALLOW_METRICS_WARNING="0"
DRY_RUN="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-config) PROFILE_CONFIG="$2"; shift 2 ;;
    --kubeconfig) KUBECONFIG_PATH="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --validation-id) VALIDATION_ID="$2"; shift 2 ;;
    --allow-metrics-warning) ALLOW_METRICS_WARNING="1"; shift ;;
    --dry-run) DRY_RUN="1"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

if [[ -z "$PROFILE_CONFIG" ]]; then
  PROFILE_CONFIG="$REPO_ROOT/config/provisioning-validation/profiles/PV_C1_PROVIDER_BACKED_BASELINE.json"
fi

PYTHON_BIN=""
if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Neither python nor python3 is available in PATH." >&2
  exit 1
fi

ARGS=("$SCRIPT_DIR/validate-proxmox-k3s-cluster.py" "--repo-root" "$REPO_ROOT" "--profile-config" "$PROFILE_CONFIG")
if [[ -n "$OUTPUT_ROOT" ]]; then
  ARGS+=("--output-root" "$OUTPUT_ROOT")
fi
if [[ -n "$KUBECONFIG_PATH" ]]; then
  ARGS+=("--kubeconfig" "$KUBECONFIG_PATH")
fi
if [[ -n "$VALIDATION_ID" ]]; then
  ARGS+=("--validation-id" "$VALIDATION_ID")
fi
if [[ "$ALLOW_METRICS_WARNING" == "1" ]]; then
  ARGS+=("--allow-metrics-warning")
fi
if [[ "$DRY_RUN" == "1" ]]; then
  ARGS+=("--dry-run")
fi

echo "==============================================="
echo " proxmox-k3s standalone cluster validation"
echo "==============================================="
echo "Repository : $REPO_ROOT"
echo "Profile    : $PROFILE_CONFIG"
echo "Kubeconfig : $KUBECONFIG_PATH"
echo "Output root: $OUTPUT_ROOT"
echo "Dry run    : $DRY_RUN"
echo ""

exec "$PYTHON_BIN" "${ARGS[@]}"
