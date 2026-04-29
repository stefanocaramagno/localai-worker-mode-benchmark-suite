# Placement sweep Report

**Reporting ID:** `analysis_reporting_all_NA_20260429T032103Z`
**Generated at UTC:** `2026-04-29T03:21:03.257749+00:00`

[Back to consolidated reporting index](../../index.html)

## Scope

This sweep-specific report isolates one benchmark family so that the varied dimension, fixed dimensions, measured values, unsupported evidence and diagnosis-based reading can be inspected without navigating the full consolidated report.

## Placement sweep

**Execution status:** `fully_measured`

**Execution note:** All configured scenarios in this sweep have measured benchmark samples.

**Varied dimension:** Kubernetes placement strategy for LocalAI server and workers

**Fixed dimensions:** baseline model, baseline worker count, baseline workload, baseline protocol.

**Reference scenario within the sweep:** `PL1`

| Scenario count | Measured | Unsupported | Missing |
|---|---|---|---|
| 2 | 2 | 0 | 0 |

### Fixed baseline parameters

| Fixed dimension | Value inherited from baseline |
|---|---|
| Model | llama-3.2-1b-instruct:q4_k_m |
| Worker count | 2 |
| Workload | users=2, spawnRate=1, runTime=2m |
| Prompt | Reply with only READY. |
| Temperature | 0.1 |
| Request timeout | 120 s |

### Scenario parameter matrix

| Scenario | Status | Varied value (Kubernetes placement strategy for LocalAI server and workers) | Model | Workers | Placement | Workload | Timeout (s) |
|---|---|---|---|---|---|---|---|
| `PL1` | measured | colocated_sc_app_02 | llama-3.2-1b-instruct:q4_k_m | 2 | colocated_sc_app_02 | users=2, spawnRate=1, runTime=2m | 120 |
| `PL2` | measured | distributed | llama-3.2-1b-instruct:q4_k_m | 2 | distributed | users=2, spawnRate=1, runTime=2m | 120 |

### Measurement summary

This compact table reports the core indicators used to read the sweep at a glance. Detailed percentiles, deltas and resource snapshots are reported in the following extended table.

| Scenario | Description | Status | Sample count | Mean response time (ms) | P95 response time (ms) | Throughput (requests/s) | Unsupported evidence |
|---|---|---|---|---|---|---|---|
| `PL1` | PL1 (colocated_sc_app_02) | measured | 3 | 1483.75 | 1500.00 | 0.5749 |  |
| `PL2` | PL2 (distributed) | measured | 3 | 1538.32 | 1600.00 | 0.5656 |  |

### Extended measurement metrics

This secondary table keeps the additional metrics aligned with the technical diagnosis while avoiding an excessively wide primary summary table.

| Scenario | P50 response time (ms) | P99 response time (ms) | Mean response time delta (%) | P95 response time delta (%) | Throughput delta (%) | Max node CPU snapshot (%) | Max node memory snapshot (%) |
|---|---|---|---|---|---|---|---|
| `PL1` | 1500.00 | 1633.33 | 0.00 | 0.00 | 0.00 | 35.00 | 32.67 |
| `PL2` | 1500.00 | 1633.33 | 3.68 | 6.67 | -1.62 | 21.00 | 33.67 |

### Diagnosis-based reading

- **Nel perimetro osservato la famiglia placement non mostra ancora un effetto abbastanza marcato da essere considerato dominante.** (status: `weak_signal`, confidence: `low`).
  - Implication: Le configurazioni di placement sono state confrontate rispetto alla baseline co-located PL1, ma la differenza di latenza resta sotto la soglia diagnostica configurata; nel cluster corrente il placement non emerge ancora come driver principale delle performance.

### Charts

#### Mean response time

![Mean response time](../../charts/placement/mean_response_time_ms.svg)

#### P50 response time

![P50 response time](../../charts/placement/p50_response_time_ms.svg)

#### P95 response time

![P95 response time](../../charts/placement/p95_response_time_ms.svg)

#### P99 response time

![P99 response time](../../charts/placement/p99_response_time_ms.svg)

#### Throughput

![Throughput](../../charts/placement/throughput_rps.svg)

#### Maximum node CPU snapshot

![Maximum node CPU snapshot](../../charts/placement/max_node_cpu_percent.svg)

#### Maximum node memory snapshot

![Maximum node memory snapshot](../../charts/placement/max_node_memory_percent.svg)

### Reading notes

- Measured scenarios: **2**.
- Unsupported scenarios under current constraints: **0**.
- Percentage deltas are computed against the family reference scenario; positive latency deltas indicate worse response time, while positive throughput deltas indicate higher request throughput.
- Unsupported scenarios are infrastructure/constraint observations and must not be interpreted as measured latency regressions.
- A `not_executed` sweep means that neither measurement CSV files nor unsupported-scenario evidence were found for any configured scenario in that family.
