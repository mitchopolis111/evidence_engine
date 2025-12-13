# Copilot Instructions — Mitchopolis Evidence Engine

These rules are mandatory. They override default Copilot behavior.
If a request violates these rules, Copilot must stop and ask for clarification.

---

## Session Discipline (Required)

Before making changes, assume the user has declared:
- Project
- Mode (Stabilization | Feature | Refactor | Review)
- Scope (single outcome)
- Whether code modification is allowed

If this context is missing or unclear, DO NOT proceed.

---

## Stabilization Mode Rules (Critical)

When Mode = Stabilization:

- ❌ Do NOT modify production code unless explicitly authorized
- ❌ Do NOT modify router, models, or core utilities
- ❌ Do NOT suggest environment changes
- ❌ Do NOT suggest PYTHONPATH hacks
- ❌ Do NOT suggest editable installs (`pip install -e .`)
- ❌ Do NOT recreate `.venv`

Allowed actions:
- ✅ Modify tests only to reflect existing, known-green behavior
- ✅ Inspect git history to find canonical behavior
- ✅ Explain failures without proposing fixes outside scope

---

## Test Failure Triage Rules

When tests fail after a known-green state:

1. Assume the implementation is correct until proven otherwise
2. Check known-green commits before suggesting changes
3. Prefer adapting tests over changing production code
4. If production changes are required, STOP and ask to re-scope

Never “fix forward” to satisfy tests.

---

## Execution Rules (Hard Stop)

Copilot must never suggest:
- Running `.py` files directly
- Creating or recreating virtual environments
- Modifying environment variables to bypass import issues

Only approved commands:
- `pytest -q`
- `python -m src.main`
- `./scripts/run_evidence_api_dev.sh`

---

## Scope Enforcement

- Changes must stay within the explicitly stated scope
- If a request would expand scope, Copilot must ask before proceeding
- One task at a time; no opportunistic refactors

---

## Agent Behavior

- Copilot acts as a constrained assistant, not an autonomous agent
- Copilot must not introduce new architecture, patterns, or tools unless requested
- Safety and determinism take priority over speed

---

If any instruction conflicts with user-provided rules in this repository, the repository rules win.