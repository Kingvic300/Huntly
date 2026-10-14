"""Reply tracking and follow-ups for sent applications.

Replies are detected by reading only the sender headers of the Gmail thread that the
application started (``gmail.metadata`` scope). Message bodies are never read.
Follow-ups are ordinary emails that go through the same approval gate; nothing here sends.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr

from sqlalchemy import select

from huntly.context import AppContext
from huntly.models import EmailApproval
from huntly.services import store
from huntly.services.applications import ApprovalError, content_hash

log = logging.getLogger(__name__)

TRACK_DAYS = 60

INTERVIEW_HINT = re.compile(r"(?i)\b(interview|call|chat|meet|meeting|schedul\w*|availability|next steps?|assessment|technical test|screening)\b")
DECLINE_HINT = re.compile(r"(?i)\b(unsuccessful|regret|not (?:been )?(?:selected|moving forward|progress\w*)|other candidates|position (?:has been )?filled)\b")


OFFER_TEXT = re.compile(r"(?i)\b(pleased to offer|offer of employment|(?:job|formal|verbal) offer|would like to offer you|extend (?:you )?an offer)\b")
DECLINE_TEXT = re.compile(
    r"(?i)(regret to inform|unfortunately|not be moving forward|decided to (?:move forward|proceed|progress) with other|"
    r"not been successful|unsuccessful|will not be progressing|won't be progressing|position has (?:now )?been filled|"
    r"decided not to proceed|other candidates whose|not (?:be )?(?:able to )?offer you|no longer considering)"
)
INTERVIEW_TEXT = re.compile(
    r"(?i)(invite you to (?:an )?interview|interview with|schedule (?:a|an) (?:call|interview|chat)|your availability|"
    r"next (?:stage|step|round)|book a (?:time|slot)|calendly\.com|technical (?:assessment|test|interview)|"
    r"would (?:like|love) to (?:speak|chat|talk)|set up a (?:call|time)|move you forward)"
)


def classify_reply_text(text: str) -> str | None:
    """Local keyword classification of an employer's reply. The text is untrusted and only matched, never acted on."""
    if not text:
        return None
    if OFFER_TEXT.search(text):
        return "offer"
    if DECLINE_TEXT.search(text):
        return "declined"
    if INTERVIEW_TEXT.search(text):
        return "interview"
    return None


def reply_hint(subject: str | None) -> str | None:
    """Guess what a reply is about from its subject line alone."""
    if not subject:
        return None
    if DECLINE_HINT.search(subject):
        return "declined"
    if INTERVIEW_HINT.search(subject):
        return "interview"
    return None
MAX_FOLLOW_UPS = 2


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def check_replies(ctx: AppContext, trigger: str = "schedule") -> dict:
    gmail = ctx.gmail()
    if not gmail.can_read_metadata():
        return {"status": "needs_permission", "checked": 0, "replies": 0}
    me = gmail.email_address().lower()
    with ctx.db.session() as s:
        read_bodies = bool(store.get_setting(s, "reply_body_analysis")) and gmail.can_read_bodies()
    since = datetime.now(timezone.utc) - timedelta(days=TRACK_DAYS)
    with ctx.db.session() as s:
        threads = list(
            s.execute(
                select(EmailApproval.gmail_thread_id, EmailApproval.application_id)
                .where(EmailApproval.status == "sent", EmailApproval.gmail_thread_id.is_not(None), EmailApproval.replied_at.is_(None), EmailApproval.sent_at >= since)
                .distinct()
            ).all()
        )
    checked = replies = 0
    for thread_id, app_id in threads:
        try:
            senders = gmail.thread_senders(thread_id)
        except Exception as exc:
            log.warning("reply check failed for a thread: %s", type(exc).__name__)
            continue
        checked += 1
        theirs = sorted((int(m[1]), (m[2] if len(m) > 2 else ""), (m[3] if len(m) > 3 else "")) for m in senders if parseaddr(m[0])[1].lower() not in ("", me))
        now = datetime.now(timezone.utc)
        with ctx.db.session() as s:
            rows = list(s.scalars(select(EmailApproval).where(EmailApproval.gmail_thread_id == thread_id)))
            for a in rows:
                a.reply_checked_at = now
            if theirs:
                first_ms, subject, _ = theirs[0]
                latest_subject = theirs[-1][1] or subject
                hint = reply_hint(latest_subject)
                if read_bodies and theirs[-1][2]:
                    try:
                        hint = classify_reply_text(gmail.message_text(theirs[-1][2])) or hint
                    except Exception as exc:
                        log.warning("could not read reply for classification: %s", type(exc).__name__)
                at = datetime.fromtimestamp(first_ms / 1000, timezone.utc)
                for a in rows:
                    if a.status == "sent" and a.replied_at is None:
                        a.replied_at = at
                    if a.status == "sent":
                        a.reply_subject = (latest_subject or "")[:300] or None
                        a.reply_hint = hint
                replies += 1
                job = rows[0].application.job
                who = job.company or "An employer"
                title = {
                    "interview": f"{who} may want to interview you",
                    "offer": f"{who} may be making you an offer",
                    "declined": f"{who} replied about {job.title}, possibly a rejection",
                }.get(hint, f"Reply from {job.company or 'an employer'}")
                store.notify(s, title, f"Subject: {latest_subject}" if latest_subject else f"About {job.title}. Check your Gmail.", "success")
                store.audit(s, trigger if trigger != "schedule" else "scheduler", "reply.detected", "application", app_id)
    return {"status": "ok", "checked": checked, "replies": replies}


def _latest_sent(s, application_id: int) -> EmailApproval | None:
    return s.scalar(
        select(EmailApproval).where(EmailApproval.application_id == application_id, EmailApproval.status == "sent").order_by(EmailApproval.sent_at.desc()).limit(1)
    )


def due_follow_ups(ctx: AppContext) -> list[dict]:
    with ctx.db.session() as s:
        days = int(store.get_setting(s, "follow_up_after_days") or 7)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        app_ids = {r for (r,) in s.execute(select(EmailApproval.application_id).where(EmailApproval.status == "sent")).all()}
        out = []
        for app_id in app_ids:
            last = _latest_sent(s, app_id)
            if last is None or last.replied_at or last.follow_up_dismissed:
                continue
            if _aware(last.sent_at) > cutoff:
                continue
            app = last.application
            if app.status in ("rejected", "withdrawn", "offer", "interviewing"):
                continue
            thread = s.scalars(select(EmailApproval).where(EmailApproval.application_id == app_id)).all()
            if any(x.replied_at for x in thread):
                continue
            if any(x.kind == "follow_up" and x.status in ("pending", "approved", "failed") for x in thread):
                continue
            sent_follow_ups = sum(1 for x in thread if x.kind == "follow_up" and x.status == "sent")
            if sent_follow_ups >= MAX_FOLLOW_UPS:
                continue
            out.append(
                {
                    "approval_id": last.id,
                    "application_id": app_id,
                    "job_title": app.job.title,
                    "company": app.job.company,
                    "to": last.to_address,
                    "sent_at": store.iso(last.sent_at),
                    "days_waiting": (datetime.now(timezone.utc) - _aware(last.sent_at)).days,
                    "follow_ups_sent": sent_follow_ups,
                }
            )
        return sorted(out, key=lambda x: -x["days_waiting"])


def create_follow_up(ctx: AppContext, approval_id: int) -> int:
    from huntly.services.profile import load_profile

    with ctx.db.session() as s:
        last = s.get(EmailApproval, approval_id)
        if last is None:
            raise LookupError("email not found")
        if last.status != "sent":
            raise ApprovalError("You can only follow up on an email that was sent")
        thread = s.scalars(select(EmailApproval).where(EmailApproval.application_id == last.application_id)).all()
        if any(x.kind == "follow_up" and x.status in ("pending", "approved", "failed") for x in thread):
            raise ApprovalError("A follow-up for this application is already waiting for your review")
        job = last.application.job
        profile = load_profile(s)
        subject = last.subject if last.subject.lower().startswith("re:") else f"Re: {last.subject}"
        sent_on = _aware(last.sent_at).strftime("%d %B")
        body = "\n\n".join(
            [
                f"Dear {job.company + ' ' if job.company else ''}Hiring Team,",
                f"I'm following up on my application for the {job.title} role, which I sent on {sent_on}. "
                "I remain very interested in the position and would be glad to share anything else that would help.",
                "Thank you for your time and consideration.",
                f"Kind regards,\n{profile.full_name}",
            ]
        )
        f = EmailApproval(
            application_id=last.application_id,
            kind="follow_up",
            parent_id=last.id,
            gmail_thread_id=last.gmail_thread_id,
            to_address=last.to_address,
            subject=subject[:300],
            body=body,
            attachment_ids=[],
            status="pending",
            content_hash=content_hash(last.to_address, subject[:300], body, []),
        )
        s.add(f)
        s.flush()
        store.audit(s, "user", "follow_up.created", "email_approval", f.id, parent=last.id)
        return f.id


def dismiss_follow_up(ctx: AppContext, approval_id: int) -> None:
    with ctx.db.session() as s:
        a = s.get(EmailApproval, approval_id)
        if a is None:
            raise LookupError("email not found")
        a.follow_up_dismissed = True
        store.audit(s, "user", "follow_up.dismissed", "email_approval", a.id)
