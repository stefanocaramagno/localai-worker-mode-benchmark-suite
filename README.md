# LocalAI Worker-Mode Benchmark Suite

A professional benchmarking, evidence-collection, and diagnostic framework for **characterizing LocalAI distributed inference on Kubernetes**, with a specific focus on **worker mode / model sharding**, controlled pilot sweeps, disciplined **client-side and cluster-side evidence capture**, technical diagnosis, and formal phase-closure evaluation.

The repository is designed to support disciplined experimentation rather than ad-hoc testing. It provides a structured execution pipeline for answering questions such as:

- How does latency change as the number of workers changes?
- When does additional worker count stop producing meaningful gains?
- How strongly does model size affect performance on a CPU-only cluster?
- Does placement materially influence response time and throughput in the current topology?
- Which scenarios are measurably supported, and which are **unsupported under current constraints**?

---

## Core Purpose

This project standardizes the execution of LocalAI worker-mode experiments across a Kubernetes cluster by combining:

- **controlled scenario definitions**;
- **repeatable benchmark launchers**;
- **baseline governance**;
- **automatic client-side artifact collection**;
- **automatic cluster-side artifact collection**;
- **technical diagnosis generation**;
- **formal completion-gate evaluation**.

The result is a benchmark suite that produces not only raw measurements, but also a two-layer evidence trail that combines:

- **client-observed service behavior** such as latency, throughput, failures, and percentile distributions;
- **cluster-observed infrastructure behavior** such as pod placement, node pressure, readiness state, restarts, and scheduling signals.

This dual perspective makes it possible to interpret results in a disciplined way, instead of treating performance numbers as isolated client-side outputs or isolated infrastructure snapshots.

---

## What the Repository Covers

The suite currently supports a first disciplined characterization cycle across four main experimental dimensions:

- **worker-count sweep**
- **workload sweep**
- **model sweep**
- **placement sweep**

It also provides:

- an **official locked baseline** for controlled comparisons;
- exploratory smoke, low-load and small concurrency validation flows;
- structured support for scenarios classified as `unsupported_under_current_constraints`;
- technical diagnosis with both **strong findings** and **family-level judgments**;
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

- **client-side benchmark metrics** such as response times, throughput, failure count, success rate, and percentile distributions;
- **cluster-side evidence** such as node pressure, pod placement, events, pod descriptions, services, restarts, and readiness state.

### 5. Technical Diagnosis

The diagnosis phase converts benchmark outputs into structured interpretation, including:

- coverage overview by family;
- scenario averages;
- explicit support for unsupported scenarios;
- strong findings when the signal is dominant;
- family-level judgments when the signal is weak or evidence is incomplete.

### 6. Completion Gate

A post-analysis completion gate evaluates whether the current characterization cycle is sufficiently strong to justify phase closure.

---

## Repository Structure

```text
.
├── config/
│   ├── baseline, pilot scenarios, protocol, metric-set
│   ├── cluster-capture, precheck, statistical rigor
│   ├── technical diagnosis, completion gate
│   └── conventions and phase profiles
├── docs/runbooks/
│   ├── cluster bootstrap and access
│   ├── deployment, validation, baseline, pilot sweeps
│   ├── evidence collection, diagnosis, completion gate
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

### 5. Collect, Diagnose, and Evaluate

After execution, use:

- technical-diagnosis launchers to generate structured interpretation;
- completion-gate launchers to decide whether the benchmark cycle is formally complete.

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
- completion-gate outputs.

This structure makes it possible to explain *why* a run behaved in a certain way, not just *what* its average latency was.

---

## Operational Notes

- The root `README.md` is intended to provide the primary technical entry point for the repository.
- Detailed execution guidance lives in `docs/runbooks/`.
- Cluster-access handling is documented separately in `config/cluster-access/README.md`.
- The repository is designed around disciplined execution and evidence preservation, not around one-off manual benchmarking.

---

## Status

The repository already supports a full first characterization cycle with:

- baseline execution;
- exploratory validation;
- pilot sweeps;
- consolidated benchmark evidence;
- technical diagnosis;
- formal completion-gate evaluation.

The next stages can therefore build on an existing structured benchmark foundation rather than on an ungoverned experimental setup.
