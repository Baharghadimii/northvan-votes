"""Tag candidate statements with issue positions.

The tagger selects text; it never writes text.

Concretely: the model is shown numbered sentences and returns sentence *ids*.
This module turns those ids back into character spans and slices the quote out
of the source itself. The model has no channel through which to emit prose, so a
published quote cannot be a paraphrase, a summary, or a hallucination -- the
worst it can do is pick the wrong sentence, which review catches.

Usage:
    python -m pipeline.tag_positions            # Claude pass (needs credentials)
    python -m pipeline.tag_positions --keywords # deterministic fallback, no API
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from pipeline.models import Position
from pipeline.text import Sentence, runs, split_sentences, word_count

ROOT = Path(__file__).resolve().parent.parent
CATEGORIES_FILE = ROOT / "config" / "categories.yaml"
CANDIDATES_FILE = ROOT / "data" / "candidates.json"
OUT = ROOT / "data" / "positions.json"
OUT_BG = ROOT / "data" / "background.json"

MODEL = "claude-opus-5"
MIN_WORDS = 15  # a span shorter than this is a fragment, not a position


# --------------------------------------------------------------------------- #
# taxonomy
# --------------------------------------------------------------------------- #

def load_taxonomy() -> tuple[list[dict], list[dict]]:
    data = yaml.safe_load(CATEGORIES_FILE.read_text(encoding="utf-8"))
    return data["categories"], data.get("flashpoints", [])


def load_background() -> list[dict]:
    data = yaml.safe_load(CATEGORIES_FILE.read_text(encoding="utf-8"))
    return data.get("background", [])


def background_ids() -> list[str]:
    return [b["id"] for b in load_background()]


def category_ids() -> list[str]:
    cats, _ = load_taxonomy()
    return [c["id"] for c in cats]


def flashpoints_in(text: str) -> list[str]:
    """Exact-phrase flashpoint tags. Precision over recall by design."""
    _, flash = load_taxonomy()
    low = text.lower()
    return [f["id"] for f in flash if any(p.lower() in low for p in f["phrases"])]


# --------------------------------------------------------------------------- #
# span assembly -- shared by both paths
# --------------------------------------------------------------------------- #

def _positions_from_ids(
    source_text: str,
    source_url: str,
    source_type: str,
    sentences: list[Sentence],
    category: str,
    ids: list[int],
) -> list[Position]:
    """Turn sentence ids into validated, verbatim Positions."""
    valid = {s.id for s in sentences}
    ids = [i for i in ids if i in valid]
    out: list[Position] = []

    for run in runs(ids):
        chosen = [s for s in sentences if s.id in set(run)]
        start = min(s.start for s in chosen)
        end = max(s.end for s in chosen)
        quote = source_text[start:end]

        if word_count(quote) < MIN_WORDS:
            continue

        position = Position(
            category=category,
            flashpoints=flashpoints_in(quote),
            quote=quote,
            source_url=source_url,
            source_type=source_type,  # type: ignore[arg-type]
            char_start=start,
            char_end=end,
        )
        # Belt and braces: the span must round-trip before it can be published.
        if not position.verify_against(source_text):
            continue
        out.append(position)

    return out


# --------------------------------------------------------------------------- #
# deterministic path (no API key)
# --------------------------------------------------------------------------- #

def keyword_hits(sentence: str, keywords: list[str]) -> int:
    low = sentence.lower()
    return sum(1 for k in keywords if k in low)


def tag_by_keywords(source: dict) -> list[Position]:
    cats, _ = load_taxonomy()
    text = source["text"]
    sentences = split_sentences(text)
    out: list[Position] = []

    for cat in cats:
        multiword = [k for k in cat["keywords"] if " " in k]
        ids = [
            s.id
            for s in sentences
            # Two distinct keywords, or one multi-word phrase. A single common
            # word ("safety", "business") is too weak to publish on.
            if keyword_hits(s.text, cat["keywords"]) >= 2
            or keyword_hits(s.text, multiword) >= 1
        ]
        out.extend(
            _positions_from_ids(
                text, source["url"], source["type"], sentences, cat["id"], ids
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Claude path
# --------------------------------------------------------------------------- #

class Assignment(BaseModel):
    category: str = Field(description="One category id from the taxonomy.")
    sentence_ids: list[int] = Field(
        description="Ids of the sentences that state this candidate's position on the category."
    )


class Assignments(BaseModel):
    assignments: list[Assignment]


def _background_prompt() -> str:
    """Prompt for the biography pass.

    Kept separate from the issues pass because the judgement is different:
    here we want what someone has done, not what they promise to do.
    """
    kinds = load_background()
    lines = [
        "You are pulling out biographical background from a candidate's "
        "election statement, so voters can see who someone is and what they "
        "have actually done before asking for their vote.",
        "",
        "You will be given the statement split into numbered sentences. For "
        "each kind of background below, return the ids of sentences that "
        "describe it.",
        "",
        "Rules:",
        "- Return sentence ids only. Never write, summarise or paraphrase text.",
        "- Facts about the person, not promises about the future. 'I will "
        "push for better transit' is a position, not background. 'I chaired "
        "the transportation committee' is background.",
        "- Slogans, values and appeals for votes are not background.",
        "- A sentence may fit more than one kind, or none.",
        "- Prefer consecutive sentences when the thought runs across them.",
        "- Omit a kind entirely rather than stretching to fill it.",
        "",
        "Kinds of background:",
    ]
    for k in kinds:
        desc = " ".join(str(k.get("description", "")).split())
        lines.append(f"- {k['id']}: {k['label']} -- {desc}")
    return "\n".join(lines)


def _system_prompt() -> str:
    cats, _ = load_taxonomy()
    lines = [
        "You are tagging statements by candidates in a municipal election so that "
        "voters can browse by issue. The result is published verbatim beside each "
        "candidate's name, so accuracy matters more than coverage.",
        "",
        "You will be given a candidate's statement split into numbered sentences.",
        "For each issue category below, return the ids of sentences that state "
        "that candidate's position, priority, or commitment on it.",
        "",
        "Rules:",
        "- Return sentence ids only. Never write, summarise, or paraphrase text.",
        "- Include a sentence only if it says something substantive about the "
        "category. Biography, credentials, thanks, and slogans are not positions.",
        "- A sentence may belong to more than one category, or to none.",
        "- Prefer a run of consecutive sentences when the thought spans them, so "
        "the published quote reads as the candidate wrote it.",
        "- Omit a category entirely rather than stretching to fill it. Most "
        "candidates address only a few.",
        "",
        "Categories:",
    ]
    for c in cats:
        desc = " ".join(str(c.get("description", "")).split())
        lines.append(f"- {c['id']}: {c['label']} -- {desc}")
    return "\n".join(lines)


def _claude_pass(source: dict, client, system: str, allowed: set[str]) -> list[Position]:
    text = source["text"]
    sentences = split_sentences(text)
    if not sentences:
        return []

    numbered = "\n".join(f"[{s.id}] {s.text}" for s in sentences)
    valid_ids = {s.id for s in sentences}

    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": f"Statement sentences:\n\n{numbered}"}],
        output_format=Assignments,
    )

    out: list[Position] = []
    for a in response.parsed_output.assignments:
        if a.category not in allowed:
            continue  # model invented a label; drop rather than publish it
        ids = [i for i in a.sentence_ids if i in valid_ids]
        out.extend(
            _positions_from_ids(
                text, source["url"], source["type"], sentences, a.category, ids
            )
        )
    return out


def tag_with_claude(source: dict, client) -> list[Position]:
    return _claude_pass(source, client, _system_prompt(), set(category_ids()))


def tag_background_with_claude(source: dict, client) -> list[Position]:
    return _claude_pass(source, client, _background_prompt(), set(background_ids()))


def tag_background_by_keywords(source: dict) -> list[Position]:
    kinds = load_background()
    text = source["text"]
    sentences = split_sentences(text)
    out: list[Position] = []
    for kind in kinds:
        multiword = [k for k in kind["keywords"] if " " in k]
        ids = [
            s.id for s in sentences
            if keyword_hits(s.text, kind["keywords"]) >= 2
            or keyword_hits(s.text, multiword) >= 1
        ]
        out.extend(
            _positions_from_ids(
                text, source["url"], source["type"], sentences, kind["id"], ids
            )
        )
    return out


# --------------------------------------------------------------------------- #

def main() -> int:
    use_keywords = "--keywords" in sys.argv
    candidates = json.loads(CANDIDATES_FILE.read_text(encoding="utf-8"))

    client = None
    if not use_keywords:
        try:
            import anthropic

            client = anthropic.Anthropic()
        except Exception as exc:  # noqa: BLE001
            print(f"could not create an Anthropic client: {exc}", file=sys.stderr)
            print("run with --keywords for the deterministic fallback", file=sys.stderr)
            return 1

    result: dict[str, list[dict]] = {}
    background: dict[str, list[dict]] = {}
    for i, cand in enumerate(candidates, 1):
        positions: list[Position] = []
        bg: list[Position] = []
        for source in cand["sources"]:
            if use_keywords:
                positions.extend(tag_by_keywords(source))
                bg.extend(tag_background_by_keywords(source))
            else:
                positions.extend(tag_with_claude(source, client))
                bg.extend(tag_background_with_claude(source, client))
        if positions:
            result[cand["id"]] = [json.loads(p.model_dump_json()) for p in positions]
        if bg:
            background[cand["id"]] = [json.loads(p.model_dump_json()) for p in bg]
        print(
            f"  [{i:2}/{len(candidates)}] {cand['name']:26} "
            f"{len(positions):2} positions  {len(bg):2} background",
            flush=True,
        )

    for path, payload in ((OUT, result), (OUT_BG, background)):
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    mode = "keyword fallback" if use_keywords else MODEL
    print(
        f"\n{sum(len(v) for v in result.values())} positions across "
        f"{len(result)} candidates, and "
        f"{sum(len(v) for v in background.values())} background passages across "
        f"{len(background)} ({mode})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
