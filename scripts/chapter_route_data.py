"""Server-side join for the chapter route viewer (``/api/chapter/<CHnn>``).

See ``reference/viewer/chapter_route_viewer.md`` sections 3 and 5.  Hand-authored
suites are excluded entirely: beats come from ``load_chapter(..., suite="gen")``,
the route from ``output/beats/<CH>.route.json``, cards from the
``output/beats/<CH>.beats.json`` sidecar, and walked paths only from an
observed-beats file tagged ``"suite": "gen"``.

Public API::

    list_chapters(out_dir=None) -> list[str]
    chapter_payload(chapter, out_dir=None) -> dict
    build_payload(...)            # pure join, injectable (tests)
    chapter_layout(map_ids, route) -> (maps, w, h)

Failure policy: a missing artifact never raises; it adds a ``notes`` entry.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).parent))
import map_viewer_common as mvc  # noqa: E402

log = logging.getLogger(__name__)

GAP = 4  # cells between laid-out maps / clusters
_SHELF_MIN_W = 48

NOTE_NO_WALK = "no generated-suite run on record; re-run with --suite gen"


# ---------------------------------------------------------------------------
# Small value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BeatInfo:
    """The slice of a ``Beat`` this module needs (decoupled for tests)."""

    name: str
    group: str | None = None
    rows: tuple[str, ...] = ()
    description: str | None = None

    @property
    def group_key(self) -> str:
        return self.group if self.group is not None else self.name


# ---------------------------------------------------------------------------
# Paths / loaders
# ---------------------------------------------------------------------------


def _beats_dir(out_dir: Path | None) -> Path:
    return (out_dir if out_dir is not None else mvc._output_base()) / "beats"


def list_chapters(out_dir: Path | None = None) -> list[str]:
    """Chapter ids that have ``output/beats/<CH>.route.json``, sorted."""
    d = _beats_dir(out_dir)
    if not d.is_dir():
        return []
    return sorted(p.name[: -len(".route.json")] for p in d.glob("*.route.json"))


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_chapter_map_ids(chapter: str) -> list[int]:
    data = _read_json(mvc._repo_root() / "reference" / "chapters.json")
    if not isinstance(data, dict):
        return []
    for ch in data.get("chapters", []):
        if ch.get("id") == chapter:
            return [int(m) for m in ch.get("maps", [])]
    return []


def _load_gen_beats(chapter: str) -> list[BeatInfo]:
    """Own beats of the generated suite, registration order."""
    from rpg2gba.playtest.chapter import load_chapter

    ch = load_chapter(chapter, suite="gen")
    return [
        BeatInfo(b.name, b.group, tuple(b.rows), b.description or None)
        for b in ch.beats
        if ":" not in b.name
    ]


def _load_observed(base: Path, chapter: str) -> dict | None:
    """The chapter's generated-suite run record, or None.

    Generated runs are written to ``output/playtest-gen`` by the operator's
    standing invocation (``--output output/playtest-gen``), so a file there
    counts as gen unless it says otherwise -- records from before the runner
    wrote ``suite`` are untagged.  The shared ``output/playtest`` holds hand and
    gen runs alike and must carry an explicit ``"suite": "gen"``.
    """
    gen = _read_json(base / "playtest-gen" / "observed_beats" / f"{chapter}.json")
    if isinstance(gen, dict) and gen.get("suite", "gen") == "gen":
        return {**gen, "suite": "gen"}
    shared = _read_json(base / "playtest" / "observed_beats" / f"{chapter}.json")
    return shared if isinstance(shared, dict) else None


def _match_card(beat: BeatInfo, cards: dict[str, dict]) -> dict | None:
    """Sidecar card for a loaded beat.

    The sidecar is keyed by the *plan's* beat names, but one template call can
    register under a different runtime name (plan ``m033e002_item_ball_arms``
    -> module ``m033e002_item_ball_spent``; trainer ``_arms`` -> ``_retalk1``).
    Fall back to the same-group card sharing a row, then the same-group card
    sharing the name stem (everything before the last ``_``).  The loaded
    beat's description fills the card's, which the plan never carries.
    """
    card = cards.get(beat.name)
    if card is None:
        same_group = [c for c in cards.values() if c.get("group") == beat.group_key]
        card = next((c for c in same_group if set(c.get("rows", ())) & set(beat.rows)), None)
        if card is None:
            stem = beat.name.rsplit("_", 1)[0]
            card = next((c for c in same_group if c["name"].rsplit("_", 1)[0] == stem), None)
    if card is None:
        return None
    if card.get("description") is None and beat.description:
        card = {**card, "description": beat.description}
    return card


def _beats_from_sidecar(sidecar: dict | None) -> list[BeatInfo]:
    if not sidecar:
        return []
    out = []
    for b in sidecar.get("beats", []):
        out.append(BeatInfo(b["name"], b.get("group"), tuple(b.get("rows", ()))))
    return out


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _tiles(tiles) -> list[list[int]]:
    return [[int(t[0]), int(t[1])] for t in tiles]


def _legs(segment) -> list[dict]:
    if segment is None:
        return []
    return [{"map_id": leg.map_id, "tiles": _tiles(leg.tiles)} for leg in segment.legs]


def _crossings(segment) -> list[dict]:
    if segment is None:
        return []
    return [
        {
            "map_id": c.map_id,
            "cell": [int(c.cell[0]), int(c.cell[1])],
            "script": c.script,
            "certainty": c.certainty,
        }
        for c in segment.crossed_foreign_triggers
    ]


def step_label(number: int, index: int, count: int) -> str:
    """``"N"`` for a one-beat group, else ``"Na"``, ``"Nb"``, ..."""
    if count <= 1:
        return str(number)
    if index < 26:
        return f"{number}{chr(ord('a') + index)}"
    return f"{number}.{index + 1}"


def collapse_path(path: list[dict]) -> list[dict]:
    """Observed path entries -> legs (consecutive same-map entries merged,
    consecutive duplicate cells dropped)."""
    legs: list[dict] = []
    for e in path:
        try:
            mid, x, y = int(e["map_id"]), int(e["x"]), int(e["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if not legs or legs[-1]["map_id"] != mid:
            legs.append({"map_id": mid, "tiles": []})
        t = legs[-1]["tiles"]
        if not t or t[-1] != [x, y]:
            t.append([x, y])
    return legs


def _walked_usable(observed: dict | None) -> bool:
    return (
        isinstance(observed, dict)
        and observed.get("suite") == "gen"
        and isinstance(observed.get("version"), int)
        and observed["version"] >= 2
    )


def _walked_for_group(
    names_to: list[str], names_from: list[str], obs_by_name: dict[str, dict], own: list[str]
) -> dict:
    def collect(names: list[str]) -> list[dict]:
        path: list[dict] = []
        for n in names:
            path.extend(obs_by_name.get(n, {}).get("path", []) or [])
        return collapse_path(path)

    off_plan: list[dict] = []
    violations: list[dict] = []
    for n in own:
        div = obs_by_name.get(n, {}).get("divergence") or {}
        for o in div.get("off_plan", []) or []:
            off_plan.append({"map_id": o["map_id"], "cell": list(o["cell"])})
        for v in div.get("trigger_violations", []) or []:
            violations.append({"map_id": v["map_id"], "cell": list(v["cell"])})
    return {
        "to": collect(names_to),
        "from": collect(names_from),
        "off_plan": off_plan,
        "violations": violations,
    }


def _intersects(entry_rows, beat_rows: set[str]) -> bool:
    if isinstance(entry_rows, str):
        entry_rows = [entry_rows]
    return any(r in beat_rows for r in (entry_rows or []))


def group_beats(plan, beats: list[BeatInfo]) -> dict[int, list[BeatInfo]]:
    """node index -> own beats (registration order) with that node's group."""
    by_key: dict[str, list[BeatInfo]] = {}
    for b in beats:
        by_key.setdefault(b.group_key, []).append(b)
    return {
        n.index: by_key.get(n.group, [])
        for n in plan.nodes
        if n.kind == "group"
    }


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def _default_component(mid: int) -> dict:
    import map_graph

    return map_graph.component_layout(mid)


CROP_PAD = 4  # cells of context kept around the relevant area of a borrowed map


def borrowed_crops(
    borrowed: set[int],
    points: list[tuple[int, int, int]],
    sizes: dict[int, tuple[int, int]],
    pad: int = CROP_PAD,
) -> dict[int, tuple[int, int, int, int]]:
    """Crop rects ``(x0, y0, w, h)`` (map-local cells) for maps the chapter only borrows.

    A map on the route but outside the chapter's own ``maps`` list (CH02 walks
    through CH01's Moki Town only to reach its exit warps) is cut down to the bbox
    of every cell the page draws on it (``points``: ``(map_id, x, y)``), padded
    and clamped to the map.  A map with no points, or whose bbox covers it
    anyway, is left whole.
    """
    box: dict[int, list[int]] = {}
    for mid, x, y in points:
        if mid not in borrowed:
            continue
        b = box.setdefault(mid, [x, y, x, y])
        b[0], b[1], b[2], b[3] = min(b[0], x), min(b[1], y), max(b[2], x), max(b[3], y)
    out: dict[int, tuple[int, int, int, int]] = {}
    for mid, (x0, y0, x1, y1) in box.items():
        if mid not in sizes:
            continue
        mw, mh = sizes[mid]
        cx0, cy0 = max(0, x0 - pad), max(0, y0 - pad)
        cx1, cy1 = min(mw - 1, x1 + pad), min(mh - 1, y1 + pad)
        if (cx0, cy0, cx1, cy1) == (0, 0, mw - 1, mh - 1):
            continue
        out[mid] = (cx0, cy0, cx1 - cx0 + 1, cy1 - cy0 + 1)
    return out


def _apply_crop(m: dict, crops: dict[int, tuple[int, int, int, int]]) -> dict:
    """Shrink a layout member to its crop: the drawn rect moves to (ox+x0, oy+y0)."""
    c = crops.get(m["id"])
    if c is None:
        return dict(m, crop=[0, 0])
    x0, y0, w, h = c
    return dict(m, ox=m["ox"] + x0, oy=m["oy"] + y0, w=w, h=h, crop=[x0, y0])


def chapter_layout(
    map_ids,
    route: list[dict],
    *,
    component: Callable[[int], dict] | None = None,
    crops: dict[int, tuple[int, int, int, int]] | None = None,
) -> tuple[list[dict], int, int]:
    """Stitch chapter maps onto one canvas.

    Seam-connected clusters (via ``map_graph.component_layout``, restricted to
    chapter maps) go left to right in order of first route visit; warp-only
    maps (single-member components) are shelf-packed in rows beneath the
    cluster the route first reaches them from, ordered by first route visit.
    ``route`` is the payload's leg list (``[{"map_id", "tiles"}, ...]``).
    Deterministic. Returns ``(maps, w, h)`` with maps ``{id,name,ox,oy,w,h,crop}``.
    ``crops`` (from ``borrowed_crops``) shrink members before packing; a member's
    ``crop`` is the map-local cell drawn at its ``(ox, oy)`` (``[0, 0]`` uncropped).
    """
    comp = component or _default_component
    crops = crops or {}
    ids = sorted({int(m) for m in map_ids})
    idset = set(ids)
    visit: dict[int, int] = {}
    for i, leg in enumerate(route):
        visit.setdefault(int(leg["map_id"]), i)

    def vkey(mid: int) -> tuple[int, int]:
        return (visit.get(mid, 10**9), mid)

    # clusters
    claimed: set[int] = set()
    clusters: list[list[dict]] = []  # each a list of member dicts (normalized)
    singles: dict[int, dict] = {}
    for mid in ids:
        if mid in claimed:
            continue
        try:
            lay = comp(mid)
            members = [m for m in lay["members"] if m["id"] in idset]
        except Exception:  # noqa: BLE001 -- viewer degrades, never raises
            log.warning("chapter_route_data: no layout for map %d", mid, exc_info=True)
            members = []
        if not members:
            members = [{"id": mid, "name": f"Map{mid:03d}", "ox": 0, "oy": 0, "w": 16, "h": 16}]
        members = [_apply_crop(m, crops) for m in members]
        for m in members:
            claimed.add(m["id"])
        if len(members) == 1:
            singles[members[0]["id"]] = dict(members[0], ox=0, oy=0)
            continue
        mx = min(m["ox"] for m in members)
        my = min(m["oy"] for m in members)
        clusters.append([dict(m, ox=m["ox"] - mx, oy=m["oy"] - my) for m in members])

    def cdim(c: list[dict]) -> tuple[int, int]:
        return (max(m["ox"] + m["w"] for m in c), max(m["oy"] + m["h"] for m in c))

    # host assignment for warp-only maps
    cluster_of: dict[int, int] = {}
    for ci, c in enumerate(clusters):
        for m in c:
            cluster_of[m["id"]] = ci
    host: dict[int, int] = {}  # single map id -> cluster index
    prev: int | None = None
    for leg in route:
        cur = int(leg["map_id"])
        if cur in singles and cur not in host and prev is not None:
            h = cluster_of.get(prev, host.get(prev))
            if h is not None:
                host[cur] = h
        prev = cur
    standalone = [m for m in singles if m not in host]

    # units, ordered by first visit
    units: list[tuple[tuple[int, int], str, int]] = []
    for ci, c in enumerate(clusters):
        units.append((min(vkey(m["id"]) for m in c), "c", ci))
    for mid in standalone:
        units.append((vkey(mid), "s", mid))
    units.sort()

    out: list[dict] = []
    x_cursor = 0
    total_h = 0
    for _, kind, ref in units:
        if kind == "s":
            m = singles[ref]
            out.append(dict(m, ox=x_cursor, oy=0))
            x_cursor += m["w"] + GAP
            total_h = max(total_h, m["h"])
            continue
        c = clusters[ref]
        cw, ch = cdim(c)
        for m in c:
            out.append(dict(m, ox=m["ox"] + x_cursor, oy=m["oy"]))
        shelf = sorted((m for m in host if host[m] == ref), key=vkey)
        limit = max(cw, _SHELF_MIN_W)
        sx = sy = 0
        row_h = 0
        y0 = ch + GAP
        shelf_w = 0
        for mid in shelf:
            m = singles[mid]
            if sx and sx + m["w"] > limit:
                sy += row_h + GAP
                sx = 0
                row_h = 0
            out.append(dict(m, ox=x_cursor + sx, oy=y0 + sy))
            sx += m["w"] + GAP
            shelf_w = max(shelf_w, sx - GAP)
            row_h = max(row_h, m["h"])
        unit_h = ch if not shelf else y0 + sy + row_h
        total_h = max(total_h, unit_h)
        x_cursor += max(cw, shelf_w) + GAP

    w = max((m["ox"] + m["w"] for m in out), default=0)
    h = max((m["oy"] + m["h"] for m in out), default=0)
    return out, w, h


# ---------------------------------------------------------------------------
# Join
# ---------------------------------------------------------------------------


def build_payload(
    chapter: str,
    plan,
    beats: list[BeatInfo],
    sidecar: dict | None,
    observed: dict | None,
    *,
    chapter_maps: list[int] | None = None,
    notes: list[str] | None = None,
    component: Callable[[int], dict] | None = None,
) -> dict:
    """Pure join of loaded objects into the payload documented in the design."""
    notes = list(notes or [])
    if plan is None:
        return {
            "chapter": chapter, "notes": notes, "w": 0, "h": 0, "maps": [],
            "connectors": [], "route": [], "groups": [], "walked_available": False,
        }

    seg_by_from = {s.from_index: s for s in plan.segments}
    seg_by_to = {s.to_index: s for s in plan.segments}

    route = [
        {"map_id": leg.map_id, "tiles": _tiles(leg.tiles)}
        for seg in plan.segments
        for leg in seg.legs
    ]

    connectors: list[dict] = []
    seen_conn: set[tuple] = set()
    for seg in plan.segments:
        for leg in seg.legs:
            ew = leg.exit_warp
            if ew is None:
                continue
            key = (leg.map_id, ew.event_id, ew.dest_map, tuple(ew.dest_cell), tuple(leg.tiles[-1]))
            if key in seen_conn:
                continue
            seen_conn.add(key)
            connectors.append({
                "from": {"map_id": leg.map_id, "cell": [int(leg.tiles[-1][0]), int(leg.tiles[-1][1])]},
                "to": {"map_id": ew.dest_map, "cell": [int(ew.dest_cell[0]), int(ew.dest_cell[1])]},
            })

    # sidecar
    cards: dict[str, dict] = {}
    odw: list[dict] = []
    refusals: list[dict] = []
    if sidecar:
        cards = {b["name"]: b for b in sidecar.get("beats", [])}
        odw = list(sidecar.get("order_dependent_writes", []))
        refusals = list(sidecar.get("refusals", []))
    else:
        notes.append("no beat-card sidecar (output/beats/%s.beats.json); cards unavailable" % chapter)

    # walked
    walked_ok = _walked_usable(observed)
    obs_by_name: dict[str, dict] = {}
    if walked_ok:
        obs_by_name = {b["beat"]: b for b in observed.get("beats", []) if "beat" in b}
    else:
        notes.append(NOTE_NO_WALK)

    gb = group_beats(plan, beats)
    group_nodes = [n for n in plan.nodes if n.kind == "group"]
    names_of = {n.index: [b.name for b in gb[n.index]] for n in group_nodes}
    node_number = {n.index: i + 1 for i, n in enumerate(group_nodes)}

    groups: list[dict] = []
    for node in group_nodes:
        number = node_number[node.index]
        bl = gb[node.index]
        if not bl:
            notes.append(f"group {node.group!r}: no own beats found")
        entries = []
        for i, b in enumerate(bl):
            card = _match_card(b, cards)
            rows = set(b.rows) | set((card or {}).get("rows", ()))
            obs = obs_by_name.get(b.name)
            entries.append({
                "step": step_label(number, i, len(bl)),
                "name": b.name,
                "card": card,
                "order_dependent_writes": [e for e in odw if _intersects(e.get("rows"), rows)],
                "refusals": [e for e in refusals if _intersects(e.get("row"), rows)],
                "status": obs.get("status") if obs else None,
            })
        to_seg = seg_by_to.get(node.index)
        from_seg = seg_by_from.get(node.index)
        walked = None
        if walked_ok:
            nxt = node_number.get(node.index + 1)
            next_names = names_of.get(node.index + 1, []) if nxt else []
            walked = _walked_for_group(names_of[node.index], next_names, obs_by_name, names_of[node.index])
        groups.append({
            "number": number,
            "node_index": node.index,
            "group": node.group,
            "map_id": node.map_id,
            "cell": [int(node.cell[0]), int(node.cell[1])],
            "side": node.chosen_approach.side if node.chosen_approach else None,
            "beats": entries,
            "to": _legs(to_seg),
            "from": _legs(from_seg),
            "to_crossings": _crossings(to_seg),
            "from_crossings": _crossings(from_seg),
            "walked": walked,
        })

    map_ids = set(chapter_maps or [])
    for n in plan.nodes:
        map_ids.add(n.map_id)
    for seg in plan.segments:
        for leg in seg.legs:
            map_ids.add(leg.map_id)
            if leg.exit_warp is not None:
                map_ids.add(leg.exit_warp.dest_map)
    comp = component or _default_component
    borrowed = set(map_ids) - set(chapter_maps) if chapter_maps else set()
    crops: dict[int, tuple[int, int, int, int]] = {}
    if borrowed:
        points: list[tuple[int, int, int]] = []
        for leg in route:
            points.extend((leg["map_id"], t[0], t[1]) for t in leg["tiles"])
        for g in groups:
            points.append((g["map_id"], g["cell"][0], g["cell"][1]))
            for leg in (g["walked"] or {}).get("to", []) + (g["walked"] or {}).get("from", []):
                points.extend((leg["map_id"], t[0], t[1]) for t in leg["tiles"])
        for c in connectors:
            for end in (c["from"], c["to"]):
                points.append((end["map_id"], end["cell"][0], end["cell"][1]))
        sizes = {}
        for mid in borrowed:
            try:
                sizes.update({m["id"]: (m["w"], m["h"]) for m in comp(mid)["members"] if m["id"] == mid})
            except Exception:  # noqa: BLE001 -- uncropped beats a 500
                log.warning("chapter_route_data: no size for map %d; left uncropped", mid, exc_info=True)
        crops = borrowed_crops(borrowed, points, sizes)
    maps, w, h = chapter_layout(map_ids, route, component=component, crops=crops)
    names = _map_names()
    for m in maps:
        if m["id"] in names:
            m["name"] = names[m["id"]]

    return {
        "chapter": chapter,
        "notes": notes,
        "w": w,
        "h": h,
        "maps": [
            {"id": m["id"], "name": m["name"], "ox": m["ox"], "oy": m["oy"], "w": m["w"], "h": m["h"],
             "crop": m.get("crop", [0, 0])}
            for m in sorted(maps, key=lambda m: m["id"])
        ],
        "connectors": connectors,
        "route": route,
        "groups": groups,
        "walked_available": walked_ok,
    }


def _map_names() -> dict[int, str]:
    try:
        import map_graph

        return map_graph.load_map_names()
    except Exception:  # noqa: BLE001
        return {}


def chapter_payload(chapter: str, out_dir: Path | None = None) -> dict:
    """The ``/api/chapter/<CH>`` payload. Never raises for missing artifacts."""
    from rpg2gba.routing.plan import load_plan

    notes: list[str] = []
    bdir = _beats_dir(out_dir)
    route_path = bdir / f"{chapter}.route.json"
    plan = None
    if not route_path.is_file():
        notes.append(f"no route plan at {route_path}")
    else:
        try:
            plan = load_plan(route_path)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"route plan unreadable: {exc}")

    sidecar = _read_json(bdir / f"{chapter}.beats.json")
    if not isinstance(sidecar, dict):
        sidecar = None

    beats: list[BeatInfo] = []
    if plan is not None:
        try:
            beats = _load_gen_beats(chapter)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"generated suite not loadable ({type(exc).__name__}: {exc}); using sidecar beat list")
            beats = _beats_from_sidecar(sidecar)

    observed = _load_observed(out_dir if out_dir is not None else mvc._output_base(), chapter)

    return build_payload(
        chapter, plan, beats, sidecar, observed,
        chapter_maps=_load_chapter_map_ids(chapter), notes=notes,
    )
