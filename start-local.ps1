Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-PythonBootstrapCommand {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return @($pythonCmd.Path)
    }

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        return @($pyCmd.Path, "-3")
    }

    return $null
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$pythonBootstrap = Get-PythonBootstrapCommand
if ($null -eq $pythonBootstrap) {
    Write-Error "Python is not installed or not on PATH. Install Python 3.10+ and retry ./start-local.ps1"
    exit 1
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Output "Creating local virtual environment..."
    if ($pythonBootstrap.Length -gt 1) {
        & $pythonBootstrap[0] @($pythonBootstrap[1..($pythonBootstrap.Length - 1)]) -m venv .venv
    }
    else {
        & $pythonBootstrap[0] -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create virtual environment."
        exit 1
    }
}

. .\.venv\Scripts\Activate.ps1

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item .env.example .env
        Write-Output "Created .env from .env.example"
    }
    else {
        Write-Error "Missing .env and .env.example. Create .env before starting."
        exit 1
    }
}

Write-Output "Installing/updating Python dependencies..."
python -m pip install --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Error "Dependency installation failed."
    exit 1
}

$env:DATABASE_URL = "sqlite:///./brainapi.db"
$env:REDIS_URL = ""
$env:ENABLE_USAGE_METERING = "true"
$env:AUTO_CREATE_TABLES = "true"

Write-Output "Starting BrainAPI locally on http://127.0.0.1:8000"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
