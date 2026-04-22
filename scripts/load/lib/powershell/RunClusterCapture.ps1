Set-StrictMode -Version Latest

function Get-ClusterCaptureProfile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProfileFile
    )

    if (-not (Test-Path $ProfileFile)) {
        throw "Il file di cluster-side collection non esiste: $ProfileFile"
    }

    $data = Get-Content -Path $ProfileFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $requiredProperties = @(
        "profileId",
        "description",
        "collectorScriptRelativePathBash",
        "collectorScriptRelativePathPowerShell",
        "preStageSuffix",
        "postStageSuffix",
        "manifestSuffix",
        "textSuffix",
        "artifacts"
    )

    foreach ($propertyName in $requiredProperties) {
        if (-not ($data.PSObject.Properties.Name -contains $propertyName)) {
            throw "Il file di cluster-side collection '$ProfileFile' non contiene la proprietà obbligatoria '$propertyName'."
        }
    }

    return [pscustomobject]@{
        ProfileFile = (Resolve-Path $ProfileFile).Path
        ProfileId = [string]$data.profileId
        Description = [string]$data.description
        CollectorScriptRelativePathBash = [string]$data.collectorScriptRelativePathBash
        CollectorScriptRelativePathPowerShell = [string]$data.collectorScriptRelativePathPowerShell
        PreStageSuffix = [string]$data.preStageSuffix
        PostStageSuffix = [string]$data.postStageSuffix
        ManifestSuffix = [string]$data.manifestSuffix
        TextSuffix = [string]$data.textSuffix
        Artifacts = @($data.artifacts)
    }
}

function Get-ClusterCaptureStagePaths {
    param(
        [Parameter(Mandatory = $true)]
        [string]$MeasurementCsvPrefix,
        [Parameter(Mandatory = $true)]$ClusterCaptureProfile
    )

    return [pscustomobject]@{
        PrePrefix = "${MeasurementCsvPrefix}$($ClusterCaptureProfile.PreStageSuffix)"
        PostPrefix = "${MeasurementCsvPrefix}$($ClusterCaptureProfile.PostStageSuffix)"
    }
}

function Get-ClusterCaptureArtifactList {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StagePrefix,
        [Parameter(Mandatory = $true)]$ClusterCaptureProfile
    )

    $artifacts = @(
        "${StagePrefix}$($ClusterCaptureProfile.ManifestSuffix)",
        "${StagePrefix}$($ClusterCaptureProfile.TextSuffix)"
    )

    foreach ($artifact in $ClusterCaptureProfile.Artifacts) {
        if ($null -eq $artifact) {
            continue
        }

        if ($artifact -is [string]) {
            $artifacts += "${StagePrefix}_${artifact}"
            continue
        }

        if ($artifact.PSObject.Properties.Name -contains "outputSuffix" -and -not [string]::IsNullOrWhiteSpace([string]$artifact.outputSuffix)) {
            $artifacts += "${StagePrefix}_$([string]$artifact.outputSuffix)"
            continue
        }

        if ($artifact.PSObject.Properties.Name -contains "name" -and -not [string]::IsNullOrWhiteSpace([string]$artifact.name)) {
            $artifacts += "${StagePrefix}_$([string]$artifact.name)"
            continue
        }

        throw "Ogni artifact del profilo cluster-side deve essere una stringa oppure contenere almeno 'outputSuffix' o 'name'."
    }

    return $artifacts
}
