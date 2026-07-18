Set-StrictMode -Version Latest

function Get-ClusterCaptureProfile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProfileFile
    )

    if (-not (Test-Path $ProfileFile)) {
        throw "The cluster-side collection file does not exist: $ProfileFile"
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
            throw "The cluster-side collection file '$ProfileFile' does not contain the required property '$propertyName'."
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
        [Parameter(Mandatory = $true)]$ClusterCaptureProfile,
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

    $artifacts = @(
        "${StagePrefix}$($ClusterCaptureProfile.ManifestSuffix)",
        "${StagePrefix}$($ClusterCaptureProfile.TextSuffix)"
    )

    foreach ($artifact in $ClusterCaptureProfile.Artifacts) {
        if ($null -eq $artifact) {
            continue
        }

        $outputSuffix = $null
        $commandText = $null

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

        if ([string]::IsNullOrWhiteSpace($outputSuffix)) {
            throw "Each artifact in the cluster-side profile must be a string or contain at least 'outputSuffix' or 'name'."
        }

        if (-not [string]::IsNullOrWhiteSpace($commandText) -and $commandText.Contains("{namespace}")) {
            foreach ($namespace in $namespaceList) {
                if ($namespace -eq $primaryNamespace) {
                    $artifacts += "${StagePrefix}_${outputSuffix}"
                }
                else {
                    $artifacts += "${StagePrefix}_$(ConvertTo-SafeNamespaceToken -Value $namespace)_${outputSuffix}"
                }
            }
        }
        else {
            $artifacts += "${StagePrefix}_${outputSuffix}"
        }
    }

    return $artifacts
}
