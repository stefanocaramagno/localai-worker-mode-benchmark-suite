param(
    [string]$ProfileConfig,
    [string]$CycleConfig,
    [string]$DiagnosisJson,
    [string]$OutputRoot,
    [string]$RepositoryRoot,
    [string]$EvaluationId,
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
        if (-not (Test-CommandAvailable -CommandName $executable)) { continue }
        try {
            $null = & $executable @($candidate.PrefixArguments + @("--version")) 2>$null
            if ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE) {
                return [pscustomobject]@{ Executable = $executable; PrefixArguments = @($candidate.PrefixArguments) }
            }
        } catch { }
    }
    throw "No compatible Python interpreter found in PATH. Expected 'python', 'py -3' or 'python3'."
}

function Resolve-RepoPath {
    param([string]$RepoRoot, [string]$PathValue)
    if ([string]::IsNullOrWhiteSpace($PathValue)) { return $null }
    if ([System.IO.Path]::IsPathRooted($PathValue)) { return $PathValue }
    return (Join-Path $RepoRoot $PathValue)
}

function Get-JsonValue {
    param(
        [string]$Path,
        [string]$Expression,
        [string]$DefaultValue = ""
    )
    if (-not (Test-Path $Path)) { return $DefaultValue }
    $data = Get-Content -Path $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    $current = $data
    foreach ($part in $Expression.Split('.')) {
        if ($null -ne $current -and ($current.PSObject.Properties.Name -contains $part)) {
            $current = $current.$part
        } else {
            return $DefaultValue
        }
    }
    if ($null -eq $current -or [string]::IsNullOrWhiteSpace([string]$current)) { return $DefaultValue }
    return [string]$current
}

function Resolve-CompletionProfileFromCycle {
    param([string]$Path)
    $cycle = Get-Content -Path $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($cycle.PSObject.Properties.Name -contains "completionGate" -and $cycle.completionGate.completionGateProfilePath) {
        return [string]$cycle.completionGate.completionGateProfilePath
    }
    if ($cycle.PSObject.Properties.Name -contains "providerBackedInfrastructure" -and $cycle.providerBackedInfrastructure.completionGateProfilePath) {
        return [string]$cycle.providerBackedInfrastructure.completionGateProfilePath
    }
    if ($cycle.PSObject.Properties.Name -contains "pipelineProfiles" -and $cycle.pipelineProfiles.completionGate) {
        return [string]$cycle.pipelineProfiles.completionGate
    }
    return ""
}

function Find-LatestAllDiagnosis {
    param([string]$RepoRoot, $PythonCommand)
    $script = @'
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
repo = Path(sys.argv[1])
roots = [repo / "results" / "experimental-cycles" / "C1" / "diagnosis", repo / "results" / "diagnosis"]
candidates = []
for root in roots:
    if not root.exists():
        continue
    for path in root.glob("*_diagnosis.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if data.get("diagnosis", {}).get("familyScope") != "all":
            continue
        score = path.stat().st_mtime
        created = data.get("diagnosis", {}).get("createdAtUtc")
        if created:
            try:
                score = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
        else:
            match = re.search(r"(\d{8}T\d{6}Z)", path.name)
            if match:
                try:
                    score = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
                except Exception:
                    pass
        candidates.append((score, path))
if not candidates:
    sys.exit(1)
print(str(max(candidates, key=lambda item: item[0])[1]))
'@
    $result = & $PythonCommand.Executable @($PythonCommand.PrefixArguments) -c $script $RepoRoot
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($result)) {
        throw "Unable to find a technical diagnosis artifact automatically. Provide -DiagnosisJson explicitly."
    }
    return [string]$result
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path
if (-not [string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $repoRoot = (Resolve-Path $RepositoryRoot).Path
}

if (-not [string]::IsNullOrWhiteSpace($CycleConfig)) {
    $CycleConfig = Resolve-RepoPath -RepoRoot $repoRoot -PathValue $CycleConfig
}

if (-not [string]::IsNullOrWhiteSpace($CycleConfig) -and [string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $ProfileConfig = Resolve-CompletionProfileFromCycle -Path $CycleConfig
}

if ([string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $ProfileConfig = Join-Path $repoRoot "config\completion-gate\profiles\CG_C0_HISTORICAL_FIXED_CLUSTER.json"
} else {
    $ProfileConfig = Resolve-RepoPath -RepoRoot $repoRoot -PathValue $ProfileConfig
}

if (-not (Test-Path $ProfileConfig)) {
    throw "Completion gate profile not found: $ProfileConfig"
}

$pythonCommand = Resolve-PythonCommand
$schemaVersion = Get-JsonValue -Path $ProfileConfig -Expression "schemaVersion" -DefaultValue ""

if ($schemaVersion -ne "completion-gate-profile/v1" -and [string]::IsNullOrWhiteSpace($DiagnosisJson)) {
    $DiagnosisJson = Find-LatestAllDiagnosis -RepoRoot $repoRoot -PythonCommand $pythonCommand
}

if (-not [string]::IsNullOrWhiteSpace($DiagnosisJson)) {
    $DiagnosisJson = Resolve-RepoPath -RepoRoot $repoRoot -PathValue $DiagnosisJson
    if (-not (Test-Path $DiagnosisJson)) { throw "Diagnosis JSON not found: $DiagnosisJson" }
}

$outputRootRel = Get-JsonValue -Path $ProfileConfig -Expression "outputRoot" -DefaultValue "results/experimental-cycles/C0/completion-gate"
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Resolve-RepoPath -RepoRoot $repoRoot -PathValue $outputRootRel
}
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

if ([string]::IsNullOrWhiteSpace($EvaluationId)) {
    $runConventionScript = Join-Path $repoRoot "scripts\load\lib\powershell\RunConvention.ps1"
    . $runConventionScript
    $timestamp = New-RunTimestampUtc
    $EvaluationId = New-RunId -Track "analysis" -Family "completion-gate" -Scenario "all" -Replica "NA" -TimestampUtc $timestamp
}

$manifestSuffix = Get-JsonValue -Path $ProfileConfig -Expression "manifestSuffix" -DefaultValue "_completion_gate.json"
$textSuffix = Get-JsonValue -Path $ProfileConfig -Expression "textSuffix" -DefaultValue "_completion_gate.txt"
$outputJson = Join-Path $OutputRoot "${EvaluationId}${manifestSuffix}"
$outputText = Join-Path $OutputRoot "${EvaluationId}${textSuffix}"
$pythonScript = Join-Path $repoRoot "scripts\analysis\evaluate-completion-gate.py"

$argsList = @(
    $pythonScript,
    "--profile-config", $ProfileConfig,
    "--repo-root", $repoRoot,
    "--output-json", $outputJson,
    "--output-text", $outputText,
    "--evaluation-id", $EvaluationId
)
if (-not [string]::IsNullOrWhiteSpace($CycleConfig)) { $argsList += @("--cycle-config", $CycleConfig) }
if (-not [string]::IsNullOrWhiteSpace($DiagnosisJson)) { $argsList += @("--diagnosis-json", $DiagnosisJson) }
if ($DryRun) { $argsList += "--dry-run" }

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Completion Gate Launcher" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Repository        : $repoRoot"
Write-Host "Cycle config      : $(if ([string]::IsNullOrWhiteSpace($CycleConfig)) { 'not provided' } else { $CycleConfig })"
Write-Host "Profile config    : $ProfileConfig"
Write-Host "Diagnosis JSON    : $(if ([string]::IsNullOrWhiteSpace($DiagnosisJson)) { 'auto-resolved by provider-aware profile' } else { $DiagnosisJson })"
Write-Host "Evaluation ID     : $EvaluationId"
Write-Host "Output JSON       : $outputJson"
Write-Host "Output text       : $outputText"
Write-Host "Python executable : $($pythonCommand.Executable)"
Write-Host ""
Write-Host ("Command           : " + (($pythonCommand.Executable, $pythonCommand.PrefixArguments, $argsList) -join " "))
Write-Host ""

& $pythonCommand.Executable @($pythonCommand.PrefixArguments) @argsList
exit $LASTEXITCODE
