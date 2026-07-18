#!/usr/bin/env python
from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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
    return Path(__file__).resolve().parents[3]


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
    path = Path(value)
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
        raise FileNotFoundError(f"mon-agent profile not found: {profile_config}")
    return profile_path, read_json(profile_path)


def load_scenario(repo_root: Path, scenario_config: Optional[str]) -> Tuple[Optional[Path], Dict[str, Any]]:
    if not scenario_config:
        return None, {}
    scenario_path = repo_path(repo_root, scenario_config)
    if scenario_path is None or not scenario_path.exists():
        raise FileNotFoundError(f"resource-aware-scheduler scenario config not found: {scenario_config}")
    return scenario_path, read_json(scenario_path)


def ordered_unique(values: List[Any]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


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
    names = []
    for tenant in scenario.get("tenantClusters") or []:
        if not isinstance(tenant, dict):
            continue
        names.extend(tenant.get("deploymentNames") or [])
    return ordered_unique(names)


def apply_runtime_target_overrides(profile: Dict[str, Any], scenario: Dict[str, Any]) -> Dict[str, Any]:
    resolved = copy.deepcopy(profile)
    if not scenario:
        return resolved
    namespaces = scenario_namespaces(scenario)
    deployment_names = scenario_deployment_names(scenario)
    if namespaces:
        resolved.setdefault("namespaceSelection", {})["applicationNamespaces"] = namespaces
    validation = resolved.setdefault("annotationValidation", {})
    if deployment_names:
        validation["deploymentNames"] = deployment_names
    if namespaces and deployment_names:
        validation["expectedSelectedDeploymentCount"] = len(namespaces) * len(deployment_names)
        validation["requireExpectedSelectedDeploymentCount"] = True
    validation["requireAllSelectedDeploymentsAnnotated"] = True
    validation["requireAtLeastOneAnnotatedDeployment"] = False
    resolved["runtimeScenarioContext"] = {
        "scenarioId": scenario.get("scenarioId") or scenario.get("variantId"),
        "logicalScenarioId": scenario.get("logicalScenarioId"),
        "experimentalVariantId": scenario.get("experimentalVariantId"),
        "schedulerModeRole": scenario.get("schedulerModeRole"),
        "namespaces": namespaces,
        "deploymentNames": deployment_names,
        "latencyProfileId": scenario.get("latencyProfileId"),
        "latencyInjectionEnabled": bool(((scenario.get("schedulerModePolicy") or {}).get("latencyInjectionEnabled"))),
    }
    return resolved


def resolve_kubeconfig(repo_root: Path, profile: Dict[str, Any], explicit_kubeconfig: Optional[str]) -> Optional[Path]:
    value = explicit_kubeconfig or profile.get("kubeconfigPath")
    return repo_path(repo_root, value)


def kubectl_base(kubectl: str, kubeconfig: Optional[Path]) -> List[str]:
    cmd = [kubectl]
    if kubeconfig is not None:
        cmd.extend(["--kubeconfig", str(kubeconfig)])
    return cmd


def run_command(command: List[str], timeout: Optional[int] = None, stdin: Optional[str] = None) -> Dict[str, Any]:
    started_at = utc_now()
    try:
        completed = subprocess.run(
            command,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return {
            "command": command,
            "startedAtUtc": started_at,
            "finishedAtUtc": utc_now(),
            "exitCode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "success": completed.returncode == 0,
        }
    except Exception as exc:
        return {
            "command": command,
            "startedAtUtc": started_at,
            "finishedAtUtc": utc_now(),
            "exitCode": 1,
            "stdout": "",
            "stderr": str(exc),
            "success": False,
        }


def get_nested(value: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def metadata(name: str, namespace: Optional[str] = None, labels: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"name": name}
    if namespace:
        out["namespace"] = namespace
    if labels:
        out["labels"] = labels
    return out


def mon_agent_labels(version: str = "v0.0.6") -> Dict[str, str]:
    return {
        "app": "mon-agent",
        "app.kubernetes.io/name": "mon-agent",
        "app.kubernetes.io/component": "metrics-annotation-agent",
        "app.kubernetes.io/version": version or "v0.0.6",
    }


def mon_agent_security_context(deployment_cfg: Dict[str, Any]) -> Dict[str, Any]:
    security_context = copy.deepcopy(deployment_cfg.get("securityContext") or {})
    if not security_context:
        security_context = {
            "allowPrivilegeEscalation": False,
            "runAsNonRoot": True,
            "runAsUser": 65532,
            "runAsGroup": 65532,
            "capabilities": {"drop": ["ALL"]},
        }
    else:
        security_context.setdefault("allowPrivilegeEscalation", False)
        security_context.setdefault("runAsNonRoot", True)
        security_context.setdefault("runAsUser", 65532)
        security_context.setdefault("runAsGroup", 65532)
        capabilities = security_context.setdefault("capabilities", {})
        if isinstance(capabilities, dict):
            capabilities.setdefault("drop", ["ALL"])
    return security_context


def render_objects(profile: Dict[str, Any]) -> Dict[str, Any]:
    k8s = profile.get("kubernetes") or {}
    deployment_cfg = profile.get("monAgentDeployment") or {}
    namespace_selection = profile.get("namespaceSelection") or {}
    prometheus = profile.get("prometheus") or {}

    namespace = k8s.get("namespace", "observability")
    service_account = k8s.get("serviceAccountName", "mon-agent")
    deployment_name = k8s.get("deploymentName", "mon-agent")
    labels = mon_agent_labels(str(deployment_cfg.get("version") or "v0.0.6"))

    objects: List[Dict[str, Any]] = []
    if k8s.get("createNamespace", True):
        objects.append({
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": metadata(namespace, labels={
                "app.kubernetes.io/name": namespace,
                "app.kubernetes.io/component": "monitoring",
            }),
        })

    objects.extend([
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": metadata(service_account, namespace, labels),
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRole",
            "metadata": metadata("mon-agent", labels=labels),
            "rules": [
                {"apiGroups": [""], "resources": ["namespaces", "nodes"], "verbs": ["get", "list", "watch"]},
                {"apiGroups": [""], "resources": ["nodes"], "verbs": ["patch"]},
                {"apiGroups": ["apps"], "resources": ["deployments"], "verbs": ["get", "list", "watch", "patch"]},
            ],
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRoleBinding",
            "metadata": metadata("mon-agent", labels=labels),
            "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "mon-agent"},
            "subjects": [{"kind": "ServiceAccount", "name": service_account, "namespace": namespace}],
        },
    ])

    pod_spec: Dict[str, Any] = {
        "serviceAccountName": service_account,
        "containers": [
            {
                "name": "mon-agent",
                "image": deployment_cfg.get("image", "ghcr.io/unict-cclab/mon-agent:v0.0.6"),
                "imagePullPolicy": deployment_cfg.get("imagePullPolicy", "IfNotPresent"),
                "env": [
                    {"name": "PROMETHEUS_URL", "value": prometheus.get("url", "http://prometheus-stack-kube-prom-prometheus.observability:9090")},
                    {"name": "SCRAPE_PERIOD_SECONDS", "value": str(deployment_cfg.get("scrapePeriodSeconds", 30))},
                    {"name": "PROMQL_RANGE", "value": str(deployment_cfg.get("promqlRange", "5m"))},
                    {"name": "NAMESPACE_LABEL_SELECTOR", "value": namespace_selection.get("selector", "mon-agent/enabled=true")},
                ],
                "securityContext": mon_agent_security_context(deployment_cfg),
            }
        ],
    }
    resources = deployment_cfg.get("resources")
    if resources:
        pod_spec["containers"][0]["resources"] = resources

    affinity_cfg = deployment_cfg.get("preferredNodeAffinity") or {}
    if affinity_cfg:
        pod_spec["affinity"] = {
            "nodeAffinity": {
                "preferredDuringSchedulingIgnoredDuringExecution": [
                    {
                        "weight": int(affinity_cfg.get("weight", 100)),
                        "preference": {
                            "matchExpressions": [
                                {
                                    "key": affinity_cfg.get("key", "nodepool"),
                                    "operator": affinity_cfg.get("operator", "In"),
                                    "values": affinity_cfg.get("values", ["management"]),
                                }
                            ]
                        },
                    }
                ]
            }
        }
    tolerations = deployment_cfg.get("tolerations")
    if tolerations:
        pod_spec["tolerations"] = tolerations

    objects.append({
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": metadata(deployment_name, namespace, labels),
        "spec": {
            "replicas": int(deployment_cfg.get("replicas", 1)),
            "selector": {"matchLabels": {"app": "mon-agent"}},
            "template": {
                "metadata": {"labels": labels},
                "spec": pod_spec,
            },
        },
    })

    return {"apiVersion": "v1", "kind": "List", "items": objects}


def artifact_paths(repo_root: Path, profile: Dict[str, Any], output_root: Optional[str]) -> Dict[str, Path]:
    policy = profile.get("artifactPolicy") or {}
    root = repo_path(repo_root, output_root) if output_root else repo_path(repo_root, policy.get("root"))
    if root is None:
        root = repo_root / "results" / "mon-agent"
    if output_root:
        paths = {
            "root": root,
            "logs": root / "logs",
            "snapshots": root / "snapshots",
            "manifests": root / "manifests",
            "summaries": root / "summaries",
            "rendered": root / "rendered",
            "latest_manifest": root / "latest-mon-agent-manifest.json",
            "latest_summary": root / "latest-mon-agent-summary.txt",
            "latest_snapshot": root / "latest-mon-agent-validation-snapshot.json",
        }
    else:
        paths = {
            "root": root,
            "logs": repo_path(repo_root, policy.get("logsRoot")) or root / "logs",
            "snapshots": repo_path(repo_root, policy.get("snapshotsRoot")) or root / "snapshots",
            "manifests": repo_path(repo_root, policy.get("manifestsRoot")) or root / "manifests",
            "summaries": repo_path(repo_root, policy.get("summariesRoot")) or root / "summaries",
            "rendered": repo_path(repo_root, policy.get("renderedManifestsRoot")) or root / "rendered",
            "latest_manifest": repo_path(repo_root, policy.get("latestManifestPath")) or root / "latest-mon-agent-manifest.json",
            "latest_summary": repo_path(repo_root, policy.get("latestSummaryPath")) or root / "latest-mon-agent-summary.txt",
            "latest_snapshot": repo_path(repo_root, policy.get("latestValidationSnapshotPath")) or root / "latest-mon-agent-validation-snapshot.json",
        }
    for path in paths.values():
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path.mkdir(parents=True, exist_ok=True)
    return paths


def write_rendered_manifest(paths: Dict[str, Path], run_id: str, rendered: Dict[str, Any], repo_root: Path) -> Path:
    rendered_path = paths["rendered"] / f"{run_id}.mon-agent-rendered-manifest.json"
    write_json(rendered_path, rendered)
    latest_rendered = paths["rendered"] / "latest-mon-agent-rendered-manifest.json"
    write_json(latest_rendered, rendered)
    return rendered_path


def kubectl_get_json(kubectl: str, kubeconfig: Optional[Path], args: List[str]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    command = kubectl_base(kubectl, kubeconfig) + args + ["-o", "json"]
    result = run_command(command)
    if result["success"]:
        try:
            return json.loads(result["stdout"]), result
        except json.JSONDecodeError as exc:
            result["success"] = False
            result["stderr"] = (result.get("stderr") or "") + f"\nJSON parse error: {exc}"
    return None, result


def label_application_namespaces(profile: Dict[str, Any], kubectl: str, kubeconfig: Optional[Path]) -> List[Dict[str, Any]]:
    selection = profile.get("namespaceSelection") or {}
    if not selection.get("labelNamespacesOnApply", True):
        return []
    label_key = selection.get("labelKey", "mon-agent/enabled")
    label_value = selection.get("labelValue", "true")
    ignore_missing = bool(selection.get("ignoreMissingApplicationNamespaces", False))
    commands: List[Dict[str, Any]] = []
    for namespace in ordered_unique(selection.get("applicationNamespaces") or []):
        if not namespace:
            continue
        get_command = kubectl_base(kubectl, kubeconfig) + ["get", "namespace", namespace]
        get_result = run_command(get_command)
        get_result["operation"] = "check_application_namespace"
        get_result["namespace"] = namespace
        commands.append(get_result)
        if not get_result.get("success"):
            if ignore_missing:
                get_result["skippedNamespaceLabeling"] = True
                continue
            missing_result = dict(get_result)
            missing_result["operation"] = "label_application_namespace"
            missing_result["success"] = False
            missing_result["exitCode"] = get_result.get("exitCode", 1)
            missing_result["stderr"] = (get_result.get("stderr") or "") + "\nApplication namespace is required by the active scenario and cannot be labeled because it was not found."
            commands.append(missing_result)
            continue
        command = kubectl_base(kubectl, kubeconfig) + ["label", "namespace", namespace, f"{label_key}={label_value}", "--overwrite"]
        label_result = run_command(command)
        label_result["operation"] = "label_application_namespace"
        label_result["namespace"] = namespace
        commands.append(label_result)
    return commands


def wait_for_deployment(profile: Dict[str, Any], kubectl: str, kubeconfig: Optional[Path]) -> Dict[str, Any]:
    k8s = profile.get("kubernetes") or {}
    namespace = k8s.get("namespace", "observability")
    name = k8s.get("deploymentName", "mon-agent")
    command = kubectl_base(kubectl, kubeconfig) + ["-n", namespace, "rollout", "status", f"deployment/{name}", "--timeout=180s"]
    return run_command(command, timeout=210)


def prometheus_service_check(profile: Dict[str, Any], kubectl: str, kubeconfig: Optional[Path]) -> Dict[str, Any]:
    prometheus = profile.get("prometheus") or {}
    namespace = prometheus.get("namespace", "observability")
    service_name = prometheus.get("serviceName", "prometheus-stack-kube-prom-prometheus")
    command = kubectl_base(kubectl, kubeconfig) + ["-n", namespace, "get", "svc", service_name, "-o", "json"]
    result = run_command(command)
    result["serviceNamespace"] = namespace
    result["serviceName"] = service_name
    return result


def list_to_name_map(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {item.get("metadata", {}).get("name", ""): item for item in items}


def selected_deployments(profile: Dict[str, Any], deployments_by_namespace: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    validation = profile.get("annotationValidation") or {}
    skip_zero = validation.get("skipDeploymentsWithZeroReplicas", True)
    allowed_names = set(ordered_unique(validation.get("deploymentNames") or []))
    label_selector_key = validation.get("labelSelectorKey", "localai.benchmark/component")
    require_group_app = bool(validation.get("requireGroupAndAppLabels", True))
    required_label_keys = ordered_unique(validation.get("requiredDeploymentLabels") or [])
    if require_group_app:
        required_label_keys = ordered_unique(required_label_keys + ["group", "app"])
    selected: List[Dict[str, Any]] = []
    for namespace, listing in deployments_by_namespace.items():
        for deployment in listing.get("items", []) or []:
            metadata = deployment.get("metadata", {}) or {}
            name = str(metadata.get("name") or "")
            spec = deployment.get("spec") or {}
            replicas = int(spec.get("replicas") or 0)
            item_labels = metadata.get("labels") or {}
            if allowed_names and name not in allowed_names:
                continue
            if skip_zero and replicas == 0:
                continue
            if any(not str(item_labels.get(label_key, "")).strip() for label_key in required_label_keys):
                continue
            if label_selector_key and label_selector_key not in item_labels:
                continue
            item = copy.deepcopy(deployment)
            item["_validationNamespace"] = namespace
            selected.append(item)
    selected.sort(key=lambda item: (item.get("_validationNamespace", ""), item.get("metadata", {}).get("name", "")))
    return selected


def annotations_for(obj: Dict[str, Any]) -> Dict[str, str]:
    return obj.get("metadata", {}).get("annotations") or {}


def labels_for(obj: Dict[str, Any]) -> Dict[str, str]:
    return obj.get("metadata", {}).get("labels") or {}


def matches_selector_labels(obj: Dict[str, Any], selector: Dict[str, Any]) -> bool:
    if not selector:
        return True
    item_labels = labels_for(obj)
    for key, expected in selector.items():
        if str(item_labels.get(str(key), "")) != str(expected):
            return False
    return True


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


def missing_annotations(obj: Dict[str, Any], required: List[str]) -> List[str]:
    annotations = annotations_for(obj)
    return [key for key in required if not annotation_requirement_present(annotations, key)]


def missing_annotations_from_values(values: Dict[str, Any], required: List[str]) -> List[str]:
    return [key for key in required if not annotation_requirement_present(values, key)]


def optional_annotations(validation: Dict[str, Any], key: str) -> List[str]:
    return [str(item) for item in validation.get(key) or [] if str(item).strip()]


def annotation_prefixes(validation: Dict[str, Any], key: str) -> List[str]:
    return [str(item) for item in validation.get(key) or [] if str(item).strip()]


def annotations_matching_prefixes(obj: Dict[str, Any], prefixes: List[str]) -> Dict[str, str]:
    annotations = annotations_for(obj)
    if not prefixes:
        return {}
    return {key: value for key, value in annotations.items() if any(str(key).startswith(prefix) for prefix in prefixes)}


def missing_annotation_prefixes(obj: Dict[str, Any], prefixes: List[str]) -> List[str]:
    annotations = annotations_for(obj)
    missing: List[str] = []
    for prefix in prefixes:
        if not any(str(key).startswith(prefix) and str(value).strip() for key, value in annotations.items()):
            missing.append(prefix + "*")
    return missing


def alternative_group_status(values: Dict[str, Any], group: List[Any]) -> Dict[str, Any]:
    required = [str(item) for item in group if str(item or "").strip()]
    missing = missing_annotations_from_values(values, required)
    return {"required": required, "satisfied": not missing, "missing": missing}


def alternative_groups_status(values: Dict[str, Any], groups: List[List[Any]]) -> List[Dict[str, Any]]:
    return [alternative_group_status(values, group) for group in groups or []]


def deployment_role(deployment: Dict[str, Any]) -> str:
    role = labels_for(deployment).get("role") or labels_for(deployment).get("localai.benchmark/role") or ""
    return str(role).strip().lower()


def gateway_traffic_required_for_deployment(profile: Dict[str, Any], deployment: Dict[str, Any]) -> bool:
    validation = profile.get("annotationValidation") or {}
    if not validation.get("gatewayTrafficRequiredOnlyForMasterRole", False):
        return bool(validation.get("requireGatewayTrafficAnnotation", False) or validation.get("requireExactGatewayTrafficKey", False))
    required_role = str(validation.get("gatewayTrafficRequiredRoleLabelValue") or "master").strip().lower()
    role = deployment_role(deployment)
    name = str((deployment.get("metadata") or {}).get("name") or "").strip().lower()
    return role == required_role or (not role and ("server" in name or "master" in name))


def annotation_capture_keys(required: List[str], optional: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for key in required + optional:
        if key and key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def capture_snapshot(profile: Dict[str, Any], kubectl: str, kubeconfig: Optional[Path]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    commands: List[Dict[str, Any]] = []
    nodes_json, nodes_cmd = kubectl_get_json(kubectl, kubeconfig, ["get", "nodes"])
    commands.append(nodes_cmd)

    deployments_by_namespace: Dict[str, Dict[str, Any]] = {}
    for namespace in (profile.get("namespaceSelection") or {}).get("applicationNamespaces") or []:
        listing, command = kubectl_get_json(kubectl, kubeconfig, ["get", "deployments", "-n", namespace])
        commands.append(command)
        deployments_by_namespace[namespace] = listing or {"items": []}

    k8s = profile.get("kubernetes") or {}
    mon_ns = k8s.get("namespace", "observability")
    mon_name = k8s.get("deploymentName", "mon-agent")
    mon_pods_json, mon_pods_cmd = kubectl_get_json(kubectl, kubeconfig, ["get", "pods", "-n", mon_ns, "-l", "app=mon-agent"])
    commands.append(mon_pods_cmd)

    logs_command = kubectl_base(kubectl, kubeconfig) + ["-n", mon_ns, "logs", f"deployment/{mon_name}", "--tail=200"]
    logs_result = run_command(logs_command)
    commands.append(logs_result)

    validation = profile.get("annotationValidation") or {}
    required_node = validation.get("requiredNodeAnnotations") or ["cpu-usage", "memory-usage"]
    required_deployment = validation.get("requiredDeploymentAnnotations") or ["cpu-usage", "memory-usage"]
    optional_node = optional_annotations(validation, "optionalNodeAnnotations")
    optional_deployment = optional_annotations(validation, "optionalDeploymentAnnotations")
    required_node_prefixes = annotation_prefixes(validation, "requiredNodeAnnotationPrefixes")
    required_deployment_prefixes = annotation_prefixes(validation, "requiredDeploymentAnnotationPrefixes")
    optional_node_prefixes = annotation_prefixes(validation, "optionalNodeAnnotationPrefixes")
    optional_deployment_prefixes = annotation_prefixes(validation, "optionalDeploymentAnnotationPrefixes")
    node_capture_keys = annotation_capture_keys(required_node, optional_node)
    deployment_capture_keys = annotation_capture_keys(required_deployment, optional_deployment)
    node_capture_prefixes = ordered_unique(required_node_prefixes + optional_node_prefixes)
    deployment_capture_prefixes = ordered_unique(required_deployment_prefixes + optional_deployment_prefixes)

    raw_node_items = (nodes_json or {}).get("items", [])
    node_selector_labels = validation.get("nodeSelectorLabels") or {}
    node_items = [node for node in raw_node_items if matches_selector_labels(node, node_selector_labels)]
    deployment_items = selected_deployments(profile, deployments_by_namespace)

    node_checks = []
    for node in node_items:
        captured_annotations = {key: annotations_for(node).get(key) for key in node_capture_keys}
        captured_annotations.update(annotations_matching_prefixes(node, node_capture_prefixes))
        node_checks.append({
            "name": node.get("metadata", {}).get("name"),
            "labels": labels_for(node),
            "selectedForAnnotationGate": True,
            "annotations": captured_annotations,
            "missingRequiredAnnotations": missing_annotations(node, required_node) + missing_annotation_prefixes(node, required_node_prefixes),
        })

    gateway_groups = validation.get("gatewayTrafficAlternativeAnnotationGroups") or validation.get("alternativeDeploymentAnnotationGroups") or []
    required_gateway_key = str(validation.get("requiredGatewayTrafficKey") or "").strip()
    require_exact_gateway_key = bool(validation.get("requireExactGatewayTrafficKey", False))
    require_gateway_traffic = bool(validation.get("requireGatewayTrafficAnnotation", False))

    deployment_checks = []
    for dep in deployment_items:
        metadata = dep.get("metadata", {})
        dep_annotations = annotations_for(dep)
        captured_annotations = {key: dep_annotations.get(key) for key in deployment_capture_keys}
        captured_annotations.update(annotations_matching_prefixes(dep, deployment_capture_prefixes))
        if required_gateway_key:
            captured_annotations[required_gateway_key] = dep_annotations.get(required_gateway_key)
        for group in gateway_groups:
            for item in group:
                text = str(item or "").strip()
                if text and "<" not in text:
                    captured_annotations[text] = dep_annotations.get(text)
        gateway_group_status = alternative_groups_status(dep_annotations, gateway_groups)
        exact_gateway_key_present = bool(required_gateway_key and str(dep_annotations.get(required_gateway_key, "")).strip())
        gateway_required = gateway_traffic_required_for_deployment(profile, dep)
        missing = missing_annotations(dep, required_deployment) + missing_annotation_prefixes(dep, required_deployment_prefixes)
        if gateway_required and require_exact_gateway_key and required_gateway_key and not exact_gateway_key_present:
            missing.append(f"required-gateway-traffic-key:{required_gateway_key}")
        elif gateway_required and require_gateway_traffic and gateway_groups and not any(item.get("satisfied") for item in gateway_group_status):
            missing.append("gateway-traffic-alternative-group")
        deployment_checks.append({
            "namespace": metadata.get("namespace") or dep.get("_validationNamespace"),
            "name": metadata.get("name"),
            "labels": metadata.get("labels") or {},
            "replicas": (dep.get("spec") or {}).get("replicas"),
            "annotations": captured_annotations,
            "annotationKeys": sorted(str(key) for key in dep_annotations.keys()),
            "gatewayTrafficRequiredForDeployment": gateway_required,
            "requiredGatewayTrafficKey": required_gateway_key or None,
            "requiredGatewayTrafficKeyPresent": exact_gateway_key_present if required_gateway_key else None,
            "requiredGatewayTrafficValue": dep_annotations.get(required_gateway_key) if required_gateway_key else None,
            "gatewayTrafficAlternativeGroups": gateway_group_status,
            "missingRequiredAnnotations": ordered_unique(missing),
        })

    annotated_nodes = [item for item in node_checks if not item["missingRequiredAnnotations"]]
    annotated_deployments = [item for item in deployment_checks if not item["missingRequiredAnnotations"]]

    snapshot = {
        "capturedAtUtc": utc_now(),
        "profileId": profile.get("monAgentProfileId"),
        "nodeCount": len(node_checks),
        "selectedDeploymentCount": len(deployment_checks),
        "annotatedNodeCount": len(annotated_nodes),
        "annotatedDeploymentCount": len(annotated_deployments),
        "runtimeScenarioContext": profile.get("runtimeScenarioContext") or {},
        "targetNamespaces": (profile.get("namespaceSelection") or {}).get("applicationNamespaces") or [],
        "expectedDeploymentNames": (profile.get("annotationValidation") or {}).get("deploymentNames") or [],
        "clusterNodeCount": len(raw_node_items),
        "nodeSelectorLabels": node_selector_labels,
        "gatewayTrafficAlternativeAnnotationGroups": gateway_groups,
        "requiredGatewayTrafficKey": required_gateway_key or None,
        "requireExactGatewayTrafficKey": require_exact_gateway_key,
        "requiredNodeAnnotations": required_node,
        "requiredNodeAnnotationPrefixes": required_node_prefixes,
        "requiredDeploymentAnnotations": required_deployment,
        "requiredDeploymentAnnotationPrefixes": required_deployment_prefixes,
        "optionalNodeAnnotations": optional_node,
        "optionalNodeAnnotationPrefixes": optional_node_prefixes,
        "optionalDeploymentAnnotations": optional_deployment,
        "optionalDeploymentAnnotationPrefixes": optional_deployment_prefixes,
        "nodes": node_checks,
        "deployments": deployment_checks,
        "monAgentPods": mon_pods_json or {},
        "monAgentLogsTail": logs_result.get("stdout", ""),
    }
    return snapshot, commands


def validation_passed(profile: Dict[str, Any], snapshot: Dict[str, Any]) -> Tuple[bool, List[str]]:
    validation = profile.get("annotationValidation") or {}
    reasons: List[str] = []
    node_count = int(snapshot.get("nodeCount", 0) or 0)
    selected_count = int(snapshot.get("selectedDeploymentCount", 0) or 0)
    annotated_deployment_count = int(snapshot.get("annotatedDeploymentCount", 0) or 0)
    expected_selected = int(validation.get("expectedSelectedDeploymentCount") or 0)
    if node_count <= 0:
        reasons.append("no_nodes_found")
    if node_count > 0 and snapshot.get("annotatedNodeCount", 0) < node_count:
        reasons.append("not_all_nodes_have_required_annotations")
    if validation.get("requireExpectedSelectedDeploymentCount", False) and expected_selected > 0 and selected_count < expected_selected:
        reasons.append("selected_deployment_count_below_expected_scenario_count")
    if validation.get("requireSelectedDeployments", True) and selected_count <= 0:
        reasons.append("no_selected_deployments_found")
    if validation.get("requireAllSelectedDeploymentsAnnotated", False):
        if selected_count > 0 and annotated_deployment_count < selected_count:
            reasons.append("not_all_selected_deployments_have_required_annotations")
    elif validation.get("requireAtLeastOneAnnotatedDeployment", True):
        if selected_count <= 0:
            reasons.append("no_selected_deployments_found")
        elif annotated_deployment_count <= 0:
            reasons.append("no_selected_deployment_has_required_annotations")
    return len(reasons) == 0, reasons


def wait_for_annotations(profile: Dict[str, Any], kubectl: str, kubeconfig: Optional[Path]) -> Tuple[Dict[str, Any], List[Dict[str, Any]], bool, List[str]]:
    validation = profile.get("annotationValidation") or {}
    timeout_seconds = int(validation.get("waitTimeoutSeconds", 180))
    poll_seconds = int(validation.get("pollIntervalSeconds", 15))
    deadline = time.time() + timeout_seconds
    commands: List[Dict[str, Any]] = []
    latest_snapshot: Dict[str, Any] = {}
    latest_reasons: List[str] = ["not_checked"]

    while True:
        snapshot, capture_commands = capture_snapshot(profile, kubectl, kubeconfig)
        commands.extend(capture_commands)
        passed, reasons = validation_passed(profile, snapshot)
        latest_snapshot = snapshot
        latest_reasons = reasons
        if passed:
            return snapshot, commands, True, []
        if timeout_seconds <= 0 or time.time() >= deadline:
            return latest_snapshot, commands, False, latest_reasons
        time.sleep(poll_seconds)


def summarize(manifest: Dict[str, Any]) -> str:
    lines = [
        "mon-agent integration summary",
        "=============================",
        f"Profile: {manifest.get('profileId')}",
        f"Action: {manifest.get('action')}",
        f"Status: {manifest.get('status')}",
        f"Started: {manifest.get('startedAtUtc')}",
        f"Finished: {manifest.get('finishedAtUtc')}",
        "",
    ]
    if manifest.get("failureReasons"):
        lines.append("Failure reasons:")
        for reason in manifest.get("failureReasons", []):
            lines.append(f"- {reason}")
        lines.append("")
    snapshot = manifest.get("annotationSnapshot") or {}
    if snapshot:
        lines.extend([
            "Annotation snapshot:",
            f"- nodes: {snapshot.get('annotatedNodeCount')}/{snapshot.get('nodeCount')} annotated",
            f"- selected deployments: {snapshot.get('annotatedDeploymentCount')}/{snapshot.get('selectedDeploymentCount')} annotated",
            "",
        ])
    if manifest.get("renderedManifestPath"):
        lines.append(f"Rendered manifest: {manifest.get('renderedManifestPath')}")
    if manifest.get("validationSnapshotPath"):
        lines.append(f"Validation snapshot: {manifest.get('validationSnapshotPath')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install, capture, and validate mon-agent runtime annotations.")
    parser.add_argument("--repo-root", default=str(default_repo_root()))
    parser.add_argument("--profile-config", default="config/mon-agent/profiles/MA_RESOURCE_AWARE.json")
    parser.add_argument("--scenario-config", help="Optional resource-aware-scheduler scenario config used to derive active tenant namespaces and expected LocalAI deployments.")
    parser.add_argument("--action", choices=["plan", "apply", "capture", "validate"], default="apply")
    parser.add_argument("--kubeconfig")
    parser.add_argument("--output-root")
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-prometheus-service-check", action="store_true")
    parser.add_argument("--skip-rollout-wait", action="store_true")
    parser.add_argument("--write-latest-aliases", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    profile_path, base_profile = load_profile(repo_root, args.profile_config)
    scenario_path, scenario = load_scenario(repo_root, args.scenario_config)
    profile = apply_runtime_target_overrides(base_profile, scenario)
    paths = artifact_paths(repo_root, profile, args.output_root)
    run_id = args.run_id or f"{profile.get('monAgentProfileId', 'mon-agent')}_{compact_now()}"
    kubectl = get_nested(profile, "kubernetes", "kubectl", default="kubectl")
    kubeconfig = resolve_kubeconfig(repo_root, profile, args.kubeconfig)

    started_at = utc_now()
    command_results: List[Dict[str, Any]] = []
    failure_reasons: List[str] = []
    rendered = render_objects(profile)
    rendered_path = write_rendered_manifest(paths, run_id, rendered, repo_root)

    status = "dry_run" if args.dry_run else "planned"
    annotation_snapshot: Dict[str, Any] = {}
    snapshot_path: Optional[Path] = None

    if args.action == "plan":
        status = "dry_run" if args.dry_run else "planned"
    elif args.dry_run:
        status = "dry_run"
    else:
        if args.action in {"apply", "validate"} and not args.skip_prometheus_service_check and get_nested(profile, "decisionPolicy", "requirePrometheusServiceBeforeApply", default=True):
            prom_check = prometheus_service_check(profile, kubectl, kubeconfig)
            command_results.append(prom_check)
            if not prom_check.get("success"):
                failure_reasons.append("prometheus_service_not_available")

        if args.action == "apply" and not failure_reasons:
            deployment_cfg = profile.get("monAgentDeployment") or {}
            decision_policy = profile.get("decisionPolicy") or {}
            provider_managed = bool(decision_policy.get("providerManagedDeployment")) or str(deployment_cfg.get("installationMode") or "").lower() in {"provider_managed", "external", "provider"}
            if provider_managed and decision_policy.get("skipManifestApplyWhenProviderManaged", True):
                command_results.append({
                    "command": ["provider-managed-mon-agent"],
                    "startedAtUtc": utc_now(),
                    "finishedAtUtc": utc_now(),
                    "exitCode": 0,
                    "stdout": "mon-agent deployment is provider-managed; manifest apply skipped.",
                    "stderr": "",
                    "success": True,
                    "operation": "skip_mon_agent_manifest_apply",
                    "providerManagedDeployment": True,
                })
            else:
                apply_command = kubectl_base(kubectl, kubeconfig) + ["apply", "-f", str(rendered_path)]
                apply_result = run_command(apply_command, timeout=180)
                command_results.append(apply_result)
                if not apply_result.get("success"):
                    failure_reasons.append("mon_agent_manifest_apply_failed")

            label_results = label_application_namespaces(profile, kubectl, kubeconfig)
            command_results.extend(label_results)
            if any(not item.get("success") for item in label_results):
                failure_reasons.append("application_namespace_labeling_failed")

            if not args.skip_rollout_wait:
                rollout = wait_for_deployment(profile, kubectl, kubeconfig)
                command_results.append(rollout)
                if not rollout.get("success"):
                    failure_reasons.append("mon_agent_rollout_not_available")

            annotation_snapshot, capture_commands = capture_snapshot(profile, kubectl, kubeconfig)
            command_results.extend(capture_commands)
            status = "applied" if not failure_reasons else "failed"

        elif args.action == "capture" and not failure_reasons:
            annotation_snapshot, capture_commands = capture_snapshot(profile, kubectl, kubeconfig)
            command_results.extend(capture_commands)
            status = "captured" if not failure_reasons else "failed"

        elif args.action == "validate" and not failure_reasons:
            annotation_snapshot, capture_commands, passed, reasons = wait_for_annotations(profile, kubectl, kubeconfig)
            command_results.extend(capture_commands)
            if passed:
                status = "validated"
            else:
                status = "failed"
                failure_reasons.extend(reasons)

        elif failure_reasons:
            status = "failed"

    if annotation_snapshot:
        snapshot_path = paths["snapshots"] / f"{run_id}.mon-agent-validation-snapshot.json"
        write_json(snapshot_path, annotation_snapshot)
        if args.write_latest_aliases or get_nested(profile, "artifactPolicy", "writeLatestAliases", default=True):
            write_json(paths["latest_snapshot"], annotation_snapshot)

    log_path = paths["logs"] / f"{run_id}.mon-agent-command-results.json"
    write_json(log_path, command_results)

    manifest = {
        "schemaVersion": "mon-agent-integration-manifest/v1",
        "profileId": profile.get("monAgentProfileId"),
        "profilePath": rel_or_abs(profile_path, repo_root),
        "scenarioConfigPath": rel_or_abs(scenario_path, repo_root),
        "runtimeScenarioContext": profile.get("runtimeScenarioContext") or {},
        "targetNamespaces": (profile.get("namespaceSelection") or {}).get("applicationNamespaces") or [],
        "expectedDeploymentNames": (profile.get("annotationValidation") or {}).get("deploymentNames") or [],
        "action": args.action,
        "status": status,
        "startedAtUtc": started_at,
        "finishedAtUtc": utc_now(),
        "dryRun": args.dry_run,
        "providerManagedDeployment": bool((profile.get("decisionPolicy") or {}).get("providerManagedDeployment")) or str(((profile.get("monAgentDeployment") or {}).get("installationMode") or "")).lower() in {"provider_managed", "external", "provider"},
        "repoRoot": rel_or_abs(repo_root, repo_root),
        "kubeconfigPath": rel_or_abs(kubeconfig, repo_root),
        "renderedManifestPath": rel_or_abs(rendered_path, repo_root),
        "commandResultsPath": rel_or_abs(log_path, repo_root),
        "validationSnapshotPath": rel_or_abs(snapshot_path, repo_root),
        "failureReasons": failure_reasons,
        "commandResults": command_results,
        "annotationSnapshot": annotation_snapshot,
    }

    manifest_path = paths["manifests"] / f"{run_id}.mon-agent-manifest.json"
    write_json(manifest_path, manifest)
    summary_path = paths["summaries"] / f"{run_id}.mon-agent-summary.txt"
    write_text(summary_path, summarize(manifest))

    if args.write_latest_aliases or get_nested(profile, "artifactPolicy", "writeLatestAliases", default=True):
        write_json(paths["latest_manifest"], manifest)
        write_text(paths["latest_summary"], summarize(manifest))

    print("===============================================")
    print(" mon-agent integration")
    print("===============================================")
    print(f"Profile : {profile.get('monAgentProfileId')}")
    print(f"Action  : {args.action}")
    print(f"Status  : {status}")
    print(f"Manifest: {manifest_path}")
    print(f"Summary : {summary_path}")
    if failure_reasons:
        print("Failure reasons:")
        for reason in failure_reasons:
            print(f"- {reason}")

    return 0 if status in {"planned", "dry_run", "applied", "captured", "validated"} else 2


if __name__ == "__main__":
    sys.exit(main())
