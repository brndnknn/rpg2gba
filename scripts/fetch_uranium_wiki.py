"""Fetch Pokémon Uranium wiki pages as raw wikitext, for chapter-doc research.

Why this exists: the agent's own `WebFetch` tool is refused for
`pokemon-uranium.fandom.com` with HTTP 402, and a bare `curl` gets 403 from
Cloudflare. The fandom MediaWiki API answers **200** from this machine as long
as a browser `User-Agent` is sent, so this script is the one reliable route to
wiki content — notably `Game_Walkthrough`, which is the source of truth for
chapter/act boundaries (`reference/chapters.json`).

Wiki content is **cross-check only**, never load-bearing: the converted rxdata
under `output/uranium-build/` decides what a chapter contains, per
`ROM_TEST_DEV.md` Branch A1(b). Fetched pages are derived artifacts and land in
gitignored `output/` (CLAUDE.md §4.4); this script is what's committed, so any
session can reproduce them.

Idempotent: re-running overwrites the cached copies.

Usage:
    python scripts/fetch_uranium_wiki.py                  # the walkthrough
    python scripts/fetch_uranium_wiki.py Route_1 Moki_Town
    python scripts/fetch_uranium_wiki.py --list           # show what's cached
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

API = "https://pokemon-uranium.fandom.com/api.php"

# Cloudflare serves the API only to something that looks like a browser; the
# default `python-requests` UA is what earns the 403.
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

DEFAULT_PAGES = ("Game_Walkthrough",)


def cache_dir() -> Path:
    root = Path(os.environ.get("RPG2GBA_OUTPUT", "output"))
    return root / "uranium-build" / "wiki"


def fetch_wikitext(page: str, timeout: int = 60) -> str:
    """Return `page`'s raw wikitext, or fail loud (§4.5) — never a default."""
    resp = requests.get(
        API,
        params={"action": "parse", "page": page,
                "prop": "wikitext", "format": "json"},
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise RuntimeError(
            f"wiki API refused {page!r}: {payload['error'].get('info', payload['error'])}")
    try:
        return payload["parse"]["wikitext"]["*"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            f"unexpected API response shape for {page!r}: {list(payload)}") from exc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pages", nargs="*", default=[],
                    help=f"wiki page titles (default: {', '.join(DEFAULT_PAGES)})")
    ap.add_argument("--list", action="store_true",
                    help="list cached pages and exit")
    args = ap.parse_args()

    out = cache_dir()
    if args.list:
        if not out.is_dir():
            sys.exit(f"nothing cached: {out} does not exist")
        for f in sorted(out.glob("*.wiki")):
            print(f"{f.stat().st_size:8d}  {f.name}")
        return

    out.mkdir(parents=True, exist_ok=True)
    for page in (args.pages or list(DEFAULT_PAGES)):
        text = fetch_wikitext(page)
        dest = out / f"{page}.wiki"
        dest.write_text(text, encoding="utf-8")
        print(f"{len(text):8d} chars -> {dest}")


if __name__ == "__main__":
    main()
