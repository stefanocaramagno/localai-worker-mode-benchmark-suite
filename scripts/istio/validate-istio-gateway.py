#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception as exc:
    raise SystemExit(f"PyYAML is required: {exc}")


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

    def identity_payload(payload: Any, _path: Path) -> Any:
        return payload

    def identity_text(text: str, _path: Path) -> str:
        return text

    return identity_payload, identity_text


normalize_artifact_payload_for_output, normalize_artifact_text_for_output = _load_artifact_path_helpers()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compact_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_artifact_payload_for_output(payload, path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = normalize_artifact_text_for_output(content, path)
    path.write_text(content, encoding="utf-8")


def repo_path(repo_root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def rel_or_abs(path: Path | None, repo_root: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def load_profile(repo_root: Path, profile_config: str) -> tuple[Path, dict[str, Any]]:
    profile_path = repo_path(repo_root, profile_config)
    if profile_path is None or not profile_path.exists():
        raise FileNotFoundError(f"Istio gateway profile not found: {profile_config}")
    return profile_path, read_json(profile_path)


def load_optional_json(repo_root: Path, value: str | None) -> tuple[Path | None, dict[str, Any] | None, str | None]:
    if not value:
        return None, None, None
    path = repo_path(repo_root, value)
    if path is None:
        return None, None, f"Invalid JSON path: {value}"
    if not path.exists():
        return path, None, f"JSON file not found: {value}"
    try:
        return path, read_json(path), None
    except Exception as exc:
        return path, None, f"Unable to read JSON file {value}: {exc}"


def _append_unique(values: list[str], value: Any) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text and text not in values:
        values.append(text)


def extract_active_tenant_ids(scenario_payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(scenario_payload, dict):
        return []
    tenant_ids: list[str] = []
    for value in scenario_payload.get("tenantIds") or []:
        _append_unique(tenant_ids, value)
    for cluster in scenario_payload.get("tenantClusters") or []:
        if isinstance(cluster, dict):
            _append_unique(tenant_ids, cluster.get("tenantId"))
    for profile in (scenario_payload.get("trafficProfile") or {}).get("tenantProfiles") or []:
        if isinstance(profile, dict):
            _append_unique(tenant_ids, profile.get("tenantId"))
    for target in scenario_payload.get("tenantTargets") or []:
        if isinstance(target, dict):
            _append_unique(tenant_ids, target.get("tenantId"))
    return tenant_ids


def extract_active_namespaces(scenario_payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(scenario_payload, dict):
        return []
    namespaces: list[str] = []
    for value in scenario_payload.get("namespaces") or []:
        _append_unique(namespaces, value)
    for cluster in scenario_payload.get("tenantClusters") or []:
        if isinstance(cluster, dict):
            _append_unique(namespaces, cluster.get("namespace"))
    namespace = scenario_payload.get("namespace")
    if namespace and not namespaces and int(scenario_payload.get("tenantCount") or 0) == 1:
        _append_unique(namespaces, namespace)
    return namespaces


def select_tenant_gateways(
    profile: dict[str, Any],
    scenario_payload: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tenant_gateways = [item for item in (profile.get("tenantGateways") or []) if isinstance(item, dict)]
    active_tenant_ids = extract_active_tenant_ids(scenario_payload)
    active_namespaces = extract_active_namespaces(scenario_payload)
    tenant_count = None
    if isinstance(scenario_payload, dict) and scenario_payload.get("tenantCount") is not None:
        try:
            tenant_count = int(scenario_payload.get("tenantCount"))
        except Exception:
            tenant_count = None

    selection_policy = "profile_all_tenants"
    selected: list[dict[str, Any]] = list(tenant_gateways)
    if active_tenant_ids:
        active_set = set(active_tenant_ids)
        selected = [item for item in tenant_gateways if str(item.get("tenantId") or "") in active_set]
        selection_policy = "scenario_tenant_ids"
    elif active_namespaces:
        namespace_set = set(active_namespaces)
        selected = [item for item in tenant_gateways if str(item.get("namespace") or "") in namespace_set]
        selection_policy = "scenario_namespaces"
    elif tenant_count is not None and tenant_count >= 0:
        selected = tenant_gateways[:tenant_count]
        selection_policy = "scenario_tenant_count_ordered_profile_subset"

    selected_ids = [str(item.get("tenantId") or "") for item in selected if str(item.get("tenantId") or "")]
    selected_namespaces = [str(item.get("namespace") or "") for item in selected if str(item.get("namespace") or "")]
    skipped = [item for item in tenant_gateways if str(item.get("tenantId") or "") not in set(selected_ids)]
    return selected, {
        "policy": selection_policy,
        "tenantCount": tenant_count,
        "expectedTenantIds": active_tenant_ids,
        "expectedNamespaces": active_namespaces,
        "activeTenantIds": selected_ids,
        "activeNamespaces": selected_namespaces,
        "missingTenantIdsFromProfile": [item for item in active_tenant_ids if item not in set(selected_ids)],
        "missingNamespacesFromProfile": [item for item in active_namespaces if item not in set(selected_namespaces)],
        "skippedTenantIds": [str(item.get("tenantId") or "") for item in skipped if str(item.get("tenantId") or "")],
        "skippedNamespaces": [str(item.get("namespace") or "") for item in skipped if str(item.get("namespace") or "")],
        "profileTenantIds": [str(item.get("tenantId") or "") for item in tenant_gateways if str(item.get("tenantId") or "")],
    }


def profile_with_selected_tenants(profile: dict[str, Any], selected_tenants: list[dict[str, Any]]) -> dict[str, Any]:
    filtered = dict(profile)
    filtered["tenantGateways"] = selected_tenants
    return filtered


def yaml_documents(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return [doc for doc in yaml.safe_load_all(handle) if isinstance(doc, dict)]


def find_document(docs: list[dict[str, Any]], kind: str, name: str | None = None) -> dict[str, Any] | None:
    for doc in docs:
        if doc.get("kind") != kind:
            continue
        if name is None or ((doc.get("metadata") or {}).get("name") == name):
            return doc
    return None


def kubectl_base(kubectl: str, kubeconfig: Path | None) -> list[str]:
    cmd = [kubectl]
    if kubeconfig is not None:
        cmd.extend(["--kubeconfig", str(kubeconfig)])
    return cmd


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def run_command(command: list[str], timeout: int | None = None) -> dict[str, Any]:
    started_at = utc_now()
    started_monotonic = time.monotonic()
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
        finished_at = utc_now()
        return {
            "command": command,
            "startedAtUtc": started_at,
            "finishedAtUtc": finished_at,
            "durationSeconds": round(time.monotonic() - started_monotonic, 3),
            "timeoutSeconds": timeout,
            "timedOut": False,
            "exitCode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "success": completed.returncode == 0,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "startedAtUtc": started_at,
            "finishedAtUtc": utc_now(),
            "durationSeconds": round(time.monotonic() - started_monotonic, 3),
            "timeoutSeconds": timeout,
            "timedOut": True,
            "exitCode": 124,
            "stdout": _coerce_text(exc.stdout),
            "stderr": _coerce_text(exc.stderr) or f"Command timed out after {timeout} seconds.",
            "success": False,
        }
    except Exception as exc:
        return {
            "command": command,
            "startedAtUtc": started_at,
            "finishedAtUtc": utc_now(),
            "durationSeconds": round(time.monotonic() - started_monotonic, 3),
            "timeoutSeconds": timeout,
            "timedOut": False,
            "exitCode": 1,
            "stdout": "",
            "stderr": str(exc),
            "success": False,
        }


def _positive_int(value: Any, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default
    return parsed if parsed >= minimum else default


def _positive_float(value: Any, default: float, minimum: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return parsed if parsed >= minimum else default


def kubectl_retry_policy(profile: dict[str, Any]) -> dict[str, Any]:
    validation = profile.get("validation") if isinstance(profile.get("validation"), dict) else {}
    policy = validation.get("kubectlRetryPolicy") if isinstance(validation.get("kubectlRetryPolicy"), dict) else {}
    return {
        "enabled": bool(policy.get("enabled", True)),
        "maxAttempts": _positive_int(policy.get("maxAttempts"), 5),
        "delaySeconds": _positive_float(policy.get("delaySeconds"), 5.0),
        "commandTimeoutSeconds": _positive_int(policy.get("commandTimeoutSeconds"), 45),
        "retryOnJsonParseError": bool(policy.get("retryOnJsonParseError", False)),
    }


def _command_result_with_attempts(
    command: list[str],
    attempts: list[dict[str, Any]],
    retry_policy: dict[str, Any],
) -> dict[str, Any]:
    final = dict(attempts[-1]) if attempts else {"command": command, "success": False}
    final["command"] = command
    final["attemptCount"] = len(attempts)
    final["attempts"] = attempts
    final["retryPolicy"] = {
        "enabled": retry_policy.get("enabled"),
        "maxAttempts": retry_policy.get("maxAttempts"),
        "delaySeconds": retry_policy.get("delaySeconds"),
        "commandTimeoutSeconds": retry_policy.get("commandTimeoutSeconds"),
        "retryOnJsonParseError": retry_policy.get("retryOnJsonParseError"),
    }
    if final.get("success"):
        final["succeededOnAttempt"] = len(attempts)
    return final


def kubectl_get_json(
    kubectl: str,
    kubeconfig: Path | None,
    args: list[str],
    retry_policy: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    policy = retry_policy or {
        "enabled": False,
        "maxAttempts": 1,
        "delaySeconds": 0.0,
        "commandTimeoutSeconds": None,
        "retryOnJsonParseError": False,
    }
    max_attempts = _positive_int(policy.get("maxAttempts"), 1) if policy.get("enabled", False) else 1
    delay_seconds = _positive_float(policy.get("delaySeconds"), 0.0)
    command_timeout = policy.get("commandTimeoutSeconds")
    if command_timeout is not None:
        command_timeout = _positive_int(command_timeout, 45)
    command = kubectl_base(kubectl, kubeconfig) + args + ["-o", "json"]
    attempts: list[dict[str, Any]] = []

    for attempt_number in range(1, max_attempts + 1):
        result = run_command(command, timeout=command_timeout)
        result["attempt"] = attempt_number
        result["willRetry"] = False
        if result["success"]:
            try:
                parsed = json.loads(result["stdout"])
                attempts.append(result)
                return parsed, _command_result_with_attempts(command, attempts, policy)
            except json.JSONDecodeError as exc:
                result["success"] = False
                result["jsonParseError"] = str(exc)
                result["stderr"] = (result.get("stderr") or "") + f"\nJSON parse error: {exc}"
                retryable = bool(policy.get("retryOnJsonParseError", False))
        else:
            retryable = True

        if attempt_number < max_attempts and retryable:
            result["willRetry"] = True
            result["retryDelaySeconds"] = delay_seconds
            attempts.append(result)
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            continue
        attempts.append(result)
        return None, _command_result_with_attempts(command, attempts, policy)

    return None, _command_result_with_attempts(command, attempts, policy)


def validate_component(repo_root: Path, profile: dict[str, Any], tenant: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    component_path = repo_path(repo_root, tenant.get("componentPath"))
    tenant_id = str(tenant.get("tenantId") or "")
    namespace = str(tenant.get("namespace") or "")
    gateway_name = str(tenant.get("gatewayName") or "localai-gateway")
    route_name = str(tenant.get("httpRouteName") or "localai-server-route")
    hostname = str(tenant.get("hostname") or "")
    backend_name = str(tenant.get("backendServiceName") or "localai-server")
    backend_port = int(tenant.get("backendServicePort") or 8080)
    gateway_api = profile.get("kubernetes", {}).get("gatewayApi", {})
    gateway_class_name = str(gateway_api.get("gatewayClassName") or "istio")

    def add(name: str, passed: bool, **extra: Any) -> None:
        checks.append({"tenantId": tenant_id, "check": name, "passed": passed, **extra})

    if component_path is None:
        add("component_path_declared", False)
        return checks
    add("component_path_exists", component_path.is_dir(), path=rel_or_abs(component_path, repo_root))
    if not component_path.is_dir():
        return checks

    kustomization = component_path / "kustomization.yaml"
    gateway_file = component_path / "gateway.yaml"
    route_file = component_path / "httproute.yaml"
    namespace_patch_file = component_path / "patch-namespace-istio-injection.yaml"
    for file_id, path in {
        "kustomization": kustomization,
        "gateway": gateway_file,
        "httproute": route_file,
        "namespace_patch": namespace_patch_file,
    }.items():
        add(f"{file_id}_file_exists", path.is_file(), path=rel_or_abs(path, repo_root))

    if not all(path.is_file() for path in [kustomization, gateway_file, route_file, namespace_patch_file]):
        return checks

    gateway = find_document(yaml_documents(gateway_file), "Gateway", gateway_name)
    route = find_document(yaml_documents(route_file), "HTTPRoute", route_name)
    namespace_patch = find_document(yaml_documents(namespace_patch_file), "Namespace", namespace)
    add("gateway_document_valid", gateway is not None)
    add("httproute_document_valid", route is not None)
    add("namespace_patch_document_valid", namespace_patch is not None)
    if gateway:
        spec = gateway.get("spec") or {}
        listeners = spec.get("listeners") or []
        add("gateway_class_matches", spec.get("gatewayClassName") == gateway_class_name, expected=gateway_class_name, actual=spec.get("gatewayClassName"))
        add("gateway_listener_declared", any(item.get("port") == 80 and item.get("protocol") == "HTTP" for item in listeners), listeners=listeners)
        add("gateway_hostname_matches", any(item.get("hostname") == hostname for item in listeners), expected=hostname)
    if route:
        spec = route.get("spec") or {}
        parent_refs = spec.get("parentRefs") or []
        rules = spec.get("rules") or []
        backends = []
        for rule in rules:
            backends.extend(rule.get("backendRefs") or [])
        add("route_parent_matches_gateway", any(item.get("name") == gateway_name for item in parent_refs), expected=gateway_name)
        add("route_hostname_matches", hostname in (spec.get("hostnames") or []), expected=hostname, actual=spec.get("hostnames") or [])
        add("route_backend_matches_localai_server", any(item.get("name") == backend_name and int(item.get("port") or 0) == backend_port for item in backends), expectedService=backend_name, expectedPort=backend_port)
    if namespace_patch:
        labels = (namespace_patch.get("metadata") or {}).get("labels") or {}
        expected_labels = profile.get("kubernetes", {}).get("namespaceLabels", {})
        for label_id, item in expected_labels.items():
            key = item.get("key")
            value = item.get("value")
            if item.get("required", False):
                add(f"namespace_label_{label_id}_present", labels.get(key) == value, key=key, expected=value, actual=labels.get(key))
    return checks


def runtime_checks(profile: dict[str, Any], kubeconfig: Path | None) -> list[dict[str, Any]]:
    kubectl = str(profile.get("kubernetes", {}).get("kubectl") or "kubectl")
    gateway_class_name = str(profile.get("kubernetes", {}).get("gatewayApi", {}).get("expectedGatewayClass") or "istio")
    retry_policy = kubectl_retry_policy(profile)
    checks: list[dict[str, Any]] = []

    payload, command = kubectl_get_json(kubectl, kubeconfig, ["get", "gatewayclass", gateway_class_name], retry_policy)
    checks.append({"check": "gatewayclass_available", "passed": payload is not None, "command": command})

    for tenant in profile.get("tenantGateways") or []:
        tenant_id = str(tenant.get("tenantId") or "")
        namespace = str(tenant.get("namespace") or "")
        gateway_name = str(tenant.get("gatewayName") or "localai-gateway")
        route_name = str(tenant.get("httpRouteName") or "localai-server-route")
        service_name = str(tenant.get("gatewayServiceName") or "localai-gateway-istio")
        namespace_payload: dict[str, Any] | None = None
        namespace_command: dict[str, Any] | None = None
        for resource_id, resource_args in {
            "namespace": ["get", "namespace", namespace],
            "gateway": ["get", "gateway", gateway_name, "-n", namespace],
            "httproute": ["get", "httproute", route_name, "-n", namespace],
            "gateway_service": ["get", "service", service_name, "-n", namespace],
        }.items():
            payload, command = kubectl_get_json(kubectl, kubeconfig, resource_args, retry_policy)
            if resource_id == "namespace":
                namespace_payload = payload
                namespace_command = command
            checks.append({"tenantId": tenant_id, "check": f"{resource_id}_available", "passed": payload is not None, "command": command})
        labels = (namespace_payload or {}).get("metadata", {}).get("labels") or {}
        for label_id, item in (profile.get("kubernetes", {}).get("namespaceLabels") or {}).items():
            if item.get("required", False):
                checks.append({
                    "tenantId": tenant_id,
                    "check": f"namespace_label_{label_id}_runtime",
                    "passed": labels.get(item.get("key")) == item.get("value"),
                    "key": item.get("key"),
                    "expected": item.get("value"),
                    "actual": labels.get(item.get("key")),
                    "sourceCheck": "namespace_available",
                    "sourceCommand": namespace_command,
                })
    return checks


def summary_text(payload: dict[str, Any]) -> str:
    lines = [
        "Istio gateway validation summary",
        "================================",
        f"Profile: {payload.get('profileId')}",
        f"Status: {payload.get('status')}",
        f"Dry run: {payload.get('dryRun')}",
        f"Checks passed: {payload.get('passedChecks')}/{payload.get('totalChecks')}",
        "",
    ]
    for check in payload.get("checks", []):
        tenant = f"[{check.get('tenantId')}] " if check.get("tenantId") else ""
        status = "PASS" if check.get("passed") else "FAIL"
        command = check.get("command") if isinstance(check.get("command"), dict) else None
        attempt_count = command.get("attemptCount") if command else None
        attempts_suffix = f" (attempts={attempt_count})" if isinstance(attempt_count, int) and attempt_count > 1 else ""
        lines.append(f" - {tenant}{check.get('check')}: {status}{attempts_suffix}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate LocalAI Istio Gateway API routing profile and resources.")
    parser.add_argument("--repo-root", default=str(default_repo_root()), help="Repository root directory.")
    parser.add_argument("--profile-config", default="config/istio-gateway/profiles/IG_LOCALAI_GATEWAY_ROUTED_C9.json", help="Istio gateway profile JSON path.")
    parser.add_argument("--scenario-config", default="", help="Optional scenario or runtime benchmark JSON path used to select the active tenant subset for this validation run.")
    parser.add_argument("--kubeconfig", default="", help="Optional kubeconfig path for runtime checks.")
    parser.add_argument("--output-root", default="", help="Output root override for validation artifacts.")
    parser.add_argument("--dry-run", action="store_true", help="Validate static files and write a planned manifest without runtime Kubernetes checks.")
    parser.add_argument("--skip-runtime-checks", action="store_true", help="Skip Kubernetes runtime checks even when not using dry-run.")
    parser.add_argument("--write-latest-aliases", action="store_true", help="Write latest Istio gateway validation aliases in the output directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    profile_path, profile = load_profile(repo_root, args.profile_config)
    scenario_path, scenario_payload, scenario_error = load_optional_json(repo_root, args.scenario_config)
    selected_tenants, tenant_selection = select_tenant_gateways(profile, scenario_payload)
    selected_profile = profile_with_selected_tenants(profile, selected_tenants)
    kubeconfig = repo_path(repo_root, args.kubeconfig or profile.get("kubeconfigPath"))
    dry_run = bool(args.dry_run)
    checks: list[dict[str, Any]] = []

    checks.append({"check": "profile_loaded", "passed": True, "path": rel_or_abs(profile_path, repo_root)})
    if args.scenario_config:
        checks.append({
            "check": "scenario_config_loaded",
            "passed": scenario_payload is not None and scenario_error is None,
            "path": rel_or_abs(scenario_path, repo_root),
            "error": scenario_error,
        })
    checks.append({
        "check": "active_tenant_gateway_selection_not_empty",
        "passed": bool(selected_tenants),
        "policy": tenant_selection.get("policy"),
        "activeTenantIds": tenant_selection.get("activeTenantIds"),
        "skippedTenantIds": tenant_selection.get("skippedTenantIds"),
    })
    checks.append({
        "check": "active_tenant_gateway_selection_matches_scenario",
        "passed": not tenant_selection.get("missingTenantIdsFromProfile") and not tenant_selection.get("missingNamespacesFromProfile"),
        "policy": tenant_selection.get("policy"),
        "missingTenantIdsFromProfile": tenant_selection.get("missingTenantIdsFromProfile"),
        "missingNamespacesFromProfile": tenant_selection.get("missingNamespacesFromProfile"),
    })
    for ref_key in ["infrastructureProfilePath", "monAgentProfilePath", "networkObservabilityProfilePath"]:
        path = repo_path(repo_root, profile.get(ref_key))
        checks.append({"check": f"{ref_key}_exists", "passed": bool(path and path.exists()), "path": rel_or_abs(path, repo_root)})
    for tenant in selected_tenants:
        checks.extend(validate_component(repo_root, selected_profile, tenant))

    if not dry_run and not args.skip_runtime_checks:
        if kubeconfig is None or not kubeconfig.exists():
            checks.append({"check": "kubeconfig_exists", "passed": False, "path": rel_or_abs(kubeconfig, repo_root)})
        else:
            checks.append({"check": "kubeconfig_exists", "passed": True, "path": rel_or_abs(kubeconfig, repo_root)})
            checks.extend(runtime_checks(selected_profile, kubeconfig))

    failed = [item for item in checks if not item.get("passed")]
    status = profile.get("decisionPolicy", {}).get("dryRunStatus", "dry_run") if dry_run else (profile.get("decisionPolicy", {}).get("validatedStatus", "validated") if not failed else profile.get("decisionPolicy", {}).get("failedStatus", "failed"))
    if dry_run and failed:
        status = "planned_with_static_failures"

    artifact_policy = profile.get("artifactPolicy") or {}
    output_root = repo_path(repo_root, args.output_root) if args.output_root else repo_path(repo_root, artifact_policy.get("root"))
    output_root = output_root or (repo_root / "results" / "_runtime" / "istio-gateway")
    manifest_path = output_root / f"{compact_now()}-istio-gateway-validation.json"
    summary_path = output_root / f"{compact_now()}-istio-gateway-validation.txt"
    payload = {
        "schemaVersion": "istio-gateway-validation/v1",
        "profileId": profile.get("istioGatewayProfileId"),
        "profilePath": rel_or_abs(profile_path, repo_root),
        "scenarioConfigPath": rel_or_abs(scenario_path, repo_root),
        "scenarioId": scenario_payload.get("scenarioId") if isinstance(scenario_payload, dict) else None,
        "variantId": scenario_payload.get("variantId") if isinstance(scenario_payload, dict) else None,
        "tenantSelection": tenant_selection,
        "startedAtUtc": utc_now(),
        "completedAtUtc": utc_now(),
        "dryRun": dry_run,
        "status": status,
        "totalChecks": len(checks),
        "passedChecks": len([item for item in checks if item.get("passed")]),
        "checks": checks,
        "artifactSet": {
            "manifest": rel_or_abs(manifest_path, repo_root),
            "summary": rel_or_abs(summary_path, repo_root),
        },
    }
    write_json(manifest_path, payload)
    write_text(summary_path, summary_text(payload))
    write_latest_aliases = bool(args.write_latest_aliases) or bool(artifact_policy.get("writeLatestAliases", True))
    if write_latest_aliases:
        if args.output_root:
            latest_manifest = output_root / "latest-istio-gateway-manifest.json"
            latest_summary = output_root / "latest-istio-gateway-summary.txt"
        else:
            latest_manifest = repo_path(repo_root, artifact_policy.get("latestManifestPath"))
            latest_summary = repo_path(repo_root, artifact_policy.get("latestSummaryPath"))
        if latest_manifest:
            write_json(latest_manifest, payload)
        if latest_summary:
            write_text(latest_summary, summary_text(payload))

    print(f"Istio gateway validation status: {status}")
    print(f"Manifest: {rel_or_abs(manifest_path, repo_root)}")
    print(f"Summary: {rel_or_abs(summary_path, repo_root)}")
    return 0 if status in {"validated", "dry_run"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
