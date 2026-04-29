# LocalAI Worker-Mode Benchmark Suite

A professional benchmarking, evidence-collection, diagnosis, reporting, and phase-closure framework for **characterizing LocalAI distributed inference on Kubernetes**, with a specific focus on **worker mode / model sharding**, controlled pilot sweeps, disciplined **client-side and cluster-side evidence capture**, technical diagnosis, advisor-facing visualization, and formal completion-gate evaluation.

The repository is designed to support disciplined experimentation rather than ad-hoc testing. It provides a structured execution pipeline for answering questions such as:

- How does latency change as the number of LocalAI RPC workers changes?
- When does additional worker count stop producing meaningful gains?
- How strongly does model size affect performance on a CPU-only cluster?
- Does placement materially influence response time and throughput in the current topology?
- Which scenarios are measurably supported, and which are **unsupported under current constraints**?
- How can benchmark evidence be summarized through diagnosis outputs, charts, and sweep-level reports before deciding whether a characterization phase can be closed?

---

## Core Purpose

This project standardizes the execution of LocalAI worker-mode experiments across a Kubernetes cluster by combining:

- **controlled scenario definitions**;
- **repeatable benchmark launchers**;
- **baseline governance**;
- **automatic client-side artifact collection**;
- **automatic cluster-side artifact collection**;
- **technical diagnosis generation**;
- **reporting and visualization generation**;
- **formal completion-gate evaluation**.

The result is a benchmark suite that produces not only raw measurements, but also a multi-layer evidence trail that combines:

- **client-observed service behavior**, such as response time, percentile latency, throughput, failure count, and success rate;
- **cluster-observed infrastructure behavior**, such as pod placement, node pressure, readiness state, restarts, and scheduling signals;
- **diagnosis-level interpretation**, such as family-level judgments, strong findings, unsupported-scenario evidence, and preliminary closure status;
- **advisor-facing reporting**, such as global reports, per-sweep reports, charts, and parameter matrices;
- **formal closure evaluation**, such as completion-gate JSON and text outputs.

This layered perspective makes it possible to interpret results in a disciplined way, instead of treating performance numbers as isolated client-side outputs or isolated infrastructure snapshots.

---

## What the Repository Covers

The suite currently supports a first disciplined characterization cycle across four main experimental dimensions:

- **worker-count sweep**;
- **workload sweep**;
- **model sweep**;
- **placement sweep**.

It also provides:

- an **official locked baseline** for controlled comparisons;
- exploratory smoke, low-load, and small-concurrency validation flows;
- structured support for scenarios classified as `unsupported_under_current_constraints`;
- technical diagnosis with both **strong findings** and **family-level judgments**;
- reporting and visualization outputs with both a **global report** and **dedicated sweep reports**;
- completion-gate logic for deciding whether a benchmark cycle is strong enough to be considered closed.

---

## Key Capabilities

### 1. Baseline-Driven Execution

A single official baseline (`B0`) freezes the initial reference configuration:

- LocalAI in **worker mode**;
- a lightweight validated model;
- two RPC workers;
- controlled low-load workload;
- colocated placement on the reference cluster.

All pilot sweeps are meant to vary **one dimension at a time** from that baseline.

### 2. Kubernetes Topology as Code

The Kubernetes layer is organized with **base**, **overlays**, and **compositions** so that deployment topology remains explicit and reproducible.

### 3. Standardized Benchmark Protocol

Each benchmark run follows a common execution model:

1. controlled cleanup;
2. scenario deployment;
3. technical precheck;
4. API smoke validation;
5. optional warm-up;
6. measurement;
7. client-side artifact collection;
8. cluster-side artifact collection;
9. final snapshot;
10. controlled cleanup or restore.

### 4. Built-In Evidence Capture

The suite collects both:

- **client-side benchmark metrics**, such as request count, response time, throughput, failure count, success rate, and percentile distributions;
- **cluster-side evidence**, such as node pressure, pod placement, events, pod descriptions, services, restarts, and readiness state.

### 5. Technical Diagnosis

The diagnosis phase converts benchmark outputs into structured interpretation, including:

- coverage overview by family;
- scenario averages;
- explicit support for unsupported scenarios;
- metric values with explicit units, including mean response time, P50, P95, P99, throughput, request count, failure count, success rate, CPU, and memory;
- strong findings when the signal is dominant;
- family-level judgments when the signal is weak or evidence is incomplete.

### 6. Reporting and Visualization

The reporting phase runs after technical diagnosis and before completion-gate evaluation. It generates a stable advisor-facing report directory under:

```text
results/reporting/
```

The reporting phase combines:

- quantitative values from measurement CSV files;
- context and interpretation from the latest technical diagnosis;
- scenario configuration metadata;
- charts for latency, throughput, CPU, and memory;
- explicit fixed and varied parameter summaries.

It produces both a global report and one dedicated report for each sweep family.

### 7. Completion Gate

A post-reporting completion gate evaluates whether the current characterization cycle is sufficiently strong to justify phase closure. It is diagnosis-driven and reporting-aware: it checks not only whether benchmark evidence and diagnosis outputs exist, but also whether the required reporting artifacts have been generated.

---

## Repository Structure

```text
.
├── config/
│   ├── baseline, pilot scenarios, protocol, metric-set
│   ├── cluster-capture, precheck, statistical rigor
│   ├── technical diagnosis, reporting, completion gate
│   └── conventions and phase profiles
├── docs/runbooks/
│   ├── cluster bootstrap and access
│   ├── deployment, validation, baseline, pilot sweeps
│   ├── evidence collection, diagnosis, reporting, completion gate
│   └── cleanup and rerun guidance
├── infra/k8s/
│   ├── base/
│   ├── overlays/
│   └── compositions/
├── load-tests/locust/
│   └── Locust workload used for LocalAI HTTP benchmarking
├── results/
│   ├── validation/
│   ├── exploratory/
│   ├── baseline/
│   ├── pilot/
│   ├── diagnosis/
│   ├── reporting/
│   └── completion-gate/
└── scripts/
    ├── validation/
    ├── load/
    └── analysis/
```

---

## Main Configuration Profiles

The repository is intentionally profile-driven. The most relevant configuration files are:

| Profile | File | Purpose |
|---|---|---|
| Baseline | `config/scenarios/baseline/B0.json` | Official locked reference configuration |
| Protocol | `config/protocol/EP1.json` | Standard benchmark execution sequence |
| Metric set | `config/metric-set/MS1.json` | Mandatory client-side and cluster-side metrics |
| Cluster capture | `config/cluster-capture/CS1.json` | Mandatory cluster-side artifacts to collect |
| Precheck | `config/precheck/TC1.json` | Technical readiness checks before a run |
| Statistical rigor | `config/statistical-rigor/SR1.json` | Repeatability and coefficient-of-variation rules |
| Technical diagnosis | `config/technical-diagnosis/TD1.json` | Evidence interpretation rules |
| Reporting | `config/reporting/RP1.json` | Advisor-facing reporting and visualization profile |
| Completion gate | `config/completion-gate/CG1.json` | Formal phase-closure criteria |

---

## Current Execution Model

The current suite is tuned around a **CPU-only Kubernetes cluster** and a worker-mode LocalAI deployment strategy.

The present reference baseline uses:

- **worker mode**;
- **two workers**;
- **a lightweight validated model**;
- **controlled low-load benchmark traffic**;
- **colocated placement**.

This baseline is not intended to be the final answer for every environment. It is the controlled reference point from which the other benchmark families are compared.

---

## Execution Workflow

### 1. Prepare Cluster Access

Before placing a live kubeconfig in the runtime path expected by the scripts, first read:

```text
config/cluster-access/README.md
```

That file explains:

- how cluster-access material is expected to be handled locally;
- why the effective runtime path remains fixed inside the project;
- how `kubeconfig.example` should be used;
- what to restore if the real kubeconfig is missing.

The effective path expected by the scripts is:

```text
config/cluster-access/kubeconfig
```

A safe template is provided at:

```text
config/cluster-access/kubeconfig.example
```

### 2. Validate Environment and Access

Use the runbooks in `docs/runbooks/00` and `docs/runbooks/01` together with the precheck scripts before attempting deployment.

### 3. Deploy the Required Kubernetes Topology

Use the compositions under `infra/k8s/compositions/` according to the selected scenario.

### 4. Run Validation and Benchmark Campaigns

Available launcher groups include:

- `scripts/load/exploratory/`
- `scripts/load/baseline/`
- `scripts/load/pilot/`
- `scripts/load/post/`

### 5. Diagnose, Report, and Evaluate

After consolidated execution, the canonical post-processing sequence is:

1. **technical diagnosis**;
2. **reporting and visualization**;
3. **completion gate**.

The corresponding launchers are available under `scripts/load/post/`. Detailed PowerShell and Bash commands, optional overrides, and rerun guidance are documented in:

- `docs/runbooks/11-technical-diagnosis.md`;
- `docs/runbooks/12-reporting-and-visualization.md`;
- `docs/runbooks/13-completion-gate-and-phase-closure.md`.

The completion-gate launcher can auto-detect the latest `all` diagnosis under `results/diagnosis/`, while explicit diagnosis paths remain available for retrospective evaluation.

---

## Reporting Outputs

The reporting phase writes its current advisor-facing outputs under:

```text
results/reporting/
```

The main entry point is:

```text
results/reporting/index.html
```

The directory also contains the Markdown report, scenario summary CSV, reporting manifest, charts, and dedicated per-sweep reports. The report is static, not live: after new benchmark or diagnosis outputs are produced, rerun the reporting launcher to refresh the generated artifacts.

The default behavior keeps `results/reporting/` as the stable current report location. Historical snapshots can optionally be stored under:

```text
results/reporting/archive/<reporting-id>/
```

For the complete output layout, archive modes, and execution commands, see `docs/runbooks/12-reporting-and-visualization.md`.

---

## Optional GitHub Pages Publication

The generated HTML reporting package can optionally be published as a static GitHub Pages site through `.github/workflows/deploy-reporting-pages.yml`.

GitHub Pages is only a publication layer for the current report under `results/reporting/`: it does not replace the local reporting workflow, it is not required by the completion gate, and it does not change the canonical post-processing order. Archived reporting snapshots under `results/reporting/archive/` are deliberately excluded from the published Pages artifact.

For setup and publication details, see `docs/runbooks/12-reporting-and-visualization.md`.

---

## Benchmark Families

### Worker Count

Assesses how latency and throughput evolve when the number of RPC workers changes.

### Workload

Assesses how the system behaves under controlled increases in client pressure and concurrency.

### Models

Assesses how model size and quantization affect performance on the active cluster.

### Placement

Assesses whether pod placement decisions materially influence performance in the current topology.

---

## Output Philosophy

This repository treats benchmark execution as an evidence-producing process.

A meaningful run is expected to produce more than a single CSV file. The suite is designed to preserve:

- configuration context;
- execution protocol traces;
- client-side benchmark artifacts;
- cluster-side snapshots;
- validation summaries;
- diagnosis outputs;
- reporting outputs;
- completion-gate outputs.

This structure makes it possible to explain *why* a run behaved in a certain way, not just *what* its average latency was.

---

## Operational Notes

- The root `README.md` is intended to provide the primary technical entry point for the repository.
- Detailed execution guidance lives in `docs/runbooks/`.
- Cluster-access handling is documented separately in `config/cluster-access/README.md`.
- The repository is designed around disciplined execution and evidence preservation, not around one-off manual benchmarking.
- Generated reports under `results/reporting/` are refreshed by rerunning the reporting launcher after new benchmark and diagnosis outputs are produced.

---

## Status

The repository already supports a full first characterization cycle with:

- baseline execution;
- exploratory validation;
- pilot sweeps;
- consolidated benchmark evidence;
- technical diagnosis;
- reporting and visualization;
- formal completion-gate evaluation.

The next stages can therefore build on an existing structured benchmark foundation rather than on an ungoverned experimental setup.
