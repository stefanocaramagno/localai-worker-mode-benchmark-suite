param(
    [string]$ProfileConfig,
    [string]$DiagnosisJson,
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

    throw "Nessun interprete Python compatibile e' disponibile nel PATH. Verificare la disponibilita' di 'python', 'py -3' oppure 'python3'."
}

function Get-LatestAllDiagnosis {
    param([string]$RepositoryRoot)

    $diagnosisRoot = Join-Path $RepositoryRoot "results\diagnosis"
    if (-not (Test-Path $diagnosisRoot)) {
        throw "La cartella dei risultati di diagnosi non esiste: $diagnosisRoot"
    }

    $candidates = @()
    foreach ($path in Get-ChildItem -Path $diagnosisRoot -Filter "*_diagnosis.json" -File) {
        try {
            $raw = Get-Content -Path $path.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($raw.diagnosis.familyScope -eq "all") {
                $candidates += $path
            }
        }
        catch {
            continue
        }
    }

    if ($candidates.Count -eq 0) {
        throw "Impossibile individuare automaticamente una diagnosi tecnica 'all' in results/diagnosis."
    }

    return ($candidates | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1).FullName
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunConvention.ps1")

if ([string]::IsNullOrWhiteSpace($ResultsRoot) -eq $false) {
    $repoRoot = (Resolve-Path $ResultsRoot).Path
}

if ([string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $ProfileConfig = Join-Path $repoRoot "config\completion-gate\CG1.json"
}
if (-not (Test-Path $ProfileConfig)) {
    throw "Il file di profilo completion gate non esiste: $ProfileConfig"
}

if ([string]::IsNullOrWhiteSpace($DiagnosisJson)) {
    $DiagnosisJson = Get-LatestAllDiagnosis -RepositoryRoot $repoRoot
}
if (-not (Test-Path $DiagnosisJson)) {
    throw "Il file di diagnosi non esiste: $DiagnosisJson"
}

$pythonCommand = Resolve-PythonCommand

$profile = Get-Content -Path $ProfileConfig -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $repoRoot ([string]$profile.outputRoot -replace '/', '\\')
}
if (-not (Test-Path $OutputRoot)) {
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
}

$runTimestampUtc = New-RunTimestampUtc
$evaluationId = New-RunId -Track "analysis" -Family "completion-gate" -Scenario "all" -Replica "NA" -TimestampUtc $runTimestampUtc
$outputJson = Join-Path $OutputRoot ("{0}{1}" -f $evaluationId, [string]$profile.manifestSuffix)
$outputText = Join-Path $OutputRoot ("{0}{1}" -f $evaluationId, [string]$profile.textSuffix)
$pythonScript = Join-Path $repoRoot "scripts\analysis\evaluate-completion-gate.py"

if (-not (Test-Path $pythonScript)) {
    throw "Lo script di evaluation non esiste: $pythonScript"
}

$pythonInvocationPrefix = @($pythonCommand.Executable) + @($pythonCommand.PrefixArguments)
$cmd = @(
    $pythonInvocationPrefix + @(
        $pythonScript,
        "--profile-config", $ProfileConfig,
        "--diagnosis-json", $DiagnosisJson,
        "--output-json", $outputJson,
        "--output-text", $outputText,
        "--evaluation-id", $evaluationId
    )
)

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Completion Gate Launcher" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Repository            : $repoRoot"
Write-Host "Profile config        : $ProfileConfig"
Write-Host "Diagnosis JSON        : $DiagnosisJson"
Write-Host "Evaluation ID         : $evaluationId"
Write-Host "Output JSON           : $outputJson"
Write-Host "Output text           : $outputText"
Write-Host "Python executable     : $($pythonCommand.Executable)"
if ($pythonCommand.PrefixArguments.Count -gt 0) {
    Write-Host ("Python arguments      : " + ($pythonCommand.PrefixArguments -join " "))
}
Write-Host ""
Write-Host ("Command               : " + ($cmd -join " "))
Write-Host ""

if ($DryRun) {
    Write-Host "DRY RUN completato. Nessuna evaluation eseguita." -ForegroundColor Yellow
    exit 0
}

& $pythonCommand.Executable @($pythonCommand.PrefixArguments) $pythonScript `
    --profile-config $ProfileConfig `
    --diagnosis-json $DiagnosisJson `
    --output-json $outputJson `
    --output-text $outputText `
    --evaluation-id $evaluationId
