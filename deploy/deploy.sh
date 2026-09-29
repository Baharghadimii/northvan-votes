#!/usr/bin/env bash
# Build on the Mac, ship the result to the VPS.
#
#   bash deploy/deploy.sh
#
# The VPS serves files; it never builds. No Node, no npm and no build memory
# needed on a box that is also running the Etsy pipeline.
set -euo pipefail

VPS="${NVV_VPS:-209.250.232.171}"
VPS_USER="${NVV_VPS_USER:-$USER}"
WEBROOT="${NVV_WEBROOT:-/var/www/northvanvotes}"

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> Rebuilding the dataset (asserts before it will publish anything)"
.venv/bin/python -m pipeline.build_dataset

echo "==> Building the site"
npm --prefix site run build

echo "==> Uploading to ${VPS_USER}@${VPS}:${WEBROOT}"
# --delete removes files that no longer exist, so a withdrawn candidate's page
# actually disappears instead of lingering.
rsync -az --delete --human-readable --info=stats1 \
  site/dist/ "${VPS_USER}@${VPS}:${WEBROOT}/"

echo "==> Verifying"
curl -sS -o /dev/null -w "  https://northvanvotes.ca -> %{http_code} in %{time_total}s\n" \
  https://northvanvotes.ca/ || echo "  (not reachable yet — check DNS)"

echo "Done."
