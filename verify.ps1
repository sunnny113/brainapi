param(
    [ValidateSet("auto", "docker", "existing")]
    [string]$Mode = "auto",
    [string]$BaseUrl = "http://localhost:8000",
    [int]$HealthTimeoutSeconds = 180,
    [string]$ReportPath = "./smoke-test-report.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-ApiHealthy {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$TimeoutSec = 3
    )

    try {
        $health = Invoke-RestMethod -Uri "$Url/health" -Method GET -TimeoutSec $TimeoutSec
        return ($health.status -eq "ok")
    }
    catch {
        return $false
    }
}

function Wait-ForHealth {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [int]$MaxSeconds
    )

    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-ApiHealthy -Url $Url -TimeoutSec 3) {
            return $true
        }
        Start-Sleep -Seconds 2
    }

    return $false
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$startScript = Join-Path $projectRoot "start.ps1"
$smokeScript = Join-Path $projectRoot "smoke-test.ps1"

if (-not (Test-Path $startScript)) {
    Write-Error "Missing script: $startScript"
    exit 1
}

if (-not (Test-Path $smokeScript)) {
    Write-Error "Missing script: $smokeScript"
    exit 1
}

$needsStart = $false
if (-not (Test-ApiHealthy -Url $BaseUrl)) {
    if ($Mode -eq "existing") {
        Write-Error "API is not healthy and Mode=existing was requested."
        exit 1
    }
    $needsStart = $true
}

if ($Mode -eq "docker") {
    $needsStart = $true
}

if ($needsStart) {
    Write-Output "Starting BrainAPI via start.ps1..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File $startScript
    if ($LASTEXITCODE -ne 0) {
        Write-Error "start.ps1 failed."
        exit 1
    }
}

Write-Output "Waiting for API health..."
if (-not (Wait-ForHealth -Url $BaseUrl -MaxSeconds $HealthTimeoutSeconds)) {
    Write-Error "API did not become healthy at $BaseUrl within $HealthTimeoutSeconds seconds."
    exit 1
}

Write-Output "Running smoke tests..."
& powershell -NoProfile -ExecutionPolicy Bypass -File $smokeScript -BaseUrl $BaseUrl -ReportPath $ReportPath
$smokeExitCode = $LASTEXITCODE

$resolvedReportPath = if ([System.IO.Path]::IsPathRooted($ReportPath)) { $ReportPath } else { Join-Path $projectRoot $ReportPath }
if (Test-Path $resolvedReportPath) {
    try {
        $report = Get-Content $resolvedReportPath -Raw | ConvertFrom-Json
        Write-Output "Verification summary: $($report.passed)/$($report.total) passed, $($report.failed) failed."
        Write-Output "Report: $resolvedReportPath"
    }
    catch {
        Write-Warning "Could not parse report at $resolvedReportPath"
    }
}

exit $smokeExitCode
