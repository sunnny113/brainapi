param(
    [switch]$Elevated
)

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-PendingReboot {
    $paths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
        "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager"
    )

    if (Test-Path $paths[0]) { return $true }
    if (Test-Path $paths[1]) { return $true }

    try {
        $pendingOps = Get-ItemProperty -Path $paths[2] -Name PendingFileRenameOperations -ErrorAction SilentlyContinue
        if ($null -ne $pendingOps) { return $true }
    } catch {
    }

    return $false
}

function Start-ServiceSafe {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [int]$MaxWaitSeconds = 20
    )

    $service = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if ($null -eq $service) {
        Write-Warning "Service not found: $Name"
        return
    }

    if ($service.StartType -eq 'Disabled') {
        Set-Service -Name $Name -StartupType Manual -ErrorAction SilentlyContinue
    }

    Start-Service -Name $Name -ErrorAction SilentlyContinue

    $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
    do {
        $service = Get-Service -Name $Name -ErrorAction SilentlyContinue
        if ($service.Status -eq 'Running') { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)

    Write-Warning "Service did not reach Running state in time: $Name"
}

if (-not (Test-IsAdmin)) {
    Write-Output "Relaunching repair script as Administrator..."
    $scriptPath = $MyInvocation.MyCommand.Path
    Start-Process powershell -Verb RunAs -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$scriptPath`"",
        "-Elevated"
    )
    exit 0
}

Write-Output "Repairing Docker prerequisites..."

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$composeFile = Join-Path $projectRoot "docker-compose.yml"

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Error "winget is not available. Install WSL manually from Microsoft Store."
    exit 1
}

Write-Output "Ensuring required Windows features are enabled..."
$requiredFeatures = @(
    "Microsoft-Windows-Subsystem-Linux",
    "VirtualMachinePlatform",
    "Microsoft-Hyper-V-All"
)

$needsReboot = $false
foreach ($feature in $requiredFeatures) {
    $featureInfo = dism /online /Get-FeatureInfo /FeatureName:$feature
    if ($featureInfo -match "State : Disabled") {
        Write-Output "Enabling feature: $feature"
        dism /online /Enable-Feature /FeatureName:$feature /All /NoRestart
        if (($LASTEXITCODE -ne 0) -and ($LASTEXITCODE -ne 3010)) {
            Write-Warning "Failed to enable $feature automatically."
        } else {
            $needsReboot = $true
        }
    }
}

if (Test-PendingReboot) {
    $needsReboot = $true
}

if ($needsReboot) {
    Write-Warning "System reboot is required to finalize Windows feature changes. Reboot now, then rerun .\repair-docker.ps1"
    exit 1
}

Write-Output "Ensuring hypervisor launches at boot..."
bcdedit /set hypervisorlaunchtype auto
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Could not set hypervisorlaunchtype automatically."
}

winget install --id Microsoft.WSL --accept-package-agreements --accept-source-agreements --silent
if ($LASTEXITCODE -ne 0) {
    Write-Warning "WSL package install returned non-zero (possibly already installed). Continuing."
}

wsl --update
if ($LASTEXITCODE -ne 0) {
    Write-Warning "wsl --update failed. You may need to complete installer prompts or reboot."
}

wsl --install -d Ubuntu --no-launch
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Ubuntu install may already exist or require first-time setup. Continuing."
}

wsl --set-default-version 2

Write-Output "Resetting WSL and Docker processes..."
wsl --shutdown
Start-ServiceSafe -Name hns
Start-ServiceSafe -Name vmcompute
Start-ServiceSafe -Name LxssManager
Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name "com.docker.backend" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name "com.docker.proxy" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

$dockerDesktopPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
if (Test-Path $dockerDesktopPath) {
    Start-Process $dockerDesktopPath
} else {
    Write-Warning "Docker Desktop executable not found at expected path."
}

$maxAttempts = 24
for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    Start-Sleep -Seconds 5
    Start-Service com.docker.service -ErrorAction SilentlyContinue
    docker info *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Output "Docker engine is ready."
        if (-not (Test-Path $composeFile)) {
            Write-Error "Compose file not found: $composeFile"
            exit 1
        }
        docker compose -f $composeFile up -d --build
        if ($LASTEXITCODE -eq 0) {
            Write-Output "BrainAPI docker stack is running. Docs: http://localhost:8000/docs"
            exit 0
        }
        Write-Error "Docker engine is ready, but compose up failed."
        exit 1
    }
    Write-Output "Waiting for Docker engine... ($attempt/$maxAttempts)"
}

Write-Error "Docker engine did not become ready. Reboot Windows, open Docker Desktop once, then rerun .\repair-docker.ps1"
exit 1
