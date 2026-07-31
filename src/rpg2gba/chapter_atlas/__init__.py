"""Chapter atlas — the play-order planning layer over the converted corpus.

A *chapter* is one location-unit of the game's walkthrough (a town and its
interiors, or a route and its side rooms). Chapters group into *acts*, which are
the walkthrough's own top-level sections (each ending at a Gym). The binding
from chapter to RMXP map ids is hand-curated in `reference/chapters.json`
(:mod:`.binding`); every *number* a chapter document quotes comes from the
mechanical census in :mod:`.census`, so a converter change refreshes the docs
instead of silently staling them.

Design record: `reference/findings/grill_chapter_atlas_2026-07-30.md`.
"""
from .binding import Act, Chapter, ChapterBinding, load_binding
from .census import ChapterCensus, MapCensus, census_for_maps

__all__ = [
    "Act",
    "Chapter",
    "ChapterBinding",
    "ChapterCensus",
    "MapCensus",
    "census_for_maps",
    "load_binding",
]
