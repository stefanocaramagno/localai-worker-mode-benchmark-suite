param(
    [string]$ProfileConfig,
    [string]$ScenarioConfig,
    [ValidateSet("plan", "apply", "capture", "validate")]
    [string]$Action = "apply",
    [string]$Kubeconfig,
    [string]$OutputRoot,
    [string]$RunId,
    [switch]$DryRun,
    [switch]$SkipPrometheusServiceCheck,
    [switch]$SkipRolloutWait,
    [switch]$WriteLatestAliases
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
$runner = Join-Path $scriptDir "run-mon-agent.py"

if (-not (Test-Path $runner)) {
    throw "mon-agent runner not found: $runner"
}

if ([string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $ProfileConfig = Join-Path $repoRoot "config\mon-agent\profiles\MA_RESOURCE_AWARE.json"
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
    "--profile-config", $ProfileConfig,
    "--action", $Action
)

if (-not [string]::IsNullOrWhiteSpace($ScenarioConfig)) {
    $argsList += @("--scenario-config", $ScenarioConfig)
}
if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $argsList += @("--kubeconfig", $Kubeconfig)
}
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
    $argsList += @("--output-root", $OutputRoot)
}
if (-not [string]::IsNullOrWhiteSpace($RunId)) {
    $argsList += @("--run-id", $RunId)
}
if ($DryRun) {
    $argsList += "--dry-run"
}
if ($SkipPrometheusServiceCheck) {
    $argsList += "--skip-prometheus-service-check"
}
if ($SkipRolloutWait) {
    $argsList += "--skip-rollout-wait"
}
if ($WriteLatestAliases) {
    $argsList += "--write-latest-aliases"
}

Write-Host "==============================================="
Write-Host " mon-agent integration"
Write-Host "==============================================="
Write-Host "Repository : $repoRoot"
Write-Host "Profile    : $ProfileConfig"
Write-Host "Scenario   : $ScenarioConfig"
Write-Host "Action     : $Action"
Write-Host "Dry run    : $DryRun"
Write-Host ""

& $python.Source @argsList
exit $LASTEXITCODE
