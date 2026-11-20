"""Draft issue matches and plain-language summaries for new council votes.

    .venv/bin/python -m pipeline.draft_vote_matches            # hints + model
    .venv/bin/python -m pipeline.draft_vote_matches --no-ai    # hints only

For every vote in data/dnv_votes.json that is not yet in data/vote-review.yaml,
appends a *draft* entry with status "pending". Nothing drafted here publishes:
build_votes only publishes entries a person has changed to "approved".

Two sources of suggestions:

  hints   the District's own category on the row, mapped to this site's issues
          in config/promises-votes.yaml. Free and predictable, often too broad.
  model   one short Claude call per vote proposing up to two issues, a reason,
          and a one-sentence plain-language summary. Cached in
          data/vote-matching-cache.json on vote id + a hash of the official
          text, so a re-run never pays twice for the same row. At the
          District's pace (~15 items a month) this is a cent or two a month.

The summary is a draft for a person to rewrite or accept. It is published as
"our summary", with the official resolution text one click away.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
VOTE_FILES = {"dnv": ROOT / "data" / "dnv_votes.json", "cnv": ROOT / "data" / "cnv_votes.json"}
COUNCIL = {"dnv": "District of North Vancouver", "cnv": "City of North Vancouver"}
REVIEW = ROOT / "data" / "vote-review.yaml"
CACHE = ROOT / "data" / "vote-matching-cache.json"
CONFIG = ROOT / "config" / "promises-votes.yaml"
TAXONOMY = ROOT / "site" / "src" / "data" / "taxonomy.json"

MODEL = "claude-opus-5-5"

REVIEW_HEADER = """\
# Promises and votes: the review file. Nothing here publishes until you say so.
#
# Each entry is one council vote since the new councils took office, from the
# District (its own vote table) or the City (read from its minutes).
# pipeline.draft_vote_matches drafted it; you decide it. For each entry:
#
#   1. Read `official_text` (the resolution) and `title`. `minutes` links to
#      the page of the minutes it comes from.
#   2. Fix `summary` until it is one plain, neutral sentence about what the
#      motion did. It publishes as "our summary". No adjectives about the
#      item, no mention of who voted which way.
#   3. Set `issues` to the issue ids it belongs under (any of the ids listed
#      below), or [] if it relates to none. `proposed_issues` is only the draft.
#   4. City entries only: `votes` is each member's vote AS READ FROM THE
#      MINUTES (present and not named as opposed = for). If `needs_check`
#      lists anything, open the minutes, correct `votes` if needed, and set
#      `checked_against_minutes: true`. An entry with needs_check cannot be
#      approved without it.
#   5. Change `status` to `approved`. Leave it `pending` to decide later.
#      An approved vote with issues: [] still appears in each member's full
#      list of votes, just not under an issue.
#
# Then run: .venv/bin/python -m pipeline.build_votes
#
# Issue ids: {ids}
"""


def load_review() -> list[dict]:
    if not REVIEW.exists():
        return []
    body = yaml.safe_load(REVIEW.read_text(encoding="utf-8"))
    return (body or {}).get("entries", []) if isinstance(body, dict) else (body or [])


def write_review(entries: list[dict], ids: list[str]) -> None:
    text = REVIEW_HEADER.format(ids=", ".join(ids)) + "\n"
    text += yaml.safe_dump(
        {"entries": entries}, sort_keys=False, allow_unicode=True, width=88,
    )
    REVIEW.write_text(text, encoding="utf-8")


def text_key(vote: dict) -> str:
    h = hashlib.sha256(
        " ".join((vote["title"] + " " + vote["resolution_text"]).split()).encode("utf-8")
    ).hexdigest()[:16]
    return f"{vote['id']}:{h}"


def hint_issues(vote: dict, hints: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    for cat in vote["district_categories"]:
        for issue in hints.get(cat, []):
            if issue not in out:
                out.append(issue)
    return out


SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["issues", "reason", "summary"],
    "additionalProperties": False,
}


def system_prompt(categories: list[dict], council: str) -> str:
    lines = "\n".join(f"- {c['id']}: {c['label']}. {c['description']}" for c in categories)
    return f"""You help a non-partisan local voter guide in North Vancouver, BC.
You will see one item the {council} council voted on: its title, the
official resolution text, the result, and any category labels the
municipality gave it (it may give none).

Do two things.

1. Pick the issues this vote clearly belongs under, from this list only:
{lines}
Pick at most two, and pick none (an empty list) when the item is procedural
or does not plainly bear on any of them (minutes, agenda changes, routine
appointments, closed-meeting procedure). A wrong match is worse than no match:
a reader will see this vote beside what a councillor promised on that issue.
Give a one-sentence reason a reviewer can check against the text.

2. Write one plain-language sentence, at most 25 words, saying what the motion
did, for a resident who does not know council jargon. Rules: describe the
item, not the debate. No evaluative words (good, controversial, finally,
important). Do not name councillors or say how anyone voted. Do not add facts
that are not in the text. Use the past tense, for example "Gave third reading
to a bylaw rezoning 1234 Example Road for a 60-unit rental building." If the
text is too thin to say more, say only what it does say."""


def ask_model(client, vote: dict, categories: list[dict]) -> dict | None:
    council = COUNCIL[vote.get("municipality", "dnv")]
    allowed = {c["id"] for c in categories}
    user = json.dumps({
        "title": vote["title"],
        "official_resolution_text": vote["resolution_text"],
        "result": vote["result"],
        "municipality_categories": vote["district_categories"],
        "meeting_type": vote["meeting_type"],
    }, ensure_ascii=False, indent=1)
    resp = client.beta.messages.create(
        model=MODEL,
        max_tokens=2000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=system_prompt(categories, council),
        messages=[{"role": "user", "content": user}],
    )
    if resp.stop_reason == "refusal":
        return None
    text = next((b.text for b in resp.content if b.type == "text"), "")
    data = json.loads(text)
    # The model may only choose from the list; anything else is dropped rather
    # than quietly becoming a new issue.
    data["issues"] = [i for i in data["issues"] if i in allowed][:2]
    data["summary"] = " ".join(data["summary"].split())
    return data


def main() -> int:
    use_ai = "--no-ai" not in sys.argv
    votes = []
    for muni, path in VOTE_FILES.items():
        if not path.exists():
            print(f"Missing {path.relative_to(ROOT)}: run pipeline.fetch_dnv_votes and pipeline.fetch_cnv_minutes first.")
            return 1
        votes += json.loads(path.read_text(encoding="utf-8"))["votes"]
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    surname = {cid: names[0] for cid, names in cfg["municipalities"]["cnv"]["members"].items()}
    categories = json.loads(TAXONOMY.read_text(encoding="utf-8"))["categories"]
    ids = [c["id"] for c in categories]

    entries = load_review()
    known = {e["vote_id"] for e in entries}
    new = [v for v in votes if v["id"] not in known]

    cache: dict = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    client = None
    if use_ai and new:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            env = ROOT / ".env"
            if env.exists():
                for line in env.read_text().splitlines():
                    if line.startswith("ANTHROPIC_API_KEY=") and line.split("=", 1)[1].strip():
                        os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip()
        import anthropic
        client = anthropic.Anthropic()

    called = reused = 0
    for v in new:
        hints = hint_issues(v, cfg.get("category_hints", {}))
        drafted = None
        if client is not None:
            key = text_key(v)
            drafted = cache.get(key)
            if drafted is None:
                try:
                    drafted = ask_model(client, v, categories)
                except Exception as e:  # a failed draft is a blank draft, never a crash
                    print(f"  model draft failed for #{v['id']}: {type(e).__name__}: {e}")
                    drafted = None
                if drafted is not None:
                    cache[key] = drafted
                    called += 1
            else:
                reused += 1
        proposed = drafted["issues"] if drafted else hints
        entry = {
            "vote_id": v["id"],
            "municipality": v["municipality"],
            "date": v["date"],
            "title": v["title"],
            "result": v["result"],
            "minutes": v["minutes_url"],
            "official_text": v["resolution_text"],
            "municipality_categories": v["district_categories"],
            "category_hints": hints,
            "proposed_issues": proposed,
            "proposal_reason": drafted["reason"] if drafted else "Category hints only; no model draft.",
            "issues": list(proposed),
            "summary": drafted["summary"] if drafted else "",
        }
        if v["municipality"] == "cnv":
            entry["votes"] = {surname[cid]: d for cid, d in v["members"].items()}
            entry["needs_check"] = v.get("needs_check", [])
            entry["checked_against_minutes"] = False
        entry["status"] = "pending"
        entries.append(entry)

    entries.sort(key=lambda e: (e["date"], e["vote_id"]))
    write_review(entries, ids)
    if client is not None:
        CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    pending = sum(1 for e in entries if e["status"] == "pending")
    print(f"{len(new)} new votes drafted ({called} model calls, {reused} from cache)")
    print(f"{pending} entries waiting for review in {REVIEW.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
