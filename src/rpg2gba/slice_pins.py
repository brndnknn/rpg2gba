"""Completeness checking for the pinned lists that must move together when a
chapter joins ``SLICE_MAP_IDS``.

Four lists have to be extended in lockstep every time a chapter is added, and
until 2026-09-08 exactly one of them was guarded:

===========================  =====================================  ==========
List                         Location                               Guarded by
===========================  =====================================  ==========
``SLICE_MAP_IDS``            ``tileset_converter/map_set.py``        ``test_chapter_atlas.py`` (== the atlas' built+in_progress set)
``SLICE_TRAINER_BATTLES``    ``trainer_converter/common.py``         this module
``SLICE_TRAINER_PICS``       ``trainer_converter/common.py``         this module
``STARTER_SPECIES``          ``species_converter/common.py``         this module
===========================  =====================================  ==========

The pre-existing tests (``test_trainer_battles.py``, ``test_species_gate.py``)
check that entries which *are* present are valid. Nothing checked the lists
were **complete** for the current ``SLICE_MAP_IDS``, so an omission was not
caught -- it surfaced later as a transpile abort, and CH05 hit three of them
one at a time:

    "Step 1 documented only SLICE_MAP_IDS; three more pinned lists ... were
    never mentioned. Each omission failed separately and looked unrelated to
    the last, costing a full loop."
    -- reference/archive/CH05_TODO.md, §Log

**The one-at-a-time discovery is the whole cost**, so every function here
reports *everything* missing in a single pass rather than raising on the first
problem. The lists themselves are fine as pinned append-only data; fork
trainer ids are assigned by position off ``PRISTINE_TRAINER_ANCHOR``, so this
module never proposes reordering one, only appending.

Two layers, because they answer different questions
---------------------------------------------------

**The gate** (:func:`check_emitted_trainers_are_pinned`) is exact and is what
fails a build: every ``TRAINER_*`` the transpiler actually *emits* into
``output/uranium-build/scripts/Map###.pory`` must be pinned. An unpinned
emitted constant is precisely the transpile abort this module exists to
pre-empt.

**The census** (:func:`census_trainer_events`) is broader and advisory: every
trainer-battle *event* on an in-slice map, whether or not the transpiler
emitted it. A trainer whose battle is still in the ``# UNHANDLED`` queue is
not a build risk today, but it is content silently missing from the ROM --
the three ``TRAINER_CLASS_BIKER`` events on Map019 (in slice since CH03) talk
to the player and never battle. The census is how that stops being invisible;
it is deliberately not an error, because pinning a trainer whose battle is
not emitted would stage a battle nothing references.

The reverse direction is legitimate and never reported: ``SLICE_TRAINER_BATTLES``
may contain keys no in-slice map event resolves to. The three
``TRAINER_THEO_*`` rival counter-picks are the standing example -- which one
fires depends on the player's starter, so the map event's own
``pbTrainerBattle`` call does not name any of them.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

#: `trainerbattle_single(TRAINER_X, ...)`, `trainerbattle_no_intro(TRAINER_X, ...)`,
#: and any other `trainerbattle_*` form the transpiler emits.
_EMITTED_TRAINER_RE = re.compile(r"\btrainerbattle_\w+\(\s*(TRAINER_[A-Z0-9_]+)")


class PinnedListError(RuntimeError):
    """One or more pinned lists are incomplete for the current `SLICE_MAP_IDS`.

    Always carries *every* gap found, never just the first -- see the module
    docstring for why that is the whole point.
    """


@dataclass(frozen=True)
class TrainerEventRef:
    """One trainer-battle event found on an in-slice map."""

    map_id: int
    event_id: int | None
    trainer_constant: str | None  #: None when unresolved in `ctx.trainers`
    trainer_class_constant: str
    display_name: str
    kind: str  #: "sight" or "rematch", per `extract_trainer_reference`
    emitted: bool  #: the transpiler emitted a `trainerbattle_*` for this constant
    pinned: bool  #: present in `SLICE_TRAINER_BATTLES`

    @property
    def status(self) -> str:
        if self.trainer_constant is None:
            return "unresolved"
        if self.emitted and not self.pinned:
            return "MISSING_PIN"
        if self.pinned and self.emitted:
            return "ok"
        if self.pinned:
            return "pinned-not-emitted"
        return "queued-not-pinned"


@dataclass
class PinReport:
    """Everything wrong with the pinned lists, collected in one pass."""

    missing_battles: list[str] = field(default_factory=list)
    missing_pics: list[str] = field(default_factory=list)
    missing_species: list[str] = field(default_factory=list)
    unmapped_classes: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)
    census: list[TrainerEventRef] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.missing_battles
            or self.missing_pics
            or self.missing_species
            or self.unmapped_classes
            or self.other
        )

    def format(self) -> str:
        """Render every gap at once, grouped by which list has to be edited."""
        blocks: list[str] = []
        if self.missing_battles:
            blocks.append(
                "SLICE_TRAINER_BATTLES (trainer_converter/common.py) -- APPEND these "
                f"{len(self.missing_battles)} key(s); the transpiler already emits a "
                "trainerbattle_* referencing them, so the build aborts without them.\n"
                "Order is load-bearing (fork ids are positional): append, never reorder.\n"
                + "".join(f"    {k}\n" for k in self.missing_battles)
            )
        if self.unmapped_classes:
            blocks.append(
                "TRAINER CLASSES -- unmapped in _CLASS_ENCOUNTER_MUSIC "
                "(trainer_converter/battles.py), or absent "
                "from the fork entirely. Each stays a human call -- CH05's single new "
                "class took two independent fork sources to justify, and that care is "
                "correct. What is batched is the LIST, so you make every call in one "
                "sitting instead of one per build (POST_CH05_REVIEW.md Tier 2).\n"
                + "".join(f"    {c}\n" for c in self.unmapped_classes)
            )
        if self.missing_pics:
            blocks.append(
                "SLICE_TRAINER_PICS (trainer_converter/common.py) -- APPEND a "
                "TrainerPicSpec for each of these (pics are keyed by the trainer's own "
                "Uranium class; internal_name is the class suffix); verify the trainertypes.dat "
                "id against a real Graphics/Characters/trainerNNN.png before pinning.\n"
                + "".join(f"    {p}\n" for p in self.missing_pics)
            )
        if self.missing_species:
            blocks.append(
                "STARTER_SPECIES (species_converter/common.py) -- APPEND these; "
                "stage whole evolution families, because build_staged_species fails "
                "loud on a dangling evolution target.\n"
                + "".join(f"    {s}\n" for s in self.missing_species)
            )
        if self.other:
            blocks.append(
                "Other staging problems reported in the same pass:\n"
                + "".join(f"    {o}\n" for o in self.other)
            )
        return "\n".join(blocks)

    def format_census(self) -> str:
        """Advisory: every trainer event on an in-slice map and its status."""
        if not self.census:
            return "no trainer-battle events found on any in-slice map"
        rows = sorted(self.census, key=lambda r: (r.map_id, r.event_id or 0))
        width = max(len(r.status) for r in rows)
        return "\n".join(
            f"  Map{r.map_id:03d} EV{r.event_id:03d} {r.status:<{width}} "
            f"{r.trainer_constant or '(unresolved)'} "
            f"[{r.trainer_class_constant}, {r.display_name!r}, {r.kind}]"
            for r in rows
        )


def emitted_trainer_constants(scripts_dir: Path, map_ids: list[int]) -> dict[str, list[int]]:
    """Every `TRAINER_*` the transpiler emitted a `trainerbattle_*` for, mapped
    to the in-slice maps that emit it.

    Reads the transpiler's own `.pory` output rather than re-deriving what it
    *would* emit -- `CLAUDE.md` §4.3. A map with no `.pory` on disk has not
    been transpiled and contributes nothing (it cannot abort a build it is not
    part of); callers that need transpile coverage should check for that
    separately.
    """
    found: dict[str, list[int]] = {}
    for map_id in map_ids:
        path = scripts_dir / f"Map{map_id:03d}.pory"
        if not path.is_file():
            continue
        for const in _EMITTED_TRAINER_RE.findall(path.read_text(encoding="utf-8")):
            found.setdefault(const, []).append(map_id)
    return found


def census_trainer_events(
    maps_dir: Path,
    map_ids: list[int],
    ctx,
    *,
    emitted: dict[str, list[int]],
    pinned: frozenset[str],
) -> list[TrainerEventRef]:
    """Every trainer-battle event on an in-slice map, with its pin/emit status.

    Identification is delegated to
    `conversion_agent.deterministic.extract_trainer_reference` -- the existing
    public extractor the debug map-viewer already uses -- so there is no second
    copy of the `pbTrainerBattle` parsing here (`CLAUDE.md` §4.3).
    """
    from rpg2gba.conversion_agent import deterministic as D

    refs: list[TrainerEventRef] = []
    for map_id in map_ids:
        path = maps_dir / f"Map{map_id:03d}.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for event in data.get("events", []):
            ref = D.extract_trainer_reference(event, ctx)
            if ref is None:
                continue
            refs.append(
                TrainerEventRef(
                    map_id=map_id,
                    event_id=event.get("id"),
                    trainer_constant=ref.trainer_constant,
                    trainer_class_constant=ref.trainer_class_constant,
                    display_name=ref.display_name,
                    kind=ref.kind,
                    emitted=ref.trainer_constant in emitted,
                    pinned=ref.trainer_constant in pinned,
                )
            )
    return refs


# Prefixes `battles.build_staged_battles` uses in its collected per-trainer
# error strings. Matching on them lets one staging run be re-grouped into the
# per-list buckets a human actually has to edit, instead of one flat blob.
_PIC_UNSTAGED = "is not staged in common.SLICE_TRAINER_PICS"
_NO_PIC_MAPPING = "no pic mapping"  # legacy wording, kept so old messages still file here
_NO_MUSIC_MAPPING = "no encounter-music mapping"
_SPECIES_UNAVAILABLE = "species not available"
_NOT_A_FORK_CLASS = "is not a TRAINER_CLASS_* constant the fork defines"


def _classify_staging_error(message: str, report: PinReport) -> None:
    """Sort one `build_staged_battles` error line into the list it implicates.

    Falls through to `report.other` on anything unrecognised rather than
    guessing -- an unclassified error is still reported, just not filed under a
    list it might not belong to.
    """
    if _NOT_A_FORK_CLASS in message:
        # A different problem from a missing *mapping*: the fork has no such
        # class at all, so no amount of editing our tables fixes it. §4.7 says
        # check the fork before concluding that; the message already names the
        # header to check.
        report.unmapped_classes.append(message)
        return
    if _NO_PIC_MAPPING in message or _NO_MUSIC_MAPPING in message:
        report.unmapped_classes.append(message)
        return
    if _PIC_UNSTAGED in message:
        # Prefer the full `TrainerPicSpec(<id>, '<name>')` the resolver names.
        m = re.search(r"append (TrainerPicSpec\([^)]*\))", message) or re.search(
            r"internal_name '([^']+)'", message
        )
        report.missing_pics.append(m.group(1) if m else message)
        return
    if _SPECIES_UNAVAILABLE in message:
        report.missing_species.extend(re.findall(r"SPECIES_[A-Z0-9_]+", message))
        return
    report.other.append(message)


def check_pinned_lists(
    *,
    out_dir: Path,
    engine_dir: Path,
    map_ids: list[int] | None = None,
) -> PinReport:
    """Derive what the four pinned lists *should* contain for the current
    `SLICE_MAP_IDS` and report every gap in one pass.

    `out_dir` is the build root (`output/uranium-build`), holding `maps/`,
    `scripts/` and `intermediate/`. `engine_dir` is the vendored fork.

    Never raises on a gap -- see :func:`require_complete_pinned_lists` for the
    fail-loud wrapper. Raises only if the inputs themselves are absent, since
    "no map JSON on disk" must not read as "no gaps".
    """
    from rpg2gba.conversion_agent import deterministic as D
    from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS
    from rpg2gba.trainer_converter import stage as trainer_stage
    from rpg2gba.trainer_converter.common import SLICE_TRAINER_BATTLES

    if map_ids is None:
        map_ids = list(SLICE_MAP_IDS)
    maps_dir, scripts_dir = out_dir / "maps", out_dir / "scripts"
    if not maps_dir.is_dir():
        raise PinnedListError(
            f"{maps_dir} does not exist -- decoded map JSON is the input this check "
            "derives from, and its absence is not evidence the pinned lists are complete"
        )
    # `load_species_manifest_constants` returns an empty set for an absent
    # manifest, which would make every party species read as unstaged and bury
    # the real gaps in ~a dozen false ones. Over-reporting is fail-safe but
    # useless; say so instead (§4.5).
    species_manifest = out_dir / "species" / "species_manifest.json"
    if not species_manifest.is_file():
        raise PinnedListError(
            f"{species_manifest} does not exist, so no species reads as staged and "
            "every trainer party would be reported as missing. Run "
            "`python scripts/stage_species.py` first (see "
            "reference/guides/slice_expansion_runbook.md)."
        )

    report = PinReport()
    pinned = frozenset(SLICE_TRAINER_BATTLES)
    emitted = emitted_trainer_constants(scripts_dir, map_ids)

    # --- Layer 1, the gate: emitted but unpinned is a build abort ------------
    for const, maps in sorted(emitted.items()):
        if const not in pinned:
            where = ", ".join(f"Map{m:03d}" for m in maps)
            report.missing_battles.append(f"{const}  (emitted by {where})")

    # --- Layer 2, the census: advisory, never an error -----------------------
    ctx = D.load_context(
        reference_dir=Path("reference"), intermediate_dir=out_dir / "intermediate"
    )
    report.census = census_trainer_events(
        maps_dir, map_ids, ctx, emitted=emitted, pinned=pinned
    )

    # --- Pics / classes / species, via one staging run over the full set -----
    # Rather than reimplementing the class->pic and party->species derivations,
    # run the real resolver over the union of pinned + newly-required keys.
    # build_staged_battles already collects every offending trainer's problems
    # instead of stopping at the first, so a single call yields the complete
    # picture -- which is exactly the batching Tier 2 asked for.
    selected = tuple(SLICE_TRAINER_BATTLES) + tuple(
        c for c in sorted(emitted) if c not in pinned
    )
    try:
        trainer_stage.stage_battles(
            uranium_src=Path("."), engine_dir=engine_dir, out_dir=out_dir / "trainers",
            selected=selected,
        )
    except (ValueError, FileNotFoundError, KeyError) as exc:
        for line in str(exc).splitlines():
            line = line.strip()
            if line and not line.endswith(":"):
                _classify_staging_error(line, report)

    # Dedupe while preserving the order each list was discovered in.
    for name in ("missing_battles", "missing_pics", "missing_species", "unmapped_classes", "other"):
        setattr(report, name, list(dict.fromkeys(getattr(report, name))))
    return report


def require_complete_pinned_lists(*, out_dir: Path, engine_dir: Path) -> PinReport:
    """:func:`check_pinned_lists`, but fail loud (`CLAUDE.md` §4.5) on any gap.

    Returns the report when everything is complete, so a caller can still log
    the advisory census.
    """
    report = check_pinned_lists(out_dir=out_dir, engine_dir=engine_dir)
    if not report.ok:
        raise PinnedListError(
            "the pinned lists are incomplete for the current SLICE_MAP_IDS.\n"
            "Everything missing is listed below -- fix it in one pass, not one "
            "build at a time.\n\n" + report.format()
        )
    return report


__all__ = [
    "PinnedListError",
    "PinReport",
    "TrainerEventRef",
    "census_trainer_events",
    "check_pinned_lists",
    "emitted_trainer_constants",
    "require_complete_pinned_lists",
]


# --- CLI ---------------------------------------------------------------------
#
# The command itself is defined once, in `pipeline.py` as `rpg2gba slice-pins`
# (§4.3 -- one definition, not two). This module form just delegates, so both
# invocations are the same code path.

if __name__ == "__main__":  # pragma: no cover
    from rpg2gba.pipeline import slice_pins_cmd

    raise SystemExit(slice_pins_cmd(standalone_mode=True))
