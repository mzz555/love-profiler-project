---
name: love-profiler-architecture
description: Use when adding, moving, refactoring, or reviewing any code in the love-profiler project (the 抖音 love-personality assessment app — FastAPI backend in love-profiler/app + 抖音 miniprogram frontend). Apply whenever deciding which layer/file new backend code belongs to, touching the scoring_engine / report_writer dual engines, adding a service or api route, writing a Supabase migration, splitting an oversized file, or renaming a module. This encodes THIS project's concrete layering, dependency directions, and hard constraints — consult it alongside the general python-architecture skill.
---

# love-profiler architecture conventions

This is the project-specific companion to the general `python-architecture` skill. The general skill gives you the principles (the Dependency Rule, cohesion, DI, etc.); this file gives you the *concrete map of this codebase* so a change lands in the right place and obeys the directions that already hold here. When the two ever conflict, the actual code wins — verify against the tree before trusting any description, including this one (the project has a known history of doc/code drift).

## The real layer map (verified from imports, not just docs)

Backend lives in `love-profiler/app/`. Observed, enforced import directions:

```
api/        (entrypoints: routes, WS, admin)
  │  imports → agents, services, schemas, models, middleware, database, config, limiter
  ▼
agents/     scoring_engine.py (pure Python, NO LLM) , report_writer.py (LLM)
  │  imports → services (llm_client, report_quality_gate), schemas
  ▼
services/   TWO sub-roles, don't conflate them:
  ├─ infrastructure services: llm_client, llm_logger, supabase_client, token_quota,
  │     access_control  → import models, config, database, other infra services
  └─ orchestration services: report_writer_runner, report_audit
        → import AGENTS (e.g. report_writer_runner imports agents.report_writer)
  ▼
models/     user, assessment, order, ai_call_log, ...  → import database (Base) only
  ▼
database.py / config.py / limiter.py / middleware/auth.py   (foundation; import config at most)
```

**The non-obvious bit that trips people up:** `services/` is not purely "below" `agents/`. Infrastructure services (`llm_client`) are imported *by* agents; orchestration services (`report_writer_runner`) import *agents* to schedule them. So when you add a service, first decide which sub-role it is — an infra adapter (gets used by agents) or an orchestrator (drives agents). Putting an orchestrator's logic into an infra service, or vice-versa, creates the exact cycle this layout avoids.

**Hard invariants:**
- `agents/scoring_engine.py` makes **no LLM call** and no DB call — pure deterministic scoring. Keep it that way; it's what makes scoring testable and cheap.
- `models/` import only `database.Base`. Never put business logic or I/O orchestration in a model.
- Foundation modules (`config`, `database`, `limiter`, `middleware`) never import `api`/`agents`/`services`.

## Where does new backend code go? (decision table)

| You're adding… | It goes in… | Because |
|---|---|---|
| A new HTTP/WS endpoint | `api/<feature>.py`, registered in `main.py` | entrypoints translate the outside world only |
| Deterministic scoring/diagnosis logic | `agents/scoring_engine.py` (or a helper it imports) | the pure-Python engine; no LLM/DB |
| LLM report-generation logic | `agents/report_writer.py` | the LLM engine |
| Background scheduling that drives an agent | an **orchestration** service (`services/*_runner.py`) | orchestrators may import agents |
| A wrapper around an external system (LLM, Supabase, quota) | an **infrastructure** service | adapters agents/api depend on |
| A new DB table | a `models/<table>.py` + register in `main.py` (business table) **or** a Supabase migration (config/question tables) | see migration rule below |
| A request/response data shape | `schemas/` (Pydantic) | typed contracts crossing the api boundary |
| Pure cross-cutting helper | name it for its concept, place near its sole user | avoid a `utils.py` dumping ground |

## Hard project constraints (from CLAUDE.md — these are non-negotiable here)

**500-line file ceiling.** No code file (`.py/.js/.ts/.html/.ttss/.ttml`) exceeds 500 lines. If a new file will exceed it, split into modules *before* writing. If editing a file already over 500 lines, propose a split and get sign-off before adding more. Exceptions: third-party/generated files, migration SQL, lock files, single-file HTML reports under `docs/`. When unsure if something is an exception, ask.

**Large writes in batches.** Don't emit more than ~150 lines in a single Write/Edit — split into multiple logical-block writes. This guards against long-response API drops.

**One migration file = one table.** Supabase migrations in `supabase/migrations/` are named `{YYYYMMDD}_{action}_{table}.sql` and each creates/alters exactly one table. A multi-table change becomes multiple migrations (same date sorts naturally). Don't retro-split already-applied historical files.

**Business tables vs. config tables.** `users / assessments / orders / ai_call_logs` and similar are SQLAlchemy-managed (auto-created at startup, registered in `main.py`). `questions` + the `base_*` static config tables are Supabase-migration-managed. Put a new table on the correct side.

## Renaming a module: the seven-layer sweep

This project has a documented history of half-finished renames (Agent A/B → scoring_engine/report_writer). When you rename an artifact, a filename + import change is **not** enough. Sweep all seven:

1. filename(s) and the package `__init__` if it re-exports
2. every `import` / `from app...` reference
3. docstrings and inline comments naming the old thing
4. log tags / logger names / metric labels
5. exception class names and their message text (`AgentAError → ScoringError`)
6. README.md, CLAUDE.md, and `docs/` references
7. test file names, test function names, and any mock/patch *target paths* (a stale patch path passes silently then breaks later)

**Deliberate exceptions that must stay:** the `ai_call_logs.agent` column keeps the literal strings `"agent_a"` / `"agent_b"` (historical data + admin filters depend on them). The file `docs/agent-b-system-prompt.md` keeps its name (code paths reference it). Don't "fix" these.

## Frontend (miniprogram) note

`love-profiler/miniprogram/` is the 抖音 miniprogram (TTML/TTSS/JS), not Python — the layering above doesn't apply, but the 500-line ceiling and batched-write rules do. Pages live under `pages/<name>/`. The real page set has drifted from older docs; check `miniprogram/app.json` for the authoritative page list before assuming.

## Before you commit

Per project rule: read the *full* `git status` including untracked files, and classify every untracked path (add core code under `app/`/`miniprogram/`/`static/`/`docs/`/`supabase/`/`scripts/`; gitignore local tooling and logs; never commit secrets). Don't rely on `git add -u` — it silently skips new files.
