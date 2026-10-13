"""Candidate answers to the North Shore Bear Advocates question.

Not a filed statement and not a campaign site, so it does not go through the
normal pipeline and does not appear as a candidate's "position". It is one
organisation's question, put to every mayor and council candidate on the North
Shore, with the answers published in full. That is a different kind of source
and the site says so on the page.

The exported documents live in data/raw/bears/ and are the thing quoted from:
every answer here is checked to be a literal substring of the file (line endings
normalised, nothing else), the same guarantee as everywhere else.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "bears"
OUT = ROOT / "data" / "bears.json"
CANDIDATES = ROOT / "data" / "candidates.json"

DOC_URLS = {
    "cnv": "https://docs.google.com/document/d/1YV9vVgJsZ_X8P2o2Mi_UOafmWpk6QWRWMeh4faAsNHQ/edit",
    "dnv": "https://docs.google.com/document/d/1L3Yk6973Qx1mddPKAix5mp1UhlDBRGCfn6_KR03FQ18/edit",
}

# Emails open with a greeting and close with a signature block. Neither is the
# answer, and the signatures carry phone numbers we are not republishing.
# Only a bare salutation. Daina Boyd opens "Hi Lindsay thanks for the email. I
# am so saddened by the recent deaths of bears..." on one line, and stripping
# the whole line threw her answer away.
GREETING = re.compile(
    r"^(hi|hello|dear|good\s+(morning|afternoon|evening)|greetings|hey)\b[\w\s,.!-]{0,24}$",
    re.I,
)
# Short enough to be a sign-off rather than a sentence. Betty Forbes closes
# "Yours, in community and conversation." and her phone number follows it.
SIGNOFF = re.compile(
    r"^(thanks|thank you|best|sincerely|warmly|regards|kind regards|cheers|"
    r"all the best|respectfully|yours|with thanks|in gratitude)\b.{0,46}$",
    re.I,
)

# Emails often open with the recipient's bare name on its own line.
BARE_GREETING = re.compile(r"^[A-Z][a-z]+( [A-Z][a-z]+)?\s*[,:]\s*$")
SEPARATOR = re.compile(r"^_{5,}$")
SECTION = re.compile(r"^Candidates (for|who)\b", re.I)
# Two candidates wrote twice, and those are headed "First reply, received ...".
RECEIVED = re.compile(
    r"^(?:(?:first|second|third|fourth)\s+reply,\s*)?received\s+(.+)$", re.I
)

# The questionnaire spells David Brun "David Braun". The municipalities' lists
# are authoritative for how a name is written, so map it rather than publish
# someone under a name their own city does not use.
ALIASES = {"David Braun": "David Brun"}


def _strip_email_furniture(lines: list[str], name: str) -> list[str]:
    """Drop the greeting and everything from the sign-off onwards."""
    out = list(lines)
    while out and (
        not out[0].strip()
        or GREETING.match(out[0].strip())
        or BARE_GREETING.match(out[0].strip())
    ):
        out.pop(0)
    # Search from the end, and only in the closing half. "Thanks for your email
    # re co-existing with bears" is how Don Bell *opens*; cutting at the first
    # match threw his whole answer away.
    for i in range(len(out) - 1, max(0, len(out) // 2) - 1, -1):
        if SIGNOFF.match(out[i].strip()):
            out = out[:i]
            break
    # A trailing name/title/URL/phone block with no sign-off line above it.
    tail_junk = re.compile(
        rf"^({re.escape(name)}|{re.escape(name.split()[0])}|.*\b(candidate|councillor|mayor|trustee)\b.*|"
        r"https?://\S+|[\w.-]+@[\w.-]+|[\d\-\(\) \.]{7,}.*|www\.\S+)$",
        re.I,
    )
    while out and (not out[-1].strip() or tail_junk.match(out[-1].strip())):
        out.pop()
    return out


def parse(muni: str, names: dict[str, str]) -> tuple[list[dict], list[str]]:
    raw = (RAW / f"{muni}.txt").read_text(encoding="utf-8-sig")
    # Normalise once and derive the lines from the same string, so "is this a
    # literal slice" is a question about one piece of text rather than two. The
    # export uses CRLF, which silently defeated the check.
    text = "\n".join(l.rstrip() for l in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    lines = text.split("\n")

    def resolve(line: str) -> str | None:
        n = ALIASES.get(line.strip(), line.strip())
        return n if n in names else None

    def is_header(k: int) -> str | None:
        """A candidate name on its own line, with a reply header under it."""
        n = resolve(lines[k])
        if n and k + 1 < len(lines) and RECEIVED.match(lines[k + 1].strip()):
            return n
        return None

    answers: list[dict] = []
    i = 0
    while i < len(lines):
        name = is_header(i)
        if not name:
            i += 1
            continue
        received = RECEIVED.match(lines[i + 1].strip()).group(1)
        segments: list[list[str]] = [[]]
        j = i + 2
        while j < len(lines):
            s_ = lines[j].strip()
            if is_header(j) or SECTION.match(s_):
                break
            if SEPARATOR.match(s_):
                j += 1
                continue
            # A second reply from the same candidate starts a new segment.
            if RECEIVED.match(s_):
                segments.append([])
                j += 1
                continue
            segments[-1].append(lines[j])
            j += 1

        parts = []
        for seg in segments:
            cleaned = _strip_email_furniture(seg, name)
            body = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned).strip())
            if body:
                parts.append(body)
        answer = "\n\n".join(parts)
        if answer:
            for para in answer.split("\n\n"):
                assert para.strip() in text, f"{name}: {para[:40]!r} is not a literal slice"
            answers.append(
                {
                    "candidate_id": names[name],
                    "name": name,
                    "received": received,
                    "replies": len(parts),
                    "answer": answer,
                }
            )
        i = j

    nonresponders: list[str] = []
    start = next((k for k, l in enumerate(lines) if "did not respond" in l.lower()), None)
    if start is not None:
        for l in lines[start:]:
            n = resolve(l.strip().lstrip("*").strip())
            if n and n not in nonresponders:
                nonresponders.append(n)
    return answers, nonresponders


def main() -> int:
    cands = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    out = {"source": DOC_URLS, "municipalities": {}}
    for muni in ("cnv", "dnv"):
        names = {
            c["name"]: c["id"]
            for c in cands
            if c["municipality"] == muni and c["office"] in ("mayor", "council")
        }
        answers, nonresponders = parse(muni, names)
        out["municipalities"][muni] = {
            "answers": answers,
            "nonresponders": [{"name": n, "candidate_id": names[n]} for n in nonresponders],
            "asked": len(names),
        }
        print(f"{muni}: {len(answers)} answered, {len(nonresponders)} did not, of {len(names)} asked")
    payload = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    OUT.write_text(payload, encoding="utf-8")
    site = ROOT / "site" / "src" / "data" / "bears.json"
    site.write_text(payload, encoding="utf-8")
    print(f"-> {OUT.relative_to(ROOT)} and {site.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
