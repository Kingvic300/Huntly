"""Deterministic job scoring (0–100) with an explainable breakdown.

The optional LLM assessment is blended in only when the user enables Groq; the
deterministic score is always computed and shown so rankings stay explainable.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from huntly.services.profile import ProfileData

SENIORITY_WORDS = {
    "intern": "intern", "internship": "intern", "graduate": "junior", "junior": "junior", "entry": "junior",
    "mid": "mid", "intermediate": "mid", "senior": "senior", "sr": "senior", "lead": "lead",
    "staff": "staff", "principal": "principal", "head": "head", "director": "director",
}

WEIGHTS = {"skills": 45, "title": 25, "location": 15, "recency": 10, "seniority": 5}


def _term_regex(term: str) -> re.Pattern:
    escaped = re.escape(term.lower())
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9+#.]+", text.lower()) if len(t) > 1}


def score_job(
    profile: ProfileData,
    *,
    title: str,
    description: str,
    location: str | None,
    remote: bool,
    posted_at: datetime | None,
    now: datetime | None = None,
) -> tuple[float, dict]:
    now = now or datetime.now(timezone.utc)
    text = f"{title}\n{description}".lower()
    title_l = title.lower()
    reasons: list[str] = []
    parts: dict[str, float] = {}

    # Skills overlap
    matched = [s for s in profile.skills if _term_regex(s).search(text)]
    denom = max(5, min(len(profile.skills), 12)) if profile.skills else 1
    parts["skills"] = round(WEIGHTS["skills"] * min(1.0, len(matched) / denom), 1) if profile.skills else 0.0
    if matched:
        reasons.append(f"Mentions {len(matched)} of your skills: {', '.join(matched[:8])}")

    # Title vs target roles
    best = 0.0
    best_role = None
    for role in profile.target_roles:
        if _term_regex(role).search(title_l):
            best, best_role = 1.0, role
            break
        rt = _tokens(role)
        if rt:
            overlap = len(rt & _tokens(title_l)) / len(rt)
            if overlap > best:
                best, best_role = overlap, role
    parts["title"] = round(WEIGHTS["title"] * best, 1)
    if best_role and best > 0:
        reasons.append(f"Title {'matches' if best == 1.0 else 'partly matches'} target role '{best_role}'")

    # Location / remote
    loc = (location or "").lower()
    if remote:
        parts["location"] = WEIGHTS["location"]
        reasons.append("Remote-friendly")
    elif profile.remote_only:
        parts["location"] = 0.0
        reasons.append("Not remote, but you prefer remote only")
    elif any(_term_regex(p).search(loc) or _term_regex(p).search(text[:1500]) for p in profile.preferred_locations):
        parts["location"] = WEIGHTS["location"]
        reasons.append("In a preferred location")
    else:
        parts["location"] = WEIGHTS["location"] * (0.4 if not profile.preferred_locations else 0.1)

    # Recency (SQLite returns naive datetimes; everything is stored as UTC)
    if posted_at and posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    if posted_at:
        age_days = (now - posted_at).total_seconds() / 86400
        parts["recency"] = WEIGHTS["recency"] * (1.0 if age_days <= 7 else 0.6 if age_days <= 14 else 0.3 if age_days <= 30 else 0.0)
    else:
        parts["recency"] = WEIGHTS["recency"] * 0.5

    # Seniority
    job_levels = {lvl for w, lvl in SENIORITY_WORDS.items() if _term_regex(w).search(title_l)}
    wanted = {SENIORITY_WORDS.get(s.lower(), s.lower()) for s in profile.seniority}
    if not wanted or not job_levels:
        parts["seniority"] = WEIGHTS["seniority"] * 0.5
    elif job_levels & wanted:
        parts["seniority"] = WEIGHTS["seniority"]
        reasons.append("Seniority matches your preference")
    else:
        parts["seniority"] = 0.0
        reasons.append(f"Seniority ({', '.join(sorted(job_levels))}) differs from your preference")

    total = sum(parts.values())

    excluded = [k for k in profile.exclude_keywords if _term_regex(k).search(text)]
    if excluded:
        total = min(total, 10.0)
        reasons.append(f"Contains excluded keyword(s): {', '.join(excluded)}")

    return round(total, 1), {
        "parts": {k: round(v, 1) for k, v in parts.items()},
        "weights": WEIGHTS,
        "matched_skills": matched,
        "excluded": excluded,
        "reasons": reasons,
    }


def blend(deterministic: float, llm_fit: int | None) -> float:
    if llm_fit is None:
        return deterministic
    return round(0.7 * deterministic + 0.3 * llm_fit, 1)
