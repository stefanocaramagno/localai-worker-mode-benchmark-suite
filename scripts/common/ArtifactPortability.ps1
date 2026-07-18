Set-StrictMode -Version Latest

$script:ArtifactPortabilityRepositoryMarker = "localai-worker-mode-benchmark-suite"
$script:ArtifactPortabilityLocalPathPlaceholder = "<local-path>"

function Get-ArtifactPortabilityRepositoryRoot {
    param([AllowNull()][string]$ReferencePath)

    $candidates = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($ReferencePath)) {
        try {
            $resolvedReference = (Resolve-Path $ReferencePath -ErrorAction Stop).Path
            $candidates.Add($resolvedReference) | Out-Null
            $referenceParent = Split-Path -Parent $resolvedReference
            while (-not [string]::IsNullOrWhiteSpace($referenceParent)) {
                $candidates.Add($referenceParent) | Out-Null
                $nextParent = Split-Path -Parent $referenceParent
                if ($nextParent -eq $referenceParent) { break }
                $referenceParent = $nextParent
            }
        }
        catch {
            $rawReference = [System.IO.Path]::GetFullPath($ReferencePath)
            $candidates.Add($rawReference) | Out-Null
            $referenceParent = Split-Path -Parent $rawReference
            while (-not [string]::IsNullOrWhiteSpace($referenceParent)) {
                $candidates.Add($referenceParent) | Out-Null
                $nextParent = Split-Path -Parent $referenceParent
                if ($nextParent -eq $referenceParent) { break }
                $referenceParent = $nextParent
            }
        }
    }

    try {
        $cwd = (Resolve-Path "." -ErrorAction Stop).Path
        $candidates.Add($cwd) | Out-Null
        $cwdParent = Split-Path -Parent $cwd
        while (-not [string]::IsNullOrWhiteSpace($cwdParent)) {
            $candidates.Add($cwdParent) | Out-Null
            $nextParent = Split-Path -Parent $cwdParent
            if ($nextParent -eq $cwdParent) { break }
            $cwdParent = $nextParent
        }
    }
    catch {
        # Keep the candidates collected from the reference path.
    }

    foreach ($candidate in $candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        if ((Test-Path (Join-Path $candidate "config")) -and (Test-Path (Join-Path $candidate "scripts"))) {
            return (Resolve-Path $candidate).Path
        }
        if ((Split-Path -Leaf $candidate) -eq $script:ArtifactPortabilityRepositoryMarker) {
            return $candidate
        }
    }

    return (Resolve-Path ".").Path
}

function ConvertTo-ArtifactPortableString {
    param(
        [AllowNull()][string]$Value,
        [AllowNull()][string]$RepositoryRoot
    )

    if ($null -eq $Value) { return $null }
    if ([string]::IsNullOrWhiteSpace($Value)) { return $Value }

    $text = [string]$Value
    $trimmedText = $text.Trim()
    if (($trimmedText -notmatch '^[A-Za-z]:[\\/]+') -and ($trimmedText -match '^[A-Za-z][A-Za-z0-9+.-]*://')) {
        return $text
    }

    $portable = $text -replace '\\', '/'
    $portable = [System.Text.RegularExpressions.Regex]::Replace($portable, '^([A-Za-z]:)/+', '$1/')
    $portable = [System.Text.RegularExpressions.Regex]::Replace($portable, '(?<!:)/{2,}', '/')
    $rootValue = $RepositoryRoot
    if ([string]::IsNullOrWhiteSpace($rootValue)) {
        $rootValue = Get-ArtifactPortabilityRepositoryRoot -ReferencePath $null
    }

    if (-not [string]::IsNullOrWhiteSpace($rootValue)) {
        try { $rootValue = (Resolve-Path $rootValue -ErrorAction Stop).Path } catch { }
        $rootForward = ($rootValue -replace '\\', '/').TrimEnd('/')
        if (-not [string]::IsNullOrWhiteSpace($rootForward)) {
            $portable = [System.Text.RegularExpressions.Regex]::Replace(
                $portable,
                [System.Text.RegularExpressions.Regex]::Escape($rootForward),
                '.',
                [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
            )
        }
    }

    $marker = "/$script:ArtifactPortabilityRepositoryMarker/"
    $markerIndex = $portable.IndexOf($marker, [System.StringComparison]::OrdinalIgnoreCase)
    if ($markerIndex -ge 0) {
        $portable = $portable.Substring($markerIndex + $marker.Length)
    }

    $absolutePathRegex = '(?<![A-Za-z0-9+.-])[A-Za-z]:(?:/[^\s"''<>|{}]+)+'
    $portable = [System.Text.RegularExpressions.Regex]::Replace(
        $portable,
        $absolutePathRegex,
        {
            param($match)
            $token = [string]$match.Value
            $segments = @($token.TrimEnd('/').Split('/') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
            if ($segments.Count -gt 0) {
                return "$script:ArtifactPortabilityLocalPathPlaceholder/$($segments[-1])"
            }
            return $script:ArtifactPortabilityLocalPathPlaceholder
        }
    )

    while ($portable.StartsWith('./')) {
        $portable = $portable.Substring(2)
    }

    return $portable
}

function ConvertTo-PortableArtifactObject {
    param(
        [AllowNull()][object]$InputObject,
        [AllowNull()][string]$RepositoryRoot
    )

    if ($null -eq $InputObject) { return $null }

    if ($InputObject -is [string]) {
        return ConvertTo-ArtifactPortableString -Value ([string]$InputObject) -RepositoryRoot $RepositoryRoot
    }

    if ($InputObject -is [System.Collections.IDictionary]) {
        $output = [ordered]@{}
        foreach ($key in $InputObject.Keys) {
            $output[$key] = ConvertTo-PortableArtifactObject -InputObject $InputObject[$key] -RepositoryRoot $RepositoryRoot
        }
        return $output
    }

    if ($InputObject -is [System.Collections.IEnumerable] -and -not ($InputObject -is [string])) {
        $items = @()
        foreach ($item in $InputObject) {
            $items += ,(ConvertTo-PortableArtifactObject -InputObject $item -RepositoryRoot $RepositoryRoot)
        }
        return $items
    }

    if ($InputObject.PSObject -and $InputObject.PSObject.Properties.Count -gt 0 -and $InputObject.GetType().FullName -notmatch '^System\.') {
        $output = [ordered]@{}
        foreach ($property in $InputObject.PSObject.Properties) {
            $output[$property.Name] = ConvertTo-PortableArtifactObject -InputObject $property.Value -RepositoryRoot $RepositoryRoot
        }
        return $output
    }

    return $InputObject
}

function Write-PortableArtifactJson {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Payload,
        [int]$Depth = 12,
        [AllowNull()][string]$RepositoryRoot
    )

    $rootValue = if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) { Get-ArtifactPortabilityRepositoryRoot -ReferencePath $Path } else { $RepositoryRoot }
    $portablePayload = ConvertTo-PortableArtifactObject -InputObject $Payload -RepositoryRoot $rootValue
    $portablePayload | ConvertTo-Json -Depth $Depth | Set-Content -Path $Path -Encoding UTF8
}

function Write-PortableArtifactText {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [AllowNull()][object]$Text,
        [AllowNull()][string]$RepositoryRoot
    )

    $rootValue = if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) { Get-ArtifactPortabilityRepositoryRoot -ReferencePath $Path } else { $RepositoryRoot }
    if ($null -eq $Text) {
        Set-Content -Path $Path -Value "" -Encoding UTF8
        return
    }

    if ($Text -is [System.Collections.IEnumerable] -and -not ($Text -is [string])) {
        $lines = @($Text | ForEach-Object { ConvertTo-ArtifactPortableString -Value ([string]$_) -RepositoryRoot $rootValue })
        $lines | Set-Content -Path $Path -Encoding UTF8
        return
    }

    $portableText = ConvertTo-ArtifactPortableString -Value ([string]$Text) -RepositoryRoot $rootValue
    Set-Content -Path $Path -Value $portableText -Encoding UTF8
}
