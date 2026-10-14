"""X API v2 recent search (https://docs.x.com/x-api/posts/search/introduction).

Requires the user's own bearer token. Each matching post becomes a lead whose
apply link is the first external URL in the post (or the post itself).
"""

from __future__ import annotations

from huntly.services.sources.base import RawJob, SourceContext, SourceError, parse_dt, require_ok

ENDPOINT = "https://api.x.com/2/tweets/search/recent"


class XSearchSource:
    kind = "x_search"
    label = "X (Twitter) recent search"
    needs_secret = "x_bearer_token"

    def validate(self, config: dict) -> dict:
        query = str(config.get("query", "")).strip()
        if not query:
            raise ValueError("A search query is required")
        if len(query) > 512:
            raise ValueError("X queries are limited to 512 characters")
        if "is:retweet" not in query:
            query = f"{query} -is:retweet"
        max_results = int(config.get("max_results", 25))
        return {"query": query, "max_results": max(10, min(100, max_results))}

    def fetch(self, config: dict, ctx: SourceContext) -> list[RawJob]:
        token = ctx.get_secret("x_bearer_token")
        if not token:
            raise SourceError("X bearer token not configured (Settings → Credentials)")
        resp = ctx.fetch(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
            params={
                "query": config["query"],
                "max_results": str(config["max_results"]),
                "tweet.fields": "created_at,author_id,entities,lang",
                "expansions": "author_id",
                "user.fields": "username,name",
            },
        )
        require_ok(resp, "X API")
        payload = resp.json()
        users = {u["id"]: u for u in payload.get("includes", {}).get("users", [])}
        jobs = []
        for t in payload.get("data", []):
            author = users.get(t.get("author_id"), {})
            username = author.get("username", "i")
            post_url = f"https://x.com/{username}/status/{t['id']}"
            link = post_url
            for u in t.get("entities", {}).get("urls", []):
                expanded = u.get("unwound_url") or u.get("expanded_url")
                if expanded and "x.com/" not in expanded and "twitter.com/" not in expanded:
                    link = expanded
                    break
            text = t.get("text", "")
            jobs.append(
                RawJob(
                    title=text.split("\n", 1)[0][:140],
                    url=link,
                    description=f"{text}\n\nPost: {post_url}",
                    company=author.get("name") or f"@{username}",
                    posted_at=parse_dt(t.get("created_at")),
                    external_id=f"x:{t['id']}",
                    extra={"post_url": post_url},
                )
            )
        return jobs
