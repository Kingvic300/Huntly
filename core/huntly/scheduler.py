"""Local background scheduler (APScheduler, in-process, Africa/Lagos timezone).

Jobs run only while the app is open, so a search that came due while it was closed runs
shortly after it opens. Nothing here can approve or send application emails; the only
email it sends is the digest to the user's own address.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import func, select

from huntly.config import TZ
from huntly.context import AppContext
from huntly.models import JobRun
from huntly.services import store

log = logging.getLogger(__name__)

# Lets the window and the core settle before the first search after opening.
STARTUP_DELAY_SECONDS = 20


class LocalScheduler:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.sched = BackgroundScheduler(timezone=TZ, job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600})

    def start(self) -> None:
        self.reload()
        self.sched.start()
        log.info("scheduler started")

    def shutdown(self) -> None:
        if self.sched.running:
            self.sched.shutdown(wait=False)

    def reload(self) -> None:
        with self.ctx.db.session() as s:
            settings = store.all_settings(s)
        for job_id in ("collect", "digest", "replies"):
            if self.sched.get_job(job_id):
                self.sched.remove_job(job_id)
        if settings.get("collection_enabled"):
            minutes = max(15, int(settings.get("collection_interval_minutes") or 60))
            self.sched.add_job(
                self._collect, IntervalTrigger(minutes=minutes, timezone=TZ), id="collect", name="Collect jobs", next_run_time=self._next_collect(minutes)
            )
        if settings.get("digest_enabled"):
            hh, mm = (str(settings.get("digest_time") or "08:00").split(":") + ["0"])[:2]
            self.sched.add_job(self._digest, CronTrigger(hour=int(hh), minute=int(mm), timezone=TZ), id="digest", name="Daily digest")
        if settings.get("reply_tracking_enabled"):
            self.sched.add_job(self._replies, IntervalTrigger(hours=2, timezone=TZ), id="replies", name="Check for replies")

    def _next_collect(self, minutes: int) -> datetime:
        """One interval after the last search, or shortly after opening if that time has passed."""
        with self.ctx.db.session() as s:
            last = s.scalar(select(func.max(JobRun.started_at)).where(JobRun.kind == "collect"))
        soon = datetime.now(TZ) + timedelta(seconds=STARTUP_DELAY_SECONDS)
        if last is None:
            return soon
        due = (last if last.tzinfo else last.replace(tzinfo=timezone.utc)) + timedelta(minutes=minutes)
        return max(due.astimezone(TZ), soon)

    def collect_soon(self) -> None:
        """Bring the next scheduled search forward to a few seconds from now."""
        job = self.sched.get_job("collect")
        if job:
            job.modify(next_run_time=datetime.now(TZ) + timedelta(seconds=3))

    def _collect(self) -> None:
        from huntly.services.collector import collect_all

        try:
            collect_all(self.ctx, trigger="schedule")
        except Exception:
            log.exception("scheduled collection failed")

    def _digest(self) -> None:
        from huntly.services.digest import send_digest

        if not self.ctx.vault.unlocked or not self.ctx.gmail_connected():
            log.info("digest skipped: vault locked or Gmail not connected")
            with self.ctx.db.session() as s:
                store.notify(s, "Daily digest skipped", "Unlock Huntly and connect Gmail to receive digests.", "warning")
            return
        try:
            send_digest(self.ctx, trigger="schedule")
        except Exception:
            log.exception("scheduled digest failed")

    def _replies(self) -> None:
        from huntly.services.followups import check_replies

        if not self.ctx.vault.unlocked or not self.ctx.gmail_connected():
            return
        try:
            check_replies(self.ctx, trigger="schedule")
        except Exception:
            log.exception("reply check failed")

    def status(self) -> dict:
        jobs = []
        for j in self.sched.get_jobs() if self.sched.running else []:
            jobs.append({"id": j.id, "name": j.name, "next_run": j.next_run_time.isoformat() if j.next_run_time else None})
        return {"running": self.sched.running, "timezone": str(TZ), "jobs": jobs, "collecting": self.ctx.collect_lock.locked()}
