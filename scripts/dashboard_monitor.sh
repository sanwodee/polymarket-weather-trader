#!/bin/bash
# Dashboard health check and auto-restart script

DASHBOARD_URL="http://localhost:5001"
LOG_FILE="$HOME/polymarket-trader/dashboard/dashboard_monitor.log"
PID_FILE="$HOME/polymarket-trader/dashboard/dashboard.pid"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Check if dashboard is responding
if curl -s -o /dev/null -w "%{http_code}" "$DASHBOARD_URL" | grep -q "200\|301\|302"; then
    # Dashboard is healthy
    PID=$(lsof -i :5001 2>/dev/null | grep LISTEN | awk '{print $2}' | head -1)
    if [ -n "$PID" ]; then
        echo "$PID" > "$PID_FILE"
    fi
    exit 0
else
    log "⚠️ Dashboard not responding on $DASHBOARD_URL"
    
    # Kill any existing processes
    pkill -f "dashboard_server.py" 2>/dev/null
    sleep 2
    
    # Restart dashboard
    cd "$HOME/polymarket-trader/dashboard" || exit 1
    source ../.venv/bin/activate
    nohup python dashboard_server.py > dashboard.log 2>&1 &
    NEW_PID=$!
    
    # Wait and verify
    sleep 3
    if curl -s -o /dev/null -w "%{http_code}" "$DASHBOARD_URL" | grep -q "200\|301\|302"; then
        echo "$NEW_PID" > "$PID_FILE"
        log "✅ Dashboard restarted successfully (PID: $NEW_PID)"
    else
        log "❌ Failed to restart dashboard"
        exit 1
    fi
fi