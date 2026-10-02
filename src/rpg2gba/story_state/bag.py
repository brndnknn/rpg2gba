"""Known-zero key items: the bag-quantity model (operator ruling, 2026-10-02).

An item's bag quantity is known to be 0 at a point in the chain unless
something reachable up to that point could grant it. Restricted to KEY ITEMS
(Essentials pocket 8): ordinary items arrive by unscripted channels (wild held
items, Pickup, Thief) a script scan cannot see; key items cannot.

This module owns (a) the key-item set and (b) the text scan that turns a
script / condition string into `BagHas(item)` grants and havocs. `extract.py`
calls (b) per row scope; nothing here decides liveness.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from rpg2gba.pbs_converter import items as pbs_items

_PBITEMS_REF = r"(?:::)?(?:PBItems::|:)"

# A literal grant of ONE item by symbol as the first argument.
_GRANT_RE = re.compile(
    r"(?:Kernel\s*\.\s*)?(?:pbItemBall|pbReceiveItem)\s*\(?\s*" + _PBITEMS_REF + r"([A-Z][A-Z0-9_]*)"
    r"|\$PokemonBag\s*\.\s*pbStoreItem\s*\(\s*" + _PBITEMS_REF + r"([A-Z][A-Z0-9_]*)"
)

# Any grant call at all, literal or not: one whose argument is not a literal
# symbol (`pbReceiveItem(pbGet(1))`, `pbItemBall(item)` -- 46 corpus sites,
# none on CH01-CH05 maps) could grant any key item.
_ANY_GRANT_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:pbItemBall|pbReceiveItem|pbStoreItem)\s*\(\s*([^,)]*)")
_LITERAL_ARG_RE = re.compile(r"^\s*" + _PBITEMS_REF + r"[A-Za-z][A-Za-z0-9_]*\s*$")

# Pure reads of the quantity: never change the bag.
_READ_RE = re.compile(
    r"\$PokemonBag\s*\.\s*(?:pbQuantity|pbHasItem\??|pbCanStore\w*)\s*\(\s*"
    + _PBITEMS_REF + r"([A-Z][A-Z0-9_]*)"
)

_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Z][A-Z0-9_]*)(?![A-Za-z0-9_])")

# `jvGiveReward` pays from the PROFREWARDS table, not a literal. (A mart call's
# stock list is a literal array in the script, so its key items are already
# caught as unclassified mentions below.)
_REWARD_CALL_RE = re.compile(r"(?<![A-Za-z0-9_])jvGiveReward(?![A-Za-z0-9_])")


def _uranium_src() -> Path:
    if "RPG2GBA_URANIUM_SRC" not in os.environ:
        from rpg2gba.pipeline import _load_dotenv  # lazy: only for the env default

        _load_dotenv()
    src = os.environ.get("RPG2GBA_URANIUM_SRC")
    if not src:
        raise RuntimeError(
            "RPG2GBA_URANIUM_SRC is not set (and .env-paths didn't provide it); "
            "story_state.bag needs items.dat to know which items are key items"
        )
    return Path(src)


def _reference_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "reference"


@cache
def key_item_symbols() -> frozenset[str]:
    """Internal symbols (e.g. ``"BIKEWHEEL"``) of every Essentials pocket-8
    (Key Items) item. Fails loud if `items.dat` or the id->symbol table is
    unreadable or disagrees."""
    items = pbs_items.parse(_uranium_src() / "Data" / "items.dat")
    path = _reference_dir() / "uranium_data" / "item_internal_names.json"
    names = {int(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}
    pbs_items.attach_internal_names(items, names)
    keys = frozenset(it.internal_name for it in items if it.pocket == pbs_items._KEY_ITEMS_POCKET)
    if not keys:
        raise ValueError("story_state.bag: no pocket-8 key items found in items.dat")
    return keys


@cache
def _reward_items() -> frozenset[str]:
    """Every item symbol the `PROFREWARDS` ladder (jvGiveReward) can pay."""
    from rpg2gba.beat_floor.reward_ladder import load_profrewards

    return frozenset(i for rung in load_profrewards() for i in rung.items)


@dataclass(frozen=True)
class BagScan:
    """What one script/condition text does to the bag: key items it grants by
    literal symbol, and key items it touches in a way it cannot classify."""

    grants: frozenset[str] = frozenset()
    havocs: frozenset[str] = frozenset()


def scan_bag_text(text: str) -> BagScan:
    """Classify every key-item mention in `text` (script source or a 111
    type-12 condition). Grants: `pbItemBall`/`pbReceiveItem`/`pbStoreItem`
    with a literal first argument. Reads (`pbQuantity`/`pbHasItem`) are
    neutral. Any OTHER occurrence of a key-item symbol (mart lists,
    `pbDeleteItem`, reward tables...) or a `jvGiveReward` (every PROFREWARDS
    key item) is a havoc, and so is every key item when a grant call's
    argument is not a literal symbol."""
    keys = key_item_symbols()
    grants: set[str] = set()
    covered: list[tuple[int, int]] = []
    for m in _GRANT_RE.finditer(text):
        item = m.group(1) or m.group(2)
        if item in keys:
            grants.add(item)
            covered.append(m.span())
    for m in _READ_RE.finditer(text):
        covered.append(m.span())

    havocs: set[str] = set()
    for m in _TOKEN_RE.finditer(text):
        if m.group(1) in keys and not any(a <= m.start() < b for a, b in covered):
            havocs.add(m.group(1))
    if _REWARD_CALL_RE.search(text):
        havocs |= _reward_items() & keys
    if any(not _LITERAL_ARG_RE.match(m.group(1)) for m in _ANY_GRANT_RE.finditer(text)):
        havocs |= keys
    return BagScan(frozenset(grants), frozenset(havocs))
