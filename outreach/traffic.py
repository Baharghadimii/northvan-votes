"""How many real people read northvanvotes.ca, from the server's access log.

    python outreach/traffic.py                         # since yesterday
    python outreach/traffic.py "7 days ago"
    python outreach/traffic.py 2026-11-19 --until 2026-11-23
    python outreach/traffic.py "30 days ago" --page /promises-and-votes

Privacy is unchanged from the first version and from what /methodology
promises: the analysis runs on the VPS, IP addresses are cut to their /24 (or
/48) network the moment they are read, nothing is written anywhere, and only
the summary comes back. No script on the page, no cookies, no third party.

Why it is stricter than it used to be: most of the log is not people. Many
bots now send an ordinary browser user agent, so counting "anything that says
Mozilla" reported ~1,000 home-page views on 2026-11-23, when about a dozen
people visited. So each network is sorted into one of:

  confirmed  its browser downloaded the page's stylesheet, fonts or photos,
             AND sent the headers a browser sends when a person opens a
             page (Sec-Fetch-Mode: navigate and an Accept-Language). A
             headless scraper that loads assets but sends neither walked
             every member page at one per second on 2026-11-22.
  possible   no download, but its requests carry the headers a browser sends
             when a person opens a page (Sec-Fetch-Mode: navigate and an
             Accept-Language). Some are returning readers whose browser still
             had the stylesheet cached; some are bots imitating a browser.
             The truth is somewhere between the two figures.
  excluded   a known bot or tool, anything probing for files a scanner looks
             for (.env, .php, /wp-admin ...), the server itself, our own
             network (whichever sent the "northvanvotes-deploy-check" user
             agent our deploy checks use), and imitators: networks that ask
             for a page without its trailing slash while claiming to come
             from a page on this site. Every link on the site ends in a
             slash, so a real click never does that. A crawler spread over
             a dozen residential networks did exactly this on 2026-11-22,
             one page per network, to look like separate people.

A network is a household or a phone carrier block, not a person: two people
on one network count once, and a phone moving networks counts twice.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys

VPS = os.environ.get("NVV_VPS", "209.250.232.171")
KEY = os.environ.get("NVV_SSH_KEY", os.path.expanduser("~/.ssh/vultr_etsy"))

# Runs on the VPS (python3 -), reading the Caddy journal there.
ANALYSIS = r'''
import collections, datetime, json, re, subprocess, sys

since, until, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
cmd = ["journalctl", "-u", "caddy", "--since", since, "--no-pager", "-o", "cat"]
if until:
    cmd += ["--until", until]
log = subprocess.run(cmd, capture_output=True, text=True).stdout

BOTS = ("bot", "crawl", "spider", "slurp", "curl/", "wget", "python", "headless", "monitoring",
        "uptime", "scanner", "bingpreview", "facebookexternalhit", "go-http-client", "dalvik/",
        "preview", "fetch", "node", "axios", "okhttp", "java/", "ruby", "perl", "libwww", "scrapy",
        "http", "northvanvotes-deploy-check")
SPOOFED = re.compile(r"^mozilla/[\d.]+ \(compatible\)\s*$")
PROBE = re.compile(r"\.(env|php|asp|aspx|cgi|git|sql|bak)\b|/(sdk|boaform|wp-|admin|cgi-bin|config|backup)", re.I)
ASSET = (".css", ".js", ".woff2", ".jpg", ".jpeg", ".png", ".webp", ".svg", ".ico", ".xml",
         ".txt", ".webmanifest", ".map", ".pdf")
LOADS = ("/_astro/", "/fonts/", "/photos/")

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Vancouver")
except Exception:
    TZ = datetime.timezone(datetime.timedelta(hours=-8))

def network(ip):
    if ":" in ip:
        return ":".join(ip.split(":")[:3]) + "::/48"
    p = ip.split(".")
    return ".".join(p[:3]) + ".0/24" if len(p) == 4 else "?"

def day(ts):
    if isinstance(ts, (int, float)):
        d = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
    else:
        d = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return d.astimezone(TZ).date().isoformat()

ours = {network("''' + VPS + r'''")}
loaded, probers, navigators, imitators = set(), set(), set(), set()
views = []          # (day, network, path, referrer, browser-navigation?)
bots = 0
for line in log.splitlines():
    line = line.strip()
    if not line.startswith("{"):
        continue
    try:
        e = json.loads(line)
    except Exception:
        continue
    if e.get("msg") != "handled request":
        continue
    r = e.get("request", {})
    h = {k.lower(): " ".join(v) for k, v in r.get("headers", {}).items()}
    ua = h.get("user-agent", "").lower()
    net = network(r.get("client_ip", ""))
    path = r.get("uri", "").split("?")[0]
    if "northvanvotes-deploy-check" in ua:
        ours.add(net)
    if not ua or any(b in ua for b in BOTS) or SPOOFED.match(ua):
        bots += 1
        continue
    if PROBE.search(path):
        probers.add(net)
        continue
    if path.startswith(LOADS):
        loaded.add(net)
        continue
    ref = h.get("referer", "")
    if e.get("status") in (301, 308) and "northvanvotes.ca" in ref and not path.endswith("/"):
        imitators.add(net)
    if path.endswith(ASSET) or e.get("status") not in (200, 304):
        continue
    navigate = h.get("sec-fetch-mode") == "navigate" and bool(h.get("accept-language"))
    if navigate:
        navigators.add(net)
    views.append((day(e.get("ts")), net, path, h.get("referer", ""), navigate))

excluded = ours | probers | imitators
confirmed = (loaded & navigators) - excluded
possible = {n for _, n, _, _, nav in views if nav} - confirmed - excluded

by_day = collections.defaultdict(lambda: [0, set(), set()])
pages, page_people = collections.Counter(), collections.defaultdict(set)
referrers = collections.Counter()
for d, net, path, ref, nav in views:
    if net in excluded:
        continue
    if not path.startswith(prefix):
        continue
    if net in confirmed:
        by_day[d][0] += 1
        by_day[d][1].add(net)
        pages[path] += 1
        page_people[path].add(net)
    elif net in possible and nav:
        by_day[d][2].add(net)
    else:
        continue
    if ref and "northvanvotes.ca" not in ref:
        referrers[ref.split("/")[2] if "//" in ref else ref] += 1

people = set().union(*(v[1] for v in by_day.values())) if by_day else set()
maybe = set().union(*(v[2] for v in by_day.values())) if by_day else set()
scope = f" on {prefix}*" if prefix != "/" else ""
print(f"\n  {since}{' to ' + until if until else ''}{scope}\n")
print(f"  confirmed readers: {len(people)} (their browser loaded the page), {sum(v[0] for v in by_day.values())} page views")
print(f"  possible readers:  {len(maybe)} more (browser-like, loaded nothing: returning visitors or bots)")
print(f"  excluded: {bots} bot and tool requests, {len(probers)} scanner networks, "
      f"{len(imitators - probers - ours)} imitating networks, "
      f"{len(ours)} of our own (the server, and wherever our deploy checks ran)")

if by_day:
    print("\n  day (Pacific)   confirmed   views   possible")
    for d in sorted(by_day):
        v, n, m = by_day[d]
        print(f"    {d}   {len(n):6}   {v:7}   {len(m):6}")

if page_people:
    print("\n  most read, by confirmed readers")
    for path, nets in sorted(page_people.items(), key=lambda x: (-len(x[1]), x[0]))[:15]:
        print(f"    {len(nets):4} people  {pages[path]:4} views  {path}")

if referrers:
    print("\n  arrived from (outside links, confirmed and possible readers)")
    for host, n in referrers.most_common(8):
        print(f"    {n:5}  {host}")
print()
'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("since", nargs="?", default="yesterday", help='journalctl time, e.g. "7 days ago" or 2026-11-19')
    ap.add_argument("--until", default="", help="end of the range (journalctl time)")
    ap.add_argument("--page", default="/", help="only count paths starting with this, e.g. /promises-and-votes")
    args = ap.parse_args()

    remote = "python3 - " + " ".join(shlex.quote(a) for a in (args.since, args.until, args.page))
    result = subprocess.run(
        ["ssh", "-i", KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", f"root@{VPS}", remote],
        input=ANALYSIS, capture_output=True, text=True, timeout=300,
    )
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
