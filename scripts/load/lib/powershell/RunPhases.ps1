Set-StrictMode -Version Latest

function Get-PhaseProfile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProfileFile
    )

    if (-not (Test-Path $ProfileFile)) {
        throw "Il file di profilo warm-up/misurazione non esiste: $ProfileFile"
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
            throw "Il file di profilo warm-up/misurazione '$ProfileFile' non contiene la proprietà obbligatoria '$propertyName'."
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
        default { throw "Modalità warm-up users non supportata: $($PhaseProfile.WarmUpUsersMode)" }
    }

    switch ($PhaseProfile.WarmUpSpawnRateMode) {
        "match_measurement" { $resolvedWarmUpSpawnRate = $MeasurementSpawnRate }
        default { throw "Modalità warm-up spawn rate non supportata: $($PhaseProfile.WarmUpSpawnRateMode)" }
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
        [Parameter(Mandatory = $true)][string]$OutputPath
    )

    $payload = [ordered]@{
        phaseProfile = [ordered]@{
            profileFile = $PhasePlan.PhaseProfile.ProfileFile
            profileId = $PhasePlan.PhaseProfile.ProfileId
            description = $PhasePlan.PhaseProfile.Description
        }
        warmUp = [ordered]@{
            enabled = $PhasePlan.WarmUpEnabled
            duration = $PhasePlan.WarmUpDuration
            users = $PhasePlan.WarmUpUsers
            spawnRate = $PhasePlan.WarmUpSpawnRate
            startupModelCheckEnabled = $PhasePlan.WarmUpStartupModelCheckEnabled
            csvPrefix = $PhasePlan.WarmUpCsvPrefix
        }
        measurement = [ordered]@{
            duration = $PhasePlan.MeasurementDuration
            users = $PhasePlan.MeasurementUsers
            spawnRate = $PhasePlan.MeasurementSpawnRate
            startupModelCheckEnabled = $PhasePlan.MeasurementStartupModelCheckEnabled
            csvPrefix = $PhasePlan.MeasurementCsvPrefix
        }
    }

    $payload | ConvertTo-Json -Depth 12 | Set-Content -Path $OutputPath -Encoding UTF8
}
