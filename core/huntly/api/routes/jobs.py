"""Jobs, sources, collection runs and the profile."""

from __future__ import annotations

import threading
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from huntly.api.deps import get_ctx
from huntly.api.serializers import job_out, source_out
from huntly.context import AppContext
from huntly.models import Application, Job, Source
from huntly.security.ssrf import UnsafeURL
from huntly.services import store
from huntly.services.collector import collect_all, rescore_all
from huntly.services.profile import ProfileData, completeness, load_profile, save_profile
from huntly.services.sources.registry import SOURCES, catalog

router = APIRouter()

JobStatus = Literal["new", "saved", "dismissed", "applied"]


@router.get("/jobs")
def list_jobs(
    q: str | None = None,
    status: str | None = None,
    min_score: float = 0,
    source_id: int | None = None,
    remote: bool | None = None,
    sort: Literal["score", "recent", "posted"] = "score",
    limit: int = 50,
    offset: int = 0,
    ctx: AppContext = Depends(get_ctx),
):
    stmt = select(Job).where(Job.score >= min_score)
    if q:
        like = f"%{q.strip()[:100]}%"
        stmt = stmt.where(or_(Job.title.ilike(like), Job.company.ilike(like), Job.location.ilike(like), Job.description.ilike(like)))
    if status:
        stmt = stmt.where(Job.status.in_(status.split(",")))
    if source_id:
        stmt = stmt.where(Job.source_id == source_id)
    if remote is not None:
        stmt = stmt.where(Job.remote.is_(remote))
    order = {"score": Job.score.desc(), "recent": Job.discovered_at.desc(), "posted": Job.posted_at.desc()}[sort]
    with ctx.db.session() as s:
        total = s.scalar(select(func.count()).select_from(stmt.subquery()))
        items = [job_out(j) for j in s.scalars(stmt.order_by(order, Job.id.desc()).limit(min(limit, 200)).offset(offset))]
    return {"total": total, "items": items}


@router.get("/jobs/{job_id}")
def get_job(job_id: int, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        job = s.get(Job, job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        out = job_out(job, full=True)
        app = s.scalar(select(Application).where(Application.job_id == job_id))
        out["application_id"] = app.id if app else None
    return out


class JobPatch(BaseModel):
    status: JobStatus


@router.patch("/jobs/{job_id}")
def patch_job(job_id: int, body: JobPatch, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        job = s.get(Job, job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        old, job.status = job.status, body.status
        store.audit(s, "user", "job.status_changed", "job", job.id, old=old, new=body.status)
        return job_out(job)


@router.post("/jobs/rescore")
def rescore(ctx: AppContext = Depends(get_ctx)):
    return {"rescored": rescore_all(ctx)}


# --- sources -------------------------------------------------------------------
class SourceIn(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=120)
    config: dict = Field(default_factory=dict)
    enabled: bool = True


class SourcePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    config: dict | None = None
    enabled: bool | None = None


@router.get("/sources/catalog")
def sources_catalog():
    return catalog()


@router.get("/sources")
def list_sources(ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        return [source_out(x) for x in s.scalars(select(Source).order_by(Source.id))]


def _validated(kind: str, config: dict) -> dict:
    impl = SOURCES.get(kind)
    if impl is None:
        raise HTTPException(400, f"Unknown source type {kind!r}")
    try:
        return impl.validate(config)
    except (ValueError, UnsafeURL) as exc:
        raise HTTPException(400, str(exc))


@router.post("/sources", status_code=201)
def create_source(body: SourceIn, ctx: AppContext = Depends(get_ctx)):
    config = _validated(body.kind, body.config)
    with ctx.db.session() as s:
        src = Source(kind=body.kind, name=body.name.strip(), config=config, enabled=body.enabled)
        s.add(src)
        s.flush()
        store.audit(s, "user", "source.created", "source", src.id, kind=body.kind)
        return source_out(src)


@router.patch("/sources/{source_id}")
def update_source(source_id: int, body: SourcePatch, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        src = s.get(Source, source_id)
        if src is None:
            raise HTTPException(404, "Source not found")
        if body.config is not None:
            src.config = _validated(src.kind, body.config)
        if body.name is not None:
            src.name = body.name.strip()
        if body.enabled is not None:
            src.enabled = body.enabled
        store.audit(s, "user", "source.updated", "source", src.id)
        return source_out(src)


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        src = s.get(Source, source_id)
        if src is None:
            raise HTTPException(404, "Source not found")
        s.delete(src)
        store.audit(s, "user", "source.deleted", "source", source_id)
    return {"ok": True}


class CollectIn(BaseModel):
    source_ids: list[int] | None = None


@router.post("/collect")
def collect(body: CollectIn | None = None, ctx: AppContext = Depends(get_ctx)):
    if ctx.collect_lock.locked():
        raise HTTPException(409, "A collection run is already in progress")
    ids = body.source_ids if body else None
    threading.Thread(target=collect_all, args=(ctx, "manual", ids), name="collect-manual", daemon=True).start()
    return {"started": True}


# --- profile -------------------------------------------------------------------
@router.get("/profile")
def get_profile(ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        p = load_profile(s)
    return {"profile": p.model_dump(), "completeness": completeness(p)}


@router.put("/profile")
def put_profile(body: ProfileData, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        save_profile(s, body)
        store.audit(s, "user", "profile.updated", "profile", 1)
    rescore_all(ctx)
    return {"profile": body.model_dump(), "completeness": completeness(body)}
