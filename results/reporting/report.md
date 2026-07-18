# LocalAI Worker-Mode Benchmark Results

Cycle-level benchmark reports across fixed-cluster and provider-backed executions

This page provides a compact entry point for reviewing benchmark reports across the available execution cycles. Each cycle is presented independently so that latency, throughput, resource pressure, placement, infrastructure size, latency injection, and multi-tenancy evidence can be interpreted within its own context.

**Reporting-site ID:** `REPORTING_SITE_20260709T201358Z`
**Generated at UTC:** `2026-07-09T20:13:58.330110Z`

## Summary

| Metric | Value |
|---|---|
| Available reports | 10 |
| Registered cycles | 10 |
| Scenario entries | 116 |
| Unsupported entries | 12 |

## Methodological note

Cross-cycle comparisons must account for the cross-cycle baseline, family-local reference scenarios, provider, and infrastructure profile documented in each cycle report. Scenario entries and unsupported entries summarize the available evidence and must be interpreted together with the corresponding cycle-level report.

## Cycle report index

| Cycle | Report profile | Provider | Infrastructure | Report availability | Scenarios | Unsupported | Generated at | Links |
|---|---|---|---|---|---|---|---|---|
| `C0` | `RP_C0_HISTORICAL_FIXED_CLUSTER` | external-k3s-cluster | INFRA_C0_1CP_2W_8C16G | available | 13 | 2 | 2026-06-19T17:46:12Z | [Open report](cycles/C0/index.html) |
| `C1` | `RP_C1_PROVIDER_BACKED_BASELINE` | proxmox-k3s | INFRA_C1_1CP_2W_8C16G | available | 1 | 0 | 2026-06-19T17:46:34Z | [Open report](cycles/C1/index.html) |
| `C2` | `RP_C2_RESOURCE_VARIATION` | proxmox-k3s | INFRA_C2_1CP_2W_4C8G, INFRA_C2_1CP_2W_4C16G, INFRA_C2_1CP_2W_8C16G | available | 3 | 2 | 2026-06-19T17:46:38Z | [Open report](cycles/C2/index.html) |
| `C3` | `RP_C3_NODE_COUNT_VARIATION` | proxmox-k3s | INFRA_C3_1CP_2W_8C16G, INFRA_C3_1CP_3W_8C16G, INFRA_C3_1CP_4W_8C16G | available | 3 | 0 | 2026-06-19T17:46:44Z | [Open report](cycles/C3/index.html) |
| `C4` | `RP_C4_PLACEMENT_VARIATION` | proxmox-k3s | INFRA_C4_1CP_4W_8C16G | available | 5 | 1 | 2026-06-19T17:46:54Z | [Open report](cycles/C4/index.html) |
| `C5` | `RP_C5_LATENCY_INJECTION` | proxmox-k3s | INFRA_C5_1CP_4W_8C16G | available | 4 | 1 | 2026-06-19T17:47:11Z | [Open report](cycles/C5/index.html) |
| `C6` | `RP_C6_MULTI_TENANCY` | proxmox-k3s | INFRA_C6_1CP_4W_8C16G | available | 4 | 1 | 2026-06-19T17:47:25Z | [Open report](cycles/C6/index.html) |
| `C7` | `RP_C7_DEFAULT_SCHEDULER_BASELINE` | proxmox-k3s | INFRA_C7_1CP_2W_8C16G, INFRA_C7_1CP_4W_8C16G, INFRA_C7_1CP_3W_8C16G | available | 25 | 2 | 2026-06-19T17:47:51Z | [Open report](cycles/C7/index.html) |
| `C8` | `RP_C8_RESOURCE_AWARE_SCHEDULER` | proxmox-k3s | INFRA_C8_1CP_2W_8C16G, INFRA_C8_1CP_4W_8C16G | available | 16 | 1 | 2026-06-19T17:50:31Z | [Open report](cycles/C8/index.html) |
| `C9` | `RP_C9_NETWORK_AWARE_SCHEDULER` | proxmox-k3s | INFRA_C9_1CP_4W_8C16G | available | 42 | 2 | 2026-07-09T20:12:27Z | [Open report](cycles/C9/index.html) |
