#!/bin/bash
# Auto-update Workshop Click-2-Track from GitHub and restart services
set -e

REPO_DIR=/root/Abhiscience-Workshop-Click-2-Track
LOG_FILE=/var/log/workshop-auto-update.log

echo "\n=== Update check at $(date) ===" >> "$LOG_FILE"
cd "$REPO_DIR"

# Stash any local uncommitted changes to avoid pull conflicts
git stash push -m "auto-stash-$(date +%%Y%%m%%d%%H%%M%%S)" >> "$LOG_FILE" 2>&1 || true

# Fetch latest from GitHub
git fetch origin >> "$LOG_FILE" 2>&1

# Check if there are new commits
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "New commits found. Pulling..." >> "$LOG_FILE"
    git pull origin master >> "$LOG_FILE" 2>&1

    # Update Python backend dependencies
    cd "$REPO_DIR/services/api"
    .venv/bin/python -m pip install -r requirements.txt >> "$LOG_FILE" 2>&1 || true

    # Update/rebuild admin web
    cd "$REPO_DIR/apps/admin-web"
    /usr/bin/npm install >> "$LOG_FILE" 2>&1
    /usr/bin/npm run build >> "$LOG_FILE" 2>&1

    # Restart services
    systemctl restart workshop-api.service
    systemctl restart workshop-web.service

    echo "Update complete at $(date)" >> "$LOG_FILE"
else
    echo "No new commits." >> "$LOG_FILE"
fi
