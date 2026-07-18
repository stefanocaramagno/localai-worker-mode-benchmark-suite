param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path,
    [string]$ProfileConfig = "config\reporting\profiles\RP_C0_HISTORICAL_FIXED_CLUSTER.json",
    [string]$OutputRoot,
    [string]$ReportingId = "",
    [switch]$Archive,
    [switch]$ArchiveCurrent,
    [switch]$ForceArchive,
    [switch]$SkipReportingSiteUpdate,
    [switch]$UpdateReportingSite
)

$ErrorActionPreference = "Stop"

if ($Archive -and $ArchiveCurrent) {
    throw "Archive and ArchiveCurrent are mutually exclusive. Use -Archive to regenerate and archive, or -ArchiveCurrent to archive the existing report as-is."
}

function Resolve-ProjectPath {
    param(
        [string]$BasePath,
        [string]$PathValue
    )

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }

    return (Join-Path $BasePath $PathValue)
}

$profilePath = Resolve-ProjectPath -BasePath $RepoRoot -PathValue $ProfileConfig
$scriptPath = Join-Path $RepoRoot "scripts\analysis\generate-reporting.py"
$reportingSiteLauncher = Join-Path $RepoRoot "scripts\load\post\Start-ReportingSite.ps1"

if (-not (Test-Path $profilePath)) {
    throw "Reporting profile not found: $profilePath"
}
if (-not (Test-Path $scriptPath)) {
    throw "Reporting generator not found: $scriptPath"
}
if ((-not $SkipReportingSiteUpdate) -and (-not (Test-Path $reportingSiteLauncher))) {
    throw "Reporting-site launcher not found: $reportingSiteLauncher"
}

$profileData = Get-Content -Path $profilePath -Raw -Encoding UTF8 | ConvertFrom-Json

if ((-not $ArchiveCurrent) -and [string]::IsNullOrWhiteSpace($ReportingId)) {
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $cycleId = [string]$profileData.cycleId
    $prefix = [string]$profileData.reportingIdPrefix
    if ([string]::IsNullOrWhiteSpace($prefix)) {
        if ([string]::IsNullOrWhiteSpace($cycleId)) {
            $prefix = "REP_GENERAL"
        }
        else {
            $prefix = "REP_$cycleId"
        }
    }
    $ReportingId = "${prefix}_${timestamp}"
}

$explicitOutputRoot = -not [string]::IsNullOrWhiteSpace($OutputRoot)
$outputRootSelectionMode = "explicit"
if (-not $explicitOutputRoot) {
    $outputRootSelectionMode = "profile outputRoot"
    $OutputRoot = [string]$profileData.outputRoot
}
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    throw "Reporting output root is not defined. Set outputRoot in the reporting profile or pass -OutputRoot explicitly."
}
$outputPath = Resolve-ProjectPath -BasePath $RepoRoot -PathValue $OutputRoot

$argsList = @(
    $scriptPath,
    "--repo-root", $RepoRoot,
    "--profile-config", $profilePath,
    "--output-root", $outputPath
)

if (-not [string]::IsNullOrWhiteSpace($ReportingId)) {
    $argsList += @("--reporting-id", $ReportingId)
}

if ($Archive) {
    $argsList += "--archive"
}
if ($ArchiveCurrent) {
    $argsList += "--archive-current"
}
if ($ForceArchive) {
    $argsList += "--force-archive"
}

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " LocalAI Reporting and Visualization Launcher" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Repository   : $RepoRoot"
Write-Host "Profile      : $profilePath"
Write-Host "Output root  : $outputPath"
Write-Host "Output source: $outputRootSelectionMode"
Write-Host "Reporting ID : $(if ([string]::IsNullOrWhiteSpace($ReportingId)) { 'current manifest' } else { $ReportingId })"
Write-Host "Archive copy : $Archive"
Write-Host "Archive current : $ArchiveCurrent"
Write-Host "Force archive   : $ForceArchive"
$updateReportingSiteEffective = (-not $SkipReportingSiteUpdate)
if ($explicitOutputRoot -and (-not $UpdateReportingSite)) {
    $updateReportingSiteEffective = $false
}
Write-Host "Update site     : $updateReportingSiteEffective"
if ($explicitOutputRoot -and (-not $SkipReportingSiteUpdate) -and (-not $UpdateReportingSite)) {
    Write-Host "Update reason   : skipped automatically because -OutputRoot points to a non-canonical output location"
}
Write-Host ""

python @argsList
$reportingExitCode = $LASTEXITCODE
if ($reportingExitCode -ne 0) {
    exit $reportingExitCode
}

if ($updateReportingSiteEffective) {
    Write-Host ""
    Write-Host "Updating reporting site entry point..."
    & $reportingSiteLauncher -RepoRoot $RepoRoot
    $reportingSiteExitCode = $LASTEXITCODE
    if ($reportingSiteExitCode -ne 0) {
        exit $reportingSiteExitCode
    }
}

Write-Host ""
Write-Host "Reporting completed."
