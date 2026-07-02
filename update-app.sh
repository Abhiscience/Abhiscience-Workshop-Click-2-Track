#!/bin/bash
# Auto-update Workshop Click-2-Track from GitHub and restart PM2 services
set -e

REPO_DIR=/root/Abhiscience-Workshop-Click-2-Track
LOG_FILE=/var/log/workshop-auto-update.log
API_URL=http://76.13.223.20:8000/api/v1

echo "\n=== Update check at $(date) ===" >> "$LOG_FILE"
cd "$REPO_DIR"

# Stash local changes
git stash push -m "auto-stash-$(date +%Y%m%d%H%M%S)" >> "$LOG_FILE" 2>&1 || true

# Fetch latest
git fetch origin >> "$LOG_FILE" 2>&1

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "New commits found. Pulling..." >> "$LOG_FILE"
    git pull origin main >> "$LOG_FILE" 2>&1

    # Update Python backend
    cd "$REPO_DIR/services/api"
    .venv/bin/pip install -r requirements.txt >> "$LOG_FILE" 2>&1 || true

    # Rebuild admin web
    cd "$REPO_DIR/apps/admin-web"
    /usr/bin/npm install --legacy-peer-deps >> "$LOG_FILE" 2>&1
    NEXT_PUBLIC_API_URL="$API_URL" /usr/bin/npm run build >> "$LOG_FILE" 2>&1

    # Restart PM2 services
    cd "$REPO_DIR"
    /usr/local/bin/pm2 restart ecosystem.config.js >> "$LOG_FILE" 2>&1
    /usr/local/bin/pm2 save --force >> "$LOG_FILE" 2>&1

    echo "Update complete at $(date)" >> "$LOG_FILE"
else
    echo "No new commits." >> "$LOG_FILE"
fi
