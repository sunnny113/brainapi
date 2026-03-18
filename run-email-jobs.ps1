param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$AdminApiKey = "",
    [int]$SendLimit = 100
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $projectRoot ".env"

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [string]$EnvPath
    )

    if (-not (Test-Path $EnvPath)) {
        return ""
    }

    $line = Get-Content $EnvPath | Where-Object { $_ -match "^\s*$Key\s*=\s*" } | Select-Object -First 1
    if (-not $line) {
        return ""
    }

    $value = $line -replace "^\s*$Key\s*=\s*", ""
    return $value.Trim().Trim('"').Trim("'")
}

$resolvedAdminKey = $AdminApiKey
if (-not $resolvedAdminKey) {
    $resolvedAdminKey = Get-EnvValue -Key "ADMIN_API_KEY" -EnvPath $envPath
}

if (-not $resolvedAdminKey) {
    Write-Error "Admin API key missing. Pass -AdminApiKey or set ADMIN_API_KEY in .env"
    exit 1
}

$headers = @{ "x-admin-key" = $resolvedAdminKey }

Write-Output "Scheduling trial reminder emails..."
try {
    $scheduleResponse = Invoke-RestMethod -Uri "$BaseUrl/api/v1/admin/emails/schedule-trial-reminders" -Method POST -Headers $headers
    Write-Output ("Schedule result: " + ($scheduleResponse | ConvertTo-Json -Compress))
}
catch {
    Write-Error ("Failed schedule call: " + $_.Exception.Message)
    exit 1
}

Write-Output "Sending pending emails..."
try {
    $sendResponse = Invoke-RestMethod -Uri "$BaseUrl/api/v1/admin/emails/send-pending?limit=$SendLimit" -Method POST -Headers $headers
    Write-Output ("Send result: " + ($sendResponse | ConvertTo-Json -Compress))
}
catch {
    Write-Error ("Failed send call: " + $_.Exception.Message)
    exit 1
}

Write-Output "Email jobs completed successfully."
