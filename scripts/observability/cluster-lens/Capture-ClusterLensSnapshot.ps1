param(
    [string]$RepoRoot,
    [string]$ProfileConfig,
    [string]$ScenarioConfig,
    [string]$Kubeconfig,
    [string]$Kubectl,
    [string]$OutputDir,
    [string]$SnapshotUrl,
    [switch]$UsePortForward,
    [switch]$NoPortForward,
    [switch]$DryRun,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

function Write-Usage {
    Write-Host "Usage:"
    Write-Host "  .\Capture-ClusterLensSnapshot.ps1 [-RepoRoot <path>] [-ProfileConfig <path>] [-ScenarioConfig <path>] [-Kubeconfig <path>] [-Kubectl <name-or-path>] [-OutputDir <path>] [-SnapshotUrl <url>] [-UsePortForward] [-NoPortForward] [-DryRun]"
    Write-Host ""
    Write-Host "Captures cluster-lens topology snapshots and Kubernetes LocalAI placement evidence."
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
    throw "Python executable not found. Install Python or add it to PATH before running cluster-lens capture."
}

if ($Help) {
    Write-Usage
    exit 0
}

$resolvedRepoRoot = Resolve-RepositoryRoot
$runner = Join-Path $resolvedRepoRoot "scripts\observability\cluster-lens\capture-cluster-lens-snapshot.py"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "cluster-lens capture runner not found: $runner"
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

if (-not [string]::IsNullOrWhiteSpace($ProfileConfig)) { $arguments += @("--profile-config", $ProfileConfig) }
if (-not [string]::IsNullOrWhiteSpace($ScenarioConfig)) { $arguments += @("--scenario-config", $ScenarioConfig) }
if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) { $arguments += @("--kubeconfig", $Kubeconfig) }
if (-not [string]::IsNullOrWhiteSpace($Kubectl)) { $arguments += @("--kubectl", $Kubectl) }
if (-not [string]::IsNullOrWhiteSpace($OutputDir)) { $arguments += @("--output-dir", $OutputDir) }
if (-not [string]::IsNullOrWhiteSpace($SnapshotUrl)) { $arguments += @("--snapshot-url", $SnapshotUrl) }
if ($UsePortForward) { $arguments += "--use-port-forward" }
if ($NoPortForward) { $arguments += "--no-port-forward" }
if ($DryRun) { $arguments += "--dry-run" }

& $python @pythonPrefixArgs @arguments
exit $LASTEXITCODE
