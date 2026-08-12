"""Walk ROMs: turn a seed blob (or a chapter-complete review ROM) into a
standalone, verified, bootable `.gba` positioned at a specific point in a
chapter's playthrough.

The chapter runner (`runner.py`) already produces the raw material for this
at every beat boundary — an embedded-save "seed blob" under
`<output_root>/blobs/<chapter>/<beat>.blob`, plus (for a fully green run) a
stamped review ROM at `<output_root>/review/<chapter>-complete.gba`. Until
now, turning either of those into a ROM a human can boot on a real device
was buried inside failure-bundle and green-stamp plumbing. This module
exposes it directly: "give me a bootable, verified ROM positioned at beat K
of chapter C" (`--at-beat`) or "give me one at the furthest state reached in
chapter C" (`--at-end`).

Seed blobs are keyed to the exact ROM build that produced them (their
metadata records the pristine ROM's sha256) — a blob from a stale build is
never silently reused; any ROM rebuild invalidates every blob and requires
a fresh green run to regenerate them.

CLI:
    python -m rpg2gba.playtest walk --chapter moki --at-beat B10
"""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import runner
from .chapter import Chapter
from .stamp import ROM_BASE

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Seed:
    """A single bootable/patchable state: either a beat's seed blob, or the
    chapter-complete review ROM."""

    chapter: str
    kind: str                       # "beat" | "chapter-complete"
    beat: str | None                # beat the state sits before; None when kind == "chapter-complete"
    source: Path                    # the .blob file, or the stamped complete .gba
    blob_offset: int                # FILE offset (ROM_BASE already subtracted)
    player_pos: tuple[int, int]
    map_location: tuple[int, int]
    created: str


def _review_paths(output_root: Path, chapter: str) -> tuple[Path, Path]:
    review_dir = output_root / "review"
    return review_dir / f"{chapter}-complete.gba", review_dir / f"{chapter}-complete.json"


def _load_beat_seed(blobs_dir: Path, chapter: Chapter, beat_name: str,
                     current_hash: str) -> Seed | None:
    blob_path, meta_path = runner.blob_paths(blobs_dir, chapter.name, beat_name)
    if not blob_path.exists() or not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.info("skipping malformed seed metadata %s: %s", meta_path, exc)
        return None

    try:
        rom_sha256 = meta["rom_sha256"]
        blob_offset = meta["blob_offset"]
        player_pos = meta["player_pos"]
        map_location = meta["map_location"]
        created = meta["created"]
    except KeyError as exc:
        logger.info("skipping seed metadata %s missing key %s", meta_path, exc)
        return None

    if rom_sha256 != current_hash:
        logger.debug("skipping stale seed %s (rom_sha256=%s, current=%s)",
                      meta_path, rom_sha256, current_hash)
        return None

    return Seed(chapter=chapter.name, kind="beat", beat=beat_name, source=blob_path,
                blob_offset=blob_offset - ROM_BASE,
                player_pos=tuple(player_pos), map_location=tuple(map_location),
                created=created)


def _load_complete_seed(output_root: Path, chapter: Chapter,
                         current_hash: str) -> Seed | None:
    complete_rom, complete_meta = _review_paths(output_root, chapter.name)
    if not complete_rom.exists() or not complete_meta.exists():
        return None
    try:
        meta = json.loads(complete_meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.info("skipping malformed review metadata %s: %s", complete_meta, exc)
        return None

    try:
        if meta["kind"] != "chapter-complete":
            logger.info("skipping review metadata %s: kind %r != 'chapter-complete'",
                         complete_meta, meta.get("kind"))
            return None
        rom_sha256 = meta["rom_sha256"]
        blob_offset = meta["blob_offset"]
        player_pos = meta["player_pos"]
        map_location = meta["map_location"]
        created = meta["created"]
    except KeyError as exc:
        logger.info("skipping review metadata %s missing key %s", complete_meta, exc)
        return None

    if rom_sha256 != current_hash:
        logger.debug("skipping stale review seed %s (rom_sha256=%s, current=%s)",
                      complete_meta, rom_sha256, current_hash)
        return None

    return Seed(chapter=chapter.name, kind="chapter-complete", beat=None,
                source=complete_rom, blob_offset=blob_offset - ROM_BASE,
                player_pos=tuple(player_pos), map_location=tuple(map_location),
                created=created)


def available_seeds(output_root: Path, chapter: Chapter, rom: Path) -> list[Seed]:
    """Every non-stale seed for `chapter` against `rom`'s current build,
    ordered by progression (beat order, then chapter-complete last)."""
    current_hash = runner.hash_file(rom)
    blobs_dir = output_root / "blobs"
    chapter_dir = blobs_dir / chapter.name

    found: list[Seed] = []
    if chapter_dir.is_dir():
        for meta_path in sorted(chapter_dir.glob("*.json")):
            beat_name = meta_path.stem
            try:
                chapter.index_of(beat_name)
            except KeyError:
                logger.info("skipping seed %s: chapter %r has no beat %r",
                            meta_path, chapter.name, beat_name)
                continue
            seed = _load_beat_seed(blobs_dir, chapter, beat_name, current_hash)
            if seed is not None:
                found.append(seed)

    found.sort(key=lambda s: chapter.index_of(s.beat))  # type: ignore[arg-type]

    complete = _load_complete_seed(output_root, chapter, current_hash)
    if complete is not None:
        found.append(complete)

    return found


def resolve_seed(output_root: Path, chapter: Chapter, rom: Path, *,
                  at_beat: str | None = None, at_end: bool = False) -> Seed:
    """Resolve exactly one of `at_beat` / `at_end` to a usable `Seed`.

    `at_end` prefers the chapter-complete seed, falling back to the
    furthest-progressed beat seed reached on this build. Raises
    `runner.RunnerError` (never falls back silently) when nothing usable
    exists for what was asked."""
    if (at_beat is not None) and at_end:
        raise runner.RunnerError(
            "resolve_seed: pass exactly one of at_beat / at_end, not both")
    if (at_beat is None) and not at_end:
        raise runner.RunnerError(
            "resolve_seed: pass exactly one of at_beat / at_end")

    current_hash = runner.hash_file(rom)

    if at_beat is not None:
        try:
            chapter.index_of(at_beat)
        except KeyError as exc:
            raise runner.RunnerError(
                f"chapter {chapter.name!r} has no beat {at_beat!r}; "
                f"beats are {[b.name for b in chapter.beats]}") from exc
        seed = _load_beat_seed(output_root / "blobs", chapter, at_beat, current_hash)
        if seed is not None:
            return seed

        blob_path, meta_path = runner.blob_paths(output_root / "blobs", chapter.name, at_beat)
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                stale_hash = meta.get("rom_sha256", "?")
            except (OSError, json.JSONDecodeError):
                stale_hash = "?"
            raise runner.RunnerError(
                f"seed blob for chapter {chapter.name!r} beat {at_beat!r} was "
                f"captured from a different ROM build (blob rom_sha256="
                f"{stale_hash}, current={current_hash}) — seeds are "
                "invalidated by any ROM rebuild; run the chapter green from "
                "the start on this build first to refresh it")
        raise runner.RunnerError(
            f"no seed for chapter {chapter.name!r} beat {at_beat!r} against "
            f"the current build (sha256={current_hash}) at {meta_path} — "
            "seeds are invalidated by any ROM rebuild; run the chapter "
            "green from the start on this build first")

    # at_end
    complete = _load_complete_seed(output_root, chapter, current_hash)
    if complete is not None:
        return complete

    seeds = available_seeds(output_root, chapter, rom)
    beat_seeds = [s for s in seeds if s.kind == "beat"]
    if beat_seeds:
        return beat_seeds[-1]

    complete_rom, complete_meta = _review_paths(output_root, chapter.name)
    if complete_meta.exists():
        try:
            meta = json.loads(complete_meta.read_text(encoding="utf-8"))
            stale_hash = meta.get("rom_sha256", "?")
        except (OSError, json.JSONDecodeError):
            stale_hash = "?"
        raise runner.RunnerError(
            f"chapter-complete review ROM for chapter {chapter.name!r} was "
            f"stamped from a different ROM build (rom_sha256={stale_hash}, "
            f"current={current_hash}), and no usable beat seeds exist "
            "against this build — seeds are invalidated by any ROM rebuild; "
            "run the chapter green from the start on this build first")
    raise runner.RunnerError(
        f"no seeds at all for chapter {chapter.name!r} against the current "
        f"build (sha256={current_hash}) under {output_root / 'blobs' / chapter.name} "
        f"or {complete_rom} — seeds are invalidated by any ROM rebuild; run "
        "the chapter green from the start on this build first")


def build_walk_rom(output_root: Path, chapter: Chapter, rom: Path, engine: Path, *,
                    at_beat: str | None = None, at_end: bool = False, out: Path,
                    verify: bool = True) -> Seed:
    """Resolve a seed and write a bootable ROM for it at `out`.

    A "beat" seed is patched into a copy of `rom`; a "chapter-complete" seed
    is already a stamped ROM and is copied as-is. When `verify`, the result
    is re-booted with a deliberately foreign `.sav` paired to prove the
    embedded blob wins over save residue (the invariant `stamp.py` pins)."""
    seed = resolve_seed(output_root, chapter, rom, at_beat=at_beat, at_end=at_end)
    out.parent.mkdir(parents=True, exist_ok=True)

    if seed.kind == "beat":
        assert seed.beat is not None
        blob, file_offset = runner.load_seed(
            output_root / "blobs", chapter.name, seed.beat, rom)
        runner.write_blob_to_rom(rom, out, blob, file_offset)
    elif seed.kind == "chapter-complete":
        shutil.copy(seed.source, out)
    else:
        raise runner.RunnerError(f"unknown seed kind {seed.kind!r}")

    logger.info("[%s] walk ROM (%s): %s", chapter.name, seed.kind, out)

    if verify:
        from .stamp import verify_stamped_rom

        verify_stamped_rom(out, engine, seed.map_location, seed.player_pos,
                            boot_frames=runner.SEEDED_BOOT_FRAMES)

    return seed
