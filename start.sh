#!/usr/bin/env bash
#
# Start both the FastAPI backend and Vite frontend dev servers.
#
# Usage:
#   ./start.sh                  # default: full app mode (/)
#   ./start.sh --mode=widget    # opens widget mode (/widget)
#   ./start.sh --mode=embed     # opens embed mode (/embed)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_PORT=8000
WEB_PORT=5173
MODE="full"

# Parse args
for arg in "$@"; do
  case $arg in
    --mode=*) MODE="${arg#*=}" ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

case "$MODE" in
  full)   URL_PATH="/" ;;
  widget) URL_PATH="/widget" ;;
  embed)  URL_PATH="/embed" ;;
  *)      echo "Invalid mode: $MODE (use full, widget, or embed)"; exit 1 ;;
esac

# PIDs to track
API_PID=""
WEB_PID=""

cleanup() {
  echo ""
  echo "Shutting down..."
  [[ -n "$WEB_PID" ]] && kill "$WEB_PID" 2>/dev/null && wait "$WEB_PID" 2>/dev/null
  [[ -n "$API_PID" ]] && kill "$API_PID" 2>/dev/null && wait "$API_PID" 2>/dev/null
  echo "Done."
  exit 0
}

trap cleanup SIGINT SIGTERM

echo "┌──────────────────────────────────────────────┐"
echo "│  🏥 Western Health Chat                      │"
echo ""
echo "  Mode:     $MODE$(printf '%*s' $((37 - ${#MODE})) '')"
echo "  API:      http://localhost:${API_PORT}│"
echo "  Frontend: http://localhost:${WEB_PORT}${URL_PATH}$(printf '%*s' $((15 - ${#URL_PATH})) '')"
echo ""
echo "  Press Ctrl+C to stop both servers│"
echo "└──────────────────────────────────────────────┘"
echo ""

# Start API server
echo "Starting API server..."
cd "$SCRIPT_DIR"
source .venv/bin/activate
uvicorn web.api.server:app --reload --port "$API_PORT" &
API_PID=$!

# Start Vite dev server
echo "Starting frontend dev server..."
cd "$SCRIPT_DIR/web"
npx vite --port "$WEB_PORT" &
WEB_PID=$!

echo ""
echo "Both servers running. Press Ctrl+C to stop."
echo ""

# Wait for either process to exit
wait -n "$API_PID" "$WEB_PID" 2>/dev/null || true
cleanup
