#!/usr/bin/env bash
# Monthly "Promises and votes" refresh. Fetches both councils' new votes and
# drafts matches for review. It publishes nothing: see VOTES.md.
#
#   bash deploy/refresh-votes.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> District: vote table"
.venv/bin/python -m pipeline.fetch_dnv_votes
echo "==> City: minutes"
.venv/bin/python -m pipeline.fetch_cnv_minutes
echo "==> Drafting matches and summaries for anything new"
.venv/bin/python -m pipeline.draft_vote_matches
echo
echo "Next: review data/vote-review.yaml (see VOTES.md), then"
echo "  .venv/bin/python -m pipeline.build_votes"
