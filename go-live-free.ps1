param(
    [string]$PublicBaseUrl = "",
    [switch]$StartStack,
    [switch]$UsePlaceholderSmtp
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if (-not (Test-Path ".\bootstrap-production-config.ps1")) {
    Write-Error "bootstrap-production-config.ps1 not found"
    exit 1
}

if ($UsePlaceholderSmtp) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap-production-config.ps1 -UsePlaceholders
    if (($LASTEXITCODE -ne 0) -and ($LASTEXITCODE -ne 2)) {
        Write-Error "Failed to apply placeholder production config"
        exit 1
    }
}

if ($PublicBaseUrl) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap-production-config.ps1 -PublicBaseUrl $PublicBaseUrl
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Could not fully validate credential fields yet. PUBLIC_BASE_URL update may still be applied."
    }
}

if ($StartStack) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "start.ps1 failed"
        exit 1
    }
}

Write-Output "Free-live preparation complete."
Write-Output "Next steps:"
Write-Output "1) Run .\start-public-tunnel.ps1 and copy the trycloudflare URL"
Write-Output "2) Re-run: .\go-live-free.ps1 -PublicBaseUrl <your_trycloudflare_url>"
Write-Output "3) Run: .\verify.ps1 and .\verify-lifecycle.ps1 -SkipRun"
Write-Output "4) Share that URL, then add Razorpay live keys when ready"
