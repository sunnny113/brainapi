param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$UserApiKey = "",
    [string]$AdminApiKey = "",
    [string]$ReportPath = "./smoke-test-report.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

function Add-TestResult {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Detail
    )

    $script:Results += [PSCustomObject]@{
        Name = $Name
        Passed = $Passed
        Detail = $Detail
    }

    if ($Passed) {
        Write-Host "[PASS] $Name - $Detail"
    }
    else {
        Write-Host "[FAIL] $Name - $Detail"
    }
}

function Invoke-Test {
    param(
        [string]$Name,
        [ScriptBlock]$Action,
        [int[]]$ExpectedStatusCodes = @(200)
    )

    try {
        $response = & $Action
        $statusCode = [int]$response.StatusCode
        if ($ExpectedStatusCodes -contains $statusCode) {
            Add-TestResult -Name $Name -Passed $true -Detail "HTTP $statusCode"
        }
        else {
            Add-TestResult -Name $Name -Passed $false -Detail "HTTP $statusCode (expected: $($ExpectedStatusCodes -join ', '))"
        }
        return $response
    }
    catch {
        $status = $null
        $responseObj = $null

        if ($_.Exception -and ($_.Exception.PSObject.Properties.Name -contains "Response")) {
            $responseObj = $_.Exception.Response
        }

        if ($null -ne $responseObj) {
            if ($responseObj.PSObject.Properties.Name -contains "StatusCode") {
                $status = [int]$responseObj.StatusCode
            }
            elseif ($responseObj -is [System.Net.Http.HttpResponseMessage]) {
                $status = [int]$responseObj.StatusCode
            }
        }

        if ($status -and ($ExpectedStatusCodes -contains [int]$status)) {
            Add-TestResult -Name $Name -Passed $true -Detail "HTTP $status"
        }
        else {
            Add-TestResult -Name $Name -Passed $false -Detail $_.Exception.Message
        }
        return $null
    }
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $projectRoot ".env"
$Results = @()

if ([System.IO.Path]::IsPathRooted($ReportPath)) {
    $resolvedReportPath = $ReportPath
}
else {
    $resolvedReportPath = Join-Path $projectRoot $ReportPath
}

$resolvedUserApiKey = $UserApiKey
if (-not $resolvedUserApiKey) {
    $apiKeysRaw = Get-EnvValue -Key "API_KEYS" -EnvPath $envPath
    if ($apiKeysRaw) {
        $resolvedUserApiKey = ($apiKeysRaw -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ } | Select-Object -First 1)
    }
}

$resolvedAdminApiKey = $AdminApiKey
if (-not $resolvedAdminApiKey) {
    $resolvedAdminApiKey = Get-EnvValue -Key "ADMIN_API_KEY" -EnvPath $envPath
}

if (-not $resolvedUserApiKey) {
    Write-Error "User API key missing. Pass -UserApiKey or set API_KEYS in .env"
    exit 1
}

if (-not $resolvedAdminApiKey) {
    Write-Error "Admin API key missing. Pass -AdminApiKey or set ADMIN_API_KEY in .env"
    exit 1
}

$provider = "unknown"
$healthResponse = Invoke-Test -Name "GET /health" -Action {
    Invoke-WebRequest -Uri "$BaseUrl/health" -Method GET
}

if ($null -eq $healthResponse) {
    Write-Error "API is not reachable. Start the service with ./start.ps1 or ./start-local.ps1 and retry."
    exit 1
}

try {
    $healthJson = $healthResponse.Content | ConvertFrom-Json
    if ($healthJson.provider) {
        $provider = [string]$healthJson.provider
    }
}
catch {
}

$userHeaders = @{
    "X-API-Key" = $resolvedUserApiKey
}

$adminHeaders = @{
    "X-Admin-Key" = $resolvedAdminApiKey
}

$textPayload = @{
    prompt = "smoke test prompt"
    temperature = 0.2
    max_output_tokens = 30
} | ConvertTo-Json

Invoke-Test -Name "POST /api/v1/text/generate" -Action {
    Invoke-WebRequest -Uri "$BaseUrl/api/v1/text/generate" -Method POST -Headers $userHeaders -ContentType "application/json" -Body $textPayload
}

$imagePayload = @{
    prompt = "smoke test image"
    size = "1024x1024"
} | ConvertTo-Json

Invoke-Test -Name "POST /api/v1/image/generate" -Action {
    Invoke-WebRequest -Uri "$BaseUrl/api/v1/image/generate" -Method POST -Headers $userHeaders -ContentType "application/json" -Body $imagePayload
}

$audioTempPath = [System.IO.Path]::Combine($env:TEMP, "brainapi-smoke-test.wav")
$wavBytes = [byte[]](
    0x52,0x49,0x46,0x46,0x24,0x00,0x00,0x00,0x57,0x41,0x56,0x45,
    0x66,0x6D,0x74,0x20,0x10,0x00,0x00,0x00,0x01,0x00,0x01,0x00,
    0x40,0x1F,0x00,0x00,0x80,0x3E,0x00,0x00,0x02,0x00,0x10,0x00,
    0x64,0x61,0x74,0x61,0x00,0x00,0x00,0x00
)
[System.IO.File]::WriteAllBytes($audioTempPath, $wavBytes)

$curlPath = (Get-Command curl.exe -ErrorAction SilentlyContinue).Path
if (-not $curlPath) {
    Add-TestResult -Name "POST /api/v1/speech/transcribe" -Passed $false -Detail "curl.exe not found (required for multipart upload in Windows PowerShell 5.1)"
}
else {
    try {
        $curlArgs = @(
            "-sS",
            "-o", "NUL",
            "-w", "%{http_code}",
            "-H", "X-API-Key: $resolvedUserApiKey",
            "-F", "file=@$audioTempPath;type=audio/wav",
            "$BaseUrl/api/v1/speech/transcribe"
        )
        $speechStatusText = (& $curlPath @curlArgs).Trim()
        $speechStatus = [int]$speechStatusText
        if ($speechStatus -eq 200) {
            Add-TestResult -Name "POST /api/v1/speech/transcribe" -Passed $true -Detail "HTTP $speechStatus"
        }
        else {
            Add-TestResult -Name "POST /api/v1/speech/transcribe" -Passed $false -Detail "HTTP $speechStatus"
        }
    }
    catch {
        Add-TestResult -Name "POST /api/v1/speech/transcribe" -Passed $false -Detail $_.Exception.Message
    }
}

$automationPayload = @{
    name = "smoke-test-automation"
    steps = @(
        @{
            type = "webhook"
            url = "https://httpbin.org/post"
            method = "POST"
            headers = @{ "Content-Type" = "application/json" }
            body = @{ test = "ok" }
        },
        @{
            type = "delay"
            seconds = 0.1
        }
    )
} | ConvertTo-Json -Depth 8

Invoke-Test -Name "POST /api/v1/automation/run" -Action {
    Invoke-WebRequest -Uri "$BaseUrl/api/v1/automation/run" -Method POST -Headers $userHeaders -ContentType "application/json" -Body $automationPayload
}

$createdKeyId = ""
$createPayload = @{
    name = "smoke-test-key"
    rate_limit_per_minute = 10
} | ConvertTo-Json

$createResponse = Invoke-Test -Name "POST /api/v1/admin/api-keys" -Action {
    Invoke-WebRequest -Uri "$BaseUrl/api/v1/admin/api-keys" -Method POST -Headers $adminHeaders -ContentType "application/json" -Body $createPayload
}

if ($createResponse -and $createResponse.Content) {
    try {
        $createJson = $createResponse.Content | ConvertFrom-Json
        if ($createJson.id) {
            $createdKeyId = [string]$createJson.id
        }
    }
    catch {
    }
}

Invoke-Test -Name "GET /api/v1/admin/api-keys" -Action {
    Invoke-WebRequest -Uri "$BaseUrl/api/v1/admin/api-keys" -Method GET -Headers $adminHeaders
}

if ($createdKeyId) {
    Invoke-Test -Name "DELETE /api/v1/admin/api-keys/{key_id}" -Action {
        Invoke-WebRequest -Uri "$BaseUrl/api/v1/admin/api-keys/$createdKeyId" -Method DELETE -Headers $adminHeaders
    }
}
else {
    Add-TestResult -Name "DELETE /api/v1/admin/api-keys/{key_id}" -Passed $false -Detail "Skipped because key creation failed"
}

Invoke-Test -Name "GET /api/v1/admin/usage" -Action {
    Invoke-WebRequest -Uri "$BaseUrl/api/v1/admin/usage?hours=1" -Method GET -Headers $adminHeaders
}

if (Test-Path $audioTempPath) {
    Remove-Item $audioTempPath -Force -ErrorAction SilentlyContinue
}

$total = $Results.Count
$passed = ($Results | Where-Object { $_.Passed }).Count
$failed = $total - $passed

$report = [PSCustomObject]@{
    base_url = $BaseUrl
    provider = $provider
    total = $total
    passed = $passed
    failed = $failed
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    results = $Results
}

$report | ConvertTo-Json -Depth 8 | Set-Content -Path $resolvedReportPath -Encoding UTF8
Write-Output "Report written: $resolvedReportPath"

Write-Output ""
Write-Output "Smoke test summary: $passed/$total passed, $failed failed. Provider=$provider"

if ($failed -gt 0) {
    exit 1
}

exit 0
