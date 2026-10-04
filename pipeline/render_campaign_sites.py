"""Render the campaign sites that a plain fetch cannot read.

Six candidates build their sites with JavaScript, so the HTML a normal request
returns is an empty shell. Left alone they showed one or two passages while
candidates on ordinary sites showed eighteen — not because they had said less,
but because of how their site was built. That is my tooling penalising them.

This runs a real browser over just those sites, waits for the page to settle,
and hands the rendered HTML to the same extractor everything else goes through,
so the result is identical in kind to the other 33.

Rendered HTML is cached under data/raw/rendered/ so a re-run never revisits a
volunteer's site.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

from pipeline.fetching import USER_AGENT, allowed
from pipeline.models import Source
from pipeline.scrape_campaign_sites import (
    MAX_PAGES, MIN_PAGE_CHARS, SKIP, clean_text, same_host, score, sitemap_urls,
)

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "data" / "candidates.json"
OUT = ROOT / "data" / "campaign_pages.json"
CACHE = ROOT / "data" / "raw" / "rendered"

SETTLE_MS = 2500

# A plain fetch "succeeding" is not the same as it working. Three candidates
# came back with a few hundred characters of hero banner from sites that are
# thousands of characters long, because the platform renders its content with
# JavaScript. The first version of this script only rescued candidates with
# *nothing*, so a useless scrap counted as done and they stayed thin — which is
# exactly the "a thin page should not be mistaken for a quiet candidate" problem
# this script exists to prevent. Anything under this gets a browser too.
# For scale: the median campaign site here yields 6,264 characters.
MIN_SITE_CHARS = 1500


def cache_for(url: str) -> Path:
    return CACHE / f"{hashlib.sha256(url.encode()).hexdigest()[:16]}.html"


def render(page, url: str) -> str | None:
    cached = cache_for(url)
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    if not allowed(url):
        print(f"      robots.txt disallows {url}")
        return None
    try:
        page.goto(url, wait_until="networkidle", timeout=45000)
    except Exception:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as exc:  # noqa: BLE001
            print(f"      {type(exc).__name__} on {url}")
            return None
    page.wait_for_timeout(SETTLE_MS)
    html = page.content()
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(html, encoding="utf-8")
    return html


def crawl(page, website: str, name: str) -> list[Source]:
    host = urlparse(website).netloc
    home = render(page, website)
    if not home:
        return []

    soup = BeautifulSoup(home, "lxml")
    pages: list[tuple[int, str]] = [(999, website)]
    seen = {urldefrag(website).url.rstrip("/")}
    for a in soup.find_all("a", href=True):
        href = urldefrag(urljoin(website, a["href"])).url
        if not same_host(urlparse(href).netloc, host) or SKIP.search(href):
            continue
        key = href.rstrip("/")
        if key in seen:
            continue
        s = score(href, a.get_text(" ", strip=True))
        if s == 0:
            continue
        seen.add(key)
        pages.append((s, href))
    pages.sort(key=lambda t: -t[0])

    # A menu built in script leaves no links to follow. The site's own sitemap
    # is a better table of contents than a rendered menu, so fall back to it
    # rather than publishing a candidate's home page and calling it their
    # platform.
    if len(pages) == 1:
        def fetch(u: str) -> str | None:
            # Plain HTTP: a sitemap is XML, and a browser wraps it in a viewer.
            import requests

            r = requests.get(u, headers={"User-Agent": USER_AGENT}, timeout=20)
            return r.text if r.status_code == 200 else None

        extra = sitemap_urls(website, fetch)
        if extra:
            print(f"      no links in the markup; sitemap lists {len(extra)} pages")
            pages += [(0, u) for u in extra]

    out: list[Source] = []
    for _, url in pages[:MAX_PAGES]:
        html = home if url == website else render(page, url)
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        text = clean_text(soup)
        if len(text) < MIN_PAGE_CHARS:
            print(f"      thin after rendering: {url}")
            continue
        t = soup.find("title")
        title = re.sub(r"\s+", " ", t.get_text(strip=True))[:120] if t else None
        out.append(
            Source(
                type="campaign_site",
                url=url,
                title=title or f"{name} campaign site",
                text=text,
                retrieved=date.fromtimestamp(cache_for(url).stat().st_mtime),
            )
        )
    return out


def main() -> int:
    from playwright.sync_api import sync_playwright

    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    existing = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}

    # Only the ones a plain fetch could not read.
    import yaml

    cfg = ROOT / "config" / "extra-websites.yaml"
    no_crawl = set()
    if cfg.exists():
        for e in yaml.safe_load(cfg.read_text(encoding="utf-8")) or []:
            if e.get("crawl") is False:
                no_crawl.add(e["name"])

    def yielded(cid: str) -> int:
        return sum(len(p.get("text", "")) for p in existing.get(cid) or [])

    targets = [
        c for c in candidates
        if c.get("website") and yielded(c["id"]) < MIN_SITE_CHARS
        and c["name"] not in no_crawl
        and "facebook.com" not in c["website"]
    ]
    print(f"{len(targets)} campaign sites need a browser\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 1600})
        page = ctx.new_page()
        # Images and fonts are irrelevant to text extraction and slow to fetch.
        page.route(re.compile(r"\.(png|jpe?g|gif|webp|svg|woff2?|ttf|mp4)$"), lambda r: r.abort())

        for i, c in enumerate(targets, 1):
            print(f"  [{i}/{len(targets)}] {c['name']:20} {urlparse(c['website']).netloc}", flush=True)
            sources = crawl(page, c["website"], c["name"])
            gained = sum(len(s.text) for s in sources) if sources else 0
            had = yielded(c["id"])
            # Never trade down: a render that goes wrong must not throw away
            # text a plain fetch already got.
            if sources and gained > had:
                existing[c["id"]] = [json.loads(s.model_dump_json()) for s in sources]
                note = f" (was {had:,})" if had else ""
                print(f"      {len(sources)} pages, {gained:,} chars{note}")
            elif had:
                print(f"      kept the {had:,} chars already captured")
            else:
                print("      still nothing usable")

        browser.close()

    OUT.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\n{len(existing)} candidates now have campaign pages -> {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
