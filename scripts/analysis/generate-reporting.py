#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable


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

def _load_network_aware_telemetry_evidence_helpers():
    import importlib.util

    candidate = Path(__file__).resolve().with_name("network-aware-telemetry-evidence.py")
    if not candidate.is_file():
        raise RuntimeError(f"Unable to locate {candidate}")
    spec = importlib.util.spec_from_file_location("networkAwareTelemetryEvidence", candidate)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return (
        module.collect_network_aware_telemetry_for_scenario,
        module.collect_network_aware_telemetry_index,
    )


collect_network_aware_telemetry_for_scenario, collect_network_aware_telemetry_index = _load_network_aware_telemetry_evidence_helpers()



METRIC_KEYS = [
    "request_count",
    "failure_count",
    "mean_response_time_ms",
    "p50_response_time_ms",
    "p95_response_time_ms",
    "p99_response_time_ms",
    "throughput_rps",
]

CSV_FIELD_MAP = {
    "request_count": "Request Count",
    "failure_count": "Failure Count",
    "mean_response_time_ms": "Average Response Time",
    "p50_response_time_ms": "50%",
    "p95_response_time_ms": "95%",
    "p99_response_time_ms": "99%",
    "throughput_rps": "Requests/s",
}

RESOURCE_METRIC_MAP = {
    "max_node_cpu_percent": ("clusterSideSnapshots", "maxNodeCpuPercent"),
    "max_node_memory_percent": ("clusterSideSnapshots", "maxNodeMemoryPercent"),
    "max_pod_cpu_millicores": ("clusterSideSnapshots", "maxPodCpuMillicores"),
    "max_pod_memory_mib": ("clusterSideSnapshots", "maxPodMemoryMiB"),
    "pod_restart_count": ("clusterSideSnapshots", "podRestartCount"),
    "pending_pods_count": ("clusterSideSnapshots", "pendingPodsCount"),
    "failed_pods_count": ("clusterSideSnapshots", "failedPodsCount"),
    "not_ready_pods_count": ("clusterSideSnapshots", "notReadyPodsCount"),
    "kubernetes_events_count": ("clusterSideSnapshots", "kubernetesEventsCount"),
    "kubernetes_warning_events_count": ("clusterSideSnapshots", "kubernetesWarningEventsCount"),
}

METRIC_DISPLAY = {
    "request_count": "Request count",
    "failure_count": "Failure count",
    "mean_response_time_ms": "Mean response time (ms)",
    "p50_response_time_ms": "P50 response time (ms)",
    "p95_response_time_ms": "P95 response time (ms)",
    "p99_response_time_ms": "P99 response time (ms)",
    "throughput_rps": "Throughput (requests/s)",
    "max_node_cpu_percent": "Max node CPU snapshot (%)",
    "max_node_memory_percent": "Max node memory snapshot (%)",
    "max_pod_cpu_millicores": "Max pod CPU snapshot (mCPU)",
    "max_pod_memory_mib": "Max pod memory snapshot (MiB)",
    "pod_restart_count": "Pod restart count",
    "pending_pods_count": "Pending pod count",
    "failed_pods_count": "Failed pod count",
    "not_ready_pods_count": "Not-ready pod count",
    "kubernetes_events_count": "Kubernetes event count",
    "kubernetes_warning_events_count": "Kubernetes warning event count",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate reporting artifacts and SVG visualizations from consolidated pilot benchmark outputs.")
    parser.add_argument("--repo-root", required=True, help="Repository root path.")
    parser.add_argument("--profile-config", required=True, help="Reporting profile JSON path.")
    parser.add_argument("--output-root", required=True, help="Reporting output root path.")
    parser.add_argument("--reporting-id", default="", help="Unique reporting run identifier. If omitted during normal generation, a UTC timestamped identifier is generated automatically. Ignored by --archive-current, which uses the identifier stored in the current reporting manifest.")
    parser.add_argument("--archive", action="store_true", help="Also preserve a timestamped copy of the newly generated current report under the reporting archive directory.")
    parser.add_argument("--archive-current", action="store_true", help="Archive the already generated current report without regenerating it.")
    parser.add_argument("--force-archive", action="store_true", help="Overwrite an existing archive directory with the same reporting identifier.")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def resolve_artifact_path(repo_root: Path, value: Any) -> Path | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None

    normalized = text.replace("\\", "/")
    marker = "/localai-worker-mode-benchmark-suite/"
    if marker in normalized:
        suffix = normalized.split(marker, 1)[1]
        return repo_root / suffix
    if normalized.startswith("localai-worker-mode-benchmark-suite/"):
        return repo_root / normalized.split("/", 1)[1]

    if re.match(r"^[A-Za-z]:/", normalized):
        path_parts = normalized.split("/")
        if "localai-worker-mode-benchmark-suite" in path_parts:
            idx = path_parts.index("localai-worker-mode-benchmark-suite")
            return repo_root / "/".join(path_parts[idx + 1:])
        return Path(normalized)

    candidate = Path(text)
    if candidate.is_absolute():
        return candidate
    repo_candidate = repo_root / candidate
    if repo_candidate.exists():
        return repo_candidate
    try:
        if candidate.exists():
            return candidate
    except OSError:
        pass
    return repo_candidate


def read_json_optional(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        return load_json(path)
    except Exception:
        return None


def text_tokens_from_any(value: Any) -> list[str]:
    tokens: list[str] = []
    if value is None:
        return tokens
    if isinstance(value, str):
        if value.strip():
            tokens.append(value.strip())
    elif isinstance(value, dict):
        for item in value.values():
            tokens.extend(text_tokens_from_any(item))
    elif isinstance(value, list):
        for item in value:
            tokens.extend(text_tokens_from_any(item))
    else:
        tokens.append(str(value))
    return tokens


def is_compact_evidence_token(token: str) -> bool:
    stripped = str(token).strip()
    if not stripped or len(stripped) > 80:
        return False
    if " " in stripped or ":" in stripped or "/" in stripped or "\\" in stripped:
        return False
    if stripped.lower() in {"true", "false", "none", "null"}:
        return False
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", stripped):
        return False
    if stripped != stripped.lower():
        return False
    if "_" not in stripped:
        return False
    return bool(re.search(r"[A-Za-z]", stripped))


def classify_evidence_text(text: Any) -> set[str]:
    evidence_kinds: set[str] = set()
    lower = str(text).lower()
    if not lower:
        return evidence_kinds
    if "failedscheduling" in lower or "failed scheduling" in lower:
        evidence_kinds.add("failed_scheduling")
    if "insufficient cpu" in lower:
        evidence_kinds.add("insufficient_cpu")
    if "insufficient memory" in lower:
        evidence_kinds.add("insufficient_memory")
    if "node affinity/selector" in lower or "node(s) didn't match pod's node affinity" in lower or "node(s) did not match pod's node affinity" in lower:
        evidence_kinds.add("node_affinity_selector_mismatch")
    if "preemption is not helpful" in lower:
        evidence_kinds.add("preemption_not_helpful")
    if "no preemption victims" in lower:
        evidence_kinds.add("no_preemption_victims_found")
    if "rollout check failed" in lower or "timed out waiting for the condition" in lower:
        evidence_kinds.add("rollout_timeout")
    if "pending" in lower:
        evidence_kinds.add("pending_pod")
    if "smoke validation failed" in lower:
        evidence_kinds.add("smoke_validation_failure")
    if "api smoke" in lower or "api_smoke" in lower:
        evidence_kinds.add("api_smoke_failed")
    if "timeout" in lower or "timed out" in lower or "request canceled" in lower:
        evidence_kinds.add("timeout")
    if "latency" in lower or "netem" in lower or "tc" in lower:
        evidence_kinds.add("latency_injection")
    if "pre_benchmark" in lower or "before benchmark" in lower:
        evidence_kinds.add("pre_benchmark_failure")
    if "localai_deployment_not_ready" in lower:
        evidence_kinds.add("application_not_ready")
    return evidence_kinds


def read_related_deployment_manifest(repo_root: Path, unsupported_payload: dict[str, Any]) -> tuple[Path | None, dict[str, Any] | None]:
    evidence = unsupported_payload.get("evidence")
    manifest_path_value = evidence.get("deploymentManifestPath") if isinstance(evidence, dict) else None
    manifest_path = resolve_artifact_path(repo_root, manifest_path_value)
    return manifest_path, read_json_optional(manifest_path)


def deployment_manifest_event_texts(repo_root: Path, manifest: dict[str, Any] | None) -> list[str]:
    if not isinstance(manifest, dict):
        return []
    texts: list[str] = []
    texts.extend(text_tokens_from_any(manifest.get("errors")))
    for rollout in manifest.get("rolloutChecks") or []:
        if rollout.get("success") is False:
            texts.append(f"Rollout check failed for deployment/{rollout.get('deployment')}")
    snapshots = manifest.get("snapshots") or {}
    candidate_paths: list[Path | None] = []
    for key in ("events", "events_json", "describe_pods", "describe_deployments", "pods", "pods_json"):
        item = snapshots.get(key)
        if isinstance(item, dict) and item.get("path"):
            candidate_paths.append(resolve_artifact_path(repo_root, item.get("path")))
    manifest_path = resolve_artifact_path(repo_root, (manifest.get("artifacts") or {}).get("manifestPath"))
    if manifest_path is not None:
        snapshots_dir = manifest_path.parent.parent / "snapshots"
        if snapshots_dir.exists():
            candidate_paths.extend(snapshots_dir.glob("*events*.txt"))
            candidate_paths.extend(snapshots_dir.glob("*describe_pods*.txt"))
    seen: set[str] = set()
    for path in candidate_paths:
        if path is None:
            continue
        try:
            resolved = str(path.resolve())
        except Exception:
            resolved = str(path)
        if resolved in seen or not path.exists() or not path.is_file():
            continue
        seen.add(resolved)
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line in content.splitlines():
            lower = line.lower()
            if any(token in lower for token in ["failedscheduling", "insufficient", "affinity/selector", "preemption", "rollout", "pending"]):
                texts.append(line.strip())
    return texts


def resolve_repo_path(repo_root: Path, path_value: Any) -> Path | None:
    if not path_value:
        return None
    path = Path(str(path_value))
    if path.is_absolute():
        return path
    return repo_root / path


def load_optional_json(repo_root: Path, path_value: Any) -> dict[str, Any]:
    path = resolve_repo_path(repo_root, path_value)
    if path is None:
        return {"path": None, "exists": False, "payload": None, "error": None}
    try:
        if not path.exists():
            return {"path": safe_rel(path, repo_root), "exists": False, "payload": None, "error": None}
        return {"path": safe_rel(path, repo_root), "exists": True, "payload": load_json(path), "error": None}
    except Exception as exc:
        return {"path": safe_rel(path, repo_root), "exists": True, "payload": None, "error": str(exc)}


def nested_get(payload: Any, *keys: str, default: Any = None) -> Any:
    current = payload
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def utc_timestamp_compact(dt: datetime | None = None) -> str:
    current = dt or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_timestamp_iso(dt: datetime | None = None) -> str:
    current = dt or datetime.now(timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reporting_cycle_id(profile: dict[str, Any]) -> str:
    return str(first_non_empty(profile.get("cycleId"), "GEN"))


def reporting_profile_id(profile: dict[str, Any]) -> str:
    return str(first_non_empty(profile.get("reportingProfileId"), profile.get("profileId"), "NA"))


def reporting_id_prefix(profile: dict[str, Any]) -> str:
    explicit = profile.get("reportingIdPrefix")
    if explicit:
        return str(explicit)
    cycle = reporting_cycle_id(profile)
    return f"REP_{cycle}" if cycle and cycle != "GEN" else "REP_GENERAL"


def default_reporting_id(profile: dict[str, Any], dt: datetime | None = None) -> str:
    return f"{reporting_id_prefix(profile)}_{utc_timestamp_compact(dt)}"


def family_display_name(profile: dict[str, Any], family: str) -> str:
    return str((profile.get("familyDisplayNames") or {}).get(family, family)).strip()


def global_report_title(profile: dict[str, Any]) -> str:
    title = str(first_non_empty(profile.get("reportTitle"), "Consolidated Reporting and Visualization")).strip()
    cycle = reporting_cycle_id(profile)
    if cycle == "GEN":
        return title
    if title == cycle:
        return title
    for separator in (" — ", " - "):
        if title.startswith(f"{cycle}{separator}"):
            return title
    if title.startswith(f"{cycle} "):
        remainder = title[len(cycle):].strip()
        return f"{cycle} — {remainder}" if remainder else cycle
    return f"{cycle} — {title}"


def family_report_title(profile: dict[str, Any], family: str) -> str:
    cycle = reporting_cycle_id(profile)
    display_name = family_display_name(profile, family)
    suffix = "Detail Report" if family == "baseline" and len(profile.get("familyOrder", [])) == 1 else "Sweep Report"
    return f"{cycle} — {display_name} {suffix}" if cycle != "GEN" else f"{display_name} {suffix}"


def is_historical_fixed_cluster_profile(profile: dict[str, Any], context: dict[str, Any] | None = None) -> bool:
    role_values = [
        profile.get("profileRole"),
        profile.get("reportingMode"),
        ((profile.get("profileGovernance") or {}).get("scope") if isinstance(profile.get("profileGovernance"), dict) else None),
    ]
    if any(str(value).lower() in {"historical_fixed_cluster_reporting", "historical_fixed_cluster"} for value in role_values if value):
        return True
    if reporting_cycle_id(profile) == "C0":
        documents = (context or {}).get("documents") or {}
        cycle_payload = (documents.get("cycle") or {}).get("payload") or {}
        return not bool(cycle_payload.get("providerBackedInfrastructure"))
    return False


def compact_list(values: Any, limit: int = 8) -> str:
    if not values:
        return "NA"
    if isinstance(values, dict):
        values = [f"{k}={v}" for k, v in values.items()]
    elif not isinstance(values, list):
        if isinstance(values, (tuple, set, frozenset)) or values.__class__.__name__ in {"dict_keys", "dict_values", "dict_items"}:
            values = list(values)
        else:
            return str(values)
    rendered = [str(v) for v in values]
    if len(rendered) > limit:
        return ", ".join(rendered[:limit]) + f", ... (+{len(rendered) - limit})"
    return ", ".join(rendered)


def semantic_value(value: Any, missing: str = "not_declared") -> Any:
    if value is None:
        return missing
    if isinstance(value, str):
        text = value.strip()
        if text.upper() in {"", "NA", "N/A", "NONE", "NULL"}:
            return missing
        return text
    return value


def context_value(value: Any, missing: str = "not_declared") -> Any:
    if value is None:
        return missing
    if isinstance(value, str):
        text = value.strip()
        if text.upper() in {"", "NA", "N/A", "NULL"}:
            return missing
        return text
    return value


def yes_no(value: Any, missing: str = "not_declared") -> str:
    if value is None or value == "":
        return missing
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def semantic_compact_list(values: Any, empty: str = "not_declared", limit: int = 8) -> str:
    if not values:
        return empty
    if isinstance(values, dict):
        if not values:
            return empty
        values = [f"{k}={v}" for k, v in values.items()]
    if isinstance(values, list) and not values:
        return empty
    rendered = compact_list(values, limit=limit)
    return semantic_value(rendered, empty)


def artifact_state(document: dict[str, Any]) -> str:
    if not document.get("path"):
        return "not declared"
    if document.get("exists"):
        if document.get("payload") is None and document.get("error"):
            return f"unreadable ({document.get('error')})"
        return "available"
    return "not available"


def extract_manifest_status(document: dict[str, Any]) -> str:
    payload = document.get("payload")
    if not isinstance(payload, dict):
        return artifact_state(document)
    return str(first_non_empty(
        payload.get("status"),
        nested_get(payload, "validation", "status"),
        nested_get(payload, "provisioning", "status"),
        nested_get(payload, "deployment", "status"),
        nested_get(payload, "smokeValidation", "status"),
        nested_get(payload, "decision", "reason"),
        "available"
    ))


def profile_id(payload: dict[str, Any] | None, *keys: str) -> str:
    if not isinstance(payload, dict):
        return "NA"
    for key in keys:
        if payload.get(key):
            return str(payload[key])
    return "NA"


def has_semantic_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().upper() not in {"", "NA", "N/A", "NONE", "NULL", "NOT AVAILABLE", "NOT DECLARED"}
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def append_semantic_row(rows: list[list[Any]], label: str, value: Any) -> None:
    if has_semantic_value(value):
        rows.append([label, value])


def document_state_phrase(document: dict[str, Any]) -> str:
    if not document.get("path"):
        return "pending generation"
    if document.get("exists"):
        if document.get("payload") is None and document.get("error"):
            return f"unreadable ({document.get('error')})"
        return "available"
    return "pending generation"


def build_reporting_context(repo_root: Path, profile: dict[str, Any]) -> dict[str, Any]:
    provider_context = profile.get("providerAwareContext") or {}
    cycle_doc = load_optional_json(repo_root, provider_context.get("cycleConfigPath") or profile.get("cycleConfigPath"))
    cycle = cycle_doc.get("payload") if isinstance(cycle_doc.get("payload"), dict) else {}
    provider_backed = cycle.get("providerBackedInfrastructure") if isinstance(cycle, dict) else {}
    pipeline_profiles = cycle.get("pipelineProfiles") if isinstance(cycle, dict) else {}

    def ctx_path(context_key: str, provider_key: str | None = None, pipeline_key: str | None = None) -> Any:
        return first_non_empty(
            provider_context.get(context_key),
            provider_backed.get(provider_key or context_key) if isinstance(provider_backed, dict) else None,
            pipeline_profiles.get(pipeline_key or context_key) if isinstance(pipeline_profiles, dict) else None,
        )

    infrastructure_profile_path = first_non_empty(
        provider_context.get("infrastructureProfilePath"),
        provider_context.get("fixedInfrastructureProfilePath"),
        provider_backed.get("infrastructureProfilePath") if isinstance(provider_backed, dict) else None,
        provider_backed.get("fixedInfrastructureProfilePath") if isinstance(provider_backed, dict) else None,
        pipeline_profiles.get("infrastructureProfilePath") if isinstance(pipeline_profiles, dict) else None,
        pipeline_profiles.get("fixedInfrastructureProfilePath") if isinstance(pipeline_profiles, dict) else None,
    )

    documents = {
        "cycle": cycle_doc,
        "infrastructureProfile": load_optional_json(repo_root, infrastructure_profile_path),
        "providerBinding": load_optional_json(repo_root, ctx_path("providerBindingPath")),
        "provisioningIntegrationProfile": load_optional_json(repo_root, ctx_path("provisioningIntegrationProfilePath", pipeline_key="provisioningIntegration")),
        "clusterValidationProfile": load_optional_json(repo_root, ctx_path("clusterValidationProfilePath", pipeline_key="clusterValidation")),
        "applicationDeploymentProfile": load_optional_json(repo_root, ctx_path("applicationDeploymentProfilePath", pipeline_key="applicationDeployment")),
        "placementProfile": load_optional_json(repo_root, ctx_path("placementProfilePath", pipeline_key="baselinePlacementProfile")),
        "minimalObservabilityProfile": load_optional_json(repo_root, ctx_path("minimalObservabilityProfilePath", pipeline_key="minimalObservability")),
        "provisioningManifest": load_optional_json(repo_root, ctx_path("provisioningManifestPath")),
        "clusterValidationManifest": load_optional_json(repo_root, ctx_path("clusterValidationManifestPath")),
        "clusterValidationRaw": load_optional_json(repo_root, ctx_path("clusterValidationRawJsonPath")),
        "applicationDeploymentManifest": load_optional_json(repo_root, ctx_path("applicationDeploymentManifestPath")),
        "localAiSmokeResult": load_optional_json(repo_root, ctx_path("localAiSmokeResultPath")),
        "minimalObservabilityManifest": load_optional_json(repo_root, ctx_path("minimalObservabilityManifestPath")),
        "minimalObservabilityMetrics": load_optional_json(repo_root, ctx_path("minimalObservabilityMetricsPath")),
    }

    provider_context_enabled = bool(provider_context.get("enabled", bool(provider_backed)))

    return {
        "enabled": provider_context_enabled,
        "repoRoot": str(repo_root),
        "cycleId": first_non_empty(profile.get("cycleId"), cycle.get("cycleId") if isinstance(cycle, dict) else None),
        "baselineId": first_non_empty(profile.get("baselineId"), cycle.get("baseline", {}).get("baselineId") if isinstance(cycle, dict) else None),
        "providerId": first_non_empty(provider_context.get("providerId"), provider_backed.get("provider") if isinstance(provider_backed, dict) else None),
        "documents": documents,
    }


def infrastructure_summary_rows(context: dict[str, Any], baseline: dict[str, Any]) -> list[list[Any]]:
    docs = context.get("documents", {})
    cycle = (docs.get("cycle") or {}).get("payload") or {}
    infra = (docs.get("infrastructureProfile") or {}).get("payload") or {}
    node_summary = infra.get("nodeSummary") if isinstance(infra, dict) else {}
    identity = infra.get("clusterIdentity") if isinstance(infra, dict) else {}
    lifecycle = infra.get("lifecycle") if isinstance(infra, dict) else {}
    pbi = cycle.get("providerBackedInfrastructure") if isinstance(cycle, dict) else {}
    return [
        ["Cycle ID", context.get("cycleId") or cycle.get("cycleId") or "NA"],
        ["Baseline ID", context.get("baselineId") or baseline.get("baselineId") or "NA"],
        ["Infrastructure profile", profile_id(infra, "infrastructureProfileId")],
        ["Provider", context.get("providerId") or profile_id(infra.get("provider") if isinstance(infra, dict) else None, "providerId")],
        ["Cluster name", identity.get("clusterName") if isinstance(identity, dict) else "NA"],
        ["Kubernetes distribution", identity.get("kubernetesDistribution") if isinstance(identity, dict) else "NA"],
        ["K3s version", identity.get("k3sVersion") if isinstance(identity, dict) else "NA"],
        ["Control-plane nodes", node_summary.get("controlPlaneCount") if isinstance(node_summary, dict) else "NA"],
        ["Worker nodes", node_summary.get("workerCount") if isinstance(node_summary, dict) else "NA"],
        ["Worker total vCPU", node_summary.get("totalWorkerVcpus") if isinstance(node_summary, dict) else "NA"],
        ["Worker total memory", f"{node_summary.get('totalWorkerMemoryGiB')} GiB" if isinstance(node_summary, dict) and node_summary.get("totalWorkerMemoryGiB") is not None else "NA"],
        ["Lifecycle mode", first_non_empty(pbi.get("clusterLifecycleMode") if isinstance(pbi, dict) else None, lifecycle.get("clusterLifecycleModeDefault") if isinstance(lifecycle, dict) else None)],
        ["Destroy after cycle", first_non_empty(pbi.get("destroyClusterAfterCycle") if isinstance(pbi, dict) else None, lifecycle.get("destroyClusterAfterCycleDefault") if isinstance(lifecycle, dict) else None)],
    ]


def normalized_summary_scope(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace("-", "_")
    if not text:
        return None
    if text in {"variant", "variant_scoped", "scenario_variant", "scenario_variant_scoped", "scenario_scoped"}:
        return "variant_scoped"
    if text in {"fixed", "fixed_cycle", "fixed_cycle_scoped", "cycle_scoped"}:
        return "fixed_cycle_scoped"
    return text


def infrastructure_summary_mode(profile: dict[str, Any], context: dict[str, Any]) -> str:
    explicit = first_non_empty(
        profile.get("infrastructureSummaryMode"),
        context.get("infrastructureSummaryMode"),
        profile.get("infrastructureProfileScope"),
    )
    normalized = normalized_summary_scope(explicit)
    if normalized:
        return normalized
    docs = context.get("documents", {}) if isinstance(context, dict) else {}
    cycle = (docs.get("cycle") or {}).get("payload") or {}
    if isinstance(cycle, dict):
        explicit_cycle = normalized_summary_scope(cycle.get("infrastructureSummaryMode"))
        if explicit_cycle:
            return explicit_cycle
        campaign = cycle.get("campaign") or {}
        if isinstance(campaign, dict) and campaign.get("variants"):
            return "variant_scoped"
    return "fixed_cycle_scoped"


def infrastructure_variant_summary_rows(context: dict[str, Any], family_data: dict[str, dict[str, Any]]) -> list[list[Any]]:
    docs = context.get("documents", {}) if isinstance(context, dict) else {}
    cycle = (docs.get("cycle") or {}).get("payload") or {}
    campaign = cycle.get("campaign") if isinstance(cycle, dict) else {}
    variants_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(campaign, dict):
        for variant in campaign.get("variants") or []:
            if isinstance(variant, dict):
                variant_id = variant.get("variantId") or variant.get("scenarioId")
                if variant_id:
                    variants_by_id[str(variant_id)] = variant

    rows: list[list[Any]] = []
    seen: set[str] = set()
    for family in sorted(family_data.keys()):
        for scenario_id, entry in sorted(family_data.get(family, {}).items(), key=lambda kv: scenario_sort_key(kv[0])):
            scenario = entry.get("scenario") or {}
            variant = variants_by_id.get(scenario_id, {})
            infra_id = first_non_empty(
                scenario.get("infrastructureProfileId") if isinstance(scenario, dict) else None,
                variant.get("infrastructureProfileId") if isinstance(variant, dict) else None,
            )
            infra_path = first_non_empty(
                scenario.get("infrastructureProfilePath") if isinstance(scenario, dict) else None,
                variant.get("infrastructureProfilePath") if isinstance(variant, dict) else None,
            )
            provider_binding = first_non_empty(
                scenario.get("providerBindingId") if isinstance(scenario, dict) else None,
                variant.get("providerBindingId") if isinstance(variant, dict) else None,
            )
            provider_id = first_non_empty(
                scenario.get("providerId") if isinstance(scenario, dict) else None,
                context.get("providerId"),
            )
            resource_variant = scenario.get("resourceVariant") if isinstance(scenario, dict) else {}
            node_count_variant = scenario.get("nodeCountVariant") if isinstance(scenario, dict) else {}
            if not isinstance(resource_variant, dict):
                resource_variant = {}
            if not isinstance(node_count_variant, dict):
                node_count_variant = {}
            worker_nodes = first_non_empty(
                node_count_variant.get("workerNodeCount"),
                resource_variant.get("workerNodeCount"),
                scenario.get("infrastructureWorkerNodeCount") if isinstance(scenario, dict) else None,
                scenario.get("workerNodeCount") if isinstance(scenario, dict) else None,
                nested_get(scenario, "defaultSchedulerTopology", "workerNodeCount") if isinstance(scenario, dict) else None,
                variant.get("workerNodeCount") if isinstance(variant, dict) else None,
            )
            worker_vcpu = first_non_empty(
                node_count_variant.get("workerVcpusPerNode"),
                resource_variant.get("workerVcpusPerNode"),
                scenario.get("workerVcpusPerNode") if isinstance(scenario, dict) else None,
                variant.get("workerVcpusPerNode") if isinstance(variant, dict) else None,
            )
            worker_memory = first_non_empty(
                node_count_variant.get("workerMemoryGiBPerNode"),
                resource_variant.get("workerMemoryGiBPerNode"),
                scenario.get("workerMemoryGiBPerNode") if isinstance(scenario, dict) else None,
                variant.get("workerMemoryGiBPerNode") if isinstance(variant, dict) else None,
            )
            lifecycle_mode = first_non_empty(
                scenario.get("clusterLifecycleMode") if isinstance(scenario, dict) else None,
                variant.get("clusterLifecycleMode") if isinstance(variant, dict) else None,
                nested_get(cycle, "providerBackedInfrastructure", "clusterLifecycleMode") if isinstance(cycle, dict) else None,
            )
            key = f"{family}:{scenario_id}:{infra_id}:{infra_path}"
            if key in seen:
                continue
            seen.add(key)
            rows.append([
                f"`{scenario_id}`",
                family,
                infra_id or "NA",
                infra_path or "NA",
                provider_id or "NA",
                provider_binding or "NA",
                worker_nodes if worker_nodes is not None else "NA",
                f"{worker_vcpu} vCPU" if worker_vcpu is not None else "NA",
                f"{worker_memory} GiB" if worker_memory is not None else "NA",
                lifecycle_mode or "NA",
            ])
    return rows


def infrastructure_variant_summary_section(context: dict[str, Any], family_data: dict[str, dict[str, Any]]) -> str:
    rows = infrastructure_variant_summary_rows(context, family_data)
    if not rows:
        return "No variant-scoped infrastructure metadata is available for this reporting profile."
    return md_table(
        [
            "Scenario",
            "Family",
            "Infrastructure profile",
            "Infrastructure profile path",
            "Provider",
            "Provider binding",
            "Worker nodes",
            "Worker vCPU/node",
            "Worker memory/node",
            "Lifecycle mode",
        ],
        rows,
    )


def campaign_variants_by_id(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    docs = context.get("documents", {}) if isinstance(context, dict) else {}
    cycle = (docs.get("cycle") or {}).get("payload") or {}
    campaign = cycle.get("campaign") if isinstance(cycle, dict) else {}
    variants: dict[str, dict[str, Any]] = {}
    if isinstance(campaign, dict):
        for variant in campaign.get("variants") or []:
            if isinstance(variant, dict):
                variant_id = first_non_empty(variant.get("variantId"), variant.get("scenarioId"))
                if variant_id:
                    variants[str(variant_id)] = variant
    return variants


def has_campaign_variants(context: dict[str, Any]) -> bool:
    return bool(campaign_variants_by_id(context))


def scenario_variant_items(context: dict[str, Any], family_data: dict[str, dict[str, Any]]) -> list[tuple[str, str, dict[str, Any], dict[str, Any], dict[str, Any]]]:
    variants = campaign_variants_by_id(context)
    items: list[tuple[str, str, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for family in sorted(family_data.keys()):
        for scenario_id, entry in sorted(family_data.get(family, {}).items(), key=lambda kv: scenario_sort_key(kv[0])):
            scenario = entry.get("scenario") if isinstance(entry, dict) else {}
            if not isinstance(scenario, dict):
                scenario = {}
            variant = variants.get(scenario_id, {})
            items.append((family, scenario_id, entry, scenario, variant if isinstance(variant, dict) else {}))
    return items


def runtime_profile_value(payload: dict[str, Any], section: str, field: str, top_level_key: str | None = None) -> Any:
    direct_value = payload.get(top_level_key) if isinstance(payload, dict) and top_level_key else None
    runtime = payload.get("runtimeGeneratedProfiles") if isinstance(payload, dict) else {}
    generated = runtime.get(section) if isinstance(runtime, dict) else {}
    return first_non_empty(direct_value, generated.get(field) if isinstance(generated, dict) else None)


def context_repo_root(context: dict[str, Any]) -> Path | None:
    repo_root = context.get("repoRoot") if isinstance(context, dict) else None
    if not repo_root:
        return None
    return Path(str(repo_root))


def runtime_cycle_config_candidates(context: dict[str, Any], scenario_id: str, scenario: dict[str, Any], variant: dict[str, Any]) -> list[Any]:
    candidates: list[Any] = []

    def append_nested_runtime_cycle(payload: dict[str, Any]) -> None:
        runtime = payload.get("runtimeGeneratedProfiles") if isinstance(payload, dict) else {}
        cycle_variant = runtime.get("cycleVariant") if isinstance(runtime, dict) else {}
        if isinstance(cycle_variant, dict):
            candidates.append(cycle_variant.get("path"))

    for payload in (scenario, variant):
        if not isinstance(payload, dict):
            continue
        append_nested_runtime_cycle(payload)
        for key in (
            "variantCycleConfig",
            "variantCycleConfigPath",
            "generatedCycleConfig",
            "generatedCycleConfigPath",
            "cycleVariantConfig",
            "cycleVariantConfigPath",
            "cycleConfigPath",
        ):
            candidates.append(payload.get(key))

    docs = context.get("documents", {}) if isinstance(context, dict) else {}
    cycle = (docs.get("cycle") or {}).get("payload") or {}
    campaign = cycle.get("campaign") if isinstance(cycle, dict) else {}
    generated_root = campaign.get("generatedRuntimeConfigRoot") if isinstance(campaign, dict) else None
    if generated_root and scenario_id:
        candidates.extend([
            f"{str(generated_root).rstrip('/')}/{scenario_id}/{scenario_id}.cycle.json",
            f"{str(generated_root).rstrip('/')}/{scenario_id}/{scenario_id}_cycle.json",
            f"{str(generated_root).rstrip('/')}/{scenario_id}/cycle.json",
        ])

    seen: set[str] = set()
    unique: list[Any] = []
    for candidate in candidates:
        if not candidate:
            continue
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def load_runtime_cycle_config(context: dict[str, Any], scenario_id: str, scenario: dict[str, Any], variant: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    repo_root = context_repo_root(context)
    if repo_root is None:
        return None, {}
    cache = context.setdefault("_runtimeCycleConfigCache", {}) if isinstance(context, dict) else {}
    if scenario_id in cache:
        cached = cache.get(scenario_id) or {}
        return cached.get("path"), cached.get("payload") or {}
    for candidate in runtime_cycle_config_candidates(context, scenario_id, scenario, variant):
        doc = load_optional_json(repo_root, candidate)
        if doc.get("exists") and isinstance(doc.get("payload"), dict):
            cache[scenario_id] = {"path": doc.get("path"), "payload": doc.get("payload")}
            return doc.get("path"), doc.get("payload") or {}
    cache[scenario_id] = {"path": None, "payload": {}}
    return None, {}


def runtime_profile_value_from_cycle(cycle_payload: dict[str, Any], section: str, field: str, top_level_key: str | None = None) -> Any:
    if not isinstance(cycle_payload, dict):
        return None
    provider_backed = cycle_payload.get("providerBackedInfrastructure") if isinstance(cycle_payload.get("providerBackedInfrastructure"), dict) else {}
    pipeline_profiles = cycle_payload.get("pipelineProfiles") if isinstance(cycle_payload.get("pipelineProfiles"), dict) else {}
    runtime = cycle_payload.get("runtimeGeneratedProfiles") if isinstance(cycle_payload.get("runtimeGeneratedProfiles"), dict) else {}
    generated = runtime.get(section) if isinstance(runtime, dict) else {}
    section_prefix = section
    profile_id_key = f"{section_prefix}ProfileId"
    profile_path_key = f"{section_prefix}ProfilePath"
    provider_value = None
    if field == "profileId":
        provider_value = first_non_empty(provider_backed.get(profile_id_key), provider_backed.get(top_level_key) if top_level_key else None)
    elif field == "path":
        provider_value = first_non_empty(provider_backed.get(profile_path_key), provider_backed.get(top_level_key) if top_level_key else None)
    return first_non_empty(
        cycle_payload.get(top_level_key) if top_level_key else None,
        provider_value,
        pipeline_profiles.get(section),
        generated.get(field) if isinstance(generated, dict) else None,
    )


def variant_cluster_validation_evidence(context: dict[str, Any], runtime_cycle_payload: dict[str, Any], fallback_doc: dict[str, Any]) -> str:
    repo_root = context_repo_root(context)
    if repo_root is None:
        return "cycle-level or campaign-level evidence"
    provider_backed = runtime_cycle_payload.get("providerBackedInfrastructure") if isinstance(runtime_cycle_payload, dict) else {}
    artifact_root = provider_backed.get("clusterValidationArtifactRoot") if isinstance(provider_backed, dict) else None
    if artifact_root:
        manifest_doc = load_optional_json(repo_root, f"{str(artifact_root).rstrip('/')}/latest-cluster-validation-manifest.json")
        if manifest_doc.get("path"):
            status = extract_manifest_status(manifest_doc) if manifest_doc.get("exists") else artifact_state(manifest_doc)
            return f"{manifest_doc.get('path')} ({status})"
    if fallback_doc.get("path"):
        return f"{fallback_doc.get('path')} ({artifact_state(fallback_doc)})"
    return "cycle-level or campaign-level evidence"


def load_provider_binding_payload(context: dict[str, Any], binding_path: Any) -> dict[str, Any]:
    repo_root_text = context.get("repoRoot") if isinstance(context, dict) else None
    if not repo_root_text:
        return {}
    doc = load_optional_json(Path(str(repo_root_text)), binding_path)
    payload = doc.get("payload") if isinstance(doc, dict) else None
    return payload if isinstance(payload, dict) else {}


def provider_summary_rows(context: dict[str, Any]) -> list[list[Any]]:
    docs = context.get("documents", {})
    binding = (docs.get("providerBinding") or {}).get("payload") or {}
    provider_config = binding.get("providerConfig") if isinstance(binding, dict) else {}
    resolution = binding.get("resolutionPolicy") if isinstance(binding, dict) else {}
    return [
        ["Provider binding", profile_id(binding, "providerBindingId")],
        ["Provider ID", binding.get("providerId") if isinstance(binding, dict) else "NA"],
        ["Materialization mode", binding.get("materializationMode") if isinstance(binding, dict) else "NA"],
        ["Example config", provider_config.get("examplePath") if isinstance(provider_config, dict) else "NA"],
        ["Local config", provider_config.get("localPath") if isinstance(provider_config, dict) else "NA"],
        ["Recommended kubeconfig", provider_config.get("recommendedKubeconfigPath") if isinstance(provider_config, dict) else "NA"],
        ["Real execution preference", compact_list(resolution.get("realExecutionConfigPreferenceOrder") if isinstance(resolution, dict) else None)],
        ["Local config required for create/delete", resolution.get("localConfigRequiredForCreateDelete") if isinstance(resolution, dict) else "NA"],
    ]


def provider_variant_summary_rows(context: dict[str, Any], family_data: dict[str, dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    seen: set[str] = set()
    for family, scenario_id, _entry, scenario, variant in scenario_variant_items(context, family_data):
        binding_path = first_non_empty(
            scenario.get("providerBindingPath"),
            variant.get("providerBindingPath"),
        )
        binding = load_provider_binding_payload(context, binding_path)
        provider_config = first_non_empty(
            scenario.get("providerConfig") if isinstance(scenario.get("providerConfig"), dict) else None,
            binding.get("providerConfig") if isinstance(binding.get("providerConfig"), dict) else None,
            {},
        )
        if not isinstance(provider_config, dict):
            provider_config = {}
        provider_id = first_non_empty(
            scenario.get("providerId"),
            variant.get("providerId"),
            binding.get("providerId") if isinstance(binding, dict) else None,
            context.get("providerId"),
        )
        binding_id = first_non_empty(
            scenario.get("providerBindingId"),
            variant.get("providerBindingId"),
            binding.get("providerBindingId") if isinstance(binding, dict) else None,
        )
        example_config = first_non_empty(
            variant.get("providerConfigExamplePath"),
            scenario.get("providerConfigExamplePath"),
            provider_config.get("examplePath"),
        )
        local_config = first_non_empty(
            variant.get("providerConfigLocalPath"),
            scenario.get("providerConfigLocalPath"),
            provider_config.get("localPath"),
        )
        kubeconfig = first_non_empty(
            scenario.get("kubeconfigPath"),
            variant.get("kubeconfigPath"),
            provider_config.get("recommendedKubeconfigPath"),
        )
        key = ":".join(str(item) for item in [family, scenario_id, provider_id, binding_id, example_config, local_config, kubeconfig])
        if key in seen:
            continue
        seen.add(key)
        rows.append([
            f"`{scenario_id}`",
            family,
            semantic_value(provider_id, "not_declared"),
            semantic_value(binding_id, "not_declared"),
            semantic_value(binding_path, "not_declared"),
            semantic_value(example_config, "not_declared"),
            semantic_value(local_config, "not_declared"),
            semantic_value(kubeconfig, "not_declared"),
        ])
    return rows


def provider_variant_summary_section(context: dict[str, Any], family_data: dict[str, dict[str, Any]]) -> str:
    rows = provider_variant_summary_rows(context, family_data)
    if not rows:
        return "No variant-scoped provider metadata is available for this reporting profile."

    provider_tuples = {tuple(row[2:]) for row in rows}
    if len(provider_tuples) == 1:
        provider, binding, binding_path, example_config, local_config, kubeconfig = rows[0][2:]
        covered = [row[0] for row in rows]
        return (
            "All configured scenarios currently resolve to the same provider binding. "
            "The provider is therefore reported once to avoid repeating identical configuration metadata.\n\n"
            + md_table(
                ["Item", "Value"],
                [
                    ["Covered scenarios", semantic_compact_list(covered, empty="not_declared", limit=16)],
                    ["Provider", provider],
                    ["Provider binding", binding],
                    ["Provider binding path", binding_path],
                    ["Example config", example_config],
                    ["Local config", local_config],
                    ["Kubeconfig", kubeconfig],
                ],
            )
        )

    return md_table(
        [
            "Scenario",
            "Family",
            "Provider",
            "Provider binding",
            "Provider binding path",
            "Example config",
            "Local config",
            "Kubeconfig",
        ],
        rows,
    )


def _load_cluster_validation_template(context: dict[str, Any], template_path: Any) -> dict[str, Any]:
    if not template_path:
        return {}
    repo_root_value = context.get("repoRoot") if isinstance(context, dict) else None
    if not repo_root_value:
        return {}
    try:
        path = resolve_artifact_path(Path(str(repo_root_value)), template_path)
        payload = read_json_optional(path)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def is_variant_scoped_campaign(campaign: Any) -> bool:
    if not isinstance(campaign, dict):
        return False
    return bool(
        campaign.get("variants")
        or campaign.get("plannedScenarioIds")
        or campaign.get("plannedScenarioReferences")
        or campaign.get("generatedRuntimeConfigRoot")
        or campaign.get("scenarioConfigRoot")
    )


def validation_summary_rows(context: dict[str, Any]) -> list[list[Any]]:
    docs = context.get("documents", {})
    cycle = (docs.get("cycle") or {}).get("payload") or {}
    profile_doc = docs.get("clusterValidationProfile") or {}
    manifest_doc = docs.get("clusterValidationManifest") or {}
    raw_doc = docs.get("clusterValidationRaw") or {}
    profile_payload = profile_doc.get("payload") or {}
    provider_backed = cycle.get("providerBackedInfrastructure") if isinstance(cycle, dict) else {}
    pipeline_profiles = cycle.get("pipelineProfiles") if isinstance(cycle, dict) else {}
    campaign = cycle.get("campaign") if isinstance(cycle, dict) else {}
    campaign_based = is_variant_scoped_campaign(campaign)

    rows: list[list[Any]] = []
    if campaign_based:
        template_path = first_non_empty(
            provider_backed.get("clusterValidationTemplatePath") if isinstance(provider_backed, dict) else None,
            pipeline_profiles.get("clusterValidationTemplate") if isinstance(pipeline_profiles, dict) else None,
        )
        registry_path = first_non_empty(
            provider_backed.get("clusterValidationIndexPath") if isinstance(provider_backed, dict) else None,
            pipeline_profiles.get("clusterValidationIndex") if isinstance(pipeline_profiles, dict) else None,
        )
        generated_root = first_non_empty(
            campaign.get("generatedRuntimeConfigRoot") if isinstance(campaign, dict) else None,
            f"results/experimental-cycles/{context.get('cycleId')}/execution/generated-runtime-configs" if context.get("cycleId") else None,
        )
        validation_root = first_non_empty(
            provider_backed.get("clusterValidationArtifactRoot") if isinstance(provider_backed, dict) else None,
            generated_root,
        )
        template_payload = _load_cluster_validation_template(context, template_path)
        template_gate = template_payload.get("preValidationGate") if isinstance(template_payload, dict) else {}
        template_policy = template_payload.get("artifactPolicy") if isinstance(template_payload, dict) else {}

        append_semantic_row(rows, "Validation profile", first_non_empty(
            template_payload.get("clusterValidationProfileId") if isinstance(template_payload, dict) else None,
            "variant-scoped generated provider-backed validation profiles",
        ))
        append_semantic_row(rows, "Profile file", first_non_empty(template_path, registry_path))

        variant_validation_docs: list[dict[str, Any]] = []
        repo_root = context_repo_root(context)
        cycle_id = context.get("cycleId") if isinstance(context, dict) else None
        if repo_root is not None and cycle_id:
            variants_root = repo_root / "results" / "experimental-cycles" / str(cycle_id) / "variants"
            if variants_root.exists():
                for path in sorted(variants_root.glob("*/infrastructure/validation/latest-cluster-validation-manifest.json")):
                    payload = read_json_optional(path)
                    variant_validation_docs.append({
                        "path": safe_rel(path, repo_root),
                        "payload": payload if isinstance(payload, dict) else {},
                    })

        if variant_validation_docs:
            status_counts: dict[str, int] = defaultdict(int)
            for item in variant_validation_docs:
                status = str((item.get("payload") or {}).get("status") or "unknown")
                status_counts[status] += 1
            validated_count = status_counts.get("validated", 0)
            rows.append(["Latest manifest", f"variant-scoped validation manifests ({len(variant_validation_docs)} available)"])
            append_semantic_row(rows, "Current status", f"variant-scoped validation available ({validated_count}/{len(variant_validation_docs)} validated)")
            append_semantic_row(rows, "Variant validation statuses", ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())))
        elif manifest_doc.get("path"):
            rows.append(["Latest manifest", f"{manifest_doc.get('path')} ({document_state_phrase(manifest_doc)})"])
            append_semantic_row(rows, "Current status", extract_manifest_status(manifest_doc) if manifest_doc.get("exists") else "pending generation")
        else:
            rows.append(["Latest manifest", "pending generation"])
            rows.append(["Current status", "pending generation"])
        append_semantic_row(rows, "Latest raw validation", f"variant-scoped validation evidence is recorded in the campaign execution manifest and generated runtime profiles under {generated_root}")
        append_semantic_row(rows, "Accepted provisioning statuses", first_non_empty(
            compact_list(template_gate.get("acceptedProvisioningStatuses") if isinstance(template_gate, dict) else None),
            "resolved from generated variant profiles",
        ))
        append_semantic_row(rows, "Required kubeconfig status", first_non_empty(
            template_gate.get("requireKubeconfigVerificationStatus") if isinstance(template_gate, dict) else None,
            "verified",
        ))
        append_semantic_row(rows, "Artifact root", first_non_empty(
            validation_root,
            template_policy.get("root") if isinstance(template_policy, dict) else None,
        ))
        return rows

    append_semantic_row(rows, "Validation profile", profile_id(profile_payload, "clusterValidationProfileId"))
    append_semantic_row(rows, "Profile file", profile_doc.get("path"))
    if manifest_doc.get("path"):
        rows.append(["Latest manifest", f"{manifest_doc.get('path')} ({document_state_phrase(manifest_doc)})"])
        if manifest_doc.get("exists"):
            append_semantic_row(rows, "Current status", extract_manifest_status(manifest_doc))
    else:
        rows.append(["Current validation evidence", "pending generation"])
    if raw_doc.get("path"):
        rows.append(["Latest raw validation", f"{raw_doc.get('path')} ({document_state_phrase(raw_doc)})"])

    artifact_policy = profile_payload.get("artifactPolicy") if isinstance(profile_payload, dict) else {}
    gate = profile_payload.get("preValidationGate") if isinstance(profile_payload, dict) else {}
    append_semantic_row(rows, "Accepted provisioning statuses", compact_list(gate.get("acceptedProvisioningStatuses") if isinstance(gate, dict) else None))
    append_semantic_row(rows, "Required kubeconfig status", gate.get("requireKubeconfigVerificationStatus") if isinstance(gate, dict) else None)
    append_semantic_row(rows, "Artifact root", artifact_policy.get("root") if isinstance(artifact_policy, dict) else None)
    return rows or [["Validation evidence", "pending generation"]]


def runtime_profile_variant_summary_rows(context: dict[str, Any], family_data: dict[str, dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    seen: set[str] = set()
    docs = context.get("documents", {}) if isinstance(context, dict) else {}
    validation_manifest = docs.get("clusterValidationManifest") or {}
    for family, scenario_id, _entry, scenario, variant in scenario_variant_items(context, family_data):
        _runtime_cycle_path, runtime_cycle = load_runtime_cycle_config(context, scenario_id, scenario, variant)
        precheck_profile = first_non_empty(
            runtime_profile_value(scenario, "precheck", "profileId", "precheckProfileId"),
            runtime_profile_value(variant, "precheck", "profileId", "precheckProfileId"),
            runtime_profile_value_from_cycle(runtime_cycle, "precheck", "profileId", "precheckProfileId"),
        )
        precheck_path = first_non_empty(
            runtime_profile_value(scenario, "precheck", "path", "precheckProfilePath"),
            runtime_profile_value(variant, "precheck", "path", "precheckProfilePath"),
            runtime_profile_value_from_cycle(runtime_cycle, "precheck", "path", "precheckProfilePath"),
        )
        app_profile = first_non_empty(
            runtime_profile_value(scenario, "applicationDeployment", "profileId", "applicationDeploymentProfileId"),
            runtime_profile_value(variant, "applicationDeployment", "profileId", "applicationDeploymentProfileId"),
            runtime_profile_value_from_cycle(runtime_cycle, "applicationDeployment", "profileId", "applicationDeploymentProfileId"),
        )
        app_path = first_non_empty(
            runtime_profile_value(scenario, "applicationDeployment", "path", "applicationDeploymentProfilePath"),
            runtime_profile_value(variant, "applicationDeployment", "path", "applicationDeploymentProfilePath"),
            runtime_profile_value_from_cycle(runtime_cycle, "applicationDeployment", "path", "applicationDeploymentProfilePath"),
        )
        observability_profile = first_non_empty(
            runtime_profile_value(scenario, "minimalObservability", "profileId", "minimalObservabilityProfileId"),
            runtime_profile_value(variant, "minimalObservability", "profileId", "minimalObservabilityProfileId"),
            runtime_profile_value_from_cycle(runtime_cycle, "minimalObservability", "profileId", "minimalObservabilityProfileId"),
        )
        observability_path = first_non_empty(
            runtime_profile_value(scenario, "minimalObservability", "path", "minimalObservabilityProfilePath"),
            runtime_profile_value(variant, "minimalObservability", "path", "minimalObservabilityProfilePath"),
            runtime_profile_value_from_cycle(runtime_cycle, "minimalObservability", "path", "minimalObservabilityProfilePath"),
        )
        key = ":".join(str(item) for item in [family, scenario_id, precheck_profile, app_profile, observability_profile])
        if key in seen:
            continue
        seen.add(key)
        rows.append([
            f"`{scenario_id}`",
            family,
            precheck_profile or "NA",
            precheck_path or "NA",
            app_profile or "NA",
            app_path or "NA",
            observability_profile or "NA",
            observability_path or "NA",
            variant_cluster_validation_evidence(context, runtime_cycle, validation_manifest),
        ])
    return rows


def runtime_profile_variant_summary_section(context: dict[str, Any], family_data: dict[str, dict[str, Any]]) -> str:
    rows = runtime_profile_variant_summary_rows(context, family_data)
    if not rows:
        return "No variant-scoped runtime profile metadata is available for this reporting profile."
    return md_table(
        [
            "Scenario",
            "Family",
            "Precheck profile",
            "Precheck profile path",
            "Application deployment profile",
            "Application deployment profile path",
            "Minimal observability profile",
            "Minimal observability profile path",
            "Cluster validation evidence",
        ],
        rows,
    )


def application_topology_rows(context: dict[str, Any]) -> list[list[Any]]:
    docs = context.get("documents", {})
    app = (docs.get("applicationDeploymentProfile") or {}).get("payload") or {}
    placement = (docs.get("placementProfile") or {}).get("payload") or {}
    topology = app.get("deploymentTopology") if isinstance(app, dict) else {}
    model = nested_get(topology, "model", default={})
    worker_count = nested_get(topology, "workerCount", default={})
    topology_placement = nested_get(topology, "placement", default={})
    apply_order = topology.get("kustomizeApplyOrder") if isinstance(topology, dict) else []
    return [
        ["Application deployment profile", profile_id(app, "applicationDeploymentProfileId")],
        ["Namespace", topology.get("namespace") if isinstance(topology, dict) else "NA"],
        ["Model", model.get("modelName") if isinstance(model, dict) else "NA"],
        ["Worker count", worker_count.get("count") if isinstance(worker_count, dict) else "NA"],
        ["Active RPC workers", compact_list(worker_count.get("expectedActiveRpcWorkers") if isinstance(worker_count, dict) else None)],
        ["Placement profile", profile_id(placement, "placementProfileId")],
        ["Placement strategy", placement.get("strategy") if isinstance(placement, dict) else topology_placement.get("placementType") if isinstance(topology_placement, dict) else "NA"],
        ["Kustomize targets", compact_list([item.get("path") for item in apply_order if isinstance(item, dict)], limit=12)],
        ["Deployment manifest", f"{(docs.get('applicationDeploymentManifest') or {}).get('path')} ({artifact_state(docs.get('applicationDeploymentManifest') or {})})"],
        ["Smoke result", f"{(docs.get('localAiSmokeResult') or {}).get('path')} ({artifact_state(docs.get('localAiSmokeResult') or {})})"],
    ]


def application_topology_variant_summary_rows(context: dict[str, Any], family_data: dict[str, dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    seen: set[str] = set()
    for family, scenario_id, _entry, scenario, variant in scenario_variant_items(context, family_data):
        topology = first_non_empty(
            scenario.get("applicationTopology") if isinstance(scenario.get("applicationTopology"), dict) else None,
            variant.get("applicationTopology") if isinstance(variant.get("applicationTopology"), dict) else None,
            {},
        )
        if not isinstance(topology, dict):
            topology = {}
        placement_profile = first_non_empty(
            scenario.get("placementProfileId"),
            topology.get("placementScenario"),
            variant.get("placementProfileId"),
        )
        placement_type = first_non_empty(
            scenario.get("resolvedPlacementType"),
            topology.get("placementType"),
            variant.get("resolvedPlacementType"),
        )
        topology_dir = first_non_empty(scenario.get("topologyDir"), topology.get("topologyDir"), variant.get("topologyDir"))
        server_manifest = first_non_empty(scenario.get("serverManifest"), topology.get("serverManifest"), variant.get("serverManifest"))
        worker_count = first_non_empty(
            scenario.get("resolvedWorkerCount"),
            scenario.get("localAiWorkerCountPerTenant"),
            topology.get("localAiWorkerCount"),
            topology.get("localAiWorkerCountPerTenant"),
            nested_get(scenario, "defaultSchedulerTopology", "localAiWorkerCountPerTenant"),
            variant.get("resolvedWorkerCount"),
            variant.get("localAiWorkerCountPerTenant"),
        )
        active_workers = first_non_empty(
            scenario.get("expectedActiveRpcWorkers"),
            topology.get("expectedActiveRpcWorkers"),
            variant.get("expectedActiveRpcWorkers"),
        )
        expected_server_node = first_non_empty(
            scenario.get("expectedServerNode"),
            topology.get("expectedServerNode"),
            variant.get("expectedServerNode"),
        )
        expected_worker_nodes = first_non_empty(
            scenario.get("expectedWorkerNodes"),
            topology.get("expectedWorkerNodes"),
            variant.get("expectedWorkerNodes"),
        )
        latency_profile = first_non_empty(scenario.get("latencyProfileId"), variant.get("latencyProfileId"))
        tenant_count = first_non_empty(
            scenario.get("tenantCount"),
            topology.get("tenantCount"),
            nested_get(scenario, "defaultSchedulerTopology", "tenantCount"),
            variant.get("tenantCount"),
        )
        tenant_ids = first_non_empty(scenario.get("tenantIds"), topology.get("tenantIds"), variant.get("tenantIds"))
        traffic_profile = first_non_empty(scenario.get("trafficProfileId"), variant.get("trafficProfileId"))
        tenancy_profile = first_non_empty(
            scenario.get("tenancyProfileId"),
            variant.get("tenancyProfileId"),
            scenario.get("tenantProfileId"),
            variant.get("tenantProfileId"),
            traffic_profile,
            f"{tenant_count} tenants" if tenant_count is not None else None,
        )
        generated_deployment = first_non_empty(
            runtime_profile_value(scenario, "applicationDeployment", "path", "applicationDeploymentProfilePath"),
            runtime_profile_value(variant, "applicationDeployment", "path", "applicationDeploymentProfilePath"),
        )
        key = ":".join(str(item) for item in [family, scenario_id, placement_profile, placement_type, topology_dir, generated_deployment])
        if key in seen:
            continue
        seen.add(key)
        latency_value = semantic_value(
            latency_profile,
            "not_declared" if family == "latency-injection" else "not_applicable",
        )
        tenancy_parts: list[str] = []
        if tenant_count is not None:
            tenancy_parts.append(f"tenants={tenant_count}")
        if tenant_ids:
            tenancy_parts.append(f"tenantIds={semantic_compact_list(tenant_ids, empty='not_declared')}")
        if traffic_profile:
            tenancy_parts.append(f"trafficProfile={traffic_profile}")
        tenancy_value = "; ".join(tenancy_parts) if tenancy_parts else semantic_value(tenancy_profile, "not_declared")
        rows.append([
            f"`{scenario_id}`",
            family,
            semantic_value(placement_profile, "not_declared"),
            semantic_value(placement_type, "not_declared"),
            semantic_value(topology_dir, "not_declared"),
            semantic_value(server_manifest, "not_declared"),
            worker_count if worker_count is not None else "not_declared",
            semantic_compact_list(active_workers, empty="not_declared"),
            semantic_value(expected_server_node, "not_declared"),
            semantic_compact_list(expected_worker_nodes, empty="not_declared"),
            latency_value,
            tenancy_value,
            semantic_value(generated_deployment, "not_declared"),
        ])
    return rows


def application_topology_variant_summary_section(context: dict[str, Any], family_data: dict[str, dict[str, Any]]) -> str:
    rows = application_topology_variant_summary_rows(context, family_data)
    if not rows:
        return "No variant-scoped application topology metadata is available for this reporting profile."
    return md_table(
        [
            "Scenario",
            "Family",
            "Placement profile",
            "Placement type",
            "Topology dir",
            "Server manifest",
            "Worker count",
            "Active RPC workers",
            "Expected server node",
            "Expected worker nodes",
            "Latency profile",
            "Tenancy profile",
            "Generated deployment profile",
        ],
        rows,
    )


def summary_aggregate_value(family_data: dict[str, dict[str, Any]], profile: dict[str, Any], key: str) -> Any:
    entries = [entry for family in profile.get("familyOrder", []) for entry in (family_data.get(family, {}) or {}).values() if entry.get("status") == "measured"]
    values: list[float | None] = []
    if key == "success_rate_percent":
        for entry in entries:
            metrics = (entry.get("summary") or {}).get("metrics") or {}
            request_count = to_number((metrics.get("request_count") or {}).get("mean"))
            failure_count = to_number((metrics.get("failure_count") or {}).get("mean"))
            if request_count is not None and request_count > 0 and failure_count is not None:
                values.append(max(0.0, min(100.0, (request_count - failure_count) / request_count * 100.0)))
        metric_summary = summarize(values)
        return metric_summary.get("mean") if metric_summary else "NA"
    if key in RESOURCE_METRIC_MAP:
        for entry in entries:
            values.append(metric_mean(entry, key))
        metric_summary = summarize(values)
        return metric_summary.get("mean") if metric_summary else "NA"
    for entry in entries:
        values.append(metric_mean(entry, key))
    metric_summary = summarize(values)
    return metric_summary.get("mean") if metric_summary else "NA"


def metric_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and value.strip().upper() in {"", "NA", "N/A", "NONE", "NULL"}:
        return False
    return True


def metrics_summary_rows(context: dict[str, Any], family_data: dict[str, dict[str, Any]], profile: dict[str, Any]) -> list[list[Any]]:
    docs = context.get("documents", {})
    metrics_doc = docs.get("minimalObservabilityMetrics") or {}
    metrics_payload = metrics_doc.get("payload")
    rows: list[list[Any]] = []
    client_keys = ["request_count", "success_rate_percent", "failure_count", "mean_response_time_ms", "p50_response_time_ms", "p95_response_time_ms", "p99_response_time_ms", "throughput_rps"]
    cluster_keys = ["max_node_cpu_percent", "max_node_memory_percent", "max_pod_cpu_millicores", "max_pod_memory_mib", "pod_restart_count", "pending_pods_count", "failed_pods_count", "not_ready_pods_count", "kubernetes_events_count", "kubernetes_warning_events_count"]
    if isinstance(metrics_payload, dict):
        client = nested_get(metrics_payload, "clientSide", "metrics", default={})
        cluster = nested_get(metrics_payload, "clusterSide", "metrics", default={})
    else:
        client = {}
        cluster = {}
    pod_level_or_event_keys = {
        "max_pod_cpu_millicores",
        "max_pod_memory_mib",
        "pod_restart_count",
        "pending_pods_count",
        "failed_pods_count",
        "not_ready_pods_count",
        "kubernetes_events_count",
        "kubernetes_warning_events_count",
    }
    for key in client_keys:
        value = client.get(key) if isinstance(client, dict) else None
        if metric_present(value):
            rows.append([key, value, "minimal observability client-side snapshot"])
        else:
            fallback = summary_aggregate_value(family_data, profile, key)
            if metric_present(fallback):
                rows.append([key, fallback, "scenario summary aggregation fallback"])
            else:
                rows.append([key, "not_available", "not_available_in_minimal_observability_or_scenario_summary"])
    for key in cluster_keys:
        value = cluster.get(key) if isinstance(cluster, dict) else None
        if metric_present(value):
            rows.append([key, value, "minimal observability cluster-side snapshot"])
        else:
            fallback = summary_aggregate_value(family_data, profile, key)
            if metric_present(fallback):
                rows.append([key, fallback, "scenario summary aggregation fallback"])
            elif key in pod_level_or_event_keys:
                rows.append([key, "not_available", "not_available_in_minimal_observability_or_scenario_summary"])
            else:
                rows.append([key, "not_available", "not_available_in_minimal_observability_or_scenario_summary"])
    return rows


def summary_row_metric(row: dict[str, Any], metric: str) -> Any:
    return first_non_empty(row.get(metric), row.get(f"{metric}_mean"), "NA")


def summary_row_unsupported_evidence(row: dict[str, Any]) -> str:
    explicit = first_non_empty(row.get("unsupported_evidence"), row.get("unsupported_evidence_kinds"), "")
    if explicit:
        return str(explicit)
    replicas = str(row.get("unsupported_replicas") or "").strip()
    if replicas:
        return f"unsupported reports: {replicas}"
    return "NA"


def scenario_summary_section(profile: dict[str, Any], family_data: dict[str, dict[str, Any]]) -> str:
    rows = []
    for item in build_summary_rows(family_data, profile):
        rows.append([
            item.get("family"),
            item.get("scenario_id"),
            item.get("status"),
            item.get("sample_count"),
            fmt(summary_row_metric(item, "mean_response_time_ms")),
            fmt(summary_row_metric(item, "p95_response_time_ms")),
            fmt(summary_row_metric(item, "throughput_rps"), 4),
            summary_row_unsupported_evidence(item),
        ])
    if not rows:
        rows = [["NA", "NA", "not_available", "NA", "NA", "NA", "NA", "NA"]]
    return md_table(["Family", "Scenario", "Status", "Samples", "Mean ms", "P95 ms", "RPS", "Unsupported evidence"], rows)


def unsupported_summary_section(family_data: dict[str, dict[str, Any]]) -> str:
    rows = []
    for family in sorted(family_data):
        entries = family_data.get(family, {})
        for scenario_id in sorted(entries, key=scenario_sort_key):
            entry = entries[scenario_id]
            status = entry.get("status")
            unsupported_reports = entry.get("unsupportedReports") or []
            unsupported_summary = entry.get("unsupportedSummary") or {}
            if status == "unsupported_under_current_constraints" or unsupported_reports or unsupported_summary:
                evidence_kinds = unsupported_summary.get("evidenceKinds") or sorted({kind for report in unsupported_reports for kind in report.get("evidenceKinds", [])})
                reasons = unsupported_summary.get("reasons") or [report.get("reason") for report in unsupported_reports if report.get("reason")]
                sources = [report.get("unsupportedJsonPath") for report in unsupported_reports if report.get("unsupportedJsonPath")]
                rows.append([
                    family,
                    scenario_id,
                    status or "unsupported_under_current_constraints",
                    compact_list(evidence_kinds) if evidence_kinds else compact_list(reasons) if reasons else "unsupported_scenario_evidence",
                    compact_list(sources, limit=6) if sources else "technical_diagnosis",
                ])
            elif status == "missing":
                rows.append([family, scenario_id, "missing", "missing_measurement_and_unsupported_evidence", "NA"])
    if not rows:
        rows = [["all", "NA", "not_applicable", "No unsupported or missing scenario evidence detected in the current reporting inputs.", "NA"]]
    return md_table(["Family", "Scenario", "Status", "Evidence", "Source"], rows)


def main_findings_section(profile: dict[str, Any], diagnosis_payload: dict[str, Any] | None, family_data: dict[str, dict[str, Any]]) -> str:
    rows = []
    findings = diagnosis_findings_by_family(diagnosis_payload)
    for family, items in findings.items():
        for item in items[:3]:
            rows.append([family, item.get("title") or item.get("id") or item.get("kind"), item.get("status") or "NA", item.get("confidence") or "NA", item.get("implication") or "NA"])
    if not rows:
        for family, entries in family_data.items():
            execution = family_execution_status(entries)
            rows.append([family, "execution_status", execution["status"], "derived", execution["explanation"]])
    return md_table(["Family", "Finding", "Status", "Confidence", "Implication"], rows)


def list_section(values: list[Any], fallback: str) -> str:
    if not values:
        return f"- {fallback}\n"
    return "\n".join(f"- {value}" for value in values) + "\n"


def build_historical_context_markdown_sections(profile: dict[str, Any], baseline: dict[str, Any], family_data: dict[str, dict[str, Any]], diagnosis_payload: dict[str, Any] | None, context: dict[str, Any]) -> str:
    family_order = list(profile.get("familyOrder") or [])
    measured_count = 0
    unsupported_count = 0
    missing_count = 0
    scenario_count = 0
    for family in family_order:
        execution = family_execution_status(family_data.get(family, {}))
        scenario_count += int(execution.get("scenarioCount", 0) or 0)
        measured_count += int(execution.get("measuredCount", 0) or 0)
        unsupported_count += int(execution.get("unsupportedCount", 0) or 0)
        missing_count += int(execution.get("missingCount", 0) or 0)
    diagnosis_profile = ((diagnosis_payload or {}).get("diagnosisProfile") or {}) if isinstance(diagnosis_payload, dict) else {}
    rows = [
        ["Cycle ID", reporting_cycle_id(profile)],
        ["Baseline ID", profile.get("baselineId") or baseline.get("baselineId") or "NA"],
        ["Reporting profile", reporting_profile_id(profile)],
        ["Cycle role", "historical fixed-cluster evidence"],
        ["Benchmark families", compact_list([family_display_name(profile, family) for family in family_order], limit=12)],
        ["Configured scenarios", scenario_count],
        ["Measured scenarios", measured_count],
        ["Unsupported scenarios", unsupported_count],
        ["Missing scenarios", missing_count],
        ["Diagnosis profile", diagnosis_profile.get("profileId") or diagnosis_profile.get("technicalDiagnosisProfileId") or "NA"],
        ["Diagnosis root", profile.get("technicalDiagnosisRoot", "NA")],
        ["Reporting output", profile.get("outputRoot", "NA")],
        ["Request target", profile.get("requestTargetName", "NA")],
    ]
    return "\n".join([
        "## Historical Fixed-Cluster Context",
        "",
        "This cycle preserves fixed-cluster benchmark evidence. Provider-specific sections are intentionally omitted because the cycle is not materialized through a provider-backed infrastructure profile.",
        "",
        md_table(["Field", "Value"], rows),
        "",
        "## Historical Evidence Scope",
        "",
        "The report keeps the historical benchmark families readable and comparable while avoiding provider-oriented fields that do not apply to this cycle.",
        "",
    ])


def build_context_markdown_sections(profile: dict[str, Any], baseline: dict[str, Any], family_data: dict[str, dict[str, Any]], diagnosis_payload: dict[str, Any] | None, context: dict[str, Any]) -> str:
    lines: list[str] = []
    infra_mode = infrastructure_summary_mode(profile, context)
    campaign_based = has_campaign_variants(context) or infra_mode == "variant_scoped"
    if infra_mode == "variant_scoped":
        lines += [
            "## Infrastructure Summary",
            "",
            "This reporting profile uses variant-scoped infrastructure: infrastructure profiles are attached to individual scenarios rather than to one fixed cycle-level cluster shape.",
            "",
            infrastructure_variant_summary_section(context, family_data),
            "",
        ]
    else:
        lines += ["## Infrastructure Summary", "", md_table(["Item", "Value"], infrastructure_summary_rows(context, baseline)), ""]
    if campaign_based:
        lines += [
            "## Provider Summary",
            "",
            "This campaign may resolve provider configuration at scenario or variant level. The table below exposes provider bindings and concrete configuration paths per scenario whenever available.",
            "",
            provider_variant_summary_section(context, family_data),
            "",
        ]
    else:
        lines += ["## Provider Summary", "", md_table(["Item", "Value"], provider_summary_rows(context)), ""]
    lines += ["## Cluster Validation Summary", "", md_table(["Item", "Value"], validation_summary_rows(context)), ""]
    if campaign_based:
        lines += [
            "## Runtime Profile Variant Summary",
            "",
            "This table links each scenario to the runtime-generated profiles used for precheck, application deployment and minimal observability evidence.",
            "",
            runtime_profile_variant_summary_section(context, family_data),
            "",
        ]
        lines += [
            "## Application Topology Summary",
            "",
            "This campaign may vary placement, tenancy, latency profile or generated deployment profiles at scenario level. The table below exposes the scenario-level application topology used by each configured variant.",
            "",
            application_topology_variant_summary_section(context, family_data),
            "",
        ]
    else:
        lines += ["## Application Topology Summary", "", md_table(["Item", "Value"], application_topology_rows(context)), ""]
    lines += ["## Scenario Summary", "", "The following table summarizes the currently available measurement and constraint evidence for all configured reporting families.", "", scenario_summary_section(profile, family_data), ""]
    lines += ["## Metrics Summary", "", "The reporting generator first uses minimal observability metrics when available; missing values are filled from scenario-summary aggregates derived from benchmark CSV files and cluster-capture artifacts whenever possible. Values marked as `not_available` were not derivable from the available artifact set and are intentionally distinguished from measured zero values.", "", md_table(["Metric", "Value", "Source"], metrics_summary_rows(context, family_data, profile)), ""]
    lines += build_scheduler_pairwise_global_section(profile, family_data)
    lines += ["## Unsupported Scenario Summary", "", unsupported_summary_section(family_data), ""]
    lines += ["## Main Findings", "", main_findings_section(profile, diagnosis_payload, family_data), ""]
    return "\n".join(lines).strip() + "\n"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_artifact_payload_for_output(payload, path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def to_number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def safe_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def scenario_sort_key(scenario_id: str) -> tuple[str, int, str]:
    match = re.match(r"([A-Za-z-]+)(\d+)$", scenario_id)
    if match:
        return (match.group(1), int(match.group(2)), scenario_id)
    return (scenario_id, 0, scenario_id)


def parse_replica(stem: str) -> str:
    for pattern in [
        re.compile(r"(?:^|[_-])run([A-Za-z0-9]+)(?:[_-]|$)"),
        re.compile(r"(?:^|[_-])([ABC])(?:[_-])\d{8}T\d{6}Z(?:[_-]|$)"),
        re.compile(r"(?:^|[_-])([ABC])(?:[_-]|$)"),
    ]:
        match = pattern.search(stem)
        if match:
            return match.group(1)
    return "NA"


def find_target_row(stats_csv: Path, target_type: str, target_name: str, fallback: bool) -> tuple[dict[str, str] | None, str | None]:
    with stats_csv.open("r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
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
    return None, None


def measurement_row_request_count(row: dict[str, str] | None) -> int | None:
    if row is None:
        return None
    value = to_number(row.get("Request Count"))
    if value is None:
        return None
    return int(round(value))


def valid_measurement_row(row: dict[str, str] | None, source: str | None) -> bool:
    if source != "target_request":
        return False
    count = measurement_row_request_count(row)
    return count is not None and count > 0


def invalid_measurement_unsupported_report(repo_root: Path, stats_file: Path, scenario_id: str, scenario_payload: dict[str, Any], row: dict[str, str] | None, source: str | None, target_type: str, target_name: str) -> dict[str, Any]:
    replica = parse_replica(stats_file.stem)
    reason = "measurement_missing_target_request_row" if row is None or source != "target_request" else "measurement_produced_zero_valid_requests"
    evidence = {
        "classificationRule": "reporting_rejected_invalid_measurement_csv",
        "failureClass": "measurement_produced_no_valid_target_requests",
        "statsCsvPath": safe_rel(stats_file, repo_root),
        "targetType": target_type,
        "targetName": target_name,
        "rowSource": source,
        "targetRequestCount": measurement_row_request_count(row) or 0,
    }
    return {
        "replica": replica,
        "unsupportedJsonPath": None,
        "status": "unsupported_under_current_constraints",
        "reason": reason,
        "evidence": evidence,
        "evidenceKinds": derive_unsupported_evidence_kinds({"reason": reason, "stage": "measurement_validation", "evidence": evidence}, repo_root),
        "timeoutSeconds": scenario_payload.get("requestTimeoutSeconds"),
        "model": scenario_payload.get("resolvedModelName"),
    }


def discover_measurement_stats(search_root: Path) -> list[Path]:
    if not search_root.exists():
        return []
    files = []
    for stats_file in search_root.rglob("*_stats.csv"):
        lower = stats_file.name.lower()
        if lower.endswith("_stats_history.csv") or "warmup" in lower:
            continue
        files.append(stats_file)
    return sorted(files)


def discover_measurement_stats_for_scenario(results_root: Path, search_roots: list[Path], scenario_id: str) -> list[Path]:
    candidates = [path for root in search_roots for path in discover_measurement_stats(root)]
    if results_root.exists():
        candidates.extend(
            path
            for path in results_root.rglob(f"{scenario_id}_run*_stats.csv")
            if not path.name.lower().endswith("_stats_history.csv") and "warmup" not in path.name.lower()
        )
    return unique_paths(candidates)


def discover_unsupported_reports(search_root: Path) -> list[Path]:
    if not search_root.exists():
        return []
    return sorted(search_root.rglob("*_unsupported.json"))


def discover_unsupported_reports_for_scenario(results_root: Path, search_roots: list[Path], scenario_id: str) -> list[Path]:
    candidates = [path for root in search_roots for path in discover_unsupported_reports(root)]
    if results_root.exists():
        candidates.extend(results_root.rglob(f"{scenario_id}_run*_unsupported.json"))
    return unique_paths(candidates)


def parse_cpu_to_millicores(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"<unknown>", "<none>"}:
        return None
    try:
        if text.endswith("m"):
            return float(text[:-1])
        if text.endswith("n"):
            return float(text[:-1]) / 1_000_000.0
        return float(text) * 1000.0
    except Exception:
        return None


def parse_memory_to_mib(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"<unknown>", "<none>"}:
        return None
    match = re.match(r"^([0-9.]+)([A-Za-z]+)?$", text)
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) or "").lower()
    factors = {"ki": 1 / 1024, "k": 1 / 1024, "mi": 1, "m": 1, "gi": 1024, "g": 1024, "ti": 1024 * 1024, "t": 1024 * 1024}
    return number * factors.get(unit, 1 / (1024 * 1024))


def parse_top_nodes(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"nodes": [], "maxNodeCpuPercent": None, "maxNodeMemoryPercent": None}
    if not path.exists():
        return result
    with path.open("r", encoding="utf-8-sig", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("NAME"):
                continue
            parts = re.split(r"\s+", line)
            if len(parts) < 5:
                continue
            node = {"name": parts[0], "cpuCores": parts[1], "cpuPercent": to_number(parts[2].rstrip("%")), "memoryBytes": parts[3], "memoryPercent": to_number(parts[4].rstrip("%"))}
            result["nodes"].append(node)
            if node["cpuPercent"] is not None:
                result["maxNodeCpuPercent"] = node["cpuPercent"] if result["maxNodeCpuPercent"] is None else max(result["maxNodeCpuPercent"], node["cpuPercent"])
            if node["memoryPercent"] is not None:
                result["maxNodeMemoryPercent"] = node["memoryPercent"] if result["maxNodeMemoryPercent"] is None else max(result["maxNodeMemoryPercent"], node["memoryPercent"])
    return result


def parse_top_pods(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"pods": [], "maxPodCpuMillicores": None, "maxPodMemoryMiB": None, "totalPodCpuMillicores": 0.0, "totalPodMemoryMiB": 0.0}
    if not path.exists():
        return result
    with path.open("r", encoding="utf-8-sig", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("NAME"):
                continue
            parts = re.split(r"\s+", line)
            if len(parts) < 3:
                continue
            cpu_m = parse_cpu_to_millicores(parts[1])
            mem_mib = parse_memory_to_mib(parts[2])
            pod = {"name": parts[0], "cpu": parts[1], "memory": parts[2], "cpuMillicores": cpu_m, "memoryMiB": mem_mib}
            result["pods"].append(pod)
            if cpu_m is not None:
                result["totalPodCpuMillicores"] += cpu_m
                result["maxPodCpuMillicores"] = cpu_m if result["maxPodCpuMillicores"] is None else max(result["maxPodCpuMillicores"], cpu_m)
            if mem_mib is not None:
                result["totalPodMemoryMiB"] += mem_mib
                result["maxPodMemoryMiB"] = mem_mib if result["maxPodMemoryMiB"] is None else max(result["maxPodMemoryMiB"], mem_mib)
    result["totalPodCpuMillicores"] = round(result["totalPodCpuMillicores"], 4)
    result["totalPodMemoryMiB"] = round(result["totalPodMemoryMiB"], 4)
    return result


def parse_pods_wide(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "pods": [],
        "placementByPod": {},
        "nodeCounts": defaultdict(int),
        "restartCount": 0,
        "pendingPodsCount": 0,
        "failedPodsCount": 0,
        "notReadyPodsCount": 0,
    }
    if not path.exists():
        result["nodeCounts"] = dict(result["nodeCounts"])
        return result
    with path.open("r", encoding="utf-8-sig", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("NAME"):
                continue
            parts = re.split(r"\s+", line)
            if len(parts) < 7:
                continue
            restart_count = int(to_number(parts[3]) or 0)
            ready_text = parts[1]
            ready = False
            ready_match = re.match(r"^(\d+)/(\d+)$", ready_text)
            if ready_match:
                ready = ready_match.group(1) == ready_match.group(2)
            status = parts[2]
            pod = {"name": parts[0], "ready": ready_text, "status": status, "restarts": parts[3], "age": parts[4], "ip": parts[5], "node": parts[6]}
            result["pods"].append(pod)
            result["placementByPod"][parts[0]] = parts[6]
            result["nodeCounts"][parts[6]] += 1
            result["restartCount"] += restart_count
            if status == "Pending":
                result["pendingPodsCount"] += 1
            if status in {"Failed", "Error", "CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"}:
                result["failedPodsCount"] += 1
            if not ready:
                result["notReadyPodsCount"] += 1
    result["nodeCounts"] = dict(result["nodeCounts"])
    return result


def parse_kubernetes_events(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"eventsCount": 0, "warningEventsCount": 0}
    if not path.exists():
        return result
    try:
        payload = load_json(path)
        if isinstance(payload, dict):
            items = payload.get("items") if isinstance(payload.get("items"), list) else []
            result["eventsCount"] = len(items)
            for item in items:
                event_type = str(item.get("type") or item.get("eventType") or "").lower() if isinstance(item, dict) else ""
                if event_type == "warning":
                    result["warningEventsCount"] += 1
            return result
    except Exception:
        pass
    with path.open("r", encoding="utf-8-sig", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("LAST SEEN") or line.startswith("NAMESPACE"):
                continue
            result["eventsCount"] += 1
            if re.search(r"\bWarning\b", line, flags=re.IGNORECASE):
                result["warningEventsCount"] += 1
    return result


def cluster_artifact_source_candidates(stats_file: Path, phase: str = "post") -> list[dict[str, Path]]:
    candidates: list[dict[str, Path]] = []
    stats_file = Path(stats_file)
    if str(stats_file).endswith("_stats.csv"):
        legacy_prefix = Path(str(stats_file)[:-len("_stats.csv")])
        candidates.append(
            {
                "topNodes": Path(str(legacy_prefix) + f"_cluster_{phase}_top-nodes.txt"),
                "topPods": Path(str(legacy_prefix) + f"_cluster_{phase}_top-pods.txt"),
                "podsWide": Path(str(legacy_prefix) + f"_cluster_{phase}_pods-wide.txt"),
                "eventsJson": Path(str(legacy_prefix) + f"_cluster_{phase}_events.json"),
                "eventsText": Path(str(legacy_prefix) + f"_cluster_{phase}_events.txt"),
            }
        )

    for ancestor in [stats_file.parent, *stats_file.parents]:
        candidates.append(
            {
                "topNodes": ancestor / f"cluster_{phase}_top-nodes.txt",
                "topPods": ancestor / f"cluster_{phase}_top-pods.txt",
                "podsWide": ancestor / f"cluster_{phase}_pods-wide.txt",
                "eventsJson": ancestor / f"cluster_{phase}_events.json",
                "eventsText": ancestor / f"cluster_{phase}_events.txt",
            }
        )

    unique: list[dict[str, Path]] = []
    seen: set[tuple[str, ...]] = set()
    for item in candidates:
        key = tuple(str(item[name]) for name in sorted(item))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def resolve_cluster_artifact_source(stats_file: Path, phase: str = "post") -> dict[str, Path] | None:
    for candidate in cluster_artifact_source_candidates(stats_file, phase=phase):
        if any(path.exists() for path in candidate.values()):
            return candidate
    return None


def cluster_side_metrics_from_artifact_source(source: dict[str, Path] | None, repo_root: Path | None = None) -> dict[str, Any]:
    if not source:
        return {}
    top_nodes = parse_top_nodes(source.get("topNodes", Path("__missing__")))
    top_pods = parse_top_pods(source.get("topPods", Path("__missing__")))
    pods_wide = parse_pods_wide(source.get("podsWide", Path("__missing__")))
    events = parse_kubernetes_events(source.get("eventsJson", Path("__missing__")))
    if events.get("eventsCount") == 0:
        events = parse_kubernetes_events(source.get("eventsText", Path("__missing__")))

    metrics: dict[str, Any] = {
        "maxNodeCpuPercent": top_nodes.get("maxNodeCpuPercent"),
        "maxNodeMemoryPercent": top_nodes.get("maxNodeMemoryPercent"),
        "maxPodCpuMillicores": top_pods.get("maxPodCpuMillicores"),
        "maxPodMemoryMiB": top_pods.get("maxPodMemoryMiB"),
        "totalPodCpuMillicores": top_pods.get("totalPodCpuMillicores"),
        "totalPodMemoryMiB": top_pods.get("totalPodMemoryMiB"),
        "podRestartCount": pods_wide.get("restartCount"),
        "pendingPodsCount": pods_wide.get("pendingPodsCount"),
        "failedPodsCount": pods_wide.get("failedPodsCount"),
        "notReadyPodsCount": pods_wide.get("notReadyPodsCount"),
        "kubernetesEventsCount": events.get("eventsCount"),
        "kubernetesWarningEventsCount": events.get("warningEventsCount"),
        "nodeCounts": pods_wide.get("nodeCounts"),
    }
    if repo_root is not None:
        metrics.update(
            {
                "clusterTopNodesPath": safe_rel(source.get("topNodes"), repo_root),
                "clusterTopPodsPath": safe_rel(source.get("topPods"), repo_root),
                "clusterPodsWidePath": safe_rel(source.get("podsWide"), repo_root),
                "clusterEventsPath": safe_rel(source.get("eventsJson"), repo_root) if source.get("eventsJson") and source.get("eventsJson").exists() else safe_rel(source.get("eventsText"), repo_root),
            }
        )
    return metrics


def cluster_side_metrics_from_stats_file(stats_file: Path | None, repo_root: Path | None = None, phase: str = "post") -> dict[str, Any]:
    if stats_file is None:
        return {}
    source = resolve_cluster_artifact_source(stats_file, phase=phase)
    return cluster_side_metrics_from_artifact_source(source, repo_root=repo_root)


def derive_unsupported_evidence_kinds(payload: dict[str, Any], repo_root: Path | None = None) -> list[str]:
    evidence_kinds: set[str] = set()
    raw_evidence = payload.get("evidence")
    for token in text_tokens_from_any(raw_evidence):
        evidence_kinds.update(classify_evidence_text(token))
        if is_compact_evidence_token(token):
            evidence_kinds.add(token.strip())
    if payload.get("reason"):
        evidence_kinds.update(classify_evidence_text(payload.get("reason")))
    if payload.get("stage"):
        evidence_kinds.add(str(payload.get("stage")).strip())
    for diagnostic in payload.get("diagnostics") or []:
        phase = (diagnostic.get("phase") or "").strip()
        reason = (diagnostic.get("reason") or "").strip()
        if phase == "Pending":
            evidence_kinds.add("pending_pod")
        if reason:
            evidence_kinds.add(reason.lower().replace(" ", "_"))
            evidence_kinds.update(classify_evidence_text(reason))
        for event in diagnostic.get("events") or []:
            evidence_kinds.update(classify_evidence_text(event))
    if repo_root is not None:
        _manifest_path, manifest = read_related_deployment_manifest(repo_root, payload)
        for token in deployment_manifest_event_texts(repo_root, manifest):
            evidence_kinds.update(classify_evidence_text(token))
    return sorted(kind for kind in evidence_kinds if kind)


def parse_scenario_and_replica_from_unsupported(path: Path) -> tuple[str | None, str]:
    match = re.match(r"(?P<scenario>.+)_run(?P<replica>[A-Za-z0-9]+)_unsupported$", path.stem)
    if not match:
        return None, "NA"
    return match.group("scenario"), match.group("replica")


def scenario_identifier(payload: dict[str, Any], fallback: str) -> str:
    return payload.get("scenarioId") or payload.get("baselineId") or fallback


def scenario_label(family: str, scenario_id: str, scenario: dict[str, Any]) -> str:
    if family == "baseline":
        return f"{scenario_id} ({scenario.get('purpose', 'baseline')})"
    if family == "worker-count":
        return f"{scenario_id} ({scenario.get('workerCount', 'NA')} worker)"
    if family == "workload":
        return f"{scenario_id} ({scenario.get('users', 'NA')} users, spawn {scenario.get('spawnRate', 'NA')})"
    if family == "models":
        model = str(scenario.get("modelName", "model"))
        return f"{scenario_id} ({model})"
    if family == "placement":
        return f"{scenario_id} ({scenario.get('placementType', 'placement')})"
    if family == "resource-variation":
        variant = scenario.get("resourceVariant") or {}
        cpu = variant.get("workerVcpusPerNode", "NA")
        memory = variant.get("workerMemoryGiBPerNode", "NA")
        return f"{scenario_id} ({cpu} vCPU / {memory} GiB per worker)"
    if family == "node-count-variation":
        variant = scenario.get("nodeCountVariant") or {}
        worker_nodes = variant.get("workerNodeCount", scenario.get("infrastructureWorkerNodeCount", "NA"))
        localai_workers = scenario.get("resolvedWorkerCount", variant.get("fixedLocalAiWorkerCount", "NA"))
        return f"{scenario_id} ({worker_nodes} provider worker nodes / W{localai_workers})"
    if family == "placement-variation":
        variant = scenario.get("placementVariant") or {}
        label = variant.get("label", scenario.get("resolvedPlacementType", "placement"))
        return f"{scenario_id} ({label})"
    if family == "latency-injection":
        variant = scenario.get("latencyVariant") or {}
        delay = variant.get("delayMs", "NA")
        jitter = variant.get("jitterMs", 0)
        return f"{scenario_id} ({delay} ms, jitter {jitter} ms)"
    if family == "resource-aware-scheduler":
        logical_id = scenario.get("logicalScenarioId") or (scenario.get("schedulerModePolicy") or {}).get("logicalScenarioId") or scenario_id
        role = scenario.get("schedulerModeRole") or (scenario.get("schedulerModePolicy") or {}).get("schedulerModeRole") or "scheduler"
        return f"{scenario_id} ({logical_id}, {role})"
    if family == "network-aware-scheduler":
        policy = scenario.get("networkAwareSchedulerPolicy") or scenario.get("schedulerModePolicy") or {}
        logical_id = scenario.get("logicalScenarioId") or policy.get("logicalScenarioId") or scenario_id
        mode = policy.get("schedulerMode") or scenario.get("schedulerMode") or "scheduler"
        return f"{scenario_id} ({logical_id}, {mode})"
    return scenario_id


def summarize(values: list[float | None]) -> dict[str, float] | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    avg = mean(clean)
    std = pstdev(clean) if len(clean) > 1 else 0.0
    return {"mean": round(avg, 4), "min": round(min(clean), 4), "max": round(max(clean), 4), "stddev": round(std, 4), "coefficientOfVariationPercent": round((std / avg * 100.0) if avg else 0.0, 4)}


def summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not samples:
        return None
    summary: dict[str, Any] = {"sampleCount": len(samples), "replicas": [s["replica"] for s in samples], "metrics": {}, "clusterSideSnapshots": {}}
    for metric in METRIC_KEYS:
        metric_summary = summarize([s.get(metric) for s in samples])
        if metric_summary:
            summary["metrics"][metric] = metric_summary
    for field in [
        "maxNodeCpuPercent",
        "maxNodeMemoryPercent",
        "maxPodCpuMillicores",
        "maxPodMemoryMiB",
        "totalPodCpuMillicores",
        "totalPodMemoryMiB",
        "podRestartCount",
        "pendingPodsCount",
        "failedPodsCount",
        "notReadyPodsCount",
        "kubernetesEventsCount",
        "kubernetesWarningEventsCount",
    ]:
        metric_summary = summarize([s.get(field) for s in samples])
        if metric_summary:
            summary["clusterSideSnapshots"][field] = metric_summary
    node_counts = defaultdict(int)
    for sample in samples:
        for node, count in (sample.get("nodeCounts") or {}).items():
            node_counts[node] += count
    if node_counts:
        summary["observedPlacementNodeCounts"] = dict(sorted(node_counts.items()))
    return summary


def discover_latest_diagnosis(repo_root: Path, diagnosis_root: Path, family_scope: str = "all") -> dict[str, Any] | None:
    root = diagnosis_root if diagnosis_root.is_absolute() else repo_root / diagnosis_root
    if not root.exists():
        return None
    candidates = sorted(root.glob("*_diagnosis.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            payload = load_json(path)
        except Exception:
            continue
        if payload.get("diagnosis", {}).get("familyScope") == family_scope:
            return {"path": safe_rel(path, repo_root), "payload": payload}
    return None


def configured_scenario_files(repo_root: Path, profile: dict[str, Any], family: str, scenario_root: Path) -> list[Path]:
    explicit_files = (profile.get("scenarioConfigFiles") or {}).get(family) or []
    files = []
    for item in explicit_files:
        path = Path(item)
        files.append(path if path.is_absolute() else repo_root / path)
    if files:
        return files
    if scenario_root.exists():
        return sorted(scenario_root.glob("*.json"), key=lambda p: scenario_sort_key(p.stem))
    return []


def scenario_result_roots(results_root: Path, scenario_id: str, scenario_payload: dict[str, Any]) -> list[Path]:
    candidates: list[Path] = []
    for key in ("outputSubdir", "benchmarkOutputSubdir"):
        value = scenario_payload.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(results_root / value.strip())
    for value in scenario_payload.get("alternativeOutputSubdirs") or []:
        if isinstance(value, str) and value.strip():
            candidates.append(results_root / value.strip())
    candidates.append(results_root / f"{scenario_id}_official_locked")

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def unique_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def campaign_results_roots(profile: dict[str, Any]) -> dict[str, str]:
    roots = profile.get("campaignResultsRoots")
    if isinstance(roots, dict):
        return roots
    return {}


def campaign_results_root(repo_root: Path, profile: dict[str, Any], family: str) -> Path:
    roots = campaign_results_roots(profile)
    if family not in roots:
        raise KeyError(f"No benchmark results root declared for family '{family}'. Expected campaignResultsRoots[{family!r}].")
    return repo_root / roots[family]


def resolve_request_target(profile: dict[str, Any], diagnosis_payload: dict[str, Any] | None) -> tuple[str, str, bool]:
    diagnosis_profile = (diagnosis_payload or {}).get("diagnosisProfile") if isinstance(diagnosis_payload, dict) else {}
    if not isinstance(diagnosis_profile, dict):
        diagnosis_profile = {}

    request_target_type = (
        profile.get("requestTargetType")
        or diagnosis_profile.get("requestTargetType")
        or "POST"
    )
    request_target_name = (
        profile.get("requestTargetName")
        or diagnosis_profile.get("requestTargetName")
        or "POST /v1/chat/completions"
    )

    if "fallbackToAggregated" in profile:
        fallback_to_aggregated = bool(profile.get("fallbackToAggregated"))
    elif "fallbackToAggregated" in diagnosis_profile:
        fallback_to_aggregated = bool(diagnosis_profile.get("fallbackToAggregated"))
    else:
        fallback_to_aggregated = False

    return str(request_target_type), str(request_target_name), fallback_to_aggregated


def discover_family(repo_root: Path, profile: dict[str, Any], family: str, diagnosis_payload: dict[str, Any] | None) -> dict[str, Any]:
    scenario_root = repo_root / profile["scenarioConfigRoots"][family]
    results_root = campaign_results_root(repo_root, profile, family)
    diagnosis_family = ((diagnosis_payload or {}).get("familyData") or {}).get(family) or {}
    scenario_configs = {}
    for path in configured_scenario_files(repo_root, profile, family, scenario_root):
        if not path.exists():
            continue
        payload = load_json(path)
        scenario_configs[scenario_identifier(payload, path.stem)] = {"configPath": path, "data": payload}
    for scenario_id, diag_entry in diagnosis_family.items():
        if scenario_id not in scenario_configs:
            scenario_configs[scenario_id] = {"configPath": None, "data": diag_entry.get("scenario") or {"scenarioId": scenario_id}}

    entries = {}
    for scenario_id, scenario_info in scenario_configs.items():
        scenario = scenario_info["data"]
        search_roots = scenario_result_roots(results_root, scenario_id, scenario)
        search_root = search_roots[0] if search_roots else results_root
        stats_files = discover_measurement_stats_for_scenario(results_root, search_roots, scenario_id)
        unsupported_files = discover_unsupported_reports_for_scenario(results_root, search_roots, scenario_id)
        samples = []
        invalid_measurement_reports = []
        request_target_type, request_target_name, fallback_to_aggregated = resolve_request_target(profile, diagnosis_payload)
        for stats_file in stats_files:
            row, source = find_target_row(stats_file, request_target_type, request_target_name, fallback_to_aggregated)
            if not valid_measurement_row(row, source):
                if family == "latency-injection":
                    invalid_measurement_reports.append(invalid_measurement_unsupported_report(repo_root, stats_file, scenario_id, scenario, row, source, request_target_type, request_target_name))
                continue
            sample: dict[str, Any] = {
                "replica": parse_replica(stats_file.stem),
                "statsCsvPath": safe_rel(stats_file, repo_root),
                "rowSource": source,
            }
            for metric_key, csv_field in CSV_FIELD_MAP.items():
                value = to_number(row.get(csv_field))
                sample[metric_key] = int(round(value)) if value is not None and metric_key in {"request_count", "failure_count"} else (round(value, 4) if value is not None else None)
            sample.update(cluster_side_metrics_from_stats_file(stats_file, repo_root=repo_root, phase="post"))
            samples.append(sample)

        unsupported = []
        for unsupported_file in unsupported_files:
            report_scenario_id, replica = parse_scenario_and_replica_from_unsupported(unsupported_file)
            if report_scenario_id != scenario_id:
                continue
            payload = load_json(unsupported_file)
            unsupported.append({
                "replica": replica,
                "unsupportedJsonPath": safe_rel(unsupported_file, repo_root),
                "status": payload.get("status"),
                "reason": payload.get("reason"),
                "evidence": payload.get("evidence"),
                "evidenceKinds": derive_unsupported_evidence_kinds(payload, repo_root),
                "timeoutSeconds": payload.get("timeoutSeconds"),
                "model": payload.get("model"),
            })

        unsupported.extend(invalid_measurement_reports)

        scheduler_runtime_artifacts: dict[str, Any] = {}
        if family in {"default-scheduler", "resource-aware-scheduler", "network-aware-scheduler"}:
            scheduler_runtime_artifacts = default_scheduler_artifacts_for_scenario(
                repo_root=repo_root,
                profile=profile,
                scenario_id=scenario_id,
                scenario=scenario,
                results_root=results_root,
                search_roots=search_roots,
            )
            multi_tenant_samples = default_scheduler_samples_from_multi_tenant_summary(
                scheduler_runtime_artifacts.get("multiTenantSummary") or {},
                repo_root=repo_root,
            )
            if multi_tenant_samples:
                samples = multi_tenant_samples

        diag_entry = diagnosis_family.get(scenario_id) or {}
        csv_summary = summarize_samples(samples)
        diagnosis_summary = diag_entry.get("summary")
        unsupported_summary = None
        if unsupported:
            unsupported_summary = {"unsupportedReplicaCount": len(unsupported), "replicas": [item["replica"] for item in unsupported], "evidenceKinds": sorted({kind for item in unsupported for kind in item.get("evidenceKinds", [])}), "reasons": [item["reason"] for item in unsupported if item.get("reason")]}
        elif diag_entry.get("unsupportedSummary"):
            unsupported_summary = diag_entry.get("unsupportedSummary")

        if csv_summary:
            summary_source = "measurement_csv"
            summary = csv_summary
            status = "measured"
        elif unsupported_summary:
            summary_source = "none"
            summary = None
            status = "unsupported_under_current_constraints"
        elif diagnosis_summary:
            summary_source = "technical_diagnosis"
            summary = diagnosis_summary
            status = "measured" if diagnosis_summary.get("sampleCount") else "missing"
        else:
            summary_source = "none"
            summary = None
            status = "missing"

        topology = scenario_application_topology(scenario)
        tenancy_profile_path = first_non_empty(
            scenario.get("tenancyProfilePath"),
            topology.get("tenancyProfilePath"),
        )
        tenancy_profile_doc = load_optional_json(repo_root, tenancy_profile_path) if tenancy_profile_path else {"payload": None}
        tenancy_profile_payload = tenancy_profile_doc.get("payload") if isinstance(tenancy_profile_doc, dict) else None
        if not isinstance(tenancy_profile_payload, dict):
            tenancy_profile_payload = {}

        latency_profile_path = first_non_empty(
            scenario.get("latencyProfilePath"),
            topology.get("latencyProfilePath"),
        )
        latency_profile_doc = load_optional_json(repo_root, latency_profile_path) if latency_profile_path else {"payload": None}
        latency_profile_payload = latency_profile_doc.get("payload") if isinstance(latency_profile_doc, dict) else None
        if not isinstance(latency_profile_payload, dict):
            latency_profile_payload = {}

        entries[scenario_id] = {
            "family": family,
            "scenarioId": scenario_id,
            "label": scenario_label(family, scenario_id, scenario),
            "scenario": scenario,
            "scenarioConfigPath": safe_rel(scenario_info["configPath"], repo_root) if scenario_info.get("configPath") else None,
            "searchRoot": safe_rel(search_root, repo_root),
            "searchRoots": [safe_rel(root, repo_root) for root in search_roots],
            "status": status,
            "samples": samples,
            "summary": summary,
            "summarySource": summary_source,
            "diagnosisScenarioSummary": diagnosis_summary,
            "unsupportedReports": unsupported or diag_entry.get("unsupportedReports") or [],
            "unsupportedSummary": unsupported_summary,
            "tenancyProfilePath": safe_rel(resolve_artifact_path(repo_root, tenancy_profile_path), repo_root) if tenancy_profile_path else None,
            "tenancyProfile": tenancy_profile_payload,
            "latencyProfilePath": safe_rel(resolve_artifact_path(repo_root, latency_profile_path), repo_root) if latency_profile_path else None,
            "latencyProfile": latency_profile_payload,
            "defaultSchedulerArtifacts": scheduler_runtime_artifacts,
        }
    return entries


def metric_mean(entry: dict[str, Any], metric: str) -> float | None:
    summary = entry.get("summary") or {}
    if metric in RESOURCE_METRIC_MAP:
        group, key = RESOURCE_METRIC_MAP[metric]
        if group == "clusterSideSnapshots":
            return (summary.get(group) or {}).get(key, {}).get("mean")
        return None
    return (summary.get("metrics") or {}).get(metric, {}).get("mean")


def pct_delta(reference: float | None, candidate: float | None) -> float | None:
    if reference in (None, 0) or candidate is None:
        return None
    return ((candidate - reference) / reference) * 100.0


def resource_aware_scheduler_role(entry: dict[str, Any], scenario_id: str) -> str:
    scenario = entry.get("scenario") if isinstance(entry.get("scenario"), dict) else {}
    policy = scenario.get("networkAwareSchedulerPolicy") if isinstance(scenario.get("networkAwareSchedulerPolicy"), dict) else {}
    if not policy:
        policy = scenario.get("schedulerModePolicy") if isinstance(scenario.get("schedulerModePolicy"), dict) else {}
    role = scenario.get("schedulerModeRole") or scenario.get("schedulerModeRole") or policy.get("schedulerModeRole")
    if role:
        text = str(role).lower()
        if "network" in text or "netaware" in text:
            return "netaware"
        if "load" in text:
            return "loadaware"
        if "default" in text or "kubernetes" in text:
            return "default"
        return text
    mode = str(policy.get("schedulerMode") or scenario.get("schedulerMode") or "").lower()
    if "network" in mode:
        return "netaware"
    if "load" in mode:
        return "loadaware"
    if "default" in mode or "kubernetes" in mode:
        return "default"
    variant_id = str(scenario.get("variantId") or scenario.get("experimentalVariantId") or scenario_id)
    if variant_id.startswith("NA_NETAWARE_") or scenario_id.startswith("NA_NETAWARE_"):
        return "netaware"
    if variant_id.startswith("NA_LOADAWARE_") or scenario_id.startswith("NA_LOADAWARE_") or variant_id.startswith("RA_LOADAWARE_") or scenario_id.startswith("RA_LOADAWARE_"):
        return "loadaware"
    if variant_id.startswith("NA_DEFAULT_") or scenario_id.startswith("NA_DEFAULT_") or variant_id.startswith("RA_DEFAULT_") or scenario_id.startswith("RA_DEFAULT_"):
        return "default"
    return "unknown"


def resource_aware_scheduler_logical_id(entry: dict[str, Any], scenario_id: str) -> str:
    scenario = entry.get("scenario") if isinstance(entry.get("scenario"), dict) else {}
    policy = scenario.get("networkAwareSchedulerPolicy") if isinstance(scenario.get("networkAwareSchedulerPolicy"), dict) else {}
    if not policy:
        policy = scenario.get("schedulerModePolicy") if isinstance(scenario.get("schedulerModePolicy"), dict) else {}
    value = scenario.get("logicalScenarioId") or policy.get("logicalScenarioId")
    if value:
        return str(value)
    for prefix in ["NA_DEFAULT_", "NA_LOADAWARE_", "NA_NETAWARE_", "RA_DEFAULT_", "RA_LOADAWARE_"]:
        if scenario_id.startswith(prefix):
            return scenario_id[len(prefix):]
    return scenario_id


def scheduler_pairwise_entries(entries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, tuple[str, dict[str, Any]]]] = defaultdict(dict)
    for scenario_id, entry in entries.items():
        logical_id = resource_aware_scheduler_logical_id(entry, scenario_id)
        role = resource_aware_scheduler_role(entry, scenario_id)
        grouped[logical_id][role] = (scenario_id, entry)

    rows: list[dict[str, Any]] = []
    for logical_id, roles in sorted(grouped.items()):
        default_item = roles.get("default")
        loadaware_item = roles.get("loadaware")
        default_entry = default_item[1] if default_item else {}
        loadaware_entry = loadaware_item[1] if loadaware_item else {}
        default_mean = metric_mean(default_entry, "mean_response_time_ms") if default_item else None
        custom_mean = metric_mean(loadaware_entry, "mean_response_time_ms") if loadaware_item else None
        default_p95 = metric_mean(default_entry, "p95_response_time_ms") if default_item else None
        custom_p95 = metric_mean(loadaware_entry, "p95_response_time_ms") if loadaware_item else None
        default_throughput = metric_mean(default_entry, "throughput_rps") if default_item else None
        custom_throughput = metric_mean(loadaware_entry, "throughput_rps") if loadaware_item else None
        default_failures = metric_mean(default_entry, "failure_count") if default_item else None
        custom_failures = metric_mean(loadaware_entry, "failure_count") if loadaware_item else None
        default_cpu = metric_mean(default_entry, "max_node_cpu_percent") if default_item else None
        custom_cpu = metric_mean(loadaware_entry, "max_node_cpu_percent") if loadaware_item else None
        default_memory = metric_mean(default_entry, "max_node_memory_percent") if default_item else None
        custom_memory = metric_mean(loadaware_entry, "max_node_memory_percent") if loadaware_item else None
        latency_delta = pct_delta(default_mean, custom_mean)
        p95_delta = pct_delta(default_p95, custom_p95)
        throughput_delta = pct_delta(default_throughput, custom_throughput)
        if not default_item or not loadaware_item:
            interpretation = "incomplete_pair"
        elif not default_entry.get("summary") or not loadaware_entry.get("summary"):
            interpretation = "insufficient_measured_evidence"
        elif latency_delta is None:
            interpretation = "measured_pair_without_latency_delta"
        elif latency_delta <= -5.0:
            interpretation = "loadaware_lower_mean_latency"
        elif latency_delta >= 5.0:
            interpretation = "loadaware_higher_mean_latency"
        else:
            interpretation = "mean_latency_neutral"
        rows.append({
            "logicalScenarioId": logical_id,
            "defaultScenarioId": default_item[0] if default_item else None,
            "loadAwareScenarioId": loadaware_item[0] if loadaware_item else None,
            "defaultVariantId": (default_entry.get("scenario") or {}).get("variantId") if default_item else None,
            "loadAwareVariantId": (loadaware_entry.get("scenario") or {}).get("variantId") if loadaware_item else None,
            "defaultStatus": default_entry.get("status") if default_item else "missing",
            "loadAwareStatus": loadaware_entry.get("status") if loadaware_item else "missing",
            "defaultMeanLatencyMs": default_mean,
            "loadAwareMeanLatencyMs": custom_mean,
            "meanLatencyDeltaPercent": latency_delta,
            "defaultP95LatencyMs": default_p95,
            "loadAwareP95LatencyMs": custom_p95,
            "p95LatencyDeltaPercent": p95_delta,
            "defaultThroughputRps": default_throughput,
            "loadAwareThroughputRps": custom_throughput,
            "throughputDeltaPercent": throughput_delta,
            "defaultFailureCount": default_failures,
            "loadAwareFailureCount": custom_failures,
            "defaultMaxNodeCpuPercent": default_cpu,
            "loadAwareMaxNodeCpuPercent": custom_cpu,
            "defaultMaxNodeMemoryPercent": default_memory,
            "loadAwareMaxNodeMemoryPercent": custom_memory,
            "interpretation": interpretation,
        })
    return rows


def network_aware_triplet_entries(entries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, tuple[str, dict[str, Any]]]] = defaultdict(dict)
    for scenario_id, entry in entries.items():
        logical_id = resource_aware_scheduler_logical_id(entry, scenario_id)
        role = resource_aware_scheduler_role(entry, scenario_id)
        grouped[logical_id][role] = (scenario_id, entry)
    rows: list[dict[str, Any]] = []
    for logical_id, roles in sorted(grouped.items()):
        items = {role: roles.get(role) for role in ["default", "loadaware", "netaware"]}
        entries_by_role = {role: item[1] if item else {} for role, item in items.items()}
        means = {role: metric_mean(entry, "mean_response_time_ms") if items[role] else None for role, entry in entries_by_role.items()}
        p95 = {role: metric_mean(entry, "p95_response_time_ms") if items[role] else None for role, entry in entries_by_role.items()}
        rps = {role: metric_mean(entry, "throughput_rps") if items[role] else None for role, entry in entries_by_role.items()}
        telemetry = ((entries_by_role.get("netaware") or {}).get("defaultSchedulerArtifacts") or {}).get("schedulerDecisionEvidence", {})
        if not telemetry:
            telemetry = (entries_by_role.get("netaware") or {}).get("schedulerDecisionEvidence") or {}
        network_telemetry = telemetry.get("networkAwareTelemetryEvidence") if isinstance(telemetry, dict) else None
        cluster_lens = network_telemetry.get("clusterLensPlacementEvidence") if isinstance(network_telemetry, dict) and isinstance(network_telemetry.get("clusterLensPlacementEvidence"), dict) else {}
        net_vs_default = pct_delta(means.get("default"), means.get("netaware"))
        net_vs_load = pct_delta(means.get("loadaware"), means.get("netaware"))
        if not all(items.values()):
            interpretation = "incomplete_triplet"
        elif not all((entries_by_role[role].get("summary") for role in ["default", "loadaware", "netaware"])):
            interpretation = "insufficient_measured_evidence"
        elif net_vs_load is not None and net_vs_load <= -5.0:
            interpretation = "netaware_lower_mean_latency_than_loadaware"
        elif net_vs_default is not None and net_vs_default <= -5.0:
            interpretation = "netaware_lower_mean_latency_than_default"
        elif (net_vs_load is not None and net_vs_load >= 5.0) or (net_vs_default is not None and net_vs_default >= 5.0):
            interpretation = "netaware_higher_mean_latency"
        else:
            interpretation = "mean_latency_neutral_or_mixed"
        rows.append({
            "logicalScenarioId": logical_id,
            "defaultVariantId": (entries_by_role["default"].get("scenario") or {}).get("variantId") if items["default"] else None,
            "loadAwareVariantId": (entries_by_role["loadaware"].get("scenario") or {}).get("variantId") if items["loadaware"] else None,
            "networkAwareVariantId": (entries_by_role["netaware"].get("scenario") or {}).get("variantId") if items["netaware"] else None,
            "defaultStatus": entries_by_role["default"].get("status") if items["default"] else "missing",
            "loadAwareStatus": entries_by_role["loadaware"].get("status") if items["loadaware"] else "missing",
            "networkAwareStatus": entries_by_role["netaware"].get("status") if items["netaware"] else "missing",
            "defaultMeanLatencyMs": means.get("default"),
            "loadAwareMeanLatencyMs": means.get("loadaware"),
            "networkAwareMeanLatencyMs": means.get("netaware"),
            "networkAwareVsDefaultMeanLatencyDeltaPercent": net_vs_default,
            "networkAwareVsLoadAwareMeanLatencyDeltaPercent": net_vs_load,
            "defaultP95LatencyMs": p95.get("default"),
            "loadAwareP95LatencyMs": p95.get("loadaware"),
            "networkAwareP95LatencyMs": p95.get("netaware"),
            "defaultThroughputRps": rps.get("default"),
            "loadAwareThroughputRps": rps.get("loadaware"),
            "networkAwareThroughputRps": rps.get("netaware"),
            "networkAwareTelemetryStatus": network_telemetry.get("status") if isinstance(network_telemetry, dict) else None,
            "networkAwarePlacementEvidenceStatus": cluster_lens.get("status"),
            "networkAwarePlacementLocalAiPodCount": cluster_lens.get("localAiPodCount"),
            "interpretation": interpretation,
        })
    return rows


def build_network_aware_triplet_table(entries: dict[str, dict[str, Any]]) -> str:
    rows = []
    for item in network_aware_triplet_entries(entries):
        rows.append([
            f"`{item['logicalScenarioId']}`",
            f"`{item.get('defaultVariantId') or 'missing'}`",
            f"`{item.get('loadAwareVariantId') or 'missing'}`",
            f"`{item.get('networkAwareVariantId') or 'missing'}`",
            item.get("defaultStatus"),
            item.get("loadAwareStatus"),
            item.get("networkAwareStatus"),
            fmt(item.get("defaultMeanLatencyMs")),
            fmt(item.get("loadAwareMeanLatencyMs")),
            fmt(item.get("networkAwareMeanLatencyMs")),
            fmt(item.get("networkAwareVsDefaultMeanLatencyDeltaPercent")),
            fmt(item.get("networkAwareVsLoadAwareMeanLatencyDeltaPercent")),
            fmt(item.get("defaultP95LatencyMs")),
            fmt(item.get("loadAwareP95LatencyMs")),
            fmt(item.get("networkAwareP95LatencyMs")),
            fmt(item.get("defaultThroughputRps"), 4),
            fmt(item.get("loadAwareThroughputRps"), 4),
            fmt(item.get("networkAwareThroughputRps"), 4),
            item.get("networkAwareTelemetryStatus") or "n/a",
            item.get("networkAwarePlacementEvidenceStatus") or "n/a",
            item.get("networkAwarePlacementLocalAiPodCount") if item.get("networkAwarePlacementLocalAiPodCount") is not None else "n/a",
            item.get("interpretation"),
        ])
    if not rows:
        return "No network-aware scheduler triplet evidence is available yet."
    return md_table([
        "Logical scenario",
        "Default variant",
        "Load-aware variant",
        "Network-aware variant",
        "Default status",
        "Load-aware status",
        "Network-aware status",
        "Mean default",
        "Mean load-aware",
        "Mean network-aware",
        "Network-aware vs default %",
        "Network-aware vs load-aware %",
        "P95 default",
        "P95 load-aware",
        "P95 network-aware",
        "RPS default",
        "RPS load-aware",
        "RPS network-aware",
        "Telemetry",
        "Placement evidence",
        "Placement pods",
        "Interpretation",
    ], rows)


def network_aware_telemetry_rows(entries: dict[str, dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for scenario_id, entry in sorted(entries.items()):
        scenario = entry.get("scenario") or {}
        role = resource_aware_scheduler_role(entry, scenario_id)
        evidence = ((entry.get("defaultSchedulerArtifacts") or {}).get("schedulerDecisionEvidence") or {})
        telemetry = evidence.get("networkAwareTelemetryEvidence") if isinstance(evidence, dict) else None
        if not isinstance(telemetry, dict):
            telemetry = entry.get("networkAwareTelemetryEvidence") if isinstance(entry.get("networkAwareTelemetryEvidence"), dict) else None
        placement = evidence.get("placementClassification") if isinstance(evidence, dict) else None
        if not isinstance(telemetry, dict):
            telemetry = {}
        if not isinstance(placement, dict):
            placement = entry.get("placementClassification") if isinstance(entry.get("placementClassification"), dict) else {}
        cluster_lens = telemetry.get("clusterLensPlacementEvidence") if isinstance(telemetry.get("clusterLensPlacementEvidence"), dict) else {}
        rows.append([
            f"`{scenario_id}`",
            scenario.get("logicalScenarioId") or resource_aware_scheduler_logical_id(entry, scenario_id),
            role,
            telemetry.get("status") or "missing",
            cluster_lens.get("status") or "missing",
            cluster_lens.get("localAiPodCount") if cluster_lens.get("localAiPodCount") is not None else "n/a",
            telemetry.get("gatewayTrafficKey") or "n/a",
            ", ".join(telemetry.get("missingNodeAnnotationPrefixes") or []) or "none",
            ", ".join(telemetry.get("missingDeploymentAnnotationPrefixes") or []) or "none",
            len(telemetry.get("schedulerNameMismatches") or []),
            ", ".join(placement.get("scenarioCategories") or []) or "n/a",
        ])
    return rows


def build_network_aware_telemetry_table(entries: dict[str, dict[str, Any]]) -> str:
    rows = network_aware_telemetry_rows(entries)
    if not rows:
        return "No network-aware telemetry evidence is available yet."
    return md_table([
        "Scenario",
        "Logical scenario",
        "Mode",
        "Telemetry status",
        "Placement evidence",
        "Placement pods",
        "Gateway traffic key",
        "Missing node prefixes",
        "Missing deployment prefixes",
        "Scheduler mismatches",
        "Placement categories",
    ], rows)


def _network_aware_policy_enabled(entries: dict[str, dict[str, Any]], key: str, default: bool = True) -> bool:
    return default


def _worker_groups_text(groups: Any) -> str:
    if not isinstance(groups, list) or not groups:
        return "n/a"
    parts: list[str] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_id = group.get("groupId") or group.get("id") or "group"
        ordinals = group.get("workerOrdinals") or group.get("workers") or []
        if isinstance(ordinals, list):
            ordinals_text = ",".join(str(item) for item in ordinals)
        else:
            ordinals_text = str(ordinals)
        parts.append(f"{group_id}: {ordinals_text}")
    return "; ".join(parts) if parts else "n/a"


def build_network_aware_latency_profile_table(entries: dict[str, dict[str, Any]]) -> str:
    grouped: dict[str, dict[str, Any]] = {}
    role_sets: dict[str, set[str]] = defaultdict(set)
    variant_sets: dict[str, set[str]] = defaultdict(set)
    for scenario_id, entry in sorted(entries.items()):
        logical_id = resource_aware_scheduler_logical_id(entry, scenario_id)
        grouped.setdefault(logical_id, entry)
        role_sets[logical_id].add(resource_aware_scheduler_role(entry, scenario_id))
        variant_sets[logical_id].add(scenario_id)

    rows: list[list[Any]] = []
    for logical_id, entry in sorted(grouped.items()):
        scenario = entry.get("scenario") if isinstance(entry.get("scenario"), dict) else {}
        latency_profile = entry.get("latencyProfile") if isinstance(entry.get("latencyProfile"), dict) else {}
        target = latency_profile.get("target") if isinstance(latency_profile.get("target"), dict) else {}
        network = latency_profile.get("networkEmulation") if isinstance(latency_profile.get("networkEmulation"), dict) else {}
        runtime = latency_profile.get("runtimeImplementation") if isinstance(latency_profile.get("runtimeImplementation"), dict) else {}
        annotation = network.get("annotationControl") if isinstance(network.get("annotationControl"), dict) else {}
        roles = ", ".join(sorted(role_sets.get(logical_id) or [])) or "n/a"
        rows.append([
            f"`{logical_id}`",
            context_value(scenario.get("latencyAlias") or latency_profile.get("latencyAlias"), "not_declared"),
            f"`{context_value(scenario.get('latencyProfileId') or latency_profile.get('latencyProfileId') or latency_profile.get('profileId'), 'not_declared')}`",
            context_value(latency_profile.get("profileRole"), "not_declared"),
            context_value(runtime.get("implementationMode") or network.get("tool") or network.get("mode"), "not_declared"),
            context_value(target.get("intraGroupDelayMs") if target.get("intraGroupDelayMs") is not None else network.get("intraGroupDelayMs"), "n/a"),
            context_value(target.get("interGroupDelayMs") if target.get("interGroupDelayMs") is not None else network.get("interGroupDelayMs") or network.get("delayMs"), "n/a"),
            context_value(network.get("jitterMs"), "n/a"),
            context_value(network.get("packetLossPercent"), "n/a"),
            "yes" if annotation.get("enabled") is True else ("no" if annotation.get("enabled") is False else "not_declared"),
            _worker_groups_text(target.get("workerGroups")),
            roles,
            len(variant_sets.get(logical_id) or []),
        ])
    if not rows:
        return "No network-aware latency profile context is available yet."
    return md_table([
        "Logical scenario",
        "Alias",
        "Latency profile",
        "Profile role",
        "Implementation",
        "Intra-group delay ms",
        "Inter-group delay ms",
        "Jitter ms",
        "Packet loss %",
        "Annotation controlled",
        "Worker groups",
        "Scheduler modes",
        "Variants",
    ], rows)


def _network_aware_telemetry(entry: dict[str, Any]) -> dict[str, Any]:
    evidence = ((entry.get("defaultSchedulerArtifacts") or {}).get("schedulerDecisionEvidence") or {})
    telemetry = evidence.get("networkAwareTelemetryEvidence") if isinstance(evidence, dict) else None
    return telemetry if isinstance(telemetry, dict) else {}


def _cluster_lens_evidence(entry: dict[str, Any]) -> dict[str, Any]:
    telemetry = _network_aware_telemetry(entry)
    evidence = telemetry.get("clusterLensPlacementEvidence") if isinstance(telemetry.get("clusterLensPlacementEvidence"), dict) else {}
    return evidence


def build_cluster_lens_placement_summary_table(entries: dict[str, dict[str, Any]]) -> str:
    rows: list[list[Any]] = []
    for scenario_id, entry in sorted(entries.items(), key=lambda item: scenario_sort_key(item[0])):
        scenario = entry.get("scenario") if isinstance(entry.get("scenario"), dict) else {}
        cluster_lens = _cluster_lens_evidence(entry)
        rows.append([
            f"`{scenario_id}`",
            f"`{resource_aware_scheduler_logical_id(entry, scenario_id)}`",
            resource_aware_scheduler_role(entry, scenario_id),
            context_value(cluster_lens.get("captureStage"), "missing"),
            context_value(cluster_lens.get("primaryStage"), "n/a"),
            context_value(cluster_lens.get("stageSelection"), "missing"),
            context_value(cluster_lens.get("status"), "missing"),
            context_value(cluster_lens.get("validationSuccess"), "n/a"),
            context_value(cluster_lens.get("kubernetesNodeCount"), "n/a"),
            context_value(cluster_lens.get("rawNodeCount"), "n/a"),
            context_value(cluster_lens.get("rawNodeEdgeCount"), "n/a"),
            context_value(cluster_lens.get("rawAppEdgeCount"), "n/a"),
            context_value(cluster_lens.get("localAiPodCount"), "n/a"),
            context_value(cluster_lens.get("scheduledLocalAiPodCount"), "n/a"),
            context_value(cluster_lens.get("unscheduledLocalAiPodCount"), "n/a"),
            context_value(cluster_lens.get("distinctObservedNodes"), "n/a"),
            compact_list(cluster_lens.get("observedSchedulerNames") or []),
            f"`{cluster_lens.get('summaryPath') or 'not_available'}`",
            f"`{cluster_lens.get('placementSignaturePath') or 'not_available'}`",
        ])
    if not rows:
        return "No cluster-lens placement summary evidence is available yet."
    return md_table([
        "Scenario",
        "Logical scenario",
        "Mode",
        "Captured stage",
        "Primary stage",
        "Stage selection",
        "Status",
        "Validation",
        "K8s nodes",
        "Lens nodes",
        "Node edges",
        "App edges",
        "LocalAI pods",
        "Scheduled",
        "Unscheduled",
        "Observed nodes",
        "Observed schedulers",
        "Summary",
        "Signature",
    ], rows)


def build_cluster_lens_tenant_placement_table(entries: dict[str, dict[str, Any]]) -> str:
    rows: list[list[Any]] = []
    for scenario_id, entry in sorted(entries.items(), key=lambda item: scenario_sort_key(item[0])):
        cluster_lens = _cluster_lens_evidence(entry)
        tenants = cluster_lens.get("tenantPlacements") if isinstance(cluster_lens.get("tenantPlacements"), list) else []
        if not tenants:
            rows.append([
                f"`{scenario_id}`",
                f"`{resource_aware_scheduler_logical_id(entry, scenario_id)}`",
                resource_aware_scheduler_role(entry, scenario_id),
                "not_available",
                "n/a",
                "n/a",
                "n/a",
                "n/a",
                "n/a",
                "n/a",
                "n/a",
            ])
            continue
        for tenant in tenants:
            if not isinstance(tenant, dict):
                continue
            rows.append([
                f"`{scenario_id}`",
                f"`{resource_aware_scheduler_logical_id(entry, scenario_id)}`",
                resource_aware_scheduler_role(entry, scenario_id),
                f"`{tenant.get('tenant') or 'unknown'}`",
                compact_list(tenant.get("namespaces") or []),
                compact_list(tenant.get("masterNodes") or []),
                compact_list(tenant.get("workerNodes") or []),
                context_value(tenant.get("distinctTenantNodes"), "n/a"),
                context_value(tenant.get("masterWorkerCoLocated"), "n/a"),
                compact_list(tenant.get("unscheduledPods") or []),
                compact_list(tenant.get("schedulerNames") or []),
            ])
    if not rows:
        return "No cluster-lens tenant placement evidence is available yet."
    return md_table([
        "Scenario",
        "Logical scenario",
        "Mode",
        "Tenant",
        "Namespaces",
        "Master nodes",
        "Worker nodes",
        "Distinct tenant nodes",
        "Master-worker co-located",
        "Unscheduled pods",
        "Schedulers",
    ], rows)


def build_network_aware_scheduler_report_sections(entries: dict[str, dict[str, Any]], subheading: str) -> list[str]:
    return [
        f"{subheading} Network-aware latency profile context",
        "",
        "This table makes the active latency profile explicit for each logical scenario. It separates annotation-controlled inter-group latency profiles from generic network-emulation labels so that placement and response-time observations can be read against the intended network-cost model.",
        "",
        build_network_aware_latency_profile_table(entries),
        "",
        f"{subheading} Cluster-lens placement evidence summary",
        "",
        "This table reports the primary cluster-lens and Kubernetes placement evidence selected for each variant. The primary stage is used as the stable reporting entry point, while stage-specific captures remain preserved under the variant artifact tree.",
        "",
        build_cluster_lens_placement_summary_table(entries),
        "",
        f"{subheading} Cluster-lens tenant placement",
        "",
        "This table expands the placement summary by tenant, exposing master nodes, worker nodes, co-location and scheduler names. It is the direct evidence used to determine whether NETAWARE differs from DEFAULT and LOADAWARE under the same logical scenario.",
        "",
        build_cluster_lens_tenant_placement_table(entries),
        "",
        f"{subheading} Scheduler comparison",
        "",
        "This table groups the DEFAULT, LOADAWARE and NETAWARE variants of each logical scenario. Latency deltas are computed for the network-aware variant relative to the default and load-aware variants, so negative values indicate lower latency for NETAWARE.",
        "",
        build_network_aware_triplet_table(entries),
        "",
        f"{subheading} Network-aware telemetry evidence",
        "",
        "This table reports whether the scheduler-decision evidence contains the node/deployment annotations, gateway traffic key, cluster-lens placement capture and scheduler assignment checks needed to interpret NetworkAwareLocalAi decisions.",
        "",
        build_network_aware_telemetry_table(entries),
        "",
    ] + build_resource_aware_scheduler_report_sections(entries, subheading)


def build_scheduler_pairwise_table(entries: dict[str, dict[str, Any]]) -> str:
    rows = []
    for item in scheduler_pairwise_entries(entries):
        rows.append([
            f"`{item['logicalScenarioId']}`",
            f"`{item.get('defaultVariantId') or item.get('defaultScenarioId') or 'missing'}`",
            f"`{item.get('loadAwareVariantId') or item.get('loadAwareScenarioId') or 'missing'}`",
            item.get("defaultStatus"),
            item.get("loadAwareStatus"),
            fmt(item.get("defaultMeanLatencyMs")),
            fmt(item.get("loadAwareMeanLatencyMs")),
            fmt(item.get("meanLatencyDeltaPercent")),
            fmt(item.get("defaultP95LatencyMs")),
            fmt(item.get("loadAwareP95LatencyMs")),
            fmt(item.get("p95LatencyDeltaPercent")),
            fmt(item.get("defaultThroughputRps"), 4),
            fmt(item.get("loadAwareThroughputRps"), 4),
            fmt(item.get("throughputDeltaPercent")),
            fmt(item.get("defaultMaxNodeCpuPercent")),
            fmt(item.get("loadAwareMaxNodeCpuPercent")),
            fmt(item.get("defaultMaxNodeMemoryPercent")),
            fmt(item.get("loadAwareMaxNodeMemoryPercent")),
            item.get("interpretation"),
        ])
    if not rows:
        return "No resource-aware-scheduler pairwise evidence is available yet."
    return md_table([
        "Logical scenario",
        "Default variant",
        "Load-aware variant",
        "Default status",
        "Load-aware status",
        "Mean default",
        "Mean load-aware",
        "Mean delta %",
        "P95 default",
        "P95 load-aware",
        "P95 delta %",
        "RPS default",
        "RPS load-aware",
        "RPS delta %",
        "CPU default",
        "CPU load-aware",
        "Memory default",
        "Memory load-aware",
        "Interpretation",
    ], rows)


def build_scheduler_pairwise_global_section(profile: dict[str, Any], family_data: dict[str, dict[str, Any]]) -> list[str]:
    policy = profile.get("schedulerModePairwiseReporting") if isinstance(profile.get("schedulerModePairwiseReporting"), dict) else {}
    if not policy.get("enabled") or ("resource-aware-scheduler" not in family_data and "network-aware-scheduler" not in family_data):
        return []
    if not policy.get("includeGlobalSection", False):
        return []
    return [
        "## Pairwise Resource-Aware Scheduler",
        "",
        "This section compares each logical scenario in its default-scheduler and load-aware scheduler variants. Delta values are computed as load-aware relative to default; negative latency deltas indicate lower load-aware latency, while positive throughput deltas indicate higher load-aware throughput.",
        "",
        build_scheduler_pairwise_table(family_data.get("resource-aware-scheduler") or {}) if "resource-aware-scheduler" in family_data else build_network_aware_triplet_table(family_data.get("network-aware-scheduler") or {}),
        "",
    ]


def fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return str(value)


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) if cell is not None else "" for cell in row) + " |")
    return "\n".join(lines)


def compact_text(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    if isinstance(value, (list, tuple)):
        return ", ".join(compact_text(item) for item in value) if value else "n/a"
    if isinstance(value, dict):
        return ", ".join(f"{key}={compact_text(val)}" for key, val in value.items()) if value else "n/a"
    return str(value)


def baseline_workload_label(baseline: dict[str, Any]) -> str:
    workload = baseline.get("resolvedWorkload") or {}
    return f"users={workload.get('users', 'n/a')}, spawnRate={workload.get('spawnRate', 'n/a')}, runTime={workload.get('runTime', 'n/a')}"


def scenario_application_topology(scenario: dict[str, Any]) -> dict[str, Any]:
    topology = scenario.get("applicationTopology") if isinstance(scenario, dict) else None
    return topology if isinstance(topology, dict) else {}


def scenario_variant_payload(scenario: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        payload = scenario.get(key) if isinstance(scenario, dict) else None
        if isinstance(payload, dict):
            return payload
    return {}


def format_model_mapping(labels: Any, model_names: Any) -> str | None:
    if not isinstance(model_names, list) or not model_names:
        return None
    rendered: list[str] = []
    label_values = labels if isinstance(labels, list) else []
    for idx, model_name in enumerate(model_names):
        if model_name is None or model_name == "":
            continue
        label = label_values[idx] if idx < len(label_values) and label_values[idx] not in (None, "") else f"model-{idx + 1}"
        rendered.append(f"{label}={model_name}")
    return "; ".join(rendered) if rendered else None


def resolved_scenario_model(scenario: dict[str, Any], baseline: dict[str, Any]) -> Any:
    tenant_clusters = scenario.get("tenantClusters") if isinstance(scenario, dict) else None
    if isinstance(tenant_clusters, list) and tenant_clusters:
        pairs: list[tuple[str, str]] = []
        for idx, tenant in enumerate(tenant_clusters):
            if not isinstance(tenant, dict):
                continue
            model_name = first_non_empty(tenant.get("modelName"), tenant.get("resolvedModelName"), tenant.get("model"))
            if not model_name:
                continue
            label = first_non_empty(tenant.get("tenantId"), tenant.get("modelScenario"), f"tenant-{idx + 1}")
            pairs.append((str(label), str(model_name)))
        distinct_models = {model for _label, model in pairs}
        distinct_model_scenarios = {str(item.get("modelScenario")) for item in tenant_clusters if isinstance(item, dict) and item.get("modelScenario")}
        if len(distinct_models) > 1 or len(distinct_model_scenarios) > 1:
            return "; ".join(f"{label}={model}" for label, model in pairs) if pairs else None
        if pairs:
            return pairs[0][1]

    resolved_model_names = scenario.get("resolvedModelNames") if isinstance(scenario, dict) else None
    model_scenarios = scenario.get("modelScenarios") if isinstance(scenario, dict) else None
    if isinstance(resolved_model_names, list) and resolved_model_names:
        distinct_names = {str(name) for name in resolved_model_names if name not in (None, "")}
        distinct_scenarios = {str(item) for item in model_scenarios} if isinstance(model_scenarios, list) else set()
        if len(distinct_names) > 1 or len(distinct_scenarios) > 1:
            mapped = format_model_mapping(model_scenarios, resolved_model_names)
            if mapped:
                return mapped
        for model_name in resolved_model_names:
            if model_name not in (None, ""):
                return model_name

    return first_non_empty(
        scenario.get("primaryResolvedModelName"),
        scenario.get("resolvedModelName"),
        scenario.get("modelName"),
        scenario.get("model"),
        baseline.get("resolvedModelName"),
    )


def resolved_scenario_workload_label(scenario: dict[str, Any], baseline: dict[str, Any]) -> str:
    scenario_workload = scenario.get("resolvedWorkload") if isinstance(scenario.get("resolvedWorkload"), dict) else {}
    baseline_workload = baseline.get("resolvedWorkload") if isinstance(baseline.get("resolvedWorkload"), dict) else {}
    users = first_non_empty(scenario.get("users"), scenario_workload.get("users"), baseline_workload.get("users"))
    spawn_rate = first_non_empty(scenario.get("spawnRate"), scenario_workload.get("spawnRate"), baseline_workload.get("spawnRate"))
    run_time = first_non_empty(scenario.get("runTime"), scenario_workload.get("runTime"), baseline_workload.get("runTime"))
    return f"users={users}, spawnRate={spawn_rate}, runTime={run_time}"


def resolved_scenario_placement_type(scenario: dict[str, Any], baseline: dict[str, Any], variant: dict[str, Any] | None = None) -> Any:
    topology = scenario_application_topology(scenario)
    placement_variant = scenario_variant_payload(scenario, "placementVariant")
    candidates = [
        scenario.get("resolvedPlacementType"),
        topology.get("placementType"),
        scenario.get("placementType"),
    ]
    if isinstance(variant, dict):
        candidates.extend([
            variant.get("resolvedPlacementType"),
            variant.get("placementType"),
        ])
    candidates.extend([
        placement_variant.get("resolvedPlacementType"),
        placement_variant.get("placementType"),
        placement_variant.get("placementLabel"),
        placement_variant.get("label"),
        baseline.get("resolvedPlacementType"),
    ])
    for value in candidates:
        if value is not None and value != "":
            return value
    return "not_declared"


def resolved_scenario_placement_profile(scenario: dict[str, Any], baseline: dict[str, Any], variant: dict[str, Any] | None = None) -> Any:
    topology = scenario_application_topology(scenario)
    placement_variant = scenario_variant_payload(scenario, "placementVariant")
    candidates = [
        scenario.get("placementProfileId"),
        scenario.get("placementScenario"),
        topology.get("placementProfileId"),
        topology.get("placementScenario"),
    ]
    if isinstance(variant, dict):
        candidates.extend([variant.get("placementProfileId"), variant.get("placementScenario")])
    candidates.extend([
        placement_variant.get("placementProfileId"),
        placement_variant.get("placementScenario"),
        baseline.get("placementProfileId"),
        baseline.get("placementScenario"),
    ])
    for value in candidates:
        if value is not None and value != "":
            return value
    return "not_declared"


def resolved_scenario_topology_dir(scenario: dict[str, Any], baseline: dict[str, Any], variant: dict[str, Any] | None = None) -> Any:
    topology = scenario_application_topology(scenario)
    candidates = [scenario.get("topologyDir"), topology.get("topologyDir")]
    if isinstance(variant, dict):
        variant_topology = variant.get("applicationTopology") if isinstance(variant.get("applicationTopology"), dict) else {}
        candidates.extend([variant.get("topologyDir"), variant_topology.get("topologyDir")])
    candidates.append(baseline.get("topologyDir"))
    for value in candidates:
        if value is not None and value != "":
            return value
    return "not_declared"


def resolved_scenario_server_manifest(scenario: dict[str, Any], baseline: dict[str, Any], variant: dict[str, Any] | None = None) -> Any:
    topology = scenario_application_topology(scenario)
    candidates = [scenario.get("serverManifest"), topology.get("serverManifest")]
    if isinstance(variant, dict):
        variant_topology = variant.get("applicationTopology") if isinstance(variant.get("applicationTopology"), dict) else {}
        candidates.extend([variant.get("serverManifest"), variant_topology.get("serverManifest")])
    candidates.append(baseline.get("serverManifest"))
    for value in candidates:
        if value is not None and value != "":
            return value
    return "not_declared"


def resolved_localai_worker_count(scenario: dict[str, Any], baseline: dict[str, Any], variant: dict[str, Any] | None = None) -> Any:
    topology = scenario_application_topology(scenario)
    node_variant = scenario_variant_payload(scenario, "nodeCountVariant")
    placement_variant = scenario_variant_payload(scenario, "placementVariant")
    latency_variant = scenario_variant_payload(scenario, "latencyVariant")
    tenancy_variant = scenario_variant_payload(scenario, "tenancyVariant")
    candidates = [
        scenario.get("resolvedWorkerCount"),
        topology.get("localAiWorkerCount") if isinstance(topology, dict) else None,
        scenario.get("workerCount"),
    ]
    if isinstance(variant, dict):
        candidates.append(variant.get("fixedLocalAiWorkerCount"))
        candidates.append(variant.get("localAiWorkerCount"))
    for candidate_variant in (node_variant, placement_variant, latency_variant, tenancy_variant):
        if isinstance(candidate_variant, dict):
            candidates.append(candidate_variant.get("fixedLocalAiWorkerCount"))
            candidates.append(candidate_variant.get("localAiWorkerCount"))
    candidates.append(baseline.get("resolvedWorkerCount"))
    for value in candidates:
        if value is not None and value != "":
            return value
    return "not_declared"


def resolved_scenario_parameters(family: str, entry: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    scenario = entry.get("scenario") or {}
    placement_variant = scenario_variant_payload(scenario, "placementVariant")
    varied_variant = scenario_variant_payload(
        scenario,
        "placementVariant",
        "nodeCountVariant",
        "latencyVariant",
        "tenancyVariant",
        "resourceVariant",
    )
    parameters = {
        "model": resolved_scenario_model(scenario, baseline),
        "model_scenario": scenario.get("scenarioId") if family == "models" else first_non_empty(scenario.get("modelScenario"), baseline.get("modelScenario")),
        "worker_count": resolved_localai_worker_count(scenario, baseline, varied_variant),
        "worker_scenario": scenario.get("scenarioId") if family == "worker-count" else first_non_empty(scenario.get("workerScenario"), baseline.get("workerScenario")),
        "placement": resolved_scenario_placement_type(scenario, baseline, placement_variant),
        "placement_scenario": resolved_scenario_placement_profile(scenario, baseline, placement_variant),
        "workload": resolved_scenario_workload_label(scenario, baseline),
        "workload_scenario": scenario.get("scenarioId") if family == "workload" else first_non_empty(scenario.get("workloadScenario"), baseline.get("workloadScenario")),
        "topology": resolved_scenario_topology_dir(scenario, baseline, varied_variant),
        "server_manifest": resolved_scenario_server_manifest(scenario, baseline, varied_variant),
        "prompt": first_non_empty(scenario.get("prompt"), baseline.get("prompt")),
        "temperature": first_non_empty(scenario.get("temperature"), baseline.get("temperature")),
        "request_timeout_seconds": first_non_empty(scenario.get("requestTimeoutSeconds"), baseline.get("requestTimeoutSeconds")),
        "output_subdir": scenario.get("outputSubdir"),
        "reference_baseline": scenario.get("referenceBaselineId", baseline.get("baselineId")),
    }
    if family == "baseline":
        parameters["varied_value"] = scenario.get("baselineId") or baseline.get("baselineId") or entry.get("scenarioId")
    elif family == "worker-count":
        parameters["varied_value"] = parameters["worker_count"]
    elif family == "workload":
        parameters["varied_value"] = parameters["workload"]
    elif family == "models":
        parameters["varied_value"] = parameters["model"]
    elif family == "placement":
        parameters["varied_value"] = parameters["placement"]
    elif family == "resource-variation":
        variant = scenario_variant_payload(scenario, "resourceVariant")
        cpu = variant.get("workerVcpusPerNode", "NA")
        memory = variant.get("workerMemoryGiBPerNode", "NA")
        parameters["varied_value"] = f"{cpu} vCPU / {memory} GiB per worker"
    elif family == "node-count-variation":
        variant = scenario_variant_payload(scenario, "nodeCountVariant")
        nodes = variant.get("workerNodeCount", "NA")
        localai = resolved_localai_worker_count(scenario, baseline, variant)
        parameters["varied_value"] = f"{nodes} provider worker nodes / W{localai}"
    elif family == "placement-variation":
        variant = scenario_variant_payload(scenario, "placementVariant")
        parameters["varied_value"] = variant.get("label") or parameters.get("placement") or parameters.get("placement_scenario")
    elif family == "latency-injection":
        variant = scenario_variant_payload(scenario, "latencyVariant")
        delay = variant.get("delayMs", "NA")
        jitter = variant.get("jitterMs", 0)
        loss = variant.get("packetLossPercent", 0)
        parameters["varied_value"] = f"{delay} ms delay / {jitter} ms jitter / {loss}% loss"
        parameters["latency_profile"] = scenario.get("latencyProfileId") or variant.get("latencyProfileId")
    elif family == "multi-tenancy":
        variant = scenario_variant_payload(scenario, "tenancyVariant")
        parameters["varied_value"] = variant.get("label") or scenario.get("tenancyProfileId") or scenario.get("scenarioId")
        parameters["tenancy_profile"] = scenario.get("tenancyProfileId") or variant.get("tenancyProfileId")
    else:
        parameters["varied_value"] = scenario.get("scenarioId")
    return parameters


def family_execution_status(entries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total = len(entries)
    measured = sum(1 for entry in entries.values() if entry.get("status") == "measured")
    unsupported = sum(1 for entry in entries.values() if entry.get("status") == "unsupported_under_current_constraints")
    missing = sum(1 for entry in entries.values() if entry.get("status") == "missing")
    if total == 0 or (measured == 0 and unsupported == 0):
        status = "not_executed"
        explanation = "No benchmark measurements and no unsupported-scenario evidence were found for this sweep family."
    elif measured == 0 and unsupported > 0:
        status = "unsupported_only"
        explanation = "The sweep produced unsupported-scenario evidence but no measured benchmark samples."
    elif measured == total:
        status = "fully_measured"
        explanation = "All configured scenarios in this sweep have measured benchmark samples."
    else:
        status = "partially_measured"
        explanation = "At least one configured scenario has measured benchmark samples, while other scenarios are missing or unsupported."
    return {"status": status, "scenarioCount": total, "measuredCount": measured, "unsupportedCount": unsupported, "missingCount": missing, "explanation": explanation}


def family_parameter_matrix(family: str, entries: dict[str, dict[str, Any]], baseline: dict[str, Any], profile: dict[str, Any]) -> str:
    rows = []
    for scenario_id, entry in sorted(entries.items(), key=lambda kv: scenario_sort_key(kv[0])):
        params = resolved_scenario_parameters(family, entry, baseline)
        rows.append([
            f"`{scenario_id}`",
            entry.get("status"),
            compact_text(params.get("varied_value")),
            compact_text(params.get("model")),
            compact_text(params.get("worker_count")),
            compact_text(params.get("placement")),
            compact_text(params.get("workload")),
            compact_text(params.get("request_timeout_seconds")),
        ])
    if not rows:
        return "No scenario configuration files were discovered for this sweep family."
    varied_label = profile.get("variedDimensionByFamily", {}).get(family, family)
    return md_table(
        ["Scenario", "Status", f"Varied value ({varied_label})", "Model", "Worker count", "Placement", "Workload", "Timeout (s)"],
        rows,
    )


CONTROLLED_PARAMETER_FIELDS = [
    ("model", "Model"),
    ("worker_count", "Worker count"),
    ("placement", "Placement"),
    ("workload", "Workload"),
    ("topology", "Topology"),
    ("server_manifest", "Server manifest"),
    ("prompt", "Prompt"),
    ("temperature", "Temperature"),
    ("request_timeout_seconds", "Request timeout (s)"),
]


def _normalized_parameter_value(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _display_parameter_value(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    if isinstance(value, (dict, list, tuple)):
        return compact_text(value)
    return str(value)


def family_controlled_parameter_summary(family: str, entries: dict[str, dict[str, Any]], baseline: dict[str, Any]) -> str:
    rows: list[list[Any]] = []
    scenario_parameters = [resolved_scenario_parameters(family, entry, baseline) for entry in entries.values()]
    if not scenario_parameters:
        return "No scenario configuration files were discovered for this sweep family."
    for field, label in CONTROLLED_PARAMETER_FIELDS:
        values = [_normalized_parameter_value(params.get(field)) for params in scenario_parameters]
        unique_values = sorted(set(values))
        if len(unique_values) == 1:
            raw_value = scenario_parameters[0].get(field)
            rows.append([label, _display_parameter_value(raw_value), "controlled"])
        else:
            rows.append([label, f"varies across scenarios ({len(unique_values)} values)", "varied or scenario-specific"])
    return md_table(["Parameter", "Resolved value", "Interpretation"], rows)


def build_svg_bar_chart(title: str, values: list[tuple[str, float | None, str]], unit: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 980, 560
    ml, mr, mt, mb = 86, 32, 74, 126
    pw, ph = width - ml - mr, height - mt - mb
    measured = [(label, value, status) for label, value, status in values if value is not None]
    parts = [f'<line x1="{ml}" y1="{mt + ph}" x2="{ml + pw}" y2="{mt + ph}" stroke="#222"/>', f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt + ph}" stroke="#222"/>']
    if measured:
        max_value = max(v for _, v, _ in measured) or 1
        magnitude = 10 ** math.floor(math.log10(max_value)) if max_value > 0 else 1
        max_value = math.ceil(max_value / magnitude * 1.12) * magnitude
        for i in range(6):
            tick = max_value * i / 5
            y = mt + ph - tick / max_value * ph
            parts.append(f'<line x1="{ml - 5}" y1="{y:.2f}" x2="{ml + pw}" y2="{y:.2f}" stroke="#ddd"/>')
            parts.append(f'<text x="{ml - 10}" y="{y + 4:.2f}" text-anchor="end" font-size="12">{tick:.2f}</text>')
        step = pw / max(len(values), 1)
        bar_w = min(74, step * 0.62)
        for idx, (label, value, status) in enumerate(values):
            cx = ml + step * idx + step / 2
            if value is not None:
                bar_h = value / max_value * ph
                x, y = cx - bar_w / 2, mt + ph - bar_h
                fill = "#666" if status == "measured" else "#999"
                parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{bar_h:.2f}" fill="{fill}"/>')
                parts.append(f'<text x="{cx:.2f}" y="{y - 7:.2f}" text-anchor="middle" font-size="12">{value:.2f}</text>')
            else:
                parts.append(f'<text x="{cx:.2f}" y="{mt + ph - 8:.2f}" text-anchor="middle" font-size="12">n/a</text>')
            safe_label = html.escape(label)
            parts.append(f'<text x="{cx:.2f}" y="{mt + ph + 18:.2f}" text-anchor="end" font-size="12" transform="rotate(-35 {cx:.2f},{mt + ph + 18:.2f})">{safe_label}</text>')
    else:
        parts.append(f'<text x="{width / 2}" y="{height / 2}" text-anchor="middle" font-size="18">No measured values available</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="white"/>
  <text x="{width/2}" y="34" text-anchor="middle" font-family="Arial, sans-serif" font-size="22" font-weight="bold">{html.escape(title)}</text>
  <text x="{width/2}" y="58" text-anchor="middle" font-family="Arial, sans-serif" font-size="13">Unit: {html.escape(unit)}</text>
  <g font-family="Arial, sans-serif" fill="#222">
{chr(10).join(parts)}
  </g>
</svg>
'''
    output_path.write_text(svg, encoding="utf-8")


def build_summary_rows(family_data: dict[str, dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for family in profile["familyOrder"]:
        entries = family_data.get(family, {})
        ref_id = profile.get("referenceScenarioByFamily", {}).get(family)
        ref_latency = metric_mean(entries.get(ref_id, {}), "mean_response_time_ms")
        ref_throughput = metric_mean(entries.get(ref_id, {}), "throughput_rps")
        for scenario_id in sorted(entries, key=scenario_sort_key):
            entry = entries[scenario_id]
            summary = entry.get("summary") or {}
            metrics = summary.get("metrics") or {}
            cluster = summary.get("clusterSideSnapshots") or {}
            row = {
                "family": family,
                "scenario_id": scenario_id,
                "label": entry.get("label"),
                "status": entry.get("status"),
                "summary_source": entry.get("summarySource"),
                "sample_count": summary.get("sampleCount", 0),
                "replicas": ",".join(summary.get("replicas", [])),
                "unsupported_replicas": ",".join((entry.get("unsupportedSummary") or {}).get("replicas", [])),
                "unsupported_evidence_kinds": ",".join((entry.get("unsupportedSummary") or {}).get("evidenceKinds", [])),
            }
            for metric in METRIC_KEYS:
                m = metrics.get(metric) or {}
                row[f"{metric}_mean"] = m.get("mean")
                row[f"{metric}_min"] = m.get("min")
                row[f"{metric}_max"] = m.get("max")
                row[f"{metric}_cv_percent"] = m.get("coefficientOfVariationPercent")
            for report_metric, (_group, cluster_key) in RESOURCE_METRIC_MAP.items():
                cluster_metric_summary = cluster.get(cluster_key) or {}
                cluster_mean = cluster_metric_summary.get("mean")
                row[f"{report_metric}_mean"] = cluster_mean if cluster_mean is not None else summary.get(f"{cluster_key}Observed")
            row["mean_latency_delta_vs_reference_percent"] = round(pct_delta(ref_latency, row.get("mean_response_time_ms_mean")), 4) if pct_delta(ref_latency, row.get("mean_response_time_ms_mean")) is not None else None
            row["throughput_delta_vs_reference_percent"] = round(pct_delta(ref_throughput, row.get("throughput_rps_mean")), 4) if pct_delta(ref_throughput, row.get("throughput_rps_mean")) is not None else None
            rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def infer_finding_family(item: dict[str, Any]) -> str:
    if item.get("family"):
        return str(item.get("family"))
    finding_id = str(item.get("id") or "")
    prefix_map = {
        "resource_variation": "resource-variation",
        "node_count_variation": "node-count-variation",
        "placement_variation": "placement-variation",
        "latency_injection": "latency-injection",
        "multi_tenancy": "multi-tenancy",
        "worker_count": "worker-count",
        "workload": "workload",
        "model": "models",
        "placement": "placement",
        "provider_backed_baseline": "baseline",
        "validation_baseline": "baseline",
        "cluster_cpu": "infrastructure",
        "cluster_memory": "infrastructure",
    }
    for prefix, family in prefix_map.items():
        if finding_id.startswith(prefix):
            return family
    return finding_id.split("_")[0] if finding_id else "general"


def diagnosis_findings_by_family(diagnosis_payload: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not diagnosis_payload:
        return result
    for item in diagnosis_payload.get("familyJudgments") or []:
        result[item.get("family", "general")].append({"kind": "family_judgment", **item})
    for item in diagnosis_payload.get("findings") or []:
        family = infer_finding_family(item)
        result[family].append({"kind": "finding", **item})
    return result


def family_ref_values(entries: dict[str, dict[str, Any]], profile: dict[str, Any], family: str) -> tuple[str | None, float | None, float | None, float | None]:
    ref_id = profile.get("referenceScenarioByFamily", {}).get(family)
    ref_entry = entries.get(ref_id, {}) if ref_id else {}
    return (
        ref_id,
        metric_mean(ref_entry, "mean_response_time_ms"),
        metric_mean(ref_entry, "p95_response_time_ms"),
        metric_mean(ref_entry, "throughput_rps"),
    )


def build_family_measurement_summary_table(entries: dict[str, dict[str, Any]], profile: dict[str, Any], family: str) -> str:
    table_rows = []
    for scenario_id, entry in sorted(entries.items(), key=lambda kv: scenario_sort_key(kv[0])):
        unsupported_kinds = ", ".join((entry.get("unsupportedSummary") or {}).get("evidenceKinds", []))
        table_rows.append([
            f"`{scenario_id}`",
            entry.get("label"),
            entry.get("status"),
            (entry.get("summary") or {}).get("sampleCount", 0),
            fmt(metric_mean(entry, "mean_response_time_ms")),
            fmt(metric_mean(entry, "p95_response_time_ms")),
            fmt(metric_mean(entry, "throughput_rps"), 4),
            unsupported_kinds,
        ])
    return md_table(
        [
            "Scenario",
            "Description",
            "Status",
            "Sample count",
            METRIC_DISPLAY["mean_response_time_ms"],
            METRIC_DISPLAY["p95_response_time_ms"],
            METRIC_DISPLAY["throughput_rps"],
            "Unsupported evidence",
        ],
        table_rows,
    )


def build_family_extended_metrics_table(entries: dict[str, dict[str, Any]], profile: dict[str, Any], family: str) -> str:
    _ref_id, ref_latency, ref_p95, ref_thr = family_ref_values(entries, profile, family)
    table_rows = []
    for scenario_id, entry in sorted(entries.items(), key=lambda kv: scenario_sort_key(kv[0])):
        mean_latency = metric_mean(entry, "mean_response_time_ms")
        p95_latency = metric_mean(entry, "p95_response_time_ms")
        throughput = metric_mean(entry, "throughput_rps")
        table_rows.append([
            f"`{scenario_id}`",
            fmt(metric_mean(entry, "p50_response_time_ms")),
            fmt(metric_mean(entry, "p99_response_time_ms")),
            fmt(pct_delta(ref_latency, mean_latency)),
            fmt(pct_delta(ref_p95, p95_latency)),
            fmt(pct_delta(ref_thr, throughput)),
            fmt(metric_mean(entry, "max_node_cpu_percent")),
            fmt(metric_mean(entry, "max_node_memory_percent")),
            fmt(metric_mean(entry, "max_pod_cpu_millicores")),
            fmt(metric_mean(entry, "max_pod_memory_mib")),
        ])
    return md_table(
        [
            "Scenario",
            METRIC_DISPLAY["p50_response_time_ms"],
            METRIC_DISPLAY["p99_response_time_ms"],
            "Mean response time delta (%)",
            "P95 response time delta (%)",
            "Throughput delta (%)",
            METRIC_DISPLAY["max_node_cpu_percent"],
            METRIC_DISPLAY["max_node_memory_percent"],
            METRIC_DISPLAY["max_pod_cpu_millicores"],
            METRIC_DISPLAY["max_pod_memory_mib"],
        ],
        table_rows,
    )


def unsupported_reason_text(entry: dict[str, Any]) -> str:
    unsupported_summary = entry.get("unsupportedSummary") or {}
    reasons = unsupported_summary.get("reasons") if isinstance(unsupported_summary, dict) else None
    return compact_list(reasons) if reasons else "none"


def build_resource_capacity_context_table(entries: dict[str, dict[str, Any]]) -> str:
    rows = []
    for scenario_id, entry in sorted(entries.items(), key=lambda kv: scenario_sort_key(kv[0])):
        scenario = entry.get("scenario") or {}
        variant = scenario.get("resourceVariant") or {}
        worker_nodes = first_non_empty(variant.get("workerNodeCount"), scenario.get("workerNodeCount"), "not_declared")
        worker_vcpus = first_non_empty(variant.get("workerVcpusPerNode"), scenario.get("workerVcpusPerNode"), "not_declared")
        worker_memory = first_non_empty(variant.get("workerMemoryGiBPerNode"), scenario.get("workerMemoryGiBPerNode"), "not_declared")
        total_cpu = first_non_empty(variant.get("totalWorkerVcpus"), "not_declared")
        total_memory = first_non_empty(variant.get("totalWorkerMemoryGiB"), "not_declared")
        is_reference = first_non_empty(variant.get("isReferenceShape"), scenario.get("referenceScenario"), False)
        rows.append([
            f"`{scenario_id}`",
            worker_nodes,
            f"{worker_vcpus} vCPU / {worker_memory} GiB",
            f"{total_cpu} vCPU",
            f"{total_memory} GiB",
            "yes" if bool(is_reference) else "no",
            semantic_value(entry.get("status"), "not_declared"),
            unsupported_reason_text(entry),
        ])
    if not rows:
        return "No resource-capacity context is available for this sweep."
    return md_table(
        [
            "Scenario",
            "Worker nodes",
            "Worker-node shape",
            "Total worker CPU",
            "Total worker memory",
            "Reference shape",
            "Execution status",
            "Unsupported reason",
        ],
        rows,
    )


def build_latency_injection_context_table(entries: dict[str, dict[str, Any]]) -> str:
    rows = []
    for scenario_id, entry in sorted(entries.items(), key=lambda kv: scenario_sort_key(kv[0])):
        scenario = entry.get("scenario") or {}
        variant = scenario.get("latencyVariant") or {}
        latency_profile = entry.get("latencyProfile") if isinstance(entry.get("latencyProfile"), dict) else {}
        target = latency_profile.get("target") if isinstance(latency_profile.get("target"), dict) else {}
        network = latency_profile.get("networkEmulation") if isinstance(latency_profile.get("networkEmulation"), dict) else {}
        safety = latency_profile.get("safetyPolicy") if isinstance(latency_profile.get("safetyPolicy"), dict) else {}
        rows.append([
            f"`{scenario_id}`",
            context_value(first_non_empty(scenario.get("latencyProfileId"), variant.get("latencyProfileId"), latency_profile.get("latencyProfileId")), "not_declared"),
            context_value(first_non_empty(variant.get("latencyCategory"), latency_profile.get("latencyCategory")), "not_declared"),
            context_value(first_non_empty(variant.get("targetNodePolicy"), target.get("targetNodePolicy")), "not_declared"),
            context_value(first_non_empty(variant.get("delayMs"), network.get("delayMs")), "not_declared"),
            context_value(first_non_empty(variant.get("jitterMs"), network.get("jitterMs")), "not_declared"),
            context_value(first_non_empty(variant.get("packetLossPercent"), network.get("packetLossPercent")), "not_declared"),
            context_value(first_non_empty(variant.get("networkInterface"), network.get("networkInterface")), "not_declared"),
            yes_no(first_non_empty(network.get("resetAfterBenchmark"), safety.get("resetAfterBenchmark")), "not_declared"),
            semantic_value(entry.get("status"), "not_declared"),
            unsupported_reason_text(entry),
        ])
    if not rows:
        return "No latency-injection context is available for this sweep."
    return md_table(
        [
            "Scenario",
            "Latency profile",
            "Category",
            "Target node policy",
            "Delay (ms)",
            "Jitter (ms)",
            "Packet loss (%)",
            "Interface",
            "Reset after benchmark",
            "Execution status",
            "Unsupported reason",
        ],
        rows,
    )


def build_node_count_context_table(entries: dict[str, dict[str, Any]]) -> str:
    rows = []
    for scenario_id, entry in sorted(entries.items(), key=lambda kv: scenario_sort_key(kv[0])):
        scenario = entry.get("scenario") or {}
        variant = scenario.get("nodeCountVariant") or {}
        summary = entry.get("summary") or {}
        rows.append([
            f"`{scenario_id}`",
            variant.get("workerNodeCount", "NA"),
            scenario.get("resolvedWorkerCount", variant.get("fixedLocalAiWorkerCount", "NA")),
            f"{variant.get('workerVcpusPerNode', 'NA')} vCPU / {variant.get('workerMemoryGiBPerNode', 'NA')} GiB",
            scenario.get("topologyDir", "NA"),
            compact_list((summary.get("observedPlacementNodeCounts") or {}).keys()) if summary else "NA",
        ])
    if not rows:
        return "No node-count context is available for this sweep."
    return md_table(["Scenario", "Provider worker nodes", "LocalAI RPC workers", "Per-node capacity", "Topology", "Observed placement nodes"], rows)


def build_tenant_topology_context_table(entries: dict[str, dict[str, Any]]) -> str:
    rows: list[list[Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for scenario_id, entry in sorted(entries.items(), key=lambda kv: scenario_sort_key(kv[0])):
        scenario = entry.get("scenario") or {}
        tenancy_profile = entry.get("tenancyProfile") if isinstance(entry.get("tenancyProfile"), dict) else {}
        tenant_clusters = tenancy_profile.get("tenantClusters") if isinstance(tenancy_profile, dict) else None
        benchmark_tenant = first_non_empty(
            tenancy_profile.get("benchmarkTenantId") if isinstance(tenancy_profile, dict) else None,
            (scenario.get("tenancyVariant") or {}).get("benchmarkTenantId") if isinstance(scenario.get("tenancyVariant"), dict) else None,
        )

        if isinstance(tenant_clusters, list) and tenant_clusters:
            for tenant in tenant_clusters:
                if not isinstance(tenant, dict):
                    continue
                tenant_id = str(first_non_empty(tenant.get("tenantId"), "not_declared"))
                key = (str(scenario_id), tenant_id, str(tenant.get("namespace") or ""))
                if key in seen:
                    continue
                seen.add(key)
                rows.append([
                    f"`{scenario_id}`",
                    f"`{tenant_id}`",
                    semantic_value(tenant.get("namespace"), "not_declared"),
                    semantic_value(tenant.get("role"), "not_declared"),
                    "yes" if benchmark_tenant and tenant_id == str(benchmark_tenant) else "no",
                    semantic_value(tenant.get("modelScenario"), "not_declared"),
                    semantic_value(tenant.get("modelName"), "not_declared"),
                    semantic_value(tenant.get("workerScenario"), "not_declared"),
                    tenant.get("workerCount") if tenant.get("workerCount") is not None else "not_declared",
                    semantic_value(tenant.get("placement"), "not_declared"),
                ])
            continue

        topology = scenario_application_topology(scenario)
        tenant_id = first_non_empty((scenario.get("tenancyVariant") or {}).get("benchmarkTenantId") if isinstance(scenario.get("tenancyVariant"), dict) else None, "tenant-a")
        namespace = first_non_empty(topology.get("namespace"), (scenario.get("tenancyVariant") or {}).get("benchmarkNamespace") if isinstance(scenario.get("tenancyVariant"), dict) else None)
        rows.append([
            f"`{scenario_id}`",
            f"`{tenant_id}`",
            semantic_value(namespace, "not_declared"),
            "benchmark_tenant",
            "yes",
            semantic_value(scenario.get("modelScenario"), "not_declared"),
            semantic_value(resolved_scenario_model(scenario, {}), "not_declared"),
            semantic_value(scenario.get("workerScenario"), "not_declared"),
            resolved_localai_worker_count(scenario, {}, None),
            semantic_value(resolved_scenario_placement_profile(scenario, {}, None), "not_declared"),
        ])

    if not rows:
        return "No tenant topology metadata is available for this sweep."
    return md_table(
        [
            "Scenario",
            "Tenant",
            "Namespace",
            "Role",
            "Benchmarked",
            "Model scenario",
            "Model",
            "Worker scenario",
            "Worker count",
            "Placement",
        ],
        rows,
    )


def default_scheduler_multi_tenant_summary_candidates(results_root: Path, search_roots: list[Path], scenario_id: str) -> list[Path]:
    candidates: list[Path] = []
    for root in search_roots:
        candidates.extend(
            [
                root / "multi-tenant-summary.json",
                root / "latest-multi-tenant-summary.json",
            ]
        )
    if results_root.exists():
        candidates.extend(results_root.glob(f"**/{scenario_id}/multi-tenant-summary.json"))
        candidates.extend(results_root.glob(f"**/{scenario_id}/latest-multi-tenant-summary.json"))
        candidates.extend(results_root.glob(f"**/{scenario_id}_*/multi-tenant-summary.json"))
    return unique_paths(candidates)


def latest_scheduler_evidence_aliases(artifact_name: str) -> list[str]:
    aliases = ["latest-default-scheduler-decision-evidence.json"]
    if artifact_name != "default-scheduler-decision-evidence.json":
        stem = artifact_name[:-5] if artifact_name.endswith(".json") else artifact_name
        aliases.insert(0, f"latest-{stem}.json")
    return aliases


def default_scheduler_evidence_candidates(repo_root: Path, profile: dict[str, Any], scenario: dict[str, Any], scenario_id: str) -> list[Path]:
    candidates: list[Path] = []
    scheduler_evidence = scenario.get("schedulerEvidence") if isinstance(scenario.get("schedulerEvidence"), dict) else {}
    artifact_name = str(
        first_non_empty(
            scheduler_evidence.get("artifactName") if isinstance(scheduler_evidence, dict) else None,
            profile.get("schedulerDecisionEvidenceArtifactName"),
            "default-scheduler-decision-evidence.json",
        )
    )
    artifact_root = first_non_empty(
        scheduler_evidence.get("artifactRoot") if isinstance(scheduler_evidence, dict) else None,
        None,
    )
    if artifact_root:
        candidates.append(resolve_artifact_path(repo_root, artifact_root) / artifact_name)

    profile_root = profile.get("schedulerDecisionEvidenceRoot")
    if profile_root:
        root = resolve_artifact_path(repo_root, profile_root)
        candidates.append(root / scenario_id / artifact_name)
        for latest_alias in latest_scheduler_evidence_aliases(artifact_name):
            candidates.append(root / scenario_id / latest_alias)
        if root.exists():
            candidates.extend(root.glob(f"**/{scenario_id}/" + artifact_name))
            for latest_alias in latest_scheduler_evidence_aliases(artifact_name):
                candidates.extend(root.glob(f"**/{scenario_id}/" + latest_alias))
    return unique_paths(candidates)


def load_first_existing_json(candidates: list[Path]) -> tuple[Path | None, dict[str, Any] | None]:
    for path in candidates:
        if path is None or not path.exists() or not path.is_file():
            continue
        payload = read_json_optional(path)
        if isinstance(payload, dict):
            return path, payload
    return None, None


def default_scheduler_artifacts_for_scenario(
    repo_root: Path,
    profile: dict[str, Any],
    scenario_id: str,
    scenario: dict[str, Any],
    results_root: Path,
    search_roots: list[Path],
) -> dict[str, Any]:
    multi_tenant_summary_path, multi_tenant_summary = load_first_existing_json(
        default_scheduler_multi_tenant_summary_candidates(results_root, search_roots, scenario_id)
    )
    scheduler_evidence_path, scheduler_evidence = load_first_existing_json(
        default_scheduler_evidence_candidates(repo_root, profile, scenario, scenario_id)
    )
    if scenario.get("scenarioFamily") == "network-aware-scheduler" or scenario_id.startswith("NA_"):
        network_telemetry = collect_network_aware_telemetry_for_scenario(repo_root, profile, scenario_id, scenario)
        if isinstance(scheduler_evidence, dict):
            scheduler_evidence = dict(scheduler_evidence)
            scheduler_evidence["networkAwareTelemetryEvidence"] = network_telemetry
        else:
            scheduler_evidence = {"networkAwareTelemetryEvidence": network_telemetry}
    return {
        "multiTenantSummaryPath": safe_rel(multi_tenant_summary_path, repo_root) if multi_tenant_summary_path else None,
        "multiTenantSummary": multi_tenant_summary or {},
        "schedulerDecisionEvidencePath": safe_rel(scheduler_evidence_path, repo_root) if scheduler_evidence_path else None,
        "schedulerDecisionEvidence": scheduler_evidence or {},
    }


def default_scheduler_samples_from_multi_tenant_summary(payload: dict[str, Any], repo_root: Path | None = None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    results = payload.get("tenantResults")
    if not isinstance(results, list):
        return []

    samples: list[dict[str, Any]] = []
    for tenant in results:
        if not isinstance(tenant, dict):
            continue
        measurement = tenant.get("measurement") if isinstance(tenant.get("measurement"), dict) else {}
        if not measurement.get("validTargetRequestsPresent"):
            continue

        tenant_id = str(tenant.get("tenantId") or tenant.get("namespace") or f"tenant-{len(samples) + 1}")
        replica_id = str(tenant.get("replica") or tenant.get("replicaId") or tenant_id)
        stats_csv_value = measurement.get("statsCsv") or nested_get(tenant, "artifacts", "statsCsv")
        stats_csv_path = resolve_artifact_path(repo_root, stats_csv_value) if repo_root is not None else (Path(str(stats_csv_value)) if stats_csv_value else None)
        sample: dict[str, Any] = {
            "replica": replica_id,
            "tenantId": tenant_id,
            "namespace": tenant.get("namespace"),
            "statsCsvPath": stats_csv_value,
            "rowSource": "multi_tenant_summary",
            "request_count": int(round(measurement.get("targetRequestCount") or 0)),
            "failure_count": int(round(measurement.get("failureCount") or 0)),
            "mean_response_time_ms": measurement.get("averageResponseTimeMs"),
            "p50_response_time_ms": measurement.get("medianResponseTimeMs"),
            "p95_response_time_ms": measurement.get("p95ResponseTimeMs"),
            "p99_response_time_ms": measurement.get("p99ResponseTimeMs"),
            "throughput_rps": measurement.get("requestsPerSecond"),
        }
        sample.update(cluster_side_metrics_from_stats_file(stats_csv_path, repo_root=repo_root, phase="post"))
        samples.append(sample)
    return samples


def default_scheduler_tenant_metric_rows(entry: dict[str, Any]) -> list[list[Any]]:
    artifacts = entry.get("defaultSchedulerArtifacts") or {}
    summary = artifacts.get("multiTenantSummary") if isinstance(artifacts.get("multiTenantSummary"), dict) else {}
    rows: list[list[Any]] = []
    for tenant in summary.get("tenantResults") or []:
        if not isinstance(tenant, dict):
            continue
        measurement = tenant.get("measurement") if isinstance(tenant.get("measurement"), dict) else {}
        rows.append(
            [
                f"`{entry.get('scenarioId')}`",
                f"`{tenant.get('tenantId')}`",
                semantic_value(tenant.get("namespace"), "not_declared"),
                semantic_value(tenant.get("status"), "not_available"),
                context_value(tenant.get("users"), "not_declared"),
                context_value(tenant.get("spawnRate"), "not_declared"),
                context_value(tenant.get("runTime"), "not_declared"),
                context_value(tenant.get("waitTimeSeconds"), "not_declared"),
                context_value(measurement.get("targetRequestCount"), "not_collected"),
                context_value(measurement.get("failureCount"), "not_collected"),
                fmt(measurement.get("averageResponseTimeMs")),
                fmt(measurement.get("p95ResponseTimeMs")),
                fmt(measurement.get("p99ResponseTimeMs")),
                fmt(measurement.get("requestsPerSecond"), 4),
            ]
        )
    return rows


def build_default_scheduler_context_table(entries: dict[str, dict[str, Any]]) -> str:
    rows: list[list[Any]] = []
    for scenario_id, entry in sorted(entries.items(), key=lambda kv: scenario_sort_key(kv[0])):
        scenario = entry.get("scenario") or {}
        rows.append(
            [
                f"`{scenario_id}`",
                semantic_value(scenario.get("scenarioClass"), "not_declared"),
                context_value(scenario.get("tenantCount"), "not_declared"),
                context_value(scenario.get("workerNodeCount"), "not_declared"),
                context_value(scenario.get("latencyProfileId"), "not_declared"),
                context_value(scenario.get("trafficProfileId"), "not_declared"),
                context_value(scenario.get("modelMix"), "not_declared"),
                context_value(scenario.get("localAiWorkerCountPerTenant") if scenario.get("localAiWorkerCountPerTenant") is not None else scenario.get("resolvedWorkerCountPerTenant"), "not_declared"),
                semantic_value(scenario.get("placementProfileId"), "not_declared"),
                semantic_value(scenario.get("topologyDir"), "not_declared"),
                semantic_value(entry.get("status"), "not_declared"),
            ]
        )
    if not rows:
        return "No scheduler scenario context is available for this sweep."
    return md_table(
        [
            "Scenario",
            "Class",
            "Tenants",
            "Worker nodes",
            "Latency profile",
            "Traffic profile",
            "Model mix",
            "Workers per tenant",
            "Scheduler/placement profile",
            "Composition",
            "Execution status",
        ],
        rows,
    )


def build_default_scheduler_tenant_traffic_table(entries: dict[str, dict[str, Any]]) -> str:
    rows: list[list[Any]] = []
    for scenario_id, entry in sorted(entries.items(), key=lambda kv: scenario_sort_key(kv[0])):
        scenario = entry.get("scenario") or {}
        for tenant in scenario.get("tenantClusters") or []:
            if not isinstance(tenant, dict):
                continue
            traffic = tenant.get("trafficProfile") if isinstance(tenant.get("trafficProfile"), dict) else {}
            rows.append(
                [
                    f"`{scenario_id}`",
                    f"`{tenant.get('tenantId')}`",
                    semantic_value(tenant.get("namespace"), "not_declared"),
                    semantic_value(tenant.get("role"), "not_declared"),
                    semantic_value(tenant.get("modelScenario"), "not_declared"),
                    semantic_value(tenant.get("modelName"), "not_declared"),
                    context_value(tenant.get("workerCount"), "not_declared"),
                    context_value(traffic.get("users"), "not_declared"),
                    context_value(traffic.get("spawnRate"), "not_declared"),
                    context_value(traffic.get("runTime"), "not_declared"),
                    context_value(traffic.get("waitTimeSeconds"), "not_declared"),
                ]
            )
    if not rows:
        return "No tenant traffic metadata is available for this sweep."
    return md_table(
        [
            "Scenario",
            "Tenant",
            "Namespace",
            "Role",
            "Model scenario",
            "Model",
            "Workers",
            "Users",
            "Spawn rate",
            "Run time",
            "Wait time (s)",
        ],
        rows,
    )


def build_default_scheduler_pod_node_table(entries: dict[str, dict[str, Any]]) -> str:
    rows: list[list[Any]] = []
    for scenario_id, entry in sorted(entries.items(), key=lambda kv: scenario_sort_key(kv[0])):
        artifacts = entry.get("defaultSchedulerArtifacts") or {}
        evidence = artifacts.get("schedulerDecisionEvidence") if isinstance(artifacts.get("schedulerDecisionEvidence"), dict) else {}
        for pod in evidence.get("podEvidence") or []:
            if not isinstance(pod, dict):
                continue
            classification = pod.get("placementClassification") if isinstance(pod.get("placementClassification"), dict) else {}
            rows.append(
                [
                    f"`{scenario_id}`",
                    f"`{pod.get('tenantId')}`",
                    semantic_value(pod.get("namespace"), "not_declared"),
                    semantic_value(pod.get("deployment"), "not_declared"),
                    semantic_value(pod.get("podName"), "not_declared"),
                    semantic_value(pod.get("role"), "not_declared"),
                    semantic_value(pod.get("nodeName"), "not_scheduled"),
                    semantic_value(pod.get("podPhase"), "not_declared"),
                    context_value(pod.get("restartCount"), 0),
                    semantic_compact_list(classification.get("categories"), "not_classified"),
                    semantic_value(classification.get("riskLevel"), "not_declared"),
                ]
            )
    if not rows:
        return "No runtime pod-to-node scheduler evidence is available yet for this sweep."
    return md_table(
        [
            "Scenario",
            "Tenant",
            "Namespace",
            "Deployment",
            "Pod",
            "Role",
            "Node",
            "Phase",
            "Restarts",
            "Placement categories",
            "Risk",
        ],
        rows,
    )


def build_default_scheduler_placement_classification_table(entries: dict[str, dict[str, Any]]) -> str:
    rows: list[list[Any]] = []
    for scenario_id, entry in sorted(entries.items(), key=lambda kv: scenario_sort_key(kv[0])):
        artifacts = entry.get("defaultSchedulerArtifacts") or {}
        evidence = artifacts.get("schedulerDecisionEvidence") if isinstance(artifacts.get("schedulerDecisionEvidence"), dict) else {}
        classification = evidence.get("placementClassification") if isinstance(evidence.get("placementClassification"), dict) else {}
        summary = evidence.get("summary") if isinstance(evidence.get("summary"), dict) else {}
        rows.append(
            [
                f"`{scenario_id}`",
                semantic_value(evidence.get("status"), "not_collected"),
                semantic_value(evidence.get("captureMode"), "not_collected"),
                semantic_value(classification.get("scenarioRiskLevel"), "not_classified"),
                semantic_compact_list(classification.get("scenarioCategories"), "not_classified"),
                context_value(summary.get("scheduledPodCount"), "not_collected"),
                context_value(summary.get("unscheduledPodCount"), "not_collected"),
                context_value(summary.get("nodeCountWithLocalAiPods"), "not_collected"),
                context_value(len(classification.get("negativeEvidence") or []), 0),
                semantic_value(artifacts.get("schedulerDecisionEvidencePath"), "not_available"),
            ]
        )
    if not rows:
        return "No placement-classification metadata is available for this sweep."
    return md_table(
        [
            "Scenario",
            "Evidence status",
            "Capture mode",
            "Risk level",
            "Scenario categories",
            "Scheduled pods",
            "Unscheduled pods",
            "Nodes with LocalAI pods",
            "Negative evidence items",
            "Evidence artifact",
        ],
        rows,
    )


def build_default_scheduler_tenant_metrics_table(entries: dict[str, dict[str, Any]]) -> str:
    rows: list[list[Any]] = []
    for _scenario_id, entry in sorted(entries.items(), key=lambda kv: scenario_sort_key(kv[0])):
        rows.extend(default_scheduler_tenant_metric_rows(entry))
    if not rows:
        return "No per-tenant benchmark metrics are available yet for this sweep."
    return md_table(
        [
            "Scenario",
            "Tenant",
            "Namespace",
            "Locust status",
            "Users",
            "Spawn rate",
            "Run time",
            "Wait time (s)",
            "Requests",
            "Failures",
            "Mean response time (ms)",
            "P95 response time (ms)",
            "P99 response time (ms)",
            "Throughput (requests/s)",
        ],
        rows,
    )


def build_default_scheduler_negative_evidence_table(entries: dict[str, dict[str, Any]]) -> str:
    rows: list[list[Any]] = []
    max_rows = 40
    for scenario_id, entry in sorted(entries.items(), key=lambda kv: scenario_sort_key(kv[0])):
        artifacts = entry.get("defaultSchedulerArtifacts") or {}
        evidence = artifacts.get("schedulerDecisionEvidence") if isinstance(artifacts.get("schedulerDecisionEvidence"), dict) else {}
        classification = evidence.get("placementClassification") if isinstance(evidence.get("placementClassification"), dict) else {}
        for item in classification.get("negativeEvidence") or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                [
                    f"`{scenario_id}`",
                    semantic_value(item.get("category"), "not_declared"),
                    semantic_value(item.get("severity"), "not_declared"),
                    compact_text(item.get("message")),
                    semantic_value(item.get("tenantId"), "all_or_not_declared"),
                    semantic_value(item.get("nodeName"), "not_declared"),
                ]
            )
            if len(rows) >= max_rows:
                break
        if len(rows) >= max_rows:
            break
    if not rows:
        return "No placement negative evidence has been collected yet, or the collected placement was not classified as warning/critical."
    return md_table(
        ["Scenario", "Category", "Severity", "Message", "Tenant", "Node"],
        rows,
    )


def build_default_scheduler_report_sections(entries: dict[str, dict[str, Any]], subheading: str) -> list[str]:
    return [
        f"{subheading} Default-scheduler scenario context",
        "",
        "This table keeps the default-scheduler experimental dimensions explicit: tenant count, worker-node count, latency profile, traffic profile and model mix vary, while hard placement controls remain disabled.",
        "",
        build_default_scheduler_context_table(entries),
        "",
        f"{subheading} Tenant traffic context",
        "",
        "This table exposes the tenant-level traffic configuration used by the multi-tenant Locust runner. It is essential for reading differentiated-traffic scenarios without collapsing tenants into a single aggregate.",
        "",
        build_default_scheduler_tenant_traffic_table(entries),
        "",
        f"{subheading} Scheduler decision table",
        "",
        "This table reports the runtime pod-to-node mapping captured from Kubernetes. It is the primary evidence that links scheduler decisions to latency, throughput and contention observations.",
        "",
        build_default_scheduler_pod_node_table(entries),
        "",
        f"{subheading} Placement classification summary",
        "",
        "This table summarizes placement categories and risk levels derived from scheduler evidence. It is intentionally separate from performance metrics because formally valid placements may still be inefficient for distributed GenAI workloads.",
        "",
        build_default_scheduler_placement_classification_table(entries),
        "",
        f"{subheading} Per-tenant benchmark metrics",
        "",
        "This table reports tenant-scoped Locust measurements when multi-tenant summaries are available. The aggregate scenario tables remain useful, but tenant-level rows are required to detect asymmetric impact.",
        "",
        build_default_scheduler_tenant_metrics_table(entries),
        "",
        f"{subheading} Placement negative evidence",
        "",
        "This table lists warning or critical scheduler-placement evidence such as latency-sensitive splits, tenant interference risk, resource-contention risk, missing workers or unscheduled pods.",
        "",
        build_default_scheduler_negative_evidence_table(entries),
        "",
    ]


def build_resource_aware_scheduler_report_sections(entries: dict[str, dict[str, Any]], subheading: str) -> list[str]:
    return [
        f"{subheading} Scheduler-comparison scenario context",
        "",
        "This table keeps the paired resource-aware-scheduler dimensions explicit: each logical scenario is evaluated with Kubernetes default scheduling and with the load-aware custom scheduler while latency injection remains disabled.",
        "",
        build_default_scheduler_context_table(entries),
        "",
        f"{subheading} Tenant traffic context",
        "",
        "This table exposes the tenant-level traffic configuration used by the multi-tenant Locust runner. It is required to interpret uniform and differentiated traffic pairs without collapsing tenants into a single aggregate.",
        "",
        build_default_scheduler_tenant_traffic_table(entries),
        "",
        f"{subheading} Scheduler decision table",
        "",
        "This table reports the runtime pod-to-node mapping captured from Kubernetes for both default and load-aware variants. It connects scheduler decisions to application performance, resource balance and placement classification.",
        "",
        build_default_scheduler_pod_node_table(entries),
        "",
        f"{subheading} Placement classification summary",
        "",
        "This table summarizes placement categories and risk levels derived from scheduler evidence. It is intentionally distinct from the pairwise performance table because resource-aware scheduling can improve placement quality even when latency is neutral or regressive.",
        "",
        build_default_scheduler_placement_classification_table(entries),
        "",
        f"{subheading} Per-tenant benchmark metrics",
        "",
        "This table reports tenant-scoped Locust measurements when multi-tenant summaries are available. Tenant-level rows are necessary to detect asymmetric effects in paired scheduler experiments.",
        "",
        build_default_scheduler_tenant_metrics_table(entries),
        "",
        f"{subheading} Placement negative evidence",
        "",
        "This table lists warning or critical placement evidence such as tenant interference risk, resource-contention risk, missing workers or unscheduled pods. Empty evidence is reported explicitly rather than inferred from aggregate latency alone.",
        "",
        build_default_scheduler_negative_evidence_table(entries),
        "",
    ]


def build_family_markdown(
    profile: dict[str, Any],
    baseline: dict[str, Any],
    family: str,
    entries: dict[str, dict[str, Any]],
    findings_by_family: dict[str, list[dict[str, Any]]],
    chart_paths: dict[str, list[dict[str, str]]],
    chart_path_prefix: str = "",
    include_title: bool = False,
) -> str:
    display_name = family_display_name(profile, family)
    heading = "#" if include_title else "##"
    subheading = "##" if include_title else "###"
    subsubheading = "###" if include_title else "####"
    ref_id = profile.get("referenceScenarioByFamily", {}).get(family)
    execution = family_execution_status(entries)
    not_executed = execution["status"] == "not_executed"
    lines: list[str] = []
    lines += [
        f"{heading} {display_name}",
        "",
        f"**Execution status:** `{execution['status']}`",
        "",
        f"**Execution note:** {execution['explanation']}",
        "",
        f"**Varied dimension:** {profile.get('variedDimensionByFamily', {}).get(family, family)}",
        "",
        "**Fixed dimensions:** " + ", ".join(profile.get("fixedDimensionsByFamily", {}).get(family, [])) + ".",
        "",
        f"**Reference scenario within the sweep:** `{ref_id}`",
        "",
        md_table(
            ["Scenario count", "Measured", "Unsupported", "Missing"],
            [[execution["scenarioCount"], execution["measuredCount"], execution["unsupportedCount"], execution["missingCount"]]],
        ),
        "",
    ]

    if not_executed:
        lines += [
            f"{subheading} Not executed",
            "",
            "No benchmark results or unsupported-scenario evidence were found for this sweep family. The section is still generated intentionally so that the consolidated reporting package remains structurally complete even when one sweep has not been executed yet.",
            "",
        ]

    lines += [
        f"{subheading} Controlled scenario parameters",
        "",
        "This table is derived from resolved scenario metadata. A parameter is marked as controlled only when it has the same effective value across all scenarios in the sweep.",
        "",
        family_controlled_parameter_summary(family, entries, baseline),
        "",
        f"{subheading} Scenario parameter matrix",
        "",
        family_parameter_matrix(family, entries, baseline, profile),
        "",
        f"{subheading} Measurement summary",
        "",
        "This compact table reports the core indicators used to read the sweep at a glance. Detailed percentiles, deltas and resource snapshots are reported in the following extended table.",
        "",
        build_family_measurement_summary_table(entries, profile, family),
        "",
        f"{subheading} Extended measurement metrics",
        "",
        "This secondary table keeps the additional metrics aligned with the technical diagnosis while avoiding an excessively wide primary summary table.",
        "",
        build_family_extended_metrics_table(entries, profile, family),
        "",
    ]

    if family == "resource-variation":
        lines += [
            f"{subheading} Resource-capacity context",
            "",
            "This table makes the resource-capacity dimension explicit. Model, workload, LocalAI worker count and placement are kept fixed while worker-node CPU and memory capacity change; unsupported variants are reported in the same context to preserve capacity-boundary evidence without introducing a separate asymmetric section.",
            "",
            build_resource_capacity_context_table(entries),
            "",
        ]

    if family == "node-count-variation":
        lines += [
            f"{subheading} Node-count context",
            "",
            "This table makes the infrastructure dimension explicit. The LocalAI worker count, per-node capacity and placement policy are kept fixed while the number of provider worker nodes changes.",
            "",
            build_node_count_context_table(entries),
            "",
        ]

    if family == "placement-variation":
        lines += [
            f"{subheading} Placement context",
            "",
            "This table makes the placement dimension explicit. Infrastructure, model, workload and LocalAI worker count are kept fixed while server and RPC-worker placement changes.",
            "",
            build_placement_variation_context_table(entries),
            "",
        ]

    if family == "latency-injection":
        lines += [
            f"{subheading} Latency-injection context",
            "",
            "This table makes the network-emulation dimension explicit. Infrastructure, model, workload, LocalAI worker count and placement are kept fixed while the injected latency profile changes.",
            "",
            build_latency_injection_context_table(entries),
            "",
        ]

    if family == "multi-tenancy":
        lines += [
            f"{subheading} Tenant topology context",
            "",
            "This table makes the tenant composition explicit. The benchmark target remains the declared primary tenant, while co-tenant clusters expose model-mix, placement and resource-contention context.",
            "",
            build_tenant_topology_context_table(entries),
            "",
        ]

    if family == "network-aware-scheduler":
        lines += build_network_aware_scheduler_report_sections(entries, subheading)

    if family == "resource-aware-scheduler":
        lines += [
            f"{subheading} Scheduler comparison",
            "",
            "This table groups the two scheduler variants of the same logical scenario and reports the observed application and resource deltas. It is intentionally separate from the generic sweep summary so that C8 remains a direct resource-aware scheduler rather than a single undifferentiated scenario list.",
            "",
            build_scheduler_pairwise_table(entries),
            "",
        ]
        lines += build_resource_aware_scheduler_report_sections(entries, subheading)

    if family == "default-scheduler":
        lines += build_default_scheduler_report_sections(entries, subheading)

    family_findings = findings_by_family.get(family, [])
    if family_findings:
        lines += [f"{subheading} Diagnosis-based reading", ""]
        for item in family_findings:
            title = item.get("title") or item.get("id") or item.get("kind")
            implication = item.get("implication")
            confidence = item.get("confidence")
            status = item.get("status")
            prefix = f"- **{title}**"
            meta = ", ".join(v for v in [f"status: `{status}`" if status else None, f"confidence: `{confidence}`" if confidence else None] if v)
            lines.append(prefix + (f" ({meta})." if meta else "."))
            if implication:
                lines.append(f"  - Implication: {implication}")
        lines.append("")
    elif not_executed:
        lines += [
            f"{subheading} Diagnosis-based reading",
            "",
            "No diagnosis findings are available for this sweep because no executed or unsupported scenarios were detected for the family.",
            "",
        ]

    lines += [f"{subheading} Charts", ""]
    if not_executed:
        lines += [
            "The charts are generated as placeholders and will show no measured values until the corresponding sweep is executed.",
            "",
        ]
    for chart in chart_paths.get(family, []):
        chart_path = f"{chart_path_prefix}{chart['path']}"
        lines += [f"{subsubheading} {chart['title']}", "", f"![{chart['title']}]({chart_path})", ""]

    measured_count = execution["measuredCount"]
    unsupported_count = execution["unsupportedCount"]
    lines += [
        f"{subheading} Reading notes",
        "",
        f"- Measured scenarios: **{measured_count}**.",
        f"- Unsupported scenarios under current constraints: **{unsupported_count}**.",
        "- Percentage deltas are computed against the family reference scenario; positive latency deltas indicate worse response time, while positive throughput deltas indicate higher request throughput.",
        "- Unsupported scenarios are infrastructure/constraint observations and must not be interpreted as measured latency regressions.",
        "- A `not_executed` sweep means that neither measurement CSV files nor unsupported-scenario evidence were found for any configured scenario in that family.",
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def build_charts(profile: dict[str, Any], family_data: dict[str, dict[str, Any]], output_dir: Path, charts_dir: Path) -> dict[str, list[dict[str, str]]]:
    chart_paths: dict[str, list[dict[str, str]]] = defaultdict(list)
    for family in profile["familyOrder"]:
        entries = family_data.get(family, {})
        for chart_def in profile.get("chartDefinitions", []):
            metric = chart_def["metric"]
            values = [(entry["label"], metric_mean(entry, metric), entry["status"]) for _, entry in sorted(entries.items(), key=lambda kv: scenario_sort_key(kv[0]))]
            chart_file = charts_dir / family / f"{metric}.svg"
            build_svg_bar_chart(f"{reporting_cycle_id(profile)} — {family_display_name(profile, family)}: {chart_def['title']}", values, chart_def.get("unit", ""), chart_file)
            chart_paths[family].append({"metric": metric, "path": chart_file.relative_to(output_dir).as_posix(), "title": chart_def["title"]})
    return dict(chart_paths)


def build_cross_cycle_baseline_reference_section(baseline: dict[str, Any]) -> str:
    rows = [
        ["Baseline ID", baseline.get("baselineId")],
        ["Model", baseline.get("resolvedModelName")],
        ["Worker count", baseline.get("resolvedWorkerCount")],
        ["Placement", baseline.get("resolvedPlacementType")],
        ["Workload", f"users={baseline.get('resolvedWorkload', {}).get('users')}, spawnRate={baseline.get('resolvedWorkload', {}).get('spawnRate')}, runTime={baseline.get('resolvedWorkload', {}).get('runTime')}"],
        ["Prompt", baseline.get("prompt")],
        ["Request timeout", f"{baseline.get('requestTimeoutSeconds')} s"],
        ["Infrastructure profile", baseline.get("infrastructureProfileId", "NA")],
        ["Placement profile", baseline.get("placementProfileId", "NA")],
    ]
    return "\n".join([
        "## Cross-cycle baseline reference",
        "",
        "The values below describe the global baseline configuration used as a cross-cycle reference. Scenario-specific and sweep-local sections report the effective infrastructure, placement, worker count and runtime configuration used by each scenario. Percentage deltas are computed against the family-local reference scenario when one is defined for the sweep.",
        "",
        md_table(["Dimension", "Reference value"], rows),
    ])


def build_family_reference_scenario_section(profile: dict[str, Any], family_data: dict[str, dict[str, Any]]) -> str:
    rows = []
    reference_by_family = profile.get("referenceScenarioByFamily") or {}
    for family in profile.get("familyOrder", []):
        ref_id = reference_by_family.get(family)
        entries = family_data.get(family, {})
        ref_entry = entries.get(ref_id, {}) if ref_id else {}
        rows.append([
            family_display_name(profile, family),
            f"`{ref_id}`" if ref_id else "not declared",
            ref_entry.get("label", "n/a"),
            ref_entry.get("status", "not_found" if ref_id else "not_declared"),
            profile.get("variedDimensionByFamily", {}).get(family, family),
        ])
    if not rows:
        return ""
    return "\n".join([
        "## Family-local reference scenarios",
        "",
        "The scenarios below are the sweep-local references used to interpret percentage deltas within each family. They may differ from the cross-cycle baseline when a campaign intentionally varies infrastructure, placement, latency or tenancy.",
        "",
        md_table(["Sweep", "Reference scenario", "Description", "Status", "Varied dimension"], rows),
    ])


def build_global_report(
    profile: dict[str, Any],
    baseline: dict[str, Any],
    family_data: dict[str, dict[str, Any]],
    diagnosis_ref: dict[str, Any] | None,
    chart_paths: dict[str, list[dict[str, str]]],
    sweep_report_paths: dict[str, dict[str, str]],
    reporting_context: dict[str, Any] | None = None,
) -> str:
    diagnosis_payload = diagnosis_ref["payload"] if diagnosis_ref else None
    findings_by_family = diagnosis_findings_by_family(diagnosis_payload)
    report_title = global_report_title(profile)
    purpose = profile.get("reportPurposeMarkdown") or "This report provides stakeholder-facing visual summaries of LocalAI worker-mode benchmark campaigns. It is generated after technical diagnosis and before completion-gate evaluation, so that the benchmark cycle is not considered closed until its results are readable and inspectable."
    lines = [
        f"# {report_title}",
        "",
        f"**Cycle ID:** `{reporting_cycle_id(profile)}`",
        f"**Reporting Profile:** `{reporting_profile_id(profile)}`",
        f"**Reporting ID:** `{profile['_runtimeReportingId']}`",
        f"**Generated at UTC:** `{profile['_runtimeCreatedAtUtc']}`",
        "",
    ]
    historical_context = bool(reporting_context and is_historical_fixed_cluster_profile(profile, reporting_context))
    evidence_sentence = (
        "The report combines **measurement CSV data**, **cluster-capture evidence**, **scenario configuration metadata** and **technical diagnosis context** when those artifacts are available."
        if historical_context
        else "The report combines **measurement CSV data**, **minimal observability evidence**, **cluster validation outputs**, **application topology metadata** and **technical diagnosis context** when those artifacts are available."
    )
    cluster_side_source = "`cluster capture artifacts`" if historical_context else "`minimal observability and cluster capture artifacts`"
    lines += ["## Purpose", "", purpose, "", evidence_sentence, ""]
    cycle_index_link = profile.get("cycleReportIndexLink", "../../../reporting/index.html")
    lines += [f"[Back to cycle report index]({cycle_index_link})", ""]
    lines += [build_cross_cycle_baseline_reference_section(baseline), "", build_family_reference_scenario_section(profile, family_data), ""]
    data_source_root = profile.get("outputRoot", "results/experimental-cycles/C0/reporting")
    lines += ["## Data sources", "", md_table(["Layer", "Primary use", "Source"], [["Measurement CSV", "Quantitative charts and scenario summary metrics", "`" + json.dumps(campaign_results_roots(profile), ensure_ascii=False) + "`"], ["Technical diagnosis", "Interpretation, family judgments, findings, unsupported-scenario context", f"`{diagnosis_ref['path']}`" if diagnosis_ref else "not available"], ["Scenario configuration", "Fixed/varied dimensions and scenario labels", "`config/scenarios/**`"], ["Cluster-side artifacts", "CPU/memory snapshots, pod placement and event evidence", cluster_side_source], ["Reporting output", "Current generated report package", f"`{data_source_root}`"]]), ""]
    if reporting_context and is_historical_fixed_cluster_profile(profile, reporting_context):
        lines.append(build_historical_context_markdown_sections(profile, baseline, family_data, diagnosis_payload, reporting_context).strip())
        lines.append("")
    elif reporting_context and reporting_context.get("enabled"):
        lines.append(build_context_markdown_sections(profile, baseline, family_data, diagnosis_payload, reporting_context).strip())
        lines.append("")

    lines += ["## Sweep-specific reports", "", "The global report below provides the stakeholder-facing overview. Each sweep also has a dedicated report for focused inspection of one varied dimension.", ""]
    sweep_rows = []
    for family in profile["familyOrder"]:
        display_name = family_display_name(profile, family)
        paths = sweep_report_paths.get(family, {})
        execution = family_execution_status(family_data.get(family, {}))
        sweep_rows.append([
            display_name,
            f"[{family}]({paths.get('htmlReport', '')})",
            execution["status"],
            f"measured={execution['measuredCount']}, unsupported={execution['unsupportedCount']}, missing={execution['missingCount']}",
            profile.get("variedDimensionByFamily", {}).get(family, family),
        ])
    lines += [md_table(["Sweep", "Dedicated HTML report", "Execution status", "Coverage", "Varied dimension"], sweep_rows), ""]

    if diagnosis_payload:
        coverage = diagnosis_payload.get("coverage") or {}
        coverage_rows = []
        for family in profile["familyOrder"]:
            item = coverage.get(family) or {}
            coverage_rows.append([family, item.get("scenarioCount"), item.get("scenariosObserved"), item.get("scenariosWithSamples"), item.get("scenariosWithUnsupportedEvidence"), item.get("sampleCount")])
        lines += ["## Diagnosis coverage snapshot", "", md_table(["Family", "Scenarios", "Observed", "Measured", "Unsupported", "Samples"], coverage_rows), ""]

    for family in profile["familyOrder"]:
        lines.append(build_family_markdown(profile, baseline, family, family_data.get(family, {}), findings_by_family, chart_paths, chart_path_prefix="", include_title=False).strip())
        lines.append("")

    for note in profile.get("notes", []):
        lines.append(f"> {note}")
    return "\n".join(lines).strip() + "\n"


def build_placement_variation_context_table(entries: dict[str, dict[str, Any]]) -> str:
    rows = []
    for scenario_id, entry in sorted(entries.items(), key=lambda item: scenario_sort_key(item[0])):
        scenario = entry.get("scenario") or {}
        variant = scenario.get("placementVariant") or {}
        rows.append([
            f"`{scenario_id}`",
            variant.get("label") or scenario.get("scenarioLabel") or "NA",
            scenario.get("placementProfileId") or variant.get("placementProfileId") or "NA",
            scenario.get("expectedServerNode") or variant.get("serverNode") or "NA",
            compact_list(scenario.get("expectedWorkerNodes") or variant.get("workerNodeMap")),
            variant.get("expectedCommunicationDistance") or "NA",
            variant.get("expectedResourceContention") or "NA",
        ])
    if not rows:
        rows = [["NA", "NA", "NA", "NA", "NA", "NA", "NA"]]
    return md_table(["Scenario", "Placement", "Profile", "Server node", "Worker node map", "Communication distance", "Resource contention"], rows)


def build_sweep_report(
    profile: dict[str, Any],
    baseline: dict[str, Any],
    family: str,
    entries: dict[str, dict[str, Any]],
    diagnosis_ref: dict[str, Any] | None,
    chart_paths: dict[str, list[dict[str, str]]],
) -> str:
    diagnosis_payload = diagnosis_ref["payload"] if diagnosis_ref else None
    findings_by_family = diagnosis_findings_by_family(diagnosis_payload)
    display_name = family_display_name(profile, family)
    report_title = family_report_title(profile, family)
    lines = [
        f"# {report_title}",
        "",
        f"**Cycle ID:** `{reporting_cycle_id(profile)}`",
        f"**Sweep:** `{family}`",
        f"**Reporting Profile:** `{reporting_profile_id(profile)}`",
        f"**Reporting ID:** `{profile['_runtimeReportingId']}`",
        f"**Generated at UTC:** `{profile['_runtimeCreatedAtUtc']}`",
        "",
        "[Back to cycle report](../../index.html)",
        "",
        "## Scope",
        "",
        f"This sweep-specific report isolates **{display_name}** so that the varied dimension, fixed dimensions, measured values, unsupported evidence and diagnosis-based reading can be inspected without navigating the full consolidated report.",
        "",
    ]
    lines.append(build_family_markdown(profile, baseline, family, entries, findings_by_family, chart_paths, chart_path_prefix="../../", include_title=False).strip())
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def markdown_to_basic_html_page(markdown: str, page_title: str = "Consolidated Pilot Reporting") -> str:
    def render_inline(text: str) -> str:
        escaped = html.escape(text)
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
        return escaped

    out, in_ul, in_table, table_buffer = [], False, False, []

    def flush_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>"); in_ul = False

    def flush_table():
        nonlocal in_table, table_buffer
        if not in_table:
            return
        rows = table_buffer
        if len(rows) >= 2:
            out.append("<table>")
            header = [c.strip() for c in rows[0].strip("|").split("|")]
            out.append("<thead><tr>" + "".join(f"<th>{render_inline(c)}</th>" for c in header) + "</tr></thead><tbody>")
            for row in rows[2:]:
                cells = [c.strip() for c in row.strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{render_inline(c)}</td>" for c in cells) + "</tr>")
            out.append("</tbody></table>")
        table_buffer, in_table = [], False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("|") and line.endswith("|"):
            flush_ul(); in_table = True; table_buffer.append(line); continue
        flush_table()
        if not line:
            flush_ul(); continue
        if line.startswith("# "):
            flush_ul(); out.append(f"<h1>{render_inline(line[2:])}</h1>")
        elif line.startswith("## "):
            flush_ul(); out.append(f"<h2>{render_inline(line[3:])}</h2>")
        elif line.startswith("### "):
            flush_ul(); out.append(f"<h3>{render_inline(line[4:])}</h3>")
        elif line.startswith("#### "):
            flush_ul(); out.append(f"<h4>{render_inline(line[5:])}</h4>")
        elif line.startswith("- "):
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append(f"<li>{render_inline(line[2:])}</li>")
        elif line.startswith("  - "):
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append(f"<li>{render_inline(line[4:])}</li>")
        elif line.startswith("> "):
            flush_ul(); out.append(f"<blockquote>{render_inline(line[2:])}</blockquote>")
        elif line.startswith("!["):
            match = re.match(r"!\[(.*?)\]\((.*?)\)", line)
            if match:
                flush_ul(); out.append(f"<img src=\"{html.escape(match.group(2))}\" alt=\"{html.escape(match.group(1))}\">")
        else:
            flush_ul()
            out.append(f"<p>{render_inline(line)}</p>")
    flush_table(); flush_ul()
    body = "\n".join(out)
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{html.escape(page_title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 1180px; margin: 32px auto; line-height: 1.5; padding: 0 24px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0 28px; font-size: 14px; display: block; overflow-x: auto; }}
    th, td {{ border: 1px solid #d0d0d0; padding: 7px 9px; vertical-align: top; }}
    th {{ background: #f2f2f2; }}
    code {{ background: #f6f6f6; padding: 1px 4px; }}
    img {{ max-width: 100%; border: 1px solid #e0e0e0; margin: 8px 0 24px; }}
    blockquote {{ border-left: 4px solid #999; padding-left: 12px; color: #333; }}
    a {{ color: #0645ad; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def resolve_current_reporting_id(output_dir: Path, profile: dict[str, Any]) -> str:
    manifest_path = output_dir / profile.get("manifestName", "reporting-manifest.json")
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Current reporting manifest not found: {manifest_path}. "
            "Run reporting first, then archive the current report."
        )
    manifest = load_json(manifest_path)
    reporting = manifest.get("reporting") or {}
    reporting_id = reporting.get("reportingId") or manifest.get("reportingId")
    if not reporting_id:
        created_at = reporting.get("createdAtUtc") or manifest.get("createdAtUtc")
        if created_at:
            try:
                dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).astimezone(timezone.utc)
                reporting_id = default_reporting_id(profile, dt)
            except Exception:
                reporting_id = None
    if not reporting_id:
        raise ValueError(
            f"Unable to resolve reportingId from current reporting manifest: {manifest_path}. "
            "The report cannot be archived safely without a logical identifier."
        )
    return str(reporting_id)


def copy_reporting_archive(output_dir: Path, archive_dir: Path, profile: dict[str, Any], *, force: bool = False) -> list[str]:
    if archive_dir.exists():
        if not force:
            raise FileExistsError(
                f"Archive directory already exists: {archive_dir}. "
                "Use --force-archive only if you intentionally want to replace it."
            )
        shutil.rmtree(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=False)
    copied: list[str] = []
    managed_file_names = [
        profile.get("reportMarkdownName", "report.md"),
        profile.get("reportHtmlName", "index.html"),
        profile.get("summaryCsvName", "scenario-summary.csv"),
        profile.get("manifestName", "reporting-manifest.json"),
    ]
    for name in managed_file_names:
        src = output_dir / name
        if src.exists():
            shutil.copy2(src, archive_dir / name)
            copied.append(name)
    for name in [profile.get("chartsDirectoryName", "charts"), profile.get("sweepsDirectoryName", "sweeps")]:
        src = output_dir / name
        if src.exists():
            dst = archive_dir / name
            shutil.copytree(src, dst)
            copied.append(name + "/")
    return copied


def remove_managed_outputs(output_dir: Path, profile: dict[str, Any]) -> None:
    managed_file_names = [
        profile.get("reportMarkdownName", "report.md"),
        profile.get("reportHtmlName", "index.html"),
        profile.get("summaryCsvName", "scenario-summary.csv"),
        profile.get("manifestName", "reporting-manifest.json"),
    ]
    for managed_file_name in managed_file_names:
        managed_file = output_dir / managed_file_name
        if managed_file.exists():
            managed_file.unlink()
    for managed_dir_name in [profile.get("chartsDirectoryName", "charts"), profile.get("sweepsDirectoryName", "sweeps")]:
        managed_dir = output_dir / managed_dir_name
        if managed_dir.exists():
            for nested in sorted(managed_dir.rglob("*"), reverse=True):
                if nested.is_file():
                    nested.unlink()
                elif nested.is_dir():
                    nested.rmdir()
            managed_dir.rmdir()


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    profile_path = Path(args.profile_config).resolve()
    profile = load_json(profile_path)
    if args.archive and args.archive_current:
        raise ValueError("--archive and --archive-current are mutually exclusive. Use --archive to regenerate and archive, or --archive-current to archive the existing report as-is.")

    output_root = Path(args.output_root).resolve()
    output_dir = output_root

    if args.archive_current:
        current_reporting_id = resolve_current_reporting_id(output_dir, profile)
        archive_dir = output_dir / profile.get("archiveDirectoryName", "archive") / current_reporting_id
        archived_items = copy_reporting_archive(output_dir, archive_dir, profile, force=bool(args.force_archive))
        print("Current reporting package archived successfully.")
        print(f"Output directory : {output_dir}")
        print(f"Reporting ID     : {current_reporting_id}")
        print(f"Archive copy     : {archive_dir}")
        print(f"Archived items   : {', '.join(archived_items) if archived_items else 'none'}")
        return

    reporting_id = args.reporting_id.strip()
    created_at = datetime.now(timezone.utc)
    if not reporting_id:
        reporting_id = default_reporting_id(profile, created_at)
    args.reporting_id = reporting_id
    profile["_runtimeReportingId"] = reporting_id
    profile["_runtimeCreatedAtUtc"] = utc_timestamp_iso(created_at)

    baseline = load_json(repo_root / profile["baselineConfig"])
    diagnosis_ref = discover_latest_diagnosis(repo_root, repo_root / profile.get("technicalDiagnosisRoot", "results/experimental-cycles/C0/diagnosis"), "all")
    diagnosis_payload = diagnosis_ref["payload"] if diagnosis_ref else None
    family_data = {family: discover_family(repo_root, profile, family, diagnosis_payload) for family in profile["familyOrder"]}
    charts_dir = output_dir / profile.get("chartsDirectoryName", "charts")
    sweeps_dir = output_dir / profile.get("sweepsDirectoryName", "sweeps")
    output_dir.mkdir(parents=True, exist_ok=True)
    remove_managed_outputs(output_dir, profile)

    summary_rows = build_summary_rows(family_data, profile)
    summary_csv = output_dir / profile.get("summaryCsvName", "scenario-summary.csv")
    write_csv(summary_csv, summary_rows)

    chart_paths = build_charts(profile, family_data, output_dir, charts_dir)

    sweep_report_paths: dict[str, dict[str, str]] = {}
    for family in profile["familyOrder"]:
        family_dir = sweeps_dir / family
        family_dir.mkdir(parents=True, exist_ok=True)
        family_markdown = build_sweep_report(profile, baseline, family, family_data.get(family, {}), diagnosis_ref, chart_paths)
        family_markdown_path = family_dir / profile.get("reportMarkdownName", "report.md")
        family_html_path = family_dir / profile.get("reportHtmlName", "index.html")
        family_markdown_path.write_text(normalize_artifact_text_for_output(family_markdown, family_markdown_path), encoding="utf-8")
        family_html_path.write_text(normalize_artifact_text_for_output(markdown_to_basic_html_page(family_markdown, family_report_title(profile, family)), family_html_path), encoding="utf-8")
        sweep_report_paths[family] = {
            "markdownReport": family_markdown_path.relative_to(output_dir).as_posix(),
            "htmlReport": family_html_path.relative_to(output_dir).as_posix(),
        }

    reporting_context = build_reporting_context(repo_root, profile)
    profile["_runtimeReportingContext"] = reporting_context

    global_markdown = build_global_report(profile, baseline, family_data, diagnosis_ref, chart_paths, sweep_report_paths, reporting_context)
    markdown_path = output_dir / profile.get("reportMarkdownName", "report.md")
    html_path = output_dir / profile.get("reportHtmlName", "index.html")
    manifest_path = output_dir / profile.get("manifestName", "reporting-manifest.json")
    markdown_path.write_text(normalize_artifact_text_for_output(global_markdown, markdown_path), encoding="utf-8")
    html_path.write_text(normalize_artifact_text_for_output(markdown_to_basic_html_page(global_markdown, global_report_title(profile)), html_path), encoding="utf-8")

    archive_dir = output_dir / profile.get("archiveDirectoryName", "archive") / args.reporting_id if args.archive else None
    manifest = {
        "reportingProfile": {"profileId": profile.get("profileId"), "profileFile": safe_rel(profile_path, repo_root), "description": profile.get("description")},
        "reporting": {"reportingId": args.reporting_id, "createdAtUtc": profile["_runtimeCreatedAtUtc"], "cycleId": reporting_cycle_id(profile), "reportingProfileId": reporting_profile_id(profile), "reportTitle": global_report_title(profile), "outputDirectory": safe_rel(output_dir, repo_root), "familyScope": "all", "pipelinePosition": "after_technical_diagnosis_before_completion_gate"},
        "baseline": baseline,
        "latestAllFamilyDiagnosis": diagnosis_ref["path"] if diagnosis_ref else None,
        "dataSourcePolicy": {"quantitativeCharts": "measurement_csv_when_available", "interpretation": "latest_technical_diagnosis_when_available", "scenarioMetadata": "scenario_configuration_files", "minimalObservability": "latest_minimal_observability_snapshot_when_available", "providerContext": "cycle_and_provider_profile_documents_when_available"},
        "reportingContext": reporting_context,
        "artifacts": {"markdownReport": safe_rel(markdown_path, repo_root), "htmlReport": safe_rel(html_path, repo_root), "scenarioSummaryCsv": safe_rel(summary_csv, repo_root), "charts": chart_paths, "sweepReports": sweep_report_paths},
        "archive": {"enabled": bool(args.archive), "archiveDirectory": safe_rel(archive_dir, repo_root) if archive_dir else None},
        "familyData": family_data,
    }
    write_json(manifest_path, manifest)
    archived_items: list[str] = []
    if archive_dir is not None:
        archived_items = copy_reporting_archive(output_dir, archive_dir, profile, force=bool(args.force_archive))
    print("Reporting artifacts generated successfully.")
    print(f"Output directory : {output_dir}")
    print(f"Markdown report  : {markdown_path}")
    print(f"HTML report      : {html_path}")
    print(f"Summary CSV      : {summary_csv}")
    print(f"Manifest         : {manifest_path}")
    print(f"Sweep reports    : {sweeps_dir}")
    if archive_dir is not None:
        print(f"Archive copy     : {archive_dir}")
        print(f"Archived items   : {', '.join(archived_items) if archived_items else 'none'}")


if __name__ == "__main__":
    main()
