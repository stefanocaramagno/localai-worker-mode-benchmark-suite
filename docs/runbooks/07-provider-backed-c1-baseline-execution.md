# Provider-Backed C1 Baseline Execution

## Purpose

This runbook describes how to execute and regenerate the complete `C1` provider-backed baseline cycle.

`C1` is the first provider-backed baseline execution track of the LocalAI worker-mode benchmark suite. Unlike `C0`, it does not assume that the target Kubernetes cluster already exists as a fixed external environment. Instead, it uses the `proxmox-k3s` provider workflow to materialize or reuse a K3s cluster from the declared infrastructure profile before deploying the LocalAI worker-mode topology and running the baseline benchmark.

The objective of this runbook is to regenerate the full `C1` evidence set, including:

- provider-backed infrastructure resolution;
- `proxmox-k3s` cluster provisioning or reuse;
- generated kubeconfig validation;
- provider-backed cluster validation;
- placement-profile resolution;
- LocalAI worker-mode deployment;
- LocalAI smoke validation;
- minimal Kubernetes and application observability capture;
- provider-backed baseline benchmark replicas;
- technical diagnosis;
- reporting;
- completion-gate evaluation;
- freeze snapshot.

`C1` must remain separate from the historical fixed-cluster execution track `C0` and from the comparative provider-backed campaigns `C2` through `C6`, the default-scheduler baseline `C7`, the resource-aware scheduler campaign `C8`, and the network-aware scheduler campaign `C9`. It is the provider-backed reference baseline used to validate the end-to-end execution path before running broader comparative campaigns.

---

## Repository Root Assumption

All commands in this runbook must be executed from the repository root:

```text
localai-worker-mode-benchmark-suite/
```

### Windows PowerShell

```powershell
Set-Location C:\Path\To\localai-worker-mode-benchmark-suite
```

### Bash

```bash
cd /path/to/localai-worker-mode-benchmark-suite
```

---

## C1 Execution Model

`C1` follows this execution model:

```text
cycle profile
→ infrastructure profile
→ provider binding
→ local provider YAML
→ proxmox-k3s provisioning or reuse
→ generated kubeconfig
→ cluster validation
→ placement-profile resolution
→ LocalAI deployment
→ smoke validation
→ minimal observability
→ baseline benchmark replicas
→ technical diagnosis
→ reporting
→ completion gate
→ freeze
```

The provider-backed baseline is intentionally narrow. It validates the full provisioning-to-benchmark path while keeping the application-level workload shape stable.

---

## Canonical C1 Inputs

The following inputs define the C1 provider-backed baseline execution track.

| Input | Canonical value |
|---|---|
| Cycle profile | `config/experimental-cycles/C1.json` |
| Baseline profile | `config/scenarios/baseline/B1.json` |
| Infrastructure profile | `config/infrastructure/profiles/INFRA_C1_1CP_2W_8C16G.json` |
| Provider binding | `config/infrastructure/providers/proxmox-k3s/bindings/BINDING_INFRA_C1_1CP_2W_8C16G_PROXMOX_K3S.json` |
| Review-only provider example | `config/infrastructure/providers/proxmox-k3s/examples/cluster.c1-1cp-2w-8c16g.example.yaml` |
| Local provider config | `config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml` |
| Generated kubeconfig | `config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig` |
| Namespace | `localai-benchmark` |
| Provider lifecycle mode | `reuse` |
| Provider-backed baseline ID | `B1` |
| Baseline model | `llama-3.2-1b-instruct:q4_k_m` |
| Worker count | `2` |
| Placement profile | `config/placement/profiles/PL_COLOCATED.json` |
| Workload profile | `WL2`, two users, spawn rate `1`, runtime `2m` |
| Precheck profile | `config/precheck/profiles/TC_C1_PROVIDER_BACKED_BASELINE.json` |
| Cluster validation profile | `config/cluster-validation/profiles/CV_C1_PROVIDER_BACKED_BASELINE.json` |
| Application deployment profile | `config/application-deployment/profiles/AD_C1_PROVIDER_BACKED_BASELINE.json` |
| Minimal observability profile | `config/observability-minimal/profiles/MO_C1_PROVIDER_BACKED_BASELINE.json` |
| Technical diagnosis profile | `config/technical-diagnosis/profiles/TD_C1_PROVIDER_BACKED_BASELINE.json` |
| Reporting profile | `config/reporting/profiles/RP_C1_PROVIDER_BACKED_BASELINE.json` |
| Completion-gate profile | `config/completion-gate/profiles/CG_C1_PROVIDER_BACKED_BASELINE.json` |
| Freeze profile | `config/freeze/profiles/FR_C1_PROVIDER_BACKED_BASELINE.json` |

---

## C1 Output Roots

A complete C1 regeneration writes artifacts under the following roots.

| Artifact family | Output root |
|---|---|
| Cycle execution manifest | `results/experimental-cycles/C1/execution` |
| Provisioning evidence | `results/experimental-cycles/C1/infrastructure/provisioning` |
| Cluster validation evidence | `results/experimental-cycles/C1/infrastructure/validation` |
| Placement resolution evidence | `results/experimental-cycles/C1/placement` |
| Application deployment evidence | `results/experimental-cycles/C1/application/deployment` |
| Minimal observability evidence | `results/experimental-cycles/C1/observability/minimal` |
| Baseline benchmark evidence | `results/experimental-cycles/C1/benchmark/baseline` |
| Technical diagnosis | `results/experimental-cycles/C1/diagnosis` |
| Reporting | `results/experimental-cycles/C1/reporting` |
| Completion gate | `results/experimental-cycles/C1/completion-gate` |
| Freeze manifest and lock | `results/experimental-cycles/C1/freeze` |
| Frozen artifact snapshot | `results/experimental-cycles/C1/artifacts` |

---

## Execution Safety Rules

Before running C1, observe the following rules.

1. `C1` must use the provider-backed execution path, not the fixed-cluster C0 workflow.
2. The local provider YAML must be reviewed before a real provisioning command is executed.
3. The review-only example YAML must not be used as a real provider config unless it has been copied, adapted, and stored as the local provider config.
4. The generated kubeconfig must be treated as local access material and must not be committed.
5. The `C1` lifecycle mode is `reuse`; therefore, the provider-backed cluster is retained by default after the cycle.
6. Provider delete operations must require explicit confirmation.
7. Do not mix `C1` artifacts with `C0` or `C2`–`C6` artifact roots.
8. The benchmark should be considered complete only after diagnosis, reporting, completion gate, and freeze have been generated.
9. Use `--continue-on-failure` or `-ContinueOnFailure` only for controlled diagnosis of partial failures. It is not the standard C1 execution path.
10. Use Metrics API warning bypass flags only when the cluster is otherwise healthy and the warning is explicitly considered non-blocking.

---

## Step 1 — Verify Required Files

Validate that the required C1 profiles, provider binding, local provider config, execution scripts, and analysis scripts are present.

### Windows PowerShell

```powershell
$RequiredPaths = @(
  ".\config\experimental-cycles\C1.json",
  ".\config\scenarios\baseline\B1.json",
  ".\config\infrastructure\profiles\INFRA_C1_1CP_2W_8C16G.json",
  ".\config\infrastructure\providers\proxmox-k3s\bindings\BINDING_INFRA_C1_1CP_2W_8C16G_PROXMOX_K3S.json",
  ".\config\infrastructure\providers\proxmox-k3s\examples\cluster.c1-1cp-2w-8c16g.example.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml",
  ".\config\provisioning\profiles\PI_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\provisioning-validation\profiles\PV_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\cluster-validation\profiles\CV_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\application-deployment\profiles\AD_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\placement\profiles\PL_COLOCATED.json",
  ".\config\observability-minimal\profiles\MO_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\technical-diagnosis\profiles\TD_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\reporting\profiles\RP_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\completion-gate\profiles\CG_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\freeze\profiles\FR_C1_PROVIDER_BACKED_BASELINE.json",
  ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1",
  ".\scripts\experimental-cycles\start-experimental-cycle.sh",
  ".\scripts\experimental-cycles\run-provider-backed-cycle.py",
  ".\scripts\infrastructure\provision\run-provider-backed-provisioning.py",
  ".\scripts\infrastructure\validation\run-provider-backed-cluster-validation.py",
  ".\scripts\application\deployment\run-provider-backed-localai-deployment.py",
  ".\scripts\analysis\generate-technical-diagnosis.py",
  ".\scripts\analysis\generate-reporting.py",
  ".\scripts\analysis\evaluate-completion-gate.py",
  ".\scripts\analysis\freeze-experimental-cycle.py"
)

$RequiredPaths | ForEach-Object {
  if (-not (Test-Path $_)) {
    throw "Missing required C1 file or directory: $_"
  }
}
```

### Bash

```bash
required_paths=(
  "./config/experimental-cycles/C1.json"
  "./config/scenarios/baseline/B1.json"
  "./config/infrastructure/profiles/INFRA_C1_1CP_2W_8C16G.json"
  "./config/infrastructure/providers/proxmox-k3s/bindings/BINDING_INFRA_C1_1CP_2W_8C16G_PROXMOX_K3S.json"
  "./config/infrastructure/providers/proxmox-k3s/examples/cluster.c1-1cp-2w-8c16g.example.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml"
  "./config/provisioning/profiles/PI_C1_PROVIDER_BACKED_BASELINE.json"
  "./config/provisioning-validation/profiles/PV_C1_PROVIDER_BACKED_BASELINE.json"
  "./config/cluster-validation/profiles/CV_C1_PROVIDER_BACKED_BASELINE.json"
  "./config/application-deployment/profiles/AD_C1_PROVIDER_BACKED_BASELINE.json"
  "./config/placement/profiles/PL_COLOCATED.json"
  "./config/observability-minimal/profiles/MO_C1_PROVIDER_BACKED_BASELINE.json"
  "./config/technical-diagnosis/profiles/TD_C1_PROVIDER_BACKED_BASELINE.json"
  "./config/reporting/profiles/RP_C1_PROVIDER_BACKED_BASELINE.json"
  "./config/completion-gate/profiles/CG_C1_PROVIDER_BACKED_BASELINE.json"
  "./config/freeze/profiles/FR_C1_PROVIDER_BACKED_BASELINE.json"
  "./scripts/experimental-cycles/Start-ExperimentalCycle.ps1"
  "./scripts/experimental-cycles/start-experimental-cycle.sh"
  "./scripts/experimental-cycles/run-provider-backed-cycle.py"
  "./scripts/infrastructure/provision/run-provider-backed-provisioning.py"
  "./scripts/infrastructure/validation/run-provider-backed-cluster-validation.py"
  "./scripts/application/deployment/run-provider-backed-localai-deployment.py"
  "./scripts/analysis/generate-technical-diagnosis.py"
  "./scripts/analysis/generate-reporting.py"
  "./scripts/analysis/evaluate-completion-gate.py"
  "./scripts/analysis/freeze-experimental-cycle.py"
)

for path in "${required_paths[@]}"; do
  test -e "$path" || { echo "Missing required C1 file or directory: $path" >&2; exit 1; }
done
```

---

## Step 2 — Define Reusable Runtime Variables

Define the C1 variables used by the remaining commands.

### Windows PowerShell

```powershell
$CycleConfig = ".\config\experimental-cycles\C1.json"
$BaselineConfig = ".\config\scenarios\baseline\B1.json"
$ProviderConfig = ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml"
$ToolPath = "proxmox-k3s"
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig"
$Namespace = "localai-benchmark"
$BaseUrl = "http://localhost:8080"
$RunId = "C1_regeneration"
$PrecheckProfile = ".\config\precheck\profiles\TC_C1_PROVIDER_BACKED_BASELINE.json"
$DiagnosisProfile = ".\config\technical-diagnosis\profiles\TD_C1_PROVIDER_BACKED_BASELINE.json"
$ReportingProfile = ".\config\reporting\profiles\RP_C1_PROVIDER_BACKED_BASELINE.json"
$CompletionGateProfile = ".\config\completion-gate\profiles\CG_C1_PROVIDER_BACKED_BASELINE.json"
$FreezeProfile = ".\config\freeze\profiles\FR_C1_PROVIDER_BACKED_BASELINE.json"
```

### Bash

```bash
CYCLE_CONFIG="./config/experimental-cycles/C1.json"
BASELINE_CONFIG="./config/scenarios/baseline/B1.json"
PROVIDER_CONFIG="./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml"
TOOL_PATH="proxmox-k3s"
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig"
NAMESPACE="localai-benchmark"
BASE_URL="http://localhost:8080"
RUN_ID="C1_regeneration"
PRECHECK_PROFILE="./config/precheck/profiles/TC_C1_PROVIDER_BACKED_BASELINE.json"
DIAGNOSIS_PROFILE="./config/technical-diagnosis/profiles/TD_C1_PROVIDER_BACKED_BASELINE.json"
REPORTING_PROFILE="./config/reporting/profiles/RP_C1_PROVIDER_BACKED_BASELINE.json"
COMPLETION_GATE_PROFILE="./config/completion-gate/profiles/CG_C1_PROVIDER_BACKED_BASELINE.json"
FREEZE_PROFILE="./config/freeze/profiles/FR_C1_PROVIDER_BACKED_BASELINE.json"
```

If `proxmox-k3s` is not available through `PATH`, set `$ToolPath` or `TOOL_PATH` to the executable path.

---

## Step 3 — Validate JSON Configuration Syntax

Validate the JSON profiles used by C1 before executing runtime operations.

### Windows PowerShell

```powershell
$JsonProfiles = @(
  $CycleConfig,
  $BaselineConfig,
  ".\config\infrastructure\profiles\INFRA_C1_1CP_2W_8C16G.json",
  ".\config\infrastructure\providers\proxmox-k3s\bindings\BINDING_INFRA_C1_1CP_2W_8C16G_PROXMOX_K3S.json",
  ".\config\provisioning\profiles\PI_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\provisioning-validation\profiles\PV_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\cluster-validation\profiles\CV_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\application-deployment\profiles\AD_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\placement\profiles\PL_COLOCATED.json",
  ".\config\observability-minimal\profiles\MO_C1_PROVIDER_BACKED_BASELINE.json",
  $DiagnosisProfile,
  $ReportingProfile,
  $CompletionGateProfile,
  $FreezeProfile
)

$JsonProfiles | ForEach-Object {
  python -m json.tool $_ > $null
}
```

### Bash

```bash
json_profiles=(
  "$CYCLE_CONFIG"
  "$BASELINE_CONFIG"
  "./config/infrastructure/profiles/INFRA_C1_1CP_2W_8C16G.json"
  "./config/infrastructure/providers/proxmox-k3s/bindings/BINDING_INFRA_C1_1CP_2W_8C16G_PROXMOX_K3S.json"
  "./config/provisioning/profiles/PI_C1_PROVIDER_BACKED_BASELINE.json"
  "./config/provisioning-validation/profiles/PV_C1_PROVIDER_BACKED_BASELINE.json"
  "./config/cluster-validation/profiles/CV_C1_PROVIDER_BACKED_BASELINE.json"
  "./config/application-deployment/profiles/AD_C1_PROVIDER_BACKED_BASELINE.json"
  "./config/placement/profiles/PL_COLOCATED.json"
  "./config/observability-minimal/profiles/MO_C1_PROVIDER_BACKED_BASELINE.json"
  "$DIAGNOSIS_PROFILE"
  "$REPORTING_PROFILE"
  "$COMPLETION_GATE_PROFILE"
  "$FREEZE_PROFILE"
)

for profile in "${json_profiles[@]}"; do
  python -m json.tool "$profile" >/dev/null
done
```

---

## Step 4 — Review the Local Provider Configuration

Inspect the local provider YAML before executing real provisioning.

### Windows PowerShell

```powershell
Get-Content $ProviderConfig
```

### Bash

```bash
cat "$PROVIDER_CONFIG"
```

Review at least the following values:

- cluster name;
- VM identifiers or VMID allocation range;
- Proxmox nodes;
- control-plane and worker-node definitions;
- vCPU, RAM, and storage values;
- IP addresses;
- gateway;
- DNS;
- bridge;
- storage pool;
- kubeconfig output path.

The local provider YAML must match the available infrastructure. The example YAML is a review aid and must not be treated as a real execution file unless it has been explicitly adapted for the target environment.

---

## Step 5 — Produce a Dry-Run Execution Plan

Run a dry-run plan before executing the real C1 cycle. This validates profile resolution and command construction without provisioning or modifying infrastructure.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope provider-backed-cycle `
  -ToolPath $ToolPath `
  -ProviderConfig $ProviderConfig `
  -BaselineReplicas "A,B,C" `
  -RunId "${RunId}_dry_run" `
  -WriteLatestAliases `
  -DryRun
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope provider-backed-cycle \
  --tool-path "$TOOL_PATH" \
  --provider-config "$PROVIDER_CONFIG" \
  --baseline-replicas "A,B,C" \
  --run-id "${RUN_ID}_dry_run" \
  --write-latest-aliases \
  --dry-run
```

Inspect the generated execution plan before continuing.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C1\execution
Get-Content .\results\experimental-cycles\C1\execution\latest-cycle-execution-summary.txt
```

### Bash

```bash
ls -la ./results/experimental-cycles/C1/execution
cat ./results/experimental-cycles/C1/execution/latest-cycle-execution-summary.txt
```

---

## Step 6 — Execute the Complete C1 Baseline Cycle

Run the complete provider-backed C1 baseline cycle.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope provider-backed-cycle `
  -ToolPath $ToolPath `
  -ProviderConfig $ProviderConfig `
  -BaselineReplicas "A,B,C" `
  -RunId $RunId `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope provider-backed-cycle \
  --tool-path "$TOOL_PATH" \
  --provider-config "$PROVIDER_CONFIG" \
  --baseline-replicas "A,B,C" \
  --run-id "$RUN_ID" \
  --write-latest-aliases
```

If the cluster is otherwise healthy but the Metrics API produces a known non-blocking warning, rerun with the Metrics API warning bypass enabled.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope provider-backed-cycle `
  -ToolPath $ToolPath `
  -ProviderConfig $ProviderConfig `
  -BaselineReplicas "A,B,C" `
  -RunId $RunId `
  -AllowMetricsWarning `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope provider-backed-cycle \
  --tool-path "$TOOL_PATH" \
  --provider-config "$PROVIDER_CONFIG" \
  --baseline-replicas "A,B,C" \
  --run-id "$RUN_ID" \
  --allow-metrics-warning \
  --write-latest-aliases
```

---

## Step 7 — Verify the Generated Kubeconfig

After provisioning or reuse, verify that the generated kubeconfig reaches the provider-backed cluster.

### Windows PowerShell

```powershell
kubectl --kubeconfig $Kubeconfig cluster-info
kubectl --kubeconfig $Kubeconfig config view --minify
kubectl --kubeconfig $Kubeconfig get nodes -o wide
kubectl --kubeconfig $Kubeconfig get pods -A
```

### Bash

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" cluster-info
kubectl --kubeconfig "$KUBECONFIG_PATH" config view --minify
kubectl --kubeconfig "$KUBECONFIG_PATH" get nodes -o wide
kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -A
```

Expected high-level cluster shape:

```text
1 control-plane node
2 worker nodes
K3s distribution
CPU-only infrastructure
```

---

## Step 8 — Verify the LocalAI Runtime State

Inspect the LocalAI namespace after deployment.

### Windows PowerShell

```powershell
kubectl --kubeconfig $Kubeconfig get namespace $Namespace
kubectl --kubeconfig $Kubeconfig get all -n $Namespace
kubectl --kubeconfig $Kubeconfig get pods -n $Namespace -o wide
kubectl --kubeconfig $Kubeconfig get pvc -n $Namespace
kubectl --kubeconfig $Kubeconfig get events -n $Namespace --sort-by=.metadata.creationTimestamp
```

### Bash

```bash
kubectl --kubeconfig "$KUBECONFIG_PATH" get namespace "$NAMESPACE"
kubectl --kubeconfig "$KUBECONFIG_PATH" get all -n "$NAMESPACE"
kubectl --kubeconfig "$KUBECONFIG_PATH" get pods -n "$NAMESPACE" -o wide
kubectl --kubeconfig "$KUBECONFIG_PATH" get pvc -n "$NAMESPACE"
kubectl --kubeconfig "$KUBECONFIG_PATH" get events -n "$NAMESPACE" --sort-by=.metadata.creationTimestamp
```

Expected application-level resources include:

- `localai-server`;
- `localai-rpc-a`;
- `localai-rpc-b`;
- LocalAI services;
- runtime ConfigMap;
- model PVC.

Inactive worker definitions may exist as reusable service or topology components depending on the applied compositions, but the C1 baseline expects two active RPC workers.

---

## Step 9 — Verify Core C1 Artifacts

Verify that all major C1 artifact families exist.

### Windows PowerShell

```powershell
$ExpectedC1Roots = @(
  ".\results\experimental-cycles\C1\execution",
  ".\results\experimental-cycles\C1\infrastructure\provisioning",
  ".\results\experimental-cycles\C1\infrastructure\validation",
  ".\results\experimental-cycles\C1\placement",
  ".\results\experimental-cycles\C1\application\deployment",
  ".\results\experimental-cycles\C1\observability\minimal",
  ".\results\experimental-cycles\C1\benchmark\baseline",
  ".\results\experimental-cycles\C1\diagnosis",
  ".\results\experimental-cycles\C1\reporting",
  ".\results\experimental-cycles\C1\completion-gate",
  ".\results\experimental-cycles\C1\freeze",
  ".\results\experimental-cycles\C1\artifacts"
)

$ExpectedC1Roots | ForEach-Object {
  if (-not (Test-Path $_)) {
    Write-Warning "Expected C1 artifact root not found: $_"
  }
  else {
    Write-Host "Found: $_"
  }
}
```

### Bash

```bash
expected_c1_roots=(
  "./results/experimental-cycles/C1/execution"
  "./results/experimental-cycles/C1/infrastructure/provisioning"
  "./results/experimental-cycles/C1/infrastructure/validation"
  "./results/experimental-cycles/C1/placement"
  "./results/experimental-cycles/C1/application/deployment"
  "./results/experimental-cycles/C1/observability/minimal"
  "./results/experimental-cycles/C1/benchmark/baseline"
  "./results/experimental-cycles/C1/diagnosis"
  "./results/experimental-cycles/C1/reporting"
  "./results/experimental-cycles/C1/completion-gate"
  "./results/experimental-cycles/C1/freeze"
  "./results/experimental-cycles/C1/artifacts"
)

for root in "${expected_c1_roots[@]}"; do
  if [[ ! -e "$root" ]]; then
    echo "Expected C1 artifact root not found: $root" >&2
  else
    echo "Found: $root"
  fi
done
```

---

## Step 10 — Inspect Completion and Freeze Outputs

Inspect the completion gate and freeze summaries.

### Windows PowerShell

```powershell
Get-Content .\results\experimental-cycles\C1\completion-gate\latest-completion-gate-summary.txt
Get-Content .\results\experimental-cycles\C1\freeze\latest-freeze-summary.txt
```

### Bash

```bash
cat ./results/experimental-cycles/C1/completion-gate/latest-completion-gate-summary.txt
cat ./results/experimental-cycles/C1/freeze/latest-freeze-summary.txt
```

The accepted C1 completion status is normally:

```text
completed
```

If an unsupported condition is explicitly detected and captured by the pipeline, it must be represented through the diagnosis, reporting, and completion-gate artifacts rather than manually edited.

---

## Step 11 — Inspect the Generated Report

Open or inspect the generated C1 report.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C1\reporting
Get-Content .\results\experimental-cycles\C1\reporting\report.md
```

### Bash

```bash
ls -la ./results/experimental-cycles/C1/reporting
cat ./results/experimental-cycles/C1/reporting/report.md
```

The HTML report is generated at:

```text
results/experimental-cycles/C1/reporting/index.html
```

The global reporting site is generated under:

```text
results/reporting/
```

---

## Step 12 — Step-by-Step Recovery Path

The end-to-end command is the preferred C1 execution path. The step-by-step commands below are intended for controlled recovery, inspection, or reruns of a specific stage.

### 12.1 Provision or Reuse the Provider-Backed Cluster

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope provisioning `
  -ProvisioningAction provision `
  -ToolPath $ToolPath `
  -ProviderConfig $ProviderConfig `
  -RunId "${RunId}_provisioning" `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope provisioning \
  --provisioning-action provision \
  --tool-path "$TOOL_PATH" \
  --provider-config "$PROVIDER_CONFIG" \
  --run-id "${RUN_ID}_provisioning" \
  --write-latest-aliases
```

### 12.2 Refresh the Generated Kubeconfig

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope provisioning `
  -ProvisioningAction kubeconfig `
  -ToolPath $ToolPath `
  -ProviderConfig $ProviderConfig `
  -RunId "${RunId}_kubeconfig" `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope provisioning \
  --provisioning-action kubeconfig \
  --tool-path "$TOOL_PATH" \
  --provider-config "$PROVIDER_CONFIG" \
  --run-id "${RUN_ID}_kubeconfig" \
  --write-latest-aliases
```

### 12.3 Validate the Provider-Backed Cluster

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope cluster-validation `
  -Kubeconfig $Kubeconfig `
  -RunId "${RunId}_cluster_validation" `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope cluster-validation \
  --kubeconfig "$KUBECONFIG_PATH" \
  --run-id "${RUN_ID}_cluster_validation" \
  --write-latest-aliases
```

If required, add the non-blocking Metrics API warning bypass.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope cluster-validation `
  -Kubeconfig $Kubeconfig `
  -RunId "${RunId}_cluster_validation" `
  -AllowMetricsWarning `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope cluster-validation \
  --kubeconfig "$KUBECONFIG_PATH" \
  --run-id "${RUN_ID}_cluster_validation" \
  --allow-metrics-warning \
  --write-latest-aliases
```

### 12.4 Resolve the C1 Placement Profile

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope placement-profile `
  -PlacementProfileId "PL_COLOCATED" `
  -PlacementProfilePath ".\config\placement\profiles\PL_COLOCATED.json" `
  -RunId "${RunId}_placement" `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope placement-profile \
  --placement-profile-id "PL_COLOCATED" \
  --placement-profile-path "./config/placement/profiles/PL_COLOCATED.json" \
  --run-id "${RUN_ID}_placement" \
  --write-latest-aliases
```

### 12.5 Deploy LocalAI and Run Smoke Validation

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope localai-deployment `
  -DeploymentAction deploy `
  -Kubeconfig $Kubeconfig `
  -BaseUrl $BaseUrl `
  -RunId "${RunId}_localai_deployment" `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope localai-deployment \
  --deployment-action deploy \
  --kubeconfig "$KUBECONFIG_PATH" \
  --base-url "$BASE_URL" \
  --run-id "${RUN_ID}_localai_deployment" \
  --write-latest-aliases
```

### 12.6 Capture Minimal Observability After Deployment

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope minimal-observability `
  -MinimalObservabilityAction capture `
  -ObservabilityStage post-deployment `
  -Kubeconfig $Kubeconfig `
  -RunId "${RunId}_observability_post_deployment" `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope minimal-observability \
  --minimal-observability-action capture \
  --observability-stage post-deployment \
  --kubeconfig "$KUBECONFIG_PATH" \
  --run-id "${RUN_ID}_observability_post_deployment" \
  --write-latest-aliases
```

### 12.7 Execute Baseline Replicas

### Windows PowerShell

```powershell
foreach ($Replica in @("A", "B", "C")) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\baseline\Start-OfficialBaseline.ps1" `
    -Replica $Replica `
    -BenchmarkConfig $BaselineConfig `
    -Kubeconfig $Kubeconfig `
    -PrecheckConfig $PrecheckProfile `
    -Namespace $Namespace
}
```

### Bash

```bash
for replica in A B C; do
  bash ./scripts/load/baseline/start-official-baseline.sh \
    --replica "$replica" \
    --benchmark-config "$BASELINE_CONFIG" \
    --kubeconfig "$KUBECONFIG_PATH" \
    --precheck-config "$PRECHECK_PROFILE" \
    --namespace "$NAMESPACE"
done
```

### 12.8 Capture Minimal Observability After Benchmark

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope minimal-observability `
  -MinimalObservabilityAction capture `
  -ObservabilityStage post-benchmark `
  -Kubeconfig $Kubeconfig `
  -RunId "${RunId}_observability_post_benchmark" `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope minimal-observability \
  --minimal-observability-action capture \
  --observability-stage post-benchmark \
  --kubeconfig "$KUBECONFIG_PATH" \
  --run-id "${RUN_ID}_observability_post_benchmark" \
  --write-latest-aliases
```

### 12.9 Generate Technical Diagnosis

### Windows PowerShell

```powershell
python .\scripts\analysis\generate-technical-diagnosis.py `
  --repo-root . `
  --profile-config $DiagnosisProfile `
  --family all `
  --output-json ".\results\experimental-cycles\C1\diagnosis\${RunId}_diagnosis_all_diagnosis.json" `
  --output-text ".\results\experimental-cycles\C1\diagnosis\${RunId}_diagnosis_all_diagnosis.txt" `
  --diagnosis-id "${RunId}_diagnosis_all"
```

### Bash

```bash
python ./scripts/analysis/generate-technical-diagnosis.py \
  --repo-root . \
  --profile-config "$DIAGNOSIS_PROFILE" \
  --family all \
  --output-json "./results/experimental-cycles/C1/diagnosis/${RUN_ID}_diagnosis_all_diagnosis.json" \
  --output-text "./results/experimental-cycles/C1/diagnosis/${RUN_ID}_diagnosis_all_diagnosis.txt" \
  --diagnosis-id "${RUN_ID}_diagnosis_all"
```

### 12.10 Generate Reporting

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope reporting `
  -ReportingProfile $ReportingProfile `
  -ReportingId "${RunId}_reporting"
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope reporting \
  --reporting-profile "$REPORTING_PROFILE" \
  --reporting-id "${RUN_ID}_reporting"
```

### 12.11 Evaluate the Completion Gate

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope completion-gate `
  -CompletionGateProfile $CompletionGateProfile `
  -DiagnosisJson ".\results\experimental-cycles\C1\diagnosis\${RunId}_diagnosis_all_diagnosis.json" `
  -EvaluationId "${RunId}_completion_gate"
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope completion-gate \
  --completion-gate-profile "$COMPLETION_GATE_PROFILE" \
  --diagnosis-json "./results/experimental-cycles/C1/diagnosis/${RUN_ID}_diagnosis_all_diagnosis.json" \
  --evaluation-id "${RUN_ID}_completion_gate"
```

### 12.12 Freeze C1 Evidence

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope freeze `
  -FreezeProfile $FreezeProfile `
  -FreezeId "${RunId}_freeze" `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope freeze \
  --freeze-profile "$FREEZE_PROFILE" \
  --freeze-id "${RUN_ID}_freeze" \
  --force-freeze \
  --write-latest-aliases
```

---

## Optional — Destroy the C1 Provider-Backed Cluster

The C1 lifecycle is `reuse`, so the cluster is retained by default. Destroy it only when the retained provider-backed cluster is no longer needed or when a clean infrastructure recreation is required.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $CycleConfig `
  -ExecutionScope provisioning `
  -ProvisioningAction destroy `
  -ToolPath $ToolPath `
  -ProviderConfig $ProviderConfig `
  -ConfirmDelete `
  -RunId "${RunId}_destroy" `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --execution-scope provisioning \
  --provisioning-action destroy \
  --tool-path "$TOOL_PATH" \
  --provider-config "$PROVIDER_CONFIG" \
  --confirm-delete \
  --run-id "${RUN_ID}_destroy" \
  --write-latest-aliases
```

Do not destroy the C1 cluster if subsequent provider-backed campaigns are expected to reuse the same cluster identity immediately.

---

## C1 Regeneration Checklist

A complete C1 regeneration is ready for downstream analysis when all checklist items below are satisfied.

- [ ] The local provider YAML has been reviewed and matches the target Proxmox environment.
- [ ] The dry-run plan resolves all required C1 profiles and writes a cycle execution plan.
- [ ] The provider-backed cluster has been provisioned or reused through `proxmox-k3s`.
- [ ] The generated kubeconfig exists and reaches the expected K3s cluster.
- [ ] Cluster validation has completed or produced an explicitly documented non-blocking warning.
- [ ] The placement profile `PL_COLOCATED` has been resolved.
- [ ] The LocalAI namespace `localai-benchmark` exists.
- [ ] The LocalAI server and the two active RPC workers are deployed.
- [ ] LocalAI smoke validation has completed.
- [ ] Minimal observability has been captured after deployment.
- [ ] Baseline replicas `A`, `B`, and `C` have been executed.
- [ ] Minimal observability has been captured after benchmark execution.
- [ ] Technical diagnosis has been generated.
- [ ] Reporting has been generated.
- [ ] The completion gate has been evaluated.
- [ ] C1 freeze artifacts have been generated.
- [ ] C1 artifacts are stored only under `results/experimental-cycles/C1/` and the global reporting site root.
- [ ] Generated kubeconfigs and provider-local configuration files remain untracked.

---

## Next Runbook

After regenerating C1, continue with the comparative provider-backed campaign execution runbook:

```text
docs/runbooks/08-provider-backed-c2-c6-campaign-execution.md
```
