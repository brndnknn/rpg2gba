"""RMXP character sheet (2x GBA scale) -> GBA object-event frames.

An Uranium `Graphics/Characters/*.png` sheet is a 4x4 grid: 4 columns are RMXP
animation patterns (0..3), 4 rows top->bottom are facing down/left/right/up
(RMXP direction codes 2, 4, 6, 8). The engine's `sAnimTable_Standard` instead
wants 9 frames — face south/north/west plus a walk-cycle pair for each — with
east produced at runtime by h-flipping west. This module converts one sheet.

Pipeline, in order (each step matters — cycle detection must run on the
binarized-but-not-yet-downscaled 2x art, and the asymmetry metric must be
measured before frames are anchored onto the 32x32 canvas):

  1. binarize alpha at 2x (GBA object palettes have no partial transparency)
  2. detect the RMXP animation cycle (which columns are idle vs. walk)
  3. select + downscale the 9 GBA-order frames (2x2-block majority vote)
  4. measure asymmetry between the mirrored west row and the real east row
  5. anchor all 9 frames onto a shared 32x32 canvas with ONE offset, so
     inter-frame motion (the walk bounce) survives

Fail loud (CLAUDE.md §4.5): a malformed sheet (bad dimensions, content that
doesn't fit the 32x32 object frame) aborts naming the sheet — never a silent
crop or blank substitute.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

GRID_SIZE = 4               # RMXP character sheet is a 4x4 grid
GBA_FRAME_PX = 32           # GBA object-event frame canvas
NUM_OUTPUT_FRAMES = 9
NUM_PLAYER_OUTPUT_FRAMES = 18  # player: walk half (0-8) + run half (9-17); see
                               # convert_player_sheets
_ALPHA_THRESHOLD = 128      # >= this (out of 255) -> fully opaque

# RMXP direction-code rows, top -> bottom.
ROW_DOWN, ROW_LEFT, ROW_RIGHT, ROW_UP = 0, 1, 2, 3

CycleName = Literal["neutral02", "neutral13", "distinct", "break_prop"]

# Sheets that are BREAK PROPS, not walk cycles: rows top->bottom are the object's
# destruction stages (RMXP animated them by "turning" the event), all in column 0.
# They convert to a 4-frame break sequence matching the fork's sAnim_RockBreak
# (frames 0..3 then ANIMCMD_END) and get sAnimTable_BreakableRock semantics at
# emission — sAnimTable_Standard's index 1 (ANIM_REMOVE_OBSTACLE) is a LOOPING
# walk anim, which left rock_smash_break waiting forever (debris never removed,
# boot gate 2026-07-06).
BREAK_PROP_SHEETS = frozenset({"fk107-rocksmash"})
NUM_BREAK_PROP_FRAMES = 4

# Output frame order (sAnimTable_Standard): (source row, column role). "idle"/
# "walkA"/"walkB" are resolved to actual columns by cycle detection.
_FRAME_PLAN: tuple[tuple[int, str], ...] = (
    (ROW_DOWN, "idle"),    # 0 face south
    (ROW_UP, "idle"),      # 1 face north
    (ROW_LEFT, "idle"),    # 2 face west
    (ROW_DOWN, "walkA"),   # 3 south step A
    (ROW_DOWN, "walkB"),   # 4 south step B
    (ROW_UP, "walkA"),     # 5 north step A
    (ROW_UP, "walkB"),     # 6 north step B
    (ROW_LEFT, "walkA"),   # 7 west step A
    (ROW_LEFT, "walkB"),   # 8 west step B
)
# Indices into the 9-frame plan above that carry the west row (used again,
# pre-anchor, for the asymmetry metric against the un-emitted east row).
_WEST_IDLE_IDX, _WEST_WALK_A_IDX, _WEST_WALK_B_IDX = 2, 7, 8


@dataclass
class ConvertedSprite:
    """One converted character sheet, ready for GBA object-event emission."""

    name: str                      # sheet stem (e.g. "HGSS_000")
    frames: list[np.ndarray]       # 9x (32, 32, 4) uint8 RGBA, GBA order (see _FRAME_PLAN)
    cycle: CycleName
    asymmetry: float               # 0.0 == east row is an exact mirror of west
    content_size: tuple[int, int]  # union bbox (w, h) after downscale, pre-anchor padding


@dataclass
class ConvertedPlayer:
    """The player's walk+run sheets, converted and jointly anchored, ready for GBA
    object-event emission. Frames 0-8 are the walk half, 9-17 the run half — each
    half in the same GBA order as `ConvertedSprite.frames` (see `_FRAME_PLAN`); the
    engine's `sAnimTable_BrendanMayNormal` indexes both halves in exactly that
    layout (verified against `object_event_anims.h`, see `convert_player_sheets`)."""

    frames: list[np.ndarray]       # 18x (32, 32, 4) uint8 RGBA: [0:9]=walk, [9:18]=run
    walk_cycle: CycleName
    run_cycle: CycleName
    content_size: tuple[int, int]  # shared union bbox (w, h) across all 18 frames


def _load_and_binarize(path: Path, name: str) -> tuple[np.ndarray, int, int]:
    """Load an RMXP 4x4 character sheet PNG, binarize its alpha (see
    `_binarize_alpha`), and return `(binarized_arr, frame_w, frame_h)`. Fails loud
    on a sheet whose dimensions aren't both divisible by 8 (each cell must halve
    evenly under the 2x downscale)."""
    img = Image.open(path).convert("RGBA")
    width, height = img.size
    if width % 8 or height % 8:
        raise ValueError(
            f"{name}: sheet is {width}x{height}, but a 4x4 RMXP character grid "
            f"(each cell halved by the 2x downscale) requires both dimensions "
            f"divisible by 8"
        )
    arr = _binarize_alpha(np.asarray(img))
    frame_w, frame_h = width // GRID_SIZE, height // GRID_SIZE
    return arr, frame_w, frame_h


def _cell_accessor(arr: np.ndarray, frame_w: int, frame_h: int) -> Callable[[int, int], np.ndarray]:
    """A `(row, col) -> native cell block` accessor over a binarized 4x4 sheet."""

    def cell(row: int, col: int) -> np.ndarray:
        return arr[row * frame_h:(row + 1) * frame_h, col * frame_w:(col + 1) * frame_w]

    return cell


def _walk_cycle_native_frames(
    cell: Callable[[int, int], np.ndarray], name: str
) -> tuple[list[np.ndarray], CycleName, dict[str, int]]:
    """Detect the RMXP animation cycle and downscale the 9 GBA-order native
    (pre-anchor) frames for one walk-cycle sheet (see `_FRAME_PLAN`). Returns the
    frames, the detected cycle, and the resolved role->column mapping (the caller
    may need the latter again, e.g. for the east-row asymmetry check)."""
    cycle, idle_col, walk_cols = _detect_cycle(cell, name)
    cols = {"idle": idle_col, "walkA": walk_cols[0], "walkB": walk_cols[1]}
    native_frames = [_downscale_2x_majority(cell(row, cols[role])) for row, role in _FRAME_PLAN]
    return native_frames, cycle, cols


def convert_character_sheet(path: Path) -> ConvertedSprite:
    """Convert one RMXP character sheet PNG into a `ConvertedSprite`."""
    name = Path(path).stem
    arr, frame_w, frame_h = _load_and_binarize(path, name)
    cell = _cell_accessor(arr, frame_w, frame_h)

    if name in BREAK_PROP_SHEETS:
        # Break sequence = column 0, rows top->bottom (intact -> shattered).
        native_frames = [
            _downscale_2x_majority(cell(row, 0)) for row in range(GRID_SIZE)
        ]
        if not native_frames[0][..., 3].any():
            raise ValueError(
                f"{name}: break-prop frame 0 (the intact object) is fully "
                "transparent — the object would be invisible"
            )
        frames, content_size = _anchor(native_frames, name)
        return ConvertedSprite(
            name=name,
            frames=frames,
            cycle="break_prop",
            asymmetry=0.0,
            content_size=content_size,
        )

    native_frames, cycle, cols = _walk_cycle_native_frames(cell, name)

    east_native = [
        _downscale_2x_majority(cell(ROW_RIGHT, cols[role]))
        for role in ("idle", "walkA", "walkB")
    ]
    west_native = [
        native_frames[_WEST_IDLE_IDX],
        native_frames[_WEST_WALK_A_IDX],
        native_frames[_WEST_WALK_B_IDX],
    ]
    asymmetry = _asymmetry(west_native, east_native)

    frames, content_size = _anchor(native_frames, name)
    return ConvertedSprite(
        name=name,
        frames=frames,
        cycle=cycle,
        asymmetry=asymmetry,
        content_size=content_size,
    )


def convert_player_sheets(walk_png: Path, run_png: Path) -> ConvertedPlayer:
    """Convert the player's walk + run RMXP character sheets into one
    `ConvertedPlayer` — 18 frames in the exact order the fork's
    `sAnimTable_BrendanMayNormal` expects.

    Frame-order finding (verified against `engine/src/data/object_events/
    object_event_anims.h`, HEAD 21c24202, this fork has `IS_FRLG == 0` — see
    `include/constants/global.h` — so the non-FRLG `sAnim_Run*` apply):
    walking half indices 0-8 are `sAnim_FaceSouth/North/West` (frames 0/1/2) and
    `sAnim_GoSouth/North/West` (step pairs 3/4, 5/6, 7/8) — identical to
    `_FRAME_PLAN`. The running half indices 9-17 are `sAnim_RunSouth/North/West`
    (`ANIMCMD_FRAME(12,5), FRAME(9,3), FRAME(13,5), FRAME(9,3)` etc): idle-run
    frames land at 9 (south) / 10 (north) / 11 (west), and step pairs at
    12/13 (south), 14/15 (north), 16/17 (west) — i.e. the SAME `_FRAME_PLAN`
    layout, offset by +9. No reordering of the run half is needed; each sheet's
    own 9 native frames are produced with the same `_FRAME_PLAN` machinery used
    for NPC sheets, then concatenated walk-then-run.

    Both sheets are jointly anchored with ONE shared offset (`_anchor` over all
    18 native frames together) so the walk<->run transition doesn't hop by a
    pixel — this is the one respect in which player conversion differs from the
    per-sheet `convert_character_sheet` anchoring.

    Fails loud (CLAUDE.md §4.5) on malformed sheet dimensions, a walk/run size
    mismatch, or content that doesn't fit the shared 32x32 canvas.
    """
    walk_name = f"{Path(walk_png).stem} (player walk)"
    run_name = f"{Path(run_png).stem} (player run)"

    walk_arr, walk_fw, walk_fh = _load_and_binarize(walk_png, walk_name)
    run_arr, run_fw, run_fh = _load_and_binarize(run_png, run_name)
    if (walk_arr.shape[:2], walk_fw, walk_fh) != (run_arr.shape[:2], run_fw, run_fh):
        raise ValueError(
            f"player walk/run sheets have mismatched dimensions: "
            f"walk {walk_arr.shape[1]}x{walk_arr.shape[0]} vs "
            f"run {run_arr.shape[1]}x{run_arr.shape[0]}"
        )

    walk_native, walk_cycle, _ = _walk_cycle_native_frames(
        _cell_accessor(walk_arr, walk_fw, walk_fh), walk_name
    )
    run_native, run_cycle, _ = _walk_cycle_native_frames(
        _cell_accessor(run_arr, run_fw, run_fh), run_name
    )

    frames, content_size = _anchor(walk_native + run_native, "player")
    return ConvertedPlayer(
        frames=frames,
        walk_cycle=walk_cycle,
        run_cycle=run_cycle,
        content_size=content_size,
    )


def _binarize_alpha(arr: np.ndarray) -> np.ndarray:
    """Binarize alpha (2x, before any other step): >=128 -> opaque (255, RGB
    kept); else fully transparent (0, 0, 0, 0). GBA object palettes have no
    partial transparency; Uranium touch-ups can carry antialiased alpha."""
    out = np.zeros_like(arr)
    opaque = arr[..., 3] >= _ALPHA_THRESHOLD
    out[opaque, :3] = arr[opaque, :3]
    out[opaque, 3] = 255
    return out


def _detect_cycle(
    cell: Callable[[int, int], np.ndarray], name: str
) -> tuple[CycleName, int, tuple[int, int]]:
    """Which RMXP columns are the idle frame vs. the walk-step pair.

    RMXP loops columns 0->1->2->3. If column 0 is pixel-identical to column 2
    in every row, 0 is the idle (neutral) frame and 1/3 are the walk steps
    (`neutral02`); if 1 mirrors 3 instead, it's `neutral13`. Neither matching
    is `distinct` — falls back to idle=0, walk=(1, 3), logged."""

    def cols_match(a: int, b: int) -> bool:
        return all(np.array_equal(cell(row, a), cell(row, b)) for row in range(GRID_SIZE))

    def col_empty(c: int) -> bool:
        return all(not cell(row, c)[..., 3].any() for row in range(GRID_SIZE))

    # A pair only counts as the idle column if it has content: prop sheets like
    # fk107-rocksmash keep the object in column 0 and leave 1/3 fully empty —
    # "1 == 3" is then vacuously true and would pick a BLANK idle frame (the
    # invisible-rock bug, boot gate 2026-07-06).
    if cols_match(0, 2) and not col_empty(0):
        return "neutral02", 0, (1, 3)
    if cols_match(1, 3) and not col_empty(1):
        return "neutral13", 1, (0, 2)
    if col_empty(0):
        raise ValueError(
            f"{name}: column 0 (the fallback idle frame) is fully transparent in "
            "every row — the converted sprite would be invisible"
        )
    logger.warning(
        "%s: neither column pair (0,2) nor (1,3) is pixel-identical across all "
        "%d rows; falling back to distinct cycle (idle=col0, walk=col1/3)",
        name,
        GRID_SIZE,
    )
    return "distinct", 0, (1, 3)


def _downscale_2x_majority(arr: np.ndarray) -> np.ndarray:
    """2x downscale by per-2x2-block majority vote over RGBA identity.

    Candidates are the 4 (already-binarized) pixels in top-left, top-right,
    bottom-left, bottom-right order. The most frequent value wins; ties are
    broken by preferring the earliest candidate (in that order) among the
    values tied for the max count. On an exact 2x nearest-neighbour source
    (all 4 candidates equal) this reproduces the source pixel exactly."""
    h, w = arr.shape[:2]
    if h % 2 or w % 2:
        raise ValueError(f"cannot 2x-downscale an odd-sized block {arr.shape[:2]}")
    candidates = np.stack(
        [arr[0::2, 0::2], arr[0::2, 1::2], arr[1::2, 0::2], arr[1::2, 1::2]],
        axis=0,
    )  # (4, h/2, w/2, 4) in TL, TR, BL, BR order
    counts = np.zeros(candidates.shape[:3], dtype=np.int32)
    for i in range(4):
        for j in range(4):
            counts[i] += np.all(candidates[i] == candidates[j], axis=-1)
    max_count = counts.max(axis=0)

    out = candidates[0].copy()
    decided = counts[0] == max_count
    for i in range(1, 4):
        take = ~decided & (counts[i] == max_count)
        out[take] = candidates[i][take]
        decided |= take
    return out


def _asymmetry(west_frames: list[np.ndarray], east_frames: list[np.ndarray]) -> float:
    """Fraction of pixels, over the union of opaque pixels in either, where
    h-mirrored west differs from the real east row (RGBA or opacity
    mismatch — both are captured by full-tuple inequality since alpha is one
    of the compared channels). 0.0 = east is an exact mirror of west."""
    diff = 0
    union = 0
    for west, east in zip(west_frames, east_frames, strict=True):
        mirrored = west[:, ::-1, :]
        opaque = (mirrored[..., 3] > 0) | (east[..., 3] > 0)
        mismatch = np.any(mirrored != east, axis=-1)
        diff += int(np.count_nonzero(mismatch & opaque))
        union += int(np.count_nonzero(opaque))
    return diff / union if union else 0.0


def _anchor(
    native_frames: list[np.ndarray], name: str
) -> tuple[list[np.ndarray], tuple[int, int]]:
    """Place all 9 frames on a shared 32x32 canvas with ONE offset: the union
    bounding box of opaque pixels (across all frames) horizontally centered,
    bottom row at canvas row 31. A single shared offset (rather than
    per-frame recentering) is what preserves the walk-cycle bounce."""
    min_x = min_y = max_x = max_y = None
    for f in native_frames:
        ys, xs = np.where(f[..., 3] > 0)
        if xs.size == 0:
            continue
        x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
        min_x = x0 if min_x is None else min(min_x, x0)
        max_x = x1 if max_x is None else max(max_x, x1)
        min_y = y0 if min_y is None else min(min_y, y0)
        max_y = y1 if max_y is None else max(max_y, y1)

    if min_x is None:
        raise ValueError(f"{name}: all {len(native_frames)} output frames are fully transparent")

    bbox_w, bbox_h = max_x - min_x + 1, max_y - min_y + 1
    if bbox_w > GBA_FRAME_PX or bbox_h > GBA_FRAME_PX:
        raise ValueError(
            f"{name}: content bbox {bbox_w}x{bbox_h} exceeds the "
            f"{GBA_FRAME_PX}x{GBA_FRAME_PX} GBA object frame"
        )

    left = (GBA_FRAME_PX - bbox_w) // 2
    top = GBA_FRAME_PX - bbox_h  # union bottom row lands on canvas row 31

    anchored = []
    for f in native_frames:
        canvas = np.zeros((GBA_FRAME_PX, GBA_FRAME_PX, 4), dtype=np.uint8)
        canvas[top:top + bbox_h, left:left + bbox_w] = f[min_y:max_y + 1, min_x:max_x + 1]
        anchored.append(canvas)
    return anchored, (bbox_w, bbox_h)
