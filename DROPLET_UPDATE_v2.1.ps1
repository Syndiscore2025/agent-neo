# Agent NEO v2.1 - DigitalOcean Droplet Update Script (PowerShell)
# Run this from your local Windows machine to update the remote droplet

param(
    [Parameter(Mandatory=$true)]
    [string]$DropletIP,
    
    [Parameter(Mandatory=$false)]
    [string]$SSHUser = "agentneo",
    
    [Parameter(Mandatory=$false)]
    [switch]$IncludeGitHub,
    
    [Parameter(Mandatory=$false)]
    [string]$GitHubToken,
    
    [Parameter(Mandatory=$false)]
    [string]$GitHubOwner
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Agent NEO v2.1 Droplet Update Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# SSH connection string
$sshConnection = "$SSHUser@$DropletIP"

Write-Host "[1/5] Pulling latest code from GitHub..." -ForegroundColor Yellow
ssh $sshConnection "cd ~/agent-neo && git pull origin main"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to pull code" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Code updated" -ForegroundColor Green
Write-Host ""

Write-Host "[2/5] Installing new dependencies..." -ForegroundColor Yellow
ssh $sshConnection "cd ~/agent-neo && source venv/bin/activate && pip install -r requirements.txt"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to install dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Dependencies installed" -ForegroundColor Green
Write-Host ""

# Optional: Configure GitHub Auto-Discovery
if ($IncludeGitHub) {
    Write-Host "[3/5] Configuring GitHub Auto-Discovery..." -ForegroundColor Yellow
    
    if (-not $GitHubToken -or -not $GitHubOwner) {
        Write-Host "❌ GitHub configuration requires -GitHubToken and -GitHubOwner parameters" -ForegroundColor Red
        exit 1
    }
    
    # Create calibration cache directory
    ssh $sshConnection "sudo mkdir -p /opt/agent-neo/calibration && sudo chown $SSHUser`:$SSHUser /opt/agent-neo/calibration"
    
    # Append GitHub config to .env
    $envConfig = @"

# ============================================
# GitHub Auto-Discovery Calibration (v2.1)
# ============================================
GITHUB_TOKEN=$GitHubToken
GITHUB_OWNER=$GitHubOwner
GITHUB_TYPE=personal
CALIBRATION_CACHE_DIR=/opt/agent-neo/calibration
CALIBRATION_EXCLUDE_TOPICS=prototype,experimental,sandbox,archive
CALIBRATION_MAX_REPOS=50
"@
    
    # Check if GitHub config already exists
    $checkConfig = ssh $sshConnection "grep -q 'GITHUB_TOKEN' ~/agent-neo/.env && echo 'exists' || echo 'missing'"
    
    if ($checkConfig -match "missing") {
        # Append config
        ssh $sshConnection "echo '$envConfig' >> ~/agent-neo/.env"
        Write-Host "✅ GitHub configuration added" -ForegroundColor Green
    } else {
        Write-Host "⚠️  GitHub configuration already exists in .env, skipping" -ForegroundColor Yellow
    }
} else {
    Write-Host "[3/5] Skipping GitHub Auto-Discovery configuration (use -IncludeGitHub to enable)" -ForegroundColor Gray
}
Write-Host ""

Write-Host "[4/5] Restarting Agent NEO service..." -ForegroundColor Yellow
ssh $sshConnection "sudo systemctl restart agent-neo"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to restart service" -ForegroundColor Red
    exit 1
}

# Wait for service to start
Start-Sleep -Seconds 3

# Check service status
$serviceStatus = ssh $sshConnection "sudo systemctl is-active agent-neo"

if ($serviceStatus -match "active") {
    Write-Host "✅ Service restarted successfully" -ForegroundColor Green
} else {
    Write-Host "❌ Service failed to start" -ForegroundColor Red
    Write-Host "Check logs with: ssh $sshConnection 'sudo journalctl -u agent-neo -n 50'" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

Write-Host "[5/5] Verifying deployment..." -ForegroundColor Yellow

# Get version
$version = ssh $sshConnection "curl -s http://localhost:8000/ | jq -r '.version'"

if ($version -eq "2.1.0") {
    Write-Host "✅ Version verified: $version" -ForegroundColor Green
} else {
    Write-Host "⚠️  Unexpected version: $version (expected 2.1.0)" -ForegroundColor Yellow
}

# Check endpoints
$endpoints = ssh $sshConnection "curl -s http://localhost:8000/ | jq -r '.endpoints | keys[]'"

if ($endpoints -match "calibrate_status" -and $endpoints -match "calibrate_discover") {
    Write-Host "✅ New endpoints available" -ForegroundColor Green
} else {
    Write-Host "⚠️  New endpoints not found" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ Update Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  • View logs: ssh $sshConnection 'sudo journalctl -u agent-neo -f'" -ForegroundColor Gray
Write-Host "  • Check status: ssh $sshConnection 'sudo systemctl status agent-neo'" -ForegroundColor Gray

if ($IncludeGitHub) {
    Write-Host "  • Test discovery: curl -X POST -H 'Authorization: Bearer YOUR_TOKEN' https://your-domain.com/calibrate/discover" -ForegroundColor Gray
}

Write-Host ""

