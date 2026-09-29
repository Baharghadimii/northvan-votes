"""Download candidate photos and serve them from our own origin.

Hotlinking the municipalities' images has two problems. Every visitor's browser
would make a request to cnv.org and images.dnv.org, which is a third-party
request we do not control and cannot promise anything about — awkward for a site
that tells readers it tracks nobody. And the photos vanish from our pages the
moment either municipality reorganises its media library, which they will do
after the election.

Photos are cached under data/raw/photos/ and copied into the site's public/
directory as <candidate id>.<ext>.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

from pipeline.fetching import fetch

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "data" / "candidates.json"
PUBLIC = ROOT / "site" / "public" / "photos"

CONTENT_EXT = {".jpg": ".jpg", ".jpeg": ".jpg", ".png": ".png", ".webp": ".webp", ".gif": ".gif"}


def extension_for(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext, norm in CONTENT_EXT.items():
        if path.endswith(ext):
            return norm
    return ".jpg"


def main() -> int:
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    PUBLIC.mkdir(parents=True, exist_ok=True)

    mapping: dict[str, str] = {}
    failed: list[tuple[str, str]] = []

    for c in candidates:
        url = c.get("photo_url")
        if not url or url.startswith("/photos/"):
            continue
        ext = extension_for(url)
        try:
            data = fetch(url, "photos", suffix=ext, binary=True)
        except Exception as exc:  # noqa: BLE001
            failed.append((c["name"], f"{type(exc).__name__}: {exc}"))
            continue
        if not data or len(data) < 512:
            failed.append((c["name"], f"suspiciously small ({len(data) if data else 0} bytes)"))
            continue
        target = PUBLIC / f"{c['id']}{ext}"
        target.write_bytes(data)
        mapping[c["id"]] = f"/photos/{c['id']}{ext}"
        print(f"  {c['name']:24} {len(data)//1024:4} KB -> {target.name}")

    (ROOT / "data" / "photos.json").write_text(
        json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    optimise()

    # Extensions change during optimisation, so rebuild the mapping from what
    # is actually on disk rather than from what was downloaded.
    mapping = {
        f.stem: f"/photos/{f.name}" for f in sorted(PUBLIC.iterdir()) if f.is_file()
    }
    (ROOT / "data" / "photos.json").write_text(
        json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"\n{len(mapping)} photos stored locally")
    if failed:
        print(f"{len(failed)} could not be fetched (their pages fall back to initials):")
        for name, why in failed:
            print(f"  - {name}: {why}")
    return 0




def optimise(max_px: int = 400, quality: int = 82) -> None:
    """Square-crop and shrink photos for the web.

    The municipalities publish these at wildly different sizes — some 200px,
    some 3000px and 1.6 MB. Unoptimised they add ~13 MB to a site most people
    will open on a phone, on the way to a polling station.
    """
    from PIL import Image, ImageOps

    before = sum(f.stat().st_size for f in PUBLIC.iterdir() if f.is_file())
    for f in sorted(PUBLIC.iterdir()):
        if not f.is_file() or f.suffix not in (".jpg", ".png", ".webp"):
            continue
        with Image.open(f) as im:
            im = ImageOps.exif_transpose(im)
            # Crop to a square around the centre so the avatar circle never
            # slices someone's face off.
            im = ImageOps.fit(im, (min(max_px, max(im.size)),) * 2, method=Image.LANCZOS, centering=(0.5, 0.4))
            im = im.convert("RGB")
            im.save(f.with_suffix(".jpg"), "JPEG", quality=quality, optimize=True, progressive=True)
        if f.suffix != ".jpg":
            f.unlink()

    after = sum(f.stat().st_size for f in PUBLIC.iterdir() if f.is_file())
    print(f"optimised: {before // 1024} KB -> {after // 1024} KB "
          f"({100 - after * 100 // max(before, 1)}% smaller)")


if __name__ == "__main__":
    raise SystemExit(main())
