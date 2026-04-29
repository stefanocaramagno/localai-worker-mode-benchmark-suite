# 12. Reporting and Visualization

## Objective

This runbook defines how to generate the advisor-facing reporting layer after technical diagnosis and before completion-gate evaluation.

The purpose of this phase is to transform consolidated benchmark evidence and diagnosis context into readable reports, charts, and parameter summaries. It exists because raw CSV files, cluster artifacts, and diagnosis JSON payloads are necessary for traceability, but they are not sufficient for quickly understanding the overall behavior of the experiment campaign.

This phase answers questions such as:

- which sweep families were executed;
- which parameter was varied in each family;
- which parameters remained fixed;
- which scenarios were measured, unsupported, missing, or not executed;
- how latency, throughput, CPU, and memory changed across scenarios;
- which findings from the technical diagnosis should be considered when reading the charts.

The reporting phase is therefore not an optional cosmetic layer. It is the readable synthesis required before the campaign can be evaluated by the completion gate.

---

## Scope

This runbook covers:

- the role of the reporting phase in the post-processing pipeline;
- the repository components involved in report generation;
- the reporting profile used by the current implementation;
- the expected output structure under `results/reporting/`;
- the execution procedure for PowerShell and Bash;
- the interpretation of global and per-sweep reports;
- the handling of missing or not-executed sweep families;
- the relationship between reporting, technical diagnosis, and completion-gate evaluation.

This runbook does **not** cover:

- Kubernetes cluster bootstrap;
- LocalAI deployment;
- workload generation;
- Locust benchmark execution;
- cluster-side evidence collection;
- statistical rigor evaluation;
- technical diagnosis generation;
- completion-gate decision logic.

Those phases must already be governed by their dedicated runbooks.

---

## Phase Position in the Pipeline

The canonical post-processing order is:

```text
technical diagnosis
        ↓
reporting and visualization
        ↓
completion gate
```

The reporting phase must run **after** technical diagnosis because the report integrates diagnosis-level context, including findings, family-level judgments, and unsupported-scenario evidence.

The reporting phase must run **before** completion-gate evaluation because the current completion-gate profile requires reporting artifacts as part of phase closure.

---

## Governing Principle

The reporting phase is a synthesis layer, not a second diagnosis engine.

It combines three types of information:

1. **quantitative measurements**, taken from benchmark CSV outputs whenever available;
2. **scenario and baseline metadata**, taken from scenario configuration files and baseline configuration;
3. **interpretative context**, taken from the latest technical diagnosis.

This division of responsibility is deliberate:

- CSV files remain the primary source for numeric charts and measurement tables;
- the technical diagnosis remains the primary source for interpretation and unsupported-scenario context;
- reporting assembles these inputs into a readable artifact for review and discussion.

---

## Repository Components Involved

### Configuration

```text
config/reporting/RP1.json
```

The reporting profile defines:

- output root;
- generated file names;
- baseline configuration path;
- diagnosis root;
- pilot results roots;
- scenario configuration roots;
- family order;
- display names;
- varied and fixed dimensions per family;
- reference scenario per family;
- chart definitions;
- output policy.

### Launchers

```text
scripts/load/post/Start-Reporting.ps1
scripts/load/post/start-reporting.sh
```

The launchers resolve the repository root, load the reporting profile, generate a reporting ID, and invoke the Python reporting generator.

### Analysis Script

```text
scripts/analysis/generate-reporting.py
```

The analysis script reads the profile, scans benchmark outputs, reads scenario metadata, incorporates diagnosis context, generates charts, and writes Markdown, HTML, CSV, and JSON reporting artifacts.

### Upstream Inputs

The reporting phase expects the following upstream areas to exist when available:

```text
results/pilot/consolidated/
results/diagnosis/
config/scenarios/baseline/B0.json
config/scenarios/pilot/
```

If a sweep family has not been executed, the report must not fail. Instead, it must classify the family as `not_executed` and produce a clear report section explaining that no measurement or unsupported-scenario evidence was found for that family.

---

## Reporting Profile: `RP1`

The active reporting profile is `RP1`.

Key characteristics include:

- output root: `results/reporting`;
- global Markdown report: `report.md`;
- global HTML report: `index.html`;
- scenario summary CSV: `scenario-summary.csv`;
- reporting manifest: `reporting-manifest.json`;
- chart directory: `charts/`;
- sweep report directory: `sweeps/`;
- profile behavior: write the current report directly under `results/reporting/` and overwrite managed current artifacts on each execution;
- optional archive directory name: `archive/`.

The profile intentionally avoids a `latest/` directory. The reporting phase represents the current readable state of the benchmark campaign through stable paths under `results/reporting/`. If new results or diagnosis outputs are generated, rerun the reporting launcher to refresh the current report.

When historical report snapshots are required, archive mode can also preserve a timestamped copy of the generated report package under `results/reporting/archive/<reporting-id>/`. This archive is optional and does not replace the stable current report path.

---

## Output Structure

A successful reporting run writes the following structure:

```text
results/reporting/
├── index.html
├── report.md
├── scenario-summary.csv
├── reporting-manifest.json
├── charts/
│   ├── worker-count/
│   ├── workload/
│   ├── models/
│   └── placement/
└── sweeps/
    ├── worker-count/
    │   ├── index.html
    │   └── report.md
    ├── workload/
    │   ├── index.html
    │   └── report.md
    ├── models/
    │   ├── index.html
    │   └── report.md
    └── placement/
        ├── index.html
        └── report.md
```

### Global Report

The global report provides a campaign-wide view. It is the main entry point for advisors and reviewers.

Open:

```text
results/reporting/index.html
```

or read:

```text
results/reporting/report.md
```

### Per-Sweep Reports

Each sweep report focuses on one experimental family. These reports make explicit:

- execution status;
- fixed baseline parameters;
- scenario parameter matrix;
- compact measurement summary;
- extended measurement metrics;
- diagnosis-based reading;
- charts;
- reading notes.

The per-sweep reports are useful when reviewing one experimental dimension in detail without navigating the global report.

The optional archive mode preserves the same managed reporting package under:

```text
results/reporting/archive/<reporting-id>/
├── index.html
├── report.md
├── scenario-summary.csv
├── reporting-manifest.json
├── charts/
└── sweeps/
```

The archive directory is not used by the completion gate. It exists only for historical inspection of previous reporting snapshots.

---

## Optional GitHub Pages Publication

The current HTML reporting package can optionally be published through GitHub Pages using the workflow located at:

```text
.github/workflows/deploy-reporting-pages.yml
```

This publication step is intentionally separate from the experimental pipeline. The canonical local output remains:

```text
results/reporting/index.html
```

When the workflow runs, it stages the current contents of `results/reporting/` as a static site and deploys that staged directory through GitHub Pages. The global `index.html` becomes the Pages entry point, while sweep-specific reports remain accessible through the relative links generated by the reporting script:

```text
sweeps/worker-count/
sweeps/workload/
sweeps/models/
sweeps/placement/
```

The workflow validates that the current report exists before deployment. It publishes the current report package only and excludes `results/reporting/archive/`, because archive entries are historical local snapshots rather than the canonical advisor-facing report.

GitHub Pages publication is optional. It must not be treated as a benchmark phase, it must not replace the local reporting artifacts, and it is not a completion-gate requirement.

Before enabling public Pages hosting, verify that the generated report does not expose sensitive cluster details, local filesystem paths, credentials, kubeconfig content, or infrastructure information that should remain private.

---

## Metrics Displayed in the Reports

The reporting phase uses human-readable column names and explicit units.

The compact `Measurement summary` table focuses on the most immediately useful comparison metrics:

| Column | Meaning |
|---|---|
| `Scenario` | Scenario identifier |
| `Description` | Human-readable scenario description |
| `Status` | Measurement status, unsupported status, missing status, or not-executed status |
| `Sample count` | Number of measured request samples |
| `Mean response time (ms)` | Mean client-observed response time |
| `P95 response time (ms)` | 95th-percentile client-observed response time |
| `Throughput (requests/s)` | Client-observed request throughput |
| `Unsupported evidence` | Relevant unsupported-scenario evidence, if present |

The `Extended measurement metrics` table preserves additional detail without making the compact table too wide:

| Column | Meaning |
|---|---|
| `Scenario` | Scenario identifier |
| `P50 response time (ms)` | Median client-observed response time |
| `P99 response time (ms)` | 99th-percentile client-observed response time |
| `Mean response time delta (%)` | Mean-latency delta against the family reference scenario |
| `P95 response time delta (%)` | P95-latency delta against the family reference scenario |
| `Throughput delta (%)` | Throughput delta against the family reference scenario |
| `Max node CPU snapshot (%)` | Maximum node CPU snapshot available for the run context |
| `Max node memory snapshot (%)` | Maximum node memory snapshot available for the run context |

Charts are generated for the metrics configured in `RP1`, including mean response time, P50, P95, P99, throughput, maximum node CPU snapshot, and maximum node memory snapshot.

---

## Sweep Execution Status Semantics

The reporting phase distinguishes the following states:

| Status | Meaning |
|---|---|
| `measured` | At least one benchmark measurement was found for the scenario |
| `unsupported_under_current_constraints` | The scenario was formally observed but could not run under the current constraints |
| `missing` | The scenario is known from configuration but no measurement or accepted unsupported evidence was found |
| `not_executed` | No benchmark measurements or unsupported-scenario evidence were found for the entire sweep family |

A `not_executed` sweep does not make the reporting phase fail. The report is still generated so that the current campaign state remains readable. However, a not-executed required family will normally prevent successful completion-gate closure.

---

## Execution Procedure

### PowerShell

From the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-Reporting.ps1"
```

If local execution policy already allows project scripts, the shorter form is also valid:

```powershell
.\scripts\load\post\Start-Reporting.ps1
```

### Bash

From the repository root:

```bash
./scripts/load/post/start-reporting.sh
```

### Optional Arguments

The PowerShell launcher supports overriding the repository root, profile path, output root, reporting ID, and archive behavior. The standard execution path should not require these overrides.

Use archive mode only when a historical reporting snapshot must be preserved in addition to the current report.

### Optional archive mode

PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-Reporting.ps1" -Archive
```

Bash:

```bash
./scripts/load/post/start-reporting.sh --archive
```

Archive mode does two things:

1. refreshes the stable current report under `results/reporting/`;
2. copies the generated report package to `results/reporting/archive/<reporting-id>/`.

The default non-archive behavior is preferred for routine execution because it keeps the reporting phase aligned with the governed repository layout and avoids unnecessary accumulation of generated HTML/SVG artifacts.

---

## Verification Checklist

After running the reporting phase, verify that the following files exist:

```text
results/reporting/index.html
results/reporting/report.md
results/reporting/scenario-summary.csv
results/reporting/reporting-manifest.json
```

Then verify that each required sweep family has a dedicated report:

```text
results/reporting/sweeps/worker-count/index.html
results/reporting/sweeps/workload/index.html
results/reporting/sweeps/models/index.html
results/reporting/sweeps/placement/index.html
```

Finally, verify that chart directories exist for the governed families:

```text
results/reporting/charts/worker-count/
results/reporting/charts/workload/
results/reporting/charts/models/
results/reporting/charts/placement/
```

---

## How to Read the Reports

Start from the global HTML report:

```text
results/reporting/index.html
```

Use it to understand the overall campaign status. Then open the relevant sweep-level report when deeper inspection is needed.

For example:

```text
results/reporting/sweeps/worker-count/index.html
results/reporting/sweeps/workload/index.html
results/reporting/sweeps/models/index.html
results/reporting/sweeps/placement/index.html
```

When reading a sweep report, use this order:

1. read the execution status;
2. check the fixed baseline parameters;
3. inspect the scenario parameter matrix;
4. compare the compact measurement summary;
5. inspect the extended metrics when more detail is needed;
6. review diagnosis-based notes;
7. inspect charts.

This order prevents the reader from interpreting a chart without first understanding which parameter was varied and which parameters remained fixed.

---

## Common Failure Modes

### Reporting runs but charts are empty

Likely causes:

- no measurement CSV files exist for the family;
- the scenario was only observed as unsupported;
- the request target in the CSV does not match the configured request target;
- the consolidated output root differs from the root configured in `RP1`.

### A sweep report says `not_executed`

This means that neither measurement data nor unsupported-scenario evidence was found for the entire family.

This is not a reporting error. It is a faithful representation of the current evidence set.

### Reporting output exists but completion gate fails

This is expected when the report exists but required evidence remains incomplete. Reporting verifies readability; the completion gate verifies formal closure readiness.

### Report appears outdated

Rerun the reporting launcher after generating new benchmark or diagnosis outputs. The reporting phase is static and must be refreshed explicitly.

### Archive was not created

Archive creation is opt-in. Run the reporting launcher with `-Archive` in PowerShell or `--archive` in Bash. Without this option, only the current stable report under `results/reporting/` is refreshed.

---

## Success Criteria

The reporting phase is successful when:

- the global Markdown and HTML reports exist;
- the scenario summary CSV exists;
- the reporting manifest exists;
- chart directories and chart files are generated for the available evidence;
- per-sweep reports exist for all governed families;
- missing or not-executed families are reported explicitly rather than silently ignored;
- the outputs can be inspected without reading raw CSV files manually.

---

## Next Step

After generating and reviewing the reporting artifacts, proceed to:

- `13-completion-gate-and-phase-closure.md`

The completion gate will evaluate the diagnosis and verify that the required reporting artifacts are present before declaring the characterization cycle complete.
