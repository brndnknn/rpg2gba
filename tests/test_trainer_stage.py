"""Tests for `rpg2gba.trainer_converter.stage` -- the trainer-pic C-emitter."""
from __future__ import annotations

import json
import re
from pathlib import Path

from rpg2gba.trainer_converter.common import TrainerPicSpec
from rpg2gba.trainer_converter.pics import BackPicResult, FrontPicResult
from rpg2gba.trainer_converter.stage import (
    BACK_SPRITE_ANIM_TABLE,
    BACK_SPRITE_Y_OFFSET,
    StagedBackPic,
    StagedFrontPic,
    write_all,
)

FIXTURES = Path(__file__).parent / "fixtures"

RIVAL_SPEC = TrainerPicSpec(86, "RIVAL")
PLAYER_SPEC = TrainerPicSpec(0, "PLAYER_MALE")


def _front_result(spec: TrainerPicSpec) -> FrontPicResult:
    return FrontPicResult(
        trainer_id=spec.trainer_id,
        internal_name=spec.internal_name,
        front_path=Path("front.png"),
        pal_path=Path("front.pal"),
        source_bbox=(100, 50),
        scaled_size=(64, 32),
        scale_factor=0.64,
        opaque_color_count=5,
    )


def _back_result(spec: TrainerPicSpec) -> BackPicResult:
    return BackPicResult(
        trainer_id=spec.trainer_id,
        internal_name=spec.internal_name,
        back_path=Path("back.png"),
        pal_path=Path("back.pal"),
        frame_count=4,
        per_frame_bbox=((0, 10, 0, 20),) * 4,
        union_bbox=(0, 10, 0, 20),
        scaled_size=(20, 60),
        scale_factor=1.0,
        opaque_color_count=6,
    )


def _staged(
    tmp_path: Path,
) -> tuple[list[StagedFrontPic], list[StagedBackPic]]:
    fronts = [StagedFrontPic(spec=RIVAL_SPEC, result=_front_result(RIVAL_SPEC))]
    backs = [StagedBackPic(spec=PLAYER_SPEC, result=_back_result(PLAYER_SPEC))]
    return fronts, backs


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --- 1. Emitted constants match the manifest ---------------------------------


def test_emitted_constants_match_manifest(tmp_path: Path) -> None:
    fronts, backs = _staged(tmp_path)
    out_dir = tmp_path / "out"
    manifest = write_all(out_dir=out_dir, fronts=fronts, backs=backs)

    front_ids = _read(out_dir / "uranium_trainer_front_pic_ids.h")
    back_ids = _read(out_dir / "uranium_trainer_back_pic_ids.h")
    sprites = _read(out_dir / "uranium_trainer_sprites.h")
    backsprites = _read(out_dir / "uranium_trainer_backsprites.h")

    front_record = next(r for r in manifest["trainers"] if r["kind"] == "front")
    back_record = next(r for r in manifest["trainers"] if r["kind"] == "back")

    assert front_record["pic_constant"] == RIVAL_SPEC.pic_constant
    assert front_record["pic_constant"] in front_ids
    assert front_record["pic_constant"] in sprites

    assert back_record["back_pic_constant"] == PLAYER_SPEC.back_pic_constant
    assert back_record["back_pic_constant"] in back_ids
    assert back_record["back_pic_constant"] in backsprites

    # manifest c_symbols exactly match what the sprite rows reference
    assert front_record["c_symbols"]["front_pic"] in sprites
    assert front_record["c_symbols"]["palette"] in sprites
    assert back_record["c_symbols"]["back_pic"] in backsprites
    assert back_record["c_symbols"]["palette"] in backsprites


def test_manifest_written_to_disk_matches_return_value(tmp_path: Path) -> None:
    fronts, backs = _staged(tmp_path)
    out_dir = tmp_path / "out"
    manifest = write_all(out_dir=out_dir, fronts=fronts, backs=backs)
    on_disk = json.loads(_read(out_dir / "trainer_manifest.json"))
    assert on_disk == manifest


# --- 2. Empty selection -> valid no-op files ----------------------------------


def test_empty_selection_produces_valid_noop_files(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    manifest = write_all(out_dir=out_dir, fronts=(), backs=())

    assert manifest["trainers"] == []

    for name in (
        "uranium_trainer_front_pic_ids.h",
        "uranium_trainer_back_pic_ids.h",
        "uranium_trainer_graphics.h",
        "uranium_trainer_sprites.h",
        "uranium_trainer_backsprites.h",
    ):
        content = _read(out_dir / name)
        assert "no-op" in content
        # no stray staged-pic constants or gTrainer* symbols in an empty overlay
        assert "TRAINER_PIC_FRONT_URANIUM_" not in content
        assert "TRAINER_PIC_BACK_URANIUM_" not in content
        assert "gTrainer" not in content

    # the chaining defines are still emitted with a zero count -- the back
    # header must have something valid to chain off even in a no-op run.
    front_ids = _read(out_dir / "uranium_trainer_front_pic_ids.h")
    back_ids = _read(out_dir / "uranium_trainer_back_pic_ids.h")
    assert "#define URANIUM_TRAINER_PIC_AFTER_FRONT" in front_ids
    assert "(TRAINER_PIC_COUNT + 0)" in front_ids
    assert "#define URANIUM_TRAINER_PIC_TOTAL" in back_ids
    assert "(URANIUM_TRAINER_PIC_AFTER_FRONT + 0)" in back_ids
    assert "URANIUM_HAVE_PLAYER_BACK_PIC" not in back_ids
    assert "URANIUM_HAVE_PLAYER_FEMALE_BACK_PIC" not in back_ids


# --- 3. Idempotence ------------------------------------------------------------


def test_idempotent_reruns_are_byte_identical(tmp_path: Path) -> None:
    fronts, backs = _staged(tmp_path)
    out_dir = tmp_path / "out"

    write_all(out_dir=out_dir, fronts=fronts, backs=backs)
    snapshot = {p.name: p.read_bytes() for p in sorted(out_dir.iterdir())}

    write_all(out_dir=out_dir, fronts=fronts, backs=backs)
    rerun = {p.name: p.read_bytes() for p in sorted(out_dir.iterdir())}

    assert snapshot == rerun


def test_idempotent_reruns_empty_selection(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    write_all(out_dir=out_dir, fronts=(), backs=())
    snapshot = {p.name: p.read_bytes() for p in sorted(out_dir.iterdir())}
    write_all(out_dir=out_dir, fronts=(), backs=())
    rerun = {p.name: p.read_bytes() for p in sorted(out_dir.iterdir())}
    assert snapshot == rerun


# --- 4. Cross-file consistency: sprite rows reference declared symbols -------


def test_sprite_rows_reference_declared_incgfx_symbols(tmp_path: Path) -> None:
    fronts, backs = _staged(tmp_path)
    out_dir = tmp_path / "out"
    write_all(out_dir=out_dir, fronts=fronts, backs=backs)

    graphics = _read(out_dir / "uranium_trainer_graphics.h")
    sprites = _read(out_dir / "uranium_trainer_sprites.h")
    backsprites = _read(out_dir / "uranium_trainer_backsprites.h")

    declared = set(re.findall(r"\bg\w+(?=\[\])", graphics))

    front = fronts[0]
    assert front.front_symbol in declared
    assert front.palette_symbol in declared
    assert front.front_symbol in sprites
    assert front.palette_symbol in sprites

    back = backs[0]
    assert back.back_symbol in declared
    assert back.palette_symbol in declared
    assert back.back_symbol in backsprites
    assert back.palette_symbol in backsprites


# --- 5. Back sprite yOffset + anim table ---------------------------------------


def test_back_sprite_uses_yoffset_4_and_uranium_anim_table(tmp_path: Path) -> None:
    fronts, backs = _staged(tmp_path)
    out_dir = tmp_path / "out"
    write_all(out_dir=out_dir, fronts=fronts, backs=backs)

    backsprites = _read(out_dir / "uranium_trainer_backsprites.h")
    assert BACK_SPRITE_Y_OFFSET == 4
    assert BACK_SPRITE_ANIM_TABLE == "sBackAnims_Uranium"

    row = next(line for line in backsprites.splitlines() if "TRAINER_BACK_SPRITE" in line)
    assert re.search(r",\s*4\s*,", row), row
    assert "sBackAnims_Uranium" in row
    # never regress back onto the stock table -- its idle slot is frame index
    # 3, but our sheets are idle-first (frame 0); see stage.py's
    # BACK_SPRITE_ANIM_TABLE comment for the concrete symptom this caused.
    assert "sBackAnims_Hoenn" not in row


# --- 10. Dedicated Uranium back-anim tables --------------------------------


def test_graphics_header_defines_uranium_anim_tables_when_back_pic_staged(
    tmp_path: Path,
) -> None:
    fronts, backs = _staged(tmp_path)
    out_dir = tmp_path / "out"
    write_all(out_dir=out_dir, fronts=fronts, backs=backs)

    graphics = _read(out_dir / "uranium_trainer_graphics.h")
    assert "sAnim_UraniumBackIdle" in graphics
    assert "sAnimCmd_UraniumBackThrow" in graphics
    assert "sBackAnims_Uranium" in graphics


def test_graphics_header_omits_uranium_anim_tables_when_no_back_pic_staged(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "out"
    fronts = [StagedFrontPic(spec=RIVAL_SPEC, result=_front_result(RIVAL_SPEC))]
    write_all(out_dir=out_dir, fronts=fronts, backs=())

    graphics = _read(out_dir / "uranium_trainer_graphics.h")
    assert "sAnim_UraniumBackIdle" not in graphics
    assert "sAnimCmd_UraniumBackThrow" not in graphics
    assert "sBackAnims_Uranium" not in graphics


def test_uranium_back_throw_table_frame_sequence_is_0123(tmp_path: Path) -> None:
    fronts, backs = _staged(tmp_path)
    out_dir = tmp_path / "out"
    write_all(out_dir=out_dir, fronts=fronts, backs=backs)

    graphics = _read(out_dir / "uranium_trainer_graphics.h")
    throw_block = graphics.split("sAnimCmd_UraniumBackThrow[] =")[1].split("};")[0]
    frames = re.findall(r"ANIMCMD_FRAME\((\d+),", throw_block)
    assert frames == ["0", "1", "2", "3"], frames


# --- 6. Art paths in INCGFX match the manifest's art filenames ----------------


def test_incgfx_art_paths_match_manifest_art_files(tmp_path: Path) -> None:
    fronts, backs = _staged(tmp_path)
    out_dir = tmp_path / "out"
    manifest = write_all(out_dir=out_dir, fronts=fronts, backs=backs)

    graphics = _read(out_dir / "uranium_trainer_graphics.h")
    for record in manifest["trainers"]:
        for art_path in record["art_files"].values():
            assert art_path in graphics, f"{art_path} not referenced in graphics header"
        assert record["asset_dir"] in graphics


# --- 7. #define chain, not enum members -----------------------------------


def test_pic_ids_are_defines_not_enum_members(tmp_path: Path) -> None:
    fronts, backs = _staged(tmp_path)
    out_dir = tmp_path / "out"
    write_all(out_dir=out_dir, fronts=fronts, backs=backs)

    front_ids = _read(out_dir / "uranium_trainer_front_pic_ids.h")
    back_ids = _read(out_dir / "uranium_trainer_back_pic_ids.h")

    # no bare enumerator lines (e.g. "    TRAINER_PIC_FRONT_URANIUM_RIVAL,")
    # -- these must never be spliced into enum TrainerPicID's body again.
    bare_enumerator = re.compile(r"^\s*TRAINER_PIC_(FRONT|BACK)_URANIUM_\w+,\s*$", re.MULTILINE)
    assert not bare_enumerator.search(front_ids)
    assert not bare_enumerator.search(back_ids)

    # every staged constant is a #define, chained off TRAINER_PIC_COUNT /
    # URANIUM_TRAINER_PIC_AFTER_FRONT, not a bare enum member.
    assert "#define TRAINER_PIC_FRONT_URANIUM_RIVAL" in front_ids
    assert re.search(r"#define TRAINER_PIC_FRONT_URANIUM_RIVAL\s+\(TRAINER_PIC_COUNT \+ 0\)", front_ids)
    assert "#define URANIUM_TRAINER_PIC_AFTER_FRONT" in front_ids
    assert "(TRAINER_PIC_COUNT + 1)" in front_ids

    assert "#ifndef URANIUM_TRAINER_PIC_AFTER_FRONT" in back_ids
    assert re.search(
        r"#define TRAINER_PIC_BACK_URANIUM_PLAYER_MALE\s+\(URANIUM_TRAINER_PIC_AFTER_FRONT \+ 0\)",
        back_ids,
    )
    assert "#define URANIUM_TRAINER_PIC_TOTAL" in back_ids
    assert "(URANIUM_TRAINER_PIC_AFTER_FRONT + 1)" in back_ids


# --- 8. Player back-pic feature-test guard ---------------------------------


def test_player_male_back_pic_emits_have_guard(tmp_path: Path) -> None:
    fronts, backs = _staged(tmp_path)  # backs includes PLAYER_MALE
    out_dir = tmp_path / "out"
    write_all(out_dir=out_dir, fronts=fronts, backs=backs)

    back_ids = _read(out_dir / "uranium_trainer_back_pic_ids.h")
    assert "#define URANIUM_HAVE_PLAYER_BACK_PIC" in back_ids
    assert "URANIUM_HAVE_PLAYER_FEMALE_BACK_PIC" not in back_ids


def test_no_player_back_pic_omits_have_guard(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    fronts = [StagedFrontPic(spec=RIVAL_SPEC, result=_front_result(RIVAL_SPEC))]
    write_all(out_dir=out_dir, fronts=fronts, backs=())

    back_ids = _read(out_dir / "uranium_trainer_back_pic_ids.h")
    assert "URANIUM_HAVE_PLAYER_BACK_PIC" not in back_ids
    assert "URANIUM_HAVE_PLAYER_FEMALE_BACK_PIC" not in back_ids


# --- 9. Golden output ----------------------------------------------------------


def test_golden_output_for_slice_selection(tmp_path: Path) -> None:
    fronts, backs = _staged(tmp_path)
    out_dir = tmp_path / "out"
    write_all(out_dir=out_dir, fronts=fronts, backs=backs)

    names = [
        "uranium_trainer_front_pic_ids.h",
        "uranium_trainer_back_pic_ids.h",
        "uranium_trainer_graphics.h",
        "uranium_trainer_sprites.h",
        "uranium_trainer_backsprites.h",
    ]
    combined = "\n".join(f"// === {n} ===\n{_read(out_dir / n)}" for n in names)

    golden_path = FIXTURES / "trainer_stage_golden.h"
    if not golden_path.exists():
        golden_path.write_text(combined, encoding="utf-8")
    expected = golden_path.read_text(encoding="utf-8")
    assert combined == expected
