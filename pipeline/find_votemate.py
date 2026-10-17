"""Find each candidate's VoteMate profile, and record the link only.

VoteMate is a non-partisan site where candidates fill in someone else's form:
it picks the fields and publishes the result. That makes it a third party's
page, not the candidate's own publication, so nothing here is ever quoted --
the same call already made for the bear questionnaire and the Chamber's
questions, both of which live on their own pages rather than in anyone's
positions.

What it is good for is a link. Most candidates have written more there than
this site shows, so every profile that has content gets linked from that
candidate's page. Deliberately not scoped to the candidates with nothing: a
rule that fires only for the people who complain is not a rule.

Stored as a URL and a flag. No profile text is written to disk, so this can
never quietly become a source.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from pipeline.fetching import fetch

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "data" / "candidates.json"
OUT = ROOT / "data" / "votemate-links.json"

RIDINGS = {"dnv": 806, "cnv": 809}
LIST_URL = "https://en.votemate.org/bc2026/candidates/?riding={}"
PROFILE_URL = "https://en.votemate.org/bc2026/candidates/{}?riding={}"

EMPTY = re.compile(r"hasn't uploaded a profile yet|yet to add their biography", re.I)
MIN_CHARS = 120


def profile_ids(muni: str) -> dict[str, int]:
    html = fetch(LIST_URL.format(RIDINGS[muni]), "votemate")
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, int] = {}
    for a in soup.find_all("a", href=re.compile(r"/bc2026/candidates/\d+")):
        m = re.search(r"/candidates/(\d+)", a["href"])
        name = re.sub(r"\s+Independent\s*$", "", a.get_text(" ", strip=True)).strip()
        if m and name:
            out.setdefault(name, int(m.group(1)))
    return out


def has_content(muni: str, vm_id: int) -> bool:
    """Whether the candidate actually filled the profile in.

    Linking an empty one is a worse dead end than linking nothing: three of the
    five candidates with nothing on this site have a blank profile there too.
    """
    html = fetch(PROFILE_URL.format(vm_id, RIDINGS[muni]), "votemate")
    soup = BeautifulSoup(html, "lxml")
    if EMPTY.search(soup.get_text(" ")):
        return False
    for block in soup.find_all("div", class_=re.compile(r"\bprofile_block\b")):
        body = block.find("div", class_=re.compile(r"profile_block_content"))
        if body and len(re.sub(r"\s+", " ", body.get_text(" ", strip=True))) >= MIN_CHARS:
            return True
    return False


def main() -> int:
    cands = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    by_name = {c["name"]: c for c in cands}
    aliases = {"Matthew Bond": "Mathew Bond"}

    links: dict[str, str] = {}
    empty: list[str] = []
    for muni in ("cnv", "dnv"):
        for name, vm_id in profile_ids(muni).items():
            cand = by_name.get(aliases.get(name, name))
            if cand is None or cand["municipality"] != muni:
                continue
            url = PROFILE_URL.format(vm_id, RIDINGS[muni])
            if has_content(muni, vm_id):
                links[cand["id"]] = url
            else:
                empty.append(cand["name"])

    OUT.write_text(json.dumps(links, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(links)} profiles with content, {len(empty)} empty or unclaimed")
    if empty:
        print("  no link for: " + ", ".join(sorted(empty)))
    print(f"-> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
