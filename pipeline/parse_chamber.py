"""Candidate answers to the North Vancouver Chamber's two business questions.

Like the bear questionnaire, this is somebody else's question rather than
anything the candidate published themselves, so it stays out of the normal
pipeline and off their positions. The Chamber invited every mayor and council
candidate in both municipalities, allowed 200 words per answer, and published
every reply it received by its deadline.

Each answer is checked to be a literal substring of the text saved under
data/raw/chamber/, the same guarantee as every other quote on this site.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "chamber"
OUT = ROOT / "data" / "chamber.json"
CANDIDATES = ROOT / "data" / "candidates.json"
SOURCE = "https://www.nvchamber.ca/blog/municipal-election-qas/"

QUESTIONS = [
    "If elected, what is your vision for improved transportation in North Vancouver?",
    "Costs are rising and small business is feeling the squeeze. What will you do to "
    "support small businesses and foster business and job growth in North Vancouver?",
]

# The Chamber spells one name differently from the ballot.
ALIASES = {"Matthew Bond": "Mathew Bond"}

# Every PDF repeats the same preamble before the candidate's own words start.
# Answer 1 opens at a line beginning "1." after the candidate's name, and
# answer 2 at "2."; nothing else in these documents starts a line that way.
ANSWER = re.compile(r"^([12])\.\s+(.*)$")


def answers_from(text: str) -> dict[int, tuple[int, int]]:
    """Character spans for answers 1 and 2, found after the questions block.

    The questions themselves are numbered too, so the search starts below them:
    the candidate's name is the last line before their first answer.
    """
    body_start = text.find("\n", text.find(QUESTIONS[1][-40:]))
    if body_start < 0:
        body_start = 0
    spans: dict[int, tuple[int, int]] = {}
    starts: list[tuple[int, int]] = []
    pos = body_start
    for line in text[body_start:].split("\n"):
        m = ANSWER.match(line)
        if m:
            starts.append((int(m.group(1)), pos + len(m.group(0)) - len(m.group(2))))
        pos += len(line) + 1
    for i, (num, start) in enumerate(starts):
        end = starts[i + 1][1] - len(f"{starts[i + 1][0]}. ") if i + 1 < len(starts) else len(text)
        spans[num] = (start, end)
    return spans


def tidy(text: str, start: int, end: int) -> str:
    """The span, with the PDF's hard line wraps turned back into sentences.

    pdfplumber keeps the line breaks the layout happened to use. Joining them is
    the one change made to a quote, and it is reversible: the words, in order,
    are exactly the words in the file.
    """
    raw = text[start:end].strip()
    return re.sub(r"\s*\n\s*", " ", raw).strip()


def combined_span(text: str, name: str) -> tuple[int, int] | None:
    """Everything the candidate wrote, for a reply that isn't numbered.

    Ken Izatt answered both questions in one piece of prose rather than as 1.
    and 2., and the numbered parser found nothing in his file, which would have
    filed him with the people who never replied. His name is the last line of
    the Chamber's heading, so his answer is everything after it.
    """
    marker = f"\n{name}\n"
    i = text.find(marker)
    if i < 0:
        return None
    return i + len(marker), len(text)


def parse_one(name: str, path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    spans = answers_from(text)
    if 1 not in spans or 2 not in spans:
        whole = combined_span(text, name)
        if whole is None:
            print(f"    !! {name}: found answers {sorted(spans)}, and no name heading either")
            return None
        answer = tidy(text, *whole)
        if re.sub(r"\s+", " ", answer) not in re.sub(r"\s+", " ", text):
            print(f"    !! {name}: combined answer is not a slice of the file")
            return None
        print(f"    {name}: answered both questions in one piece, kept whole")
        return {"answer1": answer, "combined": True}
    out = {}
    for num, (start, end) in sorted(spans.items()):
        answer = tidy(text, start, end)
        # Verbatim check, against the whitespace-collapsed source.
        flat = re.sub(r"\s+", " ", text)
        if re.sub(r"\s+", " ", answer) not in flat:
            print(f"    !! {name}: answer {num} is not a slice of the file")
            return None
        out[f"answer{num}"] = answer
    return out


def main() -> int:
    index = json.loads((RAW / "index.json").read_text(encoding="utf-8"))
    cands = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    by_name = {
        c["name"]: c
        for c in cands
        if c["office"] in ("mayor", "council")
    }

    answers: list[dict] = []
    seen: set[str] = set()
    for name, meta in index["candidates"].items():
        ballot = ALIASES.get(name, name)
        cand = by_name.get(ballot)
        if cand is None:
            print(f"    !! {name}: no candidate on the ballot by that name")
            continue
        parsed = parse_one(name, RAW / meta["text_file"])
        if parsed is None:
            continue
        seen.add(cand["id"])
        answers.append({
            "candidate_id": cand["id"],
            "name": cand["name"],
            "municipality": cand["municipality"],
            "pdf": meta["url"],
            **parsed,
        })

    out = {"source": SOURCE, "questions": QUESTIONS, "municipalities": {}}
    for muni in ("cnv", "dnv"):
        asked = [c for c in by_name.values() if c["municipality"] == muni]
        mine = [a for a in answers if a["municipality"] == muni]
        non = [{"name": c["name"], "candidate_id": c["id"]} for c in asked if c["id"] not in seen]
        out["municipalities"][muni] = {
            "answers": mine, "nonresponders": non, "asked": len(asked),
        }
        print(f"{muni}: {len(mine)} answered, {len(non)} did not, of {len(asked)} asked")

    payload = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    OUT.write_text(payload, encoding="utf-8")
    site = ROOT / "site" / "src" / "data" / "chamber.json"
    site.write_text(payload, encoding="utf-8")
    print(f"-> {OUT.relative_to(ROOT)} and {site.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
