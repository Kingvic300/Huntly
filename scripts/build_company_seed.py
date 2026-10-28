"""Rebuild the company directory's starter list (core/huntly/assets/companies.json).

Collects employer names, looks each new one up on the hiring platforms Huntly supports,
then re-checks every board in the list and keeps only those with open jobs right now.
Names are looked up in this order, stopping once the list reaches --target boards:

1. African employers: scripts/company_names_africa.txt plus Y Combinator companies tagged
   Nigeria or Africa. Checked on every platform, including Workable, BambooHR and Breezy HR.
2. Y Combinator companies that are hiring (the community-maintained yc-oss.github.io API).
3. scripts/company_names.txt and employers on the public remote job boards.

Groups 2 and 3 are checked on Greenhouse, Lever, Ashby, SmartRecruiters and Recruitee only.
Progress is saved every 50 names. Run from the repository root:

    .venv/bin/python scripts/build_company_seed.py [--target 540]
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from huntly.security.ssrf import safe_get  # noqa: E402
from huntly.services.companies import board_config, name_key, probe  # noqa: E402
from huntly.services.sources.base import SourceContext  # noqa: E402
from huntly.services.sources.registry import SOURCES  # noqa: E402

SEED = ROOT / "core" / "huntly" / "assets" / "companies.json"
ALL_PLATFORMS = ("greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "workable", "bamboohr", "breezy")
COMMON_PLATFORMS = ALL_PLATFORMS[:5]
BOARD_QUERIES = [
    ("remoteok", {}),
    *[("jobicy", {"count": 100, "tag": t}) for t in ("", "python", "javascript", "design", "marketing", "sales", "data", "devops", "product", "support", "finance")],
    ("arbeitnow", {"remote_only": False}),
    *[("himalayas", {"search": q}) for q in ("engineer", "developer", "designer", "product", "data", "marketing", "sales", "support", "finance", "operations")],
]
YC = "https://yc-oss.github.io/api/companies/"
WORKERS = 24


def read_names(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]


def yc(list_name: str, keep) -> list[str]:
    try:
        companies = safe_get(YC + list_name, max_bytes=40 * 1024 * 1024).json()
    except Exception as exc:
        print(f"yc {list_name} skipped ({exc})", file=sys.stderr)
        return []
    return [c["name"] for c in companies if c.get("name") and keep(c)]


def in_africa(company: dict) -> bool:
    places = " ".join(company.get("regions") or []) + " " + (company.get("all_locations") or "")
    return company.get("status") in ("Active", "Public") and ("Nigeria" in places or "Africa" in places)


def board_employers(sctx: SourceContext) -> list[str]:
    names = []
    for kind, config in BOARD_QUERIES:
        try:
            names += [j.company for j in SOURCES[kind].fetch(SOURCES[kind].validate(config), sctx) if j.company]
        except Exception as exc:
            print(f"{kind}: skipped ({exc})", file=sys.stderr)
    try:
        names += [j.get("company_name") for j in safe_get("https://remotive.com/api/remote-jobs").json().get("jobs", []) if j.get("company_name")]
    except Exception as exc:
        print(f"remotive skipped ({exc})", file=sys.stderr)
    return names


def open_jobs(board: tuple[str, str], sctx: SourceContext) -> int:
    platform, slug = board
    try:
        return len(SOURCES[platform].fetch(board_config(platform, slug), sctx))
    except Exception:
        return 0


def save(boards: dict, version: int) -> None:
    rows = sorted([p, slug, " ".join((name or slug).split())] for (p, slug), name in boards.items())
    SEED.write_text(json.dumps({"version": version, "companies": rows}, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=540, help="stop looking up names at this many boards")
    target = parser.parse_args().target
    sctx = SourceContext(get_secret=lambda _: None)

    data = json.loads(SEED.read_text()) if SEED.exists() else {"version": 0, "companies": []}
    version = data["version"] + 1
    boards = {(p, slug): name for p, slug, name in data["companies"]}
    known = {name_key(n or "") for n in boards.values()} | {name_key(slug) for _, slug in boards}

    groups = [
        (read_names(ROOT / "scripts" / "company_names_africa.txt") + yc("all.json", in_africa), ALL_PLATFORMS),
        (yc("hiring.json", lambda c: True), COMMON_PLATFORMS),
        (read_names(ROOT / "scripts" / "company_names.txt") + board_employers(sctx), COMMON_PLATFORMS),
    ]
    queue, seen = [], set(known)
    for names, platforms in groups:
        for n in names:
            if name_key(n) and name_key(n) not in seen:
                seen.add(name_key(n))
                queue.append((n, platforms))
    print(f"{len(boards)} boards now; looking up {len(queue)} employers until {target}", file=sys.stderr)

    done = 0
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(probe, n, sctx, platforms) for n, platforms in queue]
        for future in as_completed(futures):
            done += 1
            hit = future.result()
            if hit:
                boards.setdefault((hit[0], hit[1]), hit[2])
            if done % 50 == 0:
                save(boards, version)
                print(f"{done}/{len(queue)} looked up, {len(boards)} boards", file=sys.stderr)
            if len(boards) >= target:
                pool.shutdown(wait=False, cancel_futures=True)
                break

    with ThreadPoolExecutor(WORKERS) as pool:
        counts = dict(zip(boards, pool.map(lambda b: open_jobs(b, sctx), list(boards))))
    for board in [b for b, n in counts.items() if n == 0]:
        del boards[board]
    save(boards, version)
    print(f"wrote {len(boards)} boards with {sum(counts.values())} open jobs to {SEED.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
