"""Candidate profiles from VoteMate.

VoteMate is a non-partisan site where a candidate writes their own profile:
a biography, why they are running, and a list of promises. Every candidate in
BC can claim one, free, which makes it more evenly available than a campaign
website -- those cost money and about a third of this field has none.

Layne North, a trustee candidate with no filed statement, wrote on the evening
before the election to say the site had nothing from them and pointed here:
"It can also be copied from Vote Mate." They were right that it is public and
theirs. Read for all 59 rather than for the one who asked, which is the only
version of this that is fair.

Cached under data/raw/votemate/, and quotes are sliced from the saved capture
like every other source here.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from pipeline.fetching import fetch, retrieved_at
from pipeline.models import Source

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "data" / "candidates.json"
OUT = ROOT / "data" / "votemate.json"

RIDINGS = {"dnv": 806, "cnv": 809}
LIST_URL = "https://en.votemate.org/bc2026/candidates/?riding={}"
PROFILE_URL = "https://en.votemate.org/bc2026/candidates/{}?riding={}"

# Headings VoteMate renders around the candidate's own words.
WROTE_IT = "submitted by the candidate or their team"
# Said about a profile nobody filled in.
EMPTY = re.compile(r"hasn't uploaded a profile yet|yet to add their biography", re.I)
MIN_CHARS = 120


def profile_ids(muni: str) -> dict[str, int]:
    """Candidate name -> VoteMate id, from the municipality's listing page."""
    html = fetch(LIST_URL.format(RIDINGS[muni]), "votemate")
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, int] = {}
    for a in soup.find_all("a", href=re.compile(r"/bc2026/candidates/\d+")):
        m = re.search(r"/candidates/(\d+)", a["href"])
        name = re.sub(r"\s+Independent\s*$", "", a.get_text(" ", strip=True)).strip()
        if m and name:
            out.setdefault(name, int(m.group(1)))
    return out


def profile_text(muni: str, vm_id: int) -> str | None:
    """The candidate's own prose, with VoteMate's own chrome left out."""
    url = PROFILE_URL.format(vm_id, RIDINGS[muni])
    html = fetch(url, "votemate")
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "form"]):
        tag.decompose()

    parts: list[str] = []
    # VoteMate wraps each section the candidate wrote in a .profile_block that
    # carries a heading ("Biography", "Reason for running", "Promises") and a
    # .profile_block_content holding the prose. Reading the heading's own div
    # instead returns the forty-character note under it, which is how the first
    # version of this found nothing on all 59 pages.
    for block in soup.find_all("div", class_=re.compile(r"\bprofile_block\b")):
        # Each block can hold a short summary and a long version, one after the
        # other with nothing between them. Reading the wrapper returns both
        # welded together: "...shares the same future as students My struggle
        # with the education system." Take the long one where it exists, since
        # the short one is a trimmed version of the same writing.
        inner = block.find_all("div", class_=re.compile(r"profile_\w+_(long|short)_content"))
        chosen = next((d for d in inner if "long" in " ".join(d.get("class") or [])), None)
        chosen = chosen or (inner[0] if inner else None)
        if chosen is None:
            continue
        text = re.sub(r"\s+", " ", chosen.get_text(" ", strip=True)).strip()
        if len(text) >= MIN_CHARS and text not in parts:
            parts.append(text)

    joined = "\n\n".join(parts)
    if EMPTY.search(soup.get_text(" ")) or len(joined) < MIN_CHARS:
        return None
    return joined


def scrape() -> dict:
    cands = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    by_name = {c["name"]: c for c in cands}
    # VoteMate spells two names differently from the ballot.
    aliases = {"Mathew Bond": "Mathew Bond", "Matthew Bond": "Mathew Bond"}

    found: dict[str, dict] = {}
    missing: list[str] = []
    for muni in ("cnv", "dnv"):
        ids = profile_ids(muni)
        for name, vm_id in ids.items():
            ballot = aliases.get(name, name)
            cand = by_name.get(ballot)
            if cand is None or cand["municipality"] != muni:
                continue
            url = PROFILE_URL.format(vm_id, RIDINGS[muni])
            text = profile_text(muni, vm_id)
            if text is None:
                missing.append(cand["name"])
                continue
            found[cand["id"]] = {
                "name": cand["name"], "url": url, "text": text,
                "retrieved": str(retrieved_at("votemate", url)),
            }
            print(f"  {cand['name']:24} {len(text):5} chars")
    print(f"\n{len(found)} profiles with content, {len(missing)} empty or unclaimed")
    if missing:
        print("  empty: " + ", ".join(sorted(missing)))
    return found


def main() -> int:
    found = scrape()
    OUT.write_text(json.dumps(found, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"-> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
