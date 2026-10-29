"""Cut a release: set the next version everywhere, commit, tag and (optionally) push.

Usage (from the repository root, on a clean main branch):

    python scripts/release.py patch           # 0.3.4 -> 0.3.5
    python scripts/release.py minor           # 0.3.4 -> 0.4.0
    python scripts/release.py major           # 0.3.4 -> 1.0.0
    python scripts/release.py 0.5.0           # an exact version
    python scripts/release.py patch --push    # also push main and the tag, which starts the build

GitHub's "Cut release" workflow (Actions tab -> Cut release -> Run workflow) runs this for you.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"^\d+\.\d+\.\d+$")

# Every place the version is written: (file, pattern with one group for the version, max replacements).
PLACES = [
    ("core/huntly/__init__.py", r'^__version__ = "([^"]+)"', 1),
    ("core/huntly/config.py", r'USER_AGENT = "Huntly/([^ ]+) ', 1),
    ("core/pyproject.toml", r'^version = "([^"]+)"', 1),
    ("desktop/package.json", r'^  "version": "([^"]+)"', 1),
    ("desktop/src-tauri/Cargo.toml", r'^version = "([^"]+)"', 1),
    ("desktop/src-tauri/Cargo.lock", r'name = "huntly"\nversion = "([^"]+)"', 1),
    ("desktop/src-tauri/tauri.conf.json", r'^  "version": "([^"]+)"', 1),
    ("README.md", r"Huntly[_-]([0-9]+\.[0-9]+\.[0-9]+)[_-]", 0),  # 0: every download file name
]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def current() -> str:
    text = (ROOT / "core/huntly/__init__.py").read_text()
    return re.search(PLACES[0][1], text, re.M).group(1)


def next_version(now: str, bump: str) -> str:
    if VERSION.match(bump):
        return bump
    major, minor, patch = map(int, now.split("."))
    return {"major": f"{major + 1}.0.0", "minor": f"{major}.{minor + 1}.0", "patch": f"{major}.{minor}.{patch + 1}"}[bump]


def set_version(new: str) -> list[str]:
    changed = []
    for rel, pattern, count in PLACES:
        path = ROOT / rel
        text = path.read_text()
        n = 0

        def swap(m: re.Match) -> str:
            nonlocal n
            n += 1
            start, end = m.span(1)
            return m.group(0)[: start - m.start()] + new + m.group(0)[end - m.start():]

        updated = re.sub(pattern, swap, text, count=count, flags=re.M)
        if n == 0:
            sys.exit(f"Version not found in {rel}; update scripts/release.py")
        if updated != text:
            path.write_text(updated)
            changed.append(rel)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bump", help="patch, minor, major, or an exact version such as 0.5.0")
    parser.add_argument("--push", action="store_true", help="push main and the tag (starts the release build)")
    args = parser.parse_args()
    if args.bump not in ("patch", "minor", "major") and not VERSION.match(args.bump):
        sys.exit("Give patch, minor, major or a version like 0.5.0")

    if git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("Commit or stash your changes first.")
    now = current()
    new = next_version(now, args.bump)
    if tuple(map(int, new.split("."))) <= tuple(map(int, now.split("."))):
        sys.exit(f"{new} is not newer than {now}")
    if git("tag", "--list", f"v{new}"):
        sys.exit(f"Tag v{new} already exists")

    changed = set_version(new)
    git("add", *changed)
    git("commit", "-m", f"chore(release): {new}")
    git("tag", "-a", f"v{new}", "-m", f"Huntly {new}")
    print(f"{now} -> {new}: committed and tagged v{new} ({len(changed)} files)")
    if args.push:
        git("push", "origin", "HEAD:main")
        git("push", "origin", f"v{new}")
        print("Pushed. GitHub is building the release.")
    else:
        print(f"Push when ready: git push origin main && git push origin v{new}")


if __name__ == "__main__":
    main()
