# LocalAI Worker-Mode Benchmark Suite

A configuration-driven benchmark suite for evaluating LocalAI worker-mode inference workloads on Kubernetes and provider-backed K3s clusters.

The suite is designed to make distributed inference experiments reproducible, inspectable, and comparable. It models how application behavior changes when worker placement, node capacity, workload shape, model mix, tenant coexistence, network distance, runtime telemetry, scheduler policy, and artifact completeness vary across controlled experimental cycles.

---

## Purpose

LocalAI worker mode separates the API-facing LocalAI master from one or more RPC workers. In this topology, performance and operational stability depend on more than the selected model or request rate. They also depend on pod placement, node capacity, CPU and memory contention, network latency, tenant traffic intensity, gateway routing, scheduler decisions, and the quality of telemetry made available to the scheduler.

This repository provides a complete benchmark framework for studying those factors through explicit configuration profiles, Kubernetes manifests, provider-backed infrastructure bindings, workload definitions, observability capture, scheduler evidence, technical diagnosis, reporting, completion gates, and frozen evidence packages.

The project is intended for controlled experimental campaigns rather than ad hoc load testing. Source files define the intended experiment. Generated artifacts record what happened during a specific execution.

---

## Core Capabilities

The benchmark suite supports:

- LocalAI server/RPC-worker deployment topologies;
- fixed-cluster and provider-backed K3s execution models;
- provider lifecycle integration through `proxmox-k3s` profiles and bindings;
- single-tenant and multi-tenant workload scenarios;
- workload, model, worker-count, node-count, placement, latency, tenancy, traffic-shape, and scheduler-mode variation;
- Kubernetes default scheduler evidence capture;
- custom scheduler evaluation with `LoadAwareResourcesBalancedAllocation`;
- LocalAI-specific resource plus network-aware scheduler evaluation with `NetworkAwareLocalAi`;
- `mon-agent` runtime annotation evidence for CPU, memory, traffic, and network-facing scheduler inputs;
- Mentat inter-node telemetry for latency, packet loss, and bandwidth;
- Istio gateway-routed traffic evidence for network-aware scenarios;
- `cluster-lens` placement evidence for C9 variants;
- unsupported-scenario classification when capacity, scheduling, telemetry, rollout, latency, or topology constraints are reached;
- technical diagnosis, reporting, completion-gate evaluation, freeze packaging, and generated reporting-site artifacts.

---

## Experimental Cycle Taxonomy

The repository organizes experiments into cycle-scoped workflows.

| Cycle | Scope | Purpose |
|---|---|---|
| `C0` | Historical fixed-cluster reference | Preserves and regenerates the original fixed-cluster characterization workflow. |
| `C1` | Provider-backed baseline | Validates the provider-backed provisioning, deployment, measurement, and post-processing path end to end. |
| `C2` | Resource-capacity variation | Evaluates how worker-node CPU and memory capacity affect schedulability and benchmark behavior. |
| `C3` | Node-count variation | Evaluates how worker-node count affects placement, capacity distribution, and benchmark behavior. |
| `C4` | Controlled placement variation | Evaluates explicitly configured LocalAI server and RPC-worker placement layouts. |
| `C5` | Latency injection | Evaluates LocalAI worker-mode behavior under controlled network-latency profiles. |
| `C6` | Multi-tenancy | Evaluates coexistence scenarios with multiple LocalAI tenant-like deployments. |
| `C7` | Default scheduler baseline | Observes Kubernetes default scheduling for distributed LocalAI tenant workloads without hard pod placement controls. |
| `C8` | Resource-aware scheduler campaign | Compares Kubernetes default scheduling with a load-aware custom scheduler under paired resource-aware scenarios. |
| `C9` | Network-aware scheduler campaign | Compares Kubernetes default scheduling, resource-aware custom scheduling, and resource plus network-aware custom scheduling across 14 logical scenarios and 42 variants. |

Unsupported outcomes are treated as evidence when they expose declared experimental boundaries rather than accidental failures.

---

## Scheduler Evaluation Tracks

### C7: Default Kubernetes Scheduler Baseline

C7 captures how the native Kubernetes scheduler places distributed LocalAI tenant workloads when custom scheduler logic and hard pod placement controls are intentionally absent. It preserves pod-to-node assignment, tenant distribution, scheduler events, readiness evidence, performance measurements, and unsupported outcomes.

### C8: Resource-Aware Scheduler Campaign

C8 compares Kubernetes default scheduling with a second scheduler named `scheduler-plugins-scheduler` using the `LoadAwareResourcesBalancedAllocation` plugin. The campaign keeps workload shape, infrastructure, telemetry priming, deployment labels, redeployment policy, and measurement boundaries aligned across each pair so that scheduler mode remains the main independent variable.

### C9: Network-Aware Scheduler Campaign

C9 extends scheduler evaluation to resource plus network-aware placement. Each logical scenario is represented by three scheduler variants:

| Variant family | Scheduler behavior |
|---|---|
| `NA_DEFAULT_*` | Kubernetes default scheduler. |
| `NA_LOADAWARE_*` | Custom scheduler with `LoadAwareResourcesBalancedAllocation`. |
| `NA_NETAWARE_*` | Custom scheduler with `LoadAwareResourcesBalancedAllocation` and `NetworkAwareLocalAi`. |

The updated C9 campaign contains 14 logical scenarios and 42 variants. It includes `L0`, `L1`, `L2`, and `L3_INTER_GROUP_EXTREME` latency conditions, with high-latency L3 scenarios used to make network-distance effects more visible during placement and performance analysis.

C9 uses gateway-routed traffic, Istio evidence, `mon-agent` annotations, Mentat telemetry, controlled latency profiles, telemetry priming, controlled redeployment, scheduler evidence, and `cluster-lens` placement snapshots. The campaign does not assume that network-aware scheduling always improves response time. It evaluates whether placement decisions change when resource, traffic, and network-cost signals are available, and whether those placement decisions correlate with measured behavior.

---

## C9 Evidence Chain

The C9 evidence model is built around the following chain:

| Stage | Evidence source |
|---|---|
| Gateway-routed tenant traffic reaches the LocalAI master. | Istio Gateway and VirtualService configuration. |
| Gateway traffic becomes a scheduler-facing application signal. | Istio metrics consumed by `mon-agent`. |
| Runtime telemetry is exposed as Kubernetes annotations. | `mon-agent` node and deployment annotations. |
| Inter-node network cost is measured. | Mentat latency, packet-loss, and bandwidth metrics. |
| LocalAI tenant and role relationships are identifiable. | `group`, `app`, and `role` labels. |
| Scheduler mode is isolated across comparable variants. | Default scheduler, load-aware scheduler, and network-aware scheduler profiles. |
| Placement is observed after scheduling decisions. | Scheduler evidence, Kubernetes snapshots, and `cluster-lens` artifacts. |
| Results are interpreted with both placement and performance evidence. | Diagnosis, reporting, completion gate, and freeze outputs. |

`cluster-lens` is used as an evidence source, not as a replacement for Kubernetes state capture. The benchmark suite enriches `cluster-lens` snapshots with Kubernetes pod, deployment, and node data so placement can be compared across scheduler modes.

---

## Repository Structure

| Path | Responsibility |
|---|---|
| `config/` | Cycle descriptors, scenario indexes, infrastructure profiles, provider bindings, scheduler profiles, latency profiles, monitoring profiles, diagnosis profiles, reporting profiles, completion-gate profiles, freeze profiles, and schema files. |
| `infra/k8s/` | Kubernetes manifests, Kustomize bases, overlays, and compositions for LocalAI deployments and scheduler-oriented scenarios. |
| `load-tests/` | Locust workload definitions for LocalAI-compatible API traffic. |
| `scripts/` | Automation for provider integration, validation, deployment, workload execution, observability capture, scheduler evidence, diagnosis, reporting, completion gates, freeze, and maintenance operations. |
| `scripts/observability/cluster-lens/` | Placement-evidence capture utilities for `cluster-lens` snapshots and Kubernetes-enriched placement summaries. |
| `docs/runbooks/` | Operational documentation for repository structure, configuration taxonomy, cycle execution, artifact interpretation, cleanup, regeneration, and troubleshooting. |
| `results/` | Generated benchmark, observability, scheduler, diagnosis, reporting, completion-gate, freeze, and reporting-site artifacts. |
| `.github/workflows/` | Automation for generated reporting-site publication and related repository workflows. |

The `results/` directory is generated output. It can become stale after source configuration, manifests, scripts, scheduler profiles, or observability integrations change.

---

## Configuration Model

The suite is configuration-first. Reproducible behavior is encoded in JSON and YAML artifacts instead of implicit shell state.

| Configuration area | Examples |
|---|---|
| Experimental cycles | Cycle descriptors for `C0` through `C9`. |
| Scenarios | Baseline, resource variation, node-count variation, placement variation, latency injection, multi-tenancy, default-scheduler, resource-aware, and network-aware scenarios. |
| Infrastructure profiles | Control-plane count, worker-node count, CPU, memory, storage, management-node policy, and provider lifecycle behavior. |
| Provider bindings | Mapping between infrastructure profiles and `proxmox-k3s` provider configuration. |
| Scheduler profiles | Scheduler names, plugin policy, management-node tolerations, environment policy, manifest expectations, and scheduler-evidence settings. |
| Monitoring profiles | `mon-agent`, Kubernetes state capture, minimal observability, namespace selection, and annotation requirements. |
| Network observability profiles | Mentat telemetry, inter-node latency, packet loss, bandwidth, and scheduler-facing network annotation requirements. |
| Cluster-lens profiles | Placement snapshot policy, capture stages, output files, and profile schema. |
| Latency profiles | Zero-latency controls, edge-like profiles, and annotation-controlled inter-group latency matrices. |
| Post-processing profiles | Technical diagnosis, reporting, completion gate, freeze, and reporting-site metadata. |

This structure allows each cycle to remain reviewable and reproducible while keeping provider-specific local inputs separate from reusable repository files.

---

## Evidence and Artifact Model

The suite separates measurement, operational evidence, interpretation, and archival outputs.

| Evidence layer | Description |
|---|---|
| Measurement artifacts | Response time, throughput, request failures, and load-test statistics. |
| Cluster-side artifacts | Kubernetes pods, deployments, nodes, events, readiness, scheduling evidence, and resource snapshots. |
| Scheduler evidence | Scheduler names, pod-to-node assignment, placement classification, failed scheduling evidence, and scheduler-decision context. |
| Annotation evidence | Runtime CPU, memory, traffic, RPS, and network annotations on nodes and deployments. |
| Network telemetry evidence | Mentat latency, packet-loss, bandwidth, and scheduler-facing annotation matrices. |
| Gateway-routing evidence | Istio Gateway, VirtualService, service routing, and gateway-routed benchmark target validation. |
| Cluster-lens placement evidence | Raw `cluster-lens` snapshots, Kubernetes-enriched pod/deployment/node snapshots, placement summaries, and placement signatures. |
| Technical diagnosis | Machine-readable and human-readable interpretation of benchmark, scheduler, infrastructure, telemetry, and observability evidence. |
| Reporting | Cycle-scoped summaries, charts, tables, scenario interpretation, and artifact links. |
| Completion gate | Validation of required evidence and accepted completion states. |
| Freeze outputs | Reproducible snapshots of configuration, evidence, reports, and metadata for completed cycles. |

This separation keeps measured performance distinct from diagnostic interpretation and artifact-completeness validation.

---

## Provider-Backed Infrastructure

Provider-backed cycles integrate with an external `proxmox-k3s` workflow. The provider creates, validates, exposes, and deletes K3s clusters on Proxmox. This repository selects infrastructure profiles, resolves provider bindings, validates cluster state, deploys LocalAI workloads, collects benchmark evidence, and produces post-processing artifacts.

The provider-backed model supports reusable templates, local provider configuration, generated kubeconfig paths, management-node policies, worker-node capacity profiles, expected addon validation, and lifecycle policies for cluster reuse or deletion.

For C9, the provider-backed infrastructure profile expects the addon toolchain required for monitoring, annotation generation, inter-node telemetry, gateway routing, custom scheduling, and placement inspection. The management node uses a dedicated management taint policy while benchmark workloads remain isolated on worker nodes according to the active scenario and scheduler behavior.

Environment-specific provider inputs, generated kubeconfig files, local credentials, tokens, endpoints, and machine-specific paths are local artifacts and are excluded from version control through repository ignore rules.

---

## Monitoring, Telemetry, and Placement

The benchmark suite uses telemetry to make scheduler evaluations evidence-driven.

| Component | Role |
|---|---|
| `mon-agent` | Converts observability data into Kubernetes annotations consumed by scheduler plugins and diagnosis tooling. |
| Mentat | Exposes inter-node latency, packet-loss, and bandwidth telemetry. |
| Istio | Provides the gateway-routed traffic path used by C9 scenarios. |
| `cluster-lens` | Provides visual and machine-readable cluster topology and placement snapshots. |
| Scheduler plugins | Provide resource-aware and LocalAI-specific network-aware scheduling behavior. |

The main scheduler-facing signal families are resource usage, gateway traffic, tenant traffic, inter-node latency, packet loss, bandwidth, LocalAI tenant labels, LocalAI role labels, and scheduler names. C9 captures those signals before and after controlled redeployment so the resulting placement can be compared across scheduler modes.

---

## Reporting and Results

Generated artifacts are organized under cycle-scoped directories in `results/`. They may include benchmark measurements, cluster snapshots, scheduler evidence, annotation evidence, placement summaries, technical diagnosis, reports, completion-gate outputs, freeze manifests, and static reporting-site files.

Reporting identifiers use compact cycle-scoped prefixes such as `REP_C0`, `REP_C8`, and `REP_C9`. The identifier is metadata; the report title describes the campaign and evidence scope.

For C9, the cycle report exposes the latency-profile context, cluster-lens placement evidence summary, and tenant-level placement details used to interpret scheduler behavior. Topology-level fields describe whether the Kubernetes cluster view remained stable across comparable variants; placement fields describe whether LocalAI master and worker pods were assigned to different nodes under `DEFAULT`, `LOADAWARE`, and `NETAWARE` scheduler modes.

Artifacts in `results/` should be interpreted as evidence for the repository state that produced them. When source configuration, scripts, manifests, observability integrations, or scheduler profiles change, results should be regenerated before being treated as current evidence.

---

## Documentation

Operational documentation is maintained under `docs/runbooks/`.

The runbooks cover repository structure, local tooling assumptions, access and local configuration, provider lifecycle integration, cycle taxonomy, LocalAI topology and placement, load generation, observability, scheduler evidence, diagnosis, reporting, completion gate, freeze, cleanup, regeneration, troubleshooting, and reference material.

This README is a high-level project map. Detailed operational procedures, including shell-specific workflows, are intentionally kept in the runbooks.

---

## Security and Local Artifacts

The repository distinguishes reusable project files from environment-specific local artifacts.

Ignored local material includes fixed-cluster kubeconfig files, provider-generated kubeconfig files, provider-local configuration, credentials, tokens, endpoint material, machine-specific paths, Python bytecode, interpreter caches, and transient runtime outputs.

Files under ignored local paths may contain infrastructure endpoints, credentials, tokens, IP ranges, generated access material, or machine-specific paths. They should remain local to the execution environment.

---

## Design Principles

The project follows these principles:

1. **Configuration-first execution**: benchmark behavior is encoded through explicit profiles and manifests.
2. **Explicit cluster access**: Kubernetes operations are designed around explicit kubeconfig resolution.
3. **Provider separation**: infrastructure provisioning remains separate from benchmark logic.
4. **Reproducible artifacts**: generated evidence is stored under deterministic cycle-scoped locations.
5. **Unsupported outcomes as evidence**: expected capacity, scheduling, topology, rollout, latency, and telemetry limits are preserved instead of hidden.
6. **Scheduler comparison integrity**: C7, C8, and C9 isolate scheduler behavior according to their intended comparison model.
7. **Placement-performance interpretation**: scheduler results are interpreted with both measured performance and observed pod placement.
8. **Telemetry-aware scheduling**: resource, traffic, and network annotations are treated as first-class scheduler-facing evidence.
9. **Cross-shell parity**: supported PowerShell and Bash entry points are kept aligned in the operational layer.
10. **Environment neutrality**: reusable benchmark logic is separated from local credentials, local node names, local provider files, and generated access material.
11. **Regenerable results**: generated artifacts are not treated as source of truth after the repository model changes.
12. **Documentation separation**: high-level repository orientation belongs in this README, while operational procedures belong in runbooks.

---

## Technology Stack

| Area | Technologies and artifacts |
|---|---|
| Container orchestration | Kubernetes, K3s, Kustomize, LocalAI server and RPC-worker deployments. |
| Infrastructure provisioning | Proxmox/K3s provider integration through `proxmox-k3s` profiles and bindings. |
| Load generation | Locust workloads targeting LocalAI-compatible API endpoints. |
| Automation | Python, PowerShell, Bash. |
| Monitoring and annotations | Kubernetes snapshots, minimal observability, `mon-agent`, annotation evidence, and scheduler-decision evidence. |
| Network telemetry | Mentat inter-node latency, packet-loss, and bandwidth metrics. |
| Gateway routing | Istio Gateway and VirtualService resources. |
| Placement inspection | `cluster-lens` snapshots and Kubernetes-enriched placement signatures. |
| Scheduling | Kubernetes default scheduler, `scheduler-plugins-scheduler`, `LoadAwareResourcesBalancedAllocation`, and `NetworkAwareLocalAi`. |
| Reporting | Markdown reports, static HTML reports, charts, manifests, completion summaries, and freeze metadata. |
| Publication support | GitHub workflow support for generated reporting artifacts. |

---

## Current Project State

The repository currently provides a complete benchmark model from the historical fixed-cluster reference through provider-backed scheduler campaigns. The current scheduler-focused scope includes:

- C7 default Kubernetes scheduler baseline evidence;
- C8 paired default versus load-aware scheduler evidence;
- C9 three-way default, load-aware, and resource plus network-aware scheduler evidence;
- C9 `cluster-lens` capture support for placement inspection;
- C9 `L3_INTER_GROUP_EXTREME` scenarios for higher-latency network-aware evaluation;
- diagnosis, reporting, completion-gate, freeze, and reporting-site support for the current cycle taxonomy.

The suite is suitable for controlled experimentation, artifact inspection, report review, and further extensions of LocalAI worker-mode scheduling methodology.
