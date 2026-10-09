"""Pure id rules for split maps — no IO, safe to import from anywhere.

A piece of origin map `o` with index `k` has uid ``10000 + o*100 + k``. Real
Uranium map ids are < 1000, so a piece uid can never collide with one, and the
origin is recoverable from the uid alone. Anything keyed by the *Uranium* map
(self-switch/hide flag names, strip_list, PBS metadata, encounters) looks up
`origin_of(uid)`; anything keyed by the *GBA* map uses the uid itself."""
from __future__ import annotations

SPLIT_BASE = 10000
_MAX_PIECES = 100
_MAX_ORIGIN = 1000


def piece_uid(origin: int, k: int) -> int:
    """The uid of piece `k` of origin map `origin`."""
    if not 0 <= origin < _MAX_ORIGIN:
        raise ValueError(f"split origin {origin} outside 0..{_MAX_ORIGIN - 1}")
    if not 0 <= k < _MAX_PIECES:
        raise ValueError(f"piece index {k} outside 0..{_MAX_PIECES - 1}")
    return SPLIT_BASE + origin * _MAX_PIECES + k


def is_piece(uid: int) -> bool:
    return int(uid) >= SPLIT_BASE


def origin_of(uid: int) -> int:
    """The Uranium map a uid came from (identity for an unsplit map)."""
    uid = int(uid)
    return (uid - SPLIT_BASE) // _MAX_PIECES if uid >= SPLIT_BASE else uid


def split_blocked_cells(map_json: dict) -> set[tuple[int, int]]:
    """A piece's cut cells (local coords): walls whose art stays real. Empty for
    an unsplit map. Every collision consumer (layout, traversal) applies them."""
    split = map_json.get("split") or {}
    return {(int(x), int(y)) for x, y in split.get("blocked_cells", [])}


def piece_index(uid: int) -> int:
    """`k` of a piece uid. Raises for an unsplit map."""
    if not is_piece(uid):
        raise ValueError(f"map {uid} is not a split piece")
    return (int(uid) - SPLIT_BASE) % _MAX_PIECES
