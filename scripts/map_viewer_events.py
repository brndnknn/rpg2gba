# ruff: noqa: E501
"""Server-side data-enrichment layer for the map viewer's EVENTS debug mode.

Companion to ``map_viewer_common.py`` (the GRAPHICS mode's data layer). Where
``map_viewer_common._parse_events`` emits a thin per-event dict for drawing
markers, this module resolves *identity*: which NPC is actually a trainer
(and who), which is an item ball (and which item), where a warp actually
goes, and which playtest beats are declared/observed on this map.

Public API (do not change these three signatures — a concurrent agent wires
the server routes against this exact contract):

    enrich_events(map_id, events_list) -> list[dict]
    event_detail(map_id, event_id) -> dict          # KeyError if no such event
    beat_markers(map_id) -> dict

Circular-import note: ``map_viewer_common.build_map_data`` needs this module,
but this module also wants ``map_viewer_common``'s path helpers
(``_output_base``, ``_maps_dir``, ``_repo_root``, ``_file_fingerprint``). The
cycle is broken on the OTHER side: ``map_viewer_common`` imports this module
lazily, inside ``build_map_data``'s function body, not at its own module top
— so by the time this module's top-level ``import map_viewer_common as mvc``
runs, ``map_viewer_common`` is already fully initialized in ``sys.modules``
(whether the entry point was ``map_viewer_common`` or this module first).

Failure policy (deliberate exception to CLAUDE.md §4.5 fail-loud): this is a
debug viewer. A missing/unreadable OPTIONAL artifact (observed-beats files,
the fork's ``map_groups.h``, the trainer JSONs, the map-constant registry
state) must never break the map view — degrade to an empty/partial result
and log a warning (``beat_markers`` additionally surfaces this in its
``notes`` list, per the brief). Genuinely corrupt data that IS present still
fails loud (e.g. ``event_detail`` on an unreadable map JSON raises).
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import map_viewer_common as mvc  # noqa: E402 — see circular-import note above

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RMXP event-command / trigger constants (mirrors
# src/rpg2gba/conversion_agent/deterministic.py's names; duplicated rather
# than imported since deterministic.py doesn't export them as a public API)
# ---------------------------------------------------------------------------

_TRANSFER_PLAYER = 201
_SHOW_TEXT = 101
_SHOW_TEXT_CONT = 401
_CONDITIONAL_BRANCH = 111
_SCRIPT = 355
_SCRIPT_CONT = 655

_TRIGGER_NAMES = {
    0: "action button",
    1: "player touch",
    2: "event touch",
    3: "autorun",
    4: "parallel process",
}

_ITEMBALL_RE = re.compile(r"pbItemBall\(\s*(?:::)?PBItems::(\w+)\s*\)")


# ---------------------------------------------------------------------------
# Module-level caches — mtime-fingerprinted, following map_viewer_common's
# _png_paths_cache idiom: (fingerprint, value) tuples, recomputed only when a
# fresh fingerprint no longer matches, so a pipeline rebuild while the server
# runs is picked up rather than served stale forever.
# ---------------------------------------------------------------------------

_ctx_cache: tuple[tuple, object] | None = None
_item_names_cache: tuple[tuple, dict[str, str]] | None = None
_trainer_join_cache: tuple[tuple, dict] | None = None
_map_registry_cache: tuple[tuple, tuple[dict, dict]] | None = None
_map_groups_cache: tuple[tuple, tuple[dict, list[str]]] | None = None
_switch_names_cache: tuple[tuple, dict[str, str]] | None = None
_variable_names_cache: tuple[tuple, dict[str, str]] | None = None


def _get_context():
    """Cached ``deterministic.Context`` (items + trainers lookup tables)."""
    from rpg2gba.conversion_agent import deterministic as det

    reference_dir = mvc._repo_root() / "reference"
    intermediate_dir = mvc._output_base() / "uranium-build" / "intermediate"
    fp = (
        mvc._file_fingerprint(reference_dir / "uranium_data" / "item_internal_names.json"),
        mvc._file_fingerprint(reference_dir / "uranium_data" / "item_names.json"),
        mvc._file_fingerprint(intermediate_dir / "trainers.json"),
    )
    global _ctx_cache
    if _ctx_cache is not None and _ctx_cache[0] == fp:
        return _ctx_cache[1]
    try:
        ctx = det.load_context(reference_dir=reference_dir, intermediate_dir=intermediate_dir)
    except Exception:
        log.exception("map_viewer_events: failed to load deterministic Context")
        ctx = det.Context()
    _ctx_cache = (fp, ctx)
    return ctx


def _get_item_display_names() -> dict[str, str]:
    """Essentials ``PBItems`` symbol -> human display name (e.g. ``REPEL`` ->
    ``Repel``), via ``reference/uranium_data/{item_internal_names,item_names}.json``.
    Degrades to ``{}`` if either sidecar is missing/unreadable."""
    data_dir = mvc._repo_root() / "reference" / "uranium_data"
    internal_path = data_dir / "item_internal_names.json"
    names_path = data_dir / "item_names.json"
    fp = (mvc._file_fingerprint(internal_path), mvc._file_fingerprint(names_path))
    global _item_names_cache
    if _item_names_cache is not None and _item_names_cache[0] == fp:
        return _item_names_cache[1]
    out: dict[str, str] = {}
    try:
        internal = json.loads(internal_path.read_text(encoding="utf-8"))
        names = json.loads(names_path.read_text(encoding="utf-8"))
        for iid, sym in internal.items():
            out[sym] = names.get(iid) or sym
    except Exception:
        log.warning("map_viewer_events: item display names unavailable (%s / %s)", internal_path, names_path)
        out = {}
    _item_names_cache = (fp, out)
    return out


def _get_trainer_join() -> dict:
    """Cached join data for trainer enrichment:

    ``{"trainers": {TRAINER_* -> record}, "types": {TRAINER_CLASS_* -> record},
      "staged": {TRAINER_* actually in trainer_manifest.json's battle rows}}``

    Any missing/unreadable file degrades that piece to empty — never raises."""
    intermediate_dir = mvc._output_base() / "uranium-build" / "intermediate"
    trainers_path = intermediate_dir / "trainers.json"
    types_path = intermediate_dir / "trainer_types.json"
    manifest_path = mvc._output_base() / "uranium-build" / "trainers" / "trainer_manifest.json"
    fp = (
        mvc._file_fingerprint(trainers_path),
        mvc._file_fingerprint(types_path),
        mvc._file_fingerprint(manifest_path),
    )
    global _trainer_join_cache
    if _trainer_join_cache is not None and _trainer_join_cache[0] == fp:
        return _trainer_join_cache[1]

    trainers: dict = {}
    types: dict = {}
    staged: set[str] = set()
    try:
        trainers = json.loads(trainers_path.read_text(encoding="utf-8")).get("trainers", {})
    except Exception:
        log.warning("map_viewer_events: trainers.json unavailable at %s", trainers_path)
    try:
        types = json.loads(types_path.read_text(encoding="utf-8")).get("trainer_classes", {})
    except Exception:
        log.warning("map_viewer_events: trainer_types.json unavailable at %s", types_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for rec in manifest.get("trainers", []):
            if rec.get("kind") == "battle" and rec.get("trainer_constant"):
                staged.add(rec["trainer_constant"])
    except Exception:
        log.warning("map_viewer_events: trainer_manifest.json unavailable at %s", manifest_path)

    result = {"trainers": trainers, "types": types, "staged": staged}
    _trainer_join_cache = (fp, result)
    return result


def _get_map_registry() -> tuple[dict[int, object], dict[str, int]]:
    """``(by_uranium_id, by_map_const)`` from the persisted
    ``MapConstantRegistry`` state. ``by_map_const`` is the inverse index
    (``MAP_*`` -> uranium id) the brief asks for — the registry itself only
    exposes the forward direction (``.get(uranium_id)``), so it's built here
    from the loaded state. Degrades to ``({}, {})`` if the state file is
    missing/unreadable."""
    from rpg2gba.tileset_converter.map_constants import MapConstantRegistry

    state_path = mvc._output_base() / "uranium-build" / "porymap" / "map_constants.json"
    fp = mvc._file_fingerprint(state_path)
    global _map_registry_cache
    if _map_registry_cache is not None and _map_registry_cache[0] == fp:
        return _map_registry_cache[1]

    by_id: dict[int, object] = {}
    try:
        registry = MapConstantRegistry(state_path=state_path)
        registry.load()
        by_id = dict(registry._by_id)  # no public "all entries" accessor
    except Exception:
        log.warning("map_viewer_events: map-constant registry state unavailable at %s", state_path)

    by_const = {mc.map_const: uid for uid, mc in by_id.items()}
    result = (by_id, by_const)
    _map_registry_cache = (fp, result)
    return result


_MAP_GROUP_RE = re.compile(
    r"MAP_(\w+)\s*=\s*\(\s*(\d+)\s*\|\s*\(\s*(\d+)\s*<<\s*8\s*\)\)"
)


def _get_map_group_table() -> tuple[dict[tuple[int, int], str], list[str]]:
    """``((group, num) -> "MAP_*")`` parsed from the fork's
    ``include/constants/map_groups.h``, plus any degrade-notes. Needed
    because the playtest runner's observed-beats snapshots record GBA
    group/num, not Uranium ids."""
    mvc._load_dotenv()
    pokeemerald = os.environ.get("RPG2GBA_POKEEMERALD")
    if not pokeemerald:
        return {}, ["RPG2GBA_POKEEMERALD not set; observed beats cannot be mapped to this map"]

    path = Path(pokeemerald) / "include" / "constants" / "map_groups.h"
    fp = mvc._file_fingerprint(path)
    global _map_groups_cache
    if _map_groups_cache is not None and _map_groups_cache[0] == fp:
        return _map_groups_cache[1]

    table: dict[tuple[int, int], str] = {}
    notes: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
        for m in _MAP_GROUP_RE.finditer(text):
            name, num, group = m.group(1), int(m.group(2)), int(m.group(3))
            table[(group, num)] = f"MAP_{name}"
    except Exception:
        notes.append(f"map_groups.h unavailable at {path}; observed beats cannot be mapped to this map")

    result = (table, notes)
    _map_groups_cache = (fp, result)
    return result


def _get_switch_names() -> dict[str, str]:
    path = mvc._repo_root() / "reference" / "uranium_switches.json"
    fp = mvc._file_fingerprint(path)
    global _switch_names_cache
    if _switch_names_cache is not None and _switch_names_cache[0] == fp:
        return _switch_names_cache[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    _switch_names_cache = (fp, data)
    return data


def _get_variable_names() -> dict[str, str]:
    path = mvc._repo_root() / "reference" / "uranium_variables.json"
    fp = mvc._file_fingerprint(path)
    global _variable_names_cache
    if _variable_names_cache is not None and _variable_names_cache[0] == fp:
        return _variable_names_cache[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    _variable_names_cache = (fp, data)
    return data


# ---------------------------------------------------------------------------
# Event-structure helpers
# ---------------------------------------------------------------------------


def _is_warp(evt: dict) -> bool:
    return any(
        any(cmd.get("code") == _TRANSFER_PLAYER for cmd in page.get("list", []))
        for page in evt.get("pages", [])
    )


def _page0_trigger(evt: dict) -> int:
    pages = evt.get("pages", [])
    if not pages:
        return 0
    return pages[0].get("trigger", 0) or 0


def _has_conditions(evt: dict) -> bool:
    for page in evt.get("pages", []):
        cond = page.get("condition") or {}
        if (
            cond.get("switch1_valid")
            or cond.get("switch2_valid")
            or cond.get("self_switch_valid")
            or cond.get("variable_valid")
        ):
            return True
    return False


def _find_item_symbol(evt: dict) -> str | None:
    """Lenient scan (mirrors ``extract_trainer_reference``'s style) for a
    ``pbItemBall(::PBItems::X)`` call anywhere in the event's commands."""
    for page in evt.get("pages", []):
        for cmd in page.get("list", []):
            if cmd.get("code") not in (_CONDITIONAL_BRANCH, _SCRIPT, _SCRIPT_CONT):
                continue
            for p in cmd.get("parameters", []):
                if isinstance(p, str):
                    m = _ITEMBALL_RE.search(p)
                    if m:
                        return m.group(1)
    return None


def _classify_kind(evt: dict, *, is_warp: bool, trainer_ref) -> str:
    """Conservative event-kind classifier — 'other' is a fine answer, a wrong
    kind is not. Order: structural signals (warp, trainer, item) before the
    weaker trigger/graphic heuristics (autorun/parallel/sign/npc)."""
    if is_warp:
        return "warp"
    if trainer_ref is not None:
        return "trainer"
    if _find_item_symbol(evt) is not None:
        return "item"

    trig = _page0_trigger(evt)
    if trig == 3:
        return "autorun"
    if trig == 4:
        return "parallel"

    pages = evt.get("pages", [])
    char_name = ""
    if pages:
        char_name = pages[0].get("graphic", {}).get("character_name", "") or ""
    has_dialogue = any(
        cmd.get("code") == _SHOW_TEXT for page in pages for cmd in page.get("list", [])
    )
    if not char_name and has_dialogue and trig in (0, 1):
        return "sign"
    if char_name and trig in (0, 1, 2):
        return "npc"
    return "other"


def _join_dialogue(cmds: list[dict]) -> list[str]:
    """Collapse RMXP's Show-Text (101) + Show-Text-continuation (401) chains
    into whole readable strings, one per text box."""
    out: list[str] = []
    current: str | None = None
    for cmd in cmds:
        code = cmd.get("code")
        params = cmd.get("parameters", [])
        text = params[0] if params and isinstance(params[0], str) else ""
        if code == _SHOW_TEXT:
            if current is not None:
                out.append(current)
            current = text
        elif code == _SHOW_TEXT_CONT and current is not None:
            current += text
        else:
            if current is not None:
                out.append(current)
                current = None
    if current is not None:
        out.append(current)
    return out


def _extract_warp(evt: dict) -> dict | None:
    """Destination of this event's first TRANSFER_PLAYER (code 201) command.
    RMXP params: ``[mode, map_id, x, y, direction, fade]``; mode 0 = literal
    target (the only kind resolvable to a concrete destination)."""
    for page in evt.get("pages", []):
        for cmd in page.get("list", []):
            if cmd.get("code") != _TRANSFER_PLAYER:
                continue
            params = cmd.get("parameters", [])
            if len(params) >= 4 and params[0] == 0:
                return {
                    "map_id": params[1],
                    "x": params[2],
                    "y": params[3],
                    "direction": params[4] if len(params) > 4 else None,
                }
            return {"resolved": False, "raw_parameters": params}
    return None


def _trainer_brief(trainer_ref, join: dict) -> dict | None:
    if trainer_ref is None:
        return None
    class_name = None
    class_const = trainer_ref.trainer_class_constant
    if trainer_ref.trainer_constant:
        rec = join["trainers"].get(trainer_ref.trainer_constant)
        if rec and rec.get("trainer_class"):
            class_const = rec["trainer_class"]
    type_rec = join["types"].get(class_const)
    if type_rec:
        class_name = type_rec.get("name")
    return {
        "trainer_constant": trainer_ref.trainer_constant,
        "display_name": trainer_ref.display_name,
        "class_name": class_name,
        "kind": trainer_ref.kind,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enrich_events(map_id: int, events_list: list) -> list[dict]:
    """Per-event summary for the map payload. Preserves the original seven
    ``_parse_events`` keys byte-compatibly and adds ``kind``, ``trigger``,
    ``label``, ``trainer``, ``has_conditions``. Never raises on a single
    malformed event — logs and falls back to the safest classification."""
    from rpg2gba.conversion_agent import deterministic as det

    ctx = _get_context()
    item_names = _get_item_display_names()
    join = _get_trainer_join()

    result: list[dict] = []
    for evt in events_list:
        pages = evt.get("pages", [])
        is_warp = _is_warp(evt)
        character_name = pages[0].get("graphic", {}).get("character_name", "") if pages else ""

        try:
            trainer_ref = det.extract_trainer_reference(evt, ctx)
        except Exception:
            log.exception(
                "map_viewer_events: extract_trainer_reference failed for map %s event %s",
                map_id, evt.get("id"),
            )
            trainer_ref = None

        trainer_dict = _trainer_brief(trainer_ref, join)
        kind = _classify_kind(evt, is_warp=is_warp, trainer_ref=trainer_ref)

        label = evt.get("name", "") or ""
        if kind == "trainer" and trainer_dict:
            label = trainer_dict["display_name"]
        elif kind == "item":
            symbol = _find_item_symbol(evt)
            if symbol:
                label = item_names.get(symbol, symbol)

        trig = _page0_trigger(evt)
        result.append({
            "id": evt.get("id"),
            "name": evt.get("name", ""),
            "x": evt.get("x"),
            "y": evt.get("y"),
            "npages": len(pages),
            "is_warp": is_warp,
            "character_name": character_name or "",
            "kind": kind,
            "trigger": {"value": trig, "name": _TRIGGER_NAMES.get(trig, "unknown")},
            "label": label,
            "trainer": trainer_dict,
            "has_conditions": _has_conditions(evt),
        })
    return result


def event_detail(map_id: int, event_id: int) -> dict:
    """Full on-demand record for one event. Raises ``KeyError`` if *map_id*
    has no event *event_id*. Genuinely missing/malformed MAP json still fails
    loud (via json.loads / .read_text) — only the OPTIONAL enrichment
    sidecars (switch/variable names, trainer join, staging manifest) degrade
    quietly."""
    maps_dir = mvc._maps_dir()
    path = maps_dir / f"Map{map_id:03d}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    events = doc.get("events", [])
    evt = next((e for e in events if e.get("id") == event_id), None)
    if evt is None:
        raise KeyError(f"map {map_id}: no event {event_id}")

    summary = enrich_events(map_id, [evt])[0]
    join = _get_trainer_join()
    switch_names = _get_switch_names()
    var_names = _get_variable_names()

    notes: list[str] = []
    if not switch_names:
        notes.append("uranium_switches.json unavailable — switch conditions show ids only")
    if not var_names:
        notes.append("uranium_variables.json unavailable — variable conditions show ids only")

    def _cond_switch(cond: dict, n: int) -> dict:
        sid = cond.get(f"switch{n}_id")
        return {
            "valid": bool(cond.get(f"switch{n}_valid", False)),
            "id": sid,
            "name": switch_names.get(str(sid)) if sid is not None else None,
        }

    def _cond_variable(cond: dict) -> dict:
        vid = cond.get("variable_id")
        return {
            "valid": bool(cond.get("variable_valid", False)),
            "id": vid,
            "name": var_names.get(str(vid)) if vid is not None else None,
            "value": cond.get("variable_value"),
        }

    pages_detail = []
    for i, page in enumerate(evt.get("pages", []), start=1):
        cond_raw = page.get("condition", {}) or {}
        graphic = page.get("graphic", {}) or {}
        cmds = page.get("list", [])
        trig = page.get("trigger", 0) or 0
        pages_detail.append({
            "page": i,
            "trigger": {"value": trig, "name": _TRIGGER_NAMES.get(trig, "unknown")},
            "condition": {
                "switch1": _cond_switch(cond_raw, 1),
                "switch2": _cond_switch(cond_raw, 2),
                "self_switch": {
                    "valid": bool(cond_raw.get("self_switch_valid", False)),
                    "ch": cond_raw.get("self_switch_ch"),
                },
                "variable": _cond_variable(cond_raw),
            },
            "graphic": {
                "character_name": graphic.get("character_name", "") or "",
                "direction": graphic.get("direction"),
                "pattern": graphic.get("pattern"),
            },
            "move_type": page.get("move_type"),
            "through": page.get("through"),
            "direction_fix": page.get("direction_fix"),
            "walk_anime": page.get("walk_anime"),
            "priority_type": page.get("always_on_top"),
            "commands": [
                {"code": c.get("code"), "parameters": c.get("parameters", [])} for c in cmds
            ],
            "dialogue": _join_dialogue(cmds),
        })

    trainer_full = None
    if summary["trainer"] is not None:
        trainer_full = dict(summary["trainer"])
        tc = trainer_full["trainer_constant"]
        rec = join["trainers"].get(tc) if tc else None
        if rec is not None:
            trainer_full["trainer_class_constant"] = rec.get("trainer_class")
            trainer_full["party"] = rec.get("party", [])
            trainer_full["items"] = rec.get("items", [])
        else:
            notes.append(
                f"trainer {tc or '(unresolved)'}: no record in trainers.json — "
                "party/items unavailable"
            )
        trainer_full["staged"] = bool(tc) and tc in join["staged"]

    warp = _extract_warp(evt) if summary["is_warp"] else None

    return {
        **summary,
        "pages": pages_detail,
        "trainer": trainer_full if trainer_full is not None else summary["trainer"],
        "warp": warp,
        "notes": notes,
    }


def beat_markers(map_id: int) -> dict:
    """Playtest beats (declared + observed) that belong to this Uranium map.
    Never raises: any missing optional artifact (chapter modules, the
    map-constant registry state, the observed-beats directory, the fork's
    map_groups.h) degrades that half to empty plus a note."""
    from rpg2gba.playtest.chapter import chapter_names, load_chapter

    notes: list[str] = []
    by_id, by_const = _get_map_registry()
    if not by_const:
        notes.append("map-constant registry state unavailable — beats cannot be resolved to a map")

    declared: list[dict] = []
    for name in chapter_names():
        try:
            chapter = load_chapter(name)
        except Exception:
            notes.append(f"chapter module {name!r} failed to load")
            continue
        for beat in chapter.beats:
            if ":" in beat.name:
                # Inherited from a predecessor chapter — that chapter's own
                # module reports it under its own (bare) name; skip here to
                # avoid double-counting.
                continue
            for loc in beat.locations:
                uid = by_const.get(loc.map_constant)
                if uid == map_id:
                    declared.append({
                        "chapter": name,
                        "beat": beat.name,
                        "description": beat.description,
                        "map_constant": loc.map_constant,
                        "x": loc.x,
                        "y": loc.y,
                        "label": loc.label,
                    })

    observed: list[dict] = []
    obs_dir = mvc._output_base() / "playtest" / "observed_beats"
    if not obs_dir.is_dir():
        notes.append(
            f"no observed-beats directory at {obs_dir} — run the playtest runner to populate it"
        )
    else:
        group_table, group_notes = _get_map_group_table()
        notes += group_notes
        for path in sorted(obs_dir.glob("*.json")):
            chapter_name = path.stem
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                notes.append(f"{path} unreadable")
                continue
            for b in data.get("beats", []):
                beat_name = b.get("beat")
                status = b.get("status")
                for phase in ("enter", "exit"):
                    snap = b.get(phase)
                    if not snap:
                        continue
                    mg, mn = snap.get("map_group"), snap.get("map_num")
                    if mg is None or mn is None:
                        continue
                    map_const = group_table.get((mg, mn))
                    uid = by_const.get(map_const) if map_const else None
                    if uid != map_id:
                        continue
                    pos = snap.get("player_pos") or [None, None]
                    observed.append({
                        "chapter": chapter_name,
                        "beat": beat_name,
                        "status": status,
                        "phase": phase,
                        "x": pos[0],
                        "y": pos[1] if len(pos) > 1 else None,
                    })

    return {"map_id": map_id, "declared": declared, "observed": observed, "notes": notes}
