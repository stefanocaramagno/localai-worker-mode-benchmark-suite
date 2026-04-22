Set-StrictMode -Version Latest

function Get-StatisticalRigorProfile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ProfileFile
    )

    if (-not (Test-Path $ProfileFile)) {
        throw "Il file di statistical rigor non esiste: $ProfileFile"
    }

    $data = Get-Content -Path $ProfileFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $required = @(
        "profileId",
        "description",
        "targetRequestType",
        "targetRequestName",
        "fallbackToAggregated",
        "requiredReplicaCount",
        "minimumSuccessfulReplicaCount",
        "coolDownBetweenReplicasSeconds",
        "coolDownBetweenScenariosSeconds",
        "stabilizationTimeoutSeconds",
        "stabilizationPollIntervalSeconds",
        "summaryManifestSuffix",
        "summaryTextSuffix",
        "trackedMetrics",
        "variabilityThresholds"
    )

    foreach ($propertyName in $required) {
        if (-not ($data.PSObject.Properties.Name -contains $propertyName)) {
            throw "Il file di statistical rigor '$ProfileFile' non contiene la proprietà obbligatoria '$propertyName'."
        }
    }

    [pscustomobject]@{
        ProfileFile = (Resolve-Path $ProfileFile).Path
        RawConfig   = $data
    }
}

function Get-MeasurementStatsCsvPath {
    param(
        [Parameter(Mandatory = $true)][string]$SearchRoot,
        [Parameter(Mandatory = $true)][string]$Scenario,
        [Parameter(Mandatory = $true)][string]$Replica,
        [Parameter(Mandatory = $false)][Nullable[datetime]]$NotOlderThanUtc = $null
    )

    if ([string]::IsNullOrWhiteSpace($SearchRoot) -or -not (Test-Path $SearchRoot)) {
        return ""
    }

    $expectedName = "{0}_run{1}_stats.csv" -f $Scenario, $Replica
    $matches = @(
        Get-ChildItem -Path $SearchRoot -Recurse -File -Filter $expectedName -ErrorAction SilentlyContinue |
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
    if ($null -eq $matches -or $matches.Count -eq 0) {
        return ""
    }

    return $matches[0].FullName
}

function New-StatisticalRigorEntry {
    param(
        [Parameter(Mandatory = $true)][string]$Family,
        [Parameter(Mandatory = $true)][string]$Scenario,
        [Parameter(Mandatory = $true)][string]$Replica,
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][int]$ExitCode,
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $false)][string]$StatsCsvPath = ""
    )

    [pscustomobject]@{
        family = $Family
        scenario = $Scenario
        replica = $Replica
        status = $Status
        exitCode = $ExitCode
        command = $Command
        statsCsvPath = $StatsCsvPath
    }
}

function Write-StatisticalRigorSummary {
    param(
        [Parameter(Mandatory = $true)]$Profile,
        [Parameter(Mandatory = $true)][Object[]]$Entries,
        [Parameter(Mandatory = $true)][string]$OutputManifestPath,
        [Parameter(Mandatory = $true)][string]$OutputTextPath,
        [Parameter(Mandatory = $true)][string]$CampaignId,
        [Parameter(Mandatory = $true)][string]$FamilyScope,
        [Parameter(Mandatory = $true)][string]$CreatedAtUtc
    )

    $pythonCode = @'
import csv
import json
import statistics
import sys
from pathlib import Path

profile_path = Path(sys.argv[1])
entries_path = Path(sys.argv[2])
output_manifest_path = Path(sys.argv[3])
output_text_path = Path(sys.argv[4])
campaign_id = sys.argv[5]
family_scope = sys.argv[6]
created_at_utc = sys.argv[7]

profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
entries = json.loads(entries_path.read_text(encoding="utf-8-sig"))

metric_key_map = {
    "request_count": "Request Count",
    "failure_count": "Failure Count",
    "mean_response_time_ms": "Average Response Time",
    "p50_response_time_ms": "50%",
    "p95_response_time_ms": "95%",
    "p99_response_time_ms": "99%",
    "throughput_rps": "Requests/s",
}

def to_number(value):
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def read_target_row(stats_csv_path: Path):
    if not stats_csv_path.exists():
        return None

    with stats_csv_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    target_row = None
    aggregated_row = None
    for row in rows:
        row_type = (row.get("Type") or "").strip()
        row_name = (row.get("Name") or "").strip()
        if row_type == profile["targetRequestType"] and row_name == profile["targetRequestName"]:
            target_row = row
            break
        if row_name == "Aggregated":
            aggregated_row = row

    if target_row is not None:
        return target_row, "target_request"
    if bool(profile["fallbackToAggregated"]) and aggregated_row is not None:
        return aggregated_row, "aggregated_fallback"
    return None

scenario_groups = {}
for entry in entries:
    key = (entry["family"], entry["scenario"])
    scenario_groups.setdefault(key, []).append(entry)

scenario_summaries = []
text_lines = []
text_lines.append("=============================================")
text_lines.append(" Statistical Rigor Summary")
text_lines.append("=============================================")
text_lines.append(f"Profile               : {profile['profileFile']}")
text_lines.append(f"Profile ID            : {profile['profileId']}")
text_lines.append(f"Campaign ID           : {campaign_id}")
text_lines.append(f"Family scope          : {family_scope}")
text_lines.append(f"Created at UTC        : {created_at_utc}")
text_lines.append("")

for (family_name, scenario_name) in sorted(scenario_groups.keys()):
    group_entries = sorted(scenario_groups[(family_name, scenario_name)], key=lambda item: item["replica"])
    successful = []
    replica_rows = []

    for entry in group_entries:
        stats_path = Path(entry.get("statsCsvPath") or "")
        target = None
        source = None
        if entry["status"] == "success" and stats_path:
            result = read_target_row(stats_path)
            if result is not None:
                target, source = result

        replica_metrics = {}
        if target is not None:
            for metric_name in profile["trackedMetrics"]:
                replica_metrics[metric_name] = to_number(target.get(metric_key_map[metric_name], 0))
            successful.append(replica_metrics)

        replica_rows.append({
            "replica": entry["replica"],
            "status": entry["status"],
            "exitCode": int(entry["exitCode"]),
            "statsCsvPath": str(stats_path) if stats_path else "",
            "metricSource": source,
            "metrics": replica_metrics,
        })

    aggregate = {}
    flags = []
    for metric_name in profile["trackedMetrics"]:
        values = [row[metric_name] for row in successful if metric_name in row]
        if values:
            mean_value = statistics.fmean(values)
            stdev_value = statistics.stdev(values) if len(values) > 1 else 0.0
            cv_percent = 0.0 if mean_value == 0 else (stdev_value / mean_value) * 100.0
            aggregate[metric_name] = {
                "mean": mean_value,
                "min": min(values),
                "max": max(values),
                "stdev": stdev_value,
                "cvPercent": cv_percent,
            }
        else:
            aggregate[metric_name] = None

    successful_count = len(successful)
    if successful_count < int(profile["minimumSuccessfulReplicaCount"]):
        flags.append({
            "code": "INSUFFICIENT_SUCCESSFUL_REPLICAS",
            "message": f"Successful replicas {successful_count} below minimum {int(profile['minimumSuccessfulReplicaCount'])}."
        })

    variability_thresholds = profile["variabilityThresholds"]
    mean_cv_threshold = variability_thresholds.get("mean_response_time_cv_percent")
    if aggregate.get("mean_response_time_ms") and mean_cv_threshold is not None:
        if aggregate["mean_response_time_ms"]["cvPercent"] > float(mean_cv_threshold):
            flags.append({
                "code": "HIGH_VARIABILITY_MEAN_RESPONSE_TIME",
                "message": f"Mean response time CV {aggregate['mean_response_time_ms']['cvPercent']:.2f}% above threshold {float(mean_cv_threshold):.2f}%.",
            })

    p95_cv_threshold = variability_thresholds.get("p95_response_time_cv_percent")
    if aggregate.get("p95_response_time_ms") and p95_cv_threshold is not None:
        if aggregate["p95_response_time_ms"]["cvPercent"] > float(p95_cv_threshold):
            flags.append({
                "code": "HIGH_VARIABILITY_P95_RESPONSE_TIME",
                "message": f"P95 response time CV {aggregate['p95_response_time_ms']['cvPercent']:.2f}% above threshold {float(p95_cv_threshold):.2f}%.",
            })

    throughput_cv_threshold = variability_thresholds.get("throughput_cv_percent")
    if aggregate.get("throughput_rps") and throughput_cv_threshold is not None:
        if aggregate["throughput_rps"]["cvPercent"] > float(throughput_cv_threshold):
            flags.append({
                "code": "HIGH_VARIABILITY_THROUGHPUT",
                "message": f"Throughput CV {aggregate['throughput_rps']['cvPercent']:.2f}% above threshold {float(throughput_cv_threshold):.2f}%.",
            })

    scenario_summary = {
        "family": family_name,
        "scenario": scenario_name,
        "requiredReplicaCount": int(profile["requiredReplicaCount"]),
        "minimumSuccessfulReplicaCount": int(profile["minimumSuccessfulReplicaCount"]),
        "observedReplicaCount": len(group_entries),
        "successfulReplicaCount": successful_count,
        "replicas": replica_rows,
        "aggregate": aggregate,
        "flags": flags,
    }
    scenario_summaries.append(scenario_summary)

    text_lines.append(f"Family/Scenario       : {family_name}/{scenario_name}")
    text_lines.append(f"Observed replicas     : {len(group_entries)}")
    text_lines.append(f"Successful replicas   : {successful_count}")
    for metric_name in profile["trackedMetrics"]:
        metric_agg = aggregate.get(metric_name)
        if metric_agg is not None:
            text_lines.append(
                f" - {metric_name}: mean={metric_agg['mean']:.4f} min={metric_agg['min']:.4f} max={metric_agg['max']:.4f} stdev={metric_agg['stdev']:.4f} cv%={metric_agg['cvPercent']:.2f}"
            )
    if flags:
        for flag in flags:
            text_lines.append(f" ! {flag['code']}: {flag['message']}")
    else:
        text_lines.append(" Flags                : none")
    text_lines.append("")

overall_status = "passed"
if any(summary["flags"] for summary in scenario_summaries):
    overall_status = "warning"
if any(summary["successfulReplicaCount"] < int(profile["minimumSuccessfulReplicaCount"]) for summary in scenario_summaries):
    overall_status = "failed"

payload = {
    "statisticalRigorProfile": profile,
    "campaign": {
        "campaignId": campaign_id,
        "familyScope": family_scope,
        "createdAtUtc": created_at_utc,
        "status": overall_status,
    },
    "scenarioSummaries": scenario_summaries,
}

output_manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
output_text_path.write_text("\n".join(text_lines) + "\n", encoding="utf-8")
'@

    $profilePayload = [ordered]@{
        profileFile = $Profile.ProfileFile
        profileId = [string]$Profile.RawConfig.profileId
        description = [string]$Profile.RawConfig.description
        targetRequestType = [string]$Profile.RawConfig.targetRequestType
        targetRequestName = [string]$Profile.RawConfig.targetRequestName
        fallbackToAggregated = [bool]$Profile.RawConfig.fallbackToAggregated
        requiredReplicaCount = [int]$Profile.RawConfig.requiredReplicaCount
        minimumSuccessfulReplicaCount = [int]$Profile.RawConfig.minimumSuccessfulReplicaCount
        trackedMetrics = @($Profile.RawConfig.trackedMetrics)
        variabilityThresholds = $Profile.RawConfig.variabilityThresholds
    }

    $entriesJson = @($Entries) | ConvertTo-Json -Depth 12 -Compress
    $profileJson = $profilePayload | ConvertTo-Json -Depth 12 -Compress

    $outputManifestDirectory = Split-Path -Path $OutputManifestPath -Parent
    $outputTextDirectory = Split-Path -Path $OutputTextPath -Parent
    if ($outputManifestDirectory) {
        New-Item -ItemType Directory -Path $outputManifestDirectory -Force | Out-Null
    }
    if ($outputTextDirectory) {
        New-Item -ItemType Directory -Path $outputTextDirectory -Force | Out-Null
    }

    $tempRoot = Join-Path -Path ([System.IO.Path]::GetTempPath()) -ChildPath ("stat-rigor-" + [System.Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

    $pythonScriptPath = Join-Path -Path $tempRoot -ChildPath "statistical_rigor_runner.py"
    $profileJsonPath = Join-Path -Path $tempRoot -ChildPath "profile.json"
    $entriesJsonPath = Join-Path -Path $tempRoot -ChildPath "entries.json"

    try {
        Set-Content -Path $pythonScriptPath -Value $pythonCode -Encoding UTF8
        Set-Content -Path $profileJsonPath -Value $profileJson -Encoding UTF8
        Set-Content -Path $entriesJsonPath -Value $entriesJson -Encoding UTF8

        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $pythonCommand) {
            $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        }
        if ($null -eq $pythonCommand) {
            throw "Python non è disponibile nel PATH. Impossibile generare il riepilogo di statistical rigor."
        }

        & $pythonCommand.Source $pythonScriptPath $profileJsonPath $entriesJsonPath $OutputManifestPath $OutputTextPath $CampaignId $FamilyScope $CreatedAtUtc
        if ($LASTEXITCODE -ne 0) {
            throw "La generazione del riepilogo di statistical rigor è terminata con exit code $LASTEXITCODE."
        }
    }
    finally {
        if (Test-Path $tempRoot) {
            Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
