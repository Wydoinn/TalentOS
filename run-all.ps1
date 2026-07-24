param(
    [switch]$SkipFrontendInstall
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Join-Path $RepoRoot "backend"
$FrontendRoot = Join-Path $RepoRoot "frontend"

$PythonExe = Join-Path $BackendRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Error "Missing backend virtualenv Python at $PythonExe. Create backend/.venv first."
    exit 1
}

function Start-ServiceWindow {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string]$WorkDir,
        [Parameter(Mandatory = $true)][string]$Command
    )

    $cmdLine = "cd /d `"$WorkDir`" && $Command"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k", $cmdLine -WindowStyle Normal | Out-Null
    Write-Host "[started] $Title"
}

function Get-ListeningPid {
    param(
        [Parameter(Mandatory = $true)][int]$Port
    )

    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($null -eq $connection) {
        return $null
    }

    return [int]$connection.OwningProcess
}

function Start-ServiceIfPortFree {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string]$WorkDir,
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][int]$Port
    )

    $listenerPid = Get-ListeningPid -Port $Port
    if ($null -ne $listenerPid) {
        Write-Host "[skip] $Title already listening on $Port (PID $listenerPid)"
        return
    }

    Start-ServiceWindow -Title $Title -WorkDir $WorkDir -Command $Command
}

if (-not $SkipFrontendInstall) {
    Write-Host "[info] Ensuring frontend dependencies are installed..."
    Set-Location $FrontendRoot
    if (-not (Test-Path (Join-Path $FrontendRoot "node_modules"))) {
        npm install
    }
}

Start-ServiceIfPortFree -Title "TalentOS Auth API" -WorkDir (Join-Path $BackendRoot "authentication") -Command "..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000" -Port 8000
Start-ServiceIfPortFree -Title "TalentOS Anti-Spoofing API" -WorkDir (Join-Path $BackendRoot "anti_spoofing") -Command "..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8080" -Port 8080
Start-ServiceIfPortFree -Title "TalentOS ATS API" -WorkDir (Join-Path $BackendRoot "ats_parser_checker") -Command "..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8090" -Port 8090
Start-ServiceIfPortFree -Title "TalentOS Orchestration API" -WorkDir (Join-Path $BackendRoot "orchestration") -Command "..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001" -Port 8001
Start-ServiceIfPortFree -Title "TalentOS Frontend" -WorkDir $FrontendRoot -Command "npm run dev" -Port 3000

Write-Host "[done] TalentOS stack launch commands issued."
Write-Host "        Frontend:      http://localhost:3000"
Write-Host "        Auth API:      http://127.0.0.1:8000/health"
Write-Host "        Anti-Spoofing: http://127.0.0.1:8080/health"
Write-Host "        ATS API:       http://127.0.0.1:8090/api/health"
Write-Host "        Orchestration: http://127.0.0.1:8001/health"
