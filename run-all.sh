#!/usr/bin/env bash
# ============================================================
# TalentOS — Local Development Runner
# ============================================================
# Usage: ./run-all.sh [--skip-frontend] [--skip-backend]
# ============================================================
set -euo pipefail

SKIP_FRONTEND=false
SKIP_BACKEND=false
for arg in "$@"; do
  case $arg in
    --skip-frontend) SKIP_FRONTEND=true ;;
    --skip-backend)  SKIP_BACKEND=true  ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$ROOT_DIR/.talentos.pids"

# Colours
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[TalentOS]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

mkdir -p "$LOG_DIR"
> "$PID_FILE"

# Cleanup on exit
cleanup() {
  info "Shutting down all services..."
  if [[ -f "$PID_FILE" ]]; then
    while IFS= read -r pid; do
      [[ -n "$pid" ]] && kill "$pid" 2>/dev/null && info "Stopped PID $pid"
    done < "$PID_FILE"
  fi
  rm -f "$PID_FILE"
}
trap cleanup EXIT INT TERM

# Check prerequisites
check_prereq() {
  if ! command -v "$1" &>/dev/null; then
    error "Required tool not found: $1"
    exit 1
  fi
}
check_prereq python3
check_prereq pip

# Check .env exists
if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  error "backend/.env not found. Copy backend/.env.example to backend/.env and fill in your credentials."
  exit 1
fi

# ── Backend Services ─────────────────────────────────────────
if [[ "$SKIP_BACKEND" == "false" ]]; then
  info "Installing backend dependencies..."
  pip install -r "$BACKEND_DIR/requirements.txt" -q

  # Authentication service (port 8000)
  info "Starting Authentication service on :8000..."
  cd "$BACKEND_DIR"
  python3 -m uvicorn authentication.app.main:app \
    --host 0.0.0.0 --port 8000 \
    --log-level info \
    > "$LOG_DIR/auth.log" 2>&1 &
  echo $! >> "$PID_FILE"
  sleep 1

  # Anti-spoofing service (port 8080)
  info "Starting Anti-Spoofing service on :8080..."
  python3 -m uvicorn anti_spoofing.app.main:app \
    --host 0.0.0.0 --port 8080 \
    --log-level info \
    > "$LOG_DIR/anti_spoofing.log" 2>&1 &
  echo $! >> "$PID_FILE"
  sleep 1

  # ATS Parser service (port 8090)
  info "Starting ATS Parser service on :8090..."
  python3 -m uvicorn ats_parser_checker.app.main:app \
    --host 0.0.0.0 --port 8090 \
    --log-level info \
    > "$LOG_DIR/ats.log" 2>&1 &
  echo $! >> "$PID_FILE"
  sleep 1

  # Orchestration service (port 8001)
  info "Starting Orchestration service on :8001..."
  python3 -m uvicorn orchestration.app.main:app \
    --host 0.0.0.0 --port 8001 \
    --log-level info \
    > "$LOG_DIR/orchestration.log" 2>&1 &
  echo $! >> "$PID_FILE"
  sleep 2
fi

# ── Frontend ─────────────────────────────────────────────────
if [[ "$SKIP_FRONTEND" == "false" ]]; then
  if ! command -v node &>/dev/null; then
    warn "Node.js not found — skipping frontend. Install Node.js >= 20."
  else
    info "Installing frontend dependencies..."
    cd "$FRONTEND_DIR"
    npm install --silent

    info "Starting Angular frontend on :3000..."
    npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
    echo $! >> "$PID_FILE"
  fi
fi

# ── Status ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  TalentOS is running locally 🚀      ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Frontend    → http://localhost:3000  ║${NC}"
echo -e "${GREEN}║  Auth API    → http://localhost:8000  ║${NC}"
echo -e "${GREEN}║  Orch API    → http://localhost:8001  ║${NC}"
echo -e "${GREEN}║  ATS API     → http://localhost:8090  ║${NC}"
echo -e "${GREEN}║  AntiSpoof   → http://localhost:8080  ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Logs in: ./logs/                     ║${NC}"
echo -e "${GREEN}║  Press Ctrl+C to stop all services   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""

# Keep alive
wait
