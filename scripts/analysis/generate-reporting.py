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
from typing import Any

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


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def discover_unsupported_reports(search_root: Path) -> list[Path]:
    if not search_root.exists():
        return []
    return sorted(search_root.rglob("*_unsupported.json"))


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
    result: dict[str, Any] = {"pods": [], "placementByPod": {}, "nodeCounts": defaultdict(int)}
    if not path.exists():
        return result
    with path.open("r", encoding="utf-8-sig", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("NAME"):
                continue
            parts = re.split(r"\s+", line)
            if len(parts) < 7:
                continue
            pod = {"name": parts[0], "ready": parts[1], "status": parts[2], "restarts": parts[3], "age": parts[4], "ip": parts[5], "node": parts[6]}
            result["pods"].append(pod)
            result["placementByPod"][parts[0]] = parts[6]
            result["nodeCounts"][parts[6]] += 1
    result["nodeCounts"] = dict(result["nodeCounts"])
    return result


def derive_unsupported_evidence_kinds(payload: dict[str, Any]) -> list[str]:
    evidence_kinds = set()
    raw_evidence = payload.get("evidence")
    if isinstance(raw_evidence, str) and raw_evidence.strip():
        evidence_kinds.add(raw_evidence.strip())
    elif isinstance(raw_evidence, list):
        for item in raw_evidence:
            if isinstance(item, str) and item.strip():
                evidence_kinds.add(item.strip())
    for diagnostic in payload.get("diagnostics") or []:
        phase = (diagnostic.get("phase") or "").strip()
        reason = (diagnostic.get("reason") or "").strip()
        if phase == "Pending":
            evidence_kinds.add("pending_pod")
        if reason:
            evidence_kinds.add(reason.lower().replace(" ", "_"))
        for event in diagnostic.get("events") or []:
            text = str(event).lower()
            if "failedscheduling" in text:
                evidence_kinds.add("failed_scheduling")
            if "insufficient cpu" in text:
                evidence_kinds.add("insufficient_cpu")
            if "insufficient memory" in text:
                evidence_kinds.add("insufficient_memory")
            if "node affinity/selector" in text:
                evidence_kinds.add("node_affinity_selector_mismatch")
            if "preemption is not helpful" in text:
                evidence_kinds.add("preemption_not_helpful")
            if "no preemption victims" in text:
                evidence_kinds.add("no_preemption_victims_found")
    return sorted(evidence_kinds)


def parse_scenario_and_replica_from_unsupported(path: Path) -> tuple[str | None, str]:
    match = re.match(r"(?P<scenario>[^_]+)_run(?P<replica>[A-Za-z0-9]+)_unsupported$", path.stem)
    if not match:
        return None, "NA"
    return match.group("scenario"), match.group("replica")


def scenario_label(family: str, scenario_id: str, scenario: dict[str, Any]) -> str:
    if family == "worker-count":
        return f"{scenario_id} ({scenario.get('workerCount', 'NA')} worker)"
    if family == "workload":
        return f"{scenario_id} ({scenario.get('users', 'NA')} users, spawn {scenario.get('spawnRate', 'NA')})"
    if family == "models":
        model = str(scenario.get("modelName", "model"))
        return f"{scenario_id} ({model})"
    if family == "placement":
        return f"{scenario_id} ({scenario.get('placementType', 'placement')})"
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
    for field in ["maxNodeCpuPercent", "maxNodeMemoryPercent", "maxPodCpuMillicores", "maxPodMemoryMiB", "totalPodCpuMillicores", "totalPodMemoryMiB"]:
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


def discover_family(repo_root: Path, profile: dict[str, Any], family: str, diagnosis_payload: dict[str, Any] | None) -> dict[str, Any]:
    scenario_root = repo_root / profile["scenarioConfigRoots"][family]
    results_root = repo_root / profile["pilotResultsRoots"][family]
    diagnosis_family = ((diagnosis_payload or {}).get("familyData") or {}).get(family) or {}
    scenario_configs = {}
    if scenario_root.exists():
        for path in sorted(scenario_root.glob("*.json"), key=lambda p: scenario_sort_key(p.stem)):
            payload = load_json(path)
            scenario_configs[payload["scenarioId"]] = {"configPath": path, "data": payload}
    for scenario_id, diag_entry in diagnosis_family.items():
        if scenario_id not in scenario_configs:
            scenario_configs[scenario_id] = {"configPath": None, "data": diag_entry.get("scenario") or {"scenarioId": scenario_id}}

    entries = {}
    for scenario_id, scenario_info in scenario_configs.items():
        scenario = scenario_info["data"]
        output_subdir = scenario.get("outputSubdir")
        search_root = results_root / output_subdir if output_subdir else results_root
        samples = []
        for stats_file in discover_measurement_stats(search_root):
            row, source = find_target_row(stats_file, profile["requestTargetType"], profile["requestTargetName"], profile.get("fallbackToAggregated", False))
            if row is None:
                continue
            prefix = str(stats_file)[:-len("_stats.csv")]
            top_nodes = parse_top_nodes(Path(prefix + "_cluster_post_top-nodes.txt"))
            top_pods = parse_top_pods(Path(prefix + "_cluster_post_top-pods.txt"))
            pods_wide = parse_pods_wide(Path(prefix + "_cluster_post_pods-wide.txt"))
            sample: dict[str, Any] = {
                "replica": parse_replica(stats_file.stem),
                "statsCsvPath": safe_rel(stats_file, repo_root),
                "rowSource": source,
                "clusterTopNodesPath": safe_rel(Path(prefix + "_cluster_post_top-nodes.txt"), repo_root),
                "clusterTopPodsPath": safe_rel(Path(prefix + "_cluster_post_top-pods.txt"), repo_root),
                "clusterPodsWidePath": safe_rel(Path(prefix + "_cluster_post_pods-wide.txt"), repo_root),
            }
            for metric_key, csv_field in CSV_FIELD_MAP.items():
                value = to_number(row.get(csv_field))
                sample[metric_key] = int(round(value)) if value is not None and metric_key in {"request_count", "failure_count"} else (round(value, 4) if value is not None else None)
            sample["maxNodeCpuPercent"] = top_nodes.get("maxNodeCpuPercent")
            sample["maxNodeMemoryPercent"] = top_nodes.get("maxNodeMemoryPercent")
            sample["maxPodCpuMillicores"] = top_pods.get("maxPodCpuMillicores")
            sample["maxPodMemoryMiB"] = top_pods.get("maxPodMemoryMiB")
            sample["totalPodCpuMillicores"] = top_pods.get("totalPodCpuMillicores")
            sample["totalPodMemoryMiB"] = top_pods.get("totalPodMemoryMiB")
            sample["nodeCounts"] = pods_wide.get("nodeCounts")
            samples.append(sample)

        unsupported = []
        for unsupported_file in discover_unsupported_reports(search_root):
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
                "evidenceKinds": derive_unsupported_evidence_kinds(payload),
                "timeoutSeconds": payload.get("timeoutSeconds"),
                "model": payload.get("model"),
            })

        diag_entry = diagnosis_family.get(scenario_id) or {}
        csv_summary = summarize_samples(samples)
        diagnosis_summary = diag_entry.get("summary")
        summary_source = "measurement_csv" if csv_summary else ("technical_diagnosis" if diagnosis_summary else "none")
        summary = csv_summary or diagnosis_summary
        unsupported_summary = None
        if unsupported:
            unsupported_summary = {"unsupportedReplicaCount": len(unsupported), "replicas": [item["replica"] for item in unsupported], "evidenceKinds": sorted({kind for item in unsupported for kind in item.get("evidenceKinds", [])}), "reasons": [item["reason"] for item in unsupported if item.get("reason")]}
        elif diag_entry.get("unsupportedSummary"):
            unsupported_summary = diag_entry.get("unsupportedSummary")
        status = "measured" if summary and (samples or summary.get("sampleCount")) else ("unsupported_under_current_constraints" if unsupported_summary else "missing")
        entries[scenario_id] = {
            "family": family,
            "scenarioId": scenario_id,
            "label": scenario_label(family, scenario_id, scenario),
            "scenario": scenario,
            "scenarioConfigPath": safe_rel(scenario_info["configPath"], repo_root) if scenario_info.get("configPath") else None,
            "searchRoot": safe_rel(search_root, repo_root),
            "status": status,
            "samples": samples,
            "summary": summary,
            "summarySource": summary_source,
            "diagnosisScenarioSummary": diagnosis_summary,
            "unsupportedReports": unsupported or diag_entry.get("unsupportedReports") or [],
            "unsupportedSummary": unsupported_summary,
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
    """Return a compact, report-friendly representation for scalar/list/dict values."""
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


def resolved_scenario_parameters(family: str, entry: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Resolve the effective experimental parameters of a scenario.

    Scenario files intentionally contain only the dimension varied by their sweep.
    This helper reconstructs the full configuration by inheriting all remaining
    dimensions from the official locked baseline, so sweep reports can state
    explicitly which values were used and not only which dimension changed.
    """
    scenario = entry.get("scenario") or {}
    workload = baseline.get("resolvedWorkload") or {}
    users = scenario.get("users", workload.get("users"))
    spawn_rate = scenario.get("spawnRate", workload.get("spawnRate"))
    run_time = scenario.get("runTime", workload.get("runTime"))
    parameters = {
        "model": scenario.get("modelName", baseline.get("resolvedModelName")),
        "model_scenario": scenario.get("scenarioId") if family == "models" else baseline.get("modelScenario"),
        "worker_count": scenario.get("workerCount", baseline.get("resolvedWorkerCount")),
        "worker_scenario": scenario.get("scenarioId") if family == "worker-count" else baseline.get("workerScenario"),
        "placement": scenario.get("placementType", baseline.get("resolvedPlacementType")),
        "placement_scenario": scenario.get("scenarioId") if family == "placement" else baseline.get("placementScenario"),
        "workload": f"users={users}, spawnRate={spawn_rate}, runTime={run_time}",
        "workload_scenario": scenario.get("scenarioId") if family == "workload" else baseline.get("workloadScenario"),
        "topology": scenario.get("topologyDir", baseline.get("topologyDir")),
        "server_manifest": scenario.get("serverManifest", baseline.get("serverManifest")),
        "prompt": baseline.get("prompt"),
        "temperature": baseline.get("temperature"),
        "request_timeout_seconds": baseline.get("requestTimeoutSeconds"),
        "output_subdir": scenario.get("outputSubdir"),
        "reference_baseline": scenario.get("referenceBaselineId", baseline.get("baselineId")),
    }
    if family == "worker-count":
        parameters["varied_value"] = parameters["worker_count"]
    elif family == "workload":
        parameters["varied_value"] = parameters["workload"]
    elif family == "models":
        parameters["varied_value"] = parameters["model"]
    elif family == "placement":
        parameters["varied_value"] = parameters["placement"]
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
        ["Scenario", "Status", f"Varied value ({varied_label})", "Model", "Workers", "Placement", "Workload", "Timeout (s)"],
        rows,
    )

def family_fixed_parameter_summary(family: str, baseline: dict[str, Any]) -> str:
    fixed_rows = []
    if family != "models":
        fixed_rows.append(["Model", baseline.get("resolvedModelName")])
    if family != "worker-count":
        fixed_rows.append(["Worker count", baseline.get("resolvedWorkerCount")])
    if family != "placement":
        fixed_rows.append(["Placement", baseline.get("resolvedPlacementType")])
    if family != "workload":
        fixed_rows.append(["Workload", baseline_workload_label(baseline)])
    fixed_rows += [
        ["Prompt", baseline.get("prompt")],
        ["Temperature", baseline.get("temperature")],
        ["Request timeout", f"{baseline.get('requestTimeoutSeconds')} s"],
    ]
    return md_table(["Fixed dimension", "Value inherited from baseline"], fixed_rows)


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
            row["max_node_cpu_percent_mean"] = (cluster.get("maxNodeCpuPercent") or {}).get("mean") or summary.get("maxNodeCpuPercentObserved")
            row["max_node_memory_percent_mean"] = (cluster.get("maxNodeMemoryPercent") or {}).get("mean") or summary.get("maxNodeMemoryPercentObserved")
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


def diagnosis_findings_by_family(diagnosis_payload: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not diagnosis_payload:
        return result
    for item in diagnosis_payload.get("familyJudgments") or []:
        result[item.get("family", "general")].append({"kind": "family_judgment", **item})
    for item in diagnosis_payload.get("findings") or []:
        family = item.get("family") or item.get("id", "general").split("_")[0]
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
    """Build the compact, advisor-facing measurement table."""
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
    """Build the detailed metric table aligned with technical diagnosis."""
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
        ],
        table_rows,
    )


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
    display_name = profile.get("familyDisplayNames", {}).get(family, family)
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
        f"{subheading} Fixed baseline parameters",
        "",
        family_fixed_parameter_summary(family, baseline),
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
            build_svg_bar_chart(f"{profile.get('familyDisplayNames', {}).get(family, family)} - {chart_def['title']}", values, chart_def.get("unit", ""), chart_file)
            chart_paths[family].append({"metric": metric, "path": chart_file.relative_to(output_dir).as_posix(), "title": chart_def["title"]})
    return dict(chart_paths)


def build_global_report(
    profile: dict[str, Any],
    baseline: dict[str, Any],
    family_data: dict[str, dict[str, Any]],
    diagnosis_ref: dict[str, Any] | None,
    chart_paths: dict[str, list[dict[str, str]]],
    sweep_report_paths: dict[str, dict[str, str]],
) -> str:
    diagnosis_payload = diagnosis_ref["payload"] if diagnosis_ref else None
    findings_by_family = diagnosis_findings_by_family(diagnosis_payload)
    lines = ["# Consolidated Pilot Reporting and Visualization", "", f"**Reporting ID:** `{profile['_runtimeReportingId']}`", f"**Generated at UTC:** `{profile['_runtimeCreatedAtUtc']}`", ""]
    lines += ["## Purpose", "", "This report provides advisor-facing visual summaries of the consolidated LocalAI worker-mode pilot campaigns. It is generated after technical diagnosis and before completion-gate evaluation, so that the benchmark cycle is not considered closed until its results are readable and inspectable.", "", "The report combines **measurement CSV data** for quantitative charts with **technical diagnosis outputs** for interpretation, unsupported-scenario evidence and family-level judgments.", ""]
    lines += ["## Baseline context", "", md_table(["Dimension", "Baseline value"], [["Baseline ID", baseline.get("baselineId")], ["Model", baseline.get("resolvedModelName")], ["Worker count", baseline.get("resolvedWorkerCount")], ["Placement", baseline.get("resolvedPlacementType")], ["Workload", f"users={baseline.get('resolvedWorkload', {}).get('users')}, spawnRate={baseline.get('resolvedWorkload', {}).get('spawnRate')}, runTime={baseline.get('resolvedWorkload', {}).get('runTime')}"], ["Prompt", baseline.get("prompt")], ["Request timeout", f"{baseline.get('requestTimeoutSeconds')} s"]]), ""]
    lines += ["## Data sources", "", md_table(["Layer", "Primary use", "Source"], [["Measurement CSV", "Quantitative charts and scenario summary metrics", "`results/pilot/consolidated/**/_stats.csv`"], ["Technical diagnosis", "Interpretation, family judgments, findings, unsupported-scenario context", f"`{diagnosis_ref['path']}`" if diagnosis_ref else "not available"], ["Scenario configuration", "Fixed/varied dimensions and scenario labels", "`config/scenarios/**`"], ["Cluster-side artifacts", "CPU/memory snapshots and placement evidence", "`*_cluster_post_*` files"]]), ""]

    lines += ["## Sweep-specific reports", "", "The global report below provides the advisor-facing overview. Each sweep also has a dedicated report for focused inspection of one varied dimension.", ""]
    sweep_rows = []
    for family in profile["familyOrder"]:
        display_name = profile.get("familyDisplayNames", {}).get(family, family)
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
    display_name = profile.get("familyDisplayNames", {}).get(family, family)
    lines = [
        f"# {display_name} Report",
        "",
        f"**Reporting ID:** `{profile['_runtimeReportingId']}`",
        f"**Generated at UTC:** `{profile['_runtimeCreatedAtUtc']}`",
        "",
        "[Back to consolidated reporting index](../../index.html)",
        "",
        "## Scope",
        "",
        "This sweep-specific report isolates one benchmark family so that the varied dimension, fixed dimensions, measured values, unsupported evidence and diagnosis-based reading can be inspected without navigating the full consolidated report.",
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
            flush_ul(); out.append(f"<p>{render_inline(line)}</p>")
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
    """Resolve the logical reporting identifier of the current report.

    The current report is considered archiveable only if its manifest exists and
    exposes the reporting identifier generated when the report was created. The
    manifest, rather than the filesystem timestamp, is the authoritative source
    because it records the logical generation time and the diagnosis context used
    by the report.
    """
    manifest_path = output_dir / profile.get("manifestName", "reporting-manifest.json")
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Current reporting manifest not found: {manifest_path}. "
            "Run the reporting phase first, then archive the current report."
        )
    manifest = load_json(manifest_path)
    reporting = manifest.get("reporting") or {}
    reporting_id = reporting.get("reportingId") or manifest.get("reportingId")
    if not reporting_id:
        created_at = reporting.get("createdAtUtc") or manifest.get("createdAtUtc")
        if created_at:
            try:
                dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).astimezone(timezone.utc)
                reporting_id = "analysis_reporting_all_NA_" + dt.strftime("%Y%m%dT%H%M%SZ")
            except Exception:
                reporting_id = None
    if not reporting_id:
        raise ValueError(
            f"Unable to resolve reportingId from current reporting manifest: {manifest_path}. "
            "The report cannot be archived safely without a logical identifier."
        )
    return str(reporting_id)


def copy_reporting_archive(output_dir: Path, archive_dir: Path, profile: dict[str, Any], *, force: bool = False) -> list[str]:
    """Copy the current reporting artifacts to an archive directory.

    The stable reporting directory remains the canonical current advisor-facing
    report. Archiving copies only managed reporting artifacts, avoiding recursive
    copies of any existing archive history.
    """
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
    if not reporting_id:
        reporting_id = "analysis_reporting_all_NA_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.reporting_id = reporting_id
    profile["_runtimeReportingId"] = reporting_id
    profile["_runtimeCreatedAtUtc"] = datetime.now(timezone.utc).isoformat()

    baseline = load_json(repo_root / profile["baselineConfig"])
    diagnosis_ref = discover_latest_diagnosis(repo_root, repo_root / profile.get("technicalDiagnosisRoot", "results/diagnosis"), "all")
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
        family_markdown_path.write_text(family_markdown, encoding="utf-8")
        family_html_path.write_text(markdown_to_basic_html_page(family_markdown, f"{profile.get('familyDisplayNames', {}).get(family, family)} Reporting"), encoding="utf-8")
        sweep_report_paths[family] = {
            "markdownReport": family_markdown_path.relative_to(output_dir).as_posix(),
            "htmlReport": family_html_path.relative_to(output_dir).as_posix(),
        }

    global_markdown = build_global_report(profile, baseline, family_data, diagnosis_ref, chart_paths, sweep_report_paths)
    markdown_path = output_dir / profile.get("reportMarkdownName", "report.md")
    html_path = output_dir / profile.get("reportHtmlName", "index.html")
    manifest_path = output_dir / profile.get("manifestName", "reporting-manifest.json")
    markdown_path.write_text(global_markdown, encoding="utf-8")
    html_path.write_text(markdown_to_basic_html_page(global_markdown, "Consolidated Pilot Reporting"), encoding="utf-8")

    archive_dir = output_dir / profile.get("archiveDirectoryName", "archive") / args.reporting_id if args.archive else None
    manifest = {
        "reportingProfile": {"profileId": profile.get("profileId"), "profileFile": safe_rel(profile_path, repo_root), "description": profile.get("description")},
        "reporting": {"reportingId": args.reporting_id, "createdAtUtc": profile["_runtimeCreatedAtUtc"], "outputDirectory": safe_rel(output_dir, repo_root), "familyScope": "all", "pipelinePosition": "after_technical_diagnosis_before_completion_gate"},
        "baseline": baseline,
        "latestAllFamilyDiagnosis": diagnosis_ref["path"] if diagnosis_ref else None,
        "dataSourcePolicy": {"quantitativeCharts": "measurement_csv_when_available", "interpretation": "latest_technical_diagnosis_when_available", "scenarioMetadata": "scenario_configuration_files"},
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
