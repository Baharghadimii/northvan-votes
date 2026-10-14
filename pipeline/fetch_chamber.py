"""Download the North Vancouver Chamber's candidate response PDFs.

The Chamber put two questions to every mayor and council candidate in both
municipalities, gave them 200 words each, and published every reply it received
as a one-page PDF. Fetched once and kept, because the answers quoted on the site
are sliced out of the saved text rather than out of a live page.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pdfplumber
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "chamber"
INDEX = RAW / "index.json"
SOURCE = "https://www.nvchamber.ca/blog/municipal-election-qas/"
UA = "northvanvotes/1.0 (+https://northvanvotes.ca; hello@northvanvotes.ca)"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    links = json.loads((RAW / "links.json").read_text(encoding="utf-8"))
    index = {}
    session = requests.Session()
    session.headers["User-Agent"] = UA
    for i, (name, url) in enumerate(links, 1):
        pdf_path = RAW / f"{slug(name)}.pdf"
        txt_path = RAW / f"{slug(name)}.txt"
        if not pdf_path.exists():
            r = session.get(url, timeout=30)
            r.raise_for_status()
            pdf_path.write_bytes(r.content)
            time.sleep(1)  # one a second, same as every other crawl here
        if not txt_path.exists():
            with pdfplumber.open(pdf_path) as pdf:
                text = "\n".join((p.extract_text() or "") for p in pdf.pages)
            txt_path.write_text(text, encoding="utf-8")
        index[name] = {"url": url, "text_file": txt_path.name}
        print(f"  [{i:2}/{len(links)}] {name:22} {len(txt_path.read_text(encoding='utf-8')):5} chars")
    INDEX.write_text(json.dumps({"source": SOURCE, "candidates": index}, indent=2) + "\n",
                     encoding="utf-8")
    print(f"{len(index)} responses -> {RAW.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
