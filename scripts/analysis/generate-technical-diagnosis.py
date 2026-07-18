#!/usr/bin/env python
import argparse
import csv
import json
import re
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

METRIC_UNITS = {
    "request_count": "requests",
    "failure_count": "failures",
    "mean_response_time_ms": "ms",
    "p50_response_time_ms": "ms",
    "p95_response_time_ms": "ms",
    "p99_response_time_ms": "ms",
    "throughput_rps": "requests/s",
    "success_rate_percent": "%",
    "maxNodeCpuPercentObserved": "%",
    "maxNodeMemoryPercentObserved": "%",
}

DEFAULT_FAMILY_ORDER = ["worker-count", "workload", "models", "placement", "resource-variation", "node-count-variation", "placement-variation", "latency-injection", "multi-tenancy", "default-scheduler", "resource-aware-scheduler", "network-aware-scheduler"]
FAMILY_ORDER = DEFAULT_FAMILY_ORDER


def to_number(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def metric_mean(summary, metric_key):
    if not summary:
        return None
    return (summary.get("metrics") or {}).get(metric_key, {}).get("mean")


def scenario_metric_snapshot(summary):
    return {
        "mean_response_time_ms": metric_mean(summary, "mean_response_time_ms"),
        "p50_response_time_ms": metric_mean(summary, "p50_response_time_ms"),
        "p95_response_time_ms": metric_mean(summary, "p95_response_time_ms"),
        "p99_response_time_ms": metric_mean(summary, "p99_response_time_ms"),
        "throughput_rps": metric_mean(summary, "throughput_rps"),
        "max_node_cpu_percent": summary.get("maxNodeCpuPercentObserved") if summary else None,
        "max_node_memory_percent": summary.get("maxNodeMemoryPercentObserved") if summary else None,
    }


def compact_metric_snapshot(snapshot):
    return {key: value for key, value in snapshot.items() if value is not None}


def load_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def resolve_artifact_path(repo_root: Path, value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.exists():
        return candidate
    if not candidate.is_absolute():
        repo_candidate = repo_root / candidate
        if repo_candidate.exists():
            return repo_candidate
        return repo_candidate

    normalized = text.replace("\\", "/")
    marker = "/localai-worker-mode-benchmark-suite/"
    if marker in normalized:
        suffix = normalized.split(marker, 1)[1]
        return repo_root / suffix
    return candidate


def read_json_optional(path: Path | None):
    if path is None or not path.exists():
        return None
    try:
        return load_json(path)
    except Exception:
        return None


def resolve_validation_summary_path(repo_root: Path, configured_relative_path: Any) -> tuple[Path, str, Path | None]:
    configured_text = str(configured_relative_path or "").strip()
    configured_path = repo_root / configured_text if configured_text else repo_root
    if configured_path.exists():
        return configured_path, "configured_path", None

    search_roots: list[Path] = []
    if configured_path.parent.exists():
        search_roots.append(configured_path.parent)

    fallback_candidates: list[Path] = []
    for search_root in search_roots:
        for candidate in search_root.glob("*diagnosis*.json"):
            if candidate.name.startswith("latest-"):
                continue
            if candidate.is_file():
                fallback_candidates.append(candidate)

    if fallback_candidates:
        fallback_candidates.sort(key=lambda item: (item.stat().st_mtime, item.name), reverse=True)
        return fallback_candidates[0], "latest_diagnosis_in_configured_directory", configured_path

    return configured_path, "missing", configured_path


def text_tokens_from_any(value):
    tokens = []
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


def classify_evidence_text(text):
    evidence_kinds = set()
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


def read_related_deployment_manifest(repo_root: Path, unsupported_payload):
    evidence = unsupported_payload.get("evidence")
    manifest_path_value = None
    if isinstance(evidence, dict):
        manifest_path_value = evidence.get("deploymentManifestPath")
    manifest_path = resolve_artifact_path(repo_root, manifest_path_value)
    manifest = read_json_optional(manifest_path)
    return manifest_path, manifest


def deployment_manifest_event_texts(repo_root: Path, manifest):
    if not isinstance(manifest, dict):
        return []
    texts = []
    texts.extend(text_tokens_from_any(manifest.get("errors")))
    for rollout in manifest.get("rolloutChecks") or []:
        texts.extend(text_tokens_from_any(rollout.get("deployment")))
        if rollout.get("success") is False:
            texts.append(f"Rollout check failed for deployment/{rollout.get('deployment')}")
    snapshots = manifest.get("snapshots") or {}
    candidate_paths = []
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
    seen = set()
    for path in candidate_paths:
        if path is None:
            continue
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        if str(resolved) in seen or not path.exists() or not path.is_file():
            continue
        seen.add(str(resolved))
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line in content.splitlines():
            if any(token in line.lower() for token in ["failedscheduling", "insufficient", "affinity/selector", "preemption", "rollout", "pending"]):
                texts.append(line.strip())
    return texts


def infer_finding_family(finding_id):
    text = str(finding_id or "")
    prefix_map = {
        "resource_variation": "resource-variation",
        "node_count_variation": "node-count-variation",
        "placement_variation": "placement-variation",
        "latency_injection": "latency-injection",
        "multi_tenancy": "multi-tenancy",
        "default_scheduler": "default-scheduler",
        "resource_aware_scheduler": "resource-aware-scheduler",
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
        if text.startswith(prefix):
            return family
    return "general"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate a first technical diagnosis from pilot benchmark results.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--profile-config", required=True)
    parser.add_argument("--family", default="all", choices=["all", "baseline", "worker-count", "workload", "models", "placement", "resource-variation", "node-count-variation", "placement-variation", "latency-injection", "multi-tenancy", "default-scheduler", "resource-aware-scheduler", "network-aware-scheduler"])
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-text", required=True)
    parser.add_argument("--diagnosis-id", required=True)
    return parser.parse_args()


def find_target_row(stats_csv: Path, target_type: str, target_name: str, fallback: bool):
    with stats_csv.open("r", encoding="utf-8", newline="") as fh:
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
        "classificationRule": "diagnosis_rejected_invalid_measurement_csv",
        "failureClass": "measurement_produced_no_valid_target_requests",
        "statsCsvPath": str(stats_file),
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


def parse_replica(stem: str):
    patterns = [
        re.compile(r"(?:^|[_-])run([ABC])(?:[_-]|$)"),
        re.compile(r"(?:^|[_-])([ABC])(?:[_-])\d{8}T\d{6}Z(?:[_-]|$)"),
        re.compile(r"(?:^|[_-])([ABC])(?:[_-]|$)"),
    ]
    for pattern in patterns:
        match = pattern.search(stem)
        if match:
            return match.group(1)
    return "NA"


def parse_top_nodes(path: Path):
    if not path.exists():
        return None
    max_cpu = None
    max_mem = None
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("NAME"):
                continue
            parts = re.split(r"\s+", line)
            if len(parts) < 5:
                continue
            cpu = parts[2].rstrip("%")
            mem = parts[4].rstrip("%")
            if cpu.isdigit():
                value = float(cpu)
                max_cpu = value if max_cpu is None else max(max_cpu, value)
            if mem.isdigit():
                value = float(mem)
                max_mem = value if max_mem is None else max(max_mem, value)
    return {"maxNodeCpuPercent": max_cpu, "maxNodeMemoryPercent": max_mem}


def discover_measurement_stats(search_root: Path):
    files = []
    if not search_root.exists():
        return files
    for stats_file in search_root.rglob("*_stats.csv"):
        name = stats_file.name
        if name.endswith("_stats_history.csv"):
            continue
        if "_warmup_" in name or "warmup" in stats_file.stem.lower():
            continue
        files.append(stats_file)
    return sorted(files)


def discover_unsupported_reports(search_root: Path):
    files = []
    if not search_root.exists():
        return files
    for unsupported_file in search_root.rglob("*_unsupported.json"):
        files.append(unsupported_file)
    return sorted(files)


def parse_scenario_and_replica_from_unsupported(path: Path):
    match = re.match(r"(?P<scenario>.+)_run(?P<replica>[ABC])_unsupported$", path.stem)
    if not match:
        return None, "NA"
    return match.group("scenario"), match.group("replica")


def derive_unsupported_evidence_kinds(payload, repo_root: Path | None = None):
    evidence_kinds = set()

    raw_evidence = payload.get("evidence")
    for token in text_tokens_from_any(raw_evidence):
        evidence_kinds.update(classify_evidence_text(token))
        if is_compact_evidence_token(token):
            evidence_kinds.add(token.strip())

    if payload.get("reason"):
        evidence_kinds.update(classify_evidence_text(payload.get("reason")))
    if payload.get("stage"):
        evidence_kinds.add(str(payload.get("stage")).strip())

    diagnostics = payload.get("diagnostics") or []
    for diagnostic in diagnostics:
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


def summarize_samples(samples):
    if not samples:
        return None
    summary = {
        "sampleCount": len(samples),
        "replicas": [sample["replica"] for sample in samples],
        "metrics": {},
    }
    for metric_key in METRIC_KEYS:
        values = [sample[metric_key] for sample in samples if sample.get(metric_key) is not None]
        if not values:
            continue
        avg_value = mean(values)
        min_value = min(values)
        max_value = max(values)
        stddev_value = pstdev(values) if len(values) > 1 else 0.0
        cv_value = (stddev_value / avg_value) * 100 if avg_value not in (0, None) else 0.0
        summary["metrics"][metric_key] = {
            "mean": round(avg_value, 4),
            "min": round(min_value, 4),
            "max": round(max_value, 4),
            "stddev": round(stddev_value, 4),
            "coefficientOfVariationPercent": round(cv_value, 4),
        }
    cpu_values = [sample.get("maxNodeCpuPercent") for sample in samples if sample.get("maxNodeCpuPercent") is not None]
    mem_values = [sample.get("maxNodeMemoryPercent") for sample in samples if sample.get("maxNodeMemoryPercent") is not None]
    if cpu_values:
        summary["maxNodeCpuPercentObserved"] = round(max(cpu_values), 2)
    if mem_values:
        summary["maxNodeMemoryPercentObserved"] = round(max(mem_values), 2)
    return summary


def scenario_identifier(payload, fallback: str):
    return payload.get("scenarioId") or payload.get("baselineId") or fallback


def configured_scenario_files(repo_root: Path, profile, family_name: str, scenario_root: Path):
    explicit_files = (profile.get("scenarioConfigFiles") or {}).get(family_name) or []
    files = []
    for item in explicit_files:
        path = Path(item)
        files.append(path if path.is_absolute() else repo_root / path)
    if files:
        return files
    if scenario_root.exists():
        return sorted(scenario_root.glob("*.json"))
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


def synthetic_unsupported_reports_from_campaign(repo_root: Path, profile: dict[str, Any], family_name: str, scenario_id: str, scenario_payload: dict[str, Any], search_roots: list[Path]) -> list[dict[str, Any]]:
    campaign_cfg = profile.get("campaignAwareDiagnosis") or {}
    if not campaign_cfg.get("enabled"):
        return []
    if family_name != "latency-injection":
        return []
    campaign_manifest_path = resolve_artifact_path(repo_root, campaign_cfg.get("campaignExecutionManifest"))
    campaign_manifest = read_json_optional(campaign_manifest_path) or {}
    variant = None
    for item in campaign_manifest.get("variantResults") or []:
        if item.get("variantId") == scenario_id:
            variant = item
            break
    if not variant or variant.get("unsupportedScenario"):
        return []
    if str(variant.get("status")) not in {"failed", "failed_benchmark"}:
        return []
    execution_manifest_path = resolve_artifact_path(repo_root, variant.get("variantExecutionManifest"))
    execution_manifest = read_json_optional(execution_manifest_path) or {}
    if str(execution_manifest.get("status")) not in {"failed", "failed_benchmark"}:
        return []
    steps = execution_manifest.get("steps") or []
    latency_applied = any(step.get("name") == "apply_latency_profile" and step.get("status") == "completed" for step in steps)
    latency_reset = any(step.get("name") == "reset_latency_profile" and step.get("status") == "completed" for step in steps)
    failed_replicas = []
    for step in steps:
        name = str(step.get("name") or "")
        if name.startswith("run_baseline_") and step.get("status") == "failed":
            failed_replicas.append(name.replace("run_baseline_", "", 1))
    if not latency_applied or not failed_replicas:
        return []
    reports: list[dict[str, Any]] = []
    for replica in failed_replicas:
        root = next((candidate for candidate in search_roots if (candidate / f"{scenario_id}_run{replica}_precheck_precheck.json").exists() or (candidate / f"{scenario_id}_run{replica}_precheck.json").exists()), search_roots[0] if search_roots else None)
        if root is None:
            continue
        measurement_stats = root / f"{scenario_id}_run{replica}_stats.csv"
        precheck_json = root / f"{scenario_id}_run{replica}_precheck_precheck.json"
        if not precheck_json.exists():
            precheck_json = root / f"{scenario_id}_run{replica}_precheck.json"
        precheck_payload = read_json_optional(precheck_json) or {}
        precheck_success = (precheck_payload.get("summary") or {}).get("success")
        if measurement_stats.exists() or precheck_success is False:
            continue
        evidence = {
            "classificationRule": "diagnosis_recovered_latency_pre_benchmark_failure",
            "failureClass": "api_smoke_or_pre_benchmark_api_unavailable",
            "campaignExecutionManifest": str(campaign_manifest_path) if campaign_manifest_path else None,
            "variantExecutionManifest": str(execution_manifest_path) if execution_manifest_path else None,
            "latencyProfileApplied": latency_applied,
            "latencyProfileReset": latency_reset,
            "precheckJson": str(precheck_json) if precheck_json.exists() else None,
            "precheckSuccess": precheck_success,
            "measurementStatsPresent": measurement_stats.exists(),
            "latencyProfileId": scenario_payload.get("latencyProfileId") or (scenario_payload.get("latencyVariant") or {}).get("latencyProfileId"),
            "latencyVariant": scenario_payload.get("latencyVariant") or {},
        }
        reports.append({
            "replica": replica,
            "unsupportedJsonPath": None,
            "status": "unsupported_under_current_constraints",
            "reason": "latency_profile_pre_benchmark_api_unavailable",
            "evidence": evidence,
            "evidenceKinds": derive_unsupported_evidence_kinds({"reason": "latency_profile_pre_benchmark_api_unavailable", "stage": "latency_injection_pre_benchmark", "evidence": evidence}, repo_root),
            "timeoutSeconds": scenario_payload.get("requestTimeoutSeconds"),
            "model": scenario_payload.get("resolvedModelName"),
        })
    return reports


def campaign_results_roots(profile):
    roots = profile.get("campaignResultsRoots")
    if isinstance(roots, dict):
        return roots
    return {}


def campaign_results_root(repo_root: Path, profile, family_name: str) -> Path:
    roots = campaign_results_roots(profile)
    if family_name not in roots:
        raise KeyError(f"No benchmark results root declared for family '{family_name}'. Expected campaignResultsRoots[{family_name!r}].")
    return repo_root / roots[family_name]


def existing_path_or_none(path: Path | None) -> Path | None:
    if path is None:
        return None
    return path if path.exists() else None


def discover_named_json(search_roots: list[Path], names: list[str]) -> tuple[Path | None, dict[str, Any] | None]:
    candidates: list[Path] = []
    for root in search_roots:
        for name in names:
            candidates.append(root / name)
        if root.exists():
            for name in names:
                candidates.extend(sorted(root.rglob(name)))
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if not candidate.exists() or not candidate.is_file():
            continue
        payload = read_json_optional(candidate)
        if isinstance(payload, dict):
            return candidate, payload
    return None, None


def latest_scheduler_evidence_aliases(artifact_name: str) -> list[str]:
    aliases = ["latest-default-scheduler-decision-evidence.json"]
    if artifact_name != "default-scheduler-decision-evidence.json":
        stem = artifact_name[:-5] if artifact_name.endswith(".json") else artifact_name
        aliases.insert(0, f"latest-{stem}.json")
    return aliases


def discover_scheduler_decision_evidence(repo_root: Path, profile: dict[str, Any], scenario_id: str, scenario_payload: dict[str, Any]) -> tuple[Path | None, dict[str, Any] | None]:
    scheduler_cfg = scenario_payload.get("schedulerEvidence") or {}
    artifact_name = (
        scheduler_cfg.get("artifactName")
        or profile.get("schedulerDecisionEvidenceArtifactName")
        or "default-scheduler-decision-evidence.json"
    )
    artifact_root_value = scheduler_cfg.get("artifactRoot")
    candidates: list[Path] = []
    if artifact_root_value:
        artifact_root = resolve_artifact_path(repo_root, artifact_root_value)
        if artifact_root is not None:
            candidates.append(artifact_root / artifact_name)
            for latest_alias in latest_scheduler_evidence_aliases(artifact_name):
                candidates.append(artifact_root / latest_alias)
    profile_root_value = profile.get("schedulerDecisionEvidenceRoot") or (profile.get("campaignAwareDiagnosis") or {}).get("schedulerDecisionEvidenceRoot")
    if profile_root_value:
        profile_root = resolve_artifact_path(repo_root, profile_root_value)
        if profile_root is not None:
            candidates.append(profile_root / scenario_id / artifact_name)
            for latest_alias in latest_scheduler_evidence_aliases(artifact_name):
                candidates.append(profile_root / scenario_id / latest_alias)
            if profile_root.exists():
                scenario_root = profile_root / scenario_id
                candidates.extend(sorted(scenario_root.rglob(artifact_name)) if scenario_root.exists() else [])
                for latest_alias in latest_scheduler_evidence_aliases(artifact_name):
                    candidates.extend(sorted(scenario_root.rglob(latest_alias)) if scenario_root.exists() else [])
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_file():
            payload = read_json_optional(candidate)
            if isinstance(payload, dict):
                return candidate, payload
    return None, None


def tenant_measurements_from_multi_tenant_summary(summary_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(summary_payload, dict):
        return []
    measurements: list[dict[str, Any]] = []
    for item in summary_payload.get("tenantResults") or []:
        if not isinstance(item, dict):
            continue
        measurement = item.get("measurement") or {}
        artifacts = item.get("artifacts") or {}
        replica_value = item.get("replica") or item.get("replicaId")
        measurements.append({
            "replica": replica_value,
            "replicaId": item.get("replicaId") or (f"run{replica_value}" if replica_value else None),
            "tenantId": item.get("tenantId"),
            "namespace": item.get("namespace"),
            "status": item.get("status"),
            "exitCode": item.get("exitCode"),
            "modelName": item.get("modelName"),
            "users": item.get("users"),
            "spawnRate": item.get("spawnRate"),
            "runTime": item.get("runTime"),
            "waitTimeSeconds": item.get("waitTimeSeconds"),
            "statsCsv": artifacts.get("statsCsv") or measurement.get("statsCsv"),
            "validTargetRequestsPresent": measurement.get("validTargetRequestsPresent"),
            "targetRequestCount": measurement.get("targetRequestCount"),
            "failureCount": measurement.get("failureCount"),
            "averageResponseTimeMs": measurement.get("averageResponseTimeMs"),
            "medianResponseTimeMs": measurement.get("medianResponseTimeMs"),
            "p95ResponseTimeMs": measurement.get("p95ResponseTimeMs"),
            "p99ResponseTimeMs": measurement.get("p99ResponseTimeMs"),
            "requestsPerSecond": measurement.get("requestsPerSecond"),
            "classification": measurement.get("classification"),
        })
    return measurements


def samples_from_tenant_measurements(measurements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for item in measurements:
        if not isinstance(item, dict) or not item.get("validTargetRequestsPresent"):
            continue
        replica = item.get("replica") or item.get("replicaId") or item.get("tenantId") or f"sample-{len(samples) + 1}"
        samples.append({
            "replica": str(replica),
            "tenantId": item.get("tenantId"),
            "namespace": item.get("namespace"),
            "statsCsvPath": item.get("statsCsv"),
            "rowSource": "multi_tenant_summary",
            "request_count": item.get("targetRequestCount"),
            "failure_count": item.get("failureCount"),
            "mean_response_time_ms": item.get("averageResponseTimeMs"),
            "p50_response_time_ms": item.get("medianResponseTimeMs"),
            "p95_response_time_ms": item.get("p95ResponseTimeMs"),
            "p99_response_time_ms": item.get("p99ResponseTimeMs"),
            "throughput_rps": item.get("requestsPerSecond"),
        })
    return samples


def placement_categories_from_evidence(evidence_payload: dict[str, Any] | None) -> list[str]:
    placement = (evidence_payload or {}).get("placementClassification") or {}
    return list(placement.get("scenarioCategories") or [])


def placement_negative_evidence_from_evidence(evidence_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    placement = (evidence_payload or {}).get("placementClassification") or {}
    return list(placement.get("negativeEvidence") or [])


def placement_risk_level(evidence_payload: dict[str, Any] | None) -> str | None:
    placement = (evidence_payload or {}).get("placementClassification") or {}
    return placement.get("scenarioRiskLevel")


def is_runtime_scheduler_decision_evidence(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("captureMode") == "dry_run":
        return False
    if payload.get("status") in {"planned", "dry_run"}:
        return False
    return True


def is_runtime_multi_tenant_summary(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("dryRun") is True:
        return False
    if payload.get("status") in {"planned", "dry_run"}:
        return False
    return True


def _replica_from_run_dir(path: Path) -> str:
    match = re.fullmatch(r"run([A-Za-z0-9_-]+)", path.name)
    if match:
        return match.group(1)
    return path.name


def _artifact_file_record(path: Path, repo_root: Path) -> dict[str, Any]:
    try:
        relative_path = path.relative_to(repo_root)
        stored_path = str(relative_path)
    except Exception:
        stored_path = str(path)
    return {
        "path": stored_path,
        "exists": path.exists(),
        "sizeBytes": path.stat().st_size if path.exists() and path.is_file() else None,
    }


def _first_existing_file(directory: Path, names: list[str]) -> Path | None:
    for name in names:
        candidate = directory / name
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def discover_cluster_side_artifacts(repo_root: Path, search_roots: list[Path]) -> dict[str, Any]:
    run_dirs: list[Path] = []
    for root in search_roots:
        if not root.exists() or not root.is_dir():
            continue
        if _first_existing_file(root, ["cluster_post_top-nodes.txt", "cluster_pre_top-nodes.txt"]):
            run_dirs.append(root)
        for candidate in sorted(root.glob("run*")):
            if candidate.is_dir() and _first_existing_file(candidate, ["cluster_post_top-nodes.txt", "cluster_pre_top-nodes.txt"]):
                run_dirs.append(candidate)

    unique_run_dirs = unique_paths(run_dirs)
    run_records: list[dict[str, Any]] = []
    cpu_values: list[float] = []
    memory_values: list[float] = []
    artifact_count = 0

    artifact_names_by_stage = {
        "pre": [
            "cluster_pre_manifest.json",
            "cluster_pre_snapshot.json",
            "cluster_pre_nodes.json",
            "cluster_pre_pods.json",
            "cluster_pre_events.json",
            "cluster_pre_top-nodes.txt",
            "cluster_pre_top-pods.txt",
            "cluster_pre_top-pods-containers.txt",
            "cluster_pre_pods-wide.txt",
            "cluster_pre_nodes-wide.txt",
            "cluster_pre_services.txt",
        ],
        "post": [
            "cluster_post_manifest.json",
            "cluster_post_snapshot.json",
            "cluster_post_nodes.json",
            "cluster_post_pods.json",
            "cluster_post_events.json",
            "cluster_post_top-nodes.txt",
            "cluster_post_top-pods.txt",
            "cluster_post_top-pods-containers.txt",
            "cluster_post_pods-wide.txt",
            "cluster_post_nodes-wide.txt",
            "cluster_post_services.txt",
        ],
    }

    for run_dir in unique_run_dirs:
        replica = _replica_from_run_dir(run_dir)
        stages: dict[str, Any] = {}
        run_pressure_values: list[dict[str, Any]] = []
        for stage, names in artifact_names_by_stage.items():
            files = []
            for name in names:
                candidate = run_dir / name
                if candidate.exists() and candidate.is_file():
                    files.append(_artifact_file_record(candidate, repo_root))
            artifact_count += len(files)
            top_nodes_file = run_dir / f"cluster_{stage}_top-nodes.txt"
            pressure = parse_top_nodes(top_nodes_file) if top_nodes_file.exists() else None
            if pressure:
                cpu = pressure.get("maxNodeCpuPercent")
                mem = pressure.get("maxNodeMemoryPercent")
                if cpu is not None:
                    cpu_values.append(cpu)
                if mem is not None:
                    memory_values.append(mem)
                run_pressure_values.append({"stage": stage, **pressure})
            stages[stage] = {
                "artifactCount": len(files),
                "topNodesPath": str(top_nodes_file.relative_to(repo_root)) if top_nodes_file.exists() else None,
                "pressure": pressure,
                "files": files,
            }
        max_cpu = max((item.get("maxNodeCpuPercent") for item in run_pressure_values if item.get("maxNodeCpuPercent") is not None), default=None)
        max_memory = max((item.get("maxNodeMemoryPercent") for item in run_pressure_values if item.get("maxNodeMemoryPercent") is not None), default=None)
        run_records.append({
            "replica": replica,
            "runDirectory": str(run_dir.relative_to(repo_root)) if run_dir.exists() else str(run_dir),
            "artifactCount": sum(stage_data.get("artifactCount", 0) for stage_data in stages.values()),
            "maxNodeCpuPercent": max_cpu,
            "maxNodeMemoryPercent": max_memory,
            "stages": stages,
        })

    return {
        "available": bool(run_records),
        "runCount": len(run_records),
        "artifactCount": artifact_count,
        "maxNodeCpuPercentObserved": round(max(cpu_values), 2) if cpu_values else None,
        "maxNodeMemoryPercentObserved": round(max(memory_values), 2) if memory_values else None,
        "runs": run_records,
    }


def cluster_side_metrics_by_replica(cluster_side_artifacts: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    if not isinstance(cluster_side_artifacts, dict):
        return metrics
    for run in cluster_side_artifacts.get("runs") or []:
        replica = run.get("replica")
        if not replica:
            continue
        metrics[str(replica)] = {
            "maxNodeCpuPercent": run.get("maxNodeCpuPercent"),
            "maxNodeMemoryPercent": run.get("maxNodeMemoryPercent"),
        }
    return metrics


def enrich_samples_with_cluster_side_metrics(samples: list[dict[str, Any]], cluster_side_artifacts: dict[str, Any] | None) -> None:
    metrics_by_replica = cluster_side_metrics_by_replica(cluster_side_artifacts)
    for sample in samples:
        replica = sample.get("replica")
        if replica is None:
            continue
        replica_key = str(replica)
        metrics = metrics_by_replica.get(replica_key)
        if metrics is None and replica_key.startswith("run"):
            metrics = metrics_by_replica.get(replica_key[3:])
        if metrics is None:
            metrics = metrics_by_replica.get(f"run{replica_key}")
        if not metrics:
            continue
        for key, value in metrics.items():
            if value is not None and sample.get(key) is None:
                sample[key] = value


def attach_cluster_side_summary_to_entry(entry: dict[str, Any], cluster_side_artifacts: dict[str, Any] | None) -> None:
    if not isinstance(cluster_side_artifacts, dict) or not cluster_side_artifacts.get("available"):
        return
    summary = entry.get("summary")
    if not isinstance(summary, dict):
        summary = summarize_samples(entry.get("samples") or []) or {"sampleCount": 0, "replicas": [], "metrics": {}}
        entry["summary"] = summary
    if summary.get("maxNodeCpuPercentObserved") is None and cluster_side_artifacts.get("maxNodeCpuPercentObserved") is not None:
        summary["maxNodeCpuPercentObserved"] = cluster_side_artifacts.get("maxNodeCpuPercentObserved")
    if summary.get("maxNodeMemoryPercentObserved") is None and cluster_side_artifacts.get("maxNodeMemoryPercentObserved") is not None:
        summary["maxNodeMemoryPercentObserved"] = cluster_side_artifacts.get("maxNodeMemoryPercentObserved")


def attach_default_scheduler_artifacts(repo_root: Path, profile: dict[str, Any], scenario_id: str, scenario_payload: dict[str, Any], search_roots: list[Path], entry: dict[str, Any]) -> None:
    summary_path, summary_payload = discover_named_json(search_roots, [
        str(profile.get("multiTenantSummaryArtifactName") or "multi-tenant-summary.json"),
        "latest-multi-tenant-summary.json",
    ])
    scheduler_path, scheduler_payload = discover_scheduler_decision_evidence(repo_root, profile, scenario_id, scenario_payload)
    cluster_side_artifacts = discover_cluster_side_artifacts(repo_root, search_roots)
    entry["multiTenantSummaryPath"] = str(summary_path) if summary_path else None
    entry["multiTenantSummary"] = summary_payload
    entry["multiTenantSummaryRuntime"] = is_runtime_multi_tenant_summary(summary_payload)
    entry["tenantMeasurements"] = tenant_measurements_from_multi_tenant_summary(summary_payload)
    entry["schedulerDecisionEvidencePath"] = str(scheduler_path) if scheduler_path else None
    if scenario_payload.get("scenarioFamily") == "network-aware-scheduler" or scenario_id.startswith("NA_"):
        network_telemetry = collect_network_aware_telemetry_for_scenario(repo_root, profile, scenario_id, scenario_payload)
        if isinstance(scheduler_payload, dict):
            scheduler_payload = dict(scheduler_payload)
            scheduler_payload["networkAwareTelemetryEvidence"] = network_telemetry
        else:
            scheduler_payload = {"networkAwareTelemetryEvidence": network_telemetry}
        entry["networkAwareTelemetryEvidence"] = network_telemetry
    entry["schedulerDecisionEvidence"] = scheduler_payload
    entry["schedulerDecisionEvidenceRuntime"] = is_runtime_scheduler_decision_evidence(scheduler_payload)
    entry["placementClassification"] = (scheduler_payload or {}).get("placementClassification") if isinstance(scheduler_payload, dict) else None
    entry["schedulerNegativeEvidence"] = placement_negative_evidence_from_evidence(scheduler_payload)
    entry["schedulerScenarioCategories"] = placement_categories_from_evidence(scheduler_payload)
    entry["schedulerScenarioRiskLevel"] = placement_risk_level(scheduler_payload)
    entry["clusterSideArtifacts"] = cluster_side_artifacts
    entry["clusterSideArtifactsAvailable"] = bool(cluster_side_artifacts.get("available"))
    attach_cluster_side_summary_to_entry(entry, cluster_side_artifacts)


def discover_family_samples(repo_root: Path, profile, family_name: str):
    scenario_root = repo_root / profile["scenarioConfigRoots"][family_name]
    results_root = campaign_results_root(repo_root, profile, family_name)
    scenario_files = configured_scenario_files(repo_root, profile, family_name, scenario_root)
    if not scenario_files:
        return {}, {"resultsRoot": str(results_root), "scenarioRoot": str(scenario_root), "available": False}

    scenario_configs = {}
    for path in sorted(scenario_files):
        if not path.exists():
            continue
        data = load_json(path)
        scenario_id = scenario_identifier(data, path.stem)
        scenario_configs[scenario_id] = {"configPath": str(path), "data": data}

    family_samples = {}
    for scenario_id, scenario_info in scenario_configs.items():
        scenario_search_roots = scenario_result_roots(results_root, scenario_id, scenario_info["data"])
        stats_files = unique_paths([path for root in scenario_search_roots for path in discover_measurement_stats(root)])
        unsupported_files = unique_paths([path for root in scenario_search_roots for path in discover_unsupported_reports(root)])
        scenario_search_root = scenario_search_roots[0] if scenario_search_roots else results_root

        samples = []
        invalid_measurement_reports = []
        for stats_file in stats_files:
            row, source = find_target_row(
                stats_file,
                profile["requestTargetType"],
                profile["requestTargetName"],
                profile.get("fallbackToAggregated", False),
            )
            if not valid_measurement_row(row, source):
                if family_name == "latency-injection":
                    invalid_measurement_reports.append(invalid_measurement_unsupported_report(repo_root, stats_file, scenario_id, scenario_info["data"], row, source, profile["requestTargetType"], profile["requestTargetName"]))
                continue
            prefix = str(stats_file)[:-len("_stats.csv")]
            cluster_post = parse_top_nodes(Path(prefix + "_cluster_post_top-nodes.txt")) or {}
            replica = parse_replica(stats_file.stem)
            sample = {
                "replica": replica,
                "statsCsvPath": str(stats_file),
                "rowSource": source,
            }
            for metric_key, csv_field in CSV_FIELD_MAP.items():
                value = to_number(row.get(csv_field))
                if value is None:
                    sample[metric_key] = None
                elif metric_key in ("request_count", "failure_count"):
                    sample[metric_key] = int(round(value))
                else:
                    sample[metric_key] = round(value, 4)
            sample.update(cluster_post)
            samples.append(sample)

        unsupported_reports = []
        for unsupported_file in unsupported_files:
            report_scenario_id, replica = parse_scenario_and_replica_from_unsupported(unsupported_file)
            if report_scenario_id != scenario_id:
                continue
            unsupported_payload = load_json(unsupported_file)
            unsupported_reports.append({
                "replica": replica,
                "unsupportedJsonPath": str(unsupported_file),
                "status": unsupported_payload.get("status"),
                "reason": unsupported_payload.get("reason"),
                "evidence": unsupported_payload.get("evidence"),
                "evidenceKinds": derive_unsupported_evidence_kinds(unsupported_payload, repo_root),
                "timeoutSeconds": unsupported_payload.get("timeoutSeconds"),
                "model": unsupported_payload.get("model"),
            })
        unsupported_reports.extend(invalid_measurement_reports)
        if not unsupported_reports and not samples:
            unsupported_reports.extend(synthetic_unsupported_reports_from_campaign(repo_root, profile, family_name, scenario_id, scenario_info["data"], scenario_search_roots))

        entry = {
            "scenario": scenario_info["data"],
            "searchRoot": str(scenario_search_root),
            "searchRoots": [str(root) for root in scenario_search_roots],
            "samples": samples,
            "unsupportedReports": unsupported_reports,
            "summary": summarize_samples(samples),
            "unsupportedSummary": {
                "unsupportedReplicaCount": len(unsupported_reports),
                "replicas": [item["replica"] for item in unsupported_reports],
                "acceptedStatusValues": sorted({item["status"] for item in unsupported_reports if item.get("status")}),
                "evidenceKinds": sorted({kind for item in unsupported_reports for kind in (item.get("evidenceKinds") or [])}),
                "reasons": [item["reason"] for item in unsupported_reports if item.get("reason")],
            } if unsupported_reports else None,
        }
        if family_name in {"default-scheduler", "resource-aware-scheduler", "network-aware-scheduler"}:
            attach_default_scheduler_artifacts(repo_root, profile, scenario_id, scenario_info["data"], scenario_search_roots, entry)
            tenant_samples = samples_from_tenant_measurements(entry.get("tenantMeasurements") or [])
            if tenant_samples:
                enrich_samples_with_cluster_side_metrics(tenant_samples, entry.get("clusterSideArtifacts"))
                entry["samples"] = tenant_samples
                entry["summary"] = summarize_samples(tenant_samples)
            attach_cluster_side_summary_to_entry(entry, entry.get("clusterSideArtifacts"))
        family_samples[scenario_id] = entry

    coverage = {
        "resultsRoot": str(results_root),
        "scenarioRoot": str(scenario_root),
        "available": True,
        "scenarioCount": len(scenario_configs),
        "scenariosWithSamples": sum(1 for item in family_samples.values() if item["samples"]),
        "scenariosWithUnsupportedEvidence": sum(1 for item in family_samples.values() if item.get("unsupportedReports")),
        "scenariosObserved": sum(1 for item in family_samples.values() if item["samples"] or item.get("unsupportedReports")),
        "sampleCount": sum(len(item["samples"]) for item in family_samples.values()),
        "unsupportedReplicaCount": sum(len(item.get("unsupportedReports") or []) for item in family_samples.values()),
        "unsupportedScenarioIds": [scenario_id for scenario_id, item in family_samples.items() if item.get("unsupportedReports")],
    }
    if family_name == "default-scheduler":
        scheduler_evidence_count = sum(1 for item in family_samples.values() if item.get("schedulerDecisionEvidenceRuntime"))
        placement_classification_count = sum(1 for item in family_samples.values() if item.get("placementClassification"))
        scheduler_negative_evidence_count = sum(1 for item in family_samples.values() if item.get("schedulerNegativeEvidence"))
        multi_tenant_summary_count = sum(1 for item in family_samples.values() if item.get("multiTenantSummaryRuntime"))
        tenant_measurement_count = sum(1 for item in family_samples.values() if item.get("tenantMeasurements"))
        default_scheduler_observed = sum(
            1
            for item in family_samples.values()
            if item.get("samples") or item.get("unsupportedReports") or item.get("schedulerDecisionEvidenceRuntime") or item.get("multiTenantSummaryRuntime")
        )
        cluster_side_artifacts_count = sum(1 for item in family_samples.values() if item.get("clusterSideArtifactsAvailable"))
        coverage.update({
            "scenariosWithSchedulerDecisionEvidence": scheduler_evidence_count,
            "scenariosWithPlacementClassification": placement_classification_count,
            "scenariosWithSchedulerNegativeEvidence": scheduler_negative_evidence_count,
            "scenariosWithMultiTenantSummary": multi_tenant_summary_count,
            "scenariosWithTenantMeasurements": tenant_measurement_count,
            "scenariosWithClusterSideArtifacts": cluster_side_artifacts_count,
            "scenariosObserved": max(coverage.get("scenariosObserved", 0), default_scheduler_observed),
        })
    return family_samples, coverage


def percent_change(reference, candidate):
    if reference in (None, 0) or candidate is None:
        return None
    return ((candidate - reference) / reference) * 100.0


def add_finding(findings, finding_id, title, confidence, evidence, implication, family=None):
    findings.append({
        "id": finding_id,
        "family": family or infer_finding_family(finding_id),
        "title": title,
        "confidence": confidence,
        "evidence": evidence,
        "implication": implication,
    })


def build_family_judgment(family_name, status, confidence, title, implication, evidence):
    return {
        "family": family_name,
        "status": status,
        "confidence": confidence,
        "title": title,
        "implication": implication,
        "evidence": evidence,
    }


def resource_aware_scheduler_role(entry, scenario_id):
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
    if variant_id.startswith("NA_NETAWARE_") or str(scenario_id).startswith("NA_NETAWARE_"):
        return "netaware"
    if variant_id.startswith("NA_LOADAWARE_") or str(scenario_id).startswith("NA_LOADAWARE_") or variant_id.startswith("RA_LOADAWARE_") or str(scenario_id).startswith("RA_LOADAWARE_"):
        return "loadaware"
    if variant_id.startswith("NA_DEFAULT_") or str(scenario_id).startswith("NA_DEFAULT_") or variant_id.startswith("RA_DEFAULT_") or str(scenario_id).startswith("RA_DEFAULT_"):
        return "default"
    return "unknown"


def resource_aware_scheduler_logical_id(entry, scenario_id):
    scenario = entry.get("scenario") if isinstance(entry.get("scenario"), dict) else {}
    policy = scenario.get("networkAwareSchedulerPolicy") if isinstance(scenario.get("networkAwareSchedulerPolicy"), dict) else {}
    if not policy:
        policy = scenario.get("schedulerModePolicy") if isinstance(scenario.get("schedulerModePolicy"), dict) else {}
    logical_id = scenario.get("logicalScenarioId") or policy.get("logicalScenarioId")
    if logical_id:
        return str(logical_id)
    for prefix in ["NA_DEFAULT_", "NA_LOADAWARE_", "NA_NETAWARE_", "RA_DEFAULT_", "RA_LOADAWARE_"]:
        if str(scenario_id).startswith(prefix):
            return str(scenario_id)[len(prefix):]
    return str(scenario_id)


def scheduler_metric(entry, metric):
    summary = entry.get("summary") if isinstance(entry.get("summary"), dict) else None
    if not summary:
        return None
    if metric == "max_node_cpu_percent":
        return summary.get("maxNodeCpuPercentObserved")
    if metric == "max_node_memory_percent":
        return summary.get("maxNodeMemoryPercentObserved")
    return metric_mean(summary, metric)


def resource_aware_scheduler_pairwise_rows(family_data):
    grouped = {}
    for scenario_id, entry in sorted((family_data or {}).items()):
        logical_id = resource_aware_scheduler_logical_id(entry, scenario_id)
        role = resource_aware_scheduler_role(entry, scenario_id)
        grouped.setdefault(logical_id, {})[role] = {"scenarioId": scenario_id, "entry": entry}
    rows = []
    for logical_id, roles in sorted(grouped.items()):
        default_item = roles.get("default")
        custom_item = roles.get("loadaware")
        default_entry = default_item.get("entry") if default_item else {}
        custom_entry = custom_item.get("entry") if custom_item else {}
        default_mean = scheduler_metric(default_entry, "mean_response_time_ms") if default_item else None
        custom_mean = scheduler_metric(custom_entry, "mean_response_time_ms") if custom_item else None
        default_p95 = scheduler_metric(default_entry, "p95_response_time_ms") if default_item else None
        custom_p95 = scheduler_metric(custom_entry, "p95_response_time_ms") if custom_item else None
        default_rps = scheduler_metric(default_entry, "throughput_rps") if default_item else None
        custom_rps = scheduler_metric(custom_entry, "throughput_rps") if custom_item else None
        default_cpu = scheduler_metric(default_entry, "max_node_cpu_percent") if default_item else None
        custom_cpu = scheduler_metric(custom_entry, "max_node_cpu_percent") if custom_item else None
        default_mem = scheduler_metric(default_entry, "max_node_memory_percent") if default_item else None
        custom_mem = scheduler_metric(custom_entry, "max_node_memory_percent") if custom_item else None
        latency_delta = percent_change(default_mean, custom_mean)
        p95_delta = percent_change(default_p95, custom_p95)
        throughput_delta = percent_change(default_rps, custom_rps)
        if not default_item or not custom_item:
            classification = "incomplete_pair"
        elif not default_entry.get("summary") or not custom_entry.get("summary"):
            classification = "insufficient_evidence"
        elif latency_delta is None:
            classification = "measured_without_latency_delta"
        elif latency_delta <= -5.0:
            classification = "custom_improved_latency"
        elif latency_delta >= 5.0:
            classification = "custom_regressed_latency"
        else:
            classification = "custom_latency_neutral"
        rows.append({
            "logicalScenarioId": logical_id,
            "defaultScenarioId": default_item.get("scenarioId") if default_item else None,
            "loadAwareScenarioId": custom_item.get("scenarioId") if custom_item else None,
            "defaultVariantId": (default_entry.get("scenario") or {}).get("variantId") if default_item else None,
            "loadAwareVariantId": (custom_entry.get("scenario") or {}).get("variantId") if custom_item else None,
            "defaultStatus": default_entry.get("status") if default_item else "missing",
            "loadAwareStatus": custom_entry.get("status") if custom_item else "missing",
            "defaultMeanLatencyMs": default_mean,
            "loadAwareMeanLatencyMs": custom_mean,
            "meanLatencyDeltaPercent": latency_delta,
            "defaultP95LatencyMs": default_p95,
            "loadAwareP95LatencyMs": custom_p95,
            "p95LatencyDeltaPercent": p95_delta,
            "defaultThroughputRps": default_rps,
            "loadAwareThroughputRps": custom_rps,
            "throughputDeltaPercent": throughput_delta,
            "defaultMaxNodeCpuPercent": default_cpu,
            "loadAwareMaxNodeCpuPercent": custom_cpu,
            "defaultMaxNodeMemoryPercent": default_mem,
            "loadAwareMaxNodeMemoryPercent": custom_mem,
            "classification": classification,
        })
    return rows


def scheduler_network_aware_triplet_rows(family_data):
    grouped = {}
    for scenario_id, entry in sorted((family_data or {}).items()):
        logical_id = resource_aware_scheduler_logical_id(entry, scenario_id)
        role = resource_aware_scheduler_role(entry, scenario_id)
        grouped.setdefault(logical_id, {})[role] = {"scenarioId": scenario_id, "entry": entry}
    rows = []
    for logical_id, roles in sorted(grouped.items()):
        default_item = roles.get("default")
        loadaware_item = roles.get("loadaware")
        netaware_item = roles.get("netaware")
        default_entry = default_item.get("entry") if default_item else {}
        loadaware_entry = loadaware_item.get("entry") if loadaware_item else {}
        netaware_entry = netaware_item.get("entry") if netaware_item else {}
        default_mean = scheduler_metric(default_entry, "mean_response_time_ms") if default_item else None
        loadaware_mean = scheduler_metric(loadaware_entry, "mean_response_time_ms") if loadaware_item else None
        netaware_mean = scheduler_metric(netaware_entry, "mean_response_time_ms") if netaware_item else None
        default_p95 = scheduler_metric(default_entry, "p95_response_time_ms") if default_item else None
        loadaware_p95 = scheduler_metric(loadaware_entry, "p95_response_time_ms") if loadaware_item else None
        netaware_p95 = scheduler_metric(netaware_entry, "p95_response_time_ms") if netaware_item else None
        net_vs_default = percent_change(default_mean, netaware_mean)
        net_vs_load = percent_change(loadaware_mean, netaware_mean)
        if not default_item or not loadaware_item or not netaware_item:
            classification = "incomplete_triplet"
        elif not default_entry.get("summary") or not loadaware_entry.get("summary") or not netaware_entry.get("summary"):
            classification = "insufficient_measured_evidence"
        elif net_vs_load is not None and net_vs_load <= -5.0:
            classification = "netaware_lower_latency_than_loadaware"
        elif net_vs_default is not None and net_vs_default <= -5.0:
            classification = "netaware_lower_latency_than_default"
        elif (net_vs_load is not None and net_vs_load >= 5.0) or (net_vs_default is not None and net_vs_default >= 5.0):
            classification = "netaware_higher_latency"
        else:
            classification = "netaware_latency_neutral_or_mixed"
        telemetry = (netaware_entry.get("schedulerDecisionEvidence") or {}).get("networkAwareTelemetryEvidence") if isinstance(netaware_entry.get("schedulerDecisionEvidence"), dict) else None
        cluster_lens = telemetry.get("clusterLensPlacementEvidence") if isinstance(telemetry, dict) and isinstance(telemetry.get("clusterLensPlacementEvidence"), dict) else {}
        rows.append({
            "logicalScenarioId": logical_id,
            "defaultScenarioId": default_item.get("scenarioId") if default_item else None,
            "loadAwareScenarioId": loadaware_item.get("scenarioId") if loadaware_item else None,
            "networkAwareScenarioId": netaware_item.get("scenarioId") if netaware_item else None,
            "defaultMeanLatencyMs": default_mean,
            "loadAwareMeanLatencyMs": loadaware_mean,
            "networkAwareMeanLatencyMs": netaware_mean,
            "networkAwareVsDefaultMeanLatencyDeltaPercent": net_vs_default,
            "networkAwareVsLoadAwareMeanLatencyDeltaPercent": net_vs_load,
            "defaultP95LatencyMs": default_p95,
            "loadAwareP95LatencyMs": loadaware_p95,
            "networkAwareP95LatencyMs": netaware_p95,
            "networkAwareTelemetryStatus": telemetry.get("status") if isinstance(telemetry, dict) else None,
            "networkAwarePlacementEvidenceStatus": cluster_lens.get("status"),
            "networkAwarePlacementEvidenceComplete": cluster_lens.get("complete"),
            "networkAwarePlacementSignaturePath": cluster_lens.get("placementSignaturePath"),
            "networkAwarePlacementLocalAiPodCount": cluster_lens.get("localAiPodCount"),
            "classification": classification,
        })
    return rows


def diagnose_network_aware_scheduler(profile, family_data, findings):
    triplets = scheduler_network_aware_triplet_rows(family_data)
    if not triplets:
        return build_family_judgment(
            "network-aware-scheduler",
            "insufficient_triplet_evidence",
            "low",
            "No network-aware scheduler triplet evidence is available yet.",
            "C9 requires paired logical scenarios across DEFAULT, LOADAWARE and NETAWARE variants before the resource-aware scheduler can be interpreted.",
            {"tripletCount": 0},
        )
    counts = {}
    for row in triplets:
        counts[row.get("classification")] = counts.get(row.get("classification"), 0) + 1
    measured = sum(counts.get(key, 0) for key in ["netaware_lower_latency_than_loadaware", "netaware_lower_latency_than_default", "netaware_higher_latency", "netaware_latency_neutral_or_mixed"])
    telemetry_complete = sum(1 for row in triplets if row.get("networkAwareTelemetryStatus") == "complete")
    placement_complete = sum(1 for row in triplets if row.get("networkAwarePlacementEvidenceComplete") is True)
    if measured == 0:
        status = "configured_without_measured_triplets"
        confidence = "low"
        title = "Network-aware scheduler triplets are configured but not yet measured."
        implication = "The C9 campaign is structurally ready, but no measured triplet is available yet for a performance-level conclusion."
    elif counts.get("netaware_lower_latency_than_loadaware", 0) or counts.get("netaware_lower_latency_than_default", 0):
        status = "network_aware_improvement_observed"
        confidence = "medium"
        title = "At least one measured triplet shows lower network-aware latency."
        implication = "The network-aware signal may be useful when topology and gateway traffic make network cost observable."
    elif counts.get("netaware_higher_latency", 0):
        status = "network_aware_regression_or_overhead_observed"
        confidence = "medium"
        title = "At least one measured triplet shows higher network-aware latency."
        implication = "The network-aware strategy must be interpreted together with telemetry quality, placement evidence and scenario-level latency/traffic conditions."
    else:
        status = "network_aware_neutral_or_mixed"
        confidence = "medium"
        title = "Network-aware evidence is latency-neutral or mixed in the measured triplets."
        implication = "C9 should be interpreted per scenario rather than as an unconditional improvement claim."
    add_finding(
        findings,
        "network_aware_scheduler_triplet_evidence",
        "C9 scheduler triplet evidence is available.",
        confidence,
        {"tripletCount": len(triplets), "measuredTripletCount": measured, "telemetryCompleteTripletCount": telemetry_complete, "placementEvidenceCompleteTripletCount": placement_complete, "classificationCounts": counts, "tripletSummaries": triplets},
        implication,
        family="network-aware-scheduler",
    )
    return build_family_judgment(
        "network-aware-scheduler",
        status,
        confidence,
        title,
        implication,
        {"tripletCount": len(triplets), "measuredTripletCount": measured, "telemetryCompleteTripletCount": telemetry_complete, "placementEvidenceCompleteTripletCount": placement_complete, "classificationCounts": counts, "tripletSummaries": triplets},
    )


def diagnose_resource_aware_scheduler(profile, family_data, findings):
    pairwise_rows = resource_aware_scheduler_pairwise_rows(family_data)
    if not pairwise_rows:
        return build_family_judgment(
            "resource-aware-scheduler",
            "insufficient_pairwise_evidence",
            "low",
            "No resource-aware-scheduler pairwise evidence is available yet.",
            "The C8 resource-aware scheduler cannot be interpreted until default and load-aware variants produce measured or unsupported evidence.",
            {"pairCount": 0},
        )
    counts = {
        "custom_improved_latency": 0,
        "custom_regressed_latency": 0,
        "custom_latency_neutral": 0,
        "incomplete_pair": 0,
        "insufficient_evidence": 0,
        "measured_without_latency_delta": 0,
    }
    for row in pairwise_rows:
        counts[row.get("classification")] = counts.get(row.get("classification"), 0) + 1
    measured_pairs = counts.get("custom_improved_latency", 0) + counts.get("custom_regressed_latency", 0) + counts.get("custom_latency_neutral", 0) + counts.get("measured_without_latency_delta", 0)
    if measured_pairs == 0:
        status = "insufficient_pairwise_evidence"
        confidence = "low"
        title = "Scheduler-comparison pairs are configured but not yet measured."
        implication = "At least one measured default/load-aware pair must be available before C8 can support an evidence-based scheduler interpretation."
    elif counts.get("custom_improved_latency", 0) > counts.get("custom_regressed_latency", 0):
        status = "custom_scheduler_improved"
        confidence = "medium"
        title = "The load-aware scheduler shows lower mean latency in more measured pairs than it regresses."
        implication = "The current C8 evidence suggests that the resource-aware scheduler can improve at least part of the LocalAI worker-mode placement space."
    elif counts.get("custom_regressed_latency", 0) > counts.get("custom_improved_latency", 0):
        status = "custom_scheduler_regressed"
        confidence = "medium"
        title = "The load-aware scheduler shows higher mean latency in more measured pairs than it improves."
        implication = "The resource-aware strategy needs cautious interpretation: placement/resource balance may improve without directly improving latency, or the telemetry signal may be insufficient."
    else:
        status = "custom_scheduler_neutral_or_mixed"
        confidence = "medium"
        title = "The load-aware scheduler produces mixed or latency-neutral pairwise evidence."
        implication = "C8 should be interpreted through both performance and resource-balance evidence rather than by latency alone."
    add_finding(
        findings,
        "resource_aware_scheduler_pairwise_evidence",
        "C8 pairwise resource-aware-scheduler evidence is available.",
        confidence,
        {
            "pairCount": len(pairwise_rows),
            "measuredPairCount": measured_pairs,
            "classificationCounts": counts,
            "pairwiseSummaries": pairwise_rows,
        },
        implication,
        family="resource-aware-scheduler",
    )
    return build_family_judgment(
        "resource-aware-scheduler",
        status,
        confidence,
        title,
        implication,
        {
            "pairCount": len(pairwise_rows),
            "measuredPairCount": measured_pairs,
            "classificationCounts": counts,
            "pairwiseSummaries": pairwise_rows,
        },
    )


def normalize_family_judgment(judgment):
    if not isinstance(judgment, dict):
        return build_family_judgment(
            "unknown",
            "invalid_judgment",
            "low",
            "A malformed family-level judgment was produced.",
            "The diagnosis generator preserved the malformed value as diagnostic evidence instead of failing the whole run.",
            {"rawJudgment": str(judgment)},
        )

    if all(key in judgment for key in ("family", "status", "confidence", "title", "implication", "evidence")):
        return judgment

    family = judgment.get("family") or "unknown"
    status = judgment.get("status") or judgment.get("judgment") or "informational"
    confidence = judgment.get("confidence") or "medium"
    title = judgment.get("title") or judgment.get("judgment") or "Family-level diagnostic evidence is available."
    implication = judgment.get("implication") or judgment.get("interpretation") or "No explicit implication was provided by the diagnostic routine."

    evidence = judgment.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    if judgment.get("scenarioId") is not None:
        evidence.setdefault("scenarioId", judgment.get("scenarioId"))
    if judgment.get("metrics") is not None:
        evidence.setdefault("metrics", judgment.get("metrics"))
    evidence.setdefault("normalizedFromLegacyShape", True)

    return build_family_judgment(family, status, confidence, title, implication, evidence)


def diagnose_worker_count(profile, family_data, findings):
    scenario_means = []
    unsupported_scenarios = []
    for scenario_id, entry in sorted(family_data.items(), key=lambda item: item[1]["scenario"].get("workerCount", 0)):
        summary = entry.get("summary")
        if summary and "mean_response_time_ms" in summary["metrics"]:
            scenario_means.append((
                scenario_id,
                entry["scenario"].get("workerCount"),
                summary["metrics"]["mean_response_time_ms"]["mean"],
                metric_mean(summary, "throughput_rps"),
            ))
        elif entry.get("unsupportedSummary"):
            unsupported_scenarios.append(scenario_id)
    throughput_by_scenario = {item[0]: item[3] for item in scenario_means if item[3] is not None}
    if len(scenario_means) < 2:
        return build_family_judgment(
            "worker-count",
            "insufficient_evidence",
            "low",
            "The worker-count family does not yet provide enough measured evidence for a robust comparative assessment.",
            "Without at least two comparable measured configurations, the worker-count signal cannot yet be considered reliable; unsupported scenarios remain tracked as evidence observed under the current constraints.",
            {
                "measuredScenarios": [item[0] for item in scenario_means],
                "throughputRpsByScenario": throughput_by_scenario,
                "unsupportedScenarios": unsupported_scenarios,
            },
        )

    judgment = build_family_judgment(
        "worker-count",
        "weak_signal",
        "low",
        "Within the observed scope, worker count does not yet show a dominant effect on mean latency.",
        "Worker count has been analyzed, but the measured signal in the current cluster is not strong enough yet to be considered the primary performance driver.",
        {
            "measuredScenarios": [item[0] for item in scenario_means],
            "throughputRpsByScenario": throughput_by_scenario,
            "unsupportedScenarios": unsupported_scenarios,
        },
    )

    w1 = next((item for item in scenario_means if item[0] == "W1"), None)
    w2 = next((item for item in scenario_means if item[0] == "W2"), None)
    if w1 and w2:
        improvement = -percent_change(w1[2], w2[2])
        if improvement is not None and improvement >= profile["workerImprovementThresholdPercent"]:
            add_finding(
                findings,
                "worker_count_initial_gain",
                "The initial worker increase produces a measurable improvement in mean latency.",
                "medium",
                {
                    "W1_mean_response_time_ms": w1[2],
                    "W2_mean_response_time_ms": w2[2],
                    "W1_throughput_rps": w1[3],
                    "W2_throughput_rps": w2[3],
                    "throughputChangePercent": round(percent_change(w1[3], w2[3]), 2) if w1[3] is not None and w2[3] is not None else None,
                    "improvementPercent": round(improvement, 2),
                },
                "Moving from one to two workers appears beneficial in the current cluster and suggests that part of the initial bottleneck can be mitigated through additional parallelism.",
            )
            judgment = build_family_judgment(
                "worker-count",
                "strong_signal",
                "medium",
                "Worker count already shows a measurable performance signal in the initial comparison between measured configurations.",
                "In the current cluster, additional parallelism across the first observed configurations produces a sufficiently clear benefit to support a positive diagnostic interpretation.",
                {
                    "W1_mean_response_time_ms": w1[2],
                    "W2_mean_response_time_ms": w2[2],
                    "W1_throughput_rps": w1[3],
                    "W2_throughput_rps": w2[3],
                    "throughputChangePercent": round(percent_change(w1[3], w2[3]), 2) if w1[3] is not None and w2[3] is not None else None,
                    "improvementPercent": round(improvement, 2),
                    "unsupportedScenarios": unsupported_scenarios,
                },
            )
        elif improvement is not None:
            judgment = build_family_judgment(
                "worker-count",
                "weak_signal",
                "low",
                "In the initial comparison between measured configurations, worker count does not produce a strong enough improvement.",
                "The transition from W1 to W2 was observed, but the mean-latency benefit remains below the configured diagnostic threshold; additional unsupported scenarios also limit assessment beyond the measured scope.",
                {
                    "W1_mean_response_time_ms": w1[2],
                    "W2_mean_response_time_ms": w2[2],
                    "W1_throughput_rps": w1[3],
                    "W2_throughput_rps": w2[3],
                    "throughputChangePercent": round(percent_change(w1[3], w2[3]), 2) if w1[3] is not None and w2[3] is not None else None,
                    "improvementPercent": round(improvement, 2),
                    "workerImprovementThresholdPercent": profile["workerImprovementThresholdPercent"],
                    "unsupportedScenarios": unsupported_scenarios,
                },
            )

    best = min(scenario_means, key=lambda item: item[2])
    larger = [item for item in scenario_means if item[1] > best[1]]
    if larger:
        deltas = [percent_change(best[2], item[2]) for item in larger if percent_change(best[2], item[2]) is not None]
        if deltas and all(delta >= -profile["diminishingReturnThresholdPercent"] for delta in deltas):
            add_finding(
                findings,
                "worker_count_diminishing_returns",
                "Beyond the best observed configuration, diminishing returns or no clear additional benefits emerge.",
                "medium",
                {
                    "bestScenario": best[0],
                    "bestWorkerCount": best[1],
                    "bestMeanResponseTimeMs": best[2],
                    "throughputRpsByScenario": throughput_by_scenario,
                    "largerScenarioDeltasPercent": {item[0]: round(percent_change(best[2], item[2]), 2) for item in larger if percent_change(best[2], item[2]) is not None},
                },
                "Further increasing the number of workers in the current cluster could introduce overhead or fail to pay off in terms of mean latency.",
            )
            if judgment.get("status") != "strong_signal":
                judgment = build_family_judgment(
                    "worker-count",
                    "strong_signal",
                    "medium",
                    "The worker-count family shows an interpretable diminishing-returns signal beyond the best observed configuration.",
                    "Worker count affects system behavior, but beyond the best measured configuration the additional benefits are no longer clear in the current cluster.",
                    {
                        "bestScenario": best[0],
                        "bestWorkerCount": best[1],
                        "bestMeanResponseTimeMs": best[2],
                        "throughputRpsByScenario": throughput_by_scenario,
                        "largerScenarioDeltasPercent": {item[0]: round(percent_change(best[2], item[2]), 2) for item in larger if percent_change(best[2], item[2]) is not None},
                        "unsupportedScenarios": unsupported_scenarios,
                    },
                )
    return judgment


def diagnose_workload(profile, family_data, findings):
    wl1 = family_data.get("WL1", {}).get("summary")
    wl3 = family_data.get("WL3", {}).get("summary")
    if not wl1 or not wl3:
        return build_family_judgment(
            "workload",
            "insufficient_evidence",
            "low",
            "The workload family does not yet provide enough comparable extremes for a complete assessment.",
            "Without a comparable pair of workload scenarios between baseline and higher load, the saturation signal remains incomplete.",
            {"availableScenarios": sorted([scenario_id for scenario_id, entry in family_data.items() if entry.get("summary")])},
        )
    if "mean_response_time_ms" not in wl1["metrics"] or "mean_response_time_ms" not in wl3["metrics"]:
        return build_family_judgment(
            "workload",
            "insufficient_evidence",
            "low",
            "The workload family does not yet contain enough latency metrics for a robust comparative interpretation.",
            "The runs exist, but the absence of key metrics prevents a reliable assessment of the saturation signal.",
            {"availableScenarios": sorted([scenario_id for scenario_id, entry in family_data.items() if entry.get("summary")])},
        )
    wl1_mean = wl1["metrics"]["mean_response_time_ms"]["mean"]
    wl3_mean = wl3["metrics"]["mean_response_time_ms"]["mean"]
    stress = percent_change(wl1_mean, wl3_mean)
    wl1_thr = wl1["metrics"].get("throughput_rps", {}).get("mean")
    wl3_thr = wl3["metrics"].get("throughput_rps", {}).get("mean")
    throughput_gain = percent_change(wl1_thr, wl3_thr) if wl1_thr is not None and wl3_thr is not None else None
    if stress is not None and stress >= profile["workloadStressThresholdPercent"]:
        add_finding(
            findings,
            "workload_saturation_signal",
            "The heavier workload substantially increases latency, suggesting possible system saturation.",
            "medium",
            {
                "WL1_mean_response_time_ms": wl1_mean,
                "WL3_mean_response_time_ms": wl3_mean,
                "latencyIncreasePercent": round(stress, 2),
                "WL1_throughput_rps": wl1_thr,
                "WL3_throughput_rps": wl3_thr,
                "throughputIncreasePercent": round(throughput_gain, 2) if throughput_gain is not None else None,
            },
            "The cluster appears more fragile as concurrency increases; higher load alone does not necessarily translate into a proportional increase in useful throughput.",
        )
        return build_family_judgment(
            "workload",
            "strong_signal",
            "medium",
            "The workload family shows a clear performance degradation signal as load increases.",
            "In the current cluster, workload is a relevant latency driver and suggests a clearer fragility threshold in the more demanding configurations.",
            {
                "WL1_mean_response_time_ms": wl1_mean,
                "WL3_mean_response_time_ms": wl3_mean,
                "latencyIncreasePercent": round(stress, 2),
                "WL1_throughput_rps": wl1_thr,
                "WL3_throughput_rps": wl3_thr,
                "throughputIncreasePercent": round(throughput_gain, 2) if throughput_gain is not None else None,
            },
        )
    return build_family_judgment(
        "workload",
        "weak_signal",
        "low",
        "Within the observed scope, the workload family does not yet show a strong enough effect to be considered dominant.",
        "Load has been varied, but the latency difference between reference scenarios remains below the configured diagnostic threshold; stronger evidence or more clearly separated workloads are required for a firm conclusion.",
        {
            "WL1_mean_response_time_ms": wl1_mean,
            "WL3_mean_response_time_ms": wl3_mean,
            "latencyIncreasePercent": round(stress, 2) if stress is not None else None,
            "workloadStressThresholdPercent": profile["workloadStressThresholdPercent"],
        },
    )


def diagnose_models(profile, family_data, findings):
    small = []
    large = []
    small_throughput = []
    large_throughput = []
    observed_models = []
    for _, entry in family_data.items():
        summary = entry.get("summary")
        model_name = (entry["scenario"].get("modelName") or "").lower()
        if not summary or "mean_response_time_ms" not in summary["metrics"]:
            continue
        value = summary["metrics"]["mean_response_time_ms"]["mean"]
        throughput_value = metric_mean(summary, "throughput_rps")
        observed_models.append(entry["scenario"].get("modelName"))
        if "1b" in model_name:
            small.append(value)
            if throughput_value is not None:
                small_throughput.append(throughput_value)
        elif "3b" in model_name:
            large.append(value)
            if throughput_value is not None:
                large_throughput.append(throughput_value)
    if not small or not large:
        return build_family_judgment(
            "models",
            "insufficient_evidence",
            "low",
            "The models family does not yet provide enough comparable model groups for a robust interpretation of the size penalty.",
            "Without at least one small and one larger model group observed with comparable metrics, the impact of model size cannot yet be estimated reliably.",
            {"observedModels": observed_models},
        )
    small_mean = mean(small)
    large_mean = mean(large)
    small_throughput_mean = mean(small_throughput) if small_throughput else None
    large_throughput_mean = mean(large_throughput) if large_throughput else None
    throughput_penalty = percent_change(small_throughput_mean, large_throughput_mean) if small_throughput_mean is not None and large_throughput_mean is not None else None
    penalty = percent_change(small_mean, large_mean)
    if penalty is not None and penalty >= profile["modelPenaltyThresholdPercent"]:
        add_finding(
            findings,
            "model_size_penalty",
            "Model size emerges as a dominant driver of mean latency.",
            "high",
            {
                "smallModelMeanResponseTimeMs": round(small_mean, 4),
                "largeModelMeanResponseTimeMs": round(large_mean, 4),
                "smallModelMeanThroughputRps": round(small_throughput_mean, 4) if small_throughput_mean is not None else None,
                "largeModelMeanThroughputRps": round(large_throughput_mean, 4) if large_throughput_mean is not None else None,
                "throughputChangePercent": round(throughput_penalty, 2) if throughput_penalty is not None else None,
                "penaltyPercent": round(penalty, 2),
            },
            "In the current CPU-only cluster, moving to larger models appears to matter much more than fine-grained topology variation or light workload changes.",
        )
        return build_family_judgment(
            "models",
            "strong_signal",
            "high",
            "The models family shows a clear and dominant size penalty on mean latency.",
            "In the current cluster, model selection strongly affects service behavior and represents one of the main drivers of observed performance.",
            {
                "smallModelMeanResponseTimeMs": round(small_mean, 4),
                "largeModelMeanResponseTimeMs": round(large_mean, 4),
                "smallModelMeanThroughputRps": round(small_throughput_mean, 4) if small_throughput_mean is not None else None,
                "largeModelMeanThroughputRps": round(large_throughput_mean, 4) if large_throughput_mean is not None else None,
                "throughputChangePercent": round(throughput_penalty, 2) if throughput_penalty is not None else None,
                "penaltyPercent": round(penalty, 2),
            },
        )
    return build_family_judgment(
        "models",
        "weak_signal",
        "low",
        "Within the observed scope, the models family does not yet show a size penalty strong enough to be considered dominant.",
        "The observed models have been compared, but the average difference remains below the configured diagnostic threshold; more separated evidence or more contrasting models are required for a strong conclusion.",
        {
            "smallModelMeanResponseTimeMs": round(small_mean, 4),
            "largeModelMeanResponseTimeMs": round(large_mean, 4),
            "penaltyPercent": round(penalty, 2) if penalty is not None else None,
            "modelPenaltyThresholdPercent": profile["modelPenaltyThresholdPercent"],
        },
    )


def diagnose_baseline(profile, family_data, findings):
    measured = {scenario_id: data for scenario_id, data in family_data.items() if data.get("summary")}
    if not measured:
        return None

    scenario_id, data = sorted(measured.items())[0]
    summary = data["summary"]
    request_count = metric_mean(summary, "request_count")
    failure_count = metric_mean(summary, "failure_count")
    success_rate = None
    if request_count not in (None, 0):
        success_rate = ((request_count - (failure_count or 0)) / request_count) * 100.0
    snapshot = compact_metric_snapshot(scenario_metric_snapshot(summary))
    snapshot.update({
        "request_count": request_count,
        "failure_count": failure_count,
        "success_rate_percent": round(success_rate, 4) if success_rate is not None else None,
    })

    add_finding(
        findings,
        "provider_backed_baseline_measured",
        "The provider-backed baseline produced measurable request-level evidence.",
        "high",
        {
            "scenarioId": scenario_id,
            "sampleCount": summary.get("sampleCount"),
            "metrics": {key: value for key, value in snapshot.items() if value is not None},
            "units": METRIC_UNITS,
        },
        "The provider-backed workflow is ready to act as the reference baseline for subsequent controlled comparisons.",
    )

    return build_family_judgment(
        "baseline",
        "provider_backed_baseline_available",
        "high",
        "The provider-backed baseline is measurable and ready for controlled comparisons.",
        "Baseline evidence is available for the provider-backed cycle and can be used as the reference point for later resource, node-count and placement comparisons.",
        {
            "scenarioId": scenario_id,
            "sampleCount": summary.get("sampleCount"),
            "metrics": {key: value for key, value in snapshot.items() if value is not None},
            "units": METRIC_UNITS,
        },
    )


LEGACY_PLACEMENT_ALIAS_MAP = {
    "PL1": {
        "placementProfileId": "PL_COLOCATED",
        "description": "Historical co-located fixed-cluster placement scenario",
    },
    "PL2": {
        "placementProfileId": "PL_DISTRIBUTED_TWO_NODE",
        "description": "Historical distributed two-node fixed-cluster placement scenario",
    },
}


def diagnose_placement(profile, family_data, findings):
    colocated_id = "PL1"
    distributed_id = "PL2"
    colocated = family_data.get(colocated_id, {}).get("summary")
    distributed = family_data.get(distributed_id, {}).get("summary")
    if not colocated or not distributed:
        return build_family_judgment(
            "placement",
            "insufficient_evidence",
            "low",
            "The placement family does not yet provide enough comparable configurations for a robust assessment.",
            "Without both placement configurations measured with homogeneous metrics, the effect of worker placement cannot be estimated reliably.",
            {"availableScenarios": sorted([scenario_id for scenario_id, entry in family_data.items() if entry.get("summary")])},
        )
    if "mean_response_time_ms" not in colocated["metrics"] or "mean_response_time_ms" not in distributed["metrics"]:
        return build_family_judgment(
            "placement",
            "insufficient_evidence",
            "low",
            "The placement family does not yet contain enough comparable latency metrics for a robust interpretation.",
            "Placement configurations are present, but the absence of key metrics prevents a reliable placement-effect assessment.",
            {"availableScenarios": sorted([scenario_id for scenario_id, entry in family_data.items() if entry.get("summary")])},
        )

    colocated_mean = colocated["metrics"]["mean_response_time_ms"]["mean"]
    distributed_mean = distributed["metrics"]["mean_response_time_ms"]["mean"]
    colocated_throughput = metric_mean(colocated, "throughput_rps")
    distributed_throughput = metric_mean(distributed, "throughput_rps")
    throughput_diff = percent_change(colocated_throughput, distributed_throughput) if colocated_throughput is not None and distributed_throughput is not None else None
    diff = percent_change(colocated_mean, distributed_mean)

    evidence = {
        "referencePlacementScenario": colocated_id,
        "referencePlacementProfileId": LEGACY_PLACEMENT_ALIAS_MAP[colocated_id]["placementProfileId"],
        "candidatePlacementScenario": distributed_id,
        "candidatePlacementProfileId": LEGACY_PLACEMENT_ALIAS_MAP[distributed_id]["placementProfileId"],
        "legacyPlacementAliasPolicy": LEGACY_PLACEMENT_ALIAS_MAP,
        "referenceMeanResponseTimeMs": colocated_mean,
        "candidateMeanResponseTimeMs": distributed_mean,
        "referenceThroughputRps": colocated_throughput,
        "candidateThroughputRps": distributed_throughput,
        "throughputDifferencePercentVsReference": round(throughput_diff, 2) if throughput_diff is not None else None,
        "differencePercentVsReference": round(diff, 2) if diff is not None else None,
    }

    if diff is not None and abs(diff) >= profile["placementDifferenceThresholdPercent"]:
        if distributed_mean > colocated_mean:
            title = "Distributed placement is more expensive than co-located placement in the current cluster."
            implication = "Inter-node or coordination overhead may outweigh balancing benefits, at least in the current two-worker-node topology."
            judgment_title = "The placement family shows a measurable signal: in the current cluster, distributed placement is detrimental compared with the co-located baseline."
            judgment_implication = "Worker placement has a visible impact on observed performance and suggests that inter-node overhead is not negligible in the current topology."
        else:
            title = "Distributed placement shows a measurable advantage over co-located placement."
            implication = "Distributing workers across available nodes may help reduce local contention and improve service behavior."
            judgment_title = "The placement family shows a measurable signal: in the current cluster, distributed placement provides a visible advantage over the co-located baseline."
            judgment_implication = "Worker placement has an observable impact on latency and suggests that reduced local contention outweighs coordination overhead within the current scope."
        add_finding(
            findings,
            "placement_effect",
            title,
            "medium",
            evidence,
            implication,
        )
        return build_family_judgment(
            "placement",
            "strong_signal",
            "medium",
            judgment_title,
            judgment_implication,
            evidence,
        )
    return build_family_judgment(
        "placement",
        "weak_signal",
        "low",
        "Within the observed scope, the placement family does not yet show a strong enough effect to be considered dominant.",
        "Placement configurations were compared against the historical co-located placement resolved to the canonical PL_COLOCATED placement profile, but the latency difference remains below the configured diagnostic threshold; in the current cluster, placement does not yet emerge as the primary performance driver.",
        {
            **evidence,
            "placementDifferenceThresholdPercent": profile["placementDifferenceThresholdPercent"],
        },
    )


def resource_variant_sort_key(entry):
    scenario = entry.get("scenario") or {}
    variant = scenario.get("resourceVariant") or {}
    return (
        int(variant.get("workerVcpusPerNode") or 0),
        int(variant.get("workerMemoryGiBPerNode") or 0),
        str(scenario.get("scenarioId") or scenario.get("baselineId") or ""),
    )


def unsupported_capacity_summary(unsupported):
    summary = {
        "unsupportedScenarioIds": [],
        "evidenceKinds": [],
        "resourceLimitsByScenario": {},
        "reasonsByScenario": {},
    }
    kinds = set()
    for item in unsupported:
        scenario_id = item.get("scenarioId")
        summary["unsupportedScenarioIds"].append(scenario_id)
        unsupported_summary = item.get("unsupportedSummary") or {}
        for kind in unsupported_summary.get("evidenceKinds") or []:
            kinds.add(kind)
        variant = item.get("resourceVariant") or {}
        summary["resourceLimitsByScenario"][scenario_id] = {
            "workerVcpusPerNode": variant.get("workerVcpusPerNode"),
            "workerMemoryGiBPerNode": variant.get("workerMemoryGiBPerNode"),
            "totalWorkerVcpus": variant.get("totalWorkerVcpus"),
            "totalWorkerMemoryGiB": variant.get("totalWorkerMemoryGiB"),
        }
        summary["reasonsByScenario"][scenario_id] = unsupported_summary.get("reasons") or []
    summary["unsupportedScenarioIds"] = [item for item in summary["unsupportedScenarioIds"] if item]
    summary["evidenceKinds"] = sorted(kinds)
    return summary


def diagnose_resource_variation(profile, family_data, findings):
    measured = []
    unsupported = []
    for scenario_id, entry in sorted(family_data.items(), key=lambda item: resource_variant_sort_key(item[1])):
        summary = entry.get("summary")
        variant = (entry.get("scenario") or {}).get("resourceVariant") or {}
        if summary and "mean_response_time_ms" in summary.get("metrics", {}):
            measured.append({
                "scenarioId": scenario_id,
                "workerVcpusPerNode": variant.get("workerVcpusPerNode"),
                "workerMemoryGiBPerNode": variant.get("workerMemoryGiBPerNode"),
                "totalWorkerVcpus": variant.get("totalWorkerVcpus"),
                "totalWorkerMemoryGiB": variant.get("totalWorkerMemoryGiB"),
                "meanResponseTimeMs": metric_mean(summary, "mean_response_time_ms"),
                "p95ResponseTimeMs": metric_mean(summary, "p95_response_time_ms"),
                "throughputRps": metric_mean(summary, "throughput_rps"),
                "maxNodeCpuPercentObserved": summary.get("maxNodeCpuPercentObserved"),
                "maxNodeMemoryPercentObserved": summary.get("maxNodeMemoryPercentObserved"),
                "sampleCount": summary.get("sampleCount"),
            })
        elif entry.get("unsupportedSummary"):
            unsupported.append({
                "scenarioId": scenario_id,
                "unsupportedSummary": entry.get("unsupportedSummary"),
                "resourceVariant": variant,
            })

    capacity_evidence = unsupported_capacity_summary(unsupported)
    reference_id = (profile.get("referenceScenarioByFamily") or {}).get("resource-variation")
    reference = next((item for item in measured if item["scenarioId"] == reference_id), measured[-1] if measured else None)

    if len(measured) < 2:
        if measured and unsupported:
            scheduler_kinds = set(capacity_evidence.get("evidenceKinds") or [])
            scheduler_constraint_available = bool(scheduler_kinds.intersection({
                "failed_scheduling",
                "insufficient_cpu",
                "insufficient_memory",
                "node_affinity_selector_mismatch",
                "rollout_timeout",
                "pending_pod",
            }))
            add_finding(
                findings,
                "resource_variation_capacity_boundary",
                "The resource-variation campaign identifies a deployability boundary under fixed application-level conditions.",
                "high" if scheduler_constraint_available else "medium",
                {
                    "measuredVariants": measured,
                    "unsupportedVariants": unsupported,
                    "capacityEvidence": capacity_evidence,
                    "referenceScenarioId": reference.get("scenarioId") if reference else reference_id,
                },
                "The campaign should be read as capacity-feasibility evidence: lower worker-node shapes are not benchmark-ready under the fixed co-located topology and current LocalAI resource requests, while the reference shape is measurable.",
                family="resource-variation",
            )
            if any(kind in scheduler_kinds for kind in ["insufficient_cpu", "insufficient_memory"]):
                add_finding(
                    findings,
                    "resource_variation_scheduler_resource_limit",
                    "Unsupported resource-variation variants expose Kubernetes scheduler resource constraints.",
                    "high",
                    capacity_evidence,
                    "The unsupported variants provide concrete evidence about CPU and memory feasibility limits and should not be treated as ordinary benchmark failures.",
                    family="resource-variation",
                )
            return build_family_judgment(
                "resource-variation",
                "capacity_boundary_signal_available",
                "medium",
                "The resource-variation family provides deployability-boundary evidence, but not yet a full latency/throughput comparison.",
                "At least two measured resource shapes are still required for a robust performance comparison; however, the campaign already identifies which lower resource shapes cannot host the fixed LocalAI topology under the current constraints.",
                {
                    "measuredVariants": measured,
                    "unsupportedVariants": unsupported,
                    "capacityEvidence": capacity_evidence,
                    "minimumMeasuredVariantsForPerformanceComparison": 2,
                    "interpretation": "capacity_feasibility_boundary",
                },
            )
        return build_family_judgment(
            "resource-variation",
            "insufficient_evidence",
            "low",
            "The resource-variation family does not yet contain enough measured variants for a robust comparison.",
            "At least two measured resource shapes are needed before CPU/RAM sensitivity can be interpreted; unsupported variants remain retained as capacity evidence.",
            {"measuredVariants": measured, "unsupportedVariants": unsupported, "capacityEvidence": capacity_evidence},
        )

    reference = reference or measured[-1]
    comparisons = []
    for item in measured:
        comparisons.append({
            "scenarioId": item["scenarioId"],
            "workerVcpusPerNode": item.get("workerVcpusPerNode"),
            "workerMemoryGiBPerNode": item.get("workerMemoryGiBPerNode"),
            "meanResponseTimeMs": item.get("meanResponseTimeMs"),
            "meanLatencyDeltaVsReferencePercent": round(percent_change(reference.get("meanResponseTimeMs"), item.get("meanResponseTimeMs")), 4) if percent_change(reference.get("meanResponseTimeMs"), item.get("meanResponseTimeMs")) is not None else None,
            "throughputRps": item.get("throughputRps"),
            "throughputDeltaVsReferencePercent": round(percent_change(reference.get("throughputRps"), item.get("throughputRps")), 4) if percent_change(reference.get("throughputRps"), item.get("throughputRps")) is not None else None,
            "maxNodeCpuPercentObserved": item.get("maxNodeCpuPercentObserved"),
            "maxNodeMemoryPercentObserved": item.get("maxNodeMemoryPercentObserved"),
        })

    best_latency = min((item for item in measured if item.get("meanResponseTimeMs") is not None), key=lambda item: item["meanResponseTimeMs"], default=None)
    best_throughput = max((item for item in measured if item.get("throughputRps") is not None), key=lambda item: item["throughputRps"], default=None)
    if best_latency:
        add_finding(
            findings,
            "resource_variation_lowest_latency",
            "The resource-variation campaign identifies a lowest-latency resource shape among measured variants.",
            "medium",
            {"bestLatencyVariant": best_latency, "referenceScenarioId": reference.get("scenarioId")},
            "The result provides a controlled signal for CPU/RAM sensitivity under fixed application-level conditions.",
            family="resource-variation",
        )
    if unsupported:
        add_finding(
            findings,
            "resource_variation_unsupported_variants",
            "At least one resource-variation scenario produced unsupported evidence under the current constraints.",
            "medium",
            {"unsupportedVariants": unsupported, "capacityEvidence": capacity_evidence},
            "Unsupported variants should be treated as capacity or provider evidence and not as measured performance regressions.",
            family="resource-variation",
        )

    return build_family_judgment(
        "resource-variation",
        "comparative_signal_available",
        "medium",
        "The resource-variation family provides comparable CPU/RAM sensitivity evidence.",
        "The campaign can be used to reason about whether additional worker CPU or memory improves latency, throughput or resource pressure while model, workload, worker count and placement remain fixed.",
        {
            "referenceScenarioId": reference.get("scenarioId"),
            "measuredVariantCount": len(measured),
            "unsupportedVariantCount": len(unsupported),
            "capacityEvidence": capacity_evidence,
            "comparisons": comparisons,
            "bestLatencyScenarioId": best_latency.get("scenarioId") if best_latency else None,
            "bestThroughputScenarioId": best_throughput.get("scenarioId") if best_throughput else None,
        },
    )


def node_count_variant_sort_key(entry):
    scenario = entry.get("scenario") or {}
    variant = scenario.get("nodeCountVariant") or {}
    return (
        variant.get("workerNodeCount") if variant.get("workerNodeCount") is not None else scenario.get("infrastructureWorkerNodeCount", 0),
        scenario.get("scenarioId") or scenario.get("baselineId") or "",
    )


def diagnose_node_count_variation(profile, family_data, findings):
    measured = []
    unsupported = []
    for scenario_id, entry in sorted(family_data.items(), key=lambda item: node_count_variant_sort_key(item[1])):
        scenario = entry.get("scenario") or {}
        variant = scenario.get("nodeCountVariant") or {}
        summary = entry.get("summary")
        unsupported_summary = entry.get("unsupportedSummary")
        record = {
            "scenarioId": scenario_id,
            "label": scenario.get("scenarioLabel") or variant.get("label") or scenario_id,
            "workerNodeCount": variant.get("workerNodeCount") or scenario.get("infrastructureWorkerNodeCount"),
            "localAiWorkerCount": scenario.get("resolvedWorkerCount"),
            "workerVcpusPerNode": variant.get("workerVcpusPerNode"),
            "workerMemoryGiBPerNode": variant.get("workerMemoryGiBPerNode"),
            "totalWorkerVcpus": variant.get("totalWorkerVcpus"),
            "totalWorkerMemoryGiB": variant.get("totalWorkerMemoryGiB"),
            "placementProfileId": scenario.get("placementProfileId"),
            "placementType": scenario.get("resolvedPlacementType"),
            "topologyDir": scenario.get("topologyDir"),
        }
        if summary and "mean_response_time_ms" in (summary.get("metrics") or {}):
            record.update({
                "sampleCount": summary.get("sampleCount"),
                "meanResponseTimeMs": metric_mean(summary, "mean_response_time_ms"),
                "p95ResponseTimeMs": metric_mean(summary, "p95_response_time_ms"),
                "p99ResponseTimeMs": metric_mean(summary, "p99_response_time_ms"),
                "throughputRps": metric_mean(summary, "throughput_rps"),
                "maxNodeCpuPercentObserved": summary.get("maxNodeCpuPercentObserved"),
                "maxNodeMemoryPercentObserved": summary.get("maxNodeMemoryPercentObserved"),
                "observedPlacementNodeCounts": summary.get("observedPlacementNodeCounts"),
            })
            measured.append(record)
        elif unsupported_summary:
            record.update({
                "unsupportedReplicaCount": unsupported_summary.get("unsupportedReplicaCount"),
                "evidenceKinds": unsupported_summary.get("evidenceKinds"),
                "reasons": unsupported_summary.get("reasons"),
            })
            unsupported.append(record)

    reference_id = (profile.get("referenceScenarioByFamily") or {}).get("node-count-variation")
    reference = next((item for item in measured if item.get("scenarioId") == reference_id), None) or (measured[0] if measured else None)
    if len(measured) < 2:
        add_finding(
            findings,
            "node_count_variation_insufficient_measured_variants",
            "The node-count campaign does not yet contain enough measured variants for a robust comparison.",
            "low",
            {
                "measuredVariants": measured,
                "unsupportedVariants": unsupported,
                "minimumMeasuredVariantsForComparison": 2,
            },
            "At least two measured infrastructure node-count shapes are required before distribution or overhead effects can be interpreted comparatively.",
            family="node-count-variation",
        )
        return build_family_judgment(
            "node-count-variation",
            "insufficient_evidence",
            "low",
            "The node-count variation family does not yet provide enough measured evidence.",
            "The campaign should be rerun until at least two worker-node-count variants produce benchmark samples, while unsupported variants remain retained as capacity or scheduling evidence.",
            {"measuredVariantCount": len(measured), "unsupportedVariantCount": len(unsupported), "measuredVariants": measured, "unsupportedVariants": unsupported},
        )

    comparisons = []
    for item in measured:
        comparisons.append({
            "scenarioId": item.get("scenarioId"),
            "workerNodeCount": item.get("workerNodeCount"),
            "meanResponseTimeMs": item.get("meanResponseTimeMs"),
            "meanLatencyDeltaVsReferencePercent": round(percent_change(reference.get("meanResponseTimeMs"), item.get("meanResponseTimeMs")), 4) if percent_change(reference.get("meanResponseTimeMs"), item.get("meanResponseTimeMs")) is not None else None,
            "throughputRps": item.get("throughputRps"),
            "throughputDeltaVsReferencePercent": round(percent_change(reference.get("throughputRps"), item.get("throughputRps")), 4) if percent_change(reference.get("throughputRps"), item.get("throughputRps")) is not None else None,
            "maxNodeCpuPercentObserved": item.get("maxNodeCpuPercentObserved"),
            "maxNodeMemoryPercentObserved": item.get("maxNodeMemoryPercentObserved"),
            "observedPlacementNodeCounts": item.get("observedPlacementNodeCounts"),
        })

    best_latency = min((item for item in measured if item.get("meanResponseTimeMs") is not None), key=lambda item: item["meanResponseTimeMs"], default=None)
    best_throughput = max((item for item in measured if item.get("throughputRps") is not None), key=lambda item: item["throughputRps"], default=None)
    add_finding(
        findings,
        "node_count_variation_comparative_signal",
        "The node-count campaign provides measured evidence across multiple infrastructure sizes.",
        "medium",
        {"referenceScenarioId": reference.get("scenarioId"), "comparisons": comparisons, "unsupportedVariants": unsupported},
        "The evidence can be used to evaluate whether additional provider worker nodes reduce LocalAI contention, introduce communication overhead, or remain unused by the fixed application topology.",
        family="node-count-variation",
    )
    if best_latency:
        add_finding(
            findings,
            "node_count_variation_lowest_latency",
            "The node-count campaign identifies the lowest-latency infrastructure worker-node count among measured variants.",
            "medium",
            {"bestLatencyVariant": best_latency, "referenceScenarioId": reference.get("scenarioId")},
            "This result provides a controlled signal for the node-count dimension under fixed model, workload, LocalAI worker count, per-node resources and placement policy.",
            family="node-count-variation",
        )
    if unsupported:
        add_finding(
            findings,
            "node_count_variation_unsupported_variants",
            "At least one node-count scenario produced unsupported evidence under the current constraints.",
            "medium",
            {"unsupportedVariants": unsupported},
            "Unsupported variants should be treated as capacity or provider evidence and not as measured performance regressions.",
            family="node-count-variation",
        )

    return build_family_judgment(
        "node-count-variation",
        "comparative_signal_available",
        "medium",
        "The node-count variation family provides comparable infrastructure-size evidence.",
        "The campaign can be used to reason about whether adding provider worker nodes improves distribution and performance, or introduces overhead, while per-node capacity and application-level dimensions remain fixed.",
        {
            "referenceScenarioId": reference.get("scenarioId"),
            "measuredVariantCount": len(measured),
            "unsupportedVariantCount": len(unsupported),
            "comparisons": comparisons,
            "bestLatencyScenarioId": best_latency.get("scenarioId") if best_latency else None,
            "bestThroughputScenarioId": best_throughput.get("scenarioId") if best_throughput else None,
        },
    )


def placement_variant_sort_key(entry):
    scenario = entry.get("scenario") or {}
    variant = scenario.get("placementVariant") or {}
    order = {
        "PLC_COLOCATED": 10,
        "PLC_DISTRIBUTED_TWO_NODE": 20,
        "PLC_SPREAD_WORKERS": 30,
        "PLC_SERVER_SEPARATED": 40,
        "PLC_BALANCED_STATIC": 50,
    }
    scenario_id = scenario.get("scenarioId") or scenario.get("baselineId") or ""
    return (order.get(scenario_id, 100), str(variant.get("label") or scenario_id))


def diagnose_placement_variation(profile, family_data, findings):
    measured = []
    unsupported = []
    for scenario_id, entry in sorted(family_data.items(), key=lambda item: placement_variant_sort_key(item[1])):
        scenario = entry.get("scenario") or {}
        variant = scenario.get("placementVariant") or {}
        summary = entry.get("summary")
        unsupported_summary = entry.get("unsupportedSummary")
        record = {
            "scenarioId": scenario_id,
            "label": scenario.get("scenarioLabel") or variant.get("label") or scenario_id,
            "placementProfileId": scenario.get("placementProfileId") or variant.get("placementProfileId"),
            "placementType": scenario.get("resolvedPlacementType"),
            "serverNode": scenario.get("expectedServerNode") or variant.get("serverNode"),
            "workerNodeMap": scenario.get("expectedWorkerNodes") or variant.get("workerNodeMap"),
            "topologyDir": scenario.get("topologyDir"),
            "expectedCommunicationDistance": variant.get("expectedCommunicationDistance"),
            "expectedResourceContention": variant.get("expectedResourceContention"),
        }
        if summary and "mean_response_time_ms" in (summary.get("metrics") or {}):
            record.update({
                "sampleCount": summary.get("sampleCount"),
                "meanResponseTimeMs": metric_mean(summary, "mean_response_time_ms"),
                "p95ResponseTimeMs": metric_mean(summary, "p95_response_time_ms"),
                "p99ResponseTimeMs": metric_mean(summary, "p99_response_time_ms"),
                "throughputRps": metric_mean(summary, "throughput_rps"),
                "maxNodeCpuPercentObserved": summary.get("maxNodeCpuPercentObserved"),
                "maxNodeMemoryPercentObserved": summary.get("maxNodeMemoryPercentObserved"),
                "observedPlacementNodeCounts": summary.get("observedPlacementNodeCounts"),
            })
            measured.append(record)
        elif unsupported_summary:
            record.update({
                "unsupportedReplicaCount": unsupported_summary.get("unsupportedReplicaCount"),
                "evidenceKinds": unsupported_summary.get("evidenceKinds"),
                "reasons": unsupported_summary.get("reasons"),
            })
            unsupported.append(record)

    reference_id = (profile.get("referenceScenarioByFamily") or {}).get("placement-variation")
    reference = next((item for item in measured if item.get("scenarioId") == reference_id), None) or (measured[0] if measured else None)
    if len(measured) < 2:
        add_finding(
            findings,
            "placement_variation_insufficient_measured_variants",
            "The placement campaign does not yet contain enough measured variants for a robust comparison.",
            "low",
            {"measuredVariants": measured, "unsupportedVariants": unsupported, "minimumMeasuredVariantsForComparison": 2},
            "At least two measured placement variants are required before placement effects can be interpreted comparatively; unsupported variants remain retained as placement or capacity evidence.",
            family="placement-variation",
        )
        return build_family_judgment(
            "placement-variation",
            "insufficient_evidence",
            "low",
            "The placement variation family does not yet provide enough measured evidence.",
            "The campaign should be rerun until at least two placement variants produce benchmark samples, while unsupported variants remain retained as contention, capacity or scheduling evidence.",
            {"measuredVariantCount": len(measured), "unsupportedVariantCount": len(unsupported), "measuredVariants": measured, "unsupportedVariants": unsupported},
        )

    comparisons = []
    for item in measured:
        comparisons.append({
            "scenarioId": item.get("scenarioId"),
            "placementProfileId": item.get("placementProfileId"),
            "serverNode": item.get("serverNode"),
            "workerNodeMap": item.get("workerNodeMap"),
            "meanResponseTimeMs": item.get("meanResponseTimeMs"),
            "meanLatencyDeltaVsReferencePercent": round(percent_change(reference.get("meanResponseTimeMs"), item.get("meanResponseTimeMs")), 4) if percent_change(reference.get("meanResponseTimeMs"), item.get("meanResponseTimeMs")) is not None else None,
            "throughputRps": item.get("throughputRps"),
            "throughputDeltaVsReferencePercent": round(percent_change(reference.get("throughputRps"), item.get("throughputRps")), 4) if percent_change(reference.get("throughputRps"), item.get("throughputRps")) is not None else None,
            "maxNodeCpuPercentObserved": item.get("maxNodeCpuPercentObserved"),
            "maxNodeMemoryPercentObserved": item.get("maxNodeMemoryPercentObserved"),
            "observedPlacementNodeCounts": item.get("observedPlacementNodeCounts"),
        })

    best_latency = min((item for item in measured if item.get("meanResponseTimeMs") is not None), key=lambda item: item["meanResponseTimeMs"], default=None)
    best_throughput = max((item for item in measured if item.get("throughputRps") is not None), key=lambda item: item["throughputRps"], default=None)
    add_finding(
        findings,
        "placement_variation_comparative_signal",
        "The placement campaign provides measured evidence across multiple placement policies.",
        "medium",
        {"referenceScenarioId": reference.get("scenarioId"), "comparisons": comparisons, "unsupportedVariants": unsupported},
        "The evidence can be used to evaluate whether communication-distance reduction or resource-contention reduction dominates under the fixed infrastructure and workload.",
        family="placement-variation",
    )
    if best_latency:
        add_finding(
            findings,
            "placement_variation_lowest_latency",
            "The placement campaign identifies the lowest-latency placement among measured variants.",
            "medium",
            {"bestLatencyVariant": best_latency, "referenceScenarioId": reference.get("scenarioId")},
            "This result provides a controlled signal for placement selection under fixed infrastructure, model, workload and LocalAI worker count.",
            family="placement-variation",
        )
    if unsupported:
        add_finding(
            findings,
            "placement_variation_unsupported_variants",
            "At least one placement scenario produced unsupported evidence under the current constraints.",
            "medium",
            {"unsupportedVariants": unsupported},
            "Unsupported placement variants should be treated as contention, capacity or scheduling evidence and not as measured performance regressions.",
            family="placement-variation",
        )

    return build_family_judgment(
        "placement-variation",
        "comparative_signal_available",
        "medium",
        "The placement variation family provides comparable placement evidence.",
        "The campaign can be used to reason about the communication-vs-contention trade-off because infrastructure, model, workload and LocalAI worker count remain fixed while only placement changes.",
        {
            "referenceScenarioId": reference.get("scenarioId"),
            "measuredVariantCount": len(measured),
            "unsupportedVariantCount": len(unsupported),
            "comparisons": comparisons,
            "bestLatencyScenarioId": best_latency.get("scenarioId") if best_latency else None,
            "bestThroughputScenarioId": best_throughput.get("scenarioId") if best_throughput else None,
        },
    )


def latency_variant_sort_key(entry):
    scenario = entry.get("scenario") or {}
    variant = scenario.get("latencyVariant") or {}
    return (
        variant.get("delayMs") if variant.get("delayMs") is not None else 0,
        variant.get("jitterMs") if variant.get("jitterMs") is not None else 0,
        scenario.get("scenarioId") or scenario.get("baselineId") or "",
    )


def diagnose_latency_injection(profile, family_data, findings):
    measured = []
    unsupported = []
    for scenario_id, entry in sorted(family_data.items(), key=lambda item: latency_variant_sort_key(item[1])):
        scenario = entry.get("scenario") or {}
        variant = scenario.get("latencyVariant") or {}
        summary = entry.get("summary")
        unsupported_summary = entry.get("unsupportedSummary")
        record = {
            "scenarioId": scenario_id,
            "label": scenario.get("scenarioLabel") or variant.get("label") or scenario_id,
            "latencyProfileId": scenario.get("latencyProfileId") or variant.get("latencyProfileId"),
            "delayMs": variant.get("delayMs"),
            "jitterMs": variant.get("jitterMs"),
            "packetLossPercent": variant.get("packetLossPercent"),
            "placementProfileId": scenario.get("placementProfileId"),
            "placementType": scenario.get("resolvedPlacementType"),
            "topologyDir": scenario.get("topologyDir"),
        }
        if summary and "mean_response_time_ms" in (summary.get("metrics") or {}):
            record.update({
                "sampleCount": summary.get("sampleCount"),
                "meanResponseTimeMs": metric_mean(summary, "mean_response_time_ms"),
                "p95ResponseTimeMs": metric_mean(summary, "p95_response_time_ms"),
                "p99ResponseTimeMs": metric_mean(summary, "p99_response_time_ms"),
                "throughputRps": metric_mean(summary, "throughput_rps"),
                "maxNodeCpuPercentObserved": summary.get("maxNodeCpuPercentObserved"),
                "maxNodeMemoryPercentObserved": summary.get("maxNodeMemoryPercentObserved"),
                "observedPlacementNodeCounts": summary.get("observedPlacementNodeCounts"),
            })
            measured.append(record)
        elif unsupported_summary:
            record.update({
                "unsupportedReplicaCount": unsupported_summary.get("unsupportedReplicaCount"),
                "evidenceKinds": unsupported_summary.get("evidenceKinds"),
                "reasons": unsupported_summary.get("reasons"),
            })
            unsupported.append(record)

    reference_id = (profile.get("referenceScenarioByFamily") or {}).get("latency-injection")
    reference = next((item for item in measured if item.get("scenarioId") == reference_id), None) or (measured[0] if measured else None)
    if len(measured) < 2:
        add_finding(
            findings,
            "latency_injection_insufficient_measured_variants",
            "The latency-injection campaign does not yet contain enough measured variants for a robust comparison.",
            "low",
            {"measuredVariants": measured, "unsupportedVariants": unsupported, "minimumMeasuredVariantsForComparison": 2},
            "At least two measured latency profiles, including the no-latency reference, are required before network-sensitivity effects can be interpreted comparatively.",
            family="latency-injection",
        )
        return build_family_judgment(
            "latency-injection",
            "insufficient_evidence",
            "low",
            "The latency-injection family does not yet provide enough measured evidence.",
            "The campaign should be rerun until at least two latency variants produce benchmark samples; unsupported variants remain retained as instrumentation, timeout or network-sensitivity evidence.",
            {"measuredVariantCount": len(measured), "unsupportedVariantCount": len(unsupported), "measuredVariants": measured, "unsupportedVariants": unsupported},
        )

    comparisons = []
    for item in measured:
        comparisons.append({
            "scenarioId": item.get("scenarioId"),
            "latencyProfileId": item.get("latencyProfileId"),
            "delayMs": item.get("delayMs"),
            "jitterMs": item.get("jitterMs"),
            "meanResponseTimeMs": item.get("meanResponseTimeMs"),
            "meanLatencyDeltaVsReferencePercent": round(percent_change(reference.get("meanResponseTimeMs"), item.get("meanResponseTimeMs")), 4) if percent_change(reference.get("meanResponseTimeMs"), item.get("meanResponseTimeMs")) is not None else None,
            "throughputRps": item.get("throughputRps"),
            "throughputDeltaVsReferencePercent": round(percent_change(reference.get("throughputRps"), item.get("throughputRps")), 4) if percent_change(reference.get("throughputRps"), item.get("throughputRps")) is not None else None,
            "maxNodeCpuPercentObserved": item.get("maxNodeCpuPercentObserved"),
            "maxNodeMemoryPercentObserved": item.get("maxNodeMemoryPercentObserved"),
        })

    best_latency = min((item for item in measured if item.get("meanResponseTimeMs") is not None), key=lambda item: item["meanResponseTimeMs"], default=None)
    worst_latency = max((item for item in measured if item.get("meanResponseTimeMs") is not None), key=lambda item: item["meanResponseTimeMs"], default=None)
    best_throughput = max((item for item in measured if item.get("throughputRps") is not None), key=lambda item: item["throughputRps"], default=None)
    add_finding(
        findings,
        "latency_injection_comparative_signal",
        "The latency-injection campaign provides measured evidence across multiple network-latency profiles.",
        "medium",
        {"referenceScenarioId": reference.get("scenarioId"), "comparisons": comparisons, "unsupportedVariants": unsupported},
        "The evidence can be used to evaluate whether inter-node communication delay becomes a dominant factor under the fixed distributed placement.",
        family="latency-injection",
    )
    if worst_latency and reference:
        add_finding(
            findings,
            "latency_injection_highest_latency",
            "The latency-injection campaign identifies the highest-latency measured profile.",
            "medium",
            {"worstLatencyVariant": worst_latency, "referenceScenarioId": reference.get("scenarioId")},
            "This result provides a controlled signal for deciding when distributed worker placement becomes sensitive to network delay.",
            family="latency-injection",
        )
    if unsupported:
        add_finding(
            findings,
            "latency_injection_unsupported_variants",
            "At least one latency-injection scenario produced unsupported evidence under the current constraints.",
            "medium",
            {"unsupportedVariants": unsupported},
            "Unsupported latency variants should be treated as instrumentation, timeout or network-sensitivity evidence and not as ordinary benchmark failures.",
            family="latency-injection",
        )

    return build_family_judgment(
        "latency-injection",
        "comparative_signal_available",
        "medium",
        "The latency-injection family provides comparable network-sensitivity evidence.",
        "The campaign can be used to reason about when injected inter-node latency degrades LocalAI worker-mode behavior because infrastructure, model, workload, worker count and placement remain fixed while only latency changes.",
        {
            "referenceScenarioId": reference.get("scenarioId"),
            "measuredVariantCount": len(measured),
            "unsupportedVariantCount": len(unsupported),
            "comparisons": comparisons,
            "bestLatencyScenarioId": best_latency.get("scenarioId") if best_latency else None,
            "worstLatencyScenarioId": worst_latency.get("scenarioId") if worst_latency else None,
            "bestThroughputScenarioId": best_throughput.get("scenarioId") if best_throughput else None,
        },
    )


def tenancy_variant_sort_key(entry):
    scenario = entry.get("scenario") or {}
    variant = scenario.get("tenancyVariant") or {}
    return (
        variant.get("tenantCount") if variant.get("tenantCount") is not None else 0,
        str(variant.get("coTenantModelScenario") or ""),
        str(variant.get("coTenantPlacement") or ""),
        scenario.get("scenarioId") or scenario.get("baselineId") or "",
    )


def diagnose_multi_tenancy(profile, family_data, findings):
    measured = []
    unsupported = []
    for scenario_id, entry in sorted(family_data.items(), key=lambda item: tenancy_variant_sort_key(item[1])):
        scenario = entry.get("scenario") or {}
        variant = scenario.get("tenancyVariant") or {}
        summary = entry.get("summary")
        unsupported_summary = entry.get("unsupportedSummary")
        record = {
            "scenarioId": scenario_id,
            "label": scenario.get("scenarioLabel") or variant.get("label") or scenario_id,
            "tenantCount": variant.get("tenantCount"),
            "benchmarkTenantId": variant.get("benchmarkTenantId"),
            "coTenantModelScenario": variant.get("coTenantModelScenario"),
            "coTenantPlacement": variant.get("coTenantPlacement"),
            "sharedNodePool": variant.get("sharedNodePool"),
            "metrics": compact_metric_snapshot(scenario_metric_snapshot(summary)) if summary else {},
            "unsupportedSummary": unsupported_summary,
        }
        if summary:
            record.update({
                "meanResponseTimeMs": metric_mean(summary, "mean_response_time_ms"),
                "throughputRps": metric_mean(summary, "throughput_rps"),
                "sampleCount": summary.get("sample_count"),
            })
            measured.append(record)
        elif unsupported_summary:
            unsupported.append(record)

    reference_id = (profile.get("referenceScenarioByFamily") or {}).get("multi-tenancy")
    reference = next((item for item in measured if item.get("scenarioId") == reference_id), None)
    comparisons = []
    for item in measured:
        comparisons.append({
            "scenarioId": item.get("scenarioId"),
            "label": item.get("label"),
            "tenantCount": item.get("tenantCount"),
            "coTenantModelScenario": item.get("coTenantModelScenario"),
            "coTenantPlacement": item.get("coTenantPlacement"),
            "meanResponseTimeMs": item.get("meanResponseTimeMs"),
            "throughputRps": item.get("throughputRps"),
            "maxNodeCpuPercentObserved": item.get("maxNodeCpuPercentObserved"),
            "maxNodeMemoryPercentObserved": item.get("maxNodeMemoryPercentObserved"),
            "clusterSideArtifactsAvailable": item.get("clusterSideArtifactsAvailable"),
            "latencyDeltaPercentVsReference": round(percent_change(reference.get("meanResponseTimeMs") if reference else None, item.get("meanResponseTimeMs")), 2) if reference else None,
            "throughputDeltaPercentVsReference": round(percent_change(reference.get("throughputRps") if reference else None, item.get("throughputRps")), 2) if reference else None,
        })

    if len(measured) < 2:
        add_finding(
            findings,
            "multi_tenancy_insufficient_measured_variants",
            "The multi-tenancy campaign does not yet contain enough measured variants for a robust comparison.",
            "medium",
            {"measuredVariantCount": len(measured), "unsupportedVariantCount": len(unsupported)},
            "At least two measured tenancy variants are required before co-tenant effects can be interpreted comparatively; unsupported variants remain retained as capacity or placement evidence.",
            family="multi-tenancy",
        )
        return build_family_judgment(
            "multi-tenancy",
            "insufficient_measured_evidence",
            "medium",
            "The multi-tenancy family does not yet provide enough measured evidence.",
            "The campaign should be rerun until at least two tenant-topology variants produce benchmark samples, while unsupported variants remain retained as resource-contention evidence.",
            {"measuredVariantCount": len(measured), "unsupportedVariantCount": len(unsupported), "referenceScenarioId": reference_id},
        )

    best_latency = min((item for item in measured if item.get("meanResponseTimeMs") is not None), key=lambda item: item["meanResponseTimeMs"], default=None)
    worst_latency = max((item for item in measured if item.get("meanResponseTimeMs") is not None), key=lambda item: item["meanResponseTimeMs"], default=None)
    best_throughput = max((item for item in measured if item.get("throughputRps") is not None), key=lambda item: item["throughputRps"], default=None)
    add_finding(
        findings,
        "multi_tenancy_comparative_signal",
        "The multi-tenancy campaign provides measured evidence across tenant-topology variants.",
        "medium",
        {"referenceScenarioId": reference_id, "comparisons": comparisons, "unsupportedVariantCount": len(unsupported)},
        "The evidence can be used to reason about co-tenant contention and placement effects under fixed infrastructure and primary benchmark workload.",
        family="multi-tenancy",
    )
    if unsupported:
        add_finding(
            findings,
            "multi_tenancy_unsupported_variants",
            "At least one multi-tenant topology produced unsupported evidence under the current constraints.",
            "medium",
            {"unsupportedVariants": unsupported},
            "Unsupported tenant topologies should be treated as capacity, placement or rollout evidence and not as missing measurements.",
            family="multi-tenancy",
        )

    return build_family_judgment(
        "multi-tenancy",
        "comparative_signal_available",
        "medium",
        "The multi-tenancy family provides comparable tenant-coexistence evidence.",
        "The campaign can be used to reason about tenant-count, model-mix and placement effects because infrastructure and primary benchmark workload remain fixed while tenant topology changes.",
        {
            "referenceScenarioId": reference_id,
            "measuredVariantCount": len(measured),
            "unsupportedVariantCount": len(unsupported),
            "comparisons": comparisons,
            "bestLatencyScenarioId": best_latency.get("scenarioId") if best_latency else None,
            "worstLatencyScenarioId": worst_latency.get("scenarioId") if worst_latency else None,
            "bestThroughputScenarioId": best_throughput.get("scenarioId") if best_throughput else None,
        },
    )


def default_scheduler_variant_sort_key(entry):
    scenario = entry.get("scenario") or {}
    class_rank = {"official": 0, "diagnostic": 1, "stress": 2}
    latency_rank = {"L0_NONE": 0, "L1_EDGE_NEAR": 1, "L2_EDGE_REMOTE": 2, "L3_EXTREME": 3}
    return (
        class_rank.get(str(scenario.get("scenarioClass") or ""), 99),
        scenario.get("tenantCount") if scenario.get("tenantCount") is not None else 0,
        scenario.get("workerNodeCount") if scenario.get("workerNodeCount") is not None else 0,
        latency_rank.get(str(scenario.get("latencyProfileId") or ""), 99),
        str(scenario.get("trafficProfileId") or ""),
        str(scenario.get("modelMix") or ""),
        str(scenario.get("scenarioId") or ""),
    )


def default_scheduler_metric_from_tenants(tenant_measurements: list[dict[str, Any]], key: str):
    values = []
    for item in tenant_measurements or []:
        value = to_number(item.get(key))
        if value is not None:
            values.append(value)
    if not values:
        return None
    return round(mean(values), 4)


def default_scheduler_tenant_total(tenant_measurements: list[dict[str, Any]], key: str):
    values = []
    for item in tenant_measurements or []:
        value = to_number(item.get(key))
        if value is not None:
            values.append(value)
    if not values:
        return None
    return int(round(sum(values)))


def default_scheduler_record(scenario_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    scenario = entry.get("scenario") or {}
    summary = entry.get("summary")
    tenant_measurements = entry.get("tenantMeasurements") or []
    scheduler_evidence = entry.get("schedulerDecisionEvidence") or {}
    placement = entry.get("placementClassification") or {}
    mean_latency = metric_mean(summary, "mean_response_time_ms") if summary else None
    p95_latency = metric_mean(summary, "p95_response_time_ms") if summary else None
    p99_latency = metric_mean(summary, "p99_response_time_ms") if summary else None
    throughput = metric_mean(summary, "throughput_rps") if summary else None
    if mean_latency is None:
        mean_latency = default_scheduler_metric_from_tenants(tenant_measurements, "averageResponseTimeMs")
    if p95_latency is None:
        p95_latency = default_scheduler_metric_from_tenants(tenant_measurements, "p95ResponseTimeMs")
    if p99_latency is None:
        p99_latency = default_scheduler_metric_from_tenants(tenant_measurements, "p99ResponseTimeMs")
    if throughput is None:
        throughput = default_scheduler_metric_from_tenants(tenant_measurements, "requestsPerSecond")
    request_count = metric_mean(summary, "request_count") if summary else None
    failure_count = metric_mean(summary, "failure_count") if summary else None
    if request_count is None:
        request_count = default_scheduler_tenant_total(tenant_measurements, "targetRequestCount")
    if failure_count is None:
        failure_count = default_scheduler_tenant_total(tenant_measurements, "failureCount")
    return {
        "scenarioId": scenario_id,
        "scenarioClass": scenario.get("scenarioClass"),
        "tenantCount": scenario.get("tenantCount"),
        "workerNodeCount": scenario.get("workerNodeCount"),
        "latencyAlias": scenario.get("latencyAlias"),
        "latencyProfileId": scenario.get("latencyProfileId"),
        "trafficProfileId": scenario.get("trafficProfileId"),
        "trafficShape": (scenario.get("trafficProfile") or {}).get("trafficShape"),
        "modelMix": scenario.get("modelMix"),
        "meanResponseTimeMs": mean_latency,
        "p95ResponseTimeMs": p95_latency,
        "p99ResponseTimeMs": p99_latency,
        "throughputRps": throughput,
        "requestCount": request_count,
        "failureCount": failure_count,
        "sampleCount": (summary or {}).get("sampleCount"),
        "tenantMeasurements": tenant_measurements,
        "hasValidTenantMeasurements": any(item.get("validTargetRequestsPresent") is True for item in tenant_measurements),
        "multiTenantSummaryPath": entry.get("multiTenantSummaryPath"),
        "multiTenantSummaryRuntime": entry.get("multiTenantSummaryRuntime"),
        "schedulerDecisionEvidencePath": entry.get("schedulerDecisionEvidencePath"),
        "schedulerDecisionEvidenceRuntime": entry.get("schedulerDecisionEvidenceRuntime"),
        "schedulerEvidenceStatus": scheduler_evidence.get("status") if isinstance(scheduler_evidence, dict) else None,
        "schedulerScenarioCategories": entry.get("schedulerScenarioCategories") or [],
        "schedulerScenarioRiskLevel": entry.get("schedulerScenarioRiskLevel"),
        "schedulerNegativeEvidenceCount": len(entry.get("schedulerNegativeEvidence") or []),
        "schedulerNegativeEvidence": entry.get("schedulerNegativeEvidence") or [],
        "placementCategoryCounts": (placement.get("categoryCounts") if isinstance(placement, dict) else {}),
        "nodeOccupancy": (placement.get("nodeOccupancy") if isinstance(placement, dict) else []),
        "clusterSideArtifactsAvailable": entry.get("clusterSideArtifactsAvailable"),
        "clusterSideArtifactCount": (entry.get("clusterSideArtifacts") or {}).get("artifactCount"),
        "maxNodeCpuPercentObserved": (summary or {}).get("maxNodeCpuPercentObserved") if isinstance(summary, dict) else None,
        "maxNodeMemoryPercentObserved": (summary or {}).get("maxNodeMemoryPercentObserved") if isinstance(summary, dict) else None,
        "unsupportedSummary": entry.get("unsupportedSummary"),
    }


def diagnose_default_scheduler(profile, family_data, findings):
    records = [
        default_scheduler_record(scenario_id, entry)
        for scenario_id, entry in sorted(family_data.items(), key=lambda item: default_scheduler_variant_sort_key(item[1]))
    ]
    measured = [item for item in records if item.get("meanResponseTimeMs") is not None or item.get("hasValidTenantMeasurements") or (item.get("requestCount") not in (None, 0))]
    scheduler_observed = [item for item in records if item.get("schedulerDecisionEvidenceRuntime")]
    placement_classified = [item for item in records if item.get("schedulerDecisionEvidenceRuntime") and item.get("schedulerScenarioCategories")]
    negative_records = [item for item in records if item.get("schedulerNegativeEvidenceCount", 0) > 0]
    unsupported = [item for item in records if item.get("unsupportedSummary")]
    differentiated = [item for item in records if str(item.get("trafficProfileId") or "").endswith("DIFFERENTIATED_LOW")]
    latency_enabled = [item for item in records if item.get("latencyProfileId") not in {None, "L0_NONE"}]

    reference_id = (profile.get("referenceScenarioByFamily") or {}).get("default-scheduler") or profile.get("referenceScenarioId")
    reference = next((item for item in measured if item.get("scenarioId") == reference_id), None)
    comparisons = []
    for item in measured:
        comparisons.append({
            "scenarioId": item.get("scenarioId"),
            "scenarioClass": item.get("scenarioClass"),
            "tenantCount": item.get("tenantCount"),
            "workerNodeCount": item.get("workerNodeCount"),
            "latencyProfileId": item.get("latencyProfileId"),
            "trafficProfileId": item.get("trafficProfileId"),
            "modelMix": item.get("modelMix"),
            "meanResponseTimeMs": item.get("meanResponseTimeMs"),
            "p95ResponseTimeMs": item.get("p95ResponseTimeMs"),
            "throughputRps": item.get("throughputRps"),
            "maxNodeCpuPercentObserved": item.get("maxNodeCpuPercentObserved"),
            "maxNodeMemoryPercentObserved": item.get("maxNodeMemoryPercentObserved"),
            "clusterSideArtifactsAvailable": item.get("clusterSideArtifactsAvailable"),
            "latencyDeltaPercentVsReference": round(percent_change(reference.get("meanResponseTimeMs") if reference else None, item.get("meanResponseTimeMs")), 2) if reference else None,
            "throughputDeltaPercentVsReference": round(percent_change(reference.get("throughputRps") if reference else None, item.get("throughputRps")), 2) if reference else None,
            "schedulerScenarioCategories": item.get("schedulerScenarioCategories"),
            "schedulerScenarioRiskLevel": item.get("schedulerScenarioRiskLevel"),
            "schedulerNegativeEvidenceCount": item.get("schedulerNegativeEvidenceCount"),
        })

    if scheduler_observed:
        add_finding(
            findings,
            "default_scheduler_decision_evidence_available",
            "Default-scheduler decision evidence is available for at least one C7 scenario.",
            "high",
            {
                "scenarioCountWithSchedulerEvidence": len(scheduler_observed),
                "scenarioIds": [item.get("scenarioId") for item in scheduler_observed],
                "placementClassifiedScenarioCount": len(placement_classified),
                "clusterSideArtifactScenarioCount": sum(1 for item in records if item.get("clusterSideArtifactsAvailable")),
            },
            "The diagnosis can interpret runtime pod-to-node assignments instead of relying only on benchmark latency and throughput metrics.",
            family="default-scheduler",
        )

    if negative_records:
        add_finding(
            findings,
            "default_scheduler_negative_placement_evidence",
            "At least one default-scheduler scenario produced warning or critical placement-classification evidence.",
            "high",
            {
                "scenarioCountWithNegativeEvidence": len(negative_records),
                "scenarios": [
                    {
                        "scenarioId": item.get("scenarioId"),
                        "riskLevel": item.get("schedulerScenarioRiskLevel"),
                        "categories": item.get("schedulerScenarioCategories"),
                        "negativeEvidenceCount": item.get("schedulerNegativeEvidenceCount"),
                    }
                    for item in negative_records
                ],
            },
            "Warning or critical placement categories provide direct evidence that formally valid default-scheduler placements may be suboptimal for the observed GenAI workload topology.",
            family="default-scheduler",
        )

    if measured:
        best_latency = min((item for item in measured if item.get("meanResponseTimeMs") is not None), key=lambda item: item["meanResponseTimeMs"], default=None)
        worst_latency = max((item for item in measured if item.get("meanResponseTimeMs") is not None), key=lambda item: item["meanResponseTimeMs"], default=None)
        add_finding(
            findings,
            "default_scheduler_benchmark_evidence_available",
            "Benchmark evidence is available for the default-scheduler baseline family.",
            "medium",
            {
                "measuredScenarioCount": len(measured),
                "referenceScenarioId": reference_id,
                "bestLatencyScenarioId": best_latency.get("scenarioId") if best_latency else None,
                "worstLatencyScenarioId": worst_latency.get("scenarioId") if worst_latency else None,
                "comparisons": comparisons,
            },
            "Performance evidence can be interpreted together with scheduler placement evidence to identify when multi-tenancy, latency and traffic differentiation correlate with degraded behavior.",
            family="default-scheduler",
        )

    if differentiated:
        add_finding(
            findings,
            "default_scheduler_traffic_differentiation_context",
            "Default-scheduler scenarios include differentiated tenant traffic profiles.",
            "medium",
            {
                "differentiatedScenarioCount": len(differentiated),
                "scenarioIds": [item.get("scenarioId") for item in differentiated],
            },
            "Differentiated traffic makes it possible to evaluate whether the default scheduler treats heterogeneous tenants as equivalent from a placement perspective.",
            family="default-scheduler",
        )

    if latency_enabled:
        latency_sensitive = [item for item in records if "latency_sensitive_split" in (item.get("schedulerScenarioCategories") or [])]
        add_finding(
            findings,
            "default_scheduler_latency_aware_context",
            "Default-scheduler scenarios include latency-aware runtime contexts.",
            "medium",
            {
                "latencyEnabledScenarioCount": len(latency_enabled),
                "latencySensitiveSplitScenarioIds": [item.get("scenarioId") for item in latency_sensitive],
            },
            "Latency-enabled scenarios are the primary context for identifying whether communicating LocalAI components are placed across network paths that may amplify response time.",
            family="default-scheduler",
        )

    if unsupported:
        add_finding(
            findings,
            "default_scheduler_unsupported_scenario_evidence",
            "At least one default-scheduler scenario produced unsupported evidence under current constraints.",
            "medium",
            {
                "unsupportedScenarioCount": len(unsupported),
                "scenarios": [
                    {
                        "scenarioId": item.get("scenarioId"),
                        "unsupportedSummary": item.get("unsupportedSummary"),
                    }
                    for item in unsupported
                ],
            },
            "Unsupported C7 scenarios should be retained as capacity, scheduling, readiness or measurement evidence rather than treated as ordinary script failures.",
            family="default-scheduler",
        )

    if not measured and not scheduler_observed and not unsupported:
        return build_family_judgment(
            "default-scheduler",
            "insufficient_evidence",
            "low",
            "The default-scheduler family does not yet contain measured, unsupported or scheduler-decision evidence.",
            "The C7 diagnosis profile is configured, but the campaign still needs runtime artifacts before the default scheduler can be assessed.",
            {"configuredScenarioCount": len(records), "referenceScenarioId": reference_id},
        )

    if negative_records:
        status = "suboptimal_placement_signal_available"
        title = "The default-scheduler family provides direct negative placement evidence."
        implication = "The captured scheduler decisions include warning or critical placement categories, supporting the claim that default Kubernetes placement can become inadequate for distributed GenAI tenant workloads."
        confidence = "high" if measured else "medium"
    elif measured and scheduler_observed:
        status = "baseline_evidence_available"
        title = "The default-scheduler family provides measurable placement-aware baseline evidence."
        implication = "Benchmark evidence and scheduler-decision evidence are available and can be used to compare simple and non-trivial C7 scenarios."
        confidence = "medium"
    elif scheduler_observed:
        status = "scheduler_evidence_available_without_benchmark_closure"
        title = "Scheduler-decision evidence is available, but benchmark evidence remains incomplete."
        implication = "The placement side of C7 is observable, but performance interpretation requires benchmark artifacts per tenant."
        confidence = "medium"
    else:
        status = "partial_evidence_available"
        title = "The default-scheduler family contains partial C7 evidence."
        implication = "The current artifacts can support preliminary diagnosis, but additional scheduler or benchmark evidence is required for stronger conclusions."
        confidence = "low"

    return build_family_judgment(
        "default-scheduler",
        status,
        confidence,
        title,
        implication,
        {
            "referenceScenarioId": reference_id,
            "configuredScenarioCount": len(records),
            "measuredScenarioCount": len(measured),
            "schedulerObservedScenarioCount": len(scheduler_observed),
            "placementClassifiedScenarioCount": len(placement_classified),
            "negativeEvidenceScenarioCount": len(negative_records),
            "unsupportedScenarioCount": len(unsupported),
            "differentiatedTrafficScenarioCount": len(differentiated),
            "latencyEnabledScenarioCount": len(latency_enabled),
            "clusterSideArtifactScenarioCount": sum(1 for item in records if item.get("clusterSideArtifactsAvailable")),
            "comparisons": comparisons,
        },
    )

def derive_cluster_pressure(profile, all_family_data, findings):
    cpu_values = []
    mem_values = []
    for family_data in all_family_data.values():
        for entry in family_data.values():
            summary = entry.get("summary") or {}
            cpu = summary.get("maxNodeCpuPercentObserved")
            mem = summary.get("maxNodeMemoryPercentObserved")
            if cpu is not None:
                cpu_values.append(cpu)
            if mem is not None:
                mem_values.append(mem)
    if cpu_values and max(cpu_values) >= profile["clusterCpuPressureThresholdPercent"]:
        add_finding(
            findings,
            "cluster_cpu_pressure",
            "Cluster-side collection shows episodes of elevated CPU pressure on cluster nodes.",
            "medium",
            {"maxNodeCpuPercentObserved": round(max(cpu_values), 2)},
            "CPU may be a concrete bottleneck component in at least part of the analyzed runs.",
        )
    if mem_values and max(mem_values) >= profile["clusterMemoryPressureThresholdPercent"]:
        add_finding(
            findings,
            "cluster_memory_pressure",
            "Cluster-side collection shows episodes of elevated memory pressure on cluster nodes.",
            "medium",
            {"maxNodeMemoryPercentObserved": round(max(mem_values), 2)},
            "Memory may contribute to the observed degradation in some configurations, especially with heavier models.",
        )


def main():
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    profile = load_json(Path(args.profile_config))
    output_json = Path(args.output_json)
    output_text = Path(args.output_text)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_text.parent.mkdir(parents=True, exist_ok=True)

    family_order = profile.get("familyOrder") or DEFAULT_FAMILY_ORDER
    families = family_order if args.family == "all" else [args.family]

    validation_summary_path, validation_summary_resolution, configured_validation_summary_path = resolve_validation_summary_path(repo_root, profile.get("validationSummaryRelativePath"))
    validation_summary = load_json(validation_summary_path) if validation_summary_path.exists() else None

    all_family_data = {}
    coverage = {}
    for family_name in families:
        family_data, family_coverage = discover_family_samples(repo_root, profile, family_name)
        all_family_data[family_name] = family_data
        coverage[family_name] = family_coverage

    findings = []
    if validation_summary is not None:
        add_finding(
            findings,
            "validation_baseline_ready",
            "Minimum end-to-end validation is available as a functional reliability baseline.",
            "high",
            {
                "success_rate_percent": validation_summary.get("success_rate_percent"),
                "mean_response_time_ms": validation_summary.get("mean_response_time_ms"),
                "throughput_rps": validation_summary.get("throughput_rps"),
                "units": {
                    "success_rate_percent": METRIC_UNITS["success_rate_percent"],
                    "mean_response_time_ms": METRIC_UNITS["mean_response_time_ms"],
                    "throughput_rps": METRIC_UNITS["throughput_rps"],
                },
            },
            "The benchmark pipeline starts from a verified functional baseline rather than from a purely theoretical setup.",
        )

    family_judgments = []
    if "baseline" in all_family_data:
        judgment = diagnose_baseline(profile, all_family_data["baseline"], findings)
        if judgment:
            family_judgments.append(judgment)
    if "worker-count" in all_family_data:
        judgment = diagnose_worker_count(profile, all_family_data["worker-count"], findings)
        if judgment:
            family_judgments.append(judgment)
    if "workload" in all_family_data:
        judgment = diagnose_workload(profile, all_family_data["workload"], findings)
        if judgment:
            family_judgments.append(judgment)
    if "models" in all_family_data:
        judgment = diagnose_models(profile, all_family_data["models"], findings)
        if judgment:
            family_judgments.append(judgment)
    if "placement" in all_family_data:
        judgment = diagnose_placement(profile, all_family_data["placement"], findings)
        if judgment:
            family_judgments.append(judgment)
    if "resource-variation" in all_family_data:
        judgment = diagnose_resource_variation(profile, all_family_data["resource-variation"], findings)
        if judgment:
            family_judgments.append(judgment)
    if "node-count-variation" in all_family_data:
        judgment = diagnose_node_count_variation(profile, all_family_data["node-count-variation"], findings)
        if judgment:
            family_judgments.append(judgment)
    if "placement-variation" in all_family_data:
        judgment = diagnose_placement_variation(profile, all_family_data["placement-variation"], findings)
        if judgment:
            family_judgments.append(judgment)
    if "latency-injection" in all_family_data:
        judgment = diagnose_latency_injection(profile, all_family_data["latency-injection"], findings)
        if judgment:
            family_judgments.append(judgment)
    if "multi-tenancy" in all_family_data:
        judgment = diagnose_multi_tenancy(profile, all_family_data["multi-tenancy"], findings)
        if judgment:
            family_judgments.append(judgment)
    if "default-scheduler" in all_family_data:
        judgment = diagnose_default_scheduler(profile, all_family_data["default-scheduler"], findings)
        if judgment:
            family_judgments.append(judgment)
    if "resource-aware-scheduler" in all_family_data:
        judgment = diagnose_resource_aware_scheduler(profile, all_family_data["resource-aware-scheduler"], findings)
        if judgment:
            family_judgments.append(judgment)
    if "network-aware-scheduler" in all_family_data:
        judgment = diagnose_network_aware_scheduler(profile, all_family_data["network-aware-scheduler"], findings)
        if judgment:
            family_judgments.append(judgment)
    family_judgments = [normalize_family_judgment(judgment) for judgment in family_judgments if judgment]
    derive_cluster_pressure(profile, all_family_data, findings)

    families_with_coverage = sum(1 for item in coverage.values() if item.get("scenariosObserved", 0) > 0)
    closure_status = "not_enough_data"
    if families_with_coverage >= profile["minimumFamiliesWithCoverageForClosure"] and len(findings) >= profile["minimumFindingsForClosure"]:
        closure_status = "preliminary_diagnosis_available"

    gaps = []
    if validation_summary is None:
        gaps.append("The configured validation summary was not found; the diagnosis relies on the available benchmark and cluster-side artifacts.")
    for family_name in families:
        family_cov = coverage[family_name]
        if family_cov.get("scenariosObserved", 0) == 0:
            gaps.append(f"The family '{family_name}' contains neither measurable runs nor structured unsupported-scenario evidence; diagnosis for this dimension remains incomplete.")
    if not any(
        entry.get("summary") and (
            entry["summary"].get("maxNodeCpuPercentObserved") is not None or entry["summary"].get("maxNodeMemoryPercentObserved") is not None
        )
        for family in all_family_data.values() for entry in family.values()
    ):
        gaps.append("Cluster-side artifacts are not available in the analyzed results yet; infrastructure bottleneck hypotheses are therefore less conclusive.")

    resource_aware_scheduler_pairwise = resource_aware_scheduler_pairwise_rows(all_family_data.get("resource-aware-scheduler") or {}) if "resource-aware-scheduler" in all_family_data else []
    network_aware_triplets = scheduler_network_aware_triplet_rows(all_family_data.get("network-aware-scheduler") or {}) if "network-aware-scheduler" in all_family_data else []

    diagnosis_payload = {
        "diagnosisProfile": profile,
        "diagnosis": {
            "diagnosisId": args.diagnosis_id,
            "createdAtUtc": datetime.now(timezone.utc).isoformat(),
            "familyScope": args.family,
            "closureStatus": closure_status,
        },
        "validationSummaryPath": str(validation_summary_path),
        "configuredValidationSummaryPath": str(configured_validation_summary_path) if configured_validation_summary_path is not None else str(validation_summary_path),
        "validationSummaryPathResolution": validation_summary_resolution,
        "validationSummaryAvailable": validation_summary is not None,
        "validationSummary": validation_summary,
        "metricUnits": METRIC_UNITS,
        "coverage": coverage,
        "familyData": all_family_data,
        "findings": findings,
        "familyJudgments": family_judgments,
        "schedulerModePairwise": resource_aware_scheduler_pairwise,
        "networkAwareSchedulerTriplets": network_aware_triplets,
        "gaps": gaps,
    }
    diagnosis_payload = normalize_artifact_payload_for_output(diagnosis_payload, output_json)
    output_json.write_text(json.dumps(diagnosis_payload, indent=2) + "\n", encoding="utf-8")

    lines = []
    lines.append("=============================================")
    lines.append(" Technical Diagnosis")
    lines.append("=============================================")
    lines.append(f"Diagnosis ID          : {args.diagnosis_id}")
    lines.append(f"Family scope          : {args.family}")
    lines.append(f"Closure status        : {closure_status}")
    lines.append(f"Validation summary    : {'available' if validation_summary is not None else 'missing'}")
    lines.append("")
    lines.append("Metric units")
    lines.append("------------")
    lines.append("- mean_response_time_ms, p50_response_time_ms, p95_response_time_ms, p99_response_time_ms: ms")
    lines.append("- throughput_rps: requests/s")
    lines.append("- success_rate_percent: %")
    lines.append("- maxNodeCpuPercentObserved: %")
    lines.append("- maxNodeMemoryPercentObserved: %")
    lines.append("- request_count: requests")
    lines.append("- failure_count: failures")
    lines.append("")
    lines.append("Coverage overview")
    lines.append("-----------------")
    for family_name in families:
        item = coverage[family_name]
        lines.append(f"- {family_name}: scenariosWithSamples={item.get('scenariosWithSamples', 0)}/{item.get('scenarioCount', 0)}, scenariosWithUnsupportedEvidence={item.get('scenariosWithUnsupportedEvidence', 0)}, scenariosObserved={item.get('scenariosObserved', 0)}, sampleCount={item.get('sampleCount', 0)}, unsupportedReplicaCount={item.get('unsupportedReplicaCount', 0)}, resultsRoot={item.get('resultsRoot')}")
    lines.append("")
    lines.append("Findings")
    lines.append("--------")
    if findings:
        for idx, finding in enumerate(findings, start=1):
            lines.append(f"{idx}. [{finding['confidence']}] {finding['title']}")
            lines.append(f"   Implication: {finding['implication']}")
            lines.append(f"   Evidence: {json.dumps(finding['evidence'], ensure_ascii=False)}")
    else:
        lines.append("- No sufficient evidence is available for an initial automated technical diagnosis.")
    lines.append("")
    lines.append("Family-level judgments")
    lines.append("---------------------")
    if family_judgments:
        for judgment in family_judgments:
            family = judgment.get("family", "unknown")
            status = judgment.get("status", "unknown")
            title = judgment.get("title", "Untitled family-level judgment")
            implication = judgment.get("implication", "No implication provided.")
            evidence = judgment.get("evidence", {})
            lines.append(f"- {family}: [{status}] {title}")
            lines.append(f"  Implication: {implication}")
            lines.append(f"  Evidence: {json.dumps(evidence, ensure_ascii=False)}")
    else:
        lines.append("- No family-level judgment is available.")
    if "default-scheduler" in all_family_data:
        lines.append("")
        lines.append("Default-scheduler placement evidence")
        lines.append("------------------------------------")
        for scenario_id, entry in sorted(all_family_data["default-scheduler"].items()):
            categories = entry.get("schedulerScenarioCategories") or []
            risk_level = entry.get("schedulerScenarioRiskLevel") or "not_collected"
            tenant_measurements = entry.get("tenantMeasurements") or []
            scheduler_path = entry.get("schedulerDecisionEvidencePath") or "not_collected"
            summary_path = entry.get("multiTenantSummaryPath") or "not_collected"
            lines.append(f"- {scenario_id}: risk={risk_level}, categories={categories}, tenantMeasurements={len(tenant_measurements)}, schedulerEvidence={scheduler_path}, multiTenantSummary={summary_path}")
    if "resource-aware-scheduler" in all_family_data:
        lines.append("")
        lines.append("Scheduler-comparison pairwise evidence")
        lines.append("--------------------------------------")
        for row in resource_aware_scheduler_pairwise:
            lines.append(
                f"- {row.get('logicalScenarioId')}: default={row.get('defaultVariantId') or row.get('defaultScenarioId')}, "
                f"loadAware={row.get('loadAwareVariantId') or row.get('loadAwareScenarioId')}, "
                f"meanDeltaPercent={row.get('meanLatencyDeltaPercent')}, "
                f"throughputDeltaPercent={row.get('throughputDeltaPercent')}, classification={row.get('classification')}"
            )
    lines.append("")
    lines.append("Per-family scenario averages")
    lines.append("--------------------------")
    for family_name in families:
        lines.append(f"Family: {family_name}")
        family_data = all_family_data[family_name]
        for scenario_id, entry in sorted(family_data.items()):
            summary = entry.get("summary")
            if not summary:
                unsupported_summary = entry.get("unsupportedSummary")
                if unsupported_summary:
                    lines.append(f"- {scenario_id}: unsupportedEvidence={unsupported_summary.get('unsupportedReplicaCount', 0)}, replicas={unsupported_summary.get('replicas', [])}, evidenceKinds={unsupported_summary.get('evidenceKinds', [])}")
                else:
                    lines.append(f"- {scenario_id}: no samples")
                continue
            metric_summary = summary.get("metrics", {})
            lines.append(
                f"- {scenario_id}: "
                f"samples={summary.get('sampleCount', 0)}, "
                f"mean_response_time_ms={metric_summary.get('mean_response_time_ms', {}).get('mean')} ms, "
                f"p50_response_time_ms={metric_summary.get('p50_response_time_ms', {}).get('mean')} ms, "
                f"p95_response_time_ms={metric_summary.get('p95_response_time_ms', {}).get('mean')} ms, "
                f"p99_response_time_ms={metric_summary.get('p99_response_time_ms', {}).get('mean')} ms, "
                f"throughput_rps={metric_summary.get('throughput_rps', {}).get('mean')} requests/s, "
                f"max_node_cpu_percent={summary.get('maxNodeCpuPercentObserved')} %, "
                f"max_node_memory_percent={summary.get('maxNodeMemoryPercentObserved')} %"
            )
        lines.append("")
    lines.append("Gaps")
    lines.append("----")
    if gaps:
        for gap in gaps:
            lines.append(f"- {gap}")
    else:
        lines.append("- No critical gap was detected for the preliminary diagnosis.")
    output_text.write_text(normalize_artifact_text_for_output("\n".join(lines) + "\n", output_text), encoding="utf-8")


if __name__ == "__main__":
    main()
