"""CLI for the chapter manifest generator/checker/reviewer.

    python -m rpg2gba.chapter_manifest generate --chapter CH04
    python -m rpg2gba.chapter_manifest check --chapter CH04
    python -m rpg2gba.chapter_manifest review --chapter CH04

`generate` writes the manifest and its machine-derived sidecar; `check` and
`review` resolve the generated manifest, the authored disposition file, and
(for `check`) the sidecar by convention:

    reference/manifests/<chapter>.manifest.json       (generator.py output)
    reference/manifests/<chapter>.dispositions.json    (dispositions.py, hand-authored)
    reference/manifests/<chapter>.derived.json         (generator.py output)

with `--manifest`/`--dispositions`/`--derived` overrides for pointing at a
scratch copy. This module never writes the dispositions file; it does write
the manifest and the sidecar (`generate`), and only reads all three
otherwise.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from rpg2gba.slice_growth import SliceGrowthError

from . import checker
from .approach_model import GraphApproachModel
from .archetype_model import build_archetype_model
from .beat_model import build_beat_model
from .boundary_model import build_boundary_model
from .capability_model import build_capability_model
from .derivation import derive_entry
from .dispositions import derived_path, disposition_path, load_derived, load_dispositions
from .generator import generate_chapter_manifest, write_derived, write_manifest
from .route_model import build_route_model
from .schema import ManifestRow, row_from_dict

logger = logging.getLogger(__name__)

MANIFESTS_DIR = Path("reference") / "manifests"
DEFAULT_BUILD_DIR = Path("output") / "uranium-build"
DEFAULT_CHAPTERS_PATH = Path("reference") / "chapters.json"


def _manifest_path(chapter: str) -> Path:
    return MANIFESTS_DIR / f"{chapter}.manifest.json"


def _is_live_chapter(chapter: str, chapters_path: Path) -> bool:
    """True unless `chapters.json` records this chapter's `status` as
    ``"built"`` -- i.e. true for a chapter still being authored, false once
    it has passed its §9 boot-walk gate. Drives the severity of both
    `checker.RULE_ARCHETYPE_CONFORMANCE` and `checker.RULE_UNREGISTERED_BEAT`
    (`checker.check_chapter`'s `live_chapter` docstring).

    Falls back to `check_chapter`'s own default (False, gated/warning) with
    a logged warning when the chapter id isn't in `chapters.json` at all --
    e.g. a synthetic/test chapter id never registered there. That is a
    real gap (a chapter this checker has never heard of), but it must not
    make `check` itself unusable for such a chapter; the archetype rule
    degrading to its quieter severity is the same shape as every other
    `*_UNENFORCED` rule here rather than a hard failure of an unrelated
    command.
    """
    with chapters_path.open(encoding="utf-8") as f:
        data = json.load(f)
    for entry in data.get("chapters", []):
        if entry.get("id") == chapter:
            return entry.get("status") != "built"
    logger.warning(
        "%s: no chapter %r found; defaulting the live-chapter rules "
        "(RULE_ARCHETYPE_CONFORMANCE, RULE_UNREGISTERED_BEAT) to "
        "gated/warning severity", chapters_path, chapter)
    return False


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
@click.option("--derived", "derived_path_opt", type=click.Path(path_type=Path), default=None,
              help="Machine-derived sidecar output path "
                   "(default: reference/manifests/<chapter>.derived.json)")
@click.option("--build-dir", type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_BUILD_DIR,
              help="Converted-map build directory (default: output/uranium-build)")
@click.option("--chapters", "chapters_path", type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_CHAPTERS_PATH,
              help="Chapter/map chain JSON (default: reference/chapters.json)")
def generate_cmd(chapter: str, manifest: Path | None, derived_path_opt: Path | None,
                  build_dir: Path, chapters_path: Path) -> None:
    """Generate a chapter's manifest from converted map data."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    manifest_file = manifest or _manifest_path(chapter)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    # Sibling of wherever the manifest actually landed, not a fixed
    # chapter-keyed default -- a caller pointing `--manifest` at a scratch
    # path (every generator test does this) gets its sidecar alongside it,
    # not written into the real reference/manifests/ tree by surprise.
    derived_file = derived_path_opt or derived_path(chapter, root=manifest_file.parent)
    derived_file.parent.mkdir(parents=True, exist_ok=True)

    rows = generate_chapter_manifest(chapter, build_dir=build_dir, chapters_path=chapters_path)
    write_manifest(rows, manifest_file)

    # Same models `check_cmd` builds, for the same reason: without them
    # `derive_entry` can resolve `blocked:`/`cosmetic` but never
    # `beat:`/`boundary` (both need the playtest-module/chain facts these
    # adapters carry). Unlike `check_cmd`, `generate` must stay usable
    # against a scratch/synthetic chapter that has no real, committed
    # `reference/chapters.json` chain to read at all (every generator
    # fixture test does this) -- both adapters read the REAL repo's chapter
    # chain by design (their own docstrings), which raises loud
    # (`FileNotFoundError`/`SliceGrowthError`) rather than degrading when
    # that chain isn't reachable from the current working directory. That
    # is exactly the "beat/boundary derivation is unenforced here" state
    # (mirrors every other `*_UNENFORCED` degrade in `checker.py`), not a
    # bug in the manifest being generated -- `cosmetic`/`blocked:` still
    # derive normally without either model.
    try:
        beat_model = build_beat_model(chapter)
    except (FileNotFoundError, SliceGrowthError) as exc:
        logger.warning(
            "could not build a beat model for %s (%s) -- beat: entries will "
            "not be derived this run", chapter, exc)
        beat_model = None
    try:
        boundary_model = build_boundary_model(chapter)
    except (FileNotFoundError, SliceGrowthError) as exc:
        logger.warning(
            "could not build a boundary model for %s (%s) -- boundary "
            "entries will not be derived this run", chapter, exc)
        boundary_model = None
    write_derived(rows, derived_file, beat_model=beat_model, boundary_model=boundary_model)

    undispositionable = sum(1 for row in rows if not row.is_dispositionable)
    needs_citation = sum(1 for row in rows if row.needs_citation)
    entries = [
        entry
        for row in rows
        for entry in (derive_entry(row, beat_model=beat_model, boundary_model=boundary_model),)
        if entry is not None
    ]
    verdict_counts: dict[str, int] = {}
    proposals = 0
    for entry in entries:
        head = entry.disposition.split(":", 1)[0]
        verdict_counts[head] = verdict_counts.get(head, 0) + 1
        if entry.proposed:
            proposals += 1
    breakdown = ", ".join(f"{head}={n}" for head, n in sorted(verdict_counts.items()))
    click.echo(f"wrote {manifest_file}: {len(rows)} rows, "
               f"{undispositionable} undispositionable, {needs_citation} need citation")
    click.echo(f"wrote {derived_file}: {len(entries)} machine-derived row(s) "
               f"({breakdown}; {proposals} proposal(s) awaiting affirmation)")
    sys.exit(0)


@cli.command("check")
@click.option("--chapter", required=True, help="Chapter id, e.g. CH04.")
@click.option("--manifest", type=click.Path(exists=True, path_type=Path), default=None,
              help="Manifest JSON path (default: reference/manifests/<chapter>.manifest.json)")
@click.option("--dispositions", "dispositions_path_opt",
              type=click.Path(exists=True, path_type=Path), default=None,
              help="Disposition JSON path "
                   "(default: reference/manifests/<chapter>.dispositions.json)")
@click.option("--derived", "derived_path_opt",
              type=click.Path(exists=True, path_type=Path), default=None,
              help="Machine-derived sidecar JSON path, for the derived-hash rule "
                   "(default: reference/manifests/<chapter>.derived.json)")
@click.option("--build-dir", type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_BUILD_DIR,
              help="Converted-map build directory, for the approach model "
                   "(default: output/uranium-build)")
@click.option("--route", "route_path_opt",
              type=click.Path(exists=True, path_type=Path), default=None,
              help="Route plan JSON path, for the route-order rule "
                   "(default: reference/routes/<chapter>.route.json)")
@click.option("--chapters", "chapters_path", type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_CHAPTERS_PATH,
              help="Chapter/map chain JSON, for archetype-conformance severity "
                   "(default: reference/chapters.json)")
def check_cmd(chapter: str, manifest: Path | None, dispositions_path_opt: Path | None,
              derived_path_opt: Path | None, build_dir: Path, route_path_opt: Path | None,
              chapters_path: Path) -> None:
    """Check a chapter's manifest against its dispositions; nonzero exit on error."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    manifest_file = manifest or _manifest_path(chapter)
    dispositions_file = dispositions_path_opt or disposition_path(chapter)
    derived_file = derived_path_opt or derived_path(chapter)

    if not manifest_file.exists():
        raise click.ClickException(f"manifest not found: {manifest_file}")
    rows = load_manifest(manifest_file)
    # A missing dispositions file is zero hand decisions, not an error
    # (REDERIVATION_PLAN.md §14.6 ruling 1): rows the derived sidecar covers
    # are dispositioned without one, and every other row still reports
    # `undispositioned`, so nothing passes vacuously.
    if dispositions_file.exists():
        dispositions = load_dispositions(dispositions_file)
    else:
        logging.getLogger(__name__).info(
            "no dispositions file at %s -- checking with zero hand decisions",
            dispositions_file)
        dispositions = {}
    # Same exists()-gated pattern as the dispositions file above, but the
    # sidecar's ABSENCE is not an error: a brand-new Essentials game (or a
    # chapter predating this sidecar) has none at all, and that is exactly
    # the "0% automated" state the ratio this sidecar backs is meant to show.
    derived = load_derived(derived_file) if derived_file.exists() else None

    approach = GraphApproachModel(
        chapter, maps_dir=build_dir / "maps", tilesets_json=build_dir / "tilesets.json")
    route = build_route_model(chapter, route=route_path_opt)
    archetype_model = build_archetype_model(chapter)
    beat_model = build_beat_model(chapter)
    boundary_model = build_boundary_model(chapter)
    capabilities = build_capability_model(chapter)
    live_chapter = _is_live_chapter(chapter, chapters_path)
    findings = checker.check_chapter(
        rows, dispositions, capabilities=capabilities, approach=approach, route=route,
        archetype_model=archetype_model, beat_model=beat_model,
        boundary_model=boundary_model, derived=derived, live_chapter=live_chapter)

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
