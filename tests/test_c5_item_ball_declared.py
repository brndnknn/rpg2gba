"""Tests for the `item_ball` template's C5 refactor (REDERIVATION_PLAN.md
§16.3 C5): every registered beat declares `assertions=` in the generic beat
floor's vocabulary, and the beat BODY actually checks what it declares.

Two kinds of coverage, same split as `tests/test_c5_flavour_npc_declared.py`:

- Registration-level (skipped without staged `output/uranium-build/`, same
  convention as `tests/test_playtest_archetype_templates.py`): the real
  CH04 Potion ball (map035/ev009) and the real CH02 Potion ball
  (map033/ev002), checking declared kinds and that
  `beat_floor.coverage.uncovered` is empty modulo the documented
  intentionally-undeclared set (`text`, and the full-bag branch arm).
  Also: a wrong `item=` fails loud at registration.
- Body-level, with a duck-typed fake emulator (no `mgba` import): proves the
  grant beat's body fails when the bag delta disagrees with the floor's
  declared `item_grant` quantity.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.beat_floor.coverage import uncovered
from rpg2gba.beat_floor.lookup import floor_for_row
from rpg2gba.playtest.archetypes.item_ball import item_ball_beats
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.playtest.errors import ScenarioError

_BUILD_OK = Path("output/uranium-build/porymap/map_constants.json").exists()
pytestmark_registration = pytest.mark.skipif(
    not _BUILD_OK,
    reason="requires staged pipeline output (output/uranium-build/) to "
           "resolve coordinates via playtest.cells and floors via beat_floor",
)


def _builder(name: str = "CHZZ_TEST") -> ChapterBuilder:
    return ChapterBuilder(name, doc="test-only, not a real chapter doc")


# -- registration-level: real instances --------------------------------------


@pytestmark_registration
def test_ch04_potion_ball_declares_grant_kinds_and_covers_the_page_row() -> None:
    """`map035/ev009` (CH04, MAP_ROUTE_02) is the real Potion ball. Its
    grant page's own floor is `trigger`/`completes`/`item_grant`; the
    self-switch write lives on the bag-has-room arm `p0/b0`, which the grant
    beat walks, so it claims that arm row and declares its floor too."""
    b = _builder()
    item_ball_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=9, item="ITEM_POTION", beat_prefix="IB1",
    )
    chapter = b.build()
    beat = chapter.beats[0]
    assert beat.rows == ("map035/ev009/p0", "map035/ev009/p0/b0")
    assert beat.archetype_of("map035/ev009/p0") == "item_ball"
    assert beat.archetype_of("map035/ev009/p0/b0") is None
    assert beat.assertions is not None
    kinds = {a.kind for a in beat.assertions}
    assert "self_switch_write" in kinds and "item_grant" in kinds
    for row_id in beat.rows:
        assert uncovered(floor_for_row(row_id), beat.assertions) == ()


@pytestmark_registration
def test_ch04_potion_ball_negative_beat_spent_page() -> None:
    b = _builder()
    item_ball_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=9, item="ITEM_POTION", beat_prefix="IB1", negative_beat=True,
    )
    chapter = b.build()
    grant, spent = chapter.beats
    assert spent.rows == ("map035/ev009/p1",)
    assert spent.assertions is not None
    # A truly empty spent page: touching it returns control with no script,
    # which the body checks, so it declares trigger/completes and covers the floor.
    assert {a.kind for a in spent.assertions} == {"trigger", "completes"}
    assert uncovered(floor_for_row("map035/ev009/p1"), spent.assertions) == ()


@pytestmark_registration
def test_ch02_potion_ball_ch01_ch03_instance_declares_and_covers() -> None:
    """A second, independent real instance outside CH04:
    `map033/ev002` (CH02, MAP_MOKI_TOWN -- per `reference/manifests/
    CH02.manifest.json`) is another plain two-page Potion ball, same shape
    as CH04's but a different map/event, proving the branch-arm derivation
    (never a hardcoded `bN`) generalizes."""
    b = _builder()
    item_ball_beats(
        b, chapter_id="CH02", map_constant="MAP_MOKI_TOWN", map_id=33,
        event_id=2, item="ITEM_POTION", beat_prefix="IB2", negative_beat=True,
    )
    chapter = b.build()
    grant, spent = chapter.beats
    assert grant.rows == ("map033/ev002/p0", "map033/ev002/p0/b0")
    for row_id in grant.rows:
        assert uncovered(floor_for_row(row_id), grant.assertions) == ()

    assert spent.rows == ("map033/ev002/p1",)
    assert uncovered(floor_for_row("map033/ev002/p1"), spent.assertions) == ()


@pytestmark_registration
def test_ch05_escape_rope_ball_empty_spent_page_covers_its_floor() -> None:
    """CH05's Escape Rope ball (map036/ev003) has a truly empty spent page
    (item_ball.py's own module docstring on `spent_page_is_empty`): the
    body checks control returns with no script, so the spent row's
    trigger/completes floor is covered."""
    b = _builder()
    item_ball_beats(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=3, item="ITEM_ESCAPE_ROPE", beat_prefix="IB3",
        negative_beat=True, approach_prefer="east",
    )
    chapter = b.build()
    grant, spent = chapter.beats
    assert spent.rows == ("map036/ev003/p1",)
    assert uncovered(floor_for_row("map036/ev003/p1"), spent.assertions) == ()


@pytestmark_registration
def test_non_empty_spent_page_declares_trigger_and_completes() -> None:
    """Every REAL corpus spent page happens to be the truly-empty shape
    (confirmed above); this proves the OTHER branch of `item_ball_beats`'s
    `spent_page_is_empty` logic -- a spent page that genuinely runs a
    script (some `other_codes` present) declares `trigger`/`completes`,
    the same positive-completion shape the grant beat gets. Synthesized by
    overriding CH05's Great Ball spent row's `other_codes` and stubbing
    `floor_lookup=` for that one row only; the grant page and its branch
    arm still resolve through the real floor."""
    from dataclasses import replace

    from rpg2gba.beat_floor.assertion import FloorAssertion
    from rpg2gba.playtest.archetypes import load_chapter_rows

    real_rows = load_chapter_rows("CH05")
    spent_row_id = "map036/ev005/p1"
    synthetic_rows = tuple(
        replace(r, other_codes=(999,)) if r.row_id == spent_row_id else r
        for r in real_rows
    )

    real_spent_floor = floor_for_row(spent_row_id)
    fake_spent_floor = replace(
        real_spent_floor,
        assertions=frozenset(
            a for a in real_spent_floor.assertions if a.kind in ("trigger", "completes")
        ) | frozenset({
            FloorAssertion(row_id=spent_row_id, kind="trigger", list_index=-1,
                            code=None, params=(("trigger", "action"),), tag="flow"),
            FloorAssertion(row_id=spent_row_id, kind="completes", list_index=-1,
                            code=None, params=(), tag="flow"),
        }),
    )

    def fake_lookup(row_id: str):
        if row_id == spent_row_id:
            return fake_spent_floor
        return floor_for_row(row_id)

    b = _builder()
    item_ball_beats(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=5, item="ITEM_GREAT_BALL", beat_prefix="IB4",
        negative_beat=True, approach_prefer="west",
        manifest_rows=synthetic_rows, floor_lookup=fake_lookup,
    )
    chapter = b.build()
    grant, spent = chapter.beats
    assert spent.assertions is not None
    assert {a.kind for a in spent.assertions} == {"trigger", "completes"}
    assert uncovered(fake_spent_floor, spent.assertions) == ()


@pytestmark_registration
def test_wrong_item_constant_fails_loud_at_registration() -> None:
    """The real Potion ball grants `ITEM_POTION`
    (`reference/uranium_id_map.json`'s `items["POTION"]`) -- a wrong stated
    `item=` must fail loud before any beat is registered, not compile
    through to a beat that checks the wrong bag slot."""
    b = _builder()
    with pytest.raises(ValueError, match="disagrees with the source"):
        item_ball_beats(
            b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
            event_id=9, item="ITEM_GREAT_BALL", beat_prefix="IB1",
        )


@pytestmark_registration
def test_item_with_no_uranium_id_map_entry_fails_loud() -> None:
    """A `floor_lookup=` fake substitutes a made-up internal item symbol
    with no entry in `reference/uranium_id_map.json` -- must fail loud
    rather than silently accept whatever `item=` the author typed."""
    from dataclasses import replace

    real_floor = floor_for_row("map035/ev009/p0")
    fake_assertion = next(a for a in real_floor.assertions if a.kind == "item_grant")
    fake_assertion = replace(
        fake_assertion,
        params=tuple(
            (k, "NOT_A_REAL_ITEM_SYMBOL") if k == "item" else (k, v)
            for k, v in fake_assertion.params
        ),
    )
    fake_floor = replace(
        real_floor,
        assertions=frozenset(
            (a if a.kind != "item_grant" else fake_assertion)
            for a in real_floor.assertions
        ),
    )

    def fake_lookup(row_id: str):
        if row_id == "map035/ev009/p0":
            return fake_floor
        return floor_for_row(row_id)

    b = _builder()
    with pytest.raises(ValueError, match="no entry in"):
        item_ball_beats(
            b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
            event_id=9, item="ITEM_POTION", beat_prefix="IB1",
            floor_lookup=fake_lookup,
        )


# -- body-level: fake emulator, no mgba import -------------------------------


class _FakeGrantEmu:
    """Minimal stand-in for what the grant beat body reads: `flag`,
    `bag_item_quantity`, `walk_to`, `face`, `interact`, `advance_dialog`,
    `screenshot`. `flag(ssa)` starts False and flips True the moment
    `interact()` runs (simulating the engine setting the self-switch as
    part of the script), mirroring the real precondition/postcondition
    shape the body checks around it. `bag_item_quantity` returns each of
    `bag_quantities` in order -- one call before the pickup, one after."""

    def __init__(self, bag_quantities: list[int]) -> None:
        self._bag_quantities = iter(bag_quantities)
        self._ssa_set = False
        self.screenshots: list[str] = []

    def flag(self, name: str) -> bool:
        return self._ssa_set

    def bag_item_quantity(self, item: str) -> int:
        return next(self._bag_quantities)

    def walk_to(self, x: int, y: int) -> None:
        pass

    def face(self, direction: str) -> None:
        pass

    def interact(self, require_script: bool = True) -> bool:
        self._ssa_set = True
        return True

    def advance_dialog(self) -> None:
        pass

    def screenshot(self, name: str) -> str:
        self.screenshots.append(name)
        return f"/tmp/{name}.png"


@pytestmark_registration
def test_grant_beat_body_passes_when_bag_delta_matches_declared_quantity() -> None:
    """The real Potion ball's floor quantity is 1 -- a +1 delta must pass."""
    b = _builder()
    item_ball_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=9, item="ITEM_POTION", beat_prefix="IB1",
    )
    beat = b.build().beats[0]
    emu = _FakeGrantEmu(bag_quantities=[0, 1])
    beat.run(emu)  # must not raise


@pytestmark_registration
def test_grant_beat_body_fails_loud_when_bag_delta_disagrees_with_quantity() -> None:
    """Same real instance, but the bag only goes up by 2 instead of the
    floor's declared quantity of 1 -- proves the body checks the FLOOR's
    own quantity, not a hardcoded `+1` (the pre-C5 shape)."""
    b = _builder()
    item_ball_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=9, item="ITEM_POTION", beat_prefix="IB1",
    )
    beat = b.build().beats[0]
    emu = _FakeGrantEmu(bag_quantities=[0, 2])
    with pytest.raises(ScenarioError, match="did not reach the bag"):
        beat.run(emu)
    assert emu.screenshots == ["IB1_bag_unchanged"]


@pytestmark_registration
def test_grant_beat_body_fails_loud_when_bag_does_not_move_at_all() -> None:
    b = _builder()
    item_ball_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=9, item="ITEM_POTION", beat_prefix="IB1",
    )
    beat = b.build().beats[0]
    emu = _FakeGrantEmu(bag_quantities=[3, 3])
    with pytest.raises(ScenarioError, match="did not reach the bag"):
        beat.run(emu)
