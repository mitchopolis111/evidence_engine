# Mitchopolis Master Cheat Sheet (v1.0)

This cheat sheet defines the mandatory operating rules, daily workflows, and
guardrails for the Mitchopolis Legal Automation System.

Failure to follow these rules is the primary cause of drift, regressions, and
lost momentum.

---

## Daily Session Startup & Shutdown Checklist (No-Drift)

This checklist is mandatory for every development session.
If skipped, the session is considered invalid.

---

### Session Startup (30 seconds — before touching code)

```
Session Startup
Project:
Mode: [Stabilization | Feature | Refactor | Review]
Single Outcome:
Agents allowed: [None | Local | Background | Cloud]
Code modification allowed: [No | Tests only | Worktree only]
Known-green baseline: [commit hash or “current main”]
```

Rules:
- One session = one mode
- One session = one concrete outcome
- If any field is unclear → STOP and clarify before proceeding

---

### During-Session Rules (Hard Constraints)

- Agents execute; humans decide
- Tests validate behavior, not internal structure
- Known-green history beats assumptions
- Isolation before automation
- Never “fix multiple things while you’re here”

---

### Drift Detection (Immediate Stop Conditions)

Stop the session immediately if you:
- Recreate `.venv`
- Run `.py` files directly
- Modify production code during test triage
- Let an agent expand scope beyond intent
- Mix modes (e.g., stabilization + feature)

Restart with a fresh Session Startup block.

---

### Session Shutdown (Mandatory)

Complete before closing VS Code or Chat:

```
Session Shutdown
What changed:
What is now stable:
What remains broken or deferred:
Next single action:
```

If this is not completed, context **must not** be trusted next session.

---

## No-Drift Operating Rules (Mandatory)

The following rules override default Copilot and agent behavior for this repository.

These rules are higher priority than convenience, speed, or suggestions from tools.

### Scope Enforcement
- No changes outside the declared Session Scope
- No production code edits during Stabilization mode
- Tests may adapt to canonical behavior; production code does not

### Environment Discipline
- Exactly one virtual environment: `.venv`
- Never recreate `.venv` unless the suite is red and scoped
- Never use PYTHONPATH hacks or editable installs

### Execution Discipline
- Never execute `.py` files directly
- Allowed commands only:
  - `pytest -q`
  - `python -m src.main`
  - `./scripts/run_evidence_api_dev.sh`

Violation of any rule requires stopping the session and restarting cleanly.

---

## Test Failure Triage (No-Drift Rule)

Trigger: Any test failure after a previously green state.

---

### Step 1 — Classify the Failure (Do NOT fix yet)

Ask exactly one question:

**Is this a test-contract failure or a system failure?**

| Signal | Classification |
|------|----------------|
| Import errors (`ModuleNotFoundError`, `cannot import name`) | ❌ System / environment |
| HTTP 500 instead of expected response | ⚠️ Likely test mismatch |
| Assertion on content or structure | ⚠️ Test contract |
| Same test passed in earlier commit | ⚠️ Test regression |
| Multiple unrelated tests failing | ❌ Environment drift |

If classification is unclear → STOP and inspect git history.

---

### Step 2 — Check Known-Green History (Required)

```bash
git log --oneline -- <suspect_file>
git show <known_green_commit>:<file_path>
```

Rules:
- Known-green behavior is canonical
- Tests adapt unless a feature change was intentional

---

### Step 3 — Scope Discipline During Triage

- ❌ Do NOT modify router
- ❌ Do NOT modify models
- ❌ Do NOT modify utilities unless explicitly scoped
- ✅ Modify tests only to reflect existing behavior

If production code changes are required → stop and re-scope.

---

### Step 4 — Validate

```bash
pytest -q <target_test>
pytest -q
```

Expected:
- Target test passes
- Full suite returns green
- No new failures

---

### Step 5 — Lock the Fix

```bash
git commit -m "test: align <test_name> with canonical behavior"
```

No commit = no closure.

---

### Triage Anti-Patterns (Hard Stop)

- Adding PYTHONPATH hacks
- Recreating `.venv`
- Editing production code to satisfy tests
- Accepting Copilot environment advice during stabilization