param(
    [string]$LocalUrl = "http://localhost:8000"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    $candidatePaths = @(
        "C:\Program Files\cloudflared\cloudflared.exe",
        "C:\Program Files (x86)\cloudflared\cloudflared.exe"
    )

    foreach ($candidate in $candidatePaths) {
        if (Test-Path $candidate) {
            $cloudflared = @{ Path = $candidate }
            break
        }
    }
}

if (-not $cloudflared) {
    Write-Error "cloudflared is not installed. Install from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    exit 1
}

Write-Output "Starting Cloudflare Quick Tunnel for $LocalUrl"
Write-Output "Keep this terminal open. Copy the https://*.trycloudflare.com URL from output."
& $cloudflared.Path tunnel --url $LocalUrl
