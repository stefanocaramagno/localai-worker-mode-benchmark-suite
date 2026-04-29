# 07. Pilot Sweeps Execution

## Objective

This runbook defines how to execute the **pilot sweep phase** of the LocalAI worker-mode benchmark pipeline.

The purpose of this phase is to execute the first structured comparative benchmark families after:

- cluster access is stable;
- the repository execution environment is ready;
- the Kubernetes deployment model is understood;
- pre-check and API smoke validation are operational;
- the official baseline can be executed successfully;
- exploratory load validation has already confirmed that the system can sustain controlled synthetic traffic.

The pilot sweep phase is the first point in the pipeline where scenario families are executed intentionally to compare controlled variations against the locked baseline. This phase is still **pilot-level**, not yet statistically consolidated, but it must already be executed with disciplined scenario governance, artifact collection, and interpretation boundaries.

---

## When to Use This Runbook

Use this runbook when you need to:

- execute the first controlled benchmark comparison across one sweep family;
- validate that scenario JSON files, Kubernetes compositions, and launchers are aligned;
- confirm that a single varying dimension behaves coherently against the official baseline;
- generate pilot-level artifacts before the consolidated benchmark campaign;
- identify whether a scenario family is operationally viable and worth consolidating later.

Use this runbook only after all of the following are already true:

1. the cluster is reachable and healthy;
2. the local execution environment is prepared;
3. the scenario governance model is understood;
4. the target topology can be deployed successfully;
5. pre-check and smoke validation pass;
6. the official baseline has already been executed successfully at least once;
7. exploratory load validation has already confirmed end-to-end request generation.

Do **not** use this runbook for:

- ad hoc manual testing;
- official baseline execution;
- consolidated pilot campaigns;
- statistical rigor evaluation;
- technical diagnosis generation;
- completion gate closure.

---

## Scope

This runbook covers execution of the four pilot sweep families currently modeled in the repository:

1. **Worker Count Sweep**
2. **Workload Sweep**
3. **Model Sweep**
4. **Placement Sweep**

For each family, the runbook explains:

- the execution intent;
- the scenarios currently defined in the repository;
- the dimension that is allowed to vary;
- the dimensions that must remain fixed;
- the launcher to use;
- the expected output location;
- the correct interpretation boundaries.

This runbook does **not** cover:

- the internal design of Kubernetes manifests;
- cluster bootstrap;
- detailed pre-check troubleshooting;
- post-processing or diagnosis scripts;
- consolidated campaign logic.

---

## Phase Position in the Pipeline

The pilot sweep phase sits after baseline validation and before consolidated campaigns.

Recommended pipeline order:

1. cluster bootstrap and access validation;
2. repository and execution environment setup;
3. scenario model and baseline governance;
4. Kubernetes deployment and topology validation;
5. technical pre-check and API smoke validation;
6. official baseline execution;
7. exploratory load validation;
8. **pilot sweeps execution**;
9. consolidated pilot benchmarks;
10. statistical rigor assessment;
11. technical diagnosis;
12. reporting and visualization;
13. completion gate and phase closure.

---

## Local Endpoint Requirement

The pilot sweep phase assumes that the LocalAI server endpoint is reachable from the execution host. In the current implementation, when the sweep commands use `http://localhost:8080`, the launcher automatically checks the local endpoint and creates the required port-forward toward `service/localai-server` if it is not already available.

A manual port-forward is therefore not part of the standard sweep procedure and should only be used for exceptional standalone debugging outside the launcher flow.

## Governing Principle

All pilot sweeps in this repository follow a strict design rule:

> **Only one experimental dimension is allowed to vary inside a given sweep family. All remaining dimensions must remain inherited from the locked baseline `B0`.**

This rule is fundamental. It preserves interpretability and ensures that pilot results remain attributable to the intended variable.

The locked baseline is defined in:

```text
config/scenarios/baseline/B0.json
```

At the time of writing, the baseline resolves to:

- **Model scenario:** `M1`
- **Resolved model:** `llama-3.2-1b-instruct:q4_k_m`
- **Worker scenario:** `W2`
- **Resolved worker count:** `2`
- **Placement scenario:** `PL1`
- **Resolved placement type:** `colocated_sc_app_02`
- **Workload scenario:** `WL2`
- **Resolved load:** `2 users`, `spawn rate 1`, `run time 2m`
- **Topology composition:** `infra/k8s/compositions/topology/colocated-sc-app-02-w2`

All pilot scenario families must be interpreted as controlled deviations from that reference configuration.

---

## Repository Components Used in This Phase

### PowerShell launchers

- `scripts/load/pilot/Start-PilotWorkerCountSweep.ps1`
- `scripts/load/pilot/Start-PilotWorkloadSweep.ps1`
- `scripts/load/pilot/Start-PilotModelSweep.ps1`
- `scripts/load/pilot/Start-PilotPlacementSweep.ps1`

### Bash launchers

- `scripts/load/pilot/start-pilot-worker-count-sweep.sh`
- `scripts/load/pilot/start-pilot-workload-sweep.sh`
- `scripts/load/pilot/start-pilot-model-sweep.sh`
- `scripts/load/pilot/start-pilot-placement-sweep.sh`

### Scenario configuration directories

- `config/scenarios/pilot/worker-count`
- `config/scenarios/pilot/workload`
- `config/scenarios/pilot/models`
- `config/scenarios/pilot/placement`

### Common supporting configuration

- `config/scenarios/baseline/B0.json`
- `config/precheck/TC1.json`
- `config/phases/WM1.json`
- `config/protocol/EP1.json`
- `config/cluster-capture/CS1.json`
- `config/metric-set/MS1.json`

### Common runtime assets

- `load-tests/locust/locustfile.py`
- `scripts/validation/precheck/*`
- `scripts/validation/smoke/*`
- `scripts/validation/cluster-side/*`

---

## Common Preconditions for All Pilot Sweeps

Before launching any pilot scenario, verify all of the following:

### Cluster preconditions

- VPN is active;
- the expected kubeconfig is available;
- the cluster is reachable;
- all expected nodes are in `Ready` state;
- the target namespace is valid;
- the metrics API is functional;
- no unresolved stale workload remains from a broken previous execution.

### Application preconditions

- the LocalAI server is deployable and reachable;
- the intended model is available for the chosen scenario family;
- the API endpoint responds correctly to `/v1/models`;
- a smoke test can pass successfully using the same base URL and model.

### Local execution preconditions

- `kubectl` is installed and reachable in `PATH`;
- `locust` is installed and reachable in `PATH`;
- Python is available according to the repository runbook convention (`python` in PowerShell, `python3` in Bash; `python` in Bash is acceptable only if that environment does not expose `python3` and the Bash scripts can resolve it consistently);
- commands are launched from a consistent repository root;
- the correct runbook sequence has already been followed.

### Methodological preconditions

- the official baseline is already locked and understood;
- the sweep family being executed is clearly identified;
- the operator understands which dimension may vary and which must remain frozen;
- the result directories from earlier runs are preserved or intentionally archived.

---

## Replica Model

Every pilot scenario launcher requires a **replica identifier**.

The accepted values are:

- `A`
- `B`
- `C`

Even during the pilot phase, the replica label is important because it:

- prevents artifact overwrites;
- enables later comparison;
- keeps the transition toward consolidated campaigns smooth;
- aligns the sweep execution model with the statistical rigor phase.

At the pilot stage, you may begin with a single replica, typically `A`, and only execute `B` and `C` when operationally justified.

---

## Sweep Families

## 1. Worker Count Sweep

### Intent

This sweep measures the impact of **active RPC worker count** while keeping the remaining dimensions inherited from the baseline.

### Scenarios currently defined

- `W1` — single RPC worker
- `W2` — two RPC workers
- `W3` — three RPC workers
- `W4` — four RPC workers

Scenario files:

```text
config/scenarios/pilot/worker-count/W1.json
config/scenarios/pilot/worker-count/W2.json
config/scenarios/pilot/worker-count/W3.json
config/scenarios/pilot/worker-count/W4.json
```

### What varies

- active worker count;
- topology composition derived from the corresponding worker-count scenario.

### What remains fixed

- model family member inherited from `B0`;
- workload profile inherited from `B0`;
- prompt inherited from `B0` unless explicitly overridden;
- request timeout inherited from `B0` unless explicitly overridden;
- placement mode inherited from the worker-count scenario notes and baseline assumptions.

### Current interpretation boundary

The repository currently models this sweep as a **worker-count-only variation anchored to the locked baseline**, keeping the active RPC workers co-located on `sc-app-02` for the relevant scenarios.

This means the sweep must be interpreted as:

> the effect of worker-count variation under a constant co-located placement policy derived from the baseline.

It must **not** be interpreted as a general scalability statement independent of placement.

### Default output root

```text
results/pilot/worker-count
```

### PowerShell execution example

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\pilot\Start-PilotWorkerCountSweep.ps1" `
  -Scenario W1 `
  -Replica A
```

### Bash execution example

```bash
bash ./scripts/load/pilot/start-pilot-worker-count-sweep.sh \
  --scenario W1 \
  --replica A
```

### Recommended execution order

Run the family in increasing worker-count order:

1. `W1`
2. `W2`
3. `W3`
4. `W4`

This order is recommended because it exposes early feasibility issues before entering more demanding topologies.

---

## 2. Workload Sweep

### Intent

This sweep measures the impact of **input load profile** while keeping model, worker topology, and placement fixed to the baseline.

### Scenarios currently defined

- `WL1` — smoke single user
- `WL2` — low load two users
- `WL3` — small concurrency four users

Scenario files:

```text
config/scenarios/pilot/workload/WL1.json
config/scenarios/pilot/workload/WL2.json
config/scenarios/pilot/workload/WL3.json
```

### What varies

- Locust user count;
- spawn rate;
- run time;
- output subdirectory derived from the workload scenario.

### What remains fixed

- baseline model;
- baseline worker scenario;
- baseline placement scenario;
- prompt inherited from the baseline unless explicitly overridden;
- request timeout inherited from the baseline unless explicitly overridden.

### Current interpretation boundary

This sweep must be interpreted as:

> the effect of controlled workload intensity variation against a fixed worker-mode topology and fixed baseline model.

It must **not** be interpreted as a comparison between different orchestration policies.

### Default output root

```text
results/pilot/workload
```

### PowerShell execution example

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\pilot\Start-PilotWorkloadSweep.ps1" `
  -Scenario WL1 `
  -Replica A
```

### Bash execution example

```bash
bash ./scripts/load/pilot/start-pilot-workload-sweep.sh \
  --scenario WL1 \
  --replica A
```

### Recommended execution order

Run in ascending pressure order:

1. `WL1`
2. `WL2`
3. `WL3`

This order helps validate the load generation pipeline before moving into more demanding request patterns.

---

## 3. Model Sweep

### Intent

This sweep measures the impact of the **resolved model variant** while keeping worker count, placement, and workload inherited from the baseline.

### Scenarios currently defined

- `M1` — baseline `llama-3.2-1b-instruct:q4_k_m`
- `M2` — `llama-3.2-1b-instruct:q8_0`
- `M3` — `llama-3.2-3b-instruct:q4_k_m`
- `M4` — `llama-3.2-3b-instruct:q8_0`

Scenario files:

```text
config/scenarios/pilot/models/M1.json
config/scenarios/pilot/models/M2.json
config/scenarios/pilot/models/M3.json
config/scenarios/pilot/models/M4.json
```

### What varies

- resolved model name;
- server manifest composition associated with that model.

### What remains fixed

- worker scenario inherited from `B0`;
- placement scenario inherited from `B0`;
- workload scenario inherited from `B0`;
- prompt inherited from `B0` unless explicitly overridden;
- request timeout inherited from `B0` unless explicitly overridden.

### Current interpretation boundary

This sweep must be interpreted as:

> the effect of model choice under a fixed worker-mode topology, fixed placement, and fixed input workload.

Because server-side model manifests change across this family, this sweep captures model-driven runtime differences, not just request payload differences.

### Default output root

```text
results/pilot/models
```

### PowerShell execution example

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\pilot\Start-PilotModelSweep.ps1" `
  -Scenario M1 `
  -Replica A
```

### Bash execution example

```bash
bash ./scripts/load/pilot/start-pilot-model-sweep.sh \
  --scenario M1 \
  --replica A
```

### Recommended execution order

Run from smallest expected footprint to largest:

1. `M1`
2. `M2`
3. `M3`
4. `M4`

This order reduces the risk of starting the family with a model too demanding for the current cluster state.

---

## 4. Placement Sweep

### Intent

This sweep measures the impact of **worker placement policy** while keeping worker count, model, and workload inherited from the baseline.

### Scenarios currently defined

- `PL1` — co-located on `sc-app-02`
- `PL2` — distributed two-node placement

Scenario files:

```text
config/scenarios/pilot/placement/PL1.json
config/scenarios/pilot/placement/PL2.json
```

### What varies

- topology directory;
- worker placement policy.

### What remains fixed

- baseline worker count;
- baseline model;
- baseline workload;
- prompt inherited from the baseline unless explicitly overridden;
- request timeout inherited from the baseline unless explicitly overridden.

### Current interpretation boundary

The current repository models the placement family as a **worker-placement-only sweep** with the server kept fixed by infrastructure and deployment design.

Therefore, this family must be interpreted as:

> the effect of worker distribution relative to a fixed server location.

It must **not** be described as a full-placement sweep of the entire application topology.

### Default output root

```text
results/pilot/placement
```

### PowerShell execution example

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\pilot\Start-PilotPlacementSweep.ps1" `
  -Scenario PL1 `
  -Replica A
```

### Bash execution example

```bash
bash ./scripts/load/pilot/start-pilot-placement-sweep.sh \
  --scenario PL1 \
  --replica A
```

### Recommended execution order

Run in this order:

1. `PL1` — baseline co-located reference
2. `PL2` — distributed two-node variation

This makes comparison against the locked baseline more immediate.

---

## Common Launcher Behavior

All pilot sweep launchers share the same general execution model.

Unless explicitly overridden, they:

- resolve the locked baseline;
- validate scenario file consistency;
- validate required Kubernetes apply targets when relevant;
- use `TC1` for pre-check;
- use `WM1` for warm-up and measurement separation;
- use `EP1` for protocol sequencing;
- use `CS1` for cluster-side capture;
- use `MS1` for minimum metric-set governance;
- execute API smoke validation unless explicitly skipped;
- generate run metadata and cluster-side artifacts.

This is intentional. Pilot sweeps are already structured benchmark executions and must not bypass validation and evidence collection unless there is a strong operational justification.

---

## Recommended Family Execution Strategy

The recommended order across families is:

1. **Worker Count Sweep**
2. **Workload Sweep**
3. **Model Sweep**
4. **Placement Sweep**

This order is operationally sound because:

- worker-count behavior helps validate topology scaling assumptions early;
- workload variation then stresses the known topology;
- model variation is introduced only after the load path is stable;
- placement is compared after the previous dimensions are already operationally understood.

If current cluster conditions suggest a different order, document the reason explicitly in the campaign notes.

---

## Standard Pilot Execution Pattern

For every pilot scenario, follow this sequence:

1. ensure the cluster is in a clean, known state;
2. ensure baseline assumptions are still valid;
3. run the scenario launcher with replica `A` first;
4. let the launcher perform pre-check, deployment validation, API smoke, warm-up, measurement, and artifact collection;
5. verify the generated outputs;
6. decide whether the scenario is suitable for additional replicas or whether it should remain a single pilot run;
7. preserve the artifacts exactly as generated.

Do not change two dimensions at once during pilot execution.

---

## Output Structure

Each sweep family writes results under its own root.

### Worker Count Sweep

```text
results/pilot/worker-count/<scenario outputSubdir>/
```

Examples:

```text
results/pilot/worker-count/W1_worker_count_1/
results/pilot/worker-count/W2_worker_count_2/
results/pilot/worker-count/W3_worker_count_3/
results/pilot/worker-count/W4_worker_count_4/
```

### Workload Sweep

```text
results/pilot/workload/<scenario outputSubdir>/
```

Examples:

```text
results/pilot/workload/WL_smoke_single_user/
results/pilot/workload/WL2_low_load_two_users/
results/pilot/workload/WL3_small_concurrency_four_users/
```

### Model Sweep

```text
results/pilot/models/<scenario outputSubdir>/
```

Examples:

```text
results/pilot/models/M1_llama32_1b_q4km/
results/pilot/models/M2_llama32_1b_q8_0/
results/pilot/models/M3_llama32_3b_q4km/
results/pilot/models/M4_llama32_3b_q8_0/
```

### Placement Sweep

```text
results/pilot/placement/<scenario outputSubdir>/
```

Examples:

```text
results/pilot/placement/PL2_distributed_two_node/
results/pilot/placement/PL1_colocated_scapp02/
```

Within each scenario directory, expect run-specific artifacts associated with the chosen replica and protocol.

---

## Expected Artifact Categories

For every pilot scenario, expect these categories of outputs.

### Run metadata

- scenario manifest;
- phase manifest;
- protocol manifest;
- metric-set manifest;
- resolved scenario metadata;
- pre-check summaries.

### Warm-up artifacts

If warm-up is enabled:

- warm-up Locust CSV files;
- warm-up prefix separate from measurement.

### Measurement artifacts

- `*_stats.csv`
- `*_stats_history.csv`
- `*_failures.csv`
- `*_exceptions.csv`

### Cluster-side artifacts

- `nodes-wide.txt`
- `top-nodes.txt`
- `pods-wide.txt`
- `top-pods.txt`
- `services.txt`
- `events.txt`
- `pods-describe.txt`
- associated cluster-capture metadata files.

---

## Interpretation Rules

Pilot sweeps are structured, but still exploratory in analytical maturity.

Apply the following interpretation rules:

1. treat each family only as a comparison of its intended varying dimension;
2. do not generalize pilot results beyond the sweep definition;
3. do not merge conclusions from different families unless later consolidated evidence supports it;
4. treat severe degradation, instability, or failure as findings, not as silent noise;
5. preserve unexpected results exactly as observed.

Examples:

- if a high worker-count scenario becomes unstable, that instability is part of the pilot evidence;
- if a larger model degrades latency sharply, that is a model-sweep observation, not yet a final global conclusion;
- if distributed placement changes behavior, interpret the result relative to the fixed server position currently modeled in the repository.

---

## Success Criteria

A pilot scenario execution can be considered successful when all of the following are true:

- the launcher either exits successfully or produces an explicit unsupported classification that is coherent with the current frozen constraints;
- the intended scenario is resolved correctly;
- API smoke validation passes for benchmarkable runs;
- warm-up and measurement are both executed as expected for runs that reach benchmark execution;
- Locust measurement artifacts are present for runs that complete normally;
- unsupported scenarios, when applicable, generate their dedicated `*_unsupported.json` and `*_unsupported.txt` artifacts;
- cluster-side evidence is present whenever the run reaches the collection stages implemented by the launcher;
- no artifact overwrite or naming conflict occurs;
- the run remains interpretable within the sweep family definition.

A pilot family can be considered operationally ready for consolidation when:

- all scenarios in the family can be executed or meaningfully classified;
- artifacts are complete and organized;
- scenario behavior is interpretable;
- no unresolved procedural blockers remain.

---

## Failure Handling

If a pilot run fails, do not immediately retry blindly.

Use this decision process:

### Case 1 — Infrastructure failure

Examples:

- VPN disconnected;
- cluster unavailable;
- nodes not ready;
- metrics API unavailable.

Action:

- stop the sweep;
- restore infrastructure health;
- restart from pre-check.

### Case 2 — Deployment or topology failure

Examples:

- pods remain `Pending`;
- Kubernetes target path is invalid;
- referenced topology cannot be applied cleanly.

Action:

- stop the scenario;
- inspect the topology or cluster capacity;
- re-run only after the cause is understood.

### Case 3 — Application failure

Examples:

- `/v1/models` fails;
- API smoke fails;
- request payload is rejected.

Action:

- stop the scenario;
- validate the model configuration and LocalAI deployment;
- re-run only after smoke validation passes again.

### Case 4 — Performance degradation without hard failure

Examples:

- very high latency;
- repeated failures under load;
- obvious saturation symptoms.

Action:

- preserve all artifacts;
- classify the scenario as degraded but informative;
- do not erase the run unless it is technically invalid.

---

## Recommended Verification Commands After Each Run

### Inspect scenario result directory

PowerShell example:

```powershell
Get-ChildItem .\results\pilot\worker-count\W1_worker_count_1
```

Bash example:

```bash
find ./results/pilot/worker-count/W1_worker_count_1 -maxdepth 1 -type f | sort
```

### Verify pod placement

PowerShell example:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get pods -n genai-thesis -o wide
```

Bash example:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get pods -n genai-thesis -o wide
```

### Verify node utilization

PowerShell example:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig top nodes
```

Bash example:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig top nodes
```

### Verify pod utilization

PowerShell example:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig top pods -n genai-thesis
```

Bash example:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig top pods -n genai-thesis
```

---

## Transition to the Next Phase

Once one or more pilot sweep families have been executed successfully, the next phase is **consolidated pilot benchmark execution**.

Do not move to that phase until:

- the pilot family outputs are complete;
- the artifacts are interpretable;
- no unresolved procedural blockers remain;
- the family is worth re-running under stricter consolidation rules.

The next runbook to use after this one is:

```text
docs/runbooks/08-consolidated-pilot-benchmarks.md
```

---

## Summary

This runbook formalizes how to execute the four structured pilot sweep families already modeled in the repository.

The critical discipline is simple:

- choose the correct family;
- vary only the intended dimension;
- preserve all inherited baseline dimensions;
- execute with pre-check, smoke, warm-up, measurement, and cluster-side evidence;
- interpret the results only within the sweep family boundary.

That discipline is what makes the later consolidated phase meaningful and defensible.
