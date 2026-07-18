#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PROFILE_CONFIG = "config/cluster-lens/profiles/CL_C9_PLACEMENT_SNAPSHOT.json"
DEFAULT_SCENARIO_CONFIG = "config/scenarios/network-aware-scheduler/NA_NETAWARE_2T_4N_L3_DIFFERENTIATED_M1M1_W2.json"
DEFAULT_OUTPUT_ROOT = "results/experimental-cycles/C9/variants/__profile_default__/network-aware-scheduler/cluster-lens"
LOCALAI_FALLBACK_APPS = {"localai-server", "localai-rpc-a", "localai-rpc-b", "localai-rpc-c", "localai-rpc-d"}
CSV_FIELDS = [
    "cycleId",
    "scenarioId",
    "logicalScenarioId",
    "schedulerMode",
    "schedulerName",
    "namespace",
    "tenant",
    "podName",
    "deployment",
    "app",
    "role",
    "phase",
    "nodeName",
    "masterNode",
    "workerNodes",
    "distinctTenantNodes",
    "masterWorkerCoLocated",
    "gatewayTrafficAnnotationPresent",
    "networkLatencyAnnotationsPresent",
    "packetLossAnnotationsPresent",
    "bandwidthAnnotationsPresent",
]


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


@dataclass
class CommandResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    started_at_utc: str
    finished_at_utc: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "startedAtUtc": self.started_at_utc,
            "finishedAtUtc": self.finished_at_utc,
            "exitCode": self.exit_code,
            "success": self.ok,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def resolve_repo_root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def repo_path(repo_root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = repo_root / path
    return path.resolve()


def rel_to_repo(repo_root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_artifact_payload_for_output(payload, path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            normalized = {key: normalize_csv_value(row.get(key)) for key in fields}
            writer.writerow(normalized)


def normalize_csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def ordered_unique(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def first_label(labels: dict[str, Any], keys: list[str], default: str = "") -> str:
    for key in keys:
        value = labels.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def nested(value: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def load_scenario(repo_root: Path, scenario_config: str | None) -> tuple[Path | None, dict[str, Any]]:
    if not scenario_config:
        return None, {}
    path = repo_path(repo_root, scenario_config)
    if path is None or not path.is_file():
        raise FileNotFoundError(f"Scenario config not found: {scenario_config}")
    return path, read_json(path)


def scenario_namespaces(scenario: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(scenario.get("namespaces") or [])
    if scenario.get("namespace"):
        values.append(scenario.get("namespace"))
    values.extend(nested(scenario, "applicationTopology", "expectedResources", "namespaces", default=[]) or [])
    for tenant in scenario.get("tenantClusters") or []:
        if isinstance(tenant, dict):
            values.append(tenant.get("namespace"))
    for target in scenario.get("benchmarkTargets") or []:
        if isinstance(target, dict):
            values.append(target.get("namespace"))
    return ordered_unique(values)


def scenario_deployments(scenario: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(nested(scenario, "applicationTopology", "expectedResources", "deploymentsPerTenant", default=[]) or [])
    for tenant in scenario.get("tenantClusters") or []:
        if isinstance(tenant, dict):
            values.extend(tenant.get("deploymentNames") or [])
    return ordered_unique(values)


def scenario_tenant_by_namespace(scenario: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for tenant in scenario.get("tenantClusters") or []:
        if isinstance(tenant, dict) and tenant.get("namespace") and tenant.get("tenantId"):
            result[str(tenant["namespace"])] = str(tenant["tenantId"])
    return result


def scenario_context(scenario: dict[str, Any]) -> dict[str, Any]:
    if not scenario:
        return {}
    return {
        "cycleId": scenario.get("associatedCycleId") or scenario.get("campaignId") or "C9",
        "scenarioId": scenario.get("scenarioId") or scenario.get("variantId"),
        "variantId": scenario.get("variantId") or scenario.get("scenarioId"),
        "logicalScenarioId": scenario.get("logicalScenarioId"),
        "schedulerMode": scenario.get("schedulerMode"),
        "schedulerName": scenario.get("schedulerName") or nested(scenario, "schedulerModePolicy", "schedulerName"),
        "latencyAlias": scenario.get("latencyAlias"),
        "latencyProfileId": scenario.get("latencyProfileId"),
        "tenantIds": scenario.get("tenantIds") or [],
        "namespaces": scenario_namespaces(scenario),
        "expectedDeploymentsPerTenant": scenario_deployments(scenario),
        "workerCountPerTenant": scenario.get("localAiWorkerCountPerTenant") or scenario.get("resolvedWorkerCount"),
        "modelMix": scenario.get("modelMix"),
        "trafficProfileId": scenario.get("trafficProfileId"),
    }


def resolve_output_dir(repo_root: Path, profile: dict[str, Any], scenario: dict[str, Any], explicit: str | None) -> Path:
    if explicit:
        return repo_path(repo_root, explicit) or (repo_root / explicit)
    artifact_policy = profile.get("artifactPolicy") or {}
    root = artifact_policy.get("root") or DEFAULT_OUTPUT_ROOT
    scenario_id = scenario.get("scenarioId") or scenario.get("variantId")
    if scenario_id:
        pattern = artifact_policy.get("perVariantOutputRootPattern") or root
        root = pattern.replace("<scenario-id>", str(scenario_id)).replace("__profile_default__", str(scenario_id))
    return repo_path(repo_root, root) or (repo_root / root)


def output_paths(output_dir: Path, profile: dict[str, Any]) -> dict[str, Path]:
    policy = profile.get("artifactPolicy") or {}
    names = {
        "rawSnapshot": policy.get("rawSnapshotFileName", "cluster-lens-snapshot.json"),
        "pods": policy.get("podsSnapshotFileName", "cluster-lens-kubernetes-pods.json"),
        "deployments": policy.get("deploymentsSnapshotFileName", "cluster-lens-kubernetes-deployments.json"),
        "nodes": policy.get("nodesSnapshotFileName", "cluster-lens-kubernetes-nodes.json"),
        "summary": policy.get("placementSummaryFileName", "cluster-lens-placement-summary.json"),
        "signature": policy.get("placementSignatureFileName", "cluster-lens-placement-signature.csv"),
        "manifest": policy.get("captureManifestFileName", "cluster-lens-capture-manifest.json"),
    }
    return {key: output_dir / filename for key, filename in names.items()}


def kubectl_base(kubectl: str, kubeconfig: Path | None) -> list[str]:
    command = [kubectl]
    if kubeconfig is not None:
        command.extend(["--kubeconfig", str(kubeconfig)])
    return command


def run_command(command: list[str], timeout: int | None = None) -> CommandResult:
    started = utc_now()
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
        return CommandResult(command, completed.returncode, completed.stdout, completed.stderr, started, utc_now())
    except Exception as exc:
        return CommandResult(command, 1, "", str(exc), started, utc_now())


def run_kubectl_json(kubectl: str, kubeconfig: Path | None, args: list[str], timeout: int | None = None) -> tuple[dict[str, Any], CommandResult]:
    command = kubectl_base(kubectl, kubeconfig) + args + ["-o", "json"]
    result = run_command(command, timeout=timeout)
    if not result.ok:
        return {"apiVersion": "v1", "kind": "List", "items": []}, result
    try:
        return json.loads(result.stdout or "{}"), result
    except json.JSONDecodeError as exc:
        return {"apiVersion": "v1", "kind": "List", "items": []}, CommandResult(
            command=result.command,
            exit_code=1,
            stdout=result.stdout,
            stderr=f"Unable to parse kubectl JSON output: {exc}",
            started_at_utc=result.started_at_utc,
            finished_at_utc=utc_now(),
        )


def merge_lists(kind: str, lists: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for payload in lists:
        items.extend(payload.get("items") or [])
    return {"apiVersion": "v1", "kind": kind, "items": items}


def collect_namespaced_resource(
    kubectl: str,
    kubeconfig: Path | None,
    resource: str,
    namespaces: list[str],
    tenant_namespaces_only: bool,
    fallback_all: bool,
    timeout: int | None,
) -> tuple[dict[str, Any], list[CommandResult]]:
    commands: list[CommandResult] = []
    if tenant_namespaces_only and namespaces:
        payloads: list[dict[str, Any]] = []
        for namespace in namespaces:
            payload, result = run_kubectl_json(kubectl, kubeconfig, ["get", resource, "-n", namespace], timeout=timeout)
            commands.append(result)
            payloads.append(payload)
        return merge_lists(f"{resource.title()}List", payloads), commands
    if tenant_namespaces_only and not namespaces and fallback_all:
        payload, result = run_kubectl_json(kubectl, kubeconfig, ["get", resource, "-A"], timeout=timeout)
        commands.append(result)
        return payload, commands
    payload, result = run_kubectl_json(kubectl, kubeconfig, ["get", resource, "-A"], timeout=timeout)
    commands.append(result)
    return payload, commands


def collect_nodes(kubectl: str, kubeconfig: Path | None, timeout: int | None) -> tuple[dict[str, Any], list[CommandResult]]:
    payload, result = run_kubectl_json(kubectl, kubeconfig, ["get", "nodes"], timeout=timeout)
    return payload, [result]


def start_port_forward(kubectl: str, kubeconfig: Path | None, namespace: str, service_name: str, local_port: int, service_port: int) -> subprocess.Popen[str]:
    command = kubectl_base(kubectl, kubeconfig) + [
        "-n",
        namespace,
        "port-forward",
        f"svc/{service_name}",
        f"{local_port}:{service_port}",
    ]
    kwargs: dict[str, Any] = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
    if os.name != "nt":
        kwargs["preexec_fn"] = os.setsid
    return subprocess.Popen(command, **kwargs)


def stop_port_forward(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def fetch_json_url(url: str, timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw or "{}")


def wait_for_snapshot_url(url: str, timeout_seconds: int, request_timeout_seconds: int) -> tuple[bool, str]:
    deadline = time.time() + max(1, timeout_seconds)
    last_error = ""
    while time.time() < deadline:
        try:
            fetch_json_url(url, request_timeout_seconds)
            return True, ""
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.5)
    return False, last_error


def fetch_cluster_lens_snapshot(
    profile: dict[str, Any],
    kubectl: str,
    kubeconfig: Path | None,
    explicit_url: str | None,
    use_port_forward: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cluster_lens = profile.get("clusterLens") or {}
    kubernetes = profile.get("kubernetes") or {}
    port_forward_cfg = kubernetes.get("portForward") or {}
    api_path = cluster_lens.get("apiPath", "/api/snapshot")
    request_timeout = int(cluster_lens.get("requestTimeoutSeconds", 15))
    process: subprocess.Popen[str] | None = None
    metadata: dict[str, Any] = {
        "accessMode": "direct_url" if explicit_url else ("port_forward" if use_port_forward else "direct_url"),
        "snapshotUrl": explicit_url,
        "portForward": None,
        "success": False,
        "error": None,
    }
    url = explicit_url
    try:
        if not url and use_port_forward:
            local_host = port_forward_cfg.get("localHost", "127.0.0.1")
            local_port = int(port_forward_cfg.get("localPort", 18088))
            service_port = int(kubernetes.get("clusterLensServicePort", 8088))
            namespace = kubernetes.get("clusterLensNamespace", "observability")
            service_name = kubernetes.get("clusterLensServiceName", "cluster-lens")
            process = start_port_forward(kubectl, kubeconfig, namespace, service_name, local_port, service_port)
            url = f"http://{local_host}:{local_port}{api_path}"
            metadata["snapshotUrl"] = url
            metadata["portForward"] = {
                "namespace": namespace,
                "serviceName": service_name,
                "localPort": local_port,
                "servicePort": service_port,
                "processId": process.pid,
            }
            time.sleep(float(port_forward_cfg.get("startupGraceSeconds", 1)))
            ready, error = wait_for_snapshot_url(url, int(port_forward_cfg.get("readyTimeoutSeconds", 30)), request_timeout)
            if not ready:
                raise RuntimeError(f"cluster-lens port-forward did not become ready: {error}")
        if not url:
            raise ValueError("No cluster-lens snapshot URL was provided and port-forward is disabled.")
        snapshot = fetch_json_url(url, request_timeout)
        metadata["success"] = True
        return snapshot, metadata
    except Exception as exc:
        metadata["error"] = str(exc)
        return {"captureStatus": "failed", "error": str(exc), "generatedAt": utc_now()}, metadata
    finally:
        stop_port_forward(process)


def deployment_map(deployments_snapshot: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for deployment in deployments_snapshot.get("items") or []:
        metadata = deployment.get("metadata") or {}
        namespace = metadata.get("namespace") or ""
        name = metadata.get("name") or ""
        if namespace and name:
            result[(namespace, name)] = deployment
    return result


def node_map(nodes_snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for node in nodes_snapshot.get("items") or []:
        metadata = node.get("metadata") or {}
        name = metadata.get("name") or ""
        if name:
            result[name] = node
    return result


def labels_match(selector: dict[str, Any], labels: dict[str, Any]) -> bool:
    match_labels = selector.get("matchLabels") or {}
    for key, expected in match_labels.items():
        if labels.get(key) != expected:
            return False
    return bool(match_labels)


def resolve_deployment_for_pod(pod: dict[str, Any], deployments: dict[tuple[str, str], dict[str, Any]]) -> str:
    metadata = pod.get("metadata") or {}
    namespace = metadata.get("namespace") or ""
    labels = metadata.get("labels") or {}
    for (dep_namespace, dep_name), deployment in deployments.items():
        if dep_namespace != namespace:
            continue
        selector = nested(deployment, "spec", "selector", default={}) or {}
        if labels_match(selector, labels):
            return dep_name
    owners = metadata.get("ownerReferences") or []
    for owner in owners:
        if owner.get("kind") == "Deployment" and owner.get("name"):
            return str(owner["name"])
        if owner.get("kind") == "ReplicaSet" and owner.get("name"):
            name = str(owner["name"])
            for (dep_namespace, dep_name) in deployments.keys():
                if dep_namespace == namespace and name.startswith(dep_name + "-"):
                    return dep_name
            return name
    return ""


def has_annotation_prefix(annotations: dict[str, Any], prefix: str) -> bool:
    return any(str(key).startswith(prefix) for key in annotations.keys())


def deployment_annotations_for(deployments: dict[tuple[str, str], dict[str, Any]], namespace: str, deployment_name: str) -> dict[str, Any]:
    deployment = deployments.get((namespace, deployment_name)) or {}
    return nested(deployment, "metadata", "annotations", default={}) or {}


def node_annotations_for(nodes: dict[str, dict[str, Any]], node_name: str) -> dict[str, Any]:
    node = nodes.get(node_name) or {}
    return nested(node, "metadata", "annotations", default={}) or {}


def infer_app(labels: dict[str, Any], deployment: str, app_keys: list[str]) -> str:
    app = first_label(labels, app_keys)
    if app in {"server", "rpc-worker"} and deployment:
        return deployment
    return app or deployment


def infer_role(labels: dict[str, Any], deployment: str, role_keys: list[str]) -> str:
    role = first_label(labels, role_keys)
    if role:
        return role
    if deployment == "localai-server":
        return "master"
    if deployment.startswith("localai-rpc"):
        return "worker"
    return "unknown"


def localai_pod_rows(
    scenario: dict[str, Any],
    profile: dict[str, Any],
    pods_snapshot: dict[str, Any],
    deployments_snapshot: dict[str, Any],
    nodes_snapshot: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    extraction = profile.get("placementExtraction") or {}
    scope = profile.get("captureScope") or {}
    tenant_keys = extraction.get("tenantLabelKeys") or ["group", "localai.benchmark/tenant"]
    role_keys = extraction.get("roleLabelKeys") or ["role", "localai.benchmark/role"]
    app_keys = extraction.get("appLabelKeys") or ["app", "app.kubernetes.io/name", "localai.benchmark/component"]
    scheduler_mode_keys = extraction.get("schedulerModeLabelKeys") or ["localai.benchmark/scheduler-mode"]
    localai_apps = set(scope.get("localAiAppNames") or []) or LOCALAI_FALLBACK_APPS
    expected_deployments = set(scenario_deployments(scenario) or scope.get("requiredDeploymentNamesPerTenant") or [])
    namespaces = set(scenario_namespaces(scenario))
    tenant_by_namespace = scenario_tenant_by_namespace(scenario)
    deployments = deployment_map(deployments_snapshot)
    nodes = node_map(nodes_snapshot)
    context = scenario_context(scenario)
    gateway_key = extraction.get("gatewayTrafficAnnotationKey", "traffic.localai-gateway-istio")

    provisional: list[dict[str, Any]] = []
    for pod in pods_snapshot.get("items") or []:
        metadata = pod.get("metadata") or {}
        spec = pod.get("spec") or {}
        status = pod.get("status") or {}
        namespace = metadata.get("namespace") or ""
        labels = metadata.get("labels") or {}
        if namespaces and namespace not in namespaces:
            continue
        deployment = resolve_deployment_for_pod(pod, deployments)
        app = infer_app(labels, deployment, app_keys)
        role = infer_role(labels, deployment, role_keys)
        if app not in localai_apps and deployment not in localai_apps and deployment not in expected_deployments:
            continue
        tenant = first_label(labels, tenant_keys) or tenant_by_namespace.get(namespace, namespace)
        scheduler_name = spec.get("schedulerName") or "default-scheduler"
        row = {
            "cycleId": context.get("cycleId") or "C9",
            "scenarioId": context.get("scenarioId") or "",
            "logicalScenarioId": context.get("logicalScenarioId") or "",
            "schedulerMode": context.get("schedulerMode") or first_label(labels, scheduler_mode_keys),
            "schedulerName": scheduler_name,
            "namespace": namespace,
            "tenant": tenant,
            "podName": metadata.get("name") or "",
            "deployment": deployment,
            "app": app,
            "role": role,
            "phase": status.get("phase") or "",
            "nodeName": spec.get("nodeName") or "",
            "labels": labels,
            "annotations": metadata.get("annotations") or {},
            "deploymentAnnotations": deployment_annotations_for(deployments, namespace, deployment),
            "nodeAnnotations": node_annotations_for(nodes, spec.get("nodeName") or ""),
            "createdAt": metadata.get("creationTimestamp"),
            "podUid": metadata.get("uid"),
        }
        provisional.append(row)

    by_tenant: dict[str, list[dict[str, Any]]] = {}
    for row in provisional:
        by_tenant.setdefault(row["tenant"], []).append(row)

    final_rows: list[dict[str, Any]] = []
    per_tenant: dict[str, Any] = {}
    for tenant, rows in sorted(by_tenant.items()):
        master_nodes = ordered_unique([row["nodeName"] for row in rows if row["role"] == "master" and row.get("nodeName")])
        worker_nodes = ordered_unique([row["nodeName"] for row in rows if row["role"] == "worker" and row.get("nodeName")])
        all_nodes = ordered_unique([row["nodeName"] for row in rows if row.get("nodeName")])
        master_node = master_nodes[0] if master_nodes else ""
        master_worker_colocated = bool(master_node and master_node in worker_nodes)
        for row in rows:
            deployment_annotations = row.pop("deploymentAnnotations", {}) or {}
            node_annotations = row.pop("nodeAnnotations", {}) or {}
            row["masterNode"] = master_node
            row["workerNodes"] = worker_nodes
            row["distinctTenantNodes"] = len(all_nodes)
            row["masterWorkerCoLocated"] = master_worker_colocated
            row["gatewayTrafficAnnotationPresent"] = gateway_key in deployment_annotations
            row["networkLatencyAnnotationsPresent"] = has_annotation_prefix(node_annotations, "network-latency.")
            row["packetLossAnnotationsPresent"] = has_annotation_prefix(node_annotations, "packet-loss.")
            row["bandwidthAnnotationsPresent"] = has_annotation_prefix(node_annotations, "network-bandwidth.")
            final_rows.append(row)
        per_tenant[tenant] = {
            "tenant": tenant,
            "namespaces": ordered_unique([row["namespace"] for row in rows]),
            "podCount": len(rows),
            "masterPods": sorted([row["podName"] for row in rows if row["role"] == "master"]),
            "workerPods": sorted([row["podName"] for row in rows if row["role"] == "worker"]),
            "masterNodes": master_nodes,
            "workerNodes": worker_nodes,
            "distinctTenantNodes": len(all_nodes),
            "masterWorkerCoLocated": master_worker_colocated,
            "unscheduledPods": sorted([row["podName"] for row in rows if not row.get("nodeName")]),
            "schedulerNames": ordered_unique([row["schedulerName"] for row in rows]),
        }

    final_rows.sort(key=lambda item: (item.get("namespace", ""), item.get("tenant", ""), item.get("deployment", ""), item.get("podName", "")))
    summary_counts = {
        "localAiPodCount": len(final_rows),
        "tenantCount": len(per_tenant),
        "unscheduledLocalAiPodCount": sum(1 for row in final_rows if not row.get("nodeName")),
        "scheduledLocalAiPodCount": sum(1 for row in final_rows if row.get("nodeName")),
        "distinctObservedNodes": len(ordered_unique([row.get("nodeName") for row in final_rows if row.get("nodeName")])),
        "observedSchedulerNames": ordered_unique([row.get("schedulerName") for row in final_rows]),
    }
    return final_rows, {"counts": summary_counts, "tenants": per_tenant}


def node_annotation_coverage(nodes_snapshot: dict[str, Any], prefixes: list[str]) -> dict[str, Any]:
    nodes = nodes_snapshot.get("items") or []
    by_node: dict[str, Any] = {}
    totals = {prefix: 0 for prefix in prefixes}
    for node in nodes:
        metadata = node.get("metadata") or {}
        name = metadata.get("name") or ""
        annotations = metadata.get("annotations") or {}
        coverage = {prefix: has_annotation_prefix(annotations, prefix) for prefix in prefixes}
        for prefix, present in coverage.items():
            if present:
                totals[prefix] += 1
        if name:
            by_node[name] = coverage
    return {"nodeCount": len(nodes), "prefixTotals": totals, "byNode": by_node}


def build_summary(
    repo_root: Path,
    profile_path: Path,
    scenario_path: Path | None,
    output_dir: Path,
    paths: dict[str, Path],
    profile: dict[str, Any],
    scenario: dict[str, Any],
    snapshot: dict[str, Any],
    snapshot_metadata: dict[str, Any],
    pods_snapshot: dict[str, Any],
    deployments_snapshot: dict[str, Any],
    nodes_snapshot: dict[str, Any],
    signature_rows: list[dict[str, Any]],
    placement_summary: dict[str, Any],
    capture_stage: str,
    command_results: list[CommandResult],
    dry_run: bool,
) -> dict[str, Any]:
    extraction = profile.get("placementExtraction") or {}
    node_prefixes = extraction.get("nodeAnnotationPrefixes") or ["network-latency.", "packet-loss.", "network-bandwidth."]
    validation = profile.get("validationPolicy") or {}
    required_localai = bool(validation.get("requireAtLeastOneLocalAiPod", True))
    cluster_lens_ok = bool(snapshot_metadata.get("success"))
    localai_count = len(signature_rows)
    command_failures = [result.to_dict() for result in command_results if not result.ok]
    errors: list[str] = []
    if validation.get("requireClusterLensSnapshot", True) and not dry_run and not cluster_lens_ok:
        errors.append("cluster-lens snapshot was not captured successfully")
    if required_localai and not dry_run and localai_count == 0:
        errors.append("no LocalAI pods were found in the Kubernetes pod snapshot")
    if command_failures and not dry_run:
        errors.append("one or more kubectl snapshot commands failed")

    return {
        "schemaVersion": "cluster-lens-placement-summary/v1",
        "generatedAtUtc": utc_now(),
        "captureStage": capture_stage or None,
        "captureStatus": "dry_run" if dry_run else ("captured" if not errors else "partial"),
        "profile": {
            "clusterLensProfileId": profile.get("clusterLensProfileId"),
            "profilePath": rel_to_repo(repo_root, profile_path),
        },
        "scenario": scenario_context(scenario),
        "scenarioConfigPath": rel_to_repo(repo_root, scenario_path) if scenario_path else None,
        "output": {
            "root": rel_to_repo(repo_root, output_dir),
            "rawSnapshot": rel_to_repo(repo_root, paths["rawSnapshot"]),
            "podsSnapshot": rel_to_repo(repo_root, paths["pods"]),
            "deploymentsSnapshot": rel_to_repo(repo_root, paths["deployments"]),
            "nodesSnapshot": rel_to_repo(repo_root, paths["nodes"]),
            "placementSummary": rel_to_repo(repo_root, paths["summary"]),
            "placementSignature": rel_to_repo(repo_root, paths["signature"]),
            "captureManifest": rel_to_repo(repo_root, paths["manifest"]),
        },
        "clusterLens": {
            "snapshotCaptured": cluster_lens_ok,
            "snapshotUrl": snapshot_metadata.get("snapshotUrl"),
            "accessMode": snapshot_metadata.get("accessMode"),
            "error": snapshot_metadata.get("error"),
            "rawNodeCount": len(snapshot.get("nodes") or []),
            "rawPodCount": len(snapshot.get("pods") or []),
            "rawNodeEdgeCount": len(snapshot.get("nodeEdges") or []),
            "rawAppEdgeCount": len(snapshot.get("appEdges") or []),
            "warnings": snapshot.get("warnings") or [],
        },
        "kubernetesSnapshots": {
            "podCount": len(pods_snapshot.get("items") or []),
            "deploymentCount": len(deployments_snapshot.get("items") or []),
            "nodeCount": len(nodes_snapshot.get("items") or []),
            "commandFailures": command_failures,
        },
        "placement": placement_summary,
        "nodeAnnotationCoverage": node_annotation_coverage(nodes_snapshot, node_prefixes),
        "validation": {
            "success": dry_run or not errors,
            "errors": errors,
            "policy": validation,
        },
        "commands": [result.to_dict() for result in command_results],
    }


def build_manifest(
    repo_root: Path,
    profile_path: Path,
    scenario_path: Path | None,
    output_dir: Path,
    paths: dict[str, Path],
    profile: dict[str, Any],
    scenario: dict[str, Any],
    capture_stage: str,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "schemaVersion": "cluster-lens-capture-manifest/v1",
        "generatedAtUtc": utc_now(),
        "captureStage": capture_stage or None,
        "dryRun": dry_run,
        "profilePath": rel_to_repo(repo_root, profile_path),
        "scenarioConfigPath": rel_to_repo(repo_root, scenario_path) if scenario_path else None,
        "scenario": scenario_context(scenario),
        "outputRoot": rel_to_repo(repo_root, output_dir),
        "plannedArtifacts": {key: rel_to_repo(repo_root, value) for key, value in paths.items()},
        "profile": {
            "clusterLensProfileId": profile.get("clusterLensProfileId"),
            "clusterLensVersion": nested(profile, "clusterLens", "version"),
            "accessMode": nested(profile, "kubernetes", "defaultAccessMode"),
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture cluster-lens topology snapshots and Kubernetes placement evidence.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--profile-config", default=DEFAULT_PROFILE_CONFIG)
    parser.add_argument("--scenario-config", default=None)
    parser.add_argument("--kubeconfig", default=None)
    parser.add_argument("--kubectl", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--snapshot-url", default=None, help="Direct cluster-lens /api/snapshot URL. Overrides port-forward access.")
    parser.add_argument("--capture-stage", default="", help="Optional logical pipeline stage associated with this placement capture.")
    parser.add_argument("--use-port-forward", action="store_true", help="Fetch the cluster-lens snapshot through kubectl port-forward.")
    parser.add_argument("--no-port-forward", action="store_true", help="Disable port-forward when no direct snapshot URL is provided.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = resolve_repo_root(args.repo_root)
    profile_path = repo_path(repo_root, args.profile_config)
    if profile_path is None or not profile_path.is_file():
        raise FileNotFoundError(f"cluster-lens profile not found: {args.profile_config}")
    profile = read_json(profile_path)
    scenario_config = args.scenario_config or None
    scenario_path, scenario = load_scenario(repo_root, scenario_config) if scenario_config else (None, {})
    capture_stage = str(args.capture_stage or "").strip()
    output_dir = resolve_output_dir(repo_root, profile, scenario, args.output_dir)
    paths = output_paths(output_dir, profile)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(repo_root, profile_path, scenario_path, output_dir, paths, profile, scenario, capture_stage, args.dry_run)
    write_json(paths["manifest"], manifest)

    if args.dry_run:
        empty_list = {"apiVersion": "v1", "kind": "List", "items": []}
        summary = build_summary(
            repo_root,
            profile_path,
            scenario_path,
            output_dir,
            paths,
            profile,
            scenario,
            {"captureStatus": "dry_run", "generatedAt": utc_now()},
            {"success": True, "accessMode": "dry_run", "snapshotUrl": None, "error": None},
            empty_list,
            empty_list,
            empty_list,
            [],
            {"counts": {}, "tenants": {}},
            capture_stage,
            [],
            dry_run=True,
        )
        write_json(paths["rawSnapshot"], {"captureStatus": "dry_run", "generatedAt": utc_now()})
        write_json(paths["pods"], empty_list)
        write_json(paths["deployments"], empty_list)
        write_json(paths["nodes"], empty_list)
        write_json(paths["summary"], summary)
        write_csv(paths["signature"], [], CSV_FIELDS)
        return 0

    kubernetes = profile.get("kubernetes") or {}
    capture_scope = profile.get("captureScope") or {}
    kubectl = args.kubectl or kubernetes.get("kubectl") or "kubectl"
    kubeconfig = repo_path(repo_root, args.kubeconfig or profile.get("kubeconfigPath"))
    if kubeconfig is not None and not kubeconfig.exists():
        kubeconfig = None if args.kubeconfig is None else kubeconfig

    use_port_forward = bool(args.use_port_forward)
    if args.snapshot_url:
        use_port_forward = False
    elif args.no_port_forward:
        use_port_forward = False
    else:
        use_port_forward = bool(nested(profile, "kubernetes", "portForward", "enabledByDefault", default=True))

    snapshot, snapshot_metadata = fetch_cluster_lens_snapshot(profile, kubectl, kubeconfig, args.snapshot_url, use_port_forward)

    namespaces = scenario_namespaces(scenario)
    tenant_namespaces_only = bool(capture_scope.get("tenantNamespacesOnly", True))
    fallback_all = bool(capture_scope.get("fallbackToAllNamespacesWhenScenarioNamespacesMissing", True))
    command_timeout = int((profile.get("clusterLens") or {}).get("requestTimeoutSeconds", 15))
    command_results: list[CommandResult] = []

    pods_snapshot, pod_commands = collect_namespaced_resource(kubectl, kubeconfig, "pods", namespaces, tenant_namespaces_only, fallback_all, command_timeout)
    deployments_snapshot, deployment_commands = collect_namespaced_resource(kubectl, kubeconfig, "deployments", namespaces, tenant_namespaces_only, fallback_all, command_timeout)
    nodes_snapshot, node_commands = collect_nodes(kubectl, kubeconfig, command_timeout)
    command_results.extend(pod_commands)
    command_results.extend(deployment_commands)
    command_results.extend(node_commands)

    signature_rows, placement_summary = localai_pod_rows(scenario, profile, pods_snapshot, deployments_snapshot, nodes_snapshot)
    summary = build_summary(
        repo_root,
        profile_path,
        scenario_path,
        output_dir,
        paths,
        profile,
        scenario,
        snapshot,
        snapshot_metadata,
        pods_snapshot,
        deployments_snapshot,
        nodes_snapshot,
        signature_rows,
        placement_summary,
        capture_stage,
        command_results,
        dry_run=False,
    )

    write_json(paths["rawSnapshot"], snapshot)
    write_json(paths["pods"], pods_snapshot)
    write_json(paths["deployments"], deployments_snapshot)
    write_json(paths["nodes"], nodes_snapshot)
    write_json(paths["summary"], summary)
    write_csv(paths["signature"], signature_rows, CSV_FIELDS)

    return 0 if nested(summary, "validation", "success", default=False) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        raise SystemExit(130)
