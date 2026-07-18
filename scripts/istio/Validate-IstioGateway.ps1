param(
  [string]$RepoRoot = ".",
  [string]$ProfileConfig = "config/istio-gateway/profiles/IG_LOCALAI_GATEWAY_ROUTED_C9.json",
  [string]$ScenarioConfig = "",
  [string]$Kubeconfig = "",
  [string]$OutputRoot = "",
  [switch]$DryRun,
  [switch]$SkipRuntimeChecks,
  [switch]$WriteLatestAliases
)

$ErrorActionPreference = "Stop"

$ScriptPath = Join-Path $PSScriptRoot "validate-istio-gateway.py"
$ArgsList = @(
  $ScriptPath,
  "--repo-root", $RepoRoot,
  "--profile-config", $ProfileConfig
)

if ($ScenarioConfig) { $ArgsList += @("--scenario-config", $ScenarioConfig) }
if ($Kubeconfig) { $ArgsList += @("--kubeconfig", $Kubeconfig) }
if ($OutputRoot) { $ArgsList += @("--output-root", $OutputRoot) }
if ($DryRun) { $ArgsList += "--dry-run" }
if ($SkipRuntimeChecks) { $ArgsList += "--skip-runtime-checks" }
if ($WriteLatestAliases) { $ArgsList += "--write-latest-aliases" }

python @ArgsList
exit $LASTEXITCODE
