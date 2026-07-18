#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
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


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def nested_get(value: Any, *keys: str, default: Any = None) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def is_default_scheduler_placement(placement: Dict[str, Any], topology: Dict[str, Any]) -> bool:
    placement_id = str(placement.get("placementProfileId") or placement.get("placementReferenceId") or placement.get("scenarioId") or "")
    placement_type = str(placement.get("placementType") or placement.get("strategy") or "")
    default_scheduler = as_dict(topology.get("defaultSchedulerBaseline"))
    resource_aware_scheduler = as_dict(topology.get("schedulerMode"))
    return (
        bool(default_scheduler.get("enabled"))
        or bool(resource_aware_scheduler.get("enabled"))
        or placement_id in {"DEFAULT_KUBERNETES_SCHEDULER", "RUNTIME_SCHEDULER_DECISION"}
        or placement_type in {"kubernetes_default_scheduler", "runtime_scheduler_decision"}
        or str(placement.get("placementDecisionOwner") or "") in {"kubernetes_default_scheduler", "scheduler_plugins_loadaware", "scheduler-plugins-scheduler"}
    )


def load_cycle(repo_root: Path, cycle_config: str) -> Tuple[Path, Dict[str, Any]]:
    cycle_path = repo_path(repo_root, cycle_config)
    if cycle_path is None or not cycle_path.exists():
        raise FileNotFoundError(f"Experimental cycle profile not found: {cycle_config}")
    return cycle_path, read_json(cycle_path)


def resolve_deployment_profile(repo_root: Path, cycle: Dict[str, Any], explicit_profile: Optional[str]) -> Tuple[Path, Dict[str, Any]]:
    profile_value = (
        explicit_profile
        or cycle.get("pipelineProfiles", {}).get("applicationDeployment")
        or cycle.get("applicationDeployment", {}).get("applicationDeploymentProfilePath")
    )
    if not profile_value:
        raise ValueError("Application deployment profile path is not declared in the cycle profile and was not provided explicitly.")
    profile_path = repo_path(repo_root, profile_value)
    if profile_path is None or not profile_path.exists():
        raise FileNotFoundError(f"Application deployment profile not found: {profile_value}")
    return profile_path, read_json(profile_path)


def resolve_baseline(repo_root: Path, profile: Dict[str, Any]) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
    baseline_path = repo_path(repo_root, profile.get("baselineConfigPath"))
    if baseline_path and baseline_path.exists():
        return baseline_path, read_json(baseline_path)
    return baseline_path, None


def expected_kubernetes_nodes_from_infrastructure_profile(profile: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    inventory = profile.get("nodeInventory") or profile.get("nodes") or {}
    control_plane_nodes: List[str] = []
    worker_nodes: List[str] = []
    for item in inventory.get("controlPlane", []) or []:
        name = item.get("expectedKubernetesNodeName") or item.get("name") or item.get("configuredName")
        if name:
            control_plane_nodes.append(str(name))
    for item in inventory.get("workers", []) or []:
        name = item.get("expectedKubernetesNodeName") or item.get("name") or item.get("configuredName")
        if name:
            worker_nodes.append(str(name))
    return control_plane_nodes, worker_nodes


def resolve_infrastructure_context(repo_root: Path, profile: Dict[str, Any]) -> Dict[str, Any]:
    topology = as_dict(profile.get("deploymentTopology"))
    placement = as_dict(topology.get("placement"))
    explicit_count = placement.get("infrastructureWorkerNodeCount")
    explicit_nodes = placement.get("expectedInfrastructureWorkerNodes")

    infrastructure_profile_path = repo_path(repo_root, profile.get("infrastructureProfilePath"))
    infrastructure_profile: Optional[Dict[str, Any]] = None
    if infrastructure_profile_path and infrastructure_profile_path.exists():
        infrastructure_profile = read_json(infrastructure_profile_path)

    control_plane_nodes: List[str] = []
    worker_nodes: List[str] = []
    if infrastructure_profile:
        control_plane_nodes, worker_nodes = expected_kubernetes_nodes_from_infrastructure_profile(infrastructure_profile)

    if isinstance(explicit_nodes, list) and explicit_nodes:
        worker_nodes = [str(item) for item in explicit_nodes]

    worker_count: Optional[int] = None
    if explicit_count is not None:
        try:
            worker_count = int(explicit_count)
        except (TypeError, ValueError):
            worker_count = None
    if worker_count is None and worker_nodes:
        worker_count = len(worker_nodes)

    return {
        "infrastructureProfileId": profile.get("infrastructureProfileId"),
        "infrastructureProfilePath": rel_or_abs(infrastructure_profile_path, repo_root),
        "infrastructureProfileLoaded": infrastructure_profile is not None,
        "controlPlaneNodes": control_plane_nodes,
        "workerNodes": worker_nodes,
        "workerNodeCount": worker_count,
    }


def select_worker_node_mapping(placement_profile: Dict[str, Any], application_worker_scenario: Optional[str], infrastructure_worker_count: Optional[int]) -> Dict[str, Any]:
    worker_placement = as_dict(placement_profile.get("workerPlacement"))
    application_map = as_dict(worker_placement.get("activeWorkerNodeMapByWorkerCount"))
    infrastructure_map = as_dict(worker_placement.get("activeWorkerNodeMapByInfrastructureWorkerCount"))
    infrastructure_key = str(infrastructure_worker_count) if infrastructure_worker_count is not None else None

    if infrastructure_key and infrastructure_key in infrastructure_map:
        return {
            "selectedSource": "activeWorkerNodeMapByInfrastructureWorkerCount",
            "selectedKey": infrastructure_key,
            "selectedWorkerNodeMap": infrastructure_map[infrastructure_key],
            "selectionReason": "infrastructure_worker_node_count_match",
            "availableApplicationWorkerCountMappings": sorted(application_map.keys()),
            "availableInfrastructureWorkerCountMappings": sorted(infrastructure_map.keys()),
        }

    if application_worker_scenario and application_worker_scenario in application_map:
        return {
            "selectedSource": "activeWorkerNodeMapByWorkerCount",
            "selectedKey": application_worker_scenario,
            "selectedWorkerNodeMap": application_map[application_worker_scenario],
            "selectionReason": "application_worker_count_match",
            "availableApplicationWorkerCountMappings": sorted(application_map.keys()),
            "availableInfrastructureWorkerCountMappings": sorted(infrastructure_map.keys()),
        }

    return {
        "selectedSource": None,
        "selectedKey": None,
        "selectedWorkerNodeMap": None,
        "selectionReason": "no_matching_mapping",
        "availableApplicationWorkerCountMappings": sorted(application_map.keys()),
        "availableInfrastructureWorkerCountMappings": sorted(infrastructure_map.keys()),
    }


def resolve_placement_profile(repo_root: Path, profile: Dict[str, Any]) -> Tuple[Optional[Path], Optional[Dict[str, Any]], Dict[str, Any]]:
    topology = as_dict(profile.get("deploymentTopology"))
    placement = as_dict(topology.get("placement"))
    placement_path_value = placement.get("placementProfilePath")
    placement_id = placement.get("placementProfileId")
    details: Dict[str, Any] = {
        "placementProfileId": placement_id,
        "placementProfilePath": placement_path_value,
        "loaded": False,
        "status": "not_declared",
        "checks": [],
    }

    def add_check(name: str, passed: bool, severity: str = "error", extra: Optional[Dict[str, Any]] = None) -> None:
        details["checks"].append({"name": name, "passed": bool(passed), "severity": severity, "details": extra or {}})

    if is_default_scheduler_placement(placement, topology):
        infrastructure_context = resolve_infrastructure_context(repo_root, profile)
        default_scheduler = as_dict(topology.get("defaultSchedulerBaseline"))
        details.update({
            "loaded": False,
            "status": "default_scheduler_baseline",
            "strategy": "kubernetes_default_scheduler",
            "profileStatus": "not_applicable",
            "researchQuestion": default_scheduler.get("scenarioConfigPath") or profile.get("scenarioId"),
            "canUseForDeployment": True,
            "errorCount": 0,
            "warningCount": 0,
            "infrastructureContext": infrastructure_context,
            "workerNodeMappingSelection": {
                "selectedSource": "kubernetes_default_scheduler_runtime_decision",
                "selectedKey": None,
                "selectedWorkerNodeMap": None,
                "selectionReason": "default_scheduler_baseline_captures_runtime_placement_instead_of_using_a_static_mapping",
                "availableApplicationWorkerCountMappings": [],
                "availableInfrastructureWorkerCountMappings": [],
            },
            "mappingSemantics": {
                "decisionOwner": "kubernetes_default_scheduler",
                "hardPlacementControlsAllowed": bool(default_scheduler.get("hardPlacementControlsAllowed", False)),
                "placementEvidence": "captured_at_runtime",
                "placementProfileRequired": False,
            },
        })
        add_check(
            "default_scheduler_baseline_declared",
            True,
            "info",
            {
                "placementProfileId": placement_id,
                "placementProfilePath": placement_path_value,
                "decisionOwner": default_scheduler.get("placementDecisionOwner", "kubernetes_default_scheduler"),
            },
        )
        return None, None, details

    if not placement_path_value and not placement_id:
        add_check("placement_profile_declared", False, "warning")
        details["status"] = "not_declared"
        details["infrastructureContext"] = resolve_infrastructure_context(repo_root, profile)
        details["workerNodeMappingSelection"] = {}
        details["mappingSemantics"] = {}
        details["errorCount"] = 0
        details["warningCount"] = 1
        details["canUseForDeployment"] = True
        return None, None, details

    profile_path: Optional[Path] = None
    if placement_path_value:
        profile_path = repo_path(repo_root, placement_path_value)
    elif placement_id:
        index_path = repo_root / "config" / "placement" / "PLACEMENT_PROFILES_INDEX.json"
        if index_path.exists():
            index = read_json(index_path)
            for item in index.get("profiles", []):
                if item.get("placementProfileId") == placement_id:
                    profile_path = repo_path(repo_root, item.get("path"))
                    break

    details["resolvedProfilePath"] = rel_or_abs(profile_path, repo_root)
    if profile_path is None or not profile_path.exists():
        add_check("placement_profile_path_exists", False, "error", {"resolvedProfilePath": details["resolvedProfilePath"]})
        details["status"] = "invalid"
        details["infrastructureContext"] = resolve_infrastructure_context(repo_root, profile)
        details["workerNodeMappingSelection"] = {}
        details["mappingSemantics"] = {}
        details["errorCount"] = 1
        details["warningCount"] = 0
        details["canUseForDeployment"] = False
        return profile_path, None, details

    placement_profile = read_json(profile_path)
    details.update({
        "loaded": True,
        "status": "loaded",
        "placementProfileId": placement_profile.get("placementProfileId"),
        "strategy": placement_profile.get("strategy"),
        "profileStatus": placement_profile.get("status"),
        "researchQuestion": placement_profile.get("researchQuestion"),
    })
    add_check("placement_profile_path_exists", True)

    kustomize = as_dict(placement_profile.get("kustomize"))
    current_topology_path = kustomize.get("currentBaselineTopologyPath")
    if current_topology_path:
        target = repo_path(repo_root, current_topology_path)
        add_check("placement_current_topology_path_exists", bool(target and target.exists()), "error", {"path": current_topology_path})
    else:
        add_check("placement_current_topology_path_declared", False, "warning", {"implementationStatus": kustomize.get("implementationStatus")})

    worker_count_scenario = as_dict(profile.get("deploymentTopology")).get("workerCount", {}).get("scenarioId")
    infrastructure_context = resolve_infrastructure_context(repo_root, profile)
    infrastructure_worker_count = infrastructure_context.get("workerNodeCount")
    worker_placement = as_dict(placement_profile.get("workerPlacement"))
    worker_mappings = as_dict(worker_placement.get("activeWorkerNodeMapByWorkerCount"))
    infrastructure_worker_mappings = as_dict(worker_placement.get("activeWorkerNodeMapByInfrastructureWorkerCount"))
    selected_mapping = select_worker_node_mapping(placement_profile, worker_count_scenario, infrastructure_worker_count)
    details["infrastructureContext"] = infrastructure_context
    details["workerNodeMappingSelection"] = selected_mapping
    details["mappingSemantics"] = as_dict(worker_placement.get("mappingSemantics"))

    if worker_count_scenario:
        add_check(
            "placement_application_worker_count_mapping_available",
            worker_count_scenario in worker_mappings,
            "warning" if worker_count_scenario not in worker_mappings else "error",
            {"workerCountScenarioId": worker_count_scenario, "availableMappings": sorted(worker_mappings.keys())},
        )

    if infrastructure_worker_mappings or kustomize.get("compositionByInfrastructureWorkerCount"):
        infrastructure_key = str(infrastructure_worker_count) if infrastructure_worker_count is not None else None
        add_check(
            "placement_infrastructure_worker_count_mapping_available",
            bool(infrastructure_key and infrastructure_key in infrastructure_worker_mappings),
            "warning" if not infrastructure_key or infrastructure_key not in infrastructure_worker_mappings else "error",
            {
                "infrastructureWorkerNodeCount": infrastructure_worker_count,
                "availableMappings": sorted(infrastructure_worker_mappings.keys()),
                "expectedInfrastructureWorkerNodes": infrastructure_context.get("workerNodes"),
            },
        )

    if kustomize.get("compositionByApplicationWorkerCount"):
        application_composition = as_dict(kustomize.get("compositionByApplicationWorkerCount")).get(worker_count_scenario)
        if application_composition:
            target = repo_path(repo_root, application_composition)
            add_check("placement_application_worker_count_composition_exists", bool(target and target.exists()), "error", {"path": application_composition})
    if kustomize.get("compositionByInfrastructureWorkerCount") and infrastructure_worker_count is not None:
        infrastructure_key = str(infrastructure_worker_count)
        infrastructure_composition = as_dict(kustomize.get("compositionByInfrastructureWorkerCount")).get(infrastructure_key)
        if infrastructure_composition:
            target = repo_path(repo_root, infrastructure_composition)
            add_check("placement_infrastructure_worker_count_composition_exists", bool(target and target.exists()), "error", {"path": infrastructure_composition})

    declared_id = placement.get("placementProfileId")
    if declared_id:
        add_check(
            "deployment_placement_id_matches_profile",
            declared_id == placement_profile.get("placementProfileId"),
            "error",
            {"declaredId": declared_id, "profileId": placement_profile.get("placementProfileId")},
        )

    errors = [item for item in details["checks"] if not item["passed"] and item["severity"] == "error"]
    warnings = [item for item in details["checks"] if not item["passed"] and item["severity"] == "warning"]
    details["errorCount"] = len(errors)
    details["warningCount"] = len(warnings)
    details["status"] = "valid" if not errors else "invalid"
    details["canUseForDeployment"] = len(errors) == 0 and str(kustomize.get("implementationStatus", "")).startswith("active")
    return profile_path, placement_profile, details


def check_pre_deployment_gate(repo_root: Path, profile: Dict[str, Any], dry_run: bool, skip_gate: bool) -> Dict[str, Any]:
    gate = profile.get("preDeploymentGate", {})
    if skip_gate:
        return {"enabled": bool(gate.get("enabled", False)), "status": "skipped_by_explicit_flag", "passed": True, "details": {}}
    if dry_run and gate.get("dryRunBypassesGate", True):
        return {"enabled": bool(gate.get("enabled", False)), "status": "bypassed_for_dry_run", "passed": True, "details": {}}
    if not gate.get("enabled", False):
        return {"enabled": False, "status": "not_enabled", "passed": True, "details": {}}

    manifest_path = repo_path(repo_root, gate.get("latestClusterValidationManifestPath"))
    details: Dict[str, Any] = {
        "manifestPath": rel_or_abs(manifest_path, repo_root),
        "manifestExists": bool(manifest_path and manifest_path.exists()),
    }
    if gate.get("requireLatestClusterValidationManifest", True) and not details["manifestExists"]:
        return {"enabled": True, "status": "failed_missing_cluster_validation_manifest", "passed": False, "details": details}

    if manifest_path and manifest_path.exists():
        manifest = read_json(manifest_path)
        details["manifestStatus"] = manifest.get("status")
        details["canProceedToApplicationDeployment"] = (manifest.get("decision") or {}).get("canProceedToApplicationDeployment")
        accepted = gate.get("acceptedClusterValidationStatuses", ["validated"])
        if manifest.get("status") not in accepted:
            return {"enabled": True, "status": "failed_unaccepted_cluster_validation_status", "passed": False, "details": details}
        if gate.get("requireCanProceedToApplicationDeployment", True) and details["canProceedToApplicationDeployment"] is not True:
            return {"enabled": True, "status": "failed_cluster_validation_decision", "passed": False, "details": details}

    return {"enabled": True, "status": "passed", "passed": True, "details": details}


def classify_k8s_target(path: Path) -> str:
    if path.is_file():
        return "file"
    if path.is_dir() and (path / "kustomization.yaml").exists():
        return "kustomize"
    return "invalid"


def build_kubectl_apply_command(kubectl: str, kubeconfig: Optional[Path], target: Path) -> List[str]:
    command = [kubectl]
    if kubeconfig is not None:
        command.extend(["--kubeconfig", str(kubeconfig)])
    kind = classify_k8s_target(target)
    if kind == "file":
        command.extend(["apply", "-f", str(target)])
    elif kind == "kustomize":
        command.extend(["apply", "-k", str(target)])
    else:
        raise ValueError(f"Invalid Kubernetes apply target: {target}")
    return command


def run_command(command: List[str], cwd: Optional[Path] = None, timeout: Optional[int] = None) -> Dict[str, Any]:
    started_at = utc_now()
    completed = subprocess.run(command, cwd=str(cwd) if cwd else None, text=True, capture_output=True, timeout=timeout)
    return {
        "command": command,
        "startedAtUtc": started_at,
        "finishedAtUtc": utc_now(),
        "exitCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "success": completed.returncode == 0,
    }


def kubectl_base(kubectl: str, kubeconfig: Optional[Path]) -> List[str]:
    cmd = [kubectl]
    if kubeconfig is not None:
        cmd.extend(["--kubeconfig", str(kubeconfig)])
    return cmd


def safe_namespace_token(value: str) -> str:
    token = "".join(char.lower() if char.isalnum() or char in "._-" else "-" for char in str(value).strip())
    token = token.strip("-")
    return token or "namespace"


def dedupe_strings(values: List[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = str(value).strip() if value is not None else ""
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def resolve_snapshot_namespaces(topology: Dict[str, Any], primary_namespace: str) -> List[str]:
    namespaces: List[Any] = [primary_namespace]
    namespaces.extend(topology.get("namespaces") or [])
    namespaces.extend(topology.get("additionalNamespaces") or [])
    for target in topology.get("additionalRolloutTargets") or []:
        if isinstance(target, dict):
            namespaces.append(target.get("namespace"))
    return dedupe_strings(namespaces)


def capture_namespace_snapshot(
    kubectl: str,
    kubeconfig: Optional[Path],
    namespace: str,
    snapshots_root: Path,
    deployment_id: str,
    primary_namespace: str,
) -> Dict[str, Any]:
    snapshots_root.mkdir(parents=True, exist_ok=True)
    captures = [
        ("deployments", ["get", "deployments", "-n", namespace, "-o", "wide"]),
        ("deployments_json", ["get", "deployments", "-n", namespace, "-o", "json"]),
        ("pods", ["get", "pods", "-n", namespace, "-o", "wide"]),
        ("pods_json", ["get", "pods", "-n", namespace, "-o", "json"]),
        ("services", ["get", "services", "-n", namespace, "-o", "wide"]),
        ("configmaps", ["get", "configmaps", "-n", namespace]),
        ("pvc", ["get", "pvc", "-n", namespace, "-o", "wide"]),
        ("pvc_json", ["get", "pvc", "-n", namespace, "-o", "json"]),
        ("events", ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"]),
        ("events_json", ["get", "events", "-n", namespace, "-o", "json"]),
        ("describe_deployments", ["describe", "deployments", "-n", namespace]),
        ("describe_pods", ["describe", "pods", "-n", namespace]),
    ]
    namespace_role = "primary" if namespace == primary_namespace else "additional"
    file_prefix = deployment_id if namespace_role == "primary" else f"{deployment_id}.{safe_namespace_token(namespace)}"
    results: Dict[str, Any] = {}
    for name, args in captures:
        cmd = kubectl_base(kubectl, kubeconfig) + args
        result = run_command(cmd)
        path = snapshots_root / f"{file_prefix}.{name}.txt"
        write_text(path, (result.get("stdout") or "") + (("\n" + result.get("stderr", "")) if result.get("stderr") else ""))
        results[name] = {
            "path": str(path),
            "exitCode": result["exitCode"],
            "success": result["success"],
            "namespace": namespace,
            "namespaceRole": namespace_role,
            "namespaceScoped": True,
        }
    return results


def capture_snapshots(
    kubectl: str,
    kubeconfig: Optional[Path],
    namespaces: List[str],
    primary_namespace: str,
    snapshots_root: Path,
    deployment_id: str,
) -> Dict[str, Any]:
    resolved_namespaces = dedupe_strings([primary_namespace] + list(namespaces or []))
    additional_namespaces = [namespace for namespace in resolved_namespaces if namespace != primary_namespace]
    namespace_captures: Dict[str, Any] = {}
    for namespace in resolved_namespaces:
        namespace_captures[namespace] = capture_namespace_snapshot(kubectl, kubeconfig, namespace, snapshots_root, deployment_id, primary_namespace)

    result: Dict[str, Any] = {
        "primaryNamespace": primary_namespace,
        "namespaces": resolved_namespaces,
        "additionalNamespaces": additional_namespaces,
        "namespaceCaptures": namespace_captures,
    }
    result.update(namespace_captures.get(primary_namespace, {}))
    return result


def http_get_json(url: str, timeout_seconds: int) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    try:
        with urllib.request.urlopen(url, timeout=max(timeout_seconds, 1)) as response:
            raw = response.read().decode("utf-8")
            return True, json.loads(raw), None
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""
        return False, None, f"HTTP {exc.code}: {body or exc.reason}"
    except Exception as exc:
        return False, None, str(exc)


def post_json(url: str, payload: Dict[str, Any], timeout_seconds: int) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    try:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=max(timeout_seconds, 1)) as response:
            raw = response.read().decode("utf-8")
            return True, json.loads(raw), None
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""
        return False, None, f"HTTP {exc.code}: {body or exc.reason}"
    except Exception as exc:
        return False, None, str(exc)


def bounded_int(value: Any, default: int, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(parsed, minimum)


def terminate_process(process: Optional[subprocess.Popen[str]], timeout_seconds: int = 5) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()


def capture_smoke_diagnostics(
    repo_root: Path,
    kubectl: str,
    kubeconfig: Optional[Path],
    namespace: str,
    logs_root: Path,
    deployment_id: str,
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    diagnostics_root = logs_root / f"{deployment_id}.smoke-diagnostics"
    diagnostics_root.mkdir(parents=True, exist_ok=True)
    deployments = profile.get("deploymentTopology", {}).get("expectedResources", {}).get("deployments", [])
    commands: List[Tuple[str, List[str]]] = [
        ("pods", ["-n", namespace, "get", "pods", "-o", "wide"]),
        ("deployments", ["-n", namespace, "get", "deployments", "-o", "wide"]),
        ("services", ["-n", namespace, "get", "services", "-o", "wide"]),
        ("events", ["-n", namespace, "get", "events", "--sort-by=.lastTimestamp"]),
    ]
    for deployment in deployments:
        commands.append((f"describe-deployment-{deployment}", ["-n", namespace, "describe", "deployment", deployment]))
        commands.append((f"logs-deployment-{deployment}", ["-n", namespace, "logs", f"deployment/{deployment}", "--all-containers=true", "--tail=300"]))

    captures: Dict[str, Any] = {}
    for name, args in commands:
        command = kubectl_base(kubectl, kubeconfig) + args
        result = run_command(command, timeout=90)
        output_path = diagnostics_root / f"{name}.txt"
        write_text(output_path, (result.get("stdout") or "") + (("\n" + result.get("stderr", "")) if result.get("stderr") else ""))
        captures[name] = {
            "path": rel_or_abs(output_path, repo_root),
            "exitCode": result.get("exitCode"),
            "success": result.get("success"),
        }
    return {"root": rel_or_abs(diagnostics_root, repo_root), "captures": captures}


def resolve_smoke_validation_targets(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    smoke = profile.get("smokeValidation", {})
    explicit_targets = smoke.get("targets")
    if isinstance(explicit_targets, list) and explicit_targets:
        targets: List[Dict[str, Any]] = []
        for index, item in enumerate(explicit_targets):
            if not isinstance(item, dict):
                continue
            port_forward = dict(smoke.get("portForward") or {})
            port_forward.update(item.get("portForward") or {})
            namespace = item.get("namespace") or port_forward.get("namespace") or profile.get("deploymentTopology", {}).get("namespace", "default")
            service_name = item.get("serviceName") or port_forward.get("serviceName") or "localai-server"
            port_forward["namespace"] = namespace
            port_forward["serviceName"] = service_name
            targets.append({
                "tenantId": item.get("tenantId") or f"target-{index + 1}",
                "namespace": namespace,
                "serviceName": service_name,
                "baseUrl": item.get("baseUrl") or smoke.get("baseUrl", "http://localhost:8080"),
                "model": item.get("model") or smoke.get("model"),
                "portForward": port_forward,
            })
        if targets:
            return targets

    port_forward = dict(smoke.get("portForward") or {})
    namespace = port_forward.get("namespace") or profile.get("deploymentTopology", {}).get("namespace", "default")
    service_name = port_forward.get("serviceName", "localai-server")
    port_forward["namespace"] = namespace
    port_forward["serviceName"] = service_name
    return [{
        "tenantId": "primary",
        "namespace": namespace,
        "serviceName": service_name,
        "baseUrl": smoke.get("baseUrl", "http://localhost:8080"),
        "model": smoke.get("model"),
        "portForward": port_forward,
    }]


def run_single_smoke_validation_target(
    repo_root: Path,
    profile: Dict[str, Any],
    kubeconfig: Optional[Path],
    smoke_root: Path,
    deployment_id: str,
    target: Dict[str, Any],
    ordinal: int,
    total_targets: int,
) -> Dict[str, Any]:
    smoke = profile.get("smokeValidation", {})
    target_id = str(target.get("tenantId") or f"target-{ordinal + 1}")
    port_forward = dict(smoke.get("portForward") or {})
    port_forward.update(target.get("portForward") or {})
    base_url = str(target.get("baseUrl") or smoke.get("baseUrl", "http://localhost:8080")).rstrip("/")
    namespace = str(port_forward.get("namespace") or target.get("namespace") or profile.get("deploymentTopology", {}).get("namespace", "default"))
    service_name = str(port_forward.get("serviceName") or target.get("serviceName") or "localai-server")
    local_port = bounded_int(port_forward.get("localPort", 8080), 8080, 1)
    remote_port = bounded_int(port_forward.get("remotePort", 8080), 8080, 1)
    startup_wait = bounded_int(port_forward.get("startupWaitSeconds", 5), 5, 0)
    restart_backoff = bounded_int(port_forward.get("restartBackoffSeconds", 2), 2, 0)
    max_port_forward_starts = bounded_int(port_forward.get("maxRestartAttempts", 8), 8, 1)
    initial_delay = bounded_int(smoke.get("initialDelaySeconds", 15), 15, 0)
    readiness_timeout = bounded_int(smoke.get("readinessTimeoutSeconds", 360), 360, 1)
    readiness_request_timeout = bounded_int(smoke.get("readinessRequestTimeoutSeconds", 8), 8, 1)
    retry_interval = bounded_int(smoke.get("retryIntervalSeconds", 5), 5, 1)
    request_timeout = bounded_int(smoke.get("requestTimeoutSeconds", 120), 120, 1)
    chat_timeout = bounded_int(smoke.get("chatCompletionTimeoutSeconds", request_timeout), request_timeout, 1)
    chat_max_attempts = bounded_int(smoke.get("chatCompletionMaxAttempts", 3), 3, 1)
    chat_retry_interval = bounded_int(smoke.get("chatCompletionRetryIntervalSeconds", 10), 10, 1)
    capture_on_failure = bool(smoke.get("captureDiagnosticsOnFailure", True))
    required_endpoints = smoke.get("requiredEndpoints", ["/v1/models", "/v1/chat/completions"])
    requires_models = "/v1/models" in required_endpoints
    requires_chat = "/v1/chat/completions" in required_endpoints
    model = target.get("model") or smoke.get("model")

    kubectl = shutil.which("kubectl")
    target_identity = {
        "tenantId": target_id,
        "namespace": namespace,
        "serviceName": service_name,
        "targetOrdinal": ordinal + 1,
        "targetCount": total_targets,
    }
    if not kubectl:
        return {"enabled": True, "status": "failed", "passed": False, "error": "kubectl is not available in PATH", **target_identity}

    pf_proc: Optional[subprocess.Popen[str]] = None
    pf_log_handle: Optional[Any] = None
    suffix = "" if total_targets == 1 else f".{safe_namespace_token(target_id)}"
    pf_log_path = smoke_root / f"{deployment_id}{suffix}.port-forward.log"
    port_forward_starts: List[Dict[str, Any]] = []

    def close_pf_log() -> None:
        nonlocal pf_log_handle
        if pf_log_handle is not None:
            try:
                pf_log_handle.close()
            finally:
                pf_log_handle = None

    def ensure_port_forward(reason: str) -> Tuple[bool, Optional[str]]:
        nonlocal pf_proc, pf_log_handle
        if not port_forward.get("enabled", True):
            return True, None
        if pf_proc is not None and pf_proc.poll() is None:
            return True, None
        if len(port_forward_starts) >= max_port_forward_starts:
            return False, "maximum_port_forward_restart_attempts_exceeded"

        terminate_process(pf_proc)
        close_pf_log()
        smoke_root.mkdir(parents=True, exist_ok=True)
        command = kubectl_base(kubectl, kubeconfig) + [
            "-n", namespace, "port-forward", f"service/{service_name}", f"{local_port}:{remote_port}"
        ]
        pf_log_handle = pf_log_path.open("a", encoding="utf-8")
        pf_log_handle.write(f"\n--- port-forward start {len(port_forward_starts) + 1} at {utc_now()} target={target_id} reason={reason} ---\n")
        pf_log_handle.write("Command: " + " ".join(command) + "\n")
        pf_log_handle.flush()
        pf_proc = subprocess.Popen(command, stdout=pf_log_handle, stderr=subprocess.STDOUT, text=True)
        time.sleep(startup_wait)
        exit_code = pf_proc.poll()
        start_record = {
            "startedAtUtc": utc_now(),
            "tenantId": target_id,
            "namespace": namespace,
            "reason": reason,
            "command": command,
            "runningAfterStartupWait": exit_code is None,
            "exitCodeAfterStartupWait": exit_code,
        }
        port_forward_starts.append(start_record)
        if exit_code is not None:
            time.sleep(restart_backoff)
            return False, f"port_forward_exited_after_startup_wait_exit_code_{exit_code}"
        return True, None

    models_attempts: List[Dict[str, Any]] = []
    chat_attempts: List[Dict[str, Any]] = []
    models_payload: Optional[Dict[str, Any]] = None
    chat_response: Optional[Dict[str, Any]] = None
    models_available: List[str] = []
    models_error: Optional[str] = None
    chat_error: Optional[str] = None
    models_ok = False
    model_present = False
    chat_ok = False

    try:
        if initial_delay > 0:
            time.sleep(initial_delay)

        readiness_deadline = time.time() + readiness_timeout
        while time.time() < readiness_deadline:
            pf_ok, pf_error = ensure_port_forward("models_readiness")
            if not pf_ok:
                models_error = pf_error
                models_attempts.append({"attemptedAtUtc": utc_now(), "success": False, "error": pf_error})
                time.sleep(retry_interval)
                continue

            ok, payload, error = http_get_json(f"{base_url}/v1/models", readiness_request_timeout)
            available: List[str] = []
            if ok and isinstance(payload, dict):
                data = payload.get("data")
                if isinstance(data, list):
                    available = [item.get("id") for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)]
            present = bool(model in available) if model else bool(available)
            attempt_record = {
                "attemptedAtUtc": utc_now(),
                "success": ok,
                "error": error,
                "availableModels": available,
                "modelPresent": present,
                "portForwardRunning": (pf_proc.poll() is None if pf_proc is not None else None),
            }
            models_attempts.append(attempt_record)
            models_error = error
            if ok:
                models_payload = payload
                models_available = available
                models_ok = True
                model_present = present
                if not requires_models or model_present:
                    break
                models_error = f"model_not_available: {model}"

            if pf_proc is not None and pf_proc.poll() is not None:
                time.sleep(restart_backoff)
            else:
                time.sleep(retry_interval)

        chat_payload = {
            "model": model,
            "messages": [{"role": "user", "content": smoke.get("prompt", "Reply with only READY.")}],
            "temperature": smoke.get("temperature", 0.1),
            "max_tokens": smoke.get("maxTokens", 8),
        }

        if not requires_chat:
            chat_ok = True
        elif models_ok and model_present:
            for attempt_index in range(chat_max_attempts):
                pf_ok, pf_error = ensure_port_forward("chat_completions")
                if not pf_ok:
                    chat_error = pf_error
                    chat_attempts.append({"attemptedAtUtc": utc_now(), "success": False, "error": pf_error})
                    time.sleep(chat_retry_interval)
                    continue
                ok, response, error = post_json(f"{base_url}/v1/chat/completions", chat_payload, chat_timeout)
                chat_attempts.append({
                    "attemptedAtUtc": utc_now(),
                    "attempt": attempt_index + 1,
                    "success": ok,
                    "error": error,
                    "portForwardRunning": (pf_proc.poll() is None if pf_proc is not None else None),
                })
                chat_error = error
                if ok:
                    chat_ok = True
                    chat_response = response
                    break
                if attempt_index < chat_max_attempts - 1:
                    time.sleep(chat_retry_interval)
        else:
            chat_error = "model_not_available" if models_ok else "models_endpoint_not_ready"

        passed = bool((not requires_models or (models_ok and model_present)) and (not requires_chat or chat_ok))
        result: Dict[str, Any] = {
            "enabled": True,
            "status": "passed" if passed else "failed",
            "passed": passed,
            "applicationHttpReady": bool(models_ok and model_present),
            "baseUrl": base_url,
            "model": model,
            "requiredEndpoints": required_endpoints,
            **target_identity,
            "timing": {
                "initialDelaySeconds": initial_delay,
                "readinessTimeoutSeconds": readiness_timeout,
                "readinessRequestTimeoutSeconds": readiness_request_timeout,
                "retryIntervalSeconds": retry_interval,
                "chatCompletionTimeoutSeconds": chat_timeout,
                "chatCompletionMaxAttempts": chat_max_attempts,
            },
            "modelsEndpoint": {
                "success": models_ok,
                "error": models_error,
                "availableModels": models_available,
                "modelPresent": model_present,
                "attemptCount": len(models_attempts),
                "attempts": models_attempts,
                "lastPayload": models_payload,
            },
            "chatCompletionsEndpoint": {
                "success": chat_ok,
                "error": chat_error,
                "attemptCount": len(chat_attempts),
                "attempts": chat_attempts,
                "response": chat_response,
            },
            "portForward": {
                "enabled": port_forward.get("enabled", True),
                "namespace": namespace,
                "serviceName": service_name,
                "localPort": local_port,
                "remotePort": remote_port,
                "logPath": rel_or_abs(pf_log_path, repo_root) if port_forward.get("enabled", True) else None,
                "startCount": len(port_forward_starts),
                "starts": port_forward_starts,
                "maxRestartAttempts": max_port_forward_starts,
            },
        }
        if not passed and capture_on_failure:
            result["diagnostics"] = capture_smoke_diagnostics(repo_root, kubectl, kubeconfig, namespace, smoke_root, f"{deployment_id}{suffix}", profile)
        return result
    finally:
        terminate_process(pf_proc)
        close_pf_log()


def run_smoke_validation(repo_root: Path, profile: Dict[str, Any], kubeconfig: Optional[Path], smoke_root: Path, deployment_id: str) -> Dict[str, Any]:
    smoke = profile.get("smokeValidation", {})
    if not smoke.get("enabled", True):
        return {"enabled": False, "status": "skipped", "passed": True}

    targets = resolve_smoke_validation_targets(profile)
    target_results = [
        run_single_smoke_validation_target(repo_root, profile, kubeconfig, smoke_root, deployment_id, target, index, len(targets))
        for index, target in enumerate(targets)
    ]
    passed = bool(target_results) and all(bool(item.get("passed")) for item in target_results)
    primary = target_results[0] if target_results else {}
    result: Dict[str, Any] = {
        "enabled": True,
        "status": "passed" if passed else "failed",
        "passed": passed,
        "applicationHttpReady": bool(target_results) and all(bool(item.get("applicationHttpReady")) for item in target_results),
        "baseUrl": primary.get("baseUrl") or smoke.get("baseUrl", "http://localhost:8080"),
        "model": primary.get("model") or smoke.get("model"),
        "requiredEndpoints": smoke.get("requiredEndpoints", ["/v1/models", "/v1/chat/completions"]),
        "targetCount": len(target_results),
        "passedTargetCount": sum(1 for item in target_results if item.get("passed")),
        "failedTargetCount": sum(1 for item in target_results if not item.get("passed")),
        "targetResults": target_results,
        "timing": primary.get("timing", {}),
        "modelsEndpoint": primary.get("modelsEndpoint", {}),
        "chatCompletionsEndpoint": primary.get("chatCompletionsEndpoint", {}),
        "portForward": primary.get("portForward", {}),
    }
    if len(target_results) == 1:
        result.update({key: value for key, value in primary.items() if key not in {"status", "passed", "enabled"}})
        result["status"] = "passed" if passed else "failed"
        result["passed"] = passed
        result["enabled"] = True
    return result


def build_summary(manifest: Dict[str, Any]) -> str:
    placement_summary = as_dict(manifest.get("placementProfile"))
    smoke_summary = as_dict(manifest.get("smokeValidation"))
    infrastructure_context = as_dict(placement_summary.get("infrastructureContext"))
    mapping_selection = as_dict(placement_summary.get("workerNodeMappingSelection"))
    models_endpoint = as_dict(smoke_summary.get("modelsEndpoint"))
    chat_endpoint = as_dict(smoke_summary.get("chatCompletionsEndpoint"))
    pre_gate = as_dict(manifest.get("preDeploymentGate"))
    decision = as_dict(manifest.get("decision"))
    topology = as_dict(manifest.get("deploymentTopology"))
    worker_count = as_dict(topology.get("workerCount"))
    model = as_dict(topology.get("model"))
    placement = as_dict(topology.get("placement"))

    lines = [
        "Provider-backed LocalAI deployment summary",
        "===========================================",
        "",
        f"Deployment run ID: {manifest.get('deploymentRunId')}",
        f"Status: {manifest.get('status')}",
        f"Cycle: {nested_get(manifest, 'cycle', 'cycleId')}",
        f"Baseline: {nested_get(manifest, 'baseline', 'baselineId')}",
        f"Deployment profile: {nested_get(manifest, 'applicationDeploymentProfile', 'profileId')}",
        f"Namespace: {topology.get('namespace')}",
        f"Model: {model.get('modelName')}",
        f"Worker count: {worker_count.get('count')}",
        f"Placement: {placement.get('placementType')}",
        f"Placement profile: {placement_summary.get('placementProfileId')}",
        f"Placement profile status: {placement_summary.get('status')}",
        f"Placement strategy: {placement_summary.get('strategy')}",
        f"Infrastructure worker nodes: {infrastructure_context.get('workerNodeCount')}",
        f"Placement mapping source: {mapping_selection.get('selectedSource')}",
        "",
        "Pre-deployment gate:",
        f"- Status: {pre_gate.get('status')}",
        f"- Passed: {pre_gate.get('passed')}",
        "",
        "Kubernetes apply:",
        f"- Targets: {len(manifest.get('kubernetesApply', []) or [])}",
        f"- Successful targets: {sum(1 for item in (manifest.get('kubernetesApply', []) or []) if as_dict(item).get('success'))}",
        "",
        "Rollout checks:",
        f"- Checks: {len(manifest.get('rolloutChecks', []) or [])}",
        f"- Successful checks: {sum(1 for item in (manifest.get('rolloutChecks', []) or []) if as_dict(item).get('success'))}",
        "",
        "Smoke validation:",
        f"- Status: {smoke_summary.get('status')}",
        f"- Passed: {smoke_summary.get('passed')}",
        f"- HTTP ready: {smoke_summary.get('applicationHttpReady')}",
        f"- Targets: {smoke_summary.get('targetCount', 1 if smoke_summary.get('enabled') else 0)}",
        f"- Passed targets: {smoke_summary.get('passedTargetCount')}",
        f"- Failed targets: {smoke_summary.get('failedTargetCount')}",
        f"- /v1/models attempts: {models_endpoint.get('attemptCount')}",
        f"- /v1/chat/completions attempts: {chat_endpoint.get('attemptCount')}",
        "",
        "Decision:",
        f"- Can proceed to benchmark: {decision.get('canProceedToBenchmark')}",
        f"- Reason: {decision.get('reason')}",
    ]
    if manifest.get("errors"):
        lines.extend(["", "Errors:"])
        for error in manifest["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy LocalAI for a provider-backed experimental cycle.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--cycle-config", default="config/experimental-cycles/C1.json")
    parser.add_argument("--deployment-profile", default=None)
    parser.add_argument("--action", choices=["plan", "deploy", "smoke"], default="deploy")
    parser.add_argument("--kubeconfig", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--deployment-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-cluster-validation-gate", action="store_true")
    parser.add_argument("--skip-smoke-test", action="store_true")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--no-port-forward", action="store_true")
    parser.add_argument("--write-latest-aliases", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else default_repo_root()
    deployment_id = args.deployment_id or f"localai_deployment_{compact_now()}"
    started_at = utc_now()
    errors: List[str] = []

    try:
        cycle_path, cycle = load_cycle(repo_root, args.cycle_config)
        profile_path, profile = resolve_deployment_profile(repo_root, cycle, args.deployment_profile)
        baseline_path, baseline = resolve_baseline(repo_root, profile)
        placement_profile_path, placement_profile, placement_profile_status = resolve_placement_profile(repo_root, profile)
        artifact_policy = profile.get("artifactPolicy", {})
        explicit_output_root = bool(args.output_root)
        output_root = repo_path(repo_root, args.output_root) if explicit_output_root else repo_path(repo_root, artifact_policy.get("root"))
        output_root = output_root or repo_root / "results" / "_runtime" / "localai-deployment"
        if explicit_output_root:
            logs_root = output_root / "logs"
            manifests_root = output_root / "manifests"
            snapshots_root = output_root / "snapshots"
        else:
            logs_root = repo_path(repo_root, artifact_policy.get("logsRoot")) or output_root / "logs"
            manifests_root = repo_path(repo_root, artifact_policy.get("manifestsRoot")) or output_root / "manifests"
            snapshots_root = repo_path(repo_root, artifact_policy.get("snapshotsRoot")) or output_root / "snapshots"
        for directory in [output_root, logs_root, manifests_root, snapshots_root]:
            directory.mkdir(parents=True, exist_ok=True)

        if args.base_url:
            profile.setdefault("smokeValidation", {})["baseUrl"] = args.base_url
        if args.no_port_forward:
            profile.setdefault("smokeValidation", {}).setdefault("portForward", {})["enabled"] = False
        if args.skip_smoke_test:
            profile.setdefault("smokeValidation", {})["enabled"] = False

        topology = profile.get("deploymentTopology", {})
        namespace = topology.get("namespace", "default")
        snapshot_namespaces = resolve_snapshot_namespaces(topology, namespace)
        kubeconfig_path = repo_path(repo_root, args.kubeconfig or topology.get("kubeconfigPath"))
        pre_gate = check_pre_deployment_gate(repo_root, profile, args.dry_run, args.skip_cluster_validation_gate)
        if not pre_gate.get("passed"):
            errors.append(f"Pre-deployment gate failed: {pre_gate.get('status')}")
        if placement_profile_status.get("status") == "invalid":
            errors.append("Placement profile resolution failed.")

        kubectl = shutil.which("kubectl")
        if not args.dry_run and args.action in {"deploy", "smoke"}:
            if not kubectl:
                errors.append("kubectl is not available in PATH.")
            if not kubeconfig_path or not kubeconfig_path.exists() or kubeconfig_path.stat().st_size == 0:
                errors.append(f"Kubeconfig is missing or empty: {kubeconfig_path}")

        apply_results: List[Dict[str, Any]] = []
        rollout_results: List[Dict[str, Any]] = []
        snapshot_results: Dict[str, Any] = {}
        smoke_result: Dict[str, Any] = {"enabled": bool(profile.get("smokeValidation", {}).get("enabled", True)), "status": "not_run", "passed": False}

        if not errors and args.action == "deploy":
            for target in topology.get("kustomizeApplyOrder", []):
                target_path = repo_path(repo_root, target.get("path"))
                target_record: Dict[str, Any] = dict(target)
                target_record["resolvedPath"] = rel_or_abs(target_path, repo_root)
                target_record["exists"] = bool(target_path and target_path.exists())
                if target_path is None or not target_path.exists():
                    target_record["success"] = False
                    target_record["error"] = "target_missing"
                    apply_results.append(target_record)
                    if target.get("required", True):
                        errors.append(f"Required Kubernetes apply target is missing: {target.get('path')}")
                    continue
                target_record["targetType"] = classify_k8s_target(target_path)
                if target_record["targetType"] == "invalid":
                    target_record["success"] = False
                    target_record["error"] = "target_invalid"
                    apply_results.append(target_record)
                    if target.get("required", True):
                        errors.append(f"Required Kubernetes apply target is invalid: {target.get('path')}")
                    continue
                command = build_kubectl_apply_command(kubectl or "kubectl", kubeconfig_path, target_path)
                target_record["command"] = command
                if args.dry_run:
                    target_record["success"] = True
                    target_record["dryRun"] = True
                else:
                    result = run_command(command)
                    log_path = logs_root / f"{deployment_id}.{target.get('stepId', 'apply')}.apply.log"
                    write_text(log_path, (result.get("stdout") or "") + (("\n" + result.get("stderr", "")) if result.get("stderr") else ""))
                    target_record.update({"success": result["success"], "exitCode": result["exitCode"], "logPath": rel_or_abs(log_path, repo_root)})
                    if not result["success"] and target.get("required", True):
                        errors.append(f"Kubernetes apply failed for target: {target.get('path')}")
                apply_results.append(target_record)

        if not errors and args.action == "deploy":
            namespace_to_tenant = (topology.get("namespaceResolution") or {}).get("namespaceToTenant") or {}
            primary_tenant_id = namespace_to_tenant.get(namespace) or "primary"
            rollout_targets: List[Dict[str, Any]] = [{
                "tenantId": primary_tenant_id,
                "namespace": namespace,
                "deployments": topology.get("expectedResources", {}).get("deployments", []),
                "rolloutTimeoutSeconds": int(topology.get("expectedResources", {}).get("rolloutTimeoutSeconds", 600)),
            }]
            for item in topology.get("additionalRolloutTargets", []) or []:
                item_namespace = item.get("namespace") or namespace
                rollout_targets.append({
                    "tenantId": item.get("tenantId") or namespace_to_tenant.get(str(item_namespace)) or item_namespace or "co-tenant",
                    "namespace": item_namespace,
                    "deployments": item.get("deployments") or [],
                    "rolloutTimeoutSeconds": int(item.get("rolloutTimeoutSeconds") or topology.get("expectedResources", {}).get("rolloutTimeoutSeconds", 600)),
                })
            for target in rollout_targets:
                target_namespace = target["namespace"]
                timeout_seconds = int(target["rolloutTimeoutSeconds"])
                for deployment in target.get("deployments", []):
                    command = kubectl_base(kubectl or "kubectl", kubeconfig_path) + ["-n", target_namespace, "rollout", "status", f"deployment/{deployment}", f"--timeout={timeout_seconds}s"]
                    record = {"tenantId": target.get("tenantId"), "namespace": target_namespace, "deployment": deployment, "command": command}
                    if args.dry_run:
                        record.update({"success": True, "dryRun": True})
                    else:
                        result = run_command(command, timeout=timeout_seconds + 30)
                        safe_namespace = safe_namespace_token(target_namespace)
                        log_path = logs_root / f"{deployment_id}.{safe_namespace}.{deployment}.rollout.log"
                        write_text(log_path, (result.get("stdout") or "") + (("\n" + result.get("stderr", "")) if result.get("stderr") else ""))
                        record.update({"success": result["success"], "exitCode": result["exitCode"], "logPath": rel_or_abs(log_path, repo_root)})
                        if not result["success"]:
                            errors.append(f"Rollout check failed for deployment/{deployment} in namespace {target_namespace}.")
                    rollout_results.append(record)

        if errors and args.action == "deploy" and not args.dry_run and not snapshot_results:
            snapshot_results = capture_snapshots(kubectl or "kubectl", kubeconfig_path, snapshot_namespaces, namespace, snapshots_root, deployment_id)

        if not errors and args.action in {"deploy", "smoke"}:
            if args.dry_run:
                smoke_result = {"enabled": bool(profile.get("smokeValidation", {}).get("enabled", True)), "status": "dry_run", "passed": True}
            else:
                if args.action == "deploy" and not snapshot_results:
                    snapshot_results = capture_snapshots(kubectl or "kubectl", kubeconfig_path, snapshot_namespaces, namespace, snapshots_root, deployment_id)
                smoke_result = run_smoke_validation(repo_root, profile, kubeconfig_path, logs_root, deployment_id)
                write_json(output_root / f"{deployment_id}.smoke-result.json", smoke_result)
                latest_smoke = (output_root / "latest-localai-smoke-result.json") if explicit_output_root else repo_path(repo_root, artifact_policy.get("latestSmokeResultPath"))
                if latest_smoke and (args.write_latest_aliases or artifact_policy.get("writeLatestAliases")):
                    write_json(latest_smoke, smoke_result)
                if profile.get("smokeValidation", {}).get("enabled", True) and not smoke_result.get("passed"):
                    errors.append("LocalAI smoke validation failed.")

        if args.action == "plan":
            status = "planned" if not errors else "failed"
        elif args.dry_run:
            status = "dry_run" if not errors else "failed"
        elif args.action == "smoke" and not errors:
            status = "smoke_validated"
        elif args.action == "deploy" and not errors:
            status = "deployed"
        else:
            status = "failed"

        accepted_statuses = profile.get("decisionPolicy", {}).get("acceptedStatusesBeforeBenchmarking", ["deployed", "smoke_validated"])
        can_proceed = bool(status in accepted_statuses and not errors)
        unsupported_reason = None
        if not can_proceed:
            if any("Rollout check failed" in str(error) for error in errors):
                unsupported_reason = "unsupported_due_to_rollout_timeout"
            elif any("Kubernetes apply failed" in str(error) for error in errors):
                unsupported_reason = "unsupported_due_to_kubernetes_apply_failure"
            elif any("smoke validation failed" in str(error).lower() for error in errors):
                unsupported_reason = "unsupported_due_to_smoke_validation_failure"
            elif errors:
                unsupported_reason = "unsupported_due_to_application_deployment_failure"
            else:
                unsupported_reason = "unsupported_due_to_application_not_benchmark_ready"
        manifest_path = manifests_root / f"{deployment_id}.localai-deployment-manifest.json"
        summary_path = manifests_root / f"{deployment_id}.localai-deployment-summary.txt"
        manifest = {
            "schemaVersion": "provider-backed-localai-deployment-manifest/v1",
            "deploymentRunId": deployment_id,
            "status": status,
            "action": args.action,
            "startedAtUtc": started_at,
            "finishedAtUtc": utc_now(),
            "dryRun": args.dry_run,
            "cycle": {"cycleId": cycle.get("cycleId"), "cycleName": cycle.get("cycleName"), "cycleConfigPath": rel_or_abs(cycle_path, repo_root)},
            "baseline": {"baselineId": profile.get("baselineId"), "baselinePath": rel_or_abs(baseline_path, repo_root), "baselineLoaded": baseline is not None},
            "scenario": {
                "scenarioId": profile.get("scenarioId"),
                "variantId": profile.get("variantId"),
                "scenarioConfigPath": profile.get("scenarioConfigPath"),
                "referenceBaselineId": profile.get("referenceBaselineId") or profile.get("baselineId"),
                "referenceBaselineConfigPath": profile.get("referenceBaselineConfigPath") or profile.get("baselineConfigPath"),
                "referenceScenarioId": profile.get("referenceScenarioId"),
                "referenceScenarioConfigPath": profile.get("referenceScenarioConfigPath"),
            },
            "applicationDeploymentProfile": {"profileId": profile.get("applicationDeploymentProfileId"), "profilePath": rel_or_abs(profile_path, repo_root)},
            "infrastructure": {"infrastructureProfileId": profile.get("infrastructureProfileId"), "infrastructureProfilePath": profile.get("infrastructureProfilePath")},
            "provider": {"providerId": profile.get("providerId")},
            "clusterValidation": {"clusterValidationProfileId": profile.get("clusterValidationProfileId"), "clusterValidationProfilePath": profile.get("clusterValidationProfilePath")},
            "clusterAccess": {"kubeconfigPath": rel_or_abs(kubeconfig_path, repo_root), "kubeconfigExists": bool(kubeconfig_path and kubeconfig_path.exists())},
            "preDeploymentGate": pre_gate,
            "deploymentTopology": topology,
            "placementProfile": {
                "placementProfileId": placement_profile_status.get("placementProfileId"),
                "placementProfilePath": rel_or_abs(placement_profile_path, repo_root),
                "loaded": placement_profile is not None,
                "status": placement_profile_status.get("status"),
                "strategy": placement_profile_status.get("strategy"),
                "profileStatus": placement_profile_status.get("profileStatus"),
                "researchQuestion": placement_profile_status.get("researchQuestion"),
                "canUseForDeployment": placement_profile_status.get("canUseForDeployment"),
                "errorCount": placement_profile_status.get("errorCount"),
                "warningCount": placement_profile_status.get("warningCount"),
                "checks": placement_profile_status.get("checks"),
                "infrastructureContext": placement_profile_status.get("infrastructureContext"),
                "workerNodeMappingSelection": placement_profile_status.get("workerNodeMappingSelection"),
                "mappingSemantics": placement_profile_status.get("mappingSemantics"),
            },
            "kubernetesApply": apply_results,
            "rolloutChecks": rollout_results,
            "snapshots": snapshot_results,
            "smokeValidation": smoke_result,
            "artifacts": {"outputRoot": rel_or_abs(output_root, repo_root), "logsRoot": rel_or_abs(logs_root, repo_root), "manifestsRoot": rel_or_abs(manifests_root, repo_root), "snapshotsRoot": rel_or_abs(snapshots_root, repo_root), "manifestPath": rel_or_abs(manifest_path, repo_root), "summaryPath": rel_or_abs(summary_path, repo_root)},
            "decision": {
                "canProceedToBenchmark": can_proceed,
                "acceptedStatusesBeforeBenchmarking": accepted_statuses,
                "reason": "localai_deployment_ready" if can_proceed else "localai_deployment_not_ready",
                "unsupportedReason": unsupported_reason,
                "stopBeforeBenchmark": not can_proceed,
            },
            "errors": errors,
        }
        write_json(manifest_path, manifest)
        write_text(summary_path, build_summary(manifest))
        if args.write_latest_aliases or artifact_policy.get("writeLatestAliases"):
            if explicit_output_root:
                latest_manifest = output_root / "latest-localai-deployment-manifest.json"
                latest_summary = output_root / "latest-localai-deployment-summary.txt"
            else:
                latest_manifest = repo_path(repo_root, artifact_policy.get("latestManifestPath"))
                latest_summary = repo_path(repo_root, artifact_policy.get("latestTextSummaryPath"))
            if latest_manifest:
                write_json(latest_manifest, manifest)
            if latest_summary:
                write_text(latest_summary, build_summary(manifest))

        print(f"LocalAI deployment status: {status}")
        print(f"Manifest: {manifest_path}")
        print(f"Summary: {summary_path}")
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        return 0 if can_proceed or args.dry_run or args.action == "plan" else 1

    except Exception as exc:
        failure_root = repo_root / "results" / "_runtime" / "localai-deployment-failures"
        failure_root.mkdir(parents=True, exist_ok=True)
        failure_path = failure_root / f"{deployment_id}.failure.json"
        write_json(failure_path, {"schemaVersion": "provider-backed-localai-deployment-failure/v1", "deploymentRunId": deployment_id, "status": "failed", "startedAtUtc": started_at, "finishedAtUtc": utc_now(), "error": str(exc)})
        print(f"LocalAI deployment failed before cycle-scoped artifact resolution: {exc}", file=sys.stderr)
        print(f"Failure artifact: {failure_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
