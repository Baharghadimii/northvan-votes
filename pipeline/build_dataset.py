"""Assemble the published dataset, refusing to emit anything unverified.

Assertions here are the difference between "the scrape changed" and "the site
quietly published something false about a real person", so they fail the build
rather than warn.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pipeline.models import Candidate
from pipeline.scrape_cnv import scrape as scrape_cnv
from pipeline.scrape_dnv import scrape as scrape_dnv

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "candidates.json"

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


def build(refresh: bool = False) -> list[Candidate]:
    candidates = scrape_cnv(refresh=refresh) + scrape_dnv(refresh=refresh)
    candidates.sort(key=lambda c: (c.municipality, c.office, c.surname, c.name))
    check_counts(candidates)
    check_ids_unique(candidates)
    check_positions(candidates)
    return candidates


def write(candidates: list[Candidate]) -> None:
    payload = [json.loads(c.model_dump_json()) for c in candidates]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    refresh = "--refresh" in sys.argv
    candidates = build(refresh=refresh)
    write(candidates)

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
