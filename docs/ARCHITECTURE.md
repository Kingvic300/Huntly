# Architecture

```
┌──────────────────────────── Huntly desktop process (Tauri / Rust) ────────────────────────────┐
│  Native window (WebKitGTK)        Menu bar · System tray                                       │
│  React + TypeScript UI  ──IPC──▶  core_connection() → { base_url, token }                      │
│          │                                                                                     │
│          └── HTTP (127.0.0.1:<random port>, Bearer <per-launch token>) ──┐                     │
│                                                                          ▼                     │
│  Supervises child process ───────────────▶  huntly-core (Python sidecar)                       │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
                                             │ FastAPI routes  (api/)
                                             │ Services        (services/)
                                             │   collector · matching · documents · applications
                                             │   gmail · digest · llm · sources/*
                                             │ APScheduler     (scheduler.py, Africa/Lagos)
                                             │ Vault           (security/vault.py)
                                             ▼
                          ~/.local/share/huntly/
                            huntly.sqlite3   (SQLite, WAL, Alembic-migrated)
                            vault.json       (salt, KDF params, wrapped data key)
                            documents/       (generated and uploaded CVs/letters)
                            logs/core.log    (JSON, redacted, rotated)
```

## Processes

- **Shell (`desktop/src-tauri`)** picks a free loopback port and a 256-bit random token,
  starts the core (dev: `.venv/bin/python -m huntly`; release: bundled PyInstaller sidecar),
  hands `{base_url, token}` to the UI over Tauri IPC, and kills the core on exit. The core
  also exits if its parent disappears.
- **Core (`core/huntly`)** owns all state and logic. The UI never touches files or secrets
  directly.

## Data flow: discovery

`scheduler` (interval) or *Collect now* → `collector.collect_all` → for each enabled source,
`sources/*` fetch via `security.ssrf.safe_get` → `RawJob.normalized()` (HTML stripped, control
characters removed, injection heuristics) → dedupe by URL hash → `matching.score_job`
(deterministic, explainable) → optional Groq assessment for the top new jobs (blended 70/30)
→ stored → notification.

The company directory (`services/companies.py`) is a source of its own: each run it looks up a
few employer names from other sources on the hiring platforms (Greenhouse, Lever, Ashby,
SmartRecruiters, Recruitee), then checks the boards checked longest ago, a batch at a time
(`directory_batch_size`), and stores only jobs that pass `matching.matches_profile`.

## Data flow: applying

1. *Start application* creates an `Application` for a job.
2. *Generate* builds a tailored CV (profile facts re-ordered by relevance; optional Groq wording
   for the summary and for each achievement bullet, checked by `find_fabrications` and
   `bullet_fabrications`) and a cover letter (template from profile facts; optional Groq wording
   checked by `find_fabrications`). *Tailor for this job* in Discover runs steps 1 and 2 together.
3. *Prepare email* creates an `EmailApproval` (`pending`) with a content hash.
4. User edits (hash recomputed, approval reset), optionally saves a Gmail draft.
5. *Approve* requires `confirm=true` **and** the hash the UI displayed; stores `approved_hash`.
6. *Send* re-checks status, hash equality and the expiry window, then sends via Gmail
   `drafts.send`, updates statuses and writes the audit log.

## Scheduling

APScheduler `BackgroundScheduler` with `Africa/Lagos`: an interval job for collection and a
cron job for the digest. Jobs coalesce, never overlap, and run only while the app is open.
The first collection after start-up runs one interval after the last one, or about 20 seconds
after opening if that time has passed; finishing onboarding brings it forward to now.
If the vault is locked or Gmail is not connected, the digest is skipped with a notification.

## Database

SQLAlchemy 2 models in `models.py`; Alembic migrations in `migrations/versions` run
automatically at start-up. Tables: `secrets`, `settings`, `profile`, `sources`, `jobs`,
`documents`, `applications`, `email_approvals`, `audit_log`, `notifications`, `job_runs`.
