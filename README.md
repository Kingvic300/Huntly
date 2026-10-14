# Huntly

**A private, open-source desktop job-hunting assistant that runs entirely on your machine.**

Huntly discovers relevant vacancies from sources you choose, ranks them against your
professional profile, generates tailored CVs and cover letters from facts you entered,
and prepares application emails as Gmail drafts that **you must explicitly approve
before anything is sent**. A daily digest lands in your own inbox.

- **Local-first.** A native desktop window (Tauri) talking to a local Python core over
  `127.0.0.1`. Your data lives in one folder on your computer.
- **Bring your own keys.** Google OAuth client, X API bearer token and Groq API key are
  entered by you during onboarding and encrypted at rest (AES-256-GCM, Argon2id). The
  maintainers have no server, no copy of your keys and no way to decrypt them.
- **No telemetry.** No analytics, crash reporting, update pings or remote logging.
- **Approval gate.** Application emails are hashed when you approve them; any edit
  invalidates the approval, approvals expire, and background jobs have no code path to send.
- **Never invents content.** CVs and letters are assembled only from your profile. Optional
  AI wording is discarded automatically if it mentions anything that is not in your profile.

Licensed under [Apache-2.0](LICENSE).

---

## Contents

- [Features](#features)
- [Install (Linux / Kali)](#install-linux--kali)
- [First run](#first-run)
- [Credentials you may need](#credentials-you-may-need)
- [Job sources](#job-sources)
- [Development](#development)
- [Architecture](docs/ARCHITECTURE.md) · [Local API](docs/API.md) · [Security](SECURITY.md)

## Features

| Screen | What it does |
| --- | --- |
| **Today** | A one-line briefing, your pipeline at a glance, strongest leads, and a "Needs you" list (emails to approve, follow-ups due, failing sources, profile gaps). |
| **Discover** | Keyboard triage (<kbd>J</kbd>/<kbd>K</kbd> move, <kbd>S</kbd> shortlist, <kbd>D</kbd> dismiss, <kbd>A</kbd> apply, <kbd>O</kbd> open). Every job shows a heat meter and an explainable score breakdown. Prompt-injection attempts in postings are flagged. |
| **Applications** | A board by stage. Each application walks you through making an ATS-friendly CV and cover letter, writing the email, and approving it, with an ATS readiness report and notes. |
| **Approvals** | The email exactly as the recipient will see it, a checklist you tick before approving, time-limited approval, Gmail drafts, reply status and follow-ups. |
| **Profile** | Import your existing CV (PDF/Word, parsed locally), then edit every section: contact details including LinkedIn, GitHub and website, experience, education, projects and preferences. Plus your file library. |
| **Sources** | RSS/Atom, Greenhouse, Lever, Remotive, Arbeitnow, company career pages (schema.org `JobPosting`), X recent search. Health, last run and errors per source. |
| **Insights** | Found vs applied over time, match distribution, where applications stand, jobs per source, demand for your skills. |
| **Settings** | Search interval, digest time (Africa/Lagos), reply tracking and follow-up timing, AI options, approval expiry, accounts and keys, vault, privacy, activity log. |

The window has a native menu bar (File / Edit / Go / Help with keyboard shortcuts) and a
system-tray icon (show, search now, quit). Global search: <kbd>Ctrl</kbd>+<kbd>K</kbd>.

### Your CV, imported and tailored

- **Import:** upload the CV you already have. Huntly extracts the text on your computer
  (pypdf / python-docx) and maps it to profile fields with rules, so every value comes from
  your document. You review each field before anything is saved.
- **Tailor:** for each job, skills and achievements the posting asks for move to the top.
  With Groq enabled, the summary and cover letter can be reworded for the job; any AI
  wording that mentions something not in your profile is discarded automatically.
- **ATS-friendly:** one column, no tables, images or text boxes, standard headings
  (Summary, Skills, Work Experience, Education), contact details and LinkedIn as plain text,
  real selectable text, PDF metadata and a file name with your name in it.
- **ATS report:** how many of the job's keywords your CV covers, which ones you're missing
  (shown, never added for you), and a format checklist.

### Replies and follow-ups

Huntly does **not** track whether emails were opened. That requires a tracking image served
from a public server, which a local app doesn't have; it is also unreliable (mail clients
pre-load images) and hurts deliverability. Instead:

- **Reply tracking:** every two hours Huntly reads the *sender headers* of the Gmail threads
  your applications started (`gmail.metadata` scope; message bodies are never read) and tells
  you when an employer replies, so you can update the stage.
- **Reply sorting (optional, off by default):** turn on "Read replies to sort them" and Huntly
  also opens replies in your application threads (needs `gmail.readonly`) and checks them on
  your computer for interview, rejection or offer wording, then suggests the stage. The reply
  text is never stored or sent anywhere, and you always confirm the stage yourself.
- **Follow-ups:** after a configurable number of days with no reply (default 7), Huntly
  suggests a short follow-up in the same thread. It goes through the same approval gate as
  every other email. At most two follow-ups per application.

## Install (Linux / Kali)

### From a release package

Download the file for your system from the
[latest release](https://github.com/Kingvic300/Huntly/releases/latest) and check it against
the SHA-256 shown on the release page.

**Linux (Debian, Ubuntu, Kali)**

```bash
sudo apt install ./Huntly_0.1.1_amd64.deb
```

Or, on any distribution, make the AppImage executable and run it:
`chmod +x Huntly_0.1.1_amd64.AppImage && ./Huntly_0.1.1_amd64.AppImage`.

**macOS** (`aarch64` for Apple silicon, `x64` for Intel): open the `.dmg` and drag Huntly to
Applications. The app is not code-signed yet, so the first time, right-click it and choose
**Open**, or run `xattr -dr com.apple.quarantine /Applications/Huntly.app`.

**Windows**: run `Huntly_0.1.1_x64-setup.exe`. It is not code-signed yet, so SmartScreen may
warn you: choose **More info → Run anyway**.

### Build from source

Requirements: Python ≥ 3.11, Node.js ≥ 20, Rust ≥ 1.77 and the Tauri system libraries:

```bash
sudo apt install -y libwebkit2gtk-4.1-dev libgtk-3-dev libsoup-3.0-dev librsvg2-dev \
  libayatana-appindicator3-dev build-essential libssl-dev patchelf file

git clone https://github.com/Kingvic300/Huntly.git huntly && cd huntly
scripts/setup-dev.sh        # Python venv + npm packages
scripts/test.sh             # all automated tests
scripts/build-linux.sh      # produces release/*.deb and release/*.AppImage
```

`scripts/build-linux.sh` first freezes the Python core into a single executable with
PyInstaller and bundles it inside the Tauri package as a sidecar, so the installed app
needs no Python.

macOS and Windows installers are built by GitHub Actions (`.github/workflows/release.yml`)
on each platform whenever a `v*` tag is pushed. To build one yourself on that platform, run
`scripts/build-sidecar.sh` and then `npx tauri build` in `desktop/`.

## First run

1. **Welcome** explains the local-only, open-source model and shows where data is stored
   (`~/.local/share/huntly` on Linux).
2. **Master password** creates your encrypted vault. Optionally let the OS keychain
   (libsecret / GNOME Keyring / KWallet) unlock it automatically on this device.
3. **Your API keys** — add any of the credentials below. Each is encrypted before it is
   written to disk.
4. **Gmail** — opens Google's consent screen in your browser using *your* OAuth client.
5. **Profile** — basics now; the full editor lives in CV Library.

Nothing in Huntly works against fake or sample data: until you add sources, the job list is
empty, and until you connect Gmail, digests and sending are disabled.

## Credentials you may need

All optional — enable only what you use.

| Credential | Used for | How to get it |
| --- | --- | --- |
| Google OAuth client (Desktop app JSON) | Gmail drafts, approved sends, daily digest, reply tracking | Google Cloud Console → create project → enable **Gmail API** → OAuth consent screen (External, add yourself as test user) → Credentials → *OAuth client ID* → **Desktop app** → download JSON. Scopes requested: `gmail.compose` (drafts and sending) and `gmail.metadata` (message headers only, for reply tracking). Huntly cannot read email content. |
| X API bearer token | X recent-search source | developer.x.com → project/app → *Bearer Token*. Requires an access tier that includes `GET /2/tweets/search/recent`. |
| Groq API key | Optional AI fit notes and cover-letter wording | console.groq.com → API Keys. |

## Job sources

| Type | Endpoint | Notes |
| --- | --- | --- |
| RSS / Atom | any feed URL | Many boards publish feeds. |
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{board}/jobs` | Public Job Board API. |
| Lever | `api.lever.co/v0/postings/{company}` | Public Postings API. |
| Remotive | `remotive.com/api/remote-jobs` | Public API; links back to Remotive as required. |
| Arbeitnow | `arbeitnow.com/api/job-board-api` | Public API. |
| Career page | any URL | Reads only schema.org `JobPosting` JSON-LD the site publishes. No scraping, no JS. |
| X recent search | `api.x.com/2/tweets/search/recent` | Your bearer token; retweets excluded. |

All fetches go through an SSRF guard (http/https only, public addresses only, re-checked on
every redirect, size and time limits). Respect each site's terms of service.

## Development

```bash
scripts/setup-dev.sh
scripts/dev.sh              # tauri dev: Vite on :1420 + native window; core spawned from .venv
```

Run the core alone: `HUNTLY_API_TOKEN=dev .venv/bin/python -m huntly --port 8765`
(set `HUNTLY_DATA_DIR` to use a throwaway data folder).

Repository layout:

```
core/        Python core (FastAPI, SQLAlchemy, Alembic, APScheduler)
  huntly/    application package
  tests/     pytest suite (all external services mocked)
  packaging/ PyInstaller spec for the sidecar
desktop/     Tauri shell (Rust) + React/TypeScript/Tailwind UI
scripts/     setup, dev, test and build scripts
docs/        architecture and API reference
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Report vulnerabilities privately as described in
[SECURITY.md](SECURITY.md).

## Optional: Docker (advanced)

`docker-compose.yml` runs only the headless core (no UI) for people who want to script
against the local API. It binds to `127.0.0.1` on the host and needs `HUNTLY_API_TOKEN`.
The desktop app does not need Docker.
