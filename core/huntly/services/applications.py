"""Applications: document generation and the email approval gate.

The approval gate is the only code path that can send an application email:

1. ``prepare_email`` creates an :class:`EmailApproval` in ``pending`` state.
2. The user may edit it; every edit resets it to ``pending``.
3. ``approve`` records the exact content hash the user approved.
4. ``send`` refuses unless the approval exists, is recent, was made by the user,
   and the content is byte-for-byte what was approved.

Background workers never call ``approve`` or ``send``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from huntly.context import AppContext
from huntly.models import Application, Document, EmailApproval, Job
from huntly.services import store
from huntly.services.ats import ats_report
from huntly.services.documents import (
    allowed_corpus_for_letter,
    cv_plaintext,
    find_fabrications,
    render_cv_docx,
    render_cv_pdf,
    render_letter_docx,
    render_letter_pdf,
    safe_filename,
    sha256_file,
    tailor,
    template_paragraphs,
)
from huntly.services.gmail import build_message
from huntly.services.llm import LLMError
from huntly.services.profile import load_profile, profile_corpus

log = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
APP_STATUSES = ["preparing", "awaiting_approval", "applied", "interviewing", "offer", "rejected", "withdrawn"]


class ApprovalError(Exception):
    pass


def content_hash(to: str, subject: str, body: str, attachment_ids: list[int]) -> str:
    payload = json.dumps([to.strip().lower(), subject, body, sorted(attachment_ids)], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _add_document(s: Session, ctx: AppContext, kind: str, title: str, job_id: int | None, path: Path, meta: dict) -> Document:
    doc = Document(
        kind=kind, title=title, job_id=job_id, format=path.suffix.lstrip("."), path=str(path), sha256=sha256_file(path), size=path.stat().st_size, meta=meta
    )
    s.add(doc)
    s.flush()
    return doc


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    for i in range(2, 100):
        candidate = path.with_name(f"{path.stem}-{i}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise ValueError("Too many documents with the same name")


def generate_documents(ctx: AppContext, application_id: int, fmt: str = "pdf", use_llm: bool = True) -> dict:
    if fmt not in ("pdf", "docx"):
        raise ValueError("format must be pdf or docx")
    with ctx.db.session() as s:
        app = s.get(Application, application_id)
        if app is None:
            raise LookupError("application not found")
        job = app.job
        profile = load_profile(s)
        if not profile.full_name or not (profile.experience or profile.skills or profile.summary):
            raise ValueError("Complete your profile (name plus experience, skills or summary) before generating documents")
        t = tailor(profile, job.title, job.description)
        corpus = allowed_corpus_for_letter(profile, job.title, job.company or "")
        warnings: list[str] = []
        sources: dict[str, str] = {"summary": "profile", "letter": "template"}
        client = ctx.groq() if use_llm else None

        if client is not None and profile.summary:
            try:
                summary = client.tailored_summary(profile_corpus(profile), profile.summary, job.title, job.company or "", job.description)
                problems = find_fabrications(summary, corpus)
                if problems:
                    warnings.append("AI summary discarded: it mentioned things not in your profile (" + ", ".join(problems[:8]) + ").")
                else:
                    t.summary_override, sources["summary"] = summary, "groq"
            except LLMError as exc:
                warnings.append(f"AI summary unavailable ({exc}); used your own summary.")

        person = safe_filename(profile.full_name, 40)
        role = f"{safe_filename(job.company or 'Company', 30)}-{safe_filename(job.title, 40)}"
        cv_path = _unique(ctx.paths.documents / f"{person}-CV-{role}.{fmt}")
        pages = render_cv_pdf(t, cv_path) if fmt == "pdf" else (render_cv_docx(t, cv_path) or None)
        ats = ats_report(cv_text=cv_plaintext(t), job_title=job.title, job_text=job.description, profile=profile, fmt=fmt, pages=pages, filename=cv_path.name)

        paragraphs = template_paragraphs(t, job.title, job.company or "")
        if client is not None:
            try:
                drafted = client.cover_letter_paragraphs(profile_corpus(profile)[:5000], job.title, job.company or "", job.description)
                problems = sorted({p for para in drafted for p in find_fabrications(para, corpus)})
                if problems:
                    warnings.append("AI letter discarded: it mentioned things not in your profile (" + ", ".join(problems[:8]) + "). Used the template instead.")
                else:
                    paragraphs, sources["letter"] = drafted, "groq"
            except LLMError as exc:
                warnings.append(f"AI letter unavailable ({exc}); used the template.")

        cl_path = _unique(ctx.paths.documents / f"{person}-Cover-Letter-{role}.{fmt}")
        (render_letter_pdf if fmt == "pdf" else render_letter_docx)(profile, paragraphs, job.company or "", cl_path)

        source = "groq" if "groq" in sources.values() else "template"
        cv = _add_document(s, ctx, "tailored_cv", f"CV for {job.title}", job.id, cv_path, {"relevant_skills": t.relevant_skills, "ats": ats, "summary_source": sources["summary"], "source": source, "pages": pages})
        cl = _add_document(s, ctx, "cover_letter", f"Cover letter for {job.title}", job.id, cl_path, {"source": sources["letter"], "paragraphs": paragraphs, "warnings": warnings})
        app.cv_document_id, app.cover_letter_document_id = cv.id, cl.id
        store.audit(s, "user", "documents.generated", "application", app.id, cv=cv.id, cover_letter=cl.id, source=source, ats_score=ats["score"])
        return {"cv_document_id": cv.id, "cover_letter_document_id": cl.id, "warnings": warnings, "source": source, "ats": ats}


def prepare_email(ctx: AppContext, application_id: int, to: str | None = None) -> int:
    with ctx.db.session() as s:
        app = s.get(Application, application_id)
        if app is None:
            raise LookupError("application not found")
        job: Job = app.job
        profile = load_profile(s)
        address = (to or app.contact_email or job.apply_email or "").strip()
        attachments = [i for i in (app.cv_document_id, app.cover_letter_document_id) if i]
        subject = f"Application: {job.title}" + (f" — {profile.full_name}" if profile.full_name else "")
        letter = s.get(Document, app.cover_letter_document_id) if app.cover_letter_document_id else None
        paras = (letter.meta or {}).get("paragraphs") if letter else None
        greeting = f"Dear {job.company + ' ' if job.company else ''}Hiring Team,"
        body = "\n\n".join([greeting, *(paras or [f"Please find attached my application for the {job.title} role."]), f"Kind regards,\n{profile.full_name}"])
        approval = EmailApproval(
            application_id=app.id, to_address=address, subject=subject, body=body, attachment_ids=attachments,
            status="pending", content_hash=content_hash(address, subject, body, attachments),
        )
        s.add(approval)
        app.status = "awaiting_approval"
        s.flush()
        store.audit(s, "user", "approval.created", "email_approval", approval.id, application_id=app.id)
        store.notify(s, "Email awaiting your approval", f"{job.title} — {job.company or ''}")
        return approval.id


def edit_approval(ctx: AppContext, approval_id: int, *, to: str | None, subject: str | None, body: str | None, attachment_ids: list[int] | None) -> None:
    with ctx.db.session() as s:
        a = _get_open(s, approval_id)
        if to is not None:
            a.to_address = to.strip()
        if subject is not None:
            a.subject = subject[:300]
        if body is not None:
            a.body = body
        if attachment_ids is not None:
            for doc_id in attachment_ids:
                if s.get(Document, doc_id) is None:
                    raise ValueError(f"document {doc_id} not found")
            a.attachment_ids = list(attachment_ids)
        a.content_hash = content_hash(a.to_address, a.subject, a.body, a.attachment_ids)
        a.status, a.approved_hash, a.approved_at = "pending", None, None
        store.audit(s, "user", "approval.edited", "email_approval", a.id)


def _get_open(s: Session, approval_id: int) -> EmailApproval:
    a = s.get(EmailApproval, approval_id)
    if a is None:
        raise LookupError("approval not found")
    if a.status in ("sent", "rejected"):
        raise ApprovalError(f"Email already {a.status}")
    return a


def _parent_header(s: Session, a: EmailApproval) -> str | None:
    parent = s.get(EmailApproval, a.parent_id) if a.parent_id else None
    return parent.rfc_message_id if parent else None


def _message(ctx: AppContext, s: Session, a: EmailApproval, sender: str):
    paths = []
    for doc_id in a.attachment_ids:
        doc = s.get(Document, doc_id)
        if doc is None or not Path(doc.path).is_file():
            raise ApprovalError(f"Attachment {doc_id} is missing")
        paths.append(Path(doc.path))
    return build_message(sender=sender, to=a.to_address, subject=a.subject, text=a.body, attachments=paths, in_reply_to=_parent_header(s, a))


def push_draft(ctx: AppContext, approval_id: int) -> str:
    """Create or update the Gmail draft. Creating a draft never sends anything."""
    gmail = ctx.gmail()
    sender = gmail.email_address()
    with ctx.db.session() as s:
        a = _get_open(s, approval_id)
        if not EMAIL_RE.match(a.to_address or ""):
            raise ApprovalError("Recipient address is missing or invalid")
        msg = _message(ctx, s, a, sender)
        thread = a.gmail_thread_id
        a.gmail_draft_id = gmail.update_draft(a.gmail_draft_id, msg, thread) if a.gmail_draft_id else gmail.create_draft(msg, thread)
        store.audit(s, "user", "approval.draft_saved", "email_approval", a.id, draft_id=a.gmail_draft_id)
        return a.gmail_draft_id


def approve(ctx: AppContext, approval_id: int, *, confirm: bool, expected_hash: str) -> None:
    if confirm is not True:
        raise ApprovalError("Explicit confirmation is required")
    with ctx.db.session() as s:
        a = _get_open(s, approval_id)
        if not EMAIL_RE.match(a.to_address or ""):
            raise ApprovalError("Recipient address is missing or invalid")
        if expected_hash != a.content_hash:
            raise ApprovalError("The email changed since you reviewed it. Review it again before approving.")
        a.status, a.approved_hash, a.approved_at = "approved", a.content_hash, datetime.now(timezone.utc)
        store.audit(s, "user", "approval.approved", "email_approval", a.id, to=a.to_address, content_hash=a.content_hash)


def reject(ctx: AppContext, approval_id: int) -> None:
    with ctx.db.session() as s:
        a = _get_open(s, approval_id)
        a.status = "rejected"
        a.application.status = "preparing"
        store.audit(s, "user", "approval.rejected", "email_approval", a.id)


def send(ctx: AppContext, approval_id: int) -> str:
    with ctx.db.session() as s:
        window = int(store.get_setting(s, "approval_window_minutes") or 15)
        a = _get_open(s, approval_id)
        if a.status != "approved" or not a.approved_hash or not a.approved_at:
            raise ApprovalError("This email has not been approved")
        if a.approved_hash != a.content_hash:
            raise ApprovalError("Email content changed after approval. Approve it again.")
        approved_at = a.approved_at if a.approved_at.tzinfo else a.approved_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - approved_at > timedelta(minutes=window):
            a.status, a.approved_hash, a.approved_at = "pending", None, None
            raise ApprovalError(f"Approval expired after {window} minutes. Review and approve again.")
    gmail = ctx.gmail()
    sender = gmail.email_address()
    with ctx.db.session() as s:
        a = s.get(EmailApproval, approval_id)
        try:
            msg = _message(ctx, s, a, sender)
            thread = a.gmail_thread_id
            if a.gmail_draft_id:
                gmail.update_draft(a.gmail_draft_id, msg, thread)
            else:
                a.gmail_draft_id = gmail.create_draft(msg, thread)
            sent = gmail.send_draft(a.gmail_draft_id)
            message_id = sent.id
        except Exception as exc:
            a.status, a.error = "failed", str(exc)[:500]
            store.audit(s, "user", "approval.send_failed", "email_approval", a.id, error=str(exc)[:300])
            s.commit()
            raise ApprovalError(f"Send failed: {exc}") from exc
        now = datetime.now(timezone.utc)
        a.status, a.sent_at, a.gmail_message_id, a.error = "sent", now, message_id, None
        a.gmail_thread_id = sent.thread_id or a.gmail_thread_id
        try:
            a.rfc_message_id = gmail.message_id_header(message_id)
        except Exception:  # reply threading still works through the Gmail thread id
            a.rfc_message_id = None
        if a.kind == "application":
            if a.application.status in ("preparing", "awaiting_approval"):
                a.application.status = "applied"
            a.application.applied_at = a.application.applied_at or now
            a.application.job.status = "applied"
        store.audit(s, "user", "approval.sent", "email_approval", a.id, kind=a.kind, to=a.to_address, message_id=message_id, content_hash=a.content_hash)
        store.notify(s, "Follow-up sent" if a.kind == "follow_up" else "Application sent", f"{a.subject} to {a.to_address}", "success")
        return message_id
