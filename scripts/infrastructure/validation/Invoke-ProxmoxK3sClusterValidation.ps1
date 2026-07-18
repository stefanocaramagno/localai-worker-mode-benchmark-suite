param(
    [string]$ProfileConfig,
    [string]$Kubeconfig,
    [string]$OutputRoot,
    [string]$ValidationId,
    [switch]$AllowMetricsWarning,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path

if ([string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $ProfileConfig = Join-Path $repoRoot "config\provisioning-validation\profiles\PV_C1_PROVIDER_BACKED_BASELINE.json"
}

$pythonScript = Join-Path $scriptDir "validate-proxmox-k3s-cluster.py"
if (-not (Test-Path $pythonScript)) {
    throw "Validation Python script not found: $pythonScript"
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
    "--profile-config", $ProfileConfig
)

if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
    $argsList += @("--output-root", $OutputRoot)
}
if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $argsList += @("--kubeconfig", $Kubeconfig)
}
if (-not [string]::IsNullOrWhiteSpace($ValidationId)) {
    $argsList += @("--validation-id", $ValidationId)
}
if ($AllowMetricsWarning) {
    $argsList += "--allow-metrics-warning"
}
if ($DryRun) {
    $argsList += "--dry-run"
}

Write-Host "==============================================="
Write-Host " proxmox-k3s standalone cluster validation"
Write-Host "==============================================="
Write-Host "Repository : $repoRoot"
Write-Host "Profile    : $ProfileConfig"
Write-Host "Kubeconfig : $Kubeconfig"
Write-Host "Output root: $OutputRoot"
Write-Host "Dry run    : $DryRun"
Write-Host ""

& $pythonCommand.Source @argsList
exit $LASTEXITCODE
