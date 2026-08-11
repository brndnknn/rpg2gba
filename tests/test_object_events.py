"""Tests for object-event observability (ROM_TEST_DEV.md "Harness cannot see
NPCs" — `Emulator.object_events`/`object_event`/`observe_object_event`).

Same fake-memory-store style as `tests/test_playtest.py`'s `_FakeEmu`: no
mgba bindings, no ROM. `Emulator`'s methods are plain instance methods with
no `__init__`-time state dependency, so they're called unbound against a
lightweight stand-in that only implements `symbols`/`offsets`/`u8`/`u16`/
`run` — exactly what they read.
"""
from rpg2gba.playtest.emulator import Emulator, ObjectEventState
from rpg2gba.playtest.errors import ScenarioError

import pytest

# Real probed values (offsets.py's `_PROBE_ENTRIES`, verified 2026-08-10
# against the vendored engine at `engine/`), pinned here so these tests need
# neither devkitARM nor the engine tree to run.
OFFSETS = {
    "sizeof_objevent": 36,
    "off_objevent_localid": 8,
    "off_objevent_movementtype": 6,
    "off_objevent_graphicsid": 4,
    "off_objevent_currentcoords": 16,
    "val_map_offset": 7,
    "val_object_events_count": 3,
    "val_dir_south": 1,
    "val_dir_north": 2,
    "val_dir_west": 3,
    "val_dir_east": 4,
}

GOBJECTEVENTS = 0x02020000


class _FakeMemory:
    """Sparse little-endian byte store standing in for `core.memory`."""

    def __init__(self) -> None:
        self._bytes: dict[int, int] = {}

    def get(self, addr: int, width: int) -> int:
        value = 0
        for i in range(width):
            value |= self._bytes.get(addr + i, 0) << (8 * i)
        return value

    def set(self, addr: int, width: int, value: int) -> None:
        for i in range(width):
            self._bytes[addr + i] = (value >> (8 * i)) & 0xFF


class _FakeEmu:
    """Minimal Emulator stand-in exposing just what the object-event
    accessors read: `symbols`/`offsets` and `u8`/`u16`/`run`.

    Binds the three real (unbound) `Emulator` methods under test onto this
    class, so `object_event`'s internal `self.object_events()` call resolves
    against the fake instead of requiring a real `Emulator`.
    """

    object_events = Emulator.object_events
    object_event = Emulator.object_event
    observe_object_event = Emulator.observe_object_event

    def __init__(self, offsets: dict) -> None:
        self.symbols = {"gObjectEvents": GOBJECTEVENTS}
        self.offsets = offsets
        self._mem = _FakeMemory()
        self.frame = 0

    def u8(self, addr: int) -> int:
        return self._mem.get(addr, 1)

    def u16(self, addr: int) -> int:
        return self._mem.get(addr, 2)

    def write_u8(self, addr: int, value: int) -> None:
        self._mem.set(addr, 1, value)

    def write_u16(self, addr: int, value: int) -> None:
        self._mem.set(addr, 2, value)

    def run(self, frames: int, keys=None, on_frame=None) -> None:
        for _ in range(frames):
            self.frame += 1
            if on_frame is not None:
                on_frame()


def _write_slot(emu: _FakeEmu, index: int, *, active: bool, local_id: int,
                 x: int, y: int, facing: int, graphics_id: int,
                 movement_type: int) -> int:
    """Write one `gObjectEvents[index]` slot into the fake store; returns its
    base address. `facing` is a raw `DIR_*` value (already biased)."""
    o = emu.offsets
    base = emu.symbols["gObjectEvents"] + index * o["sizeof_objevent"]
    emu.write_u8(base + 0, 1 if active else 0)  # OBJEVENT_ACTIVE_BYTE_OFFSET/MASK
    emu.write_u8(base + o["off_objevent_localid"], local_id)
    emu.write_u8(base + o["off_objevent_movementtype"], movement_type)
    emu.write_u16(base + o["off_objevent_graphicsid"], graphics_id)
    map_offset = o["val_map_offset"]
    coords = base + o["off_objevent_currentcoords"]
    emu.write_u16(coords, x + map_offset)
    emu.write_u16(coords + 2, y + map_offset)
    emu.write_u8(base + 0x18, facing & 0x0F)  # OBJEVENT_FACING_BYTE_OFFSET/MASK
    return base


# -- object_events() / object_event() ------------------------------------

def test_parses_two_active_slots() -> None:
    emu = _FakeEmu(dict(OFFSETS))
    _write_slot(emu, 0, active=True, local_id=1, x=5, y=9, facing=1,
                graphics_id=42, movement_type=3)
    _write_slot(emu, 1, active=True, local_id=2, x=10, y=2, facing=4,
                graphics_id=7, movement_type=0)

    events = emu.object_events()

    assert events == [
        ObjectEventState(local_id=1, active=True, x=5, y=9, facing="DOWN",
                          graphics_id=42, movement_type=3),
        ObjectEventState(local_id=2, active=True, x=10, y=2, facing="RIGHT",
                          graphics_id=7, movement_type=0),
    ]


def test_inactive_slots_are_skipped() -> None:
    emu = _FakeEmu(dict(OFFSETS))
    _write_slot(emu, 0, active=True, local_id=1, x=0, y=0, facing=1,
                graphics_id=1, movement_type=0)
    _write_slot(emu, 1, active=False, local_id=2, x=0, y=0, facing=1,
                graphics_id=1, movement_type=0)
    # slot 2 left all-zero: also inactive (active bit 0).

    events = emu.object_events()

    assert [e.local_id for e in events] == [1]


def test_coordinates_are_debiased_from_map_offset() -> None:
    emu = _FakeEmu(dict(OFFSETS))
    base = _write_slot(emu, 0, active=True, local_id=1, x=12, y=3, facing=2,
                        graphics_id=1, movement_type=0)
    coords = base + OFFSETS["off_objevent_currentcoords"]
    # Confirm the raw store really carries the +MAP_OFFSET bias, not the
    # de-biased value -- otherwise this test wouldn't be exercising the
    # de-bias step at all.
    assert emu.u16(coords) == 12 + OFFSETS["val_map_offset"]
    assert emu.u16(coords + 2) == 3 + OFFSETS["val_map_offset"]

    ev = emu.object_event(1)

    assert (ev.x, ev.y) == (12, 3)


def test_facing_decodes_all_four_cardinal_directions() -> None:
    emu = _FakeEmu(dict(OFFSETS))
    for i, (raw, expected) in enumerate(
        [(1, "DOWN"), (2, "UP"), (3, "LEFT"), (4, "RIGHT")]
    ):
        emu.offsets["val_object_events_count"] = 4
        _write_slot(emu, i, active=True, local_id=i + 1, x=0, y=0,
                    facing=raw, graphics_id=0, movement_type=0)

    facings = {e.local_id: e.facing for e in emu.object_events()}

    assert facings == {1: "DOWN", 2: "UP", 3: "LEFT", 4: "RIGHT"}


def test_unknown_facing_value_raises_scenario_error() -> None:
    emu = _FakeEmu(dict(OFFSETS))
    _write_slot(emu, 0, active=True, local_id=1, x=0, y=0, facing=0,  # DIR_NONE
                graphics_id=0, movement_type=0)

    with pytest.raises(ScenarioError, match="facingDirection"):
        emu.object_events()


def test_object_event_not_found_lists_present_local_ids() -> None:
    emu = _FakeEmu(dict(OFFSETS))
    _write_slot(emu, 0, active=True, local_id=3, x=0, y=0, facing=1,
                graphics_id=0, movement_type=0)
    _write_slot(emu, 1, active=True, local_id=7, x=0, y=0, facing=1,
                graphics_id=0, movement_type=0)

    with pytest.raises(ScenarioError, match=r"\[3, 7\]"):
        emu.object_event(99)


def test_object_event_found_returns_matching_slot() -> None:
    emu = _FakeEmu(dict(OFFSETS))
    _write_slot(emu, 0, active=True, local_id=5, x=1, y=1, facing=1,
                graphics_id=9, movement_type=2)

    ev = emu.object_event(5)

    assert ev.local_id == 5
    assert ev.movement_type == 2


# -- observe_object_event() ------------------------------------------------

class _PacingFakeEmu(_FakeEmu):
    """A fake whose `run` mutates the object's x coordinate every frame,
    standing in for an NPC actually pacing under `observe_object_event`."""

    def __init__(self, offsets: dict, coords_addr: int) -> None:
        super().__init__(offsets)
        self._coords_addr = coords_addr

    def run(self, frames: int, keys=None, on_frame=None) -> None:
        for _ in range(frames):
            self.frame += 1
            self.write_u16(self._coords_addr,
                            self.frame + self.offsets["val_map_offset"])
            if on_frame is not None:
                on_frame()


def test_observe_object_event_samples_at_requested_cadence() -> None:
    offsets = dict(OFFSETS)
    emu = _PacingFakeEmu(offsets, coords_addr=0)
    base = _write_slot(emu, 0, active=True, local_id=1, x=0, y=0, facing=1,
                        graphics_id=1, movement_type=1)
    emu._coords_addr = base + offsets["off_objevent_currentcoords"]

    samples = emu.observe_object_event(local_id=1, frames=12, sample_every=4)

    # Sampled on frames 4, 8, 12 of the call -- each sample sees the x value
    # `run` wrote on that exact frame, proving the accessor actually
    # observes movement across the call rather than reading a single
    # before/after snapshot.
    assert [s.x for s in samples] == [4, 8, 12]
    assert len(samples) == 3
