"""Health, onboarding, vault, credentials, Gmail connection, settings, notifications, audit, search."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text

from huntly import __version__
from huntly.api.deps import get_ctx, require_unlocked
from huntly.api.serializers import audit_out, job_out, notification_out, run_out
from huntly.config import TIMEZONE_NAME
from huntly.context import AppContext
from huntly.models import Application, AuditLog, EmailApproval, Job, JobRun, Notification
from huntly.security.vault import InvalidPassword, VaultError, keyring_available
from huntly.services import store
from huntly.services.gmail import GmailError, run_installed_flow, validate_client_config

router = APIRouter()


@router.get("/health")
def health(ctx: AppContext = Depends(get_ctx)):
    db_ok = True
    try:
        with ctx.db.session() as s:
            s.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    st = ctx.vault.status()
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "database": "ok" if db_ok else "error",
        "vault": {"initialized": st.initialized, "unlocked": st.unlocked},
        "scheduler": ctx.scheduler.status() if ctx.scheduler else {"running": False},
        "timezone": TIMEZONE_NAME,
        "data_dir": str(ctx.paths.root),
    }


# --- onboarding / vault ------------------------------------------------------
class CreateVault(BaseModel):
    password: str = Field(min_length=1, max_length=1024)
    use_keyring: bool = False


class Unlock(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class ChangePassword(BaseModel):
    old_password: str
    new_password: str


@router.get("/onboarding/status")
def onboarding_status(ctx: AppContext = Depends(get_ctx)):
    st = ctx.vault.status()
    with ctx.db.session() as s:
        complete = bool(store.get_setting(s, "onboarding_complete"))
        creds = store.credential_status(s)
    return {
        "vault_initialized": st.initialized,
        "vault_unlocked": st.unlocked,
        "keyring_available": st.keyring_available,
        "keyring_enabled": st.keyring_enabled,
        "onboarding_complete": complete and st.initialized,
        "credentials": creds,
        "data_dir": str(ctx.paths.root),
    }


@router.post("/vault/create")
def vault_create(body: CreateVault, ctx: AppContext = Depends(get_ctx)):
    try:
        ctx.vault.create(body.password, use_keyring=False)
    except VaultError as exc:
        raise HTTPException(400, str(exc))
    # A new vault means a new key: ciphertexts from any previous vault (e.g. after the
    # user deleted vault.json to reset a forgotten password) can never be decrypted.
    with ctx.db.session() as s:
        for row in s.scalars(select(store.Secret)):
            s.delete(row)
    warning = None
    if body.use_keyring:
        try:
            ctx.vault.enable_keyring()
        except Exception as exc:
            warning = f"OS keychain unavailable ({type(exc).__name__}); you will be asked for the master password at start-up."
    with ctx.db.session() as s:
        store.audit(s, "user", "vault.created", "vault", keyring=body.use_keyring and not warning)
        # The remaining setup steps are optional; setup never has to be repeated once the vault exists.
        store.set_setting(s, "onboarding_complete", True)
    return {"ok": True, "warning": warning}


@router.post("/vault/unlock")
def vault_unlock(body: Unlock, ctx: AppContext = Depends(get_ctx)):
    try:
        ctx.vault.unlock(body.password)
    except InvalidPassword:
        raise HTTPException(401, "Incorrect master password")
    except VaultError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@router.post("/vault/lock")
def vault_lock(ctx: AppContext = Depends(get_ctx)):
    ctx.vault.lock()
    return {"ok": True}


@router.post("/vault/change-password")
def vault_change(body: ChangePassword, ctx: AppContext = Depends(get_ctx)):
    try:
        ctx.vault.change_password(body.old_password, body.new_password)
    except InvalidPassword:
        raise HTTPException(401, "Incorrect current password")
    except VaultError as exc:
        raise HTTPException(400, str(exc))
    with ctx.db.session() as s:
        store.audit(s, "user", "vault.password_changed", "vault")
    return {"ok": True}


class KeyringToggle(BaseModel):
    enabled: bool


@router.post("/vault/keyring")
def vault_keyring(body: KeyringToggle, ctx: AppContext = Depends(require_unlocked)):
    if body.enabled:
        if not keyring_available():
            raise HTTPException(400, "No OS keychain backend is available on this system")
        try:
            ctx.vault.enable_keyring()
        except Exception as exc:
            raise HTTPException(400, f"Could not store key in OS keychain: {type(exc).__name__}")
    else:
        ctx.vault.disable_keyring()
    return {"ok": True}


@router.post("/onboarding/complete")
def onboarding_complete(ctx: AppContext = Depends(require_unlocked)):
    with ctx.db.session() as s:
        store.set_setting(s, "onboarding_complete", True)
        store.audit(s, "user", "onboarding.completed", "settings")
    return {"ok": True}


# --- credentials --------------------------------------------------------------
class CredentialIn(BaseModel):
    value: str = Field(min_length=1, max_length=20000)


@router.get("/credentials")
def credentials(ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        return store.credential_status(s)


@router.put("/credentials/{name}")
def put_credential(name: str, body: CredentialIn, ctx: AppContext = Depends(require_unlocked)):
    if name not in store.CREDENTIALS or name == "google_token":
        raise HTTPException(404, "Unknown credential")
    value = body.value.strip()
    if name == "google_oauth_client":
        try:
            validate_client_config(value)
        except GmailError as exc:
            raise HTTPException(400, str(exc))
    with ctx.db.session() as s:
        store.put_secret(s, ctx.vault, name, value)
        store.audit(s, "user", "credential.saved", "credential", name)
    return {"ok": True}


@router.delete("/credentials/{name}")
def delete_credential(name: str, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        removed = store.delete_secret(s, name)
        store.audit(s, "user", "credential.deleted", "credential", name)
    return {"ok": removed}


# --- gmail --------------------------------------------------------------------
@router.get("/gmail/status")
def gmail_status(ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        has_client = s.get(store.Secret, "google_oauth_client") is not None
        email = store.get_setting(s, "gmail_address")
    can_track = can_read = None
    if ctx.gmail_connected() and ctx.vault.unlocked:
        try:
            g = ctx.gmail()
            can_track, can_read = g.can_read_metadata(), g.can_read_bodies()
        except Exception:
            can_track = can_read = None
    return {
        "client_configured": has_client,
        "connected": ctx.gmail_connected(),
        "reply_tracking_permission": can_track,
        "reply_reading_permission": can_read,
        "email": email,
        "flow_running": ctx.oauth_state.running,
        "flow_error": ctx.oauth_state.error,
    }


@router.post("/gmail/connect")
def gmail_connect(ctx: AppContext = Depends(require_unlocked)):
    raw = ctx.secret("google_oauth_client")
    if not raw:
        raise HTTPException(400, "Add your Google OAuth client JSON first")
    config = validate_client_config(raw)

    def on_success(token_json: str) -> None:
        ctx.store_secret("google_token", token_json)
        address = None
        try:
            address = ctx.gmail().email_address()
        except Exception:
            pass
        with ctx.db.session() as s:
            store.set_setting(s, "gmail_address", address)
            store.audit(s, "user", "gmail.connected", "gmail", address=address or "")
            store.notify(s, "Gmail connected", address or "", "success")

    from huntly.services.gmail import scopes_for

    with ctx.db.session() as s:
        read_replies = bool(store.get_setting(s, "reply_body_analysis"))
    try:
        run_installed_flow(config, ctx.oauth_state, on_success, scopes_for(read_replies))
    except GmailError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True, "message": "Complete the consent screen in your browser."}


@router.post("/gmail/disconnect")
def gmail_disconnect(ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        store.delete_secret(s, "google_token")
        store.set_setting(s, "gmail_address", None)
        store.audit(s, "user", "gmail.disconnected", "gmail")
    return {"ok": True}


@router.post("/gmail/test")
def gmail_test(ctx: AppContext = Depends(require_unlocked)):
    try:
        address = ctx.gmail().email_address()
    except GmailError as exc:
        raise HTTPException(400, str(exc))
    with ctx.db.session() as s:
        store.set_setting(s, "gmail_address", address)
    return {"ok": True, "email": address}


# --- settings -----------------------------------------------------------------
class SettingsIn(BaseModel):
    collection_interval_minutes: int | None = Field(None, ge=15, le=1440)
    collection_enabled: bool | None = None
    digest_enabled: bool | None = None
    digest_time: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    digest_min_score: int | None = Field(None, ge=0, le=100)
    min_score_to_show: int | None = Field(None, ge=0, le=100)
    groq_model: str | None = Field(None, max_length=100, pattern=r"^[A-Za-z0-9._/-]+$")
    groq_enabled: bool | None = None
    approval_window_minutes: int | None = Field(None, ge=1, le=120)
    reply_tracking_enabled: bool | None = None
    follow_up_after_days: int | None = Field(None, ge=2, le=60)
    reply_body_analysis: bool | None = None


@router.get("/settings")
def get_settings(ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        out = store.all_settings(s)
    out["timezone"] = TIMEZONE_NAME
    return out


@router.put("/settings")
def put_settings(body: SettingsIn, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        for k, v in body.model_dump(exclude_none=True).items():
            store.set_setting(s, k, v)
        store.audit(s, "user", "settings.updated", "settings", keys=",".join(body.model_dump(exclude_none=True)))
    if ctx.scheduler:
        ctx.scheduler.reload()
    return get_settings(ctx)


# --- scheduler / runs -----------------------------------------------------------
@router.get("/scheduler")
def scheduler_status(ctx: AppContext = Depends(get_ctx)):
    status = ctx.scheduler.status() if ctx.scheduler else {"running": False, "jobs": []}
    with ctx.db.session() as s:
        runs = [run_out(r) for r in s.scalars(select(JobRun).order_by(JobRun.id.desc()).limit(20))]
    return {**status, "runs": runs}


# --- notifications / audit ------------------------------------------------------
@router.get("/notifications")
def notifications(ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        items = [notification_out(n) for n in s.scalars(select(Notification).order_by(Notification.id.desc()).limit(50))]
        unread = s.scalar(select(func.count()).select_from(Notification).where(Notification.read.is_(False)))
    return {"items": items, "unread": unread}


@router.post("/notifications/read-all")
def notifications_read(ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        for n in s.scalars(select(Notification).where(Notification.read.is_(False))):
            n.read = True
    return {"ok": True}


@router.get("/audit")
def audit_log(limit: int = 200, ctx: AppContext = Depends(get_ctx)):
    with ctx.db.session() as s:
        return [audit_out(a) for a in s.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000)))]


@router.get("/search")
def search(q: str, ctx: AppContext = Depends(get_ctx)):
    q = q.strip()[:100]
    if len(q) < 2:
        return {"jobs": [], "applications": [], "approvals": []}
    like = f"%{q}%"
    with ctx.db.session() as s:
        jobs = [job_out(j) for j in s.scalars(select(Job).where(or_(Job.title.ilike(like), Job.company.ilike(like))).order_by(Job.score.desc()).limit(8))]
        apps = [
            {"id": a.id, "status": a.status, "title": a.job.title, "company": a.job.company}
            for a in s.scalars(select(Application).join(Job).where(or_(Job.title.ilike(like), Job.company.ilike(like))).limit(5))
        ]
        approvals = [
            {"id": a.id, "subject": a.subject, "status": a.status}
            for a in s.scalars(select(EmailApproval).where(or_(EmailApproval.subject.ilike(like), EmailApproval.to_address.ilike(like))).limit(5))
        ]
    return {"jobs": jobs, "applications": apps, "approvals": approvals}


@router.get("/time")
def now():
    from huntly.config import TZ

    return {"now": datetime.now(TZ).isoformat(), "timezone": TIMEZONE_NAME}
