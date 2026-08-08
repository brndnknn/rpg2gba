"""Thin driver around the deterministic event->Poryscript transpiler (design D5).

No checkpoints, no memo: a full deterministic pass over the corpus re-runs in
seconds, so the driver just does idempotent full re-runs instead of tracking
resumable state. For each event it tries the idiom-collapse layer
(``deterministic.try_deterministic``) first — a whole-event classifier match —
and falls back to the general transpiler (``transpiler.transpile_event``) only
when no classifier claims the event. Every map's output passes the conversion-
time fork-index gate (design D4, ``fork_index.verify_script``) before it is
written; a violation is our bug and aborts the run loud (CLAUDE.md §4.5, §4.7).

Usage:
    python -m rpg2gba.conversion_agent.transpile_driver run --maps slice
    python -m rpg2gba.conversion_agent.transpile_driver run --maps full --dry-run
    python -m rpg2gba.conversion_agent.transpile_driver run --maps 49,48,32
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import click

from rpg2gba.conversion_agent import deterministic, fork_index, hand_overrides, transpiler
from rpg2gba.conversion_agent.flag_registry import FlagRegistry
from rpg2gba.pbs_converter._id_map import IdMap
from rpg2gba.tileset_converter import stairs
from rpg2gba.tileset_converter.map_set import resolve_map_ids

logger = logging.getLogger(__name__)

_TOP_CLUSTERS = 10
_CLUSTER_PREFIX_LEN = 60


# -- per-map transpile ---------------------------------------------------------


def _det_queue_entry(
    entry: dict, *, map_id: int, event: dict
) -> dict:
    """Normalize a classifier's partial unhandled dict into the driver's
    QueueEntry-shaped row, filling in the fields DetResult entries omit."""
    return {
        "map_id": entry.get("map_id", map_id),
        "event_id": entry.get("event_id", event.get("id")),
        "event_name": entry.get("event_name", event.get("name", "")),
        "page": entry.get("page", 1),
        "line": entry.get("line", 0),
        "command_code": entry.get("command_code", 0),
        "description": entry.get("description", ""),
        "reason": entry.get("reason", "classifier-flagged"),
    }


def _canonicalize_labels(script: str, map_id: int, event: dict) -> str:
    """Rewrite a classifier's name-based labels to the canonical id-based form.

    ``deterministic._page_label`` keys blocks by event NAME — two same-named
    events on one map (Map002 has two "Receptionist TRADE") collide into
    duplicate script symbols. The transpiler already emits the canonical
    ``Map{m:03d}_EV{e:03d}_Page{n}`` (= ``metadata_wiring.page_label``); this
    brings the classifier layer onto the same scheme without touching the
    classifiers or their golden tests. Definition and references move
    together (whole-text replace)."""
    for page_no in range(1, len(event.get("pages", [])) + 1):
        old = deterministic._page_label(map_id, event, page_no)
        new = transpiler._page_label(map_id, event, page_no)
        if old != new:
            script = script.replace(old, new)
    old_mart = f"Map{int(map_id):03d}_{deterministic._label_name(event.get('name', ''))}_Mart"
    new_mart = f"Map{int(map_id):03d}_EV{int(event.get('id', 0)):03d}_Mart"
    if old_mart != new_mart:
        script = script.replace(old_mart, new_mart)
    return script


_SCRIPT_LABEL_RE = re.compile(r"^script\s+(\S+)\s*\{", re.MULTILINE)


def _defined_script_labels(pory_text: str) -> set[str]:
    """Every top-level ``script <label> {`` block label defined in `pory_text`."""
    return set(_SCRIPT_LABEL_RE.findall(pory_text))


def _record_collapsed_pages(
    map_id: int, event: dict, canonical_script: str, ctx: transpiler.TranspileContext
) -> None:
    """Mark an event the idiom-collapse classifier (``deterministic.
    try_deterministic``) claimed as ``collapsed_pages`` when it folded a
    multi-page event into a single block that defines SOME but not ALL of the
    event's canonical page labels (e.g. the trainer-battle classifier folding
    a line-of-sight trainer's pre-battle and post-battle pages into one
    ``trainerbattle_single(...)`` block — only page 1 is emitted, on
    purpose). ``metadata_wiring._resolve_script`` reads this trait to skip
    building a dispatcher for such an event, instead resolving straight to
    the page-1 label.

    Not recorded when every page label is defined (a full, ordinary
    classifier conversion — no gap to explain) or when only one page exists
    (nothing to collapse).
    """
    pages = event.get("pages", [])
    if len(pages) < 2:
        return
    expected = {
        transpiler._page_label(map_id, event, page_no)
        for page_no in range(1, len(pages) + 1)
    }
    defined = _defined_script_labels(canonical_script) & expected
    if defined and defined != expected:
        eid = event.get("id")
        ctx.traits.setdefault((map_id, eid), set()).add("collapsed_pages")


def transpile_map(
    map_id: int,
    map_json: dict,
    ctx: transpiler.TranspileContext,
    det_ctx: deterministic.Context | None,
    overrides: dict[tuple[int, int], hand_overrides.HandOverride] | None = None,
) -> tuple[str, list[dict]]:
    """Transpile every event on one map; return (pory_text, queue_entries).

    Tries the idiom-collapse classifiers first (cheaper, hand-validated
    output); falls back to the general command-by-command transpiler. An
    event keyed in ``overrides`` skips both entirely: its hand-authored text
    is spliced in verbatim (already in the canonical label scheme — no
    ``_canonicalize_labels`` rewrite) and it contributes zero queue entries.
    ``overrides`` defaults to none so existing callers (``oracle_harvest.py``,
    tests) are unaffected.
    """
    overrides = overrides or {}
    event_texts: list[str] = []
    queue_entries: list[dict] = []
    seen_event_ids: set[int] = set()
    # Diagonal-stair "player touch" events (RGSS 111 facing-conditional +
    # forced diagonal move route): the fork's native MB_SIDEWAYS_STAIRS_*
    # metatile behavior performs the step with no script at all (the
    # approved fix — see rpg2gba.tileset_converter.stairs). Detected once per
    # map from the shape of the event, never re-implemented here.
    stair_ids = stairs.stair_event_ids(map_json)
    stairs_skipped = 0

    for event in map_json.get("events", []):
        event_id = event.get("id")
        seen_event_ids.add(event_id)

        if event_id in stair_ids:
            # No .pory block, no queue entry — the tileset layer now owns
            # this cell's behavior entirely. Not silent: logged below and
            # recorded on ctx for the corpus-run summary (CLAUDE.md §4.5).
            stairs_skipped += 1
            ctx.skipped_stair_events.append({
                "map_id": map_id,
                "event_id": event_id,
                "event_name": event.get("name", ""),
                "reason": "native-sideways-stairs",
            })
            continue

        override = overrides.get((map_id, event_id))
        if override is not None:
            event_texts.append(override.text)
            continue

        if transpiler.resolve_native_object_template(map_id, event, ctx):
            # Item ball / berry tree: the native object-template fields (see
            # Map{id:03d}.template_fields.json) are the whole story — no
            # .pory block, no queue entry, same disposition as the
            # diagonal-stair skip above. Recognized BEFORE the classifiers
            # so deterministic.classify_ground_item (which already lowers
            # bare pbItemBall to giveitem/setflag) never sees these events.
            continue

        det = deterministic.try_deterministic(map_id, event, det_ctx)
        if det is not None:
            canonical_script = _canonicalize_labels(det.script, map_id, event)
            event_texts.append(canonical_script)
            queue_entries.extend(
                _det_queue_entry(entry, map_id=map_id, event=event)
                for entry in det.unhandled
            )
            _record_collapsed_pages(map_id, event, canonical_script, ctx)
            continue
        transpiled = transpiler.transpile_event(map_id, event, ctx)
        event_texts.append(transpiled.text)
        queue_entries.extend(e.to_json() for e in transpiled.unhandled)

    if stairs_skipped:
        logger.info(
            "Map%03d: skipped %d diagonal-stair event(s) (native-sideways-stairs, "
            "see tileset_converter.stairs)",
            map_id, stairs_skipped,
        )

    stale = sorted(
        (m, e) for (m, e) in overrides if m == map_id and e not in seen_event_ids
    )
    if stale:
        names = ", ".join(f"Map{m:03d}_EV{e:03d}" for m, e in stale)
        raise ValueError(
            f"transpile_map: hand override(s) for {names} reference event id(s) "
            f"not present on Map{map_id:03d} — a stale override is a bug, fix or "
            f"remove the .pory file, don't skip it"
        )

    pory_text = "\n\n".join(text for text in event_texts if text)
    return pory_text, queue_entries


# -- trait sidecar (rock-smash respawn-flag signal, task-shared contract) ------


def _map_traits_payload(ctx: transpiler.TranspileContext, map_id: int) -> dict:
    """Build the ``Map{id:03d}.traits.json`` sidecar payload for one map.

    Fixed schema — a contract with a downstream consumer (metadata_wiring.py
    / stage_slice_scripts.py, owned by a different agent) that assigns
    FLAG_TEMP_* respawn flags to smashable-rock object events:
    ``{"events": {"<event_id>": [<trait>, ...]}}``. Only events with >=1
    trait appear; values are sorted. An empty map still returns
    ``{"events": {}}`` — the caller always writes the sidecar.
    """
    events: dict[str, list[str]] = {
        str(event_id): sorted(traits)
        for (m, event_id), traits in ctx.traits.items()
        if m == map_id and traits
    }
    return {"events": events}


def _write_traits_sidecar(
    scripts_dir: Path, map_id: int, ctx: transpiler.TranspileContext
) -> None:
    """Write ``Map{id:03d}.traits.json`` next to the map's ``.pory`` file,
    always (even with no traits) — see ``_map_traits_payload``."""
    path = scripts_dir / f"Map{map_id:03d}.traits.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(_map_traits_payload(ctx, map_id), f, indent=2, sort_keys=True)
        f.write("\n")


# -- native object-template sidecar (item balls / berry trees) ----------------


def _map_template_fields_payload(ctx: transpiler.TranspileContext, map_id: int) -> dict:
    """Build the ``Map{id:03d}.template_fields.json`` sidecar payload for one
    map. Fixed schema — a contract with a downstream consumer
    (metadata_wiring.py, owned by a different agent) that turns each row
    into pokeemerald object-template fields: ``{"events": {"<event_id>":
    {"kind": ..., ...}}}``. Written unconditionally, even when empty (the
    consumer treats a missing file as fail-loud, same as the traits
    sidecar)."""
    events: dict[str, dict] = {
        str(event_id): payload
        for (m, event_id), payload in ctx.template_fields.items()
        if m == map_id
    }
    return {"events": events}


def _write_template_fields_sidecar(
    scripts_dir: Path, map_id: int, ctx: transpiler.TranspileContext
) -> None:
    """Write ``Map{id:03d}.template_fields.json`` next to the map's ``.pory``
    file, always (even with no matches) — see ``_map_template_fields_payload``.
    ``sort_keys=True`` + a trailing newline for byte-identical re-runs
    (CLAUDE.md §4.2 idempotence)."""
    path = scripts_dir / f"Map{map_id:03d}.template_fields.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(_map_template_fields_payload(ctx, map_id), f, indent=2, sort_keys=True)
        f.write("\n")


# -- species staging glue (W5 part B: pbHasSpecies? -> checkspecies) -----------


def _load_species_id_map(reference_dir: Path) -> dict[str, str]:
    """Uranium internal species name -> SPECIES_* constant, from the single
    source of truth (CLAUDE.md §4.3) — never re-derived by string-munging."""
    id_map = IdMap.load(reference_dir / "uranium_id_map.json")
    return dict(id_map.by_category["species"])


def _load_item_id_map(reference_dir: Path) -> dict[str, str]:
    """Uranium internal item/berry symbol -> ITEM_* constant, from the same
    single source of truth (CLAUDE.md §4.3), for the item-ball/berry-tree
    native object-template idioms only (see ``TranspileContext.item_id_map``
    docstring — the generic give-item idiom uses a different table)."""
    id_map = IdMap.load(reference_dir / "uranium_id_map.json")
    return dict(id_map.by_category["items"])


def _load_staged_species(species_manifest_path: Path) -> frozenset[str]:
    """SPECIES_* constants for species actually staged into the fork.

    Mirrors ``fork_index.registry_extra_symbols``'s species handling: a
    missing manifest (species converter never run) yields no staged species,
    never an error; a present-but-malformed manifest fails loud (KeyError),
    same discipline as the gate.
    """
    if not species_manifest_path.is_file():
        return frozenset()
    manifest = json.loads(species_manifest_path.read_text(encoding="utf-8"))
    return frozenset(entry["species_constant"] for entry in manifest["species"])


# -- registry glue for the gate -------------------------------------------------


def _registry_minted_names(registry: FlagRegistry) -> set[str]:
    """All FLAG_*/VAR_* names the live registry has assigned so far (preseed +
    this run's mints) — read straight off the in-memory object so a mint made
    mid-run is visible before anything is saved back to disk."""
    state = registry.to_state()
    names: set[str] = set()
    for category in ("switches", "variables", "self_switches", "temp_switches", "hide_flags"):
        names |= set(state[category].values())
    return names


# -- transpile_unhandled.jsonl merge (corpus-wide aggregate, CLAUDE.md §4.2) ---


def _load_existing_queue(queue_path: Path) -> list[dict]:
    """Read the existing ``transpile_unhandled.jsonl``, one JSON object per
    line, tolerating a not-yet-existing file (first run).

    Fails loud (CLAUDE.md §4.5) on a malformed line instead of silently
    starting fresh — silently starting fresh is exactly the truncation bug
    this merge exists to prevent, and a corrupt file is a signal something
    already went wrong, not a green light to discard the rest of the corpus.
    """
    if not queue_path.is_file():
        return []
    entries: list[dict] = []
    for line_no, line in enumerate(queue_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"transpile_driver: {queue_path} line {line_no} is not valid "
                f"JSON ({exc}) — refusing to silently start fresh (that would "
                f"be the same data-loss bug this merge exists to prevent); fix "
                f"or remove the bad line by hand and re-run"
            ) from exc
    return entries


def _queue_bucket(entry: dict) -> int | None:
    """The unit of replacement for a partial run: a map id, or ``None`` for
    common-event entries. ``QueueEntry.to_json`` (transpiler.py) omits
    ``map_id`` entirely for common-event rows in favor of
    ``common_event_id``, since a common event isn't owned by any one map —
    so those rows collapse into a single ``None`` bucket that a run only
    touches when it actually recomputed common events this pass."""
    return entry.get("map_id")


def _queue_sort_key(entry: dict) -> tuple:
    """Deterministic, stable ordering independent of insertion order
    (CLAUDE.md §4.2) — a partial re-run that changes nothing semantically
    must not reshuffle unrelated lines. Grouped by map_id first (``None`` /
    common-event rows sort after every real map), then by common_event_id
    (a common-event row's equivalent of map_id), then event_id, then the
    record's own position fields (page, line, command_code), with
    description as a last-resort tiebreak for the rare case two rows are
    identical through command_code but differ in text."""
    map_id = entry.get("map_id")
    common_event_id = entry.get("common_event_id")
    event_id = entry.get("event_id")
    return (
        map_id is None,
        map_id if map_id is not None else 0,
        common_event_id is None,
        common_event_id if common_event_id is not None else 0,
        event_id is None,
        event_id if event_id is not None else 0,
        entry.get("page", 0),
        entry.get("line", 0),
        entry.get("command_code", 0),
        str(entry.get("description", "")),
    )


def _merge_queue(
    queue_path: Path, touched_buckets: set[int | None], new_entries: list[dict]
) -> list[dict]:
    """Merge this run's queue entries into the existing on-disk file,
    replacing only the buckets (maps, or the common-events bucket) this run
    actually touched — every other map's entries survive untouched
    (CLAUDE.md §4.2). ``new_entries`` must already be limited to
    ``touched_buckets``; callers only pass what this run computed."""
    existing = _load_existing_queue(queue_path)
    preserved = [e for e in existing if _queue_bucket(e) not in touched_buckets]
    merged = preserved + new_entries
    merged.sort(key=_queue_sort_key)
    return merged


# -- corpus run loop -------------------------------------------------------------


def _ce_strips(strip_list_path: Path) -> dict[int, dict]:
    """Whole-CE STRIP decisions from the source of truth (CLAUDE.md §4.3)."""
    if not strip_list_path.is_file():
        return {}
    data = json.loads(strip_list_path.read_text(encoding="utf-8"))
    return {int(e["id"]): e for e in data.get("common_events", [])}


def transpile_common_events(
    common_events_path: Path,
    ctx: transpiler.TranspileContext,
    strip_list_path: Path = Path("reference") / "strip_list.json",
) -> tuple[str, list[dict]]:
    """Transpile every command-carrying common event into one .pory text.

    Command-less CEs (placeholders) emit nothing — a map-event `call` to one
    would dangle, but no map event calls an empty CE (they carry no commands
    to call from). CEs on the strip list emit their stub message instead of
    their content (fail-loud on an expect_name mismatch — re-export
    renumbering guard).
    """
    ces = json.loads(common_events_path.read_text(encoding="utf-8"))
    strips = _ce_strips(strip_list_path)
    texts: list[str] = []
    queue_entries: list[dict] = []
    for ce in ces:
        ce_id = int(ce.get("id", 0))
        strip = strips.get(ce_id)
        if strip is not None:
            if ce.get("name") != strip["expect_name"]:
                raise RuntimeError(
                    f"strip_list expects CE {ce_id} named {strip['expect_name']!r}, "
                    f"found {ce.get('name')!r} — re-export renumbering? Fix the "
                    f"strip list, don't guess."
                )
            stub = strip["stub_message"]
            texts.append(
                f"# STRIPPED: {strip['feature']} (strip_list.json)\n"
                f"script CommonEvent_{ce_id:03d} {{\n"
                f'    msgbox("{stub}")\n'
                f"    return\n"
                f"}}"
            )
            continue
        if not any(cmd.get("code") for cmd in ce.get("list", [])):
            continue
        result = transpiler.transpile_common_event(ce, ctx)
        texts.append(result.text)
        queue_entries.extend(e.to_json() for e in result.unhandled)
    return "\n\n".join(texts), queue_entries


def transpile_corpus(
    map_ids: list[int],
    *,
    maps_dir: Path,
    out_dir: Path,
    flag_state_path: Path,
    map_constants_path: Path,
    species_manifest_path: Path | None = None,
    trainer_manifest_path: Path | None = None,
    write: bool = True,
    common_events: bool = True,
    overrides_dir: Path | None = None,
) -> dict:
    """Transpile a set of maps, gate every one, and (optionally) write output.

    Hand overrides (``hand_overrides.load_hand_overrides``) are loaded once
    up front and threaded into every ``transpile_map`` call; ``overrides_dir``
    defaults to the package's ``hand_conversions/`` directory (pass a temp dir
    in tests to avoid touching the committed set).

    ``species_manifest_path`` is the species staging manifest
    (``species_converter.stage``'s ``species_manifest.json``); it defaults to
    ``out_dir / "species" / "species_manifest.json"`` (the layout
    ``assemble_pathfinder.py`` stages from) and is treated as absent — no
    species gate extras — when the file doesn't exist yet.

    ``trainer_manifest_path`` is the trainer staging manifest
    (``trainer_converter.stage``'s ``trainer_manifest.json``); same defaulting
    and same absent-is-not-an-error rule. It contributes the staged
    ``TRAINER_PIC_*`` pic constants and the staged ``TRAINER_*`` battle id
    constants — without it every ``trainerbattle_single`` the transpiler emits
    gates as an invented constant.
    """
    if species_manifest_path is None:
        species_manifest_path = out_dir / "species" / "species_manifest.json"
    if trainer_manifest_path is None:
        trainer_manifest_path = out_dir / "trainers" / "trainer_manifest.json"
    registry = (
        FlagRegistry.load(flag_state_path) if flag_state_path.is_file() else FlagRegistry()
    )
    reference_dir = Path("reference")
    # Labels are never part of to_state()/load() (flag_registry.py's
    # seed_labels docstring), so a freshly loaded/created registry has none
    # until re-seeded here — without this, every switch/var this pass is the
    # FIRST to touch (not already committed by an earlier stage_slice_scripts.py
    # dispatcher pass) resolves to None and queues as "unnamed", even though
    # its name is fully deterministic from the same static sidecar
    # stage_slice_scripts.py reads. Mirrors that module's identical call —
    # CLAUDE.md §4.2: a from-scratch run must resolve the same names, not
    # depend on accumulated state from a different script having run first.
    registry.seed_labels(
        reference_dir / "uranium_switches.json",
        reference_dir / "uranium_variables.json",
    )
    ctx = transpiler.TranspileContext(
        registry=registry,
        species=_load_species_id_map(reference_dir),
        staged_species=_load_staged_species(species_manifest_path),
        item_id_map=_load_item_id_map(reference_dir),
    )
    det_ctx = deterministic.load_context(
        reference_dir=reference_dir, intermediate_dir=out_dir / "intermediate"
    )
    # The give-item idiom resolves PBItems:: symbols through the same Phase-2
    # table the classifiers use; without this the transpiler queues every
    # pbReceiveItem as unknown-item.
    ctx.items = det_ctx.items
    # The canlose trainer-battle idiom resolves (class, name, party_id) ->
    # TRAINER_* through the same intermediate/trainers.json table the
    # classify_trainer_battle classifier uses; without this it queues every
    # canlose pbTrainerBattle as an unknown trainer.
    ctx.trainers = det_ctx.trainers
    # Converted content of Uranium's full-screen starter-reveal scene; the
    # pbStarterSelector idiom queues without it (CLAUDE.md §4.3).
    ctx.starter_scene = transpiler._load_starter_selector_scene(reference_dir)
    # Sheet name -> OBJ_EVENT_GFX_* for the code-41 live sprite swap. Read
    # unvalidated here (npc_gfx.load_npc_gfx_map's header check belongs to the
    # sprite pass); an unmapped sheet queues in the transpiler either way.
    _gfx_path = reference_dir / "npc_gfx_map.json"
    if _gfx_path.is_file():
        _gfx_raw = json.loads(_gfx_path.read_text(encoding="utf-8"))
        ctx.npc_gfx = {
            name: entry["gfx"]
            for name, entry in _gfx_raw.items()
            if isinstance(entry, dict) and entry.get("gfx")
        }
        # Per-STATE constants for sheets the sprite pass emits state by state
        # (large props); a code-41 that only moves (direction, pattern) resolves
        # through these instead of the sheet's single constant.
        ctx.npc_gfx_states = {
            name: {
                tuple(int(part) for part in key.split(",")): gfx
                for key, gfx in entry["states"].items()
            }
            for name, entry in _gfx_raw.items()
            if isinstance(entry, dict) and entry.get("states")
        }
    index = fork_index.load_or_build()
    # Forward check (CLAUDE.md §4.7) for resolve_native_object_template: the
    # id map is known to name ITEM_*_BERRY constants the fork doesn't
    # define (ACAI/HAFLI/GUARA/CUPU/BACU) — reuse the same ForkIndex the
    # gate below builds rather than a second symbol-resolution pass.
    ctx.fork_item_constants = frozenset(index.constants)
    overrides = hand_overrides.load_hand_overrides(overrides_dir)

    map_texts: dict[int, str] = {}
    all_queue: list[dict] = []
    events_total = 0
    overridden_total = 0

    for map_id in map_ids:
        map_path = maps_dir / f"Map{map_id:03d}.json"
        map_json = json.loads(map_path.read_text(encoding="utf-8"))
        events_total += len(map_json.get("events", []))
        overridden_total += sum(1 for (m, _e) in overrides if m == map_id)

        pory_text, queue_entries = transpile_map(map_id, map_json, ctx, det_ctx, overrides)

        extras = fork_index.registry_extra_symbols(
            None,
            map_constants_path if map_constants_path.is_file() else None,
            species_manifest_path if species_manifest_path.is_file() else None,
            # Same table ctx.npc_gfx resolves through: the OBJ_EVENT_GFX_URANIUM_*
            # constants live in generated, gitignored headers the index can't see.
            _gfx_path if _gfx_path.is_file() else None,
            trainer_manifest_path if trainer_manifest_path.is_file() else None,
        )
        extras |= _registry_minted_names(registry)
        violations = fork_index.verify_script(pory_text, index, extra_symbols=extras)
        if violations:
            lines = "\n".join(
                f"  Map{map_id:03d}:{v.line_no}: [{v.kind}] {v.symbol} — {v.context.strip()}"
                for v in violations
            )
            raise RuntimeError(
                f"transpile_driver: fork-index gate violated on Map{map_id:03d} "
                f"({len(violations)} violation(s)) — this is a transpiler bug, "
                f"never a queue item:\n{lines}"
            )

        reserved_hits = fork_index.check_reserved_var_writes(pory_text)
        if reserved_hits:
            lines = "\n".join(
                f"  Map{map_id:03d}:{v.line_no}: {v.symbol} — {v.context.strip()}"
                for v in reserved_hits
            )
            raise RuntimeError(
                f"transpile_driver: reserved-var write on Map{map_id:03d} "
                f"({len(reserved_hits)} violation(s)) — VAR_TEMP_F (coord-event "
                f"gate) and VAR_TEMP_C (ON_FRAME guard) must never be written "
                f"by transpiler output or hand overrides:\n{lines}"
            )

        map_texts[map_id] = pory_text
        all_queue.extend(queue_entries)

    ce_text: str | None = None
    ce_path = out_dir / "common_events.json"
    if common_events and ce_path.is_file():
        ce_text, ce_queue = transpile_common_events(ce_path, ctx)
        extras = fork_index.registry_extra_symbols(
            None,
            map_constants_path if map_constants_path.is_file() else None,
            species_manifest_path if species_manifest_path.is_file() else None,
            # Same table ctx.npc_gfx resolves through: the OBJ_EVENT_GFX_URANIUM_*
            # constants live in generated, gitignored headers the index can't see.
            _gfx_path if _gfx_path.is_file() else None,
            trainer_manifest_path if trainer_manifest_path.is_file() else None,
        )
        extras |= _registry_minted_names(registry)
        violations = fork_index.verify_script(ce_text, index, extra_symbols=extras)
        if violations:
            lines = "\n".join(
                f"  CommonEvents:{v.line_no}: [{v.kind}] {v.symbol} — {v.context.strip()}"
                for v in violations
            )
            raise RuntimeError(
                f"transpile_driver: fork-index gate violated on CommonEvents "
                f"({len(violations)} violation(s)):\n{lines}"
            )

        reserved_hits = fork_index.check_reserved_var_writes(ce_text)
        if reserved_hits:
            lines = "\n".join(
                f"  CommonEvents:{v.line_no}: {v.symbol} — {v.context.strip()}"
                for v in reserved_hits
            )
            raise RuntimeError(
                f"transpile_driver: reserved-var write on CommonEvents "
                f"({len(reserved_hits)} violation(s)) — VAR_TEMP_F (coord-event "
                f"gate) and VAR_TEMP_C (ON_FRAME guard) must never be written "
                f"by transpiler output or hand overrides:\n{lines}"
            )
        all_queue.extend(ce_queue)

    if write:
        scripts_dir = out_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        for map_id, text in map_texts.items():
            (scripts_dir / f"Map{map_id:03d}.pory").write_text(text, encoding="utf-8")
            _write_traits_sidecar(scripts_dir, map_id, ctx)
            _write_template_fields_sidecar(scripts_dir, map_id, ctx)
        if ce_text is not None:
            (scripts_dir / "CommonEvents.pory").write_text(ce_text, encoding="utf-8")

    if write:
        # The queue file is corpus-scoped state (the chapter census reads it to
        # tell "transpiles clean" from "never transpiled"), and a --dry-run that
        # wrote it would silently erase every other map's queue history. Keep it
        # inside the write gate with the .pory and the registry (2026-08-05).
        #
        # A run only ever computes entries for the maps it was given (plus
        # common events, if it recomputed those this pass) — it must NOT
        # clobber every other map's entries just because it wasn't asked to
        # touch them (CLAUDE.md §4.2). _merge_queue replaces only the
        # touched buckets and preserves the rest of the on-disk file.
        out_dir.mkdir(parents=True, exist_ok=True)
        queue_path = out_dir / "transpile_unhandled.jsonl"
        touched_buckets: set[int | None] = set(map_ids)
        if ce_text is not None:
            # Common events aren't scoped to the requested maps — every run
            # that processes them recomputes the WHOLE common_events.json,
            # so the None bucket is safe to replace wholesale exactly when
            # this run actually did that (ce_text is not None); otherwise
            # (common_events=False, or no common_events.json yet) the prior
            # common-event entries are left untouched.
            touched_buckets.add(None)
        merged_queue = _merge_queue(queue_path, touched_buckets, all_queue)
        queue_lines = [json.dumps(entry) for entry in merged_queue]
        queue_path.write_text(
            "".join(f"{line}\n" for line in queue_lines), encoding="utf-8"
        )
        registry.save(flag_state_path)

    return _summarize(
        map_ids, events_total, all_queue, overridden_total, len(ctx.skipped_stair_events)
    )


def _summarize(
    map_ids: list[int],
    events_total: int,
    queue: list[dict],
    overridden_total: int = 0,
    stairs_skipped_total: int = 0,
) -> dict:
    queue_by_code: dict[int, int] = {}
    for entry in queue:
        code = entry.get("command_code", 0)
        queue_by_code[code] = queue_by_code.get(code, 0) + 1

    cluster_counts: dict[str, int] = {}
    for entry in queue:
        prefix = str(entry.get("description", ""))[:_CLUSTER_PREFIX_LEN]
        cluster_counts[prefix] = cluster_counts.get(prefix, 0) + 1
    clusters = sorted(cluster_counts.items(), key=lambda kv: kv[1], reverse=True)[:_TOP_CLUSTERS]

    return {
        "maps": len(map_ids),
        "events": events_total,
        "queued": len(queue),
        "hand_overridden": overridden_total,
        "stairs_skipped": stairs_skipped_total,
        "queue_by_code": dict(sorted(queue_by_code.items(), key=lambda kv: kv[1], reverse=True)),
        "queue_clusters": clusters,
    }


# -- CLI -------------------------------------------------------------------------


def _default_maps_dir() -> Path:
    return Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build" / "maps"


def _print_summary(summary: dict) -> None:
    click.echo(
        f"maps: {summary['maps']}  events: {summary['events']}  queued: {summary['queued']}"
        f"  hand-overridden: {summary['hand_overridden']}"
        f"  stairs-skipped: {summary['stairs_skipped']}"
    )
    if summary["queue_by_code"]:
        click.echo("queue by code:")
        for code, count in summary["queue_by_code"].items():
            click.echo(f"  {code}: {count}")
    if summary["queue_clusters"]:
        click.echo("top clusters:")
        for prefix, count in summary["queue_clusters"]:
            click.echo(f"  {count:4d}  {prefix}")


@click.group()
def cli() -> None:
    """Deterministic-transpiler driver — run a map set through the transpiler."""


@cli.command()
@click.option(
    "--maps", "map_spec", required=True,
    help="'slice', 'full', or a comma-separated id list.",
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Don't write .pory files or save the registry.",
)
def run(map_spec: str, dry_run: bool) -> None:
    """Transpile a map set, gate it against the fork index, and report."""
    maps_dir = _default_maps_dir()
    out_dir = maps_dir.parent
    flag_state_path = out_dir / "flag_state.json"
    map_constants_path = out_dir / "porymap" / "map_constants.json"

    map_ids = resolve_map_ids(map_spec, maps_dir)
    summary = transpile_corpus(
        map_ids,
        maps_dir=maps_dir,
        out_dir=out_dir,
        flag_state_path=flag_state_path,
        map_constants_path=map_constants_path,
        write=not dry_run,
    )
    _print_summary(summary)


if __name__ == "__main__":  # pragma: no cover
    cli()
