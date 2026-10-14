"""All-time totals for northvanvotes.ca, read from the server journal.

    scp outreach/totals.py root@$NVV_VPS:/tmp/
    ssh root@$NVV_VPS 'journalctl -u caddy --no-pager -o cat | python3 /tmp/totals.py'

Aggregates on the server so gigabytes of journal never cross the wire. Same
privacy rules as outreach/traffic.py: addresses are truncated to a /24 as they
are read, counted, and never written anywhere.

A /24 is a network, not a person. Two households on the same ISP block count
once, so the unique figure is a floor rather than an estimate.
"""
import sys, json, re, collections, datetime

BOTS = ("bot", "crawl", "spider", "slurp", "curl/", "wget", "python-requests",
        "headless", "monitoring", "uptime", "scanner", "bingpreview",
        "facebookexternalhit", "go-http-client", "dalvik/")
SPOOF = re.compile(r"^mozilla/[\d.]+ \(compatible\)\s*$")
ASSET = (".css", ".js", ".woff2", ".jpg", ".png", ".svg", ".ico", ".xml", ".txt")

def tr(ip):
    if ":" in ip:
        return ":".join(ip.split(":")[:3]) + "::/48"
    p = ip.split(".")
    return ".".join(p[:3]) + ".0/24" if len(p) == 4 else "?"

nets = set()
views_by_day = collections.Counter()
nets_by_day = collections.defaultdict(set)
days_by_net = collections.defaultdict(set)
pages = collections.Counter()
total = 0

for line in sys.stdin:
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
    ua = " ".join(r.get("headers", {}).get("User-Agent", [""])).lower()
    if any(b in ua for b in BOTS) or SPOOF.match(ua):
        continue
    uri = r.get("uri", "")
    if any(uri.endswith(x) for x in ASSET):
        continue
    # Caddy's ts is an epoch float in the older entries and an RFC3339 string
    # in the newer ones, because the log format was changed partway through.
    # Dropping the ones that did not parse silently lost 3,200 of 3,877 page
    # views in a single day's window and made the site look five times quieter
    # than it is.
    ts = e.get("ts")
    if isinstance(ts, (int, float)):
        when = datetime.datetime.utcfromtimestamp(ts)
    elif isinstance(ts, str):
        when = datetime.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
    else:
        continue
    # Pacific, which is what "a day" means to a North Vancouver reader.
    day = (when - datetime.timedelta(hours=7)).strftime("%Y-%m-%d")
    net = tr(r.get("client_ip", ""))
    total += 1
    nets.add(net)
    views_by_day[day] += 1
    nets_by_day[day].add(net)
    days_by_net[net].add(day)
    pages[uri.split("?")[0]] += 1

print("TOTAL_VIEWS", total)
print("UNIQUE_NETWORKS", len(nets))
print("CAME_BACK", sum(1 for v in days_by_net.values() if len(v) > 1))
print("THREE_PLUS", sum(1 for v in days_by_net.values() if len(v) > 2))
for day in sorted(views_by_day):
    print("DAY", day, views_by_day[day], len(nets_by_day[day]))
for path, n in pages.most_common(10):
    print("PAGE", n, path)
