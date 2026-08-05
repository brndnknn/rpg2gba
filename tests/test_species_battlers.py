"""Tests for `rpg2gba.species_converter.battlers` (W2, the battler art
converter).

Per CLAUDE.md §4.6: a golden test pinning emitted-file content hashes for one
species (ORCHYNX -- the vertical prototype built first per
STARTER_SPECIES_PLAN.md §4/§5), an edge test for the uppercase `.PNG`
filename resolution (METALYNX's `002b.PNG`), an edge test that the
shiny-geometry-divergence check fails loud on a synthetic mismatched pair,
and a structural pass over all six starters asserting PNG size, palette
colour budget, and normal/shiny index-compatibility.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rpg2gba.species_converter import battlers
from rpg2gba.species_converter.common import (
    BATTLER_MAX_COLORS,
    BATTLER_SIZE,
    STARTER_SPECIES,
)

# --- 1. Golden test: pinned content hashes for ORCHYNX ----------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.phase2
def test_orchynx_golden_output(tmp_path: Path, uranium_data: Path) -> None:
    """Pin the emitted PNG/pal bytes for ORCHYNX (the W2 vertical prototype,
    per STARTER_SPECIES_PLAN.md §5) so a regression in extraction, fitting,
    or quantization shows up as a content-hash diff rather than silently
    changing the art."""
    uranium_src = uranium_data.parent  # uranium_data fixture points at .../Data
    spec = STARTER_SPECIES[0]
    assert spec.internal_name == "ORCHYNX"

    result = battlers.convert_species_battler(uranium_src, spec, tmp_path)

    assert _sha256(result.front_path) == (
        "4cf8f214202c5219ce7f1b263334bae795a518213a84ca96c69fcd522bce64d3"
    )
    assert _sha256(result.back_path) == (
        "c896be47d783a7439c0be858ac9c32b3c1947b43d9de57f46a6a4ba4d0b19e03"
    )
    assert _sha256(result.normal_pal_path) == (
        "2014ab36b02dd7bf7cea322518cc5258ba13a1686fb4da16d0e361520237c8c4"
    )
    assert _sha256(result.shiny_pal_path) == (
        "9587baf84b8cd71ba53fcb1ebb59a7e89434b364f2e8779f5934476fbfa9a695"
    )
    assert result.opaque_color_count == 11
    assert result.front_y_offset == 9
    assert result.back_y_offset == 9
    assert result.front_shiny_divergence == 0.0
    assert result.back_shiny_divergence == 0.0


# --- 2. Edge test: uppercase .PNG resolution --------------------------------


@pytest.mark.phase2
def test_metalynx_uppercase_png_resolves(tmp_path: Path, uranium_data: Path) -> None:
    """METALYNX (species 002) ships `002b.PNG` uppercase; the source path
    helpers only ever produce the lowercase spelling, so this exercises
    `common.resolve_case`'s case-insensitive fallback for real. Also the
    species whose front (80 frames) vs shiny front (77 frames) mismatch is
    the plan's flagged risk -- confirms it still converts (own-last-frame
    extraction keeps the poses corresponding; see module docstring)."""
    uranium_src = uranium_data.parent
    spec = STARTER_SPECIES[1]
    assert spec.internal_name == "METALYNX"

    result = battlers.convert_species_battler(uranium_src, spec, tmp_path)

    assert result.front_path.is_file()
    assert result.back_path.is_file()
    # Real, small, but nonzero divergence -- own-last-frame extraction still
    # correlates despite the differing frame counts (not a coincidence: see
    # SHINY_GEOMETRY_MAX_DIVERGENCE's docstring for the measured numbers).
    assert 0.0 < result.front_shiny_divergence < battlers.SHINY_GEOMETRY_MAX_DIVERGENCE


# --- 3. Edge test: shiny-geometry divergence fails loud ---------------------


def _solid_square(size: int, box: tuple[int, int, int, int]) -> np.ndarray:
    """An RGBA array with an opaque solid-colour square at `box` = (x0, y0,
    w, h) and transparent elsewhere."""
    arr = np.zeros((size, size, 4), dtype=np.uint8)
    x0, y0, w, h = box
    arr[y0 : y0 + h, x0 : x0 + w] = (200, 100, 50, 255)
    return arr


def test_shiny_geometry_mismatch_fails_loud() -> None:
    """A synthetic pair whose opaque silhouettes barely overlap must raise,
    not silently produce a wrong shiny palette (CLAUDE.md §4.5)."""
    normal = _solid_square(80, box=(10, 10, 20, 20))
    shiny = _solid_square(80, box=(50, 50, 20, 20))  # disjoint square

    with pytest.raises(ValueError, match="diverges"):
        battlers._check_shiny_geometry(normal, shiny, "SYNTHETIC")


def test_shiny_geometry_near_identical_passes() -> None:
    """Sanity check for the positive case: near-identical silhouettes (a
    handful of edge pixels different) stay under threshold."""
    normal = _solid_square(80, box=(10, 10, 20, 20))
    shiny = _solid_square(80, box=(10, 10, 20, 20))
    # Nudge one row of pixels off to simulate antialiasing-level noise.
    shiny[10, 10:12] = 0

    divergence = battlers._check_shiny_geometry(normal, shiny, "SYNTHETIC")
    assert 0.0 < divergence < battlers.SHINY_GEOMETRY_MAX_DIVERGENCE


# --- 3b. Edge tests: shiny registration (rigid-translation correction) ------


def test_register_shiny_aligns_rigid_translation() -> None:
    """A synthetic pair whose shiny is a known rigid (+3, -2) px translation
    of the normal (same shape, same silhouette, just shifted -- the OWTEN
    035/035s case) must register and report zero residual divergence, not
    fail loud."""
    normal = _solid_square(80, box=(20, 20, 20, 20))
    shiny = _solid_square(80, box=(23, 18, 20, 20))  # normal shifted by (+3, -2)

    aligned, divergence, offset = battlers._register_shiny(normal, shiny, "SYNTHETIC")

    assert offset == (3, -2)
    assert divergence == pytest.approx(0.0)
    assert np.array_equal(battlers._opaque_mask(aligned), battlers._opaque_mask(normal))


def test_register_shiny_identity_is_untouched_fast_path() -> None:
    """An already-registered pair must come back as the SAME array object,
    at offset (0, 0), with no search performed -- the fast path this
    function must not regress for the six starters (see
    `test_orchynx_golden_output`'s pinned hashes, unchanged by this
    function's addition)."""
    normal = _solid_square(80, box=(10, 10, 20, 20))
    shiny = _solid_square(80, box=(10, 10, 20, 20))

    aligned, divergence, offset = battlers._register_shiny(normal, shiny, "SYNTHETIC")

    assert aligned is shiny
    assert offset == (0, 0)
    assert divergence == 0.0


def test_register_shiny_genuinely_different_still_fails_loud() -> None:
    """A synthetic pair that is NOT a registration-fixable shift -- e.g. a
    totally different silhouette -- must still raise, even though a
    translation search runs first. The error must report the best offset
    found and its residual divergence so a real mismatch is distinguishable
    from an out-of-range shift."""
    normal = _solid_square(80, box=(10, 10, 20, 20))
    shiny = _solid_square(80, box=(50, 50, 8, 30))  # disjoint, different shape

    with pytest.raises(ValueError, match=r"[Bb]est integer translation"):
        battlers._register_shiny(normal, shiny, "SYNTHETIC")


# --- 4. Structural assertions over all six starters -------------------------


@pytest.mark.phase2
def test_all_starters_convert_with_valid_structure(tmp_path: Path, uranium_data: Path) -> None:
    """Every starter's emitted PNGs are exactly 64x64, palettes have at most
    BATTLER_MAX_COLORS opaque colours, and normal/shiny palettes are
    index-compatible (same length -- required for the engine's palette-swap
    shiny rendering to be well-defined)."""
    uranium_src = uranium_data.parent
    results = battlers.convert_starter_battlers(uranium_src, tmp_path, species=STARTER_SPECIES)

    assert len(results) == len(STARTER_SPECIES)
    sidecar_path = tmp_path / battlers.SIDECAR_NAME
    assert sidecar_path.is_file()

    for result in results:
        with Image.open(result.front_path) as img:
            assert img.size == (BATTLER_SIZE, BATTLER_SIZE)
            assert img.mode == "P"
        with Image.open(result.back_path) as img:
            assert img.size == (BATTLER_SIZE, BATTLER_SIZE)
            assert img.mode == "P"

        assert 0 < result.opaque_color_count <= BATTLER_MAX_COLORS

        normal_pal = battlers._read_pal(result.normal_pal_path, result.opaque_color_count)
        shiny_pal = battlers._read_pal(result.shiny_pal_path, result.opaque_color_count)
        assert normal_pal.shape == shiny_pal.shape == (result.opaque_color_count, 3)

        assert result.front_shiny_divergence <= battlers.SHINY_GEOMETRY_MAX_DIVERGENCE
        assert result.back_shiny_divergence <= battlers.SHINY_GEOMETRY_MAX_DIVERGENCE
        assert 0 <= result.front_y_offset < BATTLER_SIZE
        assert 0 <= result.back_y_offset < BATTLER_SIZE


@pytest.mark.phase2
def test_contact_sheet_builds(tmp_path: Path, uranium_data: Path) -> None:
    """The eye-gate contact sheet renders without error and produces a
    nonempty PNG covering all six species x 2 variants x front/back."""
    uranium_src = uranium_data.parent
    results = battlers.convert_starter_battlers(uranium_src, tmp_path, species=STARTER_SPECIES)

    sheet_path = battlers.build_contact_sheet(results, tmp_path / "contact_sheet.png")

    assert sheet_path.is_file()
    with Image.open(sheet_path) as img:
        assert img.width > BATTLER_SIZE * 2
        assert img.height >= BATTLER_SIZE * battlers.CONTACT_SHEET_SCALE * len(results) * 2
