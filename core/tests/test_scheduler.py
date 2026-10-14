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
