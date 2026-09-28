"""Seated-member rosters and strictly-scoped surname resolution."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from pipeline.names import candidate_id, display_name

ROOT = Path(__file__).resolve().parent.parent
ROSTER_FILE = ROOT / "config" / "rosters.yaml"


class AmbiguousMember(RuntimeError):
    """A surname matched zero or several seated members. Never guess past this."""


@dataclass(frozen=True)
class Member:
    surname: str
    given: str
    office: str
    municipality: str

    @property
    def id(self) -> str:
        return candidate_id(self.municipality, self.office, self.surname, self.given)

    @property
    def name(self) -> str:
        return display_name(self.surname, self.given)


@lru_cache(maxsize=1)
def rosters() -> dict[str, list[Member]]:
    raw = yaml.safe_load(ROSTER_FILE.read_text(encoding="utf-8"))
    out: dict[str, list[Member]] = {}
    for muni, block in raw.items():
        out[muni] = [
            Member(
                surname=m["surname"].upper(),
                given=m["given"],
                office=m["office"],
                municipality=muni,
            )
            for m in block["members"]
        ]
    return out


def resolve_surname(municipality: str, surname: str) -> Member:
    """Resolve a surname from minutes against ONE municipality's roster.

    Raises rather than returning a best guess: attributing a recorded vote to
    the wrong person is the worst thing this project could publish.
    """
    candidates = [
        m for m in rosters()[municipality] if m.surname == surname.strip().upper()
    ]
    if len(candidates) == 1:
        return candidates[0]
    known = ", ".join(sorted(m.surname for m in rosters()[municipality]))
    raise AmbiguousMember(
        f"{surname!r} matched {len(candidates)} seated members in {municipality}. "
        f"Roster: {known}. Add the member to config/rosters.yaml after confirming "
        f"from the minutes -- do not loosen the matching."
    )


def is_incumbent(municipality: str, surname: str, given: str) -> bool:
    surname_u = surname.strip().upper()
    given_l = given.strip().lower()
    return any(
        m.surname == surname_u and m.given.lower() == given_l
        for m in rosters().get(municipality, [])
    )
