#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
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


@dataclass
class StepResult:
    name: str
    description: str
    status: str
    command: list[str] = field(default_factory=list)
    startedAt: str | None = None
    completedAt: str | None = None
    exitCode: int | None = None
    artifactHints: list[str] = field(default_factory=list)
    error: str | None = None


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
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = normalize_artifact_text_for_output(content, path)
    path.write_text(content, encoding="utf-8")


def rel_to_repo(repo_root: Path, value: str | None, default: str) -> Path:
    raw = value or default
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else repo_root / candidate


def rel_string(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value
    return None


def cycle_identifier(cycle: dict[str, Any]) -> str:
    campaign = cycle.get("campaign") if isinstance(cycle.get("campaign"), dict) else {}
    return str(cycle.get("cycleId") or campaign.get("campaignId") or "cycle").strip() or "cycle"


def cycle_results_path(cycle: dict[str, Any], *parts: str) -> str:
    suffix = "/".join(str(part).strip("/") for part in parts if str(part).strip("/"))
    base = f"results/experimental-cycles/{cycle_identifier(cycle)}"
    return f"{base}/{suffix}" if suffix else base


def scenario_family(cycle: dict[str, Any], scenario_config: dict[str, Any] | None = None) -> str:
    scenario_config = scenario_config or {}
    campaign = cycle.get("campaign") if isinstance(cycle.get("campaign"), dict) else {}
    return str(
        scenario_config.get("family")
        or scenario_config.get("scenarioFamily")
        or cycle.get("scenarioFamily")
        or campaign.get("scenarioFamily")
        or cycle.get("campaignType")
        or "benchmark"
    ).strip() or "benchmark"


def is_network_aware_cycle(cycle: dict[str, Any]) -> bool:
    campaign = cycle.get("campaign") if isinstance(cycle.get("campaign"), dict) else {}
    return (
        cycle_identifier(cycle).upper() == "C9"
        or str(cycle.get("campaignType") or campaign.get("campaignType") or "") == "network_aware_scheduler"
        or bool(cycle.get("networkAwareScheduler"))
    )


def default_pipeline_profile_path(cycle: dict[str, Any], profile_kind: str) -> str:
    if is_network_aware_cycle(cycle):
        mapping = {
            "technicalDiagnosis": "config/technical-diagnosis/profiles/TD_C9_NETWORK_AWARE_SCHEDULER.json",
            "reporting": "config/reporting/profiles/RP_C9_NETWORK_AWARE_SCHEDULER.json",
            "completionGate": "config/completion-gate/profiles/CG_C9_NETWORK_AWARE_SCHEDULER.json",
            "freeze": "config/freeze/profiles/FR_C9_NETWORK_AWARE_SCHEDULER.json",
        }
        if profile_kind in mapping:
            return mapping[profile_kind]
    cycle_id = cycle_identifier(cycle).upper().replace("-", "_")
    generic = {
        "technicalDiagnosis": ("config/technical-diagnosis/profiles", "TD"),
        "reporting": ("config/reporting/profiles", "RP"),
        "completionGate": ("config/completion-gate/profiles", "CG"),
        "freeze": ("config/freeze/profiles", "FR"),
    }
    directory, prefix = generic.get(profile_kind, ("config", profile_kind.upper()))
    return f"{directory}/{prefix}_{cycle_id}.json"


def try_load_json(repo_root: Path, value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    path = rel_to_repo(repo_root, value, value)
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except Exception:
        return {}


def latest_application_deployment_manifest_path(repo_root: Path, cycle: dict[str, Any]) -> Path:
    provider = cycle.get("providerBackedInfrastructure") or {}
    pipeline_profiles = cycle.get("pipelineProfiles") or {}

    profile = try_load_json(
        repo_root,
        pipeline_profiles.get("applicationDeployment") or provider.get("applicationDeploymentProfilePath"),
    )
    artifact_policy = profile.get("artifactPolicy") or {}
    candidate = artifact_policy.get("latestManifestPath")
    if candidate:
        return rel_to_repo(repo_root, candidate, candidate)

    deployment_root = rel_to_repo(
        repo_root,
        provider.get("applicationDeploymentArtifactRoot"),
        cycle_results_path(cycle, "application", "deployment"),
    )
    return deployment_root / "latest-localai-deployment-manifest.json"


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return load_json(path)
    except Exception:
        return {}


def benchmark_scenario_id(cycle: dict[str, Any], baseline: dict[str, Any], scenario_payload: dict[str, Any]) -> str:
    return str(
        baseline.get("scenarioId")
        or baseline.get("variantId")
        or scenario_payload.get("scenarioId")
        or scenario_payload.get("variantId")
        or baseline.get("baselineId")
        or scenario_payload.get("baselineId")
        or cycle.get("cycleId")
        or "scenario"
    )


def to_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def measurement_target_request_evidence(stats_csv: Path, target_type: str = "POST", target_name: str = "POST /v1/chat/completions") -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "statsCsvPath": str(stats_csv),
        "targetType": target_type,
        "targetName": target_name,
        "targetRequestCount": 0,
        "aggregatedRequestCount": 0,
        "validTargetRequestsPresent": False,
        "invalidReason": "measurement_stats_csv_missing",
    }
    if not stats_csv.exists():
        return evidence
    try:
        with stats_csv.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except Exception as exc:
        evidence["invalidReason"] = "measurement_stats_csv_unreadable"
        evidence["error"] = str(exc)
        return evidence

    target_row = None
    aggregated_row = None
    for row in rows:
        row_type = (row.get("Type") or "").strip()
        row_name = (row.get("Name") or "").strip()
        if row_name == "Aggregated":
            aggregated_row = row
        if row_type == target_type and row_name == target_name:
            target_row = row

    if aggregated_row is not None:
        aggregated_count = to_number(aggregated_row.get("Request Count"))
        if aggregated_count is not None:
            evidence["aggregatedRequestCount"] = int(round(aggregated_count))

    if target_row is None:
        evidence["invalidReason"] = "measurement_missing_target_request_row"
        return evidence

    target_count = to_number(target_row.get("Request Count"))
    if target_count is None or target_count <= 0:
        evidence["invalidReason"] = "measurement_produced_zero_valid_requests"
        return evidence

    evidence["targetRequestCount"] = int(round(target_count))
    evidence["validTargetRequestsPresent"] = True
    evidence["invalidReason"] = None
    return evidence


def resolve_artifact_path(repo_root: Path, value: Any) -> Path | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.exists():
        return candidate
    if not candidate.is_absolute():
        return repo_root / candidate
    normalized = text.replace("\\", "/")
    marker = "/localai-worker-mode-benchmark-suite/"
    if marker in normalized:
        return repo_root / normalized.split(marker, 1)[1]
    return candidate


def classify_evidence_text(text: Any) -> set[str]:
    kinds: set[str] = set()
    lower = str(text).lower()
    if "failedscheduling" in lower or "failed scheduling" in lower:
        kinds.add("failed_scheduling")
    if "insufficient cpu" in lower:
        kinds.add("insufficient_cpu")
    if "insufficient memory" in lower:
        kinds.add("insufficient_memory")
    if "node affinity/selector" in lower or "node(s) didn't match pod's node affinity" in lower or "node(s) did not match pod's node affinity" in lower:
        kinds.add("node_affinity_selector_mismatch")
    if "preemption is not helpful" in lower:
        kinds.add("preemption_not_helpful")
    if "no preemption victims" in lower:
        kinds.add("no_preemption_victims_found")
    if "rollout check failed" in lower or "timed out waiting for the condition" in lower:
        kinds.add("rollout_timeout")
    if "pending" in lower:
        kinds.add("pending_pod")
    if "localai_deployment_not_ready" in lower:
        kinds.add("application_not_ready")
    if "benchmark_precheck" in lower or "pre-check" in lower or "precheck" in lower:
        kinds.add("benchmark_precheck_failed")
    if "restart" in lower:
        kinds.add("pod_restart")
    if "namespace_pods_healthy" in lower:
        kinds.add("namespace_pods_not_healthy")
    if "api smoke" in lower or "api_smoke" in lower:
        kinds.add("api_smoke_failed")
    if "timeout" in lower or "timed out" in lower or "request canceled" in lower:
        kinds.add("timeout")
    if "latency" in lower or "netem" in lower or "tc" in lower:
        kinds.add("latency_injection")
    if "pre_benchmark" in lower or "before benchmark" in lower:
        kinds.add("pre_benchmark_failure")
    return kinds


def deployment_constraint_evidence(repo_root: Path, deployment_manifest: dict[str, Any]) -> dict[str, Any]:
    texts: list[str] = []
    for error in deployment_manifest.get("errors") or []:
        texts.append(str(error))
    for rollout in deployment_manifest.get("rolloutChecks") or []:
        if rollout.get("success") is False:
            texts.append(f"Rollout check failed for deployment/{rollout.get('deployment')}")
    snapshots = deployment_manifest.get("snapshots") or {}
    candidate_paths: list[Path | None] = []
    for key in ("events", "events_json", "describe_pods", "describe_deployments"):
        item = snapshots.get(key)
        if isinstance(item, dict) and item.get("path"):
            candidate_paths.append(resolve_artifact_path(repo_root, item.get("path")))
    manifest_path = resolve_artifact_path(repo_root, (deployment_manifest.get("artifacts") or {}).get("manifestPath"))
    if manifest_path is not None:
        snapshots_dir = manifest_path.parent.parent / "snapshots"
        if snapshots_dir.exists():
            candidate_paths.extend(snapshots_dir.glob("*events*.txt"))
            candidate_paths.extend(snapshots_dir.glob("*describe_pods*.txt"))
    seen_paths: set[str] = set()
    evidence_lines: list[str] = []
    for path in candidate_paths:
        if path is None or not path.exists() or not path.is_file():
            continue
        try:
            resolved = str(path.resolve())
        except Exception:
            resolved = str(path)
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line in content.splitlines():
            lower = line.lower()
            if any(token in lower for token in ["failedscheduling", "insufficient", "affinity/selector", "preemption", "rollout", "pending"]):
                evidence_lines.append(line.strip())
                texts.append(line.strip())
    evidence_kinds = sorted({kind for text in texts for kind in classify_evidence_text(text)})
    return {
        "evidenceKinds": evidence_kinds,
        "schedulerEvidenceLines": evidence_lines[:50],
        "insufficientCpuObserved": "insufficient_cpu" in evidence_kinds,
        "insufficientMemoryObserved": "insufficient_memory" in evidence_kinds,
        "failedSchedulingObserved": "failed_scheduling" in evidence_kinds,
    }


def deployment_requires_benchmark_skip(manifest: dict[str, Any]) -> tuple[bool, str]:
    if not manifest:
        return False, "deployment_manifest_unavailable"
    decision = manifest.get("decision") or {}
    if decision.get("canProceedToBenchmark") is True:
        return False, str(decision.get("reason") or "localai_deployment_ready")
    status = str(manifest.get("status") or "unknown")
    reason = str(decision.get("reason") or "localai_deployment_not_ready")
    if status in {"failed", "unsupported", "partially_deployed"} or decision.get("stopBeforeBenchmark") is True:
        return True, reason
    return False, reason


def resolve_cycle_kubeconfig_path(repo_root: Path, cycle: dict[str, Any]) -> Path:
    provider = cycle.get("providerBackedInfrastructure") or {}
    pipeline_profiles = cycle.get("pipelineProfiles") or {}

    binding = try_load_json(repo_root, provider.get("providerBindingPath"))
    provisioning_profile = try_load_json(
        repo_root,
        provider.get("provisioningIntegrationProfilePath") or pipeline_profiles.get("provisioningIntegration"),
    )
    cluster_validation_profile = try_load_json(
        repo_root,
        provider.get("clusterValidationProfilePath") or pipeline_profiles.get("clusterValidation"),
    )
    application_deployment_profile = try_load_json(
        repo_root,
        provider.get("applicationDeploymentProfilePath") or pipeline_profiles.get("applicationDeployment"),
    )

    deployment_topology = application_deployment_profile.get("deploymentTopology") or {}
    candidate = first_non_empty(
        provider.get("kubeconfigPath"),
        provider.get("generatedKubeconfigPath"),
        (provisioning_profile.get("kubeconfigVerification") or {}).get("expectedPath"),
        (binding.get("providerConfig") or {}).get("recommendedKubeconfigPath"),
        (binding.get("templateVariables") or {}).get("kubeconfigPath"),
        cluster_validation_profile.get("kubeconfigPath"),
        deployment_topology.get("kubeconfigPath"),
    )
    return rel_to_repo(repo_root, candidate, "config/cluster-access/fixed-cluster/kubeconfig")


def as_command_text(command: list[str]) -> str:
    return " ".join(subprocess.list2cmdline([part]) for part in command)


def resolve_python_command() -> list[str]:
    if sys.executable:
        return [sys.executable]
    for candidate in ("python", "python3", "py"):
        resolved = shutil.which(candidate)
        if resolved:
            if candidate == "py":
                return [resolved, "-3"]
            return [resolved]
    return ["python"]


def script(repo_root: Path, relative_path: str) -> str:
    return str(repo_root / relative_path)


def run_step(
    *,
    name: str,
    description: str,
    command: list[str],
    repo_root: Path,
    dry_run: bool,
    continue_on_failure: bool,
    artifact_hints: list[str] | None = None,
) -> StepResult:
    result = StepResult(
        name=name,
        description=description,
        status="dry_run" if dry_run else "running",
        command=command,
        artifactHints=artifact_hints or [],
        startedAt=utc_now(),
    )
    if dry_run:
        result.completedAt = utc_now()
        result.exitCode = 0
        return result

    try:
        completed = subprocess.run(command, cwd=repo_root, check=False)
        result.exitCode = completed.returncode
        result.status = "completed" if completed.returncode == 0 else "failed"
        if completed.returncode != 0 and not continue_on_failure:
            result.completedAt = utc_now()
            return result
    except Exception as exc:
        result.status = "failed"
        result.exitCode = 1
        result.error = str(exc)
        if not continue_on_failure:
            result.completedAt = utc_now()
            return result
    result.completedAt = utc_now()
    return result


def skip_step(name: str, description: str) -> StepResult:
    now = utc_now()
    return StepResult(name=name, description=description, status="skipped", startedAt=now, completedAt=now, exitCode=0)


def blocked_step(name: str, description: str, reason: str, artifact_hints: list[str] | None = None) -> StepResult:
    now = utc_now()
    return StepResult(
        name=name,
        description=description,
        status="skipped_due_to_failed_precondition",
        startedAt=now,
        completedAt=now,
        exitCode=0,
        artifactHints=artifact_hints or [],
        error=reason,
    )


def build_baseline_command(repo_root: Path, baseline_config: Path, kubeconfig_path: Path, replica: str, dry_run: bool, precheck_config: Path | None = None, namespace: str | None = None) -> list[str]:
    if platform.system().lower().startswith("win"):
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh") or "powershell.exe"
        command = [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script(repo_root, "scripts/load/baseline/Start-OfficialBaseline.ps1"),
            "-Replica",
            replica,
            "-BenchmarkConfig",
            str(baseline_config),
            "-Kubeconfig",
            str(kubeconfig_path),
        ]
        if precheck_config is not None:
            command.extend(["-PrecheckConfig", str(precheck_config)])
        if namespace:
            command.extend(["-Namespace", str(namespace)])
        if dry_run:
            command.append("-DryRun")
        return command

    command = [
        "bash",
        script(repo_root, "scripts/load/baseline/start-official-baseline.sh"),
        "--replica",
        replica,
        "--benchmark-config",
        str(baseline_config),
        "--kubeconfig",
        str(kubeconfig_path),
    ]
    if precheck_config is not None:
        command.extend(["--precheck-config", str(precheck_config)])
    if namespace:
        command.extend(["--namespace", str(namespace)])
    if dry_run:
        command.append("--dry-run")
    return command


def is_default_scheduler_runtime(cycle: dict[str, Any], benchmark_config: dict[str, Any]) -> bool:
    return (
        str(cycle.get("campaignType") or "").strip() in {"default_scheduler_baseline", "resource_aware_scheduler", "network_aware_scheduler"}
        or str(cycle.get("scenarioFamily") or "").strip() in {"default-scheduler", "resource-aware-scheduler", "network-aware-scheduler"}
        or str(benchmark_config.get("family") or "").strip() in {"default-scheduler", "resource-aware-scheduler", "network-aware-scheduler"}
        or bool(benchmark_config.get("defaultSchedulerPolicy"))
        or bool(benchmark_config.get("schedulerModePolicy"))
        or bool(benchmark_config.get("networkAwareSchedulerPolicy"))
        or bool(cycle.get("defaultSchedulerBaseline"))
    )


def is_scheduler_mode_runtime(cycle: dict[str, Any], benchmark_config: dict[str, Any]) -> bool:
    return (
        str(cycle.get("campaignType") or "").strip() in {"resource_aware_scheduler", "network_aware_scheduler"}
        or str(cycle.get("scenarioFamily") or "").strip() in {"resource-aware-scheduler", "network-aware-scheduler"}
        or str(benchmark_config.get("family") or "").strip() in {"resource-aware-scheduler", "network-aware-scheduler"}
        or bool(benchmark_config.get("schedulerModePolicy"))
        or bool(benchmark_config.get("networkAwareSchedulerPolicy"))
        or bool(cycle.get("schedulerMode"))
        or bool(cycle.get("networkAwareScheduler"))
    )


def scheduler_mode_policy(cycle: dict[str, Any], benchmark_config: dict[str, Any]) -> dict[str, Any]:
    scenario_policy = benchmark_config.get("networkAwareSchedulerPolicy")
    if isinstance(scenario_policy, dict):
        return scenario_policy
    scenario_policy = benchmark_config.get("schedulerModePolicy")
    if isinstance(scenario_policy, dict):
        return scenario_policy
    cycle_policy = (cycle.get("networkAwareScheduler") or {}).get("policy")
    if isinstance(cycle_policy, dict):
        return cycle_policy
    cycle_policy = (cycle.get("schedulerMode") or {}).get("policy")
    return cycle_policy if isinstance(cycle_policy, dict) else {}


def scheduler_mode_scheduler_name(cycle: dict[str, Any], benchmark_config: dict[str, Any]) -> str | None:
    policy = scheduler_mode_policy(cycle, benchmark_config)
    topology = benchmark_config.get("applicationTopology") or {}
    return (
        policy.get("schedulerName")
        or topology.get("schedulerName")
        or ((cycle.get("schedulerMode") or {}).get("policy") or {}).get("schedulerName")
    )


def scheduler_mode_variant(cycle: dict[str, Any], benchmark_config: dict[str, Any]) -> str:
    policy = scheduler_mode_policy(cycle, benchmark_config)
    mode = str(policy.get("schedulerMode") or (benchmark_config.get("applicationTopology") or {}).get("schedulerMode") or "").lower()
    plugins = " ".join(str(item) for item in (policy.get("enabledPlugins") or policy.get("plugins") or [])).lower()
    if "network" in mode or "networkaware" in mode or "networkawarelocalai" in plugins:
        return "networkaware"
    scheduler_name = scheduler_mode_scheduler_name(cycle, benchmark_config)
    if scheduler_name:
        return "loadaware"
    if "load" in mode or "custom" in mode:
        return "loadaware"
    return "default"


def scheduler_runtime_path(cycle: dict[str, Any], benchmark_config: dict[str, Any], key: str, default: str) -> str:
    policy = scheduler_mode_policy(cycle, benchmark_config)
    runtime = cycle.get("networkAwareSchedulerRuntime") or cycle.get("schedulerModeRuntime") or {}
    pipeline = cycle.get("pipelineProfiles") or {}
    mapping = {
        "monAgentProfilePath": [policy.get("monAgentProfilePath"), runtime.get("monAgentProfilePath"), pipeline.get("monAgent")],
        "customSchedulerProfilePath": [policy.get("customSchedulerProfilePath"), runtime.get("customSchedulerProfilePath"), pipeline.get("customScheduler")],
        "reschedulingProfilePath": [policy.get("reschedulingProfilePath"), runtime.get("reschedulingProfilePath"), pipeline.get("rescheduling")],
        "networkObservabilityProfilePath": [policy.get("networkObservabilityProfilePath"), runtime.get("networkObservabilityProfilePath"), pipeline.get("networkObservability")],
        "istioGatewayProfilePath": [policy.get("istioGatewayProfilePath"), runtime.get("istioGatewayProfilePath"), pipeline.get("istioGateway")],
        "manifestValidationScript": [runtime.get("manifestValidationScript"), pipeline.get("schedulerModeValidation")],
    }
    for candidate in mapping.get(key, []):
        if candidate:
            return str(candidate)
    return default


def default_cluster_lens_profile_path(cycle: dict[str, Any]) -> str:
    pipeline = cycle.get("pipelineProfiles") or {}
    provider = cycle.get("providerBackedInfrastructure") or {}
    return str(
        pipeline.get("clusterLens")
        or provider.get("clusterLensProfilePath")
        or "config/cluster-lens/profiles/CL_C9_PLACEMENT_SNAPSHOT.json"
    )


def resolve_cluster_lens_root(
    repo_root: Path,
    profile: dict[str, Any],
    provider: dict[str, Any],
    scheduler_runtime: dict[str, Any],
    fallback_root: Path,
    scenario_id: str,
) -> Path:
    policy = profile.get("artifactPolicy") or {}
    raw = (
        provider.get("clusterLensArtifactRoot")
        or scheduler_runtime.get("clusterLensArtifactRoot")
        or provider.get("clusterLensArtifactRootPattern")
        or scheduler_runtime.get("clusterLensArtifactRootPattern")
        or policy.get("perVariantOutputRootPattern")
        or policy.get("root")
    )
    if raw:
        text = str(raw).replace("<scenario-id>", scenario_id).replace("__profile_default__", scenario_id)
        return rel_to_repo(repo_root, text, text)
    return fallback_root


def cluster_lens_stage_output_root(base_root: Path, stage: str, primary: bool = False) -> Path:
    safe_stage = str(stage or "capture").strip().replace(" ", "-").replace("_", "-").lower()
    return base_root / "stages" / safe_stage


def cluster_lens_primary_artifact_names() -> list[str]:
    return [
        "cluster-lens-snapshot.json",
        "cluster-lens-kubernetes-pods.json",
        "cluster-lens-kubernetes-deployments.json",
        "cluster-lens-kubernetes-nodes.json",
        "cluster-lens-placement-summary.json",
        "cluster-lens-placement-signature.csv",
        "cluster-lens-capture-manifest.json",
    ]


def promote_cluster_lens_primary_artifacts(
    repo_root: Path,
    stage_root: Path,
    primary_root: Path,
    stage: str,
    policy: dict[str, Any],
) -> tuple[bool, str | None]:
    if not bool(policy.get("promotePrimaryStageToRoot", True)):
        return True, None
    try:
        primary_root.mkdir(parents=True, exist_ok=True)
        promoted: list[dict[str, Any]] = []
        missing: list[str] = []
        for name in cluster_lens_primary_artifact_names():
            source = stage_root / name
            target = primary_root / name
            if source.is_file():
                shutil.copy2(source, target)
                promoted.append({
                    "fileName": name,
                    "source": rel_string(repo_root, source),
                    "target": rel_string(repo_root, target),
                })
            else:
                missing.append(name)
        manifest_name = str(policy.get("primaryStagePromotionManifestName") or "cluster-lens-primary-stage-manifest.json")
        promotion_manifest = {
            "schemaVersion": "cluster-lens-primary-stage-promotion/v1",
            "generatedAtUtc": utc_now(),
            "primaryStage": stage,
            "stageArtifactRoot": rel_string(repo_root, stage_root),
            "primaryArtifactRoot": rel_string(repo_root, primary_root),
            "promotedArtifacts": promoted,
            "missingArtifacts": missing,
            "status": "promoted" if promoted else "empty",
        }
        write_json(primary_root / manifest_name, promotion_manifest)
        return True, None
    except Exception as exc:
        return False, str(exc)


def cluster_lens_step_name(stage: str) -> str:
    safe_stage = str(stage or "capture").strip().replace(" ", "_").replace("-", "_").lower()
    return f"capture_cluster_lens_{safe_stage}"


def cluster_lens_capture_stage_policy(cycle: dict[str, Any], scheduler_runtime: dict[str, Any]) -> dict[str, Any]:
    provider = cycle.get("providerBackedInfrastructure") or {}
    policy = (
        provider.get("clusterLensCaptureStagePolicy")
        or scheduler_runtime.get("clusterLensCaptureStagePolicy")
        or {}
    )
    return policy if isinstance(policy, dict) else {}


def cluster_lens_stage_flag(stage: str, *, default_scheduler_runtime: bool = False) -> str:
    normalized = str(stage or "").strip().replace("_", "-").lower()
    mapping = {
        "post-deployment": "capturePostDeployment",
        "post-telemetry-priming": "capturePostTelemetryPriming",
        "pre-rescheduling": "capturePreRescheduling",
        "post-rescheduling": "capturePostRescheduling",
        "post-benchmark": "capturePostBenchmark",
    }
    if normalized == "pre-benchmark" and default_scheduler_runtime:
        return "capturePreBenchmarkForDefaultScheduler"
    if normalized == "pre-benchmark":
        return "capturePreBenchmark"
    return mapping.get(normalized, "")


def cluster_lens_stage_enabled(
    policy: dict[str, Any],
    stage: str,
    *,
    default_scheduler_runtime: bool = False,
    default: bool = True,
) -> bool:
    flag = cluster_lens_stage_flag(stage, default_scheduler_runtime=default_scheduler_runtime)
    if flag and flag in policy:
        return bool(policy.get(flag))
    return default


def cluster_lens_primary_stage(policy: dict[str, Any], *, default_scheduler_runtime: bool = False) -> str:
    if default_scheduler_runtime:
        return str(policy.get("defaultSchedulerPrimaryBenchmarkStateStage") or "pre-benchmark")
    return str(policy.get("primaryBenchmarkStateStage") or "post-rescheduling")


def default_rescheduling_profile_path(cycle: dict[str, Any], benchmark_config: dict[str, Any]) -> str:
    family = str(benchmark_config.get("family") or cycle.get("scenarioFamily") or "").strip()
    campaign_type = str(cycle.get("campaignType") or "").strip()
    if family == "network-aware-scheduler" or campaign_type == "network_aware_scheduler" or bool(cycle.get("networkAwareScheduler")):
        return "config/rescheduling/profiles/RS_C9_NETWORK_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json"
    return "config/rescheduling/profiles/RS_C8_RESOURCE_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json"


def scheduler_decision_artifact_name(benchmark_config: dict[str, Any], *, resource_aware_scheduler: bool) -> str:
    scheduler_evidence = benchmark_config.get("schedulerEvidence") or {}
    default_name = "resource-aware-scheduler-decision-evidence.json" if resource_aware_scheduler else "default-scheduler-decision-evidence.json"
    return str(scheduler_evidence.get("artifactName") or default_name)


def latency_profile_id_from_payload(repo_root: Path, latency_profile_value: str | None, benchmark_config: dict[str, Any]) -> str:
    direct = (
        benchmark_config.get("latencyProfileId")
        or ((benchmark_config.get("latencyVariant") or {}).get("latencyProfileId"))
        or ((benchmark_config.get("schedulerModePolicy") or {}).get("latencyProfileId"))
    )
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    if not latency_profile_value:
        return ""
    profile_path = rel_to_repo(repo_root, latency_profile_value, latency_profile_value)
    if not profile_path.exists():
        return Path(str(latency_profile_value)).stem
    try:
        payload = load_json(profile_path)
    except Exception:
        return Path(str(latency_profile_value)).stem
    return str(payload.get("latencyProfileId") or payload.get("profileId") or profile_path.stem).strip()


def should_apply_latency_profile(
    *,
    repo_root: Path,
    cycle: dict[str, Any],
    benchmark_config: dict[str, Any],
    latency_profile_value: str | None,
    scheduler_mode_runtime: bool,
    skip_benchmark_due_to_deployment: bool,
) -> tuple[bool, str]:
    if skip_benchmark_due_to_deployment:
        return False, "deployment_not_benchmark_ready"
    if not latency_profile_value:
        return False, "latency_profile_not_configured"
    latency_profile_id = latency_profile_id_from_payload(repo_root, latency_profile_value, benchmark_config)
    policy = scheduler_mode_policy(cycle, benchmark_config)
    explicit_enabled = policy.get("latencyInjectionEnabled")
    if scheduler_mode_runtime:
        if str(latency_profile_id).strip().upper() in {"", "L0_NONE", "NONE", "NO_LATENCY"}:
            return False, "resource_aware_scheduler_l0_latency_profile"
        if explicit_enabled is False:
            return False, "resource_aware_scheduler_latency_injection_disabled"
        return True, "resource_aware_scheduler_latency_profile_enabled"
    return True, "latency_profile_configured"


def build_multi_tenant_command(
    repo_root: Path,
    scenario_config: Path,
    kubeconfig_path: Path,
    run_id: str,
    output_root: Path | None = None,
) -> list[str]:
    command = [
        *resolve_python_command(),
        script(repo_root, "scripts/load/multi-tenant/run-multi-tenant-locust.py"),
        "--repo-root", str(repo_root),
        "--scenario-config", str(scenario_config),
        "--kubeconfig", str(kubeconfig_path),
        "--run-id", run_id,
    ]
    if output_root is not None:
        command.extend(["--output-root", str(output_root)])
    return command


def multi_tenant_output_root(repo_root: Path, cycle: dict[str, Any], scenario_config: dict[str, Any]) -> Path:
    scenario_id = str(scenario_config.get("scenarioId") or scenario_config.get("variantId") or "scenario")
    root_value = scenario_config.get("resultsRoot") or cycle_results_path(cycle, "benchmark", scenario_family(cycle, scenario_config))
    output_subdir = scenario_config.get("outputSubdir") or scenario_id
    return rel_to_repo(repo_root, f"{root_value}/{output_subdir}", f"{root_value}/{output_subdir}")


def load_multi_tenant_summary(path: Path) -> dict[str, Any]:
    payload = read_json_if_exists(path)
    return payload if isinstance(payload, dict) else {}


def multi_tenant_replica_summary_path(output_root: Path, replica: str) -> Path:
    preferred = output_root / f"run{replica}" / "multi-tenant-summary.json"
    if preferred.exists():
        return preferred
    return output_root / f"run{replica}" / "latest-multi-tenant-summary.json"


def write_multi_tenant_replicate_summary(
    repo_root: Path,
    cycle: dict[str, Any],
    scenario_config: dict[str, Any],
    replica_ids: list[str],
    benchmark_results: list[StepResult],
    run_id: str,
    write_latest_aliases: bool,
) -> dict[str, Any]:
    scenario_id = str(scenario_config.get("scenarioId") or scenario_config.get("variantId") or "scenario")
    output_root = multi_tenant_output_root(repo_root, cycle, scenario_config)
    output_root.mkdir(parents=True, exist_ok=True)
    results_by_replica = {
        item.name.replace("run_multi_tenant_benchmark_run", "", 1): item
        for item in benchmark_results
        if item.name.startswith("run_multi_tenant_benchmark_run")
    }

    replica_results: list[dict[str, Any]] = []
    flattened_tenant_results: list[dict[str, Any]] = []
    for replica in replica_ids:
        replica_summary_path = multi_tenant_replica_summary_path(output_root, replica)
        summary_payload = load_multi_tenant_summary(replica_summary_path)
        runner_result = results_by_replica.get(replica)
        tenant_results = summary_payload.get("tenantResults") if isinstance(summary_payload.get("tenantResults"), list) else []
        for tenant_result in tenant_results:
            if not isinstance(tenant_result, dict):
                continue
            enriched = dict(tenant_result)
            enriched.setdefault("replica", replica)
            enriched.setdefault("replicaId", f"run{replica}")
            enriched.setdefault("replicaSummaryPath", rel_string(repo_root, replica_summary_path) if replica_summary_path.exists() else None)
            flattened_tenant_results.append(enriched)
        replica_results.append({
            "replica": replica,
            "replicaId": f"run{replica}",
            "status": summary_payload.get("status") if summary_payload else (runner_result.status if runner_result else "missing"),
            "runnerStatus": runner_result.status if runner_result else None,
            "runnerExitCode": runner_result.exitCode if runner_result else None,
            "summaryPath": rel_string(repo_root, replica_summary_path) if replica_summary_path.exists() else None,
            "tenantResultCount": len(tenant_results),
            "failedTenantCount": sum(1 for item in tenant_results if isinstance(item, dict) and item.get("status") == "failed"),
            "completedTenantCount": sum(1 for item in tenant_results if isinstance(item, dict) and item.get("status") in {"passed", "completed", "planned", "dry_run"}),
        })

    completed_replicas = [item for item in replica_results if item.get("status") in {"passed", "completed", "planned", "dry_run"}]
    failed_replicas = [item for item in replica_results if item.get("status") == "failed" or item.get("runnerStatus") == "failed"]
    missing_replicas = [item for item in replica_results if item.get("status") == "missing"]
    if replica_results and all(item.get("status") == "dry_run" for item in replica_results):
        status = "planned"
    elif missing_replicas:
        status = "completed_with_missing_replicas"
    elif failed_replicas and not completed_replicas:
        status = "failed"
    elif failed_replicas:
        status = "completed_with_failed_replicas"
    else:
        status = "passed"

    summary_json_path = output_root / "multi-tenant-summary.json"
    summary_txt_path = output_root / "multi-tenant-summary.txt"
    payload = {
        "schemaVersion": "multi-tenant-locust-replicated-scenario/v1",
        "runId": run_id,
        "scenarioId": scenario_id,
        "status": status,
        "replicaCount": len(replica_results),
        "expectedReplicas": replica_ids,
        "completedReplicaCount": len(completed_replicas),
        "failedReplicaCount": len(failed_replicas),
        "missingReplicaCount": len(missing_replicas),
        "tenantResultCount": len(flattened_tenant_results),
        "replicaResults": replica_results,
        "tenantResults": flattened_tenant_results,
    }
    write_json(summary_json_path, payload)
    lines = [
        "Replicated multi-tenant Locust execution summary",
        "================================================",
        f"Run ID: {run_id}",
        f"Scenario: {scenario_id}",
        f"Status: {status}",
        f"Output root: {rel_string(repo_root, output_root)}",
        f"Replicas: {', '.join(replica_ids)}",
        "",
        "Replica results:",
    ]
    for item in replica_results:
        lines.append(
            " - run{replica}: status={status}, runnerStatus={runnerStatus}, tenants={tenantResultCount}, failedTenants={failedTenantCount}".format(
                replica=item.get("replica"),
                status=item.get("status"),
                runnerStatus=item.get("runnerStatus"),
                tenantResultCount=item.get("tenantResultCount"),
                failedTenantCount=item.get("failedTenantCount"),
            )
        )
    write_text(summary_txt_path, "\n".join(lines) + "\n")
    if write_latest_aliases:
        shutil.copyfile(summary_json_path, output_root / "latest-multi-tenant-summary.json")
        shutil.copyfile(summary_txt_path, output_root / "latest-multi-tenant-summary.txt")
    return payload


def multi_tenant_benchmark_artifact_evidence(repo_root: Path, cycle: dict[str, Any], scenario_config: dict[str, Any]) -> dict[str, Any]:
    scenario_id = str(scenario_config.get("scenarioId") or scenario_config.get("variantId") or "scenario")
    output_root = multi_tenant_output_root(repo_root, cycle, scenario_config)
    summary_path = output_root / "multi-tenant-summary.json"
    latest_summary_path = output_root / "latest-multi-tenant-summary.json"
    summary_payload = read_json_if_exists(summary_path) or read_json_if_exists(latest_summary_path)
    tenant_results = summary_payload.get("tenantResults") or []
    replica_results = summary_payload.get("replicaResults") or []
    return {
        "scenarioId": scenario_id,
        "benchmarkOutputRoot": rel_string(repo_root, output_root),
        "summaryPath": rel_string(repo_root, summary_path) if summary_path.exists() else None,
        "latestSummaryPath": rel_string(repo_root, latest_summary_path) if latest_summary_path.exists() else None,
        "summaryPresent": bool(summary_payload),
        "replicaResultCount": len(replica_results),
        "tenantResultCount": len(tenant_results),
        "failedReplicaCount": sum(1 for item in replica_results if item.get("status") == "failed" or item.get("runnerStatus") == "failed"),
        "failedTenantCount": sum(1 for item in tenant_results if item.get("status") == "failed"),
        "completedTenantCount": sum(1 for item in tenant_results if item.get("status") in {"passed", "completed", "planned", "dry_run"}),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute or plan a provider-backed experimental cycle.")
    parser.add_argument("--repo-root", default=".", help="Repository root directory.")
    parser.add_argument("--cycle-config", default="config/experimental-cycles/C9.json", help="Cycle configuration path.")
    parser.add_argument("--tool-path", default="proxmox-k3s", help="proxmox-k3s executable path or command name.")
    parser.add_argument("--provider-config", default="", help="Optional provider configuration override.")
    parser.add_argument("--run-id", default="", help="Optional run identifier. Defaults to a UTC timestamped identifier.")
    parser.add_argument("--baseline-replicas", default="A", help="Comma-separated baseline replica identifiers to execute.")
    parser.add_argument("--benchmark-config", default="", help="Optional benchmark runtime configuration override. This is the canonical option for provider-backed runtime benchmark profiles; baseline-config remains supported as a legacy alias in downstream launchers.")
    parser.add_argument("--base-url", default="", help="Optional LocalAI base URL override for deployment smoke checks.")
    parser.add_argument("--no-port-forward", action="store_true", help="Do not create a LocalAI port-forward during deployment smoke checks.")
    parser.add_argument("--dry-run", action="store_true", help="Write an execution plan without executing runtime commands.")
    parser.add_argument("--continue-on-failure", action="store_true", help="Continue planning/executing subsequent steps after a command failure.")
    parser.add_argument("--allow-metrics-warning", action="store_true", help="Allow non-blocking Metrics API warnings during cluster validation.")
    parser.add_argument("--confirm-delete", action="store_true", help="Allow provider delete actions when lifecycle policies request them.")
    parser.add_argument("--force-freeze", action="store_true", help="Force rebuild of the frozen snapshot.")
    parser.add_argument("--write-latest-aliases", action="store_true", help="Ask subcommands to update their latest artifact aliases when supported.")
    parser.add_argument("--skip-provisioning", action="store_true")
    parser.add_argument("--skip-cluster-validation", action="store_true")
    parser.add_argument("--skip-placement-profile", action="store_true")
    parser.add_argument("--skip-localai-deployment", action="store_true")
    parser.add_argument("--skip-smoke-test", action="store_true")
    parser.add_argument("--skip-minimal-observability", action="store_true")
    parser.add_argument("--skip-latency-injection", action="store_true")
    parser.add_argument("--skip-benchmark", action="store_true")
    parser.add_argument("--skip-diagnosis", action="store_true")
    parser.add_argument("--skip-reporting", action="store_true")
    parser.add_argument("--skip-completion-gate", action="store_true")
    parser.add_argument("--skip-freeze", action="store_true")
    parser.add_argument("--skip-default-scheduler-validation", action="store_true")
    parser.add_argument("--skip-scheduler-capture", action="store_true")
    parser.add_argument("--skip-scheduler-mode-validation", action="store_true", help="Skip static validation of scheduler-aware application manifests.")
    parser.add_argument("--skip-custom-scheduler", action="store_true", help="Skip installation or validation of the custom second scheduler for scheduler-mode variants.")
    parser.add_argument("--skip-mon-agent", action="store_true", help="Skip mon-agent integration and annotation validation for scheduler-mode variants.")
    parser.add_argument("--skip-telemetry-priming", action="store_true", help="Skip the warm-up-only telemetry priming workload while keeping controlled rescheduling available.")
    parser.add_argument("--skip-rescheduling", action="store_true", help="Skip telemetry-primed redeployment/rescheduling for scheduler-mode variants.")
    parser.add_argument("--skip-cluster-lens-capture", action="store_true", help="Skip cluster-lens placement evidence capture steps.")
    parser.add_argument("--cluster-lens-profile", default="", help="Optional cluster-lens capture profile override.")
    parser.add_argument("--cluster-lens-snapshot-url", default="", help="Optional direct cluster-lens /api/snapshot URL override.")
    parser.add_argument("--no-cluster-lens-port-forward", action="store_true", help="Disable kubectl port-forward for cluster-lens capture when no direct URL is supplied.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    cycle_config = rel_to_repo(repo_root, args.cycle_config, "config/experimental-cycles/C9.json")
    cycle = load_json(cycle_config)
    if cycle.get("cycleKind") != "runtime_campaign_variant" and isinstance((cycle.get("campaign") or {}).get("plannedScenarioReferences"), list):
        planned_count = len((cycle.get("campaign") or {}).get("plannedScenarioReferences") or [])
        if planned_count > 0:
            print(
                "This cycle profile describes a comparative campaign with multiple variants. "
                "Use scripts/experimental-cycles/run-experimental-campaign.py or the Start-ExperimentalCampaign launcher, "
                "or execute one generated runtime variant cycle instead.",
                file=sys.stderr,
            )
            return 2
    python_cmd = resolve_python_command()

    run_id = args.run_id.strip() or f"{cycle.get('cycleId', 'cycle')}_{safe_stamp()}"
    pipeline_profiles = cycle.get("pipelineProfiles") or {}
    provider = cycle.get("providerBackedInfrastructure") or {}
    baseline = cycle.get("baseline") or cycle.get("runtimeScenario") or cycle.get("benchmark") or {}
    reporting = cycle.get("reporting") or {}
    completion = cycle.get("completionGate") or {}
    freeze = cycle.get("freeze") or cycle.get("freezeOutputs") or {}

    kubeconfig_path = resolve_cycle_kubeconfig_path(repo_root, cycle)
    benchmark_config = rel_to_repo(
        repo_root,
        args.benchmark_config or baseline.get("benchmarkConfigPath") or baseline.get("configPath") or baseline.get("scenarioConfigPath"),
        "config/scenarios/baseline/B1.json",
    )
    baseline_config = benchmark_config
    baseline_payload = read_json_if_exists(benchmark_config)
    default_scheduler_runtime = is_default_scheduler_runtime(cycle, baseline_payload)
    raw_scenario_config_value = baseline.get("scenarioConfigPath") or baseline_payload.get("scenarioConfigPath")
    raw_scenario_config = rel_to_repo(repo_root, raw_scenario_config_value, "") if raw_scenario_config_value else None
    reference_baseline_config_value = baseline.get("referenceBaselineConfigPath") or baseline_payload.get("referenceBaselineConfigPath")
    reference_baseline_config = rel_to_repo(repo_root, reference_baseline_config_value, "") if reference_baseline_config_value else None
    precheck_profile_value = pipeline_profiles.get("precheck") or baseline_payload.get("precheckProfilePath") or baseline_payload.get("precheckConfigPath")
    precheck_config = rel_to_repo(repo_root, precheck_profile_value, precheck_profile_value) if precheck_profile_value else None
    execution_root = rel_to_repo(repo_root, provider.get("cycleExecutionArtifactRoot"), cycle_results_path(cycle, "execution"))
    execution_root.mkdir(parents=True, exist_ok=True)

    diagnosis_profile = pipeline_profiles.get("technicalDiagnosis") or provider.get("technicalDiagnosisProfilePath") or default_pipeline_profile_path(cycle, "technicalDiagnosis")
    reporting_profile = reporting.get("reportingProfilePath") or pipeline_profiles.get("reporting") or default_pipeline_profile_path(cycle, "reporting")
    completion_profile = completion.get("completionGateProfilePath") or pipeline_profiles.get("completionGate") or default_pipeline_profile_path(cycle, "completionGate")
    freeze_profile = freeze.get("freezeProfilePath") or pipeline_profiles.get("freeze") or default_pipeline_profile_path(cycle, "freeze")
    latency = cycle.get("latencyInjection") or {}
    latency_profile = (
        provider.get("latencyProfilePath")
        or pipeline_profiles.get("latencyInjection")
        or latency.get("latencyProfilePath")
    )
    latency_root = rel_to_repo(repo_root, provider.get("latencyInjectionArtifactRoot") or latency.get("artifactRoot"), cycle_results_path(cycle, "latency-injection"))

    diagnosis_root = rel_to_repo(repo_root, provider.get("technicalDiagnosisArtifactRoot"), cycle_results_path(cycle, "diagnosis"))
    reporting_root = rel_to_repo(repo_root, reporting.get("artifactRoot"), cycle_results_path(cycle, "reporting"))
    completion_root = rel_to_repo(repo_root, completion.get("artifactRoot"), cycle_results_path(cycle, "completion-gate"))
    freeze_root = rel_to_repo(repo_root, freeze.get("artifactRoot"), cycle_results_path(cycle, "freeze"))
    minimal_observability_root = rel_to_repo(repo_root, provider.get("minimalObservabilityArtifactRoot"), cycle_results_path(cycle, "observability", "minimal"))
    scheduler_runtime = cycle.get("networkAwareSchedulerRuntime") or cycle.get("schedulerModeRuntime") or {}
    cluster_lens_stage_policy = cluster_lens_capture_stage_policy(cycle, scheduler_runtime)
    cluster_lens_non_blocking = bool(cluster_lens_stage_policy.get("captureFailureIsNonBlocking", True))
    resource_aware_scheduler_root = rel_to_repo(repo_root, provider.get("networkAwareSchedulerArtifactRoot") or provider.get("schedulerModeArtifactRoot") or scheduler_runtime.get("artifactRoot"), cycle_results_path(cycle, "scheduler-runtime"))
    custom_scheduler_root = rel_to_repo(repo_root, provider.get("customSchedulerArtifactRoot") or scheduler_runtime.get("customSchedulerArtifactRoot"), str(resource_aware_scheduler_root / "custom-scheduler"))
    mon_agent_root = rel_to_repo(repo_root, provider.get("monAgentArtifactRoot") or scheduler_runtime.get("monAgentArtifactRoot"), str(resource_aware_scheduler_root / "mon-agent"))
    network_observability_root = rel_to_repo(repo_root, provider.get("networkObservabilityArtifactRoot") or scheduler_runtime.get("networkObservabilityArtifactRoot"), str(resource_aware_scheduler_root / "mentat"))
    istio_gateway_root = rel_to_repo(repo_root, provider.get("istioGatewayArtifactRoot") or scheduler_runtime.get("istioGatewayArtifactRoot"), str(resource_aware_scheduler_root / "istio"))
    rescheduling_root = rel_to_repo(repo_root, provider.get("reschedulingArtifactRoot") or scheduler_runtime.get("reschedulingArtifactRoot"), str(resource_aware_scheduler_root / "rescheduling"))
    cluster_lens_profile = args.cluster_lens_profile or default_cluster_lens_profile_path(cycle)
    cluster_lens_profile_payload = try_load_json(repo_root, cluster_lens_profile)
    cluster_lens_root = resolve_cluster_lens_root(
        repo_root,
        cluster_lens_profile_payload,
        provider,
        scheduler_runtime,
        resource_aware_scheduler_root / "cluster-lens",
        benchmark_scenario_id(cycle, baseline, baseline_payload),
    )
    cluster_lens_primary = cluster_lens_primary_stage(
        cluster_lens_stage_policy,
        default_scheduler_runtime=default_scheduler_runtime,
    )

    completion_json = rel_to_repo(repo_root, completion.get("latestManifestPath"), str(completion_root / "latest-completion-gate-manifest.json"))
    completion_text = rel_to_repo(repo_root, completion.get("latestTextSummaryPath"), str(completion_root / "latest-completion-gate-summary.txt"))
    diagnosis_json = diagnosis_root / f"{run_id}_diagnosis_all_diagnosis.json"

    steps: list[StepResult] = []
    unsupported_scenario: dict[str, Any] | None = None

    def execute_or_skip(skip: bool, name: str, description: str, command: list[str], artifact_hints: list[str] | None = None) -> StepResult:
        if skip:
            result = skip_step(name, description)
            steps.append(result)
            return result
        result = run_step(
            name=name,
            description=description,
            command=command,
            repo_root=repo_root,
            dry_run=args.dry_run,
            continue_on_failure=args.continue_on_failure,
            artifact_hints=artifact_hints,
        )
        steps.append(result)
        if result.status == "failed" and not args.continue_on_failure:
            raise SystemExit(finalize(1))
        return result

    def with_common(command: list[str]) -> list[str]:
        if args.write_latest_aliases:
            command.append("--write-latest-aliases")
        return command

    def capture_cluster_lens(stage: str, *, primary: bool = False, skip: bool = False) -> StepResult:
        output_root = cluster_lens_stage_output_root(cluster_lens_root, stage, primary=primary)
        step_name = cluster_lens_step_name(stage)
        description = f"Capture cluster-lens topology and Kubernetes placement evidence at the {stage} stage."
        artifact_hint = rel_string(repo_root, output_root)
        stage_enabled = cluster_lens_stage_enabled(
            cluster_lens_stage_policy,
            stage,
            default_scheduler_runtime=default_scheduler_runtime,
        )
        if skip or args.skip_cluster_lens_capture or not stage_enabled:
            result = skip_step(step_name, description)
            result.artifactHints.append(artifact_hint)
            steps.append(result)
            return result
        command = [
            *python_cmd,
            script(repo_root, "scripts/observability/cluster-lens/capture-cluster-lens-snapshot.py"),
            "--repo-root", str(repo_root),
            "--profile-config", cluster_lens_profile,
            "--scenario-config", str(raw_scenario_config or benchmark_config),
            "--kubeconfig", str(kubeconfig_path),
            "--output-dir", str(output_root),
            "--capture-stage", stage,
        ]
        if args.cluster_lens_snapshot_url:
            command.extend(["--snapshot-url", args.cluster_lens_snapshot_url])
        if args.no_cluster_lens_port_forward:
            command.append("--no-port-forward")
        if args.dry_run:
            command.append("--dry-run")
        result = run_step(
            name=step_name,
            description=description,
            command=command,
            repo_root=repo_root,
            dry_run=False,
            continue_on_failure=cluster_lens_non_blocking,
            artifact_hints=[artifact_hint],
        )
        if primary and result.status == "completed":
            promoted, promotion_error = promote_cluster_lens_primary_artifacts(
                repo_root,
                output_root,
                cluster_lens_root,
                stage,
                cluster_lens_stage_policy,
            )
            result.artifactHints.append(rel_string(repo_root, cluster_lens_root))
            if not promoted:
                result.status = "failed"
                result.exitCode = result.exitCode or 1
                result.error = f"cluster_lens_primary_promotion_failed:{promotion_error}"
        if result.status == "failed":
            result.error = result.error or "cluster_lens_capture_failed"
        steps.append(result)
        return result

    def benchmark_output_root() -> Path:
        baseline_id = str(benchmark_scenario_id(cycle, baseline, baseline_payload))
        results_root_value = baseline_payload.get("resultsRoot") or cycle_results_path(cycle, "benchmark", scenario_family(cycle, baseline_payload))
        output_subdir = baseline_payload.get("outputSubdir") or f"{baseline_id}_official_locked"
        return rel_to_repo(repo_root, f"{results_root_value}/{output_subdir}", f"{results_root_value}/{output_subdir}")

    def benchmark_replicas() -> list[str]:
        return [item.strip() for item in args.baseline_replicas.split(",") if item.strip()]

    def replica_precheck_json_path(output_root: Path, scenario_id: str, replica: str) -> Path:
        preferred = output_root / f"{scenario_id}_run{replica}_precheck_precheck.json"
        if preferred.exists():
            return preferred
        return output_root / f"{scenario_id}_run{replica}_precheck.json"

    def benchmark_precheck_failure_evidence(replica_ids: list[str]) -> dict[str, Any]:
        scenario_id = str(benchmark_scenario_id(cycle, baseline, baseline_payload))
        output_root = benchmark_output_root()
        failed_prechecks: list[dict[str, Any]] = []
        for replica in replica_ids:
            precheck_json = replica_precheck_json_path(output_root, scenario_id, replica)
            if not precheck_json.exists():
                continue
            payload = read_json_if_exists(precheck_json)
            summary = payload.get("summary") or {}
            if summary.get("success") is False:
                failed_prechecks.append({
                    "replica": replica,
                    "precheckJson": rel_string(repo_root, precheck_json),
                    "failedChecks": summary.get("failedChecks") or [],
                    "checks": payload.get("checks") or [],
                })
        return {
            "scenarioId": scenario_id,
            "benchmarkOutputRoot": rel_string(repo_root, output_root),
            "failedPrecheckCount": len(failed_prechecks),
            "failedPrechecks": failed_prechecks,
        }

    def benchmark_artifact_evidence(replica_ids: list[str], benchmark_results: list[StepResult] | None = None) -> dict[str, Any]:
        scenario_id = str(benchmark_scenario_id(cycle, baseline, baseline_payload))
        output_root = benchmark_output_root()
        results_by_replica = {
            item.name.replace("run_baseline_", "", 1): item
            for item in (benchmark_results or [])
            if item.name.startswith("run_baseline_")
        }
        replicas: list[dict[str, Any]] = []
        for replica in replica_ids:
            prefix = output_root / f"{scenario_id}_run{replica}"
            precheck_json = replica_precheck_json_path(output_root, scenario_id, replica)
            precheck_payload = read_json_if_exists(precheck_json)
            precheck_summary = precheck_payload.get("summary") or {}
            result = results_by_replica.get(replica)
            replicas.append({
                "replica": replica,
                "runnerStatus": result.status if result else None,
                "runnerExitCode": result.exitCode if result else None,
                "baselineLockPath": rel_string(repo_root, output_root / f"{scenario_id}_run{replica}_baseline-lock.json") if (output_root / f"{scenario_id}_run{replica}_baseline-lock.json").exists() else None,
                "protocolPath": rel_string(repo_root, output_root / f"{scenario_id}_run{replica}_protocol.json") if (output_root / f"{scenario_id}_run{replica}_protocol.json").exists() else None,
                "precheckJson": rel_string(repo_root, precheck_json) if precheck_json.exists() else None,
                "precheckSuccess": precheck_summary.get("success") if precheck_payload else None,
                "clusterPreCapturePresent": (Path(str(prefix) + "_cluster_pre_manifest.json")).exists(),
                "warmupStatsPresent": (Path(str(prefix) + "_warmup_stats.csv")).exists(),
                "measurementStatsPresent": (Path(str(prefix) + "_stats.csv")).exists(),
                "measurementHistoryPresent": (Path(str(prefix) + "_stats_history.csv")).exists(),
                "measurementTargetRequestEvidence": measurement_target_request_evidence(Path(str(prefix) + "_stats.csv")),
                "unsupportedReportPresent": (Path(str(prefix) + "_unsupported.json")).exists(),
            })
        return {
            "scenarioId": scenario_id,
            "benchmarkOutputRoot": rel_string(repo_root, output_root),
            "replicas": replicas,
            "measurementSampleCount": sum(1 for item in replicas if item.get("measurementStatsPresent")),
            "validMeasurementSampleCount": sum(1 for item in replicas if (item.get("measurementTargetRequestEvidence") or {}).get("validTargetRequestsPresent") is True),
            "invalidMeasurementSampleCount": sum(1 for item in replicas if item.get("measurementStatsPresent") and (item.get("measurementTargetRequestEvidence") or {}).get("validTargetRequestsPresent") is not True),
            "warmupSampleCount": sum(1 for item in replicas if item.get("warmupStatsPresent")),
            "precheckSuccessCount": sum(1 for item in replicas if item.get("precheckSuccess") is True),
            "failedRunnerCount": sum(1 for item in replicas if item.get("runnerStatus") == "failed"),
            "unsupportedReportCount": sum(1 for item in replicas if item.get("unsupportedReportPresent")),
        }

    def latency_profile_evidence() -> dict[str, Any]:
        if not latency_profile:
            return {}
        profile_path = rel_to_repo(repo_root, latency_profile, latency_profile)
        payload = read_json_if_exists(profile_path)
        emulation = payload.get("networkEmulation") or {}
        target = payload.get("target") or {}
        return {
            "latencyProfilePath": rel_string(repo_root, profile_path),
            "latencyProfileId": payload.get("latencyProfileId") or payload.get("profileId"),
            "latencyCategory": payload.get("latencyCategory"),
            "delayMs": emulation.get("delayMs"),
            "jitterMs": emulation.get("jitterMs"),
            "packetLossPercent": emulation.get("packetLossPercent"),
            "networkInterface": emulation.get("networkInterface"),
            "targetNodePolicy": target.get("targetNodePolicy"),
        }

    def can_classify_latency_pre_benchmark_failure(artifact_evidence: dict[str, Any]) -> bool:
        if not latency_profile or not latency_applied:
            return False
        replicas = artifact_evidence.get("replicas") or []
        if not replicas:
            return False
        if artifact_evidence.get("measurementSampleCount", 0) > 0:
            return False
        if artifact_evidence.get("failedRunnerCount", 0) == 0:
            return False
        return all(
            item.get("runnerStatus") == "failed"
            and item.get("precheckSuccess") is True
            and item.get("clusterPreCapturePresent") is True
            and item.get("measurementStatsPresent") is False
            for item in replicas
        )

    def can_classify_latency_invalid_measurement_failure(artifact_evidence: dict[str, Any]) -> bool:
        if not latency_profile or not latency_applied:
            return False
        replicas = artifact_evidence.get("replicas") or []
        if not replicas:
            return False
        if artifact_evidence.get("validMeasurementSampleCount", 0) > 0:
            return False
        if artifact_evidence.get("failedRunnerCount", 0) == 0:
            return False
        return all(
            item.get("runnerStatus") == "failed"
            and item.get("precheckSuccess") is True
            and item.get("clusterPreCapturePresent") is True
            and (
                item.get("measurementStatsPresent") is False
                or (item.get("measurementTargetRequestEvidence") or {}).get("validTargetRequestsPresent") is not True
                or item.get("unsupportedReportPresent") is True
            )
            for item in replicas
        )

    def write_unsupported_reports(stage: str, reason: str, evidence: dict[str, Any] | None = None) -> list[str]:
        if args.dry_run:
            return []
        scenario_id = str(benchmark_scenario_id(cycle, baseline, baseline_payload))
        output_root = benchmark_output_root()
        output_root.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        fixed_dimensions = baseline_payload.get("fixedDimensions") or {}
        resource_variant = baseline_payload.get("resourceVariant") or {}
        node_count_variant = baseline_payload.get("nodeCountVariant") or {}
        latency_variant = baseline_payload.get("latencyVariant") or {}
        deployment_evidence = {}
        if isinstance(evidence, dict) and evidence.get("deploymentManifestPath"):
            manifest_path = resolve_artifact_path(repo_root, evidence.get("deploymentManifestPath"))
            deployment_manifest = read_json_if_exists(manifest_path) if manifest_path is not None else {}
            if deployment_manifest:
                deployment_evidence = deployment_constraint_evidence(repo_root, deployment_manifest)
        evidence_text = json.dumps(evidence or {}, ensure_ascii=False)
        evidence_kinds = sorted(set(deployment_evidence.get("evidenceKinds", [])) | classify_evidence_text(reason) | classify_evidence_text(stage) | classify_evidence_text(evidence_text))
        scenario_family = baseline_payload.get("family")
        if not scenario_family:
            if str(scenario_id).startswith("RV_"):
                scenario_family = "resource-variation"
            elif str(scenario_id).startswith("NC_"):
                scenario_family = "node-count-variation"
            elif str(scenario_id).startswith("PLC_"):
                scenario_family = "placement-variation"
            elif str(scenario_id).startswith("LI_"):
                scenario_family = "latency-injection"
            elif str(scenario_id).startswith("MT_"):
                scenario_family = "multi-tenancy"
            else:
                scenario_family = "provider-backed"
        base_payload = {
            "family": scenario_family,
            "scenario": scenario_id,
            "scenarioId": scenario_id,
            "status": "unsupported_under_current_constraints",
            "namespace": baseline_payload.get("namespace") or "localai-benchmark",
            "placementType": baseline_payload.get("resolvedPlacementType") or fixed_dimensions.get("resolvedPlacementType"),
            "expectedWorkerCount": baseline_payload.get("resolvedWorkerCount") or fixed_dimensions.get("resolvedWorkerCount"),
            "reason": reason,
            "stage": stage,
            "evidence": evidence or {},
            "evidenceKinds": evidence_kinds,
            "schedulerEvidence": deployment_evidence,
            "diagnostics": [],
            "infrastructureProfileId": provider.get("infrastructureProfileId"),
            "providerBindingId": provider.get("providerBindingId"),
            "resourceVariant": resource_variant,
            "nodeCountVariant": node_count_variant,
            "latencyVariant": latency_variant,
            "latencyProfileId": baseline_payload.get("latencyProfileId") or latency_variant.get("latencyProfileId"),
            "timeoutSeconds": baseline_payload.get("requestTimeoutSeconds"),
            "model": baseline_payload.get("resolvedModelName"),
        }
        for replica in benchmark_replicas():
            payload = dict(base_payload)
            payload["replica"] = replica
            path = output_root / f"{scenario_id}_run{replica}_unsupported.json"
            write_json(path, payload)
            written.append(rel_string(repo_root, path))
        return written

    def append_blocked_steps(reason: str, blocked_names: list[str]) -> None:
        descriptions = {
            "validate_cluster": "Validate API access, node readiness, K3s components, storage and Metrics API.",
            "resolve_placement_profile": "Resolve the placement profile used by the application topology.",
            "validate_default_scheduler_manifests": "Validate that default-scheduler Kubernetes manifests do not contain hard placement controls.",
            "deploy_localai": "Deploy the LocalAI application topology and run API checks unless disabled.",
            "capture_scheduler_decisions": "Capture runtime scheduler pod-to-node decisions.",
            "capture_observability_after_deployment": "Capture minimal cluster evidence after the application deployment.",
            "apply_latency_profile": "Apply the configured network-latency profile before benchmark execution.",
            "run_baseline": "Execute a benchmark replica.",
            "run_multi_tenant_benchmark": "Execute the tenant-scoped multi-tenant benchmark.",
            "capture_observability_after_benchmark": "Capture minimal cluster evidence after the benchmark.",
        }
        for name in blocked_names:
            if name == "run_baseline":
                for replica in [item.strip() for item in args.baseline_replicas.split(",") if item.strip()]:
                    steps.append(blocked_step(
                        f"run_baseline_{replica}",
                        f"Skip benchmark replica {replica} because required infrastructure/application preconditions were not satisfied.",
                        reason,
                    ))
            elif name == "run_multi_tenant_benchmark":
                for replica in [item.strip() for item in args.baseline_replicas.split(",") if item.strip()]:
                    steps.append(blocked_step(
                        f"run_multi_tenant_benchmark_run{replica}",
                        f"Skip multi-tenant benchmark replica run{replica} because required infrastructure/application preconditions were not satisfied.",
                        reason,
                    ))
            else:
                steps.append(blocked_step(name, descriptions.get(name, name), reason))

    def fail_fast_after_precondition(stage: str, reason: str, blocked_names: list[str], exit_code: int = 1) -> int:
        nonlocal unsupported_scenario
        unsupported_artifacts = write_unsupported_reports(stage, reason, {"blockedSteps": blocked_names})
        unsupported_scenario = {
            "stage": stage,
            "status": "failed_precondition",
            "reason": reason,
            "canProceedToBenchmark": False,
            "unsupportedArtifacts": unsupported_artifacts,
        }
        append_blocked_steps(reason, blocked_names)
        return finalize(0)

    def derive_cycle_status() -> str:
        if args.dry_run:
            return "dry_run"
        if unsupported_scenario is not None or any(step.status in {"unsupported", "skipped_due_to_unsupported_scenario", "skipped_due_to_failed_precondition"} for step in steps):
            return "completed_with_unsupported_scenario"
        if any(step.status == "failed" for step in steps):
            return "failed"
        if any(step.status == "skipped" for step in steps):
            return "completed_with_skipped_steps"
        return "completed"

    def build_cycle_execution_manifest(status: str, execution_stage: str) -> dict[str, Any]:
        return {
            "schemaVersion": "provider-backed-cycle-execution/v1",
            "cycleId": cycle.get("cycleId"),
            "cycleName": cycle.get("cycleName"),
            "runId": run_id,
            "status": status,
            "executionStage": execution_stage,
            "dryRun": bool(args.dry_run),
            "createdAt": utc_now(),
            "repoRoot": str(repo_root),
            "cycleConfig": rel_string(repo_root, cycle_config),
            "provider": provider.get("provider"),
            "infrastructureProfileId": provider.get("infrastructureProfileId"),
            "providerBindingId": provider.get("providerBindingId"),
            "clusterLifecycleMode": provider.get("clusterLifecycleMode"),
            "destroyClusterAfterCycle": bool(provider.get("destroyClusterAfterCycle", False)),
            "baselineId": baseline.get("baselineId"),
            "benchmarkConfig": rel_string(repo_root, benchmark_config),
            "runtimeBenchmarkConfig": rel_string(repo_root, benchmark_config),
            "referenceBaselineConfig": rel_string(repo_root, reference_baseline_config) if reference_baseline_config is not None else None,
            "referenceBaselineId": baseline.get("referenceBaselineId") or baseline_payload.get("referenceBaselineId"),
            "scenarioConfig": rel_string(repo_root, raw_scenario_config) if raw_scenario_config is not None else None,
            "referenceScenarioId": (cycle.get("referenceScenario") or {}).get("referenceScenarioId") or (cycle.get("baseline") or {}).get("referenceScenarioId") or baseline_payload.get("referenceScenarioId"),
            "referenceScenarioConfigPath": (cycle.get("referenceScenario") or {}).get("referenceScenarioConfigPath") or (cycle.get("baseline") or {}).get("referenceScenarioConfigPath") or baseline_payload.get("referenceScenarioConfigPath"),
            "legacyCompatibility": {
                "baselineConfig": rel_string(repo_root, benchmark_config),
                "baselineConfigRole": "legacy_alias_for_runtime_benchmark_config",
                "reason": "The baselineConfig field is retained only as a legacy manifest alias for consumers that still expect the historical key; provider-backed cycles use benchmarkConfig and runtimeBenchmarkConfig as the canonical runtime benchmark references."
            },
            "kubeconfigPath": rel_string(repo_root, kubeconfig_path),
            "executionRoot": rel_string(repo_root, execution_root),
            "artifacts": {
                "diagnosisJson": rel_string(repo_root, diagnosis_json),
                "reportingRoot": rel_string(repo_root, reporting_root),
                "completionGateManifest": rel_string(repo_root, completion_json),
                "completionGateSummary": rel_string(repo_root, completion_text),
                "freezeRoot": rel_string(repo_root, freeze_root),
                "latencyInjectionRoot": rel_string(repo_root, latency_root),
                "schedulerRuntimeRoot": rel_string(repo_root, resource_aware_scheduler_root),
                "customSchedulerRoot": rel_string(repo_root, custom_scheduler_root),
                "monAgentRoot": rel_string(repo_root, mon_agent_root),
                "networkObservabilityRoot": rel_string(repo_root, network_observability_root),
                "istioGatewayRoot": rel_string(repo_root, istio_gateway_root),
                "reschedulingRoot": rel_string(repo_root, rescheduling_root),
                "clusterLensRoot": rel_string(repo_root, cluster_lens_root),
            },
            "unsupportedScenario": unsupported_scenario,
            "steps": [step.__dict__ for step in steps],
        }

    def build_cycle_execution_summary(status: str, execution_stage: str) -> str:
        lines = [
            "Provider-backed cycle execution summary",
            "=======================================",
            f"Cycle: {cycle.get('cycleId')} - {cycle.get('cycleName')}",
            f"Run: {run_id}",
            f"Status: {status}",
            f"Execution stage: {execution_stage}",
            f"Dry run: {args.dry_run}",
            "",
            "Steps:",
        ]
        for step in steps:
            lines.append(f"- {step.name}: {step.status} (exitCode={step.exitCode})")
            if step.command:
                lines.append(f"  command: {as_command_text(step.command)}")
            if step.error:
                lines.append(f"  error: {step.error}")
        return "\n".join(lines) + "\n"

    def write_cycle_execution_artifacts(
        *,
        execution_stage: str,
        force_latest_aliases: bool = False,
    ) -> tuple[Path, Path]:
        status = derive_cycle_status()
        manifest = build_cycle_execution_manifest(status, execution_stage)
        manifest_path = execution_root / f"{run_id}_cycle_execution_manifest.json"
        summary_path = execution_root / f"{run_id}_cycle_execution_summary.txt"
        write_json(manifest_path, manifest)
        write_text(summary_path, build_cycle_execution_summary(status, execution_stage))
        if force_latest_aliases or args.write_latest_aliases:
            write_json(execution_root / "latest-cycle-execution-manifest.json", manifest)
            write_text(execution_root / "latest-cycle-execution-summary.txt", summary_path.read_text(encoding="utf-8"))
        return manifest_path, summary_path

    def finalize(exit_code: int = 0) -> int:
        write_cycle_execution_artifacts(
            execution_stage="finalized",
            force_latest_aliases=not args.skip_freeze,
        )
        return exit_code

    try:
        prov_cmd = with_common(python_cmd + [
            script(repo_root, "scripts/infrastructure/provision/run-provider-backed-provisioning.py"),
            "--repo-root", str(repo_root),
            "--cycle-config", str(cycle_config),
            "--action", "provision",
            "--tool-path", args.tool_path,
            "--run-id", f"{run_id}_provisioning",
        ])
        if args.provider_config:
            prov_cmd.extend(["--provider-config", args.provider_config])
        if args.confirm_delete:
            prov_cmd.append("--confirm-delete")
        if args.dry_run:
            prov_cmd.append("--dry-run")
        provisioning_result = execute_or_skip(args.skip_provisioning, "provision_cluster", "Create or reuse the provider-backed K3s cluster.", prov_cmd, [provider.get("provisioningLogRoot", "")])
        if provisioning_result.status == "failed":
            provisioning_result.error = provisioning_result.error or "provider_backed_provisioning_failed"
            return fail_fast_after_precondition(
                "infrastructure_provisioning",
                "provider_backed_provisioning_failed",
                [
                    "validate_cluster",
                    "resolve_placement_profile",
                    "deploy_localai",
                    "capture_observability_after_deployment",
                    "apply_latency_profile",
                    "run_baseline",
                    "capture_observability_after_benchmark",
                ],
                1,
            )

        val_cmd = with_common(python_cmd + [
            script(repo_root, "scripts/infrastructure/validation/run-provider-backed-cluster-validation.py"),
            "--repo-root", str(repo_root),
            "--cycle-config", str(cycle_config),
            "--kubeconfig", str(kubeconfig_path),
            "--validation-id", f"{run_id}_cluster_validation",
        ])
        if args.allow_metrics_warning:
            val_cmd.append("--allow-metrics-warning")
        if args.dry_run:
            val_cmd.append("--dry-run")
        validation_result = execute_or_skip(args.skip_cluster_validation, "validate_cluster", "Validate API access, node readiness, K3s components, storage and Metrics API.", val_cmd, [provider.get("clusterValidationArtifactRoot", "")])
        if validation_result.status == "failed":
            validation_result.error = validation_result.error or "cluster_validation_failed"
            return fail_fast_after_precondition(
                "cluster_validation",
                "cluster_validation_failed",
                [
                    "resolve_placement_profile",
                    "deploy_localai",
                    "capture_observability_after_deployment",
                    "apply_latency_profile",
                    "run_baseline",
                    "capture_observability_after_benchmark",
                ],
                1,
            )

        scheduler_mode_runtime = is_scheduler_mode_runtime(cycle, baseline_payload)
        scheduler_mode = scheduler_mode_variant(cycle, baseline_payload) if scheduler_mode_runtime else ""
        expected_scheduler_name = scheduler_mode_scheduler_name(cycle, baseline_payload) or "scheduler-plugins-scheduler"

        if scheduler_mode_runtime and scheduler_mode in {"loadaware", "networkaware"}:
            default_custom_scheduler_profile_path = "config/scheduler/profiles/CS_C9_LOADAWARE_SECOND_SCHEDULER.json" if str(cycle.get("cycleId") or "").upper() == "C9" else "config/scheduler/profiles/CS_C8_LOADAWARE_SECOND_SCHEDULER.json"
            custom_scheduler_profile = scheduler_runtime_path(
                cycle,
                baseline_payload,
                "customSchedulerProfilePath",
                default_custom_scheduler_profile_path,
            )
            custom_scheduler_cmd = with_common(python_cmd + [
                script(repo_root, "scripts/scheduler/custom/run-custom-scheduler.py"),
                "--repo-root", str(repo_root),
                "--profile-config", custom_scheduler_profile,
                "--action", "install",
                "--kubeconfig", str(kubeconfig_path),
                "--output-root", str(custom_scheduler_root),
                "--run-id", f"{run_id}_custom_scheduler_install",
            ])
            if args.dry_run:
                custom_scheduler_cmd.append("--dry-run")
            custom_scheduler_result = execute_or_skip(
                args.skip_custom_scheduler,
                "install_custom_scheduler",
                "Install and validate the custom second scheduler before deploying pods that reference it.",
                custom_scheduler_cmd,
                [str(custom_scheduler_root)],
            )
            if custom_scheduler_result.status == "failed":
                custom_scheduler_result.error = custom_scheduler_result.error or "custom_scheduler_installation_failed"
                return fail_fast_after_precondition(
                    "custom_scheduler_installation",
                    custom_scheduler_result.error,
                    [
                        "resolve_placement_profile",
                        "deploy_localai",
                        "validate_scheduler_mode_manifests",
                        "apply_mon_agent",
                        "telemetry_primed_rescheduling",
                        "run_multi_tenant_benchmark",
                        "capture_observability_after_benchmark",
                    ],
                    1,
                )
        elif scheduler_mode_runtime:
            steps.append(skip_step(
                "install_custom_scheduler",
                "This scheduler-aware variant uses the Kubernetes default scheduler, so no second scheduler is installed.",
            ))

        if default_scheduler_runtime:
            steps.append(skip_step(
                "resolve_placement_profile",
                "Runtime scheduler scenarios intentionally do not resolve a controlled placement profile.",
            ))
        else:
            placement_cmd = with_common(python_cmd + [
                script(repo_root, "scripts/placement/resolve-placement-profile.py"),
                "--repo-root", str(repo_root),
                "--cycle-config", str(cycle_config),
                "--output-root", str(rel_to_repo(repo_root, provider.get("placementProfileArtifactRoot"), cycle_results_path(cycle, "placement"))),
                "--resolution-id", f"{run_id}_placement",
            ])
            placement_result = execute_or_skip(args.skip_placement_profile, "resolve_placement_profile", "Resolve the placement profile used by the application topology.", placement_cmd, [provider.get("placementProfileArtifactRoot", "")])
            if placement_result.status == "failed":
                placement_result.error = placement_result.error or "placement_profile_resolution_failed"
                return fail_fast_after_precondition(
                    "placement_profile_resolution",
                    "placement_profile_resolution_failed",
                    [
                        "deploy_localai",
                        "capture_observability_after_deployment",
                        "apply_latency_profile",
                        "run_baseline",
                        "capture_observability_after_benchmark",
                    ],
                    1,
                )

        if scheduler_mode_runtime:
            application_topology = baseline_payload.get("applicationTopology") or {}
            predeploy_scan_root = application_topology.get("topologyDir") or "infra/k8s/compositions/resource-aware-scheduler"
            validation_script = scheduler_runtime_path(
                cycle,
                baseline_payload,
                "manifestValidationScript",
                "scripts/validation/scheduler/validate-scheduler-mode-manifests.py",
            )
            predeploy_validation_cmd = [
                *python_cmd,
                script(repo_root, validation_script),
                "--repo-root", str(repo_root),
                "--scan-root", str(predeploy_scan_root),
                "--mode", scheduler_mode,
                "--expected-scheduler-name", expected_scheduler_name,
                "--render-kustomize",
                "--require-render",
                "--json",
            ]
            predeploy_validation_result = execute_or_skip(
                args.skip_scheduler_mode_validation,
                "validate_scheduler_mode_manifests",
                "Validate rendered scheduler-aware manifests before application deployment.",
                predeploy_validation_cmd,
                [str(predeploy_scan_root)],
            )
            if predeploy_validation_result.status == "failed":
                predeploy_validation_result.error = predeploy_validation_result.error or "scheduler_mode_manifest_validation_failed"
                return fail_fast_after_precondition(
                    "scheduler_mode_manifest_validation",
                    predeploy_validation_result.error,
                    [
                        "deploy_localai",
                        "apply_mon_agent",
                        "telemetry_priming_workload",
                        "validate_mon_agent_annotations",
                        "capture_scheduler_decisions",
                        "telemetry_primed_rescheduling",
                        "run_multi_tenant_benchmark",
                        "capture_observability_after_benchmark",
                    ],
                    1,
                )

        dep_cmd = with_common(python_cmd + [
            script(repo_root, "scripts/application/deployment/run-provider-backed-localai-deployment.py"),
            "--repo-root", str(repo_root),
            "--cycle-config", str(cycle_config),
            "--action", "deploy",
            "--kubeconfig", str(kubeconfig_path),
            "--deployment-id", f"{run_id}_localai_deployment",
        ])
        if args.skip_smoke_test:
            dep_cmd.append("--skip-smoke-test")
        if args.base_url:
            dep_cmd.extend(["--base-url", args.base_url])
        if args.no_port_forward:
            dep_cmd.append("--no-port-forward")
        if args.dry_run:
            dep_cmd.append("--dry-run")
        deployment_description = "Deploy the scheduler-aware LocalAI topology and run API readiness checks unless disabled." if scheduler_mode_runtime else "Deploy the LocalAI application topology and run API checks unless disabled."
        deployment_result = run_step(
            name="deploy_localai",
            description=deployment_description,
            command=dep_cmd,
            repo_root=repo_root,
            dry_run=args.dry_run,
            continue_on_failure=True,
            artifact_hints=[provider.get("applicationDeploymentArtifactRoot", "")],
        ) if not args.skip_localai_deployment else skip_step("deploy_localai", deployment_description)

        deployment_manifest_path = latest_application_deployment_manifest_path(repo_root, cycle)
        deployment_manifest = read_json_if_exists(deployment_manifest_path) if not args.skip_localai_deployment and not args.dry_run else {}
        skip_benchmark_due_to_deployment, deployment_decision_reason = (
            deployment_requires_benchmark_skip(deployment_manifest)
            if not args.skip_localai_deployment and not args.dry_run
            else (False, "deployment_gate_not_evaluated")
        )
        if deployment_result.status == "failed" and skip_benchmark_due_to_deployment:
            deployment_result.status = "unsupported"
            deployment_result.error = deployment_decision_reason
            deployment_result.artifactHints.append(rel_string(repo_root, deployment_manifest_path))
            deployment_result.exitCode = 0
            unsupported_artifacts = write_unsupported_reports(
                "localai_deployment",
                deployment_decision_reason,
                {"deploymentManifestPath": rel_string(repo_root, deployment_manifest_path), "deploymentErrors": deployment_manifest.get("errors", [])},
            )
            unsupported_scenario = {
                "stage": "localai_deployment",
                "status": deployment_manifest.get("status"),
                "reason": deployment_decision_reason,
                "manifestPath": rel_string(repo_root, deployment_manifest_path),
                "canProceedToBenchmark": (deployment_manifest.get("decision") or {}).get("canProceedToBenchmark"),
                "deploymentErrors": deployment_manifest.get("errors", []),
                "unsupportedArtifacts": unsupported_artifacts,
            }
        steps.append(deployment_result)
        if not args.skip_localai_deployment:
            capture_cluster_lens("post-deployment")
        if deployment_result.status == "failed" and not skip_benchmark_due_to_deployment:
            deployment_result.error = deployment_result.error or deployment_decision_reason or "localai_deployment_failed"
            return fail_fast_after_precondition(
                "localai_deployment",
                deployment_result.error,
                [
                    "capture_observability_after_deployment",
                    "apply_latency_profile",
                    "run_baseline",
                    "capture_observability_after_benchmark",
                ],
                1,
            )
        if deployment_result.status == "failed" and not args.continue_on_failure:
            raise SystemExit(finalize(1))

        if scheduler_mode_runtime and not skip_benchmark_due_to_deployment:
            istio_gateway_profile = scheduler_runtime_path(
                cycle,
                baseline_payload,
                "istioGatewayProfilePath",
                provider.get("istioGatewayProfilePath") or "config/istio-gateway/profiles/IG_LOCALAI_GATEWAY_ROUTED_C9.json",
            )
            istio_gateway_cmd = with_common(python_cmd + [
                script(repo_root, "scripts/istio/validate-istio-gateway.py"),
                "--repo-root", str(repo_root),
                "--profile-config", istio_gateway_profile,
                "--scenario-config", str(raw_scenario_config or benchmark_config),
                "--kubeconfig", str(kubeconfig_path),
                "--output-root", str(istio_gateway_root),
            ])
            if args.dry_run:
                istio_gateway_cmd.append("--dry-run")
            istio_gateway_result = execute_or_skip(
                False,
                "validate_istio_gateway",
                "Validate Istio Gateway API resources and runtime routing prerequisites for gateway-routed LocalAI traffic.",
                istio_gateway_cmd,
                [str(istio_gateway_root)],
            )
            if istio_gateway_result.status == "failed":
                istio_gateway_result.error = istio_gateway_result.error or "istio_gateway_validation_failed"
                return fail_fast_after_precondition(
                    "istio_gateway_validation",
                    istio_gateway_result.error,
                    [
                        "apply_mon_agent",
                        "telemetry_priming_workload",
                        "validate_mon_agent_annotations",
                        "validate_network_observability",
                        "apply_latency_profile",
                        "telemetry_primed_rescheduling",
                        "run_multi_tenant_benchmark",
                        "capture_observability_after_benchmark",
                    ],
                    1,
                )

        if default_scheduler_runtime and not scheduler_mode_runtime and not skip_benchmark_due_to_deployment:
            default_scheduler_topology = baseline_payload.get("defaultSchedulerTopology") or {}
            application_topology = baseline_payload.get("applicationTopology") or {}
            scan_root = (
                default_scheduler_topology.get("compositionPath")
                or application_topology.get("topologyDir")
                or "infra/k8s/compositions/default-scheduler"
            )
            manifest_validation_cmd = [
                *python_cmd,
                script(repo_root, "scripts/validation/scheduler/validate-default-scheduler-manifests.py"),
                "--repo-root", str(repo_root),
                "--scan-root", str(scan_root),
                "--render-kustomize",
                "--json",
            ]
            manifest_validation_result = execute_or_skip(
                args.skip_default_scheduler_validation,
                "validate_default_scheduler_manifests",
                "Validate that default-scheduler Kubernetes manifests contain no hard placement controls.",
                manifest_validation_cmd,
                [str(scan_root)],
            )
            if manifest_validation_result.status == "failed":
                manifest_validation_result.error = manifest_validation_result.error or "default_scheduler_manifest_validation_failed"
                return fail_fast_after_precondition(
                    "default_scheduler_manifest_validation",
                    manifest_validation_result.error,
                    [
                        "apply_latency_profile",
                        "run_multi_tenant_benchmark",
                        "capture_observability_after_benchmark",
                    ],
                    1,
                )

        if scheduler_mode_runtime and not skip_benchmark_due_to_deployment:
            mon_agent_profile = scheduler_runtime_path(
                cycle,
                baseline_payload,
                "monAgentProfilePath",
                "config/mon-agent/profiles/MA_RESOURCE_AWARE.json",
            )
            mon_agent_cmd = with_common(python_cmd + [
                script(repo_root, "scripts/observability/mon-agent/run-mon-agent.py"),
                "--repo-root", str(repo_root),
                "--profile-config", mon_agent_profile,
                "--scenario-config", str(benchmark_config),
                "--action", "apply",
                "--kubeconfig", str(kubeconfig_path),
                "--output-root", str(mon_agent_root),
                "--run-id", f"{run_id}_mon_agent_apply",
            ])
            if args.dry_run:
                mon_agent_cmd.append("--dry-run")
            mon_agent_result = execute_or_skip(
                args.skip_mon_agent,
                "apply_mon_agent",
                "Prepare mon-agent integration, label application namespaces and collect initial runtime annotation evidence.",
                mon_agent_cmd,
                [str(mon_agent_root)],
            )
            if mon_agent_result.status == "failed":
                mon_agent_result.error = mon_agent_result.error or "mon_agent_annotation_setup_failed"
                return fail_fast_after_precondition(
                    "mon_agent_annotation_setup",
                    mon_agent_result.error,
                    [
                        "telemetry_priming_workload",
                        "validate_mon_agent_annotations",
                        "capture_scheduler_decisions",
                        "telemetry_primed_rescheduling",
                        "run_multi_tenant_benchmark",
                        "capture_observability_after_benchmark",
                    ],
                    1,
                )

            telemetry_priming_root = resource_aware_scheduler_root / "telemetry-priming"
            telemetry_priming_cmd = build_multi_tenant_command(
                repo_root,
                benchmark_config,
                kubeconfig_path,
                f"{run_id}_telemetry_priming",
                telemetry_priming_root,
            )
            telemetry_priming_cmd.extend(["--warm-up-only", "--write-latest-aliases"])
            if args.dry_run:
                telemetry_priming_cmd.append("--dry-run")
            telemetry_priming_result = execute_or_skip(
                args.skip_telemetry_priming,
                "telemetry_priming_workload",
                "Run a warm-up-only workload to let mon-agent observe non-idle LocalAI resource usage before controlled rescheduling.",
                telemetry_priming_cmd,
                [str(telemetry_priming_root)],
            )
            if telemetry_priming_result.status == "failed":
                telemetry_priming_result.error = telemetry_priming_result.error or "telemetry_priming_workload_failed"
                return fail_fast_after_precondition(
                    "telemetry_priming_workload",
                    telemetry_priming_result.error,
                    [
                        "validate_mon_agent_annotations",
                        "capture_scheduler_decisions",
                        "telemetry_primed_rescheduling",
                        "run_multi_tenant_benchmark",
                        "capture_observability_after_benchmark",
                    ],
                    1,
                )

            mon_agent_validate_cmd = with_common(python_cmd + [
                script(repo_root, "scripts/observability/mon-agent/run-mon-agent.py"),
                "--repo-root", str(repo_root),
                "--profile-config", mon_agent_profile,
                "--scenario-config", str(benchmark_config),
                "--action", "validate",
                "--kubeconfig", str(kubeconfig_path),
                "--output-root", str(mon_agent_root),
                "--run-id", f"{run_id}_mon_agent_validate",
            ])
            if args.dry_run:
                mon_agent_validate_cmd.append("--dry-run")
            mon_agent_validate_result = execute_or_skip(
                args.skip_mon_agent,
                "validate_mon_agent_annotations",
                "Validate that mon-agent has produced the required resource and network-aware annotations after telemetry priming.",
                mon_agent_validate_cmd,
                [str(mon_agent_root)],
            )
            if mon_agent_validate_result.status == "failed":
                mon_agent_validate_result.error = mon_agent_validate_result.error or "mon_agent_annotation_validation_failed"
                return fail_fast_after_precondition(
                    "mon_agent_annotation_validation",
                    mon_agent_validate_result.error,
                    [
                        "validate_network_observability",
                        "capture_scheduler_decisions",
                        "telemetry_primed_rescheduling",
                        "run_multi_tenant_benchmark",
                        "capture_observability_after_benchmark",
                    ],
                    1,
                )

            network_observability_profile = scheduler_runtime_path(
                cycle,
                baseline_payload,
                "networkObservabilityProfilePath",
                provider.get("networkObservabilityProfilePath") or "config/network-observability/profiles/NO_MENTAT_C9.json",
            )
            network_observability_cmd = with_common(python_cmd + [
                script(repo_root, "scripts/network-observability/validate-mentat.py"),
                "--repo-root", str(repo_root),
                "--profile-config", network_observability_profile,
                "--action", "validate",
                "--kubeconfig", str(kubeconfig_path),
                "--output-root", str(network_observability_root),
                "--run-id", f"{run_id}_mentat_validate",
            ])
            if args.dry_run:
                network_observability_cmd.append("--dry-run")
            network_observability_result = execute_or_skip(
                False,
                "validate_network_observability",
                "Validate Mentat network observability evidence and required node-level network annotation telemetry after mon-agent validation.",
                network_observability_cmd,
                [str(network_observability_root)],
            )
            if network_observability_result.status == "failed":
                network_observability_result.error = network_observability_result.error or "network_observability_validation_failed"
                return fail_fast_after_precondition(
                    "network_observability_validation",
                    network_observability_result.error,
                    [
                        "capture_scheduler_decisions",
                        "telemetry_primed_rescheduling",
                        "run_multi_tenant_benchmark",
                        "capture_observability_after_benchmark",
                    ],
                    1,
                )

            capture_cluster_lens("post-telemetry-priming")

        if default_scheduler_runtime and not scheduler_mode_runtime and not skip_benchmark_due_to_deployment:
            scheduler_evidence = baseline_payload.get("schedulerEvidence") or {}
            default_scheduler_output_dir = cycle_results_path(cycle, "scheduler", benchmark_scenario_id(cycle, baseline, baseline_payload))
            scheduler_output_dir = scheduler_evidence.get("artifactRoot") or default_scheduler_output_dir
            scheduler_capture_cmd = with_common([
                *python_cmd,
                script(repo_root, "scripts/observability/scheduler/capture-scheduler-decisions.py"),
                "--repo-root", str(repo_root),
                "--scenario-config", str(benchmark_config),
                "--kubeconfig", str(kubeconfig_path),
                "--output-dir", str(rel_to_repo(repo_root, scheduler_output_dir, scheduler_output_dir)),
                "--output-name", scheduler_decision_artifact_name(baseline_payload, resource_aware_scheduler=False),
                "--write-text-summary",
            ])
            scheduler_capture_result = execute_or_skip(
                args.skip_scheduler_capture,
                "capture_scheduler_decisions",
                "Capture runtime scheduler decisions and pod-to-node placement evidence before benchmark execution.",
                scheduler_capture_cmd,
                [str(scheduler_output_dir)],
            )
            if scheduler_capture_result.status == "failed":
                scheduler_capture_result.error = scheduler_capture_result.error or "scheduler_decision_capture_failed"
                return fail_fast_after_precondition(
                    "scheduler_decision_capture",
                    "scheduler_decision_capture_failed",
                    [
                        "apply_latency_profile",
                        "run_multi_tenant_benchmark",
                        "capture_observability_after_benchmark",
                    ],
                    1,
                )

        latency_applied = False
        latency_should_run, latency_skip_reason = should_apply_latency_profile(
            repo_root=repo_root,
            cycle=cycle,
            benchmark_config=baseline_payload,
            latency_profile_value=latency_profile,
            scheduler_mode_runtime=scheduler_mode_runtime,
            skip_benchmark_due_to_deployment=skip_benchmark_due_to_deployment,
        )
        if latency_should_run:
            latency_cmd = with_common(python_cmd + [
                script(repo_root, "scripts/latency/apply-latency-profile.py"),
                "--repo-root", str(repo_root),
                "--cycle-config", str(cycle_config),
                "--profile-config", str(rel_to_repo(repo_root, latency_profile, latency_profile)),
                "--kubeconfig", str(kubeconfig_path),
                "--output-root", str(latency_root),
                "--action", "apply",
                "--injection-id", f"{run_id}_latency_apply",
            ])
            if args.dry_run:
                latency_cmd.append("--dry-run")
            latency_result = execute_or_skip(args.skip_latency_injection, "apply_latency_profile", "Apply the configured network-latency profile before benchmark execution.", latency_cmd, [str(latency_root)])
            latency_applied = latency_result.status in {"completed", "dry_run"}
            if latency_result.status == "failed":
                latency_result.error = latency_result.error or "latency_profile_application_failed"
                return fail_fast_after_precondition(
                    "latency_injection",
                    "latency_profile_application_failed",
                    [
                        "capture_observability_after_deployment",
                        "run_baseline",
                        "capture_observability_after_benchmark",
                    ],
                    1,
                )
        else:
            latency_profile_id = latency_profile_id_from_payload(repo_root, latency_profile, baseline_payload)
            if scheduler_mode_runtime:
                latency_skip_description = (
                    f"Skip latency injection because {latency_profile_id or 'no latency profile'} is configured as a no-op for this scheduler-aware run."
                )
            else:
                latency_skip_description = f"No latency profile is applied for this cycle: {latency_skip_reason}."
            steps.append(skip_step("apply_latency_profile", latency_skip_description))

        obs_pre_cmd = with_common(python_cmd + [
            script(repo_root, "scripts/observability/minimal/run-minimal-observability.py"),
            "--repo-root", str(repo_root),
            "--cycle-config", str(cycle_config),
            "--action", "capture",
            "--stage", "post-deployment",
            "--kubeconfig", str(kubeconfig_path),
            "--output-root", str(minimal_observability_root),
            "--observability-id", f"{run_id}_observability_post_deployment",
        ])
        if skip_benchmark_due_to_deployment:
            obs_pre_cmd.append("--skip-application-deployment-gate")
        if args.dry_run:
            obs_pre_cmd.append("--dry-run")
        execute_or_skip(args.skip_minimal_observability, "capture_observability_after_deployment", "Capture minimal cluster evidence after the application deployment.", obs_pre_cmd, [str(minimal_observability_root)])

        if scheduler_mode_runtime and not skip_benchmark_due_to_deployment:
            capture_cluster_lens("pre-rescheduling")

        if scheduler_mode_runtime and not skip_benchmark_due_to_deployment:
            rescheduling_profile = scheduler_runtime_path(
                cycle,
                baseline_payload,
                "reschedulingProfilePath",
                default_rescheduling_profile_path(cycle, baseline_payload),
            )
            rescheduling_cmd = with_common(python_cmd + [
                script(repo_root, "scripts/rescheduling/run-telemetry-primed-rescheduling.py"),
                "--repo-root", str(repo_root),
                "--profile-config", rescheduling_profile,
                "--scenario-config", str(benchmark_config),
                "--action", "execute",
                "--kubeconfig", str(kubeconfig_path),
                "--output-root", str(rescheduling_root),
                "--run-id", f"{run_id}_telemetry_primed_rescheduling",
            ])
            if args.skip_telemetry_priming:
                rescheduling_cmd.append("--skip-telemetry-priming")
            if args.dry_run:
                rescheduling_cmd.append("--dry-run")
            rescheduling_result = execute_or_skip(
                args.skip_rescheduling,
                "telemetry_primed_rescheduling",
                "Execute annotation gate and controlled pod recreation before the official benchmark window, reusing telemetry collected during the dedicated priming workload.",
                rescheduling_cmd,
                [str(rescheduling_root)],
            )
            capture_cluster_lens("post-rescheduling", primary=(cluster_lens_primary == "post-rescheduling"))
            if rescheduling_result.status == "failed":
                rescheduling_result.error = rescheduling_result.error or "telemetry_primed_rescheduling_failed"
                return fail_fast_after_precondition(
                    "telemetry_primed_rescheduling",
                    rescheduling_result.error,
                    [
                        "run_multi_tenant_benchmark",
                        "capture_observability_after_benchmark",
                    ],
                    1,
                )

        if scheduler_mode_runtime and not skip_benchmark_due_to_deployment:
            scheduler_evidence = baseline_payload.get("schedulerEvidence") or {}
            scenario_id_for_capture = benchmark_scenario_id(cycle, baseline, baseline_payload)
            scheduler_output_dir = scheduler_evidence.get("artifactRoot") or f"results/experimental-cycles/{cycle.get('cycleId', 'cycle')}/scheduler/{scenario_id_for_capture}"
            scheduler_capture_cmd = with_common([
                *python_cmd,
                script(repo_root, "scripts/observability/scheduler/capture-scheduler-decisions.py"),
                "--repo-root", str(repo_root),
                "--scenario-config", str(benchmark_config),
                "--kubeconfig", str(kubeconfig_path),
                "--output-dir", str(rel_to_repo(repo_root, scheduler_output_dir, scheduler_output_dir)),
                "--output-name", scheduler_decision_artifact_name(baseline_payload, resource_aware_scheduler=True),
                "--write-text-summary",
                "--write-latest-aliases",
            ])
            scheduler_capture_result = execute_or_skip(
                args.skip_scheduler_capture,
                "capture_scheduler_decisions",
                "Capture post-rescheduling scheduler decisions and pod-to-node placement evidence for the benchmarked scheduler-aware state.",
                scheduler_capture_cmd,
                [str(scheduler_output_dir)],
            )
            if scheduler_capture_result.status == "failed":
                scheduler_capture_result.error = scheduler_capture_result.error or "scheduler_decision_capture_failed"
                return fail_fast_after_precondition(
                    "scheduler_decision_capture",
                    "scheduler_decision_capture_failed",
                    [
                        "run_multi_tenant_benchmark",
                        "capture_observability_after_benchmark",
                    ],
                    1,
                )

        if not scheduler_mode_runtime and not skip_benchmark_due_to_deployment:
            capture_cluster_lens("pre-benchmark", primary=(cluster_lens_primary == "pre-benchmark"))

        if skip_benchmark_due_to_deployment and not args.dry_run:
            if default_scheduler_runtime:
                for replica in benchmark_replicas():
                    steps.append(StepResult(
                        name=f"run_multi_tenant_benchmark_run{replica}",
                        description=f"Skip multi-tenant benchmark replica run{replica} because the deployment was not benchmark-ready.",
                        status="skipped_due_to_unsupported_scenario",
                        startedAt=utc_now(),
                        completedAt=utc_now(),
                        exitCode=0,
                        artifactHints=[rel_string(repo_root, deployment_manifest_path)],
                        error=deployment_decision_reason,
                    ))
            else:
                for replica in [item.strip() for item in args.baseline_replicas.split(",") if item.strip()]:
                    steps.append(StepResult(
                        name=f"run_baseline_{replica}",
                        description=f"Skip benchmark replica {replica} because the deployment was not benchmark-ready.",
                        status="skipped_due_to_unsupported_scenario",
                        startedAt=utc_now(),
                        completedAt=utc_now(),
                        exitCode=0,
                        artifactHints=[rel_string(repo_root, deployment_manifest_path)],
                        error=deployment_decision_reason,
                    ))
            steps.append(StepResult(
                name="capture_observability_after_benchmark",
                description="Skip post-benchmark observability because no benchmark was executed.",
                status="skipped_due_to_unsupported_scenario",
                startedAt=utc_now(),
                completedAt=utc_now(),
                exitCode=0,
                artifactHints=[str(minimal_observability_root)],
                error=deployment_decision_reason,
            ))
        else:
            if default_scheduler_runtime:
                replica_ids = benchmark_replicas()
                benchmark_results: list[StepResult] = []
                scenario_benchmark_root = benchmark_output_root()
                for replica in replica_ids:
                    replica_output_root = scenario_benchmark_root / f"run{replica}"
                    multi_cmd = build_multi_tenant_command(
                        repo_root,
                        benchmark_config,
                        kubeconfig_path,
                        f"{run_id}_multi_tenant_benchmark_run{replica}",
                        replica_output_root,
                    )
                    if args.write_latest_aliases:
                        multi_cmd.append("--write-latest-aliases")
                    benchmark_results.append(execute_or_skip(
                        args.skip_benchmark,
                        f"run_multi_tenant_benchmark_run{replica}",
                        f"Execute tenant-scoped concurrent Locust workloads for scheduler-mode replica run{replica} ({scheduler_mode})." if scheduler_mode_runtime else f"Execute tenant-scoped concurrent Locust workloads for default-scheduler replica run{replica}.",
                        multi_cmd,
                        [rel_string(repo_root, replica_output_root)],
                    ))

                if not args.skip_benchmark:
                    aggregate_payload = write_multi_tenant_replicate_summary(
                        repo_root=repo_root,
                        cycle=cycle,
                        scenario_config=baseline_payload,
                        replica_ids=replica_ids,
                        benchmark_results=benchmark_results,
                        run_id=f"{run_id}_multi_tenant_benchmark",
                        write_latest_aliases=args.write_latest_aliases,
                    )
                else:
                    aggregate_payload = {}

                failed_benchmark_results = [item for item in benchmark_results if item.status == "failed"]
                completed_benchmark_results = [item for item in benchmark_results if item.status == "completed"]
                if failed_benchmark_results and not completed_benchmark_results and not args.skip_benchmark and not args.dry_run:
                    reason = "multi_tenant_benchmark_failed"
                    artifact_evidence = multi_tenant_benchmark_artifact_evidence(repo_root, cycle, baseline_payload)
                    artifact_evidence["aggregateStatus"] = aggregate_payload.get("status")
                    unsupported_artifacts = write_unsupported_reports("multi_tenant_benchmark", reason, artifact_evidence)
                    unsupported_scenario = {
                        "stage": "multi_tenant_benchmark",
                        "status": "unsupported_under_current_constraints",
                        "reason": reason,
                        "canProceedToBenchmark": False,
                        "benchmarkArtifactEvidence": artifact_evidence,
                        "unsupportedArtifacts": unsupported_artifacts,
                    }
                    for benchmark_result in failed_benchmark_results:
                        benchmark_result.status = "unsupported"
                        benchmark_result.exitCode = 0
                        benchmark_result.error = reason
                        benchmark_result.artifactHints.extend(unsupported_artifacts)
            else:
                replica_ids = benchmark_replicas()
                benchmark_results: list[StepResult] = []
                for replica in replica_ids:
                    benchmark_namespace = baseline_payload.get("namespace") or ((baseline_payload.get("applicationTopology") or {}).get("namespace"))
                    bench_cmd = build_baseline_command(repo_root, baseline_config, kubeconfig_path, replica, args.dry_run, precheck_config, benchmark_namespace)
                    benchmark_results.append(execute_or_skip(args.skip_benchmark, f"run_baseline_{replica}", f"Execute benchmark replica {replica}.", bench_cmd, [rel_string(repo_root, benchmark_output_root())]))

                failed_benchmark_results = [item for item in benchmark_results if item.status == "failed"]
                completed_benchmark_results = [item for item in benchmark_results if item.status == "completed"]
                if failed_benchmark_results and not completed_benchmark_results and not args.skip_benchmark and not args.dry_run:
                    precheck_evidence = benchmark_precheck_failure_evidence(replica_ids)
                    if precheck_evidence.get("failedPrecheckCount", 0) > 0:
                        reason = "benchmark_precheck_failed"
                        unsupported_artifacts = write_unsupported_reports("benchmark_precheck", reason, precheck_evidence)
                        unsupported_scenario = {
                            "stage": "benchmark_precheck",
                            "status": "failed_precondition",
                            "reason": reason,
                            "canProceedToBenchmark": False,
                            "precheckEvidence": precheck_evidence,
                            "unsupportedArtifacts": unsupported_artifacts,
                        }
                        for item in failed_benchmark_results:
                            item.status = "unsupported"
                            item.exitCode = 0
                            item.error = reason
                            item.artifactHints.extend(unsupported_artifacts)
                    else:
                        artifact_evidence = benchmark_artifact_evidence(replica_ids, benchmark_results)
                        if can_classify_latency_pre_benchmark_failure(artifact_evidence):
                            reason = "latency_profile_pre_benchmark_api_unavailable"
                            evidence = {
                                "latencyProfile": latency_profile_evidence(),
                                "benchmarkArtifacts": artifact_evidence,
                                "classificationRule": "latency_applied_and_all_replicas_failed_before_measurement_after_successful_precheck",
                                "failureClass": "api_smoke_or_pre_benchmark_api_unavailable",
                            }
                            unsupported_artifacts = write_unsupported_reports("latency_injection_pre_benchmark", reason, evidence)
                            unsupported_scenario = {
                                "stage": "latency_injection_pre_benchmark",
                                "status": "unsupported_under_current_constraints",
                                "reason": reason,
                                "canProceedToBenchmark": False,
                                "latencyProfile": evidence["latencyProfile"],
                                "benchmarkArtifactEvidence": artifact_evidence,
                                "unsupportedArtifacts": unsupported_artifacts,
                            }
                            for item in failed_benchmark_results:
                                item.status = "unsupported"
                                item.exitCode = 0
                                item.error = reason
                                item.artifactHints.extend(unsupported_artifacts)
                        elif can_classify_latency_invalid_measurement_failure(artifact_evidence):
                            reason = "measurement_produced_zero_valid_requests"
                            evidence = {
                                "latencyProfile": latency_profile_evidence(),
                                "benchmarkArtifacts": artifact_evidence,
                                "classificationRule": "latency_applied_and_no_valid_target_requests_after_measurement",
                                "failureClass": "measurement_produced_no_valid_target_requests",
                            }
                            unsupported_artifacts = write_unsupported_reports("measurement_validation", reason, evidence)
                            unsupported_scenario = {
                                "stage": "measurement_validation",
                                "status": "unsupported_under_current_constraints",
                                "reason": reason,
                                "canProceedToBenchmark": False,
                                "latencyProfile": evidence["latencyProfile"],
                                "benchmarkArtifactEvidence": artifact_evidence,
                                "unsupportedArtifacts": unsupported_artifacts,
                            }
                            for item in failed_benchmark_results:
                                item.status = "unsupported"
                                item.exitCode = 0
                                item.error = reason
                                item.artifactHints.extend(unsupported_artifacts)

            obs_post_cmd = with_common(python_cmd + [
                script(repo_root, "scripts/observability/minimal/run-minimal-observability.py"),
                "--repo-root", str(repo_root),
                "--cycle-config", str(cycle_config),
                "--action", "capture",
                "--stage", "post-benchmark",
                "--kubeconfig", str(kubeconfig_path),
                "--output-root", str(minimal_observability_root),
                "--observability-id", f"{run_id}_observability_post_benchmark",
            ])
            if args.dry_run:
                obs_post_cmd.append("--dry-run")
            execute_or_skip(args.skip_minimal_observability, "capture_observability_after_benchmark", "Capture minimal cluster evidence after the scheduler-aware benchmark." if scheduler_mode_runtime else "Capture minimal cluster evidence after the benchmark.", obs_post_cmd, [str(minimal_observability_root)])
            capture_cluster_lens("post-benchmark")

            if latency_profile and latency_applied:
                reset_cmd = with_common(python_cmd + [
                    script(repo_root, "scripts/latency/apply-latency-profile.py"),
                    "--repo-root", str(repo_root),
                    "--cycle-config", str(cycle_config),
                    "--profile-config", str(rel_to_repo(repo_root, latency_profile, latency_profile)),
                    "--kubeconfig", str(kubeconfig_path),
                    "--output-root", str(latency_root),
                    "--action", "reset",
                    "--injection-id", f"{run_id}_latency_reset",
                ])
                if args.dry_run:
                    reset_cmd.append("--dry-run")
                execute_or_skip(args.skip_latency_injection, "reset_latency_profile", "Reset the configured network-latency profile after benchmark execution.", reset_cmd, [str(latency_root)])
            else:
                steps.append(skip_step("reset_latency_profile", "No latency profile was applied for this cycle."))

        diagnosis_text = diagnosis_root / f"{run_id}_diagnosis_all_diagnosis.txt"
        diag_cmd = python_cmd + [
            script(repo_root, "scripts/analysis/generate-technical-diagnosis.py"),
            "--repo-root", str(repo_root),
            "--profile-config", str(rel_to_repo(repo_root, diagnosis_profile, diagnosis_profile)),
            "--family", "all",
            "--output-json", str(diagnosis_json),
            "--output-text", str(diagnosis_text),
            "--diagnosis-id", f"{run_id}_diagnosis_all",
        ]
        execute_or_skip(args.skip_diagnosis, "generate_technical_diagnosis", "Generate scheduler-aware technical diagnosis." if scheduler_mode_runtime else "Generate the provider-backed baseline technical diagnosis.", diag_cmd, [str(diagnosis_root)])

        report_cmd = python_cmd + [
            script(repo_root, "scripts/analysis/generate-reporting.py"),
            "--repo-root", str(repo_root),
            "--profile-config", str(rel_to_repo(repo_root, reporting_profile, reporting_profile)),
            "--output-root", str(reporting_root),
            "--reporting-id", f"{run_id}_reporting",
        ]
        execute_or_skip(args.skip_reporting, "generate_reporting", "Generate provider-aware reporting and charts.", report_cmd, [str(reporting_root)])

        reporting_site_root = repo_root / "results" / "reporting"
        reporting_site_cmd = python_cmd + [
            script(repo_root, "scripts/analysis/generate-reporting-site.py"),
            "--repo-root", str(repo_root),
            "--site-config", str(repo_root / "config" / "reporting" / "site" / "REPORTING_SITE.json"),
            "--output-root", str(reporting_site_root),
            "--site-id", f"{run_id}_reporting_site",
        ]
        execute_or_skip(args.skip_reporting, "generate_reporting_site", "Generate the static reporting-site entry point.", reporting_site_cmd, [str(reporting_site_root)])

        gate_cmd = python_cmd + [
            script(repo_root, "scripts/analysis/evaluate-completion-gate.py"),
            "--repo-root", str(repo_root),
            "--profile-config", str(rel_to_repo(repo_root, completion_profile, completion_profile)),
            "--cycle-config", str(cycle_config),
            "--diagnosis-json", str(diagnosis_json),
            "--output-json", str(completion_json),
            "--output-text", str(completion_text),
            "--evaluation-id", f"{run_id}_completion_gate",
        ]
        if args.dry_run:
            gate_cmd.append("--dry-run")
        execute_or_skip(args.skip_completion_gate, "evaluate_completion_gate", "Evaluate provider-aware cycle completion criteria.", gate_cmd, [str(completion_root)])

        if not args.skip_freeze:
            write_cycle_execution_artifacts(
                execution_stage="before_freeze",
                force_latest_aliases=True,
            )

        freeze_cmd = python_cmd + [
            script(repo_root, "scripts/analysis/freeze-experimental-cycle.py"),
            "--repo-root", str(repo_root),
            "--cycle-config", str(cycle_config),
            "--profile-config", str(rel_to_repo(repo_root, freeze_profile, freeze_profile)),
            "--freeze-id", f"{run_id}_freeze",
            "--output-root", str(freeze_root),
        ]
        if args.force_freeze:
            freeze_cmd.append("--force")
        if args.write_latest_aliases:
            freeze_cmd.append("--write-latest-aliases")
        if args.dry_run:
            freeze_cmd.extend(["--dry-run", "--skip-completion-gate"])
        execute_or_skip(args.skip_freeze, "freeze_cycle", "Freeze the provider-backed cycle evidence.", freeze_cmd, [str(freeze_root)])

    except SystemExit:
        raise
    except Exception as exc:
        now = utc_now()
        steps.append(StepResult(name="cycle_execution", description="Cycle launcher failure.", status="failed", startedAt=now, completedAt=now, exitCode=1, error=str(exc)))
        return finalize(1)

    return finalize(0)


if __name__ == "__main__":
    raise SystemExit(main())
