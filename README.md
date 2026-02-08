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

- Python 3.9+ (using local venv at `~/Mitchopolis/evidence_engine/venv`)
- Uvicorn installed in the venv
- Dependencies listed in `requirements.txt`

### Setup (One-Time)

```bash
cd ~/Mitchopolis/evidence_engine
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Starting the API (Dev Mode)

From the `evidence_engine` folder:

```bash
source venv/bin/activate
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Or from the Mitchopolis root:

```bash
cd ~/Mitchopolis
./run_evidence_api_dev.sh
```

The API will be available at `http://localhost:8000`.

---

## Project Structure

```
evidence_engine/
├── README.md
├── requirements.txt      # Python dependencies (currently minimal, to be expanded)
├── venv/                 # Python virtual environment (local only, not in Git)
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
| `GET` | `/api/evidence/export` | Generate evidence export package |
| `GET` | `/api/evidence/timeline/{case_id}` | Fetch timeline for a case (MongoDB if configured; in-memory fallback) |

### Planned

| Method | Endpoint | Purpose |
|--------|----------|---------|

---

## Running Tests

```bash
source venv/bin/activate
pytest tests/ -v
```

---

## Workflow: Daily Evidence Processing

1. **Drop evidence** into `~/Mitchopolis/parenting_evidence/inbox/`
2. **Watcher triggers** (LaunchAgent monitors folder)
3. **Evidence Engine processes**:
   - Classifies evidence type
   - Runs OCR on documents
   - Builds timeline entries
4. **Exports** to `~/Mitchopolis/parenting_evidence/exports/`

---

## Environment Variables

Create a `.env` file in the `evidence_engine` root (not committed to Git):

```bash
DATABASE_URL=mongodb+srv://...
MONGO_URI=mongodb+srv://...
LOG_LEVEL=INFO
EXPORT_PATH=~/Mitchopolis/parenting_evidence/exports
```

---

## Documentation

- Procedures and operational rules: `../docs/README.md`
- Architecture notes: `../docs/architecture/`

---

## Troubleshooting

### Module Not Found Errors
Ensure venv is activated:
```bash
source venv/bin/activate
which python
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
pip list | grep -i tesseract
pip list | grep -i pillow
```

---

## Git Workflow

- **Branch**: Work on `feature/*` or `dev`, never directly on `main`
- **Commits**: Use conventional commit format (see `docs/best_practices_log_v1.md`)
- **Push**: After tests pass, push to `origin/dev` and create a PR

---

## Contributing

See `~/Mitchopolis/docs/best_practices_log_v1.md` for:
- Git standards & workflow
- Commit message conventions
- Multi-repo discipline rules
- Clean working-tree guidelines

---

## License

Internal use only. Mitchopolis 2025.
