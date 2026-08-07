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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .chapter import Chapter
from .contact_sheet import Waypoint, build_contact_sheet
from .stamp import ROM_BASE, build_blob, dump_save_blocks

if TYPE_CHECKING:  # runtime import is lazy so this module works without mgba
    from .emulator import Emulator

logger = logging.getLogger(__name__)

BOOT_FRAMES = 600          # new-game intro-skip, matches scenarios.py
SEEDED_BOOT_FRAMES = 900   # continue-from-embedded-save, matches test_playtest.py

EmulatorFactory = Callable[[Path, Path, "Path | None"], "Emulator"]


class RunnerError(RuntimeError):
    """A runner setup/provenance problem (bad --from-beat, stale blob, ...).

    Distinct from a beat failure (`ScenarioError`, caught and recorded as a
    `BeatOutcome`): this is a usage error that aborts the run outright.
    """


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


def _snapshot(emu: "Emulator", beat_name: str) -> Snapshot:
    return Snapshot(beat=beat_name, player_pos=emu.player_pos(),
                     map_location=emu.map_location(), blocks=dump_save_blocks(emu))


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
    name: str
    description: str
    status: str  # "pass" | "fail"
    error: str | None = None
    traceback: str | None = None


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
    # The attempt's working ROM copy. It outlives the attempt on purpose:
    # `final_emulator` is still running on it, and stamping the green review
    # ROM drives that emulator through an in-game save, which needs its .sav
    # to actually land on disk. `run_chapter` deletes it once every consumer
    # is done.
    scratch_rom: Path | None = None

    @property
    def failed_beat(self) -> BeatOutcome | None:
        return next((b for b in self.beats if b.status == "fail"), None)


@dataclass
class ChapterRunResult:
    chapter: str
    verdict: str  # "pass" | "flake" | "fail"
    attempts: list[AttemptResult] = field(default_factory=list)
    stamped_rom: Path | None = None
    bundle_dir: Path | None = None
    flake_log: Path | None = None
    contact_sheet: list[Path] = field(default_factory=list)


# -- blob provenance (D1b / D2a) ---------------------------------------------

def blob_paths(blobs_dir: Path, chapter: str, beat: str) -> tuple[Path, Path]:
    chapter_dir = blobs_dir / chapter
    return chapter_dir / f"{beat}.blob", chapter_dir / f"{beat}.json"

def persist_seed_blob(blobs_dir: Path, chapter: str, rom: Path,
                       snapshot: Snapshot, emu: "Emulator") -> None:
    """Record `snapshot` as the seed for `snapshot.beat`, tagged with the
    ROM's hash so a later `--from-beat` run can refuse a stale blob."""
    blob_path, meta_path = blob_paths(blobs_dir, chapter, snapshot.beat)
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob = build_blob(emu.offsets, snapshot.blocks)
    blob_path.write_bytes(blob)
    meta = {
        "chapter": chapter,
        "seeds_beat": snapshot.beat,
        "rom_sha256": hash_file(rom),
        "blob_offset": emu.symbols["gUraniumEmbeddedSave"],
        "created": datetime.now(timezone.utc).isoformat(),
        "player_pos": list(snapshot.player_pos),
        "map_location": list(snapshot.map_location),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def load_seed(blobs_dir: Path, chapter: str, beat: str, rom: Path) -> tuple[bytes, int]:
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
    return blob_path.read_bytes(), meta["blob_offset"] - ROM_BASE


# -- one attempt --------------------------------------------------------------

def _run_attempt(chapter: Chapter, rom: Path, engine: Path, *, attempt_no: int,
                  from_beat: str | None, output_root: Path,
                  emulator_factory: EmulatorFactory, blobs_dir: Path) -> AttemptResult:
    start_idx = chapter.index_of(from_beat) if from_beat else 0
    scratch = output_root / f".{rom.stem}.{chapter.name}.attempt{attempt_no}.scratch.gba"
    scratch.parent.mkdir(parents=True, exist_ok=True)

    if start_idx > 0:
        blob, file_offset = load_seed(blobs_dir, chapter.name, from_beat, rom)  # type: ignore[arg-type]
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
        emu.run(boot_frames)
        last_snapshot = _snapshot(emu, chapter.beats[start_idx].name)
        # The frame the run starts on is itself worth an eye: a wrong spawn
        # map or a botched intro-skip shows up here before any beat runs.
        emu.waypoint("boot", note="seeded" if start_idx > 0 else "new game")

        for beat in chapter.beats[start_idx:]:
            logger.info("[%s] beat %s starting: %s", chapter.name, beat.name, beat.description)
            try:
                beat.run(emu)
            except Exception as exc:  # noqa: BLE001 - beat failures are data, not bugs here
                import traceback as _tb
                tb_text = _tb.format_exc()
                logger.error("[%s] beat %s FAILED: %s", chapter.name, beat.name, exc)
                beats_out.append(BeatOutcome(beat.name, beat.description, "fail",
                                              error=str(exc), traceback=tb_text))
                emu.waypoint(beat.name, "FAILED", note=beat.description, failed=True)
                return AttemptResult(passed=False, beats=beats_out, pristine_rom=rom,
                                      final_emulator=emu, last_snapshot=last_snapshot,
                                      screenshot_dir=shots, waypoints=list(emu.waypoints),
                                      scratch_rom=scratch)

            logger.info("[%s] beat %s passed", chapter.name, beat.name)
            beats_out.append(BeatOutcome(beat.name, beat.description, "pass"))
            emu.waypoint(beat.name, note=beat.description)

            idx = chapter.index_of(beat.name)
            if idx + 1 < len(chapter.beats):
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
                    last_snapshot = _snapshot(emu, chapter.beats[idx + 1].name)
                    persist_seed_blob(blobs_dir, chapter.name, rom, last_snapshot, emu)

        return AttemptResult(passed=True, beats=beats_out, pristine_rom=rom,
                              final_emulator=emu, last_snapshot=last_snapshot,
                              screenshot_dir=shots, waypoints=list(emu.waypoints),
                              scratch_rom=scratch)
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
                  output_root: Path) -> Path:
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
        meta_path = out.with_suffix(".json")
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return out


def _classify(attempts: list[AttemptResult]) -> str:
    if attempts[0].passed:
        return "pass"
    if len(attempts) > 1 and attempts[1].passed:
        return "flake"
    return "fail"


# -- entry point --------------------------------------------------------------

def run_chapter(chapter: Chapter, rom: Path, engine: Path, *,
                 from_beat: str | None = None,
                 output_root: Path | None = None,
                 emulator_factory: EmulatorFactory | None = None,
                 rerun_on_failure: bool = True) -> ChapterRunResult:
    """Run `chapter` beat by beat and return a structured result.

    `from_beat`: seed from a blob captured after the prior beat of *this
    exact build* (see `load_seed`); `None` (the default, and the only mode
    the gate/CI wrapper should use) always plays from a new game.
    `rerun_on_failure`: F3's auto-rerun-once flake classification.
    """
    output_root = output_root or Path("output") / "playtest"
    blobs_dir = output_root / "blobs"
    emulator_factory = emulator_factory or _default_emulator_factory

    attempts: list[AttemptResult] = []
    attempts.append(_run_attempt(
        chapter, rom, engine, attempt_no=1, from_beat=from_beat,
        output_root=output_root, emulator_factory=emulator_factory,
        blobs_dir=blobs_dir))

    if not attempts[0].passed and rerun_on_failure:
        failing = attempts[0].failed_beat
        logger.warning("[%s] beat %s failed; rerunning once to classify "
                        "flake vs. real failure (F3)", chapter.name,
                        failing.name if failing else "?")
        attempts.append(_run_attempt(
            chapter, rom, engine, attempt_no=2, from_beat=from_beat,
            output_root=output_root, emulator_factory=emulator_factory,
            blobs_dir=blobs_dir))

    verdict = _classify(attempts)
    result = ChapterRunResult(chapter=chapter.name, verdict=verdict, attempts=attempts)

    if verdict == "pass":
        result.stamped_rom = _stamp_green(chapter, rom, attempts[-1], output_root)
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

    # Temp per-attempt screenshot dirs are either copied into the bundle
    # already or unneeded (pass/flake) — clean them up either way.
    for attempt in attempts:
        if attempt.screenshot_dir and attempt.screenshot_dir.exists():
            shutil.rmtree(attempt.screenshot_dir)
        _discard_scratch(attempt.scratch_rom)

    return result
