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
import logging
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

WinnerFor = Callable[[str, tuple[str, ...]], str | None]


def route_winner(chapter_id: str, out_dir: Path) -> WinnerFor:
    """`build_chapter_stories`'s `winner_for` while generating `chapter_id`
    into `out_dir`. Fails loud when a predecessor's module was never
    generated -- the chain is generated in order."""
    @functools.cache
    def own_order(cid: str) -> dict[str, int]:
        path = out_dir / f"{cid.lower()}.generated.py"
        if not path.exists():
            raise ValueError(
                f"{chapter_id}: {cid} has an order-dependent write and no generated "
                f"route at {path} -- run `beat_gen generate --chapter {cid}` first")
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
