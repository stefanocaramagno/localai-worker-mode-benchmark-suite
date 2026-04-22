#!/usr/bin/env python
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_METRIC_KEY = "mean_response_time_ms"


def load_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate whether the current exploratory characterization cycle can be considered completed.")
    parser.add_argument("--profile-config", required=True)
    parser.add_argument("--diagnosis-json", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-text", required=True)
    parser.add_argument("--evaluation-id", required=True)
    return parser.parse_args()


def add_gate(gates, gate_id, title, passed, evidence, implication):
    gates.append({
        "id": gate_id,
        "title": title,
        "passed": bool(passed),
        "evidence": evidence,
        "implication": implication,
    })




def count_unsupported_replicas(entry):
    """Read unsupported evidence only from the technical diagnosis payload.

    The completion gate must not rediscover raw ``*_unsupported.json`` artifacts
    from the filesystem. Unsupported scenarios are considered only if they have
    already been consolidated by the technical diagnosis step.
    """
    unsupported_summary = entry.get("unsupportedSummary") or {}
    if unsupported_summary:
        count = unsupported_summary.get("unsupportedReplicaCount")
        if count is not None:
            return int(count)

    unsupported_reports = entry.get("unsupportedReports") or []
    return len(unsupported_reports)


def scenario_is_accepted_unsupported(unsupported_count, minimum_unsupported_replicas):
    return unsupported_count >= int(minimum_unsupported_replicas)

def evaluate_family_coverage(profile, diagnosis_payload):
    coverage = diagnosis_payload.get("coverage", {})
    family_data = diagnosis_payload.get("familyData", {})
    required_families = profile["requiredFamilies"]
    min_replicas = int(profile["minimumReplicasPerScenario"])
    strict_coverage = bool(profile.get("strictScenarioCoverage", False))
    accept_unsupported_as_covered = bool(profile.get("acceptUnsupportedScenariosAsCovered", False))
    minimum_unsupported_replicas = int(profile.get("minimumUnsupportedReplicasPerScenario", min_replicas))

    per_family = {}
    all_passed = True

    for family_name in required_families:
        family_cov = coverage.get(family_name, {})
        family_entries = family_data.get(family_name, {})
        scenario_count = int(family_cov.get("scenarioCount", 0) or 0)
        scenarios_with_samples = int(family_cov.get("scenariosWithSamples", 0) or 0)
        sample_count = int(family_cov.get("sampleCount", 0) or 0)
        minimum_expected_samples = scenario_count * min_replicas

        scenarios_meeting_replica_gate = []
        scenarios_meeting_unsupported_gate = []
        scenarios_failing_replica_gate = []
        total_unsupported_replica_count = 0
        scenarios_with_accepted_unsupported = 0

        for scenario_id, entry in sorted(family_entries.items()):
            summary = entry.get("summary") or {}
            observed_samples = int(summary.get("sampleCount", 0) or 0)
            unsupported_replica_count = count_unsupported_replicas(entry)
            total_unsupported_replica_count += unsupported_replica_count

            if observed_samples >= min_replicas:
                scenarios_meeting_replica_gate.append(scenario_id)
                continue

            accepted_unsupported = accept_unsupported_as_covered and scenario_is_accepted_unsupported(unsupported_replica_count, minimum_unsupported_replicas)
            if accepted_unsupported:
                scenarios_meeting_unsupported_gate.append({
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

        family_passed = scenario_count > 0 and effective_evidence_count >= minimum_expected_evidence
        if strict_coverage:
            family_passed = family_passed and (scenarios_with_samples + scenarios_with_accepted_unsupported) == scenario_count and len(scenarios_failing_replica_gate) == 0
        else:
            family_passed = family_passed and (len(scenarios_meeting_replica_gate) + scenarios_with_accepted_unsupported) > 0

        per_family[family_name] = {
            "scenarioCount": scenario_count,
            "scenariosWithSamples": scenarios_with_samples,
            "scenariosWithAcceptedUnsupported": scenarios_with_accepted_unsupported,
            "sampleCount": sample_count,
            "unsupportedReplicaCount": total_unsupported_replica_count,
            "effectiveEvidenceCount": effective_evidence_count,
            "minimumExpectedSamples": minimum_expected_samples,
            "minimumExpectedEvidence": minimum_expected_evidence,
            "acceptUnsupportedScenariosAsCovered": accept_unsupported_as_covered,
            "minimumUnsupportedReplicasPerScenario": minimum_unsupported_replicas,
            "scenariosMeetingReplicaGate": scenarios_meeting_replica_gate,
            "scenariosMeetingUnsupportedGate": scenarios_meeting_unsupported_gate,
            "scenariosFailingReplicaGate": scenarios_failing_replica_gate,
            "passed": family_passed,
        }
        all_passed = all_passed and family_passed

    return all_passed, per_family


def evaluate_repeatability(profile, diagnosis_payload):
    family_data = diagnosis_payload.get("familyData", {})
    required_families = profile["requiredFamilies"]
    min_replicas = int(profile["minimumReplicasPerScenario"])
    max_cv = float(profile["maximumMeanResponseTimeCvPercent"])

    per_family = {}
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
                qualifying_scenarios.append({
                    "scenarioId": scenario_id,
                    "sampleCount": observed_samples,
                    "cvPercent": cv,
                })
            else:
                rejected_scenarios.append({
                    "scenarioId": scenario_id,
                    "sampleCount": observed_samples,
                    "cvPercent": cv,
                })

        passed = len(qualifying_scenarios) > 0
        per_family[family_name] = {
            "passed": passed,
            "qualifyingScenarios": qualifying_scenarios,
            "rejectedScenarios": rejected_scenarios,
        }
        all_passed = all_passed and passed

    return all_passed, per_family


def evaluate_findings(profile, diagnosis_payload):
    findings = diagnosis_payload.get("findings", [])
    finding_ids = {item.get("id") for item in findings}
    finding_count_gate = len(findings) >= int(profile["minimumFindings"])

    required_groups = profile.get("requiredFindingGroups", {})
    satisfied_groups = {}
    for group_name, expected_ids in required_groups.items():
        matched = [finding_id for finding_id in expected_ids if finding_id in finding_ids]
        satisfied_groups[group_name] = {
            "matchedFindingIds": matched,
            "passed": len(matched) > 0,
        }

    satisfied_group_count = sum(1 for item in satisfied_groups.values() if item["passed"])
    group_gate = satisfied_group_count >= int(profile["minimumFindingGroupsSatisfied"])

    return {
        "findingCount": len(findings),
        "minimumFindingsRequired": int(profile["minimumFindings"]),
        "findingCountGatePassed": finding_count_gate,
        "satisfiedGroupCount": satisfied_group_count,
        "minimumFindingGroupsSatisfied": int(profile["minimumFindingGroupsSatisfied"]),
        "groupGatePassed": group_gate,
        "groups": satisfied_groups,
    }


def evaluate_cluster_side(profile, diagnosis_payload):
    if not profile.get("requireClusterSideEvidence", False):
        return True, {
            "required": False,
            "gapPatterns": [],
            "matchedGaps": [],
        }

    gap_patterns = [str(item).lower() for item in profile.get("clusterSideGapPatterns", [])]
    gaps = diagnosis_payload.get("gaps", [])
    matched = []
    for gap in gaps:
        gap_text = str(gap).lower()
        for pattern in gap_patterns:
            if pattern in gap_text:
                matched.append(gap)
                break

    passed = len(matched) == 0
    return passed, {
        "required": True,
        "gapPatterns": gap_patterns,
        "matchedGaps": matched,
    }


def main():
    args = parse_args()
    profile = load_json(Path(args.profile_config))
    diagnosis_payload = load_json(Path(args.diagnosis_json))
    output_json = Path(args.output_json)
    output_text = Path(args.output_text)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_text.parent.mkdir(parents=True, exist_ok=True)

    diagnosis_meta = diagnosis_payload.get("diagnosis", {})
    diagnosis_status = diagnosis_meta.get("closureStatus")
    accepted_statuses = profile.get("acceptedDiagnosisClosureStatuses", [])
    diagnosis_gate_passed = diagnosis_status in accepted_statuses

    validation_gate_passed = bool(diagnosis_payload.get("validationSummaryAvailable"))

    families_gate_passed, family_coverage = evaluate_family_coverage(profile, diagnosis_payload)
    repeatability_gate_passed, repeatability = evaluate_repeatability(profile, diagnosis_payload)
    findings_eval = evaluate_findings(profile, diagnosis_payload)
    cluster_gate_passed, cluster_eval = evaluate_cluster_side(profile, diagnosis_payload)

    gates = []
    add_gate(
        gates,
        "validation_baseline_available",
        "La baseline di validazione minima è disponibile.",
        validation_gate_passed,
        {
            "validationSummaryAvailable": diagnosis_payload.get("validationSummaryAvailable"),
            "validationSummaryPath": diagnosis_payload.get("validationSummaryPath"),
        },
        "Il ciclo di caratterizzazione deve poggiare su una baseline funzionale salvata e non solo su benchmark pilota.",
    )
    add_gate(
        gates,
        "diagnosis_status_accepted",
        "La diagnosi tecnica preliminare ha uno stato di chiusura accettato.",
        diagnosis_gate_passed,
        {
            "diagnosisClosureStatus": diagnosis_status,
            "acceptedDiagnosisClosureStatuses": accepted_statuses,
        },
        "Il completamento può considerarsi dichiarabile solo se la diagnosi preliminare è già disponibile in forma strutturata.",
    )
    add_gate(
        gates,
        "family_coverage_complete",
        "Tutte le famiglie richieste hanno copertura sufficiente e repliche minime per scenario.",
        families_gate_passed,
        family_coverage,
        "La chiusura richiede copertura esplicita di worker-count, workload, models e placement.",
    )
    add_gate(
        gates,
        "repeatability_signal_present",
        "Ogni famiglia richiesta mostra almeno uno scenario con ripetibilità accettabile.",
        repeatability_gate_passed,
        repeatability,
        "Il completamento non può dirsi raggiunto se le evidenze raccolte sono solo episodiche o troppo rumorose.",
    )
    add_gate(
        gates,
        "minimum_findings_and_groups",
        "La diagnosi contiene un numero minimo di finding e copre abbastanza gruppi interpretativi.",
        findings_eval["findingCountGatePassed"] and findings_eval["groupGatePassed"],
        findings_eval,
        "La chiusura richiede almeno una prima lettura tecnica non banale dei benchmark, non solo raccolta grezza di numeri.",
    )
    add_gate(
        gates,
        "cluster_side_evidence_present",
        "Gli artefatti cluster-side non risultano mancanti nella diagnosi valutata.",
        cluster_gate_passed,
        cluster_eval,
        "Le evidenze infrastrutturali devono accompagnare i risultati client-side nella chiusura del ciclo.",
    )

    passed_gate_count = sum(1 for gate in gates if gate["passed"])
    failed_gates = [gate["id"] for gate in gates if not gate["passed"]]
    completed = len(failed_gates) == 0
    completion_status = "completed" if completed else "not_completed"

    payload = {
        "completionProfile": profile,
        "completionGate": {
            "evaluationId": args.evaluation_id,
            "createdAtUtc": datetime.now(timezone.utc).isoformat(),
            "status": completion_status,
            "completed": completed,
            "passedGateCount": passed_gate_count,
            "totalGateCount": len(gates),
            "failedGateIds": failed_gates,
        },
        "diagnosisReference": {
            "diagnosisJson": str(Path(args.diagnosis_json).resolve()),
            "diagnosisId": diagnosis_meta.get("diagnosisId"),
            "diagnosisClosureStatus": diagnosis_status,
            "familyScope": diagnosis_meta.get("familyScope"),
        },
        "gates": gates,
        "sourceGaps": diagnosis_payload.get("gaps", []),
    }
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = []
    lines.append("=============================================")
    lines.append(" Completion Gate")
    lines.append("=============================================")
    lines.append(f"Evaluation ID         : {args.evaluation_id}")
    lines.append(f"Diagnosis ID          : {diagnosis_meta.get('diagnosisId')}")
    lines.append(f"Diagnosis file        : {str(Path(args.diagnosis_json).resolve())}")
    lines.append(f"Completion status     : {completion_status}")
    lines.append(f"Passed gates          : {passed_gate_count}/{len(gates)}")
    lines.append("")
    lines.append("Gates")
    lines.append("-----")
    for gate in gates:
        prefix = "PASS" if gate["passed"] else "FAIL"
        lines.append(f"- [{prefix}] {gate['id']} :: {gate['title']}")
        lines.append(f"  Implicazione: {gate['implication']}")
        lines.append(f"  Evidenza: {json.dumps(gate['evidence'], ensure_ascii=False)}")
    lines.append("")
    lines.append("Decision")
    lines.append("--------")
    if completed:
        lines.append("- Il ciclo corrente può essere considerato completato secondo il profilo CG1.")
    else:
        lines.append("- Il ciclo corrente NON può ancora essere considerato completato secondo il profilo CG1.")
        if failed_gates:
            for gate_id in failed_gates:
                lines.append(f"  * Gate non superato: {gate_id}")
    lines.append("")
    lines.append("Source gaps from diagnosis")
    lines.append("--------------------------")
    source_gaps = diagnosis_payload.get("gaps", [])
    if source_gaps:
        for gap in source_gaps:
            lines.append(f"- {gap}")
    else:
        lines.append("- Nessun gap riportato nella diagnosi tecnica di origine.")
    output_text.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
