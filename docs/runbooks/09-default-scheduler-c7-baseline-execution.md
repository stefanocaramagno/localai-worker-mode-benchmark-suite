# Default Scheduler C7 Baseline Execution

## Purpose

This runbook describes how to execute and regenerate the `C7` default Kubernetes scheduler baseline campaign.

`C7` evaluates how the Kubernetes default scheduler places distributed LocalAI worker-mode tenant workloads when the campaign varies:

- the number of tenant-scoped LocalAI application clusters;
- the number of provider-backed worker nodes;
- the network-latency profile applied between nodes;
- the tenant traffic profile;
- the model mix for controlled stress scenarios.

The purpose of `C7` is not to introduce a custom scheduler. The purpose is to create a realistic baseline in which Kubernetes schedules the pods without hard placement controls, and then to preserve evidence that connects the resulting pod-to-node placement with latency, throughput, failure, schedulability, and resource-pressure outcomes.

`C7` should therefore be interpreted as the default-scheduler evidence baseline that follows the controlled provider-backed campaigns `C2` through `C6`.

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

## C7 Execution Model

`C7` follows this execution model:

```text
C7 campaign profile
→ default-scheduler scenario profiles
→ provider-backed infrastructure profile resolution
→ proxmox-k3s provisioning or reuse
→ generated kubeconfig
→ cluster validation
→ default-scheduler manifest validation
→ tenant-scoped LocalAI deployment
→ multi-tenant smoke validation
→ latency injection when configured
→ scheduler-decision capture
→ multi-tenant Locust benchmark
→ minimal observability capture
→ technical diagnosis
→ reporting
→ completion gate
→ freeze
```

The execution model intentionally captures scheduler evidence before benchmark interpretation. Performance values without placement evidence are not sufficient for `C7`, because the central question is whether the default scheduler produced an operationally valid but potentially suboptimal placement.

---

## Methodological Boundary

`C7` must preserve the following boundary conditions.

| Rule | Required Behavior |
|---|---|
| Scheduler mode | Use the Kubernetes default scheduler. |
| Hard placement controls | Do not use `spec.nodeName`, hostname-specific `nodeSelector`, or hostname-specific node affinity. |
| Allowed general constraints | Control-plane exclusion, generic worker-nodepool selection, resource requests, resource limits, tenant labels, and role labels. |
| Custom scheduler | Do not introduce a scheduler plugin, extender, replacement scheduler, or custom placement policy in this campaign. |
| Placement evidence | Capture the actual pod-to-node placement selected by Kubernetes. |
| Tenant evidence | Preserve benchmark and smoke-validation evidence per tenant. |
| Unsupported scenarios | Preserve unsupported, non-schedulable, or resource-constrained scenarios as evidence when they match the campaign design. |

This boundary keeps `C7` distinct from the controlled placement campaign `C4`, the latency-injection campaign `C5`, and the multi-tenancy campaign `C6`.

---

## Canonical C7 Inputs

The canonical C7 inputs are:

```text
config/experimental-cycles/C7.json
config/scenarios/default-scheduler/DEFAULT_SCHEDULER_SCENARIOS_INDEX.json
config/scenarios/default-scheduler/
config/infrastructure/profiles/INFRA_C7_1CP_2W_8C16G.json
config/infrastructure/profiles/INFRA_C7_1CP_3W_8C16G.json
config/infrastructure/profiles/INFRA_C7_1CP_4W_8C16G.json
config/infrastructure/providers/proxmox-k3s/PROXMOX_K3S_PROVIDER_BINDINGS_INDEX.json
infra/k8s/compositions/default-scheduler/
load-tests/locust/locustfile.py
config/technical-diagnosis/profiles/TD_C7_DEFAULT_SCHEDULER_BASELINE.json
config/reporting/profiles/RP_C7_DEFAULT_SCHEDULER_BASELINE.json
config/completion-gate/profiles/CG_C7_DEFAULT_SCHEDULER_BASELINE.json
config/freeze/profiles/FR_C7_DEFAULT_SCHEDULER_BASELINE.json
```

The provider-local YAML files referenced by the provider bindings remain local configuration files. They must not be replaced by generated result artifacts.

---

## Canonical C7 Output Roots

The canonical C7 output roots are:

```text
results/experimental-cycles/C7/execution/
results/experimental-cycles/C7/benchmark/default-scheduler/
results/experimental-cycles/C7/variants/
results/experimental-cycles/C7/scheduler/
results/experimental-cycles/C7/diagnosis/
results/experimental-cycles/C7/reporting/
results/experimental-cycles/C7/completion-gate/
results/experimental-cycles/C7/freeze/
results/experimental-cycles/C7/artifacts/
```

The most important scheduler evidence artifact is:

```text
default-scheduler-decision-evidence.json
```

The campaign runner stores scenario-scoped scheduler evidence under the C7 result tree. The reporting and diagnosis layers consume these artifacts to connect placement with benchmark behavior.

---

## Scenario Families and Classes

`C7` uses one scenario family:

```text
default-scheduler
```

The scenario profiles are classified as follows.

| Class | Purpose |
|---|---|
| `official` | Core baseline scenarios that should be executed first when the infrastructure is available. |
| `diagnostic` | Additional scenarios used to inspect intermediate node counts or stronger latency profiles. |
| `stress` | More demanding scenarios, such as three tenants or mixed models, that may become unsupported under current infrastructure limits. |

The campaign profile contains the planned scenario references. The runner executes the planned list declared by the active `C7` profile.

---

## Primary Scenario

The most representative C7 scenario is:

```text
DS_2T_4N_L1_DIFFERENTIATED_M1M1_W2
```

It combines:

- Kubernetes default scheduling;
- two tenant-scoped LocalAI deployments;
- four provider-backed worker nodes;
- the `L1_EDGE_NEAR` latency profile;
- differentiated tenant traffic;
- the same model across tenants;
- two LocalAI RPC workers per tenant.

This scenario should receive particular attention when interpreting C7 evidence, because it combines the core dimensions of the campaign without immediately moving to stress-only conditions.

---

## Execution Safety Rules

Before executing C7, observe the following rules.

1. Do not run C7 against the local default Kubernetes context.
2. Use the kubeconfig generated or referenced by the active provider-backed variant.
3. Confirm destructive provider actions explicitly when the lifecycle policy deletes clusters.
4. Do not edit generated runtime profiles to make a scenario pass.
5. Do not replace a failed or unsupported scenario with manual placement controls.
6. Do not treat a non-schedulable scenario as an ordinary script error when the scenario is expected to test an infrastructure boundary.
7. Do not disable scheduler capture in official executions unless the execution is explicitly a recovery or diagnostic run.
8. Do not compare C7 with C4-C6 without checking placement policy, latency profile, tenant count, and infrastructure profile.

---

## Step 1 — Verify Required Files

### Windows PowerShell

```powershell
$RequiredFiles = @(
  ".\config\experimental-cycles\C7.json",
  ".\config\scenarios\default-scheduler\DEFAULT_SCHEDULER_SCENARIOS_INDEX.json",
  ".\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1",
  ".\scripts\experimental-cycles\run-experimental-campaign.py",
  ".\scripts\validation\scheduler\validate-default-scheduler-manifests.py",
  ".\scripts\observability\scheduler\capture-scheduler-decisions.py",
  ".\scripts\load\multi-tenant\run-multi-tenant-locust.py",
  ".\config\technical-diagnosis\profiles\TD_C7_DEFAULT_SCHEDULER_BASELINE.json",
  ".\config\reporting\profiles\RP_C7_DEFAULT_SCHEDULER_BASELINE.json",
  ".\config\completion-gate\profiles\CG_C7_DEFAULT_SCHEDULER_BASELINE.json",
  ".\config\freeze\profiles\FR_C7_DEFAULT_SCHEDULER_BASELINE.json"
)

$RequiredFiles | ForEach-Object {
  if (-not (Test-Path $_)) {
    throw "Missing required C7 file: $_"
  }
}
```

### Bash

```bash
required_files=(
  "config/experimental-cycles/C7.json"
  "config/scenarios/default-scheduler/DEFAULT_SCHEDULER_SCENARIOS_INDEX.json"
  "scripts/experimental-cycles/start-experimental-campaign.sh"
  "scripts/experimental-cycles/run-experimental-campaign.py"
  "scripts/validation/scheduler/validate-default-scheduler-manifests.py"
  "scripts/observability/scheduler/capture-scheduler-decisions.py"
  "scripts/load/multi-tenant/run-multi-tenant-locust.py"
  "config/technical-diagnosis/profiles/TD_C7_DEFAULT_SCHEDULER_BASELINE.json"
  "config/reporting/profiles/RP_C7_DEFAULT_SCHEDULER_BASELINE.json"
  "config/completion-gate/profiles/CG_C7_DEFAULT_SCHEDULER_BASELINE.json"
  "config/freeze/profiles/FR_C7_DEFAULT_SCHEDULER_BASELINE.json"
)

for file in "${required_files[@]}"; do
  test -f "$file" || { echo "Missing required C7 file: $file" >&2; exit 1; }
done
```

---

## Step 2 — Define Runtime Variables

### Windows PowerShell

```powershell
$CycleConfig = ".\config\experimental-cycles\C7.json"
$ToolPath = "proxmox-k3s"
$RunId = "C7_default_scheduler_baseline"
```

### Bash

```bash
CYCLE_CONFIG="config/experimental-cycles/C7.json"
TOOL_PATH="proxmox-k3s"
RUN_ID="C7_default_scheduler_baseline"
```

Use an explicit provider executable path instead of `proxmox-k3s` if the binary is not available on `PATH`.

On Windows, campaign PowerShell entry points are invoked through `powershell.exe -NoProfile -ExecutionPolicy Bypass -File`. This keeps the execution-policy bypass scoped to the launched process and avoids failures when local unsigned repository scripts are blocked by a restrictive workstation policy.

---

## Step 3 — Validate JSON Configuration Syntax

### Windows PowerShell

```powershell
python - <<'PY'
import json
from pathlib import Path

paths = [
    Path("config/experimental-cycles/C7.json"),
    Path("config/scenarios/default-scheduler/DEFAULT_SCHEDULER_SCENARIOS_INDEX.json"),
    *Path("config/scenarios/default-scheduler").glob("*.json"),
    Path("config/technical-diagnosis/profiles/TD_C7_DEFAULT_SCHEDULER_BASELINE.json"),
    Path("config/reporting/profiles/RP_C7_DEFAULT_SCHEDULER_BASELINE.json"),
    Path("config/completion-gate/profiles/CG_C7_DEFAULT_SCHEDULER_BASELINE.json"),
    Path("config/freeze/profiles/FR_C7_DEFAULT_SCHEDULER_BASELINE.json"),
]

for path in paths:
    with path.open("r", encoding="utf-8") as handle:
        json.load(handle)

print(f"Validated {len(paths)} C7 JSON files.")
PY
```

### Bash

```bash
python - <<'PY'
import json
from pathlib import Path

paths = [
    Path("config/experimental-cycles/C7.json"),
    Path("config/scenarios/default-scheduler/DEFAULT_SCHEDULER_SCENARIOS_INDEX.json"),
    *Path("config/scenarios/default-scheduler").glob("*.json"),
    Path("config/technical-diagnosis/profiles/TD_C7_DEFAULT_SCHEDULER_BASELINE.json"),
    Path("config/reporting/profiles/RP_C7_DEFAULT_SCHEDULER_BASELINE.json"),
    Path("config/completion-gate/profiles/CG_C7_DEFAULT_SCHEDULER_BASELINE.json"),
    Path("config/freeze/profiles/FR_C7_DEFAULT_SCHEDULER_BASELINE.json"),
]

for path in paths:
    with path.open("r", encoding="utf-8") as handle:
        json.load(handle)

print(f"Validated {len(paths)} C7 JSON files.")
PY
```

---

## Step 4 — Validate Default-Scheduler Manifests

This validation checks that the default-scheduler compositions do not contain hard placement controls.

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

When `kubectl` or `kustomize` is available, validate rendered manifests as well.

### Windows PowerShell

```powershell
python .\scripts\validation\scheduler\validate-default-scheduler-manifests.py `
  --repo-root . `
  --scan-root .\infra\k8s\compositions\default-scheduler `
  --render-kustomize `
  --require-render `
  --json
```

### Bash

```bash
python scripts/validation/scheduler/validate-default-scheduler-manifests.py \
  --repo-root . \
  --scan-root infra/k8s/compositions/default-scheduler \
  --render-kustomize \
  --require-render \
  --json
```

---

## Step 5 — Produce a Dry-Run Execution Plan

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1" `
  -CycleConfig $CycleConfig `
  -ToolPath $ToolPath `
  -RunId $RunId `
  -DryRun `
  -AllowMetricsWarning `
  -WriteLatestAliases
```

### Bash

```bash
scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --tool-path "$TOOL_PATH" \
  --run-id "$RUN_ID" \
  --dry-run \
  --allow-metrics-warning \
  --write-latest-aliases
```

The dry run should resolve scenarios, provider bindings, generated runtime configuration paths, diagnosis profiles, reporting profiles, completion-gate profiles, and freeze profiles without creating or deleting real infrastructure.

---

## Step 6 — Execute the C7 Campaign

C7 provider-backed variants may create and delete clusters according to the active lifecycle profile. Review the provider-local YAML files before starting the real execution.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1" `
  -CycleConfig $CycleConfig `
  -ToolPath $ToolPath `
  -RunId $RunId `
  -AllowMetricsWarning `
  -ContinueOnFailure `
  -ConfirmDelete `
  -WriteLatestAliases
```

### Bash

```bash
scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --tool-path "$TOOL_PATH" \
  --run-id "$RUN_ID" \
  --allow-metrics-warning \
  --continue-on-failure \
  --confirm-delete \
  --write-latest-aliases
```

Use `--continue-on-failure` / `-ContinueOnFailure` when unsupported scenarios must be preserved and later interpreted by diagnosis and completion-gate logic.

---

## Step 7 — Inspect Campaign Execution Outputs

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C7 -Recurse |
  Select-Object FullName, Length |
  Out-Host
```

### Bash

```bash
find results/experimental-cycles/C7 -maxdepth 4 -type f | sort
```

Expected areas include execution manifests, generated runtime configs, benchmark outputs, scheduler decision evidence, diagnosis outputs, reporting outputs, completion-gate outputs, and freeze outputs.

---

## Step 8 — Inspect Scheduler Decision Evidence

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C7 -Recurse `
  -Filter "default-scheduler-decision-evidence.json" |
  Select-Object FullName
```

### Bash

```bash
find results/experimental-cycles/C7 -name "default-scheduler-decision-evidence.json" | sort
```

Open the evidence for the scenario under analysis and verify that it contains at least:

- tenant identifiers;
- namespaces;
- deployments;
- pod names;
- assigned nodes;
- resource requests and limits;
- Kubernetes events;
- placement classification;
- failed scheduling events when applicable.

---

## Step 9 — Inspect Multi-Tenant Benchmark Outputs

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C7\benchmark\default-scheduler -Recurse |
  Where-Object { $_.Name -match "stats|summary|locust|tenant" } |
  Select-Object FullName, Length
```

### Bash

```bash
find results/experimental-cycles/C7/benchmark/default-scheduler \
  -type f \( -name "*stats*" -o -name "*summary*" -o -name "*locust*" -o -name "*tenant*" \) \
  | sort
```

For multi-tenant scenarios, verify that tenant-specific outputs are present for every expected tenant.

---

## Step 10 — Inspect Technical Diagnosis

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C7\diagnosis -Recurse |
  Select-Object FullName, Length
```

### Bash

```bash
find results/experimental-cycles/C7/diagnosis -type f | sort
```

The diagnosis should preserve default-scheduler evidence, tenant traffic evidence, latency profile context, unsupported-scenario evidence, and placement-performance interpretation.

---

## Step 11 — Inspect Reporting Outputs

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C7\reporting -Recurse |
  Select-Object FullName, Length
```

### Bash

```bash
find results/experimental-cycles/C7/reporting -type f | sort
```

The C7 report should include:

- scenario summary;
- pod-to-node placement evidence;
- placement classification;
- tenant traffic profile;
- benchmark metrics per tenant;
- latency and resource-pressure context;
- negative evidence when the default scheduler produces suboptimal or unsupported outcomes.

---

## Step 12 — Inspect Completion Gate and Freeze

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C7\completion-gate -Recurse |
  Select-Object FullName, Length

Get-ChildItem .\results\experimental-cycles\C7\freeze -Recurse |
  Select-Object FullName, Length
```

### Bash

```bash
find results/experimental-cycles/C7/completion-gate -type f | sort
find results/experimental-cycles/C7/freeze -type f | sort
```

An acceptable completion state may be either:

```text
completed
completed_with_unsupported_scenarios
```

The second state is acceptable only when unsupported scenarios are documented with explicit evidence.

---

## Optional Manual Scheduler Capture

Use this only for targeted inspection or recovery. During normal C7 execution, scheduler capture is part of the campaign pipeline.

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

Adjust the kubeconfig path to the provider-generated kubeconfig used by the active scenario.

---

## Optional Manual Multi-Tenant Locust Execution

Use this only when the LocalAI tenant deployments and port-forwarding conditions are already understood.

### Windows PowerShell

```powershell
python .\scripts\load\multi-tenant\run-multi-tenant-locust.py `
  --repo-root . `
  --scenario-config .\config\scenarios\default-scheduler\DS_2T_4N_L1_DIFFERENTIATED_M1M1_W2.json `
  --kubeconfig .\config\cluster-access\provider-backed\kubeconfig `
  --write-latest-aliases
```

### Bash

```bash
python scripts/load/multi-tenant/run-multi-tenant-locust.py \
  --repo-root . \
  --scenario-config config/scenarios/default-scheduler/DS_2T_4N_L1_DIFFERENTIATED_M1M1_W2.json \
  --kubeconfig config/cluster-access/provider-backed/kubeconfig \
  --write-latest-aliases
```

Prefer the campaign runner for official evidence generation.

---

## Interpretation Checklist

A C7 execution is useful when it allows the operator to answer the following questions.

- Did Kubernetes schedule the pods without hard placement controls?
- Did tenant workloads receive distinct or overlapping node placements?
- Were communicating LocalAI server/worker components split across latency-affected nodes?
- Were multiple tenant workloads co-located on the same worker node?
- Did tenant traffic differentiation correlate with performance differences?
- Did injected latency make default-scheduler decisions more expensive?
- Did unsupported scenarios fail because of clear schedulability or resource constraints?
- Does the report preserve enough evidence to justify or reject the need for a future improved scheduling strategy?

---

## Readiness Checklist

Before treating C7 as complete, verify the following.

- [ ] `C7.json` is valid and references the expected scenario family.
- [ ] All default-scheduler scenario JSON files are valid.
- [ ] Default-scheduler manifests pass source validation.
- [ ] Rendered default-scheduler manifests pass validation when rendering tools are available.
- [ ] Provider-local YAML files are available for the required infrastructure profiles.
- [ ] Scheduler decision evidence exists for executed scenarios.
- [ ] Tenant-specific benchmark artifacts exist for all active tenants.
- [ ] Diagnosis and reporting outputs include default-scheduler placement context.
- [ ] Completion gate has accepted the execution state.
- [ ] Freeze has preserved the C7 evidence package.

---

## Next Runbook

Proceed to:

```text
docs/runbooks/10-resource-aware-scheduler-c8-execution.md
```

That runbook explains the paired resource-aware scheduler campaign that uses default and load-aware scheduler variants under controlled `L0_NONE` scenarios.
