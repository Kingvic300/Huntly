"""Company directory: many companies' own job boards, checked a batch at a time.

Companies publish jobs through public hiring-platform APIs (Greenhouse, Lever, Ashby,
SmartRecruiters, Recruitee, Workable, BambooHR, Breezy HR). Huntly keeps a directory of those boards: a bundled seed
list, companies found by looking up the employer names other sources return, and lists
the user pastes. Each collection run checks the boards checked longest ago, so a large
directory is covered in rotation rather than all at once. Only jobs that match the
profile (:func:`huntly.services.matching.matches_profile`) are stored.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from huntly.config import resource_path
from huntly.models import Company, CompanyProbe, Job, Source
from huntly.services import store
from huntly.services.profile import load_profile
from huntly.services.sources.base import SLUG, RawJob, SourceContext, SourceError
from huntly.services.sources.registry import SOURCES

log = logging.getLogger(__name__)

DIRECTORY_KIND = "company_directory"
# Hiring platform -> the config key its source adapter expects, in lookup order.
PLATFORMS = {
    "greenhouse": "board", "lever": "company", "ashby": "board", "smartrecruiters": "company", "recruitee": "company",
    "workable": "company", "bamboohr": "company", "breezy": "company",
}
_SUBDOMAIN_PLATFORMS = {"recruitee", "workable", "bamboohr", "breezy"}
URL_PATTERNS = [
    ("greenhouse", re.compile(r"^(?:https?://)?(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_.-]+)", re.I)),
    ("lever", re.compile(r"^(?:https?://)?jobs\.lever\.co/([A-Za-z0-9_.-]+)", re.I)),
    ("ashby", re.compile(r"^(?:https?://)?jobs\.ashbyhq\.com/([A-Za-z0-9_.-]+)", re.I)),
    ("smartrecruiters", re.compile(r"^(?:https?://)?(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_.-]+)", re.I)),
    ("recruitee", re.compile(r"^(?:https?://)?([a-z0-9-]+)\.recruitee\.com(?:/|$)", re.I)),
    ("workable", re.compile(r"^(?:https?://)?apply\.workable\.com/([a-z0-9-]+)(?:/|$)", re.I)),
    ("workable", re.compile(r"^(?:https?://)?([a-z0-9-]+)\.workable\.com(?:/|$)", re.I)),
    ("bamboohr", re.compile(r"^(?:https?://)?([a-z0-9-]+)\.bamboohr\.com(?:/|$)", re.I)),
    ("breezy", re.compile(r"^(?:https?://)?([a-z0-9-]+)\.breezy\.hr(?:/|$)", re.I)),
]
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_SUFFIXES = {
    "inc", "llc", "ltd", "limited", "plc", "gmbh", "corp", "corporation", "co", "company", "group", "holdings", "hq",
    "technologies", "technology", "labs", "global", "africa", "nigeria", "io", "ai", "app",
}
FETCH_WORKERS = 8
DISCOVER_PER_RUN = 10
DESCRIBE_PER_RUN = 100


def board_config(platform: str, slug: str) -> dict:
    return {PLATFORMS[platform]: slug}


def valid_slug(platform: str, slug: str) -> bool:
    return bool(_DNS_LABEL.match(slug) if platform in _SUBDOMAIN_PLATFORMS else SLUG.match(slug))


def board_from_url(url: str) -> tuple[str, str] | None:
    for platform, pattern in URL_PATTERNS:
        m = pattern.match(url.strip())
        if m and m.group(1).lower() not in ("embed", "api", "www", "apply", "j", "app") and valid_slug(platform, m.group(1).lower()):
            return platform, m.group(1).lower()
    return None


def parse_import(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Board links or ``platform:name`` entries, separated by whitespace, commas or semicolons."""
    found, invalid = [], []
    for token in re.split(r"[\s,;]+", text.strip()):
        if not token:
            continue
        hit = board_from_url(token)
        if hit is None and ":" in token and "//" not in token:
            platform, _, slug = token.partition(":")
            platform, slug = platform.strip().lower(), slug.strip().strip("/").lower()
            if platform in PLATFORMS and valid_slug(platform, slug):
                hit = (platform, slug)
        if hit:
            found.append(hit)
        else:
            invalid.append(token[:100])
    return list(dict.fromkeys(found)), invalid


def add_companies(s: Session, boards: list[tuple[str, str]], origin: str, names: dict | None = None) -> int:
    existing = set(s.execute(select(Company.platform, Company.slug)).tuples())
    new = [
        Company(platform=p, slug=slug, name=(names or {}).get((p, slug)), origin=origin)
        for p, slug in dict.fromkeys(boards)
        if (p, slug) not in existing
    ]
    s.add_all(new)
    s.flush()
    return len(new)


def load_seed(s: Session) -> int:
    """Add the bundled starter list once per list version. Companies the user turned off stay off."""
    data = json.loads(resource_path("assets", "companies.json").read_text(encoding="utf-8"))
    if (store.get_setting(s, "company_seed_version") or 0) >= data["version"]:
        return 0
    rows = [(p, slug, name) for p, slug, name in data["companies"] if p in PLATFORMS and valid_slug(p, slug)]
    added = add_companies(s, [(p, slug) for p, slug, _ in rows], "seed", {(p, slug): name for p, slug, name in rows})
    store.set_setting(s, "company_seed_version", data["version"])
    return added


def name_key(name: str) -> str:
    return "".join(_words(name))[:120]


def _words(name: str) -> list[str]:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", ascii_name.lower())


def slug_guesses(name: str) -> list[str]:
    """Board names a company is likely to use: 'Grafana Labs' -> grafanalabs, grafana-labs, grafana."""
    words = _words(name)
    core = [w for w in words if w not in _SUFFIXES] or words
    guesses = ["".join(words), "-".join(words), "".join(core)]
    return [g for g in dict.fromkeys(guesses) if 2 <= len(g) <= 60]


def probe(name: str, sctx: SourceContext, platforms=PLATFORMS) -> tuple[str, str, str] | None:
    """Look a company name up on each platform; return the first board with open jobs."""
    for slug in slug_guesses(name):
        for platform in platforms:
            if not valid_slug(platform, slug):
                continue
            try:
                jobs = SOURCES[platform].fetch(board_config(platform, slug), sctx)
            except Exception:  # most guesses are simply not found
                continue
            if jobs:
                # Some platforms only return the board name; the name we looked up reads better.
                company = " ".join((jobs[0].company or "").split())
                return platform, slug, company if company.lower() not in ("", slug) else name
    return None


def discover(s: Session, source: Source, sctx: SourceContext, limit: int = DISCOVER_PER_RUN) -> int:
    """Look up employers that other sources found, a few per run, and add the boards that exist."""
    recent = s.execute(
        select(Job.company)
        .where(Job.company.is_not(None), (Job.source_id != source.id) | Job.source_id.is_(None))
        .group_by(Job.company)
        .order_by(func.max(Job.discovered_at).desc())
        .limit(limit * 20)
    ).scalars()
    keys = {name_key(n): n for n in recent if name_key(n)}
    done = set(s.scalars(select(CompanyProbe.name_key).where(CompanyProbe.name_key.in_(list(keys)))))
    todo = [(k, n) for k, n in keys.items() if k not in done][:limit]
    if not todo:
        return 0
    with ThreadPoolExecutor(FETCH_WORKERS) as pool:
        results = list(pool.map(lambda kn: probe(kn[1], sctx), todo))
    for (key, _), hit in zip(todo, results):
        s.add(CompanyProbe(name_key=key, found=hit is not None))
    hits = [h for h in results if h]
    return add_companies(s, [(p, slug) for p, slug, _ in hits], "discovered", {(p, slug): n for p, slug, n in hits})


StoreJob = Callable[..., bool]


def run_directory(s: Session, source: Source, sctx: SourceContext, store_job: StoreJob) -> tuple[int, int]:
    """One collection pass: discover new companies, then check the next batch of boards."""
    load_seed(s)
    profile = load_profile(s)
    if not (profile.target_roles or profile.skills):
        raise SourceError("Add target roles or skills to your profile first. The directory keeps only jobs that match them.")
    discover(s, source, sctx)
    batch = int(store.get_setting(s, "directory_batch_size") or 300)
    companies = list(
        s.scalars(
            select(Company)
            .where(Company.enabled.is_(True))
            .order_by(Company.last_checked_at.is_not(None), Company.last_checked_at, Company.id)
            .limit(batch)
        )
    )
    boards = [(c.id, c.platform, c.slug) for c in companies]

    def fetch(board):
        company_id, platform, slug = board
        try:
            return company_id, SOURCES[platform].fetch(board_config(platform, slug), sctx), None
        except Exception as exc:  # recorded per company; one bad board never stops the run
            return company_id, None, exc

    with ThreadPoolExecutor(FETCH_WORKERS) as pool:
        results = list(pool.map(fetch, boards))

    budget = [DESCRIBE_PER_RUN]

    def describer(platform: str):
        impl = SOURCES[platform]
        if not hasattr(impl, "describe"):
            return None

        def describe(job: RawJob) -> None:
            if budget[0] > 0:
                budget[0] -= 1
                impl.describe(job, sctx)

        return describe

    by_id = {c.id: c for c in companies}
    now = datetime.now(timezone.utc)
    fetched = new = 0
    for company_id, jobs, exc in results:
        c = by_id[company_id]
        c.last_checked_at = now
        if exc is not None:
            c.last_status, c.last_error = "error", f"{type(exc).__name__}: {exc}"[:300]
            if isinstance(exc, SourceError) and "HTTP 404" in str(exc):
                c.enabled = False  # the board no longer exists
            continue
        c.last_status, c.last_error, c.open_jobs = "ok", None, len(jobs)
        c.name = c.name or (jobs[0].company if jobs else None)
        fetched += len(jobs)
        for job in jobs:  # some platforms only return the board name; show the company's own
            if c.name and (job.company or "").lower() == c.slug:
                job.company = c.name
        describe = describer(c.platform)
        added = sum(store_job(s, source, job.normalized(), profile, relevant_only=True, describe=describe) for job in jobs)
        c.jobs_found += added
        new += added
    log.info("company directory checked %d boards, %d new jobs", len(boards), new)
    return fetched, new


def summary(s: Session) -> dict:
    by_platform = dict(s.execute(select(Company.platform, func.count()).where(Company.enabled.is_(True)).group_by(Company.platform)).tuples().all())
    return {
        "tracked": sum(by_platform.values()),
        "turned_off": s.scalar(select(func.count()).select_from(Company).where(Company.enabled.is_(False))) or 0,
        "by_platform": by_platform,
        "checked": s.scalar(select(func.count()).select_from(Company).where(Company.last_checked_at.is_not(None))) or 0,
        "hiring": s.scalar(select(func.count()).select_from(Company).where(Company.enabled.is_(True), Company.open_jobs > 0)) or 0,
        "batch_size": int(store.get_setting(s, "directory_batch_size") or 300),
    }
