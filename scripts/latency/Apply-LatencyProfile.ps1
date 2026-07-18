param(
  [string]$RepoRoot = ".",
  [Parameter(Mandatory=$true)][string]$CycleConfig,
  [Parameter(Mandatory=$true)][string]$ProfileConfig,
  [Parameter(Mandatory=$true)][string]$Kubeconfig,
  [Parameter(Mandatory=$true)][string]$OutputRoot,
  [string]$InjectionId = "",
  [ValidateSet("apply", "reset", "inspect")][string]$Action = "apply",
  [switch]$DryRun,
  [switch]$WriteLatestAliases
)

$ErrorActionPreference = "Stop"
$scriptPath = Join-Path $PSScriptRoot "apply-latency-profile.py"
$arguments = @(
  $scriptPath,
  "--repo-root", $RepoRoot,
  "--cycle-config", $CycleConfig,
  "--profile-config", $ProfileConfig,
  "--kubeconfig", $Kubeconfig,
  "--output-root", $OutputRoot,
  "--action", $Action
)
if ($InjectionId -ne "") { $arguments += @("--injection-id", $InjectionId) }
if ($DryRun) { $arguments += "--dry-run" }
if ($WriteLatestAliases) { $arguments += "--write-latest-aliases" }

python @arguments
exit $LASTEXITCODE
