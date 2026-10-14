"""Seed recompute (C6 plan §3 part 2): an order-dependent key lands the
value of whichever writer the chapter's concrete route visits last.

C2 joins the disagreeing writes (a sound over-approximation) and records the
key; this is the route half. A PREDECESSOR's route is read from its generated
module -- beats are emitted in solved order -- so a chapter is seeded, and its
liveness checked, from the order C6 actually chose. The chapter being
generated has no route yet when its story is built, so its own keys stay
joined; they only ever seed its successors, and its review doc reports them.
"""
from __future__ import annotations

import functools
import importlib.util
import re
import logging
from collections.abc import Callable
from pathlib import Path

from rpg2gba.chapter_atlas.binding import load_binding
from rpg2gba.chapter_manifest.schema import page_row_id, parse_row_id
from rpg2gba.playtest.archetypes import load_chapter_rows

logger = logging.getLogger(__name__)

WinnerFor = Callable[[str, tuple[str, ...]], str | None]


def route_winner(chapter_id: str, module_dir: Path) -> WinnerFor:
    """`build_chapter_stories`'s `winner_for` while generating `chapter_id`,
    reading predecessors' already-generated modules from `module_dir`
    (`playtest.chapters_gen`, or a redirected `--module-dir`). Fails loud
    when a predecessor's module was never generated -- the chain is
    generated in order."""
    @functools.cache
    def own_order(cid: str) -> dict[str, int]:
        path = module_dir / f"{cid.lower()}.py"
        if not path.exists():
            raise ValueError(
                f"{chapter_id}: {cid} has an order-dependent write and no generated "
                f"module at {path} -- run `beat_gen generate --chapter {cid}` first")
        spec = importlib.util.spec_from_file_location(f"_seed_{cid.lower()}_generated", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        position: dict[str, int] = {}
        own = [b for b in module.CHAPTER.beats if ":" not in b.name]
        for i, beat in enumerate(own):
            for row_id in beat.rows:
                position[row_id] = i
        return position

    def winner_for(cid: str, writers: tuple[str, ...]) -> str | None:
        if cid == chapter_id:
            return None
        position = own_order(cid)
        missing = [w for w in writers if w not in position]
        if missing:
            # A refused writer has no place in the route: which write lands
            # is genuinely unknown, so the join stands.
            logger.warning("%s: order-dependent writers %s are not walked by %s's route; "
                           "keeping the joined value", chapter_id, missing, cid)
            return None
        return max(writers, key=lambda w: position[w])

    return winner_for


_DEFERRAL_DICTS = ("ELSEWHERE", "REFUSED", "NEVER_FIRES", "EMPTY_PAGES", "WALK_CHECKED")


def _page_of(row_id: str) -> str | None:
    """The owning page row id of a branch row, else None."""
    parsed = parse_row_id(row_id)
    if parsed.kind != "branch":
        return None
    assert parsed.event_id is not None and parsed.page_idx is not None
    return page_row_id(parsed.map_id, parsed.event_id, parsed.page_idx)


_OWNER_ONLY_LATER = re.compile(r"^later: CH\w+$")


def deferred_rows(
    cid: str,
    module_dir: Path,
    *,
    chapters_path: Path | None = None,
    manifest_dir: Path | None = None,
) -> frozenset[str]:
    """Rows on `cid`'s own maps that `cid`'s generated suite did NOT walk
    because it deferred them geographically or by capability (operator
    ruling 2026-10-14, "re-offer deferred rows"). The next later chapter
    whose own maps include the row's map picks it up
    (`build_chapter_stories(deferred_for=...)`).

    Deferred = (a) `ELSEWHERE[row] == "later"`, or `"later: CHnn"` naming only
    the owner `_split_unreachable` found (a value with a further `: detail`
    after the chapter id is a boundary crossing, the inbound mechanism's), or (b) a manifest
    row with non-empty `requires` that no beat claims and no module dict
    (`ELSEWHERE`/`REFUSED`/`NEVER_FIRES`/`EMPTY_PAGES`/`WALK_CHECKED`) lists --
    the capability-blocked rows `emit.py` leaves out of `ELSEWHERE`. Closure:
    a branch row follows its page, and a page whose branch rows are deferred
    follows them when the module claims none of the page's rows."""
    path = module_dir / f"{cid.lower()}.py"
    if not path.exists():
        raise ValueError(
            f"no generated module for {cid} at {path} -- run "
            f"`beat_gen generate --chapter {cid}` first")
    spec = importlib.util.spec_from_file_location(f"_deferral_{cid.lower()}_generated", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    own_maps = set(load_binding(chapters_path).chapter(cid).maps)
    listed: set[str] = set()
    for name in _DEFERRAL_DICTS:
        listed |= set(getattr(module, name, {}))
    claimed = {r for b in module.CHAPTER.beats for r in b.rows}
    elsewhere = getattr(module, "ELSEWHERE", {})

    def on_own_map(row_id: str) -> bool:
        return parse_row_id(row_id).map_id in own_maps

    deferred = {r for r, v in elsewhere.items()
                if (v == "later" or _OWNER_ONLY_LATER.match(str(v))) and on_own_map(r)}
    rows = load_chapter_rows(cid, manifest_dir=manifest_dir)
    for row in rows:
        if (row.requires and row.row_id not in claimed and row.row_id not in listed
                and on_own_map(row.row_id)):
            deferred.add(row.row_id)

    # Closure over page/branch groups (rows known to the manifest or the module).
    all_ids = {r.row_id for r in rows} | listed | claimed | deferred
    by_page: dict[str, set[str]] = {}
    for rid in all_ids:
        if not on_own_map(rid):
            continue
        parsed = parse_row_id(rid)
        page = rid if parsed.kind == "page" else _page_of(rid)
        if page is not None:
            by_page.setdefault(page, set()).add(rid)
    for page, members in by_page.items():
        if page in deferred:
            deferred |= members
        elif members & deferred and not members & claimed:
            deferred |= members
    return frozenset(deferred)


def deferred_loader(chapter_id: str, module_dir: Path) -> Callable[[str], frozenset[str]]:
    """`build_chapter_stories`'s `deferred_for` while generating `chapter_id`:
    each EARLIER chapter's deferred rows from its generated module. Never
    reads `chapter_id`'s own module (it is being regenerated)."""
    @functools.cache
    def loader(cid: str) -> frozenset[str]:
        if cid == chapter_id:
            return frozenset()
        return deferred_rows(cid, module_dir)

    return loader
