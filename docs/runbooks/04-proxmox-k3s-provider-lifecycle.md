# Proxmox K3s Provider Lifecycle

## Purpose

This runbook describes how the benchmark suite uses the `proxmox-k3s` provider workflow to create, inspect, reuse, refresh, validate, and delete provider-backed K3s clusters.

It covers:

1. the boundary between the benchmark suite and the `proxmox-k3s` provider;
2. provider configuration files and binding resolution;
3. lifecycle modes for provider-backed executions;
4. template, cluster, kubeconfig, and deletion operations;
5. safe command usage through benchmark-suite wrappers;
6. direct provider commands for controlled standalone maintenance;
7. lifecycle artifacts and expected output locations;
8. operational safety rules before running benchmark workloads.

This runbook does not document LocalAI deployment, Locust execution, reporting, or result interpretation. Those areas are documented in later runbooks.

---

## Repository Root Assumption

All commands in this runbook must be executed from the repository root:

```text
localai-worker-mode-benchmark-suite/
```

### Windows PowerShell

```powershell
Get-ChildItem
```

### Bash

```bash
ls -la
```

A valid repository root contains at least:

```text
config/
docs/
infra/
load-tests/
scripts/
requirements.txt
```

---

## Provider Role

`proxmox-k3s` is an infrastructure provider tool. It is responsible for materializing K3s clusters on Proxmox VE from a YAML configuration file.

The benchmark suite remains responsible for selecting profiles, invoking provider workflows, validating the generated cluster, deploying LocalAI, running the benchmark workload, collecting artifacts, generating diagnosis outputs, producing reports, evaluating completion gates, and freezing cycle outputs.

| Area | Owner |
|---|---|
| VM creation | `proxmox-k3s` |
| Ubuntu or Debian cloud-image template preparation | `proxmox-k3s` |
| Cloud-Init-based node initialization | `proxmox-k3s` |
| K3s server and agent installation | `proxmox-k3s` |
| Kubeconfig export | `proxmox-k3s` |
| Cluster deletion | `proxmox-k3s` |
| Infrastructure profile selection | Benchmark suite |
| Provider binding resolution | Benchmark suite |
| Lifecycle policy selection | Benchmark suite |
| Cluster validation | Benchmark suite |
| LocalAI deployment | Benchmark suite |
| Locust benchmark execution | Benchmark suite |
| Technical diagnosis | Benchmark suite |
| Reporting | Benchmark suite |
| Completion gate | Benchmark suite |
| Freeze and artifact snapshotting | Benchmark suite |

This separation must be preserved. The provider must not be made aware of LocalAI workloads, benchmark scenarios, placement profiles, latency profiles, or reporting logic.

---

## Provider File Layout

The benchmark suite stores provider-related configuration under:

```text
config/infrastructure/providers/proxmox-k3s/
```

The main subdirectories are:

| Path | Purpose |
|---|---|
| `config/infrastructure/providers/proxmox-k3s/PROXMOX_K3S_PROVIDER_INDEX.json` | Canonical provider registry and lifecycle boundary definition. |
| `config/infrastructure/providers/proxmox-k3s/PROXMOX_K3S_PROVIDER_BINDINGS_INDEX.json` | Registry of infrastructure-profile-to-provider bindings. |
| `config/infrastructure/providers/proxmox-k3s/bindings/` | Concrete binding files linking infrastructure profiles to `proxmox-k3s` YAML files. |
| `config/infrastructure/providers/proxmox-k3s/examples/` | Review-safe example provider YAML files. |
| `config/infrastructure/providers/proxmox-k3s/local/` | Local, real provider YAML files used for execution. |
| `config/infrastructure/providers/proxmox-k3s/templates/` | Provider YAML template and metadata. |
| `config/infrastructure/providers/proxmox-k3s/schemas/` | Provider binding schema files. |
| `config/infrastructure/providers/proxmox-k3s/vmid-allocation/` | VMID allocation policies used by provider-backed workflows. |

Validate that the provider registry exists before running provider-backed operations.

### Windows PowerShell

```powershell
Test-Path .\config\infrastructure\providers\proxmox-k3s\PROXMOX_K3S_PROVIDER_INDEX.json
Test-Path .\config\infrastructure\providers\proxmox-k3s\PROXMOX_K3S_PROVIDER_BINDINGS_INDEX.json
Test-Path .\config\infrastructure\providers\proxmox-k3s\bindings
Test-Path .\config\infrastructure\providers\proxmox-k3s\examples
Test-Path .\config\infrastructure\providers\proxmox-k3s\local
```

### Bash

```bash
test -f ./config/infrastructure/providers/proxmox-k3s/PROXMOX_K3S_PROVIDER_INDEX.json
test -f ./config/infrastructure/providers/proxmox-k3s/PROXMOX_K3S_PROVIDER_BINDINGS_INDEX.json
test -d ./config/infrastructure/providers/proxmox-k3s/bindings
test -d ./config/infrastructure/providers/proxmox-k3s/examples
test -d ./config/infrastructure/providers/proxmox-k3s/local
```

---

## Provider Configuration Types

The provider workflow distinguishes three types of configuration material.

| Configuration type | Example path | Intended use | Suitable for real execution |
|---|---|---:|---:|
| Template | `config/infrastructure/providers/proxmox-k3s/templates/cluster.proxmox-k3s.template.yaml.tmpl` | Defines the generic renderable structure. | No |
| Example YAML | `config/infrastructure/providers/proxmox-k3s/examples/cluster.c1-1cp-2w-8c16g.example.yaml` | Review-safe documentation and dry-run inspection. | No |
| Local YAML | `config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml` | Real environment-specific provider execution. | Yes |

Real provider execution must use local YAML files. Example files are intentionally review-safe and must not be used for `create`, `delete`, or `kubeconfig` operations against real infrastructure.

Check available local provider configurations before running a provider-backed cycle.

### Windows PowerShell

```powershell
Get-ChildItem .\config\infrastructure\providers\proxmox-k3s\local\*.local.yaml | Select-Object Name, Length
```

### Bash

```bash
find ./config/infrastructure/providers/proxmox-k3s/local -maxdepth 1 -type f -name '*.local.yaml' -print | sort
```

If a required `.local.yaml` file is missing, create it from the matching `.example.yaml` file and populate the environment-specific Proxmox values before attempting real execution.

---

## Provider-Backed Configuration Matrix

The currently documented provider-backed execution tracks use the following local provider configuration paths.

| Scope | Local provider configuration | Generated kubeconfig |
|---|---|---|
| `C1` baseline | `config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig` |
| `C2` resource variation, 4C/8G | `config/infrastructure/providers/proxmox-k3s/local/cluster.c2-1cp-2w-4c8g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c2-1cp-2w-4c8g/kubeconfig` |
| `C2` resource variation, 4C/16G | `config/infrastructure/providers/proxmox-k3s/local/cluster.c2-1cp-2w-4c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c2-1cp-2w-4c16g/kubeconfig` |
| `C2` resource variation, 8C/16G | `config/infrastructure/providers/proxmox-k3s/local/cluster.c2-1cp-2w-8c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c2-1cp-2w-8c16g/kubeconfig` |
| `C3` node-count variation, 2 workers | `config/infrastructure/providers/proxmox-k3s/local/cluster.c3-1cp-2w-8c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c3-1cp-2w-8c16g/kubeconfig` |
| `C3` node-count variation, 3 workers | `config/infrastructure/providers/proxmox-k3s/local/cluster.c3-1cp-3w-8c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c3-1cp-3w-8c16g/kubeconfig` |
| `C3` node-count variation, 4 workers | `config/infrastructure/providers/proxmox-k3s/local/cluster.c3-1cp-4w-8c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c3-1cp-4w-8c16g/kubeconfig` |
| `C4` placement variation | `config/infrastructure/providers/proxmox-k3s/local/cluster.c4-1cp-4w-8c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c4-1cp-4w-8c16g/kubeconfig` |
| `C5` latency injection | `config/infrastructure/providers/proxmox-k3s/local/cluster.c5-1cp-4w-8c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c5-1cp-4w-8c16g/kubeconfig` |
| `C6` multi-tenancy | `config/infrastructure/providers/proxmox-k3s/local/cluster.c6-1cp-4w-8c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c6-1cp-4w-8c16g/kubeconfig` |
| `C7` default scheduler, 2 workers | `config/infrastructure/providers/proxmox-k3s/local/cluster.c7-1cp-2w-8c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c7-1cp-2w-8c16g/kubeconfig` |
| `C7` default scheduler, 3 workers | `config/infrastructure/providers/proxmox-k3s/local/cluster.c7-1cp-3w-8c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c7-1cp-3w-8c16g/kubeconfig` |
| `C7` default scheduler, 4 workers | `config/infrastructure/providers/proxmox-k3s/local/cluster.c7-1cp-4w-8c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c7-1cp-4w-8c16g/kubeconfig` |
| `C8` scheduler evaluation, 2 workers | `config/infrastructure/providers/proxmox-k3s/local/cluster.c8-1cp-2w-8c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c8-1cp-2w-8c16g/kubeconfig` |
| `C8` scheduler evaluation, 4 workers | `config/infrastructure/providers/proxmox-k3s/local/cluster.c8-1cp-4w-8c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c8-1cp-4w-8c16g/kubeconfig` |
| `C9` network-aware scheduler, 4 workers | `config/infrastructure/providers/proxmox-k3s/local/cluster.c9-1cp-4w-8c16g.local.yaml` | `config/cluster-access/generated/proxmox-k3s/c9-1cp-4w-8c16g/kubeconfig` |

The execution runbooks for `C1` through `C9` remain the authoritative reference for which profile is used by each cycle or campaign variant.

---

## C9 Provider Add-On Boundary

C9 uses the provider workflow not only for cluster lifecycle management, but also for the infrastructure add-ons required by the network-aware scheduler campaign.

The provider-local C9 YAML must make the following add-ons available:

```text
monitoring
mon-agent
cluster-lens
Mentat
Istio
```

The benchmark suite validates and consumes these add-ons. It must not install a second, divergent copy of the same component as part of the application deployment path.

The provider configuration may keep additional add-ons enabled when they are part of the local infrastructure baseline. The current C9 placement and latency evidence model, however, is based on cluster-lens placement capture, Kubernetes snapshots, Mentat telemetry, mon-agent annotations, Istio routing evidence, and annotation-controlled latency matrices.


## C8 and C9 Management Node Policy

C8 and C9 provider-backed clusters use a management-node role for control-plane and management components. The shared management label is:

```text
label: nodepool=management
```

C8 uses the historical management taint:

```text
taint: nodepool=management:NoSchedule
```

C9 uses the provider add-on toleration convention so that provider-managed add-ons such as `cluster-lens` can tolerate the management node consistently:

```text
taint: ManagementOnly=true:NoSchedule
```

The C9 provider YAML must keep this explicit inside the selected cluster entry:

```yaml
clusters:
  - name: genai-pb
    k3s:
      taint_control_plane: false
      extra_server_args: "--disable=traefik --disable=servicelb --embedded-registry --node-label=nodepool=management --node-taint=ManagementOnly=true:NoSchedule"
```

This policy allows management components such as `mon-agent`, cluster-lens, Mentat, Istio control-plane dependencies, and the custom scheduler to tolerate and prefer the management node while keeping LocalAI tenant workloads on worker nodes.

Validate the resulting labels and taints after provisioning.

### Windows PowerShell

```powershell
# Use the C8 or C9 generated kubeconfig for the cluster being inspected.
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c9-1cp-4w-8c16g\kubeconfig"

kubectl --kubeconfig $Kubeconfig get nodes --show-labels
kubectl --kubeconfig $Kubeconfig describe nodes
```

### Bash

```bash
# Use the C8 or C9 generated kubeconfig for the cluster being inspected.
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c9-1cp-4w-8c16g/kubeconfig"

kubectl --kubeconfig "$KUBECONFIG_PATH" get nodes --show-labels
kubectl --kubeconfig "$KUBECONFIG_PATH" describe nodes
```

---

## Lifecycle Modes

Provider-backed executions use explicit lifecycle policies.

| Lifecycle mode | Policy | Meaning | Typical use |
|---|---|---|---|
| `reuse` | `LC_REUSE_RETAIN_CLUSTER` | Create or reuse a provider-backed K3s cluster and retain it after the run. | Baseline runs or repeated execution on the same infrastructure profile. |
| `ephemeral` | `LC_EPHEMERAL_DELETE_CLUSTER` | Create a provider-backed K3s cluster for a bounded run and delete it after the run or variant. | Infrastructure-variation campaigns requiring clean cluster materialization. |
| `external` | `LC_C0_EXTERNAL_FIXED_CLUSTER_RETAIN` | Use an already available cluster that is not managed by `proxmox-k3s`. | Historical fixed-cluster execution track. |

Cluster deletion is always treated as destructive and must require explicit confirmation when invoked through benchmark-suite wrappers.

Validate lifecycle policy files before provider-backed execution.

### Windows PowerShell

```powershell
Test-Path .\config\infrastructure\lifecycle\policies\LC_REUSE_RETAIN_CLUSTER.json
Test-Path .\config\infrastructure\lifecycle\policies\LC_EPHEMERAL_DELETE_CLUSTER.json
Test-Path .\config\infrastructure\lifecycle\policies\LC_C0_EXTERNAL_FIXED_CLUSTER_RETAIN.json
```

### Bash

```bash
test -f ./config/infrastructure/lifecycle/policies/LC_REUSE_RETAIN_CLUSTER.json
test -f ./config/infrastructure/lifecycle/policies/LC_EPHEMERAL_DELETE_CLUSTER.json
test -f ./config/infrastructure/lifecycle/policies/LC_C0_EXTERNAL_FIXED_CLUSTER_RETAIN.json
```

---

## Active Cluster Reuse Policy

The provider-backed workflows are designed around a reusable provider-backed cluster identity. The canonical reusable cluster name is:

```text
genai-pb
```

Provider-backed campaigns that share the same cluster name, VMID range, IP range, or local YAML identity must not be executed concurrently.

Operational implications:

1. run provider-backed cycles and campaigns sequentially;
2. do not start two provider-backed campaigns that target the same reusable cluster identity at the same time;
3. allow ephemeral campaigns to clean up or replace the reusable cluster only when the active lifecycle policy requires it;
4. inspect local YAML files before execution to ensure that VM names, IP ranges, VMID ranges, and Proxmox node mappings are intentional;
5. preserve provisioning logs and lifecycle manifests for each cycle to make later comparisons auditable.

---

## Validate `proxmox-k3s` Availability

The provider-backed workflow requires the `proxmox-k3s` binary to be available either in `PATH` or through an explicit path passed to the wrapper scripts.

### Windows PowerShell

```powershell
Get-Command proxmox-k3s -ErrorAction SilentlyContinue
proxmox-k3s --help
```

### Bash

```bash
command -v proxmox-k3s
proxmox-k3s --help
```

If the binary is not in `PATH`, define an explicit provider-tool path.

### Windows PowerShell

```powershell
$ToolPath = "..\proxmox-k3s\bin\proxmox-k3s.exe"
& $ToolPath --help
```

### Bash

```bash
TOOL_PATH="../proxmox-k3s/proxmox-k3s"
"$TOOL_PATH" --help
```

On Windows, the provider repository may expose a binary named `proxmox-k3s.exe`. On Unix-like systems, the binary is commonly named `proxmox-k3s`.

---

## Preferred Invocation Path

For benchmark-suite executions, prefer the benchmark-suite wrappers instead of invoking `proxmox-k3s` directly. The wrappers resolve cycle profiles, enforce safety guards, write command manifests, record logs, and maintain latest aliases when requested.

Use direct provider commands only for controlled provider maintenance, local verification, or emergency recovery.

| Invocation path | Recommended for | Artifact capture |
|---|---|---:|
| `Start-ProviderBackedProvisioning.ps1` / `start-provider-backed-provisioning.sh` | Normal provider-backed cycle execution | Yes |
| `Invoke-ProxmoxK3sStandaloneCommand.ps1` / `invoke-proxmox-k3s-standalone-command.sh` | Controlled standalone provider command with benchmark-suite logging | Yes |
| Direct `proxmox-k3s` command | Provider debugging or manual maintenance | No benchmark-suite manifest unless wrapped externally |

---

## Render a Lifecycle Manifest

Before running a provider-backed cluster operation, render a lifecycle manifest to record the intended lifecycle mode, provider configuration, tool path, and artifact policy.

### Windows PowerShell

```powershell
.\scripts\infrastructure\lifecycle\Render-ClusterLifecycleManifest.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ToolPath proxmox-k3s `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/infrastructure/lifecycle/render-cluster-lifecycle-manifest.sh \
  --cycle-config ./config/experimental-cycles/C1.json \
  --tool-path proxmox-k3s \
  --write-latest-aliases
```

Expected output root for `C1`:

```text
results/experimental-cycles/C1/infrastructure/lifecycle/
```

For other provider-backed cycles, replace `C1.json` with the intended cycle configuration.

---

## Dry-Run Provider Resolution

Use a dry run to verify provider binding resolution, command construction, lifecycle mode, and output locations without creating or deleting infrastructure.

### Windows PowerShell

```powershell
.\scripts\infrastructure\provision\Start-ProviderBackedProvisioning.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -Action plan `
  -ToolPath proxmox-k3s `
  -DryRun `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/infrastructure/provision/start-provider-backed-provisioning.sh \
  --cycle-config ./config/experimental-cycles/C1.json \
  --action plan \
  --tool-path proxmox-k3s \
  --dry-run \
  --write-latest-aliases
```

A dry run must not create, modify, or delete Proxmox resources. It is suitable for verifying that profile resolution is correct before real execution.

---

## Optional Explicit Provider Configuration Override

The wrapper can resolve the provider configuration from the cycle profile and provider binding. When needed, a local YAML file may also be supplied explicitly.

### Windows PowerShell

```powershell
.\scripts\infrastructure\provision\Start-ProviderBackedProvisioning.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -Action plan `
  -ToolPath proxmox-k3s `
  -ProviderConfig .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml `
  -DryRun `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/infrastructure/provision/start-provider-backed-provisioning.sh \
  --cycle-config ./config/experimental-cycles/C1.json \
  --action plan \
  --tool-path proxmox-k3s \
  --provider-config ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml \
  --dry-run \
  --write-latest-aliases
```

Use this override only when the intended local YAML file is known and has already been reviewed.

---

## Create or Reuse a Provider-Backed Cluster

Run `provision` to create or reuse the provider-backed K3s cluster declared by the cycle configuration and provider binding.

### Windows PowerShell

```powershell
.\scripts\infrastructure\provision\Start-ProviderBackedProvisioning.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -Action provision `
  -ToolPath proxmox-k3s `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/infrastructure/provision/start-provider-backed-provisioning.sh \
  --cycle-config ./config/experimental-cycles/C1.json \
  --action provision \
  --tool-path proxmox-k3s \
  --write-latest-aliases
```

Expected output root for `C1`:

```text
results/experimental-cycles/C1/infrastructure/provisioning/
```

The provisioning action must stop before application deployment if provider execution, kubeconfig refresh, or kubeconfig verification fails.

---

## Refresh a Provider-Generated Kubeconfig

Run `kubeconfig` when the cluster exists but the local generated kubeconfig must be refreshed.

### Windows PowerShell

```powershell
.\scripts\infrastructure\provision\Start-ProviderBackedProvisioning.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -Action kubeconfig `
  -ToolPath proxmox-k3s `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/infrastructure/provision/start-provider-backed-provisioning.sh \
  --cycle-config ./config/experimental-cycles/C1.json \
  --action kubeconfig \
  --tool-path proxmox-k3s \
  --write-latest-aliases
```

Expected generated kubeconfig for `C1`:

```text
config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig
```

After refreshing the kubeconfig, validate cluster reachability before deploying workloads.

---

## Validate a Provider-Backed Cluster

After successful provisioning and kubeconfig refresh, run provider-backed cluster validation.

### Windows PowerShell

```powershell
.\scripts\infrastructure\validation\Start-ProviderBackedClusterValidation.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/infrastructure/validation/start-provider-backed-cluster-validation.sh \
  --cycle-config ./config/experimental-cycles/C1.json \
  --write-latest-aliases
```

Expected output root for `C1`:

```text
results/experimental-cycles/C1/infrastructure/validation/
```

Cluster validation must pass before application deployment. If metrics-server behavior is known to be environment-dependent and the selected validation profile allows it, the execution runbook may explicitly document `AllowMetricsWarning` usage for that cycle.

---

## Inspect the Generated Cluster Manually

Manual inspection is useful after provisioning and before moving to application deployment.

### Windows PowerShell

```powershell
kubectl `
  --kubeconfig .\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig `
  get nodes -o wide
```

### Bash

```bash
kubectl \
  --kubeconfig ./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig \
  get nodes -o wide
```

Inspect core K3s components.

### Windows PowerShell

```powershell
kubectl `
  --kubeconfig .\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig `
  get pods -n kube-system
```

### Bash

```bash
kubectl \
  --kubeconfig ./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig \
  get pods -n kube-system
```

This manual check does not replace the provider-backed validation command, because the validation command writes structured artifacts.

---

## Delete a Provider-Backed Cluster

Cluster deletion is destructive. Run it only when the selected lifecycle policy requires cleanup, when a campaign needs clean infrastructure materialization, or when an explicit recovery procedure requires deletion.

### Windows PowerShell

```powershell
.\scripts\infrastructure\provision\Start-ProviderBackedProvisioning.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -Action destroy `
  -ToolPath proxmox-k3s `
  -ConfirmDelete `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/infrastructure/provision/start-provider-backed-provisioning.sh \
  --cycle-config ./config/experimental-cycles/C1.json \
  --action destroy \
  --tool-path proxmox-k3s \
  --confirm-delete \
  --write-latest-aliases
```

If `ConfirmDelete` is omitted, the wrapper must fail fast and refuse the destructive operation.

---

## Standalone Provider Command Wrapper

For maintenance operations that should still produce benchmark-suite logs and command manifests, use the standalone provider command wrapper.

### Dry-Run a Standalone Create Command

### Windows PowerShell

```powershell
.\scripts\infrastructure\provision\Invoke-ProxmoxK3sStandaloneCommand.ps1 `
  -Command create `
  -ConfigPath .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml `
  -ToolPath proxmox-k3s `
  -CycleId C1 `
  -DryRun
```

### Bash

```bash
./scripts/infrastructure/provision/invoke-proxmox-k3s-standalone-command.sh \
  --command create \
  --config ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml \
  --tool-path proxmox-k3s \
  --cycle-id C1 \
  --dry-run
```

### Refresh Kubeconfig Through the Standalone Wrapper

### Windows PowerShell

```powershell
.\scripts\infrastructure\provision\Invoke-ProxmoxK3sStandaloneCommand.ps1 `
  -Command kubeconfig `
  -ConfigPath .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml `
  -ToolPath proxmox-k3s `
  -CycleId C1
```

### Bash

```bash
./scripts/infrastructure/provision/invoke-proxmox-k3s-standalone-command.sh \
  --command kubeconfig \
  --config ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml \
  --tool-path proxmox-k3s \
  --cycle-id C1
```

### Delete Through the Standalone Wrapper

### Windows PowerShell

```powershell
.\scripts\infrastructure\provision\Invoke-ProxmoxK3sStandaloneCommand.ps1 `
  -Command delete `
  -ConfigPath .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml `
  -ToolPath proxmox-k3s `
  -CycleId C1 `
  -ConfirmDelete
```

### Bash

```bash
./scripts/infrastructure/provision/invoke-proxmox-k3s-standalone-command.sh \
  --command delete \
  --config ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml \
  --tool-path proxmox-k3s \
  --cycle-id C1 \
  --confirm-delete
```

Use the standalone wrapper when the operation is provider-specific but still needs a local command manifest. Use the cycle-level wrapper for normal cycle execution.

---

## Direct Provider Commands

Direct provider commands bypass benchmark-suite profile resolution and artifact governance. Use them only for controlled maintenance or troubleshooting.

### Create a Cluster Directly

### Windows PowerShell

```powershell
proxmox-k3s cluster create -c .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml
```

### Bash

```bash
proxmox-k3s cluster create -c ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml
```

### Refresh Kubeconfig Directly

### Windows PowerShell

```powershell
proxmox-k3s cluster kubeconfig -c .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml
```

### Bash

```bash
proxmox-k3s cluster kubeconfig -c ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml
```

### Delete a Cluster Directly

The direct provider delete command is interactive. Confirm the prompt only after verifying that the selected local YAML file targets the intended cluster. Prefer the benchmark-suite wrapper for non-interactive, artifact-producing deletion.

### Windows PowerShell

```powershell
proxmox-k3s cluster delete -c .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml
```

### Bash

```bash
proxmox-k3s cluster delete -c ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml
```

Prefer wrapper-based deletion whenever the operation is part of a documented benchmark-suite workflow.

---

## Provider Template Lifecycle

`proxmox-k3s` can create a reusable VM template. The template lifecycle is separate from the benchmark cycle lifecycle.

Template creation is normally a one-time infrastructure preparation step. Do not delete templates as part of ordinary benchmark regeneration unless a dedicated maintenance procedure explicitly requires it.

The provider template file must expose `taint_control_plane` so generated YAML can preserve the intended K3s control-plane taint behavior. This is especially important for C8 and C9, where management-node isolation is part of the validation boundary.

### Create the Provider Template Directly

### Windows PowerShell

```powershell
proxmox-k3s template create -c .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml
```

### Bash

```bash
proxmox-k3s template create -c ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml
```

### Create the Provider Template Through the Standalone Wrapper

### Windows PowerShell

```powershell
.\scripts\infrastructure\provision\Invoke-ProxmoxK3sStandaloneCommand.ps1 `
  -Command template-create `
  -ConfigPath .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml `
  -ToolPath proxmox-k3s `
  -CycleId C1
```

### Bash

```bash
./scripts/infrastructure/provision/invoke-proxmox-k3s-standalone-command.sh \
  --command template-create \
  --config ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml \
  --tool-path proxmox-k3s \
  --cycle-id C1
```

### Delete the Provider Template Through the Standalone Wrapper

### Windows PowerShell

```powershell
.\scripts\infrastructure\provision\Invoke-ProxmoxK3sStandaloneCommand.ps1 `
  -Command template-delete `
  -ConfigPath .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml `
  -ToolPath proxmox-k3s `
  -CycleId C1
```

### Bash

```bash
./scripts/infrastructure/provision/invoke-proxmox-k3s-standalone-command.sh \
  --command template-delete \
  --config ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml \
  --tool-path proxmox-k3s \
  --cycle-id C1
```

Template deletion is intentionally excluded from ordinary cycle lifecycle policies. Treat it as a manual maintenance operation.

---

## Provider Artifacts

Provider-backed execution writes infrastructure artifacts under cycle-specific results directories.

Typical locations are:

| Artifact family | Example path for `C1` |
|---|---|
| Lifecycle manifests | `results/experimental-cycles/C1/infrastructure/lifecycle/` |
| Provisioning logs and manifests | `results/experimental-cycles/C1/infrastructure/provisioning/` |
| Cluster validation outputs | `results/experimental-cycles/C1/infrastructure/validation/` |
| Deletion logs and manifests | `results/experimental-cycles/C1/infrastructure/deletion/` |

Generated provider artifacts are reproducibility evidence. They record which infrastructure profile, provider binding, lifecycle mode, and kubeconfig path were used before workload execution.

---

## Provider-Backed Execution Order

For a provider-backed cycle, use the following operational order.

1. Verify local tooling with `02-local-environment-and-tooling.md`.
2. Verify local provider configuration and secret handling with `03-access-secrets-and-local-configuration.md`.
3. Render or inspect the lifecycle manifest.
4. Run a dry-run provider resolution.
5. Provision or reuse the K3s cluster.
6. Refresh or verify the generated kubeconfig.
7. Validate the provider-backed cluster.
8. Continue with application deployment and benchmark execution in the cycle-specific runbook.
9. Delete the cluster only when the lifecycle policy or cleanup procedure requires it.

The first application-level operation must occur only after provider-backed cluster validation has succeeded or after the relevant execution runbook explicitly accepts a documented warning state.

---

## Safety Checklist Before Real Provider Execution

Before running `provision`, `kubeconfig`, or `destroy`, verify the following items.

| Check | Required state |
|---|---|
| VPN or private-network access | Active when required by the environment. |
| `proxmox-k3s` binary | Available in `PATH` or passed through `ToolPath`. |
| Local provider YAML | Exists and has been reviewed. |
| Provider YAML type | Must be `.local.yaml` for real execution. |
| Example YAML | Must not be used for real execution. |
| Proxmox credentials | Present only in local files or secure local environment. |
| IP and VMID ranges | Confirmed not to collide with other active executions. |
| Cluster name | Compatible with the active cluster reuse policy. |
| Lifecycle policy | Matches the intended execution semantics. |
| Deletion intent | Explicitly confirmed for destructive operations. |
| Artifact output root | Writable under `results/experimental-cycles/<cycle>/infrastructure/`. |

---

## Common Failure Patterns

| Symptom | Likely cause | Recommended action |
|---|---|---|
| Provider wrapper fails before invoking `proxmox-k3s` | Missing local provider YAML or unsafe configuration resolution | Verify the matching `.local.yaml` file and run a dry-run plan. |
| Template creation fails during package update | Incorrect gateway, DNS, or network settings in the provider YAML | Correct network settings and retry after cleaning partial resources if needed. |
| Cluster create fails after partial VM creation | Interrupted provider execution or Proxmox-side error | Inspect provider logs, then delete or clean up the partial cluster before retrying. |
| Kubeconfig file is missing after provisioning | Provider kubeconfig export failed or YAML path mismatch | Run the `kubeconfig` action and verify the configured `clusters[*].kubeconfig_path`. |
| Cluster validation fails on node readiness | K3s node did not join or is not Ready | Inspect Proxmox VM state and `kubectl get nodes -o wide`. |
| Metrics validation fails | Metrics API unavailable or delayed | Use the cycle-specific validation policy; allow warnings only when the runbook explicitly permits it. |
| Destroy is refused by the wrapper | Missing explicit confirmation | Re-run with `ConfirmDelete` or `--confirm-delete` only after verifying the target cluster identity. |
| Unexpected cluster replacement | Shared reusable cluster name, IP range, or VMID range | Stop concurrent runs and inspect the active cluster reuse policy. |

---

## Readiness Criteria

The provider-backed infrastructure layer is ready for application deployment when all conditions below are true.

1. The intended provider-backed cycle configuration is selected.
2. The matching provider binding resolves to a reviewed `.local.yaml` file for real execution.
3. The lifecycle manifest is written under the cycle infrastructure artifacts.
4. Provisioning has completed successfully, or an intended reusable cluster has been confirmed.
5. The generated kubeconfig exists, is non-empty, and points to the intended cluster.
6. `kubectl get nodes` shows all expected nodes.
7. Provider-backed cluster validation has produced an accepted status.
8. Provisioning and validation artifacts are written under the expected `results/experimental-cycles/<cycle>/infrastructure/` tree.
9. No concurrent provider-backed campaign is targeting the same reusable cluster identity.

After these criteria are satisfied, continue with the application deployment and benchmark execution runbooks.
