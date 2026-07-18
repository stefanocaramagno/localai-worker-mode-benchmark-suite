#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


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


def resolve_cluster_validation_profile(repo_root: Path, cycle: Dict[str, Any], explicit_profile: Optional[str]) -> Tuple[Path, Dict[str, Any]]:
    profile_value = (
        explicit_profile
        or cycle.get("pipelineProfiles", {}).get("clusterValidation")
        or cycle.get("clusterValidation", {}).get("clusterValidationProfilePath")
    )
    if not profile_value:
        raise ValueError("Cluster validation profile path is not declared in the cycle profile and was not provided explicitly.")
    profile_path = repo_path(repo_root, profile_value)
    if profile_path is None or not profile_path.exists():
        raise FileNotFoundError(f"Cluster validation profile not found: {profile_value}")
    return profile_path, read_json(profile_path)


def resolve_low_level_validation_profile(repo_root: Path, cluster_validation_profile: Dict[str, Any], explicit_profile: Optional[str]) -> Tuple[Path, Dict[str, Any]]:
    profile_value = explicit_profile or cluster_validation_profile.get("provisioningValidationProfilePath")
    if not profile_value:
        raise ValueError("Low-level provisioning validation profile path is not declared.")
    profile_path = repo_path(repo_root, profile_value)
    if profile_path is None or not profile_path.exists():
        raise FileNotFoundError(f"Low-level provisioning validation profile not found: {profile_value}")
    return profile_path, read_json(profile_path)


def check_pre_validation_gate(
    repo_root: Path,
    profile: Dict[str, Any],
    dry_run: bool,
    skip_gate: bool,
) -> Dict[str, Any]:
    gate = profile.get("preValidationGate", {})
    if skip_gate:
        return {
            "enabled": bool(gate.get("enabled", False)),
            "status": "skipped_by_explicit_flag",
            "passed": True,
            "details": {},
        }
    if dry_run and gate.get("dryRunBypassesGate", True):
        return {
            "enabled": bool(gate.get("enabled", False)),
            "status": "bypassed_for_dry_run",
            "passed": True,
            "details": {},
        }
    if not gate.get("enabled", False):
        return {
            "enabled": False,
            "status": "not_enabled",
            "passed": True,
            "details": {},
        }

    manifest_path = repo_path(repo_root, gate.get("latestProvisioningIntegrationManifestPath"))
    details: Dict[str, Any] = {
        "manifestPath": rel_or_abs(manifest_path, repo_root),
        "manifestExists": bool(manifest_path and manifest_path.exists()),
    }

    if gate.get("requireLatestProvisioningIntegrationManifest", True) and not details["manifestExists"]:
        return {"enabled": True, "status": "failed_missing_provisioning_manifest", "passed": False, "details": details}

    if manifest_path and manifest_path.exists():
        manifest = read_json(manifest_path)
        details["manifestStatus"] = manifest.get("status")
        details["manifestAction"] = manifest.get("action")
        details["kubeconfigVerificationStatus"] = (manifest.get("kubeconfigVerification") or {}).get("status")

        accepted_statuses = gate.get("acceptedProvisioningStatuses", ["completed"])
        accepted_actions = gate.get("acceptedProvisioningActions", ["provision", "kubeconfig"])
        expected_kube_status = gate.get("requireKubeconfigVerificationStatus", "verified")

        if manifest.get("status") not in accepted_statuses:
            return {"enabled": True, "status": "failed_unaccepted_provisioning_status", "passed": False, "details": details}
        if manifest.get("action") not in accepted_actions:
            return {"enabled": True, "status": "failed_unaccepted_provisioning_action", "passed": False, "details": details}
        if expected_kube_status and details["kubeconfigVerificationStatus"] != expected_kube_status:
            return {"enabled": True, "status": "failed_kubeconfig_verification_status", "passed": False, "details": details}

    return {"enabled": True, "status": "passed", "passed": True, "details": details}


def run_validator(
    repo_root: Path,
    low_level_profile_path: Path,
    kubeconfig: Optional[Path],
    output_root: Path,
    validation_id: str,
    allow_metrics_warning: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    validator = repo_root / "scripts" / "infrastructure" / "validation" / "validate-proxmox-k3s-cluster.py"
    if not validator.exists():
        raise FileNotFoundError(f"Low-level cluster validator not found: {validator}")

    python = shutil.which("python") or shutil.which("python3")
    if not python:
        raise RuntimeError("Neither python nor python3 is available in PATH.")

    command = [
        python,
        str(validator),
        "--repo-root",
        str(repo_root),
        "--profile-config",
        rel_or_abs(low_level_profile_path, repo_root) or str(low_level_profile_path),
        "--output-root",
        str(output_root),
        "--validation-id",
        validation_id,
    ]
    if kubeconfig is not None:
        command.extend(["--kubeconfig", str(kubeconfig)])
    if allow_metrics_warning:
        command.append("--allow-metrics-warning")
    if dry_run:
        command.append("--dry-run")

    started_at = utc_now()
    completed = subprocess.run(command, text=True, capture_output=True)
    finished_at = utc_now()
    return {
        "command": command,
        "startedAtUtc": started_at,
        "finishedAtUtc": finished_at,
        "exitCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "success": completed.returncode == 0,
    }


def build_summary(manifest: Dict[str, Any]) -> str:
    lines = [
        "Provider-backed cluster validation summary",
        "==========================================",
        "",
        f"Validation run ID: {manifest.get('validationRunId')}",
        f"Status: {manifest.get('status')}",
        f"Cycle: {manifest.get('cycle', {}).get('cycleId')}",
        f"Infrastructure profile: {manifest.get('infrastructure', {}).get('infrastructureProfileId')}",
        f"Provider: {manifest.get('provider', {}).get('providerId')}",
        f"Cluster validation profile: {manifest.get('clusterValidationProfile', {}).get('profileId')}",
        f"Low-level validation profile: {manifest.get('lowLevelValidationProfile', {}).get('profileId')}",
        f"Kubeconfig: {manifest.get('clusterAccess', {}).get('kubeconfigPath')}",
        "",
        "Pre-validation gate:",
        f"- Status: {manifest.get('preValidationGate', {}).get('status')}",
        f"- Passed: {manifest.get('preValidationGate', {}).get('passed')}",
        "",
        "Validation result:",
        f"- Raw status: {manifest.get('rawValidation', {}).get('status')}",
        f"- Raw JSON: {manifest.get('rawValidation', {}).get('jsonPath')}",
        f"- Raw text: {manifest.get('rawValidation', {}).get('textPath')}",
        "",
        "Decision:",
        f"- Can proceed to application deployment: {manifest.get('decision', {}).get('canProceedToApplicationDeployment')}",
        f"- Reason: {manifest.get('decision', {}).get('reason')}",
    ]
    if manifest.get("errors"):
        lines.extend(["", "Errors:"])
        for error in manifest["errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run provider-backed cluster validation for an experimental cycle.")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--cycle-config", default="config/experimental-cycles/C1.json")
    parser.add_argument("--cluster-validation-profile", default=None)
    parser.add_argument("--validation-profile", default=None)
    parser.add_argument("--kubeconfig", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--validation-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-prevalidation-gate", action="store_true")
    parser.add_argument("--allow-metrics-warning", action="store_true")
    parser.add_argument("--write-latest-aliases", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else default_repo_root()
    validation_id = args.validation_id or f"cluster_validation_{compact_now()}"
    started_at = utc_now()
    errors: list[str] = []

    try:
        cycle_path, cycle = load_cycle(repo_root, args.cycle_config)
        cv_profile_path, cv_profile = resolve_cluster_validation_profile(repo_root, cycle, args.cluster_validation_profile)
        low_level_profile_path, low_level_profile = resolve_low_level_validation_profile(repo_root, cv_profile, args.validation_profile)

        artifact_policy = cv_profile.get("artifactPolicy", {})
        explicit_output_root = bool(args.output_root)
        output_root = repo_path(repo_root, args.output_root) if explicit_output_root else repo_path(repo_root, artifact_policy.get("root"))
        output_root = output_root or repo_root / "results" / "_runtime" / "cluster-validation"
        if explicit_output_root:
            logs_root = output_root / "logs"
            manifests_root = output_root / "manifests"
        else:
            logs_root = repo_path(repo_root, artifact_policy.get("logsRoot")) or output_root / "logs"
            manifests_root = repo_path(repo_root, artifact_policy.get("manifestsRoot")) or output_root / "manifests"
        for directory in [output_root, logs_root, manifests_root]:
            directory.mkdir(parents=True, exist_ok=True)

        kubeconfig_path = repo_path(repo_root, args.kubeconfig or cv_profile.get("kubeconfigPath") or low_level_profile.get("provisioning", {}).get("recommendedKubeconfigPath"))

        pre_gate = check_pre_validation_gate(
            repo_root=repo_root,
            profile=cv_profile,
            dry_run=args.dry_run,
            skip_gate=args.skip_prevalidation_gate,
        )
        if not pre_gate.get("passed"):
            errors.append(f"Pre-validation gate failed: {pre_gate.get('status')}")

        validator_result: Dict[str, Any] | None = None
        raw_validation_payload: Dict[str, Any] | None = None

        if not errors:
            validator_result = run_validator(
                repo_root=repo_root,
                low_level_profile_path=low_level_profile_path,
                kubeconfig=kubeconfig_path,
                output_root=output_root,
                validation_id=validation_id,
                allow_metrics_warning=args.allow_metrics_warning,
                dry_run=args.dry_run,
            )
            log_path = logs_root / f"{validation_id}.cluster-validation-runner.log"
            write_text(log_path, (validator_result.get("stdout") or "") + ("\n" + validator_result.get("stderr", "") if validator_result.get("stderr") else ""))
            validator_result["logPath"] = rel_or_abs(log_path, repo_root)

            raw_json_path = output_root / f"{validation_id}_validation.json"
            if raw_json_path.exists():
                raw_validation_payload = read_json(raw_json_path)
            if validator_result["exitCode"] != 0:
                errors.append("Low-level cluster validation returned a non-zero exit code.")

        raw_status = raw_validation_payload.get("status") if raw_validation_payload else None
        accepted_statuses = cv_profile.get("decisionPolicy", {}).get("acceptedStatusesBeforeApplicationDeployment", ["validated"])
        can_proceed = bool(raw_status in accepted_statuses and not errors)
        status = "validated" if can_proceed else "dry_run" if args.dry_run and not errors else "failed"

        manifest_path = manifests_root / f"{validation_id}.cluster-validation-manifest.json"
        summary_path = manifests_root / f"{validation_id}.cluster-validation-summary.txt"

        provider_backed = cycle.get("providerBackedInfrastructure", {})
        manifest = {
            "schemaVersion": "provider-backed-cluster-validation-manifest/v1",
            "validationRunId": validation_id,
            "status": status,
            "startedAtUtc": started_at,
            "finishedAtUtc": utc_now(),
            "dryRun": args.dry_run,
            "cycle": {
                "cycleId": cycle.get("cycleId"),
                "cycleName": cycle.get("cycleName"),
                "cycleConfigPath": rel_or_abs(cycle_path, repo_root),
            },
            "infrastructure": {
                "infrastructureProfileId": provider_backed.get("infrastructureProfileId") or cv_profile.get("infrastructureProfileId"),
                "infrastructureProfilePath": provider_backed.get("infrastructureProfilePath") or cv_profile.get("infrastructureProfilePath"),
            },
            "provider": {
                "providerId": provider_backed.get("provider") or cv_profile.get("providerId"),
                "providerBindingId": provider_backed.get("providerBindingId") or cv_profile.get("providerBindingId"),
                "providerBindingPath": provider_backed.get("providerBindingPath") or cv_profile.get("providerBindingPath"),
            },
            "clusterValidationProfile": {
                "profileId": cv_profile.get("clusterValidationProfileId"),
                "profilePath": rel_or_abs(cv_profile_path, repo_root),
            },
            "lowLevelValidationProfile": {
                "profileId": low_level_profile.get("profileId"),
                "profilePath": rel_or_abs(low_level_profile_path, repo_root),
            },
            "clusterAccess": {
                "kubeconfigPath": rel_or_abs(kubeconfig_path, repo_root),
                "kubeconfigExists": bool(kubeconfig_path and kubeconfig_path.exists()),
            },
            "preValidationGate": pre_gate,
            "validatorExecution": validator_result,
            "rawValidation": {
                "status": raw_status,
                "jsonPath": rel_or_abs(output_root / f"{validation_id}_validation.json", repo_root),
                "textPath": rel_or_abs(output_root / f"{validation_id}_validation.txt", repo_root),
                "markdownPath": rel_or_abs(output_root / f"{validation_id}_validation.md", repo_root),
                "summary": raw_validation_payload.get("summary") if raw_validation_payload else None,
                "decision": raw_validation_payload.get("decision") if raw_validation_payload else None,
            },
            "artifacts": {
                "outputRoot": rel_or_abs(output_root, repo_root),
                "logsRoot": rel_or_abs(logs_root, repo_root),
                "manifestsRoot": rel_or_abs(manifests_root, repo_root),
                "manifestPath": rel_or_abs(manifest_path, repo_root),
                "summaryPath": rel_or_abs(summary_path, repo_root),
            },
            "decision": {
                "canProceedToApplicationDeployment": can_proceed,
                "acceptedStatusesBeforeApplicationDeployment": accepted_statuses,
                "reason": "cluster_validated" if can_proceed else "cluster_validation_failed_or_not_accepted",
                "stopBeforeApplicationDeployment": not can_proceed,
            },
            "errors": errors,
        }

        write_json(manifest_path, manifest)
        write_text(summary_path, build_summary(manifest))

        write_latest = args.write_latest_aliases or bool(artifact_policy.get("writeLatestAliases"))
        if write_latest:
            if explicit_output_root:
                latest_manifest = output_root / "latest-cluster-validation-manifest.json"
                latest_summary = output_root / "latest-cluster-validation-summary.txt"
            else:
                latest_manifest = repo_path(repo_root, artifact_policy.get("latestManifestPath"))
                latest_summary = repo_path(repo_root, artifact_policy.get("latestTextSummaryPath"))
            if latest_manifest:
                write_json(latest_manifest, manifest)
            if latest_summary:
                write_text(latest_summary, build_summary(manifest))

        print(f"Cluster validation status: {status}")
        print(f"Manifest: {manifest_path}")
        print(f"Summary: {summary_path}")
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        return 0 if can_proceed or args.dry_run else 1

    except Exception as exc:
        failure_root = repo_root / "results" / "_runtime" / "cluster-validation-failures"
        failure_root.mkdir(parents=True, exist_ok=True)
        failure_path = failure_root / f"{validation_id}.failure.json"
        write_json(failure_path, {
            "schemaVersion": "provider-backed-cluster-validation-failure/v1",
            "validationRunId": validation_id,
            "status": "failed",
            "startedAtUtc": started_at,
            "finishedAtUtc": utc_now(),
            "error": str(exc),
        })
        print(f"Cluster validation failed before cycle-scoped artifact resolution: {exc}", file=sys.stderr)
        print(f"Failure artifact: {failure_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
