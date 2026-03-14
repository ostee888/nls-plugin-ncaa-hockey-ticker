from __future__ import annotations

from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
import logging
import os

import cairosvg

debug = logging.getLogger("scoreboard")

API_BASE_URL = os.getenv("NCAA_API_BASE_URL", "https://ncaa-api.henrygd.me").rstrip("/")

PLUGIN_DIR = Path(__file__).parent
LOGO_DIR = PLUGIN_DIR / "data" / "logos"
LOGO_DIR.mkdir(parents=True, exist_ok=True)


def cache_logo(team_name: str, force_refresh: bool = False, dark: bool = False) -> Optional[Path]:
    slug = _slugify(team_name)

    svg_path = LOGO_DIR / f"{slug}.svg"
    png_path = LOGO_DIR / f"{slug}.png"

    if force_refresh:
        svg_path.unlink(missing_ok=True)
        png_path.unlink(missing_ok=True)

    if png_path.exists():
        return png_path

    if not svg_path.exists():
        if not _download_logo_svg(slug, svg_path, dark=dark):
            return None

    try:
        cairosvg.svg2png(
            url=str(svg_path),
            write_to=str(png_path),
            output_width=128,
            output_height=128,
        )
    except Exception as exc:
        debug.warning("Failed converting SVG to PNG for %s: %s", slug, exc)
        return None

    return png_path if png_path.exists() else None


def get_logo(team_name: str, force_refresh: bool = False) -> Optional[Path]:
    return cache_logo(team_name, force_refresh=force_refresh)


def ensure_logo(team_name: str, force_refresh: bool = False) -> Optional[Path]:
    return cache_logo(team_name, force_refresh=force_refresh)


def _download_logo_svg(slug: str, svg_path: Path, dark: bool = False) -> bool:
    url = f"{API_BASE_URL}/logo/{slug}.svg"
    if dark:
        url += "?dark=true"

    req = Request(
        url,
        headers={
            "User-Agent": "NCAA-Hockey-Ticker/1.0",
            "Accept": "image/svg+xml,image/*;q=0.8,*/*;q=0.5",
        },
    )

    try:
        with urlopen(req, timeout=10) as response:
            data = response.read()

        if not data:
            return False

        svg_path.write_bytes(data)
        return True
    except Exception as exc:
        debug.warning("Failed downloading logo for %s from %s: %s", slug, url, exc)
        return False


def _slugify(value) -> str:
    text = str(value or "").strip().lower()
    chars = []
    last_dash = False

    for ch in text:
        if ch.isalnum():
            chars.append(ch)
            last_dash = False
        else:
            if not last_dash:
                chars.append("-")
                last_dash = True

    return "".join(chars).strip("-")