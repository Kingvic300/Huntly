"""The company directory: companies' own job boards, checked in rotation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from huntly.api.deps import get_ctx
from huntly.services.store import iso
from huntly.context import AppContext
from huntly.models import Company
from huntly.services import companies, store

router = APIRouter()


def company_out(c: Company) -> dict:
    return {
        "id": c.id, "platform": c.platform, "slug": c.slug, "name": c.name, "origin": c.origin, "enabled": c.enabled,
        "last_checked_at": iso(c.last_checked_at), "last_status": c.last_status, "last_error": c.last_error,
        "open_jobs": c.open_jobs, "jobs_found": c.jobs_found,
    }


@router.get("/companies")
def list_companies(
    q: str = Query("", max_length=100),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    ctx: AppContext = Depends(get_ctx),
):
    with ctx.db.session() as s:
        companies.load_seed(s)
        stmt = select(Company)
        if q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(Company.slug.ilike(like), Company.name.ilike(like), Company.platform.ilike(like)))
        total = s.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = s.scalars(stmt.order_by(Company.enabled.desc(), Company.open_jobs.desc(), Company.id).offset(offset).limit(limit))
        return {"total": total, "items": [company_out(c) for c in rows], **companies.summary(s)}


class ImportIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=3_000_000)


@router.post("/companies/import")
def import_companies(body: ImportIn, ctx: AppContext = Depends(get_ctx)):
    boards, invalid = companies.parse_import(body.text)
    with ctx.db.session() as s:
        companies.load_seed(s)
        added = companies.add_companies(s, boards, "imported")
        store.audit(s, "user", "companies.imported", "company", added=added, invalid=len(invalid))
    return {"added": added, "already_tracked": len(boards) - added, "invalid": invalid[:20], "invalid_count": len(invalid)}


class CompanyPatch(BaseModel):
    enabled: bool


@router.patch("/companies/{company_id}")
def patch_company(company_id: int, body: CompanyPatch, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        c = s.get(Company, company_id)
        if c is None:
            raise HTTPException(404, "Company not found")
        c.enabled = body.enabled
        return company_out(c)
