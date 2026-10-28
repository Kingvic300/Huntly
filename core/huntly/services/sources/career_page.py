"""Company career pages that publish schema.org ``JobPosting`` structured data.

Only the JSON-LD the site itself publishes for search engines is read; no scraping
of arbitrary markup, no JavaScript execution, no login walls. Respect each site's terms.
"""

from __future__ import annotations

import json
import re

from huntly.security.ssrf import validate_url
from huntly.services.sources.base import RawJob, SourceContext, SourceError, parse_dt, require_ok

LD_JSON = re.compile(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I)


def _walk(node):
    if isinstance(node, list):
        for n in node:
            yield from _walk(n)
    elif isinstance(node, dict):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if "JobPosting" in types:
            yield node
        for key in ("@graph", "itemListElement", "item"):
            if key in node:
                yield from _walk(node[key])


def job_postings(html: str) -> list[dict]:
    """Every schema.org JobPosting in a page's JSON-LD blocks."""
    found = []
    for block in LD_JSON.findall(html):
        try:
            found += list(_walk(json.loads(block.strip())))
        except ValueError:
            continue
    return found


def _location(posting: dict) -> str | None:
    loc = posting.get("jobLocation")
    loc = loc[0] if isinstance(loc, list) and loc else loc
    if isinstance(loc, dict):
        addr = loc.get("address") or {}
        if isinstance(addr, dict):
            parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
            parts = [p if isinstance(p, str) else (p or {}).get("name") for p in parts]
            return ", ".join(p for p in parts if p) or None
    return None


class CareerPageSource:
    kind = "career_page"
    label = "Company career page (JobPosting data)"
    needs_secret = None

    def validate(self, config: dict) -> dict:
        return {"url": validate_url(str(config.get("url", "")), resolve=False), "company": str(config.get("company", ""))[:200]}

    def fetch(self, config: dict, ctx: SourceContext) -> list[RawJob]:
        resp = ctx.fetch(config["url"], headers={"Accept": "text/html"})
        require_ok(resp, "Career page")
        jobs = []
        for p in job_postings(resp.text):
            org = p.get("hiringOrganization")
            company = org.get("name") if isinstance(org, dict) else org
            jobs.append(
                RawJob(
                    title=str(p.get("title", "")),
                    url=p.get("url") or resp.url,
                    description=str(p.get("description", "")),
                    company=config.get("company") or company,
                    location=_location(p),
                    remote=(p.get("jobLocationType") == "TELECOMMUTE") or None,
                    posted_at=parse_dt(p.get("datePosted")),
                    external_id=str(p.get("identifier", {}).get("value") if isinstance(p.get("identifier"), dict) else p.get("url") or ""),
                )
            )
        if not jobs:
            raise SourceError("No schema.org JobPosting data found on this page")
        return jobs
