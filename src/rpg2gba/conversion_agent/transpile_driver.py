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
from pathlib import Path

import click

from rpg2gba.conversion_agent import deterministic, fork_index, transpiler
from rpg2gba.conversion_agent.flag_registry import FlagRegistry
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


def transpile_map(
    map_id: int,
    map_json: dict,
    ctx: transpiler.TranspileContext,
    det_ctx: deterministic.Context | None,
) -> tuple[str, list[dict]]:
    """Transpile every event on one map; return (pory_text, queue_entries).

    Tries the idiom-collapse classifiers first (cheaper, hand-validated
    output); falls back to the general command-by-command transpiler.
    """
    event_texts: list[str] = []
    queue_entries: list[dict] = []

    for event in map_json.get("events", []):
        det = deterministic.try_deterministic(map_id, event, det_ctx)
        if det is not None:
            event_texts.append(_canonicalize_labels(det.script, map_id, event))
            queue_entries.extend(
                _det_queue_entry(entry, map_id=map_id, event=event)
                for entry in det.unhandled
            )
            continue
        transpiled = transpiler.transpile_event(map_id, event, ctx)
        event_texts.append(transpiled.text)
        queue_entries.extend(e.to_json() for e in transpiled.unhandled)

    pory_text = "\n\n".join(text for text in event_texts if text)
    return pory_text, queue_entries


# -- registry glue for the gate -------------------------------------------------


def _registry_minted_names(registry: FlagRegistry) -> set[str]:
    """All FLAG_*/VAR_* names the live registry has assigned so far (preseed +
    this run's mints) — read straight off the in-memory object so a mint made
    mid-run is visible before anything is saved back to disk."""
    state = registry.to_state()
    names: set[str] = set()
    for category in ("switches", "variables", "self_switches", "temp_switches"):
        names |= set(state[category].values())
    return names


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
    write: bool = True,
    common_events: bool = True,
) -> dict:
    """Transpile a set of maps, gate every one, and (optionally) write output."""
    registry = (
        FlagRegistry.load(flag_state_path) if flag_state_path.is_file() else FlagRegistry()
    )
    ctx = transpiler.TranspileContext(registry=registry)
    det_ctx = deterministic.load_context(
        reference_dir=Path("reference"), intermediate_dir=out_dir / "intermediate"
    )
    # The give-item idiom resolves PBItems:: symbols through the same Phase-2
    # table the classifiers use; without this the transpiler queues every
    # pbReceiveItem as unknown-item.
    ctx.items = det_ctx.items
    index = fork_index.load_or_build()

    map_texts: dict[int, str] = {}
    all_queue: list[dict] = []
    events_total = 0

    for map_id in map_ids:
        map_path = maps_dir / f"Map{map_id:03d}.json"
        map_json = json.loads(map_path.read_text(encoding="utf-8"))
        events_total += len(map_json.get("events", []))

        pory_text, queue_entries = transpile_map(map_id, map_json, ctx, det_ctx)

        extras = fork_index.registry_extra_symbols(
            None, map_constants_path if map_constants_path.is_file() else None
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

        map_texts[map_id] = pory_text
        all_queue.extend(queue_entries)

    ce_text: str | None = None
    ce_path = out_dir / "common_events.json"
    if common_events and ce_path.is_file():
        ce_text, ce_queue = transpile_common_events(ce_path, ctx)
        extras = fork_index.registry_extra_symbols(
            None, map_constants_path if map_constants_path.is_file() else None
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
        all_queue.extend(ce_queue)

    if write:
        scripts_dir = out_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        for map_id, text in map_texts.items():
            (scripts_dir / f"Map{map_id:03d}.pory").write_text(text, encoding="utf-8")
        if ce_text is not None:
            (scripts_dir / "CommonEvents.pory").write_text(ce_text, encoding="utf-8")

    out_dir.mkdir(parents=True, exist_ok=True)
    queue_path = out_dir / "transpile_unhandled.jsonl"
    queue_lines = [json.dumps(entry) for entry in all_queue]
    queue_path.write_text(
        "".join(f"{line}\n" for line in queue_lines), encoding="utf-8"
    )

    if write:
        registry.save(flag_state_path)

    return _summarize(map_ids, events_total, all_queue)


def _summarize(map_ids: list[int], events_total: int, queue: list[dict]) -> dict:
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
        "queue_by_code": dict(sorted(queue_by_code.items(), key=lambda kv: kv[1], reverse=True)),
        "queue_clusters": clusters,
    }


# -- CLI -------------------------------------------------------------------------


def _default_maps_dir() -> Path:
    return Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build" / "maps"


def _print_summary(summary: dict) -> None:
    click.echo(f"maps: {summary['maps']}  events: {summary['events']}  queued: {summary['queued']}")
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
