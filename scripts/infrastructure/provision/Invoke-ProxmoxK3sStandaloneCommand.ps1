param(
    [ValidateSet("create", "delete", "kubeconfig", "template-create", "template-delete")]
    [string]$Command = "create",
    [string]$ConfigPath,
    [string]$ToolPath = "proxmox-k3s",
    [string]$OutputRoot,
    [string]$RunId,
    [string]$CycleId = "C1",
    [ValidateSet("reuse", "ephemeral")]
    [string]$ClusterLifecycleMode = "reuse",
    [switch]$DestroyClusterAfterCycle,
    [switch]$DryRun,
    [switch]$ConfirmDelete
)
$script:ArtifactPortabilitySearchRoot = Split-Path -Parent $PSCommandPath
while (-not [string]::IsNullOrWhiteSpace($script:ArtifactPortabilitySearchRoot)) {
    $script:ArtifactPortabilityCandidate = Join-Path $script:ArtifactPortabilitySearchRoot "scripts\common\ArtifactPortability.ps1"
    if (Test-Path $script:ArtifactPortabilityCandidate) {
        . $script:ArtifactPortabilityCandidate
        break
    }
    $script:ArtifactPortabilityParent = Split-Path -Parent $script:ArtifactPortabilitySearchRoot
    if ($script:ArtifactPortabilityParent -eq $script:ArtifactPortabilitySearchRoot) { break }
    $script:ArtifactPortabilitySearchRoot = $script:ArtifactPortabilityParent
}
Remove-Variable -Name ArtifactPortabilitySearchRoot -Scope Script -ErrorAction SilentlyContinue
Remove-Variable -Name ArtifactPortabilityCandidate -Scope Script -ErrorAction SilentlyContinue
Remove-Variable -Name ArtifactPortabilityParent -Scope Script -ErrorAction SilentlyContinue

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
if ([string]::IsNullOrWhiteSpace($ConfigPath)) { $ConfigPath = Join-Path $repoRoot "config\infrastructure\providers\proxmox-k3s\local\cluster.c1-1cp-2w-8c16g.local.yaml" }
if ([string]::IsNullOrWhiteSpace($OutputRoot)) { $OutputRoot = Join-Path $repoRoot "results\experimental-cycles\$CycleId\infrastructure\provisioning" }
if ([string]::IsNullOrWhiteSpace($RunId)) { $timestampUtc = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ'); $RunId = "proxmox-k3s_$($Command.Replace('-', '_'))_$timestampUtc" }
if (-not (Test-Path $ConfigPath)) { throw "The proxmox-k3s configuration file does not exist: $ConfigPath" }
if ($Command -eq "delete" -and -not $DryRun -and -not $ConfirmDelete) { throw "The delete command is destructive. Re-run with -ConfirmDelete to explicitly confirm cluster deletion through the benchmark-suite wrapper." }
$resolvedOutputRoot = New-Item -ItemType Directory -Path $OutputRoot -Force
$logPath = Join-Path $resolvedOutputRoot.FullName "$RunId.log"
$manifestPath = Join-Path $resolvedOutputRoot.FullName "$RunId.command-manifest.json"
$commandArgs = @()
switch ($Command) {
  "create" { $commandArgs = @("cluster", "create", "-c", $ConfigPath) }
  "delete" { $commandArgs = @("cluster", "delete", "-c", $ConfigPath) }
  "kubeconfig" { $commandArgs = @("cluster", "kubeconfig", "-c", $ConfigPath) }
  "template-create" { $commandArgs = @("template", "create", "-c", $ConfigPath) }
  "template-delete" { $commandArgs = @("template", "delete", "-c", $ConfigPath) }
}
Write-Host "==============================================="
Write-Host " proxmox-k3s standalone command launcher"
Write-Host "==============================================="
Write-Host "Repository : $repoRoot"
Write-Host "Tool       : $ToolPath"
Write-Host "Command    : $Command"
Write-Host "Config     : $ConfigPath"
Write-Host "Run ID     : $RunId"
Write-Host "Log file   : $logPath"
Write-Host "Manifest   : $manifestPath"
Write-Host "Cycle      : $CycleId"
Write-Host "Lifecycle  : $ClusterLifecycleMode"
Write-Host "Destroy after cycle: $DestroyClusterAfterCycle"
Write-Host "Dry run    : $DryRun"
Write-Host "Confirm delete: $ConfirmDelete"
Write-Host ""
$printableCommand = "$ToolPath " + ($commandArgs -join " ")
$startedAt = (Get-Date).ToUniversalTime().ToString('o')
$stdinProvided = ($Command -eq "delete" -and $ConfirmDelete)
$manifest = [ordered]@{ schemaVersion = "proxmox-k3s-command-manifest/v1"; manifestId = $RunId; cycleId = $CycleId; command = $Command; clusterLifecycleMode = $ClusterLifecycleMode; destroyClusterAfterCycle = [bool]$DestroyClusterAfterCycle; toolPath = $ToolPath; configPath = $ConfigPath; printableCommand = $printableCommand; logPath = $logPath; startedAtUtc = $startedAt; dryRun = [bool]$DryRun; confirmDelete = [bool]$ConfirmDelete; stdinProvided = [bool]$stdinProvided; status = "started" }
if ($DryRun) {
  $payload = @("Dry-run only. Command not executed.", "Command: $printableCommand", "GeneratedAtUtc: $startedAt") -join [Environment]::NewLine
  Write-PortableArtifactText -Path $logPath -Text $payload
  $manifest.status = "dry_run"; $manifest.finishedAtUtc = (Get-Date).ToUniversalTime().ToString('o'); $manifest.exitCode = 0
  Write-PortableArtifactJson -Path $manifestPath -Payload $manifest -Depth 8
  Write-Host $payload
  exit 0
}
$header = @("Command: $printableCommand", "StartedAtUtc: $startedAt", "CycleId: $CycleId", "ClusterLifecycleMode: $ClusterLifecycleMode", "DestroyClusterAfterCycle: $([bool]$DestroyClusterAfterCycle)", "StdinProvided: $stdinProvided", "") -join [Environment]::NewLine
Write-PortableArtifactText -Path $logPath -Text $header
if ($stdinProvided) {
  "y" | & $ToolPath @commandArgs 2>&1 | Tee-Object -FilePath $logPath -Append
} else {
  & $ToolPath @commandArgs 2>&1 | Tee-Object -FilePath $logPath -Append
}
$exitCode = $LASTEXITCODE
$finishedAt = (Get-Date).ToUniversalTime().ToString('o')
$footer = @("", "FinishedAtUtc: $finishedAt", "ExitCode: $exitCode") -join [Environment]::NewLine
Add-Content -Path $logPath -Value $footer -Encoding UTF8
$manifest.status = if ($exitCode -eq 0) { "completed" } else { "failed" }
$manifest.finishedAtUtc = $finishedAt; $manifest.exitCode = $exitCode
Write-PortableArtifactText -Path $logPath -Text (Get-Content -Path $logPath -Raw)
Write-PortableArtifactJson -Path $manifestPath -Payload $manifest -Depth 8
if ($exitCode -ne 0) { throw "proxmox-k3s command failed with exit code $exitCode. See log: $logPath" }
