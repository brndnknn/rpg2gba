"""The chapter runner: drives a `Chapter` beat by beat from power-on (or from
a seeded embedded-save blob), producing structured results.

This is the shared core behind two consumers (ROM_TEST_DEV C5(b)):

- `__main__.py`'s `run` CLI, for interactive iteration
- a thin pytest wrapper (see `tests/test_runner.py`'s opt-in end-to-end test),
  for gate/CI runs

Three ROM_TEST_DEV items land here:

- **C5(b) `--from-beat`**: an iteration run may seed from an embedded-save
  blob captured after a previously-passing beat of the *same build*, rather
  than replaying every beat from a new game. The gate/regression bar stays
  full-from-new-game (`from_beat=None`). Blobs are derived artifacts under
  `output/`, keyed by the ROM's sha256 (D2a) — a blob whose hash doesn't
  match the ROM under test is refused loudly, never silently reused.
- **F3 rerun-once flake classification**: a failed chapter is re-run once
  automatically. `pass` (no failure), `flake` (failed then passed on rerun —
  a harness bug, logged, not investigated as a game bug), or `fail` (failed
  twice — a real failure).
- **G3(a)/(b)**: a failing run produces a self-contained repro bundle
  (screenshots, a state dump, the failing beat's identity, and a ROM stamped
  at the state just before the failing beat); a fully green run stamps the
  chapter-complete review ROM.
- **§2 contact sheet**: every run — green or red — captures a waypoint frame
  at each beat boundary and tiles them into PNG sheets (`contact_sheet.py`),
  so the by-eye categories a state assertion can't see get reviewed by
  scanning images rather than by replaying the chapter on a controller.

The emulator is only ever touched through the small surface `Chapter`/`Beat`
already define (`beat.run(emu)`, plus what `dump_save_blocks`/`stamp_rom`
need). Nothing here imports `mgba` directly or at module scope, so the
runner's own logic is testable with a stub emulator (see `tests/test_runner.py`).
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import signal
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from . import rules as playtest_rules
from .chapter import (
    Beat,
    Chapter,
    assert_chapter_locations_reachable,
    page_row_script,
    resolved_trigger_scripts,
)
from .contact_sheet import Waypoint, build_contact_sheet
from .contradictions import KIND_OFF_PLAN, Contradiction, ContradictionLedger
from .divergence import (
    PlanIndex,
    TriggerFact,
    WalkComparison,
    WalkedTile,
    compare_walk,
    load_plan_index_for_module,
)
from .frame_rule import check_frame_rule, refusal_error
from .stamp import ROM_BASE, build_blob, dump_save_blocks
from .visibility import check_object_visibility

if TYPE_CHECKING:  # runtime import is lazy so this module works without mgba
    from .emulator import Emulator

logger = logging.getLogger(__name__)

BOOT_FRAMES = 600          # new-game intro-skip, matches scenarios.py
SEEDED_BOOT_FRAMES = 900   # continue-from-embedded-save, matches test_playtest.py

# Q10: a per-beat wall-clock backstop. Per-primitive frame budgets
# (`walk_to`, `wait_for_map_grid`, ...) are the first line of defense against
# a hang; this is the top-level "something never returned control at all"
# backstop that CH03's B11 needed (finding E) -- without it, a hung beat
# doesn't fail, it just never ends, and the runner never gets a chance to
# mark anything behind it `not_run`.
#
# No per-beat override exists yet: `Beat` (chapter.py) is owned by another
# agent this session and has no budget field to read. If a beat genuinely
# needs a different budget, `chapter.py` needs a `hang_budget_s: int | None`
# field on `Beat` -- report that need rather than adding it here.
DEFAULT_BEAT_TIMEOUT_S = 120

EmulatorFactory = Callable[[Path, Path, "Path | None"], "Emulator"]


class RunnerError(RuntimeError):
    """A runner setup/provenance problem (bad --from-beat, stale blob, ...).

    Distinct from a beat failure (`ScenarioError`, caught and recorded as a
    `BeatOutcome`): this is a usage error that aborts the run outright.
    """


class BeatHangError(RuntimeError):
    """A beat exceeded its wall-clock hang budget (Q10).

    Distinct from an assertion failure so the outcome status and tally can
    tell "the game did something wrong" apart from "the harness never got
    an answer" -- CH03's B11 was the latter, and it read identically to
    silence until this existed.
    """


class BeatContinuityError(RuntimeError):
    """A beat's declared `at=`/`locations=` (Q13 slice 1, check 2 -- runtime
    continuity) disagrees with where the previous beat actually left the
    player. Raised, and caught, exactly where an ordinary beat assertion
    failure is (the beat that declared the mismatched location is the one
    that fails) -- this is deliberately the same failure shape as a
    `ScenarioError`, not a `RunnerError`: it is data about this build's
    beats, not a harness usage problem, so it gets the same repro bundle /
    contact sheet / flake-rerun treatment any other beat failure gets.

    This is the fix for `chapter.py`'s old "at= is descriptive metadata"
    contract: a beat whose declared position disagreed with the inherited
    one used to start silently somewhere else and fail later, often as a
    misleading pathfinding "stuck" error near the target. Now the
    disagreement itself is the error, raised at the point of disagreement,
    naming both positions.
    """


def _check_beat_continuity(beat: Beat, enter: dict[str, object],
                            emu: "Emulator") -> None:
    """Q13 slice 1, check 2: does `beat`'s declared entry position
    (`beat.entry_at`) match `enter` -- the position the PREVIOUS beat
    actually left the player at (or, for the chapter's first beat, the
    post-boot snapshot)?

    **Only `entry_at` is checked here -- never `locations`/`at=`.** This
    check used to read `beat.locations[0]` as the inherited-position claim,
    on the theory (recorded in the old docstring here and in
    `ChapterBuilder.beat`'s) that the corpus's own authoring convention
    always lists the entry door/threshold first in a multi-point beat. The
    first ROM run since this check landed (CH05, 2026-09-05) falsified that:
    an offline audit of every inherited CH01 beat against the recorded
    entry/exit positions from the last green run found 40 of 51 declared
    `locations[0]` values disagreed with the beat's recorded entry position
    (11 matched entry, 13 matched exit instead, 27 were neither), and
    multi-point beats scored *worse* than single-`at=` ones. The corpus-wide
    convention `at=`/`locations=` actually encode is "the tile the beat
    triggers on," not "the tile the beat starts on" -- see
    `ChapterBuilder.beat`'s docstring for the full measurement. `entry_at` is
    the separate, explicit opt-in a beat uses to make the inherited-position
    claim; a beat that doesn't set it makes no such claim, and is
    unconditionally exempt from this check -- no fallback to `locations[0]`.

    A beat with no declared `entry_at` is unaffected."""
    if beat.entry_at is None:
        return
    map_constant = beat.locations[0].map_constant if beat.locations else None
    if map_constant is None:
        raise BeatContinuityError(
            f"beat {beat.name!r}: declares entry_at={beat.entry_at!r} but no "
            "map_constant= / locations= to resolve it against -- entry_at "
            "needs a map to check continuity on")
    try:
        expected_group = emu.resolve_constant(f"MAP_GROUP({map_constant})")
        expected_num = emu.resolve_constant(f"MAP_NUM({map_constant})")
    except Exception as exc:  # noqa: BLE001 - reported as this beat's failure
        raise BeatContinuityError(
            f"beat {beat.name!r}: declared map_constant "
            f"{map_constant!r} could not be resolved against this "
            f"build's fork headers: {exc}") from exc

    actual_map = (enter["map_group"], enter["map_num"])
    expected_map = (expected_group, expected_num)
    actual_pos = tuple(enter["player_pos"])
    expected_pos = tuple(beat.entry_at)

    if actual_map != expected_map or actual_pos != expected_pos:
        raise BeatContinuityError(
            f"beat {beat.name!r}: declared entry_at={expected_pos} on "
            f"{map_constant} (map_group={expected_group}, "
            f"map_num={expected_num}) does not match where the previous "
            f"beat actually left the player: map_group="
            f"{actual_map[0]}, map_num={actual_map[1]}, player_pos="
            f"{actual_pos} -- the beat runs from wherever the previous beat "
            "left off, so this beat's declared entry position is wrong, "
            "the previous beat's exit is wrong, or the two beats are out "
            "of order (registration order is playthrough order, "
            "chapter.py's beat() docstring)")


@contextmanager
def _beat_timeout(seconds: int, beat_name: str):
    """Raise `BeatHangError` if the wrapped block doesn't return within
    `seconds`. Uses `SIGALRM`, so it only fires when control returns to the
    Python interpreter -- sufficient for the hangs this backstop targets
    (a harness-side loop that never re-checks its own frame budget), and a
    no-op (beat still runs, just untimed) on a platform without `SIGALRM`
    rather than a silent skip that pretends to be a real budget."""
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def _on_alarm(signum: int, frame: object) -> None:
        raise BeatHangError(
            f"beat {beat_name!r} exceeded its {seconds}s hang budget")

    previous = signal.signal(signal.SIGALRM, _on_alarm)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _default_emulator_factory(rom: Path, engine: Path,
                               screenshot_dir: "Path | None") -> "Emulator":
    from .emulator import Emulator

    return Emulator(rom, engine, screenshot_dir=screenshot_dir)


# -- state capture --------------------------------------------------------------

@dataclass(frozen=True)
class Snapshot:
    """Enough state to inspect a moment, or re-stamp a ROM positioned there.

    `blocks` is the same raw save-block dict `stamp.dump_save_blocks` /
    `stamp.build_blob` already work with, so a `Snapshot` can be turned into
    a stamped ROM without touching the live emulator again.
    """

    beat: str
    player_pos: tuple[int, int]
    map_location: tuple[int, int]
    blocks: dict[str, bytes]


def _install_drain_answers(emu: "Emulator", beats) -> None:  # noqa: ANN001
    """Hand the emulator every menu answer the arrival pages of `beats` are
    walked with, per map in beat order (`Beat.drain_answers`). The crossing
    that lands on such a page drains it; `settle_field` answers from these.
    A stub emulator without the attribute is left alone."""
    if not hasattr(emu, "drain_answers"):
        return
    plan: dict[tuple[int, int], list[int]] = {}
    for beat in beats:
        if beat.drain_answers is None:
            continue
        map_constant, answers = beat.drain_answers
        where = (emu.resolve_constant(f"MAP_GROUP({map_constant})"),
                 emu.resolve_constant(f"MAP_NUM({map_constant})"))
        plan.setdefault(where, []).extend(answers)
    emu.drain_answers = plan


def _snapshot(emu: "Emulator", beat_name: str) -> Snapshot:
    return Snapshot(beat=beat_name, player_pos=emu.player_pos(),
                     map_location=emu.map_location(), blocks=dump_save_blocks(emu))


def _loc(emu: "Emulator") -> dict[str, object]:
    """One player_pos()/map_location() read, shaped for `ObservedBeat`."""
    map_group, map_num = emu.map_location()
    return {"map_group": map_group, "map_num": map_num,
            "player_pos": list(emu.player_pos())}


def _loc_from_snapshot(snap: Snapshot) -> dict[str, object]:
    """Same shape as `_loc`, from a `Snapshot` already taken -- avoids a
    redundant player_pos()/map_location() read at the boot boundary."""
    return {"map_group": snap.map_location[0], "map_num": snap.map_location[1],
            "player_pos": list(snap.player_pos)}


class _WalkOracle:
    """Q13 slice 4's comparison oracle for one chapter run.

    Holds the approved route plan (if the chapter has one) and builds slice
    2's trigger overlays lazily, one per map the walk actually touches --
    eagerly building overlays for a chapter's declared map roster is what
    raised a bare `KeyError: 31` in slice 3, because a chapter's shortest
    hop between two of its own points can transit a map it never declares.

    **Why every trigger tile counts as "foreign" here, with no
    destination-script set.** `TriggerOverlay.foreign_tiles` exists to let
    the *solver* cross a tile it is deliberately aiming at. At runtime that
    exemption is already carried by the plan itself: the destination tile a
    beat interacts with is the last tile of the plan's own leg, so it is on
    the plan and can never be reported. Anything the route legitimately
    needs is on the plan; anything off the plan that fires a script is the
    B2/B3 shape by construction. Deriving a runtime destination-script set
    instead would mean joining manifest row ids (`map035/ev014/p1`) to
    Poryscript labels (`Map035_EventScript_EV014`) through a mapping that
    does not exist -- a second, guessable convention, for no gain.
    """

    def __init__(self, chapter_name: str, *,
                 plan: PlanIndex | None = None,
                 resolved_scripts: dict[int, set[str]] | None = None) -> None:
        self.plan = plan
        self.chapter_name = chapter_name
        # Per map, the page scripts an inherited beat already exercised, so
        # they are not foreign to this chapter's walks. Same set the route
        # solver plans against, from the same function, so the plan and the
        # check that grades the plan cannot disagree about what is foreign.
        self._resolved_scripts = resolved_scripts or {}
        self._triggers: dict[int, dict[tuple[int, int], tuple[TriggerFact, ...]]] = {}
        self._unavailable: set[int] = set()

    def mark_rows_resolved(self, rows: Sequence[str]) -> None:
        """Record that a beat of THIS chapter just passed, so the pages it
        claims stop being foreign to the walks that come after it.

        `resolved_trigger_scripts` narrows itself to INHERITED beats, on the
        grounds that "a chapter's own triggers stay foreign to each other:
        B3's trainer must not be excused for firing during an approach to
        B8." That reasoning is about a trigger the chapter has not resolved
        YET -- it does not survive the beat actually running. Once B3 has
        won, B3's tile fires nothing, and failing a later beat for stepping
        on it reports a script that cannot run.

        CH05's B14 is the case. Its approach walks west from B9's stop
        straight across Hiker Nunes' two event-touch tiles, and B9 defeated
        him two beats earlier -- "beat B14 left the approved route onto 2
        trigger tile(s) the plan does not walk: map 37 (22, 10) fires
        Map037_EV004_Page1" (step-7 run 14, 2026-09-06), which is B9's own
        battle page, already won.

        Order-aware on purpose, and called only on a PASS: a beat that
        failed did not necessarily resolve what it claims, and a beat that
        has not run yet resolves nothing. That keeps the narrowing's real
        intent -- an approach that walks a hot trigger is still a finding --
        while dropping the part of it that outlives the beat.

        **Known approximation, inherited from `resolved_trigger_scripts`.**
        "Resolved" here means "this page's beat passed", which holds for the
        latching shapes (a trainer's defeat flag, an item ball's one-shot)
        but not for a page guarded by a TEMP switch -- an `arrival_nudge`
        re-arms when the map is re-entered. The predecessor exemption makes
        exactly the same assumption about exactly the same pages, so this is
        the existing approximation reaching one chapter further, not a new
        one. A chapter that re-enters a map and walks a nudge cell would be
        excused wrongly; CH05 never returns to 1F after B8.
        """
        touched: set[int] = set()
        for row_id in rows:
            named = page_row_script(row_id)
            if named is None:
                continue  # seam/terrain rows name no page script
            map_id, script = named
            self._resolved_scripts.setdefault(map_id, set()).add(script)
            touched.add(map_id)
        # The overlay is built once per map and cached with the exemption
        # already applied, so a newly resolved page has to drop it.
        for map_id in touched:
            self._triggers.pop(map_id, None)

    @classmethod
    def for_chapter(cls, chapter: "Chapter | str") -> "_WalkOracle":
        """Never raises on a missing plan; a plan that exists and will not
        load is a real fault and propagates (CLAUDE.md §4.5).

        Takes the built `Chapter` where one is available, because the
        inherited-beat exemption is derived from its beats; a bare name still
        works (the stub runners in `tests/test_runner.py` pass one) and simply
        gets no exemption, which is the pre-existing behaviour.
        """
        if isinstance(chapter, str):
            return cls(chapter, plan=load_plan_index_for_module(chapter))
        if chapter.suite == "gen":
            # Operator ruling 2026-10-02: a route plan approves the HAND
            # suite's walks; a generated suite picks its own approaches
            # (CH05 gen meets Hiker Nunes from the south, over his own
            # event-touch tile) and has no plan of its own yet, so its
            # walks go uncompared rather than graded against the hand's.
            return cls(chapter.name, plan=None,
                       resolved_scripts=resolved_trigger_scripts(chapter))
        return cls(
            chapter.name,
            plan=load_plan_index_for_module(chapter.name),
            resolved_scripts=resolved_trigger_scripts(chapter),
        )

    def _overlay_for(self, map_id: int, emu: "Emulator") -> dict:
        cached = self._triggers.get(map_id)
        if cached is not None:
            return cached
        if map_id in self._unavailable:
            return {}
        from ..traversal.triggers import build_trigger_overlay
        from .divergence import foreign_trigger_index
        try:
            overlay = build_trigger_overlay(map_id, graph=emu.map_graph(map_id))
        except Exception as exc:  # noqa: BLE001
            # A map with no decoded trigger data cannot be checked, and that
            # is worth saying out loud once per map rather than per step --
            # but it is not a reason to fail a beat that is otherwise fine.
            logger.warning(
                "[%s] no trigger overlay for map %s (%s) -- walked tiles on "
                "that map are compared against the plan but cannot be "
                "classified as trigger crossings", self.chapter_name, map_id, exc)
            self._unavailable.add(map_id)
            return {}
        # Same exemption the route solver applies (`resolved_trigger_scripts`):
        # a page an INHERITED beat already exercised is not foreign to this
        # chapter's walks. Without it the oracle fails a beat for crossing a
        # tile whose script cannot fire -- CH05's approach must pass Timothy's
        # event-touch tile, and CH04:B4 defeated him 74 beats earlier.
        built = foreign_trigger_index(
            {map_id: overlay},
            destination_scripts={map_id: self._resolved_scripts.get(map_id, set())},
        )[map_id]
        self._triggers[map_id] = built
        return built

    def compare(self, beat: str, path: tuple[WalkedTile, ...],
                emu: "Emulator") -> WalkComparison:
        foreign = {}
        if self.plan is not None:
            for tile in path:
                if tile.map_id is not None and tile.map_id not in foreign:
                    foreign[tile.map_id] = self._overlay_for(tile.map_id, emu)
        return compare_walk(beat, path, plan=self.plan, foreign_triggers=foreign)


class DivergenceError(RuntimeError):
    """The walk left the approved route onto a tile that fires a script.

    This is the one divergence class that fails a beat. Every other
    divergence -- a re-plan around a patrolling NPC, a leg the offline
    graph models differently from the engine -- is recorded in Q8's
    contradiction ledger and carried, because `CH02:B14` showed that
    blocking on ambiguous evidence truncates real work.

    **Built and recorded, not raised.** The check runs *after* `beat.run`
    has already returned cleanly -- that is the whole point, since the
    beat's own assertions cannot see the tile it crossed on the way in --
    so there is no `try` left to catch it. Raising here would escape
    `_run_attempt` past the code that drains the ledger and writes the
    artifact, and re-entering the failure path would double-count the
    beat's carried findings. The class exists so the recorded message has
    a name a reader can grep for, and so a future caller that *is* inside
    a beat can raise it.
    """


def _close_walk(
    oracle: _WalkOracle, beat_name: str, emu: "Emulator",
    ledger: ContradictionLedger,
) -> tuple[tuple[WalkedTile, ...], WalkComparison | None]:
    """Read the beat's walked path, compare it, and drain the ledger.

    Called on every exit from a beat -- pass, fail and hang alike -- so a
    failed beat's path is recorded too. That is not a detail: a beat that
    hung or failed is the one whose walk you most want to look at, and the
    old two-point record went blank exactly there (`exit` is `None` for a
    beat that raised).

    Never raises. This is instrumentation wrapped around a result that is
    already decided; a comparison that cannot be made must not convert a
    passing beat into an error, and must not mask a failing one. A
    *violation* it does find is returned as data and acted on by the
    caller, not raised from here.
    """
    try:
        path = emu.walk_path()
    except AttributeError:
        # Stub emulators in `tests/test_runner.py` predate the walked path.
        return (), None
    # `_plan_route` records its graph-vs-live findings with no beat name --
    # it runs deep inside the walk stack and has no idea which beat it is
    # in. The boundary is where that is known, so stamp them here.
    try:
        emu.contradictions.drain_into(ledger, beat=beat_name)
    except AttributeError:
        pass
    if ":" in beat_name:
        # An inherited beat. `ChapterBuilder(predecessor=...)` prepends the
        # predecessor's beats renamed `<owner>:<name>` so the run can replay
        # its way to the state this chapter starts from, and the solver
        # drops exactly those groups when it plans (`routing.solver.
        # _solvable_groups`, and `chapter_manifest.route_model` drops the
        # same ones for the same reason). Comparing a replayed beat against
        # a plan that deliberately does not contain it would report every
        # tile of CH04's 60 inherited beats as off-plan -- thousands of
        # carried findings saying only "this beat belongs to another
        # chapter". The path is still recorded; only the comparison is
        # skipped.
        return path, None
    try:
        comparison = oracle.compare(beat_name, path, emu)
    except Exception as exc:  # noqa: BLE001 - see docstring
        logger.warning(
            "[%s] beat %s: walked-path comparison could not run (%s) -- the "
            "path is still recorded, but divergence is unenforced for it",
            oracle.chapter_name, beat_name, exc)
        return path, None
    for div in comparison.off_plan:
        # Q13.1 decision 3: an off-plan tile that fires nothing is evidence
        # the offline graph is wrong about the engine, not evidence the run
        # is wrong. Carried, never blocking.
        ledger.record(Contradiction(
            kind=KIND_OFF_PLAN,
            beat=beat_name,
            detail=(f"map {div.map_id} cell {div.cell} was walked at step "
                    f"{div.step_index} but the approved route "
                    f"({oracle.plan.chapter_id if oracle.plan else '?'}) "
                    "never covers it"),
            model="the approved route's tiles",
            measurement="the tile the ROM actually stood on",
            assumption="the run continued; a legitimate re-plan around a "
                       "moving object diverges on every run",
            map_id=div.map_id,
            cell=div.cell,
        ))
    return path, comparison


def _apply_frame_rule(outcome: BeatOutcome, beat_name: str,
                      emu: "Emulator") -> None:
    """Q7's enforced frame rule, applied to a beat that has just failed.

    Refusing the claim does not un-fail the beat -- the beat failed, and
    that stands. What is refused is the *recorded reason*: an unevidenced
    negative claim is replaced by the frame-rule refusal, so a later reader
    cannot take "nothing runs" at face value the way three CH04 write-ups
    were taken. The original text is preserved verbatim inside the
    refusal, never discarded.
    """
    try:
        marked = emu.frames_marked()
        screenshots = emu.screenshot_dir is not None
    except AttributeError:
        return  # a stub emulator that captures nothing
    result = check_frame_rule(outcome.error, frames_marked=marked,
                              screenshots_enabled=screenshots)
    outcome.frame_rule = result.to_dict()
    if not result.refused:
        return
    claim = outcome.error or ""
    err = refusal_error(beat_name, claim, result)
    logger.error("[frame rule] %s", err)
    outcome.error = str(err)
    outcome.refused_claim = claim


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_blob_to_rom(rom: Path, out: Path, blob: bytes, file_offset: int) -> None:
    """Patch `blob` into a copy of `rom` at `file_offset`. `rom` must have a
    zero-filled blob region there (mirrors `stamp.stamp_rom`'s check, but
    works from a stored `Snapshot`'s blob rather than a live `Emulator`)."""
    data = bytearray(rom.read_bytes())
    if data[file_offset : file_offset + len(blob)] != bytes(len(blob)):
        raise RunnerError(
            f"blob region at {file_offset:#x} in {rom} is not zero-filled — "
            "already stamped, or symbol/ROM mismatch")
    data[file_offset : file_offset + len(blob)] = blob
    out.write_bytes(data)


# -- results ----------------------------------------------------------------

@dataclass
class BeatOutcome:
    """One beat's result.

    `status` is `"not_run"` for every beat until it actually executes
    (Q10/finding E) -- the runner pre-populates every beat in the chapter
    with `"not_run"` before the attempt starts, so a chapter that stops
    early reports the beats behind the stopping point explicitly rather
    than the silence that hid CH03's B13-B18/B25 behind a hung B11.

    `rule_version` is the rule-set version (`rules.py`) this beat was
    evaluated under: the running chapter's own version for its own beats,
    or the owning ancestor chapter's last recorded version for a replayed
    predecessor beat (Q7.3) -- see `rules.effective_rule_version`.
    """

    name: str
    description: str
    status: str  # "not_run" | "pass" | "fail" | "hang"
    error: str | None = None
    traceback: str | None = None
    rule_version: int | None = None
    # Q7's frame rule (`frame_rule.py`). `frame_rule` is the verdict dict
    # for whatever claim this beat's failure made; `refused_claim` holds
    # the original text when the rule refused it, so nothing is lost --
    # `error` then carries the refusal instead.
    frame_rule: dict[str, object] | None = None
    refused_claim: str | None = None


@dataclass(frozen=True)
class ObservedBeat:
    """Where the player actually was over one beat, for the debug map viewer
    (observed-vs-planned overlay). `enter`/`exit` are dicts shaped
    `{"map_group": int, "map_num": int, "player_pos": [x, y]}`, or `None`
    for `exit` when the beat raised or hung.

    `path` is Q13.2's walked tile sequence -- every tile the walker actually
    stood on during this beat. Until slice 4 this record held `enter`/`exit`
    only, two points per beat, which cannot show what happened *between*
    them; CH04's B3 walked through Timothy's event-touch tile, fought the
    wrong trainer, and passed both guards, and this list is the artifact
    that would have shown it the first time it happened.

    `comparison` is the walked-vs-planned verdict for this beat
    (`divergence.WalkComparison`), or `None` when the chapter carries no
    approved route plan -- the ordinary state of every chapter gated before
    CH05 (`PROJECT_TODO.md` #67).
    """

    beat: str
    status: str  # "pass" | "fail" | "hang"
    enter: dict[str, object] | None
    exit: dict[str, object] | None
    path: tuple["WalkedTile", ...] = ()
    comparison: "WalkComparison | None" = None


@dataclass
class AttemptResult:
    """One full playthrough attempt (new-game or seeded)."""

    passed: bool
    beats: list[BeatOutcome]
    pristine_rom: Path
    final_emulator: "Emulator | None" = None
    last_snapshot: Snapshot | None = None
    screenshot_dir: Path | None = None
    waypoints: list[Waypoint] = field(default_factory=list)
    observed_beats: list[ObservedBeat] = field(default_factory=list)
    # The attempt's working ROM copy. It outlives the attempt on purpose:
    # `final_emulator` is still running on it, and stamping the green review
    # ROM drives that emulator through an in-game save, which needs its .sav
    # to actually land on disk. `run_chapter` deletes it once every consumer
    # is done.
    scratch_rom: Path | None = None
    # Q8's carried findings for this attempt. Never affects `passed`.
    contradictions: ContradictionLedger = field(
        default_factory=ContradictionLedger)

    @property
    def failed_beat(self) -> BeatOutcome | None:
        """The beat that stopped this attempt, whether it raised (`"fail"`)
        or exceeded its hang budget (`"hang"`) -- both stop the run the same
        way and both want a repro bundle."""
        return next((b for b in self.beats if b.status in ("fail", "hang")), None)


@dataclass(frozen=True)
class BeatTally:
    """Generated from a `BeatOutcome` list -- never hand-assembled (§5.8:
    the old "N/N" figure was prose nothing checked). `total` is the number
    of beats this attempt covered (the whole chapter from a new game, or the
    tail from `--from-beat`'s start index onward)."""

    total: int
    run: int
    passed: int
    failed: int
    hung: int
    not_run: int

    def render(self) -> str:
        return (f"{self.run}/{self.total} run, {self.passed} passed, "
                f"{self.failed} failed, {self.hung} hung, "
                f"{self.not_run} not run")


def compute_tally(beats: list[BeatOutcome]) -> BeatTally:
    total = len(beats)
    passed = sum(1 for b in beats if b.status == "pass")
    failed = sum(1 for b in beats if b.status == "fail")
    hung = sum(1 for b in beats if b.status == "hang")
    not_run = sum(1 for b in beats if b.status == "not_run")
    return BeatTally(total=total, run=total - not_run, passed=passed,
                      failed=failed, hung=hung, not_run=not_run)


@dataclass
class ChapterRunResult:
    chapter: str
    verdict: str  # "pass" | "flake" | "fail"
    attempts: list[AttemptResult] = field(default_factory=list)
    stamped_rom: Path | None = None
    bundle_dir: Path | None = None
    flake_log: Path | None = None
    contact_sheet: list[Path] = field(default_factory=list)
    tally: BeatTally | None = None
    # The rule-set version (rules.py) this run recorded as passed under --
    # only set on a full (from_beat=None), verdict="pass" run; a seeded
    # partial run never re-verifies the chapter's earlier beats, so it must
    # never advance the recorded version (Q7.3).
    rule_set_version: int | None = None


# -- blob provenance (D1b / D2a) ---------------------------------------------

def blob_paths(blobs_dir: Path, chapter: str, beat: str) -> tuple[Path, Path]:
    chapter_dir = blobs_dir / chapter
    return chapter_dir / f"{beat}.blob", chapter_dir / f"{beat}.json"

def prefix_fingerprint(chapter: Chapter, beat_name: str) -> str:
    """What a seed sitting before `beat_name` was produced by: the name and
    `Beat.source_digest` of every earlier beat, in order. A regenerated or
    reordered earlier beat changes it; a harness fix does not (by design --
    resuming after a harness fix is the point)."""
    digest = hashlib.sha256()
    for beat in chapter.beats[:chapter.index_of(beat_name)]:
        digest.update(f"{beat.name}\t{beat.source_digest}\n".encode("utf-8"))
    return digest.hexdigest()


def persist_seed_blob(blobs_dir: Path, chapter: str, rom: Path,
                       snapshot: Snapshot, emu: "Emulator", *,
                       prefix_sha256: str) -> None:
    """Record `snapshot` as the seed for `snapshot.beat`, tagged with the
    ROM's hash and the beats before it (`prefix_fingerprint`) so a later
    `--from-beat` run can refuse a stale blob."""
    blob_path, meta_path = blob_paths(blobs_dir, chapter, snapshot.beat)
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob = build_blob(emu.offsets, snapshot.blocks)
    blob_path.write_bytes(blob)
    meta = {
        "chapter": chapter,
        "seeds_beat": snapshot.beat,
        "rom_sha256": hash_file(rom),
        "prefix_sha256": prefix_sha256,
        "blob_offset": emu.symbols["gUraniumEmbeddedSave"],
        "created": datetime.now(timezone.utc).isoformat(),
        "player_pos": list(snapshot.player_pos),
        "map_location": list(snapshot.map_location),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def load_seed(blobs_dir: Path, chapter: str, beat: str, rom: Path, *,
              prefix_sha256: str) -> tuple[bytes, int]:
    blob_path, meta_path = blob_paths(blobs_dir, chapter, beat)
    if not blob_path.exists() or not meta_path.exists():
        raise RunnerError(
            f"no seed blob for chapter {chapter!r} beat {beat!r} at {blob_path} "
            "— run the chapter green from the start at least once on this "
            "build before using --from-beat")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    current_hash = hash_file(rom)
    if meta["rom_sha256"] != current_hash:
        raise RunnerError(
            f"seed blob for chapter {chapter!r} beat {beat!r} was captured "
            f"from a different ROM build (blob rom_sha256={meta['rom_sha256']}, "
            f"current={current_hash}) — blobs are invalidated by any ROM "
            "rebuild (ROM_TEST_DEV D2a); re-run the chapter green from the "
            "start to refresh it")
    if meta.get("prefix_sha256") != prefix_sha256:
        raise RunnerError(
            f"seed blob for chapter {chapter!r} beat {beat!r} is stale: the "
            "beats before it have changed since it was captured (or it "
            "predates prefix tracking) -- resume from an earlier beat whose "
            "seed is still current, or run from the start")
    return blob_path.read_bytes(), meta["blob_offset"] - ROM_BASE


# -- one attempt --------------------------------------------------------------

def _run_attempt(chapter: Chapter, rom: Path, engine: Path, *, attempt_no: int,
                  from_beat: str | None, output_root: Path,
                  emulator_factory: EmulatorFactory, blobs_dir: Path,
                  beat_timeout_s: int = DEFAULT_BEAT_TIMEOUT_S,
                  running_rule_version: int = playtest_rules.CURRENT_VERSION,
                  recorded_rule_versions: dict[str, int] | None = None,
                  ) -> AttemptResult:
    recorded_rule_versions = recorded_rule_versions or {}
    # Q13 slice 4. The oracle is resolved once per attempt: a plan that does
    # not exist is the ordinary case (route plans are enforced forward from
    # CH05), and a plan that exists but will not load is a fault that stops
    # the run here rather than silently leaving divergence unchecked.
    oracle = _WalkOracle.for_chapter(chapter)
    ledger = ContradictionLedger()
    start_idx = chapter.index_of(from_beat) if from_beat else 0
    scratch = output_root / f".{rom.stem}.{chapter.name}.attempt{attempt_no}.scratch.gba"
    scratch.parent.mkdir(parents=True, exist_ok=True)

    if start_idx > 0:
        blob, file_offset = load_seed(  # type: ignore[arg-type]
            blobs_dir, chapter.name, from_beat, rom,
            prefix_sha256=prefix_fingerprint(chapter, from_beat))  # type: ignore[arg-type]
        shutil.copy(rom, scratch)
        scratch.with_suffix(".sav").unlink(missing_ok=True)
        write_blob_to_rom(scratch, scratch, blob, file_offset)
        boot_frames = SEEDED_BOOT_FRAMES
    else:
        shutil.copy(rom, scratch)
        scratch.with_suffix(".sav").unlink(missing_ok=True)
        boot_frames = BOOT_FRAMES

    shots = output_root / f"_attempt{attempt_no}_{chapter.name}"
    beats_out: list[BeatOutcome] = []
    try:
        emu = emulator_factory(scratch, engine, shots)
        _install_drain_answers(emu, chapter.beats[start_idx:])
        emu.run(boot_frames)
        if start_idx > 0:
            # A seeded boot has never written `gStringVar4`: zero-filled RAM
            # decodes as spaces with no terminator, and the first
            # `settle_field` read raised "no EOS" (2026-09-27, `--from-beat`).
            # Terminate it so "no message yet" reads as None.
            emu.clear_field_message()
        last_snapshot = _snapshot(emu, chapter.beats[start_idx].name)
        # The frame the run starts on is itself worth an eye: a wrong spawn
        # map or a botched intro-skip shows up here before any beat runs.
        emu.waypoint("boot", note="seeded" if start_idx > 0 else "new game")
        observed: list[ObservedBeat] = []
        # Nothing moves between beats, so each beat's entry location is
        # exactly the previous beat's exit -- one location read per beat
        # boundary, not a second pass over the beat list.
        pending_enter = _loc_from_snapshot(last_snapshot)

        # Q10/finding E: every beat this attempt covers gets a "not_run"
        # outcome up front, in doc order. If the run stops early (fail or
        # hang), everything from that point on stays "not_run" instead of
        # silently missing from the report -- that silence is exactly what
        # let CH03 B13-B18/B25 hide behind B11's hang for two gate passes.
        beats_out.extend(
            BeatOutcome(
                b.name, b.description, "not_run",
                rule_version=playtest_rules.effective_rule_version(
                    chapter.name, b.name, running_rule_version,
                    recorded_rule_versions))
            for b in chapter.beats[start_idx:])

        for i, beat in enumerate(chapter.beats[start_idx:]):
            outcome = beats_out[i]
            logger.info("[%s] beat %s starting: %s", chapter.name, beat.name, beat.description)
            enter = pending_enter
            # Q13.2: the walked path is per beat, so it starts empty here
            # and is read below whichever way the beat ends. Degrades for a
            # stub emulator that predates the walked path -- this module's
            # docstring promises the runner's own logic stays testable
            # against one (`tests/test_runner.py`), and `_close_walk`
            # degrades on the same attribute at the other end.
            try:
                emu.clear_walk_path()
            except AttributeError:
                pass
            try:
                _check_beat_continuity(beat, enter, emu)
                with _beat_timeout(beat_timeout_s, beat.name):
                    beat.run(emu)
                    # PROJECT_TODO #137: every beat, not a floor kind -- an
                    # object RMXP has blanked is wrong wherever the walk
                    # meets it, not only on the row that blanks it.
                    if hasattr(emu, "object_events"):
                        check_object_visibility(emu, beat.name)
            except BeatHangError as exc:
                logger.error("[%s] beat %s HUNG: %s", chapter.name, beat.name, exc)
                outcome.status = "hang"
                outcome.error = str(exc)
                path, comparison = _close_walk(oracle, beat.name, emu, ledger)
                observed.append(
                    ObservedBeat(beat.name, "hang", enter, None, path, comparison))
                emu.waypoint(beat.name, "HANG", note=beat.description, failed=True)
                return AttemptResult(passed=False, beats=beats_out, pristine_rom=rom,
                                      final_emulator=emu, last_snapshot=last_snapshot,
                                      screenshot_dir=shots, waypoints=list(emu.waypoints),
                                      observed_beats=observed, scratch_rom=scratch,
                                      contradictions=ledger)
            except Exception as exc:  # noqa: BLE001 - beat failures are data, not bugs here
                import traceback as _tb
                tb_text = _tb.format_exc()
                logger.error("[%s] beat %s FAILED: %s", chapter.name, beat.name, exc)
                outcome.status = "fail"
                outcome.error = str(exc)
                outcome.traceback = tb_text
                # Q7's frame rule, checked BEFORE the failure waypoint below,
                # because that waypoint is the beat boundary that clears the
                # mark count. A refused claim replaces the recorded reason --
                # the beat still fails, but what goes in the record is "this
                # negative claim came with no frame" rather than an
                # unevidenced negative that a later reader would take at face
                # value. Both of CH04's confidently-wrong write-ups were
                # exactly that, and each was eventually corrected by the
                # operator hand-walking the ROM to produce the very frame the
                # rule now demands up front.
                _apply_frame_rule(outcome, beat.name, emu)
                path, comparison = _close_walk(oracle, beat.name, emu, ledger)
                observed.append(
                    ObservedBeat(beat.name, "fail", enter, None, path, comparison))
                emu.waypoint(beat.name, "FAILED", note=beat.description, failed=True)
                return AttemptResult(passed=False, beats=beats_out, pristine_rom=rom,
                                      final_emulator=emu, last_snapshot=last_snapshot,
                                      screenshot_dir=shots, waypoints=list(emu.waypoints),
                                      observed_beats=observed, scratch_rom=scratch,
                                      contradictions=ledger)

            path, comparison = _close_walk(oracle, beat.name, emu, ledger)
            if comparison is not None and comparison.failed:
                # Q13.1's blocking half. The beat's own assertions passed --
                # that is precisely the CH04 B3 shape: the walk to Larrie
                # crossed Timothy's event-touch tile, the wrong trainer was
                # fought, and BOTH guards went green. Nothing the beat can
                # assert about its end state sees the tile it crossed to get
                # there, so this check has to live outside the beat.
                cells = ", ".join(
                    f"map {d.map_id} {d.cell} fires "
                    f"{'/'.join(t.script for t in d.triggers) or '?'}"
                    for d in comparison.trigger_violations)
                exc = DivergenceError(
                    f"beat {beat.name} left the approved route onto "
                    f"{len(comparison.trigger_violations)} trigger tile(s) "
                    f"the plan does not walk: {cells} — the walk fired a "
                    "script that is not this beat's target")
                logger.error("[%s] beat %s FAILED: %s", chapter.name, beat.name, exc)
                outcome.status = "fail"
                outcome.error = str(exc)
                observed.append(
                    ObservedBeat(beat.name, "fail", enter, None, path, comparison))
                emu.waypoint(beat.name, "FAILED", note=beat.description, failed=True)
                return AttemptResult(passed=False, beats=beats_out, pristine_rom=rom,
                                      final_emulator=emu, last_snapshot=last_snapshot,
                                      screenshot_dir=shots, waypoints=list(emu.waypoints),
                                      observed_beats=observed, scratch_rom=scratch,
                                      contradictions=ledger)

            logger.info("[%s] beat %s passed", chapter.name, beat.name)
            # This beat's own pages are no longer foreign to the walks after
            # it (`_WalkOracle.mark_rows_resolved`). Inherited beats are
            # already covered wholesale by `resolved_trigger_scripts`, and
            # their `rows` name the PREDECESSOR's manifest, so skip them.
            if ":" not in beat.name:
                oracle.mark_rows_resolved(beat.rows)
            outcome.status = "pass"
            pending_enter = _loc(emu)
            observed.append(
                ObservedBeat(beat.name, "pass", enter, pending_enter, path, comparison))
            emu.waypoint(beat.name, note=beat.description)

            idx = chapter.index_of(beat.name)
            owner = playtest_rules.owning_chapter(chapter.name, beat.name)
            if (idx + 1 < len(chapter.beats) and owner != chapter.name
                    and playtest_rules.owning_chapter(
                        chapter.name, chapter.beats[idx + 1].name) == owner):
                # Inside a completed predecessor's replay: no seed. Each
                # capture is an in-game save, ~2.6s wall clock (measured
                # 2026-10-01: 179 of a CH02 attempt's 8.5 min). The boundary
                # into the next chapter still gets one.
                pass
            elif idx + 1 < len(chapter.beats):
                # Some beats legitimately end mid-scene with the field still
                # locked (moki B5 hands its running autorun to B6). Capturing a
                # seed there is not possible and would not be worth having: the
                # capture needs the engine's own save path to populate
                # SaveBlock1's party/object-event mirrors, and a state you
                # cannot save is a state that boots with a dead player object.
                # Skip the boundary rather than persist an unbootable seed —
                # `seeds` then simply does not offer that beat.
                if emu.field_locked():
                    logger.info("[%s] no seed for %s: field still locked at the "
                                "end of %s (mid-scene boundary)",
                                chapter.name, chapter.beats[idx + 1].name, beat.name)
                else:
                    # The snapshot is bookkeeping (persisting a seed blob for
                    # a later --from-beat run), not the thing under test --
                    # a failure here (e.g. save_in_game catching the beat's
                    # last action, a door warp, still mid-transition) must
                    # not take the whole run down. Degrade the same way a
                    # mid-scene lock already does: log it, skip the seed,
                    # keep going. Broad on purpose (mirrors the beat-failure
                    # catch above) -- this is bookkeeping, not the test.
                    try:
                        last_snapshot = _snapshot(emu, chapter.beats[idx + 1].name)
                        persist_seed_blob(
                            blobs_dir, chapter.name, rom, last_snapshot, emu,
                            prefix_sha256=prefix_fingerprint(
                                chapter, chapter.beats[idx + 1].name))
                    except Exception as exc:  # noqa: BLE001 - snapshot bookkeeping, not the beat under test
                        logger.warning(
                            "[%s] no seed for %s: snapshot failed at the end "
                            "of %s: %s", chapter.name,
                            chapter.beats[idx + 1].name, beat.name, exc)

        return AttemptResult(passed=True, beats=beats_out, pristine_rom=rom,
                              final_emulator=emu, last_snapshot=last_snapshot,
                              screenshot_dir=shots, waypoints=list(emu.waypoints),
                              observed_beats=observed, scratch_rom=scratch,
                              contradictions=ledger)
    except BaseException:
        # No AttemptResult escapes on this path, so nobody downstream can clean
        # up after us.
        _discard_scratch(scratch)
        raise


def _discard_scratch(scratch: Path | None) -> None:
    if scratch is None:
        return
    scratch.unlink(missing_ok=True)
    scratch.with_suffix(".sav").unlink(missing_ok=True)


# -- repro bundle (G3a) / flake log (F3) / green stamp (G3b) ------------------

def _build_bundle(chapter: Chapter, attempt: AttemptResult, output_root: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    bundle_dir = output_root / "bundles" / chapter.name / ts
    bundle_dir.mkdir(parents=True, exist_ok=True)

    if attempt.screenshot_dir and attempt.screenshot_dir.exists():
        shutil.copytree(attempt.screenshot_dir, bundle_dir / "screenshots",
                         dirs_exist_ok=True)

    failing = attempt.failed_beat
    (bundle_dir / "failure.json").write_text(json.dumps({
        "chapter": chapter.name,
        "chapter_doc": chapter.doc,
        "beat": failing.name if failing else None,
        "description": failing.description if failing else None,
        "error": failing.error if failing else None,
        "traceback": failing.traceback if failing else None,
    }, indent=2), encoding="utf-8")

    snap = attempt.last_snapshot
    if snap is not None:
        (bundle_dir / "state_dump.json").write_text(json.dumps({
            "beat": snap.beat,
            "player_pos": list(snap.player_pos),
            "map_location": list(snap.map_location),
            "blocks": {name: data.hex() for name, data in snap.blocks.items()},
        }, indent=2), encoding="utf-8")

        if attempt.final_emulator is not None:
            try:
                blob = build_blob(attempt.final_emulator.offsets, snap.blocks)
                file_offset = (attempt.final_emulator.symbols["gUraniumEmbeddedSave"]
                               - ROM_BASE)
                write_blob_to_rom(attempt.pristine_rom, bundle_dir / "pre_beat.gba",
                                   blob, file_offset)
            except RunnerError as exc:
                logger.warning("could not stamp pre-beat ROM for bundle: %s", exc)

    logger.info("[%s] repro bundle: %s", chapter.name, bundle_dir)
    return bundle_dir


def _log_flake(chapter: Chapter, first_attempt: AttemptResult, output_root: Path) -> Path:
    log_path = output_root / "flake_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    failing = first_attempt.failed_beat
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "chapter": chapter.name,
        "beat": failing.name if failing else None,
        "error": failing.error if failing else None,
        "note": ("harness flake (failed once, passed on rerun) — suspected "
                  "walk_to NPC body-block (ROM_TEST_DEV C6); log as a harness "
                  "bug, not a game bug"),
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    logger.warning("[%s] flake logged: %s", chapter.name, log_path)
    return log_path


def _stamp_green(chapter: Chapter, rom: Path, attempt: AttemptResult,
                  output_root: Path,
                  rule_set_version: int | None = None) -> Path:
    from .stamp import stamp_rom

    review_dir = output_root / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    out = review_dir / f"{chapter.name}-complete.gba"
    out.unlink(missing_ok=True)
    stamp_rom(rom, out, attempt.final_emulator)
    logger.info("[%s] green review ROM: %s", chapter.name, out)

    emu = attempt.final_emulator
    if emu is not None:
        meta = {
            "chapter": chapter.name,
            "kind": "chapter-complete",
            "rom_sha256": hash_file(rom),
            "blob_offset": emu.symbols["gUraniumEmbeddedSave"],
            "player_pos": list(emu.player_pos()),
            "map_location": list(emu.map_location()),
            "created": datetime.now(timezone.utc).isoformat(),
        }
        # Q7.3: the rule-set version this run passed under, written into the
        # gate stamp by the runner and only the runner -- never hand-edited.
        # `None` (a seeded --from-beat run) means "not recorded here": a
        # partial run never re-verifies the chapter's earlier beats, so it
        # must not claim a rule-set version for the whole chapter.
        if rule_set_version is not None:
            meta["rule_set_version"] = rule_set_version
        meta_path = out.with_suffix(".json")
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return out


def _classify(attempts: list[AttemptResult]) -> str:
    if attempts[0].passed:
        return "pass"
    if len(attempts) > 1 and attempts[1].passed:
        return "flake"
    return "fail"


def _assert_no_false_pass(chapter_name: str, verdict: str, tally: BeatTally) -> None:
    """A passing verdict must never coexist with an un-executed beat
    (Q10/finding E). Should be unreachable given `_classify`/`_run_attempt`'s
    own logic -- a stopped attempt is never `passed=True` -- but it is cheap
    to check and exactly the kind of silent drift this whole document is
    about closing off."""
    if verdict == "pass" and tally.not_run > 0:
        raise RunnerError(
            f"chapter {chapter_name!r} verdict computed as 'pass' with "
            f"{tally.not_run} beat(s) still 'not_run' -- refusing to "
            "report a false pass")


# -- observed-beats file (debug map viewer input) -----------------------------

def build_observed_beats_record(chapter: Chapter, attempts: list[AttemptResult],
                                 verdict: str, from_beat: str | None,
                                 rom_sha256: str | None,
                                 generated_at: str | None = None) -> dict:
    """Build the `output/playtest/observed_beats/<chapter>.json` payload.

    Walks `chapter.beats` in doc order so the file always lists every beat,
    even ones never reached this run. Location data comes from the *final*
    attempt (`attempts[-1]` -- the one `_classify` and the rest of
    `run_chapter` already treat as authoritative), so a flake's two attempts
    don't produce duplicate/conflicting entries: the beat that failed on
    attempt 1 but passed on attempt 2 is reported once, tagged "flake"
    rather than a plain "pass", since that instability is the point of a
    flake verdict. Beats before `from_beat`'s start index, or after a beat
    that failed with no rerun-and-pass, are "skipped" with null locations.

    **Schema 2 (Q13 slice 4)** adds three things to each beat and two to the
    file. Per beat: `path`, the tile sequence the walk actually covered
    (Q13.2); `divergence`, the walked-vs-planned verdict; and, on a failed
    beat, `frame_rule`/`refused_claim` from Q7's rule. Per file:
    `contradictions`, Q8's carried findings, and `conformance`, Q7's
    harness-vs-offline-graph summary drawn from those same findings rather
    than from a second hand-maintained expectation table -- a suite whose
    expectations the harness recorded goes green when the harness lies.

    The path is the reason the file grows, and that cost was taken
    deliberately: two points per beat cannot show what a walk crossed
    between them, which is exactly what CH04's B3 needed and did not have.
    """
    final_attempt = attempts[-1]
    by_name = {ob.beat: ob for ob in final_attempt.observed_beats}
    outcome_by_name = {bo.name: bo for bo in final_attempt.beats}

    flaky_beat = None
    if verdict == "flake":
        first_failed = attempts[0].failed_beat
        flaky_beat = first_failed.name if first_failed is not None else None

    beats: list[dict] = []
    for beat in chapter.beats:
        observed = by_name.get(beat.name)
        if observed is None:
            beats.append({"beat": beat.name, "status": "skipped",
                           "enter": None, "exit": None,
                           "path": [], "divergence": None,
                           "frame_rule": None, "refused_claim": None})
            continue
        status = "flake" if beat.name == flaky_beat else observed.status
        outcome = outcome_by_name.get(beat.name)
        beats.append({
            "beat": beat.name, "status": status,
            "enter": observed.enter, "exit": observed.exit,
            "path": [{"map_id": t.map_id, "map_group": t.map_group,
                      "map_num": t.map_num, "x": t.x, "y": t.y}
                     for t in observed.path],
            "divergence": (observed.comparison.to_dict()
                            if observed.comparison is not None else None),
            "frame_rule": outcome.frame_rule if outcome is not None else None,
            "refused_claim": (outcome.refused_claim
                               if outcome is not None else None),
        })

    ledger = final_attempt.contradictions
    return {
        "version": 2,
        "chapter": chapter.name,
        "suite": chapter.suite,
        "rom_sha256": rom_sha256,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "from_beat": from_beat,
        "beats": beats,
        "contradictions": ledger.to_list(),
        "conformance": ledger.conformance(),
    }


def _write_observed_beats(output_root: Path, chapter: Chapter,
                           attempts: list[AttemptResult], verdict: str,
                           from_beat: str | None, rom: Path) -> None:
    """Write the observed-beats file. Never raises -- this is debug-viewer
    bookkeeping, not the scenario under test, and a write failure here must
    not mask (or replace) the real run result."""
    try:
        rom_sha256 = hash_file(rom)
    except OSError as exc:
        logger.warning("[%s] could not hash rom for observed-beats file: %s",
                        chapter.name, exc)
        rom_sha256 = None
    try:
        record = build_observed_beats_record(chapter, attempts, verdict,
                                              from_beat, rom_sha256)
        out_dir = output_root / "observed_beats"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{chapter.name}.json"
        out_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 - bookkeeping, never the scenario error
        logger.exception("[%s] failed to write observed-beats file",
                          chapter.name)


# -- entry point --------------------------------------------------------------

def run_chapter(chapter: Chapter, rom: Path, engine: Path, *,
                 from_beat: str | None = None,
                 output_root: Path | None = None,
                 emulator_factory: EmulatorFactory | None = None,
                 rerun_on_failure: bool = True,
                 beat_timeout_s: int = DEFAULT_BEAT_TIMEOUT_S,
                 rule_versions_path: Path | None = None,
                 ) -> ChapterRunResult:
    """Run `chapter` beat by beat and return a structured result.

    `from_beat`: seed from a blob captured after the prior beat of *this
    exact build* (see `load_seed`); `None` (the default, and the only mode
    the gate/CI wrapper should use) always plays from a new game.
    `rerun_on_failure`: F3's auto-rerun-once flake classification.
    `beat_timeout_s`: Q10's per-beat hang budget (wall-clock).
    `rule_versions_path`: where each chapter's last-recorded green rule-set
    version lives (Q7.3) -- read to pin replayed ancestor beats to their own
    chapter's version, and written (only on a full, `from_beat=None`, pass
    verdict) to advance this chapter's own recorded version. `None` means
    `playtest_rules.DEFAULT_RECORDED_VERSIONS_PATH`, resolved at call time so
    the test suite can redirect it (#69/#70).
    """
    # Q13 slice 1, check 1: static, offline, no emulator time spent -- run
    # before anything else so a bad at=/locations= declaration is reported
    # immediately rather than discovered mid-attempt (or not at all, if the
    # chapter never walks that far). Raises ValueError, listing every
    # failing declaration, per `assert_chapter_locations_reachable`.
    assert_chapter_locations_reachable(chapter)

    output_root = output_root or Path("output") / "playtest"
    blobs_dir = output_root / "blobs"
    emulator_factory = emulator_factory or _default_emulator_factory
    if rule_versions_path is None:
        rule_versions_path = playtest_rules.DEFAULT_RECORDED_VERSIONS_PATH
    recorded_rule_versions = playtest_rules.load_recorded_versions(rule_versions_path)

    attempts: list[AttemptResult] = []
    attempts.append(_run_attempt(
        chapter, rom, engine, attempt_no=1, from_beat=from_beat,
        output_root=output_root, emulator_factory=emulator_factory,
        blobs_dir=blobs_dir, beat_timeout_s=beat_timeout_s,
        recorded_rule_versions=recorded_rule_versions))

    if not attempts[0].passed and rerun_on_failure:
        failing = attempts[0].failed_beat
        logger.warning("[%s] beat %s failed; rerunning once to classify "
                        "flake vs. real failure (F3)", chapter.name,
                        failing.name if failing else "?")
        attempts.append(_run_attempt(
            chapter, rom, engine, attempt_no=2, from_beat=from_beat,
            output_root=output_root, emulator_factory=emulator_factory,
            blobs_dir=blobs_dir, beat_timeout_s=beat_timeout_s,
            recorded_rule_versions=recorded_rule_versions))

    verdict = _classify(attempts)
    result = ChapterRunResult(chapter=chapter.name, verdict=verdict, attempts=attempts)
    result.tally = compute_tally(attempts[-1].beats)
    _assert_no_false_pass(chapter.name, verdict, result.tally)

    try:
        if verdict == "pass":
            # Only a full, un-seeded run re-verifies every beat (including
            # replayed ancestors), so only it may advance the recorded
            # rule-set version (Q7.3) -- a `--from-beat` iteration run stamps
            # a review ROM but never claims to have re-checked the chapter.
            rule_set_version = playtest_rules.CURRENT_VERSION if from_beat is None else None
            result.stamped_rom = _stamp_green(
                chapter, rom, attempts[-1], output_root,
                rule_set_version=rule_set_version)
            if rule_set_version is not None:
                playtest_rules.record_chapter_version(
                    rule_versions_path, chapter.name, rule_set_version)
                result.rule_set_version = rule_set_version
        elif verdict == "flake":
            result.flake_log = _log_flake(chapter, attempts[0], output_root)
        else:
            result.bundle_dir = _build_bundle(chapter, attempts[-1], output_root)

        # §2 contact sheet, from whichever attempt the verdict rests on: a red
        # run's sheet ships inside its repro bundle (ending on the failing
        # frame), a green run's sits beside the review ROM as the by-eye
        # artifact that replaces the boot walk.
        sheet_dir = result.bundle_dir or (output_root / "review")
        sheet_dir.mkdir(parents=True, exist_ok=True)
        for stale in sorted(sheet_dir.glob(f"{chapter.name}-sheet*.png")):
            stale.unlink()
        result.contact_sheet = build_contact_sheet(
            attempts[-1].waypoints, sheet_dir, chapter=chapter.name, verdict=verdict)
    finally:
        # Written even on a failing run (that's when it's most useful) and
        # even if the bundle/contact-sheet steps above raise -- this is the
        # debug map viewer's input, not the scenario result itself.
        _write_observed_beats(output_root, chapter, attempts, verdict, from_beat, rom)

    # Temp per-attempt screenshot dirs are either copied into the bundle
    # already or unneeded (pass/flake) — clean them up either way.
    for attempt in attempts:
        if attempt.screenshot_dir and attempt.screenshot_dir.exists():
            shutil.rmtree(attempt.screenshot_dir)
        _discard_scratch(attempt.scratch_rom)

    return result
