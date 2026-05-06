#!/bin/bash
# VOLTCORE — Start everything
# Usage: ./start.sh [--fast] [--realtime]

echo ""
echo "⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡"
echo "  VOLTCORE — Community Energy Protocol"
echo "  Starting full simulation stack..."
echo "⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡"
echo ""

# Kill any existing processes
pkill -f "python3 agent/simulate.py" 2>/dev/null
pkill -f "python3 agent/server.py" 2>/dev/null
pkill -f "python3 -m http.server 8080" 2>/dev/null

sleep 1

# Start AI simulation engine
echo "  [1/3] Starting AI simulation engine..."
python3 agent/simulate.py --fast &
SIM_PID=$!
echo "        PID: $SIM_PID"

sleep 2

# Start API server
echo "  [2/3] Starting API server on :8090..."
python3 agent/server.py &
API_PID=$!
echo "        PID: $API_PID"

sleep 1

# Start dashboard server
echo "  [3/3] Starting dashboard on :8080..."
python3 -m http.server 8080 &
DASH_PID=$!
echo "        PID: $DASH_PID"

sleep 1

echo ""
echo "  ✅ All systems running!"
echo ""
echo "  📊 Dashboard:  http://localhost:8080/dashboard.html"
echo "  📡 API:        http://localhost:8090/state"
echo "  🤖 Simulation: running in background (PID $SIM_PID)"
echo ""
echo "  Press Ctrl+C to stop all processes"
echo ""

# Open dashboard in browser
if [[ "$OSTYPE" == "darwin"* ]]; then
    sleep 2
    open http://localhost:8080/dashboard.html
fi

# Wait and handle cleanup
trap "echo ''; echo '  Stopping all processes...'; kill $SIM_PID $API_PID $DASH_PID 2>/dev/null; echo '  Done.'; exit 0" INT

wait
