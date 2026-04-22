param(
    [string]$BaseUrl = "http://localhost:8080",
    [string]$Model = "llama-3.2-1b-instruct:q4_k_m",
    [int]$Users = 1,
    [int]$SpawnRate = 1,
    [string]$RunTime = "1m",
    [switch]$DryRun,
    [string]$CsvPrefix,
    [string]$LocustFile,
    [double]$Temperature = 0.1,
    [double]$RequestTimeoutSeconds = 120,
    [string]$Prompt = "Reply with only READY.",
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
    [switch]$SkipApiSmoke
)

$ErrorActionPreference = "Stop"

function Test-CommandAvailable {
    param([string]$CommandName)

    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
    return $null -ne $cmd
}

function Get-DefaultExploratoryCsvPrefix {
    param(
        [string]$RepositoryRoot,
        [int]$ScenarioUsers,
        [int]$ScenarioSpawnRate,
        [string]$ScenarioRunTime
    )

    if ($ScenarioUsers -eq 1 -and $ScenarioSpawnRate -eq 1 -and $ScenarioRunTime -eq "1m") {
        return Join-Path $RepositoryRoot "results\exploratory\E1_smoke_single_user\locust-smoke"
    }

    if ($ScenarioUsers -eq 2 -and $ScenarioSpawnRate -eq 1 -and $ScenarioRunTime -eq "1m") {
        return Join-Path $RepositoryRoot "results\exploratory\E2_low_load_two_users\locust-low_load"
    }

    if ($ScenarioUsers -eq 4 -and $ScenarioSpawnRate -eq 2 -and $ScenarioRunTime -eq "1m") {
        return Join-Path $RepositoryRoot "results\exploratory\E3_small_concurrency_four_users\locust-small_concurrency"
    }

    return Join-Path $RepositoryRoot "results\exploratory\manual_run\locust-exploratory"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunPhases.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunProtocol.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunClusterCapture.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunPortForward.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunMetricSet.ps1")

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

$precheckScript = Join-Path $repoRoot "scripts\validation\precheck\Invoke-BenchmarkPrecheck.ps1"
$clusterCaptureScript = Join-Path $repoRoot "scripts\validation\cluster-side\Collect-ClusterSideArtifacts.ps1"

if ([string]::IsNullOrWhiteSpace($LocustFile)) {
    $LocustFile = Join-Path $repoRoot "load-tests\locust\locustfile.py"
}

if ([string]::IsNullOrWhiteSpace($CsvPrefix)) {
    $CsvPrefix = Get-DefaultExploratoryCsvPrefix `
        -RepositoryRoot $repoRoot `
        -ScenarioUsers $Users `
        -ScenarioSpawnRate $SpawnRate `
        -ScenarioRunTime $RunTime
}

if (-not (Test-Path $LocustFile)) {
    throw "Il file Locust specificato non esiste: $LocustFile"
}

if (-not $SkipPrecheck -and -not (Test-Path $precheckScript)) {
    throw "Lo script di pre-check non esiste: $precheckScript"
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

if (-not (Test-Path $clusterCaptureScript)) {
    throw "Lo script di cluster-side collection non esiste: $clusterCaptureScript"
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
if ($apiSmokeEnabled -and -not (Test-Path $apiSmokeScript)) { throw "Lo script di API smoke non esiste: $apiSmokeScript" }
$csvDirectory = Split-Path -Parent $CsvPrefix
if (-not [string]::IsNullOrWhiteSpace($csvDirectory) -and -not (Test-Path $csvDirectory)) {
    New-Item -ItemType Directory -Path $csvDirectory -Force | Out-Null
}

$runId = [System.IO.Path]::GetFileName($CsvPrefix)
if ([string]::IsNullOrWhiteSpace($runId)) {
    $runId = "locust-exploratory"
}

$phasePlan = New-PhasePlan `
    -PhaseProfile $phaseProfile `
    -MeasurementUsers $Users `
    -MeasurementSpawnRate $SpawnRate `
    -ScenarioMeasurementDuration $RunTime `
    -MeasurementCsvPrefix $CsvPrefix `
    -WarmUpDurationOverride $WarmUpDuration `
    -MeasurementDurationOverride $MeasurementDuration `
    -SkipWarmUp:$SkipWarmUp
Write-PhaseManifest -PhasePlan $phasePlan -OutputPath $phasePlan.PhaseManifestPath
$protocolPaths = Get-ProtocolPaths -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -ProtocolProfile $protocolProfile
$clusterCapturePaths = Get-ClusterCaptureStagePaths -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -ClusterCaptureProfile $clusterCaptureProfile
$metricSetPaths = Get-MetricSetPaths -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -MetricSetProfile $metricSetProfile
$metricSetClientArtifacts = Get-MetricSetClientArtifactList -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix
$metricSetClusterArtifacts = Get-MetricSetClusterArtifactList -PreStagePrefix $clusterCapturePaths.PrePrefix -PostStagePrefix $clusterCapturePaths.PostPrefix

$precheckArgs = @(
    "-ProfileConfig", $PrecheckConfig,
    "-OutputPrefix", $CsvPrefix,
    "-BaseUrl", $BaseUrl
)
$apiSmokeArgs = @($apiSmokeScript, "-BaseUrl", $BaseUrl, "-Model", $Model)
$precheckCommand = if (-not $SkipPrecheck) { New-ProtocolCommandString -Arguments (@($precheckScript) + $precheckArgs) } else { "" }
$apiSmokeCommand = if ($apiSmokeEnabled) { New-ProtocolCommandString -Arguments $apiSmokeArgs } else { "" }

$clusterCapturePreArgs = @(
    "-ProfileConfig", $ClusterCaptureConfig,
    "-OutputPrefix", $clusterCapturePaths.PrePrefix,
    "-Stage", "pre"
)

$clusterCapturePostArgs = @(
    "-ProfileConfig", $ClusterCaptureConfig,
    "-OutputPrefix", $clusterCapturePaths.PostPrefix,
    "-Stage", "post"
)

if (-not [string]::IsNullOrWhiteSpace($Model)) {
    $precheckArgs += @("-Model", $Model)
}

if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $clusterCapturePreArgs += @("-Kubeconfig", $Kubeconfig)
    $clusterCapturePostArgs += @("-Kubeconfig", $Kubeconfig)
    $precheckArgs += @("-Kubeconfig", $Kubeconfig)
}

if (-not [string]::IsNullOrWhiteSpace($Namespace)) {
    $clusterCapturePreArgs += @("-Namespace", $Namespace)
    $clusterCapturePostArgs += @("-Namespace", $Namespace)
    $precheckArgs += @("-Namespace", $Namespace)
}

$clusterCapturePreCommand = New-ProtocolCommandString -Arguments (@($clusterCaptureScript) + $clusterCapturePreArgs)
$clusterCapturePostCommand = New-ProtocolCommandString -Arguments (@($clusterCaptureScript) + $clusterCapturePostArgs)
$clusterCapturePreArtifacts = Get-ClusterCaptureArtifactList -StagePrefix $clusterCapturePaths.PrePrefix -ClusterCaptureProfile $clusterCaptureProfile
$clusterCapturePostArtifacts = Get-ClusterCaptureArtifactList -StagePrefix $clusterCapturePaths.PostPrefix -ClusterCaptureProfile $clusterCaptureProfile

$env:LOCALAI_MODEL = $Model
$env:LOCALAI_TEMPERATURE = "$Temperature"
$env:LOCALAI_REQUEST_TIMEOUT_SECONDS = "$RequestTimeoutSeconds"
$env:LOCALAI_PROMPT = $Prompt

$warmUpLocustArgs = @(
    "-f", $LocustFile,
    "--headless",
    "--host", $BaseUrl,
    "-u", ([string]$phasePlan.WarmUpUsers),
    "-r", ([string]$phasePlan.WarmUpSpawnRate),
    "-t", $phasePlan.WarmUpDuration,
    "--csv", $phasePlan.WarmUpCsvPrefix,
    "--csv-full-history",
    "--only-summary"
)

$measurementLocustArgs = @(
    "-f", $LocustFile,
    "--headless",
    "--host", $BaseUrl,
    "-u", ([string]$phasePlan.MeasurementUsers),
    "-r", ([string]$phasePlan.MeasurementSpawnRate),
    "-t", $phasePlan.MeasurementDuration,
    "--csv", $phasePlan.MeasurementCsvPrefix,
    "--csv-full-history",
    "--only-summary"
)

$warmUpCommand = if ($phasePlan.WarmUpEnabled) { New-ProtocolCommandString -Arguments (@("locust") + $warmUpLocustArgs) } else { "" }
$measurementCommand = New-ProtocolCommandString -Arguments (@("locust") + $measurementLocustArgs)
$protocolPrecheckJsonPath = "${CsvPrefix}_precheck.json"
$protocolPrecheckTextPath = "${CsvPrefix}_precheck.txt"
Write-MetricSetFiles -MetricSetProfile $metricSetProfile -ManifestPath $metricSetPaths.ManifestPath -TextPath $metricSetPaths.TextPath -LauncherName "Start-LocustExploratory" -RunId $runId -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -ClientSourceArtifacts $metricSetClientArtifacts -ClusterSourceArtifacts $metricSetClusterArtifacts
Write-ProtocolFiles -ProtocolProfile $protocolProfile -ManifestPath $protocolPaths.ManifestPath -TextPath $protocolPaths.TextPath -LauncherName "Start-LocustExploratory" -RunId $runId -CleanupNote "Ensure the namespace is in the expected state before applying manifests and running the benchmark." -RecommendedApplyOrder @() -PrecheckEnabled (-not $SkipPrecheck) -PrecheckCommand $precheckCommand -PrecheckJsonPath $protocolPrecheckJsonPath -PrecheckTextPath $protocolPrecheckTextPath -ApiSmokeEnabled $apiSmokeEnabled -ApiSmokeCommand $apiSmokeCommand -ApiSmokeModel $Model -WarmUpEnabled $phasePlan.WarmUpEnabled -WarmUpCommand $warmUpCommand -WarmUpCsvPrefix $phasePlan.WarmUpCsvPrefix -MeasurementCommand $measurementCommand -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -PhaseManifestPath $phasePlan.PhaseManifestPath -ExtraArtifacts @($phasePlan.PhaseManifestPath, $metricSetPaths.ManifestPath, $metricSetPaths.TextPath) -ClusterCollectionEnabled $true -ClusterCollectionCommand $clusterCapturePreCommand -ClusterCollectionArtifacts $clusterCapturePreArtifacts -FinalSnapshotEnabled $true -FinalSnapshotCommand $clusterCapturePostCommand -FinalSnapshotArtifacts $clusterCapturePostArtifacts
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Controlled Locust Validation - LocalAI" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Repository               : $repoRoot"
Write-Host "Base URL                 : $BaseUrl"
Write-Host "Model                    : $Model"
Write-Host "Users                    : $Users"
Write-Host "Spawn rate               : $SpawnRate"
Write-Host "Scenario run time        : $RunTime"
Write-Host "Locust file              : $LocustFile"
Write-Host "CSV prefix               : $CsvPrefix"
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
if ($SkipPrecheck) {
    Write-Host "Pre-check                : disabled"
}
else {
    Write-Host "Pre-check                : $PrecheckConfig"
}
Write-Host ""
if (-not $SkipPrecheck) {
    Write-Host "Comando pre-check:" -ForegroundColor Yellow
    Write-Host ($precheckScript + " " + ($precheckArgs -join " "))
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

Ensure-LocalKubernetesPortForward -RepoRoot $repoRoot -BaseUrl $BaseUrl -KubeconfigPath $Kubeconfig -Namespace $Namespace | Out-Null

if (-not $SkipPrecheck) {
    & $precheckScript `
    -ProfileConfig $PrecheckConfig `
    -OutputPrefix ("{0}_precheck" -f $CsvPrefix) `
    -BaseUrl $BaseUrl `
    -Model $Model `
    -Kubeconfig $Kubeconfig `
    -Namespace $Namespace
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

& $clusterCaptureScript `
    -ProfileConfig $ClusterCaptureConfig `
    -OutputPrefix $clusterCapturePaths.PrePrefix `
    -Stage pre `
    -Kubeconfig $Kubeconfig `
    -Namespace $Namespace

if ($phasePlan.WarmUpEnabled) {
    $env:LOCALAI_STARTUP_MODEL_CHECK_ENABLED = "$($phasePlan.WarmUpStartupModelCheckEnabled)".ToLower()
    & locust @warmUpLocustArgs
}

$env:LOCALAI_STARTUP_MODEL_CHECK_ENABLED = "$($phasePlan.MeasurementStartupModelCheckEnabled)".ToLower()
& locust @measurementLocustArgs
$exitCode = $LASTEXITCODE
& $clusterCaptureScript `
    -ProfileConfig $ClusterCaptureConfig `
    -OutputPrefix $clusterCapturePaths.PostPrefix `
    -Stage post `
    -Kubeconfig $Kubeconfig `
    -Namespace $Namespace
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
