# Model sweep Report

**Reporting ID:** `analysis_reporting_all_NA_20260429T032103Z`
**Generated at UTC:** `2026-04-29T03:21:03.257749+00:00`

[Back to consolidated reporting index](../../index.html)

## Scope

This sweep-specific report isolates one benchmark family so that the varied dimension, fixed dimensions, measured values, unsupported evidence and diagnosis-based reading can be inspected without navigating the full consolidated report.

## Model sweep

**Execution status:** `fully_measured`

**Execution note:** All configured scenarios in this sweep have measured benchmark samples.

**Varied dimension:** model served by the LocalAI worker-mode cluster

**Fixed dimensions:** baseline worker count, baseline workload, baseline placement, baseline protocol.

**Reference scenario within the sweep:** `M1`

| Scenario count | Measured | Unsupported | Missing |
|---|---|---|---|
| 4 | 4 | 0 | 0 |

### Fixed baseline parameters

| Fixed dimension | Value inherited from baseline |
|---|---|
| Worker count | 2 |
| Placement | colocated_sc_app_02 |
| Workload | users=2, spawnRate=1, runTime=2m |
| Prompt | Reply with only READY. |
| Temperature | 0.1 |
| Request timeout | 120 s |

### Scenario parameter matrix

| Scenario | Status | Varied value (model served by the LocalAI worker-mode cluster) | Model | Workers | Placement | Workload | Timeout (s) |
|---|---|---|---|---|---|---|---|
| `M1` | measured | llama-3.2-1b-instruct:q4_k_m | llama-3.2-1b-instruct:q4_k_m | 2 | colocated_sc_app_02 | users=2, spawnRate=1, runTime=2m | 120 |
| `M2` | measured | llama-3.2-1b-instruct:q8_0 | llama-3.2-1b-instruct:q8_0 | 2 | colocated_sc_app_02 | users=2, spawnRate=1, runTime=2m | 120 |
| `M3` | measured | llama-3.2-3b-instruct:q4_k_m | llama-3.2-3b-instruct:q4_k_m | 2 | colocated_sc_app_02 | users=2, spawnRate=1, runTime=2m | 120 |
| `M4` | measured | llama-3.2-3b-instruct:q8_0 | llama-3.2-3b-instruct:q8_0 | 2 | colocated_sc_app_02 | users=2, spawnRate=1, runTime=2m | 120 |

### Measurement summary

This compact table reports the core indicators used to read the sweep at a glance. Detailed percentiles, deltas and resource snapshots are reported in the following extended table.

| Scenario | Description | Status | Sample count | Mean response time (ms) | P95 response time (ms) | Throughput (requests/s) | Unsupported evidence |
|---|---|---|---|---|---|---|---|
| `M1` | M1 (llama-3.2-1b-instruct:q4_k_m) | measured | 3 | 1497.13 | 1600.00 | 0.5725 |  |
| `M2` | M2 (llama-3.2-1b-instruct:q8_0) | measured | 3 | 1381.22 | 1400.00 | 0.5927 |  |
| `M3` | M3 (llama-3.2-3b-instruct:q4_k_m) | measured | 3 | 5168.81 | 5100.00 | 0.2782 |  |
| `M4` | M4 (llama-3.2-3b-instruct:q8_0) | measured | 3 | 4345.21 | 4400.00 | 0.3146 |  |

### Extended measurement metrics

This secondary table keeps the additional metrics aligned with the technical diagnosis while avoiding an excessively wide primary summary table.

| Scenario | P50 response time (ms) | P99 response time (ms) | Mean response time delta (%) | P95 response time delta (%) | Throughput delta (%) | Max node CPU snapshot (%) | Max node memory snapshot (%) |
|---|---|---|---|---|---|---|---|
| `M1` | 1500.00 | 1700.00 | 0.00 | 0.00 | 0.00 | 34.00 | 37.67 |
| `M2` | 1400.00 | 1500.00 | -7.74 | -12.50 | 3.53 | 32.67 | 35.00 |
| `M3` | 5000.00 | 9300.00 | 245.25 | 218.75 | -51.41 | 52.00 | 43.00 |
| `M4` | 4300.00 | 6400.00 | 190.24 | 175.00 | -45.05 | 52.00 | 52.00 |

### Diagnosis-based reading

- **La famiglia models mostra una penalità dimensionale netta e dominante sulla latenza media.** (status: `strong_signal`, confidence: `high`).
  - Implication: Nel cluster corrente la scelta del modello incide fortemente sul comportamento del servizio e rappresenta uno dei driver principali della performance osservata.

### Charts

#### Mean response time

![Mean response time](../../charts/models/mean_response_time_ms.svg)

#### P50 response time

![P50 response time](../../charts/models/p50_response_time_ms.svg)

#### P95 response time

![P95 response time](../../charts/models/p95_response_time_ms.svg)

#### P99 response time

![P99 response time](../../charts/models/p99_response_time_ms.svg)

#### Throughput

![Throughput](../../charts/models/throughput_rps.svg)

#### Maximum node CPU snapshot

![Maximum node CPU snapshot](../../charts/models/max_node_cpu_percent.svg)

#### Maximum node memory snapshot

![Maximum node memory snapshot](../../charts/models/max_node_memory_percent.svg)

### Reading notes

- Measured scenarios: **4**.
- Unsupported scenarios under current constraints: **0**.
- Percentage deltas are computed against the family reference scenario; positive latency deltas indicate worse response time, while positive throughput deltas indicate higher request throughput.
- Unsupported scenarios are infrastructure/constraint observations and must not be interpreted as measured latency regressions.
- A `not_executed` sweep means that neither measurement CSV files nor unsupported-scenario evidence were found for any configured scenario in that family.
