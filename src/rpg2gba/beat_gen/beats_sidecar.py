"""`ChapterPlan` -> `output/beats/CHnn.beats.json` (machine-readable sidecar of
the review doc).

Every field is sourced from the same in-memory plan and helpers the review
renderer uses, so the two artifacts cannot disagree. Deterministic: same plan
and floors -> same bytes.

Schema 1: see `build_sidecar`. `description` is always null (`PlannedBeat`
carries no human description).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from rpg2gba.beat_gen.emit import TEMPLATE_CALLS
from rpg2gba.beat_gen.plan import ChapterPlan, PlannedBeat
from rpg2gba.beat_gen.review import (
    FloorLookup,
    Locator,
    _at,
    _beat_position,
    _order_dependent,
    _pick,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def _json_value(value: Any) -> Any:
    """Tuples -> lists; None/bool/int/float/str as-is; anything else -> str."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (tuple, list)):
        return [_json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    return str(value)


def _location(beat: PlannedBeat, locate: Locator | None) -> tuple[int | None, str | None, list[int] | None]:
    """(map_id, map_name, cell) as the review's Order table shows them: the
    first row's location, or the beat's map for a row-less transit beat."""
    if locate is None:
        return beat.map_id, None, None
    if beat.rows:
        loc = locate.row(beat.rows[0])
        cell = [loc.cell[0], loc.cell[1]] if loc.cell is not None else None
        return loc.map_id, loc.map_name, cell
    return beat.map_id, locate.map_name(beat.map_id), None


def _beat_entry(beat: PlannedBeat, *, floor_lookup: FloorLookup,
                locate: Locator | None) -> dict[str, Any]:
    map_id, map_name, cell = _location(beat, locate)
    pick = _pick(beat)
    assertions: list[dict[str, Any]] = []
    for row_id in beat.rows:
        floor = floor_lookup(row_id)
        for kind in sorted({a.kind for a in floor.assertions}):
            assertions.append({"row": row_id, "kind": kind, "offline": bool(floor.offline_eligible)})
    return {
        "name": beat.name,
        "group": beat.group,
        "template": TEMPLATE_CALLS[beat.template][1],
        "call": {k: _json_value(v) for k, v in beat.kwargs},
        "map_id": map_id,
        "map_name": map_name,
        "cell": cell,
        "pick": None if pick == "-" else pick,
        "description": None,
        "rows": list(beat.rows),
        "assertions": assertions,
    }


def build_sidecar(plan: ChapterPlan, *, floor_lookup: FloorLookup,
                  locate: Locator | None = None) -> dict[str, Any]:
    """The sidecar as a JSON-ready dict."""
    beats = [_beat_entry(b, floor_lookup=floor_lookup, locate=locate) for b in plan.beats]

    odks = sorted(plan.order_dependent, key=lambda k: k.key)
    odk_lines = _order_dependent(plan, floor_lookup=floor_lookup, locate=locate) if odks else []
    order_dependent = [
        {"rows": sorted(odk.writers, key=lambda rid: _beat_position(plan, rid)),
         "text": line.removeprefix("- ")}
        for odk, line in zip(odks, odk_lines, strict=True)]

    refusals = sorted(
        ({"row": r.row_id,
          "text": f"{r.row_id}{_at(r.row_id, locate)}: {r.reason} -- {r.detail}"}
         for r in plan.refusals),
        key=lambda d: (d["row"], d["text"]))

    return {
        "schema": SCHEMA_VERSION,
        "chapter": plan.chapter_id,
        "beats": beats,
        "order_dependent_writes": order_dependent,
        "refusals": refusals,
    }


def render_sidecar(plan: ChapterPlan, *, floor_lookup: FloorLookup,
                   locate: Locator | None = None) -> str:
    """Deterministic JSON text, `indent=2`, one trailing newline."""
    return json.dumps(build_sidecar(plan, floor_lookup=floor_lookup, locate=locate),
                      indent=2, ensure_ascii=False) + "\n"
