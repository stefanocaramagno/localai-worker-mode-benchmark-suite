# 11. Technical Diagnosis

## Objective

This runbook defines how to generate the first evidence-based technical diagnosis after consolidated pilot benchmark execution.

The goal of this phase is to transform validated benchmark outputs into an initial technical interpretation of the system behavior observed across the pilot sweep families.

This diagnosis is not intended to serve as a final architectural conclusion. Its purpose is to:

- identify plausible bottlenecks;
- surface repeatable performance patterns;
- correlate client-side degradation with cluster-side pressure signals;
- determine whether the current execution campaign is strong enough to support phase closure;
- provide a structured basis for the next experimental decision.

This runbook applies only after the benchmark execution and validation layers have already produced stable artifacts.

---

## When to Use This Runbook

Use this runbook when all the following conditions are true:

- the official baseline flow has already been executed successfully;
- the consolidated pilot benchmark campaign has already been completed, at least for the benchmark families currently in scope;
- minimal validation outputs already exist;
- client-side metrics have already been collected and preserved;
- cluster-side evidence has already been collected and preserved;
- a first structured interpretation is required before moving to completion-gate evaluation.

This runbook belongs to the post-execution analytical layer of the pipeline.

---

## Scope

This runbook covers:

- the role of the technical diagnosis phase;
- the repository components involved in automatic diagnosis generation;
- prerequisites and expected inputs;
- the execution procedure for generating diagnosis artifacts;
- the structure and interpretation of diagnosis outputs;
- the meaning of the automatically produced findings and family-level judgments;
- the correct use of diagnosis outputs in the wider pipeline.

This runbook does **not** cover:

- cluster bootstrap and access validation;
- repository bootstrap;
- Kubernetes deployment mechanics;
- precheck and smoke validation;
- official baseline execution;
- exploratory validation;
- pilot sweep execution;
- consolidated benchmark execution;
- raw metrics collection;
- completion-gate evaluation.

Those phases are documented in separate runbooks.

---

## Governing Principle

A benchmark campaign is not operationally useful only because it produced CSV files.

A campaign becomes analytically useful when the collected evidence can be translated into a structured explanation of what the system is actually doing.

The technical diagnosis phase exists to answer questions such as:

- Is the first increase in worker count beneficial in the current cluster?
- Are additional workers producing diminishing returns?
- Is a heavier workload pushing the system toward saturation?
- Is model size acting as the dominant latency driver?
- Does placement materially affect the observed behavior?
- Is there cluster-side CPU or memory pressure that supports the interpretation?

This phase is intentionally conservative. It produces a **preliminary, evidence-based diagnosis**, not a final design truth.

### Unsupported-Aware Evidence Semantics

In the current repository version, the diagnosis phase is not limited to successful benchmark samples.

A scenario may contribute evidence to the diagnosis in one of two different ways:

- through measurable benchmark samples derived from `*_stats.csv`;
- through structured unsupported evidence derived from `*_unsupported.json`, when the scenario was explicitly classified upstream as `unsupported_under_current_constraints`.

These two evidence types are **not equivalent**:

- successful benchmark samples contribute quantitative performance measurements;
- unsupported artifacts contribute structured operational evidence that the scenario was observed but could not be executed successfully under the current constraints.

The diagnosis therefore distinguishes between:

- scenarios with measurable samples;
- scenarios with unsupported evidence;
- scenarios with no evidence at all.

Only the third case is interpreted as a genuinely missing execution from the diagnosis perspective.

---

## Repository Components Involved

The technical diagnosis phase is driven by configuration and analysis components already present in the repository.

### Configuration

- `config/technical-diagnosis/TD1.json`

This profile governs:

- diagnosis output location;
- diagnosis file naming conventions;
- target request type and request name;
- fallback behavior to aggregated Locust rows;
- consolidated pilot result roots;
- scenario configuration roots;
- thresholds used to trigger strong diagnostic findings and weaker family-level judgments;
- minimum evidence requirements for preliminary diagnosis closure;
- whether explicitly unsupported scenarios may still count as observed evidence in diagnosis coverage semantics;
- the minimum number of unsupported replica artifacts required when that behavior is enabled.

### Analysis Script

- `scripts/analysis/generate-technical-diagnosis.py`

This script reads benchmark outputs, inspects the relevant metrics, computes per-family summaries, and emits both machine-readable and operator-readable diagnosis artifacts.

### Upstream Artifacts Consumed

The diagnosis phase depends on outputs produced earlier in the pipeline, especially:

- `results/validation/b0-summary.json`
- consolidated benchmark outputs under:
  - `results/pilot/consolidated/worker-count`
  - `results/pilot/consolidated/workload`
  - `results/pilot/consolidated/models`
  - `results/pilot/consolidated/placement`
- client-side Locust CSV artifacts;
- structured `*_unsupported.json` artifacts generated when a scenario is classified as `unsupported_under_current_constraints`;
- cluster-side post-run evidence such as:
  - `*_cluster_post_top-nodes.txt`
  - other cluster-side snapshots collected during benchmark execution

### Output Directory

The diagnosis profile writes results under:

- `results/diagnosis`

---

## Preconditions

Before running the technical diagnosis, verify that all the following conditions are satisfied.

### Functional Preconditions

- the workload under test has already been proven functionally reachable;
- the official baseline has already been executed successfully;
- the consolidated benchmark campaign has already produced artifacts for at least part of the family set in scope.

### Artifact Preconditions

- validation summary is present;
- consolidated pilot result directories contain measurement artifacts;
- Locust statistics files are available;
- scenario metadata is available under `config/scenarios/pilot/...`;
- cluster-side evidence has been collected for the same runs whenever possible.

### Quality Preconditions

- the benchmark campaign has already passed the minimum operational validity checks;
- the scenario identifiers used in the results align with the scenario configuration files;
- the execution protocol remained stable across replicas;
- no unresolved fatal anomaly invalidates the campaign being diagnosed.

If these conditions are not met, the diagnosis phase may still run, but the resulting findings and family-level judgments will be weak, incomplete, or explicitly gap-dominated.

---

## Diagnosis Profile: `TD1`

The active diagnosis profile is `TD1`.

Its purpose is to generate an **initial technical diagnosis aligned with the consolidated pilot benchmark campaign**.

Key characteristics of the profile include:

- output root: `results/diagnosis`
- diagnosis manifest suffix: `_diagnosis.json`
- diagnosis text suffix: `_diagnosis.txt`
- target request type: `POST`
- target request name: `POST /v1/chat/completions`
- fallback to aggregated rows when a request-specific row is unavailable
- family roots mapped to the four pilot benchmark families
- scenario roots mapped to the corresponding pilot scenario definitions
- pressure and pattern thresholds used to emit strong findings and weaker family-level judgments
- minimum coverage and finding counts required to classify the diagnosis as preliminarily available

This means the diagnosis logic is not arbitrary. It is explicitly profile-driven and therefore reproducible.

---

## Diagnostic Families in Scope

The diagnosis engine is designed around the four consolidated pilot benchmark families:

- `worker-count`
- `workload`
- `models`
- `placement`

Each family is interpreted through its own logic.

### Worker Count Family

The engine looks for signals such as:

- initial improvement when moving from one worker to two workers;
- diminishing returns when increasing the worker count beyond the best observed configuration.

### Workload Family

The engine looks for signals such as:

- meaningful latency increase under higher stress;
- cases in which increased load does not produce proportionate throughput gains.

### Models Family

The engine looks for signals such as:

- large latency penalties when moving from smaller to larger models;
- evidence that model size dominates over more subtle topology effects.

### Placement Family

The engine looks for signals such as:

- material latency differences between distributed and co-located worker placement;
- whether inter-node overhead or local contention appears more dominant in the current cluster.

### Cross-Family Cluster Pressure

Across all families, the engine also inspects cluster-side node pressure to determine whether:

- CPU pressure was materially high;
- memory pressure was materially high.

---

## Inputs Required by the Diagnosis Phase

The diagnosis process depends on a fixed input set.

### Mandatory Inputs

At minimum, the following should exist:

- diagnosis profile file: `config/technical-diagnosis/TD1.json`
- validation summary: `results/validation/b0-summary.json`
- benchmark outputs for at least one family in `results/pilot/consolidated/...`
- scenario definitions under `config/scenarios/pilot/...`

### Strongly Recommended Inputs

To make the diagnosis materially useful, the following should also exist:

- replicated scenario runs for each family in scope;
- request-specific Locust statistics rows for `POST /v1/chat/completions`;
- cluster-side post-run node utilization evidence;
- cluster-side evidence for pod placement, readiness, and restart state.

### Optional but Beneficial Inputs

- validation summaries from previous reruns;
- statistical-rigor outputs confirming stability;
- notes describing known anomalies during execution.

---

## Output Produced by the Diagnosis Phase

The diagnosis script produces two output files.

### 1. Diagnosis Manifest (`.json`)

This is the machine-readable artifact.

It contains:

- the diagnosis profile used;
- diagnosis metadata;
- validation summary path and contents when available;
- per-family coverage overview;
- per-scenario sample summaries;
- automatically generated findings;
- family-level judgments for each diagnostic family;
- explicit gaps.

This file is intended for structured review and downstream automation.

### 2. Diagnosis Report (`.txt`)

This is the operator-readable artifact.

It contains:

- diagnosis ID;
- family scope;
- closure status;
- coverage summary;
- human-readable findings;
- human-readable family-level judgments;
- per-family scenario averages;
- identified gaps.

This file is intended for direct inspection during pipeline review.

---

## Recommended Naming Convention

Use a diagnosis identifier that is unique, stable, and tied to a specific campaign.

A recommended pattern is:

```text
TD1_<scope>_<timestamp>
```

Examples:

```text
TD1_all_<YYYYMMDDThhmmssZ>
TD1_worker-count_<YYYYMMDDThhmmssZ>
TD1_models_<YYYYMMDDThhmmssZ>
```

In practice, the current launcher generates this timestamp automatically at execution time. The timestamp must therefore reflect the actual execution instant of the diagnosis command, not a fixed example date copied from the documentation.

The important requirement is that the diagnosis ID allow you to trace the diagnosis back to a known benchmark campaign and artifact set.

---

## Execution Procedure

## Step 1 — Confirm the Upstream Campaign Is Ready

Before running the diagnosis script, verify that:

- the consolidated pilot benchmarks already produced outputs;
- the validation summary exists;
- the family directories contain measurement results;
- cluster-side artifacts were collected for the runs under review.

Do **not** generate a diagnosis over a partially executed or obviously broken campaign unless the objective is to explicitly document its gaps.

---

## Step 2 — Choose the Scope

The diagnosis script supports either:

- full-scope diagnosis (`all`), or
- diagnosis restricted to one family:
  - `worker-count`
  - `workload`
  - `models`
  - `placement`

### Recommended Default

Use full-scope diagnosis for phase review:

```text
all
```

Use per-family diagnosis only when:

- one family was rerun independently;
- one family needs focused debugging;
- the full consolidated campaign is not yet available.

---

## Step 3 — Choose the Output Strategy

The recommended operational path is to use the dedicated diagnosis launcher scripts already provided by the repository.

The launchers automatically:

- resolve the repository root;
- load the active diagnosis profile;
- generate a fresh UTC-based diagnosis identifier at execution time;
- build the output paths consistently;
- invoke the Python analysis engine with the correct arguments.

As a result, the preferred approach is launcher-driven rather than calling the Python analysis script manually. This also avoids shell-specific ambiguity around whether the local environment exposes `python` or `python3`, because the launcher handles interpreter resolution according to the repository implementation.

---

## Step 4 — Run the Diagnosis Launcher

From the repository root, invoke the launcher that matches your shell environment.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-TechnicalDiagnosis.ps1" `
  -ProfileConfig .\config\technical-diagnosis\TD1.json `
  -Family all
```

### Linux / macOS / WSL

```bash
bash ./scripts/load/post/start-technical-diagnosis.sh \
  --profile-config ./config/technical-diagnosis/TD1.json \
  --family all
```

If you want to scope the diagnosis to a single family, pass the desired family explicitly.

### Example: Family-Scoped Diagnosis

#### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-TechnicalDiagnosis.ps1" `
  -ProfileConfig .\config\technical-diagnosis\TD1.json `
  -Family placement
```

#### Linux / macOS / WSL

```bash
bash ./scripts/load/post/start-technical-diagnosis.sh \
  --profile-config ./config/technical-diagnosis/TD1.json \
  --family placement
```

The launcher generates a fresh diagnosis ID and output file names automatically at execution time, which avoids hard-coded historical timestamps and keeps the naming convention aligned with the current repository workflow.

---

## Step 5 — Verify Output Generation

After execution, verify that both files exist:

- diagnosis manifest (`.json`)
- diagnosis text report (`.txt`)

Then open the text report and confirm that it contains at least:

- diagnosis ID;
- family scope;
- closure status;
- coverage overview;
- finding section;
- family-level judgments section;
- gap section.

If one of these sections is missing, treat the diagnosis generation as incomplete.

---

## Step 6 — Review the Closure Status

The script emits a closure classification in the diagnosis payload.

### Expected Values

- `preliminary_diagnosis_available`
- `not_enough_data`

### Meaning

#### `preliminary_diagnosis_available`

This means the minimum data threshold for a first diagnosis was met.

In practical terms, the script found:

- enough family coverage, and
- enough strong findings

according to the thresholds defined in the diagnosis profile. Family-level judgments may still be emitted even when a family does not produce a strong finding.

#### `not_enough_data`

This means the benchmark evidence is still insufficient for a meaningful first diagnosis.

Typical causes include:

- missing validation summary;
- missing consolidated run outputs;
- missing family coverage;
- insufficient measurable samples;
- no cluster-side pressure evidence.

This status does **not** necessarily mean the benchmark campaign failed. It means the diagnosis layer cannot yet support interpretation strongly enough.

---

## How the Diagnosis Engine Builds Findings and Family-Level Judgments

The diagnosis generator does not guess arbitrarily. It applies explicit threshold-based logic to the artifacts already present in the repository.

The output layer now distinguishes between two interpretative levels:

- **strong findings**, emitted when the observed signal crosses the configured diagnostic threshold strongly enough to justify a dominant interpretation;
- **family-level judgments**, emitted for every diagnostic family so that a family is never left completely silent after analysis.

A family-level judgment may therefore state that the family shows:

- a **strong signal** consistent with a strong finding;
- a **weak signal**, meaning that the family was analyzed but the observed effect is not strong enough to justify a dominant finding;
- **insufficient evidence**, meaning that the family was only partially observable or does not yet support a stable interpretation.

This distinction exists to avoid two opposite problems:

- over-claiming strong conclusions where the data do not justify them;
- leaving an analyzed family without any explicit interpretative summary.

Below is the operational meaning of the major strong-finding categories. Family-level judgments should be interpreted alongside them, not as a replacement for them.

## `validation_baseline_ready`

Emitted when a validation summary is available.

### Meaning

The benchmark pipeline starts from a functionally verified service and not from a purely theoretical deployment.

### Why it matters

Without this finding, later performance interpretation is weaker because the foundation itself may not be trusted.

---

## `worker_count_initial_gain`

Emitted when increasing the worker count from the first worker-count scenario to the next one yields a meaningful mean-latency improvement above the configured threshold.

### Meaning

The current cluster can benefit from a first increase in worker parallelism.

### Practical interpretation

This suggests that the original one-worker configuration is not already optimal and that some part of the bottleneck is mitigated by additional distributed computation.

---

## `worker_count_diminishing_returns`

Emitted when the best observed worker-count scenario is followed by larger configurations that provide no material improvement or show mild regression, within the configured threshold.

### Meaning

Beyond the best observed worker count, additional workers may not justify their coordination overhead.

### Practical interpretation

This often indicates one of the following:

- synchronization overhead;
- node-level resource pressure;
- network overhead;
- insufficient cluster capacity to support the added parallelism effectively.

---

## `workload_saturation_signal`

Emitted when a higher workload scenario increases mean latency beyond the configured stress threshold.

### Meaning

The system becomes materially more fragile as load intensity rises.

### Practical interpretation

This is a strong signal that the cluster or application topology is approaching saturation.

---

## `model_size_penalty`

Emitted when the larger-model family exhibits a latency increase beyond the configured penalty threshold.

### Meaning

Model size is acting as a dominant performance driver in the current cluster.

### Practical interpretation

On a CPU-only or otherwise constrained cluster, model choice may dominate more subtle topology choices.

---

## `placement_effect`

Emitted when the distributed and co-located placement scenarios differ enough to cross the configured placement threshold.

### Meaning

Worker placement has a measurable effect on performance in the current topology.

### Practical interpretation

Depending on which side is better, this may suggest either:

- local contention dominates, or
- inter-node coordination dominates.

Interpret this finding in the context of your placement policy, including any fixed server placement constraints already defined in the project.

---

## `cluster_cpu_pressure`

Emitted when cluster-side node utilization indicates high CPU pressure during the analyzed campaign.

### Meaning

At least some observed degradation may have an infrastructure-side CPU explanation.

### Practical interpretation

This strengthens the diagnosis when latency and throughput behavior are consistent with CPU saturation.

---

## `cluster_memory_pressure`

Emitted when cluster-side node utilization indicates high memory pressure during the analyzed campaign.

### Meaning

Memory may be contributing to degraded behavior in at least some scenarios.

### Practical interpretation

This is especially relevant when heavier models or more aggressive local co-location strategies are being tested.

---

## Coverage Interpretation

The diagnosis report includes a per-family coverage overview.

For each family, review at least:

- number of configured scenarios;
- number of scenarios with measurable samples;
- total number of samples discovered;
- results root used by the diagnosis engine.

### What Good Coverage Looks Like

A family is in good diagnostic shape when:

- most or all configured scenarios contain measurable samples;
- each scenario has the expected replica count;
- metrics can be read from request-specific or accepted aggregated Locust rows;
- cluster-side evidence exists for the same runs.

### What Poor Coverage Looks Like

A family is diagnostically weak when:

- the directory exists but contains no measurable samples;
- scenario identifiers do not align with configuration files;
- only one or two fragmented artifacts are present;
- cluster-side evidence is missing entirely.

---

## Gap Interpretation

The diagnosis generator explicitly reports gaps.

These gaps must be reviewed carefully because they explain why a diagnosis may be incomplete or weak.

Common gap examples include:

- missing validation summary;
- no measurable samples for one or more families;
- absence of cluster-side evidence;
- incomplete campaign coverage.

### Rule

A diagnosis with several gaps can still be useful, but it should be treated as a **partial diagnostic artifact**, not as a campaign conclusion.

---

## Recommended Review Workflow

After generating the diagnosis outputs, use the following review order.

### 1. Read the Text Report First

Use the `.txt` report for fast operational review.

Confirm:

- closure status;
- families covered;
- findings emitted;
- family-level judgments emitted;
- obvious missing pieces.

### 2. Open the Manifest Second

Use the `.json` manifest when you need:

- exact evidence values;
- structured scenario summaries;
- detailed family data;
- programmatic inspection.

### 3. Cross-Check Findings and Judgments Against Raw Benchmark Artifacts

Do not accept findings or family-level judgments blindly.

Always confirm at least the most important ones by inspecting:

- consolidated benchmark summaries;
- raw Locust CSVs;
- cluster-side node pressure snapshots;
- scenario definitions.

### 4. Classify Findings and Judgments by Confidence

Findings and family-level judgments should be treated according to confidence and evidence richness.

A useful internal classification is:

- **strong preliminary evidence**;
- **plausible evidence requiring rerun or corroboration**;
- **weak evidence caused by incomplete coverage or low signal strength**.

---

## Decision Rules

The diagnosis phase should lead to one of the following decisions.

## Decision A — Diagnosis Is Strong Enough to Proceed

Proceed when:

- closure status is `preliminary_diagnosis_available`;
- the family coverage is broad enough;
- the findings and family-level judgments are technically plausible;
- the cluster-side evidence supports the main interpretations.

In this case, the campaign is ready to move to completion-gate evaluation.

## Decision B — Diagnosis Exists but Requires Another Rerun Cycle

Use this outcome when:

- findings exist, but one or more key families are incomplete;
- family-level judgments indicate weak signal or insufficient evidence in an important family;
- cluster-side evidence is sparse;
- a critical family shows unexpectedly noisy or contradictory behavior.

In this case, rerun only the missing or weak families rather than restarting the whole pipeline.

## Decision C — Diagnosis Is Not Yet Valid

Use this outcome when:

- closure status is `not_enough_data`;
- validation summary is missing;
- consolidated outputs are absent or incomplete;
- coverage is too poor to support interpretation.

In this case, do not escalate to completion-gate evaluation.

---

## Common Failure Modes

## Missing Validation Summary

### Symptom

The diagnosis output reports that the minimal validation summary is missing.

### Likely Cause

The validation phase was skipped, not persisted, or saved in the wrong location.

### Action

Regenerate or restore the validation summary before rerunning diagnosis.

---

## No Measurable Samples Found in a Family

### Symptom

A family appears in coverage but shows zero measurable samples.

### Likely Causes

- consolidated run did not actually produce stats files;
- file naming is inconsistent;
- scenario output path differs from profile expectations;
- request-specific Locust row is absent and fallback behavior is insufficient.

### Action

Inspect the family result directory and verify the scenario output path conventions.

---

## Cluster-Side Pressure Not Detected

### Symptom

The diagnosis emits no pressure-related findings even though performance degradation was observed.

### Likely Causes

- cluster-side `top nodes` snapshots were not collected;
- artifacts were saved with unexpected names;
- the observed degradation was not caused by CPU or memory pressure.

### Action

Confirm whether cluster-side collection actually ran for the analyzed campaign.

---

## Findings Conflict with Manual Observation

### Symptom

The automatically generated finding or family-level judgment appears inconsistent with what you observed manually.

### Likely Causes

- the campaign contains partial data;
- the wrong family scope was selected;
- the diagnosis profile thresholds are too permissive or too strict for the current cluster;
- one or more scenario runs were noisy.

### Action

Review the manifest, confirm the raw metrics, and decide whether a targeted rerun is needed.

---

## Best Practices

- Always generate the diagnosis **after** consolidated outputs exist and **before** phase-closure evaluation.
- Prefer full-family diagnosis when reviewing the campaign globally.
- Use per-family diagnosis only for focused troubleshooting.
- Preserve every diagnosis artifact together with the benchmark campaign it refers to.
- Treat diagnosis findings and family-level judgments as evidence-based hypotheses, not as immutable truth.
- Cross-check any major finding or non-dominant judgment against raw CSV and cluster-side artifacts before citing it in broader project decisions.
- Regenerate the diagnosis whenever the consolidated campaign is rerun.

---

## Exit Criteria

The technical diagnosis phase can be considered successfully completed when all the following conditions are met:

- diagnosis artifacts were generated successfully;
- both `.json` and `.txt` outputs are present;
- the diagnosis scope is correct for the campaign under review;
- the coverage section is interpretable;
- the gap section is reviewed explicitly;
- the findings and family-level judgments are understood and cross-checked;
- a decision is made about whether the campaign can move to completion-gate evaluation.

---

## Next Step

If the diagnosis is strong enough and the campaign is considered analytically usable, proceed to:

- `12-completion-gate-and-phase-closure.md`

If the diagnosis reveals insufficient coverage, missing evidence, weak findings, or family-level judgments dominated by weak signal / insufficient evidence, return to the appropriate upstream phase and rerun only what is necessary:

- consolidated pilot benchmarks;
- metrics and artifact collection;
- statistical-rigor validation.
