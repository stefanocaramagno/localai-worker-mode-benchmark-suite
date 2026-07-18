param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("A", "B", "C")]
    [string]$Replica,

    [string]$BaselineConfig,
    [string]$BenchmarkConfig,
    [string]$BaseUrl,
    [string]$LocustFile,
    [string]$OutputRoot,
    [string]$PrecheckConfig,
    [string]$Kubeconfig,
    [string]$Namespace,
    [string[]]$AdditionalNamespaces,
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
        throw "The JSON file does not exist: $ConfigFile"
    }

    $rawConfig = Get-Content -Path $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json

    foreach ($propertyName in $RequiredProperties) {
        if (-not ($rawConfig.PSObject.Properties.Name -contains $propertyName)) {
            throw "The JSON file '$ConfigFile' does not contain the required property '$propertyName'."
        }
    }

    return [pscustomobject]@{
        ConfigFile = (Resolve-Path $ConfigFile).Path
        RawConfig  = $rawConfig
    }
}


function Test-JsonObjectProperty {
    param(
        [Parameter(Mandatory = $true)]
        [object]$JsonObject,
        [Parameter(Mandatory = $true)]
        [string]$PropertyName
    )

    return $JsonObject.PSObject.Properties.Name -contains $PropertyName
}

function Resolve-RepositoryPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$PathValue
    )

    if ([System.IO.Path]::IsPathRooted($PathValue)) { return $PathValue }
    return Join-Path $RepoRoot ($PathValue -replace '/', '\')
}


function ConvertTo-ArtifactPortableString {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [AllowNull()][string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) { return $Value }
    $portableValue = ([string]$Value) -replace '\\', '/'
    if ($portableValue.Trim() -match '^[A-Za-z][A-Za-z0-9+.-]*://') { return [string]$Value }

    $rootValue = ((Resolve-Path $RepositoryRoot).Path -replace '\\', '/').TrimEnd('/')
    if (-not [string]::IsNullOrWhiteSpace($rootValue)) {
        $portableValue = [System.Text.RegularExpressions.Regex]::Replace(
            $portableValue,
            [System.Text.RegularExpressions.Regex]::Escape($rootValue),
            '.',
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
    }

    $marker = '/localai-worker-mode-benchmark-suite/'
    $markerIndex = $portableValue.IndexOf($marker, [System.StringComparison]::OrdinalIgnoreCase)
    if ($markerIndex -ge 0) {
        $portableValue = $portableValue.Substring($markerIndex + $marker.Length)
    }

    while ($portableValue.StartsWith('./')) {
        $portableValue = $portableValue.Substring(2)
    }

    return $portableValue
}


function Get-OptionalJsonStringProperty {
    param(
        [Parameter(Mandatory = $true)]
        [object]$JsonObject,
        [Parameter(Mandatory = $true)]
        [string[]]$PropertyNames
    )

    foreach ($propertyName in $PropertyNames) {
        if (Test-JsonObjectProperty -JsonObject $JsonObject -PropertyName $propertyName) {
            $candidate = [string]$JsonObject.$propertyName
            if (-not [string]::IsNullOrWhiteSpace($candidate)) { return $candidate }
        }
    }

    return $null
}


function Add-NamespaceCandidate {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[string]]$Target,
        [AllowNull()][object]$Value
    )

    if ($null -eq $Value) { return }

    if ($Value -is [string]) {
        $items = ([string]$Value).Split(",", [System.StringSplitOptions]::RemoveEmptyEntries)
    }
    elseif ($Value -is [System.Collections.IEnumerable]) {
        $items = @($Value)
    }
    else {
        $items = @($Value)
    }

    foreach ($item in $items) {
        if ($null -eq $item) { continue }
        $text = ([string]$item).Trim()
        if ([string]::IsNullOrWhiteSpace($text)) { continue }
        if (-not $Target.Contains($text)) {
            $Target.Add($text) | Out-Null
        }
    }
}

function Resolve-BenchmarkNamespaces {
    param(
        [Parameter(Mandatory = $true)][object]$Scenario,
        [AllowNull()][string]$NamespaceOverride,
        [AllowNull()][string[]]$AdditionalNamespaceOverrides
    )

    $candidates = [System.Collections.Generic.List[string]]::new()

    if (-not [string]::IsNullOrWhiteSpace($NamespaceOverride)) {
        Add-NamespaceCandidate -Target $candidates -Value $NamespaceOverride
    }
    elseif (Test-JsonObjectProperty -JsonObject $Scenario -PropertyName "namespace") {
        Add-NamespaceCandidate -Target $candidates -Value $Scenario.namespace
    }
    elseif ((Test-JsonObjectProperty -JsonObject $Scenario -PropertyName "applicationTopology") -and $null -ne $Scenario.applicationTopology -and (Test-JsonObjectProperty -JsonObject $Scenario.applicationTopology -PropertyName "namespace")) {
        Add-NamespaceCandidate -Target $candidates -Value $Scenario.applicationTopology.namespace
    }
    elseif ((Test-JsonObjectProperty -JsonObject $Scenario -PropertyName "tenancyVariant") -and $null -ne $Scenario.tenancyVariant -and (Test-JsonObjectProperty -JsonObject $Scenario.tenancyVariant -PropertyName "benchmarkNamespace")) {
        Add-NamespaceCandidate -Target $candidates -Value $Scenario.tenancyVariant.benchmarkNamespace
    }
    else {
        Add-NamespaceCandidate -Target $candidates -Value "localai-benchmark"
    }

    Add-NamespaceCandidate -Target $candidates -Value $AdditionalNamespaceOverrides

    if (Test-JsonObjectProperty -JsonObject $Scenario -PropertyName "additionalNamespaces") {
        Add-NamespaceCandidate -Target $candidates -Value $Scenario.additionalNamespaces
    }

    if (Test-JsonObjectProperty -JsonObject $Scenario -PropertyName "tenantClusters") {
        foreach ($tenantCluster in @($Scenario.tenantClusters)) {
            if ($null -ne $tenantCluster -and (Test-JsonObjectProperty -JsonObject $tenantCluster -PropertyName "namespace")) {
                Add-NamespaceCandidate -Target $candidates -Value $tenantCluster.namespace
            }
        }
    }

    if ((Test-JsonObjectProperty -JsonObject $Scenario -PropertyName "applicationTopology") -and $null -ne $Scenario.applicationTopology) {
        $topology = $Scenario.applicationTopology
        if (Test-JsonObjectProperty -JsonObject $topology -PropertyName "additionalNamespaces") {
            Add-NamespaceCandidate -Target $candidates -Value $topology.additionalNamespaces
        }
        if (Test-JsonObjectProperty -JsonObject $topology -PropertyName "additionalRolloutTargets") {
            foreach ($target in @($topology.additionalRolloutTargets)) {
                if ($null -ne $target -and (Test-JsonObjectProperty -JsonObject $target -PropertyName "namespace")) {
                    Add-NamespaceCandidate -Target $candidates -Value $target.namespace
                }
            }
        }
    }

    $primary = $candidates[0]
    $all = @($candidates.ToArray())
    $additional = @($all | Where-Object { $_ -ne $primary })

    return [pscustomobject]@{
        PrimaryNamespace = $primary
        Namespaces = $all
        AdditionalNamespaces = $additional
    }
}

function ConvertTo-NullableDouble {
    param([object]$Value)

    if ($null -eq $Value) { return $null }
    $text = ([string]$Value).Trim()
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    $number = 0.0
    if ([double]::TryParse($text, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$number)) {
        return $number
    }
    if ([double]::TryParse($text, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::CurrentCulture, [ref]$number)) {
        return $number
    }
    return $null
}

function Test-LocustMeasurementTargetRequests {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StatsCsvPath,
        [string]$TargetType = "POST",
        [string]$TargetName = "POST /v1/chat/completions"
    )

    $result = [ordered]@{
        Valid = $false
        Reason = "measurement_stats_csv_missing"
        StatsCsvPath = $StatsCsvPath
        TargetType = $TargetType
        TargetName = $TargetName
        TargetRequestCount = 0
        AggregatedRequestCount = 0
    }

    if (-not (Test-Path -Path $StatsCsvPath -PathType Leaf)) {
        return [pscustomobject]$result
    }

    $rows = Import-Csv -Path $StatsCsvPath -Encoding UTF8
    $targetRow = $null
    $aggregatedRow = $null
    foreach ($row in $rows) {
        $rowType = ([string]$row.Type).Trim()
        $rowName = ([string]$row.Name).Trim()
        if ($rowName -eq "Aggregated") { $aggregatedRow = $row }
        if ($rowType -eq $TargetType -and $rowName -eq $TargetName) { $targetRow = $row }
    }

    if ($null -ne $aggregatedRow) {
        $aggregatedCount = ConvertTo-NullableDouble $aggregatedRow.'Request Count'
        if ($null -ne $aggregatedCount) { $result.AggregatedRequestCount = [int][Math]::Round($aggregatedCount) }
    }

    if ($null -eq $targetRow) {
        $result.Reason = "measurement_missing_target_request_row"
        return [pscustomobject]$result
    }

    $targetCount = ConvertTo-NullableDouble $targetRow.'Request Count'
    if ($null -eq $targetCount -or $targetCount -le 0) {
        $result.Reason = "measurement_produced_zero_valid_requests"
        return [pscustomobject]$result
    }

    $result.Valid = $true
    $result.Reason = "measurement_contains_valid_target_requests"
    $result.TargetRequestCount = [int][Math]::Round($targetCount)
    return [pscustomobject]$result
}

function Write-MeasurementUnsupportedEvidence {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OutputPath,
        [Parameter(Mandatory = $true)]
        [object]$BaselineScenario,
        [Parameter(Mandatory = $true)]
        [string]$Replica,
        [Parameter(Mandatory = $true)]
        [string]$Reason,
        [Parameter(Mandatory = $true)]
        [object]$MeasurementValidation,
        [object]$LatencyVariant,
        [int]$UnsupportedExitCode = 42,
        [AllowNull()][string]$RepositoryRoot
    )

    $latencyProfileId = $null
    if ($null -ne $LatencyVariant -and ($LatencyVariant.PSObject.Properties.Name -contains "latencyProfileId")) {
        $latencyProfileId = [string]$LatencyVariant.latencyProfileId
    }

    $scenarioFamily = "provider-backed"
    if ($BaselineScenario.PSObject.Properties.Name -contains "family" -and -not [string]::IsNullOrWhiteSpace([string]$BaselineScenario.family)) {
        $scenarioFamily = [string]$BaselineScenario.family
    }
    $scenarioFamilyEvidenceKind = $scenarioFamily.Replace("-", "_")

    $displayStatsCsvPath = if (-not [string]::IsNullOrWhiteSpace($RepositoryRoot)) {
        ConvertTo-ArtifactPortableString -RepositoryRoot $RepositoryRoot -Value ([string]$MeasurementValidation.StatsCsvPath)
    }
    else {
        [string]$MeasurementValidation.StatsCsvPath
    }

    $payload = [ordered]@{
        family = $scenarioFamily
        scenario = [string]$BaselineScenario.baselineId
        scenarioId = [string]$BaselineScenario.baselineId
        replica = $Replica
        status = "unsupported_under_current_constraints"
        namespace = [string]$BaselineScenario.namespace
        placementType = [string]$BaselineScenario.resolvedPlacementType
        expectedWorkerCount = [int]$BaselineScenario.resolvedWorkerCount
        reason = $Reason
        stage = "measurement_validation"
        evidence = [ordered]@{
            classificationRule = "locust_measurement_finished_without_valid_target_requests"
            failureClass = "measurement_produced_no_valid_target_requests"
            statsCsvPath = $displayStatsCsvPath
            targetType = [string]$MeasurementValidation.TargetType
            targetName = [string]$MeasurementValidation.TargetName
            targetRequestCount = [int]$MeasurementValidation.TargetRequestCount
            aggregatedRequestCount = [int]$MeasurementValidation.AggregatedRequestCount
            locustExitCode = 0
            unsupportedExitCode = $UnsupportedExitCode
        }
        evidenceKinds = @("measurement_validation", $Reason, "no_valid_target_requests", $scenarioFamilyEvidenceKind)
        schedulerEvidence = @{}
        diagnostics = @()
        latencyVariant = $LatencyVariant
        latencyProfileId = $latencyProfileId
        timeoutSeconds = [int]$BaselineScenario.requestTimeoutSeconds
        model = [string]$BaselineScenario.resolvedModelName
    }

    $parent = Split-Path -Path $OutputPath -Parent
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    Write-PortableArtifactJson -Path $OutputPath -Payload $payload -Depth 20
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
    throw "Invalid or unresolved Kubernetes target: $Path"
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
        [string]$RunId,
        [AllowNull()][string]$RepositoryRoot
    )

    $displayBaselineConfigPath = if (-not [string]::IsNullOrWhiteSpace($RepositoryRoot)) {
        ConvertTo-ArtifactPortableString -RepositoryRoot $RepositoryRoot -Value $BaselineConfigPath
    }
    else {
        $BaselineConfigPath
    }
    $displayTopologyDir = if (-not [string]::IsNullOrWhiteSpace($RepositoryRoot)) {
        ConvertTo-ArtifactPortableString -RepositoryRoot $RepositoryRoot -Value $TopologyDir
    }
    else {
        $TopologyDir
    }
    $displayServerManifest = if (-not [string]::IsNullOrWhiteSpace($RepositoryRoot)) {
        ConvertTo-ArtifactPortableString -RepositoryRoot $RepositoryRoot -Value $ServerManifest
    }
    else {
        $ServerManifest
    }

    $payload = [ordered]@{
        baselineConfig = $displayBaselineConfigPath
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
            topologyDir = $displayTopologyDir
            serverManifest = $displayServerManifest
            baseUrl = $BaseUrl
            prompt = $Prompt
            requestTimeoutSeconds = $RequestTimeoutSeconds
            temperature = $Temperature
            warmUpDuration = $WarmUpDuration
            measurementDuration = $MeasurementDuration
        }
        runId = $RunId
    }

    Write-PortableArtifactJson -Path $OutputPath -Payload $payload -Depth 12
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunPhases.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunProtocol.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunClusterCapture.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunPortForward.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunMetricSet.ps1")

if (-not [string]::IsNullOrWhiteSpace($BenchmarkConfig)) {
    $BaselineConfig = $BenchmarkConfig
}

if ([string]::IsNullOrWhiteSpace($BaselineConfig)) {
    $BaselineConfig = Join-Path $repoRoot "config\scenarios\baseline\B0.json"
}

if ([string]::IsNullOrWhiteSpace($LocustFile)) {
    $LocustFile = Join-Path $repoRoot "load-tests\locust\locustfile.py"
}

$precheckConfigProvidedExplicitly = -not [string]::IsNullOrWhiteSpace($PrecheckConfig)

if ([string]::IsNullOrWhiteSpace($PhaseConfig)) {
    $PhaseConfig = Join-Path $repoRoot "config\phases\profiles\WM_STANDARD_WARMUP_MEASUREMENT.json"
}

if ([string]::IsNullOrWhiteSpace($ProtocolConfig)) {
    $ProtocolConfig = Join-Path $repoRoot "config\protocol\profiles\EP_STANDARD_BENCHMARK_PROTOCOL.json"
}

if ([string]::IsNullOrWhiteSpace($ClusterCaptureConfig)) {
    $ClusterCaptureConfig = Join-Path $repoRoot "config\cluster-capture\profiles\CS_STANDARD_CLUSTER_CAPTURE.json"
}

if ([string]::IsNullOrWhiteSpace($MetricSetConfig)) {
    $MetricSetConfig = Join-Path $repoRoot "config\metric-set\profiles\MS_STANDARD_BENCHMARK_METRICS.json"
}

if ([string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $Kubeconfig = Join-Path $repoRoot "config\cluster-access\fixed-cluster\kubeconfig"
}

if (-not (Test-Path $BaselineConfig)) {
    throw "The benchmark configuration file does not exist: $BaselineConfig"
}

if (-not (Test-Path $LocustFile)) {
    throw "The specified Locust file does not exist: $LocustFile"
}

if (-not (Test-Path $PhaseConfig)) {
    throw "The warm-up/measurement profile file does not exist: $PhaseConfig"
}

if (-not (Test-Path $ProtocolConfig)) {
    throw "The protocol file does not exist: $ProtocolConfig"
}

if (-not (Test-Path $ClusterCaptureConfig)) {
    throw "The cluster-side collection file does not exist: $ClusterCaptureConfig"
}

if (-not (Test-Path $MetricSetConfig)) {
    throw "The metric-set file does not exist: $MetricSetConfig"
}

if (-not (Test-Path $Kubeconfig)) {
    throw "The specified kubeconfig file does not exist: $Kubeconfig"
}

$precheckScript = Join-Path $repoRoot "scripts\validation\precheck\Invoke-BenchmarkPrecheck.ps1"
$clusterCaptureScript = Join-Path $repoRoot "scripts\validation\cluster-side\Collect-ClusterSideArtifacts.ps1"

if (-not (Test-Path $clusterCaptureScript)) {
    throw "The cluster-side collection script does not exist: $clusterCaptureScript"
}

if (-not $SkipPrecheck -and -not (Test-Path $precheckScript)) {
    throw "The pre-check script does not exist: $precheckScript"
}

if (-not $DryRun -and -not (Test-CommandAvailable -CommandName "locust")) {
    throw "Locust is not available in PATH. Install Locust or verify the Python environment."
}

$phaseProfile = Get-PhaseProfile -ProfileFile $PhaseConfig
$protocolProfile = Get-ProtocolProfile -ProfileFile $ProtocolConfig
$clusterCaptureProfile = Get-ClusterCaptureProfile -ProfileFile $ClusterCaptureConfig
$metricSetProfile = Get-MetricSetProfile -ProfileFile $MetricSetConfig
$apiSmokeScript = Join-Path $repoRoot $protocolProfile.ApiSmokeScriptRelativePathPowerShell
$apiSmokeEnabled = $protocolProfile.ApiSmokeEnabledDefault -and (-not $SkipApiSmoke)
if ($apiSmokeEnabled -and -not (Test-Path $apiSmokeScript)) {
    throw "The API smoke script does not exist: $apiSmokeScript"
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
$namespaceResolution = Resolve-BenchmarkNamespaces -Scenario $baselineScenario -NamespaceOverride $Namespace -AdditionalNamespaceOverrides $AdditionalNamespaces
$Namespace = $namespaceResolution.PrimaryNamespace
$clusterCaptureNamespaces = @($namespaceResolution.Namespaces)
$clusterCaptureAdditionalNamespaces = @($namespaceResolution.AdditionalNamespaces)

$isProviderBoundBaseline = (Test-JsonObjectProperty -JsonObject $baselineScenario -PropertyName "providerBindingId") -or (Test-JsonObjectProperty -JsonObject $baselineScenario -PropertyName "infrastructureProfileId")

if (-not $precheckConfigProvidedExplicitly) {
    $candidatePrecheckPath = $null
    foreach ($propertyName in @("precheckProfilePath", "precheckConfigPath", "precheckConfig")) {
        if ($baselineScenario.PSObject.Properties.Name -contains $propertyName) {
            $candidateValue = [string]$baselineScenario.$propertyName
            if (-not [string]::IsNullOrWhiteSpace($candidateValue)) {
                $candidatePrecheckPath = $candidateValue
                break
            }
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($candidatePrecheckPath)) {
        if ([System.IO.Path]::IsPathRooted($candidatePrecheckPath)) {
            $PrecheckConfig = $candidatePrecheckPath
        }
        else {
            $PrecheckConfig = Join-Path $repoRoot ($candidatePrecheckPath -replace '/', '\')
        }
    }
    else {
        $PrecheckConfig = Join-Path $repoRoot "config\precheck\profiles\TC_C0_HISTORICAL_FIXED_CLUSTER.json"
    }
}

if (-not $SkipPrecheck -and -not (Test-Path $PrecheckConfig)) {
    throw "The pre-check profile file does not exist: $PrecheckConfig"
}

$modelScenarioFile = Join-Path $repoRoot ("config\scenarios\pilot\models\{0}.json" -f $baselineScenario.modelScenario)
$workerScenarioFile = Join-Path $repoRoot ("config\scenarios\pilot\worker-count\{0}.json" -f $baselineScenario.workerScenario)
$placementScenarioFile = Join-Path $repoRoot ("config\scenarios\pilot\placement\{0}.json" -f $baselineScenario.placementScenario)
if ($isProviderBoundBaseline) {
    $modernPlacementPath = Get-OptionalJsonStringProperty -JsonObject $baselineScenario -PropertyNames @("placementScenarioPath", "placementProfilePath")
    if (-not [string]::IsNullOrWhiteSpace($modernPlacementPath)) {
        $placementScenarioFile = Resolve-RepositoryPath -RepoRoot $repoRoot -PathValue $modernPlacementPath
    }
}
$workloadScenarioFile = Join-Path $repoRoot ("config\scenarios\pilot\workload\{0}.json" -f $baselineScenario.workloadScenario)

$modelScenarioData = Get-JsonScenarioConfig -ConfigFile $modelScenarioFile -RequiredProperties @("scenarioId", "modelName", "serverManifest")
$workerScenarioData = Get-JsonScenarioConfig -ConfigFile $workerScenarioFile -RequiredProperties @("scenarioId", "workerCount")
if ($isProviderBoundBaseline) {
    if (-not (Test-Path $placementScenarioFile)) {
        throw "The placement profile/scenario file does not exist: $placementScenarioFile"
    }
    $placementRawConfig = Get-Content -Path $placementScenarioFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $placementIdentifier = Get-OptionalJsonStringProperty -JsonObject $placementRawConfig -PropertyNames @("scenarioId", "placementProfileId", "profileId")
    if ([string]::IsNullOrWhiteSpace($placementIdentifier)) {
        throw "The placement file '$placementScenarioFile' does not contain scenarioId, placementProfileId, or profileId."
    }
    $expectedPlacementIdentifiers = @([string]$baselineScenario.placementScenario)
    $baselinePlacementProfileId = Get-OptionalJsonStringProperty -JsonObject $baselineScenario -PropertyNames @("placementProfileId")
    if (-not [string]::IsNullOrWhiteSpace($baselinePlacementProfileId)) { $expectedPlacementIdentifiers += $baselinePlacementProfileId }
    if ($expectedPlacementIdentifiers -notcontains $placementIdentifier) {
        throw "Baseline/placement mismatch: '$placementIdentifier' does not match '$($baselineScenario.placementScenario)'."
    }
    $placementScenarioData = [pscustomobject]@{
        ConfigFile = (Resolve-Path $placementScenarioFile).Path
        RawConfig = $placementRawConfig
    }
}
else {
    $placementScenarioData = Get-JsonScenarioConfig -ConfigFile $placementScenarioFile -RequiredProperties @("scenarioId", "placementType", "topologyDir")
}
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
        throw "Kubernetes target not found or invalid: $targetPath"
    }
}

$runId = "{0}_run{1}" -f [string]$baselineScenario.baselineId, $Replica
$outputSubdir = Get-OptionalJsonStringProperty -JsonObject $baselineScenario -PropertyNames @("outputSubdir", "benchmarkOutputSubdir")
if ([string]::IsNullOrWhiteSpace($outputSubdir)) {
    $outputSubdir = "{0}_official_locked" -f [string]$baselineScenario.baselineId
}
$outputDir = Join-Path $resolvedOutputRoot $outputSubdir
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

$csvPrefix = Join-Path $outputDir $runId
$phasePlan = New-PhasePlan -PhaseProfile $phaseProfile -MeasurementUsers ([int]$workloadScenarioData.RawConfig.users) -MeasurementSpawnRate ([int]$workloadScenarioData.RawConfig.spawnRate) -ScenarioMeasurementDuration ([string]$workloadScenarioData.RawConfig.runTime) -MeasurementCsvPrefix $csvPrefix -WarmUpDurationOverride $WarmUpDuration -MeasurementDurationOverride $MeasurementDuration -SkipWarmUp:$SkipWarmUp
Write-PhaseManifest -PhasePlan $phasePlan -OutputPath $phasePlan.PhaseManifestPath -RepositoryRoot $repoRoot
$protocolPaths = Get-ProtocolPaths -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -ProtocolProfile $protocolProfile
$clusterCapturePaths = Get-ClusterCaptureStagePaths -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -ClusterCaptureProfile $clusterCaptureProfile
$metricSetPaths = Get-MetricSetPaths -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -MetricSetProfile $metricSetProfile
$metricSetClientArtifacts = Get-MetricSetClientArtifactList -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix
$metricSetClusterArtifacts = Get-MetricSetClusterArtifactList -PreStagePrefix $clusterCapturePaths.PrePrefix -PostStagePrefix $clusterCapturePaths.PostPrefix -ClusterCaptureProfile $clusterCaptureProfile -Namespaces $clusterCaptureNamespaces

$runLockFile = Join-Path $outputDir ("{0}_baseline-lock.json" -f $runId)
$precheckOutputPrefix = "{0}_precheck" -f $csvPrefix
$precheckJsonPath = "{0}_precheck.json" -f $precheckOutputPrefix
$precheckTextPath = "{0}_precheck.txt" -f $precheckOutputPrefix

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
    -RunId $runId `
    -RepositoryRoot $repoRoot

$precheckCommandPreview = "$precheckScript -ProfileConfig $PrecheckConfig -BaseUrl $resolvedBaseUrl -Model $([string]$baselineScenario.resolvedModelName) -OutputPrefix $precheckOutputPrefix -Kubeconfig $Kubeconfig -Namespace $Namespace"

$scenarioFamily = Get-OptionalJsonStringProperty -JsonObject $baselineScenario -PropertyNames @("family")
$latencyVariantEnabled = $false
if (Test-JsonObjectProperty -JsonObject $baselineScenario -PropertyName "latencyVariant") {
    $latencyVariant = $baselineScenario.latencyVariant
    if ($null -ne $latencyVariant -and ($latencyVariant.PSObject.Properties.Name -contains "enabled")) {
        $latencyVariantEnabled = [System.Convert]::ToBoolean($latencyVariant.enabled)
    }
}
$apiSmokeUnsupportedExitCode = 42
$apiSmokeTimeoutAsUnsupported = ($scenarioFamily -eq "latency-injection") -and $latencyVariantEnabled
$apiSmokeInvocationArgs = @(
    "-BaseUrl", $resolvedBaseUrl,
    "-Model", ([string]$baselineScenario.resolvedModelName),
    "-RequestTimeoutSeconds", ([string][int]$baselineScenario.requestTimeoutSeconds)
)
$apiSmokeInvocationParams = @{
    BaseUrl = [string]$resolvedBaseUrl
    Model = [string]$baselineScenario.resolvedModelName
    RequestTimeoutSeconds = [int]$baselineScenario.requestTimeoutSeconds
}
if ($apiSmokeTimeoutAsUnsupported) {
    $apiSmokeInvocationArgs += @("-ExitUnsupportedOnTimeout", "-UnsupportedExitCode", ([string]$apiSmokeUnsupportedExitCode))
    $apiSmokeInvocationParams["ExitUnsupportedOnTimeout"] = $true
    $apiSmokeInvocationParams["UnsupportedExitCode"] = [int]$apiSmokeUnsupportedExitCode
}
$apiSmokeArgs = @($apiSmokeScript) + $apiSmokeInvocationArgs
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

$clusterCapturePreInvokeParams = @{
    ProfileConfig = $ClusterCaptureConfig
    Kubeconfig    = $Kubeconfig
    Namespace     = $Namespace
    OutputPrefix  = $clusterCapturePaths.PrePrefix
    Stage         = "pre"
}

$clusterCapturePostInvokeParams = @{
    ProfileConfig = $ClusterCaptureConfig
    Kubeconfig    = $Kubeconfig
    Namespace     = $Namespace
    OutputPrefix  = $clusterCapturePaths.PostPrefix
    Stage         = "post"
}

if ($clusterCaptureAdditionalNamespaces.Count -gt 0) {
    $additionalNamespaceCsv = ($clusterCaptureAdditionalNamespaces -join ",")
    $clusterCapturePreArgs += @("-AdditionalNamespaces", $additionalNamespaceCsv)
    $clusterCapturePostArgs += @("-AdditionalNamespaces", $additionalNamespaceCsv)
    $clusterCapturePreInvokeParams.AdditionalNamespaces = [string[]]$clusterCaptureAdditionalNamespaces
    $clusterCapturePostInvokeParams.AdditionalNamespaces = [string[]]$clusterCaptureAdditionalNamespaces
}

$clusterCapturePreCommand = New-ProtocolCommandString -Arguments (@($clusterCaptureScript) + $clusterCapturePreArgs)
$clusterCapturePostCommand = New-ProtocolCommandString -Arguments (@($clusterCaptureScript) + $clusterCapturePostArgs)
$clusterCapturePreArtifacts = Get-ClusterCaptureArtifactList -StagePrefix $clusterCapturePaths.PrePrefix -ClusterCaptureProfile $clusterCaptureProfile -Namespaces $clusterCaptureNamespaces
$clusterCapturePostArtifacts = Get-ClusterCaptureArtifactList -StagePrefix $clusterCapturePaths.PostPrefix -ClusterCaptureProfile $clusterCaptureProfile -Namespaces $clusterCaptureNamespaces

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

Write-MetricSetFiles -MetricSetProfile $metricSetProfile -ManifestPath $metricSetPaths.ManifestPath -TextPath $metricSetPaths.TextPath -LauncherName "Start-OfficialBaseline" -RunId $runId -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -ClientSourceArtifacts $metricSetClientArtifacts -ClusterSourceArtifacts $metricSetClusterArtifacts -RepositoryRoot $repoRoot
Write-ProtocolFiles -ProtocolProfile $protocolProfile -ManifestPath $protocolPaths.ManifestPath -TextPath $protocolPaths.TextPath -LauncherName "Start-OfficialBaseline" -RunId $runId -CleanupNote "Ensure the namespace is in the expected state before applying manifests and running the benchmark." -RecommendedApplyOrder $recommendedApplyOrder -PrecheckEnabled (-not $SkipPrecheck) -PrecheckCommand $precheckCommand -PrecheckJsonPath $protocolPrecheckJsonPath -PrecheckTextPath $protocolPrecheckTextPath -ApiSmokeEnabled $apiSmokeEnabled -ApiSmokeCommand $apiSmokeCommand -ApiSmokeModel ([string]$baselineScenario.resolvedModelName) -WarmUpEnabled $phasePlan.WarmUpEnabled -WarmUpCommand $warmUpCommand -WarmUpCsvPrefix $phasePlan.WarmUpCsvPrefix -MeasurementCommand $measurementCommand -MeasurementCsvPrefix $phasePlan.MeasurementCsvPrefix -PhaseManifestPath $phasePlan.PhaseManifestPath -ExtraArtifacts @($phasePlan.PhaseManifestPath, $runLockFile, $metricSetPaths.ManifestPath, $metricSetPaths.TextPath) -ClusterCollectionEnabled $true -ClusterCollectionCommand $clusterCapturePreCommand -ClusterCollectionArtifacts $clusterCapturePreArtifacts -FinalSnapshotEnabled $true -FinalSnapshotCommand $clusterCapturePostCommand -FinalSnapshotArtifacts $clusterCapturePostArtifacts -RepositoryRoot $repoRoot

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
Write-Host "Additional namespaces    : $(if ($clusterCaptureAdditionalNamespaces.Count -gt 0) { $clusterCaptureAdditionalNamespaces -join ', ' } else { '-' })"
if ($SkipPrecheck) { Write-Host "Pre-check                : disabled" } else { Write-Host "Pre-check                : $PrecheckConfig" }
Write-Host ""
Write-Host "Recommended Kubernetes targets to apply before the run:" -ForegroundColor Yellow
foreach ($manifestPath in $recommendedApplyOrder) { Write-Host " - $manifestPath" }
Write-Host ""
if (-not $SkipPrecheck) {
    Write-Host "Pre-check command:" -ForegroundColor Yellow
    Write-Host $precheckCommandPreview
    Write-Host ""
}
Write-Host "Cluster capture command (pre):" -ForegroundColor Yellow
Write-Host $clusterCapturePreCommand
Write-Host ""
Write-Host "Cluster capture command (post):" -ForegroundColor Yellow
Write-Host $clusterCapturePostCommand
Write-Host ""
if ($apiSmokeEnabled) {
    Write-Host "API smoke command:" -ForegroundColor Yellow
    Write-Host $apiSmokeCommand
    Write-Host ""
}
if ($phasePlan.WarmUpEnabled) {
    Write-Host "Warm-up command:" -ForegroundColor Yellow
    Write-Host ("locust " + ($warmUpLocustArgs -join " "))
    Write-Host ""
}
else {
    Write-Host "Warm-up                : disabled"
    Write-Host ""
}
Write-Host "Measurement command:" -ForegroundColor Yellow
Write-Host ("locust " + ($measurementLocustArgs -join " "))
Write-Host ""

if ($DryRun) {
    Write-Host "DRY RUN completed. No tests were executed." -ForegroundColor Yellow
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
        Write-Host "Pre-check finished with FAIL (exit code $precheckExitCode). The run is stopped without executing smoke, warm-up, or measurement." -ForegroundColor Red
        exit $precheckExitCode
    }
}

& $clusterCaptureScript @clusterCapturePreInvokeParams

if ($apiSmokeEnabled) {
    & $apiSmokeScript @apiSmokeInvocationParams
    $apiSmokeExitCode = $LASTEXITCODE
    if ($apiSmokeExitCode -eq $apiSmokeUnsupportedExitCode -and $apiSmokeTimeoutAsUnsupported) {
        Write-Host ("API smoke finished with a controlled unsupported scenario (exit code {0}). Warm-up and measurement are skipped as experimental evidence." -f $apiSmokeExitCode) -ForegroundColor Yellow
        exit $apiSmokeExitCode
    }
    if ($apiSmokeExitCode -ne 0) {
        Write-Host "API smoke finished with FAIL (exit code $apiSmokeExitCode). The run is stopped without executing warm-up or measurement." -ForegroundColor Red
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

& $clusterCaptureScript @clusterCapturePostInvokeParams

$clusterCapturePostExitCode = $LASTEXITCODE

$measurementValidation = $null
if ($exitCode -eq 0 -and $clusterCapturePostExitCode -eq 0) {
    $measurementStatsCsv = "{0}_stats.csv" -f $phasePlan.MeasurementCsvPrefix
    $measurementValidation = Test-LocustMeasurementTargetRequests -StatsCsvPath $measurementStatsCsv
    if (-not $measurementValidation.Valid) {
        if ($apiSmokeTimeoutAsUnsupported) {
            $unsupportedJsonPath = "{0}_unsupported.json" -f $phasePlan.MeasurementCsvPrefix
            Write-MeasurementUnsupportedEvidence `
                -OutputPath $unsupportedJsonPath `
                -BaselineScenario $baselineScenario `
                -Replica $Replica `
                -Reason $measurementValidation.Reason `
                -MeasurementValidation $measurementValidation `
                -LatencyVariant $latencyVariant `
                -UnsupportedExitCode $apiSmokeUnsupportedExitCode `
                -RepositoryRoot $repoRoot
            Write-Host "CONTROLLED UNSUPPORTED SCENARIO DETECTED." -ForegroundColor Yellow
            Write-Host ("The Locust measurement completed without valid target requests for {0}." -f $measurementValidation.TargetName) -ForegroundColor Yellow
            Write-Host ("Reason: {0}." -f $measurementValidation.Reason) -ForegroundColor Yellow
            Write-Host ("The generated CSV is retained as diagnostic evidence: {0}" -f $measurementValidation.StatsCsvPath) -ForegroundColor Yellow
            Write-Host ("Unsupported evidence: {0}" -f $unsupportedJsonPath) -ForegroundColor Yellow
            exit $apiSmokeUnsupportedExitCode
        }
        Write-Host "The Locust measurement completed without valid target requests." -ForegroundColor Red
        Write-Host ("Reason: {0}." -f $measurementValidation.Reason) -ForegroundColor Red
        Write-Host ("Measurement CSV: {0}" -f $measurementValidation.StatsCsvPath) -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
if ($exitCode -eq 0 -and $clusterCapturePostExitCode -eq 0) {
    Write-Host "Run completed successfully." -ForegroundColor Green
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
        Write-Host "The Locust run finished with exit code $exitCode." -ForegroundColor Red
        exit $exitCode
    }
    Write-Host "The final cluster-side collection finished with exit code $clusterCapturePostExitCode." -ForegroundColor Red
    exit $clusterCapturePostExitCode
}
