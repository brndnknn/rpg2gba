"""Map-split stage IO (design `reference/guides/map_split_stage.md`).

Runs after deserialization, before everything that reads `maps/`. For each split
origin in `reference/split_maps.json`:

* the deserializer's `maps/MapNNN.json` is moved to `maps_presplit/` (a fresh
  deserializer run writes it back to `maps/`, and the next stage run moves it
  again — so `maps_presplit/` always holds the latest unsplit source);
* one `maps/Map<uid>.json` per piece is written;
* every direct transfer (code 201) into the origin, in every map, is retargeted
  to the owning piece's local frame; the original of each map rewritten this
  way is kept in `maps_presplit/` and restored at the start of the next run,
  so a re-run never re-reads its own output;
* `connections.json` rows naming the origin are rebased onto the owning piece
  (original kept as `connections_presplit.json`);
* the generated arrow seams go to `split_seam_warps.json` and a summary to
  `split_maps.gen.json`.

Idempotent: inputs are always the pre-split copies, outputs are overwritten."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from rpg2gba.map_split.derive import SplitResult, derive_split, rebase_connection_row, rewrite_transfer
from rpg2gba.map_split.spec import SplitSpec, load_split_maps
from rpg2gba.traversal.collision import build_blocked_grid, build_tile_grid, load_tileset_arrays

logger = logging.getLogger(__name__)

PRESPLIT_DIR = "maps_presplit"
SEAMS_FILE = "split_seam_warps.json"
SUMMARY_FILE = "split_maps.gen.json"
CONNECTIONS_FILE = "connections.json"
CONNECTIONS_PRESPLIT = "connections_presplit.json"
_TRANSFER_PLAYER = 201


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _map_name(map_id: int) -> str:
    return f"Map{int(map_id):03d}.json"


def _mid(path: Path) -> int | None:
    try:
        return int(path.stem[3:])
    except ValueError:
        return None


def _names_pieces(path: Path) -> bool:
    """Does this map JSON transfer into a split piece (i.e. is it our output)?"""
    for ev in _read(path).get("events") or []:
        for page in ev.get("pages", []):
            for cmd in page.get("list", []):
                p = cmd.get("parameters") or []
                if (cmd.get("code") == _TRANSFER_PLAYER and len(p) >= 4 and p[0] == 0
                        and isinstance(p[1], int) and p[1] >= 10000):
                    return True
    return False


def _source_maps(build: Path) -> dict[int, Path]:
    """Every map's PRE-split source, once `run` has restored the pre-split state:
    `maps/` for unsplit maps, `maps_presplit/` for split origins. Generated piece
    files (uid >= 10000) are never sources."""
    out: dict[int, Path] = {}
    for d in (build / "maps", build / PRESPLIT_DIR):
        if not d.is_dir():
            continue
        for p in sorted(d.glob("Map*.json")):
            mid = _mid(p)
            if mid is None or mid >= 10000:
                continue
            out.setdefault(mid, p)  # maps/ first: a presplit backup is stale by now
    return out


def _entry_cells(origin: int, sources: dict[int, Path]) -> set[tuple[int, int]]:
    """Every direct transfer target into `origin` (any map, any page)."""
    cells: set[tuple[int, int]] = set()
    for _mid, path in sorted(sources.items()):
        doc = _read(path)
        for ev in doc.get("events") or []:
            for page in ev.get("pages", []):
                for cmd in page.get("list", []):
                    p = cmd.get("parameters") or []
                    if (cmd.get("code") == _TRANSFER_PLAYER and len(p) >= 4 and p[0] == 0
                            and p[1] == origin):
                        cells.add((int(p[2]), int(p[3])))
    return cells


def _blocked_of(doc: dict, tilesets_json: Path) -> dict[tuple[int, int], bool]:
    return build_blocked_grid(build_tile_grid(doc), load_tileset_arrays(int(doc["tileset_id"]), tilesets_json))


def _connection_entries(
    origin: int, doc: dict, blocked: dict, sources: dict[int, Path],
    connections: list[list], tilesets_json: Path,
) -> set[tuple[int, int]]:
    """Origin edge cells the player can actually cross a connection onto: passable
    here, and facing a cell of the neighbour that is reachable from the
    neighbour's own warp arrivals. (Uranium's cliff-top dirt reads passable on
    both sides of an edge, so "passable on both sides" alone floods the border.)"""
    w, h = int(doc["width"]), int(doc["height"])
    out: set[tuple[int, int]] = set()
    for row in connections:
        for side in (0, 3):
            if int(row[side]) != origin:
                continue
            other = int(row[3 - side])
            if other not in sources:
                continue
            edge, off = row[side + 1], int(row[side + 2])
            start = off - int(row[3 - side + 2])  # other's local 0, in origin coords
            odoc = _read(sources[other])
            ow, oh = int(odoc["width"]), int(odoc["height"])
            oblocked = _blocked_of(odoc, tilesets_json)
            opass = {c for c, b in oblocked.items() if not b}
            oarr = {c for c in _entry_cells(other, sources) if 0 <= c[0] < ow and 0 <= c[1] < oh}
            oreach = _flood_cells(oarr, opass | oarr)
            for i in range(w if edge in ("N", "S") else h):
                if edge == "N":
                    mine, theirs = (i, 0), (i - start, oh - 1)
                elif edge == "S":
                    mine, theirs = (i, h - 1), (i - start, 0)
                elif edge == "W":
                    mine, theirs = (0, i), (ow - 1, i - start)
                else:
                    mine, theirs = (w - 1, i), (0, i - start)
                if not blocked[mine] and theirs in oreach:
                    out.add(mine)
    return out


def _flood_cells(start: set, passable: set) -> set:
    seen = set(start)
    stack = list(seen)
    while stack:
        x, y = stack.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n in passable and n not in seen:
                seen.add(n)
                stack.append(n)
    return seen


def derive_one(
    spec: SplitSpec, sources: dict[int, Path], connections: list[list], tilesets_json: Path,
) -> SplitResult:
    if spec.origin not in sources:
        raise FileNotFoundError(f"split origin map {spec.origin} has no deserialized JSON")
    doc = _read(sources[spec.origin])
    blocked = _blocked_of(doc, tilesets_json)
    # Warp arrivals always count (a door tile reads blocked); connection edges
    # only where the neighbour can really deliver the player.
    entries = _entry_cells(spec.origin, sources) | _connection_entries(
        spec.origin, doc, blocked, sources, connections, tilesets_json)
    return derive_split(doc, blocked, entries, spec)


def run(build: Path, *, split_maps: Path | None = None, tilesets_json: Path | None = None) -> list[SplitResult]:
    """Apply every split in `split_maps` (default `reference/split_maps.json`) to
    the build dir `build` (``output/uranium-build``). Returns the results."""
    build = Path(build)
    maps_dir = build / "maps"
    pre_dir = build / PRESPLIT_DIR
    tilesets_json = Path(tilesets_json) if tilesets_json else build / "tilesets.json"
    specs = load_split_maps(split_maps)

    conn_path = build / CONNECTIONS_FILE
    conn_pre = build / CONNECTIONS_PRESPLIT
    if conn_path.is_file() and not _is_split_connections(conn_path, specs):
        shutil.copyfile(conn_path, conn_pre)  # fresh upstream copy
    connections: list[list] = _read(conn_pre) if conn_pre.is_file() else (
        _read(conn_path) if conn_path.is_file() else [])

    # Stale piece files from a previous spec go first (idempotence when a split
    # is removed or re-indexed).
    for p in maps_dir.glob("Map*.json"):
        mid = _mid(p)
        if mid is not None and mid >= 10000:
            p.unlink()

    # Restore the pre-split state of maps/. maps_presplit/ holds (a) each split
    # origin's unsplit JSON and (b) the original of every map whose transfers a
    # previous run rewrote. A maps/ copy that names no piece is fresh
    # deserializer output and supersedes the backup; one that does is our own
    # output and is replaced by the backup.
    pre_dir.mkdir(parents=True, exist_ok=True)
    for p in sorted(pre_dir.glob("Map*.json")):
        mid = _mid(p)
        live = maps_dir / p.name
        fresh = live.is_file() and not _names_pieces(live)
        if mid in specs:
            if fresh:
                shutil.move(str(live), str(p))
            elif live.is_file():
                live.unlink()
        elif fresh:
            p.unlink()
        else:
            shutil.move(str(p), str(live))
    for origin in specs:
        live = maps_dir / _map_name(origin)
        if live.is_file():
            shutil.move(str(live), str(pre_dir / _map_name(origin)))

    sources = _source_maps(build)
    results: dict[int, SplitResult] = {}
    for origin, spec in sorted(specs.items()):
        results[origin] = derive_one(spec, sources, connections, tilesets_json)

    # Piece maps (their own transfers retargeted too).
    for res in results.values():
        for piece in res.pieces:
            doc = piece.map_json
            _retarget_transfers(doc, results, f"Map{piece.uid}")
            _write(maps_dir / _map_name(piece.uid), doc)
            logger.info("split %d -> %d (%s): %dx%d @(%d,%d), %d events",
                        res.origin, piece.uid, piece.name, piece.rect.w, piece.rect.h,
                        piece.rect.x0, piece.rect.y0, len(piece.event_ids))

    # Transfers into a split origin from every other map: rewrite from the
    # pre-split source (maps/ copies of unsplit maps ARE their sources).
    if results:
        for mid, path in sorted(sources.items()):
            if mid in results:
                continue
            doc = _read(path)
            if _retarget_transfers(doc, results, f"Map{mid:03d}"):
                shutil.copyfile(path, pre_dir / _map_name(mid))  # keep the original
                _write(maps_dir / _map_name(mid), doc)

    # connections.json
    if connections:
        dims = {mid: _dims(sources[mid]) for mid in sources}
        new_rows = []
        for row in connections:
            row = list(row)
            for origin, res in results.items():
                if origin in (int(row[0]), int(row[3])):
                    other = int(row[3]) if int(row[0]) == origin else int(row[0])
                    row = rebase_connection_row(row, res, dims[origin], dims[other])
            new_rows.append(row)
        _write(conn_path, new_rows)

    _write(build / SEAMS_FILE, {
        "_doc": "GENERATED by rpg2gba.map_split — arrow-warp seams between split pieces. Do not edit.",
        "seams": [s.as_json() for res in results.values() for s in res.seams],
    })
    _write(build / SUMMARY_FILE, {
        "_doc": "GENERATED by rpg2gba.map_split — piece rectangles per split origin.",
        "splits": {
            str(o): [
                {"uid": p.uid, "k": p.k, "name": p.name, "x0": p.rect.x0, "y0": p.rect.y0,
                 "w": p.rect.w, "h": p.rect.h, "events": p.event_ids}
                for p in res.pieces
            ] for o, res in results.items()
        },
    })
    return list(results.values())


def _dims(path: Path) -> tuple[int, int]:
    doc = _read(path)
    return int(doc["width"]), int(doc["height"])


def _is_split_connections(path: Path, specs: dict[int, SplitSpec]) -> bool:
    """True if `connections.json` is already our rewritten copy (it names a piece
    uid), so the presplit copy must NOT be refreshed from it."""
    rows = _read(path)
    return any(int(r[0]) >= 10000 or int(r[3]) >= 10000 for r in rows)


def _retarget_transfers(doc: dict, results: dict[int, SplitResult], where: str) -> bool:
    changed = False
    for ev in doc.get("events") or []:
        for pi, page in enumerate(ev.get("pages", [])):
            for cmd in page.get("list", []):
                if cmd.get("code") != _TRANSFER_PLAYER:
                    continue
                p = cmd.get("parameters") or []
                new = rewrite_transfer(p, results, f"{where} EV{ev['id']:03d} p{pi}")
                if new is not p:
                    cmd["parameters"] = new
                    changed = True
    return changed
