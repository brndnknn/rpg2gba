"""Snapshot/diff tool for emitted NPC movement across the whole map corpus.

Built as the review artifact for the RMXP move-route -> pokeemerald
movement_type/route-id conversion change: take one snapshot on the
pre-change code, one on the post-change code, then diff them. The diff
IS the review — every event whose emitted movement_type, route id, or
demotion reason changed, grouped and counted.

Reuses the real Phase-5 wiring (`metadata_wiring.build_object_events`) —
this is NOT a reimplementation of the conversion. It drives the same
per-map object-event build the pipeline uses to write map.json, but only
keeps the in-memory ObjectEvent/drop records; it never writes a map.json
or dispatcher file anywhere.

SNAPSHOT (whole corpus, "full" map-set selector — see map_set.py):
    python3 scripts/route_movement_diff.py snapshot --out /tmp/before.json
    python3 scripts/route_movement_diff.py snapshot --out /tmp/after.json --continue-on-error

    --maps full|slice|1,2,3   (default: full)
    --continue-on-error       log + record each per-map failure and keep going,
                              instead of the default fail-loud abort (CLAUDE.md
                              §4.5 — this is loud-and-recorded, never silent).

DIFF:
    python3 scripts/route_movement_diff.py diff /tmp/before.json /tmp/after.json

Determinism (CLAUDE.md §4.2): map ids and event ids are iterated in sorted
order and the output is `json.dumps(..., indent=2, sort_keys=True)`, so a
snapshot re-run on unchanged inputs is byte-identical. This tool never writes
outside the path given by --out; when that path is unset it defaults under
output/ (gitignored). It also never touches
output/uranium-build/porymap/map_constants.json in place — that shared
pipeline state file is copied into a private scratch location first, so
concurrent pipeline work on the real output/ tree is undisturbed.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from rpg2gba.pipeline import _load_dotenv
from rpg2gba.tileset_converter import map_constants as mc
from rpg2gba.tileset_converter import map_set
from rpg2gba.tileset_converter.metadata_wiring import build_object_events
from rpg2gba.tileset_converter.npc_gfx import MapPassability
from rpg2gba.tileset_converter.route_bytecode import RouteRegistry

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = 1

METADATA_WIRING_LOGGER = "rpg2gba.tileset_converter.metadata_wiring"
_DEMOTED_MSG_MARKER = "movement demoted to static facing"


# --- capture the demotion reason without editing metadata_wiring.py ---------
#
# build_object_events never stores the demotion reason on the ObjectEvent it
# returns (see its dataclass in metadata_wiring.py) — the reason only ever
# exists as an argument to a `logger.warning(...)` call. We read the raw
# LogRecord args (not the formatted string), so this survives future wording
# changes to the message template as long as the (map_id, event_id, reason)
# argument order is kept.

class _DemotedCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.demoted: dict[tuple[int, int], str] = {}

    def reset(self) -> None:
        self.demoted.clear()

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno != logging.WARNING:
            return
        template = record.msg if isinstance(record.msg, str) else ""
        if _DEMOTED_MSG_MARKER not in template:
            return
        uid = eid = None
        reason = None
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            try:
                uid, eid, reason = int(args[0]), int(args[1]), str(args[-1])
            except (TypeError, ValueError):
                uid = eid = None
        if uid is None:
            # Fallback if the call site ever stops passing %-style args.
            msg = record.getMessage()
            m = re.match(r"map (\d+) EV(\d+):", msg)
            start = msg.find("(")
            if m and start != -1 and msg.rstrip().endswith(")"):
                uid, eid = int(m.group(1)), int(m.group(2))
                reason = msg[start + 1 : msg.rstrip().rfind(")")]
        if uid is not None:
            self.demoted[(uid, eid)] = reason


# --- npc gfx: load the raw name -> gfx-constant map without header validation
#
# metadata_wiring.build_object_events only ever does a plain `npc_gfx[name]`
# dict lookup — the header-checked loader (npc_gfx.load_npc_gfx_map) exists to
# additionally prove the constant is real against the fork's generated
# headers (CLAUDE.md §4.7 forward gate). That gate requires
# uranium_event_objects.gen.h, which only exists after running the sprite
# pass, which WRITES into engine/ — off limits for this tool. We don't need
# fork-symbol validation to diff movement_type/route_id, so we load the same
# JSON directly and skip the header check.

def load_npc_gfx_raw(json_path: Path) -> dict[str, str]:
    raw = json.loads(json_path.read_text(encoding="utf-8"))
    return {name: entry["gfx"] for name, entry in raw.items()}


def _err_str(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def build_map_id_list(maps_dir: Path, spec: str) -> list[int]:
    strip_list = REPO_ROOT / "reference" / "strip_list.json"
    return map_set.parse_map_ids(spec, maps_dir, strip_list=strip_list)


def snapshot(
    *,
    out_dir: Path,
    map_spec: str,
    continue_on_error: bool,
) -> dict:
    maps_dir = out_dir / "maps"
    map_ids = sorted(build_map_id_list(maps_dir, map_spec))
    slice_ids = set(map_ids)

    # Copy the shared map-constants state so build_map_constants' unconditional
    # `registry.save()` never touches the real output/ tree other agents share.
    real_state = out_dir / "porymap" / "map_constants.json"
    scratch_dir = Path(tempfile.mkdtemp(prefix="route_movement_diff_"))
    scratch_state = scratch_dir / "map_constants.json"
    if real_state.is_file():
        shutil.copyfile(real_state, scratch_state)

    registry = mc.build_map_constants(
        map_ids,
        map_infos_path=out_dir / "map_infos.json",
        overrides_path=REPO_ROOT / "reference" / "map_name_overrides.json",
        state_path=scratch_state,
        auto_disambiguate=True,  # matches the established full-corpus (Map Walker) convention
    )

    npc_gfx = load_npc_gfx_raw(REPO_ROOT / "reference" / "npc_gfx_map.json")
    tilesets = json.loads((out_dir / "tilesets.json").read_text(encoding="utf-8"))
    route_registry = RouteRegistry()

    capture = _DemotedCapture()
    logging.getLogger(METADATA_WIRING_LOGGER).addHandler(capture)

    entries: list[dict] = []
    failures: list[dict] = []

    try:
        for uid in map_ids:
            try:
                map_json = json.loads(
                    (maps_dir / f"Map{uid:03d}.json").read_text(encoding="utf-8")
                )
                consts = registry.get(uid)
                tileset_id = map_json["tileset_id"]
                try:
                    tileset = tilesets[str(tileset_id)]
                except KeyError:
                    raise KeyError(
                        f"map {uid}: tileset {tileset_id} missing from tilesets.json"
                    ) from None
                passability = MapPassability.from_map(map_json, tileset)

                capture.reset()
                result = build_object_events(
                    map_json,
                    consts,
                    slice_ids,
                    npc_gfx=npc_gfx,
                    passability=passability,
                    route_registry=route_registry,
                )

                for eid_str, pos in sorted(
                    result.local_id_map.items(), key=lambda kv: int(kv[0])
                ):
                    eid = int(eid_str)
                    obj = result.object_events[pos - 1]
                    entries.append(
                        {
                            "map_uid": uid,
                            "event_id": eid,
                            "status": "placed",
                            "movement_type": obj.movement_type,
                            "route_id": obj.route_id,
                            "demoted": capture.demoted.get((uid, eid)),
                            "x": obj.x,
                            "y": obj.y,
                            "drop_reason": None,
                        }
                    )
                for eid, reason in sorted(result.drops, key=lambda p: p[0]):
                    entries.append(
                        {
                            "map_uid": uid,
                            "event_id": eid,
                            "status": "dropped",
                            "movement_type": None,
                            "route_id": None,
                            "demoted": None,
                            "x": None,
                            "y": None,
                            "drop_reason": reason,
                        }
                    )
            except Exception as exc:  # noqa: BLE001 - deliberately broad; see --continue-on-error
                if not continue_on_error:
                    raise
                print(f"FAIL map {uid}: {_err_str(exc)}", file=sys.stderr)
                failures.append({"map_uid": uid, "error": _err_str(exc)})
    finally:
        logging.getLogger(METADATA_WIRING_LOGGER).removeHandler(capture)
        shutil.rmtree(scratch_dir, ignore_errors=True)

    return {
        "schema_version": SCHEMA_VERSION,
        "map_set": map_spec,
        "map_ids": map_ids,
        "entries": entries,
        "failures": failures,
    }


def cmd_snapshot(args: argparse.Namespace) -> int:
    _load_dotenv()
    out_dir = Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"
    data = snapshot(
        out_dir=out_dir,
        map_spec=args.maps,
        continue_on_error=args.continue_on_error,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"snapshot: {len(data['map_ids'])} map(s), {len(data['entries'])} entries, "
        f"{len(data['failures'])} failure(s) -> {out_path}"
    )
    if data["failures"] and not args.continue_on_error:
        return 1
    return 0


# --- diff --------------------------------------------------------------------

_KEY_FIELDS = ("movement_type", "route_id", "demoted")


def _load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_diff(args: argparse.Namespace) -> int:
    before = _load_snapshot(Path(args.before))
    after = _load_snapshot(Path(args.after))

    before_fail = {f["map_uid"] for f in before["failures"]}
    after_fail = {f["map_uid"] for f in after["failures"]}

    before_by_key = {
        (e["map_uid"], e["event_id"]): e
        for e in before["entries"]
        if e["map_uid"] not in before_fail
    }
    after_by_key = {
        (e["map_uid"], e["event_id"]): e
        for e in after["entries"]
        if e["map_uid"] not in after_fail
    }
    # Skip comparing any map that failed in EITHER snapshot — its entry set is
    # incomplete there for reasons unrelated to movement-conversion behavior.
    skip_maps = before_fail | after_fail
    before_by_key = {k: v for k, v in before_by_key.items() if k[0] not in skip_maps}
    after_by_key = {k: v for k, v in after_by_key.items() if k[0] not in skip_maps}

    all_keys = sorted(set(before_by_key) | set(after_by_key))

    changed: list[tuple[tuple[int, int], dict | None, dict | None]] = []
    for key in all_keys:
        b = before_by_key.get(key)
        a = after_by_key.get(key)
        b_tuple = tuple(b[f] if b else None for f in _KEY_FIELDS)
        a_tuple = tuple(a[f] if a else None for f in _KEY_FIELDS)
        if b_tuple != a_tuple:
            changed.append((key, b, a))

    print("=== route_movement diff ===")
    print(
        f"before: {args.before}  ({len(before['map_ids'])} maps, "
        f"{len(before['entries'])} entries, {len(before['failures'])} failures)"
    )
    print(
        f"after:  {args.after}  ({len(after['map_ids'])} maps, "
        f"{len(after['entries'])} entries, {len(after['failures'])} failures)"
    )
    if skip_maps:
        print(
            f"skipped {len(skip_maps)} map(s) that failed in either snapshot "
            f"(excluded from the diff below): {sorted(skip_maps)}"
        )
    print()
    print(f"CHANGED: {len(changed)} event(s) out of {len(all_keys)} compared")
    print()

    transitions: Counter[tuple[str | None, str | None]] = Counter()
    for _key, b, a in changed:
        b_mt = b["movement_type"] if b else None
        a_mt = a["movement_type"] if a else None
        transitions[(b_mt, a_mt)] += 1

    print("-- movement_type transitions (before -> after), by count --")
    for (b_mt, a_mt), n in transitions.most_common():
        print(f"  {n:5}  {b_mt!s:35} -> {a_mt!s}")
    print()

    print("-- per-event detail --")
    for (uid, eid), b, a in changed:
        print(f"Map{uid:03d} EV{eid:03d}:")
        b_status = b["status"] if b else "(absent)"
        a_status = a["status"] if a else "(absent)"
        if b_status != a_status:
            print(f"    status         {b_status} -> {a_status}")
        b_mt = b["movement_type"] if b else None
        a_mt = a["movement_type"] if a else None
        if b_mt != a_mt:
            print(f"    movement_type  {b_mt} -> {a_mt}")
        b_rid = b["route_id"] if b else None
        a_rid = a["route_id"] if a else None
        if b_rid != a_rid:
            print(f"    route_id       {b_rid} -> {a_rid}")
        b_dem = b["demoted"] if b else None
        a_dem = a["demoted"] if a else None
        if b_dem != a_dem:
            print(f"    demoted        {b_dem!r} -> {a_dem!r}")
        b_pos = (b["x"], b["y"]) if b else None
        a_pos = (a["x"], a["y"]) if a else None
        print(f"    pos            {b_pos} -> {a_pos}")
        if b and b.get("drop_reason"):
            print(f"    drop_reason(before) {b['drop_reason']}")
        if a and a.get("drop_reason"):
            print(f"    drop_reason(after)  {a['drop_reason']}")

    failure_only_before = before_fail - after_fail
    failure_only_after = after_fail - before_fail
    if failure_only_before or failure_only_after:
        print()
        print("-- map-level failure changes --")
        by_map_before = {f["map_uid"]: f["error"] for f in before["failures"]}
        by_map_after = {f["map_uid"]: f["error"] for f in after["failures"]}
        for uid in sorted(failure_only_before):
            print(f"  map {uid}: failed in BEFORE only: {by_map_before[uid]}")
        for uid in sorted(failure_only_after):
            print(f"  map {uid}: failed in AFTER only: {by_map_after[uid]}")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot", help="build a movement snapshot over the corpus")
    snap.add_argument("--out", required=True, help="snapshot JSON output path")
    snap.add_argument(
        "--maps", default="full",
        help='map-set spec: "full" (default), "slice", or a comma-separated id list',
    )
    snap.add_argument(
        "--continue-on-error", action="store_true",
        help="log + record each per-map failure and keep going, instead of aborting",
    )
    snap.set_defaults(func=cmd_snapshot)

    diff = sub.add_parser("diff", help="diff two snapshots")
    diff.add_argument("before", help="path to the pre-change snapshot JSON")
    diff.add_argument("after", help="path to the post-change snapshot JSON")
    diff.set_defaults(func=cmd_diff)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
