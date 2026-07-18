# Resource-Aware Scheduler C8 Execution

## Purpose

This runbook documents the `C8` resource-aware scheduler campaign.

`C8` compares Kubernetes default scheduling with a load-aware custom scheduler for distributed LocalAI worker-mode workloads. The campaign is provider-backed, multi-tenant, resource-aware, and intentionally limited to `L0_NONE` scenarios so that the comparison isolates CPU and memory telemetry effects rather than network-emulation effects.

The purpose of this runbook is to provide an operational procedure for:

1. validating the C8 resource-aware scheduler configuration set;
2. validating the provider-backed infrastructure required by C8;
3. validating the resource-aware scheduler Kubernetes manifests;
4. installing and validating `mon-agent` as the runtime annotation source;
5. installing and validating the custom second scheduler for load-aware variants;
6. executing the paired default/load-aware campaign;
7. inspecting scheduler evidence, annotation evidence, benchmark outputs, diagnosis, reporting, completion-gate, and freeze artifacts.

`C8` must be interpreted as a controlled comparison. For each logical scenario, the default-scheduler variant and the load-aware variant must keep workload, model mix, tenant count, worker-node count, resource envelope, traffic profile, monitoring, namespace labeling, and rescheduling procedure constant. The scheduler is the principal variable.

---

## Repository Root Assumption

All commands assume that the current working directory is the repository root:

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

---

## C8 Execution Model

The C8 execution flow is:

```text
C8.json
→ resource-aware scheduler scenario index
→ paired resource-aware scheduler scenario profiles
→ provider-backed infrastructure profile and binding
→ proxmox-k3s cluster lifecycle
→ provider-backed cluster validation
→ resource-aware scheduler manifest validation
→ LocalAI tenant deployment
→ monitoring and mon-agent validation
→ custom scheduler installation for load-aware variants
→ telemetry priming and controlled redeployment
→ benchmark measurement window
→ scheduler decision capture
→ minimal observability
→ technical diagnosis
→ comparative reporting
→ completion gate
→ freeze
```

The campaign is executed through the campaign runner, not by directly executing `C8.json` as a single provider-backed cycle.

Canonical C8 campaign entry points:

```text
scripts/experimental-cycles/Start-ExperimentalCampaign.ps1
scripts/experimental-cycles/start-experimental-campaign.sh
scripts/experimental-cycles/run-experimental-campaign.py
```

Canonical C8 cycle profile:

```text
config/experimental-cycles/C8.json
```

---

## Methodological Boundary

C8 is a resource-aware scheduler campaign.

It must preserve the following boundaries:

| Boundary | C8 rule |
|---|---|
| Scheduler-mode pairing | Each logical scenario is executed as a paired default/load-aware evaluation. |
| Default scheduler variant | `spec.schedulerName` must be absent from LocalAI workloads. |
| Load-aware variant | `spec.schedulerName` must be `scheduler-plugins-scheduler`. |
| Custom scheduler plugin scope | Only `LoadAwareResourcesBalancedAllocation` is enabled for the initial comparison. |
| Runtime telemetry | CPU and memory annotations are required on nodes and selected LocalAI deployments. |
| Monitoring agent | `mon-agent` is the runtime annotation source. |
| Namespace selection | Application namespaces must be selected through `mon-agent/enabled=true`. |
| Required workload labels | LocalAI workloads must expose `group` and `app` labels consistently. |
| Latency injection | C8 uses `L0_NONE`; NetEm and Chaos Mesh latency injection are out of scope for C8. |
| Network-aware scheduling | Network-aware plugins are out of scope for C8. |
| Autoscaling | Autoscaling is out of scope for C8. |
| Placement controls | Hard pod placement controls must not be used to predetermine LocalAI placement. |
| Measurement boundary | Telemetry priming, rollout restart, readiness waiting, and stabilization are excluded from the official measurement window. |

C8 does not replace C7. C7 characterizes the default Kubernetes scheduler under multi-tenant and latency-aware scenarios. C8 uses that evidence to perform a controlled comparison against a resource-aware scheduler under paired `L0_NONE` scenarios.

---

## Canonical C8 Inputs

| Input family | Canonical path |
|---|---|
| Cycle profile | `config/experimental-cycles/C8.json` |
| Scenario index | `config/scenarios/resource-aware-scheduler/RESOURCE_AWARE_SCHEDULER_SCENARIOS_INDEX.json` |
| Scenario profiles | `config/scenarios/resource-aware-scheduler/RA_*.json` |
| Scheduler integration index | `config/scheduler/SCHEDULER_INTEGRATION_INDEX.json` |
| Load-aware scheduler profile | `config/scheduler/profiles/CS_C8_LOADAWARE_SECOND_SCHEDULER.json` |
| mon-agent index | `config/mon-agent/MON_AGENT_INDEX.json` |
| mon-agent profile | `config/mon-agent/profiles/MA_RESOURCE_AWARE.json` |
| Rescheduling index | `config/rescheduling/RESCHEDULING_INDEX.json` |
| Rescheduling profile | `config/rescheduling/profiles/RS_C8_RESOURCE_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json` |
| Infrastructure profiles | `config/infrastructure/profiles/INFRA_C8_1CP_2W_8C16G.json`, `config/infrastructure/profiles/INFRA_C8_1CP_4W_8C16G.json` |
| Provider bindings | `config/infrastructure/providers/proxmox-k3s/bindings/BINDING_INFRA_C8_*_PROXMOX_K3S.json` |
| Provider local YAML | `config/infrastructure/providers/proxmox-k3s/local/cluster.c8-*.local.yaml` |
| Resource-aware scheduler manifests | `infra/k8s/compositions/resource-aware-scheduler/` |
| Manifest validator | `scripts/validation/scheduler/validate-default-scheduler-manifests.py` |
| Technical diagnosis profile | `config/technical-diagnosis/profiles/TD_C8_RESOURCE_AWARE_SCHEDULER.json` |
| Reporting profile | `config/reporting/profiles/RP_C8_RESOURCE_AWARE_SCHEDULER.json` |
| Completion gate profile | `config/completion-gate/profiles/CG_C8_RESOURCE_AWARE_SCHEDULER.json` |
| Freeze profile | `config/freeze/profiles/FR_C8_RESOURCE_AWARE_SCHEDULER.json` |

---

## Canonical C8 Output Roots

| Artifact family | Canonical root |
|---|---|
| Campaign execution manifests | `results/experimental-cycles/C8/execution/` |
| Generated runtime configs | `results/experimental-cycles/C8/execution/generated-runtime-configs/` |
| Benchmark outputs | `results/experimental-cycles/C8/benchmark/resource-aware-scheduler/` |
| Scheduler decision evidence | `results/experimental-cycles/C8/scheduler/` |
| Custom scheduler evidence | `results/experimental-cycles/C8/scheduler/custom-scheduler/` |
| mon-agent evidence | `results/experimental-cycles/C8/observability/mon-agent/` |
| Rescheduling evidence | `results/experimental-cycles/C8/rescheduling/` |
| Minimal observability | `results/experimental-cycles/C8/observability/minimal/` |
| Technical diagnosis | `results/experimental-cycles/C8/diagnosis/` |
| Reporting | `results/experimental-cycles/C8/reporting/` |
| Completion gate | `results/experimental-cycles/C8/completion-gate/` |
| Freeze | `results/experimental-cycles/C8/freeze/` |
| Frozen snapshot | `results/experimental-cycles/C8/artifacts/` |

Generated artifacts under `results/` may be removed and regenerated. They should not be edited manually.

---

## C8 Scenario Matrix

C8 contains eight logical scenarios. Each logical scenario is executed in two variants:

```text
default scheduler variant
load-aware scheduler variant
```

| Priority | Logical scenario | Default variant | Load-aware variant |
|---|---|---|---|
| `P0` | `1T_2N_L0_UNIFORM_M1_W2` | `RA_DEFAULT_1T_2N_L0_UNIFORM_M1_W2` | `RA_LOADAWARE_1T_2N_L0_UNIFORM_M1_W2` |
| `P0` | `1T_4N_L0_UNIFORM_M1_W2` | `RA_DEFAULT_1T_4N_L0_UNIFORM_M1_W2` | `RA_LOADAWARE_1T_4N_L0_UNIFORM_M1_W2` |
| `P0` | `2T_2N_L0_UNIFORM_M1M1_W2` | `RA_DEFAULT_2T_2N_L0_UNIFORM_M1M1_W2` | `RA_LOADAWARE_2T_2N_L0_UNIFORM_M1M1_W2` |
| `P0` | `2T_4N_L0_UNIFORM_M1M1_W2` | `RA_DEFAULT_2T_4N_L0_UNIFORM_M1M1_W2` | `RA_LOADAWARE_2T_4N_L0_UNIFORM_M1M1_W2` |
| `P0` | `2T_2N_L0_DIFFERENTIATED_M1M1_W2` | `RA_DEFAULT_2T_2N_L0_DIFFERENTIATED_M1M1_W2` | `RA_LOADAWARE_2T_2N_L0_DIFFERENTIATED_M1M1_W2` |
| `P0` | `2T_4N_L0_DIFFERENTIATED_M1M1_W2` | `RA_DEFAULT_2T_4N_L0_DIFFERENTIATED_M1M1_W2` | `RA_LOADAWARE_2T_4N_L0_DIFFERENTIATED_M1M1_W2` |
| `P1` | `2T_4N_L0_UNIFORM_M1M2_W2` | `RA_DEFAULT_2T_4N_L0_UNIFORM_M1M2_W2` | `RA_LOADAWARE_2T_4N_L0_UNIFORM_M1M2_W2` |
| `P2` | `3T_4N_L0_UNIFORM_M1M1M1_W2` | `RA_DEFAULT_3T_4N_L0_UNIFORM_M1M1M1_W2` | `RA_LOADAWARE_3T_4N_L0_UNIFORM_M1M1M1_W2` |

The default campaign replica set is:

```text
A,B,C
```

This produces forty-eight final benchmark runs when all sixteen variants are executed with three replicas.

---

## Scheduler Modes

| Variant family | Scheduler mode | Scheduler name expected in runtime evidence |
|---|---|---|
| `RA_DEFAULT_*` | `kubernetes_default_scheduler` | `default-scheduler` in generated benchmark metadata; `spec.schedulerName` absent in LocalAI manifests. |
| `RA_LOADAWARE_*` | `loadaware_custom_scheduler` | `scheduler-plugins-scheduler` in generated benchmark metadata and LocalAI pod specs. |

The runtime benchmark configuration generated for each variant must include:

```text
schedulerMode
schedulerName
effectiveSchedulerName
```

The resource-aware scheduler runtime configuration must include:

```text
runtimeScenario
reporting
completionGate
freeze
```

---

## Management Node Policy

The C8 provider-backed clusters include a management node role intended for control-plane and management components.

The expected management node policy is:

```text
label: nodepool=management
taint: nodepool=management:NoSchedule
```

Workloads such as `mon-agent` and the custom scheduler are expected to tolerate the management taint and prefer the management node through node affinity. LocalAI tenant workloads are expected to run on worker nodes and should not depend on management-node placement.

Validate the expected node labels and taints after provisioning.

### Windows PowerShell

```powershell
$Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c8-1cp-4w-8c16g\kubeconfig"

kubectl --kubeconfig $Kubeconfig get nodes --show-labels
kubectl --kubeconfig $Kubeconfig describe nodes
```

### Bash

```bash
KUBECONFIG_PATH="./config/cluster-access/generated/proxmox-k3s/c8-1cp-4w-8c16g/kubeconfig"

kubectl --kubeconfig "$KUBECONFIG_PATH" get nodes --show-labels
kubectl --kubeconfig "$KUBECONFIG_PATH" describe nodes
```

The provider-backed cluster validation profile generated for C8 must also validate management-node label and taint expectations.

---

## Execution Safety Rules

Follow these rules before executing C8:

1. Do not execute `config/experimental-cycles/C8.json` directly through `Start-ExperimentalCycle.ps1` as if it were a single provider-backed cycle. Use the campaign runner.
2. Do not introduce hard placement controls into C8 LocalAI manifests.
3. Do not enable NetEm or Chaos Mesh latency injection for C8.
4. Do not enable network-aware scheduler plugins for C8 unless the configuration model is explicitly extended for that purpose.
5. Do not remove `group` and `app` labels from LocalAI deployments, pod templates, or service selectors.
6. Do not skip `mon-agent` or custom scheduler validation during a final C8 execution unless the run is explicitly diagnostic.
7. Do not include cold start, telemetry priming, rollout restart, or readiness waiting inside the official benchmark measurement window.
8. Use `-ConfirmDelete` or `--confirm-delete` only when destructive provider cleanup is intended.
9. Treat unsupported variants as evidence when they are caused by declared capacity, scheduling, rollout, annotation, or workload constraints.

---

## Step 1 — Verify Required Files

### Windows PowerShell

```powershell
$RequiredFiles = @(
  ".\config\experimental-cycles\C8.json",
  ".\config\scenarios\resource-aware-scheduler\RESOURCE_AWARE_SCHEDULER_SCENARIOS_INDEX.json",
  ".\config\scheduler\profiles\CS_C8_LOADAWARE_SECOND_SCHEDULER.json",
  ".\config\mon-agent\profiles\MA_RESOURCE_AWARE.json",
  ".\config\rescheduling\profiles\RS_C8_RESOURCE_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json",
  ".\config\infrastructure\profiles\INFRA_C8_1CP_2W_8C16G.json",
  ".\config\infrastructure\profiles\INFRA_C8_1CP_4W_8C16G.json",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c8-1cp-2w-8c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c8-1cp-4w-8c16g.local.yaml",
  ".\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1",
  ".\scripts\experimental-cycles\run-experimental-campaign.py",
  ".\scripts\validation\scheduler\validate-default-scheduler-manifests.py"
)

foreach ($Path in $RequiredFiles) {
  if (-not (Test-Path $Path)) {
    throw "Missing required C8 file: $Path"
  }
}
```

### Bash

```bash
required_files=(
  "./config/experimental-cycles/C8.json"
  "./config/scenarios/resource-aware-scheduler/RESOURCE_AWARE_SCHEDULER_SCENARIOS_INDEX.json"
  "./config/scheduler/profiles/CS_C8_LOADAWARE_SECOND_SCHEDULER.json"
  "./config/mon-agent/profiles/MA_RESOURCE_AWARE.json"
  "./config/rescheduling/profiles/RS_C8_RESOURCE_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json"
  "./config/infrastructure/profiles/INFRA_C8_1CP_2W_8C16G.json"
  "./config/infrastructure/profiles/INFRA_C8_1CP_4W_8C16G.json"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c8-1cp-2w-8c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c8-1cp-4w-8c16g.local.yaml"
  "./scripts/experimental-cycles/start-experimental-campaign.sh"
  "./scripts/experimental-cycles/run-experimental-campaign.py"
  "./scripts/validation/scheduler/validate-default-scheduler-manifests.py"
)

for path in "${required_files[@]}"; do
  test -f "$path" || { echo "Missing required C8 file: $path" >&2; exit 1; }
done
```

---

## Step 2 — Validate JSON Configuration Syntax

### Windows PowerShell

```powershell
python - <<'PY'
import json
from pathlib import Path
paths = [
    Path("config/experimental-cycles/C8.json"),
    Path("config/scenarios/resource-aware-scheduler/RESOURCE_AWARE_SCHEDULER_SCENARIOS_INDEX.json"),
    *Path("config/scenarios/resource-aware-scheduler").glob("RA_*.json"),
    Path("config/scheduler/profiles/CS_C8_LOADAWARE_SECOND_SCHEDULER.json"),
    Path("config/mon-agent/profiles/MA_RESOURCE_AWARE.json"),
    Path("config/rescheduling/profiles/RS_C8_RESOURCE_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json"),
    Path("config/technical-diagnosis/profiles/TD_C8_RESOURCE_AWARE_SCHEDULER.json"),
    Path("config/reporting/profiles/RP_C8_RESOURCE_AWARE_SCHEDULER.json"),
    Path("config/completion-gate/profiles/CG_C8_RESOURCE_AWARE_SCHEDULER.json"),
    Path("config/freeze/profiles/FR_C8_RESOURCE_AWARE_SCHEDULER.json"),
]
for path in paths:
    with path.open("r", encoding="utf-8") as handle:
        json.load(handle)
    print(f"OK {path}")
PY
```

### Bash

```bash
python3 - <<'PY'
import json
from pathlib import Path
paths = [
    Path("config/experimental-cycles/C8.json"),
    Path("config/scenarios/resource-aware-scheduler/RESOURCE_AWARE_SCHEDULER_SCENARIOS_INDEX.json"),
    *Path("config/scenarios/resource-aware-scheduler").glob("RA_*.json"),
    Path("config/scheduler/profiles/CS_C8_LOADAWARE_SECOND_SCHEDULER.json"),
    Path("config/mon-agent/profiles/MA_RESOURCE_AWARE.json"),
    Path("config/rescheduling/profiles/RS_C8_RESOURCE_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json"),
    Path("config/technical-diagnosis/profiles/TD_C8_RESOURCE_AWARE_SCHEDULER.json"),
    Path("config/reporting/profiles/RP_C8_RESOURCE_AWARE_SCHEDULER.json"),
    Path("config/completion-gate/profiles/CG_C8_RESOURCE_AWARE_SCHEDULER.json"),
    Path("config/freeze/profiles/FR_C8_RESOURCE_AWARE_SCHEDULER.json"),
]
for path in paths:
    with path.open("r", encoding="utf-8") as handle:
        json.load(handle)
    print(f"OK {path}")
PY
```

---

## Step 3 — Validate Resource-Aware Scheduler Manifests

C8 uses resource-aware-scheduler compositions. They must not contain hard pod-placement controls.

### Windows PowerShell

```powershell
python .\scripts\validation\scheduler\validate-default-scheduler-manifests.py `
  --repo-root . `
  --scan-root .\infra\k8s\compositions\resource-aware-scheduler `
  --require-render `
  --output-json .\results\validation\resource-aware-scheduler-c8-manifest-validation.json
```

### Bash

```bash
python3 scripts/validation/scheduler/validate-default-scheduler-manifests.py \
  --repo-root . \
  --scan-root infra/k8s/compositions/resource-aware-scheduler \
  --require-render \
  --output-json results/validation/resource-aware-scheduler-c8-manifest-validation.json
```

The validator name is shared with the default-scheduler validation path, but in C8 it is used to enforce the resource-aware scheduler manifest policy.

---

## Step 4 — Inspect the Scenario Pairing Model

Validate that every logical scenario has exactly one default variant and one load-aware variant.

### Windows PowerShell

```powershell
python - <<'PY'
import json
from collections import defaultdict
from pathlib import Path
index = json.loads(Path("config/scenarios/resource-aware-scheduler/RESOURCE_AWARE_SCHEDULER_SCENARIOS_INDEX.json").read_text(encoding="utf-8"))
logical = defaultdict(list)
for item in index.get("scenarios", []):
    path = Path(item.get("path") or item.get("scenarioConfigPath", ""))
    if not path.exists():
        continue
    payload = json.loads(path.read_text(encoding="utf-8"))
    logical[payload.get("logicalScenarioId")].append((payload.get("schedulerComparisonRole"), payload.get("variantId")))
for key, values in sorted(logical.items()):
    print(key, values)
    roles = sorted(role for role, _ in values)
    if roles != ["default", "loadaware"]:
        raise SystemExit(f"Invalid scheduler pair for {key}: {roles}")
PY
```

### Bash

```bash
python3 - <<'PY'
import json
from collections import defaultdict
from pathlib import Path
index = json.loads(Path("config/scenarios/resource-aware-scheduler/RESOURCE_AWARE_SCHEDULER_SCENARIOS_INDEX.json").read_text(encoding="utf-8"))
logical = defaultdict(list)
for item in index.get("scenarios", []):
    path = Path(item.get("path") or item.get("scenarioConfigPath", ""))
    if not path.exists():
        continue
    payload = json.loads(path.read_text(encoding="utf-8"))
    logical[payload.get("logicalScenarioId")].append((payload.get("schedulerComparisonRole"), payload.get("variantId")))
for key, values in sorted(logical.items()):
    print(key, values)
    roles = sorted(role for role, _ in values)
    if roles != ["default", "loadaware"]:
        raise SystemExit(f"Invalid scheduler pair for {key}: {roles}")
PY
```

---

## Step 5 — Produce a Dry-Run Campaign Plan

A dry run verifies campaign expansion, generated runtime configuration paths, provider binding resolution, and runtime command construction without creating infrastructure.

### Windows PowerShell

```powershell
$CycleConfig = ".\config\experimental-cycles\C8.json"
$RunId = "C8_resource_aware_scheduler_dry_run"

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig $CycleConfig `
  -RunId $RunId `
  -BaselineReplicas "A,B,C" `
  -DryRun `
  -SkipDelete
```

### Bash

```bash
CYCLE_CONFIG="./config/experimental-cycles/C8.json"
RUN_ID="C8_resource_aware_scheduler_dry_run"

./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --run-id "$RUN_ID" \
  --baseline-replicas "A,B,C" \
  --dry-run \
  --skip-delete
```

After the dry run, inspect:

```text
results/experimental-cycles/C8/execution/
results/experimental-cycles/C8/execution/generated-runtime-configs/
```

Generated runtime configs must contain `runtimeScenario`, `reporting`, `completionGate`, and `freeze`, and must not use a top-level legacy `baseline` section for resource-aware-scheduler variants.

---

## Step 6 — Execute the Complete C8 Campaign

Use this command when the local provider YAML files have been reviewed, cluster deletion is expected by the lifecycle policy, and the environment is ready for a full campaign.

### Windows PowerShell

```powershell
$CycleConfig = ".\config\experimental-cycles\C8.json"
$RunId = "C8_resource_aware_scheduler"

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig $CycleConfig `
  -RunId $RunId `
  -BaselineReplicas "A,B,C" `
  -ConfirmDelete `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
CYCLE_CONFIG="./config/experimental-cycles/C8.json"
RUN_ID="C8_resource_aware_scheduler"

./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config "$CYCLE_CONFIG" \
  --run-id "$RUN_ID" \
  --baseline-replicas "A,B,C" \
  --confirm-delete \
  --force-freeze \
  --write-latest-aliases
```

Do not use `--skip-completion-gate` or `--skip-freeze` for the final campaign unless the run is explicitly partial or diagnostic.

---

## Step 7 — Inspect Campaign Execution Outputs

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C8\execution -Recurse | Select-Object FullName
Get-ChildItem .\results\experimental-cycles\C8\execution\generated-runtime-configs
```

### Bash

```bash
find ./results/experimental-cycles/C8/execution -maxdepth 4 -type f | sort
find ./results/experimental-cycles/C8/execution/generated-runtime-configs -maxdepth 2 -type f | sort
```

Each variant should have a generated runtime config under:

```text
results/experimental-cycles/C8/execution/generated-runtime-configs/<variant-id>/<variant-id>.cycle.json
```

---

## Step 8 — Inspect Scheduler Decision Evidence

Scheduler decision evidence must exist for both default and load-aware variants.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C8 -Recurse -Filter resource-aware-scheduler-decision-evidence.json |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C8 -name resource-aware-scheduler-decision-evidence.json -type f | sort
```

For load-aware variants, confirm that scheduled pods were associated with:

```text
scheduler-plugins-scheduler
```

For default variants, confirm that LocalAI manifests did not set `spec.schedulerName` and that runtime metadata classifies the effective scheduler as:

```text
default-scheduler
```

---

## Step 9 — Inspect mon-agent Evidence

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C8\observability\mon-agent -Recurse |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C8/observability/mon-agent -maxdepth 5 -type f | sort
```

The mon-agent validation evidence must confirm the required runtime annotations:

```text
cpu-usage
memory-usage
```

on nodes and selected LocalAI deployments. Optional annotations such as `disk-bandwidth` and `network-bandwidth` may be captured when available, but they are not required optimization inputs for C8.

---

## Step 10 — Inspect Custom Scheduler Evidence

Load-aware variants must install and validate the custom second scheduler.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C8\scheduler\custom-scheduler -Recurse |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C8/scheduler/custom-scheduler -maxdepth 5 -type f | sort
```

The custom scheduler evidence must confirm:

```text
scheduler-plugins-scheduler
LoadAwareResourcesBalancedAllocation
```

The second scheduler must affect only workloads that explicitly set `spec.schedulerName` to `scheduler-plugins-scheduler`.

---

## Step 11 — Inspect Rescheduling Evidence

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C8\rescheduling -Recurse |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C8/rescheduling -maxdepth 5 -type f | sort
```

Rescheduling evidence must preserve:

1. pre-redeployment placement and annotation snapshot;
2. annotation gate status;
3. rollout restart status;
4. post-redeployment placement and annotation snapshot;
5. readiness status before the official measurement window.

---

## Step 12 — Inspect Benchmark Outputs

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C8\benchmark\resource-aware-scheduler -Recurse |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C8/benchmark/resource-aware-scheduler -maxdepth 5 -type f | sort
```

For each variant and replica, inspect the Locust CSV files, protocol artifacts, metric-set artifacts, and scenario status files.

Benchmark artifacts must preserve scheduler-aware metadata and must not label load-aware variants as default-scheduler executions.

---

## Step 13 — Inspect Diagnosis, Reporting, Completion Gate, and Freeze

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C8\diagnosis -Recurse | Select-Object FullName
Get-ChildItem .\results\experimental-cycles\C8\reporting -Recurse | Select-Object FullName
Get-ChildItem .\results\experimental-cycles\C8\completion-gate -Recurse | Select-Object FullName
Get-ChildItem .\results\experimental-cycles\C8\freeze -Recurse | Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C8/diagnosis -maxdepth 5 -type f | sort
find ./results/experimental-cycles/C8/reporting -maxdepth 5 -type f | sort
find ./results/experimental-cycles/C8/completion-gate -maxdepth 5 -type f | sort
find ./results/experimental-cycles/C8/freeze -maxdepth 5 -type f | sort
```

The C8 completion gate should evaluate the campaign as a paired scheduler evaluation. A final complete execution should provide enough evidence for default/load-aware pairing, scheduler decision capture, benchmark outputs, diagnosis, reporting, and freeze.

---

## Optional — Direct Variant Execution

The preferred execution surface is the campaign runner. Direct execution of a generated runtime config is useful only for diagnosis or targeted reruns.

### Windows PowerShell

```powershell
$VariantConfig = ".\results\experimental-cycles\C8\execution\generated-runtime-configs\RA_LOADAWARE_1T_2N_L0_UNIFORM_M1_W2\RA_LOADAWARE_1T_2N_L0_UNIFORM_M1_W2.cycle.json"

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCycle.ps1 `
  -CycleConfig $VariantConfig `
  -ExecutionScope provider-backed-cycle `
  -RunId "C8_direct_variant_diagnostic" `
  -ConfirmDelete `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
VARIANT_CONFIG="./results/experimental-cycles/C8/execution/generated-runtime-configs/RA_LOADAWARE_1T_2N_L0_UNIFORM_M1_W2/RA_LOADAWARE_1T_2N_L0_UNIFORM_M1_W2.cycle.json"

./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$VARIANT_CONFIG" \
  --execution-scope provider-backed-cycle \
  --run-id "C8_direct_variant_diagnostic" \
  --confirm-delete \
  --force-freeze \
  --write-latest-aliases
```

Do not treat a single direct variant run as a complete C8 campaign result.

---

## Interpretation Checklist

Use the following checklist when reading C8 outputs:

- Does each logical scenario have both default and load-aware variants?
- Are workload, infrastructure, traffic, model mix, labels, and rescheduling policy constant within each pair?
- Does the default variant omit `spec.schedulerName`?
- Does the load-aware variant use `scheduler-plugins-scheduler`?
- Did `mon-agent` produce required CPU and memory annotations before controlled redeployment?
- Did controlled redeployment occur before the official measurement window?
- Did scheduler decision evidence capture pod-to-node placement after redeployment?
- Are unsupported scenarios explained by resource, scheduling, rollout, annotation, or workload constraints?
- Does reporting compare default and load-aware variants as paired scenarios?
- Does the freeze snapshot preserve all relevant evidence?

---

## Readiness Checklist

C8 is ready for final execution when:

- `proxmox-k3s` is available;
- Helm is available for custom scheduler installation;
- C8 local provider YAML files are reviewed and ignored by Git;
- C8 cluster validation checks management-node label and taint expectations;
- resource-aware scheduler manifests pass static validation;
- `mon-agent` profile and scheduler profile are present;
- C8 dry-run campaign produces all sixteen generated runtime configs;
- destructive deletion is intentional and `-ConfirmDelete` or `--confirm-delete` is supplied;
- the operator is ready to regenerate all C8 result artifacts from current source configuration.

---

## Next Runbook

Continue with:

```text
docs/runbooks/11-network-aware-scheduler-c9-execution.md
```

C9 extends this comparison by adding gateway-routed traffic, Mentat network telemetry, and the `NetworkAwareLocalAi` plugin.
