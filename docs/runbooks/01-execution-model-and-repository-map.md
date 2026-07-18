# Execution Model and Repository Map

## Purpose

This runbook explains the execution architecture and repository layout used by the LocalAI worker-mode benchmark suite.

It is not a step-by-step execution procedure. Its purpose is to provide the conceptual map required before using the execution runbooks that follow. It describes:

1. the execution tracks supported by the repository;
2. the responsibility boundaries between the benchmark suite and the `proxmox-k3s` provider;
3. the configuration model that drives each execution cycle;
4. the relationship between Kubernetes manifests, benchmark scripts, diagnosis, reporting, completion gates, freeze artifacts, and generated results;
5. the repository directories that are relevant when executing or regenerating the full benchmark workflow.

---

## Repository Root Assumption

All paths in this runbook are relative to the repository root:

```text
localai-worker-mode-benchmark-suite/
```

Before following the operational runbooks, open a shell in the repository root.

### Windows PowerShell

```powershell
Get-ChildItem
```

### Bash

```bash
ls
```

A valid repository root contains at least the following entries:

```text
config/
docs/
infra/
load-tests/
scripts/
requirements.txt
```

The `results/` directory may be present, empty, partially populated, or fully populated depending on whether benchmark artifacts have already been generated.

---

## High-Level Execution Architecture

The benchmark suite is organized around a configuration-driven execution model.

At a high level, each benchmark execution follows this logical flow:

```text
Configuration profiles
→ infrastructure preparation
→ cluster validation
→ LocalAI deployment
→ smoke validation
→ load generation
→ observability and artifact collection
→ technical diagnosis
→ reporting
→ completion gate
→ freeze
```

The pipeline is designed so that infrastructure, application topology, workload generation, diagnosis, reporting, and archiving are not implicit assumptions. They are represented as explicit configuration files and script entry points.

The intended model is:

```text
Declare the cycle
→ resolve the required profiles
→ prepare or access the cluster
→ deploy the application topology
→ execute the benchmark
→ collect evidence
→ generate interpretation artifacts
→ archive the cycle
```

---

## Supported Execution Tracks

The repository supports two main execution tracks.

| Track | Cycle range | Cluster source | Primary purpose |
|---|---:|---|---|
| Fixed-cluster historical execution | `C0` | Existing Kubernetes/K3s cluster accessed through a provided kubeconfig | Reproduce the original historical characterization workflow and its benchmark families. |
| Provider-backed execution | `C1`-`C9` | K3s cluster created or managed through the `proxmox-k3s` provider workflow | Execute the provider-backed baseline, controlled comparative campaigns, the default-scheduler baseline, the resource-aware scheduler evaluation, and the network-aware scheduler campaign where infrastructure and telemetry are part of the experimental configuration. |

These tracks must be interpreted separately. A fixed-cluster result and a provider-backed result may both be valid, but they are not methodologically equivalent unless their infrastructure assumptions are explicitly compared.

---

## Fixed-Cluster Historical Track

The fixed-cluster track is identified as `C0`.

It represents the execution path where a Kubernetes/K3s cluster already exists and is accessed through a local kubeconfig. The benchmark suite does not provision this cluster. It only validates access, creates or validates the application namespace, deploys LocalAI, executes workloads, and generates post-processing artifacts.

The canonical application namespace is:

```text
localai-benchmark
```

For `C0`, the namespace must not be assumed to exist. The execution procedure must create or validate it explicitly before deploying LocalAI resources.

The fixed-cluster track is expected to regenerate the historical benchmark families, not only the consolidated pilot. This includes the baseline and the historical pilot families represented under:

```text
config/scenarios/baseline/
config/scenarios/pilot/
```

The dedicated runbook for this track is:

```text
06-fixed-cluster-c0-execution.md
```

---

## Provider-Backed Execution Track

The provider-backed track is identified by cycles `C1` through `C9`.

In this track, the benchmark suite uses declared infrastructure profiles and provider bindings to prepare or reuse K3s clusters before deploying LocalAI and executing the benchmark workload.

The provider-backed track is built around the following responsibility split:

| Component | Responsibility |
|---|---|
| `proxmox-k3s` | Create, manage, retrieve kubeconfig for, and delete K3s clusters on Proxmox according to a provider-specific YAML configuration. |
| Benchmark suite | Select the cycle, resolve infrastructure and provider profiles, invoke the provider workflow, validate the generated cluster, deploy LocalAI, execute workloads, collect artifacts, generate diagnosis/reporting/completion evidence, and freeze the cycle. |

The provider-backed track is not a direct replacement for `C0`. It is a separate execution model in which infrastructure becomes part of the benchmark configuration.

---

## Provider-Backed Cycle Taxonomy

The provider-backed cycles are organized as follows:

| Cycle | Name | Primary varied dimension |
|---|---|---|
| `C1` | Provider-backed baseline | None; validates the provider-backed baseline workflow. |
| `C2` | Resource variation | Worker-node CPU and memory capacity. |
| `C3` | Node-count variation | Number of provider worker nodes. |
| `C4` | Placement variation | LocalAI server and worker placement profile. |
| `C5` | Latency injection | Controlled network-latency profile. |
| `C6` | Multi-tenancy | Tenant topology, co-tenant model mix, and co-tenant placement. |
| `C7` | Default Kubernetes scheduler baseline | Tenant count, worker-node count, latency profile, tenant traffic profile, model mix, and observed default-scheduler placement. |
| `C8` | Resource-aware scheduler | Scheduler mode under paired `L0_NONE` scenarios: Kubernetes default scheduling versus load-aware resource scheduling. |

`C2` through `C6` are controlled comparative campaigns: each one is expected to vary one primary dimension while keeping the remaining relevant dimensions fixed. `C7` is intentionally different: it observes the placement selected by Kubernetes instead of imposing a controlled placement profile. `C8` is also intentionally different: it compares paired scheduler modes while holding the logical scenario constant within each default/load-aware pair.

---

## Core Configuration Flow

The central configuration entry point for cycle selection is:

```text
config/experimental-cycles/
```

This directory contains cycle profiles such as:

```text
config/experimental-cycles/C0.json
config/experimental-cycles/C1.json
config/experimental-cycles/C2.json
config/experimental-cycles/C3.json
config/experimental-cycles/C4.json
config/experimental-cycles/C5.json
config/experimental-cycles/C6.json
config/experimental-cycles/C7.json
config/experimental-cycles/C8.json
config/experimental-cycles/EXPERIMENTAL_CYCLES_INDEX.json
```

A cycle profile identifies the intended execution scope and links the major configuration families required by the workflow.

The execution flow is profile-driven:

```text
experimental cycle
→ infrastructure profile
→ provider binding or fixed-cluster kubeconfig
→ cluster lifecycle policy
→ cluster validation profile
→ application deployment profile
→ scenario family
→ observability profile
→ technical diagnosis profile
→ reporting profile
→ completion gate profile
→ freeze profile
```

The operational runbooks describe how to execute this flow from the command line.

---

## Configuration Families

The `config/` directory is the source of truth for declarative execution metadata.

### Experimental Cycles

```text
config/experimental-cycles/
```

Defines the supported execution cycles and campaigns.

### Infrastructure Profiles

```text
config/infrastructure/profiles/
```

Defines the logical shape of the cluster expected by a cycle, including control-plane nodes, worker nodes, resource sizes, Kubernetes distribution, and methodological notes.

### Infrastructure Lifecycle Policies

```text
config/infrastructure/lifecycle/
```

Defines whether a cluster is external, reused, retained, or deleted after a cycle.

### Provider Bindings

```text
config/infrastructure/providers/
```

Defines provider-specific bindings. The main provider used by the provider-backed workflow is:

```text
config/infrastructure/providers/proxmox-k3s/
```

This provider subtree contains indexes, JSON bindings, example YAML files, local YAML files, templates, schemas, and VMID allocation metadata.

### Cluster Access

```text
config/cluster-access/
```

Contains kubeconfig-related paths and local access conventions. Fixed-cluster access and generated provider-backed kubeconfigs are treated as separate concerns.

### Provisioning Profiles

```text
config/provisioning/
```

Defines integration metadata for invoking the provider workflow from the benchmark suite.

### Provisioning Validation Profiles

```text
config/provisioning-validation/
```

Defines checks that validate whether a provider-backed cluster and its generated access artifacts are usable.

### Cluster Validation Profiles

```text
config/cluster-validation/
```

Defines cluster-level validation checks after Kubernetes access is available.

### Application Deployment Profiles

```text
config/application-deployment/
```

Defines the LocalAI deployment profile used by provider-backed execution.

### Scenario Profiles

```text
config/scenarios/
```

Defines baseline scenarios and benchmark variants, including historical pilot scenarios and provider-backed comparative campaigns.

Relevant subdirectories include:

```text
config/scenarios/baseline/
config/scenarios/pilot/
config/scenarios/resource-variation/
config/scenarios/node-count-variation/
config/scenarios/placement-variation/
config/scenarios/latency-injection/
config/scenarios/multi-tenancy/
```

### Placement Profiles

```text
config/placement/
```

Defines logical placement policies for LocalAI server and worker components.

### Latency Profiles

```text
config/latency/
```

Defines controlled latency-injection configurations used by latency-sensitive campaigns.

### Tenancy Profiles

```text
config/tenancy/
```

Defines single-tenant and multi-tenant LocalAI application-cluster coexistence patterns.

### Observability Profiles

```text
config/observability-minimal/
```

Defines minimal observability capture behavior. This workflow intentionally does not require a full observability stack to be present as a blocking prerequisite.

### Technical Diagnosis Profiles

```text
config/technical-diagnosis/
```

Defines how benchmark artifacts are interpreted into machine-readable and human-readable diagnosis outputs.

### Reporting Profiles

```text
config/reporting/
```

Defines report generation behavior, including per-cycle reporting and consolidated reporting site configuration.

### Completion Gate Profiles

```text
config/completion-gate/
```

Defines the checks used to determine whether a cycle is completed, completed with unsupported scenarios, or failed.

### Freeze Profiles

```text
config/freeze/
```

Defines how cycle configurations and generated artifacts are archived as reproducible frozen evidence.

---

## Kubernetes Manifest Layout

Kubernetes manifests are stored under:

```text
infra/k8s/
```

The manifest layout follows a base, overlay, and composition model.

### Base Manifests

```text
infra/k8s/base/
```

The base layer contains reusable Kubernetes resources for the namespace, storage, LocalAI server, shared RPC-worker services, and topology primitives.

### Overlays

```text
infra/k8s/overlays/
```

The overlay layer contains reusable patches for model selection, worker count, and placement-specific behavior.

### Compositions

```text
infra/k8s/compositions/
```

The composition layer assembles base resources and overlays into deployable application topologies.

Important composition families include:

```text
infra/k8s/compositions/foundation/
infra/k8s/compositions/server/
infra/k8s/compositions/shared/
infra/k8s/compositions/topology/
infra/k8s/compositions/tenancy/
```

The fixed-cluster and provider-backed workflows both rely on Kubernetes manifests, but the exact composition applied depends on the cycle, scenario, placement, and tenancy profile.

---

## LocalAI Application Model

The benchmark suite focuses on LocalAI worker mode.

The application topology is based on:

1. a LocalAI server acting as the API entry point;
2. one or more LocalAI RPC worker components;
3. Kubernetes services connecting the server to RPC workers;
4. configuration values that make the server aware of the RPC worker endpoints;
5. placement policies controlling where server and worker pods are scheduled.

This model is intended to evaluate distributed LocalAI execution behavior under controlled topology, resource, workload, latency, and tenancy conditions.

The detailed LocalAI topology and placement documentation is provided in:

```text
12-localai-deployment-topologies-and-placement.md
```

---

## Load Generation Model

Load generation is based on Locust.

The Locust workload definition is stored in:

```text
load-tests/locust/locustfile.py
```

Benchmark execution is controlled by scenario configuration and phase/protocol profiles, including:

```text
config/phases/
config/protocol/
config/metric-set/
config/statistical-rigor/
```

The benchmark model separates warm-up, measurement, artifact collection, and post-processing. The detailed workload and artifact documentation is provided in:

```text
13-load-generation-observability-and-artifacts.md
```

---

## Script Layout

Executable automation is stored under:

```text
scripts/
```

The script tree is organized by responsibility.

### Experimental Cycle Launchers

```text
scripts/experimental-cycles/
```

Contains high-level entry points for executing individual cycles and comparative campaigns.

### Infrastructure Provisioning

```text
scripts/infrastructure/provision/
```

Contains provider-backed provisioning entry points and provider command wrappers.

### Infrastructure Lifecycle

```text
scripts/infrastructure/lifecycle/
```

Contains lifecycle-manifest rendering utilities.

### Cluster Validation

```text
scripts/infrastructure/validation/
```

Contains provider-backed and Kubernetes cluster validation utilities.

### Application Deployment

```text
scripts/application/deployment/
```

Contains provider-backed LocalAI deployment automation.

### Latency Handling

```text
scripts/latency/
```

Contains latency-profile application and cleanup utilities.

### Minimal Observability

```text
scripts/observability/minimal/
```

Contains minimal cluster-side evidence collection utilities.

### Benchmark and Post-Processing

```text
scripts/load/
scripts/analysis/
scripts/validation/
```

Contain benchmark execution support, smoke/precheck validation, diagnosis generation, reporting generation, completion gate evaluation, and freeze handling.

The script set generally provides Windows PowerShell wrappers, Bash wrappers, and Python implementation modules where appropriate.

---

## Result and Artifact Layout

Generated artifacts are stored under:

```text
results/
```

The `results/` directory is not the source of truth. It is the output surface of the benchmark pipeline and may be regenerated.

Important result areas include:

```text
results/baseline/
results/pilot/
results/experimental-cycles/
results/diagnosis/
results/reporting/
results/completion-gate/
results/infrastructure/
results/validation/
results/_runtime/
```

The most important modern execution root is:

```text
results/experimental-cycles/
```

Expected cycle-specific artifact families include:

```text
results/experimental-cycles/<cycle-id>/execution/
results/experimental-cycles/<cycle-id>/infrastructure/
results/experimental-cycles/<cycle-id>/application/
results/experimental-cycles/<cycle-id>/benchmarks/
results/experimental-cycles/<cycle-id>/observability/
results/experimental-cycles/<cycle-id>/diagnosis/
results/experimental-cycles/<cycle-id>/reporting/
results/experimental-cycles/<cycle-id>/completion-gate/
results/experimental-cycles/<cycle-id>/freeze/
```

Not every cycle necessarily creates every subdirectory in exactly the same way. The expected outputs are defined by the relevant cycle and profile configuration.

---

## Artifact Lifecycle

The pipeline treats generated outputs as reproducible artifacts.

The intended lifecycle is:

```text
raw execution output
→ benchmark metrics
→ cluster-side evidence
→ diagnosis artifacts
→ reporting artifacts
→ completion gate artifacts
→ freeze archive
```

The freeze step is the archival boundary for a cycle. A frozen cycle should preserve enough metadata, configuration references, and generated evidence to reconstruct what was executed and how the outcome was classified.

---

## Completion Semantics

A cycle completion gate does not merely check that a command returned successfully. It evaluates whether the expected artifact families were generated and whether the cycle outcome is acceptable under the relevant profile.

Typical outcome categories include:

```text
completed
completed_with_unsupported_scenarios
failed_validation
failed_benchmark
failed_reporting
```

Unsupported scenarios are not automatically execution failures. If a scenario is intentionally designed to test a resource boundary, a non-schedulable or resource-constrained result can be a valid methodological outcome.

---

## Default-Scheduler Baseline Track

`C7` is a provider-backed campaign that evaluates Kubernetes default-scheduler behavior for distributed LocalAI worker-mode tenant workloads.

Unlike controlled placement scenarios, `C7` does not use hard pod placement controls. The default-scheduler compositions under:

```text
infra/k8s/compositions/default-scheduler/
```

must avoid:

```text
spec.nodeName
hostname-specific nodeSelector
hostname-specific nodeAffinity
controlled placement overlays
```

The campaign preserves the placement chosen by Kubernetes through scheduler decision evidence. That evidence is required to interpret response time, throughput, failure, unsupported-scenario outcomes, and resource-contention indicators.

The main execution runbook for this track is:

```text
docs/runbooks/09-default-scheduler-c7-baseline-execution.md
```

---


## Resource-Aware Scheduler Track

`C8` is a provider-backed campaign that compares Kubernetes default scheduling with a load-aware custom scheduler for distributed LocalAI worker-mode tenant workloads.

The resource-aware-scheduler compositions under:

```text
infra/k8s/compositions/resource-aware-scheduler/
```

must avoid hard placement controls and must preserve the scheduler boundary:

```text
default variants: no spec.schedulerName in LocalAI workloads
load-aware variants: spec.schedulerName = scheduler-plugins-scheduler
```

C8 introduces additional operational components:

1. `mon-agent`, which annotates nodes and deployments with runtime CPU and memory evidence;
2. the `scheduler-plugins` second scheduler with the `LoadAwareResourcesBalancedAllocation` plugin;
3. telemetry-primed controlled redeployment, which creates a new scheduling decision after runtime annotations have been collected;
4. resource-aware-scheduler decision evidence, which connects the effective scheduler, pod placement, and benchmark outcomes.

C8 intentionally excludes latency injection, Chaos Mesh, network-aware scheduler plugins, and autoscaling from the initial resource-aware comparison.

The main execution runbook for this track is:

```text
docs/runbooks/10-resource-aware-scheduler-c8-execution.md
```

---
## Network-Aware Scheduler Track

The C9 track extends the provider-backed execution model with gateway-routed traffic and network-aware telemetry. It uses the same campaign runner model as C8, but its evidence boundary is broader:

```text
provider-backed cluster
-> monitoring, mon-agent, cluster-lens, Mentat, and Istio
-> LocalAI tenant workloads with group/app/role labels
-> gateway-routed traffic
-> annotation and network telemetry priming
-> controlled redeployment when required
-> scheduler decision capture
-> cluster-lens placement capture
-> benchmark measurement
-> diagnosis, reporting, completion gate, and freeze
```


The current C9 campaign contains 14 logical scenarios and 42 scheduler-mode variants. The paired comparison unit is a triplet consisting of one `DEFAULT`, one `LOADAWARE`, and one `NETAWARE` variant for the same logical scenario. The `L3_INTER_GROUP_EXTREME` scenarios extend the latency boundary with a more severe annotation-controlled inter-group latency matrix.

cluster-lens is installed by the provider workflow and captured by the benchmark suite as read-only topology evidence. Kubernetes pod, deployment, and node snapshots remain authoritative for `schedulerName`, labels, annotations, owner references, unscheduled pods, and node assignment.

C9 must preserve the distinction between three scheduler modes:

| Scheduler mode | Expected scheduler behavior |
|---|---|
| `DEFAULT` | Kubernetes scheduler selects placement without hard placement controls. |
| `LOADAWARE` | The second scheduler uses resource-aware scoring. |
| `NETAWARE` | The second scheduler combines resource-aware scoring with `NetworkAwareLocalAi`. |

C9 evidence must not be reduced to benchmark latency and throughput alone. It must also preserve gateway routing, `mon-agent` annotations, Mentat inter-node telemetry, scheduler configuration, cluster-lens placement snapshots, and the placement state used for the benchmark window.

---

## Provider Boundary

The `proxmox-k3s` project is an infrastructure provider. It should remain independent from LocalAI and from benchmark-specific semantics.

The benchmark suite may invoke the provider, but it should not require the provider to know about:

1. LocalAI;
2. benchmark cycles;
3. placement profiles;
4. latency profiles;
5. tenancy profiles;
6. Locust workloads;
7. reporting or freeze policies.

The provider boundary is:

```text
Provider input: provider-specific cluster YAML
Provider output: K3s cluster and kubeconfig
```

The benchmark boundary begins after cluster access is available:

```text
Benchmark input: kubeconfig and cycle profile
Benchmark output: benchmark, diagnosis, reporting, completion, and freeze artifacts
```

---

## Fixed Versus Provider-Backed Results

The fixed-cluster track and the provider-backed track must remain distinguishable in reporting and interpretation.

| Aspect | `C0` fixed-cluster track | `C1`-`C9` provider-backed track |
|---|---|---|
| Cluster creation | External to the benchmark suite | Driven by provider configuration |
| Infrastructure mutability | Not controlled by the cycle | Controlled through infrastructure profiles and provider bindings |
| Namespace assumption | Must be created or validated explicitly | Created or validated as part of deployment workflow |
| Main role | Reproduce historical characterization | Execute the provider-backed baseline, controlled campaigns, default-scheduler baseline, resource-aware comparison, and network-aware scheduler campaign |
| Interpretation | Historical baseline and pilot evidence | Provider-backed baseline, controlled comparative evidence, default-scheduler placement evidence, resource-aware scheduler evidence, and network-aware scheduler evidence |

---

## Repository Map

The following map summarizes the main directories.

```text
localai-worker-mode-benchmark-suite/
├── config/
│   ├── application-deployment/
│   ├── benchmark/
│   ├── cluster-access/
│   ├── cluster-capture/
│   ├── cluster-validation/
│   ├── completion-gate/
│   ├── conventions/
│   ├── experimental-cycles/
│   ├── freeze/
│   ├── infrastructure/
│   ├── latency/
│   ├── metric-set/
│   ├── mon-agent/
│   ├── network-observability/
│   ├── observability-minimal/
│   ├── phases/
│   ├── pilot-consolidation/
│   ├── placement/
│   ├── precheck/
│   ├── protocol/
│   ├── provisioning/
│   ├── provisioning-validation/
│   ├── reporting/
│   ├── rescheduling/
│   ├── scenarios/
│   ├── scheduler/
│   ├── istio-gateway/
│   ├── statistical-rigor/
│   ├── technical-diagnosis/
│   └── tenancy/
├── docs/
│   └── runbooks/
├── infra/
│   └── k8s/
├── load-tests/
│   └── locust/
├── scripts/
│   ├── analysis/
│   ├── application/
│   ├── common/
│   ├── experimental-cycles/
│   ├── infrastructure/
│   ├── latency/
│   ├── load/
│   ├── maintenance/
│   ├── network-observability/
│   ├── istio/
│   ├── observability/
│   ├── placement/
│   └── validation/
├── results/
└── requirements.txt
```

---

## How to Use This Runbook

Use this runbook as the map for deciding where to look before executing a workflow.

For execution procedures, use the following runbooks:

| Need | Runbook |
|---|---|
| Prepare local tools and shell conventions | `02-local-environment-and-tooling.md` |
| Configure local access, kubeconfig files, and provider-local configuration | `03-access-secrets-and-local-configuration.md` |
| Understand and operate the `proxmox-k3s` provider lifecycle | `04-proxmox-k3s-provider-lifecycle.md` |
| Understand profiles, cycles, and configuration taxonomy | `05-configuration-model-and-cycle-taxonomy.md` |
| Regenerate fixed-cluster historical artifacts | `06-fixed-cluster-c0-execution.md` |
| Execute the provider-backed baseline | `07-provider-backed-c1-baseline-execution.md` |
| Execute provider-backed comparative campaigns | `08-provider-backed-c2-c6-campaign-execution.md` |
| Execute the default-scheduler baseline campaign | `09-default-scheduler-c7-baseline-execution.md` |
| Execute the resource-aware scheduler campaign | `10-resource-aware-scheduler-c8-execution.md` |
| Execute the network-aware scheduler campaign | `11-network-aware-scheduler-c9-execution.md` |
| Understand LocalAI topologies and placement | `12-localai-deployment-topologies-and-placement.md` |
| Understand load generation, observability, and artifact interpretation | `13-load-generation-observability-and-artifacts.md` |
| Run diagnosis, reporting, completion gates, and freeze | `14-diagnosis-reporting-completion-gate-and-freeze.md` |
| Remove generated artifacts and regenerate the full workflow | `15-results-cleanup-and-full-regeneration.md` |
| Recover from common failures | `16-troubleshooting-and-recovery.md` |
| Find compact command pairs | `17-command-reference.md` |

---

## Operational Invariants

The following invariants must be preserved when using or extending the benchmark suite.

1. Execute from the repository root unless a runbook explicitly states otherwise.
2. Use explicit kubeconfig paths.
3. Keep fixed-cluster and provider-backed artifacts distinguishable.
4. Treat `config/` as declarative source of truth.
5. Treat `results/` as generated output.
6. Keep provider-local files and secrets outside versioned examples.
7. Keep `proxmox-k3s` independent from LocalAI benchmark semantics.
8. Use the canonical application namespace `localai-benchmark`.
9. Treat unsupported scenarios as valid outcomes when they are expected by the experimental design.
10. Freeze each completed cycle before relying on it as reproducible evidence.

---

## Next Runbook

Proceed to:

```text
02-local-environment-and-tooling.md
```

That runbook describes the local tools, shell conventions, Python environment, Kubernetes tooling, provider binary assumptions, and cross-shell command conventions required before executing the benchmark pipeline.
