from __future__ import annotations

from huntly.services.sources.boards import (
    ArbeitnowSource,
    AshbySource,
    GreenhouseSource,
    HimalayasSource,
    JobicySource,
    LeverSource,
    RemoteOkSource,
    RemotiveSource,
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
