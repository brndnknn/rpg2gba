"""Tests for the `trainer` archetype's C5 declared assertions
(REDERIVATION_PLAN.md §16.3 C5, `src/rpg2gba/playtest/archetypes/trainer.py`).

Fixtures (a) use the real, staged CH04 build output and the committed
CH02/CH04 manifests -- skipped if that output isn't present, matching
`test_playtest_archetype_templates.py`'s own convention. Fixture (c) is
purely structural (a fake emulator, no mgba), mirroring
`test_playtest_assertions.py`'s `_FakeEmu` convention, and exercises
`trainer._register_retalk_beat` directly with a hand-built floor so it does
not depend on any staged output at all.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.beat_floor.assertion import FloorAssertion, FloorRefusal, RowFloor, make_params
from rpg2gba.beat_floor.coverage import uncovered
from rpg2gba.beat_floor.lookup import floor_for_row
from rpg2gba.playtest.archetypes.trainer import (
    _intro_text_assertions,
    _register_retalk_beat,
    trainer_beats,
)
from rpg2gba.playtest.chapter import ChapterBuilder
from rpg2gba.playtest.errors import ScenarioError

pytestmark = pytest.mark.skipif(
    not Path("output/uranium-build/porymap/map_constants.json").exists(),
    reason="requires staged pipeline output (output/uranium-build/) to "
           "resolve coordinates via playtest.cells",
)

_BUILD_DIR = Path("output/uranium-build")


def _builder(name: str = "CHZZ_TEST") -> ChapterBuilder:
    return ChapterBuilder(name, doc="test-only, not a real chapter doc")


# -- (a) declared kinds + uncovered() on real fixtures ------------------------


def test_ch04_timothy_declared_kinds_and_uncovered() -> None:
    """map035 event 12 (Timothy, CH04): a native `trainerbattle_single`
    instance -- `defeat_flag` is the native TRAINER_FLAGS bit, which IS the
    win arm's self-switch-A write on the ROM, so the battle beat claims that
    arm and declares its `self_switch_write` (module docstring point 2,
    2026-09-30 ruling). The battle beat reads the pre-battle intro box, so
    `text` is declared (point 3, 2026-09-24); `audio`/`visual` stay
    undeclared -- walk-checked, not graded (C9 ruling 7)."""
    b = _builder()
    trainer_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=12, trainer_const="TRAINER_TIMOTHY_247",
        defeat_flag="TRAINER_FLAGS_START + TRAINER_TIMOTHY_247",
        beat_prefix="T1", trigger="event_touch", phone=False, double=False,
        retalk_pages=1, rider=False,
    )
    chapter = b.build()
    battle, retalk = chapter.beats

    assert battle.rows == ("map035/ev012/p0", "map035/ev012/p0/b0")
    battle_kinds = {a.kind for a in battle.assertions}
    assert battle_kinds == {"trigger", "completes", "battle", "text", "self_switch_write"}

    battle_floor = floor_for_row("map035/ev012/p0", build_dir=_BUILD_DIR)
    battle_uncovered = {a.kind for a in uncovered(battle_floor, battle.assertions)}
    assert battle_uncovered == {"audio", "visual"}
    win_floor = floor_for_row("map035/ev012/p0/b0", build_dir=_BUILD_DIR)
    assert not uncovered(win_floor, battle.assertions)

    assert retalk.rows == ("map035/ev012/p1",)
    retalk_kinds = {a.kind for a in retalk.assertions}
    assert retalk_kinds == {"trigger", "completes", "text"}

    retalk_floor = floor_for_row("map035/ev012/p1", build_dir=_BUILD_DIR)
    retalk_uncovered = {a.kind for a in uncovered(retalk_floor, retalk.assertions)}
    assert retalk_uncovered == {"visual"}


def test_ch02_marko_declared_kinds_and_uncovered() -> None:
    """map033 event 9 (Marko, CH02): same native-idiom shape as Timothy, a
    different chapter's manifest -- the CH01-CH03 instance with a retalk
    the task asks for."""
    b = _builder()
    trainer_beats(
        b, chapter_id="CH02", map_constant="MAP_KEVLAR_TOWN", map_id=33,
        event_id=9, trainer_const="TRAINER_MARKO_19",
        defeat_flag="TRAINER_FLAGS_START + TRAINER_MARKO_19",
        beat_prefix="T9", trigger="event_touch", phone=False, double=False,
        retalk_pages=1, rider=False,
    )
    chapter = b.build()
    battle, retalk = chapter.beats

    assert battle.rows == ("map033/ev009/p0", "map033/ev009/p0/b0")
    assert {a.kind for a in battle.assertions} == {
        "trigger", "completes", "battle", "text", "self_switch_write"}

    battle_floor = floor_for_row("map033/ev009/p0", build_dir=_BUILD_DIR)
    assert uncovered(battle_floor, battle.assertions)  # non-empty: audio/visual

    assert retalk.rows == ("map033/ev009/p1",)
    assert "text" in {a.kind for a in retalk.assertions}


def test_ch04_larrie_declares_the_win_arm_branch_row() -> None:
    """map035 event 3 (Larrie, CH04): a plain self-switch defeat flag, not
    the native TRAINER_FLAGS bit -- the battle beat claims the win-arm
    branch row too, and declares its `self_switch_write`."""
    b = _builder()
    trainer_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=3, trainer_const="TRAINER_LARRIE_4",
        defeat_flag="FLAG_MAP035_EVENT003_SSA",
        beat_prefix="T2", trigger="event_touch", phone=True, double=False,
        retalk_pages=2, rider=False,
    )
    chapter = b.build()
    battle = chapter.beats[0]

    assert battle.rows == ("map035/ev003/p0", "map035/ev003/p0/b0")
    assert battle.archetype_of("map035/ev003/p0") == "trainer"
    # The branch row rides along, claimed by no archetype of its own (it is
    # a state-write consequence, not a recognized archetype shape).
    assert battle.archetype_of("map035/ev003/p0/b0") is None

    branch_floor = floor_for_row("map035/ev003/p0/b0", build_dir=_BUILD_DIR)
    branch_uncovered = uncovered(branch_floor, battle.assertions)
    # trigger/completes/self_switch_write are covered; the branch's own
    # pbPhoneRegisterBattle `service` call (phone=True instance) is honestly
    # left undeclared -- the battle beat's body never drives that flow.
    assert {a.kind for a in branch_uncovered} == {"service"}


# -- (b) contradicting trainer_const fails loud -------------------------------


def test_contradicting_trainer_const_fails_loud() -> None:
    b = _builder()
    # The disagreement this test cares about is trainer IDENTITY, not the
    # manifest-vs-stated params check -- use a param set that agrees with
    # the manifest (Timothy's real shape) but a trainer_const that names a
    # different trainer entirely.
    with pytest.raises(ValueError) as excinfo:
        trainer_beats(
            b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
            event_id=12, trainer_const="TRAINER_MARKO_19",  # wrong: real is Timothy
            defeat_flag="TRAINER_FLAGS_START + TRAINER_MARKO_19",
            beat_prefix="T1", trigger="event_touch", phone=False, double=False,
            retalk_pages=1, rider=False,
        )
    message = str(excinfo.value)
    assert "TRAINER_MARKO_19" in message
    assert "Timothy" in message


# -- (c) fake emulator: retalk body fails when declared text differs ----------


class _FakeRetalkEmu:
    """Minimal stand-in for `_register_retalk_beat`'s body: only the
    methods it actually calls, no mgba dependency (mirrors
    `test_playtest_assertions.py`'s `_FakeEmu` convention)."""

    def __init__(self, *, defeat_flag_set: bool, shown_texts: list[str],
                 trainer_at: tuple[int, int] = (5, 6)) -> None:
        self._defeat_flag_set = defeat_flag_set
        self._shown = shown_texts
        self._idx = 0
        self.screenshots: list[str] = []
        self.trainer_at = trainer_at
        self.interacted = 0

    def flag(self, _name: str) -> bool:
        return self._defeat_flag_set

    def resolve_constant(self, name: str) -> int:
        assert name == "LOCALID_PLAYER"
        return 255

    def object_event(self, local_id: int):
        from types import SimpleNamespace
        if local_id == 255:      # the player, at (5, 5) facing the trainer below
            return SimpleNamespace(x=5, y=5, facing="DOWN")
        assert local_id == _TRAINER_LID
        return SimpleNamespace(x=self.trainer_at[0], y=self.trainer_at[1], facing="UP")

    def walk_to(self, *_a, **_kw) -> None:
        raise AssertionError("a re-talk never walks (point 5)")

    def interact(self) -> None:
        self.interacted += 1

    def assert_text_contains(self, expected: str, *, exact: bool = False) -> None:
        actual = self._shown[self._idx]
        ok = (actual == expected) if exact else (expected in actual)
        if not ok:
            raise ScenarioError(
                f"expected field message text to "
                f"{'equal' if exact else 'contain'} {expected!r}; "
                f"actual text was {actual!r}"
            )

    def advance_dialog(self) -> None:
        self._idx += 1

    def field_locked(self) -> bool:
        return self._idx < len(self._shown)

    def current_field_message_text(self) -> str:
        return self._shown[self._idx] if self._idx < len(self._shown) else ""

    def screenshot(self, name: str) -> str:
        self.screenshots.append(name)
        return f"/tmp/{name}.png"


_ROW_ID = "map999/ev001/p1"
_TRAINER_LID = 7


def _text_floor(text: str) -> RowFloor:
    return RowFloor(
        row_id=_ROW_ID, trigger="action",
        assertions=frozenset({
            FloorAssertion(
                row_id=_ROW_ID, kind="text", list_index=0, code=101,
                params=make_params(index=0, text=text), tag="text",
            ),
            FloorAssertion(
                row_id=_ROW_ID, kind="trigger", list_index=-1, code=None,
                params=make_params(trigger="action"), tag="flow",
            ),
            FloorAssertion(
                row_id=_ROW_ID, kind="completes", list_index=-1, code=None,
                tag="flow",
            ),
        }),
        refusals=(),
    )


def _fake_floor_lookup(floor: RowFloor):
    def lookup(row_id: str) -> RowFloor:
        if row_id != floor.row_id:
            raise KeyError(row_id)
        return floor
    return lookup


def _register_fake_retalk(floor: RowFloor):
    b = _builder("CHZZ_RETALK")
    _register_retalk_beat(
        b, beat_prefix="TX", page_idx=1, retalk_row_id=_ROW_ID,
        map_constant="MAP_TEST", approach=(1, 1),
        defeat_flag="FLAG_TEST_DEFEAT", local_id=_TRAINER_LID, group="TX",
        floor_lookup=_fake_floor_lookup(floor),
    )
    chapter = b.build()
    return chapter.beats[0]


def test_retalk_beat_declares_text_from_floor() -> None:
    floor = _text_floor("Someone tougher than me? Impossible!")
    beat = _register_fake_retalk(floor)
    assert {a.kind for a in beat.assertions} == {"trigger", "completes", "text"}
    assert uncovered(floor, beat.assertions) == ()


def test_retalk_beat_body_fails_when_shown_text_differs_from_declared() -> None:
    floor = _text_floor("Someone tougher than me? Impossible!")
    beat = _register_fake_retalk(floor)
    emu = _FakeRetalkEmu(
        defeat_flag_set=True, shown_texts=["Something completely different."])
    with pytest.raises(ScenarioError, match="expected field message text"):
        beat.run(emu)  # type: ignore[arg-type]


def test_retalk_beat_body_passes_when_shown_text_matches_declared() -> None:
    floor = _text_floor("Someone tougher than me? Impossible!")
    beat = _register_fake_retalk(floor)
    emu = _FakeRetalkEmu(
        defeat_flag_set=True, shown_texts=["Someone tougher than me? Impossible!"])
    beat.run(emu)  # type: ignore[arg-type]  # must not raise
    assert emu.interacted == 1


def test_retalk_presses_a_in_place_and_fails_loud_when_the_trainer_is_not_faced() -> None:
    """Operator ruling 2026-10-01 (ROM run 59): no walk; the battled trainer
    must stand on the tile the player faces, else both positions are named."""
    beat = _register_fake_retalk(_text_floor("Someone tougher than me? Impossible!"))
    emu = _FakeRetalkEmu(defeat_flag_set=True, shown_texts=["x"], trainer_at=(5, 8))
    with pytest.raises(ScenarioError, match=r"faces DOWN onto \(5, 6\), but the trainer "
                                            r"\(local id 7\) stands at \(5, 8\)"):
        beat.run(emu)  # type: ignore[arg-type]
    assert emu.interacted == 0


# -- (d) intro text: declared only when every text box precedes the battle ----

_BATTLE_ROW = "map999/ev001/p0"


def _battle_floor(*text_indices: int, battle_index: int | None = 9) -> RowFloor:
    assertions = {
        FloorAssertion(row_id=_BATTLE_ROW, kind="text", list_index=i, code=101,
                       params=make_params(index=n, text=f"line {n}"), tag="text")
        for n, i in enumerate(text_indices)
    }
    if battle_index is not None:
        assertions.add(FloorAssertion(
            row_id=_BATTLE_ROW, kind="battle", list_index=battle_index, code=111,
            params=make_params(kind="trainer", name="X", trainer_type="Y"), tag="flow"))
    return RowFloor(row_id=_BATTLE_ROW, trigger="event_touch",
                    assertions=frozenset(assertions), refusals=())


def test_intro_text_before_the_battle_is_declarable() -> None:
    texts, reason = _intro_text_assertions(_BATTLE_ROW, lambda _row: _battle_floor(3, 8))
    assert reason is None
    assert [a.list_index for a in texts] == [3, 8]


def test_text_after_the_battle_blocks_the_declaration() -> None:
    texts, reason = _intro_text_assertions(_BATTLE_ROW, lambda _row: _battle_floor(8, 12))
    assert texts == ()
    assert reason is not None and "follow the battle" in reason


def test_text_without_a_battle_assertion_is_not_declared() -> None:
    texts, reason = _intro_text_assertions(
        _BATTLE_ROW, lambda _row: _battle_floor(1, battle_index=None))
    assert texts == ()
    assert reason is not None and "no 'battle'" in reason
