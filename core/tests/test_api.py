import io

from huntly.models import Job
from huntly.services import store

from .conftest import PASSWORD, TOKEN


def test_auth_required(client):
    r = client.get("/api/health", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
    r = client.get("/api/health", headers={"Authorization": ""})
    assert r.status_code == 401


def test_rejects_non_loopback_host(client):
    r = client.get("/api/health", headers={"Host": "evil.example.com"})
    assert r.status_code == 403


def test_health_and_database_initialised(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database"] == "ok" and body["timezone"] == "Africa/Lagos"
    assert body["vault"] == {"initialized": False, "unlocked": False}


def test_onboarding_flow_encrypts_credentials(client, ctx):
    st = client.get("/api/onboarding/status").json()
    assert not st["vault_initialized"] and not st["onboarding_complete"]

    assert client.put("/api/credentials/groq_api_key", json={"value": "gsk_placeholder"}).status_code == 423
    assert client.post("/api/vault/create", json={"password": "short"}).status_code == 400
    assert client.post("/api/vault/create", json={"password": PASSWORD}).status_code == 200

    secret = "gsk_" + "OnboardingSecretValue123456"  # split so the source scan stays clean
    assert client.put("/api/credentials/groq_api_key", json={"value": secret}).status_code == 200
    assert client.put("/api/credentials/google_oauth_client", json={"value": "{\"web\": {}}"}).status_code == 400
    assert client.put("/api/credentials/google_token", json={"value": "x"}).status_code == 404

    creds = client.get("/api/credentials").json()
    assert secret not in str(creds)
    assert next(c for c in creds if c["name"] == "groq_api_key")["configured"]

    assert client.post("/api/onboarding/complete").status_code == 200
    assert client.get("/api/onboarding/status").json()["onboarding_complete"]

    # Secret is unreadable once locked, and the wrong password does not unlock.
    client.post("/api/vault/lock")
    assert client.put("/api/credentials/groq_api_key", json={"value": "x"}).status_code == 423
    assert client.post("/api/vault/unlock", json={"password": "not the password"}).status_code == 401
    assert client.post("/api/vault/unlock", json={"password": PASSWORD}).status_code == 200
    assert ctx.secret("groq_api_key") == secret

    ctx.db.engine.dispose()
    for f in ctx.paths.root.rglob("*"):
        if f.is_file():
            assert secret.encode() not in f.read_bytes()


def test_profile_and_sources_and_jobs(client, fake_fetch):
    from .test_sources_matching import RSS

    p = client.get("/api/profile").json()
    assert p["profile"]["full_name"] == "Victor Oladimeji"
    prof = p["profile"] | {"skills": ["Python", "FastAPI"], "target_roles": ["Backend Engineer"]}
    assert client.put("/api/profile", json=prof).status_code == 200

    assert client.post("/api/sources", json={"kind": "rss", "name": "Bad", "config": {"url": "file:///etc/passwd"}}).status_code == 400
    assert client.post("/api/sources", json={"kind": "nope", "name": "x", "config": {}}).status_code == 400
    fake_fetch.routes["https://feed.example.com/rss"] = (200, RSS)
    src = client.post("/api/sources", json={"kind": "rss", "name": "Feed", "config": {"url": "https://feed.example.com/rss"}}).json()

    from huntly.services.collector import collect_all

    collect_all(client.app.state.ctx, "manual")
    jobs = client.get("/api/jobs").json()
    assert jobs["total"] == 2 and jobs["items"][0]["title"].startswith("Backend")
    jid = jobs["items"][0]["id"]
    assert client.patch(f"/api/jobs/{jid}", json={"status": "saved"}).json()["status"] == "saved"
    assert client.patch(f"/api/jobs/{jid}", json={"status": "bogus"}).status_code == 422
    assert client.get("/api/search", params={"q": "backend"}).json()["jobs"]
    assert client.get("/api/sources").json()[0]["last_status"] == "ok"
    a = client.get("/api/analytics").json()
    assert a["totals"]["jobs"] == 2 and len(a["timeline"]) == 30
    assert client.delete(f"/api/sources/{src['id']}").status_code == 200


def test_upload_validation(client):
    r = client.post("/api/documents", files={"file": ("cv.pdf", io.BytesIO(b"MZ\x90\x00 not a pdf"), "application/pdf")})
    assert r.status_code == 415
    r = client.post("/api/documents", files={"file": ("cv.exe", io.BytesIO(b"%PDF-1.4"), "application/pdf")})
    assert r.status_code == 415
    r = client.post("/api/documents", files={"file": ("cv.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF"), "application/pdf")}, data={"title": "Base CV"})
    assert r.status_code == 201
    doc = r.json()
    assert client.get(f"/api/documents/{doc['id']}/file").content.startswith(b"%PDF")
    big = b"%PDF-" + b"0" * (10 * 1024 * 1024 + 10)
    assert client.post("/api/documents", files={"file": ("big.pdf", io.BytesIO(big), "application/pdf")}).status_code == 413


def test_approval_gate_over_api(client, ctx, fake_gmail):
    client.post("/api/vault/create", json={"password": PASSWORD})
    from .conftest import SAMPLE_PROFILE

    client.put("/api/profile", json=SAMPLE_PROFILE.model_dump())
    with ctx.db.session() as s:
        j = Job(dedupe_key="api1", title="Backend Engineer", company="Example", description="Python", apply_email="hr@example.com")
        s.add(j)
        s.flush()
        jid = j.id
    app = client.post("/api/applications", json={"job_id": jid}).json()
    assert client.post(f"/api/applications/{app['id']}/documents", json={"format": "pdf"}).status_code == 200
    appr = client.post(f"/api/applications/{app['id']}/email", json={}).json()
    assert appr["status"] == "pending"

    assert client.post(f"/api/approvals/{appr['id']}/send").status_code == 400
    assert client.post(f"/api/approvals/{appr['id']}/approve", json={"confirm": False, "content_hash": appr["content_hash"]}).status_code == 400
    assert fake_gmail.sent == []

    edited = client.patch(f"/api/approvals/{appr['id']}", json={"body": "Updated body"}).json()
    assert client.post(f"/api/approvals/{appr['id']}/approve", json={"confirm": True, "content_hash": appr["content_hash"]}).status_code == 400
    ok = client.post(f"/api/approvals/{appr['id']}/approve", json={"confirm": True, "content_hash": edited["content_hash"]})
    assert ok.json()["status"] == "approved"
    sent = client.post(f"/api/approvals/{appr['id']}/send")
    assert sent.status_code == 200 and len(fake_gmail.sent) == 1
    assert client.get(f"/api/applications/{app['id']}").json()["status"] == "applied"
    audit = [a["action"] for a in client.get("/api/audit").json()]
    assert "approval.sent" in audit


def test_digest_goes_only_to_self(client, ctx, fake_gmail):
    client.post("/api/vault/create", json={"password": PASSWORD})
    with ctx.db.session() as s:
        s.add(Job(dedupe_key="d1", title="Python Dev", company="X", description="", score=90, url="https://x.example/1"))
        store.set_setting(s, "digest_min_score", 50)
    prev = client.get("/api/digest/preview").json()
    assert "Python Dev" in prev["text"] and "<script" not in prev["html"]
    r = client.post("/api/digest/send")
    assert r.status_code == 200 and r.json()["jobs"] == 1
    kind, msg = fake_gmail.sent[0]
    assert kind == "message" and msg["To"] == fake_gmail.address == msg["From"]
    assert client.post("/api/digest/send").json()["jobs"] == 0  # not re-sent


def test_settings_validation(client):
    assert client.put("/api/settings", json={"digest_time": "25:00"}).status_code == 422
    assert client.put("/api/settings", json={"collection_interval_minutes": 5}).status_code == 422
    r = client.put("/api/settings", json={"digest_time": "07:30", "collection_interval_minutes": 30})
    assert r.json()["digest_time"] == "07:30" and r.json()["timezone"] == "Africa/Lagos"


def test_vault_reset_discards_undecryptable_secrets(client, ctx):
    client.post("/api/vault/create", json={"password": PASSWORD})
    client.put("/api/credentials/x_bearer_token", json={"value": "old-token-value"})
    ctx.vault.lock()
    ctx.paths.vault.unlink()  # user forgot password and reset
    assert client.post("/api/vault/create", json={"password": "a brand new password"}).status_code == 200
    creds = {c["name"]: c["configured"] for c in client.get("/api/credentials").json()}
    assert creds["x_bearer_token"] is False


def test_pipeline_counts(client, ctx):
    with ctx.db.session() as s:
        s.add(Job(dedupe_key="p1", title="A", score=90))
        s.add(Job(dedupe_key="p2", title="B", score=20, status="saved"))
    p = client.get("/api/pipeline").json()
    stages = {st["id"]: st["count"] for st in p["stages"]}
    assert stages["new"] == 1 and stages["shortlisted"] == 1
    assert p["hot_new"] == 1 and p["new_last_24h"] == 2


def test_timestamps_are_serialised_as_utc(client, ctx):
    with ctx.db.session() as s:
        s.add(Job(dedupe_key="tz1", title="TZ"))
    item = client.get("/api/jobs").json()["items"][0]
    assert item["discovered_at"].endswith("+00:00")


def test_profile_save_rescores_jobs_loaded_from_db(client, ctx):
    from datetime import datetime, timezone

    with ctx.db.session() as s:
        s.add(Job(dedupe_key="naive1", title="Python Developer", description="Python", posted_at=datetime(2026, 10, 1, tzinfo=timezone.utc)))
    prof = client.get("/api/profile").json()["profile"] | {"skills": ["Python"], "target_roles": ["Python Developer"]}
    r = client.put("/api/profile", json=prof)
    assert r.status_code == 200
    assert client.get("/api/jobs").json()["items"][0]["score"] > 40
