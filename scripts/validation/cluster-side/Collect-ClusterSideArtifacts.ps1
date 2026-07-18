param(
    [string]$ProfileConfig,
    [string]$Kubeconfig,
    [string]$Namespace,
    [string[]]$AdditionalNamespaces,
    [string]$OutputPrefix,
    [ValidateSet("pre", "post")]
    [string]$Stage
)
$script:ArtifactPortabilitySearchRoot = Split-Path -Parent $PSCommandPath
while (-not [string]::IsNullOrWhiteSpace($script:ArtifactPortabilitySearchRoot)) {
    $script:ArtifactPortabilityCandidate = Join-Path $script:ArtifactPortabilitySearchRoot "scripts\common\ArtifactPortability.ps1"
    if (Test-Path $script:ArtifactPortabilityCandidate) {
        . $script:ArtifactPortabilityCandidate
        break
    }
    $script:ArtifactPortabilityParent = Split-Path -Parent $script:ArtifactPortabilitySearchRoot
    if ($script:ArtifactPortabilityParent -eq $script:ArtifactPortabilitySearchRoot) { break }
    $script:ArtifactPortabilitySearchRoot = $script:ArtifactPortabilityParent
}
Remove-Variable -Name ArtifactPortabilitySearchRoot -Scope Script -ErrorAction SilentlyContinue
Remove-Variable -Name ArtifactPortabilityCandidate -Scope Script -ErrorAction SilentlyContinue
Remove-Variable -Name ArtifactPortabilityParent -Scope Script -ErrorAction SilentlyContinue


$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

function Test-CommandAvailable {
    param([Parameter(Mandatory = $true)][string]$CommandName)

    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
    return $null -ne $cmd
}

function Test-ObjectProperty {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )

    return $Object.PSObject.Properties.Name -contains $Name
}

function Get-ObjectPropertyValue {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        [switch]$Required
    )

    if (-not (Test-ObjectProperty -Object $Object -Name $Name)) {
        if ($Required) {
            throw "The required property '$Name' is missing."
        }
        return $null
    }

    return $Object.$Name
}

function Get-ObjectStringValue {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name,
        [switch]$Required
    )

    $value = Get-ObjectPropertyValue -Object $Object -Name $Name -Required:$Required
    if ($null -eq $value) {
        return $null
    }

    $stringValue = [string]$value
    if ($Required -and [string]::IsNullOrWhiteSpace($stringValue)) {
        throw "The required property '$Name' is empty."
    }

    return $stringValue
}

function Resolve-RepositoryPath {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [Parameter(Mandatory = $true)][string]$PathValue
    )

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }

    return Join-Path $RepositoryRoot $PathValue
}

function Convert-ToRepositoryRelativeString {
    param(
        [Parameter(Mandatory = $true)][string]$RepositoryRoot,
        [AllowNull()][string]$PathValue
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $PathValue
    }

    $root = ((Resolve-Path $RepositoryRoot).Path -replace '\\', '/').TrimEnd("/")
    $value = ([string]$PathValue) -replace '\\', '/'

    if ([string]::Equals($value, $root, [System.StringComparison]::OrdinalIgnoreCase)) {
        return "."
    }

    if ($value.StartsWith($root + "/", [System.StringComparison]::OrdinalIgnoreCase)) {
        return $value.Substring($root.Length + 1)
    }

    $marker = "/localai-worker-mode-benchmark-suite/"
    $markerIndex = $value.IndexOf($marker, [System.StringComparison]::OrdinalIgnoreCase)
    if ($markerIndex -ge 0) {
        return $value.Substring($markerIndex + $marker.Length)
    }

    return $PathValue
}

function Convert-ToSafeFileToken {
    param([Parameter(Mandatory = $true)][string]$Value)

    $token = $Value.Trim().ToLowerInvariant() -replace "[^a-z0-9._-]+", "-"
    $token = $token.Trim("-")
    if ([string]::IsNullOrWhiteSpace($token)) {
        return "namespace"
    }
    return $token
}

function Add-NamespaceCandidate {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[string]]$Target,
        [AllowNull()][object]$Value
    )

    if ($null -eq $Value) {
        return
    }

    if ($Value -is [string]) {
        $items = ([string]$Value).Split(",", [System.StringSplitOptions]::RemoveEmptyEntries)
    }
    elseif ($Value -is [System.Collections.IEnumerable]) {
        $items = @($Value)
    }
    else {
        $items = @($Value)
    }

    foreach ($item in $items) {
        if ($null -eq $item) {
            continue
        }
        $text = ([string]$item).Trim()
        if ([string]::IsNullOrWhiteSpace($text)) {
            continue
        }
        if (-not $Target.Contains($text)) {
            $Target.Add($text) | Out-Null
        }
    }
}

function Invoke-ClusterCaptureCommand {
    param([Parameter(Mandatory = $true)][string]$CommandText)

    $previousNativePreference = $null
    if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
        $previousNativePreference = $PSNativeCommandUseErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $false
    }

    try {
        $useBash = $false
        $isWindowsVariable = Get-Variable -Name IsWindows -ErrorAction SilentlyContinue
        if ($null -ne $isWindowsVariable) {
            $useBash = -not [bool]$isWindowsVariable.Value
        }

        if ($useBash) {
            $output = & bash -lc "$CommandText 2>&1"
        }
        else {
            $output = & cmd.exe /d /c "$CommandText 2>&1"
        }

        $nativeExitCode = $LASTEXITCODE
        return [pscustomobject]@{
            Output = @($output)
            ExitCode = [int]$nativeExitCode
        }
    }
    finally {
        if ($null -ne $previousNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $previousNativePreference
        }
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path

if ([string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $ProfileConfig = Join-Path $repoRoot "config\cluster-capture\profiles\CS_STANDARD_CLUSTER_CAPTURE.json"
}

if (-not (Test-Path $ProfileConfig)) {
    throw "The cluster-side profile file does not exist: $ProfileConfig"
}

if (-not (Test-CommandAvailable -CommandName "kubectl")) {
    throw "The required command is not available in PATH: kubectl"
}

$profile = Get-Content -Path $ProfileConfig -Raw -Encoding UTF8 | ConvertFrom-Json

$requiredProperties = @(
    "profileId",
    "description",
    "manifestSuffix",
    "textSuffix",
    "artifacts"
)

foreach ($propertyName in $requiredProperties) {
    if (-not (Test-ObjectProperty -Object $profile -Name $propertyName)) {
        throw "The profile file '$ProfileConfig' does not contain the required property '$propertyName'."
    }
}

$profileId = Get-ObjectStringValue -Object $profile -Name "profileId" -Required
$profileDescription = Get-ObjectStringValue -Object $profile -Name "description" -Required
$manifestSuffix = Get-ObjectStringValue -Object $profile -Name "manifestSuffix" -Required
$textSuffix = Get-ObjectStringValue -Object $profile -Name "textSuffix" -Required

if ($null -eq $profile.artifacts -or $profile.artifacts.Count -eq 0) {
    throw "Profile '$ProfileConfig' does not contain artifacts to collect."
}

foreach ($artifact in $profile.artifacts) {
    foreach ($artifactProperty in @("name", "command", "outputSuffix")) {
        if (-not (Test-ObjectProperty -Object $artifact -Name $artifactProperty)) {
            throw "An artifact in profile '$ProfileConfig' does not contain the required property '$artifactProperty'."
        }

        $artifactValue = [string]$artifact.$artifactProperty
        if ([string]::IsNullOrWhiteSpace($artifactValue)) {
            throw "An artifact in profile '$ProfileConfig' contains property '$artifactProperty' empty."
        }
    }
}

if ([string]::IsNullOrWhiteSpace($Kubeconfig)) {
    if ((Test-ObjectProperty -Object $profile -Name "kubeconfig") -and -not [string]::IsNullOrWhiteSpace([string]$profile.kubeconfig)) {
        $Kubeconfig = Resolve-RepositoryPath -RepositoryRoot $repoRoot -PathValue ([string]$profile.kubeconfig)
    }
    else {
        $defaultKubeconfig = Join-Path $repoRoot "config\cluster-access\fixed-cluster\kubeconfig"
        if (Test-Path $defaultKubeconfig) {
            $Kubeconfig = $defaultKubeconfig
        }
        else {
            throw "No kubeconfig is available: it was not passed as a parameter and is not present in the profile or default path."
        }
    }
}

if (-not (Test-Path $Kubeconfig)) {
    throw "The specified kubeconfig file does not exist: $Kubeconfig"
}

$namespaceCandidates = [System.Collections.Generic.List[string]]::new()

if (-not [string]::IsNullOrWhiteSpace($Namespace)) {
    Add-NamespaceCandidate -Target $namespaceCandidates -Value $Namespace
}
elseif ((Test-ObjectProperty -Object $profile -Name "namespace") -and -not [string]::IsNullOrWhiteSpace([string]$profile.namespace)) {
    Add-NamespaceCandidate -Target $namespaceCandidates -Value ([string]$profile.namespace)
}
elseif ((Test-ObjectProperty -Object $profile -Name "namespaces") -and $null -ne $profile.namespaces -and $profile.namespaces.Count -gt 0) {
    Add-NamespaceCandidate -Target $namespaceCandidates -Value @($profile.namespaces)[0]
}
else {
    Add-NamespaceCandidate -Target $namespaceCandidates -Value "localai-benchmark"
}

Add-NamespaceCandidate -Target $namespaceCandidates -Value $AdditionalNamespaces

if (Test-ObjectProperty -Object $profile -Name "additionalNamespaces") {
    Add-NamespaceCandidate -Target $namespaceCandidates -Value $profile.additionalNamespaces
}

if (Test-ObjectProperty -Object $profile -Name "namespaces") {
    Add-NamespaceCandidate -Target $namespaceCandidates -Value $profile.namespaces
}

$Namespace = $namespaceCandidates[0]
$namespaces = @($namespaceCandidates.ToArray())
$additionalNamespaceValues = @($namespaces | Where-Object { $_ -ne $Namespace })

if ([string]::IsNullOrWhiteSpace($OutputPrefix)) {
    if ((Test-ObjectProperty -Object $profile -Name "defaultOutputRoot") -and -not [string]::IsNullOrWhiteSpace([string]$profile.defaultOutputRoot)) {
        $outputRoot = Resolve-RepositoryPath -RepositoryRoot $repoRoot -PathValue ([string]$profile.defaultOutputRoot)
        if (-not (Test-Path $outputRoot)) {
            New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
        }
        $OutputPrefix = Join-Path $outputRoot "cluster_capture"
    }
    else {
        throw "No output prefix is available: specify -OutputPrefix or define 'defaultOutputRoot' in profile '$ProfileConfig'."
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

$manifestPath = "{0}{1}" -f $OutputPrefix, $manifestSuffix
$summaryPath = "{0}{1}" -f $OutputPrefix, $textSuffix

$artifacts = @()
foreach ($artifact in $profile.artifacts) {
    $commandTemplate = [string]$artifact.command
    $artifactName = [string]$artifact.name
    $artifactSuffix = [string]$artifact.outputSuffix

    if ($commandTemplate.Contains("{namespace}")) {
        foreach ($namespaceItem in $namespaces) {
            $isPrimary = $namespaceItem -eq $Namespace
            $safeNamespace = Convert-ToSafeFileToken -Value $namespaceItem
            $outputFile = if ($isPrimary) {
                "{0}_{1}" -f $OutputPrefix, $artifactSuffix
            }
            else {
                "{0}_{1}_{2}" -f $OutputPrefix, $safeNamespace, $artifactSuffix
            }

            $artifacts += [pscustomobject]@{
                name = if ($isPrimary) { $artifactName } else { "$artifactName`:$namespaceItem" }
                command = $commandTemplate.Replace("{kubeconfig}", $Kubeconfig).Replace("{namespace}", $namespaceItem)
                outputFile = $outputFile
                exitCode = $null
                namespace = $namespaceItem
                namespaceRole = if ($isPrimary) { "primary" } else { "additional" }
                namespaceScoped = $true
            }
        }
    }
    else {
        $outputFile = "{0}_{1}" -f $OutputPrefix, $artifactSuffix
        $artifacts += [pscustomobject]@{
            name = $artifactName
            command = $commandTemplate.Replace("{kubeconfig}", $Kubeconfig)
            outputFile = $outputFile
            exitCode = $null
            namespace = $null
            namespaceRole = "cluster"
            namespaceScoped = $false
        }
    }
}

$exitCode = 0

foreach ($artifact in $artifacts) {
    $outputFile = [string]$artifact.outputFile
    $outputDirectory = Split-Path -Parent $outputFile
    if (-not [string]::IsNullOrWhiteSpace($outputDirectory) -and -not (Test-Path $outputDirectory)) {
        New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    }

    $result = Invoke-ClusterCaptureCommand -CommandText ([string]$artifact.command)
    @($result.Output) | Set-Content -Path $outputFile -Encoding UTF8
    $artifact.exitCode = [int]$result.ExitCode

    if ($result.ExitCode -ne 0 -and $exitCode -eq 0) {
        $exitCode = [int]$result.ExitCode
    }
}

$displayProfileConfig = Convert-ToRepositoryRelativeString -RepositoryRoot $repoRoot -PathValue ((Resolve-Path $ProfileConfig).Path)
$displayKubeconfig = Convert-ToRepositoryRelativeString -RepositoryRoot $repoRoot -PathValue $Kubeconfig
$displayOutputPrefix = Convert-ToRepositoryRelativeString -RepositoryRoot $repoRoot -PathValue $OutputPrefix
$displayManifestPath = Convert-ToRepositoryRelativeString -RepositoryRoot $repoRoot -PathValue $manifestPath
$displaySummaryPath = Convert-ToRepositoryRelativeString -RepositoryRoot $repoRoot -PathValue $summaryPath

$payload = [ordered]@{
    clusterCaptureProfile = [ordered]@{
        profileFile = $displayProfileConfig
        profileId = $profileId
        description = $profileDescription
        manifestSuffix = $manifestSuffix
        textSuffix = $textSuffix
    }
    capture = [ordered]@{
        timestampUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        stage = $Stage
        namespace = $Namespace
        primaryNamespace = $Namespace
        namespaces = @($namespaces)
        additionalNamespaces = @($additionalNamespaceValues)
        kubeconfig = $displayKubeconfig
        outputPrefix = $displayOutputPrefix
        exitCode = $exitCode
        artifacts = @($artifacts | ForEach-Object {
            [ordered]@{
                name = $_.name
                command = (Convert-ToRepositoryRelativeString -RepositoryRoot $repoRoot -PathValue ([string]$_.command))
                outputFile = (Convert-ToRepositoryRelativeString -RepositoryRoot $repoRoot -PathValue ([string]$_.outputFile))
                exitCode = $_.exitCode
                namespace = $_.namespace
                namespaceRole = $_.namespaceRole
                namespaceScoped = $_.namespaceScoped
            }
        })
    }
}

Write-PortableArtifactJson -Path $manifestPath -Payload $payload -Depth 10

$summaryLines = @(
    "=============================================",
    " Cluster-side Collection",
    "=============================================",
    "Profile       : $profileId",
    "Description   : $profileDescription",
    "Stage         : $Stage",
    "Namespace     : $Namespace",
    "Namespaces    : $($namespaces -join ', ')",
    "Kubeconfig    : $displayKubeconfig",
    "Output prefix : $displayOutputPrefix",
    "Manifest      : $displayManifestPath",
    "Summary       : $displaySummaryPath",
    "Exit code     : $exitCode",
    "",
    "Artifacts:"
)

foreach ($artifact in $artifacts) {
    $summaryLines += "- $($artifact.name): $(Convert-ToRepositoryRelativeString -RepositoryRoot $repoRoot -PathValue ([string]$artifact.outputFile))"
}

Write-PortableArtifactText -Path $summaryPath -Text $summaryLines

Write-Host "Cluster-side collection completed: stage=$Stage"
Write-Host " - $manifestPath"
Write-Host " - $summaryPath"

if ($exitCode -ne 0) {
    exit $exitCode
}
