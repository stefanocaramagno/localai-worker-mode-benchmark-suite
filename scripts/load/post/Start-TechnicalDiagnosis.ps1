param(
    [string]$ProfileConfig,
    [ValidateSet("worker-count", "workload", "models", "placement", "resource-variation", "node-count-variation", "placement-variation", "latency-injection", "multi-tenancy", "default-scheduler", "all")]
    [string]$Family = "all",
    [string]$OutputRoot,
    [string]$ResultsRoot,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Test-CommandAvailable {
    param([string]$CommandName)
    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
    return $null -ne $cmd
}

function Resolve-PythonCommand {
    $candidates = @(
        @{ Executable = "python";  PrefixArguments = @() },
        @{ Executable = "py";      PrefixArguments = @("-3") },
        @{ Executable = "python3"; PrefixArguments = @() }
    )

    foreach ($candidate in $candidates) {
        $executable = [string]$candidate.Executable
        if (-not (Test-CommandAvailable -CommandName $executable)) {
            continue
        }

        try {
            $null = & $executable @($candidate.PrefixArguments + @("--version")) 2>$null
            if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq $null) {
                return [pscustomobject]@{
                    Executable      = $executable
                    PrefixArguments = @($candidate.PrefixArguments)
                }
            }
        }
        catch {
            continue
        }
    }

    throw "No compatible Python interpreter is available in PATH. Verify that 'python', 'py -3', or 'python3' is available."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunConvention.ps1")

$pythonCommand = Resolve-PythonCommand

if (-not [string]::IsNullOrWhiteSpace($ResultsRoot)) {
    $repoRoot = (Resolve-Path $ResultsRoot).Path
}

if ([string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $ProfileConfig = Join-Path $repoRoot "config\technical-diagnosis\profiles\TD_C0_HISTORICAL_FIXED_CLUSTER.json"
}

if (-not (Test-Path $ProfileConfig)) {
    throw "The diagnosis profile file does not exist: $ProfileConfig"
}

$profileData = Get-Content -Path $ProfileConfig -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $repoRoot ([string]$profileData.outputRoot -replace '/', '\\')
}

if (-not (Test-Path $OutputRoot)) {
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
}

$runTimestampUtc = New-RunTimestampUtc
$diagnosisId = New-RunId -Track "analysis" -Family "diagnosis" -Scenario $Family -Replica "NA" -TimestampUtc $runTimestampUtc
$outputJson = Join-Path $OutputRoot ("{0}_diagnosis.json" -f $diagnosisId)
$outputText = Join-Path $OutputRoot ("{0}_diagnosis.txt" -f $diagnosisId)
$pythonScript = Join-Path $repoRoot "scripts\analysis\generate-technical-diagnosis.py"

if (-not (Test-Path $pythonScript)) {
    throw "The diagnosis script does not exist: $pythonScript"
}

$pythonInvocationPrefix = @($pythonCommand.Executable) + @($pythonCommand.PrefixArguments)
$cmdArgs = @(
    $pythonInvocationPrefix + @(
        $pythonScript,
        "--repo-root", $repoRoot,
        "--profile-config", $ProfileConfig,
        "--family", $Family,
        "--output-json", $outputJson,
        "--output-text", $outputText,
        "--diagnosis-id", $diagnosisId
    )
)

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Initial Technical Diagnosis Launcher" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Repository            : $repoRoot"
Write-Host "Profile config        : $ProfileConfig"
Write-Host "Family scope          : $Family"
Write-Host "Diagnosis ID          : $diagnosisId"
Write-Host "Output JSON           : $outputJson"
Write-Host "Output text           : $outputText"
Write-Host "Python executable     : $($pythonCommand.Executable)"
if ($pythonCommand.PrefixArguments.Count -gt 0) {
    Write-Host ("Python arguments      : " + ($pythonCommand.PrefixArguments -join " "))
}
Write-Host ""
Write-Host ("Command               : {0}" -f ($cmdArgs -join ' '))
Write-Host ""

if ($DryRun) {
    Write-Host "DRY RUN completed. No diagnosis was executed." -ForegroundColor Yellow
    exit 0
}

& $pythonCommand.Executable @($pythonCommand.PrefixArguments) $pythonScript `
    --repo-root $repoRoot `
    --profile-config $ProfileConfig `
    --family $Family `
    --output-json $outputJson `
    --output-text $outputText `
    --diagnosis-id $diagnosisId

$diagnosisExitCode = $LASTEXITCODE
if ($diagnosisExitCode -ne 0) {
    Write-Error "Technical diagnosis failed with exit code $diagnosisExitCode."
    exit $diagnosisExitCode
}
