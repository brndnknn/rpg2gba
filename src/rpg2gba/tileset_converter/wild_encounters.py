"""Phase 5 — wild encounter emission into the fork's `wild_encounters.json`.

Bridges `output/uranium-build/intermediate/wild_encounters.json` (produced by
`src/rpg2gba/pbs_converter/encounters.py`, keyed by Uranium map id) into the
engine's `engine/src/data/wild_encounters.json`
(`engine/tools/wild_encounters/wild_encounters_to_header.py` is the contract:
one `gWildMonHeaders` group, fixed-length slot arrays per field, a `groups`
block on `fishing_mons` declaring which flat-array indices belong to which
rod).

`base_label` scheme
--------------------
Strip the `MAP_` prefix from the map constant, split on `_`, title-case each
segment, join, prefix `g`. `MAP_ROUTE101` -> `gRoute101` (matches the fork's
own committed Route 101 entry verbatim); `MAP_ROUTE_1` -> `gRoute1`. This is
deterministic and collision-free as long as `map_const` values are unique per
Uranium map id (guaranteed upstream by the MapConstantRegistry contract);
`build_encounter_entries` still fails loud if two live map ids ever reduce to
the same label, as a defensive check rather than a silent collision.

Slot-count policy
------------------
`land_mons` / `water_mons` / `rock_smash_mons` slot counts are read from the
fork's own `fields[].encounter_rates` array length (never hardcoded). A
too-short or too-long Uranium list is a real corpus/fork mismatch, not
something to silently pad or truncate (repeating the last entry to fill would
be a silent lie about Uranium's actual table) — both directions fail loud,
naming the map, the field, and expected-vs-actual counts.

`fishing_mons` is shaped differently upstream (three separate rod lists, no
`encounter_rate`) than in the fork (one flat `mons` array + `encounter_rate`,
with rod->index-range membership declared once in the fork's `fields[].groups`
block). We flatten: each rod's list must have exactly as many entries as its
declared index group, and the three rod lists must sum to exactly the fork's
declared flat slot count — any mismatch fails loud. The upstream data carries
no per-map `encounter_rate` for fishing at all, so `DEFAULT_FISHING_ENCOUNTER_RATE`
is substituted (see its docstring for how that number was chosen) — a
documented policy default, not a fact recovered from Uranium data.

`uranium_extra` (Cave/time-of-day/Headbutt/BugContest tables with no fork
host) is dropped here — logged once per map at info level so the loss stays
visible, per CLAUDE.md §4.5. No home is invented for it.

Overlay mechanism
------------------
`upsert_encounters` never writes the committed `engine/src/data/wild_encounters.json`
in place — that file is git-tracked vendored engine source, and every assembler run
would otherwise dirty it. Instead it always reads that committed file as the
read-modify-write *base* and writes the merged result to a sibling overlay file,
`wild_encounters.gen.json` (derived from `fork_encounters_path`, never hardcoded
absolute). This mirrors the layouts/map_groups overlay pattern already used by
`scripts/assemble_pathfinder.py`'s `run_fork_pass`
(`data/layouts/layouts.gen.json`, `data/maps/map_groups.gen.json`).

The engine's `engine/Makefile` (`URANIUM_WILD_ENCOUNTERS`, near line 253) is the
consumer: it prefers `src/data/wild_encounters.gen.json` when present, falling
back to the committed `src/data/wild_encounters.json` when absent — so a repo
with no overlay on disk builds pristine upstream behavior unchanged. The overlay
path is `.gitignore`d.

Because the base is re-read fresh from the committed file on every call (never
from a prior overlay), running this function N times with the same inputs always
produces a byte-identical overlay — entries can never accumulate or double-apply
across runs, and a changed entry on a later run replaces rather than appends.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_GROUP_LABEL = "gWildMonHeaders"
_FLAT_FIELDS = ("land_mons", "water_mons", "rock_smash_mons")
_ROD_LABELS = ("old_rod", "good_rod", "super_rod")

# Fishing per-map encounter_rate: Uranium's rod tables carry no equivalent
# field, so there is nothing to preserve. 20 is the fork's own modal value
# across its committed wild_encounters.json (80 of ~150 fishing_mons entries
# use it, vs. 35/33/3/2 for 30/10/35/60 respectively — surveyed 2026-08-08).
# A reasonable default, not a recovered fact; revisit if Uranium is ever found
# to encode a real per-map fishing success rate somewhere upstream.
DEFAULT_FISHING_ENCOUNTER_RATE = 20


@dataclass(frozen=True)
class EncounterEntry:
    uranium_map_id: int
    map_const: str  # e.g. "MAP_ROUTE_1"
    base_label: str  # e.g. "gUraniumMap33"
    data: dict[str, object]  # fork-shaped body: map/base_label + *_mons fields


def _base_label(map_const: str) -> str:
    if not map_const.startswith("MAP_"):
        raise ValueError(f"map const {map_const!r} does not start with MAP_")
    rest = map_const[len("MAP_") :]
    parts = [p for p in rest.split("_") if p]
    if not parts:
        raise ValueError(f"map const {map_const!r} has no name after MAP_ prefix")
    return "g" + "".join(p[:1].upper() + p[1:].lower() for p in parts)


def _load_fork_group(fork_encounters_path: Path) -> dict:
    raw = json.loads(fork_encounters_path.read_text(encoding="utf-8"))
    for group in raw.get("wild_encounter_groups", []):
        if group.get("label") == _GROUP_LABEL:
            return group
    raise ValueError(
        f"{fork_encounters_path}: no wild_encounter_groups entry with label {_GROUP_LABEL!r}"
    )


def _field_specs(group: dict) -> dict[str, dict]:
    fields: dict[str, dict] = {}
    for field in group.get("fields", []):
        fields[field["type"]] = field
    for required in (*_FLAT_FIELDS, "fishing_mons"):
        if required not in fields:
            raise ValueError(
                f"fork wild_encounters group {_GROUP_LABEL!r} missing a fields[] "
                f"entry for {required!r}"
            )
    return fields


def _validate_species(
    mons: list[dict],
    known_species: Container[str],
    uranium_map_id: int,
    field_label: str,
) -> None:
    for idx, mon in enumerate(mons):
        species = mon.get("species")
        if species not in known_species:
            raise ValueError(
                f"map {uranium_map_id}: {field_label} slot {idx}: unknown species "
                f"{species!r} (not in known_species)"
            )


def _build_flat_field(
    table_entry: dict,
    field_name: str,
    spec: dict,
    known_species: Container[str],
    uranium_map_id: int,
) -> dict[str, object]:
    mons = table_entry.get("mons")
    if mons is None:
        raise ValueError(f"map {uranium_map_id}: {field_name} is missing 'mons'")
    expected = len(spec["encounter_rates"])
    if len(mons) != expected:
        raise ValueError(
            f"map {uranium_map_id}: {field_name} has {len(mons)} slots, fork "
            f"requires exactly {expected} (engine/include/constants/wild_encounter.h)"
        )
    _validate_species(mons, known_species, uranium_map_id, field_name)
    encounter_rate = table_entry.get("encounter_rate")
    if encounter_rate is None:
        raise ValueError(f"map {uranium_map_id}: {field_name} is missing 'encounter_rate'")
    return {
        "encounter_rate": encounter_rate,
        "mons": [dict(m) for m in mons],
    }


def _build_fishing_field(
    table_entry: dict,
    spec: dict,
    known_species: Container[str],
    uranium_map_id: int,
) -> dict[str, object]:
    groups = spec.get("groups")
    if not groups:
        raise ValueError(
            "fork fishing_mons field has no 'groups' block declaring rod slot indices"
        )
    total = len(spec["encounter_rates"])
    flat: list[dict | None] = [None] * total
    running = 0
    for rod in _ROD_LABELS:
        indices = groups.get(rod)
        if indices is None:
            raise ValueError(f"fork fishing_mons groups block is missing {rod!r}")
        rod_mons = table_entry.get(rod, [])
        if len(rod_mons) != len(indices):
            raise ValueError(
                f"map {uranium_map_id}: fishing_mons.{rod} has {len(rod_mons)} "
                f"entries, fork declares {len(indices)} slots at indices {indices}"
            )
        _validate_species(rod_mons, known_species, uranium_map_id, f"fishing_mons.{rod}")
        for slot_idx, mon in zip(indices, rod_mons):
            if flat[slot_idx] is not None:
                raise ValueError(
                    f"fork fishing_mons groups: index {slot_idx} claimed by "
                    "more than one rod"
                )
            flat[slot_idx] = dict(mon)
        running += len(rod_mons)
    if running != total:
        raise ValueError(
            f"map {uranium_map_id}: fishing_mons rod lists sum to {running} "
            f"entries, fork requires exactly {total}"
        )
    missing = [i for i, m in enumerate(flat) if m is None]
    if missing:
        raise ValueError(
            f"map {uranium_map_id}: fishing_mons flat slots {missing} unfilled "
            "after rod placement (fork groups block doesn't cover every index)"
        )
    return {
        "encounter_rate": table_entry.get("encounter_rate", DEFAULT_FISHING_ENCOUNTER_RATE),
        "mons": flat,
    }


def build_encounter_entries(
    encounters_path: Path,
    map_ids: Sequence[int],
    map_consts: Mapping[int, str],
    known_species: Container[str],
    *,
    fork_encounters_path: Path,
) -> list[EncounterEntry]:
    raw = json.loads(encounters_path.read_text(encoding="utf-8"))
    maps = raw.get("maps", {})
    group = _load_fork_group(fork_encounters_path)
    fields = _field_specs(group)

    entries: list[EncounterEntry] = []
    seen_labels: dict[str, int] = {}
    for uid in map_ids:
        table = maps.get(str(uid))
        if table is None:
            logger.debug("map %d: no encounter table (null/absent) — skipped", uid)
            continue

        map_const = map_consts.get(uid)
        if map_const is None:
            raise ValueError(
                f"map {uid}: has encounter data but no MAP_* constant in map_consts"
            )

        body: dict[str, object] = {}
        for field_name in _FLAT_FIELDS:
            if field_name in table:
                body[field_name] = _build_flat_field(
                    table[field_name], field_name, fields[field_name], known_species, uid
                )
        if "fishing_mons" in table:
            body["fishing_mons"] = _build_fishing_field(
                table["fishing_mons"], fields["fishing_mons"], known_species, uid
            )

        extra = table.get("uranium_extra")
        if extra:
            logger.info(
                "map %d: dropped uranium_extra tables (no fork host): %s",
                uid, ", ".join(sorted(extra)),
            )

        base_label = _base_label(map_const)
        if base_label in seen_labels and seen_labels[base_label] != uid:
            raise ValueError(
                f"base_label {base_label!r} collision between map "
                f"{seen_labels[base_label]} and map {uid} (map_const {map_const!r})"
            )
        seen_labels[base_label] = uid

        data: dict[str, object] = {"map": map_const, "base_label": base_label, **body}
        entries.append(EncounterEntry(uid, map_const, base_label, data))

    return entries


def overlay_path(fork_encounters_path: Path) -> Path:
    """The overlay sibling of `fork_encounters_path`: `wild_encounters.json` ->
    `wild_encounters.gen.json`. Matches the `URANIUM_WILD_ENCOUNTERS` wildcard
    hook in `engine/Makefile` (near line 253) — derived, never hardcoded."""
    return fork_encounters_path.with_name(
        fork_encounters_path.stem + ".gen" + fork_encounters_path.suffix
    )


def upsert_encounters(
    fork_encounters_path: Path,
    entries: Sequence[EncounterEntry],
    *,
    out_path: Path | None = None,
) -> int:
    """Read the committed `fork_encounters_path` as the base and write the
    upserted result to `out_path` (default: `overlay_path(fork_encounters_path)`,
    the `wild_encounters.gen.json` sibling `URANIUM_WILD_ENCOUNTERS` looks for).

    The base is always re-read fresh from `fork_encounters_path` — never from a
    prior overlay — so N calls with the same `entries` produce a byte-identical
    overlay and entries never accumulate or double-apply. `fork_encounters_path`
    itself is never written; callers who pass `out_path == fork_encounters_path`
    (asking for the old in-place behavior) get a fail-loud `ValueError`, since
    that would dirty the committed vendored file, which is exactly what the
    overlay exists to avoid.
    """
    if out_path is None:
        out_path = overlay_path(fork_encounters_path)
    elif out_path == fork_encounters_path:
        raise ValueError(
            f"upsert_encounters: out_path must not equal fork_encounters_path "
            f"({fork_encounters_path}) — that would write the committed vendored "
            "file in place; pass a distinct out_path or omit it for the default "
            "overlay location"
        )

    text = fork_encounters_path.read_text(encoding="utf-8")
    had_trailing_newline = text.endswith("\n")
    raw = json.loads(text)

    group = None
    for g in raw.get("wild_encounter_groups", []):
        if g.get("label") == _GROUP_LABEL:
            group = g
            break
    if group is None:
        raise ValueError(
            f"{fork_encounters_path}: no wild_encounter_groups entry with label {_GROUP_LABEL!r}"
        )

    existing = group.setdefault("encounters", [])
    by_map: dict[str, int] = {e["map"]: i for i, e in enumerate(existing)}

    for entry in entries:
        map_const = entry.data["map"]
        if map_const in by_map:
            existing[by_map[map_const]] = dict(entry.data)
        else:
            by_map[map_const] = len(existing)
            existing.append(dict(entry.data))

    out = json.dumps(raw, indent=2, ensure_ascii=False)
    if had_trailing_newline:
        out += "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out, encoding="utf-8")
    return len(entries)
