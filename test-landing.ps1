# Test BrainAPI Landing Page and Endpoints

$baseUrl = "http://localhost:8000"

Write-Host "=================================" -ForegroundColor Cyan
Write-Host "Testing BrainAPI Landing Page & API" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan

# Test 1: Landing Page
Write-Host "`n[1] Testing Landing Page (GET /)" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$baseUrl/" -UseBasicParsing -ErrorAction Stop
    Write-Host "✓ Status: $($response.StatusCode)" -ForegroundColor Green
    Write-Host "✓ Content-Type: $($response.Headers['Content-Type'])" -ForegroundColor Green
    $htmlLength = $response.Content.Length
    Write-Host "✓ HTML Size: $htmlLength bytes" -ForegroundColor Green
    if ($response.Content -match "BrainAPI") {
        Write-Host "✓ Page title found" -ForegroundColor Green
    }
} catch {
    Write-Host "✗ Error: $_" -ForegroundColor Red
}

# Test 2: Health Check
Write-Host "`n[2] Testing Health Check (GET /health)" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$baseUrl/health" -UseBasicParsing -ErrorAction Stop
    Write-Host "✓ Status: $($response.StatusCode)" -ForegroundColor Green
    $data = $response.Content | ConvertFrom-Json
    Write-Host "✓ Response: $($data | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "✗ Error: $_" -ForegroundColor Red
}

# Test 3: API Docs
Write-Host "`n[3] Testing API Docs (GET /docs)" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$baseUrl/docs" -UseBasicParsing -ErrorAction Stop
    Write-Host "✓ Status: $($response.StatusCode)" -ForegroundColor Green
    Write-Host "✓ Content-Type: $($response.Headers['Content-Type'])" -ForegroundColor Green
} catch {
    Write-Host "✗ Error: $_" -ForegroundColor Red
}

# Test 4: Text Generation WITHOUT API Key (should fail)
Write-Host "`n[4] Testing Text Generation WITHOUT API Key (should fail)" -ForegroundColor Yellow
try {
    $body = @{
        prompt = "Hello world"
        temperature = 0.7
        max_output_tokens = 100
    } | ConvertTo-Json
    
    $response = Invoke-WebRequest -Uri "$baseUrl/api/v1/text/generate" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -UseBasicParsing `
        -ErrorAction Stop
    Write-Host "✗ Should have failed but got 200!" -ForegroundColor Red
} catch {
    if ($_.Exception.Response.StatusCode -eq 401) {
        Write-Host "✓ Correctly returned 401 Unauthorized" -ForegroundColor Green
        $errorContent = $_.Exception.Response.Content.ReadAsStream()
        $reader = New-Object System.IO.StreamReader($errorContent)
        $body = $reader.ReadToEnd()
        $reader.Close()
        Write-Host "✓ Error message: $(($body | ConvertFrom-Json).detail)" -ForegroundColor Green
    } else {
        Write-Host "✗ Unexpected error: $_" -ForegroundColor Red
    }
}

# Test 5: Public Plans Endpoint (should work without API key)
Write-Host "`n[5] Testing Public Plans (GET /api/v1/public/plans)" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$baseUrl/api/v1/public/plans" -UseBasicParsing -ErrorAction Stop
    Write-Host "✓ Status: $($response.StatusCode)" -ForegroundColor Green
    $data = $response.Content | ConvertFrom-Json
    Write-Host "✓ Plans found: $($data.plans.Count) plans" -ForegroundColor Green
} catch {
    Write-Host "✗ Error: $_" -ForegroundColor Red
}

Write-Host "`n=================================" -ForegroundColor Cyan
Write-Host "Test Complete!" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan
Write-Host "`nTo access the landing page: http://localhost:8000" -ForegroundColor Magenta
Write-Host "To access API docs: http://localhost:8000/docs" -ForegroundColor Magenta
