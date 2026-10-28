"""Rebuild the company directory's starter list (core/huntly/assets/companies.json).

Collects employer names from the public remote job boards plus scripts/company_names.txt,
looks each one up on the hiring platforms Huntly supports, and keeps the boards that have
open jobs. Entries already in the file are kept. Run from the repository root:

    .venv/bin/python scripts/build_company_seed.py
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from huntly.services.companies import name_key, probe  # noqa: E402
from huntly.services.sources.base import SourceContext  # noqa: E402
from huntly.services.sources.registry import SOURCES  # noqa: E402

SEED = ROOT / "core" / "huntly" / "assets" / "companies.json"
BOARD_QUERIES = [
    ("remotive", {"limit": 200}),
    ("remoteok", {}),
    ("jobicy", {"count": 100}),
    ("arbeitnow", {"remote_only": True}),
    *[("himalayas", {"search": q}) for q in ("engineer", "developer", "designer", "product", "data", "marketing", "sales", "support", "finance", "operations")],
]


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
    unique = list({name_key(n): n for n in names if name_key(n)}.values())
    print(f"looking up {len(unique)} employers", file=sys.stderr)

    data = json.loads(SEED.read_text()) if SEED.exists() else {"version": 0, "companies": []}
    boards = {(p, slug): name for p, slug, name in data["companies"]}
    with ThreadPoolExecutor(10) as pool:
        for i, hit in enumerate(pool.map(lambda n: probe(n, sctx), unique), 1):
            if hit:
                boards.setdefault((hit[0], hit[1]), hit[2])
            if i % 50 == 0:
                print(f"{i}/{len(unique)} looked up, {len(boards)} boards", file=sys.stderr)
    rows = sorted([p, slug, name] for (p, slug), name in boards.items())
    SEED.write_text(json.dumps({"version": data["version"] + 1, "companies": rows}, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} boards to {SEED.relative_to(ROOT)}", file=sys.stderr)


if __name__ == "__main__":
    main()
