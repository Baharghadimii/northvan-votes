"""Read northvanvotes.ca's traffic from the server journal.

Runs over SSH and prints a summary. Nothing is stored: IP addresses are
truncated to a /24 the moment they are read, used only to approximate how many
distinct people visited, and never written anywhere. No cookies, no client-side
script, nothing leaves the VPS. /methodology says exactly this.

    python outreach/traffic.py            # since yesterday
    python outreach/traffic.py "3 days ago"
"""

from __future__ import annotations

import collections
import json
import re
import os
import subprocess
import sys

VPS = os.environ.get("NVV_VPS", "209.250.232.171")
KEY = os.environ.get("NVV_SSH_KEY", os.path.expanduser("~/.ssh/vultr_etsy"))

# Anything that is obviously not a reader.
BOTS = ("bot", "crawl", "spider", "slurp", "curl/", "wget", "python-requests",
        "headless", "monitoring", "uptime", "scanner", "bingpreview", "facebookexternalhit",
        "go-http-client", "dalvik/")

# Scanners that claim to be a browser without naming one. A real browser always
# carries a product token (Chrome/, Safari/, Firefox/); "Mozilla/5.0 (compatible)"
# on its own is a scraper. One such crawler walked the candidate list from a
# datacentre and re-requested its own malformed "<url>,<count>" concatenations,
# which looked at first glance like a bug in our markup. It was not.
SPOOFED = re.compile(r"^mozilla/[\d.]+ \(compatible\)\s*$")


def truncate(ip: str) -> str:
    """Keep the network, drop the host. Enough to count people, not identify one."""
    if ":" in ip:
        return ":".join(ip.split(":")[:3]) + "::/48"
    parts = ip.split(".")
    return ".".join(parts[:3]) + ".0/24" if len(parts) == 4 else "?"


def main() -> int:
    since = sys.argv[1] if len(sys.argv) > 1 else "yesterday"
    out = subprocess.run(
        ["ssh", "-i", KEY, "-o", "BatchMode=yes", f"root@{VPS}",
         f'journalctl -u caddy --since "{since}" --no-pager -o cat'],
        capture_output=True, text=True, timeout=180,
    ).stdout

    pages = collections.Counter()
    referrers = collections.Counter()
    networks = set()
    statuses = collections.Counter()
    missing = collections.Counter()
    bots = 0
    total = 0

    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("msg") != "handled request":
            continue

        req = e.get("request", {})
        ua = " ".join(req.get("headers", {}).get("User-Agent", [""])).lower()
        if any(b in ua for b in BOTS) or SPOOFED.match(ua):
            bots += 1
            continue

        uri = req.get("uri", "")
        # Count errors before the asset filter: a missing icon is a real miss
        # even though an icon is never a page view.
        if e.get("status", 0) >= 400:
            missing[f'{e["status"]} {uri.split("?")[0]}'] += 1
        if any(uri.endswith(x) for x in (".css", ".js", ".woff2", ".jpg", ".png", ".svg", ".ico", ".xml", ".txt")):
            continue

        total += 1
        statuses[e.get("status", 0)] += 1
        pages[uri.split("?")[0]] += 1
        networks.add(truncate(req.get("client_ip", "")))

        ref = " ".join(req.get("headers", {}).get("Referer", [""]))
        if ref and "northvanvotes.ca" not in ref:
            host = ref.split("/")[2] if "//" in ref else ref
            referrers[host] += 1

    print(f"\n  since {since}\n")
    print(f"  {total} page views from roughly {len(networks)} distinct networks")
    print(f"  ({bots} requests from bots and tools, excluded)\n")

    if not total:
        print("  Nothing yet. Logging started 2026-10-03.\n")
        return 0

    print("  most read")
    for path, n in pages.most_common(12):
        print(f"    {n:5}  {path}")

    if referrers:
        print("\n  where they came from")
        for host, n in referrers.most_common(10):
            print(f"    {n:5}  {host}")
    else:
        print("\n  where they came from: nothing yet — no external referrers seen")

    if missing:
        print("\n  errors (bots excluded):")
        for what, n in missing.most_common(12):
            print(f"    {n:5}  {what}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
