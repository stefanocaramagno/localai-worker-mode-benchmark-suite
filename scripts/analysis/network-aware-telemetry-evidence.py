#!/usr/bin/env python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

DEFAULT_COMPONENT_ARTIFACT_NAMES: dict[str, list[str]] = {
    "monAgent": ["latest-mon-agent-manifest.json", "latest-mon-agent-validation-snapshot.json"],
    "mentat": ["latest-mentat-observability-manifest.json", "latest-mentat-validation-snapshot.json"],
    "istio": ["latest-istio-gateway-manifest.json"],
    "rescheduling": ["latest-rescheduling-manifest.json", "latest-pre-redeployment-snapshot.json"],
    "clusterLens": ["cluster-lens-placement-summary.json", "cluster-lens-capture-manifest.json"],
}

DEFAULT_ACCEPTED_STATUSES: dict[str, set[str]] = {
    "monAgent": {"applied", "captured", "validated"},
    "mentat": {"captured", "validated"},
    "istio": {"validated"},
    "rescheduling": {"captured", "validated", "executed"},
    "clusterLens": {"captured", "partial"},
}


def _repo_path(repo_root: Path, value: str | None) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else repo_root / path


def _safe_relpath(path: Path | None, repo_root: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _load_json_optional(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "path_not_declared"
    if not path.is_file():
        return None, "missing"
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return None, "not_json_object"
        return payload, None
    except Exception as exc:
        return None, f"invalid_json:{exc}"


def _get_nested(payload: Any, dotted_path: str, default: Any = None) -> Any:
    current = payload
    for part in dotted_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def _first_json_by_name(root: Path, names: Iterable[str]) -> tuple[Path | None, dict[str, Any] | None, str | None]:
    candidates: list[Path] = []
    if root.is_dir():
        for name in names:
            candidates.append(root / name)
        for name in names:
            candidates.extend(sorted(root.rglob(name)))
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.as_posix()
        if key in seen:
            continue
        seen.add(key)
        payload, error = _load_json_optional(candidate)
        if payload is not None:
            return candidate, payload, None
        if error not in {"missing", "path_not_declared"}:
            return candidate, None, error
    return None, None, "missing"


def _component_status(component: str, payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    if status is None and component == "rescheduling":
        status = payload.get("actionStatus")
    if status is None and component == "clusterLens":
        status = payload.get("captureStatus")
    return str(status) if status is not None else None


def _annotation_key_set(items: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for item in items:
        annotations = item.get("annotations") if isinstance(item.get("annotations"), dict) else {}
        keys.update(str(key) for key in annotations.keys())
        keys.update(str(key) for key in item.get("annotationKeys") or [])
    return keys


def _missing_prefixes(keys: set[str], prefixes: Iterable[str]) -> list[str]:
    missing: list[str] = []
    for prefix in prefixes:
        p = str(prefix)
        if p and not any(key.startswith(p) for key in keys):
            missing.append(p)
    return missing


def _is_master_deployment(item: dict[str, Any]) -> bool:
    labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}
    role = str(labels.get("role") or labels.get("localai.benchmark/role") or "").lower()
    name = str(item.get("name") or "").lower()
    return role == "master" or "server" in name or "master" in name


def gateway_key_status(snapshot: dict[str, Any], required_key: str | None) -> dict[str, Any]:
    deployments = [item for item in snapshot.get("deploymentChecks") or [] if isinstance(item, dict)]
    relevant = [item for item in deployments if _is_master_deployment(item)] or deployments
    required_key = str(required_key or "").strip()
    if not required_key:
        return {"requiredGatewayTrafficKey": None, "requiredGatewayTrafficKeyPresent": True, "relevantDeploymentCount": len(relevant), "checkedDeployments": []}
    checked: list[dict[str, Any]] = []
    present_count = 0
    for item in relevant:
        annotations = item.get("annotations") if isinstance(item.get("annotations"), dict) else {}
        value = annotations.get(required_key)
        explicit_present = item.get("requiredGatewayTrafficKeyPresent")
        present = bool(explicit_present) if explicit_present is not None else bool(str(value or "").strip())
        if present:
            present_count += 1
        checked.append({
            "namespace": item.get("namespace"),
            "name": item.get("name"),
            "role": (item.get("labels") or {}).get("role") if isinstance(item.get("labels"), dict) else None,
            "requiredGatewayTrafficKeyPresent": present,
            "requiredGatewayTrafficValue": item.get("requiredGatewayTrafficValue") if item.get("requiredGatewayTrafficValue") is not None else value,
            "missingRequiredAnnotations": item.get("missingRequiredAnnotations") or [],
        })
    return {
        "requiredGatewayTrafficKey": required_key,
        "requiredGatewayTrafficKeyPresent": present_count > 0,
        "presentDeploymentCount": present_count,
        "relevantDeploymentCount": len(relevant),
        "checkedDeployments": checked,
    }


def latency_matrix_status(snapshot: dict[str, Any], latency_profile_id: str | None) -> dict[str, Any]:
    validation = snapshot.get("annotationControlledLatencyMatrixValidation")
    if not isinstance(validation, dict):
        validation = {}
    status = str(validation.get("status") or "missing")
    latency_id = str(latency_profile_id or _get_nested(snapshot, "runtimeScenarioContext.latencyProfileId") or "").upper()
    required = latency_id in {"L1_INTER_GROUP_MODERATE", "L2_INTER_GROUP_HIGH", "L3_INTER_GROUP_EXTREME"}
    if not required and status in {"missing", "skipped"}:
        accepted = True
    else:
        accepted = status == "validated"
    return {
        "latencyProfileId": latency_id or None,
        "required": required,
        "status": status,
        "accepted": accepted,
        "checkedPairCount": validation.get("checkedPairCount"),
        "failedPairCount": validation.get("failedPairCount"),
        "reason": validation.get("reason"),
    }


def telemetry_root_for_scenario(repo_root: Path, profile: dict[str, Any], scenario_id: str) -> Path:
    roots = profile.get("networkAwareTelemetryEvidenceRoots") or {}
    policy = profile.get("networkAwareTelemetryEvidencePolicy") or {}
    variant_root_value = roots.get("variantEvidenceRoot") or policy.get("variantEvidenceRoot")
    if not variant_root_value:
        cycle_id = str(profile.get("cycleId") or profile.get("cycle") or "").strip()
        if cycle_id:
            variant_root_value = f"results/experimental-cycles/{cycle_id}/variants"
    variant_root = _repo_path(repo_root, variant_root_value)
    if variant_root is None:
        variant_root = repo_root / "results" / "experimental-cycles" / "variants"
    return variant_root / scenario_id / "network-aware-scheduler"



def _cluster_lens_root(telemetry_root: Path) -> Path:
    return telemetry_root / "cluster-lens"


def _csv_row_count(path: Path | None) -> int | None:
    if path is None or not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            line_count = sum(1 for _ in handle)
        return max(0, line_count - 1)
    except Exception:
        return None


def _scheduler_role_from_scenario(scenario: dict[str, Any] | None, scenario_id: str | None = None) -> str:
    scenario = scenario or {}
    policy = scenario.get("networkAwareSchedulerPolicy") if isinstance(scenario.get("networkAwareSchedulerPolicy"), dict) else {}
    if not policy:
        policy = scenario.get("schedulerModePolicy") if isinstance(scenario.get("schedulerModePolicy"), dict) else {}
    mode = str(
        scenario.get("schedulerMode")
        or scenario.get("schedulerModeRole")
        or policy.get("schedulerMode")
        or policy.get("schedulerModeRole")
        or scenario.get("variantId")
        or scenario.get("scenarioId")
        or scenario_id
        or ""
    ).lower()
    if "netaware" in mode or "network" in mode:
        return "netaware"
    if "loadaware" in mode or "load" in mode:
        return "loadaware"
    if "default" in mode or "kubernetes" in mode:
        return "default"
    return "unknown"


def _cluster_lens_primary_stage(policy: dict[str, Any] | None, scenario: dict[str, Any] | None = None) -> str:
    policy = policy or {}
    stage_policy = {}
    for key in ("clusterLensPrimaryStagePolicy", "networkAwareReportingPolicy", "networkAwareTelemetryEvidencePolicy"):
        candidate = policy.get(key) if isinstance(policy.get(key), dict) else {}
        if key in {"networkAwareReportingPolicy", "networkAwareTelemetryEvidencePolicy"}:
            candidate = candidate.get("clusterLensPrimaryStagePolicy") if isinstance(candidate.get("clusterLensPrimaryStagePolicy"), dict) else {}
        if isinstance(candidate, dict) and candidate:
            stage_policy = candidate
            break
    role = _scheduler_role_from_scenario(scenario, (scenario or {}).get("scenarioId") if isinstance(scenario, dict) else None)
    if role == "default":
        return str(stage_policy.get("default") or "pre-benchmark")
    if role == "loadaware":
        return str(stage_policy.get("loadaware") or "post-rescheduling")
    if role == "netaware":
        return str(stage_policy.get("netaware") or "post-rescheduling")
    return str(stage_policy.get("defaultStage") or "post-rescheduling")


def _cluster_lens_fallback_stages(policy: dict[str, Any] | None) -> list[str]:
    policy = policy or {}
    stage_policy = {}
    for key in ("clusterLensPrimaryStagePolicy", "networkAwareReportingPolicy", "networkAwareTelemetryEvidencePolicy"):
        candidate = policy.get(key) if isinstance(policy.get(key), dict) else {}
        if key in {"networkAwareReportingPolicy", "networkAwareTelemetryEvidencePolicy"}:
            candidate = candidate.get("clusterLensPrimaryStagePolicy") if isinstance(candidate.get("clusterLensPrimaryStagePolicy"), dict) else {}
        if isinstance(candidate, dict) and candidate:
            stage_policy = candidate
            break
    stages = stage_policy.get("fallbackStages") if isinstance(stage_policy.get("fallbackStages"), list) else []
    if stages:
        return [str(stage) for stage in stages if str(stage).strip()]
    return ["post-rescheduling", "pre-benchmark", "post-benchmark", "post-telemetry-priming", "post-deployment", "pre-rescheduling"]


def _load_cluster_lens_artifact_set(root: Path, repo_root: Path) -> tuple[Path, dict[str, Any] | None, str | None, dict[str, Any] | None, str | None]:
    summary_path = root / "cluster-lens-placement-summary.json"
    manifest_path = root / "cluster-lens-capture-manifest.json"
    summary, summary_error = _load_json_optional(summary_path)
    manifest, manifest_error = _load_json_optional(manifest_path)
    return root, summary, None if summary is not None else summary_error, manifest, None if manifest is not None else manifest_error


def _cluster_lens_candidate_roots(root: Path, primary_stage: str, fallback_stages: list[str]) -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = [(root, "primary_root")]
    if primary_stage:
        candidates.append((root / "stages" / primary_stage, "configured_primary_stage"))
    for stage in fallback_stages:
        stage = str(stage or "").strip()
        if not stage or stage == primary_stage:
            continue
        candidates.append((root / "stages" / stage, "fallback_stage"))
    seen: set[str] = set()
    unique: list[tuple[Path, str]] = []
    for item in candidates:
        key = item[0].as_posix()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _tenant_placement_rows(placement: dict[str, Any]) -> list[dict[str, Any]]:
    tenants = placement.get("tenants") if isinstance(placement.get("tenants"), dict) else {}
    rows: list[dict[str, Any]] = []
    for tenant_id, item in sorted(tenants.items()):
        if not isinstance(item, dict):
            continue
        rows.append({
            "tenant": str(tenant_id),
            "namespaces": item.get("namespaces") or [],
            "podCount": item.get("podCount"),
            "masterNodes": item.get("masterNodes") or [],
            "workerNodes": item.get("workerNodes") or [],
            "distinctTenantNodes": item.get("distinctTenantNodes"),
            "masterWorkerCoLocated": item.get("masterWorkerCoLocated"),
            "unscheduledPods": item.get("unscheduledPods") or [],
            "schedulerNames": item.get("schedulerNames") or [],
        })
    return rows


def cluster_lens_placement_evidence(
    repo_root: Path,
    telemetry_root: Path,
    scenario: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = _cluster_lens_root(telemetry_root)
    primary_stage = _cluster_lens_primary_stage(policy, scenario)
    fallback_stages = _cluster_lens_fallback_stages(policy)

    selected_root: Path | None = None
    summary: dict[str, Any] | None = None
    manifest: dict[str, Any] | None = None
    summary_error: str | None = "missing"
    manifest_error: str | None = "missing"
    selection_reason = "missing"

    for candidate_root, reason in _cluster_lens_candidate_roots(root, primary_stage, fallback_stages):
        if not candidate_root.exists():
            continue
        candidate_summary_path = candidate_root / "cluster-lens-placement-summary.json"
        candidate_manifest_path = candidate_root / "cluster-lens-capture-manifest.json"
        candidate_signature_path = candidate_root / "cluster-lens-placement-signature.csv"
        if not (candidate_summary_path.is_file() or candidate_manifest_path.is_file() or candidate_signature_path.is_file()):
            continue
        selected_root, summary, summary_error, manifest, manifest_error = _load_cluster_lens_artifact_set(candidate_root, repo_root)
        selection_reason = reason
        break

    if selected_root is None:
        summary_path, summary, summary_error = _first_json_by_name(root, ["cluster-lens-placement-summary.json"])
        manifest_path, manifest, manifest_error = _first_json_by_name(root, ["cluster-lens-capture-manifest.json"])
        selected_root = summary_path.parent if summary_path is not None else (manifest_path.parent if manifest_path is not None else root)
        selection_reason = "recursive_fallback" if summary_path is not None or manifest_path is not None else "missing"

    raw_snapshot_path = selected_root / "cluster-lens-snapshot.json"
    pods_path = selected_root / "cluster-lens-kubernetes-pods.json"
    deployments_path = selected_root / "cluster-lens-kubernetes-deployments.json"
    nodes_path = selected_root / "cluster-lens-kubernetes-nodes.json"
    signature_path = selected_root / "cluster-lens-placement-signature.csv"
    summary_path = selected_root / "cluster-lens-placement-summary.json"
    manifest_path = selected_root / "cluster-lens-capture-manifest.json"

    status = _component_status("clusterLens", summary)
    validation = summary.get("validation") if isinstance(summary, dict) and isinstance(summary.get("validation"), dict) else {}
    placement = summary.get("placement") if isinstance(summary, dict) and isinstance(summary.get("placement"), dict) else {}
    cluster_lens = summary.get("clusterLens") if isinstance(summary, dict) and isinstance(summary.get("clusterLens"), dict) else {}
    kubernetes = summary.get("kubernetesSnapshots") if isinstance(summary, dict) and isinstance(summary.get("kubernetesSnapshots"), dict) else {}
    output = summary.get("output") if isinstance(summary, dict) and isinstance(summary.get("output"), dict) else {}
    counts = placement.get("counts") if isinstance(placement.get("counts"), dict) else {}
    localai_pod_count = placement.get("localAiPodCount") if placement.get("localAiPodCount") is not None else counts.get("localAiPodCount")
    signature_row_count = _csv_row_count(signature_path)
    available = summary is not None or manifest is not None or signature_path.is_file()
    return {
        "available": available,
        "status": status or ("missing" if not available else "unknown"),
        "complete": bool(summary is not None and validation.get("success") is True and signature_path.is_file()),
        "clusterLensRoot": _safe_relpath(root, repo_root),
        "selectedArtifactRoot": _safe_relpath(selected_root, repo_root),
        "primaryStage": primary_stage,
        "stageSelection": selection_reason,
        "summaryPath": _safe_relpath(summary_path if summary_path.is_file() else None, repo_root),
        "summaryLoadError": None if summary_path.is_file() else summary_error,
        "captureManifestPath": _safe_relpath(manifest_path if manifest_path.is_file() else None, repo_root),
        "captureManifestLoadError": None if manifest_path.is_file() else manifest_error,
        "rawSnapshotPath": _safe_relpath(raw_snapshot_path if raw_snapshot_path.is_file() else None, repo_root),
        "podsSnapshotPath": _safe_relpath(pods_path if pods_path.is_file() else None, repo_root),
        "deploymentsSnapshotPath": _safe_relpath(deployments_path if deployments_path.is_file() else None, repo_root),
        "nodesSnapshotPath": _safe_relpath(nodes_path if nodes_path.is_file() else None, repo_root),
        "placementSignaturePath": _safe_relpath(signature_path if signature_path.is_file() else None, repo_root),
        "placementSignatureRowCount": signature_row_count,
        "captureStage": summary.get("captureStage") if isinstance(summary, dict) else (manifest.get("captureStage") if isinstance(manifest, dict) else None),
        "validationSuccess": validation.get("success"),
        "validationErrors": validation.get("errors") or [],
        "snapshotCaptured": cluster_lens.get("snapshotCaptured"),
        "rawNodeCount": cluster_lens.get("rawNodeCount"),
        "rawPodCount": cluster_lens.get("rawPodCount"),
        "rawNodeEdgeCount": cluster_lens.get("rawNodeEdgeCount"),
        "rawAppEdgeCount": cluster_lens.get("rawAppEdgeCount"),
        "kubernetesPodCount": kubernetes.get("podCount"),
        "kubernetesDeploymentCount": kubernetes.get("deploymentCount"),
        "kubernetesNodeCount": kubernetes.get("nodeCount"),
        "localAiPodCount": localai_pod_count,
        "scheduledLocalAiPodCount": counts.get("scheduledLocalAiPodCount"),
        "unscheduledLocalAiPodCount": counts.get("unscheduledLocalAiPodCount"),
        "distinctObservedNodes": counts.get("distinctObservedNodes"),
        "observedSchedulerNames": counts.get("observedSchedulerNames") or [],
        "tenantCount": len((placement.get("tenants") or {}) if isinstance(placement.get("tenants"), dict) else {}),
        "tenantPlacements": _tenant_placement_rows(placement),
        "output": output,
    }


def collect_network_aware_telemetry_for_scenario(
    repo_root: Path,
    profile: dict[str, Any],
    scenario_id: str,
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scenario = scenario or {}
    policy = profile.get("networkAwareTelemetryEvidencePolicy") or {}
    required_node_prefixes = list(policy.get("requiredNodeAnnotationPrefixes") or ["network-latency.", "packet-loss.", "network-bandwidth."])
    required_deployment_prefixes = list(policy.get("requiredDeploymentAnnotationPrefixes") or ["traffic."])
    required_gateway_key = str(policy.get("requiredGatewayTrafficKey") or policy.get("gatewayTrafficKey") or "traffic.localai-gateway-istio")
    component_names = policy.get("componentArtifactNames") or DEFAULT_COMPONENT_ARTIFACT_NAMES
    accepted_statuses = {component: set(values) for component, values in DEFAULT_ACCEPTED_STATUSES.items()}
    for component, values in (policy.get("componentAcceptedStatuses") or {}).items():
        accepted_statuses[str(component)] = {str(value) for value in values}

    telemetry_root = telemetry_root_for_scenario(repo_root, profile, scenario_id)
    component_records: dict[str, Any] = {}
    components_ok: list[str] = []
    missing_components: list[str] = []
    rescheduling_manifest: dict[str, Any] = {}
    pre_snapshot: dict[str, Any] = {}

    for component, names in component_names.items():
        names = [str(name) for name in (names if isinstance(names, list) else [names])]
        component_dir = telemetry_root / str(component).replace("monAgent", "mon-agent")
        if component == "rescheduling":
            component_dir = telemetry_root / "rescheduling"
        elif component == "mentat":
            component_dir = telemetry_root / "mentat"
        elif component == "istio":
            component_dir = telemetry_root / "istio"
        elif component == "clusterLens":
            component_dir = telemetry_root / "cluster-lens"
        path, payload, error = _first_json_by_name(component_dir, names)
        status = _component_status(str(component), payload)
        accepted = bool(payload is not None and status in accepted_statuses.get(str(component), set()))
        if accepted:
            components_ok.append(str(component))
        else:
            missing_components.append(str(component))
        component_records[str(component)] = {
            "componentRoot": _safe_relpath(component_dir, repo_root),
            "artifactNames": names,
            "artifactPath": _safe_relpath(path, repo_root),
            "loadError": error,
            "status": status,
            "acceptedStatuses": sorted(accepted_statuses.get(str(component), set())),
            "accepted": accepted,
        }
        if component == "rescheduling" and isinstance(payload, dict):
            rescheduling_manifest = payload
            pre_snapshot = payload.get("preRedeploymentSnapshot") if isinstance(payload.get("preRedeploymentSnapshot"), dict) else {}

    if not pre_snapshot:
        path, payload, error = _first_json_by_name(telemetry_root / "rescheduling", ["latest-pre-redeployment-snapshot.json"])
        if isinstance(payload, dict):
            pre_snapshot = payload
            component_records.setdefault("reschedulingPreSnapshot", {})
            component_records["reschedulingPreSnapshot"] = {"artifactPath": _safe_relpath(path, repo_root), "loadError": error, "available": True}

    node_keys = _annotation_key_set([item for item in pre_snapshot.get("nodeChecks") or [] if isinstance(item, dict)])
    deployment_items = [item for item in pre_snapshot.get("deploymentChecks") or [] if isinstance(item, dict)]
    deployment_keys = _annotation_key_set(deployment_items)
    gateway = gateway_key_status(pre_snapshot, required_gateway_key)
    latency_profile_id = scenario.get("latencyProfileId") or _get_nested(pre_snapshot, "runtimeScenarioContext.latencyProfileId")
    matrix = latency_matrix_status(pre_snapshot, latency_profile_id)
    cluster_lens = cluster_lens_placement_evidence(repo_root, telemetry_root, scenario=scenario, policy=profile)
    require_cluster_lens = bool(policy.get("requireClusterLensPlacementEvidence", "clusterLens" in component_names))
    missing_node_prefixes = _missing_prefixes(node_keys, required_node_prefixes)
    missing_deployment_prefixes = _missing_prefixes(deployment_keys, required_deployment_prefixes)

    status = "complete"
    reasons: list[str] = []
    if missing_components:
        status = "incomplete"
        reasons.append("missing_or_unaccepted_components:" + ",".join(sorted(missing_components)))
    if missing_node_prefixes:
        status = "incomplete"
        reasons.append("missing_node_annotation_prefixes:" + ",".join(missing_node_prefixes))
    if missing_deployment_prefixes:
        status = "incomplete"
        reasons.append("missing_deployment_annotation_prefixes:" + ",".join(missing_deployment_prefixes))
    if not gateway.get("requiredGatewayTrafficKeyPresent"):
        status = "incomplete"
        reasons.append("missing_required_gateway_traffic_key")
    if not matrix.get("accepted"):
        status = "incomplete"
        reasons.append("latency_matrix_validation_not_accepted")
    if require_cluster_lens and not cluster_lens.get("complete"):
        status = "incomplete"
        reasons.append("cluster_lens_placement_evidence_incomplete")

    return {
        "schemaVersion": "network-aware-telemetry-evidence/v1",
        "scenarioId": scenario_id,
        "status": status,
        "complete": status == "complete",
        "reasons": reasons,
        "telemetryRoot": _safe_relpath(telemetry_root, repo_root),
        "components": component_records,
        "componentsAccepted": sorted(components_ok),
        "componentsMissingOrRejected": sorted(missing_components),
        "gatewayTrafficKey": required_gateway_key,
        "gatewayTrafficKeyEvidence": gateway,
        "requiredNodeAnnotationPrefixes": required_node_prefixes,
        "missingNodeAnnotationPrefixes": missing_node_prefixes,
        "requiredDeploymentAnnotationPrefixes": required_deployment_prefixes,
        "missingDeploymentAnnotationPrefixes": missing_deployment_prefixes,
        "latencyMatrixValidation": matrix,
        "clusterLensPlacementEvidence": cluster_lens,
        "reschedulingStatus": rescheduling_manifest.get("status") if isinstance(rescheduling_manifest, dict) else None,
    }


def collect_network_aware_telemetry_index(
    repo_root: Path,
    roots: Iterable[str],
    required_gateway_key: str | None = None,
    required_node_prefixes: Iterable[str] | None = None,
    required_deployment_prefixes: Iterable[str] | None = None,
    component_names: dict[str, list[str]] | None = None,
    require_cluster_lens: bool | None = None,
) -> dict[str, Any]:
    base_policy = {
        "requiredGatewayTrafficKey": required_gateway_key or "traffic.localai-gateway-istio",
        "requiredNodeAnnotationPrefixes": list(required_node_prefixes or ["network-latency.", "packet-loss.", "network-bandwidth."]),
        "requiredDeploymentAnnotationPrefixes": list(required_deployment_prefixes or ["traffic."]),
        "componentArtifactNames": component_names or DEFAULT_COMPONENT_ARTIFACT_NAMES,
    }
    if require_cluster_lens is not None:
        base_policy["requireClusterLensPlacementEvidence"] = bool(require_cluster_lens)
    scenario_records: dict[str, Any] = {}
    missing_roots: list[str] = []
    for root_value in roots:
        root = _repo_path(repo_root, root_value)
        if root is None or not root.exists():
            missing_roots.append(str(root_value))
            continue
        scenario_profile = {
            "networkAwareTelemetryEvidenceRoots": {"variantEvidenceRoot": str(root_value)},
            "networkAwareTelemetryEvidencePolicy": dict(base_policy),
        }
        for variant_dir in sorted(item for item in root.iterdir() if item.is_dir()):
            telemetry_root = variant_dir / "network-aware-scheduler"
            if not telemetry_root.is_dir():
                continue
            scenario_id = variant_dir.name
            scenario_records[scenario_id] = collect_network_aware_telemetry_for_scenario(repo_root, scenario_profile, scenario_id, {})
    complete = [sid for sid, item in scenario_records.items() if item.get("complete")]
    incomplete = {sid: item.get("reasons") for sid, item in scenario_records.items() if not item.get("complete")}
    return {
        "scenarioCount": len(scenario_records),
        "completeScenarioCount": len(complete),
        "completeScenarioIds": complete,
        "incompleteScenarios": incomplete,
        "missingRoots": sorted(set(missing_roots)),
        "scenarios": scenario_records,
    }
