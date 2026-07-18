#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


TARGET_REQUEST_TYPE = "POST"
TARGET_REQUEST_NAME = "POST /v1/chat/completions"
DEFAULT_SCENARIO_CONFIG = "config/scenarios/default-scheduler/DS_2T_4N_L1_DIFFERENTIATED_M1M1_W2.json"
DEFAULT_LOCUST_FILE = "load-tests/locust/locustfile.py"
DEFAULT_PHASE_CONFIG = "config/phases/profiles/WM_STANDARD_WARMUP_MEASUREMENT.json"
DEFAULT_OUTPUT_ROOT = "results/experimental-cycles/C7/benchmark/default-scheduler"
DEFAULT_REMOTE_PORT = 8080
DEFAULT_BASE_PORT = 8080


def _load_artifact_path_helpers():
    import importlib.util

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "scripts" / "common" / "artifact_paths.py"
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("artifact_paths", candidate)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            return module.normalize_artifact_payload_for_output, module.normalize_artifact_text_for_output

    def normalize_payload(value: Any, _output_path: Path | str) -> Any:
        return value

    def normalize_text(value: str, _output_path: Path | str) -> str:
        return value

    return normalize_payload, normalize_text


normalize_artifact_payload_for_output, normalize_artifact_text_for_output = _load_artifact_path_helpers()


@dataclass(frozen=True)
class TenantExecutionPlan:
    tenant_id: str
    namespace: str
    service_name: str
    model_name: str
    base_url: str
    access_mode: str
    host_header: str
    port_forward_namespace: str
    port_forward_service_name: str
    port_forward_remote_port: int
    port_forward_target_kind: str
    users: int
    spawn_rate: float
    run_time: str
    wait_time_seconds: float
    warm_up_enabled: bool
    warm_up_users: int
    warm_up_spawn_rate: float
    warm_up_duration: str
    output_dir: Path
    warm_up_csv_prefix: Path
    csv_prefix: Path
    environment: dict[str, str] = field(default_factory=dict)


@dataclass
class RunningPortForward:
    tenant_id: str
    namespace: str
    service_name: str
    local_port: int
    remote_port: int
    target_kind: str
    process: subprocess.Popen[Any]
    stdout_path: Path
    stderr_path: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_artifact_payload_for_output(payload, path)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = normalize_artifact_text_for_output(content, path)
    path.write_text(content, encoding="utf-8")


def resolve_repo_root(value: str) -> Path:
    candidate = Path(value).expanduser().resolve()
    if not (candidate / "config").is_dir() or not (candidate / "scripts").is_dir():
        raise SystemExit(f"Repository root does not look valid: {candidate}")
    return candidate


def resolve_path(repo_root: Path, value: str | None, default: str) -> Path:
    raw = value if value else default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else repo_root / path


def rel_to_repo(repo_root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def parse_key_value_map(raw_value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_item in raw_value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if "=" not in item:
            raise SystemExit(f"Invalid key=value item: {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise SystemExit(f"Invalid key=value item: {item!r}")
        result[key] = value
    return result


def parse_tenant_ports(raw_value: str) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for key, value in parse_key_value_map(raw_value).items():
        try:
            port = int(value)
        except ValueError as exc:
            raise SystemExit(f"Invalid port for tenant {key}: {value!r}") from exc
        if port <= 0 or port > 65535:
            raise SystemExit(f"Invalid port for tenant {key}: {port}")
        parsed[key] = port
    return parsed


def parse_float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed


def parse_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed


def scenario_output_root(repo_root: Path, scenario: dict[str, Any], output_root_override: str | None) -> Path:
    if output_root_override:
        return resolve_path(repo_root, output_root_override, output_root_override)
    results_root = str(scenario.get("resultsRoot") or DEFAULT_OUTPUT_ROOT)
    output_subdir = str(scenario.get("outputSubdir") or scenario.get("scenarioId") or "multi-tenant-run")
    return resolve_path(repo_root, f"{results_root}/{output_subdir}", f"{DEFAULT_OUTPUT_ROOT}/{output_subdir}")


def load_phase_profile(repo_root: Path, scenario: dict[str, Any], phase_config_override: str | None) -> dict[str, Any]:
    candidates = [
        phase_config_override,
        scenario.get("phaseProfilePath"),
        scenario.get("phaseConfigPath"),
        DEFAULT_PHASE_CONFIG,
    ]
    for value in candidates:
        if not value:
            continue
        path = resolve_path(repo_root, str(value), str(value))
        if path.is_file():
            payload = load_json(path)
            payload.setdefault("profilePath", rel_to_repo(repo_root, path))
            return payload
    return {
        "profileId": "WM1_DEFAULT",
        "description": "Built-in Locust warm-up and measurement phase profile.",
        "warmUpEnabled": True,
        "warmUpDuration": "30s",
        "warmUpUsersMode": "match_measurement",
        "warmUpSpawnRateMode": "match_measurement",
        "profilePath": DEFAULT_PHASE_CONFIG,
    }


def benchmark_targets_by_tenant(scenario: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in scenario.get("benchmarkTargets") or []:
        if not isinstance(item, dict):
            continue
        tenant_id = str(item.get("tenantId") or "").strip()
        if tenant_id:
            result[tenant_id] = item
    return result


def traffic_profiles_by_tenant(scenario: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    traffic = scenario.get("trafficProfile") or {}
    for item in traffic.get("tenantProfiles") or []:
        if not isinstance(item, dict):
            continue
        tenant_id = str(item.get("tenantId") or "").strip()
        if tenant_id:
            result[tenant_id] = item
    return result


def normalize_access_mode(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in {"istio_gateway", "gateway", "gateway_routed", "istio_gateway_routed"}:
        return "istio_gateway_routed"
    if text in {"tenant_scoped_port_forward", "port_forward", "localai_service_port_forward"}:
        return "tenant_scoped_port_forward"
    if text in {"external", "external_endpoint", "direct_endpoint"}:
        return "external_endpoint"
    return text or "tenant_scoped_port_forward"


def tenant_gateway_settings(tenant: dict[str, Any], tenant_target: dict[str, Any], tenant_id: str, namespace: str) -> dict[str, Any]:
    gateway = {}
    if isinstance(tenant.get("gateway"), dict):
        gateway.update(tenant.get("gateway") or {})
    if isinstance(tenant_target.get("gateway"), dict):
        gateway.update(tenant_target.get("gateway") or {})

    host_header = str(
        tenant_target.get("hostHeader")
        or tenant_target.get("gatewayHost")
        or gateway.get("hostHeader")
        or gateway.get("hostname")
        or tenant.get("hostHeader")
        or tenant.get("gatewayHost")
        or ""
    ).strip()
    service_name = str(gateway.get("serviceName") or gateway.get("gatewayServiceName") or "localai-gateway-istio").strip()
    service_namespace = str(gateway.get("namespace") or namespace).strip()
    remote_port = parse_int(gateway.get("remotePort") or gateway.get("port"), 80)
    target_kind = str(gateway.get("targetKind") or "istio_gateway_service").strip()
    return {
        "hostHeader": host_header,
        "serviceName": service_name,
        "namespace": service_namespace,
        "remotePort": remote_port,
        "targetKind": target_kind,
    }


def scheduler_runtime_context(scenario: dict[str, Any]) -> dict[str, str | None]:
    topology = scenario.get("applicationTopology") if isinstance(scenario.get("applicationTopology"), dict) else {}
    scheduler_policy = scenario.get("schedulerModePolicy") if isinstance(scenario.get("schedulerModePolicy"), dict) else {}
    fixed_dimensions = scenario.get("fixedDimensions") if isinstance(scenario.get("fixedDimensions"), dict) else {}

    mode = (
        scenario.get("schedulerMode")
        or topology.get("schedulerMode")
        or scheduler_policy.get("schedulerMode")
        or fixed_dimensions.get("schedulerMode")
        or "kubernetes_default_scheduler"
    )
    scheduler_name = (
        scenario.get("schedulerName")
        or topology.get("schedulerName")
        or scheduler_policy.get("schedulerName")
        or fixed_dimensions.get("schedulerName")
    )
    if not scheduler_name and str(mode) == "kubernetes_default_scheduler":
        scheduler_name = "default-scheduler"

    if str(mode) == "loadaware_custom_scheduler":
        display_name = "Load-aware custom scheduler"
        placement_policy = "scheduler_plugins_loadaware_decides_at_runtime"
    elif str(mode) == "kubernetes_default_scheduler":
        display_name = "Kubernetes default scheduler"
        placement_policy = "kubernetes_default_scheduler_decides_at_runtime"
    else:
        display_name = str(mode).replace("_", " ").replace("-", " ").title()
        placement_policy = f"{str(mode)}_decides_at_runtime"

    return {
        "schedulerMode": str(mode),
        "schedulerName": str(scheduler_name) if scheduler_name else None,
        "schedulerDisplayName": display_name,
        "placementPolicy": placement_policy,
    }


def build_tenant_plans(
    repo_root: Path,
    scenario: dict[str, Any],
    output_root: Path,
    base_port: int,
    tenant_ports: dict[str, int],
    tenant_base_urls: dict[str, str],
    phase_profile: dict[str, Any],
) -> list[TenantExecutionPlan]:
    tenant_clusters = scenario.get("tenantClusters") or []
    if not isinstance(tenant_clusters, list) or not tenant_clusters:
        raise SystemExit("The scenario does not define tenantClusters; unable to build a multi-tenant Locust plan.")

    target_by_tenant = benchmark_targets_by_tenant(scenario)
    traffic_by_tenant = traffic_profiles_by_tenant(scenario)
    default_prompt = str(scenario.get("prompt") or "Reply with only READY.")
    default_temperature = str(scenario.get("temperature") if scenario.get("temperature") is not None else "0.1")
    default_timeout = str(scenario.get("requestTimeoutSeconds") if scenario.get("requestTimeoutSeconds") is not None else "120")
    warm_up_enabled = bool(phase_profile.get("warmUpEnabled", True))
    warm_up_duration = str(scenario.get("warmUpDuration") or phase_profile.get("warmUpDuration") or "30s")
    warm_up_users_mode = str(phase_profile.get("warmUpUsersMode") or "match_measurement")
    warm_up_spawn_rate_mode = str(phase_profile.get("warmUpSpawnRateMode") or "match_measurement")

    plans: list[TenantExecutionPlan] = []
    for ordinal, tenant in enumerate(tenant_clusters):
        if not isinstance(tenant, dict):
            continue
        tenant_id = str(tenant.get("tenantId") or f"tenant-{ordinal + 1}").strip()
        namespace = str(tenant.get("namespace") or "").strip()
        if not tenant_id or not namespace:
            raise SystemExit(f"Tenant entry at index {ordinal} must define both tenantId and namespace.")

        service_name = str(tenant.get("serviceName") or "localai-server").strip()
        model_name = str(tenant.get("modelName") or scenario.get("primaryResolvedModelName") or scenario.get("resolvedModelName") or "").strip()
        if not model_name:
            raise SystemExit(f"Tenant {tenant_id} does not define a LocalAI model name.")

        tenant_target = target_by_tenant.get(tenant_id) or {}
        access_mode = normalize_access_mode(
            tenant_target.get("accessMode")
            or tenant_target.get("baseUrlMode")
            or tenant.get("accessMode")
            or tenant.get("baseUrlMode")
            or scenario.get("benchmarkAccessMode")
        )
        gateway_settings = tenant_gateway_settings(tenant, tenant_target, tenant_id, namespace)
        tenant_traffic = tenant.get("trafficProfile") or traffic_by_tenant.get(tenant_id) or {}
        users = parse_int(tenant_traffic.get("users"), 1)
        spawn_rate = parse_float(tenant_traffic.get("spawnRate"), 1.0)
        run_time = str(tenant_traffic.get("runTime") or (scenario.get("resolvedWorkload") or {}).get("runTime") or "2m")
        wait_time_seconds = parse_float(tenant_traffic.get("waitTimeSeconds"), 2.0)
        warm_up_users = users if warm_up_users_mode == "match_measurement" else parse_int(phase_profile.get("warmUpUsers"), users)
        warm_up_spawn_rate = spawn_rate if warm_up_spawn_rate_mode == "match_measurement" else parse_float(phase_profile.get("warmUpSpawnRate"), spawn_rate)

        port = tenant_ports.get(tenant_id, base_port + ordinal)
        base_url = tenant_base_urls.get(tenant_id)
        if not base_url:
            raw_base_url = str(tenant_target.get("baseUrl") or "").strip()
            if raw_base_url and "__TENANT_PORT__" not in raw_base_url:
                base_url = raw_base_url
            else:
                base_url = f"http://localhost:{port}"

        tenant_output_subdir = str(tenant_target.get("outputSubdir") or tenant_id).replace("\\", "/").split("/")[-1]
        tenant_output_dir = output_root / tenant_output_subdir
        warm_up_csv_prefix = tenant_output_dir / "warmup"
        csv_prefix = tenant_output_dir / "measurement"
        environment = {
            "LOCALAI_MODEL": model_name,
            "LOCALAI_PROMPT": default_prompt,
            "LOCALAI_TEMPERATURE": default_temperature,
            "LOCALAI_REQUEST_TIMEOUT_SECONDS": default_timeout,
            "LOCALAI_WAIT_TIME_SECONDS": str(wait_time_seconds),
            "LOCALAI_STARTUP_MODEL_CHECK_ENABLED": "true",
        }
        host_header = gateway_settings["hostHeader"] if access_mode == "istio_gateway_routed" else str(tenant_target.get("hostHeader") or "").strip()
        if host_header:
            environment["LOCALAI_HTTP_HOST_HEADER"] = host_header
        for key, value in (tenant_traffic.get("environment") or {}).items():
            environment[str(key)] = str(value)
        environment["LOCALAI_WAIT_TIME_SECONDS"] = str(wait_time_seconds)

        plans.append(
            TenantExecutionPlan(
                tenant_id=tenant_id,
                namespace=namespace,
                service_name=service_name,
                model_name=model_name,
                base_url=base_url,
                access_mode=access_mode,
                host_header=host_header,
                port_forward_namespace=gateway_settings["namespace"] if access_mode == "istio_gateway_routed" else namespace,
                port_forward_service_name=gateway_settings["serviceName"] if access_mode == "istio_gateway_routed" else service_name,
                port_forward_remote_port=gateway_settings["remotePort"] if access_mode == "istio_gateway_routed" else DEFAULT_REMOTE_PORT,
                port_forward_target_kind=gateway_settings["targetKind"] if access_mode == "istio_gateway_routed" else "localai_service",
                users=users,
                spawn_rate=spawn_rate,
                run_time=run_time,
                wait_time_seconds=wait_time_seconds,
                warm_up_enabled=warm_up_enabled,
                warm_up_users=warm_up_users,
                warm_up_spawn_rate=warm_up_spawn_rate,
                warm_up_duration=warm_up_duration,
                output_dir=tenant_output_dir,
                warm_up_csv_prefix=warm_up_csv_prefix,
                csv_prefix=csv_prefix,
                environment=environment,
            )
        )

    if not plans:
        raise SystemExit("No valid tenant execution plans were resolved from the scenario.")
    return plans


def is_localhost_url(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.hostname or "") in {"localhost", "127.0.0.1", "::1"}


def port_from_url(url: str) -> int:
    parsed = urlparse(url)
    if parsed.port is not None:
        return int(parsed.port)
    return 443 if parsed.scheme == "https" else 80


def wait_local_port(host: str, port: int, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def request_headers(plan: TenantExecutionPlan | None = None) -> dict[str, str]:
    if plan is not None and plan.host_header:
        return {"Host": plan.host_header}
    return {}


def wait_http_ready(url: str, timeout_seconds: int, headers: dict[str, str] | None = None) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            request = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(request, timeout=5) as response:
                if 200 <= response.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(1)
    return False


def http_json_get(url: str, timeout_seconds: int, headers: dict[str, str] | None = None) -> tuple[bool, int | None, dict[str, Any] | None, str | None]:
    try:
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = int(response.status)
            raw = response.read().decode("utf-8", errors="replace")
            payload = json.loads(raw) if raw.strip() else {}
            return 200 <= status < 300, status, payload if isinstance(payload, dict) else {"payload": payload}, None
    except Exception as exc:
        return False, None, None, str(exc)


def check_local_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def build_kubectl_command(kubeconfig: Path | None, args: list[str]) -> list[str]:
    command = ["kubectl"]
    if kubeconfig is not None:
        command.extend(["--kubeconfig", str(kubeconfig)])
    command.extend(args)
    return command


def service_selector_to_label_selector(selector: dict[str, Any] | None) -> str | None:
    if not selector:
        return None
    items: list[str] = []
    for key, value in sorted(selector.items()):
        key_text = str(key).strip()
        value_text = str(value).strip()
        if key_text and value_text:
            items.append(f"{key_text}={value_text}")
    return ",".join(items) if items else None


def get_service_selector(kubeconfig: Path | None, namespace: str, service_name: str) -> dict[str, str] | None:
    command = build_kubectl_command(
        kubeconfig,
        ["get", "service", service_name, "-n", namespace, "-o", "json"],
    )
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=10)
    except Exception:
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    selector = (payload.get("spec") or {}).get("selector")
    if not isinstance(selector, dict) or not selector:
        return None
    resolved: dict[str, str] = {}
    for key, value in selector.items():
        key_text = str(key).strip()
        value_text = str(value).strip()
        if key_text and value_text:
            resolved[key_text] = value_text
    return resolved or None


def wait_service_endpoints(kubeconfig: Path | None, namespace: str, service_name: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    endpoint_command = build_kubectl_command(
        kubeconfig,
        [
            "get",
            "endpointslice",
            "-n",
            namespace,
            "-l",
            f"kubernetes.io/service-name={service_name}",
            "-o",
            "jsonpath={.items[*].endpoints[*].addresses[*]}",
        ],
    )
    while time.time() < deadline:
        endpoints = subprocess.run(endpoint_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if endpoints.returncode == 0 and endpoints.stdout.strip():
            return
        time.sleep(1)
    raise RuntimeError(f"Timeout while waiting for service/{service_name} endpoints in namespace {namespace}.")


def wait_kubernetes_backend_ready(kubeconfig: Path | None, plan: TenantExecutionPlan, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    rollout_command = build_kubectl_command(
        kubeconfig,
        ["rollout", "status", f"deployment/{plan.service_name}", "-n", plan.namespace, "--timeout=5s"],
    )
    endpoint_command = build_kubectl_command(
        kubeconfig,
        [
            "get",
            "endpointslice",
            "-n",
            plan.namespace,
            "-l",
            f"kubernetes.io/service-name={plan.service_name}",
            "-o",
            "jsonpath={.items[*].endpoints[*].addresses[*]}",
        ],
    )
    last_selector = None

    while time.time() < deadline:
        rollout = subprocess.run(rollout_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        if rollout.returncode != 0:
            time.sleep(1)
            continue

        service_selector = get_service_selector(kubeconfig, plan.namespace, plan.service_name)
        label_selector = service_selector_to_label_selector(service_selector)
        if label_selector:
            last_selector = label_selector
            pod_wait_command = build_kubectl_command(
                kubeconfig,
                ["wait", "--for=condition=Ready", "pod", "-l", label_selector, "-n", plan.namespace, "--timeout=5s"],
            )
            pod_wait = subprocess.run(pod_wait_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
            if pod_wait.returncode != 0:
                time.sleep(1)
                continue

        endpoints = subprocess.run(endpoint_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if endpoints.returncode == 0 and endpoints.stdout.strip():
            return
        time.sleep(1)

    selector_detail = f" selector={last_selector}" if last_selector else " selector=unresolved"
    raise RuntimeError(
        f"Timeout while waiting for backend service/{plan.service_name} in namespace {plan.namespace} ({selector_detail})."
    )


def start_port_forward(
    repo_root: Path,
    kubeconfig: Path | None,
    plan: TenantExecutionPlan,
    remote_port: int,
    allow_existing: bool,
    readiness_timeout_seconds: int,
    run_id: str,
) -> RunningPortForward | None:
    if not is_localhost_url(plan.base_url):
        return None
    local_port = port_from_url(plan.base_url)
    if not check_local_port_available(local_port):
        if allow_existing:
            readiness_url = f"{plan.base_url.rstrip('/')}/v1/models"
            if wait_http_ready(readiness_url, readiness_timeout_seconds, request_headers(plan)):
                return None
        raise RuntimeError(
            f"Local port {local_port} is already in use for tenant {plan.tenant_id}. "
            "Use --reuse-existing-port-forward only when the existing listener targets the expected service."
        )

    wait_kubernetes_backend_ready(kubeconfig, plan, readiness_timeout_seconds)
    if plan.port_forward_service_name != plan.service_name or plan.port_forward_namespace != plan.namespace:
        wait_service_endpoints(kubeconfig, plan.port_forward_namespace, plan.port_forward_service_name, readiness_timeout_seconds)

    runtime_root = repo_root / "results" / "_runtime" / "port-forward" / run_id
    runtime_root.mkdir(parents=True, exist_ok=True)
    safe_tenant = plan.tenant_id.replace("/", "-")
    stdout_path = runtime_root / f"{safe_tenant}_{plan.port_forward_service_name}_{local_port}_stdout.log"
    stderr_path = runtime_root / f"{safe_tenant}_{plan.port_forward_service_name}_{local_port}_stderr.log"
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    command = build_kubectl_command(
        kubeconfig,
        ["port-forward", "-n", plan.port_forward_namespace, f"service/{plan.port_forward_service_name}", f"{local_port}:{plan.port_forward_remote_port}"],
    )
    process = subprocess.Popen(command, stdout=stdout_handle, stderr=stderr_handle, text=True)
    stdout_handle.close()
    stderr_handle.close()

    if not wait_local_port("127.0.0.1", local_port, 30):
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        raise RuntimeError(f"Timeout while opening local port-forward for tenant {plan.tenant_id} on port {local_port}.")

    readiness_url = f"{plan.base_url.rstrip('/')}/v1/models"
    if not wait_http_ready(readiness_url, readiness_timeout_seconds, request_headers(plan)):
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        raise RuntimeError(f"Timeout while waiting for LocalAI readiness through {readiness_url}.")

    return RunningPortForward(
        tenant_id=plan.tenant_id,
        namespace=plan.port_forward_namespace,
        service_name=plan.port_forward_service_name,
        local_port=local_port,
        remote_port=plan.port_forward_remote_port,
        target_kind=plan.port_forward_target_kind,
        process=process,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def stop_port_forwards(port_forwards: list[RunningPortForward]) -> None:
    for item in port_forwards:
        if item.process.poll() is not None:
            continue
        item.process.terminate()
    for item in port_forwards:
        if item.process.poll() is not None:
            continue
        try:
            item.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            item.process.kill()


def phase_csv_prefix(plan: TenantExecutionPlan, phase: str) -> Path:
    return plan.warm_up_csv_prefix if phase == "warmup" else plan.csv_prefix


def phase_run_time(plan: TenantExecutionPlan, phase: str) -> str:
    return plan.warm_up_duration if phase == "warmup" else plan.run_time


def phase_users(plan: TenantExecutionPlan, phase: str) -> int:
    return plan.warm_up_users if phase == "warmup" else plan.users


def phase_spawn_rate(plan: TenantExecutionPlan, phase: str) -> float:
    return plan.warm_up_spawn_rate if phase == "warmup" else plan.spawn_rate


def build_locust_command(locust_command: str, locust_file: Path, plan: TenantExecutionPlan, phase: str) -> list[str]:
    return [
        locust_command,
        "-f",
        str(locust_file),
        "--host",
        plan.base_url,
        "--headless",
        "--users",
        str(phase_users(plan, phase)),
        "--spawn-rate",
        str(phase_spawn_rate(plan, phase)),
        "--run-time",
        phase_run_time(plan, phase),
        "--csv",
        str(phase_csv_prefix(plan, phase)),
        "--csv-full-history",
    ]


def tenant_artifacts(plan: TenantExecutionPlan) -> dict[str, str]:
    return {
        "outputDir": str(plan.output_dir),
        "warmUpCsvPrefix": str(plan.warm_up_csv_prefix),
        "warmUpStatsCsv": str(plan.output_dir / "warmup_stats.csv"),
        "warmUpFailuresCsv": str(plan.output_dir / "warmup_failures.csv"),
        "warmUpExceptionsCsv": str(plan.output_dir / "warmup_exceptions.csv"),
        "warmUpStatsHistoryCsv": str(plan.output_dir / "warmup_stats_history.csv"),
        "measurementCsvPrefix": str(plan.csv_prefix),
        "statsCsv": str(plan.output_dir / "measurement_stats.csv"),
        "failuresCsv": str(plan.output_dir / "measurement_failures.csv"),
        "exceptionsCsv": str(plan.output_dir / "measurement_exceptions.csv"),
        "statsHistoryCsv": str(plan.output_dir / "measurement_stats_history.csv"),
        "tenantBenchmarkManifest": str(plan.output_dir / "tenant-benchmark-manifest.json"),
        "tenantBenchmarkSummaryJson": str(plan.output_dir / "tenant-benchmark-summary.json"),
        "tenantBenchmarkSummaryText": str(plan.output_dir / "tenant-benchmark-summary.txt"),
        "tenantExecutionStatus": str(plan.output_dir / "tenant-execution-status.json"),
    }


def to_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_measurement_summary(stats_csv: Path, failures_csv: Path) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "statsCsv": str(stats_csv),
        "failuresCsv": str(failures_csv),
        "targetType": TARGET_REQUEST_TYPE,
        "targetName": TARGET_REQUEST_NAME,
        "statsPresent": stats_csv.exists(),
        "targetRequestCount": 0,
        "aggregatedRequestCount": 0,
        "failureCount": 0,
        "validTargetRequestsPresent": False,
    }
    if not stats_csv.exists():
        evidence["classification"] = "stats_csv_missing"
        return evidence

    try:
        with stats_csv.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except Exception as exc:
        evidence["classification"] = "stats_csv_unreadable"
        evidence["error"] = str(exc)
        return evidence

    target_row: dict[str, str] | None = None
    aggregated_row: dict[str, str] | None = None
    for row in rows:
        row_type = (row.get("Type") or "").strip()
        row_name = (row.get("Name") or "").strip()
        if row_name == "Aggregated":
            aggregated_row = row
        if row_type == TARGET_REQUEST_TYPE and row_name == TARGET_REQUEST_NAME:
            target_row = row

    if aggregated_row is not None:
        aggregated_count = to_number(aggregated_row.get("Request Count"))
        if aggregated_count is not None:
            evidence["aggregatedRequestCount"] = int(round(aggregated_count))

    if target_row is not None:
        target_count = to_number(target_row.get("Request Count"))
        failure_count = to_number(target_row.get("Failure Count"))
        evidence["targetRequestCount"] = int(round(target_count or 0))
        evidence["failureCount"] = int(round(failure_count or 0))
        evidence["validTargetRequestsPresent"] = bool(target_count and target_count > 0)
        for output_key, csv_key in {
            "averageResponseTimeMs": "Average Response Time",
            "medianResponseTimeMs": "Median Response Time",
            "minResponseTimeMs": "Min Response Time",
            "maxResponseTimeMs": "Max Response Time",
            "requestsPerSecond": "Requests/s",
            "failuresPerSecond": "Failures/s",
            "p95ResponseTimeMs": "95%",
            "p99ResponseTimeMs": "99%",
        }.items():
            value = to_number(target_row.get(csv_key))
            if value is not None:
                evidence[output_key] = value
        evidence["classification"] = "target_request_row_present"
    else:
        evidence["classification"] = "target_request_row_missing"

    return evidence


def run_locust_phase_processes(
    locust_command: str,
    locust_file: Path,
    plans: list[TenantExecutionPlan],
    phase: str,
) -> list[dict[str, Any]]:
    running: list[tuple[TenantExecutionPlan, subprocess.Popen[Any], list[str]]] = []
    results: list[dict[str, Any]] = []
    for plan in plans:
        plan.output_dir.mkdir(parents=True, exist_ok=True)
        command = build_locust_command(locust_command, locust_file, plan, phase)
        env = os.environ.copy()
        env.update(plan.environment)
        env["LOCALAI_STARTUP_MODEL_CHECK_ENABLED"] = "true" if phase == "warmup" else "false"
        print(f"Starting Locust {phase} for {plan.tenant_id} ({plan.namespace}) -> {plan.base_url}", flush=True)
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, env=env, text=True)
        running.append((plan, process, command))

    for plan, process, command in running:
        exit_code = process.wait()
        print(f"Completed Locust {phase} for {plan.tenant_id} ({plan.namespace}) with exitCode={exit_code}", flush=True)
        prefix = phase_csv_prefix(plan, phase)
        result = {
            "tenantId": plan.tenant_id,
            "namespace": plan.namespace,
            "phase": phase,
            "status": "passed" if exit_code == 0 else "failed",
            "exitCode": exit_code,
            "command": command,
            "baseUrl": plan.base_url,
            "accessMode": plan.access_mode,
            "hostHeader": plan.host_header or None,
            "portForwardTarget": {
                "namespace": plan.port_forward_namespace,
                "serviceName": plan.port_forward_service_name,
                "remotePort": plan.port_forward_remote_port,
                "targetKind": plan.port_forward_target_kind,
            },
            "modelName": plan.model_name,
            "users": phase_users(plan, phase),
            "spawnRate": phase_spawn_rate(plan, phase),
            "runTime": phase_run_time(plan, phase),
            "waitTimeSeconds": plan.wait_time_seconds,
            "artifacts": {
                "csvPrefix": str(prefix),
                "statsCsv": str(prefix.with_name(prefix.name + "_stats.csv")),
                "failuresCsv": str(prefix.with_name(prefix.name + "_failures.csv")),
                "exceptionsCsv": str(prefix.with_name(prefix.name + "_exceptions.csv")),
                "statsHistoryCsv": str(prefix.with_name(prefix.name + "_stats_history.csv")),
            },
            "metrics": read_measurement_summary(
                prefix.with_name(prefix.name + "_stats.csv"),
                prefix.with_name(prefix.name + "_failures.csv"),
            ),
        }
        results.append(result)
    return results


def dry_run_results(locust_command: str, locust_file: Path, plans: list[TenantExecutionPlan], phase: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for plan in plans:
        prefix = phase_csv_prefix(plan, phase)
        results.append(
            {
                "tenantId": plan.tenant_id,
                "namespace": plan.namespace,
                "phase": phase,
                "status": "planned",
                "exitCode": None,
                "command": build_locust_command(locust_command, locust_file, plan, phase),
                "baseUrl": plan.base_url,
                "accessMode": plan.access_mode,
                "hostHeader": plan.host_header or None,
                "portForwardTarget": {
                    "namespace": plan.port_forward_namespace,
                    "serviceName": plan.port_forward_service_name,
                    "remotePort": plan.port_forward_remote_port,
                    "targetKind": plan.port_forward_target_kind,
                },
                "modelName": plan.model_name,
                "users": phase_users(plan, phase),
                "spawnRate": phase_spawn_rate(plan, phase),
                "runTime": phase_run_time(plan, phase),
                "waitTimeSeconds": plan.wait_time_seconds,
                "artifacts": {
                    "csvPrefix": str(prefix),
                    "statsCsv": str(prefix.with_name(prefix.name + "_stats.csv")),
                    "failuresCsv": str(prefix.with_name(prefix.name + "_failures.csv")),
                    "exceptionsCsv": str(prefix.with_name(prefix.name + "_exceptions.csv")),
                    "statsHistoryCsv": str(prefix.with_name(prefix.name + "_stats_history.csv")),
                },
                "metrics": {
                    "classification": "planned",
                    "validTargetRequestsPresent": False,
                },
            }
        )
    return results


def run_kubectl_json(kubeconfig: Path | None, args: list[str]) -> dict[str, Any]:
    command = build_kubectl_command(kubeconfig, args)
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    except Exception as exc:
        return {"command": command, "status": "failed_to_execute", "error": str(exc)}
    payload: Any = None
    if completed.stdout.strip():
        try:
            payload = json.loads(completed.stdout)
        except Exception:
            payload = completed.stdout
    return {
        "command": command,
        "status": "completed" if completed.returncode == 0 else "failed",
        "exitCode": completed.returncode,
        "payload": payload,
        "stderr": completed.stderr.strip(),
    }


def run_kubectl_text(kubeconfig: Path | None, args: list[str]) -> dict[str, Any]:
    command = build_kubectl_command(kubeconfig, args)
    try:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    except Exception as exc:
        return {"command": command, "status": "failed_to_execute", "exitCode": None, "stdout": "", "stderr": str(exc)}
    return {
        "command": command,
        "status": "completed" if completed.returncode == 0 else "failed",
        "exitCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr.strip(),
    }


def safe_namespace_token(value: str) -> str:
    token = re.sub(r"[^a-z0-9._-]+", "-", str(value).strip().lower()).strip("-")
    return token or "namespace"


def cluster_stage_prefix(output_root: Path, stage: str) -> Path:
    return output_root / f"cluster_{stage}"


def cluster_manifest_path(output_root: Path, stage: str) -> Path:
    return output_root / f"cluster_{stage}_manifest.json"


def cluster_summary_path(output_root: Path, stage: str) -> Path:
    return output_root / f"cluster_{stage}_summary.txt"


def cluster_snapshot_path(output_root: Path, stage: str) -> Path:
    return output_root / f"cluster_{stage}_snapshot.json"


def cluster_capture_specs(output_root: Path, stage: str, namespaces: list[str]) -> list[dict[str, Any]]:
    prefix = cluster_stage_prefix(output_root, stage)
    primary_namespace = namespaces[0] if namespaces else "localai-benchmark"
    specs: list[dict[str, Any]] = [
        {"scope": "cluster", "suffix": "nodes-wide.txt", "format": "text", "commandArgs": ["get", "nodes", "-o", "wide"]},
        {"scope": "cluster", "suffix": "nodes.json", "format": "json", "commandArgs": ["get", "nodes", "-o", "json"]},
        {"scope": "cluster", "suffix": "top-nodes.txt", "format": "text", "commandArgs": ["top", "nodes"]},
    ]
    namespace_artifacts = [
        ("pods-wide.txt", "text", ["get", "pods", "-n", "{namespace}", "-o", "wide"]),
        ("pods.json", "json", ["get", "pods", "-n", "{namespace}", "-o", "json"]),
        ("top-pods.txt", "text", ["top", "pods", "-n", "{namespace}"]),
        ("top-pods-containers.txt", "text", ["top", "pods", "-n", "{namespace}", "--containers"]),
        ("services.txt", "text", ["get", "svc", "-n", "{namespace}"]),
        ("events.txt", "text", ["get", "events", "-n", "{namespace}"]),
        ("events.json", "json", ["get", "events", "-n", "{namespace}", "-o", "json"]),
        ("pods-describe.txt", "text", ["describe", "pods", "-n", "{namespace}"]),
    ]
    for namespace in namespaces or [primary_namespace]:
        namespace_prefix = "" if namespace == primary_namespace else f"{safe_namespace_token(namespace)}_"
        for suffix, output_format, args in namespace_artifacts:
            specs.append({
                "scope": "namespace",
                "namespace": namespace,
                "suffix": f"{namespace_prefix}{suffix}",
                "format": output_format,
                "commandArgs": [namespace if item == "{namespace}" else item for item in args],
            })
    for spec in specs:
        spec["path"] = Path(str(prefix) + "_" + str(spec["suffix"]))
    return specs


def cluster_expected_artifact_paths(output_root: Path, stage: str, namespaces: list[str]) -> dict[str, Any]:
    specs = cluster_capture_specs(output_root, stage, namespaces)
    return {
        "manifest": cluster_manifest_path(output_root, stage),
        "summary": cluster_summary_path(output_root, stage),
        "snapshot": cluster_snapshot_path(output_root, stage),
        "artifacts": [Path(spec["path"]) for spec in specs],
    }


def write_kubectl_text_artifact(path: Path, result: dict[str, Any]) -> None:
    if result.get("status") == "completed":
        content = str(result.get("stdout") or "")
        if not content.strip():
            content = "(command completed with no output)\n"
        write_text(path, content if content.endswith("\n") else content + "\n")
        return
    lines = [
        "Kubernetes command did not complete successfully.",
        f"Status: {result.get('status')}",
        f"Exit code: {result.get('exitCode')}",
        f"Command: {' '.join(str(item) for item in result.get('command') or [])}",
        "",
        "Standard output:",
        str(result.get("stdout") or ""),
        "",
        "Standard error:",
        str(result.get("stderr") or result.get("error") or ""),
    ]
    write_text(path, "\n".join(lines).rstrip() + "\n")


def write_planned_cluster_artifact(path: Path, spec: dict[str, Any], stage: str) -> dict[str, Any]:
    command = build_kubectl_command(None, list(spec.get("commandArgs") or []))
    payload = {
        "schemaVersion": "multi-tenant-cluster-command-artifact/v1",
        "stage": stage,
        "status": "planned",
        "scope": spec.get("scope"),
        "namespace": spec.get("namespace"),
        "format": spec.get("format"),
        "command": command,
        "path": str(path),
    }
    if spec.get("format") == "json":
        write_json(path, payload)
    else:
        write_text(
            path,
            "Planned Kubernetes command artifact.\n"
            f"Stage: {stage}\n"
            f"Scope: {spec.get('scope')}\n"
            f"Namespace: {spec.get('namespace') or 'n/a'}\n"
            f"Command: {' '.join(command)}\n",
        )
    return payload


def capture_cluster_snapshot(kubeconfig: Path | None, plans: list[TenantExecutionPlan], stage: str, output_root: Path, dry_run: bool) -> dict[str, Any]:
    namespaces = sorted({plan.namespace for plan in plans}) or ["localai-benchmark"]
    manifest_path = cluster_manifest_path(output_root, stage)
    summary_path = cluster_summary_path(output_root, stage)
    snapshot_path = cluster_snapshot_path(output_root, stage)
    specs = cluster_capture_specs(output_root, stage, namespaces)
    started_at = utc_now()
    artifact_records: list[dict[str, Any]] = []
    nodes_payload: dict[str, Any] | None = None
    tenant_namespace_payloads: dict[str, dict[str, Any]] = {namespace: {} for namespace in namespaces}

    for spec in specs:
        path = Path(spec["path"])
        command_args = list(spec.get("commandArgs") or [])
        if dry_run:
            result = write_planned_cluster_artifact(path, spec, stage)
        elif spec.get("format") == "json":
            result = run_kubectl_json(kubeconfig, command_args)
            write_json(path, {
                "schemaVersion": "multi-tenant-cluster-command-artifact/v1",
                "stage": stage,
                "scope": spec.get("scope"),
                "namespace": spec.get("namespace"),
                "format": "json",
                **result,
            })
        else:
            result = run_kubectl_text(kubeconfig, command_args)
            write_kubectl_text_artifact(path, result)

        record = {
            "scope": spec.get("scope"),
            "namespace": spec.get("namespace"),
            "suffix": spec.get("suffix"),
            "format": spec.get("format"),
            "command": result.get("command") or build_kubectl_command(kubeconfig, command_args),
            "status": result.get("status"),
            "exitCode": result.get("exitCode"),
            "path": str(path),
        }
        if result.get("error"):
            record["error"] = result.get("error")
        if result.get("stderr"):
            record["stderr"] = result.get("stderr")
        artifact_records.append(record)

        if spec.get("format") == "json" and isinstance(result, dict):
            payload = result.get("payload")
            suffix = str(spec.get("suffix") or "")
            namespace = spec.get("namespace")
            if suffix == "nodes.json":
                nodes_payload = result
            elif namespace and suffix.endswith("pods.json"):
                tenant_namespace_payloads.setdefault(str(namespace), {})["pods"] = result
            elif namespace and suffix.endswith("events.json"):
                tenant_namespace_payloads.setdefault(str(namespace), {})["events"] = result

    completed_at = utc_now()
    failed_count = sum(1 for item in artifact_records if item.get("status") not in {"completed", "planned"})
    manifest = {
        "schemaVersion": "multi-tenant-cluster-capture-manifest/v1",
        "stage": stage,
        "status": "planned" if dry_run else ("captured" if failed_count == 0 else "captured_with_warnings"),
        "startedAt": started_at,
        "completedAt": completed_at,
        "namespaces": namespaces,
        "artifactCount": len(artifact_records),
        "failedArtifactCount": failed_count,
        "artifacts": artifact_records,
        "snapshotPath": str(snapshot_path),
        "summaryPath": str(summary_path),
    }
    write_json(manifest_path, manifest)

    summary_lines = [
        "Cluster capture summary",
        "=======================",
        f"Stage: {stage}",
        f"Status: {manifest['status']}",
        f"Namespaces: {', '.join(namespaces)}",
        f"Artifacts: {len(artifact_records)}",
        f"Failed artifacts: {failed_count}",
        "",
        "Artifact status:",
    ]
    for item in artifact_records:
        namespace_text = f" namespace={item.get('namespace')}" if item.get("namespace") else ""
        summary_lines.append(f" - {item.get('suffix')}:{namespace_text} status={item.get('status')} exitCode={item.get('exitCode')}")
    write_text(summary_path, "\n".join(summary_lines) + "\n")

    snapshot_payload = {
        "schemaVersion": "multi-tenant-cluster-snapshot/v1",
        "stage": stage,
        "status": manifest["status"],
        "capturedAt": completed_at,
        "namespaces": namespaces,
        "manifestPath": str(manifest_path),
        "summaryPath": str(summary_path),
        "artifactRecords": artifact_records,
        "cluster": {
            "nodes": nodes_payload or {"status": "planned" if dry_run else "not_collected"},
        },
        "tenantNamespaces": tenant_namespace_payloads,
    }
    write_json(snapshot_path, snapshot_payload)
    return snapshot_payload


def write_protocol_files(
    repo_root: Path,
    output_root: Path,
    run_id: str,
    scenario: dict[str, Any],
    scenario_config: Path,
    locust_file: Path,
    phase_profile: dict[str, Any],
    plans: list[TenantExecutionPlan],
) -> dict[str, Any]:
    payload = {
        "schemaVersion": "multi-tenant-locust-protocol/v1",
        "runId": run_id,
        "scenarioId": scenario.get("scenarioId") or scenario_config.stem,
        "scenarioConfigPath": rel_to_repo(repo_root, scenario_config),
        "createdAt": utc_now(),
        "launcherName": "run-multi-tenant-locust",
        "locustFile": rel_to_repo(repo_root, locust_file),
        "phaseProfile": phase_profile,
        "executionModel": {
            "replicaScope": "scenario_level",
            "tenantExecutionMode": "concurrent_locust_process_per_tenant",
            "placementPolicy": scheduler_runtime_context(scenario)["placementPolicy"],
            "schedulerMode": scheduler_runtime_context(scenario)["schedulerMode"],
            "schedulerName": scheduler_runtime_context(scenario)["schedulerName"],
            "schedulerDisplayName": scheduler_runtime_context(scenario)["schedulerDisplayName"],
        },
        "tenantPlans": [
            {
                "tenantId": plan.tenant_id,
                "namespace": plan.namespace,
                "serviceName": plan.service_name,
                "baseUrl": plan.base_url,
                "modelName": plan.model_name,
                "measurement": {
                    "users": plan.users,
                    "spawnRate": plan.spawn_rate,
                    "runTime": plan.run_time,
                    "csvPrefix": rel_to_repo(repo_root, plan.csv_prefix),
                },
                "warmUp": {
                    "enabled": plan.warm_up_enabled,
                    "users": plan.warm_up_users,
                    "spawnRate": plan.warm_up_spawn_rate,
                    "runTime": plan.warm_up_duration,
                    "csvPrefix": rel_to_repo(repo_root, plan.warm_up_csv_prefix),
                },
                "waitTimeSeconds": plan.wait_time_seconds,
                "outputDir": rel_to_repo(repo_root, plan.output_dir),
            }
            for plan in plans
        ],
        "expectedArtifacts": {
            "protocolJson": rel_to_repo(repo_root, output_root / "protocol.json"),
            "protocolText": rel_to_repo(repo_root, output_root / "protocol.txt"),
            "precheckJson": rel_to_repo(repo_root, output_root / "precheck.json"),
            "precheckText": rel_to_repo(repo_root, output_root / "precheck.txt"),
            "phasesJson": rel_to_repo(repo_root, output_root / "phases.json"),
            "metricSetJson": rel_to_repo(repo_root, output_root / "metric-set.json"),
            "metricSetText": rel_to_repo(repo_root, output_root / "metric-set.txt"),
            "clusterPreManifest": rel_to_repo(repo_root, cluster_manifest_path(output_root, "pre")),
            "clusterPreSummary": rel_to_repo(repo_root, cluster_summary_path(output_root, "pre")),
            "clusterPreSnapshot": rel_to_repo(repo_root, cluster_snapshot_path(output_root, "pre")),
            "clusterPreArtifacts": [
                rel_to_repo(repo_root, item)
                for item in cluster_expected_artifact_paths(output_root, "pre", [plan.namespace for plan in plans])["artifacts"]
            ],
            "clusterPostManifest": rel_to_repo(repo_root, cluster_manifest_path(output_root, "post")),
            "clusterPostSummary": rel_to_repo(repo_root, cluster_summary_path(output_root, "post")),
            "clusterPostSnapshot": rel_to_repo(repo_root, cluster_snapshot_path(output_root, "post")),
            "clusterPostArtifacts": [
                rel_to_repo(repo_root, item)
                for item in cluster_expected_artifact_paths(output_root, "post", [plan.namespace for plan in plans])["artifacts"]
            ],
        },
    }
    write_json(output_root / "protocol.json", payload)
    protocol_title = f"{payload['executionModel']['schedulerDisplayName']} multi-tenant benchmark protocol"
    lines = [
        protocol_title,
        "=" * len(protocol_title),
        f"Run ID: {run_id}",
        f"Scenario: {payload['scenarioId']}",
        f"Scenario config: {payload['scenarioConfigPath']}",
        f"Execution model: {payload['executionModel']['tenantExecutionMode']}",
        f"Scheduler mode: {payload['executionModel']['schedulerMode']}",
        f"Scheduler name: {payload['executionModel']['schedulerName']}",
        f"Placement policy: {payload['executionModel']['placementPolicy']}",
        "",
        "Tenant plans:",
    ]
    for tenant in payload["tenantPlans"]:
        lines.append(
            f" - {tenant['tenantId']} ({tenant['namespace']}): model={tenant['modelName']}, "
            f"measurement={tenant['measurement']['users']} users/{tenant['measurement']['runTime']}, "
            f"warm-up={'enabled' if tenant['warmUp']['enabled'] else 'disabled'}"
        )
    write_text(output_root / "protocol.txt", "\n".join(lines) + "\n")
    return payload


def write_precheck_files(
    repo_root: Path,
    output_root: Path,
    plans: list[TenantExecutionPlan],
    dry_run: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for plan in plans:
        if dry_run:
            checks.append({
                "tenantId": plan.tenant_id,
                "namespace": plan.namespace,
                "baseUrl": plan.base_url,
                "accessMode": plan.access_mode,
                "hostHeader": plan.host_header or None,
                "portForwardTarget": {
                    "namespace": plan.port_forward_namespace,
                    "serviceName": plan.port_forward_service_name,
                    "remotePort": plan.port_forward_remote_port,
                    "targetKind": plan.port_forward_target_kind,
                },
                "modelName": plan.model_name,
                "status": "planned",
                "passed": True,
            })
            continue
        url = f"{plan.base_url.rstrip('/')}/v1/models"
        ok, status_code, payload, error = http_json_get(url, min(max(timeout_seconds, 1), 30), request_headers(plan))
        model_ids: list[str] = []
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            model_ids = [str(item.get("id")) for item in payload["data"] if isinstance(item, dict) and item.get("id") is not None]
        checks.append({
            "tenantId": plan.tenant_id,
            "namespace": plan.namespace,
            "baseUrl": plan.base_url,
            "accessMode": plan.access_mode,
            "hostHeader": plan.host_header or None,
            "portForwardTarget": {
                "namespace": plan.port_forward_namespace,
                "serviceName": plan.port_forward_service_name,
                "remotePort": plan.port_forward_remote_port,
                "targetKind": plan.port_forward_target_kind,
            },
            "modelName": plan.model_name,
            "url": url,
            "statusCode": status_code,
            "modelsEndpointReady": ok,
            "modelExposed": plan.model_name in model_ids if model_ids else None,
            "modelIds": model_ids,
            "passed": bool(ok and (not model_ids or plan.model_name in model_ids)),
            "error": error,
        })
    passed = all(item.get("passed") is True for item in checks)
    payload = {
        "schemaVersion": "multi-tenant-locust-precheck/v1",
        "status": "passed" if passed else "failed",
        "createdAt": utc_now(),
        "summary": {
            "success": passed,
            "checkCount": len(checks),
            "failedChecks": [item for item in checks if item.get("passed") is not True],
        },
        "checks": checks,
    }
    write_json(output_root / "precheck.json", payload)
    lines = [
        "Multi-tenant benchmark precheck",
        "===============================",
        f"Status: {payload['status']}",
        f"Checks: {len(checks)}",
        "",
    ]
    for item in checks:
        lines.append(f" - {item.get('tenantId')}: passed={item.get('passed')}, baseUrl={item.get('baseUrl')}, model={item.get('modelName')}")
    write_text(output_root / "precheck.txt", "\n".join(lines) + "\n")
    return payload


def write_phases_file(output_root: Path, run_id: str, scenario_id: str, phases: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "schemaVersion": "multi-tenant-locust-phases/v1",
        "runId": run_id,
        "scenarioId": scenario_id,
        "createdAt": utc_now(),
        "phases": phases,
    }
    write_json(output_root / "phases.json", payload)
    return payload


def write_metric_set_files(
    repo_root: Path,
    output_root: Path,
    run_id: str,
    scenario: dict[str, Any],
    scenario_id: str,
    plans: list[TenantExecutionPlan],
    warmup_results: list[dict[str, Any]],
    measurement_results: list[dict[str, Any]],
    cluster_pre_path: Path,
    cluster_post_path: Path,
) -> dict[str, Any]:
    warmup_by_tenant = {item.get("tenantId"): item for item in warmup_results if isinstance(item, dict)}
    measurement_by_tenant = {item.get("tenantId"): item for item in measurement_results if isinstance(item, dict)}
    tenant_metrics: list[dict[str, Any]] = []
    for plan in plans:
        measurement = measurement_by_tenant.get(plan.tenant_id, {})
        warmup = warmup_by_tenant.get(plan.tenant_id, {})
        metric_payload = {
            "tenantId": plan.tenant_id,
            "namespace": plan.namespace,
            "modelName": plan.model_name,
            "warmUp": warmup.get("metrics") or {},
            "measurement": measurement.get("measurement") or measurement.get("metrics") or {},
            "artifacts": tenant_artifacts(plan),
        }
        tenant_metrics.append(metric_payload)

    payload = {
        "schemaVersion": "multi-tenant-locust-metric-set/v1",
        "runId": run_id,
        "scenarioId": scenario_id,
        "createdAt": utc_now(),
        "metricScope": "tenant_scoped_and_replica_scoped",
        "scheduler": scheduler_runtime_context(scenario),
        "targetRequestType": TARGET_REQUEST_TYPE,
        "targetRequestName": TARGET_REQUEST_NAME,
        "tenantMetrics": tenant_metrics,
        "clusterArtifacts": {
            "preManifest": rel_to_repo(repo_root, cluster_manifest_path(output_root, "pre")),
            "preSummary": rel_to_repo(repo_root, cluster_summary_path(output_root, "pre")),
            "preSnapshot": rel_to_repo(repo_root, cluster_pre_path),
            "preArtifacts": [
                rel_to_repo(repo_root, item)
                for item in cluster_expected_artifact_paths(output_root, "pre", [plan.namespace for plan in plans])["artifacts"]
            ],
            "postManifest": rel_to_repo(repo_root, cluster_manifest_path(output_root, "post")),
            "postSummary": rel_to_repo(repo_root, cluster_summary_path(output_root, "post")),
            "postSnapshot": rel_to_repo(repo_root, cluster_post_path),
            "postArtifacts": [
                rel_to_repo(repo_root, item)
                for item in cluster_expected_artifact_paths(output_root, "post", [plan.namespace for plan in plans])["artifacts"]
            ],
        },
        "clientArtifacts": [
            {
                "tenantId": plan.tenant_id,
                "warmUpStatsCsv": rel_to_repo(repo_root, plan.output_dir / "warmup_stats.csv"),
                "warmUpStatsHistoryCsv": rel_to_repo(repo_root, plan.output_dir / "warmup_stats_history.csv"),
                "measurementStatsCsv": rel_to_repo(repo_root, plan.output_dir / "measurement_stats.csv"),
                "measurementStatsHistoryCsv": rel_to_repo(repo_root, plan.output_dir / "measurement_stats_history.csv"),
            }
            for plan in plans
        ],
    }
    write_json(output_root / "metric-set.json", payload)
    metric_title = f"{payload['scheduler']['schedulerDisplayName']} multi-tenant metric set"
    lines = [
        metric_title,
        "=" * len(metric_title),
        f"Run ID: {run_id}",
        f"Scenario: {scenario_id}",
        f"Scheduler mode: {payload['scheduler']['schedulerMode']}",
        f"Scheduler name: {payload['scheduler']['schedulerName']}",
        "",
        "Tenant measurement metrics:",
    ]
    for item in tenant_metrics:
        measurement = item.get("measurement") or {}
        lines.append(
            f" - {item.get('tenantId')}: requests={measurement.get('targetRequestCount', 'n/a')}, "
            f"failures={measurement.get('failureCount', 'n/a')}, "
            f"meanMs={measurement.get('averageResponseTimeMs', 'n/a')}, "
            f"rps={measurement.get('requestsPerSecond', 'n/a')}"
        )
    write_text(output_root / "metric-set.txt", "\n".join(lines) + "\n")
    return payload


def write_tenant_benchmark_artifacts(
    repo_root: Path,
    output_root: Path,
    run_id: str,
    scenario: dict[str, Any],
    plans: list[TenantExecutionPlan],
    warmup_results: list[dict[str, Any]],
    measurement_results: list[dict[str, Any]],
    dry_run: bool,
) -> None:
    warmup_by_tenant = {item.get("tenantId"): item for item in warmup_results if isinstance(item, dict)}
    measurement_by_tenant = {item.get("tenantId"): item for item in measurement_results if isinstance(item, dict)}
    scenario_id = str(scenario.get("scenarioId") or "scenario")
    for plan in plans:
        plan.output_dir.mkdir(parents=True, exist_ok=True)
        warmup = warmup_by_tenant.get(plan.tenant_id, {})
        measurement = measurement_by_tenant.get(plan.tenant_id, {})
        manifest = {
            "schemaVersion": "tenant-benchmark-manifest/v1",
            "runId": run_id,
            "scenarioId": scenario_id,
            "tenantId": plan.tenant_id,
            "namespace": plan.namespace,
            "serviceName": plan.service_name,
            "baseUrl": plan.base_url,
            "accessMode": plan.access_mode,
            "hostHeader": plan.host_header or None,
            "portForwardTarget": {
                "namespace": plan.port_forward_namespace,
                "serviceName": plan.port_forward_service_name,
                "remotePort": plan.port_forward_remote_port,
                "targetKind": plan.port_forward_target_kind,
            },
            "modelName": plan.model_name,
            "dryRun": dry_run,
            "createdAt": utc_now(),
            "traffic": {
                "users": plan.users,
                "spawnRate": plan.spawn_rate,
                "runTime": plan.run_time,
                "waitTimeSeconds": plan.wait_time_seconds,
            },
            "warmUp": {
                "enabled": plan.warm_up_enabled,
                "users": plan.warm_up_users,
                "spawnRate": plan.warm_up_spawn_rate,
                "runTime": plan.warm_up_duration,
            },
            "artifacts": tenant_artifacts(plan),
            "commands": {
                "warmUp": warmup.get("command"),
                "measurement": measurement.get("command"),
            },
        }
        status_payload = {
            "schemaVersion": "tenant-execution-status/v1",
            "runId": run_id,
            "scenarioId": scenario_id,
            "tenantId": plan.tenant_id,
            "status": measurement.get("status") or ("planned" if dry_run else "not_executed"),
            "warmUpStatus": warmup.get("status"),
            "measurementStatus": measurement.get("status"),
            "warmUpExitCode": warmup.get("exitCode"),
            "measurementExitCode": measurement.get("exitCode"),
            "createdAt": utc_now(),
        }
        summary = {
            "schemaVersion": "tenant-benchmark-summary/v1",
            "runId": run_id,
            "scenarioId": scenario_id,
            "tenantId": plan.tenant_id,
            "namespace": plan.namespace,
            "status": status_payload["status"],
            "warmUp": warmup.get("metrics") or {},
            "measurement": measurement.get("measurement") or measurement.get("metrics") or {},
            "artifacts": tenant_artifacts(plan),
        }
        write_json(plan.output_dir / "tenant-benchmark-manifest.json", manifest)
        write_json(plan.output_dir / "tenant-execution-status.json", status_payload)
        write_json(plan.output_dir / "tenant-benchmark-summary.json", summary)
        lines = [
            "Tenant benchmark summary",
            "========================",
            f"Run ID: {run_id}",
            f"Scenario: {scenario_id}",
            f"Tenant: {plan.tenant_id}",
            f"Namespace: {plan.namespace}",
            f"Status: {summary['status']}",
            "",
            "Measurement:",
        ]
        measurement_metrics = summary.get("measurement") or {}
        lines.append(f" - target requests: {measurement_metrics.get('targetRequestCount', 'n/a')}")
        lines.append(f" - failures: {measurement_metrics.get('failureCount', 'n/a')}")
        lines.append(f" - average response time (ms): {measurement_metrics.get('averageResponseTimeMs', 'n/a')}")
        lines.append(f" - requests/s: {measurement_metrics.get('requestsPerSecond', 'n/a')}")
        write_text(plan.output_dir / "tenant-benchmark-summary.txt", "\n".join(lines) + "\n")


def summary_text(payload: dict[str, Any]) -> str:
    lines = [
        "Multi-tenant Locust execution summary",
        "=====================================",
        f"Run ID: {payload.get('runId')}",
        f"Scenario: {payload.get('scenarioId')}",
        f"Status: {payload.get('status')}",
        f"Started at: {payload.get('startedAt')}",
        f"Completed at: {payload.get('completedAt')}",
        f"Output root: {payload.get('outputRoot')}",
        "",
        "Tenant measurement results:",
    ]
    for tenant in payload.get("tenantResults") or []:
        measurement = tenant.get("measurement") or {}
        lines.append(
            " - {tenantId}: status={status}, exitCode={exitCode}, requests={requests}, failures={failures}, rps={rps}".format(
                tenantId=tenant.get("tenantId"),
                status=tenant.get("status"),
                exitCode=tenant.get("exitCode"),
                requests=measurement.get("targetRequestCount", "n/a"),
                failures=measurement.get("failureCount", "n/a"),
                rps=measurement.get("requestsPerSecond", "n/a"),
            )
        )
    lines.append("")
    return "\n".join(lines)


def copy_latest_aliases(output_root: Path, summary_json: Path, summary_txt: Path) -> None:
    shutil.copyfile(summary_json, output_root / "latest-multi-tenant-summary.json")
    shutil.copyfile(summary_txt, output_root / "latest-multi-tenant-summary.txt")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run concurrent Locust workloads for multiple LocalAI tenants.")
    parser.add_argument("--repo-root", default=".", help="Repository root directory.")
    parser.add_argument("--scenario-config", default=DEFAULT_SCENARIO_CONFIG, help="Scenario JSON path for the tenant-scoped benchmark.")
    parser.add_argument("--kubeconfig", default="", help="Optional kubeconfig path for tenant-scoped port-forwarding.")
    parser.add_argument("--locust-file", default=DEFAULT_LOCUST_FILE, help="Locust workload file path.")
    parser.add_argument("--locust-command", default="locust", help="Locust command name or executable path.")
    parser.add_argument("--phase-config", default="", help="Optional warm-up/measurement phase profile override.")
    parser.add_argument("--output-root", default="", help="Output root override. Defaults to scenario resultsRoot/outputSubdir.")
    parser.add_argument("--base-port", type=int, default=DEFAULT_BASE_PORT, help="First local port used for tenant port-forwards.")
    parser.add_argument("--remote-port", type=int, default=DEFAULT_REMOTE_PORT, help="Remote LocalAI service port.")
    parser.add_argument("--tenant-ports", default="", help="Comma-separated tenantId=port mapping.")
    parser.add_argument("--tenant-base-urls", default="", help="Comma-separated tenantId=http://host:port mapping.")
    parser.add_argument("--run-id", default="", help="Optional run identifier.")
    parser.add_argument("--skip-port-forward", action="store_true", help="Do not create kubectl port-forwards.")
    parser.add_argument("--reuse-existing-port-forward", action="store_true", help="Reuse already reachable localhost endpoints.")
    parser.add_argument("--readiness-timeout-seconds", type=int, default=180, help="Readiness timeout for services and local endpoints.")
    parser.add_argument("--dry-run", action="store_true", help="Write an execution plan without starting port-forwards or Locust.")
    parser.add_argument("--warm-up-only", action="store_true", help="Run only the configured warm-up phase and skip the official measurement phase. Use this for telemetry priming before controlled rescheduling.")
    parser.add_argument("--write-latest-aliases", action="store_true", help="Write latest summary aliases in the scenario output root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = resolve_repo_root(args.repo_root)
    scenario_config = resolve_path(repo_root, args.scenario_config, DEFAULT_SCENARIO_CONFIG)
    locust_file = resolve_path(repo_root, args.locust_file, DEFAULT_LOCUST_FILE)
    kubeconfig = resolve_path(repo_root, args.kubeconfig, args.kubeconfig) if args.kubeconfig else None

    if not scenario_config.is_file():
        raise SystemExit(f"Scenario config not found: {scenario_config}")
    if not locust_file.is_file():
        raise SystemExit(f"Locust file not found: {locust_file}")
    if kubeconfig is not None and not kubeconfig.is_file():
        raise SystemExit(f"Kubeconfig not found: {kubeconfig}")
    if not args.dry_run and shutil.which(args.locust_command) is None and not Path(args.locust_command).is_file():
        raise SystemExit(f"Locust command is not available: {args.locust_command}")
    if not args.dry_run and not args.skip_port_forward and shutil.which("kubectl") is None:
        raise SystemExit("kubectl is not available in PATH. Use --skip-port-forward only when tenant endpoints are already reachable.")

    scenario = load_json(scenario_config)
    scenario_id = str(scenario.get("scenarioId") or scenario_config.stem)
    run_id = args.run_id.strip() or f"{scenario_id}_{safe_stamp()}"
    output_root = scenario_output_root(repo_root, scenario, args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    phase_profile = load_phase_profile(repo_root, scenario, args.phase_config)
    tenant_ports = parse_tenant_ports(args.tenant_ports) if args.tenant_ports else {}
    tenant_base_urls = parse_key_value_map(args.tenant_base_urls) if args.tenant_base_urls else {}
    plans = build_tenant_plans(repo_root, scenario, output_root, args.base_port, tenant_ports, tenant_base_urls, phase_profile)

    started_at = utc_now()
    port_forwards: list[RunningPortForward] = []
    warmup_results: list[dict[str, Any]] = []
    tenant_results: list[dict[str, Any]] = []
    phase_records: list[dict[str, Any]] = []
    status = "passed"
    error: str | None = None
    precheck_payload: dict[str, Any] = {}
    cluster_pre_path = output_root / "cluster_pre_snapshot.json"
    cluster_post_path = output_root / "cluster_post_snapshot.json"

    write_protocol_files(repo_root, output_root, run_id, scenario, scenario_config, locust_file, phase_profile, plans)

    try:
        if args.dry_run:
            status = "planned"
            precheck_payload = write_precheck_files(repo_root, output_root, plans, True, args.readiness_timeout_seconds)
            capture_cluster_snapshot(kubeconfig, plans, "pre", output_root, True)
            if any(plan.warm_up_enabled for plan in plans):
                warmup_results = dry_run_results(args.locust_command, locust_file, plans, "warmup")
            if args.warm_up_only:
                tenant_results = []
            else:
                tenant_results = dry_run_results(args.locust_command, locust_file, plans, "measurement")
            capture_cluster_snapshot(kubeconfig, plans, "post", output_root, True)
            phase_records.extend([
                {"phase": "precheck", "status": precheck_payload.get("status"), "completedAt": utc_now()},
                {"phase": "cluster_pre_snapshot", "status": "planned", "artifact": rel_to_repo(repo_root, cluster_pre_path)},
                {"phase": "warmup", "status": "planned" if warmup_results else "skipped", "tenantResultCount": len(warmup_results)},
                {"phase": "measurement", "status": "skipped_telemetry_priming_only" if args.warm_up_only else "planned", "tenantResultCount": len(tenant_results)},
                {"phase": "cluster_post_snapshot", "status": "planned", "artifact": rel_to_repo(repo_root, cluster_post_path)},
            ])
        else:
            if not args.skip_port_forward:
                for plan in plans:
                    item = start_port_forward(
                        repo_root=repo_root,
                        kubeconfig=kubeconfig,
                        plan=plan,
                        remote_port=args.remote_port,
                        allow_existing=args.reuse_existing_port_forward,
                        readiness_timeout_seconds=args.readiness_timeout_seconds,
                        run_id=run_id,
                    )
                    if item is not None:
                        port_forwards.append(item)

            precheck_payload = write_precheck_files(repo_root, output_root, plans, False, args.readiness_timeout_seconds)
            phase_records.append({"phase": "precheck", "status": precheck_payload.get("status"), "completedAt": utc_now()})
            if precheck_payload.get("status") != "passed":
                status = "failed"
                error = "precheck_failed"
            else:
                capture_cluster_snapshot(kubeconfig, plans, "pre", output_root, False)
                phase_records.append({"phase": "cluster_pre_snapshot", "status": "captured", "artifact": rel_to_repo(repo_root, cluster_pre_path)})

                if any(plan.warm_up_enabled for plan in plans):
                    warmup_started = utc_now()
                    warmup_results = run_locust_phase_processes(args.locust_command, locust_file, [plan for plan in plans if plan.warm_up_enabled], "warmup")
                    phase_records.append({
                        "phase": "warmup",
                        "status": "passed" if all(item.get("exitCode") == 0 for item in warmup_results) else "failed",
                        "startedAt": warmup_started,
                        "completedAt": utc_now(),
                        "tenantResultCount": len(warmup_results),
                    })
                else:
                    phase_records.append({"phase": "warmup", "status": "skipped", "tenantResultCount": 0})

                if args.warm_up_only:
                    tenant_results = []
                    phase_records.append({
                        "phase": "measurement",
                        "status": "skipped_telemetry_priming_only",
                        "tenantResultCount": 0,
                    })
                else:
                    measurement_started = utc_now()
                    tenant_results = run_locust_phase_processes(args.locust_command, locust_file, plans, "measurement")
                    phase_records.append({
                        "phase": "measurement",
                        "status": "passed" if all(item.get("exitCode") == 0 for item in tenant_results) else "failed",
                        "startedAt": measurement_started,
                        "completedAt": utc_now(),
                        "tenantResultCount": len(tenant_results),
                    })

                capture_cluster_snapshot(kubeconfig, plans, "post", output_root, False)
                phase_records.append({"phase": "cluster_post_snapshot", "status": "captured", "artifact": rel_to_repo(repo_root, cluster_post_path)})

                if args.warm_up_only:
                    if any(item.get("exitCode") not in {0, None} for item in warmup_results):
                        status = "failed"
                elif any(item.get("exitCode") not in {0, None} for item in tenant_results):
                    status = "failed"
                elif any(not (item.get("measurement") or item.get("metrics") or {}).get("validTargetRequestsPresent") for item in tenant_results):
                    status = "completed_without_valid_target_requests"
    except Exception as exc:
        status = "failed"
        error = str(exc)
    finally:
        stop_port_forwards(port_forwards)

    completed_at = utc_now()

    write_tenant_benchmark_artifacts(repo_root, output_root, run_id, scenario, plans, warmup_results, tenant_results, bool(args.dry_run))
    write_phases_file(output_root, run_id, scenario_id, phase_records)
    write_metric_set_files(repo_root, output_root, run_id, scenario, scenario_id, plans, warmup_results, tenant_results, cluster_pre_path, cluster_post_path)

    summary_json_path = output_root / "multi-tenant-summary.json"
    summary_txt_path = output_root / "multi-tenant-summary.txt"
    port_forward_artifacts = [
        {
            "tenantId": item.tenant_id,
            "namespace": item.namespace,
            "serviceName": item.service_name,
            "localPort": item.local_port,
            "remotePort": item.remote_port,
            "stdout": str(item.stdout_path),
            "stderr": str(item.stderr_path),
        }
        for item in port_forwards
    ]
    payload = {
        "schemaVersion": "multi-tenant-locust-run/v1",
        "runId": run_id,
        "scenarioId": scenario_id,
        "scenarioConfigPath": str(scenario_config),
        "status": status,
        "startedAt": started_at,
        "completedAt": completed_at,
        "dryRun": bool(args.dry_run),
        "executionMode": "telemetry_priming_warm_up_only" if args.warm_up_only else "warm_up_and_measurement",
        "officialMeasurementSkipped": bool(args.warm_up_only),
        "outputRoot": str(output_root),
        "locustFile": str(locust_file),
        "phaseProfile": phase_profile,
        "tenantCount": len(plans),
        "warmUpResults": warmup_results,
        "tenantResults": [
            {
                **item,
                "measurement": item.get("metrics") or {},
                "artifacts": {
                    **(item.get("artifacts") or {}),
                    **tenant_artifacts(next(plan for plan in plans if plan.tenant_id == item.get("tenantId"))),
                },
            }
            for item in tenant_results
        ],
        "artifactSet": {
            "protocolJson": str(output_root / "protocol.json"),
            "protocolText": str(output_root / "protocol.txt"),
            "precheckJson": str(output_root / "precheck.json"),
            "precheckText": str(output_root / "precheck.txt"),
            "phasesJson": str(output_root / "phases.json"),
            "metricSetJson": str(output_root / "metric-set.json"),
            "metricSetText": str(output_root / "metric-set.txt"),
            "clusterPreManifest": str(cluster_manifest_path(output_root, "pre")),
            "clusterPreSummary": str(cluster_summary_path(output_root, "pre")),
            "clusterPreSnapshot": str(cluster_pre_path),
            "clusterPreArtifacts": [
                str(item) for item in cluster_expected_artifact_paths(output_root, "pre", [plan.namespace for plan in plans])["artifacts"]
            ],
            "clusterPostManifest": str(cluster_manifest_path(output_root, "post")),
            "clusterPostSummary": str(cluster_summary_path(output_root, "post")),
            "clusterPostSnapshot": str(cluster_post_path),
            "clusterPostArtifacts": [
                str(item) for item in cluster_expected_artifact_paths(output_root, "post", [plan.namespace for plan in plans])["artifacts"]
            ],
        },
        "portForwarding": {
            "enabled": not args.skip_port_forward,
            "reusedExistingEndpointsAllowed": bool(args.reuse_existing_port_forward),
            "remotePort": args.remote_port,
            "effectiveRemotePortsByTenant": {plan.tenant_id: plan.port_forward_remote_port for plan in plans},
            "artifacts": port_forward_artifacts,
        },
        "error": error,
    }
    write_json(summary_json_path, payload)
    write_text(summary_txt_path, summary_text(payload))
    if args.write_latest_aliases:
        copy_latest_aliases(output_root, summary_json_path, summary_txt_path)

    print(f"Multi-tenant Locust status: {status}")
    print(f"Summary JSON: {rel_to_repo(repo_root, summary_json_path)}")
    print(f"Summary text: {rel_to_repo(repo_root, summary_txt_path)}")
    if error:
        print(f"Error: {error}", file=sys.stderr)
    return 0 if status in {"passed", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
