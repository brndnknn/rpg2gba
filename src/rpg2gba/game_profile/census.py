"""Corpus-wide event-data census -> `include/config/rpg2gba_sizes.gen.h`.

The flag/var region capacities (`RPG2GBA_*_COUNT`) and the trainer capacity were
hand-typed in the engine from a manual census (2026-07-10). This module recomputes
the demand deterministically from the WHOLE deserialized game (every
`maps/Map*.json`, not just built chapters), so the SaveBlock1 layout is identical
for every chapter build, and renders it as a generated header the engine includes
ahead of its own (now `#ifndef`-guarded) literals.

The census reuses the minting logic's own detectors so it cannot drift from it:

* self switches  -- `orchestrator._event_self_switches` (code 123 + page
  conditions) plus `pbSetSelfSwitch(N,"X",v)` cross-event targets, including the
  fused `for i in A..B` loop, exactly the forms the transpiler mints for;
* temp switches  -- `orchestrator._event_temp_switches` plus `s:tsOn?/tsOff?("K")`
  page-condition labels (`metadata_wiring._TEMP_SWITCH_COND_RE`);
* hide flags     -- OVERCOUNT: every event that is the target of a move route
  containing Change Opacity 0. The real detector (`terminal_hide`) is a
  transpile-time trait that needs a per-map transpile; this is a superset, and
  one hide flag is minted at most per event, so it can only err high;
* global switches / vars -- labelled entries of `reference/uranium_switches.json`
  / `uranium_variables.json`, minus the `s:` runtime predicates (never minted).

Private helpers are imported on purpose (same-package-family reuse beats a
second regex that drifts); if one is renamed the import fails loudly.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from rpg2gba.conversion_agent.flag_registry import load_label_tables
from rpg2gba.conversion_agent.orchestrator import (
    _event_self_switches,
    _event_temp_switches,
)
from rpg2gba.conversion_agent.transpiler import (
    _SET_SELF_SWITCH_RE,
    _SS_LOOP_BODY_RE,
    _SS_LOOP_END_RE,
    _SS_LOOP_HEADER_RE,
)
from rpg2gba.map_split.ids import origin_of
from rpg2gba.pbs_converter._c_emit import generated_banner
from rpg2gba.tileset_converter.metadata_wiring import _TEMP_SWITCH_COND_RE

from .settings import REPO_ROOT

logger = logging.getLogger(__name__)

GENERATOR = "rpg2gba.game_profile.census"
HEADER_REL = Path("include/config/rpg2gba_sizes.gen.h")
DEFAULT_SWITCHES_JSON = REPO_ROOT / "reference" / "uranium_switches.json"
DEFAULT_VARIABLES_JSON = REPO_ROOT / "reference" / "uranium_variables.json"

_SCRIPT_CODES = (355, 655)
_CHANGE_OPACITY = 42
_SET_MOVE_ROUTE = 209


@dataclass(frozen=True)
class EventCensus:
    """Raw corpus demand per region (before byte-alignment rounding)."""

    temp_switches: int
    global_switches: int
    self_switches: int
    hide_flags: int
    vars: int
    trainers: int


def default_build_dir() -> Path:
    return Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"


def _script_rows(event: dict) -> list[list[tuple[int, str]]]:
    """Per page: [(code, text)] of the 355/655 rows, in order."""
    pages: list[list[tuple[int, str]]] = []
    for page in event.get("pages", []):
        rows: list[tuple[int, str]] = []
        for cmd in page.get("list", []):
            if cmd.get("code") in _SCRIPT_CODES:
                params = cmd.get("parameters", [])
                if params and isinstance(params[0], str):
                    rows.append((cmd["code"], params[0]))
        pages.append(rows)
    return pages


def _remote_self_switch_targets(rows: list[tuple[int, str]]) -> set[tuple[int, str]]:
    """(target event id, letter) for every `pbSetSelfSwitch` form the transpiler
    mints a flag for: the bare call and the fused `for i in A..B` loop."""
    out: set[tuple[int, str]] = set()
    i = 0
    while i < len(rows):
        text = rows[i][1]
        m = _SET_SELF_SWITCH_RE.match(text)
        if m:
            out.add((int(m.group(1)), m.group(2)))
            i += 1
            continue
        h = _SS_LOOP_HEADER_RE.match(text)
        if h and i + 2 < len(rows):
            b = _SS_LOOP_BODY_RE.match(rows[i + 1][1])
            if b and b.group(1) == h.group(1) and _SS_LOOP_END_RE.match(rows[i + 2][1]):
                for target in range(int(h.group(2)), int(h.group(3)) + 1):
                    out.add((target, b.group(2)))
                i += 3
                continue
        i += 1
    return out


def _hide_targets(event: dict) -> set[int]:
    """Event ids (0 = the scripting event itself) whose opacity a move route sets
    to 0. The player (-1) is excluded.

    Deliberately NOT narrowed by "no later restore": the transpiler's terminal-hide
    rule (`_insert_terminal_hide_removeobject`) works per emitted body, and a
    restore that is later on the page can still sit in another body (measured:
    Map172 EV001 is minted although EV004 restores it later on the same page).
    Any narrower static rule undercounts; this one only errs high."""
    targets: set[int] = set()
    for page in event.get("pages", []):
        for cmd in page.get("list", []):
            if cmd.get("code") != _SET_MOVE_ROUTE:
                continue
            params = cmd.get("parameters", [])
            if len(params) < 2 or not isinstance(params[0], int) or params[0] < 0:
                continue
            route = params[1] if isinstance(params[1], dict) else {}
            for step in route.get("list", []):
                if step.get("code") != _CHANGE_OPACITY:
                    continue
                sp = step.get("parameters", [])
                if sp and sp[0] == 0:
                    targets.add(params[0])
    return targets


def _temp_cond_keys(event: dict, switch_labels: dict[int, str]) -> set[str]:
    """Temp keys read through `s:tsOn?("K")` / `s:tsOff?("K")` page conditions."""
    keys: set[str] = set()
    for page in event.get("pages", []):
        cond = page.get("condition", {})
        for n in (1, 2):
            if not cond.get(f"switch{n}_valid"):
                continue
            label = switch_labels.get(int(cond.get(f"switch{n}_id", 0)))
            m = _TEMP_SWITCH_COND_RE.match(label) if label else None
            if m:
                keys.add(m.group(2).upper())
    return keys


def collect_keys(
    maps: list[dict], switch_labels: dict[int, str]
) -> tuple[set[tuple[int, int, str]], set[tuple[int, int, str]], set[tuple[int, int]]]:
    """(temp keys, self-switch keys, hide keys), all keyed by ORIGIN map id so a
    split map's pieces collapse exactly as the registry does."""
    temp: set[tuple[int, int, str]] = set()
    selfsw: set[tuple[int, int, str]] = set()
    hide: set[tuple[int, int]] = set()
    for m in maps:
        origin = origin_of(int(m["map_id"]))
        for event in m.get("events", []):
            eid = int(event["id"])
            for k in _event_temp_switches(event) | _temp_cond_keys(event, switch_labels):
                temp.add((origin, eid, k))
            for letter in _event_self_switches(event):
                selfsw.add((origin, eid, letter))
            for rows in _script_rows(event):
                for target, letter in _remote_self_switch_targets(rows):
                    selfsw.add((origin, target, letter))
            for t in _hide_targets(event):
                hide.add((origin, eid if t == 0 else t))
    return temp, selfsw, hide


def load_maps(maps_dir: Path) -> list[dict]:
    paths = sorted(Path(maps_dir).glob("Map*.json"))
    if not paths:
        raise FileNotFoundError(f"no Map*.json under {maps_dir} -- run the map deserializer first")
    return [json.loads(p.read_text(encoding="utf-8")) for p in paths]


def count_trainers(trainers_json: Path) -> int:
    data = json.loads(Path(trainers_json).read_text(encoding="utf-8"))
    return len(data["trainers"])


def build_census(
    build_dir: Path,
    switches_json: Path = DEFAULT_SWITCHES_JSON,
    variables_json: Path = DEFAULT_VARIABLES_JSON,
) -> EventCensus:
    switches, variables = load_label_tables(switches_json, variables_json)
    temp, selfsw, hide = collect_keys(load_maps(Path(build_dir) / "maps"), switches)
    return EventCensus(
        temp_switches=len(temp),
        global_switches=sum(1 for v in switches.values() if v and not v.startswith("s:")),
        self_switches=len(selfsw),
        hide_flags=len(hide),
        vars=sum(1 for v in variables.values() if v),
        trainers=count_trainers(Path(build_dir) / "intermediate" / "trainers.json"),
    )


def _ceil8(n: int) -> int:
    return (n + 7) // 8 * 8


def capacities(census: EventCensus) -> dict[str, int]:
    """Region sizes: demand rounded up to a multiple of 8 (flag regions must stay
    byte-aligned), no slack -- overflow fails loud at assembly (`dump_header`).
    Keys match `assemble_pathfinder._load_rpg2gba_capacities`, plus `trainers`."""
    return {
        "tempswitches": _ceil8(census.temp_switches),
        "flags": _ceil8(census.global_switches),
        "selfswitches": _ceil8(census.self_switches + census.hide_flags),
        "vars": _ceil8(census.vars),
        "trainers": census.trainers,
    }


def render_sizes_header(census: EventCensus) -> str:
    cap = capacities(census)
    banner = generated_banner(
        "output/uranium-build/maps/Map*.json + intermediate/trainers.json + "
        "reference/uranium_switches.json + uranium_variables.json",
        GENERATOR,
        timestamp=False,
    )
    lines = [
        banner.rstrip("\n"),
        "#ifndef GUARD_CONFIG_RPG2GBA_SIZES_GEN_H",
        "#define GUARD_CONFIG_RPG2GBA_SIZES_GEN_H",
        "",
        "// Whole-corpus demand (not per chapter, so the save layout never moves between",
        "// chapters): "
        f"{census.temp_switches} temp, {census.global_switches} global, "
        f"{census.self_switches} self + {census.hide_flags} hide (shared region), "
        f"{census.vars} vars, {census.trainers} trainers.",
        "// Flag regions and vars are the demand rounded up to a multiple of 8.",
        f"#define RPG2GBA_TEMP_FLAGS_COUNT       {cap['tempswitches']}",
        f"#define RPG2GBA_GLOBAL_FLAGS_COUNT     {cap['flags']}",
        f"#define RPG2GBA_SELFSWITCH_FLAGS_COUNT {cap['selfswitches']}",
        f"#define RPG2GBA_VARS_COUNT             {cap['vars']}",
        "// Generated trainer ids chain from TRAINER_MAY_PLACEHOLDER (constants/opponents.h).",
        f"#define RPG2GBA_GAME_TRAINERS_COUNT    {cap['trainers']}",
        "",
        "#endif // GUARD_CONFIG_RPG2GBA_SIZES_GEN_H",
        "",
    ]
    return "\n".join(lines)


def install(
    fork: Path,
    build_dir: Path | None = None,
    switches_json: Path = DEFAULT_SWITCHES_JSON,
    variables_json: Path = DEFAULT_VARIABLES_JSON,
) -> Path:
    """Write `<fork>/include/config/rpg2gba_sizes.gen.h`; byte-stable. Returns the
    engine-relative path. `build_dir` defaults to `$RPG2GBA_OUTPUT/uranium-build`."""
    census = build_census(build_dir or default_build_dir(), switches_json, variables_json)
    text = render_sizes_header(census)
    dest = Path(fork) / HEADER_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or dest.read_text(encoding="utf-8") != text:
        dest.write_text(text, encoding="utf-8")
    logger.info(
        "  census: temp %d, global %d, self %d+hide %d, vars %d, trainers %d",
        census.temp_switches, census.global_switches, census.self_switches,
        census.hide_flags, census.vars, census.trainers,
    )
    return HEADER_REL


