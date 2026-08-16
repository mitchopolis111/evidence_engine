# Mitchopolis Evidence Engine

Python/FastAPI service responsible for:

- Ingesting and classifying evidence
- Running OCR on documents
- Building timelines
- Exporting evidence packages

---

## Scope and Boundaries

- This service handles OCR, classification, and timeline generation only.
- Evidence storage, search, and legal API access live in `../legal_ai_engine/`.

## Local Development

### Prerequisites

- Python 3.9+ (using local venv at `/Users/mitchelwatson/Projects/Mitchopolis/evidence_engine/.venv`)
- Uvicorn installed in the venv
- Dependencies listed in `requirements.txt`

### Setup (One-Time)

```bash
cd /Users/mitchelwatson/Projects/Mitchopolis/evidence_engine
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### Starting the API (Dev Mode)

From the `evidence_engine` folder:

```bash
.venv/bin/python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Or from the Mitchopolis root:

```bash
cd /Users/mitchelwatson/Projects/Mitchopolis
./run_evidence_api_dev.sh
```

The API will be available at `http://localhost:8000`.

---

## Project Structure

```
evidence_engine/
├── README.md
├── requirements.txt      # Python dependencies (currently minimal, to be expanded)
├── .venv/                # Python virtual environment (local only, not in Git)
├── src/
│   ├── __init__.py
│   ├── main.py          # FastAPI app entry point
│   ├── classifier.py    # Evidence classification logic
│   ├── db.py            # Database connection and utilities
│   ├── ocr.py           # OCR pipeline (document processing)
│   ├── router.py        # API route definitions
│   └── timeline.py      # Timeline building and analysis
├── tests/               # Unit and integration tests (directory exists)
├── logs/                # Runtime logs (local only, not in Git)
└── scripts/             # Utility scripts (to be created)
```

---

## Key Endpoints

### Implemented

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/health` | Service health check |
| `POST` | `/api/evidence/process` | Upload file, extract text (OCR), classify, and store timeline |
| `POST` | `/api/evidence/ingest` | Ingest evidence (currently forwards to `/process`) |
| `GET` | `/api/evidence/export` | Export an approved evidence folder as a deterministic ZIP |
| `GET` | `/api/evidence/timeline/{case_id}` | Fetch timeline for a case (MongoDB if configured; in-memory fallback) |

Each processed timeline entry includes `extraction_method` and a structured
`processing_warnings` list. Missing files, unsupported media, empty extraction,
OCR availability, per-page OCR failures, and PDF page limits are reported
without exposing exception text or silently claiming that media was read.

Timeline dates are parsed by the single canonical `src.timeline` module. ISO
dates, English month-name dates, and court-registry dates such as
`16-NOV-2023` are normalized to `YYYY-MM-DD`. Invalid or absent dates remain
unset; the service does not substitute the current date.

### Planned

| Method | Endpoint | Purpose |
|--------|----------|---------|

---

## Running Tests

```bash
.venv/bin/python -m pytest -q
```

---

## Workflow: Daily Evidence Processing

Source-preserving case intake:

```bash
.venv/bin/python scripts/case_intake.py \
  --case-id BCSC_138865_Watson_v_McClean \
  --source-folder /path/to/legal-files
```

This creates a copied-file package, manifest, extracted text, timeline draft, proof-gap report, dashboard JSON, and ZIP under `/Users/mitchelwatson/Projects/Mitchopolis/output/`.
Use `--ocr-text-dir /path/to/text --prefer-ocr-sidecar` when a corrected OCR sidecar should replace a weak embedded PDF text layer.

1. **Drop evidence** into `/Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/inbox/`
2. **Watcher triggers** (LaunchAgent monitors folder)
3. **Evidence Engine processes**:
   - Classifies evidence type
   - Runs OCR on documents
   - Builds timeline entries
   - File-based ingestion is idempotent (hash + upsert) to prevent duplicate entries
4. **Exports** to `/Users/mitchelwatson/Projects/Mitchopolis/exports/`

---

## Environment Variables

Create a `.env` file in the `evidence_engine` root (not committed to Git):

```bash
MONGO_URI=mongodb+srv://...
EVIDENCE_SOURCE_FOLDER=/Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence/text_logs
EVIDENCE_EXPORT_ALLOWED_ROOTS=/absolute/additional/evidence/root
```

`EVIDENCE_SOURCE_FOLDER` is the default source when `/api/evidence/export` is
called without a `folder` query parameter, and it is also treated as an approved
export root. The canonical `parenting_evidence` folder is always approved.
Additional absolute roots can be listed in `EVIDENCE_EXPORT_ALLOWED_ROOTS`,
separated by the platform path separator (`:` on macOS).

The export endpoint rejects relative paths, paths outside the approved roots,
and sources containing symbolic links or special files. Generated archives are
written under `/Users/mitchelwatson/Projects/Mitchopolis/exports/`. See
`docs/export_contract.md` for status codes and examples.

---

## Documentation

- Procedures and operational rules: `../docs/README.md`
- Architecture notes: `../docs/architecture/`

---

## Troubleshooting

### Module Not Found Errors
Ensure venv is activated:
```bash
.venv/bin/python -V
.venv/bin/python -m pytest -q
```

### Port Already in Use
If port 8000 is occupied:
```bash
lsof -i :8000
kill -9 <PID>
```

### OCR Failures
Check that tesseract and Pillow are installed:
```bash
.venv/bin/python -m pip list | grep -i tesseract
.venv/bin/python -m pip list | grep -i pillow
```

---

## Git Workflow

- **Branch**: Work on `feature/*` or `dev`, never directly on `main`
- **Commits**: Use conventional commit format (see `docs/best_practices_log_v1.md`)
- **Push**: After tests pass, push to `origin/dev` and create a PR

---

## Contributing

See `/Users/mitchelwatson/Projects/Mitchopolis/docs/best_practices_log_v1.md` for:
- Git standards & workflow
- Commit message conventions
- Multi-repo discipline rules
- Clean working-tree guidelines

---

## License

Internal use only. Mitchopolis 2025.
