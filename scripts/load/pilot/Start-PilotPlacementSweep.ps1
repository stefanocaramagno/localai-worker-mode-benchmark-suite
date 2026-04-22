param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("PL1", "PL2")]
    [string]$Scenario,

    [Parameter(Mandatory = $true)]
    [ValidateSet("A", "B", "C")]
    [string]$Replica,

    [string]$BaseUrl = "http://localhost:8080",
    [string]$Model,
    [string]$Prompt = "Reply with only READY.",
    [string]$LocustFile,
    [string]$OutputRoot,
    [string]$PlacementScenarioConfigRoot,
    [string]$ModelScenarioConfigRoot,
    [string]$WorkerCountScenarioConfigRoot,
    [string]$WorkloadScenarioConfigRoot,
    [string]$BaselineConfig,
    [string]$PrecheckConfig,
    [string]$Kubeconfig,
    [string]$Namespace,
    [switch]$SkipPrecheck,
    [string]$PhaseConfig,
    [string]$WarmUpDuration,
    [string]$MeasurementDuration,
    [switch]$SkipWarmUp,
    [string]$ProtocolConfig,
    [string]$ClusterCaptureConfig,
    [string]$MetricSetConfig,
    [switch]$SkipApiSmoke,
    [switch]$DryRun,
    [switch]$AutoApplyK8s
)

$ErrorActionPreference = "Stop"


function Test-K8sApplyTarget {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -Path $Path -PathType Leaf) { return $true }
    if ((Test-Path -Path $Path -PathType Container) -and (Test-Path (Join-Path $Path "kustomization.yaml") -PathType Leaf)) { return $true }
    return $false
}

function Get-K8sApplyCommandString {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -Path $Path -PathType Leaf) { return "kubectl apply -f $Path" }
    if ((Test-Path -Path $Path -PathType Container) -and (Test-Path (Join-Path $Path "kustomization.yaml") -PathType Leaf)) { return "kubectl apply -k $Path" }
    throw "Target Kubernetes non valido o non risolvibile: $Path"
}

function Get-JsonScenarioConfig {
    param(
        [Parameter(Mandatory = $true, ParameterSetName = "ByFile")]
        [string]$ConfigFile,
        [Parameter(Mandatory = $true, ParameterSetName = "ByScenario")]
        [string]$ScenarioName,
        [Parameter(Mandatory = $true, ParameterSetName = "ByScenario")]
        [string]$ConfigRoot,
        [Parameter(Mandatory = $true)]
        [string[]]$RequiredProperties
    )

    $resolvedConfigFile = if ($PSCmdlet.ParameterSetName -eq "ByScenario") {
        Join-Path $ConfigRoot ("{0}.json" -f $ScenarioName)
    }
    else {
        $ConfigFile
    }

    if (-not (Test-Path $resolvedConfigFile)) {
        throw "Il file JSON non esiste: $resolvedConfigFile"
    }

    $rawConfig = Get-Content -Path $resolvedConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($propertyName in $RequiredProperties) {
        if (-not ($rawConfig.PSObject.Properties.Name -contains $propertyName)) {
            throw "Il file JSON '$resolvedConfigFile' non contiene la proprietà obbligatoria '$propertyName'."
        }
    }

    [pscustomobject]@{
        ConfigFile = (Resolve-Path $resolvedConfigFile).Path
        ScenarioFile = (Resolve-Path $resolvedConfigFile).Path
        RawConfig = $rawConfig
    }
}

function Invoke-K8sApplyTarget {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [string]$KubeconfigPath
    )

    if (-not (Test-CommandAvailable -CommandName "kubectl")) {
        throw "kubectl non risulta disponibile nel PATH. Impossibile applicare automaticamente i target Kubernetes."
    }

    $kubectlArgs = @()
    if (-not [string]::IsNullOrWhiteSpace($KubeconfigPath)) {
        $kubectlArgs += @("--kubeconfig", $KubeconfigPath)
    }

    if (Test-Path -Path $Path -PathType Leaf) {
        $kubectlArgs += @("apply", "-f", $Path)
    }
    elseif ((Test-Path -Path $Path -PathType Container) -and (Test-Path (Join-Path $Path "kustomization.yaml") -PathType Leaf)) {
        $kubectlArgs += @("apply", "-k", $Path)
    }
    else {
        throw "Target Kubernetes non valido o non risolvibile: $Path"
    }

    Write-Host ("Applicazione automatica target Kubernetes: kubectl " + ($kubectlArgs -join " ")) -ForegroundColor Yellow
    & kubectl @kubectlArgs

    if ($LASTEXITCODE -ne 0) {
        throw "Applicazione Kubernetes fallita per il target: $Path (exit code: $LASTEXITCODE)"
    }
}

function Test-CommandAvailable {
    param([string]$CommandName)
    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
    return $null -ne $cmd
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path

if ([string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $Kubeconfig = Join-Path $repoRoot "config\cluster-access\kubeconfig"
}

if ([string]::IsNullOrWhiteSpace($Namespace)) {
    $Namespace = "genai-thesis"
}

$resolvedBaseUrl = $BaseUrl
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunPhases.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunProtocol.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunClusterCapture.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunPortForward.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunMetricSet.ps1")

if ([string]::IsNullOrWhiteSpace($LocustFile)) { $LocustFile = Join-Path $repoRoot "load-tests\locust\locustfile.py" }
if ([string]::IsNullOrWhiteSpace($OutputRoot)) { $OutputRoot = Join-Path $repoRoot "results\pilot\placement" }
if ([string]::IsNullOrWhiteSpace($PlacementScenarioConfigRoot)) { $PlacementScenarioConfigRoot = Join-Path $repoRoot "config\scenarios\pilot\placement" }
if ([string]::IsNullOrWhiteSpace($ModelScenarioConfigRoot)) { $ModelScenarioConfigRoot = Join-Path $repoRoot "config\scenarios\pilot\models" }
if ([string]::IsNullOrWhiteSpace($WorkerCountScenarioConfigRoot)) { $WorkerCountScenarioConfigRoot = Join-Path $repoRoot "config\scenarios\pilot\worker-count" }
if ([string]::IsNullOrWhiteSpace($WorkloadScenarioConfigRoot)) { $WorkloadScenarioConfigRoot = Join-Path $repoRoot "config\scenarios\pilot\workload" }
if ([string]::IsNullOrWhiteSpace($BaselineConfig)) { $BaselineConfig = Join-Path $repoRoot "config\scenarios\baseline\B0.json" }
if ([string]::IsNullOrWhiteSpace($PrecheckConfig)) { $PrecheckConfig = Join-Path $repoRoot "config\precheck\TC1.json" }
if ([string]::IsNullOrWhiteSpace($PhaseConfig)) { $PhaseConfig = Join-Path $repoRoot "config\phases\WM1.json" }
if ([string]::IsNullOrWhiteSpace($ProtocolConfig)) { $ProtocolConfig = Join-Path $repoRoot "config\protocol\EP1.json" }
if ([string]::IsNullOrWhiteSpace($ClusterCaptureConfig)) { $ClusterCaptureConfig = Join-Path $repoRoot "config\cluster-capture\CS1.json" }
if ([string]::IsNullOrWhiteSpace($MetricSetConfig)) { $MetricSetConfig = Join-Path $repoRoot "config\metric-set\MS1.json" }

$precheckScript = Join-Path $repoRoot "scripts\validation\precheck\Invoke-BenchmarkPrecheck.ps1"
$clusterCaptureScript = Join-Path $repoRoot "scripts\validation\cluster-side\Collect-ClusterSideArtifacts.ps1"

if (-not (Test-Path $LocustFile)) { throw "Il file Locust specificato non esiste: $LocustFile" }
if (-not (Test-Path $BaselineConfig)) { throw "Il file di baseline non esiste: $BaselineConfig" }
if (-not $SkipPrecheck -and -not (Test-Path $precheckScript)) { throw "Lo script di pre-check non esiste: $precheckScript" }
if (-not (Test-Path $PhaseConfig)) { throw "Il file di profilo warm-up/misurazione non esiste: $PhaseConfig" }
if (-not (Test-Path $ProtocolConfig)) { throw "Il file di protocollo non esiste: $ProtocolConfig" }
if (-not (Test-Path $ClusterCaptureConfig)) { throw "Il file di cluster-side collection non esiste: $ClusterCaptureConfig" }
if (-not (Test-Path $MetricSetConfig)) { throw "Il file di metric set non esiste: $MetricSetConfig" }
if (-not (Test-Path $clusterCaptureScript)) { throw "Lo script di cluster-side collection non esiste: $clusterCaptureScript" }
if (-not $DryRun -and -not (Test-CommandAvailable -CommandName "locust")) { throw "Locust non risulta disponibile nel PATH. Installa Locust o verifica l'ambiente Python." }

$phaseProfile = Get-PhaseProfile -ProfileFile $PhaseConfig
$protocolProfile = Get-ProtocolProfile -ProfileFile $ProtocolConfig
$clusterCaptureProfile = Get-ClusterCaptureProfile -ProfileFile $ClusterCaptureConfig
$metricSetProfile = Get-MetricSetProfile -ProfileFile $MetricSetConfig
$apiSmokeScript = Join-Path $repoRoot $protocolProfile.ApiSmokeScriptRelativePathPowerShell
$apiSmokeEnabled = $protocolProfile.ApiSmokeEnabledDefault -and (-not $SkipApiSmoke)
if ($apiSmokeEnabled -and -not (Test-Path $apiSmokeScript)) { throw "Lo script di API smoke non esiste: $apiSmokeScript" }

$placementScenarioData = Get-JsonScenarioConfig `
    -ScenarioName $Scenario `
    -ConfigRoot $PlacementScenarioConfigRoot `
    -RequiredProperties @("scenarioId", "purpose", "placementType", "outputSubdir", "referenceBaselineId", "topologyDir")
$placementConfig = $placementScenarioData.RawConfig
$referenceBaselineId = [string]$placementConfig.referenceBaselineId

$baselineData = Get-JsonScenarioConfig -ConfigFile $BaselineConfig -RequiredProperties @(
    "baselineId",
    "purpose",
    "workerMode",
    "modelScenario",
    "resolvedModelName",
    "workerScenario",
    "resolvedWorkerCount",
    "workloadScenario",
    "resolvedWorkload",
    "namespaceManifest",
    "storageManifest",
    "prompt",
    "temperature",
    "requestTimeoutSeconds"
)
$baselineConfigData = $baselineData.RawConfig

if ($referenceBaselineId -ne [string]$baselineConfigData.baselineId) {
    throw "Lo scenario placement $Scenario richiede la baseline $referenceBaselineId ma il file fornito espone $($baselineConfigData.baselineId)."
}

$modelScenarioFile = Join-Path $ModelScenarioConfigRoot ("{0}.json" -f $baselineConfigData.modelScenario)
$workerScenarioFile = Join-Path $WorkerCountScenarioConfigRoot ("{0}.json" -f $baselineConfigData.workerScenario)
$workloadScenarioFile = Join-Path $WorkloadScenarioConfigRoot ("{0}.json" -f $baselineConfigData.workloadScenario)

$modelScenarioData = Get-JsonScenarioConfig -ConfigFile $modelScenarioFile -RequiredProperties @("scenarioId", "purpose", "modelName", "outputSubdir", "referenceBaselineId", "serverManifest")
$workerScenarioData = Get-JsonScenarioConfig -ConfigFile $workerScenarioFile -RequiredProperties @("scenarioId", "purpose", "workerCount", "outputSubdir", "referenceBaselineId")
$workloadScenarioData = Get-JsonScenarioConfig -ConfigFile $workloadScenarioFile -RequiredProperties @("scenarioId", "purpose", "users", "spawnRate", "runTime", "outputSubdir")
$modelConfig = $modelScenarioData.RawConfig
$workerConfig = $workerScenarioData.RawConfig
$workloadConfig = $workloadScenarioData.RawConfig

if ([string]$modelScenarioData.RawConfig.scenarioId -ne [string]$baselineConfigData.modelScenario -or [string]$modelScenarioData.RawConfig.modelName -ne [string]$baselineConfigData.resolvedModelName) {
    throw "La baseline placement non è coerente con lo scenario model di riferimento."
}

if ([string]$workerScenarioData.RawConfig.scenarioId -ne [string]$baselineConfigData.workerScenario -or [int]$workerScenarioData.RawConfig.workerCount -ne [int]$baselineConfigData.resolvedWorkerCount) {
    throw "La baseline placement non è coerente con lo scenario worker di riferimento."
}

if ([string]$workloadScenarioData.RawConfig.scenarioId -ne [string]$baselineConfigData.workloadScenario) {
    throw "La baseline placement non è coerente con lo scenario workload di riferimento."
}

if (-not [string]::IsNullOrWhiteSpace($Model) -and $Model -ne [string]$baselineConfigData.resolvedModelName) {
    throw "Il placement sweep è ancorato alla baseline $($baselineConfigData.baselineId). Il modello richiesto ($Model) non coincide con il modello fisso di baseline ($($baselineConfigData.resolvedModelName))."
}
$Model = [string]$baselineConfigData.resolvedModelName

if (-not [string]::IsNullOrWhiteSpace($Prompt) -and $Prompt -ne [string]$baselineConfigData.prompt) {
    throw "Il placement sweep è ancorato alla baseline $($baselineConfigData.baselineId). Il prompt richiesto non coincide con il prompt fisso di baseline."
}
$Prompt = [string]$baselineConfigData.prompt

$topologyRoot = Join-Path $repoRoot ([string]$placementConfig.topologyDir -replace '/', '\')
$serverManifest = Join-Path $repoRoot ([string]$modelConfig.serverManifest -replace '/', '\')
$namespaceManifest = Join-Path $repoRoot ([string]$baselineConfigData.namespaceManifest -replace '/', '\')
$storageManifest = Join-Path $repoRoot ([string]$baselineConfigData.storageManifest -replace '/', '\')
$topologyTarget = $topologyRoot
$sharedCompositionDir = Join-Path $repoRoot "infra\k8s\compositions\shared\rpc-workers-services"
$k8sApplyTargets = @($namespaceManifest, $sharedCompositionDir, $storageManifest, $topologyTarget, $serverManifest)
foreach ($targetPath in $k8sApplyTargets) {
    if (-not (Test-K8sApplyTarget -Path $targetPath)) { throw "Target Kubernetes non trovato o non valido: $targetPath" }
}

$outputDir = Join-Path $OutputRoot ([string]$placementConfig.outputSubdir)
if (-not (Test-Path $outputDir)) { New-Item -ItemType Directory -Path $outputDir -Force | Out-Null }
$runId = "${Scenario}_run${Replica}"
$csvPrefix = Join-Path $outputDir $runId

$phasePlan = New-PhasePlan `
    -PhaseProfile $phaseProfile `
    -MeasurementUsers ([int]$workloadConfig.users) `
    -MeasurementSpawnRate ([int]$workloadConfig.spawnRate) `
    -ScenarioMeasurementDuration ([string]$workloadConfig.runTime) `
    -MeasurementCsvPrefix $csvPrefix `
    -WarmUpDurationOverride $WarmUpDuration `
    -MeasurementDurationOverride $MeasurementDuration `
    -SkipWarmUp:$SkipWarmUp
Write-PhaseManifest -PhasePlan $phasePlan -OutputPath $phasePlan.PhaseManifestPath
$protocolPaths = Get-ProtocolPaths -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -ProtocolProfile $protocolProfile
$clusterCapturePaths = Get-ClusterCaptureStagePaths -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -ClusterCaptureProfile $clusterCaptureProfile
$metricSetPaths = Get-MetricSetPaths -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -MetricSetProfile $metricSetProfile
$metricSetClientArtifacts = Get-MetricSetClientArtifactList -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix
$metricSetClusterArtifacts = Get-MetricSetClusterArtifactList -PreStagePrefix $clusterCapturePaths.PrePrefix -PostStagePrefix $clusterCapturePaths.PostPrefix

$precheckJsonPath = "{0}_precheck.json" -f $csvPrefix
$precheckTextPath = "{0}_precheck.txt" -f $csvPrefix
$precheckOutputPrefix = "{0}_precheck" -f $csvPrefix
$precheckArgs = @(
    "-ProfileConfig", $PrecheckConfig,
    "-OutputPrefix", $precheckOutputPrefix,
    "-BaseUrl", $BaseUrl,
    "-Model", $Model
)
$precheckInvokeParams = @{
    ProfileConfig = $PrecheckConfig
    OutputPrefix  = $precheckOutputPrefix
    BaseUrl       = $BaseUrl
    Model         = $Model
}
if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $precheckArgs += @("-Kubeconfig", $Kubeconfig)
    $precheckInvokeParams.Kubeconfig = $Kubeconfig
}
if (-not [string]::IsNullOrWhiteSpace($Namespace)) {
    $precheckArgs += @("-Namespace", $Namespace)
    $precheckInvokeParams.Namespace = $Namespace
}
$apiSmokeArgs = @($apiSmokeScript, "-BaseUrl", $BaseUrl, "-Model", $Model)
$precheckCommand = if (-not $SkipPrecheck) { New-ProtocolCommandString -Arguments (@($precheckScript) + $precheckArgs) } else { "" }
$apiSmokeCommand = if ($apiSmokeEnabled) { New-ProtocolCommandString -Arguments $apiSmokeArgs } else { "" }

$clusterCapturePreArgs = @(
    "-ProfileConfig", $ClusterCaptureConfig,
    "-OutputPrefix", $clusterCapturePaths.PrePrefix,
    "-Stage", "pre"
)
$clusterCapturePreInvokeParams = @{
    ProfileConfig = $ClusterCaptureConfig
    OutputPrefix  = $clusterCapturePaths.PrePrefix
    Stage         = "pre"
}
if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $clusterCapturePreArgs += @("-Kubeconfig", $Kubeconfig)
    $clusterCapturePreInvokeParams.Kubeconfig = $Kubeconfig
}
if (-not [string]::IsNullOrWhiteSpace($Namespace)) {
    $clusterCapturePreArgs += @("-Namespace", $Namespace)
    $clusterCapturePreInvokeParams.Namespace = $Namespace
}

$clusterCapturePostArgs = @(
    "-ProfileConfig", $ClusterCaptureConfig,
    "-OutputPrefix", $clusterCapturePaths.PostPrefix,
    "-Stage", "post"
)
$clusterCapturePostInvokeParams = @{
    ProfileConfig = $ClusterCaptureConfig
    OutputPrefix  = $clusterCapturePaths.PostPrefix
    Stage         = "post"
}
if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $clusterCapturePostArgs += @("-Kubeconfig", $Kubeconfig)
    $clusterCapturePostInvokeParams.Kubeconfig = $Kubeconfig
}
if (-not [string]::IsNullOrWhiteSpace($Namespace)) {
    $clusterCapturePostArgs += @("-Namespace", $Namespace)
    $clusterCapturePostInvokeParams.Namespace = $Namespace
}

$clusterCapturePreCommand = New-ProtocolCommandString -Arguments (@($clusterCaptureScript) + $clusterCapturePreArgs)
$clusterCapturePostCommand = New-ProtocolCommandString -Arguments (@($clusterCaptureScript) + $clusterCapturePostArgs)
$clusterCapturePreArtifacts = Get-ClusterCaptureArtifactList -StagePrefix $clusterCapturePaths.PrePrefix -ClusterCaptureProfile $clusterCaptureProfile
$clusterCapturePostArtifacts = Get-ClusterCaptureArtifactList -StagePrefix $clusterCapturePaths.PostPrefix -ClusterCaptureProfile $clusterCaptureProfile

$env:LOCALAI_MODEL = $Model
$env:LOCALAI_PROMPT = $Prompt
$env:LOCALAI_REQUEST_TIMEOUT_SECONDS = [string]$baselineConfigData.requestTimeoutSeconds
$env:LOCALAI_TEMPERATURE = [string]$baselineConfigData.temperature

$warmUpLocustArgs = @(
    "-f", $LocustFile, "-H", $BaseUrl, "--headless",
    "-u", ([string]$phasePlan.WarmUpUsers), "-r", ([string]$phasePlan.WarmUpSpawnRate),
    "--run-time", $phasePlan.WarmUpDuration, "--csv", $phasePlan.WarmUpCsvPrefix, "--csv-full-history"
)
$measurementLocustArgs = @(
    "-f", $LocustFile, "-H", $BaseUrl, "--headless",
    "-u", ([string]$phasePlan.MeasurementUsers), "-r", ([string]$phasePlan.MeasurementSpawnRate),
    "--run-time", $phasePlan.MeasurementDuration, "--csv", $phasePlan.MeasurementCsvPrefix, "--csv-full-history"
)

$warmUpCommand = if ($phasePlan.WarmUpEnabled) { New-ProtocolCommandString -Arguments (@("locust") + $warmUpLocustArgs) } else { "" }
$measurementCommand = New-ProtocolCommandString -Arguments (@("locust") + $measurementLocustArgs)
$protocolPrecheckJsonPath = $precheckJsonPath
$protocolPrecheckTextPath = $precheckTextPath
Write-MetricSetFiles -MetricSetProfile $metricSetProfile -ManifestPath $metricSetPaths.ManifestPath -TextPath $metricSetPaths.TextPath -LauncherName "Start-PilotPlacementSweep" -RunId $runId -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -ClientSourceArtifacts $metricSetClientArtifacts -ClusterSourceArtifacts $metricSetClusterArtifacts

$recommendedApplyOrder = @(
    (Get-K8sApplyCommandString -Path $namespaceManifest),
    (Get-K8sApplyCommandString -Path $sharedCompositionDir),
    (Get-K8sApplyCommandString -Path $storageManifest),
    (Get-K8sApplyCommandString -Path $topologyTarget),
    (Get-K8sApplyCommandString -Path $serverManifest)
)

Write-ProtocolFiles -ProtocolProfile $protocolProfile -ManifestPath $protocolPaths.ManifestPath -TextPath $protocolPaths.TextPath -LauncherName "Start-PilotPlacementSweep" -RunId $runId -CleanupNote "Ensure the namespace is in the expected state before applying manifests and running the benchmark." -RecommendedApplyOrder $recommendedApplyOrder -PrecheckEnabled (-not $SkipPrecheck) -PrecheckCommand $precheckCommand -PrecheckJsonPath $protocolPrecheckJsonPath -PrecheckTextPath $protocolPrecheckTextPath -ApiSmokeEnabled $apiSmokeEnabled -ApiSmokeCommand $apiSmokeCommand -ApiSmokeModel $Model -WarmUpEnabled $phasePlan.WarmUpEnabled -WarmUpCommand $warmUpCommand -WarmUpCsvPrefix $phasePlan.WarmUpCsvPrefix -MeasurementCommand $measurementCommand -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -PhaseManifestPath $phasePlan.PhaseManifestPath -ExtraArtifacts @($phasePlan.PhaseManifestPath, $metricSetPaths.ManifestPath, $metricSetPaths.TextPath) -ClusterCollectionEnabled $true -ClusterCollectionCommand $clusterCapturePreCommand -ClusterCollectionArtifacts $clusterCapturePreArtifacts -FinalSnapshotEnabled $true -FinalSnapshotCommand $clusterCapturePostCommand -FinalSnapshotArtifacts $clusterCapturePostArtifacts
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Official Pilot Placement Sweep Launcher" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Repository                   : $repoRoot"
Write-Host "Placement scenario           : $Scenario"
Write-Host "Replica                      : $Replica"
Write-Host "Run ID                       : $runId"
Write-Host "Purpose                      : $($placementConfig.purpose)"
Write-Host "Placement cfg                : $($placementScenarioData.ConfigFile)"
Write-Host "Reference baseline           : $($baselineConfigData.baselineId)"
Write-Host "Baseline config              : $($baselineData.ConfigFile)"
Write-Host "Baseline purpose             : $($baselineConfigData.purpose)"
Write-Host "Resolved placement           : $($placementConfig.placementType)"
Write-Host "Fixed model scenario         : $($baselineConfigData.modelScenario)"
Write-Host "Model cfg                    : $($modelScenarioData.ConfigFile)"
Write-Host "Resolved model               : $Model"
Write-Host "Fixed worker-count scenario  : $($baselineConfigData.workerScenario)"
Write-Host "Worker-count cfg             : $($workerScenarioData.ConfigFile)"
Write-Host "Worker count                 : $($workerConfig.workerCount)"
Write-Host "Fixed workload               : $($baselineConfigData.workloadScenario)"
Write-Host "Workload cfg                 : $($workloadScenarioData.ConfigFile)"
Write-Host "Workload purpose             : $($workloadConfig.purpose)"
Write-Host "Scenario users               : $($workloadConfig.users)"
Write-Host "Scenario spawn rate          : $($workloadConfig.spawnRate)"
Write-Host "Scenario run time            : $($workloadConfig.runTime)"
Write-Host "Topology root                : $topologyRoot"
Write-Host "Server target                : $serverManifest"
Write-Host "Base URL                     : $BaseUrl"
Write-Host "Model                        : $Model"
Write-Host "Prompt                       : $Prompt"
Write-Host "Temperature                  : $($baselineConfigData.temperature)"
Write-Host "Request timeout (s)          : $($baselineConfigData.requestTimeoutSeconds)"
Write-Host "Locust file                  : $LocustFile"
Write-Host "Output root                  : $OutputRoot"
Write-Host "Output dir                   : $outputDir"
Write-Host "CSV prefix                   : $csvPrefix"
Write-Host "Phase profile                : $($phaseProfile.ProfileFile)"
Write-Host "Warm-up enabled              : $($phasePlan.WarmUpEnabled)"
Write-Host "Warm-up duration             : $($phasePlan.WarmUpDuration)"
Write-Host "Warm-up users                : $($phasePlan.WarmUpUsers)"
Write-Host "Warm-up spawn rate           : $($phasePlan.WarmUpSpawnRate)"
Write-Host "Warm-up CSV prefix           : $($phasePlan.WarmUpCsvPrefix)"
Write-Host "Measurement duration         : $($phasePlan.MeasurementDuration)"
Write-Host "Measurement users            : $($phasePlan.MeasurementUsers)"
Write-Host "Measurement spawn rate       : $($phasePlan.MeasurementSpawnRate)"
Write-Host "Measurement CSV prefix       : $($phasePlan.MeasurementCsvPrefix)"
Write-Host "Phase manifest               : $($phasePlan.PhaseManifestPath)"
Write-Host "Protocol profile             : $($protocolProfile.ProfileFile)"
Write-Host "Protocol manifest            : $($protocolPaths.ManifestPath)"
Write-Host "Protocol text                : $($protocolPaths.TextPath)"
Write-Host "Cluster capture profile      : $($clusterCaptureProfile.ProfileFile)"
Write-Host "Metric set profile           : $($metricSetProfile.ProfileFile)"
Write-Host "Metric set manifest          : $($metricSetPaths.ManifestPath)"
Write-Host "Metric set text              : $($metricSetPaths.TextPath)"
Write-Host "Cluster pre prefix           : $($clusterCapturePaths.PrePrefix)"
Write-Host "Cluster post prefix          : $($clusterCapturePaths.PostPrefix)"
Write-Host "Auto-apply Kubernetes        : $AutoApplyK8s"
Write-Host ""
Write-Host "Target Kubernetes raccomandati da applicare prima della run:" -ForegroundColor Yellow
foreach ($manifestPath in $recommendedApplyOrder) {
    Write-Host " - $manifestPath"
}
Write-Host ""
if (-not $SkipPrecheck) {
    Write-Host "Comando pre-check:" -ForegroundColor Yellow
    Write-Host $precheckCommand
    Write-Host ""
}
Write-Host "Comando cluster capture (pre):" -ForegroundColor Yellow
Write-Host $clusterCapturePreCommand
Write-Host ""
Write-Host "Comando cluster capture (post):" -ForegroundColor Yellow
Write-Host $clusterCapturePostCommand
Write-Host ""
if ($apiSmokeEnabled) {
    Write-Host "Comando API smoke:" -ForegroundColor Yellow
    Write-Host $apiSmokeCommand
    Write-Host ""
}
if ($phasePlan.WarmUpEnabled) {
    Write-Host "Comando warm-up:" -ForegroundColor Yellow
    Write-Host ("locust " + ($warmUpLocustArgs -join " "))
    Write-Host ""
}
else {
    Write-Host "Warm-up                : disabled"
    Write-Host ""
}
Write-Host "Comando measurement:" -ForegroundColor Yellow
Write-Host ("locust " + ($measurementLocustArgs -join " "))
Write-Host ""
if ($AutoApplyK8s) {
    Write-Host "Applicazione automatica dei target Kubernetes raccomandati prima della run." -ForegroundColor Yellow
    foreach ($targetPath in $k8sApplyTargets) {
        Invoke-K8sApplyTarget -Path $targetPath -KubeconfigPath $Kubeconfig
    }
    Ensure-LocalKubernetesPortForward -RepoRoot $repoRoot -BaseUrl $resolvedBaseUrl -KubeconfigPath $Kubeconfig -Namespace $Namespace | Out-Null
    Write-Host ""
}

if ($DryRun) {
    Write-Host "DRY RUN completato. Nessun test eseguito." -ForegroundColor Yellow
    exit 0
}

Ensure-LocalKubernetesPortForward -RepoRoot $repoRoot -BaseUrl $resolvedBaseUrl -KubeconfigPath $Kubeconfig -Namespace $Namespace | Out-Null

if (-not $SkipPrecheck) {
    & $precheckScript @precheckInvokeParams
    $precheckExitCode = $LASTEXITCODE
    if ($precheckExitCode -ne 0) {
        Write-Host "Pre-check terminato con FAIL (exit code $precheckExitCode). La run viene interrotta senza eseguire smoke, warm-up o measurement." -ForegroundColor Red
        exit $precheckExitCode
    }
}
if ($apiSmokeEnabled) {
    & $apiSmokeScript -BaseUrl $BaseUrl -Model $Model
    $apiSmokeExitCode = $LASTEXITCODE
    if ($apiSmokeExitCode -ne 0) {
        Write-Host "API smoke terminato con FAIL (exit code $apiSmokeExitCode). La run viene interrotta senza eseguire warm-up o measurement." -ForegroundColor Red
        exit $apiSmokeExitCode
    }
}
& $clusterCaptureScript @clusterCapturePreInvokeParams
if ($phasePlan.WarmUpEnabled) {
    $env:LOCALAI_STARTUP_MODEL_CHECK_ENABLED = "$($phasePlan.WarmUpStartupModelCheckEnabled)".ToLower()
    & locust @warmUpLocustArgs
}
$env:LOCALAI_STARTUP_MODEL_CHECK_ENABLED = "$($phasePlan.MeasurementStartupModelCheckEnabled)".ToLower()
& locust @measurementLocustArgs
$exitCode = $LASTEXITCODE
& $clusterCaptureScript @clusterCapturePostInvokeParams
$clusterCapturePostExitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0 -and $clusterCapturePostExitCode -eq 0) {
    Write-Host "Run completata con successo." -ForegroundColor Green
    Write-Host "File attesi:" -ForegroundColor Green
    if ($phasePlan.WarmUpEnabled) {
        Write-Host " - $($phasePlan.WarmUpCsvPrefix)_stats.csv"
        Write-Host " - $($phasePlan.WarmUpCsvPrefix)_stats_history.csv"
        Write-Host " - $($phasePlan.WarmUpCsvPrefix)_failures.csv"
        Write-Host " - $($phasePlan.WarmUpCsvPrefix)_exceptions.csv"
    }
    Write-Host " - $($phasePlan.MeasurementCsvPrefix)_stats.csv"
    Write-Host " - $($phasePlan.MeasurementCsvPrefix)_stats_history.csv"
    Write-Host " - $($phasePlan.MeasurementCsvPrefix)_failures.csv"
    Write-Host " - $($phasePlan.MeasurementCsvPrefix)_exceptions.csv"
    Write-Host "Cluster-side artifacts (pre):" -ForegroundColor Green
    foreach ($artifact in $clusterCapturePreArtifacts) { Write-Host " - $artifact" }
    Write-Host "Metric-set artifacts:" -ForegroundColor Green
    Write-Host " - $($metricSetPaths.ManifestPath)"
    Write-Host " - $($metricSetPaths.TextPath)"
    Write-Host "Cluster-side artifacts (post):" -ForegroundColor Green
    foreach ($artifact in $clusterCapturePostArtifacts) { Write-Host " - $artifact" }
    exit 0
}
else {
    if ($exitCode -ne 0) {
        Write-Host "La run Locust è terminata con exit code $exitCode." -ForegroundColor Red
        exit $exitCode
    }
    Write-Host "La cluster-side collection finale è terminata con exit code $clusterCapturePostExitCode." -ForegroundColor Red
    exit $clusterCapturePostExitCode
}
