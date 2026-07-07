"""RMXP character sheet -> GBA object-event frames."""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rpg2gba.tileset_converter.graphics.sprites import (
    NUM_PLAYER_OUTPUT_FRAMES,
    ConvertedPlayer,
    ConvertedSprite,
    _anchor,
    _asymmetry,
    _binarize_alpha,
    _downscale_2x_majority,
    convert_character_sheet,
    convert_player_sheets,
)

TRANSPARENT = (0, 0, 0, 0)


def _upscale2x(native: np.ndarray) -> np.ndarray:
    return np.repeat(np.repeat(native, 2, axis=0), 2, axis=1)


def _make_sheet(
    tmp_path: Path,
    cells: dict[tuple[int, int], np.ndarray],
    cell_px: int,
    name: str = "sheet",
) -> Path:
    """Build a 4x4-grid RMXP sheet PNG. `cells[(row, col)]` is a native
    (cell_px, cell_px, 4) uint8 block; unset cells default to transparent.
    The sheet is an exact 2x nearest-neighbour upscale of the native grid."""
    native = np.zeros((cell_px * 4, cell_px * 4, 4), dtype=np.uint8)
    for (row, col), block in cells.items():
        assert block.shape == (cell_px, cell_px, 4)
        native[row * cell_px:(row + 1) * cell_px, col * cell_px:(col + 1) * cell_px] = block
    sheet = _upscale2x(native)
    path = tmp_path / f"{name}.png"
    Image.fromarray(sheet, "RGBA").save(path)
    return path


def _solid(cell_px: int, rgba: tuple[int, int, int, int]) -> np.ndarray:
    block = np.zeros((cell_px, cell_px, 4), dtype=np.uint8)
    block[:, :] = rgba
    return block


# --- _downscale_2x_majority ------------------------------------------------


def test_downscale_exact_nn_reproduces_source() -> None:
    rng = np.random.default_rng(0)
    native = rng.integers(0, 256, size=(6, 8, 4), dtype=np.uint8)
    up = _upscale2x(native)
    assert np.array_equal(_downscale_2x_majority(up), native)


def test_downscale_majority_wins_over_minority() -> None:
    # TL is the odd one out; the other 3 agree -> majority wins.
    block = np.array(
        [
            [[9, 9, 9, 255], [1, 1, 1, 255]],
            [[1, 1, 1, 255], [1, 1, 1, 255]],
        ],
        dtype=np.uint8,
    )
    out = _downscale_2x_majority(block)
    assert out.shape == (1, 1, 4)
    assert tuple(out[0, 0]) == (1, 1, 1, 255)


def test_downscale_full_tie_prefers_top_left() -> None:
    # All 4 candidates distinct -> every value tied at count 1 -> earliest (TL).
    block = np.array(
        [
            [[1, 0, 0, 255], [2, 0, 0, 255]],
            [[3, 0, 0, 255], [4, 0, 0, 255]],
        ],
        dtype=np.uint8,
    )
    out = _downscale_2x_majority(block)
    assert tuple(out[0, 0]) == (1, 0, 0, 255)


def test_downscale_partial_tie_prefers_earliest_tied_value() -> None:
    # TL is a unique singleton; TR and BL agree (the max-count pair); BR is a
    # unique singleton. The tie is between TR/BL (count 2) — TR is earliest.
    block = np.array(
        [
            [[9, 0, 0, 255], [5, 0, 0, 255]],
            [[5, 0, 0, 255], [7, 0, 0, 255]],
        ],
        dtype=np.uint8,
    )
    out = _downscale_2x_majority(block)
    assert tuple(out[0, 0]) == (5, 0, 0, 255)


# --- alpha binarization -----------------------------------------------------


def test_alpha_binarize_threshold() -> None:
    arr = np.array([[[10, 20, 30, 127], [40, 50, 60, 128]]], dtype=np.uint8)
    out = _binarize_alpha(arr)
    assert tuple(out[0, 0]) == TRANSPARENT
    assert tuple(out[0, 1]) == (40, 50, 60, 255)


# --- cycle detection ---------------------------------------------------------


def test_cycle_detection_neutral02(tmp_path: Path) -> None:
    cell_px = 4
    cells = {}
    for row in range(4):
        idle = _solid(cell_px, (10 * (row + 1), 1, 1, 255))
        walk_a = _solid(cell_px, (10 * (row + 1), 2, 1, 255))
        walk_b = _solid(cell_px, (10 * (row + 1), 3, 1, 255))
        cells[(row, 0)] = idle
        cells[(row, 2)] = idle  # col0 == col2 -> neutral02
        cells[(row, 1)] = walk_a
        cells[(row, 3)] = walk_b
    path = _make_sheet(tmp_path, cells, cell_px, name="neutral02")

    sprite = convert_character_sheet(path)
    assert sprite.cycle == "neutral02"
    # south idle (frame 0) should be col0's row0 color; south walk A/B (3,4)
    # should be col1/col3's row0 colors.
    assert sprite.frames[0][sprite.frames[0][..., 3] > 0][0, 0] == 10
    assert sprite.frames[3][sprite.frames[3][..., 3] > 0][0, 1] == 2
    assert sprite.frames[4][sprite.frames[4][..., 3] > 0][0, 1] == 3


def test_cycle_detection_neutral13(tmp_path: Path) -> None:
    cell_px = 4
    cells = {}
    for row in range(4):
        idle = _solid(cell_px, (10 * (row + 1), 1, 1, 255))
        walk_a = _solid(cell_px, (10 * (row + 1), 2, 1, 255))
        walk_b = _solid(cell_px, (10 * (row + 1), 3, 1, 255))
        cells[(row, 1)] = idle
        cells[(row, 3)] = idle  # col1 == col3 -> neutral13
        cells[(row, 0)] = walk_a
        cells[(row, 2)] = walk_b

    path = _make_sheet(tmp_path, cells, cell_px, name="neutral13")

    sprite = convert_character_sheet(path)
    assert sprite.cycle == "neutral13"
    assert sprite.frames[0][sprite.frames[0][..., 3] > 0][0, 0] == 10  # south idle = col1
    assert sprite.frames[3][sprite.frames[3][..., 3] > 0][0, 1] == 2  # south walk A = col0
    assert sprite.frames[4][sprite.frames[4][..., 3] > 0][0, 1] == 3  # south walk B = col2


def test_break_prop_sheet_converts_column0_stages(tmp_path: Path) -> None:
    """A BREAK_PROP_SHEETS sheet converts column 0's rows (top->bottom) into a
    4-frame break sequence — never the walk-cycle plan (frame 0 must be the
    intact object, matching the fork's sAnim_RockBreak frames 0..3)."""
    cell_px = 4
    cells = {
        (row, 0): _solid(cell_px, ((row + 1) * 20, 1, 1, 255)) for row in range(4)
    }
    path = _make_sheet(tmp_path, cells, cell_px, name="fk107-rocksmash")

    sprite = convert_character_sheet(path)
    assert sprite.cycle == "break_prop"
    assert len(sprite.frames) == 4
    for i, frame in enumerate(sprite.frames):
        vals = frame[frame[..., 3] > 0]
        assert vals[0, 0] == (i + 1) * 20  # row i -> break stage i


def test_break_prop_blank_intact_frame_raises(tmp_path: Path) -> None:
    cell_px = 4
    cells = {(1, 0): _solid(cell_px, (80, 70, 60, 255))}  # row 0 empty
    path = _make_sheet(tmp_path, cells, cell_px, name="fk107-rocksmash")
    with pytest.raises(ValueError, match="intact"):
        convert_character_sheet(path)


def test_cycle_detection_empty_pair_falls_back_to_distinct(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Prop sheets (fk107-rocksmash) keep the object in col0 and leave cols 1/3
    fully empty: "1 == 3" is vacuously true and used to pick a BLANK idle frame
    (the invisible-rock bug, boot gate 2026-07-06). An all-empty column pair
    must not count as the idle — fall back to distinct with idle=col0."""
    cell_px = 4
    cells = {(0, 0): _solid(cell_px, (80, 70, 60, 255))}  # rock in row0/col0 only
    path = _make_sheet(tmp_path, cells, cell_px, name="rock_sheet")

    with caplog.at_level(logging.WARNING):
        sprite = convert_character_sheet(path)

    assert sprite.cycle == "distinct"
    assert sprite.frames[0][..., 3].any()  # south idle frame is NOT blank
    assert sprite.frames[0][sprite.frames[0][..., 3] > 0][0, 0] == 80


def test_cycle_detection_all_empty_col0_raises(tmp_path: Path) -> None:
    """If even the fallback idle column is fully transparent the sprite would be
    invisible in-game — fail loud instead of emitting it."""
    cell_px = 4
    cells = {(0, 1): _solid(cell_px, (80, 70, 60, 255))}  # content only in col1
    path = _make_sheet(tmp_path, cells, cell_px, name="ghost_sheet")

    with pytest.raises(ValueError, match="fully transparent"):
        convert_character_sheet(path)


def test_cycle_detection_distinct_fallback_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    cell_px = 4
    cells = {}
    for row in range(4):
        for col in range(4):
            cells[(row, col)] = _solid(cell_px, ((row * 4 + col + 1) * 10, 1, 1, 255))
    path = _make_sheet(tmp_path, cells, cell_px, name="distinct_sheet")

    with caplog.at_level(logging.WARNING):
        sprite = convert_character_sheet(path)

    assert sprite.cycle == "distinct"
    assert any("distinct_sheet" in rec.message for rec in caplog.records)


# --- frame order mapping -----------------------------------------------------


def test_frame_order_mapping_matches_gba_convention(tmp_path: Path) -> None:
    cell_px = 4
    cells = {}
    for row in range(4):
        for col in range(4):
            cells[(row, col)] = _solid(cell_px, ((row * 4 + col + 1) * 10, 50, 90, 255))
    path = _make_sheet(tmp_path, cells, cell_px, name="order_sheet")

    sprite = convert_character_sheet(path)
    assert sprite.cycle == "distinct"  # idle=col0, walk=(1, 3)

    # Expected (row, col) source for each of the 9 GBA-order output frames.
    expected_sources = [
        (0, 0),  # 0 south idle
        (3, 0),  # 1 north idle
        (1, 0),  # 2 west idle
        (0, 1),  # 3 south walk A
        (0, 3),  # 4 south walk B
        (3, 1),  # 5 north walk A
        (3, 3),  # 6 north walk B
        (1, 1),  # 7 west walk A
        (1, 3),  # 8 west walk B
    ]
    assert sprite.content_size == (cell_px, cell_px)
    for idx, (row, col) in enumerate(expected_sources):
        expected_r = (row * 4 + col + 1) * 10
        opaque = sprite.frames[idx][..., 3] > 0
        assert opaque.sum() == cell_px * cell_px
        r_values = sprite.frames[idx][..., 0][opaque]
        assert (r_values == expected_r).all(), f"frame {idx}: expected R={expected_r}"


# --- shared-anchor placement -------------------------------------------------


def test_anchor_shared_offset_preserves_walk_bounce(tmp_path: Path) -> None:
    cell_px = 8
    color = (200, 30, 30, 255)

    def block_at(y0: int) -> np.ndarray:
        b = np.zeros((cell_px, cell_px, 4), dtype=np.uint8)
        b[y0:y0 + 4, 2:6] = color
        return b

    idle_block = block_at(2)   # rows 2-5
    walk_a_block = block_at(0)  # rows 0-3 (bounced up)
    walk_b_block = block_at(4)  # rows 4-7 (bounced down)

    cells = {}
    for row in (0, 1, 3):  # south, west, north all share the same pattern
        cells[(row, 0)] = idle_block
        cells[(row, 2)] = idle_block  # col0 == col2 -> neutral02
        cells[(row, 1)] = walk_a_block
        cells[(row, 3)] = walk_b_block
    path = _make_sheet(tmp_path, cells, cell_px, name="bounce")

    sprite = convert_character_sheet(path)
    assert sprite.cycle == "neutral02"
    assert sprite.content_size == (4, 8)  # union x:2-5 (w4), y:0-7 (h8)

    top = 32 - 8
    left = (32 - 4) // 2

    def rows_with_color(frame: np.ndarray) -> tuple[int, int]:
        ys, _ = np.where(frame[..., 3] > 0)
        return int(ys.min()), int(ys.max())

    # South idle: local y 2-5 -> canvas rows top+2..top+5 (NOT bottom-aligned).
    assert rows_with_color(sprite.frames[0]) == (top + 2, top + 5)
    # South walk A: local y 0-3 -> canvas rows top+0..top+3.
    assert rows_with_color(sprite.frames[3]) == (top + 0, top + 3)
    # South walk B: local y 4-7 -> canvas rows top+4..top+7; bottom == 31.
    a, b = rows_with_color(sprite.frames[4])
    assert (a, b) == (top + 4, top + 7)
    assert b == 31

    # Horizontally centered, same offset for every frame.
    for idx in (0, 3, 4):
        _, xs = np.where(sprite.frames[idx][..., 3] > 0)
        assert xs.min() == left
        assert xs.max() == left + 3


def test_anchor_fails_loud_on_oversize_content(tmp_path: Path) -> None:
    cell_px = 40  # native content bigger than the 32x32 GBA object frame
    block = _solid(cell_px, (5, 5, 5, 255))
    cells = {(0, 0): block, (1, 0): block, (3, 0): block}
    path = _make_sheet(tmp_path, cells, cell_px, name="too_big")

    with pytest.raises(ValueError, match="too_big"):
        convert_character_sheet(path)


def test_anchor_helper_fails_loud_on_oversize_content() -> None:
    frame = np.zeros((40, 40, 4), dtype=np.uint8)
    frame[:, :] = (1, 2, 3, 255)
    with pytest.raises(ValueError, match=r"40x40.*exceeds"):
        _anchor([frame] * 9, "direct_oversize")


# --- asymmetry ----------------------------------------------------------------


def test_asymmetry_zero_for_perfect_mirror() -> None:
    west = np.zeros((8, 8, 4), dtype=np.uint8)
    west[2:5, 1:3] = (10, 20, 30, 255)
    east = west[:, ::-1, :].copy()
    assert _asymmetry([west], [east]) == 0.0


def test_asymmetry_positive_for_unmirrored_row() -> None:
    west = np.zeros((8, 8, 4), dtype=np.uint8)
    west[2:5, 1:3] = (10, 20, 30, 255)
    east = west.copy()  # not mirrored — west's content isn't h-symmetric
    assert _asymmetry([west], [east]) > 0.0


def test_asymmetry_end_to_end(tmp_path: Path) -> None:
    cell_px = 8
    west_block = np.zeros((cell_px, cell_px, 4), dtype=np.uint8)
    west_block[2:5, 1:3] = (10, 20, 30, 255)
    mirrored_block = west_block[:, ::-1, :].copy()
    unmirrored_block = west_block.copy()

    idle = _solid(cell_px, (1, 1, 1, 255))

    # col2/col3 are left unset (transparent) everywhere and col1 is set only
    # on row0 -> cols_match(0,2) and cols_match(1,3) both fail at row0, so
    # this deterministically falls back to "distinct" with idle_col=0 (the
    # column carrying west_block/mirrored_block below), regardless of the
    # exact fallback rule.
    def cells(east_col0_row2: np.ndarray) -> dict[tuple[int, int], np.ndarray]:
        return {
            (0, 0): idle,
            (0, 1): idle,  # breaks cols_match(1,3) at row0
            (1, 0): west_block,
            (2, 0): east_col0_row2,
            (3, 0): idle,
        }

    path_mirror = _make_sheet(tmp_path, cells(mirrored_block), cell_px, name="mirror_sheet")
    sprite_mirror = convert_character_sheet(path_mirror)
    assert sprite_mirror.cycle == "distinct"
    assert sprite_mirror.asymmetry == 0.0

    # Unmirrored (east == west, not flipped) sheet.
    path_bad = _make_sheet(tmp_path, cells(unmirrored_block), cell_px, name="asym_sheet")
    sprite_bad = convert_character_sheet(path_bad)
    assert sprite_bad.cycle == "distinct"
    assert sprite_bad.asymmetry > 0.0


# --- input validation ---------------------------------------------------------


def test_sheet_size_not_divisible_by_8_fails_loud(tmp_path: Path) -> None:
    img = Image.new("RGBA", (30, 30), TRANSPARENT)
    path = tmp_path / "odd_size.png"
    img.save(path)
    with pytest.raises(ValueError, match="odd_size"):
        convert_character_sheet(path)


# --- dataclass sanity ----------------------------------------------------------


def test_converted_sprite_has_nine_frames_of_correct_shape(tmp_path: Path) -> None:
    cell_px = 4
    cells = {(row, col): _solid(cell_px, (1, 2, 3, 255)) for row in range(4) for col in range(4)}
    path = _make_sheet(tmp_path, cells, cell_px, name="shape_check")
    sprite = convert_character_sheet(path)
    assert isinstance(sprite, ConvertedSprite)
    assert sprite.name == "shape_check"
    assert len(sprite.frames) == 9
    for f in sprite.frames:
        assert f.shape == (32, 32, 4)
        assert f.dtype == np.uint8


# --- convert_player_sheets ------------------------------------------------------


def test_player_sheets_produce_18_frames_in_gba_order(tmp_path: Path) -> None:
    """Walk half (0-8) and run half (9-17) each follow `_FRAME_PLAN`'s GBA order
    (south/north/west idle, then south/north/west walk-A/walk-B) -- verified
    here with two disjoint colour ranges (walk R values 10-160, run R values
    110-260) so a frame landing in the wrong half is unambiguous."""
    cell_px = 4

    def sheet_cells(offset: int) -> dict[tuple[int, int], np.ndarray]:
        return {
            (row, col): _solid(cell_px, ((row * 4 + col + 1) * 5 + offset, 50, 90, 255))
            for row in range(4)
            for col in range(4)
        }

    walk_path = _make_sheet(tmp_path, sheet_cells(0), cell_px, name="HERO")
    run_path = _make_sheet(tmp_path, sheet_cells(150), cell_px, name="HERO-RUN")

    player = convert_player_sheets(walk_path, run_path)
    assert isinstance(player, ConvertedPlayer)
    assert len(player.frames) == NUM_PLAYER_OUTPUT_FRAMES
    for f in player.frames:
        assert f.shape == (32, 32, 4)
        assert f.dtype == np.uint8

    # Both sheets have every column distinct -> "distinct" cycle (idle=col0,
    # walk=(1,3)), same as test_frame_order_mapping_matches_gba_convention.
    expected_sources = [
        (0, 0), (3, 0), (1, 0),  # idle: south, north, west
        (0, 1), (0, 3),          # south walk A/B
        (3, 1), (3, 3),          # north walk A/B
        (1, 1), (1, 3),          # west walk A/B
    ]
    for half_idx, offset in ((0, 0), (9, 150)):
        for local_idx, (row, col) in enumerate(expected_sources):
            expected_r = (row * 4 + col + 1) * 5 + offset
            frame = player.frames[half_idx + local_idx]
            opaque = frame[..., 3] > 0
            assert opaque.sum() == cell_px * cell_px
            r_values = frame[..., 0][opaque]
            assert (r_values == expected_r).all(), (
                f"frame {half_idx + local_idx}: expected R={expected_r}, "
                f"got {set(r_values.tolist())}"
            )


def test_player_sheets_joint_anchor_shares_one_offset(tmp_path: Path) -> None:
    """Construct a walk sheet and a run sheet whose own content bounding boxes
    differ (walk: rows 2-5, height 4; run: rows 0-7, height 8) -- per-sheet
    anchoring (`convert_character_sheet`'s behaviour, applied independently to
    each) would place walk content at canvas rows 28-31 (its own height-4 bbox
    bottom-aligned) while run content would land at rows 24-31. Joint anchoring
    (one shared offset from the union bbox, height 8) must instead place BOTH
    at the union's top=24: walk's content (which only spans local rows 2-5)
    lands at canvas rows 26-29, not 28-31."""
    cell_px = 8
    color = (200, 30, 30, 255)

    def block(y0: int, y1: int) -> np.ndarray:
        b = np.zeros((cell_px, cell_px, 4), dtype=np.uint8)
        b[y0:y1, 2:6] = color
        return b

    walk_block = block(2, 6)  # native rows 2-5 (height 4)
    run_block = block(0, 8)   # native rows 0-7 (height 8)

    walk_cells = {(row, col): walk_block for row in range(4) for col in range(4)}
    run_cells = {(row, col): run_block for row in range(4) for col in range(4)}
    walk_path = _make_sheet(tmp_path, walk_cells, cell_px, name="HERO")
    run_path = _make_sheet(tmp_path, run_cells, cell_px, name="HERO-RUN")

    player = convert_player_sheets(walk_path, run_path)
    assert player.content_size == (4, 8)  # union: width 4 (cols 2-5), height 8 (rows 0-7)

    top = 32 - 8  # = 24
    left = (32 - 4) // 2  # = 14

    def rows_with_color(frame: np.ndarray) -> tuple[int, int]:
        ys, _ = np.where(frame[..., 3] > 0)
        return int(ys.min()), int(ys.max())

    def cols_with_color(frame: np.ndarray) -> tuple[int, int]:
        _, xs = np.where(frame[..., 3] > 0)
        return int(xs.min()), int(xs.max())

    # Walk half (frames 0-8): local content rows 2-5 -> canvas rows top+2..top+5.
    for idx in range(9):
        assert rows_with_color(player.frames[idx]) == (top + 2, top + 5), idx
        assert rows_with_color(player.frames[idx]) != (28, 31), (
            f"frame {idx}: looks like independent per-sheet anchoring was used, "
            "not the shared joint offset"
        )

    # Run half (frames 9-17): local content rows 0-7 -> canvas rows top..top+7.
    for idx in range(9, 18):
        assert rows_with_color(player.frames[idx]) == (top, top + 7), idx

    # Same horizontal offset shared by every frame in both halves (content
    # spans the union bbox's full width, cols 2-5 natively -> cols left..left+3
    # once pasted, since the union crop already starts at native col 2).
    for idx in range(18):
        assert cols_with_color(player.frames[idx]) == (left, left + 3), idx


def test_player_sheets_dimension_mismatch_fails_loud(tmp_path: Path) -> None:
    walk_cells = {(row, col): _solid(4, (1, 2, 3, 255)) for row in range(4) for col in range(4)}
    run_cells = {(row, col): _solid(8, (1, 2, 3, 255)) for row in range(4) for col in range(4)}
    walk_path = _make_sheet(tmp_path, walk_cells, 4, name="HERO")
    run_path = _make_sheet(tmp_path, run_cells, 8, name="HERO-RUN")

    with pytest.raises(ValueError, match="mismatched dimensions"):
        convert_player_sheets(walk_path, run_path)


def test_player_sheets_bad_dimensions_fails_loud(tmp_path: Path) -> None:
    img = Image.new("RGBA", (30, 30), TRANSPARENT)
    walk_path = tmp_path / "HERO.png"
    img.save(walk_path)
    run_cells = {(row, col): _solid(4, (1, 2, 3, 255)) for row in range(4) for col in range(4)}
    run_path = _make_sheet(tmp_path, run_cells, 4, name="HERO-RUN")

    with pytest.raises(ValueError, match="player walk"):
        convert_player_sheets(walk_path, run_path)
