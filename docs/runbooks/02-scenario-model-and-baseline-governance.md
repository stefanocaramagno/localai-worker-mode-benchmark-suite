# 02. Scenario Model and Baseline Governance

## Objective

Define the governance model used to control benchmark scenarios, baseline locking, pilot sweep families, execution profiles, run naming, and interpretation boundaries for the LocalAI worker-mode benchmarking pipeline.

This runbook must be applied **before** launching any official baseline run, pilot sweep, consolidated campaign, technical diagnosis, or completion gate. Its purpose is to ensure that all benchmark activity is traceable, comparable, and methodologically consistent.

---

## When to Use This Runbook

Use this runbook in the following situations:

- before the first official baseline execution;
- before launching any pilot sweep family;
- before re-running consolidated pilot campaigns;
- before changing a scenario JSON file under `config/scenarios/`;
- before interpreting benchmark results as comparable evidence;
- whenever a new operator needs to understand how the repository governs experimental state.

---

## Scope

This document covers the governance layer of the repository, specifically:

- the official baseline definition;
- the scenario model used by pilot sweeps;
- the distinction between baseline and controlled variations;
- run identification and required metadata;
- execution and evidence profiles that standardize the pipeline;
- interpretation constraints that apply to worker-count, workload, model, and placement sweeps.

This runbook does **not** cover deployment commands, smoke validation commands, load generation commands, or cleanup commands in detail. Those belong to their dedicated runbooks.

---

## Repository Areas Covered by This Runbook

The governance model is implemented in the following repository areas:

```text
config/
├── cluster-capture/
│   └── CS1.json
├── completion-gate/
│   └── CG1.json
├── conventions/
│   └── RC1.json
├── metric-set/
│   └── MS1.json
├── phases/
│   └── WM1.json
├── pilot-consolidation/
│   └── CP1.json
├── precheck/
│   └── TC1.json
├── protocol/
│   └── EP1.json
├── scenarios/
│   ├── baseline/
│   │   └── B0.json
│   └── pilot/
│       ├── models/
│       ├── placement/
│       ├── worker-count/
│       └── workload/
├── reporting/
│   └── RP1.json
├── statistical-rigor/
│   └── SR1.json
└── technical-diagnosis/
    └── TD1.json
```

All benchmark activity must remain aligned with these files.

---

## Governance Principles

The benchmarking pipeline is governed by the following principles.

### 1. A single official baseline must exist

The repository defines one locked reference configuration through:

```text
config/scenarios/baseline/B0.json
```

All controlled pilot variations must be interpreted as deltas from this baseline.

### 2. Only one experimental dimension may vary at a time

Pilot sweeps are designed so that each scenario family changes **exactly one** dimension while inheriting all others from the official baseline.

### 3. All runs must be traceable

Every run must produce a unique run identifier and a run manifest with required metadata.

### 4. All campaigns must use explicit execution profiles

Warm-up handling, protocol order, metric sets, cluster-side evidence, statistical rigor, technical diagnosis, reporting, and completion criteria are governed by configuration profiles, not by ad hoc operator choices.

### 5. Interpretation boundaries must be explicit

If infrastructure constraints or topology choices shape a scenario family, those constraints must be treated as part of the experimental design and not as hidden assumptions.

---

## Official Baseline

### Baseline File

```text
config/scenarios/baseline/B0.json
```

### Baseline Identity

The official baseline is identified as:

- **Baseline ID:** `B0`
- **Status:** `official_locked_baseline`

### Baseline Purpose

The baseline is defined as the official locked reference configuration for consolidated LocalAI worker-mode characterization on the current CPU-only two-worker-node Kubernetes cluster.

### Baseline Resolved Configuration

The baseline freezes the following dimensions:

- **Worker mode:** `worker`
- **Model scenario:** `M1`
- **Resolved model name:** `llama-3.2-1b-instruct:q4_k_m`
- **Worker scenario:** `W2`
- **Resolved worker count:** `2`
- **Placement scenario:** `PL1`
- **Resolved placement type:** `colocated_sc_app_02`
- **Workload scenario:** `WL2`
- **Resolved workload:**
  - users: `2`
  - spawn rate: `1`
  - run time: `2m`
- **Topology composition:** `infra/k8s/compositions/topology/colocated-sc-app-02-w2`
- **Server composition:** `infra/k8s/compositions/server/models/m1`
- **Namespace composition:** `infra/k8s/compositions/foundation/namespace`
- **Storage composition:** `infra/k8s/compositions/foundation/storage`
- **Base URL:** `http://localhost:8080`

This local base URL is the canonical endpoint used across the repository. In the current pipeline, when `http://localhost:8080` is used through the main launcher stack, the launcher automatically verifies and, if necessary, creates the local port-forward toward `service/localai-server` in the `genai-thesis` namespace. Standalone validation scripts keep a narrower responsibility and therefore assume that the supplied `BaseUrl` is already reachable.

- **Prompt:** `Reply with only READY.`
- **Temperature:** `0.1`
- **Request timeout:** `120 seconds`
- **Results root:** `results/baseline/official`

### Baseline Lock Rules

The baseline file defines explicit lock rules:

- do not override model, worker count, placement, or workload from launcher parameters;
- use `B0` as the unique reference configuration until the consolidated characterization phase is complete;
- treat all future deltas as controlled variations from `B0`.

### Operational Consequence

Operators must not treat the baseline as a suggestion. It is the canonical reference point for:

- official baseline execution;
- pilot family inheritance;
- comparative interpretation;
- consolidated campaign consistency;
- diagnosis, reporting, and completion-gate evaluation.

---

## Pilot Scenario Families

The repository defines four pilot sweep families under:

```text
config/scenarios/pilot/
```

Each family is anchored to `B0` via `referenceBaselineId` and changes a single dimension only.

---

## Worker Count Sweep Governance

### Directory

```text
config/scenarios/pilot/worker-count/
```

### Scenarios

- `W1` — single RPC worker
- `W2` — two RPC workers
- `W3` — three RPC workers
- `W4` — four RPC workers

### Fixed Dimensions Inherited from Baseline

The worker-count family inherits from `B0`:

- model;
- server manifest;
- workload;
- prompt;
- temperature;
- request timeout;
- baseline placement mode.

### Variable Dimension

Only the **active worker count** changes.

### Interpretation Rule

This family is intentionally modeled as a **worker-count-only variation under constant co-located placement policy**. The family is designed to answer:

> What changes when the number of active RPC workers increases while all other dimensions remain fixed?

### Important Boundary

The worker-count sweep must **not** be interpreted as a generic scaling study across arbitrary topologies. It is specifically a controlled comparison under a placement policy anchored to the baseline.

---

## Workload Sweep Governance

### Directory

```text
config/scenarios/pilot/workload/
```

### Scenarios

- `WL1` — smoke single user
- `WL2` — low load two users
- `WL3` — small concurrency four users

### Fixed Dimensions Inherited from Baseline

The workload family inherits from `B0`:

- model;
- worker scenario;
- placement scenario;
- prompt;
- temperature;
- request timeout.

### Variable Dimension

Only the **input workload profile** changes:

- users;
- spawn rate;
- run time.

### Interpretation Rule

The workload sweep measures the response of the baseline topology and model to increasing input pressure. It is not a topology comparison and must not be interpreted as a placement experiment.

---

## Model Sweep Governance

### Directory

```text
config/scenarios/pilot/models/
```

### Scenarios

- `M1` — Llama 3.2 1B q4_k_m
- `M2` — Llama 3.2 1B q8_0
- `M3` — Llama 3.2 3B q4_k_m
- `M4` — Llama 3.2 3B q8_0

### Fixed Dimensions Inherited from Baseline

The model family inherits from `B0`:

- worker scenario;
- placement scenario;
- workload scenario;
- prompt;
- temperature;
- request timeout.

### Variable Dimension

Only the **resolved model** and the derived **server manifest** change.

### Interpretation Rule

This family is a model-only comparison within the same operational envelope. It is intended to reveal model footprint or model-size penalties under otherwise stable conditions.

---

## Placement Sweep Governance

### Directory

```text
config/scenarios/pilot/placement/
```

### Scenarios

- `PL1` — co-located on `sc-app-02`
- `PL2` — distributed two-node placement

### Fixed Dimensions Inherited from Baseline

The placement family inherits from `B0`:

- model;
- worker count;
- workload;
- prompt;
- temperature;
- request timeout.

### Variable Dimension

Only the **worker topology / placement policy** changes via the resolved topology composition.

### Critical Interpretation Rule

In the current repository design, the **server remains fixed** according to the server deployment composition, while the placement sweep varies the **worker placement only**.

Therefore, the placement family must be interpreted as:

> the effect of changing worker distribution relative to a fixed server placement.

It must **not** be described as a full-topology placement optimization study.

This boundary is methodologically acceptable and must be preserved in result interpretation.

---

## Run Convention Governance

### Convention File

```text
config/conventions/RC1.json
```

### Convention Identity

- **Run convention ID:** `RC1`
- **Version:** `1.0.0`
- **Timezone:** `UTC`

### Run ID Format

All launcher scripts must produce run IDs in the following format:

```text
RID-<UTC_TIMESTAMP_COMPACT>-<CAMPAIGN>-<PRIMARY_SCENARIO>-R<REPLICA>
```

### Timestamp Pattern

```text
YYYYMMDDTHHMMSSZ
```

### Replica Policy

- replicated runs: `A`, `B`, `C`
- non-replicated runs: `NA`

### Required Run Metadata

Every run manifest must include at least:

- `runId`
- `startedAtUtc`
- `campaign`
- `primaryScenario`
- `replica`
- `scenarioPurpose`
- `baseUrl`
- `locustFile`
- `modelName`
- `workerCount`
- `placementType`
- `users`
- `spawnRate`
- `warmUpDuration`
- `measurementDuration`

### Governance Rule

Operators must not create custom, inconsistent naming conventions for ad hoc runs that are later mixed with official evidence. Any run intended to be retained as evidence must comply with `RC1`.

---

## Phase Governance

### Phase File

```text
config/phases/WM1.json
```

### Phase Identity

- **Profile ID:** `WM1`

### Standardized Phases

The benchmark phase model includes:

1. warm-up;
2. measurement.

### Standard Defaults

- default warm-up duration: `30s`
- default measurement duration: `120s`
- warm-up artifacts retained: `true`
- startup model check during measurement: `false`

### Governance Rule

Warm-up and measurement must remain separate. Operators must not merge bootstrap and steady-state measurement into a single undifferentiated run if the output is intended for comparison.

---

## Protocol Governance

### Protocol File

```text
config/protocol/EP1.json
```

### Protocol Identity

- **Profile ID:** `EP1`

### Standard Protocol Sequence

The repository defines the following ordered protocol:

1. controlled cleanup;
2. deploy scenario;
3. technical pre-check;
4. API smoke validation;
5. optional warm-up;
6. measurement;
7. collect client metrics;
8. collect cluster metrics;
9. final snapshot;
10. cleanup or restore.

### Governance Rule

This execution order is not optional for official benchmark runs. If a run skips required stages, it must not be treated as comparable evidence.

---

## Technical Pre-Check Governance

### File

```text
config/precheck/TC1.json
```

### Purpose

The pre-check profile standardizes the mandatory health and readiness checks that must pass before a run enters the benchmark protocol.

### Governance Rule

No official baseline run, pilot run, consolidated run, or diagnosis input should be accepted if it bypassed the required technical pre-check.

---

## Cluster-Side Evidence Governance

### File

```text
config/cluster-capture/CS1.json
```

### Profile Identity

- **Profile ID:** `CS1`

### Mandatory Cluster Artifacts

The cluster capture profile requires collection of:

- `nodes-wide.txt`
- `top-nodes.txt`
- `pods-wide.txt`
- `top-pods.txt`
- `services.txt`
- `events.txt`
- `pods-describe.txt`

### Governance Rule

Client-side latency and throughput numbers are not sufficient by themselves. Every retained benchmark must include mandatory cluster-side evidence before it can be used for diagnosis or closure decisions.

---

## Metric Set Governance

### File

```text
config/metric-set/MS1.json
```

### Profile Identity

- **Profile ID:** `MS1`

### Mandatory Client Metrics

- request count;
- success rate percent;
- failure count;
- mean response time;
- p50 response time;
- p95 response time;
- p99 response time;
- throughput.

### Mandatory Cluster Metrics

- node CPU percent;
- node memory percent;
- pod CPU millicores;
- pod memory MiB;
- pod placement;
- pod restart count;
- pod readiness.

### Governance Rule

Operators must not change the metric basket from one campaign to another if the results are meant to be comparable.

---

## Statistical Rigor Governance

### File

```text
config/statistical-rigor/SR1.json
```

### Profile Identity

- **Profile ID:** `SR1`

### Key Rules

- required replica count: `3`
- minimum successful replicas: `3`
- cool-down between replicas: `10s`
- cool-down between scenarios: `20s`

### Tracked Metrics

- request count;
- failure count;
- mean response time;
- p50 response time;
- p95 response time;
- p99 response time;
- throughput.

### Variability Thresholds

- mean response time CV: `10.0%`
- p95 response time CV: `12.5%`
- throughput CV: `12.5%`

### Governance Rule

Exploratory evidence and consolidated evidence are not equivalent. If a family is governed by `SR1`, then A/B/C replicas and variability checks are part of the acceptance model.

---

## Pilot Consolidation Governance

### File

```text
config/pilot-consolidation/CP1.json
```

### Profile Identity

- **Profile ID:** `CP1`

### Purpose

`CP1` defines the controlled consolidated benchmark campaign for all pilot families.

### Key Rules

- output root: `results/pilot/consolidated`
- stop on first failure: `true`
- warm-up duration: `45s`
- measurement duration: `3m`

### Governed Families

- `worker-count`
- `workload`
- `models`
- `placement`

### Replica Regime

All consolidated pilot families use replicas:

- `A`
- `B`
- `C`

### Governance Rule

Once a campaign enters the consolidated stage, it must use the explicit `CP1` profile rather than ad hoc launcher arguments.

---

## Technical Diagnosis Governance

### File

```text
config/technical-diagnosis/TD1.json
```

### Profile Identity

- **Profile ID:** `TD1`

### Purpose

`TD1` defines the first evidence-based diagnosis stage that interprets consolidated pilot results.

### Governed Result Roots

- `results/pilot/consolidated/worker-count`
- `results/pilot/consolidated/workload`
- `results/pilot/consolidated/models`
- `results/pilot/consolidated/placement`

### Intended Diagnostic Outputs

The diagnosis profile is aligned with two complementary output layers:

- **strong findings**, emitted when the observed signal is sufficiently clear and diagnostically meaningful;
- **family-level judgments**, emitted for every governed family so that a family may still receive an explicit interpretation even when the signal is weak, non-dominant, or supported only by incomplete evidence.

Strong findings may include patterns such as:

- worker count initial gain;
- worker count diminishing returns;
- workload saturation signal;
- model size penalty;
- placement effect.

Family-level judgments may instead express outcomes such as:

- strong signal;
- weak signal;
- insufficient evidence.

### Governance Rule

Diagnosis is a governed post-processing stage based on consolidated evidence, not a free-form narrative written from memory. It must not be reduced to strong findings only: the governed output is expected to provide an explicit family-level interpretation even when a family does not justify a dominant finding.

---


## Reporting and Visualization Governance

### File

```text
config/reporting/RP1.json
```

### Profile Identity

- **Profile ID:** `RP1`

### Purpose

`RP1` defines the advisor-facing reporting layer that runs after technical diagnosis and before the completion gate. Its purpose is to convert the governed measurements and diagnosis context into readable global and per-sweep reports.

### Governed Output Location

```text
results/reporting/
```

The current reporting profile writes one stable report directory, not a timestamped hierarchy. Rerunning the reporting launcher refreshes the managed reporting artifacts in that directory.

### Expected Output Layers

The reporting phase is expected to produce:

- a global Markdown report;
- a global HTML report;
- a scenario summary CSV;
- a reporting manifest;
- charts organized by sweep family;
- one dedicated Markdown and HTML report for each governed sweep family.

### Governance Rule

Reporting is not a substitute for diagnosis. Quantitative charts are generated from benchmark measurements, while diagnosis outputs provide interpretative context, unsupported-scenario evidence, and family-level readings.

---

## Completion Gate Governance

### File

```text
config/completion-gate/CG1.json
```

### Profile Identity

- **Profile ID:** `CG1`

### Purpose

`CG1` defines the closure criteria for the current exploratory characterization cycle.

### Required Families

- `worker-count`
- `workload`
- `models`
- `placement`

### Gate Conditions

The completion gate expects, among other things:

- strict scenario coverage;
- minimum replicas per scenario: `2`;
- bounded variability;
- minimum findings: `3`;
- minimum finding groups satisfied: `2`;
- cluster-side evidence present.

### Governance Rule

A phase is not considered complete because the scripts exist. It is complete only when the configured gate criteria are met.

---

## Governance Decision Matrix

Use the following matrix when deciding whether an action is allowed.

| Question | Allowed? | Rule |
|---|---:|---|
| Can the official baseline be overridden from launcher parameters? | No | `B0` lock rules |
| Can a pilot scenario vary more than one dimension? | No | single-delta family design |
| Can a result be retained without a run manifest? | No | `RC1` required metadata |
| Can a result be retained without cluster-side evidence? | No | `CS1` |
| Can a consolidated campaign skip A/B/C replicas? | No | `SR1` / `CP1` |
| Can a placement result be interpreted as full-topology mobility? | No | placement family boundary |
| Can a diagnosis be issued from exploratory-only runs? | Not as governed diagnosis | `TD1` expects consolidated evidence |
| Can the phase be declared complete without the completion gate? | No | `CG1` |

---

## Pre-Execution Governance Checklist

Before launching any official or consolidated activity, confirm the following.

- [ ] `B0.json` exists and remains the official locked baseline.
- [ ] The intended scenario belongs to exactly one family and changes one dimension only.
- [ ] The run will use the `RC1` naming and metadata convention.
- [ ] The operator understands whether the run is exploratory, baseline, pilot, or consolidated.
- [ ] Warm-up and measurement durations are governed by `WM1` or `CP1`, not by ad hoc values.
- [ ] The protocol sequence from `EP1` will be respected.
- [ ] Cluster-side evidence will be collected under `CS1`.
- [ ] Metrics will be evaluated against `MS1`.
- [ ] If the run belongs to a consolidated family, `SR1` and `CP1` will be applied.
- [ ] Any later diagnosis will be generated from governed inputs under `TD1`.
- [ ] Phase closure will be validated through `CG1`.

---

## Common Governance Mistakes to Avoid

### 1. Treating exploratory runs as baseline evidence

Exploratory load checks are useful, but they do not replace the locked baseline or consolidated campaign evidence.

### 2. Changing multiple dimensions manually

Do not change worker count, model, and workload together and then classify the run under a controlled family.

### 3. Overriding baseline values from the command line

If the baseline is locked, launcher overrides must not silently change the baseline meaning.

### 4. Ignoring interpretation boundaries

The placement family is not a full-topology mobility study. The worker-count family is not a generic cluster scaling study across arbitrary placements.

### 5. Keeping results without manifests and evidence

A CSV without run metadata and cluster-side artifacts is not governed evidence.

### 6. Closing the phase by intuition

The exploratory characterization cycle closes only through the configured completion gate.

---

## Success Criteria

This governance layer is correctly applied when:

- the official baseline is unique and stable;
- every pilot scenario is a single-dimension variation from the baseline;
- every retained run is uniquely traceable;
- every official or consolidated run uses explicit profiles for phases, protocol, metrics, evidence, and rigor;
- interpretation boundaries are explicitly respected;
- closure decisions are made through the configured gate rather than by operator intuition.

---

## Next Step

After governance has been validated and accepted, proceed to:

```text
docs/runbooks/03-kubernetes-manifests-and-topology-deployment.md
```

That runbook covers how the governed scenario model is materialized into Kubernetes compositions and deployed into the target cluster.
