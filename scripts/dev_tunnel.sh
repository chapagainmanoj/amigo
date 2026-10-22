#!/usr/bin/env bash
# Run Amigo in Telegram mode behind a persistent Microsoft Dev Tunnel (same service as
# VS Code port forwarding). The tunnel ID is fixed, so the public URL is stable across runs.
#
# Usage:
#   scripts/dev_tunnel.sh                # tunnel + uvicorn
#   scripts/dev_tunnel.sh --reload       # tunnel + uvicorn --reload
#   scripts/dev_tunnel.sh --tunnel-only  # tunnel only (run the API from the VS Code debugger)
#
# Env overrides: PORT (default 8000), TUNNEL_ID (default amigo-<user>).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"
TUNNEL_ID="${TUNNEL_ID:-amigo-$(whoami | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9\n' '-')}"
LOG_FILE="$(mktemp -t amigo-devtunnel)"
RELOAD=""
TUNNEL_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --reload) RELOAD="--reload" ;;
    --tunnel-only) TUNNEL_ONLY=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

env_value() {
  grep -E "^$1=" .env 2>/dev/null | tail -n1 | cut -d= -f2- | sed -E 's/^["'\'']|["'\'']$//g'
}

# 1. devtunnel CLI + login
if ! command -v devtunnel >/dev/null; then
  echo "devtunnel CLI not found. Install with: brew install --cask devtunnel" >&2
  exit 1
fi
# `user show` exits 0 even when logged out, so check its output instead
if devtunnel user show 2>&1 | grep -qi "not logged in"; then
  echo "Logging in to Dev Tunnels (GitHub)..."
  devtunnel user login -g
fi

# 2. Persistent tunnel with anonymous (public) access on $PORT
if ! devtunnel show "$TUNNEL_ID" >/dev/null 2>&1; then
  echo "Creating tunnel $TUNNEL_ID..."
  devtunnel create "$TUNNEL_ID" --allow-anonymous --expiration 30d >/dev/null
fi
devtunnel port create "$TUNNEL_ID" -p "$PORT" >/dev/null 2>&1 || true
devtunnel access create "$TUNNEL_ID" --anonymous >/dev/null 2>&1 || true

# 3. Host the tunnel in the background and read the public URL from its output
devtunnel host "$TUNNEL_ID" >"$LOG_FILE" 2>&1 &
HOST_PID=$!
cleanup() {
  kill "$HOST_PID" 2>/dev/null || true
  [[ -n "${CHECK_PID:-}" ]] && kill "$CHECK_PID" 2>/dev/null || true
  rm -f "$LOG_FILE"
}
trap cleanup EXIT INT TERM

URL=""
for _ in $(seq 1 30); do
  URL="$(grep -oE "https://[a-z0-9.-]*-${PORT}\.[a-z0-9.-]*devtunnels\.ms" "$LOG_FILE" | head -n1 || true)"
  [[ -n "$URL" ]] && break
  if ! kill -0 "$HOST_PID" 2>/dev/null; then
    echo "devtunnel host exited:" >&2; cat "$LOG_FILE" >&2; exit 1
  fi
  sleep 1
done
if [[ -z "$URL" ]]; then
  echo "Timed out waiting for tunnel URL. Output:" >&2; cat "$LOG_FILE" >&2; exit 1
fi

echo "Tunnel: $URL -> localhost:$PORT"
if [[ "$(env_value APP_BASE_URL)" != "$URL" ]]; then
  echo "Tip: set APP_BASE_URL=$URL in .env so the VS Code debugger uses it too."
fi

if [[ "$TUNNEL_ONLY" == 1 ]]; then
  echo "Tunnel-only mode. Start the API (F5 → 'Amigo API (Telegram)'). Ctrl+C to stop."
  wait "$HOST_PID"
  exit 0
fi

# 4. After the API is healthy, report what Telegram sees for the webhook
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-$(env_value TELEGRAM_BOT_TOKEN)}"
(
  for _ in $(seq 1 60); do
    curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1 && break
    sleep 1
  done
  sleep 2
  if [[ -n "$BOT_TOKEN" ]]; then
    echo "--- Telegram getWebhookInfo ---"
    curl -s "https://api.telegram.org/bot$BOT_TOKEN/getWebhookInfo"
    echo
  fi
) &
CHECK_PID=$!

# 5. Run the API; APP_BASE_URL env var overrides .env (pydantic-settings precedence).
# pydantic_ai reads GOOGLE_API_KEY from the process environment, not from Settings, so export it.
GOOGLE_API_KEY="${GOOGLE_API_KEY:-$(env_value GOOGLE_API_KEY)}"
export GOOGLE_API_KEY
# shellcheck disable=SC1091
[[ -f .venv/bin/activate ]] && source .venv/bin/activate
APP_BASE_URL="$URL" uvicorn src.main:app --port "$PORT" $RELOAD
