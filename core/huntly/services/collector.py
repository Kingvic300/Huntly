"""Collection pipeline: fetch → sanitise → dedupe → score → store → notify."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from huntly.context import AppContext
from huntly.models import Job, JobRun, Source
from huntly.security.vault import VaultLocked
from huntly.services import store
from huntly.services.llm import LLMError
from huntly.services.matching import blend, score_job
from huntly.services.profile import load_profile, profile_corpus
from huntly.services.sources.base import RawJob, SourceContext, SourceError
from huntly.services.sources.registry import SOURCES
from huntly.security.ssrf import UnsafeURL, safe_get

log = logging.getLogger(__name__)

LLM_ASSESSMENTS_PER_RUN = 10


def _source_context(ctx: AppContext) -> SourceContext:
    def get_secret(name: str) -> str | None:
        try:
            return ctx.secret(name)
        except VaultLocked:
            raise SourceError("Vault is locked; unlock it to use stored credentials")

    return SourceContext(get_secret=get_secret, fetch=ctx.fetch or safe_get)


def run_source(ctx: AppContext, s: Session, source: Source) -> tuple[int, int]:
    impl = SOURCES.get(source.kind)
    if impl is None:
        raise SourceError(f"Unknown source kind {source.kind}")
    raw_jobs = impl.fetch(source.config, _source_context(ctx))
    profile = load_profile(s)
    new = 0
    for raw in raw_jobs:
        if _store_job(s, source, raw.normalized(), profile):
            new += 1
    return len(raw_jobs), new


def _store_job(s: Session, source: Source, raw: RawJob, profile) -> bool:
    key = raw.dedupe_key()
    if s.scalar(select(Job.id).where(Job.dedupe_key == key)) is not None:
        return False
    score, breakdown = score_job(
        profile, title=raw.title, description=raw.description, location=raw.location, remote=bool(raw.remote), posted_at=raw.posted_at
    )
    breakdown["deterministic"] = score
    s.add(
        Job(
            source_id=source.id,
            external_id=(raw.external_id or "")[:255] or None,
            dedupe_key=key,
            title=raw.title,
            company=raw.company,
            location=raw.location,
            remote=bool(raw.remote),
            url=raw.url[:2048] if raw.url else None,
            apply_email=raw.apply_email,
            description=raw.description,
            posted_at=raw.posted_at,
            score=score,
            score_breakdown=breakdown,
            flagged_injection=raw.injection_suspected,
        )
    )
    s.flush()
    return True


def assess_with_llm(ctx: AppContext, s: Session, jobs: list[Job]) -> int:
    client = ctx.groq()
    if client is None:
        return 0
    profile_text = profile_corpus(load_profile(s))
    done = 0
    for job in jobs[:LLM_ASSESSMENTS_PER_RUN]:
        try:
            result = client.assess_fit(profile_text, job.title, job.description)
        except LLMError as exc:
            log.warning("llm assessment failed: %s", exc)
            break
        breakdown = dict(job.score_breakdown or {})
        breakdown["llm"] = result
        job.score_breakdown = breakdown
        job.score = blend(breakdown.get("deterministic", job.score), result["fit"])
        job.llm_summary = result["summary"]
        done += 1
    return done


def collect_all(ctx: AppContext, trigger: str = "schedule", source_ids: list[int] | None = None) -> dict:
    if not ctx.collect_lock.acquire(blocking=False):
        return {"status": "skipped", "reason": "collection already running"}
    try:
        with ctx.db.session() as s:
            run = JobRun(kind="collect", trigger=trigger)
            s.add(run)
            s.flush()
            run_id = run.id
        stats = {"sources": 0, "fetched": 0, "new": 0, "errors": 0, "llm_assessed": 0}
        with ctx.db.session() as s:
            q = select(Source).where(Source.enabled.is_(True))
            if source_ids:
                q = select(Source).where(Source.id.in_(source_ids))
            sources = list(s.scalars(q))
        for src in sources:
            stats["sources"] += 1
            with ctx.db.session() as s:
                source = s.get(Source, src.id)
                source.last_run_at = datetime.now(timezone.utc)
                try:
                    fetched, new = run_source(ctx, s, source)
                    source.last_status, source.last_error = "ok", None
                    source.last_found = new
                    source.total_found = (source.total_found or 0) + new
                    stats["fetched"] += fetched
                    stats["new"] += new
                except (SourceError, UnsafeURL, ValueError) as exc:
                    s.rollback()
                    source = s.get(Source, src.id)
                    source.last_run_at = datetime.now(timezone.utc)
                    source.last_status, source.last_error = "error", str(exc)[:500]
                    stats["errors"] += 1
                except Exception as exc:  # network errors etc.
                    s.rollback()
                    source = s.get(Source, src.id)
                    source.last_run_at = datetime.now(timezone.utc)
                    source.last_status, source.last_error = "error", f"{type(exc).__name__}: {str(exc)[:300]}"
                    stats["errors"] += 1
                    log.exception("source %s failed", src.id)
        with ctx.db.session() as s:
            if stats["new"]:
                fresh = list(
                    s.scalars(select(Job).where(Job.status == "new", Job.llm_summary.is_(None)).order_by(Job.score.desc()).limit(LLM_ASSESSMENTS_PER_RUN))
                )
                try:
                    stats["llm_assessed"] = assess_with_llm(ctx, s, fresh)
                except VaultLocked:
                    pass
                top = s.scalar(select(Job).where(Job.status == "new").order_by(Job.score.desc()).limit(1))
                store.notify(
                    s,
                    f"{stats['new']} new job{'s' if stats['new'] != 1 else ''} found",
                    f"Top match: {top.title} ({top.score:.0f})" if top else "",
                )
            if stats["errors"]:
                store.notify(s, f"{stats['errors']} source(s) failed", "Open Sources for details.", "warning")
            run = s.get(JobRun, run_id)
            run.finished_at = datetime.now(timezone.utc)
            run.status = "ok" if not stats["errors"] else ("partial" if stats["errors"] < max(1, stats["sources"]) else "error")
            run.stats = stats
        log.info("collection finished", extra={"data": stats})
        return {"status": "ok", "run_id": run_id, **stats}
    finally:
        ctx.collect_lock.release()


def rescore_all(ctx: AppContext) -> int:
    with ctx.db.session() as s:
        profile = load_profile(s)
        n = 0
        for job in s.scalars(select(Job)):
            score, breakdown = score_job(
                profile, title=job.title, description=job.description, location=job.location, remote=job.remote, posted_at=job.posted_at
            )
            breakdown["deterministic"] = score
            llm = (job.score_breakdown or {}).get("llm")
            if llm:
                breakdown["llm"] = llm
            job.score_breakdown = breakdown
            job.score = blend(score, llm["fit"] if llm else None)
            n += 1
        return n
