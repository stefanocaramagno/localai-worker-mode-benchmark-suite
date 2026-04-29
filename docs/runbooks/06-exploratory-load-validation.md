# 06. Exploratory Load Validation

## Objective

This runbook defines how to execute **exploratory Locust-based load validation** against a deployed LocalAI worker-mode scenario before launching structured sweep campaigns or consolidated pilot benchmarks.

The goal of this phase is to verify that the deployed system:

- accepts repeated API requests under controlled synthetic load;
- behaves coherently under low-intensity and small-concurrency traffic patterns;
- produces the expected client-side and cluster-side artifacts;
- can be observed and measured using the project metric and capture conventions;
- is ready to progress toward formal pilot sweeps and later consolidated benchmark campaigns.

This phase is intentionally **exploratory**, not conclusive. Its purpose is to expose obvious bottlenecks, protocol issues, artifact collection gaps, and unstable deployment behavior before investing time in more rigorous multi-run benchmark campaigns.

---

## When to Use This Runbook

Use this runbook after all of the following conditions are already satisfied:

1. cluster bootstrap and access validation are complete;
2. the local execution environment is ready;
3. baseline governance and naming conventions are understood;
4. the target LocalAI topology has been deployed successfully;
5. technical precheck and API smoke validation can be executed successfully.

This runbook should be used in these situations:

- after the first successful deployment of a scenario;
- after changing a model, worker count, or placement composition and before formal sweeps;
- after changing Locust payload behavior or request-generation logic;
- after modifying validation, capture, or metric-set configuration;
- after cleanup and redeployment when a quick operational confidence pass is needed.

Do **not** use this phase as a replacement for:

- the official baseline execution;
- formal pilot sweep execution;
- consolidated pilot benchmark campaigns;
- statistical stability assessment.

---

## Phase Position in the Pipeline

Exploratory load validation sits between **manual functional validation** and **structured experimental execution**.

Recommended pipeline order:

1. cluster bootstrap and access validation;
2. repository and execution environment setup;
3. scenario selection and baseline governance;
4. Kubernetes deployment of the target topology;
5. technical precheck and API smoke validation;
6. **exploratory load validation**;
7. official baseline execution or pilot sweep execution;
8. consolidated pilot benchmark campaigns;
9. technical diagnosis, reporting, and phase closure.

---

## Scope and Expected Outcome

At the end of this phase, you should have:

- at least one successful exploratory load run;
- Locust CSV artifacts for the selected exploratory scenario;
- phase and protocol manifests generated for the run;
- cluster-side evidence captured before and after the run;
- a minimal confirmation that warm-up, measurement, and artifact collection behave correctly;
- enough operational confidence to start either the official baseline or one of the pilot sweep families.

What this phase **does not** provide:

- statistically stable conclusions;
- final performance claims;
- validated comparative results across scenarios;
- phase-completion evidence for the broader benchmark campaign.

---

## Repository Components Used in This Phase

### Primary launchers

PowerShell:

- `scripts/load/exploratory/Start-LocustExploratory.ps1`

Bash:

- `scripts/load/exploratory/start-locust-exploratory.sh`

### Supporting validation scripts

PowerShell:

- `scripts/validation/precheck/Invoke-BenchmarkPrecheck.ps1`
- `scripts/validation/smoke/Test-LocalAIWorkerMode.ps1`
- `scripts/validation/cluster-side/Collect-ClusterSideArtifacts.ps1`

Bash:

- `scripts/validation/precheck/invoke-benchmark-precheck.sh`
- `scripts/validation/smoke/test-localai-worker-mode.sh`
- `scripts/validation/cluster-side/collect-cluster-side-artifacts.sh`

### Default configuration files resolved by the exploratory launcher

- `config/precheck/TC1.json`
- `config/phases/WM1.json`
- `config/protocol/EP1.json`
- `config/cluster-capture/CS1.json`
- `config/metric-set/MS1.json`

### Default Locust test file

- `load-tests/locust/locustfile.py`

---

## Preconditions

Before executing exploratory load validation, verify the following:

### Infrastructure preconditions

- the VPN session is active;
- the cluster is reachable;
- the expected Kubernetes context is selected through the project kubeconfig or explicit `--kubeconfig` usage;
- nodes are in `Ready` state;
- the target namespace exists and contains the deployed scenario;
- the LocalAI server and required worker pods are running;
- no unresolved `Pending`, `CrashLoopBackOff`, or repeated restart conditions are present.

### Application preconditions

- the intended model is available and correctly configured for the run;
- the LocalAI API endpoint is reachable from the execution host;
- when using `http://localhost:8080`, the launcher can automatically prepare the local endpoint toward `service/localai-server` when required;
- `/v1/models` responds successfully;
- a manual or automated API smoke check has already passed, or will be executed by the exploratory launcher as part of the protocol.

### Local execution preconditions

- `locust` is available in the local `PATH` unless the launcher is used in `--dry-run` mode;
- Python dependencies required by the Locust test file are available;
- `kubectl` is available when cluster-side capture is enabled;
- the repository root is known and all commands are launched from a consistent working environment.

---

## Local Endpoint Exposure

If the exploratory run uses `http://localhost:8080`, you normally do **not** need to expose the LocalAI server manually. In the current pipeline, the launcher stack automatically verifies the local endpoint and creates the required port-forward toward `service/localai-server` when needed.

Manual port-forwarding is reserved for exceptional troubleshooting or standalone debugging sessions executed outside the standard launcher flow.

## Default Behavior of the Exploratory Launcher

The exploratory launcher is not a raw Locust wrapper. It executes a controlled workflow that combines validation, warm-up, measurement, and artifact collection.

By default, it resolves and applies:

- **technical precheck** via `TC1`;
- **warm-up/measurement separation** via `WM1`;
- **execution protocol** via `EP1`;
- **cluster-side collection profile** via `CS1`;
- **metric-set governance** via `MS1`.

Unless explicitly overridden, the launcher also:

- uses the project Locust file under `load-tests/locust/locustfile.py`;
- performs API smoke validation before the measurement phase;
- generates a phase manifest;
- generates a protocol manifest;
- captures cluster-side artifacts before and after the run.

This behavior is intentional and should be preserved unless there is a strong operational reason to override it.

---

## Built-In Exploratory Scenarios

If `--csv-prefix` is not explicitly provided, the launcher maps certain parameter combinations to predefined exploratory result directories.

### E1 — Smoke single-user validation

Parameters:

- users: `1`
- spawn rate: `1`
- run time: `1m`

Default output prefix:

- `results/exploratory/E1_smoke_single_user/locust-smoke`

### E2 — Low-load two-user validation

Parameters:

- users: `2`
- spawn rate: `1`
- run time: `1m`

Default output prefix:

- `results/exploratory/E2_low_load_two_users/locust-low_load`

### E3 — Small-concurrency four-user validation

Parameters:

- users: `4`
- spawn rate: `2`
- run time: `1m`

Default output prefix:

- `results/exploratory/E3_small_concurrency_four_users/locust-small_concurrency`

### Manual exploratory run

If the parameter combination does not match one of the predefined mappings, the launcher writes under:

- `results/exploratory/manual_run/locust-exploratory`

For repeatability, use an explicit custom `--csv-prefix` when running any non-standard exploratory scenario.

---

## Warm-Up and Measurement Semantics

The exploratory phase uses the phase profile `WM1`, which enforces formal separation between warm-up and measurement.

Default `WM1` behavior:

- warm-up enabled: `true`
- warm-up duration: `30s`
- warm-up users mode: match measurement
- warm-up spawn-rate mode: match measurement
- startup model check during warm-up: enabled
- startup model check during measurement: disabled
- warm-up CSV suffix: `_warmup`
- phase manifest suffix: `_phases.json`

This means the launcher generates:

1. a **warm-up run** intended to stabilize the application;
2. a **measurement run** intended to produce the exploratory Locust results;
3. a **phase manifest** documenting the phase plan used.

Exploratory runs must not be interpreted without considering whether the warm-up completed successfully.

---

## Protocol Semantics

The protocol profile `EP1` defines the ordered benchmark steps used by the exploratory launcher.

The ordered step model is:

1. controlled cleanup;
2. scenario deployment;
3. technical precheck;
4. API smoke validation;
5. optional warm-up;
6. measurement;
7. client-side artifact collection;
8. cluster-side metric collection;
9. final snapshot;
10. controlled cleanup or restore placeholder.

Important:

- cleanup and deployment are still treated as controlled manual steps in the broader protocol;
- the exploratory launcher automates the validation and measurement steps around the deployed scenario;
- this runbook assumes deployment has already been completed before the launcher is executed.

---

## Recommended Exploratory Execution Strategy

Execute exploratory validation progressively.

### Step 1 — Start with E1

Use the single-user scenario first.

This confirms:

- endpoint reachability under repeated requests;
- absence of immediate application-level failures;
- correct artifact generation;
- stable warm-up-to-measurement transition.

### Step 2 — Continue with E2

Move to the two-user low-load scenario only if E1 is clean.

This confirms:

- basic concurrent request handling;
- absence of obvious request queuing anomalies;
- absence of immediate throughput collapse.

### Step 3 — Continue with E3

Move to small concurrency only if E2 remains operationally consistent.

This confirms:

- baseline readiness for limited concurrent load;
- absence of catastrophic degradation under slightly more demanding traffic;
- ability of the current scenario to support entry-level pilot benchmarking.

Do not escalate beyond this phase using ad-hoc exploratory combinations unless there is a specific reason to debug or validate a non-standard scenario.

---

## Standard PowerShell Execution

### Example 1 — E1 smoke single-user validation

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\exploratory\Start-LocustExploratory.ps1" `
  -BaseUrl http://localhost:8080 `
  -Model llama-3.2-1b-instruct:q4_k_m `
  -Users 1 `
  -SpawnRate 1 `
  -RunTime 1m `
  -Kubeconfig .\config\cluster-access\kubeconfig `
  -Namespace genai-thesis
```

### Example 2 — E2 low-load two-user validation

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\exploratory\Start-LocustExploratory.ps1" `
  -BaseUrl http://localhost:8080 `
  -Model llama-3.2-1b-instruct:q4_k_m `
  -Users 2 `
  -SpawnRate 1 `
  -RunTime 1m `
  -Kubeconfig .\config\cluster-access\kubeconfig `
  -Namespace genai-thesis
```

### Example 3 — E3 small-concurrency four-user validation

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\exploratory\Start-LocustExploratory.ps1" `
  -BaseUrl http://localhost:8080 `
  -Model llama-3.2-1b-instruct:q4_k_m `
  -Users 4 `
  -SpawnRate 2 `
  -RunTime 1m `
  -Kubeconfig .\config\cluster-access\kubeconfig `
  -Namespace genai-thesis
```

### Example 4 — Manual exploratory run with explicit output prefix

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\exploratory\Start-LocustExploratory.ps1" `
  -BaseUrl http://localhost:8080 `
  -Model llama-3.2-1b-instruct:q4_k_m `
  -Users 3 `
  -SpawnRate 1 `
  -RunTime 90s `
  -CsvPrefix .\results\exploratory\manual_run\custom-E4 `
  -Kubeconfig .\config\cluster-access\kubeconfig `
  -Namespace genai-thesis
```

---

## Standard Bash Execution

### Example 1 — E1 smoke single-user validation

```bash
bash ./scripts/load/exploratory/start-locust-exploratory.sh \
  --base-url http://localhost:8080 \
  --model llama-3.2-1b-instruct:q4_k_m \
  --users 1 \
  --spawn-rate 1 \
  --run-time 1m \
  --kubeconfig ./config/cluster-access/kubeconfig \
  --namespace genai-thesis
```

### Example 2 — E2 low-load two-user validation

```bash
bash ./scripts/load/exploratory/start-locust-exploratory.sh \
  --base-url http://localhost:8080 \
  --model llama-3.2-1b-instruct:q4_k_m \
  --users 2 \
  --spawn-rate 1 \
  --run-time 1m \
  --kubeconfig ./config/cluster-access/kubeconfig \
  --namespace genai-thesis
```

### Example 3 — E3 small-concurrency four-user validation

```bash
bash ./scripts/load/exploratory/start-locust-exploratory.sh \
  --base-url http://localhost:8080 \
  --model llama-3.2-1b-instruct:q4_k_m \
  --users 4 \
  --spawn-rate 2 \
  --run-time 1m \
  --kubeconfig ./config/cluster-access/kubeconfig \
  --namespace genai-thesis
```

### Example 4 — Manual exploratory run with explicit output prefix

```bash
bash ./scripts/load/exploratory/start-locust-exploratory.sh \
  --base-url http://localhost:8080 \
  --model llama-3.2-1b-instruct:q4_k_m \
  --users 3 \
  --spawn-rate 1 \
  --run-time 90s \
  --csv-prefix ./results/exploratory/manual_run/custom-E4 \
  --kubeconfig ./config/cluster-access/kubeconfig \
  --namespace genai-thesis
```

---

## Useful Optional Flags

### Skip precheck

Use only for controlled debugging when the precheck has already been executed separately and the cluster state is unchanged.

PowerShell:

```powershell
-SkipPrecheck
```

Bash:

```bash
--skip-precheck
```

### Skip API smoke

Use only if the smoke test has already passed for the same deployed scenario and the endpoint state is unchanged.

PowerShell:

```powershell
-SkipApiSmoke
```

Bash:

```bash
--skip-api-smoke
```

### Skip warm-up

Use only for troubleshooting phase handling or when testing launcher behavior rather than workload behavior.

PowerShell:

```powershell
-SkipWarmUp
```

Bash:

```bash
--skip-warm-up
```

### Dry-run mode

Use dry-run to inspect the resolved execution plan without running Locust.

PowerShell:

```powershell
-DryRun
```

Bash:

```bash
--dry-run
```

Dry-run is strongly recommended after changing:

- phase configuration;
- protocol configuration;
- metric-set configuration;
- output prefixes;
- model selection;
- exploratory scenario parameters.

---

## Parameters You Should Normally Keep Stable

During exploratory validation, avoid changing multiple dimensions at once.

Keep the following stable unless you are explicitly debugging a specific issue:

- target model;
- deployment topology;
- namespace;
- endpoint exposure method;
- Locust file;
- validation profile set;
- metric-set profile;
- cluster-capture profile.

Exploratory validation is meant to test operational readiness, not to produce comparative multi-variable findings.

---

## Output Artifacts

The exploratory launcher should produce a coherent set of artifacts under the selected output prefix.

Expected artifact groups include:

### Phase artifacts

- warm-up CSV files;
- measurement CSV files;
- phase manifest (`_phases.json`).

### Protocol artifacts

- protocol manifest;
- protocol text rendering.

### Client-side metrics

Based on `MS1`, expect client-side metrics to include at least:

- request count;
- success count and/or success rate;
- failure count;
- mean response time;
- p50;
- p95;
- p99;
- throughput.

### Cluster-side artifacts

Based on `CS1`, expect artifacts collected before and after the run, including cluster-state snapshots such as:

- `kubectl get pods -o wide` output;
- `kubectl top pods` output;
- `kubectl top nodes` output;
- services snapshot;
- events snapshot;
- final cluster-side state relevant to the run.

### Validation artifacts

If precheck is enabled, validation outputs associated with the run should also be present.

---

## How to Review an Exploratory Run

After a run finishes, review it in the following order.

### 1. Confirm launcher success

Verify that the launcher completed without interruption and did not terminate during precheck, smoke, warm-up, or measurement.

### 2. Confirm warm-up succeeded

Check that warm-up artifacts exist and that the warm-up phase was actually executed unless it was intentionally disabled.

### 3. Confirm measurement artifacts exist

Verify that the measurement CSV outputs were written to the expected path.

### 4. Confirm protocol and phase manifests exist

These files are essential to prove what the launcher actually executed.

### 5. Confirm cluster-side evidence exists

Do not consider the run operationally useful if the cluster-side pre/post evidence is missing.

### 6. Inspect basic result quality

Check for:

- request failures;
- extreme response times;
- abrupt throughput collapse;
- pod restarts during the run;
- obvious scheduling or readiness instability.

### 7. Decide whether to proceed

A clean exploratory run should justify moving toward one of:

- the official baseline execution;
- a pilot sweep run;
- a deployment correction step if issues were discovered.

---

## Decision Rules

### A run is considered operationally successful when

- the deployed scenario remains reachable throughout the run;
- precheck passes or was intentionally skipped with justification;
- API smoke validation passes or was intentionally skipped with justification;
- warm-up completes successfully unless intentionally disabled;
- measurement completes successfully;
- client-side artifacts are generated;
- cluster-side artifacts are generated;
- no unexpected systemic failure invalidates the run.

### A run should be treated as exploratory failure when

- the endpoint is unreachable;
- API smoke fails;
- Locust cannot execute the request flow correctly;
- the application produces repeated request failures;
- the cluster shows major instability or repeated pod restarts;
- the required artifacts are missing.

An exploratory failure is not wasted work. It is often the fastest way to detect deployment, model, routing, or observability issues before pilot benchmarking.

---

## What You May Conclude from This Phase

You may conclude:

- the scenario is operationally ready or not ready for benchmark progression;
- the API path and payload are functioning under repeated synthetic requests;
- the current deployment can or cannot tolerate low-intensity and small-concurrency traffic;
- artifact generation and cluster-side capture are working as intended;
- the next phase can begin safely or requires remediation.

You may **not** conclude:

- final performance of a model or topology;
- comparative superiority of one scenario over another;
- statistically stable latency or throughput rankings;
- final worker-count, placement, or model conclusions.

---

## Common Failure Modes and Troubleshooting

### Precheck failure

Typical causes:

- wrong kubeconfig path;
- VPN not active;
- wrong namespace;
- node readiness issue;
- metrics pipeline unavailable.

Action:

- stop the exploratory run;
- fix infrastructure or access conditions;
- rerun precheck before retrying.

### API smoke failure

Typical causes:

- LocalAI server not reachable;
- model not loaded correctly;
- wrong endpoint exposure method;
- service reachability issue or failure in the automatic local endpoint preparation logic;
- runtime model mismatch.

Action:

- inspect service exposure and server logs;
- confirm `/v1/models` output;
- retry smoke manually before relaunching the full exploratory flow.

### Measurement starts but requests fail

Typical causes:

- payload mismatch with the selected model;
- LocalAI runtime instability;
- worker-side errors;
- server/worker incompatibility in the deployed topology.

Action:

- review Locust logs and LocalAI logs;
- re-run the smoke test;
- validate the deployed composition and model selection.

### Missing cluster-side artifacts

Typical causes:

- cluster capture script failure;
- missing `kubectl` access;
- wrong namespace or kubeconfig;
- write-permission issue in the output path.

Action:

- rerun only after ensuring cluster-side evidence can be captured;
- do not promote the run to any later phase if cluster evidence is incomplete.

### Warm-up succeeds but measurement degrades sharply

Typical causes:

- too aggressive exploratory concurrency;
- resource contention;
- placement-specific instability;
- model behavior under repeated generation requests.

Action:

- inspect cluster-side snapshots;
- compare pod allocation and resource usage;
- reduce concurrency or revisit the deployment before entering structured sweeps.

---

## Recommended Exit Criteria

You may leave this phase and continue to the next one when all the following are true:

- at least one exploratory run completed successfully;
- phase and protocol manifests are present;
- Locust measurement artifacts are present;
- cluster-side artifacts are present;
- there is no unresolved blocker in endpoint availability, model loading, worker communication, or artifact collection.

Recommended progression:

- if the deployed scenario is meant to become the reference configuration, continue to the **official baseline execution** runbook;
- if the deployment is already baseline-stable and exploratory validation was used only as an intermediate check, continue to the appropriate **pilot sweep** runbook.

---

## Next Runbook

After this phase, proceed to one of the following depending on your execution plan:

- `05-official-baseline-execution.md` if the scenario is the selected reference configuration and the baseline run has not yet been executed;
- `07-pilot-sweeps-execution.md` if the baseline is already established and the goal is to begin exploratory pilot sweeps.

