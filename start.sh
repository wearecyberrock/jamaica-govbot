#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8010}"
FRONTEND_PORT="${FRONTEND_PORT:-3010}"

echo "================================================================"
echo "  Jahtaria Travel Services — U.S. Visa Intelligence Suite"
echo "  Desktop Launcher (SQLite + Local Obsidian Vault + Official PDFs)"
echo "================================================================"

# 1. Setup Python backend venv if missing
if [ ! -d "$ROOT_DIR/backend/.venv" ]; then
  echo "[1/3] Creating Python virtual environment..."
  python3 -m venv "$ROOT_DIR/backend/.venv"
  "$ROOT_DIR/backend/.venv/bin/pip" install --upgrade pip -q
  "$ROOT_DIR/backend/.venv/bin/pip" install -r "$ROOT_DIR/backend/requirements.txt"
fi

# 2. Setup Next.js frontend dependencies if missing
if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then
  echo "[2/3] Installing Next.js frontend packages..."
  (cd "$ROOT_DIR/frontend" && npm install)
fi

echo "[3/3] Starting Backend (:$BACKEND_PORT) and Frontend (:$FRONTEND_PORT)..."
(cd "$ROOT_DIR/backend" && "$ROOT_DIR/backend/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$BACKEND_PORT") &
BACK_PID=$!

trap 'echo "Shutting down..."; kill $BACK_PID 2>/dev/null || true' EXIT INT TERM

sleep 2
echo ""
echo "  App Ready! Open: http://localhost:$FRONTEND_PORT/login"
echo "  Seeded CEO:      ceo@jahtariatravel.com    / JahtariaCEO2026!"
echo "  Seeded Staff:    staff@jahtariatravel.com  / JahtariaStaff2026!"
echo "  Seeded Customer: client@jahtariatravel.com / JahtariaClient2026! (Code: JAH-C034)"
echo "  MCP Endpoint:    http://localhost:$BACKEND_PORT/mcp"
echo "  Obsidian Vault:  $ROOT_DIR/data/obsidian-vault"
echo ""

# Open default desktop browser if available
if command -v open >/dev/null 2>&1; then
  (sleep 3 && open "http://localhost:$FRONTEND_PORT/login") &
elif command -v xdg-open >/dev/null 2>&1; then
  (sleep 3 && xdg-open "http://localhost:$FRONTEND_PORT/login") &
fi

cd "$ROOT_DIR/frontend"
if [ -d ".next" ]; then
  npx next start -p "$FRONTEND_PORT"
else
  npm run dev -- -p "$FRONTEND_PORT"
fi
