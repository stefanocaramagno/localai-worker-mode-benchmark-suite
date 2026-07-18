[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$ScenarioConfig,
    [string]$Kubeconfig,
    [string]$LocustFile,
    [string]$OutputRoot,
    [int]$BasePort = 0,
    [int]$RemotePort = 0,
    [string]$TenantPorts,
    [string]$TenantBaseUrls,
    [string]$RunId,
    [string]$LocustCommand,
    [int]$ReadinessTimeoutSeconds = 0,
    [switch]$SkipPortForward,
    [switch]$ReuseExistingPortForward,
    [switch]$DryRun,
    [switch]$WriteLatestAliases,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AdditionalArguments
)

$ErrorActionPreference = 'Stop'

function Resolve-RepositoryRoot {
    param([string]$Override)

    if (-not [string]::IsNullOrWhiteSpace($Override)) {
        return (Resolve-Path -Path $Override).Path
    }

    $scriptDirectory = Split-Path -Parent $PSCommandPath
    return (Resolve-Path -Path (Join-Path $scriptDirectory '..\..\..')).Path
}

function Resolve-PythonCommand {
    foreach ($candidate in @('python', 'python3')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            return $command.Source
        }
    }

    throw 'Unable to find python or python3 in PATH.'
}

$resolvedRepoRoot = Resolve-RepositoryRoot -Override $RepoRoot
$pythonCommand = Resolve-PythonCommand
$runner = Join-Path $resolvedRepoRoot 'scripts\load\multi-tenant\run-multi-tenant-locust.py'

$arguments = @($runner, '--repo-root', $resolvedRepoRoot)

if (-not [string]::IsNullOrWhiteSpace($ScenarioConfig)) { $arguments += @('--scenario-config', $ScenarioConfig) }
if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) { $arguments += @('--kubeconfig', $Kubeconfig) }
if (-not [string]::IsNullOrWhiteSpace($LocustFile)) { $arguments += @('--locust-file', $LocustFile) }
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) { $arguments += @('--output-root', $OutputRoot) }
if ($BasePort -gt 0) { $arguments += @('--base-port', [string]$BasePort) }
if ($RemotePort -gt 0) { $arguments += @('--remote-port', [string]$RemotePort) }
if (-not [string]::IsNullOrWhiteSpace($TenantPorts)) { $arguments += @('--tenant-ports', $TenantPorts) }
if (-not [string]::IsNullOrWhiteSpace($TenantBaseUrls)) { $arguments += @('--tenant-base-urls', $TenantBaseUrls) }
if (-not [string]::IsNullOrWhiteSpace($RunId)) { $arguments += @('--run-id', $RunId) }
if (-not [string]::IsNullOrWhiteSpace($LocustCommand)) { $arguments += @('--locust-command', $LocustCommand) }
if ($ReadinessTimeoutSeconds -gt 0) { $arguments += @('--readiness-timeout-seconds', [string]$ReadinessTimeoutSeconds) }
if ($SkipPortForward) { $arguments += '--skip-port-forward' }
if ($ReuseExistingPortForward) { $arguments += '--reuse-existing-port-forward' }
if ($DryRun) { $arguments += '--dry-run' }
if ($WriteLatestAliases) { $arguments += '--write-latest-aliases' }
if ($AdditionalArguments) { $arguments += $AdditionalArguments }

& $pythonCommand @arguments
exit $LASTEXITCODE
