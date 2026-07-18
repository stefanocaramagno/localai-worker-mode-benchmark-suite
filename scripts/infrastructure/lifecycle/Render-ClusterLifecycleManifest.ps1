param(
    [string]$CycleConfig,
    [string]$LifecyclePolicy,
    [ValidateSet("external", "reuse", "ephemeral")]
    [string]$Mode,
    [Nullable[bool]]$DestroyClusterAfterCycle,
    [string]$ProviderConfig,
    [string]$ToolPath = "proxmox-k3s",
    [string]$OutputRoot,
    [string]$RunId,
    [switch]$WriteLatestAliases
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
$pythonScript = Join-Path $scriptDir "render-cluster-lifecycle-manifest.py"
if (-not (Test-Path $pythonScript)) { throw "Cluster lifecycle renderer not found: $pythonScript" }
if ([string]::IsNullOrWhiteSpace($CycleConfig)) { $CycleConfig = Join-Path $repoRoot "config\experimental-cycles\C1.json" }
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $pythonCommand) { $pythonCommand = Get-Command python3 -ErrorAction SilentlyContinue }
if ($null -eq $pythonCommand) { throw "Neither python nor python3 is available in PATH." }
$argsList = @($pythonScript, "--repo-root", $repoRoot, "--cycle-config", $CycleConfig, "--tool-path", $ToolPath)
if (-not [string]::IsNullOrWhiteSpace($LifecyclePolicy)) { $argsList += @("--lifecycle-policy", $LifecyclePolicy) }
if (-not [string]::IsNullOrWhiteSpace($Mode)) { $argsList += @("--mode", $Mode) }
if ($null -ne $DestroyClusterAfterCycle) { $argsList += @("--destroy-cluster-after-cycle", $DestroyClusterAfterCycle.ToString().ToLowerInvariant()) }
if (-not [string]::IsNullOrWhiteSpace($ProviderConfig)) { $argsList += @("--provider-config", $ProviderConfig) }
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) { $argsList += @("--output-root", $OutputRoot) }
if (-not [string]::IsNullOrWhiteSpace($RunId)) { $argsList += @("--run-id", $RunId) }
if ($WriteLatestAliases) { $argsList += "--write-latest-aliases" }
Write-Host "==============================================="
Write-Host " cluster lifecycle manifest renderer"
Write-Host "==============================================="
Write-Host "Repository : $repoRoot"
Write-Host "Cycle      : $CycleConfig"
Write-Host "Tool       : $ToolPath"
Write-Host ""
& $pythonCommand.Source @argsList
exit $LASTEXITCODE
