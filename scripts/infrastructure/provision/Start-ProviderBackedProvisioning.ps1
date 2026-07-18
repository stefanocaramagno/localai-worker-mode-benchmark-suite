param(
    [string]$CycleConfig,
    [string]$ProvisioningProfile,
    [ValidateSet("plan", "provision", "kubeconfig", "destroy")]
    [string]$Action = "provision",
    [string]$ToolPath = "proxmox-k3s",
    [string]$ProviderConfig,
    [ValidateSet("reuse", "ephemeral", "external")]
    [string]$ClusterLifecycleMode,
    [Nullable[bool]]$DestroyClusterAfterCycle,
    [switch]$DryRun,
    [switch]$ConfirmDelete,
    [string]$RunId,
    [string]$OutputRoot,
    [switch]$WriteLatestAliases
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
$pythonScript = Join-Path $scriptDir "run-provider-backed-provisioning.py"

if (-not (Test-Path $pythonScript)) {
    throw "Provider-backed provisioning runner not found: $pythonScript"
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
    "--cycle-config", $CycleConfig,
    "--action", $Action,
    "--tool-path", $ToolPath
)

if (-not [string]::IsNullOrWhiteSpace($ProvisioningProfile)) {
    $argsList += @("--provisioning-profile", $ProvisioningProfile)
}
if (-not [string]::IsNullOrWhiteSpace($ProviderConfig)) {
    $argsList += @("--provider-config", $ProviderConfig)
}
if (-not [string]::IsNullOrWhiteSpace($ClusterLifecycleMode)) {
    $argsList += @("--cluster-lifecycle-mode", $ClusterLifecycleMode)
}
if ($null -ne $DestroyClusterAfterCycle) {
    $argsList += @("--destroy-cluster-after-cycle", $DestroyClusterAfterCycle.ToString().ToLowerInvariant())
}
if ($DryRun) {
    $argsList += "--dry-run"
}
if ($ConfirmDelete) {
    $argsList += "--confirm-delete"
}
if (-not [string]::IsNullOrWhiteSpace($RunId)) {
    $argsList += @("--run-id", $RunId)
}
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
    $argsList += @("--output-root", $OutputRoot)
}
if ($WriteLatestAliases) {
    $argsList += "--write-latest-aliases"
}

Write-Host "==============================================="
Write-Host " provider-backed provisioning integration"
Write-Host "==============================================="
Write-Host "Repository : $repoRoot"
Write-Host "Cycle      : $CycleConfig"
Write-Host "Action     : $Action"
Write-Host "Tool       : $ToolPath"
Write-Host "Dry run    : $DryRun"
Write-Host ""

& $pythonCommand.Source @argsList
exit $LASTEXITCODE
