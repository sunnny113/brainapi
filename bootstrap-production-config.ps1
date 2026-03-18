param(
    [string]$PublicBaseUrl = "",
    [string]$SmtpHost = "",
    [string]$SmtpPort = "587",
    [string]$SmtpUsername = "",
    [SecureString]$SmtpPassword,
    [string]$SmtpUseTls = "true",
    [string]$EmailFromAddress = "",
    [string]$EmailFromName = "BrainAPI",
    [string]$EmailReplyTo = "",
    [string]$RazorpayKeyId = "",
    [string]$RazorpayKeySecret = "",
    [string]$RazorpayWebhookSecret = "",
    [switch]$UsePlaceholders
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $projectRoot ".env"
$envExamplePath = Join-Path $projectRoot ".env.example"

function ConvertTo-PlainText {
    param([SecureString]$SecureValue)
    if ($null -eq $SecureValue) { return "" }
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

$smtpPasswordPlain = ConvertTo-PlainText -SecureValue $SmtpPassword

if (-not (Test-Path $envPath)) {
    if (Test-Path $envExamplePath) {
        Copy-Item $envExamplePath $envPath
        Write-Output "Created .env from .env.example"
    }
    else {
        Write-Error "Missing .env and .env.example"
        exit 1
    }
}

if ($UsePlaceholders) {
    if (-not $PublicBaseUrl) { $PublicBaseUrl = "https://api.your-domain.com" }
    if (-not $SmtpHost) { $SmtpHost = "smtp.your-provider.com" }
    if (-not $SmtpUsername) { $SmtpUsername = "replace-me" }
    if (-not $smtpPasswordPlain) { $smtpPasswordPlain = "replace-me" }
    if (-not $EmailFromAddress) { $EmailFromAddress = "noreply@your-domain.com" }
    if (-not $EmailReplyTo) { $EmailReplyTo = "support@your-domain.com" }
    if (-not $RazorpayKeyId) { $RazorpayKeyId = "rzp_live_replace_me" }
    if (-not $RazorpayKeySecret) { $RazorpayKeySecret = "replace-me" }
    if (-not $RazorpayWebhookSecret) { $RazorpayWebhookSecret = "replace-me" }
}

$updates = @{
    "PUBLIC_BASE_URL" = $PublicBaseUrl
    "SMTP_HOST" = $SmtpHost
    "SMTP_PORT" = $SmtpPort
    "SMTP_USERNAME" = $SmtpUsername
    "SMTP_PASSWORD" = $smtpPasswordPlain
    "SMTP_USE_TLS" = $SmtpUseTls
    "EMAIL_FROM_ADDRESS" = $EmailFromAddress
    "EMAIL_FROM_NAME" = $EmailFromName
    "EMAIL_REPLY_TO" = $EmailReplyTo
    "RAZORPAY_KEY_ID" = $RazorpayKeyId
    "RAZORPAY_KEY_SECRET" = $RazorpayKeySecret
    "RAZORPAY_WEBHOOK_SECRET" = $RazorpayWebhookSecret
}

$lines = Get-Content $envPath

foreach ($key in $updates.Keys) {
    $value = $updates[$key]
    if ($null -eq $value -or $value -eq "") { continue }

    $pattern = "^\s*$([regex]::Escape($key))\s*="
    $newLine = "$key=$value"

    $matched = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $pattern) {
            $lines[$i] = $newLine
            $matched = $true
            break
        }
    }

    if (-not $matched) {
        $lines += $newLine
    }
}

Set-Content -Path $envPath -Value $lines -Encoding UTF8
Write-Output "Updated .env with provided values."

$missing = @()
foreach ($key in @("PUBLIC_BASE_URL", "SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_FROM_ADDRESS", "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET")) {
    $line = $lines | Where-Object { $_ -match "^\s*$([regex]::Escape($key))\s*=" } | Select-Object -First 1
    if (-not $line) {
        $missing += $key
        continue
    }
    $val = ($line -replace "^\s*$([regex]::Escape($key))\s*=\s*", "").Trim()
    if (-not $val -or $val -match "replace-me|your-domain|rzp_live_replace_me") {
        $missing += $key
    }
}

if ($missing.Count -gt 0) {
    Write-Warning "Still missing or placeholder values: $($missing -join ', ')"
    exit 2
}

Write-Output "Production credential fields look populated."
exit 0
