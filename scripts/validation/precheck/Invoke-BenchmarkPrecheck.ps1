param(
    [string]$ProfileConfig,
    [string]$Kubeconfig,
    [string]$Namespace,
    [string]$OutputPrefix,
    [string]$BaseUrl,
    [string]$Model
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


function Test-JsonObjectProperty {
    param(
        [Parameter(Mandatory = $true)]
        [AllowNull()]
        [object]$JsonObject,
        [Parameter(Mandatory = $true)]
        [string]$PropertyName
    )

    if ($null -eq $JsonObject) { return $false }
    return ($JsonObject.PSObject.Properties.Name -contains $PropertyName)
}

function Get-JsonObjectPropertyValue {
    param(
        [Parameter(Mandatory = $true)]
        [AllowNull()]
        [object]$JsonObject,
        [Parameter(Mandatory = $true)]
        [string]$PropertyName,
        [object]$DefaultValue = $null
    )

    if (-not (Test-JsonObjectProperty -JsonObject $JsonObject -PropertyName $PropertyName)) {
        return $DefaultValue
    }

    foreach ($property in $JsonObject.PSObject.Properties) {
        if ($property.Name -eq $PropertyName) {
            return $property.Value
        }
    }

    return $DefaultValue
}

function New-PrecheckDetailObject {
    param([hashtable]$Properties)

    return [pscustomobject]$Properties
}


function Wait-ServiceModelsCatalog {
    param(
        [Parameter(Mandatory = $true)][string]$BaseUrl,
        [string]$RequiredModel,
        [int]$TimeoutSeconds = 180,
        [int]$PollIntervalMilliseconds = 2000,
        [int]$RequestTimeoutSeconds = 10
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = $null
    $lastModels = @()
    $attempt = 0

    while ((Get-Date) -lt $deadline) {
        $attempt++
        try {
            $modelsResponse = Invoke-RestMethod -Uri "$BaseUrl/v1/models" -Method Get -TimeoutSec $RequestTimeoutSeconds -ErrorAction Stop
            $candidateModels = @()
            if ($modelsResponse.data) {
                $candidateModels = @($modelsResponse.data | ForEach-Object { $_.id })
            }

            $lastModels = @($candidateModels)
            if ([string]::IsNullOrWhiteSpace($RequiredModel) -or ($candidateModels -contains $RequiredModel)) {
                return [pscustomobject]@{
                    Ready          = $true
                    AvailableModels = @($candidateModels)
                    Attempts       = $attempt
                    LastError      = $null
                }
            }

            $lastError = "The model catalog is reachable, but the required model '$RequiredModel' is not available yet."
        }
        catch {
            $lastError = $_.Exception.Message
        }

        Start-Sleep -Milliseconds $PollIntervalMilliseconds
    }

    return [pscustomobject]@{
        Ready           = $false
        AvailableModels = @($lastModels)
        Attempts        = $attempt
        LastError       = $lastError
    }
}


function Get-StandaloneEndpointPreparationGuidance {
    param([string]$BaseUrl)

    $guidanceLines = @(
        "This standalone pre-check script does not automatically create the Kubernetes port-forward.",
        "The specified BaseUrl must already be reachable before executing this standalone script.",
        "When running through the main launchers with http://localhost:8080, port-forwarding is managed automatically by the launcher layer.",
        "If you are running this standalone script directly, prepare the endpoint first or create the port-forward to service/localai-server manually."
    )

    if (-not [string]::IsNullOrWhiteSpace($BaseUrl)) {
        $guidanceLines += "Required BaseUrl: $BaseUrl"
    }

    return ($guidanceLines -join ' ')
}

function Add-PrecheckResult {
    param(
        [string]$Name,
        [bool]$Success,
        [object]$Details
    )

    $script:checks += [pscustomobject]@{
        name    = $Name
        success = $Success
        details = $Details
    }

    if (-not $Success) {
        $script:failedChecks += $Name
    }
}


function Convert-ToRepositoryRelativeString {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [AllowNull()][string]$PathValue
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $PathValue
    }

    $root = ((Resolve-Path $RepositoryRoot).Path -replace '\\', '/').TrimEnd("/")
    $value = ([string]$PathValue) -replace '\\', '/'

    if ([string]::Equals($value, $root, [System.StringComparison]::OrdinalIgnoreCase)) {
        return "."
    }

    if ($value.StartsWith($root + "/", [System.StringComparison]::OrdinalIgnoreCase)) {
        return $value.Substring($root.Length + 1)
    }

    $marker = "/localai-worker-mode-benchmark-suite/"
    $markerIndex = $value.IndexOf($marker, [System.StringComparison]::OrdinalIgnoreCase)
    if ($markerIndex -ge 0) {
        return $value.Substring($markerIndex + $marker.Length)
    }

    return $PathValue
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path

if ([string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $ProfileConfig = Join-Path $repoRoot "config\precheck\profiles\TC_C0_HISTORICAL_FIXED_CLUSTER.json"
}

if (-not (Test-Path $ProfileConfig)) {
    throw "The pre-check profile file does not exist: $ProfileConfig"
}

if (-not (Test-CommandAvailable -CommandName "kubectl")) {
    throw "The required command is not available in PATH: kubectl"
}

$profile = Get-Content -Path $ProfileConfig -Raw -Encoding UTF8 | ConvertFrom-Json

$requiredProperties = @(
    "profileId",
    "description",
    "kubeconfig",
    "namespace",
    "expectedReadyNodes",
    "expectedWorkerNodes",
    "allowedPodPhases",
    "minimumNamespacePods",
    "criticalWaitingReasons",
    "maxTotalRestartsInNamespace",
    "requireMetricsApi",
    "maxNodeCpuPercent",
    "maxNodeMemoryPercent",
    "defaultOutputRoot"
)

foreach ($propertyName in $requiredProperties) {
    if (-not ($profile.PSObject.Properties.Name -contains $propertyName)) {
        throw "The profile file '$ProfileConfig' does not contain the required property '$propertyName'."
    }
}

if ([string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $Kubeconfig = Join-Path $repoRoot ([string]$profile.kubeconfig)
}

if ([string]::IsNullOrWhiteSpace($Namespace)) {
    $Namespace = [string]$profile.namespace
}

$AdditionalNamespaces = @()
if (Test-JsonObjectProperty -JsonObject $profile -PropertyName "additionalNamespaces") {
    $AdditionalNamespaces = @(Get-JsonObjectPropertyValue -JsonObject $profile -PropertyName "additionalNamespaces") | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | ForEach-Object { [string]$_ }
}
$AdditionalNamespaces = @($AdditionalNamespaces | Where-Object { $_ -ne $Namespace } | Select-Object -Unique)

if (-not (Test-Path $Kubeconfig)) {
    throw "The specified kubeconfig file does not exist: $Kubeconfig"
}

if (-not [string]::IsNullOrWhiteSpace($BaseUrl)) {
    Write-Host ""
    Write-Host (Get-StandaloneEndpointPreparationGuidance -BaseUrl $BaseUrl) -ForegroundColor DarkYellow
    Write-Host ""
}

if ([string]::IsNullOrWhiteSpace($OutputPrefix)) {
    $outputRoot = Join-Path $repoRoot ([string]$profile.defaultOutputRoot)
    if (-not (Test-Path $outputRoot)) {
        New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
    }
    $OutputPrefix = Join-Path $outputRoot "precheck"
}
else {
    $outputDirectory = Split-Path -Parent $OutputPrefix
    if (-not [string]::IsNullOrWhiteSpace($outputDirectory) -and -not (Test-Path $outputDirectory)) {
        New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    }
}

$precheckJsonPath = "${OutputPrefix}_precheck.json"
$precheckTextPath = "${OutputPrefix}_precheck.txt"

$nodesPayload = & kubectl --kubeconfig $Kubeconfig get nodes -o json | ConvertFrom-Json
$namespacePayload = & kubectl --kubeconfig $Kubeconfig get namespace $Namespace -o json | ConvertFrom-Json
$podsPayload = & kubectl --kubeconfig $Kubeconfig get pods -n $Namespace -o json | ConvertFrom-Json

$podItems = @($podsPayload.items)
$namespacePodCount = $podItems.Count

$topNodesLines = @()
$topPodsLines = @()
if ([bool]$profile.requireMetricsApi) {
    $topNodesLines = @(& kubectl --kubeconfig $Kubeconfig top nodes --no-headers)

    if ($namespacePodCount -gt 0) {
        $topPodsLines = @(& kubectl --kubeconfig $Kubeconfig top pods -n $Namespace --no-headers 2>$null)
    }
    else {
        $topPodsLines = @()
    }
}

$availableModels = @()
$serviceEndpointReady = $true
$serviceEndpointAttempts = 0
$serviceEndpointLastError = $null
$serviceReadinessTimeoutSeconds = if ($profile.PSObject.Properties.Name -contains "serviceReadinessTimeoutSeconds") { [int]$profile.serviceReadinessTimeoutSeconds } else { 180 }
$serviceReadinessPollIntervalMilliseconds = if ($profile.PSObject.Properties.Name -contains "serviceReadinessPollIntervalMilliseconds") { [int]$profile.serviceReadinessPollIntervalMilliseconds } else { 2000 }
$serviceReadinessRequestTimeoutSeconds = if ($profile.PSObject.Properties.Name -contains "serviceReadinessRequestTimeoutSeconds") { [int]$profile.serviceReadinessRequestTimeoutSeconds } else { 10 }

if (-not [string]::IsNullOrWhiteSpace($BaseUrl)) {
    $serviceCatalogProbe = Wait-ServiceModelsCatalog `
        -BaseUrl $BaseUrl `
        -RequiredModel $Model `
        -TimeoutSeconds $serviceReadinessTimeoutSeconds `
        -PollIntervalMilliseconds $serviceReadinessPollIntervalMilliseconds `
        -RequestTimeoutSeconds $serviceReadinessRequestTimeoutSeconds

    $serviceEndpointReady = [bool]$serviceCatalogProbe.Ready
    $serviceEndpointAttempts = [int]$serviceCatalogProbe.Attempts
    $serviceEndpointLastError = $serviceCatalogProbe.LastError
    $availableModels = @($serviceCatalogProbe.AvailableModels)
}

$checks = @()
$failedChecks = @()

$nodeMap = @{}
foreach ($node in $nodesPayload.items) {
    $readyCondition = $node.status.conditions | Where-Object { $_.type -eq "Ready" } | Select-Object -First 1
    $nodeMap[$node.metadata.name] = @{
        ready  = ($readyCondition.status -eq "True")
        labels = $node.metadata.labels
    }
}

$expectedReadyNodes = @($profile.expectedReadyNodes)
$missingNodes = @($expectedReadyNodes | Where-Object { -not $nodeMap.ContainsKey($_) })
$notReadyNodes = @($expectedReadyNodes | Where-Object { $nodeMap.ContainsKey($_) -and -not [bool]$nodeMap[$_].ready })

$clusterNodesReadySuccess = (($missingNodes.Count -eq 0) -and ($notReadyNodes.Count -eq 0))
$clusterNodesReadyDetails = @{
    expectedReadyNodes = $expectedReadyNodes
    missingNodes       = $missingNodes
    notReadyNodes      = $notReadyNodes
    discoveredNodes    = @($nodeMap.Keys | Sort-Object)
}

Add-PrecheckResult `
    -Name "cluster_nodes_ready" `
    -Success $clusterNodesReadySuccess `
    -Details $clusterNodesReadyDetails

$namespaceActiveSuccess = ($namespacePayload.status.phase -eq "Active")
$namespaceActiveDetails = @{
    namespace = $Namespace
    phase     = $namespacePayload.status.phase
}

Add-PrecheckResult `
    -Name "namespace_active" `
    -Success $namespaceActiveSuccess `
    -Details $namespaceActiveDetails

$allowedPodPhases = @($profile.allowedPodPhases)
$criticalWaitingReasons = @($profile.criticalWaitingReasons)
$minimumNamespacePods = [int]$profile.minimumNamespacePods
$maxTotalRestarts = [int]$profile.maxTotalRestartsInNamespace

$restartTolerancePolicy = $null
if (Test-JsonObjectProperty -JsonObject $profile -PropertyName "restartTolerancePolicy") {
    $restartTolerancePolicy = Get-JsonObjectPropertyValue -JsonObject $profile -PropertyName "restartTolerancePolicy"
}

$treatRecoveredRestartsAsWarning = $false
$maxRecoveredRestarts = $maxTotalRestarts
$requireAllContainersReadyForRestartTolerance = $true
$requireServiceEndpointReadyForRestartTolerance = $true

if ($null -ne $restartTolerancePolicy) {
    if (Test-JsonObjectProperty -JsonObject $restartTolerancePolicy -PropertyName "treatRecoveredRestartsAsWarning") {
        $treatRecoveredRestartsAsWarning = [bool](Get-JsonObjectPropertyValue -JsonObject $restartTolerancePolicy -PropertyName "treatRecoveredRestartsAsWarning")
    }

    if (Test-JsonObjectProperty -JsonObject $restartTolerancePolicy -PropertyName "maxRecoveredRestartsInNamespace") {
        $maxRecoveredRestarts = [int](Get-JsonObjectPropertyValue -JsonObject $restartTolerancePolicy -PropertyName "maxRecoveredRestartsInNamespace")
    }

    if (Test-JsonObjectProperty -JsonObject $restartTolerancePolicy -PropertyName "requireAllContainersReady") {
        $requireAllContainersReadyForRestartTolerance = [bool](Get-JsonObjectPropertyValue -JsonObject $restartTolerancePolicy -PropertyName "requireAllContainersReady")
    }

    if (Test-JsonObjectProperty -JsonObject $restartTolerancePolicy -PropertyName "requireServiceEndpointReady") {
        $requireServiceEndpointReadyForRestartTolerance = [bool](Get-JsonObjectPropertyValue -JsonObject $restartTolerancePolicy -PropertyName "requireServiceEndpointReady")
    }
}

$namespaceValidationPolicy = $null
if (Test-JsonObjectProperty -JsonObject $profile -PropertyName "namespaceValidationPolicy") {
    $namespaceValidationPolicy = Get-JsonObjectPropertyValue -JsonObject $profile -PropertyName "namespaceValidationPolicy"
}
$validateAdditionalNamespaces = ($AdditionalNamespaces.Count -gt 0)
$minimumPodsPerAdditionalNamespace = 1
if ($null -ne $namespaceValidationPolicy) {
    if (Test-JsonObjectProperty -JsonObject $namespaceValidationPolicy -PropertyName "validateAdditionalNamespaces") {
        $validateAdditionalNamespaces = [bool](Get-JsonObjectPropertyValue -JsonObject $namespaceValidationPolicy -PropertyName "validateAdditionalNamespaces")
    }
    if (Test-JsonObjectProperty -JsonObject $namespaceValidationPolicy -PropertyName "minimumPodsPerAdditionalNamespace") {
        $minimumPodsPerAdditionalNamespace = [int](Get-JsonObjectPropertyValue -JsonObject $namespaceValidationPolicy -PropertyName "minimumPodsPerAdditionalNamespace")
    }
}

if ($validateAdditionalNamespaces) {
    foreach ($additionalNamespace in $AdditionalNamespaces) {
        $additionalNamespaceDetails = [ordered]@{
            namespace = $additionalNamespace
            namespaceActive = $false
            podCount = 0
            minimumPods = $minimumPodsPerAdditionalNamespace
            invalidPhasePods = @()
            criticalWaiting = @()
            notReadyContainers = @()
            totalRestarts = 0
            error = $null
        }
        $additionalNamespaceSuccess = $false
        try {
            $additionalNamespacePayload = & kubectl --kubeconfig $Kubeconfig get namespace $additionalNamespace -o json | ConvertFrom-Json
            $additionalPodsPayload = & kubectl --kubeconfig $Kubeconfig get pods -n $additionalNamespace -o json | ConvertFrom-Json
            $additionalPodItems = @($additionalPodsPayload.items)
            $additionalNamespaceDetails.namespaceActive = ($additionalNamespacePayload.status.phase -eq "Active")
            $additionalNamespaceDetails.podCount = $additionalPodItems.Count

            foreach ($pod in $additionalPodItems) {
                if ($allowedPodPhases -notcontains $pod.status.phase) {
                    $additionalNamespaceDetails.invalidPhasePods += New-PrecheckDetailObject @{
                        pod = [string]$pod.metadata.name
                        phase = [string]$pod.status.phase
                    }
                }
                foreach ($collectionName in @("containerStatuses", "initContainerStatuses")) {
                    $statusObject = $pod.status
                    if ($null -eq $statusObject -or -not (Test-JsonObjectProperty -JsonObject $statusObject -PropertyName $collectionName)) { continue }
                    $collection = Get-JsonObjectPropertyValue -JsonObject $statusObject -PropertyName $collectionName
                    if ($null -eq $collection) { continue }
                    foreach ($containerStatus in $collection) {
                        $additionalNamespaceDetails.totalRestarts += [int]$containerStatus.restartCount
                        if ($collectionName -eq "containerStatuses") {
                            $containerReady = $false
                            if (Test-JsonObjectProperty -JsonObject $containerStatus -PropertyName "ready") {
                                $containerReady = [bool](Get-JsonObjectPropertyValue -JsonObject $containerStatus -PropertyName "ready")
                            }
                            if (-not $containerReady -and [string]$pod.status.phase -ne "Succeeded") {
                                $additionalNamespaceDetails.notReadyContainers += New-PrecheckDetailObject @{
                                    pod = [string]$pod.metadata.name
                                    container = [string]$containerStatus.name
                                }
                            }
                        }
                        $stateObject = $containerStatus.state
                        if ($null -ne $stateObject -and (Test-JsonObjectProperty -JsonObject $stateObject -PropertyName "waiting")) {
                            $waitingState = Get-JsonObjectPropertyValue -JsonObject $stateObject -PropertyName "waiting"
                            if ($null -ne $waitingState) {
                                $reason = [string]$waitingState.reason
                                if ($criticalWaitingReasons -contains $reason) {
                                    $additionalNamespaceDetails.criticalWaiting += New-PrecheckDetailObject @{
                                        pod = [string]$pod.metadata.name
                                        container = [string]$containerStatus.name
                                        reason = [string]$reason
                                    }
                                }
                            }
                        }
                    }
                }
            }
            $additionalNamespaceSuccess = (
                $additionalNamespaceDetails.namespaceActive -and
                ($additionalNamespaceDetails.podCount -ge $minimumPodsPerAdditionalNamespace) -and
                ($additionalNamespaceDetails.invalidPhasePods.Count -eq 0) -and
                ($additionalNamespaceDetails.criticalWaiting.Count -eq 0) -and
                ($additionalNamespaceDetails.notReadyContainers.Count -eq 0)
            )
        }
        catch {
            $additionalNamespaceDetails.error = $_.Exception.Message
            $additionalNamespaceSuccess = $false
        }

        Add-PrecheckResult `
            -Name "additional_namespace_healthy:$additionalNamespace" `
            -Success $additionalNamespaceSuccess `
            -Details $additionalNamespaceDetails
    }
}

$invalidPhasePods = @()
$criticalWaiting = @()
$notReadyContainers = @()
$restartDetails = @()
$totalRestarts = 0
$workerPodNodes = @{}

foreach ($pod in $podItems) {
    if ($allowedPodPhases -notcontains $pod.status.phase) {
        $invalidPhasePods += New-PrecheckDetailObject @{
            pod   = [string]$pod.metadata.name
            phase = [string]$pod.status.phase
        }
    }

    foreach ($collectionName in @("containerStatuses", "initContainerStatuses")) {
        $statusObject = $pod.status
        if ($null -eq $statusObject) {
            continue
        }

        if (-not (Test-JsonObjectProperty -JsonObject $statusObject -PropertyName $collectionName)) {
            continue
        }

        $collection = Get-JsonObjectPropertyValue -JsonObject $statusObject -PropertyName $collectionName
        if ($null -eq $collection) {
            continue
        }

        foreach ($containerStatus in $collection) {
            $containerRestarts = [int]$containerStatus.restartCount
            $totalRestarts += $containerRestarts

            if ($containerRestarts -gt 0) {
                $restartDetails += New-PrecheckDetailObject @{
                    pod          = [string]$pod.metadata.name
                    container    = [string]$containerStatus.name
                    restartCount = $containerRestarts
                    collection   = [string]$collectionName
                }
            }

            if ($collectionName -eq "containerStatuses") {
                $containerReady = $false
                if (Test-JsonObjectProperty -JsonObject $containerStatus -PropertyName "ready") {
                    $containerReady = [bool](Get-JsonObjectPropertyValue -JsonObject $containerStatus -PropertyName "ready")
                }

                if (-not $containerReady -and [string]$pod.status.phase -ne "Succeeded") {
                    $notReadyContainers += New-PrecheckDetailObject @{
                        pod       = [string]$pod.metadata.name
                        container = [string]$containerStatus.name
                    }
                }
            }

            $stateObject = $containerStatus.state
            if ($null -ne $stateObject -and (Test-JsonObjectProperty -JsonObject $stateObject -PropertyName "waiting")) {
                $waitingState = Get-JsonObjectPropertyValue -JsonObject $stateObject -PropertyName "waiting"
                if ($null -ne $waitingState) {
                    $reason = [string]$waitingState.reason
                    if ($criticalWaitingReasons -contains $reason) {
                        $criticalWaiting += New-PrecheckDetailObject @{
                            pod       = [string]$pod.metadata.name
                            container = [string]$containerStatus.name
                            reason    = [string]$reason
                        }
                    }
                }
            }
        }
    }

    $podSpec = $pod.spec
    $nodeName = [string](Get-JsonObjectPropertyValue -JsonObject $podSpec -PropertyName "nodeName" -DefaultValue "")

    if ($pod.metadata.name -like "localai-rpc-*" -and -not [string]::IsNullOrWhiteSpace($nodeName)) {
        $workerPodNodes[$pod.metadata.name] = $nodeName
    }
}

if ($namespacePodCount -eq 0) {
    $namespacePodsHealthySuccess = $false
    $namespacePodsHealthyDetails = @{
        namespace               = $Namespace
        minimumNamespacePods    = $minimumNamespacePods
        podCount                = $namespacePodCount
        hasMinimumNamespacePods = $false
        invalidPhasePodsCount   = 0
        criticalWaitingCount    = 0
        totalRestarts           = 0
        maxTotalRestarts        = $maxTotalRestarts
        note                    = "Namespace exists but currently contains no workload pods."
    }
}
else {
    $namespaceHasMinimumPods = ($namespacePodCount -ge $minimumNamespacePods)
    $basePodsHealthyIgnoringRestarts = (
        $namespaceHasMinimumPods -and
        ($invalidPhasePods.Count -eq 0) -and
        ($criticalWaiting.Count -eq 0)
    )
    $allContainersReady = ($notReadyContainers.Count -eq 0)
    $serviceEndpointConditionMet = ((-not $requireServiceEndpointReadyForRestartTolerance) -or $serviceEndpointReady)
    $containersReadyConditionMet = ((-not $requireAllContainersReadyForRestartTolerance) -or $allContainersReady)
    $restartToleranceApplies = (
        $treatRecoveredRestartsAsWarning -and
        ($totalRestarts -gt $maxTotalRestarts) -and
        ($totalRestarts -le $maxRecoveredRestarts) -and
        $basePodsHealthyIgnoringRestarts -and
        $containersReadyConditionMet -and
        $serviceEndpointConditionMet
    )
    $namespacePodsHealthySuccess = (
        ($basePodsHealthyIgnoringRestarts -and ($totalRestarts -le $maxTotalRestarts)) -or
        $restartToleranceApplies
    )

    $restartSeverity = if ($totalRestarts -le $maxTotalRestarts) {
        "none_or_within_strict_threshold"
    }
    elseif ($restartToleranceApplies) {
        "warning_recovered_restarts_within_tolerance"
    }
    else {
        "blocking_restarts_exceed_policy"
    }

    $namespacePodsHealthyDetails = @{
        namespace                                      = $Namespace
        minimumNamespacePods                           = $minimumNamespacePods
        podCount                                       = $namespacePodCount
        hasMinimumNamespacePods                        = $namespaceHasMinimumPods
        invalidPhasePodsCount                          = $invalidPhasePods.Count
        invalidPhasePods                               = @($invalidPhasePods)
        criticalWaitingCount                           = $criticalWaiting.Count
        criticalWaiting                                = @($criticalWaiting)
        notReadyContainersCount                        = $notReadyContainers.Count
        notReadyContainers                             = @($notReadyContainers)
        allContainersReady                             = $allContainersReady
        totalRestarts                                  = $totalRestarts
        maxTotalRestarts                               = $maxTotalRestarts
        restartTolerancePolicy                         = @{
            enabled                         = $treatRecoveredRestartsAsWarning
            maxRecoveredRestartsInNamespace = $maxRecoveredRestarts
            requireAllContainersReady       = $requireAllContainersReadyForRestartTolerance
            requireServiceEndpointReady     = $requireServiceEndpointReadyForRestartTolerance
        }
        restartToleranceApplied                        = $restartToleranceApplies
        restartSeverity                                = $restartSeverity
        restartDetails                                 = @($restartDetails)
        note                                           = $(if ($restartToleranceApplies) { "Recovered restarts were observed and retained as a warning because all pod health, readiness and service checks required by the profile are satisfied." } else { $null })
    }
}

Add-PrecheckResult `
    -Name "namespace_pods_healthy" `
    -Success $namespacePodsHealthySuccess `
    -Details $namespacePodsHealthyDetails

$expectedWorkerNodes = @($profile.expectedWorkerNodes)
$observedWorkerNodes = @($workerPodNodes.Values | Sort-Object -Unique)
$unexpectedWorkerNodes = @($observedWorkerNodes | Where-Object { $expectedWorkerNodes -notcontains $_ })

$workerNodesExpectedSuccess = ($unexpectedWorkerNodes.Count -eq 0)
$workerNodesExpectedDetails = @{
    expectedWorkerNodes    = $expectedWorkerNodes
    observedWorkerPodNodes = $workerPodNodes
    unexpectedWorkerNodes  = $unexpectedWorkerNodes
}

Add-PrecheckResult `
    -Name "worker_nodes_expected" `
    -Success $workerNodesExpectedSuccess `
    -Details $workerNodesExpectedDetails

if ([bool]$profile.requireMetricsApi) {
    $nodeMetrics = @()
    foreach ($line in $topNodesLines) {
        $parts = ($line -split '\s+') | Where-Object { $_ -ne "" }
        if ($parts.Count -ge 5) {
            $nodeMetrics += New-PrecheckDetailObject @{
                name          = [string]$parts[0]
                cpu           = [string]$parts[1]
                cpuPercent    = [int]($parts[2].TrimEnd('%'))
                memory        = [string]$parts[3]
                memoryPercent = [int]($parts[4].TrimEnd('%'))
            }
        }
    }

    $namespacePodMetrics = @()
    foreach ($line in $topPodsLines) {
        $parts = ($line -split '\s+') | Where-Object { $_ -ne "" }
        if ($parts.Count -ge 3) {
            $namespacePodMetrics += New-PrecheckDetailObject @{
                pod    = [string]$parts[0]
                cpu    = [string]$parts[1]
                memory = [string]$parts[2]
            }
        }
    }

    $maxNodeCpuPercent = 0
    $maxNodeMemoryPercent = 0

    foreach ($metric in $nodeMetrics) {
        if ([int]$metric.cpuPercent -gt $maxNodeCpuPercent) {
            $maxNodeCpuPercent = [int]$metric.cpuPercent
        }

        if ([int]$metric.memoryPercent -gt $maxNodeMemoryPercent) {
            $maxNodeMemoryPercent = [int]$metric.memoryPercent
        }
    }

    $metricsApiAndCapacitySuccess = (
        ($maxNodeCpuPercent -le [int]$profile.maxNodeCpuPercent) -and
        ($maxNodeMemoryPercent -le [int]$profile.maxNodeMemoryPercent)
    )

    $metricsApiAndCapacityDetails = @{
        maxNodeCpuPercent           = $maxNodeCpuPercent
        maxAllowedNodeCpuPercent    = [int]$profile.maxNodeCpuPercent
        maxNodeMemoryPercent        = $maxNodeMemoryPercent
        maxAllowedNodeMemoryPercent = [int]$profile.maxNodeMemoryPercent
        nodeMetricsCount            = $nodeMetrics.Count
        namespacePodMetricsCount    = $namespacePodMetrics.Count
        note                        = $(if ($namespacePodCount -eq 0) { "Namespace contains no workload pods, so pod-level metrics are intentionally empty." } else { $null })
    }

    Add-PrecheckResult `
        -Name "metrics_api_and_capacity" `
        -Success $metricsApiAndCapacitySuccess `
        -Details $metricsApiAndCapacityDetails
}

$modelCheckSuccess = $true
if (-not [string]::IsNullOrWhiteSpace($BaseUrl)) {
    $modelCheckSuccess = $serviceEndpointReady
    if ($modelCheckSuccess -and -not [string]::IsNullOrWhiteSpace($Model)) {
        $modelCheckSuccess = $availableModels -contains $Model
    }
}

$serviceEndpointGuidance = $null
if (-not $serviceEndpointReady -and -not [string]::IsNullOrWhiteSpace($BaseUrl)) {
    $serviceEndpointGuidance = Get-StandaloneEndpointPreparationGuidance -BaseUrl $BaseUrl
}

$serviceEndpointAndModelDetails = @{
    baseUrl                          = $(if ([string]::IsNullOrWhiteSpace($BaseUrl)) { $null } else { $BaseUrl })
    requiredModel                    = $(if ([string]::IsNullOrWhiteSpace($Model)) { $null } else { $Model })
    availableModels                  = @($availableModels)
    endpointReady                    = $serviceEndpointReady
    attempts                         = $serviceEndpointAttempts
    serviceReadinessTimeoutSeconds   = $serviceReadinessTimeoutSeconds
    serviceReadinessRequestTimeoutSeconds = $serviceReadinessRequestTimeoutSeconds
    lastError                        = $serviceEndpointLastError
    guidance                         = $serviceEndpointGuidance
}

Add-PrecheckResult `
    -Name "service_endpoint_and_model" `
    -Success $modelCheckSuccess `
    -Details $serviceEndpointAndModelDetails

$timestampUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$displayProfileConfig = Convert-ToRepositoryRelativeString -RepositoryRoot $repoRoot -PathValue ((Resolve-Path $ProfileConfig).Path)
$displayKubeconfig = Convert-ToRepositoryRelativeString -RepositoryRoot $repoRoot -PathValue $Kubeconfig
$displayOutputPrefix = Convert-ToRepositoryRelativeString -RepositoryRoot $repoRoot -PathValue $OutputPrefix
$displayPrecheckJsonPath = Convert-ToRepositoryRelativeString -RepositoryRoot $repoRoot -PathValue $precheckJsonPath
$displayPrecheckTextPath = Convert-ToRepositoryRelativeString -RepositoryRoot $repoRoot -PathValue $precheckTextPath

$success = ($failedChecks.Count -eq 0)

$resultPayload = [ordered]@{
    profile = [ordered]@{
        profileFile = $displayProfileConfig
        profileId = [string]$profile.profileId
        description = [string]$profile.description
    }
    execution = [ordered]@{
        timestampUtc = $timestampUtc
        kubeconfig = $displayKubeconfig
        namespace = $Namespace
        additionalNamespaces = @($AdditionalNamespaces)
        outputPrefix = $displayOutputPrefix
        baseUrl = $(if ([string]::IsNullOrWhiteSpace($BaseUrl)) { $null } else { $BaseUrl })
        model = $(if ([string]::IsNullOrWhiteSpace($Model)) { $null } else { $Model })
    }
    summary = [ordered]@{
        success = $success
        failedChecks = @($failedChecks)
        checkCount = $checks.Count
    }
    checks = @($checks)
}

Write-PortableArtifactJson -Path $precheckJsonPath -Payload $resultPayload -Depth 12

$summaryLines = @(
    "=============================================",
    " Benchmark Technical Pre-Check",
    "=============================================",
    "Profile ID          : $($profile.profileId)",
    "Timestamp (UTC)     : $timestampUtc",
    "Kubeconfig          : $displayKubeconfig",
    "Namespace           : $Namespace",
    "Additional namespaces: $(if ($AdditionalNamespaces.Count -eq 0) { '-' } else { $AdditionalNamespaces -join ', ' })",
    "Base URL            : $(if ([string]::IsNullOrWhiteSpace($BaseUrl)) { '-' } else { $BaseUrl })",
    "Model               : $(if ([string]::IsNullOrWhiteSpace($Model)) { '-' } else { $Model })",
    "JSON report         : $displayPrecheckJsonPath",
    "Overall result      : $(if ($success) { 'PASS' } else { 'FAIL' })",
    "",
    "Checks:"
)

foreach ($check in $checks) {
    $status = if ($check.success) { "PASS" } else { "FAIL" }
    $summaryLines += " - $($check.name): $status"
}

if ($failedChecks.Count -gt 0) {
    $summaryLines += ""
    $summaryLines += "Failed checks:"
    foreach ($failedCheck in $failedChecks) {
        $summaryLines += " - $failedCheck"
    }
}

Write-PortableArtifactText -Path $precheckTextPath -Text $summaryLines
$summaryLines | ForEach-Object { Write-Host $_ }

if (-not $success) {
    exit 1
}
