"""Rebuild the company directory's starter list (core/huntly/assets/companies.json).

Collects employer names from the public remote job boards, Y Combinator companies that are
hiring (the community-maintained yc-oss.github.io API) and scripts/company_names.txt,
looks each new one up on the hiring platforms Huntly supports, then re-checks every board
in the list and keeps only those with open jobs right now. Run from the repository root:

    .venv/bin/python scripts/build_company_seed.py
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from huntly.security.ssrf import safe_get  # noqa: E402
from huntly.services.companies import board_config, name_key, probe  # noqa: E402
from huntly.services.sources.base import SourceContext  # noqa: E402
from huntly.services.sources.registry import SOURCES  # noqa: E402

SEED = ROOT / "core" / "huntly" / "assets" / "companies.json"
BOARD_QUERIES = [
    ("remoteok", {}),
    *[("jobicy", {"count": 100, "tag": t}) for t in ("", "python", "javascript", "design", "marketing", "sales", "data", "devops", "product", "support", "finance")],
    ("arbeitnow", {"remote_only": False}),
    *[("himalayas", {"search": q}) for q in ("engineer", "developer", "designer", "product", "data", "marketing", "sales", "support", "finance", "operations")],
]
HIMALAYAS_PAGES = 20  # 20 jobs a page, newest first; few of these employers use the supported platforms
WORKERS = 16


def yc_employers() -> list[str]:
    """Y Combinator companies currently hiring. Most hire through Ashby, Lever or Greenhouse."""
    try:
        return [c["name"] for c in safe_get("https://yc-oss.github.io/api/companies/hiring.json").json() if c.get("name")]
    except Exception as exc:
        print(f"yc skipped ({exc})", file=sys.stderr)
        return []


def feed_employers() -> list[str]:
    """Employers from Remotive's full list (one call) and a few Arbeitnow pages."""
    names = []
    try:
        names += [j.get("company_name") for j in safe_get("https://remotive.com/api/remote-jobs").json().get("jobs", [])]
    except Exception as exc:
        print(f"remotive skipped ({exc})", file=sys.stderr)
    for page in range(2, 8):
        try:
            names += [j.get("company_name") for j in safe_get("https://www.arbeitnow.com/api/job-board-api", params={"page": str(page)}).json().get("data", [])]
        except Exception:
            break
    return [n for n in names if n]


def open_jobs(board: tuple[str, str], sctx: SourceContext) -> int:
    platform, slug = board
    try:
        return len(SOURCES[platform].fetch(board_config(platform, slug), sctx))
    except Exception:
        return 0


def himalayas_employers(pages: int) -> list[str]:
    """Employer names from the newest Himalayas listings, following its cursor."""
    names, cursor = [], None
    for _ in range(pages):
        params = {"limit": "20", **({"cursor": cursor} if cursor else {})}
        try:
            data = safe_get("https://himalayas.app/jobs/api", params=params).json()
        except Exception as exc:
            print(f"himalayas pages stopped ({exc})", file=sys.stderr)
            break
        names += [j.get("companyName") for j in data.get("jobs", []) if j.get("companyName")]
        cursor = data.get("nextCursor")
        if not cursor:
            break
    return names


def main() -> None:
    sctx = SourceContext(get_secret=lambda _: None)
    names = [line.strip() for line in (ROOT / "scripts" / "company_names.txt").read_text().splitlines() if line.strip() and not line.startswith("#")]
    for kind, config in BOARD_QUERIES:
        try:
            jobs = SOURCES[kind].fetch(SOURCES[kind].validate(config), sctx)
        except Exception as exc:
            print(f"{kind}: skipped ({exc})", file=sys.stderr)
            continue
        names += [j.company for j in jobs if j.company]
    names += himalayas_employers(HIMALAYAS_PAGES)
    names += feed_employers()
    names += yc_employers()

    data = json.loads(SEED.read_text()) if SEED.exists() else {"version": 0, "companies": []}
    boards = {(p, slug): name for p, slug, name in data["companies"]}
    known = {name_key(n or "") for n in boards.values()} | {name_key(slug) for _, slug in boards}
    unique = [n for k, n in {name_key(n): n for n in names if name_key(n)}.items() if k not in known]
    print(f"looking up {len(unique)} employers not in the list yet", file=sys.stderr)
    with ThreadPoolExecutor(WORKERS) as pool:
        for i, hit in enumerate(pool.map(lambda n: probe(n, sctx), unique), 1):
            if hit:
                boards.setdefault((hit[0], hit[1]), hit[2])
            if i % 50 == 0:
                print(f"{i}/{len(unique)} looked up, {len(boards)} boards", file=sys.stderr)
    with ThreadPoolExecutor(WORKERS) as pool:
        counts = dict(zip(boards, pool.map(lambda b: open_jobs(b, sctx), list(boards))))
    closed = [b for b, n in counts.items() if n == 0]
    for b in closed:
        del boards[b]
    print(f"dropped {len(closed)} boards with no open jobs; {sum(counts.values())} open jobs across {len(boards)} boards", file=sys.stderr)
    rows = sorted([p, slug, " ".join((name or slug).split())] for (p, slug), name in boards.items())
    SEED.write_text(json.dumps({"version": data["version"] + 1, "companies": rows}, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} boards to {SEED.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
