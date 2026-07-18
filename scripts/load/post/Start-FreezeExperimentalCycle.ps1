param(
    [string]$RepoRoot = ".",
    [string]$CycleConfig = "config/experimental-cycles/C1.json",
    [string]$ProfileConfig,
    [string]$FreezeId,
    [string]$OutputRoot,
    [switch]$Force,
    [switch]$DryRun,
    [switch]$SkipCompletionGate,
    [switch]$WriteLatestAliases
)

$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $RepoRoot "scripts/analysis/freeze-experimental-cycle.py"
if (-not (Test-Path $scriptPath)) {
    throw "Freeze script not found: $scriptPath"
}

$arguments = @(
    "-S",
    $scriptPath,
    "--repo-root",
    $RepoRoot,
    "--cycle-config",
    $CycleConfig
)

if (-not [string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $arguments += @("--profile-config", $ProfileConfig)
}

if (-not [string]::IsNullOrWhiteSpace($FreezeId)) {
    $arguments += @("--freeze-id", $FreezeId)
}

if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
    $arguments += @("--output-root", $OutputRoot)
}

if ($Force) {
    $arguments += "--force"
}

if ($DryRun) {
    $arguments += "--dry-run"
}

if ($SkipCompletionGate) {
    $arguments += "--skip-completion-gate"
}

if ($WriteLatestAliases) {
    $arguments += "--write-latest-aliases"
}

python @arguments
$freezeExitCode = $LASTEXITCODE
if ($freezeExitCode -ne 0) {
    exit $freezeExitCode
}
