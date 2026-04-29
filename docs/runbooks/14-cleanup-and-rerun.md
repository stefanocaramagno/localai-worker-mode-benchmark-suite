# 14. Cleanup and Rerun

## Objective

This runbook defines the operational procedure to clean the benchmark environment, preserve relevant evidence, recover from partial or failed executions, and rerun the pipeline in a controlled and repeatable way.

The procedure is designed for the current project topology and execution model, where benchmark scenarios are deployed into a dedicated Kubernetes namespace, measured through client-side and cluster-side evidence collection, and consolidated through post-processing steps.

This runbook must be used whenever one of the following conditions applies:

- a benchmark campaign has completed and the environment must be reset before the next campaign;
- a scenario failed during deployment, warm-up, measurement, or artifact collection;
- the namespace contains residual objects from a previous run;
- the cluster entered an ambiguous state and the validity of the next run would be compromised;
- the completion gate returned a **no-go** decision and a controlled rerun is required.

---

## Scope

This runbook covers:

- controlled cleanup of the benchmark namespace;
- verification that no residual workload artifacts remain in the cluster;
- preservation of run outputs and generated evidence before cleanup;
- handling of namespace deletion edge cases, including stuck `Terminating` namespaces;
- restoration of a clean starting point for the next execution;
- rerun preparation for baseline, exploratory, pilot, consolidated, diagnosis, reporting, and completion-gate phases.

This runbook does **not** redefine how to execute individual benchmark phases. Those steps are documented in the phase-specific runbooks.

---

## Related Runbooks

This runbook is operationally related to the following documents:

- `00-cluster-bootstrap-and-access.md`
- `01-repository-and-execution-environment-setup.md`
- `04-precheck-and-smoke-validation.md`
- `05-official-baseline-execution.md`
- `06-exploratory-load-validation.md`
- `07-pilot-sweeps-execution.md`
- `08-consolidated-pilot-benchmarks.md`
- `09-metrics-artifacts-and-cluster-side-evidence.md`
- `10-statistical-rigor-and-repeatability.md`
- `11-technical-diagnosis.md`
- `12-reporting-and-visualization.md`
- `13-completion-gate-and-phase-closure.md`

---

## Repository Areas Involved

The procedure references the following areas of the repository:

- `results/`
- `config/scenarios/`
- `config/precheck/`
- `config/protocol/`
- `scripts/validation/precheck/`
- `scripts/validation/cluster-side/`
- `scripts/load/baseline/`
- `scripts/load/exploratory/`
- `scripts/load/pilot/`
- `scripts/load/post/`
- `infra/k8s/compositions/`

---

## Cleanup Principles

All cleanup operations must respect the following principles:

1. **Never delete first and inspect later.** Always preserve evidence before modifying the cluster state.
2. **Treat cleanup as part of the protocol.** Cleanup is not an informal convenience step; it is a required control action to preserve repeatability.
3. **Reset workload state, not project state.** Benchmark artifacts under `results/` must remain available unless a deliberate archival or replacement action has been taken. Optional reporting archives under `results/reporting/archive/` are historical snapshots and should not be deleted during normal workload cleanup.
4. **A rerun is valid only after a fresh precheck.** Cleanup alone is not enough; the next execution must start from a newly validated state.
5. **Residual state must be assumed dangerous.** Any surviving pod, PVC binding issue, restart anomaly, stale service, or unresolved namespace state can invalidate the next run.

---

## When Cleanup Is Mandatory

Cleanup is mandatory in the following situations:

### After a successful execution cycle

Perform cleanup when:

- a baseline run has completed;
- an exploratory run has completed;
- a pilot sweep scenario has completed;
- a consolidated campaign has completed and the environment must be reset before the next family or rerun.

### After a failed execution cycle

Perform cleanup when any of the following occurred:

- deployment timed out;
- one or more pods remained `Pending`;
- one or more pods entered `CrashLoopBackOff`, `ImagePullBackOff`, or repeated restarts;
- smoke validation failed after the scenario was partially deployed;
- Locust execution aborted unexpectedly;
- cluster-side artifact collection was incomplete or inconsistent;
- the cluster remained saturated after the benchmark ended;
- the namespace did not return to a clearly reusable state.

### Before a controlled rerun

Perform cleanup before rerunning:

- the same scenario after a failure;
- the baseline after a protocol fix;
- a full sweep after changing a profile or scenario definition;
- a completion-gate cycle after remediating missing evidence.

---

## Inputs Required

Before starting cleanup, confirm the following inputs:

- the repository root path;
- the kubeconfig path;
- the target namespace;
- the scenario or campaign identifier being cleaned up;
- the output directory containing artifacts for the last run;
- the reason for cleanup;
- whether the next step is:
  - a rerun of the same scenario,
  - execution of the next scenario,
  - a full campaign restart,
  - or phase closure.

Typical values in this project are:

- **Kubeconfig:** `config/cluster-access/kubeconfig`
- **Namespace:** `genai-thesis`

Do not rely on shell history or memory. Confirm the actual paths before proceeding.

---

## Pre-Cleanup Preservation Checklist

Before deleting or modifying any workload resource, preserve the evidence already produced by the run.

### Minimum preservation set

Verify that the following artifacts already exist and are readable:

- Locust CSV output or equivalent client-side benchmark output;
- run manifest and scenario metadata;
- validation metrics export, if generated;
- cluster-side evidence already collected for the run;
- post-processing summaries already produced, if applicable.

### If evidence is incomplete

If cluster-side evidence has not yet been collected and the namespace is still alive, collect it **before cleanup**.

Use the existing cluster-side artifact collection script for the active run.

Typical examples:

### PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\validation\cluster-side\Collect-ClusterSideArtifacts.ps1" `
  -ProfileConfig .\config\cluster-capture\CS1.json `
  -Kubeconfig .\config\cluster-access\kubeconfig `
  -Namespace genai-thesis `
  -Stage post `
  -OutputPrefix .\results\manual-capture\<RUN_ID>\<RUN_ID>_cluster_post
```

### Bash

```bash
./scripts/validation/cluster-side/collect-cluster-side-artifacts.sh \
  --profile-config ./config/cluster-capture/CS1.json \
  --kubeconfig ./config/cluster-access/kubeconfig \
  --namespace genai-thesis \
  --stage post \
  --output-prefix ./results/manual-capture/<RUN_ID>/<RUN_ID>_cluster_post
```

If post-processing summaries depend on artifacts that do not yet exist, do **not** delete the namespace until you have either:

- captured the missing data;
- or explicitly declared the run invalid and documented the failure reason.

---

## Reporting Archive Considerations

The current reporting package under `results/reporting/` is regenerated by the reporting launcher. Historical snapshots are stored under the archive directory only when either archive mode was explicitly used:

```text
results/reporting/archive/<reporting-id>/
```

`-Archive` / `--archive` regenerates the current report and then archives the generated package. `-ArchiveCurrent` / `--archive-current` archives the already generated current report as-is, using the `reportingId` stored in `results/reporting/reporting-manifest.json`.

Do not remove this archive during routine cluster or namespace cleanup. Remove archived reporting snapshots only as a deliberate evidence-retention decision.

## Standard Cleanup Procedure

### Step 1 — Confirm the target namespace

Check whether the namespace exists and list all objects still present.

### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get ns
kubectl --kubeconfig .\config\cluster-access\kubeconfig get all -n genai-thesis
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get ns
kubectl --kubeconfig ./config/cluster-access/kubeconfig get all -n genai-thesis
```

Also inspect PVCs, ConfigMaps, and Secrets if applicable:

### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get pvc,configmap,secret -n genai-thesis
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get pvc,configmap,secret -n genai-thesis
```

### Step 2 — Record final cluster state if needed

If the run ended abnormally, take one final snapshot before deletion.

Recommended minimum commands:

### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get pods -n genai-thesis -o wide
kubectl --kubeconfig .\config\cluster-access\kubeconfig describe pods -n genai-thesis
kubectl --kubeconfig .\config\cluster-access\kubeconfig get events -n genai-thesis --sort-by=.metadata.creationTimestamp
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get pods -n genai-thesis -o wide
kubectl --kubeconfig ./config/cluster-access/kubeconfig describe pods -n genai-thesis
kubectl --kubeconfig ./config/cluster-access/kubeconfig get events -n genai-thesis --sort-by=.metadata.creationTimestamp
```

Persist these outputs under the relevant run directory if they are not already stored.

### Step 3 — Delete the benchmark namespace

Delete the benchmark namespace using the standard Kubernetes flow.

### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig delete namespace genai-thesis
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig delete namespace genai-thesis
```

### Step 4 — Wait for namespace termination

Monitor the namespace until it disappears.

### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get namespace genai-thesis --watch
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get namespace genai-thesis --watch
```

The cleanup is complete only when the namespace no longer appears in the namespace list.

---

## Handling a Namespace Stuck in `Terminating`

A namespace stuck in `Terminating` must be resolved before any rerun.

### Why this matters

If the namespace remains in `Terminating`:

- you may be unable to recreate it cleanly;
- namespaced resources may remain partially registered;
- subsequent deployments may fail or behave ambiguously;
- the next run will not satisfy the clean-state requirement.

### Standard inspection

Inspect the namespace object:

### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get namespace genai-thesis -o yaml
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get namespace genai-thesis -o yaml
```

Pay special attention to:

- `status.phase`
- finalizers
- resource references still attached to the namespace

### Force-finalization procedure

If the namespace is stuck and standard deletion does not complete, remove finalizers through the Kubernetes API finalization path.

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get namespace genai-thesis -o json |
  Out-File -Encoding utf8 .\results\_runtime\genai-thesis-namespace.json
```

Edit the JSON file and set:

- `.spec.finalizers = []`

Then send the finalized object back through the finalize endpoint:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig replace --raw "/api/v1/namespaces/genai-thesis/finalize" -f .\results\_runtime\genai-thesis-namespace.json
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get namespace genai-thesis -o json \
  > ./results/_runtime/genai-thesis-namespace.json
```

Edit the JSON file and set:

- `.spec.finalizers = []`

Then apply finalization:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig replace --raw "/api/v1/namespaces/genai-thesis/finalize" -f ./results/_runtime/genai-thesis-namespace.json
```

### Post-finalization verification

Confirm that the namespace is fully gone:

### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get ns
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get ns
```

Do not continue until the namespace is absent.

---

## Post-Cleanup Validation

Once the namespace has been removed, validate that the cluster is ready to be reused.

### Required checks

1. The benchmark namespace is absent.
2. No pods from the previous scenario remain.
3. No residual services remain under the benchmark namespace.
4. No PVC from the benchmark namespace remains bound.
5. Worker nodes are still `Ready`.
6. The control-plane node is healthy.
7. `metrics-server` and observability components remain healthy.
8. No unexpected cluster-wide saturation remains from the previous run.

### Recommended commands

### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get nodes
kubectl --kubeconfig .\config\cluster-access\kubeconfig top nodes
kubectl --kubeconfig .\config\cluster-access\kubeconfig get pods -A
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get nodes
kubectl --kubeconfig ./config/cluster-access/kubeconfig top nodes
kubectl --kubeconfig ./config/cluster-access/kubeconfig get pods -A
```

If any node is no longer `Ready`, or if cluster metrics are unavailable, do not proceed with a rerun. Return to cluster validation and resolve the issue first.

---

## Cleanup Modes

Different situations require different cleanup depth. Use the correct mode deliberately.

### Mode A — Standard scenario cleanup

Use this mode when:

- one scenario has completed successfully;
- artifacts have been preserved;
- the next scenario can begin from a clean namespace.

Actions:

- delete the benchmark namespace;
- wait for completion;
- validate cluster health;
- proceed to the next scenario.

### Mode B — Failure recovery cleanup

Use this mode when:

- deployment failed;
- a benchmark aborted mid-run;
- cluster-side evidence is incomplete;
- the namespace contains broken or partially started objects.

Actions:

- preserve final diagnostics first;
- delete the namespace;
- resolve `Terminating` if necessary;
- rerun the precheck before any new deployment.

### Mode C — Campaign reset cleanup

Use this mode when:

- a whole family of runs must be restarted;
- protocol or scenario definitions changed materially;
- the campaign must be rerun under a fresh and consistent state.

Actions:

- preserve all previous results;
- clean the namespace;
- validate cluster readiness;
- rerun the official baseline before resuming the campaign.

---

## Rerun Readiness Criteria

A rerun is allowed only when **all** of the following conditions are satisfied:

1. The previous run evidence has been preserved or explicitly declared invalid.
2. The benchmark namespace has been fully removed or cleanly recreated.
3. No resource residue from the previous scenario remains.
4. Worker nodes are `Ready`.
5. Metrics collection is functioning.
6. The correct scenario file and profiles are selected.
7. The reason for rerun is documented.
8. A fresh precheck will be executed before the rerun.

If even one of these conditions is not met, the rerun must be postponed.

---

## Controlled Rerun Procedure

### Step 1 — Identify the rerun type

Before redeploying anything, explicitly classify the rerun as one of the following:

- **same scenario / same configuration rerun**
- **same scenario / corrected protocol rerun**
- **full baseline rerun**
- **full sweep family rerun**
- **post-diagnosis rerun**

This classification matters because it determines what comparisons will remain valid later.

### Step 2 — Record the rerun reason

Document the rerun cause in the relevant run notes, manifest, or execution log.

Typical reasons include:

- namespace failed to terminate cleanly;
- smoke test failed;
- cluster-side evidence missing;
- Locust aborted;
- scenario changed;
- baseline changed;
- statistical consistency not achieved;
- completion gate returned `no-go`.

### Step 3 — Re-establish the local server endpoint when needed

If the rerun phase will use `http://localhost:8080`, you normally do **not** need to reopen the port-forward manually when you stay inside the current launcher stack. In the current pipeline, the launcher automatically verifies the local endpoint and recreates the required port-forward toward `service/localai-server` when needed before the dependent steps start. If you instead run the standalone precheck or smoke scripts directly, they still require an endpoint that is already reachable.

Manual port-forwarding should therefore be considered only for exceptional standalone debugging outside the standard rerun flow.

If you need to re-open the endpoint manually for troubleshooting outside the launcher flow, use one of the following commands.

### PowerShell — manual troubleshooting port-forward

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig port-forward -n genai-thesis service/localai-server 8080:8080
```

### Bash — manual troubleshooting port-forward

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig port-forward -n genai-thesis service/localai-server 8080:8080
```

### Step 4 — Re-run the precheck

A rerun must always restart from the precheck phase. When the precheck is invoked as a standalone script, remember that it does not create the port-forward automatically.

Use the standard precheck script with the expected configuration profile.

Typical example:

### PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\validation\precheck\Invoke-BenchmarkPrecheck.ps1" `
  -ProfileConfig .\config\precheck\TC1.json `
  -Kubeconfig .\config\cluster-access\kubeconfig `
  -Namespace genai-thesis `
  -BaseUrl http://localhost:8080 `
  -Model llama-3.2-1b-instruct:q4_k_m `
  -OutputPrefix .\results\precheck\rerun-check
```

### Bash

```bash
./scripts/validation/precheck/invoke-benchmark-precheck.sh \
  --profile-config ./config/precheck/TC1.json \
  --kubeconfig ./config/cluster-access/kubeconfig \
  --namespace genai-thesis \
  --base-url http://localhost:8080 \
  --model llama-3.2-1b-instruct:q4_k_m \
  --output-prefix ./results/precheck/rerun-check
```

Do not skip the precheck because “the cluster looked fine after cleanup”.

### Step 5 — Re-enter the correct phase runbook

Once the fresh precheck passes, continue by following the runbook for the intended phase:

- official baseline;
- exploratory validation;
- pilot sweep execution;
- consolidated pilot benchmarks;
- diagnosis;
- reporting;
- completion gate.

The rerun procedure ends here. All subsequent steps must follow the phase-specific execution protocol.

---

## What Must Be Preserved Across Cleanup

Cleanup should remove cluster workload state, but not erase evidence that is needed for auditability and analysis.

Preserve at minimum:

- run manifests;
- scenario metadata;
- Locust CSV outputs;
- validation summaries;
- cluster-side evidence bundles;
- diagnosis outputs;
- reporting outputs;
- completion gate outputs;
- manual notes on failures or rerun reasons.

If a run is invalid, do not silently delete it. Mark it as invalid or superseded instead.

---

## What Must Not Be Reused Blindly After Cleanup

Do **not** blindly reuse the following without explicit verification:

- stale local endpoint state left from a previous run, including residual port-forward sessions;
- locally cached assumptions about the active namespace state;
- previous run identifiers;
- baseline outputs after changing scenario definitions;
- diagnosis results generated from obsolete or partial data;
- completion-gate outputs generated before a rerun.

Any of these can contaminate the next execution cycle.

---

## Recommended Manual Checks Before the Next Run

Before starting the next run, perform the following quick confirmation checks:

- VPN is still connected;
- the kubeconfig path is still valid;
- `kubectl` context resolves correctly;
- all nodes are still `Ready`;
- observability stack is still healthy;
- namespace `genai-thesis` is absent or will be recreated from scratch;
- no residual process is occupying the intended local port used by the automatic local endpoint preparation logic;
- `results/` contains the preserved outputs from the previous run;
- the next scenario file is the one intentionally selected.

---

## Common Failure Patterns and Responses

### Failure Pattern 1 — Namespace stuck in `Terminating`

**Symptom**

- namespace remains visible for too long after deletion;
- recreation fails;
- resources appear half-removed.

**Response**

- inspect namespace JSON/YAML;
- remove finalizers through the finalize endpoint;
- verify namespace disappearance before continuing.

### Failure Pattern 2 — Previous run evidence not collected

**Symptom**

- Locust output exists but cluster-side evidence is missing;
- diagnosis cannot be generated.

**Response**

- collect manual cluster-side artifacts before deleting the namespace if still possible;
- if not possible, explicitly mark the run as incomplete.

### Failure Pattern 3 — Rerun started on a dirty cluster

**Symptom**

- unexpected pod residue;
- namespace already exists with stale objects;
- precheck inconsistencies.

**Response**

- stop the rerun;
- perform full namespace cleanup;
- restart from precheck.

### Failure Pattern 4 — Repeated reruns without traceability

**Symptom**

- multiple output folders exist but no reason is documented;
- difficult result attribution.

**Response**

- record rerun reason and scenario identity before every rerun;
- preserve invalid runs instead of silently overwriting them.

---

## Success Criteria

Cleanup and rerun preparation are considered successful only when all of the following are true:

- the prior run evidence is preserved;
- the benchmark namespace has been fully deleted or cleanly reset;
- no workload residue remains in the cluster;
- cluster health is confirmed;
- the rerun reason is recorded;
- a fresh precheck is ready to be executed;
- the next phase can begin from a deterministic starting point.

---

## Final Recommendation

Do not treat cleanup as an administrative afterthought. In this project, cleanup is a mandatory control step that directly affects:

- result validity;
- benchmark comparability;
- repeatability;
- diagnosis credibility;
- and phase-closure decisions.

A rerun is trustworthy only if cleanup has been executed with the same level of rigor as deployment, measurement, and artifact collection.
