param(
    [string]$CycleConfig,
    [string]$ClusterValidationProfile,
    [string]$ValidationProfile,
    [string]$Kubeconfig,
    [string]$OutputRoot,
    [string]$ValidationId,
    [switch]$DryRun,
    [switch]$SkipPreValidationGate,
    [switch]$AllowMetricsWarning,
    [switch]$WriteLatestAliases
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
$pythonScript = Join-Path $scriptDir "run-provider-backed-cluster-validation.py"

if (-not (Test-Path $pythonScript)) {
    throw "Provider-backed cluster validation runner not found: $pythonScript"
}

if ([string]::IsNullOrWhiteSpace($CycleConfig)) {
    $CycleConfig = Join-Path $repoRoot "config\experimental-cycles\C1.json"
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $pythonCommand) {
    $pythonCommand = Get-Command python3 -ErrorAction SilentlyContinue
}
if ($null -eq $pythonCommand) {
    throw "Neither python nor python3 is available in PATH."
}

$argsList = @(
    $pythonScript,
    "--repo-root", $repoRoot,
    "--cycle-config", $CycleConfig
)

if (-not [string]::IsNullOrWhiteSpace($ClusterValidationProfile)) {
    $argsList += @("--cluster-validation-profile", $ClusterValidationProfile)
}
if (-not [string]::IsNullOrWhiteSpace($ValidationProfile)) {
    $argsList += @("--validation-profile", $ValidationProfile)
}
if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $argsList += @("--kubeconfig", $Kubeconfig)
}
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
    $argsList += @("--output-root", $OutputRoot)
}
if (-not [string]::IsNullOrWhiteSpace($ValidationId)) {
    $argsList += @("--validation-id", $ValidationId)
}
if ($DryRun) {
    $argsList += "--dry-run"
}
if ($SkipPreValidationGate) {
    $argsList += "--skip-prevalidation-gate"
}
if ($AllowMetricsWarning) {
    $argsList += "--allow-metrics-warning"
}
if ($WriteLatestAliases) {
    $argsList += "--write-latest-aliases"
}

Write-Host "==============================================="
Write-Host " provider-backed cluster validation"
Write-Host "==============================================="
Write-Host "Repository : $repoRoot"
Write-Host "Cycle      : $CycleConfig"
Write-Host "Dry run    : $DryRun"
Write-Host ""

& $pythonCommand.Source @argsList
exit $LASTEXITCODE
