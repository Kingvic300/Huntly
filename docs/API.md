# Local API

Base URL `http://127.0.0.1:<port>/api`. Every request needs `Authorization: Bearer <token>`
and a loopback `Host` header. The desktop shell supplies both; nothing listens on other
interfaces. `GET /openapi.json` returns the machine-readable schema.

Status codes: `401` bad token · `403` non-loopback host · `423` vault locked ·
`400` validation/business rule · `404` not found · `409` conflict (e.g. collection running).

## System

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | DB, vault, scheduler status, timezone, data dir |
| GET | `/onboarding/status` | Vault state, keychain availability, credential presence |
| POST | `/vault/create` | `{password, use_keyring}` create vault |
| POST | `/vault/unlock` · `/vault/lock` | Unlock with `{password}` / lock |
| POST | `/vault/change-password` | `{old_password, new_password}` |
| POST | `/vault/keyring` | `{enabled}` store/remove data key in OS keychain |
| POST | `/onboarding/complete` | Mark onboarding finished |
| GET | `/credentials` | Names and *configured* flags only — values are never returned |
| PUT/DELETE | `/credentials/{name}` | `google_oauth_client`, `groq_api_key` |
| GET | `/gmail/status` · POST `/gmail/connect` · `/gmail/disconnect` · `/gmail/test` | Gmail OAuth |
| GET/PUT | `/settings` | Schedules, digest, Groq, approval window |
| GET | `/scheduler` | Scheduled jobs and recent runs |
| GET | `/notifications` · POST `/notifications/read-all` | In-app notifications |
| GET | `/audit` | Local audit log |
| GET | `/search?q=` | Global search |

## Jobs, sources, profile

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/jobs` | `q, status, min_score, source_id, remote, seniority (comma list of intern, entry, mid, senior, lead, manager), sort, limit, offset` |
| GET/PATCH | `/jobs/{id}` | Detail with score breakdown / `{status}` |
| POST | `/jobs/rescore` | Re-score all jobs |
| GET | `/sources/catalog` | Source types and their config fields |
| GET/POST | `/sources` | List / create `{kind, name, config, enabled}` |
| PATCH/DELETE | `/sources/{id}` | Update / remove |
| GET | `/companies?q=&limit=&offset=` | Company directory page plus totals by platform |
| POST | `/companies/import` | `{text}` board links or `platform:name` entries; returns added / already tracked / not recognised |
| PATCH | `/companies/{id}` | `{enabled}` turn a company on or off |
| POST | `/collect` | `{source_ids?}` start a collection run in the background |
| GET/PUT | `/profile` | Profile and completeness |

## Applications, approvals, documents, digest

| Method | Path | Purpose |
| --- | --- | --- |
| GET/POST | `/applications` | List / create `{job_id}` |
| GET/PATCH/DELETE | `/applications/{id}` | Detail / `{status, notes, contact_email}` / delete |
| POST | `/applications/{id}/documents` | `{format: pdf|docx, use_llm}` generate ATS-friendly CV + letter; returns the ATS report |
| POST | `/applications/{id}/email` | `{to?}` create pending approval |
| GET | `/approvals` · `/approvals/{id}` | List / detail with attachments |
| PATCH | `/approvals/{id}` | Edit (resets approval) |
| POST | `/approvals/{id}/draft` | Create/update Gmail draft (never sends) |
| POST | `/approvals/{id}/approve` | `{confirm: true, content_hash}` |
| POST | `/approvals/{id}/reject` | Reject |
| POST | `/approvals/{id}/send` | Send — only if approved, unchanged and unexpired |
| GET/POST | `/documents` | List / upload base CV (multipart `file`, `title`) |
| POST | `/documents/{id}/parse` | Read a CV into profile fields for review (local, nothing saved) |
| GET | `/documents/{id}/file` | Download |
| DELETE | `/documents/{id}` | Delete |
| GET | `/follow-ups` | Sent applications with no reply after the configured wait |
| POST | `/replies/check` | Check Gmail threads for replies now |
| POST | `/approvals/{id}/follow-up` | Write a follow-up (pending approval) in the same thread |
| POST | `/approvals/{id}/dismiss-follow-up` | Stop suggesting a follow-up for this email |
| GET | `/pipeline` | Stage counts for the pipeline summary |
| GET | `/digest/preview` | Subject, text and HTML of the next digest |
| POST | `/digest/send` | Send digest now (to your own address) |
| GET | `/analytics?days=` | Aggregates for charts |
