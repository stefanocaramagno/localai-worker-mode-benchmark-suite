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

$script:RunProtocolRepositoryRoot = $null
try {
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        $candidateRoot = Join-Path $PSScriptRoot "..\..\..\.."
        if (Test-Path $candidateRoot) {
            $script:RunProtocolRepositoryRoot = (Resolve-Path $candidateRoot).Path
        }
    }
}
catch {
    $script:RunProtocolRepositoryRoot = $null
}

function Get-RunProtocolRepositoryRoot {
    param([AllowNull()][string]$RepositoryRoot)

    if (-not [string]::IsNullOrWhiteSpace($RepositoryRoot)) { return (Resolve-Path $RepositoryRoot).Path }
    if (-not [string]::IsNullOrWhiteSpace($script:RunProtocolRepositoryRoot)) { return $script:RunProtocolRepositoryRoot }
    return $null
}

function ConvertTo-RunProtocolPortableString {
    param(
        [AllowNull()][string]$Value,
        [AllowNull()][string]$RepositoryRoot
    )

    if ([string]::IsNullOrWhiteSpace($Value)) { return $Value }
    $portableValue = ([string]$Value) -replace '\\', '/'
    if ($portableValue.Trim() -match '^[A-Za-z][A-Za-z0-9+.-]*://') { return [string]$Value }

    $rootValue = Get-RunProtocolRepositoryRoot -RepositoryRoot $RepositoryRoot
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


function Get-ProtocolProfile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProfileFile
    )

    if (-not (Test-Path $ProfileFile)) {
        throw "The protocol file does not exist: $ProfileFile"
    }

    $data = Get-Content -Path $ProfileFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $requiredProperties = @(
        "profileId",
        "description",
        "apiSmokeEnabledDefault",
        "apiSmokeScriptRelativePathBash",
        "apiSmokeScriptRelativePathPowerShell",
        "protocolManifestSuffix",
        "protocolTextSuffix",
        "steps"
    )

    foreach ($propertyName in $requiredProperties) {
        if (-not ($data.PSObject.Properties.Name -contains $propertyName)) {
            throw "The protocol file '$ProfileFile' does not contain the required property '$propertyName'."
        }
    }

    return [pscustomobject]@{
        ProfileFile = (Resolve-Path $ProfileFile).Path
        ProfileId = [string]$data.profileId
        Description = [string]$data.description
        ApiSmokeEnabledDefault = [bool]$data.apiSmokeEnabledDefault
        ApiSmokeScriptRelativePathBash = [string]$data.apiSmokeScriptRelativePathBash
        ApiSmokeScriptRelativePathPowerShell = [string]$data.apiSmokeScriptRelativePathPowerShell
        ProtocolManifestSuffix = [string]$data.protocolManifestSuffix
        ProtocolTextSuffix = [string]$data.protocolTextSuffix
        Steps = @($data.steps)
    }
}

function Get-ProtocolPaths {
    param(
        [Parameter(Mandatory = $true)]
        [string]$MeasurementCsvPrefix,
        [Parameter(Mandatory = $true)]$ProtocolProfile
    )

    return [pscustomobject]@{
        ManifestPath = "${MeasurementCsvPrefix}$($ProtocolProfile.ProtocolManifestSuffix)"
        TextPath = "${MeasurementCsvPrefix}$($ProtocolProfile.ProtocolTextSuffix)"
    }
}

function New-ProtocolCommandString {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [AllowNull()][string]$RepositoryRoot
    )

    $escaped = foreach ($argument in $Arguments) {
        $portableArgument = ConvertTo-RunProtocolPortableString -Value $argument -RepositoryRoot $RepositoryRoot
        if ($portableArgument -match '[\s"]') {
            '"' + ($portableArgument -replace '"', '\"') + '"'
        }
        else {
            $portableArgument
        }
    }

    return ($escaped -join ' ')
}

function Write-ProtocolFiles {
    param(
        [Parameter(Mandatory = $true)]$ProtocolProfile,
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$TextPath,
        [Parameter(Mandatory = $true)][string]$LauncherName,
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][string]$CleanupNote,
        [string[]]$RecommendedApplyOrder = @(),
        [Parameter(Mandatory = $true)][bool]$PrecheckEnabled,
        [Parameter(Mandatory = $true)][string]$PrecheckCommand,
        [Parameter(Mandatory = $true)][string]$PrecheckJsonPath,
        [Parameter(Mandatory = $true)][string]$PrecheckTextPath,
        [Parameter(Mandatory = $true)][bool]$ApiSmokeEnabled,
        [Parameter(Mandatory = $true)][string]$ApiSmokeCommand,
        [Parameter(Mandatory = $true)][string]$ApiSmokeModel,
        [Parameter(Mandatory = $true)][bool]$WarmUpEnabled,
        [Parameter(Mandatory = $true)][string]$WarmUpCommand,
        [Parameter(Mandatory = $true)][string]$WarmUpCsvPrefix,
        [Parameter(Mandatory = $true)][string]$MeasurementCommand,
        [Parameter(Mandatory = $true)][string]$MeasurementCsvPrefix,
        [Parameter(Mandatory = $true)][string]$PhaseManifestPath,
        [string[]]$ExtraArtifacts = @(),
        [Parameter(Mandatory = $true)][bool]$ClusterCollectionEnabled,
        [Parameter(Mandatory = $true)][string]$ClusterCollectionCommand,
        [string[]]$ClusterCollectionArtifacts = @(),
        [Parameter(Mandatory = $true)][bool]$FinalSnapshotEnabled,
        [Parameter(Mandatory = $true)][string]$FinalSnapshotCommand,
        [string[]]$FinalSnapshotArtifacts = @(),
        [AllowNull()][string]$RepositoryRoot
    )

    $displayProfileFile = ConvertTo-RunProtocolPortableString -Value $ProtocolProfile.ProfileFile -RepositoryRoot $RepositoryRoot
    $displayRecommendedApplyOrder = @($RecommendedApplyOrder | ForEach-Object { ConvertTo-RunProtocolPortableString -Value $_ -RepositoryRoot $RepositoryRoot })
    $displayPrecheckCommand = ConvertTo-RunProtocolPortableString -Value $PrecheckCommand -RepositoryRoot $RepositoryRoot
    $displayPrecheckJsonPath = ConvertTo-RunProtocolPortableString -Value $PrecheckJsonPath -RepositoryRoot $RepositoryRoot
    $displayPrecheckTextPath = ConvertTo-RunProtocolPortableString -Value $PrecheckTextPath -RepositoryRoot $RepositoryRoot
    $displayApiSmokeCommand = ConvertTo-RunProtocolPortableString -Value $ApiSmokeCommand -RepositoryRoot $RepositoryRoot
    $displayWarmUpCommand = ConvertTo-RunProtocolPortableString -Value $WarmUpCommand -RepositoryRoot $RepositoryRoot
    $displayWarmUpCsvPrefix = ConvertTo-RunProtocolPortableString -Value $WarmUpCsvPrefix -RepositoryRoot $RepositoryRoot
    $displayMeasurementCommand = ConvertTo-RunProtocolPortableString -Value $MeasurementCommand -RepositoryRoot $RepositoryRoot
    $displayMeasurementCsvPrefix = ConvertTo-RunProtocolPortableString -Value $MeasurementCsvPrefix -RepositoryRoot $RepositoryRoot
    $displayPhaseManifestPath = ConvertTo-RunProtocolPortableString -Value $PhaseManifestPath -RepositoryRoot $RepositoryRoot
    $displayExtraArtifacts = @($ExtraArtifacts | ForEach-Object { ConvertTo-RunProtocolPortableString -Value $_ -RepositoryRoot $RepositoryRoot })
    $displayClusterCollectionCommand = ConvertTo-RunProtocolPortableString -Value $ClusterCollectionCommand -RepositoryRoot $RepositoryRoot
    $displayClusterCollectionArtifacts = @($ClusterCollectionArtifacts | ForEach-Object { ConvertTo-RunProtocolPortableString -Value $_ -RepositoryRoot $RepositoryRoot })
    $displayFinalSnapshotCommand = ConvertTo-RunProtocolPortableString -Value $FinalSnapshotCommand -RepositoryRoot $RepositoryRoot
    $displayFinalSnapshotArtifacts = @($FinalSnapshotArtifacts | ForEach-Object { ConvertTo-RunProtocolPortableString -Value $_ -RepositoryRoot $RepositoryRoot })

    $clientArtifacts = @()
    if ($WarmUpEnabled -and -not [string]::IsNullOrWhiteSpace($displayWarmUpCsvPrefix)) {
        $clientArtifacts += @(
            "${displayWarmUpCsvPrefix}_stats.csv",
            "${displayWarmUpCsvPrefix}_stats_history.csv",
            "${displayWarmUpCsvPrefix}_failures.csv",
            "${displayWarmUpCsvPrefix}_exceptions.csv"
        )
    }

    $clientArtifacts += @(
        "${displayMeasurementCsvPrefix}_stats.csv",
        "${displayMeasurementCsvPrefix}_stats_history.csv",
        "${displayMeasurementCsvPrefix}_failures.csv",
        "${displayMeasurementCsvPrefix}_exceptions.csv"
    )

    $payload = [ordered]@{
        protocolProfile = [ordered]@{
            profileFile = $displayProfileFile
            profileId = $ProtocolProfile.ProfileId
            description = $ProtocolProfile.Description
            steps = $ProtocolProfile.Steps
        }
        launcher = $LauncherName
        runId = $RunId
        steps = [ordered]@{
            cleanupControlled = [ordered]@{ required = $true; mode = "manual"; note = $CleanupNote }
            deployScenario = [ordered]@{ required = $true; mode = "manual"; recommendedApplyOrder = $displayRecommendedApplyOrder }
            technicalPrecheck = [ordered]@{ enabled = $PrecheckEnabled; mode = "automated"; command = $displayPrecheckCommand; artifacts = [ordered]@{ json = $displayPrecheckJsonPath; text = $displayPrecheckTextPath } }
            apiSmokeValidation = [ordered]@{ enabled = $ApiSmokeEnabled; mode = "automated"; command = $displayApiSmokeCommand; model = $ApiSmokeModel }
            warmUp = [ordered]@{ enabled = $WarmUpEnabled; mode = "automated_optional"; command = $displayWarmUpCommand; csvPrefix = $displayWarmUpCsvPrefix }
            measurement = [ordered]@{ enabled = $true; mode = "automated"; command = $displayMeasurementCommand; csvPrefix = $displayMeasurementCsvPrefix }
            collectClientMetrics = [ordered]@{ enabled = $true; mode = "automatic_artifact"; artifacts = $clientArtifacts }
            collectClusterMetrics = [ordered]@{ enabled = $ClusterCollectionEnabled; mode = "automated_required"; command = $displayClusterCollectionCommand; artifacts = $displayClusterCollectionArtifacts }
            finalSnapshot = [ordered]@{ enabled = $FinalSnapshotEnabled; mode = "automated_required"; command = $displayFinalSnapshotCommand; artifacts = $displayFinalSnapshotArtifacts }
            cleanupOrRestore = [ordered]@{ enabled = $false; mode = "manual_placeholder"; note = "Placeholder for controlled cleanup or restore to baseline state." }
        }
        artifacts = [ordered]@{ phaseManifest = $displayPhaseManifestPath; extra = $displayExtraArtifacts }
    }

    Write-PortableArtifactJson -Path $ManifestPath -Payload $payload -Depth 20

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("=============================================")
    $lines.Add(" Standard Execution Protocol")
    $lines.Add("=============================================")
    $lines.Add("Protocol profile : $($ProtocolProfile.ProfileId)")
    $lines.Add("Description      : $($ProtocolProfile.Description)")
    $lines.Add("Launcher         : $LauncherName")
    $lines.Add("Run ID           : $RunId")
    $lines.Add("")
    $lines.Add("[S01] cleanup_controlled")
    $lines.Add("  Note: $CleanupNote")
    $lines.Add("")
    $lines.Add("[S02] deploy_scenario")
    if ($displayRecommendedApplyOrder.Count -gt 0) {
        $lines.Add("  Recommended apply order:")
        foreach ($item in $displayRecommendedApplyOrder) { $lines.Add("   - $item") }
    }
    else {
        $lines.Add("  Recommended apply order: not applicable for this launcher.")
    }
    $lines.Add("")
    $lines.Add("[S03] technical_precheck")
    $lines.Add("  Enabled: $($PrecheckEnabled.ToString().ToLower())")
    if ($PrecheckEnabled) {
        $lines.Add("  Command: $displayPrecheckCommand")
        $lines.Add("  JSON artifact: $displayPrecheckJsonPath")
        $lines.Add("  Text artifact: $displayPrecheckTextPath")
    }
    $lines.Add("")
    $lines.Add("[S04] api_smoke_validation")
    $lines.Add("  Enabled: $($ApiSmokeEnabled.ToString().ToLower())")
    if ($ApiSmokeEnabled) {
        $lines.Add("  Command: $displayApiSmokeCommand")
        $lines.Add("  Model: $ApiSmokeModel")
    }
    $lines.Add("")
    $lines.Add("[S05] warm_up")
    $lines.Add("  Enabled: $($WarmUpEnabled.ToString().ToLower())")
    if ($WarmUpEnabled) {
        $lines.Add("  Command: $displayWarmUpCommand")
        $lines.Add("  CSV prefix: $displayWarmUpCsvPrefix")
    }
    $lines.Add("")
    $lines.Add("[S06] measurement")
    $lines.Add("  Command: $displayMeasurementCommand")
    $lines.Add("  CSV prefix: $displayMeasurementCsvPrefix")
    $lines.Add("")
    $lines.Add("[S07] collect_client_metrics")
    foreach ($artifact in $clientArtifacts) { $lines.Add("   - $artifact") }
    $lines.Add("")
    $lines.Add("[S08] collect_cluster_metrics")
    $lines.Add("  Enabled: $($ClusterCollectionEnabled.ToString().ToLower())")
    if ($ClusterCollectionEnabled) {
        $lines.Add("  Command: $displayClusterCollectionCommand")
        foreach ($artifact in $displayClusterCollectionArtifacts) { $lines.Add("   - $artifact") }
    }
    $lines.Add("")
    $lines.Add("[S09] final_snapshot")
    $lines.Add("  Enabled: $($FinalSnapshotEnabled.ToString().ToLower())")
    if ($FinalSnapshotEnabled) {
        $lines.Add("  Command: $displayFinalSnapshotCommand")
        foreach ($artifact in $displayFinalSnapshotArtifacts) { $lines.Add("   - $artifact") }
    }
    $lines.Add("")
    $lines.Add("[S10] cleanup_or_restore")
    $lines.Add("  Placeholder: apply controlled cleanup or restore policy.")
    $lines.Add("")
    $lines.Add("Phase manifest: $displayPhaseManifestPath")
    if ($displayExtraArtifacts.Count -gt 0) {
        $lines.Add("Extra artifacts:")
        foreach ($artifact in $displayExtraArtifacts) { $lines.Add(" - $artifact") }
    }

    Write-PortableArtifactText -Path $TextPath -Text ($lines -join [Environment]::NewLine)
}
