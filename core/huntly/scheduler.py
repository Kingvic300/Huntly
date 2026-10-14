"""Local background scheduler (APScheduler, in-process, Africa/Lagos timezone).

Jobs run only while the app is open. Nothing here can approve or send
application emails; the only email it sends is the digest to the user's own address.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from huntly.config import TZ
from huntly.context import AppContext
from huntly.services import store

log = logging.getLogger(__name__)


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
            self.sched.add_job(self._collect, IntervalTrigger(minutes=minutes, timezone=TZ), id="collect", name="Collect jobs")
        if settings.get("digest_enabled"):
            hh, mm = (str(settings.get("digest_time") or "08:00").split(":") + ["0"])[:2]
            self.sched.add_job(self._digest, CronTrigger(hour=int(hh), minute=int(mm), timezone=TZ), id="digest", name="Daily digest")
        if settings.get("reply_tracking_enabled"):
            self.sched.add_job(self._replies, IntervalTrigger(hours=2, timezone=TZ), id="replies", name="Check for replies")

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
