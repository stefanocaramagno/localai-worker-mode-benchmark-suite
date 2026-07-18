#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
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
class CommandResult:
    name: str
    status: str
    description: str = ""
    command: list[str] = field(default_factory=list)
    exitCode: int | None = None
    startedAt: str | None = None
    completedAt: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
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
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = normalize_artifact_text_for_output(content, path)
    path.write_text(content, encoding="utf-8")


def repo_path(repo_root: Path, value: str | None, default: str | None = None) -> Path:
    raw = value or default
    if not raw:
        raise ValueError("Cannot resolve an empty path.")
    path = Path(raw)
    return path if path.is_absolute() else repo_root / path


def rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return str(path)


def python_cmd() -> list[str]:
    if sys.executable:
        return [sys.executable]
    for candidate in ("python", "python3", "py"):
        found = shutil.which(candidate)
        if found:
            return [found, "-3"] if candidate == "py" else [found]
    return ["python"]


def as_text(command: list[str]) -> str:
    return " ".join(subprocess.list2cmdline([part]) for part in command)


def run_command(*, name: str, description: str, command: list[str], repo_root: Path, dry_run: bool, continue_on_failure: bool, artifacts: dict[str, Any] | None = None) -> CommandResult:
    result = CommandResult(
        name=name,
        description=description,
        status="dry_run" if dry_run else "running",
        command=command,
        startedAt=utc_now(),
        artifacts=artifacts or {},
    )
    if dry_run:
        result.exitCode = 0
        result.completedAt = utc_now()
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


def skipped_step(name: str, description: str, artifacts: dict[str, Any] | None = None) -> CommandResult:
    now = utc_now()
    return CommandResult(name=name, description=description, status="skipped", exitCode=0, startedAt=now, completedAt=now, artifacts=artifacts or {})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute or plan an experimental campaign composed of multiple provider-backed variants.")
    parser.add_argument("--repo-root", default=".", help="Repository root directory.")
    parser.add_argument("--cycle-config", default="config/experimental-cycles/C2.json", help="Comparative campaign cycle profile path.")
    parser.add_argument("--tool-path", default="proxmox-k3s", help="proxmox-k3s executable path or command name.")
    parser.add_argument("--run-id", default="", help="Optional run identifier. Defaults to a UTC timestamped identifier.")
    parser.add_argument("--baseline-replicas", default="", help="Comma-separated benchmark replica identifiers for every variant.")
    parser.add_argument("--base-url", default="", help="Optional LocalAI base URL override for deployment smoke checks.")
    parser.add_argument("--dry-run", action="store_true", help="Write an execution plan without executing runtime commands.")
    parser.add_argument("--continue-on-failure", action="store_true", help="Continue subsequent steps after a command failure.")
    parser.add_argument("--allow-metrics-warning", action="store_true", help="Allow non-blocking Metrics API warnings during cluster validation.")
    parser.add_argument("--confirm-delete", action="store_true", help="Allow provider delete actions when lifecycle policies request them.")
    parser.add_argument("--force-freeze", action="store_true", help="Force rebuild of the frozen snapshot.")
    parser.add_argument("--write-latest-aliases", action="store_true", help="Update latest artifact aliases when supported.")
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
    parser.add_argument("--skip-default-scheduler-validation", action="store_true", help="Skip static validation of default-scheduler manifests when executing C7 variants.")
    parser.add_argument("--skip-scheduler-capture", action="store_true", help="Skip runtime capture of Kubernetes default scheduler decisions when executing C7 variants.")
    parser.add_argument("--skip-scheduler-mode-validation", action="store_true", help="Skip static validation of scheduler-aware application manifests.")
    parser.add_argument("--skip-custom-scheduler", action="store_true", help="Skip custom second scheduler installation for load-aware scheduler-mode variants.")
    parser.add_argument("--skip-mon-agent", action="store_true", help="Skip mon-agent integration and runtime annotation capture for scheduler-mode variants.")
    parser.add_argument("--skip-telemetry-priming", action="store_true", help="Skip the warm-up-only telemetry priming workload while keeping controlled rescheduling available.")
    parser.add_argument("--skip-rescheduling", action="store_true", help="Skip telemetry-primed redeployment/rescheduling for scheduler-mode variants.")
    parser.add_argument("--skip-cluster-lens-capture", action="store_true", help="Skip cluster-lens placement evidence capture for scheduler-aware variants.")
    parser.add_argument("--skip-delete", action="store_true")
    return parser.parse_args()


def load_optional_json(repo_root: Path, path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    path = repo_path(repo_root, path_value)
    if not path.exists():
        return {}
    return load_json(path)


def is_default_scheduler_campaign(cycle: dict[str, Any]) -> bool:
    campaign = cycle.get("campaign") or {}
    campaign_type = str(cycle.get("campaignType") or campaign.get("campaignType") or "").strip()
    scenario_family = str(campaign.get("scenarioFamily") or "").strip()
    return campaign_type in {"default_scheduler_baseline", "resource_aware_scheduler", "network_aware_scheduler"} or scenario_family in {"default-scheduler", "resource-aware-scheduler", "network-aware-scheduler"}


def default_scheduler_variants_from_planned_scenarios(repo_root: Path, cycle: dict[str, Any]) -> list[dict[str, Any]]:
    campaign = cycle.get("campaign") or {}
    references = campaign.get("plannedScenarioReferences") or []
    if not isinstance(references, list):
        references = []

    variants: list[dict[str, Any]] = []
    for reference in references:
        if not isinstance(reference, dict):
            continue
        scenario_path = str(reference.get("scenarioConfigPath") or "").strip()
        if not scenario_path:
            continue
        scenario = load_optional_json(repo_root, scenario_path)
        if not scenario:
            raise ValueError(f"Default-scheduler scenario profile cannot be loaded: {scenario_path}")

        binding = load_optional_json(repo_root, scenario.get("providerBindingPath"))
        provider_config = binding.get("providerConfig") or {}
        scenario_id = str(
            scenario.get("variantId")
            or scenario.get("scenarioId")
            or reference.get("scenarioId")
            or Path(scenario_path).stem
        )

        variant = {
            "variantId": scenario_id,
            "scenarioFamily": "default-scheduler",
            "scenarioClass": reference.get("scenarioClass") or scenario.get("scenarioClass"),
            "scenarioOrdinal": scenario.get("scenarioOrdinal"),
            "scenarioConfigPath": scenario_path,
            "infrastructureProfileId": scenario.get("infrastructureProfileId"),
            "infrastructureProfilePath": scenario.get("infrastructureProfilePath"),
            "providerBindingId": scenario.get("providerBindingId"),
            "providerBindingPath": scenario.get("providerBindingPath"),
            "providerConfigExamplePath": provider_config.get("examplePath"),
            "providerConfigLocalPath": provider_config.get("localPath"),
            "kubeconfigPath": provider_config.get("recommendedKubeconfigPath"),
            "workerNodeCount": scenario.get("workerNodeCount"),
            "workerVcpusPerNode": scenario.get("workerVcpusPerNode"),
            "workerMemoryGiBPerNode": scenario.get("workerMemoryGiBPerNode"),
            "workerStorageGiBPerNode": scenario.get("workerStorageGiBPerNode"),
            "resultsRoot": scenario.get("resultsRoot") or campaign.get("resultsRoot"),
            "outputSubdir": scenario.get("outputSubdir") or scenario_id,
            "clusterLifecycleMode": (cycle.get("providerBackedInfrastructure") or {}).get("clusterLifecycleMode", "ephemeral"),
            "destroyClusterAfterVariant": bool(campaign.get("destroyClusterBetweenVariants", True)),
            "lifecyclePolicyId": (cycle.get("providerBackedInfrastructure") or {}).get("lifecyclePolicyId", "LC_EPHEMERAL_DELETE_CLUSTER"),
            "lifecyclePolicyPath": (cycle.get("providerBackedInfrastructure") or {}).get("lifecyclePolicyPath", "config/infrastructure/lifecycle/policies/LC_EPHEMERAL_DELETE_CLUSTER.json"),
            "placementProfileId": scenario.get("placementProfileId") or "DEFAULT_KUBERNETES_SCHEDULER",
            "placementProfilePath": scenario.get("placementProfilePath") or "",
            "latencyProfileId": scenario.get("latencyProfileId"),
            "latencyProfilePath": scenario.get("latencyProfilePath"),
            "applicationTopology": copy.deepcopy(scenario.get("applicationTopology") or {}),
        }
        missing = [
            key
            for key in ("infrastructureProfileId", "infrastructureProfilePath", "providerBindingId", "providerBindingPath")
            if not variant.get(key)
        ]
        if missing:
            raise ValueError(f"Default-scheduler scenario {scenario_id} is missing required provider fields: {', '.join(missing)}")
        variants.append(variant)

    return variants


def campaign_variants(repo_root: Path, cycle: dict[str, Any]) -> list[dict[str, Any]]:
    campaign = cycle.get("campaign") or {}
    explicit_variants = campaign.get("variants") or []
    if explicit_variants:
        return explicit_variants
    if is_default_scheduler_campaign(cycle):
        return default_scheduler_variants_from_planned_scenarios(repo_root, cycle)
    return []


def load_variant_execution_manifest(repo_root: Path, variant_cycle_config: Path) -> dict[str, Any]:
    if not variant_cycle_config.exists():
        return {}
    try:
        variant_cycle = load_json(variant_cycle_config)
    except Exception:
        return {}
    provider = variant_cycle.get("providerBackedInfrastructure") or {}
    execution_root_value = provider.get("cycleExecutionArtifactRoot")
    if not execution_root_value:
        return {}
    execution_root = repo_path(repo_root, execution_root_value)
    latest_manifest = execution_root / "latest-cycle-execution-manifest.json"
    if latest_manifest.exists():
        try:
            return load_json(latest_manifest)
        except Exception:
            return {}
    manifests = sorted(execution_root.glob("*_cycle_execution_manifest.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not manifests:
        return {}
    try:
        return load_json(manifests[0])
    except Exception:
        return {}


def generated_profile_paths(generated_root: Path, variant_id: str) -> dict[str, Path]:
    root = generated_root / variant_id
    return {
        "cycle": root / f"{variant_id}.cycle.json",
        "provisioning": root / f"PI_{variant_id}.json",
        "provisioningValidation": root / f"PV_{variant_id}.json",
        "clusterValidation": root / f"CV_{variant_id}.json",
        "applicationDeployment": root / f"AD_{variant_id}.json",
        "minimalObservability": root / f"MO_{variant_id}.json",
        "precheck": root / f"TC_{variant_id}.json",
        "benchmark": root / f"BENCHMARK_{variant_id}.json",
    }


def deep_merge_dicts(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dicts(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


BENCHMARK_RUNTIME_INDEX_PATH = "config/benchmark/BENCHMARK_RUNTIME_CONFIG_INDEX.json"

DEFAULT_BENCHMARK_RUNTIME_SCHEMA_ID = "BENCHMARK_RUNTIME_CONFIG_SCHEMA_V1"

DEFAULT_BENCHMARK_RUNTIME_SCHEMA_PATH = "config/benchmark/schemas/BENCHMARK_RUNTIME_CONFIG_SCHEMA_V1.json"

_BENCHMARK_RUNTIME_INDEX_CACHE: dict[str, Any] | None = None

BASELINE_ONLY_METADATA_FIELDS = {
    "historicalReferenceBaselineId",
}

BASELINE_DESCRIPTIVE_FIELDS = {
    "notes",
    "purpose",
    "selectionCriteria",
}


def ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)
    return ordered


def benchmark_runtime_index_file() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / BENCHMARK_RUNTIME_INDEX_PATH
        if candidate.is_file():
            return candidate
    return Path(BENCHMARK_RUNTIME_INDEX_PATH)


def load_benchmark_runtime_index() -> dict[str, Any]:
    global _BENCHMARK_RUNTIME_INDEX_CACHE
    if _BENCHMARK_RUNTIME_INDEX_CACHE is None:
        index_file = benchmark_runtime_index_file()
        with index_file.open("r", encoding="utf-8-sig") as handle:
            _BENCHMARK_RUNTIME_INDEX_CACHE = json.load(handle)
    return _BENCHMARK_RUNTIME_INDEX_CACHE


def benchmark_runtime_schema_id() -> str:
    return str(load_benchmark_runtime_index().get("schemaId") or DEFAULT_BENCHMARK_RUNTIME_SCHEMA_ID)


def benchmark_runtime_schema_path() -> str:
    return str(load_benchmark_runtime_index().get("schemaPath") or DEFAULT_BENCHMARK_RUNTIME_SCHEMA_PATH)


def benchmark_runtime_profile_naming_policy() -> str:
    return str(load_benchmark_runtime_index().get("generatedProfileNamingPolicy") or "BENCHMARK_<VARIANT_ID>.json")


def benchmark_baseline_ancestry(reference_baseline: dict[str, Any], direct_reference_baseline_id: str) -> list[str]:
    return ordered_unique([
        str(reference_baseline.get("historicalReferenceBaselineId") or ""),
        str(reference_baseline.get("referenceBaselineId") or ""),
        str(reference_baseline.get("baselineId") or direct_reference_baseline_id or ""),
        str(direct_reference_baseline_id or ""),
    ])


def sanitize_generated_benchmark_config_metadata(
    config: dict[str, Any],
    *,
    reference_baseline: dict[str, Any],
    scenario: dict[str, Any],
    scenario_family: str,
    variant_id: str,
    variant_reference_baseline_id: str,
    variant_reference_baseline_config_path: str,
    variant_reference_scenario_id: str,
    variant_reference_scenario_config_path: str,
    source_scenario_id: str,
    source_scenario_config_path: str,
    benchmark_config_path: str,
) -> None:
    for key in BASELINE_ONLY_METADATA_FIELDS:
        config.pop(key, None)

    for key in BASELINE_DESCRIPTIVE_FIELDS:
        if key in reference_baseline and key not in scenario:
            config.pop(key, None)

    if not str(config.get("purpose") or "").strip():
        config["purpose"] = f"Runtime benchmark configuration for provider-backed {scenario_family} variant {variant_id}."
    if not str(config.get("notes") or "").strip():
        config["notes"] = f"Generated benchmark runtime profile for scenario {source_scenario_id} using {variant_reference_baseline_id} only as the direct reference baseline."

    lineage = benchmark_baseline_ancestry(reference_baseline, variant_reference_baseline_id)
    config["baselineLineage"] = {
        "directReferenceBaselineId": variant_reference_baseline_id,
        "directReferenceBaselineConfigPath": variant_reference_baseline_config_path,
        "ancestry": lineage,
        "sourceScenarioId": source_scenario_id,
        "sourceScenarioConfigPath": source_scenario_config_path,
        "executedScenarioId": source_scenario_id,
        "executedScenarioConfigPath": source_scenario_config_path,
        "campaignReferenceScenarioId": variant_reference_scenario_id,
        "campaignReferenceScenarioConfigPath": variant_reference_scenario_config_path,
    }
    config["benchmarkRuntimeConfigSchemaId"] = benchmark_runtime_schema_id()
    config["benchmarkRuntimeConfigSchemaPath"] = benchmark_runtime_schema_path()
    config["benchmarkConfigPath"] = benchmark_config_path
    config["benchmarkConfigRole"] = config.get("benchmarkConfigRole") or f"provider_backed_{scenario_family.replace('-', '_')}_variant"


def benchmark_runtime_schema_file() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / benchmark_runtime_schema_path()
        if candidate.is_file():
            return candidate
    return Path(benchmark_runtime_schema_path())


def load_benchmark_runtime_schema() -> dict[str, Any]:
    schema_file = benchmark_runtime_schema_file()
    with schema_file.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _schema_type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return (isinstance(value, (int, float)) and not isinstance(value, bool))
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True


def _validate_json_schema_subset(value: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}, got {value!r}")
        return

    expected = schema.get("type")
    if expected:
        expected_types = expected if isinstance(expected, list) else [expected]
        if not any(_schema_type_matches(value, item) for item in expected_types):
            errors.append(f"{path}: expected type {'/'.join(expected_types)}, got {type(value).__name__}")
            return

    if isinstance(value, str) and isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
        errors.append(f"{path}: expected minimum string length {schema['minLength']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool) and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: expected minimum value {schema['minimum']}")

    if isinstance(value, dict):
        required = schema.get("required") or []
        for key in required:
            if key not in value or value.get(key) in (None, ""):
                errors.append(f"{path}.{key}: missing required field")
        properties = schema.get("properties") or {}
        for key, property_schema in properties.items():
            if key in value:
                _validate_json_schema_subset(value[key], property_schema, f"{path}.{key}", errors)

    if isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_json_schema_subset(item, item_schema, f"{path}[{index}]", errors)


def validate_generated_benchmark_config(config: dict[str, Any], *, benchmark_config_path: str) -> None:
    schema = load_benchmark_runtime_schema()
    errors: list[str] = []
    _validate_json_schema_subset(config, schema, "$", errors)
    if errors:
        preview = "; ".join(errors[:10])
        remaining = len(errors) - 10
        suffix = f"; ... and {remaining} more error(s)" if remaining > 0 else ""
        raise ValueError(
            f"Generated benchmark runtime config {benchmark_config_path} does not satisfy {benchmark_runtime_schema_id()}: {preview}{suffix}"
        )
    if config.get("benchmarkRuntimeConfigSchemaId") != benchmark_runtime_schema_id():
        raise ValueError(f"Generated benchmark runtime config {benchmark_config_path} has an invalid benchmarkRuntimeConfigSchemaId.")
    if config.get("benchmarkRuntimeConfigSchemaPath") != benchmark_runtime_schema_path():
        raise ValueError(f"Generated benchmark runtime config {benchmark_config_path} has an invalid benchmarkRuntimeConfigSchemaPath.")


def build_generated_benchmark_config(
    *,
    reference_baseline: dict[str, Any],
    scenario: dict[str, Any],
    parent_cycle_id: str,
    variant_id: str,
    scenario_id: str,
    scenario_family: str,
    generated_profile_prefix: str,
    variant: dict[str, Any],
    variant_reference_baseline_id: str,
    variant_reference_baseline_config_path: str,
    variant_reference_scenario_id: str,
    variant_reference_scenario_config_path: str,
    source_scenario_id: str,
    source_scenario_config_path: str,
    benchmark_config_path: str,
    application_deployment_path: str,
    minimal_observability_path: str,
    precheck_path: str,
    primary_namespace: str,
    all_namespaces: list[str],
    additional_namespaces: list[str],
    provider_context: dict[str, Any],
    placement_profile_id: str,
    placement_profile_path: str,
    latency_profile_id: str | None,
    latency_profile_path: str | None,
    variant_root: str,
    deployment_root: str,
    observability_root: str,
) -> dict[str, Any]:
    config = deep_merge_dicts(reference_baseline, scenario)
    sanitize_generated_benchmark_config_metadata(
        config,
        reference_baseline=reference_baseline,
        scenario=scenario,
        scenario_family=scenario_family,
        variant_id=variant_id,
        variant_reference_baseline_id=variant_reference_baseline_id,
        variant_reference_baseline_config_path=variant_reference_baseline_config_path,
        variant_reference_scenario_id=variant_reference_scenario_id,
        variant_reference_scenario_config_path=variant_reference_scenario_config_path,
        source_scenario_id=str(scenario.get("scenarioId") or scenario.get("variantId") or variant_id),
        source_scenario_config_path=str(variant.get("scenarioConfigPath") or variant_reference_scenario_config_path),
        benchmark_config_path=benchmark_config_path,
    )
    scheduler_policy = scenario.get("networkAwareSchedulerPolicy") or scenario.get("schedulerModePolicy") or {}
    scheduler_mode_value = (
        scenario.get("schedulerMode")
        or scheduler_policy.get("schedulerMode")
        or ((scenario.get("applicationTopology") or {}).get("schedulerMode"))
    )
    scheduler_name_value = (
        scenario.get("schedulerName")
        if scenario.get("schedulerName") not in (None, "")
        else scheduler_policy.get("schedulerName")
    )
    if scheduler_mode_value == "kubernetes_default_scheduler" and not scheduler_name_value:
        scheduler_name_value = "default-scheduler"

    if scenario_family == "default-scheduler":
        if scenario.get("primaryModelScenario"):
            config["modelScenario"] = scenario.get("primaryModelScenario")
        if scenario.get("primaryResolvedModelName"):
            config["resolvedModelName"] = scenario.get("primaryResolvedModelName")
        worker_count_per_tenant = localai_worker_count_per_tenant_from_scenario(scenario)
        if worker_count_per_tenant is not None:
            config["localAiWorkerCountPerTenant"] = worker_count_per_tenant
            config["resolvedWorkerCount"] = worker_count_per_tenant
        config["benchmarkRunner"] = "multi_tenant_locust"
        config["tenantBenchmarkMode"] = "one_locust_process_per_tenant"
        config["schedulerEvidenceRequired"] = True

    config.update({
        "baselineId": scenario_id,
        "benchmarkScenarioId": scenario_id,
        "benchmarkConfigId": f"BENCHMARK_{generated_profile_prefix}",
        "benchmarkConfigPath": benchmark_config_path,
        "benchmarkConfigRole": f"provider_backed_{scenario_family.replace('-', '_')}_variant",
        "profileStatus": "generated_runtime_profile",
        "scenarioId": scenario_id,
        "scenarioProfileId": scenario.get("scenarioProfileId") or scenario_id,
        "variantId": variant_id,
        "family": scenario.get("family") or scenario_family,
        "campaignId": scenario.get("campaignId") or parent_cycle_id,
        "associatedCycleId": scenario.get("associatedCycleId") or parent_cycle_id,
        "referenceBaselineId": variant_reference_baseline_id,
        "referenceBaselineConfigPath": variant_reference_baseline_config_path,
        "referenceScenarioId": source_scenario_id,
        "referenceScenarioConfigPath": source_scenario_config_path,
        "executedScenarioId": source_scenario_id,
        "executedScenarioConfigPath": source_scenario_config_path,
        "campaignReferenceScenarioId": variant_reference_scenario_id,
        "campaignReferenceScenarioConfigPath": variant_reference_scenario_config_path,
        "scenarioConfigPath": variant.get("scenarioConfigPath"),
        "schedulerMode": scheduler_mode_value,
        "schedulerName": scheduler_name_value,
        "effectiveSchedulerName": scheduler_name_value,
        "roleInCycle": f"{scenario_family}_benchmark_variant",
        "namespace": primary_namespace,
        "namespaces": all_namespaces,
        "additionalNamespaces": additional_namespaces,
        "infrastructureProfileId": variant.get("infrastructureProfileId"),
        "infrastructureProfilePath": variant.get("infrastructureProfilePath"),
        "providerBindingId": variant.get("providerBindingId"),
        "providerBindingPath": variant.get("providerBindingPath"),
        "providerId": "proxmox-k3s",
        "applicationDeploymentProfileId": f"AD_{generated_profile_prefix}",
        "applicationDeploymentProfilePath": application_deployment_path,
        "applicationDeploymentArtifactRoot": deployment_root,
        "minimalObservabilityProfileId": f"MO_{generated_profile_prefix}",
        "minimalObservabilityProfilePath": minimal_observability_path,
        "minimalObservabilityArtifactRoot": observability_root,
        "precheckProfileId": f"TC_{generated_profile_prefix}",
        "precheckProfilePath": precheck_path,
        "placementProfileId": placement_profile_id,
        "placementProfilePath": placement_profile_path,
        "placementScenarioPath": placement_profile_path,
        "latencyProfileId": latency_profile_id,
        "latencyProfilePath": latency_profile_path,
        "variantRoot": variant_root,
    })
    if "outputSubdir" not in config or not str(config.get("outputSubdir") or "").strip():
        config["outputSubdir"] = f"{scenario_id}_official_locked"
    config["runtimeGeneration"] = {
        "generator": "scripts/experimental-cycles/run-experimental-campaign.py",
        "parentCycleId": parent_cycle_id,
        "variantId": variant_id,
        "scenarioFamily": scenario_family,
        "referenceBaselineId": variant_reference_baseline_id,
        "referenceBaselineConfigPath": variant_reference_baseline_config_path,
        "scenarioId": source_scenario_id,
        "scenarioConfigPath": source_scenario_config_path,
        "executedScenarioId": source_scenario_id,
        "executedScenarioConfigPath": source_scenario_config_path,
        "campaignReferenceScenarioId": variant_reference_scenario_id,
        "campaignReferenceScenarioConfigPath": variant_reference_scenario_config_path,
        "generatedBenchmarkConfigPath": benchmark_config_path,
        "schemaId": benchmark_runtime_schema_id(),
        "schemaPath": benchmark_runtime_schema_path(),
        "benchmarkRuntimeConfigIndexPath": BENCHMARK_RUNTIME_INDEX_PATH,
        "profileNamingPolicy": benchmark_runtime_profile_naming_policy(),
    }
    validate_generated_benchmark_config(config, benchmark_config_path=benchmark_config_path)
    return config


def _is_explicit_placeholder(value: str) -> bool:
    return (value.startswith("__") and value.endswith("__")) or (value.startswith("<") and value.endswith(">"))


def with_replacements(payload: dict[str, Any], replacements: dict[str, str | None]) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=False)
    for old, new in replacements.items():
        if not _is_explicit_placeholder(old):
            raise ValueError(f"Refusing non-placeholder runtime replacement key: {old}")
        if new is not None:
            text = text.replace(old, new)
    return json.loads(text)


def resolve_payload_placeholders(payload: Any, replacements: dict[str, str | None]) -> Any:
    text = json.dumps(payload, ensure_ascii=False)
    for old, new in replacements.items():
        if not _is_explicit_placeholder(old):
            raise ValueError(f"Refusing non-placeholder scenario replacement key: {old}")
        if new is not None:
            text = text.replace(old, new)
    return json.loads(text)


def mark_generated_runtime_profile(payload: dict[str, Any]) -> None:
    if "profileStatus" in payload:
        payload["profileStatus"] = "generated_runtime_profile"
    if "templateMetadata" in payload and isinstance(payload["templateMetadata"], dict):
        payload["templateMetadata"]["materializedAs"] = "generated_runtime_profile"


def provider_context(cycle: dict[str, Any]) -> dict[str, Any]:
    return cycle.get("providerBackedInfrastructure") or {}


def pipeline_context(cycle: dict[str, Any]) -> dict[str, Any]:
    return cycle.get("pipelineProfiles") or {}


def cycle_artifact_root(cycle: dict[str, Any], section_name: str, section_key: str, provider_key: str, default_suffix: str) -> str:
    section = cycle.get(section_name) or {}
    provider = provider_context(cycle)
    cycle_id = str(cycle.get("cycleId") or "campaign")
    return str(section.get(section_key) or provider.get(provider_key) or f"results/experimental-cycles/{cycle_id}/{default_suffix}")


def cycle_profile_path(cycle: dict[str, Any], section_name: str, section_key: str, provider_key: str, pipeline_key: str, default_path: str) -> str:
    section = cycle.get(section_name) or {}
    provider = provider_context(cycle)
    pipeline = pipeline_context(cycle)
    return str(section.get(section_key) or provider.get(provider_key) or pipeline.get(pipeline_key) or default_path)


def expected_kubernetes_nodes_from_infrastructure_profile(profile: dict[str, Any]) -> tuple[list[str], list[str]]:
    inventory = profile.get("nodeInventory") or profile.get("nodes") or {}
    control_plane_nodes = []
    worker_nodes = []
    for item in inventory.get("controlPlane", []) or []:
        name = item.get("expectedKubernetesNodeName") or item.get("name") or item.get("configuredName")
        if name:
            control_plane_nodes.append(str(name))
    for item in inventory.get("workers", []) or []:
        name = item.get("expectedKubernetesNodeName") or item.get("name") or item.get("configuredName")
        if name:
            worker_nodes.append(str(name))
    return control_plane_nodes, worker_nodes


def select_topology_from_placement_profile(placement_profile: dict[str, Any], application_worker_scenario: str | None, infrastructure_worker_count: int | None) -> dict[str, Any]:
    kustomize = placement_profile.get("kustomize") or {}
    infrastructure_key = str(infrastructure_worker_count) if infrastructure_worker_count is not None else None

    if infrastructure_key:
        infrastructure_topologies = kustomize.get("compositionByInfrastructureWorkerCount") or {}
        if infrastructure_key in infrastructure_topologies:
            return {
                "selectedTopologyDir": infrastructure_topologies[infrastructure_key],
                "selectedSource": "compositionByInfrastructureWorkerCount",
                "selectedKey": infrastructure_key,
                "availableApplicationWorkerCountTopologies": sorted((kustomize.get("compositionByApplicationWorkerCount") or {}).keys()),
                "availableInfrastructureWorkerCountTopologies": sorted(infrastructure_topologies.keys()),
            }

    application_topologies = kustomize.get("compositionByApplicationWorkerCount") or kustomize.get("compositionByWorkerCount") or {}
    if application_worker_scenario and application_worker_scenario in application_topologies:
        return {
            "selectedTopologyDir": application_topologies[application_worker_scenario],
            "selectedSource": "compositionByApplicationWorkerCount",
            "selectedKey": application_worker_scenario,
            "availableApplicationWorkerCountTopologies": sorted(application_topologies.keys()),
            "availableInfrastructureWorkerCountTopologies": sorted((kustomize.get("compositionByInfrastructureWorkerCount") or {}).keys()),
        }

    return {
        "selectedTopologyDir": None,
        "selectedSource": None,
        "selectedKey": None,
        "availableApplicationWorkerCountTopologies": sorted(application_topologies.keys()),
        "availableInfrastructureWorkerCountTopologies": sorted((kustomize.get("compositionByInfrastructureWorkerCount") or {}).keys()),
    }


def select_worker_node_mapping_from_placement_profile(placement_profile: dict[str, Any], application_worker_scenario: str | None, infrastructure_worker_count: int | None) -> dict[str, Any]:
    worker_placement = placement_profile.get("workerPlacement") or {}
    application_mappings = worker_placement.get("activeWorkerNodeMapByWorkerCount") or {}
    infrastructure_mappings = worker_placement.get("activeWorkerNodeMapByInfrastructureWorkerCount") or {}
    infrastructure_key = str(infrastructure_worker_count) if infrastructure_worker_count is not None else None

    if infrastructure_key and infrastructure_key in infrastructure_mappings:
        return {
            "selectedWorkerNodeMap": infrastructure_mappings[infrastructure_key],
            "selectedSource": "activeWorkerNodeMapByInfrastructureWorkerCount",
            "selectedKey": infrastructure_key,
            "availableApplicationWorkerCountMappings": sorted(application_mappings.keys()),
            "availableInfrastructureWorkerCountMappings": sorted(infrastructure_mappings.keys()),
        }

    if application_worker_scenario and application_worker_scenario in application_mappings:
        return {
            "selectedWorkerNodeMap": application_mappings[application_worker_scenario],
            "selectedSource": "activeWorkerNodeMapByWorkerCount",
            "selectedKey": application_worker_scenario,
            "availableApplicationWorkerCountMappings": sorted(application_mappings.keys()),
            "availableInfrastructureWorkerCountMappings": sorted(infrastructure_mappings.keys()),
        }

    return {
        "selectedWorkerNodeMap": None,
        "selectedSource": None,
        "selectedKey": None,
        "availableApplicationWorkerCountMappings": sorted(application_mappings.keys()),
        "availableInfrastructureWorkerCountMappings": sorted(infrastructure_mappings.keys()),
    }


def ordered_unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
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


def namespace_resolution_from_scenario(scenario: dict[str, Any], app_topology: dict[str, Any]) -> dict[str, Any]:
    primary_namespace = (
        app_topology.get("namespace")
        or scenario.get("namespace")
        or ((scenario.get("tenancyVariant") or {}).get("benchmarkNamespace"))
        or "localai-benchmark"
    )
    namespace_candidates: list[Any] = [primary_namespace]
    namespace_roles: list[dict[str, Any]] = []
    namespace_to_tenant: dict[str, str] = {}
    tenant_to_namespace: dict[str, str] = {}

    def register_namespace(namespace_value: Any, tenant_value: Any = None, role: str | None = None, extra: dict[str, Any] | None = None) -> None:
        namespace_text = str(namespace_value or "").strip()
        tenant_text = str(tenant_value or "").strip()
        if not namespace_text:
            return
        namespace_candidates.append(namespace_text)
        if tenant_text:
            namespace_to_tenant[namespace_text] = tenant_text
            tenant_to_namespace[tenant_text] = namespace_text
        if role or tenant_text or extra:
            record: dict[str, Any] = {"namespace": namespace_text}
            if tenant_text:
                record["tenantId"] = tenant_text
            if role:
                record["role"] = role
            if extra:
                record.update(extra)
            namespace_roles.append(record)

    for cluster in scenario.get("tenantClusters", []) or []:
        if not isinstance(cluster, dict):
            continue
        register_namespace(
            cluster.get("namespace"),
            cluster.get("tenantId"),
            str(cluster.get("role") or "tenant"),
            {
                "modelScenario": cluster.get("modelScenario"),
                "workerScenario": cluster.get("workerScenario"),
                "placement": cluster.get("placement"),
            },
        )

    for target in app_topology.get("additionalRolloutTargets", []) or []:
        if isinstance(target, dict) and target.get("namespace"):
            register_namespace(
                target.get("namespace"),
                target.get("tenantId") or namespace_to_tenant.get(str(target.get("namespace") or "")),
                "additional_rollout_target",
                {"deployments": target.get("deployments") or []},
            )

    for namespace in scenario.get("additionalNamespaces", []) or []:
        register_namespace(namespace)
    for namespace in app_topology.get("additionalNamespaces", []) or []:
        register_namespace(namespace)

    namespaces = ordered_unique_strings(namespace_candidates)
    if str(primary_namespace) not in namespaces:
        namespaces.insert(0, str(primary_namespace))
    additional_namespaces = [namespace for namespace in namespaces if namespace != str(primary_namespace)]

    if str(primary_namespace) not in namespace_to_tenant and scenario.get("tenantIds"):
        first_tenant = str((scenario.get("tenantIds") or [])[0] or "").strip()
        if first_tenant:
            namespace_to_tenant[str(primary_namespace)] = first_tenant
            tenant_to_namespace.setdefault(first_tenant, str(primary_namespace))

    return {
        "primaryNamespace": str(primary_namespace),
        "namespaces": namespaces,
        "additionalNamespaces": additional_namespaces,
        "namespaceRoles": namespace_roles,
        "namespaceToTenant": dict(sorted(namespace_to_tenant.items())),
        "tenantToNamespace": dict(sorted(tenant_to_namespace.items())),
        "isMultiNamespace": len(namespaces) > 1,
    }


def localai_worker_count_per_tenant_from_scenario(scenario: dict[str, Any]) -> int | None:
    for key in ("localAiWorkerCountPerTenant", "resolvedWorkerCountPerTenant", "resolvedWorkerCount"):
        raw = scenario.get(key)
        if raw is None:
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    worker_scenario = str(scenario.get("workerScenario") or "").strip().upper()
    if worker_scenario.startswith("W"):
        try:
            value = int(worker_scenario[1:])
        except (TypeError, ValueError):
            value = -1
        if value >= 0:
            return value
    return None


def build_smoke_validation_targets(scenario: dict[str, Any], base_local_port: int = 8080, remote_port: int = 8080) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for index, cluster in enumerate(scenario.get("tenantClusters") or []):
        if not isinstance(cluster, dict):
            continue
        tenant_id = str(cluster.get("tenantId") or f"tenant-{index + 1}").strip()
        namespace = str(cluster.get("namespace") or "").strip()
        model_name = str(cluster.get("modelName") or scenario.get("primaryResolvedModelName") or scenario.get("resolvedModelName") or "").strip()
        if not tenant_id or not namespace or not model_name:
            continue
        local_port = base_local_port + index
        targets.append({
            "tenantId": tenant_id,
            "namespace": namespace,
            "serviceName": str(cluster.get("serviceName") or "localai-server"),
            "baseUrl": f"http://localhost:{local_port}",
            "model": model_name,
            "portForward": {
                "enabled": True,
                "namespace": namespace,
                "serviceName": str(cluster.get("serviceName") or "localai-server"),
                "localPort": local_port,
                "remotePort": remote_port,
            },
        })
    return targets


def build_variant_runtime_configs(repo_root: Path, campaign_cycle: dict[str, Any], variant: dict[str, Any], generated_root: Path) -> Path:
    variant_id = variant["variantId"]
    paths = generated_profile_paths(generated_root, variant_id)
    campaign = campaign_cycle.get("campaign") or {}
    provider_context = campaign_cycle.get("providerBackedInfrastructure") or {}
    parent_cycle_id = str(campaign_cycle.get("cycleId") or "campaign")
    campaign_type = str(campaign_cycle.get("campaignType") or campaign.get("campaignType") or "comparative_campaign")
    scenario_family = str(campaign.get("scenarioFamily") or campaign_type.replace("_", "-"))
    campaign_root = str(provider_context.get("campaignArtifactRoot") or f"results/experimental-cycles/{parent_cycle_id}")
    if variant_id.startswith(f"{parent_cycle_id}_"):
        generated_profile_prefix = variant_id
    else:
        generated_profile_prefix = f"{parent_cycle_id}_{variant_id}"
    variant_cycle_id = generated_profile_prefix

    scenario_placeholder_replacements = {
        "<variant>": variant_id,
        "__VARIANT_ID__": variant_id,
        "__PARENT_CYCLE_ID__": parent_cycle_id,
        "__GENERATED_PROFILE_PREFIX__": generated_profile_prefix,
    }
    scenario = resolve_payload_placeholders(load_json(repo_path(repo_root, variant["scenarioConfigPath"])), scenario_placeholder_replacements)
    scenario_id = str(scenario.get("scenarioId") or scenario.get("variantId") or variant_id)
    scenario_family = str(variant.get("scenarioFamily") or scenario.get("family") or scenario_family)
    variant_reference_baseline_id = str(
        scenario.get("referenceBaselineId")
        or (campaign_cycle.get("baseline") or {}).get("baselineId")
        or "B1"
    )
    variant_reference_baseline_config_path = str(
        scenario.get("referenceBaselineConfigPath")
        or (campaign_cycle.get("baseline") or {}).get("configPath")
        or (campaign_cycle.get("cycleGovernance") or {}).get("referenceBaselineConfigPath")
        or "config/scenarios/baseline/B1.json"
    )
    variant_reference_scenario_id = str(
        scenario.get("referenceScenarioId")
        or (campaign_cycle.get("cycleGovernance") or {}).get("referenceScenarioId")
        or scenario_id
    )
    variant_reference_scenario_config_path = str(
        scenario.get("referenceScenarioConfigPath")
        or (campaign_cycle.get("cycleGovernance") or {}).get("referenceScenarioConfigPath")
        or variant.get("scenarioConfigPath")
    )
    reference_baseline = load_optional_json(repo_root, variant_reference_baseline_config_path)
    binding = load_optional_json(repo_root, variant.get("providerBindingPath"))
    pipeline = pipeline_context(campaign_cycle)

    cycle_variant_template_path = (
        provider_context.get("cycleVariantTemplatePath")
        or pipeline.get("cycleVariantTemplate")
        or "config/experimental-cycles/templates/PROVIDER_BACKED_CAMPAIGN_VARIANT_CYCLE_TEMPLATE.json"
    )
    cycle_variant_template = load_optional_json(repo_root, cycle_variant_template_path)

    provisioning_integration_template_path = (
        provider_context.get("provisioningIntegrationTemplatePath")
        or pipeline.get("provisioningIntegrationTemplate")
        or "config/provisioning/templates/PI_PROVIDER_BACKED_PROVISIONING_TEMPLATE.json"
    )
    provisioning_integration_template = load_optional_json(repo_root, provisioning_integration_template_path)

    cluster_validation_template_path = (
        provider_context.get("clusterValidationTemplatePath")
        or pipeline.get("clusterValidationTemplate")
        or "config/cluster-validation/templates/CV_PROVIDER_BACKED_VALIDATION_TEMPLATE.json"
    )
    cluster_validation_template = load_optional_json(repo_root, cluster_validation_template_path)

    application_deployment_template_path = (
        provider_context.get("applicationDeploymentTemplatePath")
        or pipeline.get("applicationDeploymentTemplate")
        or "config/application-deployment/templates/AD_PROVIDER_BACKED_LOCALAI_DEPLOYMENT_TEMPLATE.json"
    )
    application_deployment_template = load_optional_json(repo_root, application_deployment_template_path)

    minimal_observability_template_path = (
        provider_context.get("minimalObservabilityTemplatePath")
        or pipeline.get("minimalObservabilityTemplate")
        or "config/observability-minimal/templates/MO_PROVIDER_BACKED_OBSERVABILITY_TEMPLATE.json"
    )
    minimal_observability_template = load_optional_json(repo_root, minimal_observability_template_path)

    precheck_template_path = (
        provider_context.get("precheckTemplatePath")
        or pipeline.get("precheckTemplate")
        or "config/precheck/templates/TC_PROVIDER_BACKED_PRECHECK_TEMPLATE.json"
    )
    precheck_template = load_optional_json(repo_root, precheck_template_path)

    provisioning_validation_template_path = (
        provider_context.get("provisioningValidationTemplatePath")
        or pipeline.get("provisioningValidationTemplate")
        or "config/provisioning-validation/templates/PV_PROVIDER_BACKED_VALIDATION_TEMPLATE.json"
    )
    provisioning_validation_template = load_optional_json(repo_root, provisioning_validation_template_path)
    infrastructure_profile = load_optional_json(repo_root, variant.get("infrastructureProfilePath"))

    kubeconfig = variant.get("kubeconfigPath") or (binding.get("providerConfig") or {}).get("recommendedKubeconfigPath")
    variant_root = f"{campaign_root}/variants/{variant_id}"
    provisioning_root = f"{variant_root}/infrastructure/provisioning"
    validation_root = f"{variant_root}/infrastructure/validation"
    deployment_root = f"{variant_root}/application/deployment"
    observability_root = f"{variant_root}/observability/minimal"
    placement_root = f"{variant_root}/placement"
    deletion_root = f"{variant_root}/infrastructure/deletion"
    scheduler_runtime_family = "network-aware-scheduler" if scenario_family == "network-aware-scheduler" or campaign_type == "network_aware_scheduler" else "resource-aware-scheduler"
    resource_aware_scheduler_root = f"{variant_root}/{scheduler_runtime_family}"
    custom_scheduler_root = f"{resource_aware_scheduler_root}/custom-scheduler"
    mon_agent_root = f"{resource_aware_scheduler_root}/mon-agent"
    network_observability_root = f"{resource_aware_scheduler_root}/mentat"
    istio_gateway_root = f"{resource_aware_scheduler_root}/istio"
    rescheduling_root = f"{resource_aware_scheduler_root}/rescheduling"
    cluster_lens_root = f"{resource_aware_scheduler_root}/cluster-lens"

    scenario_policy = scenario.get("networkAwareSchedulerPolicy") or scenario.get("schedulerModePolicy") or {}
    mon_agent_profile_path = variant.get("monAgentProfilePath") or scenario_policy.get("monAgentProfilePath") or provider_context.get("monAgentProfilePath") or "config/mon-agent/profiles/MA_RESOURCE_AWARE.json"
    network_observability_profile_path = variant.get("networkObservabilityProfilePath") or scenario_policy.get("networkObservabilityProfilePath") or provider_context.get("networkObservabilityProfilePath") or "config/network-observability/profiles/NO_MENTAT_C9.json"
    istio_gateway_profile_path = variant.get("istioGatewayProfilePath") or scenario_policy.get("istioGatewayProfilePath") or provider_context.get("istioGatewayProfilePath") or "config/istio-gateway/profiles/IG_LOCALAI_GATEWAY_ROUTED_C9.json"
    default_custom_scheduler_profile_path = "config/scheduler/profiles/CS_C9_LOADAWARE_SECOND_SCHEDULER.json" if scenario_family == "network-aware-scheduler" or campaign_type == "network_aware_scheduler" else "config/scheduler/profiles/CS_C8_LOADAWARE_SECOND_SCHEDULER.json"
    custom_scheduler_profile_path = variant.get("customSchedulerProfilePath") or scenario_policy.get("customSchedulerProfilePath") or provider_context.get("customSchedulerProfilePath") or default_custom_scheduler_profile_path
    default_rescheduling_profile_path = "config/rescheduling/profiles/RS_C9_NETWORK_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json" if scenario_family == "network-aware-scheduler" or campaign_type == "network_aware_scheduler" else "config/rescheduling/profiles/RS_C8_RESOURCE_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json"
    rescheduling_profile_path = variant.get("reschedulingProfilePath") or scenario_policy.get("reschedulingProfilePath") or provider_context.get("reschedulingProfilePath") or default_rescheduling_profile_path
    cluster_lens_profile_id = provider_context.get("clusterLensProfileId") or "CL_C9_PLACEMENT_SNAPSHOT"
    cluster_lens_profile_path = variant.get("clusterLensProfilePath") or scenario_policy.get("clusterLensProfilePath") or provider_context.get("clusterLensProfilePath") or pipeline.get("clusterLens") or "config/cluster-lens/profiles/CL_C9_PLACEMENT_SNAPSHOT.json"

    technical_profile_id = provider_context.get("technicalDiagnosisProfileId") or "TD_C2_RESOURCE_VARIATION"
    technical_profile_path = provider_context.get("technicalDiagnosisProfilePath") or "config/technical-diagnosis/profiles/TD_C2_RESOURCE_VARIATION.json"
    technical_root = provider_context.get("technicalDiagnosisArtifactRoot") or f"{campaign_root}/diagnosis"
    reporting_profile_id = provider_context.get("reportingProfileId") or "RP_C2_RESOURCE_VARIATION"
    reporting_profile_path = provider_context.get("reportingProfilePath") or "config/reporting/profiles/RP_C2_RESOURCE_VARIATION.json"
    reporting_root = provider_context.get("reportingArtifactRoot") or f"{campaign_root}/reporting"
    completion_profile_id = provider_context.get("completionGateProfileId") or "CG_C2_RESOURCE_VARIATION"
    completion_profile_path = provider_context.get("completionGateProfilePath") or "config/completion-gate/profiles/CG_C2_RESOURCE_VARIATION.json"
    completion_root = provider_context.get("completionGateArtifactRoot") or f"{campaign_root}/completion-gate"
    freeze_profile_id = provider_context.get("freezeProfileId") or "FR_C2_RESOURCE_VARIATION"
    freeze_profile_path = provider_context.get("freezeProfilePath") or "config/freeze/profiles/FR_C2_RESOURCE_VARIATION.json"
    freeze_root = provider_context.get("freezeArtifactRoot") or f"{campaign_root}/freeze"

    is_default_scheduler_variant = scenario_family in {"default-scheduler", "resource-aware-scheduler"} or bool(scenario.get("defaultSchedulerPolicy")) or bool(scenario.get("schedulerModePolicy"))
    if is_default_scheduler_variant:
        placement_profile_id = variant.get("placementProfileId") or scenario.get("placementProfileId") or "DEFAULT_KUBERNETES_SCHEDULER"
        placement_profile_path = variant.get("placementProfilePath") or scenario.get("placementProfilePath") or ""
        placement_profile = {}
    else:
        placement_profile_id = variant.get("placementProfileId") or provider_context.get("placementProfileId") or "PL_COLOCATED"
        placement_profile_path = variant.get("placementProfilePath") or provider_context.get("placementProfilePath") or "config/placement/profiles/PL_COLOCATED.json"
        placement_profile = load_optional_json(repo_root, placement_profile_path)
    latency_profile_id = variant.get("latencyProfileId") or provider_context.get("latencyProfileId")
    latency_profile_path = variant.get("latencyProfilePath") or provider_context.get("latencyProfilePath")
    app_topology = variant.get("applicationTopology") or {}
    namespace_resolution = namespace_resolution_from_scenario(scenario, app_topology)
    primary_namespace = namespace_resolution["primaryNamespace"]
    all_namespaces = namespace_resolution["namespaces"]
    additional_namespaces = namespace_resolution["additionalNamespaces"]

    replacements = {
        "__CYCLE_ID__": variant_cycle_id,
        "__PARENT_CYCLE_ID__": parent_cycle_id,
        "__VARIANT_ID__": variant_id,
        "__GENERATED_PROFILE_PREFIX__": generated_profile_prefix,
        "__CAMPAIGN_TYPE__": campaign_type,
        "__SCENARIO_FAMILY__": scenario_family,
        "__CYCLE_CONFIG_PATH__": rel(paths["cycle"], repo_root),
        "__BASELINE_ID__": variant_reference_baseline_id,
        "__BASELINE_CONFIG_PATH__": variant_reference_baseline_config_path,
        "__SCENARIO_CONFIG_PATH__": variant["scenarioConfigPath"],
        "__INFRASTRUCTURE_PROFILE_ID__": variant["infrastructureProfileId"],
        "__INFRASTRUCTURE_PROFILE_PATH__": variant["infrastructureProfilePath"],
        "__PROVIDER_BINDING_ID__": variant["providerBindingId"],
        "__PROVIDER_BINDING_PATH__": variant["providerBindingPath"],
        "__KUBECONFIG_PATH__": kubeconfig,
        "__PI_PROFILE_ID__": f"PI_{generated_profile_prefix}",
        "__PI_PROFILE_PATH__": rel(paths["provisioning"], repo_root),
        "__PV_PROFILE_ID__": f"PV_{generated_profile_prefix}",
        "__PV_PROFILE_PATH__": rel(paths["provisioningValidation"], repo_root),
        "__CV_PROFILE_ID__": f"CV_{generated_profile_prefix}",
        "__CV_PROFILE_PATH__": rel(paths["clusterValidation"], repo_root),
        "__AD_PROFILE_ID__": f"AD_{generated_profile_prefix}",
        "__AD_PROFILE_PATH__": rel(paths["applicationDeployment"], repo_root),
        "__MO_PROFILE_ID__": f"MO_{generated_profile_prefix}",
        "__MO_PROFILE_PATH__": rel(paths["minimalObservability"], repo_root),
        "__TC_PROFILE_ID__": f"TC_{generated_profile_prefix}",
        "__TC_PROFILE_PATH__": rel(paths["precheck"], repo_root),
        "__BENCHMARK_CONFIG_PATH__": rel(paths["benchmark"], repo_root),
        "__TECHNICAL_DIAGNOSIS_PROFILE_ID__": technical_profile_id,
        "__TECHNICAL_DIAGNOSIS_PROFILE_PATH__": technical_profile_path,
        "__REPORTING_PROFILE_ID__": reporting_profile_id,
        "__REPORTING_PROFILE_PATH__": reporting_profile_path,
        "__COMPLETION_GATE_PROFILE_ID__": completion_profile_id,
        "__COMPLETION_GATE_PROFILE_PATH__": completion_profile_path,
        "__FREEZE_PROFILE_ID__": freeze_profile_id,
        "__FREEZE_PROFILE_PATH__": freeze_profile_path,
        "__PROVISIONING_ROOT__": provisioning_root,
        "__VALIDATION_ROOT__": validation_root,
        "__DEPLOYMENT_ROOT__": deployment_root,
        "__OBSERVABILITY_ROOT__": observability_root,
        "__PLACEMENT_ROOT__": placement_root,
        "__DELETION_ROOT__": deletion_root,
        "__TECHNICAL_DIAGNOSIS_ROOT__": technical_root,
        "__REPORTING_ROOT__": reporting_root,
        "__COMPLETION_GATE_ROOT__": completion_root,
        "__FREEZE_ROOT__": freeze_root,
        "__VARIANT_ROOT__": variant_root,
        "__CAMPAIGN_ROOT__": campaign_root,
        "__PLACEMENT_PROFILE_ID__": placement_profile_id,
        "__PLACEMENT_PROFILE_PATH__": placement_profile_path,
        "__LATENCY_PROFILE_ID__": latency_profile_id,
        "__LATENCY_PROFILE_PATH__": latency_profile_path,
        "__CYCLE_VARIANT_TEMPLATE_ID__": "PROVIDER_BACKED_CAMPAIGN_VARIANT_CYCLE_TEMPLATE",
        "__CYCLE_VARIANT_TEMPLATE_PATH__": cycle_variant_template_path,
    }

    pi = with_replacements(provisioning_integration_template, replacements)
    pi.update({
        "provisioningIntegrationProfileId": f"PI_{generated_profile_prefix}",
        "profileName": f"Provider-Backed {campaign_type.replace('_', ' ').title()} Provisioning - {variant_id}",
        "profileRole": f"generated_{scenario_family.replace('-', '_')}_provisioning_profile",
        "purpose": f"Provision the provider-backed cluster for {variant_id}.",
        "cycleId": variant_cycle_id,
        "cycleConfigPath": rel(paths["cycle"], repo_root),
        "infrastructureProfileId": variant["infrastructureProfileId"],
        "infrastructureProfilePath": variant["infrastructureProfilePath"],
        "providerBindingId": variant["providerBindingId"],
        "providerBindingPath": variant["providerBindingPath"],
    })
    pi.setdefault("lifecycle", {}).update({
        "lifecyclePolicyId": variant.get("lifecyclePolicyId", "LC_EPHEMERAL_DELETE_CLUSTER"),
        "lifecyclePolicyPath": variant.get("lifecyclePolicyPath", "config/infrastructure/lifecycle/policies/LC_EPHEMERAL_DELETE_CLUSTER.json"),
        "clusterLifecycleMode": variant.get("clusterLifecycleMode", "ephemeral"),
        "destroyClusterAfterCycle": True,
        "deleteClusterAfterCycle": True,
    })
    pi.setdefault("artifactPolicy", {}).update({
        "root": provisioning_root,
        "logsRoot": f"{provisioning_root}/logs",
        "manifestsRoot": f"{provisioning_root}/manifests",
        "commandsRoot": f"{provisioning_root}/commands",
        "latestManifestPath": f"{provisioning_root}/latest-provisioning-integration-manifest.json",
        "latestTextSummaryPath": f"{provisioning_root}/latest-provisioning-integration-summary.txt",
        "writeLatestAliases": True,
    })
    pi.setdefault("kubeconfigVerification", {}).update({"expectedPath": kubeconfig})
    pi.setdefault("clusterValidation", {}).update({
        "clusterValidationProfileId": f"CV_{generated_profile_prefix}",
        "clusterValidationProfilePath": rel(paths["clusterValidation"], repo_root),
        "clusterValidationIndexPath": provider_context.get("clusterValidationIndexPath", "config/cluster-validation/CLUSTER_VALIDATION_INDEX.json"),
        "requiredAfterSuccessfulProvisioning": True,
        "runner": "scripts/infrastructure/validation/run-provider-backed-cluster-validation.py",
    })
    pi["profileGovernance"] = {
        "scope": f"generated_{scenario_family.replace('-', '_')}_variant",
        "cycleId": variant_cycle_id,
        "campaignParentCycleId": parent_cycle_id,
        "variantId": variant_id,
        "infrastructureProfileId": variant["infrastructureProfileId"],
        "providerId": "proxmox-k3s",
        "status": "generated",
        "pathRole": "runtime_generated_profile",
        "templateId": "PI_PROVIDER_BACKED_PROVISIONING_TEMPLATE",
        "templatePath": provisioning_integration_template_path,
    }

    control_plane_nodes, worker_nodes = expected_kubernetes_nodes_from_infrastructure_profile(infrastructure_profile)
    node_naming = infrastructure_profile.get("nodeNaming") or {}
    selectors = infrastructure_profile.get("selectors") or {}
    validation_spec = infrastructure_profile.get("validation") or {}
    expected_worker_selector = (
        validation_spec.get("expectedWorkerLabelSelector")
        or "nodepool=workers"
    )

    pv = with_replacements(provisioning_validation_template, replacements)
    pv.update({
        "profileId": f"PV_{generated_profile_prefix}",
        "profileName": f"Provider-Backed {campaign_type.replace('_', ' ').title()} Provisioning Validation - {variant_id}",
        "description": f"Runtime-generated provisioning validation profile for the provider-backed cluster used by variant {variant_id}.",
        "profileRole": f"generated_{scenario_family.replace('-', '_')}_provisioning_validation_profile",
    })
    pv.setdefault("scope", {}).update({
        "phase": "provider_backed_cluster_validation",
        "tool": "proxmox-k3s",
        "purpose": f"Validate the provider-backed K3s cluster for variant {variant_id} before LocalAI deployment and benchmark execution.",
    })
    pv.setdefault("provisioning", {}).update({
        "localConfigTemplatePath": variant.get("providerConfigExamplePath"),
        "recommendedLocalConfigPath": variant.get("providerConfigLocalPath"),
        "recommendedKubeconfigPath": kubeconfig,
        "providerBindingId": variant["providerBindingId"],
        "providerBindingPath": variant["providerBindingPath"],
        "providerBindingsIndexPath": provider_context.get("providerBindingsIndexPath", "config/infrastructure/providers/proxmox-k3s/PROXMOX_K3S_PROVIDER_BINDINGS_INDEX.json"),
        "provisioningIntegrationProfileId": f"PI_{generated_profile_prefix}",
        "provisioningIntegrationProfilePath": rel(paths["provisioning"], repo_root),
        "provisioningIntegrationIndexPath": pipeline_context(campaign_cycle).get("provisioningIntegrationIndex") or "config/provisioning/PROVISIONING_INTEGRATION_INDEX.json",
    })
    expected_management_nodes = list(validation_spec.get("expectedManagementNodes") or [])
    expected_management_label_selector = validation_spec.get("expectedManagementLabelSelector")
    expected_management_taints = list(validation_spec.get("expectedManagementTaints") or [])

    pv_expected_cluster = {
        "infrastructureProfileId": variant["infrastructureProfileId"],
        "nodeNamingConventionId": node_naming.get("nodeNamingConventionId"),
        "expectedControlPlaneNodes": control_plane_nodes,
        "expectedWorkerNodes": worker_nodes,
        "expectedWorkerLabelSelector": expected_worker_selector,
        "minimumReadyNodes": len(control_plane_nodes) + len(worker_nodes),
        "requireAllExpectedNodesReady": True,
        "requireK3sDistribution": bool(validation_spec.get("requireK3sDistribution", True)),
        "infrastructureProfilePath": variant["infrastructureProfilePath"],
    }
    if expected_management_nodes:
        pv_expected_cluster["expectedManagementNodes"] = expected_management_nodes
    if expected_management_label_selector:
        pv_expected_cluster["expectedManagementLabelSelector"] = expected_management_label_selector
    if expected_management_taints:
        pv_expected_cluster["expectedManagementTaints"] = expected_management_taints

    pv.setdefault("expectedCluster", {}).update(pv_expected_cluster)
    pv.setdefault("output", {}).update({
        "defaultOutputRoot": validation_root,
        "writeLatestAliases": True,
        "jsonSuffix": "validation.json",
        "textSuffix": "validation.txt",
        "markdownSuffix": "validation.md",
        "latestJsonPath": f"{validation_root}/latest-validation.json",
        "latestTextPath": f"{validation_root}/latest-validation.txt",
        "latestMarkdownPath": f"{validation_root}/latest-validation.md",
    })
    pv.setdefault("clusterLifecycle", {}).update({
        "lifecyclePolicyId": variant.get("lifecyclePolicyId", "LC_EPHEMERAL_DELETE_CLUSTER"),
        "lifecyclePolicyPath": variant.get("lifecyclePolicyPath", "config/infrastructure/lifecycle/policies/LC_EPHEMERAL_DELETE_CLUSTER.json"),
        "clusterLifecycleMode": variant.get("clusterLifecycleMode", "ephemeral"),
        "destroyClusterAfterCycleDefault": bool(variant.get("destroyClusterAfterVariant", True)),
        "lifecyclePoliciesIndexPath": provider_context.get("lifecyclePoliciesIndexPath", "config/infrastructure/lifecycle/CLUSTER_LIFECYCLE_POLICIES_INDEX.json"),
        "lifecycleManifestRequired": True,
        "lifecycleArtifactRoot": f"{variant_root}/infrastructure/lifecycle",
    })
    pv.setdefault("preValidationGate", {}).update({
        "provisioningIntegrationLatestManifestPath": f"{provisioning_root}/latest-provisioning-integration-manifest.json"
    })
    pv.setdefault("clusterValidation", {}).update({
        "clusterValidationProfileId": f"CV_{generated_profile_prefix}",
        "clusterValidationProfilePath": rel(paths["clusterValidation"], repo_root),
        "clusterValidationIndexPath": provider_context.get("clusterValidationIndexPath", "config/cluster-validation/CLUSTER_VALIDATION_INDEX.json"),
        "requiredBeforeApplicationDeployment": True,
    })
    pv["profileGovernance"] = {
        "scope": f"generated_{scenario_family.replace('-', '_')}_variant",
        "cycleId": variant_cycle_id,
        "campaignParentCycleId": parent_cycle_id,
        "variantId": variant_id,
        "infrastructureProfileId": variant["infrastructureProfileId"],
        "providerId": "proxmox-k3s",
        "status": "generated",
        "pathRole": "runtime_generated_profile",
    }

    cv = with_replacements(cluster_validation_template, replacements)
    cv.update({
        "clusterValidationProfileId": f"CV_{generated_profile_prefix}",
        "profileName": f"Provider-Backed {campaign_type.replace('_', ' ').title()} Cluster Validation - {variant_id}",
        "profileRole": f"generated_{scenario_family.replace('-', '_')}_cluster_validation_profile",
        "purpose": f"Validate the provider-backed K3s cluster for variant {variant_id}.",
        "cycleId": variant_cycle_id,
        "cycleConfigPath": rel(paths["cycle"], repo_root),
        "infrastructureProfileId": variant["infrastructureProfileId"],
        "infrastructureProfilePath": variant["infrastructureProfilePath"],
        "providerBindingId": variant["providerBindingId"],
        "providerBindingPath": variant["providerBindingPath"],
        "provisioningIntegrationProfileId": f"PI_{generated_profile_prefix}",
        "provisioningIntegrationProfilePath": rel(paths["provisioning"], repo_root),
        "provisioningIntegrationTemplateId": provider_context.get("provisioningIntegrationTemplateId", "PI_PROVIDER_BACKED_PROVISIONING_TEMPLATE"),
        "provisioningIntegrationTemplatePath": provisioning_integration_template_path,
        "provisioningIntegrationIndexPath": provider_context.get("provisioningIntegrationIndexPath", "config/provisioning/PROVISIONING_INTEGRATION_INDEX.json"),
        "provisioningValidationProfileId": f"PV_{generated_profile_prefix}",
        "provisioningValidationProfilePath": rel(paths["provisioningValidation"], repo_root),
        "kubeconfigPath": kubeconfig,
    })
    cv.setdefault("expectedCluster", {}).update({
        "expectedManagementNodes": expected_management_nodes,
        "expectedManagementLabelSelector": expected_management_label_selector,
        "expectedManagementTaints": expected_management_taints,
    })
    cv.setdefault("preValidationGate", {}).update({"latestProvisioningIntegrationManifestPath": f"{provisioning_root}/latest-provisioning-integration-manifest.json"})
    cv.setdefault("artifactPolicy", {}).update({
        "root": validation_root,
        "logsRoot": f"{validation_root}/logs",
        "manifestsRoot": f"{validation_root}/manifests",
        "latestManifestPath": f"{validation_root}/latest-cluster-validation-manifest.json",
        "latestTextSummaryPath": f"{validation_root}/latest-cluster-validation-summary.txt",
        "writeLatestAliases": True,
    })
    cv.setdefault("applicationDeployment", {}).update({
        "applicationDeploymentProfileId": f"AD_{generated_profile_prefix}",
        "applicationDeploymentProfilePath": rel(paths["applicationDeployment"], repo_root),
        "requiredAfterSuccessfulValidation": True,
        "runner": "scripts/application/deployment/run-provider-backed-localai-deployment.py",
    })
    cv.setdefault("downstreamConsumers", {}).update({
        "minimalObservabilityProfileId": f"MO_{generated_profile_prefix}",
        "minimalObservabilityProfilePath": rel(paths["minimalObservability"], repo_root),
        "reason": "Minimal observability consumes the validated kubeconfig, Metrics API and Kubernetes snapshots after the cluster validation gate passes.",
    })
    cv["profileGovernance"] = {
        "scope": f"generated_{scenario_family.replace('-', '_')}_variant",
        "cycleId": variant_cycle_id,
        "campaignParentCycleId": parent_cycle_id,
        "variantId": variant_id,
        "infrastructureProfileId": variant["infrastructureProfileId"],
        "providerId": "proxmox-k3s",
        "status": "generated",
        "pathRole": "runtime_generated_profile",
        "templateId": "CV_PROVIDER_BACKED_VALIDATION_TEMPLATE",
        "templatePath": cluster_validation_template_path,
    }

    ad = with_replacements(application_deployment_template, replacements)
    ad.update({
        "applicationDeploymentProfileId": f"AD_{generated_profile_prefix}",
        "profileName": f"Provider-Backed {campaign_type.replace('_', ' ').title()} LocalAI Deployment - {variant_id}",
        "profileRole": f"generated_{scenario_family.replace('-', '_')}_localai_deployment_profile",
        "purpose": f"Deploy the declared LocalAI topology on the provider-backed cluster for {variant_id}.",
        "cycleId": variant_cycle_id,
        "scenarioId": scenario_id,
        "variantId": variant_id,
        "scenarioConfigPath": variant["scenarioConfigPath"],
        "baselineId": variant_reference_baseline_id,
        "baselineConfigPath": variant_reference_baseline_config_path,
        "referenceBaselineId": variant_reference_baseline_id,
        "referenceBaselineConfigPath": variant_reference_baseline_config_path,
        "referenceScenarioId": variant_reference_scenario_id,
        "referenceScenarioConfigPath": variant_reference_scenario_config_path,
        "cycleConfigPath": rel(paths["cycle"], repo_root),
        "infrastructureProfileId": variant["infrastructureProfileId"],
        "infrastructureProfilePath": variant["infrastructureProfilePath"],
        "clusterValidationProfileId": f"CV_{generated_profile_prefix}",
        "clusterValidationProfilePath": rel(paths["clusterValidation"], repo_root),
    })
    ad_topology = ad.setdefault("deploymentTopology", {})
    ad_topology["kubeconfigPath"] = kubeconfig
    ad_topology["namespace"] = primary_namespace
    ad_topology["namespaces"] = list(all_namespaces)
    ad_topology["additionalNamespaces"] = list(additional_namespaces)
    ad_topology["namespaceResolution"] = copy.deepcopy(namespace_resolution)
    smoke_validation = ad.setdefault("smokeValidation", {})
    smoke_validation.setdefault("portForward", {})["namespace"] = primary_namespace

    smoke_targets = build_smoke_validation_targets(scenario) if is_default_scheduler_variant else []
    if smoke_targets:
        smoke_validation["targets"] = smoke_targets
        primary_smoke_target = smoke_targets[0]
        smoke_validation["baseUrl"] = primary_smoke_target["baseUrl"]
        smoke_validation["model"] = primary_smoke_target["model"]
        smoke_validation.setdefault("portForward", {}).update(primary_smoke_target["portForward"])
        ad_topology["smokeValidationTargets"] = [
            {
                "tenantId": target["tenantId"],
                "namespace": target["namespace"],
                "serviceName": target["serviceName"],
                "baseUrl": target["baseUrl"],
                "model": target["model"],
            }
            for target in smoke_targets
        ]

    if app_topology.get("kustomizeApplyOrder"):
        ad_topology["kustomizeApplyOrder"] = copy.deepcopy(app_topology.get("kustomizeApplyOrder") or [])
    else:
        apply_path_by_step = {
            "namespace": app_topology.get("namespaceManifest") or scenario.get("namespaceManifest"),
            "storage": app_topology.get("storageManifest") or scenario.get("storageManifest"),
            "rpc-worker-services": app_topology.get("sharedServicesManifest") or scenario.get("sharedServicesManifest"),
        }
        for target in ad_topology.get("kustomizeApplyOrder", []):
            replacement_path = apply_path_by_step.get(target.get("stepId"))
            if replacement_path:
                target["path"] = replacement_path

    worker_count_value = app_topology.get("localAiWorkerCount") or localai_worker_count_per_tenant_from_scenario(scenario)
    worker_scenario = app_topology.get("workerScenario") or scenario.get("workerScenario")
    infrastructure_worker_count = len(worker_nodes) if worker_nodes else None
    topology_selection = select_topology_from_placement_profile(placement_profile, worker_scenario, infrastructure_worker_count) if placement_profile else {}
    worker_mapping_selection = select_worker_node_mapping_from_placement_profile(placement_profile, worker_scenario, infrastructure_worker_count) if placement_profile else {}

    topology_dir = app_topology.get("topologyDir") or scenario.get("topologyDir") or topology_selection.get("selectedTopologyDir")
    if topology_dir:
        for target in ad_topology.get("kustomizeApplyOrder", []):
            if target.get("stepId") == "worker-topology":
                target["path"] = topology_dir
        ad_topology.setdefault("workerCount", {})["topologyDir"] = topology_dir
    server_manifest = app_topology.get("serverManifest") or scenario.get("serverManifest")
    if server_manifest:
        for target in ad_topology.get("kustomizeApplyOrder", []):
            if target.get("stepId") == "server-model":
                target["path"] = server_manifest
        ad_topology.setdefault("model", {})["serverManifest"] = server_manifest
    model_name = scenario.get("resolvedModelName") or scenario.get("modelName")
    if model_name:
        ad_topology.setdefault("model", {})["modelName"] = model_name
        ad.setdefault("smokeValidation", {})["model"] = model_name
    if worker_count_value is not None:
        ad_topology["localAiWorkerCountPerTenant"] = worker_count_value
        ad_topology.setdefault("workerCount", {}).update({
            "scenarioId": worker_scenario,
            "scenarioPath": app_topology.get("workerScenarioPath") or scenario.get("workerScenarioPath") or f"config/scenarios/pilot/worker-count/{worker_scenario}.json",
            "count": worker_count_value,
            "localAiWorkerCountPerTenant": worker_count_value,
            "topologyDir": topology_dir or ad_topology.get("workerCount", {}).get("topologyDir"),
            "topologySelection": topology_selection,
            "expectedActiveRpcWorkers": app_topology.get("expectedActiveRpcWorkers") or scenario.get("expectedActiveRpcWorkers") or ad_topology.get("workerCount", {}).get("expectedActiveRpcWorkers"),
            "expectedInactiveRpcWorkers": app_topology.get("expectedInactiveRpcWorkers") or scenario.get("expectedInactiveRpcWorkers") or [],
        })
    expected_worker_nodes = app_topology.get("expectedWorkerNodes") or scenario.get("expectedWorkerNodes") or worker_mapping_selection.get("selectedWorkerNodeMap") or {}
    placement_type = app_topology.get("placementType") or scenario.get("resolvedPlacementType") or (placement_profile.get("strategy") if placement_profile else None)
    placement_scenario_id = scenario.get("scenarioId") or app_topology.get("placementScenario") or scenario.get("placementScenario")
    placement_reference_id = app_topology.get("placementScenario") or scenario.get("placementScenario") or placement_profile_id
    ad_topology.setdefault("placement", {}).update({
        "scenarioId": placement_scenario_id,
        "scenarioPath": app_topology.get("placementScenarioPath") or scenario.get("placementScenarioPath") or scenario.get("placementProfilePath"),
        "placementScenarioId": placement_scenario_id,
        "placementReferenceId": placement_reference_id,
        "canonicalPlacementProfileId": placement_profile_id,
        "placementType": placement_type,
        "expectedWorkerNodes": expected_worker_nodes,
        "expectedInfrastructureWorkerNodes": worker_nodes,
        "infrastructureWorkerNodeCount": infrastructure_worker_count,
        "workerNodeMappingSelection": worker_mapping_selection,
        "topologySelection": topology_selection,
        "selectorMode": (placement_profile.get("selectorPolicy") or {}).get("selectorMode") if placement_profile else None,
        "placementProfileId": placement_profile_id,
        "placementProfilePath": placement_profile_path,
        "latencyProfileId": latency_profile_id,
        "latencyProfilePath": latency_profile_path,
        "latencyInjectionArtifactRoot": f"{variant_root}/latency-injection",
        "placementProfilesIndexPath": provider_context.get("placementProfilesIndexPath", "config/placement/PLACEMENT_PROFILES_INDEX.json"),
        "strategy": placement_profile.get("strategy") if placement_profile else placement_type,
        "expectedServerNode": app_topology.get("expectedServerNode") or scenario.get("expectedServerNode") or ((placement_profile.get("serverPlacement") or {}).get("expectedNode") if placement_profile else None),
        "nodePoolLabel": ((placement_profile.get("selectorPolicy") or {}).get("workerNodePoolLabel") if placement_profile else {"nodepool": "workers"}),
        "profileResearchQuestion": placement_profile.get("researchQuestion") if placement_profile else None,
    })
    active = app_topology.get("expectedActiveRpcWorkers") or scenario.get("expectedActiveRpcWorkers") or ad_topology.get("workerCount", {}).get("expectedActiveRpcWorkers") or []
    inactive = app_topology.get("expectedInactiveRpcWorkers") or scenario.get("expectedInactiveRpcWorkers") or []
    if app_topology.get("expectedResources"):
        ad_topology["expectedResources"] = copy.deepcopy(app_topology.get("expectedResources") or {})
    expected_resources = ad_topology.setdefault("expectedResources", {})
    expected_resources.setdefault("deployments", ["localai-server"] + list(active))
    expected_resources.setdefault("inactiveDeployments", list(inactive))
    expected_resources.setdefault("minimumReadyDeployments", len(expected_resources.get("deployments", [])))
    if scenario_family in {"default-scheduler", "resource-aware-scheduler"}:
        deployments_per_tenant = list(expected_resources.get("deploymentsPerTenant") or [])
        if deployments_per_tenant:
            expected_resources["deployments"] = deployments_per_tenant
            expected_resources.setdefault("minimumReadyDeployments", len(deployments_per_tenant))
            if not app_topology.get("additionalRolloutTargets"):
                rollout_timeout = int(expected_resources.get("rolloutTimeoutSeconds") or 900)
                namespace_to_tenant = namespace_resolution.get("namespaceToTenant", {}) or {}
                ad_topology["additionalRolloutTargets"] = [
                    {
                        "tenantId": namespace_to_tenant.get(namespace) or namespace,
                        "namespace": namespace,
                        "deployments": deployments_per_tenant,
                        "rolloutTimeoutSeconds": rollout_timeout,
                    }
                    for namespace in additional_namespaces
                ]
        if scenario_family == "default-scheduler":
            ad_topology["defaultSchedulerBaseline"] = {
                "enabled": True,
                "placementDecisionOwner": "kubernetes_default_scheduler",
                "hardPlacementControlsAllowed": False,
                "schedulerEvidenceRequired": True,
                "scenarioConfigPath": variant["scenarioConfigPath"],
            }
        else:
            scheduler_policy = scenario.get("schedulerModePolicy") or {}
            ad_topology["schedulerMode"] = {
                "enabled": True,
                "schedulerMode": scheduler_policy.get("schedulerMode"),
                "schedulerName": scheduler_policy.get("schedulerName"),
                "placementDecisionOwner": scheduler_policy.get("schedulerName") or "kubernetes_default_scheduler",
                "hardPlacementControlsAllowed": False,
                "schedulerEvidenceRequired": True,
                "scenarioConfigPath": variant["scenarioConfigPath"],
            }
    if app_topology.get("additionalRolloutTargets"):
        namespace_to_tenant = namespace_resolution.get("namespaceToTenant", {}) or {}
        explicit_rollout_targets = copy.deepcopy(app_topology.get("additionalRolloutTargets") or [])
        for target in explicit_rollout_targets:
            if isinstance(target, dict) and target.get("namespace") and not target.get("tenantId"):
                target["tenantId"] = namespace_to_tenant.get(str(target.get("namespace"))) or str(target.get("namespace"))
        ad_topology["additionalRolloutTargets"] = explicit_rollout_targets
    if app_topology.get("tenancyProfileId"):
        ad_topology["tenancyProfileId"] = app_topology.get("tenancyProfileId")
        ad_topology["tenancyProfilePath"] = app_topology.get("tenancyProfilePath")
    ad.setdefault("preDeploymentGate", {}).update({"latestClusterValidationManifestPath": f"{validation_root}/latest-cluster-validation-manifest.json"})
    ad.setdefault("artifactPolicy", {}).update({
        "root": deployment_root,
        "logsRoot": f"{deployment_root}/logs",
        "manifestsRoot": f"{deployment_root}/manifests",
        "snapshotsRoot": f"{deployment_root}/snapshots",
        "latestManifestPath": f"{deployment_root}/latest-localai-deployment-manifest.json",
        "latestTextSummaryPath": f"{deployment_root}/latest-localai-deployment-summary.txt",
        "latestSmokeResultPath": f"{deployment_root}/latest-smoke-result.json",
        "writeLatestAliases": True,
    })
    ad.update({"minimalObservabilityProfileId": f"MO_{generated_profile_prefix}", "minimalObservabilityProfilePath": rel(paths["minimalObservability"], repo_root)})
    ad.setdefault("postDeploymentObservability", {}).update({
        "minimalObservabilityProfileId": f"MO_{generated_profile_prefix}",
        "minimalObservabilityProfilePath": rel(paths["minimalObservability"], repo_root),
        "artifactRoot": observability_root,
    })
    ad["profileGovernance"] = {
        "scope": f"generated_{scenario_family.replace('-', '_')}_variant",
        "cycleId": variant_cycle_id,
        "campaignParentCycleId": parent_cycle_id,
        "variantId": variant_id,
        "infrastructureProfileId": variant["infrastructureProfileId"],
        "providerId": "proxmox-k3s",
        "status": "generated",
        "pathRole": "runtime_generated_profile",
        "templateId": "AD_PROVIDER_BACKED_LOCALAI_DEPLOYMENT_TEMPLATE",
        "templatePath": application_deployment_template_path,
    }

    mo = with_replacements(minimal_observability_template, replacements)
    mo.update({
        "minimalObservabilityProfileId": f"MO_{generated_profile_prefix}",
        "profileName": f"Provider-Backed {campaign_type.replace('_', ' ').title()} Minimal Observability - {variant_id}",
        "profileRole": f"generated_{scenario_family.replace('-', '_')}_minimal_observability_profile",
        "purpose": f"Collect minimal K3s and LocalAI evidence for variant {variant_id}.",
        "cycleId": variant_cycle_id,
        "cycleConfigPath": rel(paths["cycle"], repo_root),
        "scenarioId": scenario_id,
        "variantId": variant_id,
        "scenarioConfigPath": variant["scenarioConfigPath"],
        "baselineId": variant_reference_baseline_id,
        "baselineConfigPath": variant_reference_baseline_config_path,
        "referenceBaselineId": variant_reference_baseline_id,
        "referenceBaselineConfigPath": variant_reference_baseline_config_path,
        "referenceScenarioId": variant_reference_scenario_id,
        "referenceScenarioConfigPath": variant_reference_scenario_config_path,
        "infrastructureProfileId": variant["infrastructureProfileId"],
        "infrastructureProfilePath": variant["infrastructureProfilePath"],
        "namespace": primary_namespace,
        "namespaces": list(all_namespaces),
        "additionalNamespaces": list(additional_namespaces),
        "namespaceCollectionPolicy": {
            "primaryNamespace": primary_namespace,
            "collectAllScenarioNamespaces": True,
            "namespaceRoles": copy.deepcopy(namespace_resolution.get("namespaceRoles") or []),
            "multiNamespace": bool(namespace_resolution.get("isMultiNamespace")),
        },
        "kubeconfigPath": kubeconfig,
        "applicationDeploymentProfileId": f"AD_{generated_profile_prefix}",
        "applicationDeploymentProfilePath": rel(paths["applicationDeployment"], repo_root),
    })
    mo.setdefault("artifactPolicy", {}).update({
        "root": observability_root,
        "logsRoot": f"{observability_root}/logs",
        "snapshotsRoot": f"{observability_root}/snapshots",
        "manifestsRoot": f"{observability_root}/manifests",
        "summariesRoot": f"{observability_root}/summaries",
        "latestManifestPath": f"{observability_root}/latest-minimal-observability-manifest.json",
        "latestTextSummaryPath": f"{observability_root}/latest-minimal-observability-summary.txt",
        "latestMetricsSnapshotPath": f"{observability_root}/latest-minimal-observability-metrics.json",
        "writeLatestAliases": True,
    })
    mo.update({
        "placementProfileId": placement_profile_id,
        "placementProfilePath": placement_profile_path,
    })
    mo.setdefault("gates", {}).update({
        "latestClusterValidationManifestPath": f"{validation_root}/latest-cluster-validation-manifest.json",
        "latestApplicationDeploymentManifestPath": f"{deployment_root}/latest-localai-deployment-manifest.json",
    })
    mo["profileGovernance"] = {
        "scope": f"generated_{scenario_family.replace('-', '_')}_variant",
        "cycleId": variant_cycle_id,
        "campaignParentCycleId": parent_cycle_id,
        "variantId": variant_id,
        "infrastructureProfileId": variant["infrastructureProfileId"],
        "providerId": "proxmox-k3s",
        "status": "generated",
        "pathRole": "runtime_generated_profile",
        "templateId": "MO_PROVIDER_BACKED_OBSERVABILITY_TEMPLATE",
        "templatePath": minimal_observability_template_path,
    }

    expected_ready_nodes = control_plane_nodes + worker_nodes
    tc = copy.deepcopy(precheck_template)
    tc.update({
        "profileId": f"TC_{generated_profile_prefix}",
        "description": f"Provider-backed benchmark technical pre-check for {scenario_family} variant {variant_id}.",
        "kubeconfig": kubeconfig,
        "namespace": primary_namespace,
        "additionalNamespaces": list(additional_namespaces),
        "namespaceValidationPolicy": {
            "primaryNamespace": primary_namespace,
            "additionalNamespaces": list(additional_namespaces),
            "validateAdditionalNamespaces": bool(additional_namespaces),
            "minimumPodsPerAdditionalNamespace": 1,
            "treatAdditionalNamespaceWarningsAsBlocking": True,
            "namespaceRoles": copy.deepcopy(namespace_resolution.get("namespaceRoles") or []),
        },
        "expectedReadyNodes": expected_ready_nodes,
        "expectedWorkerNodes": worker_nodes,
        "defaultOutputRoot": f"{variant.get('resultsRoot', f'{campaign_root}/benchmark/{scenario_family}')}/{variant.get('outputSubdir', variant_id + '_official_locked')}",
    })
    if scenario_family in {"node-count-variation", "resource-variation", "placement-variation", "latency-injection", "multi-tenancy"}:
        localai_worker_count = int((app_topology.get("localAiWorkerCount") or scenario.get("resolvedWorkerCount") or 4))
        max_recovered_restarts = int(
            scenario.get("maxRecoveredRestartsInNamespace")
            or variant.get("maxRecoveredRestartsInNamespace")
            or max(2, localai_worker_count)
        )
        tc["restartTolerancePolicy"] = {
            "treatRecoveredRestartsAsWarning": True,
            "maxRecoveredRestartsInNamespace": max_recovered_restarts,
            "requireAllContainersReady": True,
            "requireServiceEndpointReady": True,
            "warningOnly": True,
            "rationale": "Transient LocalAI worker restarts after provider-backed deployment are retained as diagnostic warnings when all pods are Running/Ready and the model endpoint is available.",
        }
    tc["providerBackedInfrastructure"] = {
        "cycleId": parent_cycle_id,
        "variantId": variant_id,
        "infrastructureProfileId": variant.get("infrastructureProfileId"),
        "infrastructureProfilePath": variant.get("infrastructureProfilePath"),
        "providerBindingId": variant.get("providerBindingId"),
        "providerBindingPath": variant.get("providerBindingPath"),
    }

    benchmark_config = build_generated_benchmark_config(
        reference_baseline=reference_baseline,
        scenario=scenario,
        parent_cycle_id=parent_cycle_id,
        variant_id=variant_id,
        scenario_id=scenario_id,
        scenario_family=scenario_family,
        generated_profile_prefix=generated_profile_prefix,
        variant=variant,
        variant_reference_baseline_id=variant_reference_baseline_id,
        variant_reference_baseline_config_path=variant_reference_baseline_config_path,
        variant_reference_scenario_id=variant_reference_scenario_id,
        variant_reference_scenario_config_path=variant_reference_scenario_config_path,
        source_scenario_id=str(scenario.get("scenarioId") or scenario.get("variantId") or variant_id),
        source_scenario_config_path=str(variant.get("scenarioConfigPath") or variant_reference_scenario_config_path),
        benchmark_config_path=rel(paths["benchmark"], repo_root),
        application_deployment_path=rel(paths["applicationDeployment"], repo_root),
        minimal_observability_path=rel(paths["minimalObservability"], repo_root),
        precheck_path=rel(paths["precheck"], repo_root),
        primary_namespace=primary_namespace,
        all_namespaces=all_namespaces,
        additional_namespaces=additional_namespaces,
        provider_context=provider_context,
        placement_profile_id=placement_profile_id,
        placement_profile_path=placement_profile_path,
        latency_profile_id=latency_profile_id,
        latency_profile_path=latency_profile_path,
        variant_root=variant_root,
        deployment_root=deployment_root,
        observability_root=observability_root,
    )

    variant_cycle = with_replacements(cycle_variant_template, replacements)
    variant_cycle.update({
        "cycleId": variant_cycle_id,
        "cycleKind": "runtime_campaign_variant",
        "cycleType": f"provider_backed_{scenario_family.replace('-', '_')}_variant",
        "cycleName": f"{parent_cycle_id} {campaign_type.replace('_', ' ').title()} Variant {variant_id}",
        "profileStatus": "generated_runtime_profile",
        "status": "generated_campaign_variant_cycle",
        "description": f"Runtime-generated provider-backed variant cycle for {variant_id} within the {parent_cycle_id} campaign.",
        "campaignParentCycleId": parent_cycle_id,
        "campaignType": campaign_type,
        "scenarioFamily": scenario_family,
        "profileGovernance": {
            "scope": f"generated_{scenario_family.replace('-', '_')}_variant_cycle",
            "cycleId": variant_cycle_id,
            "campaignParentCycleId": parent_cycle_id,
            "variantId": variant_id,
            "status": "generated",
            "pathRole": "runtime_generated_cycle_profile",
            "templateId": "PROVIDER_BACKED_CAMPAIGN_VARIANT_CYCLE_TEMPLATE",
            "templatePath": cycle_variant_template_path,
        },
    })
    variant_cycle["providerBackedInfrastructure"] = copy.deepcopy(variant_cycle.get("providerBackedInfrastructure") or {})
    pbi = variant_cycle["providerBackedInfrastructure"]
    pbi.update({
        "infrastructureProfileId": variant["infrastructureProfileId"],
        "infrastructureProfilePath": variant["infrastructureProfilePath"],
        "provider": "proxmox-k3s",
        "providerConfigExamplePath": variant.get("providerConfigExamplePath"),
        "providerConfigLocalPath": variant.get("providerConfigLocalPath"),
        "providerBindingId": variant["providerBindingId"],
        "providerBindingPath": variant["providerBindingPath"],
        "clusterLifecycleMode": variant.get("clusterLifecycleMode", "ephemeral"),
        "destroyClusterAfterCycle": True,
        "lifecyclePolicyId": variant.get("lifecyclePolicyId", "LC_EPHEMERAL_DELETE_CLUSTER"),
        "lifecyclePolicyPath": variant.get("lifecyclePolicyPath", "config/infrastructure/lifecycle/policies/LC_EPHEMERAL_DELETE_CLUSTER.json"),
        "kubeconfigPath": kubeconfig,
        "generatedKubeconfigPath": kubeconfig,
        "provisioningLogRoot": provisioning_root,
        "deletionLogRoot": deletion_root,
        "clusterValidationArtifactRoot": validation_root,
        "applicationDeploymentArtifactRoot": deployment_root,
        "minimalObservabilityArtifactRoot": observability_root,
        "schedulerModeArtifactRoot": resource_aware_scheduler_root,
        "customSchedulerArtifactRoot": custom_scheduler_root,
        "monAgentArtifactRoot": mon_agent_root,
        "networkObservabilityArtifactRoot": network_observability_root,
        "istioGatewayArtifactRoot": istio_gateway_root,
        "reschedulingArtifactRoot": rescheduling_root,
        "clusterLensProfileId": cluster_lens_profile_id,
        "clusterLensProfilePath": cluster_lens_profile_path,
        "clusterLensArtifactRoot": cluster_lens_root,
        "placementProfileArtifactRoot": placement_root,
        "placementProfileId": placement_profile_id,
        "placementProfilePath": placement_profile_path,
        "latencyProfileId": latency_profile_id,
        "latencyProfilePath": latency_profile_path,
        "latencyInjectionArtifactRoot": f"{variant_root}/latency-injection",
        "provisioningIntegrationProfileId": f"PI_{generated_profile_prefix}",
        "provisioningIntegrationProfilePath": rel(paths["provisioning"], repo_root),
        "provisioningIntegrationTemplateId": provider_context.get("provisioningIntegrationTemplateId", "PI_PROVIDER_BACKED_PROVISIONING_TEMPLATE"),
        "provisioningIntegrationTemplatePath": provisioning_integration_template_path,
        "provisioningIntegrationIndexPath": provider_context.get("provisioningIntegrationIndexPath", "config/provisioning/PROVISIONING_INTEGRATION_INDEX.json"),
        "provisioningValidationProfileId": f"PV_{generated_profile_prefix}",
        "provisioningValidationProfilePath": rel(paths["provisioningValidation"], repo_root),
        "provisioningValidationTemplateId": provider_context.get("provisioningValidationTemplateId", "PV_PROVIDER_BACKED_VALIDATION_TEMPLATE"),
        "provisioningValidationTemplatePath": provisioning_validation_template_path,
        "provisioningValidationIndexPath": provider_context.get("provisioningValidationIndexPath", "config/provisioning-validation/PROVISIONING_VALIDATION_INDEX.json"),
        "clusterValidationProfileId": f"CV_{generated_profile_prefix}",
        "clusterValidationProfilePath": rel(paths["clusterValidation"], repo_root),
        "clusterValidationTemplateId": provider_context.get("clusterValidationTemplateId", "CV_PROVIDER_BACKED_VALIDATION_TEMPLATE"),
        "clusterValidationTemplatePath": cluster_validation_template_path,
        "clusterValidationIndexPath": provider_context.get("clusterValidationIndexPath", "config/cluster-validation/CLUSTER_VALIDATION_INDEX.json"),
        "applicationDeploymentProfileId": f"AD_{generated_profile_prefix}",
        "applicationDeploymentProfilePath": rel(paths["applicationDeployment"], repo_root),
        "applicationDeploymentTemplateId": provider_context.get("applicationDeploymentTemplateId", "AD_PROVIDER_BACKED_LOCALAI_DEPLOYMENT_TEMPLATE"),
        "applicationDeploymentTemplatePath": application_deployment_template_path,
        "applicationDeploymentIndexPath": provider_context.get("applicationDeploymentIndexPath", "config/application-deployment/APPLICATION_DEPLOYMENT_INDEX.json"),
        "minimalObservabilityProfileId": f"MO_{generated_profile_prefix}",
        "minimalObservabilityProfilePath": rel(paths["minimalObservability"], repo_root),
        "minimalObservabilityTemplateId": provider_context.get("minimalObservabilityTemplateId", "MO_PROVIDER_BACKED_OBSERVABILITY_TEMPLATE"),
        "minimalObservabilityTemplatePath": minimal_observability_template_path,
        "minimalObservabilityIndexPath": provider_context.get("minimalObservabilityIndexPath", "config/observability-minimal/MINIMAL_OBSERVABILITY_INDEX.json"),
        "precheckProfileId": f"TC_{generated_profile_prefix}",
        "precheckProfilePath": rel(paths["precheck"], repo_root),
        "networkObservabilityProfileId": provider_context.get("networkObservabilityProfileId") or scenario_policy.get("networkObservabilityProfileId") or "NO_MENTAT_C9",
        "networkObservabilityProfilePath": network_observability_profile_path,
        "istioGatewayProfileId": provider_context.get("istioGatewayProfileId") or scenario_policy.get("istioGatewayProfileId") or "IG_LOCALAI_GATEWAY_ROUTED_C9",
        "istioGatewayProfilePath": istio_gateway_profile_path,
        "technicalDiagnosisProfileId": technical_profile_id,
        "technicalDiagnosisProfilePath": technical_profile_path,
        "technicalDiagnosisArtifactRoot": technical_root,
        "reportingProfileId": reporting_profile_id,
        "reportingProfilePath": reporting_profile_path,
        "reportingArtifactRoot": reporting_root,
        "completionGateProfileId": completion_profile_id,
        "completionGateProfilePath": completion_profile_path,
        "completionGateArtifactRoot": completion_root,
        "freezeProfileId": freeze_profile_id,
        "freezeProfilePath": freeze_profile_path,
        "freezeArtifactRoot": freeze_root,
        "cycleExecutionArtifactRoot": f"{variant_root}/execution",
    })
    benchmark_reference = {
        "benchmarkConfigId": f"BENCHMARK_{generated_profile_prefix}",
        "benchmarkConfigPath": rel(paths["benchmark"], repo_root),
        "runtimeBenchmarkConfigPath": rel(paths["benchmark"], repo_root),
        "referenceBaselineId": variant_reference_baseline_id,
        "referenceBaselineConfigPath": variant_reference_baseline_config_path,
        "referenceScenarioId": scenario_id,
        "referenceScenarioConfigPath": variant["scenarioConfigPath"],
        "executedScenarioId": scenario_id,
        "executedScenarioConfigPath": variant["scenarioConfigPath"],
        "campaignReferenceScenarioId": variant_reference_scenario_id,
        "campaignReferenceScenarioConfigPath": variant_reference_scenario_config_path,
        "scenarioId": scenario_id,
        "variantId": variant_id,
        "scenarioConfigPath": variant["scenarioConfigPath"],
        "configRole": "runtime_benchmark_config",
        "roleInCycle": f"{scenario_family}_benchmark_variant",
    }
    runtime_scenario_reference = {
        "runtimeScenarioId": scenario_id,
        "configPath": rel(paths["benchmark"], repo_root),
        "benchmarkConfigPath": rel(paths["benchmark"], repo_root),
        "runtimeBenchmarkConfigPath": rel(paths["benchmark"], repo_root),
        **benchmark_reference,
    }
    if scenario_family == "resource-aware-scheduler":
        variant_cycle.pop("baseline", None)
    else:
        variant_cycle["baseline"] = copy.deepcopy(variant_cycle.get("baseline") or {})
        variant_cycle["baseline"].update({
            "baselineId": scenario_id,
            "configPath": rel(paths["benchmark"], repo_root),
            **benchmark_reference,
        })
    variant_cycle["runtimeScenario"] = copy.deepcopy(runtime_scenario_reference)
    variant_cycle["benchmark"] = copy.deepcopy(variant_cycle.get("benchmark") or {})
    variant_cycle["benchmark"].update(copy.deepcopy(benchmark_reference))
    variant_cycle["benchmarkConfig"] = {
        "configId": benchmark_reference["benchmarkConfigId"],
        "configPath": benchmark_reference["benchmarkConfigPath"],
        "configRole": "runtime_benchmark_config",
        "canonical": True,
    }
    variant_cycle["runtimeBenchmarkConfig"] = {
        "configId": benchmark_reference["benchmarkConfigId"],
        "configPath": benchmark_reference["runtimeBenchmarkConfigPath"],
        "configRole": "runtime_benchmark_config",
        "canonical": True,
    }
    variant_cycle["referenceBaselineConfig"] = {
        "baselineId": variant_reference_baseline_id,
        "configPath": variant_reference_baseline_config_path,
        "configRole": "reference_baseline_config",
    }
    variant_cycle["scenarioConfig"] = {
        "scenarioId": scenario_id,
        "configPath": variant["scenarioConfigPath"],
        "scenarioFamily": scenario_family,
        "configRole": "source_scenario_variant_config",
    }
    variant_cycle["referenceScenario"] = {
        "scenarioFamily": scenario_family,
        "referenceScenarioId": scenario_id,
        "referenceScenarioConfigPath": variant["scenarioConfigPath"],
        "referenceRole": "executed_variant_scenario",
        "campaignReferenceScenarioId": variant_reference_scenario_id,
        "campaignReferenceScenarioConfigPath": variant_reference_scenario_config_path,
    }
    variant_cycle["reporting"] = {
        "reportingProfileId": reporting_profile_id,
        "reportingProfilePath": reporting_profile_path,
        "artifactRoot": reporting_root,
    }
    variant_cycle["completionGate"] = {
        "completionGateProfileId": completion_profile_id,
        "completionGateProfilePath": completion_profile_path,
        "artifactRoot": completion_root,
        "latestManifestPath": f"{completion_root}/latest-completion-gate-manifest.json",
        "latestTextSummaryPath": f"{completion_root}/latest-completion-gate-summary.txt",
    }
    variant_cycle["freeze"] = {
        "freezeProfileId": freeze_profile_id,
        "freezeProfilePath": freeze_profile_path,
        "artifactRoot": freeze_root,
        "artifactSnapshotRoot": f"{variant_root}/artifacts",
    }
    variant_cycle["pipelineProfiles"] = copy.deepcopy(variant_cycle.get("pipelineProfiles") or {})
    variant_cycle["pipelineProfiles"].update({
        "provisioningIntegration": rel(paths["provisioning"], repo_root),
        "provisioningIntegrationTemplate": provisioning_integration_template_path,
        "provisioningIntegrationIndex": provider_context.get("provisioningIntegrationIndexPath", "config/provisioning/PROVISIONING_INTEGRATION_INDEX.json"),
        "provisioningValidation": rel(paths["provisioningValidation"], repo_root),
        "provisioningValidationTemplate": provisioning_validation_template_path,
        "provisioningValidationIndex": provider_context.get("provisioningValidationIndexPath", "config/provisioning-validation/PROVISIONING_VALIDATION_INDEX.json"),
        "clusterValidation": rel(paths["clusterValidation"], repo_root),
        "clusterValidationTemplate": cluster_validation_template_path,
        "clusterValidationIndex": provider_context.get("clusterValidationIndexPath", "config/cluster-validation/CLUSTER_VALIDATION_INDEX.json"),
        "applicationDeployment": rel(paths["applicationDeployment"], repo_root),
        "applicationDeploymentTemplate": application_deployment_template_path,
        "applicationDeploymentIndex": provider_context.get("applicationDeploymentIndexPath", "config/application-deployment/APPLICATION_DEPLOYMENT_INDEX.json"),
        "minimalObservability": rel(paths["minimalObservability"], repo_root),
        "minimalObservabilityTemplate": minimal_observability_template_path,
        "minimalObservabilityIndex": provider_context.get("minimalObservabilityIndexPath", "config/observability-minimal/MINIMAL_OBSERVABILITY_INDEX.json"),
        "precheck": rel(paths["precheck"], repo_root),
        "benchmarkConfig": rel(paths["benchmark"], repo_root),
        "monAgent": mon_agent_profile_path,
        "networkObservability": network_observability_profile_path,
        "istioGateway": istio_gateway_profile_path,
        "customScheduler": custom_scheduler_profile_path,
        "rescheduling": rescheduling_profile_path,
        "clusterLens": cluster_lens_profile_path,
        "schedulerModeValidation": provider_context.get("schedulerModeManifestValidationScript", "scripts/validation/scheduler/validate-scheduler-mode-manifests.py"),
        "latencyInjection": latency_profile_path,
        "technicalDiagnosis": technical_profile_path,
        "reporting": reporting_profile_path,
        "completionGate": completion_profile_path,
        "freeze": freeze_profile_path,
    })
    embedded_scenario = copy.deepcopy(scenario)
    variant_cycle["campaignVariant"] = {"parentCycleId": parent_cycle_id, "variantId": variant_id, "scenarioFamily": scenario_family, "scenario": embedded_scenario}
    if scenario_family == "resource-variation":
        variant_cycle["resourceVariation"] = {"parentCycleId": parent_cycle_id, "variantId": variant_id, "scenario": copy.deepcopy(embedded_scenario)}
    elif scenario_family == "node-count-variation":
        variant_cycle["nodeCountVariation"] = {"parentCycleId": parent_cycle_id, "variantId": variant_id, "scenario": copy.deepcopy(embedded_scenario)}
    elif scenario_family == "placement-variation":
        variant_cycle["placementVariation"] = {"parentCycleId": parent_cycle_id, "variantId": variant_id, "scenario": copy.deepcopy(embedded_scenario)}
    elif scenario_family == "latency-injection":
        variant_cycle["latencyInjection"] = {"parentCycleId": parent_cycle_id, "variantId": variant_id, "scenario": copy.deepcopy(embedded_scenario), "latencyProfileId": latency_profile_id, "latencyProfilePath": latency_profile_path}
    elif scenario_family == "multi-tenancy":
        variant_cycle["multiTenancy"] = {"parentCycleId": parent_cycle_id, "variantId": variant_id, "scenario": copy.deepcopy(embedded_scenario), "tenancyProfileId": scenario.get("tenancyProfileId"), "tenancyProfilePath": scenario.get("tenancyProfilePath")}
    elif scenario_family == "default-scheduler":
        variant_cycle["defaultSchedulerBaseline"] = {
            "parentCycleId": parent_cycle_id,
            "variantId": variant_id,
            "scenario": copy.deepcopy(embedded_scenario),
            "placementDecisionOwner": "kubernetes_default_scheduler",
            "schedulerEvidenceRequired": True,
            "multiTenantBenchmarkRequired": True,
        }
    elif scenario_family in {"resource-aware-scheduler", "network-aware-scheduler"}:
        runtime_annotations = ["cpu-usage", "memory-usage"]
        if scenario_family == "network-aware-scheduler":
            runtime_annotations.extend([
                "network-latency.<node>",
                "packet-loss.<node>",
                "network-bandwidth.<node>",
                "traffic.<peer-workload>",
                "rps.<peer-workload>",
            ])
        policy = copy.deepcopy(scenario.get("networkAwareSchedulerPolicy") or scenario.get("schedulerModePolicy") or {})
        scheduler_runtime_payload = {
            "parentCycleId": parent_cycle_id,
            "variantId": variant_id,
            "scenario": copy.deepcopy(embedded_scenario),
            "policy": policy,
            "schedulerEvidenceRequired": True,
            "multiTenantBenchmarkRequired": True,
            "runtimeAnnotationsRequired": runtime_annotations,
            "monAgentProfilePath": mon_agent_profile_path,
            "networkObservabilityProfilePath": network_observability_profile_path,
            "istioGatewayProfilePath": istio_gateway_profile_path,
            "customSchedulerProfilePath": custom_scheduler_profile_path if variant.get("schedulerName") else None,
            "reschedulingProfilePath": rescheduling_profile_path,
            "artifactRoot": resource_aware_scheduler_root,
            "customSchedulerArtifactRoot": custom_scheduler_root,
            "monAgentArtifactRoot": mon_agent_root,
            "networkObservabilityArtifactRoot": network_observability_root,
            "istioGatewayArtifactRoot": istio_gateway_root,
            "reschedulingArtifactRoot": rescheduling_root,
            "clusterLensProfilePath": cluster_lens_profile_path,
            "clusterLensArtifactRoot": cluster_lens_root,
        }
        variant_cycle["schedulerMode"] = scheduler_runtime_payload
        variant_cycle["schedulerModeRuntime"] = {
            "enabled": True,
            "manifestValidationScript": provider_context.get("schedulerModeManifestValidationScript", "scripts/validation/scheduler/validate-scheduler-mode-manifests.py"),
            "monAgentProfilePath": mon_agent_profile_path,
            "networkObservabilityProfilePath": network_observability_profile_path,
            "istioGatewayProfilePath": istio_gateway_profile_path,
            "customSchedulerProfilePath": custom_scheduler_profile_path,
            "reschedulingProfilePath": rescheduling_profile_path,
            "artifactRoot": resource_aware_scheduler_root,
            "customSchedulerArtifactRoot": custom_scheduler_root,
            "monAgentArtifactRoot": mon_agent_root,
            "networkObservabilityArtifactRoot": network_observability_root,
            "istioGatewayArtifactRoot": istio_gateway_root,
            "reschedulingArtifactRoot": rescheduling_root,
            "clusterLensProfilePath": cluster_lens_profile_path,
            "clusterLensArtifactRoot": cluster_lens_root,
            "annotationValidationRequired": True,
            "reschedulingRequired": True,
        }
        if scenario_family == "network-aware-scheduler":
            variant_cycle["networkAwareScheduler"] = copy.deepcopy(scheduler_runtime_payload)
            variant_cycle["networkAwareSchedulerRuntime"] = copy.deepcopy(variant_cycle["schedulerModeRuntime"])
            variant_cycle["providerBackedInfrastructure"]["networkAwareSchedulerArtifactRoot"] = resource_aware_scheduler_root

    for generated_payload in (pi, pv, cv, ad, mo, benchmark_config):
        mark_generated_runtime_profile(generated_payload)

    for key, payload in [
        ("provisioning", pi),
        ("provisioningValidation", pv),
        ("clusterValidation", cv),
        ("applicationDeployment", ad),
        ("minimalObservability", mo),
        ("precheck", tc),
        ("benchmark", benchmark_config),
        ("cycle", variant_cycle),
    ]:
        write_json(paths[key], payload)
    return paths["cycle"]


def cycle_runner_command(repo_root: Path, variant_cycle_config: Path, args: argparse.Namespace, replicas: str, run_id: str) -> list[str]:
    command = python_cmd() + [
        str(repo_root / "scripts/experimental-cycles/run-provider-backed-cycle.py"),
        "--repo-root", str(repo_root),
        "--cycle-config", str(variant_cycle_config),
        "--tool-path", args.tool_path,
        "--baseline-replicas", replicas,
        "--run-id", run_id,
        "--skip-diagnosis",
        "--skip-reporting",
        "--skip-completion-gate",
        "--skip-freeze",
    ]
    if args.base_url:
        command.extend(["--base-url", args.base_url])
    if args.dry_run:
        command.append("--dry-run")
    if args.continue_on_failure:
        command.append("--continue-on-failure")
    if args.allow_metrics_warning:
        command.append("--allow-metrics-warning")
    if args.confirm_delete:
        command.append("--confirm-delete")
    if args.write_latest_aliases:
        command.append("--write-latest-aliases")
    for flag, enabled in [
        ("--skip-provisioning", args.skip_provisioning),
        ("--skip-cluster-validation", args.skip_cluster_validation),
        ("--skip-placement-profile", args.skip_placement_profile),
        ("--skip-localai-deployment", args.skip_localai_deployment),
        ("--skip-smoke-test", args.skip_smoke_test),
        ("--skip-minimal-observability", args.skip_minimal_observability),
        ("--skip-latency-injection", args.skip_latency_injection),
        ("--skip-benchmark", args.skip_benchmark),
        ("--skip-default-scheduler-validation", getattr(args, "skip_default_scheduler_validation", False)),
        ("--skip-scheduler-capture", getattr(args, "skip_scheduler_capture", False)),
        ("--skip-scheduler-mode-validation", getattr(args, "skip_scheduler_mode_validation", False)),
        ("--skip-custom-scheduler", getattr(args, "skip_custom_scheduler", False)),
        ("--skip-mon-agent", getattr(args, "skip_mon_agent", False)),
        ("--skip-telemetry-priming", getattr(args, "skip_telemetry_priming", False)),
        ("--skip-rescheduling", getattr(args, "skip_rescheduling", False)),
        ("--skip-cluster-lens-capture", getattr(args, "skip_cluster_lens_capture", False)),
    ]:
        if enabled:
            command.append(flag)
    return command


def destroy_command(repo_root: Path, variant_cycle_config: Path, args: argparse.Namespace, run_id: str) -> list[str]:
    command = python_cmd() + [
        str(repo_root / "scripts/infrastructure/provision/run-provider-backed-provisioning.py"),
        "--repo-root", str(repo_root),
        "--cycle-config", str(variant_cycle_config),
        "--action", "destroy",
        "--tool-path", args.tool_path,
        "--run-id", run_id,
        "--write-latest-aliases",
    ]
    if args.confirm_delete:
        command.append("--confirm-delete")
    if args.dry_run:
        command.append("--dry-run")
    return command


def build_manifest(repo_root: Path, cycle_config: Path, cycle: dict[str, Any], run_id: str, execution_root: Path, steps: list[dict[str, Any]], variant_results: list[dict[str, Any]], status: str, dry_run: bool) -> dict[str, Any]:
    return {
        "schemaVersion": "experimental-campaign-execution/v1",
        "cycleId": cycle.get("cycleId"),
        "cycleName": cycle.get("cycleName"),
        "cycleKind": cycle.get("cycleKind"),
        "campaignType": cycle.get("campaignType"),
        "runId": run_id,
        "status": "dry_run" if dry_run else status,
        "dryRun": dry_run,
        "createdAt": utc_now(),
        "cycleConfig": rel(cycle_config, repo_root),
        "executionRoot": rel(execution_root, repo_root),
        "variantResults": variant_results,
        "steps": steps,
    }


def write_execution_summary(summary_path: Path, cycle: dict[str, Any], run_id: str, status: str, dry_run: bool, steps: list[dict[str, Any]], variant_results: list[dict[str, Any]]) -> None:
    lines = [
        "Experimental campaign execution summary",
        "======================================",
        f"Cycle: {cycle.get('cycleId')} - {cycle.get('cycleName')}",
        f"Campaign type: {cycle.get('campaignType')}",
        f"Run: {run_id}",
        f"Status: {status}",
        f"Dry run: {dry_run}",
        "",
        "Variants:",
    ]
    for item in variant_results:
        lines.append(f"- {item['variantId']}: {item['status']} (exitCode={item['exitCode']})")
    lines.extend(["", "Steps:"])
    for step in steps:
        lines.append(f"- {step.get('name')}: {step.get('status')} (exitCode={step.get('exitCode')})")
        if step.get("command"):
            lines.append(f"  command: {as_text(step['command'])}")
        if step.get("error"):
            lines.append(f"  error: {step.get('error')}")
    write_text(summary_path, "\n".join(lines) + "\n")


def run_or_skip(*, name: str, description: str, command: list[str], skip: bool, repo_root: Path, dry_run: bool, continue_on_failure: bool, artifacts: dict[str, Any] | None = None) -> CommandResult:
    if skip:
        return skipped_step(name, description, artifacts)
    return run_command(
        name=name,
        description=description,
        command=command,
        repo_root=repo_root,
        dry_run=dry_run,
        continue_on_failure=continue_on_failure,
        artifacts=artifacts,
    )


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    cycle_config = repo_path(repo_root, args.cycle_config)
    cycle = load_json(cycle_config)
    campaign = cycle.get("campaign") or {}
    if cycle.get("cycleKind") != "comparative_campaign":
        raise SystemExit("The selected cycle profile is not a comparative campaign.")

    run_id = args.run_id.strip() or f"{cycle.get('cycleId', 'campaign')}_{safe_stamp()}"
    execution_root = repo_path(repo_root, (cycle.get("providerBackedInfrastructure") or {}).get("cycleExecutionArtifactRoot"), "results/experimental-cycles/C2/execution")
    generated_root = repo_path(repo_root, campaign.get("generatedRuntimeConfigRoot"), str(execution_root / "generated-runtime-configs"))
    execution_root.mkdir(parents=True, exist_ok=True)
    generated_root.mkdir(parents=True, exist_ok=True)
    replicas = args.baseline_replicas.strip() or ",".join(campaign.get("defaultBaselineReplicas") or ["A", "B", "C"])

    steps: list[dict[str, Any]] = []
    variant_results: list[dict[str, Any]] = []
    failed = False

    def append(result: CommandResult) -> bool:
        nonlocal failed
        steps.append(result.__dict__)
        if result.status == "failed":
            failed = True
            return False
        return True

    try:
        resolved_variants = campaign_variants(repo_root, cycle)
        if not resolved_variants:
            raise ValueError("No executable campaign variants were resolved from the selected cycle profile.")
        for variant in resolved_variants:
            variant_id = variant["variantId"]
            variant_cycle_config = build_variant_runtime_configs(repo_root, cycle, variant, generated_root)
            variant_run_id = f"{run_id}_{variant_id}"

            if variant.get("destroyClusterAfterVariant", False):
                preclean_cmd = destroy_command(repo_root, variant_cycle_config, args, f"{variant_run_id}_precleanup")
                preclean_result = run_or_skip(
                    name=f"preclean_variant_cluster_{variant_id}",
                    description="Delete any stale provider-backed cluster before creating the variant.",
                    command=preclean_cmd,
                    skip=args.skip_delete,
                    repo_root=repo_root,
                    dry_run=args.dry_run,
                    continue_on_failure=args.continue_on_failure,
                    artifacts={"variantCycleConfig": rel(variant_cycle_config, repo_root)},
                )
                preclean_success = append(preclean_result)
                if not preclean_success:
                    variant_results.append({
                        "variantId": variant_id,
                        "status": "failed_precleanup",
                        "commandStatus": preclean_result.status,
                        "exitCode": preclean_result.exitCode,
                        "variantCycleConfig": rel(variant_cycle_config, repo_root),
                        "variantExecutionManifest": None,
                        "unsupportedScenario": None,
                    })
                    if not args.continue_on_failure:
                        break
                    continue

            command = cycle_runner_command(repo_root, variant_cycle_config, args, replicas, variant_run_id)
            result = run_command(
                name=f"execute_variant_{variant_id}",
                description="Execute one provider-backed campaign variant.",
                command=command,
                repo_root=repo_root,
                dry_run=args.dry_run,
                continue_on_failure=args.continue_on_failure,
                artifacts={
                    "variantCycleConfig": rel(variant_cycle_config, repo_root),
                    "benchmarkRoot": variant.get("resultsRoot"),
                    "outputSubdir": variant.get("outputSubdir"),
                },
            )
            success = append(result)
            variant_execution_manifest = load_variant_execution_manifest(repo_root, variant_cycle_config) if not args.dry_run else {}
            if variant_execution_manifest.get("status") == "completed_with_unsupported_scenario":
                failed = any(step.get("status") == "failed" and step.get("name") != f"execute_variant_{variant_id}" for step in steps)
            variant_results.append({
                "variantId": variant_id,
                "status": variant_execution_manifest.get("status") or result.status,
                "commandStatus": result.status,
                "exitCode": result.exitCode,
                "variantCycleConfig": rel(variant_cycle_config, repo_root),
                "variantExecutionManifest": rel(repo_path(repo_root, (variant_execution_manifest.get("executionRoot") or "")) / "latest-cycle-execution-manifest.json", repo_root) if variant_execution_manifest.get("executionRoot") else None,
                "unsupportedScenario": variant_execution_manifest.get("unsupportedScenario"),
            })
            if not success and not args.continue_on_failure:
                break

            if variant.get("destroyClusterAfterVariant", False):
                delete_cmd = destroy_command(repo_root, variant_cycle_config, args, f"{variant_run_id}_delete")
                delete_result = run_or_skip(
                    name=f"delete_variant_cluster_{variant_id}",
                    description="Delete the provider-backed variant cluster after the benchmark run.",
                    command=delete_cmd,
                    skip=args.skip_delete,
                    repo_root=repo_root,
                    dry_run=args.dry_run,
                    continue_on_failure=args.continue_on_failure,
                    artifacts={"variantCycleConfig": rel(variant_cycle_config, repo_root)},
                )
                success = append(delete_result)
                if not success and not args.continue_on_failure:
                    break

        if not failed or args.continue_on_failure:
            cycle_id = str(cycle.get("cycleId") or "campaign")
            diagnosis_root = repo_path(
                repo_root,
                cycle_artifact_root(cycle, "diagnosis", "artifactRoot", "technicalDiagnosisArtifactRoot", "diagnosis"),
                f"results/experimental-cycles/{cycle_id}/diagnosis",
            )
            diagnosis_json = diagnosis_root / f"{run_id}_diagnosis_all_diagnosis.json"
            diagnosis_text = diagnosis_root / f"{run_id}_diagnosis_all_summary.txt"
            diagnosis_profile = repo_path(
                repo_root,
                cycle_profile_path(
                    cycle,
                    "diagnosis",
                    "technicalDiagnosisProfilePath",
                    "technicalDiagnosisProfilePath",
                    "technicalDiagnosis",
                    f"config/technical-diagnosis/profiles/TD_{cycle_id}.json",
                ),
                f"config/technical-diagnosis/profiles/TD_{cycle_id}.json",
            )
            diag_cmd = python_cmd() + [
                str(repo_root / "scripts/analysis/generate-technical-diagnosis.py"),
                "--repo-root", str(repo_root),
                "--profile-config", str(diagnosis_profile),
                "--family", "all",
                "--output-json", str(diagnosis_json),
                "--output-text", str(diagnosis_text),
                "--diagnosis-id", f"{run_id}_diagnosis_all",
            ]
            append(run_or_skip(
                name="generate_campaign_diagnosis",
                description="Generate campaign-level technical diagnosis.",
                command=diag_cmd,
                skip=args.skip_diagnosis,
                repo_root=repo_root,
                dry_run=args.dry_run,
                continue_on_failure=args.continue_on_failure,
                artifacts={"diagnosisJson": rel(diagnosis_json, repo_root), "diagnosisText": rel(diagnosis_text, repo_root)},
            ))

            reporting_root = repo_path(
                repo_root,
                cycle_artifact_root(cycle, "reporting", "artifactRoot", "reportingArtifactRoot", "reporting"),
                f"results/experimental-cycles/{cycle_id}/reporting",
            )
            reporting_profile = repo_path(
                repo_root,
                cycle_profile_path(
                    cycle,
                    "reporting",
                    "reportingProfilePath",
                    "reportingProfilePath",
                    "reporting",
                    f"config/reporting/profiles/RP_{cycle_id}.json",
                ),
                f"config/reporting/profiles/RP_{cycle_id}.json",
            )
            report_cmd = python_cmd() + [
                str(repo_root / "scripts/analysis/generate-reporting.py"),
                "--repo-root", str(repo_root),
                "--profile-config", str(reporting_profile),
                "--output-root", str(reporting_root),
                "--reporting-id", f"{run_id}_reporting",
            ]
            append(run_or_skip(
                name="generate_campaign_reporting",
                description="Generate campaign-level reporting artifacts.",
                command=report_cmd,
                skip=args.skip_reporting,
                repo_root=repo_root,
                dry_run=args.dry_run,
                continue_on_failure=args.continue_on_failure,
                artifacts={"reportingRoot": rel(reporting_root, repo_root)},
            ))

            reporting_site_root = repo_root / "results" / "reporting"
            reporting_site_cmd = python_cmd() + [
                str(repo_root / "scripts/analysis/generate-reporting-site.py"),
                "--repo-root", str(repo_root),
                "--site-config", str(repo_root / "config" / "reporting" / "site" / "REPORTING_SITE.json"),
                "--output-root", str(reporting_site_root),
                "--site-id", f"{run_id}_reporting_site",
            ]
            append(run_or_skip(
                name="generate_reporting_site",
                description="Generate the static reporting-site entry point.",
                command=reporting_site_cmd,
                skip=args.skip_reporting,
                repo_root=repo_root,
                dry_run=args.dry_run,
                continue_on_failure=args.continue_on_failure,
                artifacts={"reportingSiteRoot": rel(reporting_site_root, repo_root)},
            ))

            completion_root = repo_path(
                repo_root,
                cycle_artifact_root(cycle, "completionGate", "artifactRoot", "completionGateArtifactRoot", "completion-gate"),
                f"results/experimental-cycles/{cycle_id}/completion-gate",
            )
            completion_profile = repo_path(
                repo_root,
                cycle_profile_path(
                    cycle,
                    "completionGate",
                    "completionGateProfilePath",
                    "completionGateProfilePath",
                    "completionGate",
                    f"config/completion-gate/profiles/CG_{cycle_id}.json",
                ),
                f"config/completion-gate/profiles/CG_{cycle_id}.json",
            )
            completion_json = completion_root / "latest-completion-gate-manifest.json"
            completion_text = completion_root / "latest-completion-gate-summary.txt"
            gate_cmd = python_cmd() + [
                str(repo_root / "scripts/analysis/evaluate-completion-gate.py"),
                "--repo-root", str(repo_root),
                "--profile-config", str(completion_profile),
                "--cycle-config", str(cycle_config),
                "--diagnosis-json", str(diagnosis_json),
                "--output-json", str(completion_json),
                "--output-text", str(completion_text),
                "--evaluation-id", f"{run_id}_completion_gate",
            ]
            if args.dry_run:
                gate_cmd.append("--dry-run")
            append(run_or_skip(
                name="evaluate_campaign_completion_gate",
                description="Evaluate campaign-level completion criteria.",
                command=gate_cmd,
                skip=args.skip_completion_gate,
                repo_root=repo_root,
                dry_run=args.dry_run,
                continue_on_failure=args.continue_on_failure,
                artifacts={"completionGateManifest": rel(completion_json, repo_root), "completionGateSummary": rel(completion_text, repo_root)},
            ))

            freeze_root = repo_path(
                repo_root,
                cycle_artifact_root(cycle, "freeze", "artifactRoot", "freezeArtifactRoot", "freeze"),
                f"results/experimental-cycles/{cycle_id}/freeze",
            )
            freeze_profile = repo_path(
                repo_root,
                cycle_profile_path(
                    cycle,
                    "freeze",
                    "freezeProfilePath",
                    "freezeProfilePath",
                    "freeze",
                    f"config/freeze/profiles/FR_{cycle_id}.json",
                ),
                f"config/freeze/profiles/FR_{cycle_id}.json",
            )
            freeze_cmd = python_cmd() + [
                str(repo_root / "scripts/analysis/freeze-experimental-cycle.py"),
                "--repo-root", str(repo_root),
                "--cycle-config", str(cycle_config),
                "--profile-config", str(freeze_profile),
                "--freeze-id", f"{run_id}_freeze",
                "--output-root", str(freeze_root),
            ]
            if args.force_freeze:
                freeze_cmd.append("--force")
            if args.write_latest_aliases:
                freeze_cmd.append("--write-latest-aliases")
            if args.dry_run:
                freeze_cmd.extend(["--dry-run", "--skip-completion-gate"])
            append(run_or_skip(
                name="freeze_campaign",
                description="Freeze campaign-level artifacts.",
                command=freeze_cmd,
                skip=args.skip_freeze,
                repo_root=repo_root,
                dry_run=args.dry_run,
                continue_on_failure=args.continue_on_failure,
                artifacts={"freezeRoot": rel(freeze_root, repo_root)},
            ))
    except Exception as exc:
        failed = True
        steps.append(CommandResult(name="campaign_execution", description="Unhandled campaign execution error.", status="failed", startedAt=utc_now(), completedAt=utc_now(), exitCode=1, error=str(exc)).__dict__)

    if args.dry_run:
        final_status = "dry_run"
    elif failed:
        final_status = "failed"
    elif any(str(item.get("status")) == "completed_with_unsupported_scenario" or item.get("unsupportedScenario") for item in variant_results):
        final_status = "completed_with_unsupported_scenarios"
    elif any(step.get("status") == "skipped" for step in steps):
        final_status = "completed_with_skipped_steps"
    else:
        final_status = "completed"

    manifest = build_manifest(repo_root, cycle_config, cycle, run_id, execution_root, steps, variant_results, final_status, args.dry_run)
    manifest_path = execution_root / f"{run_id}_campaign_execution_manifest.json"
    summary_path = execution_root / f"{run_id}_campaign_execution_summary.txt"
    write_json(manifest_path, manifest)
    write_execution_summary(summary_path, cycle, run_id, final_status, args.dry_run, steps, variant_results)
    if args.write_latest_aliases:
        write_json(execution_root / "latest-campaign-execution-manifest.json", manifest)
        write_text(execution_root / "latest-campaign-execution-summary.txt", summary_path.read_text(encoding="utf-8"))

    return 0 if final_status in {"completed", "dry_run", "completed_with_skipped_steps", "completed_with_unsupported_scenarios"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
