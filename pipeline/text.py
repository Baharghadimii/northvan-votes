"""Sentence segmentation that keeps character offsets.

Offsets are the whole point: the tagger picks sentences by id and this module is
what turns those ids back into an exact slice of the source, so a published
quote cannot drift from what the candidate actually wrote.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Abbreviations that should not end a sentence.
_ABBREV = r"(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)(?<!\bSt)(?<!\bJr)(?<!\bSr)(?<!\bNo)(?<!\bvs)(?<!\bapprox)"
_BOUNDARY = re.compile(rf"{_ABBREV}(?<=[.!?])[\"')\]]*\s+(?=[A-Z0-9\"'(\[])|\n{{2,}}")


@dataclass(frozen=True)
class Sentence:
    id: int
    start: int
    end: int
    text: str


def split_sentences(text: str, min_chars: int = 25) -> list[Sentence]:
    """Split into sentences, each carrying its span in the original string.

    Fragments shorter than `min_chars` are folded into the previous sentence
    rather than dropped, so the offsets always tile the whole text.
    """
    if not text.strip():
        return []

    cuts: list[int] = [0]
    for m in _BOUNDARY.finditer(text):
        cuts.append(m.end())
    cuts.append(len(text))

    raw: list[tuple[int, int]] = []
    for i in range(len(cuts) - 1):
        start, end = cuts[i], cuts[i + 1]
        # Trim trailing whitespace from the span so quotes don't end in blanks.
        while end > start and text[end - 1].isspace():
            end -= 1
        while start < end and text[start].isspace():
            start += 1
        if start < end:
            raw.append((start, end))

    merged: list[tuple[int, int]] = []
    for start, end in raw:
        if merged and (end - start) < min_chars:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))

    return [Sentence(i, s, e, text[s:e]) for i, (s, e) in enumerate(merged)]


def span_of(sentences: list[Sentence], ids: list[int]) -> tuple[int, int]:
    """Char span covering a run of sentence ids (inclusive of any gap between)."""
    chosen = [s for s in sentences if s.id in set(ids)]
    if not chosen:
        raise ValueError("no sentences matched those ids")
    return min(s.start for s in chosen), max(s.end for s in chosen)


def runs(ids: list[int]) -> list[list[int]]:
    """Group sorted ids into consecutive runs: [1,2,4,7,8] -> [[1,2],[4],[7,8]]."""
    out: list[list[int]] = []
    for i in sorted(set(ids)):
        if out and i == out[-1][-1] + 1:
            out[-1].append(i)
        else:
            out.append([i])
    return out


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))
