# Evidence Engine Codex Instructions

## Project

- This repository is the Mitchopolis Evidence Engine: a Python/FastAPI service for evidence ingestion, OCR, classification, timeline generation, and export packaging.
- Canonical repository path: `/Users/mitchelwatson/Projects/Mitchopolis/evidence_engine`.
- Canonical evidence root: `/Users/mitchelwatson/Projects/Mitchopolis/parenting_evidence`.
- Treat home-directory shadow workspace paths as stale unless the user explicitly says otherwise.
- Main application code lives in `src/`.
- Tests live in `tests/`.
- Operational scripts live in `scripts/`.
- Local runtime logs, exports, virtual environments, `.env`, and generated artifacts are not source code.

## Working Mode

- Start code work by checking the Git status and reading the relevant files before editing.
- If the user does not name a mode, infer it conservatively:
  - failing tests or regressions: Stabilization
  - explicit new behavior: Feature
  - cleanup without behavior change: Refactor
  - review or audit: Review
  - docs-only changes: Docs
- Keep each task scoped to the requested outcome. Do not bundle unrelated refactors, dependency changes, or cross-service edits into a narrow request.
- If a requested change affects API contracts used by `../legal_ai_engine/`, `_core/`, or `../parenting_evidence/`, call that out and update tests or docs for the contract change.

## Local Environment

- Prefer the existing local virtual environment at `.venv/`.
- Do not recreate virtual environments, change environment variables, or add `PYTHONPATH` workarounds unless the user explicitly asks.
- Do not expose `.env` contents. Treat database URLs and case configuration as secrets.
- Default API target is `http://localhost:8000`.

## Commands

- Default test command: `.venv/bin/python -m pytest -q`.
- For broader verification, use the documented scripts only when they match the current environment. If a script expects `venv/` while this checkout has `.venv/`, report that mismatch instead of recreating the environment.
- To run the app directly from the repo, prefer the module/app entrypoint documented by the project, such as `uvicorn src.main:app --reload --host 0.0.0.0 --port 8000`.
- For route, export, watcher, OCR, or ingestion changes, add or update focused tests in `tests/` and run the narrow test first, then the full suite when practical.

## Evidence Semantics

- Preserve originals. Evidence processing should read, copy, hash, classify, and export; it should not destructively rewrite source evidence.
- Preserve provenance in generated outputs: case ID, source path, extraction method, timestamps, hash, classification confidence, and any warnings.
- For document search or recovery tasks, search both filenames and extracted content. Use PDF/DOCX extraction tools when available, but treat filenames, paths, ZIP listings, and metadata as first-class evidence when text extraction is weak.
- Normalize identifiers before matching, especially court or file numbers such as `138865`, because underscores and punctuation can break naive word-boundary checks.
- When the user asks for ordered or batch-preserved evidence, keep download/import grouping and date metadata visible in the result.

## Exports And Manifests

- Evidence exports should be deterministic, inspectable, and ready to hand off.
- Deduplicate exact copies by content hash, but keep a manifest row for every original source path.
- Verify generated ZIPs or bundles before delivery.
- Keep category names and folder order stable unless the user asks for a new taxonomy.

## Repository Hygiene

- Do not commit or package `.env`, `.venv/`, `venv/`, logs, caches, raw exports, or temporary folders unless the user explicitly asks.
- Follow the workspace Git guidance: work on feature or dev branches, keep commits small, and use conventional commit messages when committing.
- Update `README.md`, `docs/export_contract.md`, or `docs/run_cheat_sheet.md` when commands, endpoints, export fields, or operational workflows change.
