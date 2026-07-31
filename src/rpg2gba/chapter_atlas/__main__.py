"""CLI for the chapter atlas.

    python -m rpg2gba.chapter_atlas validate
    python -m rpg2gba.chapter_atlas list [--act A1]
    python -m rpg2gba.chapter_atlas census --chapter CH02
    python -m rpg2gba.chapter_atlas census --all --json output/chapter_census.json
    python -m rpg2gba.chapter_atlas coverage
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import click

from .binding import default_binding_path, load_binding
from .census import census_for_maps


def _out_dir() -> Path:
    return Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"


def _binding(out_dir: Path):
    return load_binding(map_infos_path=out_dir / "map_infos.json")


@click.group()
def cli() -> None:
    """Play-order chapter atlas over the converted Uranium corpus."""


@cli.command()
def validate() -> None:
    """Validate reference/chapters.json; non-zero exit on any curation error."""
    out_dir = _out_dir()
    binding = _binding(out_dir)
    click.echo(f"OK  {default_binding_path()}")
    click.echo(f"    {len(binding.acts)} acts, {len(binding.chapters)} chapters, "
               f"{len(binding.map_ids)} distinct maps")
    revisits = [c for c in binding.chapters if c.is_revisit]
    click.echo(f"    {len(revisits)} revisit chapters")
    for tier in ("full", "medium", "thin"):
        n = sum(1 for c in binding.chapters if c.tier == tier)
        click.echo(f"    tier {tier:6s} {n:3d}")


@cli.command(name="list")
@click.option("--act", "act_id", default=None, help="Only this act.")
def list_chapters(act_id: str | None) -> None:
    """List chapters in play order."""
    binding = _binding(_out_dir())
    acts = [binding.act(act_id)] if act_id else list(binding.acts)
    for act in acts:
        click.echo(f"\n{act.id}  {act.title}")
        for chapter in binding.chapters_in(act.id):
            visit = f" v{chapter.visit}" if chapter.is_revisit else "   "
            click.echo(f"  {chapter.id}{visit}  {chapter.tier:6s} "
                       f"{chapter.title:38s} {len(chapter.maps):2d} maps")


@cli.command()
@click.option("--chapter", "chapter_id", default=None, help="One chapter id.")
@click.option("--all", "do_all", is_flag=True, help="Every chapter.")
@click.option("--json", "json_path", type=click.Path(path_type=Path),
              default=None, help="Write machine-readable output here.")
def census(chapter_id: str | None, do_all: bool, json_path: Path | None) -> None:
    """Mechanical inventory for a chapter (or all of them)."""
    if not chapter_id and not do_all:
        raise click.UsageError("pass --chapter ID or --all")
    out_dir = _out_dir()
    binding = _binding(out_dir)
    targets = binding.chapters if do_all else [binding.chapter(chapter_id)]

    payload = {}
    for chapter in targets:
        result = census_for_maps(
            list(chapter.maps), out_dir=out_dir, chapter_id=chapter.id,
            title=chapter.title, act=chapter.act, visit=chapter.visit,
            tier=chapter.tier)
        totals = result.totals
        payload[chapter.id] = {
            "title": chapter.title,
            "act": chapter.act,
            "visit": chapter.visit,
            "tier": chapter.tier,
            "totals": totals,
            "mechanics": result.mechanics,
            "unknown_script_heads": result.unknown_script_heads,
            "script_heads": dict(result.script_heads),
            "external_warp_destinations": sorted(result.external_warp_destinations),
            "seams": result.seams,
            "maps": [
                {
                    "map_id": m.map_id, "name": m.name,
                    "size": [m.width, m.height], "tileset_id": m.tileset_id,
                    "events": m.events, "pages": m.pages, "commands": m.commands,
                    "trainer_battles": m.trainer_battles,
                    "item_grants": m.item_grants, "shops": m.shops,
                    "encounter_tables": m.encounter_tables,
                    "unhandled": m.unhandled,
                }
                for m in result.maps
            ],
        }
        if not json_path:
            click.echo(f"\n{chapter.id}  {chapter.title}  "
                       f"[{chapter.act}, tier {chapter.tier}, visit {chapter.visit}]")
            click.echo("  totals: " + "  ".join(
                f"{k}={v}" for k, v in totals.items() if v))
            if result.mechanics:
                click.echo("  mechanics: " + ", ".join(result.mechanics))
            if result.unknown_script_heads:
                click.echo("  unmapped script heads: "
                           + ", ".join(result.unknown_script_heads))
            for m in result.maps:
                enc = f" enc[{','.join(m.encounter_tables)}]" if m.encounter_tables else ""
                q = "" if m.unhandled is None else f" queue={m.unhandled}"
                click.echo(f"    {m.map_id:3d} {m.name[:34]:34s} "
                           f"{m.width:3d}x{m.height:<3d} ev={m.events:3d}{enc}{q}")

    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        click.echo(f"wrote {json_path} ({len(payload)} chapters)")


@cli.command()
def coverage() -> None:
    """Check that chapters + unbound_maps account for every converted map."""
    out_dir = _out_dir()
    binding = _binding(out_dir)
    raw = json.loads(default_binding_path().read_text(encoding="utf-8"))
    unbound = {int(k) for k in raw.get("unbound_maps", {}) if k != "_comment"}
    infos = json.loads((out_dir / "map_infos.json").read_text(encoding="utf-8"))
    known = {int(k) for k in infos}

    bound = set(binding.map_ids)
    missing = sorted(known - bound - unbound)
    overlap = sorted(bound & unbound)

    click.echo(f"map_infos maps : {len(known)}")
    click.echo(f"bound to acts  : {len(bound)}")
    click.echo(f"declared unbound: {len(unbound)}")
    if overlap:
        click.echo(f"ERROR both bound and unbound: {overlap}")
    if missing:
        click.echo(f"ERROR unaccounted maps: {missing}")
        for m in missing:
            click.echo(f"    {m:3d} {infos[str(m)]['name']!r}")
    if not missing and not overlap:
        click.echo("OK every map is either bound to a chapter or explicitly unbound")
    raise SystemExit(1 if (missing or overlap) else 0)


if __name__ == "__main__":
    cli()
