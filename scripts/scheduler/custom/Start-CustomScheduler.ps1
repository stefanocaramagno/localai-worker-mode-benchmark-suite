param(
    [string]$ProfileConfig,
    [ValidateSet("plan", "install", "apply", "capture", "validate", "uninstall")]
    [string]$Action = "install",
    [string]$Kubeconfig,
    [string]$SchedulerPluginsRoot,
    [string]$ChartPath,
    [string]$OutputRoot,
    [string]$RunId,
    [switch]$DryRun,
    [switch]$SkipValidation,
    [switch]$SkipTestWorkload,
    [switch]$KeepTestWorkload,
    [switch]$WriteLatestAliases
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
$runner = Join-Path $scriptDir "run-custom-scheduler.py"

if (-not (Test-Path $runner)) {
    throw "Custom scheduler runner not found: $runner"
}

if ([string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $ProfileConfig = Join-Path $repoRoot "config\scheduler\profiles\CS_C8_LOADAWARE_SECOND_SCHEDULER.json"
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

if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $argsList += @("--kubeconfig", $Kubeconfig)
}
if (-not [string]::IsNullOrWhiteSpace($SchedulerPluginsRoot)) {
    $argsList += @("--scheduler-plugins-root", $SchedulerPluginsRoot)
}
if (-not [string]::IsNullOrWhiteSpace($ChartPath)) {
    $argsList += @("--chart-path", $ChartPath)
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
if ($SkipValidation) {
    $argsList += "--skip-validation"
}
if ($SkipTestWorkload) {
    $argsList += "--skip-test-workload"
}
if ($KeepTestWorkload) {
    $argsList += "--keep-test-workload"
}
if ($WriteLatestAliases) {
    $argsList += "--write-latest-aliases"
}

Write-Host "==============================================="
Write-Host " custom scheduler integration"
Write-Host "==============================================="
Write-Host "Repository : $repoRoot"
Write-Host "Profile    : $ProfileConfig"
Write-Host "Action     : $Action"
Write-Host "Dry run    : $DryRun"
Write-Host ""

& $python.Source @argsList
exit $LASTEXITCODE
