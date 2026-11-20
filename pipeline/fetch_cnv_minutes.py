"""Read the City of North Vancouver's council minutes and draft each member's vote.

    .venv/bin/python -m pipeline.fetch_cnv_minutes

The City publishes no vote table, only minutes PDFs. Its minutes follow one
consistent pattern, which this reads:

    PRESENT: Mayor L. Buchanan / Councillor H. Back / ...
    ABSENT: Councillor ...                       (when anyone is)
    5. Item title – File: ...
    Moved by Councillor Girard, seconded by Councillor Bell
    THAT ...
    CARRIED UNANIMOUSLY | (CARRIED UNANIMOUSLY BY CONSENT) | CARRIED | DEFEATED
    Councillor Back and Councillor Bell opposed.  (only when someone was)
    R2026-11-16/5                                 (the resolution number)

and "Councillor X left the meeting at 7:07 pm [and returned at 7:10 pm]."
lines, applied in the order they appear.

So, for each numbered resolution:
    present at that moment, not named as opposed  -> for
    named as opposed                              -> against
    absent, or out of the room at that moment     -> absent

This is an inference from the minutes, not a recorded roll call, and the site
says so. Anything the reading cannot be sure of goes into `needs_check` on the
vote, which the review file shows, so a person checks it against the PDF:
a conflict-of-interest declaration, someone leaving mid-item, a name it does
not recognise, a count that does not fit the result (a CARRIED motion with as
many against as for), or minutes that council has not yet adopted.

Procedural motions (approving the agenda, adopting minutes, adjourning, and
the single motion that approves the consent agenda as a block) are listed
separately and not drafted for review: the consent items themselves are.

Writes data/cnv_votes.json in the same shape as data/dnv_votes.json.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import re
import sys
from pathlib import Path

import yaml

from pipeline.fetching import fetch

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "promises-votes.yaml"
OUT = ROOT / "data" / "cnv_votes.json"
BASE = "https://www.cnv.org"

# "CARRIED", "(CARRIED UNANIMOUSLY BY CONSENT)", and prefixed forms such as
# "Amendment CARRIED" or "Main motion, as amended, CARRIED UNANIMOUSLY".
RESULT = re.compile(
    r"^(?:(?P<prefix>[A-Z][A-Za-z ,]{0,40}?),?\s+)?\(?(?P<res>CARRIED UNANIMOUSLY BY CONSENT|CARRIED BY CONSENT"
    r"|CARRIED UNANIMOUSLY|CARRIED|DEFEATED)\)?\.?$"
)
RESOLUTION = re.compile(r"^R\d{4}-\d{2}-\d{2}/\d+$")
OPPOSED = re.compile(r"^(.+?) opposed\.?$")
LEFT = re.compile(r"^(?:Mayor|Councillor) ([A-Z][\w'-]+) left the meeting\b(.*)$")
RETURNED = re.compile(r"^(?:Mayor|Councillor) ([A-Z][\w'-]+) returned to the meeting\b")
HEADING = re.compile(r"^(\d+)\.\s+(.+)$")
NOISE = re.compile(
    r"^(Document Number:.*|The Corporation of the City of North Vancouver Page .*|Continued…)$"
)
# Lines that end a wrapped item title.
TITLE_STOP = re.compile(r"^(–|Report:|Re:|Moved by|Submitted by|\(|CARRIED|DEFEATED|THAT\b|PURSUANT)")
PROCEDURAL_TITLE = re.compile(r"Council Meeting (Agenda|Minutes)|^THAT the meeting adjourn", re.I)
MONTHS = "January February March April May June July August September October November December".split()


def load_config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def listing(source_page: str) -> list[dict]:
    """Meetings on the City's agendas-and-minutes page, with their links."""
    html = fetch(source_page, "cnv-council-meetings", refresh=True)
    meetings = []
    for row in re.findall(r'<tr class="listItem">(.*?)</tr>', html, flags=re.S):
        date = re.search(r'council-meeting-date">([^<]+)<', row)
        kind = re.search(r'council-meeting-type">([^<]+)<', row)
        minutes = re.search(r'href="([^"]+Council-Meeting-Minutes[^"]+\.pdf)"', row)
        video = re.search(r'href="([^"]*council-videos\?videoid=[^"]+)"', row)
        if not date:
            continue
        d = dt.datetime.strptime(" ".join(date.group(1).split()), "%B %d %Y").date()
        meetings.append({
            "date": d.isoformat(),
            "meeting_type": " ".join(kind.group(1).split()) if kind else "",
            "minutes_url": BASE + minutes.group(1) if minutes else None,
            "video_url": video.group(1) if video else None,
        })
    # The page lists each meeting twice (two layouts of the same table).
    seen, unique = set(), []
    for m in meetings:
        key = (m["date"], m["meeting_type"], m["minutes_url"])
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique


def pdf_lines(blob: bytes) -> list[tuple[int, str]]:
    import pdfplumber
    out: list[tuple[int, str]] = []
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for n, page in enumerate(pdf.pages, start=1):
            for line in (page.extract_text() or "").splitlines():
                line = " ".join(line.split())
                if line and not NOISE.match(line):
                    out.append((n, line))
    return out


ATTENDEE = re.compile(r"^(Mayor|Councillor)\s+(?:[A-Z]\.\s*)*([A-Z][\w'-]+)(\*?)(.*)$")


def surname_of(phrase: str) -> str:
    m = ATTENDEE.match(phrase.strip())
    if m:
        return m.group(2)
    return phrase.replace("Councillor", "").replace("Mayor", "").strip().split()[-1].strip(".,*")


def split_names(phrase: str) -> list[str]:
    parts = re.split(r",\s*|\s+and\s+", phrase)
    return [surname_of(p) for p in parts if p.strip()]


def human_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


CLAUSE = re.compile(r"^(THAT|WHEREAS|AND THAT|THEREFORE|PURSUANT|BE IT|\d+\.\s|•|[a-z]\)\s)")


def reflow(lines: list[str]) -> str:
    """Join PDF-wrapped lines into paragraphs, breaking before each clause."""
    paras: list[str] = []
    for line in lines:
        if not paras or CLAUSE.match(line):
            paras.append(line)
        else:
            joiner = "" if paras[-1].endswith("-") and not paras[-1].endswith(" -") else " "
            paras[-1] = paras[-1] + joiner + line
    return "\n".join(paras).strip()


def read_attendance(lines: list[tuple[int, str]]) -> tuple[set[str], set[str], list[str]]:
    """PRESENT and ABSENT council members from the top of the minutes.

    Handles both layouts the City uses: a single "PRESENT:" column, and a
    two-column "COUNCIL MEMBERS / STAFF MEMBERS" table, where each line starts
    with the council member and continues with a staff name.
    """
    present: set[str] = set()
    absent: set[str] = set()
    notes: list[str] = []
    mode = None
    for _, line in lines[:45]:
        if re.match(r"^(The meeting was called to order|CALL TO ORDER|APPROVAL OF AGENDA)", line):
            break
        if line.startswith("PRESENT"):
            mode, line = "present", line[len("PRESENT"):].lstrip(": ")
        elif line.startswith("ABSENT"):
            mode, line = "absent", line[len("ABSENT"):].lstrip(": ")
        m = ATTENDEE.match(line)
        if mode and m:
            (present if mode == "present" else absent).add(m.group(2))
            rest = m.group(4).strip()
            if re.search(r"\b(joined|left|arrived|departed)\b", rest):
                notes.append(f"{m.group(1)} {m.group(2)} {rest.strip('() ')}")
    return present, absent, notes


def parse_minutes(lines: list[tuple[int, str]], members: dict[str, str]) -> tuple[list[dict], list[dict], list[str]]:
    """Return (resolutions, procedural, meeting-level problems)."""
    problems: list[str] = []
    present, absent, late = read_attendance(lines)
    unknown = (present | absent) - set(members)
    if unknown:
        problems.append("attendance names people not on the 2026-2030 council: " + ", ".join(sorted(unknown)))
    if not present:
        problems.append("could not read the PRESENT list")
    meeting_flags = [f"attendance note at the top of the minutes: {n}; check which items they voted on" for n in late]
    out_of_room: set[str] = set()

    def note_attendance(text: str) -> bool:
        lm, rm = LEFT.match(text), RETURNED.match(text)
        if lm and "returned" not in lm.group(2):
            out_of_room.add(lm.group(1))
        if rm:
            out_of_room.discard(rm.group(1))
        return bool(lm or rm)

    resolutions, procedural = [], []
    claimed: set[str] = set()
    section, heading, re_line = "", "", ""
    i = 0
    while i < len(lines):
        page, line = lines[i]

        if note_attendance(line):
            i += 1
            continue
        if line.endswith("– Continued"):
            i += 1
            continue
        if line.isupper() and len(line) > 3 and not RESULT.match(line) and not line.startswith("R20"):
            section = line.title()
            i += 1
            continue
        hm = HEADING.match(line)
        if hm:
            title, j = hm.group(2), i + 1
            while "File:" not in title and j < min(i + 4, len(lines)) \
                    and not TITLE_STOP.match(lines[j][1]) and not HEADING.match(lines[j][1]):
                title += " " + lines[j][1]
                j += 1
            if "File:" not in title and j < len(lines) and lines[j][1].startswith("–"):
                title += " " + lines[j][1]
                j += 1
            if "Continued" not in title:
                heading, re_line = re.split(r"\s+–\s+File:", title)[0].strip(), ""
            i = j
            continue
        if line.startswith("Re:"):
            re_line, j = line[3:].strip(), i + 1
            while j < len(lines) and not TITLE_STOP.match(lines[j][1]) and not HEADING.match(lines[j][1]):
                re_line += " " + lines[j][1]
                j += 1
            i = j
            continue

        if not line.startswith("Moved by"):
            i += 1
            continue

        # A motion runs from "Moved by" to its resolution number. On the way
        # there may be amendments ("Amendment CARRIED"), a motion voted in
        # parts, or people leaving the room. The last result before the number
        # is the vote on the motion as a whole.
        start_page = page
        body: list[str] = []
        results: list[tuple[str, str, list[str]]] = []  # (prefix, result, opposed)
        flags = list(meeting_flags)
        number = None
        j = i + 1
        while j < len(lines):
            text = lines[j][1]
            if RESOLUTION.match(text):
                number = text
                j += 1
                break
            rm = RESULT.match(text)
            if rm:
                opposed: list[str] = []
                if j + 1 < len(lines):
                    om = OPPOSED.match(lines[j + 1][1])
                    if om:
                        opposed = split_names(om.group(1))
                        j += 1
                results.append(((rm.group("prefix") or "").strip(" ,"), rm.group("res"), opposed))
                j += 1
                continue
            sub_motion = results and re.search(r"amend|refer|motion to", results[-1][0], re.I)
            if results and not sub_motion and (text.startswith("Moved by") or HEADING.match(text)
                                               or (text.isupper() and len(text) > 3)):
                break  # the previous motion had no number; this is the next item
            if text.endswith("– Continued") or (
                HEADING.match(text) and j + 1 < len(lines) and lines[j + 1][1].endswith("– Continued")
            ):
                j += 1  # a heading repeated at the top of a new page
                continue
            if note_attendance(text):
                flags.append(f"attendance changed during this item: {text}")
            elif "conflict" in text.lower() and ("declare" in text.lower() or "interest" in text.lower()):
                flags.append(f"conflict of interest mentioned: {text}")
            else:
                body.append(text)
            j += 1

        motion_text = reflow(body)
        first = body[0] if body else ""
        nested = HEADING.match(first)
        if motion_text.startswith("THAT the meeting adjourn"):
            title = "Adjourn the meeting"
        elif "“Consent Agenda” be approved" in motion_text:
            title = "Approve the consent agenda as a block"
        elif "Closed Session" in motion_text or "Closed session" in motion_text:
            title = "Ratify items from the closed session (wording kept closed)"
        elif nested and not motion_text.startswith(("THAT", "PURSUANT", "WHEREAS")):
            title = nested.group(2)
        else:
            title = re_line or heading or first
        title = " ".join(re.split(r"\s+–\s+File:", title)[0].split())
        if number:
            claimed.add(number)

        record = {"number": number, "section": section, "title": title,
                  "resolution_text": motion_text, "page": start_page}
        if number is None or not results or PROCEDURAL_TITLE.search(title) \
                or PROCEDURAL_TITLE.search(motion_text) or title.startswith(("Approve the consent", "Ratify items")):
            procedural.append(record)
            i = j
            continue

        if len(results) > 1:
            parts = "; ".join(f"{p + ' ' if p else ''}{r}" + (f" ({', '.join(o)} opposed)" if o else "")
                              for p, r, o in results)
            flags.append(f"more than one vote on this item ({parts}). The votes shown are for the last "
                         "one; correct `votes` if the motion was voted on in parts")
        prefix, result, opposed = results[-1]
        unknown_opp = [s for s in opposed if s not in members]
        if unknown_opp:
            flags.append("opposed names not on the council: " + ", ".join(unknown_opp))
        if "UNANIMOUSLY" in result and opposed:
            flags.append("marked unanimous but names someone as opposed")
        in_room = (present - absent) - out_of_room
        decisions: dict[str, str] = {}
        for surname, cid in members.items():
            if surname in opposed:
                decisions[cid] = "against"
            elif surname in in_room:
                decisions[cid] = "for"
            else:
                decisions[cid] = "absent"
        n_for = sum(1 for d in decisions.values() if d == "for")
        n_against = sum(1 for d in decisions.values() if d == "against")
        carried = result.startswith("CARRIED")
        if carried and n_for <= n_against:
            flags.append(f"reads as {n_for} for, {n_against} against, but the motion CARRIED")
        if not carried and n_for > n_against:
            flags.append(f"reads as {n_for} for, {n_against} against, but the motion was DEFEATED")
        record.update({"result": "Carried" if carried else "Defeated", "members": decisions, "needs_check": flags})
        resolutions.append(record)
        i = j

    # Resolution numbers that belong to no motion we read: council inquiries,
    # closed-session items listed under one ratifying motion. Not votes we
    # show, but listed so a person can see nothing was silently skipped.
    for page, text in lines:
        if RESOLUTION.match(text) and text not in claimed:
            procedural.append({"number": text, "section": "", "title": "Numbered item with no separate public vote "
                               "(an inquiry, an item removed from the agenda, or a closed-session item)", "resolution_text": "", "page": page})
    return resolutions, procedural, problems


def main() -> int:
    cfg = load_config()
    muni = cfg["municipalities"]["cnv"]
    members = {names[0]: cid for cid, names in muni["members"].items()}
    meetings = listing(muni["source_page"])
    if len(meetings) < 10:
        print(f"!! Only {len(meetings)} meetings found on the City's page. Its layout may have changed. Stopping.")
        return 1

    with_minutes = [m for m in meetings if m["minutes_url"]]
    texts: dict[str, list[tuple[int, str]]] = {}
    # Minutes are adopted at a later meeting. Until then they may still change,
    # so unadopted ones are re-fetched every run; adopted ones come from cache.
    for m in sorted(with_minutes, key=lambda m: m["date"]):
        if m["date"] < cfg["term_start"]:
            continue
        blob = fetch(m["minutes_url"], "cnv-minutes", suffix=".pdf", binary=True, refresh=False)
        texts[m["minutes_url"]] = pdf_lines(blob)
    adopted_phrases = "\n".join(l for t in texts.values() for _, l in t)

    votes, procedural_all, held_back, problems_all = [], [], [], []
    for m in sorted(with_minutes, key=lambda m: m["date"]):
        if m["date"] < cfg["term_start"]:
            continue
        lines = texts[m["minutes_url"]]
        phrase = f"Minutes, {human_date(m['date'])}"
        adopted = phrase in adopted_phrases
        if not adopted:
            blob = fetch(m["minutes_url"], "cnv-minutes", suffix=".pdf", binary=True, refresh=True)
            lines = pdf_lines(blob)
        resolutions, procedural, problems = parse_minutes(lines, members)
        for p in problems:
            problems_all.append(f"{m['date']}: {p}")
        for r in procedural:
            procedural_all.append({"date": m["date"], "title": r["title"], "number": r["number"]})
        for r in resolutions:
            flags = list(r["needs_check"])
            item = {
                "id": f"cnv-{r['number']}",
                "municipality": "cnv",
                "source_kind": "city_minutes",
                "date": m["date"],
                "item_number": r["number"],
                "title": r["title"],
                "meeting_type": m["meeting_type"],
                "result": r["result"],
                "resolution_text": r["resolution_text"],
                "district_categories": [],
                "minutes_url": f"{m['minutes_url']}#page={r['page']}",
                "video_url": m["video_url"],
                "members": r["members"],
                "needs_check": flags,
                "minutes_adopted": adopted,
            }
            if problems:
                held_back.append({"id": item["id"], "date": item["date"], "title": item["title"],
                                  "reason": "; ".join(problems)})
            else:
                votes.append(item)

    OUT.write_text(json.dumps({
        "retrieved": dt.date.today().isoformat(),
        "municipality": "cnv",
        "source_page": muni["source_page"],
        "term_start": cfg["term_start"],
        "meetings_read": [m["date"] for m in with_minutes if m["date"] >= cfg["term_start"]],
        "votes": votes,
        "held_back": held_back,
        "no_motion": [],
        "procedural": procedural_all,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"{len(meetings)} meetings listed; read minutes for {len(texts)} since {cfg['term_start']}")
    print(f"  {len(votes)} resolutions drafted, {len(procedural_all)} procedural, {len(held_back)} held back")
    for v in votes:
        if v["needs_check"]:
            print(f"  check {v['id']}: " + "; ".join(v["needs_check"]))
    for p in problems_all:
        print(f"  !! {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
