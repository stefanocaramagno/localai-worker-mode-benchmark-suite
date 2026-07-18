#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=""
SCENARIO_CONFIG=""
KUBECONFIG_PATH=""
KUBECTL_CMD=""
OUTPUT_DIR=""
OUTPUT_NAME=""
SELECTOR=""
SELECTOR_SET=0
DISABLE_FALLBACK_APP_FILTER=0
DRY_RUN=0
WRITE_TEXT_SUMMARY=0
WRITE_LATEST_ALIASES=0

usage() {
  cat <<'EOF'
Usage:
  capture-scheduler-decisions.sh [options]

Options:
  --repo-root <path>
  --scenario-config <path>
  --kubeconfig <path>
  --kubectl <name-or-path>
  --output-dir <path>
  --output-name <name>
  --selector <label-selector>
  --disable-fallback-app-filter
  --dry-run
  --write-text-summary
  --write-latest-aliases
  --help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root|-RepoRoot)
      REPO_ROOT="${2:?Missing value for --repo-root}"; shift 2 ;;
    --scenario-config|-ScenarioConfig)
      SCENARIO_CONFIG="${2:?Missing value for --scenario-config}"; shift 2 ;;
    --kubeconfig|-Kubeconfig)
      KUBECONFIG_PATH="${2:?Missing value for --kubeconfig}"; shift 2 ;;
    --kubectl|-Kubectl)
      KUBECTL_CMD="${2:?Missing value for --kubectl}"; shift 2 ;;
    --output-dir|-OutputDir)
      OUTPUT_DIR="${2:?Missing value for --output-dir}"; shift 2 ;;
    --output-name|-OutputName)
      OUTPUT_NAME="${2:?Missing value for --output-name}"; shift 2 ;;
    --selector|-Selector)
      SELECTOR="${2-}"; SELECTOR_SET=1; shift 2 ;;
    --disable-fallback-app-filter|-DisableFallbackAppFilter)
      DISABLE_FALLBACK_APP_FILTER=1; shift ;;
    --dry-run|-DryRun)
      DRY_RUN=1; shift ;;
    --write-text-summary|-WriteTextSummary)
      WRITE_TEXT_SUMMARY=1; shift ;;
    --write-latest-aliases|-WriteLatestAliases)
      WRITE_LATEST_ALIASES=1; shift ;;
    --help|-h|-Help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "$REPO_ROOT" ]]; then
  REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
else
  REPO_ROOT="$(cd -- "$REPO_ROOT" && pwd)"
fi

RUNNER="$REPO_ROOT/scripts/observability/scheduler/capture-scheduler-decisions.py"
if [[ ! -f "$RUNNER" ]]; then
  echo "Scheduler decision capture runner not found: $RUNNER" >&2
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "Neither python3 nor python is available in PATH." >&2
  exit 1
fi

ARGS=("$RUNNER" --repo-root "$REPO_ROOT")
[[ -n "$SCENARIO_CONFIG" ]] && ARGS+=(--scenario-config "$SCENARIO_CONFIG")
[[ -n "$KUBECONFIG_PATH" ]] && ARGS+=(--kubeconfig "$KUBECONFIG_PATH")
[[ -n "$KUBECTL_CMD" ]] && ARGS+=(--kubectl "$KUBECTL_CMD")
[[ -n "$OUTPUT_DIR" ]] && ARGS+=(--output-dir "$OUTPUT_DIR")
[[ -n "$OUTPUT_NAME" ]] && ARGS+=(--output-name "$OUTPUT_NAME")
[[ "$SELECTOR_SET" == "1" ]] && ARGS+=(--selector "$SELECTOR")
[[ "$DISABLE_FALLBACK_APP_FILTER" == "1" ]] && ARGS+=(--disable-fallback-app-filter)
[[ "$DRY_RUN" == "1" ]] && ARGS+=(--dry-run)
[[ "$WRITE_TEXT_SUMMARY" == "1" ]] && ARGS+=(--write-text-summary)
[[ "$WRITE_LATEST_ALIASES" == "1" ]] && ARGS+=(--write-latest-aliases)

exec "$PYTHON_CMD" "${ARGS[@]}"
