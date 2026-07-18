# Troubleshooting and Recovery

## Purpose

This runbook provides troubleshooting and recovery procedures for the LocalAI worker-mode benchmark suite.

It covers failures that may occur while preparing the local workstation, accessing a fixed Kubernetes cluster, provisioning provider-backed K3s clusters, deploying LocalAI, running benchmark workloads, collecting observability evidence, generating post-processing artifacts, and regenerating the complete `results/` tree.

The objective is to recover from operational failures without weakening the experimental evidence model. A failed, pending, non-schedulable, or unsupported scenario must be interpreted according to the active cycle profile, not manually rewritten into a successful measurement.

---

## Scope

This runbook covers recovery for the following areas:

1. local shell, Python, Locust, and script execution failures;
2. repository root and path-resolution errors;
3. kubeconfig and private-network access failures;
4. namespace, Kubernetes API, and Metrics API failures;
5. `proxmox-k3s` provider availability and lifecycle failures;
6. provider-local YAML, template, gateway, DNS, VM, and generated-kubeconfig failures;
7. Kustomize rendering and Kubernetes deployment failures;
8. LocalAI rollout, worker-mode, service, PVC, and model-loading failures;
9. port-forwarding, LocalAI API, and smoke-test failures;
10. Locust execution and benchmark artifact failures;
11. minimal observability, diagnosis, reporting, completion-gate, and freeze failures;
12. campaign-level partial failures and unsupported-scenario handling;
13. cleanup and safe rerun procedures.

This runbook does not replace the execution runbooks. Use it after a command from one of the execution runbooks fails, produces incomplete artifacts, or leaves the cluster in a state that must be inspected before a rerun.

---

## Repository Root Assumption

All commands in this runbook must be executed from the repository root:

```text
localai-worker-mode-benchmark-suite/
```

### Windows PowerShell

```powershell
Set-Location C:\Path\To\localai-worker-mode-benchmark-suite
Get-Location
```

### Bash

```bash
cd /path/to/localai-worker-mode-benchmark-suite
pwd
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

## Recovery Principles

Follow these principles before applying any recovery action.

1. **Preserve evidence first**: capture logs, manifests, events, and generated artifacts before deleting resources.
2. **Do not rely on the default Kubernetes context**: use the intended kubeconfig explicitly.
3. **Separate fixed-cluster and provider-backed recovery**: `C0` is not managed by `proxmox-k3s`; `C1` through `C9` are provider-backed.
4. **Do not edit generated runtime profiles**: files under `results/experimental-cycles/<cycle>/execution/generated-runtime-configs/` are outputs, not source configuration.
5. **Do not convert unsupported scenarios into successful measurements**: if a scenario is unsupported under declared constraints, preserve the unsupported evidence.
6. **Use destructive recovery only after inspection**: provider-backed delete operations must be explicitly confirmed and must target the intended cluster.
7. **Rerun at the smallest safe scope**: prefer rerunning a failed stage or cycle before deleting broader evidence.
8. **Regenerate from source profiles**: source-of-truth configuration lives under `config/`, not under `results/`.

---

## Initial Triage Checklist

When a command fails, perform the following triage before changing anything.

| Question | Action |
|---|---|
| Did the command run from the repository root? | Validate the current directory and required paths. |
| Was the correct shell used? | Use the documented PowerShell or Bash entry point consistently. |
| Was the intended kubeconfig passed explicitly? | Inspect the command and validate the kubeconfig path. |
| Is the target cluster reachable? | Run `cluster-info` and `get nodes`. |
| Did a provider-backed operation use the correct local YAML file? | Inspect the resolved provider config and generated artifacts. |
| Did the failure occur during scheduling or rollout? | Capture pod status, events, and deployment descriptions. |
| Did Locust fail or did LocalAI fail before Locust started? | Separate API reachability from load generation. |
| Are artifacts missing or malformed? | Regenerate post-processing only after benchmark evidence exists. |

---

## Capture a Recovery Snapshot

Before deleting resources or rerunning a failed cycle, capture a local recovery snapshot.

### Windows PowerShell

```powershell
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RecoveryRoot = ".\results\recovery\$Stamp"
New-Item -ItemType Directory -Force -Path $RecoveryRoot | Out-Null

Get-Location | Out-File "$RecoveryRoot\working-directory.txt" -Encoding utf8
Get-ChildItem | Out-File "$RecoveryRoot\repository-root-listing.txt" -Encoding utf8

if (Get-Command git -ErrorAction SilentlyContinue) {
  git status --short | Out-File "$RecoveryRoot\git-status-short.txt" -Encoding utf8
}
```

### Bash

```bash
STAMP="$(date +%Y%m%d_%H%M%S)"
RECOVERY_ROOT="./results/recovery/$STAMP"
mkdir -p "$RECOVERY_ROOT"

pwd > "$RECOVERY_ROOT/working-directory.txt"
ls -la > "$RECOVERY_ROOT/repository-root-listing.txt"

if command -v git >/dev/null 2>&1; then
  git status --short > "$RECOVERY_ROOT/git-status-short.txt"
fi
```

When a Kubernetes cluster is reachable, also capture cluster evidence.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\fixed-cluster\kubeconfig"
$Namespace = "localai-benchmark"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RecoveryRoot = ".\results\recovery\$Stamp"
New-Item -ItemType Directory -Force -Path $RecoveryRoot | Out-Null

kubectl --kubeconfig $Kubeconfig get nodes -o wide | Out-File "$RecoveryRoot\nodes-wide.txt" -Encoding utf8
kubectl --kubeconfig $Kubeconfig get pods -A -o wide | Out-File "$RecoveryRoot\pods-all-wide.txt" -Encoding utf8
kubectl --kubeconfig $Kubeconfig get events -A --sort-by=.lastTimestamp | Out-File "$RecoveryRoot\events-all.txt" -Encoding utf8
kubectl --kubeconfig $Kubeconfig get pods -n $Namespace -o yaml | Out-File "$RecoveryRoot\pods-$Namespace.yaml" -Encoding utf8
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/fixed-cluster/kubeconfig"
NAMESPACE="localai-benchmark"
STAMP="$(date +%Y%m%d_%H%M%S)"
RECOVERY_ROOT="./results/recovery/$STAMP"
mkdir -p "$RECOVERY_ROOT"

kubectl --kubeconfig "$KUBECONFIG_PATH" get nodes -o wide > "$RECOVERY_ROOT/nodes-wide.txt"
kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -A -o wide > "$RECOVERY_ROOT/pods-all-wide.txt"
kubectl --kubeconfig "$KUBECONFIG_PATH" get events -A --sort-by=.lastTimestamp > "$RECOVERY_ROOT/events-all.txt"
kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -n "$NAMESPACE" -o yaml > "$RECOVERY_ROOT/pods-$NAMESPACE.yaml"
```

For provider-backed cycles, replace the kubeconfig path with the generated kubeconfig associated with the active cycle or variant.

---

## Local Environment Issues

### Problem: Commands Are Being Run Outside the Repository Root

Symptoms include missing `config/`, `infra/`, `scripts/`, or `requirements.txt` paths.

Validate the repository root.

### Windows PowerShell

```powershell
$Required = @(".\config", ".\docs", ".\infra", ".\load-tests", ".\scripts", ".\requirements.txt")
foreach ($Path in $Required) {
  if (-not (Test-Path $Path)) {
    throw "Missing repository-root path: $Path"
  }
}
```

### Bash

```bash
required=("./config" "./docs" "./infra" "./load-tests" "./scripts" "./requirements.txt")
for path in "${required[@]}"; do
  test -e "$path" || { echo "Missing repository-root path: $path" >&2; exit 1; }
done
```

Recovery: move to the repository root and rerun the command.

---

### Problem: PowerShell Blocks Script Execution

Symptoms include messages about disabled script execution, unsigned scripts, `PSSecurityException`, or `UnauthorizedAccess` before the repository script starts.

Use the documented execution style with `-ExecutionPolicy Bypass`. Prefer the per-command bypass shown below instead of changing the global workstation policy.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCycle.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ExecutionScope provider-backed-cycle `
  -DryRun
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config config/experimental-cycles/C1.json \
  --dry-run
```

Recovery: do not change global workstation policy unless explicitly required. Prefer per-command bypass for repository scripts.

For the C7 campaign wrapper, use the same scoped invocation style.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C7.json `
  -ToolPath proxmox-k3s `
  -RunId "C7_default_scheduler_baseline" `
  -DryRun `
  -AllowMetricsWarning `
  -WriteLatestAliases
```

---

### Problem: Bash Scripts Are Not Executable

Symptoms include `Permission denied` when invoking `.sh` scripts.

Restore executable bits.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\maintenance\Set-BashExecutableBits.ps1
```

### Bash

```bash
chmod +x ./scripts/maintenance/set-bash-executable-bits.sh
./scripts/maintenance/set-bash-executable-bits.sh
```

Validate one entry point.

### Windows PowerShell

```powershell
Test-Path .\scripts\experimental-cycles\start-experimental-cycle.sh
```

### Bash

```bash
test -x ./scripts/experimental-cycles/start-experimental-cycle.sh && echo "executable"
```

---

### Problem: Python Is Not Available or Uses the Wrong Environment

Symptoms include `python: command not found`, missing modules, or Locust not being found.

Validate Python and package availability.

### Windows PowerShell

```powershell
python --version
python -m pip --version
python -m pip show locust
```

### Bash

```bash
python3 --version || python --version
python3 -m pip --version || python -m pip --version
python3 -m pip show locust || python -m pip show locust
```

Reinstall dependencies from the repository requirements file.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

### Bash

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r ./requirements.txt
```

Recovery: activate the virtual environment or use the virtual-environment Python path consistently throughout the run.

---

### Problem: JSON Configuration Validation Fails

Symptoms include Python JSON parsing errors or launcher failures before runtime execution starts.

Identify invalid JSON files.

### Windows PowerShell

```powershell
Get-ChildItem .\config -Recurse -Filter *.json | ForEach-Object {
  python -m json.tool $_.FullName > $null
  if ($LASTEXITCODE -ne 0) {
    throw "Invalid JSON file: $($_.FullName)"
  }
}
```

### Bash

```bash
find ./config -type f -name "*.json" -print0 |
while IFS= read -r -d '' file; do
  python3 -m json.tool "$file" >/dev/null || {
    echo "Invalid JSON file: $file" >&2
    exit 1
  }
done
```

Recovery: fix the source profile under `config/`; do not patch generated runtime profiles under `results/`.

---

## Cluster Access Issues

### Problem: The Fixed-Cluster Kubeconfig Is Missing

Symptoms include missing file errors for `config/cluster-access/fixed-cluster/kubeconfig`.

Validate the path.

### Windows PowerShell

```powershell
Test-Path .\config\cluster-access\fixed-cluster\kubeconfig
```

### Bash

```bash
test -f ./config/cluster-access/fixed-cluster/kubeconfig && echo "fixed-cluster kubeconfig found"
```

Recovery: restore the local fixed-cluster kubeconfig from the authorized source. If only the example file exists, copy it only as a template and replace placeholders with real local access material.

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

Do not commit the real kubeconfig.

---

### Problem: Kubernetes API Is Unreachable

Symptoms include connection timeouts, TLS errors, or `Unable to connect to the server`.

Validate the kubeconfig and cluster reachability.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\fixed-cluster\kubeconfig"
kubectl --kubeconfig $Kubeconfig config current-context
kubectl --kubeconfig $Kubeconfig cluster-info
kubectl --kubeconfig $Kubeconfig get nodes -o wide
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/fixed-cluster/kubeconfig"
kubectl --kubeconfig "$KUBECONFIG_PATH" config current-context
kubectl --kubeconfig "$KUBECONFIG_PATH" cluster-info
kubectl --kubeconfig "$KUBECONFIG_PATH" get nodes -o wide
```

Recovery actions:

1. verify that the private-network connection is active;
2. verify that the kubeconfig points to the intended API server;
3. verify that the cluster still exists;
4. rerun the same validation before applying workloads.

---

### Problem: The Default Kubernetes Context Is Accidentally Used

Symptoms include resources appearing in the wrong cluster or `kubectl` returning unexpected nodes.

Always compare the explicit kubeconfig context and the default context.

### Windows PowerShell

```powershell
kubectl config current-context
kubectl --kubeconfig .\config\cluster-access\fixed-cluster\kubeconfig config current-context
kubectl --kubeconfig .\config\cluster-access\fixed-cluster\kubeconfig get nodes -o wide
```

### Bash

```bash
kubectl config current-context
kubectl --kubeconfig ./config/cluster-access/fixed-cluster/kubeconfig config current-context
kubectl --kubeconfig ./config/cluster-access/fixed-cluster/kubeconfig get nodes -o wide
```

Recovery: rerun all cluster-facing commands with `--kubeconfig`. Do not rely on `KUBECONFIG` or the local default context unless a runbook explicitly asks for it.

---

### Problem: The Application Namespace Is Missing

Symptoms include `namespace not found`, failed deployment, or empty pod listings.

Create or validate the canonical namespace.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\fixed-cluster\kubeconfig"
$Namespace = "localai-benchmark"

kubectl --kubeconfig $Kubeconfig apply -k .\infra\k8s\compositions\foundation\namespace
kubectl --kubeconfig $Kubeconfig get namespace $Namespace
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/fixed-cluster/kubeconfig"
NAMESPACE="localai-benchmark"

kubectl --kubeconfig "$KUBECONFIG_PATH" apply -k ./infra/k8s/compositions/foundation/namespace
kubectl --kubeconfig "$KUBECONFIG_PATH" get namespace "$NAMESPACE"
```

Recovery: after namespace creation, apply the remaining deployment resources in the order documented by the relevant execution runbook.

---

## Provider-Backed Infrastructure Issues

### Problem: `proxmox-k3s` Is Not Found

Symptoms include `proxmox-k3s: command not found` or PowerShell failing to resolve the command.

Validate the provider binary.

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

If the binary is outside `PATH`, use an explicit tool path.

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

Recovery: pass the explicit tool path to provider-backed scripts.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCycle.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ExecutionScope provider-backed-cycle `
  -ToolPath "..\proxmox-k3s\bin\proxmox-k3s.exe" `
  -DryRun
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config config/experimental-cycles/C1.json \
  --tool-path ../proxmox-k3s/proxmox-k3s \
  --dry-run
```

---

### Problem: Local Provider YAML Is Missing

Symptoms include provider binding resolution failures or missing `.local.yaml` files.

Validate local provider configuration.

### Windows PowerShell

```powershell
Get-ChildItem .\config\infrastructure\providers\proxmox-k3s\local\*.local.yaml | Select-Object Name, Length
```

### Bash

```bash
find ./config/infrastructure/providers/proxmox-k3s/local -maxdepth 1 -type f -name '*.local.yaml' -print | sort
```

Create a local file from the matching example file and populate real environment values.

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

Recovery: edit the `.local.yaml` file and rerun a dry run before executing real provider operations.

---

### Problem: Provider Template Creation Fails Because of Network Configuration

Symptoms include failures during package refresh, template preparation, SSH wait, DNS resolution, or gateway reachability.

Inspect the provider-local YAML fields that control template networking.

### Windows PowerShell

```powershell
$ProviderConfig = ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml"
Select-String -Path $ProviderConfig -Pattern "template:|gateway:|dns:|ip:|bridge:|subnet_mask:"
```

### Bash

```bash
PROVIDER_CONFIG="./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml"
grep -nE 'template:|gateway:|dns:|ip:|bridge:|subnet_mask:' "$PROVIDER_CONFIG"
```

Validate the provider command in dry-run mode through the benchmark-suite wrapper.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\infrastructure\provision\Start-ProviderBackedProvisioning.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -Action plan `
  -ProviderConfig .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml `
  -DryRun
```

### Bash

```bash
./scripts/infrastructure/provision/start-provider-backed-provisioning.sh \
  --cycle-config config/experimental-cycles/C1.json \
  --action plan \
  --provider-config config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml \
  --dry-run
```

Recovery actions:

1. correct gateway, DNS, bridge, IP, subnet, storage, and Proxmox node values in the local YAML;
2. remove any partial template or VM only after confirming the target identity;
3. rerun template or cluster creation after validation.

---

### Problem: Provider-Backed Cluster Already Exists or Is Partially Created

Symptoms include VM name collisions, VMID conflicts, IP conflicts, or provisioning aborting after a previous partial run.

Inspect the lifecycle state through the wrapper and generated artifacts.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\infrastructure\provision\Start-ProviderBackedProvisioning.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -Action plan `
  -ToolPath proxmox-k3s `
  -DryRun `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/infrastructure/provision/start-provider-backed-provisioning.sh \
  --cycle-config config/experimental-cycles/C1.json \
  --action plan \
  --tool-path proxmox-k3s \
  --dry-run \
  --write-latest-aliases
```

If deletion is required, use the benchmark-suite wrapper and explicit confirmation only after validating the local YAML target.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\infrastructure\provision\Start-ProviderBackedProvisioning.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -Action destroy `
  -ToolPath proxmox-k3s `
  -ConfirmDelete `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/infrastructure/provision/start-provider-backed-provisioning.sh \
  --cycle-config config/experimental-cycles/C1.json \
  --action destroy \
  --tool-path proxmox-k3s \
  --confirm-delete \
  --write-latest-aliases
```

Recovery: after cleanup, rerun provisioning from a dry run first. Do not run concurrent provider-backed campaigns against the same reusable cluster identity.

---

### Problem: Generated Provider-Backed Kubeconfig Is Missing or Invalid

Symptoms include provider-backed cluster validation failing immediately after provisioning.

Validate the generated kubeconfig path.

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

Regenerate kubeconfig through the provider-backed wrapper.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\infrastructure\provision\Start-ProviderBackedProvisioning.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -Action kubeconfig `
  -ToolPath proxmox-k3s `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/infrastructure/provision/start-provider-backed-provisioning.sh \
  --cycle-config config/experimental-cycles/C1.json \
  --action kubeconfig \
  --tool-path proxmox-k3s \
  --write-latest-aliases
```

Recovery: if kubeconfig regeneration fails, inspect provider logs and confirm that the control-plane VM is running and reachable.

---

## Kubernetes Validation and Metrics Issues

### Problem: Nodes Are Not Ready

Symptoms include `NotReady`, `NodeStatusUnknown`, or missing worker nodes.

Inspect node status and events.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig"
kubectl --kubeconfig $Kubeconfig get nodes -o wide
kubectl --kubeconfig $Kubeconfig describe nodes
kubectl --kubeconfig $Kubeconfig get events -A --sort-by=.lastTimestamp
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig"
kubectl --kubeconfig "$KUBECONFIG_PATH" get nodes -o wide
kubectl --kubeconfig "$KUBECONFIG_PATH" describe nodes
kubectl --kubeconfig "$KUBECONFIG_PATH" get events -A --sort-by=.lastTimestamp
```

Recovery actions:

1. verify that the provider-backed VMs are powered on;
2. verify private-network reachability;
3. verify that K3s server and agents completed installation;
4. rerun cluster validation after the nodes become `Ready`;
5. if the cluster is irrecoverable, delete and recreate it through the provider lifecycle wrapper.

---

### Problem: Metrics API Is Not Available

Symptoms include failures in `kubectl top nodes`, `kubectl top pods`, cluster validation, or minimal observability.

Validate Metrics API availability.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig"
kubectl --kubeconfig $Kubeconfig get apiservice v1beta1.metrics.k8s.io
kubectl --kubeconfig $Kubeconfig top nodes
kubectl --kubeconfig $Kubeconfig top pods -A
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig"
kubectl --kubeconfig "$KUBECONFIG_PATH" get apiservice v1beta1.metrics.k8s.io
kubectl --kubeconfig "$KUBECONFIG_PATH" top nodes
kubectl --kubeconfig "$KUBECONFIG_PATH" top pods -A
```

For provider-backed execution, allow non-blocking metrics warnings only when the cluster is otherwise healthy and the active methodology accepts missing live metrics.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCycle.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ExecutionScope provider-backed-cycle `
  -AllowMetricsWarning `
  -DryRun
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config config/experimental-cycles/C1.json \
  --allow-metrics-warning \
  --dry-run
```

Recovery: prefer restoring metrics availability. Use warning bypass only as an explicit, documented choice.

---

## Kubernetes Deployment and Placement Issues

### Problem: Kustomize Rendering Fails

Symptoms include missing resource paths, patch failures, deprecated syntax warnings, or invalid YAML.

Render the target composition before applying it.

### Windows PowerShell

```powershell
kubectl kustomize .\infra\k8s\compositions\topology\colocated-genai-pb-worker-02-w2
kubectl kustomize .\infra\k8s\compositions\server\models\m1-provider-backed
```

### Bash

```bash
kubectl kustomize ./infra/k8s/compositions/topology/colocated-genai-pb-worker-02-w2
kubectl kustomize ./infra/k8s/compositions/server/models/m1-provider-backed
```

Recovery actions:

1. verify that the composition path exists;
2. verify that referenced base and overlay paths exist;
3. inspect recent profile changes under `config/placement/` and `config/application-deployment/`;
4. rerun the deployment through the cycle launcher after rendering succeeds.

---

### Problem: Pods Remain Pending

Symptoms include `Pending` pod phase, `FailedScheduling` events, insufficient CPU or memory, node-affinity conflicts, or unsatisfied taints.

Inspect pod placement and events.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c4-1cp-4w-8c16g\kubeconfig"
$Namespace = "localai-benchmark"

kubectl --kubeconfig $Kubeconfig get pods -n $Namespace -o wide
kubectl --kubeconfig $Kubeconfig describe pods -n $Namespace
kubectl --kubeconfig $Kubeconfig get events -n $Namespace --sort-by=.lastTimestamp
kubectl --kubeconfig $Kubeconfig describe nodes
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c4-1cp-4w-8c16g/kubeconfig"
NAMESPACE="localai-benchmark"

kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -n "$NAMESPACE" -o wide
kubectl --kubeconfig "$KUBECONFIG_PATH" describe pods -n "$NAMESPACE"
kubectl --kubeconfig "$KUBECONFIG_PATH" get events -n "$NAMESPACE" --sort-by=.lastTimestamp
kubectl --kubeconfig "$KUBECONFIG_PATH" describe nodes
```

Recovery interpretation:

| Condition | Interpretation |
|---|---|
| Insufficient memory or CPU | The scenario may be unsupported under current constraints. Preserve evidence. |
| Required node affinity does not match any node | Placement profile or node naming may be inconsistent with the active infrastructure profile. |
| Taints not tolerated | Inspect worker taints and deployment tolerations. |
| PVC pending | Inspect storage class and persistent volume provisioning. |
| Image pull failure | Inspect image name, registry reachability, and node network access. |

Do not remove pending evidence from campaign outputs when the scenario is intentionally capacity-stressing.

---

### Problem: Rollout Times Out

Symptoms include `timed out waiting for the condition` during deployment rollout.

Inspect the rollout, pod status, and container logs.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig"
$Namespace = "localai-benchmark"

kubectl --kubeconfig $Kubeconfig rollout status deployment/localai-server -n $Namespace --timeout=30s
kubectl --kubeconfig $Kubeconfig get pods -n $Namespace -o wide
kubectl --kubeconfig $Kubeconfig describe deployment/localai-server -n $Namespace
kubectl --kubeconfig $Kubeconfig logs deployment/localai-server -n $Namespace --tail=200
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig"
NAMESPACE="localai-benchmark"

kubectl --kubeconfig "$KUBECONFIG_PATH" rollout status deployment/localai-server -n "$NAMESPACE" --timeout=30s
kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -n "$NAMESPACE" -o wide
kubectl --kubeconfig "$KUBECONFIG_PATH" describe deployment/localai-server -n "$NAMESPACE"
kubectl --kubeconfig "$KUBECONFIG_PATH" logs deployment/localai-server -n "$NAMESPACE" --tail=200
```

Recovery actions:

1. if the rollout is slow because the model is loading, wait and recheck logs;
2. if pods are pending, use the pending-pod procedure;
3. if readiness fails, inspect LocalAI logs and service endpoints;
4. if this occurs in a comparative campaign, preserve the variant evidence and allow the campaign runner to classify it if applicable.

---

### Problem: PVC or Storage Is Not Available

Symptoms include model storage PVC pending, pod mount failures, or LocalAI failing to access `/models`.

Inspect storage resources.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig"
$Namespace = "localai-benchmark"

kubectl --kubeconfig $Kubeconfig get storageclass
kubectl --kubeconfig $Kubeconfig get pvc -n $Namespace
kubectl --kubeconfig $Kubeconfig describe pvc -n $Namespace
kubectl --kubeconfig $Kubeconfig get events -n $Namespace --sort-by=.lastTimestamp
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig"
NAMESPACE="localai-benchmark"

kubectl --kubeconfig "$KUBECONFIG_PATH" get storageclass
kubectl --kubeconfig "$KUBECONFIG_PATH" get pvc -n "$NAMESPACE"
kubectl --kubeconfig "$KUBECONFIG_PATH" describe pvc -n "$NAMESPACE"
kubectl --kubeconfig "$KUBECONFIG_PATH" get events -n "$NAMESPACE" --sort-by=.lastTimestamp
```

Recovery: ensure that the expected storage class exists and that the foundation storage composition has been applied before LocalAI server startup.

---

### Problem: Worker-Mode Runtime Configuration Is Inconsistent

Symptoms include LocalAI server running but not using the expected RPC workers, worker count mismatch, or failed RPC connections.

Inspect the runtime configuration, services, endpoints, and active deployments.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig"
$Namespace = "localai-benchmark"

kubectl --kubeconfig $Kubeconfig get configmap localai-runtime-config -n $Namespace -o yaml
kubectl --kubeconfig $Kubeconfig get svc -n $Namespace
kubectl --kubeconfig $Kubeconfig get endpoints -n $Namespace
kubectl --kubeconfig $Kubeconfig get deploy -n $Namespace
kubectl --kubeconfig $Kubeconfig get pods -n $Namespace -o wide
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig"
NAMESPACE="localai-benchmark"

kubectl --kubeconfig "$KUBECONFIG_PATH" get configmap localai-runtime-config -n "$NAMESPACE" -o yaml
kubectl --kubeconfig "$KUBECONFIG_PATH" get svc -n "$NAMESPACE"
kubectl --kubeconfig "$KUBECONFIG_PATH" get endpoints -n "$NAMESPACE"
kubectl --kubeconfig "$KUBECONFIG_PATH" get deploy -n "$NAMESPACE"
kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -n "$NAMESPACE" -o wide
```

Recovery actions:

1. verify that `LLAMACPP_GRPC_SERVERS` matches the active worker-count overlay;
2. verify that each listed RPC service has endpoints;
3. redeploy through the relevant execution launcher instead of manually editing live ConfigMaps;
4. expect a server restart or reload when the active worker set changes.

---

## Port-Forwarding and LocalAI API Issues

### Problem: Local Port `8080` Is Already in Use

Symptoms include port-forward failure or `address already in use`.

Inspect local listeners.

### Windows PowerShell

```powershell
Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress, LocalPort, State, OwningProcess

Get-Process -Id (Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue).OwningProcess -ErrorAction SilentlyContinue
```

### Bash

```bash
(ss -ltnp 2>/dev/null || lsof -iTCP:8080 -sTCP:LISTEN 2>/dev/null || true) | grep 8080 || true
```

Terminate only the process that belongs to an old benchmark or port-forward session.

### Windows PowerShell

```powershell
$Connections = Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue
$Connections | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

### Bash

```bash
pkill -f "kubectl.*port-forward.*8080" || true
```

Recovery: rerun the launcher after the port is free, or use an alternate `BaseUrl` only if the target endpoint is explicitly prepared.

---

### Problem: LocalAI Service Is Not Reachable

Symptoms include failed smoke tests, Locust connection errors, or `connection refused`.

Verify service, endpoints, and port-forward.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig"
$Namespace = "localai-benchmark"

kubectl --kubeconfig $Kubeconfig get svc localai-server -n $Namespace
kubectl --kubeconfig $Kubeconfig get endpoints localai-server -n $Namespace
kubectl --kubeconfig $Kubeconfig port-forward -n $Namespace svc/localai-server 8080:8080
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig"
NAMESPACE="localai-benchmark"

kubectl --kubeconfig "$KUBECONFIG_PATH" get svc localai-server -n "$NAMESPACE"
kubectl --kubeconfig "$KUBECONFIG_PATH" get endpoints localai-server -n "$NAMESPACE"
kubectl --kubeconfig "$KUBECONFIG_PATH" port-forward -n "$NAMESPACE" svc/localai-server 8080:8080
```

Run API checks in a second terminal while port-forwarding is active.

### Windows PowerShell

```powershell
Invoke-RestMethod -Uri "http://localhost:8080/v1/models" -Method Get -TimeoutSec 120
```

### Bash

```bash
curl -fsS --max-time 120 http://localhost:8080/v1/models
```

Recovery: if endpoints are empty, fix deployment readiness first. If port-forward fails, fix local port conflicts or service availability.

---

### Problem: Smoke Test Fails

Run the standalone smoke test only after preparing the endpoint.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\validation\smoke\Test-LocalAIWorkerMode.ps1 `
  -BaseUrl "http://localhost:8080" `
  -Model "llama-3.2-1b-instruct:q4_k_m" `
  -RequestTimeoutSeconds 120
```

### Bash

```bash
./scripts/validation/smoke/test-localai-worker-mode.sh \
  --base-url http://localhost:8080 \
  --model llama-3.2-1b-instruct:q4_k_m \
  --request-timeout-seconds 120
```

Recovery actions:

1. if `/v1/models` fails, inspect LocalAI server logs and model availability;
2. if `/v1/chat/completions` times out, inspect CPU, memory, pod logs, and model-loading time;
3. if timeout is expected under a stress scenario, preserve unsupported evidence through the main launcher instead of forcing a successful manual smoke test.

---

## Benchmark and Locust Issues

### Problem: Locust Is Not Available

Validate Locust through the active Python environment.

### Windows PowerShell

```powershell
python -m locust --version
```

### Bash

```bash
python3 -m locust --version || python -m locust --version
```

Recovery: reinstall repository requirements.

### Windows PowerShell

```powershell
python -m pip install -r .\requirements.txt
```

### Bash

```bash
python3 -m pip install -r ./requirements.txt || python -m pip install -r ./requirements.txt
```

---

### Problem: Locust Starts but Produces Failures

Inspect the generated CSV artifacts.

### Windows PowerShell

```powershell
Get-ChildItem .\results -Recurse -Filter "*_failures.csv" | Select-Object FullName, Length
Get-ChildItem .\results -Recurse -Filter "*_exceptions.csv" | Select-Object FullName, Length
Get-ChildItem .\results -Recurse -Filter "*_stats.csv" | Select-Object FullName, Length
```

### Bash

```bash
find ./results -type f \( -name '*_failures.csv' -o -name '*_exceptions.csv' -o -name '*_stats.csv' \) -print | sort
```

Inspect the first rows.

### Windows PowerShell

```powershell
Get-ChildItem .\results -Recurse -Filter "*_failures.csv" |
  Select-Object -First 1 |
  ForEach-Object { Get-Content $_.FullName -TotalCount 20 }
```

### Bash

```bash
first_failures_file="$(find ./results -type f -name '*_failures.csv' | sort | head -n 1)"
if [ -n "$first_failures_file" ]; then sed -n '1,20p' "$first_failures_file"; fi
```

Recovery actions:

1. verify that smoke validation passes before the benchmark phase;
2. verify the model name used by the benchmark profile;
3. inspect LocalAI logs for timeout or model errors;
4. preserve timeout-based unsupported evidence when generated by the main launcher under declared constraints.

---

### Problem: Measurement CSV Files Are Missing or Empty

Symptoms include diagnosis failure, reporting failure, or completion-gate failure because benchmark evidence is absent.

Search for benchmark CSV files.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles -Recurse -Filter "*_stats.csv" |
  Select-Object FullName, Length
```

### Bash

```bash
find ./results/experimental-cycles -type f -name '*_stats.csv' -printf '%p %s bytes\n' | sort
```

Recovery interpretation:

| Condition | Action |
|---|---|
| No CSV files exist for a measured scenario | Rerun the benchmark stage or full cycle. |
| Warm-up CSV exists but measurement CSV is missing | Inspect phase execution and Locust errors. |
| CSV exists but contains only failures | Treat as failed benchmark unless the scenario is explicitly unsupported. |
| Unsupported reports exist for the scenario | Preserve unsupported evidence and check completion-gate policy. |

---

## Minimal Observability Issues

### Problem: Minimal Observability Capture Fails

Validate the observability entry point and Kubernetes access.

### Windows PowerShell

```powershell
Test-Path .\scripts\observability\minimal\Start-MinimalObservability.ps1
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig"
kubectl --kubeconfig $Kubeconfig get nodes -o wide
kubectl --kubeconfig $Kubeconfig get pods -A -o wide
```

### Bash

```bash
test -f ./scripts/observability/minimal/start-minimal-observability.sh
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig"
kubectl --kubeconfig "$KUBECONFIG_PATH" get nodes -o wide
kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -A -o wide
```

Run a minimal observability dry run or capture for a known profile.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\observability\minimal\Start-MinimalObservability.ps1 `
  -ProfileConfig .\config\observability-minimal\profiles\MO_C1_PROVIDER_BACKED_BASELINE.json `
  -Kubeconfig .\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig `
  -Action capture `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/observability/minimal/start-minimal-observability.sh \
  --profile-config config/observability-minimal/profiles/MO_C1_PROVIDER_BACKED_BASELINE.json \
  --kubeconfig config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig \
  --action capture \
  --write-latest-aliases
```

Recovery: if Metrics API is missing but Kubernetes snapshots work, record the limitation and use metrics-warning policy only when appropriate.

---

## C7 Default-Scheduler Baseline Issues

### Problem: Default-Scheduler Manifest Validation Fails

C7 manifests must not contain hard pod placement controls.

### Windows PowerShell

```powershell
python .\scripts\validation\scheduler\validate-default-scheduler-manifests.py `
  --repo-root . `
  --scan-root .\infra\k8s\compositions\default-scheduler `
  --json
```

### Bash

```bash
python scripts/validation/scheduler/validate-default-scheduler-manifests.py \
  --repo-root . \
  --scan-root infra/k8s/compositions/default-scheduler \
  --json
```

If the validation fails, inspect the reported file and remove any occurrence of:

```text
spec.nodeName
hostname-specific nodeSelector
hostname-specific nodeAffinity
controlled placement overlay reference
```

Do not bypass the validator for official C7 evidence generation.

### Problem: Scheduler Decision Evidence Is Missing

C7 requires scheduler decision evidence for executed scenarios.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C7 -Recurse `
  -Filter "default-scheduler-decision-evidence.json" |
  Select-Object FullName
```

### Bash

```bash
find results/experimental-cycles/C7 -name "default-scheduler-decision-evidence.json" -print | sort
```

If no evidence exists, verify that the C7 campaign was not executed with scheduler capture skipped. For targeted recovery, capture the evidence manually after the workload is deployed.

### Windows PowerShell

```powershell
python .\scripts\observability\scheduler\capture-scheduler-decisions.py `
  --repo-root . `
  --scenario-config .\config\scenarios\default-scheduler\DS_2T_4N_L1_DIFFERENTIATED_M1M1_W2.json `
  --kubeconfig .\config\cluster-access\provider-backed\kubeconfig `
  --write-text-summary `
  --write-latest-aliases
```

### Bash

```bash
python scripts/observability/scheduler/capture-scheduler-decisions.py \
  --repo-root . \
  --scenario-config config/scenarios/default-scheduler/DS_2T_4N_L1_DIFFERENTIATED_M1M1_W2.json \
  --kubeconfig config/cluster-access/provider-backed/kubeconfig \
  --write-text-summary \
  --write-latest-aliases
```

Use the kubeconfig path generated by the active provider-backed variant.

### Problem: Only One Tenant Has Benchmark Artifacts

Multi-tenant scenarios must preserve tenant-scoped evidence.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C7\benchmark\default-scheduler -Recurse |
  Where-Object { $_.Name -match "tenant|summary|stats" } |
  Select-Object FullName, Length
```

### Bash

```bash
find results/experimental-cycles/C7/benchmark/default-scheduler \
  -type f \( -name "*tenant*" -o -name "*summary*" -o -name "*stats*" \) \
  | sort
```

If only the primary tenant is represented, verify that the scenario profile declares all tenant benchmark targets and that the multi-tenant Locust runner was used.

### Problem: Tenant ID and Namespace Are Confused

Tenant IDs and namespaces are related but distinct.

Use the following convention:

```text
tenant-a -> genai-tenant-a
tenant-b -> genai-tenant-b
tenant-c -> genai-tenant-c
```

Runtime artifacts should preserve both fields. A namespace value should not replace the logical tenant ID in rollout targets, smoke validation targets, scheduler evidence, benchmark outputs, diagnosis, or reporting.

### Problem: C7 Stress Scenario Is Not Schedulable

Three-tenant or mixed-model stress scenarios may exceed available capacity.

Do not manually add hard placement controls to make the scenario run. Preserve the scenario as unsupported when the evidence shows non-schedulability, resource exhaustion, model-loading failure, or rollout timeout caused by current infrastructure constraints.

---

## C8 Resource-Aware Scheduler Issues

### Problem: Resource-Aware Scheduler Manifest Validation Fails

C8 resource-aware scheduler manifests must not contain hard pod placement controls.

### Windows PowerShell

```powershell
python .\scripts\validation\scheduler\validate-default-scheduler-manifests.py `
  --repo-root . `
  --scan-root .\infra\k8s\compositions\resource-aware-scheduler `
  --require-render `
  --json
```

### Bash

```bash
python scripts/validation/scheduler/validate-default-scheduler-manifests.py \
  --repo-root . \
  --scan-root infra/k8s/compositions/resource-aware-scheduler \
  --require-render \
  --json
```

If validation fails, inspect the reported manifest and remove hard pod-placement controls. Default variants should omit `spec.schedulerName`; load-aware variants should use `scheduler-plugins-scheduler`.

### Problem: Management Node Validation Fails

C8 and C9 expect a management node label and an explicit management taint.

Expected values:

```text
label: nodepool=management
taint for C8: nodepool=management:NoSchedule
taint for C9: ManagementOnly=true:NoSchedule
```

Inspect the generated nodes.

### Windows PowerShell

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH get nodes --show-labels
kubectl --kubeconfig $KUBECONFIG_PATH describe nodes
```

### Bash

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" get nodes --show-labels
kubectl --kubeconfig "$KUBECONFIG_PATH" describe nodes
```

If labels or taints are missing, review the C8 provider-local YAML and confirm that `k3s.extra_server_args` and `k3s.taint_control_plane` preserve the C8 management-node policy.

### Problem: mon-agent Does Not Produce Required Annotations

C8 requires `cpu-usage` and `memory-usage` annotations on nodes and selected LocalAI deployments before controlled redeployment.

Inspect mon-agent evidence.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C8\observability\mon-agent -Recurse | Select-Object FullName
kubectl --kubeconfig $KUBECONFIG_PATH get namespaces --show-labels
kubectl --kubeconfig $KUBECONFIG_PATH get deployments -A --show-labels
```

### Bash

```bash
find ./results/experimental-cycles/C8/observability/mon-agent -maxdepth 5 -type f | sort
kubectl --kubeconfig "$KUBECONFIG_PATH" get namespaces --show-labels
kubectl --kubeconfig "$KUBECONFIG_PATH" get deployments -A --show-labels
```

Recovery: verify Prometheus availability, kube-state-metrics availability, namespace label `mon-agent/enabled=true`, and required `group` and `app` labels on LocalAI deployments and pod templates.

### Problem: Custom Scheduler Is Installed but Not Used

Load-aware C8 variants must use:

```text
scheduler-plugins-scheduler
```

Inspect pods and events.

### Windows PowerShell

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH get pods -A -o wide
kubectl --kubeconfig $KUBECONFIG_PATH get events -A --sort-by=.lastTimestamp
kubectl --kubeconfig $KUBECONFIG_PATH get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"/"}{.metadata.name}{" scheduler="}{.spec.schedulerName}{" node="}{.spec.nodeName}{"`n"}{end}'
```

### Bash

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -A -o wide
kubectl --kubeconfig "$KUBECONFIG_PATH" get events -A --sort-by=.lastTimestamp
kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"/"}{.metadata.name}{" scheduler="}{.spec.schedulerName}{" node="}{.spec.nodeName}{"\n"}{end}'
```

Recovery: verify the custom scheduler profile, scheduler namespace, Helm release status, scheduler logs, and the load-aware scenario's resource-aware scheduler policy.

### Problem: Controlled Redeployment Fails

C8 uses controlled redeployment so the configured scheduler can make a fresh placement decision after runtime telemetry is available.

Inspect rescheduling evidence.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C8\rescheduling -Recurse | Select-Object FullName
kubectl --kubeconfig $KUBECONFIG_PATH rollout status deployment/localai-server -n genai-tenant-a --timeout=600s
```

### Bash

```bash
find ./results/experimental-cycles/C8/rescheduling -maxdepth 5 -type f | sort
kubectl --kubeconfig "$KUBECONFIG_PATH" rollout status deployment/localai-server -n genai-tenant-a --timeout=600s
```

Recovery: inspect missing annotations, deployment readiness, image pull status, model loading, and scheduler events before rerunning the variant.

### Problem: Load-Aware Artifacts Are Labeled as Default-Scheduler Artifacts

C8 benchmark artifacts must preserve scheduler-aware metadata.

Inspect generated benchmark protocol and metric-set files for the affected variant.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C8\benchmark\resource-aware-scheduler -Recurse `
  -Include protocol.json,protocol.txt,metric-set.json,metric-set.txt |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C8/benchmark/resource-aware-scheduler \
  \( -name protocol.json -o -name protocol.txt -o -name metric-set.json -o -name metric-set.txt \) \
  -type f | sort
```

Recovery: rerun benchmark generation from the current resource-aware scheduler runtime configuration. Do not manually edit generated artifacts.

---

## C9 Network-Aware Scheduler Issues

### Problem: Network-Aware Manifest Validation Fails

C9 network-aware manifests must preserve scheduler-mode semantics, tenant labels, Istio routing compatibility, and the absence of hard pod-to-node placement controls.

### Windows PowerShell

```powershell
python .\scripts\validation\scheduler\validate-scheduler-mode-manifests.py `
  --repo-root . `
  --scan-root .\infra\k8s\compositions\network-aware-scheduler `
  --scenario-index .\config\scenarios\network-aware-scheduler\NETWORK_AWARE_SCHEDULER_SCENARIOS_INDEX.json `
  --require-render `
  --json
```

### Bash

```bash
python scripts/validation/scheduler/validate-scheduler-mode-manifests.py \
  --repo-root . \
  --scan-root infra/k8s/compositions/network-aware-scheduler \
  --scenario-index config/scenarios/network-aware-scheduler/NETWORK_AWARE_SCHEDULER_SCENARIOS_INDEX.json \
  --require-render \
  --json
```

Recovery: fix the reported composition or scenario file. Default variants must omit `spec.schedulerName`; load-aware and network-aware variants must use `scheduler-plugins-scheduler`; all LocalAI pods must expose plain `group`, `app`, and `role` labels.

### Problem: Istio Gateway Evidence Is Missing

C9 traffic must be gateway-routed. Missing Istio evidence makes gateway-to-master traffic annotations inconclusive.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse |
  Where-Object { $_.FullName -match 'istio' } |
  Select-Object FullName

kubectl --kubeconfig $KUBECONFIG_PATH get gateway,virtualservice -A
```

### Bash

```bash
find ./results/experimental-cycles/C9/variants -path '*istio*' -type f | sort
kubectl --kubeconfig "$KUBECONFIG_PATH" get gateway,virtualservice -A
```

Recovery: verify the provider add-on configuration, namespace sidecar injection label, Gateway and VirtualService manifests, and benchmark target URL resolution before rerunning the affected variant.

### Problem: Mentat or Network Annotation Evidence Is Missing

C9 network-aware scheduling requires internode network evidence and corresponding node annotations.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse |
  Where-Object { $_.FullName -match 'mentat|mon-agent' } |
  Select-Object FullName

kubectl --kubeconfig $KUBECONFIG_PATH get nodes -o yaml | Select-String 'network-latency|packet-loss|network-bandwidth'
```

### Bash

```bash
find ./results/experimental-cycles/C9/variants -path '*mentat*' -o -path '*mon-agent*' | sort
kubectl --kubeconfig "$KUBECONFIG_PATH" get nodes -o yaml | grep -E 'network-latency|packet-loss|network-bandwidth'
```

Recovery: verify the Mentat DaemonSet, Prometheus scraping, mon-agent configuration, tenant namespace labels, and the expected annotation contract before repeating telemetry priming.

### Problem: Gateway Traffic Key Is Not Resolved

If `GATEWAY_TRAFFIC_KEY` points to an annotation that is not produced, the network-aware plugin may score with missing or zero traffic evidence.

Inspect scheduler profile evidence and deployment annotations.

### Windows PowerShell

```powershell
Get-Content .\config\scheduler\profiles\CS_C9_LOCALAI_RESOURCE_NETWORK_AWARE_SECOND_SCHEDULER.json
kubectl --kubeconfig $KUBECONFIG_PATH get deployments -A -o yaml | Select-String 'gateway-traffic|rps\.|traffic\.'
```

### Bash

```bash
cat ./config/scheduler/profiles/CS_C9_LOCALAI_RESOURCE_NETWORK_AWARE_SECOND_SCHEDULER.json
kubectl --kubeconfig "$KUBECONFIG_PATH" get deployments -A -o yaml | grep -E 'gateway-traffic|rps\.|traffic\.'
```

Recovery: align the scheduler profile, mon-agent profile, and runtime annotation evidence. The configured gateway traffic key must correspond to a deployment annotation emitted for the LocalAI master workload.

### Problem: Network-Aware Scheduler Is Installed but the Plugin Is Not Active

Network-aware variants must use the second scheduler with both resource-aware and network-aware scoring enabled.

### Windows PowerShell

```powershell
kubectl --kubeconfig $KUBECONFIG_PATH get pods -A -o wide
kubectl --kubeconfig $KUBECONFIG_PATH logs -n scheduler-plugins -l app=scheduler-plugins-scheduler --tail=200
```

### Bash

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -A -o wide
kubectl --kubeconfig "$KUBECONFIG_PATH" logs -n scheduler-plugins -l app=scheduler-plugins-scheduler --tail=200
```

Recovery: validate the scheduler image, plugin configuration, profile name, rendered scheduler manifest, and scenario scheduler mode before rerunning the affected variant.

### Problem: Telemetry-Primed Rescheduling Fails

C9 uses telemetry-primed redeployment so the selected scheduler can make placement decisions after updated annotations are available.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse |
  Where-Object { $_.FullName -match 'telemetry-priming|rescheduling' } |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C9/variants \
  \( -path '*telemetry-priming*' -o -path '*rescheduling*' \) \
  -type f | sort
```

Recovery: inspect annotation freshness, rollout events, image pull status, model loading, and scheduler events. If the failure reason contains `annotation_controlled_latency_matrix_mismatch`, inspect the rescheduling manifest and snapshots under the affected variant's `network-aware-scheduler/rescheduling/` directory and verify that the controlled annotation window was able to converge the expected `network-latency.<node>` matrix before redeployment. Do not manually patch pod placement or generated artifacts to make a variant pass.

---

### Problem: cluster-lens Placement Evidence Is Missing

C9 can execute benchmark workloads while still missing placement evidence if cluster-lens is not installed, the service is unreachable, the capture policy was disabled, or the collector could not access the Kubernetes API.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c9-1cp-4w-8c16g\kubeconfig"

kubectl --kubeconfig $Kubeconfig -n observability get pods,svc | Select-String cluster-lens
Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse -Filter cluster-lens-capture-manifest.json |
  Select-Object FullName
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c9-1cp-4w-8c16g/kubeconfig"

kubectl --kubeconfig "$KUBECONFIG_PATH" -n observability get pods,svc | grep cluster-lens
find ./results/experimental-cycles/C9/variants -name cluster-lens-capture-manifest.json -type f | sort
```

If the manifests are missing but benchmark artifacts exist, regenerate C9 after confirming that the provider C9 YAML enables `cluster_lens` and that `clusterLensCaptureStagePolicy` is not disabled.

If the stage-specific artifacts exist but the primary root artifacts are missing, inspect whether primary-stage promotion ran successfully. The root should contain `cluster-lens-placement-summary.json`, `cluster-lens-placement-signature.csv`, `cluster-lens-capture-manifest.json`, and `cluster-lens-primary-stage-manifest.json`.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse -Filter cluster-lens-primary-stage-manifest.json |
  Select-Object FullName, Length

Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse -Filter cluster-lens-placement-summary.json |
  Where-Object { $_.FullName -notmatch '\\stages\\' } |
  Select-Object FullName, Length
```

### Bash

```bash
find ./results/experimental-cycles/C9/variants -name cluster-lens-primary-stage-manifest.json -type f | sort
find ./results/experimental-cycles/C9/variants -name cluster-lens-placement-summary.json -type f | grep -v '/stages/' | sort
```

Recovery: keep the stage-specific artifacts for audit, but rerun the affected C9 variant or rerun the reporting workflow only after confirming that primary placement evidence is available or that the configured fallback stage is explicitly acceptable for the affected scheduler mode.

---

## Post-Processing Issues

### Problem: Technical Diagnosis Fails

Validate diagnosis profiles and benchmark evidence.

### Windows PowerShell

```powershell
python -m json.tool .\config\technical-diagnosis\profiles\TD_C1_PROVIDER_BACKED_BASELINE.json | Out-Null
Get-ChildItem .\results\experimental-cycles\C1 -Recurse | Select-Object FullName, Length | Select-Object -First 40
```

### Bash

```bash
python3 -m json.tool ./config/technical-diagnosis/profiles/TD_C1_PROVIDER_BACKED_BASELINE.json >/dev/null
find ./results/experimental-cycles/C1 -maxdepth 4 -type f -print | sort | head -40
```

Regenerate diagnosis.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-TechnicalDiagnosis.ps1 `
  -ProfileConfig .\config\technical-diagnosis\profiles\TD_C1_PROVIDER_BACKED_BASELINE.json `
  -Family all
```

### Bash

```bash
./scripts/load/post/start-technical-diagnosis.sh \
  --profile-config config/technical-diagnosis/profiles/TD_C1_PROVIDER_BACKED_BASELINE.json \
  --family all
```

Recovery: if diagnosis still fails, inspect whether benchmark or unsupported-scenario evidence exists for the expected cycle.

---

### Problem: Reporting Fails or Charts Are Missing

Validate reporting profiles and regenerate the report.

### Windows PowerShell

```powershell
python -m json.tool .\config\reporting\profiles\RP_C1_PROVIDER_BACKED_BASELINE.json | Out-Null
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-Reporting.ps1 `
  -ProfileConfig .\config\reporting\profiles\RP_C1_PROVIDER_BACKED_BASELINE.json
```

### Bash

```bash
python3 -m json.tool ./config/reporting/profiles/RP_C1_PROVIDER_BACKED_BASELINE.json >/dev/null
./scripts/load/post/start-reporting.sh \
  --profile-config config/reporting/profiles/RP_C1_PROVIDER_BACKED_BASELINE.json
```

Validate expected outputs.

### Windows PowerShell

```powershell
Test-Path .\results\experimental-cycles\C1\reporting\report.md
Test-Path .\results\experimental-cycles\C1\reporting\index.html
Test-Path .\results\experimental-cycles\C1\reporting\reporting-manifest.json
```

### Bash

```bash
test -f ./results/experimental-cycles/C1/reporting/report.md
test -f ./results/experimental-cycles/C1/reporting/index.html
test -f ./results/experimental-cycles/C1/reporting/reporting-manifest.json
```

Recovery: generate diagnosis first if reporting expects diagnosis context and it is missing.

---

### Problem: Global Reporting Site Is Missing or Stale

Regenerate the reporting site.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-ReportingSite.ps1 `
  -SiteConfig .\config\reporting\site\REPORTING_SITE.json
```

### Bash

```bash
./scripts/load/post/start-reporting-site.sh \
  --site-config config/reporting/site/REPORTING_SITE.json
```

Validate outputs.

### Windows PowerShell

```powershell
Test-Path .\results\reporting\index.html
Test-Path .\results\reporting\reporting-site-manifest.json
```

### Bash

```bash
test -f ./results/reporting/index.html
test -f ./results/reporting/reporting-site-manifest.json
```

---

### Problem: Completion Gate Fails

Inspect the completion-gate summary and the required upstream artifacts.

### Windows PowerShell

```powershell
Get-Content .\results\experimental-cycles\C1\completion-gate\latest-completion-gate-summary.txt -ErrorAction SilentlyContinue
Get-ChildItem .\results\experimental-cycles\C1\diagnosis -ErrorAction SilentlyContinue
Get-ChildItem .\results\experimental-cycles\C1\reporting -ErrorAction SilentlyContinue
```

### Bash

```bash
cat ./results/experimental-cycles/C1/completion-gate/latest-completion-gate-summary.txt 2>/dev/null || true
find ./results/experimental-cycles/C1/diagnosis -maxdepth 1 -type f -print 2>/dev/null || true
find ./results/experimental-cycles/C1/reporting -maxdepth 1 -type f -print 2>/dev/null || true
```

Regenerate the completion gate.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-CompletionGate.ps1 `
  -ProfileConfig .\config\completion-gate\profiles\CG_C1_PROVIDER_BACKED_BASELINE.json
```

### Bash

```bash
./scripts/load/post/start-completion-gate.sh \
  --profile-config config/completion-gate/profiles/CG_C1_PROVIDER_BACKED_BASELINE.json
```

Recovery interpretation:

| Gate failure | Likely recovery |
|---|---|
| Missing benchmark evidence | Rerun benchmark or campaign. |
| Missing diagnosis | Regenerate technical diagnosis. |
| Missing reporting | Regenerate reporting. |
| Unsupported scenarios not accepted | Inspect the completion-gate profile and scenario evidence. |
| Malformed manifest | Regenerate the corresponding upstream stage. |

---

### Problem: Freeze Fails

Freeze requires accepted completion status and the expected artifact set.

Inspect completion and freeze outputs.

### Windows PowerShell

```powershell
Get-Content .\results\experimental-cycles\C1\completion-gate\latest-completion-gate-summary.txt -ErrorAction SilentlyContinue
Get-ChildItem .\results\experimental-cycles\C1\freeze -ErrorAction SilentlyContinue
```

### Bash

```bash
cat ./results/experimental-cycles/C1/completion-gate/latest-completion-gate-summary.txt 2>/dev/null || true
find ./results/experimental-cycles/C1/freeze -maxdepth 1 -type f -print 2>/dev/null || true
```

Regenerate freeze after completion-gate evaluation.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-FreezeExperimentalCycle.ps1 `
  -ProfileConfig .\config\freeze\profiles\FR_C1_PROVIDER_BACKED_BASELINE.json
```

### Bash

```bash
./scripts/load/post/start-freeze-experimental-cycle.sh \
  --profile-config config/freeze/profiles/FR_C1_PROVIDER_BACKED_BASELINE.json
```

Use forced freeze only for controlled recovery when the target evidence package has been reviewed.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-FreezeExperimentalCycle.ps1 `
  -ProfileConfig .\config\freeze\profiles\FR_C1_PROVIDER_BACKED_BASELINE.json `
  -ForceFreeze
```

### Bash

```bash
./scripts/load/post/start-freeze-experimental-cycle.sh \
  --profile-config config/freeze/profiles/FR_C1_PROVIDER_BACKED_BASELINE.json \
  --force-freeze
```

---

## Campaign-Level Recovery

### Problem: A C2-C6 Campaign Stops at the First Failed Variant

For comparative campaigns, continue-on-failure is useful when unsupported variants are expected and should not prevent later variants from being evaluated.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C4.json `
  -ToolPath proxmox-k3s `
  -BaselineReplicas A,B,C `
  -ContinueOnFailure `
  -AllowMetricsWarning `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config config/experimental-cycles/C4.json \
  --tool-path proxmox-k3s \
  --baseline-replicas A,B,C \
  --continue-on-failure \
  --allow-metrics-warning \
  --write-latest-aliases
```

Recovery: use `continue-on-failure` to preserve comparative evidence, not to hide invalid local configuration or provider errors.

---

### Problem: Unsupported Scenario Evidence Is Missing

Unsupported scenarios should produce explicit unsupported reports or variant manifests. Search for them.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C4 -Recurse |
  Where-Object { $_.Name -match "unsupported|variant|manifest|summary" } |
  Select-Object FullName, Length
```

### Bash

```bash
find ./results/experimental-cycles/C4 -type f | grep -Ei 'unsupported|variant|manifest|summary' | sort
```

Recovery actions:

1. inspect the campaign execution manifest;
2. inspect variant-level logs and deployment manifests;
3. rerun the campaign with `continue-on-failure` if the campaign stopped before unsupported evidence was written;
4. do not delete unsupported artifacts before diagnosis, reporting, and completion gate have consumed them.

---

### Problem: Latency Injection May Have Left Cluster State Modified

Inspect or reset latency configuration for the target cycle and profile.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\latency\Apply-LatencyProfile.ps1 `
  -RepoRoot . `
  -CycleConfig .\config\experimental-cycles\C5.json `
  -ProfileConfig .\config\latency\profiles\L0_NONE.json `
  -Kubeconfig .\config\cluster-access\generated\proxmox-k3s\c5-1cp-4w-8c16g\kubeconfig `
  -OutputRoot .\results\experimental-cycles\C5\latency `
  -Action reset `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/latency/apply-latency-profile.sh \
  --repo-root . \
  --cycle-config config/experimental-cycles/C5.json \
  --profile-config config/latency/profiles/L0_NONE.json \
  --kubeconfig config/cluster-access/generated/proxmox-k3s/c5-1cp-4w-8c16g/kubeconfig \
  --output-root results/experimental-cycles/C5/latency \
  --action reset \
  --write-latest-aliases
```

Recovery: reset latency state before running unrelated cycles on the same retained provider-backed cluster.

---

### Problem: Multi-Tenant Namespaces or Workloads Remain After a Failed C6 Run

Inspect tenant namespaces and workloads.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c6-1cp-4w-8c16g\kubeconfig"

kubectl --kubeconfig $Kubeconfig get namespaces
kubectl --kubeconfig $Kubeconfig get pods -n genai-tenant-a -o wide
kubectl --kubeconfig $Kubeconfig get pods -n genai-tenant-b -o wide
kubectl --kubeconfig $Kubeconfig get pods -n localai-benchmark -o wide
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c6-1cp-4w-8c16g/kubeconfig"

kubectl --kubeconfig "$KUBECONFIG_PATH" get namespaces
kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -n genai-tenant-a -o wide
kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -n genai-tenant-b -o wide
kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -n localai-benchmark -o wide
```

Delete tenant namespaces only when you are sure they belong to the failed test run.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c6-1cp-4w-8c16g\kubeconfig"
kubectl --kubeconfig $Kubeconfig delete namespace genai-tenant-a genai-tenant-b --ignore-not-found
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c6-1cp-4w-8c16g/kubeconfig"
kubectl --kubeconfig "$KUBECONFIG_PATH" delete namespace genai-tenant-a genai-tenant-b --ignore-not-found
```

Recovery: after cleanup, rerun the C6 campaign from the campaign launcher so that runtime configuration and artifacts remain consistent.

---

## Results Cleanup and Regeneration Recovery

### Problem: `results/` Was Deleted but Required Local Files Were Also Removed

The cleanup procedure must remove generated artifacts only. If kubeconfigs or local provider YAML files were removed, restore them before rerunning cycles.

Validate local files.

### Windows PowerShell

```powershell
$RequiredLocalFiles = @(
  ".\config\cluster-access\fixed-cluster\kubeconfig",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml"
)

foreach ($File in $RequiredLocalFiles) {
  if (-not (Test-Path $File)) {
    Write-Warning "Missing local file: $File"
  }
}
```

### Bash

```bash
required_local_files=(
  "./config/cluster-access/fixed-cluster/kubeconfig"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml"
)

for file in "${required_local_files[@]}"; do
  test -f "$file" || echo "Missing local file: $file" >&2
done
```

Recovery: restore missing local files from authorized local sources or recreate them from reviewed examples and real environment values.

---

### Problem: Full Regeneration Fails Midway

Do not immediately delete all regenerated evidence. First identify the failed cycle.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles -Directory -ErrorAction SilentlyContinue |
  Select-Object Name, FullName

Get-ChildItem .\results\experimental-cycles -Recurse -Filter "latest-*manifest.json" -ErrorAction SilentlyContinue |
  Select-Object FullName, Length
```

### Bash

```bash
find ./results/experimental-cycles -maxdepth 1 -type d -print 2>/dev/null | sort
find ./results/experimental-cycles -type f -name 'latest-*manifest.json' -print 2>/dev/null | sort
```

Recovery actions:

1. keep successful earlier cycles unless their source configuration changed;
2. rerun the failed cycle or campaign only;
3. regenerate global reporting site after the failed cycle succeeds;
4. rerun final artifact validation.

---

## Safe Cleanup Commands

### Clean the Application Namespace on the Active Cluster

Use this only for controlled application cleanup. It does not delete provider-backed infrastructure.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig"
$Namespace = "localai-benchmark"

kubectl --kubeconfig $Kubeconfig delete namespace $Namespace --ignore-not-found
kubectl --kubeconfig $Kubeconfig apply -k .\infra\k8s\compositions\foundation\namespace
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig"
NAMESPACE="localai-benchmark"

kubectl --kubeconfig "$KUBECONFIG_PATH" delete namespace "$NAMESPACE" --ignore-not-found
kubectl --kubeconfig "$KUBECONFIG_PATH" apply -k ./infra/k8s/compositions/foundation/namespace
```

### Delete a Provider-Backed Cluster

Use only when cluster deletion is intended.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\infrastructure\provision\Start-ProviderBackedProvisioning.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -Action destroy `
  -ToolPath proxmox-k3s `
  -ConfirmDelete
```

### Bash

```bash
./scripts/infrastructure/provision/start-provider-backed-provisioning.sh \
  --cycle-config config/experimental-cycles/C1.json \
  --action destroy \
  --tool-path proxmox-k3s \
  --confirm-delete
```

### Clean Generated Results Only

### Windows PowerShell

```powershell
if (-not (Test-Path .\results)) {
  New-Item -ItemType Directory -Path .\results | Out-Null
}

Get-ChildItem .\results -Force |
  Where-Object { $_.Name -ne ".gitkeep" } |
  Remove-Item -Recurse -Force

if (-not (Test-Path .\results\.gitkeep)) {
  New-Item -ItemType File -Path .\results\.gitkeep | Out-Null
}
```

### Bash

```bash
mkdir -p ./results
find ./results -mindepth 1 -maxdepth 1 ! -name ".gitkeep" -exec rm -rf {} +
touch ./results/.gitkeep
```

---

## Final Health Check After Recovery

After recovery, validate the repository, cluster, artifacts, and post-processing state.

### Windows PowerShell

```powershell
# Repository structure
Test-Path .\config
Test-Path .\infra
Test-Path .\scripts
Test-Path .\load-tests

# JSON validity
Get-ChildItem .\config -Recurse -Filter *.json | ForEach-Object { python -m json.tool $_.FullName > $null }

# Artifact roots
Get-ChildItem .\results\experimental-cycles -Directory -ErrorAction SilentlyContinue | Select-Object Name

# Reporting site
Test-Path .\results\reporting\index.html
```

### Bash

```bash
# Repository structure
test -d ./config
test -d ./infra
test -d ./scripts
test -d ./load-tests

# JSON validity
find ./config -type f -name '*.json' -print0 |
while IFS= read -r -d '' file; do
  python3 -m json.tool "$file" >/dev/null || exit 1
done

# Artifact roots
find ./results/experimental-cycles -maxdepth 1 -type d -print 2>/dev/null | sort

# Reporting site
test -f ./results/reporting/index.html
```

A recovered execution state is acceptable when:

1. source configuration validates;
2. required kubeconfigs and provider-local files exist locally;
3. cluster-facing commands use explicit kubeconfig paths;
4. failed scenarios are either rerun successfully or preserved as unsupported evidence;
5. diagnosis, reporting, completion gate, and freeze artifacts exist for completed cycles;
6. the global reporting site can be regenerated from cycle-scoped reports.

---

## Escalation Package

If a failure cannot be recovered locally, prepare an escalation package with enough evidence to reproduce the issue.

Include:

```text
results/recovery/<timestamp>/
results/experimental-cycles/<cycle>/execution/
results/experimental-cycles/<cycle>/infrastructure/
results/experimental-cycles/<cycle>/application/
results/experimental-cycles/<cycle>/benchmark/
results/experimental-cycles/<cycle>/diagnosis/
results/experimental-cycles/<cycle>/reporting/
results/experimental-cycles/<cycle>/completion-gate/
```

Do not include real kubeconfig files, provider tokens, `.local.yaml` files containing secrets, private keys, or private infrastructure credentials.

Create a sanitized archive manually after reviewing its contents.

### Windows PowerShell

```powershell
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Archive = "..\benchmark-recovery-package-$Stamp.zip"
Compress-Archive `
  -Path .\results\recovery\*, .\results\experimental-cycles\* `
  -DestinationPath $Archive `
  -Force
```

### Bash

```bash
STAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE="../benchmark-recovery-package-$STAMP.tar.gz"
tar -czf "$ARCHIVE" ./results/recovery ./results/experimental-cycles
```

Before sharing, inspect the archive and remove any accidental sensitive files.

### Windows PowerShell

```powershell
Get-ChildItem ..\benchmark-recovery-package-*.zip | Select-Object Name, Length, LastWriteTime
```

### Bash

```bash
ls -lh ../benchmark-recovery-package-*.tar.gz
```
