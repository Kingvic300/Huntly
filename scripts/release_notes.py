"""Rewrite a GitHub release's notes into a per-platform download table.

Usage: python scripts/release_notes.py <tag>   (needs the `gh` CLI, authenticated)
"""

from __future__ import annotations

import json
import subprocess
import sys

REPO = "Kingvic300/Huntly"

ROWS = [
    # (platform, match, label, how to install)
    ("Linux", lambda n: n.endswith(".deb"), "Debian, Ubuntu, Kali", "`sudo apt install ./{name}`"),
    ("Linux", lambda n: n.endswith(".AppImage"), "Any distribution", "`chmod +x {name}` then run it"),
    ("Linux", lambda n: n.endswith(".rpm"), "Fedora, openSUSE", "`sudo dnf install ./{name}`"),
    ("macOS", lambda n: n.endswith(".dmg") and "aarch64" in n, "Apple silicon (M1 and later)", "Open, drag to Applications, first launch: right-click > Open"),
    ("macOS", lambda n: n.endswith(".dmg") and "aarch64" not in n, "Intel", "Open, drag to Applications, first launch: right-click > Open"),
    ("Windows", lambda n: n.endswith("-setup.exe"), "Windows 10 and 11", "Run it. If SmartScreen warns: More info > Run anyway"),
    ("Windows", lambda n: n.endswith(".msi"), "IT-managed PCs", "Deploy with your usual tools"),
]


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main(tag: str) -> None:
    release = json.loads(gh("release", "view", tag, "-R", REPO, "--json", "assets,url"))
    assets = {a["name"]: a for a in release["assets"]}
    base = f"https://github.com/{REPO}/releases/download/{tag}"
    lines = [
        f"## Download Huntly {tag.lstrip('v')}",
        "",
        "Easiest: use the [download page](https://kingvic300.github.io/Huntly/), which picks the right file for your computer.",
        "",
        "**With a package manager** (updates arrive with the rest of your system):",
        "",
        "- Linux, any distribution: `curl -fsSL https://kingvic300.github.io/Huntly/install.sh | sudo sh`, then `sudo apt install huntly` / `dnf install huntly` installs and upgrades it",
        "- macOS: `brew tap kingvic300/huntly https://github.com/Kingvic300/Huntly && brew install --cask huntly`",
        "- Windows: `scoop bucket add huntly https://github.com/Kingvic300/Huntly; scoop install huntly`",
        "",
        "| System | For | File | How to install |",
        "| --- | --- | --- | --- |",
    ]
    for platform, match, label, how in ROWS:
        for name in sorted(n for n in assets if match(n)):
            mb = assets[name]["size"] / 1048576
            lines.append(f"| **{platform}** | {label} | [{name}]({base}/{name}) ({mb:.0f} MB) | {how.format(name=name)} |")
    lines += [
        "",
        "**Already have Huntly?** It updates itself. The new version downloads in the background and you'll be asked to restart.",
        "",
        "You don't need the `.sig`, `.tar.gz` or `latest.json` files; the automatic updater uses them.",
        "",
        "These builds are not code-signed yet, which is why macOS and Windows show a warning the first time.",
    ]
    gh("release", "edit", tag, "-R", REPO, "--notes", "\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1])
