#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_PROFILE = "config/rescheduling/profiles/RS_C8_RESOURCE_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json"
ACTIVE_PHASES = {"execute", "restart"}
SUCCESS_STATUSES = {"planned", "dry_run", "captured", "executed", "validated"}


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
    return (lambda payload, _path: payload), (lambda text, _path: text)


normalize_artifact_payload_for_output, normalize_artifact_text_for_output = _load_artifact_path_helpers()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compact_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def read_json(path: Path) -> Dict[str, Any]:
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


def repo_path(repo_root: Path, value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return repo_root / path


def rel_or_abs(path: Optional[Path], repo_root: Path) -> Optional[str]:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def load_profile(repo_root: Path, profile_config: str) -> Tuple[Path, Dict[str, Any]]:
    profile_path = repo_path(repo_root, profile_config)
    if profile_path is None or not profile_path.exists():
        raise FileNotFoundError(f"Rescheduling profile not found: {profile_config}")
    return profile_path, read_json(profile_path)


def load_scenario(repo_root: Path, scenario_config: Optional[str]) -> Tuple[Optional[Path], Dict[str, Any]]:
    if not scenario_config:
        return None, {}
    scenario_path = repo_path(repo_root, scenario_config)
    if scenario_path is None or not scenario_path.exists():
        raise FileNotFoundError(f"Scheduler-comparison scenario config not found: {scenario_config}")
    return scenario_path, read_json(scenario_path)


def scenario_namespaces(scenario: Dict[str, Any]) -> List[str]:
    values: List[Any] = []
    values.extend(scenario.get("namespaces") or [])
    values.append(scenario.get("namespace"))
    topology = scenario.get("applicationTopology") or {}
    expected = topology.get("expectedResources") or {}
    values.extend(expected.get("namespaces") or [])
    for tenant in scenario.get("tenantClusters") or []:
        if isinstance(tenant, dict):
            values.append(tenant.get("namespace"))
    for target in scenario.get("benchmarkTargets") or []:
        if isinstance(target, dict):
            values.append(target.get("namespace"))
    return ordered_unique(values)


def scenario_deployment_names(scenario: Dict[str, Any]) -> List[str]:
    topology = scenario.get("applicationTopology") or {}
    expected = topology.get("expectedResources") or {}
    names = ordered_unique(expected.get("deploymentsPerTenant") or [])
    if names:
        return names
    out: List[Any] = []
    for tenant in scenario.get("tenantClusters") or []:
        if isinstance(tenant, dict):
            out.extend(tenant.get("deploymentNames") or [])
    return ordered_unique(out)


def apply_runtime_target_overrides(profile: Dict[str, Any], scenario: Dict[str, Any]) -> Dict[str, Any]:
    resolved = json.loads(json.dumps(profile))
    if not scenario:
        return resolved
    namespaces = scenario_namespaces(scenario)
    deployment_names_from_scenario = scenario_deployment_names(scenario)
    target = resolved.setdefault("targetWorkloads", {})
    if namespaces:
        target["namespaces"] = namespaces
    if deployment_names_from_scenario:
        target["deploymentNames"] = deployment_names_from_scenario
    if namespaces and deployment_names_from_scenario:
        target["minimumSelectedDeployments"] = len(namespaces) * len(deployment_names_from_scenario)
        target["expectedSelectedDeploymentCount"] = len(namespaces) * len(deployment_names_from_scenario)
        target["requireExpectedSelectedDeploymentCount"] = True
    gate = resolved.setdefault("annotationGate", {})
    gate["requireAllSelectedDeploymentsAnnotated"] = True
    gate["requireAtLeastOneSelectedDeploymentAnnotated"] = False
    resolved["runtimeScenarioContext"] = {
        "scenarioId": scenario.get("scenarioId") or scenario.get("variantId"),
        "logicalScenarioId": scenario.get("logicalScenarioId"),
        "experimentalVariantId": scenario.get("experimentalVariantId"),
        "schedulerModeRole": scenario.get("schedulerModeRole"),
        "namespaces": namespaces,
        "deploymentNames": deployment_names_from_scenario,
        "latencyProfileId": scenario.get("latencyProfileId"),
        "latencyProfilePath": scenario.get("latencyProfilePath"),
        "latencyInjectionEnabled": bool(((scenario.get("schedulerModePolicy") or {}).get("latencyInjectionEnabled"))),
    }
    return resolved


def resolve_kubeconfig(repo_root: Path, profile: Dict[str, Any], explicit_kubeconfig: Optional[str]) -> Optional[Path]:
    value = explicit_kubeconfig or profile.get("kubeconfigPath")
    return repo_path(repo_root, value)


def nested_get(value: Any, *keys: str, default: Any = None) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _positive_int(value: Any, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _non_negative_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, parsed)


def kubectl_retry_policy(profile: Dict[str, Any]) -> Dict[str, Any]:
    policy = nested_get(profile, "redeploymentPolicy", "kubectlRetryPolicy", default=None)
    if not isinstance(policy, dict):
        policy = nested_get(profile, "kubernetes", "kubectlRetryPolicy", default={}) or {}
    enabled = bool(policy.get("enabled", False))
    max_attempts = _positive_int(policy.get("maxAttempts"), 1 if not enabled else 5) if enabled else 1
    return {
        "enabled": enabled,
        "maxAttempts": max_attempts,
        "delaySeconds": _non_negative_float(policy.get("delaySeconds"), 5.0),
        "commandTimeoutSeconds": _positive_int(policy.get("commandTimeoutSeconds"), 60),
        "retryOnJsonParseError": bool(policy.get("retryOnJsonParseError", False)),
    }


def kubectl_result_is_retryable(result: Dict[str, Any], parse_error: bool = False, retry_policy: Optional[Dict[str, Any]] = None) -> bool:
    if parse_error:
        return bool((retry_policy or {}).get("retryOnJsonParseError", False))
    message = f"{result.get('stderr') or ''}\n{result.get('stdout') or ''}".lower()
    non_retryable_fragments = (
        "notfound",
        "not found",
        "forbidden",
        "unauthorized",
        "unknown flag",
        "unknown command",
        "invalid value",
        "the server doesn't have a resource type",
    )
    if any(fragment in message for fragment in non_retryable_fragments):
        return False
    retryable_fragments = (
        "unable to connect to the server",
        "connection refused",
        "connection reset",
        "connection attempt failed",
        "i/o timeout",
        "tls handshake timeout",
        "context deadline exceeded",
        "temporarily unavailable",
        "no route to host",
        "net/http",
        "eof",
        "timed out",
        "timeout",
    )
    return any(fragment in message for fragment in retryable_fragments)


def sleep_between_attempts(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def kubectl_base(kubectl: str, kubeconfig: Optional[Path]) -> List[str]:
    command = [kubectl]
    if kubeconfig is not None:
        command.extend(["--kubeconfig", str(kubeconfig)])
    return command


def run_command(command: List[str], timeout: Optional[int] = None) -> Dict[str, Any]:
    started_at = utc_now()
    started_monotonic = time.monotonic()
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
        return {
            "command": command,
            "startedAtUtc": started_at,
            "finishedAtUtc": utc_now(),
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


def kubectl_json(
    kubectl: str,
    kubeconfig: Optional[Path],
    args: List[str],
    timeout: Optional[int] = None,
    retry_policy: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    command = kubectl_base(kubectl, kubeconfig) + args + ["-o", "json"]
    policy = retry_policy or {"enabled": False, "maxAttempts": 1, "delaySeconds": 0, "commandTimeoutSeconds": timeout or 60}
    max_attempts = _positive_int(policy.get("maxAttempts"), 1) if policy.get("enabled") else 1
    command_timeout = timeout if timeout is not None else _positive_int(policy.get("commandTimeoutSeconds"), 60)
    delay_seconds = _non_negative_float(policy.get("delaySeconds"), 0.0)
    attempts: List[Dict[str, Any]] = []
    last_result: Dict[str, Any] = {}

    for attempt_index in range(1, max_attempts + 1):
        result = run_command(command, timeout=command_timeout)
        result["attempt"] = attempt_index
        result["maxAttempts"] = max_attempts
        last_result = result
        parse_error = False

        if result.get("success"):
            try:
                payload = json.loads(result.get("stdout") or "{}")
                attempts.append(dict(result))
                result["attempts"] = attempts
                result["attemptCount"] = attempt_index
                result["succeededOnAttempt"] = attempt_index
                result["retryPolicy"] = policy
                return payload, result
            except json.JSONDecodeError as exc:
                parse_error = True
                result["success"] = False
                result["stderr"] = (result.get("stderr") or "") + f"\nUnable to parse JSON output: {exc}"

        retryable = kubectl_result_is_retryable(result, parse_error=parse_error, retry_policy=policy)
        should_retry = bool(policy.get("enabled") and retryable and attempt_index < max_attempts)
        result["retryable"] = retryable
        result["willRetry"] = should_retry
        attempts.append(result)
        if not should_retry:
            break
        sleep_between_attempts(delay_seconds)

    last_result = dict(last_result or {})
    last_result["attempts"] = attempts
    last_result["attemptCount"] = len(attempts)
    last_result["succeededOnAttempt"] = None
    last_result["retryPolicy"] = policy
    last_result["success"] = False
    return {}, last_result


def artifact_paths(repo_root: Path, profile: Dict[str, Any], output_root: Optional[str]) -> Dict[str, Path]:
    policy = profile.get("artifactPolicy") or {}
    root = repo_path(repo_root, output_root) if output_root else repo_path(repo_root, policy.get("root"))
    if root is None:
        root = repo_root / "results" / "experimental-cycles" / "C9" / "rescheduling"
    if output_root:
        paths = {
            "root": root,
            "logs": root / "logs",
            "snapshots": root / "snapshots",
            "manifests": root / "manifests",
            "summaries": root / "summaries",
            "latest_manifest": root / "latest-rescheduling-manifest.json",
            "latest_summary": root / "latest-rescheduling-summary.txt",
            "latest_pre_snapshot": root / "latest-pre-redeployment-snapshot.json",
            "latest_post_snapshot": root / "latest-post-redeployment-snapshot.json",
        }
    else:
        paths = {
            "root": root,
            "logs": repo_path(repo_root, policy.get("logsRoot")) or root / "logs",
            "snapshots": repo_path(repo_root, policy.get("snapshotsRoot")) or root / "snapshots",
            "manifests": repo_path(repo_root, policy.get("manifestsRoot")) or root / "manifests",
            "summaries": repo_path(repo_root, policy.get("summariesRoot")) or root / "summaries",
            "latest_manifest": repo_path(repo_root, policy.get("latestManifestPath")) or root / "latest-rescheduling-manifest.json",
            "latest_summary": repo_path(repo_root, policy.get("latestSummaryPath")) or root / "latest-rescheduling-summary.txt",
            "latest_pre_snapshot": repo_path(repo_root, policy.get("latestPreSnapshotPath")) or root / "latest-pre-redeployment-snapshot.json",
            "latest_post_snapshot": repo_path(repo_root, policy.get("latestPostSnapshotPath")) or root / "latest-post-redeployment-snapshot.json",
        }
    for path in paths.values():
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path.mkdir(parents=True, exist_ok=True)
    return paths


def ordered_unique(values: List[Any]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def required_annotations(profile: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    gate = profile.get("annotationGate") or {}
    return (
        [str(x) for x in gate.get("requiredNodeAnnotations") or ["cpu-usage", "memory-usage"]],
        [str(x) for x in gate.get("requiredDeploymentAnnotations") or ["cpu-usage", "memory-usage"]],
    )


def optional_annotations(profile: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    gate = profile.get("annotationGate") or {}
    return (
        [str(x) for x in gate.get("optionalNodeAnnotations") or [] if str(x).strip()],
        [str(x) for x in gate.get("optionalDeploymentAnnotations") or [] if str(x).strip()],
    )


def annotation_capture_keys(required: List[str], optional: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for key in required + optional:
        if key and key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def annotations(obj: Dict[str, Any]) -> Dict[str, Any]:
    return obj.get("metadata", {}).get("annotations") or {}


def labels(obj: Dict[str, Any]) -> Dict[str, Any]:
    return obj.get("metadata", {}).get("labels") or {}


def annotation_requirement_present(values: Dict[str, Any], requirement: str) -> bool:
    requirement = str(requirement or "").strip()
    if not requirement:
        return True
    if "<node>" in requirement:
        prefix = requirement.split("<node>", 1)[0]
        return any(str(key).startswith(prefix) and str(value).strip() for key, value in values.items())
    if "<peer-workload>" in requirement:
        prefix = requirement.split("<peer-workload>", 1)[0]
        return any(str(key).startswith(prefix) and str(value).strip() for key, value in values.items())
    return bool(str(values.get(requirement, "")).strip())


def missing_required(obj: Dict[str, Any], required: List[str]) -> List[str]:
    values = annotations(obj)
    return [key for key in required if not annotation_requirement_present(values, key)]


def missing_required_from_values(values: Dict[str, Any], required: List[str]) -> List[str]:
    return [key for key in required if not annotation_requirement_present(values, key)]


def alternative_group_satisfied(values: Dict[str, Any], group: List[Any]) -> bool:
    return all(annotation_requirement_present(values, str(item)) for item in group if str(item or "").strip())


def alternative_groups_status(values: Dict[str, Any], groups: List[List[Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for group in groups or []:
        required = [str(item) for item in group if str(item or "").strip()]
        missing = missing_required_from_values(values, required)
        out.append({"required": required, "satisfied": not missing, "missing": missing})
    return out


def any_alternative_group_satisfied(values: Dict[str, Any], groups: List[List[Any]]) -> bool:
    return any(item.get("satisfied") for item in alternative_groups_status(values, groups))


def matches_selector_labels(obj: Dict[str, Any], selector: Dict[str, Any]) -> bool:
    if not selector:
        return True
    item_labels = labels(obj)
    for key, expected in selector.items():
        if str(item_labels.get(str(key), "")) != str(expected):
            return False
    return True


def expand_node_annotation_requirements(required: List[str], node_names: List[str], current_node_name: str) -> List[str]:
    expanded: List[str] = []
    for item in required:
        text = str(item or "").strip()
        if "<node>" in text:
            for peer in node_names:
                if peer and peer != current_node_name:
                    expanded.append(text.replace("<node>", peer))
        else:
            expanded.append(text)
    return ordered_unique(expanded)


def target_namespaces(profile: Dict[str, Any]) -> List[str]:
    return ordered_unique((profile.get("targetWorkloads") or {}).get("namespaces") or [])


def deployment_names(profile: Dict[str, Any]) -> List[str]:
    return ordered_unique((profile.get("targetWorkloads") or {}).get("deploymentNames") or [])


def has_label_selector_match(obj: Dict[str, Any], selector_key: Optional[str]) -> bool:
    if not selector_key:
        return True
    item_labels = labels(obj)
    if selector_key in item_labels:
        return True
    return False


def select_deployments(profile: Dict[str, Any], deployments_by_namespace: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    target = profile.get("targetWorkloads") or {}
    allowed_names = set(deployment_names(profile))
    skip_zero = bool(target.get("skipZeroReplicaDeployments", True))
    selector_key = target.get("labelSelector")
    selected: List[Dict[str, Any]] = []
    for namespace, listing in deployments_by_namespace.items():
        for deployment in listing.get("items", []) or []:
            name = deployment.get("metadata", {}).get("name")
            replicas = int((deployment.get("spec") or {}).get("replicas") or 0)
            if allowed_names and name not in allowed_names:
                continue
            if skip_zero and replicas == 0:
                continue
            if selector_key and not has_label_selector_match(deployment, str(selector_key)):
                continue
            item = deployment.copy()
            item["_selectedNamespace"] = namespace
            selected.append(item)
    selected.sort(key=lambda item: (item.get("_selectedNamespace", ""), item.get("metadata", {}).get("name", "")))
    return selected


def pod_owner_name(pod: Dict[str, Any]) -> Optional[str]:
    for owner in pod.get("metadata", {}).get("ownerReferences") or []:
        if owner.get("kind") == "ReplicaSet":
            rs_name = str(owner.get("name") or "")
            parts = rs_name.rsplit("-", 1)
            if len(parts) == 2:
                return parts[0]
            return rs_name
    return None


def capture_snapshot(profile: Dict[str, Any], kubectl: str, kubeconfig: Optional[Path], phase: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    command_results: List[Dict[str, Any]] = []
    retry_policy = kubectl_retry_policy(profile)
    node_required, deployment_required = required_annotations(profile)
    node_optional, deployment_optional = optional_annotations(profile)
    node_capture_keys = annotation_capture_keys(node_required, node_optional)
    deployment_capture_keys = annotation_capture_keys(deployment_required, deployment_optional)

    nodes_json, nodes_cmd = kubectl_json(kubectl, kubeconfig, ["get", "nodes"], retry_policy=retry_policy)
    command_results.append(nodes_cmd)

    deployments_by_namespace: Dict[str, Dict[str, Any]] = {}
    pods_by_namespace: Dict[str, Dict[str, Any]] = {}
    events_by_namespace: Dict[str, Dict[str, Any]] = {}
    for namespace in target_namespaces(profile):
        deployments_json, deployments_cmd = kubectl_json(kubectl, kubeconfig, ["get", "deployments", "-n", namespace], retry_policy=retry_policy)
        pods_json, pods_cmd = kubectl_json(kubectl, kubeconfig, ["get", "pods", "-n", namespace], retry_policy=retry_policy)
        events_json, events_cmd = kubectl_json(kubectl, kubeconfig, ["get", "events", "-n", namespace], retry_policy=retry_policy)
        command_results.extend([deployments_cmd, pods_cmd, events_cmd])
        deployments_by_namespace[namespace] = deployments_json or {"items": []}
        pods_by_namespace[namespace] = pods_json or {"items": []}
        events_by_namespace[namespace] = events_json or {"items": []}

    selected = select_deployments(profile, deployments_by_namespace)
    selected_keys = {(d.get("_selectedNamespace"), d.get("metadata", {}).get("name")) for d in selected}

    gate = profile.get("annotationGate") or {}
    node_selector_labels = gate.get("nodeSelectorLabels") or {}
    raw_nodes = (nodes_json or {}).get("items", []) or []
    selected_nodes = [node for node in raw_nodes if matches_selector_labels(node, node_selector_labels)]
    selected_node_names = [str((node.get("metadata") or {}).get("name") or "") for node in selected_nodes]

    node_checks: List[Dict[str, Any]] = []
    for node in selected_nodes:
        node_name = str((node.get("metadata") or {}).get("name") or "")
        expanded_required = expand_node_annotation_requirements(node_required, selected_node_names, node_name)
        expanded_optional = expand_node_annotation_requirements(node_optional, selected_node_names, node_name)
        expanded_capture_keys = annotation_capture_keys(expanded_required, expanded_optional)
        node_checks.append({
            "name": node_name,
            "labels": labels(node),
            "selectedForAnnotationGate": True,
            "annotations": {key: annotations(node).get(key) for key in expanded_capture_keys},
            "missingRequiredAnnotations": missing_required(node, expanded_required),
        })

    gateway_groups = gate.get("gatewayTrafficAlternativeAnnotationGroups") or gate.get("alternativeDeploymentAnnotationGroups") or []
    deployment_checks: List[Dict[str, Any]] = []
    for deployment in selected:
        metadata = deployment.get("metadata", {})
        spec = deployment.get("spec") or {}
        template_spec = (spec.get("template") or {}).get("spec") or {}
        deployment_annotations = annotations(deployment)
        gateway_group_status = alternative_groups_status(deployment_annotations, gateway_groups)
        required_gateway_key = str(gate.get("requiredGatewayTrafficKey") or "").strip()
        require_exact_gateway_key = bool(gate.get("requireExactGatewayTrafficKey", False))
        exact_gateway_key_present = bool(required_gateway_key and str(deployment_annotations.get(required_gateway_key, "")).strip())
        missing = missing_required(deployment, deployment_required)
        gateway_required_for_deployment = gateway_traffic_required_for_deployment(profile, {
            "name": metadata.get("name"),
            "labels": labels(deployment),
        })
        if gateway_required_for_deployment and require_exact_gateway_key and required_gateway_key and not exact_gateway_key_present:
            missing.append(f"required-gateway-traffic-key:{required_gateway_key}")
        elif gateway_required_for_deployment and gate.get("requireGatewayTrafficAnnotation", False) and not any(item.get("satisfied") for item in gateway_group_status):
            missing.append("gateway-traffic-alternative-group")
        capture_keys = annotation_capture_keys(deployment_required, deployment_optional)
        if required_gateway_key:
            capture_keys = annotation_capture_keys(capture_keys, [required_gateway_key])
        for group in gateway_groups:
            capture_keys = annotation_capture_keys(capture_keys, [str(item) for item in group])
        deployment_checks.append({
            "namespace": deployment.get("_selectedNamespace") or metadata.get("namespace"),
            "name": metadata.get("name"),
            "labels": labels(deployment),
            "annotations": {key: deployment_annotations.get(key) for key in capture_keys if "<" not in key},
            "annotationKeys": sorted(str(key) for key in deployment_annotations.keys()),
            "gatewayTrafficRequiredForDeployment": gateway_required_for_deployment,
            "requiredGatewayTrafficKey": required_gateway_key or None,
            "requiredGatewayTrafficKeyPresent": exact_gateway_key_present if required_gateway_key else None,
            "requiredGatewayTrafficValue": deployment_annotations.get(required_gateway_key) if required_gateway_key else None,
            "gatewayTrafficAlternativeGroups": gateway_group_status,
            "missingRequiredAnnotations": ordered_unique(missing),
            "replicas": spec.get("replicas"),
            "readyReplicas": deployment.get("status", {}).get("readyReplicas", 0),
            "availableReplicas": deployment.get("status", {}).get("availableReplicas", 0),
            "updatedReplicas": deployment.get("status", {}).get("updatedReplicas", 0),
            "schedulerName": template_spec.get("schedulerName") or "default-scheduler",
            "selector": (spec.get("selector") or {}).get("matchLabels") or {},
        })

    pod_checks: List[Dict[str, Any]] = []
    for namespace, pods_listing in pods_by_namespace.items():
        for pod in pods_listing.get("items", []) or []:
            owner = pod_owner_name(pod)
            if selected_keys and (namespace, owner) not in selected_keys:
                continue
            pod_spec = pod.get("spec") or {}
            pod_status = pod.get("status") or {}
            pod_checks.append({
                "namespace": namespace,
                "name": pod.get("metadata", {}).get("name"),
                "deployment": owner,
                "nodeName": pod_spec.get("nodeName"),
                "phase": pod_status.get("phase"),
                "podIP": pod_status.get("podIP"),
                "startTime": pod_status.get("startTime"),
                "schedulerName": pod_spec.get("schedulerName") or "default-scheduler",
                "labels": labels(pod),
                "annotations": annotations(pod),
                "containerRestartCount": sum(int((c or {}).get("restartCount") or 0) for c in pod_status.get("containerStatuses") or []),
            })

    event_items: List[Dict[str, Any]] = []
    for namespace, events_listing in events_by_namespace.items():
        for event in events_listing.get("items", []) or []:
            involved = event.get("involvedObject") or {}
            event_items.append({
                "namespace": namespace,
                "name": event.get("metadata", {}).get("name"),
                "reason": event.get("reason"),
                "type": event.get("type"),
                "message": event.get("message"),
                "involvedObjectKind": involved.get("kind"),
                "involvedObjectName": involved.get("name"),
                "firstTimestamp": event.get("firstTimestamp"),
                "lastTimestamp": event.get("lastTimestamp"),
                "eventTime": event.get("eventTime"),
            })
    event_items.sort(key=lambda item: str(item.get("lastTimestamp") or item.get("eventTime") or item.get("firstTimestamp") or ""))

    annotated_nodes = [item for item in node_checks if not item["missingRequiredAnnotations"]]
    annotated_deployments = [item for item in deployment_checks if not item["missingRequiredAnnotations"]]
    ready_pods = [item for item in pod_checks if item.get("phase") == "Running" and item.get("nodeName")]

    node_distribution: Dict[str, int] = {}
    tenant_node_distribution: Dict[str, Dict[str, int]] = {}
    for pod in pod_checks:
        node = str(pod.get("nodeName") or "unscheduled")
        node_distribution[node] = node_distribution.get(node, 0) + 1
        tenant = str((pod.get("labels") or {}).get("group") or (pod.get("labels") or {}).get("localai.benchmark/tenant") or "unknown")
        tenant_node_distribution.setdefault(tenant, {})[node] = tenant_node_distribution.setdefault(tenant, {}).get(node, 0) + 1

    return {
        "schemaVersion": "localai-rescheduling-snapshot/v1",
        "capturedAtUtc": utc_now(),
        "phase": phase,
        "runtimeScenarioContext": profile.get("runtimeScenarioContext") or {},
        "targetNamespaces": target_namespaces(profile),
        "expectedDeploymentNames": deployment_names(profile),
        "requiredNodeAnnotations": node_required,
        "requiredDeploymentAnnotations": deployment_required,
        "optionalNodeAnnotations": node_optional,
        "optionalDeploymentAnnotations": deployment_optional,
        "nodeSelectorLabels": (profile.get("annotationGate") or {}).get("nodeSelectorLabels") or {},
        "gatewayTrafficAlternativeAnnotationGroups": (profile.get("annotationGate") or {}).get("gatewayTrafficAlternativeAnnotationGroups") or (profile.get("annotationGate") or {}).get("alternativeDeploymentAnnotationGroups") or [],
        "nodeCount": len(node_checks),
        "annotatedNodeCount": len(annotated_nodes),
        "selectedDeploymentCount": len(deployment_checks),
        "annotatedDeploymentCount": len(annotated_deployments),
        "selectedPodCount": len(pod_checks),
        "readyScheduledPodCount": len(ready_pods),
        "nodeChecks": node_checks,
        "deploymentChecks": deployment_checks,
        "podChecks": pod_checks,
        "nodeDistribution": node_distribution,
        "tenantNodeDistribution": tenant_node_distribution,
        "recentEvents": event_items[-100:],
    }, command_results


def planned_snapshot(profile: Dict[str, Any], phase: str) -> Dict[str, Any]:
    planned_deployments = []
    for namespace in target_namespaces(profile):
        for name in deployment_names(profile):
            planned_deployments.append({
                "namespace": namespace,
                "name": name,
                "labels": {},
                "annotations": {},
                "missingRequiredAnnotations": [],
                "replicas": None,
                "readyReplicas": None,
                "availableReplicas": None,
                "updatedReplicas": None,
                "schedulerName": "unknown",
                "selector": {},
                "plannedOnly": True,
            })
    return {
        "schemaVersion": "localai-rescheduling-snapshot/v1",
        "capturedAtUtc": utc_now(),
        "phase": phase,
        "dryRun": True,
        "runtimeScenarioContext": profile.get("runtimeScenarioContext") or {},
        "targetNamespaces": target_namespaces(profile),
        "expectedDeploymentNames": deployment_names(profile),
        "nodeCount": 0,
        "annotatedNodeCount": 0,
        "selectedDeploymentCount": len(planned_deployments),
        "annotatedDeploymentCount": 0,
        "selectedPodCount": 0,
        "readyScheduledPodCount": 0,
        "nodeChecks": [],
        "deploymentChecks": planned_deployments,
        "podChecks": [],
        "nodeDistribution": {},
        "tenantNodeDistribution": {},
        "recentEvents": [],
    }

def annotation_gate(profile: Dict[str, Any], snapshot: Dict[str, Any]) -> Tuple[bool, List[str]]:
    gate = profile.get("annotationGate") or {}
    if not gate.get("enabled", True):
        return True, []
    reasons: List[str] = []
    if gate.get("requireAllNodesAnnotated", True) and snapshot.get("annotatedNodeCount", 0) < snapshot.get("nodeCount", 0):
        reasons.append("not_all_nodes_have_required_annotations")
    if gate.get("requireAllSelectedDeploymentsAnnotated", False) and snapshot.get("annotatedDeploymentCount", 0) < snapshot.get("selectedDeploymentCount", 0):
        reasons.append("not_all_selected_deployments_have_required_annotations")
    if gate.get("requireAtLeastOneSelectedDeploymentAnnotated", True):
        if snapshot.get("selectedDeploymentCount", 0) <= 0:
            reasons.append("no_selected_deployments_found")
        elif snapshot.get("annotatedDeploymentCount", 0) <= 0:
            reasons.append("no_selected_deployment_has_required_annotations")
    return not reasons, reasons

def deployment_role(deployment: Dict[str, Any]) -> str:
    labels_value = deployment.get("labels") if isinstance(deployment.get("labels"), dict) else {}
    return str(labels_value.get("role") or labels_value.get("localai.benchmark/role") or "").strip().lower()


def gateway_traffic_required_for_deployment(profile: Dict[str, Any], deployment: Dict[str, Any]) -> bool:
    gate = profile.get("annotationGate") or {}
    required_role = str(gate.get("gatewayTrafficRequiredRoleLabelValue") or (profile.get("targetWorkloads") or {}).get("masterRoleLabelValue") or "master").strip().lower()
    if not required_role:
        return True
    role = deployment_role(deployment)
    name = str(deployment.get("name") or "").lower()
    return role == required_role or (not role and ("server" in name or "master" in name))


def should_reapply_annotation_controlled_latency_matrix(profile: Dict[str, Any]) -> bool:
    gate = profile.get("annotationGate") or {}
    matrix_gate = gate.get("annotationControlledLatencyMatrixGate") or {}
    if not matrix_gate.get("enabled", False) or not matrix_gate.get("reapplyBeforeRedeployment", False):
        return False
    context = profile.get("runtimeScenarioContext") or {}
    latency_profile_path = str(context.get("latencyProfilePath") or "").strip()
    latency_profile_id = str(context.get("latencyProfileId") or "").strip().upper()
    if not latency_profile_path or latency_profile_id in {"", "L0_NONE", "NONE", "NO_LATENCY"}:
        return False
    required_profiles = {str(item).strip().upper() for item in matrix_gate.get("requiredForProfiles") or [] if str(item).strip()}
    if required_profiles and latency_profile_id not in required_profiles:
        return False
    return True


def reapply_annotation_controlled_latency_matrix(
    repo_root: Path,
    profile: Dict[str, Any],
    paths: Dict[str, Path],
    kubeconfig: Optional[Path],
    run_id: str,
    dry_run: bool,
    injection_suffix: str = "pre_redeployment_reapply",
) -> List[Dict[str, Any]]:
    gate = profile.get("annotationGate") or {}
    matrix_gate = gate.get("annotationControlledLatencyMatrixGate") or {}
    if not matrix_gate.get("enabled", False) or not matrix_gate.get("reapplyBeforeRedeployment", False):
        return []
    context = profile.get("runtimeScenarioContext") or {}
    latency_profile_path = str(context.get("latencyProfilePath") or "").strip()
    latency_profile_id = str(context.get("latencyProfileId") or "").strip().upper()
    if not latency_profile_path or latency_profile_id in {"", "L0_NONE", "NONE", "NO_LATENCY"}:
        return [{
            "operation": "reapply_annotation_controlled_latency_matrix",
            "success": True,
            "skipped": True,
            "reason": "latency_profile_missing_or_noop",
            "latencyProfileId": latency_profile_id or None,
            "startedAtUtc": utc_now(),
            "finishedAtUtc": utc_now(),
        }]
    script = repo_path(repo_root, str(matrix_gate.get("reapplyScriptPath") or "scripts/latency/apply-latency-profile.py"))
    cycle_config = repo_path(repo_root, str(matrix_gate.get("cycleConfigPath") or "config/experimental-cycles/C9.json"))
    output_root = paths["root"].parent / "chaos"
    command = [
        sys.executable,
        str(script),
        "--repo-root", str(repo_root),
        "--cycle-config", str(cycle_config),
        "--profile-config", str(repo_path(repo_root, latency_profile_path)),
        "--kubeconfig", str(kubeconfig or ""),
        "--output-root", str(output_root),
        "--injection-id", f"{run_id}_{injection_suffix}",
        "--action", "apply",
        "--write-latest-aliases",
    ]
    if dry_run:
        command.append("--dry-run")
    result = run_command(command, timeout=int(matrix_gate.get("reapplyTimeoutSeconds") or 300))
    result["success"] = result.get("exitCode") in (0, None)
    result["operation"] = "reapply_annotation_controlled_latency_matrix"
    result["latencyProfileId"] = latency_profile_id
    result["latencyProfilePath"] = latency_profile_path
    result["outputRoot"] = rel_or_abs(output_root, repo_root)
    return [result]



def worker_ordinal_from_node_name(node_name: str, fallback_index: int) -> int:
    match = re.search(r"(?:worker|w)[-_]?(\d+)$", str(node_name or ""))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return fallback_index


def load_latency_profile_for_matrix_gate(repo_root: Path, profile: Dict[str, Any]) -> Tuple[Optional[Path], Dict[str, Any]]:
    context = profile.get("runtimeScenarioContext") or {}
    latency_path_value = context.get("latencyProfilePath")
    latency_id = str(context.get("latencyProfileId") or "").strip().upper()
    if not latency_path_value or latency_id in {"", "L0_NONE", "NONE", "NO_LATENCY"}:
        return None, {}
    latency_path = repo_path(repo_root, str(latency_path_value))
    if latency_path is None or not latency_path.exists():
        return latency_path, {}
    try:
        return latency_path, read_json(latency_path)
    except Exception:
        return latency_path, {}


def latency_profile_uses_annotation_matrix(latency_profile: Dict[str, Any]) -> bool:
    emulation = latency_profile.get("networkEmulation") or {}
    runtime = latency_profile.get("runtimeImplementation") or {}
    mode = str(emulation.get("mode") or "")
    tool = str(emulation.get("tool") or "")
    implementation_mode = str(runtime.get("implementationMode") or "")
    control = emulation.get("annotationControl") or {}
    return (
        mode == "inter_group_worker_latency_matrix"
        and (
            bool(control.get("enabled"))
            or "annotation" in tool
            or implementation_mode == "annotation_controlled_inter_group_latency_matrix"
        )
    )


def group_mapping_for_latency_nodes(node_names: List[str], latency_profile: Dict[str, Any]) -> Dict[str, str]:
    target = latency_profile.get("target") or {}
    worker_groups = target.get("workerGroups") or []
    ordinal_to_node = {worker_ordinal_from_node_name(node, idx + 1): node for idx, node in enumerate(node_names)}
    mapping: Dict[str, str] = {}
    for group in worker_groups:
        group_id = str(group.get("groupId") or "worker-group")
        for ordinal in group.get("workerOrdinals") or []:
            try:
                node = ordinal_to_node.get(int(ordinal))
            except (TypeError, ValueError):
                node = None
            if node:
                mapping[node] = group_id
    for idx, node in enumerate(node_names):
        mapping.setdefault(node, f"worker-group-{worker_ordinal_from_node_name(node, idx + 1)}")
    return mapping


def parse_numeric_annotation(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def latency_matrix_gate(profile: Dict[str, Any], snapshot: Dict[str, Any], repo_root: Path) -> Tuple[bool, List[str], Dict[str, Any]]:
    gate = profile.get("annotationGate") or {}
    matrix_gate = gate.get("annotationControlledLatencyMatrixGate") or {}
    if not matrix_gate.get("enabled", False):
        return True, [], {"enabled": False, "status": "skipped", "reason": "latency_matrix_gate_disabled"}

    latency_path, latency_profile = load_latency_profile_for_matrix_gate(repo_root, profile)
    report: Dict[str, Any] = {
        "enabled": True,
        "latencyProfilePath": rel_or_abs(latency_path, repo_root),
        "latencyProfileId": (latency_profile or {}).get("latencyProfileId") or (profile.get("runtimeScenarioContext") or {}).get("latencyProfileId"),
        "status": "skipped",
        "checks": [],
    }
    if not latency_profile:
        report["status"] = "skipped"
        report["reason"] = "latency_profile_missing_or_noop"
        return True, [], report
    if not latency_profile_uses_annotation_matrix(latency_profile):
        report["status"] = "skipped"
        report["reason"] = "latency_profile_not_annotation_controlled_inter_group_matrix"
        return True, [], report

    node_checks = snapshot.get("nodeChecks") or []
    node_names = [str(item.get("name") or "") for item in node_checks if str(item.get("name") or "").strip()]
    node_names = ordered_unique(node_names)
    group_for_node = group_mapping_for_latency_nodes(node_names, latency_profile)
    target = latency_profile.get("target") or {}
    emulation = latency_profile.get("networkEmulation") or {}
    control = emulation.get("annotationControl") or {}
    latency_prefix = str(control.get("latencyAnnotationPrefix") or "network-latency.")
    intra_ms = float(target.get("intraGroupDelayMs", emulation.get("intraGroupDelayMs", 0)) or 0)
    inter_ms = float(target.get("interGroupDelayMs", emulation.get("interGroupDelayMs", emulation.get("delayMs", 0))) or 0)
    tolerance = float(matrix_gate.get("latencyToleranceMs", 0.001) or 0.001)

    failed: List[Dict[str, Any]] = []
    for node_check in node_checks:
        origin = str(node_check.get("name") or "")
        values = node_check.get("annotations") or {}
        for destination in node_names:
            if not origin or not destination or destination == origin:
                continue
            same_group = group_for_node.get(origin) == group_for_node.get(destination)
            expected = intra_ms if same_group else inter_ms
            key = f"{latency_prefix}{destination}"
            actual = parse_numeric_annotation(values.get(key))
            passed = actual is not None and abs(actual - expected) <= tolerance
            record = {
                "originNode": origin,
                "destinationNode": destination,
                "originGroup": group_for_node.get(origin),
                "destinationGroup": group_for_node.get(destination),
                "sameGroup": same_group,
                "annotationKey": key,
                "expectedLatencyMs": expected,
                "actualLatencyMs": actual,
                "passed": passed,
            }
            report["checks"].append(record)
            if not passed:
                failed.append(record)

    report["nodeCount"] = len(node_names)
    report["checkedPairCount"] = len(report["checks"])
    report["failedPairCount"] = len(failed)
    report["status"] = "validated" if not failed and report["checks"] else "failed"
    if failed:
        report["failedPairs"] = failed[:25]
    elif not report["checks"]:
        report["status"] = "failed"
        report["reason"] = "no_latency_matrix_pairs_checked"
        failed.append({"reason": "no_latency_matrix_pairs_checked"})

    if report["status"] == "validated":
        return True, [], report
    reason = f"annotation_controlled_latency_matrix_mismatch:{report.get('latencyProfileId') or 'unknown'}"
    return False, [reason], report




def controlled_latency_window_policy(profile: Dict[str, Any]) -> Dict[str, Any]:
    gate = profile.get("annotationGate") or {}
    matrix_gate = gate.get("annotationControlledLatencyMatrixGate") or {}
    window = matrix_gate.get("controlledAnnotationWindow") or {}
    enabled = bool(window.get("enabled", True))
    max_attempts = _positive_int(window.get("maxAttempts"), _positive_int(matrix_gate.get("maxReapplyAttempts"), 4), minimum=1)
    return {
        "enabled": enabled,
        "maxAttempts": max_attempts,
        "delayAfterReapplySeconds": _non_negative_float(window.get("delayAfterReapplySeconds"), _non_negative_float(matrix_gate.get("delayAfterReapplySeconds"), 1.0)),
        "delayBetweenAttemptsSeconds": _non_negative_float(window.get("delayBetweenAttemptsSeconds"), _non_negative_float(matrix_gate.get("delayBetweenAttemptsSeconds"), 2.0)),
        "stabilityValidationDelaySeconds": _non_negative_float(window.get("stabilityValidationDelaySeconds"), 0.0),
        "capturePhasePrefix": str(window.get("capturePhasePrefix") or "pre_redeployment_latency_window"),
        "reason": str(window.get("reason") or "Converge annotation-controlled latency matrix immediately before pod recreation."),
    }


def wait_with_operation(seconds: float, operation: str, dry_run: bool) -> Dict[str, Any]:
    started_at = utc_now()
    if not dry_run and seconds > 0:
        time.sleep(seconds)
    return {
        "operation": operation,
        "seconds": seconds,
        "dryRun": dry_run,
        "startedAtUtc": started_at,
        "finishedAtUtc": utc_now(),
        "success": True,
    }


def establish_annotation_controlled_latency_window(
    repo_root: Path,
    profile: Dict[str, Any],
    paths: Dict[str, Path],
    kubectl: str,
    kubeconfig: Optional[Path],
    run_id: str,
    dry_run: bool,
) -> Tuple[bool, List[str], Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    policy = controlled_latency_window_policy(profile)
    attempts: List[Dict[str, Any]] = []
    command_results: List[Dict[str, Any]] = []
    failure_reasons: List[str] = []
    last_snapshot: Dict[str, Any] = {}

    if not policy.get("enabled", True):
        return True, [], last_snapshot, command_results, [{"enabled": False, "status": "skipped", "reason": "controlled_annotation_window_disabled"}]

    for attempt in range(1, int(policy.get("maxAttempts") or 1) + 1):
        attempt_record: Dict[str, Any] = {
            "attempt": attempt,
            "maxAttempts": int(policy.get("maxAttempts") or 1),
            "startedAtUtc": utc_now(),
            "status": "running",
        }
        reapply_results = reapply_annotation_controlled_latency_matrix(
            repo_root,
            profile,
            paths,
            kubeconfig,
            run_id,
            dry_run,
            injection_suffix=f"pre_redeployment_reapply_attempt{attempt}",
        )
        command_results.extend(reapply_results)
        attempt_record["reapplyResults"] = reapply_results
        reapply_failed = any(not result.get("success", False) for result in reapply_results if not result.get("skipped"))
        if reapply_failed:
            attempt_record["status"] = "failed"
            attempt_record["reason"] = "annotation_controlled_latency_matrix_reapply_failed"
            attempts.append(attempt_record)
            failure_reasons = ["annotation_controlled_latency_matrix_reapply_failed"]
        else:
            delay_after = float(policy.get("delayAfterReapplySeconds") or 0)
            if delay_after > 0:
                delay_result = wait_with_operation(delay_after, "latency_matrix_window_delay_after_reapply", dry_run)
                delay_result["attempt"] = attempt
                command_results.append(delay_result)
                attempt_record["delayAfterReapply"] = delay_result

            phase = f"{policy.get('capturePhasePrefix')}_attempt{attempt}"
            snapshot, snapshot_commands = capture_snapshot(profile, kubectl, kubeconfig, phase)
            command_results.extend(snapshot_commands)
            matrix_ok, matrix_reasons, matrix_report = latency_matrix_gate(profile, snapshot, repo_root)
            snapshot["annotationControlledLatencyMatrixValidation"] = matrix_report
            last_snapshot = snapshot
            attempt_record["validation"] = matrix_report

            stability_delay = float(policy.get("stabilityValidationDelaySeconds") or 0)
            if matrix_ok and stability_delay > 0:
                stability_wait = wait_with_operation(stability_delay, "latency_matrix_window_stability_delay", dry_run)
                stability_wait["attempt"] = attempt
                command_results.append(stability_wait)
                stable_snapshot, stable_commands = capture_snapshot(profile, kubectl, kubeconfig, f"{phase}_stable")
                command_results.extend(stable_commands)
                stable_ok, stable_reasons, stable_report = latency_matrix_gate(profile, stable_snapshot, repo_root)
                stable_snapshot["annotationControlledLatencyMatrixValidation"] = stable_report
                last_snapshot = stable_snapshot
                attempt_record["stableValidation"] = stable_report
                if not stable_ok:
                    matrix_ok = False
                    matrix_reasons = stable_reasons

            if matrix_ok:
                attempt_record["status"] = "validated"
                attempt_record["finishedAtUtc"] = utc_now()
                attempts.append(attempt_record)
                return True, [], last_snapshot, command_results, attempts

            attempt_record["status"] = "failed"
            attempt_record["failureReasons"] = matrix_reasons
            attempt_record["finishedAtUtc"] = utc_now()
            attempts.append(attempt_record)
            failure_reasons = matrix_reasons or ["annotation_controlled_latency_matrix_mismatch"]

        if attempt < int(policy.get("maxAttempts") or 1):
            delay_between = float(policy.get("delayBetweenAttemptsSeconds") or 0)
            if delay_between > 0:
                delay_result = wait_with_operation(delay_between, "latency_matrix_window_delay_between_attempts", dry_run)
                delay_result["attempt"] = attempt
                command_results.append(delay_result)

    return False, failure_reasons, last_snapshot, command_results, attempts

def deployment_selection_gate(profile: Dict[str, Any], snapshot: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    target = profile.get("targetWorkloads") or {}
    minimum = int(target.get("minimumSelectedDeployments") or 0)
    expected = int(target.get("expectedSelectedDeploymentCount") or 0)
    selected_count = int(snapshot.get("selectedDeploymentCount") or 0)
    if minimum and selected_count < minimum:
        reasons.append("selected_deployment_count_below_minimum")
    if target.get("requireExpectedSelectedDeploymentCount", False) and expected and selected_count < expected:
        reasons.append("selected_deployment_count_below_expected_scenario_count")
    return not reasons, reasons


def pods_ready_gate(profile: Dict[str, Any], snapshot: Dict[str, Any]) -> Tuple[bool, List[str]]:
    if not nested_get(profile, "decisionPolicy", "requirePostRestartReadyPods", default=True):
        return True, []
    selected_count = int(snapshot.get("selectedPodCount") or 0)
    ready_count = int(snapshot.get("readyScheduledPodCount") or 0)
    if selected_count > 0 and ready_count < selected_count:
        return False, ["not_all_selected_pods_running_and_scheduled"]
    if selected_count == 0:
        return False, ["no_selected_pods_found"]
    return True, []


def target_deployments_from_snapshot(snapshot: Dict[str, Any]) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for item in snapshot.get("deploymentChecks") or []:
        namespace = str(item.get("namespace") or "").strip()
        name = str(item.get("name") or "").strip()
        if namespace and name:
            pairs.append((namespace, name))
    pairs.sort()
    return pairs


def wait_seconds(seconds: int, dry_run: bool) -> Dict[str, Any]:
    started_at = utc_now()
    if not dry_run and seconds > 0:
        time.sleep(seconds)
    return {
        "operation": "wait",
        "seconds": seconds,
        "dryRun": dry_run,
        "startedAtUtc": started_at,
        "finishedAtUtc": utc_now(),
        "success": True,
    }


def deployment_desired_replicas(deployment: Dict[str, Any]) -> int:
    spec = deployment.get("spec") or {}
    replicas = spec.get("replicas")
    if replicas is None:
        return 1
    try:
        return max(0, int(replicas))
    except Exception:
        return 1


def selector_to_argument(match_labels: Dict[str, Any]) -> Optional[str]:
    pairs: List[str] = []
    for key in sorted(match_labels):
        value = str(match_labels.get(key) or "").strip()
        if not str(key).strip() or not value:
            return None
        pairs.append(f"{key}={value}")
    if not pairs:
        return None
    return ",".join(pairs)


def pod_uid(pod: Dict[str, Any]) -> str:
    return str((pod.get("metadata") or {}).get("uid") or "")


def pod_name(pod: Dict[str, Any]) -> str:
    return str((pod.get("metadata") or {}).get("name") or "")


def pod_deletion_timestamp(pod: Dict[str, Any]) -> str:
    return str((pod.get("metadata") or {}).get("deletionTimestamp") or "")


def pod_is_ready(pod: Dict[str, Any]) -> bool:
    metadata = pod.get("metadata") or {}
    spec = pod.get("spec") or {}
    status = pod.get("status") or {}
    if metadata.get("deletionTimestamp"):
        return False
    if status.get("phase") != "Running":
        return False
    if not spec.get("nodeName"):
        return False
    conditions = status.get("conditions") or []
    ready_condition = next((item for item in conditions if item.get("type") == "Ready"), None)
    if not ready_condition or ready_condition.get("status") != "True":
        return False
    container_statuses = status.get("containerStatuses") or []
    if container_statuses and not all(bool(item.get("ready")) for item in container_statuses):
        return False
    return True


def summarize_pods_for_wait(pods: List[Dict[str, Any]], old_uids: set[str]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for pod in pods:
        status = pod.get("status") or {}
        spec = pod.get("spec") or {}
        uid = pod_uid(pod)
        items.append({
            "name": pod_name(pod),
            "uid": uid,
            "isOldPod": uid in old_uids,
            "phase": status.get("phase"),
            "ready": pod_is_ready(pod),
            "nodeName": spec.get("nodeName"),
            "deletionTimestamp": pod_deletion_timestamp(pod) or None,
        })
    return {
        "podCount": len(items),
        "readyPodCount": len([item for item in items if item.get("ready")]),
        "oldPodCount": len([item for item in items if item.get("isOldPod")]),
        "oldNonDeletingPodCount": len([item for item in items if item.get("isOldPod") and not item.get("deletionTimestamp")]),
        "pods": items,
    }


def wait_for_recreated_pods(
    profile: Dict[str, Any],
    kubectl: str,
    kubeconfig: Optional[Path],
    namespace: str,
    deployment: str,
    selector_arg: str,
    old_uids: set[str],
    desired_replicas: int,
    timeout_seconds: int,
) -> Dict[str, Any]:
    started_at = utc_now()
    poll_seconds = int(nested_get(profile, "redeploymentPolicy", "podReadinessPollSeconds", default=5) or 5)
    poll_seconds = max(1, poll_seconds)
    retry_policy = kubectl_retry_policy(profile)
    deadline = time.time() + max(1, timeout_seconds)
    observations: List[Dict[str, Any]] = []
    last_result: Optional[Dict[str, Any]] = None
    desired_ready_count = max(1, desired_replicas)
    get_cmd = kubectl_base(kubectl, kubeconfig) + ["-n", namespace, "get", "pods", "-l", selector_arg, "-o", "json"]

    while True:
        pods_json, result = kubectl_json(kubectl, kubeconfig, ["-n", namespace, "get", "pods", "-l", selector_arg], timeout=60, retry_policy=retry_policy)
        last_result = result
        if not result.get("success"):
            return {
                "command": get_cmd,
                "operation": "wait_for_recreated_pods",
                "namespace": namespace,
                "deployment": deployment,
                "selector": selector_arg,
                "startedAtUtc": started_at,
                "finishedAtUtc": utc_now(),
                "exitCode": result.get("exitCode", 1),
                "success": False,
                "stdout": "",
                "stderr": result.get("stderr") or "Unable to list pods while waiting for recreated pods.",
                "attemptCount": result.get("attemptCount", 1),
                "succeededOnAttempt": result.get("succeededOnAttempt"),
                "retryPolicy": result.get("retryPolicy"),
                "lastKubectlResult": result,
                "observations": observations,
            }

        pods = list((pods_json or {}).get("items") or [])
        summary = summarize_pods_for_wait(pods, old_uids)
        ready_new_pods = [pod for pod in pods if pod_is_ready(pod) and pod_uid(pod) not in old_uids]
        old_non_deleting = [pod for pod in pods if pod_uid(pod) in old_uids and not pod_deletion_timestamp(pod)]
        observation = {
            "observedAtUtc": utc_now(),
            "desiredReadyPodCount": desired_ready_count,
            "readyNewPodCount": len(ready_new_pods),
            "oldNonDeletingPodCount": len(old_non_deleting),
            "summary": summary,
        }
        observations.append(observation)

        if len(ready_new_pods) >= desired_ready_count and not old_non_deleting:
            return {
                "command": get_cmd,
                "operation": "wait_for_recreated_pods",
                "namespace": namespace,
                "deployment": deployment,
                "selector": selector_arg,
                "desiredReadyPodCount": desired_ready_count,
                "readyNewPodCount": len(ready_new_pods),
                "startedAtUtc": started_at,
                "finishedAtUtc": utc_now(),
                "exitCode": 0,
                "success": True,
                "stdout": f"Recreated pods are ready for deployment/{deployment} in namespace {namespace}.",
                "stderr": "",
                "attemptCount": result.get("attemptCount", 1),
                "succeededOnAttempt": result.get("succeededOnAttempt"),
                "retryPolicy": result.get("retryPolicy"),
                "lastKubectlResult": result,
                "observations": observations[-10:],
            }

        if time.time() >= deadline:
            return {
                "command": get_cmd,
                "operation": "wait_for_recreated_pods",
                "namespace": namespace,
                "deployment": deployment,
                "selector": selector_arg,
                "desiredReadyPodCount": desired_ready_count,
                "readyNewPodCount": len(ready_new_pods),
                "startedAtUtc": started_at,
                "finishedAtUtc": utc_now(),
                "exitCode": 1,
                "success": False,
                "stdout": "",
                "stderr": f"Timed out waiting for recreated pods of deployment/{deployment} in namespace {namespace}.",
                "attemptCount": (last_result or {}).get("attemptCount", 1),
                "succeededOnAttempt": (last_result or {}).get("succeededOnAttempt"),
                "retryPolicy": (last_result or {}).get("retryPolicy"),
                "lastKubectlResult": last_result,
                "observations": observations[-20:],
            }

        time.sleep(poll_seconds)


def recreate_deployment_pods_serially(
    profile: Dict[str, Any],
    kubectl: str,
    kubeconfig: Optional[Path],
    namespace: str,
    deployment: str,
    dry_run: bool,
) -> List[Dict[str, Any]]:
    timeout_seconds = int(nested_get(profile, "redeploymentPolicy", "rolloutTimeoutSeconds", default=600) or 600)
    deletion_timeout_seconds = int(nested_get(profile, "redeploymentPolicy", "podDeletionTimeoutSeconds", default=timeout_seconds) or timeout_seconds)
    results: List[Dict[str, Any]] = []

    if dry_run:
        planned_delete_cmd = kubectl_base(kubectl, kubeconfig) + [
            "-n", namespace, "delete", "pod", "<pods-selected-by-deployment-selector>",
            "--wait=true", f"--timeout={deletion_timeout_seconds}s",
        ]
        results.append({
            "command": planned_delete_cmd,
            "operation": "delete_pods_serial_recreate",
            "namespace": namespace,
            "deployment": deployment,
            "strategy": "delete_pods_serial",
            "dryRun": True,
            "success": True,
            "exitCode": 0,
            "stdout": "dry-run: command not executed",
            "stderr": "",
            "startedAtUtc": utc_now(),
            "finishedAtUtc": utc_now(),
        })
        return results

    retry_policy = kubectl_retry_policy(profile)
    deployment_json, deployment_cmd = kubectl_json(
        kubectl,
        kubeconfig,
        ["-n", namespace, "get", f"deployment/{deployment}"],
        timeout=60,
        retry_policy=retry_policy,
    )
    deployment_cmd["operation"] = "get_deployment_for_pod_recreate"
    deployment_cmd["namespace"] = namespace
    deployment_cmd["deployment"] = deployment
    results.append(deployment_cmd)
    if not deployment_cmd.get("success"):
        return results

    match_labels = (((deployment_json.get("spec") or {}).get("selector") or {}).get("matchLabels") or {})
    selector_arg = selector_to_argument(match_labels)
    if not selector_arg:
        results.append({
            "command": [],
            "operation": "resolve_deployment_selector",
            "namespace": namespace,
            "deployment": deployment,
            "strategy": "delete_pods_serial",
            "success": False,
            "exitCode": 1,
            "stdout": "",
            "stderr": "Deployment selector.matchLabels is empty or cannot be represented as a kubectl label selector.",
            "startedAtUtc": utc_now(),
            "finishedAtUtc": utc_now(),
        })
        return results

    desired_replicas = deployment_desired_replicas(deployment_json)
    pods_json, pods_cmd = kubectl_json(
        kubectl,
        kubeconfig,
        ["-n", namespace, "get", "pods", "-l", selector_arg],
        timeout=60,
        retry_policy=retry_policy,
    )
    pods_cmd["operation"] = "list_pods_before_serial_recreate"
    pods_cmd["namespace"] = namespace
    pods_cmd["deployment"] = deployment
    pods_cmd["selector"] = selector_arg
    results.append(pods_cmd)
    if not pods_cmd.get("success"):
        return results

    pods = [pod for pod in (pods_json.get("items") or []) if not pod_deletion_timestamp(pod)]
    old_pod_names = [pod_name(pod) for pod in pods if pod_name(pod)]
    old_uids = {pod_uid(pod) for pod in pods if pod_uid(pod)}
    if desired_replicas > 0 and not old_pod_names:
        results.append({
            "command": [],
            "operation": "delete_pods_serial_recreate",
            "namespace": namespace,
            "deployment": deployment,
            "selector": selector_arg,
            "strategy": "delete_pods_serial",
            "success": False,
            "exitCode": 1,
            "stdout": "",
            "stderr": "No active pods found for the selected deployment before controlled pod recreation.",
            "startedAtUtc": utc_now(),
            "finishedAtUtc": utc_now(),
        })
        return results

    if old_pod_names:
        delete_cmd = kubectl_base(kubectl, kubeconfig) + [
            "-n", namespace, "delete", "pod", *old_pod_names, "--wait=true", f"--timeout={deletion_timeout_seconds}s",
        ]
        delete_result = run_command(delete_cmd, timeout=deletion_timeout_seconds + 30)
        delete_result["operation"] = "delete_pods_serial_recreate"
        delete_result["namespace"] = namespace
        delete_result["deployment"] = deployment
        delete_result["selector"] = selector_arg
        delete_result["strategy"] = "delete_pods_serial"
        delete_result["deletedPodNames"] = old_pod_names
        delete_result["oldPodUids"] = sorted(old_uids)
        results.append(delete_result)
        if not delete_result.get("success"):
            return results

    wait_result = wait_for_recreated_pods(
        profile,
        kubectl,
        kubeconfig,
        namespace,
        deployment,
        selector_arg,
        old_uids,
        desired_replicas,
        timeout_seconds,
    )
    wait_result["strategy"] = "delete_pods_serial"
    results.append(wait_result)
    return results


def rollout_restart_deployments(profile: Dict[str, Any], kubectl: str, kubeconfig: Optional[Path], deployments: List[Tuple[str, str]], dry_run: bool) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    timeout_seconds = int(nested_get(profile, "redeploymentPolicy", "rolloutTimeoutSeconds", default=600) or 600)
    wait_for_rollout = bool(nested_get(profile, "redeploymentPolicy", "waitForRolloutCompletion", default=True))
    for namespace, deployment in deployments:
        restart_cmd = kubectl_base(kubectl, kubeconfig) + ["-n", namespace, "rollout", "restart", f"deployment/{deployment}"]
        if dry_run:
            results.append({
                "command": restart_cmd,
                "operation": "rollout_restart",
                "namespace": namespace,
                "deployment": deployment,
                "strategy": "rollout_restart",
                "dryRun": True,
                "success": True,
                "exitCode": 0,
                "stdout": "dry-run: command not executed",
                "stderr": "",
                "startedAtUtc": utc_now(),
                "finishedAtUtc": utc_now(),
            })
        else:
            result = run_command(restart_cmd, timeout=120)
            result["operation"] = "rollout_restart"
            result["namespace"] = namespace
            result["deployment"] = deployment
            result["strategy"] = "rollout_restart"
            results.append(result)
        if wait_for_rollout:
            status_cmd = kubectl_base(kubectl, kubeconfig) + ["-n", namespace, "rollout", "status", f"deployment/{deployment}", f"--timeout={timeout_seconds}s"]
            if dry_run:
                results.append({
                    "command": status_cmd,
                    "operation": "rollout_status",
                    "namespace": namespace,
                    "deployment": deployment,
                    "strategy": "rollout_restart",
                    "dryRun": True,
                    "success": True,
                    "exitCode": 0,
                    "stdout": "dry-run: command not executed",
                    "stderr": "",
                    "startedAtUtc": utc_now(),
                    "finishedAtUtc": utc_now(),
                })
            else:
                status = run_command(status_cmd, timeout=timeout_seconds + 30)
                status["operation"] = "rollout_status"
                status["namespace"] = namespace
                status["deployment"] = deployment
                status["strategy"] = "rollout_restart"
                results.append(status)
    return results


def redeployment_strategy(profile: Dict[str, Any]) -> str:
    strategy = str(nested_get(profile, "redeploymentPolicy", "strategy", default="rollout_restart") or "rollout_restart").strip()
    return strategy or "rollout_restart"


def redeployment_failure_reason(profile: Dict[str, Any]) -> str:
    strategy = redeployment_strategy(profile)
    if strategy == "delete_pods_serial":
        return "redeployment_pod_recreation_failed"
    return "redeployment_rollout_failed"


def restart_deployments(profile: Dict[str, Any], kubectl: str, kubeconfig: Optional[Path], deployments: List[Tuple[str, str]], dry_run: bool) -> List[Dict[str, Any]]:
    strategy = redeployment_strategy(profile)
    if strategy == "delete_pods_serial":
        results: List[Dict[str, Any]] = []
        for namespace, deployment in deployments:
            results.extend(recreate_deployment_pods_serially(profile, kubectl, kubeconfig, namespace, deployment, dry_run))
            if any(not result.get("success") for result in results):
                break
        return results
    return rollout_restart_deployments(profile, kubectl, kubeconfig, deployments, dry_run)


def summarize(manifest: Dict[str, Any]) -> str:
    lines = [
        "telemetry-primed rescheduling summary",
        "======================================",
        f"Profile: {manifest.get('profileId')}",
        f"Action: {manifest.get('action')}",
        f"Status: {manifest.get('status')}",
        f"Redeployment strategy: {(manifest.get('redeploymentPolicy') or {}).get('strategy')}",
        f"Started: {manifest.get('startedAtUtc')}",
        f"Finished: {manifest.get('finishedAtUtc')}",
        "",
    ]
    if manifest.get("failureReasons"):
        lines.append("Failure reasons:")
        for reason in manifest.get("failureReasons", []):
            lines.append(f"- {reason}")
        lines.append("")
    pre = manifest.get("preRedeploymentSnapshot") or {}
    post = manifest.get("postRedeploymentSnapshot") or {}
    if pre:
        lines.extend([
            "Pre-redeployment snapshot:",
            f"- selected deployments: {pre.get('selectedDeploymentCount')}",
            f"- selected pods: {pre.get('selectedPodCount')}",
            f"- annotated nodes: {pre.get('annotatedNodeCount')}/{pre.get('nodeCount')}",
            f"- annotated deployments: {pre.get('annotatedDeploymentCount')}/{pre.get('selectedDeploymentCount')}",
            "",
        ])
        window = pre.get("annotationControlledLatencyMatrixWindow") or {}
        if window:
            lines.extend([
                "Annotation-controlled latency window:",
                f"- status: {window.get('status')}",
                f"- attempts: {window.get('attemptCount')}",
            ])
            attempts = window.get("attempts") or []
            for attempt in attempts[:10]:
                validation = attempt.get("stableValidation") or attempt.get("validation") or {}
                lines.append(
                    f"- attempt {attempt.get('attempt')}: {attempt.get('status')} "
                    f"(failedPairs={validation.get('failedPairCount')}, checkedPairs={validation.get('checkedPairCount')})"
                )
            if len(attempts) > 10:
                lines.append(f"- ... {len(attempts) - 10} additional attempts omitted from the text summary")
            lines.append("")
    if post:
        lines.extend([
            "Post-redeployment snapshot:",
            f"- selected deployments: {post.get('selectedDeploymentCount')}",
            f"- selected pods: {post.get('selectedPodCount')}",
            f"- ready scheduled pods: {post.get('readyScheduledPodCount')}/{post.get('selectedPodCount')}",
            f"- annotated nodes: {post.get('annotatedNodeCount')}/{post.get('nodeCount')}",
            f"- annotated deployments: {post.get('annotatedDeploymentCount')}/{post.get('selectedDeploymentCount')}",
            "",
        ])
    retried_commands = [
        result for result in manifest.get("commandResults") or []
        if int(result.get("attemptCount") or 1) > 1
    ]
    if retried_commands:
        lines.append("Kubectl retries:")
        for result in retried_commands[:20]:
            operation = result.get("operation") or "kubectl_json"
            namespace = result.get("namespace") or ""
            deployment = result.get("deployment") or ""
            target = "/".join([item for item in [namespace, deployment] if item])
            suffix = f" ({target})" if target else ""
            lines.append(f"- {operation}{suffix}: attempts={result.get('attemptCount')}, success={result.get('success')}")
        if len(retried_commands) > 20:
            lines.append(f"- ... {len(retried_commands) - 20} additional retried commands omitted from the text summary")
        lines.append("")

    if manifest.get("targetDeployments"):
        lines.append("Target deployments:")
        for item in manifest.get("targetDeployments") or []:
            lines.append(f"- {item.get('namespace')}/{item.get('name')}")
        lines.append("")
    if manifest.get("preRedeploymentSnapshotPath"):
        lines.append(f"Pre snapshot: {manifest.get('preRedeploymentSnapshotPath')}")
    if manifest.get("postRedeploymentSnapshotPath"):
        lines.append(f"Post snapshot: {manifest.get('postRedeploymentSnapshotPath')}")
    return "\n".join(lines) + "\n"


def write_optional_snapshot(path: Path, latest_path: Path, snapshot: Dict[str, Any], write_latest: bool) -> Optional[Path]:
    if not snapshot:
        return None
    write_json(path, snapshot)
    if write_latest:
        write_json(latest_path, snapshot)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run controlled telemetry-primed redeployment for scheduler-aware experiments.")
    parser.add_argument("--repo-root", default=str(default_repo_root()))
    parser.add_argument("--profile-config", default=DEFAULT_PROFILE)
    parser.add_argument("--scenario-config", help="Optional resource-aware-scheduler scenario config used to derive active tenant namespaces and expected LocalAI deployments.")
    parser.add_argument("--action", choices=["plan", "capture", "execute", "restart", "validate"], default="execute")
    parser.add_argument("--kubeconfig")
    parser.add_argument("--output-root")
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-telemetry-priming", action="store_true")
    parser.add_argument("--skip-annotation-gate", action="store_true")
    parser.add_argument("--skip-post-restart-stabilization", action="store_true")
    parser.add_argument("--write-latest-aliases", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    profile_path, base_profile = load_profile(repo_root, args.profile_config)
    scenario_path, scenario = load_scenario(repo_root, args.scenario_config)
    profile = apply_runtime_target_overrides(base_profile, scenario)
    paths = artifact_paths(repo_root, profile, args.output_root)
    run_id = args.run_id or f"{profile.get('reschedulingProfileId', 'rescheduling')}_{compact_now()}"
    kubectl = nested_get(profile, "kubernetes", "kubectl", default="kubectl")
    kubeconfig = resolve_kubeconfig(repo_root, profile, args.kubeconfig)
    write_latest = bool(args.write_latest_aliases or nested_get(profile, "artifactPolicy", "writeLatestAliases", default=True))

    started_at = utc_now()
    command_results: List[Dict[str, Any]] = []
    failure_reasons: List[str] = []
    pre_snapshot: Dict[str, Any] = {}
    post_snapshot: Dict[str, Any] = {}
    target_deployments: List[Tuple[str, str]] = []
    status = "dry_run" if args.dry_run else "planned"

    if args.action == "plan":
        status = "dry_run" if args.dry_run else "planned"
    elif args.dry_run:
        status = "dry_run"
        pre_snapshot = planned_snapshot(profile, "dry_run_pre_redeployment" if args.action in ACTIVE_PHASES else "dry_run_capture")
        if args.action in ACTIVE_PHASES:
            target_deployments = target_deployments_from_snapshot(pre_snapshot)
            if not args.skip_telemetry_priming and nested_get(profile, "telemetryPriming", "enabled", default=True):
                wait_result = wait_seconds(int(nested_get(profile, "telemetryPriming", "waitSeconds", default=0) or 0), True)
                wait_result["operation"] = "telemetry_priming_wait"
                command_results.append(wait_result)
            command_results.extend(reapply_annotation_controlled_latency_matrix(repo_root, profile, paths, kubeconfig, run_id, True))
            command_results.extend(restart_deployments(profile, kubectl, kubeconfig, target_deployments, True))
            if not args.skip_post_restart_stabilization:
                wait_after = wait_seconds(int(nested_get(profile, "redeploymentPolicy", "postRestartStabilizationSeconds", default=0) or 0), True)
                wait_after["operation"] = "post_restart_stabilization_wait"
                command_results.append(wait_after)
            post_snapshot = planned_snapshot(profile, "dry_run_post_redeployment")
    else:
        if args.action in {"execute", "restart"} and not args.skip_telemetry_priming and nested_get(profile, "telemetryPriming", "enabled", default=True):
            wait_result = wait_seconds(int(nested_get(profile, "telemetryPriming", "waitSeconds", default=0) or 0), args.dry_run)
            wait_result["operation"] = "telemetry_priming_wait"
            command_results.append(wait_result)

        reapply_required = args.action in ACTIVE_PHASES and should_reapply_annotation_controlled_latency_matrix(profile)
        pre_phase = "pre_redeployment_before_latency_matrix_reapply" if reapply_required else ("pre_redeployment" if args.action in ACTIVE_PHASES else "capture")
        pre_snapshot, pre_commands = capture_snapshot(profile, kubectl, kubeconfig, pre_phase)
        command_results.extend(pre_commands)
        selection_ok, selection_reasons = deployment_selection_gate(profile, pre_snapshot)
        if not selection_ok:
            failure_reasons.extend(selection_reasons)

        if args.action in {"capture", "validate"}:
            gate_ok, gate_reasons = annotation_gate(profile, pre_snapshot)
            matrix_ok, matrix_reasons, matrix_report = latency_matrix_gate(profile, pre_snapshot, repo_root)
            pre_snapshot["annotationControlledLatencyMatrixValidation"] = matrix_report
            if args.action == "validate" and not gate_ok:
                failure_reasons.extend(gate_reasons)
            if args.action == "validate" and not matrix_ok:
                failure_reasons.extend(matrix_reasons)
            status = "validated" if args.action == "validate" and not failure_reasons else "captured"
            if failure_reasons:
                status = "failed"

        elif args.action in ACTIVE_PHASES:
            reapply_attempts: List[Dict[str, Any]] = []
            if not failure_reasons and reapply_required:
                window_ok, window_reasons, window_snapshot, window_commands, reapply_attempts = establish_annotation_controlled_latency_window(
                    repo_root,
                    profile,
                    paths,
                    kubectl,
                    kubeconfig,
                    run_id,
                    args.dry_run,
                )
                command_results.extend(window_commands)
                if window_snapshot:
                    pre_snapshot = window_snapshot
                    pre_snapshot["annotationControlledLatencyMatrixWindow"] = {
                        "enabled": True,
                        "status": "validated" if window_ok else "failed",
                        "attemptCount": len(reapply_attempts),
                        "attempts": reapply_attempts,
                    }
                if not window_ok:
                    failure_reasons.extend(window_reasons or ["annotation_controlled_latency_matrix_window_failed"])

            if not failure_reasons and reapply_required:
                selection_ok, selection_reasons = deployment_selection_gate(profile, pre_snapshot)
                if not selection_ok:
                    failure_reasons.extend(selection_reasons)

            target_deployments = target_deployments_from_snapshot(pre_snapshot)
            if not args.skip_annotation_gate:
                gate_ok, gate_reasons = annotation_gate(profile, pre_snapshot)
                matrix_ok, matrix_reasons, matrix_report = latency_matrix_gate(profile, pre_snapshot, repo_root)
                pre_snapshot["annotationControlledLatencyMatrixValidation"] = matrix_report
                if not gate_ok and nested_get(profile, "annotationGate", "failBeforeRestartWhenMissing", default=True):
                    failure_reasons.extend(gate_reasons)
                if not matrix_ok and nested_get(profile, "annotationGate", "failBeforeRestartWhenMissing", default=True):
                    failure_reasons.extend(matrix_reasons)

            if not failure_reasons:
                restart_results = restart_deployments(profile, kubectl, kubeconfig, target_deployments, args.dry_run)
                command_results.extend(restart_results)
                if any(not result.get("success") for result in restart_results):
                    failure_reasons.append(redeployment_failure_reason(profile))

            if not failure_reasons and not args.skip_post_restart_stabilization:
                wait_after = wait_seconds(int(nested_get(profile, "redeploymentPolicy", "postRestartStabilizationSeconds", default=0) or 0), args.dry_run)
                wait_after["operation"] = "post_restart_stabilization_wait"
                command_results.append(wait_after)

            if not failure_reasons:
                post_snapshot, post_commands = capture_snapshot(profile, kubectl, kubeconfig, "post_redeployment")
                command_results.extend(post_commands)
                pods_ok, pod_reasons = pods_ready_gate(profile, post_snapshot)
                if not pods_ok:
                    failure_reasons.extend(pod_reasons)

            status = "executed" if not failure_reasons else "failed"

    pre_snapshot_path = write_optional_snapshot(
        paths["snapshots"] / f"{run_id}.pre-redeployment-snapshot.json",
        paths["latest_pre_snapshot"],
        pre_snapshot,
        write_latest,
    )
    post_snapshot_path = write_optional_snapshot(
        paths["snapshots"] / f"{run_id}.post-redeployment-snapshot.json",
        paths["latest_post_snapshot"],
        post_snapshot,
        write_latest,
    )
    command_results_path = paths["logs"] / f"{run_id}.rescheduling-command-results.json"
    write_json(command_results_path, command_results)

    manifest = {
        "schemaVersion": "localai-rescheduling-manifest/v1",
        "profileId": profile.get("reschedulingProfileId"),
        "profilePath": rel_or_abs(profile_path, repo_root),
        "scenarioConfigPath": rel_or_abs(scenario_path, repo_root),
        "runtimeScenarioContext": profile.get("runtimeScenarioContext") or {},
        "targetNamespaces": target_namespaces(profile),
        "expectedDeploymentNames": deployment_names(profile),
        "action": args.action,
        "status": status,
        "startedAtUtc": started_at,
        "finishedAtUtc": utc_now(),
        "dryRun": args.dry_run,
        "repoRoot": rel_or_abs(repo_root, repo_root),
        "kubeconfigPath": rel_or_abs(kubeconfig, repo_root),
        "targetDeployments": [{"namespace": ns, "name": name} for ns, name in (target_deployments or target_deployments_from_snapshot(pre_snapshot))],
        "redeploymentPolicy": profile.get("redeploymentPolicy") or {},
        "measurementBoundary": profile.get("measurementBoundary") or {},
        "failureReasons": failure_reasons,
        "commandResultsPath": rel_or_abs(command_results_path, repo_root),
        "preRedeploymentSnapshotPath": rel_or_abs(pre_snapshot_path, repo_root),
        "postRedeploymentSnapshotPath": rel_or_abs(post_snapshot_path, repo_root),
        "preRedeploymentSnapshot": pre_snapshot,
        "postRedeploymentSnapshot": post_snapshot,
        "commandResults": command_results,
    }

    manifest_path = paths["manifests"] / f"{run_id}.rescheduling-manifest.json"
    summary_path = paths["summaries"] / f"{run_id}.rescheduling-summary.txt"
    write_json(manifest_path, manifest)
    summary = summarize(manifest)
    write_text(summary_path, summary)
    if write_latest:
        write_json(paths["latest_manifest"], manifest)
        write_text(paths["latest_summary"], summary)

    print("===============================================")
    print(" telemetry-primed rescheduling")
    print("===============================================")
    print(f"Profile : {profile.get('reschedulingProfileId')}")
    print(f"Action  : {args.action}")
    print(f"Status  : {status}")
    print(f"Manifest: {manifest_path}")
    print(f"Summary : {summary_path}")
    if failure_reasons:
        print("Failure reasons:")
        for reason in failure_reasons:
            print(f"- {reason}")

    return 0 if status in SUCCESS_STATUSES else 2


if __name__ == "__main__":
    sys.exit(main())
