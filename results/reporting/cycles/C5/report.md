# C5 — Latency Injection Report

**Cycle ID:** `C5`
**Reporting Profile:** `RP_C5_LATENCY_INJECTION`
**Reporting ID:** `REP_C5_20260619T174611Z`
**Generated at UTC:** `2026-06-19T17:47:11Z`

## Purpose

This report compares progressively injected network-latency profiles under fixed provider-backed infrastructure, model, workload, LocalAI worker count and placement. It is intended to expose when distributed worker communication becomes a dominant performance factor.

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
| Latency Injection | `LI_L0_NONE` | LI_L0_NONE (0 ms, jitter 0 ms) | measured | latency profile |

## Data sources

| Layer | Primary use | Source |
|---|---|---|
| Measurement CSV | Quantitative charts and scenario summary metrics | `{"latency-injection": "results/experimental-cycles/C5/benchmark/latency-injection"}` |
| Technical diagnosis | Interpretation, family judgments, findings, unsupported-scenario context | `results/experimental-cycles/C5/diagnosis/analysis_diagnosis_all_NA_20260619T174711Z_diagnosis.json` |
| Scenario configuration | Fixed/varied dimensions and scenario labels | `config/scenarios/**` |
| Cluster-side artifacts | CPU/memory snapshots, pod placement and event evidence | `minimal observability and cluster capture artifacts` |
| Reporting output | Current generated report package | `results/experimental-cycles/C5/reporting` |

## Infrastructure Summary

| Item | Value |
|---|---|
| Cycle ID | C5 |
| Baseline ID | B1 |
| Infrastructure profile | INFRA_C5_1CP_4W_8C16G |
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
| Covered scenarios | `LI_L0_NONE`, `LI_L1_EDGE_NEAR`, `LI_L2_EDGE_REMOTE`, `LI_L3_EXTREME` |
| Provider | proxmox-k3s |
| Provider binding | BINDING_INFRA_C5_1CP_4W_8C16G_PROXMOX_K3S |
| Provider binding path | config/infrastructure/providers/proxmox-k3s/bindings/BINDING_INFRA_C5_1CP_4W_8C16G_PROXMOX_K3S.json |
| Example config | config/infrastructure/providers/proxmox-k3s/examples/cluster.c5-1cp-4w-8c16g.example.yaml |
| Local config | config/infrastructure/providers/proxmox-k3s/local/cluster.c5-1cp-4w-8c16g.local.yaml |
| Kubeconfig | config/cluster-access/generated/proxmox-k3s/c5-1cp-4w-8c16g/kubeconfig |

## Cluster Validation Summary

| Item | Value |
|---|---|
| Validation profile | CV_PROVIDER_BACKED_VALIDATION_TEMPLATE |
| Profile file | config/cluster-validation/templates/CV_PROVIDER_BACKED_VALIDATION_TEMPLATE.json |
| Latest manifest | variant-scoped validation manifests (4 available) |
| Current status | variant-scoped validation available (4/4 validated) |
| Variant validation statuses | validated=4 |
| Latest raw validation | variant-scoped validation evidence is recorded in the campaign execution manifest and generated runtime profiles under results/experimental-cycles/C5/execution/generated-runtime-configs |
| Accepted provisioning statuses | completed |
| Required kubeconfig status | verified |
| Artifact root | results/experimental-cycles/C5/execution/generated-runtime-configs |

## Runtime Profile Variant Summary

This table links each scenario to the runtime-generated profiles used for precheck, application deployment and minimal observability evidence.

| Scenario | Family | Precheck profile | Precheck profile path | Application deployment profile | Application deployment profile path | Minimal observability profile | Minimal observability profile path | Cluster validation evidence |
|---|---|---|---|---|---|---|---|---|
| `LI_L0_NONE` | latency-injection | TC_C5_LI_L0_NONE | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L0_NONE/TC_LI_L0_NONE.json | AD_C5_LI_L0_NONE | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L0_NONE/AD_LI_L0_NONE.json | MO_C5_LI_L0_NONE | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L0_NONE/MO_LI_L0_NONE.json | results/experimental-cycles/C5/variants/LI_L0_NONE/infrastructure/validation/latest-cluster-validation-manifest.json (validated) |
| `LI_L1_EDGE_NEAR` | latency-injection | TC_C5_LI_L1_EDGE_NEAR | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L1_EDGE_NEAR/TC_LI_L1_EDGE_NEAR.json | AD_C5_LI_L1_EDGE_NEAR | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L1_EDGE_NEAR/AD_LI_L1_EDGE_NEAR.json | MO_C5_LI_L1_EDGE_NEAR | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L1_EDGE_NEAR/MO_LI_L1_EDGE_NEAR.json | results/experimental-cycles/C5/variants/LI_L1_EDGE_NEAR/infrastructure/validation/latest-cluster-validation-manifest.json (validated) |
| `LI_L2_EDGE_REMOTE` | latency-injection | TC_C5_LI_L2_EDGE_REMOTE | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L2_EDGE_REMOTE/TC_LI_L2_EDGE_REMOTE.json | AD_C5_LI_L2_EDGE_REMOTE | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L2_EDGE_REMOTE/AD_LI_L2_EDGE_REMOTE.json | MO_C5_LI_L2_EDGE_REMOTE | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L2_EDGE_REMOTE/MO_LI_L2_EDGE_REMOTE.json | results/experimental-cycles/C5/variants/LI_L2_EDGE_REMOTE/infrastructure/validation/latest-cluster-validation-manifest.json (validated) |
| `LI_L3_EXTREME` | latency-injection | TC_C5_LI_L3_EXTREME | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L3_EXTREME/TC_LI_L3_EXTREME.json | AD_C5_LI_L3_EXTREME | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L3_EXTREME/AD_LI_L3_EXTREME.json | MO_C5_LI_L3_EXTREME | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L3_EXTREME/MO_LI_L3_EXTREME.json | results/experimental-cycles/C5/variants/LI_L3_EXTREME/infrastructure/validation/latest-cluster-validation-manifest.json (validated) |

## Application Topology Summary

This campaign may vary placement, tenancy, latency profile or generated deployment profiles at scenario level. The table below exposes the scenario-level application topology used by each configured variant.

| Scenario | Family | Placement profile | Placement type | Topology dir | Server manifest | Worker count | Active RPC workers | Expected server node | Expected worker nodes | Latency profile | Tenancy profile | Generated deployment profile |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `LI_L0_NONE` | latency-injection | PL_SPREAD_WORKERS | spread_workers_across_four_provider_worker_nodes | infra/k8s/compositions/topology/spread-genai-pb-4-worker-nodes-w4 | infra/k8s/compositions/server/models/m1-provider-backed | 4 | localai-rpc-a, localai-rpc-b, localai-rpc-c, localai-rpc-d | genai-pb-worker-02 | localai-rpc-a=genai-pb-worker-01, localai-rpc-b=genai-pb-worker-02, localai-rpc-c=genai-pb-worker-03, localai-rpc-d=genai-pb-worker-04 | L0_NONE | not_declared | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L0_NONE/AD_LI_L0_NONE.json |
| `LI_L1_EDGE_NEAR` | latency-injection | PL_SPREAD_WORKERS | spread_workers_across_four_provider_worker_nodes | infra/k8s/compositions/topology/spread-genai-pb-4-worker-nodes-w4 | infra/k8s/compositions/server/models/m1-provider-backed | 4 | localai-rpc-a, localai-rpc-b, localai-rpc-c, localai-rpc-d | genai-pb-worker-02 | localai-rpc-a=genai-pb-worker-01, localai-rpc-b=genai-pb-worker-02, localai-rpc-c=genai-pb-worker-03, localai-rpc-d=genai-pb-worker-04 | L1_EDGE_NEAR | not_declared | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L1_EDGE_NEAR/AD_LI_L1_EDGE_NEAR.json |
| `LI_L2_EDGE_REMOTE` | latency-injection | PL_SPREAD_WORKERS | spread_workers_across_four_provider_worker_nodes | infra/k8s/compositions/topology/spread-genai-pb-4-worker-nodes-w4 | infra/k8s/compositions/server/models/m1-provider-backed | 4 | localai-rpc-a, localai-rpc-b, localai-rpc-c, localai-rpc-d | genai-pb-worker-02 | localai-rpc-a=genai-pb-worker-01, localai-rpc-b=genai-pb-worker-02, localai-rpc-c=genai-pb-worker-03, localai-rpc-d=genai-pb-worker-04 | L2_EDGE_REMOTE | not_declared | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L2_EDGE_REMOTE/AD_LI_L2_EDGE_REMOTE.json |
| `LI_L3_EXTREME` | latency-injection | PL_SPREAD_WORKERS | spread_workers_across_four_provider_worker_nodes | infra/k8s/compositions/topology/spread-genai-pb-4-worker-nodes-w4 | infra/k8s/compositions/server/models/m1-provider-backed | 4 | localai-rpc-a, localai-rpc-b, localai-rpc-c, localai-rpc-d | genai-pb-worker-02 | localai-rpc-a=genai-pb-worker-01, localai-rpc-b=genai-pb-worker-02, localai-rpc-c=genai-pb-worker-03, localai-rpc-d=genai-pb-worker-04 | L3_EXTREME | not_declared | results/experimental-cycles/C5/execution/generated-runtime-configs/LI_L3_EXTREME/AD_LI_L3_EXTREME.json |

## Scenario Summary

The following table summarizes the currently available measurement and constraint evidence for all configured reporting families.

| Family | Scenario | Status | Samples | Mean ms | P95 ms | RPS | Unsupported evidence |
|---|---|---|---|---|---|---|---|
| latency-injection | LI_L0_NONE | measured | 3 | 1560.12 | 1600.00 | 0.5630 | NA |
| latency-injection | LI_L1_EDGE_NEAR | measured | 3 | 23467.32 | 26000.00 | 0.0749 | NA |
| latency-injection | LI_L2_EDGE_REMOTE | measured | 3 | 64483.46 | 80333.33 | 0.0251 | NA |
| latency-injection | LI_L3_EXTREME | unsupported_under_current_constraints | 0 | NA | NA | NA | all_worker_nodes_from_infrastructure_profile,api_smoke_failed,api_smoke_or_pre_benchmark_api_unavailable,latency_injection,latency_injection_pre_benchmark,measurement_stats_csv_missing,pre_benchmark_failure |

## Metrics Summary

The reporting generator first uses minimal observability metrics when available; missing values are filled from scenario-summary aggregates derived from benchmark CSV files and cluster-capture artifacts whenever possible. Values marked as `not_available` were not derivable from the available artifact set and are intentionally distinguished from measured zero values.

| Metric | Value | Source |
|---|---|---|
| request_count | 25.8889 | scenario summary aggregation fallback |
| success_rate_percent | 100.0 | scenario summary aggregation fallback |
| failure_count | 0 | scenario summary aggregation fallback |
| mean_response_time_ms | 29836.9679 | scenario summary aggregation fallback |
| p50_response_time_ms | 33622.2222 | scenario summary aggregation fallback |
| p95_response_time_ms | 35977.7778 | scenario summary aggregation fallback |
| p99_response_time_ms | 36055.5555 | scenario summary aggregation fallback |
| throughput_rps | 0.221 | scenario summary aggregation fallback |
| max_node_cpu_percent | 4.1111 | scenario summary aggregation fallback |
| max_node_memory_percent | 16.0 | scenario summary aggregation fallback |
| max_pod_cpu_millicores | 326.1111 | scenario summary aggregation fallback |
| max_pod_memory_mib | 384.2222 | scenario summary aggregation fallback |
| pod_restart_count | 0 | scenario summary aggregation fallback |
| pending_pods_count | 0 | scenario summary aggregation fallback |
| failed_pods_count | 0 | scenario summary aggregation fallback |
| not_ready_pods_count | 0 | scenario summary aggregation fallback |
| kubernetes_events_count | 39 | scenario summary aggregation fallback |
| kubernetes_warning_events_count | 0 | scenario summary aggregation fallback |

## Unsupported Scenario Summary

| Family | Scenario | Status | Evidence | Source |
|---|---|---|---|---|
| latency-injection | LI_L3_EXTREME | unsupported_under_current_constraints | all_worker_nodes_from_infrastructure_profile, api_smoke_failed, api_smoke_or_pre_benchmark_api_unavailable, latency_injection, latency_injection_pre_benchmark, measurement_stats_csv_missing, pre_benchmark_failure | results/experimental-cycles/C5/benchmark/latency-injection/LI_L3_EXTREME_official_locked/LI_L3_EXTREME_runA_unsupported.json, results/experimental-cycles/C5/benchmark/latency-injection/LI_L3_EXTREME_official_locked/LI_L3_EXTREME_runB_unsupported.json, results/experimental-cycles/C5/benchmark/latency-injection/LI_L3_EXTREME_official_locked/LI_L3_EXTREME_runC_unsupported.json |

## Main Findings

| Family | Finding | Status | Confidence | Implication |
|---|---|---|---|---|
| latency-injection | The latency-injection family provides comparable network-sensitivity evidence. | comparative_signal_available | medium | The campaign can be used to reason about when injected inter-node latency degrades LocalAI worker-mode behavior because infrastructure, model, workload, worker count and placement remain fixed while only latency changes. |
| latency-injection | The latency-injection campaign provides measured evidence across multiple network-latency profiles. | NA | medium | The evidence can be used to evaluate whether inter-node communication delay becomes a dominant factor under the fixed distributed placement. |
| latency-injection | The latency-injection campaign identifies the highest-latency measured profile. | NA | medium | This result provides a controlled signal for deciding when distributed worker placement becomes sensitive to network delay. |
| baseline | Minimum end-to-end validation is available as a functional reliability baseline. | NA | high | The benchmark pipeline starts from a verified functional baseline rather than from a purely theoretical setup. |

## Sweep-specific reports

The global report below provides the stakeholder-facing overview. Each sweep also has a dedicated report for focused inspection of one varied dimension.

| Sweep | Dedicated HTML report | Execution status | Coverage | Varied dimension |
|---|---|---|---|---|
| Latency Injection | [latency-injection](sweeps/latency-injection/index.html) | partially_measured | measured=3, unsupported=1, missing=0 | latency profile |

## Diagnosis coverage snapshot

| Family | Scenarios | Observed | Measured | Unsupported | Samples |
|---|---|---|---|---|---|
| latency-injection | 4 | 4 | 3 | 1 | 9 |

## Latency Injection

**Execution status:** `partially_measured`

**Execution note:** At least one configured scenario has measured benchmark samples, while other scenarios are missing or unsupported.

**Varied dimension:** latency profile

**Fixed dimensions:** infrastructure=INFRA_C5_1CP_4W_8C16G, model=M1, LocalAI worker-count=W4, workload=WL2, placement=PL_SPREAD_WORKERS, worker node capacity=8 vCPU / 16 GiB.

**Reference scenario within the sweep:** `LI_L0_NONE`

| Scenario count | Measured | Unsupported | Missing |
|---|---|---|---|
| 4 | 3 | 1 | 0 |

### Controlled scenario parameters

This table is derived from resolved scenario metadata. A parameter is marked as controlled only when it has the same effective value across all scenarios in the sweep.

| Parameter | Resolved value | Interpretation |
|---|---|---|
| Model | llama-3.2-1b-instruct:q4_k_m | controlled |
| Worker count | 4 | controlled |
| Placement | spread_workers_across_four_provider_worker_nodes | controlled |
| Workload | users=2, spawnRate=1, runTime=2m | controlled |
| Topology | infra/k8s/compositions/topology/spread-genai-pb-4-worker-nodes-w4 | controlled |
| Server manifest | infra/k8s/compositions/server/models/m1-provider-backed | controlled |
| Prompt | Reply with only READY. | controlled |
| Temperature | 0.1 | controlled |
| Request timeout (s) | 120 | controlled |

### Scenario parameter matrix

| Scenario | Status | Varied value (latency profile) | Model | Worker count | Placement | Workload | Timeout (s) |
|---|---|---|---|---|---|---|---|
| `LI_L0_NONE` | measured | 0 ms delay / 0 ms jitter / 0.0% loss | llama-3.2-1b-instruct:q4_k_m | 4 | spread_workers_across_four_provider_worker_nodes | users=2, spawnRate=1, runTime=2m | 120 |
| `LI_L1_EDGE_NEAR` | measured | 50 ms delay / 5 ms jitter / 0.0% loss | llama-3.2-1b-instruct:q4_k_m | 4 | spread_workers_across_four_provider_worker_nodes | users=2, spawnRate=1, runTime=2m | 120 |
| `LI_L2_EDGE_REMOTE` | measured | 150 ms delay / 15 ms jitter / 0.0% loss | llama-3.2-1b-instruct:q4_k_m | 4 | spread_workers_across_four_provider_worker_nodes | users=2, spawnRate=1, runTime=2m | 120 |
| `LI_L3_EXTREME` | unsupported_under_current_constraints | 600 ms delay / 50 ms jitter / 0.0% loss | llama-3.2-1b-instruct:q4_k_m | 4 | spread_workers_across_four_provider_worker_nodes | users=2, spawnRate=1, runTime=2m | 120 |

### Measurement summary

This compact table reports the core indicators used to read the sweep at a glance. Detailed percentiles, deltas and resource snapshots are reported in the following extended table.

| Scenario | Description | Status | Sample count | Mean response time (ms) | P95 response time (ms) | Throughput (requests/s) | Unsupported evidence |
|---|---|---|---|---|---|---|---|
| `LI_L0_NONE` | LI_L0_NONE (0 ms, jitter 0 ms) | measured | 3 | 1560.12 | 1600.00 | 0.5630 |  |
| `LI_L1_EDGE_NEAR` | LI_L1_EDGE_NEAR (50 ms, jitter 5 ms) | measured | 3 | 23467.32 | 26000.00 | 0.0749 |  |
| `LI_L2_EDGE_REMOTE` | LI_L2_EDGE_REMOTE (150 ms, jitter 15 ms) | measured | 3 | 64483.46 | 80333.33 | 0.0251 |  |
| `LI_L3_EXTREME` | LI_L3_EXTREME (600 ms, jitter 50 ms) | unsupported_under_current_constraints | 0 | n/a | n/a | n/a | all_worker_nodes_from_infrastructure_profile, api_smoke_failed, api_smoke_or_pre_benchmark_api_unavailable, latency_injection, latency_injection_pre_benchmark, measurement_stats_csv_missing, pre_benchmark_failure |

### Extended measurement metrics

This secondary table keeps the additional metrics aligned with the technical diagnosis while avoiding an excessively wide primary summary table.

| Scenario | P50 response time (ms) | P99 response time (ms) | Mean response time delta (%) | P95 response time delta (%) | Throughput delta (%) | Max node CPU snapshot (%) | Max node memory snapshot (%) | Max pod CPU snapshot (mCPU) | Max pod memory snapshot (MiB) |
|---|---|---|---|---|---|---|---|---|---|
| `LI_L0_NONE` | 1533.33 | 1833.33 | 0.00 | 0.00 | 0.00 | 10.33 | 16.00 | 795.67 | 384.00 |
| `LI_L1_EDGE_NEAR` | 24333.33 | 26000.00 | 1404.20 | 1525.00 | -86.70 | 1.00 | 16.00 | 117.33 | 384.67 |
| `LI_L2_EDGE_REMOTE` | 75000.00 | 80333.33 | 4033.24 | 4920.83 | -95.54 | 1.00 | 16.00 | 65.33 | 384.00 |
| `LI_L3_EXTREME` | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

### Latency-injection context

This table makes the network-emulation dimension explicit. Infrastructure, model, workload, LocalAI worker count and placement are kept fixed while the injected latency profile changes.

| Scenario | Latency profile | Category | Target node policy | Delay (ms) | Jitter (ms) | Packet loss (%) | Interface | Reset after benchmark | Execution status | Unsupported reason |
|---|---|---|---|---|---|---|---|---|---|---|
| `LI_L0_NONE` | L0_NONE | none | all_worker_nodes_from_infrastructure_profile | 0 | 0 | 0.0 | eth0 | yes | measured | none |
| `LI_L1_EDGE_NEAR` | L1_EDGE_NEAR | edge_near | all_worker_nodes_from_infrastructure_profile | 50 | 5 | 0.0 | eth0 | yes | measured | none |
| `LI_L2_EDGE_REMOTE` | L2_EDGE_REMOTE | edge_remote | all_worker_nodes_from_infrastructure_profile | 150 | 15 | 0.0 | eth0 | yes | measured | none |
| `LI_L3_EXTREME` | L3_EXTREME | extreme | all_worker_nodes_from_infrastructure_profile | 600 | 50 | 0.0 | eth0 | yes | unsupported_under_current_constraints | latency_profile_pre_benchmark_api_unavailable, latency_profile_pre_benchmark_api_unavailable, latency_profile_pre_benchmark_api_unavailable |

### Diagnosis-based reading

- **The latency-injection family provides comparable network-sensitivity evidence.** (status: `comparative_signal_available`, confidence: `medium`).
  - Implication: The campaign can be used to reason about when injected inter-node latency degrades LocalAI worker-mode behavior because infrastructure, model, workload, worker count and placement remain fixed while only latency changes.
- **The latency-injection campaign provides measured evidence across multiple network-latency profiles.** (confidence: `medium`).
  - Implication: The evidence can be used to evaluate whether inter-node communication delay becomes a dominant factor under the fixed distributed placement.
- **The latency-injection campaign identifies the highest-latency measured profile.** (confidence: `medium`).
  - Implication: This result provides a controlled signal for deciding when distributed worker placement becomes sensitive to network delay.
- **At least one latency-injection scenario produced unsupported evidence under the current constraints.** (confidence: `medium`).
  - Implication: Unsupported latency variants should be treated as instrumentation, timeout or network-sensitivity evidence and not as ordinary benchmark failures.

### Charts

#### Mean response time

![Mean response time](charts/latency-injection/mean_response_time_ms.svg)

#### P50 response time

![P50 response time](charts/latency-injection/p50_response_time_ms.svg)

#### P95 response time

![P95 response time](charts/latency-injection/p95_response_time_ms.svg)

#### P99 response time

![P99 response time](charts/latency-injection/p99_response_time_ms.svg)

#### Throughput

![Throughput](charts/latency-injection/throughput_rps.svg)

#### Maximum node CPU snapshot

![Maximum node CPU snapshot](charts/latency-injection/max_node_cpu_percent.svg)

#### Maximum node memory snapshot

![Maximum node memory snapshot](charts/latency-injection/max_node_memory_percent.svg)

#### Maximum pod CPU snapshot

![Maximum pod CPU snapshot](charts/latency-injection/max_pod_cpu_millicores.svg)

#### Maximum pod memory snapshot

![Maximum pod memory snapshot](charts/latency-injection/max_pod_memory_mib.svg)

### Reading notes

- Measured scenarios: **3**.
- Unsupported scenarios under current constraints: **1**.
- Percentage deltas are computed against the family reference scenario; positive latency deltas indicate worse response time, while positive throughput deltas indicate higher request throughput.
- Unsupported scenarios are infrastructure/constraint observations and must not be interpreted as measured latency regressions.
- A `not_executed` sweep means that neither measurement CSV files nor unsupported-scenario evidence were found for any configured scenario in that family.

> Only the latency profile is varied in this campaign; infrastructure, model, workload, LocalAI worker count and placement remain fixed.
> The no-latency profile is the campaign-local reference scenario.
> Latency conclusions require checking both latency/throughput and the latency-injection manifests to ensure the intended profile was applied.
