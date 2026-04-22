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
        "Questo smoke test standalone non crea automaticamente il port-forward Kubernetes.",
        "Il BaseUrl specificato deve essere già raggiungibile prima dell'esecuzione dello script.",
        "Se stai eseguendo la pipeline tramite i launcher principali e usi http://localhost:8080, il port-forward viene gestito automaticamente a livello di launcher.",
        "Se invece stai eseguendo direttamente questo script standalone, prepara prima l'endpoint oppure crea manualmente il port-forward verso service/localai-server."
    )

    if (-not [string]::IsNullOrWhiteSpace($BaseUrl)) {
        $guidanceLines += "BaseUrl richiesto: $BaseUrl"
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
    Write-Host "[1/3] Verifica disponibilita' del modello tramite /v1/models ..." -ForegroundColor Yellow

    $modelsResponse = Invoke-RestMethod `
        -Uri "$BaseUrl/v1/models" `
        -Method Get

    if (-not $modelsResponse.data) {
        throw "La risposta di /v1/models non contiene il campo 'data'."
    }

    $availableModels = $modelsResponse.data | ForEach-Object { $_.id }

    Write-Host "Modelli disponibili:" -ForegroundColor Green
    $availableModels | ForEach-Object { Write-Host " - $_" }

    if ($availableModels -notcontains $Model) {
        throw "Il modello richiesto '$Model' non è presente nella risposta di /v1/models."
    }

    Write-Host ""
    Write-Host "[2/3] Invio richiesta a /v1/chat/completions ..." -ForegroundColor Yellow

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
        throw "La risposta di /v1/chat/completions non contiene il campo 'choices'."
    }

    $messageContent = $chatResponse.choices[0].message.content

    Write-Host ""
    Write-Host "[3/3] Risposta ricevuta correttamente." -ForegroundColor Green
    Write-Host ""

    Write-Host "Contenuto del messaggio generato:" -ForegroundColor Cyan
    Write-Host "---------------------------------------------"
    Write-Host $messageContent
    Write-Host "---------------------------------------------"
    Write-Host ""

    Write-Host "Risposta JSON completa:" -ForegroundColor Cyan
    $chatResponse | ConvertTo-Json -Depth 10

    Write-Host ""
    Write-Host "VALIDAZIONE API COMPLETATA CON SUCCESSO." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host ""

    if ($ExitUnsupportedOnTimeout -and (Test-IsTimeoutException -Exception $_.Exception)) {
        Write-Host "SCENARIO OPERATIVAMENTE NON SUPPORTATO." -ForegroundColor Yellow
        Write-Host ("La richiesta di smoke test verso /v1/chat/completions per il modello '{0}' non ha restituito una risposta entro {1} secondi." -f $Model, $RequestTimeoutSeconds) -ForegroundColor Yellow
        Write-Host "Il modello viene classificato come non supportato operativamente nella configurazione corrente." -ForegroundColor Yellow
        exit $UnsupportedExitCode
    }

    Write-Host "ERRORE DURANTE LA VALIDAZIONE API." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}