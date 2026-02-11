# Agent Neo — DigitalOcean Deployment Guide

## Prerequisites

- DigitalOcean account
- Domain name (optional, for HTTPS)
- SSH key configured

## 1. Create Droplet

```bash
# Recommended specs
- Ubuntu 22.04 LTS
- 2GB RAM / 1 vCPU (minimum)
- 50GB SSD
```

## 2. Initial Server Setup

```bash
# SSH into droplet
ssh root@your-droplet-ip

# Update system
apt update && apt upgrade -y

# Install dependencies
apt install -y python3.11 python3.11-venv python3-pip git nginx certbot python3-certbot-nginx

# Create app user
useradd -m -s /bin/bash agentneo
usermod -aG sudo agentneo
```

## 3. Clone & Configure Application

```bash
# Switch to app user
su - agentneo

# Clone repository
git clone https://github.com/your-repo/agent-neo.git
cd agent-neo

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## 4. Environment Configuration

```bash
# Create .env file
cat > .env << 'EOF'
# Required
AGENT_NEO_TOKEN=your-secure-bearer-token
REPO_PATH=/home/agentneo/target-repo

# Optional - Diff Limits (defaults shown)
RAPID_MAX_FILES=20
RAPID_MAX_LINES=2000
CRITICAL_MAX_FILES=50
CRITICAL_MAX_LINES=5000
MAX_DIFF_SIZE_BYTES=51200

# Optional - Behavior
REQUIRE_REMOTE=true
SKIP_PUSH=false
EOF

chmod 600 .env
```

## 5. Setup Target Repository

```bash
# Clone the repository Agent Neo will manage
cd /home/agentneo
git clone https://github.com/your-org/target-repo.git
cd target-repo
git config user.email "agentneo@yourdomain.com"
git config user.name "Agent Neo"
```

## 6. Install Systemd Service

```bash
# Copy service file
sudo cp /home/agentneo/agent-neo/deploy/agent-neo.service /etc/systemd/system/

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable agent-neo
sudo systemctl start agent-neo

# Check status
sudo systemctl status agent-neo
```

## 7. Configure Nginx

```bash
# Copy nginx config
sudo cp /home/agentneo/agent-neo/deploy/nginx.conf /etc/nginx/sites-available/agent-neo
sudo ln -s /etc/nginx/sites-available/agent-neo /etc/nginx/sites-enabled/

# Edit domain name
sudo nano /etc/nginx/sites-available/agent-neo

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

## 8. Setup SSL (HTTPS)

```bash
# Get SSL certificate
sudo certbot --nginx -d agent-neo.yourdomain.com

# Auto-renewal is configured automatically
```

## 9. Verify Deployment

```bash
# Health check
curl https://agent-neo.yourdomain.com/health

# Test with auth
curl -X POST https://agent-neo.yourdomain.com/plan \
  -H "Authorization: Bearer your-secure-bearer-token" \
  -H "Content-Type: application/json" \
  -d '{"task_id": "test-1", "description": "Test task"}'
```

## 10. Monitoring

```bash
# View logs
sudo journalctl -u agent-neo -f

# Check service status
sudo systemctl status agent-neo
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| 502 Bad Gateway | Check if service is running: `systemctl status agent-neo` |
| Auth failures | Verify AGENT_NEO_TOKEN in .env matches request header |
| Git push fails | Check SSH keys and REQUIRE_REMOTE setting |
| Permission denied | Ensure agentneo user owns REPO_PATH |

## Security Checklist

- [ ] Strong bearer token (32+ chars)
- [ ] HTTPS enabled
- [ ] Firewall configured (ufw allow 80,443)
- [ ] SSH key auth only (disable password auth)
- [ ] Regular security updates

