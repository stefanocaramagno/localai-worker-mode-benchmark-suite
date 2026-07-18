# C2 — Resource Variation Sweep Report

**Cycle ID:** `C2`
**Sweep:** `resource-variation`
**Reporting Profile:** `RP_C2_RESOURCE_VARIATION`
**Reporting ID:** `REP_C2_20260619T174611Z`
**Generated at UTC:** `2026-06-19T17:46:38Z`

[Back to cycle report](../../index.html)

## Scope

This sweep-specific report isolates **Resource Variation** so that the varied dimension, fixed dimensions, measured values, unsupported evidence and diagnosis-based reading can be inspected without navigating the full consolidated report.

## Resource Variation

**Execution status:** `partially_measured`

**Execution note:** At least one configured scenario has measured benchmark samples, while other scenarios are missing or unsupported.

**Varied dimension:** worker CPU and memory capacity

**Fixed dimensions:** model=M1, workload=WL2, LocalAI worker count=W2, placement=PL_COLOCATED, request payload.

**Reference scenario within the sweep:** `RV_8C16G`

| Scenario count | Measured | Unsupported | Missing |
|---|---|---|---|
| 3 | 1 | 2 | 0 |

### Controlled scenario parameters

This table is derived from resolved scenario metadata. A parameter is marked as controlled only when it has the same effective value across all scenarios in the sweep.

| Parameter | Resolved value | Interpretation |
|---|---|---|
| Model | llama-3.2-1b-instruct:q4_k_m | controlled |
| Worker count | 2 | controlled |
| Placement | colocated_genai_pb_worker_02 | controlled |
| Workload | users=2, spawnRate=1, runTime=2m | controlled |
| Topology | infra/k8s/compositions/topology/colocated-genai-pb-worker-02-w2 | controlled |
| Server manifest | infra/k8s/compositions/server/models/m1-provider-backed | controlled |
| Prompt | Reply with only READY. | controlled |
| Temperature | 0.1 | controlled |
| Request timeout (s) | 120 | controlled |

### Scenario parameter matrix

| Scenario | Status | Varied value (worker CPU and memory capacity) | Model | Worker count | Placement | Workload | Timeout (s) |
|---|---|---|---|---|---|---|---|
| `RV_4C16G` | unsupported_under_current_constraints | 4 vCPU / 16 GiB per worker | llama-3.2-1b-instruct:q4_k_m | 2 | colocated_genai_pb_worker_02 | users=2, spawnRate=1, runTime=2m | 120 |
| `RV_4C8G` | unsupported_under_current_constraints | 4 vCPU / 8 GiB per worker | llama-3.2-1b-instruct:q4_k_m | 2 | colocated_genai_pb_worker_02 | users=2, spawnRate=1, runTime=2m | 120 |
| `RV_8C16G` | measured | 8 vCPU / 16 GiB per worker | llama-3.2-1b-instruct:q4_k_m | 2 | colocated_genai_pb_worker_02 | users=2, spawnRate=1, runTime=2m | 120 |

### Measurement summary

This compact table reports the core indicators used to read the sweep at a glance. Detailed percentiles, deltas and resource snapshots are reported in the following extended table.

| Scenario | Description | Status | Sample count | Mean response time (ms) | P95 response time (ms) | Throughput (requests/s) | Unsupported evidence |
|---|---|---|---|---|---|---|---|
| `RV_4C16G` | RV_4C16G (4 vCPU / 16 GiB per worker) | unsupported_under_current_constraints | 0 | n/a | n/a | n/a | application_not_ready, failed_scheduling, insufficient_cpu, latency_injection, localai_deployment, no_preemption_victims_found, node_affinity_selector_mismatch, pending_pod, preemption_not_helpful, rollout_timeout |
| `RV_4C8G` | RV_4C8G (4 vCPU / 8 GiB per worker) | unsupported_under_current_constraints | 0 | n/a | n/a | n/a | application_not_ready, failed_scheduling, insufficient_memory, latency_injection, localai_deployment, no_preemption_victims_found, node_affinity_selector_mismatch, pending_pod, preemption_not_helpful, rollout_timeout |
| `RV_8C16G` | RV_8C16G (8 vCPU / 16 GiB per worker) | measured | 3 | 1503.11 | 1500.00 | 0.5728 |  |

### Extended measurement metrics

This secondary table keeps the additional metrics aligned with the technical diagnosis while avoiding an excessively wide primary summary table.

| Scenario | P50 response time (ms) | P99 response time (ms) | Mean response time delta (%) | P95 response time delta (%) | Throughput delta (%) | Max node CPU snapshot (%) | Max node memory snapshot (%) | Max pod CPU snapshot (mCPU) | Max pod memory snapshot (MiB) |
|---|---|---|---|---|---|---|---|---|---|
| `RV_4C16G` | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| `RV_4C8G` | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| `RV_8C16G` | 1500.00 | 1700.00 | 0.00 | 0.00 | 0.00 | 34.00 | 15.67 | 1447.33 | 592.00 |

### Resource-capacity context

This table makes the resource-capacity dimension explicit. Model, workload, LocalAI worker count and placement are kept fixed while worker-node CPU and memory capacity change; unsupported variants are reported in the same context to preserve capacity-boundary evidence without introducing a separate asymmetric section.

| Scenario | Worker nodes | Worker-node shape | Total worker CPU | Total worker memory | Reference shape | Execution status | Unsupported reason |
|---|---|---|---|---|---|---|---|
| `RV_4C16G` | 2 | 4 vCPU / 16 GiB | 8 vCPU | 32 GiB | no | unsupported_under_current_constraints | localai_deployment_not_ready, localai_deployment_not_ready, localai_deployment_not_ready |
| `RV_4C8G` | 2 | 4 vCPU / 8 GiB | 8 vCPU | 16 GiB | no | unsupported_under_current_constraints | localai_deployment_not_ready, localai_deployment_not_ready, localai_deployment_not_ready |
| `RV_8C16G` | 2 | 8 vCPU / 16 GiB | 16 vCPU | 32 GiB | yes | measured | none |

### Diagnosis-based reading

- **The resource-variation family provides deployability-boundary evidence, but not yet a full latency/throughput comparison.** (status: `capacity_boundary_signal_available`, confidence: `medium`).
  - Implication: At least two measured resource shapes are still required for a robust performance comparison; however, the campaign already identifies which lower resource shapes cannot host the fixed LocalAI topology under the current constraints.
- **The resource-variation campaign identifies a deployability boundary under fixed application-level conditions.** (confidence: `high`).
  - Implication: The campaign should be read as capacity-feasibility evidence: lower worker-node shapes are not benchmark-ready under the fixed co-located topology and current LocalAI resource requests, while the reference shape is measurable.
- **Unsupported resource-variation variants expose Kubernetes scheduler resource constraints.** (confidence: `high`).
  - Implication: The unsupported variants provide concrete evidence about CPU and memory feasibility limits and should not be treated as ordinary benchmark failures.

### Charts

#### Mean response time

![Mean response time](../../charts/resource-variation/mean_response_time_ms.svg)

#### P50 response time

![P50 response time](../../charts/resource-variation/p50_response_time_ms.svg)

#### P95 response time

![P95 response time](../../charts/resource-variation/p95_response_time_ms.svg)

#### P99 response time

![P99 response time](../../charts/resource-variation/p99_response_time_ms.svg)

#### Throughput

![Throughput](../../charts/resource-variation/throughput_rps.svg)

#### Maximum node CPU snapshot

![Maximum node CPU snapshot](../../charts/resource-variation/max_node_cpu_percent.svg)

#### Maximum node memory snapshot

![Maximum node memory snapshot](../../charts/resource-variation/max_node_memory_percent.svg)

#### Maximum pod CPU snapshot

![Maximum pod CPU snapshot](../../charts/resource-variation/max_pod_cpu_millicores.svg)

#### Maximum pod memory snapshot

![Maximum pod memory snapshot](../../charts/resource-variation/max_pod_memory_mib.svg)

### Reading notes

- Measured scenarios: **1**.
- Unsupported scenarios under current constraints: **2**.
- Percentage deltas are computed against the family reference scenario; positive latency deltas indicate worse response time, while positive throughput deltas indicate higher request throughput.
- Unsupported scenarios are infrastructure/constraint observations and must not be interpreted as measured latency regressions.
- A `not_executed` sweep means that neither measurement CSV files nor unsupported-scenario evidence were found for any configured scenario in that family.
