# Configuration Model and Cycle Taxonomy

## Purpose

This runbook describes the configuration model used by the LocalAI worker-mode benchmark suite and explains how experimental cycles, infrastructure profiles, scenario profiles, provider bindings, validation profiles, reporting profiles, completion gates, and freeze profiles relate to each other.

The benchmark suite is intentionally configuration-driven. Execution scripts should not be treated as the primary source of experimental meaning. Instead, scripts consume explicit configuration profiles, produce generated artifacts, and preserve traceability from each benchmark result back to the profiles that produced it.

This runbook focuses on configuration semantics. It does not provide the full execution procedures for each cycle. Use the execution-specific runbooks for operational commands that create clusters, deploy LocalAI, run benchmarks, or regenerate artifacts.

---

## Repository Root Assumption

All paths in this document are relative to the repository root:

```text
localai-worker-mode-benchmark-suite/
```

Before inspecting configuration files, move to the repository root.

### Windows PowerShell

```powershell
Set-Location C:\Path\To\localai-worker-mode-benchmark-suite
```

### Bash

```bash
cd /path/to/localai-worker-mode-benchmark-suite
```

---

## Configuration Design Principles

The configuration model follows the principles below.

1. **Profiles are authoritative**: cycle meaning, infrastructure shape, scenario identity, lifecycle behavior, reporting scope, and completion criteria must be derived from explicit profile files.
2. **Generated artifacts are not configuration**: files under `results/` are outputs. They may contain generated runtime configuration snapshots, but they must not replace the source profiles under `config/`.
3. **Cycle identity must be explicit**: every official execution path is associated with a cycle identifier from `C0` through `C9`.
4. **Infrastructure identity must be explicit**: results collected on different infrastructure profiles must not be interpreted as directly comparable unless the infrastructure difference is explicitly declared.
5. **Provider-backed execution must resolve a provider binding**: infrastructure profiles managed by `proxmox-k3s` must map to a provider binding before resolving a real local provider YAML file.
6. **Scenario families vary one primary dimension at a time**: resource, node-count, placement, latency, and tenancy campaigns must keep unrelated dimensions controlled whenever possible.
7. **Unsupported scenarios are valid outcomes**: a scenario that cannot be scheduled or cannot complete under declared constraints may still provide valid resource, placement, or capacity evidence.
8. **Historical and provider-backed tracks must remain separate**: `C0` is a fixed-cluster historical track; `C1` through `C9` are provider-backed tracks.

---

## Top-Level Configuration Areas

The repository uses the following configuration areas.

| Configuration area | Path | Purpose |
|---|---|---|
| Experimental cycles | `config/experimental-cycles/` | Defines cycle-level governance, execution scope, profile references, artifact roots, and campaign variants. |
| Infrastructure profiles | `config/infrastructure/profiles/` | Defines cluster shape, node roles, resource classes, provider identity, lifecycle policy, and default placement expectations. |
| Infrastructure lifecycle policies | `config/infrastructure/lifecycle/` | Defines whether a cluster is externally managed, reused, retained, or deleted after a run. |
| Infrastructure providers | `config/infrastructure/providers/` | Defines provider registries and provider-specific bindings. |
| Proxmox/K3s provider bindings | `config/infrastructure/providers/proxmox-k3s/` | Maps infrastructure profiles to `proxmox-k3s` YAML files, VMID policies, lifecycle behavior, and kubeconfig paths. |
| Provisioning profiles | `config/provisioning/` | Defines benchmark-suite wrapper behavior for provider-backed cluster creation and lifecycle integration. |
| Provisioning validation profiles | `config/provisioning-validation/` | Defines checks that validate provider-backed cluster materialization before deeper benchmark operations. |
| Cluster validation profiles | `config/cluster-validation/` | Defines Kubernetes-level validation after a cluster is available. |
| Application deployment profiles | `config/application-deployment/` | Defines LocalAI deployment behavior for provider-backed execution. |
| Precheck profiles | `config/precheck/` | Defines benchmark preconditions, namespace expectations, model/API checks, and runtime validation requirements. |
| Benchmark protocol and phases | `config/protocol/`, `config/phases/` | Defines benchmark protocol parameters, warm-up behavior, measurement behavior, and runtime phase structure. |
| Metric and evidence profiles | `config/metric-set/`, `config/cluster-capture/`, `config/statistical-rigor/` | Defines metrics, cluster-side evidence, and repeatability rules. |
| Scenario profiles | `config/scenarios/` | Defines baseline, historical pilot, resource-variation, node-count, placement, latency, tenancy, default-scheduler, resource-aware-scheduler, and network-aware scheduler scenarios. |
| Scheduler profiles | `config/scheduler/` | Defines custom scheduler installation and validation profiles. |
| mon-agent profiles | `config/mon-agent/` | Defines runtime annotation requirements and monitoring-agent validation policies. |
| Network observability profiles | `config/network-observability/` | Defines Mentat-based inter-node network telemetry requirements. |
| Istio gateway profiles | `config/istio-gateway/` | Defines gateway-routed benchmark access requirements. |
| Rescheduling profiles | `config/rescheduling/` | Defines telemetry-primed redeployment policies. |
| Placement profiles | `config/placement/` | Defines placement policies and node-affinity semantics used by LocalAI server and worker deployments. |
| Latency profiles | `config/latency/` | Defines controlled network-latency injection levels. |
| Tenancy profiles | `config/tenancy/` | Defines namespace-scoped multi-tenant LocalAI deployment layouts. |
| Minimal observability profiles | `config/observability-minimal/` | Defines lightweight observability evidence collected during provider-backed runs. |
| Technical diagnosis profiles | `config/technical-diagnosis/` | Defines post-processing rules that turn benchmark artifacts into technical diagnosis outputs. |
| Reporting profiles | `config/reporting/` | Defines cycle-scoped reporting and static reporting-site generation. |
| Completion-gate profiles | `config/completion-gate/` | Defines evidence requirements for declaring a cycle or campaign complete. |
| Freeze profiles | `config/freeze/` | Defines snapshotting rules for preserving cycle evidence after completion. |

---

## Configuration Registry Pattern

Most configuration areas follow the same registry pattern:

```text
index file
→ profile files
→ optional schema files
→ optional template files
```

For example:

```text
config/reporting/REPORTING_INDEX.json
config/reporting/profiles/RP_C1_PROVIDER_BACKED_BASELINE.json
config/reporting/schemas/REPORTING_PROFILE_SCHEMA_V1.json
```

The index file provides discoverability and governance. The profile file provides concrete execution semantics. The schema file documents the expected shape. Template files, when present, provide reusable patterns for new profiles.

Validate that the main registries are present before editing or executing configuration-driven workflows.

### Windows PowerShell

```powershell
$RequiredIndexes = @(
  ".\config\experimental-cycles\EXPERIMENTAL_CYCLES_INDEX.json",
  ".\config\infrastructure\INFRA_PROFILES_INDEX.json",
  ".\config\infrastructure\lifecycle\CLUSTER_LIFECYCLE_POLICIES_INDEX.json",
  ".\config\infrastructure\providers\PROVIDERS_INDEX.json",
  ".\config\infrastructure\providers\proxmox-k3s\PROXMOX_K3S_PROVIDER_INDEX.json",
  ".\config\infrastructure\providers\proxmox-k3s\PROXMOX_K3S_PROVIDER_BINDINGS_INDEX.json",
  ".\config\placement\PLACEMENT_PROFILES_INDEX.json",
  ".\config\latency\LATENCY_PROFILES_INDEX.json",
  ".\config\tenancy\TENANCY_PROFILES_INDEX.json",
  ".\config\technical-diagnosis\TECHNICAL_DIAGNOSIS_INDEX.json",
  ".\config\reporting\REPORTING_INDEX.json",
  ".\config\completion-gate\COMPLETION_GATE_INDEX.json",
  ".\config\freeze\FREEZE_INDEX.json"
)

$RequiredIndexes | ForEach-Object {
  if (-not (Test-Path $_)) {
    throw "Missing required configuration index: $_"
  }
}
```

### Bash

```bash
required_indexes=(
  "./config/experimental-cycles/EXPERIMENTAL_CYCLES_INDEX.json"
  "./config/infrastructure/INFRA_PROFILES_INDEX.json"
  "./config/infrastructure/lifecycle/CLUSTER_LIFECYCLE_POLICIES_INDEX.json"
  "./config/infrastructure/providers/PROVIDERS_INDEX.json"
  "./config/infrastructure/providers/proxmox-k3s/PROXMOX_K3S_PROVIDER_INDEX.json"
  "./config/infrastructure/providers/proxmox-k3s/PROXMOX_K3S_PROVIDER_BINDINGS_INDEX.json"
  "./config/placement/PLACEMENT_PROFILES_INDEX.json"
  "./config/latency/LATENCY_PROFILES_INDEX.json"
  "./config/tenancy/TENANCY_PROFILES_INDEX.json"
  "./config/technical-diagnosis/TECHNICAL_DIAGNOSIS_INDEX.json"
  "./config/reporting/REPORTING_INDEX.json"
  "./config/completion-gate/COMPLETION_GATE_INDEX.json"
  "./config/freeze/FREEZE_INDEX.json"
)

for index_path in "${required_indexes[@]}"; do
  test -f "$index_path" || { echo "Missing required configuration index: $index_path" >&2; exit 1; }
done
```

---

## Cycle Taxonomy

The benchmark suite is organized around eight official cycles.

| Cycle | Track | Name | Primary role |
|---|---|---|---|
| `C0` | Historical fixed-cluster | Historical Fixed Cluster Characterization Cycle | Regenerates the complete historical characterization workflow on an externally available Kubernetes/K3s cluster. |
| `C1` | Provider-backed | Provider-Backed Baseline Cycle | Validates the provider-backed workflow end to end using one infrastructure profile and baseline scenario `B1`. |
| `C2` | Provider-backed campaign | Resource Variation Campaign | Varies CPU and memory capacity while controlling the application-side dimensions. |
| `C3` | Provider-backed campaign | Node-Count Variation Campaign | Varies the number of provider-backed worker nodes while keeping per-node capacity controlled. |
| `C4` | Provider-backed campaign | Placement Variation Campaign | Varies LocalAI server and RPC-worker placement strategies under controlled infrastructure and workload conditions. |
| `C5` | Provider-backed campaign | Latency Injection Campaign | Varies network-latency injection profiles under controlled infrastructure, placement, and workload conditions. |
| `C6` | Provider-backed campaign | Multi-Tenancy Campaign | Varies namespace-scoped LocalAI tenant layouts on the same underlying infrastructure. |
| `C7` | Default-scheduler provider-backed campaign | Default Kubernetes Scheduler Baseline Campaign | Observes default Kubernetes scheduler placement under tenant-count, worker-node-count, latency-profile, tenant-traffic, and model-mix variation. |
| `C8` | resource-aware scheduler campaign | Resource-Aware Scheduler Campaign | Compares Kubernetes default scheduling with load-aware custom scheduling under paired `L0_NONE` resource-aware scenarios. |
| `C9` | Network-aware scheduler campaign | Network-Aware Scheduler Campaign | Compares Kubernetes default scheduling, load-aware custom scheduling, and resource plus network-aware scheduling under gateway-routed and latency-differentiated scenarios. |

The canonical cycle registry is:

```text
config/experimental-cycles/EXPERIMENTAL_CYCLES_INDEX.json
```

The cycle profiles are:

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
config/experimental-cycles/C9.json
```

List available cycle profiles before running or modifying a cycle.

### Windows PowerShell

```powershell
Get-ChildItem .\config\experimental-cycles\C*.json | Select-Object Name, Length
```

### Bash

```bash
find ./config/experimental-cycles -maxdepth 1 -type f -name 'C*.json' -print | sort
```

---

## Historical Fixed-Cluster Track: `C0`

`C0` is the historical fixed-cluster execution track. It is associated with:

| Concept | Identifier or path |
|---|---|
| Cycle profile | `config/experimental-cycles/C0.json` |
| Baseline scenario | `config/scenarios/baseline/B0.json` |
| Infrastructure profile | `config/infrastructure/profiles/INFRA_C0_1CP_2W_8C16G.json` |
| Lifecycle policy | `config/infrastructure/lifecycle/policies/LC_C0_EXTERNAL_FIXED_CLUSTER_RETAIN.json` |
| Precheck profile | `config/precheck/profiles/TC_C0_HISTORICAL_FIXED_CLUSTER.json` |
| Technical diagnosis profile | `config/technical-diagnosis/profiles/TD_C0_HISTORICAL_FIXED_CLUSTER.json` |
| Reporting profile | `config/reporting/profiles/RP_C0_HISTORICAL_FIXED_CLUSTER.json` |
| Completion-gate profile | `config/completion-gate/profiles/CG_C0_HISTORICAL_FIXED_CLUSTER.json` |
| Freeze profile | `config/freeze/profiles/FR_C0_HISTORICAL_FIXED_CLUSTER.json` |

`C0` uses an externally available cluster and must not invoke `proxmox-k3s` create or delete operations. Its lifecycle policy is descriptive and retention-oriented.

`C0` must also be treated as broader than the consolidated pilot alone. The historical track includes the fixed-cluster baseline, exploratory checks where applicable, pilot sweeps, consolidated pilot, diagnosis, reporting, completion gate, and freeze.

Historical pilot scenario families include:

| Family | Path | Scenario identifiers |
|---|---|---|
| Worker-count pilot | `config/scenarios/pilot/worker-count/` | `W1`, `W2`, `W3`, `W4` |
| Workload pilot | `config/scenarios/pilot/workload/` | `WL1`, `WL2`, `WL3` |
| Model pilot | `config/scenarios/pilot/models/` | `M1`, `M2`, `M3`, `M4` |
| Placement pilot | `config/scenarios/pilot/placement/` | `PL1`, `PL2` |
| Consolidated pilot | `config/pilot-consolidation/profiles/PC_CONSOLIDATED_PILOT_CAMPAIGN.json` | consolidated historical profile |

The canonical namespace for LocalAI benchmark workloads is `localai-benchmark`. The C0 execution runbook must create or validate that namespace explicitly before applying workloads.

---

## Provider-Backed Baseline Track: `C1`

`C1` is the provider-backed baseline. It establishes that the full workflow can run on a K3s cluster materialized or reused through the declared infrastructure profile and `proxmox-k3s` provider binding.

| Concept | Identifier or path |
|---|---|
| Cycle profile | `config/experimental-cycles/C1.json` |
| Baseline scenario | `config/scenarios/baseline/B1.json` |
| Infrastructure profile | `config/infrastructure/profiles/INFRA_C1_1CP_2W_8C16G.json` |
| Provider binding | `config/infrastructure/providers/proxmox-k3s/bindings/BINDING_INFRA_C1_1CP_2W_8C16G_PROXMOX_K3S.json` |
| Provider local YAML | `config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml` |
| Generated kubeconfig | `config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig` |
| Provisioning profile | `config/provisioning/profiles/PI_C1_PROVIDER_BACKED_BASELINE.json` |
| Provisioning validation profile | `config/provisioning-validation/profiles/PV_C1_PROVIDER_BACKED_BASELINE.json` |
| Cluster validation profile | `config/cluster-validation/profiles/CV_C1_PROVIDER_BACKED_BASELINE.json` |
| Application deployment profile | `config/application-deployment/profiles/AD_C1_PROVIDER_BACKED_BASELINE.json` |
| Minimal observability profile | `config/observability-minimal/profiles/MO_C1_PROVIDER_BACKED_BASELINE.json` |
| Technical diagnosis profile | `config/technical-diagnosis/profiles/TD_C1_PROVIDER_BACKED_BASELINE.json` |
| Reporting profile | `config/reporting/profiles/RP_C1_PROVIDER_BACKED_BASELINE.json` |
| Completion-gate profile | `config/completion-gate/profiles/CG_C1_PROVIDER_BACKED_BASELINE.json` |
| Freeze profile | `config/freeze/profiles/FR_C1_PROVIDER_BACKED_BASELINE.json` |

`C1` normally uses a reusable lifecycle policy. It should be executed before provider-backed comparative campaigns when regenerating a complete artifact set.

---

## Provider-Backed Comparative Campaigns: `C2` Through `C6`

`C2` through `C6` are provider-backed campaigns. A campaign contains multiple variants. Each variant has a scenario identifier, scenario configuration, infrastructure relationship, benchmark output root, diagnosis scope, reporting profile, completion gate, and freeze profile.

| Cycle | Campaign type | Scenario family | Scenario index |
|---|---|---|---|
| `C2` | resource variation | `resource-variation` | `config/scenarios/resource-variation/RESOURCE_VARIATION_SCENARIOS_INDEX.json` |
| `C3` | node-count variation | `node-count-variation` | `config/scenarios/node-count-variation/NODE_COUNT_VARIATION_SCENARIOS_INDEX.json` |
| `C4` | placement variation | `placement-variation` | `config/scenarios/placement-variation/PLACEMENT_VARIATION_SCENARIOS_INDEX.json` |
| `C5` | latency injection | `latency-injection` | `config/scenarios/latency-injection/LATENCY_INJECTION_SCENARIOS_INDEX.json` |
| `C6` | multi-tenancy | `multi-tenancy` | `config/scenarios/multi-tenancy/MULTI_TENANCY_SCENARIOS_INDEX.json` |

Campaigns generally use an ephemeral lifecycle policy, because each variant may require a clean infrastructure profile, clean cluster materialization, or controlled topology reset.

---

## Default-Scheduler Baseline Campaign: `C7`

`C7` is a provider-backed campaign that evaluates Kubernetes default-scheduler placement decisions under multi-tenant, latency-aware, and traffic-differentiated conditions.

Its authoritative cycle profile is:

```text
config/experimental-cycles/C7.json
config/experimental-cycles/C8.json
config/experimental-cycles/C9.json
```

Its scenario registry is:

```text
config/scenarios/default-scheduler/DEFAULT_SCHEDULER_SCENARIOS_INDEX.json
```

Its scenario family is:

```text
default-scheduler
```

The configuration model for `C7` differs from the controlled placement campaigns in one essential way: placement must be observed rather than imposed. The C7 manifests must not contain hard placement controls such as `spec.nodeName`, hostname-specific `nodeSelector`, or hostname-specific node affinity.

The C7 configuration model must preserve:

- scenario class: `official`, `diagnostic`, or `stress`;
- tenant count;
- worker-node count;
- latency profile;
- tenant traffic profile;
- model mix;
- LocalAI worker count per tenant;
- provider-backed infrastructure profile;
- scheduler-decision capture requirements.

The corresponding execution runbook is:

```text
docs/runbooks/09-default-scheduler-c7-baseline-execution.md
```

## Resource-Aware Scheduler Campaign: `C8`

`C8` is a provider-backed campaign that compares Kubernetes default scheduling with a load-aware custom scheduler.

Its authoritative cycle profile is:

```text
config/experimental-cycles/C8.json
```

Its scenario registry is:

```text
config/scenarios/resource-aware-scheduler/RESOURCE_AWARE_SCHEDULER_SCENARIOS_INDEX.json
```

Its scenario family is:

```text
resource-aware-scheduler
```

C8 pairs default and load-aware variants for each logical scenario. The resource-aware-scheduler model must preserve:

- logical scenario identity;
- default/load-aware pairing;
- `L0_NONE` latency boundary;
- workload and model-mix invariance within each pair;
- `mon-agent` annotation requirements;
- controlled telemetry-primed redeployment;
- scheduler decision evidence;
- comparative reporting and completion-gate evidence.

C8 introduces the following configuration families:

| Configuration family | Canonical path | Purpose |
|---|---|---|
| Resource-aware scheduler scenarios | `config/scenarios/resource-aware-scheduler/` | Defines the paired default/load-aware scenario variants. |
| Custom scheduler profiles | `config/scheduler/` | Defines the second scheduler and enabled scheduler plugins. |
| Monitoring agent profiles | `config/mon-agent/` | Defines `mon-agent` deployment, namespace selection, and annotation validation. |
| Rescheduling profiles | `config/rescheduling/` | Defines telemetry priming, annotation gate, controlled redeployment, and measurement boundary. |
| C8 infrastructure profiles | `config/infrastructure/profiles/INFRA_C8_*.json` | Defines two- and four-worker provider-backed infrastructure envelopes. |

The corresponding execution runbook is:

```text
docs/runbooks/10-resource-aware-scheduler-c8-execution.md
```

---

## Network-Aware Scheduler Campaign: `C9`

`C9` is a provider-backed campaign that compares Kubernetes default scheduling, load-aware custom scheduling, and resource plus network-aware custom scheduling for gateway-routed distributed LocalAI worker-mode workloads.

The canonical cycle profile is:

```text
config/experimental-cycles/C9.json
```

The scenario family is:

```text
config/scenarios/network-aware-scheduler/
```

C9 uses fourteen logical scenarios and three scheduler modes per logical scenario, producing forty-two planned variants. The scheduler modes are:

| Scheduler mode | Variant prefix | Expected scheduler behavior |
|---|---|---|
| Kubernetes default scheduler | `NA_DEFAULT_*` | Workloads omit `spec.schedulerName`. |
| Load-aware scheduler | `NA_LOADAWARE_*` | Workloads use `scheduler-plugins-scheduler` with `LoadAwareResourcesBalancedAllocation`. |
| Resource plus network-aware scheduler | `NA_NETAWARE_*` | Workloads use `scheduler-plugins-scheduler` with both `LoadAwareResourcesBalancedAllocation` and `NetworkAwareLocalAi`. |

C9 introduces the following configuration families:

| C9 configuration family | Path | Purpose |
|---|---|---|
| Network-aware scenarios | `config/scenarios/network-aware-scheduler/` | Defines default, load-aware, and network-aware variants. |
| Four-worker infrastructure | `config/infrastructure/profiles/INFRA_C9_1CP_4W_8C16G.json` | Defines the C9 provider-backed infrastructure envelope. |
| C9 load-aware scheduler profile | `config/scheduler/profiles/CS_C9_LOADAWARE_SECOND_SCHEDULER.json` | Enables `LoadAwareResourcesBalancedAllocation` for C9 LOADAWARE variants. |
| C9 resource plus network-aware scheduler profile | `config/scheduler/profiles/CS_C9_LOCALAI_RESOURCE_NETWORK_AWARE_SECOND_SCHEDULER.json` | Enables `LoadAwareResourcesBalancedAllocation` and `NetworkAwareLocalAi` for C9 NETAWARE variants. |
| Network-aware mon-agent profile | `config/mon-agent/profiles/MA_NETWORK_AWARE.json` | Validates resource, gateway-traffic, and network-aware annotations. |
| Mentat network observability profile | `config/network-observability/profiles/NO_MENTAT_C9.json` | Validates inter-node latency, packet loss, and bandwidth evidence. |
| cluster-lens placement capture profile | `config/cluster-lens/profiles/CL_C9_PLACEMENT_SNAPSHOT.json` | Defines read-only placement snapshot capture and artifact conventions. |
| Istio gateway profile | `config/istio-gateway/profiles/IG_LOCALAI_GATEWAY_ROUTED_C9.json` | Validates gateway-routed benchmark traffic. |
| Telemetry-primed rescheduling profile | `config/rescheduling/profiles/RS_C9_NETWORK_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json` | Gates redeployment on current telemetry and scheduler-facing annotations. |

C9 must not reinterpret C8. C8 remains the resource-aware comparison. C9 is the network-aware extension where gateway-routed traffic, inter-node network telemetry, annotation-controlled latency profiles, and cluster-lens placement evidence are part of the evidence boundary.

---

## Scenario Family Matrix

The scenario matrix below summarizes the currently defined campaign variants.

| Cycle | Scenario family | Variants | Main varied dimension |
|---|---|---|---|
| `C2` | `resource-variation` | `RV_4C8G`, `RV_4C16G`, `RV_8C16G` | Worker-node CPU and memory capacity. |
| `C3` | `node-count-variation` | `NC_2N`, `NC_3N`, `NC_4N` | Number of provider-backed worker nodes. |
| `C4` | `placement-variation` | `PLC_COLOCATED`, `PLC_DISTRIBUTED_TWO_NODE`, `PLC_SPREAD_WORKERS`, `PLC_SERVER_SEPARATED`, `PLC_BALANCED_STATIC` | Placement of LocalAI server and RPC workers. |
| `C5` | `latency-injection` | `LI_L0_NONE`, `LI_L1_EDGE_NEAR`, `LI_L2_EDGE_REMOTE`, `LI_L3_EXTREME` | Injected network-latency profile. |
| `C6` | `multi-tenancy` | `MT_SINGLE_TENANT_REFERENCE`, `MT_TWO_TENANTS_SEPARATED`, `MT_TWO_TENANTS_MIXED_MODELS`, `MT_TWO_TENANTS_SHARED_NODEPOOL` | Tenant topology and namespace-scoped LocalAI coexistence. |
| `C7` | `default-scheduler` | `DS_*` | Default Kubernetes scheduler placement under tenant, node-count, latency, traffic, and model-mix variation. |
| `C8` | `resource-aware-scheduler` | `RA_DEFAULT_*`, `RA_LOADAWARE_*` | Paired default/load-aware scheduler evaluation under `L0_NONE` resource-aware scenarios. |
| `C9` | `network-aware-scheduler` | `NA_DEFAULT_*`, `NA_LOADAWARE_*`, `NA_NETAWARE_*` | Three-way default/load-aware/network-aware comparison under gateway-routed and latency-differentiated scenarios. |

Scenario identifiers and lower-level profile identifiers are intentionally distinct. For example, a `PLC_*` placement-variation scenario may select a `PL_*` placement profile. The scenario describes the experimental variant; the placement profile describes the Kubernetes placement policy.

---

## Infrastructure Profile Model

Infrastructure profiles define the cluster-level shape expected by a cycle or campaign variant. They describe the intended control-plane and worker-node topology, provider identity, lifecycle policy, default placement assumptions, and relationship to cycle/campaign scope.

The canonical infrastructure registry is:

```text
config/infrastructure/INFRA_PROFILES_INDEX.json
```

Main infrastructure profiles include:

| Infrastructure profile | Primary use |
|---|---|
| `INFRA_C0_1CP_2W_8C16G` | Historical fixed-cluster `C0` reference. |
| `INFRA_C1_1CP_2W_8C16G` | Provider-backed baseline `C1`. |
| `INFRA_C2_1CP_2W_4C8G` | Resource-variation low-resource candidate. |
| `INFRA_C2_1CP_2W_4C16G` | Resource-variation CPU-constrained candidate. |
| `INFRA_C2_1CP_2W_8C16G` | Resource-variation reference-capacity candidate. |
| `INFRA_C3_1CP_2W_8C16G` | Node-count variation with two worker nodes. |
| `INFRA_C3_1CP_3W_8C16G` | Node-count variation with three worker nodes. |
| `INFRA_C3_1CP_4W_8C16G` | Node-count variation with four worker nodes. |
| `INFRA_C4_1CP_4W_8C16G` | Placement-variation infrastructure profile. |
| `INFRA_C5_1CP_4W_8C16G` | Latency-injection infrastructure profile. |
| `INFRA_C6_1CP_4W_8C16G` | Multi-tenancy infrastructure profile. |
| `INFRA_C7_1CP_2W_8C16G` | Default-scheduler infrastructure profile with two worker nodes. |
| `INFRA_C7_1CP_3W_8C16G` | Default-scheduler infrastructure profile with three worker nodes. |
| `INFRA_C7_1CP_4W_8C16G` | Default-scheduler infrastructure profile with four worker nodes. |
| `INFRA_C8_1CP_2W_8C16G` | Resource-aware scheduler infrastructure profile with one management/control-plane node and two worker nodes. |
| `INFRA_C8_1CP_4W_8C16G` | Resource-aware scheduler infrastructure profile with one management/control-plane node and four worker nodes. |
| `INFRA_C9_1CP_4W_8C16G` | Network-aware scheduler infrastructure profile with one management/control-plane node and four worker nodes plus the required observability add-on boundary. |

Inspect the infrastructure registry when validating campaign scope.

### Windows PowerShell

```powershell
python -c "import json; p='config/infrastructure/INFRA_PROFILES_INDEX.json'; d=json.load(open(p, encoding='utf-8')); [print(x.get('infrastructureProfileId'), x.get('associatedCycleId'), x.get('providerId')) for x in d.get('profiles', [])]"
```

### Bash

```bash
python -c "import json; p='config/infrastructure/INFRA_PROFILES_INDEX.json'; d=json.load(open(p, encoding='utf-8')); [print(x.get('infrastructureProfileId'), x.get('associatedCycleId'), x.get('providerId')) for x in d.get('profiles', [])]"
```

---

## Provider Binding Model

Provider-backed infrastructure profiles are resolved through provider bindings. A provider binding links an infrastructure profile to:

- provider identifier;
- local provider YAML file;
- example provider YAML file;
- generated kubeconfig path;
- VMID allocation policy;
- lifecycle policy;
- provisioning integration profile.

The canonical provider-binding registry is:

```text
config/infrastructure/providers/proxmox-k3s/PROXMOX_K3S_PROVIDER_BINDINGS_INDEX.json
```

Provider-backed cycles must not skip this resolution step. An infrastructure profile alone defines the intended shape; the provider binding defines how that shape maps to the real provider workflow.

Inspect provider bindings with the following commands.

### Windows PowerShell

```powershell
python -c "import json; p='config/infrastructure/providers/proxmox-k3s/PROXMOX_K3S_PROVIDER_BINDINGS_INDEX.json'; d=json.load(open(p, encoding='utf-8')); [print(x.get('providerBindingId'), '=>', x.get('infrastructureProfileId'), '|', x.get('lifecyclePolicyId')) for x in d.get('bindings', [])]"
```

### Bash

```bash
python -c "import json; p='config/infrastructure/providers/proxmox-k3s/PROXMOX_K3S_PROVIDER_BINDINGS_INDEX.json'; d=json.load(open(p, encoding='utf-8')); [print(x.get('providerBindingId'), '=>', x.get('infrastructureProfileId'), '|', x.get('lifecyclePolicyId')) for x in d.get('bindings', [])]"
```

---

## Lifecycle Policy Model

Lifecycle policies define how a cluster is managed before and after an execution.

| Lifecycle policy | Provider model | Intended meaning |
|---|---|---|
| `LC_C0_EXTERNAL_FIXED_CLUSTER_RETAIN` | external fixed cluster | Use an already reachable cluster and never create or delete it through the provider. |
| `LC_REUSE_RETAIN_CLUSTER` | `proxmox-k3s` | Create or reuse a provider-backed cluster and retain it after the run. |
| `LC_EPHEMERAL_DELETE_CLUSTER` | `proxmox-k3s` | Create a provider-backed cluster for a bounded run or variant and delete it when appropriate. |

The lifecycle-policy registry is:

```text
config/infrastructure/lifecycle/CLUSTER_LIFECYCLE_POLICIES_INDEX.json
```

Lifecycle policy selection must be consistent with the execution track. `C0` must use the external fixed-cluster lifecycle model. Provider-backed campaigns may use reusable or ephemeral lifecycle behavior depending on the intended comparison.

---

## Placement Profile Model

Placement profiles define Kubernetes placement semantics for LocalAI server and RPC-worker components. They are used by provider-backed deployment and campaign scenarios to control the trade-off between communication locality and resource contention.

The placement registry is:

```text
config/placement/PLACEMENT_PROFILES_INDEX.json
```

Main placement profiles include:

| Placement profile | General meaning |
|---|---|
| `PL_COLOCATED` | Places LocalAI server and worker components as close as possible, typically on the same node when schedulable. |
| `PL_DISTRIBUTED_TWO_NODE` | Distributes components over a two-node layout. |
| `PL_SPREAD_WORKERS` | Spreads workers across available worker nodes to reduce local resource contention. |
| `PL_SERVER_SEPARATED` | Separates the LocalAI server from worker components. |
| `PL_BALANCED_STATIC` | Applies a static balanced placement layout. |

Placement-variation scenario identifiers in `C4` use the `PLC_*` prefix. Placement profile identifiers use the `PL_*` prefix. Do not conflate the two namespaces.

---

## Latency Profile Model

Latency profiles define controlled network-latency levels used by latency-injection scenarios.

The latency registry is:

```text
config/latency/LATENCY_PROFILES_INDEX.json
```

Main latency profiles include:

| Latency profile | General meaning |
|---|---|
| `L0_NONE` | No intentional latency injection. |
| `L1_EDGE_NEAR` | Near-edge latency profile. |
| `L2_EDGE_REMOTE` | Remote-edge latency profile. |
| `L3_EXTREME` | Extreme latency profile intended to expose stability or feasibility limits. |

Latency-injection scenarios in `C5` use the `LI_*` prefix and map to one of the latency profiles above.

---

## Tenancy Profile Model

Tenancy profiles define namespace-scoped LocalAI deployment layouts used by the multi-tenancy campaign.

The tenancy registry is:

```text
config/tenancy/TENANCY_PROFILES_INDEX.json
```

Main tenancy profiles include:

| Tenancy profile | General meaning |
|---|---|
| `TP_SINGLE_TENANT_REFERENCE` | Single-tenant reference layout. |
| `TP_TWO_TENANTS_SEPARATED` | Two tenant-like LocalAI deployments separated by namespace and placement policy. |
| `TP_TWO_TENANTS_MIXED_MODELS` | Two tenant-like deployments using different model characteristics. |
| `TP_TWO_TENANTS_SHARED_NODEPOOL` | Two tenant-like deployments sharing the same node pool more aggressively. |

Multi-tenancy scenarios in `C6` use the `MT_*` prefix and map to tenancy profiles.

---

## Benchmark Runtime Profiles

Benchmark execution is controlled by reusable runtime profiles. These profiles define how traffic is generated, how benchmark phases are organized, and how evidence is collected.

| Runtime profile | Path | Purpose |
|---|---|---|
| Run convention | `config/conventions/profiles/RC_STANDARD_RUN_CONVENTION.json` | Defines naming and artifact conventions. |
| Phase profile | `config/phases/profiles/WM_STANDARD_WARMUP_MEASUREMENT.json` | Defines warm-up and measurement phase behavior. |
| Protocol profile | `config/protocol/profiles/EP_STANDARD_BENCHMARK_PROTOCOL.json` | Defines endpoint protocol and request behavior. |
| Cluster capture profile | `config/cluster-capture/profiles/CS_STANDARD_CLUSTER_CAPTURE.json` | Defines cluster-side artifact collection. |
| Metric set | `config/metric-set/profiles/MS_STANDARD_BENCHMARK_METRICS.json` | Defines the primary metric set. |
| Statistical rigor profile | `config/statistical-rigor/profiles/SR_REPLICATED_BENCHMARK_RIGOR.json` | Defines repeatability and replica semantics. |
| Pilot consolidation profile | `config/pilot-consolidation/profiles/PC_CONSOLIDATED_PILOT_CAMPAIGN.json` | Defines historical consolidated pilot behavior. |

These runtime profiles are shared by multiple execution paths and should not be modified for a single scenario unless a new scenario or new cycle explicitly requires different runtime semantics.

---

## Validation, Diagnosis, Reporting, Completion, and Freeze Profiles

Post-benchmark processing uses dedicated profile families.

| Profile family | Path | Purpose |
|---|---|---|
| Technical diagnosis | `config/technical-diagnosis/profiles/` | Converts raw benchmark and cluster evidence into technical interpretation artifacts. |
| Reporting | `config/reporting/profiles/` | Produces Markdown/HTML reports and reporting-site inputs. |
| Completion gate | `config/completion-gate/profiles/` | Evaluates whether required evidence is present and whether completion criteria are satisfied. |
| Freeze | `config/freeze/profiles/` | Snapshots relevant artifacts into cycle-scoped frozen evidence packages. |

Each official cycle from `C0` through `C9` has a corresponding technical diagnosis profile, reporting profile, completion-gate profile, and freeze profile.

Validate that post-processing profiles exist for each official cycle.

### Windows PowerShell

```powershell
$Cycles = @("C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9")
$Cycles | ForEach-Object {
  $Cycle = $_
  $Expected = @(
    ".\config\technical-diagnosis\profiles\TD_${Cycle}_*.json",
    ".\config\reporting\profiles\RP_${Cycle}_*.json",
    ".\config\completion-gate\profiles\CG_${Cycle}_*.json",
    ".\config\freeze\profiles\FR_${Cycle}_*.json"
  )
  $Expected | ForEach-Object {
    if (-not (Get-ChildItem $_ -ErrorAction SilentlyContinue)) {
      throw "Missing post-processing profile matching pattern: $_"
    }
  }
}
```

### Bash

```bash
for cycle in C0 C1 C2 C3 C4 C5 C6 C7 C8 C9; do
  for prefix in TD RP CG FR; do
    case "$prefix" in
      TD) root="./config/technical-diagnosis/profiles" ;;
      RP) root="./config/reporting/profiles" ;;
      CG) root="./config/completion-gate/profiles" ;;
      FR) root="./config/freeze/profiles" ;;
    esac
    matches=$(find "$root" -maxdepth 1 -type f -name "${prefix}_${cycle}_*.json" | wc -l)
    test "$matches" -gt 0 || { echo "Missing ${prefix} profile for ${cycle}" >&2; exit 1; }
  done
done
```

---

## Profile Resolution Chain

A complete provider-backed execution resolves configuration in the following order:

```text
experimental cycle
→ campaign variant or baseline scenario
→ infrastructure profile
→ provider binding
→ local provider YAML
→ lifecycle policy
→ generated kubeconfig
→ cluster validation profile
→ application deployment profile
→ placement / latency / tenancy profile, when applicable
→ scheduler / mon-agent / network-observability / gateway / rescheduling profile, when applicable
→ benchmark runtime profiles
→ technical diagnosis profile
→ reporting profile
→ completion-gate profile
→ freeze profile
```

A historical fixed-cluster execution resolves a shorter chain:

```text
C0 experimental cycle
→ B0 and historical pilot scenarios
→ fixed-cluster infrastructure profile
→ external lifecycle policy
→ fixed-cluster kubeconfig
→ namespace creation or validation
→ benchmark runtime profiles
→ technical diagnosis profile
→ reporting profile
→ completion-gate profile
→ freeze profile
```

The difference is intentional. `C0` does not resolve a `proxmox-k3s` provider binding and must not trigger provider create/delete operations.

---


## Scheduler, Monitoring Agent, Network Observability, and Rescheduling Profiles

C8 and C9 add configuration families that are not required by earlier controlled placement campaigns.

| Cycle scope | Family | Registry | Primary profile | Purpose |
|---|---|---|---|---|
| C8 | Custom scheduler | `config/scheduler/SCHEDULER_INTEGRATION_INDEX.json` | `config/scheduler/profiles/CS_C8_LOADAWARE_SECOND_SCHEDULER.json` | Installs and validates the scheduler-plugins second scheduler and the `LoadAwareResourcesBalancedAllocation` plugin. |
| C8 | Monitoring agent | `config/mon-agent/MON_AGENT_INDEX.json` | `config/mon-agent/profiles/MA_RESOURCE_AWARE.json` | Selects application namespaces and validates CPU/memory annotations on nodes and deployments. |
| C8 | Controlled rescheduling | `config/rescheduling/RESCHEDULING_INDEX.json` | `config/rescheduling/profiles/RS_C8_RESOURCE_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json` | Captures telemetry, gates on annotations, recreates selected LocalAI pods, and captures post-redeployment evidence. |
| C9 | Load-aware scheduler | `config/scheduler/SCHEDULER_INTEGRATION_INDEX.json` | `config/scheduler/profiles/CS_C9_LOADAWARE_SECOND_SCHEDULER.json` | Enables and validates `LoadAwareResourcesBalancedAllocation` for C9 LOADAWARE variants. |
| C9 | Resource plus network-aware scheduler | `config/scheduler/SCHEDULER_INTEGRATION_INDEX.json` | `config/scheduler/profiles/CS_C9_LOCALAI_RESOURCE_NETWORK_AWARE_SECOND_SCHEDULER.json` | Enables and validates both `LoadAwareResourcesBalancedAllocation` and `NetworkAwareLocalAi` for C9 NETAWARE variants. |
| C9 | Network-aware monitoring agent | `config/mon-agent/MON_AGENT_INDEX.json` | `config/mon-agent/profiles/MA_NETWORK_AWARE.json` | Validates resource annotations, gateway traffic annotations, and network-aware node/deployment annotations. |
| C9 | Network observability | `config/network-observability/NETWORK_OBSERVABILITY_INDEX.json` | `config/network-observability/profiles/NO_MENTAT_C9.json` | Validates Mentat inter-node latency, packet-loss, and bandwidth evidence. |
| C9 | Istio gateway routing | `config/istio-gateway/ISTIO_GATEWAY_INDEX.json` | `config/istio-gateway/profiles/IG_LOCALAI_GATEWAY_ROUTED_C9.json` | Validates that benchmark traffic follows the gateway-routed access path. |
| C9 | Network-aware rescheduling | `config/rescheduling/RESCHEDULING_INDEX.json` | `config/rescheduling/profiles/RS_C9_NETWORK_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json` | Gates controlled redeployment on gateway and network telemetry before the official measurement window. |

These profiles must remain configuration artifacts. They should not embed local secrets, local operator identity, or generated result data.

---

## Source Profiles Versus Generated Runtime Configuration

Source profiles live under `config/` and should be version-controlled when they do not contain local secrets.

Generated runtime configuration lives under `results/` and is produced during execution. For example:

```text
results/experimental-cycles/<cycle>/execution/generated-runtime-configs/
```

Generated runtime configuration is useful for traceability, but it is not the primary source of truth. To change an execution, update the source profiles under `config/`, then regenerate the results.

---

## Naming Conventions

The repository uses structured prefixes to avoid ambiguity.

| Prefix | Meaning | Example |
|---|---|---|
| `C*` | Experimental cycle | `C4` |
| `B*` | Baseline scenario | `B1` |
| `INFRA_*` | Infrastructure profile | `INFRA_C3_1CP_4W_8C16G` |
| `BINDING_*` | Provider binding | `BINDING_INFRA_C1_1CP_2W_8C16G_PROXMOX_K3S` |
| `LC_*` | Lifecycle policy | `LC_EPHEMERAL_DELETE_CLUSTER` |
| `PI_*` | Provisioning integration profile | `PI_C1_PROVIDER_BACKED_BASELINE` |
| `PV_*` | Provisioning validation profile | `PV_C1_PROVIDER_BACKED_BASELINE` |
| `CV_*` | Cluster validation profile | `CV_C1_PROVIDER_BACKED_BASELINE` |
| `AD_*` | Application deployment profile | `AD_C1_PROVIDER_BACKED_BASELINE` |
| `MO_*` | Minimal observability profile | `MO_C1_PROVIDER_BACKED_BASELINE` |
| `TC_*` | Precheck profile | `TC_C0_HISTORICAL_FIXED_CLUSTER` |
| `TD_*` | Technical diagnosis profile | `TD_C5_LATENCY_INJECTION` |
| `RP_*` | Reporting profile | `RP_C6_MULTI_TENANCY` |
| `CG_*` | Completion-gate profile | `CG_C4_PLACEMENT_VARIATION` |
| `FR_*` | Freeze profile | `FR_C2_RESOURCE_VARIATION` |
| `PL_*` | Placement profile | `PL_SPREAD_WORKERS` |
| `PLC_*` | Placement-variation scenario | `PLC_SPREAD_WORKERS` |
| `L*` | Latency profile | `L2_EDGE_REMOTE` |
| `LI_*` | Latency-injection scenario | `LI_L2_EDGE_REMOTE` |
| `TP_*` | Tenancy profile | `TP_TWO_TENANTS_SEPARATED` |
| `MT_*` | Multi-tenancy scenario | `MT_TWO_TENANTS_SEPARATED` |
| `RV_*` | Resource-variation scenario | `RV_4C16G` |
| `NC_*` | Node-count-variation scenario | `NC_4N` |
| `W*` | Historical worker-count pilot scenario | `W2` |
| `WL*` | Historical workload pilot scenario | `WL3` |
| `M*` | Historical model pilot scenario | `M4` |

Do not infer equivalence from similar names. Always follow the explicit references in the cycle profile and indexes.

---

## Baseline Governance

The benchmark suite uses two baseline identifiers with different meanings.

| Baseline | Track | Meaning |
|---|---|---|
| `B0` | `C0` historical fixed-cluster | Historical baseline bound to the original fixed-cluster infrastructure profile. |
| `B1` | `C1` and provider-backed campaigns | Provider-backed baseline used as the reference identity for `C1` through `C9`. |

`B1` must not overwrite `B0`. Provider-backed results must not be placed under historical C0 artifact paths. Historical fixed-cluster results must not be reinterpreted as provider-backed evidence.

---

## Configuration Integrity Checks

Use JSON parsing checks before running large regeneration workflows.

### Windows PowerShell

```powershell
python -c "import json, pathlib; errors=[]; [json.load(open(p, encoding='utf-8')) for p in pathlib.Path('config').rglob('*.json')]; print('All JSON configuration files parsed successfully.')"
```

### Bash

```bash
python -c "import json, pathlib; errors=[]; [json.load(open(p, encoding='utf-8')) for p in pathlib.Path('config').rglob('*.json')]; print('All JSON configuration files parsed successfully.')"
```

Validate that each official cycle profile exists and can be parsed.

### Windows PowerShell

```powershell
python -c "import json, pathlib; [print(json.load(open(pathlib.Path('config/experimental-cycles') / f'C{i}.json', encoding='utf-8')).get('cycleId')) for i in range(7)]"
```

### Bash

```bash
python -c "import json, pathlib; [print(json.load(open(pathlib.Path('config/experimental-cycles') / f'C{i}.json', encoding='utf-8')).get('cycleId')) for i in range(7)]"
```

---

## Change-Control Rules

Apply the following rules when modifying configuration.

1. Do not modify generated artifacts under `results/` to change experimental meaning.
2. Do not edit local provider YAML examples as if they were real execution configuration.
3. Do not commit real credentials, real kubeconfig files, local provider YAML files, or environment-specific secrets.
4. Do not change a scenario profile without checking the cycle profile and scenario-family index that reference it.
5. Do not change an infrastructure profile without checking provider bindings, lifecycle policy, generated kubeconfig path, and reporting/completion assumptions.
6. Do not reuse `B0` or `C0` paths for provider-backed results.
7. Do not treat an unsupported scenario as a failed experiment unless the scenario was expected to be schedulable and the failure is unrelated to the declared resource, placement, latency, or tenancy constraints.
8. When introducing a new official cycle, add the cycle profile, infrastructure references, scenario indexes if needed, diagnosis profile, reporting profile, completion-gate profile, freeze profile, and index entries before execution.

---

## Readiness Checklist

Before executing any cycle or campaign, verify the following.

| Check | Required condition |
|---|---|
| Cycle profile | The intended `C*.json` file exists and references the expected profiles. |
| Infrastructure profile | The cycle or variant references the expected `INFRA_*` profile. |
| Provider binding | Provider-backed profiles resolve to a `BINDING_*` file. |
| Local provider YAML | Provider-backed execution has a populated `.local.yaml` file when real provisioning is required. |
| Lifecycle policy | The selected lifecycle policy matches the intended execution mode. |
| Kubeconfig | Fixed-cluster or generated kubeconfig path is known and intentionally selected. |
| Scenario profile | The scenario family contains the expected variant file. |
| Placement profile | Placement-sensitive scenarios resolve to the intended `PL_*` profile. |
| Latency profile | Latency-sensitive scenarios resolve to the intended `L*` profile. |
| Tenancy profile | Multi-tenancy scenarios resolve to the intended `TP_*` profile. |
| Diagnosis profile | The cycle has a `TD_*` profile. |
| Reporting profile | The cycle has an `RP_*` profile. |
| Completion gate | The cycle has a `CG_*` profile. |
| Freeze profile | The cycle has an `FR_*` profile. |

The detailed execution runbooks describe how to perform these checks in the correct operational order.
