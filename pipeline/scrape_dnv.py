"""District of North Vancouver candidate profiles.

The District site is a React SPA, so the rendered page has no candidate markup.
Content comes from SimpliCity's public content API, which returns the profiles
as ProseMirror-style rich text -- cleaner and more stable than scraping HTML.

Reader-facing citations point at the human page, not the API.
"""

from __future__ import annotations

import json
from datetime import date

from pipeline.fetching import fetch, retrieved_at
from pipeline.models import Candidate, Source
from pipeline.names import candidate_id, display_name, split_listing
from pipeline.rosters import is_incumbent

PAGE_URL = "https://www.dnv.org/government-administration/see-who-is-running"
API_URL = (
    "https://simplicity-api.dnv.org/public/webpage/path/detailed/"
    "%2Fgovernment-administration%2Fsee-who-is-running"
)

HEADING_OFFICES = {
    "candidates for mayor": "mayor",
    "candidates for councillor": "council",
    "candidates for school trustee": "trustee",
}

SOCIAL_LABELS = {
    "facebook": "facebook",
    "instagram": "instagram",
    "x": "twitter",
    "twitter": "twitter",
    "linkedin": "linkedin",
    "youtube": "youtube",
    "bluesky": "bluesky",
    "threads": "threads",
    "tiktok": "tiktok",
}

CONNECT_HEADING = "connect with this candidate"


def _text(node) -> str:
    """Flatten a rich-text node to its literal text."""
    if isinstance(node, list):
        return "".join(_text(n) for n in node)
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        return "".join(_text(c) for c in node.get("content") or [])
    return ""


def _marks_of(node, kind: str, out: list[tuple[str, dict]]) -> None:
    if isinstance(node, list):
        for n in node:
            _marks_of(n, kind, out)
        return
    if not isinstance(node, dict):
        return
    for m in node.get("marks") or []:
        if m.get("type") == kind:
            out.append((node.get("text", ""), m.get("attrs") or {}))
    for c in node.get("content") or []:
        _marks_of(c, kind, out)


def _has_mark(node, kind: str) -> bool:
    found: list[tuple[str, dict]] = []
    _marks_of(node, kind, found)
    return bool(found)


def _parse_section(section: dict, office: str, retrieved: date) -> Candidate:
    listing = section["title"].strip()
    surname, given = split_listing(listing)
    content = section.get("richtext", {}).get("content") or []

    photo_url: str | None = None
    statement_parts: list[str] = []
    nomination_docs: list[str] = []
    financial_disclosure: list[str] = []
    website: str | None = None
    socials: dict[str, str] = {}

    in_statement = True
    for node in content:
        node_type = node.get("type")

        if node_type == "image":
            photo_url = photo_url or (node.get("attrs") or {}).get("src")
            continue

        if node_type == "heading":
            # "Connect with this candidate" ends the statement and starts links.
            if _text(node).strip().lower() == CONNECT_HEADING:
                in_statement = False
            continue

        # Document links (nomination package, financial disclosure) also end it.
        doclinks: list[tuple[str, dict]] = []
        _marks_of(node, "doclink", doclinks)
        if doclinks:
            in_statement = False
            for label, attrs in doclinks:
                href = attrs.get("href") or attrs.get("url")
                if not href:
                    continue
                target = (
                    financial_disclosure
                    if any(w in label.lower() for w in ("financial", "disclosure"))
                    else nomination_docs
                )
                if href not in target:
                    target.append(href)
            continue

        links: list[tuple[str, dict]] = []
        _marks_of(node, "link", links)
        if links:
            in_statement = False
            for label, attrs in links:
                href = attrs.get("href") or attrs.get("url")
                if not href:
                    continue
                key = SOCIAL_LABELS.get(label.strip().lower())
                if key:
                    socials.setdefault(key, href)
                elif label.strip().lower() == "website" and website is None:
                    website = href
            continue

        if in_statement and node_type in ("paragraph", "bulletList"):
            text = " ".join(_text(node).split())
            if text:
                statement_parts.append(text)

    sources: list[Source] = []
    statement = "\n\n".join(statement_parts)
    if statement:
        sources.append(
            Source(
                type="official_statement",
                url=PAGE_URL,
                title=f"District of North Vancouver candidate statement - {listing}",
                text=statement,
                retrieved=retrieved,
            )
        )

    return Candidate(
        id=candidate_id("dnv", office, surname, given),
        name=display_name(surname, given),
        surname=surname.upper(),
        municipality="dnv",
        office=office,  # type: ignore[arg-type]
        incumbent=is_incumbent("dnv", surname, given),
        photo_url=photo_url,
        website=website,
        socials=socials,
        nomination_docs=nomination_docs,
        financial_disclosure=financial_disclosure,
        sources=sources,
    )


def scrape(refresh: bool = False) -> list[Candidate]:
    payload = json.loads(fetch(API_URL, "candidates", suffix=".json", refresh=refresh))
    blocks = payload["model"]["fields"][0]["values"][0]["value"]
    retrieved = retrieved_at('candidates', API_URL, '.json')

    candidates: list[Candidate] = []
    office: str | None = None

    for block in blocks:
        block_type = block.get("type")
        if block_type == "component.heading":
            office = HEADING_OFFICES.get(str(block.get("value", "")).strip().lower(), office)
            continue
        if block_type != "component.accordion":
            continue
        if office is None:
            raise RuntimeError("accordion appeared before any office heading")
        # NB: sections carry isVisible=False for every candidate -- in this CMS
        # that is the accordion's collapsed state, not a publication flag.
        # Filtering on it silently drops the entire field.
        for section in block.get("sections") or []:
            candidates.append(_parse_section(section, office, retrieved))

    return candidates


if __name__ == "__main__":
    found = scrape()
    print(f"{len(found)} District candidates")
    for office in ("mayor", "council", "trustee"):
        group = [c for c in found if c.office == office]
        print(f"  {office:8} {len(group):2}  statements {sum(1 for c in group if c.has_statement):2}  "
              f"websites {sum(1 for c in group if c.website):2}  "
              f"incumbents {sum(1 for c in group if c.incumbent)}")
