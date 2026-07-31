"""Load and validate `reference/chapters.json` — the chapter→map-id binding.

This file is the §4.3 source of truth for *what maps a play-order unit covers*.
Nothing else creates that mapping: the census keys off it, the chapter documents
cite it, and `tileset_converter.map_set` is expected to derive its slice roster
from it rather than keeping a second hand-edited list.

Curation rules the loader enforces (all fail loud, §4.5):

* every chapter id is unique, and names an act that exists;
* every act lists chapters that exist, and every chapter belongs to its act;
* every map id resolves in `map_infos.json` (typo protection);
* a chapter's `outdoor` map, when set, is one of its own maps;
* `visit` numbering is consistent — a location's first chapter is visit 1, and
  revisits increment without gaps;
* `tier` and `status` come from closed vocabularies.

A map id may legitimately appear in several chapters: revisits are separate
chapters over the same maps (see the design record), so map ids are *not*
required to be globally unique across chapters.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

TIERS = ("full", "medium", "thin")
"""Detail tiers, per the grill's distance-plus-novelty gradient."""

STATUSES = ("built", "in_progress", "planned")


@dataclass(frozen=True)
class Chapter:
    """One location-unit of the walkthrough, at one point in play order."""

    id: str
    act: str
    title: str
    maps: tuple[int, ...]
    visit: int = 1
    wiki_page: str | None = None
    outdoor: int | None = None
    predecessor: str | None = None
    tier: str = "thin"
    status: str = "planned"
    gate_in: str | None = None
    notes: str = ""

    @property
    def is_revisit(self) -> bool:
        return self.visit > 1


@dataclass(frozen=True)
class Act:
    """A walkthrough top-level section — a span of chapters ending at a Gym."""

    id: str
    title: str
    chapters: tuple[str, ...]
    wiki_heading: str | None = None


@dataclass(frozen=True)
class ChapterBinding:
    """The whole binding, indexed for lookup."""

    acts: tuple[Act, ...]
    chapters: tuple[Chapter, ...]
    _by_id: dict[str, Chapter] = field(default_factory=dict, repr=False)

    def chapter(self, chapter_id: str) -> Chapter:
        try:
            return self._by_id[chapter_id]
        except KeyError:
            raise KeyError(
                f"no chapter {chapter_id!r}; known: {[c.id for c in self.chapters]}"
            ) from None

    def act(self, act_id: str) -> Act:
        for a in self.acts:
            if a.id == act_id:
                return a
        raise KeyError(f"no act {act_id!r}; known: {[a.id for a in self.acts]}")

    def chapters_in(self, act_id: str) -> list[Chapter]:
        return [self.chapter(cid) for cid in self.act(act_id).chapters]

    def chapters_for_map(self, map_id: int) -> list[Chapter]:
        """Every chapter covering *map_id*, in play order (revisits included)."""
        return [c for c in self.chapters if map_id in c.maps]

    @property
    def map_ids(self) -> list[int]:
        """Every map id bound to any chapter, sorted and de-duplicated."""
        return sorted({m for c in self.chapters for m in c.maps})


def default_binding_path() -> Path:
    """`reference/chapters.json`, resolved from this file's location."""
    return Path(__file__).resolve().parents[3] / "reference" / "chapters.json"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"reference/chapters.json: {message}")


def load_binding(
    path: Path | None = None,
    *,
    map_infos_path: Path | None = None,
) -> ChapterBinding:
    """Parse and validate the binding. Raises `ValueError` on any curation error.

    *map_infos_path* enables the map-id existence check; pass ``None`` to skip it
    (useful in tests that don't have a converted corpus on disk).
    """
    path = path or default_binding_path()
    raw = json.loads(path.read_text(encoding="utf-8"))

    schema = raw.get("schema")
    _require(schema == SCHEMA_VERSION,
             f"schema is {schema!r}, expected {SCHEMA_VERSION}")

    chapters: list[Chapter] = []
    seen: set[str] = set()
    for entry in raw.get("chapters", []):
        cid = entry["id"]
        _require(cid not in seen, f"duplicate chapter id {cid!r}")
        seen.add(cid)
        tier, status = entry.get("tier", "thin"), entry.get("status", "planned")
        _require(tier in TIERS, f"{cid}: tier {tier!r} not in {TIERS}")
        _require(status in STATUSES, f"{cid}: status {status!r} not in {STATUSES}")
        maps = tuple(entry.get("maps", []))
        _require(bool(maps), f"{cid}: has no maps")
        outdoor = entry.get("outdoor")
        _require(outdoor is None or outdoor in maps,
                 f"{cid}: outdoor map {outdoor} is not among its maps {maps}")
        chapters.append(Chapter(
            id=cid,
            act=entry["act"],
            title=entry["title"],
            maps=maps,
            visit=entry.get("visit", 1),
            wiki_page=entry.get("wiki_page"),
            outdoor=outdoor,
            predecessor=entry.get("predecessor"),
            tier=tier,
            status=status,
            gate_in=entry.get("gate_in"),
            notes=entry.get("notes", ""),
        ))

    by_id = {c.id: c for c in chapters}
    acts = tuple(
        Act(id=a["id"], title=a["title"], chapters=tuple(a.get("chapters", [])),
            wiki_heading=a.get("wiki_heading"))
        for a in raw.get("acts", [])
    )

    act_ids = {a.id for a in acts}
    for c in chapters:
        _require(c.act in act_ids, f"{c.id}: unknown act {c.act!r}")
        _require(c.predecessor is None or c.predecessor in by_id,
                 f"{c.id}: unknown predecessor {c.predecessor!r}")
    for a in acts:
        for cid in a.chapters:
            _require(cid in by_id, f"act {a.id}: unknown chapter {cid!r}")
            _require(by_id[cid].act == a.id,
                     f"act {a.id} lists {cid!r}, which claims act "
                     f"{by_id[cid].act!r}")
    listed = [cid for a in acts for cid in a.chapters]
    _require(len(listed) == len(chapters),
             f"{len(chapters)} chapters defined but {len(listed)} listed in acts")

    _validate_visits(chapters)

    if map_infos_path is not None and map_infos_path.exists():
        infos = json.loads(map_infos_path.read_text(encoding="utf-8"))
        known = {int(k) for k in infos}
        for c in chapters:
            unknown = [m for m in c.maps if m not in known]
            _require(not unknown,
                     f"{c.id}: map ids not in map_infos.json: {unknown}")

    return ChapterBinding(acts=acts, chapters=tuple(chapters), _by_id=by_id)


def _validate_visits(chapters: list[Chapter]) -> None:
    """A location's visits must run 1,2,3… in play order, without gaps."""
    by_place: dict[str, list[Chapter]] = {}
    for c in chapters:
        key = c.wiki_page or c.title
        by_place.setdefault(key, []).append(c)
    for place, group in by_place.items():
        visits = [c.visit for c in group]
        expected = list(range(1, len(group) + 1))
        _require(sorted(visits) == expected,
                 f"{place!r}: visit numbers {sorted(visits)} should be {expected} "
                 f"(chapters {[c.id for c in group]})")
