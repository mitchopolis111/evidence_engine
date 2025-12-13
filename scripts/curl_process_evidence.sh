#!/usr/bin/env bash
set -e

cd "$HOME/Mitchopolis/evidence_engine"

curl -X POST \
  http://127.0.0.1:8000/api/evidence/process \
  -H "Content-Type: application/json" \
  -d @scripts/sample_evidence_payload.json
