param(
    [string]$ProfileConfig,
    [string]$Kubeconfig,
    [string]$Namespace,
    [string]$OutputPrefix,
    [ValidateSet("pre", "post")]
    [string]$Stage
)

$ErrorActionPreference = "Stop"

function Test-CommandAvailable {
    param([string]$CommandName)

    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
    return $null -ne $cmd
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path

if ([string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $ProfileConfig = Join-Path $repoRoot "config\cluster-capture\CS1.json"
}

if (-not (Test-Path $ProfileConfig)) {
    throw "Il file di profilo cluster-side non esiste: $ProfileConfig"
}

if (-not (Test-CommandAvailable -CommandName "kubectl")) {
    throw "Il comando richiesto non è disponibile nel PATH: kubectl"
}

$profile = Get-Content -Path $ProfileConfig -Raw -Encoding UTF8 | ConvertFrom-Json

$requiredProperties = @(
    "profileId",
    "description",
    "artifacts"
)

foreach ($propertyName in $requiredProperties) {
    if (-not ($profile.PSObject.Properties.Name -contains $propertyName)) {
        throw "Il file di profilo '$ProfileConfig' non contiene la proprietà obbligatoria '$propertyName'."
    }
}

if ([string]::IsNullOrWhiteSpace($Kubeconfig)) {
    $defaultKubeconfig = Join-Path $repoRoot "config\cluster-access\kubeconfig"
    if (Test-Path $defaultKubeconfig) {
        $Kubeconfig = $defaultKubeconfig
    }
    elseif ($profile.PSObject.Properties.Name -contains "kubeconfig" -and -not [string]::IsNullOrWhiteSpace([string]$profile.kubeconfig)) {
        $Kubeconfig = Join-Path $repoRoot ([string]$profile.kubeconfig)
    }
    else {
        throw "Nessun kubeconfig disponibile: non è stato passato come parametro e non è presente né nella repository né nel profilo '$ProfileConfig'."
    }
}

if ([string]::IsNullOrWhiteSpace($Namespace)) {
    if ($profile.PSObject.Properties.Name -contains "namespace" -and -not [string]::IsNullOrWhiteSpace([string]$profile.namespace)) {
        $Namespace = [string]$profile.namespace
    }
    else {
        throw "Nessun namespace disponibile: non è stato passato come parametro e non è presente nel profilo '$ProfileConfig'."
    }
}

if (-not (Test-Path $Kubeconfig)) {
    throw "Il file kubeconfig specificato non esiste: $Kubeconfig"
}

if ([string]::IsNullOrWhiteSpace($OutputPrefix)) {
    if ($profile.PSObject.Properties.Name -contains "defaultOutputRoot" -and -not [string]::IsNullOrWhiteSpace([string]$profile.defaultOutputRoot)) {
        $outputRoot = Join-Path $repoRoot ([string]$profile.defaultOutputRoot)
        if (-not (Test-Path $outputRoot)) {
            New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
        }
        $OutputPrefix = Join-Path $outputRoot "cluster_capture"
    }
    else {
        throw "Nessun output prefix disponibile: non è stato passato come parametro e il profilo '$ProfileConfig' non contiene 'defaultOutputRoot'."
    }
}
else {
    $outputDirectory = Split-Path -Parent $OutputPrefix
    if (-not [string]::IsNullOrWhiteSpace($outputDirectory) -and -not (Test-Path $outputDirectory)) {
        New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    }
}

if ([string]::IsNullOrWhiteSpace($Stage)) {
    $Stage = "pre"
}

$manifestPath = "${OutputPrefix}_manifest.json"
$summaryPath = "${OutputPrefix}_summary.txt"

$artifacts = @()
foreach ($artifact in $profile.artifacts) {
    $artifacts += [pscustomobject]@{
        name = [string]$artifact.name
        command = [string]$artifact.command
        outputFile = ("{0}_{1}" -f $OutputPrefix, [string]$artifact.outputSuffix)
    }
}

$exitCode = 0

foreach ($artifact in $artifacts) {
    $command = [string]$artifact.command
    $command = $command.Replace("{kubeconfig}", $Kubeconfig)
    $command = $command.Replace("{namespace}", $Namespace)

    $outputFile = [string]$artifact.outputFile
    $tempErrorFile = [System.IO.Path]::GetTempFileName()

    try {
        $previousNativePreference = $null
        if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
            $previousNativePreference = $PSNativeCommandUseErrorActionPreference
            $PSNativeCommandUseErrorActionPreference = $false
        }

        $result = & cmd.exe /d /c "$command 2>&1"
        $nativeExitCode = $LASTEXITCODE

        @($result) | Set-Content -Path $outputFile -Encoding UTF8

        if ($nativeExitCode -ne 0) {
            $exitCode = $nativeExitCode
        }
    }
    finally {
        if ($null -ne $previousNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $previousNativePreference
        }

        if (Test-Path $tempErrorFile) {
            Remove-Item $tempErrorFile -Force
        }
    }
}

$payload = [ordered]@{
    profile = [ordered]@{
        profileFile = (Resolve-Path $ProfileConfig).Path
        profileId = [string]$profile.profileId
        description = [string]$profile.description
    }
    execution = [ordered]@{
        timestampUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        kubeconfig = $Kubeconfig
        namespace = $Namespace
        outputPrefix = $OutputPrefix
        stage = $Stage
        exitCode = $exitCode
    }
    artifacts = @($artifacts | ForEach-Object {
        [ordered]@{
            name = $_.name
            outputFile = $_.outputFile
        }
    })
}

$payload | ConvertTo-Json -Depth 8 | Set-Content -Path $manifestPath -Encoding UTF8

$summaryLines = @(
    "=============================================",
    " Cluster-side collection",
    "=============================================",
    "Profile ID          : $($profile.profileId)",
    "Stage               : $Stage",
    "Kubeconfig          : $Kubeconfig",
    "Namespace           : $Namespace",
    "Manifest            : $manifestPath",
    "Summary             : $summaryPath",
    "Exit code           : $exitCode",
    "",
    "Artifacts:"
)

foreach ($artifact in $artifacts) {
    $summaryLines += " - $($artifact.outputFile)"
}

$summaryLines | Set-Content -Path $summaryPath -Encoding UTF8
Write-Host "Cluster-side collection completata: stage=$Stage"
Write-Host " - $manifestPath"
Write-Host " - $summaryPath"

if ($exitCode -ne 0) {
    exit $exitCode
}
