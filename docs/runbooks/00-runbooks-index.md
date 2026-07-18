# Runbooks Index

## Purpose

This runbook set provides the operational documentation required to execute, regenerate, validate, diagnose, report, and archive the complete LocalAI worker-mode benchmark pipeline.

The documentation describes the current operational model of the benchmark suite. It is an execution reference for operators who need to reproduce fixed-cluster evidence, provider-backed baseline evidence, comparative campaign evidence, default-scheduler baseline evidence, paired resource-aware scheduler evidence, and network-aware scheduler evidence from explicit configuration profiles.

The benchmark workflow is organized around the following execution tracks:

1. a historical fixed-cluster execution track, identified as `C0`;
2. provider-backed execution tracks, identified as `C1` through `C6`, where Kubernetes/K3s clusters are created, reused, validated, or deleted through the `proxmox-k3s` provider workflow;
3. a default-scheduler baseline campaign, identified as `C7`, where Kubernetes is intentionally left free to place tenant-scoped LocalAI workloads without hard pod placement controls;
4. a resource-aware scheduler campaign, identified as `C8`, where Kubernetes default scheduling is compared with a resource-aware custom scheduler under paired `L0_NONE` scenarios;
5. a network-aware scheduler campaign, identified as `C9`, where Kubernetes default scheduling, resource-aware custom scheduling, and resource plus network-aware custom scheduling are compared under gateway-routed, latency-differentiated LocalAI scenarios, with placement evidence captured through cluster-lens and Kubernetes snapshots.

---

## Documentation Principles

The runbook set follows the principles below.

1. **Reproducibility first**: each execution path must be driven by explicit configuration profiles, deterministic script entry points, and clearly defined output locations.
2. **Explicit configuration**: cluster access, infrastructure profiles, provider bindings, placement profiles, latency profiles, tenancy profiles, benchmark profiles, scheduler profiles, monitoring profiles, diagnosis profiles, reporting profiles, completion gates, and freeze profiles are first-class configuration artifacts.
3. **No implicit cluster context**: Kubernetes operations must use the intended `kubeconfig` explicitly instead of relying on the local default context.
4. **Regenerable outputs**: files under `results/` are generated artifacts and may be removed and regenerated from source profiles, manifests, workloads, and scripts.
5. **Cross-shell parity**: operational commands must provide Windows PowerShell and Bash variants where both shells are supported.
6. **Unsupported scenarios are evidence**: non-schedulable, resource-constrained, telemetry-constrained, rollout-constrained, or operationally unsupported scenarios must be preserved when they match the active experimental design.
7. **Minimal hard-coded infrastructure assumptions**: node names, provider paths, local credentials, provider-local cluster manifests, and environment-specific values must remain local configuration or explicit profile data.
8. **Clean separation of responsibilities**: `proxmox-k3s` provisions and manages K3s clusters on Proxmox; the benchmark suite selects profiles, invokes the provider workflow, validates the cluster, deploys LocalAI, executes workloads, and generates post-processing artifacts.
9. **Default-scheduler evidence integrity**: C7 must not introduce hard pod placement controls or custom scheduler behavior. Its value depends on observing the placement chosen by Kubernetes.
10. **Resource-aware scheduler integrity**: C8 must compare paired default/load-aware scenarios while holding workload, infrastructure, monitoring, labels, telemetry priming, rescheduling policy, and measurement boundaries constant.
11. **Network-aware scheduler integrity**: C9 must compare default, load-aware, and network-aware variants while preserving gateway-routed traffic, `mon-agent` annotations, Mentat inter-node telemetry, Istio evidence, cluster-lens placement evidence, controlled latency profiles, and telemetry-primed redeployment boundaries.
12. **Documentation neutrality**: runbooks must describe the operational benchmark suite and must not depend on private organizational context, external planning context, or local operator identity.

---

## Repository Root Assumption

All runbooks assume that commands are executed from the repository root:

```text
localai-worker-mode-benchmark-suite/
```

Relative paths are resolved from that directory unless a runbook explicitly states otherwise.

---

## Canonical Namespaces

The canonical single-tenant benchmark namespace is:

```text
localai-benchmark
```

Default-scheduler and resource-aware scheduler scenarios may use tenant-scoped namespaces such as:

```text
genai-tenant-a
genai-tenant-b
genai-tenant-c
```

C8 and C9 also use management namespaces such as:

```text
observability
scheduler-plugins
scheduler-validation
istio-system
chaos-mesh
```

The active runtime configuration determines the benchmark target. Do not infer the benchmark target only from the namespace name.

---

## Execution Tracks

| Track | Cycle Scope | Infrastructure Model | Main Purpose |
|---|---|---|---|
| Historical fixed-cluster execution | `C0` | Externally available Kubernetes/K3s cluster accessed through a fixed kubeconfig | Regenerate the historical characterization workflow, including baseline, exploratory validation, pilot sweeps, consolidated pilot, diagnosis, reporting, completion gate, and freeze artifacts. |
| Provider-backed baseline | `C1` | Cluster generated or reused through infrastructure profiles and `proxmox-k3s` provider bindings | Validate the provider-backed execution path end to end. |
| Provider-backed comparative campaigns | `C2`-`C6` | Provider-backed clusters and controlled scenario variants | Evaluate resource capacity, node count, controlled placement, latency injection, and multi-tenancy. |
| Default-scheduler baseline | `C7` | Provider-backed clusters with default Kubernetes scheduling and no hard pod placement controls | Evaluate how Kubernetes places distributed LocalAI tenant workloads under tenant-count, node-count, latency, and traffic variation. |
| Resource-aware scheduler | `C8` | Provider-backed clusters with monitoring, `mon-agent`, controlled redeployment, and optional custom second scheduler | Compare Kubernetes default scheduling against a load-aware resource scheduler using paired `L0_NONE` LocalAI worker-mode scenarios. |
| Network-aware scheduler campaign | `C9` | Provider-backed four-worker clusters with monitoring, `mon-agent`, cluster-lens, Mentat, Istio, custom scheduler, telemetry priming, controlled placement capture, and controlled redeployment | Compare default, load-aware, and resource plus network-aware scheduling under gateway-routed traffic, differentiated inter-node latency, and explicit placement evidence. |

The tracks must not be conflated. `C0` is fixed-cluster evidence. `C1` through `C9` are provider-backed cycles or campaigns. `C7` is the default-scheduler evidence baseline. `C8` is the paired resource-aware scheduler campaign. `C9` is the three-way network-aware scheduler campaign.

---

## Cycle Taxonomy

| Cycle | Name | Operational Purpose |
|---|---|---|
| `C0` | Historical fixed-cluster cycle | Re-executes the complete historical benchmark workflow on an already reachable cluster. |
| `C1` | Provider-backed baseline cycle | Validates provisioning, cluster validation, LocalAI deployment, benchmark execution, diagnosis, reporting, completion gate, and freeze. |
| `C2` | Resource variation campaign | Evaluates how worker-node CPU and memory capacity affect schedulability and benchmark behavior. |
| `C3` | Node-count variation campaign | Evaluates how the number of provider-backed worker nodes affects placement, resource distribution, and benchmark behavior. |
| `C4` | Placement variation campaign | Evaluates controlled LocalAI server and RPC-worker placement strategies. |
| `C5` | Latency injection campaign | Evaluates the impact of controlled network-latency profiles on LocalAI worker-mode execution. |
| `C6` | Multi-tenancy campaign | Evaluates coexistence scenarios with multiple LocalAI application clusters or tenant-like deployments on the same infrastructure. |
| `C7` | Default Kubernetes scheduler baseline campaign | Evaluates default scheduler placement decisions under tenant-count, worker-node-count, latency-profile, traffic-profile, and model-mix variation. |
| `C8` | Resource-aware scheduler campaign | Compares Kubernetes default scheduling with a load-aware custom scheduler using paired resource-aware `L0_NONE` scenarios. |
| `C9` | Network-aware scheduler campaign | Compares Kubernetes default scheduling, resource-aware custom scheduling, and resource plus network-aware custom scheduling across 14 logical scenarios and 42 variants, including `L3_INTER_GROUP_EXTREME` scenarios and cluster-lens placement evidence. |

---

## Recommended Runbook Set

| File | Purpose |
|---|---|
| `00-runbooks-index.md` | Provides the entry point, documentation principles, execution tracks, cycle taxonomy, and recommended reading order. |
| `01-execution-model-and-repository-map.md` | Explains the end-to-end execution model, repository layout, major configuration areas, and artifact flow. |
| `02-local-environment-and-tooling.md` | Defines local workstation requirements, required tools, shell assumptions, Python/Locust setup, and local validation checks. |
| `03-access-secrets-and-local-configuration.md` | Documents kubeconfig handling, VPN-dependent access, local provider configuration, ignored files, and secret-management rules. |
| `04-proxmox-k3s-provider-lifecycle.md` | Describes how the benchmark suite uses `proxmox-k3s` to create, reuse, inspect, and delete K3s clusters. |
| `05-configuration-model-and-cycle-taxonomy.md` | Describes cycle profiles, infrastructure profiles, provider bindings, placement profiles, latency profiles, tenancy profiles, scheduler profiles, monitoring profiles, validation profiles, reporting profiles, completion gates, and freeze profiles. |
| `06-fixed-cluster-c0-execution.md` | Documents the full C0 regeneration workflow on a fixed cluster. |
| `07-provider-backed-c1-baseline-execution.md` | Documents the C1 provider-backed baseline workflow. |
| `08-provider-backed-c2-c6-campaign-execution.md` | Documents the comparative provider-backed campaign workflow for C2 through C6. |
| `09-default-scheduler-c7-baseline-execution.md` | Documents the C7 default Kubernetes scheduler baseline campaign. |
| `10-resource-aware-scheduler-c8-execution.md` | Documents the C8 resource-aware scheduler campaign between Kubernetes default scheduling and the load-aware custom scheduler. |
| `11-network-aware-scheduler-c9-execution.md` | Documents the C9 network-aware scheduler campaign comparing default, load-aware, and resource plus network-aware scheduler modes under gateway-routed, latency-differentiated scenarios, including cluster-lens placement capture. |
| `12-localai-deployment-topologies-and-placement.md` | Explains LocalAI server and RPC-worker deployment topologies, worker mode, model sharding assumptions, Kubernetes services, placement profiles, tenant compositions, default-scheduler compositions, resource-aware-scheduler compositions, and network-aware scheduler compositions. |
| `13-load-generation-observability-and-artifacts.md` | Documents Locust workload execution, benchmark phases, multi-tenant load generation, gateway-routed C9 traffic, client-side metrics, cluster-side evidence, minimal observability, scheduler evidence, mon-agent evidence, cluster-lens placement evidence, Mentat evidence, Istio evidence, and artifact layout. |
| `14-diagnosis-reporting-completion-gate-and-freeze.md` | Documents technical diagnosis, report generation, reporting-site generation, completion-gate evaluation, freeze manifests, and completion states. |
| `15-results-cleanup-and-full-regeneration.md` | Documents how to remove generated results safely and regenerate the full artifact set in the correct order. |
| `16-troubleshooting-and-recovery.md` | Provides recovery procedures for cluster access, provisioning, deployment, scheduling, latency, Locust, monitoring, resource-aware-scheduler, network-aware telemetry, reporting, completion, freeze, and cleanup failures. |
| `17-command-reference.md` | Provides a compact PowerShell/Bash command reference for common execution, validation, reporting, cleanup, and recovery tasks. |

---

## Recommended Reading Order

For a first complete execution, read the runbooks in this order:

1. `00-runbooks-index.md`
2. `01-execution-model-and-repository-map.md`
3. `02-local-environment-and-tooling.md`
4. `03-access-secrets-and-local-configuration.md`
5. `05-configuration-model-and-cycle-taxonomy.md`
6. `15-results-cleanup-and-full-regeneration.md`
7. `06-fixed-cluster-c0-execution.md`
8. `04-proxmox-k3s-provider-lifecycle.md`
9. `07-provider-backed-c1-baseline-execution.md`
10. `08-provider-backed-c2-c6-campaign-execution.md`
11. `09-default-scheduler-c7-baseline-execution.md`
12. `10-resource-aware-scheduler-c8-execution.md`
13. `11-network-aware-scheduler-c9-execution.md`
14. `12-localai-deployment-topologies-and-placement.md`
15. `13-load-generation-observability-and-artifacts.md`
16. `14-diagnosis-reporting-completion-gate-and-freeze.md`
17. `16-troubleshooting-and-recovery.md`
18. `17-command-reference.md`

For repeated execution after the operator already understands the model, the minimum reading path is:

1. the cycle-specific runbook for the target cycle;
2. `04-proxmox-k3s-provider-lifecycle.md` for provider-backed cycles;
3. `14-diagnosis-reporting-completion-gate-and-freeze.md` for post-processing;
4. `16-troubleshooting-and-recovery.md` if a failure occurs.

---

## Full Regeneration Order

A complete regeneration should follow this order:

| Order | Runbook | Outcome |
|---:|---|---|
| 1 | `15-results-cleanup-and-full-regeneration.md` | Current generated artifacts are archived or removed according to the selected cleanup policy. |
| 2 | `06-fixed-cluster-c0-execution.md` | C0 historical fixed-cluster evidence is regenerated. |
| 3 | `07-provider-backed-c1-baseline-execution.md` | C1 provider-backed baseline evidence is regenerated. |
| 4 | `08-provider-backed-c2-c6-campaign-execution.md` | C2-C6 comparative provider-backed campaign artifacts are regenerated. |
| 5 | `09-default-scheduler-c7-baseline-execution.md` | C7 default-scheduler baseline artifacts are regenerated. |
| 6 | `10-resource-aware-scheduler-c8-execution.md` | C8 paired resource-aware scheduler artifacts are regenerated. |
| 7 | `11-network-aware-scheduler-c9-execution.md` | C9 network-aware scheduler artifacts are regenerated. |
| 8 | `14-diagnosis-reporting-completion-gate-and-freeze.md` | Post-processing artifacts are regenerated or inspected across cycles. |
| 9 | `15-results-cleanup-and-full-regeneration.md` | Final artifact coverage and reporting-site state are verified. |

---

## Results Handling Policy

The `results/` directory contains generated outputs. Treat every artifact as evidence for the repository state, configuration profiles, local provider inputs, and runtime environment that produced it.

If source configuration, scripts, manifests, scheduler profiles, or observability integrations changed after an execution, regenerate the affected cycle before treating those artifacts as current evidence. If the artifacts were generated from the current repository state, use the associated manifests, reporting metadata, completion-gate output, and freeze metadata to confirm that interpretation.

Generated result roots may be removed and regenerated when:

- the source profiles have changed;
- the Kubernetes manifests have changed;
- the benchmark scripts have changed;
- the diagnosis/reporting/completion/freeze logic has changed;
- a clean final artifact set is required.

Do not manually edit generated benchmark, diagnosis, reporting, completion-gate, or freeze artifacts. Regenerate them from source configuration instead.

---

## Completion States

| State | Meaning |
|---|---|
| `supported` | The scenario or cycle executed sufficiently for benchmark and post-processing evidence. |
| `unsupported` | The scenario exposed a declared operational boundary such as resource pressure, schedulability failure, cluster instability, annotation failure, or workload infeasibility. |
| `failed` | The run failed because of an unexpected tooling, configuration, or execution error that must be corrected before interpreting the run as evidence. |
| `partial` | Some artifacts exist, but the cycle cannot yet be treated as complete evidence. |
| `frozen` | The relevant latest artifacts have been snapshotted under the configured frozen artifact root. |

Unsupported scenarios must be interpreted in the context of the active cycle design. They can be valid experimental outcomes when the scenario tests the operational boundary of a workload, placement policy, resource profile, latency profile, tenancy profile, default-scheduler behavior, or resource-aware scheduler behavior, or network-aware telemetry behavior.

---

## Safety Rules

1. Do not commit provider-local YAML files, kubeconfigs, credentials, `.env` files, generated logs with private values, or `__pycache__` directories.
2. Do not run destructive provider cleanup unless the intended lifecycle policy requires deletion and the command explicitly confirms it.
3. Do not mix artifact sets produced by different source versions when producing final reports.
4. Do not interpret a dry run as benchmark evidence.
5. Do not interpret a single direct variant execution as a complete campaign result.
6. Do not modify root `README.md` or official documentation as part of runtime execution.
7. Do not edit generated artifacts under `results/`; regenerate them.
8. Do not introduce hard placement controls in C7 or C8 scheduler-observation paths.
9. Do not use network-aware scheduler claims for C8; network-aware interpretation belongs to C9.
10. Do not interpret C9 without validating gateway-routed traffic, `mon-agent` annotations, Mentat evidence, cluster-lens placement evidence, and scheduler decision evidence.

---

## Terminology

| Term | Meaning |
|---|---|
| Fixed-cluster execution | Execution against an already available Kubernetes/K3s cluster. |
| Provider-backed execution | Execution where cluster lifecycle is controlled through provider profiles and `proxmox-k3s`. |
| Campaign | A cycle composed of multiple variants. |
| Variant | A concrete scenario-profile execution inside a campaign. |
| Logical scenario | The workload/infrastructure/model/traffic condition shared by a C8 default/load-aware pair or a C9 default/load-aware/network-aware triplet. |
| C8 scheduler pair | A default-scheduler C8 variant and a load-aware C8 variant sharing the same logical scenario. |
| C9 scheduler triplet | A default-scheduler C9 variant, a load-aware C9 variant, and a network-aware C9 variant sharing the same logical scenario. |
| mon-agent | Monitoring agent that reads Prometheus metrics and writes runtime annotations to nodes and deployments. |
| Runtime annotation | Kubernetes annotation such as `cpu-usage`, `memory-usage`, `traffic.<peer-workload>`, or `network-latency.<node>` used as scheduler evidence or validation input. |
| Mentat | Inter-node network observability component used to collect latency, packet loss, and bandwidth evidence for C9. |
| cluster-lens | Provider-installed topology and placement viewer captured by the benchmark suite as read-only placement evidence for C9. |
| Gateway-routed traffic | Benchmark traffic routed through Istio Gateway and VirtualService so that tenant ingress intensity can be captured as scheduler evidence. |
| Controlled redeployment | A rollout restart used to create a new scheduling decision after runtime telemetry has been collected. |
| Completion gate | A post-processing validation that evaluates whether the expected evidence set exists and is consistent. |
| Freeze | A reproducible snapshot of selected latest artifacts for a cycle or campaign. |

---

## Next Runbook

Continue with:

```text
docs/runbooks/01-execution-model-and-repository-map.md
```
