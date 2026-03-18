function Test-DockerReady {
	docker info *> $null
	return ($LASTEXITCODE -eq 0)
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$composeFile = Join-Path $projectRoot "docker-compose.yml"
$envFile = Join-Path $projectRoot ".env"
$envExampleFile = Join-Path $projectRoot ".env.example"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
	Write-Error "Docker CLI is not installed."
	exit 1
}

if (-not (Test-DockerReady)) {
	$dockerDesktopPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
	if (Test-Path $dockerDesktopPath) {
		Write-Output "Starting Docker Desktop..."
		Start-Process $dockerDesktopPath
	}

	$maxAttempts = 36
	for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
		Start-Sleep -Seconds 5
		if (Test-DockerReady) {
			break
		}
		Write-Output "Waiting for Docker engine... ($attempt/$maxAttempts)"
	}
}

if (-not (Test-DockerReady)) {
	Write-Error "Docker engine is not ready. Open Docker Desktop and retry ./start.ps1"
	exit 1
}

if (-not (Test-Path $composeFile)) {
	Write-Error "Compose file not found: $composeFile"
	exit 1
}

if (-not (Test-Path $envFile)) {
	if (Test-Path $envExampleFile) {
		Copy-Item $envExampleFile $envFile
		Write-Warning "Created .env from .env.example. Review API key values before production use."
	}
	else {
		Write-Error "Missing .env and .env.example at project root."
		exit 1
	}
}

docker compose -f $composeFile up -d --build
if ($LASTEXITCODE -ne 0) {
	Write-Error "Failed to start docker compose stack."
	exit 1
}

$healthUrl = "http://localhost:8000/health"
$maxAttempts = 30
for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
	Start-Sleep -Seconds 2
	try {
		$health = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 3
		if ($health.status -eq "ok") {
			Write-Output "BrainAPI started. Docs: http://localhost:8000/docs"
			exit 0
		}
	}
	catch {
	}
	Write-Output "Waiting for API health... ($attempt/$maxAttempts)"
}

Write-Warning "Containers started, but API health check did not pass in time. Check logs with: docker compose -f $composeFile logs api"
