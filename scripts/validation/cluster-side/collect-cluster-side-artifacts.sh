#!/usr/bin/env bash
set -euo pipefail

artifact_portability_search_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
while [[ -n "$artifact_portability_search_dir" && "$artifact_portability_search_dir" != "/" ]]; do
  artifact_portability_candidate="$artifact_portability_search_dir/scripts/common/artifact-portability.sh"
  if [[ -f "$artifact_portability_candidate" ]]; then
    # shellcheck source=/dev/null
    source "$artifact_portability_candidate"
    break
  fi
  artifact_portability_search_dir="$(dirname "$artifact_portability_search_dir")"
done
unset artifact_portability_search_dir artifact_portability_candidate

PROFILE_CONFIG=""
KUBECONFIG_PATH=""
NAMESPACE_OVERRIDE=""
ADDITIONAL_NAMESPACES=""
OUTPUT_PREFIX=""
STAGE=""

usage() {
  cat <<'EOF'
Usage: collect-cluster-side-artifacts.sh --profile-config <path> --kubeconfig <path> --output-prefix <path-prefix> --stage <pre|post> [--namespace <namespace>] [--additional-namespaces <ns1,ns2>]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-config|-ProfileConfig)
      PROFILE_CONFIG="$2"; shift 2 ;;
    --kubeconfig|-Kubeconfig)
      KUBECONFIG_PATH="$2"; shift 2 ;;
    --namespace|-Namespace)
      NAMESPACE_OVERRIDE="$2"; shift 2 ;;
    --additional-namespaces|-AdditionalNamespaces)
      ADDITIONAL_NAMESPACES="$2"; shift 2 ;;
    --output-prefix|-OutputPrefix)
      OUTPUT_PREFIX="$2"; shift 2 ;;
    --stage|-Stage)
      STAGE="$2"; shift 2 ;;
    --help|-h)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1 ;;
  esac
done

resolve_repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd -- "$script_dir/../../.." && pwd
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Required command not found: $cmd" >&2
    exit 1
  fi
}

require_python_command() {
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
  elif command -v python >/dev/null 2>&1; then
    echo "python"
  else
    echo "Python is required but was not found in PATH." >&2
    exit 1
  fi
}

REPO_ROOT="$(resolve_repo_root)"

if [[ -z "$PROFILE_CONFIG" || -z "$OUTPUT_PREFIX" || -z "$STAGE" ]]; then
  usage >&2
  exit 1
fi
case "$STAGE" in
  pre|post) ;;
  *) echo "Stage must be either 'pre' or 'post'." >&2; exit 1 ;;
esac

require_command kubectl
PYTHON_CMD="$(require_python_command)"

"$PYTHON_CMD" - \
  "$PROFILE_CONFIG" "$KUBECONFIG_PATH" "$NAMESPACE_OVERRIDE" "$ADDITIONAL_NAMESPACES" \
  "$OUTPUT_PREFIX" "$STAGE" "$REPO_ROOT" <<'PY'
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

profile_arg = sys.argv[1]
kubeconfig = sys.argv[2]
namespace_override = sys.argv[3]
additional_namespaces_arg = sys.argv[4]
output_prefix = sys.argv[5]
stage = sys.argv[6]
repo_root = Path(sys.argv[7]).resolve()
sys.path.insert(0, str(repo_root / "scripts" / "common"))
from artifact_paths import normalize_artifact_payload, normalize_artifact_text

profile_path = Path(profile_arg)
if not profile_path.is_absolute():
    profile_path = (repo_root / profile_path).resolve()
if not profile_path.exists():
    print(f"Cluster capture profile not found: {profile_path}", file=sys.stderr)
    sys.exit(1)

with profile_path.open("r", encoding="utf-8-sig") as handle:
    profile = json.load(handle)

profile_id = profile.get("id") or profile.get("profileId") or profile_path.stem
profile_description = profile.get("description", "")
manifest_suffix = profile.get("manifestSuffix", "_manifest.json")
text_suffix = profile.get("textSuffix") or profile.get("textSummarySuffix", "_summary.txt")
artifacts_config = profile.get("artifacts", [])


def values_from(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;]", value) if item.strip()]
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                candidate = item.get("namespace") or item.get("name")
            else:
                candidate = item
            if candidate is not None and str(candidate).strip():
                result.append(str(candidate).strip())
        return result
    if isinstance(value, dict):
        candidate = value.get("namespace") or value.get("name")
        return [str(candidate).strip()] if candidate is not None and str(candidate).strip() else []
    text = str(value).strip()
    return [text] if text else []


def dedupe(values):
    seen = set()
    result = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result

profile_namespaces = values_from(profile.get("namespaces"))
primary_candidates = values_from(namespace_override) + values_from(profile.get("namespace")) + profile_namespaces + ["localai-benchmark"]
primary_namespace = dedupe(primary_candidates)[0]
all_namespaces = dedupe(
    [primary_namespace]
    + values_from(additional_namespaces_arg)
    + values_from(profile.get("additionalNamespaces"))
    + profile_namespaces
)
additional_namespaces = [namespace for namespace in all_namespaces if namespace != primary_namespace]


def safe_token(value):
    token = re.sub(r"[^a-z0-9._-]+", "-", str(value).strip().lower()).strip("-")
    return token or "namespace"


def repo_relative(value):
    if value is None:
        return None
    text = str(value)
    if not text.strip():
        return text
    normalised = text.replace("\\", "/")
    root = str(repo_root.resolve()).replace("\\", "/").rstrip("/")
    normalised_cmp = normalised.lower()
    root_cmp = root.lower()
    if normalised_cmp == root_cmp:
        return "."
    if normalised_cmp.startswith(root_cmp + "/"):
        return normalised[len(root) + 1:]
    marker = "/localai-worker-mode-benchmark-suite/"
    marker_index = normalised_cmp.find(marker)
    if marker_index >= 0:
        return normalised[marker_index + len(marker):]
    return text


def normalize_payload(value):
    if isinstance(value, dict):
        return {key: normalize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_payload(item) for item in value]
    if isinstance(value, str):
        return repo_relative(value)
    return value

Path(output_prefix).parent.mkdir(parents=True, exist_ok=True)
manifest_path = Path(f"{output_prefix}{manifest_suffix}")
text_path = Path(f"{output_prefix}{text_suffix}")

planned_artifacts = []
for item in artifacts_config:
    name = str(item.get("name"))
    command_template = str(item.get("command"))
    output_suffix = str(item.get("outputSuffix"))
    if "{namespace}" in command_template:
        for namespace in all_namespaces:
            role = "primary" if namespace == primary_namespace else "additional"
            output_file = f"{output_prefix}_{output_suffix}" if role == "primary" else f"{output_prefix}_{safe_token(namespace)}_{output_suffix}"
            planned_artifacts.append({
                "name": name if role == "primary" else f"{name}:{namespace}",
                "command": command_template.replace("{kubeconfig}", kubeconfig).replace("{namespace}", namespace),
                "outputFile": output_file,
                "namespace": namespace,
                "namespaceRole": role,
                "namespaceScoped": True,
            })
    else:
        planned_artifacts.append({
            "name": name,
            "command": command_template.replace("{kubeconfig}", kubeconfig),
            "outputFile": f"{output_prefix}_{output_suffix}",
            "namespace": None,
            "namespaceRole": "cluster",
            "namespaceScoped": False,
        })

exit_code = 0
executed_artifacts = []
for artifact in planned_artifacts:
    output_file = Path(artifact["outputFile"])
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        result = subprocess.run(
            artifact["command"],
            shell=True,
            executable="/bin/bash",
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )
    artifact["exitCode"] = int(result.returncode)
    if result.returncode != 0:
        exit_code = 1
    executed_artifacts.append(artifact)

payload = {
    "clusterCaptureProfile": {
        "profileFile": repo_relative(profile_path),
        "profileId": profile_id,
        "description": profile_description,
    },
    "capture": {
        "timestampUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "stage": stage,
        "namespace": primary_namespace,
        "primaryNamespace": primary_namespace,
        "namespaces": all_namespaces,
        "additionalNamespaces": additional_namespaces,
        "kubeconfig": kubeconfig,
        "outputPrefix": output_prefix,
        "exitCode": exit_code,
        "artifacts": [
            {
                "name": item["name"],
                "command": item["command"],
                "outputFile": item["outputFile"],
                "exitCode": item.get("exitCode"),
                "namespace": item.get("namespace"),
                "namespaceRole": item.get("namespaceRole"),
                "namespaceScoped": item.get("namespaceScoped", False),
            }
            for item in executed_artifacts
        ],
    },
}
payload = normalize_artifact_payload(normalize_payload(payload), repo_root)
manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8-sig")
summary_lines = [
    "=============================================",
    " Cluster-side Collection",
    "=============================================",
    f"Profile       : {profile_id}",
    f"Description   : {profile_description}",
    f"Stage         : {stage}",
    f"Namespace     : {primary_namespace}",
    f"Namespaces    : {', '.join(all_namespaces)}",
    f"Output prefix : {repo_relative(output_prefix)}",
    f"Exit code     : {exit_code}",
    "",
    "Artifacts:",
]
for item in payload["capture"]["artifacts"]:
    namespace = item.get("namespace") or "cluster"
    summary_lines.append(f" - {item['name']} [{namespace}]: {item['outputFile']} (exit={item.get('exitCode')})")
text_path.write_text(normalize_artifact_text("\n".join(summary_lines) + "\n", repo_root), encoding="utf-8-sig")

print(f"Cluster-side collection completed: stage={stage}")
print(f" - {repo_relative(manifest_path)}")
print(f" - {repo_relative(text_path)}")
sys.exit(exit_code)
PY
