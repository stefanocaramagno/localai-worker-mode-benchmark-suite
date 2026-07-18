param(
    [string]$CycleConfig,
    [string]$DeploymentProfile,
    [ValidateSet("plan", "deploy", "smoke")]
    [string]$Action = "deploy",
    [string]$Kubeconfig,
    [string]$OutputRoot,
    [string]$DeploymentId,
    [switch]$DryRun,
    [switch]$SkipClusterValidationGate,
    [switch]$SkipSmokeTest,
    [string]$BaseUrl,
    [switch]$NoPortForward,
    [switch]$WriteLatestAliases
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
$pythonScript = Join-Path $scriptDir "run-provider-backed-localai-deployment.py"

if (-not (Test-Path $pythonScript)) {
    throw "Provider-backed LocalAI deployment runner not found: $pythonScript"
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
    "--action", $Action
)

if (-not [string]::IsNullOrWhiteSpace($DeploymentProfile)) {
    $argsList += @("--deployment-profile", $DeploymentProfile)
}
if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $argsList += @("--kubeconfig", $Kubeconfig)
}
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
    $argsList += @("--output-root", $OutputRoot)
}
if (-not [string]::IsNullOrWhiteSpace($DeploymentId)) {
    $argsList += @("--deployment-id", $DeploymentId)
}
if ($DryRun) {
    $argsList += "--dry-run"
}
if ($SkipClusterValidationGate) {
    $argsList += "--skip-cluster-validation-gate"
}
if ($SkipSmokeTest) {
    $argsList += "--skip-smoke-test"
}
if (-not [string]::IsNullOrWhiteSpace($BaseUrl)) {
    $argsList += @("--base-url", $BaseUrl)
}
if ($NoPortForward) {
    $argsList += "--no-port-forward"
}
if ($WriteLatestAliases) {
    $argsList += "--write-latest-aliases"
}

Write-Host "==============================================="
Write-Host " provider-backed LocalAI deployment"
Write-Host "==============================================="
Write-Host "Repository : $repoRoot"
Write-Host "Cycle      : $CycleConfig"
Write-Host "Action     : $Action"
Write-Host "Dry run    : $DryRun"
Write-Host ""

& $pythonCommand.Source @argsList
exit $LASTEXITCODE
