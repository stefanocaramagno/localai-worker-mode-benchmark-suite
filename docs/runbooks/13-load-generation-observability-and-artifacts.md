# Load Generation, Observability, and Artifacts

## Purpose

This runbook explains how load generation, observability collection, and artifact management work in the LocalAI worker-mode benchmark suite.

It is not the primary entry point for executing complete cycles. Complete cycle execution is documented in:

```text
docs/runbooks/06-fixed-cluster-c0-execution.md
docs/runbooks/07-provider-backed-c1-baseline-execution.md
docs/runbooks/08-provider-backed-c2-c6-campaign-execution.md
docs/runbooks/09-default-scheduler-c7-baseline-execution.md
docs/runbooks/10-resource-aware-scheduler-c8-execution.md
docs/runbooks/11-network-aware-scheduler-c9-execution.md
```

This runbook focuses on the operational mechanics behind those executions:

1. how Locust generates benchmark traffic against LocalAI;
2. how warm-up and measurement phases are separated;
3. which client-side and cluster-side metrics are considered canonical;
4. how pre-benchmark and post-benchmark cluster evidence is collected;
5. how minimal observability snapshots are generated;
6. how resource-aware scheduler evidence is captured for C8;
7. how network-aware scheduler evidence is captured for C9;
8. how artifacts are organized under `results/`;
9. how generated artifacts should be inspected after a run.

---

## Repository Root Assumption

All commands in this runbook assume that the current working directory is the repository root:

```text
localai-worker-mode-benchmark-suite/
```

### Windows PowerShell

```powershell
Get-ChildItem
```

### Bash

```bash
ls
```

A valid repository root contains at least:

```text
config/
docs/
infra/
load-tests/
scripts/
requirements.txt
```

---

## Canonical Namespace

The canonical application namespace for the main single-tenant LocalAI benchmark is:

```text
localai-benchmark
```

Multi-tenant scenarios may create additional namespace-scoped LocalAI deployments, such as:

```text
genai-tenant-a
genai-tenant-b
```

The benchmark target remains defined by the active cycle or runtime configuration. Do not infer the benchmark target only from the namespace name.

---

## Load Generation Architecture

The benchmark suite uses Locust as the load-generation engine.

The canonical Locust file is:

```text
load-tests/locust/locustfile.py
```

The Locust workload is intentionally small and controlled. It sends OpenAI-compatible requests to the LocalAI API endpoint exposed by the deployed `localai-server`.

The workload uses two LocalAI endpoints:

```text
GET  /v1/models
POST /v1/chat/completions
```

The startup model check verifies that the configured model is exposed by `/v1/models`.

The main benchmark task sends a chat completion request to `/v1/chat/completions`.

The default runtime values used by the Locust file are:

```text
LOCALAI_MODEL=llama-3.2-1b-instruct:q4_k_m
LOCALAI_TEMPERATURE=0.1
LOCALAI_REQUEST_TIMEOUT_SECONDS=120
LOCALAI_PROMPT=Reply with only READY.
LOCALAI_STARTUP_MODEL_CHECK_ENABLED=true
```

These defaults may be overridden by the benchmark launchers according to the selected baseline, scenario, or generated runtime configuration.

---

## Canonical Load Generation Inputs

The canonical benchmark inputs are configuration-driven.

| Input class | Canonical location | Purpose |
|---|---|---|
| Locust workload | `load-tests/locust/locustfile.py` | Defines the HTTP task executed against LocalAI |
| Phase profile | `config/phases/profiles/WM_STANDARD_WARMUP_MEASUREMENT.json` | Defines warm-up and measurement separation |
| Execution protocol | `config/protocol/profiles/EP_STANDARD_BENCHMARK_PROTOCOL.json` | Defines the expected benchmark execution sequence |
| Metric set | `config/metric-set/profiles/MS_STANDARD_BENCHMARK_METRICS.json` | Defines required client-side and cluster-side metrics |
| Cluster capture profile | `config/cluster-capture/profiles/CS_STANDARD_CLUSTER_CAPTURE.json` | Defines Kubernetes evidence collected before and after runs |
| Historical baseline | `config/scenarios/baseline/B0.json` | Defines the fixed-cluster historical baseline |
| Provider-backed baseline | `config/scenarios/baseline/B1.json` | Defines the provider-backed baseline |
| Cycle profiles | `config/experimental-cycles/C*.json` | Define cycle-level execution context |
| Runtime configs | `results/experimental-cycles/<cycle>/execution/generated-runtime-configs/` | Define generated per-variant benchmark inputs |

Do not manually edit generated runtime configuration under `results/`. Those files are derived from repository configuration and cycle execution logic.

---

## Phase Separation

The standard benchmark phase profile is:

```text
config/phases/profiles/WM_STANDARD_WARMUP_MEASUREMENT.json
```

The standard model separates benchmark execution into:

1. **warm-up phase**;
2. **measurement phase**.

The warm-up phase is used to stabilize the application before recording the official measurement artifacts.

The measurement phase is the source of the benchmark metrics used by diagnosis, reporting, and completion gates.

The phase profile controls, among other properties:

```text
warmUpEnabled
warmUpDuration
warmUpUsersMode
warmUpSpawnRateMode
startupModelCheckDuringWarmUp
startupModelCheckDuringMeasurement
warmUpCsvSuffix
phaseManifestSuffix
```

The expected artifact convention is that warm-up CSV files and measurement CSV files are distinct. Measurement CSV files must not be mixed with warm-up CSV files when computing benchmark results.

---

## Execution Protocol

The canonical benchmark protocol is:

```text
config/protocol/profiles/EP_STANDARD_BENCHMARK_PROTOCOL.json
```

The protocol defines the intended sequence:

```text
controlled cleanup
→ scenario deployment
→ technical precheck
→ API smoke validation
→ optional warm-up
→ measurement
→ client-side artifact collection
→ cluster-side artifact collection
→ final snapshot
→ cleanup or restore placeholder
```

Cycle-level runners and benchmark launchers use this protocol to maintain consistent artifact semantics across C0, C1, C2-C6, C7, C8, and C9.

---

## C7 Multi-Tenant Load Generation

C7 uses tenant-aware load generation for scenarios that deploy more than one tenant-scoped LocalAI application cluster.

The canonical multi-tenant runner is:

```text
scripts/load/multi-tenant/run-multi-tenant-locust.py
```

The wrapper entry points are:

```text
scripts/load/multi-tenant/Start-MultiTenantLocust.ps1
scripts/load/multi-tenant/start-multi-tenant-locust.sh
```

The runner reads the default-scheduler scenario profile and derives tenant-specific benchmark targets and traffic settings.

The canonical wait-time environment variable used by the Locust workload is:

```text
LOCALAI_WAIT_TIME_SECONDS
```

This allows C7 to represent traffic profiles such as:

| Traffic Profile | Tenant A | Tenant B | Tenant C |
|---|---:|---:|---:|
| `TR_1T_UNIFORM_LOW` | 5 s | - | - |
| `TR_2T_UNIFORM_LOW` | 5 s | 5 s | - |
| `TR_2T_DIFFERENTIATED_LOW` | 5 s | 10 s | - |
| `TR_3T_DIFFERENTIATED_LOW` | 5 s | 10 s | 15 s |

Tenant-specific traffic is part of the evidence model. For C7, benchmark artifacts should not be interpreted only as global aggregate values; they should also be inspected per tenant.

### Manual C7 Multi-Tenant Locust Run

Use this only for targeted validation or recovery. Official C7 executions should use the campaign runner.

#### Windows PowerShell

```powershell
python .\scripts\load\multi-tenant\run-multi-tenant-locust.py `
  --repo-root . `
  --scenario-config .\config\scenarios\default-scheduler\DS_2T_4N_L1_DIFFERENTIATED_M1M1_W2.json `
  --kubeconfig .\config\cluster-access\provider-backed\kubeconfig `
  --write-latest-aliases
```

#### Bash

```bash
python scripts/load/multi-tenant/run-multi-tenant-locust.py \
  --repo-root . \
  --scenario-config config/scenarios/default-scheduler/DS_2T_4N_L1_DIFFERENTIATED_M1M1_W2.json \
  --kubeconfig config/cluster-access/provider-backed/kubeconfig \
  --write-latest-aliases
```

Adjust the kubeconfig path to the provider-generated kubeconfig for the active scenario.

---
## Canonical Metric Set

The canonical metric set is:

```text
config/metric-set/profiles/MS_STANDARD_BENCHMARK_METRICS.json
```

The benchmark suite distinguishes between client-side metrics and cluster-side metrics.

### Client-Side Metrics

Client-side metrics are derived from Locust output files.

Canonical client-side metrics include:

```text
request_count
success_rate_percent
failure_count
mean_response_time_ms
p50_response_time_ms
p95_response_time_ms
p99_response_time_ms
throughput_rps
```

These metrics describe how the LocalAI API behaves from the perspective of the load generator.

### Cluster-Side Metrics

Cluster-side metrics are derived from Kubernetes snapshots, metrics-server output, pod state, node state, and events.

Canonical cluster-side metrics include:

```text
max_node_cpu_percent
max_node_memory_percent
node_cpu_percent
node_memory_percent
max_pod_cpu_millicores
max_pod_memory_mib
pod_cpu_millicores
pod_memory_mib
pod_placement
pod_restart_count
pod_readiness
pending_pods_count
failed_pods_count
not_ready_pods_count
kubernetes_events_count
kubernetes_warning_events_count
metrics_api_available
```

Cluster-side metrics are required to interpret whether performance changes are related to application behavior, scheduling placement, CPU pressure, memory pressure, rollout failures, pending pods, or missing observability support.

---

## Locust Client-Side Artifacts

Locust generates CSV artifacts using the selected CSV prefix.

The expected files include:

```text
<prefix>_stats.csv
<prefix>_stats_history.csv
<prefix>_failures.csv
<prefix>_exceptions.csv
```

Depending on the run mode and Locust behavior, some files may be empty but still valid. For example, a successful run may produce an empty failures file.

The most important file for benchmark aggregation is usually:

```text
<prefix>_stats.csv
```

The history file is useful for time-series inspection:

```text
<prefix>_stats_history.csv
```

---

## Cluster-Side Artifacts

The canonical cluster capture profile is:

```text
config/cluster-capture/profiles/CS_STANDARD_CLUSTER_CAPTURE.json
```

Cluster-side evidence is collected before and after the benchmark where applicable.

The expected artifact classes include:

```text
_nodes-wide.txt
_nodes.json
_top-nodes.txt
_pods-wide.txt
_pods.json
_top-pods.txt
_top-pods-containers.txt
_services.txt
_events.txt
_events.json
_pods-describe.txt
```

Cluster-side artifacts are important because benchmark results without Kubernetes context are incomplete. For example, a latency increase may be caused by real application degradation, a pending pod, placement changes, resource saturation, missing metrics, or rollout instability.

---

## Minimal Observability

Minimal observability is implemented through Kubernetes API and metrics-server snapshots.

The canonical minimal observability profile available in the repository is:

```text
config/observability-minimal/profiles/MO_C1_PROVIDER_BACKED_BASELINE.json
```

Provider-backed campaigns may generate runtime observability profiles or use cycle-level bindings derived from templates.

The canonical minimal observability template is:

```text
config/observability-minimal/templates/MO_PROVIDER_BACKED_OBSERVABILITY_TEMPLATE.json
```

Expected minimal observability artifacts include:

```text
latest-minimal-observability-manifest.json
latest-minimal-observability-summary.txt
latest-minimal-observability-metrics.json
```

Minimal observability intentionally avoids requiring a full external observability stack. It is designed to remain usable on K3s clusters where metrics-server and Kubernetes API snapshots are the primary sources of operational evidence.

---

## Artifact Roots

Generated artifacts are stored under:

```text
results/
```

The current cycle-oriented artifact root is:

```text
results/experimental-cycles/
```

The main cycle roots are:

```text
results/experimental-cycles/C0/
results/experimental-cycles/C1/
results/experimental-cycles/C2/
results/experimental-cycles/C3/
results/experimental-cycles/C4/
results/experimental-cycles/C5/
results/experimental-cycles/C6/
```

The `results/` tree is generated output. It may be removed and regenerated using the documented execution procedures.

---

## C0 Artifact Layout

C0 represents the historical fixed-cluster execution track.

The frozen C0 artifact layout is organized under:

```text
results/experimental-cycles/C0/
```

Expected C0 artifact groups include:

```text
results/experimental-cycles/C0/artifacts/diagnosis/
results/experimental-cycles/C0/artifacts/reporting/
results/experimental-cycles/C0/artifacts/completion-gate/
```

During regeneration, C0 benchmark artifacts are also expected to be produced through the historical baseline, exploratory validation, pilot sweeps, consolidated pilot campaign, diagnosis, reporting, completion gate, and freeze procedures described in the C0 execution runbook.

Use C0 artifacts only as generated benchmark evidence. Do not treat previous files under `results/` as immutable source configuration.

---

## C1 Artifact Layout

C1 represents the provider-backed baseline execution track.

The expected C1 root is:

```text
results/experimental-cycles/C1/
```

Important C1 artifact groups include:

```text
results/experimental-cycles/C1/infrastructure/
results/experimental-cycles/C1/application/
results/experimental-cycles/C1/benchmark/
results/experimental-cycles/C1/observability/
results/experimental-cycles/C1/diagnosis/
results/experimental-cycles/C1/reporting/
results/experimental-cycles/C1/completion-gate/
results/experimental-cycles/C1/freeze/
results/experimental-cycles/C1/execution/
```

The C1 benchmark subtree contains the official provider-backed baseline measurements.

The C1 observability subtree contains minimal observability snapshots and latest aliases when enabled.

---

## C2-C6 Campaign Artifact Layout

C2-C6 are comparative provider-backed campaigns.

The expected campaign roots are:

```text
results/experimental-cycles/C2/
results/experimental-cycles/C3/
results/experimental-cycles/C4/
results/experimental-cycles/C5/
results/experimental-cycles/C6/
```

Each comparative campaign may contain:

```text
results/experimental-cycles/<cycle>/variants/
results/experimental-cycles/<cycle>/benchmark/
results/experimental-cycles/<cycle>/diagnosis/
results/experimental-cycles/<cycle>/reporting/
results/experimental-cycles/<cycle>/completion-gate/
results/experimental-cycles/<cycle>/freeze/
results/experimental-cycles/<cycle>/execution/
```

The `variants/` subtree stores per-scenario execution evidence. The `benchmark/` subtree stores measured Locust artifacts and related benchmark outputs. The `diagnosis/`, `reporting/`, `completion-gate/`, and `freeze/` subtrees store post-processing outputs.

For multi-tenant campaign runs, namespace-scoped artifacts may include additional namespace tokens when evidence is collected from more than one namespace.

---

## C7 Default-Scheduler Artifact Layout

C7 artifacts are organized around default-scheduler scenarios and tenant-scoped evidence.

The campaign-level root is:

```text
results/experimental-cycles/C7/
```

Important subtrees include:

```text
results/experimental-cycles/C7/execution/
results/experimental-cycles/C7/benchmark/default-scheduler/
results/experimental-cycles/C7/variants/
results/experimental-cycles/C7/scheduler/
results/experimental-cycles/C7/diagnosis/
results/experimental-cycles/C7/reporting/
results/experimental-cycles/C7/completion-gate/
results/experimental-cycles/C7/freeze/
results/experimental-cycles/C7/artifacts/
```

The scheduler evidence should include files named:

```text
default-scheduler-decision-evidence.json
```

The benchmark evidence should include tenant-scoped Locust outputs and an aggregate summary when a scenario has more than one tenant.

C7 artifact quality depends on the presence of both performance evidence and placement evidence. A C7 run with benchmark CSV files but without scheduler decision evidence is incomplete for default-scheduler analysis.


## C8 Resource-Aware Scheduler Artifact Layout

C8 artifacts are organized around resource-aware-scheduler variants and paired logical scenarios.

The campaign-level root is:

```text
results/experimental-cycles/C8/
```

Important subtrees include:

```text
results/experimental-cycles/C8/execution/
results/experimental-cycles/C8/execution/generated-runtime-configs/
results/experimental-cycles/C8/benchmark/resource-aware-scheduler/
results/experimental-cycles/C8/scheduler/
results/experimental-cycles/C8/scheduler/custom-scheduler/
results/experimental-cycles/C8/observability/mon-agent/
results/experimental-cycles/C8/rescheduling/
results/experimental-cycles/C8/observability/minimal/
results/experimental-cycles/C8/diagnosis/
results/experimental-cycles/C8/reporting/
results/experimental-cycles/C8/completion-gate/
results/experimental-cycles/C8/freeze/
results/experimental-cycles/C8/artifacts/
```

The resource-aware scheduler evidence should include files named:

```text
resource-aware-scheduler-decision-evidence.json
```

C8 benchmark artifacts must preserve scheduler-aware metadata, including:

```text
schedulerMode
schedulerName
effectiveSchedulerName
logicalScenarioId
schedulerComparisonRole
pairedDefaultVariantId
pairedLoadAwareVariantId
```

For load-aware variants, artifact metadata should identify:

```text
loadaware_custom_scheduler
scheduler-plugins-scheduler
```

For default variants, artifact metadata should identify:

```text
kubernetes_default_scheduler
default-scheduler
```

The official measurement window must start after telemetry priming, annotation validation, controlled redeployment, readiness waiting, and stabilization have completed.

---

## C9 Network-Aware Scheduler Artifact Layout

C9 artifacts are organized around network-aware scheduler variants and logical scenario triplets. Each logical scenario should preserve comparable evidence for:

```text
DEFAULT
LOADAWARE
NETAWARE
```

The campaign-level root is:

```text
results/experimental-cycles/C9/
```

Important subtrees include:

```text
results/experimental-cycles/C9/execution/
results/experimental-cycles/C9/execution/generated-runtime-configs/
results/experimental-cycles/C9/benchmark/network-aware-scheduler/
results/experimental-cycles/C9/scheduler/
results/experimental-cycles/C9/scheduler/custom-scheduler/
results/experimental-cycles/C9/variants/<scenario-id>/observability/minimal/
results/experimental-cycles/C9/variants/<scenario-id>/network-aware-scheduler/mon-agent/
results/experimental-cycles/C9/variants/<scenario-id>/network-aware-scheduler/mentat/
results/experimental-cycles/C9/variants/<scenario-id>/network-aware-scheduler/istio/
results/experimental-cycles/C9/variants/<scenario-id>/network-aware-scheduler/cluster-lens/
results/experimental-cycles/C9/variants/<scenario-id>/network-aware-scheduler/telemetry-priming/
results/experimental-cycles/C9/variants/<scenario-id>/network-aware-scheduler/rescheduling/
results/experimental-cycles/C9/variants/<scenario-id>/network-aware-scheduler/cluster-lens/stages/<capture-stage>/
results/experimental-cycles/C9/diagnosis/
results/experimental-cycles/C9/reporting/
results/experimental-cycles/C9/completion-gate/
results/experimental-cycles/C9/freeze/
results/experimental-cycles/C9/artifacts/
```

## C9 cluster-lens Placement Artifacts

C9 captures read-only cluster-lens placement evidence at the configured pipeline stages. The primary benchmark-state evidence is stored directly under the variant-level `cluster-lens/` root; auxiliary stage snapshots are stored under `cluster-lens/stages/<capture-stage>/`.

Canonical cluster-lens artifacts are:

```text
cluster-lens-snapshot.json
cluster-lens-kubernetes-pods.json
cluster-lens-kubernetes-deployments.json
cluster-lens-kubernetes-nodes.json
cluster-lens-placement-summary.json
cluster-lens-placement-signature.csv
cluster-lens-capture-manifest.json
cluster-lens-primary-stage-manifest.json
```

The raw cluster-lens snapshot is useful for topology inspection. The Kubernetes snapshots are authoritative for `schedulerName`, labels, annotations, unscheduled pods, and owner/deployment relationships. The placement signature CSV is the preferred artifact for comparing scheduler triplets.

Use the primary artifacts under the variant-level `cluster-lens/` root for downstream diagnosis, reporting, completion-gate, and freeze interpretation. Use `cluster-lens/stages/<capture-stage>/` when auditing how placement evolved across capture stages or when investigating a missing primary artifact.

Do not infer C9 placement from latency or traffic artifacts alone. Use the placement signature together with scheduler decision evidence and benchmark results. In the C9 report, topology fields indicate whether the cluster view was comparable across scheduler modes, while tenant-placement fields indicate whether LocalAI pod placement changed across `DEFAULT`, `LOADAWARE`, and `NETAWARE`.

---

C9 benchmark artifacts must preserve network-aware metadata, including:

```text
schedulerMode
schedulerName
effectiveSchedulerName
logicalScenarioId
networkAwareSchedulerRole
latencyProfileId
trafficProfileId
tenantCount
modelMix
gatewayTrafficKey
```

For network-aware variants, artifact metadata should identify:

```text
localai_resource_network_aware_custom_scheduler
scheduler-plugins-scheduler
NetworkAwareLocalAi
```

For load-aware variants, artifact metadata should identify the same second scheduler without the network-aware scoring component. For default variants, artifact metadata should identify the Kubernetes default scheduler and preserve the absence of an explicit `schedulerName`.

The official measurement window must start only after gateway routing validation, telemetry priming, annotation validation, controlled redeployment, readiness waiting, and stabilization have completed.

---

## Check Locust Availability

Use the following commands to verify that Locust is available in the active Python environment.

### Windows PowerShell

```powershell
python -m locust --version
```

### Bash

```bash
python3 -m locust --version || python -m locust --version
```

---

## Inspect the Canonical Locust File

Use the following commands to inspect the workload definition.

### Windows PowerShell

```powershell
Get-Content .\load-tests\locust\locustfile.py -TotalCount 80
```

### Bash

```bash
sed -n '1,80p' load-tests/locust/locustfile.py
```

The workload should define a Locust `HttpUser` that performs a startup model check and sends chat completion requests to LocalAI.

---

## Standalone Exploratory Load Run

The complete cycle-specific procedures for `C0` through `C9` should normally be preferred over standalone manual runs.

A standalone exploratory run may still be useful when validating that LocalAI is reachable before executing a full cycle.

The following example assumes that:

1. a LocalAI deployment is already running;
2. `localai-server` is reachable through `http://localhost:8080`;
3. the selected kubeconfig and namespace are valid.

### Windows PowerShell

```powershell
.\scripts\load\exploratory\Start-LocustExploratory.ps1 `
  -BaseUrl "http://localhost:8080" `
  -Model "llama-3.2-1b-instruct:q4_k_m" `
  -Users 1 `
  -SpawnRate 1 `
  -RunTime "1m" `
  -CsvPrefix ".\results\_runtime\manual\exploratory\locust-smoke" `
  -LocustFile ".\load-tests\locust\locustfile.py" `
  -Kubeconfig ".\config\cluster-access\fixed-cluster\kubeconfig" `
  -Namespace "localai-benchmark" `
  -PhaseConfig ".\config\phases\profiles\WM_STANDARD_WARMUP_MEASUREMENT.json" `
  -ProtocolConfig ".\config\protocol\profiles\EP_STANDARD_BENCHMARK_PROTOCOL.json" `
  -ClusterCaptureConfig ".\config\cluster-capture\profiles\CS_STANDARD_CLUSTER_CAPTURE.json" `
  -MetricSetConfig ".\config\metric-set\profiles\MS_STANDARD_BENCHMARK_METRICS.json"
```

### Bash

```bash
./scripts/load/exploratory/start-locust-exploratory.sh \
  --base-url "http://localhost:8080" \
  --model "llama-3.2-1b-instruct:q4_k_m" \
  --users 1 \
  --spawn-rate 1 \
  --run-time "1m" \
  --csv-prefix "./results/_runtime/manual/exploratory/locust-smoke" \
  --locust-file "./load-tests/locust/locustfile.py" \
  --kubeconfig "./config/cluster-access/fixed-cluster/kubeconfig" \
  --namespace "localai-benchmark" \
  --phase-config "./config/phases/profiles/WM_STANDARD_WARMUP_MEASUREMENT.json" \
  --protocol-config "./config/protocol/profiles/EP_STANDARD_BENCHMARK_PROTOCOL.json" \
  --cluster-capture-config "./config/cluster-capture/profiles/CS_STANDARD_CLUSTER_CAPTURE.json" \
  --metric-set-config "./config/metric-set/profiles/MS_STANDARD_BENCHMARK_METRICS.json"
```

Use standalone exploratory runs only for validation or troubleshooting. Official cycle artifacts should be produced through the cycle-specific runbooks.

---

## Minimal Metrics Validation

The validation metrics exporter sends a small number of LocalAI requests and writes compact metrics artifacts. It is useful for validating the API path and metric extraction logic before a longer benchmark.

### Windows PowerShell

```powershell
.\scripts\validation\precheck\Export-ValidationMetrics.ps1 `
  -BaseUrl "http://localhost:8080" `
  -Model "llama-3.2-1b-instruct:q4_k_m" `
  -Iterations 5 `
  -PauseSeconds 2 `
  -OutputPrefix ".\results\_runtime\manual\validation\minimal-metrics" `
  -MetricSetConfig ".\config\metric-set\profiles\MS_STANDARD_BENCHMARK_METRICS.json"
```

### Bash

```bash
./scripts/validation/precheck/export-validation-metrics.sh \
  --base-url "http://localhost:8080" \
  --model "llama-3.2-1b-instruct:q4_k_m" \
  --iterations 5 \
  --pause-seconds 2 \
  --output-prefix "./results/_runtime/manual/validation/minimal-metrics" \
  --metric-set-config "./config/metric-set/profiles/MS_STANDARD_BENCHMARK_METRICS.json"
```

---

## Manual Cluster-Side Capture

Cluster-side capture is normally executed automatically by the benchmark protocol.

Manual capture is useful when diagnosing a running deployment or checking whether the metrics API is available.

### Windows PowerShell

```powershell
.\scripts\validation\cluster-side\Collect-ClusterSideArtifacts.ps1 `
  -ProfileConfig ".\config\cluster-capture\profiles\CS_STANDARD_CLUSTER_CAPTURE.json" `
  -Kubeconfig ".\config\cluster-access\fixed-cluster\kubeconfig" `
  -Namespace "localai-benchmark" `
  -OutputPrefix ".\results\_runtime\manual\cluster-capture\localai-benchmark" `
  -Stage "post"
```

### Bash

```bash
./scripts/validation/cluster-side/collect-cluster-side-artifacts.sh \
  --profile-config "./config/cluster-capture/profiles/CS_STANDARD_CLUSTER_CAPTURE.json" \
  --kubeconfig "./config/cluster-access/fixed-cluster/kubeconfig" \
  --namespace "localai-benchmark" \
  --output-prefix "./results/_runtime/manual/cluster-capture/localai-benchmark" \
  --stage "post"
```

For multi-tenant inspection, include additional namespaces.

### Windows PowerShell

```powershell
.\scripts\validation\cluster-side\Collect-ClusterSideArtifacts.ps1 `
  -ProfileConfig ".\config\cluster-capture\profiles\CS_STANDARD_CLUSTER_CAPTURE.json" `
  -Kubeconfig ".\config\cluster-access\generated\proxmox-k3s\c6-1cp-4w-8c16g\kubeconfig" `
  -Namespace "genai-tenant-a" `
  -AdditionalNamespaces "genai-tenant-b" `
  -OutputPrefix ".\results\_runtime\manual\cluster-capture\multi-tenant" `
  -Stage "post"
```

### Bash

```bash
./scripts/validation/cluster-side/collect-cluster-side-artifacts.sh \
  --profile-config "./config/cluster-capture/profiles/CS_STANDARD_CLUSTER_CAPTURE.json" \
  --kubeconfig "./config/cluster-access/generated/proxmox-k3s/c6-1cp-4w-8c16g/kubeconfig" \
  --namespace "genai-tenant-a" \
  --additional-namespaces "genai-tenant-b" \
  --output-prefix "./results/_runtime/manual/cluster-capture/multi-tenant" \
  --stage "post"
```

---

## Manual Minimal Observability Capture

Minimal observability is normally integrated into provider-backed cycle and campaign execution.

Manual capture can be used to inspect a deployed cluster before or after benchmark execution.

### Windows PowerShell

```powershell
.\scripts\observability\minimal\Start-MinimalObservability.ps1 `
  -CycleConfig ".\config\experimental-cycles\C1.json" `
  -ProfileConfig ".\config\observability-minimal\profiles\MO_C1_PROVIDER_BACKED_BASELINE.json" `
  -Action "capture" `
  -Stage "post-benchmark" `
  -Kubeconfig ".\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig" `
  -Namespace "localai-benchmark" `
  -OutputRoot ".\results\_runtime\manual\observability\C1" `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/observability/minimal/start-minimal-observability.sh \
  --cycle-config "./config/experimental-cycles/C1.json" \
  --profile-config "./config/observability-minimal/profiles/MO_C1_PROVIDER_BACKED_BASELINE.json" \
  --action "capture" \
  --stage "post-benchmark" \
  --kubeconfig "./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig" \
  --namespace "localai-benchmark" \
  --output-root "./results/_runtime/manual/observability/C1" \
  --write-latest-aliases
```

Use cycle-generated or campaign-generated observability profiles when the cycle runner creates more specific runtime profiles.

---

## Inspect Generated Client-Side CSV Files

Use the following commands to list Locust CSV files generated under a cycle.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C1\benchmark -Recurse -File |
  Where-Object { $_.Name -match "_stats\.csv$|_stats_history\.csv$|_failures\.csv$|_exceptions\.csv$" } |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C1/benchmark -type f \
  \( -name "*_stats.csv" -o -name "*_stats_history.csv" -o -name "*_failures.csv" -o -name "*_exceptions.csv" \)
```

---

## Preview Locust Statistics

Use the following commands to preview a Locust statistics file.

### Windows PowerShell

```powershell
Import-Csv ".\results\experimental-cycles\C1\benchmark\baseline\official\B1_runA_stats.csv" |
  Select-Object -First 10
```

### Bash

```bash
head -n 10 ./results/experimental-cycles/C1/benchmark/baseline/official/B1_runA_stats.csv
```

Adjust the path according to the actual cycle, variant, scenario, and replica produced by the run.

---

## Inspect Cluster Capture Files

Use the following commands to list cluster-side evidence files.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C1 -Recurse -File |
  Where-Object { $_.Name -match "nodes-wide|top-nodes|pods-wide|top-pods|events|pods-describe|pods\.json|nodes\.json" } |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C1 -type f \
  \( -name "*nodes-wide.txt" -o -name "*top-nodes.txt" -o -name "*pods-wide.txt" -o -name "*top-pods.txt" -o -name "*events.txt" -o -name "*pods-describe.txt" -o -name "*pods.json" -o -name "*nodes.json" \)
```

---

## Inspect Minimal Observability Outputs

Use the following commands to inspect latest minimal observability aliases.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C1\observability -Recurse -File |
  Where-Object { $_.Name -match "latest-minimal-observability" } |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C1/observability -type f -name "latest-minimal-observability*"
```

---

## Validate JSON Artifacts

Use the following commands to validate that a generated JSON artifact can be parsed.

### Windows PowerShell

```powershell
Get-Content ".\results\experimental-cycles\C1\observability\minimal\latest-minimal-observability-manifest.json" -Raw |
  ConvertFrom-Json |
  Select-Object -First 1
```

### Bash

```bash
python3 -m json.tool ./results/experimental-cycles/C1/observability/minimal/latest-minimal-observability-manifest.json >/dev/null
```

If `python3` is not available, use `python` in Bash.

---

## Inspect Variant Status Files

Comparative campaigns write per-variant evidence under the `variants/` subtree.

Use the following commands to inspect variant-related files for C2-C6.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C2\variants -Recurse -File |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C2/variants -type f
```

Replace `C2` with `C3`, `C4`, `C5`, or `C6` as needed.

---

## Inspect Reporting Scenario Summaries

Reporting outputs are documented in the reporting runbook, but the scenario summary is often useful when checking whether benchmark metrics were aggregated correctly.

### Windows PowerShell

```powershell
Import-Csv ".\results\experimental-cycles\C2\reporting\scenario-summary.csv" |
  Format-Table -AutoSize
```

### Bash

```bash
column -s, -t < ./results/experimental-cycles/C2/reporting/scenario-summary.csv | head -n 40
```

If `column` is unavailable, use:

```bash
head -n 40 ./results/experimental-cycles/C2/reporting/scenario-summary.csv
```

---

## Inspect C7 Scheduler Evidence

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C7 -Recurse `
  -Filter "default-scheduler-decision-evidence.json" |
  Select-Object FullName, Length
```

### Bash

```bash
find results/experimental-cycles/C7 -name "default-scheduler-decision-evidence.json" -print | sort
```

For each executed C7 scenario, verify that scheduler evidence can be related to:

- tenant-specific Locust artifacts;
- latency profile;
- resource pressure;
- pod placement classification;
- errors, timeouts, or unsupported status.

---

## Inspect C8 mon-agent and Rescheduling Evidence

C8 requires runtime evidence from `mon-agent` and from the telemetry-primed redeployment procedure.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C8\observability\mon-agent -Recurse | Select-Object FullName
Get-ChildItem .\results\experimental-cycles\C8\rescheduling -Recurse | Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C8/observability/mon-agent -maxdepth 5 -type f | sort
find ./results/experimental-cycles/C8/rescheduling -maxdepth 5 -type f | sort
```

The required annotation evidence is:

```text
cpu-usage
memory-usage
```

on nodes and selected LocalAI deployments. Optional annotations such as `disk-bandwidth` and `network-bandwidth` may be captured when emitted by the monitoring agent, but they are not required optimization inputs for C8.

---

## Inspect C9 Network-Aware Telemetry Evidence

C9 requires runtime evidence from Istio, Mentat, `mon-agent`, scheduler decisions, telemetry priming, and controlled rescheduling.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse |
  Where-Object { $_.FullName -match 'network-aware-scheduler' } |
  Select-Object FullName

Get-ChildItem .\results\experimental-cycles\C9\scheduler -Recurse | Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C9/variants -path '*network-aware-scheduler*' -type f | sort
find ./results/experimental-cycles/C9/scheduler -maxdepth 6 -type f | sort
```

The required evidence should include:

```text
Istio Gateway and VirtualService evidence
mon-agent node and deployment annotation evidence
Mentat internode latency, packet-loss, and bandwidth evidence
telemetry-priming evidence
telemetry-primed rescheduling evidence
scheduler decision evidence for DEFAULT, LOADAWARE, and NETAWARE variants
```

The required annotation evidence includes:

```text
network-latency.<destination-node>
packet-loss.<destination-node>
network-bandwidth.<destination-node>
rps.<peer-workload> or traffic.<peer-workload>
gateway traffic key resolved for the active scheduler profile
```

---

## Expected Artifact Quality Rules

A complete measured run should provide enough evidence to answer all of the following questions:

1. Was the LocalAI API reachable?
2. Was the expected model exposed by `/v1/models`?
3. Did the measurement phase produce Locust statistics?
4. Did the run record failures and exceptions, even if the corresponding files are empty?
5. Were Kubernetes nodes and pods captured before and/or after the benchmark?
6. Was pod placement recorded?
7. Were warning events recorded?
8. Was metrics-server available or was its absence recorded?
9. Were pending, failed, or not-ready pods captured as evidence?
10. Were post-processing outputs able to consume the generated artifacts?

A run that lacks one of these evidence classes may still be useful for troubleshooting, but it should not be treated as a complete benchmark run unless the relevant completion gate accepts that condition explicitly.

---

## Unsupported Scenarios as Evidence

Some scenarios are expected to be operationally unsupported under specific resource, placement, latency, or multi-tenant constraints.

An unsupported scenario must not be silently discarded.

A valid unsupported scenario should leave enough evidence to explain why it was classified as unsupported, for example:

```text
rollout timeout
pending pods
insufficient CPU
insufficient memory
not-ready deployments
missing benchmark target
latency-induced benchmark instability
```

The relevant evidence should be visible in at least one of the following artifact classes:

```text
variant manifest
cluster-side capture
Kubernetes events
pod descriptions
diagnosis output
completion gate output
reporting summary
```

---

## Metrics API Warnings

The benchmark suite relies on metrics-server for `kubectl top` snapshots.

If metrics-server is unavailable or temporarily unable to provide metrics, the run should record the condition as a warning rather than hiding it.

Possible symptoms include:

```text
kubectl top nodes fails
kubectl top pods fails
metrics API unavailable
top-* artifact files contain errors or warnings
```

Metrics-server warnings are operational evidence. They should be considered when interpreting CPU and memory metrics.

---

## Artifact Hygiene

Generated artifacts should not be manually edited.

Recommended practice:

1. modify source configuration under `config/`;
2. rerun the relevant cycle or campaign;
3. regenerate diagnosis, reporting, completion gate, and freeze artifacts;
4. inspect generated outputs under `results/`.

Do not manually patch generated CSV, JSON, HTML, or Markdown reporting outputs to make a run appear successful.

---

## Generated Runtime Configuration

Provider-backed campaigns may generate runtime configuration under paths such as:

```text
results/experimental-cycles/<cycle>/execution/generated-runtime-configs/
```

These files are useful for auditability because they show the concrete configuration resolved for a variant at execution time.

They are not source-of-truth configuration files. If a runtime configuration is incorrect, update the corresponding source profile under `config/` and rerun the cycle or campaign.

---

## Direct Locust Invocation

Direct Locust invocation is not the preferred method for official benchmark runs because it bypasses benchmark protocol logic, cluster capture, smoke validation, phase manifests, and artifact conventions.

Use direct Locust invocation only for isolated debugging.

### Windows PowerShell

```powershell
$env:LOCALAI_MODEL = "llama-3.2-1b-instruct:q4_k_m"
$env:LOCALAI_PROMPT = "Reply with only READY."
$env:LOCALAI_TEMPERATURE = "0.1"
$env:LOCALAI_REQUEST_TIMEOUT_SECONDS = "120"

python -m locust `
  -f ".\load-tests\locust\locustfile.py" `
  --host "http://localhost:8080" `
  --headless `
  --users 1 `
  --spawn-rate 1 `
  --run-time "30s" `
  --csv ".\results\_runtime\manual\direct-locust\direct" `
  --csv-full-history
```

### Bash

```bash
export LOCALAI_MODEL="llama-3.2-1b-instruct:q4_k_m"
export LOCALAI_PROMPT="Reply with only READY."
export LOCALAI_TEMPERATURE="0.1"
export LOCALAI_REQUEST_TIMEOUT_SECONDS="120"

python3 -m locust \
  -f "./load-tests/locust/locustfile.py" \
  --host "http://localhost:8080" \
  --headless \
  --users 1 \
  --spawn-rate 1 \
  --run-time "30s" \
  --csv "./results/_runtime/manual/direct-locust/direct" \
  --csv-full-history
```

After debugging, remove or ignore direct Locust artifacts unless they are intentionally needed for local troubleshooting.

---

## Cleanup of Manual Runtime Artifacts

Manual diagnostic artifacts under `results/_runtime/` may be removed when no longer needed.

### Windows PowerShell

```powershell
Remove-Item -Recurse -Force ".\results\_runtime" -ErrorAction SilentlyContinue
```

### Bash

```bash
rm -rf ./results/_runtime
```

Do not remove official cycle artifacts from `results/experimental-cycles/` unless the full regeneration procedure is being followed.

---

## Readiness Checklist

Before treating a benchmark run as usable evidence, verify that:

1. the benchmark was executed through the intended runbook or cycle runner;
2. the selected `kubeconfig` points to the intended cluster;
3. the expected namespace exists;
4. the expected LocalAI deployments are ready;
5. the selected model is exposed by `/v1/models`;
6. the measurement phase generated Locust CSV files;
7. cluster-side captures exist;
8. minimal observability artifacts exist when required by the cycle;
9. failures, pending pods, rollout timeouts, and metrics warnings are recorded when present;
10. diagnosis, reporting, completion gate, and freeze steps can consume the generated artifacts;
11. for C7, scheduler decision evidence exists for executed default-scheduler scenarios;
12. for C8, resource-aware scheduler evidence, mon-agent annotation evidence, and rescheduling evidence exist;
13. for C9, gateway-routed traffic evidence, network-aware telemetry evidence, cluster-lens placement evidence, scheduler decision evidence, and telemetry-primed rescheduling evidence exist.

---

## Next Runbook

After understanding load generation, observability, and artifact structure, continue with:

```text
docs/runbooks/14-diagnosis-reporting-completion-gate-and-freeze.md
```
