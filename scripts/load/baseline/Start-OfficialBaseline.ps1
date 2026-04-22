param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("A", "B", "C")]
    [string]$Replica,

    [string]$BaselineConfig,
    [string]$BaseUrl,
    [string]$LocustFile,
    [string]$OutputRoot,
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
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Test-CommandAvailable {
    param([string]$CommandName)

    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
    return $null -ne $cmd
}

function Get-JsonScenarioConfig {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConfigFile,
        [Parameter(Mandatory = $true)]
        [string[]]$RequiredProperties
    )

    if (-not (Test-Path $ConfigFile)) {
        throw "Il file JSON non esiste: $ConfigFile"
    }

    $rawConfig = Get-Content -Path $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json

    foreach ($propertyName in $RequiredProperties) {
        if (-not ($rawConfig.PSObject.Properties.Name -contains $propertyName)) {
            throw "Il file JSON '$ConfigFile' non contiene la proprietà obbligatoria '$propertyName'."
        }
    }

    return [pscustomobject]@{
        ConfigFile = (Resolve-Path $ConfigFile).Path
        RawConfig  = $rawConfig
    }
}

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

function Write-BaselineLockFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OutputPath,
        [Parameter(Mandatory = $true)]
        [string]$BaselineConfigPath,
        [Parameter(Mandatory = $true)]
        [string]$BaselineId,
        [Parameter(Mandatory = $true)]
        [string]$ModelScenario,
        [Parameter(Mandatory = $true)]
        [string]$ModelName,
        [Parameter(Mandatory = $true)]
        [string]$WorkerScenario,
        [Parameter(Mandatory = $true)]
        [int]$WorkerCount,
        [Parameter(Mandatory = $true)]
        [string]$PlacementScenario,
        [Parameter(Mandatory = $true)]
        [string]$PlacementType,
        [Parameter(Mandatory = $true)]
        [string]$WorkloadScenario,
        [Parameter(Mandatory = $true)]
        [int]$Users,
        [Parameter(Mandatory = $true)]
        [int]$SpawnRate,
        [Parameter(Mandatory = $true)]
        [string]$RunTime,
        [Parameter(Mandatory = $true)]
        [string]$TopologyDir,
        [Parameter(Mandatory = $true)]
        [string]$ServerManifest,
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,
        [Parameter(Mandatory = $true)]
        [string]$Prompt,
        [Parameter(Mandatory = $true)]
        [int]$RequestTimeoutSeconds,
        [Parameter(Mandatory = $true)]
        [double]$Temperature,
        [Parameter(Mandatory = $true)]
        [string]$WarmUpDuration,
        [Parameter(Mandatory = $true)]
        [string]$MeasurementDuration,
        [Parameter(Mandatory = $true)]
        [string]$RunId
    )

    $payload = [ordered]@{
        baselineConfig = $BaselineConfigPath
        baselineId = $BaselineId
        resolvedConfiguration = [ordered]@{
            modelScenario = $ModelScenario
            modelName = $ModelName
            workerScenario = $WorkerScenario
            workerCount = $WorkerCount
            placementScenario = $PlacementScenario
            placementType = $PlacementType
            workloadScenario = $WorkloadScenario
            users = $Users
            spawnRate = $SpawnRate
            scenarioRunTime = $RunTime
            topologyDir = $TopologyDir
            serverManifest = $ServerManifest
            baseUrl = $BaseUrl
            prompt = $Prompt
            requestTimeoutSeconds = $RequestTimeoutSeconds
            temperature = $Temperature
            warmUpDuration = $WarmUpDuration
            measurementDuration = $MeasurementDuration
        }
        runId = $RunId
    }

    $payload | ConvertTo-Json -Depth 12 | Set-Content -Path $OutputPath -Encoding UTF8
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunPhases.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunProtocol.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunClusterCapture.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunPortForward.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunMetricSet.ps1")

if ([string]::IsNullOrWhiteSpace($BaselineConfig)) {
    $BaselineConfig = Join-Path $repoRoot "config\scenarios\baseline\B0.json"
}

if ([string]::IsNullOrWhiteSpace($LocustFile)) {
    $LocustFile = Join-Path $repoRoot "load-tests\locust\locustfile.py"
}

if ([string]::IsNullOrWhiteSpace($PrecheckConfig)) {
    $PrecheckConfig = Join-Path $repoRoot "config\precheck\TC1.json"
}

if ([string]::IsNullOrWhiteSpace($PhaseConfig)) {
    $PhaseConfig = Join-Path $repoRoot "config\phases\WM1.json"
}

if ([string]::IsNullOrWhiteSpace($ProtocolConfig)) {
    $ProtocolConfig = Join-Path $repoRoot "config\protocol\EP1.json"
}

if ([string]::IsNullOrWhiteSpace($ClusterCaptureConfig)) {
    $ClusterCaptureConfig = Join-Path $repoRoot "config\cluster-capture\CS1.json"
}

if ([string]::IsNullOrWhiteSpace($MetricSetConfig)) {
    $MetricSetConfig = Join-Path $repoRoot "config\metric-set\MS1.json"
}

if ([string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $Kubeconfig = Join-Path $repoRoot "config\cluster-access\kubeconfig"
}

if ([string]::IsNullOrWhiteSpace($Namespace)) {
    $Namespace = "genai-thesis"
}

if (-not (Test-Path $BaselineConfig)) {
    throw "Il file di baseline non esiste: $BaselineConfig"
}

if (-not (Test-Path $LocustFile)) {
    throw "Il file Locust specificato non esiste: $LocustFile"
}

if (-not (Test-Path $PhaseConfig)) {
    throw "Il file di profilo warm-up/misurazione non esiste: $PhaseConfig"
}

if (-not (Test-Path $ProtocolConfig)) {
    throw "Il file di protocollo non esiste: $ProtocolConfig"
}

if (-not (Test-Path $ClusterCaptureConfig)) {
    throw "Il file di cluster-side collection non esiste: $ClusterCaptureConfig"
}

if (-not (Test-Path $MetricSetConfig)) {
    throw "Il file di metric set non esiste: $MetricSetConfig"
}

if (-not (Test-Path $Kubeconfig)) {
    throw "Il file kubeconfig specificato non esiste: $Kubeconfig"
}

$precheckScript = Join-Path $repoRoot "scripts\validation\precheck\Invoke-BenchmarkPrecheck.ps1"
$clusterCaptureScript = Join-Path $repoRoot "scripts\validation\cluster-side\Collect-ClusterSideArtifacts.ps1"

if (-not (Test-Path $clusterCaptureScript)) {
    throw "Lo script di cluster-side collection non esiste: $clusterCaptureScript"
}

if (-not $SkipPrecheck -and -not (Test-Path $precheckScript)) {
    throw "Lo script di pre-check non esiste: $precheckScript"
}

if (-not $DryRun -and -not (Test-CommandAvailable -CommandName "locust")) {
    throw "Locust non risulta disponibile nel PATH. Installa Locust o verifica l'ambiente Python."
}

$phaseProfile = Get-PhaseProfile -ProfileFile $PhaseConfig
$protocolProfile = Get-ProtocolProfile -ProfileFile $ProtocolConfig
$clusterCaptureProfile = Get-ClusterCaptureProfile -ProfileFile $ClusterCaptureConfig
$metricSetProfile = Get-MetricSetProfile -ProfileFile $MetricSetConfig
$apiSmokeScript = Join-Path $repoRoot $protocolProfile.ApiSmokeScriptRelativePathPowerShell
$apiSmokeEnabled = $protocolProfile.ApiSmokeEnabledDefault -and (-not $SkipApiSmoke)
if ($apiSmokeEnabled -and -not (Test-Path $apiSmokeScript)) {
    throw "Lo script di API smoke non esiste: $apiSmokeScript"
}

$baselineData = Get-JsonScenarioConfig `
    -ConfigFile $BaselineConfig `
    -RequiredProperties @(
        "baselineId",
        "purpose",
        "modelScenario",
        "resolvedModelName",
        "workerScenario",
        "resolvedWorkerCount",
        "placementScenario",
        "resolvedPlacementType",
        "workloadScenario",
        "topologyDir",
        "serverManifest",
        "namespaceManifest",
        "storageManifest",
        "baseUrl",
        "prompt",
        "temperature",
        "requestTimeoutSeconds",
        "resultsRoot"
    )

$baselineScenario = $baselineData.RawConfig

$modelScenarioFile = Join-Path $repoRoot ("config\scenarios\pilot\models\{0}.json" -f $baselineScenario.modelScenario)
$workerScenarioFile = Join-Path $repoRoot ("config\scenarios\pilot\worker-count\{0}.json" -f $baselineScenario.workerScenario)
$placementScenarioFile = Join-Path $repoRoot ("config\scenarios\pilot\placement\{0}.json" -f $baselineScenario.placementScenario)
$workloadScenarioFile = Join-Path $repoRoot ("config\scenarios\pilot\workload\{0}.json" -f $baselineScenario.workloadScenario)

$modelScenarioData = Get-JsonScenarioConfig -ConfigFile $modelScenarioFile -RequiredProperties @("scenarioId", "modelName", "serverManifest")
$workerScenarioData = Get-JsonScenarioConfig -ConfigFile $workerScenarioFile -RequiredProperties @("scenarioId", "workerCount")
$placementScenarioData = Get-JsonScenarioConfig -ConfigFile $placementScenarioFile -RequiredProperties @("scenarioId", "placementType", "topologyDir")
$workloadScenarioData = Get-JsonScenarioConfig -ConfigFile $workloadScenarioFile -RequiredProperties @("scenarioId", "users", "spawnRate", "runTime")

$resolvedBaseUrl = if ([string]::IsNullOrWhiteSpace($BaseUrl)) { [string]$baselineScenario.baseUrl } else { [string]$BaseUrl }
$resolvedOutputRoot = if ([string]::IsNullOrWhiteSpace($OutputRoot)) { Join-Path $repoRoot ([string]$baselineScenario.resultsRoot -replace '/', '\') } else { [string]$OutputRoot }

$topologyRoot = Join-Path $repoRoot ([string]$baselineScenario.topologyDir -replace '/', '\')
$serverManifest = Join-Path $repoRoot ([string]$baselineScenario.serverManifest -replace '/', '\')
$namespaceManifest = Join-Path $repoRoot ([string]$baselineScenario.namespaceManifest -replace '/', '\')
$storageManifest = Join-Path $repoRoot ([string]$baselineScenario.storageManifest -replace '/', '\')
$topologyTarget = $topologyRoot
$sharedCompositionDir = Join-Path $repoRoot "infra\k8s\compositions\shared\rpc-workers-services"
$k8sApplyTargets = @($namespaceManifest, $sharedCompositionDir, $storageManifest, $topologyTarget, $serverManifest)
foreach ($targetPath in $k8sApplyTargets) {
    if (-not (Test-K8sApplyTarget -Path $targetPath)) {
        throw "Target Kubernetes non trovato o non valido: $targetPath"
    }
}

$runId = "{0}_run{1}" -f [string]$baselineScenario.baselineId, $Replica
$outputDir = Join-Path $resolvedOutputRoot ("{0}_official_locked" -f [string]$baselineScenario.baselineId)
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

$csvPrefix = Join-Path $outputDir $runId
$phasePlan = New-PhasePlan -PhaseProfile $phaseProfile -MeasurementUsers ([int]$workloadScenarioData.RawConfig.users) -MeasurementSpawnRate ([int]$workloadScenarioData.RawConfig.spawnRate) -ScenarioMeasurementDuration ([string]$workloadScenarioData.RawConfig.runTime) -MeasurementCsvPrefix $csvPrefix -WarmUpDurationOverride $WarmUpDuration -MeasurementDurationOverride $MeasurementDuration -SkipWarmUp:$SkipWarmUp
Write-PhaseManifest -PhasePlan $phasePlan -OutputPath $phasePlan.PhaseManifestPath
$protocolPaths = Get-ProtocolPaths -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -ProtocolProfile $protocolProfile
$clusterCapturePaths = Get-ClusterCaptureStagePaths -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -ClusterCaptureProfile $clusterCaptureProfile
$metricSetPaths = Get-MetricSetPaths -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -MetricSetProfile $metricSetProfile
$metricSetClientArtifacts = Get-MetricSetClientArtifactList -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix
$metricSetClusterArtifacts = Get-MetricSetClusterArtifactList -PreStagePrefix $clusterCapturePaths.PrePrefix -PostStagePrefix $clusterCapturePaths.PostPrefix

$runLockFile = Join-Path $outputDir ("{0}_baseline-lock.json" -f $runId)
$precheckOutputPrefix = "{0}_precheck" -f $csvPrefix
$precheckJsonPath = "{0}.json" -f $precheckOutputPrefix
$precheckTextPath = "{0}.txt" -f $precheckOutputPrefix

Write-BaselineLockFile `
    -OutputPath $runLockFile `
    -BaselineConfigPath $baselineData.ConfigFile `
    -BaselineId ([string]$baselineScenario.baselineId) `
    -ModelScenario ([string]$baselineScenario.modelScenario) `
    -ModelName ([string]$baselineScenario.resolvedModelName) `
    -WorkerScenario ([string]$baselineScenario.workerScenario) `
    -WorkerCount ([int]$baselineScenario.resolvedWorkerCount) `
    -PlacementScenario ([string]$baselineScenario.placementScenario) `
    -PlacementType ([string]$baselineScenario.resolvedPlacementType) `
    -WorkloadScenario ([string]$baselineScenario.workloadScenario) `
    -Users ([int]$workloadScenarioData.RawConfig.users) `
    -SpawnRate ([int]$workloadScenarioData.RawConfig.spawnRate) `
    -RunTime ([string]$workloadScenarioData.RawConfig.runTime) `
    -TopologyDir ([string]$baselineScenario.topologyDir) `
    -ServerManifest ([string]$baselineScenario.serverManifest) `
    -BaseUrl $resolvedBaseUrl `
    -Prompt ([string]$baselineScenario.prompt) `
    -RequestTimeoutSeconds ([int]$baselineScenario.requestTimeoutSeconds) `
    -Temperature ([double]$baselineScenario.temperature) `
    -WarmUpDuration $phasePlan.WarmUpDuration `
    -MeasurementDuration $phasePlan.MeasurementDuration `
    -RunId $runId

$precheckCommandPreview = "$precheckScript -ProfileConfig $PrecheckConfig -BaseUrl $resolvedBaseUrl -Model $([string]$baselineScenario.resolvedModelName) -OutputPrefix $precheckOutputPrefix -Kubeconfig $Kubeconfig -Namespace $Namespace"

$apiSmokeArgs = @($apiSmokeScript, "-BaseUrl", $resolvedBaseUrl, "-Model", ([string]$baselineScenario.resolvedModelName))
$precheckCommand = if (-not $SkipPrecheck) { $precheckCommandPreview } else { "" }
$apiSmokeCommand = if ($apiSmokeEnabled) { New-ProtocolCommandString -Arguments $apiSmokeArgs } else { "" }

$clusterCapturePreArgs = @(
    "-ProfileConfig", $ClusterCaptureConfig,
    "-Kubeconfig", $Kubeconfig,
    "-Namespace", $Namespace,
    "-OutputPrefix", $clusterCapturePaths.PrePrefix,
    "-Stage", "pre"
)

$clusterCapturePostArgs = @(
    "-ProfileConfig", $ClusterCaptureConfig,
    "-Kubeconfig", $Kubeconfig,
    "-Namespace", $Namespace,
    "-OutputPrefix", $clusterCapturePaths.PostPrefix,
    "-Stage", "post"
)

$clusterCapturePreCommand = New-ProtocolCommandString -Arguments (@($clusterCaptureScript) + $clusterCapturePreArgs)
$clusterCapturePostCommand = New-ProtocolCommandString -Arguments (@($clusterCaptureScript) + $clusterCapturePostArgs)
$clusterCapturePreArtifacts = Get-ClusterCaptureArtifactList -StagePrefix $clusterCapturePaths.PrePrefix -ClusterCaptureProfile $clusterCaptureProfile
$clusterCapturePostArtifacts = Get-ClusterCaptureArtifactList -StagePrefix $clusterCapturePaths.PostPrefix -ClusterCaptureProfile $clusterCaptureProfile

$env:LOCALAI_MODEL = [string]$baselineScenario.resolvedModelName
$env:LOCALAI_PROMPT = [string]$baselineScenario.prompt
$env:LOCALAI_REQUEST_TIMEOUT_SECONDS = [string]$baselineScenario.requestTimeoutSeconds
$env:LOCALAI_TEMPERATURE = [string]$baselineScenario.temperature

$warmUpLocustArgs = @("-f", $LocustFile, "-H", $resolvedBaseUrl, "--headless", "-u", ([string]$phasePlan.WarmUpUsers), "-r", ([string]$phasePlan.WarmUpSpawnRate), "--run-time", $phasePlan.WarmUpDuration, "--csv", $phasePlan.WarmUpCsvPrefix, "--csv-full-history")
$measurementLocustArgs = @("-f", $LocustFile, "-H", $resolvedBaseUrl, "--headless", "-u", ([string]$phasePlan.MeasurementUsers), "-r", ([string]$phasePlan.MeasurementSpawnRate), "--run-time", $phasePlan.MeasurementDuration, "--csv", $phasePlan.MeasurementCsvPrefix, "--csv-full-history")

$recommendedApplyOrder = @(
    (Get-K8sApplyCommandString -Path $namespaceManifest),
    (Get-K8sApplyCommandString -Path $sharedCompositionDir),
    (Get-K8sApplyCommandString -Path $storageManifest),
    (Get-K8sApplyCommandString -Path $topologyTarget),
    (Get-K8sApplyCommandString -Path $serverManifest)
)

$warmUpCommand = if ($phasePlan.WarmUpEnabled) { New-ProtocolCommandString -Arguments (@("locust") + $warmUpLocustArgs) } else { "" }
$measurementCommand = New-ProtocolCommandString -Arguments (@("locust") + $measurementLocustArgs)
$protocolPrecheckJsonPath = $precheckJsonPath
$protocolPrecheckTextPath = $precheckTextPath

Write-MetricSetFiles -MetricSetProfile $metricSetProfile -ManifestPath $metricSetPaths.ManifestPath -TextPath $metricSetPaths.TextPath -LauncherName "Start-OfficialBaseline" -RunId $runId -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -ClientSourceArtifacts $metricSetClientArtifacts -ClusterSourceArtifacts $metricSetClusterArtifacts
Write-ProtocolFiles -ProtocolProfile $protocolProfile -ManifestPath $protocolPaths.ManifestPath -TextPath $protocolPaths.TextPath -LauncherName "Start-OfficialBaseline" -RunId $runId -CleanupNote "Ensure the namespace is in the expected state before applying manifests and running the benchmark." -RecommendedApplyOrder $recommendedApplyOrder -PrecheckEnabled (-not $SkipPrecheck) -PrecheckCommand $precheckCommand -PrecheckJsonPath $protocolPrecheckJsonPath -PrecheckTextPath $protocolPrecheckTextPath -ApiSmokeEnabled $apiSmokeEnabled -ApiSmokeCommand $apiSmokeCommand -ApiSmokeModel ([string]$baselineScenario.resolvedModelName) -WarmUpEnabled $phasePlan.WarmUpEnabled -WarmUpCommand $warmUpCommand -WarmUpCsvPrefix $phasePlan.WarmUpCsvPrefix -MeasurementCommand $measurementCommand -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -PhaseManifestPath $phasePlan.PhaseManifestPath -ExtraArtifacts @($phasePlan.PhaseManifestPath, $runLockFile, $metricSetPaths.ManifestPath, $metricSetPaths.TextPath) -ClusterCollectionEnabled $true -ClusterCollectionCommand $clusterCapturePreCommand -ClusterCollectionArtifacts $clusterCapturePreArtifacts -FinalSnapshotEnabled $true -FinalSnapshotCommand $clusterCapturePostCommand -FinalSnapshotArtifacts $clusterCapturePostArtifacts

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Official Locked Baseline Launcher" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Repository               : $repoRoot"
Write-Host "Baseline config          : $($baselineData.ConfigFile)"
Write-Host "Baseline ID              : $($baselineScenario.baselineId)"
Write-Host "Purpose                  : $($baselineScenario.purpose)"
Write-Host "Replica                  : $Replica"
Write-Host "Run ID                   : $runId"
Write-Host "Model scenario           : $($baselineScenario.modelScenario)"
Write-Host "Resolved model           : $($baselineScenario.resolvedModelName)"
Write-Host "Worker-count scenario    : $($baselineScenario.workerScenario)"
Write-Host "Worker count             : $($baselineScenario.resolvedWorkerCount)"
Write-Host "Placement scenario       : $($baselineScenario.placementScenario)"
Write-Host "Placement type           : $($baselineScenario.resolvedPlacementType)"
Write-Host "Workload scenario        : $($baselineScenario.workloadScenario)"
Write-Host "Scenario users           : $($workloadScenarioData.RawConfig.users)"
Write-Host "Scenario spawn rate      : $($workloadScenarioData.RawConfig.spawnRate)"
Write-Host "Scenario run time        : $($workloadScenarioData.RawConfig.runTime)"
Write-Host "Topology root            : $topologyRoot"
Write-Host "Server target            : $serverManifest"
Write-Host "Base URL                 : $resolvedBaseUrl"
Write-Host "Prompt                   : $($baselineScenario.prompt)"
Write-Host "Temperature              : $($baselineScenario.temperature)"
Write-Host "Request timeout (s)      : $($baselineScenario.requestTimeoutSeconds)"
Write-Host "Locust file              : $LocustFile"
Write-Host "Output dir               : $outputDir"
Write-Host "CSV prefix               : $csvPrefix"
Write-Host "Run lock file            : $runLockFile"
Write-Host "Phase profile            : $($phaseProfile.ProfileFile)"
Write-Host "Warm-up enabled          : $($phasePlan.WarmUpEnabled)"
Write-Host "Warm-up duration         : $($phasePlan.WarmUpDuration)"
Write-Host "Warm-up users            : $($phasePlan.WarmUpUsers)"
Write-Host "Warm-up spawn rate       : $($phasePlan.WarmUpSpawnRate)"
Write-Host "Warm-up CSV prefix       : $($phasePlan.WarmUpCsvPrefix)"
Write-Host "Measurement duration     : $($phasePlan.MeasurementDuration)"
Write-Host "Measurement users        : $($phasePlan.MeasurementUsers)"
Write-Host "Measurement spawn rate   : $($phasePlan.MeasurementSpawnRate)"
Write-Host "Measurement CSV prefix   : $($phasePlan.MeasurementCsvPrefix)"
Write-Host "Phase manifest           : $($phasePlan.PhaseManifestPath)"
Write-Host "Protocol profile         : $($protocolProfile.ProfileFile)"
Write-Host "Protocol manifest        : $($protocolPaths.ManifestPath)"
Write-Host "Protocol text            : $($protocolPaths.TextPath)"
Write-Host "Cluster capture profile  : $($clusterCaptureProfile.ProfileFile)"
Write-Host "Metric set profile       : $($metricSetProfile.ProfileFile)"
Write-Host "Metric set manifest      : $($metricSetPaths.ManifestPath)"
Write-Host "Metric set text          : $($metricSetPaths.TextPath)"
Write-Host "Cluster pre prefix       : $($clusterCapturePaths.PrePrefix)"
Write-Host "Cluster post prefix      : $($clusterCapturePaths.PostPrefix)"
Write-Host "Kubeconfig               : $Kubeconfig"
Write-Host "Namespace                : $Namespace"
if ($SkipPrecheck) { Write-Host "Pre-check                : disabled" } else { Write-Host "Pre-check                : $PrecheckConfig" }
Write-Host ""
Write-Host "Target Kubernetes raccomandati da applicare prima della run:" -ForegroundColor Yellow
foreach ($manifestPath in $recommendedApplyOrder) { Write-Host " - $manifestPath" }
Write-Host ""
if (-not $SkipPrecheck) {
    Write-Host "Comando pre-check:" -ForegroundColor Yellow
    Write-Host $precheckCommandPreview
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

if ($DryRun) {
    Write-Host "DRY RUN completato. Nessun test eseguito." -ForegroundColor Yellow
    exit 0
}

Ensure-LocalKubernetesPortForward -RepoRoot $repoRoot -BaseUrl $resolvedBaseUrl -KubeconfigPath $Kubeconfig -Namespace $Namespace | Out-Null

if (-not $SkipPrecheck) {
    & $precheckScript `
        -ProfileConfig $PrecheckConfig `
        -Kubeconfig $Kubeconfig `
        -Namespace $Namespace `
        -BaseUrl $resolvedBaseUrl `
        -Model ([string]$baselineScenario.resolvedModelName) `
        -OutputPrefix $precheckOutputPrefix
    $precheckExitCode = $LASTEXITCODE
    if ($precheckExitCode -ne 0) {
        Write-Host "Pre-check terminato con FAIL (exit code $precheckExitCode). La run viene interrotta senza eseguire smoke, warm-up o measurement." -ForegroundColor Red
        exit $precheckExitCode
    }
}

& $clusterCaptureScript `
    -ProfileConfig $ClusterCaptureConfig `
    -Kubeconfig $Kubeconfig `
    -Namespace $Namespace `
    -OutputPrefix $clusterCapturePaths.PrePrefix `
    -Stage pre

if ($apiSmokeEnabled) {
    & $apiSmokeScript -BaseUrl $resolvedBaseUrl -Model ([string]$baselineScenario.resolvedModelName)
    $apiSmokeExitCode = $LASTEXITCODE
    if ($apiSmokeExitCode -ne 0) {
        Write-Host "API smoke terminato con FAIL (exit code $apiSmokeExitCode). La run viene interrotta senza eseguire warm-up o measurement." -ForegroundColor Red
        exit $apiSmokeExitCode
    }
}

if ($phasePlan.WarmUpEnabled) {
    $env:LOCALAI_STARTUP_MODEL_CHECK_ENABLED = "$($phasePlan.WarmUpStartupModelCheckEnabled)".ToLower()
    & locust @warmUpLocustArgs
}

$env:LOCALAI_STARTUP_MODEL_CHECK_ENABLED = "$($phasePlan.MeasurementStartupModelCheckEnabled)".ToLower()
& locust @measurementLocustArgs
$exitCode = $LASTEXITCODE

& $clusterCaptureScript `
    -ProfileConfig $ClusterCaptureConfig `
    -Kubeconfig $Kubeconfig `
    -Namespace $Namespace `
    -OutputPrefix $clusterCapturePaths.PostPrefix `
    -Stage post

$clusterCapturePostExitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0 -and $clusterCapturePostExitCode -eq 0) {
    Write-Host "Run completata con successo." -ForegroundColor Green
    if ($phasePlan.WarmUpEnabled) {
        Write-Host "Warm-up artifacts:" -ForegroundColor Green
        Write-Host " - $($phasePlan.WarmUpCsvPrefix)_stats.csv"
        Write-Host " - $($phasePlan.WarmUpCsvPrefix)_stats_history.csv"
        Write-Host " - $($phasePlan.WarmUpCsvPrefix)_failures.csv"
        Write-Host " - $($phasePlan.WarmUpCsvPrefix)_exceptions.csv"
    }
    Write-Host "Measurement artifacts:" -ForegroundColor Green
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
