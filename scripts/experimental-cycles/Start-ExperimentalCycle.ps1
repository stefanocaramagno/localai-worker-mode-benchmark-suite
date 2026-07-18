param(
    [string]$CycleConfig,
    [ValidateSet("provider-backed-cycle", "provisioning", "cluster-validation", "localai-deployment", "placement-profile", "minimal-observability", "reporting", "completion-gate", "freeze")]
    [string]$ExecutionScope = "provisioning",

    [ValidateSet("plan", "provision", "kubeconfig", "destroy")]
    [string]$ProvisioningAction = "provision",
    [string]$ToolPath = "proxmox-k3s",
    [string]$ProviderConfig,
    [switch]$ConfirmDelete,

    [string]$ClusterValidationProfile,
    [string]$ValidationProfile,
    [switch]$SkipPreValidationGate,
    [switch]$AllowMetricsWarning,

    [string]$DeploymentProfile,
    [ValidateSet("plan", "deploy", "smoke")]
    [string]$DeploymentAction = "deploy",
    [switch]$SkipClusterValidationGate,
    [switch]$SkipSmokeTest,
    [string]$BaseUrl,
    [string]$BenchmarkConfig,
    [switch]$NoPortForward,

    [string]$Kubeconfig,
    [switch]$DryRun,
    [string]$RunId,
    [string]$OutputRoot,
    [string]$PlacementProfileId,
    [string]$PlacementProfilePath,

    [string]$MinimalObservabilityProfile,
    [ValidateSet("plan", "capture", "summarize")]
    [string]$MinimalObservabilityAction = "capture",
    [string]$ObservabilityStage,
    [string]$MeasurementCsvPrefix,
    [switch]$SkipApplicationDeploymentGate,

    [string]$ReportingProfile,
    [string]$ReportingId,
    [switch]$Archive,
    [switch]$ArchiveCurrent,
    [switch]$ForceArchive,
    [switch]$SkipReportingSiteUpdate,

    [string]$CompletionGateProfile,
    [string]$DiagnosisJson,
    [string]$EvaluationId,

    [string]$FreezeProfile,
    [string]$FreezeId,
    [switch]$ForceFreeze,
    [switch]$SkipCompletionGateForFreeze,

    [string]$BaselineReplicas = "A",
    [switch]$SkipProvisioning,
    [switch]$SkipClusterValidationStep,
    [switch]$SkipPlacementProfileStep,
    [switch]$SkipLocalAIDeploymentStep,
    [switch]$SkipMinimalObservabilityStep,
    [switch]$SkipLatencyInjection,
    [switch]$SkipDefaultSchedulerValidation,
    [switch]$SkipSchedulerCapture,
    [switch]$SkipTelemetryPriming,
    [switch]$SkipClusterLensCapture,
    [switch]$SkipBenchmark,
    [switch]$SkipDiagnosis,
    [switch]$SkipReportingStep,
    [switch]$SkipCompletionGateStep,
    [switch]$SkipFreezeStep,
    [switch]$ContinueOnFailure,

    [switch]$WriteLatestAliases
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$provisioningLauncher = Join-Path $repoRoot "scripts\infrastructure\provision\Start-ProviderBackedProvisioning.ps1"
$clusterValidationLauncher = Join-Path $repoRoot "scripts\infrastructure\validation\Start-ProviderBackedClusterValidation.ps1"
$deploymentLauncher = Join-Path $repoRoot "scripts\application\deployment\Start-ProviderBackedLocalAIDeployment.ps1"
$placementProfileLauncher = Join-Path $repoRoot "scripts\placement\Resolve-PlacementProfile.ps1"
$minimalObservabilityLauncher = Join-Path $repoRoot "scripts\observability\minimal\Start-MinimalObservability.ps1"
$reportingLauncher = Join-Path $repoRoot "scripts\load\post\Start-Reporting.ps1"
$completionGateLauncher = Join-Path $repoRoot "scripts\load\post\Start-CompletionGate.ps1"
$freezeLauncher = Join-Path $repoRoot "scripts\load\post\Start-FreezeExperimentalCycle.ps1"
$providerBackedCycleRunner = Join-Path $repoRoot "scripts\experimental-cycles\run-provider-backed-cycle.py"

function Resolve-PythonCommand {
    $candidates = @(
        @{ Executable = "python";  PrefixArguments = @() },
        @{ Executable = "py";      PrefixArguments = @("-3") },
        @{ Executable = "python3"; PrefixArguments = @() }
    )

    foreach ($candidate in $candidates) {
        $command = Get-Command ([string]$candidate.Executable) -ErrorAction SilentlyContinue
        if (-not $command) { continue }

        try {
            $prefixArguments = @($candidate.PrefixArguments)
            $null = & $command.Source @($prefixArguments + @("--version")) 2>$null
            if ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE) {
                return [pscustomobject]@{
                    Executable      = $command.Source
                    PrefixArguments = $prefixArguments
                }
            }
        }
        catch {
            continue
        }
    }

    throw "No compatible Python interpreter found in PATH. Expected 'python', 'py -3' or 'python3'."
}

if ([string]::IsNullOrWhiteSpace($CycleConfig)) {
    $CycleConfig = Join-Path $repoRoot "config\experimental-cycles\C1.json"
}

Write-Host "==============================================="
Write-Host " experimental cycle launcher"
Write-Host "==============================================="
Write-Host "Repository      : $repoRoot"
Write-Host "Cycle           : $CycleConfig"
Write-Host "Execution scope : $ExecutionScope"
Write-Host ""

if ($ExecutionScope -eq "provider-backed-cycle") {
    if (-not (Test-Path $providerBackedCycleRunner)) { throw "Provider-backed cycle runner not found: $providerBackedCycleRunner" }
    $pythonCommand = Resolve-PythonCommand
    $argsList = @($providerBackedCycleRunner, "--repo-root", $repoRoot, "--cycle-config", $CycleConfig, "--tool-path", $ToolPath, "--baseline-replicas", $BaselineReplicas)
    if (-not [string]::IsNullOrWhiteSpace($ProviderConfig)) { $argsList += @("--provider-config", $ProviderConfig) }
    if (-not [string]::IsNullOrWhiteSpace($RunId)) { $argsList += @("--run-id", $RunId) }
    if (-not [string]::IsNullOrWhiteSpace($BaseUrl)) { $argsList += @("--base-url", $BaseUrl) }
    if (-not [string]::IsNullOrWhiteSpace($BenchmarkConfig)) { $argsList += @("--benchmark-config", $BenchmarkConfig) }
    if ($NoPortForward) { $argsList += "--no-port-forward" }
    if ($DryRun) { $argsList += "--dry-run" }
    if ($ContinueOnFailure) { $argsList += "--continue-on-failure" }
    if ($AllowMetricsWarning) { $argsList += "--allow-metrics-warning" }
    if ($ConfirmDelete) { $argsList += "--confirm-delete" }
    if ($ForceFreeze) { $argsList += "--force-freeze" }
    if ($WriteLatestAliases) { $argsList += "--write-latest-aliases" }
    if ($SkipProvisioning) { $argsList += "--skip-provisioning" }
    if ($SkipClusterValidationStep) { $argsList += "--skip-cluster-validation" }
    if ($SkipPlacementProfileStep) { $argsList += "--skip-placement-profile" }
    if ($SkipLocalAIDeploymentStep) { $argsList += "--skip-localai-deployment" }
    if ($SkipSmokeTest) { $argsList += "--skip-smoke-test" }
    if ($SkipMinimalObservabilityStep) { $argsList += "--skip-minimal-observability" }
    if ($SkipLatencyInjection) { $argsList += "--skip-latency-injection" }
    if ($SkipDefaultSchedulerValidation) { $argsList += "--skip-default-scheduler-validation" }
    if ($SkipSchedulerCapture) { $argsList += "--skip-scheduler-capture" }
    if ($SkipTelemetryPriming) { $argsList += "--skip-telemetry-priming" }
    if ($SkipClusterLensCapture) { $argsList += "--skip-cluster-lens-capture" }
    if ($SkipBenchmark) { $argsList += "--skip-benchmark" }
    if ($SkipDiagnosis) { $argsList += "--skip-diagnosis" }
    if ($SkipReportingStep) { $argsList += "--skip-reporting" }
    if ($SkipCompletionGateStep) { $argsList += "--skip-completion-gate" }
    if ($SkipFreezeStep) { $argsList += "--skip-freeze" }
    $pythonArgs = @($pythonCommand.PrefixArguments) + $argsList
    & $pythonCommand.Executable @pythonArgs
    exit $LASTEXITCODE
}

if ($ExecutionScope -eq "provisioning") {
    if (-not (Test-Path $provisioningLauncher)) { throw "Provider-backed provisioning launcher not found: $provisioningLauncher" }
    $provisioningArgs = @{
        CycleConfig = $CycleConfig
        Action      = $ProvisioningAction
        ToolPath    = $ToolPath
    }
    if (-not [string]::IsNullOrWhiteSpace($ProviderConfig)) { $provisioningArgs.ProviderConfig = $ProviderConfig }
    if ($DryRun) { $provisioningArgs.DryRun = $true }
    if ($ConfirmDelete) { $provisioningArgs.ConfirmDelete = $true }
    if (-not [string]::IsNullOrWhiteSpace($RunId)) { $provisioningArgs.RunId = $RunId }
    if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) { $provisioningArgs.OutputRoot = $OutputRoot }
    if ($WriteLatestAliases) { $provisioningArgs.WriteLatestAliases = $true }
    & $provisioningLauncher @provisioningArgs
    exit $LASTEXITCODE
}

if ($ExecutionScope -eq "cluster-validation") {
    if (-not (Test-Path $clusterValidationLauncher)) { throw "Provider-backed cluster validation launcher not found: $clusterValidationLauncher" }
    $clusterValidationArgs = @{
        CycleConfig = $CycleConfig
    }
    if (-not [string]::IsNullOrWhiteSpace($ClusterValidationProfile)) { $clusterValidationArgs.ClusterValidationProfile = $ClusterValidationProfile }
    if (-not [string]::IsNullOrWhiteSpace($ValidationProfile)) { $clusterValidationArgs.ValidationProfile = $ValidationProfile }
    if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) { $clusterValidationArgs.Kubeconfig = $Kubeconfig }
    if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) { $clusterValidationArgs.OutputRoot = $OutputRoot }
    if (-not [string]::IsNullOrWhiteSpace($RunId)) { $clusterValidationArgs.ValidationId = $RunId }
    if ($DryRun) { $clusterValidationArgs.DryRun = $true }
    if ($SkipPreValidationGate) { $clusterValidationArgs.SkipPreValidationGate = $true }
    if ($AllowMetricsWarning) { $clusterValidationArgs.AllowMetricsWarning = $true }
    if ($WriteLatestAliases) { $clusterValidationArgs.WriteLatestAliases = $true }
    & $clusterValidationLauncher @clusterValidationArgs
    exit $LASTEXITCODE
}


if ($ExecutionScope -eq "placement-profile") {
    if (-not (Test-Path $placementProfileLauncher)) { throw "Placement profile launcher not found: $placementProfileLauncher" }
    $placementProfileArgs = @{}
    if (-not [string]::IsNullOrWhiteSpace($CycleConfig)) { $placementProfileArgs.CycleConfig = $CycleConfig }
    if (-not [string]::IsNullOrWhiteSpace($DeploymentProfile)) { $placementProfileArgs.ApplicationDeploymentProfile = $DeploymentProfile }
    if (-not [string]::IsNullOrWhiteSpace($PlacementProfileId)) { $placementProfileArgs.PlacementProfileId = $PlacementProfileId }
    if (-not [string]::IsNullOrWhiteSpace($PlacementProfilePath)) { $placementProfileArgs.PlacementProfilePath = $PlacementProfilePath }
    if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) { $placementProfileArgs.OutputRoot = $OutputRoot }
    if (-not [string]::IsNullOrWhiteSpace($RunId)) { $placementProfileArgs.ResolutionId = $RunId }
    if ($WriteLatestAliases) { $placementProfileArgs.WriteLatestAliases = $true }
    & $placementProfileLauncher @placementProfileArgs
    exit $LASTEXITCODE
}


if ($ExecutionScope -eq "minimal-observability") {
    if (-not (Test-Path $minimalObservabilityLauncher)) { throw "Minimal observability launcher not found: $minimalObservabilityLauncher" }
    $minimalObservabilityArgs = @{
        CycleConfig = $CycleConfig
        Action      = $MinimalObservabilityAction
    }
    if (-not [string]::IsNullOrWhiteSpace($MinimalObservabilityProfile)) { $minimalObservabilityArgs.ProfileConfig = $MinimalObservabilityProfile }
    if (-not [string]::IsNullOrWhiteSpace($ObservabilityStage)) { $minimalObservabilityArgs.Stage = $ObservabilityStage }
    if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) { $minimalObservabilityArgs.Kubeconfig = $Kubeconfig }
    if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) { $minimalObservabilityArgs.OutputRoot = $OutputRoot }
    if (-not [string]::IsNullOrWhiteSpace($RunId)) { $minimalObservabilityArgs.ObservabilityId = $RunId }
    if (-not [string]::IsNullOrWhiteSpace($MeasurementCsvPrefix)) { $minimalObservabilityArgs.MeasurementCsvPrefix = $MeasurementCsvPrefix }
    if ($DryRun) { $minimalObservabilityArgs.DryRun = $true }
    if ($SkipClusterValidationGate) { $minimalObservabilityArgs.SkipClusterValidationGate = $true }
    if ($SkipApplicationDeploymentGate) { $minimalObservabilityArgs.SkipApplicationDeploymentGate = $true }
    if ($WriteLatestAliases) { $minimalObservabilityArgs.WriteLatestAliases = $true }
    & $minimalObservabilityLauncher @minimalObservabilityArgs
    exit $LASTEXITCODE
}


if ($ExecutionScope -eq "reporting") {
    if (-not (Test-Path $reportingLauncher)) { throw "Reporting launcher not found: $reportingLauncher" }
    $resolvedReportingProfile = $ReportingProfile
    if ([string]::IsNullOrWhiteSpace($resolvedReportingProfile)) {
        $cycleData = Get-Content -Path $CycleConfig -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($cycleData.reporting -and $cycleData.reporting.reportingProfilePath) {
            $resolvedReportingProfile = [string]$cycleData.reporting.reportingProfilePath
        } elseif ($cycleData.providerBackedInfrastructure -and $cycleData.providerBackedInfrastructure.reportingProfilePath) {
            $resolvedReportingProfile = [string]$cycleData.providerBackedInfrastructure.reportingProfilePath
        } elseif ($cycleData.pipelineProfiles -and $cycleData.pipelineProfiles.reporting) {
            $resolvedReportingProfile = [string]$cycleData.pipelineProfiles.reporting
        }
    }
    if ([string]::IsNullOrWhiteSpace($resolvedReportingProfile)) {
        throw "Reporting profile path is not declared in the cycle profile and was not provided explicitly."
    }
    $reportingArgs = @{
        RepoRoot      = $repoRoot
        ProfileConfig = $resolvedReportingProfile
    }
    if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) { $reportingArgs.OutputRoot = $OutputRoot }
    if (-not [string]::IsNullOrWhiteSpace($ReportingId)) { $reportingArgs.ReportingId = $ReportingId }
    elseif (-not [string]::IsNullOrWhiteSpace($RunId)) { $reportingArgs.ReportingId = $RunId }
    if ($Archive) { $reportingArgs.Archive = $true }
    if ($ArchiveCurrent) { $reportingArgs.ArchiveCurrent = $true }
    if ($ForceArchive) { $reportingArgs.ForceArchive = $true }
    if ($SkipReportingSiteUpdate) { $reportingArgs.SkipReportingSiteUpdate = $true }
    & $reportingLauncher @reportingArgs
    exit $LASTEXITCODE
}


if ($ExecutionScope -eq "completion-gate") {
    if (-not (Test-Path $completionGateLauncher)) { throw "Completion gate launcher not found: $completionGateLauncher" }
    $resolvedCompletionGateProfile = $CompletionGateProfile
    if ([string]::IsNullOrWhiteSpace($resolvedCompletionGateProfile)) {
        $cycleData = Get-Content -Path $CycleConfig -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($cycleData.completionGate -and $cycleData.completionGate.completionGateProfilePath) {
            $resolvedCompletionGateProfile = [string]$cycleData.completionGate.completionGateProfilePath
        } elseif ($cycleData.providerBackedInfrastructure -and $cycleData.providerBackedInfrastructure.completionGateProfilePath) {
            $resolvedCompletionGateProfile = [string]$cycleData.providerBackedInfrastructure.completionGateProfilePath
        } elseif ($cycleData.pipelineProfiles -and $cycleData.pipelineProfiles.completionGate) {
            $resolvedCompletionGateProfile = [string]$cycleData.pipelineProfiles.completionGate
        }
    }
    $completionGateArgs = @{
        CycleConfig = $CycleConfig
    }
    if (-not [string]::IsNullOrWhiteSpace($resolvedCompletionGateProfile)) { $completionGateArgs.ProfileConfig = $resolvedCompletionGateProfile }
    if (-not [string]::IsNullOrWhiteSpace($DiagnosisJson)) { $completionGateArgs.DiagnosisJson = $DiagnosisJson }
    if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) { $completionGateArgs.OutputRoot = $OutputRoot }
    if (-not [string]::IsNullOrWhiteSpace($EvaluationId)) { $completionGateArgs.EvaluationId = $EvaluationId }
    elseif (-not [string]::IsNullOrWhiteSpace($RunId)) { $completionGateArgs.EvaluationId = $RunId }
    if ($DryRun) { $completionGateArgs.DryRun = $true }
    & $completionGateLauncher @completionGateArgs
    exit $LASTEXITCODE
}


if ($ExecutionScope -eq "freeze") {
    if (-not (Test-Path $freezeLauncher)) { throw "Freeze launcher not found: $freezeLauncher" }
    $resolvedFreezeProfile = $FreezeProfile
    if ([string]::IsNullOrWhiteSpace($resolvedFreezeProfile)) {
        $cycleData = Get-Content -Path $CycleConfig -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($cycleData.freeze -and $cycleData.freeze.freezeProfilePath) {
            $resolvedFreezeProfile = [string]$cycleData.freeze.freezeProfilePath
        } elseif ($cycleData.freezeOutputs -and $cycleData.freezeOutputs.freezeProfilePath) {
            $resolvedFreezeProfile = [string]$cycleData.freezeOutputs.freezeProfilePath
        } elseif ($cycleData.providerBackedInfrastructure -and $cycleData.providerBackedInfrastructure.freezeProfilePath) {
            $resolvedFreezeProfile = [string]$cycleData.providerBackedInfrastructure.freezeProfilePath
        } elseif ($cycleData.pipelineProfiles -and $cycleData.pipelineProfiles.freeze) {
            $resolvedFreezeProfile = [string]$cycleData.pipelineProfiles.freeze
        }
    }
    $freezeArgs = @{
        RepoRoot     = $repoRoot
        CycleConfig  = $CycleConfig
    }
    if (-not [string]::IsNullOrWhiteSpace($resolvedFreezeProfile)) { $freezeArgs.ProfileConfig = $resolvedFreezeProfile }
    if (-not [string]::IsNullOrWhiteSpace($FreezeId)) { $freezeArgs.FreezeId = $FreezeId }
    elseif (-not [string]::IsNullOrWhiteSpace($RunId)) { $freezeArgs.FreezeId = $RunId }
    if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) { $freezeArgs.OutputRoot = $OutputRoot }
    if ($ForceFreeze) { $freezeArgs.Force = $true }
    if ($DryRun) { $freezeArgs.DryRun = $true }
    if ($SkipCompletionGateForFreeze) { $freezeArgs.SkipCompletionGate = $true }
    if ($WriteLatestAliases) { $freezeArgs.WriteLatestAliases = $true }
    & $freezeLauncher @freezeArgs
    exit $LASTEXITCODE
}

if ($ExecutionScope -eq "localai-deployment") {
    if (-not (Test-Path $deploymentLauncher)) { throw "Provider-backed LocalAI deployment launcher not found: $deploymentLauncher" }
    $deploymentArgs = @{
        CycleConfig = $CycleConfig
        Action      = $DeploymentAction
    }
    if (-not [string]::IsNullOrWhiteSpace($DeploymentProfile)) { $deploymentArgs.DeploymentProfile = $DeploymentProfile }
    if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) { $deploymentArgs.Kubeconfig = $Kubeconfig }
    if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) { $deploymentArgs.OutputRoot = $OutputRoot }
    if (-not [string]::IsNullOrWhiteSpace($RunId)) { $deploymentArgs.DeploymentId = $RunId }
    if ($DryRun) { $deploymentArgs.DryRun = $true }
    if ($SkipClusterValidationGate) { $deploymentArgs.SkipClusterValidationGate = $true }
    if ($SkipSmokeTest) { $deploymentArgs.SkipSmokeTest = $true }
    if (-not [string]::IsNullOrWhiteSpace($BaseUrl)) { $deploymentArgs.BaseUrl = $BaseUrl }
    if ($NoPortForward) { $deploymentArgs.NoPortForward = $true }
    if ($WriteLatestAliases) { $deploymentArgs.WriteLatestAliases = $true }
    & $deploymentLauncher @deploymentArgs
    exit $LASTEXITCODE
}

throw "Unsupported execution scope: $ExecutionScope"
