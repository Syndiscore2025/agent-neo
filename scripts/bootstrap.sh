#!/bin/bash
set -e

echo "========================================="
echo "AGENT NEO - Bootstrap Script"
echo "========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Configuration
INSTALL_DIR="/opt/agent-neo"
SERVICE_USER="agent"
REPO_URL="${REPO_URL:-}"
DOMAIN="${DOMAIN:-}"

echo "Installation directory: $INSTALL_DIR"
echo "Service user: $SERVICE_USER"

# Update system
echo "Updating system packages..."
apt-get update
apt-get upgrade -y

# Install dependencies
echo "Installing dependencies..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    nginx \
    certbot \
    python3-certbot-nginx

# Create service user
if ! id "$SERVICE_USER" &>/dev/null; then
    echo "Creating service user: $SERVICE_USER"
    useradd -r -s /bin/bash -d "$INSTALL_DIR" "$SERVICE_USER"
fi

# Create installation directory
echo "Creating installation directory..."
mkdir -p "$INSTALL_DIR"

# Clone or copy repository
if [ -n "$REPO_URL" ]; then
    echo "Cloning repository from $REPO_URL..."
    git clone "$REPO_URL" "$INSTALL_DIR/agent-neo"
else
    echo "Copying local files..."
    cp -r "$(dirname "$0")/.." "$INSTALL_DIR/agent-neo"
fi

cd "$INSTALL_DIR/agent-neo"

# Create Python virtual environment
echo "Creating Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"

# Activate virtual environment and install dependencies
echo "Installing Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f "$INSTALL_DIR/agent-neo/.env" ]; then
    echo "Creating .env file..."
    cp "$INSTALL_DIR/agent-neo/.env.example" "$INSTALL_DIR/agent-neo/.env"
    
    # Prompt for configuration
    read -p "Enter repository path to manage: " REPO_PATH
    sed -i "s|REPO_PATH=.*|REPO_PATH=$REPO_PATH|" "$INSTALL_DIR/agent-neo/.env"
fi

# Set ownership
echo "Setting ownership..."
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# Install systemd service
echo "Installing systemd service..."
cp "$INSTALL_DIR/agent-neo/deploy/agent-neo.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable agent-neo

# Configure nginx
echo "Configuring nginx..."
cp "$INSTALL_DIR/agent-neo/deploy/nginx.conf" /etc/nginx/sites-available/agent-neo

if [ -n "$DOMAIN" ]; then
    sed -i "s/server_name _;/server_name $DOMAIN;/" /etc/nginx/sites-available/agent-neo
fi

ln -sf /etc/nginx/sites-available/agent-neo /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test nginx configuration
nginx -t

# Start services
echo "Starting services..."
systemctl start agent-neo
systemctl restart nginx

# Setup HTTPS with certbot (if domain provided)
if [ -n "$DOMAIN" ]; then
    echo "Setting up HTTPS with Let's Encrypt..."
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email "admin@$DOMAIN"
fi

# Display status
echo ""
echo "========================================="
echo "AGENT NEO Installation Complete"
echo "========================================="
echo ""
systemctl status agent-neo --no-pager
echo ""
echo "Service status: systemctl status agent-neo"
echo "Service logs: journalctl -u agent-neo -f"
echo "Nginx logs: tail -f /var/log/nginx/agent-neo.*.log"
echo ""

if [ -n "$DOMAIN" ]; then
    echo "Access AGENT NEO at: https://$DOMAIN"
else
    echo "Access AGENT NEO at: http://localhost"
fi

echo ""
echo "Status: Working"

