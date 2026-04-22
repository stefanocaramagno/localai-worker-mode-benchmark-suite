param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("W1", "W2", "W3", "W4")]
    [string]$Scenario,

    [Parameter(Mandatory = $true)]
    [ValidateSet("A", "B", "C")]
    [string]$Replica,

    [string]$BaseUrl = "http://localhost:8080",
    [string]$Model = "llama-3.2-1b-instruct:q4_k_m",
    [string]$Prompt = "Reply with only READY.",
    [string]$LocustFile,
    [string]$OutputRoot,
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
$UnsupportedScenarioExitCode = 42


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

function Get-KubectlJson {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$KubeconfigPath
    )

    if (-not (Test-CommandAvailable -CommandName "kubectl")) {
        throw "kubectl non risulta disponibile nel PATH."
    }

    $kubectlArgs = @()
    if (-not [string]::IsNullOrWhiteSpace($KubeconfigPath)) {
        $kubectlArgs += @("--kubeconfig", $KubeconfigPath)
    }
    $kubectlArgs += $Arguments
    $kubectlArgs += @("-o", "json")

    $raw = & kubectl @kubectlArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Comando kubectl fallito: kubectl $($kubectlArgs -join ' ')"
    }

    return ($raw | ConvertFrom-Json)
}

function Wait-ForWorkerPodsScheduled {
    param(
        [Parameter(Mandatory = $true)][string]$Namespace,
        [Parameter(Mandatory = $true)][int]$ExpectedWorkerCount,
        [string]$KubeconfigPath,
        [int]$TimeoutSeconds = 90,
        [int]$PollIntervalSeconds = 3
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $podList = Get-KubectlJson -Arguments @("get", "pods", "-n", $Namespace) -KubeconfigPath $KubeconfigPath
        $items = @($podList.items)

        $workerPods = @(
            $items | Where-Object {
                $podName = $_.metadata.name
                -not [string]::IsNullOrWhiteSpace($podName) -and $podName -like "localai-rpc-*"
            }
        )

        $scheduledWorkerPods = @(
            $workerPods | Where-Object {
                $specProperty = $_.PSObject.Properties['spec']
                if ($null -eq $specProperty) { return $false }
                $spec = $specProperty.Value
                if ($null -eq $spec) { return $false }
                $nodeNameProperty = $spec.PSObject.Properties['nodeName']
                if ($null -eq $nodeNameProperty) { return $false }
                -not [string]::IsNullOrWhiteSpace([string]$nodeNameProperty.Value)
            }
        )

        if ($workerPods.Count -ge $ExpectedWorkerCount -and $scheduledWorkerPods.Count -ge $ExpectedWorkerCount) {
            return $scheduledWorkerPods
        }

        Start-Sleep -Seconds $PollIntervalSeconds
    }
    while ((Get-Date) -lt $deadline)

    $observed = if ($null -ne $workerPods) { $workerPods.Count } else { 0 }
    $scheduled = if ($null -ne $scheduledWorkerPods) { $scheduledWorkerPods.Count } else { 0 }
    throw "Timeout durante l'attesa della schedulazione dei pod worker RPC nel namespace '$Namespace'. Attesi: $ExpectedWorkerCount, osservati: $observed, con nodeName valorizzato: $scheduled."
}

function Get-SafeNestedPropertyValue {
    param(
        [Parameter(Mandatory = $false)][object]$Object,
        [Parameter(Mandatory = $true)][string[]]$PropertyPath
    )

    $current = $Object
    foreach ($propertyName in $PropertyPath) {
        if ($null -eq $current) {
            return $null
        }

        $properties = $current.PSObject.Properties
        if ($null -eq $properties) {
            return $null
        }

        $property = $properties[$propertyName]
        if ($null -eq $property) {
            return $null
        }

        $current = $property.Value
    }

    return $current
}

function Get-WorkerSchedulingDiagnostics {
    param(
        [Parameter(Mandatory = $true)][string]$Namespace,
        [string]$KubeconfigPath
    )

    $podList = Get-KubectlJson -Arguments @("get", "pods", "-n", $Namespace) -KubeconfigPath $KubeconfigPath
    $items = @($podList.items)
    $workerPods = @(
        $items | Where-Object {
            $podName = [string](Get-SafeNestedPropertyValue -Object $_ -PropertyPath @('metadata', 'name'))
            -not [string]::IsNullOrWhiteSpace($podName) -and $podName -like "localai-rpc-*"
        }
    )

    $details = @()
    foreach ($pod in $workerPods) {
        $podName = [string](Get-SafeNestedPropertyValue -Object $pod -PropertyPath @('metadata', 'name'))
        $nodeName = [string](Get-SafeNestedPropertyValue -Object $pod -PropertyPath @('spec', 'nodeName'))
        $phase = [string](Get-SafeNestedPropertyValue -Object $pod -PropertyPath @('status', 'phase'))
        $reason = [string](Get-SafeNestedPropertyValue -Object $pod -PropertyPath @('status', 'reason'))

        $eventArgs = @("get", "events", "-n", $Namespace, "--field-selector", ("involvedObject.name={0}" -f $podName), "--sort-by=.metadata.creationTimestamp")
        $eventList = Get-KubectlJson -Arguments $eventArgs -KubeconfigPath $KubeconfigPath
        $eventItems = @($eventList.items)
        $eventMessages = @()

        foreach ($eventItem in $eventItems) {
            $evtReason = [string](Get-SafeNestedPropertyValue -Object $eventItem -PropertyPath @('reason'))
            $evtMessage = [string](Get-SafeNestedPropertyValue -Object $eventItem -PropertyPath @('message'))

            if ([string]::IsNullOrWhiteSpace($evtReason) -and [string]::IsNullOrWhiteSpace($evtMessage)) {
                continue
            }

            if ([string]::IsNullOrWhiteSpace($evtReason)) {
                $eventMessages += $evtMessage
            }
            else {
                $eventMessages += ("[{0}] {1}" -f $evtReason, $evtMessage)
            }
        }

        $details += [pscustomobject]@{
            podName = $podName
            phase = $phase
            reason = $reason
            nodeName = $nodeName
            events = @($eventMessages)
        }
    }

    return @($details)
}

function Test-WorkerScenarioUnsupportedUnderCurrentConstraints {
    param(
        [Parameter(Mandatory = $true)][Object[]]$Diagnostics,
        [Parameter(Mandatory = $true)][int]$ExpectedWorkerCount,
        [Parameter(Mandatory = $true)][string]$PlacementType
    )

    if ($ExpectedWorkerCount -le 0) {
        return $false
    }

    $items = @($Diagnostics)
    if ($items.Count -eq 0) {
        return $false
    }

    $pendingPods = @(
        $items | Where-Object {
            ([string]$_.phase -eq "Pending") -or [string]::IsNullOrWhiteSpace([string]$_.nodeName)
        }
    )

    if ($pendingPods.Count -eq 0) {
        return $false
    }

    $resourceOrPlacementEvidence = $false
    foreach ($pod in $pendingPods) {
        foreach ($message in @($pod.events)) {
            $normalized = ([string]$message).ToLowerInvariant()

            if (
                $normalized -match 'insufficient cpu' -or
                $normalized -match 'insufficient memory' -or
                $normalized -match "didn''t match pod''s node affinity/selector" -or
                $normalized -match "didn't match pod's node affinity/selector" -or
                $normalized -match 'preemption is not helpful' -or
                $normalized -match 'failedscheduling' -or
                $normalized -match '0/\d+ nodes are available'
            ) {
                $resourceOrPlacementEvidence = $true
                break
            }
        }

        if ($resourceOrPlacementEvidence) {
            break
        }
    }

    if ($resourceOrPlacementEvidence) {
        return $true
    }

    return $true
}

function Write-UnsupportedScenarioArtifacts {
    param(
        [Parameter(Mandatory = $true)][string]$OutputPrefix,
        [Parameter(Mandatory = $true)][string]$Scenario,
        [Parameter(Mandatory = $true)][string]$Replica,
        [Parameter(Mandatory = $true)][string]$Family,
        [Parameter(Mandatory = $true)][string]$Reason,
        [Parameter(Mandatory = $true)][Object[]]$Diagnostics,
        [Parameter(Mandatory = $true)][string]$Namespace,
        [Parameter(Mandatory = $true)][string]$PlacementType,
        [Parameter(Mandatory = $true)][int]$ExpectedWorkerCount
    )

    $jsonPath = "{0}_unsupported.json" -f $OutputPrefix
    $textPath = "{0}_unsupported.txt" -f $OutputPrefix

    $payload = [ordered]@{
        family = $Family
        scenario = $Scenario
        replica = $Replica
        status = 'unsupported_under_current_constraints'
        namespace = $Namespace
        placementType = $PlacementType
        expectedWorkerCount = $ExpectedWorkerCount
        reason = $Reason
        diagnostics = @($Diagnostics)
    }

    $payload | ConvertTo-Json -Depth 8 | Set-Content -Path $jsonPath -Encoding UTF8

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add('=============================================') | Out-Null
    $lines.Add(' Unsupported Scenario Report') | Out-Null
    $lines.Add('=============================================') | Out-Null
    $lines.Add(("Family                : {0}" -f $Family)) | Out-Null
    $lines.Add(("Scenario              : {0}" -f $Scenario)) | Out-Null
    $lines.Add(("Replica               : {0}" -f $Replica)) | Out-Null
    $lines.Add(("Status                : unsupported_under_current_constraints")) | Out-Null
    $lines.Add(("Namespace             : {0}" -f $Namespace)) | Out-Null
    $lines.Add(("Placement             : {0}" -f $PlacementType)) | Out-Null
    $lines.Add(("Expected worker count : {0}" -f $ExpectedWorkerCount)) | Out-Null
    $lines.Add(("Reason                : {0}" -f $Reason)) | Out-Null
    $lines.Add('') | Out-Null
    $lines.Add('Worker scheduling diagnostics:') | Out-Null

    foreach ($item in @($Diagnostics)) {
        $lines.Add((" - Pod: {0}" -f $item.podName)) | Out-Null
        $lines.Add(("   Phase   : {0}" -f $item.phase)) | Out-Null
        $lines.Add(("   Node    : {0}" -f $(if ([string]::IsNullOrWhiteSpace([string]$item.nodeName)) { '<not-assigned>' } else { [string]$item.nodeName }))) | Out-Null
        if (-not [string]::IsNullOrWhiteSpace([string]$item.reason)) {
            $lines.Add(("   Reason  : {0}" -f $item.reason)) | Out-Null
        }
        foreach ($eventLine in @($item.events)) {
            $lines.Add(("   Event   : {0}" -f $eventLine)) | Out-Null
        }
        $lines.Add('') | Out-Null
    }

    ($lines -join [Environment]::NewLine) | Set-Content -Path $textPath -Encoding UTF8

    return [pscustomobject]@{
        JsonPath = $jsonPath
        TextPath = $textPath
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
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunPhases.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunProtocol.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunClusterCapture.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunPortForward.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunMetricSet.ps1")

if ([string]::IsNullOrWhiteSpace($LocustFile)) { $LocustFile = Join-Path $repoRoot "load-tests\locust\locustfile.py" }
if ([string]::IsNullOrWhiteSpace($OutputRoot)) { $OutputRoot = Join-Path $repoRoot "results\pilot\worker-count" }
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
$workerScenarioData = Get-JsonScenarioConfig `
    -ScenarioName $Scenario `
    -ConfigRoot $WorkerCountScenarioConfigRoot `
    -RequiredProperties @("scenarioId", "purpose", "workerCount", "outputSubdir", "referenceBaselineId")
$workerConfig = $workerScenarioData.RawConfig
$referenceBaselineId = [string]$workerConfig.referenceBaselineId
$workerTopologyDir = if (($workerConfig.PSObject.Properties.Name -contains "topologyDir") -and (-not [string]::IsNullOrWhiteSpace([string]$workerConfig.topologyDir))) {
    [string]$workerConfig.topologyDir
}
else {
    "infra/k8s/compositions/topology/colocated-sc-app-02-{0}" -f $Scenario.ToLowerInvariant()
}

$baselineData = Get-JsonScenarioConfig -ConfigFile $BaselineConfig -RequiredProperties @(
    "baselineId",
    "purpose",
    "modelScenario",
    "resolvedModelName",
    "placementScenario",
    "resolvedPlacementType",
    "workloadScenario",
    "resolvedWorkload",
    "topologyDir",
    "serverManifest",
    "namespaceManifest",
    "storageManifest",
    "prompt",
    "temperature",
    "requestTimeoutSeconds"
)
$baselineConfigData = $baselineData.RawConfig

if ($referenceBaselineId -ne [string]$baselineConfigData.baselineId) {
    throw "Lo scenario worker $Scenario richiede la baseline $referenceBaselineId ma il file fornito espone $($baselineConfigData.baselineId)."
}

$modelScenarioFile = Join-Path $repoRoot ("config\scenarios\pilot\models\{0}.json" -f $baselineConfigData.modelScenario)
$placementScenarioFile = Join-Path $repoRoot ("config\scenarios\pilot\placement\{0}.json" -f $baselineConfigData.placementScenario)
$workloadScenarioFile = Join-Path $WorkloadScenarioConfigRoot ("{0}.json" -f $baselineConfigData.workloadScenario)

$modelScenarioData = Get-JsonScenarioConfig -ConfigFile $modelScenarioFile -RequiredProperties @("scenarioId", "modelName", "serverManifest")
$placementScenarioData = Get-JsonScenarioConfig -ConfigFile $placementScenarioFile -RequiredProperties @("scenarioId", "placementType", "topologyDir")
$workloadScenarioData = Get-JsonScenarioConfig -ConfigFile $workloadScenarioFile -RequiredProperties @("scenarioId", "purpose", "users", "spawnRate", "runTime", "outputSubdir")
$workloadConfig = $workloadScenarioData.RawConfig

if ([string]$modelScenarioData.RawConfig.scenarioId -ne [string]$baselineConfigData.modelScenario -or [string]$modelScenarioData.RawConfig.modelName -ne [string]$baselineConfigData.resolvedModelName -or [string]$modelScenarioData.RawConfig.serverManifest -ne [string]$baselineConfigData.serverManifest) {
    throw "La baseline worker non è coerente con lo scenario model di riferimento."
}

if ([string]$placementScenarioData.RawConfig.scenarioId -ne [string]$baselineConfigData.placementScenario -or [string]$placementScenarioData.RawConfig.placementType -ne [string]$baselineConfigData.resolvedPlacementType -or [string]$placementScenarioData.RawConfig.topologyDir -ne [string]$baselineConfigData.topologyDir) {
    throw "La baseline worker non è coerente con lo scenario placement di riferimento."
}

if ([string]$workloadScenarioData.RawConfig.scenarioId -ne [string]$baselineConfigData.workloadScenario) {
    throw "La baseline worker non è coerente con lo scenario workload di riferimento."
}

if (-not [string]::IsNullOrWhiteSpace($Model) -and $Model -ne [string]$baselineConfigData.resolvedModelName) {
    throw "Il worker count sweep è ancorato alla baseline $($baselineConfigData.baselineId). Il modello richiesto ($Model) non coincide con il modello fisso di baseline ($($baselineConfigData.resolvedModelName))."
}
$Model = [string]$baselineConfigData.resolvedModelName

if (-not [string]::IsNullOrWhiteSpace($Prompt) -and $Prompt -ne [string]$baselineConfigData.prompt) {
    throw "Il worker count sweep è ancorato alla baseline $($baselineConfigData.baselineId). Il prompt richiesto non coincide con il prompt fisso di baseline."
}
$Prompt = [string]$baselineConfigData.prompt

$topologyRoot = Join-Path $repoRoot ($workerTopologyDir -replace '/', '\')
$serverManifest = Join-Path $repoRoot ([string]$baselineConfigData.serverManifest -replace '/', '\')
$namespaceManifest = Join-Path $repoRoot ([string]$baselineConfigData.namespaceManifest -replace '/', '\')
$storageManifest = Join-Path $repoRoot ([string]$baselineConfigData.storageManifest -replace '/', '\')
$topologyTarget = $topologyRoot
$sharedCompositionDir = Join-Path $repoRoot "infra\k8s\compositions\shared\rpc-workers-services"
$k8sApplyTargets = @($namespaceManifest, $sharedCompositionDir, $storageManifest, $topologyTarget, $serverManifest)
foreach ($targetPath in $k8sApplyTargets) {
    if (-not (Test-K8sApplyTarget -Path $targetPath)) { throw "Target Kubernetes non trovato o non valido: $targetPath" }
}

$outputDir = Join-Path $OutputRoot ([string]$workerConfig.outputSubdir)
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

$precheckArgs = @("-ProfileConfig", $PrecheckConfig, "-OutputPrefix", ("{0}_precheck" -f $csvPrefix), "-BaseUrl", $BaseUrl)
if (-not [string]::IsNullOrWhiteSpace($Model)) { $precheckArgs += @("-Model", $Model) }
if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) { $precheckArgs += @("-Kubeconfig", $Kubeconfig) }
if (-not [string]::IsNullOrWhiteSpace($Namespace)) { $precheckArgs += @("-Namespace", $Namespace) }
$apiSmokeArgs = @($apiSmokeScript, "-BaseUrl", $BaseUrl, "-Model", $Model)
$precheckCommand = if (-not $SkipPrecheck) {
    $precheckCommandArgs = @(
        $precheckScript,
        "-ProfileConfig", $PrecheckConfig,
        "-OutputPrefix", ("{0}_precheck" -f $csvPrefix),
        "-BaseUrl", $BaseUrl,
        "-Model", $Model,
        "-Kubeconfig", $Kubeconfig,
        "-Namespace", $Namespace
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }

    New-ProtocolCommandString -Arguments $precheckCommandArgs
}
else {
    ""
}
$apiSmokeCommand = if ($apiSmokeEnabled) {
    $apiSmokeCommandArgs = @(
        $apiSmokeScript,
        "-BaseUrl", $BaseUrl,
        "-Model", $Model
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }

    New-ProtocolCommandString -Arguments $apiSmokeCommandArgs
}
else {
    ""
}

$clusterCapturePreArgs = @(
    "-ProfileConfig", $ClusterCaptureConfig,
    "-OutputPrefix", $clusterCapturePaths.PrePrefix,
    "-Stage", "pre",
    "-Kubeconfig", $Kubeconfig,
    "-Namespace", $Namespace
)
$clusterCapturePreCommandArgs = @(
    $clusterCaptureScript,
    "-ProfileConfig", $ClusterCaptureConfig,
    "-OutputPrefix", $clusterCapturePaths.PrePrefix,
    "-Stage", "pre",
    "-Kubeconfig", $Kubeconfig,
    "-Namespace", $Namespace
) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }

$clusterCapturePreCommand = New-ProtocolCommandString -Arguments $clusterCapturePreCommandArgs

$clusterCapturePostCommandArgs = @(
    $clusterCaptureScript,
    "-ProfileConfig", $ClusterCaptureConfig,
    "-OutputPrefix", $clusterCapturePaths.PostPrefix,
    "-Stage", "post",
    "-Kubeconfig", $Kubeconfig,
    "-Namespace", $Namespace
) | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }

$clusterCapturePostCommand = New-ProtocolCommandString -Arguments $clusterCapturePostCommandArgs

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
Write-MetricSetFiles -MetricSetProfile $metricSetProfile -ManifestPath $metricSetPaths.ManifestPath -TextPath $metricSetPaths.TextPath -LauncherName "Start-PilotWorkerCountSweep" -RunId $runId -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -ClientSourceArtifacts $metricSetClientArtifacts -ClusterSourceArtifacts $metricSetClusterArtifacts

$recommendedApplyOrder = @(
    (Get-K8sApplyCommandString -Path $namespaceManifest),
    (Get-K8sApplyCommandString -Path $sharedCompositionDir),
    (Get-K8sApplyCommandString -Path $storageManifest),
    (Get-K8sApplyCommandString -Path $topologyTarget),
    (Get-K8sApplyCommandString -Path $serverManifest)
)

Write-ProtocolFiles -ProtocolProfile $protocolProfile -ManifestPath $protocolPaths.ManifestPath -TextPath $protocolPaths.TextPath -LauncherName "Start-PilotWorkerCountSweep" -RunId $runId -CleanupNote "Ensure the namespace is in the expected state before applying manifests and running the benchmark." -RecommendedApplyOrder $recommendedApplyOrder -PrecheckEnabled (-not $SkipPrecheck) -PrecheckCommand $precheckCommand -PrecheckJsonPath $protocolPrecheckJsonPath -PrecheckTextPath $protocolPrecheckTextPath -ApiSmokeEnabled $apiSmokeEnabled -ApiSmokeCommand $apiSmokeCommand -ApiSmokeModel $Model -WarmUpEnabled $phasePlan.WarmUpEnabled -WarmUpCommand $warmUpCommand -WarmUpCsvPrefix $phasePlan.WarmUpCsvPrefix -MeasurementCommand $measurementCommand -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -PhaseManifestPath $phasePlan.PhaseManifestPath -ExtraArtifacts @($phasePlan.PhaseManifestPath, $metricSetPaths.ManifestPath, $metricSetPaths.TextPath) -ClusterCollectionEnabled $true -ClusterCollectionCommand $clusterCapturePreCommand -ClusterCollectionArtifacts $clusterCapturePreArtifacts -FinalSnapshotEnabled $true -FinalSnapshotCommand $clusterCapturePostCommand -FinalSnapshotArtifacts $clusterCapturePostArtifacts
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Official Pilot Worker Count Sweep Launcher" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Repository               : $repoRoot"
Write-Host "Worker scenario          : $Scenario"
Write-Host "Replica                  : $Replica"
Write-Host "Run ID                   : $runId"
Write-Host "Purpose                  : $($workerConfig.purpose)"
Write-Host "Worker count             : $($workerConfig.workerCount)"
Write-Host "Worker cfg               : $($workerScenarioData.ConfigFile)"
Write-Host "Reference baseline       : $($baselineConfigData.baselineId)"
Write-Host "Baseline config          : $($baselineData.ConfigFile)"
Write-Host "Baseline purpose         : $($baselineConfigData.purpose)"
Write-Host "Fixed model scenario     : $($baselineConfigData.modelScenario)"
Write-Host "Fixed model              : $Model"
Write-Host "Fixed placement          : $($baselineConfigData.placementScenario) ($($baselineConfigData.resolvedPlacementType))"
Write-Host "Fixed workload           : $($baselineConfigData.workloadScenario)"
Write-Host "Workload cfg             : $($workloadScenarioData.ConfigFile)"
Write-Host "Workload purpose         : $($workloadConfig.purpose)"
Write-Host "Scenario users           : $($workloadConfig.users)"
Write-Host "Scenario spawn rate      : $($workloadConfig.spawnRate)"
Write-Host "Scenario run time        : $($workloadConfig.runTime)"
Write-Host "Topology root            : $topologyRoot"
Write-Host "Server target            : $serverManifest"
Write-Host "Base URL                 : $BaseUrl"
Write-Host "Model                    : $Model"
Write-Host "Prompt                   : $Prompt"
Write-Host "Temperature              : $($baselineConfigData.temperature)"
Write-Host "Request timeout (s)      : $($baselineConfigData.requestTimeoutSeconds)"
Write-Host "Locust file              : $LocustFile"
Write-Host "Output root              : $OutputRoot"
Write-Host "Output dir               : $outputDir"
Write-Host "CSV prefix               : $csvPrefix"
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
Write-Host "Auto-apply Kubernetes    : $AutoApplyK8s"
Write-Host ""
Write-Host "Target Kubernetes raccomandati da applicare prima della run:" -ForegroundColor Yellow
foreach ($manifestPath in $recommendedApplyOrder) {
    Write-Host " - $manifestPath"
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
if ($AutoApplyK8s) {
    Write-Host "Applicazione automatica dei target Kubernetes raccomandati prima della run." -ForegroundColor Yellow
    foreach ($targetPath in $k8sApplyTargets) {
        Invoke-K8sApplyTarget -Path $targetPath -KubeconfigPath $Kubeconfig
    }

    if (-not [string]::IsNullOrWhiteSpace($Namespace)) {
        Write-Host "Attesa schedulazione dei pod worker RPC dopo l'auto-apply..." -ForegroundColor Yellow
        try {
            $scheduledWorkerPods = Wait-ForWorkerPodsScheduled -Namespace $Namespace -ExpectedWorkerCount ([int]$workerConfig.workerCount) -KubeconfigPath $Kubeconfig
            foreach ($pod in $scheduledWorkerPods) {
                $podName = $pod.metadata.name
                $podSpecProperty = $pod.PSObject.Properties['spec']
                $podSpec = if ($null -ne $podSpecProperty) { $podSpecProperty.Value } else { $null }
                $nodeNameProperty = if ($null -ne $podSpec) { $podSpec.PSObject.Properties['nodeName'] } else { $null }
                $nodeName = if ($null -ne $nodeNameProperty) { [string]$nodeNameProperty.Value } else { '<non-assegnato>' }
                Write-Host " - $podName schedulato su $nodeName" -ForegroundColor DarkYellow
            }
        }
        catch {
            $diagnostics = Get-WorkerSchedulingDiagnostics -Namespace $Namespace -KubeconfigPath $Kubeconfig
            $isUnsupported = Test-WorkerScenarioUnsupportedUnderCurrentConstraints -Diagnostics $diagnostics -ExpectedWorkerCount ([int]$workerConfig.workerCount) -PlacementType ([string]$baselineConfigData.resolvedPlacementType)

            if ($isUnsupported) {
                $unsupportedReason = "Scenario worker-count non supportato sotto i vincoli correnti della baseline fissata: il placement '$($baselineConfigData.resolvedPlacementType)' deve restare invariato e, dopo l'auto-apply e il tempo di stabilizzazione previsto, almeno un pod RPC richiesto dallo scenario rimane non schedulabile sul cluster corrente per vincoli di risorse e/o affinity."
                $unsupportedArtifacts = Write-UnsupportedScenarioArtifacts -OutputPrefix $csvPrefix -Scenario $Scenario -Replica $Replica -Family 'worker-count' -Reason $unsupportedReason -Diagnostics $diagnostics -Namespace $Namespace -PlacementType ([string]$baselineConfigData.resolvedPlacementType) -ExpectedWorkerCount ([int]$workerConfig.workerCount)

                Write-Host "" 
                Write-Host "Scenario non supportato sotto i vincoli correnti." -ForegroundColor Yellow
                Write-Host $unsupportedReason -ForegroundColor Yellow
                Write-Host "Report JSON            : $($unsupportedArtifacts.JsonPath)" -ForegroundColor Yellow
                Write-Host "Report text            : $($unsupportedArtifacts.TextPath)" -ForegroundColor Yellow
                exit $UnsupportedScenarioExitCode
            }

            throw
        }
    }

    Ensure-LocalKubernetesPortForward -RepoRoot $repoRoot -BaseUrl $BaseUrl -KubeconfigPath $Kubeconfig -Namespace $Namespace | Out-Null
    Write-Host ""
}

if ($DryRun) {
    Write-Host "DRY RUN completato. Nessun test eseguito." -ForegroundColor Yellow
    exit 0
}

Ensure-LocalKubernetesPortForward -RepoRoot $repoRoot -BaseUrl $BaseUrl -KubeconfigPath $Kubeconfig -Namespace $Namespace | Out-Null

if (-not $SkipPrecheck) {
    & $precheckScript `
        -ProfileConfig $PrecheckConfig `
        -OutputPrefix ("{0}_precheck" -f $csvPrefix) `
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
