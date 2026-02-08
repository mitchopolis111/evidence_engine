# Evidence Engine utility scripts

This folder contains helper scripts for:

- Database migrations
- Bulk evidence processing
- Export utilities
- Development utilities

## Available Scripts

- `curl_process_evidence.sh` — Fires a sample `/api/evidence/process` request using `sample_evidence_payload.json`.
- `batch_ingest_folder.py` — Batch-ingests a folder of evidence files by calling the API. Example: `python scripts/batch_ingest_folder.py --case-id BCSC_138865 --folder ~/Mitchopolis/parenting_evidence/inbox`.
- `watch_inbox.py` — Polls an inbox and auto-ingests new files, then moves them to the case folder. Example: `python scripts/watch_inbox.py --case-id BCSC_138865_Watson_v_McClean --include-ext .pdf,.docx`.
