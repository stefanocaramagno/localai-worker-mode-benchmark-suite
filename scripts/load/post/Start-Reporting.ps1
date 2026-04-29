param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path,
    [string]$ProfileConfig = "config\reporting\RP1.json",
    [string]$OutputRoot,
    [string]$ReportingId = "",
    [switch]$Archive,
    [switch]$ArchiveCurrent,
    [switch]$ForceArchive
)

$ErrorActionPreference = "Stop"

if ($Archive -and $ArchiveCurrent) {
    throw "Archive and ArchiveCurrent are mutually exclusive. Use -Archive to regenerate and archive, or -ArchiveCurrent to archive the existing report as-is."
}

if ((-not $ArchiveCurrent) -and [string]::IsNullOrWhiteSpace($ReportingId)) {
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $ReportingId = "analysis_reporting_all_NA_$timestamp"
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

if (-not (Test-Path $profilePath)) {
    throw "Reporting profile not found: $profilePath"
}
if (-not (Test-Path $scriptPath)) {
    throw "Reporting generator not found: $scriptPath"
}

$profileData = Get-Content -Path $profilePath -Raw -Encoding UTF8 | ConvertFrom-Json
$outputRootSelectionMode = "explicit"
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
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
Write-Host ""

python @argsList

Write-Host ""
Write-Host "Reporting phase completed."
