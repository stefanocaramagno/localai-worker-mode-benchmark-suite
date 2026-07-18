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

$script:RunPhasesRepositoryRoot = $null
try {
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        $candidateRoot = Join-Path $PSScriptRoot "..\..\..\.."
        if (Test-Path $candidateRoot) {
            $script:RunPhasesRepositoryRoot = (Resolve-Path $candidateRoot).Path
        }
    }
}
catch {
    $script:RunPhasesRepositoryRoot = $null
}

function Get-RunPhasesRepositoryRoot {
    param([AllowNull()][string]$RepositoryRoot)
    if (-not [string]::IsNullOrWhiteSpace($RepositoryRoot)) { return (Resolve-Path $RepositoryRoot).Path }
    if (-not [string]::IsNullOrWhiteSpace($script:RunPhasesRepositoryRoot)) { return $script:RunPhasesRepositoryRoot }
    return $null
}

function ConvertTo-RunPhasesPortableString {
    param(
        [AllowNull()][string]$Value,
        [AllowNull()][string]$RepositoryRoot
    )

    if ([string]::IsNullOrWhiteSpace($Value)) { return $Value }
    $portableValue = ([string]$Value) -replace '\\', '/'
    if ($portableValue.Trim() -match '^[A-Za-z][A-Za-z0-9+.-]*://') { return [string]$Value }
    $rootValue = Get-RunPhasesRepositoryRoot -RepositoryRoot $RepositoryRoot
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


function Get-PhaseProfile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProfileFile
    )

    if (-not (Test-Path $ProfileFile)) {
        throw "The warm-up/measurement profile file does not exist: $ProfileFile"
    }

    $data = Get-Content -Path $ProfileFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $requiredProperties = @(
        "profileId",
        "description",
        "warmUpEnabled",
        "warmUpDuration",
        "warmUpUsersMode",
        "warmUpSpawnRateMode",
        "startupModelCheckDuringWarmUp",
        "startupModelCheckDuringMeasurement",
        "warmUpCsvSuffix",
        "phaseManifestSuffix"
    )

    foreach ($propertyName in $requiredProperties) {
        if (-not ($data.PSObject.Properties.Name -contains $propertyName)) {
            throw "The warm-up/measurement profile file '$ProfileFile' does not contain the required property '$propertyName'."
        }
    }

    return [pscustomobject]@{
        ProfileFile = (Resolve-Path $ProfileFile).Path
        ProfileId = [string]$data.profileId
        Description = [string]$data.description
        WarmUpEnabled = [bool]$data.warmUpEnabled
        WarmUpDuration = [string]$data.warmUpDuration
        WarmUpUsersMode = [string]$data.warmUpUsersMode
        WarmUpSpawnRateMode = [string]$data.warmUpSpawnRateMode
        StartupModelCheckDuringWarmUp = [bool]$data.startupModelCheckDuringWarmUp
        StartupModelCheckDuringMeasurement = [bool]$data.startupModelCheckDuringMeasurement
        WarmUpCsvSuffix = [string]$data.warmUpCsvSuffix
        PhaseManifestSuffix = [string]$data.phaseManifestSuffix
    }
}

function New-PhasePlan {
    param(
        [Parameter(Mandatory = $true)]$PhaseProfile,
        [Parameter(Mandatory = $true)][int]$MeasurementUsers,
        [Parameter(Mandatory = $true)][int]$MeasurementSpawnRate,
        [Parameter(Mandatory = $true)][string]$ScenarioMeasurementDuration,
        [Parameter(Mandatory = $true)][string]$MeasurementCsvPrefix,
        [string]$WarmUpDurationOverride,
        [string]$MeasurementDurationOverride,
        [switch]$SkipWarmUp
    )

    $resolvedMeasurementDuration = if ([string]::IsNullOrWhiteSpace($MeasurementDurationOverride)) {
        $ScenarioMeasurementDuration
    }
    else {
        $MeasurementDurationOverride
    }

    $resolvedWarmUpDuration = if ([string]::IsNullOrWhiteSpace($WarmUpDurationOverride)) {
        $PhaseProfile.WarmUpDuration
    }
    else {
        $WarmUpDurationOverride
    }

    switch ($PhaseProfile.WarmUpUsersMode) {
        "match_measurement" { $resolvedWarmUpUsers = $MeasurementUsers }
        default { throw "Unsupported warm-up users mode: $($PhaseProfile.WarmUpUsersMode)" }
    }

    switch ($PhaseProfile.WarmUpSpawnRateMode) {
        "match_measurement" { $resolvedWarmUpSpawnRate = $MeasurementSpawnRate }
        default { throw "Unsupported warm-up spawn-rate mode: $($PhaseProfile.WarmUpSpawnRateMode)" }
    }

    $warmUpEnabledEffective = $PhaseProfile.WarmUpEnabled -and (-not $SkipWarmUp)
    $warmUpCsvPrefix = "${MeasurementCsvPrefix}$($PhaseProfile.WarmUpCsvSuffix)"
    $phaseManifestPath = "${MeasurementCsvPrefix}$($PhaseProfile.PhaseManifestSuffix)"

    return [pscustomobject]@{
        PhaseProfile = $PhaseProfile
        WarmUpEnabled = $warmUpEnabledEffective
        WarmUpDuration = $resolvedWarmUpDuration
        WarmUpUsers = [int]$resolvedWarmUpUsers
        WarmUpSpawnRate = [int]$resolvedWarmUpSpawnRate
        WarmUpStartupModelCheckEnabled = [bool]$PhaseProfile.StartupModelCheckDuringWarmUp
        WarmUpCsvPrefix = $warmUpCsvPrefix
        MeasurementDuration = $resolvedMeasurementDuration
        MeasurementUsers = [int]$MeasurementUsers
        MeasurementSpawnRate = [int]$MeasurementSpawnRate
        MeasurementStartupModelCheckEnabled = [bool]$PhaseProfile.StartupModelCheckDuringMeasurement
        MeasurementCsvPrefix = $MeasurementCsvPrefix
        PhaseManifestPath = $phaseManifestPath
    }
}

function Write-PhaseManifest {
    param(
        [Parameter(Mandatory = $true)]$PhasePlan,
        [Parameter(Mandatory = $true)][string]$OutputPath,
        [AllowNull()][string]$RepositoryRoot
    )

    $displayProfileFile = ConvertTo-RunPhasesPortableString -Value $PhasePlan.PhaseProfile.ProfileFile -RepositoryRoot $RepositoryRoot
    $displayWarmUpCsvPrefix = ConvertTo-RunPhasesPortableString -Value $PhasePlan.WarmUpCsvPrefix -RepositoryRoot $RepositoryRoot
    $displayMeasurementCsvPrefix = ConvertTo-RunPhasesPortableString -Value $PhasePlan.MeasurementCsvPrefix -RepositoryRoot $RepositoryRoot

    $payload = [ordered]@{
        phaseProfile = [ordered]@{
            profileFile = $displayProfileFile
            profileId = $PhasePlan.PhaseProfile.ProfileId
            description = $PhasePlan.PhaseProfile.Description
        }
        warmUp = [ordered]@{
            enabled = $PhasePlan.WarmUpEnabled
            duration = $PhasePlan.WarmUpDuration
            users = $PhasePlan.WarmUpUsers
            spawnRate = $PhasePlan.WarmUpSpawnRate
            startupModelCheckEnabled = $PhasePlan.WarmUpStartupModelCheckEnabled
            csvPrefix = $displayWarmUpCsvPrefix
        }
        measurement = [ordered]@{
            duration = $PhasePlan.MeasurementDuration
            users = $PhasePlan.MeasurementUsers
            spawnRate = $PhasePlan.MeasurementSpawnRate
            startupModelCheckEnabled = $PhasePlan.MeasurementStartupModelCheckEnabled
            csvPrefix = $displayMeasurementCsvPrefix
        }
    }

    Write-PortableArtifactJson -Path $OutputPath -Payload $payload -Depth 12
}
