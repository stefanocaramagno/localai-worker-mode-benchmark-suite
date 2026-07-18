#!/usr/bin/env bash
set -euo pipefail

print_usage() {
  cat <<'USAGE'
Usage:
  ./start-multi-tenant-locust.sh [options]

Options are forwarded to run-multi-tenant-locust.py.
Common options:
  --repo-root PATH
  --scenario-config PATH
  --kubeconfig PATH
  --locust-file PATH
  --output-root PATH
  --base-port PORT
  --remote-port PORT
  --tenant-ports tenant-a=8080,tenant-b=8081
  --tenant-base-urls tenant-a=http://localhost:8080,tenant-b=http://localhost:8081
  --run-id VALUE
  --skip-port-forward
  --reuse-existing-port-forward
  --dry-run
  --write-latest-aliases
  --help
USAGE
}

require_python_command() {
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    printf '%s' python
    return 0
  fi
  echo "Error: unable to find python3 or python in PATH." >&2
  exit 1
}

resolve_repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd -- "$script_dir/../../.." && pwd
}

for arg in "$@"; do
  case "$arg" in
    --help|-Help|-h)
      print_usage
      exit 0
      ;;
  esac
done

REPO_ROOT="$(resolve_repo_root)"
PYTHON_CMD="$(require_python_command)"
RUNNER="$REPO_ROOT/scripts/load/multi-tenant/run-multi-tenant-locust.py"

exec "$PYTHON_CMD" "$RUNNER" --repo-root "$REPO_ROOT" "$@"
