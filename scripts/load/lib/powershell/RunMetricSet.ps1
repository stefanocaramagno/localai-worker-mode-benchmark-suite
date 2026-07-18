Set-StrictMode -Version Latest

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

$script:RunMetricSetRepositoryRoot = $null
try {
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        $candidateRoot = Join-Path $PSScriptRoot "..\..\..\.."
        if (Test-Path $candidateRoot) {
            $script:RunMetricSetRepositoryRoot = (Resolve-Path $candidateRoot).Path
        }
    }
}
catch {
    $script:RunMetricSetRepositoryRoot = $null
}

function Get-RunMetricSetRepositoryRoot {
    param([AllowNull()][string]$RepositoryRoot)
    if (-not [string]::IsNullOrWhiteSpace($RepositoryRoot)) { return (Resolve-Path $RepositoryRoot).Path }
    if (-not [string]::IsNullOrWhiteSpace($script:RunMetricSetRepositoryRoot)) { return $script:RunMetricSetRepositoryRoot }
    return $null
}

function ConvertTo-RunMetricSetPortableString {
    param(
        [AllowNull()][string]$Value,
        [AllowNull()][string]$RepositoryRoot
    )

    if ([string]::IsNullOrWhiteSpace($Value)) { return $Value }
    $portableValue = ([string]$Value) -replace '\\', '/'
    if ($portableValue.Trim() -match '^[A-Za-z][A-Za-z0-9+.-]*://') { return [string]$Value }
    $rootValue = Get-RunMetricSetRepositoryRoot -RepositoryRoot $RepositoryRoot
    if (-not [string]::IsNullOrWhiteSpace($rootValue)) {
        $rootForward = ($rootValue -replace '\\', '/').TrimEnd('/')
        $portableValue = [System.Text.RegularExpressions.Regex]::Replace(
            $portableValue,
            [System.Text.RegularExpressions.Regex]::Escape($rootForward),
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


function Get-MetricSetProfile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProfileFile
    )

    if (-not (Test-Path $ProfileFile)) {
        throw "The metric-set file does not exist: $ProfileFile"
    }

    $data = Get-Content -Path $ProfileFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $requiredProperties = @(
        "profileId",
        "description",
        "clientMetrics",
        "clusterMetrics",
        "metricSetManifestSuffix",
        "metricSetTextSuffix"
    )

    foreach ($propertyName in $requiredProperties) {
        if (-not ($data.PSObject.Properties.Name -contains $propertyName)) {
            throw "The metric-set file '$ProfileFile' does not contain the required property '$propertyName'."
        }
    }

    return [pscustomobject]@{
        ProfileFile = (Resolve-Path $ProfileFile).Path
        ProfileId = [string]$data.profileId
        Description = [string]$data.description
        ClientMetrics = @($data.clientMetrics)
        ClusterMetrics = @($data.clusterMetrics)
        MetricSetManifestSuffix = [string]$data.metricSetManifestSuffix
        MetricSetTextSuffix = [string]$data.metricSetTextSuffix
    }
}

function Get-MetricSetPaths {
    param(
        [Parameter(Mandatory = $true)]
        [string]$MeasurementCsvPrefix,
        [Parameter(Mandatory = $true)]$MetricSetProfile
    )

    return [pscustomobject]@{
        ManifestPath = "${MeasurementCsvPrefix}$($MetricSetProfile.MetricSetManifestSuffix)"
        TextPath = "${MeasurementCsvPrefix}$($MetricSetProfile.MetricSetTextSuffix)"
    }
}

function Get-MetricSetClientArtifactList {
    param(
        [Parameter(Mandatory = $true)]
        [string]$MeasurementCsvPrefix
    )

    return @(
        "${MeasurementCsvPrefix}_stats.csv",
        "${MeasurementCsvPrefix}_stats_history.csv",
        "${MeasurementCsvPrefix}_failures.csv",
        "${MeasurementCsvPrefix}_exceptions.csv"
    )
}

function Get-MetricSetClusterArtifactList {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PreStagePrefix,
        [Parameter(Mandatory = $true)]
        [string]$PostStagePrefix,
        [object]$ClusterCaptureProfile,
        [string[]]$Namespaces
    )

    function ConvertTo-SafeNamespaceToken {
        param([Parameter(Mandatory = $true)][string]$Value)
        $token = $Value.Trim().ToLowerInvariant() -replace "[^a-z0-9._-]+", "-"
        $token = $token.Trim("-")
        if ([string]::IsNullOrWhiteSpace($token)) { return "namespace" }
        return $token
    }

    $namespaceList = @($Namespaces | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
    if ($namespaceList.Count -eq 0) {
        $namespaceList = @("localai-benchmark")
    }
    $primaryNamespace = [string]$namespaceList[0]

    $artifactItems = @()
    $manifestSuffix = "_manifest.json"
    $textSuffix = "_summary.txt"

    if ($null -ne $ClusterCaptureProfile) {
        if ($ClusterCaptureProfile.PSObject.Properties.Name -contains "Artifacts") {
            $artifactItems = @($ClusterCaptureProfile.Artifacts)
        }
        if ($ClusterCaptureProfile.PSObject.Properties.Name -contains "ManifestSuffix" -and -not [string]::IsNullOrWhiteSpace([string]$ClusterCaptureProfile.ManifestSuffix)) {
            $manifestSuffix = [string]$ClusterCaptureProfile.ManifestSuffix
        }
        if ($ClusterCaptureProfile.PSObject.Properties.Name -contains "TextSuffix" -and -not [string]::IsNullOrWhiteSpace([string]$ClusterCaptureProfile.TextSuffix)) {
            $textSuffix = [string]$ClusterCaptureProfile.TextSuffix
        }
    }

    if ($artifactItems.Count -eq 0) {
        $artifactItems = @(
            [pscustomobject]@{ outputSuffix = "nodes-wide.txt"; command = "kubectl get nodes -o wide" },
            [pscustomobject]@{ outputSuffix = "nodes.json"; command = "kubectl get nodes -o json" },
            [pscustomobject]@{ outputSuffix = "top-nodes.txt"; command = "kubectl top nodes" },
            [pscustomobject]@{ outputSuffix = "pods-wide.txt"; command = "kubectl get pods -n {namespace} -o wide" },
            [pscustomobject]@{ outputSuffix = "pods.json"; command = "kubectl get pods -n {namespace} -o json" },
            [pscustomobject]@{ outputSuffix = "top-pods.txt"; command = "kubectl top pods -n {namespace}" },
            [pscustomobject]@{ outputSuffix = "top-pods-containers.txt"; command = "kubectl top pods -n {namespace} --containers" },
            [pscustomobject]@{ outputSuffix = "services.txt"; command = "kubectl get svc -n {namespace}" },
            [pscustomobject]@{ outputSuffix = "events.txt"; command = "kubectl get events -n {namespace}" },
            [pscustomobject]@{ outputSuffix = "events.json"; command = "kubectl get events -n {namespace} -o json" },
            [pscustomobject]@{ outputSuffix = "pods-describe.txt"; command = "kubectl describe pods -n {namespace}" }
        )
    }

    function Get-StageMetricArtifacts {
        param([Parameter(Mandatory = $true)][string]$StagePrefix)

        $artifacts = @(
            "${StagePrefix}${manifestSuffix}",
            "${StagePrefix}${textSuffix}"
        )

        foreach ($artifact in $artifactItems) {
            if ($null -eq $artifact) { continue }

            $outputSuffix = $null
            $commandText = ""

            if ($artifact -is [string]) {
                $outputSuffix = [string]$artifact
            }
            else {
                if ($artifact.PSObject.Properties.Name -contains "outputSuffix" -and -not [string]::IsNullOrWhiteSpace([string]$artifact.outputSuffix)) {
                    $outputSuffix = [string]$artifact.outputSuffix
                }
                elseif ($artifact.PSObject.Properties.Name -contains "name" -and -not [string]::IsNullOrWhiteSpace([string]$artifact.name)) {
                    $outputSuffix = [string]$artifact.name
                }

                if ($artifact.PSObject.Properties.Name -contains "command") {
                    $commandText = [string]$artifact.command
                }
            }

            if ([string]::IsNullOrWhiteSpace($outputSuffix)) { continue }

            if (-not [string]::IsNullOrWhiteSpace($commandText) -and $commandText.Contains("{namespace}")) {
                foreach ($namespace in $namespaceList) {
                    if ([string]$namespace -eq $primaryNamespace) {
                        $artifacts += "${StagePrefix}_${outputSuffix}"
                    }
                    else {
                        $artifacts += "${StagePrefix}_$(ConvertTo-SafeNamespaceToken -Value ([string]$namespace))_${outputSuffix}"
                    }
                }
            }
            else {
                $artifacts += "${StagePrefix}_${outputSuffix}"
            }
        }

        return $artifacts
    }

    return @((Get-StageMetricArtifacts -StagePrefix $PreStagePrefix) + (Get-StageMetricArtifacts -StagePrefix $PostStagePrefix))
}

function Write-MetricSetFiles {
    param(
        [Parameter(Mandatory = $true)]$MetricSetProfile,
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$TextPath,
        [Parameter(Mandatory = $true)][string]$LauncherName,
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][string]$MeasurementCsvPrefix,
        [string[]]$ClientSourceArtifacts = @(),
        [string[]]$ClusterSourceArtifacts = @(),
        [AllowNull()][string]$RepositoryRoot
    )

    $displayProfileFile = ConvertTo-RunMetricSetPortableString -Value $MetricSetProfile.ProfileFile -RepositoryRoot $RepositoryRoot
    $displayMeasurementCsvPrefix = ConvertTo-RunMetricSetPortableString -Value $MeasurementCsvPrefix -RepositoryRoot $RepositoryRoot
    $displayClientSourceArtifacts = @($ClientSourceArtifacts | ForEach-Object { ConvertTo-RunMetricSetPortableString -Value $_ -RepositoryRoot $RepositoryRoot })
    $displayClusterSourceArtifacts = @($ClusterSourceArtifacts | ForEach-Object { ConvertTo-RunMetricSetPortableString -Value $_ -RepositoryRoot $RepositoryRoot })

    $payload = [ordered]@{
        metricSetProfile = [ordered]@{
            profileFile = $displayProfileFile
            profileId = $MetricSetProfile.ProfileId
            description = $MetricSetProfile.Description
        }
        launcher = $LauncherName
        runId = $RunId
        measurementCsvPrefix = $displayMeasurementCsvPrefix
        minimumMetrics = [ordered]@{
            clientSide = $MetricSetProfile.ClientMetrics
            clusterSide = $MetricSetProfile.ClusterMetrics
        }
        sourceArtifacts = [ordered]@{
            clientSide = $displayClientSourceArtifacts
            clusterSide = $displayClusterSourceArtifacts
        }
    }

    Write-PortableArtifactJson -Path $ManifestPath -Payload $payload -Depth 20

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("=============================================")
    $lines.Add(" Minimum Mandatory Metric Set")
    $lines.Add("=============================================")
    $lines.Add("Metric set profile : $($MetricSetProfile.ProfileId)")
    $lines.Add("Description        : $($MetricSetProfile.Description)")
    $lines.Add("Launcher           : $LauncherName")
    $lines.Add("Run ID             : $RunId")
    $lines.Add("Measurement prefix : $displayMeasurementCsvPrefix")
    $lines.Add("")
    $lines.Add("Client-side metrics:")
    foreach ($metricName in $MetricSetProfile.ClientMetrics) {
        $lines.Add(" - $metricName")
    }
    $lines.Add("")
    $lines.Add("Cluster-side metrics:")
    foreach ($metricName in $MetricSetProfile.ClusterMetrics) {
        $lines.Add(" - $metricName")
    }
    $lines.Add("")
    $lines.Add("Client-side source artifacts:")
    foreach ($artifact in $displayClientSourceArtifacts) {
        $lines.Add(" - $artifact")
    }
    $lines.Add("")
    $lines.Add("Cluster-side source artifacts:")
    foreach ($artifact in $displayClusterSourceArtifacts) {
        $lines.Add(" - $artifact")
    }

    Write-PortableArtifactText -Path $TextPath -Text $lines
}
