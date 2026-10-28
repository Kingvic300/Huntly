from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from huntly.models import Application, Document, EmailApproval, Job
from huntly.services import applications as svc
from huntly.services import store
from huntly.services.documents import apply_highlight_rewrites, bullet_fabrications, find_fabrications, tailor
from huntly.services.llm import GroqClient


def _job(ctx, **kw) -> int:
    with ctx.db.session() as s:
        j = Job(dedupe_key=kw.get("key", "k1"), title="Backend Engineer", company="Example Corp", description="Python, FastAPI and Docker required.", apply_email="jobs@example.com")
        s.add(j)
        s.flush()
        a = Application(job_id=j.id, contact_email=j.apply_email)
        s.add(a)
        s.flush()
        return a.id


@pytest.mark.parametrize("fmt", ["pdf", "docx"])
def test_generate_documents(with_profile, fmt):
    app_id = _job(with_profile)
    out = svc.generate_documents(with_profile, app_id, fmt)
    with with_profile.db.session() as s:
        app = s.get(Application, app_id)
        cv = s.get(Document, app.cv_document_id)
        path = Path(cv.path)
        assert path.is_file() and path.suffix == f".{fmt}" and path.stat().st_size > 1000
        head = path.read_bytes()[:5]
        assert head.startswith(b"%PDF-" if fmt == "pdf" else b"PK")
    assert out["source"] == "template"


def test_generate_requires_profile(ctx):
    app_id = _job(ctx)
    with ctx.db.session() as s:
        from huntly.services.profile import ProfileData, save_profile

        save_profile(s, ProfileData(full_name=""))
    with pytest.raises(ValueError):
        svc.generate_documents(ctx, app_id)


def test_fabrication_detector():
    corpus = "Ada Example Backend Engineer Acme Ltd Python FastAPI 2021 Example Corp"
    assert find_fabrications("I built APIs in Python at Acme Ltd since 2021.", corpus) == []
    probs = find_fabrications("At Google I increased revenue by 300% using Kubernetes.", corpus)
    assert {"Google", "300%", "Kubernetes"} <= set(probs)


class FabricatingGroq(GroqClient):
    def __init__(self):
        pass

    def cover_letter_paragraphs(self, *a, **k):
        return ["I led a team of 40 engineers at Google and hold a PhD from MIT."]

    def tailored_summary(self, *a, **k):
        return "Backend engineer with 12 years at Microsoft."

    def tailored_highlights(self, *a, **k):
        return [["Built payment APIs in Python, FastAPI and Kubernetes", "Cut deploy time by 80% by moving to Docker"]]


class HonestGroq(GroqClient):
    def __init__(self):
        pass

    def cover_letter_paragraphs(self, *a, **k):
        return ["I built payment APIs in Python and FastAPI at Acme Ltd."]

    def tailored_summary(self, *a, **k):
        return "Backend Engineer who built payment APIs in Python and FastAPI."

    def tailored_highlights(self, *a, **k):
        return [["Developed payment APIs with Python and FastAPI", "Reduced deploy time by moving services to Docker"]]


def test_llm_fabrication_is_discarded(with_profile, monkeypatch):
    ctx = with_profile
    monkeypatch.setattr(ctx, "groq", lambda: FabricatingGroq())
    app_id = _job(ctx)
    out = svc.generate_documents(ctx, app_id, "pdf")
    assert out["source"] == "template"
    assert sum("discarded" in w for w in out["warnings"]) == 3
    assert any("2 of 2 achievement bullets" in w and "Kubernetes" in w and "80%" in w for w in out["warnings"])
    with ctx.db.session() as s:
        assert s.get(Document, out["cv_document_id"]).meta["highlights_source"] == "profile"


def test_honest_llm_wording_is_used_and_ats_report_present(with_profile, monkeypatch):
    ctx = with_profile
    monkeypatch.setattr(ctx, "groq", lambda: HonestGroq())
    out = svc.generate_documents(ctx, _job(ctx), "pdf")
    assert out["source"] == "groq" and not out["warnings"]
    ats = out["ats"]
    assert {"Python", "FastAPI", "Docker"} <= set(ats["covered"])
    assert ats["coverage"] == 100 and ats["score"] > 70
    with ctx.db.session() as s:
        doc = s.get(Document, out["cv_document_id"])
        assert Path(doc.path).name.startswith("Ada-Example-CV-Example-Corp")
        assert doc.meta["highlights_source"] == "groq"


def test_bullet_rewrites_cannot_add_or_move_facts():
    from .conftest import SAMPLE_PROFILE

    role = SAMPLE_PROFILE.experience[0]
    original = "Cut deploy time by moving to Docker"
    assert bullet_fabrications("Reduced deploy time by moving services to Docker", original, role, SAMPLE_PROFILE) == []
    assert bullet_fabrications("Cut deploy time by 40% with docker and kubernetes", original, role, SAMPLE_PROFILE) == ["40%", "Kubernetes"]
    # A skill the user has, but not in this bullet, may not be moved into it.
    assert bullet_fabrications("Cut deploy time by moving to Docker on AWS", original, role, SAMPLE_PROFILE) == ["AWS"]

    t = tailor(SAMPLE_PROFILE, "Backend Engineer", "Docker")
    used, offered, problems = apply_highlight_rewrites(t, [["Shipped Docker builds 3x faster", "Built payment APIs in Python and FastAPI"]], "Docker")
    assert (used, offered, problems) == (1, 2, ["3"])
    assert t.experience[0].highlights == ["Cut deploy time by moving to Docker", "Built payment APIs in Python and FastAPI"]
    # A reply with the wrong number of bullets leaves the role untouched.
    t = tailor(SAMPLE_PROFILE, "Backend Engineer", "Docker")
    assert apply_highlight_rewrites(t, [["Only one bullet"]], "Docker") == (0, 0, [])


def _prepared(ctx):
    app_id = _job(ctx)
    svc.generate_documents(ctx, app_id, "pdf")
    return svc.prepare_email(ctx, app_id)


def _hash(ctx, aid):
    with ctx.db.session() as s:
        return s.get(EmailApproval, aid).content_hash


def test_cannot_send_without_approval(with_profile, fake_gmail):
    ctx = with_profile
    aid = _prepared(ctx)
    with pytest.raises(svc.ApprovalError):
        svc.send(ctx, aid)
    assert fake_gmail.sent == []


def test_approval_requires_explicit_confirm_and_matching_hash(with_profile, fake_gmail):
    ctx = with_profile
    aid = _prepared(ctx)
    with pytest.raises(svc.ApprovalError):
        svc.approve(ctx, aid, confirm=False, expected_hash=_hash(ctx, aid))
    with pytest.raises(svc.ApprovalError):
        svc.approve(ctx, aid, confirm=True, expected_hash="0" * 64)
    assert fake_gmail.sent == []


def test_edit_after_approval_blocks_send(with_profile, fake_gmail):
    ctx = with_profile
    aid = _prepared(ctx)
    svc.approve(ctx, aid, confirm=True, expected_hash=_hash(ctx, aid))
    svc.edit_approval(ctx, aid, to=None, subject="Changed", body=None, attachment_ids=None)
    with pytest.raises(svc.ApprovalError):
        svc.send(ctx, aid)
    assert fake_gmail.sent == []


def test_expired_approval_blocks_send(with_profile, fake_gmail):
    ctx = with_profile
    aid = _prepared(ctx)
    svc.approve(ctx, aid, confirm=True, expected_hash=_hash(ctx, aid))
    with ctx.db.session() as s:
        s.get(EmailApproval, aid).approved_at = datetime.now(timezone.utc) - timedelta(hours=2)
    with pytest.raises(svc.ApprovalError, match="expired"):
        svc.send(ctx, aid)
    assert fake_gmail.sent == []


def test_full_approved_send_and_audit(with_profile, fake_gmail):
    ctx = with_profile
    aid = _prepared(ctx)
    svc.push_draft(ctx, aid)
    assert fake_gmail.sent == [] and len(fake_gmail.drafts) == 1  # drafts never send
    svc.approve(ctx, aid, confirm=True, expected_hash=_hash(ctx, aid))
    svc.send(ctx, aid)
    assert len(fake_gmail.sent) == 1
    kind, msg = fake_gmail.sent[0]
    assert kind == "draft" and msg["To"] == "jobs@example.com"
    assert len(list(msg.iter_attachments())) == 2
    with pytest.raises(svc.ApprovalError):
        svc.send(ctx, aid)  # cannot send twice
    with ctx.db.session() as s:
        a = s.get(EmailApproval, aid)
        assert a.status == "sent" and a.application.status == "applied"
        actions = [x.action for x in s.query(store.AuditLog).all()]
        assert "approval.approved" in actions and "approval.sent" in actions


def test_rejected_cannot_be_sent(with_profile, fake_gmail):
    ctx = with_profile
    aid = _prepared(ctx)
    svc.reject(ctx, aid)
    with pytest.raises(svc.ApprovalError):
        svc.approve(ctx, aid, confirm=True, expected_hash=_hash(ctx, aid))
    assert fake_gmail.sent == []


def test_background_code_never_sends_applications():
    root = Path(__file__).resolve().parents[1] / "huntly"
    for name in ("scheduler.py", "services/collector.py", "services/digest.py"):
        text = (root / name).read_text(encoding="utf-8")
        assert "send_draft" not in text and "applications" not in text.split("import")[0]
        assert "svc.send" not in text and "approve(" not in text
