from __future__ import annotations

from huntly.models import Application, AuditLog, Document, EmailApproval, Job, JobRun, Notification, Source
from huntly.services.store import iso


def job_out(j: Job, full: bool = False) -> dict:
    out = {
        "id": j.id,
        "title": j.title,
        "company": j.company,
        "location": j.location,
        "remote": j.remote,
        "seniority": j.seniority,
        "url": j.url,
        "apply_email": j.apply_email,
        "posted_at": iso(j.posted_at),
        "discovered_at": iso(j.discovered_at),
        "score": j.score,
        "status": j.status,
        "source_id": j.source_id,
        "source_name": j.source.name if j.source else None,
        "source_kind": j.source.kind if j.source else None,
        "llm_summary": j.llm_summary,
        "flagged_injection": j.flagged_injection,
        "matched_skills": (j.score_breakdown or {}).get("matched_skills", []),
    }
    if full:
        out["description"] = j.description
        out["score_breakdown"] = j.score_breakdown
    else:
        out["snippet"] = (j.description or "")[:280]
    return out


def source_out(s: Source) -> dict:
    return {
        "id": s.id, "kind": s.kind, "name": s.name, "config": s.config, "enabled": s.enabled,
        "created_at": iso(s.created_at), "last_run_at": iso(s.last_run_at), "last_status": s.last_status,
        "last_error": s.last_error, "last_found": s.last_found, "total_found": s.total_found,
    }


def document_out(d: Document) -> dict:
    return {
        "id": d.id, "kind": d.kind, "title": d.title, "job_id": d.job_id, "format": d.format, "path": d.path,
        "sha256": d.sha256, "size": d.size, "meta": d.meta, "created_at": iso(d.created_at),
    }


def approval_out(a: EmailApproval) -> dict:
    app = a.application
    return {
        "id": a.id, "application_id": a.application_id, "to": a.to_address, "subject": a.subject, "body": a.body,
        "attachment_ids": a.attachment_ids, "status": a.status, "content_hash": a.content_hash,
        "approved_at": iso(a.approved_at), "gmail_draft_id": a.gmail_draft_id, "gmail_message_id": a.gmail_message_id,
        "sent_at": iso(a.sent_at), "error": a.error, "created_at": iso(a.created_at), "updated_at": iso(a.updated_at),
        "kind": a.kind, "parent_id": a.parent_id, "replied_at": iso(a.replied_at), "reply_subject": a.reply_subject, "reply_hint": a.reply_hint, "reply_checked_at": iso(a.reply_checked_at),
        "follow_up_dismissed": a.follow_up_dismissed,
        "job": {"id": app.job.id, "title": app.job.title, "company": app.job.company, "url": app.job.url} if app else None,
    }


def application_out(a: Application, approvals: list[EmailApproval] | None = None, replied_at=None, reply_subject=None, stored_hint=None) -> dict:
    from huntly.services.followups import reply_hint

    if approvals is not None:
        replied = [x for x in approvals if x.replied_at]
        replied_at = min((x.replied_at for x in replied), default=None)
        reply_subject = next((x.reply_subject for x in replied if x.reply_subject), None)
        stored_hint = next((x.reply_hint for x in replied if x.reply_hint), None)
    return {
        "replied_at": iso(replied_at),
        "reply_subject": reply_subject,
        "reply_hint": stored_hint or reply_hint(reply_subject),
        "id": a.id, "status": a.status, "job": job_out(a.job), "cv_document_id": a.cv_document_id,
        "cover_letter_document_id": a.cover_letter_document_id, "contact_email": a.contact_email, "notes": a.notes,
        "created_at": iso(a.created_at), "updated_at": iso(a.updated_at), "applied_at": iso(a.applied_at),
        "approvals": [approval_out(x) for x in approvals] if approvals is not None else None,
    }


def audit_out(a: AuditLog) -> dict:
    return {"id": a.id, "ts": iso(a.ts), "actor": a.actor, "action": a.action, "entity": a.entity, "entity_id": a.entity_id, "detail": a.detail}


def notification_out(n: Notification) -> dict:
    return {"id": n.id, "ts": iso(n.ts), "level": n.level, "title": n.title, "body": n.body, "read": n.read}


def run_out(r: JobRun) -> dict:
    return {"id": r.id, "kind": r.kind, "trigger": r.trigger, "started_at": iso(r.started_at), "finished_at": iso(r.finished_at), "status": r.status, "stats": r.stats, "error": r.error}
