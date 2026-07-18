function Test-LocalPortReachable {
    param(
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutMs = 1000
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $asyncResult = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $asyncResult.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }

        $client.EndConnect($asyncResult)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Test-HttpEndpointReady {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 5
    )

    try {
        $null = Invoke-WebRequest -Uri $Url -Method Get -UseBasicParsing -TimeoutSec $TimeoutSeconds -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

function Wait-HttpEndpointReady {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 60,
        [int]$PollIntervalMilliseconds = 1000,
        [int]$RequestTimeoutSeconds = 5,
        [string]$ContextMessage = 'endpoint HTTP'
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpEndpointReady -Url $Url -TimeoutSeconds $RequestTimeoutSeconds) {
            return $true
        }

        Start-Sleep -Milliseconds $PollIntervalMilliseconds
    }

    throw "Timeout while waiting for HTTP readiness of $ContextMessage at $Url."
}

function Get-LocalPortOwningProcesses {
    param(
        [Parameter(Mandatory = $true)][int]$Port
    )

    $processIds = @()

    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique
        if ($connections) {
            $processIds += $connections
        }
    }
    catch {
        $netstatOutput = netstat -ano -p tcp 2>$null
        if ($LASTEXITCODE -eq 0 -and $netstatOutput) {
            $pattern = ":$Port\s"
            foreach ($line in $netstatOutput) {
                if ($line -match $pattern) {
                    $tokens = ($line -split '\s+') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
                    if ($tokens.Count -ge 5) {
                        $pidCandidate = $tokens[-1]
                        if ($pidCandidate -match '^\d+$') {
                            $processIds += [int]$pidCandidate
                        }
                    }
                }
            }
        }
    }

    $processIds = $processIds | Sort-Object -Unique
    $processes = @()
    foreach ($processId in $processIds) {
        try {
            $processes += Get-Process -Id $processId -ErrorAction Stop
        }
        catch {
        }
    }

    return @($processes | Sort-Object Id -Unique)
}

function Stop-KubectlPortForwardProcessesOnPort {
    param(
        [Parameter(Mandatory = $true)][int]$Port
    )

    $processes = @(Get-LocalPortOwningProcesses -Port $Port)
    if (-not $processes -or $processes.Count -eq 0) {
        return @()
    }

    $stopped = @()
    foreach ($process in $processes) {
        if ($process.ProcessName -ieq 'kubectl') {
            try {
                Stop-Process -Id $process.Id -Force -ErrorAction Stop
                $stopped += $process
            }
            catch {
            }
        }
    }

    if ($stopped.Count -gt 0) {
        Start-Sleep -Seconds 1
    }

    return @($stopped)
}


function Invoke-KubectlForPortForward {
    param(
        [string]$KubeconfigPath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
        throw 'kubectl is not available in PATH. Unable to run Kubernetes checks for port-forwarding.'
    }

    $kubectlArgs = @()
    if (-not [string]::IsNullOrWhiteSpace($KubeconfigPath)) {
        $kubectlArgs += @('--kubeconfig', $KubeconfigPath)
    }
    $kubectlArgs += $Arguments

    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) 'localai-portforward-kubectl'
    if (-not (Test-Path -Path $tempRoot)) {
        New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    }

    $token = [guid]::NewGuid().ToString('N')
    $stdoutFile = Join-Path $tempRoot ("kubectl_${token}_stdout.log")
    $stderrFile = Join-Path $tempRoot ("kubectl_${token}_stderr.log")

    try {
        $process = Start-Process -FilePath 'kubectl' -ArgumentList $kubectlArgs -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile -PassThru -WindowStyle Hidden -Wait
        $stdoutLines = @()
        $stderrLines = @()

        if (Test-Path -Path $stdoutFile) {
            $stdoutLines = @(Get-Content -Path $stdoutFile -ErrorAction SilentlyContinue)
        }
        if (Test-Path -Path $stderrFile) {
            $stderrLines = @(Get-Content -Path $stderrFile -ErrorAction SilentlyContinue)
        }

        $combinedOutput = @($stdoutLines + $stderrLines)

        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Output   = $combinedOutput
            Stdout   = $stdoutLines
            Stderr   = $stderrLines
            Command  = @($kubectlArgs)
        }
    }
    finally {
        Remove-Item -Path $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
    }
}

function Wait-KubernetesServiceBackendReady {
    param(
        [string]$KubeconfigPath,
        [Parameter(Mandatory = $true)][string]$Namespace,
        [Parameter(Mandatory = $true)][string]$ServiceName,
        [int]$TimeoutSeconds = 180,
        [int]$PollIntervalMilliseconds = 1000
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $deploymentName = $ServiceName
    $serviceSelector = "app=$ServiceName"

    while ((Get-Date) -lt $deadline) {
        $rollout = Invoke-KubectlForPortForward -KubeconfigPath $KubeconfigPath -Arguments @(
            'rollout', 'status', ("deployment/{0}" -f $deploymentName), '-n', $Namespace, '--timeout=5s'
        )
        if ($rollout.ExitCode -ne 0) {
            Start-Sleep -Milliseconds $PollIntervalMilliseconds
            continue
        }

        $podWait = Invoke-KubectlForPortForward -KubeconfigPath $KubeconfigPath -Arguments @(
            'wait', '--for=condition=Ready', 'pod', '-l', $serviceSelector, '-n', $Namespace, '--timeout=5s'
        )
        if ($podWait.ExitCode -ne 0) {
            Start-Sleep -Milliseconds $PollIntervalMilliseconds
            continue
        }

        $endpoints = Invoke-KubectlForPortForward -KubeconfigPath $KubeconfigPath -Arguments @(
            'get', 'endpointslice', '-n', $Namespace, '-l', ("kubernetes.io/service-name={0}" -f $ServiceName), '-o', 'jsonpath={.items[*].endpoints[*].addresses[*]}'
        )
        $endpointText = ($endpoints.Output -join ' ').Trim()
        if ($endpoints.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($endpointText)) {
            return $true
        }

        Start-Sleep -Milliseconds $PollIntervalMilliseconds
    }

    $rolloutDiag = Invoke-KubectlForPortForward -KubeconfigPath $KubeconfigPath -Arguments @(
        'rollout', 'status', ("deployment/{0}" -f $deploymentName), '-n', $Namespace, '--timeout=5s'
    )
    $podsDiag = Invoke-KubectlForPortForward -KubeconfigPath $KubeconfigPath -Arguments @(
        'get', 'pods', '-n', $Namespace, '-l', $serviceSelector, '-o', 'wide'
    )
    $endpointsDiag = Invoke-KubectlForPortForward -KubeconfigPath $KubeconfigPath -Arguments @(
        'get', 'endpointslice', '-n', $Namespace, '-l', ("kubernetes.io/service-name={0}" -f $ServiceName), '-o', 'yaml'
    )

    $message = "Timeout while waiting for Kubernetes readiness of service/$ServiceName in namespace $Namespace."

    if ($rolloutDiag.Output) {
        $message += "`nRollout status:`n" + (($rolloutDiag.Output | Select-Object -Last 20) -join [Environment]::NewLine)
    }
    if ($podsDiag.Output) {
        $message += "`nPod selector ($serviceSelector):`n" + (($podsDiag.Output | Select-Object -Last 20) -join [Environment]::NewLine)
    }
    if ($endpointsDiag.Output) {
        $message += "`nEndpoints:`n" + (($endpointsDiag.Output | Select-Object -Last 40) -join [Environment]::NewLine)
    }

    throw $message
}

function Ensure-LocalKubernetesPortForward {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$BaseUrl,
        [string]$KubeconfigPath,
        [string]$Namespace,
        [string]$ServiceName = 'localai-server',
        [int]$RemotePort = 8080,
        [int]$ConnectTimeoutMs = 1000,
        [int]$StartupTimeoutSeconds = 30,
        [int]$HttpReadinessTimeoutSeconds = 120,
        [string]$HttpReadinessPath = '/v1/models'
    )

    if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
        return $false
    }

    try {
        $uri = [System.Uri]$BaseUrl
    }
    catch {
        throw "Invalid BaseUrl for port-forward management: $BaseUrl"
    }

    $hostName = $uri.Host
    $isLocalHost = @('localhost', '127.0.0.1', '[::1]', '::1') -contains $hostName
    if (-not $isLocalHost) {
        return $false
    }

    $localPort = if ($uri.IsDefaultPort) {
        if ($uri.Scheme -ieq 'https') { 443 } else { 80 }
    }
    else {
        [int]$uri.Port
    }

    $normalizedReadinessPath = if ([string]::IsNullOrWhiteSpace($HttpReadinessPath)) {
        '/'
    }
    elseif ($HttpReadinessPath.StartsWith('/')) {
        $HttpReadinessPath
    }
    else {
        "/$HttpReadinessPath"
    }

    $readinessUriBuilder = New-Object System.UriBuilder($uri)
    $readinessUriBuilder.Path = $normalizedReadinessPath
    $readinessUriBuilder.Query = ''
    $readinessUrl = $readinessUriBuilder.Uri.AbsoluteUri

    $existingPortReachable = Test-LocalPortReachable -HostName '127.0.0.1' -Port $localPort -TimeoutMs $ConnectTimeoutMs
    if ($existingPortReachable) {
        $stoppedProcesses = @(Stop-KubectlPortForwardProcessesOnPort -Port $localPort)
        if ($stoppedProcesses.Count -gt 0) {
            Write-Host (
                "Detected an existing local listener on localhost:{0}. Stopped residual kubectl processes before creating a new port-forward: {1}." -f
                $localPort,
                (($stoppedProcesses | ForEach-Object { $_.Id }) -join ', ')
            ) -ForegroundColor Yellow
        }

        if (Test-LocalPortReachable -HostName '127.0.0.1' -Port $localPort -TimeoutMs $ConnectTimeoutMs) {
            $owners = @(Get-LocalPortOwningProcesses -Port $localPort)
            $ownerSummary = if ($owners.Count -gt 0) {
                ($owners | ForEach-Object { "{0} (PID {1})" -f $_.ProcessName, $_.Id }) -join ', '
            }
            else {
                'undetermined process'
            }

            throw "Local port localhost:$localPort is already in use by $ownerSummary. A new port-forward cannot be created safely."
        }
    }

    if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
        throw 'kubectl is not available in PATH. Unable to create the port-forward automatically.'
    }

    if ([string]::IsNullOrWhiteSpace($Namespace)) {
        throw 'Namespace is required to automatically create the port-forward to the Kubernetes service.'
    }

    Write-Host ("Checking Kubernetes backend readiness for service/{0} in namespace {1} before local port-forwarding." -f $ServiceName, $Namespace) -ForegroundColor DarkYellow
    Wait-KubernetesServiceBackendReady -KubeconfigPath $KubeconfigPath -Namespace $Namespace -ServiceName $ServiceName -TimeoutSeconds $HttpReadinessTimeoutSeconds
    Start-Sleep -Seconds 2

    $runtimeDir = Join-Path $RepoRoot 'results\_runtime\port-forward'
    if (-not (Test-Path -Path $runtimeDir)) {
        New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
    }

    $safeServiceName = ($ServiceName -replace '[^A-Za-z0-9._-]', '_')
    $logPrefix = Join-Path $runtimeDir ("{0}_{1}" -f $safeServiceName, $localPort)
    $stdoutLog = "{0}_stdout.log" -f $logPrefix
    $stderrLog = "{0}_stderr.log" -f $logPrefix

    Remove-Item -Path $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue

    $kubectlArgs = @()
    if (-not [string]::IsNullOrWhiteSpace($KubeconfigPath)) {
        $kubectlArgs += @('--kubeconfig', $KubeconfigPath)
    }
    $kubectlArgs += @('port-forward', '-n', $Namespace, ("service/{0}" -f $ServiceName), ("{0}:{1}" -f $localPort, $RemotePort))

    $overallDeadline = (Get-Date).AddSeconds([Math]::Max([Math]::Max($HttpReadinessTimeoutSeconds, $StartupTimeoutSeconds), 30))
    $attempt = 0
    $lastFailureMessage = ''

    while ((Get-Date) -lt $overallDeadline) {
        $attempt++
        Remove-Item -Path $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue

        Write-Host ("Local port-forward is not reachable on {0}:{1}. Automatic start: kubectl {2} (attempt {3})" -f $hostName, $localPort, ($kubectlArgs -join ' '), $attempt) -ForegroundColor Yellow
        $process = Start-Process -FilePath 'kubectl' -ArgumentList $kubectlArgs -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru -WindowStyle Hidden

        $startupDeadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
        $tcpReady = $false
        while ((Get-Date) -lt $startupDeadline) {
            if ($process.HasExited) {
                break
            }

            if (Test-LocalPortReachable -HostName '127.0.0.1' -Port $localPort -TimeoutMs $ConnectTimeoutMs) {
                $tcpReady = $true
                break
            }

            Start-Sleep -Milliseconds 500
        }

        $stderrTail = ''
        if (Test-Path -Path $stderrLog) {
            $stderrTail = (Get-Content -Path $stderrLog -Tail 20 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
        }

        if (-not $tcpReady) {
            if (-not $process.HasExited) {
                try { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } catch {}
            }

            if ($process.HasExited) {
                $lastFailureMessage = "The kubectl port-forward process terminated prematurely (PID $($process.Id), exit code $($process.ExitCode))."
                if (-not [string]::IsNullOrWhiteSpace($stderrTail)) {
                    $lastFailureMessage += "`nDettagli stderr:`n$stderrTail"
                }
            }
            else {
                $lastFailureMessage = "Timeout while waiting for kubectl port-forward to service/$ServiceName on localhost:$localPort."
                if (-not [string]::IsNullOrWhiteSpace($stderrTail)) {
                    $lastFailureMessage += "`nDettagli stderr:`n$stderrTail"
                }
            }

            if ((Get-Date) -lt $overallDeadline) {
                Write-Host "Port-forward is not stable yet; starting a new attempt..." -ForegroundColor DarkYellow
                Start-Sleep -Seconds 2
                continue
            }

            throw $lastFailureMessage
        }

        Write-Host ("Port-forward active on {0}:{1} (PID {2}). Checking HTTP readiness on {3}." -f $hostName, $localPort, $process.Id, $readinessUrl) -ForegroundColor DarkYellow

        $httpReady = $false
        while ((Get-Date) -lt $overallDeadline) {
            if ($process.HasExited) {
                break
            }

            if (Test-HttpEndpointReady -Url $readinessUrl -TimeoutSeconds 5) {
                $httpReady = $true
                break
            }

            Start-Sleep -Seconds 1
        }

        if ($httpReady) {
            return $true
        }

        $stderrTail = ''
        if (Test-Path -Path $stderrLog) {
            $stderrTail = (Get-Content -Path $stderrLog -Tail 20 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
        }

        if (-not $process.HasExited) {
            try { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } catch {}
            $lastFailureMessage = "Timeout while waiting for HTTP readiness of service/$ServiceName behind the local port-forward at $readinessUrl."
            if (-not [string]::IsNullOrWhiteSpace($stderrTail)) {
                $lastFailureMessage += "`nDettagli stderr port-forward:`n$stderrTail"
            }
            throw $lastFailureMessage
        }

        $lastFailureMessage = "The kubectl port-forward process terminated while waiting for HTTP readiness (PID $($process.Id), exit code $($process.ExitCode))."
        if (-not [string]::IsNullOrWhiteSpace($stderrTail)) {
            $lastFailureMessage += "`nDettagli stderr port-forward:`n$stderrTail"
        }

        if ((Get-Date) -lt $overallDeadline) {
            Write-Host "The backend was not ready to accept connections behind the port-forward yet; starting a new attempt..." -ForegroundColor DarkYellow
            Start-Sleep -Seconds 2
            continue
        }

        throw $lastFailureMessage
    }

    if (-not [string]::IsNullOrWhiteSpace($lastFailureMessage)) {
        throw $lastFailureMessage
    }

    throw "Timeout while waiting for the local port-forward to service/$ServiceName on localhost:$localPort."
}
