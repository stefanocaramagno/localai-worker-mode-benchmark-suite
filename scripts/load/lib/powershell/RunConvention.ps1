Set-StrictMode -Version Latest

function Get-RunConvention {
    param(
        [Parameter(Mandatory = $false)]
        [string]$ConventionFile
    )

    if ([string]::IsNullOrWhiteSpace($ConventionFile)) {
        $scriptDir = Split-Path -Parent $PSCommandPath
        $repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..\..")).Path
        $ConventionFile = Join-Path $repoRoot "config\conventions\RC1.json"
    }

    if (-not (Test-Path $ConventionFile)) {
        throw "Il file di convenzione non esiste: $ConventionFile"
    }

    $data = Get-Content -Raw -Path $ConventionFile | ConvertFrom-Json

    $conventionId = if ($data.PSObject.Properties.Name -contains "conventionId") {
        [string]$data.conventionId
    }
    elseif ($data.PSObject.Properties.Name -contains "runConventionId") {
        [string]$data.runConventionId
    }
    else {
        $null
    }

    $runIdPattern = if ($data.PSObject.Properties.Name -contains "runIdPattern") {
        [string]$data.runIdPattern
    }
    elseif ($data.PSObject.Properties.Name -contains "runIdFormat") {
        [string]$data.runIdFormat
    }
    else {
        $null
    }

    $metadataFilePattern = if ($data.PSObject.Properties.Name -contains "metadataFilePattern") {
        [string]$data.metadataFilePattern
    }
    elseif ($data.PSObject.Properties.Name -contains "runManifestSuffix") {
        [string]$data.runManifestSuffix
    }
    else {
        $null
    }

    $csvPrefixPattern = if ($data.PSObject.Properties.Name -contains "csvPrefixPattern") {
        [string]$data.csvPrefixPattern
    }
    elseif ($data.PSObject.Properties.Name -contains "csvPrefixFormat") {
        [string]$data.csvPrefixFormat
    }
    else {
        $null
    }

    $missing = @()
    if ([string]::IsNullOrWhiteSpace($conventionId)) { $missing += "conventionId|runConventionId" }
    if ([string]::IsNullOrWhiteSpace([string]$data.version)) { $missing += "version" }
    if ([string]::IsNullOrWhiteSpace($runIdPattern)) { $missing += "runIdPattern|runIdFormat" }
    if ([string]::IsNullOrWhiteSpace($metadataFilePattern)) { $missing += "metadataFilePattern|runManifestSuffix" }
    if ([string]::IsNullOrWhiteSpace($csvPrefixPattern)) { $missing += "csvPrefixPattern|csvPrefixFormat" }

    if ($missing.Count -gt 0) {
        throw "Il file di convenzione '$ConventionFile' non contiene le proprietà obbligatorie: $($missing -join ', ')."
    }

    return [PSCustomObject]@{
        ConventionFile = (Resolve-Path $ConventionFile).Path
        ConventionId = $conventionId
        Version = [string]$data.version
        RunIdPattern = $runIdPattern
        MetadataFilePattern = $metadataFilePattern
        CsvPrefixPattern = $csvPrefixPattern
    }
}

function New-RunTimestampUtc {
    return (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
}

function Test-RunConventionComponent {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    if ($Value -notmatch '^[A-Za-z0-9._-]+$') {
        throw "Il componente '$Name' contiene caratteri non ammessi: $Value"
    }
}

function New-RunId {
    param(
        [Parameter(Mandatory = $true)][string]$Track,
        [Parameter(Mandatory = $true)][string]$Family,
        [Parameter(Mandatory = $true)][string]$Scenario,
        [Parameter(Mandatory = $true)][string]$Replica,
        [Parameter(Mandatory = $true)][string]$TimestampUtc
    )

    Test-RunConventionComponent -Name "track" -Value $Track
    Test-RunConventionComponent -Name "family" -Value $Family
    Test-RunConventionComponent -Name "scenario" -Value $Scenario
    Test-RunConventionComponent -Name "replica" -Value $Replica
    Test-RunConventionComponent -Name "timestampUtc" -Value $TimestampUtc

    return "${Track}_${Family}_${Scenario}_${Replica}_${TimestampUtc}"
}

function Get-RunCsvPrefix {
    param(
        [Parameter(Mandatory = $true)][string]$OutputDir,
        [Parameter(Mandatory = $true)][string]$RunId
    )

    return (Join-Path $OutputDir $RunId)
}

function Get-RunMetadataPath {
    param(
        [Parameter(Mandatory = $true)][string]$CsvPrefix
    )

    return "${CsvPrefix}_run.json"
}

function Write-RunMetadata {
    param(
        [Parameter(Mandatory = $true)]$Convention,
        [Parameter(Mandatory = $true)][string]$OutputPath,
        [Parameter(Mandatory = $true)][string]$RunId,
        [Parameter(Mandatory = $true)][string]$CreatedAtUtc,
        [Parameter(Mandatory = $true)][string]$Track,
        [Parameter(Mandatory = $true)][string]$Family,
        [Parameter(Mandatory = $true)][string]$Scenario,
        [Parameter(Mandatory = $true)][string]$Replica,
        [Parameter(Mandatory = $true)][string]$OutputDir,
        [Parameter(Mandatory = $true)][string]$CsvPrefix,
        [Parameter(Mandatory = $true)]$ContextObject
    )

    $payload = [ordered]@{
        runConvention = [ordered]@{
            conventionFile = $Convention.ConventionFile
            conventionId = $Convention.ConventionId
            version = $Convention.Version
            runIdPattern = $Convention.RunIdPattern
            metadataFilePattern = $Convention.MetadataFilePattern
            csvPrefixPattern = $Convention.CsvPrefixPattern
        }
        run = [ordered]@{
            runId = $RunId
            createdAtUtc = $CreatedAtUtc
            track = $Track
            family = $Family
            scenario = $Scenario
            replica = $Replica
            outputDir = $OutputDir
            csvPrefix = $CsvPrefix
        }
        context = $ContextObject
    }

    $payload | ConvertTo-Json -Depth 12 | Set-Content -Path $OutputPath -Encoding UTF8
}
