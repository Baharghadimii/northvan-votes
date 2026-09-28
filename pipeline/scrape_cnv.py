"""City of North Vancouver candidate profiles.

Source: https://www.cnv.org/.../2026-General-Local-Election/Candidate-Profiles

Server markup is a set of `div.mobile-accordion` blocks, one per office. Inside
each, an `<h3>` name is followed by a sibling `div.accordion-item-content`
holding contact details, an optional candidate statement, and a nomination
package link. Office is read from the blue section headings that precede each
block ("Mayor (one to be elected)").
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from pipeline.fetching import fetch, retrieved_at
from pipeline.models import Candidate, Source
from pipeline.names import candidate_id, display_name, split_listing
from pipeline.rosters import is_incumbent

URL = (
    "https://www.cnv.org/City-Hall/General-Local-Election/"
    "2026-General-Local-Election/Candidate-Profiles"
)

OFFICE_HEADINGS = {
    "mayor": "mayor",
    "councillor": "council",
    "school trustee": "trustee",
}

SOCIAL_HOSTS = {
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "linkedin.com": "linkedin",
    "youtube.com": "youtube",
    "bsky.app": "bluesky",
}

NO_PROFILE = re.compile(r"^no profile provided\.?$", re.I)


def _is_statement_marker(tag: Tag) -> bool:
    """True for the "Candidate Statement" heading paragraph.

    Some profiles split it across an inline span -- `Candidate <span>Statement
    </span>` -- so compare with all whitespace removed rather than relying on the
    rendered spacing.
    """
    squashed = re.sub(r"\s+", "", tag.get_text(" ", strip=True)).lower()
    return squashed == "candidatestatement"


def _office_from_heading(text: str) -> str | None:
    lowered = text.strip().lower()
    for key, office in OFFICE_HEADINGS.items():
        if lowered.startswith(key):
            return office
    return None


def _social_key(href: str) -> str | None:
    for host, key in SOCIAL_HOSTS.items():
        if host in href.lower():
            return key
    return None


def _statement_text(body: Tag) -> str:
    """Paragraphs after the 'Candidate Statement' marker, joined verbatim.

    Offsets into this string are what Position spans cite, so the join has to be
    deterministic. Anything that isn't candidate prose (the nomination package
    link, empty spacers) is excluded.
    """
    paragraphs = body.find_all("p")
    marker_index = next(
        (i for i, p in enumerate(paragraphs) if _is_statement_marker(p)),
        None,
    )
    if marker_index is None:
        return ""

    parts: list[str] = []
    for p in paragraphs[marker_index + 1 :]:
        if p.find("a", href=re.compile(r"Nom-Package", re.I)):
            continue
        text = p.get_text(" ", strip=True).replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _parse_body(body: Tag) -> dict:
    out: dict = {
        "photo_url": None,
        "phone": None,
        "email": None,
        "website": None,
        "socials": {},
        "nomination_docs": [],
    }

    img = body.find("img")
    if img and img.get("src"):
        out["photo_url"] = urljoin(URL, img["src"])

    for p in body.find_all("p"):
        label = p.find("strong")
        if not label:
            continue
        key = label.get_text(strip=True).rstrip(":").strip().lower()
        if key == "phone":
            value = p.get_text(" ", strip=True)[len(label.get_text(strip=True)) :]
            out["phone"] = value.strip(": ").strip() or None

    for a in body.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            out["email"] = href[7:].strip() or None
            continue
        if re.search(r"Nom-Package", href, re.I):
            out["nomination_docs"].append(urljoin(URL, href))
            continue
        key = _social_key(href)
        if key:
            out["socials"].setdefault(key, href)
        elif href.startswith("http") and "cnv.org" not in href:
            out.setdefault("website", None)
            if out["website"] is None:
                out["website"] = href

    return out


def scrape(refresh: bool = False) -> list[Candidate]:
    html = fetch(URL, "candidates", refresh=refresh)
    soup = BeautifulSoup(html, "lxml")
    retrieved = retrieved_at('candidates', URL)

    candidates: list[Candidate] = []
    office: str | None = None

    for h3 in soup.find_all("h3"):
        heading_text = h3.get_text(" ", strip=True)
        maybe_office = _office_from_heading(heading_text)
        if maybe_office:
            office = maybe_office
            continue
        if "," not in heading_text:
            continue

        body = h3.find_next_sibling("div", class_="accordion-item-content")
        if body is None:
            raise RuntimeError(f"no accordion body for {heading_text!r}")
        if office is None:
            raise RuntimeError(f"{heading_text!r} appeared before any office heading")

        surname, given = split_listing(heading_text)
        parsed = _parse_body(body)
        statement = _statement_text(body)

        sources: list[Source] = []
        if statement:
            sources.append(
                Source(
                    type="official_statement",
                    url=URL,
                    title=f"City of North Vancouver candidate statement - {heading_text}",
                    text=statement,
                    retrieved=retrieved,
                )
            )

        candidates.append(
            Candidate(
                id=candidate_id("cnv", office, surname, given),
                name=display_name(surname, given),
                surname=surname.upper(),
                municipality="cnv",
                office=office,  # type: ignore[arg-type]
                incumbent=is_incumbent("cnv", surname, given),
                photo_url=parsed["photo_url"],
                email=parsed["email"],
                phone=parsed["phone"],
                website=parsed["website"],
                socials=parsed["socials"],
                nomination_docs=parsed["nomination_docs"],
                sources=sources,
            )
        )

    return candidates


if __name__ == "__main__":
    found = scrape()
    print(f"{len(found)} City candidates")
    for office in ("mayor", "council", "trustee"):
        group = [c for c in found if c.office == office]
        with_stmt = sum(1 for c in group if c.has_statement)
        print(f"  {office:8} {len(group):2}  statements {with_stmt:2}  "
              f"websites {sum(1 for c in group if c.website):2}  "
              f"incumbents {sum(1 for c in group if c.incumbent)}")
