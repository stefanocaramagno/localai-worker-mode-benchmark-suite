#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


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



REQUIRED_METRIC_KEY = "mean_response_time_ms"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_artifact_payload_for_output(payload, path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = normalize_artifact_text_for_output(content, path)
    path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate completion gates for historical and provider-backed LocalAI benchmark cycles.")
    parser.add_argument("--profile-config", required=True, help="Completion gate profile path.")
    parser.add_argument("--cycle-config", default="", help="Optional experimental cycle profile path. Provider-backed profiles can also declare cycleConfigPath.")
    parser.add_argument("--repo-root", default="", help="Repository root. If omitted, it is inferred from the profile path.")
    parser.add_argument("--diagnosis-json", default="", help="Optional technical diagnosis JSON. If omitted, the profile-defined roots are searched.")
    parser.add_argument("--output-json", required=True, help="Output JSON manifest path.")
    parser.add_argument("--output-text", required=True, help="Output text summary path.")
    parser.add_argument("--evaluation-id", required=True, help="Completion gate evaluation identifier.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve inputs and write a dry-run manifest without failing on missing runtime artifacts.")
    return parser.parse_args()


def infer_repo_root(profile_config_path: Path, explicit_repo_root: str = "") -> Path:
    if explicit_repo_root:
        return Path(explicit_repo_root).resolve()
    profile_config_path = profile_config_path.resolve()
    parts = profile_config_path.parts
    if "config" in parts:
        idx = len(parts) - 1 - list(reversed(parts)).index("config")
        return Path(*parts[:idx]).resolve()
    return Path.cwd().resolve()


def repo_path(repo_root: Path, value: Optional[str]) -> Optional[Path]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else repo_root / path


def safe_rel(path: Optional[Path], repo_root: Path) -> Optional[str]:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except Exception:
        return str(path)


def get_nested(payload: Any, dotted_path: str, default: Any = None) -> Any:
    current = payload
    for part in dotted_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def add_gate(gates: List[Dict[str, Any]], gate_id: str, title: str, passed: bool, evidence: Dict[str, Any], implication: str, category: str = "general") -> None:
    gates.append({
        "id": gate_id,
        "category": category,
        "title": title,
        "passed": bool(passed),
        "evidence": evidence,
        "implication": implication,
    })


def count_unsupported_replicas(entry: Dict[str, Any]) -> int:
    unsupported_summary = entry.get("unsupportedSummary") or {}
    if unsupported_summary:
        count = unsupported_summary.get("unsupportedReplicaCount")
        if count is not None:
            return int(count)
    unsupported_reports = entry.get("unsupportedReports") or []
    return len(unsupported_reports)


def scenario_is_accepted_unsupported(unsupported_count: int, minimum_unsupported_replicas: int) -> bool:
    return unsupported_count >= int(minimum_unsupported_replicas)


def evaluate_family_coverage(profile: Dict[str, Any], diagnosis_payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    coverage = diagnosis_payload.get("coverage", {})
    family_data = diagnosis_payload.get("familyData", {})
    required_families = profile.get("requiredFamilies", [])
    min_replicas = int(profile.get("minimumReplicasPerScenario", 1))
    strict_coverage = bool(profile.get("strictScenarioCoverage", False))
    accept_unsupported_as_covered = bool(profile.get("acceptUnsupportedScenariosAsCovered", False))
    minimum_unsupported_replicas = int(profile.get("minimumUnsupportedReplicasPerScenario", min_replicas))
    minimum_measured_by_family = profile.get("minimumMeasuredScenariosByFamily") or {}
    default_minimum_measured = profile.get("minimumMeasuredScenarios")

    per_family: Dict[str, Any] = {}
    all_passed = True
    for family_name in required_families:
        family_cov = coverage.get(family_name, {})
        family_entries = family_data.get(family_name, {})
        scenario_count = int(family_cov.get("scenarioCount", 0) or 0)
        scenarios_with_samples = int(family_cov.get("scenariosWithSamples", 0) or 0)
        sample_count = int(family_cov.get("sampleCount", 0) or 0)
        minimum_expected_samples = scenario_count * min_replicas
        scenarios_satisfying_replica_gate = []
        scenarios_satisfying_unsupported_gate = []
        scenarios_failing_replica_gate = []
        total_unsupported_replica_count = 0
        scenarios_with_accepted_unsupported = 0

        for scenario_id, entry in sorted(family_entries.items()):
            summary = entry.get("summary") or {}
            observed_samples = int(summary.get("sampleCount", 0) or 0)
            unsupported_replica_count = count_unsupported_replicas(entry)
            total_unsupported_replica_count += unsupported_replica_count
            if observed_samples >= min_replicas:
                scenarios_satisfying_replica_gate.append(scenario_id)
                continue
            accepted_unsupported = accept_unsupported_as_covered and scenario_is_accepted_unsupported(unsupported_replica_count, minimum_unsupported_replicas)
            if accepted_unsupported:
                scenarios_satisfying_unsupported_gate.append({
                    "scenarioId": scenario_id,
                    "unsupportedReplicaCount": unsupported_replica_count,
                    "requiredUnsupportedReplicas": minimum_unsupported_replicas,
                })
                scenarios_with_accepted_unsupported += 1
            else:
                scenarios_failing_replica_gate.append({
                    "scenarioId": scenario_id,
                    "observedSamples": observed_samples,
                    "unsupportedReplicaCount": unsupported_replica_count,
                    "requiredSamples": min_replicas,
                })

        effective_evidence_count = sample_count + total_unsupported_replica_count
        minimum_expected_evidence = scenario_count * min_replicas
        required_measured_scenarios = int(minimum_measured_by_family.get(family_name, default_minimum_measured if default_minimum_measured is not None else 0) or 0)
        measured_scenario_gate_passed = scenarios_with_samples >= required_measured_scenarios
        family_passed = scenario_count > 0 and effective_evidence_count >= minimum_expected_evidence and measured_scenario_gate_passed
        if strict_coverage:
            family_passed = family_passed and (scenarios_with_samples + scenarios_with_accepted_unsupported) == scenario_count and len(scenarios_failing_replica_gate) == 0
        else:
            family_passed = family_passed and (len(scenarios_satisfying_replica_gate) + scenarios_with_accepted_unsupported) > 0
        per_family[family_name] = {
            "scenarioCount": scenario_count,
            "scenariosWithSamples": scenarios_with_samples,
            "scenariosWithAcceptedUnsupported": scenarios_with_accepted_unsupported,
            "sampleCount": sample_count,
            "unsupportedReplicaCount": total_unsupported_replica_count,
            "effectiveEvidenceCount": effective_evidence_count,
            "minimumExpectedSamples": minimum_expected_samples,
            "minimumExpectedEvidence": minimum_expected_evidence,
            "minimumMeasuredScenariosRequired": required_measured_scenarios,
            "measuredScenarioGatePassed": measured_scenario_gate_passed,
            "acceptUnsupportedScenariosAsCovered": accept_unsupported_as_covered,
            "minimumUnsupportedReplicasPerScenario": minimum_unsupported_replicas,
            "scenariosSatisfyingReplicaGate": scenarios_satisfying_replica_gate,
            "scenariosSatisfyingUnsupportedGate": scenarios_satisfying_unsupported_gate,
            "scenariosFailingReplicaGate": scenarios_failing_replica_gate,
            "passed": family_passed,
        }
        all_passed = all_passed and family_passed
    return all_passed, per_family


def evaluate_repeatability(profile: Dict[str, Any], diagnosis_payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    family_data = diagnosis_payload.get("familyData", {})
    required_families = profile.get("requiredFamilies", [])
    min_replicas = int(profile.get("minimumReplicasPerScenario", 1))
    max_cv = float(profile.get("maximumMeanResponseTimeCvPercent", 1000000))
    per_family: Dict[str, Any] = {}
    all_passed = True
    for family_name in required_families:
        family_entries = family_data.get(family_name, {})
        qualifying_scenarios = []
        rejected_scenarios = []
        for scenario_id, entry in sorted(family_entries.items()):
            summary = entry.get("summary") or {}
            metrics = summary.get("metrics") or {}
            metric_summary = metrics.get(REQUIRED_METRIC_KEY) or {}
            observed_samples = int(summary.get("sampleCount", 0) or 0)
            cv = metric_summary.get("coefficientOfVariationPercent")
            if observed_samples >= min_replicas and cv is not None and float(cv) <= max_cv:
                qualifying_scenarios.append({"scenarioId": scenario_id, "sampleCount": observed_samples, "cvPercent": cv})
            else:
                rejected_scenarios.append({"scenarioId": scenario_id, "sampleCount": observed_samples, "cvPercent": cv})
        passed = len(qualifying_scenarios) > 0
        per_family[family_name] = {"passed": passed, "qualifyingScenarios": qualifying_scenarios, "rejectedScenarios": rejected_scenarios}
        all_passed = all_passed and passed
    return all_passed, per_family


def evaluate_findings(profile: Dict[str, Any], diagnosis_payload: Dict[str, Any]) -> Dict[str, Any]:
    findings = diagnosis_payload.get("findings", [])
    finding_ids = {item.get("id") for item in findings}
    min_findings = int(profile.get("minimumFindings", 0))
    finding_count_gate = len(findings) >= min_findings
    required_groups = profile.get("requiredFindingGroups", {})
    satisfied_groups = {}
    for group_name, expected_ids in required_groups.items():
        matched = [finding_id for finding_id in expected_ids if finding_id in finding_ids]
        satisfied_groups[group_name] = {"matchedFindingIds": matched, "passed": len(matched) > 0}
    satisfied_group_count = sum(1 for item in satisfied_groups.values() if item["passed"])
    min_groups = int(profile.get("minimumFindingGroupsSatisfied", 0))
    group_gate = satisfied_group_count >= min_groups
    return {
        "findingCount": len(findings),
        "minimumFindingsRequired": min_findings,
        "findingCountGatePassed": finding_count_gate,
        "satisfiedGroupCount": satisfied_group_count,
        "minimumFindingGroupsSatisfied": min_groups,
        "groupGatePassed": group_gate,
        "groups": satisfied_groups,
    }


def evaluate_cluster_side(profile: Dict[str, Any], diagnosis_payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    if not profile.get("requireClusterSideEvidence", False):
        return True, {"required": False, "gapPatterns": [], "matchedGaps": []}
    gap_patterns = [str(item).lower() for item in profile.get("clusterSideGapPatterns", [])]
    gaps = diagnosis_payload.get("gaps", [])
    matched = []
    for gap in gaps:
        gap_text = str(gap).lower()
        if any(pattern in gap_text for pattern in gap_patterns):
            matched.append(gap)
    return len(matched) == 0, {"required": True, "gapPatterns": gap_patterns, "matchedGaps": matched}


def evaluate_legacy_reporting(profile: Dict[str, Any], repo_root: Path) -> Tuple[bool, Dict[str, Any]]:
    reporting_profile = profile.get("requiredReportingArtifacts") or {}
    if not reporting_profile.get("enabled", False):
        return True, {"required": False, "reason": "Reporting artifact gate disabled in completion profile."}
    reporting_root = repo_path(repo_root, reporting_profile.get("reportingRoot", "results/experimental-cycles/C0/reporting")) or (repo_root / "results/experimental-cycles/C0/reporting")
    manifest_name = reporting_profile.get("manifestName", "reporting-manifest.json")
    markdown_name = reporting_profile.get("markdownReportName", "report.md")
    html_name = reporting_profile.get("htmlReportName", "index.html")
    summary_name = reporting_profile.get("scenarioSummaryCsvName", "scenario-summary.csv")
    charts_dir_name = reporting_profile.get("chartsDirectoryName", "charts")
    sweeps_dir_name = reporting_profile.get("sweepsDirectoryName", "sweeps")
    required_files = [reporting_root / manifest_name, reporting_root / markdown_name, reporting_root / html_name, reporting_root / summary_name]
    missing_files = [str(path) for path in required_files if not path.is_file()]
    required_chart_families = reporting_profile.get("requiredChartFamilies", [])
    required_chart_metrics = reporting_profile.get("requiredChartMetrics", [])
    missing_charts = []
    chart_evidence = []
    for family in required_chart_families:
        family_dir = reporting_root / charts_dir_name / family
        for metric in required_chart_metrics:
            expected_chart = family_dir / f"{metric}.svg"
            if expected_chart.is_file():
                chart_evidence.append({"family": family, "metric": metric, "path": str(expected_chart)})
            else:
                missing_charts.append({"family": family, "metric": metric, "path": str(expected_chart)})
    required_sweep_reports = reporting_profile.get("requiredSweepReports", required_chart_families)
    missing_sweep_reports = []
    sweep_report_evidence = []
    for family in required_sweep_reports:
        sweep_dir = reporting_root / sweeps_dir_name / family
        expected_markdown = sweep_dir / markdown_name
        expected_html = sweep_dir / html_name
        family_missing = []
        if not expected_markdown.is_file():
            family_missing.append(str(expected_markdown))
        if not expected_html.is_file():
            family_missing.append(str(expected_html))
        if family_missing:
            missing_sweep_reports.append({"family": family, "missingFiles": family_missing})
        else:
            sweep_report_evidence.append({"family": family, "markdownReport": str(expected_markdown), "htmlReport": str(expected_html)})
    manifest_payload = None
    manifest_path = reporting_root / manifest_name
    if manifest_path.is_file():
        try:
            manifest_payload = load_json(manifest_path)
        except Exception as exc:
            missing_files.append(f"{manifest_path} (invalid JSON: {exc})")
    passed = len(missing_files) == 0 and len(missing_charts) == 0 and len(missing_sweep_reports) == 0
    return passed, {
        "required": True,
        "reportingRoot": str(reporting_root),
        "requiredFiles": [str(path) for path in required_files],
        "missingFiles": missing_files,
        "requiredChartFamilies": required_chart_families,
        "requiredChartMetrics": required_chart_metrics,
        "missingCharts": missing_charts,
        "chartEvidenceCount": len(chart_evidence),
        "requiredSweepReports": required_sweep_reports,
        "missingSweepReports": missing_sweep_reports,
        "sweepReportEvidenceCount": len(sweep_report_evidence),
        "reportingId": get_nested(manifest_payload, "reporting.reportingId") if isinstance(manifest_payload, dict) else None,
        "createdAtUtc": get_nested(manifest_payload, "reporting.createdAtUtc") if isinstance(manifest_payload, dict) else None,
    }


def evaluate_legacy(profile: Dict[str, Any], repo_root: Path, args: argparse.Namespace) -> Dict[str, Any]:
    diagnosis_path = Path(args.diagnosis_json).resolve()
    diagnosis_payload = load_json(diagnosis_path)
    diagnosis_meta = diagnosis_payload.get("diagnosis", {})
    diagnosis_status = diagnosis_meta.get("closureStatus")
    accepted_statuses = profile.get("acceptedDiagnosisClosureStatuses", [])
    diagnosis_gate_passed = diagnosis_status in accepted_statuses
    validation_gate_passed = bool(diagnosis_payload.get("validationSummaryAvailable"))
    families_gate_passed, family_coverage = evaluate_family_coverage(profile, diagnosis_payload)
    repeatability_gate_passed, repeatability = evaluate_repeatability(profile, diagnosis_payload)
    findings_eval = evaluate_findings(profile, diagnosis_payload)
    cluster_gate_passed, cluster_eval = evaluate_cluster_side(profile, diagnosis_payload)
    reporting_gate_passed, reporting_eval = evaluate_legacy_reporting(profile, repo_root)
    gates: List[Dict[str, Any]] = []
    add_gate(gates, "validation_baseline_available", "Minimum validation baseline is available.", validation_gate_passed, {"validationSummaryAvailable": diagnosis_payload.get("validationSummaryAvailable"), "validationSummaryPath": diagnosis_payload.get("validationSummaryPath")}, "The characterization cycle must rely on saved functional validation evidence, not only pilot benchmarks.", "validation")
    add_gate(gates, "diagnosis_status_accepted", "Technical diagnosis closure status is accepted.", diagnosis_gate_passed, {"diagnosisClosureStatus": diagnosis_status, "acceptedDiagnosisClosureStatuses": accepted_statuses}, "The cycle can be closed only after structured technical diagnosis is available.", "diagnosis")
    add_gate(gates, "family_coverage_complete", "Required benchmark families have sufficient coverage.", families_gate_passed, family_coverage, "Closure requires explicit coverage of the configured benchmark families.", "benchmark")
    add_gate(gates, "repeatability_signal_present", "Each required family includes at least one scenario with acceptable repeatability.", repeatability_gate_passed, repeatability, "Completion requires repeatable evidence, not only isolated samples.", "benchmark")
    add_gate(gates, "minimum_findings_and_groups", "Diagnosis contains enough findings and interpretive groups.", findings_eval["findingCountGatePassed"] and findings_eval["groupGatePassed"], findings_eval, "Completion requires a non-trivial technical interpretation of the benchmark results.", "diagnosis")
    add_gate(gates, "cluster_side_evidence_present", "Cluster-side evidence is not missing from the evaluated diagnosis.", cluster_gate_passed, cluster_eval, "Infrastructure evidence must accompany client-side benchmark results.", "observability")
    add_gate(gates, "reporting_artifacts_available", "Reporting artifacts and charts are available.", reporting_gate_passed, reporting_eval, "Formal closure requires readable reports, tables and visualizations.", "reporting")
    return build_payload(profile, repo_root, args, gates, diagnosis_reference={"diagnosisJson": str(diagnosis_path), "diagnosisId": diagnosis_meta.get("diagnosisId"), "diagnosisClosureStatus": diagnosis_status, "familyScope": diagnosis_meta.get("familyScope")}, reporting_reference=reporting_eval, source_gaps=diagnosis_payload.get("gaps", []), provider_aware=False)


def load_optional(path: Optional[Path]) -> Tuple[Optional[Any], Optional[str]]:
    if path is None:
        return None, "path_not_declared"
    if not path.exists():
        return None, "missing"
    try:
        return load_json(path), None
    except Exception as exc:
        return None, f"invalid_json: {exc}"


def latest_diagnosis_from_roots(repo_root: Path, roots: Iterable[str], family_scope: str = "all") -> Tuple[Optional[Path], Optional[Dict[str, Any]], List[str]]:
    candidates: List[Tuple[float, Path, Dict[str, Any]]] = []
    errors: List[str] = []
    for root_value in roots:
        root_path = repo_path(repo_root, root_value)
        if root_path is None:
            continue
        if not root_path.exists():
            errors.append(f"diagnosis_root_missing:{safe_rel(root_path, repo_root)}")
            continue
        for path in root_path.glob("*_diagnosis.json"):
            try:
                payload = load_json(path)
            except Exception as exc:
                errors.append(f"diagnosis_invalid_json:{safe_rel(path, repo_root)}:{exc}")
                continue
            meta = payload.get("diagnosis", {}) if isinstance(payload, dict) else {}
            if family_scope and meta.get("familyScope") != family_scope:
                continue
            created_at = meta.get("createdAtUtc")
            timestamp = path.stat().st_mtime
            if created_at:
                try:
                    timestamp = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).timestamp()
                except Exception:
                    pass
            else:
                match = re.search(r"(\d{8}T\d{6}Z)", path.name)
                if match:
                    try:
                        timestamp = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
                    except Exception:
                        pass
            candidates.append((timestamp, path, payload))
    if not candidates:
        return None, None, errors
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1], candidates[0][2], errors


def count_matching_files(repo_root: Path, roots: Iterable[str], patterns: Iterable[str]) -> Tuple[int, List[str], List[str]]:
    matched: List[str] = []
    missing_roots: List[str] = []
    for root_value in roots:
        root_path = repo_path(repo_root, root_value)
        if root_path is None:
            continue
        if not root_path.exists():
            missing_roots.append(str(root_value))
            continue
        for pattern in patterns:
            for path in root_path.rglob(pattern):
                if path.is_file():
                    rel = safe_rel(path, repo_root)
                    if rel not in matched:
                        matched.append(rel or str(path))
    return len(matched), sorted(matched), missing_roots


def find_named_files(repo_root: Path, roots: Iterable[str], names: Iterable[str]) -> Tuple[List[str], List[str]]:
    matched: List[str] = []
    missing_roots: List[str] = []
    name_set = {str(name) for name in names if str(name).strip()}
    for root_value in roots:
        root_path = repo_path(repo_root, root_value)
        if root_path is None:
            continue
        if not root_path.exists():
            missing_roots.append(str(root_value))
            continue
        for path in root_path.rglob("*"):
            if path.is_file() and path.name in name_set:
                rel = safe_rel(path, repo_root)
                if rel not in matched:
                    matched.append(rel or str(path))
    return sorted(matched), missing_roots


def load_json_artifacts(repo_root: Path, rel_paths: Iterable[str], max_items: int = 50) -> Tuple[List[Dict[str, Any]], List[str]]:
    payloads: List[Dict[str, Any]] = []
    errors: List[str] = []
    for rel in list(rel_paths)[:max_items]:
        path = repo_path(repo_root, rel)
        if path is None or not path.is_file():
            errors.append(f"missing:{rel}")
            continue
        try:
            payload = load_json(path)
            if isinstance(payload, dict):
                payloads.append({"path": rel, "payload": payload})
            else:
                errors.append(f"not_json_object:{rel}")
        except Exception as exc:
            errors.append(f"invalid_json:{rel}:{exc}")
    return payloads, errors


def evaluate_default_scheduler_manifest_policy(repo_root: Path, gate_cfg: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    if gate_is_disabled(gate_cfg):
        return True, disabled_gate_evidence()
    roots = gate_cfg.get("roots") or ["infra/k8s/compositions/default-scheduler"]
    forbidden_literal_patterns = [str(item) for item in gate_cfg.get("forbiddenLiteralPatterns", ["nodeName:", "kubernetes.io/hostname"])]
    forbidden_path_fragments = [str(item) for item in gate_cfg.get("forbiddenPathFragments", ["placement-variation", "controlled-placement", "node-pinning"])]
    file_extensions = tuple(gate_cfg.get("fileExtensions", [".yaml", ".yml", ".json"]))
    inspected_files: List[str] = []
    violations: List[Dict[str, Any]] = []
    missing_roots: List[str] = []
    for root_value in roots:
        root_path = repo_path(repo_root, root_value)
        if root_path is None:
            continue
        if not root_path.exists():
            missing_roots.append(str(root_value))
            continue
        for path in root_path.rglob("*"):
            if not path.is_file() or path.suffix not in file_extensions:
                continue
            rel = safe_rel(path, repo_root) or str(path)
            inspected_files.append(rel)
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in forbidden_literal_patterns:
                if pattern and pattern in text:
                    violations.append({"path": rel, "pattern": pattern, "violationType": "forbidden_literal"})
            normalized_rel = rel.replace("\\", "/").lower()
            for fragment in forbidden_path_fragments:
                if fragment and fragment.lower() in normalized_rel:
                    violations.append({"path": rel, "pattern": fragment, "violationType": "forbidden_path_fragment"})
    minimum_files = int(gate_cfg.get("minimumInspectedFileCount", 1))
    passed = len(violations) == 0 and len(inspected_files) >= minimum_files and not missing_roots
    return passed, {
        "roots": roots,
        "missingRoots": missing_roots,
        "inspectedFileCount": len(inspected_files),
        "minimumInspectedFileCount": minimum_files,
        "sampleInspectedFiles": inspected_files[:30],
        "forbiddenLiteralPatterns": forbidden_literal_patterns,
        "forbiddenPathFragments": forbidden_path_fragments,
        "violationCount": len(violations),
        "violations": violations[:50],
    }


def evaluate_network_aware_manifest_policy(repo_root: Path, gate_cfg: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    if gate_is_disabled(gate_cfg):
        return True, disabled_gate_evidence()
    roots = gate_cfg.get("roots") or ["infra/k8s/compositions/network-aware-scheduler"]
    file_extensions = tuple(gate_cfg.get("fileExtensions", [".yaml", ".yml", ".json"]))
    required_literals = [str(item) for item in gate_cfg.get("requiredLiteralPatterns", []) if str(item).strip()]
    forbidden_literals = [str(item) for item in gate_cfg.get("forbiddenLiteralPatterns", ["nodeName:", "kubernetes.io/hostname"]) if str(item).strip()]
    inspected_files: List[str] = []
    missing_roots: List[str] = []
    observed_literals = {literal: False for literal in required_literals}
    violations: List[Dict[str, Any]] = []
    for root_value in roots:
        root_path = repo_path(repo_root, root_value)
        if root_path is None:
            continue
        if not root_path.exists():
            missing_roots.append(str(root_value))
            continue
        for path in root_path.rglob("*"):
            if not path.is_file() or path.suffix not in file_extensions:
                continue
            rel = safe_rel(path, repo_root) or str(path)
            inspected_files.append(rel)
            content = path.read_text(encoding="utf-8", errors="replace")
            for literal in required_literals:
                if literal in content:
                    observed_literals[literal] = True
            for literal in forbidden_literals:
                if literal in content:
                    violations.append({"path": rel, "pattern": literal, "violationType": "forbidden_literal"})

    missing_literals = [literal for literal, observed in observed_literals.items() if not observed]
    profile_evidence: List[Dict[str, Any]] = []
    missing_profile_files: List[str] = []
    for profile_rel in gate_cfg.get("requiredProfileFiles", []):
        profile_path = repo_path(repo_root, str(profile_rel))
        exists = bool(profile_path and profile_path.is_file())
        record: Dict[str, Any] = {"path": str(profile_rel), "exists": exists}
        if exists and profile_path:
            try:
                payload = load_json(profile_path)
                record["jsonLoadable"] = True
                record["profileId"] = payload.get("profileId") or payload.get("schedulerProfileId") or payload.get("monAgentProfileId") or payload.get("networkObservabilityProfileId") or payload.get("istioGatewayProfileId")
            except Exception as exc:
                record["jsonLoadable"] = False
                record["error"] = str(exc)
        else:
            missing_profile_files.append(str(profile_rel))
        profile_evidence.append(record)

    scheduler_profile_rel = gate_cfg.get("schedulerProfilePath") or "config/scheduler/profiles/CS_C9_LOCALAI_RESOURCE_NETWORK_AWARE_SECOND_SCHEDULER.json"
    scheduler_profile_path = repo_path(repo_root, scheduler_profile_rel)
    scheduler_profile, scheduler_profile_error = load_optional(scheduler_profile_path)
    expected_plugins = [str(item) for item in gate_cfg.get("requiredSchedulerPlugins", [])]
    scheduler_profile_text = ""
    if scheduler_profile_path and scheduler_profile_path.is_file():
        scheduler_profile_text = scheduler_profile_path.read_text(encoding="utf-8", errors="replace")
    missing_scheduler_plugins = [plugin for plugin in expected_plugins if plugin not in scheduler_profile_text]
    expected_gateway_key = str(gate_cfg.get("requiredGatewayTrafficKey", "")).strip()
    gateway_key_declared = (not expected_gateway_key) or expected_gateway_key in scheduler_profile_text

    minimum_files = int(gate_cfg.get("minimumInspectedFileCount", 1))
    passed = (
        not missing_roots
        and len(inspected_files) >= minimum_files
        and not missing_literals
        and not violations
        and not missing_profile_files
        and scheduler_profile_error is None
        and not missing_scheduler_plugins
        and gateway_key_declared
    )
    return passed, {
        "roots": roots,
        "missingRoots": missing_roots,
        "inspectedFileCount": len(inspected_files),
        "minimumInspectedFileCount": minimum_files,
        "sampleInspectedFiles": inspected_files[:30],
        "requiredLiteralPatterns": required_literals,
        "missingRequiredLiteralPatterns": missing_literals,
        "forbiddenLiteralPatterns": forbidden_literals,
        "violationCount": len(violations),
        "violations": violations[:50],
        "requiredProfileFiles": profile_evidence,
        "missingProfileFiles": missing_profile_files,
        "schedulerProfilePath": scheduler_profile_rel,
        "schedulerProfileLoadError": scheduler_profile_error,
        "requiredSchedulerPlugins": expected_plugins,
        "missingSchedulerPlugins": missing_scheduler_plugins,
        "requiredGatewayTrafficKey": expected_gateway_key or None,
        "gatewayTrafficKeyDeclared": gateway_key_declared,
        "schedulerProfileId": (scheduler_profile or {}).get("schedulerProfileId") if isinstance(scheduler_profile, dict) else None,
    }


def evaluate_network_aware_telemetry_evidence(repo_root: Path, gate_cfg: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    if gate_is_disabled(gate_cfg):
        return True, disabled_gate_evidence()
    roots = gate_cfg.get("roots") or ["results/experimental-cycles/C9/variants"]
    index = collect_network_aware_telemetry_index(
        repo_root,
        roots,
        required_gateway_key=gate_cfg.get("requiredExactGatewayTrafficKey") or gate_cfg.get("gatewayTrafficKey"),
        required_node_prefixes=gate_cfg.get("requiredNodeAnnotationPrefixes") or [],
        required_deployment_prefixes=gate_cfg.get("requiredDeploymentAnnotationPrefixes") or [],
        component_names=gate_cfg.get("componentArtifactNames") or None,
        require_cluster_lens=gate_cfg.get("requireClusterLensPlacementEvidence"),
    )
    minimum_components = int(gate_cfg.get("minimumComponentsWithEvidence", 4))
    minimum_artifacts = int(gate_cfg.get("minimumArtifactCount", 4))
    minimum_complete_scenarios = int(gate_cfg.get("minimumCompleteScenarioCount", 1))
    complete_scenarios = index.get("completeScenarioIds") or []
    scenarios = index.get("scenarios") or {}
    component_counts: Dict[str, int] = {}
    artifact_count = 0
    rejected_statuses: List[Dict[str, Any]] = []
    gateway_failures: List[str] = []
    matrix_failures: List[str] = []
    for scenario_id, scenario_evidence in sorted(scenarios.items()):
        for component, record in (scenario_evidence.get("components") or {}).items():
            if record.get("artifactPath"):
                artifact_count += 1
                component_counts[component] = component_counts.get(component, 0) + 1
            if component in {"monAgent", "mentat", "istio", "rescheduling", "clusterLens"} and record.get("artifactPath") and not record.get("accepted"):
                rejected_statuses.append({"scenarioId": scenario_id, "component": component, "status": record.get("status"), "path": record.get("artifactPath")})
        gateway = scenario_evidence.get("gatewayTrafficKeyEvidence") or {}
        if not gateway.get("requiredGatewayTrafficKeyPresent"):
            gateway_failures.append(scenario_id)
        matrix = scenario_evidence.get("latencyMatrixValidation") or {}
        if not matrix.get("accepted"):
            matrix_failures.append(scenario_id)
    components_with_evidence = sorted(component for component, count in component_counts.items() if count > 0)
    passed = (
        not index.get("missingRoots")
        and len(components_with_evidence) >= minimum_components
        and artifact_count >= minimum_artifacts
        and len(complete_scenarios) >= minimum_complete_scenarios
        and not rejected_statuses
        and not gateway_failures
        and not matrix_failures
    )
    return passed, {
        "roots": roots,
        "missingRoots": index.get("missingRoots") or [],
        "scenarioCount": index.get("scenarioCount"),
        "completeScenarioCount": index.get("completeScenarioCount"),
        "completeScenarioIds": complete_scenarios,
        "minimumCompleteScenarioCount": minimum_complete_scenarios,
        "incompleteScenarios": index.get("incompleteScenarios") or {},
        "componentCounts": component_counts,
        "componentsWithEvidence": components_with_evidence,
        "minimumComponentsWithEvidence": minimum_components,
        "matchedArtifactCount": artifact_count,
        "minimumArtifactCount": minimum_artifacts,
        "rejectedComponentStatuses": rejected_statuses[:50],
        "gatewayTrafficKey": gate_cfg.get("requiredExactGatewayTrafficKey") or gate_cfg.get("gatewayTrafficKey"),
        "gatewayTrafficKeyFailures": gateway_failures[:50],
        "latencyMatrixValidationFailures": matrix_failures[:50],
        "requiredNodeAnnotationPrefixes": gate_cfg.get("requiredNodeAnnotationPrefixes", []),
        "requiredDeploymentAnnotationPrefixes": gate_cfg.get("requiredDeploymentAnnotationPrefixes", []),
        "scenarioEvidenceSample": {key: scenarios[key] for key in list(sorted(scenarios))[:5]},
    }


def evaluate_named_json_artifact_gate(repo_root: Path, gate_cfg: Dict[str, Any], runtime: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    if gate_is_disabled(gate_cfg):
        return True, disabled_gate_evidence()
    roots = gate_cfg.get("roots") or []
    if not roots and gate_cfg.get("root"):
        roots = [gate_cfg.get("root")]
    names = gate_cfg.get("artifactNames") or gate_cfg.get("artifactName")
    if isinstance(names, str):
        names = [names]
    if not names:
        names = []
    matched, missing_roots = find_named_files(repo_root, roots, names)
    payloads, load_errors = load_json_artifacts(repo_root, matched, int(gate_cfg.get("maxArtifactsToInspect", 50)))
    minimum_artifacts = int(gate_cfg.get("minimumArtifactCount", 1))
    accepted_statuses = set(gate_cfg.get("acceptedStatuses", []))
    require_json_loadable = bool(gate_cfg.get("requireJsonLoadable", True))
    require_status_accepted = bool(gate_cfg.get("requireAcceptedStatus", False))
    accepted_payloads = []
    rejected_payloads = []
    required_dotted_paths = gate_cfg.get("requiredDottedPaths", [])
    minimum_numeric_paths = gate_cfg.get("minimumNumericDottedPaths") or {}
    if isinstance(minimum_numeric_paths, list):
        minimum_numeric_paths = {str(item): 1 for item in minimum_numeric_paths}
    elif not isinstance(minimum_numeric_paths, dict):
        minimum_numeric_paths = {}
    missing_required_paths: List[Dict[str, Any]] = []
    numeric_path_failures: List[Dict[str, Any]] = []
    for item in payloads:
        payload = item["payload"]
        status = payload.get("status")
        paths_ok = True
        numeric_ok = True
        missing_for_payload = []
        numeric_failures_for_payload = []
        for dotted_path in required_dotted_paths:
            value = get_nested(payload, str(dotted_path))
            if value is None:
                paths_ok = False
                missing_for_payload.append(str(dotted_path))
        for dotted_path, minimum_value in minimum_numeric_paths.items():
            value = get_nested(payload, str(dotted_path))
            try:
                numeric_value = float(value)
                numeric_minimum = float(minimum_value)
            except (TypeError, ValueError):
                numeric_ok = False
                numeric_failures_for_payload.append({
                    "path": str(dotted_path),
                    "observedValue": value,
                    "minimumValue": minimum_value,
                    "reason": "not_numeric",
                })
                continue
            if numeric_value < numeric_minimum:
                numeric_ok = False
                numeric_failures_for_payload.append({
                    "path": str(dotted_path),
                    "observedValue": numeric_value,
                    "minimumValue": numeric_minimum,
                    "reason": "below_minimum",
                })
        status_ok = (not require_status_accepted) or status in accepted_statuses
        entry = {
            "path": item["path"],
            "status": status,
            "requiredPathsOk": paths_ok,
            "numericPathsOk": numeric_ok,
            "missingRequiredPaths": missing_for_payload,
            "numericPathFailures": numeric_failures_for_payload,
        }
        if status_ok and paths_ok and numeric_ok:
            accepted_payloads.append(entry)
        else:
            rejected_payloads.append(entry)
            if missing_for_payload:
                missing_required_paths.append({"path": item["path"], "missingRequiredPaths": missing_for_payload})
            if numeric_failures_for_payload:
                numeric_path_failures.append({"path": item["path"], "numericPathFailures": numeric_failures_for_payload})
    load_gate = (not require_json_loadable) or not load_errors
    passed = len(matched) >= minimum_artifacts and load_gate and len(accepted_payloads) >= minimum_artifacts and not missing_roots
    return passed, {
        "roots": roots,
        "artifactNames": names,
        "matchedArtifactCount": len(matched),
        "minimumArtifactCount": minimum_artifacts,
        "matchedArtifacts": matched[:50],
        "missingRoots": missing_roots,
        "loadErrors": load_errors,
        "requireJsonLoadable": require_json_loadable,
        "acceptedStatuses": sorted(accepted_statuses),
        "requireAcceptedStatus": require_status_accepted,
        "acceptedPayloadCount": len(accepted_payloads),
        "acceptedPayloads": accepted_payloads[:30],
        "rejectedPayloads": rejected_payloads[:30],
        "requiredDottedPaths": required_dotted_paths,
        "minimumNumericDottedPaths": minimum_numeric_paths,
        "missingRequiredPaths": missing_required_paths[:30],
        "numericPathFailures": numeric_path_failures[:30],
    }


def evaluate_latency_evidence_gate(repo_root: Path, profile: Dict[str, Any], gate_cfg: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    if gate_is_disabled(gate_cfg):
        return True, disabled_gate_evidence()
    scenario_index_path = repo_path(repo_root, gate_cfg.get("scenarioIndexPath") or "config/scenarios/default-scheduler/DEFAULT_SCHEDULER_SCENARIOS_INDEX.json")
    scenario_index, scenario_index_error = load_optional(scenario_index_path)
    scenario_entries = scenario_index.get("scenarios", []) if isinstance(scenario_index, dict) else []
    latency_profiles = sorted({entry.get("latencyProfileId") for entry in scenario_entries if isinstance(entry, dict) and entry.get("latencyProfileId")})
    configured_latency_scenarios = [entry.get("scenarioId") for entry in scenario_entries if isinstance(entry, dict) and str(entry.get("latencyProfileId", "")).strip() not in {"", "L0_NONE"}]
    roots = gate_cfg.get("roots") or ["results/experimental-cycles/C7/variants", "results/experimental-cycles/C7/latency-injection"]
    names = gate_cfg.get("artifactNames") or ["latest-latency-injection-manifest.json", "latency-profile-disabled.json"]
    matched, missing_roots = find_named_files(repo_root, roots, names)
    minimum_runtime_artifacts = int(gate_cfg.get("minimumRuntimeArtifactCount", 0))
    passed = scenario_index_error is None and bool(configured_latency_scenarios) and len(matched) >= minimum_runtime_artifacts
    return passed, {
        "scenarioIndexPath": safe_rel(scenario_index_path, repo_root),
        "scenarioIndexLoadError": scenario_index_error,
        "declaredLatencyProfiles": latency_profiles,
        "declaredLatencyScenarioCount": len(configured_latency_scenarios),
        "sampleLatencyScenarios": configured_latency_scenarios[:20],
        "runtimeEvidenceRoots": roots,
        "runtimeArtifactNames": names,
        "runtimeArtifactCount": len(matched),
        "minimumRuntimeArtifactCount": minimum_runtime_artifacts,
        "runtimeArtifacts": matched[:30],
        "missingRuntimeRoots": missing_roots,
        "note": "L0 scenarios are considered explicitly disabled by configuration; runtime latency artifacts are required only when minimumRuntimeArtifactCount is greater than zero.",
    }


def evaluate_default_scheduler_specific_gates(repo_root: Path, profile: Dict[str, Any], runtime: Dict[str, Any]) -> List[Dict[str, Any]]:
    gates: List[Dict[str, Any]] = []
    gate_cfg = profile.get("gates") or {}

    manifest_cfg = gate_cfg.get("schedulerModeManifestPolicyValidation") or gate_cfg.get("defaultSchedulerManifestValidation") or {}
    if manifest_cfg:
        passed, evidence = evaluate_default_scheduler_manifest_policy(repo_root, manifest_cfg)
        if "schedulerModeManifestPolicyValidation" in gate_cfg:
            add_gate(
                gates,
                str(manifest_cfg.get("gateId") or "scheduler_mode_manifest_policy_clean"),
                str(manifest_cfg.get("title") or "Scheduler-mode manifests do not contain hard pod-placement controls."),
                passed,
                evidence,
                str(manifest_cfg.get("implication") or "Completion requires placement to be owned by Kubernetes scheduler decisions rather than static manifest pinning."),
                "configuration",
            )
        else:
            add_gate(gates, "default_scheduler_manifest_policy_clean", "Default-scheduler manifests do not contain hard pod-placement controls.", passed, evidence, "C7 completion requires Kubernetes, not static manifest pinning, to own pod placement decisions.", "configuration")

    cluster_validation_cfg = gate_cfg.get("clusterValidationArtifacts") or {}
    if cluster_validation_cfg:
        passed, evidence = evaluate_named_json_artifact_gate(repo_root, cluster_validation_cfg, runtime)
        add_gate(gates, "cluster_validation_artifacts_available", "Cluster validation artifacts are available for executed scheduler variants.", passed, evidence, "Scheduler evidence must be tied to a validated provider-backed Kubernetes cluster before workload results are interpreted.", "validation")

    application_deployment_cfg = gate_cfg.get("applicationDeploymentArtifacts") or {}
    if application_deployment_cfg:
        passed, evidence = evaluate_named_json_artifact_gate(repo_root, application_deployment_cfg, runtime)
        add_gate(gates, "application_deployment_artifacts_available", "Application deployment artifacts are available for executed scheduler variants.", passed, evidence, "Scheduler measurements must be linked to deployed LocalAI tenant topologies.", "deployment")

    scheduler_cfg = gate_cfg.get("schedulerDecisionEvidence") or {}
    if scheduler_cfg:
        passed, evidence = evaluate_named_json_artifact_gate(repo_root, scheduler_cfg, runtime)
        add_gate(gates, "scheduler_decision_evidence_available", "Scheduler decision evidence has been captured.", passed, evidence, "Completion requires saved pod-to-node and placement-classification evidence for the evaluated scheduler scenarios.", "observability")

    mt_cfg = gate_cfg.get("multiTenantBenchmarkSummary") or {}
    if mt_cfg:
        passed, evidence = evaluate_named_json_artifact_gate(repo_root, mt_cfg, runtime)
        add_gate(gates, "multi_tenant_benchmark_summary_available", "Tenant-scoped benchmark summary artifacts are available.", passed, evidence, "Multi-tenant scheduler interpretation requires tenant-level workload evidence rather than only aggregate files.", "benchmark")

    latency_cfg = gate_cfg.get("latencyEvidence") or {}
    if latency_cfg:
        passed, evidence = evaluate_latency_evidence_gate(repo_root, profile, latency_cfg)
        add_gate(gates, "latency_evidence_declared", "Latency-enabled and latency-disabled scenarios are explicitly represented.", passed, evidence, "C7 completion must distinguish L0 control scenarios from scenarios where latency injection is applied and then interpreted.", "observability")

    net_manifest_cfg = gate_cfg.get("networkAwareManifestPolicyValidation") or {}
    if net_manifest_cfg:
        passed, evidence = evaluate_network_aware_manifest_policy(repo_root, net_manifest_cfg)
        add_gate(gates, "network_aware_manifest_policy_valid", "Network-aware manifests and scheduler profile expose the required labels, routing and plugins.", passed, evidence, "C9 completion requires LocalAI workloads to expose group/app/role labels, gateway-routed namespaces and the NetworkAwareLocalAi scheduler plugin without hard placement controls.", "configuration")

    net_telemetry_cfg = gate_cfg.get("networkAwareTelemetryEvidence") or {}
    if net_telemetry_cfg:
        passed, evidence = evaluate_network_aware_telemetry_evidence(repo_root, net_telemetry_cfg)
        add_gate(gates, "network_aware_telemetry_evidence_available", "Network-aware telemetry, annotation and placement evidence is available for executed variants.", passed, evidence, "C9 results are interpretable only when mon-agent annotations, Mentat network telemetry, Istio gateway evidence, telemetry-primed scheduling evidence and cluster-lens placement evidence are preserved with the benchmark outputs.", "observability")

    return gates
    

def status_in(payload: Optional[Dict[str, Any]], accepted: Iterable[str]) -> Tuple[bool, Optional[str]]:
    status = payload.get("status") if isinstance(payload, dict) else None
    return status in set(accepted), status


def evaluate_manifest_gate(repo_root: Path, gate_id: str, gate_cfg: Dict[str, Any], manifest_path_value: Optional[str], accepted_statuses: List[str], decision_paths: List[str]) -> Tuple[bool, Dict[str, Any], Optional[Dict[str, Any]]]:
    manifest_path = repo_path(repo_root, manifest_path_value)
    payload, error = load_optional(manifest_path)
    evidence: Dict[str, Any] = {
        "manifestPath": safe_rel(manifest_path, repo_root),
        "exists": manifest_path.exists() if manifest_path else False,
        "loadError": error,
        "acceptedStatuses": accepted_statuses,
        "decisionChecks": {},
    }
    if not isinstance(payload, dict):
        return False, evidence, None
    passed_status, observed_status = status_in(payload, accepted_statuses)
    evidence["observedStatus"] = observed_status
    passed = passed_status
    for path in decision_paths:
        value = get_nested(payload, path)
        evidence["decisionChecks"][path] = value
        if value is not True:
            passed = False
    return passed, evidence, payload


def gate_is_disabled(gate_cfg: Dict[str, Any]) -> bool:
    return isinstance(gate_cfg, dict) and gate_cfg.get("enabled") is False


def disabled_gate_evidence(reason: str = "disabled_by_profile") -> Dict[str, Any]:
    return {"enabled": False, "reason": reason}


def setdefault_nonempty(target: Dict[str, Any], key: str, value: Any) -> None:
    if key not in target and isinstance(value, str) and value.strip():
        target[key] = value


def evaluate_report_sections(report_path: Optional[Path], required_sections: Iterable[str]) -> Dict[str, Any]:
    if report_path is None or not report_path.is_file():
        return {"reportPath": safe_rel(report_path, report_path.parent if report_path else Path.cwd()), "missingSections": list(required_sections), "presentSections": []}
    content = report_path.read_text(encoding="utf-8", errors="replace")
    present = []
    missing = []
    for section in required_sections:
        if str(section) in content:
            present.append(str(section))
        else:
            missing.append(str(section))
    return {"presentSections": present, "missingSections": missing}


def evaluate_provider_aware(profile: Dict[str, Any], repo_root: Path, args: argparse.Namespace) -> Dict[str, Any]:
    cycle_path = repo_path(repo_root, args.cycle_config or profile.get("cycleConfigPath"))
    cycle, cycle_error = load_optional(cycle_path)
    cycle = cycle if isinstance(cycle, dict) else {}
    gates: List[Dict[str, Any]] = []

    required_refs = dict(profile.get("requiredReferences") or {})
    if cycle:
        provider_backed = cycle.get("providerBackedInfrastructure") or {}
        pipeline_profiles = cycle.get("pipelineProfiles") or {}
        setdefault_nonempty(required_refs, "cycleConfig", safe_rel(cycle_path, repo_root) if cycle_path else profile.get("cycleConfigPath"))
        setdefault_nonempty(required_refs, "baselineConfig", (cycle.get("baseline") or {}).get("configPath"))
        setdefault_nonempty(required_refs, "infrastructureProfile", provider_backed.get("infrastructureProfilePath"))
        setdefault_nonempty(required_refs, "providerBinding", provider_backed.get("providerBindingPath"))
        setdefault_nonempty(required_refs, "provisioningIntegrationProfile", provider_backed.get("provisioningIntegrationProfilePath") or pipeline_profiles.get("provisioningIntegration"))
        setdefault_nonempty(required_refs, "clusterValidationProfile", provider_backed.get("clusterValidationProfilePath") or pipeline_profiles.get("clusterValidation"))
        setdefault_nonempty(required_refs, "applicationDeploymentProfile", provider_backed.get("applicationDeploymentProfilePath") or pipeline_profiles.get("applicationDeployment"))
        setdefault_nonempty(required_refs, "placementProfile", provider_backed.get("placementProfilePath") or pipeline_profiles.get("baselinePlacementProfile"))
        setdefault_nonempty(required_refs, "minimalObservabilityProfile", provider_backed.get("minimalObservabilityProfilePath") or pipeline_profiles.get("minimalObservability"))
        setdefault_nonempty(required_refs, "reportingProfile", provider_backed.get("reportingProfilePath") or pipeline_profiles.get("reporting"))
        if not bool(profile.get("ignoreCycleFreezeProfileInProfileResolution", False)):
            setdefault_nonempty(required_refs, "freezeProfile", provider_backed.get("freezeProfilePath") or pipeline_profiles.get("freeze") or (cycle.get("freeze") or {}).get("freezeProfilePath"))

    ref_evidence = {}
    missing_refs = []
    for key, value in sorted(required_refs.items()):
        path = repo_path(repo_root, value)
        exists = bool(path and path.is_file())
        ref_evidence[key] = {"path": value, "resolvedPath": safe_rel(path, repo_root), "exists": exists}
        if not exists:
            missing_refs.append(key)
    profile_resolution_passed = not missing_refs and cycle_error is None
    if cycle_error:
        ref_evidence["cycleConfigError"] = cycle_error
    add_gate(gates, "profile_resolution", "Required cycle, infrastructure and pipeline profiles are resolvable.", profile_resolution_passed, {"references": ref_evidence, "missingReferenceKeys": missing_refs}, "Provider-backed execution must be traceable through explicit configuration profiles before runtime evidence is accepted.", "configuration")

    provider_cfg = (profile.get("gates") or {}).get("providerConfig") or {}
    if gate_is_disabled(provider_cfg):
        add_gate(gates, "provider_config_resolved", "Provider binding and provider configuration references are declared.", True, disabled_gate_evidence(), "The completion decision must be tied to a resolvable provider binding without embedding provider-specific logic into the benchmark suite.", "configuration")
    else:
        provider_binding_payload, provider_binding_error = load_optional(repo_path(repo_root, required_refs.get("providerBinding")))
        selected_config_paths = []
        provider_config_status = None
        if isinstance(provider_binding_payload, dict):
            config_selection = provider_binding_payload.get("providerConfigSelection") or provider_binding_payload.get("providerConfig") or {}
            provider_config_status = provider_binding_payload.get("status") or provider_binding_payload.get("bindingStatus") or "declared"
            for key in ["localConfigPath", "exampleConfigPath", "templatePath", "providerConfigLocalPath", "providerConfigExamplePath"]:
                value = config_selection.get(key) if isinstance(config_selection, dict) else None
                if value:
                    selected_config_paths.append(value)
            for key in ["providerConfigLocalPath", "providerConfigExamplePath", "providerConfigTemplatePath"]:
                value = provider_binding_payload.get(key)
                if value:
                    selected_config_paths.append(value)
        if cycle:
            provider_backed = cycle.get("providerBackedInfrastructure") or {}
            for key in ["providerConfigLocalPath", "providerConfigExamplePath", "providerConfigTemplatePath"]:
                value = provider_backed.get(key)
                if value:
                    selected_config_paths.append(value)
        selected_config_paths = sorted(set(selected_config_paths))
        existing_provider_configs = [path for path in selected_config_paths if (repo_path(repo_root, path) and repo_path(repo_root, path).is_file())]
        provider_config_declared = bool(selected_config_paths)
        require_provider_config_file = bool(provider_cfg.get("requireProviderConfigFile", False))
        provider_config_passed = provider_binding_error is None and provider_config_declared and (not require_provider_config_file or bool(existing_provider_configs))
        add_gate(gates, "provider_config_resolved", "Provider binding and provider configuration references are declared.", provider_config_passed, {"providerBindingError": provider_binding_error, "providerBindingStatus": provider_config_status, "providerConfigDeclaredPaths": selected_config_paths, "existingProviderConfigPaths": existing_provider_configs, "requireProviderConfigFile": require_provider_config_file}, "The completion decision must be tied to a resolvable provider binding without embedding provider-specific logic into the benchmark suite.", "configuration")

    gate_cfg = profile.get("gates") or {}
    runtime = profile.get("runtimeEvidence") or {}

    prov_cfg = gate_cfg.get("provisioning") or {}
    if gate_is_disabled(prov_cfg):
        provisioning_manifest = None
        add_gate(gates, "provisioning_completed", "Provider-backed provisioning evidence is complete and accepted.", True, disabled_gate_evidence(), "The generated cluster must be created or refreshed successfully before validation and workloads are considered.", "provisioning")
    else:
        prov_passed, prov_evidence, provisioning_manifest = evaluate_manifest_gate(repo_root, "provisioning", prov_cfg, prov_cfg.get("manifestPath") or runtime.get("provisioningManifest"), prov_cfg.get("acceptedStatuses", ["completed"]), ["decision.canProceedToClusterValidation"] if prov_cfg.get("requireCanProceedToClusterValidation", True) else [])
        add_gate(gates, "provisioning_completed", "Provider-backed provisioning evidence is complete and accepted.", prov_passed, prov_evidence, "The generated cluster must be created or refreshed successfully before validation and workloads are considered.", "provisioning")

    cv_cfg = gate_cfg.get("clusterValidation") or {}
    if gate_is_disabled(cv_cfg):
        cluster_validation_manifest = None
        add_gate(gates, "cluster_validation_passed", "Generated cluster validation has passed.", True, disabled_gate_evidence(), "LocalAI deployment must not proceed on an unvalidated provider-backed cluster.", "validation")
    else:
        cv_passed, cv_evidence, cluster_validation_manifest = evaluate_manifest_gate(repo_root, "cluster_validation", cv_cfg, cv_cfg.get("manifestPath") or runtime.get("clusterValidationManifest"), cv_cfg.get("acceptedStatuses", ["validated"]), ["decision.canProceedToApplicationDeployment"] if cv_cfg.get("requireCanProceedToApplicationDeployment", True) else [])
        add_gate(gates, "cluster_validation_passed", "Generated cluster validation has passed.", cv_passed, cv_evidence, "LocalAI deployment must not proceed on an unvalidated provider-backed cluster.", "validation")

    ad_cfg = gate_cfg.get("applicationDeployment") or {}
    if gate_is_disabled(ad_cfg):
        app_manifest = None
        add_gate(gates, "application_deployment_and_smoke_validated", "LocalAI deployment and smoke validation are accepted.", True, disabled_gate_evidence(), "Benchmark and diagnosis results must be tied to a deployed and smoke-validated LocalAI topology.", "deployment")
    else:
        ad_passed, ad_evidence, app_manifest = evaluate_manifest_gate(repo_root, "application_deployment", ad_cfg, ad_cfg.get("manifestPath") or runtime.get("applicationDeploymentManifest"), ad_cfg.get("acceptedStatuses", ["deployed", "smoke_validated"]), ["decision.canProceedToBenchmark"] if ad_cfg.get("requireCanProceedToBenchmark", True) else [])
        smoke_evidence = {}
        if ad_cfg.get("requireSmokeValidation", True):
            smoke_status = get_nested(app_manifest, "smokeValidation.status") if isinstance(app_manifest, dict) else None
            smoke_passed = get_nested(app_manifest, "smokeValidation.passed") if isinstance(app_manifest, dict) else None
            accepted_smoke = ad_cfg.get("acceptedSmokeStatuses", ["passed"])
            smoke_evidence = {"observedStatus": smoke_status, "observedPassed": smoke_passed, "acceptedSmokeStatuses": accepted_smoke}
            if smoke_status not in accepted_smoke or smoke_passed is not True:
                ad_passed = False
        ad_evidence["smokeValidation"] = smoke_evidence
        add_gate(gates, "application_deployment_and_smoke_validated", "LocalAI deployment and smoke validation are accepted.", ad_passed, ad_evidence, "Benchmark and diagnosis results must be tied to a deployed and smoke-validated LocalAI topology.", "deployment")

    mo_cfg = gate_cfg.get("minimalObservability") or {}
    if gate_is_disabled(mo_cfg):
        minimal_observability_manifest = None
        add_gate(gates, "minimal_observability_available", "Minimal observability evidence is available.", True, disabled_gate_evidence(), "Completion must preserve CPU, memory, placement, restart and event evidence without requiring a heavyweight observability stack.", "observability")
    else:
        mo_passed, mo_evidence, minimal_observability_manifest = evaluate_manifest_gate(repo_root, "minimal_observability", mo_cfg, mo_cfg.get("manifestPath") or runtime.get("minimalObservabilityManifest"), mo_cfg.get("acceptedStatuses", ["observability_collected", "collected_with_warnings"]), ["decision.canProceedToDiagnosis"] if mo_cfg.get("requireCanProceedToDiagnosis", True) else [])
        metrics_path = repo_path(repo_root, mo_cfg.get("metricsSnapshotPath") or runtime.get("minimalObservabilityMetrics"))
        mo_evidence["metricsSnapshotPath"] = safe_rel(metrics_path, repo_root)
        mo_evidence["metricsSnapshotExists"] = bool(metrics_path and metrics_path.is_file())
        if mo_cfg.get("enabled", True) and not mo_evidence["metricsSnapshotExists"]:
            mo_passed = False
        add_gate(gates, "minimal_observability_available", "Minimal observability evidence is available.", mo_passed, mo_evidence, "Completion must preserve CPU, memory, placement, restart and event evidence without requiring a heavyweight observability stack.", "observability")

    bench_cfg = gate_cfg.get("benchmarkArtifacts") or {}
    bench_count, bench_files, bench_missing_roots = count_matching_files(repo_root, bench_cfg.get("roots", runtime.get("benchmarkRoots", [])), bench_cfg.get("patterns", ["*.csv", "*.json"]))
    minimum_benchmark = int(bench_cfg.get("minimumArtifactCount", 1))
    bench_passed = (not bench_cfg.get("enabled", True)) or bench_count >= minimum_benchmark
    add_gate(gates, "benchmark_artifacts_available", "Benchmark artifacts are available under cycle-scoped roots.", bench_passed, {"artifactCount": bench_count, "minimumArtifactCount": minimum_benchmark, "sampleArtifacts": bench_files[:20], "missingRoots": bench_missing_roots}, "Completion requires measured workload artifacts, not only configuration or deployment manifests.", "benchmark")

    cluster_side_cfg = gate_cfg.get("clusterSideArtifacts") or {}
    cluster_side_count, cluster_side_files, cluster_side_missing_roots = count_matching_files(repo_root, cluster_side_cfg.get("roots", runtime.get("clusterSideRoots", [])), cluster_side_cfg.get("patterns", ["*.json", "*.txt", "*.csv"]))
    minimum_cluster_side = int(cluster_side_cfg.get("minimumArtifactCount", 1))
    cluster_side_passed = (not cluster_side_cfg.get("enabled", True)) or cluster_side_count >= minimum_cluster_side
    add_gate(gates, "cluster_side_artifacts_available", "Cluster-side artifacts are available.", cluster_side_passed, {"artifactCount": cluster_side_count, "minimumArtifactCount": minimum_cluster_side, "sampleArtifacts": cluster_side_files[:20], "missingRoots": cluster_side_missing_roots}, "Infrastructure-side evidence must accompany client-side benchmark metrics.", "observability")

    td_cfg = gate_cfg.get("technicalDiagnosis") or {}
    diagnosis_path = repo_path(repo_root, args.diagnosis_json) if args.diagnosis_json else None
    diagnosis_payload = None
    diagnosis_discovery_errors: List[str] = []
    if diagnosis_path:
        diagnosis_payload, diagnosis_error = load_optional(diagnosis_path)
        if diagnosis_error:
            diagnosis_discovery_errors.append(f"explicit_diagnosis:{diagnosis_error}")
            diagnosis_payload = None
    else:
        diagnosis_path, diagnosis_payload, diagnosis_discovery_errors = latest_diagnosis_from_roots(repo_root, td_cfg.get("roots", runtime.get("technicalDiagnosisFallbackRoots", [])), td_cfg.get("familyScope", "all"))
    diagnosis_meta = diagnosis_payload.get("diagnosis", {}) if isinstance(diagnosis_payload, dict) else {}
    diagnosis_status = diagnosis_meta.get("closureStatus")
    td_accepted = td_cfg.get("acceptedClosureStatuses", ["preliminary_diagnosis_available"])
    td_passed = isinstance(diagnosis_payload, dict) and diagnosis_status in td_accepted
    add_gate(gates, "technical_diagnosis_available", "Technical diagnosis is available with an accepted closure status.", td_passed, {"diagnosisPath": safe_rel(diagnosis_path, repo_root), "diagnosisId": diagnosis_meta.get("diagnosisId"), "diagnosisClosureStatus": diagnosis_status, "acceptedClosureStatuses": td_accepted, "discoveryErrors": diagnosis_discovery_errors}, "Completion requires structured interpretation of the benchmark and infrastructure evidence.", "diagnosis")

    if isinstance(diagnosis_payload, dict) and profile.get("requiredFamilies"):
        family_coverage_passed, family_coverage = evaluate_family_coverage(profile, diagnosis_payload)
        add_gate(gates, "benchmark_family_coverage_sufficient", "Required benchmark families have sufficient measured or explicitly unsupported coverage.", family_coverage_passed, family_coverage, "Provider-backed campaign completion must be based on scenario-level evidence and must not be satisfied by unrelated files in the benchmark root.", "benchmark")
        repeatability_passed, repeatability = evaluate_repeatability(profile, diagnosis_payload)
        add_gate(gates, "repeatability_signal_present", "At least one measured scenario provides an acceptable repeatability signal for each required family.", repeatability_passed, repeatability, "Unsupported scenarios can document capacity or provider constraints, but at least one measured scenario is required for quantitative interpretation.", "benchmark")

    rep_cfg = gate_cfg.get("reporting") or {}
    reporting_root = repo_path(repo_root, rep_cfg.get("reportingRoot") or runtime.get("reportingRoot") or "results/experimental-cycles/C1/reporting")
    manifest_name = rep_cfg.get("manifestName", "reporting-manifest.json")
    markdown_name = rep_cfg.get("markdownReportName", "report.md")
    html_name = rep_cfg.get("htmlReportName", "index.html")
    summary_name = rep_cfg.get("scenarioSummaryCsvName", "scenario-summary.csv")
    charts_dir = rep_cfg.get("chartsDirectoryName", "charts")
    sweeps_dir = rep_cfg.get("sweepsDirectoryName", "sweeps")
    required_files = [reporting_root / manifest_name, reporting_root / markdown_name, reporting_root / html_name, reporting_root / summary_name]
    reporting_missing_files = [safe_rel(path, repo_root) for path in required_files if not path.is_file()]
    missing_charts = []
    for family in rep_cfg.get("requiredChartFamilies", []):
        for metric in rep_cfg.get("requiredChartMetrics", []):
            chart = reporting_root / charts_dir / family / f"{metric}.svg"
            if not chart.is_file():
                missing_charts.append({"family": family, "metric": metric, "path": safe_rel(chart, repo_root)})
    missing_sweeps = []
    for family in rep_cfg.get("requiredSweepReports", []):
        md = reporting_root / sweeps_dir / family / markdown_name
        html = reporting_root / sweeps_dir / family / html_name
        missing = [safe_rel(path, repo_root) for path in [md, html] if not path.is_file()]
        if missing:
            missing_sweeps.append({"family": family, "missingFiles": missing})
    section_eval = evaluate_report_sections(reporting_root / markdown_name, rep_cfg.get("requiredSections", []))
    reporting_manifest, reporting_manifest_error = load_optional(reporting_root / manifest_name)
    reporting_passed = not reporting_missing_files and not missing_charts and not missing_sweeps and not section_eval.get("missingSections") and reporting_manifest_error is None
    add_gate(gates, "reporting_artifacts_available", "Provider-aware reporting artifacts are available and structurally complete.", reporting_passed, {"reportingRoot": safe_rel(reporting_root, repo_root), "missingFiles": reporting_missing_files, "missingCharts": missing_charts, "missingSweepReports": missing_sweeps, "sectionEvaluation": section_eval, "manifestLoadError": reporting_manifest_error, "reportingId": get_nested(reporting_manifest, "reporting.reportingId") if isinstance(reporting_manifest, dict) else None}, "Completion must occur only after results are readable through cycle-scoped reports, tables and charts.", "reporting")

    gates.extend(evaluate_default_scheduler_specific_gates(repo_root, profile, runtime))

    freeze_cfg = gate_cfg.get("freezeReadiness") or {}
    freeze_outputs = cycle.get("freezeOutputs") if isinstance(cycle, dict) else None
    freeze_profile_path = (
        (cycle.get("freeze") or {}).get("freezeProfilePath")
        or (freeze_outputs or {}).get("freezeProfilePath")
        or (cycle.get("providerBackedInfrastructure") or {}).get("freezeProfilePath")
        or (cycle.get("pipelineProfiles") or {}).get("freeze")
        or freeze_cfg.get("freezeProfilePath")
    )
    freeze_profile_file = repo_path(repo_root, freeze_profile_path)
    freeze_outputs_ok = not freeze_cfg.get("requireFreezeOutputsDeclared", True) or isinstance(freeze_outputs, dict)
    freeze_profile_ok = (
        not freeze_cfg.get("requireFreezeProfileDeclared", False)
        or bool(freeze_profile_path)
    )
    freeze_profile_file_ok = (
        not freeze_cfg.get("requireFreezeProfileFile", False)
        or bool(freeze_profile_file and freeze_profile_file.is_file())
    )
    freeze_passed = not freeze_cfg.get("enabled", True) or (freeze_outputs_ok and freeze_profile_ok and freeze_profile_file_ok)
    add_gate(gates, "freeze_readiness_declared", "Freeze outputs and profile are declared for the cycle.", freeze_passed, {"freezeOutputsDeclared": isinstance(freeze_outputs, dict), "freezeOutputs": freeze_outputs, "freezeProfilePath": freeze_profile_path, "freezeProfileExists": bool(freeze_profile_file and freeze_profile_file.is_file()), "requireFrozenArtifacts": bool(freeze_cfg.get("requireFrozenArtifacts", False))}, "The completion gate validates readiness for the dedicated freeze workflow without producing frozen artifacts itself.", "freeze")

    unsupported_signals = collect_unsupported_signals(diagnosis_payload, reporting_manifest, profile)

    return build_payload(
        profile,
        repo_root,
        args,
        gates,
        diagnosis_reference={
            "diagnosisJson": safe_rel(diagnosis_path, repo_root),
            "diagnosisId": diagnosis_meta.get("diagnosisId"),
            "diagnosisClosureStatus": diagnosis_status,
            "familyScope": diagnosis_meta.get("familyScope"),
        },
        reporting_reference={"reportingRoot": safe_rel(reporting_root, repo_root), "reportingId": get_nested(reporting_manifest, "reporting.reportingId") if isinstance(reporting_manifest, dict) else None},
        source_gaps=diagnosis_payload.get("gaps", []) if isinstance(diagnosis_payload, dict) else [],
        provider_aware=True,
        cycle_reference={"cycleConfigPath": safe_rel(cycle_path, repo_root), "cycleId": cycle.get("cycleId"), "baselineId": (cycle.get("baseline") or {}).get("baselineId") or (cycle.get("cycleGovernance") or {}).get("baselineId")},
        unsupported_signals=unsupported_signals,
    )


def collect_unsupported_signals(diagnosis_payload: Optional[Dict[str, Any]], reporting_manifest: Optional[Dict[str, Any]], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []
    signal_terms = [str(item) for item in (profile.get("decisionPolicy") or {}).get("unsupportedScenarioSignals", ["unsupported"])]
    if isinstance(diagnosis_payload, dict):
        for family, family_entries in (diagnosis_payload.get("familyData") or {}).items():
            if isinstance(family_entries, dict):
                for scenario_id, entry in family_entries.items():
                    unsupported_count = count_unsupported_replicas(entry if isinstance(entry, dict) else {})
                    if unsupported_count:
                        signals.append({"source": "diagnosis", "family": family, "scenarioId": scenario_id, "unsupportedReplicaCount": unsupported_count})
    if isinstance(reporting_manifest, dict):
        for family, entries in (reporting_manifest.get("familyData") or {}).items():
            if isinstance(entries, dict):
                for scenario_id, entry in entries.items():
                    status = str((entry or {}).get("status", ""))
                    if any(term in status for term in signal_terms):
                        signals.append({"source": "reporting", "family": family, "scenarioId": scenario_id, "status": status})
    return signals


def derive_completion_status(profile: Dict[str, Any], gates: List[Dict[str, Any]], provider_aware: bool, unsupported_signals: Optional[List[Dict[str, Any]]] = None) -> str:
    failed = [gate for gate in gates if not gate.get("passed")]
    policy = profile.get("decisionPolicy") or {}
    if not failed:
        if provider_aware and unsupported_signals and policy.get("allowUnsupportedScenariosWhenDocumented", True):
            return policy.get("completedWithUnsupportedScenariosStatus", "completed_with_unsupported_scenarios")
        return policy.get("completedStatus", "completed")
    failed_categories = {gate.get("category") for gate in failed}
    if "validation" in failed_categories or "provisioning" in failed_categories or "deployment" in failed_categories:
        return policy.get("failedValidationStatus", "failed_validation")
    if "benchmark" in failed_categories or "observability" in failed_categories or "diagnosis" in failed_categories:
        return policy.get("failedBenchmarkStatus", "failed_benchmark")
    if "reporting" in failed_categories:
        return policy.get("failedReportingStatus", "failed_reporting")
    return policy.get("notCompletedStatus", "not_completed")


def build_payload(
    profile: Dict[str, Any],
    repo_root: Path,
    args: argparse.Namespace,
    gates: List[Dict[str, Any]],
    diagnosis_reference: Dict[str, Any],
    reporting_reference: Dict[str, Any],
    source_gaps: List[Any],
    provider_aware: bool,
    cycle_reference: Optional[Dict[str, Any]] = None,
    unsupported_signals: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    passed_gate_count = sum(1 for gate in gates if gate.get("passed"))
    failed_gates = [gate["id"] for gate in gates if not gate.get("passed")]
    if args.dry_run:
        status = "dry_run"
        completed = False
    else:
        status = derive_completion_status(profile, gates, provider_aware, unsupported_signals)
        completed_statuses = {"completed", "completed_with_unsupported_scenarios", profile.get("decisionPolicy", {}).get("completedStatus"), profile.get("decisionPolicy", {}).get("completedWithUnsupportedScenariosStatus")}
        completed = status in completed_statuses and not failed_gates
    return {
        "completionProfile": profile,
        "completionGate": {
            "evaluationId": args.evaluation_id,
            "createdAtUtc": utc_now(),
            "status": status,
            "completed": bool(completed),
            "providerAware": provider_aware,
            "dryRun": bool(args.dry_run),
            "passedGateCount": passed_gate_count,
            "totalGateCount": len(gates),
            "failedGateIds": failed_gates,
            "unsupportedScenarioSignalCount": len(unsupported_signals or []),
        },
        "cycleReference": cycle_reference or {},
        "diagnosisReference": diagnosis_reference,
        "reportingReference": reporting_reference,
        "unsupportedScenarioSignals": unsupported_signals or [],
        "gates": gates,
        "sourceGaps": source_gaps,
    }


def build_text_summary(payload: Dict[str, Any]) -> str:
    gate = payload.get("completionGate", {})
    profile = payload.get("completionProfile", {})
    lines: List[str] = []
    lines.append("=============================================")
    lines.append(" Completion Gate")
    lines.append("=============================================")
    lines.append(f"Evaluation ID     : {gate.get('evaluationId')}")
    lines.append(f"Profile           : {profile.get('completionGateProfileId') or profile.get('profileId')}")
    lines.append(f"Cycle             : {(payload.get('cycleReference') or {}).get('cycleId') or profile.get('cycleId', 'NA')}")
    lines.append(f"Provider-aware    : {gate.get('providerAware')}")
    lines.append(f"Completion status : {gate.get('status')}")
    lines.append(f"Passed gates      : {gate.get('passedGateCount')}/{gate.get('totalGateCount')}")
    lines.append("")
    lines.append("Gates")
    lines.append("-----")
    for item in payload.get("gates", []):
        prefix = "PASS" if item.get("passed") else "FAIL"
        lines.append(f"- [{prefix}] {item.get('id')} :: {item.get('title')}")
        lines.append(f"  Category: {item.get('category')}")
        lines.append(f"  Implication: {item.get('implication')}")
        lines.append(f"  Evidence: {json.dumps(item.get('evidence'), ensure_ascii=False)}")
    lines.append("")
    if payload.get("unsupportedScenarioSignals"):
        lines.append("Unsupported scenario signals")
        lines.append("----------------------------")
        for signal in payload["unsupportedScenarioSignals"]:
            lines.append(f"- {json.dumps(signal, ensure_ascii=False)}")
        lines.append("")
    lines.append("Decision")
    lines.append("--------")
    if gate.get("completed"):
        lines.append("- The cycle satisfies the configured completion gate.")
    else:
        lines.append("- The cycle does not yet satisfy the configured completion gate.")
        for gate_id in gate.get("failedGateIds", []):
            lines.append(f"  * Failed gate: {gate_id}")
    lines.append("")
    lines.append("Source gaps")
    lines.append("-----------")
    gaps = payload.get("sourceGaps") or []
    if gaps:
        for gap in gaps:
            lines.append(f"- {gap}")
    else:
        lines.append("- No source gaps were reported by the selected diagnosis artifact.")
    return "\n".join(lines) + "\n"


def maybe_write_latest_aliases(profile: Dict[str, Any], output_json: Path, output_text: Path, payload: Dict[str, Any], summary: str, repo_root: Path) -> None:
    artifact_policy = profile.get("artifactPolicy") or {}
    if not artifact_policy.get("writeLatestAliases", False):
        return
    latest_manifest = repo_path(repo_root, artifact_policy.get("latestManifestPath"))
    latest_summary = repo_path(repo_root, artifact_policy.get("latestTextSummaryPath"))
    if latest_manifest:
        write_json(latest_manifest, payload)
    if latest_summary:
        write_text(latest_summary, summary)


def main() -> int:
    args = parse_args()
    profile_path = Path(args.profile_config).resolve()
    repo_root = infer_repo_root(profile_path, args.repo_root)
    profile = load_json(profile_path)
    if args.dry_run:
        pass
    evaluation_engine = str(profile.get("evaluationEngine") or profile.get("profileMode") or "").strip().lower()
    provider_aware = bool(profile.get("schemaVersion") == "completion-gate-profile/v1" or profile.get("completionGateProfileId"))
    if evaluation_engine in {"legacy_completion_gate", "historical_legacy_completion_gate", "legacy"}:
        provider_aware = False
    if provider_aware:
        payload = evaluate_provider_aware(profile, repo_root, args)
    else:
        if not args.diagnosis_json:
            raise SystemExit("--diagnosis-json is required for legacy completion gate profiles.")
        payload = evaluate_legacy(profile, repo_root, args)
    output_json = Path(args.output_json).resolve()
    output_text = Path(args.output_text).resolve()
    summary = build_text_summary(payload)
    write_json(output_json, payload)
    write_text(output_text, summary)
    maybe_write_latest_aliases(profile, output_json, output_text, payload, summary, repo_root)
    return 0 if payload.get("completionGate", {}).get("completed") or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
