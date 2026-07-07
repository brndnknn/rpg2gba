"""Unit tests for sprite_emit.py -- ConvertedSprite list -> GBA object-event
engine artifacts (shared-palette quantization, indexed PNGs, 7 `.gen.h`
fragments). Fixtures build `ConvertedSprite`s directly (frames as plain numpy
arrays) rather than going through `convert_character_sheet`, per the task 4
wave-2 brief."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rpg2gba.tileset_converter.graphics.sprite_emit import (
    _GEN_RELPATHS,
    FIRST_GFX_ID,
    MAX_COLORS_PER_SHEET,
    MAX_PALETTES,
    _c_ident,
    emit_sprites,
    write_stub_gen_files,
)
from rpg2gba.tileset_converter.graphics.sprites import (
    GBA_FRAME_PX,
    NUM_BREAK_PROP_FRAMES,
    NUM_OUTPUT_FRAMES,
    NUM_PLAYER_OUTPUT_FRAMES,
    ConvertedPlayer,
    ConvertedSprite,
)
from rpg2gba.tileset_converter.npc_gfx import gfx_constant_for_sheet

PICS_RELDIR = Path("graphics/object_events/pics/uranium")


def _make_sprite(name: str, colors: list[tuple[int, int, int]]) -> ConvertedSprite:
    """A `ConvertedSprite` whose 9 (identical) frames each carry one opaque
    pixel per colour in `colors`, placed along frame row 0. Colours should be
    multiples of 8 so RGB555 snapping keeps them bucketed distinctly."""
    if len(colors) > GBA_FRAME_PX:
        raise ValueError("fixture helper: too many colours for one 32px row")
    frame = np.zeros((GBA_FRAME_PX, GBA_FRAME_PX, 4), dtype=np.uint8)
    for i, (r, g, b) in enumerate(colors):
        frame[0, i] = (r, g, b, 255)
    frames = [frame.copy() for _ in range(NUM_OUTPUT_FRAMES)]
    return ConvertedSprite(
        name=name, frames=frames, cycle="neutral02", asymmetry=0.0,
        content_size=(len(colors), 1),
    )


def _make_break_prop(name: str) -> ConvertedSprite:
    """A 4-frame break-prop sprite (fk107-rocksmash shape)."""
    frame = np.zeros((GBA_FRAME_PX, GBA_FRAME_PX, 4), dtype=np.uint8)
    frame[0, 0] = (80, 72, 64, 255)
    frames = [frame.copy() for _ in range(NUM_BREAK_PROP_FRAMES)]
    return ConvertedSprite(
        name=name, frames=frames, cycle="break_prop", asymmetry=0.0,
        content_size=(1, 1),
    )


def _family(name: str, family: int, n_colors: int = 15) -> ConvertedSprite:
    """`n_colors` distinct colours in a family identified by `family` (0..N);
    different families never share a colour (fixed R per family, varying B),
    so any two families forced to share a palette exceed the 15-colour cap."""
    colors = [(family * 50, 0, j * 8) for j in range(n_colors)]
    return _make_sprite(name, colors)


def _make_player(colors: list[tuple[int, int, int]] | None = None) -> ConvertedPlayer:
    """An 18-frame `ConvertedPlayer` (identical frames, one opaque pixel per
    colour along frame row 0) -- same fixture shape as `_make_sprite`, just 18
    frames instead of 9."""
    colors = colors if colors is not None else [(0, 0, 0)]
    if len(colors) > GBA_FRAME_PX:
        raise ValueError("fixture helper: too many colours for one 32px row")
    frame = np.zeros((GBA_FRAME_PX, GBA_FRAME_PX, 4), dtype=np.uint8)
    for i, (r, g, b) in enumerate(colors):
        frame[0, i] = (r, g, b, 255)
    frames = [frame.copy() for _ in range(NUM_PLAYER_OUTPUT_FRAMES)]
    return ConvertedPlayer(
        frames=frames, walk_cycle="neutral02", run_cycle="neutral02",
        content_size=(len(colors), 1),
    )


# --- naming / determinism vs npc_gfx ----------------------------------------


def test_gfx_constant_matches_npc_gfx_module(tmp_path: Path) -> None:
    sprite = _make_sprite("HGSS_000", [(0, 0, 0)])
    result = emit_sprites([sprite], tmp_path)
    assert result.gfx_constants["HGSS_000"] == gfx_constant_for_sheet("HGSS_000")
    assert result.gfx_constants["HGSS_000"] == "OBJ_EVENT_GFX_URANIUM_HGSS_000"
    assert result.gfx_ids["HGSS_000"] == FIRST_GFX_ID


# --- happy path --------------------------------------------------------------


def test_happy_path_shared_palette_two_sheets(tmp_path: Path) -> None:
    # Identical colour sets: the packer groups sheets by their exact colour-set
    # bitmask before any merging, so two sheets with the same set share a
    # palette unconditionally (unlike a mere subset, which only merges when
    # more groups than MAX_PALETTES force the greedy union-merge loop to run).
    s_z = _make_sprite("zzz", [(0, 0, 0), (8, 0, 0)])
    s_a = _make_sprite("aaa", [(0, 0, 0), (8, 0, 0)])
    result = emit_sprites([s_z, s_a], tmp_path)

    assert result.gfx_ids["aaa"] == FIRST_GFX_ID  # "AAA" sorts before "ZZZ"
    assert result.gfx_ids["zzz"] == FIRST_GFX_ID + 1
    assert len(result.palette_tags) == 1  # both fit in one shared palette
    assert result.palette_index["aaa"] == result.palette_index["zzz"]
    assert len(result.palettes) == 1
    assert len(result.palettes[0]) <= MAX_COLORS_PER_SHEET

    # 2 PNGs + 7 gen fragments
    assert len(result.files_written) == 2 + len(_GEN_RELPATHS)
    for path in result.files_written:
        assert path.is_file()

    for name in ("aaa", "zzz"):
        png_path = tmp_path / PICS_RELDIR / f"{result.stems[name]}.png"
        assert png_path in result.files_written
        img = Image.open(png_path)
        assert img.mode == "P"
        assert img.size == (GBA_FRAME_PX * NUM_OUTPUT_FRAMES, GBA_FRAME_PX)


def test_happy_path_three_sheets_two_families(tmp_path: Path) -> None:
    """Two sheets share a colour family (merge into one palette); a third,
    disjoint family gets its own -> exactly 2 shared palettes for 3 sheets."""
    s1 = _family("s1", family=0, n_colors=5)
    s2 = _family("s2", family=0, n_colors=5)  # same family as s1 -> shares
    s3 = _family("s3", family=1, n_colors=5)  # disjoint family
    result = emit_sprites([s1, s2, s3], tmp_path)

    assert len(result.palettes) == 2
    assert result.palette_index["s1"] == result.palette_index["s2"]
    assert result.palette_index["s3"] != result.palette_index["s1"]


def test_forced_merge_when_sheets_exceed_max_palettes(tmp_path: Path) -> None:
    """5 mutually-disjoint (but small, 3-colour) families with MAX_PALETTES=4
    forces exactly one merge in the packer's greedy loop -- whichever pair it
    picks stays well under the 15-colour cap, so this only asserts that
    sharing happened (one palette index used by 2 sheets), not which pair."""
    sprites = [_family(f"f{i}", family=i, n_colors=3) for i in range(5)]
    result = emit_sprites(sprites, tmp_path)
    assert len(result.palettes) == MAX_PALETTES

    counts = Counter(result.palette_index.values())
    assert sorted(counts.values()) == [1, 1, 1, 2]


# --- fail-loud budgets --------------------------------------------------------


def test_single_sheet_over_15_colors_is_reduced(tmp_path: Path) -> None:
    # A single 4bpp sprite carries one 16-colour palette (15 usable), so a sheet
    # with more colours is physically un-representable and MUST be median-cut
    # reduced (loudly) rather than rejected -- there is no lossless alternative
    # and no separate palette to spill into (real case: the Rivaltheo rival sheet,
    # 18 colours). This is distinct from the >MAX_PALETTES shared-palette overflow,
    # which still fails loud.
    too_many = [(i * 8, 0, 0) for i in range(20)]
    sprite = _make_sprite("overflow", too_many)
    result = emit_sprites([sprite], tmp_path)
    assert len(result.palettes) == 1
    assert len(result.palettes[0]) <= MAX_COLORS_PER_SHEET
    assert (tmp_path / PICS_RELDIR / "overflow.png").is_file()


def test_more_than_max_palettes_needed_packs_lossily(tmp_path: Path) -> None:
    # 5 mutually-disjoint 15-colour families: pigeonholing 5 sheets into
    # MAX_PALETTES(4) shared palettes forces >=2 sheets into one group whose
    # exact union is 30 colours. Real NPC art always overflows the 4 OBJ palette
    # banks (vanilla shares ~196 NPCs across 4), so the packer reduces lossily
    # rather than failing -- the ONLY fail-loud left is a packer-contract
    # violation (>4 palettes / a palette >15 colours).
    sprites = [_family(f"family_{i}", family=i, n_colors=MAX_COLORS_PER_SHEET) for i in range(5)]
    result = emit_sprites(sprites, tmp_path)
    assert len(result.palettes) <= MAX_PALETTES
    assert all(len(pal) <= MAX_COLORS_PER_SHEET for pal in result.palettes)


def test_exactly_max_palettes_of_disjoint_families_succeeds(tmp_path: Path) -> None:
    """The boundary case: exactly MAX_PALETTES disjoint families must fit."""
    sprites = [
        _family(f"family_{i}", family=i, n_colors=MAX_COLORS_PER_SHEET)
        for i in range(MAX_PALETTES)
    ]
    result = emit_sprites(sprites, tmp_path)
    assert len(result.palettes) == MAX_PALETTES


# --- other fail-loud guards ----------------------------------------------------


def test_empty_sprite_list_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        emit_sprites([], tmp_path)


def test_duplicate_sheet_name_raises(tmp_path: Path) -> None:
    s1 = _make_sprite("dup", [(0, 0, 0)])
    s2 = _make_sprite("dup", [(8, 0, 0)])
    with pytest.raises(ValueError, match="dup"):
        emit_sprites([s1, s2], tmp_path)


def test_constant_collision_raises(tmp_path: Path) -> None:
    # "foo bar" and "foo-bar" both normalize to OBJ_EVENT_GFX_URANIUM_FOO_BAR.
    s1 = _make_sprite("foo bar", [(0, 0, 0)])
    s2 = _make_sprite("foo-bar", [(8, 0, 0)])
    with pytest.raises(ValueError, match="FOO_BAR"):
        emit_sprites([s1, s2], tmp_path)


def test_wrong_frame_count_raises(tmp_path: Path) -> None:
    frame = np.zeros((GBA_FRAME_PX, GBA_FRAME_PX, 4), dtype=np.uint8)
    sprite = ConvertedSprite(
        name="short", frames=[frame.copy() for _ in range(5)],
        cycle="neutral02", asymmetry=0.0, content_size=(1, 1),
    )
    with pytest.raises(ValueError, match="short"):
        emit_sprites([sprite], tmp_path)


def test_wrong_frame_shape_raises(tmp_path: Path) -> None:
    bad_frame = np.zeros((16, 16, 4), dtype=np.uint8)
    frames = [bad_frame.copy() for _ in range(NUM_OUTPUT_FRAMES)]
    sprite = ConvertedSprite(
        name="badshape", frames=frames, cycle="neutral02", asymmetry=0.0,
        content_size=(1, 1),
    )
    with pytest.raises(ValueError, match="badshape"):
        emit_sprites([sprite], tmp_path)


# --- PNG readback --------------------------------------------------------------


def test_png_readback_indexed_and_palette_matches_assignment(tmp_path: Path) -> None:
    sprite = _make_sprite("aaa_sheet", [(0, 0, 0), (8, 0, 0), (16, 0, 0)])
    result = emit_sprites([sprite], tmp_path)

    png_path = tmp_path / PICS_RELDIR / f"{result.stems['aaa_sheet']}.png"
    img = Image.open(png_path)
    assert img.mode == "P"
    assert img.size == (GBA_FRAME_PX * NUM_OUTPUT_FRAMES, GBA_FRAME_PX)

    raw_pal = img.getpalette()
    assert raw_pal[0:3] == [0, 0, 0]  # index 0 reserved/transparent placeholder

    pal_idx = result.palette_index["aaa_sheet"]
    expected_colors = result.palettes[pal_idx]
    for slot, color in enumerate(expected_colors):
        got = tuple(raw_pal[(slot + 1) * 3: (slot + 1) * 3 + 3])
        assert got == color

    arr = np.array(img)
    assert arr.shape == (GBA_FRAME_PX, GBA_FRAME_PX * NUM_OUTPUT_FRAMES)
    # the 3 pixels drawn (frame 0, row 0, cols 0-2) are opaque -> nonzero index
    for i in range(3):
        assert arr[0, i] != 0
    # a pixel never drawn is transparent -> index 0
    assert arr[GBA_FRAME_PX - 1, GBA_FRAME_PX * NUM_OUTPUT_FRAMES - 1] == 0


# --- gen-file content: constants golden ----------------------------------------


def test_constants_file_golden(tmp_path: Path) -> None:
    s_z = _make_sprite("zzz", [(0, 0, 0)])
    s_a = _make_sprite("aaa", [(0, 0, 0)])  # identical colour -> 1 shared palette
    emit_sprites([s_z, s_a], tmp_path)

    text = (tmp_path / _GEN_RELPATHS["constants"]).read_text(encoding="utf-8")
    lines = text.splitlines()

    assert "#ifndef GUARD_URANIUM_EVENT_OBJECTS_GEN_H" in lines
    assert "#define GUARD_URANIUM_EVENT_OBJECTS_GEN_H" in lines
    assert "#endif // GUARD_URANIUM_EVENT_OBJECTS_GEN_H" in lines

    assert f"#define OBJ_EVENT_GFX_URANIUM_AAA {FIRST_GFX_ID}" in lines
    assert f"#define OBJ_EVENT_GFX_URANIUM_ZZZ {FIRST_GFX_ID + 1}" in lines
    idx_aaa = lines.index(f"#define OBJ_EVENT_GFX_URANIUM_AAA {FIRST_GFX_ID}")
    idx_zzz = lines.index(f"#define OBJ_EVENT_GFX_URANIUM_ZZZ {FIRST_GFX_ID + 1}")
    assert idx_aaa < idx_zzz  # sorted by constant name, not sheet-name/insertion order

    assert "#define NUM_URANIUM_OBJ_EVENT_GFX 2" in lines
    assert "#define OBJ_EVENT_PAL_TAG_URANIUM_0 0x1134" in lines
    assert "OBJ_EVENT_PAL_TAG_URANIUM_1" not in text  # only 1 palette was needed


# --- gen-file shapes -----------------------------------------------------------


def test_graphics_file_shape(tmp_path: Path) -> None:
    sprite = _make_sprite("foo", [(0, 0, 0), (8, 0, 0)])
    emit_sprites([sprite], tmp_path)
    text = (tmp_path / _GEN_RELPATHS["graphics"]).read_text(encoding="utf-8")

    assert "const u16 gUraniumObjEventPal_0[16] = {" in text
    # Slot 0 must be the transparent placeholder: the sheet PNGs index opaque
    # colours at 1..15, so the hardware palette carries them at the same
    # positions. Omitting it shifts every colour down one (live ROM bug,
    # 2026-07-06 boot gate).
    assert "gUraniumObjEventPal_0[16] = {0x0000, " in text
    ident = _c_ident("foo")
    assert f"gObjectEventPic_{ident}[]" in text
    assert (
        'INCGFX_U16("graphics/object_events/pics/uranium/foo.png", ".4bpp", '
        '"-mwidth 4 -mheight 4");' in text
    )


def test_break_prop_emits_rock_semantics(tmp_path: Path) -> None:
    """A break_prop sprite gets vanilla BreakableRock semantics: the finite
    sAnim_RockBreak table (Standard's ANIM_REMOVE_OBSTACLE slot is a LOOPING
    walk anim — rock_smash_break waited on it forever, debris never removed,
    boot gate 2026-07-06), inanimate, no tracks, and a 4-frame strip."""
    prop = _make_break_prop("fk107-rocksmash")
    emit_sprites([prop], tmp_path)
    info = (tmp_path / _GEN_RELPATHS["graphics_info"]).read_text(encoding="utf-8")
    assert ".anims = sAnimTable_BreakableRock," in info
    assert ".inanimate = TRUE," in info
    assert ".tracks = TRACKS_NONE," in info
    assert ".shadowSize = SHADOW_SIZE_S," in info
    png = Image.open(tmp_path / PICS_RELDIR / "fk107_rocksmash.png")
    assert png.size == (GBA_FRAME_PX * NUM_BREAK_PROP_FRAMES, GBA_FRAME_PX)


def test_break_prop_frame_count_validated(tmp_path: Path) -> None:
    prop = _make_break_prop("fk107-rocksmash")
    prop.frames.append(prop.frames[0].copy())  # 5 frames — invalid for a prop
    with pytest.raises(ValueError, match="expected 4 frames"):
        emit_sprites([prop], tmp_path)


def test_pic_tables_file_shape(tmp_path: Path) -> None:
    sprite = _make_sprite("foo", [(0, 0, 0)])
    emit_sprites([sprite], tmp_path)
    text = (tmp_path / _GEN_RELPATHS["pic_tables"]).read_text(encoding="utf-8")
    ident = _c_ident("foo")
    assert f"static const struct SpriteFrameImage sPicTable_{ident}[] = {{" in text
    assert f"overworld_ascending_frames(gObjectEventPic_{ident}, 4, 4)," in text


def test_graphics_info_file_shape(tmp_path: Path) -> None:
    sprite = _make_sprite("foo", [(0, 0, 0)])
    result = emit_sprites([sprite], tmp_path)
    text = (tmp_path / _GEN_RELPATHS["graphics_info"]).read_text(encoding="utf-8")
    ident = _c_ident("foo")

    assert f"const struct ObjectEventGraphicsInfo gObjectEventGraphicsInfo_{ident} = {{" in text
    assert ".tileTag = TAG_NONE," in text
    tag = result.palette_tags[result.palette_index["foo"]]
    assert f".paletteTag = {tag}," in text
    assert ".reflectionPaletteTag = OBJ_EVENT_PAL_TAG_NONE," in text
    assert f".size = {GBA_FRAME_PX * GBA_FRAME_PX // 2}," in text
    assert f".width = {GBA_FRAME_PX}," in text
    assert f".height = {GBA_FRAME_PX}," in text
    assert ".paletteSlot = PALSLOT_NPC_SPECIAL," in text
    assert ".shadowSize = SHADOW_SIZE_M," in text
    assert ".inanimate = FALSE," in text
    assert ".compressed = FALSE," in text
    assert ".tracks = TRACKS_FOOT," in text
    assert ".oam = &gObjectEventBaseOam_32x32," in text
    assert ".subspriteTables = sOamTables_32x32," in text
    assert ".anims = sAnimTable_Standard," in text
    assert f".images = sPicTable_{ident}," in text
    assert ".affineAnims = gDummySpriteAffineAnimTable," in text


def test_decls_are_above_pointer_style_and_pointers_are_designated(tmp_path: Path) -> None:
    s1 = _make_sprite("foo", [(0, 0, 0), (8, 0, 0)])
    s2 = _make_sprite("bar", [(100, 0, 0)])
    result = emit_sprites([s1, s2], tmp_path)

    decls_text = (tmp_path / _GEN_RELPATHS["graphics_info_decls"]).read_text(encoding="utf-8")
    for name in ("foo", "bar"):
        ident = _c_ident(name)
        assert (
            f"extern const struct ObjectEventGraphicsInfo gObjectEventGraphicsInfo_{ident};"
            in decls_text
        )

    pointers_text = (tmp_path / _GEN_RELPATHS["graphics_info_pointers"]).read_text(
        encoding="utf-8"
    )
    for name in ("foo", "bar"):
        ident = _c_ident(name)
        gfx_name = result.gfx_constants[name]
        assert f"[{gfx_name}] = &gObjectEventGraphicsInfo_{ident}," in pointers_text


def test_palette_registration_file_only_contains_entries(tmp_path: Path) -> None:
    s1 = _family("s1", family=0, n_colors=5)
    s2 = _family("s2", family=1, n_colors=5)
    result = emit_sprites([s1, s2], tmp_path)

    text = (tmp_path / _GEN_RELPATHS["palettes"]).read_text(encoding="utf-8")
    for i, tag in enumerate(result.palette_tags):
        assert f"{{gUraniumObjEventPal_{i}, {tag}}}," in text

    # every non-comment, non-blank line is exactly one registration entry
    for line in text.splitlines():
        if not line.strip() or line.startswith("//"):
            continue
        assert line.startswith("{") and line.endswith("},"), f"stray content: {line!r}"


# --- player emission -----------------------------------------------------------


def test_player_strip_png_shape_and_transparent_slot(tmp_path: Path) -> None:
    player = _make_player([(0, 0, 0), (8, 0, 0), (16, 0, 0)])
    result = emit_sprites([], tmp_path, player=player)

    png_path = tmp_path / PICS_RELDIR / "hero.png"
    assert png_path in result.files_written
    img = Image.open(png_path)
    assert img.mode == "P"
    assert img.size == (GBA_FRAME_PX * NUM_PLAYER_OUTPUT_FRAMES, GBA_FRAME_PX)

    raw_pal = img.getpalette()
    assert raw_pal[0:3] == [0, 0, 0]  # index 0 reserved/transparent placeholder


def test_player_dedicated_palette_tag_and_value(tmp_path: Path) -> None:
    player = _make_player([(0, 0, 0)])
    result = emit_sprites([], tmp_path, player=player)

    assert result.player_palette_tag == "OBJ_EVENT_PAL_TAG_URANIUM_PLAYER"
    assert result.player_palette == [(0, 0, 0)]

    constants_text = (tmp_path / _GEN_RELPATHS["constants"]).read_text(encoding="utf-8")
    # next value after the (up-to-MAX_PALETTES) reserved NPC tag block, i.e.
    # 0x1134 (the NPC block's base) + MAX_PALETTES.
    assert "#define OBJ_EVENT_PAL_TAG_URANIUM_PLAYER 0x1138" in constants_text


def test_player_does_not_get_a_gfx_id_or_pointer_entry(tmp_path: Path) -> None:
    sprite = _make_sprite("aaa", [(0, 0, 0)])
    player = _make_player([(8, 0, 0)])
    result = emit_sprites([sprite], tmp_path, player=player)

    assert "player" not in {k.lower() for k in result.gfx_constants}
    assert not any("PLAYER" in c for c in result.gfx_constants.values())

    pointers_text = (tmp_path / _GEN_RELPATHS["graphics_info_pointers"]).read_text(
        encoding="utf-8"
    )
    assert "UraniumPlayerNormal" not in pointers_text

    constants_text = (tmp_path / _GEN_RELPATHS["constants"]).read_text(encoding="utf-8")
    assert "OBJ_EVENT_GFX_URANIUM_PLAYER" not in constants_text
    # NPC gfx count is unaffected by the player being present.
    assert "#define NUM_URANIUM_OBJ_EVENT_GFX 1" in constants_text


def test_player_graphics_info_struct_shape(tmp_path: Path) -> None:
    player = _make_player([(0, 0, 0)])
    emit_sprites([], tmp_path, player=player)

    text = (tmp_path / _GEN_RELPATHS["graphics_info"]).read_text(encoding="utf-8")
    assert (
        "const struct ObjectEventGraphicsInfo gObjectEventGraphicsInfo_UraniumPlayerNormal = {"
        in text
    )
    assert ".paletteTag = OBJ_EVENT_PAL_TAG_URANIUM_PLAYER," in text
    assert ".paletteSlot = PALSLOT_PLAYER," in text
    assert ".anims = sAnimTable_BrendanMayNormal," in text
    assert ".tracks = TRACKS_FOOT," in text
    assert ".shadowSize = SHADOW_SIZE_M," in text
    assert ".inanimate = FALSE," in text
    assert ".reflectionPaletteTag = OBJ_EVENT_PAL_TAG_NONE," in text
    assert ".width = 32," in text
    assert ".height = 32," in text
    assert ".oam = &gObjectEventBaseOam_32x32," in text
    assert ".subspriteTables = sOamTables_32x32," in text
    assert ".images = sPicTable_UraniumPlayerNormal," in text


def test_player_pic_table_and_incgfx_line(tmp_path: Path) -> None:
    player = _make_player([(0, 0, 0)])
    emit_sprites([], tmp_path, player=player)

    graphics_text = (tmp_path / _GEN_RELPATHS["graphics"]).read_text(encoding="utf-8")
    assert "const u16 gUraniumObjEventPal_Player[16] = {0x0000, " in graphics_text
    assert "const u16 gObjectEventPic_UraniumPlayerNormal[]" in graphics_text
    assert (
        'INCGFX_U16("graphics/object_events/pics/uranium/hero.png", ".4bpp", '
        '"-mwidth 4 -mheight 4");' in graphics_text
    )

    pic_tables_text = (tmp_path / _GEN_RELPATHS["pic_tables"]).read_text(encoding="utf-8")
    assert (
        "static const struct SpriteFrameImage sPicTable_UraniumPlayerNormal[] = {"
        in pic_tables_text
    )
    assert (
        "overworld_ascending_frames(gObjectEventPic_UraniumPlayerNormal, 4, 4),"
        in pic_tables_text
    )


def test_player_extern_decl_in_decls_file(tmp_path: Path) -> None:
    player = _make_player([(0, 0, 0)])
    emit_sprites([], tmp_path, player=player)

    text = (tmp_path / _GEN_RELPATHS["graphics_info_decls"]).read_text(encoding="utf-8")
    assert (
        "extern const struct ObjectEventGraphicsInfo gObjectEventGraphicsInfo_UraniumPlayerNormal;"
        in text
    )
    # The real decls output never also emits the stub's #define fallback.
    assert "#define gObjectEventGraphicsInfo_UraniumPlayerNormal" not in text


def test_player_palette_registration_entry(tmp_path: Path) -> None:
    player = _make_player([(0, 0, 0)])
    emit_sprites([], tmp_path, player=player)

    text = (tmp_path / _GEN_RELPATHS["palettes"]).read_text(encoding="utf-8")
    assert "{gUraniumObjEventPal_Player, OBJ_EVENT_PAL_TAG_URANIUM_PLAYER}," in text


def test_player_joint_palette_reduced_when_over_budget(tmp_path: Path) -> None:
    """36 distinct colours across the 18 player frames (2 per frame, all
    mutually distinct) forces the dedicated palette's forced `max_palettes=1`
    quantization to median-cut reduce -- exercises the same reduction path as
    the NPC `_reduce_sprite_to_budget`, but applied jointly across all 18
    frames via `_quantize_player`."""
    frame_w = GBA_FRAME_PX
    frames = []
    color = 0
    for _ in range(NUM_PLAYER_OUTPUT_FRAMES):
        frame = np.zeros((GBA_FRAME_PX, frame_w, 4), dtype=np.uint8)
        frame[0, 0] = (color % 256, 0, 0, 255)
        frame[0, 1] = ((color + 8) % 256, 40, 0, 255)
        color += 16
        frames.append(frame)
    player = ConvertedPlayer(
        frames=frames, walk_cycle="neutral02", run_cycle="neutral02", content_size=(2, 1)
    )
    result = emit_sprites([], tmp_path, player=player)
    assert len(result.player_palette) <= MAX_COLORS_PER_SHEET


def test_player_alone_without_any_npc_sprites_succeeds(tmp_path: Path) -> None:
    """`emit_sprites` no longer requires at least one NPC sprite when a player
    is given (backward-compatible: omitting `player` preserves the old
    at-least-one-sprite requirement, see `test_empty_sprite_list_raises`)."""
    player = _make_player([(0, 0, 0)])
    result = emit_sprites([], tmp_path, player=player)
    assert result.gfx_constants == {}
    assert result.player_palette_tag is not None


def test_player_wrong_frame_count_raises(tmp_path: Path) -> None:
    player = _make_player([(0, 0, 0)])
    player.frames = player.frames[:9]  # only the walk half
    with pytest.raises(ValueError, match="18"):
        emit_sprites([], tmp_path, player=player)


def test_player_wrong_frame_shape_raises(tmp_path: Path) -> None:
    player = _make_player([(0, 0, 0)])
    player.frames[5] = np.zeros((16, 16, 4), dtype=np.uint8)
    with pytest.raises(ValueError, match="frame 5"):
        emit_sprites([], tmp_path, player=player)


def test_emit_sprites_with_both_npc_sprites_and_player(tmp_path: Path) -> None:
    """The primary real-world call shape: NPC sheets and the player emitted
    together into the same 7 gen files."""
    s1 = _make_sprite("aaa", [(0, 0, 0)])
    s2 = _make_sprite("bbb", [(8, 0, 0)])
    player = _make_player([(16, 0, 0)])
    result = emit_sprites([s1, s2], tmp_path, player=player)

    assert set(result.gfx_constants) == {"aaa", "bbb"}
    assert result.player_palette_tag == "OBJ_EVENT_PAL_TAG_URANIUM_PLAYER"
    # 2 NPC PNGs + 1 player PNG + 7 gen fragments
    assert len(result.files_written) == 2 + 1 + len(_GEN_RELPATHS)
    for path in result.files_written:
        assert path.is_file()


def test_player_determinism_byte_identical_across_runs(tmp_path: Path) -> None:
    player = _make_player([(0, 0, 0), (8, 0, 0)])
    sprite = _make_sprite("aaa", [(16, 0, 0)])
    out1, out2 = tmp_path / "run1", tmp_path / "run2"
    emit_sprites([sprite], out1, player=player)
    emit_sprites([sprite], out2, player=player)

    for relpath in _GEN_RELPATHS.values():
        assert (out1 / relpath).read_bytes() == (out2 / relpath).read_bytes(), relpath
    assert (out1 / PICS_RELDIR / "hero.png").read_bytes() == (
        out2 / PICS_RELDIR / "hero.png"
    ).read_bytes()


# --- determinism ---------------------------------------------------------------


def test_determinism_byte_identical_across_runs(tmp_path: Path) -> None:
    sprites = [
        _make_sprite("foo", [(0, 0, 0), (8, 0, 0)]),
        _make_sprite("bar", [(100, 0, 0)]),
    ]
    out1, out2 = tmp_path / "run1", tmp_path / "run2"
    emit_sprites(sprites, out1)
    emit_sprites(sprites, out2)

    for relpath in _GEN_RELPATHS.values():
        assert (out1 / relpath).read_bytes() == (out2 / relpath).read_bytes(), relpath

    pics1 = sorted((out1 / PICS_RELDIR).iterdir())
    pics2 = sorted((out2 / PICS_RELDIR).iterdir())
    assert [p.name for p in pics1] == [p.name for p in pics2]
    for p1, p2 in zip(pics1, pics2, strict=True):
        assert p1.read_bytes() == p2.read_bytes()


# --- stub writer -----------------------------------------------------------------


def test_write_stub_gen_files_is_idempotent_and_minimal(tmp_path: Path) -> None:
    def _read_all() -> dict[Path, str]:
        return {
            relpath: (tmp_path / relpath).read_text(encoding="utf-8")
            for relpath in _GEN_RELPATHS.values()
        }

    write_stub_gen_files(tmp_path)
    first = _read_all()
    write_stub_gen_files(tmp_path)
    second = _read_all()
    assert first == second

    constants_text = (tmp_path / _GEN_RELPATHS["constants"]).read_text(encoding="utf-8")
    assert "#define NUM_URANIUM_OBJ_EVENT_GFX 0" in constants_text
    assert "OBJ_EVENT_GFX_URANIUM_" not in constants_text
    assert "OBJ_EVENT_PAL_TAG_URANIUM_" not in constants_text


def test_stub_writer_pins_literal_content(tmp_path: Path) -> None:
    """Pin `write_stub_gen_files`'s exact output shape against literal strings
    rather than comparing to the on-disk `engine/*.gen.h` files: those now hold
    real emitted content from staged sprites (NPC + player), so a disk
    comparison only ever passed on a fresh clone with nothing staged. The
    INTENT this test still covers — a fresh clone / no-sprites-staged build
    compiles against exactly this shape — is unchanged; only the oracle moved
    from "whatever's on disk right now" to a fixed expectation."""
    write_stub_gen_files(tmp_path)

    stub_header = (
        "// GENERATED by rpg2gba (stub) — do not edit; the sprite emitter overwrites "
        "this file.\n"
    )

    constants = (tmp_path / _GEN_RELPATHS["constants"]).read_text(encoding="utf-8")
    assert constants == (
        stub_header
        + "#ifndef GUARD_URANIUM_EVENT_OBJECTS_GEN_H\n"
        + "#define GUARD_URANIUM_EVENT_OBJECTS_GEN_H\n"
        + "\n"
        + "#define NUM_URANIUM_OBJ_EVENT_GFX 0\n"
        + "\n"
        + "#endif // GUARD_URANIUM_EVENT_OBJECTS_GEN_H\n"
    )

    graphics = (tmp_path / _GEN_RELPATHS["graphics"]).read_text(encoding="utf-8")
    assert graphics == stub_header

    pic_tables = (tmp_path / _GEN_RELPATHS["pic_tables"]).read_text(encoding="utf-8")
    assert pic_tables == stub_header

    graphics_info = (tmp_path / _GEN_RELPATHS["graphics_info"]).read_text(encoding="utf-8")
    assert graphics_info == stub_header

    # The decls stub carries ONE extra line the other empty stubs don't: the
    # tracked pointers file (owned by the lead session, outside this module)
    # references gObjectEventGraphicsInfo_UraniumPlayerNormal unconditionally,
    # so a fresh clone needs a name for it to resolve to even with zero sprites
    # staged -- aliased to the vanilla Brendan struct.
    graphics_info_decls = (tmp_path / _GEN_RELPATHS["graphics_info_decls"]).read_text(
        encoding="utf-8"
    )
    assert graphics_info_decls == (
        stub_header
        + "#define gObjectEventGraphicsInfo_UraniumPlayerNormal "
        + "gObjectEventGraphicsInfo_BrendanNormal\n"
    )

    graphics_info_pointers = (tmp_path / _GEN_RELPATHS["graphics_info_pointers"]).read_text(
        encoding="utf-8"
    )
    assert graphics_info_pointers == (
        stub_header
        + "// Included INSIDE gObjectEventGraphicsInfoPointers[] — entries only, no declarations.\n"
    )

    palettes = (tmp_path / _GEN_RELPATHS["palettes"]).read_text(encoding="utf-8")
    assert palettes == (
        stub_header
        + "// Included INSIDE sObjectEventSpritePalettes[] BEFORE the OBJ_EVENT_PAL_TAG_NONE "
        + "terminator — entries only.\n"
    )
