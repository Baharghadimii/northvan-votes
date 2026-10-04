"""Crawl candidates' own campaign websites.

Self-reported, like their filed statement — but it is their claim on their own
site, and every candidate who listed a site is treated the same way. Most of
these are volunteer-built on shared hosting, so the crawl is deliberately small
and slow: robots.txt respected, one request per second per host, a handful of
pages each, everything cached so a re-run never touches the site again.

Text quality matters more here than in a normal scrape. Published quotes are cut
character-for-character out of whatever this stores, so boilerplate that slips
through would end up beside a candidate's name.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

from pipeline.fetching import Blocked, fetch, retrieved_at
from pipeline.models import Source

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "data" / "candidates.json"
OUT = ROOT / "data" / "campaign_pages.json"

MAX_PAGES = 6
MIN_PARAGRAPH_CHARS = 60
MIN_PAGE_CHARS = 200

# Pages worth reading, best first. A candidate's platform is rarely on the
# homepage; it is behind a link called "Platform" or "Priorities".
PRIORITY = [
    (100, re.compile(r"platform|priorit|policy|policies|issues|my-plan|the-plan|vision", re.I)),
    (80, re.compile(r"where-i-stand|what-i|commitments|pledge|agenda", re.I)),
    # Incumbents often file their substance under their record rather than a
    # platform page. Jessica McIlroy's is at /at-city-hall, which matched nothing
    # above, so the crawler took her home page and stopped.
    (70, re.compile(r"at-city-hall|city-hall|my-record|track-record|accomplish"
                    r"|achievement|on-council|in-office|delivered", re.I)),
    (60, re.compile(r"about|bio|background|experience|who-i-am|meet", re.I)),
    (40, re.compile(r"housing|transport|transit|traffic|climate|tax|safety|school", re.I)),
]

SKIP = re.compile(
    r"\.(pdf|jpe?g|png|gif|svg|webp|mp4|mov|zip|docx?|xlsx?)$"
    r"|/(donate|contribute|volunteer|signup|sign-up|contact|privacy|terms|cart|checkout)"
    r"|/(coming-soon|maintenance-mode|under-construction)"
    r"|mailto:|tel:|javascript:",
    re.I,
)

# Chrome that appears on every page of a site and is not the candidate speaking.
BOILERPLATE = re.compile(
    r"^(home|about|menu|skip to|copyright|©|all rights reserved|powered by|"
    r"authorized by|privacy policy|terms|follow (us|me)|share this|"
    r"sign up|subscribe|donate|volunteer|contact|back to top|read more|learn more)\b",
    re.I,
)


def score(href: str, text: str) -> int:
    blob = f"{href} {text}"
    for weight, pattern in PRIORITY:
        if pattern.search(blob):
            return weight
    return 0


def clean_text(soup: BeautifulSoup) -> str:
    """Paragraph text a human would read, joined the same way statements are."""
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "form", "svg"]):
        tag.decompose()
    for tag in soup.find_all(attrs={"role": ["navigation", "banner", "contentinfo"]}):
        tag.decompose()

    body = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup

    def collect(elements) -> list[str]:
        parts: list[str] = []
        seen: set[str] = set()
        for el in elements:
            text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
            if len(text) < MIN_PARAGRAPH_CHARS or BOILERPLATE.match(text):
                continue
            if text in seen:  # repeated blocks across a template
                continue
            seen.add(text)
            parts.append(text)
        return parts

    parts = collect(body.find_all(["p", "li", "h2", "h3", "blockquote"]))

    # Some site builders emit prose in divs and spans with no paragraph tags at
    # all. One candidate's priorities page held 7,000 characters that the tag
    # list above simply could not see. Fall back to the innermost blocks that
    # hold text directly, which avoids swallowing a wrapper and its children.
    if sum(len(x) for x in parts) < MIN_PAGE_CHARS:
        leaves = [
            el for el in body.find_all(["div", "section", "article", "span", "td"])
            if not el.find(["div", "section", "article", "p", "li", "table"])
        ]
        parts = collect(leaves)

    return "\n\n".join(parts)


def same_host(a: str, b: str) -> bool:
    """Whether two hosts are the same site, ignoring a leading "www.".

    Candidates register www.example.ca and then link internally to example.ca,
    or the reverse. Comparing netloc literally treated every one of those links
    as leaving the site, so the crawler read the home page and stopped. Linda
    Munro's platform lives on five subpages that were all discarded this way,
    leaving her with a hero banner and one position while her site was full of
    policy. She had to email me to find out.
    """
    return a.lower().removeprefix("www.") == b.lower().removeprefix("www.")


def sitemap_urls(website: str, get) -> list[str]:
    """Pages listed in the site's own sitemap, for sites whose menu is script.

    Kulvir Mann's nav renders as script with no hrefs, so link discovery found
    five targets and none of them were his platform. A WordPress sitemap lists
    every page, which is a more reliable table of contents than a rendered menu.

    Ordering prefers a scored page, then a shallower path: a campaign's current
    pages sit at the top level while old material gets filed underneath, and his
    site still carries his 2022 trustee run under /trustee/. Quoting that as if
    it were this election would be worse than quoting nothing.
    """
    host = urlparse(website).netloc
    found: list[str] = []
    for name_ in ("wp-sitemap.xml", "sitemap.xml", "sitemap_index.xml"):
        try:
            body = get(urljoin(website, "/" + name_))
        except Exception:  # noqa: BLE001
            continue
        if not body:
            continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body)
        # A sitemap index points at further sitemaps; follow one level.
        for loc in list(locs):
            if loc.endswith(".xml"):
                locs.remove(loc)
                try:
                    inner = get(loc)
                except Exception:  # noqa: BLE001
                    continue
                if inner:
                    locs += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", inner)
        for loc in locs:
            if not same_host(urlparse(loc).netloc, host) or SKIP.search(loc):
                continue
            if urlparse(loc).path.strip("/") == urlparse(website).path.strip("/"):
                continue  # the home page is already the crawl's starting point
            found.append(loc)
        if found:
            break
    order = {u: i for i, u in enumerate(dict.fromkeys(found))}

    def rank(u: str) -> tuple:
        # Depth first, so archived sections sink below the live campaign; then
        # the site's own sitemap order, which tracks how pages were built.
        return (urlparse(u).path.strip("/").count("/"), -score(u, ""), order[u])

    seen: set[str] = set()
    out: list[str] = []
    for u in sorted(dict.fromkeys(found), key=rank):
        k = u.rstrip("/")
        if k in seen:
            continue
        seen.add(k)
        out.append(u)
    return out


def crawl(website: str, name: str) -> list[Source]:
    root = urlparse(website)
    if not root.netloc:
        return []
    host = root.netloc

    try:
        home_html = fetch(website, "campaign")
    except Blocked:
        print(f"    robots.txt disallows {host}")
        return []
    except Exception as exc:  # noqa: BLE001
        print(f"    {host}: {type(exc).__name__}")
        return []

    soup = BeautifulSoup(home_html, "lxml")
    pages: list[tuple[int, str]] = [(999, website)]
    seen_urls = {urldefrag(website).url.rstrip("/")}

    for a in soup.find_all("a", href=True):
        href = urldefrag(urljoin(website, a["href"])).url
        if not same_host(urlparse(href).netloc, host) or SKIP.search(href):
            continue
        key = href.rstrip("/")
        if key in seen_urls:
            continue
        s = score(href, a.get_text(" ", strip=True))
        if s == 0:
            continue
        seen_urls.add(key)
        pages.append((s, href))

    pages.sort(key=lambda t: -t[0])
    out: list[Source] = []

    for _, url in pages[:MAX_PAGES]:
        try:
            html = home_html if url == website else fetch(url, "campaign")
        except Blocked:
            continue
        except Exception:  # noqa: BLE001
            continue
        text = clean_text(BeautifulSoup(html, "lxml"))
        if len(text) < MIN_PAGE_CHARS:
            continue
        title = None
        t = BeautifulSoup(html, "lxml").find("title")
        if t:
            title = re.sub(r"\s+", " ", t.get_text(strip=True))[:120]
        out.append(
            Source(
                type="campaign_site",
                url=url,
                title=title or f"{name} campaign site",
                text=text,
                retrieved=retrieved_at("campaign", url),
            )
        )
    return out


def main() -> int:
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))

    # Some sites are listed for readers but deliberately not read: a Facebook
    # page behind a login, or a site in maintenance.
    import yaml

    cfg = ROOT / "config" / "extra-websites.yaml"
    no_crawl = set()
    if cfg.exists():
        for e in yaml.safe_load(cfg.read_text(encoding="utf-8")) or []:
            if e.get("crawl") is False:
                no_crawl.add(e["name"])

    with_sites = [
        c for c in candidates
        if c.get("website") and c["name"] not in no_crawl
        and "facebook.com" not in c["website"]
    ]
    print(f"{len(with_sites)} candidates listed a campaign site\n")

    result: dict[str, list[dict]] = {}
    empty: list[str] = []

    for i, c in enumerate(with_sites, 1):
        print(f"  [{i:2}/{len(with_sites)}] {c['name']:24} {urlparse(c['website']).netloc}", flush=True)
        sources = crawl(c["website"], c["name"])
        if sources:
            result[c["id"]] = [json.loads(s.model_dump_json()) for s in sources]
            chars = sum(len(s.text) for s in sources)
            print(f"      {len(sources)} pages, {chars:,} chars")
        else:
            empty.append(c["name"])
            print("      nothing usable")

    OUT.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    pages = sum(len(v) for v in result.values())
    print(f"\n{pages} pages from {len(result)} of {len(with_sites)} campaign sites -> {OUT.name}")
    if empty:
        print(f"\n{len(empty)} produced nothing readable (often a JavaScript-rendered site):")
        for n in empty:
            print(f"  - {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
