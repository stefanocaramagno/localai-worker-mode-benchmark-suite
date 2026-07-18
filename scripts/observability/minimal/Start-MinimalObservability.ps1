param(
    [string]$CycleConfig,
    [string]$ProfileConfig,
    [ValidateSet("plan", "capture", "summarize")]
    [string]$Action = "capture",
    [string]$Stage,
    [string]$Kubeconfig,
    [string]$Namespace,
    [string]$MeasurementCsvPrefix,
    [string]$OutputRoot,
    [string]$ObservabilityId,
    [switch]$DryRun,
    [switch]$SkipClusterValidationGate,
    [switch]$SkipApplicationDeploymentGate,
    [switch]$WriteLatestAliases
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
$runner = Join-Path $scriptDir "run-minimal-observability.py"

if (-not (Test-Path $runner)) {
    throw "Minimal observability runner not found: $runner"
}

if ([string]::IsNullOrWhiteSpace($CycleConfig)) {
    $CycleConfig = Join-Path $repoRoot "config\experimental-cycles\C1.json"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) {
    $python = Get-Command python3 -ErrorAction SilentlyContinue
}
if ($null -eq $python) {
    throw "Neither python nor python3 is available in PATH."
}

$argsList = @(
    $runner,
    "--repo-root", $repoRoot,
    "--cycle-config", $CycleConfig,
    "--action", $Action
)

if (-not [string]::IsNullOrWhiteSpace($ProfileConfig)) { $argsList += @("--profile-config", $ProfileConfig) }
if (-not [string]::IsNullOrWhiteSpace($Stage)) { $argsList += @("--stage", $Stage) }
if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) { $argsList += @("--kubeconfig", $Kubeconfig) }
if (-not [string]::IsNullOrWhiteSpace($Namespace)) { $argsList += @("--namespace", $Namespace) }
if (-not [string]::IsNullOrWhiteSpace($MeasurementCsvPrefix)) { $argsList += @("--measurement-csv-prefix", $MeasurementCsvPrefix) }
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) { $argsList += @("--output-root", $OutputRoot) }
if (-not [string]::IsNullOrWhiteSpace($ObservabilityId)) { $argsList += @("--observability-id", $ObservabilityId) }
if ($DryRun) { $argsList += "--dry-run" }
if ($SkipClusterValidationGate) { $argsList += "--skip-cluster-validation-gate" }
if ($SkipApplicationDeploymentGate) { $argsList += "--skip-application-deployment-gate" }
if ($WriteLatestAliases) { $argsList += "--write-latest-aliases" }

& $python.Source @argsList
exit $LASTEXITCODE
