# Huntly

**A private, open-source desktop job-hunting assistant that runs entirely on your machine.**

Huntly discovers relevant vacancies from sources you choose, ranks them against your
professional profile, generates tailored CVs and cover letters from facts you entered,
and prepares application emails as Gmail drafts that **you must explicitly approve
before anything is sent**. A daily digest lands in your own inbox.

- **Local-first.** A native desktop window (Tauri) talking to a local Python core over
  `127.0.0.1`. Your data lives in one folder on your computer.
- **Bring your own keys.** Google OAuth client and Groq API key are
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
| **Discover** | Keyboard triage (<kbd>J</kbd>/<kbd>K</kbd> move, <kbd>S</kbd> shortlist, <kbd>D</kbd> dismiss, <kbd>A</kbd> apply, <kbd>O</kbd> open). Every job shows a match ring and an explainable score breakdown. Filter by remote (hybrid jobs never count as remote) and by seniority level, worked out from the title, the employer's own label, then the description (for example "5+ years of experience"). **Tailor for this job** starts the application and makes the CV and cover letter in one click. Prompt-injection attempts in postings are flagged. |
| **Applications** | A board by stage. Each application walks you through making an ATS-friendly CV and cover letter, writing the email, and approving it, with an ATS readiness report and notes. |
| **Approvals** | The email exactly as the recipient will see it, a checklist you tick before approving, time-limited approval, Gmail drafts, reply status and follow-ups. |
| **Profile** | Import your existing CV (PDF/Word, parsed locally), then edit every section: contact details including LinkedIn, GitHub and website, experience, education, projects and preferences. Plus your file library. |
| **Sources** | Remote job boards (Remotive, Remote OK, Himalayas, Jobicy, Arbeitnow) and a company directory, added for you on your first search. Plus RSS/Atom, single company boards (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, Workable, BambooHR, Breezy HR) and career pages (schema.org `JobPosting`). Health, last run and errors per source. |
| **Insights** | Found vs applied over time, match distribution, where applications stand, jobs per source, demand for your skills. |
| **Settings** | Search interval, digest time (Africa/Lagos), reply tracking and follow-up timing, AI options, approval expiry, accounts and keys, vault, privacy, activity log. |

There is no menu bar on Linux and Windows; every action is in the app and has a keyboard
shortcut (macOS keeps a minimal menu, which its copy and paste shortcuts need). A system-tray
icon offers show, search now and quit. Global search: <kbd>Ctrl</kbd>+<kbd>K</kbd>.

### Your CV, imported and tailored

- **Import:** upload the CV you already have. Huntly extracts the text on your computer
  (pypdf / python-docx) and maps it to profile fields with rules, so every value comes from
  your document. You review each field before anything is saved.
- **Tailor:** for each job, skills and achievements the posting asks for move to the top.
  With Groq enabled, the summary, achievement bullets and cover letter are reworded for the
  job; any AI wording that mentions something not in your profile is discarded automatically.
  Bullets are checked one by one: a reworded bullet may only use numbers, names and skills
  from the bullet it replaces, so facts never move between roles.
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
sudo apt install ./Huntly_0.3.4_amd64.deb
```

Or, on any distribution, make the AppImage executable and run it:
`chmod +x Huntly_0.3.4_amd64.AppImage && ./Huntly_0.3.4_amd64.AppImage`.

**macOS** (`aarch64` for Apple silicon, `x64` for Intel): open the `.dmg` and drag Huntly to
Applications. The app is not code-signed yet, so the first time, right-click it and choose
**Open**, or run `xattr -dr com.apple.quarantine /Applications/Huntly.app`.

**Windows**: run `Huntly_0.3.4_x64-setup.exe`. It is not code-signed yet, so SmartScreen may
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
| Google OAuth client (Desktop app JSON) | Gmail drafts, approved sends, daily digest, reply tracking | Google Cloud Console → create project → enable **Gmail API** → Google Auth Platform (OAuth consent screen): External, then **Audience → Test users → add your own Gmail address** → Credentials → *OAuth client ID* → **Desktop app** → download JSON. Recommended: on Audience click **Publish app** (no verification needed for personal use); in Testing mode Google expires the connection every 7 days. When connecting, Google warns the app is unverified; it is your own app, so choose Continue. If you see `Error 403: access_denied`, your address is not on the test-user list. Scopes requested: `gmail.compose` (drafts and sending) and `gmail.metadata` (message headers only, for reply tracking). Huntly cannot read email content. |
| Groq API key | Optional AI fit notes and cover-letter wording | console.groq.com → API Keys. |

## Job sources

| Type | Endpoint | Notes |
| --- | --- | --- |
| RSS / Atom | any feed URL | Many boards publish feeds. |
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{board}/jobs` | Public Job Board API. |
| Lever | `api.lever.co/v0/postings/{company}` | Public Postings API. |
| Remotive | `remotive.com/api/remote-jobs` | Public API; links back to Remotive as required. |
| Arbeitnow | `arbeitnow.com/api/job-board-api` | Public API. |
| Remote OK | `remoteok.com/api` | Public API; jobs link back to Remote OK and name it as the source, as its terms require. |
| Himalayas | `himalayas.app/jobs/api` | Public API; jobs link back to Himalayas. |
| Jobicy | `jobicy.com/api/v2/remote-jobs` | Public API; jobs link to the original Jobicy listing, as its terms require. |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{board}` | Public Job Postings API for companies hiring through Ashby. |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/{company}/postings` | Public Posting API. A job's full text is fetched only when its title fits your profile. |
| Recruitee | `{company}.recruitee.com/api/offers/` | Public careers-site API. |
| Workable | `www.workable.com/api/accounts/{company}` | Public careers-page API. Used by many Nigerian startups (Kuda, FairMoney, Renmoney). |
| BambooHR | `{company}.bamboohr.com/careers/list` | Public careers-page API (Chowdeck, Paga, Risevest). A job's full text is fetched only when its title fits your profile. |
| Breezy HR | `{company}.breezy.hr/json` | Public careers-page API (Busha). Full text comes from the posting page's schema.org `JobPosting` data, only for jobs whose title fits. |
| Career page | any URL | Reads only schema.org `JobPosting` JSON-LD the site publishes. No scraping, no JS. |

### Default sources

When you finish onboarding, Huntly searches straight away. That first search adds Remotive,
Remote OK, Himalayas and Jobicy (searching for the first target role in your profile),
Arbeitnow (remote jobs only) and the company directory. This happens once; edit or remove them
on the Sources page.

Huntly searches only while it is open. When you open it and the last search is older than your
search interval (60 minutes by default), a search starts about 20 seconds later.

### Company directory

The directory follows companies' own job boards on Greenhouse, Lever, Ashby, SmartRecruiters,
Recruitee, Workable, BambooHR and Breezy HR, from startups in Lagos to remote-first companies
anywhere:

- **Starter list:** about 540 boards with open jobs ship with the app, including Nigerian
  and other African employers (`core/huntly/assets/companies.json`, rebuilt with
  `scripts/build_company_seed.py`).
- **Grows by itself:** each search looks up a few employers that your other sources found and
  adds the ones with a public board. A job link that points at a hiring board adds that
  company too.
- **Your lists:** paste board links or `platform:name` entries on the Sources page, as many as
  you like.
- **Rotation:** each search checks the companies checked longest ago, 300 by default
  (50–2,000). The Sources page shows how often each company comes round.
- **Only matches are kept:** a job is stored when its title fits a target role or it names two
  of your skills, so thousands of companies don't flood your list.

A board that returns *not found* is turned off. Turn off any company you don't want.

All fetches go through an SSRF guard (http/https only, public addresses only, re-checked on
every redirect, size and time limits). Respect each site's terms of service.

We Work Remotely publishes RSS feeds (for example
`https://weworkremotely.com/categories/remote-programming-jobs.rss`); add them as an RSS source.
Some boards have no official API or feed, and their terms or `robots.txt` forbid automated
access, so Huntly does not support them: Glassdoor, and Jobberman (its `robots.txt` blocks
job pages and its API). Use their own email alerts for those boards.

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
