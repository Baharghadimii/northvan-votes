"""Publish the approved part of the vote review to the site.

    .venv/bin/python -m pipeline.build_votes

Reads data/dnv_votes.json and data/cnv_votes.json (what each municipality
published) and data/vote-review.yaml (what a person decided), and writes
site/src/data/votes.json with only the entries marked `approved`.

Refuses to write anything, and exits non-zero, when an approved entry:
  - points at a vote that is no longer in the municipality's record,
  - names an issue that is not in the taxonomy,
  - has an empty or placeholder summary, or one longer than 220 characters,
  - mentions a council member by surname in "our summary" (the summary
    describes the item; how each person voted is shown separately),
  - is a City vote the parser flagged (`needs_check`) and nobody has marked
    `checked_against_minutes: true`,
  - is a City vote whose corrected `votes` names someone not on the council
    or a decision other than for / against / absent.

A vote with no review entry yet, or still `pending`, is counted and left out.
The page says how many are waiting, rather than pretending they don't exist.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
VOTE_FILES = {"dnv": ROOT / "data" / "dnv_votes.json", "cnv": ROOT / "data" / "cnv_votes.json"}
REVIEW = ROOT / "data" / "vote-review.yaml"
CONFIG = ROOT / "config" / "promises-votes.yaml"
TAXONOMY = ROOT / "site" / "src" / "data" / "taxonomy.json"
CANDIDATES = ROOT / "site" / "src" / "data" / "candidates.json"
OUT = ROOT / "site" / "src" / "data" / "votes.json"
DECISIONS = {"for", "against", "absent", "n/a"}


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    issue_ids = {c["id"] for c in json.loads(TAXONOMY.read_text(encoding="utf-8"))["categories"]}
    cands = {c["id"]: c for c in json.loads(CANDIDATES.read_text(encoding="utf-8"))}
    tables = {m: json.loads(p.read_text(encoding="utf-8")) for m, p in VOTE_FILES.items()}
    members = {m: list(cfg["municipalities"][m]["members"]) for m in tables}
    surnames = [cands[cid]["surname"] for ids in members.values() for cid in ids]
    cnv_by_surname = {names[0]: cid for cid, names in cfg["municipalities"]["cnv"]["members"].items()}

    entries = []
    if REVIEW.exists():
        body = yaml.safe_load(REVIEW.read_text(encoding="utf-8")) or {}
        entries = body.get("entries", []) if isinstance(body, dict) else body
    by_id = {e["vote_id"]: e for e in entries}
    votes = {v["id"]: v for t in tables.values() for v in t["votes"]}

    problems: list[str] = []
    published = []
    for e in entries:
        vid = e["vote_id"]
        if e.get("status") != "approved":
            if e.get("status") not in ("pending", None):
                problems.append(f"{vid}: status must be pending or approved, not {e.get('status')!r}")
            continue
        v = votes.get(vid)
        if v is None:
            problems.append(f"{vid}: approved, but no longer in the municipality's record")
            continue
        summary = " ".join(str(e.get("summary") or "").split())
        if not summary or summary.upper().startswith(("TODO", "WRITE")):
            problems.append(f"{vid}: approved with no summary")
        if len(summary) > 220:
            problems.append(f"{vid}: summary is {len(summary)} characters; keep it to one sentence")
        words = summary.lower().replace("’", "'").split()
        for s in surnames:
            if s.lower() in words or f"{s.lower()}'s" in words:
                problems.append(f"{vid}: summary names {s}; describe the item, not the people")
        issues = list(e.get("issues") or [])
        bad = [i for i in issues if i not in issue_ids]
        if bad:
            problems.append(f"{vid}: unknown issue id(s) {bad}")

        decided = dict(v["members"])
        if v["municipality"] == "cnv":
            if v.get("needs_check") and e.get("checked_against_minutes") is not True:
                problems.append(f"{vid}: the minutes reading was flagged ({'; '.join(v['needs_check'])}). "
                                "Check it and set checked_against_minutes: true")
            corrected = e.get("votes") or {}
            for name, d in corrected.items():
                if name not in cnv_by_surname:
                    problems.append(f"{vid}: votes names {name!r}, who is not on the City council")
                elif d not in DECISIONS:
                    problems.append(f"{vid}: {name} has decision {d!r}; use for, against or absent")
                else:
                    decided[cnv_by_surname[name]] = d
        published.append({**v, "members": decided, "summary": summary, "issues": issues})

    if problems:
        print("!! The vote review has problems. Nothing written.")
        for p in problems:
            print("   " + p)
        return 1

    published.sort(key=lambda v: (v["date"], v["municipality"], str(v["item_number"]), v["id"]))
    status = {}
    for m, t in tables.items():
        status[m] = {
            "retrieved": t["retrieved"],
            "source_page": t["source_page"],
            "awaiting_review": sum(1 for v in t["votes"] if by_id.get(v["id"], {}).get("status") != "approved"),
            "held_back": len(t["held_back"]),
            "no_motion": t.get("no_motion", []),
            "procedural": len(t.get("procedural", [])),
            "meetings_read": t.get("meetings_read", []),
        }
    OUT.write_text(json.dumps({
        "term_start": cfg["term_start"],
        "members": members,
        "status": status,
        "published": published,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for m, s in status.items():
        n = sum(1 for v in published if v["municipality"] == m)
        print(f"{m}: {n} approved votes published, {s['awaiting_review']} awaiting review, "
              f"{s['held_back']} held back")
    return 0


if __name__ == "__main__":
    sys.exit(main())
