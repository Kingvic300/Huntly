"""Daily digest email, sent only to the user's own connected Gmail address."""

from __future__ import annotations

import html
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select

from huntly.config import TZ
from huntly.context import AppContext
from huntly.models import Application, EmailApproval, Job, JobRun
from huntly.services import store
from huntly.services.gmail import build_message

log = logging.getLogger(__name__)


def build_digest(ctx: AppContext, limit: int = 25) -> dict:
    with ctx.db.session() as s:
        min_score = float(store.get_setting(s, "digest_min_score") or 0)
        jobs = list(
            s.scalars(
                select(Job)
                .where(Job.included_in_digest_at.is_(None), Job.status.in_(["new", "saved"]), Job.score >= min_score)
                .order_by(Job.score.desc())
                .limit(limit)
            )
        )
        pending = s.scalar(select(func.count()).select_from(EmailApproval).where(EmailApproval.status.in_(["pending", "approved"]))) or 0
        by_status = dict(s.execute(select(Application.status, func.count()).group_by(Application.status)).all())
        items = [
            {"id": j.id, "title": j.title, "company": j.company, "location": j.location, "remote": j.remote, "score": j.score, "url": j.url, "summary": j.llm_summary}
            for j in jobs
        ]
    date = datetime.now(TZ).strftime("%A %d %B %Y")
    return {"date": date, "jobs": items, "pending_approvals": pending, "applications": by_status}


def render_digest(d: dict) -> tuple[str, str, str]:
    subject = f"Huntly digest — {len(d['jobs'])} new match{'es' if len(d['jobs']) != 1 else ''} — {d['date']}"
    lines = [f"Huntly daily digest — {d['date']}", ""]
    if d["pending_approvals"]:
        lines.append(f"{d['pending_approvals']} application email(s) are waiting for your approval in Huntly.\n")
    if d["applications"]:
        lines.append("Applications: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in sorted(d["applications"].items())) + "\n")
    for j in d["jobs"]:
        loc = " · ".join(x for x in [j["company"], j["location"], "Remote" if j["remote"] else None] if x)
        lines.append(f"[{j['score']:.0f}] {j['title']}\n    {loc}\n    {j['url'] or ''}")
    if not d["jobs"]:
        lines.append("No new matches above your threshold since the last digest.")
    lines += ["", "Sent by Huntly from your own computer. Nothing was sent to any third party."]
    text = "\n".join(lines)

    e = html.escape
    rows = "".join(
        f"<tr><td style='padding:10px 12px;border-bottom:1px solid #e5e7eb;font:600 13px system-ui;color:#0e7490'>{j['score']:.0f}</td>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #e5e7eb;font:13px system-ui'>"
        f"<a href='{e(j['url'] or '#')}' style='color:#111827;font-weight:600;text-decoration:none'>{e(j['title'])}</a><br>"
        f"<span style='color:#6b7280'>{e(' · '.join(x for x in [j['company'], j['location'], 'Remote' if j['remote'] else None] if x))}</span>"
        + (f"<br><span style='color:#374151'>{e(j['summary'])}</span>" if j.get("summary") else "")
        + "</td></tr>"
        for j in d["jobs"]
    ) or "<tr><td style='padding:12px;font:13px system-ui;color:#6b7280'>No new matches above your threshold since the last digest.</td></tr>"
    pending = (
        f"<p style='font:13px system-ui;color:#92400e;background:#fffbeb;padding:10px 12px;border-radius:6px'>"
        f"{d['pending_approvals']} application email(s) are waiting for your approval in Huntly.</p>"
        if d["pending_approvals"] else ""
    )
    body_html = (
        f"<div style='max-width:640px;margin:0 auto'><h2 style='font:600 18px system-ui;color:#111827'>Huntly daily digest</h2>"
        f"<p style='font:13px system-ui;color:#6b7280'>{e(d['date'])}</p>{pending}"
        f"<table style='width:100%;border-collapse:collapse'>{rows}</table>"
        f"<p style='font:12px system-ui;color:#9ca3af;margin-top:16px'>Sent by Huntly from your own computer.</p></div>"
    )
    return subject, text, body_html


def send_digest(ctx: AppContext, trigger: str = "schedule") -> dict:
    with ctx.db.session() as s:
        run = JobRun(kind="digest", trigger=trigger)
        s.add(run)
        s.flush()
        run_id = run.id
    try:
        d = build_digest(ctx)
        subject, text, body_html = render_digest(d)
        gmail = ctx.gmail()
        me = gmail.email_address()  # digest recipient is always the connected account itself
        message_id = gmail.send_message(build_message(sender=me, to=me, subject=subject, text=text, html=body_html))
        with ctx.db.session() as s:
            now = datetime.now(timezone.utc)
            ids = [j["id"] for j in d["jobs"]]
            for job in s.scalars(select(Job).where(Job.id.in_(ids))):
                job.included_in_digest_at = now
            r = s.get(JobRun, run_id)
            r.finished_at, r.status, r.stats = now, "ok", {"jobs": len(ids), "message_id": message_id}
            store.audit(s, "scheduler" if trigger == "schedule" else "user", "digest.sent", "digest", run_id, to=me, jobs=len(ids))
        return {"status": "ok", "jobs": len(d["jobs"]), "message_id": message_id}
    except Exception as exc:
        with ctx.db.session() as s:
            r = s.get(JobRun, run_id)
            r.finished_at, r.status, r.error = datetime.now(timezone.utc), "error", str(exc)[:500]
            store.notify(s, "Daily digest failed", str(exc)[:300], "error")
        log.warning("digest failed: %s", exc)
        raise
