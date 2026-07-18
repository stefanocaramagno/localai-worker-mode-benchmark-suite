#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_artifact_payload_for_output(payload, path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = normalize_artifact_text_for_output(content, path)
    path.write_text(content, encoding="utf-8")


def repo_path(repo_root: Path, value: str | None, default: str | None = None) -> Path:
    raw = value or default
    if not raw:
        raise ValueError("Cannot resolve an empty path.")
    path = Path(str(raw))
    return path if path.is_absolute() else repo_root / path


def rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return str(path)


def kubectl_command() -> str:
    return shutil.which("kubectl") or "kubectl"


def run_command(command: list[str], *, cwd: Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    record: dict[str, Any] = {
        "command": command,
        "startedAt": utc_now(),
        "dryRun": dry_run,
    }
    if dry_run:
        record.update({"status": "dry_run", "exitCode": 0, "stdout": "", "stderr": "", "completedAt": utc_now()})
        return record
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    record.update({
        "status": "completed" if completed.returncode == 0 else "failed",
        "exitCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "completedAt": utc_now(),
    })
    return record


def sanitize_name(value: str, limit: int = 63) -> str:
    text = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    text = re.sub(r"-+", "-", text)
    if len(text) <= limit:
        return text or "latency"
    return text[:limit].rstrip("-")


def expected_worker_nodes_from_infra(profile: dict[str, Any]) -> list[str]:
    inventory = profile.get("nodeInventory") or profile.get("nodes") or {}
    result: list[str] = []
    for item in inventory.get("workers", []) or []:
        name = item.get("expectedKubernetesNodeName") or item.get("name") or item.get("configuredName")
        if name:
            result.append(str(name))
    return result


def resolve_infrastructure_profile_path(repo_root: Path, cycle: dict[str, Any]) -> str | None:
    provider = cycle.get("providerBackedInfrastructure") or {}
    infra_path = provider.get("infrastructureProfilePath") or provider.get("fixedInfrastructureProfilePath")
    if infra_path:
        return str(infra_path)
    campaign = cycle.get("campaign") or {}
    infra_path = campaign.get("fixedInfrastructureProfilePath")
    if infra_path:
        return str(infra_path)
    planned_ids = provider.get("plannedInfrastructureProfileIds") or []
    if planned_ids:
        target_id = str(planned_ids[0])
        index_path = provider.get("infrastructureProfilesIndexPath") or "config/infrastructure/INFRA_PROFILES_INDEX.json"
        try:
            index = load_json(repo_path(repo_root, str(index_path)))
        except Exception:
            index = {}
        for item in index.get("profiles") or []:
            if str(item.get("infrastructureProfileId") or item.get("profileId") or "") == target_id:
                path = item.get("path") or item.get("profilePath")
                if path:
                    return str(path)
        return f"config/infrastructure/profiles/{target_id}.json"
    return None


def resolve_target_nodes(repo_root: Path, cycle: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    target = profile.get("target") or {}
    explicit = [str(item) for item in target.get("explicitNodeNames") or [] if str(item).strip()]
    if explicit:
        return explicit
    infra_path = resolve_infrastructure_profile_path(repo_root, cycle)
    infra_profile = load_json(repo_path(repo_root, infra_path)) if infra_path else {}
    policy = target.get("targetNodePolicy") or "all_worker_nodes_from_infrastructure_profile"
    if policy in {"all_worker_nodes_from_infrastructure_profile", "inter_group_worker_nodes_from_infrastructure_profile"}:
        return expected_worker_nodes_from_infra(infra_profile)
    if policy == "none":
        return []
    return expected_worker_nodes_from_infra(infra_profile)


def worker_ordinal_from_node_name(node_name: str, fallback_index: int) -> int:
    match = re.search(r"(?:worker|w)[-_]?(\d+)$", node_name)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return fallback_index


def inter_group_mapping(target_nodes: list[str], profile: dict[str, Any]) -> dict[str, str]:
    target = profile.get("target") or {}
    worker_groups = target.get("workerGroups") or []
    ordinal_to_node = {worker_ordinal_from_node_name(node, idx + 1): node for idx, node in enumerate(target_nodes)}
    out: dict[str, str] = {}
    for group in worker_groups:
        group_id = str(group.get("groupId") or "worker-group")
        for ordinal in group.get("workerOrdinals") or []:
            node = ordinal_to_node.get(int(ordinal))
            if node:
                out[node] = group_id
    for idx, node in enumerate(target_nodes):
        out.setdefault(node, f"worker-group-{worker_ordinal_from_node_name(node, idx + 1)}")
    return out


def build_inter_group_matrix(target_nodes: list[str], profile: dict[str, Any]) -> list[dict[str, Any]]:
    target = profile.get("target") or {}
    emulation = profile.get("networkEmulation") or {}
    control = emulation.get("annotationControl") or {}
    group_for_node = inter_group_mapping(target_nodes, profile)
    intra_ms = int(target.get("intraGroupDelayMs", emulation.get("intraGroupDelayMs", 0)) or 0)
    inter_ms = int(target.get("interGroupDelayMs", emulation.get("interGroupDelayMs", emulation.get("delayMs", 0))) or 0)
    loss = float(emulation.get("packetLossPercent") or 0.0)
    intra_bw = int(control.get("defaultIntraGroupBandwidthBytesPerSecond") or 1000000000)
    inter_bw = int(control.get("defaultInterGroupBandwidthBytesPerSecond") or intra_bw)
    rows: list[dict[str, Any]] = []
    for origin in target_nodes:
        peers: list[dict[str, Any]] = []
        for destination in target_nodes:
            if destination == origin:
                continue
            same_group = group_for_node.get(origin) == group_for_node.get(destination)
            peers.append({
                "destinationNode": destination,
                "originGroup": group_for_node.get(origin),
                "destinationGroup": group_for_node.get(destination),
                "sameGroup": same_group,
                "latencyMs": intra_ms if same_group else inter_ms,
                "packetLossPercent": loss,
                "bandwidthBytesPerSecond": intra_bw if same_group else inter_bw,
            })
        rows.append({"originNode": origin, "originGroup": group_for_node.get(origin), "peers": peers})
    return rows


def inter_group_annotation_args(row: dict[str, Any], profile: dict[str, Any], action: str) -> list[str]:
    emulation = profile.get("networkEmulation") or {}
    control = emulation.get("annotationControl") or {}
    latency_prefix = str(control.get("latencyAnnotationPrefix") or "network-latency.")
    loss_prefix = str(control.get("packetLossAnnotationPrefix") or "packet-loss.")
    bandwidth_prefix = str(control.get("bandwidthAnnotationPrefix") or "network-bandwidth.")
    owner_key = str(control.get("generatedAnnotationOwner") or "localai.benchmark/network-aware-latency-profile")
    profile_id = str(profile.get("latencyProfileId") or "latency-profile")
    args: list[str] = []
    for peer in row.get("peers") or []:
        destination = str(peer.get("destinationNode"))
        for key, value in [
            (latency_prefix + destination, peer.get("latencyMs")),
            (loss_prefix + destination, peer.get("packetLossPercent")),
            (bandwidth_prefix + destination, peer.get("bandwidthBytesPerSecond")),
        ]:
            args.append(f"{key}-" if action == "reset" else f"{key}={value}")
    args.append(f"{owner_key}-" if action == "reset" else f"{owner_key}={profile_id}")
    return args


def make_namespace(namespace: str) -> dict[str, Any]:
    return {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace}}


def shell_script(action: str) -> str:
    return r'''set -eu
IFACE="${NETEM_INTERFACE:-eth0}"
ACTION="${NETEM_ACTION:-apply}"
DELAY_MS="${DELAY_MS:-0}"
JITTER_MS="${JITTER_MS:-0}"
LOSS_PERCENT="${LOSS_PERCENT:-0}"
DISTRIBUTION="${NETEM_DISTRIBUTION:-normal}"

echo "latency-control: action=${ACTION} iface=${IFACE} delay=${DELAY_MS}ms jitter=${JITTER_MS}ms loss=${LOSS_PERCENT}%"

if [ "${ACTION}" = "inspect" ]; then
  tc qdisc show dev "${IFACE}" || true
  exit 0
fi

tc qdisc del dev "${IFACE}" root 2>/dev/null || true

if [ "${ACTION}" = "reset" ]; then
  tc qdisc show dev "${IFACE}" || true
  exit 0
fi

if [ "${DELAY_MS}" = "0" ] && [ "${JITTER_MS}" = "0" ] && [ "${LOSS_PERCENT}" = "0" ]; then
  tc qdisc show dev "${IFACE}" || true
  exit 0
fi

cmd="tc qdisc add dev ${IFACE} root netem delay ${DELAY_MS}ms"
if [ "${JITTER_MS}" != "0" ]; then
  cmd="${cmd} ${JITTER_MS}ms distribution ${DISTRIBUTION}"
fi
if [ "${LOSS_PERCENT}" != "0" ]; then
  cmd="${cmd} loss ${LOSS_PERCENT}%"
fi

echo "${cmd}"
sh -c "${cmd}"
tc qdisc show dev "${IFACE}"
'''


def make_job(*, namespace: str, job_name: str, node_name: str, image: str, action: str, interface: str, delay_ms: int, jitter_ms: int, loss_percent: float, distribution: str, timeout_seconds: int) -> dict[str, Any]:
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": job_name, "namespace": namespace, "labels": {"app.kubernetes.io/name": "latency-control", "latency-control/action": action}},
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 600,
            "activeDeadlineSeconds": timeout_seconds,
            "template": {
                "metadata": {"labels": {"app.kubernetes.io/name": "latency-control", "latency-control/action": action, "latency-control/node": sanitize_name(node_name, 52)}},
                "spec": {
                    "restartPolicy": "Never",
                    "hostNetwork": True,
                    "nodeName": node_name,
                    "tolerations": [{"operator": "Exists"}],
                    "containers": [
                        {
                            "name": "netem",
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "securityContext": {"privileged": True, "capabilities": {"add": ["NET_ADMIN"]}},
                            "env": [
                                {"name": "NETEM_ACTION", "value": action},
                                {"name": "NETEM_INTERFACE", "value": interface},
                                {"name": "DELAY_MS", "value": str(delay_ms)},
                                {"name": "JITTER_MS", "value": str(jitter_ms)},
                                {"name": "LOSS_PERCENT", "value": str(loss_percent)},
                                {"name": "NETEM_DISTRIBUTION", "value": distribution or "normal"},
                            ],
                            "command": ["/bin/sh", "-c", shell_script(action)],
                        }
                    ],
                },
            },
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply, reset or inspect a declarative latency profile on provider-backed Kubernetes worker nodes.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--cycle-config", required=True)
    parser.add_argument("--profile-config", required=True)
    parser.add_argument("--kubeconfig", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--injection-id", default="")
    parser.add_argument("--action", choices=["apply", "reset", "inspect"], default="apply")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write-latest-aliases", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    cycle_config = repo_path(repo_root, args.cycle_config)
    profile_config = repo_path(repo_root, args.profile_config)
    kubeconfig = repo_path(repo_root, args.kubeconfig)
    output_root = repo_path(repo_root, args.output_root)
    manifests_root = output_root / "manifests"
    logs_root = output_root / "logs"
    output_root.mkdir(parents=True, exist_ok=True)
    manifests_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)

    cycle = load_json(cycle_config)
    profile = load_json(profile_config)
    injection_id = args.injection_id.strip() or f"{profile.get('latencyProfileId', 'latency')}_{safe_stamp()}_{args.action}"
    enabled = bool(profile.get("enabled", False))
    runtime = profile.get("runtimeImplementation") or {}
    emulation = profile.get("networkEmulation") or {}
    namespace = str(runtime.get("kubernetesNamespace") or "latency-control")
    image = str(runtime.get("jobImage") or "docker.io/nicolaka/netshoot:latest")
    timeout_seconds = int(runtime.get("jobTimeoutSeconds") or 180)
    interface = str(emulation.get("networkInterface") or "eth0")
    delay_ms = int(emulation.get("delayMs") or 0)
    jitter_ms = int(emulation.get("jitterMs") or 0)
    loss_percent = float(emulation.get("packetLossPercent") or 0.0)
    distribution = str(emulation.get("distribution") or "normal")
    target_nodes = resolve_target_nodes(repo_root, cycle, profile)

    manifest: dict[str, Any] = {
        "schemaVersion": "latency-injection-manifest/v1",
        "injectionId": injection_id,
        "latencyProfileId": profile.get("latencyProfileId"),
        "profileConfig": rel(profile_config, repo_root),
        "cycleConfig": rel(cycle_config, repo_root),
        "action": args.action,
        "enabled": enabled,
        "dryRun": bool(args.dry_run),
        "createdAtUtc": utc_now(),
        "kubeconfigPath": rel(kubeconfig, repo_root),
        "outputRoot": rel(output_root, repo_root),
        "targetNodes": target_nodes,
        "networkEmulation": emulation,
        "runtimeImplementation": runtime,
        "commands": [],
        "generatedManifests": [],
        "logs": [],
        "status": "running",
        "errors": [],
    }

    inter_group_mode = str(emulation.get("mode") or "") == "inter_group_worker_latency_matrix"
    annotation_control = bool((emulation.get("annotationControl") or {}).get("enabled")) or "annotation" in str(emulation.get("tool") or "")

    if args.action == "apply" and not enabled:
        manifest["status"] = "skipped_disabled"
        manifest["decision"] = {"applied": False, "reason": "latency_profile_disabled"}
    elif not target_nodes:
        manifest["status"] = "failed"
        manifest["errors"].append("no_target_nodes_resolved")
    elif inter_group_mode and annotation_control:
        kubectl = kubectl_command()
        matrix = build_inter_group_matrix(target_nodes, profile)
        manifest["implementationMode"] = "annotation_controlled_inter_group_latency_matrix"
        manifest["interGroupLatencyMatrix"] = matrix
        manifest["commands"] = []
        node_results = []
        for row in matrix:
            node = str(row.get("originNode"))
            annotate_args = inter_group_annotation_args(row, profile, args.action)
            command = [kubectl, "--kubeconfig", str(kubeconfig), "annotate", "node", node, *annotate_args, "--overwrite"]
            if args.action == "inspect":
                command = [kubectl, "--kubeconfig", str(kubeconfig), "get", "node", node, "-o", "json"]
            result = run_command(command, cwd=repo_root, dry_run=args.dry_run)
            manifest["commands"].append(result)
            node_record = {"node": node, "operation": args.action, "annotationArgs": annotate_args, "command": result}
            node_record["status"] = "dry_run" if args.dry_run else ("completed" if result.get("exitCode") in (0, None) else "failed")
            node_results.append(node_record)
            if result.get("exitCode") not in (0, None):
                manifest["status"] = "failed"
                manifest["errors"].append(f"node_annotation_failed:{node}")
        manifest["nodeResults"] = node_results
        if manifest.get("status") != "failed":
            manifest["status"] = "dry_run" if args.dry_run else "completed"
            manifest["decision"] = {"applied": args.action == "apply" and enabled, "reset": args.action == "reset", "reason": "inter_group_latency_matrix_annotations_processed"}
    else:
        kubectl = kubectl_command()
        ns_path = manifests_root / f"{injection_id}_namespace.json"
        write_json(ns_path, make_namespace(namespace))
        manifest["generatedManifests"].append(rel(ns_path, repo_root))
        if args.action in {"apply", "reset"}:
            command = [kubectl, "--kubeconfig", str(kubeconfig), "apply", "-f", str(ns_path)]
            result = run_command(command, cwd=repo_root, dry_run=args.dry_run)
            manifest["commands"].append(result)
            if result.get("exitCode") not in (0, None):
                manifest["status"] = "failed"
                manifest["errors"].append("namespace_apply_failed")

        if manifest.get("status") != "failed":
            node_results = []
            for node in target_nodes:
                suffix = sanitize_name(f"{profile.get('latencyProfileId')}-{args.action}-{node}", 49)
                job_name = sanitize_name(f"latency-{suffix}")
                action = args.action if args.action in {"apply", "reset", "inspect"} else "apply"
                job = make_job(namespace=namespace, job_name=job_name, node_name=node, image=image, action=action, interface=interface, delay_ms=delay_ms, jitter_ms=jitter_ms, loss_percent=loss_percent, distribution=distribution, timeout_seconds=timeout_seconds)
                job_path = manifests_root / f"{injection_id}_{job_name}.json"
                write_json(job_path, job)
                manifest["generatedManifests"].append(rel(job_path, repo_root))

                node_record = {"node": node, "jobName": job_name, "jobManifest": rel(job_path, repo_root), "commands": []}
                for command in [
                    [kubectl, "--kubeconfig", str(kubeconfig), "-n", namespace, "delete", "job", job_name, "--ignore-not-found=true"],
                    [kubectl, "--kubeconfig", str(kubeconfig), "apply", "-f", str(job_path)],
                    [kubectl, "--kubeconfig", str(kubeconfig), "-n", namespace, "wait", "--for=condition=complete", f"job/{job_name}", f"--timeout={timeout_seconds}s"],
                ]:
                    result = run_command(command, cwd=repo_root, dry_run=args.dry_run)
                    node_record["commands"].append(result)
                    manifest["commands"].append(result)
                    if result.get("exitCode") not in (0, None):
                        node_record["status"] = "failed"
                        manifest["status"] = "failed"
                        manifest["errors"].append(f"job_failed:{job_name}")
                        break
                log_path = logs_root / f"{injection_id}_{job_name}.log"
                log_command = [kubectl, "--kubeconfig", str(kubeconfig), "-n", namespace, "logs", f"job/{job_name}"]
                log_result = run_command(log_command, cwd=repo_root, dry_run=args.dry_run)
                node_record["logCommand"] = log_result
                manifest["commands"].append(log_result)
                write_text(log_path, str(log_result.get("stdout") or "") + ("\nSTDERR:\n" + str(log_result.get("stderr") or "") if log_result.get("stderr") else ""))
                node_record["logPath"] = rel(log_path, repo_root)
                manifest["logs"].append(rel(log_path, repo_root))
                if not node_record.get("status"):
                    node_record["status"] = "dry_run" if args.dry_run else "completed"
                node_results.append(node_record)
            manifest["nodeResults"] = node_results
            if manifest.get("status") != "failed":
                manifest["status"] = "dry_run" if args.dry_run else "completed"
                manifest["decision"] = {"applied": args.action == "apply" and enabled, "reset": args.action == "reset", "reason": "latency_profile_processed"}

    manifest_path = output_root / f"{injection_id}_latency_injection_manifest.json"
    summary_path = output_root / f"{injection_id}_latency_injection_summary.txt"
    write_json(manifest_path, manifest)
    lines = [
        "Latency profile execution summary",
        "=================================",
        f"Injection: {injection_id}",
        f"Profile: {profile.get('latencyProfileId')}",
        f"Action: {args.action}",
        f"Status: {manifest.get('status')}",
        f"Enabled: {enabled}",
        f"Dry run: {args.dry_run}",
        f"Target nodes: {', '.join(target_nodes) if target_nodes else 'none'}",
        f"Delay: {delay_ms} ms",
        f"Jitter: {jitter_ms} ms",
        f"Loss: {loss_percent}%",
        f"Interface: {interface}",
    ]
    if manifest.get("errors"):
        lines.append("Errors:")
        lines.extend(f"- {item}" for item in manifest.get("errors") or [])
    write_text(summary_path, "\n".join(lines) + "\n")
    if args.write_latest_aliases:
        write_json(output_root / "latest-latency-injection-manifest.json", manifest)
        write_text(output_root / "latest-latency-injection-summary.txt", summary_path.read_text(encoding="utf-8"))
    return 0 if manifest.get("status") in {"completed", "dry_run", "skipped_disabled"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
