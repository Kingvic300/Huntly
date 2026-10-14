"""Professional profile. The single source of truth for every generated document.

Nothing in generated CVs or cover letters may come from anywhere else.
"""

from __future__ import annotations

import re
from copy import deepcopy

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from huntly.models import Profile


class Experience(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    start: str = ""
    end: str = ""
    highlights: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str = ""
    qualification: str = ""
    start: str = ""
    end: str = ""
    details: str = ""


class Project(BaseModel):
    name: str = ""
    description: str = ""
    url: str = ""
    technologies: list[str] = Field(default_factory=list)


class ProfileData(BaseModel):
    full_name: str = ""
    headline: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    links: list[str] = Field(default_factory=list)
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    # Matching preferences
    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    remote_only: bool = False
    seniority: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)

    @field_validator("linkedin_url", "github_url", "portfolio_url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            return ""
        if not re.match(r"^https?://", v, re.I):
            v = "https://" + v.lstrip("/")
        if len(v) > 300 or not re.match(r"^https?://[^\s/$.?#][^\s]*$", v, re.I):
            raise ValueError("Enter a web address such as https://linkedin.com/in/your-name")
        return v

    @field_validator("skills", "target_roles", "preferred_locations", "exclude_keywords", "links", "seniority")
    @classmethod
    def _strip(cls, v: list[str]) -> list[str]:
        seen, out = set(), []
        for item in v:
            item = item.strip()
            if item and item.lower() not in seen:
                seen.add(item.lower())
                out.append(item[:200])
        return out


# Editable starting template. Only the name is pre-filled; every fact must come from the user.
TEMPLATE = ProfileData(full_name="Victor Oladimeji")


def load_profile(s: Session) -> ProfileData:
    row = s.get(Profile, 1)
    if row is None:
        row = Profile(id=1, data=TEMPLATE.model_dump())
        s.add(row)
        s.flush()
    return ProfileData.model_validate(row.data)


def save_profile(s: Session, data: ProfileData) -> ProfileData:
    row = s.get(Profile, 1)
    payload = deepcopy(data.model_dump())
    if row is None:
        s.add(Profile(id=1, data=payload))
    else:
        row.data = payload
    return data


def contact_links(p: ProfileData) -> list[str]:
    return [x for x in [p.linkedin_url, p.github_url, p.portfolio_url, *p.links] if x]


def profile_corpus(p: ProfileData) -> str:
    """All facts in the profile as plain text, used for anti-fabrication checks."""
    parts = [p.full_name, p.headline, p.email, p.phone, p.location, p.linkedin_url, p.github_url, p.portfolio_url, p.summary, *p.links, *p.skills, *p.certifications, *p.languages]
    for e in p.experience:
        parts += [e.title, e.company, e.location, e.start, e.end, *e.highlights]
    for ed in p.education:
        parts += [ed.institution, ed.qualification, ed.start, ed.end, ed.details]
    for pr in p.projects:
        parts += [pr.name, pr.description, pr.url, *pr.technologies]
    return "\n".join(x for x in parts if x)


def completeness(p: ProfileData) -> dict:
    checks = {
        "name": bool(p.full_name),
        "email": bool(p.email),
        "linkedin": bool(p.linkedin_url),
        "summary": bool(p.summary),
        "skills": len(p.skills) >= 3,
        "experience": bool(p.experience),
        "target_roles": bool(p.target_roles),
    }
    return {"score": round(100 * sum(checks.values()) / len(checks)), "checks": checks}
