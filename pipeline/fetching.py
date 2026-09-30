"""Polite, cached HTTP.

Every byte this project uses is written to data/raw/ and committed. That keeps
re-runs off other people's servers (several of these are volunteer campaign
sites on shared hosting) and makes the published dataset reproducible by anyone
who clones the repo.
"""

from __future__ import annotations

import datetime
import hashlib
import os
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

CONTACT = os.environ.get("CONTACT_EMAIL", "contact@northvanvotes.ca")
USER_AGENT = f"NorthVanVotesBot/0.1 (+https://northvanvotes.ca; {CONTACT})"

MIN_INTERVAL = 1.0  # seconds between requests to the same host

_last_hit: dict[str, float] = {}
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}


class Blocked(RuntimeError):
    """robots.txt disallows this path."""


def _host(url: str) -> str:
    return urlparse(url).netloc


def _throttle(host: str) -> None:
    last = _last_hit.get(host)
    if last is not None:
        wait = MIN_INTERVAL - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _last_hit[host] = time.monotonic()


def _robots_for(url: str) -> urllib.robotparser.RobotFileParser | None:
    host = _host(url)
    if host in _robots:
        return _robots[host]
    parsed = urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(f"{parsed.scheme}://{host}/robots.txt")
    try:
        _throttle(host)
        resp = requests.get(
            rp.url, headers={"User-Agent": USER_AGENT}, timeout=20
        )
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        else:
            rp = None  # no robots.txt served -> nothing disallowed
    except requests.RequestException:
        rp = None
    _robots[host] = rp
    return rp


def allowed(url: str) -> bool:
    rp = _robots_for(url)
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def retrieved_at(namespace: str, url: str, suffix: str = ".html") -> "datetime.date":
    """The date these bytes were actually fetched, not the date we parsed them.

    Sourced from the cache file mtime so a citation stays truthful across
    re-runs and so rebuilding produces identical output.
    """
    path = cache_path(namespace, url, suffix)
    if not path.exists():
        raise FileNotFoundError(f"not cached yet: {url}")
    return datetime.date.fromtimestamp(path.stat().st_mtime)


def cache_path(namespace: str, url: str, suffix: str) -> Path:
    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
    return RAW / namespace / f"{digest}{suffix}"


def fetch(
    url: str,
    namespace: str,
    *,
    suffix: str = ".html",
    binary: bool = False,
    refresh: bool = False,
    respect_robots: bool = True,
) -> bytes | str:
    """Return a URL's content, from cache when we already have it."""
    path = cache_path(namespace, url, suffix)
    if path.exists() and not refresh:
        return path.read_bytes() if binary else path.read_text(encoding="utf-8")

    if respect_robots and not allowed(url):
        raise Blocked(f"robots.txt disallows {url}")

    _throttle(_host(url))
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()

    path.parent.mkdir(parents=True, exist_ok=True)
    if binary:
        path.write_bytes(resp.content)
        return resp.content

    # RFC 2616 says an unlabelled text/* response is ISO-8859-1, and requests
    # obeys that. Plenty of small sites serve UTF-8 without declaring it, so
    # honouring the spec turns every curly apostrophe into "â€™" — which would
    # then appear, character for character, inside a published quote. Sniff the
    # real encoding whenever the server did not actually tell us one.
    declared = (resp.encoding or "").lower()
    from_header = "charset=" in resp.headers.get("content-type", "").lower()
    if not from_header or declared in ("iso-8859-1", "latin-1", "ascii"):
        resp.encoding = resp.apparent_encoding or "utf-8"

    path.write_text(resp.text, encoding="utf-8")
    return resp.text
