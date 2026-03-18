$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$composeFile = Join-Path $projectRoot "docker-compose.yml"

if (-not (Test-Path $composeFile)) {
	Write-Error "Compose file not found: $composeFile"
	exit 1
}

docker compose -f $composeFile down
Write-Output "BrainAPI stopped."
