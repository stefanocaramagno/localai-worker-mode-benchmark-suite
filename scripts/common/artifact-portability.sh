#!/usr/bin/env bash

artifact_portability_find_repo_root() {
  local start_dir="$1"
  local current="$start_dir"
  while [[ -n "$current" && "$current" != "/" ]]; do
    if [[ -d "$current/config" && -d "$current/scripts" ]]; then
      printf '%s\n' "$current"
      return 0
    fi
    current="$(dirname "$current")"
  done
  pwd
}

artifact_portability_require_python() {
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "python3"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    printf '%s\n' "python"
    return 0
  fi
  echo "Python is required for artifact portability normalization." >&2
  return 1
}

normalize_artifact_file() {
  local artifact_path="$1"
  local python_cmd
  python_cmd="$(artifact_portability_require_python)" || return 1

  "$python_cmd" - "$artifact_path" <<'PY'
import json
import sys
from pathlib import Path

artifact_path = Path(sys.argv[1])
start = artifact_path.resolve().parent if artifact_path.exists() else Path.cwd().resolve()
repo_root = None
for candidate in [start, *start.parents, Path.cwd().resolve(), *Path.cwd().resolve().parents]:
    if (candidate / "config").is_dir() and (candidate / "scripts").is_dir():
        repo_root = candidate
        break
if repo_root is None:
    repo_root = Path.cwd().resolve()

sys.path.insert(0, str(repo_root / "scripts" / "common"))
from artifact_paths import normalize_artifact_payload, normalize_artifact_text

if not artifact_path.exists() or not artifact_path.is_file():
    sys.exit(0)

suffix = artifact_path.suffix.lower()
if suffix == ".json":
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8-sig"))
        payload = normalize_artifact_payload(payload, repo_root)
        artifact_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception:
        text = artifact_path.read_text(encoding="utf-8", errors="replace")
        artifact_path.write_text(normalize_artifact_text(text, repo_root), encoding="utf-8")
else:
    text = artifact_path.read_text(encoding="utf-8", errors="replace")
    artifact_path.write_text(normalize_artifact_text(text, repo_root), encoding="utf-8")
PY
}
