"""Assemble the published dataset, refusing to emit anything unverified.

Assertions here are the difference between "the scrape changed" and "the site
quietly published something false about a real person", so they fail the build
rather than warn.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from pipeline.models import Candidate, Position, Source
from pipeline.scrape_cnv import scrape as scrape_cnv
from pipeline.scrape_dnv import scrape as scrape_dnv

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "candidates.json"
POSITIONS = ROOT / "data" / "positions.json"
BACKGROUND = ROOT / "data" / "background.json"
CAMPAIGN = ROOT / "data" / "campaign_pages.json"
EXTRA_SITES = ROOT / "config" / "extra-websites.yaml"
# The site imports this copy at build time; data/candidates.json stays the
# canonical, reviewable artefact.
SITE_DATA = ROOT / "site" / "src" / "data" / "candidates.json"
SITE_TAXONOMY = ROOT / "site" / "src" / "data" / "taxonomy.json"
PHOTOS = ROOT / "data" / "photos.json"

# Field as it stood at the close of nominations, Sept 11 2026.
EXPECTED_COUNTS = {
    ("cnv", "mayor"): 4,
    ("cnv", "council"): 18,
    ("cnv", "trustee"): 6,
    ("dnv", "mayor"): 5,
    ("dnv", "council"): 15,
    ("dnv", "trustee"): 11,
}
EXPECTED_INCUMBENTS = {"cnv": 7, "dnv": 7}


class BuildError(RuntimeError):
    pass


def check_counts(candidates: list[Candidate]) -> None:
    actual: dict[tuple[str, str], int] = {}
    for c in candidates:
        actual[(c.municipality, c.office)] = actual.get((c.municipality, c.office), 0) + 1
    if actual != EXPECTED_COUNTS:
        raise BuildError(
            "candidate counts changed.\n"
            f"  expected {EXPECTED_COUNTS}\n  actual   {actual}\n"
            "If a candidate genuinely withdrew, update EXPECTED_COUNTS and say so "
            "on /methodology. Do not relax this check to make a scrape pass."
        )


def check_ids_unique(candidates: list[Candidate]) -> None:
    seen: dict[str, str] = {}
    for c in candidates:
        if c.id in seen:
            raise BuildError(f"duplicate candidate id {c.id!r}: {seen[c.id]} and {c.name}")
        seen[c.id] = c.name


def check_positions(candidates: list[Candidate]) -> None:
    """Every quote must be exactly the span it cites. The core invariant."""
    for c in candidates:
        for p in list(c.positions) + list(c.background):
            source = c.source_for(p.source_url)
            if source is None:
                raise BuildError(f"{c.id}: position cites {p.source_url!r}, not among its sources")
            if not p.verify_against(source.text):
                raise BuildError(
                    f"{c.id}: quote does not match source span "
                    f"[{p.char_start}:{p.char_end}] of {p.source_url}"
                )


def review_flags(candidates: list[Candidate]) -> list[str]:
    """A candidate with a statement but no positions looks identical on the site
    to one who said nothing. Surface it rather than publishing it quietly."""
    return [
        f"{c.id} ({c.name}) has a statement but nothing tagged at all"
        for c in candidates
        if c.has_statement and not c.positions and not c.background
    ]


def attach_extra_websites(candidates: list[Candidate]) -> None:
    """Fill in campaign sites the municipalities did not publish.

    Readers were telling me candidates had websites that the site showed as
    having none, and they were right: the District lists a link for only some
    candidates.
    """
    if not EXTRA_SITES.exists():
        return
    import yaml

    entries = yaml.safe_load(EXTRA_SITES.read_text(encoding="utf-8")) or []
    by_name = {c.name: c for c in candidates}
    for e in entries:
        c = by_name.get(e["name"])
        if c is None:
            raise BuildError(f"config/extra-websites.yaml names an unknown candidate: {e['name']}")
        if not c.website:
            c.website = e["url"]


def attach_campaign_pages(candidates: list[Candidate]) -> None:
    """Add crawled campaign pages as additional sources.

    Self-reported, exactly like the filed statement, and labelled as such
    wherever a quote from one appears. Attached before tagging so positions and
    background can be drawn from either.
    """
    if not CAMPAIGN.exists():
        return
    pages = json.loads(CAMPAIGN.read_text(encoding="utf-8"))
    by_id = {c.id: c for c in candidates}
    unknown = sorted(set(pages) - set(by_id))
    if unknown:
        raise BuildError(f"data/campaign_pages.json has unknown ids: {unknown}")
    for cid, raw in pages.items():
        have = {s.url for s in by_id[cid].sources}
        for entry in raw:
            if entry["url"] not in have:
                by_id[cid].sources.append(Source(**entry))


# A candidate's own site repeats its pitch across pages, so the same sentence
# is legitimately extracted several times. Left alone that produced 124 passages
# for one candidate, 16% of them identical — a page nobody would read.
# A passage longer than this stops being a quotation and becomes a page dump;
# the worst was 5,102 characters. Trimmed at a sentence boundary so the span
# stays a literal slice of the source.
MAX_QUOTE_CHARS = 700
MAX_PER_CATEGORY = 2
MAX_PER_BACKGROUND_KIND = 2


def _trim(p: Position, source_text: str) -> Position:
    """Shorten an over-long passage at a sentence boundary, keeping it exact."""
    if len(p.quote) <= MAX_QUOTE_CHARS:
        return p
    window = p.quote[:MAX_QUOTE_CHARS]
    cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if cut < MAX_QUOTE_CHARS // 3:
        cut = window.rfind(" ")           # no sentence break: fall back to a word
    if cut <= 0:
        return p
    end = cut + 1
    p.quote = p.quote[:end].rstrip()
    p.char_end = p.char_start + len(p.quote)
    # The slice must still match the source exactly, or it does not ship.
    if not p.verify_against(source_text):
        raise BuildError(f"trimming broke the span for {p.source_url}")
    return p


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z']+", text.lower()))


def _overlaps(a: Position, b: Position) -> bool:
    """True when one passage is substantially the other.

    Campaign sites repeat a paragraph with a different lead-in, so two
    extractions can share most of their words while differing in the first
    sixty characters. Comparing openings missed 142 such pairs.
    """
    wa, wb = _words(a.quote), _words(b.quote)
    if not wa or not wb:
        return False
    small, big = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    return len(small & big) / len(small) > 0.7


def _rank(p: Position) -> tuple:
    """Best passage first: the filed statement outranks a campaign page, then
    longer passages, which tend to be the substantive ones rather than a
    banner slogan."""
    return (0 if p.source_type == "official_statement" else 1, -len(p.quote))


def _prune(items: list[Position], cap: int) -> list[Position]:
    seen_exact: set[str] = set()
    seen_open: set[str] = set()
    per_category: dict[str, int] = {}
    kept: list[Position] = []

    for p in sorted(items, key=_rank):
        norm = " ".join(p.quote.split()).lower()
        opening = norm[:60]
        if norm in seen_exact or opening in seen_open:
            continue
        if per_category.get(p.category, 0) >= cap:
            continue
        if any(_overlaps(p, k) for k in kept):
            continue
        seen_exact.add(norm)
        seen_open.add(opening)
        per_category[p.category] = per_category.get(p.category, 0) + 1
        kept.append(p)

    # Back to taxonomy order so the page reads consistently.
    order = {c: i for i, c in enumerate(dict.fromkeys(x.category for x in items))}
    kept.sort(key=lambda p: (order.get(p.category, 99), _rank(p)))
    return kept


def prune_duplicates(candidates: list[Candidate]) -> tuple[int, int]:
    before = sum(len(c.positions) + len(c.background) for c in candidates)
    for c in candidates:
        for p in list(c.positions) + list(c.background):
            source = c.source_for(p.source_url)
            if source:
                _trim(p, source.text)
        c.positions = _prune(c.positions, MAX_PER_CATEGORY)
        c.background = _prune(c.background, MAX_PER_BACKGROUND_KIND)
    after = sum(len(c.positions) + len(c.background) for c in candidates)
    return before, after


def attach_photos(candidates: list[Candidate]) -> None:
    """Point photos at our own origin.

    Left hotlinked, every visitor's browser would fetch images from cnv.org and
    images.dnv.org — a third-party request we cannot make promises about on a
    site that tells readers it tracks nobody — and the pictures would disappear
    whenever either municipality tidies its media library after the election.
    """
    if not PHOTOS.exists():
        return
    local = json.loads(PHOTOS.read_text(encoding="utf-8"))
    for c in candidates:
        if c.id in local:
            c.photo_url = local[c.id]


def attach_positions(candidates: list[Candidate]) -> None:
    """Merge tagger output, if it has been run. Unknown ids are a hard error:
    a stale positions file must not silently attach a quote to nobody."""
    if not POSITIONS.exists():
        return
    tagged = json.loads(POSITIONS.read_text(encoding="utf-8"))
    by_id = {c.id: c for c in candidates}
    unknown = sorted(set(tagged) - set(by_id))
    if unknown:
        raise BuildError(
            f"data/positions.json references unknown candidate ids: {unknown}. "
            "Re-run pipeline.tag_positions against the current field."
        )
    for cid, raw in tagged.items():
        by_id[cid].positions = [Position(**p) for p in raw]

    if not BACKGROUND.exists():
        return
    bg = json.loads(BACKGROUND.read_text(encoding="utf-8"))
    unknown_bg = sorted(set(bg) - set(by_id))
    if unknown_bg:
        raise BuildError(
            f"data/background.json references unknown candidate ids: {unknown_bg}."
        )
    for cid, raw in bg.items():
        by_id[cid].background = [Position(**p) for p in raw]


def build(refresh: bool = False) -> list[Candidate]:
    candidates = scrape_cnv(refresh=refresh) + scrape_dnv(refresh=refresh)
    attach_extra_websites(candidates)
    attach_campaign_pages(candidates)
    attach_positions(candidates)
    prune_duplicates(candidates)
    attach_photos(candidates)
    candidates.sort(key=lambda c: (c.municipality, c.office, c.surname, c.name))
    check_counts(candidates)
    check_ids_unique(candidates)
    check_positions(candidates)
    return candidates


def write(candidates: list[Candidate]) -> None:
    payload = [json.loads(c.model_dump_json()) for c in candidates]
    blob = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    for target in (OUT, SITE_DATA):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(blob, encoding="utf-8")


def write_taxonomy() -> None:
    """Publish the taxonomy the site renders labels from, so page copy and the
    tagger can never drift apart."""
    import yaml

    data = yaml.safe_load((ROOT / "config" / "categories.yaml").read_text(encoding="utf-8"))
    payload = {
        "categories": [
            {
                "id": c["id"],
                "label": c["label"],
                "description": " ".join(str(c.get("description", "")).split()),
                "hue": c.get("hue", 172),
            }
            for c in data["categories"]
        ],
        "background": [
            {
                "id": b["id"],
                "label": b["label"],
                "description": " ".join(str(b.get("description", "")).split()),
            }
            for b in data.get("background", [])
        ],
        "flashpoints": [
            {
                "id": f["id"],
                "label": f["label"],
                "description": " ".join(str(f.get("description", "")).split()),
            }
            for f in data.get("flashpoints", [])
        ],
    }
    SITE_TAXONOMY.parent.mkdir(parents=True, exist_ok=True)
    SITE_TAXONOMY.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def check_categories_known(candidates: list[Candidate]) -> None:
    """A position tagged with a category the site has no label for would render
    as a blank heading. Fail instead."""
    import yaml

    data = yaml.safe_load((ROOT / "config" / "categories.yaml").read_text(encoding="utf-8"))
    known = {c["id"] for c in data["categories"]}
    known |= {b["id"] for b in data.get("background", [])}
    seen = {p.category for c in candidates for p in list(c.positions) + list(c.background)}
    unknown = sorted(seen - known)
    if unknown:
        raise BuildError(f"positions use unknown categories: {unknown}")


def main() -> int:
    refresh = "--refresh" in sys.argv
    candidates = build(refresh=refresh)
    check_categories_known(candidates)
    write(candidates)
    write_taxonomy()

    print(f"{len(candidates)} candidates -> {OUT.relative_to(ROOT)}")
    for muni in ("cnv", "dnv"):
        group = [c for c in candidates if c.municipality == muni]
        inc = sum(1 for c in group if c.incumbent)
        if inc != EXPECTED_INCUMBENTS[muni]:
            raise BuildError(
                f"{muni}: {inc} incumbents flagged, expected {EXPECTED_INCUMBENTS[muni]}. "
                "Check config/rosters.yaml against the seated council."
            )
        print(
            f"  {muni}: {len(group):2} candidates, "
            f"{sum(1 for c in group if c.has_statement):2} statements, "
            f"{sum(1 for c in group if c.website):2} websites, "
            f"{sum(len(c.sources) for c in group):3} sources, "
            f"{inc} incumbents, "
            f"{sum(len(c.positions) for c in group)} positions, "
            f"{sum(len(c.background) for c in group)} background"
        )

    flags = review_flags(candidates)
    if flags:
        print(f"\nreview flags ({len(flags)}):")
        for f in flags[:5]:
            print(f"  - {f}")
        if len(flags) > 5:
            print(f"  ... and {len(flags) - 5} more (expected until tag_positions runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
