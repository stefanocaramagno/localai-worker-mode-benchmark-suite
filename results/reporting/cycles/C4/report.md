# C4 — Placement Variation Report

**Cycle ID:** `C4`
**Reporting Profile:** `RP_C4_PLACEMENT_VARIATION`
**Reporting ID:** `REP_C4_20260619T174611Z`
**Generated at UTC:** `2026-06-19T17:46:54Z`

## Purpose

This report compares LocalAI server/RPC-worker placement variants under fixed provider-backed infrastructure, model, workload and LocalAI worker count. It is intended to expose the trade-off between communication distance and CPU/memory contention.

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
| Placement Variation | `PLC_SPREAD_WORKERS` | PLC_SPREAD_WORKERS (spread workers) | measured | placement profile |

## Data sources

| Layer | Primary use | Source |
|---|---|---|
| Measurement CSV | Quantitative charts and scenario summary metrics | `{"placement-variation": "results/experimental-cycles/C4/benchmark/placement-variation"}` |
| Technical diagnosis | Interpretation, family judgments, findings, unsupported-scenario context | `results/experimental-cycles/C4/diagnosis/analysis_diagnosis_all_NA_20260619T174654Z_diagnosis.json` |
| Scenario configuration | Fixed/varied dimensions and scenario labels | `config/scenarios/**` |
| Cluster-side artifacts | CPU/memory snapshots, pod placement and event evidence | `minimal observability and cluster capture artifacts` |
| Reporting output | Current generated report package | `results/experimental-cycles/C4/reporting` |

## Infrastructure Summary

| Item | Value |
|---|---|
| Cycle ID | C4 |
| Baseline ID | B1 |
| Infrastructure profile | INFRA_C4_1CP_4W_8C16G |
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
| Covered scenarios | `PLC_BALANCED_STATIC`, `PLC_COLOCATED`, `PLC_DISTRIBUTED_TWO_NODE`, `PLC_SERVER_SEPARATED`, `PLC_SPREAD_WORKERS` |
| Provider | proxmox-k3s |
| Provider binding | BINDING_INFRA_C4_1CP_4W_8C16G_PROXMOX_K3S |
| Provider binding path | config/infrastructure/providers/proxmox-k3s/bindings/BINDING_INFRA_C4_1CP_4W_8C16G_PROXMOX_K3S.json |
| Example config | config/infrastructure/providers/proxmox-k3s/examples/cluster.c4-1cp-4w-8c16g.example.yaml |
| Local config | config/infrastructure/providers/proxmox-k3s/local/cluster.c4-1cp-4w-8c16g.local.yaml |
| Kubeconfig | config/cluster-access/generated/proxmox-k3s/c4-1cp-4w-8c16g/kubeconfig |

## Cluster Validation Summary

| Item | Value |
|---|---|
| Validation profile | CV_PROVIDER_BACKED_VALIDATION_TEMPLATE |
| Profile file | config/cluster-validation/templates/CV_PROVIDER_BACKED_VALIDATION_TEMPLATE.json |
| Latest manifest | variant-scoped validation manifests (5 available) |
| Current status | variant-scoped validation available (5/5 validated) |
| Variant validation statuses | validated=5 |
| Latest raw validation | variant-scoped validation evidence is recorded in the campaign execution manifest and generated runtime profiles under results/experimental-cycles/C4/execution/generated-runtime-configs |
| Accepted provisioning statuses | completed |
| Required kubeconfig status | verified |
| Artifact root | results/experimental-cycles/C4/execution/generated-runtime-configs |

## Runtime Profile Variant Summary

This table links each scenario to the runtime-generated profiles used for precheck, application deployment and minimal observability evidence.

| Scenario | Family | Precheck profile | Precheck profile path | Application deployment profile | Application deployment profile path | Minimal observability profile | Minimal observability profile path | Cluster validation evidence |
|---|---|---|---|---|---|---|---|---|
| `PLC_BALANCED_STATIC` | placement-variation | TC_C4_PLC_BALANCED_STATIC | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_BALANCED_STATIC/TC_PLC_BALANCED_STATIC.json | AD_C4_PLC_BALANCED_STATIC | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_BALANCED_STATIC/AD_PLC_BALANCED_STATIC.json | MO_C4_PLC_BALANCED_STATIC | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_BALANCED_STATIC/MO_PLC_BALANCED_STATIC.json | results/experimental-cycles/C4/variants/PLC_BALANCED_STATIC/infrastructure/validation/latest-cluster-validation-manifest.json (validated) |
| `PLC_COLOCATED` | placement-variation | TC_C4_PLC_COLOCATED | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_COLOCATED/TC_PLC_COLOCATED.json | AD_C4_PLC_COLOCATED | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_COLOCATED/AD_PLC_COLOCATED.json | MO_C4_PLC_COLOCATED | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_COLOCATED/MO_PLC_COLOCATED.json | results/experimental-cycles/C4/variants/PLC_COLOCATED/infrastructure/validation/latest-cluster-validation-manifest.json (validated) |
| `PLC_DISTRIBUTED_TWO_NODE` | placement-variation | TC_C4_PLC_DISTRIBUTED_TWO_NODE | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_DISTRIBUTED_TWO_NODE/TC_PLC_DISTRIBUTED_TWO_NODE.json | AD_C4_PLC_DISTRIBUTED_TWO_NODE | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_DISTRIBUTED_TWO_NODE/AD_PLC_DISTRIBUTED_TWO_NODE.json | MO_C4_PLC_DISTRIBUTED_TWO_NODE | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_DISTRIBUTED_TWO_NODE/MO_PLC_DISTRIBUTED_TWO_NODE.json | results/experimental-cycles/C4/variants/PLC_DISTRIBUTED_TWO_NODE/infrastructure/validation/latest-cluster-validation-manifest.json (validated) |
| `PLC_SERVER_SEPARATED` | placement-variation | TC_C4_PLC_SERVER_SEPARATED | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_SERVER_SEPARATED/TC_PLC_SERVER_SEPARATED.json | AD_C4_PLC_SERVER_SEPARATED | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_SERVER_SEPARATED/AD_PLC_SERVER_SEPARATED.json | MO_C4_PLC_SERVER_SEPARATED | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_SERVER_SEPARATED/MO_PLC_SERVER_SEPARATED.json | results/experimental-cycles/C4/variants/PLC_SERVER_SEPARATED/infrastructure/validation/latest-cluster-validation-manifest.json (validated) |
| `PLC_SPREAD_WORKERS` | placement-variation | TC_C4_PLC_SPREAD_WORKERS | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_SPREAD_WORKERS/TC_PLC_SPREAD_WORKERS.json | AD_C4_PLC_SPREAD_WORKERS | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_SPREAD_WORKERS/AD_PLC_SPREAD_WORKERS.json | MO_C4_PLC_SPREAD_WORKERS | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_SPREAD_WORKERS/MO_PLC_SPREAD_WORKERS.json | results/experimental-cycles/C4/variants/PLC_SPREAD_WORKERS/infrastructure/validation/latest-cluster-validation-manifest.json (validated) |

## Application Topology Summary

This campaign may vary placement, tenancy, latency profile or generated deployment profiles at scenario level. The table below exposes the scenario-level application topology used by each configured variant.

| Scenario | Family | Placement profile | Placement type | Topology dir | Server manifest | Worker count | Active RPC workers | Expected server node | Expected worker nodes | Latency profile | Tenancy profile | Generated deployment profile |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `PLC_BALANCED_STATIC` | placement-variation | PL_BALANCED_STATIC | balanced_static_server_with_partial_worker_colocation | infra/k8s/compositions/topology/balanced-static-genai-pb-w4 | infra/k8s/compositions/server/models/m1-provider-backed | 4 | localai-rpc-a, localai-rpc-b, localai-rpc-c, localai-rpc-d | genai-pb-worker-02 | localai-rpc-a=genai-pb-worker-01, localai-rpc-b=genai-pb-worker-02, localai-rpc-c=genai-pb-worker-03, localai-rpc-d=genai-pb-worker-02 | not_applicable | not_declared | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_BALANCED_STATIC/AD_PLC_BALANCED_STATIC.json |
| `PLC_COLOCATED` | placement-variation | PL_COLOCATED | colocated_server_and_workers_on_genai_pb_worker_02 | infra/k8s/compositions/topology/colocated-genai-pb-worker-02-w4 | infra/k8s/compositions/server/models/m1-provider-backed | 4 | localai-rpc-a, localai-rpc-b, localai-rpc-c, localai-rpc-d | genai-pb-worker-02 | localai-rpc-a=genai-pb-worker-02, localai-rpc-b=genai-pb-worker-02, localai-rpc-c=genai-pb-worker-02, localai-rpc-d=genai-pb-worker-02 | not_applicable | not_declared | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_COLOCATED/AD_PLC_COLOCATED.json |
| `PLC_DISTRIBUTED_TWO_NODE` | placement-variation | PL_DISTRIBUTED_TWO_NODE | distributed_workers_across_two_provider_worker_nodes | infra/k8s/compositions/topology/distributed-genai-pb-two-node-w4 | infra/k8s/compositions/server/models/m1-provider-backed | 4 | localai-rpc-a, localai-rpc-b, localai-rpc-c, localai-rpc-d | genai-pb-worker-02 | localai-rpc-a=genai-pb-worker-01, localai-rpc-b=genai-pb-worker-02, localai-rpc-c=genai-pb-worker-01, localai-rpc-d=genai-pb-worker-02 | not_applicable | not_declared | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_DISTRIBUTED_TWO_NODE/AD_PLC_DISTRIBUTED_TWO_NODE.json |
| `PLC_SERVER_SEPARATED` | placement-variation | PL_SERVER_SEPARATED | server_separated_from_spread_workers | infra/k8s/compositions/topology/server-separated-genai-pb-worker-01-spread-w4 | infra/k8s/compositions/server/models/m1-provider-backed-worker-01 | 4 | localai-rpc-a, localai-rpc-b, localai-rpc-c, localai-rpc-d | genai-pb-worker-01 | localai-rpc-a=genai-pb-worker-02, localai-rpc-b=genai-pb-worker-03, localai-rpc-c=genai-pb-worker-04, localai-rpc-d=genai-pb-worker-02 | not_applicable | not_declared | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_SERVER_SEPARATED/AD_PLC_SERVER_SEPARATED.json |
| `PLC_SPREAD_WORKERS` | placement-variation | PL_SPREAD_WORKERS | spread_workers_across_four_provider_worker_nodes | infra/k8s/compositions/topology/spread-genai-pb-4-worker-nodes-w4 | infra/k8s/compositions/server/models/m1-provider-backed | 4 | localai-rpc-a, localai-rpc-b, localai-rpc-c, localai-rpc-d | genai-pb-worker-02 | localai-rpc-a=genai-pb-worker-01, localai-rpc-b=genai-pb-worker-02, localai-rpc-c=genai-pb-worker-03, localai-rpc-d=genai-pb-worker-04 | not_applicable | not_declared | results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_SPREAD_WORKERS/AD_PLC_SPREAD_WORKERS.json |

## Scenario Summary

The following table summarizes the currently available measurement and constraint evidence for all configured reporting families.

| Family | Scenario | Status | Samples | Mean ms | P95 ms | RPS | Unsupported evidence |
|---|---|---|---|---|---|---|---|
| placement-variation | PLC_BALANCED_STATIC | measured | 3 | 1535.15 | 1600.00 | 0.5666 | NA |
| placement-variation | PLC_COLOCATED | unsupported_under_current_constraints | 0 | NA | NA | NA | benchmark_precheck,cluster_nodes_ready,metrics_api_and_capacity,namespace_active,namespace_pods_healthy,none_or_within_strict_threshold,pending_pod,service_endpoint_and_model,worker_nodes_expected |
| placement-variation | PLC_DISTRIBUTED_TWO_NODE | measured | 3 | 1530.12 | 1600.00 | 0.5676 | NA |
| placement-variation | PLC_SERVER_SEPARATED | measured | 3 | 1568.79 | 1600.00 | 0.5623 | NA |
| placement-variation | PLC_SPREAD_WORKERS | measured | 3 | 1570.03 | 1733.33 | 0.5619 | NA |

## Metrics Summary

The reporting generator first uses minimal observability metrics when available; missing values are filled from scenario-summary aggregates derived from benchmark CSV files and cluster-capture artifacts whenever possible. Values marked as `not_available` were not derivable from the available artifact set and are intentionally distinguished from measured zero values.

| Metric | Value | Source |
|---|---|---|
| request_count | 66.5833 | scenario summary aggregation fallback |
| success_rate_percent | 100.0 | scenario summary aggregation fallback |
| failure_count | 0 | scenario summary aggregation fallback |
| mean_response_time_ms | 1551.0229 | scenario summary aggregation fallback |
| p50_response_time_ms | 1533.3333 | scenario summary aggregation fallback |
| p95_response_time_ms | 1633.3333 | scenario summary aggregation fallback |
| p99_response_time_ms | 1883.3333 | scenario summary aggregation fallback |
| throughput_rps | 0.5646 | scenario summary aggregation fallback |
| max_node_cpu_percent | 14.9167 | scenario summary aggregation fallback |
| max_node_memory_percent | 15.9167 | scenario summary aggregation fallback |
| max_pod_cpu_millicores | 809.0833 | scenario summary aggregation fallback |
| max_pod_memory_mib | 384.1667 | scenario summary aggregation fallback |
| pod_restart_count | 0 | scenario summary aggregation fallback |
| pending_pods_count | 0 | scenario summary aggregation fallback |
| failed_pods_count | 0 | scenario summary aggregation fallback |
| not_ready_pods_count | 0 | scenario summary aggregation fallback |
| kubernetes_events_count | 38.5 | scenario summary aggregation fallback |
| kubernetes_warning_events_count | 0 | scenario summary aggregation fallback |

## Unsupported Scenario Summary

| Family | Scenario | Status | Evidence | Source |
|---|---|---|---|---|
| placement-variation | PLC_COLOCATED | unsupported_under_current_constraints | benchmark_precheck, cluster_nodes_ready, metrics_api_and_capacity, namespace_active, namespace_pods_healthy, none_or_within_strict_threshold, pending_pod, service_endpoint_and_model, ... (+1) | results/experimental-cycles/C4/benchmark/placement-variation/PLC_COLOCATED_official_locked/PLC_COLOCATED_runA_unsupported.json, results/experimental-cycles/C4/benchmark/placement-variation/PLC_COLOCATED_official_locked/PLC_COLOCATED_runB_unsupported.json, results/experimental-cycles/C4/benchmark/placement-variation/PLC_COLOCATED_official_locked/PLC_COLOCATED_runC_unsupported.json |

## Main Findings

| Family | Finding | Status | Confidence | Implication |
|---|---|---|---|---|
| placement-variation | The placement variation family provides comparable placement evidence. | comparative_signal_available | medium | The campaign can be used to reason about the communication-vs-contention trade-off because infrastructure, model, workload and LocalAI worker count remain fixed while only placement changes. |
| placement-variation | The placement campaign provides measured evidence across multiple placement policies. | NA | medium | The evidence can be used to evaluate whether communication-distance reduction or resource-contention reduction dominates under the fixed infrastructure and workload. |
| placement-variation | The placement campaign identifies the lowest-latency placement among measured variants. | NA | medium | This result provides a controlled signal for placement selection under fixed infrastructure, model, workload and LocalAI worker count. |
| baseline | Minimum end-to-end validation is available as a functional reliability baseline. | NA | high | The benchmark pipeline starts from a verified functional baseline rather than from a purely theoretical setup. |

## Sweep-specific reports

The global report below provides the stakeholder-facing overview. Each sweep also has a dedicated report for focused inspection of one varied dimension.

| Sweep | Dedicated HTML report | Execution status | Coverage | Varied dimension |
|---|---|---|---|---|
| Placement Variation | [placement-variation](sweeps/placement-variation/index.html) | partially_measured | measured=4, unsupported=1, missing=0 | placement profile |

## Diagnosis coverage snapshot

| Family | Scenarios | Observed | Measured | Unsupported | Samples |
|---|---|---|---|---|---|
| placement-variation | 5 | 5 | 4 | 1 | 12 |

## Placement Variation

**Execution status:** `partially_measured`

**Execution note:** At least one configured scenario has measured benchmark samples, while other scenarios are missing or unsupported.

**Varied dimension:** placement profile

**Fixed dimensions:** infrastructure=INFRA_C4_1CP_4W_8C16G, model=M1, LocalAI worker-count=W4, workload=WL2, worker node capacity=8 vCPU / 16 GiB.

**Reference scenario within the sweep:** `PLC_SPREAD_WORKERS`

| Scenario count | Measured | Unsupported | Missing |
|---|---|---|---|
| 5 | 4 | 1 | 0 |

### Controlled scenario parameters

This table is derived from resolved scenario metadata. A parameter is marked as controlled only when it has the same effective value across all scenarios in the sweep.

| Parameter | Resolved value | Interpretation |
|---|---|---|
| Model | llama-3.2-1b-instruct:q4_k_m | controlled |
| Worker count | 4 | controlled |
| Placement | varies across scenarios (5 values) | varied or scenario-specific |
| Workload | users=2, spawnRate=1, runTime=2m | controlled |
| Topology | varies across scenarios (5 values) | varied or scenario-specific |
| Server manifest | varies across scenarios (2 values) | varied or scenario-specific |
| Prompt | Reply with only READY. | controlled |
| Temperature | 0.1 | controlled |
| Request timeout (s) | 120 | controlled |

### Scenario parameter matrix

| Scenario | Status | Varied value (placement profile) | Model | Worker count | Placement | Workload | Timeout (s) |
|---|---|---|---|---|---|---|---|
| `PLC_BALANCED_STATIC` | measured | balanced static | llama-3.2-1b-instruct:q4_k_m | 4 | balanced_static_server_with_partial_worker_colocation | users=2, spawnRate=1, runTime=2m | 120 |
| `PLC_COLOCATED` | unsupported_under_current_constraints | co-located | llama-3.2-1b-instruct:q4_k_m | 4 | colocated_server_and_workers_on_genai_pb_worker_02 | users=2, spawnRate=1, runTime=2m | 120 |
| `PLC_DISTRIBUTED_TWO_NODE` | measured | distributed two-node | llama-3.2-1b-instruct:q4_k_m | 4 | distributed_workers_across_two_provider_worker_nodes | users=2, spawnRate=1, runTime=2m | 120 |
| `PLC_SERVER_SEPARATED` | measured | server separated | llama-3.2-1b-instruct:q4_k_m | 4 | server_separated_from_spread_workers | users=2, spawnRate=1, runTime=2m | 120 |
| `PLC_SPREAD_WORKERS` | measured | spread workers | llama-3.2-1b-instruct:q4_k_m | 4 | spread_workers_across_four_provider_worker_nodes | users=2, spawnRate=1, runTime=2m | 120 |

### Measurement summary

This compact table reports the core indicators used to read the sweep at a glance. Detailed percentiles, deltas and resource snapshots are reported in the following extended table.

| Scenario | Description | Status | Sample count | Mean response time (ms) | P95 response time (ms) | Throughput (requests/s) | Unsupported evidence |
|---|---|---|---|---|---|---|---|
| `PLC_BALANCED_STATIC` | PLC_BALANCED_STATIC (balanced static) | measured | 3 | 1535.15 | 1600.00 | 0.5666 |  |
| `PLC_COLOCATED` | PLC_COLOCATED (co-located) | unsupported_under_current_constraints | 0 | n/a | n/a | n/a | benchmark_precheck, cluster_nodes_ready, metrics_api_and_capacity, namespace_active, namespace_pods_healthy, none_or_within_strict_threshold, pending_pod, service_endpoint_and_model, worker_nodes_expected |
| `PLC_DISTRIBUTED_TWO_NODE` | PLC_DISTRIBUTED_TWO_NODE (distributed two-node) | measured | 3 | 1530.12 | 1600.00 | 0.5676 |  |
| `PLC_SERVER_SEPARATED` | PLC_SERVER_SEPARATED (server separated) | measured | 3 | 1568.79 | 1600.00 | 0.5623 |  |
| `PLC_SPREAD_WORKERS` | PLC_SPREAD_WORKERS (spread workers) | measured | 3 | 1570.03 | 1733.33 | 0.5619 |  |

### Extended measurement metrics

This secondary table keeps the additional metrics aligned with the technical diagnosis while avoiding an excessively wide primary summary table.

| Scenario | P50 response time (ms) | P99 response time (ms) | Mean response time delta (%) | P95 response time delta (%) | Throughput delta (%) | Max node CPU snapshot (%) | Max node memory snapshot (%) | Max pod CPU snapshot (mCPU) | Max pod memory snapshot (MiB) |
|---|---|---|---|---|---|---|---|---|---|
| `PLC_BALANCED_STATIC` | 1500.00 | 1800.00 | -2.22 | -7.69 | 0.84 | 15.67 | 15.67 | 841.67 | 384.00 |
| `PLC_COLOCATED` | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| `PLC_DISTRIBUTED_TWO_NODE` | 1500.00 | 1833.33 | -2.54 | -7.69 | 1.01 | 18.33 | 16.00 | 796.33 | 384.00 |
| `PLC_SERVER_SEPARATED` | 1600.00 | 1900.00 | -0.08 | -7.69 | 0.07 | 15.00 | 16.00 | 780.00 | 384.33 |
| `PLC_SPREAD_WORKERS` | 1533.33 | 2000.00 | 0.00 | 0.00 | 0.00 | 10.67 | 16.00 | 818.33 | 384.33 |

### Placement context

This table makes the placement dimension explicit. Infrastructure, model, workload and LocalAI worker count are kept fixed while server and RPC-worker placement changes.

| Scenario | Placement | Profile | Server node | Worker node map | Communication distance | Resource contention |
|---|---|---|---|---|---|---|
| `PLC_BALANCED_STATIC` | balanced static | PL_BALANCED_STATIC | genai-pb-worker-02 | localai-rpc-a=genai-pb-worker-01, localai-rpc-b=genai-pb-worker-02, localai-rpc-c=genai-pb-worker-03, localai-rpc-d=genai-pb-worker-02 | medium | medium |
| `PLC_COLOCATED` | co-located | PL_COLOCATED | genai-pb-worker-02 | localai-rpc-a=genai-pb-worker-02, localai-rpc-b=genai-pb-worker-02, localai-rpc-c=genai-pb-worker-02, localai-rpc-d=genai-pb-worker-02 | minimal | highest |
| `PLC_DISTRIBUTED_TWO_NODE` | distributed two-node | PL_DISTRIBUTED_TWO_NODE | genai-pb-worker-02 | localai-rpc-a=genai-pb-worker-01, localai-rpc-b=genai-pb-worker-02, localai-rpc-c=genai-pb-worker-01, localai-rpc-d=genai-pb-worker-02 | medium | medium_high |
| `PLC_SERVER_SEPARATED` | server separated | PL_SERVER_SEPARATED | genai-pb-worker-01 | localai-rpc-a=genai-pb-worker-02, localai-rpc-b=genai-pb-worker-03, localai-rpc-c=genai-pb-worker-04, localai-rpc-d=genai-pb-worker-02 | highest | low |
| `PLC_SPREAD_WORKERS` | spread workers | PL_SPREAD_WORKERS | genai-pb-worker-02 | localai-rpc-a=genai-pb-worker-01, localai-rpc-b=genai-pb-worker-02, localai-rpc-c=genai-pb-worker-03, localai-rpc-d=genai-pb-worker-04 | higher | lowest |

### Diagnosis-based reading

- **The placement variation family provides comparable placement evidence.** (status: `comparative_signal_available`, confidence: `medium`).
  - Implication: The campaign can be used to reason about the communication-vs-contention trade-off because infrastructure, model, workload and LocalAI worker count remain fixed while only placement changes.
- **The placement campaign provides measured evidence across multiple placement policies.** (confidence: `medium`).
  - Implication: The evidence can be used to evaluate whether communication-distance reduction or resource-contention reduction dominates under the fixed infrastructure and workload.
- **The placement campaign identifies the lowest-latency placement among measured variants.** (confidence: `medium`).
  - Implication: This result provides a controlled signal for placement selection under fixed infrastructure, model, workload and LocalAI worker count.
- **At least one placement scenario produced unsupported evidence under the current constraints.** (confidence: `medium`).
  - Implication: Unsupported placement variants should be treated as contention, capacity or scheduling evidence and not as measured performance regressions.

### Charts

#### Mean response time

![Mean response time](charts/placement-variation/mean_response_time_ms.svg)

#### P50 response time

![P50 response time](charts/placement-variation/p50_response_time_ms.svg)

#### P95 response time

![P95 response time](charts/placement-variation/p95_response_time_ms.svg)

#### P99 response time

![P99 response time](charts/placement-variation/p99_response_time_ms.svg)

#### Throughput

![Throughput](charts/placement-variation/throughput_rps.svg)

#### Maximum node CPU snapshot

![Maximum node CPU snapshot](charts/placement-variation/max_node_cpu_percent.svg)

#### Maximum node memory snapshot

![Maximum node memory snapshot](charts/placement-variation/max_node_memory_percent.svg)

#### Maximum pod CPU snapshot

![Maximum pod CPU snapshot](charts/placement-variation/max_pod_cpu_millicores.svg)

#### Maximum pod memory snapshot

![Maximum pod memory snapshot](charts/placement-variation/max_pod_memory_mib.svg)

### Reading notes

- Measured scenarios: **4**.
- Unsupported scenarios under current constraints: **1**.
- Percentage deltas are computed against the family reference scenario; positive latency deltas indicate worse response time, while positive throughput deltas indicate higher request throughput.
- Unsupported scenarios are infrastructure/constraint observations and must not be interpreted as measured latency regressions.
- A `not_executed` sweep means that neither measurement CSV files nor unsupported-scenario evidence were found for any configured scenario in that family.

> Only placement is varied in this campaign; infrastructure, model, workload, LocalAI worker count and resource requests remain fixed.
> The co-located W4 variant may expose resource-contention or schedulability limits and must be reported as unsupported evidence if it cannot be benchmarked.
> Placement conclusions require checking both latency/throughput and cluster-side CPU/memory/pod-placement evidence.
