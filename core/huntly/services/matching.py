"""Deterministic job scoring (0–100) with an explainable breakdown.

The optional LLM assessment is blended in only when the user enables Groq; the
deterministic score is always computed and shown so rankings stay explainable.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from huntly.services.profile import ProfileData

# --- seniority ---------------------------------------------------------------
LEVELS = ("intern", "entry", "mid", "senior", "lead", "manager")
LEVEL_LABELS = {
    "intern": "Internship", "entry": "Entry level", "mid": "Mid level", "senior": "Senior",
    "lead": "Lead / Staff", "manager": "Manager / Director",
}
_TECH_ROLE = (
    r"(?:software|data|machine|ml|ai|product|security|backend|back-end|frontend|front-end|full[- ]?stack|platform|"
    r"infrastructure|site|research|applied|mobile|ios|android|devops|cloud|analytics|engineer|scientist|designer|"
    r"developer|architect|design|hardware|systems|solutions|firmware|network|qa|test|quality)"
)
# Checked in order on the title; the first match wins. "Senior Director" is a manager role,
# "Staff Accountant" is not a staff-level engineer, and "Lead Generation" is not a lead role.
_TITLE_LEVELS = [
    ("intern", re.compile(r"\b(?:intern|internship|trainee|apprentice(?:ship)?)\b")),
    ("manager", re.compile(
        r"\b(?:head\s+of|director|vp|vice\s+president|chief|c[tefmo]o|engineering\s+manager|general\s+manager|"
        r"country\s+manager|managing\s+director|people\s+manager)\b")),
    ("lead", re.compile(rf"\b(?:principal|distinguished|tech\s+lead|team\s+lead|lead(?![\s-]+gen)|staff\s+{_TECH_ROLE})\b")),
    ("senior", re.compile(r"\b(?:senior|sr\.?)(?=\s|$|[,/(-])")),
    ("mid", re.compile(r"\b(?:mid[- ]?level|intermediate|mid(?![- ]?market))\b")),
    ("entry", re.compile(r"\b(?:junior|jr\.?|graduate|entry[- ]level|associate)(?=\s|$|[,/(-])")),
]
_ROMAN = re.compile(r"\b(i{1,3}|iv|v)\s*(?:$|[-–,(|/])")
_ROMAN_LEVEL = {"i": "entry", "ii": "mid", "iii": "senior", "iv": "lead", "v": "lead"}
# A platform's own label: Workable "Mid-Senior level", SmartRecruiters "entry_level", Jobicy "Midweight".
_HINT_WORDS = {"executive": "manager", "director": "manager", "midweight": "mid", "mid_level": "mid", "entry_level": "entry", "internship": "intern"}
_YEARS = re.compile(
    r"(?i)\b(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*\d{1,2}\s*)?\+?\s*(?:years?|yrs?)\b.{0,60}?\bexperience"
    r"|\bexperience\b\W{0,3}(?:of\s+)?(?:at\s+least\s+|minimum\s+(?:of\s+)?)?(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b"
)
_TEXT_LEVELS = [
    ("intern", re.compile(r"(?i)\bthis\s+is\s+an?\s+(?:paid\s+|unpaid\s+)?internship\b|\binternship\s+(?:role|position|opportunity)\b")),
    ("entry", re.compile(r"(?i)\bentry[- ]level\b|\bjunior[- ](?:level|role|position)\b|\bno\s+(?:prior\s+)?experience\s+(?:is\s+)?required\b")),
    ("mid", re.compile(r"(?i)\bmid[- ]level\b")),
    ("senior", re.compile(r"(?i)\bsenior[- ]level\b")),
]


def _title_level(title: str) -> str | None:
    t = title.lower()
    for level, pattern in _TITLE_LEVELS:
        if pattern.search(t):
            return level
    m = _ROMAN.search(t)
    return _ROMAN_LEVEL[m.group(1)] if m else None


def level_from_label(label: str | None) -> str | None:
    """A level from a short label: a platform's field or a profile preference ("Senior", "Mid-level")."""
    if not label:
        return None
    key = label.strip().lower().replace(" ", "_")
    if "mid" in key and "senior" in key:
        return None  # LinkedIn-style "Mid-Senior level" covers two levels
    return _HINT_WORDS.get(key) or (key if key in LEVELS else None) or _title_level(label)


def years_required(text: str) -> int | None:
    """The most years of experience the text asks for (typos like 50 years are ignored)."""
    found = [int(a or b) for a, b in _YEARS.findall(text[:6000])]
    found = [n for n in found if n <= 20]
    return max(found) if found else None


def seniority_level(title: str, description: str = "", hint: str | None = None) -> str | None:
    """Seniority of a job: the title first, then the employer's own label, then the description."""
    level = _title_level(title) or level_from_label(hint)
    if level:
        return level
    years = years_required(description)
    if years is not None:
        return "entry" if years <= 1 else "mid" if years <= 4 else "senior" if years <= 7 else "lead"
    for level, pattern in _TEXT_LEVELS:
        if pattern.search(description[:6000]):
            return level
    return None


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
    level: str | None = None,
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

    # Seniority (title, then the employer's label, then the description)
    job_level = level or seniority_level(title, description)
    wanted = {lvl for lvl in (level_from_label(s) for s in profile.seniority) if lvl}
    if not wanted or not job_level:
        parts["seniority"] = WEIGHTS["seniority"] * 0.5
    elif job_level in wanted:
        parts["seniority"] = WEIGHTS["seniority"]
        reasons.append(f"{LEVEL_LABELS[job_level]}, matching your preference")
    else:
        parts["seniority"] = 0.0
        reasons.append(f"{LEVEL_LABELS[job_level]}, not a level you prefer")

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


def matches_profile(breakdown: dict) -> bool:
    """Worth keeping from a broad source: the title fits a target role, or the text names two of your skills."""
    if breakdown["excluded"]:
        return False
    return breakdown["parts"]["title"] >= WEIGHTS["title"] * 0.5 or len(breakdown["matched_skills"]) >= 2
