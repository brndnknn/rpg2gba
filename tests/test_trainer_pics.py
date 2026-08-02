"""Uranium trainer front/back pic -> pokeemerald-expansion 4bpp sprite converter."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rpg2gba.trainer_converter.common import (
    BACK_PIC_FRAMES,
    TRAINER_MAX_COLORS,
    TRAINER_PIC_SIZE,
    TrainerPicSpec,
    resolve_case,
    uranium_trainer_back,
    uranium_trainer_front,
)
from rpg2gba.trainer_converter.pics import (
    BackPicResult,
    FrontPicResult,
    build_contact_sheet,
    convert_back_pic,
    convert_front_pic,
)

RIVAL_SPEC = TrainerPicSpec(86, "RIVAL")
PLAYER_SPEC = TrainerPicSpec(0, "PLAYER_MALE")


# --- Synthetic fixture builders ---------------------------------------------


def _rgba_canvas(w: int, h: int) -> np.ndarray:
    return np.zeros((h, w, 4), dtype=np.uint8)


def _fill_rect(
    arr: np.ndarray, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]
) -> None:
    """Fill an inclusive rect with a solid opaque colour."""
    arr[y0 : y1 + 1, x0 : x1 + 1, 0] = color[0]
    arr[y0 : y1 + 1, x0 : x1 + 1, 1] = color[1]
    arr[y0 : y1 + 1, x0 : x1 + 1, 2] = color[2]
    arr[y0 : y1 + 1, x0 : x1 + 1, 3] = 255


def _save(arr: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, mode="RGBA").save(path)


def _front_source(tmp_path: Path, trainer_id: int, uppercase: bool = False) -> Path:
    """A 100x50 opaque rect (non-square, multi-colour) on a 160x160 canvas."""
    arr = _rgba_canvas(160, 160)
    _fill_rect(arr, 20, 60, 119, 109, (200, 40, 40))
    _fill_rect(arr, 20, 60, 40, 70, (40, 200, 40))  # a second colour in-bbox
    ext = "PNG" if uppercase else "png"
    path = tmp_path / "Graphics" / "Characters" / f"trainer{trainer_id:03d}.{ext}"
    _save(arr, path)
    return path


def _back_strip(
    tmp_path: Path,
    trainer_id: int,
    *,
    width: int = 640,
    height: int = 234,
    frame_offsets: list[int] | None = None,
    rect_w: int = 30,
    rect_h: int = 80,
) -> Path:
    """A `BACK_PIC_FRAMES`-frame horizontal strip. Each frame gets an opaque
    rect anchored to the bottom of the frame at x-offset `frame_offsets[i]`
    (defaults: same offset in every frame)."""
    fw = width // BACK_PIC_FRAMES
    if frame_offsets is None:
        frame_offsets = [10] * BACK_PIC_FRAMES
    arr = _rgba_canvas(width, height)
    for i, off in enumerate(frame_offsets):
        x0 = i * fw + off
        x1 = x0 + rect_w - 1
        y1 = height - 1
        y0 = y1 - rect_h + 1
        _fill_rect(arr, x0, y0, x1, y1, (60 + i * 30, 100, 180))
    path = tmp_path / "Graphics" / "Characters" / f"trback{trainer_id:03d}.png"
    _save(arr, path)
    return path


# --- 1. Front pic geometry ----------------------------------------------------


def test_front_pic_non_square_dimensions_and_colors(tmp_path: Path) -> None:
    uranium_src = tmp_path / "uranium"
    _front_source(uranium_src, RIVAL_SPEC.trainer_id)
    out_dir = tmp_path / "out" / "front"

    result = convert_front_pic(uranium_src, RIVAL_SPEC, out_dir)

    img = Image.open(result.front_path)
    assert img.size == (TRAINER_PIC_SIZE, TRAINER_PIC_SIZE)
    assert img.mode == "P"

    idx = np.asarray(img)
    assert idx.max() <= TRAINER_MAX_COLORS  # index 0 (transparent) + <=15 opaque slots
    assert result.opaque_color_count <= TRAINER_MAX_COLORS


def test_front_pic_aspect_ratio_preserved(tmp_path: Path) -> None:
    uranium_src = tmp_path / "uranium"
    _front_source(uranium_src, RIVAL_SPEC.trainer_id)
    out_dir = tmp_path / "out" / "front"

    result = convert_front_pic(uranium_src, RIVAL_SPEC, out_dir)

    src_w, src_h = result.source_bbox
    scaled_w, scaled_h = result.scaled_size
    expected_h = round(scaled_w * src_h / src_w)
    assert abs(expected_h - scaled_h) <= 1


# --- 2. Back pic geometry ------------------------------------------------------


def test_back_pic_dimensions_and_bottom_anchor(tmp_path: Path) -> None:
    uranium_src = tmp_path / "uranium"
    _back_strip(uranium_src, PLAYER_SPEC.trainer_id)
    out_dir = tmp_path / "out" / "back"

    result = convert_back_pic(uranium_src, PLAYER_SPEC, out_dir)

    img = Image.open(result.back_path)
    assert img.size == (TRAINER_PIC_SIZE, TRAINER_PIC_SIZE * BACK_PIC_FRAMES)
    assert img.mode == "P"
    assert result.opaque_color_count <= TRAINER_MAX_COLORS

    idx = np.asarray(img)  # (256, 64)
    for i in range(BACK_PIC_FRAMES):
        frame = idx[i * TRAINER_PIC_SIZE : (i + 1) * TRAINER_PIC_SIZE, :]
        # content reached the source frame's bottom edge -> bottom-anchored
        # output should have opaque pixels on its last row.
        assert (frame[-1, :] != 0).any(), f"frame {i} not bottom-anchored"

    # single shared palette: exactly one .pal file for all 4 frames.
    assert result.pal_path.exists()


def test_back_pic_floor_division_drops_remainder(tmp_path: Path) -> None:
    """Width 662 -> frames of 165 (662 // 4), remainder 2px dropped, no raise."""
    uranium_src = tmp_path / "uranium"
    _back_strip(uranium_src, PLAYER_SPEC.trainer_id, width=662, height=236)
    out_dir = tmp_path / "out" / "back"

    result = convert_back_pic(uranium_src, PLAYER_SPEC, out_dir)
    assert result.frame_count == BACK_PIC_FRAMES


def test_back_pic_shared_crop_window_preserves_frame_offsets(tmp_path: Path) -> None:
    """Frames with deliberately different content bboxes must NOT be
    independently re-centered -- the horizontal offset relationship between
    frames must survive conversion."""
    uranium_src = tmp_path / "uranium"
    offsets = [10, 30, 10, 50]  # deliberately different per-frame x offsets
    _back_strip(uranium_src, PLAYER_SPEC.trainer_id, frame_offsets=offsets, rect_w=20, rect_h=60)
    out_dir = tmp_path / "out" / "back"

    result = convert_back_pic(uranium_src, PLAYER_SPEC, out_dir)
    idx = np.asarray(Image.open(result.back_path))

    def leftmost_opaque_col(frame: np.ndarray) -> int:
        cols = np.where((frame != 0).any(axis=0))[0]
        assert cols.size > 0
        return int(cols.min())

    output_lefts = []
    for i in range(BACK_PIC_FRAMES):
        frame = idx[i * TRAINER_PIC_SIZE : (i + 1) * TRAINER_PIC_SIZE, :]
        output_lefts.append(leftmost_opaque_col(frame))

    # Expected relative offsets (source space) vs measured (output space,
    # scaled) should agree up to the scale factor within rounding.
    for i in range(1, BACK_PIC_FRAMES):
        expected_delta = (offsets[i] - offsets[0]) * result.scale_factor
        measured_delta = output_lefts[i] - output_lefts[0]
        assert abs(measured_delta - expected_delta) <= 2, (
            f"frame {i}: expected delta ~{expected_delta:.1f}, got {measured_delta} "
            f"-- frames may have been independently re-centered"
        )


# --- 5. Uppercase .PNG resolution ----------------------------------------------


def test_uppercase_png_extension_resolves(tmp_path: Path) -> None:
    uranium_src = tmp_path / "uranium"
    _front_source(uranium_src, 0, uppercase=True)
    out_dir = tmp_path / "out"

    result = convert_front_pic(uranium_src, PLAYER_SPEC, out_dir)
    assert result.front_path.exists()


def test_resolve_case_helper_finds_uppercase_sibling(tmp_path: Path) -> None:
    uranium_src = tmp_path / "uranium"
    _front_source(uranium_src, 0, uppercase=True)
    wanted = uranium_trainer_front(uranium_src, 0)
    resolved = resolve_case(wanted)
    assert resolved.name == "trainer000.PNG"


# --- 6. Fail-loud cases ---------------------------------------------------------


def test_missing_front_file_raises(tmp_path: Path) -> None:
    uranium_src = tmp_path / "uranium"
    (uranium_src / "Graphics" / "Characters").mkdir(parents=True)
    out_dir = tmp_path / "out"
    with pytest.raises(FileNotFoundError):
        convert_front_pic(uranium_src, RIVAL_SPEC, out_dir)


def test_missing_front_file_no_parent_dir_raises(tmp_path: Path) -> None:
    uranium_src = tmp_path / "uranium"
    out_dir = tmp_path / "out"
    with pytest.raises(FileNotFoundError):
        convert_front_pic(uranium_src, RIVAL_SPEC, out_dir)


def test_fully_transparent_front_raises(tmp_path: Path) -> None:
    uranium_src = tmp_path / "uranium"
    arr = _rgba_canvas(160, 160)  # fully transparent, nothing filled
    path = uranium_trainer_front(uranium_src, RIVAL_SPEC.trainer_id)
    _save(arr, path)
    out_dir = tmp_path / "out"
    with pytest.raises(ValueError, match="transparent"):
        convert_front_pic(uranium_src, RIVAL_SPEC, out_dir)


def test_fully_transparent_back_raises(tmp_path: Path) -> None:
    uranium_src = tmp_path / "uranium"
    arr = _rgba_canvas(640, 234)  # fully transparent
    path = uranium_trainer_back(uranium_src, PLAYER_SPEC.trainer_id)
    _save(arr, path)
    out_dir = tmp_path / "out"
    with pytest.raises(ValueError, match="transparent"):
        convert_back_pic(uranium_src, PLAYER_SPEC, out_dir)


def test_back_strip_narrower_than_frames_raises(tmp_path: Path) -> None:
    uranium_src = tmp_path / "uranium"
    arr = _rgba_canvas(3, 20)  # narrower than BACK_PIC_FRAMES=4
    path = uranium_trainer_back(uranium_src, PLAYER_SPEC.trainer_id)
    _save(arr, path)
    out_dir = tmp_path / "out"
    with pytest.raises(ValueError, match="frames"):
        convert_back_pic(uranium_src, PLAYER_SPEC, out_dir)


# --- 7. Idempotence --------------------------------------------------------------


def test_front_pic_conversion_is_idempotent(tmp_path: Path) -> None:
    uranium_src = tmp_path / "uranium"
    _front_source(uranium_src, RIVAL_SPEC.trainer_id)
    out_dir = tmp_path / "out"

    r1 = convert_front_pic(uranium_src, RIVAL_SPEC, out_dir)
    png_bytes_1 = r1.front_path.read_bytes()
    pal_bytes_1 = r1.pal_path.read_bytes()

    r2 = convert_front_pic(uranium_src, RIVAL_SPEC, out_dir)
    png_bytes_2 = r2.front_path.read_bytes()
    pal_bytes_2 = r2.pal_path.read_bytes()

    assert png_bytes_1 == png_bytes_2
    assert pal_bytes_1 == pal_bytes_2
    assert r1 == r2


def test_back_pic_conversion_is_idempotent(tmp_path: Path) -> None:
    uranium_src = tmp_path / "uranium"
    _back_strip(uranium_src, PLAYER_SPEC.trainer_id)
    out_dir = tmp_path / "out"

    r1 = convert_back_pic(uranium_src, PLAYER_SPEC, out_dir)
    png_bytes_1 = r1.back_path.read_bytes()
    pal_bytes_1 = r1.pal_path.read_bytes()

    r2 = convert_back_pic(uranium_src, PLAYER_SPEC, out_dir)
    png_bytes_2 = r2.back_path.read_bytes()
    pal_bytes_2 = r2.pal_path.read_bytes()

    assert png_bytes_1 == png_bytes_2
    assert pal_bytes_1 == pal_bytes_2
    assert r1 == r2


# --- Contact sheet smoke test ----------------------------------------------------


def test_build_contact_sheet_writes_png(tmp_path: Path) -> None:
    uranium_src = tmp_path / "uranium"
    _front_source(uranium_src, RIVAL_SPEC.trainer_id)
    _back_strip(uranium_src, PLAYER_SPEC.trainer_id)
    out_dir = tmp_path / "out"

    front = convert_front_pic(uranium_src, RIVAL_SPEC, out_dir / "front")
    back = convert_back_pic(uranium_src, PLAYER_SPEC, out_dir / "back")

    sheet_path = out_dir / "contact_sheet.png"
    build_contact_sheet(front, back, sheet_path)
    assert sheet_path.exists()
    img = Image.open(sheet_path)
    assert img.size[0] > 0 and img.size[1] > 0


# --- 8. Real-art smoke test (skips cleanly without RPG2GBA_URANIUM_SRC) ---------


def test_real_art_trainer086_front_and_trback000_back(tmp_path: Path) -> None:
    src = os.environ.get("RPG2GBA_URANIUM_SRC")
    if not src:
        pytest.skip("RPG2GBA_URANIUM_SRC not set")
    uranium_src = Path(src)
    if not uranium_src.is_dir():
        pytest.skip(f"{uranium_src} not found")

    front_spec = TrainerPicSpec(86, "RIVAL")
    back_spec = TrainerPicSpec(0, "PLAYER_MALE")
    out_dir = tmp_path / "out"

    front = convert_front_pic(uranium_src, front_spec, out_dir / "front")
    back = convert_back_pic(uranium_src, back_spec, out_dir / "back")

    assert Image.open(front.front_path).size == (TRAINER_PIC_SIZE, TRAINER_PIC_SIZE)
    assert Image.open(back.back_path).size == (
        TRAINER_PIC_SIZE,
        TRAINER_PIC_SIZE * BACK_PIC_FRAMES,
    )
