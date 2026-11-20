# Promises and votes: the monthly routine

`/promises-and-votes/` puts each council member's campaign quotes next to how
they have voted since the new councils took office on 2026-11-02. Nothing on
it publishes until a person has approved it in `data/vote-review.yaml`.

Expect 20–30 minutes a month: the City and District together vote on roughly
15–30 items a month, and most are routine.

## 1. Fetch and draft (2 minutes, about 2 cents)

```bash
bash deploy/refresh-votes.sh
```

This:

1. **District**: downloads the District's Council voting decisions table
   (`pipeline.fetch_dnv_votes` → `data/dnv_votes.json`). It keeps only rows
   on or after `term_start` where every member named is on the new council.
   Rows naming anyone else are "held back" and printed. The District has
   carried the old member list on a new-term row before (2026-11-09).
2. **City**: reads the City's council minutes PDFs
   (`pipeline.fetch_cnv_minutes` → `data/cnv_votes.json`). The City publishes
   no vote table, so each vote is read from the minutes: present and not
   named as opposed = for, named as opposed = against, absent or out of the
   room = absent. Anything uncertain is listed under `needs_check`.
3. **Drafts**: for each new vote, `pipeline.draft_vote_matches` asks Claude
   (`claude-opus-5-5`) for up to two issue matches and a one-sentence summary,
   and appends a `pending` entry to `data/vote-review.yaml`. Drafts are
   cached in `data/vote-matching-cache.json`, so a re-run costs nothing.
   `--no-ai` drafts from the District's categories alone.

## 2. Review (the 20–30 minutes)

Open `data/vote-review.yaml`. For each `pending` entry:

- Read `title` and `official_text`. For City entries, `minutes` opens the
  exact page of the minutes.
- **`summary`**: one plain, neutral sentence about what the motion did. It
  publishes labelled "Our summary". No adjectives about the item, no names,
  nothing about who voted which way. The build refuses a summary that names
  a council member.
- **`issues`**: the issue ids it belongs under, or `[]`. Matching is a
  judgement: when unsure, leave it out. A vote with `[]` still appears in the
  member's "Every vote this term" list.
- **City only, `votes`**: each member's vote as read from the minutes. If
  `needs_check` lists anything (a late arrival, someone leaving mid-item, an
  amendment or a motion voted in parts, a count that doesn't fit the result),
  check the minutes, correct `votes`, and set `checked_against_minutes: true`.
  The build refuses a flagged entry without it.
- Set **`status: approved`**. Leave anything you're not sure about as
  `pending`; the page says how many are waiting.

Purely procedural motions (agenda, minutes, adjourning, the consent-agenda
block) and closed-session items never reach this file.

## 3. Publish

```bash
.venv/bin/python -m pipeline.build_votes   # checks every approved entry
cd site && npm run dev                      # look at /promises-and-votes/
cd .. && bash deploy/deploy.sh              # deploy runs build_votes again
git add -A && git commit -m "Votes: <month>" && git push
```

## Corrections

If a reader reports a wrong vote, match or summary, fix the entry in
`data/vote-review.yaml` (or set it back to `pending`), rebuild and deploy.
A correction to a City vote reading belongs in that entry's `votes`.

## Known limits

- City votes are inferred from minutes, not a roll call. The site says so on
  every page that shows one (`CityVotesNote.astro`).
- City minutes are final only once council adopts them at a later meeting.
  Votes from unadopted minutes are labelled. `fetch_cnv_minutes` re-reads
  unadopted minutes on every run, in case they changed.
- The City parser was tested on all 23 sets of 2026 minutes from before the
  election: every numbered resolution is either read as a vote, listed as
  procedural, or listed as a numbered item with no separate public vote.
  A new layout from the City would show up as a "held back" meeting or as
  `needs_check` entries, not as silently wrong votes.
