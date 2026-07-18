#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
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


def load_cycle(repo_root: Path, cycle_config: Optional[str]) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
    if not cycle_config:
        return None, None
    cycle_path = repo_path(repo_root, cycle_config)
    if cycle_path is None or not cycle_path.exists():
        raise FileNotFoundError(f"Cycle profile not found: {cycle_config}")
    return cycle_path, read_json(cycle_path)


def load_application_deployment(repo_root: Path, value: Optional[str]) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
    if not value:
        return None, None
    profile_path = repo_path(repo_root, value)
    if profile_path is None or not profile_path.exists():
        raise FileNotFoundError(f"Application deployment profile not found: {value}")
    return profile_path, read_json(profile_path)


def load_index(repo_root: Path) -> Tuple[Path, Dict[str, Any]]:
    index_path = repo_root / "config" / "placement" / "PLACEMENT_PROFILES_INDEX.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Placement profiles index not found: {index_path}")
    return index_path, read_json(index_path)


def resolve_profile_from_index(repo_root: Path, placement_profile_id: str) -> Tuple[Path, Dict[str, Any]]:
    index_path, index = load_index(repo_root)
    for item in index.get("profiles", []):
        if item.get("placementProfileId") == placement_profile_id:
            profile_path = repo_path(repo_root, item.get("path"))
            if profile_path is None or not profile_path.exists():
                raise FileNotFoundError(f"Placement profile path does not exist for {placement_profile_id}: {item.get('path')}")
            return profile_path, read_json(profile_path)

    for alias in index.get("legacyPlacementScenarioAliases", []):
        if alias.get("legacyScenarioId") == placement_profile_id:
            canonical_id = alias.get("canonicalPlacementProfileId")
            if not canonical_id or canonical_id == placement_profile_id:
                break
            return resolve_profile_from_index(repo_root, canonical_id)

    raise ValueError(f"Placement profile not found in {rel_or_abs(index_path, repo_root)}: {placement_profile_id}")


def resolve_profile(repo_root: Path, args: argparse.Namespace, cycle: Optional[Dict[str, Any]], deployment: Optional[Dict[str, Any]]) -> Tuple[Path, Dict[str, Any]]:
    explicit_path = args.placement_profile_path
    explicit_id = args.placement_profile_id

    if explicit_path:
        profile_path = repo_path(repo_root, explicit_path)
        if profile_path is None or not profile_path.exists():
            raise FileNotFoundError(f"Placement profile path not found: {explicit_path}")
        return profile_path, read_json(profile_path)

    if explicit_id:
        return resolve_profile_from_index(repo_root, explicit_id)

    if deployment:
        placement = deployment.get("deploymentTopology", {}).get("placement", {})
        if placement.get("placementProfilePath"):
            profile_path = repo_path(repo_root, placement.get("placementProfilePath"))
            if profile_path is None or not profile_path.exists():
                raise FileNotFoundError(f"Placement profile declared by deployment profile not found: {placement.get('placementProfilePath')}")
            return profile_path, read_json(profile_path)
        if placement.get("placementProfileId"):
            return resolve_profile_from_index(repo_root, placement["placementProfileId"])

    if cycle:
        if cycle.get("placementProfiles", {}).get("baselinePlacementProfilePath"):
            profile_path = repo_path(repo_root, cycle["placementProfiles"]["baselinePlacementProfilePath"])
            if profile_path is None or not profile_path.exists():
                raise FileNotFoundError(f"Placement profile declared by cycle profile not found: {cycle['placementProfiles']['baselinePlacementProfilePath']}")
            return profile_path, read_json(profile_path)
        if cycle.get("placementProfiles", {}).get("baselinePlacementProfileId"):
            return resolve_profile_from_index(repo_root, cycle["placementProfiles"]["baselinePlacementProfileId"])

    _, index = load_index(repo_root)
    default_id = index.get("defaultBaselinePlacementProfileId")
    if not default_id:
        raise ValueError("No placement profile was provided and the index does not declare a default profile.")
    return resolve_profile_from_index(repo_root, default_id)


def validate_profile(repo_root: Path, profile_path: Path, profile: Dict[str, Any], deployment: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    def check(name: str, passed: bool, details: Optional[Dict[str, Any]] = None, severity: str = "error") -> None:
        checks.append({"name": name, "passed": bool(passed), "severity": severity, "details": details or {}})

    check("profile_id_present", bool(profile.get("placementProfileId")))
    check("strategy_present", bool(profile.get("strategy")))
    check("selector_policy_present", bool(profile.get("selectorPolicy")))
    check("worker_placement_present", bool(profile.get("workerPlacement")))

    kustomize = profile.get("kustomize", {})
    current_topology = kustomize.get("currentBaselineTopologyPath")
    if current_topology:
        topology_path = repo_path(repo_root, current_topology)
        check(
            "current_topology_path_exists",
            bool(topology_path and topology_path.exists()),
            {"path": current_topology, "resolvedPath": rel_or_abs(topology_path, repo_root) if topology_path else None}
        )
    else:
        check(
            "current_topology_path_declared",
            False,
            {"implementationStatus": kustomize.get("implementationStatus")},
            severity="warning"
        )

    legacy_composition_by_worker_count = kustomize.get("compositionByWorkerCount") or {}
    if legacy_composition_by_worker_count:
        check(
            "legacy_composition_by_worker_count_not_used",
            False,
            {
                "legacyField": "compositionByWorkerCount",
                "canonicalField": "compositionByApplicationWorkerCount",
                "legacyKeys": sorted(legacy_composition_by_worker_count.keys()),
            },
            severity="warning",
        )

    composition_maps = [
        ("compositionByApplicationWorkerCount", kustomize.get("compositionByApplicationWorkerCount") or legacy_composition_by_worker_count),
        ("compositionByInfrastructureWorkerCount", kustomize.get("compositionByInfrastructureWorkerCount") or {}),
    ]
    for map_name, mapping in composition_maps:
        for key, value in mapping.items():
            target_path = repo_path(repo_root, value)
            check(
                f"{map_name}_{key}_exists",
                bool(target_path and target_path.exists()),
                {"path": value, "resolvedPath": rel_or_abs(target_path, repo_root) if target_path else None}
            )

    if deployment:
        deployment_placement = deployment.get("deploymentTopology", {}).get("placement", {})
        declared_id = deployment_placement.get("placementProfileId")
        check(
            "deployment_profile_alignment",
            declared_id in (None, profile.get("placementProfileId")),
            {"deploymentPlacementProfileId": declared_id, "resolvedPlacementProfileId": profile.get("placementProfileId")}
        )
        worker_count = deployment.get("deploymentTopology", {}).get("workerCount", {}).get("scenarioId")
        if worker_count:
            by_count = profile.get("workerPlacement", {}).get("activeWorkerNodeMapByWorkerCount", {})
            check(
                "worker_count_mapping_available",
                worker_count in by_count,
                {"workerCountScenarioId": worker_count, "availableMappings": sorted(by_count.keys())},
                severity="warning" if worker_count not in by_count else "error"
            )

    errors = [item for item in checks if not item["passed"] and item["severity"] == "error"]
    warnings = [item for item in checks if not item["passed"] and item["severity"] == "warning"]
    return {
        "profilePath": rel_or_abs(profile_path, repo_root),
        "status": "valid" if not errors else "invalid",
        "checks": checks,
        "errorCount": len(errors),
        "warningCount": len(warnings),
        "canUseForDeployment": len(errors) == 0 and str(profile.get("kustomize", {}).get("implementationStatus", "")).startswith("active"),
        "warnings": warnings,
        "errors": errors,
    }


def build_summary(manifest: Dict[str, Any]) -> str:
    profile = manifest.get("placementProfile", {})
    validation = manifest.get("validation", {})
    lines = [
        "Placement profile resolution summary",
        "====================================",
        "",
        f"Resolution ID: {manifest.get('resolutionId')}",
        f"Status: {manifest.get('status')}",
        f"Placement profile: {profile.get('placementProfileId')}",
        f"Strategy: {profile.get('strategy')}",
        f"Profile status: {profile.get('status')}",
        f"Can use for deployment: {validation.get('canUseForDeployment')}",
        f"Validation errors: {validation.get('errorCount')}",
        f"Validation warnings: {validation.get('warningCount')}",
        "",
        "Research question:",
        profile.get("researchQuestion") or "",
        "",
        "Kustomize:",
        f"- Implementation status: {profile.get('kustomize', {}).get('implementationStatus')}",
        f"- Current topology path: {profile.get('kustomize', {}).get('currentBaselineTopologyPath')}",
    ]
    if validation.get("errors"):
        lines.extend(["", "Errors:"])
        for item in validation["errors"]:
            lines.append(f"- {item.get('name')}: {item.get('details')}")
    if validation.get("warnings"):
        lines.extend(["", "Warnings:"])
        for item in validation["warnings"]:
            lines.append(f"- {item.get('name')}: {item.get('details')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve and validate LocalAI placement profiles.")
    parser.add_argument("--repo-root", default=str(default_repo_root()))
    parser.add_argument("--cycle-config")
    parser.add_argument("--application-deployment-profile")
    parser.add_argument("--placement-profile-id")
    parser.add_argument("--placement-profile-path")
    parser.add_argument("--output-root", default="results/_runtime/placement-profile")
    parser.add_argument("--resolution-id")
    parser.add_argument("--write-latest-aliases", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    resolution_id = args.resolution_id or f"placement_profile_{compact_now()}"

    cycle_path, cycle = load_cycle(repo_root, args.cycle_config) if args.cycle_config else (None, None)
    deployment_path, deployment = load_application_deployment(repo_root, args.application_deployment_profile) if args.application_deployment_profile else (None, None)

    if cycle and not deployment:
        deployment_value = (
            cycle.get("pipelineProfiles", {}).get("applicationDeployment")
            or cycle.get("applicationDeployment", {}).get("applicationDeploymentProfilePath")
        )
        if deployment_value:
            deployment_path, deployment = load_application_deployment(repo_root, deployment_value)

    profile_path, profile = resolve_profile(repo_root, args, cycle, deployment)
    validation = validate_profile(repo_root, profile_path, profile, deployment)

    output_root = repo_path(repo_root, args.output_root) or (repo_root / "results" / "_runtime" / "placement-profile")
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / f"{resolution_id}.placement-profile-manifest.json"
    summary_path = output_root / f"{resolution_id}.placement-profile-summary.txt"

    manifest = {
        "schemaVersion": "placement-profile-resolution-manifest/v1",
        "resolutionId": resolution_id,
        "status": validation["status"],
        "startedAtUtc": utc_now(),
        "finishedAtUtc": utc_now(),
        "cycle": {"cycleId": cycle.get("cycleId") if cycle else None, "cycleConfigPath": rel_or_abs(cycle_path, repo_root)},
        "applicationDeployment": {
            "applicationDeploymentProfileId": deployment.get("applicationDeploymentProfileId") if deployment else None,
            "applicationDeploymentProfilePath": rel_or_abs(deployment_path, repo_root)
        },
        "placementProfile": {
            "placementProfileId": profile.get("placementProfileId"),
            "placementProfilePath": rel_or_abs(profile_path, repo_root),
            "status": profile.get("status"),
            "strategy": profile.get("strategy"),
            "researchQuestion": profile.get("researchQuestion"),
            "selectorPolicy": profile.get("selectorPolicy"),
            "serverPlacement": profile.get("serverPlacement"),
            "workerPlacement": profile.get("workerPlacement"),
            "kustomize": profile.get("kustomize"),
            "expectedTradeoffs": profile.get("expectedTradeoffs")
        },
        "validation": validation,
        "artifacts": {
            "manifestPath": rel_or_abs(manifest_path, repo_root),
            "summaryPath": rel_or_abs(summary_path, repo_root)
        }
    }

    write_json(manifest_path, manifest)
    write_text(summary_path, build_summary(manifest))

    if args.write_latest_aliases:
        write_json(output_root / "latest-placement-profile-manifest.json", manifest)
        write_text(output_root / "latest-placement-profile-summary.txt", build_summary(manifest))

    print(f"Placement profile status: {manifest['status']}")
    print(f"Manifest: {manifest_path}")
    print(f"Summary: {summary_path}")
    return 0 if manifest["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
