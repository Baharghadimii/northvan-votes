# North Van Votes

An independent, non-partisan voter guide for the **October 17, 2026** general
local election in the City and District of North Vancouver.

Existing guides are candidate-first: pick a name, then read. This one is
issue-first — pick a topic, see what all 59 candidates have said about it, in
their own words, with a link to the source.

## The rule the whole thing is built around

**The tagger selects text. It never writes text.**

Each candidate statement is split into numbered sentences. The language model is
shown those numbered sentences and replies with *sentence numbers*. Python then
slices those exact characters out of the stored source document.

A paraphrase or invented quote isn't something this pipeline tries to detect —
it's something the pipeline cannot produce. Every span is additionally
re-verified against its source at build time (`Position.verify_against`), and
anything that doesn't match character-for-character is dropped.

## Layout

```
config/categories.yaml   issue taxonomy + named local flashpoints
config/rosters.yaml      seated 2022-2026 members, per municipality
pipeline/                scrape -> tag -> build, all cached and reproducible
data/raw/                every byte we fetched, committed so runs are auditable
data/candidates.json     the canonical dataset
site/                    Astro static site (one React island, for Compare)
```

## Running it

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env        # add ANTHROPIC_API_KEY

.venv/bin/python -m pipeline.build_dataset    # scrape + assert + emit
.venv/bin/python -m pipeline.tag_positions    # Claude pass (or --keywords)
.venv/bin/python -m pipeline.build_dataset    # merge positions

cd site && npm install && npm run dev
```

`build_dataset` fails rather than warns on: a changed candidate count, a
duplicate id, an unknown category, a positions file referencing someone who
isn't running, or any quote that is not exactly the span it cites.

## Two traps worth knowing about

Both of these produce *wrong data*, not a crash:

- **The City's statement marker is split by an inline `<span>`** —
  `Candidate <span>Statement</span>` collapses to `CandidateStatement`. Matching
  on the rendered spacing silently drops 7 statements.
- **Every District candidate carries `isVisible: false`.** In that CMS it's the
  accordion's collapsed state, not a publication flag. Filtering on it silently
  drops the entire District field, and the scrape still "succeeds".

## Scraping conduct

`robots.txt` respected, identifying User-Agent with a contact address, one
request per second, everything cached to `data/raw/` so re-runs never touch a
volunteer's campaign site twice. **nsnews.com is Cloudflare-blocked to automated
access and is never scraped** — link to their coverage, don't ingest it.

## Not built yet

Release 2: four years of council minutes (~250 PDFs, confirmed machine-readable
and directly fetchable from both municipalities) to rank issues by what council
actually spent its time on, and to show incumbents' **explicitly recorded**
dissent. See the plan for the name-collision hazard — `BACK` and `BELL` each
name a different real person in each municipality.
