"""Diff a chapter's FROZEN P7 expected answers against a FRESHLY DERIVED
manifest/dispositions/beats, and classify every difference for a human.

**Scaffolding for REDERIVATION_PLAN.md step P8. Scheduled for deletion at
P10** (same lifetime as `scripts/freeze_rederivation.py`, which wrote the
freeze this script reads). Per CLAUDE.md §3, this is one of the three
scripts/ files that says it is a spent one-off in advance.

`freeze_rederivation.py check` verifies a freeze is faithful to the git blobs
it pinned -- it never compares the freeze to a regenerated manifest, because
that comparison only makes sense once P8 starts *regenerating* manifests,
which is exactly what this script's caller is about to do. This is that
missing half: it regenerates a chapter's manifest to a SCRATCH path (never
touching `reference/manifests/`), and diffs the regenerated rows, the
regenerated composed beat list, and (when the freeze carries one) the
authored dispositions file, against what P7 froze.

## Reading `manifest_rows` as raw JSON, not through `schema.row_from_dict`

`row_from_dict` does strict field-set equality against the CURRENT
`ManifestRow` dataclass. CH01-CH03's frozen manifests predate two fields
(`reachability_consulted`, `terrain` -- REDERIVATION_PLAN.md §8 item 2), so
they do not have that field set and `row_from_dict` raises on all three. This
script therefore reads `manifest_rows` out of the freeze as plain JSON dicts,
keyed by `row_id`, exactly as `freeze_rederivation._manifest_rows_by_id`
wrote them -- and reads the freshly generated manifest the same way (raw
JSON via `write_manifest` + `json.load`), so both sides of every comparison
are the same representation. Two extra keys the freeze predates on the old
side are simply absent there; the diff reports that as an added field on
that row like any other field difference, which is correct: those two fields
*are* new information the derivation now carries.

## Classification design (why this script does not auto-classify 1/2/3)

REDERIVATION_PLAN.md §1 names three categories a diff line can fall into:

  1. the derivation is better than the hand-authored answer (accept)
  2. the hand-authored answer was always wrong (accept, and note it)
  3. the derivation code regressed (reject, stop the pass)

Categories 1 and 2 are indistinguishable from the diff alone -- both look
like "the frozen value and the fresh value disagree, and the fresh one is
different." Telling them apart requires knowing whether the *old* answer was
ever correct, which is a fact about Uranium's source or the booted ROM, not
about this diff. Category 3 requires knowing whether the *derivation logic*
changed since the freeze was cut in a way that is wrong, which is a code
review judgment, not a diff-shape judgment. So this script does not attempt
1/2/3 classification. It does two narrower things instead:

* it emits every diff line in a form built for human adjudication (row id,
  field name, before -> after, and which of the three report sections it's
  in), and
* it applies exactly ONE mechanical, conservative auto-mark: a `page`-kind
  row's `unhandled` field changing `0 -> None` is marked `benign (schema
  default)` when-and-only-when the OLD value came from a manifest that
  predates a schema change making `None` the honest default for that shape
  of row (see `_BENIGN_UNHANDLED_NONE_FIELDS` below). This is narrow by
  design: it is the exact, already-adjudicated CH01 finding
  (`investigations/ch01_coverage.md` §1, category 1), encoded so a human
  re-running this script on CH01 is not asked to re-litigate a decision
  already made. It is not a general "None means fine" rule -- any OTHER
  field changing to/from `None`, or `unhandled` changing between two
  non-`0`/`None` values, is reported unmarked, for a human to adjudicate.

Exit code is nonzero whenever there is anything left to adjudicate (any row
added/removed, any field diff not auto-marked benign, any content_hash
change, any disposition diff, any own-beat diff) -- 0 only on a totally clean
diff. This makes the script usable as a CI-shaped gate even though it never
renders a verdict itself.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import click

from rpg2gba.chapter_manifest.generator import generate_chapter_manifest, write_manifest
from rpg2gba.playtest.chapter import load_chapter

REPO_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

FREEZE_DIR = REPO_ROOT / "reference" / "frozen" / "rederivation"
DEFAULT_BUILD_DIR = REPO_ROOT / "output" / "uranium-build"
DEFAULT_CHAPTERS_PATH = REPO_ROOT / "reference" / "chapters.json"

CHAPTERS = ("CH01", "CH02", "CH03", "CH04")

# The one mechanical, conservative auto-mark this script performs. See the
# module docstring's "Classification design" section. Keyed by the field
# name whose `0 -> None` transition is a known-benign schema default, not a
# regression -- currently just `unhandled`, and only for `kind="seam"` rows
# (a seam row has no event page for transpile_unhandled.jsonl to ever join
# against, so `None` -- "never measured" -- is the honest value; the frozen
# `0` predates the schema's own definition of what the field means for a
# page-less row). Extending this set is a deliberate, reviewed act, not a
# place to paper over an unrelated field.
_BENIGN_UNHANDLED_NONE_FIELDS = {"unhandled"}

# Fields the CURRENT schema carries that CH01-CH03's frozen manifests predate
# entirely (`reachability_consulted`, `terrain` -- REDERIVATION_PLAN.md §8
# item 2). Their absence from an old row is a schema-vintage fact, not a
# value that changed, so `_diff_rows` skips them outright rather than
# reporting "added" on every single row -- exactly what
# `investigations/ch01_coverage.md` §1 did by hand ("ignoring
# terrain/reachability_consulted, which the freeze predates"). This is
# unconditional on old-row absence, not per-chapter, because CH04's frozen
# rows already carry both fields (`LOADS_THROUGH_ROW_FROM_DICT["CH04"] =
# True` in freeze_rederivation.py) and so never trigger this skip.
_SCHEMA_ADDITIONS_NOT_IN_OLD_FREEZES = {"reachability_consulted", "terrain"}


# --- data model for one diff result -----------------------------------------


@dataclass
class FieldDiff:
    row_id: str
    field: str
    before: object
    after: object
    benign: bool = False
    benign_reason: str | None = None


@dataclass
class ChapterDiff:
    chapter: str
    rows_added: list[str] = field(default_factory=list)
    rows_removed: list[str] = field(default_factory=list)
    field_diffs: list[FieldDiff] = field(default_factory=list)
    content_hash_diffs: list[FieldDiff] = field(default_factory=list)
    dispositions_note: str | None = None
    dispositions_added: list[str] = field(default_factory=list)
    dispositions_removed: list[str] = field(default_factory=list)
    dispositions_changed: list[FieldDiff] = field(default_factory=list)
    beats_added: list[str] = field(default_factory=list)
    beats_removed: list[str] = field(default_factory=list)
    beats_changed: list[FieldDiff] = field(default_factory=list)
    fresh_row_count: int = 0
    frozen_row_count: int = 0
    # `<field> -> number of rows on which it was skipped as a schema-vintage
    # absence`. Counted, not just performed: this whole task exists to stop a
    # freeze silently encoding a blind spot, so a skip that never appears in
    # the output is the same failure in miniature. It does NOT make
    # `has_anything_to_adjudicate` true -- an absent field is not a diff --
    # but a reader must be able to see how much the tool declined to compare.
    schema_addition_skips: dict[str, int] = field(default_factory=dict)

    @property
    def unresolved_field_diffs(self) -> list[FieldDiff]:
        return [d for d in self.field_diffs if not d.benign]

    @property
    def has_anything_to_adjudicate(self) -> bool:
        return bool(
            self.rows_added
            or self.rows_removed
            or self.unresolved_field_diffs
            or self.content_hash_diffs
            or self.dispositions_added
            or self.dispositions_removed
            or self.dispositions_changed
            or self.beats_added
            or self.beats_removed
            or self.beats_changed
        )


# --- loading the two sides --------------------------------------------------


def _load_freeze(chapter: str) -> dict:
    path = FREEZE_DIR / f"{chapter}.freeze.json"
    if not path.exists():
        raise click.ClickException(
            f"no freeze for {chapter} at {path}; run "
            "scripts/freeze_rederivation.py write first"
        )
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _generate_fresh_rows(chapter: str, *, build_dir: Path, chapters_path: Path) -> dict:
    """Regenerate the chapter's manifest to a SCRATCH path (never
    `reference/manifests/`) and read it back as raw JSON, the same
    representation the freeze uses -- never through `schema.row_from_dict`,
    for the reason in the module docstring."""
    rows = generate_chapter_manifest(chapter, build_dir=build_dir, chapters_path=chapters_path)
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp) / f"{chapter}.manifest.scratch.json"
        write_manifest(rows, scratch)
        with scratch.open(encoding="utf-8") as f:
            raw = json.load(f)
    by_id: dict[str, dict] = {}
    for row in raw:
        by_id[row["row_id"]] = row
    return by_id


_OWN_BEAT_PREFIX_RE = re.compile(r"^(?!CH\d\d:)")


def _generate_fresh_beats(chapter: str) -> list[dict]:
    """Mirrors `freeze_rederivation._beat_dicts` exactly, so the freeze and
    the fresh side are the same shape to diff."""
    chapter_obj = load_chapter(chapter)
    result = []
    for beat in chapter_obj.beats:
        map_constant = beat.locations[0].map_constant if beat.locations else None
        result.append({
            "name": beat.name,
            "own": _OWN_BEAT_PREFIX_RE.match(beat.name) is not None,
            "map_constant": map_constant,
            "group": beat.group,
            "rows": list(beat.rows),
        })
    return result


def _load_fresh_dispositions(chapter: str) -> dict | None:
    """Raw JSON of the currently-committed dispositions file, or None if it
    does not exist -- mirrors the freeze's own `dispositions: null`
    convention for CH01-CH03 (REDERIVATION_PLAN.md §8 item 1)."""
    path = REPO_ROOT / "reference" / "manifests" / f"{chapter}.dispositions.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


# --- diffing -----------------------------------------------------------------


def _diff_rows(frozen: dict[str, dict], fresh: dict[str, dict]) -> tuple[
    list[str], list[str], list[FieldDiff], list[FieldDiff], dict[str, int]
]:
    frozen_ids = set(frozen)
    fresh_ids = set(fresh)
    added = sorted(fresh_ids - frozen_ids)
    removed = sorted(frozen_ids - fresh_ids)

    field_diffs: list[FieldDiff] = []
    hash_diffs: list[FieldDiff] = []
    skips: dict[str, int] = {}
    for row_id in sorted(frozen_ids & fresh_ids):
        old_row = frozen[row_id]
        new_row = fresh[row_id]
        all_fields = sorted(set(old_row) | set(new_row))
        for f_name in all_fields:
            if f_name in _SCHEMA_ADDITIONS_NOT_IN_OLD_FREEZES and f_name not in old_row:
                skips[f_name] = skips.get(f_name, 0) + 1
                # CH01-CH03's frozen manifests predate these two fields
                # entirely (REDERIVATION_PLAN.md §8 item 2; freeze README).
                # Their key is simply absent from the old row -- not a
                # comparable "value changed", so this is not a diff line at
                # all, per the ch01_coverage.md precedent that ignores them.
                continue
            old_val = old_row.get(f_name, "<absent: field not in frozen row>")
            new_val = new_row.get(f_name, "<absent: field not in fresh row>")
            if old_val == new_val:
                continue
            diff = FieldDiff(row_id=row_id, field=f_name, before=old_val, after=new_val)
            if f_name == "content_hash":
                hash_diffs.append(diff)
                continue
            if (
                f_name in _BENIGN_UNHANDLED_NONE_FIELDS
                and old_val == 0
                and new_val is None
                and new_row.get("kind") == "seam"
            ):
                diff.benign = True
                diff.benign_reason = (
                    "seam row's unhandled has no event page to measure against; "
                    "None is the schema-correct 'never measured' value, not a "
                    "regression from the frozen 0 (investigations/ch01_coverage.md §1)"
                )
            field_diffs.append(diff)
    return added, removed, field_diffs, hash_diffs, skips


def _diff_dispositions_values(
    chapter: str, frozen_dispositions: dict | None, fresh: dict | None,
) -> tuple[str | None, list[str], list[str], list[FieldDiff]]:
    """Pure comparison, no disk access -- split out from `_diff_dispositions`
    so tests can exercise the null-handling and diff logic with synthetic
    fixtures instead of real `reference/manifests/` state."""
    if frozen_dispositions is None and fresh is None:
        return (
            f"{chapter}: no dispositions file ever existed (frozen) and none exists now -- "
            "nothing to diff.",
            [], [], [],
        )
    if frozen_dispositions is None:
        return (
            f"{chapter}: freeze recorded no dispositions file (none ever existed for this "
            f"chapter -- reference/frozen/rederivation/README.md), but a dispositions file "
            f"now exists with {len(fresh)} row(s). This is new authored content, not a "
            "diff against a prior answer; review it on its own, not as an 'added' regression.",
            [], [], [],
        )
    if fresh is None:
        return (
            f"{chapter}: freeze recorded {len(frozen_dispositions)} disposition(s), but no "
            "dispositions file exists now. Investigate before proceeding -- an authored "
            "file should not disappear.",
            [], sorted(frozen_dispositions), [],
        )

    frozen_ids = set(frozen_dispositions)
    fresh_ids = set(fresh)
    added = sorted(fresh_ids - frozen_ids)
    removed = sorted(frozen_ids - fresh_ids)
    changed: list[FieldDiff] = []
    for row_id in sorted(frozen_ids & fresh_ids):
        if frozen_dispositions[row_id] != fresh[row_id]:
            changed.append(FieldDiff(
                row_id=row_id, field="disposition",
                before=frozen_dispositions[row_id], after=fresh[row_id],
            ))
    return None, added, removed, changed


def _diff_dispositions(chapter: str, frozen_dispositions: dict | None) -> tuple[
    str | None, list[str], list[str], list[FieldDiff]
]:
    fresh = _load_fresh_dispositions(chapter)
    return _diff_dispositions_values(chapter, frozen_dispositions, fresh)


def _diff_beats(frozen_beats: list[dict], fresh_beats: list[dict]) -> tuple[
    list[str], list[str], list[FieldDiff]
]:
    """Own beats only (REDERIVATION_PLAN.md §7 / freeze README: diff `own`
    beats per chapter; an inherited-beat diff belongs to the chapter that
    owns it, and would otherwise double-report predecessor changes on every
    descendant chapter)."""
    frozen_own = {b["name"]: b for b in frozen_beats if b["own"]}
    fresh_own = {b["name"]: b for b in fresh_beats if b["own"]}

    added = sorted(set(fresh_own) - set(frozen_own))
    removed = sorted(set(frozen_own) - set(fresh_own))
    changed: list[FieldDiff] = []
    for name in sorted(set(frozen_own) & set(fresh_own)):
        old_beat = frozen_own[name]
        new_beat = fresh_own[name]
        for key in ("map_constant", "group", "rows"):
            if old_beat.get(key) != new_beat.get(key):
                changed.append(FieldDiff(
                    row_id=name, field=key,
                    before=old_beat.get(key), after=new_beat.get(key),
                ))
    return added, removed, changed


def diff_chapter(
    chapter: str, *, build_dir: Path = DEFAULT_BUILD_DIR,
    chapters_path: Path = DEFAULT_CHAPTERS_PATH,
) -> ChapterDiff:
    freeze = _load_freeze(chapter)
    frozen_rows: dict[str, dict] = freeze["manifest_rows"]
    frozen_dispositions = freeze["dispositions"]
    frozen_beats: list[dict] = freeze["beats"]

    fresh_rows = _generate_fresh_rows(chapter, build_dir=build_dir, chapters_path=chapters_path)
    fresh_beats = _generate_fresh_beats(chapter)

    added, removed, field_diffs, hash_diffs, skips = _diff_rows(
        frozen_rows, fresh_rows)
    disp_note, disp_added, disp_removed, disp_changed = _diff_dispositions(
        chapter, frozen_dispositions)
    beats_added, beats_removed, beats_changed = _diff_beats(frozen_beats, fresh_beats)

    return ChapterDiff(
        chapter=chapter,
        rows_added=added,
        rows_removed=removed,
        field_diffs=field_diffs,
        content_hash_diffs=hash_diffs,
        dispositions_note=disp_note,
        dispositions_added=disp_added,
        dispositions_removed=disp_removed,
        dispositions_changed=disp_changed,
        beats_added=beats_added,
        beats_removed=beats_removed,
        beats_changed=beats_changed,
        fresh_row_count=len(fresh_rows),
        frozen_row_count=len(frozen_rows),
        schema_addition_skips=skips,
    )


# --- rendering ---------------------------------------------------------------


def _field_diff_to_dict(d: FieldDiff) -> dict:
    out = {"row_id": d.row_id, "field": d.field, "before": d.before, "after": d.after}
    if d.benign:
        out["benign"] = True
        out["benign_reason"] = d.benign_reason
    return out


def diff_to_dict(d: ChapterDiff) -> dict:
    return {
        "chapter": d.chapter,
        "frozen_row_count": d.frozen_row_count,
        "fresh_row_count": d.fresh_row_count,
        "rows_added": d.rows_added,
        "rows_removed": d.rows_removed,
        "schema_addition_skips": d.schema_addition_skips,
        "field_diffs": [_field_diff_to_dict(fd) for fd in d.field_diffs],
        "content_hash_diffs": [_field_diff_to_dict(fd) for fd in d.content_hash_diffs],
        "dispositions": {
            "note": d.dispositions_note,
            "added": d.dispositions_added,
            "removed": d.dispositions_removed,
            "changed": [_field_diff_to_dict(fd) for fd in d.dispositions_changed],
        },
        "beats": {
            "added": d.beats_added,
            "removed": d.beats_removed,
            "changed": [_field_diff_to_dict(fd) for fd in d.beats_changed],
        },
        "has_anything_to_adjudicate": d.has_anything_to_adjudicate,
    }


def render_text(d: ChapterDiff) -> str:
    lines: list[str] = []
    lines.append(f"=== {d.chapter}: manifest rows ===")
    lines.append(f"frozen: {d.frozen_row_count}  fresh: {d.fresh_row_count}")
    lines.append(f"added:   {len(d.rows_added)}")
    for row_id in d.rows_added:
        lines.append(f"  + {row_id}")
    lines.append(f"removed: {len(d.rows_removed)}")
    for row_id in d.rows_removed:
        lines.append(f"  - {row_id}")

    lines.append("")
    lines.append(f"content_hash changes: {len(d.content_hash_diffs)}"
                  + ("  *** SEVERITY: game data or its interpretation moved ***"
                     if d.content_hash_diffs else ""))
    for hd in d.content_hash_diffs:
        lines.append(f"  {hd.row_id}: content_hash {hd.before} -> {hd.after}")

    unresolved = d.unresolved_field_diffs
    benign = [fd for fd in d.field_diffs if fd.benign]
    lines.append("")
    lines.append(f"field diffs (excl. content_hash): {len(unresolved)} to adjudicate, "
                 f"{len(benign)} auto-marked benign")
    if d.schema_addition_skips:
        detail = ", ".join(
            f"{name} on {count} row(s)"
            for name, count in sorted(d.schema_addition_skips.items()))
        lines.append(
            f"  not compared (field absent from the frozen row, so there is no "
            f"before-value): {detail}")
    for fd in unresolved:
        lines.append(f"  {fd.row_id}  {fd.field}: {fd.before!r} -> {fd.after!r}")
    for fd in benign:
        lines.append(f"  (benign) {fd.row_id}  {fd.field}: {fd.before!r} -> {fd.after!r}"
                     f"  [{fd.benign_reason}]")

    lines.append("")
    lines.append(f"=== {d.chapter}: dispositions ===")
    if d.dispositions_note:
        lines.append(d.dispositions_note)
    else:
        lines.append(f"added:   {len(d.dispositions_added)}")
        for row_id in d.dispositions_added:
            lines.append(f"  + {row_id}")
        lines.append(f"removed: {len(d.dispositions_removed)}")
        for row_id in d.dispositions_removed:
            lines.append(f"  - {row_id}")
        lines.append(f"changed: {len(d.dispositions_changed)}")
        for fd in d.dispositions_changed:
            lines.append(f"  {fd.row_id}: {fd.before!r} -> {fd.after!r}")

    lines.append("")
    lines.append(f"=== {d.chapter}: own beats ===")
    lines.append(f"added:   {len(d.beats_added)}")
    for name in d.beats_added:
        lines.append(f"  + {name}")
    lines.append(f"removed: {len(d.beats_removed)}")
    for name in d.beats_removed:
        lines.append(f"  - {name}")
    lines.append(f"changed: {len(d.beats_changed)}")
    for fd in d.beats_changed:
        lines.append(f"  {fd.row_id}  {fd.field}: {fd.before!r} -> {fd.after!r}")

    lines.append("")
    lines.append(
        f"=== {d.chapter}: VERDICT === "
        + ("NOTHING TO ADJUDICATE" if not d.has_anything_to_adjudicate
           else "HAS DIFFERENCES TO ADJUDICATE (see above; category 1/2/3 per "
                "REDERIVATION_PLAN.md §1 is a human call, not this tool's)")
    )
    return "\n".join(lines)


# --- CLI ----------------------------------------------------------------------


@click.group()
def cli() -> None:
    """Diff a chapter's P7 freeze against a freshly derived manifest/dispositions/beats
    (REDERIVATION_PLAN.md P8). Read-only: never writes reference/manifests/ or reference/."""


@cli.command("diff")
@click.option("--chapter", required=True, type=click.Choice(CHAPTERS),
              help="Chapter id, e.g. CH01.")
@click.option("--build-dir", type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_BUILD_DIR,
              help="Converted-map build directory (default: output/uranium-build)")
@click.option("--chapters", "chapters_path", type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_CHAPTERS_PATH,
              help="Chapter/map chain JSON (default: reference/chapters.json)")
@click.option("--json", "as_json", is_flag=True, help="Emit structured JSON instead of text.")
def diff_cmd(chapter: str, build_dir: Path, chapters_path: Path, as_json: bool) -> None:
    """Regenerate CHAPTER's manifest to a scratch path and diff against its P7 freeze."""
    result = diff_chapter(chapter, build_dir=build_dir, chapters_path=chapters_path)
    if as_json:
        click.echo(json.dumps(diff_to_dict(result), indent=2, sort_keys=False))
    else:
        click.echo(render_text(result))
    sys.exit(1 if result.has_anything_to_adjudicate else 0)


if __name__ == "__main__":
    cli()
