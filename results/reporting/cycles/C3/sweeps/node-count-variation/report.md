# C3 — Node-Count Variation Sweep Report

**Cycle ID:** `C3`
**Sweep:** `node-count-variation`
**Reporting Profile:** `RP_C3_NODE_COUNT_VARIATION`
**Reporting ID:** `REP_C3_20260619T174611Z`
**Generated at UTC:** `2026-06-19T17:46:44Z`

[Back to cycle report](../../index.html)

## Scope

This sweep-specific report isolates **Node-Count Variation** so that the varied dimension, fixed dimensions, measured values, unsupported evidence and diagnosis-based reading can be inspected without navigating the full consolidated report.

## Node-Count Variation

**Execution status:** `fully_measured`

**Execution note:** All configured scenarios in this sweep have measured benchmark samples.

**Varied dimension:** provider worker node count

**Fixed dimensions:** model=M1, LocalAI worker-count=W4, placement=PL_SPREAD_WORKERS, workload=WL2, worker node capacity=8 vCPU / 16 GiB.

**Reference scenario within the sweep:** `NC_2N`

| Scenario count | Measured | Unsupported | Missing |
|---|---|---|---|
| 3 | 3 | 0 | 0 |

### Controlled scenario parameters

This table is derived from resolved scenario metadata. A parameter is marked as controlled only when it has the same effective value across all scenarios in the sweep.

| Parameter | Resolved value | Interpretation |
|---|---|---|
| Model | llama-3.2-1b-instruct:q4_k_m | controlled |
| Worker count | 4 | controlled |
| Placement | varies across scenarios (3 values) | varied or scenario-specific |
| Workload | users=2, spawnRate=1, runTime=2m | controlled |
| Topology | varies across scenarios (3 values) | varied or scenario-specific |
| Server manifest | infra/k8s/compositions/server/models/m1-provider-backed | controlled |
| Prompt | Reply with only READY. | controlled |
| Temperature | 0.1 | controlled |
| Request timeout (s) | 120 | controlled |

### Scenario parameter matrix

| Scenario | Status | Varied value (provider worker node count) | Model | Worker count | Placement | Workload | Timeout (s) |
|---|---|---|---|---|---|---|---|
| `NC_2N` | measured | 2 provider worker nodes / W4 | llama-3.2-1b-instruct:q4_k_m | 4 | spread_workers_across_2_provider_worker_nodes | users=2, spawnRate=1, runTime=2m | 120 |
| `NC_3N` | measured | 3 provider worker nodes / W4 | llama-3.2-1b-instruct:q4_k_m | 4 | spread_workers_across_3_provider_worker_nodes | users=2, spawnRate=1, runTime=2m | 120 |
| `NC_4N` | measured | 4 provider worker nodes / W4 | llama-3.2-1b-instruct:q4_k_m | 4 | spread_workers_across_4_provider_worker_nodes | users=2, spawnRate=1, runTime=2m | 120 |

### Measurement summary

This compact table reports the core indicators used to read the sweep at a glance. Detailed percentiles, deltas and resource snapshots are reported in the following extended table.

| Scenario | Description | Status | Sample count | Mean response time (ms) | P95 response time (ms) | Throughput (requests/s) | Unsupported evidence |
|---|---|---|---|---|---|---|---|
| `NC_2N` | NC_2N (2 provider worker nodes / W4) | measured | 3 | 1528.61 | 1600.00 | 0.5677 |  |
| `NC_3N` | NC_3N (3 provider worker nodes / W4) | measured | 3 | 1542.26 | 1633.33 | 0.5655 |  |
| `NC_4N` | NC_4N (4 provider worker nodes / W4) | measured | 3 | 1576.54 | 1633.33 | 0.5611 |  |

### Extended measurement metrics

This secondary table keeps the additional metrics aligned with the technical diagnosis while avoiding an excessively wide primary summary table.

| Scenario | P50 response time (ms) | P99 response time (ms) | Mean response time delta (%) | P95 response time delta (%) | Throughput delta (%) | Max node CPU snapshot (%) | Max node memory snapshot (%) | Max pod CPU snapshot (mCPU) | Max pod memory snapshot (MiB) |
|---|---|---|---|---|---|---|---|---|---|
| `NC_2N` | 1500.00 | 1800.00 | 0.00 | 0.00 | 0.00 | 18.00 | 16.00 | 819.67 | 384.00 |
| `NC_3N` | 1500.00 | 1800.00 | 0.89 | 2.08 | -0.39 | 15.33 | 16.00 | 861.67 | 385.00 |
| `NC_4N` | 1533.33 | 2433.33 | 3.13 | 2.08 | -1.16 | 10.00 | 16.67 | 824.00 | 384.67 |

### Node-count context

This table makes the infrastructure dimension explicit. The LocalAI worker count, per-node capacity and placement policy are kept fixed while the number of provider worker nodes changes.

| Scenario | Provider worker nodes | LocalAI RPC workers | Per-node capacity | Topology | Observed placement nodes |
|---|---|---|---|---|---|
| `NC_2N` | 2 | 4 | 8 vCPU / 16 GiB | infra/k8s/compositions/topology/spread-genai-pb-2-worker-nodes-w4 | genai-pb-worker-01, genai-pb-worker-02 |
| `NC_3N` | 3 | 4 | 8 vCPU / 16 GiB | infra/k8s/compositions/topology/spread-genai-pb-3-worker-nodes-w4 | genai-pb-worker-01, genai-pb-worker-02, genai-pb-worker-03 |
| `NC_4N` | 4 | 4 | 8 vCPU / 16 GiB | infra/k8s/compositions/topology/spread-genai-pb-4-worker-nodes-w4 | genai-pb-worker-01, genai-pb-worker-02, genai-pb-worker-03, genai-pb-worker-04 |

### Diagnosis-based reading

- **The node-count variation family provides comparable infrastructure-size evidence.** (status: `comparative_signal_available`, confidence: `medium`).
  - Implication: The campaign can be used to reason about whether adding provider worker nodes improves distribution and performance, or introduces overhead, while per-node capacity and application-level dimensions remain fixed.
- **The node-count campaign provides measured evidence across multiple infrastructure sizes.** (confidence: `medium`).
  - Implication: The evidence can be used to evaluate whether additional provider worker nodes reduce LocalAI contention, introduce communication overhead, or remain unused by the fixed application topology.
- **The node-count campaign identifies the lowest-latency infrastructure worker-node count among measured variants.** (confidence: `medium`).
  - Implication: This result provides a controlled signal for the node-count dimension under fixed model, workload, LocalAI worker count, per-node resources and placement policy.

### Charts

#### Mean response time

![Mean response time](../../charts/node-count-variation/mean_response_time_ms.svg)

#### P50 response time

![P50 response time](../../charts/node-count-variation/p50_response_time_ms.svg)

#### P95 response time

![P95 response time](../../charts/node-count-variation/p95_response_time_ms.svg)

#### P99 response time

![P99 response time](../../charts/node-count-variation/p99_response_time_ms.svg)

#### Throughput

![Throughput](../../charts/node-count-variation/throughput_rps.svg)

#### Maximum node CPU snapshot

![Maximum node CPU snapshot](../../charts/node-count-variation/max_node_cpu_percent.svg)

#### Maximum node memory snapshot

![Maximum node memory snapshot](../../charts/node-count-variation/max_node_memory_percent.svg)

#### Maximum pod CPU snapshot

![Maximum pod CPU snapshot](../../charts/node-count-variation/max_pod_cpu_millicores.svg)

#### Maximum pod memory snapshot

![Maximum pod memory snapshot](../../charts/node-count-variation/max_pod_memory_mib.svg)

### Reading notes

- Measured scenarios: **3**.
- Unsupported scenarios under current constraints: **0**.
- Percentage deltas are computed against the family reference scenario; positive latency deltas indicate worse response time, while positive throughput deltas indicate higher request throughput.
- Unsupported scenarios are infrastructure/constraint observations and must not be interpreted as measured latency regressions.
- A `not_executed` sweep means that neither measurement CSV files nor unsupported-scenario evidence were found for any configured scenario in that family.
