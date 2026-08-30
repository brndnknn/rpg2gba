"""CLI for the chapter manifest generator/checker/reviewer.

    python -m rpg2gba.chapter_manifest generate --chapter CH04
    python -m rpg2gba.chapter_manifest check --chapter CH04
    python -m rpg2gba.chapter_manifest review --chapter CH04

`generate` writes the manifest; `check` and `review` resolve the generated
manifest and the authored disposition file by convention:

    reference/manifests/<chapter>.manifest.json       (generator.py output)
    reference/manifests/<chapter>.dispositions.json    (dispositions.py)

with `--manifest`/`--dispositions` overrides for pointing at a scratch copy.
This module only reads those two files; it never writes either.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from . import checker
from .approach_model import GraphApproachModel
from .dispositions import disposition_path, load_dispositions
from .generator import generate_chapter_manifest, write_manifest
from .route_model import build_route_model
from .schema import ManifestRow, row_from_dict

logger = logging.getLogger(__name__)

MANIFESTS_DIR = Path("reference") / "manifests"
DEFAULT_BUILD_DIR = Path("output") / "uranium-build"
DEFAULT_CHAPTERS_PATH = Path("reference") / "chapters.json"


def _manifest_path(chapter: str) -> Path:
    return MANIFESTS_DIR / f"{chapter}.manifest.json"


def load_manifest(path: Path) -> list[ManifestRow]:
    """Read a generated manifest.

    Deserialization is `schema.row_from_dict`, the same round trip the
    generator writes through, and it is strict in both directions: a row whose
    key set is not exactly `ManifestRow`'s fields is an error. A lenient reader
    here would default a newly-added field away and silently evaluate the rules
    against a row that is not the row on disk.
    """
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        raise click.ClickException(
            f"{path}: expected a JSON list of manifest rows, got {type(raw).__name__}"
        )
    try:
        return [row_from_dict(entry) for entry in raw]
    except ValueError as exc:
        raise click.ClickException(f"{path}: {exc}") from exc


@click.group()
def cli() -> None:
    """rpg2gba chapter manifest checker/reviewer (see PLAYTEST_AUTHORING_IMPROVEMENT.md Q1/Q6)."""


@cli.command("generate")
@click.option("--chapter", required=True, help="Chapter id, e.g. CH04.")
@click.option("--manifest", type=click.Path(path_type=Path), default=None,
              help="Manifest output path (default: reference/manifests/<chapter>.manifest.json)")
@click.option("--build-dir", type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_BUILD_DIR,
              help="Converted-map build directory (default: output/uranium-build)")
@click.option("--chapters", "chapters_path", type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_CHAPTERS_PATH,
              help="Chapter/map chain JSON (default: reference/chapters.json)")
def generate_cmd(chapter: str, manifest: Path | None, build_dir: Path,
                  chapters_path: Path) -> None:
    """Generate a chapter's manifest from converted map data."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    manifest_file = manifest or _manifest_path(chapter)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)

    rows = generate_chapter_manifest(chapter, build_dir=build_dir, chapters_path=chapters_path)
    write_manifest(rows, manifest_file)

    undispositionable = sum(1 for row in rows if not row.is_dispositionable)
    needs_citation = sum(1 for row in rows if row.needs_citation)
    click.echo(f"wrote {manifest_file}: {len(rows)} rows, "
               f"{undispositionable} undispositionable, {needs_citation} need citation")
    sys.exit(0)


@cli.command("check")
@click.option("--chapter", required=True, help="Chapter id, e.g. CH04.")
@click.option("--manifest", type=click.Path(exists=True, path_type=Path), default=None,
              help="Manifest JSON path (default: reference/manifests/<chapter>.manifest.json)")
@click.option("--dispositions", "dispositions_path_opt",
              type=click.Path(exists=True, path_type=Path), default=None,
              help="Disposition JSON path "
                   "(default: reference/manifests/<chapter>.dispositions.json)")
@click.option("--build-dir", type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_BUILD_DIR,
              help="Converted-map build directory, for the approach model "
                   "(default: output/uranium-build)")
@click.option("--route", "route_path_opt",
              type=click.Path(exists=True, path_type=Path), default=None,
              help="Route plan JSON path, for the route-order rule "
                   "(default: reference/routes/<chapter>.route.json)")
def check_cmd(chapter: str, manifest: Path | None, dispositions_path_opt: Path | None,
              build_dir: Path, route_path_opt: Path | None) -> None:
    """Check a chapter's manifest against its dispositions; nonzero exit on error."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    manifest_file = manifest or _manifest_path(chapter)
    dispositions_file = dispositions_path_opt or disposition_path(chapter)

    if not manifest_file.exists():
        raise click.ClickException(f"manifest not found: {manifest_file}")
    if not dispositions_file.exists():
        raise click.ClickException(f"dispositions not found: {dispositions_file}")

    rows = load_manifest(manifest_file)
    dispositions = load_dispositions(dispositions_file)

    approach = GraphApproachModel(
        chapter, maps_dir=build_dir / "maps", tilesets_json=build_dir / "tilesets.json")
    route = build_route_model(chapter, route=route_path_opt)
    findings = checker.check_chapter(
        rows, dispositions, approach=approach, route=route)

    if not findings:
        click.echo(f"chapter {chapter}: OK ({len(rows)} rows)")
        sys.exit(0)

    for finding in findings:
        click.echo(f"[{finding.severity.upper()}] {finding.row_id} ({finding.rule}): "
                    f"{finding.message}")

    code = checker.exit_code(findings)
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    click.echo(f"chapter {chapter}: {errors} error(s), {warnings} warning(s), "
               f"{len(rows)} rows")
    sys.exit(code)


@cli.command("review")
@click.option("--chapter", required=True, help="Chapter id, e.g. CH04.")
@click.option("--manifest", type=click.Path(exists=True, path_type=Path), default=None,
              help="Manifest JSON path (default: reference/manifests/<chapter>.manifest.json)")
@click.option("--dispositions", "dispositions_path_opt",
              type=click.Path(exists=True, path_type=Path), default=None,
              help="Disposition JSON path "
                   "(default: reference/manifests/<chapter>.dispositions.json)")
def review_cmd(chapter: str, manifest: Path | None, dispositions_path_opt: Path | None) -> None:
    """Print the Markdown human review view of a chapter's manifest."""
    from .render import render_review

    manifest_file = manifest or _manifest_path(chapter)
    dispositions_file = dispositions_path_opt or disposition_path(chapter)

    if not manifest_file.exists():
        raise click.ClickException(f"manifest not found: {manifest_file}")

    rows = load_manifest(manifest_file)
    dispositions = load_dispositions(dispositions_file) if dispositions_file.exists() else {}

    click.echo(render_review(rows, dispositions))


if __name__ == "__main__":
    cli()
