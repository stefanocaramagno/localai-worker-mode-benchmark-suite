# Provider-Backed C2-C6 Campaign Execution

## Purpose

This runbook describes how to execute and regenerate the comparative provider-backed campaigns `C2` through `C6`.

The campaigns extend the provider-backed baseline execution model by running multiple controlled variants. Each campaign changes one experimental dimension while keeping the remaining dimensions fixed as much as possible. The objective is to produce a complete, reproducible artifact set for resource variation, node-count variation, placement variation, latency injection, and multi-tenancy evaluation.

The campaigns covered by this runbook are:

| Cycle | Campaign | Primary varied dimension |
|---|---|---|
| `C2` | Resource variation | Worker-node CPU and memory capacity |
| `C3` | Node-count variation | Number of provider-backed worker nodes |
| `C4` | Placement variation | LocalAI server and RPC-worker placement profile |
| `C5` | Latency injection | Controlled network-latency profile |
| `C6` | Multi-tenancy | Tenant topology, co-tenant model mix, and co-tenant placement |

This runbook assumes that the local environment, access material, provider lifecycle model, configuration taxonomy, fixed-cluster execution path, and provider-backed baseline path are already understood from the preceding runbooks.

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

## Campaign Execution Model

Each comparative campaign follows this execution model:

```text
campaign cycle profile
→ campaign variants
→ generated runtime profiles for each variant
→ optional stale-cluster pre-cleanup
→ provider-backed variant execution
→ optional post-variant cluster deletion
→ campaign-level technical diagnosis
→ campaign-level reporting
→ global reporting-site refresh
→ campaign-level completion gate
→ campaign-level freeze
```

For each variant, the campaign runner materializes a runtime provider-backed cycle profile under the campaign execution root. That generated variant cycle is then executed by the provider-backed cycle runner.

This means that `C2` through `C6` are not simple loops around a benchmark command. They are campaign-level orchestrations that generate per-variant runtime configuration, run provider-backed infrastructure lifecycle operations, deploy LocalAI, execute benchmark replicas, capture evidence, and then aggregate post-processing artifacts at campaign level.

---

## Campaign Scope Summary

### C2 — Resource Variation

`C2` varies worker-node resource capacity while preserving the intended LocalAI model, workload, worker count, and placement profile.

| Variant | Scenario profile | Infrastructure profile | Intended comparison role |
|---|---|---|---|
| `RV_4C8G` | `config/scenarios/resource-variation/RV_4C8G.json` | `INFRA_C2_1CP_2W_4C8G` | Lower CPU and lower memory resource envelope |
| `RV_4C16G` | `config/scenarios/resource-variation/RV_4C16G.json` | `INFRA_C2_1CP_2W_4C16G` | Lower CPU with baseline memory envelope |
| `RV_8C16G` | `config/scenarios/resource-variation/RV_8C16G.json` | `INFRA_C2_1CP_2W_8C16G` | Reference resource envelope for the campaign |

### C3 — Node-Count Variation

`C3` varies the number of provider-backed worker nodes while preserving per-node resource capacity and the intended application-side topology.

| Variant | Scenario profile | Infrastructure profile | Placement profile |
|---|---|---|---|
| `NC_2N` | `config/scenarios/node-count-variation/NC_2N.json` | `INFRA_C3_1CP_2W_8C16G` | `PL_SPREAD_WORKERS` |
| `NC_3N` | `config/scenarios/node-count-variation/NC_3N.json` | `INFRA_C3_1CP_3W_8C16G` | `PL_SPREAD_WORKERS` |
| `NC_4N` | `config/scenarios/node-count-variation/NC_4N.json` | `INFRA_C3_1CP_4W_8C16G` | `PL_SPREAD_WORKERS` |

### C4 — Placement Variation

`C4` keeps the infrastructure, model, workload, and LocalAI worker count fixed while varying the placement profile.

| Variant | Scenario profile | Placement profile | Intended comparison role |
|---|---|---|---|
| `PLC_COLOCATED` | `config/scenarios/placement-variation/PLC_COLOCATED.json` | `PL_COLOCATED` | Co-locate LocalAI server and RPC workers |
| `PLC_DISTRIBUTED_TWO_NODE` | `config/scenarios/placement-variation/PLC_DISTRIBUTED_TWO_NODE.json` | `PL_DISTRIBUTED_TWO_NODE` | Distribute components across two provider worker nodes |
| `PLC_SPREAD_WORKERS` | `config/scenarios/placement-variation/PLC_SPREAD_WORKERS.json` | `PL_SPREAD_WORKERS` | Spread RPC workers across the worker-node pool |
| `PLC_SERVER_SEPARATED` | `config/scenarios/placement-variation/PLC_SERVER_SEPARATED.json` | `PL_SERVER_SEPARATED` | Separate the API server from selected RPC workers |
| `PLC_BALANCED_STATIC` | `config/scenarios/placement-variation/PLC_BALANCED_STATIC.json` | `PL_BALANCED_STATIC` | Use a static balanced placement policy |

### C5 — Latency Injection

`C5` keeps infrastructure, model, workload, LocalAI worker count, and placement fixed while varying the controlled latency profile.

| Variant | Scenario profile | Latency profile | Intended comparison role |
|---|---|---|---|
| `LI_L0_NONE` | `config/scenarios/latency-injection/LI_L0_NONE.json` | `L0_NONE` | No artificial latency |
| `LI_L1_EDGE_NEAR` | `config/scenarios/latency-injection/LI_L1_EDGE_NEAR.json` | `L1_EDGE_NEAR` | Near-edge latency envelope |
| `LI_L2_EDGE_REMOTE` | `config/scenarios/latency-injection/LI_L2_EDGE_REMOTE.json` | `L2_EDGE_REMOTE` | Remote-edge latency envelope |
| `LI_L3_EXTREME` | `config/scenarios/latency-injection/LI_L3_EXTREME.json` | `L3_EXTREME` | Extreme latency envelope |

### C6 — Multi-Tenancy

`C6` evaluates LocalAI tenant-like coexistence patterns while keeping the underlying infrastructure and primary benchmark workload controlled.

| Variant | Scenario profile | Intended comparison role |
|---|---|---|
| `MT_SINGLE_TENANT_REFERENCE` | `config/scenarios/multi-tenancy/MT_SINGLE_TENANT_REFERENCE.json` | Single-tenant reference execution |
| `MT_TWO_TENANTS_SEPARATED` | `config/scenarios/multi-tenancy/MT_TWO_TENANTS_SEPARATED.json` | Two tenants separated by placement and namespace design |
| `MT_TWO_TENANTS_MIXED_MODELS` | `config/scenarios/multi-tenancy/MT_TWO_TENANTS_MIXED_MODELS.json` | Two tenants using different model profiles |
| `MT_TWO_TENANTS_SHARED_NODEPOOL` | `config/scenarios/multi-tenancy/MT_TWO_TENANTS_SHARED_NODEPOOL.json` | Aggressive shared-nodepool coexistence |

---

## Canonical Campaign Inputs

The campaign runner uses the following canonical cycle profiles:

| Cycle | Cycle profile | Scenario family | Default replicas |
|---|---|---|---|
| `C2` | `config/experimental-cycles/C2.json` | `resource-variation` | `A,B,C` |
| `C3` | `config/experimental-cycles/C3.json` | `node-count-variation` | `A,B,C` |
| `C4` | `config/experimental-cycles/C4.json` | `placement-variation` | `A,B,C` |
| `C5` | `config/experimental-cycles/C5.json` | `latency-injection` | `A,B,C` |
| `C6` | `config/experimental-cycles/C6.json` | `multi-tenancy` | `A,B,C` |

All five campaigns are provider-backed. They require `proxmox-k3s` provider bindings, local provider YAML files, generated kubeconfig paths, and infrastructure profiles declared by the selected campaign variants.

---

## Canonical Output Roots

A complete regeneration writes campaign-level artifacts under the following roots.

| Cycle | Execution root | Benchmark root | Diagnosis root | Reporting root | Completion gate root | Freeze root |
|---|---|---|---|---|---|---|
| `C2` | `results/experimental-cycles/C2/execution` | `results/experimental-cycles/C2/benchmark/resource-variation` | `results/experimental-cycles/C2/diagnosis` | `results/experimental-cycles/C2/reporting` | `results/experimental-cycles/C2/completion-gate` | `results/experimental-cycles/C2/freeze` |
| `C3` | `results/experimental-cycles/C3/execution` | `results/experimental-cycles/C3/benchmark/node-count-variation` | `results/experimental-cycles/C3/diagnosis` | `results/experimental-cycles/C3/reporting` | `results/experimental-cycles/C3/completion-gate` | `results/experimental-cycles/C3/freeze` |
| `C4` | `results/experimental-cycles/C4/execution` | `results/experimental-cycles/C4/benchmark/placement-variation` | `results/experimental-cycles/C4/diagnosis` | `results/experimental-cycles/C4/reporting` | `results/experimental-cycles/C4/completion-gate` | `results/experimental-cycles/C4/freeze` |
| `C5` | `results/experimental-cycles/C5/execution` | `results/experimental-cycles/C5/benchmark/latency-injection` | `results/experimental-cycles/C5/diagnosis` | `results/experimental-cycles/C5/reporting` | `results/experimental-cycles/C5/completion-gate` | `results/experimental-cycles/C5/freeze` |
| `C6` | `results/experimental-cycles/C6/execution` | `results/experimental-cycles/C6/benchmark/multi-tenancy` | `results/experimental-cycles/C6/diagnosis` | `results/experimental-cycles/C6/reporting` | `results/experimental-cycles/C6/completion-gate` | `results/experimental-cycles/C6/freeze` |

Each campaign also writes generated per-variant runtime configuration under:

```text
results/experimental-cycles/<cycle>/execution/generated-runtime-configs/
```

Those generated runtime profiles are execution artifacts. They are not the source configuration layer.

---

## Execution Safety Rules

Before running `C2` through `C6`, observe the following rules.

1. Run `C1` successfully before executing comparative campaigns.
2. Review all local provider YAML files before real provisioning operations.
3. Treat provider-backed delete operations as destructive. Use delete confirmation only when the targeted cluster names, VM identifiers, IP ranges, and Proxmox nodes have been verified.
4. Do not rely on the default Kubernetes context. Campaign runners must use the kubeconfig paths declared by the provider-backed cycle configuration.
5. Keep `C2`–`C6` artifacts separated from `C0` and `C1` artifacts.
6. Use `--dry-run` or `-DryRun` before real execution whenever provider-local configuration has changed.
7. Use `--continue-on-failure` or `-ContinueOnFailure` only to preserve evidence across variants. It must not be used to ignore infrastructure mistakes.
8. Use metrics-warning bypass flags only when Metrics API warnings are explicitly non-blocking for the intended run.
9. Unsupported scenarios are valid methodological outcomes only when the generated artifacts identify the unsupported stage and preserve the corresponding evidence.
10. Do not manually edit generated runtime profiles under `results/experimental-cycles/<cycle>/execution/generated-runtime-configs/`.

---

## Step 1 — Verify Campaign Entry Points

Validate that the campaign runner entry points are available.

### Windows PowerShell

```powershell
$RequiredPaths = @(
  ".\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1",
  ".\scripts\experimental-cycles\start-experimental-campaign.sh",
  ".\scripts\experimental-cycles\run-experimental-campaign.py",
  ".\scripts\experimental-cycles\run-provider-backed-cycle.py",
  ".\scripts\analysis\generate-technical-diagnosis.py",
  ".\scripts\analysis\generate-reporting.py",
  ".\scripts\analysis\generate-reporting-site.py",
  ".\scripts\analysis\evaluate-completion-gate.py",
  ".\scripts\analysis\freeze-experimental-cycle.py"
)

$RequiredPaths | ForEach-Object {
  if (-not (Test-Path $_)) {
    throw "Missing required campaign file: $_"
  }
}
```

### Bash

```bash
required_paths=(
  "./scripts/experimental-cycles/Start-ExperimentalCampaign.ps1"
  "./scripts/experimental-cycles/start-experimental-campaign.sh"
  "./scripts/experimental-cycles/run-experimental-campaign.py"
  "./scripts/experimental-cycles/run-provider-backed-cycle.py"
  "./scripts/analysis/generate-technical-diagnosis.py"
  "./scripts/analysis/generate-reporting.py"
  "./scripts/analysis/generate-reporting-site.py"
  "./scripts/analysis/evaluate-completion-gate.py"
  "./scripts/analysis/freeze-experimental-cycle.py"
)

for path in "${required_paths[@]}"; do
  test -e "$path" || { echo "Missing required campaign file: $path" >&2; exit 1; }
done
```

---

## Step 2 — Verify Campaign Profiles

Validate that all campaign cycle profiles and campaign-level post-processing profiles exist.

### Windows PowerShell

```powershell
$RequiredPaths = @(
  ".\config\experimental-cycles\C2.json",
  ".\config\experimental-cycles\C3.json",
  ".\config\experimental-cycles\C4.json",
  ".\config\experimental-cycles\C5.json",
  ".\config\experimental-cycles\C6.json",
  ".\config\technical-diagnosis\profiles\TD_C2_RESOURCE_VARIATION.json",
  ".\config\technical-diagnosis\profiles\TD_C3_NODE_COUNT_VARIATION.json",
  ".\config\technical-diagnosis\profiles\TD_C4_PLACEMENT_VARIATION.json",
  ".\config\technical-diagnosis\profiles\TD_C5_LATENCY_INJECTION.json",
  ".\config\technical-diagnosis\profiles\TD_C6_MULTI_TENANCY.json",
  ".\config\reporting\profiles\RP_C2_RESOURCE_VARIATION.json",
  ".\config\reporting\profiles\RP_C3_NODE_COUNT_VARIATION.json",
  ".\config\reporting\profiles\RP_C4_PLACEMENT_VARIATION.json",
  ".\config\reporting\profiles\RP_C5_LATENCY_INJECTION.json",
  ".\config\reporting\profiles\RP_C6_MULTI_TENANCY.json",
  ".\config\completion-gate\profiles\CG_C2_RESOURCE_VARIATION.json",
  ".\config\completion-gate\profiles\CG_C3_NODE_COUNT_VARIATION.json",
  ".\config\completion-gate\profiles\CG_C4_PLACEMENT_VARIATION.json",
  ".\config\completion-gate\profiles\CG_C5_LATENCY_INJECTION.json",
  ".\config\completion-gate\profiles\CG_C6_MULTI_TENANCY.json",
  ".\config\freeze\profiles\FR_C2_RESOURCE_VARIATION.json",
  ".\config\freeze\profiles\FR_C3_NODE_COUNT_VARIATION.json",
  ".\config\freeze\profiles\FR_C4_PLACEMENT_VARIATION.json",
  ".\config\freeze\profiles\FR_C5_LATENCY_INJECTION.json",
  ".\config\freeze\profiles\FR_C6_MULTI_TENANCY.json"
)

$RequiredPaths | ForEach-Object {
  if (-not (Test-Path $_)) {
    throw "Missing required campaign profile: $_"
  }
}
```

### Bash

```bash
required_paths=(
  "./config/experimental-cycles/C2.json"
  "./config/experimental-cycles/C3.json"
  "./config/experimental-cycles/C4.json"
  "./config/experimental-cycles/C5.json"
  "./config/experimental-cycles/C6.json"
  "./config/technical-diagnosis/profiles/TD_C2_RESOURCE_VARIATION.json"
  "./config/technical-diagnosis/profiles/TD_C3_NODE_COUNT_VARIATION.json"
  "./config/technical-diagnosis/profiles/TD_C4_PLACEMENT_VARIATION.json"
  "./config/technical-diagnosis/profiles/TD_C5_LATENCY_INJECTION.json"
  "./config/technical-diagnosis/profiles/TD_C6_MULTI_TENANCY.json"
  "./config/reporting/profiles/RP_C2_RESOURCE_VARIATION.json"
  "./config/reporting/profiles/RP_C3_NODE_COUNT_VARIATION.json"
  "./config/reporting/profiles/RP_C4_PLACEMENT_VARIATION.json"
  "./config/reporting/profiles/RP_C5_LATENCY_INJECTION.json"
  "./config/reporting/profiles/RP_C6_MULTI_TENANCY.json"
  "./config/completion-gate/profiles/CG_C2_RESOURCE_VARIATION.json"
  "./config/completion-gate/profiles/CG_C3_NODE_COUNT_VARIATION.json"
  "./config/completion-gate/profiles/CG_C4_PLACEMENT_VARIATION.json"
  "./config/completion-gate/profiles/CG_C5_LATENCY_INJECTION.json"
  "./config/completion-gate/profiles/CG_C6_MULTI_TENANCY.json"
  "./config/freeze/profiles/FR_C2_RESOURCE_VARIATION.json"
  "./config/freeze/profiles/FR_C3_NODE_COUNT_VARIATION.json"
  "./config/freeze/profiles/FR_C4_PLACEMENT_VARIATION.json"
  "./config/freeze/profiles/FR_C5_LATENCY_INJECTION.json"
  "./config/freeze/profiles/FR_C6_MULTI_TENANCY.json"
)

for path in "${required_paths[@]}"; do
  test -e "$path" || { echo "Missing required campaign profile: $path" >&2; exit 1; }
done
```

---

## Step 3 — Validate Campaign JSON Syntax

Validate that the campaign cycle profiles are syntactically valid JSON.

### Windows PowerShell

```powershell
python -c "import json, pathlib; [json.load(open(p, encoding='utf-8-sig')) for p in ['config/experimental-cycles/C2.json','config/experimental-cycles/C3.json','config/experimental-cycles/C4.json','config/experimental-cycles/C5.json','config/experimental-cycles/C6.json']]; print('Campaign JSON syntax validation completed.')"
```

### Bash

```bash
python3 -c "import json, pathlib; [json.load(open(p, encoding='utf-8-sig')) for p in ['config/experimental-cycles/C2.json','config/experimental-cycles/C3.json','config/experimental-cycles/C4.json','config/experimental-cycles/C5.json','config/experimental-cycles/C6.json']]; print('Campaign JSON syntax validation completed.')"
```

---

## Step 4 — Inspect Campaign Variants

Print the variants declared by each campaign before executing any provider-backed operation.

### Windows PowerShell

```powershell
python -c "import json; import pathlib;\
files=['config/experimental-cycles/C2.json','config/experimental-cycles/C3.json','config/experimental-cycles/C4.json','config/experimental-cycles/C5.json','config/experimental-cycles/C6.json'];\
[print('\n'+d['cycleId'], d['cycleName'], '\n  ' + '\n  '.join(v['variantId'] for v in d.get('campaign',{}).get('variants',[]))) for d in (json.load(open(f, encoding='utf-8-sig')) for f in files)]"
```

### Bash

```bash
python3 -c "import json; import pathlib;\
files=['config/experimental-cycles/C2.json','config/experimental-cycles/C3.json','config/experimental-cycles/C4.json','config/experimental-cycles/C5.json','config/experimental-cycles/C6.json'];\
[print('\n'+d['cycleId'], d['cycleName'], '\n  ' + '\n  '.join(v['variantId'] for v in d.get('campaign',{}).get('variants',[]))) for d in (json.load(open(f, encoding='utf-8-sig')) for f in files)]"
```

Expected variant groups:

```text
C2: RV_4C8G, RV_4C16G, RV_8C16G
C3: NC_2N, NC_3N, NC_4N
C4: PLC_COLOCATED, PLC_DISTRIBUTED_TWO_NODE, PLC_SPREAD_WORKERS, PLC_SERVER_SEPARATED, PLC_BALANCED_STATIC
C5: LI_L0_NONE, LI_L1_EDGE_NEAR, LI_L2_EDGE_REMOTE, LI_L3_EXTREME
C6: MT_SINGLE_TENANT_REFERENCE, MT_TWO_TENANTS_SEPARATED, MT_TWO_TENANTS_MIXED_MODELS, MT_TWO_TENANTS_SHARED_NODEPOOL
```

---

## Step 5 — Verify Local Provider Configuration Coverage

Each provider-backed variant references a local `proxmox-k3s` YAML file. These local files contain environment-specific values and must be reviewed before real execution.

The following command prints the local provider config required by every campaign variant and marks missing files.

### Windows PowerShell

```powershell
python -c "import json, pathlib;\
files=['config/experimental-cycles/C2.json','config/experimental-cycles/C3.json','config/experimental-cycles/C4.json','config/experimental-cycles/C5.json','config/experimental-cycles/C6.json'];\
missing=[];\
print('Required local provider configs:');\
[print(f'{d[\"cycleId\"]}/{v[\"variantId\"]}: {p} ' + ('[OK]' if pathlib.Path(p).exists() else '[MISSING]')) or (missing.append(p) if not pathlib.Path(p).exists() else None) for d in (json.load(open(f, encoding='utf-8-sig')) for f in files) for v in d.get('campaign',{}).get('variants',[]) for p in [v.get('providerConfigLocalPath')]];\
raise SystemExit(1 if missing else 0)"
```

### Bash

```bash
python3 -c "import json, pathlib;\
files=['config/experimental-cycles/C2.json','config/experimental-cycles/C3.json','config/experimental-cycles/C4.json','config/experimental-cycles/C5.json','config/experimental-cycles/C6.json'];\
missing=[];\
print('Required local provider configs:');\
[print(f'{d[\"cycleId\"]}/{v[\"variantId\"]}: {p} ' + ('[OK]' if pathlib.Path(p).exists() else '[MISSING]')) or (missing.append(p) if not pathlib.Path(p).exists() else None) for d in (json.load(open(f, encoding='utf-8-sig')) for f in files) for v in d.get('campaign',{}).get('variants',[]) for p in [v.get('providerConfigLocalPath')]];\
raise SystemExit(1 if missing else 0)"
```

If a required local provider config is missing, copy the corresponding `.example.yaml` file into `config/infrastructure/providers/proxmox-k3s/local/`, rename it to the expected `.local.yaml` path, and adapt all environment-specific values before running the campaign.

---

## Step 6 — Review Provider Config Paths Before Real Execution

Print example config, local config, kubeconfig path, and lifecycle mode for every variant.

### Windows PowerShell

```powershell
python -c "import json; files=['config/experimental-cycles/C2.json','config/experimental-cycles/C3.json','config/experimental-cycles/C4.json','config/experimental-cycles/C5.json','config/experimental-cycles/C6.json'];\
[print('\n'.join(['', d['cycleId'] + ' ' + d['cycleName']] + [f\"- {v['variantId']}: example={v.get('providerConfigExamplePath')} | local={v.get('providerConfigLocalPath')} | kubeconfig={v.get('kubeconfigPath')} | lifecycle={v.get('clusterLifecycleMode')}\" for v in d.get('campaign',{}).get('variants',[])])) for d in (json.load(open(f, encoding='utf-8-sig')) for f in files)]"
```

### Bash

```bash
python3 -c "import json; files=['config/experimental-cycles/C2.json','config/experimental-cycles/C3.json','config/experimental-cycles/C4.json','config/experimental-cycles/C5.json','config/experimental-cycles/C6.json'];\
[print('\n'.join(['', d['cycleId'] + ' ' + d['cycleName']] + [f\"- {v['variantId']}: example={v.get('providerConfigExamplePath')} | local={v.get('providerConfigLocalPath')} | kubeconfig={v.get('kubeconfigPath')} | lifecycle={v.get('clusterLifecycleMode')}\" for v in d.get('campaign',{}).get('variants',[])])) for d in (json.load(open(f, encoding='utf-8-sig')) for f in files)]"
```

Do not proceed if any local provider YAML points to an unexpected Proxmox node, VM identifier range, IP range, storage pool, network bridge, gateway, DNS configuration, template name, or kubeconfig output path.

---

## Step 7 — Perform a Dry Run for Each Campaign

A dry run writes an execution plan without running the provider-backed runtime commands.

### Windows PowerShell

```powershell
$Campaigns = @(
  ".\config\experimental-cycles\C2.json",
  ".\config\experimental-cycles\C3.json",
  ".\config\experimental-cycles\C4.json",
  ".\config\experimental-cycles\C5.json",
  ".\config\experimental-cycles\C6.json"
)

foreach ($Campaign in $Campaigns) {
  .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
    -CycleConfig $Campaign `
    -ToolPath "proxmox-k3s" `
    -DryRun `
    -ConfirmDelete `
    -AllowMetricsWarning `
    -WriteLatestAliases
}
```

### Bash

```bash
campaigns=(
  "./config/experimental-cycles/C2.json"
  "./config/experimental-cycles/C3.json"
  "./config/experimental-cycles/C4.json"
  "./config/experimental-cycles/C5.json"
  "./config/experimental-cycles/C6.json"
)

for campaign in "${campaigns[@]}"; do
  ./scripts/experimental-cycles/start-experimental-campaign.sh \
    --cycle-config "$campaign" \
    --tool-path proxmox-k3s \
    --dry-run \
    --confirm-delete \
    --allow-metrics-warning \
    --write-latest-aliases
done
```

After this step, inspect the dry-run campaign manifests under:

```text
results/experimental-cycles/<cycle>/execution/
```

---

## Step 8 — Execute C2 Resource Variation

Run `C2` after all resource-variation local provider YAML files have been reviewed.

### Windows PowerShell

```powershell
.\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C2.json `
  -ToolPath "proxmox-k3s" `
  -ConfirmDelete `
  -AllowMetricsWarning `
  -ContinueOnFailure `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config ./config/experimental-cycles/C2.json \
  --tool-path proxmox-k3s \
  --confirm-delete \
  --allow-metrics-warning \
  --continue-on-failure \
  --force-freeze \
  --write-latest-aliases
```

Expected campaign-level outputs:

```text
results/experimental-cycles/C2/execution/latest-campaign-execution-manifest.json
results/experimental-cycles/C2/diagnosis/
results/experimental-cycles/C2/reporting/
results/experimental-cycles/C2/completion-gate/latest-completion-gate-manifest.json
results/experimental-cycles/C2/freeze/
```

---

## Step 9 — Execute C3 Node-Count Variation

Run `C3` after all node-count local provider YAML files have been reviewed.

### Windows PowerShell

```powershell
.\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C3.json `
  -ToolPath "proxmox-k3s" `
  -ConfirmDelete `
  -AllowMetricsWarning `
  -ContinueOnFailure `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config ./config/experimental-cycles/C3.json \
  --tool-path proxmox-k3s \
  --confirm-delete \
  --allow-metrics-warning \
  --continue-on-failure \
  --force-freeze \
  --write-latest-aliases
```

Expected campaign-level outputs:

```text
results/experimental-cycles/C3/execution/latest-campaign-execution-manifest.json
results/experimental-cycles/C3/diagnosis/
results/experimental-cycles/C3/reporting/
results/experimental-cycles/C3/completion-gate/latest-completion-gate-manifest.json
results/experimental-cycles/C3/freeze/
```

---

## Step 10 — Execute C4 Placement Variation

Run `C4` after the 4-worker provider-backed local provider YAML and placement profiles have been reviewed.

### Windows PowerShell

```powershell
.\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C4.json `
  -ToolPath "proxmox-k3s" `
  -ConfirmDelete `
  -AllowMetricsWarning `
  -ContinueOnFailure `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config ./config/experimental-cycles/C4.json \
  --tool-path proxmox-k3s \
  --confirm-delete \
  --allow-metrics-warning \
  --continue-on-failure \
  --force-freeze \
  --write-latest-aliases
```

Expected campaign-level outputs:

```text
results/experimental-cycles/C4/execution/latest-campaign-execution-manifest.json
results/experimental-cycles/C4/diagnosis/
results/experimental-cycles/C4/reporting/
results/experimental-cycles/C4/completion-gate/latest-completion-gate-manifest.json
results/experimental-cycles/C4/freeze/
```

---

## Step 11 — Execute C5 Latency Injection

Run `C5` after the latency profiles and the latency-application script path have been reviewed.

### Windows PowerShell

```powershell
.\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C5.json `
  -ToolPath "proxmox-k3s" `
  -ConfirmDelete `
  -AllowMetricsWarning `
  -ContinueOnFailure `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config ./config/experimental-cycles/C5.json \
  --tool-path proxmox-k3s \
  --confirm-delete \
  --allow-metrics-warning \
  --continue-on-failure \
  --force-freeze \
  --write-latest-aliases
```

Expected campaign-level outputs:

```text
results/experimental-cycles/C5/execution/latest-campaign-execution-manifest.json
results/experimental-cycles/C5/diagnosis/
results/experimental-cycles/C5/reporting/
results/experimental-cycles/C5/completion-gate/latest-completion-gate-manifest.json
results/experimental-cycles/C5/freeze/
```

Latency-injection evidence is stored under each variant root, for example:

```text
results/experimental-cycles/C5/variants/<variant-id>/latency-injection/
```

---

## Step 12 — Execute C6 Multi-Tenancy

Run `C6` after tenancy profiles, namespaces, topology directories, model assignments, and rollout targets have been reviewed.

### Windows PowerShell

```powershell
.\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C6.json `
  -ToolPath "proxmox-k3s" `
  -ConfirmDelete `
  -AllowMetricsWarning `
  -ContinueOnFailure `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config ./config/experimental-cycles/C6.json \
  --tool-path proxmox-k3s \
  --confirm-delete \
  --allow-metrics-warning \
  --continue-on-failure \
  --force-freeze \
  --write-latest-aliases
```

Expected campaign-level outputs:

```text
results/experimental-cycles/C6/execution/latest-campaign-execution-manifest.json
results/experimental-cycles/C6/diagnosis/
results/experimental-cycles/C6/reporting/
results/experimental-cycles/C6/completion-gate/latest-completion-gate-manifest.json
results/experimental-cycles/C6/freeze/
```

Tenant-specific runtime evidence is stored under each variant root and under the application deployment artifacts generated for that variant.

---

## Step 13 — Optional Full C2-C6 Sequential Regeneration

The following command sequence runs all comparative campaigns in the recommended order.

Use this only after completing all validation and dry-run steps.

### Windows PowerShell

```powershell
$Campaigns = @(
  ".\config\experimental-cycles\C2.json",
  ".\config\experimental-cycles\C3.json",
  ".\config\experimental-cycles\C4.json",
  ".\config\experimental-cycles\C5.json",
  ".\config\experimental-cycles\C6.json"
)

foreach ($Campaign in $Campaigns) {
  .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
    -CycleConfig $Campaign `
    -ToolPath "proxmox-k3s" `
    -ConfirmDelete `
    -AllowMetricsWarning `
    -ContinueOnFailure `
    -ForceFreeze `
    -WriteLatestAliases

  if ($LASTEXITCODE -ne 0) {
    throw "Campaign execution failed: $Campaign"
  }
}
```

### Bash

```bash
campaigns=(
  "./config/experimental-cycles/C2.json"
  "./config/experimental-cycles/C3.json"
  "./config/experimental-cycles/C4.json"
  "./config/experimental-cycles/C5.json"
  "./config/experimental-cycles/C6.json"
)

for campaign in "${campaigns[@]}"; do
  ./scripts/experimental-cycles/start-experimental-campaign.sh \
    --cycle-config "$campaign" \
    --tool-path proxmox-k3s \
    --confirm-delete \
    --allow-metrics-warning \
    --continue-on-failure \
    --force-freeze \
    --write-latest-aliases

done
```

---

## Step 14 — Inspect Campaign Execution Status

After each campaign, inspect the latest campaign execution manifest.

### Windows PowerShell

```powershell
python -c "import json, pathlib;\
for c in ['C2','C3','C4','C5','C6']:\
 p=pathlib.Path(f'results/experimental-cycles/{c}/execution/latest-campaign-execution-manifest.json');\
 print(c, 'MISSING' if not p.exists() else json.load(open(p, encoding='utf-8-sig')).get('status'))"
```

### Bash

```bash
python3 -c "import json, pathlib;\
for c in ['C2','C3','C4','C5','C6']:\
 p=pathlib.Path(f'results/experimental-cycles/{c}/execution/latest-campaign-execution-manifest.json');\
 print(c, 'MISSING' if not p.exists() else json.load(open(p, encoding='utf-8-sig')).get('status'))"
```

Valid terminal states include:

| Status | Meaning |
|---|---|
| `completed` | All variants and campaign-level post-processing completed without unsupported scenarios. |
| `completed_with_unsupported_scenarios` | At least one variant reached an expected unsupported state and preserved diagnostic evidence. |
| `completed_with_skipped_steps` | One or more steps were intentionally skipped. Inspect the manifest before accepting the result. |
| `failed` | The campaign failed. Inspect failed steps, provider logs, validation artifacts, and variant execution manifests. |
| `dry_run` | The campaign was planned but not actually executed. |

---

## Step 15 — Inspect Variant-Level Status

Print the status of all variants captured by the latest campaign execution manifests.

### Windows PowerShell

```powershell
python -c "import json, pathlib;\
for c in ['C2','C3','C4','C5','C6']:\
 p=pathlib.Path(f'results/experimental-cycles/{c}/execution/latest-campaign-execution-manifest.json');\
 print('\n'+c);\
 d=json.load(open(p, encoding='utf-8-sig')) if p.exists() else {};\
 [print(f\"- {v.get('variantId')}: {v.get('status')} unsupported={bool(v.get('unsupportedScenario'))}\") for v in d.get('variantResults', [])]"
```

### Bash

```bash
python3 -c "import json, pathlib;\
for c in ['C2','C3','C4','C5','C6']:\
 p=pathlib.Path(f'results/experimental-cycles/{c}/execution/latest-campaign-execution-manifest.json');\
 print('\n'+c);\
 d=json.load(open(p, encoding='utf-8-sig')) if p.exists() else {};\
 [print(f\"- {v.get('variantId')}: {v.get('status')} unsupported={bool(v.get('unsupportedScenario'))}\") for v in d.get('variantResults', [])]"
```

A campaign with unsupported scenarios can still be acceptable if all unsupported states are expected, documented, and captured by artifacts.

---

## Step 16 — Verify Generated Runtime Configs

The campaign runner generates runtime profiles for each variant. Verify that each variant has generated profile files.

### Windows PowerShell

```powershell
python -c "import pathlib;\
for c in ['C2','C3','C4','C5','C6']:\
 root=pathlib.Path(f'results/experimental-cycles/{c}/execution/generated-runtime-configs');\
 print(c, 'MISSING' if not root.exists() else len([p for p in root.rglob('*.json')]), 'generated JSON files')"
```

### Bash

```bash
python3 -c "import pathlib;\
for c in ['C2','C3','C4','C5','C6']:\
 root=pathlib.Path(f'results/experimental-cycles/{c}/execution/generated-runtime-configs');\
 print(c, 'MISSING' if not root.exists() else len([p for p in root.rglob('*.json')]), 'generated JSON files')"
```

Generated runtime configs are useful for auditability, but source changes must be made in the canonical configuration files under `config/`, not directly in generated runtime artifacts.

---

## Step 17 — Verify Post-Processing Artifacts

Validate that diagnosis, reporting, completion gate, and freeze outputs exist for each campaign.

### Windows PowerShell

```powershell
$Cycles = @("C2", "C3", "C4", "C5", "C6")

foreach ($Cycle in $Cycles) {
  $Paths = @(
    ".\results\experimental-cycles\$Cycle\diagnosis",
    ".\results\experimental-cycles\$Cycle\reporting",
    ".\results\experimental-cycles\$Cycle\completion-gate\latest-completion-gate-manifest.json",
    ".\results\experimental-cycles\$Cycle\freeze"
  )

  foreach ($Path in $Paths) {
    if (-not (Test-Path $Path)) {
      throw "Missing post-processing artifact for $Cycle: $Path"
    }
  }
}
```

### Bash

```bash
for cycle in C2 C3 C4 C5 C6; do
  paths=(
    "./results/experimental-cycles/$cycle/diagnosis"
    "./results/experimental-cycles/$cycle/reporting"
    "./results/experimental-cycles/$cycle/completion-gate/latest-completion-gate-manifest.json"
    "./results/experimental-cycles/$cycle/freeze"
  )

  for path in "${paths[@]}"; do
    test -e "$path" || { echo "Missing post-processing artifact for $cycle: $path" >&2; exit 1; }
  done
done
```

---

## Step 18 — Verify Reporting Site Refresh

Each completed campaign execution refreshes the global reporting-site root unless reporting is skipped.

### Windows PowerShell

```powershell
if (-not (Test-Path ".\results\reporting\index.html")) {
  throw "Reporting site index was not generated."
}

Get-ChildItem .\results\reporting
```

### Bash

```bash
test -f ./results/reporting/index.html || { echo "Reporting site index was not generated." >&2; exit 1; }
ls -la ./results/reporting
```

---

## Step 19 — Optional Strict Campaign Execution

The standard regeneration commands above include `ContinueOnFailure` to preserve evidence across variants. For a stricter execution mode, omit the continue flag.

### Windows PowerShell

```powershell
.\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C4.json `
  -ToolPath "proxmox-k3s" `
  -ConfirmDelete `
  -AllowMetricsWarning `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config ./config/experimental-cycles/C4.json \
  --tool-path proxmox-k3s \
  --confirm-delete \
  --allow-metrics-warning \
  --force-freeze \
  --write-latest-aliases
```

Use strict mode when the purpose is to fail immediately on unexpected infrastructure, provisioning, deployment, or benchmark failures.

---

## Step 20 — Optional Re-run Without Provisioning

If a campaign variant cluster is intentionally kept alive and already validated, provisioning can be skipped for diagnostic re-runs. This mode must be used with caution because it assumes that the cluster state still matches the selected variant.

### Windows PowerShell

```powershell
.\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C3.json `
  -ToolPath "proxmox-k3s" `
  -SkipProvisioning `
  -SkipDelete `
  -AllowMetricsWarning `
  -ContinueOnFailure `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config ./config/experimental-cycles/C3.json \
  --tool-path proxmox-k3s \
  --skip-provisioning \
  --skip-delete \
  --allow-metrics-warning \
  --continue-on-failure \
  --force-freeze \
  --write-latest-aliases
```

Do not use this mode for official regeneration unless the cluster lifecycle has been intentionally changed to a retained/reuse workflow and the retained state has been validated.

---

## Step 21 — Optional Re-run Post-Processing Only

If benchmark artifacts already exist and only campaign-level post-processing must be regenerated, skip infrastructure, deployment, benchmark, and validation steps.

### Windows PowerShell

```powershell
.\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C5.json `
  -ToolPath "proxmox-k3s" `
  -SkipProvisioning `
  -SkipClusterValidation `
  -SkipPlacementProfile `
  -SkipLocalAIDeployment `
  -SkipSmokeTest `
  -SkipMinimalObservability `
  -SkipBenchmark `
  -SkipDelete `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config ./config/experimental-cycles/C5.json \
  --tool-path proxmox-k3s \
  --skip-provisioning \
  --skip-cluster-validation \
  --skip-placement-profile \
  --skip-localai-deployment \
  --skip-smoke-test \
  --skip-minimal-observability \
  --skip-benchmark \
  --skip-delete \
  --force-freeze \
  --write-latest-aliases
```

Post-processing-only mode must not be used to claim that the runtime benchmark was regenerated. It only refreshes diagnosis, reporting, completion-gate, and freeze outputs from already available evidence.

---

## Step 22 — Inspect Unsupported Scenario Evidence

Use this check to list unsupported scenario records from the latest campaign manifests.

### Windows PowerShell

```powershell
python -c "import json, pathlib;\
for c in ['C2','C3','C4','C5','C6']:\
 p=pathlib.Path(f'results/experimental-cycles/{c}/execution/latest-campaign-execution-manifest.json');\
 print('\n'+c);\
 d=json.load(open(p, encoding='utf-8-sig')) if p.exists() else {};\
 [print(f\"- {v.get('variantId')}: {v.get('unsupportedScenario')}\") for v in d.get('variantResults', []) if v.get('unsupportedScenario')]"
```

### Bash

```bash
python3 -c "import json, pathlib;\
for c in ['C2','C3','C4','C5','C6']:\
 p=pathlib.Path(f'results/experimental-cycles/{c}/execution/latest-campaign-execution-manifest.json');\
 print('\n'+c);\
 d=json.load(open(p, encoding='utf-8-sig')) if p.exists() else {};\
 [print(f\"- {v.get('variantId')}: {v.get('unsupportedScenario')}\") for v in d.get('variantResults', []) if v.get('unsupportedScenario')]"
```

Unsupported evidence should be inspected together with variant-level infrastructure validation, deployment, events, rollout status, and observability artifacts.

---

## Step 23 — Inspect Latest Completion Gate Results

Print campaign-level completion-gate status for `C2` through `C6`.

### Windows PowerShell

```powershell
python -c "import json, pathlib;\
for c in ['C2','C3','C4','C5','C6']:\
 p=pathlib.Path(f'results/experimental-cycles/{c}/completion-gate/latest-completion-gate-manifest.json');\
 d=json.load(open(p, encoding='utf-8-sig')) if p.exists() else {};\
 print(c, d.get('status', 'MISSING'))"
```

### Bash

```bash
python3 -c "import json, pathlib;\
for c in ['C2','C3','C4','C5','C6']:\
 p=pathlib.Path(f'results/experimental-cycles/{c}/completion-gate/latest-completion-gate-manifest.json');\
 d=json.load(open(p, encoding='utf-8-sig')) if p.exists() else {};\
 print(c, d.get('status', 'MISSING'))"
```

Completion-gate outputs must be read together with the corresponding diagnosis outputs. A completion gate can accept a campaign with unsupported scenarios only if the gate policy and diagnosis profile explicitly support that interpretation.

---

## Step 24 — Inspect Freeze Outputs

Verify that campaign freeze outputs exist.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C2\freeze
Get-ChildItem .\results\experimental-cycles\C3\freeze
Get-ChildItem .\results\experimental-cycles\C4\freeze
Get-ChildItem .\results\experimental-cycles\C5\freeze
Get-ChildItem .\results\experimental-cycles\C6\freeze
```

### Bash

```bash
ls -la ./results/experimental-cycles/C2/freeze
ls -la ./results/experimental-cycles/C3/freeze
ls -la ./results/experimental-cycles/C4/freeze
ls -la ./results/experimental-cycles/C5/freeze
ls -la ./results/experimental-cycles/C6/freeze
```

A campaign should be considered archived only after the freeze step has produced the expected manifest, lock, and frozen artifact snapshot according to its freeze profile.

---

## Step 25 — Optional Provider Cleanup After Interrupted Campaigns

If a campaign is interrupted before the post-variant delete step, stale provider-backed clusters may remain. Use the provider-backed provisioning runner only after identifying the generated variant cycle config that owns the cluster.

The generated variant cycle configs are stored under:

```text
results/experimental-cycles/<cycle>/execution/generated-runtime-configs/<variant-id>/<variant-id>.cycle.json
```

Example cleanup for one generated variant cycle:

### Windows PowerShell

```powershell
python .\scripts\infrastructure\provision\run-provider-backed-provisioning.py `
  --repo-root . `
  --cycle-config .\results\experimental-cycles\C4\execution\generated-runtime-configs\PLC_COLOCATED\PLC_COLOCATED.cycle.json `
  --action destroy `
  --tool-path "proxmox-k3s" `
  --confirm-delete `
  --write-latest-aliases
```

### Bash

```bash
python3 ./scripts/infrastructure/provision/run-provider-backed-provisioning.py \
  --repo-root . \
  --cycle-config ./results/experimental-cycles/C4/execution/generated-runtime-configs/PLC_COLOCATED/PLC_COLOCATED.cycle.json \
  --action destroy \
  --tool-path proxmox-k3s \
  --confirm-delete \
  --write-latest-aliases
```

Do not run cleanup against a generated variant cycle unless the target provider configuration has been verified.

---

## Final Campaign Regeneration Checklist

A complete `C2`–`C6` regeneration is acceptable when all of the following conditions hold.

1. All required local provider YAML files exist and have been reviewed.
2. Dry-run manifests have been generated and inspected before real execution.
3. `C2` completed or completed with documented unsupported scenarios.
4. `C3` completed or completed with documented unsupported scenarios.
5. `C4` completed or completed with documented unsupported scenarios.
6. `C5` completed or completed with documented unsupported scenarios.
7. `C6` completed or completed with documented unsupported scenarios.
8. Each campaign has a latest campaign execution manifest.
9. Each campaign has generated variant runtime profiles.
10. Each campaign has diagnosis artifacts.
11. Each campaign has reporting artifacts.
12. The global reporting site has been refreshed.
13. Each campaign has a completion-gate manifest.
14. Each campaign has freeze artifacts.
15. Any unsupported scenario has preserved explicit evidence and is interpreted through the campaign diagnosis and completion-gate policy.
16. No local provider config, kubeconfig, credential, VPN file, SSH key, or generated access artifact is prepared for publication.

---

## Relationship to the C7 Default-Scheduler Baseline

The `C2` through `C6` campaigns use controlled variants to characterize resource capacity, node count, placement, latency injection, and multi-tenancy behavior.

`C7` should be executed after the controlled provider-backed campaigns when the operator needs to evaluate what happens without hard placement controls. C7 reuses the same provider-backed execution principles, but it changes the scheduling boundary: Kubernetes chooses pod placement, and the benchmark suite captures the resulting default-scheduler decision as evidence.

Proceed to the C7 execution runbook only after the C2-C6 evidence is available or intentionally skipped for the current regeneration scope.

```text
docs/runbooks/09-default-scheduler-c7-baseline-execution.md
```

After C7 has established default-scheduler evidence, C8 can be executed as the paired resource-aware scheduler campaign. C8 reuses provider-backed campaign mechanics, but adds `mon-agent`, custom scheduler installation, controlled redeployment, and resource-aware scheduler evidence. After C8, C9 extends the model with gateway-routed traffic, Mentat inter-node telemetry, Istio evidence, network-aware annotations, and the `NetworkAwareLocalAi` plugin.

```text
docs/runbooks/10-resource-aware-scheduler-c8-execution.md
```

