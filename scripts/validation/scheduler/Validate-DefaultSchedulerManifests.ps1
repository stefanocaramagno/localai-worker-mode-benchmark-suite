param(
    [string]$RepoRoot,
    [string[]]$ScanRoot,
    [string[]]$RenderedManifest,
    [switch]$RenderKustomize,
    [switch]$RequireRender,
    [switch]$Json,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

function Write-Usage {
    Write-Host "Usage:"
    Write-Host "  .\Validate-DefaultSchedulerManifests.ps1 [-RepoRoot <path>] [-ScanRoot <path[]>] [-RenderedManifest <path[]>] [-RenderKustomize] [-RequireRender] [-Json]"
    Write-Host ""
    Write-Host "Validates default-scheduler Kubernetes manifests against hard placement controls."
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
    throw "Python executable not found. Install Python or add it to PATH before running default-scheduler manifest validation."
}

if ($Help) {
    Write-Usage
    exit 0
}

$resolvedRepoRoot = Resolve-RepositoryRoot
$validator = Join-Path $resolvedRepoRoot "scripts\validation\scheduler\validate-default-scheduler-manifests.py"
if (-not (Test-Path -LiteralPath $validator)) {
    throw "Default-scheduler manifest validator not found: $validator"
}

$python = Resolve-PythonCommand
$pythonPrefixArgs = @()
if ($python -eq "py") {
    $pythonPrefixArgs += "-3"
}

$arguments = @(
    $validator,
    "--repo-root", $resolvedRepoRoot
)

foreach ($item in @($ScanRoot)) {
    if (-not [string]::IsNullOrWhiteSpace($item)) {
        $arguments += @("--scan-root", $item)
    }
}

foreach ($item in @($RenderedManifest)) {
    if (-not [string]::IsNullOrWhiteSpace($item)) {
        $arguments += @("--rendered-manifest", $item)
    }
}

if ($RenderKustomize) { $arguments += "--render-kustomize" }
if ($RequireRender) { $arguments += "--require-render" }
if ($Json) { $arguments += "--json" }

& $python @pythonPrefixArgs @arguments
exit $LASTEXITCODE
