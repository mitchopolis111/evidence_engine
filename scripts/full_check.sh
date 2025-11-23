#!/usr/bin/env bash
set -e

# Always run from the repo root
cd "$(dirname "$0")/.."

# 1) Activate virtual environment
if [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
else
  echo "venv not found. Run: python3 -m venv venv && pip install -r requirements.txt"
  exit 1
fi

echo "[1/2] Running pytest..."
pytest -vv

echo "[2/2] Running sample /api/evidence/process call (if API is up)..."

set +e
if [ -x "./scripts/curl_process_evidence.sh" ]; then
  ./scripts/curl_process_evidence.sh
  status=$?
else
  echo "scripts/curl_process_evidence.sh not found or not executable."
  status=1
fi
set -e

if [ "$status" -ne 0 ]; then
  echo "Sample curl failed — is run_evidence_api_dev.sh running in another terminal?"
else
  echo "Sample curl succeeded."
fi

echo "Evidence Engine full check complete."
