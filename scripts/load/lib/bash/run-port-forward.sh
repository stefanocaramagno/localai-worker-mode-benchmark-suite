#!/usr/bin/env bash
set -euo pipefail

port_forward_test_local_port_reachable() {
  local host_name="$1"
  local port="$2"
  local timeout_seconds="${3:-1}"
  if command -v nc >/dev/null 2>&1; then
    nc -z -w "$timeout_seconds" "$host_name" "$port" >/dev/null 2>&1
    return $?
  fi
  (echo > "/dev/tcp/${host_name}/${port}") >/dev/null 2>&1
}

port_forward_test_http_endpoint_ready() {
  local url="$1"
  local timeout_seconds="${2:-5}"
  curl --silent --show-error --fail --max-time "$timeout_seconds" "$url" >/dev/null 2>&1
}

get_local_port_owning_process_ids() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk '!seen[$0]++'
    return 0
  fi
  if command -v netstat >/dev/null 2>&1; then
    netstat -ltnp 2>/dev/null | awk -v port=":$port" '$4 ~ port { split($7,a,"/"); if (a[1] ~ /^[0-9]+$/) print a[1] }' | awk '!seen[$0]++'
  fi
}

stop_kubectl_port_forward_processes_on_port() {
  local port="$1"
  local stopped=()
  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    local comm
    comm="$(ps -p "$pid" -o comm= 2>/dev/null | awk '{print $1}')"
    if [[ "$comm" == kubectl ]]; then
      kill -9 "$pid" >/dev/null 2>&1 || true
      stopped+=("$pid")
    fi
  done < <(get_local_port_owning_process_ids "$port")
  if (( ${#stopped[@]} > 0 )); then
    sleep 1
    printf '%s
' "${stopped[@]}"
  fi
}

wait_kubernetes_service_backend_ready() {
  local kubeconfig_path="$1"
  local namespace="$2"
  local service_name="$3"
  local timeout_seconds="${4:-180}"
  local deadline=$((SECONDS + timeout_seconds))
  local kubectl_prefix=(kubectl)
  [[ -n "$kubeconfig_path" ]] && kubectl_prefix+=(--kubeconfig "$kubeconfig_path")
  while (( SECONDS < deadline )); do
    if ! "${kubectl_prefix[@]}" rollout status "deployment/${service_name}" -n "$namespace" --timeout=5s >/dev/null 2>&1; then
      sleep 1
      continue
    fi
    if ! "${kubectl_prefix[@]}" wait --for=condition=Ready pod -l "app=${service_name}" -n "$namespace" --timeout=5s >/dev/null 2>&1; then
      sleep 1
      continue
    fi
    local endpoint_text
    endpoint_text="$("${kubectl_prefix[@]}" get endpointslice -n "$namespace" -l "kubernetes.io/service-name=${service_name}" -o 'jsonpath={.items[*].endpoints[*].addresses[*]}' 2>/dev/null || true)"
    if [[ -n "$endpoint_text" ]]; then
      return 0
    fi
    sleep 1
  done
  echo "Timeout durante l'attesa della readiness Kubernetes di service/$service_name nel namespace $namespace." >&2
  return 1
}

ensure_local_kubernetes_port_forward() {
  local repo_root="$1"
  local base_url="$2"
  local kubeconfig_path="${3:-}"
  local namespace="${4:-}"
  local service_name="${5:-localai-server}"
  local remote_port="${6:-8080}"
  [[ -z "$base_url" ]] && return 0

  local python_cmd
  if command -v python >/dev/null 2>&1 && python --version >/dev/null 2>&1; then
    python_cmd=python
  elif command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; then
    python_cmd=python3
  else
    echo "Nessun interprete Python compatibile e disponibile nel PATH. Impossibile analizzare automaticamente il Base URL per il port-forward." >&2
    return 1
  fi

  local parsed
  parsed="$($python_cmd - <<'PY' "$base_url"
from urllib.parse import urlparse
import sys
u = urlparse(sys.argv[1])
host = u.hostname or ''
port = u.port if u.port is not None else (443 if u.scheme == 'https' else 80)
print(host)
print(port)
print(u.scheme or 'http')
PY
)"
  local host_name port scheme
  host_name="$(printf '%s' "$parsed" | sed -n '1p')"
  port="$(printf '%s' "$parsed" | sed -n '2p')"
  scheme="$(printf '%s' "$parsed" | sed -n '3p')"
  case "$host_name" in localhost|127.0.0.1|::1) ;; *) return 0 ;; esac
  local readiness_url="${scheme}://${host_name}:${port}/v1/models"

  if port_forward_test_local_port_reachable 127.0.0.1 "$port" 1; then
    mapfile -t stopped < <(stop_kubectl_port_forward_processes_on_port "$port" || true)
    if (( ${#stopped[@]} > 0 )); then
      echo "Rilevato listener locale preesistente su localhost:${port}. Terminati processi kubectl residui prima di creare un nuovo port-forward: $(IFS=', '; echo "${stopped[*]}")."
    fi
    if port_forward_test_local_port_reachable 127.0.0.1 "$port" 1; then
      echo "La porta locale localhost:${port} risulta già occupata. Impossibile creare un nuovo port-forward in sicurezza." >&2
      return 1
    fi
  fi

  command -v kubectl >/dev/null 2>&1 || { echo 'kubectl non risulta disponibile nel PATH. Impossibile creare automaticamente il port-forward.' >&2; return 1; }
  [[ -n "$namespace" ]] || { echo 'Namespace obbligatorio per creare automaticamente il port-forward verso il service Kubernetes.' >&2; return 1; }

  echo "Verifica della readiness Kubernetes del backend di service/${service_name} nel namespace ${namespace} prima del port-forward locale."
  wait_kubernetes_service_backend_ready "$kubeconfig_path" "$namespace" "$service_name" 120 || return 1
  sleep 2

  mkdir -p -- "$repo_root/results/_runtime/port-forward"
  local stdout_log="$repo_root/results/_runtime/port-forward/${service_name}_${port}_stdout.log"
  local stderr_log="$repo_root/results/_runtime/port-forward/${service_name}_${port}_stderr.log"
  rm -f -- "$stdout_log" "$stderr_log"

  local kubectl_args=(port-forward -n "$namespace" "service/${service_name}" "${port}:${remote_port}")
  [[ -n "$kubeconfig_path" ]] && kubectl_args=(--kubeconfig "$kubeconfig_path" "${kubectl_args[@]}")

  local attempt=1
  while (( attempt <= 3 )); do
    echo "Port-forward locale non raggiungibile su ${host_name}:${port}. Avvio automatico: kubectl ${kubectl_args[*]} (tentativo ${attempt})"
    kubectl "${kubectl_args[@]}" >"$stdout_log" 2>"$stderr_log" &
    local pf_pid=$!
    local waited=0
    while (( waited < 30 )); do
      if ! kill -0 "$pf_pid" >/dev/null 2>&1; then
        break
      fi
      if port_forward_test_local_port_reachable 127.0.0.1 "$port" 1; then
        echo "Port-forward attivo su ${host_name}:${port} (PID ${pf_pid}). Verifica della readiness HTTP in corso su ${readiness_url}."
        local ready_wait=0
        while (( ready_wait < 120 )); do
          if port_forward_test_http_endpoint_ready "$readiness_url" 5; then
            return 0
          fi
          if ! kill -0 "$pf_pid" >/dev/null 2>&1; then
            break
          fi
          sleep 1
          ready_wait=$((ready_wait + 1))
        done
        kill -9 "$pf_pid" >/dev/null 2>&1 || true
        echo "Il backend non era ancora pronto ad accettare connessioni dietro il port-forward; nuovo tentativo in corso..."
        break
      fi
      sleep 1
      waited=$((waited + 1))
    done
    kill -9 "$pf_pid" >/dev/null 2>&1 || true
    attempt=$((attempt + 1))
    sleep 2
  done

  echo "Timeout durante la stabilizzazione del port-forward locale verso service/$service_name su localhost:$port." >&2
  return 1
}
