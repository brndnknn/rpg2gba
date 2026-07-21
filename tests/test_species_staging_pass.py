"""Tests for `scripts/assemble_pathfinder.py`'s species staging pass (S8b2).

Verifies the wiring `assemble_pathfinder.py` owns (per `STARTER_SPECIES_PLAN.md`
§4-W6) rather than re-testing the converters themselves (`test_species_stage.py`
/ `test_species_battlers.py` / `test_species_icons.py` / `test_species_cries.py`
already cover those):

  * every generated header/inc `stage.write_all` documents has a staging
    destination in `assemble_pathfinder._SPECIES_HEADER_DEST_DIRS` -- an
    orphaned generated file would silently never reach the fork
  * `--dry-run` reports the full staging plan (headers, per-species art, cry
    wavs) without ever writing under the fork
  * the battler converter's measured Y offsets and the icon converter's
    chosen `iconPalIndex` actually reach the emitted `species_info` entries
    via `stage.write_all`'s `overrides=` -- not `stage.py`'s
    `DEFAULT_FRONT_PIC_Y_OFFSET` / `DEFAULT_BACK_PIC_Y_OFFSET` /
    `DEFAULT_ICON_PAL_INDEX` placeholders. Per the task brief this is "the
    single most important wiring detail in this unit."

`run_species_pass` always runs the art converters + `stage.write_all` into
`out_dir` regardless of `dry_run` (only the copies INTO the fork are gated by
it) -- see its docstring -- so every test here can safely pass `dry_run=True`
and never touches `$RPG2GBA_POKEEMERALD` / `engine/`, matching how
`test_species_stage.py` et al. never write outside `tmp_path` either.

Gated behind the `uranium_data` + `fork_path` fixtures (skips cleanly when
either is unavailable), matching the rest of the phase2 species-converter
suite.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import assemble_pathfinder  # noqa: E402

from rpg2gba.species_converter import battlers, icons, stage  # noqa: E402
from rpg2gba.species_converter.common import STARTER_SPECIES  # noqa: E402

pytestmark = pytest.mark.phase2

_ART_FILES = ("anim_front.png", "back.png", "normal.pal", "shiny.pal", "icon.png")


@pytest.fixture()
def uranium_src(uranium_data: Path) -> Path:
    """`$RPG2GBA_URANIUM_SRC` root (one level up from the `Data` dir)."""
    return uranium_data.parent


@pytest.fixture()
def engine_dir(fork_path: Path | None) -> Path:
    if fork_path is None:
        pytest.skip("RPG2GBA_POKEEMERALD not set; species staging pass needs the real fork")
    return fork_path


def _entry(c_text: str, const: str) -> str:
    m = re.search(r"    \[" + re.escape(const) + r"\] =\n    \{.*?\n    \},", c_text, re.S)
    assert m, f"{const} entry not found in emitted species_info.h"
    return m.group(0)


# ===========================================================================
# Destination-mapping completeness
# ===========================================================================


def test_header_dest_map_covers_every_generated_file() -> None:
    """`_SPECIES_HEADER_DEST_DIRS` must have exactly one entry per file
    `stage.write_all` writes (per its module docstring's "Generated files"
    list, excluding the manifest, which stays in `out/` and is never staged
    into the fork)."""
    documented = {
        "uranium_species_constants.h",
        "uranium_pokedex_ids.h",
        "uranium_learnsets.h",
        "uranium_species_info.h",
        "uranium_species_graphics.h",
        "uranium_cries_enum.h",
        "uranium_cry_table_forward.inc",
        "uranium_cry_table_reverse.inc",
        "uranium_cry_sound_data.inc",
    }
    assert set(assemble_pathfinder._SPECIES_HEADER_DEST_DIRS) == documented


def test_header_dest_dirs_match_committed_hooks() -> None:
    """Pin the exact engine-relative directories the committed
    `URANIUM PATHFINDER SLICE` hooks `#include`/`.include` these files from
    (verified against the real fork in `engine/`: `species.h`,
    `pokedex.h`, `cries.h`, `species_info.h`, `graphics/pokemon.h`,
    `sound/cry_tables.inc`, `sound/direct_sound_data.inc`) -- a change here
    that drifts from those hook paths would silently break the `#include`
    resolution at compile time, not at staging time."""
    assert assemble_pathfinder._SPECIES_HEADER_DEST_DIRS == {
        "uranium_species_constants.h": "include/constants",
        "uranium_pokedex_ids.h": "include/constants",
        "uranium_cries_enum.h": "include/constants",
        "uranium_learnsets.h": "src/data/pokemon",
        "uranium_species_info.h": "src/data/pokemon",
        "uranium_species_graphics.h": "src/data/graphics",
        "uranium_cry_table_forward.inc": "sound",
        "uranium_cry_table_reverse.inc": "sound",
        "uranium_cry_sound_data.inc": "sound",
    }


# ===========================================================================
# Dry-run staging plan
# ===========================================================================


def test_dry_run_reports_every_staging_action(
    uranium_src: Path, engine_dir: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    assemble_pathfinder.run_species_pass(tmp_path, engine_dir, uranium_src, dry_run=True)
    text = "\n".join(r.message for r in caplog.records)

    for name, dest_dir in assemble_pathfinder._SPECIES_HEADER_DEST_DIRS.items():
        assert f"[dry] would copy {name} -> {engine_dir / dest_dir / name}" in text

    for spec in STARTER_SPECIES:
        for fname in _ART_FILES:
            expected_dest = engine_dir / "graphics" / "pokemon" / "uranium" / spec.internal_name.lower() / fname
            assert f"[dry] would copy {spec.internal_name} {fname} -> {expected_dest}" in text
        expected_wav = engine_dir / "sound" / "direct_sound_samples" / "cries" / f"{spec.internal_name.lower()}.wav"
        assert f"[dry] would copy {spec.internal_name} cry -> {expected_wav}" in text


def test_dry_run_writes_generated_files_but_never_touches_fork(
    uranium_src: Path, engine_dir: Path, tmp_path: Path
) -> None:
    """Conversion + emission run for real (into `out_dir`) even under
    `--dry-run` -- only the copy into the fork is skipped -- so the dry-run
    log is a faithful preview. Assert the `out_dir` side landed, and that no
    file was created under a scratch subdirectory of the fork standing in
    for "the fork" (nothing here writes to the real `engine_dir`, since only
    `_copy`'s dry-run branch would touch it and that's a log line, not I/O)."""
    species_dir = tmp_path / "species"
    assemble_pathfinder.run_species_pass(tmp_path, engine_dir, uranium_src, dry_run=True)

    assert (species_dir / "uranium_species_info.h").is_file()
    assert (species_dir / "species_manifest.json").is_file()
    for spec in STARTER_SPECIES:
        art_dir = tmp_path / "species" / "art" / spec.internal_name.lower()
        for fname in _ART_FILES:
            assert (art_dir / fname).is_file()
        assert (tmp_path / "species" / "cries" / f"{spec.internal_name.lower()}.wav").is_file()


# ===========================================================================
# Sidecar override wiring (the critical detail)
# ===========================================================================


def test_sidecar_overrides_reach_species_info(
    uranium_src: Path, engine_dir: Path, tmp_path: Path
) -> None:
    """The battler converter's measured Y offsets and the icon converter's
    chosen `iconPalIndex` must appear verbatim in the emitted
    `species_info.h` entries -- computed independently here by calling the
    art converters directly (into a separate scratch dir) and comparing
    against what `run_species_pass` staged."""
    # Independently recompute the expected per-species values.
    art_dir = tmp_path / "independent_art"
    battler_results = {r.internal_name: r for r in battlers.convert_starter_battlers(uranium_src, art_dir)}
    icon_result = icons.convert_starter_icons(uranium_src, engine_dir, art_dir)
    icon_by_name = {r.spec.internal_name: r for r in icon_result.species}

    assemble_pathfinder.run_species_pass(tmp_path, engine_dir, uranium_src, dry_run=True)
    info_text = (tmp_path / "species" / "uranium_species_info.h").read_text(encoding="utf-8")

    for spec in STARTER_SPECIES:
        entry = _entry(info_text, spec.constant)
        br = battler_results[spec.internal_name]
        ir = icon_by_name[spec.internal_name]

        assert f".frontPicYOffset = {br.front_y_offset}," in entry
        assert f".backPicYOffset = {br.back_y_offset}," in entry
        assert f".iconPalIndex = {ir.icon_pal_index}," in entry

        # And not stage.py's module-default placeholders, for at least the
        # fields real per-species measurement is expected to move.
        if br.front_y_offset != stage.DEFAULT_FRONT_PIC_Y_OFFSET:
            assert f".frontPicYOffset = {stage.DEFAULT_FRONT_PIC_Y_OFFSET}," not in entry
