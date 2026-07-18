# C6 — Multi-Tenancy Report

**Cycle ID:** `C6`
**Reporting Profile:** `RP_C6_MULTI_TENANCY`
**Reporting ID:** `REP_C6_20260619T174611Z`
**Generated at UTC:** `2026-06-19T17:47:25Z`

## Purpose

This report compares namespace-scoped LocalAI tenant-cluster coexistence scenarios under fixed provider-backed infrastructure and a fixed primary benchmark workload. It is intended to expose co-tenant contention and model-mix effects on the benchmarked tenant.

The report combines **measurement CSV data**, **minimal observability evidence**, **cluster validation outputs**, **application topology metadata** and **technical diagnosis context** when those artifacts are available.

[Back to cycle report index](../../index.html)

## Cross-cycle baseline reference

The values below describe the global baseline configuration used as a cross-cycle reference. Scenario-specific and sweep-local sections report the effective infrastructure, placement, worker count and runtime configuration used by each scenario. Percentage deltas are computed against the family-local reference scenario when one is defined for the sweep.

| Dimension | Reference value |
|---|---|
| Baseline ID | B1 |
| Model | llama-3.2-1b-instruct:q4_k_m |
| Worker count | 2 |
| Placement | colocated_genai_pb_worker_02 |
| Workload | users=2, spawnRate=1, runTime=2m |
| Prompt | Reply with only READY. |
| Request timeout | 120 s |
| Infrastructure profile | INFRA_C1_1CP_2W_8C16G |
| Placement profile | PL_COLOCATED |

## Family-local reference scenarios

The scenarios below are the sweep-local references used to interpret percentage deltas within each family. They may differ from the cross-cycle baseline when a campaign intentionally varies infrastructure, placement, latency or tenancy.

| Sweep | Reference scenario | Description | Status | Varied dimension |
|---|---|---|---|---|
| Multi-Tenancy | `MT_SINGLE_TENANT_REFERENCE` | MT_SINGLE_TENANT_REFERENCE | measured | tenant topology |

## Data sources

| Layer | Primary use | Source |
|---|---|---|
| Measurement CSV | Quantitative charts and scenario summary metrics | `{"multi-tenancy": "results/experimental-cycles/C6/benchmark/multi-tenancy"}` |
| Technical diagnosis | Interpretation, family judgments, findings, unsupported-scenario context | `results/experimental-cycles/C6/diagnosis/analysis_diagnosis_all_NA_20260619T174725Z_diagnosis.json` |
| Scenario configuration | Fixed/varied dimensions and scenario labels | `config/scenarios/**` |
| Cluster-side artifacts | CPU/memory snapshots, pod placement and event evidence | `minimal observability and cluster capture artifacts` |
| Reporting output | Current generated report package | `results/experimental-cycles/C6/reporting` |

## Infrastructure Summary

| Item | Value |
|---|---|
| Cycle ID | C6 |
| Baseline ID | B1 |
| Infrastructure profile | INFRA_C6_1CP_4W_8C16G |
| Provider | proxmox-k3s |
| Cluster name | genai-pb |
| Kubernetes distribution | K3s |
| K3s version | v1.35.3+k3s1 |
| Control-plane nodes | 1 |
| Worker nodes | 4 |
| Worker total vCPU | 32 |
| Worker total memory | 64 GiB |
| Lifecycle mode | ephemeral |
| Destroy after cycle | True |

## Provider Summary

This campaign may resolve provider configuration at scenario or variant level. The table below exposes provider bindings and concrete configuration paths per scenario whenever available.

All configured scenarios currently resolve to the same provider binding. The provider is therefore reported once to avoid repeating identical configuration metadata.

| Item | Value |
|---|---|
| Covered scenarios | `MT_SINGLE_TENANT_REFERENCE`, `MT_TWO_TENANTS_MIXED_MODELS`, `MT_TWO_TENANTS_SEPARATED`, `MT_TWO_TENANTS_SHARED_NODEPOOL` |
| Provider | proxmox-k3s |
| Provider binding | BINDING_INFRA_C6_1CP_4W_8C16G_PROXMOX_K3S |
| Provider binding path | config/infrastructure/providers/proxmox-k3s/bindings/BINDING_INFRA_C6_1CP_4W_8C16G_PROXMOX_K3S.json |
| Example config | config/infrastructure/providers/proxmox-k3s/examples/cluster.c6-1cp-4w-8c16g.example.yaml |
| Local config | config/infrastructure/providers/proxmox-k3s/local/cluster.c6-1cp-4w-8c16g.local.yaml |
| Kubeconfig | config/cluster-access/generated/proxmox-k3s/c6-1cp-4w-8c16g/kubeconfig |

## Cluster Validation Summary

| Item | Value |
|---|---|
| Validation profile | CV_PROVIDER_BACKED_VALIDATION_TEMPLATE |
| Profile file | config/cluster-validation/templates/CV_PROVIDER_BACKED_VALIDATION_TEMPLATE.json |
| Latest manifest | variant-scoped validation manifests (4 available) |
| Current status | variant-scoped validation available (4/4 validated) |
| Variant validation statuses | validated=4 |
| Latest raw validation | variant-scoped validation evidence is recorded in the campaign execution manifest and generated runtime profiles under results/experimental-cycles/C6/execution/generated-runtime-configs |
| Accepted provisioning statuses | completed |
| Required kubeconfig status | verified |
| Artifact root | results/experimental-cycles/C6/execution/generated-runtime-configs |

## Runtime Profile Variant Summary

This table links each scenario to the runtime-generated profiles used for precheck, application deployment and minimal observability evidence.

| Scenario | Family | Precheck profile | Precheck profile path | Application deployment profile | Application deployment profile path | Minimal observability profile | Minimal observability profile path | Cluster validation evidence |
|---|---|---|---|---|---|---|---|---|
| `MT_SINGLE_TENANT_REFERENCE` | multi-tenancy | TC_C6_MT_SINGLE_TENANT_REFERENCE | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_SINGLE_TENANT_REFERENCE/TC_MT_SINGLE_TENANT_REFERENCE.json | AD_C6_MT_SINGLE_TENANT_REFERENCE | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_SINGLE_TENANT_REFERENCE/AD_MT_SINGLE_TENANT_REFERENCE.json | MO_C6_MT_SINGLE_TENANT_REFERENCE | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_SINGLE_TENANT_REFERENCE/MO_MT_SINGLE_TENANT_REFERENCE.json | results/experimental-cycles/C6/variants/MT_SINGLE_TENANT_REFERENCE/infrastructure/validation/latest-cluster-validation-manifest.json (validated) |
| `MT_TWO_TENANTS_MIXED_MODELS` | multi-tenancy | TC_C6_MT_TWO_TENANTS_MIXED_MODELS | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_TWO_TENANTS_MIXED_MODELS/TC_MT_TWO_TENANTS_MIXED_MODELS.json | AD_C6_MT_TWO_TENANTS_MIXED_MODELS | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_TWO_TENANTS_MIXED_MODELS/AD_MT_TWO_TENANTS_MIXED_MODELS.json | MO_C6_MT_TWO_TENANTS_MIXED_MODELS | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_TWO_TENANTS_MIXED_MODELS/MO_MT_TWO_TENANTS_MIXED_MODELS.json | results/experimental-cycles/C6/variants/MT_TWO_TENANTS_MIXED_MODELS/infrastructure/validation/latest-cluster-validation-manifest.json (validated) |
| `MT_TWO_TENANTS_SEPARATED` | multi-tenancy | TC_C6_MT_TWO_TENANTS_SEPARATED | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_TWO_TENANTS_SEPARATED/TC_MT_TWO_TENANTS_SEPARATED.json | AD_C6_MT_TWO_TENANTS_SEPARATED | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_TWO_TENANTS_SEPARATED/AD_MT_TWO_TENANTS_SEPARATED.json | MO_C6_MT_TWO_TENANTS_SEPARATED | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_TWO_TENANTS_SEPARATED/MO_MT_TWO_TENANTS_SEPARATED.json | results/experimental-cycles/C6/variants/MT_TWO_TENANTS_SEPARATED/infrastructure/validation/latest-cluster-validation-manifest.json (validated) |
| `MT_TWO_TENANTS_SHARED_NODEPOOL` | multi-tenancy | TC_C6_MT_TWO_TENANTS_SHARED_NODEPOOL | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_TWO_TENANTS_SHARED_NODEPOOL/TC_MT_TWO_TENANTS_SHARED_NODEPOOL.json | AD_C6_MT_TWO_TENANTS_SHARED_NODEPOOL | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_TWO_TENANTS_SHARED_NODEPOOL/AD_MT_TWO_TENANTS_SHARED_NODEPOOL.json | MO_C6_MT_TWO_TENANTS_SHARED_NODEPOOL | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_TWO_TENANTS_SHARED_NODEPOOL/MO_MT_TWO_TENANTS_SHARED_NODEPOOL.json | results/experimental-cycles/C6/variants/MT_TWO_TENANTS_SHARED_NODEPOOL/infrastructure/validation/latest-cluster-validation-manifest.json (validated) |

## Application Topology Summary

This campaign may vary placement, tenancy, latency profile or generated deployment profiles at scenario level. The table below exposes the scenario-level application topology used by each configured variant.

| Scenario | Family | Placement profile | Placement type | Topology dir | Server manifest | Worker count | Active RPC workers | Expected server node | Expected worker nodes | Latency profile | Tenancy profile | Generated deployment profile |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `MT_SINGLE_TENANT_REFERENCE` | multi-tenancy | PL_DISTRIBUTED_TWO_NODE | tenant_primary_distributed_two_node | infra/k8s/compositions/tenancy/single-tenant-reference | infra/k8s/compositions/tenancy/single-tenant-reference | 2 | localai-rpc-a, localai-rpc-b | genai-pb-worker-01 | localai-rpc-a=genai-pb-worker-01, localai-rpc-b=genai-pb-worker-02 | not_applicable | TP_SINGLE_TENANT_REFERENCE | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_SINGLE_TENANT_REFERENCE/AD_MT_SINGLE_TENANT_REFERENCE.json |
| `MT_TWO_TENANTS_MIXED_MODELS` | multi-tenancy | PL_DISTRIBUTED_TWO_NODE | tenant_primary_distributed_two_node | infra/k8s/compositions/tenancy/two-tenants-mixed-models | infra/k8s/compositions/tenancy/two-tenants-mixed-models | 2 | localai-rpc-a, localai-rpc-b | genai-pb-worker-01 | localai-rpc-a=genai-pb-worker-01, localai-rpc-b=genai-pb-worker-02 | not_applicable | TP_TWO_TENANTS_MIXED_MODELS | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_TWO_TENANTS_MIXED_MODELS/AD_MT_TWO_TENANTS_MIXED_MODELS.json |
| `MT_TWO_TENANTS_SEPARATED` | multi-tenancy | PL_DISTRIBUTED_TWO_NODE | tenant_primary_distributed_two_node | infra/k8s/compositions/tenancy/two-tenants-separated | infra/k8s/compositions/tenancy/two-tenants-separated | 2 | localai-rpc-a, localai-rpc-b | genai-pb-worker-01 | localai-rpc-a=genai-pb-worker-01, localai-rpc-b=genai-pb-worker-02 | not_applicable | TP_TWO_TENANTS_SEPARATED | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_TWO_TENANTS_SEPARATED/AD_MT_TWO_TENANTS_SEPARATED.json |
| `MT_TWO_TENANTS_SHARED_NODEPOOL` | multi-tenancy | PL_DISTRIBUTED_TWO_NODE | tenant_primary_distributed_two_node | infra/k8s/compositions/tenancy/two-tenants-shared-nodepool | infra/k8s/compositions/tenancy/two-tenants-shared-nodepool | 2 | localai-rpc-a, localai-rpc-b | genai-pb-worker-01 | localai-rpc-a=genai-pb-worker-01, localai-rpc-b=genai-pb-worker-02 | not_applicable | TP_TWO_TENANTS_SHARED_NODEPOOL | results/experimental-cycles/C6/execution/generated-runtime-configs/MT_TWO_TENANTS_SHARED_NODEPOOL/AD_MT_TWO_TENANTS_SHARED_NODEPOOL.json |

## Scenario Summary

The following table summarizes the currently available measurement and constraint evidence for all configured reporting families.

| Family | Scenario | Status | Samples | Mean ms | P95 ms | RPS | Unsupported evidence |
|---|---|---|---|---|---|---|---|
| multi-tenancy | MT_SINGLE_TENANT_REFERENCE | measured | 3 | 1523.58 | 1500.00 | 0.5686 | NA |
| multi-tenancy | MT_TWO_TENANTS_MIXED_MODELS | measured | 3 | 1535.02 | 1600.00 | 0.5669 | NA |
| multi-tenancy | MT_TWO_TENANTS_SEPARATED | measured | 3 | 1532.20 | 1566.67 | 0.5673 | NA |
| multi-tenancy | MT_TWO_TENANTS_SHARED_NODEPOOL | unsupported_under_current_constraints | 0 | NA | NA | NA | application_not_ready,failed_scheduling,insufficient_memory,latency_injection,localai_deployment,no_preemption_victims_found,node_affinity_selector_mismatch,pending_pod,preemption_not_helpful,rollout_timeout |

## Metrics Summary

The reporting generator first uses minimal observability metrics when available; missing values are filled from scenario-summary aggregates derived from benchmark CSV files and cluster-capture artifacts whenever possible. Values marked as `not_available` were not derivable from the available artifact set and are intentionally distinguished from measured zero values.

| Metric | Value | Source |
|---|---|---|
| request_count | 67 | scenario summary aggregation fallback |
| success_rate_percent | 100.0 | scenario summary aggregation fallback |
| failure_count | 0 | scenario summary aggregation fallback |
| mean_response_time_ms | 1530.2675 | scenario summary aggregation fallback |
| p50_response_time_ms | 1500.0 | scenario summary aggregation fallback |
| p95_response_time_ms | 1555.5556 | scenario summary aggregation fallback |
| p99_response_time_ms | 1822.2222 | scenario summary aggregation fallback |
| throughput_rps | 0.5676 | scenario summary aggregation fallback |
| max_node_cpu_percent | 20.8889 | scenario summary aggregation fallback |
| max_node_memory_percent | 16.3333 | scenario summary aggregation fallback |
| max_pod_cpu_millicores | 1455.8889 | scenario summary aggregation fallback |
| max_pod_memory_mib | 592.0 | scenario summary aggregation fallback |
| pod_restart_count | 0 | scenario summary aggregation fallback |
| pending_pods_count | 0 | scenario summary aggregation fallback |
| failed_pods_count | 0 | scenario summary aggregation fallback |
| not_ready_pods_count | 0 | scenario summary aggregation fallback |
| kubernetes_events_count | 24.6667 | scenario summary aggregation fallback |
| kubernetes_warning_events_count | 0 | scenario summary aggregation fallback |

## Unsupported Scenario Summary

| Family | Scenario | Status | Evidence | Source |
|---|---|---|---|---|
| multi-tenancy | MT_TWO_TENANTS_SHARED_NODEPOOL | unsupported_under_current_constraints | application_not_ready, failed_scheduling, insufficient_memory, latency_injection, localai_deployment, no_preemption_victims_found, node_affinity_selector_mismatch, pending_pod, ... (+2) | results/experimental-cycles/C6/benchmark/multi-tenancy/MT_TWO_TENANTS_SHARED_NODEPOOL_official_locked/MT_TWO_TENANTS_SHARED_NODEPOOL_runA_unsupported.json, results/experimental-cycles/C6/benchmark/multi-tenancy/MT_TWO_TENANTS_SHARED_NODEPOOL_official_locked/MT_TWO_TENANTS_SHARED_NODEPOOL_runB_unsupported.json, results/experimental-cycles/C6/benchmark/multi-tenancy/MT_TWO_TENANTS_SHARED_NODEPOOL_official_locked/MT_TWO_TENANTS_SHARED_NODEPOOL_runC_unsupported.json |

## Main Findings

| Family | Finding | Status | Confidence | Implication |
|---|---|---|---|---|
| multi-tenancy | The multi-tenancy family provides comparable tenant-coexistence evidence. | comparative_signal_available | medium | The campaign can be used to reason about tenant-count, model-mix and placement effects because infrastructure and primary benchmark workload remain fixed while tenant topology changes. |
| multi-tenancy | The multi-tenancy campaign provides measured evidence across tenant-topology variants. | NA | medium | The evidence can be used to reason about co-tenant contention and placement effects under fixed infrastructure and primary benchmark workload. |
| multi-tenancy | At least one multi-tenant topology produced unsupported evidence under the current constraints. | NA | medium | Unsupported tenant topologies should be treated as capacity, placement or rollout evidence and not as missing measurements. |
| baseline | Minimum end-to-end validation is available as a functional reliability baseline. | NA | high | The benchmark pipeline starts from a verified functional baseline rather than from a purely theoretical setup. |

## Sweep-specific reports

The global report below provides the stakeholder-facing overview. Each sweep also has a dedicated report for focused inspection of one varied dimension.

| Sweep | Dedicated HTML report | Execution status | Coverage | Varied dimension |
|---|---|---|---|---|
| Multi-Tenancy | [multi-tenancy](sweeps/multi-tenancy/index.html) | partially_measured | measured=3, unsupported=1, missing=0 | tenant topology |

## Diagnosis coverage snapshot

| Family | Scenarios | Observed | Measured | Unsupported | Samples |
|---|---|---|---|---|---|
| multi-tenancy | 4 | 4 | 3 | 1 | 9 |

## Multi-Tenancy

**Execution status:** `partially_measured`

**Execution note:** At least one configured scenario has measured benchmark samples, while other scenarios are missing or unsupported.

**Varied dimension:** tenant topology

**Fixed dimensions:** infrastructure=INFRA_C6_1CP_4W_8C16G, benchmark tenant=tenant-a, primary model=M1, primary worker-count=W2, workload=WL2.

**Reference scenario within the sweep:** `MT_SINGLE_TENANT_REFERENCE`

| Scenario count | Measured | Unsupported | Missing |
|---|---|---|---|
| 4 | 3 | 1 | 0 |

### Controlled scenario parameters

This table is derived from resolved scenario metadata. A parameter is marked as controlled only when it has the same effective value across all scenarios in the sweep.

| Parameter | Resolved value | Interpretation |
|---|---|---|
| Model | varies across scenarios (2 values) | varied or scenario-specific |
| Worker count | 2 | controlled |
| Placement | tenant_primary_distributed_two_node | controlled |
| Workload | users=2, spawnRate=1, runTime=2m | controlled |
| Topology | varies across scenarios (4 values) | varied or scenario-specific |
| Server manifest | varies across scenarios (4 values) | varied or scenario-specific |
| Prompt | Reply with only READY. | controlled |
| Temperature | 0.1 | controlled |
| Request timeout (s) | 120 | controlled |

### Scenario parameter matrix

| Scenario | Status | Varied value (tenant topology) | Model | Worker count | Placement | Workload | Timeout (s) |
|---|---|---|---|---|---|---|---|
| `MT_SINGLE_TENANT_REFERENCE` | measured | single tenant reference | llama-3.2-1b-instruct:q4_k_m | 2 | tenant_primary_distributed_two_node | users=2, spawnRate=1, runTime=2m | 120 |
| `MT_TWO_TENANTS_MIXED_MODELS` | measured | two tenants mixed models | tenant-a=llama-3.2-1b-instruct:q4_k_m; tenant-b=llama-3.2-1b-instruct:q8_0 | 2 | tenant_primary_distributed_two_node | users=2, spawnRate=1, runTime=2m | 120 |
| `MT_TWO_TENANTS_SEPARATED` | measured | two tenants separated | llama-3.2-1b-instruct:q4_k_m | 2 | tenant_primary_distributed_two_node | users=2, spawnRate=1, runTime=2m | 120 |
| `MT_TWO_TENANTS_SHARED_NODEPOOL` | unsupported_under_current_constraints | two tenants shared node pool | tenant-a=llama-3.2-1b-instruct:q4_k_m; tenant-b=llama-3.2-1b-instruct:q8_0 | 2 | tenant_primary_distributed_two_node | users=2, spawnRate=1, runTime=2m | 120 |

### Measurement summary

This compact table reports the core indicators used to read the sweep at a glance. Detailed percentiles, deltas and resource snapshots are reported in the following extended table.

| Scenario | Description | Status | Sample count | Mean response time (ms) | P95 response time (ms) | Throughput (requests/s) | Unsupported evidence |
|---|---|---|---|---|---|---|---|
| `MT_SINGLE_TENANT_REFERENCE` | MT_SINGLE_TENANT_REFERENCE | measured | 3 | 1523.58 | 1500.00 | 0.5686 |  |
| `MT_TWO_TENANTS_MIXED_MODELS` | MT_TWO_TENANTS_MIXED_MODELS | measured | 3 | 1535.02 | 1600.00 | 0.5669 |  |
| `MT_TWO_TENANTS_SEPARATED` | MT_TWO_TENANTS_SEPARATED | measured | 3 | 1532.20 | 1566.67 | 0.5673 |  |
| `MT_TWO_TENANTS_SHARED_NODEPOOL` | MT_TWO_TENANTS_SHARED_NODEPOOL | unsupported_under_current_constraints | 0 | n/a | n/a | n/a | application_not_ready, failed_scheduling, insufficient_memory, latency_injection, localai_deployment, no_preemption_victims_found, node_affinity_selector_mismatch, pending_pod, preemption_not_helpful, rollout_timeout |

### Extended measurement metrics

This secondary table keeps the additional metrics aligned with the technical diagnosis while avoiding an excessively wide primary summary table.

| Scenario | P50 response time (ms) | P99 response time (ms) | Mean response time delta (%) | P95 response time delta (%) | Throughput delta (%) | Max node CPU snapshot (%) | Max node memory snapshot (%) | Max pod CPU snapshot (mCPU) | Max pod memory snapshot (MiB) |
|---|---|---|---|---|---|---|---|---|---|
| `MT_SINGLE_TENANT_REFERENCE` | 1500.00 | 1800.00 | 0.00 | 0.00 | 0.00 | 20.67 | 16.00 | 1427.67 | 592.00 |
| `MT_TWO_TENANTS_MIXED_MODELS` | 1500.00 | 1800.00 | 0.75 | 6.67 | -0.30 | 21.00 | 16.00 | 1428.00 | 592.00 |
| `MT_TWO_TENANTS_SEPARATED` | 1500.00 | 1866.67 | 0.57 | 4.44 | -0.23 | 21.00 | 17.00 | 1512.00 | 592.00 |
| `MT_TWO_TENANTS_SHARED_NODEPOOL` | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Tenant topology context

This table makes the tenant composition explicit. The benchmark target remains the declared primary tenant, while co-tenant clusters expose model-mix, placement and resource-contention context.

| Scenario | Tenant | Namespace | Role | Benchmarked | Model scenario | Model | Worker scenario | Worker count | Placement |
|---|---|---|---|---|---|---|---|---|---|
| `MT_SINGLE_TENANT_REFERENCE` | `tenant-a` | genai-tenant-a | benchmark_tenant | yes | M1 | llama-3.2-1b-instruct:q4_k_m | W2 | 2 | primary_workers_01_02 |
| `MT_TWO_TENANTS_MIXED_MODELS` | `tenant-a` | genai-tenant-a | benchmark_tenant | yes | M1 | llama-3.2-1b-instruct:q4_k_m | W2 | 2 | workers_01_02 |
| `MT_TWO_TENANTS_MIXED_MODELS` | `tenant-b` | genai-tenant-b | co_tenant | no | M2 | llama-3.2-1b-instruct:q8_0 | W2 | 2 | workers_03_04 |
| `MT_TWO_TENANTS_SEPARATED` | `tenant-a` | genai-tenant-a | benchmark_tenant | yes | M1 | llama-3.2-1b-instruct:q4_k_m | W2 | 2 | workers_01_02 |
| `MT_TWO_TENANTS_SEPARATED` | `tenant-b` | genai-tenant-b | co_tenant | no | M1 | llama-3.2-1b-instruct:q4_k_m | W2 | 2 | workers_03_04 |
| `MT_TWO_TENANTS_SHARED_NODEPOOL` | `tenant-a` | genai-tenant-a | benchmark_tenant | yes | M1 | llama-3.2-1b-instruct:q4_k_m | W2 | 2 | workers_01_02 |
| `MT_TWO_TENANTS_SHARED_NODEPOOL` | `tenant-b` | genai-tenant-b | co_tenant | no | M2 | llama-3.2-1b-instruct:q8_0 | W2 | 2 | workers_01_02 |

### Diagnosis-based reading

- **The multi-tenancy family provides comparable tenant-coexistence evidence.** (status: `comparative_signal_available`, confidence: `medium`).
  - Implication: The campaign can be used to reason about tenant-count, model-mix and placement effects because infrastructure and primary benchmark workload remain fixed while tenant topology changes.
- **The multi-tenancy campaign provides measured evidence across tenant-topology variants.** (confidence: `medium`).
  - Implication: The evidence can be used to reason about co-tenant contention and placement effects under fixed infrastructure and primary benchmark workload.
- **At least one multi-tenant topology produced unsupported evidence under the current constraints.** (confidence: `medium`).
  - Implication: Unsupported tenant topologies should be treated as capacity, placement or rollout evidence and not as missing measurements.

### Charts

#### Mean response time

![Mean response time](charts/multi-tenancy/mean_response_time_ms.svg)

#### P50 response time

![P50 response time](charts/multi-tenancy/p50_response_time_ms.svg)

#### P95 response time

![P95 response time](charts/multi-tenancy/p95_response_time_ms.svg)

#### P99 response time

![P99 response time](charts/multi-tenancy/p99_response_time_ms.svg)

#### Throughput

![Throughput](charts/multi-tenancy/throughput_rps.svg)

#### Maximum node CPU snapshot

![Maximum node CPU snapshot](charts/multi-tenancy/max_node_cpu_percent.svg)

#### Maximum node memory snapshot

![Maximum node memory snapshot](charts/multi-tenancy/max_node_memory_percent.svg)

#### Maximum pod CPU snapshot

![Maximum pod CPU snapshot](charts/multi-tenancy/max_pod_cpu_millicores.svg)

#### Maximum pod memory snapshot

![Maximum pod memory snapshot](charts/multi-tenancy/max_pod_memory_mib.svg)

### Reading notes

- Measured scenarios: **3**.
- Unsupported scenarios under current constraints: **1**.
- Percentage deltas are computed against the family reference scenario; positive latency deltas indicate worse response time, while positive throughput deltas indicate higher request throughput.
- Unsupported scenarios are infrastructure/constraint observations and must not be interpreted as measured latency regressions.
- A `not_executed` sweep means that neither measurement CSV files nor unsupported-scenario evidence were found for any configured scenario in that family.

> The primary benchmark target remains tenant-a in namespace genai-tenant-a.
> Co-tenant clusters are deployed to model resource contention and tenant coexistence, while benchmark traffic remains intentionally controlled.
> Unsupported multi-tenant topologies are retained as capacity or placement evidence.
