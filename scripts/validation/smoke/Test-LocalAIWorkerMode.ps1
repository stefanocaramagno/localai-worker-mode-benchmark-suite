param(
    [string]$BaseUrl = "http://localhost:8080",
    [string]$Model = "llama-3.2-1b-instruct:q4_k_m",
    [int]$RequestTimeoutSeconds = 120,
    [switch]$ExitUnsupportedOnTimeout,
    [int]$UnsupportedExitCode = 42
)

$ErrorActionPreference = "Stop"

function Test-IsTimeoutException {
    param(
        [Parameter(Mandatory = $true)]
        [System.Exception]$Exception
    )

    $current = $Exception
    while ($null -ne $current) {
        if ($current -is [System.TimeoutException]) { return $true }
        if ($current -is [System.Threading.Tasks.TaskCanceledException]) { return $true }
        if ($current -is [System.Net.WebException] -and $current.Status -eq [System.Net.WebExceptionStatus]::Timeout) { return $true }

        $message = [string]$current.Message
        if ($message -match '(?i)timeout|timed out|time-out|tempo scaduto|operazione scaduta') {
            return $true
        }

        $current = $current.InnerException
    }

    return $false
}

function Get-StandaloneEndpointPreparationGuidance {
    param([string]$BaseUrl)

    $guidanceLines = @(
        "This standalone smoke test does not automatically create the Kubernetes port-forward.",
        "The specified BaseUrl must already be reachable before executing this script.",
        "When running through the main launchers with http://localhost:8080, port-forwarding is managed automatically by the launcher layer.",
        "If you are running this standalone script directly, prepare the endpoint first or create the port-forward to service/localai-server manually."
    )

    if (-not [string]::IsNullOrWhiteSpace($BaseUrl)) {
        $guidanceLines += "Required BaseUrl: $BaseUrl"
    }

    return ($guidanceLines -join ' ')
}

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " LocalAI Worker Mode Validation Script" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "Base URL : $BaseUrl"
Write-Host "Model    : $Model"
Write-Host ""
Write-Host (Get-StandaloneEndpointPreparationGuidance -BaseUrl $BaseUrl) -ForegroundColor DarkYellow
Write-Host ""

try {
    Write-Host "[1/3] Checking model availability through /v1/models ..." -ForegroundColor Yellow

    $modelsResponse = Invoke-RestMethod `
        -Uri "$BaseUrl/v1/models" `
        -Method Get `
        -TimeoutSec $RequestTimeoutSeconds

    if (-not $modelsResponse.data) {
        throw "The /v1/models response does not contain the 'data' field."
    }

    $availableModels = $modelsResponse.data | ForEach-Object { $_.id }

    Write-Host "Available models:" -ForegroundColor Green
    $availableModels | ForEach-Object { Write-Host " - $_" }

    if ($availableModels -notcontains $Model) {
        throw "The requested model '$Model' is not present in the /v1/models response."
    }

    Write-Host ""
    Write-Host "[2/3] Sending request to /v1/chat/completions ..." -ForegroundColor Yellow

    $bodyObject = @{
        model = $Model
        messages = @(
            @{
                role    = "user"
                content = "Reply with only READY."
            }
        )
        temperature = 0.1
    }

    $bodyJson = $bodyObject | ConvertTo-Json -Depth 10 -Compress

    $chatResponse = Invoke-RestMethod `
        -Uri "$BaseUrl/v1/chat/completions" `
        -Method Post `
        -ContentType "application/json" `
        -Body $bodyJson `
        -TimeoutSec $RequestTimeoutSeconds

    if (-not $chatResponse.choices) {
        throw "The /v1/chat/completions response does not contain the 'choices' field."
    }

    $messageContent = $chatResponse.choices[0].message.content

    Write-Host ""
    Write-Host "[3/3] Response received successfully." -ForegroundColor Green
    Write-Host ""

    Write-Host "Generated message content:" -ForegroundColor Cyan
    Write-Host "---------------------------------------------"
    Write-Host $messageContent
    Write-Host "---------------------------------------------"
    Write-Host ""

    Write-Host "Full JSON response:" -ForegroundColor Cyan
    $chatResponse | ConvertTo-Json -Depth 10

    Write-Host ""
    Write-Host "API VALIDATION COMPLETED SUCCESSFULLY." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host ""

    if ($ExitUnsupportedOnTimeout -and (Test-IsTimeoutException -Exception $_.Exception)) {
        Write-Host "SCENARIO UNSUPPORTED UNDER CURRENT CONSTRAINTS." -ForegroundColor Yellow
        Write-Host ("API validation for model '{0}' did not complete within {1} seconds." -f $Model, $RequestTimeoutSeconds) -ForegroundColor Yellow
        Write-Host "The condition is reported to the launcher as unsupported evidence; warm-up and measurement must be intentionally skipped." -ForegroundColor Yellow
        exit $UnsupportedExitCode
    }

    Write-Host "API VALIDATION FAILED." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}