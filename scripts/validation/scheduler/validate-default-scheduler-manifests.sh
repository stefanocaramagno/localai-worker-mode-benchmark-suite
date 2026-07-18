#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=""
SCAN_ROOTS=()
RENDERED_MANIFESTS=()
RENDER_KUSTOMIZE=0
REQUIRE_RENDER=0
JSON_OUTPUT=0

usage() {
  cat <<'EOF'
Usage:
  validate-default-scheduler-manifests.sh [options]

Options:
  --repo-root <path>
  --scan-root <path>                 Can be supplied multiple times.
  --rendered-manifest <path>         Can be supplied multiple times.
  --render-kustomize
  --require-render
  --json
  --help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root|-RepoRoot)
      REPO_ROOT="${2:?Missing value for --repo-root}"; shift 2 ;;
    --scan-root|-ScanRoot)
      SCAN_ROOTS+=("${2:?Missing value for --scan-root}"); shift 2 ;;
    --rendered-manifest|-RenderedManifest)
      RENDERED_MANIFESTS+=("${2:?Missing value for --rendered-manifest}"); shift 2 ;;
    --render-kustomize|-RenderKustomize)
      RENDER_KUSTOMIZE=1; shift ;;
    --require-render|-RequireRender)
      REQUIRE_RENDER=1; shift ;;
    --json|-Json)
      JSON_OUTPUT=1; shift ;;
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

VALIDATOR="$REPO_ROOT/scripts/validation/scheduler/validate-default-scheduler-manifests.py"
if [[ ! -f "$VALIDATOR" ]]; then
  echo "Default-scheduler manifest validator not found: $VALIDATOR" >&2
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

ARGS=("$VALIDATOR" --repo-root "$REPO_ROOT")
for item in "${SCAN_ROOTS[@]}"; do
  ARGS+=(--scan-root "$item")
done
for item in "${RENDERED_MANIFESTS[@]}"; do
  ARGS+=(--rendered-manifest "$item")
done
[[ "$RENDER_KUSTOMIZE" == "1" ]] && ARGS+=(--render-kustomize)
[[ "$REQUIRE_RENDER" == "1" ]] && ARGS+=(--require-render)
[[ "$JSON_OUTPUT" == "1" ]] && ARGS+=(--json)

exec "$PYTHON_CMD" "${ARGS[@]}"
