# 04. Precheck and Smoke Validation

## Objective

Establish a mandatory validation gate that must succeed before any exploratory run, official baseline execution, pilot sweep, consolidated benchmark campaign, or post-processing workflow is allowed to proceed.

This runbook defines the standard workflow for:

- executing the technical benchmark precheck profile;
- exporting validation metrics for traceability;
- validating the LocalAI API with a minimal manual smoke test;
- deciding whether the environment is safe to enter the benchmark phase.

The purpose of this runbook is to prevent invalid, ambiguous, or infrastructure-contaminated benchmark runs.

---

## When to Execute

Execute this runbook in all of the following situations:

- before the first benchmark run on a freshly deployed topology;
- before an official baseline execution;
- before each pilot sweep campaign;
- before a consolidated pilot benchmark campaign;
- after changing Kubernetes manifests, worker-count composition, placement composition, or model composition;
- after any cleanup and redeployment cycle;
- after any cluster interruption, restart, or infrastructure anomaly.

This runbook should be treated as a **hard gate**, not as an optional health check.

---

## Scope

This runbook covers two validation layers:

1. **Technical precheck** against the Kubernetes cluster and project namespace;
2. **Manual API smoke validation** against the deployed LocalAI worker-mode endpoint.

The precheck validates infrastructure and benchmark-readiness conditions such as:

- expected nodes present and ready;
- project namespace active;
- pod phases acceptable;
- no critical waiting reasons;
- no unexpected worker-node placement;
- Metrics API available;
- node resource pressure below the configured thresholds;
- required model visible through the LocalAI API when a base URL is supplied.

The smoke validation confirms that:

- the deployed endpoint is reachable;
- the intended model is exposed through `/v1/models`;
- a minimal `/v1/chat/completions` request succeeds;
- the response structure is valid enough to begin load generation.

This runbook does **not** execute Locust benchmarks and does **not** collect full cluster-side evidence for a benchmark campaign. Those steps belong to later runbooks.

---

## Repository Areas Covered by This Runbook

```text
config/precheck/TC1.json
scripts/validation/precheck/Invoke-BenchmarkPrecheck.ps1
scripts/validation/precheck/invoke-benchmark-precheck.sh
scripts/validation/precheck/Export-ValidationMetrics.ps1
scripts/validation/precheck/export-validation-metrics.sh
scripts/validation/smoke/Test-LocalAIWorkerMode.ps1
scripts/validation/smoke/test-localai-worker-mode.sh
results/precheck/
results/validation/
```

---

## Validation Model

The validation gate is intentionally split into two phases.

### Phase A — Infrastructure and namespace precheck

This phase answers the question:

> Is the cluster, namespace, and deployment state technically suitable for benchmark execution?

### Phase B — API smoke validation

This phase answers the question:

> Does the deployed LocalAI worker-mode service respond correctly to a minimal request using the intended model?

A run must **not** proceed to Locust or baseline execution unless both phases succeed.

---

## Default Validation Profile

The standard technical precheck profile is:

```text
config/precheck/TC1.json
```

### TC1 summary

The `TC1` profile currently defines the following benchmark-readiness assumptions:

- `kubeconfig`: `config/cluster-access/kubeconfig`
- `namespace`: `genai-thesis`
- expected ready nodes:
  - `sc-master-01`
  - `sc-app-01`
  - `sc-app-02`
- expected worker nodes:
  - `sc-app-01`
  - `sc-app-02`
- allowed pod phases:
  - `Running`
  - `Succeeded`
- minimum namespace pods: `1`
- critical waiting reasons:
  - `CrashLoopBackOff`
  - `ImagePullBackOff`
  - `ErrImagePull`
  - `CreateContainerConfigError`
  - `CreateContainerError`
  - `InvalidImageName`
- maximum total restarts in namespace: `0`
- Metrics API required: `true`
- maximum node CPU utilization: `95%`
- maximum node memory utilization: `95%`
- default output root: `results/precheck`

The runbook below assumes `TC1` unless an intentionally different precheck profile is introduced later.

---

## Prerequisites

Before starting, ensure that the following conditions are already satisfied.

### Local prerequisites

- the repository is available locally;
- the current working directory is the repository root;
- `kubectl` is available in `PATH`;
- PowerShell or Bash is available, depending on the script family used;
- the VPN session is active and stable;
- the project `kubeconfig` file is present.

### Cluster prerequisites

- the target topology has already been deployed;
- the namespace exists;
- the LocalAI server service is expected to be reachable;
- the intended model composition has already been applied.

If the topology has **not** yet been deployed, do not use this runbook. Complete the Kubernetes deployment workflow first.

---

## Required Inputs

The following inputs must be known before execution.

| Input | Description |
|---|---|
| `ProfileConfig` | Technical precheck profile, typically `config/precheck/TC1.json` |
| `Kubeconfig` | Kubernetes access file, typically `config/cluster-access/kubeconfig` |
| `Namespace` | Project namespace, typically `genai-thesis` |
| `BaseUrl` | LocalAI API base URL, typically `http://localhost:8080`; in the current pipeline the launcher stack automatically prepares the local endpoint when needed |
| `Model` | Expected model identifier exposed by LocalAI |
| `OutputPrefix` | Prefix used to write validation artifacts |

---

## Standard Success Criteria

The validation gate is considered successful only if:

1. the precheck script exits successfully;
2. no required precheck condition is reported as failed;
3. the validation metrics export runs successfully;
4. the smoke test script exits successfully;
5. `/v1/models` contains the intended model;
6. `/v1/chat/completions` returns a structurally valid response;
7. no manual inspection reveals a deployment anomaly that would make the benchmark ambiguous.

If any of these conditions fails, the benchmark must be blocked.

---

## Recommended Output Locations

For consistency, use output paths under the repository `results/` directory.

Recommended conventions:

```text
results/precheck/
results/validation/
```

Example prefixes:

```text
results/precheck/b0
results/validation/b0
results/precheck/w2_pl2_wl2_m1
results/validation/w2_pl2_wl2_m1
```

The exact naming convention may later be aligned with the run convention profile, but precheck and smoke artifacts should already be deterministic and traceable.

---

## Procedure

## Step 1 — Confirm the repository root and required files

From the repository root, confirm that the validation entry points and profile file exist.

### PowerShell

```powershell
Test-Path .\config\precheck\TC1.json
Test-Path .\scripts\validation\precheck\Invoke-BenchmarkPrecheck.ps1
Test-Path .\scripts\validation\precheck\Export-ValidationMetrics.ps1
Test-Path .\scripts\validation\smoke\Test-LocalAIWorkerMode.ps1
```

### Bash

```bash
 test -f ./config/precheck/TC1.json
 test -f ./scripts/validation/precheck/invoke-benchmark-precheck.sh
 test -f ./scripts/validation/precheck/export-validation-metrics.sh
 test -f ./scripts/validation/smoke/test-localai-worker-mode.sh
```

All checks must evaluate positively.

---

## Step 2 — Local endpoint preparation

If the validation activity uses `http://localhost:8080` **through the current launcher stack**, you do **not** need to create the port-forward manually. The repository performs automatic local endpoint preparation and will verify or create the required port-forward toward `service/localai-server` when needed. By contrast, the standalone scripts `Invoke-BenchmarkPrecheck.*` and `Test-LocalAIWorkerMode.*` do **not** create the port-forward themselves and therefore require an endpoint that is already reachable.

Manual port-forwarding should therefore be treated only as an exceptional troubleshooting action for isolated debugging sessions executed outside the standard launcher flow.

If you need to debug the endpoint manually outside the launcher flow, use one of the following commands.

### PowerShell — manual troubleshooting port-forward

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig port-forward -n genai-thesis service/localai-server 8080:8080
```

### Bash — manual troubleshooting port-forward

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig port-forward -n genai-thesis service/localai-server 8080:8080
```

## Step 3 — Execute the technical precheck

Run the benchmark precheck against the intended namespace and endpoint context. If you execute the standalone precheck script directly with `BaseUrl=http://localhost:8080`, ensure that the endpoint is already reachable before launching the command.

### PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\validation\precheck\Invoke-BenchmarkPrecheck.ps1" `
  -ProfileConfig .\config\precheck\TC1.json `
  -Kubeconfig .\config\cluster-access\kubeconfig `
  -Namespace genai-thesis `
  -BaseUrl http://localhost:8080 `
  -Model llama-3.2-1b-instruct:q4_k_m `
  -OutputPrefix .\results\precheck\b0
```

### Bash

```bash
./scripts/validation/precheck/invoke-benchmark-precheck.sh \
  --profile-config ./config/precheck/TC1.json \
  --kubeconfig ./config/cluster-access/kubeconfig \
  --namespace genai-thesis \
  --base-url http://localhost:8080 \
  --model llama-3.2-1b-instruct:q4_k_m \
  --output-prefix ./results/precheck/b0
```

### Expected artifacts

The precheck writes at least the following files:

```text
<output-prefix>_precheck.json
<output-prefix>_precheck.txt
```

### Expected behavior

The precheck should succeed only when all mandatory checks pass.

The script evaluates at least the following categories:

- cluster nodes ready;
- namespace active;
- namespace pods healthy;
- worker pods running only on expected worker nodes;
- Metrics API availability and node-capacity sanity;
- model availability through `/v1/models` when `BaseUrl` is supplied.

---

## Step 4 — Review the precheck result before proceeding

Do not rely only on the process exit code. Inspect the generated JSON and text report. When the endpoint check fails, also verify whether the standalone script was executed without first preparing the local endpoint.

### Minimum review points

- all expected nodes are present;
- no expected node is `NotReady`;
- namespace phase is `Active`;
- no pod is in disallowed phase;
- no critical waiting reason is reported;
- total restart count in the namespace is within the allowed threshold;
- no worker pod is running on an unexpected node;
- node CPU and memory utilization are below the configured limits;
- the intended model is visible if the endpoint is already reachable.

### If the precheck fails

Do **not** start the smoke test yet unless the failure is clearly unrelated to the deployed benchmark target and has been intentionally accepted.

In standard operation, any failed precheck should block the run.

---

## Step 5 — Export validation metrics snapshot

After a successful precheck, export a compact validation metrics snapshot for traceability.

### PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\validation\precheck\Export-ValidationMetrics.ps1" `
  -BaseUrl http://localhost:8080 `
  -Model llama-3.2-1b-instruct:q4_k_m `
  -Iterations 10 `
  -PauseSeconds 2 `
  -OutputPrefix .\results\validation\b0
```

### Bash

```bash
./scripts/validation/precheck/export-validation-metrics.sh \
  --base-url http://localhost:8080 \
  --model llama-3.2-1b-instruct:q4_k_m \
  --iterations 10 \
  --pause-seconds 2 \
  --output-prefix ./results/validation/b0
```

### Purpose

This step is not a benchmark. It creates a minimal request/response sample and a compact metrics summary that helps confirm basic response behavior before load generation starts.

### Expected artifacts

The validation metrics export writes at least:

```text
<output-prefix>-results.csv
<output-prefix>-summary.json
```

### Metrics included

The summary currently includes values such as:

- request count;
- successful requests;
- failed requests;
- success rate;
- mean response time;
- p50;
- p95;
- p99;
- throughput;
- token usage aggregates.

These artifacts are useful to confirm that the endpoint is not only reachable, but also minimally operational.

---

## Step 6 — Execute the manual smoke test against LocalAI worker mode

Run the dedicated smoke validation script.

### PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\validation\smoke\Test-LocalAIWorkerMode.ps1" `
  -BaseUrl http://localhost:8080 `
  -Model llama-3.2-1b-instruct:q4_k_m
```

### Bash

```bash
./scripts/validation/smoke/test-localai-worker-mode.sh \
  --base-url http://localhost:8080 \
  --model llama-3.2-1b-instruct:q4_k_m
```

### What the smoke test validates

The smoke script performs three essential checks:

1. it queries `/v1/models` and verifies that the intended model exists;
2. it sends a minimal request to `/v1/chat/completions`;
3. it verifies that the response contains a valid `choices[0].message.content` payload.

### Expected behavior

A successful smoke test ends with an explicit success message and a zero exit code.

When the smoke script is executed manually in standalone mode, any timeout or request failure must still be treated as a blocking validation failure for deployment readiness. In the current repository version, the same smoke scripts can also be invoked by higher-level model-sweep launchers with an explicit timeout-classification mode. In that launcher-managed mode, a `/v1/chat/completions` timeout may be translated into `unsupported_under_current_constraints` with exit code `42`, but that classification is produced by the launcher workflow, not by the manual validation procedure described in this runbook.

If the smoke test fails, treat the deployment as not ready for benchmark execution.

---

## Step 7 — Perform a brief manual review of the deployed namespace

Even after a successful precheck and smoke test, perform a quick operator review.

### Recommended commands

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get pods -n genai-thesis -o wide
kubectl --kubeconfig .\config\cluster-access\kubeconfig top pods -n genai-thesis
kubectl --kubeconfig .\config\cluster-access\kubeconfig top nodes
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get pods -n genai-thesis -o wide
kubectl --kubeconfig ./config/cluster-access/kubeconfig top pods -n genai-thesis
kubectl --kubeconfig ./config/cluster-access/kubeconfig top nodes
```

### Review objectives

Confirm that:

- expected pods are present;
- pods are on the intended nodes;
- there are no obvious spikes, restarts, or resource anomalies;
- the namespace state matches the topology expected for the upcoming run.

This brief review is especially important after changing worker count, placement, or model composition.

---

## Step 8 — Record the validation decision

Before starting any benchmark workflow, record the outcome of the validation gate.

The operator should explicitly classify the result as one of the following:

- **PASS** — benchmark execution is allowed;
- **FAIL** — benchmark execution is blocked;
- **CONDITIONAL PASS** — benchmark execution is allowed only because a known and documented non-blocking anomaly has been accepted.

A conditional pass should be rare and justified in the run notes.

---

## Recommended Decision Table

| Condition | Decision |
|---|---|
| Precheck failed | FAIL |
| Precheck passed, smoke failed | FAIL |
| Precheck passed, smoke passed, namespace healthy | PASS |
| Precheck passed, smoke passed, but known non-blocking issue exists and is documented | CONDITIONAL PASS |

In normal operation, use **PASS** or **FAIL** only.

---

## Expected Outputs

At the end of this runbook, the following evidence should exist:

- precheck JSON report;
- precheck text report;
- validation metrics CSV;
- validation metrics JSON summary;
- smoke test console output captured in the operator log or terminal transcript;
- operator decision on whether the benchmark may proceed.

---

## Failure Handling and Troubleshooting

## Case 1 — `kubectl` commands fail inside the precheck

### Typical causes

- VPN disconnected;
- wrong or stale `kubeconfig`;
- cluster unavailable;
- local shell environment missing `kubectl`.

### Required action

Stop immediately and restore cluster access before retrying.

---

## Case 2 — Namespace reported as inactive or missing

### Typical causes

- namespace not yet deployed;
- cleanup removed the namespace;
- wrong namespace value supplied to the precheck.

### Required action

Recreate or redeploy the namespace before continuing.

---

## Case 3 — Pods are in `Pending`, `CrashLoopBackOff`, or other critical waiting states

### Typical causes

- invalid image reference;
- broken manifest;
- missing PVC or storage issue;
- model configuration mismatch;
- node resource exhaustion.

### Required action

Do not proceed to smoke validation or benchmarks. Inspect pod status and fix the deployment first.

---

## Case 4 — `kubectl top` fails or Metrics API is unavailable

### Typical causes

- `metrics-server` unavailable or unhealthy;
- cluster metrics pipeline degraded.

### Required action

Treat this as a blocking issue when using the `TC1` profile, because the profile requires Metrics API support.

---

## Case 5 — Model not present in `/v1/models`

### Typical causes

- wrong server composition applied;
- model patch not applied as expected;
- LocalAI not fully initialized;
- incorrect `BaseUrl` or failure in the automatic local endpoint preparation logic.

### Required action

Do not proceed. Fix model availability first.

---

## Case 6 — Smoke test fails on `/v1/chat/completions`

### Typical causes

- service reachable but backend not operational;
- runtime configuration mismatch;
- model initialization incomplete;
- worker-mode topology not functioning correctly.

### Required action

Treat as blocking. The deployment is not ready for load generation.

In the current repository version, note an additional distinction: when the same smoke logic is executed indirectly by the Model Sweep launchers, an operational timeout on `/v1/chat/completions` can be elevated to an explicit scenario classification of `unsupported_under_current_constraints`. That behavior is intentional for launcher-managed benchmark execution, but it does **not** change the rule of this manual validation runbook: a standalone smoke timeout still means the deployment is not ready for benchmarking.

---

## Operational Rules

The following rules apply to every benchmark campaign.

1. Never start Locust before the smoke test succeeds.
2. Never start the official baseline if the precheck fails.
3. Never treat a failed smoke run as a benchmark failure; it is a deployment-readiness failure.
4. Always preserve the precheck and validation artifacts for traceability.
5. If the topology changes, rerun the entire validation gate.
6. If the namespace is cleaned and redeployed, rerun the entire validation gate.
7. If the model changes, rerun the entire validation gate.

---

## Exit Criteria

This runbook is complete only when all the following are true:

- the technical precheck succeeded;
- the validation metrics snapshot was exported;
- the manual smoke test succeeded;
- the operator completed the quick namespace review;
- the run was explicitly classified as `PASS`.

Only then may the workflow continue to:

- official baseline execution;
- exploratory validation with Locust;
- pilot sweep execution;
- consolidated pilot benchmark execution.

---

## Next Step

If this runbook completes successfully, proceed to one of the following runbooks depending on the phase being executed:

- `05-official-baseline-execution.md` for the locked baseline run;
- `06-exploratory-load-validation.md` for non-authoritative exploratory load checks;
- `07-pilot-sweeps-execution.md` for controlled pilot sweep families.
