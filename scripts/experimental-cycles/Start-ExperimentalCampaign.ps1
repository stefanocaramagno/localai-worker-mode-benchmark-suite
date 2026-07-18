param(
    [string]$CycleConfig,
    [string]$ToolPath = "proxmox-k3s",
    [string]$RunId,
    [string]$BaselineReplicas,
    [string]$BaseUrl,
    [switch]$DryRun,
    [switch]$ContinueOnFailure,
    [switch]$AllowMetricsWarning,
    [switch]$ConfirmDelete,
    [switch]$ForceFreeze,
    [switch]$WriteLatestAliases,
    [switch]$SkipProvisioning,
    [switch]$SkipClusterValidation,
    [switch]$SkipPlacementProfile,
    [switch]$SkipLocalAIDeployment,
    [switch]$SkipSmokeTest,
    [switch]$SkipMinimalObservability,
    [switch]$SkipLatencyInjection,
    [switch]$SkipDefaultSchedulerValidation,
    [switch]$SkipSchedulerCapture,
    [switch]$SkipTelemetryPriming,
    [switch]$SkipClusterLensCapture,
    [switch]$SkipBenchmark,
    [switch]$SkipDiagnosis,
    [switch]$SkipReporting,
    [switch]$SkipCompletionGate,
    [switch]$SkipFreeze,
    [switch]$SkipDelete
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$runner = Join-Path $repoRoot "scripts\experimental-cycles\run-experimental-campaign.py"
if (-not (Test-Path $runner)) { throw "Experimental campaign runner not found: $runner" }
if ([string]::IsNullOrWhiteSpace($CycleConfig)) { $CycleConfig = Join-Path $repoRoot "config\experimental-cycles\C2.json" }
$python = (Get-Command python -ErrorAction SilentlyContinue)
if ($null -eq $python) { $python = (Get-Command python3 -ErrorAction SilentlyContinue) }
if ($null -eq $python) { throw "No Python interpreter found in PATH." }

$argsList = @($runner, "--repo-root", $repoRoot, "--cycle-config", $CycleConfig, "--tool-path", $ToolPath)
if (-not [string]::IsNullOrWhiteSpace($RunId)) { $argsList += @("--run-id", $RunId) }
if (-not [string]::IsNullOrWhiteSpace($BaselineReplicas)) { $argsList += @("--baseline-replicas", $BaselineReplicas) }
if (-not [string]::IsNullOrWhiteSpace($BaseUrl)) { $argsList += @("--base-url", $BaseUrl) }
if ($DryRun) { $argsList += "--dry-run" }
if ($ContinueOnFailure) { $argsList += "--continue-on-failure" }
if ($AllowMetricsWarning) { $argsList += "--allow-metrics-warning" }
if ($ConfirmDelete) { $argsList += "--confirm-delete" }
if ($ForceFreeze) { $argsList += "--force-freeze" }
if ($WriteLatestAliases) { $argsList += "--write-latest-aliases" }
if ($SkipProvisioning) { $argsList += "--skip-provisioning" }
if ($SkipClusterValidation) { $argsList += "--skip-cluster-validation" }
if ($SkipPlacementProfile) { $argsList += "--skip-placement-profile" }
if ($SkipLocalAIDeployment) { $argsList += "--skip-localai-deployment" }
if ($SkipSmokeTest) { $argsList += "--skip-smoke-test" }
if ($SkipMinimalObservability) { $argsList += "--skip-minimal-observability" }
if ($SkipLatencyInjection) { $argsList += "--skip-latency-injection" }
if ($SkipDefaultSchedulerValidation) { $argsList += "--skip-default-scheduler-validation" }
if ($SkipSchedulerCapture) { $argsList += "--skip-scheduler-capture" }
if ($SkipTelemetryPriming) { $argsList += "--skip-telemetry-priming" }
if ($SkipClusterLensCapture) { $argsList += "--skip-cluster-lens-capture" }
if ($SkipBenchmark) { $argsList += "--skip-benchmark" }
if ($SkipDiagnosis) { $argsList += "--skip-diagnosis" }
if ($SkipReporting) { $argsList += "--skip-reporting" }
if ($SkipCompletionGate) { $argsList += "--skip-completion-gate" }
if ($SkipFreeze) { $argsList += "--skip-freeze" }
if ($SkipDelete) { $argsList += "--skip-delete" }

& $python.Source @argsList
exit $LASTEXITCODE
