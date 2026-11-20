"""Fetch the District of North Vancouver's council vote table, keep the new term.

    .venv/bin/python -m pipeline.fetch_dnv_votes

Reads the JSON behind https://www.dnv.org/page/council-voting-decisions (the
same rows its "Download complete table (.xlsx)" button exports), saves the raw
response under data/raw/ as the audit trail, and writes data/dnv_votes.json
with three lists:

  votes       rows from the 2026-2030 council: on or after term_start, a
              motion was put, and every member named is on the new council
  held_back   new-term rows that name someone who is not on the new council.
              The table has carried the old member list on a new-term row
              before, so these are never counted; a person looks at them.
  no_motion   new-term rows where no motion was put and nobody voted, such as
              orientation workshops. Kept so the page can say they happened.

Nothing here decides which issue a vote belongs to. That is draft_vote_matches
(a proposal) and data/vote-review.yaml (a person's decision).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import yaml

from pipeline.fetching import fetch

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "promises-votes.yaml"
OUT = ROOT / "data" / "dnv_votes.json"

DECISIONS = {"for": "for", "against": "against", "absent": "absent", "n/a": "n/a"}


def load_config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def name_index(muni: dict) -> dict[str, str]:
    """Every accepted spelling, lower-cased, to a candidate id."""
    out: dict[str, str] = {}
    for cid, names in muni["members"].items():
        for n in names:
            out[" ".join(n.lower().split())] = cid
    return out


def normalise(row: dict, names: dict[str, str]) -> tuple[dict, list[str]]:
    members: dict[str, str] = {}
    unknown: list[str] = []
    for v in row.get("votes") or []:
        key = " ".join((v.get("name") or "").lower().split())
        decision = DECISIONS.get((v.get("decision") or "").strip().lower())
        if decision is None:
            raise ValueError(f"row {row['id']}: unknown decision {v.get('decision')!r}")
        cid = names.get(key)
        if cid is None:
            unknown.append(v.get("name") or "?")
        else:
            members[cid] = decision
    return {
        "id": f"dnv-{row['id']}",
        "municipality": "dnv",
        "source_kind": "district_table",
        "needs_check": [],
        "date": row["meetingDate"][:10],
        "item_number": row.get("itemNumber") or "",
        "title": " ".join((row.get("itemTitle") or "").split()),
        "meeting_type": row.get("meetingType") or "",
        "result": row.get("resolution") or "",
        "resolution_text": (row.get("resolutionDescription") or "").strip(),
        "district_categories": [c["type"] for c in row.get("categories") or []],
        "minutes_url": row.get("minuteLink") or None,
        "video_url": row.get("videoLink") or None,
        "members": members,
    }, unknown


def main() -> int:
    cfg = load_config()
    muni = cfg["municipalities"]["dnv"]
    names = name_index(muni)
    raw = fetch(muni["api_url"], "dnv-council-votes", suffix=".json", refresh=True)
    rows = json.loads(raw)
    if not isinstance(rows, list) or len(rows) < 500:
        # The 2022-2026 term alone is 750+ rows. Far fewer means the endpoint
        # changed or failed quietly, and an empty table must not read as
        # "the council has not voted on anything".
        print(f"!! The vote table returned {len(rows) if isinstance(rows, list) else 'no'} rows. Stopping.")
        return 1

    votes, held_back, no_motion = [], [], []
    for row in sorted(rows, key=lambda r: (r["meetingDate"], str(r.get("itemNumber")), r["id"])):
        if row["meetingDate"][:10] < cfg["term_start"]:
            continue
        item, unknown = normalise(row, names)
        decisions = [v.get("decision", "").strip().lower() for v in row.get("votes") or []]
        if all(d == "n/a" for d in decisions) and item["result"] in ("", "None"):
            no_motion.append({k: item[k] for k in ("id", "date", "title", "meeting_type", "resolution_text", "minutes_url", "video_url")})
        elif unknown:
            held_back.append({
                "id": item["id"], "date": item["date"], "title": item["title"],
                "reason": "names people who are not on the 2026-2030 council: " + ", ".join(unknown),
            })
        else:
            missing = [cid for cid in muni["members"] if cid not in item["members"]]
            if missing:
                held_back.append({
                    "id": item["id"], "date": item["date"], "title": item["title"],
                    "reason": "no recorded decision for: " + ", ".join(missing),
                })
            else:
                votes.append(item)

    OUT.write_text(json.dumps({
        "retrieved": dt.date.today().isoformat(),
        "municipality": "dnv",
        "source_page": muni["source_page"],
        "api_url": muni["api_url"],
        "term_start": cfg["term_start"],
        "rows_in_table": len(rows),
        "votes": votes,
        "held_back": held_back,
        "no_motion": no_motion,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"{len(rows)} rows in the District's table")
    print(f"  since {cfg['term_start']}: {len(votes)} votes by the new council, "
          f"{len(no_motion)} items with no motion, {len(held_back)} held back")
    for h in held_back:
        print(f"  held back: {h['date']} #{h['id']} {h['title']} ({h['reason']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
