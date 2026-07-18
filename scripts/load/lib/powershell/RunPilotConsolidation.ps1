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

function Get-PilotConsolidationProfile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProfileFile
    )

    if (-not (Test-Path $ProfileFile)) {
        throw "The consolidation file does not exist: $ProfileFile"
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
            throw "The consolidation file '$ProfileFile' does not contain the required property '$propertyName'."
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
        throw "The family '$FamilyName' is not defined in profile '$($Profile.ProfileFile)'."
    }

    $familyConfig = $families.$FamilyName
    $required = @("launcherBash", "launcherPowerShell", "outputRoot", "scenarios", "replicas")

    foreach ($propertyName in $required) {
        if (-not ($familyConfig.PSObject.Properties.Name -contains $propertyName)) {
            throw "The family '$FamilyName' in profile '$($Profile.ProfileFile)' does not contain the required property '$propertyName'."
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

    Write-PortableArtifactJson -Path $OutputPath -Payload $Payload -Depth 12
}

function Write-PilotConsolidationReport {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OutputPath,
        [Parameter(Mandatory = $true)]
        [string]$TextPayload
    )

    Write-PortableArtifactText -Path $OutputPath -Text $TextPayload
}
