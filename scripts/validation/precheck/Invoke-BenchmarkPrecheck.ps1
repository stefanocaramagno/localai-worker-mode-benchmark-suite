param(
    [string]$ProfileConfig,
    [string]$Kubeconfig,
    [string]$Namespace,
    [string]$OutputPrefix,
    [string]$BaseUrl,
    [string]$Model
)

$ErrorActionPreference = "Stop"

function Test-CommandAvailable {
    param([string]$CommandName)

    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
    return $null -ne $cmd
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

            $lastError = "Il catalogo modelli è raggiungibile ma il modello richiesto '$RequiredModel' non è ancora disponibile."
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
        "Questo script di pre-check non crea automaticamente il port-forward Kubernetes.",
        "Il BaseUrl specificato deve essere già raggiungibile prima dell'esecuzione dello script standalone.",
        "Se stai eseguendo la pipeline tramite i launcher principali e usi http://localhost:8080, il port-forward viene gestito automaticamente a livello di launcher.",
        "Se invece stai eseguendo direttamente questo script standalone, prepara prima l'endpoint oppure crea manualmente il port-forward verso service/localai-server."
    )

    if (-not [string]::IsNullOrWhiteSpace($BaseUrl)) {
        $guidanceLines += "BaseUrl richiesto: $BaseUrl"
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

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path

if ([string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $ProfileConfig = Join-Path $repoRoot "config\precheck\TC1.json"
}

if (-not (Test-Path $ProfileConfig)) {
    throw "Il file di profilo del pre-check non esiste: $ProfileConfig"
}

if (-not (Test-CommandAvailable -CommandName "kubectl")) {
    throw "Il comando richiesto non è disponibile nel PATH: kubectl"
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
        throw "Il file di profilo '$ProfileConfig' non contiene la proprietà obbligatoria '$propertyName'."
    }
}

if ([string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $Kubeconfig = Join-Path $repoRoot ([string]$profile.kubeconfig)
}

if ([string]::IsNullOrWhiteSpace($Namespace)) {
    $Namespace = [string]$profile.namespace
}

if (-not (Test-Path $Kubeconfig)) {
    throw "Il file kubeconfig specificato non esiste: $Kubeconfig"
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

$invalidPhasePods = New-Object System.Collections.Generic.List[object]
$criticalWaiting = New-Object System.Collections.Generic.List[object]
$totalRestarts = 0
$workerPodNodes = @{}

foreach ($pod in $podItems) {
    if ($allowedPodPhases -notcontains $pod.status.phase) {
        $invalidPhasePods.Add(@{
            pod   = $pod.metadata.name
            phase = $pod.status.phase
        }) | Out-Null
    }

    foreach ($collectionName in @("containerStatuses", "initContainerStatuses")) {
        $statusObject = $pod.status
        if ($null -eq $statusObject) {
            continue
        }

        if (-not ($statusObject.PSObject.Properties.Name -contains $collectionName)) {
            continue
        }

        $collection = $statusObject.$collectionName
        if ($null -eq $collection) {
            continue
        }

        foreach ($containerStatus in $collection) {
            $totalRestarts += [int]$containerStatus.restartCount

            $stateObject = $containerStatus.state
            if ($null -ne $stateObject -and ($stateObject.PSObject.Properties.Name -contains "waiting")) {
                $waitingState = $stateObject.waiting
                if ($null -ne $waitingState) {
                    $reason = [string]$waitingState.reason
                    if ($criticalWaitingReasons -contains $reason) {
                        $criticalWaiting.Add(@{
                            pod       = $pod.metadata.name
                            container = $containerStatus.name
                            reason    = $reason
                        }) | Out-Null
                    }
                }
            }
        }
    }

    if ($pod.metadata.name -like "localai-rpc-*" -and -not [string]::IsNullOrWhiteSpace($pod.spec.nodeName)) {
        $workerPodNodes[$pod.metadata.name] = $pod.spec.nodeName
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
    $namespacePodsHealthySuccess = (
        $namespaceHasMinimumPods -and
        ($invalidPhasePods.Count -eq 0) -and
        ($criticalWaiting.Count -eq 0) -and
        ($totalRestarts -le $maxTotalRestarts)
    )

    $namespacePodsHealthyDetails = @{
        namespace               = $Namespace
        minimumNamespacePods    = $minimumNamespacePods
        podCount                = $namespacePodCount
        hasMinimumNamespacePods = $namespaceHasMinimumPods
        invalidPhasePodsCount   = $invalidPhasePods.Count
        criticalWaitingCount    = $criticalWaiting.Count
        totalRestarts           = $totalRestarts
        maxTotalRestarts        = $maxTotalRestarts
        note                    = $null
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
    $nodeMetrics = New-Object System.Collections.Generic.List[object]
    foreach ($line in $topNodesLines) {
        $parts = ($line -split '\s+') | Where-Object { $_ -ne "" }
        if ($parts.Count -ge 5) {
            $nodeMetrics.Add(@{
                name          = $parts[0]
                cpu           = $parts[1]
                cpuPercent    = [int]($parts[2].TrimEnd('%'))
                memory        = $parts[3]
                memoryPercent = [int]($parts[4].TrimEnd('%'))
            }) | Out-Null
        }
    }

    $namespacePodMetrics = New-Object System.Collections.Generic.List[object]
    foreach ($line in $topPodsLines) {
        $parts = ($line -split '\s+') | Where-Object { $_ -ne "" }
        if ($parts.Count -ge 3) {
            $namespacePodMetrics.Add(@{
                pod    = $parts[0]
                cpu    = $parts[1]
                memory = $parts[2]
            }) | Out-Null
        }
    }

    $maxNodeCpuPercent = 0
    $maxNodeMemoryPercent = 0

    foreach ($metric in $nodeMetrics) {
        if ([int]$metric["cpuPercent"] -gt $maxNodeCpuPercent) {
            $maxNodeCpuPercent = [int]$metric["cpuPercent"]
        }

        if ([int]$metric["memoryPercent"] -gt $maxNodeMemoryPercent) {
            $maxNodeMemoryPercent = [int]$metric["memoryPercent"]
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
$success = ($failedChecks.Count -eq 0)

$resultPayload = [ordered]@{
    profile = [ordered]@{
        profileFile = (Resolve-Path $ProfileConfig).Path
        profileId = [string]$profile.profileId
        description = [string]$profile.description
    }
    execution = [ordered]@{
        timestampUtc = $timestampUtc
        kubeconfig = $Kubeconfig
        namespace = $Namespace
        outputPrefix = $OutputPrefix
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

$resultPayload | ConvertTo-Json -Depth 12 | Set-Content -Path $precheckJsonPath -Encoding UTF8

$summaryLines = @(
    "=============================================",
    " Benchmark Technical Pre-Check",
    "=============================================",
    "Profile ID          : $($profile.profileId)",
    "Timestamp (UTC)     : $timestampUtc",
    "Kubeconfig          : $Kubeconfig",
    "Namespace           : $Namespace",
    "Base URL            : $(if ([string]::IsNullOrWhiteSpace($BaseUrl)) { '-' } else { $BaseUrl })",
    "Model               : $(if ([string]::IsNullOrWhiteSpace($Model)) { '-' } else { $Model })",
    "JSON report         : $precheckJsonPath",
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

$summaryLines | Set-Content -Path $precheckTextPath -Encoding UTF8
$summaryLines | ForEach-Object { Write-Host $_ }

if (-not $success) {
    exit 1
}
