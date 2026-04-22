# 00. Cluster Bootstrap and Access

## Objective

Bring a newly provisioned Kubernetes cluster to a validated, usable state for the benchmark pipeline.

This runbook covers the initial access workflow, cluster reachability checks, namespace and control-plane validation, storage and metrics availability checks, and the minimum acceptance criteria required before any project workloads are deployed.

---

## When to Execute

Execute this runbook in any of the following cases:

- immediately after a new cluster has been created;
- when cluster access has been re-issued or changed;
- when the VPN profile or `kubeconfig` has been replaced;
- before the first project deployment on a fresh environment;
- after infrastructure maintenance, node replacement, or cluster recreation.

This runbook is not intended to be repeated before every benchmark run. Once the cluster is considered operational, the recurring validation workflow is handled by the pre-check runbook and the benchmark pre-check scripts.

---

## Scope

This runbook validates the infrastructure prerequisites for the benchmark pipeline, specifically:

- secure network access to the cluster;
- `kubectl` reachability through the project `kubeconfig`;
- node readiness and expected topology;
- system namespace health;
- observability stack presence;
- dynamic storage provisioning availability;
- Metrics API availability.

This runbook does **not** deploy LocalAI, does **not** execute smoke tests against the LocalAI API, and does **not** launch any benchmark workload.

---

## Expected Cluster Topology

The current project pipeline assumes a three-node Kubernetes cluster with the following logical structure:

- `sc-master-01` — control-plane node;
- `sc-app-01` — worker node;
- `sc-app-02` — worker node.

The current benchmark design also assumes a dedicated project namespace:

- `genai-thesis`

The recurring technical pre-check profile stored in `config/precheck/TC1.json` expects exactly those three nodes to be reachable and ready, and expects `sc-app-01` and `sc-app-02` to act as the worker nodes for application workloads.

---

## Prerequisites

Before starting, ensure the following are available on the local workstation:

### Required local tools

- OpenVPN client or equivalent VPN client compatible with the provided `.ovpn` profile;
- `kubectl` available in `PATH`;
- PowerShell **or** Bash shell;
- access to the repository root on the local filesystem.

### Required access artifacts

- VPN configuration file (`.ovpn`);
- project `kubeconfig` file;
- permission to connect to the target infrastructure.

### Repository assumptions

The commands below assume execution from the repository root:

```text
localai-worker-mode-benchmark-suite/
```

and the project `kubeconfig` located at:

```text
config/cluster-access/kubeconfig
```

---

## Inputs

This runbook uses the following inputs.

| Input | Description |
|---|---|
| VPN profile | Enables network reachability to the private cluster network. |
| `config/cluster-access/kubeconfig` | Kubernetes client configuration used by all project scripts. |
| Expected node names | `sc-master-01`, `sc-app-01`, `sc-app-02`. |
| Expected namespace | `genai-thesis`. |

---

## Success Criteria

The cluster can be considered ready for the project only if all the following are true:

1. the VPN tunnel is active and stable;
2. `kubectl` can query the cluster through the project `kubeconfig`;
3. all expected nodes are present and in `Ready` state;
4. the control-plane and both worker nodes are visible;
5. system namespaces are healthy and their critical pods are running;
6. the project namespace exists and is `Active`;
7. a default dynamic storage path exists and is usable;
8. the Metrics API is available (`kubectl top nodes` succeeds);
9. the observability stack is present and running.

If any of these checks fails, do **not** proceed with workload deployment.

---

## Procedure

## Step 1 — Connect to the VPN

Establish the VPN session using the provided `.ovpn` profile.

The exact procedure depends on the VPN client in use. The key requirement is that, once connected, the workstation must be able to reach the private network used by the cluster.

### Validation

After the VPN is connected, verify that the Kubernetes API endpoint is reachable through the provided `kubeconfig`.

### Recommended check

From the repository root:

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig cluster-info
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig cluster-info
```

### Expected outcome

The command must return cluster endpoint information instead of timing out or returning authentication/network errors.

### Typical failure cases

- VPN tunnel not established;
- invalid or expired VPN profile;
- incorrect route propagation;
- stale or invalid `kubeconfig`;
- API server unreachable from the local workstation.

---

## Step 2 — Verify that `kubectl` uses the intended cluster access file

Do not rely on the default local Kubernetes context during project execution. Always use the repository `kubeconfig` explicitly.

### Recommended check

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig config view --minify
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig config view --minify
```

### Objective

Confirm that:

- the command reads the expected cluster and user definition;
- the active context is not pointing to a different cluster;
- the file path used by subsequent scripts is valid.

---

## Step 3 — Validate node discovery and readiness

Validate that the expected cluster topology is present and healthy.

### Recommended check

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get nodes
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get nodes
```

### Expected outcome

The output should list the following nodes:

- `sc-master-01`
- `sc-app-01`
- `sc-app-02`

and each of them must be in `Ready` state.

### Additional detailed check

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get nodes -o wide
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get nodes -o wide
```

### What to verify

- node names match the expected topology;
- the control-plane node is visible;
- both worker nodes are visible;
- no node is `NotReady`, `Unknown`, or missing;
- no unexpected infrastructure churn is visible in the node list.

If a node is missing or not ready, stop here and resolve the infrastructure issue first.

---

## Step 4 — Verify core system namespaces and pods

Before deploying application workloads, validate the health of the cluster system components.

### Recommended check

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get pods -A
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get pods -A
```

### Minimum namespaces that should be inspected

- `kube-system`
- `istio-system` (if present)
- `observability` (if present)
- project namespace `genai-thesis` (if already created)

### Minimum components that should be healthy

In `kube-system`:

- `coredns`
- `local-path-provisioner`
- `metrics-server`

In `istio-system` (if the service mesh layer is part of the cluster setup):

- `istiod`
- `kiali` or any expected control-plane components

In `observability`:

- Prometheus stack components
- Grafana
- node exporters
- Jaeger (if installed)

### What to verify

- pods are in `Running` or completed `Succeeded` state where appropriate;
- there are no crash loops in critical namespaces;
- there are no obvious image pull or configuration errors;
- the observability stack is already available before benchmark execution begins.

---

## Step 5 — Verify that the project namespace exists and is active

The project pipeline assumes the namespace `genai-thesis`.

### Recommended check

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get namespace genai-thesis
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get namespace genai-thesis
```

### Expected outcome

The namespace must exist and its status must be `Active`.

### If the namespace does not exist yet

Create it using the project manifest composition rather than ad hoc commands.

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig apply -k .\infra\k8s\compositions\foundation\namespace
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig apply -k ./infra/k8s/compositions/foundation/namespace
```

### Re-check

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get namespace genai-thesis
```

or

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get namespace genai-thesis
```

---

## Step 6 — Verify dynamic storage provisioning

The project uses a PersistentVolumeClaim defined in:

```text
infra/k8s/base/foundation/01-storage.yaml
```

and the current cluster setup relies on the local path provisioner.

### Recommended checks

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get storageclass
```

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get pods -n kube-system
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get storageclass
```

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get pods -n kube-system
```

### What to verify

- at least one usable `StorageClass` is present;
- the local path provisioner is running;
- the cluster supports dynamic PVC provisioning;
- there is no obvious storage bootstrap issue before workload deployment.

### Optional early validation

If you want to validate project storage manifests immediately, apply the storage composition.

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig apply -k .\infra\k8s\compositions\foundation\storage
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig apply -k ./infra/k8s/compositions/foundation/storage
```

Then verify the resulting PVC:

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get pvc -n genai-thesis
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get pvc -n genai-thesis
```

The PVC should become `Bound`.

If the PVC stays `Pending`, stop and resolve storage provisioning before proceeding.

---

## Step 7 — Verify Metrics API availability

The benchmark pipeline relies on node and pod capacity checks, and the technical pre-check profile `TC1` explicitly requires the Metrics API.

### Recommended checks

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig top nodes
```

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig top pods -n genai-thesis
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig top nodes
```

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig top pods -n genai-thesis
```

### Expected outcome

- `kubectl top nodes` must return CPU and memory usage for nodes;
- `kubectl top pods -n genai-thesis` must return data once pods exist in the namespace.

### Important note

If the project namespace has not yet received any workload, `kubectl top pods -n genai-thesis` may legitimately return no pod rows. That is acceptable at bootstrap time **as long as the command itself works** and the Metrics API is functioning.

### Failure handling

If `kubectl top nodes` fails, do not continue to workload deployment. The recurring benchmark pre-checks depend on a working Metrics API.

---

## Step 8 — Verify observability stack presence

The benchmark pipeline assumes that infrastructure-level observability already exists in the cluster.

### Recommended checks

#### PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get pods -n observability
```

```powershell
kubectl --kubeconfig .\config\cluster-access\kubeconfig get svc -n observability
```

#### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get pods -n observability
```

```bash
kubectl --kubeconfig ./config/cluster-access/kubeconfig get svc -n observability
```

### What to verify

- Prometheus is running;
- Grafana is running;
- node exporters are running on all nodes;
- kube-state-metrics is running;
- Jaeger is running if tracing is part of the environment;
- no critical observability component is crashing.

### Why this matters

The benchmark design requires cluster-side evidence collection and metric correlation. Starting the benchmark pipeline without a working observability layer is operationally risky and weakens the quality of the resulting evidence.

---

## Step 9 — Execute the formal benchmark pre-check once on the fresh cluster

Once the raw infrastructure checks have passed, execute the project pre-check script once to validate that the project-level assumptions already encoded in the repository are satisfied.

### PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\validation\precheck\Invoke-BenchmarkPrecheck.ps1"
```

### Bash

```bash
./scripts/validation/precheck/invoke-benchmark-precheck.sh
```

### Notes

- if no explicit arguments are passed, the script uses `config/precheck/TC1.json`;
- the script resolves the repository `kubeconfig` automatically from the profile;
- by default it writes output under `results/precheck`.

### Expected output artifacts

The pre-check should generate:

- a JSON report ending with `_precheck.json`;
- a text summary ending with `_precheck.txt`.

### What to do with the result

A successful pre-check is the formal confirmation that the cluster is aligned with the current benchmark profile and ready for workload deployment.

If the pre-check fails, do not proceed. Resolve the failing condition first.

---

## Acceptance Checklist

Use the following checklist before declaring the cluster ready.

- [ ] VPN connected successfully
- [ ] `kubectl cluster-info` works through `config/cluster-access/kubeconfig`
- [ ] `sc-master-01`, `sc-app-01`, and `sc-app-02` are visible
- [ ] all expected nodes are `Ready`
- [ ] critical `kube-system` pods are healthy
- [ ] `metrics-server` is running
- [ ] `genai-thesis` exists and is `Active`
- [ ] storage provisioning is available
- [ ] `kubectl top nodes` works
- [ ] observability stack is running
- [ ] project benchmark pre-check passes

Only after all items are checked should the cluster be considered ready for the next phase.

---

## Output Artifacts

This runbook may produce or confirm the following artifacts:

- namespace creation in `genai-thesis`;
- project PVC objects if storage composition is applied;
- formal pre-check reports under `results/precheck`;
- evidence that the cluster is ready for project workload deployment.

---

## Common Failure Modes and Troubleshooting

## VPN connected, but `kubectl` cannot reach the API server

Possible causes:

- incorrect VPN routing;
- stale `kubeconfig`;
- expired credentials;
- firewall or ACL issue.

Action:

- verify VPN status first;
- verify the `kubeconfig` path;
- re-run `kubectl config view --minify` using the project file;
- confirm with the infrastructure owner that the API endpoint is reachable through the VPN.

## One or more nodes are not `Ready`

Possible causes:

- worker not joined correctly;
- node restart or kubelet failure;
- resource pressure;
- control-plane instability.

Action:

- stop the pipeline immediately;
- collect node status and events;
- resolve the infrastructure issue before any deployment.

## `kubectl top nodes` fails

Possible causes:

- `metrics-server` not running;
- Metrics API unavailable;
- RBAC or API aggregation issue.

Action:

- inspect `metrics-server` in `kube-system`;
- confirm the Metrics API is functioning before continuing.

## PVC remains `Pending`

Possible causes:

- missing default storage class;
- failed local path provisioner;
- storage provisioning misconfiguration.

Action:

- inspect `StorageClass` objects;
- inspect the provisioner pod logs;
- do not proceed until the PVC can be bound.

## Observability stack missing or unhealthy

Possible causes:

- bootstrap sequence incomplete;
- monitoring stack deployed to a different namespace;
- one or more components failed.

Action:

- validate the intended namespace;
- recover observability before starting the benchmark pipeline.

---

## Exit Condition

This runbook is complete when:

- all infrastructure checks have passed;
- the project namespace is usable;
- storage and metrics are available;
- the project benchmark pre-check succeeds;
- the cluster is formally declared ready for deployment.

---

## Next Runbook

Once this runbook has completed successfully, continue with:

```text
01-repository-and-execution-environment-setup.md
```

If the local execution environment is already known to be valid and stable, proceed directly to the deployment-oriented runbook sequence.
