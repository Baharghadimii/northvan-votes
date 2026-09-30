"""Typed records shared by every pipeline stage.

Two invariants are enforced here rather than at the call site, because they are
the two ways this project could publish something untrue about a real person:

  * Position.quote must be a literal slice of the source text it cites.
  * CouncilVote names must come from an explicit dissent line, never inferred.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Municipality = Literal["cnv", "dnv"]
Office = Literal["mayor", "council", "trustee"]
SourceType = Literal["official_statement", "campaign_site"]

OFFICE_LABELS: dict[Office, str] = {
    "mayor": "Mayor",
    "council": "Council",
    "trustee": "School Trustee",
}

MUNICIPALITY_LABELS: dict[Municipality, str] = {
    "cnv": "City of North Vancouver",
    "dnv": "District of North Vancouver",
}

# Seats up for election, used to sanity-check the scrape.
SEATS: dict[tuple[Municipality, Office], int] = {
    ("cnv", "mayor"): 1,
    ("cnv", "council"): 6,
    ("cnv", "trustee"): 3,
    ("dnv", "mayor"): 1,
    ("dnv", "council"): 6,
    ("dnv", "trustee"): 4,
}


class Source(BaseModel):
    """A document we actually retrieved, kept verbatim so spans stay checkable."""

    type: SourceType
    url: str
    title: str | None = None
    text: str
    retrieved: date


class Position(BaseModel):
    """A candidate's stated position: a literal span of one Source."""

    category: str
    # Named local flashpoints this span touches (wastewater plant, amalgamation,
    # ...). Cross-cutting, so a span can carry a category and flashpoints at once.
    flashpoints: list[str] = Field(default_factory=list)
    quote: str
    source_url: str
    source_type: SourceType
    char_start: int
    char_end: int

    @field_validator("quote")
    @classmethod
    def _non_trivial(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("quote must not be empty")
        return v

    def verify_against(self, source_text: str) -> bool:
        """True only if the quote is exactly what the offsets point at."""
        if self.char_start < 0 or self.char_end > len(source_text):
            return False
        if self.char_start >= self.char_end:
            return False
        return source_text[self.char_start : self.char_end] == self.quote


class Candidate(BaseModel):
    id: str
    name: str
    surname: str
    municipality: Municipality
    office: Office
    incumbent: bool = False
    photo_url: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    socials: dict[str, str] = Field(default_factory=dict)
    nomination_docs: list[str] = Field(default_factory=list)
    financial_disclosure: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    positions: list[Position] = Field(default_factory=list)
    # Who they are and what they have done, as opposed to what they would do.
    # Same verbatim-span guarantee; `category` holds a background type id.
    background: list[Position] = Field(default_factory=list)

    @property
    def has_statement(self) -> bool:
        return any(s.type == "official_statement" and s.text.strip() for s in self.sources)

    def source_for(self, url: str) -> Source | None:
        return next((s for s in self.sources if s.url == url), None)


class CouncilItem(BaseModel):
    """One agenda item from one meeting, with any explicitly recorded dissent."""

    municipality: Municipality
    meeting_date: date
    meeting_type: str
    item_no: str | None = None
    title: str
    file_no: str | None = None
    categories: list[str] = Field(default_factory=list)
    outcome: str | None = None
    # Candidate/member ids. Populated ONLY from a literal dissent line.
    opposed: list[str] = Field(default_factory=list)
    opposed_raw: list[str] = Field(default_factory=list)
    source_url: str
    source_page: int
