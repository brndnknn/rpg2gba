"""S8: stage the pathfinder slice's .pory for fork assembly.

Deterministic transforms, in order, per slice map:
  1. NORMALIZE labels — strip the agent's inconsistent event-name component so
     blocks match S5's un-named ``Map{m}_EV{e}_Page{n}`` references (Option A).
  2. REGENERATE map.json — re-run the S5 wiring with the *real* converted page
     labels (the ``pory_labels`` hook). An event S6 left bodyless (a standing NPC
     / globally-gated cutscene actor with no commands) is then wired as a static
     object (``script "0x0"``) instead of a dangling ``Map{m}_EV{e}_Page1`` ref.
     The S5 *preview* map.json was optimistic (``pory_labels=None``); this run
     supersedes it.
  3. PRUNE orphans — drop blocks for events ``map.json`` does not wire (the
     out-of-slice doors whose ``warp(MAP_URANIUM_<N>)`` the alias header can't
     resolve), with the fail-loud guards in ``tileset_converter.assembly``.
Then, across the whole staged set (normalized+pruned map scripts + dispatchers +
``CommonEvents.pory`` + the ``map.json``s):
  4. EXISTENCE CHECK — every referenced script label must be defined (no
     undefined ``goto``/``call``/``map.json`` script — catches EV074-style gaps),
     and no label may be defined twice (no duplicate symbol).

map.json + dispatchers (regenerable ``porymap/`` output) are rewritten on every
run; ``--write`` controls only whether the transformed ``.pory`` is staged under
``output/uranium-build/staging/scripts/``. The canonical S6 output in
``scripts/`` is never modified (CLAUDE.md §4.4). The checks always run and still
fail loud. The future ``assemble_pathfinder.py`` consumes the staged copies.

Usage:
    python scripts/stage_slice_scripts.py            # regenerate + report + checks
    python scripts/stage_slice_scripts.py --write     # also stage transformed .pory
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from rpg2gba.conversion_agent.flag_registry import FlagRegistry
from rpg2gba.pipeline import _load_dotenv
from rpg2gba.tileset_converter import assembly as asm
from rpg2gba.tileset_converter import map_constants as mc
from rpg2gba.tileset_converter import metadata_wiring as mw
from rpg2gba.tileset_converter import sprite_pass
from rpg2gba.tileset_converter.local_id_remap import (
    _COMMAND_PATTERN,
    _mask_strings_and_comments,
    load_local_id_table,
    remap_pory_object_ids,
)
from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS, WALKABLE_OVERRIDES
from rpg2gba.tileset_converter.npc_gfx import DEFAULT_NPC_GFX_MAP, load_npc_gfx_map
from rpg2gba.tileset_converter.route_bytecode import RouteRegistry
from rpg2gba.tileset_converter.route_table_emit import emit_route_table

DEFAULT_SLICE = tuple(SLICE_MAP_IDS)
ALLOWED_MAPS = {49, 48, 32, 50, 64, 65, 172, 89}
OVERRIDES = Path("reference/map_name_overrides.json")
SWITCHES = Path("reference/uranium_switches.json")
VARIABLES = Path("reference/uranium_variables.json")

# ON_FRAME dispatcher block header: `script <MapDirName>_OnFrame {` at column 0.
_ONFRAME_HEADER_RE = re.compile(r"^script\s+(\S+_OnFrame)\s*\{")
_FLAG_TOKEN_RE = re.compile(r"\bFLAG_[A-Z0-9_]+\b")
_VAR_TOKEN_RE = re.compile(r"\bVAR_[A-Z0-9_]+\b")
_GOTO_TARGET_RE = re.compile(r"\bgoto\(\s*(Map\d+_EV\d+_Page\d+)\s*\)")
_SET_FLAG_WRITE_RE = re.compile(r"\b(?:setflag|clearflag)\(\s*(FLAG_[A-Z0-9_]+)")
_SET_VAR_WRITE_RE = re.compile(r"\b(?:setvar|addvar|subvar|copyvar)\(\s*(VAR_[A-Z0-9_]+)")
# The quiescence guard var the dispatcher itself writes at the end of every
# OnFrame body (`setvar(VAR_TEMP_C, 1)`) — not a page's job to write, so it
# never counts as a guard symbol a page must intersect.
_QUIESCENCE_VAR = "VAR_TEMP_C"


def _find_script_block(text: str, header_re: re.Pattern[str]) -> tuple[str, str] | None:
    """Find the first ``script <label> {`` block matching `header_re` and return
    ``(label, block_text)``. A Poryscript block opens at column 0 and closes at
    the next column-0 ``}`` — nested ``if (...) { ... }`` bodies are always
    indented, so scanning line-by-line for an unindented closing brace finds the
    true end of the block without needing a brace counter."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = header_re.match(line)
        if not m:
            continue
        label = m.group(1)
        for j in range(i + 1, len(lines)):
            if re.match(r"^\}\s*$", lines[j]):
                return label, "\n".join(lines[i:j + 1])
        # Unterminated block (shouldn't happen in well-formed .pory) — return
        # what's left rather than silently dropping it.
        return label, "\n".join(lines[i:])
    return None


def check_onframe_deactivation(
    dispatch_text: str, map_pory_text: str, *, source_name: str
) -> list[str]:
    """Fail-loud guard for the ON_FRAME re-fire bug: every page a map's
    ``<MapDirName>_OnFrame`` dispatcher can `goto` must, in its body, write at
    least one FLAG_*/VAR_* symbol that also appears in the OnFrame guard
    conditions — otherwise the guard never changes and the dispatcher re-fires
    the same page every frame (infinite cutscene loop).

    Returns a list of human-readable violation strings (empty = pass). Pure —
    no I/O; callers pass in already-read dispatch/map .pory text.
    """
    found = _find_script_block(dispatch_text, _ONFRAME_HEADER_RE)
    if found is None:
        return []
    onframe_label, onframe_block = found

    guard_symbols = set(_FLAG_TOKEN_RE.findall(onframe_block))
    guard_symbols.update(_VAR_TOKEN_RE.findall(onframe_block))
    guard_symbols.discard(_QUIESCENCE_VAR)

    violations: list[str] = []
    for label in sorted(set(_GOTO_TARGET_RE.findall(onframe_block))):
        body_header_re = re.compile(rf"^script\s+({re.escape(label)})\s*\{{")
        body = _find_script_block(map_pory_text, body_header_re)
        if body is None:
            violations.append(
                f"{source_name}: {onframe_label} dispatches {label}, but no "
                f"`script {label} {{...}}` body is defined for it"
            )
            continue
        _, body_block = body
        written = set(_SET_FLAG_WRITE_RE.findall(body_block))
        written.update(_SET_VAR_WRITE_RE.findall(body_block))
        if not (written & guard_symbols):
            violations.append(
                f"{source_name}: {label} (dispatched from {onframe_label}) writes "
                f"none of the OnFrame guard symbols {sorted(guard_symbols)} — the "
                f"ON_FRAME page never deactivates itself and will re-fire every frame"
            )
    return violations


def _load_event_traits(out: Path, map_id: int, pory_path: Path) -> dict[int, list[str]]:
    """Load `Map{id:03d}.traits.json` from the same scripts dir as the .pory
    (the transpile driver's fixed-schema sidecar — see metadata_wiring.py). No
    sidecar is a fail-loud data-integrity error (CLAUDE.md §4.5), not a skip:
    the driver is expected to emit one, empty or not, for every map it transpiles."""
    traits_path = out / "scripts" / f"Map{map_id:03d}.traits.json"
    if not traits_path.is_file():
        raise FileNotFoundError(
            f"{traits_path} missing (expected alongside {pory_path.name}) — "
            f"re-run the transpile driver to regenerate the trait sidecar"
        )
    sidecar = json.loads(traits_path.read_text(encoding="utf-8"))
    return {int(eid): traits for eid, traits in sidecar["events"].items()}


def _scan_required_actor_ids(pory_text: str, map_json: dict) -> set[int]:
    """Every RMXP event id targeted by an object-command bare-integer literal
    (applymovement/setobjectxy/addobject/removeobject/turnobject — the same
    `REMAP_COMMANDS`/`_COMMAND_PATTERN` `local_id_remap.py` later rewrites)
    in `pory_text` — the transpiled choreography's OWN idea of which events
    it drives, independent of whether metadata_wiring emitted them at boot
    (findings §3.3/§5: these are the "hidden cutscene actor" candidates).

    Must run on PRE-PRUNE, pre-remap text (the caller's normalized-but-not-
    yet-pruned `.pory`) — the same masking helper `local_id_remap` uses so
    string/comment contents can't be mistaken for a command argument.

    Fails loud on an id that doesn't correspond to any event on the map at
    all (a garbage reference — CLAUDE.md §4.5)."""
    event_ids = {e["id"] for e in map_json["events"]}
    ids: set[int] = set()
    masked = _mask_strings_and_comments(pory_text)
    for m in _COMMAND_PATTERN.finditer(masked):
        candidate = int(m.group(2))
        if candidate not in event_ids:
            raise ValueError(
                f"{m.group(1)}({candidate}): targets event id {candidate}, "
                f"absent from this map's events (garbage reference)"
            )
        ids.add(candidate)
    return ids


def _regenerate_map_json(
    out: Path,
    pory_labels: set[str],
    npc_gfx: dict[str, str],
    local_id_dir: Path,
    event_traits: dict[int, dict[int, list[str]]],
    fork: Path,
    required_actor_ids: dict[int, set[int]],
) -> None:
    """Re-run S5 wiring over the whole slice with the real converted page labels,
    so bodyless events become static objects. Warp pairing needs the full slice,
    so this always covers ``DEFAULT_SLICE`` regardless of the requested subset.

    `npc_gfx` (character_name -> OBJ_EVENT_GFX_*) places visible NPCs; the per-map
    RMXP-id -> compiled-local-id tables are written to `local_id_dir` for the
    staging remap pass below. `event_traits` (Uranium map id -> event id -> trait
    list, from the per-map `.traits.json` sidecars) assigns smashable-rock
    visibility flags. `required_actor_ids` (Uranium map id -> RMXP event ids
    scanned pre-prune off each map's own `.pory`, `_scan_required_actor_ids`)
    are the hidden-cutscene-actor candidates (findings §3.3/§5) forwarded to
    `build_slice_maps`.

    Loads the live flag registry (`out/flag_state.json`) and forwards it to
    `build_slice_maps` so multi-page events gated on a global switch/var get a
    real dispatcher (the names are deterministically resolvable through the
    registry, not just S6-minted — see metadata_wiring.build_page_dispatcher).
    Saves the registry back afterward — REQUIRED, not just tidy: wiring can mint
    a self-switch (or a switch/var name it hadn't seen yet) that the downstream
    assembler's fork-capability gate reads from this same file, and a mint that
    isn't persisted would be silently missing at gate time. Saving is safe to do
    unconditionally — the registry is idempotent (CLAUDE.md §4.2)."""
    reg = mc.build_map_constants(
        list(DEFAULT_SLICE),
        map_infos_path=out / "map_infos.json",
        overrides_path=OVERRIDES,
        state_path=out / "porymap" / "map_constants.json",
    )
    flag_state_path = out / "flag_state.json"
    flag_reg = FlagRegistry.load(flag_state_path, fork_path=fork)
    # load() restores mints + script-switch ids but not labels (labels aren't
    # part of to_state()) — seed them so build_page_dispatcher's script-switch
    # temp-switch carve-out (label_for_switch) can resolve here, not just in
    # unit tests that pre_seed a fresh registry.
    flag_reg.seed_labels(SWITCHES, VARIABLES)
    # One RouteRegistry across the whole slice: build_slice_maps interns each
    # custom-route object's bytecode (→ its map.json trainer_sight_or_berry_tree_id
    # route id), then emit_route_table writes the matching engine gen.h table.
    # Single instance, two consumers — they agree by construction (no cross-pass
    # id rebuild). See reference/guides/custom_route_interpreter.md.
    route_reg = RouteRegistry()
    mw.build_slice_maps(
        list(DEFAULT_SLICE),
        maps_dir=out / "maps",
        registry=reg,
        metadata_path=out / "intermediate" / "map_metadata.json",
        out_dir=out / "porymap" / "maps",
        dispatcher_dir=out / "porymap" / "dispatch",
        pory_labels=pory_labels,
        npc_gfx=npc_gfx,
        local_id_dir=local_id_dir,
        event_traits=event_traits,
        flag_registry=flag_reg,
        tilesets_path=out / "tilesets.json",
        walkable_overrides=WALKABLE_OVERRIDES,
        route_registry=route_reg,
        required_actor_ids=required_actor_ids,
    )
    flag_reg.save(flag_state_path)
    # Always write (empty → stub) so the engine #include resolves even with no
    # custom routes; keyed to the ids build_slice_maps just stamped into map.json.
    emit_route_table(route_reg, fork)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("maps", nargs="*", type=int, default=list(DEFAULT_SLICE),
                    help=f"Uranium map ids to stage (default: the slice {DEFAULT_SLICE}).")
    ap.add_argument("--write", action="store_true",
                    help="stage transformed .pory under output/.../staging/scripts/.")
    args = ap.parse_args()

    _load_dotenv()
    out = Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"
    consts = json.loads((out / "porymap" / "map_constants.json").read_text(encoding="utf-8"))
    staging = out / "staging" / "scripts"
    local_id_dir = out / "staging" / "local_ids"

    fork_path = os.environ.get("RPG2GBA_POKEEMERALD")
    if not fork_path:
        print("RPG2GBA_POKEEMERALD not set", file=sys.stderr)
        return 1
    fork = Path(fork_path)

    # NPC sprites first: populate engine/include/constants/uranium_event_objects.gen.h
    # so load_npc_gfx_map can validate every OBJ_EVENT_GFX_URANIUM_* against a real
    # #define (idempotent — assemble_pathfinder re-runs it before make).
    sprite_pass.run_sprite_pass(fork)
    npc_gfx = load_npc_gfx_map(
        DEFAULT_NPC_GFX_MAP,
        [
            fork / "include" / "constants" / "event_objects.h",
            fork / "include" / "constants" / "uranium_event_objects.gen.h",
        ],
    )

    # --- pass 1: normalize every slice .pory, collect the canonical (un-named)
    # page-label definition set the regenerated map.json must agree with ---
    normalized: dict[int, asm.NormalizeResult] = {}
    pory_labels: set[str] = set()
    event_traits: dict[int, dict[int, list[str]]] = {}
    for map_id in DEFAULT_SLICE:
        pory_path = out / "scripts" / f"Map{map_id:03d}.pory"
        if consts.get(str(map_id)) is None or not pory_path.is_file():
            continue
        norm = asm.normalize_labels(pory_path.read_text(encoding="utf-8"))
        normalized[map_id] = norm
        pory_labels.update(asm.script_definitions(norm.text))
        event_traits[map_id] = _load_event_traits(out, map_id, pory_path)

    # --- scan each map's own PRE-PRUNE .pory for object-command targets (the
    # hidden-cutscene-actor candidates — findings §3.3/§5) BEFORE the S5
    # rewiring pass runs, since build_object_events needs the full set up
    # front to decide which of them lack a boot-active page ---
    required_actor_ids: dict[int, set[int]] = {}
    for map_id, norm in normalized.items():
        map_json_path = out / "maps" / f"Map{map_id:03d}.json"
        map_json_raw = json.loads(map_json_path.read_text(encoding="utf-8"))
        required_actor_ids[map_id] = _scan_required_actor_ids(norm.text, map_json_raw)

    # --- regenerate map.json with the real labels (the S5 stub hook) +
    # per-map local-id tables (RMXP id -> compiled object-event local id) ---
    _regenerate_map_json(
        out, pory_labels, npc_gfx, local_id_dir, event_traits, fork, required_actor_ids,
    )

    # --- pass 2: prune + report per requested map (reads the fresh map.json) ---
    staged: dict[str, str] = {}   # filename -> transformed text (for the staged-set checks)
    map_jsons: list[dict] = []
    onframe_violations: list[str] = []

    for map_id in args.maps:
        entry = consts.get(str(map_id))
        if entry is None or map_id not in normalized:
            print(f"Map{map_id:03d}: no map_constants entry or .pory — skipped", file=sys.stderr)
            continue
        map_json_path = out / "porymap" / "maps" / entry["dir_name"] / "map.json"
        if not map_json_path.is_file():
            print(f"Map{map_id:03d}: missing map.json — skipped", file=sys.stderr)
            continue

        map_json = json.loads(map_json_path.read_text(encoding="utf-8"))
        map_jsons.append(map_json)

        norm = normalized[map_id]
        # The dispatcher .pory (page dispatchers + the unified mapscripts
        # block) may reference page bodies of events map.json wires nowhere —
        # an ON_FRAME autorun entry for a blank-graphic/opacity-0 event, for
        # example — so those events must survive the prune too.
        live_ids = asm.live_event_ids(map_json)
        disp_path = out / "porymap" / "dispatch" / f"Map{map_id:03d}_dispatch.pory"
        disp_text = disp_path.read_text(encoding="utf-8") if disp_path.is_file() else None
        if disp_text is not None:
            for ref in asm.script_reference_labels(disp_text):
                m = re.match(rf"Map{map_id:03d}_EV(\d+)_", ref)
                if m:
                    live_ids.add(int(m.group(1)))
        result = asm.prune_orphan_blocks(
            norm.text, live_ids, allowed_uranium_maps=ALLOWED_MAPS
        )

        # Remap RMXP event ids in object-targeting commands (applymovement/
        # setobjectxy/addobject/removeobject/turnobject) to compiled local ids.
        # EXACTLY ONCE, on fresh (pruned) transpiler output — this is the sole
        # application site; assemble_pathfinder must not remap again.
        table = load_local_id_table(local_id_dir / f"Map{map_id:03d}.json")
        remap = remap_pory_object_ids(
            result.text, table, source_name=f"Map{map_id:03d}.pory"
        )
        staged[f"Map{map_id:03d}.pory"] = remap.text

        # ON_FRAME re-fire guard: run against the final staged text (post
        # normalize/prune/remap, and — since it's read from out/scripts/ where
        # transpile_driver already applied hand_conversions/ overlays, e.g.
        # Map032_EV009.pory — post-overlay too) so a hand-authored page is
        # checked the same as a transpiled one.
        if disp_text is not None:
            onframe_violations.extend(
                check_onframe_deactivation(
                    disp_text, remap.text, source_name=f"Map{map_id:03d}.pory"
                )
            )

        statics = sum(1 for o in map_json.get("object_events", []) if o.get("script") == "0x0")
        print(f"Map{map_id:03d} ({entry['dir_name']}): "
              f"normalized {len(norm.renames)} label(s), "
              f"kept {len(result.kept)}, dropped {len(result.dropped)} orphan(s), "
              f"{statics} static object(s), "
              f"{len(remap.replacements)} local-id remap(s), "
              f"{len(remap.warnings)} unmapped")
        for old, new in sorted(norm.renames.items()):
            print(f"    rename  {old} -> {new}")
        for label in result.dropped:
            print(f"    drop    {label}")
        for line, command, old_id, new_id in remap.replacements:
            print(f"    remap   line {line}: {command}({old_id}) -> {new_id}")
        for line, command, old_id in remap.warnings:
            print(f"    remap   WARN line {line}: {command}({old_id}) not in local-id table")

    # --- staged-set checks (read-only; dispatchers + CommonEvents define labels
    # the map scripts reference, so they must be in the defined set) ---
    aux_texts: list[str] = []
    disp_dir = out / "porymap" / "dispatch"
    if disp_dir.is_dir():
        aux_texts += [f.read_text(encoding="utf-8") for f in sorted(disp_dir.glob("*.pory"))]
    ce = out / "scripts" / "CommonEvents.pory"
    if ce.is_file():
        aux_texts.append(ce.read_text(encoding="utf-8"))

    all_texts = list(staged.values()) + aux_texts
    dangling = asm.find_dangling_references(all_texts, map_jsons)
    duplicates = asm.find_duplicate_definitions(all_texts)

    print()
    if dangling or duplicates:
        if dangling:
            print(f"FAIL: {len(dangling)} undefined script reference(s):", file=sys.stderr)
            for ref in sorted(dangling):
                print(f"    {ref}", file=sys.stderr)
        if duplicates:
            print(f"FAIL: {len(duplicates)} duplicate definition(s):", file=sys.stderr)
            for label, n in sorted(duplicates.items()):
                print(f"    {label}  x{n}", file=sys.stderr)
        return 1
    print("existence check: every referenced script label is defined exactly once.")

    if onframe_violations:
        raise RuntimeError(
            f"{len(onframe_violations)} ON_FRAME deactivation violation(s):\n"
            + "\n".join(f"    {v}" for v in onframe_violations)
        )
    print("onframe check: every ON_FRAME-dispatched page deactivates its own guard.")

    if args.write:
        staging.mkdir(parents=True, exist_ok=True)
        for name, text in staged.items():
            (staging / name).write_text(text, encoding="utf-8")
            print(f"staged -> {staging / name}")
    else:
        print("(dry-run — re-run with --write to stage the transformed .pory)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
