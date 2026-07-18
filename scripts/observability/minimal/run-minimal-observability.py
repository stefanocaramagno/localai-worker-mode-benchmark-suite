#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
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
    raise RuntimeError("Unable to locate scripts/common/artifact_paths.py")


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


def load_cycle(repo_root: Path, cycle_config: str) -> Tuple[Path, Dict[str, Any]]:
    cycle_path = repo_path(repo_root, cycle_config)
    if cycle_path is None or not cycle_path.exists():
        raise FileNotFoundError(f"Experimental cycle profile not found: {cycle_config}")
    return cycle_path, read_json(cycle_path)


def resolve_observability_profile(repo_root: Path, cycle: Dict[str, Any], explicit_profile: Optional[str]) -> Tuple[Path, Dict[str, Any]]:
    profile_value = (
        explicit_profile
        or cycle.get("pipelineProfiles", {}).get("minimalObservability")
        or cycle.get("minimalObservability", {}).get("minimalObservabilityProfilePath")
        or cycle.get("providerBackedInfrastructure", {}).get("minimalObservabilityProfilePath")
    )
    if not profile_value:
        raise ValueError("Minimal observability profile path is not declared in the cycle profile and was not provided explicitly.")
    profile_path = repo_path(repo_root, profile_value)
    if profile_path is None or not profile_path.exists():
        raise FileNotFoundError(f"Minimal observability profile not found: {profile_value}")
    return profile_path, read_json(profile_path)


def resolve_kubeconfig(repo_root: Path, profile: Dict[str, Any], explicit_kubeconfig: Optional[str]) -> Optional[Path]:
    kubeconfig = explicit_kubeconfig or profile.get("kubeconfigPath")
    return repo_path(repo_root, kubeconfig)


def run_command(command: List[str], timeout: Optional[int] = None) -> Dict[str, Any]:
    started_at = utc_now()
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
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


def kubectl_base(kubectl: str, kubeconfig: Optional[Path]) -> List[str]:
    cmd = [kubectl]
    if kubeconfig is not None:
        cmd.extend(["--kubeconfig", str(kubeconfig)])
    return cmd


def replace_namespace(args: List[str], namespace: str) -> List[str]:
    return [item.replace("{namespace}", namespace) for item in args]


def safe_namespace_token(namespace: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", namespace.strip()) or "namespace"


def ordered_unique_strings(values: List[Any]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def resolve_collection_namespaces(profile: Dict[str, Any], explicit_namespace: Optional[str]) -> Tuple[str, List[str], List[str]]:
    primary = explicit_namespace or profile.get("namespace") or "default"
    if explicit_namespace:
        namespaces = [primary]
    else:
        namespaces = ordered_unique_strings([primary] + list(profile.get("namespaces") or []) + list(profile.get("additionalNamespaces") or []))
    if primary not in namespaces:
        namespaces.insert(0, primary)
    additional = [namespace for namespace in namespaces if namespace != primary]
    return primary, namespaces, additional


def namespace_command_has_placeholder(args: List[str]) -> bool:
    return any("{namespace}" in str(item) for item in args)


def parse_cpu_to_millicores(value: str) -> Optional[float]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("n"):
            return float(text[:-1]) / 1_000_000.0
        if text.endswith("u"):
            return float(text[:-1]) / 1_000.0
        if text.endswith("m"):
            return float(text[:-1])
        return float(text) * 1000.0
    except Exception:
        return None


def parse_memory_to_mib(value: str) -> Optional[float]:
    text = (value or "").strip()
    if not text:
        return None
    units = {
        "Ki": 1.0 / 1024.0,
        "Mi": 1.0,
        "Gi": 1024.0,
        "Ti": 1024.0 * 1024.0,
        "K": 1.0 / 1000.0,
        "M": 1000.0 / 1024.0,
        "G": 1000.0 * 1000.0 / 1024.0,
        "T": 1000.0 * 1000.0 * 1000.0 / 1024.0,
    }
    match = re.match(r"^([0-9.]+)([A-Za-z]+)?$", text)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2) or ""
    if unit in units:
        return number * units[unit]
    return number / (1024.0 * 1024.0)


def parse_percent(value: str) -> Optional[float]:
    text = (value or "").strip().rstrip("%")
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def parse_top_nodes(text: str) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        rows.append({
            "nodeName": parts[0],
            "cpuMillicores": parse_cpu_to_millicores(parts[1]),
            "cpuPercent": parse_percent(parts[2]),
            "memoryMiB": parse_memory_to_mib(parts[3]),
            "memoryPercent": parse_percent(parts[4]),
        })
    return {
        "rows": rows,
        "maxNodeCpuPercent": max([row["cpuPercent"] for row in rows if row["cpuPercent"] is not None], default=None),
        "maxNodeMemoryPercent": max([row["memoryPercent"] for row in rows if row["memoryPercent"] is not None], default=None),
    }


def parse_top_pods(text: str) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        rows.append({
            "podName": parts[0],
            "cpuMillicores": parse_cpu_to_millicores(parts[1]),
            "memoryMiB": parse_memory_to_mib(parts[2]),
        })
    return {
        "rows": rows,
        "maxPodCpuMillicores": max([row["cpuMillicores"] for row in rows if row["cpuMillicores"] is not None], default=None),
        "maxPodMemoryMiB": max([row["memoryMiB"] for row in rows if row["memoryMiB"] is not None], default=None),
    }


def parse_nodes_json(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"nodes": [], "nodeCount": 0}
    nodes = []
    for item in payload.get("items", []) or []:
        meta = item.get("metadata", {}) or {}
        status = item.get("status", {}) or {}
        labels = meta.get("labels", {}) or {}
        conditions = status.get("conditions", []) or []
        ready_condition = next((cond for cond in conditions if cond.get("type") == "Ready"), {})
        nodes.append({
            "nodeName": meta.get("name"),
            "labels": labels,
            "capacity": status.get("capacity", {}) or {},
            "allocatable": status.get("allocatable", {}) or {},
            "ready": ready_condition.get("status") == "True",
            "roles": [
                key.replace("node-role.kubernetes.io/", "")
                for key in labels.keys()
                if key.startswith("node-role.kubernetes.io/")
            ],
        })
    return {"nodes": nodes, "nodeCount": len(nodes), "readyNodeCount": sum(1 for node in nodes if node.get("ready"))}


def parse_pods_json(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"pods": [], "podCount": 0}
    pods = []
    pods_by_node: Dict[str, List[str]] = {}
    pending = 0
    failed = 0
    not_ready = 0
    restart_total = 0
    for item in payload.get("items", []) or []:
        meta = item.get("metadata", {}) or {}
        spec = item.get("spec", {}) or {}
        status = item.get("status", {}) or {}
        phase = status.get("phase")
        statuses = status.get("containerStatuses", []) or []
        restart_count = sum(int(container.get("restartCount", 0) or 0) for container in statuses)
        ready_containers = sum(1 for container in statuses if container.get("ready") is True)
        total_containers = len(statuses)
        all_ready = total_containers > 0 and ready_containers == total_containers
        node = spec.get("nodeName")
        pod_name = meta.get("name")
        if phase == "Pending":
            pending += 1
        if phase == "Failed":
            failed += 1
        if not all_ready:
            not_ready += 1
        restart_total += restart_count
        if node:
            pods_by_node.setdefault(node, []).append(pod_name)
        pods.append({
            "podName": pod_name,
            "namespace": meta.get("namespace"),
            "nodeName": node,
            "phase": phase,
            "restartCount": restart_count,
            "readyContainers": ready_containers,
            "totalContainers": total_containers,
            "allContainersReady": all_ready,
            "labels": meta.get("labels", {}) or {},
        })
    return {
        "pods": pods,
        "podCount": len(pods),
        "podsByNode": pods_by_node,
        "pendingPodsCount": pending,
        "failedPodsCount": failed,
        "notReadyPodsCount": not_ready,
        "totalRestartCount": restart_total,
    }


def parse_events_json(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"eventCount": None, "warningEventCount": None}
    items = payload.get("items", []) or []
    warning = 0
    normal = 0
    for item in items:
        event_type = item.get("type") or item.get("reason") or ""
        if str(event_type).lower() == "warning":
            warning += 1
        else:
            normal += 1
    return {"eventCount": len(items), "warningEventCount": warning, "normalEventCount": normal}


def safe_load_json_file(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None or not path.exists():
        return None
    try:
        return read_json(path)
    except Exception:
        return None


def find_target_row(stats_csv: Path, target_type: str, target_name: str, fallback: bool) -> Tuple[Optional[Dict[str, str]], str]:
    with stats_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    target_row = None
    aggregated_row = None
    for row in rows:
        row_type = (row.get("Type") or "").strip()
        row_name = (row.get("Name") or "").strip()
        if row_type == target_type and row_name == target_name:
            target_row = row
            break
        if row_name == "Aggregated":
            aggregated_row = row
    if target_row is not None:
        return target_row, "target_request"
    if fallback and aggregated_row is not None:
        return aggregated_row, "aggregated_fallback"
    return None, "not_found"


def to_number(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def parse_locust_metrics(measurement_csv_prefix: Optional[str], repo_root: Path, profile: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "source": "locust_csv",
        "measurementCsvPrefix": measurement_csv_prefix,
        "available": False,
        "metrics": {},
        "artifacts": {},
        "rowSelection": "not_attempted",
    }
    if not measurement_csv_prefix:
        result["status"] = "skipped_no_measurement_csv_prefix"
        return result

    prefix = repo_path(repo_root, measurement_csv_prefix)
    if prefix is None:
        result["status"] = "invalid_measurement_csv_prefix"
        return result

    stats_csv = Path(str(prefix) + "_stats.csv")
    failures_csv = Path(str(prefix) + "_failures.csv")
    exceptions_csv = Path(str(prefix) + "_exceptions.csv")
    history_csv = Path(str(prefix) + "_stats_history.csv")
    result["artifacts"] = {
        "statsCsv": rel_or_abs(stats_csv, repo_root),
        "failuresCsv": rel_or_abs(failures_csv, repo_root),
        "exceptionsCsv": rel_or_abs(exceptions_csv, repo_root),
        "statsHistoryCsv": rel_or_abs(history_csv, repo_root),
        "statsCsvExists": stats_csv.exists(),
        "failuresCsvExists": failures_csv.exists(),
        "exceptionsCsvExists": exceptions_csv.exists(),
        "statsHistoryCsvExists": history_csv.exists(),
    }

    if not stats_csv.exists():
        result["status"] = "stats_csv_missing"
        return result

    client_cfg = profile.get("clientSideMetrics", {}) or {}
    row, selection = find_target_row(
        stats_csv,
        client_cfg.get("requestTargetType", "POST"),
        client_cfg.get("requestTargetName", "POST /v1/chat/completions"),
        bool(client_cfg.get("fallbackToAggregated", True)),
    )
    result["rowSelection"] = selection
    if row is None:
        result["status"] = "target_row_missing"
        return result

    request_count = to_number(row.get("Request Count"))
    failure_count = to_number(row.get("Failure Count"))
    success_rate = None
    if request_count and request_count > 0 and failure_count is not None:
        success_rate = max(0.0, (request_count - failure_count) / request_count * 100.0)

    result["available"] = True
    result["status"] = "available"
    result["metrics"] = {
        "request_count": request_count,
        "failure_count": failure_count,
        "success_rate_percent": success_rate,
        "mean_response_time_ms": to_number(row.get("Average Response Time")),
        "p50_response_time_ms": to_number(row.get("50%")),
        "p95_response_time_ms": to_number(row.get("95%")),
        "p99_response_time_ms": to_number(row.get("99%")),
        "throughput_rps": to_number(row.get("Requests/s")),
    }
    return result


def check_cluster_validation_gate(repo_root: Path, profile: Dict[str, Any], dry_run: bool, skip_gate: bool) -> Dict[str, Any]:
    gates = profile.get("gates", {}) or {}
    if skip_gate:
        return {"enabled": bool(gates.get("requireClusterValidationBeforeCollection", False)), "passed": True, "status": "skipped_by_explicit_flag"}
    if dry_run and gates.get("dryRunBypassesGates", True):
        return {"enabled": bool(gates.get("requireClusterValidationBeforeCollection", False)), "passed": True, "status": "bypassed_for_dry_run"}
    if not gates.get("requireClusterValidationBeforeCollection", False):
        return {"enabled": False, "passed": True, "status": "not_enabled"}

    manifest_path = repo_path(repo_root, gates.get("latestClusterValidationManifestPath"))
    details = {"manifestPath": rel_or_abs(manifest_path, repo_root), "manifestExists": bool(manifest_path and manifest_path.exists())}
    if not details["manifestExists"]:
        return {"enabled": True, "passed": False, "status": "failed_missing_cluster_validation_manifest", "details": details}
    manifest = read_json(manifest_path)
    details["manifestStatus"] = manifest.get("status")
    details["canProceedToApplicationDeployment"] = (manifest.get("decision") or {}).get("canProceedToApplicationDeployment")
    accepted = gates.get("acceptedClusterValidationStatuses", ["validated"])
    if manifest.get("status") not in accepted:
        return {"enabled": True, "passed": False, "status": "failed_unaccepted_cluster_validation_status", "details": details}
    if gates.get("requireCanProceedToApplicationDeployment", True) and details["canProceedToApplicationDeployment"] is not True:
        return {"enabled": True, "passed": False, "status": "failed_cluster_validation_decision", "details": details}
    return {"enabled": True, "passed": True, "status": "passed", "details": details}


def check_application_deployment_gate(repo_root: Path, profile: Dict[str, Any], dry_run: bool, skip_gate: bool, stage: str) -> Dict[str, Any]:
    gates = profile.get("gates", {}) or {}
    require = bool(gates.get("requireApplicationDeploymentBeforePostDeploymentCollection", False))
    if stage == "pre-benchmark":
        require = False
    if skip_gate:
        return {"enabled": require, "passed": True, "status": "skipped_by_explicit_flag"}
    if dry_run and gates.get("dryRunBypassesGates", True):
        return {"enabled": require, "passed": True, "status": "bypassed_for_dry_run"}
    if not require:
        return {"enabled": False, "passed": True, "status": "not_enabled"}

    manifest_path = repo_path(repo_root, gates.get("latestApplicationDeploymentManifestPath"))
    details = {"manifestPath": rel_or_abs(manifest_path, repo_root), "manifestExists": bool(manifest_path and manifest_path.exists())}
    if not details["manifestExists"]:
        return {"enabled": True, "passed": False, "status": "failed_missing_application_deployment_manifest", "details": details}
    manifest = read_json(manifest_path)
    details["manifestStatus"] = manifest.get("status")
    details["canProceedToBenchmark"] = (manifest.get("decision") or {}).get("canProceedToBenchmark")
    accepted = gates.get("acceptedApplicationDeploymentStatuses", ["deployed", "smoke_validated"])
    if manifest.get("status") not in accepted:
        return {"enabled": True, "passed": False, "status": "failed_unaccepted_application_deployment_status", "details": details}
    if gates.get("requireCanProceedToBenchmark", True) and details["canProceedToBenchmark"] is not True:
        return {"enabled": True, "passed": False, "status": "failed_application_deployment_decision", "details": details}
    return {"enabled": True, "passed": True, "status": "passed", "details": details}


def collect_kubectl_snapshots(repo_root: Path, profile: Dict[str, Any], kubeconfig: Optional[Path], namespaces: List[str], snapshots_root: Path, observability_id: str, stage: str, dry_run: bool) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    snapshots_root.mkdir(parents=True, exist_ok=True)
    kubectl = shutil.which("kubectl") or "kubectl"
    results: List[Dict[str, Any]] = []
    paths: Dict[str, Any] = {"_namespace_paths": {}}
    primary_namespace = namespaces[0] if namespaces else str(profile.get("namespace") or "default")

    for item in profile.get("collection", {}).get("commands", []):
        name = item.get("name")
        raw_args = [str(arg) for arg in item.get("args", [])]
        namespace_aware = namespace_command_has_placeholder(raw_args)
        command_namespaces = namespaces if namespace_aware else [primary_namespace]

        for namespace in command_namespaces:
            if namespace_aware:
                suffix = item.get("outputFile")
                output_name = suffix if namespace == primary_namespace else f"{safe_namespace_token(namespace)}.{suffix}"
                output_path = snapshots_root / f"{observability_id}.{stage}.{output_name}"
                args = replace_namespace(raw_args, namespace)
                result_name = name if namespace == primary_namespace else f"{name}:{namespace}"
                paths.setdefault("_namespace_paths", {}).setdefault(namespace, {})[name] = output_path
                if namespace == primary_namespace:
                    paths[name] = output_path
            else:
                output_path = snapshots_root / f"{observability_id}.{stage}.{item.get('outputFile')}"
                args = raw_args
                result_name = name
                paths[name] = output_path

            command = kubectl_base(kubectl, kubeconfig) + args
            if dry_run:
                results.append({
                    "name": result_name,
                    "baseName": name,
                    "namespace": namespace if namespace_aware else None,
                    "description": item.get("description"),
                    "required": bool(item.get("required", False)),
                    "command": command,
                    "outputPath": rel_or_abs(output_path, repo_root),
                    "exitCode": None,
                    "success": None,
                    "skipped": True,
                    "reason": "dry_run",
                })
                continue
            result = run_command(command)
            output = (result.get("stdout") or "")
            if result.get("stderr"):
                output += ("\n" if output else "") + str(result.get("stderr"))
            write_text(output_path, output)
            results.append({
                "name": result_name,
                "baseName": name,
                "namespace": namespace if namespace_aware else None,
                "description": item.get("description"),
                "required": bool(item.get("required", False)),
                "command": command,
                "outputPath": rel_or_abs(output_path, repo_root),
                "exitCode": result.get("exitCode"),
                "success": result.get("success"),
                "stderrPresent": bool(result.get("stderr")),
            })
    return results, paths


def merge_pod_metrics(parsed_by_namespace: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    pods: List[Dict[str, Any]] = []
    pods_by_node: Dict[str, List[str]] = {}
    pending = failed = not_ready = restarts = 0
    for namespace, parsed in parsed_by_namespace.items():
        for pod in parsed.get("pods", []) or []:
            pod = dict(pod)
            pod.setdefault("namespace", namespace)
            pods.append(pod)
        for node, names in (parsed.get("podsByNode") or {}).items():
            pods_by_node.setdefault(node, []).extend([f"{namespace}/{name}" for name in names])
        pending += int(parsed.get("pendingPodsCount") or 0)
        failed += int(parsed.get("failedPodsCount") or 0)
        not_ready += int(parsed.get("notReadyPodsCount") or 0)
        restarts += int(parsed.get("totalRestartCount") or 0)
    return {
        "pods": pods,
        "podCount": len(pods),
        "podsByNode": pods_by_node,
        "pendingPodsCount": pending,
        "failedPodsCount": failed,
        "notReadyPodsCount": not_ready,
        "totalRestartCount": restarts,
        "namespaces": parsed_by_namespace,
    }


def merge_event_metrics(parsed_by_namespace: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    event_count = 0
    warning_count = 0
    normal_count = 0
    for parsed in parsed_by_namespace.values():
        event_count += int(parsed.get("eventCount") or 0)
        warning_count += int(parsed.get("warningEventCount") or 0)
        normal_count += int(parsed.get("normalEventCount") or 0)
    return {
        "eventCount": event_count,
        "warningEventCount": warning_count,
        "normalEventCount": normal_count,
        "namespaces": parsed_by_namespace,
    }


def build_metrics(paths: Dict[str, Any], measurement_csv_prefix: Optional[str], repo_root: Path, profile: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    if dry_run:
        return {
            "clientSide": parse_locust_metrics(measurement_csv_prefix, repo_root, profile),
            "clusterSide": {
                "status": "skipped_for_dry_run",
                "metrics": {},
                "podPlacement": {},
            }
        }

    namespace_paths: Dict[str, Dict[str, Path]] = paths.get("_namespace_paths") or {}
    nodes_payload = safe_load_json_file(paths.get("nodes_json"))
    top_nodes_text = paths.get("top_nodes").read_text(encoding="utf-8", errors="replace") if paths.get("top_nodes") and paths.get("top_nodes").exists() else ""

    if namespace_paths:
        pods_by_namespace = {
            namespace: parse_pods_json(safe_load_json_file(ns_paths.get("pods_json")))
            for namespace, ns_paths in namespace_paths.items()
        }
        events_by_namespace = {
            namespace: parse_events_json(safe_load_json_file(ns_paths.get("events_json")))
            for namespace, ns_paths in namespace_paths.items()
        }
        top_pods_rows: List[Dict[str, Any]] = []
        for namespace, ns_paths in namespace_paths.items():
            top_pods_text = ns_paths.get("top_pods").read_text(encoding="utf-8", errors="replace") if ns_paths.get("top_pods") and ns_paths.get("top_pods").exists() else ""
            parsed_top_pods = parse_top_pods(top_pods_text)
            for row in parsed_top_pods.get("rows", []) or []:
                row = dict(row)
                row["namespace"] = namespace
                top_pods_rows.append(row)
        top_pods = {
            "rows": top_pods_rows,
            "maxPodCpuMillicores": max([row["cpuMillicores"] for row in top_pods_rows if row.get("cpuMillicores") is not None], default=None),
            "maxPodMemoryMiB": max([row["memoryMiB"] for row in top_pods_rows if row.get("memoryMiB") is not None], default=None),
        }
        pods = merge_pod_metrics(pods_by_namespace)
        events = merge_event_metrics(events_by_namespace)
    else:
        pods_payload = safe_load_json_file(paths.get("pods_json"))
        events_payload = safe_load_json_file(paths.get("events_json"))
        top_pods_text = paths.get("top_pods").read_text(encoding="utf-8", errors="replace") if paths.get("top_pods") and paths.get("top_pods").exists() else ""
        top_pods = parse_top_pods(top_pods_text)
        pods = parse_pods_json(pods_payload)
        events = parse_events_json(events_payload)

    top_nodes = parse_top_nodes(top_nodes_text)
    nodes = parse_nodes_json(nodes_payload)

    cluster_metrics = {
        "status": "available",
        "metrics": {
            "max_node_cpu_percent": top_nodes.get("maxNodeCpuPercent"),
            "max_node_memory_percent": top_nodes.get("maxNodeMemoryPercent"),
            "max_pod_cpu_millicores": top_pods.get("maxPodCpuMillicores"),
            "max_pod_memory_mib": top_pods.get("maxPodMemoryMiB"),
            "pending_pods_count": pods.get("pendingPodsCount"),
            "failed_pods_count": pods.get("failedPodsCount"),
            "not_ready_pods_count": pods.get("notReadyPodsCount"),
            "pod_restart_count": pods.get("totalRestartCount"),
            "kubernetes_events_count": events.get("eventCount"),
            "kubernetes_warning_events_count": events.get("warningEventCount"),
        },
        "nodes": nodes,
        "topNodes": top_nodes,
        "topPods": top_pods,
        "podPlacement": pods,
        "events": events,
    }
    return {
        "clientSide": parse_locust_metrics(measurement_csv_prefix, repo_root, profile),
        "clusterSide": cluster_metrics,
    }


def build_summary(manifest: Dict[str, Any]) -> str:
    metrics = manifest.get("metrics", {})
    client = (metrics.get("clientSide") or {}).get("metrics") or {}
    cluster = (metrics.get("clusterSide") or {}).get("metrics") or {}
    lines = [
        "Minimal observability summary",
        "==============================",
        "",
        f"Observability run ID: {manifest.get('observabilityRunId')}",
        f"Status: {manifest.get('status')}",
        f"Cycle: {manifest.get('cycle', {}).get('cycleId')}",
        f"Profile: {manifest.get('minimalObservabilityProfile', {}).get('profileId')}",
        f"Stage: {manifest.get('collection', {}).get('stage')}",
        f"Namespace: {manifest.get('collection', {}).get('namespace')}",
        f"Collected namespaces: {', '.join(manifest.get('collection', {}).get('namespaces') or [])}",
        "",
        "Gates:",
        f"- Cluster validation: {manifest.get('gates', {}).get('clusterValidation', {}).get('status')}",
        f"- Application deployment: {manifest.get('gates', {}).get('applicationDeployment', {}).get('status')}",
        "",
        "Client-side metrics:",
        f"- Request count: {client.get('request_count')}",
        f"- Failure count: {client.get('failure_count')}",
        f"- Success rate (%): {client.get('success_rate_percent')}",
        f"- Mean response time (ms): {client.get('mean_response_time_ms')}",
        f"- P95 response time (ms): {client.get('p95_response_time_ms')}",
        f"- Throughput (requests/s): {client.get('throughput_rps')}",
        "",
        "Cluster-side metrics:",
        f"- Max node CPU (%): {cluster.get('max_node_cpu_percent')}",
        f"- Max node memory (%): {cluster.get('max_node_memory_percent')}",
        f"- Max pod CPU (millicores): {cluster.get('max_pod_cpu_millicores')}",
        f"- Max pod memory (MiB): {cluster.get('max_pod_memory_mib')}",
        f"- Pending pods: {cluster.get('pending_pods_count')}",
        f"- Failed pods: {cluster.get('failed_pods_count')}",
        f"- Not-ready pods: {cluster.get('not_ready_pods_count')}",
        f"- Total pod restarts: {cluster.get('pod_restart_count')}",
        f"- Kubernetes events: {cluster.get('kubernetes_events_count')}",
        f"- Kubernetes warning events: {cluster.get('kubernetes_warning_events_count')}",
        "",
        "Decision:",
        f"- Can proceed to diagnosis: {manifest.get('decision', {}).get('canProceedToDiagnosis')}",
        f"- Reason: {manifest.get('decision', {}).get('reason')}",
    ]
    if manifest.get("warnings"):
        lines.extend(["", "Warnings:"])
        for warning in manifest["warnings"]:
            lines.append(f"- {warning}")
    if manifest.get("errors"):
        lines.extend(["", "Errors:"])
        for error in manifest["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect minimal K3s/metrics-server observability evidence for a provider-backed cycle.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--cycle-config", default="config/experimental-cycles/C1.json")
    parser.add_argument("--profile-config", default=None)
    parser.add_argument("--action", choices=["plan", "capture", "summarize"], default="capture")
    parser.add_argument("--stage", default=None)
    parser.add_argument("--kubeconfig", default=None)
    parser.add_argument("--namespace", default=None)
    parser.add_argument("--measurement-csv-prefix", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--observability-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-cluster-validation-gate", action="store_true")
    parser.add_argument("--skip-application-deployment-gate", action="store_true")
    parser.add_argument("--write-latest-aliases", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else default_repo_root().resolve()
    cycle_path, cycle = load_cycle(repo_root, args.cycle_config)
    profile_path, profile = resolve_observability_profile(repo_root, cycle, args.profile_config)
    observability_id = args.observability_id or f"{profile.get('minimalObservabilityProfileId', 'MO')}_{compact_now()}"
    stage = args.stage or profile.get("collection", {}).get("defaultStage", "post-deployment")
    namespace, namespaces, additional_namespaces = resolve_collection_namespaces(profile, args.namespace)
    kubeconfig = resolve_kubeconfig(repo_root, profile, args.kubeconfig)

    artifact_policy = profile.get("artifactPolicy", {}) or {}
    output_root_override = repo_path(repo_root, args.output_root) if args.output_root else None
    output_root = output_root_override or repo_path(repo_root, artifact_policy.get("root"))
    if output_root is None:
        output_root = repo_root / "results" / "observability" / "minimal"
    if output_root_override is not None:
        snapshots_root = output_root / "snapshots"
        manifests_root = output_root / "manifests"
        summaries_root = output_root / "summaries"
    else:
        snapshots_root = repo_path(repo_root, artifact_policy.get("snapshotsRoot")) or (output_root / "snapshots")
        manifests_root = repo_path(repo_root, artifact_policy.get("manifestsRoot")) or (output_root / "manifests")
        summaries_root = repo_path(repo_root, artifact_policy.get("summariesRoot")) or (output_root / "summaries")
    metrics_snapshot_path = summaries_root / f"{observability_id}-metrics.json"
    manifest_path = manifests_root / f"{observability_id}-manifest.json"
    summary_path = summaries_root / f"{observability_id}-summary.txt"

    cluster_gate = check_cluster_validation_gate(repo_root, profile, args.dry_run or args.action == "plan", args.skip_cluster_validation_gate)
    app_gate = check_application_deployment_gate(repo_root, profile, args.dry_run or args.action == "plan", args.skip_application_deployment_gate, stage)
    errors: List[str] = []
    warnings: List[str] = []

    if not cluster_gate.get("passed"):
        errors.append(f"Cluster validation gate failed: {cluster_gate.get('status')}")
    if not app_gate.get("passed"):
        errors.append(f"Application deployment gate failed: {app_gate.get('status')}")
    if not kubeconfig or not kubeconfig.exists():
        if args.action != "plan" and not args.dry_run:
            errors.append(f"Kubeconfig does not exist: {kubeconfig}")
        else:
            warnings.append(f"Kubeconfig not verified during {args.action}: {kubeconfig}")

    can_execute = not errors or args.action == "plan" or args.dry_run
    command_results: List[Dict[str, Any]] = []
    snapshot_paths: Dict[str, Path] = {}
    metrics: Dict[str, Any] = {
        "clientSide": parse_locust_metrics(args.measurement_csv_prefix, repo_root, profile),
        "clusterSide": {"status": "not_collected", "metrics": {}},
    }

    if args.action in ["plan", "capture"]:
        if can_execute:
            command_results, snapshot_paths = collect_kubectl_snapshots(
                repo_root=repo_root,
                profile=profile,
                kubeconfig=kubeconfig,
                namespaces=namespaces,
                snapshots_root=snapshots_root,
                observability_id=observability_id,
                stage=stage,
                dry_run=(args.dry_run or args.action == "plan"),
            )
            required_failures = [
                item for item in command_results
                if item.get("required") and item.get("success") is False
            ]
            optional_failures = [
                item for item in command_results
                if not item.get("required") and item.get("success") is False
            ]
            if required_failures:
                errors.append(f"{len(required_failures)} required kubectl observability command(s) failed.")
            if optional_failures:
                warnings.append(f"{len(optional_failures)} optional kubectl observability command(s) failed.")
            metrics = build_metrics(snapshot_paths, args.measurement_csv_prefix, repo_root, profile, args.dry_run or args.action == "plan")
        else:
            warnings.append("Kubectl observability collection skipped because a required gate failed.")

    elif args.action == "summarize":
        metrics = build_metrics(snapshot_paths, args.measurement_csv_prefix, repo_root, profile, args.dry_run)

    client_status = (metrics.get("clientSide") or {}).get("status")
    if client_status not in [None, "available", "skipped_no_measurement_csv_prefix"]:
        if profile.get("decisionPolicy", {}).get("allowMissingClientCsvWhenNoMeasurementPrefix", True):
            warnings.append(f"Client-side metrics were not fully available: {client_status}")
        else:
            errors.append(f"Client-side metrics were not fully available: {client_status}")

    status = "dry_run" if args.dry_run or args.action == "plan" else "observability_collected"
    if errors and status != "dry_run":
        status = "failed"
    elif warnings and status != "dry_run":
        status = "collected_with_warnings"

    can_proceed = status in ["observability_collected", "collected_with_warnings", "dry_run"]
    manifest: Dict[str, Any] = {
        "schemaVersion": "minimal-observability-manifest/v1",
        "observabilityRunId": observability_id,
        "createdAtUtc": utc_now(),
        "status": status,
        "action": args.action,
        "dryRun": bool(args.dry_run),
        "cycle": {
            "cycleId": cycle.get("cycleId"),
            "cycleConfigPath": rel_or_abs(cycle_path, repo_root),
            "baselineId": cycle.get("baseline", {}).get("baselineId") or cycle.get("cycleGovernance", {}).get("baselineId"),
        },
        "minimalObservabilityProfile": {
            "profileId": profile.get("minimalObservabilityProfileId"),
            "profilePath": rel_or_abs(profile_path, repo_root),
            "metricSetProfilePath": profile.get("metricSetProfilePath"),
            "clusterCaptureProfilePath": profile.get("clusterCaptureProfilePath"),
        },
        "collection": {
            "stage": stage,
            "namespace": namespace,
            "namespaces": namespaces,
            "additionalNamespaces": additional_namespaces,
            "kubeconfig": rel_or_abs(kubeconfig, repo_root),
            "measurementCsvPrefix": args.measurement_csv_prefix,
            "outputRoot": rel_or_abs(output_root, repo_root),
        },
        "gates": {
            "clusterValidation": cluster_gate,
            "applicationDeployment": app_gate,
        },
        "commands": command_results,
        "metrics": metrics,
        "artifacts": {
            "manifestPath": rel_or_abs(manifest_path, repo_root),
            "summaryPath": rel_or_abs(summary_path, repo_root),
            "metricsSnapshotPath": rel_or_abs(metrics_snapshot_path, repo_root),
            "snapshotsRoot": rel_or_abs(snapshots_root, repo_root),
            "latestManifestPath": artifact_policy.get("latestManifestPath"),
            "latestTextSummaryPath": artifact_policy.get("latestTextSummaryPath"),
            "latestMetricsSnapshotPath": artifact_policy.get("latestMetricsSnapshotPath"),
        },
        "warnings": warnings,
        "errors": errors,
        "decision": {
            "canProceedToDiagnosis": can_proceed,
            "reason": "minimal_observability_available" if can_proceed else "minimal_observability_failed",
        },
    }

    write_json(manifest_path, manifest)
    write_json(metrics_snapshot_path, metrics)
    write_text(summary_path, build_summary(manifest))

    write_aliases = args.write_latest_aliases or (bool(artifact_policy.get("writeLatestAliases", False)) and output_root_override is None)
    if write_aliases:
        latest_manifest = repo_path(repo_root, artifact_policy.get("latestManifestPath"))
        latest_summary = repo_path(repo_root, artifact_policy.get("latestTextSummaryPath"))
        latest_metrics = repo_path(repo_root, artifact_policy.get("latestMetricsSnapshotPath"))
        if latest_manifest:
            write_json(latest_manifest, manifest)
        if latest_summary:
            write_text(latest_summary, build_summary(manifest))
        if latest_metrics:
            write_json(latest_metrics, metrics)

    print(f"Minimal observability status: {status}")
    print(f" - manifest: {manifest_path}")
    print(f" - summary : {summary_path}")
    print(f" - metrics : {metrics_snapshot_path}")
    return 0 if status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
