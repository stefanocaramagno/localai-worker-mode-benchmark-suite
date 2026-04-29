#!/usr/bin/env python
import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev

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

FAMILY_ORDER = ["worker-count", "workload", "models", "placement"]


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


def parse_args():
    parser = argparse.ArgumentParser(description="Generate a first technical diagnosis from pilot benchmark results.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--profile-config", required=True)
    parser.add_argument("--family", default="all", choices=["all", "worker-count", "workload", "models", "placement"])
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
    match = re.match(r"(?P<scenario>[^_]+)_run(?P<replica>[ABC])_unsupported$", path.stem)
    if not match:
        return None, "NA"
    return match.group("scenario"), match.group("replica")


def derive_unsupported_evidence_kinds(payload):
    evidence_kinds = set()

    raw_evidence = payload.get("evidence")
    if isinstance(raw_evidence, str) and raw_evidence.strip():
        evidence_kinds.add(raw_evidence.strip())
    elif isinstance(raw_evidence, list):
        for item in raw_evidence:
            if isinstance(item, str) and item.strip():
                evidence_kinds.add(item.strip())

    diagnostics = payload.get("diagnostics") or []
    for diagnostic in diagnostics:
        phase = (diagnostic.get("phase") or "").strip()
        reason = (diagnostic.get("reason") or "").strip()
        if phase == "Pending":
            evidence_kinds.add("pending_pod")
        if reason:
            evidence_kinds.add(reason.lower().replace(" ", "_"))
        for event in diagnostic.get("events") or []:
            event_text = str(event)
            lower_event = event_text.lower()
            if "[failedscheduling]" in lower_event or "failedscheduling" in lower_event:
                evidence_kinds.add("failed_scheduling")
            if "insufficient cpu" in lower_event:
                evidence_kinds.add("insufficient_cpu")
            if "insufficient memory" in lower_event:
                evidence_kinds.add("insufficient_memory")
            if "didn't match pod's node affinity/selector" in lower_event or "did not match pod's node affinity/selector" in lower_event:
                evidence_kinds.add("node_affinity_selector_mismatch")
            if "preemption is not helpful for scheduling" in lower_event:
                evidence_kinds.add("preemption_not_helpful")
            if "no preemption victims found for incoming pod" in lower_event:
                evidence_kinds.add("no_preemption_victims_found")

    return sorted(evidence_kinds)


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


def discover_family_samples(repo_root: Path, profile, family_name: str):
    scenario_root = repo_root / profile["scenarioConfigRoots"][family_name]
    results_root = repo_root / profile["pilotResultsRoots"][family_name]
    if not scenario_root.exists():
        return {}, {"resultsRoot": str(results_root), "scenarioRoot": str(scenario_root), "available": False}

    scenario_configs = {}
    for path in sorted(scenario_root.glob("*.json")):
        data = load_json(path)
        scenario_configs[data["scenarioId"]] = {"configPath": str(path), "data": data}

    family_samples = {}
    for scenario_id, scenario_info in scenario_configs.items():
        output_subdir = scenario_info["data"].get("outputSubdir")
        scenario_search_root = results_root / output_subdir if output_subdir else results_root
        stats_files = discover_measurement_stats(scenario_search_root)
        unsupported_files = discover_unsupported_reports(scenario_search_root)

        samples = []
        for stats_file in stats_files:
            row, source = find_target_row(
                stats_file,
                profile["requestTargetType"],
                profile["requestTargetName"],
                profile.get("fallbackToAggregated", False),
            )
            if row is None:
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
                "evidenceKinds": derive_unsupported_evidence_kinds(unsupported_payload),
                "timeoutSeconds": unsupported_payload.get("timeoutSeconds"),
                "model": unsupported_payload.get("model"),
            })

        family_samples[scenario_id] = {
            "scenario": scenario_info["data"],
            "searchRoot": str(scenario_search_root),
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
    return family_samples, coverage



def percent_change(reference, candidate):
    if reference in (None, 0) or candidate is None:
        return None
    return ((candidate - reference) / reference) * 100.0


def add_finding(findings, finding_id, title, confidence, evidence, implication):
    findings.append({
        "id": finding_id,
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
            "La famiglia worker-count non dispone ancora di evidenza misurata sufficiente per un giudizio comparativo robusto.",
            "Senza almeno due configurazioni misurate comparabili non è ancora possibile attribuire un segnale affidabile al numero di worker; gli scenari unsupported restano comunque tracciati come osservati sotto i vincoli correnti.",
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
        "Nel perimetro osservato il numero di worker non mostra ancora un effetto dominante sulla latenza media.",
        "Il worker-count è stato analizzato, ma il segnale misurato nel cluster attuale non è ancora abbastanza marcato per essere considerato driver principale delle performance.",
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
                "L'incremento iniziale dei worker produce un miglioramento apprezzabile della latenza media.",
                "medium",
                {
                    "W1_mean_response_time_ms": w1[2],
                    "W2_mean_response_time_ms": w2[2],
                    "W1_throughput_rps": w1[3],
                    "W2_throughput_rps": w2[3],
                    "throughputChangePercent": round(percent_change(w1[3], w2[3]), 2) if w1[3] is not None and w2[3] is not None else None,
                    "improvementPercent": round(improvement, 2),
                },
                "Il passaggio da uno a due worker sembra utile nel cluster corrente e suggerisce che una parte del collo di bottiglia iniziale sia mitigabile con parallelismo aggiuntivo.",
            )
            judgment = build_family_judgment(
                "worker-count",
                "strong_signal",
                "medium",
                "Il numero di worker mostra un segnale prestazionale apprezzabile già nel confronto iniziale tra configurazioni misurate.",
                "Nel cluster corrente il parallelismo aggiuntivo tra le prime configurazioni osservate produce un beneficio abbastanza chiaro da meritare una lettura diagnostica positiva.",
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
                "Nel confronto iniziale tra configurazioni misurate il numero di worker non produce un miglioramento abbastanza marcato.",
                "Il passaggio da W1 a W2 è stato osservato, ma il beneficio sulla latenza media resta sotto la soglia diagnostica configurata; eventuali scenari superiori unsupported limitano inoltre la valutazione oltre il perimetro misurato.",
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
                "Oltre la configurazione migliore osservata emergono rendimenti decrescenti o assenza di benefici netti.",
                "medium",
                {
                    "bestScenario": best[0],
                    "bestWorkerCount": best[1],
                    "bestMeanResponseTimeMs": best[2],
                    "throughputRpsByScenario": throughput_by_scenario,
                    "largerScenarioDeltasPercent": {item[0]: round(percent_change(best[2], item[2]), 2) for item in larger if percent_change(best[2], item[2]) is not None},
                },
                "Aumentare ulteriormente il numero di worker nel cluster attuale potrebbe introdurre overhead o comunque non ripagare in termini di latenza media.",
            )
            if judgment.get("status") != "strong_signal":
                judgment = build_family_judgment(
                    "worker-count",
                    "strong_signal",
                    "medium",
                    "La famiglia worker-count mostra un segnale interpretabile di rendimenti decrescenti oltre la configurazione migliore osservata.",
                    "Il numero di worker incide sul comportamento del sistema, ma oltre la configurazione migliore misurata i benefici aggiuntivi non risultano più netti nel cluster corrente.",
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
            "La famiglia workload non dispone ancora di estremi comparabili sufficienti per un giudizio completo.",
            "Senza una coppia di scenari di workload comparabili tra baseline e carico più intenso il segnale sulla saturazione resta incompleto.",
            {"availableScenarios": sorted([scenario_id for scenario_id, entry in family_data.items() if entry.get("summary")])},
        )
    if "mean_response_time_ms" not in wl1["metrics"] or "mean_response_time_ms" not in wl3["metrics"]:
        return build_family_judgment(
            "workload",
            "insufficient_evidence",
            "low",
            "La famiglia workload non contiene ancora metriche di latenza sufficienti per una lettura comparativa robusta.",
            "Le run esistono, ma l'assenza delle metriche chiave impedisce una valutazione affidabile del segnale di saturazione.",
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
            "Il workload più intenso aumenta sensibilmente la latenza, segnalando possibile saturazione del sistema.",
            "medium",
            {
                "WL1_mean_response_time_ms": wl1_mean,
                "WL3_mean_response_time_ms": wl3_mean,
                "latencyIncreasePercent": round(stress, 2),
                "WL1_throughput_rps": wl1_thr,
                "WL3_throughput_rps": wl3_thr,
                "throughputIncreasePercent": round(throughput_gain, 2) if throughput_gain is not None else None,
            },
            "Il cluster appare più fragile quando cresce la concorrenza; la sola crescita del carico non si traduce necessariamente in aumento proporzionale del throughput utile.",
        )
        return build_family_judgment(
            "workload",
            "strong_signal",
            "medium",
            "La famiglia workload mostra un segnale netto di deterioramento prestazionale all'aumentare del carico.",
            "Nel cluster corrente il workload è un driver rilevante della latenza e suggerisce una soglia di fragilità più evidente nelle configurazioni più spinte.",
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
        "Nel perimetro osservato la famiglia workload non mostra ancora un effetto abbastanza marcato da essere considerato dominante.",
        "Il carico è stato variato, ma la differenza di latenza tra gli scenari di riferimento resta sotto la soglia diagnostica configurata; servono evidenze più forti o workload più separati per una conclusione netta.",
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
            "La famiglia models non dispone ancora di gruppi di modelli comparabili sufficienti per una lettura robusta della penalità dimensionale.",
            "Senza almeno un gruppo piccolo e uno più grande osservati con metriche comparabili non è ancora possibile stimare in modo affidabile il peso della dimensione del modello.",
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
            "La dimensione del modello emerge come driver dominante della latenza media.",
            "high",
            {
                "smallModelMeanResponseTimeMs": round(small_mean, 4),
                "largeModelMeanResponseTimeMs": round(large_mean, 4),
                "smallModelMeanThroughputRps": round(small_throughput_mean, 4) if small_throughput_mean is not None else None,
                "largeModelMeanThroughputRps": round(large_throughput_mean, 4) if large_throughput_mean is not None else None,
                "throughputChangePercent": round(throughput_penalty, 2) if throughput_penalty is not None else None,
                "penaltyPercent": round(penalty, 2),
            },
            "Nel cluster CPU-only attuale il passaggio a modelli più grandi sembra incidere molto più della variazione fine di topologia o workload leggero.",
        )
        return build_family_judgment(
            "models",
            "strong_signal",
            "high",
            "La famiglia models mostra una penalità dimensionale netta e dominante sulla latenza media.",
            "Nel cluster corrente la scelta del modello incide fortemente sul comportamento del servizio e rappresenta uno dei driver principali della performance osservata.",
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
        "Nel perimetro osservato la famiglia models non mostra ancora una penalità dimensionale abbastanza marcata da essere considerata dominante.",
        "I modelli osservati sono stati confrontati, ma la differenza media resta sotto la soglia diagnostica configurata; servono evidenze più separate o modelli più contrastivi per una conclusione forte.",
        {
            "smallModelMeanResponseTimeMs": round(small_mean, 4),
            "largeModelMeanResponseTimeMs": round(large_mean, 4),
            "penaltyPercent": round(penalty, 2) if penalty is not None else None,
            "modelPenaltyThresholdPercent": profile["modelPenaltyThresholdPercent"],
        },
    )


def diagnose_placement(profile, family_data, findings):
    colocated = family_data.get("PL1", {}).get("summary")
    distributed = family_data.get("PL2", {}).get("summary")
    if not colocated or not distributed:
        return build_family_judgment(
            "placement",
            "insufficient_evidence",
            "low",
            "La famiglia placement non dispone ancora di configurazioni comparabili sufficienti per un giudizio robusto.",
            "Senza entrambe le configurazioni di placement misurate con metriche omogenee non è possibile stimare in modo affidabile l'effetto della collocazione dei worker.",
            {"availableScenarios": sorted([scenario_id for scenario_id, entry in family_data.items() if entry.get("summary")])},
        )
    if "mean_response_time_ms" not in colocated["metrics"] or "mean_response_time_ms" not in distributed["metrics"]:
        return build_family_judgment(
            "placement",
            "insufficient_evidence",
            "low",
            "La famiglia placement non contiene ancora metriche di latenza comparabili sufficienti per una lettura robusta.",
            "Le configurazioni di placement sono presenti, ma l'assenza delle metriche chiave impedisce una valutazione affidabile dell'effetto di collocazione.",
            {"availableScenarios": sorted([scenario_id for scenario_id, entry in family_data.items() if entry.get("summary")])},
        )

    # PL1 is the locked baseline placement defined by B0: co-located on sc-app-02.
    # PL2 is the experimental distributed two-node placement. Deltas must therefore
    # be computed as PL2 relative to PL1, not the other way around.
    colocated_mean = colocated["metrics"]["mean_response_time_ms"]["mean"]
    distributed_mean = distributed["metrics"]["mean_response_time_ms"]["mean"]
    colocated_throughput = metric_mean(colocated, "throughput_rps")
    distributed_throughput = metric_mean(distributed, "throughput_rps")
    throughput_diff = percent_change(colocated_throughput, distributed_throughput) if colocated_throughput is not None and distributed_throughput is not None else None
    diff = percent_change(colocated_mean, distributed_mean)

    evidence = {
        "referencePlacementScenario": "PL1",
        "candidatePlacementScenario": "PL2",
        "PL1_mean_response_time_ms": colocated_mean,
        "PL2_mean_response_time_ms": distributed_mean,
        "PL1_throughput_rps": colocated_throughput,
        "PL2_throughput_rps": distributed_throughput,
        "throughputDifferencePercentVsPL1": round(throughput_diff, 2) if throughput_diff is not None else None,
        "differencePercentVsPL1": round(diff, 2) if diff is not None else None,
    }

    if diff is not None and abs(diff) >= profile["placementDifferenceThresholdPercent"]:
        if distributed_mean > colocated_mean:
            title = "Il placement distribuito risulta più costoso del placement co-locato nel cluster corrente."
            implication = "L'overhead inter-nodo o di coordinamento potrebbe superare i benefici del bilanciamento, almeno nella topologia attuale a due worker node."
            judgment_title = "La famiglia placement mostra un segnale misurabile: nel cluster corrente il placement distribuito risulta penalizzante rispetto alla baseline co-located."
            judgment_implication = "La collocazione dei worker incide in modo leggibile sulle performance osservate e suggerisce che l'overhead inter-nodo non sia trascurabile nella topologia attuale."
        else:
            title = "Il placement distribuito mostra un vantaggio misurabile rispetto al placement co-locato."
            implication = "Distribuire i worker sui nodi disponibili potrebbe aiutare a ridurre contention locale e migliorare il comportamento del servizio."
            judgment_title = "La famiglia placement mostra un segnale misurabile: nel cluster corrente il placement distribuito offre un vantaggio leggibile rispetto alla baseline co-located."
            judgment_implication = "La collocazione dei worker incide in modo osservabile sulla latenza e suggerisce che la riduzione della contention locale superi l'overhead di coordinamento nel perimetro attuale."
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
        "Nel perimetro osservato la famiglia placement non mostra ancora un effetto abbastanza marcato da essere considerato dominante.",
        "Le configurazioni di placement sono state confrontate rispetto alla baseline co-located PL1, ma la differenza di latenza resta sotto la soglia diagnostica configurata; nel cluster corrente il placement non emerge ancora come driver principale delle performance.",
        {
            **evidence,
            "placementDifferenceThresholdPercent": profile["placementDifferenceThresholdPercent"],
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
            "La raccolta cluster-side mostra episodi di pressione CPU elevata sui nodi del cluster.",
            "medium",
            {"maxNodeCpuPercentObserved": round(max(cpu_values), 2)},
            "La CPU potrebbe essere una componente concreta del collo di bottiglia in almeno una parte delle run considerate.",
        )
    if mem_values and max(mem_values) >= profile["clusterMemoryPressureThresholdPercent"]:
        add_finding(
            findings,
            "cluster_memory_pressure",
            "La raccolta cluster-side mostra episodi di pressione memoria elevata sui nodi del cluster.",
            "medium",
            {"maxNodeMemoryPercentObserved": round(max(mem_values), 2)},
            "La memoria potrebbe contribuire al degrado osservato in alcune configurazioni, specialmente con modelli più pesanti.",
        )


def main():
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    profile = load_json(Path(args.profile_config))
    output_json = Path(args.output_json)
    output_text = Path(args.output_text)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_text.parent.mkdir(parents=True, exist_ok=True)

    families = FAMILY_ORDER if args.family == "all" else [args.family]

    validation_summary_path = repo_root / profile["validationSummaryRelativePath"]
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
            "La validazione minima end-to-end risulta disponibile come base di affidabilità funzionale.",
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
            "La pipeline di benchmark parte da una base funzionale verificata e non da un setup puramente teorico.",
        )

    family_judgments = []
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
    derive_cluster_pressure(profile, all_family_data, findings)

    families_with_coverage = sum(1 for item in coverage.values() if item.get("scenariosObserved", 0) > 0)
    closure_status = "not_enough_data"
    if families_with_coverage >= profile["minimumFamiliesWithCoverageForClosure"] and len(findings) >= profile["minimumFindingsForClosure"]:
        closure_status = "preliminary_diagnosis_available"

    gaps = []
    if validation_summary is None:
        gaps.append("La summary di validazione minima non è stata trovata: manca una baseline funzionale salvata in results/validation.")
    for family_name in families:
        family_cov = coverage[family_name]
        if family_cov.get("scenariosObserved", 0) == 0:
            gaps.append(f"La famiglia '{family_name}' non contiene né run misurabili né evidenza strutturata di scenari unsupported; la diagnosi per questa dimensione resta incompleta.")
    if not any(
        entry.get("summary") and (
            entry["summary"].get("maxNodeCpuPercentObserved") is not None or entry["summary"].get("maxNodeMemoryPercentObserved") is not None
        )
        for family in all_family_data.values() for entry in family.values()
    ):
        gaps.append("Gli artefatti cluster-side non risultano ancora presenti nei risultati analizzati; le ipotesi di collo di bottiglia infrastrutturale sono quindi meno forti.")

    diagnosis_payload = {
        "diagnosisProfile": profile,
        "diagnosis": {
            "diagnosisId": args.diagnosis_id,
            "createdAtUtc": datetime.now(timezone.utc).isoformat(),
            "familyScope": args.family,
            "closureStatus": closure_status,
        },
        "validationSummaryPath": str(validation_summary_path),
        "validationSummaryAvailable": validation_summary is not None,
        "validationSummary": validation_summary,
        "metricUnits": METRIC_UNITS,
        "coverage": coverage,
        "familyData": all_family_data,
        "findings": findings,
        "familyJudgments": family_judgments,
        "gaps": gaps,
    }
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
            lines.append(f"   Implicazione: {finding['implication']}")
            lines.append(f"   Evidenza: {json.dumps(finding['evidence'], ensure_ascii=False)}")
    else:
        lines.append("- Nessuna evidenza sufficiente per una prima diagnosi tecnica automatizzata.")
    lines.append("")
    lines.append("Family-level judgments")
    lines.append("---------------------")
    if family_judgments:
        for judgment in family_judgments:
            lines.append(f"- {judgment['family']}: [{judgment['status']}] {judgment['title']}")
            lines.append(f"  Implicazione: {judgment['implication']}")
            lines.append(f"  Evidenza: {json.dumps(judgment['evidence'], ensure_ascii=False)}")
    else:
        lines.append("- Nessun giudizio di famiglia disponibile.")
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
        lines.append("- Nessun gap critico rilevato per la diagnosi preliminare.")
    output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
