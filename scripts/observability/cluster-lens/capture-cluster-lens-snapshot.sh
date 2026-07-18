#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=""
PROFILE_CONFIG=""
SCENARIO_CONFIG=""
KUBECONFIG_PATH=""
KUBECTL_CMD=""
OUTPUT_DIR=""
SNAPSHOT_URL=""
USE_PORT_FORWARD=0
NO_PORT_FORWARD=0
DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage:
  capture-cluster-lens-snapshot.sh [options]

Options:
  --repo-root <path>
  --profile-config <path>
  --scenario-config <path>
  --kubeconfig <path>
  --kubectl <name-or-path>
  --output-dir <path>
  --snapshot-url <url>
  --use-port-forward
  --no-port-forward
  --dry-run
  --help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root|-RepoRoot)
      REPO_ROOT="${2:?Missing value for --repo-root}"; shift 2 ;;
    --profile-config|-ProfileConfig)
      PROFILE_CONFIG="${2:?Missing value for --profile-config}"; shift 2 ;;
    --scenario-config|-ScenarioConfig)
      SCENARIO_CONFIG="${2:?Missing value for --scenario-config}"; shift 2 ;;
    --kubeconfig|-Kubeconfig)
      KUBECONFIG_PATH="${2:?Missing value for --kubeconfig}"; shift 2 ;;
    --kubectl|-Kubectl)
      KUBECTL_CMD="${2:?Missing value for --kubectl}"; shift 2 ;;
    --output-dir|-OutputDir)
      OUTPUT_DIR="${2:?Missing value for --output-dir}"; shift 2 ;;
    --snapshot-url|-SnapshotUrl)
      SNAPSHOT_URL="${2:?Missing value for --snapshot-url}"; shift 2 ;;
    --use-port-forward|-UsePortForward)
      USE_PORT_FORWARD=1; shift ;;
    --no-port-forward|-NoPortForward)
      NO_PORT_FORWARD=1; shift ;;
    --dry-run|-DryRun)
      DRY_RUN=1; shift ;;
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

RUNNER="$REPO_ROOT/scripts/observability/cluster-lens/capture-cluster-lens-snapshot.py"
if [[ ! -f "$RUNNER" ]]; then
  echo "cluster-lens capture runner not found: $RUNNER" >&2
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
[[ -n "$PROFILE_CONFIG" ]] && ARGS+=(--profile-config "$PROFILE_CONFIG")
[[ -n "$SCENARIO_CONFIG" ]] && ARGS+=(--scenario-config "$SCENARIO_CONFIG")
[[ -n "$KUBECONFIG_PATH" ]] && ARGS+=(--kubeconfig "$KUBECONFIG_PATH")
[[ -n "$KUBECTL_CMD" ]] && ARGS+=(--kubectl "$KUBECTL_CMD")
[[ -n "$OUTPUT_DIR" ]] && ARGS+=(--output-dir "$OUTPUT_DIR")
[[ -n "$SNAPSHOT_URL" ]] && ARGS+=(--snapshot-url "$SNAPSHOT_URL")
[[ "$USE_PORT_FORWARD" == "1" ]] && ARGS+=(--use-port-forward)
[[ "$NO_PORT_FORWARD" == "1" ]] && ARGS+=(--no-port-forward)
[[ "$DRY_RUN" == "1" ]] && ARGS+=(--dry-run)

exec "$PYTHON_CMD" "${ARGS[@]}"
