#!/usr/bin/env bash
# Build on the Mac, ship the result to the VPS.
#
#   bash deploy/deploy.sh
#
# The VPS serves files; it never builds. No Node, no npm and no build memory
# needed on a box that is also running the Etsy pipeline.
set -euo pipefail

VPS="${NVV_VPS:-209.250.232.171}"
VPS_USER="${NVV_VPS_USER:-root}"
SSH_KEY="${NVV_SSH_KEY:-$HOME/.ssh/vultr_etsy}"
WEBROOT="${NVV_WEBROOT:-/var/www/northvanvotes}"

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> Rebuilding the dataset (asserts before it will publish anything)"
.venv/bin/python -m pipeline.build_dataset

echo "==> Building the site"
# Astro reports a per-page render failure as [ERROR] but still exits 0 and
# still writes dist/, so `set -e` alone will not catch it. Deploying that
# output with --delete removes every page that failed to build: it once wiped
# all 59 candidate pages off the live site.
BUILD_LOG="$(mktemp)"
npm --prefix site run build 2>&1 | tee "$BUILD_LOG"
if grep -q "\[ERROR\]" "$BUILD_LOG"; then
  echo
  echo "!! The build reported errors. Nothing has been uploaded." >&2
  grep "\[ERROR\]" "$BUILD_LOG" | head -5 >&2
  exit 1
fi

# A sanity floor on what we are about to ship. Catches a build that "succeeds"
# while silently producing far fewer pages than it should.
PAGES=$(find site/dist -name "*.html" | wc -l | tr -d " ")
CANDIDATES=$(find site/dist/candidates -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d " ")
echo "==> Built ${PAGES} pages, ${CANDIDATES} candidate pages"
if [ "$PAGES" -lt 70 ] || [ "$CANDIDATES" -lt 59 ]; then
  echo "!! Too few pages built (expected 70+ and 59 candidates). Not uploading." >&2
  exit 1
fi

echo "==> Uploading to ${VPS_USER}@${VPS}:${WEBROOT}"
# --delete removes files that no longer exist, so a withdrawn candidate's page
# actually disappears instead of lingering.
# Upload into a staging directory, then swap it in with a single mv. Replacing
# files in place leaves a two-to-three second window where a visitor can be
# served new HTML that references a stylesheet which has not arrived yet. The
# site has readers now, so that window is worth closing.
STAGING="${WEBROOT}.incoming"

# macOS ships rsync 2.6.9, which has no --info=stats1; --stats works on both.
# --delete still applies, but to the staging copy rather than what is live.
rsync -az --delete --human-readable --stats \
  -e "ssh -i ${SSH_KEY}" \
  site/dist/ "${VPS_USER}@${VPS}:${STAGING}/"

echo "==> Swapping it in"
ssh -i "${SSH_KEY}" "${VPS_USER}@${VPS}" "
  set -e
  test -f ${STAGING}/index.html
  test -d ${STAGING}/candidates
  chown -R caddy:caddy ${STAGING}
  rm -rf ${WEBROOT}.previous
  mv ${WEBROOT} ${WEBROOT}.previous
  mv ${STAGING} ${WEBROOT}
  echo '    swapped; previous kept at ${WEBROOT}.previous'
"

echo "==> Verifying"
curl -sS -o /dev/null -w "  https://northvanvotes.ca -> %{http_code} in %{time_total}s\n" \
  https://northvanvotes.ca/ || echo "  (not reachable yet — check DNS)"

echo "Done."
