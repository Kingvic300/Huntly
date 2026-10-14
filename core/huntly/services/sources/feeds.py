"""RSS / Atom feeds."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import feedparser

from huntly.security.ssrf import validate_url
from huntly.services.sources.base import RawJob, SourceContext, SourceError, require_ok


class RssSource:
    kind = "rss"
    label = "RSS / Atom feed"
    needs_secret = None

    def validate(self, config: dict) -> dict:
        url = validate_url(str(config.get("url", "")), resolve=False)
        return {"url": url, "company": str(config.get("company", ""))[:200]}

    def fetch(self, config: dict, ctx: SourceContext) -> list[RawJob]:
        resp = ctx.fetch(config["url"], headers={"Accept": "application/rss+xml, application/atom+xml, */*"})
        require_ok(resp, "Feed")
        parsed = feedparser.parse(resp.content)
        if parsed.bozo and not parsed.entries:
            raise SourceError(f"Feed could not be parsed: {type(parsed.bozo_exception).__name__}")
        feed_title = parsed.feed.get("title", "")
        jobs = []
        for e in parsed.entries[:200]:
            content = ""
            if e.get("content"):
                content = e.content[0].get("value", "")
            content = content or e.get("summary", "")
            published = None
            for key in ("published_parsed", "updated_parsed"):
                if e.get(key):
                    published = datetime.fromtimestamp(time.mktime(e[key]), timezone.utc)
                    break
            jobs.append(
                RawJob(
                    title=e.get("title", ""),
                    url=e.get("link"),
                    description=content,
                    company=config.get("company") or e.get("author") or feed_title,
                    location=e.get("location"),
                    posted_at=published,
                    external_id=e.get("id") or e.get("link"),
                )
            )
        return jobs
