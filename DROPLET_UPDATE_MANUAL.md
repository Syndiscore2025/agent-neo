# Agent NEO v2.1 - Manual Droplet Update (PowerShell Commands)

## Prerequisites

- PowerShell 5.1+ or PowerShell Core 7+
- SSH client installed (Windows 10+ has OpenSSH built-in)
- SSH access to your DigitalOcean droplet

---

## Option 1: Automated Script (Recommended)

### Basic Update (No GitHub Auto-Discovery)

```powershell
# Run the automated script
.\DROPLET_UPDATE_v2.1.ps1 -DropletIP "your.droplet.ip.address"

# Example:
.\DROPLET_UPDATE_v2.1.ps1 -DropletIP "159.89.123.45"
```

### Full Update (With GitHub Auto-Discovery)

```powershell
# Run with GitHub configuration
.\DROPLET_UPDATE_v2.1.ps1 `
    -DropletIP "your.droplet.ip.address" `
    -IncludeGitHub `
    -GitHubToken "ghp_your_token_here" `
    -GitHubOwner "your-github-username"

# Example:
.\DROPLET_UPDATE_v2.1.ps1 `
    -DropletIP "159.89.123.45" `
    -IncludeGitHub `
    -GitHubToken "ghp_xxxxxxxxxxxxxxxxxxxx" `
    -GitHubOwner "rakin"
```

### Custom SSH User

```powershell
# If using a different SSH user
.\DROPLET_UPDATE_v2.1.ps1 `
    -DropletIP "159.89.123.45" `
    -SSHUser "root"
```

---

## Option 2: Manual Commands (Step-by-Step)

### Step 1: Pull Latest Code

```powershell
# SSH into droplet and pull code
ssh agentneo@your.droplet.ip.address "cd ~/agent-neo && git pull origin main"

# Example:
ssh agentneo@159.89.123.45 "cd ~/agent-neo && git pull origin main"
```

### Step 2: Install Dependencies

```powershell
# Install new httpx dependency
ssh agentneo@your.droplet.ip.address "cd ~/agent-neo && source venv/bin/activate && pip install -r requirements.txt"
```

### Step 3: Restart Service

```powershell
# Restart Agent NEO service
ssh agentneo@your.droplet.ip.address "sudo systemctl restart agent-neo"
```

### Step 4: Verify Version

```powershell
# Check version (should be 2.1.0)
ssh agentneo@your.droplet.ip.address "curl -s http://localhost:8000/ | jq -r '.version'"
```

### Step 5: Check Service Status

```powershell
# Verify service is running
ssh agentneo@your.droplet.ip.address "sudo systemctl status agent-neo"
```

---

## Option 3: Interactive SSH Session

```powershell
# Connect to droplet
ssh agentneo@your.droplet.ip.address

# Once connected, run these commands:
```

```bash
# Pull latest code
cd ~/agent-neo
git pull origin main

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Restart service
sudo systemctl restart agent-neo

# Check status
sudo systemctl status agent-neo

# Verify version
curl http://localhost:8000/ | jq '.version'

# Exit SSH session
exit
```

---

## Optional: Add GitHub Auto-Discovery

### Step 1: Create Cache Directory

```powershell
ssh agentneo@your.droplet.ip.address "sudo mkdir -p /opt/agent-neo/calibration && sudo chown agentneo:agentneo /opt/agent-neo/calibration"
```

### Step 2: Edit .env File

```powershell
# Open .env file for editing
ssh agentneo@your.droplet.ip.address "nano ~/agent-neo/.env"
```

Then add these lines at the end:

```bash
# ============================================
# GitHub Auto-Discovery Calibration (v2.1)
# ============================================
GITHUB_TOKEN=ghp_your_actual_token_here
GITHUB_OWNER=your-github-username
GITHUB_TYPE=personal
CALIBRATION_CACHE_DIR=/opt/agent-neo/calibration
CALIBRATION_EXCLUDE_TOPICS=prototype,experimental,sandbox,archive
CALIBRATION_MAX_REPOS=50
```

Save and exit (Ctrl+X, Y, Enter)

### Step 3: Restart Service

```powershell
ssh agentneo@your.droplet.ip.address "sudo systemctl restart agent-neo"
```

---

## Verification Commands

### Check Version

```powershell
ssh agentneo@your.droplet.ip.address "curl -s http://localhost:8000/ | jq"
```

Expected output:
```json
{
  "agent": "AGENT NEO",
  "version": "2.1.0",
  "status": "Working",
  "endpoints": {
    "health": "/health",
    "health_live": "/health/live",
    "health_ready": "/health/ready",
    "plan": "/plan",
    "execute": "/execute",
    "calibrate_status": "/calibrate/status",
    "calibrate_discover": "/calibrate/discover",
    "calibrate": "/calibrate",
    "calibrate_apply": "/calibrate/apply"
  }
}
```

### Check Service Logs

```powershell
# View last 50 lines
ssh agentneo@your.droplet.ip.address "sudo journalctl -u agent-neo -n 50"

# Follow logs in real-time
ssh agentneo@your.droplet.ip.address "sudo journalctl -u agent-neo -f"
```

### Test New Endpoints (If GitHub Configured)

```powershell
# Set your token
$token = "your-agent-neo-bearer-token"

# Test calibration status
ssh agentneo@your.droplet.ip.address "curl -s -H 'Authorization: Bearer $token' http://localhost:8000/calibrate/status | jq"

# Test repository discovery
ssh agentneo@your.droplet.ip.address "curl -s -X POST -H 'Authorization: Bearer $token' http://localhost:8000/calibrate/discover | jq"
```

---

## Troubleshooting

### Service Won't Start

```powershell
# Check detailed logs
ssh agentneo@your.droplet.ip.address "sudo journalctl -u agent-neo -n 100 --no-pager"

# Check if port is in use
ssh agentneo@your.droplet.ip.address "sudo netstat -tulpn | grep 8000"
```

### Version Still Shows 2.0.0

```powershell
# Force restart
ssh agentneo@your.droplet.ip.address "sudo systemctl stop agent-neo && sleep 2 && sudo systemctl start agent-neo"

# Check if code was actually pulled
ssh agentneo@your.droplet.ip.address "cd ~/agent-neo && git log -1 --oneline"
```

### Dependencies Not Installing

```powershell
# Check Python version
ssh agentneo@your.droplet.ip.address "python3 --version"

# Manually install httpx
ssh agentneo@your.droplet.ip.address "cd ~/agent-neo && source venv/bin/activate && pip install httpx>=0.28.0"
```

---

## Quick Reference

| Task | Command |
|------|---------|
| **Connect to droplet** | `ssh agentneo@your.droplet.ip` |
| **View logs** | `ssh agentneo@ip "sudo journalctl -u agent-neo -f"` |
| **Restart service** | `ssh agentneo@ip "sudo systemctl restart agent-neo"` |
| **Check status** | `ssh agentneo@ip "sudo systemctl status agent-neo"` |
| **Check version** | `ssh agentneo@ip "curl -s localhost:8000 \| jq .version"` |
| **Pull latest code** | `ssh agentneo@ip "cd ~/agent-neo && git pull"` |

---

## Complete One-Liner (Basic Update)

```powershell
ssh agentneo@your.droplet.ip.address "cd ~/agent-neo && git pull origin main && source venv/bin/activate && pip install -r requirements.txt && sudo systemctl restart agent-neo && sleep 3 && curl -s http://localhost:8000/ | jq '.version'"
```

Expected output: `"2.1.0"`

---

## Notes

- Replace `your.droplet.ip.address` with your actual droplet IP
- Replace `agentneo` with your SSH user if different
- The automated script (`DROPLET_UPDATE_v2.1.ps1`) handles all steps automatically
- GitHub Auto-Discovery is completely optional
- All existing functionality remains unchanged


