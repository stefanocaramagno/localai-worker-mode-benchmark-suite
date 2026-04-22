#!/usr/bin/env bash
set -euo pipefail

resolve_k8s_apply_target_type() {
  local target="$1"
  if [[ -f "$target" ]]; then
    echo file
    return 0
  fi
  if [[ -d "$target" && -f "$target/kustomization.yaml" ]]; then
    echo directory
    return 0
  fi
  echo invalid
}

require_k8s_apply_target() {
  local target="$1"
  local kind
  kind="$(resolve_k8s_apply_target_type "$target")"
  if [[ "$kind" == invalid ]]; then
    echo "Target Kubernetes non valido o non risolvibile: $target" >&2
    exit 1
  fi
}

describe_k8s_apply_command() {
  local target="$1"
  local kind
  kind="$(resolve_k8s_apply_target_type "$target")"
  case "$kind" in
    file) printf 'kubectl apply -f %q' "$target" ;;
    directory) printf 'kubectl apply -k %q' "$target" ;;
    *) echo "Target Kubernetes non valido o non risolvibile: $target" >&2; exit 1 ;;
  esac
}

invoke_k8s_apply_target() {
  local path="$1"
  local kubeconfig_path="${2:-}"
  local kind
  kind="$(resolve_k8s_apply_target_type "$path")"
  local kubectl_args=()
  [[ -n "$kubeconfig_path" ]] && kubectl_args+=(--kubeconfig "$kubeconfig_path")
  case "$kind" in
    file)
      echo "Applicazione automatica target Kubernetes: kubectl${kubeconfig_path:+ --kubeconfig $kubeconfig_path} apply -f $path"
      kubectl "${kubectl_args[@]}" apply -f "$path"
      ;;
    directory)
      echo "Applicazione automatica target Kubernetes: kubectl${kubeconfig_path:+ --kubeconfig $kubeconfig_path} apply -k $path"
      kubectl "${kubectl_args[@]}" apply -k "$path"
      ;;
    *) echo "Target Kubernetes non valido o non risolvibile: $path" >&2; exit 1 ;;
  esac
}
