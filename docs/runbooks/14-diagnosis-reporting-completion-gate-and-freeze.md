# Diagnosis, Reporting, Completion Gate, and Freeze

## Purpose

This runbook documents the post-processing layer of the LocalAI worker-mode benchmark suite.

The post-processing layer turns raw benchmark, infrastructure, deployment, observability, and runtime artifacts into reviewable evidence packages. It is responsible for:

1. generating technical diagnosis outputs;
2. generating cycle-scoped reports and visualizations;
3. refreshing the global reporting site;
4. evaluating completion gates;
5. freezing cycle artifacts into reproducible snapshots.

This runbook is not the primary entry point for executing the benchmark workload itself. Complete cycle execution is documented in:

```text
docs/runbooks/06-fixed-cluster-c0-execution.md
docs/runbooks/07-provider-backed-c1-baseline-execution.md
docs/runbooks/08-provider-backed-c2-c6-campaign-execution.md
docs/runbooks/09-default-scheduler-c7-baseline-execution.md
docs/runbooks/10-resource-aware-scheduler-c8-execution.md
docs/runbooks/11-network-aware-scheduler-c9-execution.md
```

Use this runbook when the benchmark artifacts already exist and the post-processing outputs must be inspected, regenerated, validated, or frozen.

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

## Post-Processing Execution Model

The post-processing layer follows this canonical order:

```text
benchmark and runtime artifacts
→ technical diagnosis
→ cycle-scoped reporting
→ global reporting-site refresh
→ completion gate
→ freeze
```

The dependency chain is intentional:

1. **Technical diagnosis** consumes benchmark outputs, unsupported-scenario evidence, cluster-side observations, and scenario metadata.
2. **Reporting** consumes benchmark outputs, diagnosis context, runtime metadata, observability snapshots, and configuration references.
3. **Reporting-site refresh** collects cycle-scoped reports under a stable static entry point.
4. **Completion gate** checks whether the required configuration and runtime evidence for a cycle are available and acceptable.
5. **Freeze** snapshots the cycle configuration and evidence package after completion-gate validation.

Do not freeze a cycle before its completion gate has been evaluated, unless explicitly performing a dry run or a controlled diagnostic operation.

---

## Cycle Coverage

The post-processing layer covers the complete cycle taxonomy:

| Cycle | Execution track | Post-processing role |
|---|---|---|
| `C0` | Historical fixed-cluster | Preserve and summarize fixed-cluster worker-mode characterization evidence |
| `C1` | Provider-backed baseline | Validate the first provider-backed baseline evidence package |
| `C2` | Provider-backed campaign | Summarize resource-variation evidence |
| `C3` | Provider-backed campaign | Summarize node-count variation evidence |
| `C4` | Provider-backed campaign | Summarize placement-variation evidence |
| `C5` | Provider-backed campaign | Summarize latency-injection evidence |
| `C6` | Provider-backed campaign | Summarize multi-tenancy evidence |
| `C7` | Default-scheduler provider-backed campaign | Summarize default Kubernetes scheduler baseline evidence, including scheduler decisions, tenant traffic, latency profiles, and placement-performance interpretation |
| `C8` | Resource-aware scheduler provider-backed campaign | Summarize paired default/load-aware scheduler evidence, runtime annotations, controlled redeployment, placement, and comparative performance outcomes |
| `C9` | Network-aware scheduler provider-backed campaign | Summarize default/load-aware/network-aware scheduler evidence, gateway-routed traffic, network telemetry, controlled rescheduling, placement, and comparative performance outcomes |

`C0` and `C1` are cycle-level executions. `C2` through `C6` are controlled provider-backed campaign-level executions composed of multiple variants. `C7` is a default-scheduler provider-backed campaign composed of default-scheduler scenarios. `C8` is a paired resource-aware scheduler campaign composed of default and load-aware variants. `C9` is a network-aware scheduler campaign composed of default, load-aware, and network-aware variants. Their post-processing outputs must therefore preserve both campaign-level summaries and variant-level status evidence.

---

## Canonical Post-Processing Profiles

Each cycle has one profile for each post-processing stage.

| Cycle | Technical diagnosis | Reporting | Completion gate | Freeze |
|---|---|---|---|---|
| `C0` | `TD_C0_HISTORICAL_FIXED_CLUSTER.json` | `RP_C0_HISTORICAL_FIXED_CLUSTER.json` | `CG_C0_HISTORICAL_FIXED_CLUSTER.json` | `FR_C0_HISTORICAL_FIXED_CLUSTER.json` |
| `C1` | `TD_C1_PROVIDER_BACKED_BASELINE.json` | `RP_C1_PROVIDER_BACKED_BASELINE.json` | `CG_C1_PROVIDER_BACKED_BASELINE.json` | `FR_C1_PROVIDER_BACKED_BASELINE.json` |
| `C2` | `TD_C2_RESOURCE_VARIATION.json` | `RP_C2_RESOURCE_VARIATION.json` | `CG_C2_RESOURCE_VARIATION.json` | `FR_C2_RESOURCE_VARIATION.json` |
| `C3` | `TD_C3_NODE_COUNT_VARIATION.json` | `RP_C3_NODE_COUNT_VARIATION.json` | `CG_C3_NODE_COUNT_VARIATION.json` | `FR_C3_NODE_COUNT_VARIATION.json` |
| `C4` | `TD_C4_PLACEMENT_VARIATION.json` | `RP_C4_PLACEMENT_VARIATION.json` | `CG_C4_PLACEMENT_VARIATION.json` | `FR_C4_PLACEMENT_VARIATION.json` |
| `C5` | `TD_C5_LATENCY_INJECTION.json` | `RP_C5_LATENCY_INJECTION.json` | `CG_C5_LATENCY_INJECTION.json` | `FR_C5_LATENCY_INJECTION.json` |
| `C6` | `TD_C6_MULTI_TENANCY.json` | `RP_C6_MULTI_TENANCY.json` | `CG_C6_MULTI_TENANCY.json` | `FR_C6_MULTI_TENANCY.json` |
| `C7` | `TD_C7_DEFAULT_SCHEDULER_BASELINE.json` | `RP_C7_DEFAULT_SCHEDULER_BASELINE.json` | `CG_C7_DEFAULT_SCHEDULER_BASELINE.json` | `FR_C7_DEFAULT_SCHEDULER_BASELINE.json` |
| `C8` | `TD_C8_RESOURCE_AWARE_SCHEDULER.json` | `RP_C8_RESOURCE_AWARE_SCHEDULER.json` | `CG_C8_RESOURCE_AWARE_SCHEDULER.json` | `FR_C8_RESOURCE_AWARE_SCHEDULER.json` |
| `C9` | `TD_C9_NETWORK_AWARE_SCHEDULER.json` | `RP_C9_NETWORK_AWARE_SCHEDULER.json` | `CG_C9_NETWORK_AWARE_SCHEDULER.json` | `FR_C9_NETWORK_AWARE_SCHEDULER.json` |

The profile directories are:

```text
config/technical-diagnosis/profiles/
config/reporting/profiles/
config/completion-gate/profiles/
config/freeze/profiles/
```

The corresponding schema and index directories are:

```text
config/technical-diagnosis/
config/reporting/
config/completion-gate/
config/freeze/
```

---

## Canonical Output Roots

Post-processing outputs are cycle-scoped.

| Cycle | Diagnosis root | Reporting root | Completion-gate root | Freeze root |
|---|---|---|---|---|
| `C0` | `results/experimental-cycles/C0/diagnosis/` | `results/experimental-cycles/C0/reporting/` | `results/experimental-cycles/C0/completion-gate/` | `results/experimental-cycles/C0/freeze/` |
| `C1` | `results/experimental-cycles/C1/diagnosis/` | `results/experimental-cycles/C1/reporting/` | `results/experimental-cycles/C1/completion-gate/` | `results/experimental-cycles/C1/freeze/` |
| `C2` | `results/experimental-cycles/C2/diagnosis/` | `results/experimental-cycles/C2/reporting/` | `results/experimental-cycles/C2/completion-gate/` | `results/experimental-cycles/C2/freeze/` |
| `C3` | `results/experimental-cycles/C3/diagnosis/` | `results/experimental-cycles/C3/reporting/` | `results/experimental-cycles/C3/completion-gate/` | `results/experimental-cycles/C3/freeze/` |
| `C4` | `results/experimental-cycles/C4/diagnosis/` | `results/experimental-cycles/C4/reporting/` | `results/experimental-cycles/C4/completion-gate/` | `results/experimental-cycles/C4/freeze/` |
| `C5` | `results/experimental-cycles/C5/diagnosis/` | `results/experimental-cycles/C5/reporting/` | `results/experimental-cycles/C5/completion-gate/` | `results/experimental-cycles/C5/freeze/` |
| `C6` | `results/experimental-cycles/C6/diagnosis/` | `results/experimental-cycles/C6/reporting/` | `results/experimental-cycles/C6/completion-gate/` | `results/experimental-cycles/C6/freeze/` |
| `C7` | `results/experimental-cycles/C7/diagnosis/` | `results/experimental-cycles/C7/reporting/` | `results/experimental-cycles/C7/completion-gate/` | `results/experimental-cycles/C7/freeze/` |
| `C8` | `results/experimental-cycles/C8/diagnosis/` | `results/experimental-cycles/C8/reporting/` | `results/experimental-cycles/C8/completion-gate/` | `results/experimental-cycles/C8/freeze/` |
| `C9` | `results/experimental-cycles/C9/diagnosis/` | `results/experimental-cycles/C9/reporting/` | `results/experimental-cycles/C9/completion-gate/` | `results/experimental-cycles/C9/freeze/` |

The global reporting-site root is:

```text
results/reporting/
```

The reporting site is a compact static entry point. Cycle-scoped reports remain the authoritative report packages.

---

## Generated Artifact Types

### Technical Diagnosis

Technical diagnosis produces machine-readable and human-readable outputs.

Typical outputs include:

```text
results/experimental-cycles/<cycle>/diagnosis/*_diagnosis.json
results/experimental-cycles/<cycle>/diagnosis/*_diagnosis.txt
```

The JSON file is the primary input for downstream automated checks. The text file is intended for quick human inspection.

### Reporting

Reporting produces a cycle-scoped report package.

Typical outputs include:

```text
results/experimental-cycles/<cycle>/reporting/report.md
results/experimental-cycles/<cycle>/reporting/index.html
results/experimental-cycles/<cycle>/reporting/scenario-summary.csv
results/experimental-cycles/<cycle>/reporting/reporting-manifest.json
results/experimental-cycles/<cycle>/reporting/charts/
results/experimental-cycles/<cycle>/reporting/sweeps/
```

For campaigns, the report must preserve scenario or variant-level interpretation instead of flattening everything into an ambiguous aggregate.

For C9, the report must also preserve the evidence needed to interpret network-aware scheduler behavior. The generated C9 report should include the following network-aware sections:

| Section | Interpretation role |
|---|---|
| `Network-aware latency profile context` | Shows the latency profile, latency alias, implementation mode, inter-group delay, jitter, packet-loss policy, and worker-group model associated with each logical scenario. |
| `Cluster-lens placement evidence summary` | Shows whether primary cluster-lens evidence was selected for each variant, which capture stage was used, whether validation succeeded, and whether the cluster topology view is available. |
| `Cluster-lens tenant placement` | Shows tenant-level LocalAI master and worker pod placement, distinct tenant nodes, co-location, unscheduled pods, and observed scheduler names. |
| `Scheduler comparison` | Compares performance metrics across the `DEFAULT`, `LOADAWARE`, and `NETAWARE` variants belonging to the same logical scenario. |

When reading C9 reports, do not treat a stable cluster topology as lack of scheduler effect. The Kubernetes topology is expected to remain comparable across paired scheduler variants. The scheduler effect is evaluated through LocalAI pod placement, tenant co-location, distinct tenant nodes, scheduler assignment, and the relationship between placement and performance metrics.

The static reporting site mirrors the cycle-scoped C9 report under:

```text
results/reporting/cycles/C9/index.html
```

### Reporting Identifiers

Cycle-scoped reporting identifiers must use the canonical prefix `REP_C<cycle-number>` followed by the UTC timestamp generated by the reporting script. Examples:

```text
REP_C0_<UTC_TIMESTAMP>
REP_C1_<UTC_TIMESTAMP>
REP_C8_<UTC_TIMESTAMP>
REP_C9_<UTC_TIMESTAMP>
```

The reporting identifier is metadata, not the report title. The identifier should remain compact and machine-comparable across cycles, while the report title can describe the campaign, such as `C9 - Network-Aware Scheduler Campaign Report`.

For `C9`, the reporting profile must therefore keep `reportingIdPrefix` set to `REP_C9`, even though the campaign itself is named `Network-Aware Scheduler Campaign`.

### Reporting Site

The reporting site produces a stable static entry point:

```text
results/reporting/index.html
results/reporting/reporting-site-manifest.json
results/reporting/reporting-manifest.json
results/reporting/cycles/
results/reporting/.nojekyll
```

### Completion Gate

The completion gate produces an execution manifest and a text summary.

Typical outputs include:

```text
results/experimental-cycles/<cycle>/completion-gate/latest-completion-gate-manifest.json
results/experimental-cycles/<cycle>/completion-gate/latest-completion-gate-summary.txt
```

Timestamped completion-gate files may also exist depending on the active profile and execution mode.

### Freeze

Freeze produces a cycle lock, freeze manifest, freeze text summary, and artifact snapshot.

Typical outputs include:

```text
results/experimental-cycles/<cycle>/freeze/latest-freeze-manifest.json
results/experimental-cycles/<cycle>/freeze/latest-freeze-summary.txt
results/experimental-cycles/<cycle>/freeze/<cycle>-cycle-lock.json
results/experimental-cycles/<cycle>/freeze/<cycle>-cycle-lock.txt
results/experimental-cycles/<cycle>/artifacts/
```

The artifact snapshot is intended to preserve the evidence package that existed when the cycle was frozen.

---

## Completion Status Semantics

Completion gate and freeze logic may report different statuses depending on the available evidence.

| Status | Meaning |
|---|---|
| `completed` | Required evidence exists and all enabled gates passed |
| `completed_with_unsupported_scenarios` | Required evidence exists, and unsupported scenarios are present but accepted by the profile policy |
| `failed_validation` | Cluster validation or required precondition evidence is missing or invalid |
| `failed_benchmark` | Required benchmark evidence is missing or unusable |
| `failed_diagnosis` | Diagnosis evidence is missing, malformed, or not accepted |
| `failed_reporting` | Reporting artifacts are missing or incomplete |
| `failed_completion_gate` | Completion-gate evaluation failed or was not accepted |
| `failed_freeze` | Freeze could not create or preserve the expected artifact snapshot |

The accepted terminal states for freeze are defined by the freeze profile. In the current cycle profiles, freeze generally accepts:

```text
completed
completed_with_unsupported_scenarios
```

Unsupported scenarios are valid evidence when they result from a documented experimental condition such as insufficient resources, scheduling constraints, rollout timeout, or intentionally unsupported latency or tenancy layout. They must not be silently removed from the evidence package.

---

## Step 1 — Verify Post-Processing Entry Points

### Windows PowerShell

```powershell
Test-Path .\scripts\load\post\Start-TechnicalDiagnosis.ps1
Test-Path .\scripts\load\post\Start-Reporting.ps1
Test-Path .\scripts\load\post\Start-ReportingSite.ps1
Test-Path .\scripts\load\post\Start-CompletionGate.ps1
Test-Path .\scripts\load\post\Start-FreezeExperimentalCycle.ps1
```

### Bash

```bash
test -f scripts/load/post/start-technical-diagnosis.sh
test -f scripts/load/post/start-reporting.sh
test -f scripts/load/post/start-reporting-site.sh
test -f scripts/load/post/start-completion-gate.sh
test -f scripts/load/post/start-freeze-experimental-cycle.sh
```

---

## Step 2 — Verify Post-Processing Profiles

### Windows PowerShell

```powershell
Get-ChildItem .\config\technical-diagnosis\profiles\TD_C*.json
Get-ChildItem .\config\reporting\profiles\RP_C*.json
Get-ChildItem .\config\completion-gate\profiles\CG_C*.json
Get-ChildItem .\config\freeze\profiles\FR_C*.json
```

### Bash

```bash
ls config/technical-diagnosis/profiles/TD_C*.json
ls config/reporting/profiles/RP_C*.json
ls config/completion-gate/profiles/CG_C*.json
ls config/freeze/profiles/FR_C*.json
```

Expected profile coverage:

```text
C0 C1 C2 C3 C4 C5 C6 C7 C8 C9
```

---

## Step 3 — Validate Post-Processing JSON Files

### Windows PowerShell

```powershell
python -m json.tool .\config\technical-diagnosis\TECHNICAL_DIAGNOSIS_INDEX.json | Out-Null
python -m json.tool .\config\reporting\REPORTING_INDEX.json | Out-Null
python -m json.tool .\config\reporting\site\REPORTING_SITE.json | Out-Null
python -m json.tool .\config\completion-gate\COMPLETION_GATE_INDEX.json | Out-Null
python -m json.tool .\config\freeze\FREEZE_INDEX.json | Out-Null
Get-ChildItem .\config\technical-diagnosis\profiles\TD_C*.json | ForEach-Object { python -m json.tool $_.FullName | Out-Null }
Get-ChildItem .\config\reporting\profiles\RP_C*.json | ForEach-Object { python -m json.tool $_.FullName | Out-Null }
Get-ChildItem .\config\completion-gate\profiles\CG_C*.json | ForEach-Object { python -m json.tool $_.FullName | Out-Null }
Get-ChildItem .\config\freeze\profiles\FR_C*.json | ForEach-Object { python -m json.tool $_.FullName | Out-Null }
```

### Bash

```bash
python3 -m json.tool config/technical-diagnosis/TECHNICAL_DIAGNOSIS_INDEX.json >/dev/null
python3 -m json.tool config/reporting/REPORTING_INDEX.json >/dev/null
python3 -m json.tool config/reporting/site/REPORTING_SITE.json >/dev/null
python3 -m json.tool config/completion-gate/COMPLETION_GATE_INDEX.json >/dev/null
python3 -m json.tool config/freeze/FREEZE_INDEX.json >/dev/null
for file in config/technical-diagnosis/profiles/TD_C*.json; do python3 -m json.tool "$file" >/dev/null; done
for file in config/reporting/profiles/RP_C*.json; do python3 -m json.tool "$file" >/dev/null; done
for file in config/completion-gate/profiles/CG_C*.json; do python3 -m json.tool "$file" >/dev/null; done
for file in config/freeze/profiles/FR_C*.json; do python3 -m json.tool "$file" >/dev/null; done
```

---

## Step 4 — Generate Technical Diagnosis for One Cycle

Use the cycle-specific technical diagnosis profile.

The example below regenerates diagnosis for `C1`.

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

Expected outputs:

```text
results/experimental-cycles/C1/diagnosis/*_diagnosis.json
results/experimental-cycles/C1/diagnosis/*_diagnosis.txt
```

---

## Step 5 — Generate Technical Diagnosis for All Cycles

### Windows PowerShell

```powershell
$diagnosisProfiles = @(
  ".\config\technical-diagnosis\profiles\TD_C0_HISTORICAL_FIXED_CLUSTER.json",
  ".\config\technical-diagnosis\profiles\TD_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\technical-diagnosis\profiles\TD_C2_RESOURCE_VARIATION.json",
  ".\config\technical-diagnosis\profiles\TD_C3_NODE_COUNT_VARIATION.json",
  ".\config\technical-diagnosis\profiles\TD_C4_PLACEMENT_VARIATION.json",
  ".\config\technical-diagnosis\profiles\TD_C5_LATENCY_INJECTION.json",
  ".\config\technical-diagnosis\profiles\TD_C6_MULTI_TENANCY.json",
  ".\config\technical-diagnosis\profiles\TD_C7_DEFAULT_SCHEDULER_BASELINE.json",
  ".\config\technical-diagnosis\profiles\TD_C8_RESOURCE_AWARE_SCHEDULER.json",
  ".\config\technical-diagnosis\profiles\TD_C9_NETWORK_AWARE_SCHEDULER.json"
)

foreach ($profile in $diagnosisProfiles) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File .\scripts\load\post\Start-TechnicalDiagnosis.ps1 `
    -ProfileConfig $profile `
    -Family all
}
```

### Bash

```bash
for profile in \
  config/technical-diagnosis/profiles/TD_C0_HISTORICAL_FIXED_CLUSTER.json \
  config/technical-diagnosis/profiles/TD_C1_PROVIDER_BACKED_BASELINE.json \
  config/technical-diagnosis/profiles/TD_C2_RESOURCE_VARIATION.json \
  config/technical-diagnosis/profiles/TD_C3_NODE_COUNT_VARIATION.json \
  config/technical-diagnosis/profiles/TD_C4_PLACEMENT_VARIATION.json \
  config/technical-diagnosis/profiles/TD_C5_LATENCY_INJECTION.json \
  config/technical-diagnosis/profiles/TD_C6_MULTI_TENANCY.json \
  config/technical-diagnosis/profiles/TD_C7_DEFAULT_SCHEDULER_BASELINE.json \
  config/technical-diagnosis/profiles/TD_C8_RESOURCE_AWARE_SCHEDULER.json \
  config/technical-diagnosis/profiles/TD_C9_NETWORK_AWARE_SCHEDULER.json
do
  ./scripts/load/post/start-technical-diagnosis.sh \
    --profile-config "$profile" \
    --family all
done
```

---

## Step 6 — Generate Reporting for One Cycle

The example below regenerates the report for `C1`.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-Reporting.ps1 `
  -ProfileConfig .\config\reporting\profiles\RP_C1_PROVIDER_BACKED_BASELINE.json
```

### Bash

```bash
./scripts/load/post/start-reporting.sh \
  --profile-config config/reporting/profiles/RP_C1_PROVIDER_BACKED_BASELINE.json
```

Expected outputs:

```text
results/experimental-cycles/C1/reporting/report.md
results/experimental-cycles/C1/reporting/index.html
results/experimental-cycles/C1/reporting/scenario-summary.csv
results/experimental-cycles/C1/reporting/reporting-manifest.json
results/experimental-cycles/C1/reporting/charts/
```

By default, reporting may also refresh the global reporting site unless explicitly disabled by command arguments or profile behavior.

---

## Step 7 — Generate Reporting for All Cycles

### Windows PowerShell

```powershell
$reportingProfiles = @(
  ".\config\reporting\profiles\RP_C0_HISTORICAL_FIXED_CLUSTER.json",
  ".\config\reporting\profiles\RP_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\reporting\profiles\RP_C2_RESOURCE_VARIATION.json",
  ".\config\reporting\profiles\RP_C3_NODE_COUNT_VARIATION.json",
  ".\config\reporting\profiles\RP_C4_PLACEMENT_VARIATION.json",
  ".\config\reporting\profiles\RP_C5_LATENCY_INJECTION.json",
  ".\config\reporting\profiles\RP_C6_MULTI_TENANCY.json",
  ".\config\reporting\profiles\RP_C7_DEFAULT_SCHEDULER_BASELINE.json",
  ".\config\reporting\profiles\RP_C8_RESOURCE_AWARE_SCHEDULER.json",
  ".\config\reporting\profiles\RP_C9_NETWORK_AWARE_SCHEDULER.json"
)

foreach ($profile in $reportingProfiles) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File .\scripts\load\post\Start-Reporting.ps1 `
    -ProfileConfig $profile
}
```

### Bash

```bash
for profile in \
  config/reporting/profiles/RP_C0_HISTORICAL_FIXED_CLUSTER.json \
  config/reporting/profiles/RP_C1_PROVIDER_BACKED_BASELINE.json \
  config/reporting/profiles/RP_C2_RESOURCE_VARIATION.json \
  config/reporting/profiles/RP_C3_NODE_COUNT_VARIATION.json \
  config/reporting/profiles/RP_C4_PLACEMENT_VARIATION.json \
  config/reporting/profiles/RP_C5_LATENCY_INJECTION.json \
  config/reporting/profiles/RP_C6_MULTI_TENANCY.json \
  config/reporting/profiles/RP_C7_DEFAULT_SCHEDULER_BASELINE.json \
  config/reporting/profiles/RP_C8_RESOURCE_AWARE_SCHEDULER.json \
  config/reporting/profiles/RP_C9_NETWORK_AWARE_SCHEDULER.json
do
  ./scripts/load/post/start-reporting.sh \
    --profile-config "$profile"
done
```

---

## Step 8 — Refresh the Global Reporting Site

The global reporting site collects available cycle-scoped HTML reports under a stable entry point.

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

Expected outputs:

```text
results/reporting/index.html
results/reporting/reporting-site-manifest.json
results/reporting/reporting-manifest.json
results/reporting/cycles/
results/reporting/.nojekyll
```

Use strict mode only when the execution must fail if no cycle-scoped report package is available.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-ReportingSite.ps1 `
  -SiteConfig .\config\reporting\site\REPORTING_SITE.json `
  -Strict
```

### Bash

```bash
./scripts/load/post/start-reporting-site.sh \
  --site-config config/reporting/site/REPORTING_SITE.json \
  --strict
```

---

## Step 9 — Evaluate Completion Gate for One Cycle

The example below evaluates the completion gate for `C1`.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-CompletionGate.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ProfileConfig .\config\completion-gate\profiles\CG_C1_PROVIDER_BACKED_BASELINE.json
```

### Bash

```bash
./scripts/load/post/start-completion-gate.sh \
  --cycle-config config/experimental-cycles/C1.json \
  --profile-config config/completion-gate/profiles/CG_C1_PROVIDER_BACKED_BASELINE.json
```

Expected outputs:

```text
results/experimental-cycles/C1/completion-gate/latest-completion-gate-manifest.json
results/experimental-cycles/C1/completion-gate/latest-completion-gate-summary.txt
```

The launcher can resolve the most recent diagnosis artifact when `--diagnosis-json` or `-DiagnosisJson` is omitted. Use an explicit diagnosis JSON when a specific diagnosis run must be used.

### Windows PowerShell

```powershell
$diagnosis = Get-ChildItem .\results\experimental-cycles\C1\diagnosis\*_diagnosis.json |
  Sort-Object LastWriteTime |
  Select-Object -Last 1

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-CompletionGate.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ProfileConfig .\config\completion-gate\profiles\CG_C1_PROVIDER_BACKED_BASELINE.json `
  -DiagnosisJson $diagnosis.FullName
```

### Bash

```bash
diagnosis="$(ls -t results/experimental-cycles/C1/diagnosis/*_diagnosis.json | head -n 1)"

./scripts/load/post/start-completion-gate.sh \
  --cycle-config config/experimental-cycles/C1.json \
  --profile-config config/completion-gate/profiles/CG_C1_PROVIDER_BACKED_BASELINE.json \
  --diagnosis-json "$diagnosis"
```

---

## Step 10 — Evaluate Completion Gates for All Cycles

### Windows PowerShell

```powershell
$completionGateProfiles = @(
  @{ Cycle = ".\config\experimental-cycles\C0.json"; Profile = ".\config\completion-gate\profiles\CG_C0_HISTORICAL_FIXED_CLUSTER.json" },
  @{ Cycle = ".\config\experimental-cycles\C1.json"; Profile = ".\config\completion-gate\profiles\CG_C1_PROVIDER_BACKED_BASELINE.json" },
  @{ Cycle = ".\config\experimental-cycles\C2.json"; Profile = ".\config\completion-gate\profiles\CG_C2_RESOURCE_VARIATION.json" },
  @{ Cycle = ".\config\experimental-cycles\C3.json"; Profile = ".\config\completion-gate\profiles\CG_C3_NODE_COUNT_VARIATION.json" },
  @{ Cycle = ".\config\experimental-cycles\C4.json"; Profile = ".\config\completion-gate\profiles\CG_C4_PLACEMENT_VARIATION.json" },
  @{ Cycle = ".\config\experimental-cycles\C5.json"; Profile = ".\config\completion-gate\profiles\CG_C5_LATENCY_INJECTION.json" },
  @{ Cycle = ".\config\experimental-cycles\C6.json"; Profile = ".\config\completion-gate\profiles\CG_C6_MULTI_TENANCY.json" },
  @{ Cycle = ".\config\experimental-cycles\C7.json"; Profile = ".\config\completion-gate\profiles\CG_C7_DEFAULT_SCHEDULER_BASELINE.json" },
  @{ Cycle = ".\config\experimental-cycles\C8.json"; Profile = ".\config\completion-gate\profiles\CG_C8_RESOURCE_AWARE_SCHEDULER.json" },
  @{ Cycle = ".\config\experimental-cycles\C9.json"; Profile = ".\config\completion-gate\profiles\CG_C9_NETWORK_AWARE_SCHEDULER.json" }
)

foreach ($item in $completionGateProfiles) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File .\scripts\load\post\Start-CompletionGate.ps1 `
    -CycleConfig $item.Cycle `
    -ProfileConfig $item.Profile
}
```

### Bash

```bash
for pair in \
  "C0:config/completion-gate/profiles/CG_C0_HISTORICAL_FIXED_CLUSTER.json" \
  "C1:config/completion-gate/profiles/CG_C1_PROVIDER_BACKED_BASELINE.json" \
  "C2:config/completion-gate/profiles/CG_C2_RESOURCE_VARIATION.json" \
  "C3:config/completion-gate/profiles/CG_C3_NODE_COUNT_VARIATION.json" \
  "C4:config/completion-gate/profiles/CG_C4_PLACEMENT_VARIATION.json" \
  "C5:config/completion-gate/profiles/CG_C5_LATENCY_INJECTION.json" \
  "C6:config/completion-gate/profiles/CG_C6_MULTI_TENANCY.json" \
  "C7:config/completion-gate/profiles/CG_C7_DEFAULT_SCHEDULER_BASELINE.json" \
  "C8:config/completion-gate/profiles/CG_C8_RESOURCE_AWARE_SCHEDULER.json" \
  "C9:config/completion-gate/profiles/CG_C9_NETWORK_AWARE_SCHEDULER.json"
do
  cycle="${pair%%:*}"
  profile="${pair#*:}"
  ./scripts/load/post/start-completion-gate.sh \
    --cycle-config "config/experimental-cycles/${cycle}.json" \
    --profile-config "$profile"
done
```

---

## Step 11 — Inspect Completion-Gate Status

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C*\completion-gate\latest-completion-gate-manifest.json |
  ForEach-Object {
    $data = Get-Content $_.FullName -Raw | ConvertFrom-Json
    [PSCustomObject]@{
      Cycle  = $_.FullName
      Status = $data.status
    }
  }
```

### Bash

```bash
python3 - <<'PY'
import json
from pathlib import Path

for path in sorted(Path("results/experimental-cycles").glob("C*/completion-gate/latest-completion-gate-manifest.json")):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"{path}: unreadable ({exc})")
        continue
    print(f"{path}: {data.get('status')}")
PY
```

Acceptable status values are profile-dependent, but the standard expected terminal states are:

```text
completed
completed_with_unsupported_scenarios
```

---

## Step 12 — Freeze One Cycle

The example below freezes `C1`.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-FreezeExperimentalCycle.ps1 `
  -RepoRoot . `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ProfileConfig .\config\freeze\profiles\FR_C1_PROVIDER_BACKED_BASELINE.json `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/load/post/start-freeze-experimental-cycle.sh \
  --repo-root . \
  --cycle-config config/experimental-cycles/C1.json \
  --profile-config config/freeze/profiles/FR_C1_PROVIDER_BACKED_BASELINE.json \
  --write-latest-aliases
```

Expected outputs:

```text
results/experimental-cycles/C1/freeze/latest-freeze-manifest.json
results/experimental-cycles/C1/freeze/latest-freeze-summary.txt
results/experimental-cycles/C1/freeze/C1-cycle-lock.json
results/experimental-cycles/C1/freeze/C1-cycle-lock.txt
results/experimental-cycles/C1/artifacts/
```

Use force only when intentionally replacing an existing freeze snapshot.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-FreezeExperimentalCycle.ps1 `
  -RepoRoot . `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ProfileConfig .\config\freeze\profiles\FR_C1_PROVIDER_BACKED_BASELINE.json `
  -Force `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/load/post/start-freeze-experimental-cycle.sh \
  --repo-root . \
  --cycle-config config/experimental-cycles/C1.json \
  --profile-config config/freeze/profiles/FR_C1_PROVIDER_BACKED_BASELINE.json \
  --force \
  --write-latest-aliases
```

---

## Step 13 — Freeze All Cycles

Freeze all cycles only after diagnosis, reporting, reporting-site refresh, and completion-gate evaluation have completed.

### Windows PowerShell

```powershell
$freezeProfiles = @(
  @{ Cycle = ".\config\experimental-cycles\C0.json"; Profile = ".\config\freeze\profiles\FR_C0_HISTORICAL_FIXED_CLUSTER.json" },
  @{ Cycle = ".\config\experimental-cycles\C1.json"; Profile = ".\config\freeze\profiles\FR_C1_PROVIDER_BACKED_BASELINE.json" },
  @{ Cycle = ".\config\experimental-cycles\C2.json"; Profile = ".\config\freeze\profiles\FR_C2_RESOURCE_VARIATION.json" },
  @{ Cycle = ".\config\experimental-cycles\C3.json"; Profile = ".\config\freeze\profiles\FR_C3_NODE_COUNT_VARIATION.json" },
  @{ Cycle = ".\config\experimental-cycles\C4.json"; Profile = ".\config\freeze\profiles\FR_C4_PLACEMENT_VARIATION.json" },
  @{ Cycle = ".\config\experimental-cycles\C5.json"; Profile = ".\config\freeze\profiles\FR_C5_LATENCY_INJECTION.json" },
  @{ Cycle = ".\config\experimental-cycles\C6.json"; Profile = ".\config\freeze\profiles\FR_C6_MULTI_TENANCY.json" },
  @{ Cycle = ".\config\experimental-cycles\C7.json"; Profile = ".\config\freeze\profiles\FR_C7_DEFAULT_SCHEDULER_BASELINE.json" },
  @{ Cycle = ".\config\experimental-cycles\C8.json"; Profile = ".\config\freeze\profiles\FR_C8_RESOURCE_AWARE_SCHEDULER.json" },
  @{ Cycle = ".\config\experimental-cycles\C9.json"; Profile = ".\config\freeze\profiles\FR_C9_NETWORK_AWARE_SCHEDULER.json" }
)

foreach ($item in $freezeProfiles) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File .\scripts\load\post\Start-FreezeExperimentalCycle.ps1 `
    -RepoRoot . `
    -CycleConfig $item.Cycle `
    -ProfileConfig $item.Profile `
    -WriteLatestAliases
}
```

### Bash

```bash
for pair in \
  "C0:config/freeze/profiles/FR_C0_HISTORICAL_FIXED_CLUSTER.json" \
  "C1:config/freeze/profiles/FR_C1_PROVIDER_BACKED_BASELINE.json" \
  "C2:config/freeze/profiles/FR_C2_RESOURCE_VARIATION.json" \
  "C3:config/freeze/profiles/FR_C3_NODE_COUNT_VARIATION.json" \
  "C4:config/freeze/profiles/FR_C4_PLACEMENT_VARIATION.json" \
  "C5:config/freeze/profiles/FR_C5_LATENCY_INJECTION.json" \
  "C6:config/freeze/profiles/FR_C6_MULTI_TENANCY.json" \
  "C7:config/freeze/profiles/FR_C7_DEFAULT_SCHEDULER_BASELINE.json" \
  "C8:config/freeze/profiles/FR_C8_RESOURCE_AWARE_SCHEDULER.json" \
  "C9:config/freeze/profiles/FR_C9_NETWORK_AWARE_SCHEDULER.json"
do
  cycle="${pair%%:*}"
  profile="${pair#*:}"
  ./scripts/load/post/start-freeze-experimental-cycle.sh \
    --repo-root . \
    --cycle-config "config/experimental-cycles/${cycle}.json" \
    --profile-config "$profile" \
    --write-latest-aliases
done
```

---

## Step 14 — Inspect Freeze Outputs

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C*\freeze\latest-freeze-manifest.json |
  ForEach-Object {
    $data = Get-Content $_.FullName -Raw | ConvertFrom-Json
    [PSCustomObject]@{
      Manifest = $_.FullName
      Cycle    = $data.cycleId
      Status   = $data.status
      FreezeId = $data.freezeId
    }
  }
```

### Bash

```bash
python3 - <<'PY'
import json
from pathlib import Path

for path in sorted(Path("results/experimental-cycles").glob("C*/freeze/latest-freeze-manifest.json")):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"{path}: unreadable ({exc})")
        continue
    print(f"{path}: cycle={data.get('cycleId')} status={data.get('status')} freezeId={data.get('freezeId')}")
PY
```

---

## Step 15 — Inspect Reporting Manifests

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C*\reporting\reporting-manifest.json |
  ForEach-Object {
    $data = Get-Content $_.FullName -Raw | ConvertFrom-Json
    [PSCustomObject]@{
      Manifest    = $_.FullName
      Cycle       = $data.cycleId
      ReportingId = $data.reportingId
      ReportHtml  = $data.reportHtmlPath
    }
  }
```

### Bash

```bash
python3 - <<'PY'
import json
from pathlib import Path

for path in sorted(Path("results/experimental-cycles").glob("C*/reporting/reporting-manifest.json")):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"{path}: unreadable ({exc})")
        continue
    print(f"{path}: cycle={data.get('cycleId')} reportingId={data.get('reportingId')} html={data.get('reportHtmlPath')}")
PY
```

---

## Step 16 — Inspect Scenario Summaries

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C*\reporting\scenario-summary.csv |
  ForEach-Object {
    Write-Host "`n$($_.FullName)"
    Import-Csv $_.FullName | Select-Object -First 5 | Format-Table -AutoSize
  }
```

### Bash

```bash
python3 - <<'PY'
import csv
from pathlib import Path

for path in sorted(Path("results/experimental-cycles").glob("C*/reporting/scenario-summary.csv")):
    print(f"\n{path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for idx, row in enumerate(reader):
            if idx >= 5:
                break
            print(row)
PY
```

Scenario summaries are useful for verifying that each report consumed the intended benchmark evidence and preserved the expected scenario labels.

---

## Step 17 — Inspect Diagnosis Findings

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C*\diagnosis\*_diagnosis.json |
  Sort-Object FullName |
  ForEach-Object {
    $data = Get-Content $_.FullName -Raw | ConvertFrom-Json
    [PSCustomObject]@{
      File       = $_.FullName
      Family     = $data.diagnosis.familyScope
      Cycle      = $data.diagnosis.cycleId
      FindingCnt = @($data.findings).Count
      Status     = $data.diagnosis.status
    }
  }
```

### Bash

```bash
python3 - <<'PY'
import json
from pathlib import Path

for path in sorted(Path("results/experimental-cycles").glob("C*/diagnosis/*_diagnosis.json")):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        print(f"{path}: unreadable ({exc})")
        continue
    diagnosis = data.get("diagnosis") or {}
    findings = data.get("findings") or []
    print(f"{path}: cycle={diagnosis.get('cycleId')} family={diagnosis.get('familyScope')} findings={len(findings)} status={diagnosis.get('status')}")
PY
```

---

## Step 18 — End-to-End Post-Processing Regeneration

Use this procedure only after the benchmark artifacts for all cycles already exist.

### Windows PowerShell

```powershell
# 1. Technical diagnosis
$diagnosisProfiles = @(
  ".\config\technical-diagnosis\profiles\TD_C0_HISTORICAL_FIXED_CLUSTER.json",
  ".\config\technical-diagnosis\profiles\TD_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\technical-diagnosis\profiles\TD_C2_RESOURCE_VARIATION.json",
  ".\config\technical-diagnosis\profiles\TD_C3_NODE_COUNT_VARIATION.json",
  ".\config\technical-diagnosis\profiles\TD_C4_PLACEMENT_VARIATION.json",
  ".\config\technical-diagnosis\profiles\TD_C5_LATENCY_INJECTION.json",
  ".\config\technical-diagnosis\profiles\TD_C6_MULTI_TENANCY.json",
  ".\config\technical-diagnosis\profiles\TD_C7_DEFAULT_SCHEDULER_BASELINE.json",
  ".\config\technical-diagnosis\profiles\TD_C8_RESOURCE_AWARE_SCHEDULER.json",
  ".\config\technical-diagnosis\profiles\TD_C9_NETWORK_AWARE_SCHEDULER.json"
)
foreach ($profile in $diagnosisProfiles) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\load\post\Start-TechnicalDiagnosis.ps1 -ProfileConfig $profile -Family all
}

# 2. Reporting
$reportingProfiles = @(
  ".\config\reporting\profiles\RP_C0_HISTORICAL_FIXED_CLUSTER.json",
  ".\config\reporting\profiles\RP_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\reporting\profiles\RP_C2_RESOURCE_VARIATION.json",
  ".\config\reporting\profiles\RP_C3_NODE_COUNT_VARIATION.json",
  ".\config\reporting\profiles\RP_C4_PLACEMENT_VARIATION.json",
  ".\config\reporting\profiles\RP_C5_LATENCY_INJECTION.json",
  ".\config\reporting\profiles\RP_C6_MULTI_TENANCY.json",
  ".\config\reporting\profiles\RP_C7_DEFAULT_SCHEDULER_BASELINE.json",
  ".\config\reporting\profiles\RP_C8_RESOURCE_AWARE_SCHEDULER.json",
  ".\config\reporting\profiles\RP_C9_NETWORK_AWARE_SCHEDULER.json"
)
foreach ($profile in $reportingProfiles) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\load\post\Start-Reporting.ps1 -ProfileConfig $profile
}

# 3. Reporting site
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\load\post\Start-ReportingSite.ps1 -SiteConfig .\config\reporting\site\REPORTING_SITE.json

# 4. Completion gate
$completionGateProfiles = @(
  @{ Cycle = ".\config\experimental-cycles\C0.json"; Profile = ".\config\completion-gate\profiles\CG_C0_HISTORICAL_FIXED_CLUSTER.json" },
  @{ Cycle = ".\config\experimental-cycles\C1.json"; Profile = ".\config\completion-gate\profiles\CG_C1_PROVIDER_BACKED_BASELINE.json" },
  @{ Cycle = ".\config\experimental-cycles\C2.json"; Profile = ".\config\completion-gate\profiles\CG_C2_RESOURCE_VARIATION.json" },
  @{ Cycle = ".\config\experimental-cycles\C3.json"; Profile = ".\config\completion-gate\profiles\CG_C3_NODE_COUNT_VARIATION.json" },
  @{ Cycle = ".\config\experimental-cycles\C4.json"; Profile = ".\config\completion-gate\profiles\CG_C4_PLACEMENT_VARIATION.json" },
  @{ Cycle = ".\config\experimental-cycles\C5.json"; Profile = ".\config\completion-gate\profiles\CG_C5_LATENCY_INJECTION.json" },
  @{ Cycle = ".\config\experimental-cycles\C6.json"; Profile = ".\config\completion-gate\profiles\CG_C6_MULTI_TENANCY.json" },
  @{ Cycle = ".\config\experimental-cycles\C7.json"; Profile = ".\config\completion-gate\profiles\CG_C7_DEFAULT_SCHEDULER_BASELINE.json" },
  @{ Cycle = ".\config\experimental-cycles\C8.json"; Profile = ".\config\completion-gate\profiles\CG_C8_RESOURCE_AWARE_SCHEDULER.json" },
  @{ Cycle = ".\config\experimental-cycles\C9.json"; Profile = ".\config\completion-gate\profiles\CG_C9_NETWORK_AWARE_SCHEDULER.json" }
)
foreach ($item in $completionGateProfiles) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\load\post\Start-CompletionGate.ps1 -CycleConfig $item.Cycle -ProfileConfig $item.Profile
}

# 5. Freeze
$freezeProfiles = @(
  @{ Cycle = ".\config\experimental-cycles\C0.json"; Profile = ".\config\freeze\profiles\FR_C0_HISTORICAL_FIXED_CLUSTER.json" },
  @{ Cycle = ".\config\experimental-cycles\C1.json"; Profile = ".\config\freeze\profiles\FR_C1_PROVIDER_BACKED_BASELINE.json" },
  @{ Cycle = ".\config\experimental-cycles\C2.json"; Profile = ".\config\freeze\profiles\FR_C2_RESOURCE_VARIATION.json" },
  @{ Cycle = ".\config\experimental-cycles\C3.json"; Profile = ".\config\freeze\profiles\FR_C3_NODE_COUNT_VARIATION.json" },
  @{ Cycle = ".\config\experimental-cycles\C4.json"; Profile = ".\config\freeze\profiles\FR_C4_PLACEMENT_VARIATION.json" },
  @{ Cycle = ".\config\experimental-cycles\C5.json"; Profile = ".\config\freeze\profiles\FR_C5_LATENCY_INJECTION.json" },
  @{ Cycle = ".\config\experimental-cycles\C6.json"; Profile = ".\config\freeze\profiles\FR_C6_MULTI_TENANCY.json" },
  @{ Cycle = ".\config\experimental-cycles\C7.json"; Profile = ".\config\freeze\profiles\FR_C7_DEFAULT_SCHEDULER_BASELINE.json" },
  @{ Cycle = ".\config\experimental-cycles\C8.json"; Profile = ".\config\freeze\profiles\FR_C8_RESOURCE_AWARE_SCHEDULER.json" },
  @{ Cycle = ".\config\experimental-cycles\C9.json"; Profile = ".\config\freeze\profiles\FR_C9_NETWORK_AWARE_SCHEDULER.json" }
)
foreach ($item in $freezeProfiles) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\load\post\Start-FreezeExperimentalCycle.ps1 -RepoRoot . -CycleConfig $item.Cycle -ProfileConfig $item.Profile -WriteLatestAliases
}
```

### Bash

```bash
# 1. Technical diagnosis
for profile in \
  config/technical-diagnosis/profiles/TD_C0_HISTORICAL_FIXED_CLUSTER.json \
  config/technical-diagnosis/profiles/TD_C1_PROVIDER_BACKED_BASELINE.json \
  config/technical-diagnosis/profiles/TD_C2_RESOURCE_VARIATION.json \
  config/technical-diagnosis/profiles/TD_C3_NODE_COUNT_VARIATION.json \
  config/technical-diagnosis/profiles/TD_C4_PLACEMENT_VARIATION.json \
  config/technical-diagnosis/profiles/TD_C5_LATENCY_INJECTION.json \
  config/technical-diagnosis/profiles/TD_C6_MULTI_TENANCY.json \
  config/technical-diagnosis/profiles/TD_C7_DEFAULT_SCHEDULER_BASELINE.json \
  config/technical-diagnosis/profiles/TD_C8_RESOURCE_AWARE_SCHEDULER.json \
  config/technical-diagnosis/profiles/TD_C9_NETWORK_AWARE_SCHEDULER.json
do
  ./scripts/load/post/start-technical-diagnosis.sh --profile-config "$profile" --family all
done

# 2. Reporting
for profile in \
  config/reporting/profiles/RP_C0_HISTORICAL_FIXED_CLUSTER.json \
  config/reporting/profiles/RP_C1_PROVIDER_BACKED_BASELINE.json \
  config/reporting/profiles/RP_C2_RESOURCE_VARIATION.json \
  config/reporting/profiles/RP_C3_NODE_COUNT_VARIATION.json \
  config/reporting/profiles/RP_C4_PLACEMENT_VARIATION.json \
  config/reporting/profiles/RP_C5_LATENCY_INJECTION.json \
  config/reporting/profiles/RP_C6_MULTI_TENANCY.json \
  config/reporting/profiles/RP_C7_DEFAULT_SCHEDULER_BASELINE.json \
  config/reporting/profiles/RP_C8_RESOURCE_AWARE_SCHEDULER.json \
  config/reporting/profiles/RP_C9_NETWORK_AWARE_SCHEDULER.json
do
  ./scripts/load/post/start-reporting.sh --profile-config "$profile"
done

# 3. Reporting site
./scripts/load/post/start-reporting-site.sh \
  --site-config config/reporting/site/REPORTING_SITE.json

# 4. Completion gate
for pair in \
  "C0:config/completion-gate/profiles/CG_C0_HISTORICAL_FIXED_CLUSTER.json" \
  "C1:config/completion-gate/profiles/CG_C1_PROVIDER_BACKED_BASELINE.json" \
  "C2:config/completion-gate/profiles/CG_C2_RESOURCE_VARIATION.json" \
  "C3:config/completion-gate/profiles/CG_C3_NODE_COUNT_VARIATION.json" \
  "C4:config/completion-gate/profiles/CG_C4_PLACEMENT_VARIATION.json" \
  "C5:config/completion-gate/profiles/CG_C5_LATENCY_INJECTION.json" \
  "C6:config/completion-gate/profiles/CG_C6_MULTI_TENANCY.json" \
  "C7:config/completion-gate/profiles/CG_C7_DEFAULT_SCHEDULER_BASELINE.json" \
  "C8:config/completion-gate/profiles/CG_C8_RESOURCE_AWARE_SCHEDULER.json" \
  "C9:config/completion-gate/profiles/CG_C9_NETWORK_AWARE_SCHEDULER.json"
do
  cycle="${pair%%:*}"
  profile="${pair#*:}"
  ./scripts/load/post/start-completion-gate.sh \
    --cycle-config "config/experimental-cycles/${cycle}.json" \
    --profile-config "$profile"
done

# 5. Freeze
for pair in \
  "C0:config/freeze/profiles/FR_C0_HISTORICAL_FIXED_CLUSTER.json" \
  "C1:config/freeze/profiles/FR_C1_PROVIDER_BACKED_BASELINE.json" \
  "C2:config/freeze/profiles/FR_C2_RESOURCE_VARIATION.json" \
  "C3:config/freeze/profiles/FR_C3_NODE_COUNT_VARIATION.json" \
  "C4:config/freeze/profiles/FR_C4_PLACEMENT_VARIATION.json" \
  "C5:config/freeze/profiles/FR_C5_LATENCY_INJECTION.json" \
  "C6:config/freeze/profiles/FR_C6_MULTI_TENANCY.json" \
  "C7:config/freeze/profiles/FR_C7_DEFAULT_SCHEDULER_BASELINE.json" \
  "C8:config/freeze/profiles/FR_C8_RESOURCE_AWARE_SCHEDULER.json" \
  "C9:config/freeze/profiles/FR_C9_NETWORK_AWARE_SCHEDULER.json"
do
  cycle="${pair%%:*}"
  profile="${pair#*:}"
  ./scripts/load/post/start-freeze-experimental-cycle.sh \
    --repo-root . \
    --cycle-config "config/experimental-cycles/${cycle}.json" \
    --profile-config "$profile" \
    --write-latest-aliases
done
```

---

## Step 19 — Integrated Post-Processing Through Cycle Runners

For normal regeneration, prefer the complete cycle or campaign runbooks. They execute post-processing as part of the end-to-end workflow.

### Provider-Backed Baseline

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCycle.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ExecutionScope provider-backed-cycle `
  -ToolPath proxmox-k3s `
  -BaselineReplicas A,B,C `
  -AllowMetricsWarning `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config config/experimental-cycles/C1.json \
  --execution-scope provider-backed-cycle \
  --tool-path proxmox-k3s \
  --baseline-replicas A,B,C \
  --allow-metrics-warning \
  --write-latest-aliases
```

### Provider-Backed Campaign

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C2.json `
  -ToolPath proxmox-k3s `
  -BaselineReplicas A,B,C `
  -AllowMetricsWarning `
  -ContinueOnFailure `
  -ConfirmDelete `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config config/experimental-cycles/C2.json \
  --tool-path proxmox-k3s \
  --baseline-replicas A,B,C \
  --allow-metrics-warning \
  --continue-on-failure \
  --confirm-delete \
  --force-freeze \
  --write-latest-aliases
```

Use the isolated post-processing commands in this runbook when benchmark artifacts are already present and only the analysis/reporting/gate/freeze layers need to be regenerated.

---

## Step 20 — Post-Processing Dry Runs

Dry runs are useful to validate profile resolution before generating or replacing artifacts.

### Technical Diagnosis Dry Run

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-TechnicalDiagnosis.ps1 `
  -ProfileConfig .\config\technical-diagnosis\profiles\TD_C1_PROVIDER_BACKED_BASELINE.json `
  -Family all `
  -DryRun
```

### Bash

```bash
./scripts/load/post/start-technical-diagnosis.sh \
  --profile-config config/technical-diagnosis/profiles/TD_C1_PROVIDER_BACKED_BASELINE.json \
  --family all \
  --dry-run
```

### Completion Gate Dry Run

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-CompletionGate.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ProfileConfig .\config\completion-gate\profiles\CG_C1_PROVIDER_BACKED_BASELINE.json `
  -DryRun
```

### Bash

```bash
./scripts/load/post/start-completion-gate.sh \
  --cycle-config config/experimental-cycles/C1.json \
  --profile-config config/completion-gate/profiles/CG_C1_PROVIDER_BACKED_BASELINE.json \
  --dry-run
```

### Freeze Dry Run

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-FreezeExperimentalCycle.ps1 `
  -RepoRoot . `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ProfileConfig .\config\freeze\profiles\FR_C1_PROVIDER_BACKED_BASELINE.json `
  -DryRun
```

### Bash

```bash
./scripts/load/post/start-freeze-experimental-cycle.sh \
  --repo-root . \
  --cycle-config config/experimental-cycles/C1.json \
  --profile-config config/freeze/profiles/FR_C1_PROVIDER_BACKED_BASELINE.json \
  --dry-run
```

---

## Step 21 — Inspect Reporting Site Files

### Windows PowerShell

```powershell
Get-ChildItem .\results\reporting -Force
Get-ChildItem .\results\reporting\cycles -Directory -ErrorAction SilentlyContinue
```

### Bash

```bash
ls -la results/reporting
find results/reporting/cycles -maxdepth 1 -type d 2>/dev/null
```

The global site must not be treated as a replacement for cycle-scoped reports. Its purpose is to expose a stable navigation entry point.

---

## Step 22 — Open Generated HTML Reports Locally

### Windows PowerShell

```powershell
Start-Process .\results\reporting\index.html
Start-Process .\results\experimental-cycles\C1\reporting\index.html
```

### Bash

```bash
python3 -m webbrowser "file://$(pwd)/results/reporting/index.html"
python3 -m webbrowser "file://$(pwd)/results/experimental-cycles/C1/reporting/index.html"
```

If the local shell does not support graphical browser opening, copy the resolved file path and open it manually.

---

## Step 23 — Archive Current Report Before Regeneration

Use report archiving before regenerating a cycle-scoped report when the previous report must be retained for comparison.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-Reporting.ps1 `
  -ProfileConfig .\config\reporting\profiles\RP_C1_PROVIDER_BACKED_BASELINE.json `
  -ArchiveCurrent
```

### Bash

```bash
./scripts/load/post/start-reporting.sh \
  --profile-config config/reporting/profiles/RP_C1_PROVIDER_BACKED_BASELINE.json \
  --archive-current
```

To regenerate and archive in the same operation:

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-Reporting.ps1 `
  -ProfileConfig .\config\reporting\profiles\RP_C1_PROVIDER_BACKED_BASELINE.json `
  -Archive
```

### Bash

```bash
./scripts/load/post/start-reporting.sh \
  --profile-config config/reporting/profiles/RP_C1_PROVIDER_BACKED_BASELINE.json \
  --archive
```

---

## C9 Network-Aware Post-Processing Evidence

C9 post-processing must preserve enough evidence to explain whether the network-aware scheduler received usable telemetry and whether that telemetry influenced placement.

Diagnosis, reporting, completion-gate, and freeze outputs should expose the following evidence classes:

```text
Istio Gateway and VirtualService routing evidence
mon-agent node and deployment annotation evidence
Mentat internode latency, packet-loss, and bandwidth evidence
gateway traffic key resolution evidence
telemetry-priming evidence
telemetry-primed rescheduling evidence
cluster-lens placement summary, placement signature, and capture manifest evidence
scheduler decision evidence for DEFAULT, LOADAWARE, and NETAWARE variants
benchmark evidence with offered load, throughput, latency, errors, and timeouts
```

The completion gate must not treat a network-aware run as fully complete when the required network-aware telemetry or placement evidence is missing. Such cases should be reported as validation failures or inconclusive telemetry evidence, depending on the available artifacts.

---

## Quality Rules

A post-processing package is valid only when the following conditions hold:

1. the cycle or campaign benchmark artifacts exist before diagnosis is generated;
2. diagnosis is generated with the intended cycle-specific profile;
3. reporting is generated after diagnosis when diagnosis context is expected by the reporting profile;
4. reporting artifacts include both human-readable and machine-readable outputs;
5. the global reporting site is refreshed after cycle-scoped reports have been generated;
6. completion gate is evaluated after reporting;
7. freeze is generated only after an accepted completion-gate state;
8. freeze snapshots include configuration references and generated runtime evidence;
9. unsupported scenarios remain visible in diagnosis, reporting, completion gate, and freeze artifacts;
10. no local kubeconfig, provider credential, VPN file, SSH key, or provider-local YAML is copied into a publishable evidence package.

---

## Unsupported Scenario Handling

Unsupported scenarios must be interpreted through their cycle context.

They are valid evidence when caused by a controlled experimental condition such as:

1. insufficient CPU;
2. insufficient memory;
3. unschedulable placement;
4. rollout timeout under a constrained topology;
5. intentionally extreme latency profile;
6. aggressive multi-tenant resource contention;
7. unavailable metrics that are explicitly allowed by the execution profile.

They are not valid evidence when caused by:

1. wrong kubeconfig;
2. wrong namespace;
3. missing provider-local configuration;
4. accidental cluster deletion;
5. wrong model identifier;
6. failed local Python environment;
7. incomplete benchmark artifact cleanup;
8. manually edited generated runtime profiles.

The completion gate should distinguish accepted unsupported evidence from execution errors whenever the corresponding profile policy supports it.

---

## Artifact Hygiene

Follow these rules when regenerating post-processing artifacts:

1. do not manually edit files under `results/`;
2. do not copy old diagnosis files into a new cycle root;
3. do not mix `C0` fixed-cluster artifacts with `C1-C9` provider-backed artifacts;
4. do not delete freeze snapshots unless the full regeneration procedure requires it;
5. use `-Force` or `--force` for freeze only when intentionally replacing an existing snapshot;
6. preserve timestamped artifacts when comparing multiple post-processing runs;
7. use latest aliases only as convenience pointers, not as the only source of evidence;
8. never publish local provider config, kubeconfig, VPN files, SSH keys, or credentials.

---

## Troubleshooting

### Diagnosis Cannot Find Measurements

Verify the benchmark roots expected by the profile.

### Windows PowerShell

```powershell
Get-Content .\config\technical-diagnosis\profiles\TD_C1_PROVIDER_BACKED_BASELINE.json -Raw |
  ConvertFrom-Json |
  Select-Object -ExpandProperty campaignResultsRoots
```

### Bash

```bash
python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("config/technical-diagnosis/profiles/TD_C1_PROVIDER_BACKED_BASELINE.json").read_text(encoding="utf-8-sig"))
print(json.dumps(data.get("campaignResultsRoots", {}), indent=2))
PY
```

Then verify that the referenced files exist under `results/`.

### Reporting Generates Empty Charts

Verify that the scenario summary exists and contains rows.

### Windows PowerShell

```powershell
Import-Csv .\results\experimental-cycles\C1\reporting\scenario-summary.csv | Measure-Object
```

### Bash

```bash
python3 - <<'PY'
import csv
from pathlib import Path
path = Path("results/experimental-cycles/C1/reporting/scenario-summary.csv")
with path.open("r", encoding="utf-8-sig", newline="") as handle:
    rows = list(csv.DictReader(handle))
print(len(rows))
PY
```

### Completion Gate Fails Because Diagnosis Is Missing

Regenerate diagnosis before evaluating the completion gate.

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

### Freeze Fails Because Completion Gate Is Missing

Regenerate completion gate before freezing.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\load\post\Start-CompletionGate.ps1 `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ProfileConfig .\config\completion-gate\profiles\CG_C1_PROVIDER_BACKED_BASELINE.json
```

### Bash

```bash
./scripts/load/post/start-completion-gate.sh \
  --cycle-config config/experimental-cycles/C1.json \
  --profile-config config/completion-gate/profiles/CG_C1_PROVIDER_BACKED_BASELINE.json
```

### Reporting Site Does Not Show a Cycle

Verify that the cycle report contains the required HTML report and manifest.

### Windows PowerShell

```powershell
Test-Path .\results\experimental-cycles\C1\reporting\index.html
Test-Path .\results\experimental-cycles\C1\reporting\reporting-manifest.json
```

### Bash

```bash
test -f results/experimental-cycles/C1/reporting/index.html
test -f results/experimental-cycles/C1/reporting/reporting-manifest.json
```

Then refresh the reporting site.

---

## Final Post-Processing Checklist

Before considering a cycle evidence package complete, verify that:

- [ ] benchmark and runtime artifacts exist for the intended cycle;
- [ ] technical diagnosis was generated with the cycle-specific profile;
- [ ] reporting was generated with the cycle-specific profile;
- [ ] `report.md`, `index.html`, `scenario-summary.csv`, and `reporting-manifest.json` exist;
- [ ] the global reporting site was refreshed;
- [ ] completion gate was evaluated with the cycle-specific profile;
- [ ] completion status is accepted by the freeze profile;
- [ ] freeze was generated with the cycle-specific freeze profile;
- [ ] freeze lock files and snapshot artifacts exist;
- [ ] unsupported scenarios, if any, remain visible in the evidence chain;
- [ ] for C7, scheduler decision evidence and placement classification remain visible in diagnosis and reporting;
- [ ] for C8, paired resource-aware scheduler evidence, mon-agent annotation evidence, rescheduling evidence, and scheduler decision evidence remain visible in diagnosis and reporting;
- [ ] for C9, gateway-routed traffic, network-aware telemetry, cluster-lens placement evidence, telemetry-primed rescheduling, scheduler decision evidence, and triplet comparison evidence remain visible in diagnosis and reporting;
- [ ] no sensitive local access material is included in generated publishable artifacts.

---

## Next Runbook

After understanding diagnosis, reporting, completion gates, and freeze, continue with:

```text
docs/runbooks/15-results-cleanup-and-full-regeneration.md
```
