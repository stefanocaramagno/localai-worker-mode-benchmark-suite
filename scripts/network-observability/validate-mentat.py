#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
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


def ordered_unique(values: List[Any]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def load_profile(repo_root: Path, profile_config: str) -> Tuple[Path, Dict[str, Any]]:
    profile_path = repo_path(repo_root, profile_config)
    if profile_path is None or not profile_path.exists():
        raise FileNotFoundError(f"Network observability profile not found: {profile_config}")
    return profile_path, read_json(profile_path)


def resolve_kubeconfig(repo_root: Path, profile: Dict[str, Any], explicit_kubeconfig: Optional[str]) -> Optional[Path]:
    return repo_path(repo_root, explicit_kubeconfig or profile.get("kubeconfigPath"))


def kubectl_base(kubectl: str, kubeconfig: Optional[Path]) -> List[str]:
    cmd = [kubectl]
    if kubeconfig is not None:
        cmd.extend(["--kubeconfig", str(kubeconfig)])
    return cmd


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


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def query_prometheus_via_port_forward(profile: Dict[str, Any], kubectl: str, kubeconfig: Optional[Path], queries: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    prometheus = profile.get("prometheus") or {}
    namespace = prometheus.get("namespace", "observability")
    service_name = prometheus.get("serviceName", "prometheus-stack-kube-prom-prometheus")
    remote_port = int(prometheus.get("port", 9090))
    timeout_seconds = int(prometheus.get("queryTimeoutSeconds", 10))
    ready_timeout = int(prometheus.get("portForwardReadyTimeoutSeconds", 20))
    local_port = free_local_port()
    command = kubectl_base(kubectl, kubeconfig) + ["-n", namespace, "port-forward", f"svc/{service_name}", f"{local_port}:{remote_port}"]
    started_at = utc_now()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    port_forward_result: Dict[str, Any] = {
        "command": command,
        "startedAtUtc": started_at,
        "finishedAtUtc": None,
        "exitCode": None,
        "stdout": "",
        "stderr": "",
        "success": False,
        "operation": "prometheus_port_forward",
        "localPort": local_port,
    }
    deadline = time.time() + ready_timeout
    ready = False
    lines: List[str] = []
    try:
        while time.time() < deadline:
            if process.poll() is not None:
                break
            line = process.stdout.readline() if process.stdout is not None else ""
            if line:
                lines.append(line)
                if "Forwarding from" in line:
                    ready = True
                    break
            else:
                time.sleep(0.2)
        port_forward_result["stdout"] = "".join(lines)
        port_forward_result["success"] = ready
        query_results: List[Dict[str, Any]] = []
        if ready:
            base_url = f"http://127.0.0.1:{local_port}/api/v1/query"
            for query in queries:
                query_id = str(query.get("queryId") or query.get("metricFamily") or "query")
                promql = str(query.get("promql") or query.get("metricFamily") or "")
                url = base_url + "?" + urllib.parse.urlencode({"query": promql})
                result: Dict[str, Any] = {
                    "queryId": query_id,
                    "metricFamily": query.get("metricFamily"),
                    "promql": promql,
                    "url": url,
                    "startedAtUtc": utc_now(),
                    "finishedAtUtc": None,
                    "success": False,
                    "seriesCount": 0,
                    "required": bool(query.get("required", False)),
                    "minimumSeries": int(query.get("minimumSeries") or 0),
                }
                try:
                    with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    values = (((payload or {}).get("data") or {}).get("result") or [])
                    result["seriesCount"] = len(values)
                    result["responseStatus"] = payload.get("status")
                    result["sampleSeries"] = values[:5]
                    result["success"] = payload.get("status") == "success" and len(values) >= int(query.get("minimumSeries") or 0)
                except Exception as exc:
                    result["error"] = str(exc)
                result["finishedAtUtc"] = utc_now()
                query_results.append(result)
        else:
            query_results = [{
                "queryId": str(query.get("queryId") or query.get("metricFamily") or "query"),
                "metricFamily": query.get("metricFamily"),
                "promql": query.get("promql"),
                "success": False,
                "seriesCount": 0,
                "required": bool(query.get("required", False)),
                "error": "prometheus_port_forward_not_ready",
            } for query in queries]
        return query_results, [port_forward_result]
    finally:
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        port_forward_result["finishedAtUtc"] = utc_now()
        port_forward_result["exitCode"] = process.poll()


def annotations_for(obj: Dict[str, Any]) -> Dict[str, str]:
    return obj.get("metadata", {}).get("annotations") or {}


def labels_for(obj: Dict[str, Any]) -> Dict[str, str]:
    return obj.get("metadata", {}).get("labels") or {}


def annotations_matching_prefixes(obj: Dict[str, Any], prefixes: List[str]) -> Dict[str, str]:
    annotations = annotations_for(obj)
    return {key: value for key, value in annotations.items() if any(str(key).startswith(prefix) for prefix in prefixes)}


def missing_annotation_prefixes(obj: Dict[str, Any], prefixes: List[str]) -> List[str]:
    annotations = annotations_for(obj)
    missing: List[str] = []
    for prefix in prefixes:
        if not any(str(key).startswith(prefix) and str(value).strip() for key, value in annotations.items()):
            missing.append(prefix + "*")
    return missing


def is_pod_ready(pod: Dict[str, Any]) -> bool:
    conditions = ((pod.get("status") or {}).get("conditions") or [])
    return any(cond.get("type") == "Ready" and cond.get("status") == "True" for cond in conditions)


def node_matches_selector(node: Dict[str, Any], selector: Dict[str, str]) -> bool:
    if not selector:
        return True
    labels = labels_for(node)
    for key, expected in selector.items():
        if str(labels.get(key) or "") != str(expected):
            return False
    return True


def capture_snapshot(profile: Dict[str, Any], kubectl: str, kubeconfig: Optional[Path], query_prometheus: bool) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    k8s = profile.get("kubernetes") or {}
    validation = profile.get("validation") or {}
    prometheus = profile.get("prometheus") or {}
    namespace = k8s.get("namespace", "observability")
    daemonset_name = k8s.get("daemonSetName", "mentat")
    pod_selector = k8s.get("podLabelSelector", "app=mentat")
    podmonitor_name = k8s.get("podMonitorName", "mentat")
    prefixes = [str(item) for item in validation.get("requiredNodeAnnotationPrefixes") or []]
    worker_selector = validation.get("workerNodeLabelSelector") or {}
    commands: List[Dict[str, Any]] = []

    daemonset_json, daemonset_cmd = kubectl_get_json(kubectl, kubeconfig, ["get", "daemonset", daemonset_name, "-n", namespace])
    daemonset_cmd["operation"] = "get_mentat_daemonset"
    commands.append(daemonset_cmd)

    pods_json, pods_cmd = kubectl_get_json(kubectl, kubeconfig, ["get", "pods", "-n", namespace, "-l", pod_selector])
    pods_cmd["operation"] = "get_mentat_pods"
    commands.append(pods_cmd)

    nodes_json, nodes_cmd = kubectl_get_json(kubectl, kubeconfig, ["get", "nodes"])
    nodes_cmd["operation"] = "get_nodes"
    commands.append(nodes_cmd)

    podmonitor_json = None
    if validation.get("requirePodMonitorWhenMonitoringEnabled", True) or k8s.get("podMonitorRequired", True):
        podmonitor_json, podmonitor_cmd = kubectl_get_json(kubectl, kubeconfig, ["get", "podmonitor", podmonitor_name, "-n", namespace])
        podmonitor_cmd["operation"] = "get_mentat_podmonitor"
        commands.append(podmonitor_cmd)

    service_json = None
    if validation.get("requirePrometheusService", True) or prometheus.get("required", True):
        service_json, service_cmd = kubectl_get_json(kubectl, kubeconfig, ["get", "svc", prometheus.get("serviceName", "prometheus-stack-kube-prom-prometheus"), "-n", prometheus.get("namespace", "observability")])
        service_cmd["operation"] = "get_prometheus_service"
        commands.append(service_cmd)

    logs: Dict[str, str] = {}
    pod_items = (pods_json or {}).get("items", [])
    for pod in pod_items[:10]:
        pod_name = (pod.get("metadata") or {}).get("name")
        if not pod_name:
            continue
        log_cmd = kubectl_base(kubectl, kubeconfig) + ["-n", namespace, "logs", pod_name, "--tail=120"]
        log_result = run_command(log_cmd)
        log_result["operation"] = "get_mentat_pod_logs"
        log_result["podName"] = pod_name
        commands.append(log_result)
        logs[pod_name] = log_result.get("stdout", "")

    metric_results: List[Dict[str, Any]] = []
    if query_prometheus and prometheus.get("queries"):
        metric_results, metric_commands = query_prometheus_via_port_forward(profile, kubectl, kubeconfig, prometheus.get("queries") or [])
        commands.extend(metric_commands)

    node_items = (nodes_json or {}).get("items", [])
    worker_nodes = [node for node in node_items if node_matches_selector(node, worker_selector)]
    node_checks = []
    for node in node_items:
        node_checks.append({
            "name": (node.get("metadata") or {}).get("name"),
            "labels": labels_for(node),
            "matchesWorkerSelector": node in worker_nodes,
            "annotations": annotations_matching_prefixes(node, prefixes),
            "missingRequiredAnnotationPrefixes": missing_annotation_prefixes(node, prefixes),
        })

    pod_checks = []
    for pod in pod_items:
        metadata = pod.get("metadata") or {}
        status = pod.get("status") or {}
        pod_checks.append({
            "name": metadata.get("name"),
            "namespace": metadata.get("namespace"),
            "nodeName": (pod.get("spec") or {}).get("nodeName"),
            "podStatus": status.get("pha" + "se"),
            "ready": is_pod_ready(pod),
            "podIP": status.get("podIP"),
            "labels": labels_for(pod),
        })

    snapshot = {
        "capturedAtUtc": utc_now(),
        "profileId": profile.get("networkObservabilityProfileId"),
        "namespace": namespace,
        "daemonSetName": daemonset_name,
        "podLabelSelector": pod_selector,
        "daemonSet": daemonset_json or {},
        "podMonitor": podmonitor_json or {},
        "prometheusService": service_json or {},
        "nodeCount": len(node_items),
        "workerNodeCount": len(worker_nodes),
        "mentatPodCount": len(pod_checks),
        "readyMentatPodCount": len([pod for pod in pod_checks if pod.get("ready")]),
        "nodesWithRequiredNetworkAnnotations": len([node for node in node_checks if not node.get("missingRequiredAnnotationPrefixes")]),
        "requiredNodeAnnotationPrefixes": prefixes,
        "nodes": node_checks,
        "mentatPods": pod_checks,
        "mentatLogsTailByPod": logs,
        "prometheusMetricResults": metric_results,
    }
    return snapshot, commands


def validation_passed(profile: Dict[str, Any], snapshot: Dict[str, Any], command_results: List[Dict[str, Any]], skip_prometheus_query: bool) -> Tuple[bool, List[str]]:
    validation = profile.get("validation") or {}
    reasons: List[str] = []
    if validation.get("requireDaemonSet", True):
        ds = snapshot.get("daemonSet") or {}
        if not ds.get("metadata", {}).get("name"):
            reasons.append("mentat_daemonset_not_found")
    expected_ready = int(validation.get("expectedMinimumReadyPods") or 0)
    if expected_ready > 0 and int(snapshot.get("readyMentatPodCount") or 0) < expected_ready:
        reasons.append("mentat_ready_pod_count_below_expected")
    expected_workers = int(validation.get("requiredWorkerNodeCount") or 0)
    if expected_workers > 0 and int(snapshot.get("workerNodeCount") or 0) < expected_workers:
        reasons.append("worker_node_count_below_expected")
    if validation.get("requirePodMonitorWhenMonitoringEnabled", True):
        if not (snapshot.get("podMonitor") or {}).get("metadata", {}).get("name"):
            reasons.append("mentat_podmonitor_not_found")
    if validation.get("requirePrometheusService", True):
        if not (snapshot.get("prometheusService") or {}).get("metadata", {}).get("name"):
            reasons.append("prometheus_service_not_found")
    if validation.get("requireNodeAnnotations", True):
        if int(snapshot.get("workerNodeCount") or 0) > 0 and int(snapshot.get("nodesWithRequiredNetworkAnnotations") or 0) < int(snapshot.get("workerNodeCount") or 0):
            reasons.append("not_all_worker_nodes_have_required_network_annotations")
    if validation.get("requirePrometheusMetrics", True) and not skip_prometheus_query:
        required_failures = []
        for result in snapshot.get("prometheusMetricResults") or []:
            if result.get("required") and not result.get("success"):
                required_failures.append(result.get("queryId") or result.get("metricFamily"))
        if required_failures:
            reasons.append("required_prometheus_metric_queries_failed:" + ",".join(str(item) for item in required_failures))
        if not (snapshot.get("prometheusMetricResults") or []):
            reasons.append("prometheus_metric_queries_not_executed")
    elif validation.get("requirePrometheusMetrics", True) and skip_prometheus_query:
        reasons.append("prometheus_metric_queries_skipped")
    return len(reasons) == 0, reasons


def wait_for_validation(profile: Dict[str, Any], kubectl: str, kubeconfig: Optional[Path], skip_prometheus_query: bool) -> Tuple[Dict[str, Any], List[Dict[str, Any]], bool, List[str]]:
    validation = profile.get("validation") or {}
    timeout_seconds = int(validation.get("waitTimeoutSeconds", 240))
    poll_seconds = int(validation.get("pollIntervalSeconds", 15))
    deadline = time.time() + timeout_seconds
    latest_snapshot: Dict[str, Any] = {}
    all_commands: List[Dict[str, Any]] = []
    latest_reasons: List[str] = ["not_checked"]
    while True:
        snapshot, commands = capture_snapshot(profile, kubectl, kubeconfig, query_prometheus=not skip_prometheus_query)
        all_commands.extend(commands)
        passed, reasons = validation_passed(profile, snapshot, commands, skip_prometheus_query)
        latest_snapshot = snapshot
        latest_reasons = reasons
        if passed:
            return snapshot, all_commands, True, []
        if timeout_seconds <= 0 or time.time() >= deadline:
            return latest_snapshot, all_commands, False, latest_reasons
        time.sleep(poll_seconds)


def artifact_paths(repo_root: Path, profile: Dict[str, Any], output_root: Optional[str]) -> Dict[str, Path]:
    policy = profile.get("artifactPolicy") or {}
    root = repo_path(repo_root, output_root) if output_root else repo_path(repo_root, policy.get("root"))
    if root is None:
        root = repo_root / "results" / "network-observability" / "mentat"
    if output_root:
        paths = {
            "root": root,
            "logs": root / "logs",
            "snapshots": root / "snapshots",
            "manifests": root / "manifests",
            "summaries": root / "summaries",
            "latest_manifest": root / "latest-mentat-observability-manifest.json",
            "latest_summary": root / "latest-mentat-observability-summary.txt",
            "latest_snapshot": root / "latest-mentat-validation-snapshot.json",
        }
    else:
        paths = {
            "root": root,
            "logs": repo_path(repo_root, policy.get("logsRoot")) or root / "logs",
            "snapshots": repo_path(repo_root, policy.get("snapshotsRoot")) or root / "snapshots",
            "manifests": repo_path(repo_root, policy.get("manifestsRoot")) or root / "manifests",
            "summaries": repo_path(repo_root, policy.get("summariesRoot")) or root / "summaries",
            "latest_manifest": repo_path(repo_root, policy.get("latestManifestPath")) or root / "latest-mentat-observability-manifest.json",
            "latest_summary": repo_path(repo_root, policy.get("latestSummaryPath")) or root / "latest-mentat-observability-summary.txt",
            "latest_snapshot": repo_path(repo_root, policy.get("latestValidationSnapshotPath")) or root / "latest-mentat-validation-snapshot.json",
        }
    for path in paths.values():
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path.mkdir(parents=True, exist_ok=True)
    return paths


def summarize(manifest: Dict[str, Any]) -> str:
    lines = [
        "Mentat network observability summary",
        "====================================",
        f"Profile: {manifest.get('profileId')}",
        f"Action: {manifest.get('action')}",
        f"Status: {manifest.get('status')}",
        f"Started: {manifest.get('startedAtUtc')}",
        f"Finished: {manifest.get('finishedAtUtc')}",
        "",
    ]
    if manifest.get("failureReasons"):
        lines.append("Failure reasons:")
        for reason in manifest.get("failureReasons") or []:
            lines.append(f"- {reason}")
        lines.append("")
    snapshot = manifest.get("validationSnapshot") or {}
    if snapshot:
        lines.extend([
            "Runtime snapshot:",
            f"- worker nodes: {snapshot.get('workerNodeCount')}",
            f"- Mentat pods: {snapshot.get('readyMentatPodCount')}/{snapshot.get('mentatPodCount')} ready",
            f"- nodes with required network annotations: {snapshot.get('nodesWithRequiredNetworkAnnotations')}/{snapshot.get('nodeCount')}",
            f"- Prometheus metric queries: {len(snapshot.get('prometheusMetricResults') or [])}",
            "",
        ])
    if manifest.get("validationSnapshotPath"):
        lines.append(f"Validation snapshot: {manifest.get('validationSnapshotPath')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and capture Mentat network observability evidence.")
    parser.add_argument("--repo-root", default=str(default_repo_root()))
    parser.add_argument("--profile-config", default="config/network-observability/profiles/NO_MENTAT_C9.json")
    parser.add_argument("--action", choices=["plan", "capture", "validate"], default="validate")
    parser.add_argument("--kubeconfig")
    parser.add_argument("--output-root")
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-prometheus-query", action="store_true")
    parser.add_argument("--write-latest-aliases", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    profile_path, profile = load_profile(repo_root, args.profile_config)
    paths = artifact_paths(repo_root, profile, args.output_root)
    run_id = args.run_id or f"{profile.get('networkObservabilityProfileId', 'mentat')}_{compact_now()}"
    kubeconfig = resolve_kubeconfig(repo_root, profile, args.kubeconfig)
    kubectl = (profile.get("kubernetes") or {}).get("kubectl", "kubectl")

    started_at = utc_now()
    command_results: List[Dict[str, Any]] = []
    snapshot: Dict[str, Any] = {}
    failure_reasons: List[str] = []
    status = "dry_run" if args.dry_run else "planned"

    if args.action == "plan" or args.dry_run:
        status = "dry_run" if args.dry_run else "planned"
    elif args.action == "capture":
        snapshot, command_results = capture_snapshot(profile, kubectl, kubeconfig, query_prometheus=not args.skip_prometheus_query)
        status = "captured"
    elif args.action == "validate":
        snapshot, command_results, passed, reasons = wait_for_validation(profile, kubectl, kubeconfig, args.skip_prometheus_query)
        if passed:
            status = "validated"
        else:
            status = "failed"
            failure_reasons.extend(reasons)

    snapshot_path: Optional[Path] = None
    if snapshot:
        snapshot_path = paths["snapshots"] / f"{run_id}.mentat-validation-snapshot.json"
        write_json(snapshot_path, snapshot)
        if args.write_latest_aliases or (profile.get("artifactPolicy") or {}).get("writeLatestAliases", True):
            write_json(paths["latest_snapshot"], snapshot)

    command_results_path = paths["logs"] / f"{run_id}.mentat-command-results.json"
    write_json(command_results_path, command_results)

    manifest = {
        "schemaVersion": "mentat-network-observability-manifest/v1",
        "profileId": profile.get("networkObservabilityProfileId"),
        "profilePath": rel_or_abs(profile_path, repo_root),
        "action": args.action,
        "status": status,
        "startedAtUtc": started_at,
        "finishedAtUtc": utc_now(),
        "dryRun": args.dry_run,
        "repoRoot": rel_or_abs(repo_root, repo_root),
        "kubeconfigPath": rel_or_abs(kubeconfig, repo_root),
        "providerManagedDeployment": bool((profile.get("mentat") or {}).get("managedByProvider", True)),
        "commandResultsPath": rel_or_abs(command_results_path, repo_root),
        "validationSnapshotPath": rel_or_abs(snapshot_path, repo_root),
        "failureReasons": failure_reasons,
        "validationSnapshot": snapshot,
    }
    manifest_path = paths["manifests"] / f"{run_id}.mentat-observability-manifest.json"
    summary_path = paths["summaries"] / f"{run_id}.mentat-observability-summary.txt"
    write_json(manifest_path, manifest)
    write_text(summary_path, summarize(manifest))
    if args.write_latest_aliases or (profile.get("artifactPolicy") or {}).get("writeLatestAliases", True):
        write_json(paths["latest_manifest"], manifest)
        write_text(paths["latest_summary"], summarize(manifest))

    print("===============================================")
    print(" Mentat network observability")
    print("===============================================")
    print(f"Profile : {profile.get('networkObservabilityProfileId')}")
    print(f"Action  : {args.action}")
    print(f"Status  : {status}")
    print(f"Manifest: {manifest_path}")
    print(f"Summary : {summary_path}")
    if failure_reasons:
        print("Failure reasons:")
        for reason in failure_reasons:
            print(f"- {reason}")

    return 0 if status in {"planned", "dry_run", "captured", "validated"} else 2


if __name__ == "__main__":
    sys.exit(main())
