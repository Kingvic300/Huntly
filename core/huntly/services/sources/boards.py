"""Public job-board APIs that explicitly permit programmatic access.

* Greenhouse Job Board API  – https://developers.greenhouse.io/job-board.html
* Lever Postings API        – https://github.com/lever/postings-api
* Remotive public API       – https://remotive.com/api-documentation (attribution: links back to Remotive)
* Arbeitnow job board API   – https://www.arbeitnow.com/blog/job-board-api
"""

from __future__ import annotations

import html

from huntly.services.sources.base import SLUG, RawJob, SourceContext, parse_dt, require_ok


def _slug(config: dict, key: str) -> str:
    value = str(config.get(key, "")).strip()
    if not SLUG.match(value):
        raise ValueError(f"'{key}' must be a board identifier such as 'acme' (letters, digits, - _ .)")
    return value


class GreenhouseSource:
    kind = "greenhouse"
    label = "Greenhouse company board"
    needs_secret = None

    def validate(self, config: dict) -> dict:
        return {"board": _slug(config, "board")}

    def fetch(self, config: dict, ctx: SourceContext) -> list[RawJob]:
        board = config["board"]
        resp = ctx.fetch(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", params={"content": "true"})
        require_ok(resp, "Greenhouse")
        jobs = []
        for j in resp.json().get("jobs", [])[:500]:
            jobs.append(
                RawJob(
                    title=j.get("title", ""),
                    url=j.get("absolute_url"),
                    description=html.unescape(j.get("content", "") or ""),
                    company=j.get("company_name") or board,
                    location=(j.get("location") or {}).get("name"),
                    posted_at=parse_dt(j.get("first_published") or j.get("updated_at")),
                    external_id=f"gh:{board}:{j.get('id')}",
                )
            )
        return jobs


class LeverSource:
    kind = "lever"
    label = "Lever company board"
    needs_secret = None

    def validate(self, config: dict) -> dict:
        return {"company": _slug(config, "company")}

    def fetch(self, config: dict, ctx: SourceContext) -> list[RawJob]:
        company = config["company"]
        resp = ctx.fetch(f"https://api.lever.co/v0/postings/{company}", params={"mode": "json"})
        require_ok(resp, "Lever")
        jobs = []
        for j in resp.json()[:500]:
            cats = j.get("categories") or {}
            lists = "\n".join(
                f"{lst.get('text', '')}\n{lst.get('content', '')}" for lst in j.get("lists", []) if isinstance(lst, dict)
            )
            jobs.append(
                RawJob(
                    title=j.get("text", ""),
                    url=j.get("hostedUrl"),
                    description=f"{j.get('descriptionPlain') or j.get('description', '')}\n{lists}\n{j.get('additionalPlain', '')}",
                    company=company,
                    location=cats.get("location"),
                    remote=(j.get("workplaceType") == "remote") or None,
                    posted_at=parse_dt(j.get("createdAt")),
                    external_id=f"lever:{company}:{j.get('id')}",
                )
            )
        return jobs


class RemotiveSource:
    kind = "remotive"
    label = "Remotive (remote jobs)"
    needs_secret = None

    def validate(self, config: dict) -> dict:
        search = str(config.get("search", "")).strip()[:100]
        category = str(config.get("category", "")).strip()[:60]
        return {"search": search, "category": category, "limit": max(1, min(200, int(config.get("limit", 50))))}

    def fetch(self, config: dict, ctx: SourceContext) -> list[RawJob]:
        params = {"limit": str(config["limit"])}
        if config.get("search"):
            params["search"] = config["search"]
        if config.get("category"):
            params["category"] = config["category"]
        resp = ctx.fetch("https://remotive.com/api/remote-jobs", params=params)
        require_ok(resp, "Remotive")
        return [
            RawJob(
                title=j.get("title", ""),
                url=j.get("url"),
                description=j.get("description", ""),
                company=j.get("company_name"),
                location=j.get("candidate_required_location"),
                remote=True,
                posted_at=parse_dt(j.get("publication_date")),
                external_id=f"remotive:{j.get('id')}",
            )
            for j in resp.json().get("jobs", [])
        ]


class ArbeitnowSource:
    kind = "arbeitnow"
    label = "Arbeitnow job board"
    needs_secret = None

    def validate(self, config: dict) -> dict:
        return {"remote_only": bool(config.get("remote_only", False))}

    def fetch(self, config: dict, ctx: SourceContext) -> list[RawJob]:
        resp = ctx.fetch("https://www.arbeitnow.com/api/job-board-api")
        require_ok(resp, "Arbeitnow")
        jobs = []
        for j in resp.json().get("data", []):
            if config.get("remote_only") and not j.get("remote"):
                continue
            jobs.append(
                RawJob(
                    title=j.get("title", ""),
                    url=j.get("url"),
                    description=j.get("description", ""),
                    company=j.get("company_name"),
                    location=j.get("location"),
                    remote=bool(j.get("remote")),
                    posted_at=parse_dt(j.get("created_at")),
                    external_id=f"arbeitnow:{j.get('slug')}",
                )
            )
        return jobs
