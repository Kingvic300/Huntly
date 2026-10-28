from datetime import datetime, timedelta, timezone

from huntly.models import JobRun
from huntly.scheduler import LocalScheduler
from huntly.services import store


def test_scheduler_uses_lagos_timezone_and_settings(ctx):
    with ctx.db.session() as s:
        store.set_setting(s, "digest_time", "07:45")
        store.set_setting(s, "collection_interval_minutes", 30)
    sched = LocalScheduler(ctx)
    sched.start()
    try:
        st = sched.status()
        assert st["running"] and st["timezone"] == "Africa/Lagos"
        ids = {j["id"]: j for j in st["jobs"]}
        assert set(ids) == {"collect", "digest", "replies"}
        nxt = sched.sched.get_job("digest").next_run_time
        assert (nxt.hour, nxt.minute) == (7, 45) and str(nxt.tzinfo) == "Africa/Lagos"
        with ctx.db.session() as s:
            store.set_setting(s, "digest_enabled", False)
        sched.reload()
        assert {j["id"] for j in sched.status()["jobs"]} == {"collect", "replies"}
    finally:
        sched.shutdown()


def test_digest_skipped_when_locked(ctx, fake_gmail):
    sched = LocalScheduler(ctx)
    sched._digest()
    assert fake_gmail.sent == []


def test_search_runs_soon_after_opening_when_due(ctx):
    sched = LocalScheduler(ctx)
    sched.start()
    try:
        first = sched.sched.get_job("collect").next_run_time
        assert first - datetime.now(timezone.utc) < timedelta(minutes=1)  # never searched: soon after opening
        with ctx.db.session() as s:
            s.add(JobRun(kind="collect", trigger="manual", started_at=datetime.now(timezone.utc) - timedelta(minutes=10)))
        sched.reload()
        nxt = sched.sched.get_job("collect").next_run_time
        assert timedelta(minutes=45) < nxt - datetime.now(timezone.utc) < timedelta(minutes=55)  # 60-minute rhythm kept
        sched.collect_soon()
        assert sched.sched.get_job("collect").next_run_time - datetime.now(timezone.utc) < timedelta(seconds=10)
    finally:
        sched.shutdown()
