param(
    [string]$ProfileConfig,
    [ValidateSet("plan", "capture", "validate")]
    [string]$Action = "validate",
    [string]$Kubeconfig,
    [string]$OutputRoot,
    [string]$RunId,
    [switch]$DryRun,
    [switch]$SkipPrometheusQuery,
    [switch]$WriteLatestAliases
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$runner = Join-Path $scriptDir "validate-mentat.py"

if (-not (Test-Path $runner)) {
    throw "Mentat network observability runner not found: $runner"
}

if ([string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $ProfileConfig = Join-Path $repoRoot "config\network-observability\profiles\NO_MENTAT_C9.json"
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
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
    $argsList += @("--output-root", $OutputRoot)
}
if (-not [string]::IsNullOrWhiteSpace($RunId)) {
    $argsList += @("--run-id", $RunId)
}
if ($DryRun) {
    $argsList += "--dry-run"
}
if ($SkipPrometheusQuery) {
    $argsList += "--skip-prometheus-query"
}
if ($WriteLatestAliases) {
    $argsList += "--write-latest-aliases"
}

Write-Host "==============================================="
Write-Host " Mentat network observability"
Write-Host "==============================================="
Write-Host "Repository : $repoRoot"
Write-Host "Profile    : $ProfileConfig"
Write-Host "Action     : $Action"
Write-Host "Dry run    : $DryRun"
Write-Host ""

& $python.Source @argsList
exit $LASTEXITCODE
