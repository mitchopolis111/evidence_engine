# Evidence Engine utility scripts

This folder contains helper scripts for:

- Database migrations
- Bulk evidence processing
- Export utilities
- Development utilities

## Available Scripts

- `curl_process_evidence.sh` — Fires a sample `/api/evidence/process` request using `sample_evidence_payload.json`.
- `batch_ingest_folder.py` — Batch-ingests a folder of evidence files by calling the API. Example: `python scripts/batch_ingest_folder.py --case-id BCSC_138865 --folder ~/Mitchopolis/parenting_evidence/inbox`.
