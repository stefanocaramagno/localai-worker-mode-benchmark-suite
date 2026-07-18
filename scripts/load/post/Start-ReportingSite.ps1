param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path,
    [string]$SiteConfig = "config\reporting\site\REPORTING_SITE.json",
    [string]$ReportingIndex = "",
    [string]$OutputRoot = "",
    [string]$SiteId = "",
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

function Resolve-ProjectPath {
    param(
        [string]$BasePath,
        [string]$PathValue
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return ""
    }

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }

    return (Join-Path $BasePath $PathValue)
}

$siteConfigPath = Resolve-ProjectPath -BasePath $RepoRoot -PathValue $SiteConfig
$scriptPath = Join-Path $RepoRoot "scripts\analysis\generate-reporting-site.py"

if (-not (Test-Path $siteConfigPath)) {
    throw "Reporting-site config not found: $siteConfigPath"
}
if (-not (Test-Path $scriptPath)) {
    throw "Reporting-site generator not found: $scriptPath"
}

$argsList = @(
    $scriptPath,
    "--repo-root", $RepoRoot,
    "--site-config", $siteConfigPath
)

if (-not [string]::IsNullOrWhiteSpace($ReportingIndex)) {
    $argsList += @("--reporting-index", (Resolve-ProjectPath -BasePath $RepoRoot -PathValue $ReportingIndex))
}
if (-not [string]::IsNullOrWhiteSpace($OutputRoot)) {
    $argsList += @("--output-root", (Resolve-ProjectPath -BasePath $RepoRoot -PathValue $OutputRoot))
}
if (-not [string]::IsNullOrWhiteSpace($SiteId)) {
    $argsList += @("--site-id", $SiteId)
}
if ($Strict) {
    $argsList += "--strict"
}

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " LocalAI Reporting Site Launcher" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Repository     : $RepoRoot"
Write-Host "Site config    : $siteConfigPath"
Write-Host "Reporting index: $(if ([string]::IsNullOrWhiteSpace($ReportingIndex)) { 'site config default' } else { $ReportingIndex })"
Write-Host "Output root    : $(if ([string]::IsNullOrWhiteSpace($OutputRoot)) { 'site config default' } else { $OutputRoot })"
Write-Host "Site ID        : $(if ([string]::IsNullOrWhiteSpace($SiteId)) { 'auto-generated' } else { $SiteId })"
Write-Host "Strict mode    : $Strict"
Write-Host ""

python @argsList
$reportingSiteExitCode = $LASTEXITCODE
if ($reportingSiteExitCode -ne 0) {
    exit $reportingSiteExitCode
}

Write-Host ""
Write-Host "Reporting site completed."
