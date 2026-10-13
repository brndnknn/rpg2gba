"""The on-ROM visibility invariant (PROJECT_TODO #137, playtest/visibility.py).

Pure page-pick tests, plus `object_visibility_violations` against a fake
emulator and registry: no mGBA, no build tree."""
import pytest

from rpg2gba.conversion_agent.flag_registry import FlagRegistry
from rpg2gba.playtest import visibility
from rpg2gba.playtest.emulator import ObjectEventState
from rpg2gba.playtest.errors import ScenarioError
from rpg2gba.playtest.visibility import (
    Unreadable,
    check_object_visibility,
    live_page,
    object_visibility_violations,
    page_shows,
)


def _cond(**kw):
    base = {"switch1_valid": False, "switch1_id": 1, "switch2_valid": False,
            "switch2_id": 1, "variable_valid": False, "variable_id": 1,
            "variable_value": 0, "self_switch_valid": False, "self_switch_ch": "A"}
    base.update(kw)
    return base


def _page(sheet="NPC", opacity=255, tile_id=0, **cond):
    return {"condition": _cond(**cond),
            "graphic": {"character_name": sheet, "opacity": opacity, "tile_id": tile_id}}


# Map040 EV018 "Fufufu" (CH06 walk #135): seen at boot and after self switch
# A; self switch B (written by another event's script) or switch 55 blanks him.
FUFUFU = [
    _page(),
    _page(self_switch_valid=True, self_switch_ch="A"),
    _page("", self_switch_valid=True, self_switch_ch="B"),
    _page("", switch1_valid=True, switch1_id=55),
]


def _pick(pages, switches=None, variables=None, selfs=()):
    switches = switches or {}
    variables = variables or {}
    return live_page(
        pages,
        lambda s: switches.get(s, Unreadable(f"switch {s}")),
        lambda v: variables.get(v, Unreadable(f"var {v}")),
        lambda letter: letter in selfs)


# -- page_shows / live_page ----------------------------------------------

def test_page_shows_needs_a_graphic_and_opacity():
    assert page_shows(_page())
    assert not page_shows(_page(""))
    assert not page_shows(_page(opacity=0))
    assert page_shows(_page("", tile_id=384))


def test_highest_holding_page_wins():
    assert _pick(FUFUFU, switches={55: False}) == 0
    assert _pick(FUFUFU, switches={55: False}, selfs={"A"}) == 1
    assert _pick(FUFUFU, switches={55: False}, selfs={"A", "B"}) == 2
    assert _pick(FUFUFU, switches={55: True}) == 3


def test_no_holding_page_is_none():
    pages = [_page(self_switch_valid=True, self_switch_ch="A")]
    assert _pick(pages) is None


def test_unreadable_page_above_the_winner_is_unreadable():
    # switch 55 can't be read, and its page outranks every other one.
    assert isinstance(_pick(FUFUFU, selfs={"A"}), Unreadable)


def test_a_false_atom_settles_a_page_with_an_unreadable_one():
    pages = [_page(), _page("", switch1_valid=True, switch1_id=9,
                            self_switch_valid=True, self_switch_ch="C")]
    assert _pick(pages) == 0


def test_variable_condition_is_at_least():
    pages = [_page(), _page("", variable_valid=True, variable_id=4, variable_value=3)]
    assert _pick(pages, variables={4: 2}) == 0
    assert _pick(pages, variables={4: 3}) == 1


# -- object_visibility_violations -------------------------------------------

class _Emu:
    def __init__(self, objects, flags=(), locked=False):
        self._objects = objects
        self._flags = set(flags)
        self._locked = locked
        self.resolved: list[list[str]] = []
        self.shots: list[str] = []

    def object_events(self):
        return self._objects

    def uranium_map_id(self, group, num):
        return {(0, 1): 14001, (0, 2): 33}[(group, num)]

    def resolve_constants(self, names):
        self.resolved.append(list(names))
        return {n: 0 for n in names}

    def flag(self, name):
        return name in self._flags

    def var(self, name):
        return 0

    def field_locked(self):
        return self._locked

    def screenshot(self, name):
        self.shots.append(name)
        return f"{name}.png"


def _obj(local_id, map_num=1, invisible=False):
    return ObjectEventState(local_id=local_id, active=True, x=13, y=5, facing="DOWN",
                            graphics_id=1, movement_type=0, map_group=0,
                            map_num=map_num, invisible=invisible)


@pytest.fixture
def registry(monkeypatch):
    reg = FlagRegistry()
    reg.propose_flag(55, "FLAG_STORY_55")
    reg.mint_self_switch(14001, 18, "A")
    reg.mint_self_switch(14001, 18, "B")
    events = {14001: {18: {"id": 18, "pages": FUFUFU},
                      141: {"id": 141, "pages": [_page(opacity=0)]}},
              33: {18: {"id": 18, "pages": [_page()]}}}
    monkeypatch.setattr(visibility, "_map_events", lambda m: events[m])
    monkeypatch.setattr(visibility, "_event_for_local_id",
                        lambda m: {14001: {2: 18, 4: 141}, 33: {2: 18}}[m])
    monkeypatch.setattr(visibility, "_berry_tree", lambda m, e: False)
    return reg


def test_a_blanked_npc_still_spawned_is_reported(registry):
    emu = _Emu([_obj(2)], flags={"FLAG_MAP040_EVENT018_SSA", "FLAG_MAP040_EVENT018_SSB"})

    found = object_visibility_violations(emu, registry)

    assert [(v.event_id, v.page) for v in found] == [(18, 2)]
    assert emu.resolved == [sorted(["FLAG_STORY_55", "FLAG_MAP040_EVENT018_SSA",
                                    "FLAG_MAP040_EVENT018_SSB"])]


def test_a_visible_live_page_passes(registry):
    emu = _Emu([_obj(2)], flags={"FLAG_MAP040_EVENT018_SSA"})
    assert object_visibility_violations(emu, registry) == []


def test_a_never_visible_actor_is_reported_even_invisible(registry):
    # Map040 EV141 (#136): opacity 0 on every page, spawned by a bracket.
    emu = _Emu([_obj(4, invisible=True)])

    (found,) = object_visibility_violations(emu, registry)

    assert (found.event_id, found.invisible) == (141, True)
    assert "still blocks" in found.describe()


def test_objects_are_read_against_their_own_map(registry):
    # Local id 2 is Fufufu on 14001 but a plain NPC on map 33: an object left
    # over from the previous map is judged by that map's events.
    emu = _Emu([_obj(2, map_num=2)], flags={"FLAG_MAP040_EVENT018_SSB"})
    assert object_visibility_violations(emu, registry) == []


def test_the_player_and_unknown_local_ids_are_skipped(registry):
    emu = _Emu([_obj(255)])
    assert object_visibility_violations(emu, registry) == []


def test_a_native_berry_tree_is_skipped(registry, monkeypatch):
    # Map033 EV101: a blank `pbBerryPlant` page the plant script draws over.
    monkeypatch.setattr(visibility, "_berry_tree", lambda m, e: e == 141)
    emu = _Emu([_obj(4)])
    assert object_visibility_violations(emu, registry) == []


def test_an_unreadable_event_is_skipped(registry, monkeypatch):
    pages = [_page(), _page("", switch1_valid=True, switch1_id=77)]
    monkeypatch.setattr(visibility, "_map_events",
                        lambda m: {18: {"id": 18, "pages": pages}})
    emu = _Emu([_obj(2)])
    assert object_visibility_violations(emu, registry) == []


def test_check_raises_with_a_frame(registry, monkeypatch):
    emu = _Emu([_obj(2)], flags={"FLAG_MAP040_EVENT018_SSB"})
    _use_registry(monkeypatch, registry)

    with pytest.raises(ScenarioError, match=r"map14001/ev018 .*live page p2 has no graphic"):
        check_object_visibility(emu, "m14001e014_warp")
    assert emu.shots == ["m14001e014_warp_visibility"]


def test_check_skips_a_locked_field(registry, monkeypatch):
    emu = _Emu([_obj(2)], flags={"FLAG_MAP040_EVENT018_SSB"}, locked=True)
    _use_registry(monkeypatch, registry)
    check_object_visibility(emu, "mid_scene")
    assert emu.shots == []


def _use_registry(monkeypatch, reg):
    from rpg2gba.playtest.archetypes import generic

    monkeypatch.setattr(generic, "_flag_registry", lambda: reg)


def test_registry_self_switch_lookup_uses_the_origin_map():
    reg = FlagRegistry()
    reg.mint_self_switch(40, 18, "b")
    assert reg.get_self_switch(14001, 18, "B") == "FLAG_MAP040_EVENT018_SSB"
    assert reg.get_self_switch(14001, 18, "C") is None
