Set-StrictMode -Version Latest

function Get-MetricSetProfile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProfileFile
    )

    if (-not (Test-Path $ProfileFile)) {
        throw "Il file di metric set non esiste: $ProfileFile"
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
            throw "Il file di metric set '$ProfileFile' non contiene la proprietà obbligatoria '$propertyName'."
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
        [string]$PostStagePrefix
    )

    return @(
        "${PreStagePrefix}_manifest.json",
        "${PreStagePrefix}_summary.txt",
        "${PreStagePrefix}_nodes-wide.txt",
        "${PreStagePrefix}_top-nodes.txt",
        "${PreStagePrefix}_pods-wide.txt",
        "${PreStagePrefix}_top-pods.txt",
        "${PreStagePrefix}_services.txt",
        "${PreStagePrefix}_events.txt",
        "${PreStagePrefix}_pods-describe.txt",
        "${PostStagePrefix}_manifest.json",
        "${PostStagePrefix}_summary.txt",
        "${PostStagePrefix}_nodes-wide.txt",
        "${PostStagePrefix}_top-nodes.txt",
        "${PostStagePrefix}_pods-wide.txt",
        "${PostStagePrefix}_top-pods.txt",
        "${PostStagePrefix}_services.txt",
        "${PostStagePrefix}_events.txt",
        "${PostStagePrefix}_pods-describe.txt"
    )
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
        [string[]]$ClusterSourceArtifacts = @()
    )

    $payload = [ordered]@{
        metricSetProfile = [ordered]@{
            profileFile = $MetricSetProfile.ProfileFile
            profileId = $MetricSetProfile.ProfileId
            description = $MetricSetProfile.Description
        }
        launcher = $LauncherName
        runId = $RunId
        measurementCsvPrefix = $MeasurementCsvPrefix
        minimumMetrics = [ordered]@{
            clientSide = $MetricSetProfile.ClientMetrics
            clusterSide = $MetricSetProfile.ClusterMetrics
        }
        sourceArtifacts = [ordered]@{
            clientSide = $ClientSourceArtifacts
            clusterSide = $ClusterSourceArtifacts
        }
    }

    $payload | ConvertTo-Json -Depth 20 | Set-Content -Path $ManifestPath -Encoding UTF8

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("=============================================")
    $lines.Add(" Minimum Mandatory Metric Set")
    $lines.Add("=============================================")
    $lines.Add("Metric set profile : $($MetricSetProfile.ProfileId)")
    $lines.Add("Description        : $($MetricSetProfile.Description)")
    $lines.Add("Launcher           : $LauncherName")
    $lines.Add("Run ID             : $RunId")
    $lines.Add("Measurement prefix : $MeasurementCsvPrefix")
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
    foreach ($artifact in $ClientSourceArtifacts) {
        $lines.Add(" - $artifact")
    }
    $lines.Add("")
    $lines.Add("Cluster-side source artifacts:")
    foreach ($artifact in $ClusterSourceArtifacts) {
        $lines.Add(" - $artifact")
    }

    $lines | Set-Content -Path $TextPath -Encoding UTF8
}
