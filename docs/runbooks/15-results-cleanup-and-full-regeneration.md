# Results Cleanup and Full Regeneration

## Purpose

This runbook defines the operational procedure for removing generated benchmark artifacts and regenerating the complete benchmark evidence set from a clean `results/` tree.

The procedure covers the complete execution order:

```text
C0 fixed-cluster historical cycle
→ C1 provider-backed baseline cycle
→ C2 resource-variation campaign
→ C3 node-count-variation campaign
→ C4 placement-variation campaign
→ C5 latency-injection campaign
→ C6 multi-tenancy campaign
→ C7 default-scheduler baseline campaign
→ C8 resource-aware scheduler campaign
→ C9 network-aware scheduler campaign with cluster-lens placement evidence
→ global reporting-site regeneration
→ final artifact validation
```

The procedure assumes that configuration profiles, scripts, Kubernetes manifests, local access files, and provider-local configuration files are already in place. It does not recreate sensitive configuration files and does not modify source profiles.

---

## Scope

This runbook covers:

1. safe cleanup of generated artifacts under `results/`;
2. optional archival of the current `results/` tree before deletion;
3. validation of repository prerequisites before regeneration;
4. regeneration of the fixed-cluster `C0` evidence set;
5. regeneration of provider-backed `C1`;
6. regeneration of provider-backed comparative campaigns `C2` through `C6`;
7. regeneration of the `C7` default-scheduler baseline campaign;
8. regeneration of the `C8` resource-aware scheduler campaign;
9. regeneration of the `C9` network-aware scheduler campaign, including cluster-lens placement evidence;
10. regeneration of the global reporting site;
11. verification of the regenerated artifact tree;
12. rerun and recovery rules after partial failures.

This runbook does not replace the detailed cycle-specific runbooks. It provides the recommended global execution order and the cleanup/regeneration workflow. For detailed cycle-level execution semantics, use:

```text
docs/runbooks/06-fixed-cluster-c0-execution.md
docs/runbooks/07-provider-backed-c1-baseline-execution.md
docs/runbooks/08-provider-backed-c2-c6-campaign-execution.md
docs/runbooks/09-default-scheduler-c7-baseline-execution.md
docs/runbooks/10-resource-aware-scheduler-c8-execution.md
docs/runbooks/11-network-aware-scheduler-c9-execution.md
docs/runbooks/13-load-generation-observability-and-artifacts.md
docs/runbooks/14-diagnosis-reporting-completion-gate-and-freeze.md
```

---

## Results Currency and Regeneration Note

The `results/` tree is generated evidence, not source configuration. If it was produced from the current repository state, it can be used for inspection, reporting review, completion-gate evaluation, and freeze validation. If source configuration, scripts, manifests, scheduler profiles, latency profiles, cluster-lens capture policy, reporting logic, or provider-local inputs changed after the run, regenerate the affected cycle before treating the artifacts as current evidence.

For C9, current evidence should include the expanded 14-logical-scenario / 42-variant matrix, `L3_INTER_GROUP_EXTREME` latency scenarios, primary cluster-lens placement artifacts, network-aware diagnosis, C9 reporting, completion-gate output, freeze output, and reporting-site files.

---

## Cleanup Boundaries

The cleanup procedure must remove generated artifacts only.

The following path is disposable and may be regenerated:

```text
results/
```

The following paths must not be removed by this runbook:

```text
config/
infra/
scripts/
load-tests/
docs/
config/cluster-access/fixed-cluster/kubeconfig
config/cluster-access/generated/
config/infrastructure/providers/proxmox-k3s/local/
```

The generated `results/` tree may contain benchmark CSV files, runtime manifests, diagnosis outputs, reporting files, completion-gate outputs, frozen snapshots, infrastructure logs, cluster-capture evidence, and latest aliases. All of these are execution artifacts.

---

## Required Execution Discipline

Follow the rules below during cleanup and regeneration.

1. Run commands from the repository root.
2. Keep a stable shell session for the full regeneration whenever possible.
3. Do not rely on the default Kubernetes context.
4. Keep `localai-benchmark` as the canonical single-tenant namespace.
5. Do not delete fixed-cluster or provider-backed kubeconfig files during results cleanup.
6. Do not delete local provider YAML files during results cleanup.
7. Regenerate cycles in order: `C0`, `C1`, `C2`, `C3`, `C4`, `C5`, `C6`, `C7`, `C8`, `C9`.
8. Treat unsupported scenarios as valid methodological evidence when they are produced by declared constraints.
9. Use `ContinueOnFailure` / `--continue-on-failure` for comparative campaigns so that unsupported variants do not prevent the remaining variants from being evaluated.
10. Do not run concurrent provider-backed campaigns against the same reusable provider identity.

---

## Step 1 — Move to the Repository Root

### Windows PowerShell

```powershell
Set-Location C:\path\to\localai-worker-mode-benchmark-suite
Get-Location
```

### Bash

```bash
cd /path/to/localai-worker-mode-benchmark-suite
pwd
```

Expected outcome: the current directory contains at least the following entries:

```text
config/
docs/
infra/
load-tests/
scripts/
```

---

## Step 2 — Verify the Required Runbook Set

Before deleting artifacts, verify that the operational documentation set is present.

### Windows PowerShell

```powershell
$Runbooks = @(
  ".\docs\runbooks\00-runbooks-index.md",
  ".\docs\runbooks\01-execution-model-and-repository-map.md",
  ".\docs\runbooks\02-local-environment-and-tooling.md",
  ".\docs\runbooks\03-access-secrets-and-local-configuration.md",
  ".\docs\runbooks\04-proxmox-k3s-provider-lifecycle.md",
  ".\docs\runbooks\05-configuration-model-and-cycle-taxonomy.md",
  ".\docs\runbooks\06-fixed-cluster-c0-execution.md",
  ".\docs\runbooks\07-provider-backed-c1-baseline-execution.md",
  ".\docs\runbooks\08-provider-backed-c2-c6-campaign-execution.md",
  ".\docs\runbooks\09-default-scheduler-c7-baseline-execution.md",
  ".\docs\runbooks\10-resource-aware-scheduler-c8-execution.md",
  ".\docs\runbooks\11-network-aware-scheduler-c9-execution.md",
  ".\docs\runbooks\12-localai-deployment-topologies-and-placement.md",
  ".\docs\runbooks\13-load-generation-observability-and-artifacts.md",
  ".\docs\runbooks\14-diagnosis-reporting-completion-gate-and-freeze.md",
  ".\docs\runbooks\15-results-cleanup-and-full-regeneration.md",
  ".\docs\runbooks\16-troubleshooting-and-recovery.md",
  ".\docs\runbooks\17-command-reference.md"
)

foreach ($Runbook in $Runbooks) {
  if (-not (Test-Path $Runbook)) {
    throw "Missing runbook: $Runbook"
  }
}
```

### Bash

```bash
runbooks=(
  "./docs/runbooks/00-runbooks-index.md"
  "./docs/runbooks/01-execution-model-and-repository-map.md"
  "./docs/runbooks/02-local-environment-and-tooling.md"
  "./docs/runbooks/03-access-secrets-and-local-configuration.md"
  "./docs/runbooks/04-proxmox-k3s-provider-lifecycle.md"
  "./docs/runbooks/05-configuration-model-and-cycle-taxonomy.md"
  "./docs/runbooks/06-fixed-cluster-c0-execution.md"
  "./docs/runbooks/07-provider-backed-c1-baseline-execution.md"
  "./docs/runbooks/08-provider-backed-c2-c6-campaign-execution.md"
  "./docs/runbooks/09-default-scheduler-c7-baseline-execution.md"
  "./docs/runbooks/10-resource-aware-scheduler-c8-execution.md"
  "./docs/runbooks/11-network-aware-scheduler-c9-execution.md"
  "./docs/runbooks/12-localai-deployment-topologies-and-placement.md"
  "./docs/runbooks/13-load-generation-observability-and-artifacts.md"
  "./docs/runbooks/14-diagnosis-reporting-completion-gate-and-freeze.md"
  "./docs/runbooks/15-results-cleanup-and-full-regeneration.md"
  "./docs/runbooks/16-troubleshooting-and-recovery.md"
  "./docs/runbooks/17-command-reference.md"
)

for runbook in "${runbooks[@]}"; do
  test -f "$runbook" || { echo "Missing runbook: $runbook" >&2; exit 1; }
done
```

---

## Step 3 — Stop Local Interactive Processes

Before deleting generated artifacts, stop any local port-forward, Locust, or manually launched benchmark command that may still be running.

### Windows PowerShell

```powershell
Get-Process |
  Where-Object { $_.ProcessName -match "kubectl|locust|python|python3|py" } |
  Select-Object Id, ProcessName, StartTime
```

### Bash

```bash
ps aux | grep -E "kubectl|locust|python|python3" | grep -v grep || true
```

If an active process is part of a currently running benchmark, do not continue until the execution is complete or intentionally stopped.

---

## Step 4 — Optional Archive of the Current Results Tree

Archiving is optional. Use it when the current `results/` tree must be preserved outside the repository before cleanup.

### Windows PowerShell

```powershell
$ArchiveRoot = "..\benchmark-results-archive"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"

New-Item -ItemType Directory -Force -Path $ArchiveRoot | Out-Null

if (Test-Path .\results) {
  Compress-Archive `
    -Path .\results\* `
    -DestinationPath (Join-Path $ArchiveRoot "results_$Stamp.zip") `
    -Force
}
```

### Bash

```bash
ARCHIVE_ROOT="../benchmark-results-archive"
STAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$ARCHIVE_ROOT"

if [ -d "./results" ]; then
  tar -czf "$ARCHIVE_ROOT/results_$STAMP.tar.gz" -C ./results .
fi
```

The archive is stored outside the repository root to avoid mixing archived evidence with newly generated artifacts.

---

## Step 5 — Clean the Results Tree

Remove all generated artifacts under `results/` while preserving or recreating the directory itself.

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

## Step 6 — Verify the Clean Results State

### Windows PowerShell

```powershell
Get-ChildItem .\results -Force
```

### Bash

```bash
ls -la ./results
```

Expected clean state:

```text
results/
└── .gitkeep
```

If additional generated directories remain, stop and inspect them before proceeding.

---

## Step 7 — Validate Configuration Files

Validate all JSON profiles before running the regeneration sequence.

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
  python -m json.tool "$file" >/dev/null || {
    echo "Invalid JSON file: $file" >&2
    exit 1
  }
done
```

---

## Step 8 — Verify Required Local Configuration

The full regeneration requires both fixed-cluster access and provider-backed local configuration.

### Windows PowerShell

```powershell
$RequiredLocalFiles = @(
  ".\config\cluster-access\fixed-cluster\kubeconfig",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c2-1cp-2w-4c8g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c2-1cp-2w-4c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c2-1cp-2w-8c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c3-1cp-2w-8c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c3-1cp-3w-8c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c3-1cp-4w-8c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c4-1cp-4w-8c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c5-1cp-4w-8c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c6-1cp-4w-8c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c7-1cp-2w-8c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c7-1cp-3w-8c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c7-1cp-4w-8c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c8-1cp-2w-8c16g.local.yaml",
  ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c8-1cp-4w-8c16g.local.yaml"
)

foreach ($File in $RequiredLocalFiles) {
  if (-not (Test-Path $File)) {
    throw "Missing local execution file: $File"
  }
}
```

### Bash

```bash
required_local_files=(
  "./config/cluster-access/fixed-cluster/kubeconfig"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c2-1cp-2w-4c8g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c2-1cp-2w-4c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c2-1cp-2w-8c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c3-1cp-2w-8c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c3-1cp-3w-8c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c3-1cp-4w-8c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c4-1cp-4w-8c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c5-1cp-4w-8c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c6-1cp-4w-8c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c7-1cp-2w-8c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c7-1cp-3w-8c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c7-1cp-4w-8c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c8-1cp-2w-8c16g.local.yaml"
  "./config/infrastructure/providers/proxmox-k3s/local/cluster.c8-1cp-4w-8c16g.local.yaml"
)

for file in "${required_local_files[@]}"; do
  test -f "$file" || { echo "Missing local execution file: $file" >&2; exit 1; }
done
```

If the provider-backed campaign is intentionally executed with only a subset of local YAML files, validate that the corresponding campaign variants are either excluded or expected to fail at the provider-configuration gate.

---

## Step 9 — Verify Core Executables

### Windows PowerShell

```powershell
$RequiredCommands = @("python", "kubectl")
foreach ($CommandName in $RequiredCommands) {
  if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
    throw "Required command not found in PATH: $CommandName"
  }
}

if (-not (Get-Command "proxmox-k3s" -ErrorAction SilentlyContinue)) {
  Write-Warning "proxmox-k3s not found in PATH. Use an explicit -ToolPath value when running provider-backed cycles."
}
```

### Bash

```bash
command -v python >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1 || {
  echo "Required command not found: python or python3" >&2
  exit 1
}

command -v kubectl >/dev/null 2>&1 || {
  echo "Required command not found: kubectl" >&2
  exit 1
}

command -v proxmox-k3s >/dev/null 2>&1 || {
  echo "WARNING: proxmox-k3s not found in PATH. Use an explicit --tool-path value when running provider-backed cycles." >&2
}
```

---

## Step 10 — Define Shared Runtime Variables

### Windows PowerShell

```powershell
$Namespace = "localai-benchmark"
$BaseUrl = "http://localhost:8080"
$Model = "llama-3.2-1b-instruct:q4_k_m"
$ToolPath = "proxmox-k3s"

$C0Kubeconfig = ".\config\cluster-access\fixed-cluster\kubeconfig"
$PrecheckProfile = ".\config\precheck\profiles\TC_C0_HISTORICAL_FIXED_CLUSTER.json"
$PhaseProfile = ".\config\phases\profiles\WM_STANDARD_WARMUP_MEASUREMENT.json"
$ProtocolProfile = ".\config\protocol\profiles\EP_STANDARD_BENCHMARK_PROTOCOL.json"
$ClusterCaptureProfile = ".\config\cluster-capture\profiles\CS_STANDARD_CLUSTER_CAPTURE.json"
$MetricSetProfile = ".\config\metric-set\profiles\MS_STANDARD_BENCHMARK_METRICS.json"
$StatisticalRigorProfile = ".\config\statistical-rigor\profiles\SR_REPLICATED_BENCHMARK_RIGOR.json"
$PilotConsolidationProfile = ".\config\pilot-consolidation\profiles\PC_CONSOLIDATED_PILOT_CAMPAIGN.json"
```

### Bash

```bash
NAMESPACE="localai-benchmark"
BASE_URL="http://localhost:8080"
MODEL="llama-3.2-1b-instruct:q4_k_m"
TOOL_PATH="proxmox-k3s"

C0_KUBECONFIG="./config/cluster-access/fixed-cluster/kubeconfig"
PRECHECK_PROFILE="./config/precheck/profiles/TC_C0_HISTORICAL_FIXED_CLUSTER.json"
PHASE_PROFILE="./config/phases/profiles/WM_STANDARD_WARMUP_MEASUREMENT.json"
PROTOCOL_PROFILE="./config/protocol/profiles/EP_STANDARD_BENCHMARK_PROTOCOL.json"
CLUSTER_CAPTURE_PROFILE="./config/cluster-capture/profiles/CS_STANDARD_CLUSTER_CAPTURE.json"
METRIC_SET_PROFILE="./config/metric-set/profiles/MS_STANDARD_BENCHMARK_METRICS.json"
STATISTICAL_RIGOR_PROFILE="./config/statistical-rigor/profiles/SR_REPLICATED_BENCHMARK_RIGOR.json"
PILOT_CONSOLIDATION_PROFILE="./config/pilot-consolidation/profiles/PC_CONSOLIDATED_PILOT_CAMPAIGN.json"
```

---

## Step 11 — Regenerate C0 Fixed-Cluster Evidence

`C0` uses an existing fixed cluster. It must be regenerated before the provider-backed cycles so that the historical fixed-cluster evidence is available in the same regenerated result set.

### 11.1 Verify Fixed-Cluster Access

#### Windows PowerShell

```powershell
kubectl --kubeconfig $C0Kubeconfig cluster-info
kubectl --kubeconfig $C0Kubeconfig get nodes -o wide
```

#### Bash

```bash
kubectl --kubeconfig "$C0_KUBECONFIG" cluster-info
kubectl --kubeconfig "$C0_KUBECONFIG" get nodes -o wide
```

### 11.2 Create the Application Namespace

Assume the namespace does not exist and create it through the namespace composition.

#### Windows PowerShell

```powershell
kubectl --kubeconfig $C0Kubeconfig apply -k .\infra\k8s\compositions\foundation\namespace
kubectl --kubeconfig $C0Kubeconfig get namespace $Namespace
```

#### Bash

```bash
kubectl --kubeconfig "$C0_KUBECONFIG" apply -k ./infra/k8s/compositions/foundation/namespace
kubectl --kubeconfig "$C0_KUBECONFIG" get namespace "$NAMESPACE"
```

### 11.3 Deploy the C0 Baseline Application Topology

#### Windows PowerShell

```powershell
kubectl --kubeconfig $C0Kubeconfig apply -k .\infra\k8s\compositions\shared\rpc-workers-services
kubectl --kubeconfig $C0Kubeconfig apply -k .\infra\k8s\compositions\foundation\storage
kubectl --kubeconfig $C0Kubeconfig apply -k .\infra\k8s\compositions\topology\colocated-sc-app-02-w2
kubectl --kubeconfig $C0Kubeconfig apply -k .\infra\k8s\compositions\server\models\m1
kubectl --kubeconfig $C0Kubeconfig rollout status deployment/localai-server -n $Namespace --timeout=30m
```

#### Bash

```bash
kubectl --kubeconfig "$C0_KUBECONFIG" apply -k ./infra/k8s/compositions/shared/rpc-workers-services
kubectl --kubeconfig "$C0_KUBECONFIG" apply -k ./infra/k8s/compositions/foundation/storage
kubectl --kubeconfig "$C0_KUBECONFIG" apply -k ./infra/k8s/compositions/topology/colocated-sc-app-02-w2
kubectl --kubeconfig "$C0_KUBECONFIG" apply -k ./infra/k8s/compositions/server/models/m1
kubectl --kubeconfig "$C0_KUBECONFIG" rollout status deployment/localai-server -n "$NAMESPACE" --timeout=30m
```

### 11.4 Run C0 Official Baseline Replicas

#### Windows PowerShell

```powershell
foreach ($Replica in @("A", "B", "C")) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\baseline\Start-OfficialBaseline.ps1" `
    -Replica $Replica `
    -BenchmarkConfig .\config\scenarios\baseline\B0.json `
    -Kubeconfig $C0Kubeconfig `
    -Namespace $Namespace `
    -BaseUrl $BaseUrl `
    -PrecheckConfig $PrecheckProfile `
    -PhaseConfig $PhaseProfile `
    -ProtocolConfig $ProtocolProfile `
    -ClusterCaptureConfig $ClusterCaptureProfile `
    -MetricSetConfig $MetricSetProfile

  if ($LASTEXITCODE -ne 0) {
    throw "C0 official baseline failed for replica $Replica"
  }
}
```

#### Bash

```bash
for replica in A B C; do
  bash ./scripts/load/baseline/start-official-baseline.sh \
    --replica "$replica" \
    --benchmark-config ./config/scenarios/baseline/B0.json \
    --kubeconfig "$C0_KUBECONFIG" \
    --namespace "$NAMESPACE" \
    --base-url "$BASE_URL" \
    --precheck-config "$PRECHECK_PROFILE" \
    --phase-config "$PHASE_PROFILE" \
    --protocol-config "$PROTOCOL_PROFILE" \
    --cluster-capture-config "$CLUSTER_CAPTURE_PROFILE" \
    --metric-set-config "$METRIC_SET_PROFILE" || exit 1
done
```

### 11.5 Run C0 Exploratory Evidence Samples

#### Windows PowerShell

```powershell
$ExploratoryRuns = @(
  @{ Name = "E1_smoke_single_user"; Users = 1; SpawnRate = 1; RunTime = "1m"; CsvPrefix = ".\results\experimental-cycles\C0\benchmark\exploratory\E1_smoke_single_user\locust-smoke" },
  @{ Name = "E2_low_load_two_users"; Users = 2; SpawnRate = 1; RunTime = "1m"; CsvPrefix = ".\results\experimental-cycles\C0\benchmark\exploratory\E2_low_load_two_users\locust-low_load" },
  @{ Name = "E3_small_concurrency_four_users"; Users = 4; SpawnRate = 2; RunTime = "1m"; CsvPrefix = ".\results\experimental-cycles\C0\benchmark\exploratory\E3_small_concurrency_four_users\locust-small_concurrency" },
  @{ Name = "manual_run"; Users = 3; SpawnRate = 1; RunTime = "1m"; CsvPrefix = ".\results\experimental-cycles\C0\benchmark\exploratory\manual_run\locust-exploratory" }
)

foreach ($Run in $ExploratoryRuns) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\exploratory\Start-LocustExploratory.ps1" `
    -BaseUrl $BaseUrl `
    -Model $Model `
    -Users $Run.Users `
    -SpawnRate $Run.SpawnRate `
    -RunTime $Run.RunTime `
    -CsvPrefix $Run.CsvPrefix `
    -Kubeconfig $C0Kubeconfig `
    -Namespace $Namespace `
    -PrecheckConfig $PrecheckProfile `
    -PhaseConfig $PhaseProfile `
    -ProtocolConfig $ProtocolProfile `
    -ClusterCaptureConfig $ClusterCaptureProfile `
    -MetricSetConfig $MetricSetProfile
}
```

#### Bash

```bash
exploratory_runs=(
  "E1_smoke_single_user|1|1|1m|./results/experimental-cycles/C0/benchmark/exploratory/E1_smoke_single_user/locust-smoke"
  "E2_low_load_two_users|2|1|1m|./results/experimental-cycles/C0/benchmark/exploratory/E2_low_load_two_users/locust-low_load"
  "E3_small_concurrency_four_users|4|2|1m|./results/experimental-cycles/C0/benchmark/exploratory/E3_small_concurrency_four_users/locust-small_concurrency"
  "manual_run|3|1|1m|./results/experimental-cycles/C0/benchmark/exploratory/manual_run/locust-exploratory"
)

for run_spec in "${exploratory_runs[@]}"; do
  IFS='|' read -r run_name users spawn_rate run_time csv_prefix <<< "$run_spec"
  bash ./scripts/load/exploratory/start-locust-exploratory.sh \
    --base-url "$BASE_URL" \
    --model "$MODEL" \
    --users "$users" \
    --spawn-rate "$spawn_rate" \
    --run-time "$run_time" \
    --csv-prefix "$csv_prefix" \
    --kubeconfig "$C0_KUBECONFIG" \
    --namespace "$NAMESPACE" \
    --precheck-config "$PRECHECK_PROFILE" \
    --phase-config "$PHASE_PROFILE" \
    --protocol-config "$PROTOCOL_PROFILE" \
    --cluster-capture-config "$CLUSTER_CAPTURE_PROFILE" \
    --metric-set-config "$METRIC_SET_PROFILE" || {
      echo "Exploratory run $run_name completed with a non-zero exit code. Inspect generated artifacts." >&2
    }
done
```

### 11.6 Run C0 Individual Pilot Sweeps

This step regenerates the broader C0 evidence set, not only the consolidated pilot campaign.

#### Windows PowerShell

```powershell
$Replicas = @("A", "B", "C")

$PilotFamilies = @(
  @{ Name = "worker-count"; Script = ".\scripts\load\pilot\Start-PilotWorkerCountSweep.ps1"; Scenarios = @("W1", "W2", "W3", "W4") },
  @{ Name = "workload"; Script = ".\scripts\load\pilot\Start-PilotWorkloadSweep.ps1"; Scenarios = @("WL1", "WL2", "WL3") },
  @{ Name = "models"; Script = ".\scripts\load\pilot\Start-PilotModelSweep.ps1"; Scenarios = @("M1", "M2", "M3", "M4") },
  @{ Name = "placement"; Script = ".\scripts\load\pilot\Start-PilotPlacementSweep.ps1"; Scenarios = @("PL1", "PL2") }
)

foreach ($Family in $PilotFamilies) {
  foreach ($Scenario in $Family.Scenarios) {
    foreach ($Replica in $Replicas) {
      powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Family.Script `
        -Scenario $Scenario `
        -Replica $Replica `
        -Kubeconfig $C0Kubeconfig `
        -Namespace $Namespace `
        -BaseUrl $BaseUrl `
        -PrecheckConfig $PrecheckProfile `
        -PhaseConfig $PhaseProfile `
        -ProtocolConfig $ProtocolProfile `
        -ClusterCaptureConfig $ClusterCaptureProfile `
        -MetricSetConfig $MetricSetProfile `
        -AutoApplyK8s

      if ($LASTEXITCODE -ne 0) {
        Write-Warning "C0 pilot $($Family.Name)/$Scenario/$Replica produced a non-zero exit code. Continue and inspect artifacts."
      }
    }
  }
}
```

#### Bash

```bash
replicas=(A B C)

run_pilot_family() {
  local family_name="$1"
  local script_path="$2"
  shift 2
  local scenarios=("$@")

  for scenario in "${scenarios[@]}"; do
    for replica in "${replicas[@]}"; do
      bash "$script_path" \
        --scenario "$scenario" \
        --replica "$replica" \
        --kubeconfig "$C0_KUBECONFIG" \
        --namespace "$NAMESPACE" \
        --base-url "$BASE_URL" \
        --precheck-config "$PRECHECK_PROFILE" \
        --phase-config "$PHASE_PROFILE" \
        --protocol-config "$PROTOCOL_PROFILE" \
        --cluster-capture-config "$CLUSTER_CAPTURE_PROFILE" \
        --metric-set-config "$METRIC_SET_PROFILE" \
        --auto-apply-k8s || {
          echo "C0 pilot $family_name/$scenario/$replica produced a non-zero exit code. Continue and inspect artifacts." >&2
        }
    done
  done
}

run_pilot_family "worker-count" "./scripts/load/pilot/start-pilot-worker-count-sweep.sh" W1 W2 W3 W4
run_pilot_family "workload" "./scripts/load/pilot/start-pilot-workload-sweep.sh" WL1 WL2 WL3
run_pilot_family "models" "./scripts/load/pilot/start-pilot-model-sweep.sh" M1 M2 M3 M4
run_pilot_family "placement" "./scripts/load/pilot/start-pilot-placement-sweep.sh" PL1 PL2
```

### 11.7 Run the C0 Consolidated Pilot Campaign

#### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-ConsolidatedPilotBenchmarks.ps1" `
  -Family all `
  -ProfileConfig $PilotConsolidationProfile `
  -StatisticalRigorConfig $StatisticalRigorProfile `
  -Kubeconfig $C0Kubeconfig `
  -Namespace $Namespace `
  -BaseUrl $BaseUrl `
  -ContinueOnFailure
```

#### Bash

```bash
bash ./scripts/load/post/start-consolidated-pilot-benchmarks.sh \
  --family all \
  --profile-config "$PILOT_CONSOLIDATION_PROFILE" \
  --statistical-rigor-config "$STATISTICAL_RIGOR_PROFILE" \
  --kubeconfig "$C0_KUBECONFIG" \
  --namespace "$NAMESPACE" \
  --base-url "$BASE_URL" \
  --continue-on-failure
```

### 11.8 Run C0 Post-Processing

#### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-TechnicalDiagnosis.ps1" `
  -ProfileConfig .\config\technical-diagnosis\profiles\TD_C0_HISTORICAL_FIXED_CLUSTER.json `
  -Family all

powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-Reporting.ps1" `
  -ProfileConfig .\config\reporting\profiles\RP_C0_HISTORICAL_FIXED_CLUSTER.json `
  -Archive

$C0DiagnosisJson = (Get-ChildItem .\results\experimental-cycles\C0\diagnosis\*_diagnosis.json |
  Sort-Object LastWriteTimeUtc -Descending |
  Select-Object -First 1).FullName

powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-CompletionGate.ps1" `
  -ProfileConfig .\config\completion-gate\profiles\CG_C0_HISTORICAL_FIXED_CLUSTER.json `
  -CycleConfig .\config\experimental-cycles\C0.json `
  -DiagnosisJson $C0DiagnosisJson

powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-FreezeExperimentalCycle.ps1" `
  -CycleConfig .\config\experimental-cycles\C0.json `
  -ProfileConfig .\config\freeze\profiles\FR_C0_HISTORICAL_FIXED_CLUSTER.json `
  -Force `
  -WriteLatestAliases
```

#### Bash

```bash
bash ./scripts/load/post/start-technical-diagnosis.sh \
  --profile-config ./config/technical-diagnosis/profiles/TD_C0_HISTORICAL_FIXED_CLUSTER.json \
  --family all

bash ./scripts/load/post/start-reporting.sh \
  --profile-config ./config/reporting/profiles/RP_C0_HISTORICAL_FIXED_CLUSTER.json \
  --archive

c0_diagnosis_json="$(ls -t ./results/experimental-cycles/C0/diagnosis/*_diagnosis.json | head -n 1)"

bash ./scripts/load/post/start-completion-gate.sh \
  --profile-config ./config/completion-gate/profiles/CG_C0_HISTORICAL_FIXED_CLUSTER.json \
  --cycle-config ./config/experimental-cycles/C0.json \
  --diagnosis-json "$c0_diagnosis_json"

bash ./scripts/load/post/start-freeze-experimental-cycle.sh \
  --cycle-config ./config/experimental-cycles/C0.json \
  --profile-config ./config/freeze/profiles/FR_C0_HISTORICAL_FIXED_CLUSTER.json \
  --force \
  --write-latest-aliases
```

---

## Step 12 — Regenerate C1 Provider-Backed Baseline

`C1` is the provider-backed baseline cycle. It validates the end-to-end provider-backed workflow before running comparative campaigns.

### Windows PowerShell

```powershell
$C1RunId = "C1_regeneration_$(Get-Date -Format 'yyyyMMdd_HHmmss')"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ExecutionScope provider-backed-cycle `
  -ToolPath $ToolPath `
  -ProviderConfig .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml `
  -BaselineReplicas "A,B,C" `
  -RunId $C1RunId `
  -AllowMetricsWarning `
  -WriteLatestAliases
```

### Bash

```bash
C1_RUN_ID="C1_regeneration_$(date +%Y%m%d_%H%M%S)"

bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config ./config/experimental-cycles/C1.json \
  --execution-scope provider-backed-cycle \
  --tool-path "$TOOL_PATH" \
  --provider-config ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml \
  --baseline-replicas "A,B,C" \
  --run-id "$C1_RUN_ID" \
  --allow-metrics-warning \
  --write-latest-aliases
```

After `C1`, verify that the baseline produced diagnosis, reporting, completion-gate, and freeze artifacts.

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C1\diagnosis
Get-ChildItem .\results\experimental-cycles\C1\reporting
Get-ChildItem .\results\experimental-cycles\C1\completion-gate
Get-ChildItem .\results\experimental-cycles\C1\freeze
```

### Bash

```bash
ls -la ./results/experimental-cycles/C1/diagnosis
ls -la ./results/experimental-cycles/C1/reporting
ls -la ./results/experimental-cycles/C1/completion-gate
ls -la ./results/experimental-cycles/C1/freeze
```

---

## Step 13 — Regenerate C2-C6 Provider-Backed Campaigns

Run provider-backed campaigns in order. Use `ContinueOnFailure` / `--continue-on-failure` so that unsupported variants are recorded without invalidating the rest of the campaign.

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
    -ToolPath $ToolPath `
    -ConfirmDelete `
    -AllowMetricsWarning `
    -ContinueOnFailure `
    -ForceFreeze `
    -WriteLatestAliases

  if ($LASTEXITCODE -ne 0) {
    throw "Provider-backed campaign failed: $Campaign"
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
    --tool-path "$TOOL_PATH" \
    --confirm-delete \
    --allow-metrics-warning \
    --continue-on-failure \
    --force-freeze \
    --write-latest-aliases || {
      echo "Provider-backed campaign failed: $campaign" >&2
      exit 1
    }
done
```

Expected campaign-level artifact roots:

```text
results/experimental-cycles/C2/
results/experimental-cycles/C3/
results/experimental-cycles/C4/
results/experimental-cycles/C5/
results/experimental-cycles/C6/
```

---


## Step 14 — Regenerate C7 Default-Scheduler Baseline

Regenerate C7 after the controlled provider-backed campaigns when a full evidence set is required.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C7.json `
  -ToolPath $ToolPath `
  -RunId "C7_default_scheduler_baseline" `
  -AllowMetricsWarning `
  -ContinueOnFailure `
  -ConfirmDelete `
  -WriteLatestAliases
```

### Bash

```bash
scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config config/experimental-cycles/C7.json \
  --tool-path "$TOOL_PATH" \
  --run-id C7_default_scheduler_baseline \
  --allow-metrics-warning \
  --continue-on-failure \
  --confirm-delete \
  --write-latest-aliases
```

C7 must preserve scheduler decision evidence for executed default-scheduler scenarios. Do not replace default-scheduler scenarios with controlled placement overlays during regeneration.

---

## Step 15 — Regenerate C8 Resource-Aware Scheduler

Regenerate C8 after C7 when a complete resource-aware scheduler evidence set is required. C8 compares default and load-aware scheduling under paired `L0_NONE` scenarios.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C8.json `
  -ToolPath $ToolPath `
  -RunId "C8_resource_aware_scheduler" `
  -BaselineReplicas "A,B,C" `
  -AllowMetricsWarning `
  -ContinueOnFailure `
  -ConfirmDelete `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config config/experimental-cycles/C8.json \
  --tool-path "$TOOL_PATH" \
  --run-id C8_resource_aware_scheduler \
  --baseline-replicas "A,B,C" \
  --allow-metrics-warning \
  --continue-on-failure \
  --confirm-delete \
  --force-freeze \
  --write-latest-aliases
```

C8 must preserve paired resource-aware scheduler evidence, `mon-agent` annotation evidence, custom scheduler evidence for load-aware variants, rescheduling evidence, benchmark metrics, diagnosis, reporting, completion-gate, and freeze artifacts.

---

## Step 16 — Regenerate C9 Network-Aware Scheduler Campaign

Regenerate C9 after C8 when a complete network-aware scheduler evidence set is required. C9 compares default, load-aware, and network-aware scheduling under the selected network-aware scenario matrix.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C9.json `
  -RunId "C9_network_aware_scheduler" `
  -BaselineReplicas "A,B,C" `
  -ConfirmDelete `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config config/experimental-cycles/C9.json \
  --run-id C9_network_aware_scheduler \
  --baseline-replicas "A,B,C" \
  --confirm-delete \
  --force-freeze \
  --write-latest-aliases
```

C9 must preserve gateway-routed traffic evidence, Istio routing evidence, Mentat network evidence, `mon-agent` annotation evidence, custom scheduler evidence for load-aware and network-aware variants, telemetry-primed rescheduling evidence, benchmark metrics, diagnosis, reporting, completion-gate, and freeze artifacts.

---

## Step 17 — Regenerate the Global Reporting Site

Regenerate the global reporting site after all cycles have produced reporting artifacts.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-ReportingSite.ps1" `
  -SiteConfig .\config\reporting\site\REPORTING_SITE.json
```

### Bash

```bash
bash ./scripts/load/post/start-reporting-site.sh \
  --site-config ./config/reporting/site/REPORTING_SITE.json
```

Expected output root:

```text
results/reporting/
```

---

## Step 18 — Verify Per-Cycle Regeneration Status

Verify the presence of diagnosis, reporting, completion-gate, freeze, and frozen artifact snapshots for all cycles.

### Windows PowerShell

```powershell
$Cycles = @("C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9")
$RequiredSubdirs = @("diagnosis", "reporting", "completion-gate", "freeze", "artifacts")

foreach ($Cycle in $Cycles) {
  foreach ($Subdir in $RequiredSubdirs) {
    $Path = ".\results\experimental-cycles\$Cycle\$Subdir"
    if (-not (Test-Path $Path)) {
      Write-Warning "Missing artifact directory: $Path"
    }
    else {
      Write-Host "OK: $Path"
    }
  }
}
```

### Bash

```bash
cycles=(C0 C1 C2 C3 C4 C5 C6 C7 C8 C9)
required_subdirs=(diagnosis reporting completion-gate freeze artifacts)

for cycle in "${cycles[@]}"; do
  for subdir in "${required_subdirs[@]}"; do
    path="./results/experimental-cycles/$cycle/$subdir"
    if [ ! -d "$path" ]; then
      echo "WARNING: Missing artifact directory: $path" >&2
    else
      echo "OK: $path"
    fi
  done
done
```

---

## Step 19 — Inspect Completion-Gate Outcomes

### Windows PowerShell

```powershell
python -c "import json, pathlib; \
for c in ['C0','C1','C2','C3','C4','C5','C6','C7','C8','C9']: \
 p=pathlib.Path('results/experimental-cycles')/c/'completion-gate'/'latest-completion-gate-manifest.json'; \
 print(c, 'MISSING' if not p.exists() else json.load(open(p, encoding='utf-8-sig')).get('status'))"
```

### Bash

```bash
python - <<'PY'
import json
import pathlib

for cycle in ["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"]:
    path = pathlib.Path("results/experimental-cycles") / cycle / "completion-gate" / "latest-completion-gate-manifest.json"
    if not path.exists():
        print(cycle, "MISSING")
        continue
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    print(cycle, payload.get("status"))
PY
```

Accepted statuses depend on the corresponding completion-gate profile. Comparative campaigns may complete with unsupported-scenario evidence when unsupported variants are caused by declared resource, placement, latency, or tenancy constraints.

---

## Step 20 — Inspect Campaign Variant and Scenario Statuses

### Windows PowerShell

```powershell
python -c "import json, pathlib; \
for c in ['C2','C3','C4','C5','C6','C7']: \
 p=pathlib.Path('results/experimental-cycles')/c/'execution'/'latest-campaign-execution-manifest.json'; \
 print('\n'+c); \
 data=json.load(open(p, encoding='utf-8-sig')) if p.exists() else {}; \
 variants=data.get('variantResults', data.get('variants', [])); \
 [print(' ', v.get('variantId'), v.get('status'), 'unsupported=' + str(bool(v.get('unsupportedScenario')))) for v in variants]"
```

### Bash

```bash
python - <<'PY'
import json
import pathlib

for cycle in ["C2", "C3", "C4", "C5", "C6", "C7"]:
    path = pathlib.Path("results/experimental-cycles") / cycle / "execution" / "latest-campaign-execution-manifest.json"
    print(f"\n{cycle}")
    if not path.exists():
        print("  MISSING latest campaign manifest")
        continue
    with path.open(encoding="utf-8-sig") as handle:
        data = json.load(handle)
    for variant in data.get("variantResults", data.get("variants", [])):
        print(" ", variant.get("variantId"), variant.get("status"), "unsupported=" + str(bool(variant.get("unsupportedScenario"))))
PY
```

The purpose of this check is to distinguish:

```text
measured variants
unsupported variants
failed variants
missing variants
```

Unsupported variants should be reviewed together with the corresponding scheduling, rollout, resource, latency, or tenancy evidence.

---

## Step 21 — Verify the Global Reporting Site

### Windows PowerShell

```powershell
Test-Path .\results\reporting\index.html
Get-ChildItem .\results\reporting -Force
```

### Bash

```bash
test -f ./results/reporting/index.html
ls -la ./results/reporting
```

Expected result:

```text
results/reporting/index.html
```

Additional charts, manifests, and per-cycle reporting assets may be present depending on the reporting-site profile.

---

## Step 22 — Validate That No Generated Artifact Uses a Deprecated Namespace

The canonical application namespace is `localai-benchmark`. If a deprecated application namespace exists for the local environment, set it explicitly before running the check below. No matches are expected after a clean regeneration.

### Windows PowerShell

```powershell
$DeprecatedNamespace = "<deprecated-namespace>"

if ($DeprecatedNamespace -ne "<deprecated-namespace>" -and -not [string]::IsNullOrWhiteSpace($DeprecatedNamespace)) {
  Select-String -Path ".\results\**\*" -Pattern $DeprecatedNamespace -ErrorAction SilentlyContinue
} else {
  Write-Host "No deprecated namespace configured for validation."
}
```

### Bash

```bash
deprecated_namespace="<deprecated-namespace>"

if [ "$deprecated_namespace" != "<deprecated-namespace>" ] && [ -n "$deprecated_namespace" ]; then
  grep -R "$deprecated_namespace" ./results 2>/dev/null || true
else
  echo "No deprecated namespace configured for validation."
fi
```

---

## Step 23 — Validate Canonical Namespace Evidence

### Windows PowerShell

```powershell
Select-String -Path ".\results\**\*" -Pattern "localai-benchmark" -ErrorAction SilentlyContinue |
  Select-Object -First 20
```

### Bash

```bash
grep -R "localai-benchmark" ./results 2>/dev/null | head -20 || true
```

At least the fixed-cluster and single-tenant application artifacts should contain evidence of the canonical namespace. Multi-tenant artifacts may also include tenant-specific namespaces depending on the scenario.

---

## Step 24 — Review Git Status After Regeneration

### Windows PowerShell

```powershell
git status --short
```

### Bash

```bash
git status --short
```

Expected behavior:

- source documentation changes appear under `docs/runbooks/`;
- regenerated artifacts may appear under `results/` depending on the repository tracking policy;
- local kubeconfig files and provider-local YAML files should remain untracked if ignored correctly.

If sensitive local configuration appears in `git status`, stop and fix ignore rules before committing.

---

## Step 25 — Optional Removal of Partial Provider-Backed Clusters

Use this only when a provider-backed execution was interrupted and left a temporary cluster behind.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ExecutionScope provisioning `
  -ProvisioningAction destroy `
  -ToolPath $ToolPath `
  -ProviderConfig .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml `
  -ConfirmDelete `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config ./config/experimental-cycles/C1.json \
  --execution-scope provisioning \
  --provisioning-action destroy \
  --tool-path "$TOOL_PATH" \
  --provider-config ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml \
  --confirm-delete \
  --write-latest-aliases
```

For comparative campaigns, prefer the campaign-specific lifecycle behavior unless a manual cleanup is required after an interruption.

---

## Rerun Policy

Use the policy below when a regeneration step fails.

| Failure point | Recommended action |
|---|---|
| JSON validation fails | Fix the profile before running any benchmark. |
| Fixed-cluster access fails | Restore VPN and kubeconfig access before running C0. |
| C0 namespace creation fails | Inspect cluster permissions and namespace state. |
| C0 application rollout fails | Inspect pods, events, PVCs, and node resources. |
| Provider provisioning fails | Inspect provider-local YAML, gateway, DNS, VMID policy, and partial VMs. |
| Cluster validation fails | Inspect generated kubeconfig and node readiness. |
| LocalAI deployment fails | Inspect rollout status, pod placement, PVCs, and events. |
| Benchmark fails | Inspect Locust CSV files, LocalAI logs, port-forwarding, and precheck output. |
| Variant is unsupported | Preserve the evidence and continue when the constraint is expected. |
| Reporting fails | Regenerate diagnosis first, then reporting. |
| Completion gate fails | Inspect diagnosis and gate manifest before rerunning freeze. |
| Freeze fails | Ensure completion-gate artifacts exist, then rerun freeze with force only when intentional. |

---

## Minimal Full-Regeneration Checklist

Use this checklist after completing the command sequence.

```text
[ ] results/ was cleaned before execution.
[ ] C0 namespace localai-benchmark was created or reconciled.
[ ] C0 baseline replicas A/B/C were regenerated.
[ ] C0 exploratory evidence was regenerated.
[ ] C0 individual pilot sweeps were regenerated.
[ ] C0 consolidated pilot campaign was regenerated.
[ ] C0 diagnosis, reporting, completion gate, and freeze were regenerated.
[ ] C1 provider-backed baseline was regenerated.
[ ] C2 resource-variation campaign was regenerated.
[ ] C3 node-count-variation campaign was regenerated.
[ ] C4 placement-variation campaign was regenerated.
[ ] C5 latency-injection campaign was regenerated.
[ ] C6 multi-tenancy campaign was regenerated.
[ ] C7 default-scheduler baseline campaign was regenerated.
[ ] Global reporting site was regenerated.
[ ] Completion-gate outcomes were inspected.
[ ] Unsupported scenarios were reviewed as evidence, not deleted.
[ ] No generated artifact still references the previous namespace.
[ ] Git status does not expose local secrets or kubeconfig material.
```

---

## Expected Final Artifact Layout

After full regeneration, the generated tree should include at least:

```text
results/
├── .gitkeep
├── experimental-cycles/
│   ├── C0/
│   ├── C1/
│   ├── C2/
│   ├── C3/
│   ├── C4/
│   ├── C5/
│   ├── C6/
│   └── C7/
└── reporting/
    └── index.html
```

Each cycle should contain the relevant subset of:

```text
benchmark/
cluster-capture/
completion-gate/
diagnosis/
execution/
freeze/
infrastructure/
observability/
reporting/
validation/
artifacts/
```

The exact subdirectory set may differ between `C0`, `C1`, provider-backed comparative campaigns, the default-scheduler campaign, and the resource-aware scheduler campaign because their execution models are different.

---

## Final Acceptance Criteria

A full regeneration is acceptable when:

1. `results/experimental-cycles/C0` through `results/experimental-cycles/C9` exist;
2. each cycle has diagnosis, reporting, completion-gate, and freeze artifacts;
3. the global reporting site exists under `results/reporting/`;
4. unsupported variants are explicitly represented in campaign artifacts when expected;
5. no obsolete namespace reference remains in regenerated artifacts;
6. source configuration files were not modified during results cleanup;
7. local secrets, kubeconfig files, and provider-local YAML files remain excluded from shared outputs unless intentionally handled outside the repository.
