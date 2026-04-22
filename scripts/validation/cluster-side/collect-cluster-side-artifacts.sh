#!/usr/bin/env bash
set -euo pipefail

PROFILE_CONFIG=""
KUBECONFIG_PATH=""
NAMESPACE_OVERRIDE=""
OUTPUT_PREFIX=""
STAGE=""

print_usage() {
  cat <<'USAGE'
Usage:
  ./collect-cluster-side-artifacts.sh [options]

Options:
  --profile-config PATH | -ProfileConfig PATH
  --kubeconfig PATH | -Kubeconfig PATH
  --namespace NAME | -Namespace NAME
  --output-prefix PREFIX | -OutputPrefix PREFIX
  --stage pre|post | -Stage pre|post
  --help | -Help
USAGE
}

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Errore: il comando richiesto non è disponibile nel PATH: $cmd" >&2
    exit 1
  fi
}

require_python_command() {
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return 0
  fi

  if command -v python >/dev/null 2>&1; then
    echo "python"
    return 0
  fi

  echo "Errore: impossibile trovare python3 o python nel PATH." >&2
  exit 1
}

resolve_repo_root() {
  local script_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  cd -- "$script_dir/../../.." && pwd
}

load_profile() {
  local profile_file="$1"
  local python_cmd
  python_cmd="$(require_python_command)"

  mapfile -t PROFILE_VALUES < <("$python_cmd" - "$profile_file" <<'PY'
import json
import sys
from pathlib import Path

profile_path = Path(sys.argv[1])
required = [
    "profileId",
    "description",
    "manifestSuffix",
    "textSuffix",
    "artifacts",
]
with profile_path.open("r", encoding="utf-8-sig") as fh:
    data = json.load(fh)
missing = [key for key in required if key not in data]
if missing:
    print(
        f"Il file di cluster-side collection '{profile_path}' non contiene le proprietà obbligatorie: {', '.join(missing)}.",
        file=sys.stderr,
    )
    sys.exit(1)
print(str(profile_path))
print(str(data["profileId"]))
print(str(data["description"]))
print(str(data["manifestSuffix"]))
print(str(data["textSuffix"]))
print(json.dumps(data["artifacts"], separators=(",", ":")))
PY
)

  PROFILE_FILE_RESOLVED="${PROFILE_VALUES[0]}"
  PROFILE_ID="${PROFILE_VALUES[1]}"
  PROFILE_DESCRIPTION="${PROFILE_VALUES[2]}"
  PROFILE_MANIFEST_SUFFIX="${PROFILE_VALUES[3]}"
  PROFILE_TEXT_SUFFIX="${PROFILE_VALUES[4]}"
  PROFILE_ARTIFACTS_JSON="${PROFILE_VALUES[5]}"
}

build_kubectl_prefix() {
  KUBECTL_BASE_ARGS=()
  if [[ -n "$KUBECONFIG_PATH" ]]; then
    KUBECTL_BASE_ARGS+=(--kubeconfig "$KUBECONFIG_PATH")
  fi
}

run_kubectl_to_file() {
  local output_file="$1"
  shift
  kubectl "${KUBECTL_BASE_ARGS[@]}" "$@" > "$output_file"
}

build_artifact_paths() {
  MANIFEST_PATH="${OUTPUT_PREFIX}${PROFILE_MANIFEST_SUFFIX}"
  TEXT_PATH="${OUTPUT_PREFIX}${PROFILE_TEXT_SUFFIX}"
  NODES_WIDE_PATH="${OUTPUT_PREFIX}_nodes-wide.txt"
  TOP_NODES_PATH="${OUTPUT_PREFIX}_top-nodes.txt"
  PODS_WIDE_PATH="${OUTPUT_PREFIX}_pods-wide.txt"
  TOP_PODS_PATH="${OUTPUT_PREFIX}_top-pods.txt"
  SERVICES_PATH="${OUTPUT_PREFIX}_services.txt"
  EVENTS_PATH="${OUTPUT_PREFIX}_events.txt"
  PODS_DESCRIBE_PATH="${OUTPUT_PREFIX}_pods-describe.txt"
}

build_artifacts_json() {
  local python_cmd
  python_cmd="$(require_python_command)"
  "$python_cmd" - "$MANIFEST_PATH" "$TEXT_PATH" "$NODES_WIDE_PATH" "$TOP_NODES_PATH" "$PODS_WIDE_PATH" "$TOP_PODS_PATH" "$SERVICES_PATH" "$EVENTS_PATH" "$PODS_DESCRIBE_PATH" <<'PY'
import json
import sys
print(json.dumps(sys.argv[1:], separators=(",", ":")))
PY
}

write_manifest_and_summary() {
  local artifact_list_json="$1"
  local kubectl_command_prefix="kubectl"
  local python_cmd
  python_cmd="$(require_python_command)"

  if [[ -n "$KUBECONFIG_PATH" ]]; then
    kubectl_command_prefix="kubectl --kubeconfig $KUBECONFIG_PATH"
  fi

  "$python_cmd" - "$MANIFEST_PATH" "$TEXT_PATH" \
    "$PROFILE_FILE_RESOLVED" "$PROFILE_ID" "$PROFILE_DESCRIPTION" \
    "$STAGE" "$NAMESPACE_EFFECTIVE" "$artifact_list_json" "$kubectl_command_prefix" \
    "$NODES_WIDE_PATH" "$TOP_NODES_PATH" "$PODS_WIDE_PATH" "$TOP_PODS_PATH" \
    "$SERVICES_PATH" "$EVENTS_PATH" "$PODS_DESCRIBE_PATH" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
text_path = Path(sys.argv[2])
artifacts = json.loads(sys.argv[8])
payload = {
    "clusterCaptureProfile": {
        "profileFile": sys.argv[3],
        "profileId": sys.argv[4],
        "description": sys.argv[5],
    },
    "capture": {
        "stage": sys.argv[6],
        "namespace": sys.argv[7],
        "artifacts": artifacts,
        "commands": {
            "nodesWide": f"{sys.argv[9]} get nodes -o wide",
            "topNodes": f"{sys.argv[9]} top nodes",
            "podsWide": f"{sys.argv[9]} get pods -n {sys.argv[7]} -o wide",
            "topPods": f"{sys.argv[9]} top pods -n {sys.argv[7]}",
            "services": f"{sys.argv[9]} get svc -n {sys.argv[7]}",
            "events": f"{sys.argv[9]} get events -n {sys.argv[7]} --sort-by=.metadata.creationTimestamp",
            "podsDescribe": f"{sys.argv[9]} describe pods -n {sys.argv[7]}",
        },
    },
}
manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8-sig")
lines = [
    "=============================================",
    " Cluster-side Collection",
    "=============================================",
    f"Profile       : {sys.argv[4]}",
    f"Description   : {sys.argv[5]}",
    f"Stage         : {sys.argv[6]}",
    f"Namespace     : {sys.argv[7]}",
    f"Manifest      : {sys.argv[1]}",
    f"nodes-wide    : {sys.argv[10]}",
    f"top-nodes     : {sys.argv[11]}",
    f"pods-wide     : {sys.argv[12]}",
    f"top-pods      : {sys.argv[13]}",
    f"services      : {sys.argv[14]}",
    f"events        : {sys.argv[15]}",
    f"pods-describe : {sys.argv[16]}",
]
text_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-config|-ProfileConfig)
      PROFILE_CONFIG="$2"
      shift 2
      ;;
    --kubeconfig|-Kubeconfig)
      KUBECONFIG_PATH="$2"
      shift 2
      ;;
    --namespace|-Namespace)
      NAMESPACE_OVERRIDE="$2"
      shift 2
      ;;
    --output-prefix|-OutputPrefix)
      OUTPUT_PREFIX="$2"
      shift 2
      ;;
    --stage|-Stage)
      STAGE="$2"
      shift 2
      ;;
    --help|-Help)
      print_usage
      exit 0
      ;;
    *)
      echo "Argomento non riconosciuto: $1" >&2
      print_usage >&2
      exit 1
      ;;
  esac
done

REPO_ROOT="$(resolve_repo_root)"
[[ -n "$PROFILE_CONFIG" ]] || PROFILE_CONFIG="$REPO_ROOT/config/cluster-capture/CS1.json"
[[ -n "$OUTPUT_PREFIX" ]] || { echo "Il parametro OutputPrefix è obbligatorio." >&2; print_usage >&2; exit 1; }
[[ -n "$STAGE" ]] || { echo "Il parametro Stage è obbligatorio." >&2; print_usage >&2; exit 1; }
case "$STAGE" in pre|post) ;; *) echo "Stage non supportato: $STAGE" >&2; exit 1 ;; esac

require_command kubectl
load_profile "$PROFILE_CONFIG"
build_kubectl_prefix
NAMESPACE_EFFECTIVE="${NAMESPACE_OVERRIDE:-genai-thesis}"
build_artifact_paths
mkdir -p -- "$(dirname -- "$OUTPUT_PREFIX")"

run_kubectl_to_file "$NODES_WIDE_PATH" get nodes -o wide
run_kubectl_to_file "$TOP_NODES_PATH" top nodes
run_kubectl_to_file "$PODS_WIDE_PATH" get pods -n "$NAMESPACE_EFFECTIVE" -o wide
run_kubectl_to_file "$TOP_PODS_PATH" top pods -n "$NAMESPACE_EFFECTIVE"
run_kubectl_to_file "$SERVICES_PATH" get svc -n "$NAMESPACE_EFFECTIVE"
run_kubectl_to_file "$EVENTS_PATH" get events -n "$NAMESPACE_EFFECTIVE" --sort-by=.metadata.creationTimestamp
run_kubectl_to_file "$PODS_DESCRIBE_PATH" describe pods -n "$NAMESPACE_EFFECTIVE"

ARTIFACTS_JSON="$(build_artifacts_json)"
write_manifest_and_summary "$ARTIFACTS_JSON"

echo "Cluster-side collection completata: stage=$STAGE"
echo " - $MANIFEST_PATH"
echo " - $TEXT_PATH"
