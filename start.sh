#!/usr/bin/env bash
# =============================================================================
# Legal Lens — one command to boot the complete project (backend API + frontend).
#
#   ./start.sh            prepare everything, start both servers, wait until healthy,
#                         open the browser; Ctrl+C stops both
#   ./start.sh stop       stop servers started by this script (from another terminal)
#   ./start.sh status     show what is running and whether the backend is ready
#   ./start.sh help       this text
#
# Windows: run from Git Bash. From PowerShell use Git's bash explicitly
# (plain `bash` there is usually WSL, which cannot use this Windows virtualenv):
#   & "C:\Program Files\Git\bin\bash.exe" start.sh
#
# What "prepare" does (each step is skipped when already done):
#   1. checks Python >= 3.11, Node >= 20, curl
#   2. creates ./venv and installs requirements.txt (+ requirements-dev.txt)
#   3. installs frontend/node_modules (again when package-lock.json changed)
#   4. creates .env from .env.example (you still need to add GROQ_API_KEY)
#   5. builds the local search index from data/legal_docs when it does not exist
#
# Options (environment variables):
#   BACKEND_PORT=8000  FRONTEND_PORT=5173
#   LL_NO_BROWSER=1       do not open the browser
#   LL_NO_RELOAD=1        start uvicorn without --reload
#   LL_SKIP_INSTALL=1     never install dependencies (fail instead)
#   LL_KEEP_SHELL_ENV=1   keep QDRANT_URL / QDRANT_API_KEY from this shell (normally .env wins)
#   LL_INGEST_FIXTURES=1  also index evaluation/corpus (paraphrased demo statutes) on first run
#   LL_READY_TIMEOUT=300  seconds to wait for the embedding model before giving up waiting
# =============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$ROOT/frontend"
RUN_DIR="$ROOT/.run"
LOG_DIR="$ROOT/logs"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
READY_TIMEOUT="${LL_READY_TIMEOUT:-300}"
BACKEND_URL="http://127.0.0.1:$BACKEND_PORT"
FRONTEND_URL="http://localhost:$FRONTEND_PORT"

# ---------------------------------------------------------------- output helpers
if [[ -t 1 ]]; then
  B=$'\e[1m'; DIM=$'\e[2m'; GRN=$'\e[32m'; YEL=$'\e[33m'; RED=$'\e[31m'; CYN=$'\e[36m'; RST=$'\e[0m'
else
  B=""; DIM=""; GRN=""; YEL=""; RED=""; CYN=""; RST=""
fi
step() { printf '%s==>%s %s\n' "$CYN$B" "$RST" "$*"; }
ok()   { printf '    %s✓%s %s\n' "$GRN" "$RST" "$*"; }
warn() { printf '    %s!%s %s\n' "$YEL" "$RST" "$*"; }
die()  { printf '%s✗ %s%s\n' "$RED$B" "$*" "$RST" >&2; exit 1; }

usage() { sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; }

# ---------------------------------------------------------------- platform
is_windows() { [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* || -n "${MSYSTEM:-}" ]]; }
is_wsl()     { grep -qi microsoft /proc/version 2>/dev/null; }

venv_python() {
  if [[ -x "$ROOT/venv/Scripts/python.exe" ]]; then echo "$ROOT/venv/Scripts/python.exe"
  elif [[ -x "$ROOT/venv/bin/python" ]]; then echo "$ROOT/venv/bin/python"
  fi
}

# ---------------------------------------------------------------- process helpers
pid_file() { echo "$RUN_DIR/$1.pid"; }

save_pid() { # name pid  -> "msys_pid windows_pid"
  local winpid=""
  [[ -r "/proc/$2/winpid" ]] && winpid="$(cat "/proc/$2/winpid" 2>/dev/null)"
  echo "$2 $winpid" > "$(pid_file "$1")"
}

kill_tree() { # pid [winpid]
  local pid="${1:-}" winpid="${2:-}"
  [[ -z "$pid" && -z "$winpid" ]] && return 0
  if [[ -z "$winpid" && -n "$pid" && -r "/proc/$pid/winpid" ]]; then winpid="$(cat "/proc/$pid/winpid" 2>/dev/null)"; fi
  if [[ -n "$winpid" ]] && command -v taskkill >/dev/null 2>&1; then
    taskkill //PID "$winpid" //T //F >/dev/null 2>&1   # whole tree: uvicorn reloader + worker, node
  fi
  if [[ -n "$pid" ]]; then
    pkill -TERM -P "$pid" >/dev/null 2>&1
    kill -TERM "$pid" >/dev/null 2>&1
  fi
  return 0
}

stop_named() { # name
  local f; f="$(pid_file "$1")"
  [[ -f "$f" ]] || return 1
  local pid winpid
  read -r pid winpid < "$f" || true
  kill_tree "$pid" "$winpid"
  rm -f "$f"
  return 0
}

port_open() { (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1; }
backend_healthy() { curl -fsS -m 3 "$BACKEND_URL/health" 2>/dev/null | grep -q '"healthy"'; }
frontend_up() { curl -fsS -m 3 -o /dev/null "http://127.0.0.1:$FRONTEND_PORT/" 2>/dev/null; }

# Summarise /ready with Python (no jq dependency). Prints "<status>|<checks>|<failed>".
ready_summary() {
  local py; py="$(venv_python)"
  curl -sS -m 6 "$BACKEND_URL/ready" 2>/dev/null | "$py" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("unreachable||"); sys.exit()
checks = " ".join("%s=%s" % kv for kv in d.get("checks", {}).items())
print("|".join([str(d.get("status", "?")), checks, ",".join(d.get("failed", []))]))
' 2>/dev/null || echo "unreachable||"
}

# ---------------------------------------------------------------- commands
cmd_stop() {
  local any=0
  stop_named frontend && { ok "frontend stopped"; any=1; }
  stop_named backend && { ok "backend stopped"; any=1; }
  [[ $any -eq 1 ]] || warn "nothing started by start.sh is running (servers started elsewhere are left alone)"
}

cmd_status() {
  if backend_healthy; then
    local s; s="$(ready_summary)"
    ok "backend  $BACKEND_URL  — ${s%%|*}  ${DIM}$(cut -d'|' -f2 <<<"$s")${RST}"
  elif port_open "$BACKEND_PORT"; then warn "port $BACKEND_PORT is in use but /health does not answer"
  else warn "backend not running"; fi
  if frontend_up; then ok "frontend $FRONTEND_URL"; else warn "frontend not running"; fi
}

prepare() {
  step "Checking prerequisites"
  is_wsl && die "This looks like WSL. Run start.sh from Git Bash (Windows) so it uses the project's Windows virtualenv:
    & \"C:\\Program Files\\Git\\bin\\bash.exe\" start.sh      (from PowerShell)"
  command -v curl >/dev/null 2>&1 || die "curl is required (it ships with Git for Windows)"
  command -v node >/dev/null 2>&1 || die "Node.js 20+ is required: https://nodejs.org"
  command -v npm  >/dev/null 2>&1 || die "npm is required (installed with Node.js)"
  local node_major; node_major="$(node -p 'process.versions.node.split(".")[0]')"
  (( node_major >= 20 )) || die "Node.js 20+ is required (found $(node -v))"
  ok "node $(node -v), npm $(npm -v)"

  # Python virtualenv
  local py; py="$(venv_python)"
  if [[ -z "$py" ]]; then
    [[ -n "${LL_SKIP_INSTALL:-}" ]] && die "venv/ is missing and LL_SKIP_INSTALL is set"
    local base=""
    for cand in "py -3.12" "py -3" python3.12 python3 python; do
      if $cand -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then base="$cand"; break; fi
    done
    [[ -n "$base" ]] || die "Python 3.11+ is required: https://www.python.org/downloads/"
    step "Creating virtualenv with $base"
    $base -m venv "$ROOT/venv" || die "could not create venv"
    py="$(venv_python)"
  fi
  ok "python $("$py" -c 'import platform; print(platform.python_version())') (venv)"

  if ! "$py" -c 'import importlib.util as u, sys; sys.exit(0 if all(u.find_spec(m) for m in ("fastapi","uvicorn","qdrant_client","langgraph","sentence_transformers","groq","alembic","aiosqlite")) else 1)' 2>/dev/null; then
    [[ -n "${LL_SKIP_INSTALL:-}" ]] && die "Python dependencies are missing and LL_SKIP_INSTALL is set"
    step "Installing Python dependencies (first run can take several minutes)"
    "$py" -m pip install --upgrade pip >/dev/null 2>&1
    "$py" -m pip install -r "$ROOT/requirements.txt" -r "$ROOT/requirements-dev.txt" || die "pip install failed"
  fi
  ok "python dependencies installed"

  # Frontend dependencies
  if [[ ! -d "$FRONTEND/node_modules" || "$FRONTEND/package-lock.json" -nt "$FRONTEND/node_modules/.package-lock.json" ]]; then
    [[ -n "${LL_SKIP_INSTALL:-}" ]] && die "frontend dependencies are missing/outdated and LL_SKIP_INSTALL is set"
    step "Installing frontend dependencies"
    (cd "$FRONTEND" && npm install --no-audit --no-fund) || die "npm install failed"
  fi
  ok "frontend dependencies installed"

  # Configuration
  if [[ ! -f "$ROOT/.env" ]]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    warn "created .env from .env.example — add GROQ_API_KEY (or LLM_API_KEY) to get generated answers"
  elif ! grep -Eq '^[[:space:]]*(GROQ_API_KEY|LLM_API_KEY)[[:space:]]*=[[:space:]]*[^[:space:]#]' "$ROOT/.env"; then
    warn ".env has no GROQ_API_KEY / LLM_API_KEY — search works, answers cannot be generated"
  else
    ok ".env found (LLM key configured)"
  fi
  if [[ -z "${LL_KEEP_SHELL_ENV:-}" ]]; then
    for v in QDRANT_URL QDRANT_API_KEY; do
      if [[ -n "${!v:-}" ]]; then warn "ignoring $v from this shell so .env decides (set LL_KEEP_SHELL_ENV=1 to keep it)"; unset "$v"; fi
    done
  fi

  # Local search index (only in embedded mode, i.e. no QDRANT_URL in .env)
  if ! grep -Eq '^[[:space:]]*QDRANT_URL[[:space:]]*=[[:space:]]*[^[:space:]#]' "$ROOT/.env" && [[ ! -d "$ROOT/data/qdrant" ]]; then
    step "Building the local search index from data/legal_docs (downloads the embedding model on first run)"
    "$py" "$ROOT/scripts/ingest.py" --source "$ROOT/data/legal_docs" || die "indexing failed (see output above)"
    if [[ -n "${LL_INGEST_FIXTURES:-}" ]]; then
      "$py" "$ROOT/scripts/ingest.py" --source "$ROOT/evaluation/corpus" || warn "fixture indexing failed"
    fi
  fi
  ok "search index ready"
}

STARTED_BACKEND=0
STARTED_FRONTEND=0
cleanup() { # exit-code
  local rc="${1:-0}"
  trap - INT TERM EXIT
  if [[ $STARTED_BACKEND -eq 1 || $STARTED_FRONTEND -eq 1 ]]; then
    echo
    step "Shutting down"
    [[ $STARTED_FRONTEND -eq 1 ]] && stop_named frontend && ok "frontend stopped"
    [[ $STARTED_BACKEND -eq 1 ]] && stop_named backend && ok "backend stopped"
  fi
  exit "$rc"
}

wait_for() { # description seconds probe-function pid-name
  local what="$1" secs="$2" probe="$3" name="$4" i
  for ((i = 0; i < secs; i++)); do
    "$probe" && return 0
    local f; f="$(pid_file "$name")"
    if [[ -f "$f" ]]; then
      local pid; read -r pid _ < "$f"
      if ! kill -0 "$pid" 2>/dev/null; then
        printf '%s--- last lines of logs/%s.log ---%s\n' "$DIM" "$name" "$RST"
        tail -n 25 "$LOG_DIR/$name.log" 2>/dev/null
        die "$what exited during startup"
      fi
    fi
    sleep 1
  done
  printf '%s--- last lines of logs/%s.log ---%s\n' "$DIM" "$name" "$RST"; tail -n 25 "$LOG_DIR/$name.log" 2>/dev/null
  die "$what did not come up within ${secs}s"
}

start_backend() {
  if backend_healthy; then ok "backend already running at $BACKEND_URL — reusing it"; return; fi
  port_open "$BACKEND_PORT" && die "port $BACKEND_PORT is in use by another program. Free it or run: BACKEND_PORT=8001 ./start.sh"
  local py reload=(--reload); py="$(venv_python)"
  [[ -n "${LL_NO_RELOAD:-}" ]] && reload=()
  step "Starting backend on $BACKEND_URL ${DIM}(logs/backend.log)${RST}"
  (
    cd "$ROOT" && exec "$py" -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" "${reload[@]}"
  ) >>"$LOG_DIR/backend.log" 2>&1 &
  save_pid backend $!
  STARTED_BACKEND=1
  wait_for "backend" 90 backend_healthy backend
  ok "backend is live"
}

start_frontend() {
  if frontend_up; then ok "frontend already running at $FRONTEND_URL — reusing it"; return; fi
  port_open "$FRONTEND_PORT" && die "port $FRONTEND_PORT is in use by another program. Free it or run: FRONTEND_PORT=5174 ./start.sh"
  step "Starting frontend on $FRONTEND_URL ${DIM}(logs/frontend.log)${RST}"
  (
    cd "$FRONTEND" && VITE_DEV_PROXY_TARGET="$BACKEND_URL" exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort
  ) >>"$LOG_DIR/frontend.log" 2>&1 &
  save_pid frontend $!
  STARTED_FRONTEND=1
  wait_for "frontend" 60 frontend_up frontend
  ok "frontend is live"
}

wait_ready() {
  step "Waiting for the backend to be ready ${DIM}(embedding model loads in the background)${RST}"
  local i s status
  for ((i = 0; i < READY_TIMEOUT; i += 3)); do
    s="$(ready_summary)"; status="${s%%|*}"
    if [[ "$status" == "ready" ]]; then ok "ready: $(cut -d'|' -f2 <<<"$s")"; return; fi
    # Anything other than a model that is still loading will not fix itself by waiting.
    if [[ "$s" != *"embedding=loading"* && "$status" == "not_ready" ]]; then
      warn "not ready — unavailable: $(cut -d'|' -f3 <<<"$s")"
      warn "details: $BACKEND_URL/ready   (the app opens in limited mode)"
      return
    fi
    sleep 3
  done
  warn "still not ready after ${READY_TIMEOUT}s — check $BACKEND_URL/ready and logs/backend.log"
}

open_browser() {
  [[ -n "${LL_NO_BROWSER:-}" ]] && return
  if is_windows; then cmd //c start "" "$FRONTEND_URL" >/dev/null 2>&1
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$FRONTEND_URL" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then open "$FRONTEND_URL" >/dev/null 2>&1
  fi
}

cmd_start() {
  mkdir -p "$RUN_DIR" "$LOG_DIR"
  printf '\n%s  Legal Lens — starting the complete project%s\n\n' "$B" "$RST"
  prepare
  # Ctrl+C / kill stops what we started; a startup failure (die) also stops it, keeping its exit code.
  trap 'cleanup 0' INT TERM
  trap 'cleanup $?' EXIT
  start_backend
  start_frontend
  wait_ready
  open_browser
  cat <<EOF

${B}  Legal Lens is running${RST}
    App            ${CYN}$FRONTEND_URL${RST}
    API docs       $BACKEND_URL/docs
    Health / ready $BACKEND_URL/health · $BACKEND_URL/ready
    Logs           logs/backend.log · logs/frontend.log

  First visit: create an account, then ask a question.
  ${DIM}Press Ctrl+C to stop both servers (or run ./start.sh stop from another terminal).${RST}

EOF
  if [[ $STARTED_BACKEND -eq 0 && $STARTED_FRONTEND -eq 0 ]]; then
    trap - INT TERM EXIT
    echo "  Both servers were already running; nothing to supervise."
    exit 0
  fi
  # Supervise: if a server we started exits, stop the other and report it.
  while true; do
    if [[ ! -f "$(pid_file backend)" && ! -f "$(pid_file frontend)" ]]; then
      # `./start.sh stop` ran in another terminal and already stopped everything.
      trap - INT TERM EXIT
      ok "servers stopped by ./start.sh stop"
      exit 0
    fi
    for name in backend frontend; do
      local f; f="$(pid_file "$name")"
      [[ -f "$f" ]] || continue
      local pid; read -r pid _ < "$f"
      if ! kill -0 "$pid" 2>/dev/null; then
        warn "$name stopped unexpectedly — last lines of logs/$name.log:"
        tail -n 20 "$LOG_DIR/$name.log" 2>/dev/null
        rm -f "$f"
        cleanup 1
      fi
    done
    sleep 2
  done
}

case "${1:-start}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  help | -h | --help) usage ;;
  *) usage; exit 2 ;;
esac
