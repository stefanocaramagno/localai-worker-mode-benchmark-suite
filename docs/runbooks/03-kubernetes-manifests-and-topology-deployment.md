# 03. Kubernetes Manifests and Topology Deployment

## Objective

Deploy the Kubernetes resources that define the benchmark system topology, using the repository's Kustomize-based manifest model exactly as intended by the current pipeline.

This runbook explains how the Kubernetes manifests are organized, how the foundation, shared services, topology, and server resources are composed, and how to deploy a valid LocalAI worker-mode target environment in a controlled and repeatable way.

The goal of this runbook is not only to apply manifests, but to do so in the correct order, with the correct interpretation of each layer, and with post-deployment validation steps that confirm the topology is ready for smoke validation and benchmark execution.

---

## When to Execute

Execute this runbook in any of the following situations:

- before the first deployment of the benchmark topology on a fresh cluster;
- after the cluster has been recreated;
- after the project namespace has been deleted or reset;
- after changing the target model composition;
- after changing worker-count or placement compositions;
- before re-running the pipeline if Kubernetes resources must be recreated from manifests rather than reused.

This runbook should be executed **after** cluster access and repository setup have already been validated.

---

## Scope

This runbook covers the Kubernetes deployment layer of the repository, including:

- namespace creation;
- persistent storage claim creation;
- shared RPC worker services;
- LocalAI server deployment and service;
- LocalAI RPC worker deployments;
- runtime configuration for worker-mode gRPC sharding;
- worker-count and placement compositions;
- model-specific server compositions.

This runbook does **not** cover:

- benchmark pre-check execution;
- API smoke validation details;
- Locust-based load generation;
- results collection or diagnosis;
- cleanup and rerun procedures.

Those phases are handled by their dedicated runbooks.

---

## Deployment Model Overview

The repository uses a layered Kubernetes manifest structure based on Kustomize.

The deployment model is intentionally split into four logical areas:

1. **foundation**
2. **shared services**
3. **server composition**
4. **topology composition**

This structure allows the pipeline to keep the overall system stable while varying only the experimental dimensions that matter for a given scenario.

---

## Repository Areas Covered by This Runbook

The Kubernetes resources relevant to this runbook are stored under:

```text
infra/k8s/
├── base/
│   ├── foundation/
│   │   ├── 00-namespace.yaml
│   │   └── 01-storage.yaml
│   ├── server/
│   │   └── 00-server-workload-and-service.yaml
│   ├── shared/
│   │   └── 00-rpc-workers-services.yaml
│   └── topology/
│       ├── 00-workers-deployments.yaml
│       └── 01-runtime-config.yaml
├── overlays/
│   ├── server/
│   │   └── models/
│   │       ├── m1/
│   │       ├── m2/
│   │       ├── m3/
│   │       └── m4/
│   └── topology/
│       ├── placement/
│       │   ├── colocated-sc-app-02/
│       │   └── distributed-two-node/
│       └── worker-count/
│           ├── w1/
│           ├── w2/
│           ├── w3/
│           └── w4/
└── compositions/
    ├── foundation/
    │   ├── namespace/
    │   └── storage/
    ├── server/
    │   └── models/
    │       ├── m1/
    │       ├── m2/
    │       ├── m3/
    │       └── m4/
    ├── shared/
    │   └── rpc-workers-services/
    └── topology/
        ├── colocated-sc-app-02-w1/
        ├── colocated-sc-app-02-w2/
        ├── colocated-sc-app-02-w3/
        ├── colocated-sc-app-02-w4/
        └── distributed-two-node-w2/
```

All deployments in this runbook must be driven from these compositions, not from ad hoc manifest edits.

---

## Core Design Principles

The current manifest architecture follows these design principles.

### 1. The namespace and storage are deployed explicitly

The pipeline does not assume the project namespace or the model storage claim already exist.

### 2. Shared RPC services are deployed separately from worker deployments

The service objects for `localai-rpc-a` through `localai-rpc-d` are applied independently, so that the network endpoints exist consistently across worker-count scenarios.

### 3. The LocalAI server and RPC workers are separated

The server and the worker topology are not baked into one single manifest. This makes it possible to vary model and worker topology independently.

### 4. Worker topology is built from a composition of two dimensions

Worker topology is controlled by combining:

- a **placement policy**;
- a **worker-count policy**.

### 5. The server remains fixed on `sc-app-02`

The current server deployment uses a `nodeSelector` that pins `localai-server` to `sc-app-02`. This is part of the active deployment design and must be treated as a controlled infrastructure constraint during the current pipeline.

---

## Foundation Resources

## Namespace

The namespace is defined in:

```text
infra/k8s/base/foundation/00-namespace.yaml
```

### Current namespace

```text
genai-thesis
```

### Resource summary

- creates the namespace used by the project;
- sets `istio-injection: "disabled"` on the namespace metadata.

### Why it matters

All subsequent resources assume that this namespace already exists.

---

## Storage

The storage claim is defined in:

```text
infra/k8s/base/foundation/01-storage.yaml
```

### Current PVC

```text
localai-models-pvc
```

### Current storage request

```text
10Gi
```

### Why it matters

The LocalAI server mounts this PVC at `/models`, and the deployment assumes that the cluster provides a default storage class capable of dynamically provisioning the claim.

---

## Shared RPC Services

The shared service definitions are stored in:

```text
infra/k8s/base/shared/00-rpc-workers-services.yaml
```

### Services created

- `localai-rpc-a`
- `localai-rpc-b`
- `localai-rpc-c`
- `localai-rpc-d`

### Port model

Each service exposes:

- service port: `50051`
- target port: `50051`
- protocol: TCP

### Why they are shared

These services are stable network identities for the RPC workers. The worker-count overlays then decide which deployments actually run with `replicas: 1` and which remain disabled with `replicas: 0`.

---

## Server Base Manifest

The LocalAI server base resource is stored in:

```text
infra/k8s/base/server/00-server-workload-and-service.yaml
```

### Server deployment name

```text
localai-server
```

### Service name

```text
localai-server
```

### Important characteristics

The base server manifest currently defines:

- one server replica;
- `Recreate` deployment strategy;
- container image:

```text
quay.io/go-skynet/local-ai:v4.1.0
```

- container port `8080`;
- PVC mount at `/models`;
- runtime config loaded from `localai-runtime-config`;
- resource requests:
  - CPU: `2`
  - memory: `4Gi`
- resource limits:
  - CPU: `4`
  - memory: `8Gi`
- `nodeSelector` fixed to:

```text
kubernetes.io/hostname: sc-app-02
```

### Current base model argument

The base manifest directly uses:

```text
llama-3.2-1b-instruct:q4_k_m
```

This corresponds to the current `m1` baseline server model composition.

---

## Topology Base Manifests

The topology base is split into two files.

### Worker deployments

```text
infra/k8s/base/topology/00-workers-deployments.yaml
```

This file defines the four worker deployments:

- `localai-rpc-a`
- `localai-rpc-b`
- `localai-rpc-c`
- `localai-rpc-d`

### Runtime configuration

```text
infra/k8s/base/topology/01-runtime-config.yaml
```

This file defines the `ConfigMap` named:

```text
localai-runtime-config
```

### Base runtime configuration values

The current base runtime config sets:

- `LOCALAI_MODELS_PATH=/models`
- `LOCALAI_THREADS=4`
- `LOCALAI_CONTEXT_SIZE=1024`
- `LLAMACPP_GRPC_SERVERS=""`

The `LLAMACPP_GRPC_SERVERS` value is intentionally overridden by the worker-count overlays.

---

## Worker Deployment Model

Each worker deployment is a LocalAI RPC process launched through:

```text
/local-ai p2p-worker llama-cpp-rpc --llama-cpp-args="-H 0.0.0.0 -p 50051"
```

and installs the backend dynamically through:

```text
/local-ai backends install llama-cpp
```

### Resource profile per worker

Each worker currently requests:

- CPU: `2`
- memory: `4Gi`

and defines limits of:

- CPU: `4`
- memory: `8Gi`

### Base scheduling intent

In the topology base, worker deployments are initially configured with:

- `replicas: 0`
- node affinity targeting `sc-app-02`
- control-plane exclusion through `node-role.kubernetes.io/control-plane DoesNotExist`

The actual worker count and placement used for a scenario are then resolved by composition patches.

---

## Server Model Compositions

The server model compositions are stored under:

```text
infra/k8s/compositions/server/models/
```

### Available model compositions

- `m1`
- `m2`
- `m3`
- `m4`

### Interpretation

Each server model composition resolves the LocalAI server deployment to a specific model argument.

### Current behavior

- `m1` uses the base server manifest as-is;
- `m2`, `m3`, and `m4` apply a strategic merge patch to override the model argument.

### Operational rule

Always deploy the server through the model composition directory, not by applying the base server manifest directly, unless you are deliberately performing low-level manifest debugging.

---

## Placement Overlays

The placement overlays are stored in:

```text
infra/k8s/overlays/topology/placement/
```

### Available placement policies

#### `colocated-sc-app-02`

All workers are constrained to:

```text
sc-app-02
```

This is the current baseline placement policy.

#### `distributed-two-node`

Workers are split across:

- `sc-app-01`
- `sc-app-02`

according to the current patch design:

- `localai-rpc-a` -> `sc-app-01`
- `localai-rpc-b` -> `sc-app-02`
- `localai-rpc-c` -> `sc-app-01`
- `localai-rpc-d` -> `sc-app-02`

### Interpretation boundary

The current placement study varies the **worker placement only**. The LocalAI server remains pinned to `sc-app-02` in all current server compositions.

---

## Worker-Count Overlays

The worker-count overlays are stored in:

```text
infra/k8s/overlays/topology/worker-count/
```

### Available worker-count policies

- `w1`
- `w2`
- `w3`
- `w4`

### What each worker-count overlay changes

Each worker-count policy patches two things:

1. **worker replicas**
2. **`LLAMACPP_GRPC_SERVERS`** in the runtime config map

### Example resolution

#### `w1`

- active worker deployments: `a`
- runtime config:

```text
LLAMACPP_GRPC_SERVERS=localai-rpc-a:50051
```

#### `w2`

- active worker deployments: `a`, `b`
- runtime config:

```text
LLAMACPP_GRPC_SERVERS=localai-rpc-a:50051,localai-rpc-b:50051
```

#### `w3`

- active worker deployments: `a`, `b`, `c`

#### `w4`

- active worker deployments: `a`, `b`, `c`, `d`

### Operational consequence

The topology is not valid unless the worker replica patch and the runtime-config patch are aligned. The existing composition directories already guarantee this alignment and must therefore be used as the canonical deployment entry points.

---

## Topology Compositions

The topology compositions are stored under:

```text
infra/k8s/compositions/topology/
```

These directories are the canonical deployable topology units.

### Available compositions

- `colocated-sc-app-02-w1`
- `colocated-sc-app-02-w2`
- `colocated-sc-app-02-w3`
- `colocated-sc-app-02-w4`
- `distributed-two-node-w2`

### What a topology composition contains

Each topology composition references:

- the worker deployment base;
- the runtime-config base;
- one placement patch;
- one worker-count patch;
- one `LLAMACPP_GRPC_SERVERS` patch.

### Deployment rule

Do not try to assemble placement and worker-count manually during normal execution. Apply the correct composition directory with `kubectl apply -k`.

---

## Canonical Deployment Order

The repository scripts establish a consistent apply order. The same order should be used when deploying manually.

### Required order

1. namespace composition
2. shared RPC worker services composition
3. storage composition
4. topology composition
5. server model composition

### Canonical targets

```text
infra/k8s/compositions/foundation/namespace
infra/k8s/compositions/shared/rpc-workers-services
infra/k8s/compositions/foundation/storage
infra/k8s/compositions/topology/<topology-composition>
infra/k8s/compositions/server/models/<model-composition>
```

### Why this order matters

- the namespace must exist first;
- the shared RPC service identities should be available before workers start;
- the PVC must exist before the server starts;
- the topology config map and worker deployments must exist before the server consumes the runtime config and starts using the gRPC server list;
- the server is applied last so that it comes up against the intended topology and runtime configuration.

---

## Inputs Required for Deployment

Before deploying, determine these inputs explicitly.

| Input | Example | Meaning |
|---|---|---|
| Namespace composition | `infra/k8s/compositions/foundation/namespace` | Creates the project namespace. |
| Shared composition | `infra/k8s/compositions/shared/rpc-workers-services` | Creates the stable RPC services. |
| Storage composition | `infra/k8s/compositions/foundation/storage` | Creates the model PVC. |
| Topology composition | `infra/k8s/compositions/topology/colocated-sc-app-02-w2` | Resolves placement and worker count. |
| Server composition | `infra/k8s/compositions/server/models/m1` | Resolves the server model. |
| Kubeconfig | `config/cluster-access/kubeconfig` | Cluster access file. |
| Namespace | `genai-thesis` | Target namespace for validation. |

---

## Recommended Manual Deployment Procedure

All commands below assume execution from the repository root.

## Step 1 — Apply the namespace composition

### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig apply -k .\infra\k8s\compositions\foundation\namespace
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig apply -k ./infra/k8s/compositions/foundation/namespace
```

### Validate

PowerShell:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get namespace genai-thesis
```

Bash:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get namespace genai-thesis
```

---

## Step 2 — Apply the shared RPC services composition

### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig apply -k .\infra\k8s\compositions\shared\rpc-workers-services
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig apply -k ./infra/k8s/compositions/shared/rpc-workers-services
```

### Validate

PowerShell:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get svc -n genai-thesis
```

Bash:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get svc -n genai-thesis
```

Expected shared service names:

- `localai-rpc-a`
- `localai-rpc-b`
- `localai-rpc-c`
- `localai-rpc-d`

---

## Step 3 — Apply the storage composition

### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig apply -k .\infra\k8s\compositions\foundation\storage
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig apply -k ./infra/k8s/compositions/foundation/storage
```

### Validate

PowerShell:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get pvc -n genai-thesis
```

Bash:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get pvc -n genai-thesis
```

Expected PVC:

- `localai-models-pvc`

The PVC should eventually move to `Bound`, assuming the cluster has a working default storage class.

---

## Step 4 — Apply the topology composition

Select the topology composition required for the scenario you want to deploy.

### Example: official baseline topology

Current baseline topology:

```text
infra/k8s/compositions/topology/colocated-sc-app-02-w2
```

### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig apply -k .\infra\k8s\compositions\topology\colocated-sc-app-02-w2
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig apply -k ./infra/k8s/compositions/topology/colocated-sc-app-02-w2
```

### Validate

PowerShell:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get configmap localai-runtime-config -n genai-thesis -o yaml
kubectl --kubeconfig .\config\cluster-access\kubeconfig get deploy -n genai-thesis
```

Bash:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get configmap localai-runtime-config -n genai-thesis -o yaml
kubectl --kubeconfig ./config/cluster-access/kubeconfig get deploy -n genai-thesis
```

Confirm that:

- the expected worker deployments have `replicas: 1`;
- the inactive workers remain at `replicas: 0`;
- `LLAMACPP_GRPC_SERVERS` matches the selected worker count and topology.

---

## Step 5 — Apply the server model composition

Select the required model composition.

### Example: official baseline model

Current baseline server composition:

```text
infra/k8s/compositions/server/models/m1
```

### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig apply -k .\infra\k8s\compositions\server\models\m1
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig apply -k ./infra/k8s/compositions/server/models/m1
```

### Validate

PowerShell:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get deploy localai-server -n genai-thesis -o wide
kubectl --kubeconfig .\config\cluster-access\kubeconfig get svc localai-server -n genai-thesis
```

Bash:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get deploy localai-server -n genai-thesis -o wide
kubectl --kubeconfig ./config/cluster-access/kubeconfig get svc localai-server -n genai-thesis
```

Confirm that:

- the server deployment exists;
- the service exists;
- the server pod is scheduled on `sc-app-02` as expected.

---

## Post-Deployment Validation

After all manifests are applied, validate the deployed topology before moving to smoke testing.

## Required checks

### 1. Namespace resources are present

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get all -n genai-thesis
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get all -n genai-thesis
```

### 2. Pod placement is correct

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get pods -n genai-thesis -o wide
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get pods -n genai-thesis -o wide
```

Verify:

- `localai-server` on `sc-app-02`;
- worker pods on the nodes expected by the selected topology composition.

### 3. Services are present

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get svc -n genai-thesis
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get svc -n genai-thesis
```

### 4. Runtime config is consistent

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get configmap localai-runtime-config -n genai-thesis -o yaml
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get configmap localai-runtime-config -n genai-thesis -o yaml
```

### 5. No immediate pod failure exists

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get pods -n genai-thesis
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get pods -n genai-thesis
```

No active component expected for the scenario should remain in:

- `Pending`
- `CrashLoopBackOff`
- `ImagePullBackOff`
- `Error`

---

## Canonical Deployment Examples

## Official baseline deployment

Use this pair when deploying the current official baseline.

### Topology

```text
infra/k8s/compositions/topology/colocated-sc-app-02-w2
```

### Server model

```text
infra/k8s/compositions/server/models/m1
```

---

## Worker-count study on co-located placement

Use these topology compositions for the current worker-count family:

- `infra/k8s/compositions/topology/colocated-sc-app-02-w1`
- `infra/k8s/compositions/topology/colocated-sc-app-02-w2`
- `infra/k8s/compositions/topology/colocated-sc-app-02-w3`
- `infra/k8s/compositions/topology/colocated-sc-app-02-w4`

All of them preserve the same co-located placement policy and vary only the number of active workers.

---

## Placement comparison on fixed worker count

Use this topology composition for the current distributed placement comparison:

- `infra/k8s/compositions/topology/distributed-two-node-w2`

This composition changes worker placement while keeping the worker count at `2`.

---

## Success Criteria

A deployment is considered valid for the next phase only if all the following are true:

1. the namespace exists and is active;
2. the PVC exists and is usable;
3. the shared RPC services exist;
4. the topology composition has created the expected worker deployment state;
5. the runtime config map reflects the intended gRPC worker set;
6. the server deployment exists and the server pod is scheduled as expected;
7. the required pods are in `Running` state, or at least have progressed cleanly toward readiness without immediate failure;
8. pod placement matches the selected topology composition.

Only after these criteria are satisfied should you proceed to the pre-check and API smoke-validation phase.

---

## Common Failure Modes and Troubleshooting

## 1. Namespace not found

### Symptom

Subsequent resources fail because `genai-thesis` does not exist.

### Action

Re-apply the namespace composition first and verify it exists before applying other layers.

---

## 2. PVC remains `Pending`

### Symptom

`localai-models-pvc` does not become `Bound`.

### Likely cause

- no default storage class;
- broken local-path provisioner;
- storage provisioning problem on the cluster.

### Action

Check:

PowerShell:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get storageclass
kubectl --kubeconfig .\config\cluster-access\kubeconfig describe pvc localai-models-pvc -n genai-thesis
```

Bash:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get storageclass
kubectl --kubeconfig ./config/cluster-access/kubeconfig describe pvc localai-models-pvc -n genai-thesis
```

Do not continue until storage provisioning is understood.

---

## 3. Worker pods remain `Pending`

### Symptom

One or more worker deployments do not schedule.

### Likely cause

- selected topology exceeds available node capacity;
- node affinity does not match current node names;
- cluster resources are already partially consumed.

### Action

Inspect:

PowerShell:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig describe pod <pod-name> -n genai-thesis
kubectl --kubeconfig .\config\cluster-access\kubeconfig top nodes
```

Bash:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig describe pod <pod-name> -n genai-thesis
kubectl --kubeconfig ./config/cluster-access/kubeconfig top nodes
```

Treat unresolved scheduling failures as deployment blockers.

---

## 4. Server pod does not start

### Symptom

`localai-server` does not reach `Running`.

### Likely cause

- PVC issue;
- image pull issue;
- runtime config mismatch;
- insufficient capacity on `sc-app-02`.

### Action

Inspect:

PowerShell:

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig describe pod -n genai-thesis -l app=localai-server
kubectl --kubeconfig .\config\cluster-access\kubeconfig logs -n genai-thesis deploy/localai-server
```

Bash:

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig describe pod -n genai-thesis -l app=localai-server
kubectl --kubeconfig ./config/cluster-access/kubeconfig logs -n genai-thesis deploy/localai-server
```

---

## 5. Runtime config does not match the selected worker-count scenario

### Symptom

The `LLAMACPP_GRPC_SERVERS` value does not correspond to the selected topology composition.

### Likely cause

- wrong topology composition applied;
- manual patching outside the supported composition model;
- stale resources from an earlier run.

### Action

Re-apply the intended topology composition and verify the config map again.

---

## 6. Service exists but worker pod is missing

### Symptom

A service such as `localai-rpc-c` exists but no pod backs it.

### Interpretation

This can be valid if the current worker-count composition intentionally sets that worker to `replicas: 0`.

### Action

Check the active worker-count scenario before treating it as a problem.

---

## Operator Notes

- Always deploy from the composition directories, not from individual patches.
- Do not change deployment order unless you are deliberately debugging the infrastructure.
- Treat the server pinning to `sc-app-02` as an active design constraint for the current pipeline.
- When comparing topologies, remember that current placement comparisons vary the worker placement only.
- If you need a clean redeploy, use the cleanup runbook rather than deleting resources ad hoc.

---

## Exit Condition

This runbook is complete when:

- the selected namespace, storage, shared services, topology, and server compositions have been applied;
- the deployed topology matches the selected scenario;
- the server and required workers are present and schedulable;
- post-deployment validation passes without unresolved blockers.

At that point, continue with the pre-check and smoke-validation workflow.

---

## Next Runbook

Proceed to:

```text
docs/runbooks/04-precheck-and-smoke-validation.md
```

