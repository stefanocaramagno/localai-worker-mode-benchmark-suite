# Access, Secrets, and Local Configuration

## Purpose

This runbook defines how local access material, generated kubeconfigs, provider-specific configuration files, and environment-specific values must be prepared and handled before running the benchmark suite.

It covers:

1. fixed-cluster access for the historical execution track `C0`;
2. provider-backed access for execution tracks `C1` through `C9`;
3. local-only configuration files for the `proxmox-k3s` provider;
4. secret-management rules;
5. Kubernetes access validation;
6. canonical namespace preparation;
7. Git ignore validation;
8. safe archive and sharing practices.

This runbook does not install local tooling. Local workstation prerequisites are covered in `02-local-environment-and-tooling.md`. Provider lifecycle operations are covered in `04-proxmox-k3s-provider-lifecycle.md`.

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

## Access Model Overview

The repository supports two access models.

| Execution track | Cluster source | Access material | Expected handling |
|---|---|---|---|
| `C0` | Existing fixed Kubernetes/K3s cluster | `config/cluster-access/fixed-cluster/kubeconfig` | Manually provided local file, never committed |
| `C1`-`C9` | Provider-backed K3s clusters created through `proxmox-k3s` | `config/cluster-access/generated/proxmox-k3s/<profile>/kubeconfig` | Generated runtime file, never committed |

The benchmark suite must not rely on the workstation default Kubernetes context. Any cluster-facing command must use the intended kubeconfig path explicitly.

---

## Local-Only and Secret-Bearing Files

The following files and directories are local execution artifacts and must not be committed.

| Path | Purpose | Sensitivity |
|---|---|---|
| `config/cluster-access/fixed-cluster/kubeconfig` | Fixed-cluster kubeconfig used by `C0` | Contains real Kubernetes access material |
| `config/cluster-access/generated/proxmox-k3s/**/kubeconfig` | Provider-generated kubeconfigs for `C1`-`C9` | Contains real Kubernetes access material |
| `config/infrastructure/providers/proxmox-k3s/local/*.local.yaml` | Environment-specific Proxmox provider inputs | May contain API endpoints, tokens, IP ranges, node mappings, local paths |

The repository contains `.example` files and placeholders to document the expected layout. Real local files must be created by the operator and kept outside version control.

---

## Verify Ignore Rules for Sensitive Paths

Before creating or copying real access files, verify that Git ignores the intended local paths.

### Windows PowerShell

```powershell
git check-ignore -v .\config\cluster-access\fixed-cluster\kubeconfig
git check-ignore -v .\config\cluster-access\generated\proxmox-k3s\example-profile\kubeconfig
git check-ignore -v .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml
```

### Bash

```bash
git check-ignore -v ./config/cluster-access/fixed-cluster/kubeconfig
git check-ignore -v ./config/cluster-access/generated/proxmox-k3s/example-profile/kubeconfig
git check-ignore -v ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml
```

Each command must print the matching ignore rule. If any command returns no matching rule, stop and inspect `.gitignore` before placing real credentials in the repository tree.

---

## Fixed-Cluster Access for `C0`

The historical fixed-cluster execution track `C0` uses a manually supplied kubeconfig.

Canonical local path:

```text
config/cluster-access/fixed-cluster/kubeconfig
```

Example template path:

```text
config/cluster-access/fixed-cluster/kubeconfig.example
```

### Create the Local Kubeconfig from the Example Template

Copy the example file to the local-only path, then replace all placeholders with the real cluster access material.

### Windows PowerShell

```powershell
Copy-Item `
  -Path .\config\cluster-access\fixed-cluster\kubeconfig.example `
  -Destination .\config\cluster-access\fixed-cluster\kubeconfig `
  -Force
```

### Bash

```bash
cp \
  ./config/cluster-access/fixed-cluster/kubeconfig.example \
  ./config/cluster-access/fixed-cluster/kubeconfig
```

After editing the copied file, verify that it exists.

### Windows PowerShell

```powershell
Test-Path .\config\cluster-access\fixed-cluster\kubeconfig
```

### Bash

```bash
test -f ./config/cluster-access/fixed-cluster/kubeconfig && echo "kubeconfig found"
```

### Validate the Fixed-Cluster Kubeconfig Structure

This check validates that `kubectl` can parse the file and resolve the active context.

### Windows PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\fixed-cluster\kubeconfig config current-context
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/fixed-cluster/kubeconfig config current-context
```

### Validate Fixed-Cluster Reachability

The VPN or equivalent private-network access must be active before running this command.

### Windows PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\fixed-cluster\kubeconfig cluster-info
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/fixed-cluster/kubeconfig cluster-info
```

### Validate Fixed-Cluster Nodes

### Windows PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\fixed-cluster\kubeconfig get nodes -o wide
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/fixed-cluster/kubeconfig get nodes -o wide
```

The command must return the intended fixed cluster nodes in `Ready` state before executing `C0` workflows.

---

## Canonical Application Namespace

The canonical namespace for benchmark workloads is:

```text
localai-benchmark
```

For `C0`, this namespace must not be assumed to exist. Create it explicitly if it is missing.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\fixed-cluster\kubeconfig"
$Namespace = "localai-benchmark"

kubectl --kubeconfig $Kubeconfig get namespace $Namespace *> $null
if ($LASTEXITCODE -ne 0) {
    kubectl --kubeconfig $Kubeconfig create namespace $Namespace
}
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/fixed-cluster/kubeconfig"
NAMESPACE="localai-benchmark"

if ! kubectl --kubeconfig "$KUBECONFIG_PATH" get namespace "$NAMESPACE" >/dev/null 2>&1; then
  kubectl --kubeconfig "$KUBECONFIG_PATH" create namespace "$NAMESPACE"
fi
```

Validate that the namespace is active.

### Windows PowerShell

```powershell
kubectl --kubeconfig .\config\cluster-access\fixed-cluster\kubeconfig get namespace localai-benchmark
```

### Bash

```bash
kubectl --kubeconfig ./config/cluster-access/fixed-cluster/kubeconfig get namespace localai-benchmark
```

Provider-backed executions must also use `localai-benchmark` as the application namespace unless a cycle-specific profile explicitly declares a different namespace.

---

## Provider-Backed Local Configuration for `proxmox-k3s`

Provider-backed cycles use environment-specific YAML files under:

```text
config/infrastructure/providers/proxmox-k3s/local/
```

These files are copied from reviewed examples under:

```text
config/infrastructure/providers/proxmox-k3s/examples/
```

Example files are safe to commit because they contain placeholders or redacted values. Local files are not safe to commit because they may contain real provider details.

### Create a Local Provider Configuration from an Example

The following example prepares the local provider configuration for the `C1` baseline infrastructure profile.

### Windows PowerShell

```powershell
Copy-Item `
  -Path .\config\infrastructure\providers\proxmox-k3s\examples\cluster.c1-1cp-2w-8c16g.example.yaml `
  -Destination .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml `
  -Force
```

### Bash

```bash
cp \
  ./config/infrastructure/providers/proxmox-k3s/examples/cluster.c1-1cp-2w-8c16g.example.yaml \
  ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml
```

Edit the local file and replace all placeholder values with the values assigned for the target Proxmox environment.

### Local Provider Fields That Require Review

At minimum, review the following fields in each local provider configuration:

| Field group | Required review |
|---|---|
| `proxmox.api_url` | Must point to the correct Proxmox API endpoint |
| `proxmox.token_id` | Must match the intended local API token identifier |
| `proxmox.token_secret` | Must be populated locally and never committed |
| `template.*` | Must match the intended template, storage, bridge, gateway, DNS, image storage, and VMID policy |
| `clusters[*].name` | Must identify the intended K3s cluster declared by the provider YAML |
| `clusters[*].kubeconfig_path` | Must point to the expected generated kubeconfig location under `config/cluster-access/generated/proxmox-k3s/` |
| `clusters[*].control_plane[*].*` | Must match the intended control-plane VM resource and network assignment |
| `clusters[*].workers[*].*` | Must match the intended worker VM resources, IPs, Proxmox node placement, labels, and taints |
| `clusters[*].k3s.*` | Must preserve the intended K3s version, server arguments, labels, taints, and addon-relevant settings |

Do not place real tokens, private endpoints, private key material, or operator-specific secrets in example files.

---


### C8 Local Provider Configuration

C8 requires local provider files for the two supported infrastructure envelopes:

```text
config/infrastructure/providers/proxmox-k3s/local/cluster.c8-1cp-2w-8c16g.local.yaml
config/infrastructure/providers/proxmox-k3s/local/cluster.c8-1cp-4w-8c16g.local.yaml
```

These files must be reviewed before real execution. In addition to normal Proxmox fields, each C8 cluster entry must preserve the management-node policy used by monitoring and scheduler components:

```yaml
clusters:
  - name: genai-pb
    k3s:
      taint_control_plane: false
      extra_server_args: "--disable=traefik --disable=servicelb --disable-network-policy --embedded-registry --node-label=nodepool=management --node-taint=nodepool=management:NoSchedule"
```

The local token values remain local-only and must not be committed.

### C9 Local Provider Configuration

C9 uses the provider-local file below for the four-worker network-aware scheduler campaign:

```text
config/infrastructure/providers/proxmox-k3s/local/cluster.c9-1cp-4w-8c16g.local.yaml
```

The local file must be reviewed before real execution because it controls the provider environment, VM addressing, node placement, kubeconfig output path, the management-node taint, and the infrastructure add-ons required by C9.

The C9 provider configuration must enable, or otherwise make available through the provider workflow, the following runtime prerequisites:

```text
monitoring
mon-agent
cluster-lens
Mentat
Istio
```

C9 keeps the management node label used by the benchmark profiles, but its taint must match the provider-managed add-on toleration convention:

```yaml
clusters:
  - name: genai-pb
    k3s:
      taint_control_plane: false
      extra_server_args: "--disable=traefik --disable=servicelb --embedded-registry --node-label=nodepool=management --node-taint=ManagementOnly=true:NoSchedule"
```

The `cluster_lens` add-on should be enabled in the same C9 provider file so that placement evidence can be captured during the campaign.

### Validate C8 Local Provider Configuration Presence

#### Windows PowerShell

```powershell
$C8ProviderFiles = @(
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c8-1cp-2w-8c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c8-1cp-4w-8c16g.local.yaml"
)
foreach ($Path in $C8ProviderFiles) {
  if (-not (Test-Path $Path)) {
    throw "Missing C8 provider local configuration: $Path"
  }
  git check-ignore -v $Path
}
```

#### Bash

```bash
c8_provider_files=(
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c8-1cp-2w-8c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c8-1cp-4w-8c16g.local.yaml"
)
for path in "${c8_provider_files[@]}"; do
  test -f "$path" || { echo "Missing C8 provider local configuration: $path" >&2; exit 1; }
  git check-ignore -v "$path"
done
```

## Validate Local Provider Configuration Presence

### Windows PowerShell

```powershell
Test-Path .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml
```

### Bash

```bash
test -f ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml && echo "provider local configuration found"
```

Validate that the local provider file is ignored by Git.

### Windows PowerShell

```powershell
git check-ignore -v .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml
```

### Bash

```bash
git check-ignore -v ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml
```

---

### Validate C9 Local Provider Configuration Presence

### Windows PowerShell

```powershell
$C9ProviderYaml = ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c9-1cp-4w-8c16g.local.yaml"
if (-not (Test-Path $C9ProviderYaml)) {
  throw "Missing C9 provider-local YAML: $C9ProviderYaml"
}
```

### Bash

```bash
C9_PROVIDER_YAML="./config/infrastructure/providers/proxmox-k3s/local/cluster.c9-1cp-4w-8c16g.local.yaml"
test -f "$C9_PROVIDER_YAML" || { echo "Missing C9 provider-local YAML: $C9_PROVIDER_YAML" >&2; exit 1; }
```

## Provider-Generated Kubeconfigs

When `proxmox-k3s` provisions a cluster or retrieves its kubeconfig, the benchmark suite expects the generated kubeconfig under:

```text
config/cluster-access/generated/proxmox-k3s/<profile-id>/kubeconfig
```

For example:

```text
config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig
```

The exact path is defined by the provider binding and local provider YAML used for the cycle.

### Validate a Provider-Generated Kubeconfig

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig"

Test-Path $Kubeconfig
kubectl --kubeconfig $Kubeconfig config current-context
kubectl --kubeconfig $Kubeconfig get nodes -o wide
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig"

test -f "$KUBECONFIG_PATH" && echo "generated kubeconfig found"
kubectl --kubeconfig "$KUBECONFIG_PATH" config current-context
kubectl --kubeconfig "$KUBECONFIG_PATH" get nodes -o wide
```

If the file is missing, run the provider lifecycle procedure documented in `04-proxmox-k3s-provider-lifecycle.md` or the relevant provider-backed execution runbook.

---

## Validate Provider Binding Resolution Without Exposing Secrets

The provider-backed provisioning launcher can be executed in dry-run mode to validate cycle and provider resolution without invoking destructive or external operations.

### Windows PowerShell

```powershell
.\scripts\infrastructure\provision\Start-ProviderBackedProvisioning.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -Action plan `
  -ProviderConfig .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml `
  -ToolPath proxmox-k3s `
  -DryRun `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/infrastructure/provision/start-provider-backed-provisioning.sh \
  --cycle-config ./config/experimental-cycles/C1.json \
  --action plan \
  --provider-config ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml \
  --tool-path proxmox-k3s \
  --dry-run \
  --write-latest-aliases
```

This command must be treated as a configuration-resolution check. It does not replace full provisioning validation.

---

## Optional Temporary `KUBECONFIG` Environment Variable

Most runbooks use explicit `--kubeconfig` arguments. This is the preferred approach because it prevents accidental use of the wrong cluster.

For short manual inspection only, a temporary shell-scoped `KUBECONFIG` variable may be used.

### Windows PowerShell

```powershell
$env:KUBECONFIG = ".\config\cluster-access\fixed-cluster\kubeconfig"
kubectl get nodes
Remove-Item Env:\KUBECONFIG
```

### Bash

```bash
export KUBECONFIG="./config/cluster-access/fixed-cluster/kubeconfig"
kubectl get nodes
unset KUBECONFIG
```

Do not rely on this variable for scripted benchmark execution unless the specific script explicitly documents that behavior.

---

## Safe Handling Rules

Follow these rules whenever handling access material or provider-local configuration.

1. Never commit real kubeconfigs.
2. Never commit provider-local YAML files containing real Proxmox endpoint details or tokens.
3. Never paste client certificates, client keys, API tokens, or provider secrets into documentation, issue descriptions, pull requests, or reports.
4. Do not rename local-only files to remove `.local` or `.example` semantics.
5. Keep example files placeholder-based and review-safe.
6. Use explicit kubeconfig paths for all Kubernetes commands.
7. Treat files under `results/` as generated artifacts, but inspect them before sharing because logs may include local paths or environment-specific identifiers.
8. Treat manually created ZIP archives as potentially unsafe unless they are produced from tracked, reviewed files only.

---

## Safe Archive Creation

When a clean shareable archive is required, prefer generating it from Git-tracked content instead of compressing the working directory manually.

### Windows PowerShell

```powershell
git archive --format zip --output .\localai-worker-mode-benchmark-suite.clean.zip HEAD
```

### Bash

```bash
git archive --format zip --output ./localai-worker-mode-benchmark-suite.clean.zip HEAD
```

Validate that local-only access files are not present in the archive.

### Windows PowerShell

```powershell
Expand-Archive .\localai-worker-mode-benchmark-suite.clean.zip -DestinationPath .\_archive_check -Force
Get-ChildItem .\_archive_check -Recurse | Where-Object { $_.FullName -match "kubeconfig|\.local\.yaml" }
Remove-Item .\_archive_check -Recurse -Force
```

### Bash

```bash
rm -rf ./_archive_check
mkdir -p ./_archive_check
unzip -q ./localai-worker-mode-benchmark-suite.clean.zip -d ./_archive_check
find ./_archive_check -type f \( -name "kubeconfig" -o -name "*.local.yaml" \)
rm -rf ./_archive_check
```

The validation command should not list any real local access file. If it does, do not share the archive.

---

## Access Readiness Checklist

Before running any benchmark workflow, confirm the following checklist.

| Check | Required for `C0` | Required for `C1`-`C9` |
|---|---:|---:|
| Local tooling is installed | Yes | Yes |
| VPN or equivalent private network access is active, when required | Yes | Environment-dependent |
| Fixed-cluster kubeconfig exists | Yes | No |
| Provider-local YAML exists | No | Yes |
| Provider-generated kubeconfig exists | No | Yes, after provisioning or kubeconfig retrieval |
| Kubeconfig is ignored by Git | Yes | Yes |
| Provider-local YAML is ignored by Git | Not applicable | Yes |
| Kubernetes API is reachable | Yes | Yes |
| Expected nodes are `Ready` | Yes | Yes |
| Namespace `localai-benchmark` exists or can be created | Yes | Yes |

---

## Common Failure Modes

| Symptom | Likely cause | Recovery direction |
|---|---|---|
| `kubectl cluster-info` times out | VPN or private-network route is missing | Reconnect the VPN or verify network reachability |
| `kubectl` reports authentication errors | Kubeconfig is stale or invalid | Replace the local kubeconfig with a valid one |
| `kubectl get nodes` returns an unexpected cluster | Wrong kubeconfig or default context used | Use explicit `--kubeconfig` paths |
| Namespace creation fails | Missing permissions or wrong cluster | Validate context and RBAC permissions |
| Provider dry-run cannot resolve local config | Missing `.local.yaml` file or wrong path | Copy the correct example file and edit local values |
| Provider create fails during network setup | Incorrect gateway, bridge, DNS, IP range, or Proxmox node mapping | Review the local provider YAML |
| Generated kubeconfig is missing after provisioning | Provider command failed or wrote to a different path | Inspect provisioning logs and provider binding |
| Local secrets appear in Git status | Ignore rules are incomplete or file was force-added | Remove the file from the index and fix ignore rules |

---

## Remove Accidentally Staged Local Files

If a local access file was accidentally staged, remove it from the Git index without deleting the local working copy.

### Windows PowerShell

```powershell
git rm --cached .\config\cluster-access\fixed-cluster\kubeconfig
git rm --cached .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml
```

### Bash

```bash
git rm --cached ./config/cluster-access/fixed-cluster/kubeconfig
git rm --cached ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml
```

Then validate that the files are ignored.

### Windows PowerShell

```powershell
git check-ignore -v .\config\cluster-access\fixed-cluster\kubeconfig
git check-ignore -v .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml
```

### Bash

```bash
git check-ignore -v ./config/cluster-access/fixed-cluster/kubeconfig
git check-ignore -v ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml
```

---

## Completion Criteria

This runbook is complete when:

1. the fixed-cluster kubeconfig required by `C0` is available locally, ignored by Git, and validated with `kubectl`;
2. the canonical namespace `localai-benchmark` exists or can be created on the fixed cluster;
3. the provider-local YAML files required by provider-backed cycles are available locally and ignored by Git;
4. provider-generated kubeconfig paths are understood and validated after provisioning;
5. all sensitive files are excluded from version control and from shareable archives;
6. all cluster-facing operations use explicit kubeconfig paths.

After these conditions are satisfied, proceed to `04-proxmox-k3s-provider-lifecycle.md` for provider lifecycle operations or to `06-fixed-cluster-c0-execution.md` for the historical fixed-cluster execution track.
