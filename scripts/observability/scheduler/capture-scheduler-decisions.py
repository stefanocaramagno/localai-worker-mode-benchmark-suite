#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SCENARIO_CONFIG = "config/scenarios/default-scheduler/DS_2T_4N_L1_DIFFERENTIATED_M1M1_W2.json"
DEFAULT_OUTPUT_ROOT = "results/experimental-cycles/C7/scheduler"
DEFAULT_ARTIFACT_NAME = "default-scheduler-decision-evidence.json"
DEFAULT_SELECTOR = "localai.benchmark/scheduler-mode=default-scheduler"
LOCALAI_APPS = {"localai-server", "localai-rpc-a", "localai-rpc-b", "localai-rpc-c", "localai-rpc-d"}
SCHEDULING_EVENT_REASONS = {"Scheduled", "FailedScheduling", "Preempted", "NotTriggerScaleUp"}
CPU_KEYS = {"cpu"}
MEMORY_KEYS = {"memory"}

PLACEMENT_CLASSIFICATION_SCHEMA_VERSION = "placement-classification/v1"
SCHEDULER_DECISION_EVIDENCE_SCHEMA_VERSION = "scheduler-decision-evidence/v1"
DEFAULT_RESOURCE_CONTENTION_POD_THRESHOLD = 3

PLACEMENT_CATEGORY_DEFINITIONS = {
    "server_worker_colocated": "At least one LocalAI server and its RPC workers for a tenant are scheduled on the same node.",
    "server_worker_partially_colocated": "Some server-worker communication remains local, but at least one worker is scheduled on a different node.",
    "server_worker_split": "At least one LocalAI server and one RPC worker for the same tenant are scheduled on different nodes.",
    "tenant_interference_risk": "Pods belonging to different tenants share at least one Kubernetes worker node.",
    "fully_spread": "The tenant's LocalAI server and RPC workers are scheduled on distinct nodes.",
    "resource_contention_risk": "A node hosts several LocalAI server or RPC worker pods and may become a local contention point.",
    "latency_sensitive_split": "Latency injection is enabled and communicating LocalAI components are scheduled on different nodes.",
    "missing_server_pod": "No LocalAI server pod was observed for a tenant in the captured runtime state.",
    "missing_worker_pods": "The observed number of LocalAI RPC worker pods is lower than the expected worker count.",
    "unscheduled_pods": "One or more LocalAI pods were observed without an assigned node.",
    "default_scheduler_unclassified": "The observed placement does not match any explicit classification rule.",
}

PLACEMENT_CATEGORY_SEVERITY = {
    "latency_sensitive_split": "critical",
    "missing_server_pod": "critical",
    "missing_worker_pods": "critical",
    "unscheduled_pods": "critical",
    "server_worker_split": "warning",
    "server_worker_partially_colocated": "warning",
    "tenant_interference_risk": "warning",
    "resource_contention_risk": "warning",
    "fully_spread": "info",
    "server_worker_colocated": "info",
    "default_scheduler_unclassified": "info",
}

SEVERITY_RANK = {
    "info": 0,
    "warning": 1,
    "critical": 2,
}


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

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exitCode": self.exit_code,
            "success": self.ok,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass
class TenantContext:
    tenant_id: str
    namespace: str
    role: str = "tenant"
    model_name: str | None = None
    worker_count: int | None = None


@dataclass
class PodEvidence:
    scenario_id: str
    tenant_id: str
    namespace: str
    deployment: str | None
    pod_name: str
    pod_uid: str | None
    node_name: str | None
    pod_phase: str | None
    start_time: str | None
    labels: dict[str, Any]
    annotations: dict[str, Any]
    role: str
    resource_requests: dict[str, Any]
    resource_limits: dict[str, Any]
    restart_count: int
    owner_references: list[dict[str, Any]]
    events: list[dict[str, Any]] = field(default_factory=list)
    placement_classification: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenarioId": self.scenario_id,
            "tenantId": self.tenant_id,
            "namespace": self.namespace,
            "deployment": self.deployment,
            "podName": self.pod_name,
            "podUid": self.pod_uid,
            "nodeName": self.node_name,
            "podPhase": self.pod_phase,
            "startTime": self.start_time,
            "labels": self.labels,
            "annotations": self.annotations,
            "role": self.role,
            "resourceRequests": self.resource_requests,
            "resourceLimits": self.resource_limits,
            "restartCount": self.restart_count,
            "ownerReferences": self.owner_references,
            "events": self.events,
            "placementClassification": self.placement_classification,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def resolve_repo_root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def resolve_path(repo_root: Path, value: str | None, default: str | None = None) -> Path:
    raw = value or default
    if not raw:
        raise ValueError("Path value is empty.")
    path = Path(raw).expanduser()
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


def load_json(path: Path) -> dict[str, Any]:
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


def build_kubectl_command(kubectl: str, kubeconfig: Path | None, args: list[str]) -> list[str]:
    command = [kubectl]
    if kubeconfig is not None:
        command.extend(["--kubeconfig", str(kubeconfig)])
    command.extend(args)
    return command


def run_command(command: list[str]) -> CommandResult:
    completed = subprocess.run(command, text=True, capture_output=True)
    return CommandResult(
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_kubectl_json(kubectl: str, kubeconfig: Path | None, args: list[str]) -> tuple[dict[str, Any], CommandResult]:
    command = build_kubectl_command(kubectl, kubeconfig, args + ["-o", "json"])
    result = run_command(command)
    if not result.ok:
        return {}, result
    try:
        return json.loads(result.stdout or "{}"), result
    except json.JSONDecodeError as exc:
        error = CommandResult(
            command=command,
            exit_code=1,
            stdout=result.stdout,
            stderr=f"Unable to parse kubectl JSON output: {exc}",
        )
        return {}, error


def ordered_unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def scenario_id(scenario: dict[str, Any], scenario_config: Path) -> str:
    return str(scenario.get("scenarioId") or scenario.get("variantId") or scenario_config.stem)


def localai_worker_count_per_tenant_from_scenario(scenario: dict[str, Any]) -> int | None:
    for key in ("localAiWorkerCountPerTenant", "resolvedWorkerCountPerTenant", "resolvedWorkerCount"):
        raw = scenario.get(key)
        if raw is None:
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    worker_scenario = str(scenario.get("workerScenario") or "").strip().upper()
    if worker_scenario.startswith("W"):
        try:
            value = int(worker_scenario[1:])
        except (TypeError, ValueError):
            value = -1
        if value >= 0:
            return value
    return None


def tenant_contexts_from_scenario(scenario: dict[str, Any]) -> list[TenantContext]:
    contexts: list[TenantContext] = []
    for item in scenario.get("tenantClusters") or []:
        tenant_id = str(item.get("tenantId") or "").strip()
        namespace = str(item.get("namespace") or "").strip()
        if not tenant_id or not namespace:
            continue
        worker_count = item.get("workerCount")
        try:
            worker_count_int = int(worker_count) if worker_count is not None else None
        except Exception:
            worker_count_int = None
        contexts.append(
            TenantContext(
                tenant_id=tenant_id,
                namespace=namespace,
                role=str(item.get("role") or "tenant"),
                model_name=str(item.get("modelName") or "").strip() or None,
                worker_count=worker_count_int,
            )
        )
    if not contexts:
        tenant_ids = [str(item) for item in scenario.get("tenantIds") or []]
        namespaces = [str(item) for item in scenario.get("namespaces") or []]
        if tenant_ids and namespaces:
            for index, namespace in enumerate(namespaces):
                tenant_id = tenant_ids[index] if index < len(tenant_ids) else f"tenant-{index + 1}"
                contexts.append(TenantContext(tenant_id=tenant_id, namespace=namespace))
    if not contexts:
        namespace = str(scenario.get("namespace") or "").strip()
        if namespace:
            contexts.append(TenantContext(tenant_id="tenant-a", namespace=namespace, role="primary_benchmark_tenant"))
    return contexts


def output_dir_from_scenario(repo_root: Path, scenario: dict[str, Any], scenario_config: Path, override: str | None) -> Path:
    if override:
        return resolve_path(repo_root, override)
    scheduler_evidence = scenario.get("schedulerEvidence") or {}
    artifact_root = scheduler_evidence.get("artifactRoot")
    if artifact_root:
        return resolve_path(repo_root, str(artifact_root))
    root = scenario.get("schedulerEvidenceRoot") or DEFAULT_OUTPUT_ROOT
    return resolve_path(repo_root, str(root)) / scenario_id(scenario, scenario_config)


def artifact_name_from_scenario(scenario: dict[str, Any]) -> str:
    scheduler_evidence = scenario.get("schedulerEvidence") or {}
    return str(scheduler_evidence.get("artifactName") or DEFAULT_ARTIFACT_NAME)


def latest_artifact_name_from_scenario(scenario: dict[str, Any], artifact_name: str) -> str:
    scheduler_evidence = scenario.get("schedulerEvidence") or {}
    configured = str(scheduler_evidence.get("latestArtifactName") or "").strip()
    if configured:
        return configured
    if artifact_name == DEFAULT_ARTIFACT_NAME:
        return "latest-default-scheduler-decision-evidence.json"
    stem = artifact_name[:-5] if artifact_name.endswith(".json") else artifact_name
    return f"latest-{stem}.json"


def text_alias_name(json_alias_name: str) -> str:
    return json_alias_name[:-5] + ".txt" if json_alias_name.endswith(".json") else json_alias_name + ".txt"


def selector_from_scenario(scenario: dict[str, Any], requested_selector: str | None) -> str | None:
    if requested_selector not in (None, "", DEFAULT_SELECTOR):
        return requested_selector.strip()
    scheduler_evidence = scenario.get("schedulerEvidence") or {}
    configured = str(scheduler_evidence.get("selector") or "").strip()
    if configured:
        return configured
    policy = scenario.get("schedulerModePolicy") or {}
    topology = scenario.get("applicationTopology") or {}
    mode = str(policy.get("schedulerModeRole") or policy.get("schedulerMode") or topology.get("schedulerMode") or "").lower()
    if "network" in mode or "netaware" in mode:
        return "localai.benchmark/scheduler-mode=networkaware-scheduler"
    if "load" in mode or "custom" in mode:
        return "localai.benchmark/scheduler-mode=loadaware-scheduler"
    if "default" in mode or scenario.get("family") == "resource-aware-scheduler":
        return "localai.benchmark/scheduler-mode=default-scheduler"
    return requested_selector.strip() if requested_selector is not None else None


def namespace_selector(selector: str | None) -> list[str]:
    if selector is None:
        return []
    text = selector.strip()
    if not text:
        return []
    return ["-l", text]


def pod_app_name(pod: dict[str, Any]) -> str:
    labels = pod.get("metadata", {}).get("labels", {}) or {}
    for key in ("app", "app.kubernetes.io/name", "localai.benchmark/app"):
        value = labels.get(key)
        if value:
            return str(value)
    name = str(pod.get("metadata", {}).get("name") or "")
    for app in sorted(LOCALAI_APPS, key=len, reverse=True):
        if name.startswith(app):
            return app
    return name


def is_localai_pod(pod: dict[str, Any]) -> bool:
    labels = pod.get("metadata", {}).get("labels", {}) or {}
    if labels.get("localai.benchmark/scheduler-mode") in {"default-scheduler", "loadaware-scheduler"}:
        return True
    if pod_app_name(pod) in LOCALAI_APPS:
        return True
    return False


def infer_role(pod: dict[str, Any]) -> str:
    labels = pod.get("metadata", {}).get("labels", {}) or {}
    component = str(labels.get("localai.benchmark/component") or "").strip()
    if component == "server":
        return "server"
    if component in {"rpc-worker", "worker"}:
        return "rpc-worker"
    app = pod_app_name(pod)
    if app == "localai-server":
        return "server"
    if app.startswith("localai-rpc"):
        return "rpc-worker"
    return component or "unknown"


def owner_refs(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref in metadata.get("ownerReferences") or []:
        refs.append(
            {
                "apiVersion": ref.get("apiVersion"),
                "kind": ref.get("kind"),
                "name": ref.get("name"),
                "uid": ref.get("uid"),
                "controller": ref.get("controller"),
            }
        )
    return refs


def build_replicaset_to_deployment(replicasets: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for replicaset in replicasets:
        metadata = replicaset.get("metadata", {}) or {}
        name = str(metadata.get("name") or "")
        uid = str(metadata.get("uid") or "")
        deployment_name: str | None = None
        for ref in metadata.get("ownerReferences") or []:
            if ref.get("kind") == "Deployment" and ref.get("name"):
                deployment_name = str(ref.get("name"))
                break
        if deployment_name:
            if name:
                mapping[name] = deployment_name
            if uid:
                mapping[uid] = deployment_name
    return mapping


def infer_deployment(pod: dict[str, Any], rs_to_deployment: dict[str, str]) -> str | None:
    metadata = pod.get("metadata", {}) or {}
    labels = metadata.get("labels", {}) or {}
    for ref in metadata.get("ownerReferences") or []:
        if ref.get("kind") == "ReplicaSet":
            for key in (str(ref.get("uid") or ""), str(ref.get("name") or "")):
                if key and key in rs_to_deployment:
                    return rs_to_deployment[key]
        if ref.get("kind") == "Deployment" and ref.get("name"):
            return str(ref.get("name"))
    app = labels.get("app") or labels.get("app.kubernetes.io/name")
    if app:
        return str(app)
    name = str(metadata.get("name") or "")
    for app_name in sorted(LOCALAI_APPS, key=len, reverse=True):
        if name.startswith(app_name):
            return app_name
    return None


def container_resources(pod: dict[str, Any], resource_key: str) -> dict[str, Any]:
    resources: dict[str, Any] = {}
    for container in pod.get("spec", {}).get("containers") or []:
        name = str(container.get("name") or "container")
        value = (container.get("resources") or {}).get(resource_key) or {}
        resources[name] = value
    return resources


def restart_count(pod: dict[str, Any]) -> int:
    total = 0
    for status in pod.get("status", {}).get("containerStatuses") or []:
        try:
            total += int(status.get("restartCount") or 0)
        except Exception:
            pass
    return total


def event_timestamp(event: dict[str, Any]) -> str | None:
    for key in ("eventTime", "lastTimestamp", "firstTimestamp", "metadata.creationTimestamp"):
        if key == "metadata.creationTimestamp":
            value = event.get("metadata", {}).get("creationTimestamp")
        else:
            value = event.get(key)
        if value:
            return str(value)
    return None


def simplify_event(event: dict[str, Any]) -> dict[str, Any]:
    involved = event.get("involvedObject") or event.get("regarding") or {}
    return {
        "reason": event.get("reason"),
        "type": event.get("type"),
        "message": event.get("message"),
        "timestamp": event_timestamp(event),
        "count": event.get("count") or event.get("series", {}).get("count"),
        "involvedObject": {
            "kind": involved.get("kind"),
            "namespace": involved.get("namespace"),
            "name": involved.get("name"),
            "uid": involved.get("uid"),
        },
    }


def index_events_by_pod(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        involved = event.get("involvedObject") or event.get("regarding") or {}
        if involved.get("kind") != "Pod":
            continue
        simplified = simplify_event(event)
        name = str(involved.get("name") or "")
        uid = str(involved.get("uid") or "")
        if name:
            by_key[name].append(simplified)
        if uid:
            by_key[uid].append(simplified)
    return by_key


def compact_node_items(nodes_payload: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for node in nodes_payload.get("items") or []:
        metadata = node.get("metadata", {}) or {}
        status = node.get("status", {}) or {}
        labels = metadata.get("labels", {}) or {}
        conditions = status.get("conditions") or []
        ready_condition = next((item for item in conditions if item.get("type") == "Ready"), {})
        nodes.append(
            {
                "name": metadata.get("name"),
                "labels": labels,
                "ready": ready_condition.get("status") == "True",
                "roles": node_roles(labels),
                "capacity": status.get("capacity") or {},
                "allocatable": status.get("allocatable") or {},
            }
        )
    return nodes


def node_roles(labels: dict[str, Any]) -> list[str]:
    roles: list[str] = []
    for key in labels:
        if key.startswith("node-role.kubernetes.io/"):
            role = key.rsplit("/", 1)[-1] or "unknown"
            roles.append(role)
    return sorted(roles)


def collect_namespace_evidence(
    kubectl: str,
    kubeconfig: Path | None,
    scenario: dict[str, Any],
    tenant: TenantContext,
    selector: str | None,
    fallback_app_filter: bool,
) -> tuple[list[PodEvidence], list[dict[str, Any]], list[dict[str, Any]]]:
    scenario_text = scenario_id(scenario, Path(DEFAULT_SCENARIO_CONFIG))
    commands: list[dict[str, Any]] = []

    pod_args = ["get", "pods", "-n", tenant.namespace] + namespace_selector(selector)
    pods_payload, pods_command = run_kubectl_json(kubectl, kubeconfig, pod_args)
    commands.append(pods_command.to_dict())
    if not pods_command.ok:
        return [], [], commands

    pods = list(pods_payload.get("items") or [])
    if fallback_app_filter and not pods:
        fallback_payload, fallback_command = run_kubectl_json(kubectl, kubeconfig, ["get", "pods", "-n", tenant.namespace])
        commands.append(fallback_command.to_dict())
        if fallback_command.ok:
            pods = [pod for pod in fallback_payload.get("items") or [] if is_localai_pod(pod)]

    replicasets_payload, rs_command = run_kubectl_json(kubectl, kubeconfig, ["get", "replicasets", "-n", tenant.namespace])
    commands.append(rs_command.to_dict())
    rs_to_deployment = build_replicaset_to_deployment(replicasets_payload.get("items") or []) if rs_command.ok else {}

    events_payload, events_command = run_kubectl_json(kubectl, kubeconfig, ["get", "events", "-n", tenant.namespace])
    commands.append(events_command.to_dict())
    events = events_payload.get("items") or [] if events_command.ok else []
    event_index = index_events_by_pod(events)

    evidence: list[PodEvidence] = []
    for pod in pods:
        metadata = pod.get("metadata", {}) or {}
        status = pod.get("status", {}) or {}
        spec = pod.get("spec", {}) or {}
        pod_name = str(metadata.get("name") or "")
        pod_uid = str(metadata.get("uid") or "") or None
        matched_events = []
        if pod_name in event_index:
            matched_events.extend(event_index[pod_name])
        if pod_uid and pod_uid in event_index:
            matched_events.extend([item for item in event_index[pod_uid] if item not in matched_events])
        evidence.append(
            PodEvidence(
                scenario_id=scenario_text,
                tenant_id=tenant.tenant_id,
                namespace=tenant.namespace,
                deployment=infer_deployment(pod, rs_to_deployment),
                pod_name=pod_name,
                pod_uid=pod_uid,
                node_name=spec.get("nodeName"),
                pod_phase=status.get("phase"),
                start_time=status.get("startTime"),
                labels=metadata.get("labels") or {},
                annotations=metadata.get("annotations") or {},
                role=infer_role(pod),
                resource_requests=container_resources(pod, "requests"),
                resource_limits=container_resources(pod, "limits"),
                restart_count=restart_count(pod),
                owner_references=owner_refs(metadata),
                events=matched_events,
            )
        )

    return evidence, [simplify_event(event) for event in events if (event.get("reason") in SCHEDULING_EVENT_REASONS)], commands


def latency_enabled(scenario: dict[str, Any]) -> bool:
    alias = str(scenario.get("latencyAlias") or "").upper()
    profile = str(scenario.get("latencyProfileId") or "").upper()
    return bool(alias and alias != "L0") or bool(profile and "L0" not in profile and "NONE" not in profile)


def placement_category_definitions(categories: list[str] | set[str] | None = None) -> dict[str, str]:
    selected = sorted(set(categories or PLACEMENT_CATEGORY_DEFINITIONS.keys()))
    return {
        category: PLACEMENT_CATEGORY_DEFINITIONS.get(category, "No category definition available.")
        for category in selected
    }


def category_risk_level(categories: list[str] | set[str]) -> str:
    if not categories:
        return "info"
    return max((PLACEMENT_CATEGORY_SEVERITY.get(category, "info") for category in categories), key=lambda item: SEVERITY_RANK.get(item, 0))


def normalized_categories(categories: list[str] | set[str]) -> list[str]:
    result = set(categories)
    if len(result) > 1:
        result.discard("default_scheduler_unclassified")
    return sorted(result)


def category_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for item in items:
        for category in item.get("categories") or []:
            counter[str(category)] += 1
    return dict(sorted(counter.items()))


def expected_worker_count_by_tenant(scenario: dict[str, Any]) -> dict[str, int]:
    expected: dict[str, int] = {}
    fallback_count = localai_worker_count_per_tenant_from_scenario(scenario)
    for item in scenario.get("tenantClusters") or []:
        tenant_id = str(item.get("tenantId") or "").strip()
        if not tenant_id:
            continue
        raw = item.get("workerCount")
        if raw is None:
            raw = item.get("localAiWorkerCount")
        if raw is None:
            raw = item.get("resolvedWorkerCount")
        if raw is None:
            raw = fallback_count
        try:
            count = int(raw)
        except Exception:
            continue
        if count >= 0:
            expected[tenant_id] = count
    if not expected and fallback_count is not None:
        for tenant_id in scenario.get("tenantIds") or []:
            expected[str(tenant_id)] = fallback_count
    return expected


def resource_contention_threshold(scenario: dict[str, Any]) -> int:
    policy_sources = [
        scenario.get("placementClassificationPolicy") or {},
        (scenario.get("schedulerEvidence") or {}).get("placementClassificationPolicy") or {},
        scenario.get("defaultSchedulerPolicy") or {},
    ]
    for policy in policy_sources:
        for key in ("resourceContentionPodThreshold", "resourceContentionThreshold", "localAiPodThreshold"):
            raw = policy.get(key)
            if raw is None:
                continue
            try:
                value = int(raw)
            except Exception:
                continue
            if value > 0:
                return value
    return DEFAULT_RESOURCE_CONTENTION_POD_THRESHOLD


def scheduled_localai_role_pods(pods: list[PodEvidence]) -> list[PodEvidence]:
    return [
        pod
        for pod in pods
        if pod.node_name and pod.role in {"server", "rpc-worker"}
    ]


def compact_pod_reference(pod: PodEvidence) -> dict[str, Any]:
    return {
        "tenantId": pod.tenant_id,
        "namespace": pod.namespace,
        "podName": pod.pod_name,
        "deployment": pod.deployment,
        "role": pod.role,
        "nodeName": pod.node_name,
    }


def classification_evidence(category: str, message: str, **details: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "category": category,
        "severity": PLACEMENT_CATEGORY_SEVERITY.get(category, "info"),
        "message": message,
    }
    for key, value in details.items():
        if value is not None:
            payload[key] = value
    return payload


def classify_pods(pods: list[PodEvidence], scenario: dict[str, Any]) -> dict[str, Any]:
    pods_by_tenant: dict[str, list[PodEvidence]] = defaultdict(list)
    pods_by_node: dict[str, list[PodEvidence]] = defaultdict(list)
    for pod in pods:
        pods_by_tenant[pod.tenant_id].append(pod)
        if pod.node_name:
            pods_by_node[pod.node_name].append(pod)

    latency_is_enabled = latency_enabled(scenario)
    contention_threshold = resource_contention_threshold(scenario)
    expected_workers = expected_worker_count_by_tenant(scenario)

    node_role_pods: dict[str, list[PodEvidence]] = {
        node: [pod for pod in node_pods if pod.role in {"server", "rpc-worker"}]
        for node, node_pods in pods_by_node.items()
    }

    shared_nodes = {
        node: sorted({pod.tenant_id for pod in node_pods})
        for node, node_pods in pods_by_node.items()
        if len({pod.tenant_id for pod in node_pods}) > 1
    }

    contention_nodes = {
        node: node_pods
        for node, node_pods in node_role_pods.items()
        if len(node_pods) >= contention_threshold
    }

    node_classifications: list[dict[str, Any]] = []
    node_categories_by_name: dict[str, set[str]] = defaultdict(set)
    node_evidence_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for node, node_pods in sorted(pods_by_node.items()):
        role_pods = [pod for pod in node_pods if pod.role in {"server", "rpc-worker"}]
        tenant_ids = sorted({pod.tenant_id for pod in node_pods})
        categories: set[str] = set()
        evidence: list[dict[str, Any]] = []

        if len(tenant_ids) > 1:
            categories.add("tenant_interference_risk")
            evidence.append(
                classification_evidence(
                    "tenant_interference_risk",
                    "The node hosts LocalAI pods from multiple tenants.",
                    nodeName=node,
                    tenantIds=tenant_ids,
                    pods=[compact_pod_reference(pod) for pod in sorted(node_pods, key=lambda item: (item.tenant_id, item.pod_name))],
                )
            )

        if len(role_pods) >= contention_threshold:
            categories.add("resource_contention_risk")
            evidence.append(
                classification_evidence(
                    "resource_contention_risk",
                    "The node hosts a high number of LocalAI server/RPC worker pods.",
                    nodeName=node,
                    localAiPodCount=len(role_pods),
                    threshold=contention_threshold,
                    pods=[compact_pod_reference(pod) for pod in sorted(role_pods, key=lambda item: (item.tenant_id, item.pod_name))],
                )
            )

        for tenant_id in tenant_ids:
            tenant_node_pods = [pod for pod in node_pods if pod.tenant_id == tenant_id]
            if any(pod.role == "server" for pod in tenant_node_pods) and any(pod.role == "rpc-worker" for pod in tenant_node_pods):
                categories.add("server_worker_colocated")
                evidence.append(
                    classification_evidence(
                        "server_worker_colocated",
                        "The node hosts at least one server and one RPC worker for the same tenant.",
                        nodeName=node,
                        tenantId=tenant_id,
                        pods=[compact_pod_reference(pod) for pod in sorted(tenant_node_pods, key=lambda item: item.pod_name)],
                    )
                )

        if not categories:
            categories.add("default_scheduler_unclassified")

        node_categories_by_name[node].update(categories)
        node_evidence_by_name[node].extend(evidence)
        node_classifications.append(
            {
                "nodeName": node,
                "categories": normalized_categories(categories),
                "riskLevel": category_risk_level(categories),
                "tenantIds": tenant_ids,
                "localAiRolePodCount": len(role_pods),
                "podCount": len(node_pods),
                "evidence": evidence,
            }
        )

    tenant_summaries: list[dict[str, Any]] = []
    tenant_categories_by_id: dict[str, set[str]] = defaultdict(set)
    tenant_evidence_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for tenant_id, tenant_pods in sorted(pods_by_tenant.items()):
        role_pods = [pod for pod in tenant_pods if pod.role in {"server", "rpc-worker"}]
        scheduled_role_pods = scheduled_localai_role_pods(tenant_pods)
        unscheduled_role_pods = [pod for pod in role_pods if not pod.node_name]
        server_pods = [pod for pod in tenant_pods if pod.role == "server"]
        worker_pods = [pod for pod in tenant_pods if pod.role == "rpc-worker"]
        scheduled_servers = [pod for pod in server_pods if pod.node_name]
        scheduled_workers = [pod for pod in worker_pods if pod.node_name]
        server_nodes = sorted({pod.node_name for pod in scheduled_servers if pod.node_name})
        worker_nodes = sorted({pod.node_name for pod in scheduled_workers if pod.node_name})
        active_nodes = sorted({pod.node_name for pod in scheduled_role_pods if pod.node_name})
        expected_worker_count = expected_workers.get(tenant_id)

        categories: set[str] = set()
        evidence: list[dict[str, Any]] = []

        if not server_pods:
            categories.add("missing_server_pod")
            evidence.append(
                classification_evidence(
                    "missing_server_pod",
                    "No LocalAI server pod was observed for this tenant.",
                    tenantId=tenant_id,
                    namespace=tenant_pods[0].namespace if tenant_pods else None,
                )
            )

        if expected_worker_count is not None and len(worker_pods) < expected_worker_count:
            categories.add("missing_worker_pods")
            evidence.append(
                classification_evidence(
                    "missing_worker_pods",
                    "The observed number of LocalAI RPC worker pods is lower than expected.",
                    tenantId=tenant_id,
                    expectedWorkerCount=expected_worker_count,
                    observedWorkerCount=len(worker_pods),
                )
            )

        if unscheduled_role_pods:
            categories.add("unscheduled_pods")
            evidence.append(
                classification_evidence(
                    "unscheduled_pods",
                    "One or more LocalAI server/RPC worker pods do not have an assigned node.",
                    tenantId=tenant_id,
                    pods=[compact_pod_reference(pod) for pod in sorted(unscheduled_role_pods, key=lambda item: item.pod_name)],
                )
            )

        if server_nodes and worker_nodes:
            all_role_nodes = sorted(set(server_nodes).union(worker_nodes))
            worker_nodes_outside_server_nodes = sorted(set(worker_nodes).difference(server_nodes))
            local_worker_nodes = sorted(set(worker_nodes).intersection(server_nodes))

            if len(all_role_nodes) == 1:
                categories.add("server_worker_colocated")
                evidence.append(
                    classification_evidence(
                        "server_worker_colocated",
                        "The tenant server and RPC workers are all scheduled on the same node.",
                        tenantId=tenant_id,
                        nodeName=all_role_nodes[0],
                        serverNodes=server_nodes,
                        workerNodes=worker_nodes,
                    )
                )
            elif worker_nodes_outside_server_nodes:
                categories.add("server_worker_split")
                evidence.append(
                    classification_evidence(
                        "server_worker_split",
                        "At least one tenant RPC worker is scheduled on a node that does not host the tenant server.",
                        tenantId=tenant_id,
                        serverNodes=server_nodes,
                        workerNodes=worker_nodes,
                        remoteWorkerNodes=worker_nodes_outside_server_nodes,
                    )
                )
                if local_worker_nodes:
                    categories.add("server_worker_partially_colocated")
                    evidence.append(
                        classification_evidence(
                            "server_worker_partially_colocated",
                            "Some RPC workers are colocated with the server while others are remote.",
                            tenantId=tenant_id,
                            localWorkerNodes=local_worker_nodes,
                            remoteWorkerNodes=worker_nodes_outside_server_nodes,
                        )
                    )
                if latency_is_enabled:
                    categories.add("latency_sensitive_split")
                    evidence.append(
                        classification_evidence(
                            "latency_sensitive_split",
                            "Latency injection is enabled while server and RPC workers are split across nodes.",
                            tenantId=tenant_id,
                            latencyAlias=scenario.get("latencyAlias"),
                            latencyProfileId=scenario.get("latencyProfileId"),
                            serverNodes=server_nodes,
                            workerNodes=worker_nodes,
                        )
                    )
            elif len(all_role_nodes) > 1:
                categories.add("server_worker_split")
                evidence.append(
                    classification_evidence(
                        "server_worker_split",
                        "The tenant server/worker set spans multiple nodes.",
                        tenantId=tenant_id,
                        serverNodes=server_nodes,
                        workerNodes=worker_nodes,
                    )
                )
                if latency_is_enabled:
                    categories.add("latency_sensitive_split")
                    evidence.append(
                        classification_evidence(
                            "latency_sensitive_split",
                            "Latency injection is enabled while the tenant server/worker set spans multiple nodes.",
                            tenantId=tenant_id,
                            latencyAlias=scenario.get("latencyAlias"),
                            latencyProfileId=scenario.get("latencyProfileId"),
                            serverNodes=server_nodes,
                            workerNodes=worker_nodes,
                        )
                    )

        if len(scheduled_role_pods) > 1:
            scheduled_role_nodes = [pod.node_name for pod in scheduled_role_pods if pod.node_name]
            if len(set(scheduled_role_nodes)) == len(scheduled_role_nodes):
                categories.add("fully_spread")
                evidence.append(
                    classification_evidence(
                        "fully_spread",
                        "The tenant LocalAI server/RPC worker pods are scheduled on distinct nodes.",
                        tenantId=tenant_id,
                        nodes=sorted(set(scheduled_role_nodes)),
                        podCount=len(scheduled_role_pods),
                    )
                )

        tenant_shared_nodes = sorted({pod.node_name for pod in tenant_pods if pod.node_name in shared_nodes})
        if tenant_shared_nodes:
            categories.add("tenant_interference_risk")
            evidence.append(
                classification_evidence(
                    "tenant_interference_risk",
                    "The tenant shares at least one node with other tenants.",
                    tenantId=tenant_id,
                    sharedNodes=[
                        {"nodeName": node, "tenantIds": shared_nodes[node]}
                        for node in tenant_shared_nodes
                    ],
                )
            )

        tenant_contention_nodes = sorted({pod.node_name for pod in tenant_pods if pod.node_name in contention_nodes})
        if tenant_contention_nodes:
            categories.add("resource_contention_risk")
            evidence.append(
                classification_evidence(
                    "resource_contention_risk",
                    "The tenant has pods on nodes with high LocalAI pod density.",
                    tenantId=tenant_id,
                    threshold=contention_threshold,
                    contentionNodes=[
                        {
                            "nodeName": node,
                            "localAiPodCount": len(contention_nodes[node]),
                            "podNames": sorted(pod.pod_name for pod in contention_nodes[node]),
                        }
                        for node in tenant_contention_nodes
                    ],
                )
            )

        if not categories:
            categories.add("default_scheduler_unclassified")

        tenant_categories_by_id[tenant_id].update(categories)
        tenant_evidence_by_id[tenant_id].extend(evidence)
        tenant_summaries.append(
            {
                "tenantId": tenant_id,
                "namespace": tenant_pods[0].namespace if tenant_pods else None,
                "podCount": len(tenant_pods),
                "localAiRolePodCount": len(role_pods),
                "serverPodCount": len(server_pods),
                "rpcWorkerPodCount": len(worker_pods),
                "expectedRpcWorkerCount": expected_worker_count,
                "scheduledLocalAiRolePodCount": len(scheduled_role_pods),
                "unscheduledLocalAiRolePodCount": len(unscheduled_role_pods),
                "serverNodes": server_nodes,
                "workerNodes": worker_nodes,
                "activeNodes": active_nodes,
                "categories": normalized_categories(categories),
                "riskLevel": category_risk_level(categories),
                "evidence": evidence,
            }
        )

    all_categories: set[str] = set()
    all_evidence: list[dict[str, Any]] = []

    for item in tenant_summaries:
        all_categories.update(item.get("categories") or [])
        all_evidence.extend(item.get("evidence") or [])
    for item in node_classifications:
        all_categories.update(item.get("categories") or [])
        all_evidence.extend(item.get("evidence") or [])

    for pod in pods:
        categories: set[str] = set()
        evidence: list[dict[str, Any]] = []
        categories.update(tenant_categories_by_id.get(pod.tenant_id, set()))
        evidence.extend(tenant_evidence_by_id.get(pod.tenant_id, []))
        if pod.node_name:
            categories.update(node_categories_by_name.get(pod.node_name, set()))
            evidence.extend(node_evidence_by_name.get(pod.node_name, []))
        else:
            categories.add("unscheduled_pods")

        scheduling_events = [event for event in pod.events if event.get("reason") in SCHEDULING_EVENT_REASONS]
        if not categories:
            categories.add("default_scheduler_unclassified")

        pod.placement_classification = {
            "schemaVersion": PLACEMENT_CLASSIFICATION_SCHEMA_VERSION,
            "categories": normalized_categories(categories),
            "riskLevel": category_risk_level(categories),
            "nodeName": pod.node_name,
            "tenantId": pod.tenant_id,
            "role": pod.role,
            "scheduled": bool(pod.node_name),
            "schedulingEvents": scheduling_events,
            "evidence": evidence,
        }

    if not all_categories:
        all_categories.add("default_scheduler_unclassified")

    negative_evidence = [
        item for item in all_evidence
        if SEVERITY_RANK.get(str(item.get("severity") or "info"), 0) >= SEVERITY_RANK["warning"]
    ]

    scenario_categories = normalized_categories(all_categories)
    return {
        "schemaVersion": PLACEMENT_CLASSIFICATION_SCHEMA_VERSION,
        "classificationPolicy": {
            "latencyAwareClassificationEnabled": latency_is_enabled,
            "latencyAlias": scenario.get("latencyAlias"),
            "latencyProfileId": scenario.get("latencyProfileId"),
            "resourceContentionPodThreshold": contention_threshold,
            "nodeSharingAcrossTenantsConsideredInterferenceRisk": True,
            "serverWorkerSplitConsideredLatencySensitiveWhenLatencyIsEnabled": True,
        },
        "scenarioCategories": scenario_categories,
        "scenarioRiskLevel": category_risk_level(scenario_categories),
        "categoryDefinitions": placement_category_definitions(scenario_categories),
        "categorySeverity": {
            category: PLACEMENT_CATEGORY_SEVERITY.get(category, "info")
            for category in scenario_categories
        },
        "categoryCounts": {
            "tenant": category_counts(tenant_summaries),
            "node": category_counts(node_classifications),
            "pod": category_counts([pod.placement_classification for pod in pods]),
        },
        "tenantClassifications": tenant_summaries,
        "nodeClassifications": node_classifications,
        "nodeOccupancy": [
            {
                "nodeName": node,
                "podCount": len(node_pods),
                "localAiRolePodCount": len(node_role_pods.get(node, [])),
                "tenantIds": sorted({pod.tenant_id for pod in node_pods}),
                "roles": sorted({pod.role for pod in node_pods}),
                "categories": normalized_categories(node_categories_by_name.get(node, {"default_scheduler_unclassified"})),
                "riskLevel": category_risk_level(node_categories_by_name.get(node, {"default_scheduler_unclassified"})),
                "pods": [
                    {
                        "tenantId": pod.tenant_id,
                        "namespace": pod.namespace,
                        "podName": pod.pod_name,
                        "deployment": pod.deployment,
                        "role": pod.role,
                    }
                    for pod in sorted(node_pods, key=lambda item: (item.tenant_id, item.pod_name))
                ],
            }
            for node, node_pods in sorted(pods_by_node.items())
        ],
        "sharedTenantNodes": [
            {"nodeName": node, "tenantIds": tenant_ids}
            for node, tenant_ids in sorted(shared_nodes.items())
        ],
        "resourceContentionRiskNodes": [
            {
                "nodeName": node,
                "localAiPodCount": len(node_pods),
                "threshold": contention_threshold,
                "podNames": sorted(pod.pod_name for pod in node_pods),
                "tenantIds": sorted({pod.tenant_id for pod in node_pods}),
            }
            for node, node_pods in sorted(contention_nodes.items())
        ],
        "negativeEvidence": negative_evidence,
    }

def scenario_summary(scenario: dict[str, Any], scenario_config: Path) -> dict[str, Any]:
    return {
        "scenarioId": scenario_id(scenario, scenario_config),
        "scenarioConfigPath": str(scenario_config),
        "associatedCycleId": scenario.get("associatedCycleId") or scenario.get("campaignId"),
        "family": scenario.get("family"),
        "scenarioClass": scenario.get("scenarioClass"),
        "workerNodeCount": scenario.get("workerNodeCount"),
        "tenantCount": scenario.get("tenantCount"),
        "latencyAlias": scenario.get("latencyAlias"),
        "latencyProfileId": scenario.get("latencyProfileId"),
        "trafficProfileId": scenario.get("trafficProfileId"),
        "modelMix": scenario.get("modelMix"),
        "workerScenario": scenario.get("workerScenario"),
        "localAiWorkerCountPerTenant": localai_worker_count_per_tenant_from_scenario(scenario),
        "placementScenario": scenario.get("placementScenario"),
        "placementProfileId": scenario.get("placementProfileId"),
    }


def dry_run_payload(repo_root: Path, scenario: dict[str, Any], scenario_config: Path, output_path: Path, tenants: list[TenantContext], selector: str | None) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEDULER_DECISION_EVIDENCE_SCHEMA_VERSION,
        "captureMode": "dry_run",
        "status": "planned",
        "generatedAt": utc_now(),
        "scenario": scenario_summary(scenario, scenario_config),
        "captureConfiguration": {
            "outputPath": str(output_path),
            "tenantNamespaces": [tenant.namespace for tenant in tenants],
            "selector": selector,
            "kubectlExecutionEnabled": False,
        },
        "tenantContexts": [tenant.__dict__ for tenant in tenants],
        "podEvidence": [],
        "placementClassification": {
            "schemaVersion": PLACEMENT_CLASSIFICATION_SCHEMA_VERSION,
            "classificationPolicy": {
                "latencyAwareClassificationEnabled": latency_enabled(scenario),
                "latencyAlias": scenario.get("latencyAlias"),
                "latencyProfileId": scenario.get("latencyProfileId"),
                "resourceContentionPodThreshold": resource_contention_threshold(scenario),
                "nodeSharingAcrossTenantsConsideredInterferenceRisk": True,
                "serverWorkerSplitConsideredLatencySensitiveWhenLatencyIsEnabled": True,
            },
            "scenarioCategories": ["dry_run_no_runtime_placement_available"],
            "scenarioRiskLevel": "info",
            "categoryDefinitions": {
                "dry_run_no_runtime_placement_available": "No runtime pod placement is available because the capture was executed in dry-run mode."
            },
            "categorySeverity": {
                "dry_run_no_runtime_placement_available": "info"
            },
            "categoryCounts": {
                "tenant": {},
                "node": {},
                "pod": {},
            },
            "tenantClassifications": [],
            "nodeClassifications": [],
            "nodeOccupancy": [],
            "negativeEvidence": [],
        },
        "commands": [],
        "errors": [],
    }


def summary_text(payload: dict[str, Any]) -> str:
    lines = [
        "Scheduler decision evidence",
        "===========================",
        f"Scenario: {(payload.get('scenario') or {}).get('scenarioId')}",
        f"Status: {payload.get('status')}",
        f"Generated at: {payload.get('generatedAt')}",
        f"Capture mode: {payload.get('captureMode')}",
        "",
        "Placement categories:",
    ]
    for category in (payload.get("placementClassification") or {}).get("scenarioCategories") or []:
        lines.append(f" - {category}")
    lines.append("")
    lines.append("Pods:")
    for pod in payload.get("podEvidence") or []:
        classes = ",".join((pod.get("placementClassification") or {}).get("categories") or [])
        lines.append(
            " - {tenant}/{namespace}/{pod}: node={node}, deployment={deployment}, role={role}, class={classes}".format(
                tenant=pod.get("tenantId"),
                namespace=pod.get("namespace"),
                pod=pod.get("podName"),
                node=pod.get("nodeName"),
                deployment=pod.get("deployment"),
                role=pod.get("role"),
                classes=classes,
            )
        )
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture runtime scheduler placement decisions for LocalAI tenant workloads.")
    parser.add_argument("--repo-root", default=".", help="Repository root directory.")
    parser.add_argument("--scenario-config", default=DEFAULT_SCENARIO_CONFIG, help="Scenario JSON path.")
    parser.add_argument("--kubeconfig", default="", help="Optional kubeconfig path.")
    parser.add_argument("--kubectl", default="kubectl", help="kubectl executable name or path.")
    parser.add_argument("--output-dir", default="", help="Output directory override.")
    parser.add_argument("--output-name", default="", help="Output JSON file name override.")
    parser.add_argument("--selector", default=DEFAULT_SELECTOR, help="Pod label selector used for runtime evidence capture. Use an empty value to disable it.")
    parser.add_argument("--disable-fallback-app-filter", action="store_true", help="Do not fall back to app-based LocalAI pod filtering when the selector returns no pods.")
    parser.add_argument("--dry-run", action="store_true", help="Write a planned capture artifact without invoking kubectl.")
    parser.add_argument("--write-text-summary", action="store_true", help="Write a human-readable text summary next to the JSON artifact.")
    parser.add_argument("--write-latest-aliases", action="store_true", help="Write latest evidence aliases in the output directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = resolve_repo_root(args.repo_root)
    scenario_config = resolve_path(repo_root, args.scenario_config, DEFAULT_SCENARIO_CONFIG)
    kubeconfig = resolve_path(repo_root, args.kubeconfig) if args.kubeconfig else None

    if not scenario_config.is_file():
        raise SystemExit(f"Scenario config not found: {scenario_config}")
    if kubeconfig is not None and not kubeconfig.is_file():
        raise SystemExit(f"Kubeconfig not found: {kubeconfig}")
    if not args.dry_run and shutil.which(args.kubectl) is None and not Path(args.kubectl).is_file():
        raise SystemExit(f"kubectl is not available: {args.kubectl}")

    scenario = load_json(scenario_config)
    tenants = tenant_contexts_from_scenario(scenario)
    if not tenants:
        raise SystemExit("No tenant namespace could be resolved from the scenario configuration.")

    output_dir = output_dir_from_scenario(repo_root, scenario, scenario_config, args.output_dir or None)
    output_name = args.output_name.strip() or artifact_name_from_scenario(scenario)
    output_path = output_dir / output_name
    text_summary_path = output_path.with_suffix(".txt")
    selector_or_none = selector_from_scenario(scenario, args.selector)

    if args.dry_run:
        payload = dry_run_payload(repo_root, scenario, scenario_config, output_path, tenants, selector_or_none)
        write_json(output_path, payload)
        if args.write_text_summary:
            write_text(text_summary_path, summary_text(payload))
        if args.write_latest_aliases:
            latest_name = latest_artifact_name_from_scenario(scenario, output_name)
            write_json(output_dir / latest_name, payload)
            if args.write_text_summary:
                write_text(output_dir / text_alias_name(latest_name), summary_text(payload))
        print(f"Scheduler decision capture status: {payload['status']}")
        print(f"Evidence JSON: {rel_to_repo(repo_root, output_path)}")
        return 0

    started_at = utc_now()
    commands: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    all_pods: list[PodEvidence] = []
    namespace_events: dict[str, list[dict[str, Any]]] = {}

    nodes_payload, nodes_command = run_kubectl_json(args.kubectl, kubeconfig, ["get", "nodes"])
    commands.append(nodes_command.to_dict())
    nodes = compact_node_items(nodes_payload) if nodes_command.ok else []
    if not nodes_command.ok:
        errors.append({"scope": "nodes", "message": nodes_command.stderr or "Unable to collect node metadata."})

    for tenant in tenants:
        pod_evidence, scheduling_events, namespace_commands = collect_namespace_evidence(
            kubectl=args.kubectl,
            kubeconfig=kubeconfig,
            scenario=scenario,
            tenant=tenant,
            selector=selector_or_none,
            fallback_app_filter=not args.disable_fallback_app_filter,
        )
        commands.extend(namespace_commands)
        all_pods.extend(pod_evidence)
        namespace_events[tenant.namespace] = scheduling_events
        if not any(command.get("success") for command in namespace_commands if " pods " in " ".join(command.get("command") or [])):
            errors.append({"scope": tenant.namespace, "message": "Unable to collect pod evidence for namespace."})

    placement_classification = classify_pods(all_pods, scenario)
    completed_at = utc_now()
    status = "captured" if all_pods else "captured_without_matching_pods"
    if errors and not all_pods:
        status = "failed"

    payload = {
        "schemaVersion": SCHEDULER_DECISION_EVIDENCE_SCHEMA_VERSION,
        "captureMode": "kubectl_runtime_capture",
        "status": status,
        "generatedAt": completed_at,
        "startedAt": started_at,
        "completedAt": completed_at,
        "scenario": scenario_summary(scenario, scenario_config),
        "captureConfiguration": {
            "outputPath": str(output_path),
            "tenantNamespaces": [tenant.namespace for tenant in tenants],
            "selector": selector_or_none,
            "fallbackAppFilterEnabled": not args.disable_fallback_app_filter,
            "kubectlExecutionEnabled": True,
            "kubectl": args.kubectl,
            "kubeconfig": str(kubeconfig) if kubeconfig is not None else None,
        },
        "tenantContexts": [tenant.__dict__ for tenant in tenants],
        "nodeEvidence": nodes,
        "namespaceSchedulingEvents": namespace_events,
        "podEvidence": [pod.to_dict() for pod in sorted(all_pods, key=lambda item: (item.tenant_id, item.namespace, item.pod_name))],
        "placementClassification": placement_classification,
        "summary": {
            "tenantCount": len(tenants),
            "podCount": len(all_pods),
            "scheduledPodCount": len([pod for pod in all_pods if pod.node_name]),
            "unscheduledPodCount": len([pod for pod in all_pods if not pod.node_name]),
            "nodeCountWithLocalAiPods": len({pod.node_name for pod in all_pods if pod.node_name}),
            "scenarioCategories": placement_classification.get("scenarioCategories") or [],
        },
        "commands": commands,
        "errors": errors,
    }

    write_json(output_path, payload)
    if args.write_text_summary:
        write_text(text_summary_path, summary_text(payload))
    if args.write_latest_aliases:
        latest_name = latest_artifact_name_from_scenario(scenario, output_name)
        latest_json = output_dir / latest_name
        write_json(latest_json, payload)
        if args.write_text_summary:
            write_text(output_dir / text_alias_name(latest_name), summary_text(payload))

    print(f"Scheduler decision capture status: {status}")
    print(f"Evidence JSON: {rel_to_repo(repo_root, output_path)}")
    if args.write_text_summary:
        print(f"Evidence text: {rel_to_repo(repo_root, text_summary_path)}")
    return 0 if status in {"captured", "captured_without_matching_pods"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
