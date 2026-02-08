#!/usr/bin/env bash
set -euo pipefail

PID_FILE="/tmp/mitchopolis_watch_inbox.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "No watcher pid file found."
  exit 0
fi

pid="$(cat "$PID_FILE")"
if kill -0 "$pid" 2>/dev/null; then
  kill "$pid"
  sleep 1
  if kill -0 "$pid" 2>/dev/null; then
    echo "Watcher still running (pid $pid)."
    exit 1
  fi
  echo "Watcher stopped (pid $pid)."
else
  echo "Watcher not running (stale pid file)."
fi

rm -f "$PID_FILE"
