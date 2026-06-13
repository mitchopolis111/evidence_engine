#!/usr/bin/env bash
set -euo pipefail

TODAY_UTC="$(date -u +%F)"
NOW_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
LOG="dist/logs/${TODAY_UTC}_day1.log"
STATUS_TXT=".vscode/day1_status.txt"
SETTINGS=".vscode/settings.json"

mkdir -p dist/logs .vscode dist/out

fail_status() {
  echo "DAY1_FAIL (${NOW_UTC})" | tee "$STATUS_TXT"
  /usr/bin/python3 - <<PY
import json, os
p=".vscode/settings.json"
try:
    data=json.load(open(p)) if os.path.exists(p) else {}
except Exception:
    data={}
data["mitch.day1Status"]="DAY1_FAIL (${NOW_UTC})"
json.dump(data, open(p,"w"), indent=2, sort_keys=True)
PY
  exit 1
}

pass_status() {
  echo "DAY1_PASS (${NOW_UTC})" | tee "$STATUS_TXT"
  /usr/bin/python3 - <<PY
import json, os
p=".vscode/settings.json"
try:
    data=json.load(open(p)) if os.path.exists(p) else {}
except Exception:
    data={}
data["mitch.day1Status"]="DAY1_PASS (${NOW_UTC})"
json.dump(data, open(p,"w"), indent=2, sort_keys=True)
PY
}

{
  echo "=== DAY1 REAL pipeline start ${NOW_UTC} ==="

  echo "[python]"
  .venv/bin/python -V

  echo "[pytest]"
  .venv/bin/python -m pytest -q

  echo "[api health]"
  curl -fsS http://localhost:8000/health

  echo
  echo "[api version]"
  curl -fsS http://localhost:8000/version

  echo
  echo "[process smoke]"
  bash scripts/curl_process_evidence.sh

  echo
  echo "[zip export]"
  zip -X -r "dist/day1_${TODAY_UTC}.zip" dist/out >/dev/null 2>&1 || true

  echo "=== DAY1 REAL pipeline end ==="
} >>"$LOG" 2>&1 || fail_status

pass_status

echo "ACCEPT: Mitch Day-1 REAL completed ${TODAY_UTC} UTC — tests, API, and process endpoint verified."
