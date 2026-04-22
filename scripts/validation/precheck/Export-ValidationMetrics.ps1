param(
    [string]$BaseUrl = "http://localhost:8080",
    [string]$Model = "llama-3.2-1b-instruct:q4_k_m",
    [int]$Iterations = 5,
    [int]$PauseSeconds = 2,
    [string]$OutputPrefix,
    [string]$MetricSetConfig
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..\..")).Path

if ([string]::IsNullOrWhiteSpace($OutputPrefix)) {
    $OutputPrefix = Join-Path $repoRoot "results\validation\minimal-metrics"
}

if ([string]::IsNullOrWhiteSpace($MetricSetConfig)) {
    $MetricSetConfig = Join-Path $repoRoot "config\metric-set\MS1.json"
}

if (-not (Test-Path $MetricSetConfig)) {
    throw "Il file di metric set non esiste: $MetricSetConfig"
}

function Get-Percentile {
    param(
        [double[]]$Values,
        [double]$Percentile
    )

    if (-not $Values -or $Values.Count -eq 0) {
        return $null
    }

    $sorted = $Values | Sort-Object
    if ($sorted.Count -eq 1) {
        return [math]::Round($sorted[0], 2)
    }

    $rank = ($Percentile / 100) * ($sorted.Count - 1)
    $lowerIndex = [math]::Floor($rank)
    $upperIndex = [math]::Ceiling($rank)

    if ($lowerIndex -eq $upperIndex) {
        return [math]::Round($sorted[$lowerIndex], 2)
    }

    $weight = $rank - $lowerIndex
    $value = $sorted[$lowerIndex] + ($sorted[$upperIndex] - $sorted[$lowerIndex]) * $weight
    return [math]::Round($value, 2)
}

$metricSetProfile = Get-Content -Path $MetricSetConfig -Raw -Encoding UTF8 | ConvertFrom-Json

$outputDirectory = Split-Path -Parent $OutputPrefix
if (-not [string]::IsNullOrWhiteSpace($outputDirectory) -and -not (Test-Path $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " LocalAI Minimal Metrics Validation" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Repository   : $repoRoot"
Write-Host "Base URL     : $BaseUrl"
Write-Host "Model        : $Model"
Write-Host "Iterations   : $Iterations"
Write-Host "Pause (sec)  : $PauseSeconds"
Write-Host "OutputPrefix : $OutputPrefix"
Write-Host "Metric set   : $MetricSetConfig"
Write-Host ""

$results = @()
$batchStopwatch = [System.Diagnostics.Stopwatch]::StartNew()

for ($i = 1; $i -le $Iterations; $i++) {
    $prompt = "Reply with only READY-$i."

    $bodyObject = @{
        model = $Model
        messages = @(
            @{
                role    = "user"
                content = $prompt
            }
        )
        temperature = 0.1
    }

    $bodyJson = $bodyObject | ConvertTo-Json -Depth 10 -Compress
    $timestamp = Get-Date
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

    try {
        $response = Invoke-RestMethod `
            -Uri "$BaseUrl/v1/chat/completions" `
            -Method Post `
            -ContentType "application/json" `
            -Body $bodyJson

        $stopwatch.Stop()

        $content = $null
        $promptTokens = $null
        $completionTokens = $null
        $totalTokens = $null
        $finishReason = $null

        if ($response.choices -and $response.choices.Count -gt 0) {
            $content = $response.choices[0].message.content
            $finishReason = $response.choices[0].finish_reason
        }

        if ($response.usage) {
            $promptTokens = $response.usage.prompt_tokens
            $completionTokens = $response.usage.completion_tokens
            $totalTokens = $response.usage.total_tokens
        }

        $row = [PSCustomObject]@{
            iteration          = $i
            timestamp          = $timestamp.ToString("o")
            success            = $true
            latency_ms         = [math]::Round($stopwatch.Elapsed.TotalMilliseconds, 2)
            model              = $response.model
            finish_reason      = $finishReason
            prompt_tokens      = $promptTokens
            completion_tokens  = $completionTokens
            total_tokens       = $totalTokens
            prompt             = $prompt
            response_content   = $content
            error_message      = $null
        }

        $results += $row

        Write-Host "[$i/$Iterations] OK - latency: $($row.latency_ms) ms - response: $($row.response_content)" -ForegroundColor Green
    }
    catch {
        $stopwatch.Stop()

        $row = [PSCustomObject]@{
            iteration          = $i
            timestamp          = $timestamp.ToString("o")
            success            = $false
            latency_ms         = [math]::Round($stopwatch.Elapsed.TotalMilliseconds, 2)
            model              = $Model
            finish_reason      = $null
            prompt_tokens      = $null
            completion_tokens  = $null
            total_tokens       = $null
            prompt             = $prompt
            response_content   = $null
            error_message      = $_.Exception.Message
        }

        $results += $row

        Write-Host "[$i/$Iterations] ERROR - latency: $($row.latency_ms) ms - error: $($row.error_message)" -ForegroundColor Red
    }

    if ($i -lt $Iterations) {
        Start-Sleep -Seconds $PauseSeconds
    }
}

$batchStopwatch.Stop()
$successRows = $results | Where-Object { $_.success -eq $true }
$latencies = @($successRows | ForEach-Object { [double]$_.latency_ms })
$successfulRequests = ($results | Where-Object { $_.success -eq $true }).Count
$failedRequests = ($results | Where-Object { $_.success -eq $false }).Count
$elapsedSeconds = [math]::Round($batchStopwatch.Elapsed.TotalSeconds, 4)
$throughputRps = if ($elapsedSeconds -gt 0) { [math]::Round(($successfulRequests / $elapsedSeconds), 4) } else { $null }
$meanResponseTime = if ($latencies.Count -gt 0) { [math]::Round((($latencies | Measure-Object -Average).Average), 2) } else { $null }

$summary = [PSCustomObject]@{
    timestamp_utc           = (Get-Date).ToUniversalTime().ToString("o")
    base_url                = $BaseUrl
    model                   = $Model
    metric_set_profile_id   = [string]$metricSetProfile.profileId
    iterations              = $Iterations
    request_count           = $results.Count
    successful_requests     = $successfulRequests
    failed_requests         = $failedRequests
    failure_count           = $failedRequests
    success_rate_percent    = if ($Iterations -gt 0) { [math]::Round((($successfulRequests / $Iterations) * 100), 2) } else { 0 }
    mean_response_time_ms   = $meanResponseTime
    p50_response_time_ms    = Get-Percentile -Values $latencies -Percentile 50
    p95_response_time_ms    = Get-Percentile -Values $latencies -Percentile 95
    p99_response_time_ms    = Get-Percentile -Values $latencies -Percentile 99
    throughput_rps          = $throughputRps
    avg_latency_ms          = $meanResponseTime
    min_latency_ms          = if ($latencies.Count -gt 0) { [math]::Round((($latencies | Measure-Object -Minimum).Minimum), 2) } else { $null }
    max_latency_ms          = if ($latencies.Count -gt 0) { [math]::Round((($latencies | Measure-Object -Maximum).Maximum), 2) } else { $null }
    p50_latency_ms          = Get-Percentile -Values $latencies -Percentile 50
    p95_latency_ms          = Get-Percentile -Values $latencies -Percentile 95
    total_prompt_tokens     = (($successRows | Measure-Object -Property prompt_tokens -Sum).Sum)
    total_completion_tokens = (($successRows | Measure-Object -Property completion_tokens -Sum).Sum)
    total_tokens            = (($successRows | Measure-Object -Property total_tokens -Sum).Sum)
}

$csvPath = "$OutputPrefix-results.csv"
$jsonPath = "$OutputPrefix-summary.json"

$results | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
$summary | ConvertTo-Json -Depth 10 | Set-Content -Path $jsonPath -Encoding UTF8

Write-Host ""
Write-Host "==================== SUMMARY ====================" -ForegroundColor Cyan
$summary | Format-List
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Risultati salvati in: $csvPath" -ForegroundColor Yellow
Write-Host "Riepilogo salvato in: $jsonPath" -ForegroundColor Yellow
