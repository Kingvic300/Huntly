# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Use GitHub's private vulnerability reporting ("Security" tab → "Report a vulnerability")
on this repository. Include affected version, reproduction steps and impact. We aim to
acknowledge reports within 5 working days and to publish a fix and advisory within 90 days,
crediting you unless you prefer otherwise.

Only the latest release receives security fixes.

## Threat model and design

Huntly is a single-user desktop application. It has **no server component**; the
maintainers never receive user data, keys or telemetry.

| Concern | Mitigation |
| --- | --- |
| Credentials at rest | AES-256-GCM per secret (secret name bound as associated data). Data key wrapped with a key derived from the master password via Argon2id (64 MiB, t=3, p=4). Files `0600`, data dir `0700`. Optional OS keychain storage of the data key, opt-in. |
| Credentials in logs | JSON log formatter redacts known token formats and every secret value loaded in the session. Tests assert no leakage. |
| Local API exposure | Binds to `127.0.0.1` only, random port, random per-launch bearer token passed via environment (not argv), loopback `Host` header check (DNS-rebinding defence), CORS limited to the Tauri origin. |
| Unintended sending | Emails require an explicit approval that records a SHA-256 hash of recipient, subject, body and attachments. Any edit resets it; approvals expire (default 15 min); background jobs contain no send path. The digest is only ever sent to the connected account's own address. Every approval and send is written to the local audit log. |
| SSRF via sources | Only http/https, ports 80/443/8080/8443, no credentials in URLs, DNS-resolved addresses must be public (re-checked on each redirect), 5 MB response cap, timeouts. |
| Prompt injection | Job content is sanitised, fenced as untrusted data in prompts, flagged when it looks like an injection attempt, and LLM output is parsed as strict JSON and cannot trigger actions. |
| Fabricated CV content | Documents are assembled only from the profile; AI drafts mentioning numbers or proper nouns not in the profile are discarded. |
| Gmail access | `gmail.compose` to draft and send approved emails, `gmail.metadata` to read the From and Subject headers of application threads for reply tracking. Only if the user opts in to reply sorting is `gmail.readonly` requested; then only replies in application threads are opened, classified locally by keyword, and the text is discarded. Reply text is treated as untrusted and never acted on. |
| CV import | Parsed locally with pypdf / python-docx; no external service. Encrypted PDFs are refused; extracted text is length-limited and sanitised. |
| Uploads | PDF/DOCX only, verified by magic bytes, 10 MB limit, stored under the data directory with sanitised names. |
| Webview | Strict CSP, no remote content, minimal Tauri capabilities (file opening scoped to the documents folder). |

## Known limitations

- Personal data other than credentials (profile, jobs, documents) is stored unencrypted in
  the user's data directory and relies on OS account security / full-disk encryption.
- A process running as the same OS user can read the per-launch API token from the
  child's environment. Huntly does not defend against malware running as you.
- If the OS keychain option is enabled, anyone who can unlock your OS session can use
  your stored credentials.
