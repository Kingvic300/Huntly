"""Public job-board APIs that explicitly permit programmatic access.

* Greenhouse Job Board API  – https://developers.greenhouse.io/job-board.html
* Lever Postings API        – https://github.com/lever/postings-api
* Remotive public API       – https://remotive.com/api-documentation (attribution: links back to Remotive)
* Arbeitnow job board API   – https://www.arbeitnow.com/blog/job-board-api
* Remote OK API             – https://remoteok.com/api (terms: link back to Remote OK and name it as the source)
* Himalayas jobs API        – https://himalayas.app/api (links back to Himalayas)
* Jobicy remote jobs API    – https://jobicy.com/jobs-rss-feed (terms: credit Jobicy, link to the original job URL)
* Ashby Job Postings API    – https://developers.ashbyhq.com/docs/public-job-posting-api
* SmartRecruiters Posting API (public, no key) and Recruitee careers-site API (public, no key)
"""

from __future__ import annotations

import html
import re

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
        # Large employers' boards with full job text run to several megabytes (Cloudflare: about 8 MB).
        resp = ctx.fetch(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", params={"content": "true"}, max_bytes=25 * 1024 * 1024)
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


def _search(config: dict) -> str:
    return str(config.get("search", "")).strip()[:100]


def _matches(search: str, *texts) -> bool:
    if not search:
        return True
    haystack = " ".join(str(t or "") for t in texts).lower()
    return all(word in haystack for word in search.lower().split())


class RemoteOkSource:
    kind = "remoteok"
    label = "Remote OK (remote jobs)"
    needs_secret = None

    def validate(self, config: dict) -> dict:
        return {"search": _search(config)}

    def fetch(self, config: dict, ctx: SourceContext) -> list[RawJob]:
        resp = ctx.fetch("https://remoteok.com/api")
        require_ok(resp, "Remote OK")
        jobs = []
        # The first element is Remote OK's legal notice, not a job.
        for j in resp.json():
            if not isinstance(j, dict) or not j.get("id") or not j.get("position"):
                continue
            tags = j.get("tags") or []
            if not _matches(config.get("search", ""), j.get("position"), " ".join(map(str, tags)), j.get("description")):
                continue
            jobs.append(
                RawJob(
                    title=j.get("position", ""),
                    url=j.get("url"),
                    description=j.get("description", ""),
                    company=j.get("company"),
                    location=j.get("location") or None,
                    remote=True,
                    posted_at=parse_dt(j.get("date") or j.get("epoch")),
                    external_id=f"remoteok:{j.get('id')}",
                )
            )
        return jobs


class HimalayasSource:
    kind = "himalayas"
    label = "Himalayas (remote jobs)"
    needs_secret = None

    def validate(self, config: dict) -> dict:
        return {"search": _search(config)}

    def fetch(self, config: dict, ctx: SourceContext) -> list[RawJob]:
        if config.get("search"):
            resp = ctx.fetch("https://himalayas.app/jobs/api/search", params={"q": config["search"]})
        else:
            resp = ctx.fetch("https://himalayas.app/jobs/api", params={"limit": "20"})
        require_ok(resp, "Himalayas")
        jobs = []
        for j in resp.json().get("jobs", []):
            places = [str(x) for x in j.get("locationRestrictions") or []]
            jobs.append(
                RawJob(
                    title=j.get("title", ""),
                    url=j.get("applicationLink") or j.get("guid"),
                    description=j.get("description") or j.get("excerpt", ""),
                    company=j.get("companyName"),
                    location=", ".join(places[:6]) or "Anywhere",
                    remote=True,
                    posted_at=parse_dt(j.get("pubDate")),
                    external_id=f"himalayas:{j.get('guid')}",
                )
            )
        return jobs


class JobicySource:
    kind = "jobicy"
    label = "Jobicy (remote jobs)"
    needs_secret = None

    def validate(self, config: dict) -> dict:
        tag = str(config.get("tag", "")).strip()[:60]
        geo = str(config.get("geo", "")).strip()[:40]
        if geo and not SLUG.match(geo):
            raise ValueError("'geo' must be a region such as 'europe' or 'anywhere'")
        return {"tag": tag, "geo": geo.lower(), "count": max(1, min(100, int(config.get("count") or 50)))}

    def fetch(self, config: dict, ctx: SourceContext) -> list[RawJob]:
        params = {"count": str(config["count"])}
        if config.get("tag"):
            params["tag"] = config["tag"]
        if config.get("geo"):
            params["geo"] = config["geo"]
        resp = ctx.fetch("https://jobicy.com/api/v2/remote-jobs", params=params)
        require_ok(resp, "Jobicy")
        return [
            RawJob(
                title=html.unescape(j.get("jobTitle", "")),
                url=j.get("url"),
                description=j.get("jobDescription") or j.get("jobExcerpt", ""),
                company=html.unescape(j.get("companyName") or "") or None,
                location=j.get("jobGeo"),
                remote=True,
                posted_at=parse_dt(j.get("pubDate")),
                external_id=f"jobicy:{j.get('id')}",
            )
            for j in resp.json().get("jobs", [])
        ]


class AshbySource:
    kind = "ashby"
    label = "Ashby company board"
    needs_secret = None

    def validate(self, config: dict) -> dict:
        return {"board": _slug(config, "board")}

    def fetch(self, config: dict, ctx: SourceContext) -> list[RawJob]:
        board = config["board"]
        resp = ctx.fetch(f"https://api.ashbyhq.com/posting-api/job-board/{board}")
        require_ok(resp, "Ashby")
        jobs = []
        for j in resp.json().get("jobs", [])[:500]:
            if j.get("isListed") is False:
                continue
            jobs.append(
                RawJob(
                    title=j.get("title", ""),
                    url=j.get("jobUrl"),
                    description=j.get("descriptionPlain") or j.get("descriptionHtml", ""),
                    company=board,
                    location=j.get("location"),
                    remote=bool(j.get("isRemote")) or None,
                    posted_at=parse_dt(j.get("publishedAt")),
                    external_id=f"ashby:{board}:{j.get('id')}",
                )
            )
        return jobs


_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class SmartRecruitersSource:
    kind = "smartrecruiters"
    label = "SmartRecruiters company board"
    needs_secret = None

    def validate(self, config: dict) -> dict:
        return {"company": _slug(config, "company")}

    def fetch(self, config: dict, ctx: SourceContext) -> list[RawJob]:
        company = config["company"]
        resp = ctx.fetch(f"https://api.smartrecruiters.com/v1/companies/{company}/postings", params={"limit": "100"})
        require_ok(resp, "SmartRecruiters")
        jobs = []
        for j in resp.json().get("content", []):
            job_id = str(j.get("id", ""))
            if not _ID.match(job_id):
                continue
            loc = j.get("location") or {}
            country = next((f.get("valueLabel") for f in j.get("customField") or [] if f.get("fieldId") == "COUNTRY"), None)
            jobs.append(
                RawJob(
                    title=j.get("name", ""),
                    url=f"https://jobs.smartrecruiters.com/{company}/{job_id}",
                    company=(j.get("company") or {}).get("name") or company,
                    location=", ".join(x for x in [loc.get("city"), country or str(loc.get("country") or "").upper()] if x) or None,
                    remote=bool(loc.get("remote")) or None,
                    posted_at=parse_dt(j.get("releasedDate")),
                    external_id=f"smartrecruiters:{company}:{job_id}",
                    extra={"company": company, "id": job_id},
                )
            )
        return jobs

    def describe(self, job: RawJob, ctx: SourceContext) -> None:
        """The postings list has no descriptions; fetch one posting's text. Call only for jobs worth keeping."""
        resp = ctx.fetch(f"https://api.smartrecruiters.com/v1/companies/{job.extra['company']}/postings/{job.extra['id']}")
        require_ok(resp, "SmartRecruiters")
        sections = (resp.json().get("jobAd") or {}).get("sections") or {}
        job.description = "\n".join(f"{x.get('title', '')}\n{x.get('text', '')}" for x in sections.values() if isinstance(x, dict))


class RecruiteeSource:
    kind = "recruitee"
    label = "Recruitee company board"
    needs_secret = None

    def validate(self, config: dict) -> dict:
        value = str(config.get("company", "")).strip().lower()
        if not _DNS_LABEL.match(value):
            raise ValueError("'company' must be the name before .recruitee.com, such as 'acme'")
        return {"company": value}

    def fetch(self, config: dict, ctx: SourceContext) -> list[RawJob]:
        company = config["company"]
        resp = ctx.fetch(f"https://{company}.recruitee.com/api/offers/")
        require_ok(resp, "Recruitee")
        jobs = []
        for j in resp.json().get("offers", [])[:500]:
            if j.get("status") not in (None, "published"):
                continue
            jobs.append(
                RawJob(
                    title=j.get("title", ""),
                    url=j.get("careers_url"),
                    description=f"{j.get('description') or ''}\n{j.get('requirements') or ''}",
                    company=j.get("company_name") or company,
                    location=j.get("location"),
                    remote=bool(j.get("remote")) or None,
                    posted_at=parse_dt(str(j.get("published_at") or "").replace(" UTC", "+00:00")),
                    external_id=f"recruitee:{company}:{j.get('id')}",
                )
            )
        return jobs
