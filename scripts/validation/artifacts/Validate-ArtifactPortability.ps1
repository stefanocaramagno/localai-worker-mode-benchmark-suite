param(
  [string]$ResultsRoot = "results",
  [switch]$Json
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
  $scriptPath = $PSScriptRoot
  if (-not $scriptPath) {
    $scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
  }
  return (Resolve-Path (Join-Path $scriptPath "..\..\..")).Path
}

function Resolve-PythonCommand {
  foreach ($candidate in @("python", "py", "python3")) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($null -ne $command) {
      return $candidate
    }
  }
  throw "Python executable not found. Install Python or add it to PATH before running artifact portability validation."
}

$repoRoot = Resolve-RepoRoot
$validator = Join-Path $repoRoot "scripts\common\artifact_portability.py"
if (-not (Test-Path -LiteralPath $validator)) {
  throw "Common artifact portability validator not found: $validator"
}

$python = Resolve-PythonCommand
$arguments = @()
if ($python -eq "py") {
  $arguments += "-3"
}
$arguments += @(
  $validator,
  "--repo-root", $repoRoot,
  "--results-root", $ResultsRoot
)
if ($Json) {
  $arguments += "--json"
}

& $python @arguments
exit $LASTEXITCODE
