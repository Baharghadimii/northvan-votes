"""Name handling.

Minutes refer to members by bare surname (MURI, BACK, POPE) and there are real
collisions across the two municipalities -- BACK, Holly (City) vs BACK, Jordan
(District); BELL, Don (City) vs BELL, Trey (District). Surnames are therefore
kept in their raw uppercase form for matching, and resolution is always scoped
to one municipality's roster. See pipeline/rosters.py.
"""

from __future__ import annotations

import re


def _pretty_token(token: str) -> str:
    low = token.strip().lower()
    if not low:
        return ""
    if "-" in low:
        return "-".join(_pretty_token(p) for p in low.split("-"))
    if low.startswith("mc") and len(low) > 2:
        return "Mc" + low[2:].capitalize()
    if low.startswith("o'") and len(low) > 2:
        return "O'" + low[2:].capitalize()
    return low.capitalize()


def prettify(name: str) -> str:
    """'McILROY' -> 'McIlroy', 'KEN' -> 'Ken', 'Linda' -> 'Linda'."""
    return " ".join(_pretty_token(t) for t in name.split() if t.strip())


def split_listing(listing: str) -> tuple[str, str]:
    """'BUCHANAN, Linda' -> ('BUCHANAN', 'Linda'). Surname kept verbatim."""
    if "," not in listing:
        raise ValueError(f"unexpected name format: {listing!r}")
    surname, given = listing.split(",", 1)
    return surname.strip(), given.strip()


def slug(value: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not out:
        raise ValueError(f"cannot slugify {value!r}")
    return out


def candidate_id(municipality: str, office: str, surname: str, given: str) -> str:
    return f"{municipality}-{office}-{slug(surname)}-{slug(given)}"


def display_name(surname: str, given: str) -> str:
    return f"{prettify(given)} {prettify(surname)}".strip()
