param(
    [ValidateSet("worker-count", "workload", "models", "placement", "all")]
    [string]$Family = "all",
    [string]$ProfileConfig,
    [string]$BaseUrl = "http://localhost:8080",
    [string]$OutputRoot,
    [string]$Kubeconfig,
    [string]$Namespace,
    [switch]$SkipPrecheck,
    [switch]$SkipApiSmoke,
    [switch]$ContinueOnFailure,
    [string]$StatisticalRigorConfig,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$UnsupportedScenarioExitCode = 42

function Test-CommandAvailable {
    param([string]$CommandName)
    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
    return $null -ne $cmd
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path

. (Join-Path $repoRoot "scripts\load\lib\powershell\RunConvention.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunPilotConsolidation.ps1")
. (Join-Path $repoRoot "scripts\load\lib\powershell\RunStatisticalRigor.ps1")

function Get-MeasurementStatsCsvPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SearchRoot,
        [Parameter(Mandatory = $true)]
        [string]$Scenario,
        [Parameter(Mandatory = $true)]
        [string]$Replica,
        [Parameter(Mandatory = $false)]
        [Nullable[datetime]]$NotOlderThanUtc = $null
    )

    if ([string]::IsNullOrWhiteSpace($SearchRoot) -or -not (Test-Path $SearchRoot)) {
        return $null
    }

    $expectedFileName = "${Scenario}_run${Replica}_stats.csv"

    $matches = @(
        Get-ChildItem -Path $SearchRoot -Recurse -File -Filter $expectedFileName -ErrorAction SilentlyContinue |
            Where-Object {
                if ($null -eq $NotOlderThanUtc) {
                    return $true
                }

                try {
                    $thresholdUtc = [datetime]$NotOlderThanUtc
                }
                catch {
                    return $true
                }

                $_.LastWriteTimeUtc -ge $thresholdUtc
            } |
            Sort-Object -Property LastWriteTimeUtc, FullName -Descending
    )

    if ($matches.Count -gt 0) {
        return $matches[0].FullName
    }

    return $null
}

function Get-KubectlJsonForConsolidation {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [string]$KubeconfigPath
    )

    if (-not (Test-CommandAvailable -CommandName "kubectl")) {
        throw "kubectl non risulta disponibile nel PATH."
    }

    $kubectlArgs = @()
    if (-not [string]::IsNullOrWhiteSpace($KubeconfigPath)) {
        $kubectlArgs += @("--kubeconfig", $KubeconfigPath)
    }

    $kubectlArgs += $Arguments
    $kubectlArgs += @("-o", "json")

    $raw = & kubectl @kubectlArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Comando kubectl fallito: kubectl $($kubectlArgs -join ' ')"
    }

    return ($raw | ConvertFrom-Json)
}


function Get-OptionalObjectPropertyValue {
    param(
        [Parameter(Mandatory = $true)]
        [object]$InputObject,
        [Parameter(Mandatory = $true)]
        [string]$PropertyName,
        [object]$DefaultValue = $null
    )

    if ($null -eq $InputObject) {
        return $DefaultValue
    }

    $property = $InputObject.PSObject.Properties[$PropertyName]
    if ($null -eq $property) {
        return $DefaultValue
    }

    return $property.Value
}

function Wait-ConsolidatedClusterStabilization {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Namespace,
        [string]$KubeconfigPath,
        [int]$TimeoutSeconds = 180,
        [int]$PollIntervalSeconds = 5
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastReason = "Cluster stabilization check not yet executed."

    do {
        $deploymentsJson = Get-KubectlJsonForConsolidation -Arguments @("get", "deployments", "-n", $Namespace) -KubeconfigPath $KubeconfigPath
        $podsJson = Get-KubectlJsonForConsolidation -Arguments @("get", "pods", "-n", $Namespace) -KubeconfigPath $KubeconfigPath

        $deployments = @(
            @($deploymentsJson.items) | Where-Object {
                $name = [string]$_.metadata.name
                $name -eq "localai-server" -or $name -like "localai-rpc-*"
            }
        )

        $pods = @(
            @($podsJson.items) | Where-Object {
                $name = [string]$_.metadata.name
                $name -like "localai-server*" -or $name -like "localai-rpc-*"
            }
        )

        if ($deployments.Count -eq 0) {
            $lastReason = "Nessun deployment LocalAI osservato nel namespace '$Namespace'."
            Start-Sleep -Seconds $PollIntervalSeconds
            continue
        }

        if ($pods.Count -eq 0) {
            $lastReason = "Nessun pod LocalAI osservato nel namespace '$Namespace'."
            Start-Sleep -Seconds $PollIntervalSeconds
            continue
        }

        $deploymentIssues = New-Object System.Collections.Generic.List[string]
        foreach ($deployment in $deployments) {
            $name = [string]$deployment.metadata.name
            $specReplicas = if ($null -ne $deployment.spec.replicas) { [int]$deployment.spec.replicas } else { 1 }
            $status = $deployment.status
            $readyReplicas = [int](Get-OptionalObjectPropertyValue -InputObject $status -PropertyName "readyReplicas" -DefaultValue 0)
            $updatedReplicas = [int](Get-OptionalObjectPropertyValue -InputObject $status -PropertyName "updatedReplicas" -DefaultValue 0)
            $availableReplicas = [int](Get-OptionalObjectPropertyValue -InputObject $status -PropertyName "availableReplicas" -DefaultValue 0)
            $observedGeneration = [int](Get-OptionalObjectPropertyValue -InputObject $status -PropertyName "observedGeneration" -DefaultValue 0)
            $generation = [int](Get-OptionalObjectPropertyValue -InputObject $deployment.metadata -PropertyName "generation" -DefaultValue 0)

            if ($observedGeneration -lt $generation) {
                $deploymentIssues.Add(("{0}: observedGeneration={1} < generation={2}" -f $name, $observedGeneration, $generation)) | Out-Null
                continue
            }

            if ($readyReplicas -lt $specReplicas -or $updatedReplicas -lt $specReplicas -or $availableReplicas -lt $specReplicas) {
                $deploymentIssues.Add(("{0}: replicas spec={1}, ready={2}, updated={3}, available={4}" -f $name, $specReplicas, $readyReplicas, $updatedReplicas, $availableReplicas)) | Out-Null
            }
        }

        $podIssues = New-Object System.Collections.Generic.List[string]
        foreach ($pod in $pods) {
            $name = [string]$pod.metadata.name
            $deletionTimestamp = Get-OptionalObjectPropertyValue -InputObject $pod.metadata -PropertyName "deletionTimestamp" -DefaultValue $null
            if ($null -ne $deletionTimestamp) {
                $podIssues.Add(("{0}: in terminazione" -f $name)) | Out-Null
                continue
            }

            $phase = [string](Get-OptionalObjectPropertyValue -InputObject $pod.status -PropertyName "phase" -DefaultValue "")
            if ($phase -ne "Running") {
                $podIssues.Add(("{0}: phase={1}" -f $name, $phase)) | Out-Null
                continue
            }

            $conditions = @((Get-OptionalObjectPropertyValue -InputObject $pod.status -PropertyName "conditions" -DefaultValue @()))
            $readyCondition = $conditions | Where-Object { $_.type -eq "Ready" } | Select-Object -First 1
            if ($null -eq $readyCondition -or [string](Get-OptionalObjectPropertyValue -InputObject $readyCondition -PropertyName "status" -DefaultValue "") -ne "True") {
                $podIssues.Add(("{0}: Ready condition non soddisfatta" -f $name)) | Out-Null
            }
        }

        if ($deploymentIssues.Count -eq 0 -and $podIssues.Count -eq 0) {
            return [pscustomobject]@{
                deploymentCount = $deployments.Count
                podCount = $pods.Count
                summary = "Deployment e pod LocalAI risultano stabili nel namespace '$Namespace'."
            }
        }

        $issueParts = @()
        if ($deploymentIssues.Count -gt 0) {
            $issueParts += ("deployment non stabili: {0}" -f (($deploymentIssues.ToArray()) -join "; "))
        }
        if ($podIssues.Count -gt 0) {
            $issueParts += ("pod non stabili: {0}" -f (($podIssues.ToArray()) -join "; "))
        }
        $lastReason = $issueParts -join " | "
        Start-Sleep -Seconds $PollIntervalSeconds
    }
    while ((Get-Date) -lt $deadline)

    throw "Timeout durante la stabilizzazione del cluster nel namespace '$Namespace'. Ultima osservazione: $lastReason"
}


if ([string]::IsNullOrWhiteSpace($ProfileConfig)) {
    $ProfileConfig = Join-Path $repoRoot "config\pilot-consolidation\CP1.json"
}

$profile = Get-PilotConsolidationProfile -ProfileFile $ProfileConfig

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $repoRoot ([string]$profile.RawConfig.outputRoot -replace '/', '\')
}

if ([string]::IsNullOrWhiteSpace($StatisticalRigorConfig)) {
    $StatisticalRigorConfig = Join-Path $repoRoot ([string]$profile.RawConfig.statisticalRigorConfig -replace '/', '\')
}

$statisticalRigor = Get-StatisticalRigorProfile -ProfileFile $StatisticalRigorConfig

$campaignsRoot = Join-Path $OutputRoot "campaigns"
if (-not (Test-Path $campaignsRoot)) {
    New-Item -ItemType Directory -Path $campaignsRoot -Force | Out-Null
}

$runTimestampUtc = New-RunTimestampUtc
$campaignId = New-RunId -Track "pilot" -Family "consolidated" -Scenario $Family -Replica "NA" -TimestampUtc $runTimestampUtc
$manifestPath = Join-Path $campaignsRoot ("{0}{1}" -f $campaignId, [string]$profile.RawConfig.campaignManifestSuffix)
$textReportPath = Join-Path $campaignsRoot ("{0}{1}" -f $campaignId, [string]$profile.RawConfig.campaignTextSuffix)
$rigorManifestPath = Join-Path $campaignsRoot ("{0}{1}" -f $campaignId, [string]$statisticalRigor.RawConfig.summaryManifestSuffix)
$rigorTextPath = Join-Path $campaignsRoot ("{0}{1}" -f $campaignId, [string]$statisticalRigor.RawConfig.summaryTextSuffix)

$targetFamilies = if ($Family -eq "all") {
    @("worker-count", "workload", "models", "placement")
}
else {
    @($Family)
}

$entries = New-Object System.Collections.Generic.List[object]
$reportLines = New-Object System.Collections.Generic.List[string]
$reportLines.Add("=============================================")
$reportLines.Add(" Consolidated Pilot Benchmarks Launcher")
$reportLines.Add("=============================================")
$reportLines.Add("Repository              : $repoRoot")
$reportLines.Add("Profile                 : $($profile.ProfileFile)")
$reportLines.Add("Profile ID              : $($profile.RawConfig.profileId)")
$reportLines.Add("Campaign ID             : $campaignId")
$reportLines.Add("Family scope            : $Family")
$reportLines.Add("Base URL                : $BaseUrl")
$reportLines.Add("Output root             : $OutputRoot")
$reportLines.Add("Statistical rigor       : $($statisticalRigor.ProfileFile)")
$reportLines.Add("Replica cooldown (s)    : $($statisticalRigor.RawConfig.coolDownBetweenReplicasSeconds)")
$reportLines.Add("Scenario cooldown (s)   : $($statisticalRigor.RawConfig.coolDownBetweenScenariosSeconds)")
$reportLines.Add("Stabilization timeout   : $($statisticalRigor.RawConfig.stabilizationTimeoutSeconds)")
$reportLines.Add("Stabilization poll (s)  : $($statisticalRigor.RawConfig.stabilizationPollIntervalSeconds)")
$reportLines.Add("Dry run                 : $DryRun")
$reportLines.Add("Continue on failure     : $ContinueOnFailure")
$reportLines.Add("")

$overallStatus = "success"
$stopCampaign = $false

foreach ($familyName in $targetFamilies) {
    $familyConfig = Get-PilotConsolidationFamily -Profile $profile -FamilyName $familyName
    $launcherPath = Join-Path $repoRoot ([string]$familyConfig.RawConfig.launcherPowerShell -replace '/', '\')
    $familyOutputRoot = Join-Path $OutputRoot $familyName

    if (-not (Test-Path $launcherPath)) {
        throw "Launcher di famiglia non trovato: $launcherPath"
    }

    if (-not (Test-Path $familyOutputRoot)) {
        New-Item -ItemType Directory -Path $familyOutputRoot -Force | Out-Null
    }

    $reportLines.Add("Family                : $familyName")
    $reportLines.Add("Launcher              : $launcherPath")
    $reportLines.Add("Output root           : $familyOutputRoot")
    $reportLines.Add("Scenarios             : $(([string[]]$familyConfig.RawConfig.scenarios) -join ' ')")
    $reportLines.Add("Replicas              : $(([string[]]$familyConfig.RawConfig.replicas) -join ' ')")
    $reportLines.Add("")

    $familyScenarios = [string[]]$familyConfig.RawConfig.scenarios
    $familyReplicas = [string[]]$familyConfig.RawConfig.replicas

    for ($scenarioIndex = 0; $scenarioIndex -lt $familyScenarios.Count; $scenarioIndex++) {
        $scenario = $familyScenarios[$scenarioIndex]

        for ($replicaIndex = 0; $replicaIndex -lt $familyReplicas.Count; $replicaIndex++) {
            $replica = $familyReplicas[$replicaIndex]

            $cmdArgs = [ordered]@{
                Scenario = $scenario
                Replica = $replica
                BaseUrl = $BaseUrl
                OutputRoot = $familyOutputRoot
                PrecheckConfig = (Join-Path $repoRoot ([string]$profile.RawConfig.precheckConfig -replace '/', '\'))
                PhaseConfig = (Join-Path $repoRoot ([string]$profile.RawConfig.phaseConfig -replace '/', '\'))
                WarmUpDuration = [string]$profile.RawConfig.warmUpDuration
                MeasurementDuration = [string]$profile.RawConfig.measurementDuration
                ProtocolConfig = (Join-Path $repoRoot ([string]$profile.RawConfig.protocolConfig -replace '/', '\'))
                ClusterCaptureConfig = (Join-Path $repoRoot ([string]$profile.RawConfig.clusterCaptureConfig -replace '/', '\'))
                MetricSetConfig = (Join-Path $repoRoot ([string]$profile.RawConfig.metricSetConfig -replace '/', '\'))
                AutoApplyK8s = $true
            }

            if (-not [string]::IsNullOrWhiteSpace($Kubeconfig)) {
                $cmdArgs.Kubeconfig = $Kubeconfig
            }

            if (-not [string]::IsNullOrWhiteSpace($Namespace)) {
                $cmdArgs.Namespace = $Namespace
            }

            if ($SkipPrecheck) {
                $cmdArgs.SkipPrecheck = $true
            }

            if ($SkipApiSmoke) {
                $cmdArgs.SkipApiSmoke = $true
            }

            if ($DryRun) {
                $cmdArgs.DryRun = $true
            }

            $commandText = "& `"$launcherPath`" " + (($cmdArgs.GetEnumerator() | ForEach-Object {
                if ($_.Value -is [bool]) {
                    if ($_.Value) {
                        "-$($_.Key)"
                    }
                }
                else {
                    "-$($_.Key) $($_.Value)"
                }
            }) -join " ")
            $reportLines.Add("Run command           : $commandText")

            $statsCsvPath = $null

            if ($DryRun) {
                $entries.Add((New-StatisticalRigorEntry -Family $familyName -Scenario $scenario -Replica $replica -Status "dry_run" -ExitCode 0 -Command $commandText -StatsCsvPath $statsCsvPath)) | Out-Null
                continue
            }

            $runStartedAtUtc = (Get-Date).ToUniversalTime()
            & $launcherPath @cmdArgs
            $exitCode = $LASTEXITCODE
            $statsCsvPath = Get-MeasurementStatsCsvPath -SearchRoot $familyOutputRoot -Scenario $scenario -Replica $replica -NotOlderThanUtc $runStartedAtUtc

            if ($exitCode -eq 0) {
                $entries.Add((New-StatisticalRigorEntry -Family $familyName -Scenario $scenario -Replica $replica -Status "success" -ExitCode $exitCode -Command $commandText -StatsCsvPath $statsCsvPath)) | Out-Null
            }
            elseif ($exitCode -eq $UnsupportedScenarioExitCode) {
                if ($overallStatus -eq "success") {
                    $overallStatus = "completed_with_unsupported_scenarios"
                }
                $entries.Add((New-StatisticalRigorEntry -Family $familyName -Scenario $scenario -Replica $replica -Status "unsupported_under_current_constraints" -ExitCode $exitCode -Command $commandText -StatsCsvPath $statsCsvPath)) | Out-Null
                $reportLines.Add("Unsupported scenario  : family=$familyName scenario=$scenario replica=$replica exitCode=$exitCode (recorded as unsupported_under_current_constraints)")
            }
            else {
                $overallStatus = "failed"
                $entries.Add((New-StatisticalRigorEntry -Family $familyName -Scenario $scenario -Replica $replica -Status "failed" -ExitCode $exitCode -Command $commandText -StatsCsvPath $statsCsvPath)) | Out-Null

                if (-not $ContinueOnFailure -and [bool]$profile.RawConfig.stopOnFirstFailure) {
                    $reportLines.Add("Stopped on failure    : family=$familyName scenario=$scenario replica=$replica exitCode=$exitCode")
                    $stopCampaign = $true
                }
            }

            $shouldRunClusterStabilization = (-not $DryRun) -and ($exitCode -eq 0)

            if ($shouldRunClusterStabilization -and -not [string]::IsNullOrWhiteSpace($Namespace)) {
                $stabilizationResult = Wait-ConsolidatedClusterStabilization `
                    -Namespace $Namespace `
                    -KubeconfigPath $Kubeconfig `
                    -TimeoutSeconds ([int]$statisticalRigor.RawConfig.stabilizationTimeoutSeconds) `
                    -PollIntervalSeconds ([int]$statisticalRigor.RawConfig.stabilizationPollIntervalSeconds)

                $reportLines.Add("Cluster stabilization : family=$familyName scenario=$scenario replica=$replica deployments=$($stabilizationResult.deploymentCount) pods=$($stabilizationResult.podCount)")
            }
            elseif (-not $DryRun -and $exitCode -eq $UnsupportedScenarioExitCode) {
                $reportLines.Add("Cluster stabilization : skipped for family=$familyName scenario=$scenario replica=$replica because the scenario was classified as unsupported_under_current_constraints")
            }
            elseif (-not $DryRun -and -not [string]::IsNullOrWhiteSpace($Namespace)) {
                $reportLines.Add("Cluster stabilization : skipped for family=$familyName scenario=$scenario replica=$replica because the run did not complete successfully (exitCode=$exitCode)")
            }
            elseif (-not $DryRun) {
                $reportLines.Add("Cluster stabilization : skipped for family=$familyName scenario=$scenario replica=$replica because Namespace was not provided")
            }

            if ($stopCampaign) {
                break
            }

            if ($replicaIndex -lt ($familyReplicas.Count - 1) -and [int]$statisticalRigor.RawConfig.coolDownBetweenReplicasSeconds -gt 0) {
                $reportLines.Add("Replica cooldown      : $($statisticalRigor.RawConfig.coolDownBetweenReplicasSeconds)s after ${familyName}/${scenario}/${replica}")
                Start-Sleep -Seconds ([int]$statisticalRigor.RawConfig.coolDownBetweenReplicasSeconds)
            }
        }

        if ($stopCampaign) {
            break
        }

        if (-not $DryRun -and $scenarioIndex -lt ($familyScenarios.Count - 1) -and [int]$statisticalRigor.RawConfig.coolDownBetweenScenariosSeconds -gt 0) {
            $reportLines.Add("Scenario cooldown     : $($statisticalRigor.RawConfig.coolDownBetweenScenariosSeconds)s after ${familyName}/${scenario}")
            Start-Sleep -Seconds ([int]$statisticalRigor.RawConfig.coolDownBetweenScenariosSeconds)
        }
    }

    if ($stopCampaign) {
        break
    }
}

$entriesArray = @($entries.ToArray())
$manifestPayload = New-Object System.Collections.Specialized.OrderedDictionary
$manifestPayload.Add("profileFile", $profile.ProfileFile)
$manifestPayload.Add("profileId", [string]$profile.RawConfig.profileId)
$manifestPayload.Add("description", [string]$profile.RawConfig.description)
$manifestPayload.Add("campaignId", $campaignId)
$manifestPayload.Add("campaignScope", $Family)
$manifestPayload.Add("createdAtUtc", $runTimestampUtc)
$manifestPayload.Add("baseUrl", $BaseUrl)
$manifestPayload.Add("outputRoot", $OutputRoot)
$manifestPayload.Add("status", $overallStatus)
$manifestPayload.Add("entries", $entriesArray)

Write-PilotConsolidationManifest -OutputPath $manifestPath -Payload $manifestPayload
Write-PilotConsolidationReport -OutputPath $textReportPath -TextPayload ($reportLines -join [Environment]::NewLine)
Write-StatisticalRigorSummary -Profile $statisticalRigor -Entries $entriesArray -OutputManifestPath $rigorManifestPath -OutputTextPath $rigorTextPath -CampaignId $campaignId -FamilyScope $Family -CreatedAtUtc $runTimestampUtc

Write-Host "Manifest campagna     : $manifestPath"
Write-Host "Report campagna       : $textReportPath"
Write-Host "Rigor summary         : $rigorManifestPath"
Write-Host "Rigor report          : $rigorTextPath"
Write-Host "Stato campagna        : $overallStatus"

if ($overallStatus -eq "failed") {
    exit 1
}

exit 0
