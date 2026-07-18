# LocalAI Deployment Topologies and Placement

## Purpose

This runbook describes the LocalAI application deployment model used by the benchmark suite, with specific focus on worker-mode topologies, Kubernetes manifest composition, placement profiles, and multi-tenant deployment layouts.

It explains how the repository represents:

1. the LocalAI API server;
2. LocalAI RPC workers;
3. worker-count overlays;
4. model-specific server manifests;
5. placement profiles;
6. provider-backed topology compositions;
7. tenant-scoped LocalAI application clusters;
8. resource-aware-scheduler LocalAI topologies;
9. network-aware scheduler LocalAI topologies;
10. placement validation and runtime inspection.

This runbook is not the primary procedure for running benchmark cycles. Full execution procedures are documented in:

- `06-fixed-cluster-c0-execution.md` for the fixed-cluster historical execution track;
- `07-provider-backed-c1-baseline-execution.md` for the provider-backed baseline cycle;
- `08-provider-backed-c2-c6-campaign-execution.md` for provider-backed comparative campaigns;
- `09-default-scheduler-c7-baseline-execution.md` for the default Kubernetes scheduler baseline campaign;
- `10-resource-aware-scheduler-c8-execution.md` for resource-aware-scheduler execution with default and load-aware variants;
- `11-network-aware-scheduler-c9-execution.md` for network-aware scheduler execution with default, load-aware, and network-aware variants.

This runbook provides the architectural and operational reference needed to understand what those execution runbooks deploy and how placement-sensitive scenarios are represented.

---

## Repository Root Assumption

All commands in this runbook must be executed from the repository root.

Windows PowerShell:

```powershell
Set-Location C:\path\to\localai-worker-mode-benchmark-suite
```

Bash:

```bash
cd /path/to/localai-worker-mode-benchmark-suite
```

---

## Scope

This runbook covers only the LocalAI application topology layer.

It covers:

- Kubernetes manifests under `infra/k8s/`;
- application deployment profiles under `config/application-deployment/`;
- placement profiles under `config/placement/`;
- placement-variation scenarios under `config/scenarios/placement-variation/`;
- tenancy profiles under `config/tenancy/`;
- tenant Kustomize compositions under `infra/k8s/compositions/tenancy/`;
- default-scheduler compositions under `infra/k8s/compositions/default-scheduler/`;
- resource-aware-scheduler compositions under `infra/k8s/compositions/resource-aware-scheduler/`;
- network-aware scheduler compositions under `infra/k8s/compositions/network-aware-scheduler/`;
- runtime inspection commands for pod placement and LocalAI worker-mode configuration.

It does not cover:

- local workstation setup;
- secret and kubeconfig handling;
- Proxmox/K3s provisioning lifecycle;
- full cycle execution;
- benchmark load generation;
- diagnosis;
- reporting;
- completion gates;
- freeze operations.

Those topics are covered by the other runbooks in this documentation set.

---

## Application Deployment Responsibility Boundary

The benchmark suite separates infrastructure lifecycle from application deployment.

| Layer | Responsibility | Main locations |
|---|---|---|
| Infrastructure provider | Create, reuse, inspect, and delete provider-backed K3s clusters | `config/infrastructure/`, `scripts/infrastructure/` |
| Cluster validation | Verify that the Kubernetes cluster is usable before deploying workloads | `config/cluster-validation/`, `results/experimental-cycles/<cycle>/infrastructure/validation/` |
| Application deployment | Deploy LocalAI server, RPC workers, services, storage, and runtime configuration | `infra/k8s/`, `config/application-deployment/`, `scripts/application/deployment/` |
| Benchmark execution | Generate traffic and collect client-side metrics | `load-tests/`, `scripts/load/`, `results/experimental-cycles/<cycle>/benchmark/` |
| Analysis pipeline | Diagnose, report, gate, and freeze artifacts | `scripts/analysis/`, `results/experimental-cycles/<cycle>/` |

LocalAI deployment must occur only after the target cluster is reachable and the required validation gates have either passed or been intentionally bypassed for a documented recovery operation.

---

## LocalAI Worker-Mode Architecture

The application topology is based on LocalAI worker mode.

In this repository, the deployed LocalAI topology is composed of:

| Component | Kubernetes object | Purpose |
|---|---|---|
| LocalAI server | `Deployment/localai-server` | HTTP API entry point exposed on port `8080` |
| LocalAI server service | `Service/localai-server` | Cluster-internal service used for port-forwarding and benchmark access |
| RPC worker A | `Deployment/localai-rpc-a` | First llama.cpp RPC worker |
| RPC worker B | `Deployment/localai-rpc-b` | Second llama.cpp RPC worker |
| RPC worker C | `Deployment/localai-rpc-c` | Third llama.cpp RPC worker |
| RPC worker D | `Deployment/localai-rpc-d` | Fourth llama.cpp RPC worker |
| RPC worker services | `Service/localai-rpc-a` through `Service/localai-rpc-d` | Stable DNS names for RPC worker endpoints |
| Runtime config | `ConfigMap/localai-runtime-config` | LocalAI runtime settings and RPC worker list |
| Model storage | `PersistentVolumeClaim/localai-models-pvc` | Persistent model storage mounted at `/models` |

The server receives OpenAI-compatible HTTP requests, while the active RPC workers are exposed to the server through the `LLAMACPP_GRPC_SERVERS` runtime variable.

The active RPC worker set is not inferred dynamically by Kubernetes. It is encoded through the selected Kustomize worker-count overlay and must remain consistent with the intended LocalAI worker-mode topology.

---

## Canonical Namespace

The canonical namespace for the single-tenant LocalAI benchmark topology is:

```text
localai-benchmark
```

The namespace is defined in:

```text
infra/k8s/base/foundation/namespace/00-namespace.yaml
```

The namespace composition is:

```text
infra/k8s/compositions/foundation/namespace
```

C0 must treat this namespace as absent before regeneration. Provider-backed cycles also treat namespace creation as part of the application deployment sequence, unless the cluster is intentionally reused and the namespace already exists.

---

## Manifest Layering Model

The Kubernetes manifests follow a base, overlay, and composition model.

```text
infra/k8s/
├── base/
│   ├── foundation/
│   ├── server/
│   ├── shared/
│   └── topology/
├── overlays/
│   ├── server/
│   └── topology/
└── compositions/
    ├── foundation/
    ├── server/
    ├── shared/
    ├── tenancy/
    └── topology/
```

The intended interpretation is:

| Layer | Role |
|---|---|
| `base/` | Defines reusable Kubernetes resources with conservative defaults |
| `overlays/` | Applies focused patches for model selection, worker count, or placement |
| `compositions/` | Produces deployable Kustomize targets used by execution profiles |

Execution scripts and cycle profiles should reference composition paths, not raw base paths, except for explicitly defined foundation or shared components.

---

## Foundation Compositions

The foundation layer contains namespace and storage resources.

| Composition | Purpose |
|---|---|
| `infra/k8s/compositions/foundation/namespace` | Creates the canonical namespace |
| `infra/k8s/compositions/foundation/storage` | Creates model storage resources |

Render the namespace composition.

Windows PowerShell:

```powershell
kubectl kustomize .\infra\k8s\compositions\foundation\namespace
```

Bash:

```bash
kubectl kustomize ./infra/k8s/compositions/foundation/namespace
```

Render the storage composition.

Windows PowerShell:

```powershell
kubectl kustomize .\infra\k8s\compositions\foundation\storage
```

Bash:

```bash
kubectl kustomize ./infra/k8s/compositions/foundation/storage
```

Apply operations should normally be performed by the execution scripts described in the cycle runbooks. Direct `kubectl apply -k` usage is appropriate only for controlled manual recovery or topology inspection.

---

## Shared RPC Worker Services

RPC worker services are deployed independently from worker replicas.

The shared service composition is:

```text
infra/k8s/compositions/shared/rpc-workers-services
```

It creates ClusterIP services for:

```text
localai-rpc-a
localai-rpc-b
localai-rpc-c
localai-rpc-d
```

These services remain available even when some worker deployments have zero replicas. This is intentional: worker-count overlays determine which RPC deployments are active, while service names remain stable for runtime configuration and topology composition.

Render the RPC worker services composition.

Windows PowerShell:

```powershell
kubectl kustomize .\infra\k8s\compositions\shared\rpc-workers-services
```

Bash:

```bash
kubectl kustomize ./infra/k8s/compositions/shared/rpc-workers-services
```

---

## Server Model Compositions

The LocalAI server is defined in:

```text
infra/k8s/base/server/00-server-workload-and-service.yaml
```

Model-specific overlays are available under:

```text
infra/k8s/overlays/server/models/
```

Deployable server compositions are available under:

```text
infra/k8s/compositions/server/models/
```

The relevant compositions include:

| Composition | Purpose |
|---|---|
| `m1` | Historical fixed-cluster model M1 |
| `m2` | Historical fixed-cluster model M2 |
| `m3` | Historical fixed-cluster model M3 |
| `m4` | Historical fixed-cluster model M4 |
| `m1-provider-backed` | Provider-backed M1 server pinned to the standard provider-backed server node |
| `m1-provider-backed-worker-01` | Provider-backed M1 server pinned to worker `genai-pb-worker-01` for server-separated layouts |

The canonical provider-backed baseline uses:

```text
infra/k8s/compositions/server/models/m1-provider-backed
```

Server-separated layouts may use:

```text
infra/k8s/compositions/server/models/m1-provider-backed-worker-01
```

Render the provider-backed M1 server composition.

Windows PowerShell:

```powershell
kubectl kustomize .\infra\k8s\compositions\server\models\m1-provider-backed
```

Bash:

```bash
kubectl kustomize ./infra/k8s/compositions/server/models/m1-provider-backed
```

Render the server-separated M1 server composition.

Windows PowerShell:

```powershell
kubectl kustomize .\infra\k8s\compositions\server\models\m1-provider-backed-worker-01
```

Bash:

```bash
kubectl kustomize ./infra/k8s/compositions/server/models/m1-provider-backed-worker-01
```

---

## Server Placement Semantics

The base server deployment avoids the control-plane node through required node affinity.

Provider-backed server compositions add explicit node placement using `kubernetes.io/hostname`.

| Server composition | Expected server node |
|---|---|
| `m1-provider-backed` | `genai-pb-worker-02` |
| `m1-provider-backed-worker-01` | `genai-pb-worker-01` |

The server placement choice is part of the placement semantics. A placement profile may change only worker placement, or it may require a different server manifest when the experiment needs to separate the server from selected worker nodes.

---

## Worker Base Topology

The worker base topology is defined in:

```text
infra/k8s/base/topology/
```

The base topology contains four RPC worker deployments:

```text
localai-rpc-a
localai-rpc-b
localai-rpc-c
localai-rpc-d
```

In the base manifest, all RPC workers default to zero replicas. This prevents accidental activation until an explicit worker-count overlay is selected.

The base runtime configuration is:

```text
infra/k8s/base/topology/01-runtime-config.yaml
```

By default, `LLAMACPP_GRPC_SERVERS` is empty. Worker-count overlays populate this variable according to the active worker set.

---

## Worker-Count Overlays

Worker-count overlays are stored in:

```text
infra/k8s/overlays/topology/worker-count/
```

The supported worker-count overlays are:

| Overlay | Active workers | `LLAMACPP_GRPC_SERVERS` |
|---|---:|---|
| `w1` | `localai-rpc-a` | `localai-rpc-a:50051` |
| `w2` | `localai-rpc-a`, `localai-rpc-b` | `localai-rpc-a:50051,localai-rpc-b:50051` |
| `w3` | `localai-rpc-a`, `localai-rpc-b`, `localai-rpc-c` | `localai-rpc-a:50051,localai-rpc-b:50051,localai-rpc-c:50051` |
| `w4` | `localai-rpc-a`, `localai-rpc-b`, `localai-rpc-c`, `localai-rpc-d` | `localai-rpc-a:50051,localai-rpc-b:50051,localai-rpc-c:50051,localai-rpc-d:50051` |

Worker-count overlays must be interpreted as application-topology settings, not infrastructure-node-count settings. For example, `w4` means four active LocalAI RPC workers; it does not by itself imply that the cluster has four Kubernetes worker nodes.

---

## Placement Profiles

Reusable placement intent is represented under:

```text
config/placement/profiles/
```

The placement profile index is:

```text
config/placement/PLACEMENT_PROFILES_INDEX.json
```

Validate the placement profile index.

Windows PowerShell:

```powershell
python -m json.tool .\config\placement\PLACEMENT_PROFILES_INDEX.json > $null
```

Bash:

```bash
python -m json.tool ./config/placement/PLACEMENT_PROFILES_INDEX.json >/dev/null
```

The active placement profiles are:

| Placement profile | Strategy | Primary intent |
|---|---|---|
| `PL_COLOCATED` | `colocated` | Minimize server-worker communication distance by co-locating active RPC workers on `genai-pb-worker-02` |
| `PL_DISTRIBUTED_TWO_NODE` | `distributed_two_node` | Split RPC workers across two provider-backed worker nodes |
| `PL_SPREAD_WORKERS` | `spread_workers` | Spread RPC workers according to available infrastructure worker-node count |
| `PL_SERVER_SEPARATED` | `server_separated_spread_workers` | Place the server on `genai-pb-worker-01` and spread active RPC workers away from it as much as possible |
| `PL_BALANCED_STATIC` | `balanced_static` | Use a static hybrid layout that avoids full concentration while preserving partial locality |

Placement profiles describe topology intent and Kustomize target resolution. Campaign-specific placement scenarios are stored separately under:

```text
config/scenarios/placement-variation/
```

Provider-backed placement-variation scenario identifiers use the `PLC_*` prefix. Reusable placement profiles use the `PL_*` prefix.

---

## Legacy Fixed-Cluster Placement Identifiers

The fixed-cluster historical track may still use legacy placement scenario identifiers:

| Legacy scenario | Canonical interpretation |
|---|---|
| `PL1` | co-located fixed-cluster placement |
| `PL2` | distributed two-node fixed-cluster placement |

Provider-backed cycles must use canonical placement profile identifiers such as `PL_COLOCATED`, `PL_DISTRIBUTED_TWO_NODE`, and campaign-specific `PLC_*` scenario identifiers.

Do not use `PV_*` for placement scenarios. `PV_*` is reserved for provisioning-validation concepts and must not be used as a placement-scenario prefix.

---

## Provider-Backed Placement Topologies

Provider-backed placement topologies are implemented through Kustomize compositions under:

```text
infra/k8s/compositions/topology/
```

### Co-located Provider-Backed Topology

The co-located profile places active RPC workers on `genai-pb-worker-02`.

Representative compositions:

| Composition | Application worker count |
|---|---:|
| `colocated-genai-pb-worker-02-w1` | 1 |
| `colocated-genai-pb-worker-02-w2` | 2 |
| `colocated-genai-pb-worker-02-w3` | 3 |
| `colocated-genai-pb-worker-02-w4` | 4 |

The provider-backed C1 baseline uses:

```text
infra/k8s/compositions/topology/colocated-genai-pb-worker-02-w2
```

Render the C1 baseline worker topology.

Windows PowerShell:

```powershell
kubectl kustomize .\infra\k8s\compositions\topology\colocated-genai-pb-worker-02-w2
```

Bash:

```bash
kubectl kustomize ./infra/k8s/compositions/topology/colocated-genai-pb-worker-02-w2
```

Expected trade-off:

| Benefit | Risk |
|---|---|
| Lower communication distance | Higher CPU and memory contention on the selected worker node |
| Simpler topology interpretation | Lower headroom when increasing worker count |

### Distributed Two-Node Provider-Backed Topology

The distributed two-node profile alternates RPC workers across `genai-pb-worker-01` and `genai-pb-worker-02`.

Representative compositions:

| Composition | Application worker count |
|---|---:|
| `distributed-genai-pb-two-node-w2` | 2 |
| `distributed-genai-pb-two-node-w4` | 4 |

Render the W4 distributed two-node topology.

Windows PowerShell:

```powershell
kubectl kustomize .\infra\k8s\compositions\topology\distributed-genai-pb-two-node-w4
```

Bash:

```bash
kubectl kustomize ./infra/k8s/compositions/topology/distributed-genai-pb-two-node-w4
```

Expected trade-off:

| Benefit | Risk |
|---|---|
| Lower concentration of RPC workers on one node | Additional inter-node communication |
| Initial signal on worker distribution effects | Server may remain close to only part of the worker set |

### Spread Workers Provider-Backed Topology

The spread profile chooses a topology based on the available provider-backed worker-node count.

Representative compositions:

| Composition | Infrastructure worker-node count | Application worker count |
|---|---:|---:|
| `spread-genai-pb-2-worker-nodes-w4` | 2 | 4 |
| `spread-genai-pb-3-worker-nodes-w4` | 3 | 4 |
| `spread-genai-pb-4-worker-nodes-w4` | 4 | 4 |

Render the four-node spread topology.

Windows PowerShell:

```powershell
kubectl kustomize .\infra\k8s\compositions\topology\spread-genai-pb-4-worker-nodes-w4
```

Bash:

```bash
kubectl kustomize ./infra/k8s/compositions/topology/spread-genai-pb-4-worker-nodes-w4
```

Expected trade-off:

| Benefit | Risk |
|---|---|
| Lower worker concentration | Network overhead may dominate tightly coupled worker-mode requests |
| Direct comparison against co-located placement | Server may remain close to only part of the worker set |

### Server-Separated Provider-Backed Topology

The server-separated profile places the LocalAI server on `genai-pb-worker-01` and active RPC workers across the remaining worker nodes as defined by the W4 topology.

Representative composition:

```text
infra/k8s/compositions/topology/server-separated-genai-pb-worker-01-spread-w4
```

This placement is meaningful only when the corresponding server composition is also selected:

```text
infra/k8s/compositions/server/models/m1-provider-backed-worker-01
```

Render the server-separated worker topology.

Windows PowerShell:

```powershell
kubectl kustomize .\infra\k8s\compositions\topology\server-separated-genai-pb-worker-01-spread-w4
```

Bash:

```bash
kubectl kustomize ./infra/k8s/compositions/topology/server-separated-genai-pb-worker-01-spread-w4
```

Render the matching server manifest.

Windows PowerShell:

```powershell
kubectl kustomize .\infra\k8s\compositions\server\models\m1-provider-backed-worker-01
```

Bash:

```bash
kubectl kustomize ./infra/k8s/compositions/server/models/m1-provider-backed-worker-01
```

Expected trade-off:

| Benefit | Risk |
|---|---|
| Separates server and RPC-worker resource demand | Inter-node communication becomes mandatory |
| Exposes communication-vs-contention behavior | Requires a sufficiently large provider-backed worker-node set |

### Balanced Static Provider-Backed Topology

The balanced static profile defines a static hybrid layout for W4.

Representative composition:

```text
infra/k8s/compositions/topology/balanced-static-genai-pb-w4
```

Render the balanced static topology.

Windows PowerShell:

```powershell
kubectl kustomize .\infra\k8s\compositions\topology\balanced-static-genai-pb-w4
```

Bash:

```bash
kubectl kustomize ./infra/k8s/compositions/topology/balanced-static-genai-pb-w4
```

Expected trade-off:

| Benefit | Risk |
|---|---|
| Avoids a fully compact topology | Static placement may not reflect runtime resource pressure |
| Preserves partial locality | Requires at least three provider-backed worker nodes for meaningful interpretation |

---

## Placement Comparison Matrix

The following matrix summarizes the intended placement semantics.

| Profile | Server node | Worker placement | Best used for |
|---|---|---|---|
| `PL_COLOCATED` | `genai-pb-worker-02` | Active workers concentrated on `genai-pb-worker-02` | Communication-minimized baseline |
| `PL_DISTRIBUTED_TWO_NODE` | `genai-pb-worker-02` | Workers split between `genai-pb-worker-01` and `genai-pb-worker-02` | Two-node distribution analysis |
| `PL_SPREAD_WORKERS` | `genai-pb-worker-02` | Workers spread across available worker nodes | Node-count-aware worker spreading |
| `PL_SERVER_SEPARATED` | `genai-pb-worker-01` | Workers spread across separate worker nodes | Server isolation and inter-node communication analysis |
| `PL_BALANCED_STATIC` | `genai-pb-worker-02` | Static hybrid worker distribution | Controlled hybrid comparison |

A placement comparison is meaningful only when all non-placement dimensions are fixed unless the scenario explicitly declares otherwise.

For placement-sensitive cycles, fixed dimensions normally include:

- infrastructure profile;
- model scenario;
- workload scenario;
- application worker count;
- prompt;
- temperature;
- benchmark protocol;
- measurement duration;
- diagnosis profile;
- reporting profile.

---

## Placement-Variation Scenarios

Provider-backed placement-variation scenarios are stored in:

```text
config/scenarios/placement-variation/
```

The active scenarios are:

| Scenario | Placement profile | Purpose |
|---|---|---|
| `PLC_COLOCATED` | `PL_COLOCATED` | Concentrated server-worker layout |
| `PLC_DISTRIBUTED_TWO_NODE` | `PL_DISTRIBUTED_TWO_NODE` | Two-node worker distribution |
| `PLC_SPREAD_WORKERS` | `PL_SPREAD_WORKERS` | Spread workers across provider-backed worker nodes |
| `PLC_SERVER_SEPARATED` | `PL_SERVER_SEPARATED` | Server separated from the main worker layout |
| `PLC_BALANCED_STATIC` | `PL_BALANCED_STATIC` | Static hybrid placement |

Validate the placement-variation scenario index.

Windows PowerShell:

```powershell
python -m json.tool .\config\scenarios\placement-variation\PLACEMENT_VARIATION_SCENARIOS_INDEX.json > $null
```

Bash:

```bash
python -m json.tool ./config/scenarios/placement-variation/PLACEMENT_VARIATION_SCENARIOS_INDEX.json >/dev/null
```

---

## Application Deployment Profiles

Application deployment profiles are stored in:

```text
config/application-deployment/
```

The static C1 provider-backed baseline deployment profile is:

```text
config/application-deployment/profiles/AD_C1_PROVIDER_BACKED_BASELINE.json
```

Provider-backed campaign variants generate runtime deployment profiles under:

```text
results/experimental-cycles/<cycle>/execution/generated-runtime-configs/<variant>/
```

This separation is intentional:

| Profile type | Purpose |
|---|---|
| Static deployment profile | Used for stable baseline or standalone deployment definitions |
| Runtime-generated deployment profile | Used by campaign variants that bind a specific scenario, infrastructure, placement profile, kubeconfig, and artifact root |

Validate the static application deployment profile.

Windows PowerShell:

```powershell
python -m json.tool .\config\application-deployment\profiles\AD_C1_PROVIDER_BACKED_BASELINE.json > $null
```

Bash:

```bash
python -m json.tool ./config/application-deployment/profiles/AD_C1_PROVIDER_BACKED_BASELINE.json >/dev/null
```

Plan the provider-backed C1 deployment without applying resources.

Windows PowerShell:

```powershell
.\scripts\application\deployment\Start-ProviderBackedLocalAIDeployment.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -Action plan `
  -DryRun
```

Bash:

```bash
./scripts/application/deployment/start-provider-backed-localai-deployment.sh \
  --cycle-config ./config/experimental-cycles/C1.json \
  --action plan \
  --dry-run
```

---

## Deployment Apply Order

The application deployment profile declares the Kustomize apply order.

For the provider-backed C1 baseline, the order is:

1. namespace;
2. storage;
3. RPC worker services;
4. server model;
5. worker topology.

The order is important because:

- the namespace must exist before namespaced resources are applied;
- storage must exist before the server mounts the model volume;
- RPC worker services must exist before the runtime config points to worker DNS names;
- the server model composition determines the server image, model and placement;
- the topology composition activates the intended worker count and worker placement.

Do not manually reorder these steps unless performing a controlled recovery and documenting the reason.

---

## Runtime Placement Inspection

After deployment, the effective placement must be verified from the cluster state, not only from configuration files.

Set the kubeconfig path for the target execution.

Windows PowerShell:

```powershell
$KUBECONFIG_PATH = ".\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig"
```

Bash:

```bash
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig"
```

List pods with node placement.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH -n localai-benchmark get pods -o wide
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" -n localai-benchmark get pods -o wide
```

List LocalAI deployments.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH -n localai-benchmark get deployments
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" -n localai-benchmark get deployments
```

Inspect the active RPC worker list used by the LocalAI server.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH -n localai-benchmark get configmap localai-runtime-config -o jsonpath="{.data.LLAMACPP_GRPC_SERVERS}"
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" -n localai-benchmark get configmap localai-runtime-config -o jsonpath='{.data.LLAMACPP_GRPC_SERVERS}'
```

Inspect pod scheduling events when a placement is not schedulable.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH -n localai-benchmark get events --sort-by=.lastTimestamp
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" -n localai-benchmark get events --sort-by=.lastTimestamp
```

Inspect node labels used by placement constraints.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH get nodes --show-labels
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" get nodes --show-labels
```

---

## Rollout Validation

Verify the LocalAI server rollout.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH -n localai-benchmark rollout status deployment/localai-server --timeout=600s
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" -n localai-benchmark rollout status deployment/localai-server --timeout=600s
```

Verify RPC worker rollouts for an active W2 topology.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH -n localai-benchmark rollout status deployment/localai-rpc-a --timeout=600s
kubectl --kubeconfig $KUBECONFIG_PATH -n localai-benchmark rollout status deployment/localai-rpc-b --timeout=600s
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" -n localai-benchmark rollout status deployment/localai-rpc-a --timeout=600s
kubectl --kubeconfig "$KUBECONFIG_PATH" -n localai-benchmark rollout status deployment/localai-rpc-b --timeout=600s
```

For W4 topologies, verify all four RPC workers.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH -n localai-benchmark rollout status deployment/localai-rpc-a --timeout=600s
kubectl --kubeconfig $KUBECONFIG_PATH -n localai-benchmark rollout status deployment/localai-rpc-b --timeout=600s
kubectl --kubeconfig $KUBECONFIG_PATH -n localai-benchmark rollout status deployment/localai-rpc-c --timeout=600s
kubectl --kubeconfig $KUBECONFIG_PATH -n localai-benchmark rollout status deployment/localai-rpc-d --timeout=600s
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" -n localai-benchmark rollout status deployment/localai-rpc-a --timeout=600s
kubectl --kubeconfig "$KUBECONFIG_PATH" -n localai-benchmark rollout status deployment/localai-rpc-b --timeout=600s
kubectl --kubeconfig "$KUBECONFIG_PATH" -n localai-benchmark rollout status deployment/localai-rpc-c --timeout=600s
kubectl --kubeconfig "$KUBECONFIG_PATH" -n localai-benchmark rollout status deployment/localai-rpc-d --timeout=600s
```

A rollout failure caused by unsatisfied node affinity, insufficient CPU, or insufficient memory must be interpreted in the context of the active cycle. In placement and resource-variation campaigns, unsupported scenarios may be valid evidence rather than a documentation error.

---

## LocalAI API Access Check

Expose the LocalAI server through port-forwarding.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH -n localai-benchmark port-forward service/localai-server 8080:8080
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" -n localai-benchmark port-forward service/localai-server 8080:8080
```

Run the following checks from a separate terminal while the port-forward is active.

Check the model list endpoint.

Windows PowerShell:

```powershell
Invoke-RestMethod -Uri "http://localhost:8080/v1/models" -Method Get
```

Bash:

```bash
curl -sS http://localhost:8080/v1/models
```

Send a minimal chat-completion request.

Windows PowerShell:

```powershell
$Body = @{
  model = "llama-3.2-1b-instruct:q4_k_m"
  messages = @(
    @{
      role = "user"
      content = "Reply with only READY."
    }
  )
  temperature = 0.1
  max_tokens = 8
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Uri "http://localhost:8080/v1/chat/completions" `
  -Method Post `
  -ContentType "application/json" `
  -Body $Body
```

Bash:

```bash
curl -sS http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.2-1b-instruct:q4_k_m",
    "messages": [
      {
        "role": "user",
        "content": "Reply with only READY."
      }
    ],
    "temperature": 0.1,
    "max_tokens": 8
  }'
```

Benchmark cycle scripts perform their own smoke and readiness checks. These manual commands are intended for controlled inspection and recovery.

---

## Multi-Tenant Topologies

Multi-tenant application-cluster layouts are represented under:

```text
config/tenancy/
infra/k8s/compositions/tenancy/
```

The tenancy profile index is:

```text
config/tenancy/TENANCY_PROFILES_INDEX.json
```

Validate the tenancy profile index.

Windows PowerShell:

```powershell
python -m json.tool .\config\tenancy\TENANCY_PROFILES_INDEX.json > $null
```

Bash:

```bash
python -m json.tool ./config/tenancy/TENANCY_PROFILES_INDEX.json >/dev/null
```

The active tenancy profiles are:

| Tenancy profile | Tenant count | Benchmark tenant | Purpose |
|---|---:|---|---|
| `TP_SINGLE_TENANT_REFERENCE` | 1 | `tenant-a` | Single-tenant reference deployment |
| `TP_TWO_TENANTS_SEPARATED` | 2 | `tenant-a` | Two LocalAI tenant clusters on disjoint worker-node pairs |
| `TP_TWO_TENANTS_MIXED_MODELS` | 2 | `tenant-a` | Two tenants using different model variants |
| `TP_TWO_TENANTS_SHARED_NODEPOOL` | 2 | `tenant-a` | Two tenants competing on the same worker-node pair |

Tenant-scoped LocalAI application clusters use separate namespaces, such as:

```text
genai-tenant-a
genai-tenant-b
```

The benchmark target remains the declared benchmark tenant. Co-tenant clusters remain deployed to expose resource-contention and placement effects.

Render the mixed-model two-tenant composition.

Windows PowerShell:

```powershell
kubectl kustomize .\infra\k8s\compositions\tenancy\two-tenants-mixed-models
```

Bash:

```bash
kubectl kustomize ./infra/k8s/compositions/tenancy/two-tenants-mixed-models
```

Render the separated two-tenant composition.

Windows PowerShell:

```powershell
kubectl kustomize .\infra\k8s\compositions\tenancy\two-tenants-separated
```

Bash:

```bash
kubectl kustomize ./infra/k8s/compositions/tenancy/two-tenants-separated
```

Render the shared-nodepool two-tenant composition.

Windows PowerShell:

```powershell
kubectl kustomize .\infra\k8s\compositions\tenancy\two-tenants-shared-nodepool
```

Bash:

```bash
kubectl kustomize ./infra/k8s/compositions/tenancy/two-tenants-shared-nodepool
```

After deploying a tenant scenario through the campaign runner, inspect tenant namespaces.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH get namespaces
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" get namespaces
```

Inspect tenant A pod placement.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH -n genai-tenant-a get pods -o wide
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" -n genai-tenant-a get pods -o wide
```

Inspect tenant B pod placement.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH -n genai-tenant-b get pods -o wide
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" -n genai-tenant-b get pods -o wide
```

---

## Default-Scheduler Compositions

The default-scheduler composition tree is:

```text
infra/k8s/compositions/default-scheduler/
```

This tree is used by `C7` to deploy tenant-scoped LocalAI worker-mode workloads without hard pod placement controls.

Default-scheduler compositions must preserve the following rule:

```text
Kubernetes decides pod-to-node placement.
```

Therefore, C7 compositions must not use:

```text
spec.nodeName
hostname-specific nodeSelector
hostname-specific nodeAffinity
controlled placement overlays
```

They may still use general constraints such as:

- control-plane exclusion;
- generic worker nodepool selection;
- resource requests;
- resource limits;
- tenant labels;
- application role labels.

This distinction is important. Controlled placement scenarios are used to characterize known topologies. C7 scenarios are used to observe how Kubernetes places workloads when the scheduler is not given hard pod locations.

---

## Default-Scheduler Tenant Layouts

C7 scenarios can deploy one, two, or three tenant-scoped LocalAI application clusters.

The tenant namespace convention is:

```text
genai-tenant-a
genai-tenant-b
genai-tenant-c
```

Each tenant layout preserves a logical tenant identifier separate from the namespace:

```text
tenant-a -> genai-tenant-a
tenant-b -> genai-tenant-b
tenant-c -> genai-tenant-c
```

This distinction must be retained in generated runtime configuration, rollout targets, smoke validation, benchmark artifacts, scheduler evidence, diagnosis, and reporting.

A typical tenant contains:

- a LocalAI API server;
- two LocalAI RPC workers;
- tenant-scoped services;
- tenant labels;
- role labels for server and worker components;
- resource requests and limits.

The LocalAI worker count per tenant is expressed in source scenario profiles as:

```text
localAiWorkerCountPerTenant
```

Generated runtime artifacts may include resolved or derived fields, but source scenario profiles should use the canonical field above.

---

## Default-Scheduler Placement Inspection

For C7, placement inspection is not a validation of an expected node map. It is evidence capture.

Use:

```text
scripts/observability/scheduler/capture-scheduler-decisions.py
```

to preserve the actual placement chosen by Kubernetes.

The evidence should include:

- tenant ID;
- namespace;
- deployment;
- pod name and UID;
- assigned node;
- role;
- phase;
- resource requests and limits;
- restart count;
- Kubernetes events;
- failed scheduling events when present;
- placement classification.

Common placement classifications include:

| Classification | Interpretation |
|---|---|
| `server_worker_colocated` | Server and worker pods for the same tenant are on the same node. |
| `server_worker_split` | Server and worker pods for the same tenant are split across nodes. |
| `tenant_interference_risk` | Pods from multiple tenants are co-located on the same node. |
| `resource_contention_risk` | Multiple resource-intensive pods share a node. |
| `latency_sensitive_split` | Communicating components are split across latency-affected nodes. |
| `fully_spread` | Components are broadly distributed across nodes. |

For C7, these classifications are not success/failure labels by themselves. They must be interpreted together with latency, throughput, errors, tenant traffic profile, and resource-pressure evidence.

---


## Resource-Aware Scheduler Compositions

The resource-aware-scheduler composition tree is:

```text
infra/k8s/compositions/resource-aware-scheduler/
```

This tree is used by `C8` to deploy paired default and load-aware LocalAI worker-mode workloads. The same logical scenario must be represented with two scheduler modes:

```text
RA_DEFAULT_*   -> Kubernetes default scheduler
RA_LOADAWARE_* -> scheduler-plugins-scheduler
```

C8 compositions must preserve these rules:

1. Default variants must not set `spec.schedulerName` on LocalAI workloads.
2. Load-aware variants must set `spec.schedulerName: scheduler-plugins-scheduler`.
3. LocalAI deployments and pod templates must expose `group` and `app` labels.
4. Service selectors must remain aligned with deployment selectors and pod-template labels.
5. Tenant namespaces must be compatible with the `mon-agent/enabled=true` namespace-selection policy.
6. Hard placement controls must not be used to predetermine pod-to-node placement.

A resource-aware-scheduler tenant typically contains:

- `localai-server`;
- `localai-rpc-a`;
- `localai-rpc-b`;
- tenant-scoped services;
- `group` and `app` labels for runtime metrics association;
- descriptive `localai.benchmark/*` labels for artifact interpretation.

### Resource-Aware Scheduler Manifest Rendering

Render the resource-aware-scheduler compositions before real execution when validating local changes.

#### Windows PowerShell

```powershell
kubectl kustomize .\infra\k8s\compositions\resource-aware-scheduler
```

#### Bash

```bash
kubectl kustomize ./infra/k8s/compositions/resource-aware-scheduler
```

If the composition root contains multiple scenario subdirectories, render the scenario-specific directory selected by the active C8 runtime configuration.

### C8 Placement Inspection

C8 placement inspection is comparative evidence. For each logical scenario, compare:

```text
default variant placement
load-aware variant placement
```

The scheduler decision evidence should be interpreted together with:

- scheduler mode;
- effective scheduler name;
- node CPU and memory annotations;
- deployment CPU and memory annotations;
- pre- and post-redeployment placement;
- benchmark latency, throughput, and failure metrics.

---

## Placement and Schedulability Interpretation

Placement is not only a performance variable. It is also a schedulability variable.

A placement may fail because:

- required node names do not exist;
- node labels do not match;
- the target node is a control-plane node and control-plane scheduling is not allowed;
- requested CPU is unavailable;
- requested memory is unavailable;
- multiple high-demand LocalAI components are concentrated on the same node;
- tenant clusters compete for the same worker-node pool;
- latency injection or topology-specific constraints expose a deployment that is technically valid but operationally unsuitable.

When a placement variant is declared unsupported by the pipeline, the first diagnostic question should not be “which command failed?”. The first diagnostic question should be:

```text
Does this unsupported result provide evidence about the resource, topology, or placement limits of the selected scenario?
```

Unsupported scenarios must be preserved when they are expected outputs of controlled variation campaigns.

---

## Correct Use of Direct `kubectl apply`

Direct application of a Kustomize composition is useful for inspection and recovery, but it is not the preferred way to regenerate official artifacts.

For controlled manual validation, apply the namespace composition.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH apply -k .\infra\k8s\compositions\foundation\namespace
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" apply -k ./infra/k8s/compositions/foundation/namespace
```

Apply storage.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH apply -k .\infra\k8s\compositions\foundation\storage
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" apply -k ./infra/k8s/compositions/foundation/storage
```

Apply shared RPC worker services.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH apply -k .\infra\k8s\compositions\shared\rpc-workers-services
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" apply -k ./infra/k8s/compositions/shared/rpc-workers-services
```

Apply the provider-backed M1 server composition.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH apply -k .\infra\k8s\compositions\server\models\m1-provider-backed
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" apply -k ./infra/k8s/compositions/server/models/m1-provider-backed
```

Apply the C1 co-located W2 worker topology.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH apply -k .\infra\k8s\compositions\topology\colocated-genai-pb-worker-02-w2
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" apply -k ./infra/k8s/compositions/topology/colocated-genai-pb-worker-02-w2
```

For official regeneration, use the cycle and campaign execution runbooks instead of manually applying these resources.

---

## Cleanup of Application Resources

Application cleanup may be required when manually testing topology compositions.

Delete the canonical single-tenant namespace.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH delete namespace localai-benchmark --ignore-not-found
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" delete namespace localai-benchmark --ignore-not-found
```

Delete tenant namespaces.

Windows PowerShell:

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH delete namespace genai-tenant-a --ignore-not-found
kubectl --kubeconfig $KUBECONFIG_PATH delete namespace genai-tenant-b --ignore-not-found
```

Bash:

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" delete namespace genai-tenant-a --ignore-not-found
kubectl --kubeconfig "$KUBECONFIG_PATH" delete namespace genai-tenant-b --ignore-not-found
```

Cleanup of provider-backed clusters is not an application-deployment concern. Use the provider lifecycle runbook for infrastructure deletion.

---

## Change-Control Rules

When modifying LocalAI deployment topologies, follow these rules:

1. Do not change model, workload, worker count, and placement in the same profile unless the scenario explicitly declares multiple varied dimensions.
2. Do not edit generated runtime profiles manually unless performing documented recovery.
3. Do not change node names inside a placement overlay without also updating the corresponding placement profile and scenario metadata.
4. Do not add a new placement scenario without linking it to a reusable placement profile.
5. Do not reuse legacy `PL1` and `PL2` identifiers for provider-backed scenarios.
6. Do not use `PV_*` identifiers for placement scenarios.
7. Do not interpret a placement experiment without inspecting pod placement, node resource pressure, pending pods, restarts, and events.
8. Do not treat unsupported scenarios as failures when they are produced by controlled resource or placement variation.

---

## Readiness Checklist

Before considering a LocalAI deployment topology ready for benchmark execution, verify that:

- the target kubeconfig reaches the intended cluster;
- the required namespace exists or is created by the deployment sequence;
- the storage composition has been applied;
- the RPC worker services exist;
- the selected server model composition is correct;
- the selected worker topology composition is correct;
- the selected placement profile matches the scenario metadata;
- `LLAMACPP_GRPC_SERVERS` contains exactly the expected active RPC workers;
- expected inactive RPC workers have zero replicas;
- pod placement matches the expected node map for controlled placement scenarios, or scheduler decision evidence exists for default-scheduler scenarios;
- all required deployments reach the Ready state;
- the LocalAI server responds through `/v1/models`;
- the LocalAI server responds through `/v1/chat/completions`;
- unsupported placement outcomes, if any, are captured as artifacts rather than discarded.

---

## Next Runbook

After understanding the LocalAI deployment and placement model, continue with:

```text
13-load-generation-observability-and-artifacts.md
```

That runbook explains how load generation, metric collection, runtime evidence, and benchmark artifacts are organized.
