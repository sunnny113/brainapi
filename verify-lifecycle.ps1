param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$AdminApiKey = "",
    [int]$SendLimit = 100,
    [switch]$SkipRun
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

function Add-Check {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Detail
    )

    $script:Checks += [PSCustomObject]@{
        Name = $Name
        Passed = $Passed
        Detail = $Detail
    }

    if ($Passed) {
        Write-Output "[PASS] $Name - $Detail"
    }
    else {
        Write-Output "[FAIL] $Name - $Detail"
    }
}

function Invoke-Api {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [ValidateSet("GET", "POST")]
        [string]$Method = "GET",
        [hashtable]$Headers
    )

    try {
        $res = Invoke-WebRequest -Uri $Uri -Method $Method -Headers $Headers -TimeoutSec 15
        return [PSCustomObject]@{
            Ok = $true
            StatusCode = [int]$res.StatusCode
            Body = $res.Content
            Error = ""
        }
    }
    catch {
        $statusCode = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode.value__
        }
        return [PSCustomObject]@{
            Ok = $false
            StatusCode = $statusCode
            Body = ""
            Error = $_.Exception.Message
        }
    }
}

$Checks = @()

$resolvedAdminKey = $AdminApiKey
if (-not $resolvedAdminKey) {
    $resolvedAdminKey = Get-EnvValue -Key "ADMIN_API_KEY" -EnvPath $envPath
}

# Health check
$health = Invoke-Api -Uri "$BaseUrl/health" -Method GET
if ($health.Ok -and $health.StatusCode -eq 200) {
    Add-Check -Name "API health" -Passed $true -Detail "HTTP 200"
}
else {
    Add-Check -Name "API health" -Passed $false -Detail ($health.Error -or ("HTTP " + $health.StatusCode))
}

# Admin key presence
if ($resolvedAdminKey) {
    Add-Check -Name "Admin key present" -Passed $true -Detail "Loaded from argument or .env"
}
else {
    Add-Check -Name "Admin key present" -Passed $false -Detail "Missing AdminApiKey and ADMIN_API_KEY"
}

# SMTP configuration presence (only config presence, not external SMTP connectivity)
$smtpHost = Get-EnvValue -Key "SMTP_HOST" -EnvPath $envPath
$emailFrom = Get-EnvValue -Key "EMAIL_FROM_ADDRESS" -EnvPath $envPath
if ($smtpHost -and $emailFrom) {
    Add-Check -Name "SMTP config" -Passed $true -Detail "SMTP_HOST and EMAIL_FROM_ADDRESS are set"
}
else {
    Add-Check -Name "SMTP config" -Passed $false -Detail "Set SMTP_HOST and EMAIL_FROM_ADDRESS in .env"
}

# Auth and endpoint checks
if ($resolvedAdminKey) {
    $headers = @{ "x-admin-key" = $resolvedAdminKey }

    $scheduleProbe = Invoke-Api -Uri "$BaseUrl/api/v1/admin/emails/schedule-trial-reminders" -Method POST -Headers $headers
    if ($scheduleProbe.Ok -and $scheduleProbe.StatusCode -eq 200) {
        Add-Check -Name "Admin email endpoint auth" -Passed $true -Detail "schedule-trial-reminders returned HTTP 200"
    }
    else {
        $detail = if ($scheduleProbe.StatusCode) { "HTTP $($scheduleProbe.StatusCode)" } else { $scheduleProbe.Error }
        Add-Check -Name "Admin email endpoint auth" -Passed $false -Detail $detail
    }

    if (-not $SkipRun) {
        $scheduleRun = Invoke-Api -Uri "$BaseUrl/api/v1/admin/emails/schedule-trial-reminders" -Method POST -Headers $headers
        $sendRun = Invoke-Api -Uri "$BaseUrl/api/v1/admin/emails/send-pending?limit=$SendLimit" -Method POST -Headers $headers

        $runOk = ($scheduleRun.Ok -and $scheduleRun.StatusCode -eq 200 -and $sendRun.Ok -and $sendRun.StatusCode -eq 200)
        if ($runOk) {
            Add-Check -Name "Lifecycle jobs run" -Passed $true -Detail "schedule + send both returned HTTP 200"
            Write-Output "Schedule response: $($scheduleRun.Body)"
            Write-Output "Send response: $($sendRun.Body)"
        }
        else {
            $s1 = if ($scheduleRun.StatusCode) { "schedule=$($scheduleRun.StatusCode)" } else { "schedule=ERR" }
            $s2 = if ($sendRun.StatusCode) { "send=$($sendRun.StatusCode)" } else { "send=ERR" }
            Add-Check -Name "Lifecycle jobs run" -Passed $false -Detail "$s1, $s2"
        }
    }
    else {
        Add-Check -Name "Lifecycle jobs run" -Passed $true -Detail "Skipped by -SkipRun"
    }
}
else {
    Add-Check -Name "Admin email endpoint auth" -Passed $false -Detail "Cannot test without admin key"
    Add-Check -Name "Lifecycle jobs run" -Passed $false -Detail "Cannot run without admin key"
}

$total = $Checks.Count
$passed = ($Checks | Where-Object { $_.Passed }).Count
$failed = $total - $passed

Write-Output ""
Write-Output "Lifecycle verification summary: $passed/$total passed, $failed failed"

if ($failed -gt 0) {
    exit 1
}

exit 0
