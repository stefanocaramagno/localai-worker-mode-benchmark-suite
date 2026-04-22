# 05. Official Baseline Execution

## Objective

This runbook describes how to execute the **official locked baseline** for the LocalAI worker-mode benchmark pipeline.

The baseline is the unique reference configuration used to compare all subsequent controlled variations. It must be executed in a repeatable and traceable way, with full pre-check, API smoke validation, warm-up separation, measurement, client-side artifact generation, and mandatory cluster-side evidence collection.

This document applies to both supported execution environments:

- **PowerShell on Windows**
- **Bash on Linux/macOS**

---

## When to Use This Runbook

Use this runbook when you need to:

- execute the official baseline for the first time;
- re-run the baseline after infrastructure or configuration changes;
- generate the reference artifacts used by pilot sweeps and consolidated analysis;
- verify that the current cluster state can support the locked reference scenario;
- produce reproducible baseline evidence before comparing worker-count, workload, model, or placement variations.

Do **not** use this runbook for exploratory tests, pilot sweeps, or post-processing phases. Those activities are covered by separate runbooks.

---

## Scope

This runbook covers the complete baseline execution flow from launcher invocation to artifact verification, including:

1. baseline configuration resolution;
2. controlled deployment order validation;
3. technical pre-check;
4. API smoke validation;
5. optional warm-up phase;
6. measurement phase;
7. client-side metrics collection;
8. mandatory cluster-side collection before and after the run;
9. run manifest generation;
10. baseline artifact verification.

This runbook does **not** cover:

- cluster creation;
- repository bootstrap;
- manual topology design;
- pilot sweeps;
- technical diagnosis;
- completion gate evaluation.

---

## Baseline Definition

The official locked baseline is defined in:

```text
config/scenarios/baseline/B0.json
```

At the time of writing, the baseline resolves to the following reference configuration:

- **Baseline ID:** `B0`
- **Mode:** `worker`
- **Model scenario:** `M1`
- **Resolved model:** `llama-3.2-1b-instruct:q4_k_m`
- **Worker scenario:** `W2`
- **Resolved worker count:** `2`
- **Placement scenario:** `PL1`
- **Resolved placement type:** `colocated_sc_app_02`
- **Workload scenario:** `WL2`
- **Resolved load:** `2 users`, `spawn rate 1`, `run time 2m`
- **Topology composition:** `infra/k8s/compositions/topology/colocated-sc-app-02-w2`
- **Server manifest:** `infra/k8s/compositions/server/models/m1`
- **Results root:** `results/baseline/official`
- **Base URL:** `http://localhost:8080`

### Local Endpoint Requirement

The baseline uses `http://localhost:8080` as the execution endpoint. In the current implementation you do **not** need to start a manual port-forward before launching the baseline. The launcher automatically verifies whether the local endpoint is reachable and, when required, creates the port-forward toward `service/localai-server` before the precheck, smoke, warm-up, and measurement flow begins.

A manual port-forward is therefore no longer part of the standard baseline procedure and should only be used for exceptional standalone debugging outside the launcher flow.

The baseline file also declares the following lock rules:

- model, worker count, placement, and workload must **not** be overridden;
- the baseline must remain the unique reference configuration for the current characterization phase;
- all future comparisons must be interpreted as controlled variations from this file.

---

## Related Configuration Files

The baseline launcher relies on the following configuration files by default:

```text
config/scenarios/baseline/B0.json
config/precheck/TC1.json
config/phases/WM1.json
config/protocol/EP1.json
config/cluster-capture/CS1.json
config/metric-set/MS1.json
config/conventions/RC1.json
```

Their roles are summarized below.

### `TC1` — Technical Pre-check
Controls mandatory pre-run validation, including:

- expected ready nodes;
- allowed pod phases;
- metrics API availability;
- maximum allowed node CPU and memory percentages;
- restart thresholds.

### `WM1` — Warm-up / Measurement Separation
Defines phase separation rules, including:

- warm-up enabled by default;
- warm-up duration = `30s`;
- warm-up concurrency matching the measurement phase;
- distinct CSV suffix for warm-up artifacts.

### `EP1` — Execution Protocol
Defines the canonical protocol sequence:

1. controlled cleanup;
2. scenario deployment;
3. technical pre-check;
4. API smoke validation;
5. warm-up;
6. measurement;
7. client-side artifact collection;
8. cluster-side collection;
9. final snapshot;
10. cleanup or restore placeholder.

### `CS1` — Cluster-side Collection
Defines mandatory infrastructure evidence collection before and after the run.

### `MS1` — Minimum Metric Set
Defines the canonical metric set that must always be available or derivable.

### `RC1` — Run Convention
Defines run ID format, CSV naming, and required run metadata.

---

## Prerequisites

Before executing the official baseline, ensure that all of the following conditions are satisfied.

### Local prerequisites

The local execution environment must already be prepared according to the repository setup runbook. At minimum, the following commands must be available:

- `kubectl`
- `locust`
- Python available according to the repository runbook convention (`python` in PowerShell, `python3` in Bash; `python` in Bash is acceptable only if that environment does not expose `python3` and the Bash scripts can resolve it consistently)

In addition:

- the VPN connection must be active;
- the `kubeconfig` file must be available at the expected path or explicitly overridden;
- the repository must be checked out locally;
- the current working directory should be the repository root.

### Cluster prerequisites

The target cluster must already exist and be reachable. In particular:

- all expected nodes must be `Ready`;
- the project namespace must be valid or deployable;
- the metrics API must be working;
- the cluster must not already be saturated;
- no stale project pods should remain from a previous inconsistent run.

### Repository prerequisites

The following paths must exist:

```text
config/scenarios/baseline/B0.json
scripts/load/baseline/start-official-baseline.sh
scripts/load/baseline/Start-OfficialBaseline.ps1
load-tests/locust/locustfile.py
```

---

## Default Deployment Inputs Used by the Baseline Launcher

The baseline launcher resolves and applies the reference deployment set from the baseline file. The effective deployment order is built around the following manifest targets:

```text
infra/k8s/compositions/foundation/namespace
infra/k8s/compositions/foundation/storage
infra/k8s/compositions/shared/rpc-workers-services
infra/k8s/compositions/server/models/m1
infra/k8s/compositions/topology/colocated-sc-app-02-w2
```

The launcher validates these paths before attempting deployment.

---

## Baseline Execution Outputs

The baseline launcher writes artifacts under:

```text
results/baseline/official/B0_official_locked/
```

The run ID is built from the baseline ID and replica, using:

```text
B0_runA
B0_runB
B0_runC
```

The following categories of artifacts are expected:

### Run metadata

- baseline lock file
- phase manifest
- protocol manifest
- metric-set manifest
- pre-check JSON and text summaries

### Warm-up artifacts

If warm-up is enabled, the launcher generates a distinct Locust CSV prefix for warm-up.

Expected files include:

- `*_warmup_stats.csv`
- `*_warmup_stats_history.csv`
- `*_warmup_failures.csv`
- `*_warmup_exceptions.csv`

### Measurement artifacts

Expected Locust measurement files include:

- `*_stats.csv`
- `*_stats_history.csv`
- `*_failures.csv`
- `*_exceptions.csv`

### Cluster-side artifacts

The cluster-side collector writes pre- and post-run infrastructure evidence. Expected outputs include:

- `nodes-wide.txt`
- `top-nodes.txt`
- `pods-wide.txt`
- `top-pods.txt`
- `services.txt`
- `events.txt`
- `pods-describe.txt`
- corresponding manifest and summary files

---

## Recommended Execution Model

The official baseline should be executed in the following disciplined way:

1. start from a controlled, known cluster state;
2. execute the baseline with a single replica first (typically `A`);
3. verify all generated artifacts;
4. if the run is valid, execute additional replicas (`B`, `C`) only when required by the current campaign;
5. preserve all artifacts exactly as generated.

The baseline should not be edited or treated as an exploratory sandbox.

---

## Execution Procedure — PowerShell

From the repository root, execute:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\baseline\Start-OfficialBaseline.ps1" -Replica A
```

### Optional parameters

The launcher supports explicit overrides for selected infrastructure and runtime inputs, including:

- `-BaselineConfig`
- `-BaseUrl`
- `-LocustFile`
- `-OutputRoot`
- `-PrecheckConfig`
- `-Kubeconfig`
- `-Namespace`
- `-SkipPrecheck`
- `-PhaseConfig`
- `-WarmUpDuration`
- `-MeasurementDuration`
- `-SkipWarmUp`
- `-ProtocolConfig`
- `-ClusterCaptureConfig`
- `-MetricSetConfig`
- `-SkipApiSmoke`
- `-DryRun`

### Example with explicit kubeconfig and dry run

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\baseline\Start-OfficialBaseline.ps1" `
  -Replica A `
  -Kubeconfig .\config\cluster-access\kubeconfig `
  -DryRun
```

Use `-DryRun` whenever you want to inspect the resolved deployment sequence, commands, and artifact paths without executing the benchmark.

---

## Execution Procedure — Bash

From the repository root, execute:

```bash
bash ./scripts/load/baseline/start-official-baseline.sh --replica A
```

### Optional parameters

The Bash launcher supports the same logical inputs, including:

- `--baseline-config`
- `--base-url`
- `--locust-file`
- `--output-root`
- `--precheck-config`
- `--kubeconfig`
- `--namespace`
- `--skip-precheck`
- `--phase-config`
- `--warm-up-duration`
- `--measurement-duration`
- `--skip-warm-up`
- `--protocol-config`
- `--cluster-capture-config`
- `--metric-set-config`
- `--skip-api-smoke`
- `--dry-run`

### Example with explicit kubeconfig and dry run

```bash
bash ./scripts/load/baseline/start-official-baseline.sh \
  --replica A \
  --kubeconfig ./config/cluster-access/kubeconfig \
  --dry-run
```

---

## Expected Runtime Flow

A valid baseline execution should follow the sequence below.

### 1. Baseline resolution

The launcher reads `B0.json` and resolves:

- baseline ID;
- model scenario and model name;
- worker scenario and worker count;
- placement scenario and placement type;
- workload scenario;
- topology and server manifest targets;
- base URL and request parameters.

### 2. Required manifest validation

The launcher validates that all referenced Kubernetes apply targets exist and are resolvable.

### 3. Protocol and phase initialization

The launcher prepares:

- run ID;
- output directory;
- CSV prefixes;
- phase manifest path;
- protocol manifest path;
- metric-set manifest path.

### 4. Technical pre-check

Unless skipped explicitly, the launcher invokes the benchmark pre-check script and persists its outputs.

### 5. API smoke validation

Unless skipped explicitly, the launcher executes the worker-mode smoke validation script before load generation starts.

### 6. Warm-up phase

If enabled, the launcher executes a warm-up Locust phase using the same concurrency profile as the measurement phase, but with a distinct CSV prefix.

### 7. Measurement phase

The launcher executes the measurement Locust run and stores the main benchmark CSV outputs.

### 8. Cluster-side collection

Cluster-side evidence is collected before and after the measurement phase.

### 9. Artifact emission

The launcher writes manifests, summaries, CSV outputs, and baseline lock data into the results directory.

---

## Baseline Validation Checklist

After the run completes, verify all of the following before considering the baseline execution valid.

### A. Run completion

Confirm that the launcher exited successfully and that no command failed silently.

### B. Pre-check outputs exist

Verify that the pre-check JSON and text files are present.

Expected examples:

```text
<B0_runX>_precheck.json
<B0_runX>_precheck.txt
```

### C. Warm-up and measurement separation is visible

If warm-up is enabled, confirm that warm-up and measurement have distinct CSV prefixes and distinct artifact files.

### D. Measurement CSV files exist

At minimum, confirm presence of:

- stats
- stats history
- failures
- exceptions

### E. Cluster-side artifacts exist for both stages

Confirm that both pre-stage and post-stage infrastructure captures were written.

### F. Baseline lock file exists

Confirm presence of the baseline lock artifact, which records the resolved reference configuration used for the run.

### G. Phase, protocol, and metric-set manifests exist

These files are mandatory because they formalize how the run was executed.

### H. Topology is the expected baseline topology

Confirm that:

- the server is deployed from the expected server manifest;
- the topology corresponds to `colocated-sc-app-02-w2`;
- the expected active RPC workers are the two baseline workers;
- their placement matches the baseline expectations.

---

## Recommended Post-run Verification Commands

These commands are useful immediately after the launcher completes.

### Verify result directory contents

PowerShell:

```powershell
Get-ChildItem .\results\baseline\official\B0_official_locked
```

Bash:

```bash
find ./results/baseline/official/B0_official_locked -maxdepth 1 -type f | sort
```

### Verify current pod placement

PowerShell:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get pods -n genai-thesis -o wide
```

Bash:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get pods -n genai-thesis -o wide
```

### Verify node utilization snapshot

PowerShell:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig top nodes
```

Bash:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig top nodes
```

### Verify pod-level utilization snapshot

PowerShell:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig top pods -n genai-thesis
```

Bash:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig top pods -n genai-thesis
```

---

## Success Criteria

An official baseline run is considered successful only if all of the following are true:

1. the launcher completes without execution failure;
2. the pre-check passes or is intentionally skipped with explicit justification;
3. API smoke validation succeeds or is intentionally skipped with explicit justification;
4. the measurement phase completes and writes the expected Locust CSV files;
5. cluster-side artifacts are collected successfully before and after the run;
6. phase, protocol, metric-set, and baseline-lock manifests are present;
7. the resolved topology and model match the locked baseline definition;
8. the resulting artifacts are sufficient to compare future controlled variations against this run.

---

## Failure Conditions

Treat the baseline run as invalid if any of the following occurs:

- missing or unresolved baseline configuration;
- missing Kubernetes manifest targets;
- cluster pre-check failure;
- API smoke failure;
- Locust measurement failure;
- missing required cluster-side artifacts;
- missing baseline-lock or protocol manifests;
- evidence that the effective deployment differs from the locked baseline configuration.

If the run is invalid, do not use it as reference evidence for downstream comparisons.

---

## Troubleshooting

### Issue: pre-check fails because the cluster is already saturated

**Symptoms**

- node CPU or memory exceeds the threshold defined in `TC1`;
- metrics API reports pressure before the run starts.

**Action**

- inspect running workloads;
- clean residual test resources;
- confirm that no previous benchmark is still active;
- re-run the baseline only after the cluster returns to an acceptable state.

### Issue: API smoke validation fails

**Symptoms**

- model endpoint does not answer correctly;
- worker mode is not operational;
- service path or model loading is incomplete.

**Action**

- inspect the deployed pods;
- check server and worker logs;
- verify service reachability and model initialization;
- do not continue to the benchmark phase until smoke validation passes.

### Issue: measurement Locust run completes but required files are missing

**Symptoms**

- CSV prefix exists only partially;
- one or more required Locust CSV outputs are absent.

**Action**

- treat the run as invalid;
- inspect the launcher logs;
- verify filesystem permissions and output path resolution;
- re-run from a clean state.

### Issue: cluster-side collection failed after measurement

**Symptoms**

- missing `_cluster_pre` or `_cluster_post` artifacts;
- summary file not generated.

**Action**

- inspect collector script output;
- verify that `kubectl top` and `kubectl get` work at that moment;
- do not mark the run as baseline-valid without mandatory cluster-side evidence.

### Issue: baseline run was executed with overrides that change locked behavior

**Symptoms**

- model, worker count, placement, or workload no longer reflect `B0.json`.

**Action**

- reject the run as an official baseline;
- keep it only as an ad hoc test if needed;
- execute a fresh run without violating baseline lock rules.

---

## Operational Recommendations

- always execute a **dry run** first after changing infrastructure, scripts, or repository paths;
- preserve the official baseline artifacts exactly as generated;
- avoid manual modification inside the result directory;
- do not override locked baseline dimensions for convenience;
- treat the baseline as the canonical comparison anchor for all subsequent campaigns.

---

## Output Handover Guidance

Before moving to pilot sweeps or consolidated analysis, archive or at least verify the following baseline materials:

- baseline lock file;
- pre-check outputs;
- phase manifest;
- protocol manifest;
- metric-set manifest;
- warm-up CSV files, if enabled;
- measurement CSV files;
- cluster-side evidence collected before and after the run.

These artifacts form the minimum evidence package required for a trustworthy baseline.

---

## Next Step

Once the official baseline has been executed successfully and all required artifacts have been verified, proceed to the runbook for exploratory or pilot benchmark execution, depending on the current campaign objective.

Recommended next document:

```text
06-exploratory-load-validation.md
```

If the current goal is to move directly into controlled pilot campaigns after a validated baseline, the next operational document may instead be:

```text
07-pilot-sweeps-execution.md
```
