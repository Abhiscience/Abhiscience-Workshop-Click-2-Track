#!/bin/bash
# Part B deployment helper for VPS
set -e
cd /root/Abhiscience-Workshop-Click-2-Track
git pull origin main
cd services/api

# Apply DB migration first.
.venv/bin/python3 scripts/apply_part_b.py

# Restart backend. Prefer PM2 if available; otherwise use the existing start script or uvicorn directly.
if [ -f /root/start_api_server.sh ]; then
  bash /root/start_api_server.sh
  sleep 4
elif command -v pm2 &>/dev/null; then
  pm2 restart workshop-api || pm2 start .venv/bin/python3 --name workshop-api -- -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
  sleep 4
else
  pkill -f "uvicorn.*app.main:app" || true
  nohup .venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/api.log 2>&1 &
  sleep 4
fi

echo "--- health check ---"
curl -s http://localhost:8000/ || true
echo ""
echo "Part B applied."
