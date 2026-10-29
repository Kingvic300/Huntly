from huntly.models import Company, CompanyProbe, Job, Source
from huntly.services import companies, store
from huntly.services.collector import collect_all
from huntly.services.sources.base import SourceContext
from huntly.services.sources.registry import SOURCES

GH = "https://boards-api.greenhouse.io/v1/boards/"
SR = "https://api.smartrecruiters.com/v1/companies/"


def _directory(ctx, *boards) -> int:
    with ctx.db.session() as s:
        store.set_setting(s, "company_seed_version", 10**6)  # keep the bundled list out of these tests
        companies.add_companies(s, list(boards), "imported")
        src = Source(kind=companies.DIRECTORY_KIND, name="Company directory", config={})
        s.add(src)
        s.flush()
        return src.id


def test_board_links_and_import_parsing():
    assert companies.board_from_url("https://boards.greenhouse.io/Stripe/jobs/123") == ("greenhouse", "stripe")
    assert companies.board_from_url("https://boards.greenhouse.io/embed/job_board?for=acme") == ("greenhouse", "acme")
    assert companies.board_from_url("jobs.lever.co/netflix/abc-123") == ("lever", "netflix")
    assert companies.board_from_url("https://jobs.ashbyhq.com/posthog") == ("ashby", "posthog")
    assert companies.board_from_url("https://jobs.smartrecruiters.com/Vendease/7439") == ("smartrecruiters", "vendease")
    assert companies.board_from_url("https://bunq.recruitee.com/o/lead") == ("recruitee", "bunq")
    assert companies.board_from_url("https://example.com/careers") is None
    found, invalid = companies.parse_import("https://jobs.lever.co/kuda\nashby:lemfi, greenhouse:moniepoint; nonsense workday:acme ashby:lemfi")
    assert found == [("lever", "kuda"), ("ashby", "lemfi"), ("greenhouse", "moniepoint")]
    assert invalid == ["nonsense", "workday:acme"]
    assert companies.slug_guesses("Grafana Labs") == ["grafanalabs", "grafana-labs", "grafana"]
    assert companies.slug_guesses("Moniepoint Inc.") == ["moniepointinc", "moniepoint-inc", "moniepoint"]


def test_directory_keeps_only_matching_jobs_and_rotates(with_profile, fake_fetch):
    ctx = with_profile
    fake_fetch.routes[GH + "acme/jobs"] = (200, {"jobs": [
        {"id": 1, "title": "Backend Engineer", "absolute_url": "https://boards.greenhouse.io/acme/jobs/1", "content": "Python and FastAPI", "location": {"name": "Remote"}},
        {"id": 2, "title": "Sales Manager", "absolute_url": "https://boards.greenhouse.io/acme/jobs/2", "content": "Sell things", "location": {"name": "Berlin"}},
    ]})
    fake_fetch.routes[SR + "vend/postings"] = (200, {"totalFound": 2, "content": [
        {"id": "123", "name": "Python Developer", "company": {"name": "Vendease"}, "location": {"city": "Lagos", "country": "ng"}, "customField": [{"fieldId": "COUNTRY", "valueLabel": "Nigeria"}], "releasedDate": "2026-10-20T10:00:00.000Z"},
        {"id": "124", "name": "Delivery Driver", "company": {"name": "Vendease"}, "location": {"city": "Lagos", "country": "ng"}},
    ]})
    fake_fetch.routes[SR + "vend/postings/123"] = (200, {"jobAd": {"sections": {"jobDescription": {"title": "About", "text": "<p>Python, Docker, AWS</p>"}}}})
    dir_id = _directory(ctx, ("greenhouse", "acme"), ("lever", "gone"), ("smartrecruiters", "vend"))

    out = collect_all(ctx, "manual", source_ids=[dir_id])
    assert out["new"] == 2 and out["errors"] == 0
    with ctx.db.session() as s:
        titles = {j.title: j for j in s.query(Job).all()}
        assert set(titles) == {"Backend Engineer", "Python Developer"}
        assert "Docker" in titles["Python Developer"].description and titles["Python Developer"].location == "Lagos, Nigeria"
        by_slug = {c.slug: c for c in s.query(Company).all()}
        assert by_slug["acme"].open_jobs == 2 and by_slug["acme"].jobs_found == 1 and by_slug["acme"].last_status == "ok"
        assert by_slug["gone"].enabled is False and "404" in by_slug["gone"].last_error  # board no longer exists
    fetched = [url for url, *_ in fake_fetch.calls]
    assert SR + "vend/postings/123" in fetched and SR + "vend/postings/124" not in fetched  # text fetched only for a fitting title

    # Rotation: with a batch of one, the board checked longest ago goes next.
    with ctx.db.session() as s:
        store.set_setting(s, "directory_batch_size", 1)
        s.query(Company).filter_by(slug="vend").one().last_checked_at = None
    fake_fetch.calls.clear()
    collect_all(ctx, "manual", source_ids=[dir_id])
    assert [u for u, *_ in fake_fetch.calls if "/companies/" in u or "/boards/" in u] == [SR + "vend/postings"]


def test_directory_needs_roles_or_skills(ctx):
    dir_id = _directory(ctx, ("greenhouse", "acme"))
    out = collect_all(ctx, "manual", source_ids=[dir_id])
    assert out["errors"] == 1
    with ctx.db.session() as s:
        assert "target roles or skills" in s.get(Source, dir_id).last_error


def test_discovers_boards_from_employer_names_once(with_profile, fake_fetch):
    ctx = with_profile
    dir_id = _directory(ctx)
    with ctx.db.session() as s:
        s.add(Job(dedupe_key="r1", title="Engineer", company="Acme Corp"))
        s.add(Job(dedupe_key="r2", title="Engineer", company="Nobody Ltd"))
    fake_fetch.routes["https://api.lever.co/v0/postings/acme"] = (200, [{"id": "a", "text": "Backend Engineer", "hostedUrl": "https://jobs.lever.co/acme/a", "descriptionPlain": "Python"}])
    collect_all(ctx, "manual", source_ids=[dir_id])
    with ctx.db.session() as s:
        assert [(c.platform, c.slug, c.origin) for c in s.query(Company).all()] == [("lever", "acme", "discovered")]
        assert {p.name_key: p.found for p in s.query(CompanyProbe).all()} == {"acmecorp": True, "nobodyltd": False}
        assert s.query(Job).filter_by(title="Backend Engineer").count() == 1
    fake_fetch.calls.clear()
    collect_all(ctx, "manual", source_ids=[dir_id])
    assert not any("nobody" in u for u, *_ in fake_fetch.calls)  # each name is looked up once


def test_job_links_to_hiring_boards_join_the_directory(with_profile, fake_fetch):
    ctx = with_profile
    rss = """<?xml version="1.0"?><rss version="2.0"><channel><title>Feed</title>
    <item><title>Backend Engineer</title><link>https://boards.greenhouse.io/paystack/jobs/9</link><description>Python</description></item>
    </channel></rss>"""
    fake_fetch.routes["https://feed.example.com/rss"] = (200, rss)
    with ctx.db.session() as s:
        s.add(Source(kind="rss", name="Feed", config={"url": "https://feed.example.com/rss"}))
    collect_all(ctx, "manual")
    with ctx.db.session() as s:
        assert [(c.platform, c.slug) for c in s.query(Company).all()] == [("greenhouse", "paystack")]


def test_default_sources_added_once_after_onboarding(with_profile):
    ctx = with_profile
    collect_all(ctx, "manual")
    with ctx.db.session() as s:
        assert s.query(Source).count() == 0  # not before onboarding is finished
        store.set_setting(s, "onboarding_complete", True)
    collect_all(ctx, "manual")
    collect_all(ctx, "manual")
    with ctx.db.session() as s:
        kinds = {src.kind: src.config for src in s.query(Source).all()}
    assert set(kinds) == {"remotive", "remoteok", "himalayas", "jobicy", "arbeitnow", companies.DIRECTORY_KIND}
    assert kinds["himalayas"]["search"] == "Backend Engineer" and kinds["arbeitnow"]["remote_only"] is True


def test_recruitee_source(fake_fetch):
    fake_fetch.routes["https://bunq.recruitee.com/api/offers/"] = (200, {"offers": [
        {"id": 7, "title": "Support Lead", "status": "published", "careers_url": "https://careers.bunq.com/o/lead", "description": "<p>Help</p>", "requirements": "<ul><li>Python</li></ul>", "company_name": "bunq", "location": "Sofia, Bulgaria", "remote": False, "published_at": "2026-10-27 12:11:34 UTC"},
        {"id": 8, "title": "Draft", "status": "draft"},
    ]})
    jobs = SOURCES["recruitee"].fetch(SOURCES["recruitee"].validate({"company": "Bunq"}), SourceContext(get_secret=lambda n: None, fetch=fake_fetch))
    assert len(jobs) == 1
    j = jobs[0].normalized()
    assert j.title == "Support Lead" and "Python" in j.description and j.posted_at.day == 27


def test_company_api(client):
    with client:
        r = client.post("/api/companies/import", json={"text": "https://jobs.lever.co/huntlytest\nashby:examplelabs\nnot-a-board"})
        assert r.json() == {"added": 2, "already_tracked": 0, "invalid": ["not-a-board"], "invalid_count": 1}
        assert client.post("/api/companies/import", json={"text": "ashby:examplelabs"}).json()["already_tracked"] == 1
        page = client.get("/api/companies", params={"q": "huntlytest"}).json()
        assert page["total"] == 1 and page["items"][0]["platform"] == "lever"
        assert page["tracked"] > 100 and page["batch_size"] == 300  # starter list loaded too
        off = client.patch(f"/api/companies/{page['items'][0]['id']}", json={"enabled": False}).json()
        assert off["enabled"] is False
        assert client.put("/api/settings", json={"directory_batch_size": 10}).status_code == 422


def test_bundled_starter_list_loads_once_and_respects_turned_off(ctx):
    with ctx.db.session() as s:
        added = companies.load_seed(s)
        assert added > 100
        boards = s.query(Company).all()
        assert all(c.platform in companies.PLATFORMS and companies.valid_slug(c.platform, c.slug) and c.origin == "seed" for c in boards)
        assert {"moniepoint", "jumia", "palmpay"} <= {c.slug for c in boards}  # Nigerian employers included
        boards[0].enabled = False
        assert companies.load_seed(s) == 0  # same list version: nothing re-added, turned-off stays off
        assert s.get(Company, boards[0].id).enabled is False


def test_workable_bamboohr_breezy(with_profile, fake_fetch):
    assert companies.board_from_url("https://apply.workable.com/kuda/j/82E249C10F") == ("workable", "kuda")
    assert companies.board_from_url("https://chowdeck.bamboohr.com/careers/34") == ("bamboohr", "chowdeck")
    assert companies.board_from_url("https://busha.breezy.hr/p/028b-bdm") == ("breezy", "busha")
    assert companies.board_from_url("https://apply.workable.com/j/82E249C10F") is None  # a job link, not a board

    ctx = with_profile
    fake_fetch.routes["https://www.workable.com/api/accounts/kuda"] = (200, {"name": "Kuda", "jobs": [
        {"title": "Backend Engineer", "shortcode": "AB1", "url": "https://apply.workable.com/j/AB1", "description": "<p>Python, PostgreSQL</p>", "city": "Lagos", "country": "Nigeria", "telecommuting": False, "published_on": "2026-10-20"},
    ]})
    fake_fetch.routes["https://chowdeck.bamboohr.com/careers/list"] = (200, {"result": [
        {"id": "34", "jobOpeningName": "Senior Backend Engineer", "location": {"city": "Ikoyi", "state": "Lagos"}, "atsLocation": {}, "locationType": "2"},
        {"id": "35", "jobOpeningName": "Rider Operations Lead", "location": {"city": "Lagos"}, "locationType": "0"},
    ]})
    fake_fetch.routes["https://chowdeck.bamboohr.com/careers/34/detail"] = (200, {"result": {"jobOpening": {"description": "<p>Python and Docker</p>", "datePosted": "2026-10-25"}}})
    fake_fetch.routes["https://busha.breezy.hr/json"] = (200, [
        {"id": "9", "friendly_id": "9-python-developer", "name": "Python Developer", "published_date": "2026-10-08T11:57:12Z", "location": {"city": "Lagos", "country": {"name": "Nigeria"}, "is_remote": True}, "company": {"name": "Busha"}},
    ])
    fake_fetch.routes["https://busha.breezy.hr/p/9-python-developer"] = (200, '<script type="application/ld+json">{"@type":"JobPosting","title":"Python Developer","description":"<p>FastAPI and AWS</p>"}</script>')
    dir_id = _directory(ctx, ("workable", "kuda"), ("bamboohr", "chowdeck"), ("breezy", "busha"))
    with ctx.db.session() as s:
        s.query(Company).filter_by(slug="chowdeck").one().name = "Chowdeck"
    out = collect_all(ctx, "manual", source_ids=[dir_id])
    assert out["new"] == 3 and out["errors"] == 0
    with ctx.db.session() as s:
        jobs = {j.title: j for j in s.query(Job).all()}
    assert set(jobs) == {"Backend Engineer", "Senior Backend Engineer", "Python Developer"}
    assert jobs["Backend Engineer"].company == "Kuda" and jobs["Backend Engineer"].location == "Lagos, Nigeria"
    chow = jobs["Senior Backend Engineer"]
    assert chow.company == "Chowdeck" and chow.remote is False and "Docker" in chow.description  # hybrid, text fetched
    assert jobs["Python Developer"].remote is True and "FastAPI" in jobs["Python Developer"].description
    assert "https://chowdeck.bamboohr.com/careers/35/detail" not in [u for u, *_ in fake_fetch.calls]


def test_search_never_holds_the_write_lock_while_on_the_network(with_profile, fake_fetch):
    """The app must stay able to save (start an application, shortlist) during a long search."""
    import sqlite3

    ctx = with_profile
    fake_fetch.routes[GH + "acme/jobs"] = (200, {"jobs": [
        {"id": 1, "title": "Backend Engineer", "absolute_url": "https://boards.greenhouse.io/acme/jobs/1", "content": "Python and FastAPI"},
    ]})
    fake_fetch.routes[SR + "vend/postings"] = (200, {"totalFound": 1, "content": [{"id": "123", "name": "Python Developer"}]})
    fake_fetch.routes[SR + "vend/postings/123"] = (200, {"jobAd": {"sections": {"d": {"title": "About", "text": "Python, Docker"}}}})
    dir_id = _directory(ctx, ("greenhouse", "acme"), ("smartrecruiters", "vend"))
    with ctx.db.session() as s:
        s.add(Job(dedupe_key="other", title="Engineer", company="Acme Corp"))  # gives discovery a name to look up
    blocked = []

    def fetch_while_user_saves(url, **kw):
        conn = sqlite3.connect(ctx.paths.db, timeout=0.5)
        try:
            conn.execute("UPDATE settings SET value = value WHERE key = 'x'")
            conn.commit()
        except sqlite3.OperationalError as exc:
            blocked.append((url, str(exc)))
        finally:
            conn.close()
        return fake_fetch(url, **kw)

    ctx.fetch = fetch_while_user_saves
    out = collect_all(ctx, "manual", source_ids=[dir_id])
    assert out["new"] == 2
    assert blocked == []
