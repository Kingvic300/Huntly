"""Applications, the email approval gate, documents and the digest."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from huntly.api.deps import get_ctx, require_unlocked
from huntly.api.serializers import application_out, approval_out, document_out
from huntly.config import MAX_UPLOAD_BYTES
from huntly.context import AppContext
from huntly.models import Application, Document, EmailApproval, Job
from huntly.services import applications as svc
from huntly.services import store
from huntly.services.digest import build_digest, render_digest, send_digest
from huntly.services.documents import detect_upload_type, safe_filename, sha256_file
from huntly.services.gmail import GmailError

router = APIRouter()


def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(404, str(exc))
    if isinstance(exc, (svc.ApprovalError, ValueError, GmailError)):
        return HTTPException(400, str(exc))
    raise exc


# --- applications ----------------------------------------------------------------
class ApplicationIn(BaseModel):
    job_id: int


class ApplicationPatch(BaseModel):
    status: Literal["preparing", "awaiting_approval", "applied", "interviewing", "offer", "rejected", "withdrawn"] | None = None
    notes: str | None = Field(None, max_length=20000)
    contact_email: str | None = Field(None, max_length=320)


@router.get("/applications")
def list_applications(status: str | None = None, ctx: AppContext = Depends(get_ctx)):
    from sqlalchemy import func

    stmt = select(Application).order_by(Application.updated_at.desc())
    if status:
        stmt = stmt.where(Application.status.in_(status.split(",")))
    with ctx.db.session() as s:
        replies = {
            app_id: (at, subj, hint)
            for app_id, at, subj, hint in s.execute(
                select(
                    EmailApproval.application_id,
                    func.min(EmailApproval.replied_at),
                    func.max(EmailApproval.reply_subject),
                    func.max(EmailApproval.reply_hint),
                ).group_by(EmailApproval.application_id)
            ).all()
        }
        out = []
        for a in s.scalars(stmt):
            at, subj, hint = replies.get(a.id, (None, None, None))
            out.append(application_out(a, replied_at=at, reply_subject=subj, stored_hint=hint))
        return out


@router.post("/applications", status_code=201)
def create_application(body: ApplicationIn, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        job = s.get(Job, body.job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        existing = s.scalar(select(Application).where(Application.job_id == job.id))
        if existing:
            return application_out(existing, [])
        app = Application(job_id=job.id, contact_email=job.apply_email)
        s.add(app)
        if job.status == "new":
            job.status = "saved"
        s.flush()
        store.audit(s, "user", "application.created", "application", app.id, job_id=job.id)
        return application_out(app, [])


@router.get("/applications/{app_id}")
def get_application(app_id: int, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        app = s.get(Application, app_id)
        if app is None:
            raise HTTPException(404, "Application not found")
        approvals = list(s.scalars(select(EmailApproval).where(EmailApproval.application_id == app_id).order_by(EmailApproval.id.desc())))
        return application_out(app, approvals)


@router.patch("/applications/{app_id}")
def patch_application(app_id: int, body: ApplicationPatch, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        app = s.get(Application, app_id)
        if app is None:
            raise HTTPException(404, "Application not found")
        if body.status and body.status != app.status:
            store.audit(s, "user", "application.status_changed", "application", app.id, old=app.status, new=body.status)
            app.status = body.status
        if body.notes is not None:
            app.notes = body.notes
        if body.contact_email is not None:
            if body.contact_email and not svc.EMAIL_RE.match(body.contact_email):
                raise HTTPException(400, "Invalid email address")
            app.contact_email = body.contact_email or None
        return application_out(app)


@router.delete("/applications/{app_id}")
def delete_application(app_id: int, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        app = s.get(Application, app_id)
        if app is None:
            raise HTTPException(404, "Application not found")
        s.delete(app)
        store.audit(s, "user", "application.deleted", "application", app_id)
    return {"ok": True}


class GenerateIn(BaseModel):
    format: Literal["pdf", "docx"] = "pdf"
    use_llm: bool = True


@router.post("/applications/{app_id}/documents")
def generate(app_id: int, body: GenerateIn, ctx: AppContext = Depends(get_ctx)):
    try:
        return svc.generate_documents(ctx, app_id, body.format, body.use_llm and ctx.vault.unlocked)
    except Exception as exc:
        raise _err(exc)


class PrepareIn(BaseModel):
    to: str | None = Field(None, max_length=320)


@router.post("/applications/{app_id}/email", status_code=201)
def prepare(app_id: int, body: PrepareIn, ctx: AppContext = Depends(get_ctx)):
    try:
        approval_id = svc.prepare_email(ctx, app_id, body.to)
    except Exception as exc:
        raise _err(exc)
    with ctx.db.session() as s:
        return approval_out(s.get(EmailApproval, approval_id))


# --- approvals -----------------------------------------------------------------
class ApprovalPatch(BaseModel):
    to: str | None = Field(None, max_length=320)
    subject: str | None = Field(None, max_length=300)
    body: str | None = Field(None, max_length=50000)
    attachment_ids: list[int] | None = None


class ApproveIn(BaseModel):
    confirm: bool
    content_hash: str = Field(min_length=64, max_length=64)


@router.get("/approvals")
def list_approvals(status: str | None = None, ctx: AppContext = Depends(get_ctx)):
    stmt = select(EmailApproval).order_by(EmailApproval.id.desc())
    if status:
        stmt = stmt.where(EmailApproval.status.in_(status.split(",")))
    with ctx.db.session() as s:
        return [approval_out(a) for a in s.scalars(stmt)]


@router.get("/approvals/{approval_id}")
def get_approval(approval_id: int, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        a = s.get(EmailApproval, approval_id)
        if a is None:
            raise HTTPException(404, "Approval not found")
        out = approval_out(a)
        out["attachments"] = [document_out(d) for d in s.scalars(select(Document).where(Document.id.in_(a.attachment_ids or [])))]
        return out


@router.patch("/approvals/{approval_id}")
def patch_approval(approval_id: int, body: ApprovalPatch, ctx: AppContext = Depends(get_ctx)):
    try:
        svc.edit_approval(ctx, approval_id, to=body.to, subject=body.subject, body=body.body, attachment_ids=body.attachment_ids)
    except Exception as exc:
        raise _err(exc)
    return get_approval(approval_id, ctx)


@router.post("/approvals/{approval_id}/draft")
def draft(approval_id: int, ctx: AppContext = Depends(require_unlocked)):
    try:
        draft_id = svc.push_draft(ctx, approval_id)
    except Exception as exc:
        raise _err(exc)
    return {"ok": True, "draft_id": draft_id}


@router.post("/approvals/{approval_id}/approve")
def approve(approval_id: int, body: ApproveIn, ctx: AppContext = Depends(get_ctx)):
    try:
        svc.approve(ctx, approval_id, confirm=body.confirm, expected_hash=body.content_hash)
    except Exception as exc:
        raise _err(exc)
    return get_approval(approval_id, ctx)


@router.post("/approvals/{approval_id}/reject")
def reject(approval_id: int, ctx: AppContext = Depends(get_ctx)):
    try:
        svc.reject(ctx, approval_id)
    except Exception as exc:
        raise _err(exc)
    return get_approval(approval_id, ctx)


@router.post("/approvals/{approval_id}/send")
def send(approval_id: int, ctx: AppContext = Depends(require_unlocked)):
    try:
        message_id = svc.send(ctx, approval_id)
    except Exception as exc:
        raise _err(exc)
    return {"ok": True, "message_id": message_id}


# --- replies and follow-ups ---------------------------------------------------
@router.get("/follow-ups")
def follow_ups(ctx: AppContext = Depends(get_ctx)):
    from huntly.services.followups import due_follow_ups

    return due_follow_ups(ctx)


@router.post("/replies/check")
def replies_check(ctx: AppContext = Depends(require_unlocked)):
    from huntly.services.followups import check_replies

    try:
        return check_replies(ctx, trigger="user")
    except GmailError as exc:
        raise HTTPException(400, str(exc))


@router.post("/approvals/{approval_id}/follow-up", status_code=201)
def make_follow_up(approval_id: int, ctx: AppContext = Depends(get_ctx)):
    from huntly.services.followups import create_follow_up

    try:
        new_id = create_follow_up(ctx, approval_id)
    except Exception as exc:
        raise _err(exc)
    return get_approval(new_id, ctx)


@router.post("/approvals/{approval_id}/dismiss-follow-up")
def skip_follow_up(approval_id: int, ctx: AppContext = Depends(get_ctx)):
    from huntly.services.followups import dismiss_follow_up

    try:
        dismiss_follow_up(ctx, approval_id)
    except Exception as exc:
        raise _err(exc)
    return {"ok": True}


# --- documents -----------------------------------------------------------------
@router.get("/documents")
def list_documents(kind: str | None = None, ctx: AppContext = Depends(get_ctx)):
    stmt = select(Document).order_by(Document.id.desc())
    if kind:
        stmt = stmt.where(Document.kind.in_(kind.split(",")))
    with ctx.db.session() as s:
        return [document_out(d) for d in s.scalars(stmt)]


@router.post("/documents", status_code=201)
async def upload_document(file: UploadFile = File(...), title: str = Form(""), ctx: AppContext = Depends(get_ctx)):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    kind = detect_upload_type(data[:8], file.filename or "")
    if kind is None:
        raise HTTPException(415, "Only PDF and DOCX files are accepted (checked by content, not just extension)")
    name = safe_filename(Path(file.filename or "cv").stem)
    dest = ctx.paths.documents / f"base-{name}-{sha256_hex(data)[:8]}.{kind}"
    dest.write_bytes(data)
    with ctx.db.session() as s:
        doc = Document(kind="base_cv", title=(title or Path(file.filename or 'CV').stem)[:300], format=kind, path=str(dest), sha256=sha256_file(dest), size=len(data), meta={"original_name": (file.filename or "")[:200]})
        s.add(doc)
        s.flush()
        store.audit(s, "user", "document.uploaded", "document", doc.id)
        return document_out(doc)


def sha256_hex(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


@router.get("/documents/{doc_id}/file")
def download_document(doc_id: int, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        d = s.get(Document, doc_id)
        if d is None:
            raise HTTPException(404, "Document not found")
        path = Path(d.path).resolve()
    if ctx.paths.documents.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "File missing")
    media = "application/pdf" if path.suffix == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(path, media_type=media, filename=path.name)


@router.post("/documents/{doc_id}/parse")
def parse_document(doc_id: int, ctx: AppContext = Depends(get_ctx)):
    """Read a CV into profile fields for the user to review. Runs locally; nothing is saved here."""
    from huntly.services.cv_import import ImportError_, extract_text, parse_cv

    with ctx.db.session() as s:
        d = s.get(Document, doc_id)
        if d is None:
            raise HTTPException(404, "Document not found")
        path, fmt = Path(d.path).resolve(), d.format
    if ctx.paths.documents.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "File missing")
    try:
        result = parse_cv(extract_text(path, fmt))
    except ImportError_ as exc:
        raise HTTPException(400, str(exc))
    with ctx.db.session() as s:
        store.audit(s, "user", "document.parsed", "document", doc_id, sections=",".join(result["sections_found"]))
    return result


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        d = s.get(Document, doc_id)
        if d is None:
            raise HTTPException(404, "Document not found")
        path = Path(d.path).resolve()
        if ctx.paths.documents.resolve() in path.parents and path.is_file():
            path.unlink()
        s.delete(d)
        store.audit(s, "user", "document.deleted", "document", doc_id)
    return {"ok": True}


# --- digest --------------------------------------------------------------------
@router.get("/digest/preview")
def digest_preview(ctx: AppContext = Depends(get_ctx)):
    d = build_digest(ctx)
    subject, text, html = render_digest(d)
    return {"subject": subject, "text": text, "html": html, "data": d}


@router.post("/digest/send")
def digest_send(ctx: AppContext = Depends(require_unlocked)):
    try:
        return send_digest(ctx, trigger="manual")
    except GmailError as exc:
        raise HTTPException(400, str(exc))
