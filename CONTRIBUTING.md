# Contributing to Huntly

Thanks for helping! Huntly is a privacy-first desktop app, so a few rules are firm.

## Non-negotiables

1. **No telemetry or remote calls** other than the user-configured integrations. PRs adding
   analytics, crash reporting, update pings or third-party SDKs that phone home will be declined.
2. **No path that sends an application email without an explicit, hash-matched user approval.**
3. **No invented candidate content** in generated documents.
4. **No secrets in code, tests, fixtures or logs.** `tests/test_security.py` scans the tree.
5. Treat all job-posting content as untrusted input.

## Getting started

```bash
scripts/setup-dev.sh
scripts/dev.sh
scripts/test.sh
```

## Pull requests

- One logical change per PR; describe the user-visible effect.
- Add or update tests. External services must be mocked — never hit real Gmail/X/Groq in tests.
- Schema changes need an Alembic migration in `core/huntly/migrations/versions/`.
- Dependencies are pinned exactly (`core/requirements*.txt`, `desktop/package.json`,
  `desktop/src-tauri/Cargo.toml` + lockfiles). Justify any new dependency.
- Match the surrounding style: Python is formatted for 120 columns; TypeScript is strict.
- Use Conventional Commit messages (`feat:`, `fix:`, `docs:` …).

## Reporting bugs

Open an issue with steps to reproduce, expected vs actual behaviour, OS and version. Attach
the relevant lines of `~/.local/share/huntly/logs/core.log` after checking they contain no
personal data. Security issues: see [SECURITY.md](SECURITY.md).

By contributing you agree that your contributions are licensed under Apache-2.0.
