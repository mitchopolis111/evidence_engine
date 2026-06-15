# Evidence Engine Run Cheat Sheet

Use this when you just want to get the Mitchopolis Evidence Engine running quickly.

## 1. Go to the repo

```bash
cd /Users/mitchelwatson/Projects/Mitchopolis/evidence_engine
```

## 2. First-time setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## 3. Check local config

Expected local file:

```bash
/Users/mitchelwatson/Projects/Mitchopolis/evidence_engine/.env
```

Typical variables:

```bash
DATABASE_URL=...
MONGO_URI=...
LOG_LEVEL=INFO
EXPORT_PATH=/Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/exports
```

## 4. Run the API

From `evidence_engine`:

```bash
.venv/bin/python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

The API should come up at:

```bash
http://localhost:8000
```

## 5. Quick health checks

In another terminal:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/version
```

Expected health response:

```json
{"status":"ok"}
```

## 6. Run tests

```bash
cd /Users/mitchelwatson/Projects/Mitchopolis/evidence_engine
.venv/bin/python -m pytest -q
```

Full local check:

```bash
bash scripts/full_check.sh
```

## 7. Smoke test the main evidence endpoint

With the API running:

```bash
cd /Users/mitchelwatson/Projects/Mitchopolis/evidence_engine
bash scripts/curl_process_evidence.sh
```

## 8. Batch ingest a folder

Source-preserving legal-file intake:

```bash
cd /Users/mitchelwatson/Projects/Mitchopolis/evidence_engine
.venv/bin/python scripts/case_intake.py \
  --case-id BCSC_138865_Watson_v_McClean \
  --source-folder /path/to/legal-files
```

This writes copied files, hashes, extracted text, a manifest, a timeline draft, a proof-gap report, dashboard JSON, and a ZIP under `/Users/mitchelwatson/Projects/Mitchopolis/output/`.

For a slower scanned-PDF OCR pass, add `--ocr-scanned-pdfs`.
For corrected OCR text, add `--ocr-text-dir /path/to/text --prefer-ocr-sidecar`.

For an exact-file package:

```bash
.venv/bin/python scripts/case_intake.py \
  --case-id BCSC_138865_Watson_v_McClean \
  --source-file /path/to/agreement.pdf \
  --source-file /path/to/consent-order.pdf
```

```bash
cd /Users/mitchelwatson/Projects/Mitchopolis/evidence_engine
.venv/bin/python scripts/batch_ingest_folder.py \
  --case-id BCSC_138865_Watson_v_McClean \
  --folder /Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/inbox
```

Single-file example:

```bash
.venv/bin/python scripts/batch_ingest_folder.py \
  --case-id BCSC_138865_Watson_v_McClean \
  --folder /Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/inbox \
  --file "OFW_Messages_Report_2026-01-26_07-24-21 (1).pdf"
```

## 9. Start the inbox watcher

```bash
cd /Users/mitchelwatson/Projects/Mitchopolis/evidence_engine
CASE_ID=BCSC_138865_Watson_v_McClean \
TAGS="our-family-wizard,messages" \
bash scripts/watch_inbox_start.sh
```

Stop it:

```bash
bash scripts/watch_inbox_stop.sh
```

Logs:

```bash
tail -f /Users/mitchelwatson/Projects/Mitchopolis/evidence_engine/logs/watch_inbox.log
```

## 10. Daily workflow

1. Start the API.
2. Drop files into `/Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/inbox/`.
3. Run batch ingest or start the watcher.
4. Fetch timeline data from `GET /api/evidence/timeline/{case_id}`.
5. Pull exports from `/Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/exports/`.

## 11. Common fixes

Port 8000 busy:

```bash
lsof -i :8000
kill -9 <PID>
```

Wrong Python/venv:

```bash
.venv/bin/python -V
.venv/bin/python -m pytest -q
```

OCR problems:

```bash
.venv/bin/python -m pip list | grep -i pillow
.venv/bin/python -m pip list | grep -i tesseract
```

## 12. Main endpoints

```text
GET  /health
GET  /version
POST /upload
POST /api/evidence/process
POST /api/evidence/ingest
GET  /api/evidence/export
GET  /api/evidence/timeline/{case_id}
```
