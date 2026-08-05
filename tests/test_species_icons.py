"""Tests for `rpg2gba.species_converter.icons` (W3, STARTER_SPECIES_PLAN.md).

Per CLAUDE.md §4.6: a frame-restack round-trip test, a golden test pinning
each starter's chosen shared icon palette, and a structural edge test on the
emitted PNGs. Uranium-asset-backed tests skip cleanly (not fail) when
`RPG2GBA_URANIUM_SRC` is unset, matching `tests/conftest.py`'s convention for
the rest of the suite. The six shared icon palettes live in the vendored
`engine/` tree (committed, not gitignored), so palette-only tests never skip.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rpg2gba.species_converter.common import (
    ICON_HEIGHT,
    ICON_PALETTE_COUNT,
    ICON_WIDTH,
    STARTER_SPECIES,
)
from rpg2gba.species_converter.icons import (
    CONTACT_SHEET_NAME,
    MANIFEST_NAME,
    IconPalette,
    choose_palette,
    convert_starter_icons,
    load_icon_palettes,
    remap_to_palette,
    stack_icon_frames,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = REPO_ROOT / "engine"

# Pinned 2026-07-18 against the real Uranium assets + the vendored engine's
# six shared icon palettes (engine/graphics/pokemon/icon_palettes/pal0..5.pal,
# pinned 21c24202). A future change to the remap metric that reassigns any of
# these should show up here as an explicit diff, never a silent art
# regression (STARTER_SPECIES_PLAN.md W3).
EXPECTED_ICON_PAL_INDEX = {
    "ORCHYNX": 1,
    "METALYNX": 1,
    "RAPTORCH": 1,
    "ARCHILLES": 1,
    "ELETUX": 3,
    "ELECTRUXO": 3,
    # Pinned 2026-08-05 against the same real Uranium assets + vendored
    # engine icon palettes, for the Route-1 trainer-party species (+ their
    # evolution-chain closure, see common.py's STARTER_SPECIES comment).
    # Computed via convert_species_icon, then spot-checked by eye against a
    # rendered contact sheet (icons.write_contact_sheet) for BIRBIE, FOLEROG,
    # NIMFLORA, OWTEN, and CUBBUG: each chosen palette preserves the
    # sprite's actual colour family (BIRBIE's navy/black -> pal4's dark
    # blues, OWTEN's brown/tan -> pal2's warm browns, CUBBUG's pink -> pal0,
    # FOLEROG's blue -> pal3, NIMFLORA's green/pink -> pal5) rather than
    # snapping to an unrelated hue -- no palette here reads as a mismatch to
    # the eye, just the expected loss of saturation/brightness range that
    # comes from only 6 shared palettes covering the whole cast.
    "CHYINMUNK": 2,
    "KINETMUNK": 2,
    "BIRBIE": 4,
    "AVEDEN": 4,
    "SPLENDIFOWL": 4,
    "CUBBUG": 0,
    "CUBBLFLY": 1,
    "NIMFLORA": 5,
    "BAREWL": 2,
    "DEAREWL": 0,
    "GARAREWL": 5,
    "TONEMY": 2,
    "TOFURANG": 0,
    "FARTOG": 0,
    "FOLEROG": 3,
    "BLUBELROG": 3,
    "OWTEN": 2,
    "ESHOUTEN": 1,
}


@pytest.fixture(scope="session")
def uranium_src() -> Path:
    """Root of the Uranium source tree (parent of `Graphics/`) -- distinct
    from `tests/conftest.py`'s `uranium_data` fixture, which points at the
    `Data/` subdirectory instead. Skips cleanly when unavailable."""
    src = os.environ.get("RPG2GBA_URANIUM_SRC")
    if not src:
        pytest.skip("RPG2GBA_URANIUM_SRC not set")
    path = Path(src)
    if not path.is_dir():
        pytest.skip(f"{path} not found")
    return path


@pytest.fixture(scope="session")
def icon_palettes() -> list[IconPalette]:
    return load_icon_palettes(ENGINE_ROOT)


# --- frame-restack round-trip -------------------------------------------------


def _solid_frame(color: tuple[int, int, int], size: int = 64) -> np.ndarray:
    frame = np.zeros((size, size, 4), dtype=np.uint8)
    frame[..., :3] = color
    frame[..., 3] = 255
    return frame


def test_stack_icon_frames_round_trip() -> None:
    """A synthetic 128x64 two-frame image with distinguishable solid-colour
    frames must restack into a 32x64 image whose TOP 32x32 is the downscaled
    LEFT (frame 0) source and whose BOTTOM 32x32 is the downscaled RIGHT
    (frame 1) source -- getting this backwards is the obvious silent bug
    (`pokemon_icon.c`'s `sMonIconAnims` walks tile 0 then tile 1 top-to-bottom
    over the INCGFX strip, so frame order must survive the restack)."""
    red = (200, 20, 20)
    blue = (20, 20, 200)
    icon = np.zeros((64, 128, 4), dtype=np.uint8)
    icon[:, :64] = _solid_frame(red)
    icon[:, 64:] = _solid_frame(blue)

    stacked = stack_icon_frames(icon)

    assert stacked.shape == (64, 32, 4)
    top, bottom = stacked[:32], stacked[32:]
    assert np.all(top[..., 3] == 255)
    assert np.all(bottom[..., 3] == 255)
    assert np.all(top[..., :3] == red)
    assert np.all(bottom[..., :3] == blue)


def test_stack_icon_frames_rejects_wrong_shape() -> None:
    with pytest.raises(ValueError):
        stack_icon_frames(np.zeros((64, 64, 4), dtype=np.uint8))


# --- palette loading -----------------------------------------------------------


def test_load_icon_palettes_shape() -> None:
    palettes = load_icon_palettes(ENGINE_ROOT)
    assert len(palettes) == ICON_PALETTE_COUNT
    for i, pal in enumerate(palettes):
        assert pal.index == i
        assert pal.colors.shape == (16, 3)
        assert pal.colors.dtype == np.uint8


def test_icon_palette_slot_zero_is_shared_background(
    icon_palettes: list[IconPalette],
) -> None:
    """Index 0 is the engine's fixed icon-box background colour and is
    IDENTICAL across all six shared palettes -- `remap_to_palette` depends on
    this to map transparent source pixels there unconditionally."""
    first = tuple(int(c) for c in icon_palettes[0].colors[0])
    for pal in icon_palettes[1:]:
        assert tuple(int(c) for c in pal.colors[0]) == first


# --- palette selection ----------------------------------------------------------


def test_choose_palette_prefers_exact_match() -> None:
    """A synthetic icon built entirely from one palette's own colours must
    choose that palette with ~zero error, and remapping must reproduce those
    colours exactly (a sanity check on the metric + remap before trusting it
    against real art)."""
    palettes = [
        IconPalette(index=0, colors=np.tile(np.array([10, 200, 10], np.uint8), (16, 1))),
        IconPalette(index=1, colors=np.tile(np.array([200, 10, 10], np.uint8), (16, 1))),
    ]
    stacked = np.zeros((64, 32, 4), dtype=np.uint8)
    stacked[..., :3] = [200, 10, 10]
    stacked[..., 3] = 255

    chosen, error = choose_palette(stacked, palettes)

    assert chosen == 1
    assert error == pytest.approx(0.0, abs=1e-6)

    indices = remap_to_palette(stacked, palettes[chosen])
    assert np.all(indices == 0)  # every colour in a flat-16 palette maps to slot 0


def test_remap_transparent_pixels_go_to_slot_zero() -> None:
    palette = IconPalette(
        index=0, colors=(np.arange(48) % 200).astype(np.uint8).reshape(16, 3)
    )
    stacked = np.zeros((64, 32, 4), dtype=np.uint8)  # fully transparent
    stacked[0, 0] = [200, 10, 10, 255]  # one opaque pixel so choose_palette wouldn't error

    indices = remap_to_palette(stacked, palette)

    assert indices[1, 1] == 0  # a transparent pixel elsewhere
    assert np.all(indices[stacked[..., 3] == 0] == 0)


# --- golden: pinned palette choice per starter ----------------------------------


@pytest.mark.parametrize("spec", STARTER_SPECIES, ids=lambda s: s.internal_name)
def test_golden_icon_palette_choice(
    spec, uranium_src: Path, icon_palettes: list[IconPalette]
) -> None:
    from rpg2gba.species_converter.icons import convert_species_icon

    result = convert_species_icon(uranium_src, spec, icon_palettes)
    assert result.icon_pal_index == EXPECTED_ICON_PAL_INDEX[spec.internal_name]


# --- structural / edge: emitted PNGs -------------------------------------------


def test_convert_starter_icons_emits_valid_indexed_pngs(
    uranium_src: Path, tmp_path: Path
) -> None:
    result = convert_starter_icons(uranium_src, ENGINE_ROOT, tmp_path)

    assert len(result.species) == len(STARTER_SPECIES)
    assert result.manifest_path == tmp_path / MANIFEST_NAME
    assert result.contact_sheet_path == tmp_path / CONTACT_SHEET_NAME
    assert result.manifest_path.exists()
    assert result.contact_sheet_path.exists()

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1

    for spec_result in result.species:
        name = spec_result.spec.internal_name
        icon_path = result.icon_paths[name]
        assert icon_path.exists()

        img = Image.open(icon_path)
        assert img.mode == "P"
        assert img.size == (ICON_WIDTH, ICON_HEIGHT)

        palette_entries = len(img.getpalette()) // 3
        pixels = np.asarray(img)
        assert pixels.shape == (ICON_HEIGHT, ICON_WIDTH)
        assert pixels.max() < palette_entries
        assert pixels.min() >= 0

        entry = manifest["species"][name]
        assert entry["icon_pal_index"] == spec_result.icon_pal_index
        assert entry["uranium_id"] == spec_result.spec.uranium_id
        assert entry["remap_error"] == pytest.approx(spec_result.remap_error)
        assert Path(entry["icon_png"]) == icon_path
