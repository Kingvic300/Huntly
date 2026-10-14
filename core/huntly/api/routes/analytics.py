from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from huntly.api.deps import get_ctx
from huntly.config import TZ
from huntly.context import AppContext
from huntly.models import Application, EmailApproval, Job, Source

router = APIRouter()


@router.get("/analytics")
def analytics(days: int = 30, ctx: AppContext = Depends(get_ctx)):
    days = max(7, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with ctx.db.session() as s:
        jobs = list(s.execute(select(Job.discovered_at, Job.score, Job.source_id, Job.status, Job.remote, Job.score_breakdown).where(Job.discovered_at >= since)))
        apps = list(s.execute(select(Application.created_at, Application.applied_at, Application.status)))
        sources = {sid: name for sid, name in s.execute(select(Source.id, Source.name))}
        total_jobs = s.scalar(select(func.count()).select_from(Job)) or 0
        sent = s.scalar(select(func.count()).select_from(EmailApproval).where(EmailApproval.status == "sent")) or 0
        pending = s.scalar(select(func.count()).select_from(EmailApproval).where(EmailApproval.status.in_(["pending", "approved"]))) or 0
        new_jobs = s.scalar(select(func.count()).select_from(Job).where(Job.status == "new")) or 0

    def day(dt):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ).date().isoformat()

    start = datetime.now(TZ).date() - timedelta(days=days - 1)
    series = {(start + timedelta(days=i)).isoformat(): {"date": (start + timedelta(days=i)).isoformat(), "discovered": 0, "applied": 0} for i in range(days)}
    for j in jobs:
        d = day(j.discovered_at)
        if d in series:
            series[d]["discovered"] += 1
    for a in apps:
        if a.applied_at:
            d = day(a.applied_at)
            if d in series:
                series[d]["applied"] += 1

    buckets = Counter()
    for j in jobs:
        b = min(int(j.score // 10) * 10, 90)
        buckets[b] += 1
    by_source = Counter(sources.get(j.source_id, "Removed source") for j in jobs)
    skills = Counter(sk for j in jobs for sk in (j.score_breakdown or {}).get("matched_skills", []))
    funnel_order = ["preparing", "awaiting_approval", "applied", "interviewing", "offer", "rejected", "withdrawn"]
    app_status = Counter(a.status for a in apps)

    return {
        "days": days,
        "totals": {
            "jobs": total_jobs,
            "jobs_in_period": len(jobs),
            "new_jobs": new_jobs,
            "applications": len(apps),
            "emails_sent": sent,
            "pending_approvals": pending,
            "avg_score": round(sum(j.score for j in jobs) / len(jobs), 1) if jobs else None,
            "remote_share": round(100 * sum(1 for j in jobs if j.remote) / len(jobs)) if jobs else None,
        },
        "timeline": list(series.values()),
        "score_distribution": [{"bucket": f"{b}–{b + 9 if b < 90 else 100}", "count": buckets.get(b, 0)} for b in range(0, 100, 10)],
        "by_source": [{"source": k, "count": v} for k, v in by_source.most_common(10)],
        "top_skills": [{"skill": k, "count": v} for k, v in skills.most_common(12)],
        "funnel": [{"status": st, "count": app_status.get(st, 0)} for st in funnel_order],
    }


@router.get("/pipeline")
def pipeline(ctx: AppContext = Depends(get_ctx)):
    """Counts for the pipeline strip and the daily briefing."""
    day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    with ctx.db.session() as s:
        jobs = dict(s.execute(select(Job.status, func.count()).group_by(Job.status)).all())
        apps = dict(s.execute(select(Application.status, func.count()).group_by(Application.status)).all())
        shortlisted = s.scalar(
            select(func.count()).select_from(Job).where(Job.status == "saved", ~Job.id.in_(select(Application.job_id)))
        ) or 0
        fresh = s.scalar(select(func.count()).select_from(Job).where(Job.discovered_at >= day_ago)) or 0
        hot = s.scalar(select(func.count()).select_from(Job).where(Job.status == "new", Job.score >= 75)) or 0
        failing = s.scalar(select(func.count()).select_from(Source).where(Source.enabled.is_(True), Source.last_status == "error")) or 0
        pending = s.scalar(select(func.count()).select_from(EmailApproval).where(EmailApproval.status.in_(["pending", "approved"]))) or 0
    return {
        "stages": [
            {"id": "new", "label": "New", "count": jobs.get("new", 0)},
            {"id": "shortlisted", "label": "Shortlisted", "count": shortlisted},
            {"id": "preparing", "label": "Applying", "count": apps.get("preparing", 0)},
            {"id": "awaiting_approval", "label": "Awaiting approval", "count": pending},
            {"id": "applied", "label": "Sent", "count": apps.get("applied", 0)},
            {"id": "interviewing", "label": "Interviewing", "count": apps.get("interviewing", 0)},
            {"id": "offer", "label": "Offer", "count": apps.get("offer", 0)},
        ],
        "new_last_24h": fresh,
        "hot_new": hot,
        "failing_sources": failing,
    }
