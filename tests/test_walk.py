"""Tests for the walk-ROM builder (src/rpg2gba/playtest/walk.py).

A "walk ROM" is a standalone `.gba` positioned at a specific point in a
chapter's playthrough, built from either a beat's seed blob (an
embedded-save snapshot captured mid-run by the chapter runner) or a
chapter-complete review ROM (a fully stamped ROM from a green run). It lets
a human boot straight into the middle of a chapter on real hardware/mGBA
instead of replaying every prior beat.

These tests use synthetic chapters/ROMs on `tmp_path`, following the same
no-mgba, no-real-ROM pattern as `tests/test_runner.py`. Helpers are reused
from there rather than duplicated.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.playtest import runner
from rpg2gba.playtest import walk
from rpg2gba.playtest.chapter import Chapter
from rpg2gba.playtest.stamp import ROM_BASE, build_blob
from tests.test_runner import make_chapter, make_rom, ok

ROM_SIZE = 0x400
BLOB_FILE_OFFSET = 0x100
BLOB_OFFSET_ABS = ROM_BASE + BLOB_FILE_OFFSET

OFFSETS = {
    "sizeof_sb1": 4, "sizeof_sb2": 4, "sizeof_sb3": 4, "sizeof_storage": 4,
    "sizeof_es": 16, "embedded_save_magic": 0xABCDEF01,
    "off_es_sb1": 0, "off_es_sb2": 4, "off_es_sb3": 8, "off_es_storage": 12,
}


def make_blob(fill: int = 0xAB) -> bytes:
    blocks = {name: bytes([fill]) * 4 for name in ("sb1", "sb2", "sb3", "storage")}
    return build_blob(OFFSETS, blocks)


def three_beat_chapter() -> Chapter:
    """Beat names chosen so alphabetical order (B1, B10, B2) disagrees with
    chapter order (B1, B2, B10) -- the case resolve_seed's at_end fallback
    must get right."""
    return make_chapter("walkch", [("B1", ok), ("B2", ok), ("B10", ok)])


def write_beat_seed(blobs_dir: Path, chapter: str, beat: str, rom: Path, *,
                     blob: bytes | None = None, rom_sha256: str | None = None,
                     blob_offset: int = BLOB_OFFSET_ABS,
                     player_pos: tuple[int, int] = (5, 7),
                     map_location: tuple[int, int] = (2, 9),
                     extra_meta: dict | None = None,
                     omit_key: str | None = None) -> bytes:
    blob = blob if blob is not None else make_blob()
    blob_path, meta_path = runner.blob_paths(blobs_dir, chapter, beat)
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(blob)
    meta = {
        "chapter": chapter,
        "seeds_beat": beat,
        "rom_sha256": rom_sha256 if rom_sha256 is not None else runner.hash_file(rom),
        "blob_offset": blob_offset,
        "created": "2026-01-01T00:00:00+00:00",
        "player_pos": list(player_pos),
        "map_location": list(map_location),
    }
    if extra_meta:
        meta.update(extra_meta)
    if omit_key:
        meta.pop(omit_key, None)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return blob


def write_complete_seed(output_root: Path, chapter: str, rom: Path, *,
                         complete_bytes: bytes = b"STAMPED-COMPLETE-ROM",
                         rom_sha256: str | None = None,
                         blob_offset: int = BLOB_OFFSET_ABS,
                         player_pos: tuple[int, int] = (11, 13),
                         map_location: tuple[int, int] = (4, 1),
                         kind: str = "chapter-complete") -> Path:
    review_dir = output_root / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    complete_rom = review_dir / f"{chapter}-complete.gba"
    complete_meta = review_dir / f"{chapter}-complete.json"
    complete_rom.write_bytes(complete_bytes)
    meta = {
        "chapter": chapter,
        "kind": kind,
        "rom_sha256": rom_sha256 if rom_sha256 is not None else runner.hash_file(rom),
        "blob_offset": blob_offset,
        "player_pos": list(player_pos),
        "map_location": list(map_location),
        "created": "2026-01-01T00:00:00+00:00",
    }
    complete_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return complete_rom


# -- available_seeds ----------------------------------------------------------

def test_available_seeds_returns_beats_in_chapter_order_then_complete_last(
        tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"
    blobs_dir = out / "blobs"

    for beat in ("B10", "B1", "B2"):  # written out of order on purpose
        write_beat_seed(blobs_dir, chapter.name, beat, rom)
    write_complete_seed(out, chapter.name, rom)

    seeds = walk.available_seeds(out, chapter, rom)

    assert [s.beat for s in seeds] == ["B1", "B2", "B10", None]
    assert [s.kind for s in seeds] == ["beat", "beat", "beat", "chapter-complete"]


def test_available_seeds_excludes_seed_with_mismatched_rom_hash(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"
    blobs_dir = out / "blobs"

    write_beat_seed(blobs_dir, chapter.name, "B1", rom)
    write_beat_seed(blobs_dir, chapter.name, "B2", rom, rom_sha256="deadbeef" * 8)

    seeds = walk.available_seeds(out, chapter, rom)

    assert [s.beat for s in seeds] == ["B1"]


def test_available_seeds_skips_malformed_sidecar_json(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"
    blobs_dir = out / "blobs"

    write_beat_seed(blobs_dir, chapter.name, "B1", rom)
    _, meta_path = runner.blob_paths(blobs_dir, chapter.name, "B2")
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text("{not json", encoding="utf-8")
    (meta_path.parent / "B2.blob").write_bytes(make_blob())

    seeds = walk.available_seeds(out, chapter, rom)

    assert [s.beat for s in seeds] == ["B1"]


def test_available_seeds_skips_sidecar_missing_required_keys(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"
    blobs_dir = out / "blobs"

    write_beat_seed(blobs_dir, chapter.name, "B1", rom)
    write_beat_seed(blobs_dir, chapter.name, "B2", rom, omit_key="player_pos")

    seeds = walk.available_seeds(out, chapter, rom)

    assert [s.beat for s in seeds] == ["B1"]


def test_available_seeds_skips_sidecar_naming_beat_chapter_no_longer_has(
        tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"
    blobs_dir = out / "blobs"

    write_beat_seed(blobs_dir, chapter.name, "B1", rom)
    write_beat_seed(blobs_dir, chapter.name, "B99", rom)  # not a beat in this chapter

    seeds = walk.available_seeds(out, chapter, rom)

    assert [s.beat for s in seeds] == ["B1"]


def test_available_seeds_empty_when_nothing_exists(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"

    assert walk.available_seeds(out, chapter, rom) == []


# -- resolve_seed: at_beat -----------------------------------------------------

def test_resolve_seed_at_beat_returns_that_exact_beats_seed(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"
    blobs_dir = out / "blobs"

    write_beat_seed(blobs_dir, chapter.name, "B1", rom)
    write_beat_seed(blobs_dir, chapter.name, "B2", rom)

    seed = walk.resolve_seed(out, chapter, rom, at_beat="B2")

    assert seed.kind == "beat"
    assert seed.beat == "B2"
    assert seed.source == blobs_dir / chapter.name / "B2.blob"


def test_resolve_seed_at_beat_unknown_beat_raises(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"

    with pytest.raises(runner.RunnerError, match="no beat"):
        walk.resolve_seed(out, chapter, rom, at_beat="B99")


def test_resolve_seed_at_beat_missing_blob_raises_with_rerun_guidance(
        tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"

    with pytest.raises(runner.RunnerError, match="run the chapter green from the start"):
        walk.resolve_seed(out, chapter, rom, at_beat="B1")


def test_resolve_seed_at_beat_stale_blob_raises_with_both_hashes(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"
    blobs_dir = out / "blobs"

    stale_hash = "deadbeef" * 8
    write_beat_seed(blobs_dir, chapter.name, "B1", rom, rom_sha256=stale_hash)
    current_hash = runner.hash_file(rom)

    with pytest.raises(runner.RunnerError) as excinfo:
        walk.resolve_seed(out, chapter, rom, at_beat="B1")

    msg = str(excinfo.value)
    assert stale_hash in msg
    assert current_hash in msg


# -- resolve_seed: at_end -------------------------------------------------------

def test_resolve_seed_at_end_prefers_chapter_complete_seed(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"
    blobs_dir = out / "blobs"

    write_beat_seed(blobs_dir, chapter.name, "B10", rom)
    write_complete_seed(out, chapter.name, rom)

    seed = walk.resolve_seed(out, chapter, rom, at_end=True)

    assert seed.kind == "chapter-complete"


def test_resolve_seed_at_end_falls_back_to_furthest_beat_in_chapter_order_not_alpha(
        tmp_path: Path) -> None:
    """Alphabetically B2 > B10 > B1, but chapter order is B1, B2, B10. No
    complete seed exists, so at_end must fall back to B10 (chapter-last),
    never B2 (alphabetically last) nor B1 (filesystem/glob-first)."""
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"
    blobs_dir = out / "blobs"

    for beat in ("B1", "B2", "B10"):
        write_beat_seed(blobs_dir, chapter.name, beat, rom)

    seed = walk.resolve_seed(out, chapter, rom, at_end=True)

    assert seed.kind == "beat"
    assert seed.beat == "B10"


def test_resolve_seed_at_end_raises_when_nothing_available(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"

    with pytest.raises(runner.RunnerError, match="no seeds at all"):
        walk.resolve_seed(out, chapter, rom, at_end=True)


# -- resolve_seed: usage errors -------------------------------------------------

def test_resolve_seed_raises_when_both_at_beat_and_at_end_given(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"

    with pytest.raises(runner.RunnerError, match="not both"):
        walk.resolve_seed(out, chapter, rom, at_beat="B1", at_end=True)


def test_resolve_seed_raises_when_neither_at_beat_nor_at_end_given(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"

    with pytest.raises(runner.RunnerError, match="pass exactly one"):
        walk.resolve_seed(out, chapter, rom)


# -- build_walk_rom: beat seed ---------------------------------------------------

def test_build_walk_rom_for_beat_seed_patches_only_the_blob_region(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    pristine_bytes = rom.read_bytes()
    out = tmp_path / "out"
    blobs_dir = out / "blobs"

    blob = write_beat_seed(blobs_dir, chapter.name, "B1", rom)
    walk_out = tmp_path / "walk" / "b1.gba"

    seed = walk.build_walk_rom(out, chapter, rom, tmp_path / "engine",
                                at_beat="B1", out=walk_out, verify=False)

    assert seed.kind == "beat"
    assert seed.beat == "B1"
    produced = walk_out.read_bytes()
    assert produced[BLOB_FILE_OFFSET:BLOB_FILE_OFFSET + len(blob)] == blob
    # Everything outside the patched region is unchanged from pristine.
    assert produced[:BLOB_FILE_OFFSET] == pristine_bytes[:BLOB_FILE_OFFSET]
    assert produced[BLOB_FILE_OFFSET + len(blob):] == pristine_bytes[BLOB_FILE_OFFSET + len(blob):]
    assert len(produced) == len(pristine_bytes)


def test_build_walk_rom_creates_missing_parent_directories(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"
    blobs_dir = out / "blobs"
    write_beat_seed(blobs_dir, chapter.name, "B1", rom)

    walk_out = tmp_path / "nested" / "deep" / "walk.gba"
    assert not walk_out.parent.exists()

    walk.build_walk_rom(out, chapter, rom, tmp_path / "engine",
                         at_beat="B1", out=walk_out, verify=False)

    assert walk_out.exists()


def test_build_walk_rom_returns_the_resolved_seed(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"
    blobs_dir = out / "blobs"
    write_beat_seed(blobs_dir, chapter.name, "B1", rom,
                     player_pos=(9, 4), map_location=(6, 6))

    seed = walk.build_walk_rom(out, chapter, rom, tmp_path / "engine",
                                at_beat="B1", out=tmp_path / "w.gba", verify=False)

    assert seed.player_pos == (9, 4)
    assert seed.map_location == (6, 6)


def test_build_walk_rom_leaves_pristine_rom_untouched(tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    before_bytes = rom.read_bytes()
    before_hash = runner.hash_file(rom)
    out = tmp_path / "out"
    blobs_dir = out / "blobs"
    write_beat_seed(blobs_dir, chapter.name, "B1", rom)

    walk.build_walk_rom(out, chapter, rom, tmp_path / "engine",
                         at_beat="B1", out=tmp_path / "w.gba", verify=False)

    assert rom.read_bytes() == before_bytes
    assert runner.hash_file(rom) == before_hash


# -- build_walk_rom: chapter-complete seed ---------------------------------------

def test_build_walk_rom_for_chapter_complete_copies_stamped_rom_verbatim(
        tmp_path: Path) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"

    complete_bytes = b"STAMPED-COMPLETE-ROM-NOT-A-PATCH" + bytes(50)
    complete_rom = write_complete_seed(out, chapter.name, rom, complete_bytes=complete_bytes)

    walk_out = tmp_path / "w.gba"
    seed = walk.build_walk_rom(out, chapter, rom, tmp_path / "engine",
                                at_end=True, out=walk_out, verify=False)

    assert seed.kind == "chapter-complete"
    assert walk_out.read_bytes() == complete_bytes
    assert walk_out.read_bytes() == complete_rom.read_bytes()
    # Not a patch of the pristine rom: sizes/content differ entirely.
    assert walk_out.read_bytes() != rom.read_bytes()


# -- verify=False does not touch the emulator ------------------------------------

def test_build_walk_rom_verify_false_never_invokes_verification(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"
    blobs_dir = out / "blobs"
    write_beat_seed(blobs_dir, chapter.name, "B1", rom)

    from rpg2gba.playtest import stamp as stamp_mod

    def boom(*args, **kwargs):
        raise AssertionError("verify_stamped_rom must not be called when verify=False")

    monkeypatch.setattr(stamp_mod, "verify_stamped_rom", boom)

    # Should not raise -- proves the emulator-touching verify path is never
    # reached (engine dir below doesn't even exist, which a real
    # Emulator/verify call would choke on).
    walk.build_walk_rom(out, chapter, rom, tmp_path / "nonexistent-engine",
                         at_beat="B1", out=tmp_path / "w.gba", verify=False)


# -- round trip -------------------------------------------------------------------

def test_round_trip_build_blob_persist_resolve_build_walk_rom_and_read_back(
        tmp_path: Path) -> None:
    """stamp.build_blob -> persist (hand-built, faithful to persist_seed_blob's
    format) -> resolve_seed -> build_walk_rom -> read the blob back out of
    the produced ROM and confirm it matches what went in."""
    chapter = three_beat_chapter()
    rom = make_rom(tmp_path / "rom.gba", ROM_SIZE)
    out = tmp_path / "out"
    blobs_dir = out / "blobs"

    synthetic_blocks = {
        "sb1": bytes([0x11, 0x22, 0x33, 0x44]),
        "sb2": bytes([0x55, 0x66, 0x77, 0x88]),
        "sb3": bytes([0x99, 0xAA, 0xBB, 0xCC]),
        "storage": bytes([0xDD, 0xEE, 0xFF, 0x00]),
    }
    blob = build_blob(OFFSETS, synthetic_blocks)

    blob_path, meta_path = runner.blob_paths(blobs_dir, chapter.name, "B2")
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(blob)
    meta_path.write_text(json.dumps({
        "chapter": chapter.name,
        "seeds_beat": "B2",
        "rom_sha256": runner.hash_file(rom),
        "blob_offset": BLOB_OFFSET_ABS,
        "created": "2026-01-01T00:00:00+00:00",
        "player_pos": [3, 8],
        "map_location": [1, 5],
    }, indent=2), encoding="utf-8")

    seed = walk.resolve_seed(out, chapter, rom, at_beat="B2")
    assert seed.blob_offset == BLOB_FILE_OFFSET

    walk_out = tmp_path / "roundtrip.gba"
    resolved = walk.build_walk_rom(out, chapter, rom, tmp_path / "engine",
                                    at_beat="B2", out=walk_out, verify=False)
    assert resolved == seed

    produced = walk_out.read_bytes()
    read_back = produced[BLOB_FILE_OFFSET:BLOB_FILE_OFFSET + len(blob)]
    assert read_back == blob
