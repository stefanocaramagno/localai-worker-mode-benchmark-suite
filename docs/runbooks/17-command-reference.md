# Command Reference

## Purpose

This runbook provides a compact command reference for the LocalAI worker-mode benchmark suite.

It is intended as a quick lookup after the execution model, configuration model, access model, provider lifecycle, cycle-specific execution runbooks, troubleshooting runbook, and cleanup/regeneration runbook have been reviewed.

Use this document to locate the most common commands for:

1. validating the local workstation;
2. validating repository layout and configuration files;
3. preparing fixed-cluster and provider-backed access;
4. running the fixed-cluster `C0` workflow;
5. running the provider-backed `C1` baseline;
6. running the provider-backed `C2` through `C6` campaigns;
7. running the `C7` default-scheduler baseline campaign;
8. running the `C8` resource-aware scheduler campaign;
9. running the `C9` network-aware scheduler campaign;
10. regenerating diagnosis, reporting, completion gates, and freeze snapshots;
11. inspecting Kubernetes, LocalAI, Locust, scheduler evidence, mon-agent evidence, network-aware evidence, rescheduling evidence, and generated artifacts;
12. performing safe cleanup and recovery operations.

This file is a command index, not a substitute for the detailed operational runbooks.

---

## Repository Root Assumption

All commands must be executed from the repository root unless a command explicitly states otherwise.

```text
localai-worker-mode-benchmark-suite/
```

### Windows PowerShell

```powershell
Set-Location C:\Path\To\localai-worker-mode-benchmark-suite
Get-Location
Get-ChildItem
```

### Bash

```bash
cd /path/to/localai-worker-mode-benchmark-suite
pwd
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

## Command Conventions

Use the command block for the shell family actually used on the workstation.

| Shell family | Use |
|---|---|
| Windows PowerShell | `.ps1` launchers and Windows-style paths |
| Bash | `.sh` launchers and POSIX-style paths |

Do not rely on the default Kubernetes context. Use explicit kubeconfig paths.

Use `localai-benchmark` as the canonical single-tenant LocalAI benchmark namespace.

Unsupported scenarios must be preserved as evidence when they result from declared capacity, scheduling, rollout, latency, or tenancy constraints.

---

## 1. Validate Repository Layout

### Windows PowerShell

```powershell
$RequiredPaths = @(
  ".\config",
  ".\docs",
  ".\infra",
  ".\load-tests",
  ".\scripts",
  ".\requirements.txt"
)

foreach ($Path in $RequiredPaths) {
  if (-not (Test-Path $Path)) {
    throw "Missing repository path: $Path"
  }
}
```

### Bash

```bash
required_paths=(
  "./config"
  "./docs"
  "./infra"
  "./load-tests"
  "./scripts"
  "./requirements.txt"
)

for path in "${required_paths[@]}"; do
  test -e "$path" || { echo "Missing repository path: $path" >&2; exit 1; }
done
```

---

## 2. Validate Main Runbooks

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

## 3. Validate Local Tooling

### Windows PowerShell

```powershell
python --version
python -m pip --version
kubectl version --client
locust --version
Get-Command helm -ErrorAction SilentlyContinue
Get-Command kustomize -ErrorAction SilentlyContinue
Get-Command proxmox-k3s -ErrorAction SilentlyContinue
```

### Bash

```bash
python3 --version || python --version
python3 -m pip --version || python -m pip --version
kubectl version --client
locust --version
command -v helm || true
command -v kustomize || true
command -v proxmox-k3s || true
```

---

## 4. Create and Activate the Python Environment

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\.venv\Scripts\Activate.ps1
```

### Bash

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r ./requirements.txt
source ./.venv/bin/activate
```

---

## 5. Validate Python Dependencies

### Windows PowerShell

```powershell
python -m pip show locust
python -m locust --version
```

### Bash

```bash
python3 -m pip show locust || python -m pip show locust
python3 -m locust --version || python -m locust --version
```

---

## 6. Validate Bash Entrypoint Permissions

### Windows PowerShell

```powershell
Get-ChildItem .\scripts -Recurse -Filter *.sh | Select-Object FullName
```

### Bash

```bash
find ./scripts -type f -name "*.sh" -exec chmod +x {} \;
find ./scripts -type f -name "*.sh" -print | sort
```

---

## 7. Validate All JSON Configuration Files

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
  python3 -m json.tool "$file" >/dev/null || python -m json.tool "$file" >/dev/null || {
    echo "Invalid JSON file: $file" >&2
    exit 1
  }
done
```

---

## 8. Validate Main Configuration Registries

### Windows PowerShell

```powershell
$RequiredIndexes = @(
  ".\config\experimental-cycles\EXPERIMENTAL_CYCLES_INDEX.json",
  ".\config\infrastructure\INFRA_PROFILES_INDEX.json",
  ".\config\infrastructure\lifecycle\CLUSTER_LIFECYCLE_POLICIES_INDEX.json",
  ".\config\infrastructure\providers\PROVIDERS_INDEX.json",
  ".\config\infrastructure\providers\proxmox-k3s\PROXMOX_K3S_PROVIDER_INDEX.json",
  ".\config\infrastructure\providers\proxmox-k3s\PROXMOX_K3S_PROVIDER_BINDINGS_INDEX.json",
  ".\config\placement\PLACEMENT_PROFILES_INDEX.json",
  ".\config\latency\LATENCY_PROFILES_INDEX.json",
  ".\config\tenancy\TENANCY_PROFILES_INDEX.json",
  ".\config\technical-diagnosis\TECHNICAL_DIAGNOSIS_INDEX.json",
  ".\config\reporting\REPORTING_INDEX.json",
  ".\config\completion-gate\COMPLETION_GATE_INDEX.json",
  ".\config\freeze\FREEZE_INDEX.json"
)

foreach ($Index in $RequiredIndexes) {
  if (-not (Test-Path $Index)) {
    throw "Missing configuration index: $Index"
  }
  python -m json.tool $Index > $null
}
```

### Bash

```bash
required_indexes=(
  "./config/experimental-cycles/EXPERIMENTAL_CYCLES_INDEX.json"
  "./config/infrastructure/INFRA_PROFILES_INDEX.json"
  "./config/infrastructure/lifecycle/CLUSTER_LIFECYCLE_POLICIES_INDEX.json"
  "./config/infrastructure/providers/PROVIDERS_INDEX.json"
  "./config/infrastructure/providers/proxmox-k3s/PROXMOX_K3S_PROVIDER_INDEX.json"
  "./config/infrastructure/providers/proxmox-k3s/PROXMOX_K3S_PROVIDER_BINDINGS_INDEX.json"
  "./config/placement/PLACEMENT_PROFILES_INDEX.json"
  "./config/latency/LATENCY_PROFILES_INDEX.json"
  "./config/tenancy/TENANCY_PROFILES_INDEX.json"
  "./config/technical-diagnosis/TECHNICAL_DIAGNOSIS_INDEX.json"
  "./config/reporting/REPORTING_INDEX.json"
  "./config/completion-gate/COMPLETION_GATE_INDEX.json"
  "./config/freeze/FREEZE_INDEX.json"
)

for index_path in "${required_indexes[@]}"; do
  test -f "$index_path" || { echo "Missing configuration index: $index_path" >&2; exit 1; }
  python3 -m json.tool "$index_path" >/dev/null || python -m json.tool "$index_path" >/dev/null || exit 1
done
```

---

## 9. Define Common Runtime Variables

### Windows PowerShell

```powershell
$Namespace = "localai-benchmark"
$BaseUrl = "http://localhost:8080"
$Model = "llama-3.2-1b-instruct:q4_k_m"
$ToolPath = "proxmox-k3s"

$PhaseProfile = ".\config\phases\profiles\WM_STANDARD_WARMUP_MEASUREMENT.json"
$ProtocolProfile = ".\config\protocol\profiles\EP_STANDARD_BENCHMARK_PROTOCOL.json"
$MetricSetProfile = ".\config\metric-set\profiles\MS_STANDARD_BENCHMARK_METRICS.json"
$ClusterCaptureProfile = ".\config\cluster-capture\profiles\CS_STANDARD_CLUSTER_CAPTURE.json"
$StatisticalRigorProfile = ".\config\statistical-rigor\profiles\SR_REPLICATED_BENCHMARK_RIGOR.json"
```

### Bash

```bash
NAMESPACE="localai-benchmark"
BASE_URL="http://localhost:8080"
MODEL="llama-3.2-1b-instruct:q4_k_m"
TOOL_PATH="proxmox-k3s"

PHASE_PROFILE="./config/phases/profiles/WM_STANDARD_WARMUP_MEASUREMENT.json"
PROTOCOL_PROFILE="./config/protocol/profiles/EP_STANDARD_BENCHMARK_PROTOCOL.json"
METRIC_SET_PROFILE="./config/metric-set/profiles/MS_STANDARD_BENCHMARK_METRICS.json"
CLUSTER_CAPTURE_PROFILE="./config/cluster-capture/profiles/CS_STANDARD_CLUSTER_CAPTURE.json"
STATISTICAL_RIGOR_PROFILE="./config/statistical-rigor/profiles/SR_REPLICATED_BENCHMARK_RIGOR.json"
```

---

## 10. Validate Fixed-Cluster C0 Access

### Windows PowerShell

```powershell
$C0Kubeconfig = ".\config\cluster-access\fixed-cluster\kubeconfig"

kubectl --kubeconfig $C0Kubeconfig config current-context
kubectl --kubeconfig $C0Kubeconfig cluster-info
kubectl --kubeconfig $C0Kubeconfig get nodes -o wide
```

### Bash

```bash
C0_KUBECONFIG="./config/cluster-access/fixed-cluster/kubeconfig"

kubectl --kubeconfig "$C0_KUBECONFIG" config current-context
kubectl --kubeconfig "$C0_KUBECONFIG" cluster-info
kubectl --kubeconfig "$C0_KUBECONFIG" get nodes -o wide
```

---

## 11. Create or Validate the C0 Namespace

### Windows PowerShell

```powershell
kubectl --kubeconfig $C0Kubeconfig apply -k .\infra\k8s\compositions\foundation\namespace
kubectl --kubeconfig $C0Kubeconfig get namespace $Namespace
```

### Bash

```bash
kubectl --kubeconfig "$C0_KUBECONFIG" apply -k ./infra/k8s/compositions/foundation/namespace
kubectl --kubeconfig "$C0_KUBECONFIG" get namespace "$NAMESPACE"
```

---

## 12. Apply the C0 Baseline LocalAI Deployment

### Windows PowerShell

```powershell
kubectl --kubeconfig $C0Kubeconfig apply -k .\infra\k8s\compositions\shared\rpc-workers-services
kubectl --kubeconfig $C0Kubeconfig apply -k .\infra\k8s\compositions\foundation\storage
kubectl --kubeconfig $C0Kubeconfig apply -k .\infra\k8s\compositions\topology\colocated-sc-app-02-w2
kubectl --kubeconfig $C0Kubeconfig apply -k .\infra\k8s\compositions\server\models\m1
kubectl --kubeconfig $C0Kubeconfig rollout status deployment/localai-server -n $Namespace --timeout=900s
```

### Bash

```bash
kubectl --kubeconfig "$C0_KUBECONFIG" apply -k ./infra/k8s/compositions/shared/rpc-workers-services
kubectl --kubeconfig "$C0_KUBECONFIG" apply -k ./infra/k8s/compositions/foundation/storage
kubectl --kubeconfig "$C0_KUBECONFIG" apply -k ./infra/k8s/compositions/topology/colocated-sc-app-02-w2
kubectl --kubeconfig "$C0_KUBECONFIG" apply -k ./infra/k8s/compositions/server/models/m1
kubectl --kubeconfig "$C0_KUBECONFIG" rollout status deployment/localai-server -n "$NAMESPACE" --timeout=900s
```

---

## 13. Inspect LocalAI Runtime State

### Windows PowerShell

```powershell
kubectl --kubeconfig $C0Kubeconfig get pods -n $Namespace -o wide
kubectl --kubeconfig $C0Kubeconfig get svc -n $Namespace
kubectl --kubeconfig $C0Kubeconfig get pvc -n $Namespace
kubectl --kubeconfig $C0Kubeconfig get configmap localai-runtime-config -n $Namespace -o yaml
```

### Bash

```bash
kubectl --kubeconfig "$C0_KUBECONFIG" get pods -n "$NAMESPACE" -o wide
kubectl --kubeconfig "$C0_KUBECONFIG" get svc -n "$NAMESPACE"
kubectl --kubeconfig "$C0_KUBECONFIG" get pvc -n "$NAMESPACE"
kubectl --kubeconfig "$C0_KUBECONFIG" get configmap localai-runtime-config -n "$NAMESPACE" -o yaml
```

---

## 14. Open a LocalAI Port Forward

Run this command in a dedicated terminal.

### Windows PowerShell

```powershell
kubectl --kubeconfig $C0Kubeconfig -n $Namespace port-forward svc/localai-server 8080:8080
```

### Bash

```bash
kubectl --kubeconfig "$C0_KUBECONFIG" -n "$NAMESPACE" port-forward svc/localai-server 8080:8080
```

---

## 15. Run the LocalAI Smoke Test

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\validation\smoke\Test-LocalAIWorkerMode.ps1" `
  -BaseUrl $BaseUrl `
  -Model $Model `
  -RequestTimeoutSeconds 120
```

### Bash

```bash
bash ./scripts/validation/smoke/test-localai-worker-mode.sh \
  --base-url "$BASE_URL" \
  --model "$MODEL" \
  --request-timeout-seconds 120
```

---

## 16. Run C0 Precheck

### Windows PowerShell

```powershell
$C0PrecheckProfile = ".\config\precheck\profiles\TC_C0_HISTORICAL_FIXED_CLUSTER.json"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\validation\precheck\Invoke-BenchmarkPrecheck.ps1" `
  -ProfileConfig $C0PrecheckProfile `
  -Kubeconfig $C0Kubeconfig `
  -Namespace $Namespace `
  -OutputPrefix .\results\experimental-cycles\C0\precheck\c0-precheck `
  -BaseUrl $BaseUrl `
  -Model $Model
```

### Bash

```bash
C0_PRECHECK_PROFILE="./config/precheck/profiles/TC_C0_HISTORICAL_FIXED_CLUSTER.json"

bash ./scripts/validation/precheck/invoke-benchmark-precheck.sh \
  --profile-config "$C0_PRECHECK_PROFILE" \
  --kubeconfig "$C0_KUBECONFIG" \
  --namespace "$NAMESPACE" \
  --output-prefix ./results/experimental-cycles/C0/precheck/c0-precheck \
  --base-url "$BASE_URL" \
  --model "$MODEL"
```

---

## 17. Capture Cluster-Side Evidence

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\validation\cluster-side\Collect-ClusterSideArtifacts.ps1" `
  -ProfileConfig $ClusterCaptureProfile `
  -Kubeconfig $C0Kubeconfig `
  -Namespace $Namespace `
  -OutputPrefix .\results\experimental-cycles\C0\cluster-capture\pre\c0-pre `
  -Stage pre
```

### Bash

```bash
bash ./scripts/validation/cluster-side/collect-cluster-side-artifacts.sh \
  --profile-config "$CLUSTER_CAPTURE_PROFILE" \
  --kubeconfig "$C0_KUBECONFIG" \
  --namespace "$NAMESPACE" \
  --output-prefix ./results/experimental-cycles/C0/cluster-capture/pre/c0-pre \
  --stage pre
```

---

## 18. Run the Official C0 Baseline

### Windows PowerShell

```powershell
foreach ($Replica in @("A", "B", "C")) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\baseline\Start-OfficialBaseline.ps1" `
    -Replica $Replica `
    -BenchmarkConfig .\config\scenarios\baseline\B0.json `
    -Kubeconfig $C0Kubeconfig `
    -Namespace $Namespace `
    -BaseUrl $BaseUrl `
    -PrecheckConfig $C0PrecheckProfile `
    -PhaseConfig $PhaseProfile `
    -ProtocolConfig $ProtocolProfile `
    -ClusterCaptureConfig $ClusterCaptureProfile `
    -MetricSetConfig $MetricSetProfile

  if ($LASTEXITCODE -ne 0) {
    throw "C0 baseline failed for replica $Replica."
  }
}
```

### Bash

```bash
for replica in A B C; do
  bash ./scripts/load/baseline/start-official-baseline.sh \
    --replica "$replica" \
    --benchmark-config ./config/scenarios/baseline/B0.json \
    --kubeconfig "$C0_KUBECONFIG" \
    --namespace "$NAMESPACE" \
    --base-url "$BASE_URL" \
    --precheck-config "$C0_PRECHECK_PROFILE" \
    --phase-config "$PHASE_PROFILE" \
    --protocol-config "$PROTOCOL_PROFILE" \
    --cluster-capture-config "$CLUSTER_CAPTURE_PROFILE" \
    --metric-set-config "$METRIC_SET_PROFILE" || exit 1
done
```

---

## 19. Run C0 Exploratory Load Samples

### Windows PowerShell

```powershell
$ExploratoryRuns = @(
  @{ Users = 1; SpawnRate = 1; RunTime = "1m"; CsvPrefix = ".\results\experimental-cycles\C0\benchmark\exploratory\E1_smoke_single_user\locust-smoke" },
  @{ Users = 2; SpawnRate = 1; RunTime = "1m"; CsvPrefix = ".\results\experimental-cycles\C0\benchmark\exploratory\E2_low_load_two_users\locust-low_load" },
  @{ Users = 4; SpawnRate = 2; RunTime = "1m"; CsvPrefix = ".\results\experimental-cycles\C0\benchmark\exploratory\E3_small_concurrency_four_users\locust-small_concurrency" },
  @{ Users = 3; SpawnRate = 1; RunTime = "1m"; CsvPrefix = ".\results\experimental-cycles\C0\benchmark\exploratory\manual_run\locust-exploratory" }
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
    -PrecheckConfig $C0PrecheckProfile `
    -PhaseConfig $PhaseProfile `
    -ProtocolConfig $ProtocolProfile `
    -ClusterCaptureConfig $ClusterCaptureProfile `
    -MetricSetConfig $MetricSetProfile
}
```

### Bash

```bash
exploratory_runs=(
  "1 1 1m ./results/experimental-cycles/C0/benchmark/exploratory/E1_smoke_single_user/locust-smoke"
  "2 1 1m ./results/experimental-cycles/C0/benchmark/exploratory/E2_low_load_two_users/locust-low_load"
  "4 2 1m ./results/experimental-cycles/C0/benchmark/exploratory/E3_small_concurrency_four_users/locust-small_concurrency"
  "3 1 1m ./results/experimental-cycles/C0/benchmark/exploratory/manual_run/locust-exploratory"
)

for run_spec in "${exploratory_runs[@]}"; do
  set -- $run_spec
  users="$1"
  spawn_rate="$2"
  run_time="$3"
  csv_prefix="$4"

  bash ./scripts/load/exploratory/start-locust-exploratory.sh \
    --base-url "$BASE_URL" \
    --model "$MODEL" \
    --users "$users" \
    --spawn-rate "$spawn_rate" \
    --run-time "$run_time" \
    --csv-prefix "$csv_prefix" \
    --kubeconfig "$C0_KUBECONFIG" \
    --namespace "$NAMESPACE" \
    --precheck-config "$C0_PRECHECK_PROFILE" \
    --phase-config "$PHASE_PROFILE" \
    --protocol-config "$PROTOCOL_PROFILE" \
    --cluster-capture-config "$CLUSTER_CAPTURE_PROFILE" \
    --metric-set-config "$METRIC_SET_PROFILE"
done
```

---

## 20. Run Individual C0 Pilot Sweeps

### Windows PowerShell

```powershell
$Replicas = @("A", "B", "C")

$PilotFamilies = @(
  @{ Script = ".\scripts\load\pilot\Start-PilotWorkerCountSweep.ps1"; Scenarios = @("W1", "W2", "W3", "W4") },
  @{ Script = ".\scripts\load\pilot\Start-PilotWorkloadSweep.ps1"; Scenarios = @("WL1", "WL2", "WL3") },
  @{ Script = ".\scripts\load\pilot\Start-PilotModelSweep.ps1"; Scenarios = @("M1", "M2", "M3", "M4") },
  @{ Script = ".\scripts\load\pilot\Start-PilotPlacementSweep.ps1"; Scenarios = @("PL1", "PL2") }
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
        -PrecheckConfig $C0PrecheckProfile `
        -PhaseConfig $PhaseProfile `
        -ProtocolConfig $ProtocolProfile `
        -ClusterCaptureConfig $ClusterCaptureProfile `
        -MetricSetConfig $MetricSetProfile `
        -AutoApplyK8s
    }
  }
}
```

### Bash

```bash
replicas=(A B C)

for script_and_scenarios in \
  "./scripts/load/pilot/start-pilot-worker-count-sweep.sh W1 W2 W3 W4" \
  "./scripts/load/pilot/start-pilot-workload-sweep.sh WL1 WL2 WL3" \
  "./scripts/load/pilot/start-pilot-model-sweep.sh M1 M2 M3 M4" \
  "./scripts/load/pilot/start-pilot-placement-sweep.sh PL1 PL2"
do
  set -- $script_and_scenarios
  script="$1"
  shift

  for scenario in "$@"; do
    for replica in "${replicas[@]}"; do
      bash "$script" \
        --scenario "$scenario" \
        --replica "$replica" \
        --kubeconfig "$C0_KUBECONFIG" \
        --namespace "$NAMESPACE" \
        --base-url "$BASE_URL" \
        --precheck-config "$C0_PRECHECK_PROFILE" \
        --phase-config "$PHASE_PROFILE" \
        --protocol-config "$PROTOCOL_PROFILE" \
        --cluster-capture-config "$CLUSTER_CAPTURE_PROFILE" \
        --metric-set-config "$METRIC_SET_PROFILE" \
        --auto-apply-k8s
    done
  done
done
```

---

## 21. Run the Consolidated C0 Pilot Campaign

### Windows PowerShell

```powershell
$PilotConsolidationProfile = ".\config\pilot-consolidation\profiles\PC_CONSOLIDATED_PILOT_CAMPAIGN.json"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-ConsolidatedPilotBenchmarks.ps1" `
  -Family all `
  -ProfileConfig $PilotConsolidationProfile `
  -StatisticalRigorConfig $StatisticalRigorProfile `
  -Kubeconfig $C0Kubeconfig `
  -Namespace $Namespace `
  -BaseUrl $BaseUrl `
  -ContinueOnFailure
```

### Bash

```bash
PILOT_CONSOLIDATION_PROFILE="./config/pilot-consolidation/profiles/PC_CONSOLIDATED_PILOT_CAMPAIGN.json"

bash ./scripts/load/post/start-consolidated-pilot-benchmarks.sh \
  --family all \
  --profile-config "$PILOT_CONSOLIDATION_PROFILE" \
  --statistical-rigor-config "$STATISTICAL_RIGOR_PROFILE" \
  --kubeconfig "$C0_KUBECONFIG" \
  --namespace "$NAMESPACE" \
  --base-url "$BASE_URL" \
  --continue-on-failure
```

---

## 22. Validate `proxmox-k3s` Availability

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

If the binary is not in `PATH`, use an explicit tool path.

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

---

## 23. Validate Provider Local Configuration Files

### Windows PowerShell

```powershell
$RequiredProviderFiles = @(
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

foreach ($File in $RequiredProviderFiles) {
  if (-not (Test-Path $File)) {
    throw "Missing provider-local file: $File"
  }
}
```

### Bash

```bash
required_provider_files=(
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

for file in "${required_provider_files[@]}"; do
  test -f "$file" || { echo "Missing provider-local file: $file" >&2; exit 1; }
done
```

---

## 24. Direct Provider Template Maintenance

Use direct provider commands only for controlled infrastructure maintenance.

### Windows PowerShell

```powershell
proxmox-k3s template create -c .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml
```

### Bash

```bash
proxmox-k3s template create -c ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml
```

### Windows PowerShell

```powershell
proxmox-k3s template delete -c .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml
```

### Bash

```bash
proxmox-k3s template delete -c ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml
```

---

## 25. Direct Provider Cluster Maintenance

Use wrapper scripts for normal executions. Use direct commands only when controlled provider maintenance is required. Cluster operations use the `proxmox-k3s` `cluster` command namespace.

### Windows PowerShell

```powershell
proxmox-k3s cluster create -c .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml
proxmox-k3s cluster kubeconfig -c .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml
```

### Bash

```bash
proxmox-k3s cluster create -c ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml
proxmox-k3s cluster kubeconfig -c ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml
```

The direct provider delete command prompts for confirmation. Confirm only after verifying the target cluster identity.

### Windows PowerShell

```powershell
proxmox-k3s cluster delete -c .\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml
```

### Bash

```bash
proxmox-k3s cluster delete -c ./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml
```

---

## 26. Dry-Run C1 Provider-Backed Baseline

### Windows PowerShell

```powershell
$C1CycleConfig = ".\config\experimental-cycles\C1.json"
$C1ProviderConfig = ".\config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $C1CycleConfig `
  -ExecutionScope provider-backed-cycle `
  -ToolPath $ToolPath `
  -ProviderConfig $C1ProviderConfig `
  -BaselineReplicas "A,B,C" `
  -RunId "C1_dry_run" `
  -WriteLatestAliases `
  -DryRun
```

### Bash

```bash
C1_CYCLE_CONFIG="./config/experimental-cycles/C1.json"
C1_PROVIDER_CONFIG="./config/infrastructure/providers/proxmox-k3s/local/cluster.c1-1cp-2w-8c16g.local.yaml"

bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$C1_CYCLE_CONFIG" \
  --execution-scope provider-backed-cycle \
  --tool-path "$TOOL_PATH" \
  --provider-config "$C1_PROVIDER_CONFIG" \
  --baseline-replicas "A,B,C" \
  --run-id "C1_dry_run" \
  --write-latest-aliases \
  --dry-run
```

---

## 27. Execute C1 Provider-Backed Baseline

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $C1CycleConfig `
  -ExecutionScope provider-backed-cycle `
  -ToolPath $ToolPath `
  -ProviderConfig $C1ProviderConfig `
  -BaselineReplicas "A,B,C" `
  -RunId "C1_regeneration" `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$C1_CYCLE_CONFIG" \
  --execution-scope provider-backed-cycle \
  --tool-path "$TOOL_PATH" \
  --provider-config "$C1_PROVIDER_CONFIG" \
  --baseline-replicas "A,B,C" \
  --run-id "C1_regeneration" \
  --write-latest-aliases
```

---

## 28. Execute C1 with Non-Blocking Metrics Warning Bypass

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $C1CycleConfig `
  -ExecutionScope provider-backed-cycle `
  -ToolPath $ToolPath `
  -ProviderConfig $C1ProviderConfig `
  -BaselineReplicas "A,B,C" `
  -RunId "C1_regeneration" `
  -AllowMetricsWarning `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$C1_CYCLE_CONFIG" \
  --execution-scope provider-backed-cycle \
  --tool-path "$TOOL_PATH" \
  --provider-config "$C1_PROVIDER_CONFIG" \
  --baseline-replicas "A,B,C" \
  --run-id "C1_regeneration" \
  --allow-metrics-warning \
  --write-latest-aliases
```

---

## 29. Refresh a Provider-Backed Kubeconfig

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $C1CycleConfig `
  -ExecutionScope provisioning `
  -ProvisioningAction kubeconfig `
  -ToolPath $ToolPath `
  -ProviderConfig $C1ProviderConfig `
  -RunId "C1_kubeconfig_refresh" `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$C1_CYCLE_CONFIG" \
  --execution-scope provisioning \
  --provisioning-action kubeconfig \
  --tool-path "$TOOL_PATH" \
  --provider-config "$C1_PROVIDER_CONFIG" \
  --run-id "C1_kubeconfig_refresh" \
  --write-latest-aliases
```

---

## 30. Validate a Provider-Backed Cluster

### Windows PowerShell

```powershell
$C1Kubeconfig = ".\config\cluster-access\generated\proxmox-k3s\c1-1cp-2w-8c16g\kubeconfig"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $C1CycleConfig `
  -ExecutionScope cluster-validation `
  -Kubeconfig $C1Kubeconfig `
  -RunId "C1_cluster_validation" `
  -WriteLatestAliases
```

### Bash

```bash
C1_KUBECONFIG="./config/cluster-access/generated/proxmox-k3s/c1-1cp-2w-8c16g/kubeconfig"

bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$C1_CYCLE_CONFIG" \
  --execution-scope cluster-validation \
  --kubeconfig "$C1_KUBECONFIG" \
  --run-id "C1_cluster_validation" \
  --write-latest-aliases
```

---

## 31. Deploy LocalAI on a Provider-Backed Cluster

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $C1CycleConfig `
  -ExecutionScope localai-deployment `
  -DeploymentAction deploy `
  -Kubeconfig $C1Kubeconfig `
  -BaseUrl $BaseUrl `
  -RunId "C1_localai_deployment" `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$C1_CYCLE_CONFIG" \
  --execution-scope localai-deployment \
  --deployment-action deploy \
  --kubeconfig "$C1_KUBECONFIG" \
  --base-url "$BASE_URL" \
  --run-id "C1_localai_deployment" \
  --write-latest-aliases
```

---

## 32. Capture Minimal Observability

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $C1CycleConfig `
  -ExecutionScope minimal-observability `
  -MinimalObservabilityAction capture `
  -ObservabilityStage post-deployment `
  -Kubeconfig $C1Kubeconfig `
  -RunId "C1_observability_post_deployment" `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$C1_CYCLE_CONFIG" \
  --execution-scope minimal-observability \
  --minimal-observability-action capture \
  --observability-stage post-deployment \
  --kubeconfig "$C1_KUBECONFIG" \
  --run-id "C1_observability_post_deployment" \
  --write-latest-aliases
```

---

## 33. Destroy a Provider-Backed Cluster Through the Wrapper

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCycle.ps1" `
  -CycleConfig $C1CycleConfig `
  -ExecutionScope provisioning `
  -ProvisioningAction destroy `
  -ToolPath $ToolPath `
  -ProviderConfig $C1ProviderConfig `
  -ConfirmDelete `
  -RunId "C1_destroy" `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-cycle.sh \
  --cycle-config "$C1_CYCLE_CONFIG" \
  --execution-scope provisioning \
  --provisioning-action destroy \
  --tool-path "$TOOL_PATH" \
  --provider-config "$C1_PROVIDER_CONFIG" \
  --confirm-delete \
  --run-id "C1_destroy" \
  --write-latest-aliases
```

---

## 34. Execute One Provider-Backed Campaign

The example below runs `C2`. Replace the cycle profile and run identifier for `C3`, `C4`, `C5`, or `C6`.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1" `
  -CycleConfig .\config\experimental-cycles\C2.json `
  -ToolPath $ToolPath `
  -RunId "C2_regeneration" `
  -BaselineReplicas "A,B,C" `
  -BaseUrl $BaseUrl `
  -ContinueOnFailure `
  -AllowMetricsWarning `
  -ConfirmDelete `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config ./config/experimental-cycles/C2.json \
  --tool-path "$TOOL_PATH" \
  --run-id "C2_regeneration" \
  --baseline-replicas "A,B,C" \
  --base-url "$BASE_URL" \
  --continue-on-failure \
  --allow-metrics-warning \
  --confirm-delete \
  --force-freeze \
  --write-latest-aliases
```

---

## 35. Dry-Run Provider-Backed Campaigns C2-C6

### Windows PowerShell

```powershell
foreach ($Cycle in @("C2", "C3", "C4", "C5", "C6")) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1" `
    -CycleConfig ".\config\experimental-cycles\$Cycle.json" `
    -ToolPath $ToolPath `
    -RunId "${Cycle}_dry_run" `
    -BaselineReplicas "A,B,C" `
    -BaseUrl $BaseUrl `
    -ContinueOnFailure `
    -AllowMetricsWarning `
    -ConfirmDelete `
    -ForceFreeze `
    -WriteLatestAliases `
    -DryRun
}
```

### Bash

```bash
for cycle in C2 C3 C4 C5 C6; do
  bash ./scripts/experimental-cycles/start-experimental-campaign.sh \
    --cycle-config "./config/experimental-cycles/${cycle}.json" \
    --tool-path "$TOOL_PATH" \
    --run-id "${cycle}_dry_run" \
    --baseline-replicas "A,B,C" \
    --base-url "$BASE_URL" \
    --continue-on-failure \
    --allow-metrics-warning \
    --confirm-delete \
    --force-freeze \
    --write-latest-aliases \
    --dry-run
done
```

---

## 36. Execute Provider-Backed Campaigns C2-C6

### Windows PowerShell

```powershell
foreach ($Cycle in @("C2", "C3", "C4", "C5", "C6")) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1" `
    -CycleConfig ".\config\experimental-cycles\$Cycle.json" `
    -ToolPath $ToolPath `
    -RunId "${Cycle}_regeneration" `
    -BaselineReplicas "A,B,C" `
    -BaseUrl $BaseUrl `
    -ContinueOnFailure `
    -AllowMetricsWarning `
    -ConfirmDelete `
    -ForceFreeze `
    -WriteLatestAliases
}
```

### Bash

```bash
for cycle in C2 C3 C4 C5 C6; do
  bash ./scripts/experimental-cycles/start-experimental-campaign.sh \
    --cycle-config "./config/experimental-cycles/${cycle}.json" \
    --tool-path "$TOOL_PATH" \
    --run-id "${cycle}_regeneration" \
    --baseline-replicas "A,B,C" \
    --base-url "$BASE_URL" \
    --continue-on-failure \
    --allow-metrics-warning \
    --confirm-delete \
    --force-freeze \
    --write-latest-aliases
done
```

---

## 37. Inspect Campaign Variant Status

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C2 -Recurse -Filter "*variant*status*.json" |
  Select-Object FullName
```

### Bash

```bash
find ./results/experimental-cycles/C2 -type f -name "*variant*status*.json" -print | sort
```

---

## 38. Apply a Latency Profile Manually

Prefer the full `C5` campaign for official latency-injection execution. Use the manual command only for controlled inspection.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\latency\Apply-LatencyProfile.ps1" `
  -ProfileConfig .\config\latency\profiles\L1_EDGE_NEAR.json `
  -Kubeconfig $C1Kubeconfig `
  -Action apply
```

### Bash

```bash
bash ./scripts/latency/apply-latency-profile.sh \
  --profile-config ./config/latency/profiles/L1_EDGE_NEAR.json \
  --kubeconfig "$C1_KUBECONFIG" \
  --action apply
```

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\latency\Apply-LatencyProfile.ps1" `
  -ProfileConfig .\config\latency\profiles\L1_EDGE_NEAR.json `
  -Kubeconfig $C1Kubeconfig `
  -Action cleanup
```

### Bash

```bash
bash ./scripts/latency/apply-latency-profile.sh \
  --profile-config ./config/latency/profiles/L1_EDGE_NEAR.json \
  --kubeconfig "$C1_KUBECONFIG" \
  --action cleanup
```

---

## 39. Render Kubernetes Compositions

### Windows PowerShell

```powershell
kubectl kustomize .\infra\k8s\compositions\foundation\namespace
kubectl kustomize .\infra\k8s\compositions\foundation\storage
kubectl kustomize .\infra\k8s\compositions\shared\rpc-workers-services
kubectl kustomize .\infra\k8s\compositions\topology\colocated-genai-pb-worker-02-w2
kubectl kustomize .\infra\k8s\compositions\server\models\m1-provider-backed
```

### Bash

```bash
kubectl kustomize ./infra/k8s/compositions/foundation/namespace
kubectl kustomize ./infra/k8s/compositions/foundation/storage
kubectl kustomize ./infra/k8s/compositions/shared/rpc-workers-services
kubectl kustomize ./infra/k8s/compositions/topology/colocated-genai-pb-worker-02-w2
kubectl kustomize ./infra/k8s/compositions/server/models/m1-provider-backed
```

---

## 40. Inspect Placement Profiles

### Windows PowerShell

```powershell
python -m json.tool .\config\placement\PLACEMENT_PROFILES_INDEX.json > $null
Get-ChildItem .\config\placement\profiles\PL_*.json | Select-Object Name
```

### Bash

```bash
python3 -m json.tool ./config/placement/PLACEMENT_PROFILES_INDEX.json >/dev/null || python -m json.tool ./config/placement/PLACEMENT_PROFILES_INDEX.json >/dev/null
find ./config/placement/profiles -maxdepth 1 -type f -name "PL_*.json" -print | sort
```

---

## 41. Inspect Runtime Pod Placement

### Windows PowerShell

```powershell
kubectl --kubeconfig $C1Kubeconfig get pods -n $Namespace -o wide
kubectl --kubeconfig $C1Kubeconfig get nodes --show-labels
```

### Bash

```bash
kubectl --kubeconfig "$C1_KUBECONFIG" get pods -n "$NAMESPACE" -o wide
kubectl --kubeconfig "$C1_KUBECONFIG" get nodes --show-labels
```

---

## 42. Inspect Cluster Metrics

### Windows PowerShell

```powershell
kubectl --kubeconfig $C1Kubeconfig top nodes
kubectl --kubeconfig $C1Kubeconfig top pods -n $Namespace
kubectl --kubeconfig $C1Kubeconfig get events -A --sort-by=.metadata.creationTimestamp
```

### Bash

```bash
kubectl --kubeconfig "$C1_KUBECONFIG" top nodes
kubectl --kubeconfig "$C1_KUBECONFIG" top pods -n "$NAMESPACE"
kubectl --kubeconfig "$C1_KUBECONFIG" get events -A --sort-by=.metadata.creationTimestamp
```

---

## 43. Inspect LocalAI Logs

### Windows PowerShell

```powershell
kubectl --kubeconfig $C1Kubeconfig logs -n $Namespace deployment/localai-server --tail=200
kubectl --kubeconfig $C1Kubeconfig logs -n $Namespace deployment/localai-rpc-a --tail=200
kubectl --kubeconfig $C1Kubeconfig logs -n $Namespace deployment/localai-rpc-b --tail=200
```

### Bash

```bash
kubectl --kubeconfig "$C1_KUBECONFIG" logs -n "$NAMESPACE" deployment/localai-server --tail=200
kubectl --kubeconfig "$C1_KUBECONFIG" logs -n "$NAMESPACE" deployment/localai-rpc-a --tail=200
kubectl --kubeconfig "$C1_KUBECONFIG" logs -n "$NAMESPACE" deployment/localai-rpc-b --tail=200
```

---

## 44. Inspect LocalAI API Manually

A LocalAI port forward must already be running.

### Windows PowerShell

```powershell
Invoke-RestMethod -Uri "http://localhost:8080/v1/models" -Method Get
Invoke-RestMethod `
  -Uri "http://localhost:8080/v1/chat/completions" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"model":"llama-3.2-1b-instruct:q4_k_m","messages":[{"role":"user","content":"Reply with only READY."}],"temperature":0.1}'
```

### Bash

```bash
curl -fsS http://localhost:8080/v1/models
curl -fsS http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"llama-3.2-1b-instruct:q4_k_m","messages":[{"role":"user","content":"Reply with only READY."}],"temperature":0.1}'
```

---

## 45. Run a Standalone Locust Validation

A LocalAI port forward must already be running.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\exploratory\Start-LocustExploratory.ps1" `
  -BaseUrl "http://localhost:8080" `
  -Model "llama-3.2-1b-instruct:q4_k_m" `
  -Users 2 `
  -SpawnRate 1 `
  -RunTime "1m" `
  -CsvPrefix ".\results\manual\locust-standalone" `
  -Kubeconfig $C1Kubeconfig `
  -Namespace $Namespace
```

### Bash

```bash
bash ./scripts/load/exploratory/start-locust-exploratory.sh \
  --base-url "http://localhost:8080" \
  --model "llama-3.2-1b-instruct:q4_k_m" \
  --users 2 \
  --spawn-rate 1 \
  --run-time "1m" \
  --csv-prefix "./results/manual/locust-standalone" \
  --kubeconfig "$C1_KUBECONFIG" \
  --namespace "$NAMESPACE"
```

---

## 46. Inspect Locust CSV Artifacts

### Windows PowerShell

```powershell
Get-ChildItem .\results -Recurse -Filter "*_stats.csv" | Select-Object FullName, Length
Get-ChildItem .\results -Recurse -Filter "*_failures.csv" | Select-Object FullName, Length
Get-ChildItem .\results -Recurse -Filter "*_exceptions.csv" | Select-Object FullName, Length
```

### Bash

```bash
find ./results -type f -name "*_stats.csv" -print | sort
find ./results -type f -name "*_failures.csv" -print | sort
find ./results -type f -name "*_exceptions.csv" -print | sort
```

---

## 47. Generate Technical Diagnosis for One Cycle

The example below regenerates `C1`.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-TechnicalDiagnosis.ps1" `
  -ProfileConfig .\config\technical-diagnosis\profiles\TD_C1_PROVIDER_BACKED_BASELINE.json `
  -Family all
```

### Bash

```bash
bash ./scripts/load/post/start-technical-diagnosis.sh \
  --profile-config ./config/technical-diagnosis/profiles/TD_C1_PROVIDER_BACKED_BASELINE.json \
  --family all
```

---

## 48. Generate Technical Diagnosis for All Cycles

### Windows PowerShell

```powershell
$DiagnosisProfiles = @(
  ".\config\technical-diagnosis\profiles\TD_C0_HISTORICAL_FIXED_CLUSTER.json",
  ".\config\technical-diagnosis\profiles\TD_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\technical-diagnosis\profiles\TD_C2_RESOURCE_VARIATION.json",
  ".\config\technical-diagnosis\profiles\TD_C3_NODE_COUNT_VARIATION.json",
  ".\config\technical-diagnosis\profiles\TD_C4_PLACEMENT_VARIATION.json",
  ".\config\technical-diagnosis\profiles\TD_C5_LATENCY_INJECTION.json",
  ".\config\technical-diagnosis\profiles\TD_C6_MULTI_TENANCY.json",
  ".\config\technical-diagnosis\profiles\TD_C7_DEFAULT_SCHEDULER_BASELINE.json"
)

foreach ($Profile in $DiagnosisProfiles) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-TechnicalDiagnosis.ps1" `
    -ProfileConfig $Profile `
    -Family all
}
```

### Bash

```bash
for profile in \
  ./config/technical-diagnosis/profiles/TD_C0_HISTORICAL_FIXED_CLUSTER.json \
  ./config/technical-diagnosis/profiles/TD_C1_PROVIDER_BACKED_BASELINE.json \
  ./config/technical-diagnosis/profiles/TD_C2_RESOURCE_VARIATION.json \
  ./config/technical-diagnosis/profiles/TD_C3_NODE_COUNT_VARIATION.json \
  ./config/technical-diagnosis/profiles/TD_C4_PLACEMENT_VARIATION.json \
  ./config/technical-diagnosis/profiles/TD_C5_LATENCY_INJECTION.json \
  ./config/technical-diagnosis/profiles/TD_C6_MULTI_TENANCY.json \
  ./config/technical-diagnosis/profiles/TD_C7_DEFAULT_SCHEDULER_BASELINE.json
do
  bash ./scripts/load/post/start-technical-diagnosis.sh \
    --profile-config "$profile" \
    --family all
done
```

---

## 49. Generate Reporting for One Cycle

The example below regenerates `C1`.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-Reporting.ps1" `
  -ProfileConfig .\config\reporting\profiles\RP_C1_PROVIDER_BACKED_BASELINE.json
```

### Bash

```bash
bash ./scripts/load/post/start-reporting.sh \
  --profile-config ./config/reporting/profiles/RP_C1_PROVIDER_BACKED_BASELINE.json
```

---

## 50. Generate Reporting for All Cycles

### Windows PowerShell

```powershell
$ReportingProfiles = @(
  ".\config\reporting\profiles\RP_C0_HISTORICAL_FIXED_CLUSTER.json",
  ".\config\reporting\profiles\RP_C1_PROVIDER_BACKED_BASELINE.json",
  ".\config\reporting\profiles\RP_C2_RESOURCE_VARIATION.json",
  ".\config\reporting\profiles\RP_C3_NODE_COUNT_VARIATION.json",
  ".\config\reporting\profiles\RP_C4_PLACEMENT_VARIATION.json",
  ".\config\reporting\profiles\RP_C5_LATENCY_INJECTION.json",
  ".\config\reporting\profiles\RP_C6_MULTI_TENANCY.json",
  ".\config\reporting\profiles\RP_C7_DEFAULT_SCHEDULER_BASELINE.json"
)

foreach ($Profile in $ReportingProfiles) {
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-Reporting.ps1" `
    -ProfileConfig $Profile
}
```

### Bash

```bash
for profile in \
  ./config/reporting/profiles/RP_C0_HISTORICAL_FIXED_CLUSTER.json \
  ./config/reporting/profiles/RP_C1_PROVIDER_BACKED_BASELINE.json \
  ./config/reporting/profiles/RP_C2_RESOURCE_VARIATION.json \
  ./config/reporting/profiles/RP_C3_NODE_COUNT_VARIATION.json \
  ./config/reporting/profiles/RP_C4_PLACEMENT_VARIATION.json \
  ./config/reporting/profiles/RP_C5_LATENCY_INJECTION.json \
  ./config/reporting/profiles/RP_C6_MULTI_TENANCY.json \
  ./config/reporting/profiles/RP_C7_DEFAULT_SCHEDULER_BASELINE.json
do
  bash ./scripts/load/post/start-reporting.sh \
    --profile-config "$profile"
done
```

---

## 51. Refresh the Global Reporting Site

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

---

## 52. Evaluate Completion Gate for One Cycle

The example below evaluates `C1`.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-CompletionGate.ps1" `
  -ProfileConfig .\config\completion-gate\profiles\CG_C1_PROVIDER_BACKED_BASELINE.json `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -DiagnosisJson .\results\experimental-cycles\C1\diagnosis\latest-diagnosis.json `
  -EvaluationId "C1_completion_gate"
```

### Bash

```bash
bash ./scripts/load/post/start-completion-gate.sh \
  --profile-config ./config/completion-gate/profiles/CG_C1_PROVIDER_BACKED_BASELINE.json \
  --cycle-config ./config/experimental-cycles/C1.json \
  --diagnosis-json ./results/experimental-cycles/C1/diagnosis/latest-diagnosis.json \
  --evaluation-id "C1_completion_gate"
```

If the diagnosis filename is timestamped rather than aliased, replace `latest-diagnosis.json` with the exact generated diagnosis file.

---

## 53. Freeze One Cycle

The example below freezes `C1`.

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\load\post\Start-FreezeExperimentalCycle.ps1" `
  -RepoRoot . `
  -CycleConfig .\config\experimental-cycles\C1.json `
  -ProfileConfig .\config\freeze\profiles\FR_C1_PROVIDER_BACKED_BASELINE.json `
  -FreezeId "C1_freeze" `
  -Force `
  -WriteLatestAliases
```

### Bash

```bash
bash ./scripts/load/post/start-freeze-experimental-cycle.sh \
  --repo-root . \
  --cycle-config ./config/experimental-cycles/C1.json \
  --profile-config ./config/freeze/profiles/FR_C1_PROVIDER_BACKED_BASELINE.json \
  --freeze-id "C1_freeze" \
  --force \
  --write-latest-aliases
```

---

## 54. Inspect Post-Processing Outputs

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C1\diagnosis -Force
Get-ChildItem .\results\experimental-cycles\C1\reporting -Force
Get-ChildItem .\results\experimental-cycles\C1\completion-gate -Force
Get-ChildItem .\results\experimental-cycles\C1\freeze -Force
```

### Bash

```bash
ls -la ./results/experimental-cycles/C1/diagnosis
ls -la ./results/experimental-cycles/C1/reporting
ls -la ./results/experimental-cycles/C1/completion-gate
ls -la ./results/experimental-cycles/C1/freeze
```

---

## 55. Inspect Completion Statuses

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles -Recurse -Filter "*completion*manifest*.json" |
  ForEach-Object {
    Write-Host "----- $($_.FullName)"
    Get-Content $_.FullName -Raw
  }
```

### Bash

```bash
find ./results/experimental-cycles -type f -name "*completion*manifest*.json" -print |
while IFS= read -r file; do
  echo "----- $file"
  cat "$file"
done
```

---

## 56. Optional Results Archive

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

---

## 57. Clean Generated Results

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

## 58. Verify Clean Results State

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

---

## 59. Full Regeneration Order

Use the detailed cycle-specific runbooks for the complete command sequence.

### Windows PowerShell

```powershell
Write-Host "1. Regenerate C0 using docs\runbooks\06-fixed-cluster-c0-execution.md"
Write-Host "2. Regenerate C1 using docs\runbooks\07-provider-backed-c1-baseline-execution.md"
Write-Host "3. Regenerate C2-C6 using docs\runbooks\08-provider-backed-c2-c6-campaign-execution.md"
Write-Host "4. Regenerate C7 using docs\runbooks\09-default-scheduler-c7-baseline-execution.md"
Write-Host "5. Regenerate C8 using docs\runbooks\10-resource-aware-scheduler-c8-execution.md"
Write-Host "6. Regenerate C9 using docs\runbooks\11-network-aware-scheduler-c9-execution.md"
Write-Host "7. Refresh global reporting using docs\runbooks\14-diagnosis-reporting-completion-gate-and-freeze.md"
```

### Bash

```bash
printf '%s\n' "1. Regenerate C0 using docs/runbooks/06-fixed-cluster-c0-execution.md"
printf '%s\n' "2. Regenerate C1 using docs/runbooks/07-provider-backed-c1-baseline-execution.md"
printf '%s\n' "3. Regenerate C2-C6 using docs/runbooks/08-provider-backed-c2-c6-campaign-execution.md"
printf '%s\n' "4. Regenerate C7 using docs/runbooks/09-default-scheduler-c7-baseline-execution.md"
printf '%s\n' "5. Regenerate C8 using docs/runbooks/10-resource-aware-scheduler-c8-execution.md"
printf '%s\n' "6. Regenerate C9 using docs/runbooks/11-network-aware-scheduler-c9-execution.md"
printf '%s\n' "7. Refresh global reporting using docs/runbooks/14-diagnosis-reporting-completion-gate-and-freeze.md"
```

---

## 60. Collect a Sanitized Escalation Snapshot

Review generated files before sharing them. Do not include kubeconfigs, provider-local YAML files, tokens, private endpoints, or private keys.

### Windows PowerShell

```powershell
$BundleRoot = ".\results\support-bundle"
New-Item -ItemType Directory -Force -Path $BundleRoot | Out-Null

kubectl --kubeconfig $C1Kubeconfig get nodes -o wide > "$BundleRoot\nodes-wide.txt"
kubectl --kubeconfig $C1Kubeconfig get pods -A -o wide > "$BundleRoot\pods-wide.txt"
kubectl --kubeconfig $C1Kubeconfig get events -A --sort-by=.metadata.creationTimestamp > "$BundleRoot\events.txt"

Get-ChildItem .\results\experimental-cycles -Recurse -Include "*summary*.txt","*manifest*.json","*diagnosis*.txt" |
  Copy-Item -Destination $BundleRoot -Force
```

### Bash

```bash
BUNDLE_ROOT="./results/support-bundle"
mkdir -p "$BUNDLE_ROOT"

kubectl --kubeconfig "$C1_KUBECONFIG" get nodes -o wide > "$BUNDLE_ROOT/nodes-wide.txt"
kubectl --kubeconfig "$C1_KUBECONFIG" get pods -A -o wide > "$BUNDLE_ROOT/pods-wide.txt"
kubectl --kubeconfig "$C1_KUBECONFIG" get events -A --sort-by=.metadata.creationTimestamp > "$BUNDLE_ROOT/events.txt"

find ./results/experimental-cycles -type f \( -name "*summary*.txt" -o -name "*manifest*.json" -o -name "*diagnosis*.txt" \) \
  -exec cp {} "$BUNDLE_ROOT" \;
```

---

## 61. Stop Local Port-Forward Processes

### Windows PowerShell

```powershell
Get-Process |
  Where-Object { $_.ProcessName -match "kubectl" } |
  Select-Object Id, ProcessName, StartTime
```

### Bash

```bash
ps aux | grep kubectl | grep port-forward | grep -v grep || true
```

Terminate only the processes that correspond to intentional local port-forward sessions.

### Windows PowerShell

```powershell
Stop-Process -Id <PROCESS_ID>
```

### Bash

```bash
kill <PROCESS_ID>
```

---

## 62. Clean LocalAI Resources from a Target Namespace

Use this only for controlled recovery.

### Windows PowerShell

```powershell
kubectl --kubeconfig $C1Kubeconfig delete deployment -n $Namespace -l app.kubernetes.io/part-of=localai-benchmark --ignore-not-found
kubectl --kubeconfig $C1Kubeconfig delete service -n $Namespace -l app.kubernetes.io/part-of=localai-benchmark --ignore-not-found
kubectl --kubeconfig $C1Kubeconfig delete configmap -n $Namespace -l app.kubernetes.io/part-of=localai-benchmark --ignore-not-found
```

### Bash

```bash
kubectl --kubeconfig "$C1_KUBECONFIG" delete deployment -n "$NAMESPACE" -l app.kubernetes.io/part-of=localai-benchmark --ignore-not-found
kubectl --kubeconfig "$C1_KUBECONFIG" delete service -n "$NAMESPACE" -l app.kubernetes.io/part-of=localai-benchmark --ignore-not-found
kubectl --kubeconfig "$C1_KUBECONFIG" delete configmap -n "$NAMESPACE" -l app.kubernetes.io/part-of=localai-benchmark --ignore-not-found
```

PVC deletion is intentionally excluded from the command above. Delete storage resources only when model storage reset is explicitly required.

---

## 63. Validate Final Artifact Coverage

### Windows PowerShell

```powershell
foreach ($Cycle in @("C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9")) {
  Write-Host "=== $Cycle ==="
  Test-Path ".\results\experimental-cycles\$Cycle"
  Get-ChildItem ".\results\experimental-cycles\$Cycle" -Force -ErrorAction SilentlyContinue |
    Select-Object Name
}
```

### Bash

```bash
for cycle in C0 C1 C2 C3 C4 C5 C6 C7 C8 C9; do
  echo "=== $cycle ==="
  test -d "./results/experimental-cycles/$cycle" || echo "missing cycle root"
  find "./results/experimental-cycles/$cycle" -maxdepth 1 -mindepth 1 -print 2>/dev/null | sort
done
```

---

## 64. Validate C7 Default-Scheduler Manifests

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

---

## 65. Dry-Run C7 Default-Scheduler Baseline

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C7.json `
  -ToolPath "proxmox-k3s" `
  -RunId "C7_default_scheduler_baseline" `
  -DryRun `
  -AllowMetricsWarning `
  -WriteLatestAliases
```

### Bash

```bash
scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config config/experimental-cycles/C7.json \
  --tool-path proxmox-k3s \
  --run-id C7_default_scheduler_baseline \
  --dry-run \
  --allow-metrics-warning \
  --write-latest-aliases
```

---

## 66. Execute C7 Default-Scheduler Baseline

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C7.json `
  -ToolPath "proxmox-k3s" `
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
  --tool-path proxmox-k3s \
  --run-id C7_default_scheduler_baseline \
  --allow-metrics-warning \
  --continue-on-failure \
  --confirm-delete \
  --write-latest-aliases
```

---

## 67. Capture C7 Scheduler Decisions Manually

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

---

## 68. Inspect C7 Scheduler Evidence

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C7 -Recurse `
  -Filter "default-scheduler-decision-evidence.json" |
  Select-Object FullName, Length
```

### Bash

```bash
find results/experimental-cycles/C7 -name "default-scheduler-decision-evidence.json" -print | sort
```

---


## 69. Dry-Run C8 Resource-Aware Scheduler

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C8.json `
  -RunId "C8_resource_aware_scheduler_dry_run" `
  -BaselineReplicas "A,B,C" `
  -DryRun `
  -SkipDelete
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config ./config/experimental-cycles/C8.json \
  --run-id C8_resource_aware_scheduler_dry_run \
  --baseline-replicas "A,B,C" \
  --dry-run \
  --skip-delete
```

---

## 70. Execute C8 Resource-Aware Scheduler

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C8.json `
  -RunId "C8_resource_aware_scheduler" `
  -BaselineReplicas "A,B,C" `
  -ConfirmDelete `
  -ForceFreeze `
  -WriteLatestAliases
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config ./config/experimental-cycles/C8.json \
  --run-id C8_resource_aware_scheduler \
  --baseline-replicas "A,B,C" \
  --confirm-delete \
  --force-freeze \
  --write-latest-aliases
```

---

## 71. Validate C8 Resource-Aware Scheduler Manifests

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

---

## 72. Inspect C8 Resource-Aware Scheduler Evidence

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C8 -Recurse `
  -Filter "resource-aware-scheduler-decision-evidence.json" |
  Select-Object FullName, Length
Get-ChildItem .\results\experimental-cycles\C8\scheduler\custom-scheduler -Recurse |
  Select-Object FullName, Length
```

### Bash

```bash
find ./results/experimental-cycles/C8 -name "resource-aware-scheduler-decision-evidence.json" -print | sort
find ./results/experimental-cycles/C8/scheduler/custom-scheduler -maxdepth 5 -type f | sort
```

---

## 73. Inspect C8 mon-agent and Rescheduling Evidence

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C8\observability\mon-agent -Recurse |
  Select-Object FullName, Length
Get-ChildItem .\results\experimental-cycles\C8\rescheduling -Recurse |
  Select-Object FullName, Length
```

### Bash

```bash
find ./results/experimental-cycles/C8/observability/mon-agent -maxdepth 5 -type f | sort
find ./results/experimental-cycles/C8/rescheduling -maxdepth 5 -type f | sort
```

---

## 74. Dry-Run C9 Network-Aware Scheduler Campaign

### Windows PowerShell

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\experimental-cycles\Start-ExperimentalCampaign.ps1 `
  -CycleConfig .\config\experimental-cycles\C9.json `
  -RunId "C9_network_aware_scheduler_dry_run" `
  -BaselineReplicas "A,B,C" `
  -DryRun `
  -SkipDelete
```

### Bash

```bash
./scripts/experimental-cycles/start-experimental-campaign.sh \
  --cycle-config ./config/experimental-cycles/C9.json \
  --run-id C9_network_aware_scheduler_dry_run \
  --baseline-replicas "A,B,C" \
  --dry-run \
  --skip-delete
```

---

## 75. Execute C9 Network-Aware Scheduler Campaign

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
  --cycle-config ./config/experimental-cycles/C9.json \
  --run-id C9_network_aware_scheduler \
  --baseline-replicas "A,B,C" \
  --confirm-delete \
  --force-freeze \
  --write-latest-aliases
```

---

## 76. Validate C9 Network-Aware Scheduler Manifests

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

---

## 77. Inspect C9 Network-Aware Evidence

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse |
  Where-Object { $_.FullName -match 'network-aware-scheduler|istio|mentat|mon-agent|cluster-lens|rescheduling|telemetry-priming' } |
  Select-Object FullName, Length

Get-ChildItem .\results\experimental-cycles\C9\scheduler -Recurse |
  Select-Object FullName, Length
```

### Bash

```bash
find ./results/experimental-cycles/C9/variants \
  \( -path '*network-aware-scheduler*' -o -path '*istio*' -o -path '*mentat*' -o -path '*mon-agent*' -o -path '*cluster-lens*' -o -path '*rescheduling*' -o -path '*telemetry-priming*' \) \
  -type f | sort

find ./results/experimental-cycles/C9/scheduler -maxdepth 6 -type f | sort
```

---

## 78. Inspect C9 cluster-lens Placement Evidence

### Windows PowerShell

```powershell
Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse -Filter cluster-lens-placement-summary.json |
  Select-Object FullName, Length

Get-ChildItem .\results\experimental-cycles\C9\variants -Recurse -Filter cluster-lens-placement-signature.csv |
  Select-Object FullName, Length
```

### Bash

```bash
find ./results/experimental-cycles/C9/variants -name cluster-lens-placement-summary.json -type f | sort
find ./results/experimental-cycles/C9/variants -name cluster-lens-placement-signature.csv -type f | sort
```

---

## 79. Capture C9 cluster-lens Placement Evidence Manually

The campaign runner captures cluster-lens automatically according to `clusterLensCaptureStagePolicy`. Use this command only for targeted inspection or recovery.

### Windows PowerShell

```powershell
python .\scripts\observability\cluster-lens\capture-cluster-lens-snapshot.py `
  --profile-config .\config\cluster-lens\profiles\CL_C9_PLACEMENT_SNAPSHOT.json `
  --scenario-config .\config\scenarios\network-aware-scheduler\NA_NETAWARE_2T_4N_L3_DIFFERENTIATED_M1M1_W2.json `
  --output-dir .\results\experimental-cycles\C9\variants\NA_NETAWARE_2T_4N_L3_DIFFERENTIATED_M1M1_W2\network-aware-scheduler\cluster-lens\manual `
  --capture-stage manual
```

### Bash

```bash
python scripts/observability/cluster-lens/capture-cluster-lens-snapshot.py \
  --profile-config ./config/cluster-lens/profiles/CL_C9_PLACEMENT_SNAPSHOT.json \
  --scenario-config ./config/scenarios/network-aware-scheduler/NA_NETAWARE_2T_4N_L3_DIFFERENTIATED_M1M1_W2.json \
  --output-dir ./results/experimental-cycles/C9/variants/NA_NETAWARE_2T_4N_L3_DIFFERENTIATED_M1M1_W2/network-aware-scheduler/cluster-lens/manual \
  --capture-stage manual
```

---

## 80. Inspect C9 Reporting Placement Sections

Use these commands after generating the C9 report or reporting site to verify that latency context and cluster-lens placement sections are visible.

### Windows PowerShell

```powershell
$Report = ".\results\reporting\cycles\C9\index.html"
$Patterns = @(
  "Network-aware latency profile context",
  "Cluster-lens placement evidence summary",
  "Cluster-lens tenant placement",
  "Scheduler comparison"
)

Select-String -Path $Report -Pattern $Patterns |
  Select-Object LineNumber, Line
```

### Bash

```bash
REPORT="./results/reporting/cycles/C9/index.html"

grep -nE 'Network-aware latency profile context|Cluster-lens placement evidence summary|Cluster-lens tenant placement|Scheduler comparison' "$REPORT"
```

When interpreting the report, compare rows with the same logical scenario and different scheduler modes. Topology columns should normally confirm comparable cluster structure; tenant-placement columns show whether LocalAI master and worker pods were assigned differently under `DEFAULT`, `LOADAWARE`, and `NETAWARE`.

---

## 81. Validate Global Reporting Site

### Windows PowerShell

```powershell
Test-Path .\results\reporting\index.html
Test-Path .\results\reporting\reporting-site-manifest.json
Get-ChildItem .\results\reporting -Force
```

### Bash

```bash
test -f ./results/reporting/index.html
test -f ./results/reporting/reporting-site-manifest.json
ls -la ./results/reporting
```

---

## 82. Final Readiness Checklist

### Windows PowerShell

```powershell
$ExpectedRoots = @(
  ".\results\experimental-cycles\C0",
  ".\results\experimental-cycles\C1",
  ".\results\experimental-cycles\C2",
  ".\results\experimental-cycles\C3",
  ".\results\experimental-cycles\C4",
  ".\results\experimental-cycles\C5",
  ".\results\experimental-cycles\C6",
  ".\results\experimental-cycles\C7",
  ".\results\experimental-cycles\C8",
  ".\results\experimental-cycles\C9",
  ".\results\reporting"
)

foreach ($Root in $ExpectedRoots) {
  if (-not (Test-Path $Root)) {
    throw "Missing expected result root: $Root"
  }
}

Write-Host "Artifact coverage check completed."
```

### Bash

```bash
expected_roots=(
  "./results/experimental-cycles/C0"
  "./results/experimental-cycles/C1"
  "./results/experimental-cycles/C2"
  "./results/experimental-cycles/C3"
  "./results/experimental-cycles/C4"
  "./results/experimental-cycles/C5"
  "./results/experimental-cycles/C6"
  "./results/experimental-cycles/C7"
  "./results/experimental-cycles/C8"
  "./results/experimental-cycles/C9"
  "./results/reporting"
)

for root in "${expected_roots[@]}"; do
  test -d "$root" || { echo "Missing expected result root: $root" >&2; exit 1; }
done

echo "Artifact coverage check completed."
```
