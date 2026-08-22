#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/logs"
PID_FILE="/tmp/mitchopolis_watch_inbox.pid"
LOG_FILE="$LOG_DIR/watch_inbox.log"

CASE_ID="${CASE_ID:-}"
INBOX="${INBOX:-}"
INCLUDE_EXT="${INCLUDE_EXT:-.pdf,.docx}"
ENDPOINT="${ENDPOINT:-}"
TAGS="${TAGS:-}"

if [ -z "$CASE_ID" ]; then
  echo "CASE_ID is required. Example: CASE_ID=BCSC_138865_Watson_v_McClean"
  exit 1
fi

mkdir -p "$LOG_DIR"

if [ -f "$PID_FILE" ]; then
  existing_pid="$(cat "$PID_FILE")"
  if kill -0 "$existing_pid" 2>/dev/null; then
    echo "Watcher already running (pid $existing_pid)."
    exit 0
  fi
  rm -f "$PID_FILE"
fi

args=( "--case-id" "$CASE_ID" "--include-ext" "$INCLUDE_EXT" )

if [ -n "$INBOX" ]; then
  args+=( "--inbox" "$INBOX" )
fi

if [ -n "$ENDPOINT" ]; then
  args+=( "--endpoint" "$ENDPOINT" )
fi

if [ -n "$TAGS" ]; then
  IFS=',' read -r -a tag_array <<< "$TAGS"
  for tag in "${tag_array[@]}"; do
    trimmed="$(echo "$tag" | sed -e 's/^ *//' -e 's/ *$//')"
    if [ -n "$trimmed" ]; then
      args+=( "--tag" "$trimmed" )
    fi
  done
fi

nohup python "$ROOT/scripts/watch_inbox.py" "${args[@]}" >"$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "Watcher started (pid $(cat "$PID_FILE")). Log: $LOG_FILE"
