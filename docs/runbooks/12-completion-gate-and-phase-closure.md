# 12. Completion Gate and Phase Closure

## Objective

This runbook defines how to evaluate whether the current exploratory characterization cycle can be formally considered complete.

The purpose of the completion gate is to prevent premature phase closure based on partial execution, weak evidence, or incomplete analytical coverage.

This phase exists to answer a simple operational question:

> **Is the current benchmark campaign strong enough to justify moving from exploratory characterization to the next planned execution stage?**

The completion gate does not execute workload generation, Kubernetes deployment, smoke validation, or diagnosis logic by itself. Instead, it evaluates whether those upstream phases produced enough structured evidence to support a disciplined phase closure.

---

## Scope

This runbook covers:

- the role of the completion gate in the pipeline;
- the repository components involved in the evaluation;
- the prerequisites and expected inputs;
- the execution procedure for the completion-gate step;
- the meaning of each gate checked by the evaluation profile;
- the interpretation of `completed` versus `not_completed` outcomes;
- the correct decision process after the gate result is produced.

This runbook does **not** cover:

- cluster bootstrap and access validation;
- repository bootstrap;
- Kubernetes topology deployment;
- precheck and smoke validation;
- official baseline execution;
- exploratory load validation;
- pilot sweep execution;
- consolidated pilot benchmark execution;
- raw metrics collection;
- technical diagnosis generation.

Those phases are documented in separate runbooks and must already be complete before this runbook is used.

---

## When to Use This Runbook

Use this runbook only after all of the following conditions are true:

- the official baseline flow has already been executed successfully;
- the exploratory and pilot benchmark phases have already been completed for the families currently in scope;
- the consolidated pilot benchmark phase has already produced stable outputs;
- minimal validation outputs already exist;
- a technical diagnosis has already been generated;
- a formal go / no-go decision is required before advancing to the next execution phase.

This runbook belongs to the **post-execution phase-closure layer** of the pipeline.

---

## Governing Principle

A benchmark campaign is not complete merely because it has produced result files.

A campaign is considered complete only when it satisfies all of the following dimensions simultaneously:

- minimum validation evidence exists;
- the diagnosis phase is already available in a structured form;
- all required benchmark families are covered;
- replica coverage is sufficient, either through successful samples or through explicitly accepted unsupported evidence when the active completion-gate profile allows it;
- repeatability is not purely episodic;
- the diagnosis contains enough meaningful findings;
- cluster-side evidence is present and not missing from the diagnosis context.

The completion gate exists to enforce this principle explicitly.

When the profile is configured to do so, the gate may therefore distinguish between:

- scenarios that are simply missing from the evidence set;
- scenarios that produced valid benchmark samples;
- scenarios that were formally observed as `unsupported_under_current_constraints`.

Only the first case is always interpreted as missing coverage.

Its purpose is not to make the process bureaucratic. Its purpose is to ensure that the next stage of work is driven by validated evidence rather than by intuition or incomplete execution.

---

## Repository Components Involved

The completion-gate phase is driven by configuration, launcher scripts, and an analysis engine already present in the repository.

### Configuration

- `config/completion-gate/CG1.json`

This profile governs:

- output location;
- output suffixes;
- accepted diagnosis closure statuses;
- required benchmark families;
- strict family coverage behavior;
- minimum replicas per scenario;
- whether explicitly unsupported scenarios may still satisfy scenario coverage;
- the minimum number of unsupported replica evidences required when that behavior is enabled;
- maximum allowed coefficient of variation for mean response time;
- minimum number of findings required in the technical diagnosis;
- required finding groups and group coverage expectations;
- cluster-side evidence requirements.

### Launchers

- `scripts/load/post/Start-CompletionGate.ps1`
- `scripts/load/post/start-completion-gate.sh`

These launchers:

- resolve repository paths;
- load the active completion-gate profile;
- locate the latest diagnosis file when not explicitly provided;
- generate a new evaluation identifier;
- invoke the completion-gate analysis script;
- write machine-readable and operator-readable outputs.

### Analysis Script

- `scripts/analysis/evaluate-completion-gate.py`

This script performs the actual evaluation and emits:

- a structured JSON manifest;
- a human-readable text summary.

### Upstream Artifacts Consumed

The completion gate depends on outputs already generated by earlier phases, especially:

- technical diagnosis JSON generated by the diagnosis phase;
- validation summary referenced inside the diagnosis;
- consolidated pilot benchmark outputs referenced inside the diagnosis;
- family coverage and repeatability signals derived from the diagnosis payload;
- cluster-side evidence coverage represented in the diagnosis gaps list;

### Coverage Semantics for Unsupported Scenarios

In the current repository version, a scenario does not contribute to family coverage only through successful benchmark samples.

When the active completion-gate profile explicitly enables unsupported-aware coverage semantics, a scenario may also be considered covered if all of the following conditions are true:

- the scenario is explicitly classified upstream as `unsupported_under_current_constraints`;
- the unsupported status is represented through structured diagnosis fields rather than informal notes;
- the minimum number of unsupported replica evidences required by the profile is satisfied according to the technical diagnosis payload consumed by the gate.

This rule exists to avoid treating structurally unsupported scenarios as if they were merely missing or forgotten executions.

It does **not** mean that unsupported scenarios are reinterpreted as successful benchmark samples.

It means only that, for phase-closure purposes, those scenarios may satisfy the **coverage** dimension when the profile is configured to accept them as formally observed outcomes under the current execution constraints.

### Output Directory

The active profile writes results under:

- `results/completion-gate`

---

## Completion-Gate Profile: `CG1`

The active phase-closure profile is `CG1`.

Its purpose is to declare whether the current exploratory characterization cycle can be considered completed after validation, consolidated pilot coverage, repeatability evidence, and a first structured technical diagnosis.

Key characteristics of `CG1` include:

- output root: `results/completion-gate`
- manifest suffix: `_completion_gate.json`
- text suffix: `_completion_gate.txt`
- accepted diagnosis closure status:
  - `preliminary_diagnosis_available`
- required families:
  - `worker-count`
  - `workload`
  - `models`
  - `placement`
- strict scenario coverage: enabled
- minimum replicas per scenario: `2`
- maximum mean response-time coefficient of variation: `35%`
- minimum number of findings: `3`
- minimum finding groups satisfied: `2`
- cluster-side evidence required: yes

This means the completion gate is intentionally conservative. It does not only ask whether benchmarks were run. It asks whether the execution campaign is analytically usable.

---

## Preconditions

Before running the completion gate, verify that all of the following conditions are already satisfied.

### Functional Preconditions

- the baseline run has already completed successfully;
- the relevant sweep families have already been executed;
- the consolidated pilot benchmark phase has already produced results;
- the technical diagnosis phase has already completed.

### Artifact Preconditions

- a diagnosis JSON exists under `results/diagnosis` or is available at a known path;
- the diagnosis was generated from the current benchmark cycle, not from an older unrelated campaign;
- the diagnosis references valid validation and benchmark artifacts;
- consolidated family outputs exist for all families required by `CG1`;
- diagnosis outputs are internally readable and not malformed.

### Quality Preconditions

- the execution protocol remained stable across scenarios;
- no known fatal anomaly invalidates the benchmark campaign globally;
- any scenario-level failures are already documented and reflected in the diagnosis;
- the diagnosis gaps, if present, are understood before attempting closure.

If these conditions are not satisfied, the completion gate may still run, but the resulting decision will likely be `not_completed`.

---

## Inputs Expected by the Completion Gate

The completion gate consumes the diagnosis JSON as its primary input.

That diagnosis JSON must already include or reference enough information to support evaluation of:

- validation-summary availability;
- diagnosis closure status;
- family coverage;
- sample counts per scenario;
- repeatability summaries;
- finding count and finding groups;
- source gaps indicating missing cluster-side evidence.

In practice, the completion gate is **diagnosis-driven**. This means the technical diagnosis phase must already have transformed the raw benchmark campaign into structured analytical metadata.

---

## Gate Logic Evaluated by `CG1`

The completion gate evaluates six explicit gates.

### 1. Validation Baseline Availability

This gate checks whether a minimal validation summary is available.

Why it matters:

- the campaign must be anchored to a saved validation baseline;
- phase closure cannot rely only on pilot benchmark outputs.

### 2. Accepted Diagnosis Status

This gate checks whether the diagnosis closure status belongs to the set accepted by the profile.

For `CG1`, the accepted status is:

- `preliminary_diagnosis_available`

Why it matters:

- phase closure is allowed only if a structured diagnosis already exists.

### 3. Family Coverage Completeness

This gate checks whether all required families are covered with enough scenario-level samples.

For `CG1`, the required families are:

- `worker-count`
- `workload`
- `models`
- `placement`

With strict family coverage enabled, the gate requires:

- every required family to exist;
- every scenario in each family to have samples;
- every scenario to satisfy the minimum replica gate.

Why it matters:

- the phase cannot be considered complete if a required family is partially executed or under-sampled.

### 4. Repeatability Signal Presence

This gate checks whether each required family has at least one qualifying scenario whose mean response time coefficient of variation remains within the profile threshold.

For `CG1`:

- minimum replicas per scenario: `2`
- maximum allowed CV for mean response time: `35%`

Why it matters:

- a campaign cannot be closed if every family is purely noisy or episodic.

### 5. Minimum Findings and Finding-Group Coverage

This gate checks two things simultaneously:

- whether the diagnosis contains at least the minimum number of findings;
- whether enough interpretative finding groups are satisfied.

For `CG1`:

- minimum findings: `3`
- minimum finding groups satisfied: `2`

The configured finding groups are:

- `worker_count_signal`
  - `worker_count_initial_gain`
  - `worker_count_diminishing_returns`
- `workload_stress_signal`
  - `workload_saturation_signal`
- `model_penalty_signal`
  - `model_size_penalty`
- `placement_signal`
  - `placement_effect`

Why it matters:

- closure requires more than raw measurements;
- it requires a minimum level of structured technical interpretation.

### 6. Cluster-Side Evidence Presence

This gate checks whether the diagnosis gaps indicate missing cluster-side evidence.

For `CG1`, cluster-side evidence is mandatory.

Why it matters:

- client-side benchmark metrics alone are not enough for disciplined phase closure;
- the campaign must include infrastructure-facing evidence as well.

---

## Expected Outputs

The completion-gate phase produces two artifacts.

### JSON Manifest

A structured file written under:

- `results/completion-gate/*_completion_gate.json`

This file contains:

- the active completion profile;
- the evaluation identifier;
- the completion status;
- the total and passed gate counts;
- failed gate identifiers;
- diagnosis reference metadata;
- detailed evidence for each gate;
- the source gaps inherited from the diagnosis.

### Text Summary

A human-readable file written under:

- `results/completion-gate/*_completion_gate.txt`

This file summarizes:

- evaluation ID;
- diagnosis ID;
- diagnosis file path;
- completion status;
- passed versus total gates;
- gate-by-gate pass/fail status;
- the practical decision statement;
- source gaps reported by the diagnosis.

---

## Execution Procedure

### PowerShell

Run the completion gate from the repository root or by using the script path explicitly.

Example:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-CompletionGate.ps1" `
  -ProfileConfig .\config\completion-gate\CG1.json `
  -DiagnosisJson .\results\diagnosis\<diagnosis-file>.json
```

If `-DiagnosisJson` is omitted, the launcher attempts to locate the latest diagnosis file whose `familyScope` is `all`.

Dry-run mode is also available:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-CompletionGate.ps1" `
  -ProfileConfig .\config\completion-gate\CG1.json `
  -DryRun
```

### Bash

Example:

```bash
bash ./scripts/load/post/start-completion-gate.sh \
  --profile-config ./config/completion-gate/CG1.json \
  --diagnosis-json ./results/diagnosis/<diagnosis-file>.json
```

If `--diagnosis-json` is omitted, the launcher attempts to locate the latest diagnosis file with `familyScope = all`.

Dry-run mode is also available:

```bash
bash ./scripts/load/post/start-completion-gate.sh \
  --profile-config ./config/completion-gate/CG1.json \
  --dry-run
```

---

## Recommended Operator Workflow

Use the following order.

1. Confirm that the diagnosis phase has already completed successfully.
2. Confirm that the diagnosis corresponds to the current benchmark campaign.
3. Confirm that all required consolidated pilot families are present.
4. Run the completion gate.
5. Inspect the text summary first.
6. Inspect the JSON manifest when one or more gates fail.
7. Decide whether to:
   - close the current phase;
   - rerun missing families;
   - improve repeatability;
   - regenerate diagnosis after collecting missing evidence.

---

## How to Interpret the Result

### `completed`

If the completion status is `completed`, it means:

- all configured gates passed;
- the diagnosis status is acceptable;
- family coverage is sufficient;
- repeatability is strong enough under the profile rules;
- the diagnosis contains enough meaningful findings;
- cluster-side evidence is not flagged as missing.

This does **not** mean the project is complete.

It means only that the **current exploratory characterization cycle** can be considered closed according to `CG1`.

### `not_completed`

If the completion status is `not_completed`, it means at least one required condition was not satisfied.

Typical causes include:

- missing or incomplete family coverage;
- too few replicas per scenario;
- repeatability too weak;
- insufficient findings;
- diagnosis status not accepted;
- cluster-side evidence gaps still present.

This outcome should be treated as an operational signal, not as a failure of the project itself.

It simply means that the current evidence set is not yet strong enough to justify disciplined phase closure.

---

## Typical Failure Scenarios and Their Meaning

### Failure: `validation_baseline_available`

Meaning:

- the minimal validation summary is missing or not reachable from the diagnosis context.

Action:

- regenerate the validation summary;
- confirm that the diagnosis references the correct validation artifacts.

### Failure: `diagnosis_status_accepted`

Meaning:

- the diagnosis closure status is not in the accepted status set for `CG1`.

Action:

- revisit the diagnosis phase;
- verify that the diagnosis was generated from enough valid upstream artifacts.

### Failure: `family_coverage_complete`

Meaning:

- one or more required families are missing, incomplete, or under-sampled;
- or one or more scenarios expected to count as unsupported-aware coverage do not yet have enough structured unsupported replica evidence under the active profile.

Action:

- rerun the missing or insufficient consolidated benchmark family;
- verify strict scenario coverage expectations;
- verify whether the active completion-gate profile is configured to accept unsupported scenarios as covered outcomes;
- if unsupported-aware coverage is enabled, verify that the technical diagnosis payload contains sufficient structured unsupported replica evidence for the affected scenarios under the active profile.

### Failure: `repeatability_signal_present`

Meaning:

- one or more families do not contain at least one qualifying repeatable scenario.

Action:

- rerun the affected family with stricter execution control;
- verify warm-up consistency and replica stability;
- inspect cluster pressure during the affected scenarios.

### Failure: `minimum_findings_and_groups`

Meaning:

- the diagnosis is too poor analytically, either because it contains too few findings or because the findings do not cover enough interpretative groups.

Action:

- improve benchmark coverage;
- improve cluster-side evidence quality;
- regenerate diagnosis after the evidence set becomes richer.

### Failure: `cluster_side_evidence_present`

Meaning:

- the diagnosis indicates missing cluster-side evidence.

Action:

- collect or restore cluster-side artifacts for the affected runs;
- regenerate diagnosis before rerunning the completion gate.

---

## Phase Closure Decision Rules

Use the following decision logic.

### Close the Current Phase

Close the current exploratory characterization cycle only when:

- completion status is `completed`;
- no failed gates remain;
- diagnosis text and JSON are archived with the benchmark outputs;
- the team agrees that the current evidence set is sufficient for the next phase.

### Do Not Close the Current Phase

Do not close the phase when:

- completion status is `not_completed`;
- one or more required families remain weak or incomplete;
- the diagnosis lacks enough evidence;
- cluster-side evidence is still missing.

In this case, the correct action is not to bypass the gate, but to strengthen the campaign and rerun the gate later.

---

## Recommended Actions After Gate Evaluation

### If the Gate Passes

Recommended next actions:

1. archive the gate outputs;
2. mark the exploratory characterization cycle as completed internally;
3. select the next focused extension path;
4. proceed to the next planned execution phase under controlled scope.

Typical next-phase directions may include:

- deeper model comparison;
- more refined placement analysis;
- richer workload patterns;
- transition toward the next characterization or orchestration stage.

### If the Gate Fails

Recommended next actions:

1. identify the failed gate IDs from the text or JSON output;
2. map each failed gate back to its upstream phase;
3. rerun only the missing or weak parts of the campaign;
4. regenerate technical diagnosis;
5. rerun the completion gate.

---

## Troubleshooting

### The launcher cannot find a diagnosis file automatically

Cause:

- `results/diagnosis` does not contain a diagnosis file with `familyScope = all`;
- or the latest diagnosis file is malformed.

Resolution:

- provide `-DiagnosisJson` or `--diagnosis-json` explicitly;
- verify that the diagnosis phase completed successfully.

### The gate returns `not_completed` even though many artifacts exist

Cause:

- artifact existence alone does not satisfy the profile;
- strict family coverage, repeatability, or finding-group constraints may still be failing.

Resolution:

- inspect the JSON manifest;
- identify which gate IDs failed;
- address the specific upstream weakness.

### Cluster-side evidence is reported as missing even though some cluster files exist

Cause:

- the diagnosis may still contain cluster-side gap markers;
- the expected evidence may be incomplete, misnamed, or missing for some scenarios.

Resolution:

- verify the cluster-side collection phase for the affected scenarios;
- regenerate the diagnosis after the missing evidence has been restored.

### The completion gate passes, but the campaign still feels weak

Cause:

- the profile checks minimum closure conditions, not absolute scientific sufficiency.

Resolution:

- treat `completed` as a formal phase-closure signal, not as a prohibition against deeper follow-up work;
- extend the campaign only in a controlled, data-driven way.

---

## Criteria for Success

This runbook has been executed successfully when all of the following are true:

- the completion-gate launcher executed without error;
- a JSON manifest was created under `results/completion-gate`;
- a text summary was created under `results/completion-gate`;
- the completion status was reviewed by the operator;
- the next action was chosen explicitly based on the gate result.

---

## Phase Closure Recordkeeping

When the completion gate is used as an official closure step for the current execution cycle, preserve at least the following:

- completion-gate JSON manifest;
- completion-gate text summary;
- referenced diagnosis JSON;
- validation summary used by the diagnosis;
- consolidated pilot result roots used in the diagnosis;
- any operator notes explaining the final decision.

This ensures that the phase-closure decision remains auditable and repeatable.

---

## Next Step

- If the completion status is `completed`, proceed to the next controlled execution phase.
- If the completion status is `not_completed`, return to the upstream phase indicated by the failed gate and strengthen the evidence before reevaluating closure.
