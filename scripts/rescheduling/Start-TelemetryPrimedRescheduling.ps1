param(
    [string]$ProfileConfig,
    [string]$ScenarioConfig,
    [ValidateSet("plan", "capture", "execute", "restart", "validate")]
    [string]$Action = "execute",
    [string]$Kubeconfig,
    [string]$OutputRoot,
    [string]$RunId,
    [switch]$DryRun,
    [switch]$SkipTelemetryPriming,
    [switch]$SkipAnnotationGate,
    [switch]$SkipPostRestartStabilization,
    [switch]$WriteLatestAliases
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$runner = Join-Path $scriptDir "run-telemetry-primed-rescheduling.py"

if (-not (Test-Path $runner)) {
    throw "Telemetry-primed rescheduling runner not found: $runner"
}

if ([string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $ProfileConfig = Join-Path $repoRoot "config\rescheduling\profiles\RS_C8_RESOURCE_AWARE_TELEMETRY_PRIMED_REDEPLOYMENT.json"
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
if ($SkipTelemetryPriming) {
    $argsList += "--skip-telemetry-priming"
}
if ($SkipAnnotationGate) {
    $argsList += "--skip-annotation-gate"
}
if ($SkipPostRestartStabilization) {
    $argsList += "--skip-post-restart-stabilization"
}
if ($WriteLatestAliases) {
    $argsList += "--write-latest-aliases"
}

Write-Host "==============================================="
Write-Host " telemetry-primed rescheduling"
Write-Host "==============================================="
Write-Host "Repository : $repoRoot"
Write-Host "Profile    : $ProfileConfig"
Write-Host "Scenario   : $ScenarioConfig"
Write-Host "Action     : $Action"
Write-Host "Dry run    : $DryRun"
Write-Host ""

& $python.Source @argsList
exit $LASTEXITCODE
