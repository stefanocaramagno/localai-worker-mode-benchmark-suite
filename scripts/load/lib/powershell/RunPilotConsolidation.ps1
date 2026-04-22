Set-StrictMode -Version Latest

function Get-PilotConsolidationProfile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProfileFile
    )

    if (-not (Test-Path $ProfileFile)) {
        throw "Il file di consolidamento non esiste: $ProfileFile"
    }

    $data = Get-Content -Path $ProfileFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $required = @(
        "profileId",
        "description",
        "outputRoot",
        "campaignManifestSuffix",
        "campaignTextSuffix",
        "stopOnFirstFailure",
        "precheckConfig",
        "phaseConfig",
        "protocolConfig",
        "clusterCaptureConfig",
        "metricSetConfig",
        "statisticalRigorConfig",
        "warmUpDuration",
        "measurementDuration",
        "families"
    )

    foreach ($propertyName in $required) {
        if (-not ($data.PSObject.Properties.Name -contains $propertyName)) {
            throw "Il file di consolidamento '$ProfileFile' non contiene la proprietà obbligatoria '$propertyName'."
        }
    }

    [pscustomobject]@{
        ProfileFile = (Resolve-Path $ProfileFile).Path
        RawConfig = $data
    }
}

function Get-PilotConsolidationFamily {
    param(
        [Parameter(Mandatory = $true)]
        $Profile,
        [Parameter(Mandatory = $true)]
        [string]$FamilyName
    )

    $families = $Profile.RawConfig.families
    if (-not ($families.PSObject.Properties.Name -contains $FamilyName)) {
        throw "La famiglia '$FamilyName' non è definita nel profilo '$($Profile.ProfileFile)'."
    }

    $familyConfig = $families.$FamilyName
    $required = @("launcherBash", "launcherPowerShell", "outputRoot", "scenarios", "replicas")

    foreach ($propertyName in $required) {
        if (-not ($familyConfig.PSObject.Properties.Name -contains $propertyName)) {
            throw "La famiglia '$FamilyName' nel profilo '$($Profile.ProfileFile)' non contiene la proprietà obbligatoria '$propertyName'."
        }
    }

    [pscustomobject]@{
        FamilyName = $FamilyName
        RawConfig = $familyConfig
    }
}

function Write-PilotConsolidationManifest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OutputPath,
        [Parameter(Mandatory = $true)]
        $Payload
    )

    $Payload | ConvertTo-Json -Depth 12 | Set-Content -Path $OutputPath -Encoding UTF8
}

function Write-PilotConsolidationReport {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OutputPath,
        [Parameter(Mandatory = $true)]
        [string]$TextPayload
    )

    Set-Content -Path $OutputPath -Value $TextPayload -Encoding UTF8
}
