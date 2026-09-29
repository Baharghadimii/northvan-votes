"""Assemble the published dataset, refusing to emit anything unverified.

Assertions here are the difference between "the scrape changed" and "the site
quietly published something false about a real person", so they fail the build
rather than warn.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pipeline.models import Candidate, Position
from pipeline.scrape_cnv import scrape as scrape_cnv
from pipeline.scrape_dnv import scrape as scrape_dnv

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "candidates.json"
POSITIONS = ROOT / "data" / "positions.json"
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
        for p in c.positions:
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
        f"{c.id} ({c.name}) has a statement but zero tagged positions"
        for c in candidates
        if c.has_statement and not c.positions
    ]


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


def build(refresh: bool = False) -> list[Candidate]:
    candidates = scrape_cnv(refresh=refresh) + scrape_dnv(refresh=refresh)
    attach_positions(candidates)
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
    seen = {p.category for c in candidates for p in c.positions}
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
            f"{inc} incumbents, "
            f"{sum(len(c.positions) for c in group)} positions"
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
