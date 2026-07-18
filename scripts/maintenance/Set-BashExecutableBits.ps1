param(
    [switch]$SkipGitIndex
)

$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Set-Location $repoRoot

function Test-GitRepository {
    try {
        git rev-parse --is-inside-work-tree *> $null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

function Convert-ToRepositoryRelativePath {
    param([string]$Path)

    return (Resolve-Path -Relative $Path).Replace('\\', '/') -replace '^\./', ''
}

$insideGitRepository = Test-GitRepository
$bashScripts = Get-ChildItem -Path 'scripts' -Recurse -Filter '*.sh' -File | Sort-Object FullName

foreach ($scriptInfo in $bashScripts) {
    $script = Convert-ToRepositoryRelativePath -Path $scriptInfo.FullName

    if (Get-Command chmod -ErrorAction SilentlyContinue) {
        chmod +x -- $script
    }

    if (-not $SkipGitIndex -and $insideGitRepository) {
        git check-ignore -q -- $script
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Skipped ignored Bash script: $script"
            continue
        }

        git update-index --add --chmod=+x -- $script
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to mark Bash script as executable in the Git index: $script"
        }
    }
}

Write-Host 'Bash scripts have been marked executable locally and in the Git index.'
