from __future__ import annotations

from huntly.services.sources.boards import (
    ArbeitnowSource,
    AshbySource,
    BambooHRSource,
    BreezySource,
    GreenhouseSource,
    HimalayasSource,
    JobicySource,
    LeverSource,
    RecruiteeSource,
    RemoteOkSource,
    RemotiveSource,
    SmartRecruitersSource,
    WorkableSource,
)
from huntly.services.sources.career_page import CareerPageSource
from huntly.services.sources.feeds import RssSource

SOURCES = {
    s.kind: s
    for s in (
        RssSource(),
        GreenhouseSource(),
        LeverSource(),
        AshbySource(),
        SmartRecruitersSource(),
        RecruiteeSource(),
        WorkableSource(),
        BambooHRSource(),
        BreezySource(),
        RemotiveSource(),
        RemoteOkSource(),
        HimalayasSource(),
        JobicySource(),
        ArbeitnowSource(),
        CareerPageSource(),
    )
}

CONFIG_FIELDS = {
    "rss": [
        {"key": "url", "label": "Feed URL", "required": True, "placeholder": "e.g. https://weworkremotely.com/categories/remote-programming-jobs.rss"},
        {"key": "company", "label": "Company (optional)"},
    ],
    "greenhouse": [{"key": "board", "label": "Board token", "required": True, "placeholder": "e.g. stripe"}],
    "lever": [{"key": "company", "label": "Company slug", "required": True, "placeholder": "e.g. netflix"}],
    "ashby": [{"key": "board", "label": "Board name", "required": True, "placeholder": "e.g. ramp (from jobs.ashbyhq.com/ramp)"}],
    "smartrecruiters": [{"key": "company", "label": "Company ID", "required": True, "placeholder": "e.g. vendease (from jobs.smartrecruiters.com/Vendease)"}],
    "recruitee": [{"key": "company", "label": "Company", "required": True, "placeholder": "e.g. bunq (from bunq.recruitee.com)"}],
    "workable": [{"key": "company", "label": "Company", "required": True, "placeholder": "e.g. kuda (from apply.workable.com/kuda)"}],
    "bamboohr": [{"key": "company", "label": "Company", "required": True, "placeholder": "e.g. chowdeck (from chowdeck.bamboohr.com)"}],
    "breezy": [{"key": "company", "label": "Company", "required": True, "placeholder": "e.g. busha (from busha.breezy.hr)"}],
    "remotive": [{"key": "search", "label": "Search"}, {"key": "category", "label": "Category", "placeholder": "software-dev"}, {"key": "limit", "label": "Limit", "type": "number"}],
    "remoteok": [{"key": "search", "label": "Keywords (optional)", "placeholder": "e.g. python"}],
    "himalayas": [{"key": "search", "label": "Search (optional)", "placeholder": "e.g. backend engineer"}],
    "jobicy": [
        {"key": "tag", "label": "Keyword", "placeholder": "e.g. python"},
        {"key": "geo", "label": "Region", "placeholder": "e.g. anywhere, europe, emea"},
        {"key": "count", "label": "Limit (1–100)", "type": "number"},
    ],
    "arbeitnow": [{"key": "remote_only", "label": "Remote only", "type": "boolean"}],
    "career_page": [{"key": "url", "label": "Careers page URL", "required": True}, {"key": "company", "label": "Company (optional)"}],
}


def catalog() -> list[dict]:
    return [
        {"kind": k, "label": s.label, "needs_secret": s.needs_secret, "fields": CONFIG_FIELDS[k]} for k, s in SOURCES.items()
    ]
