#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


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


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_artifact_payload_for_output(payload, path)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=4, ensure_ascii=False)
        handle.write("\n")


def resolve_repo_path(repo_root: Path, value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return repo_root / path


def path_exists(path: Optional[Path]) -> bool:
    return bool(path and path.exists())


def bool_arg(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def command_preview(tool_path: str, command: str, config_path: Optional[Path], confirm_delete: bool = False) -> Optional[str]:
    if config_path is None:
        return None
    if command == "create":
        return f"{tool_path} create -c {config_path.as_posix()}"
    if command == "kubeconfig":
        return f"{tool_path} kubeconfig -c {config_path.as_posix()}"
    if command == "delete":
        suffix = " --yes" if confirm_delete else ""
        return f"{tool_path} delete -c {config_path.as_posix()}{suffix}"
    if command == "template-create":
        return f"{tool_path} template create -c {config_path.as_posix()}"
    if command == "template-delete":
        return f"{tool_path} template delete -c {config_path.as_posix()}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a cluster lifecycle manifest for a cycle.")
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument("--cycle-config", default="config/experimental-cycles/C1.json", help="Cycle profile JSON path.")
    parser.add_argument("--lifecycle-policy", default=None, help="Optional lifecycle policy JSON path override.")
    parser.add_argument("--mode", choices=["external", "reuse", "ephemeral"], default=None, help="Optional lifecycle mode override.")
    parser.add_argument("--destroy-cluster-after-cycle", type=bool_arg, default=None, help="Optional destroy intent override.")
    parser.add_argument("--provider-config", default=None, help="Optional provider config path override for real execution previews.")
    parser.add_argument("--tool-path", default="proxmox-k3s", help="Provider tool path used in command previews.")
    parser.add_argument("--output-root", default=None, help="Output directory. Defaults to cycle lifecycle artifact root.")
    parser.add_argument("--run-id", default=None, help="Stable run id for manifest file names.")
    parser.add_argument("--write-latest-aliases", action="store_true", help="Also write latest aliases in the output directory.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    cycle_path = resolve_repo_path(repo_root, args.cycle_config)
    if cycle_path is None or not cycle_path.exists():
        raise FileNotFoundError(f"Cycle profile not found: {cycle_path}")

    cycle = load_json(cycle_path)
    cycle_id = cycle.get("cycleId", "unknown-cycle")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    run_id = args.run_id or f"{cycle_id.lower()}_cluster_lifecycle_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    cycle_lifecycle = cycle.get("clusterLifecycle", {})
    provider_infra = cycle.get("providerBackedInfrastructure", {})
    lifecycle_policy_path_value = args.lifecycle_policy or cycle_lifecycle.get("lifecyclePolicyPath") or provider_infra.get("lifecyclePolicyPath")
    lifecycle_policy_path = resolve_repo_path(repo_root, lifecycle_policy_path_value)
    lifecycle_policy = load_json(lifecycle_policy_path) if path_exists(lifecycle_policy_path) else {}

    mode = args.mode or cycle_lifecycle.get("clusterLifecycleMode") or lifecycle_policy.get("clusterLifecycleMode") or provider_infra.get("clusterLifecycleMode") or "external"
    destroy_after_cycle = args.destroy_cluster_after_cycle
    if destroy_after_cycle is None:
        destroy_after_cycle = cycle_lifecycle.get("destroyClusterAfterCycle")
    if destroy_after_cycle is None:
        destroy_after_cycle = lifecycle_policy.get("destroyClusterAfterCycleDefault", False)

    infra_profile_path = provider_infra.get("infrastructureProfilePath") or cycle.get("infrastructureProfile", {}).get("profilePath") or cycle.get("clusterContext", {}).get("infrastructureProfilePath")
    infra_profile = {}
    if infra_profile_path:
        resolved = resolve_repo_path(repo_root, infra_profile_path)
        if path_exists(resolved):
            infra_profile = load_json(resolved)

    binding_path = provider_infra.get("providerBindingPath") or infra_profile.get("provider", {}).get("providerBindingPath")
    binding = {}
    if binding_path:
        resolved = resolve_repo_path(repo_root, binding_path)
        if path_exists(resolved):
            binding = load_json(resolved)

    provider_config = binding.get("providerConfig", {})
    local_config = resolve_repo_path(repo_root, provider_config.get("localPath"))
    example_config = resolve_repo_path(repo_root, provider_config.get("examplePath"))
    template_config = resolve_repo_path(repo_root, provider_config.get("templatePath"))

    explicit_provider_config = resolve_repo_path(repo_root, args.provider_config) if args.provider_config else None
    resolved_real_config = explicit_provider_config
    if resolved_real_config is None:
        configured_paths = {
            "localPath": local_config,
            "examplePath": example_config,
            "templatePath": template_config,
        }
        preference_order = binding.get("resolutionPolicy", {}).get("realExecutionConfigPreferenceOrder", ["localPath"])
        for key in preference_order:
            candidate = configured_paths.get(key)
            if candidate is not None:
                resolved_real_config = candidate
                break

    commands = {
        "createCluster": {"planned": mode in {"reuse", "ephemeral"} and lifecycle_policy.get("commands", {}).get("createCluster", {}).get("allowed", False), "required": lifecycle_policy.get("commands", {}).get("createCluster", {}).get("required", False), "preview": command_preview(args.tool_path, "create", resolved_real_config), "providerConfigResolved": resolved_real_config.as_posix() if resolved_real_config else None},
        "refreshKubeconfig": {"planned": mode in {"reuse", "ephemeral"} and lifecycle_policy.get("commands", {}).get("refreshKubeconfig", {}).get("allowed", False), "required": lifecycle_policy.get("commands", {}).get("refreshKubeconfig", {}).get("required", False), "preview": command_preview(args.tool_path, "kubeconfig", resolved_real_config), "providerConfigResolved": resolved_real_config.as_posix() if resolved_real_config else None},
        "deleteCluster": {"planned": bool(destroy_after_cycle), "required": bool(destroy_after_cycle) and lifecycle_policy.get("commands", {}).get("deleteCluster", {}).get("required", False), "preview": command_preview(args.tool_path, "delete", resolved_real_config, confirm_delete=True), "providerConfigResolved": resolved_real_config.as_posix() if resolved_real_config else None, "requiresExplicitConfirmation": lifecycle_policy.get("executionGuards", {}).get("requireExplicitDeleteConfirmation", True)}
    }

    output_root_value = args.output_root or cycle_lifecycle.get("lifecycleArtifactRoot") or lifecycle_policy.get("artifactPolicy", {}).get("defaultLifecycleArtifactRootTemplate", "results/experimental-cycles/{cycleId}/infrastructure/lifecycle")
    output_root = resolve_repo_path(repo_root, output_root_value.format(cycleId=cycle_id))
    output_root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schemaVersion": "cluster-lifecycle-manifest/v1",
        "manifestId": run_id,
        "generatedAtUtc": now,
        "cycle": {"cycleId": cycle_id, "cycleName": cycle.get("cycleName"), "cycleConfigPath": args.cycle_config},
        "infrastructure": {"infrastructureProfileId": provider_infra.get("infrastructureProfileId") or cycle.get("infrastructureProfile", {}).get("infrastructureProfileId") or cycle.get("clusterContext", {}).get("infrastructureProfileId"), "infrastructureProfilePath": infra_profile_path, "clusterName": infra_profile.get("clusterIdentity", {}).get("clusterName"), "providerId": provider_infra.get("provider") or infra_profile.get("provider", {}).get("providerId")},
        "providerBinding": {"providerBindingId": binding.get("providerBindingId") or provider_infra.get("providerBindingId"), "providerBindingPath": binding_path, "localConfigPath": provider_config.get("localPath"), "localConfigAvailable": path_exists(local_config), "exampleConfigPath": provider_config.get("examplePath"), "exampleConfigAvailable": path_exists(example_config), "templateConfigPath": provider_config.get("templatePath"), "templateConfigAvailable": path_exists(template_config), "resolvedRealExecutionConfigPath": resolved_real_config.as_posix() if resolved_real_config else None, "realExecutionConfigAvailable": path_exists(resolved_real_config)},
        "clusterLifecycle": {"lifecyclePolicyId": lifecycle_policy.get("lifecyclePolicyId") or cycle_lifecycle.get("lifecyclePolicyId"), "lifecyclePolicyPath": lifecycle_policy_path_value, "clusterLifecycleMode": mode, "providerManagedLifecycle": lifecycle_policy.get("providerManagedLifecycle", cycle_lifecycle.get("providerManagedLifecycle")), "provisioningRequired": lifecycle_policy.get("provisioningRequired", cycle_lifecycle.get("provisioningRequired")), "destroyClusterAfterCycle": destroy_after_cycle, "deleteClusterAfterCycle": bool(destroy_after_cycle), "destructiveActionsRequireExplicitConfirmation": lifecycle_policy.get("executionGuards", {}).get("requireExplicitDeleteConfirmation", True)},
        "artifactPolicy": {"outputRoot": output_root.as_posix(), "lifecycleManifestPath": (output_root / f"{run_id}.json").as_posix(), "lifecycleTextPath": (output_root / f"{run_id}.txt").as_posix(), "provisioningLogRoot": (cycle_lifecycle.get("provisioningLogRoot") or lifecycle_policy.get("artifactPolicy", {}).get("defaultProvisioningLogRootTemplate") or "").format(cycleId=cycle_id) or None, "deletionLogRoot": (cycle_lifecycle.get("deletionLogRoot") or lifecycle_policy.get("artifactPolicy", {}).get("defaultDeleteLogRootTemplate") or "").format(cycleId=cycle_id) or None},
        "plannedCommands": commands,
        "guards": lifecycle_policy.get("executionGuards", {}),
        "decision": {"status": "lifecycle_manifest_rendered", "canRunCreateWithResolvedConfig": bool(commands["createCluster"]["planned"] and resolved_real_config and resolved_real_config.exists()), "canRunDeleteWithResolvedConfig": bool(commands["deleteCluster"]["planned"] and resolved_real_config and resolved_real_config.exists()), "missingRealExecutionConfig": bool(mode in {"reuse", "ephemeral"} and not path_exists(resolved_real_config)), "notes": ["This manifest is a planning and evidence artifact; it does not execute provider commands.", "Provider command wrappers must still enforce destructive-action confirmation for delete operations."]}
    }

    json_path = output_root / f"{run_id}.json"
    txt_path = output_root / f"{run_id}.txt"
    write_json(json_path, manifest)
    lines = ["Cluster lifecycle manifest", "==========================", f"Manifest ID: {run_id}", f"Generated at UTC: {now}", f"Cycle: {cycle_id}", f"Infrastructure profile: {manifest['infrastructure']['infrastructureProfileId']}", f"Provider: {manifest['infrastructure']['providerId']}", f"Lifecycle policy: {manifest['clusterLifecycle']['lifecyclePolicyId']}", f"Lifecycle mode: {mode}", f"Destroy cluster after cycle: {destroy_after_cycle}", f"Real execution config: {manifest['providerBinding']['resolvedRealExecutionConfigPath']}", f"Real execution config available: {manifest['providerBinding']['realExecutionConfigAvailable']}", "", "Planned commands:", f"- create: {commands['createCluster']['preview']}", f"- kubeconfig: {commands['refreshKubeconfig']['preview']}", f"- delete: {commands['deleteCluster']['preview']}", "", f"JSON manifest: {json_path.as_posix()}", f"Text summary: {txt_path.as_posix()}"]
    txt_path.write_text(normalize_artifact_text_for_output("\n".join(lines) + "\n", txt_path), encoding="utf-8")
    if args.write_latest_aliases:
        write_json(output_root / "latest-cluster-lifecycle-manifest.json", manifest)
        (output_root / "latest-cluster-lifecycle-manifest.txt").write_text(normalize_artifact_text_for_output("\n".join(lines) + "\n", output_root / "latest-cluster-lifecycle-manifest.txt"), encoding="utf-8")
    print(json_path.as_posix())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
