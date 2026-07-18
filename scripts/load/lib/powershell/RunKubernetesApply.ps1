Set-StrictMode -Version Latest

function Invoke-K8sApplyTarget {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $false)][string]$Kubeconfig
    )

    $kubectlArgs = @()
    if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) {
        $kubectlArgs += @('--kubeconfig', $Kubeconfig)
    }

    if (Test-Path -Path $Path -PathType Leaf) {
        & kubectl @kubectlArgs apply -f $Path
        return
    }

    if ((Test-Path -Path $Path -PathType Container) -and (Test-Path (Join-Path $Path 'kustomization.yaml') -PathType Leaf)) {
        & kubectl @kubectlArgs apply -k $Path
        return
    }

    throw "Invalid or unresolved Kubernetes target: $Path"
}

function Invoke-RecommendedK8sApplyOrder {
    param(
        [Parameter(Mandatory = $true)][string[]]$Targets,
        [Parameter(Mandatory = $false)][string]$Kubeconfig,
        [Parameter(Mandatory = $false)][string]$LauncherName = 'launcher',
        [Parameter(Mandatory = $false)][string]$RunId = ''
    )

    if ($null -eq $Targets -or $Targets.Count -eq 0) {
        throw 'No Kubernetes target was provided for apply.'
    }

    Write-Host ''
    Write-Host 'Applying requested Kubernetes targets automatically...' -ForegroundColor Yellow
    Write-Host "Launcher               : $LauncherName"
    if (-not [string]::IsNullOrWhiteSpace($RunId)) {
        Write-Host "Run ID                 : $RunId"
    }

    foreach ($target in $Targets) {
        Write-Host " - apply => $target"
        Invoke-K8sApplyTarget -Path $target -Kubeconfig $Kubeconfig
    }
}
