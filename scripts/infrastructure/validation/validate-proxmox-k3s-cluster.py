#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


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
    raise RuntimeError("Unable to locate scripts/common/artifact_paths.py")


normalize_artifact_payload_for_output, normalize_artifact_text_for_output = _load_artifact_path_helpers()


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_artifact_payload_for_output(payload, path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = normalize_artifact_text_for_output(content, path)
    path.write_text(content, encoding="utf-8")


def safe_rel(path: Optional[Path], repo_root: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def run_command(args: list[str], allow_failure: bool = False) -> dict[str, Any]:
    completed = subprocess.run(args, text=True, capture_output=True)
    payload = {
        "command": args,
        "exitCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "success": completed.returncode == 0,
    }
    if completed.returncode != 0 and not allow_failure:
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{completed.stderr}")
    return payload


def kubectl_base(kubeconfig: Path) -> list[str]:
    return ["kubectl", "--kubeconfig", str(kubeconfig)]


def kubectl_json(kubeconfig: Path, resource_args: list[str], allow_failure: bool = False) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    result = run_command(kubectl_base(kubeconfig) + resource_args + ["-o", "json"], allow_failure=allow_failure)
    if not result["success"]:
        return None, result
    try:
        return json.loads(result["stdout"]), result
    except json.JSONDecodeError as exc:
        if allow_failure:
            result["jsonParseError"] = str(exc)
            return None, result
        raise


def parse_label_selector(selector: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for chunk in selector.split(","):
        text = chunk.strip()
        if not text:
            continue
        if "=" not in text:
            continue
        key, value = text.split("=", 1)
        labels[key.strip()] = value.strip()
    return labels


def taint_to_string(taint: dict[str, Any]) -> str:
    key = str(taint.get("key") or "").strip()
    value = str(taint.get("value") or "").strip()
    effect = str(taint.get("effect") or "").strip()
    key_value = f"{key}={value}" if value else key
    return f"{key_value}:{effect}" if effect else key_value


def parse_taint_requirement(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {
            "key": str(raw.get("key") or "").strip(),
            "value": str(raw.get("value") or "").strip(),
            "effect": str(raw.get("effect") or "").strip(),
        }
    text = str(raw or "").strip()
    effect = ""
    if ":" in text:
        text, effect = text.rsplit(":", 1)
    key = text
    value = ""
    if "=" in text:
        key, value = text.split("=", 1)
    return {"key": key.strip(), "value": value.strip(), "effect": effect.strip()}


def taint_matches_requirement(taint: dict[str, Any], requirement: dict[str, str]) -> bool:
    if requirement.get("key") and str(taint.get("key") or "") != requirement["key"]:
        return False
    if requirement.get("value") and str(taint.get("value") or "") != requirement["value"]:
        return False
    if requirement.get("effect") and str(taint.get("effect") or "") != requirement["effect"]:
        return False
    return True


def node_has_required_taint(node: dict[str, Any], requirement: dict[str, str]) -> bool:
    for taint in node.get("spec", {}).get("taints", []) or []:
        if taint_matches_requirement(taint, requirement):
            return True
    return False


def node_ready(node: dict[str, Any]) -> bool:
    for condition in node.get("status", {}).get("conditions", []):
        if condition.get("type") == "Ready":
            return condition.get("status") == "True"
    return False


def pod_ready(pod: dict[str, Any]) -> bool:
    if pod.get("status", {}).get("phase") != "Running":
        return False
    statuses = pod.get("status", {}).get("containerStatuses", [])
    if not statuses:
        return False
    return all(bool(status.get("ready")) for status in statuses)


def required_kube_system_prefixes_ready(pods_json: dict[str, Any] | None, prefixes: list[str]) -> bool:
    pods = pods_json.get("items", []) if pods_json else []
    for prefix in prefixes:
        candidates = [pod for pod in pods if pod.get("metadata", {}).get("name", "").startswith(prefix)]
        if not any(pod_ready(pod) for pod in candidates):
            return False
    return True


def metrics_commands_succeeded(top_nodes_cmd: dict[str, Any], top_pods_cmd: dict[str, Any]) -> bool:
    return bool(top_nodes_cmd.get("success") and top_pods_cmd.get("success"))


def collect_kube_system_state_with_retry(kubeconfig: Path, profile: dict[str, Any]) -> dict[str, Any]:
    kube_system = profile.get("kubeSystemChecks") or {}
    namespace = kube_system.get("namespace", "kube-system")
    prefixes = list(kube_system.get("requiredRunningPodNamePrefixes", []) or [])
    require_metrics = bool(kube_system.get("requireMetricsApi", True))
    timeout_seconds = int(kube_system.get("readinessWaitSeconds", kube_system.get("metricsReadinessWaitSeconds", 180)) or 0)
    interval_seconds = max(1, int(kube_system.get("readinessPollIntervalSeconds", kube_system.get("metricsReadinessPollIntervalSeconds", 10)) or 10))
    deadline = time.monotonic() + max(0, timeout_seconds)
    attempts: list[dict[str, Any]] = []

    while True:
        pods_json, pods_cmd = kubectl_json(kubeconfig, ["get", "pods", "-n", namespace], allow_failure=True)
        top_nodes_cmd = run_command(kubectl_base(kubeconfig) + ["top", "nodes"], allow_failure=True)
        top_pods_cmd = run_command(kubectl_base(kubeconfig) + ["top", "pods", "-n", namespace], allow_failure=True)
        prefixes_ready = required_kube_system_prefixes_ready(pods_json, prefixes)
        metrics_ready = metrics_commands_succeeded(top_nodes_cmd, top_pods_cmd)
        attempts.append({
            "attempt": len(attempts) + 1,
            "timestampUtc": utc_now_iso(),
            "requiredPrefixesReady": prefixes_ready,
            "metricsApiReady": metrics_ready,
            "topNodesExitCode": top_nodes_cmd.get("exitCode"),
            "topPodsExitCode": top_pods_cmd.get("exitCode"),
            "kubeSystemPodsExitCode": pods_cmd.get("exitCode"),
        })
        if prefixes_ready and (metrics_ready or not require_metrics):
            return {
                "podsJson": pods_json,
                "podsCommand": pods_cmd,
                "topNodesCommand": top_nodes_cmd,
                "topPodsCommand": top_pods_cmd,
                "attempts": attempts,
                "timedOut": False,
            }
        if time.monotonic() >= deadline:
            return {
                "podsJson": pods_json,
                "podsCommand": pods_cmd,
                "topNodesCommand": top_nodes_cmd,
                "topPodsCommand": top_pods_cmd,
                "attempts": attempts,
                "timedOut": True,
            }
        time.sleep(interval_seconds)


def is_control_plane_node(node: dict[str, Any]) -> bool:
    labels = node.get("metadata", {}).get("labels", {})
    return any(
        key in labels
        for key in (
            "node-role.kubernetes.io/control-plane",
            "node-role.kubernetes.io/master",
        )
    )


def node_summary(node: dict[str, Any]) -> dict[str, Any]:
    metadata = node.get("metadata", {})
    status = node.get("status", {})
    addresses = status.get("addresses", [])
    labels = metadata.get("labels", {})
    return {
        "name": metadata.get("name", ""),
        "ready": node_ready(node),
        "isControlPlane": is_control_plane_node(node),
        "labels": labels,
        "taints": [taint_to_string(taint) for taint in node.get("spec", {}).get("taints", []) or []],
        "kubeletVersion": status.get("nodeInfo", {}).get("kubeletVersion", ""),
        "internalIP": next((addr.get("address") for addr in addresses if addr.get("type") == "InternalIP"), None),
        "capacity": status.get("capacity", {}),
        "allocatable": status.get("allocatable", {}),
    }


def add_check(checks: list[dict[str, Any]], name: str, success: bool, details: Any, severity: str = "error") -> None:
    checks.append({"name": name, "success": bool(success), "severity": severity, "details": details})


def latest_alias(source: Path, alias: Path) -> None:
    alias.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, alias)


def build_dry_run_payload(validation_id: str, profile: dict[str, Any], profile_path: Path, kubeconfig: Path, repo_root: Path) -> dict[str, Any]:
    return {
        "schemaVersion": "proxmox-k3s-cluster-validation-result/v1",
        "validationId": validation_id,
        "generatedAtUtc": utc_now_iso(),
        "status": "dry_run",
        "profileId": profile.get("profileId"),
        "profileConfigPath": safe_rel(profile_path, repo_root),
        "kubeconfigPath": safe_rel(kubeconfig, repo_root),
        "expectedCluster": profile.get("expectedCluster", {}),
        "observedCluster": {"nodes": [], "kubeSystemPods": [], "managementNodes": []},
        "checks": [
            {
                "name": "dry_run_only",
                "success": True,
                "severity": "info",
                "details": "No kubectl command was executed. The validation plan was rendered only.",
            }
        ],
        "summary": {
            "totalChecks": 1,
            "failedChecks": [],
            "warningChecks": [],
        },
        "rawCommands": {},
        "decision": {
            "canProceedToApplicationDeployment": False,
            "reason": "dry_run_does_not_validate_cluster_runtime_state",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a proxmox-k3s generated K3s cluster before running LocalAI benchmarks.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--profile-config", default="config/provisioning-validation/profiles/PV_C1_PROVIDER_BACKED_BASELINE.json", help="Provisioning validation profile JSON path.")
    parser.add_argument("--kubeconfig", default="", help="Kubeconfig path. If omitted, the profile recommended kubeconfig path is used.")
    parser.add_argument("--output-root", default="", help="Output root for validation artifacts.")
    parser.add_argument("--validation-id", default="", help="Validation identifier. If omitted, a timestamped ID is generated.")
    parser.add_argument("--allow-metrics-warning", action="store_true", help="Downgrade Metrics API failure to warning even if the profile requires metrics.")
    parser.add_argument("--dry-run", action="store_true", help="Render validation plan and artifacts without executing kubectl.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    profile_path = (repo_root / args.profile_config).resolve() if not Path(args.profile_config).is_absolute() else Path(args.profile_config).resolve()
    profile = load_json(profile_path)

    kubeconfig = Path(args.kubeconfig) if args.kubeconfig else repo_root / profile["provisioning"]["recommendedKubeconfigPath"]
    kubeconfig = kubeconfig.resolve()
    output_root = Path(args.output_root) if args.output_root else repo_root / profile["output"]["defaultOutputRoot"]
    output_root = output_root.resolve()
    validation_id = args.validation_id or f"proxmox-k3s_validation_{utc_now_compact()}"

    if args.dry_run:
        payload = build_dry_run_payload(validation_id, profile, profile_path, kubeconfig, repo_root)
        return write_outputs_and_return(profile, payload, output_root, validation_id, repo_root)

    checks: list[dict[str, Any]] = []
    raw_commands: dict[str, Any] = {}

    kubectl_path = shutil.which("kubectl")
    add_check(checks, "kubectl_available", kubectl_path is not None, {"command": "kubectl", "resolvedPath": kubectl_path})
    add_check(checks, "kubeconfig_exists", kubeconfig.exists(), {"path": str(kubeconfig)})
    add_check(checks, "kubeconfig_non_empty", kubeconfig.exists() and kubeconfig.stat().st_size > 0, {"path": str(kubeconfig), "sizeBytes": kubeconfig.stat().st_size if kubeconfig.exists() else 0})

    if kubectl_path is None or not kubeconfig.exists() or kubeconfig.stat().st_size == 0:
        failed = [check for check in checks if not check["success"] and check.get("severity") != "warning"]
        payload = {
            "schemaVersion": "proxmox-k3s-cluster-validation-result/v1",
            "validationId": validation_id,
            "generatedAtUtc": utc_now_iso(),
            "status": "failed",
            "profileId": profile.get("profileId"),
            "profileConfigPath": safe_rel(profile_path, repo_root),
            "kubeconfigPath": str(kubeconfig),
            "expectedCluster": profile.get("expectedCluster", {}),
            "observedCluster": {"nodes": [], "kubeSystemPods": []},
            "checks": checks,
            "summary": {
                "totalChecks": len(checks),
                "failedChecks": [check["name"] for check in failed],
                "warningChecks": [],
            },
            "rawCommands": raw_commands,
            "decision": {
                "canProceedToApplicationDeployment": False,
                "reason": "kubectl_or_kubeconfig_unavailable",
            },
        }
        return write_outputs_and_return(profile, payload, output_root, validation_id, repo_root)

    nodes_json, nodes_cmd = kubectl_json(kubeconfig, ["get", "nodes"], allow_failure=True)
    raw_commands["getNodes"] = nodes_cmd
    kube_system_state = collect_kube_system_state_with_retry(kubeconfig, profile)
    pods_json = kube_system_state["podsJson"]
    pods_cmd = kube_system_state["podsCommand"]
    raw_commands["getKubeSystemPods"] = pods_cmd
    raw_commands["kubeSystemReadinessAttempts"] = kube_system_state["attempts"]
    raw_commands["kubeSystemReadinessTimedOut"] = kube_system_state["timedOut"]
    namespaces_json, namespaces_cmd = kubectl_json(kubeconfig, ["get", "namespace", profile["kubeSystemChecks"]["namespace"]], allow_failure=True)
    raw_commands["getKubeSystemNamespace"] = namespaces_cmd
    storage_json, storage_cmd = kubectl_json(kubeconfig, ["get", "storageclass"], allow_failure=True)
    raw_commands["getStorageClass"] = storage_cmd
    top_nodes_cmd = kube_system_state["topNodesCommand"]
    raw_commands["topNodes"] = top_nodes_cmd
    top_pods_cmd = kube_system_state["topPodsCommand"]
    raw_commands["topKubeSystemPods"] = top_pods_cmd
    events_json, events_cmd = kubectl_json(kubeconfig, ["get", "events", "-A"], allow_failure=True)
    raw_commands["getEvents"] = events_cmd

    nodes = nodes_json.get("items", []) if nodes_json else []
    node_by_name = {node.get("metadata", {}).get("name", ""): node for node in nodes}
    ready_nodes = [name for name, node in node_by_name.items() if node_ready(node)]

    expected_cp = profile["expectedCluster"].get("expectedControlPlaneNodes", [])
    expected_workers = profile["expectedCluster"].get("expectedWorkerNodes", [])
    expected_all = expected_cp + expected_workers
    missing_nodes = [name for name in expected_all if name not in node_by_name]
    not_ready_nodes = [name for name in expected_all if name in node_by_name and not node_ready(node_by_name[name])]

    add_check(checks, "api_server_reachable", nodes_json is not None, {"exitCode": nodes_cmd["exitCode"], "stderr": nodes_cmd.get("stderr", "")})
    add_check(checks, "expected_nodes_present", not missing_nodes, {"expectedNodes": expected_all, "missingNodes": missing_nodes, "observedNodes": sorted(node_by_name.keys())})
    add_check(checks, "expected_nodes_ready", not not_ready_nodes, {"notReadyNodes": not_ready_nodes, "readyNodes": sorted(ready_nodes)})
    add_check(checks, "minimum_ready_nodes", len(ready_nodes) >= int(profile["expectedCluster"].get("minimumReadyNodes", 0)), {"readyNodeCount": len(ready_nodes), "minimumReadyNodes": profile["expectedCluster"].get("minimumReadyNodes")})

    control_plane_role_failures = []
    for name in expected_cp:
        node = node_by_name.get(name)
        if node and not is_control_plane_node(node):
            control_plane_role_failures.append(name)
    add_check(checks, "expected_control_plane_roles", not control_plane_role_failures, {"controlPlaneNodesWithoutRoleLabel": control_plane_role_failures})

    worker_role_failures = []
    for name in expected_workers:
        node = node_by_name.get(name)
        if node and is_control_plane_node(node):
            worker_role_failures.append(name)
    add_check(checks, "expected_workers_not_control_plane", not worker_role_failures, {"workerNodesWithControlPlaneRole": worker_role_failures})

    if profile["expectedCluster"].get("requireK3sDistribution", False):
        non_k3s = []
        for name, node in node_by_name.items():
            version = node.get("status", {}).get("nodeInfo", {}).get("kubeletVersion", "")
            if "+k3s" not in version:
                non_k3s.append({"node": name, "kubeletVersion": version})
        add_check(checks, "k3s_distribution", not non_k3s, {"nonK3sNodes": non_k3s})

    selector = profile["expectedCluster"].get("expectedWorkerLabelSelector", "")
    selector_labels = parse_label_selector(selector)
    worker_label_failures = []
    for name in expected_workers:
        node = node_by_name.get(name)
        if not node:
            continue
        labels = node.get("metadata", {}).get("labels", {})
        missing = {k: v for k, v in selector_labels.items() if labels.get(k) != v}
        if missing:
            worker_label_failures.append({"node": name, "missingOrMismatchedLabels": missing})
    add_check(checks, "expected_worker_labels", not worker_label_failures, {"selector": selector, "failures": worker_label_failures})

    expected_management_nodes = list(profile["expectedCluster"].get("expectedManagementNodes", []) or [])
    management_selector = str(profile["expectedCluster"].get("expectedManagementLabelSelector") or "").strip()
    management_selector_labels = parse_label_selector(management_selector)
    expected_management_taints = list(profile["expectedCluster"].get("expectedManagementTaints", []) or [])
    management_node_failures: list[dict[str, Any]] = []
    management_label_failures: list[dict[str, Any]] = []
    management_taint_failures: list[dict[str, Any]] = []

    if expected_management_nodes:
        for name in expected_management_nodes:
            node = node_by_name.get(str(name))
            if not node:
                management_node_failures.append({"node": name, "reason": "missing"})
                continue
            labels = node.get("metadata", {}).get("labels", {})
            missing_labels = {k: v for k, v in management_selector_labels.items() if labels.get(k) != v}
            if missing_labels:
                management_label_failures.append({"node": name, "missingOrMismatchedLabels": missing_labels})
            missing_taints = []
            for raw_taint in expected_management_taints:
                requirement = parse_taint_requirement(raw_taint)
                if not node_has_required_taint(node, requirement):
                    missing_taints.append(raw_taint)
            if missing_taints:
                management_taint_failures.append({
                    "node": name,
                    "missingTaints": missing_taints,
                    "observedTaints": [taint_to_string(taint) for taint in node.get("spec", {}).get("taints", []) or []],
                })

    add_check(
        checks,
        "expected_management_nodes_present",
        not management_node_failures,
        {"expectedManagementNodes": expected_management_nodes, "failures": management_node_failures},
        severity="error" if expected_management_nodes else "warning",
    )
    add_check(
        checks,
        "expected_management_labels",
        not management_label_failures,
        {"selector": management_selector, "failures": management_label_failures},
        severity="error" if expected_management_nodes and management_selector else "warning",
    )
    add_check(
        checks,
        "expected_management_taints",
        not management_taint_failures,
        {"expectedTaints": expected_management_taints, "failures": management_taint_failures},
        severity="error" if expected_management_nodes and expected_management_taints else "warning",
    )

    pods = pods_json.get("items", []) if pods_json else []
    pod_names = [pod.get("metadata", {}).get("name", "") for pod in pods]
    add_check(checks, "kube_system_namespace_reachable", namespaces_json is not None, {"exitCode": namespaces_cmd["exitCode"], "stderr": namespaces_cmd.get("stderr", "")})
    add_check(checks, "kube_system_pods_api_reachable", pods_json is not None, {"exitCode": pods_cmd["exitCode"], "stderr": pods_cmd.get("stderr", "")})
    for prefix in profile["kubeSystemChecks"].get("requiredRunningPodNamePrefixes", []):
        candidates = [pod for pod in pods if pod.get("metadata", {}).get("name", "").startswith(prefix)]
        running_ready = [pod.get("metadata", {}).get("name", "") for pod in candidates if pod_ready(pod)]
        add_check(checks, f"kube_system_{prefix}_ready", bool(running_ready), {"prefix": prefix, "matchingPods": [pod.get("metadata", {}).get("name", "") for pod in candidates], "runningReadyPods": running_ready})

    storage_classes = storage_json.get("items", []) if storage_json else []
    add_check(checks, "storageclass_available", bool(storage_classes) if profile["kubeSystemChecks"].get("requireStorageClass", True) else True, {"storageClasses": [item.get("metadata", {}).get("name", "") for item in storage_classes], "apiReachable": storage_json is not None})

    metrics_required = profile["kubeSystemChecks"].get("requireMetricsApi", True)
    metrics_success = top_nodes_cmd["success"] and top_pods_cmd["success"]
    severity = "warning" if args.allow_metrics_warning or profile["kubeSystemChecks"].get("allowMetricsApiWarning", False) else "error"
    add_check(checks, "metrics_api_available", metrics_success or (severity == "warning"), {"topNodesExitCode": top_nodes_cmd["exitCode"], "topPodsExitCode": top_pods_cmd["exitCode"], "topNodesStdout": top_nodes_cmd.get("stdout", ""), "topPodsStdout": top_pods_cmd.get("stdout", ""), "topNodesStderr": top_nodes_cmd.get("stderr", ""), "topPodsStderr": top_pods_cmd.get("stderr", "")}, severity=severity if metrics_required else "warning")

    add_check(checks, "node_resource_inventory_captured", nodes_json is not None, {"nodeCount": len(nodes), "capturedFields": ["capacity", "allocatable", "labels", "kubeletVersion"]}, severity="warning")
    add_check(checks, "cluster_events_captured", events_json is not None, {"eventCount": len(events_json.get("items", [])) if events_json else 0, "apiReachable": events_json is not None}, severity="warning")

    failed = [check for check in checks if not check["success"] and check.get("severity") != "warning"]
    warnings = [check for check in checks if not check["success"] and check.get("severity") == "warning"]
    status = "validated" if not failed and not warnings else "validated_with_warnings" if not failed else "failed"

    accepted_for_app = profile.get("decisionPolicy", {}).get("acceptedStatusesBeforeApplicationDeployment") or profile.get("decisionPolicy", {}).get("blockApplicationDeploymentUnlessStatusIn") or ["validated"]

    payload = {
        "schemaVersion": "proxmox-k3s-cluster-validation-result/v1",
        "validationId": validation_id,
        "generatedAtUtc": utc_now_iso(),
        "status": status,
        "profileId": profile.get("profileId"),
        "profileRole": profile.get("profileRole"),
        "profileConfigPath": safe_rel(profile_path, repo_root),
        "kubeconfigPath": str(kubeconfig),
        "expectedCluster": profile.get("expectedCluster", {}),
        "observedCluster": {
            "nodes": [node_summary(node) for node in nodes],
            "readyNodes": sorted(ready_nodes),
            "managementNodes": [str(name) for name in profile["expectedCluster"].get("expectedManagementNodes", []) or []],
            "kubeSystemPods": pod_names,
            "storageClasses": [item.get("metadata", {}).get("name", "") for item in storage_classes],
            "eventsCaptured": len(events_json.get("items", [])) if events_json else 0,
        },
        "checks": checks,
        "summary": {
            "totalChecks": len(checks),
            "failedChecks": [check["name"] for check in failed],
            "warningChecks": [check["name"] for check in warnings],
        },
        "rawCommands": raw_commands,
        "decision": {
            "canProceedToApplicationDeployment": status in accepted_for_app,
            "acceptedStatusesBeforeApplicationDeployment": accepted_for_app,
            "reason": "cluster_validated" if status in accepted_for_app else "cluster_validation_did_not_meet_required_status",
        },
    }

    return write_outputs_and_return(profile, payload, output_root, validation_id, repo_root)


def write_outputs_and_return(profile: dict[str, Any], payload: dict[str, Any], output_root: Path, validation_id: str, repo_root: Path) -> int:
    output_json = output_root / f"{validation_id}_validation.json"
    output_txt = output_root / f"{validation_id}_validation.txt"
    output_md = output_root / f"{validation_id}_validation.md"

    write_json(output_json, payload)
    write_text(output_txt, render_text(payload))
    write_text(output_md, render_markdown(payload))

    if profile.get("output", {}).get("writeLatestAliases", True):
        latest_json = profile.get("output", {}).get("latestJsonPath")
        latest_text = profile.get("output", {}).get("latestTextPath")
        latest_md = profile.get("output", {}).get("latestMarkdownPath")
        if latest_json:
            latest_alias(output_json, repo_root / latest_json)
        else:
            latest_alias(output_json, output_root / "latest-validation.json")
        if latest_text:
            latest_alias(output_txt, repo_root / latest_text)
        else:
            latest_alias(output_txt, output_root / "latest-validation.txt")
        if latest_md:
            latest_alias(output_md, repo_root / latest_md)
        else:
            latest_alias(output_md, output_root / "latest-validation.md")

    print(f"Validation status: {payload.get('status')}")
    print(f"JSON output      : {output_json}")
    print(f"Text output      : {output_txt}")
    print(f"Markdown output  : {output_md}")

    if payload.get("status") == "failed":
        return 1
    return 0


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        "Proxmox K3s Cluster Validation",
        "==============================",
        f"Validation ID : {payload.get('validationId')}",
        f"Generated UTC : {payload.get('generatedAtUtc')}",
        f"Status        : {payload.get('status')}",
        f"Profile       : {payload.get('profileConfigPath')}",
        f"Kubeconfig    : {payload.get('kubeconfigPath')}",
        "",
        "Decision",
        "--------",
        f"Can proceed to application deployment : {payload.get('decision', {}).get('canProceedToApplicationDeployment')}",
        f"Reason                                : {payload.get('decision', {}).get('reason')}",
        "",
        "Summary",
        "-------",
        f"Total checks  : {payload.get('summary', {}).get('totalChecks')}",
        f"Failed checks : {', '.join(payload.get('summary', {}).get('failedChecks', [])) or 'none'}",
        f"Warnings      : {', '.join(payload.get('summary', {}).get('warningChecks', [])) or 'none'}",
        "",
        "Checks",
        "------",
    ]
    for check in payload.get("checks", []):
        marker = "PASS" if check.get("success") else "WARN" if check.get("severity") == "warning" else "FAIL"
        lines.append(f"[{marker}] {check.get('name')}")
    lines.extend(["", "Observed nodes", "--------------"])
    for node in payload.get("observedCluster", {}).get("nodes", []):
        lines.append(f"- {node.get('name')} | Ready={node.get('ready')} | ControlPlane={node.get('isControlPlane')} | Version={node.get('kubeletVersion')} | InternalIP={node.get('internalIP')}")
        alloc = node.get("allocatable", {})
        if alloc:
            lines.append(f"  Allocatable: cpu={alloc.get('cpu')} memory={alloc.get('memory')} pods={alloc.get('pods')}")
        if node.get("taints"):
            lines.append(f"  Taints: {', '.join(node.get('taints') or [])}")
    lines.append("")
    return "\n".join(lines)


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Proxmox K3s Cluster Validation",
        "",
        f"- **Validation ID:** `{payload.get('validationId')}`",
        f"- **Generated UTC:** `{payload.get('generatedAtUtc')}`",
        f"- **Status:** `{payload.get('status')}`",
        f"- **Profile:** `{payload.get('profileConfigPath')}`",
        f"- **Kubeconfig:** `{payload.get('kubeconfigPath')}`",
        "",
        "## Decision",
        "",
        f"- **Can proceed to application deployment:** `{payload.get('decision', {}).get('canProceedToApplicationDeployment')}`",
        f"- **Reason:** `{payload.get('decision', {}).get('reason')}`",
        "",
        "## Summary",
        "",
        f"- **Total checks:** `{payload.get('summary', {}).get('totalChecks')}`",
        f"- **Failed checks:** `{', '.join(payload.get('summary', {}).get('failedChecks', [])) or 'none'}`",
        f"- **Warnings:** `{', '.join(payload.get('summary', {}).get('warningChecks', [])) or 'none'}`",
        "",
        "## Checks",
        "",
        "| Status | Check | Severity |",
        "|---|---|---|",
    ]
    for check in payload.get("checks", []):
        marker = "PASS" if check.get("success") else "WARN" if check.get("severity") == "warning" else "FAIL"
        lines.append(f"| {marker} | `{check.get('name')}` | `{check.get('severity')}` |")
    lines.extend(["", "## Observed nodes", "", "| Node | Ready | Control Plane | Kubelet | Internal IP | Taints |", "|---|---:|---:|---|---|---|"])
    for node in payload.get("observedCluster", {}).get("nodes", []):
        taints = ", ".join(node.get("taints") or []) or "none"
        lines.append(f"| `{node.get('name')}` | `{node.get('ready')}` | `{node.get('isControlPlane')}` | `{node.get('kubeletVersion')}` | `{node.get('internalIP')}` | `{taints}` |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
