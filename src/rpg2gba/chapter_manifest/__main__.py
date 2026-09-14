"""CLI for the chapter manifest generator/checker/reviewer/affirmer.

    python -m rpg2gba.chapter_manifest generate --chapter CH04
    python -m rpg2gba.chapter_manifest check --chapter CH04
    python -m rpg2gba.chapter_manifest review --chapter CH04
    python -m rpg2gba.chapter_manifest affirm --chapter CH04 --digest <d> --all

`generate` writes the manifest, its machine-derived sidecar, and a Markdown
review of the sidecar's `blocked:` PROPOSALS; `check`, `review`, and `affirm`
resolve the generated manifest, the authored disposition file, and (for
`check`/`affirm`) the sidecar by convention:

    reference/manifests/<chapter>.manifest.json       (generator.py output)
    reference/manifests/<chapter>.dispositions.json    (dispositions.py, hand-authored)
    reference/manifests/<chapter>.derived.json         (generator.py output)

with `--manifest`/`--dispositions`/`--derived` overrides for pointing at a
scratch copy. `generate` writes the manifest and the sidecar; `affirm` is the
one command that writes the dispositions file, and only when a human invokes
it with a `--digest` that matches the sidecar's current proposals
(`dispositions.proposal_digest`) -- every other command only reads.
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
from .derivation import DerivedEntry, derive_entry
from .dispositions import (
    derived_path,
    disposition_path,
    load_derived,
    load_dispositions,
    proposal_digest,
    write_dispositions,
)
from .generator import generate_chapter_manifest, write_derived, write_manifest
from .render import EventFacts, render_blocked_proposals
from .route_model import build_route_model
from .schema import Disposition, ManifestRow, row_from_dict

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


def _review_path(chapter: str, manifest: Path | None, manifest_file: Path) -> Path:
    """Default: a `--manifest` override redirects the review file alongside
    it, exactly like `derived_path`'s own `--manifest`-relative default
    (`generate_cmd`'s comment above `derived_file`) -- a caller pointing
    `--manifest` at a scratch path (every generator test does this) must not
    have its review land in the real `output/manifests/` tree by surprise.
    """
    if manifest is not None:
        return manifest_file.parent / f"{chapter}.blocked_review.md"
    return Path("output") / "manifests" / f"{chapter}.blocked_review.md"


def _load_event_facts(
    rows_by_id: dict[str, ManifestRow],
    derived: dict[str, DerivedEntry],
    build_dir: Path,
) -> dict[tuple[int, int], EventFacts]:
    """Resolve every `(map_id, event_id)` an event-page PROPOSAL row names to
    an `EventFacts`, from the converted map data under `build_dir` --
    `map_infos.json` for the map's display name, `maps/Map<NNN>.json` for the
    event's own name and tile. Fails loud (CLAUDE.md §4.5) the moment a map,
    event, or expected field is missing; never defaults a name away.
    """
    needed: set[tuple[int, int]] = set()
    for row_id, entry in derived.items():
        if not entry.proposed:
            continue
        row = rows_by_id.get(row_id)
        if row is None:
            raise click.ClickException(
                f"proposal row {row_id!r} (in the derived sidecar) has no "
                "matching row in the manifest"
            )
        if row.kind == "page" and row.event_id is not None:
            needed.add((row.map_id, row.event_id))

    if not needed:
        return {}

    map_infos_path = build_dir / "map_infos.json"
    if not map_infos_path.exists():
        raise click.ClickException(
            f"cannot build the blocked-proposal review: {map_infos_path} not found"
        )
    with map_infos_path.open(encoding="utf-8") as f:
        map_infos = json.load(f)

    facts: dict[tuple[int, int], EventFacts] = {}
    events_by_map: dict[int, dict[int, dict]] = {}
    for map_id, event_id in sorted(needed):
        info = map_infos.get(str(map_id))
        if not isinstance(info, dict) or not isinstance(info.get("name"), str):
            raise click.ClickException(
                f"map {map_id:03d} not found (or has no string 'name') in {map_infos_path}"
            )
        map_name = info["name"]

        if map_id not in events_by_map:
            map_json_path = build_dir / "maps" / f"Map{map_id:03d}.json"
            if not map_json_path.exists():
                raise click.ClickException(
                    f"cannot build the blocked-proposal review: {map_json_path} not found"
                )
            with map_json_path.open(encoding="utf-8") as f:
                map_json = json.load(f)
            events_by_map[map_id] = {
                event["id"]: event for event in map_json.get("events", [])
            }

        event = events_by_map[map_id].get(event_id)
        if event is None or not isinstance(event.get("name"), str):
            raise click.ClickException(
                f"event {event_id} not found (or has no string 'name') on map "
                f"{map_id:03d} in {build_dir / 'maps' / f'Map{map_id:03d}.json'}"
            )
        facts[(map_id, event_id)] = EventFacts(
            map_name=map_name, event_name=event["name"], x=event["x"], y=event["y"])

    return facts


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
@click.option("--review", "review_path_opt", type=click.Path(path_type=Path), default=None,
              help="Blocked-proposal review output path "
                   "(default: output/manifests/<chapter>.blocked_review.md, or a sibling of "
                   "--manifest when --manifest is given)")
@click.option("--build-dir", type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_BUILD_DIR,
              help="Converted-map build directory (default: output/uranium-build)")
@click.option("--chapters", "chapters_path", type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_CHAPTERS_PATH,
              help="Chapter/map chain JSON (default: reference/chapters.json)")
def generate_cmd(chapter: str, manifest: Path | None, derived_path_opt: Path | None,
                  review_path_opt: Path | None, build_dir: Path, chapters_path: Path) -> None:
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

    # Reloaded from disk rather than reusing `entries` above: the sidecar
    # file IS the row_id-keyed shape `render_blocked_proposals`/`affirm` both
    # need, and `load_derived` is the same strict round trip `affirm` will
    # later read through -- the review must describe exactly what a
    # follow-up `affirm` run will see, not a same-process recomputation that
    # could in principle diverge from what `write_derived` actually wrote.
    derived = load_derived(derived_file)
    review_file = review_path_opt or _review_path(chapter, manifest, manifest_file)
    review_file.parent.mkdir(parents=True, exist_ok=True)
    rows_by_id = {row.row_id: row for row in rows}
    # Same degrade shape as the beat/boundary models above: `generate` must
    # stay usable against a scratch/synthetic build dir that has no
    # `map_infos.json` at all (every chokepoint/CLI fixture test does this),
    # so a build-data gap here logs a warning and produces a review with
    # unresolved names rather than failing the whole `generate` run over an
    # optional artifact.
    try:
        event_facts = _load_event_facts(rows_by_id, derived, build_dir)
    except click.ClickException as exc:
        logger.warning(
            "could not resolve event/map facts for %s's blocked-proposal review "
            "(%s) -- the review will show map/event ids without names",
            chapter, exc.message)
        event_facts = {}
    review_text = render_blocked_proposals(chapter, derived, rows, event_facts)
    review_file.write_text(review_text, encoding="utf-8")
    digest = proposal_digest(derived)
    review_proposals = sum(1 for entry in derived.values() if entry.proposed)
    click.echo(f"wrote {review_file}: {review_proposals} proposal(s), digest {digest}")
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


@cli.command("affirm")
@click.option("--chapter", required=True, help="Chapter id, e.g. CH04.")
@click.option("--digest", required=True,
              help="Proposal digest from the `generate`-written review file "
                   "(`dispositions.proposal_digest`); must match the sidecar's CURRENT "
                   "proposals or nothing is written.")
@click.option("--all", "affirm_all", is_flag=True, default=False,
              help="Affirm every current proposal. Mutually exclusive with --row.")
@click.option("--row", "row_ids", multiple=True,
              help="Affirm this row id (repeatable). Mutually exclusive with --all.")
@click.option("--manifest", type=click.Path(exists=True, path_type=Path), default=None,
              help="Manifest JSON path (default: reference/manifests/<chapter>.manifest.json)")
@click.option("--dispositions", "dispositions_path_opt",
              type=click.Path(path_type=Path), default=None,
              help="Disposition JSON path to merge into "
                   "(default: reference/manifests/<chapter>.dispositions.json)")
@click.option("--derived", "derived_path_opt",
              type=click.Path(exists=True, path_type=Path), default=None,
              help="Machine-derived sidecar JSON path "
                   "(default: reference/manifests/<chapter>.derived.json)")
def affirm_cmd(chapter: str, digest: str, affirm_all: bool, row_ids: tuple[str, ...],
               manifest: Path | None, dispositions_path_opt: Path | None,
               derived_path_opt: Path | None) -> None:
    """Affirm one or more `blocked:` proposals from the derived sidecar into
    the hand-authored dispositions file.

    Every check below runs before anything is written; on any failure this
    raises `click.ClickException` and writes nothing (CLAUDE.md §4.5) --
    there is no partial-affirm state.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if affirm_all and row_ids:
        raise click.ClickException("pass exactly one of --all or --row, not both")
    if not affirm_all and not row_ids:
        raise click.ClickException("pass --all or at least one --row")

    manifest_file = manifest or _manifest_path(chapter)
    dispositions_file = dispositions_path_opt or disposition_path(chapter)
    derived_file = derived_path_opt or derived_path(chapter)

    if not manifest_file.exists():
        raise click.ClickException(f"manifest not found: {manifest_file}")
    if not derived_file.exists():
        raise click.ClickException(f"derived sidecar not found: {derived_file}")

    rows = load_manifest(manifest_file)
    rows_by_id = {row.row_id: row for row in rows}
    derived = load_derived(derived_file)

    current_digest = proposal_digest(derived)
    if current_digest != digest:
        raise click.ClickException(
            f"proposal digest mismatch: given {digest!r}, sidecar's current "
            f"proposals hash to {current_digest!r} -- the proposals changed since "
            "this review was generated; re-run `generate` and re-review before "
            "affirming"
        )

    proposals = {row_id: entry for row_id, entry in derived.items() if entry.proposed}

    if affirm_all:
        selected = sorted(proposals)
    else:
        selected = list(row_ids)
        for row_id in selected:
            if row_id not in proposals:
                raise click.ClickException(
                    f"{row_id!r} is not a current proposal in {derived_file}"
                )

    for row_id in selected:
        row = rows_by_id.get(row_id)
        if row is None:
            raise click.ClickException(f"{row_id!r}: no such row in {manifest_file}")
        entry = proposals[row_id]
        if row.content_hash != entry.derived_hash:
            raise click.ClickException(
                f"{row_id!r}: sidecar derived_hash {entry.derived_hash!r} does not "
                f"match the manifest's current content_hash {row.content_hash!r} -- "
                "the sidecar is stale versus the manifest; regenerate before affirming"
            )

    existing_dispositions = (
        load_dispositions(dispositions_file) if dispositions_file.exists() else {}
    )

    merged = dict(existing_dispositions)
    affirmed_count = 0
    already_count = 0
    for row_id in selected:
        entry = proposals[row_id]
        new_disp = Disposition.parse(row_id, entry.disposition, affirmed_hash=entry.derived_hash)
        existing = existing_dispositions.get(row_id)
        if existing is None:
            merged[row_id] = new_disp
            affirmed_count += 1
        elif existing.spec == new_disp.spec and existing.affirmed_hash == new_disp.affirmed_hash:
            already_count += 1
        else:
            raise click.ClickException(
                f"{row_id!r}: {dispositions_file} already carries a conflicting "
                f"entry ({existing.spec!r}, affirmed_hash={existing.affirmed_hash!r}) "
                f"-- refusing to overwrite it with {new_disp.spec!r}"
            )

    write_dispositions(merged, dispositions_file)
    click.echo(
        f"affirmed {affirmed_count} row(s) ({already_count} already affirmed) into "
        f"{dispositions_file}"
    )
    sys.exit(0)


if __name__ == "__main__":
    cli()
