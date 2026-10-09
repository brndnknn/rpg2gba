"""`reference/split_maps.json` — load, validate, and expand map-id lists.

The file is hand-authored operator data (CLAUDE.md §4.3). Validation here is
structural only (types, uniqueness); whether the cuts actually separate the
seeds is checked by `derive` against the map's geometry."""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rpg2gba.map_split.ids import piece_uid

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SPLIT_MAPS_PATH = _REPO_ROOT / "reference" / "split_maps.json"

Cell = tuple[int, int]


@dataclass(frozen=True)
class PieceSpec:
    k: int
    name: str
    seeds: tuple[Cell, ...]

    def uid(self, origin: int) -> int:
        return piece_uid(origin, self.k)


@dataclass(frozen=True)
class SplitSpec:
    origin: int
    cuts: frozenset[Cell]
    pieces: tuple[PieceSpec, ...]  # sorted by k; k == 0 is the main piece

    def uids(self) -> list[int]:
        return [p.uid(self.origin) for p in self.pieces]

    def piece(self, k: int) -> PieceSpec:
        for p in self.pieces:
            if p.k == k:
                return p
        raise KeyError(f"split {self.origin}: no piece k={k}")


def _cell(raw: object, where: str) -> Cell:
    if (not isinstance(raw, list) or len(raw) != 2
            or not all(isinstance(v, int) and not isinstance(v, bool) for v in raw)):
        raise ValueError(f"{where}: expected [x, y] ints, got {raw!r}")
    return (raw[0], raw[1])


def parse_split_maps(raw: dict, where: str = "split_maps.json") -> dict[int, SplitSpec]:
    """Parse the file's dict form. Fails loud on any structural problem."""
    splits = raw.get("splits")
    if not isinstance(splits, dict):
        raise ValueError(f"{where}: 'splits' must be an object keyed by origin map id")
    out: dict[int, SplitSpec] = {}
    for key, entry in splits.items():
        w = f"{where} splits[{key!r}]"
        try:
            origin = int(key)
        except ValueError:
            raise ValueError(f"{w}: key must be a map id") from None
        cuts_raw = entry.get("cuts")
        pieces_raw = entry.get("pieces")
        if not isinstance(cuts_raw, list) or not isinstance(pieces_raw, list) or not pieces_raw:
            raise ValueError(f"{w}: needs a 'cuts' list and a non-empty 'pieces' list")
        cuts = [_cell(c, f"{w} cuts[{i}]") for i, c in enumerate(cuts_raw)]
        if len(set(cuts)) != len(cuts):
            raise ValueError(f"{w}: duplicate cut cell(s)")
        pieces: list[PieceSpec] = []
        names: set[str] = set()
        seeds_seen: set[Cell] = set()
        for i, p in enumerate(pieces_raw):
            pw = f"{w} pieces[{i}]"
            k, name, seeds_raw = p.get("k"), p.get("name"), p.get("seeds")
            if not isinstance(k, int) or isinstance(k, bool):
                raise ValueError(f"{pw}: 'k' must be an int")
            piece_uid(origin, k)  # range check
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"{pw}: 'name' must be a non-empty string")
            if name in names:
                raise ValueError(f"{pw}: duplicate piece name {name!r}")
            names.add(name)
            if not isinstance(seeds_raw, list) or not seeds_raw:
                raise ValueError(f"{pw}: needs at least one seed cell")
            seeds = tuple(_cell(s, f"{pw} seeds[{j}]") for j, s in enumerate(seeds_raw))
            dup = seeds_seen & set(seeds)
            if dup:
                raise ValueError(f"{pw}: seed(s) {sorted(dup)} already used by another piece")
            seeds_seen |= set(seeds)
            if set(seeds) & set(cuts):
                raise ValueError(f"{pw}: seed on a cut cell {sorted(set(seeds) & set(cuts))}")
            pieces.append(PieceSpec(k=k, name=name, seeds=seeds))
        ks = sorted(p.k for p in pieces)
        if ks != list(range(len(ks))):
            raise ValueError(f"{w}: piece indices must be 0..{len(ks) - 1}, got {ks}")
        out[origin] = SplitSpec(
            origin=origin, cuts=frozenset(cuts),
            pieces=tuple(sorted(pieces, key=lambda p: p.k)),
        )
    return out


def load_split_maps(path: Path | None = None) -> dict[int, SplitSpec]:
    """Load + validate `reference/split_maps.json` (missing file = no splits)."""
    path = Path(path) if path is not None else DEFAULT_SPLIT_MAPS_PATH
    if not path.is_file():
        return {}
    return parse_split_maps(json.loads(path.read_text(encoding="utf-8")), str(path))


@lru_cache(maxsize=None)
def _default_specs() -> dict[int, SplitSpec]:
    return load_split_maps(DEFAULT_SPLIT_MAPS_PATH)


def expand_split_ids(
    ids: Iterable[int], specs: dict[int, SplitSpec] | None = None
) -> list[int]:
    """Replace every split origin in `ids` with its piece uids, in place of the
    origin, preserving order. Unsplit ids pass through."""
    specs = _default_specs() if specs is None else specs
    out: list[int] = []
    for m in ids:
        spec = specs.get(int(m))
        out.extend(spec.uids() if spec is not None else [m])
    return out


def split_specs() -> dict[int, SplitSpec]:
    """The repo's split decisions (cached)."""
    return _default_specs()
