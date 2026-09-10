"""Freeze CH01-CH04's committed, gate-passed artifacts before re-derivation.

**Scaffolding for REDERIVATION_PLAN.md step P7. Scheduled for deletion at P10**
(see REDERIVATION_PLAN.md Phase C). Per CLAUDE.md §3: ~75 of scripts/'s ~95
files are spent one-offs and only three say so -- this is now one of the
three. Do not build on it after P10 closes; the freeze files it wrote are the
durable artifact, this script is not.

Implements PROJECT_TODO #62's safeguard: freeze the expected answers, derive,
diff, then write -- never derive-and-write in one pass, or a regression in
the derivation logic reads as a correct re-disposition. This script only
reads committed state and writes `reference/frozen/rederivation/CHnn.freeze.json`
for CH01-CH04 (CH04 in scope, CH05 is not -- it is the already-current
chapter, not part of this re-derivation).

Format precedent: `reference/frozen/archetype_expectations.json`.

CH01-CH03's manifests do not load through `chapter_manifest.schema.
row_from_dict` today (missing `reachability_consulted`/`terrain`), so this
script reads manifests as raw JSON and never through the loader -- going
through the loader would fail on exactly the three chapters that most need
freezing.

Usage:

    .venv/bin/python scripts/freeze_rederivation.py write
    .venv/bin/python scripts/freeze_rederivation.py check
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

import click

from rpg2gba.playtest.chapter import load_chapter

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
FREEZE_DIR = REPO_ROOT / "reference" / "frozen" / "rederivation"

AUTHORED = "2026-09-10"

# Chapters in scope for this freeze. CH05 is deliberately excluded -- it is
# the already-current chapter, not part of the CH01-CH04 re-derivation.
CHAPTERS = ("CH01", "CH02", "CH03", "CH04")

# Whether each chapter's manifest loads through row_from_dict today, and
# which fields it is missing if not (REDERIVATION_PLAN.md P7 scope facts).
LOADS_THROUGH_ROW_FROM_DICT: dict[str, bool] = {
    "CH01": False,
    "CH02": False,
    "CH03": False,
    "CH04": True,
}
MISSING_FIELDS: dict[str, list[str]] = {
    "CH01": ["reachability_consulted", "terrain"],
    "CH02": ["reachability_consulted", "terrain"],
    "CH03": ["reachability_consulted", "terrain"],
    "CH04": [],
}

# Which chapters have a committed dispositions file. Verified by git log
# --all: CH01/CH02/CH03's dispositions have never existed in this repo's
# history -- not merely deleted.
HAS_DISPOSITIONS: dict[str, bool] = {
    "CH01": False,
    "CH02": False,
    "CH03": False,
    "CH04": True,
}

CHAPTER_MODULE_PATHS: dict[str, str] = {
    "CH01": "src/rpg2gba/playtest/chapters/ch01.py",
    "CH02": "src/rpg2gba/playtest/chapters/ch02.py",
    "CH03": "src/rpg2gba/playtest/chapters/ch03.py",
    "CH04": "src/rpg2gba/playtest/chapters/ch04.py",
}

MANIFEST_PATHS: dict[str, str] = {
    ch: f"reference/manifests/{ch}.manifest.json" for ch in CHAPTERS
}

DISPOSITIONS_PATHS: dict[str, str] = {
    ch: f"reference/manifests/{ch}.dispositions.json" for ch in CHAPTERS
}


# A predecessor's beats arrive under a `CHnn:` name prefix; a chapter's own
# beats are bare. This is the only discriminator between the two in the
# composed list `load_chapter` returns.
_OWN_BEAT_NAME = re.compile(r"^(?!CH\d\d:)")


def _git_blob_sha(repo_relative_path: str) -> str:
    """`git rev-parse HEAD:<path>` -- fails loud if the path cannot be
    resolved, per the task's own standard: a freeze that cannot name its
    own provenance is worthless."""
    result = subprocess.run(
        ["git", "rev-parse", f"HEAD:{repo_relative_path}"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"cannot resolve git blob for {repo_relative_path!r}: "
            f"{result.stderr.strip()}")
    return result.stdout.strip()


def _read_json(repo_relative_path: str) -> Any:
    path = REPO_ROOT / repo_relative_path
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _manifest_rows_by_id(chapter: str) -> dict[str, dict[str, Any]]:
    """Raw JSON list -> dict keyed by row_id. Fails loud on a duplicate
    row_id, per the task's rule -- that would be a real data defect, not
    something to silently overwrite."""
    rows = _read_json(MANIFEST_PATHS[chapter])
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = row["row_id"]
        if row_id in by_id:
            raise ValueError(
                f"{chapter}: duplicate row_id {row_id!r} in "
                f"{MANIFEST_PATHS[chapter]} -- data defect, refusing to "
                "silently overwrite")
        by_id[row_id] = row
    return by_id


def _beat_dicts(chapter: str) -> list[dict[str, Any]]:
    """The chapter's gate-passed beats, in registration order, as the
    playtest module defines them today. `rows` will be an empty list for
    every CH01-CH04 beat (measured, REDERIVATION_PLAN.md P7 scope facts);
    the key is included anyway so P8's diff has a slot.

    A beat's `map_constant` is not a top-level `Beat` field -- it lives on
    each `BeatLocation` in `beat.locations`. We record the first location's
    map_constant (None for a beat with no declared location), which is also
    what the route solver treats as the beat's own interaction cell.

    `load_chapter` returns the COMPOSED beat list: a chapter's own beats
    plus, recursively, every predecessor's. So CH04's 74 beats are 13 of its
    own and 61 inherited, and CH01's 17 beats appear in all four freeze
    files. That is faithful to what the checker and beat model actually see,
    so the composed list is what gets frozen -- but an undifferentiated list
    would make CH04's beat diff light up whenever CH01 changed, which is
    noise, not signal. Hence `own`: a predecessor's beats arrive under a
    `CHnn:` name prefix (`CH01:B1`), the chapter's own are bare (`B1`), and
    that prefix is the discriminator. P8 should diff `own` beats per chapter
    and treat an inherited-beat diff as belonging to the chapter that owns
    it."""
    chapter_obj = load_chapter(chapter)
    result = []
    for beat in chapter_obj.beats:
        map_constant = beat.locations[0].map_constant if beat.locations else None
        result.append({
            "name": beat.name,
            "own": _OWN_BEAT_NAME.match(beat.name) is not None,
            "map_constant": map_constant,
            "group": beat.group,
            "rows": list(beat.rows),
        })
    return result


def _blind_spots(chapter: str) -> list[str]:
    if chapter in ("CH01", "CH02", "CH03"):
        return [
            "No dispositions.json ever existed for this chapter -- verified "
            "by `git log --all`, not merely deleted. There is no hand- or "
            "gate-authored expected answer to freeze on the disposition "
            "side at all.",
            "This freeze therefore protects only the manifest side for "
            "this chapter. PROJECT_TODO #62's safeguard (freeze, derive, "
            "diff) is structurally unavailable for this chapter's "
            "dispositions: there is nothing to diff a re-derivation "
            "against.",
            "P8's disposition adjudication for this chapter has to rest "
            "on evidence outside this freeze: the chapter doc under "
            "reference/chapters/, the gate-passed beats, and the booted "
            "ROM -- not on agreement with a number this freeze invents.",
            "The frozen manifest rows are themselves derivation output "
            "from commit de9343cb, not a hand-authored expectation. "
            "Agreement between this freeze and a re-derivation proves only "
            "that the derivation did not change since de9343cb -- never "
            "that de9343cb's output was right. REDERIVATION_PLAN.md §1's "
            "#90 precedent is the warning: a frozen expectation and a "
            "derivation that come from the same rule agree with each "
            "other and disagree with the ROM.",
        ]
    if chapter == "CH04":
        return [
            "CH04's dispositions ARE hand-authored and gate-passed (unlike "
            "CH01-CH03), but were hand-migrated from the retired "
            "deferred:/unreachable:<reason> vocabulary to blocked:<set> "
            "(REDERIVATION_PLAN.md §1) -- the migration itself is not "
            "independently re-verified by this freeze, only carried "
            "forward verbatim.",
            "REDERIVATION_PLAN.md §4 records a known live contradiction: "
            "CH04's DEFERRED_BEATS reason for map035/ev001 says CH05's "
            "entry beat claims that row, while ch05.py's module docstring "
            "says the opposite twice ('owned by CH04's manifest, not this "
            "one', 'not claimable here'), and successor_claims confirms "
            "CH05 claims neither p0 nor p1 in any beat's rows=. Only p0 is "
            "a valid `boundary` candidate; p1 is an arrival-nudge autorun, "
            "not a transfer, so `is_forward_crossing` rejects it regardless "
            "of how the p0 contradiction is settled. P8 must settle this "
            "pair; this freeze only records the contradiction as it stands "
            "today, it does not resolve it.",
        ]
    raise ValueError(f"no blind_spots defined for chapter {chapter!r}")


def build_freeze(chapter: str) -> dict[str, Any]:
    manifest_rows = _manifest_rows_by_id(chapter)
    manifest_blob = _git_blob_sha(MANIFEST_PATHS[chapter])

    dispositions: dict[str, Any] | None = None
    frozen_from: dict[str, Any] = {
        "manifest": {
            "path": MANIFEST_PATHS[chapter],
            "blob_sha": manifest_blob,
            "rows": len(manifest_rows),
            "loads_through_row_from_dict": LOADS_THROUGH_ROW_FROM_DICT[chapter],
            "missing_fields": MISSING_FIELDS[chapter],
        },
    }

    if HAS_DISPOSITIONS[chapter]:
        dispositions = _read_json(DISPOSITIONS_PATHS[chapter])
        disp_blob = _git_blob_sha(DISPOSITIONS_PATHS[chapter])
        frozen_from["dispositions"] = {
            "path": DISPOSITIONS_PATHS[chapter],
            "blob_sha": disp_blob,
            "entries": len(dispositions),
        }
    else:
        frozen_from["dispositions"] = None

    module_path = CHAPTER_MODULE_PATHS[chapter]
    module_blob = _git_blob_sha(module_path)
    beats = _beat_dicts(chapter)
    frozen_from["chapter_module"] = {
        "path": module_path,
        "blob_sha": module_blob,
        # Both counts, because only one of them is this chapter's work:
        # `beats` is the composed list the checker sees, `beats_own` is what
        # this chapter actually registered. See `_beat_dicts`.
        "beats": len(beats),
        "beats_own": sum(1 for b in beats if b["own"]),
        "beats_own_with_rows": sum(1 for b in beats if b["own"] and b["rows"]),
    }

    header = {
        "authored": AUTHORED,
        "chapter": chapter,
        "purpose": (
            f"Frozen expected state for {chapter}'s committed, gate-passed "
            "manifest rows, dispositions, and beats, captured before "
            "REDERIVATION_PLAN.md P8 regenerates anything -- PROJECT_TODO "
            "#62: freeze the expected answers, derive, diff, then write; "
            "never derive-and-write in one pass, or a regression in the "
            "derivation logic reads as a correct re-disposition."
        ),
        "frozen_from": frozen_from,
        "blind_spots": _blind_spots(chapter),
    }

    return {
        "_header": header,
        "manifest_rows": manifest_rows,
        "dispositions": dispositions,
        "beats": beats,
    }


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=False) + "\n"


def _freeze_path(chapter: str) -> Path:
    return FREEZE_DIR / f"{chapter}.freeze.json"


@click.group()
def cli() -> None:
    """Freeze CH01-CH04's committed rederivation-input state (P7)."""


@cli.command()
def write() -> None:
    """Regenerate all four freeze files on disk."""
    FREEZE_DIR.mkdir(parents=True, exist_ok=True)
    for chapter in CHAPTERS:
        data = build_freeze(chapter)
        path = _freeze_path(chapter)
        path.write_text(_dump(data), encoding="utf-8")
        logger.info("wrote %s (%d manifest rows, %d beats)",
                     path.relative_to(REPO_ROOT),
                     len(data["manifest_rows"]), len(data["beats"]))


@cli.command()
def check() -> None:
    """Regenerate in memory and diff against what is on disk.

    Exits non-zero if anything on disk would change -- useful to P8 as a
    guard against an accidental re-derive-and-write."""
    drift = False
    for chapter in CHAPTERS:
        data = build_freeze(chapter)
        expected = _dump(data)
        path = _freeze_path(chapter)
        if not path.exists():
            logger.error("%s: missing on disk", path.relative_to(REPO_ROOT))
            drift = True
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            logger.error("%s: drift detected", path.relative_to(REPO_ROOT))
            drift = True
        else:
            logger.info("%s: clean", path.relative_to(REPO_ROOT))
    if drift:
        raise SystemExit(1)
    logger.info("all freeze files match regeneration")


if __name__ == "__main__":
    cli()
