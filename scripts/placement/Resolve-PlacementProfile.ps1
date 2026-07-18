param(
    [string]$CycleConfig,
    [string]$ApplicationDeploymentProfile,
    [string]$PlacementProfileId,
    [string]$PlacementProfilePath,
    [string]$OutputRoot,
    [string]$ResolutionId,
    [switch]$WriteLatestAliases
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$pythonScript = Join-Path $scriptDir "resolve-placement-profile.py"

if (-not (Test-Path $pythonScript)) {
    throw "Placement profile resolver not found: $pythonScript"
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
    "--repo-root", $repoRoot
)

if (-not [string]::IsNullOrWhiteSpace($CycleConfig)) {
    $argsList += @("--cycle-config", $CycleConfig)
}
if (-not [string]::IsNullOrWhiteSpace($ApplicationDeploymentProfile)) {
    $argsList += @("--application-deployment-profile", $ApplicationDeploymentProfile)
}
if (-not [string]::IsNullOrWhiteSpace($PlacementProfileId)) {
    $argsList += @("--placement-profile-id", $PlacementProfileId)
}
if (-not [string]::IsNullOrWhiteSpace($PlacementProfilePath)) {
    $argsList += @("--placement-profile-path", $PlacementProfilePath)
}
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
    $argsList += @("--output-root", $OutputRoot)
}
if (-not [string]::IsNullOrWhiteSpace($ResolutionId)) {
    $argsList += @("--resolution-id", $ResolutionId)
}
if ($WriteLatestAliases) {
    $argsList += "--write-latest-aliases"
}

Write-Host "==============================================="
Write-Host " placement profile resolver"
Write-Host "==============================================="
Write-Host "Repository : $repoRoot"
Write-Host ""

& $pythonCommand.Source @argsList
exit $LASTEXITCODE
