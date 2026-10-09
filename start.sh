#!/usr/bin/env bash
# Run from the project root: bash start.sh start
# No local development credentials are required; login state is imported in the GUI.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODE_DIR="$PROJECT_DIR/code"
LOG_DIR="$PROJECT_DIR/logs"
PID_FILE="$LOG_DIR/gui.pid"
LOG_FILE="$LOG_DIR/gui.log"
ACTION="${1:-start}"

is_running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

status() {
  if is_running; then
    printf 'running pid=%s\n' "$(cat "$PID_FILE")"
    return 0
  fi
  [[ -f "$PID_FILE" ]] && rm "$PID_FILE"
  printf 'stopped\n'
  return 1
}

stop() {
  if ! is_running; then
    [[ -f "$PID_FILE" ]] && rm "$PID_FILE"
    printf 'already stopped\n'
    return 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  kill "$pid" 2>/dev/null || true
  for _ in {1..30}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.1
  done
  kill -9 "$pid" 2>/dev/null || true
  rm "$PID_FILE"
  printf 'stopped\n'
}

start() {
  command -v uv >/dev/null 2>&1 || {
    printf 'uv is required: https://docs.astral.sh/uv/\n' >&2
    exit 1
  }
  if is_running; then
    printf 'already running pid=%s\n' "$(cat "$PID_FILE")"
    return 0
  fi
  mkdir -p "$LOG_DIR"
  cd "$CODE_DIR"
  if [[ "${START_MODE:-foreground}" == "background" ]]; then
    uv run python main.py >>"$LOG_FILE" 2>&1 &
    local pid=$!
    printf '%s\n' "$pid" >"$PID_FILE"
    sleep 1
    if ! kill -0 "$pid" 2>/dev/null; then
      rm "$PID_FILE"
      printf 'startup failed; see %s\n' "$LOG_FILE" >&2
      exit 1
    fi
    printf 'running pid=%s log=%s\n' "$pid" "$LOG_FILE"
    return 0
  fi
  trap 'printf "stopped\n"' EXIT INT TERM
  exec uv run python main.py
}

case "$ACTION" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  *) printf 'usage: %s {start|stop|restart|status}\n' "$0" >&2; exit 2 ;;
esac
