#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="."
MODE="auto"
EXPECTED_SCHEDULER_NAME="scheduler-plugins-scheduler"
SCAN_ROOTS=()
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      REPO_ROOT="$2"; shift 2 ;;
    --scan-root)
      SCAN_ROOTS+=("$2"); shift 2 ;;
    --mode)
      MODE="$2"; shift 2 ;;
    --expected-scheduler-name)
      EXPECTED_SCHEDULER_NAME="$2"; shift 2 ;;
    --render-kustomize|--require-render|--source-only|--json)
      EXTRA_ARGS+=("$1"); shift ;;
    *)
      EXTRA_ARGS+=("$1"); shift ;;
  esac
done

if [[ ${#SCAN_ROOTS[@]} -eq 0 ]]; then
  SCAN_ROOTS=("infra/k8s/compositions/resource-aware-scheduler")
fi

ARGS=(
  "$(cd "$REPO_ROOT" && pwd)/scripts/validation/scheduler/validate-scheduler-mode-manifests.py"
  --repo-root "$REPO_ROOT"
  --mode "$MODE"
  --expected-scheduler-name "$EXPECTED_SCHEDULER_NAME"
)

for ROOT in "${SCAN_ROOTS[@]}"; do
  ARGS+=(--scan-root "$ROOT")
done

ARGS+=("${EXTRA_ARGS[@]}")
python "${ARGS[@]}"
