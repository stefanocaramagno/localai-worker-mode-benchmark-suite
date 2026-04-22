Set-StrictMode -Version Latest

function Get-ProtocolProfile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProfileFile
    )

    if (-not (Test-Path $ProfileFile)) {
        throw "Il file di protocollo non esiste: $ProfileFile"
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
            throw "Il file di protocollo '$ProfileFile' non contiene la proprietà obbligatoria '$propertyName'."
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
        [string[]]$Arguments
    )

    $escaped = foreach ($argument in $Arguments) {
        if ($argument -match '[\s"]') {
            '"' + ($argument -replace '"', '\"') + '"'
        }
        else {
            $argument
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
        [string[]]$FinalSnapshotArtifacts = @()
    )

    $clientArtifacts = @()
    if ($WarmUpEnabled -and -not [string]::IsNullOrWhiteSpace($WarmUpCsvPrefix)) {
        $clientArtifacts += @(
            "${WarmUpCsvPrefix}_stats.csv",
            "${WarmUpCsvPrefix}_stats_history.csv",
            "${WarmUpCsvPrefix}_failures.csv",
            "${WarmUpCsvPrefix}_exceptions.csv"
        )
    }

    $clientArtifacts += @(
        "${MeasurementCsvPrefix}_stats.csv",
        "${MeasurementCsvPrefix}_stats_history.csv",
        "${MeasurementCsvPrefix}_failures.csv",
        "${MeasurementCsvPrefix}_exceptions.csv"
    )

    $payload = [ordered]@{
        protocolProfile = [ordered]@{
            profileFile = $ProtocolProfile.ProfileFile
            profileId = $ProtocolProfile.ProfileId
            description = $ProtocolProfile.Description
            steps = $ProtocolProfile.Steps
        }
        launcher = $LauncherName
        runId = $RunId
        steps = [ordered]@{
            cleanupControlled = [ordered]@{ required = $true; mode = "manual"; note = $CleanupNote }
            deployScenario = [ordered]@{ required = $true; mode = "manual"; recommendedApplyOrder = $RecommendedApplyOrder }
            technicalPrecheck = [ordered]@{ enabled = $PrecheckEnabled; mode = "automated"; command = $PrecheckCommand; artifacts = [ordered]@{ json = $PrecheckJsonPath; text = $PrecheckTextPath } }
            apiSmokeValidation = [ordered]@{ enabled = $ApiSmokeEnabled; mode = "automated"; command = $ApiSmokeCommand; model = $ApiSmokeModel }
            warmUp = [ordered]@{ enabled = $WarmUpEnabled; mode = "automated_optional"; command = $WarmUpCommand; csvPrefix = $WarmUpCsvPrefix }
            measurement = [ordered]@{ enabled = $true; mode = "automated"; command = $MeasurementCommand; csvPrefix = $MeasurementCsvPrefix }
            collectClientMetrics = [ordered]@{ enabled = $true; mode = "automatic_artifact"; artifacts = $clientArtifacts }
            collectClusterMetrics = [ordered]@{ enabled = $ClusterCollectionEnabled; mode = "automated_required"; command = $ClusterCollectionCommand; artifacts = $ClusterCollectionArtifacts }
            finalSnapshot = [ordered]@{ enabled = $FinalSnapshotEnabled; mode = "automated_required"; command = $FinalSnapshotCommand; artifacts = $FinalSnapshotArtifacts }
            cleanupOrRestore = [ordered]@{ enabled = $false; mode = "manual_placeholder"; note = "Placeholder for controlled cleanup or restore to baseline state." }
        }
        artifacts = [ordered]@{ phaseManifest = $PhaseManifestPath; extra = $ExtraArtifacts }
    }

    $payload | ConvertTo-Json -Depth 20 | Set-Content -Path $ManifestPath -Encoding UTF8

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
    if ($RecommendedApplyOrder.Count -gt 0) {
        $lines.Add("  Recommended apply order:")
        foreach ($item in $RecommendedApplyOrder) { $lines.Add("   - $item") }
    }
    else {
        $lines.Add("  Recommended apply order: not applicable for this launcher.")
    }
    $lines.Add("")
    $lines.Add("[S03] technical_precheck")
    $lines.Add("  Enabled: $($PrecheckEnabled.ToString().ToLower())")
    if ($PrecheckEnabled) {
        $lines.Add("  Command: $PrecheckCommand")
        $lines.Add("  JSON artifact: $PrecheckJsonPath")
        $lines.Add("  Text artifact: $PrecheckTextPath")
    }
    $lines.Add("")
    $lines.Add("[S04] api_smoke_validation")
    $lines.Add("  Enabled: $($ApiSmokeEnabled.ToString().ToLower())")
    if ($ApiSmokeEnabled) {
        $lines.Add("  Command: $ApiSmokeCommand")
        $lines.Add("  Model: $ApiSmokeModel")
    }
    $lines.Add("")
    $lines.Add("[S05] warm_up")
    $lines.Add("  Enabled: $($WarmUpEnabled.ToString().ToLower())")
    if ($WarmUpEnabled) {
        $lines.Add("  Command: $WarmUpCommand")
        $lines.Add("  CSV prefix: $WarmUpCsvPrefix")
    }
    $lines.Add("")
    $lines.Add("[S06] measurement")
    $lines.Add("  Command: $MeasurementCommand")
    $lines.Add("  CSV prefix: $MeasurementCsvPrefix")
    $lines.Add("")
    $lines.Add("[S07] collect_client_metrics")
    foreach ($artifact in $clientArtifacts) { $lines.Add("   - $artifact") }
    $lines.Add("")
    $lines.Add("[S08] collect_cluster_metrics")
    $lines.Add("  Enabled: $($ClusterCollectionEnabled.ToString().ToLower())")
    if ($ClusterCollectionEnabled) {
        $lines.Add("  Command: $ClusterCollectionCommand")
        foreach ($artifact in $ClusterCollectionArtifacts) { $lines.Add("   - $artifact") }
    }
    $lines.Add("")
    $lines.Add("[S09] final_snapshot")
    $lines.Add("  Enabled: $($FinalSnapshotEnabled.ToString().ToLower())")
    if ($FinalSnapshotEnabled) {
        $lines.Add("  Command: $FinalSnapshotCommand")
        foreach ($artifact in $FinalSnapshotArtifacts) { $lines.Add("   - $artifact") }
    }
    $lines.Add("")
    $lines.Add("[S10] cleanup_or_restore")
    $lines.Add("  Placeholder: apply controlled cleanup or restore policy.")
    $lines.Add("")
    $lines.Add("Phase manifest: $PhaseManifestPath")
    if ($ExtraArtifacts.Count -gt 0) {
        $lines.Add("Extra artifacts:")
        foreach ($artifact in $ExtraArtifacts) { $lines.Add(" - $artifact") }
    }

    $lines -join [Environment]::NewLine | Set-Content -Path $TextPath -Encoding UTF8
}
