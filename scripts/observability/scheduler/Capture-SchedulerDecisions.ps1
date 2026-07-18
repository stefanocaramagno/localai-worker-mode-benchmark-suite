param(
    [string]$RepoRoot,
    [string]$ScenarioConfig,
    [string]$Kubeconfig,
    [string]$Kubectl,
    [string]$OutputDir,
    [string]$OutputName,
    [AllowEmptyString()]
    [string]$Selector,
    [switch]$DisableFallbackAppFilter,
    [switch]$DryRun,
    [switch]$WriteTextSummary,
    [switch]$WriteLatestAliases,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

function Write-Usage {
    Write-Host "Usage:"
    Write-Host "  .\Capture-SchedulerDecisions.ps1 [-RepoRoot <path>] [-ScenarioConfig <path>] [-Kubeconfig <path>] [-Kubectl <name-or-path>] [-OutputDir <path>] [-OutputName <name>] [-Selector <selector>] [-DisableFallbackAppFilter] [-DryRun] [-WriteTextSummary] [-WriteLatestAliases]"
    Write-Host ""
    Write-Host "Captures Kubernetes default-scheduler placement evidence for LocalAI tenant workloads."
}

function Resolve-RepositoryRoot {
    if (-not [string]::IsNullOrWhiteSpace($RepoRoot)) {
        return (Resolve-Path -LiteralPath $RepoRoot).Path
    }

    $scriptPath = $PSScriptRoot
    if (-not $scriptPath) {
        $scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    return (Resolve-Path (Join-Path $scriptPath "..\..\..")).Path
}

function Resolve-PythonCommand {
    foreach ($candidate in @("python", "py", "python3")) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            return $candidate
        }
    }
    throw "Python executable not found. Install Python or add it to PATH before running scheduler decision capture."
}

if ($Help) {
    Write-Usage
    exit 0
}

$resolvedRepoRoot = Resolve-RepositoryRoot
$runner = Join-Path $resolvedRepoRoot "scripts\observability\scheduler\capture-scheduler-decisions.py"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Scheduler decision capture runner not found: $runner"
}

$python = Resolve-PythonCommand
$pythonPrefixArgs = @()
if ($python -eq "py") {
    $pythonPrefixArgs += "-3"
}

$arguments = @(
    $runner,
    "--repo-root", $resolvedRepoRoot
)

if (-not [string]::IsNullOrWhiteSpace($ScenarioConfig)) { $arguments += @("--scenario-config", $ScenarioConfig) }
if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) { $arguments += @("--kubeconfig", $Kubeconfig) }
if (-not [string]::IsNullOrWhiteSpace($Kubectl)) { $arguments += @("--kubectl", $Kubectl) }
if (-not [string]::IsNullOrWhiteSpace($OutputDir)) { $arguments += @("--output-dir", $OutputDir) }
if (-not [string]::IsNullOrWhiteSpace($OutputName)) { $arguments += @("--output-name", $OutputName) }
if ($PSBoundParameters.ContainsKey("Selector")) { $arguments += @("--selector", $Selector) }
if ($DisableFallbackAppFilter) { $arguments += "--disable-fallback-app-filter" }
if ($DryRun) { $arguments += "--dry-run" }
if ($WriteTextSummary) { $arguments += "--write-text-summary" }
if ($WriteLatestAliases) { $arguments += "--write-latest-aliases" }

& $python @pythonPrefixArgs @arguments
exit $LASTEXITCODE
