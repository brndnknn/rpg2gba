"""Headless mGBA core wrapper with poll-state input primitives.

Design rule (from the feasibility study): never frame-count a scripted input
tape — poll game state (coords, field-controls lock) and act on it, with
frame-budget timeouts that fail loud with a screenshot. That keeps scenarios
robust against text-length, timing, and converter changes.
"""
import heapq
import logging
import struct
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .contact_sheet import Waypoint
from .errors import ScenarioError
from .offsets import (
    OBJEVENT_ACTIVE_BIT_MASK,
    OBJEVENT_ACTIVE_BYTE_OFFSET,
    OBJEVENT_FACING_BYTE_OFFSET,
    OBJEVENT_FACING_MASK,
    probe_constants,
    probe_offsets,
)
from .symbols import (
    SymbolMap,
    static_addr_via_accessor,
    static_fn_via_literal_pool,
    static_ptr_via_accessor,
)

try:
    import mgba.core
    import mgba.image
    import mgba.log
    from mgba.gba import GBA
except ModuleNotFoundError as exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "mGBA python bindings not installed — run scripts/fetch_libmgba.py"
    ) from exc

logger = logging.getLogger(__name__)

KEYS = {
    "A": GBA.KEY_A, "B": GBA.KEY_B, "SELECT": GBA.KEY_SELECT,
    "START": GBA.KEY_START, "RIGHT": GBA.KEY_RIGHT, "LEFT": GBA.KEY_LEFT,
    "UP": GBA.KEY_UP, "DOWN": GBA.KEY_DOWN, "R": GBA.KEY_R, "L": GBA.KEY_L,
}

# walk_to's step-aside fallback (ROM_TEST_DEV.md C6a): per-direction grid
# deltas, and the two directions perpendicular to each axis.
_DIR_DELTA: dict[str, tuple[int, int]] = {
    "LEFT": (-1, 0), "RIGHT": (1, 0), "UP": (0, -1), "DOWN": (0, 1),
}
_PERPENDICULAR: dict[str, tuple[str, str]] = {
    "LEFT": ("UP", "DOWN"), "RIGHT": ("UP", "DOWN"),
    "UP": ("LEFT", "RIGHT"), "DOWN": ("LEFT", "RIGHT"),
}

# A waypoint frame captured during a palette fade or a battle transition is
# solid black — useless as the by-eye review surface the contact sheet exists
# to be (5 of 19 frames in the 2026-07-27 moki sheet were blank). A frame is
# "unreviewable" when it is essentially one flat colour, or so dark nothing in
# it can be judged; `waypoint` waits out that state before capturing.
_BLANK_COLOR_CAP = 8  # a fade/wipe frame holds a handful of colours at most
_BLANK_DOMINANCE = 0.98  # ...and one of them covers nearly every pixel
_DARK_LUMA = 24  # mean luma (0-255) below which a frame shows nothing usable
_SETTLE_BUDGET = 240  # 4s: longer than any fade, short enough to give up on
_SETTLE_STEP = 4

# How many times walk_to re-plans its route after a leg gets locally stuck
# (a randomly-walking NPC parked in a doorway is the normal cause, and it
# moves on its own within a second or two).
_MAX_REPLANS = 4
_REPLAN_WAIT = 60

# `walk_to(..., resolve_interruptions=True)`'s cap on how many times it will
# call `resolve_interruption()` and retry before giving up -- a walk that
# keeps getting re-interrupted after being resolved is a real bug (e.g. a
# trainer whose battle never actually ends), and must fail loud rather than
# spin forever.
_MAX_INTERRUPTION_RESOLUTIONS = 3

# `_walk_greedy`'s grace period for a mid-walk lock that might be a
# self-resolving scene -- an autorun cameo that plays out with no input and
# releases the field on its own (moki.py B4: crossing the fence-row tile
# fires Theo's cameo, then the walk continues) -- rather than one that will
# never clear without help (a msgbox waiting on a button the walk isn't
# pressing, a sight trainer's approach-and-battle). Long enough to outlast
# any scripted cameo on the roster; short enough that the input-blocked case
# still fails fast as `WalkInterrupted` instead of degrading back into the
# old slow frame-budget-exhaustion death.
_INTERRUPT_GRACE = 300  # 5s

# `resolve_interruption()`'s post-resolution settle budgets: how long to
# wait for the overworld to actually be back (field unlocked AND
# `gBackupMapLayout` loaded and consistent with `map_location()`) after
# winning a battle or clearing a dialogue, before treating "not back yet" as
# a bug rather than an ordinary transition. A battle-end fade back to the
# field is worth several seconds, not the couple of frames
# `wait_for_map_grid`'s own 300-frame default assumes for an ordinary warp --
# resuming `walk_to` before it finishes reads `gBackupMapLayout` still
# holding the battle's own stub grid (30x30, `map_location` (0,0)), and
# `_plan_route` then refuses the target with a "wrong map" message that
# points at the wrong layer (2026-08-11 route1 B4 regression: the ambush
# resolved and the battle was won correctly, but the resumed walk landed one
# frame into that still-settling transition).
_BATTLE_SETTLE_BUDGET = 600  # 10s
_DIALOGUE_SETTLE_BUDGET = 300  # 5s

# `_plan_route`'s cost for entering a tall-grass (`MB_TALL_GRASS`) tile, vs.
# 1 for ordinary ground -- Dijkstra prefers clear tiles when a reasonable
# detour exists, but still crosses grass rather than take an absurd one (a
# route entirely walled by grass, or a target that IS grass -- B4's cells,
# Flood standing in a field -- must still be reachable, see `_plan_route`'s
# own docstring on that point).
#
# Chosen from the encounter math, not guessed: at Route 1's observed 25%
# per-step encounter rate, the expected number of *plain* tiles between two
# encounters is 1/0.25 = 4 -- i.e. a 4-tile detour costs roughly the same in
# real walk time as the encounter (absorb battle, settle, resume) a grass
# tile has a 1-in-4 chance of costing instead. Pricing grass at 1 (base) + 4
# (that expected-detour-equivalent) = 5 means the planner will happily take
# up to a ~4-tile-longer clear route to dodge one grass cell, but won't
# wander 20 tiles out of its way just to avoid a single cell it could have
# crossed for the price of walking it once. This is a general-purpose
# constant (not a Route 1-specific tuning), so it deliberately isn't derived
# from Route 1's own encounter table -- 25% is pokeemerald's stock land
# encounter rate and a reasonable default for any map.
_GRASS_TRAVERSAL_COST = 5


class WalkInterrupted(ScenarioError):
    """A `walk_to` was cut short because the field went from unlocked to
    locked mid-walk -- a sight/patrol trainer ambush, or any other script
    that grabs the player -- rather than the walk simply running out of
    frame budget.

    Raised only when the walk *began* unlocked (see `_walk_greedy`'s
    `start_locked`); a walk that begins already locked (a beat that starts
    mid-scene, e.g. `moki.py` B5 handing a running autorun to B6) keeps
    today's wait-it-out behaviour unchanged.

    A caller that doesn't opt into `resolve_interruptions=True` still gets a
    clear, specific failure here instead of the old generic "frame budget
    exhausted" -- this subclasses `ScenarioError`, so nothing that already
    catches `ScenarioError` needs to change.
    """

    def __init__(self, target: tuple[int, int], stopped_at: tuple[int, int],
                 battle: bool) -> None:
        self.target = target
        self.stopped_at = stopped_at
        self.battle = battle
        kind = "a battle" if battle else "a locked-field scene"
        super().__init__(
            f"walk_to{target} interrupted by {kind} at {stopped_at}"
        )


@dataclass(frozen=True)
class ObjectEventState:
    """One decoded `gObjectEvents` slot (ROM_TEST_DEV.md "Harness cannot see
    NPCs").

    `local_id` is the object's *compiled* local id -- its 1-based position in
    the map JSON's `object_events` array after
    `tileset_converter/local_id_remap.py`'s per-map remap -- not necessarily
    the RMXP event id the source map used; scripts and this accessor both
    address objects by the compiled id. `x`/`y` are map-relative coordinates,
    de-biased by `MAP_OFFSET` the same way `player_pos()` reads
    `SaveBlock1.pos` un-biased (the engine's `currentCoords` carries the
    `+MAP_OFFSET` grid bias `player_pos()` never sees; see `stamp.py`'s
    `_verify_player_object_alive` for the same conversion done in reverse).
    """

    local_id: int
    active: bool
    x: int
    y: int
    facing: str
    graphics_id: int
    movement_type: int
    #: `ObjectEvent.trainerRange_berryTreeId` -- for a sight/patrol trainer,
    #: its own live sight range (see `_read_object_event_slot`'s note on why
    #: this defaults to 0 rather than failing on offset tables that predate
    #: it). Meaningless for non-trainer objects (item balls, NPCs); callers
    #: that care (route1.py's `_sight_lane_tiles`) only read it for objects
    #: they already know are trainers.
    trainer_range: int = 0


#: Maps each cardinal `DIR_*` probe key (offsets.py) to the facing string
#: `ObjectEventState.facing` reports.
_FACING_OFFSET_KEYS: dict[str, str] = {
    "val_dir_south": "DOWN",
    "val_dir_north": "UP",
    "val_dir_west": "LEFT",
    "val_dir_east": "RIGHT",
}


def _decode_facing(raw: int, offsets: dict) -> str:
    for offset_key, name in _FACING_OFFSET_KEYS.items():
        if raw == offsets[offset_key]:
            return name
    raise ScenarioError(
        f"object event facingDirection {raw} is not one of the known "
        f"cardinal DIR_* values (DOWN={offsets['val_dir_south']}, "
        f"UP={offsets['val_dir_north']}, LEFT={offsets['val_dir_west']}, "
        f"RIGHT={offsets['val_dir_east']})"
    )


def _read_object_event_slot(emu, base: int) -> ObjectEventState | None:
    """Decode one `gObjectEvents` slot starting at `base`, or None if the
    slot isn't active.

    Module-level and duck-typed on `emu` (needs only `.offsets` and
    `.u8`/`.u16`) so it is testable against a fake memory store with no mgba
    dependency, the same shape `battle.py`'s pure functions use.
    """
    o = emu.offsets
    active = emu.u8(base + OBJEVENT_ACTIVE_BYTE_OFFSET) & OBJEVENT_ACTIVE_BIT_MASK
    if not active:
        return None
    map_offset = o["val_map_offset"]
    coords_addr = base + o["off_objevent_currentcoords"]
    facing_raw = emu.u8(base + OBJEVENT_FACING_BYTE_OFFSET) & OBJEVENT_FACING_MASK
    try:
        trainer_range = emu.u8(base + o["off_objevent_trainerrange_berrytreeid"])
    except KeyError:
        # Degrades to 0 on an offsets table that predates this field
        # (test_object_events.py's fake) -- same fail-soft shape this
        # module already uses for fakes missing a newer primitive.
        trainer_range = 0
    return ObjectEventState(
        local_id=emu.u8(base + o["off_objevent_localid"]),
        active=True,
        x=emu.u16(coords_addr) - map_offset,
        y=emu.u16(coords_addr + 2) - map_offset,
        facing=_decode_facing(facing_raw, o),
        graphics_id=emu.u16(base + o["off_objevent_graphicsid"]),
        movement_type=emu.u8(base + o["off_objevent_movementtype"]),
        trainer_range=trainer_range,
    )


def _collision_walkable(blocks: Sequence[int], width: int, off: int,
                        map_w: int, map_h: int, x: int, y: int) -> bool:
    """Whether `(x, y)` (map-relative) is collision-0 on an already-fetched
    `gBackupMapLayout` grid -- the single implementation `Emulator.
    tile_walkable` (a one-off public query) and `_plan_route`'s internal
    `walkable()` closure (called once per Dijkstra node, with the grid
    already cached) both call, so the bit-twiddling and bounds semantics
    exist in exactly one place. Module-level rather than a method: neither
    caller needs `self` for this, and `_plan_route` calling it directly
    (instead of through `self.tile_walkable`) avoids re-running `_map_grid`
    -- a full grid parse -- on every single search-node expansion.

    Coordinates outside `(map_w, map_h)` (the map's own dimensions, not
    `_map_grid`'s border-padded frame) read as not walkable, never raise.
    """
    if not (0 <= x < map_w and 0 <= y < map_h):
        return False
    return (blocks[(x + off) + width * (y + off)] >> 10) & 0x3 == 0


class Emulator:
    """One headless core for one ROM, wired to one engine build's artifacts."""

    def __init__(self, rom: Path, engine: Path,
                 screenshot_dir: Path | None = None):
        mgba.log.silence()
        self.rom = rom
        self.engine = engine
        self.screenshot_dir = screenshot_dir
        self.waypoints: list[Waypoint] = []
        self.symbols = SymbolMap(engine / "pokeemerald.map")
        self.offsets = probe_offsets(engine)
        self._constants: dict[str, int] = {}
        self._lock_addr = static_addr_via_accessor(
            engine / "pokeemerald.elf",
            self.symbols["ArePlayerFieldControlsLocked"],
        )
        # `sFieldMessageBoxMode` (field_message_box.c): FIELD_MESSAGE_BOX_HIDDEN
        # (0) while no field message box is up, NORMAL/AUTO_SCROLL while one is.
        # Recovered through the same global-accessor trick as the lock above —
        # `IsFieldMessageBoxHidden` and `GetFieldMessageBoxMode` both compile to
        # the ldr-literal + ldrb shape and resolve to the same static.
        self._msgbox_addr = static_addr_via_accessor(
            engine / "pokeemerald.elf",
            self.symbols["IsFieldMessageBoxHidden"],
        )
        self._printer_list = static_ptr_via_accessor(
            engine / "pokeemerald.elf",
            self.symbols["IsTextPrinterActiveOnWindow"],
        )
        # `Task_HandleYesNoInput` (script_menu.c): the task `ScriptMenu_YesNo`
        # creates alongside the menu and which lives exactly as long as the
        # prompt is on screen. Static, so it is not in the link map — but
        # `ScriptMenu_YesNo` must load its address as a literal to pass it to
        # `FuncIsActiveTask`/`CreateTask`, so the pool carries it.
        self._yesno_task_fn = static_fn_via_literal_pool(
            engine / "pokeemerald.elf",
            self.symbols["ScriptMenu_YesNo"],
        )
        self._text_frame: "object | None" = None
        self._text_was_drawing = False
        self._frame_pinned = False
        self.core = mgba.core.load_path(str(rom))
        if self.core is None:
            raise ScenarioError(f"could not load ROM {rom}")
        self.screen = mgba.image.Image(*self.core.desired_video_dimensions())
        self.core.set_video_buffer(self.screen)
        if not self.core.autoload_save():
            # Without this, in-game saves are silently discarded (spike 3).
            raise ScenarioError(f"could not attach save file for {rom}")
        self.core.reset()
        self.frame = 0

    # -- raw access ---------------------------------------------------------

    def run(self, frames: int, keys: list[str] | None = None,
            on_frame: Callable[[], None] | None = None) -> None:
        """Advance `frames` frames with `keys` held for all of them.

        `on_frame` is called after each individual frame, for observations that
        must not miss a short-lived state (see `tap`). It must not advance the
        core itself. The keys stay held across the whole call either way —
        re-pressing per frame would turn one press into `frames` presses, and
        the engine's `JOY_NEW` checks would see every one of them.
        """
        mask = 0
        for k in keys or []:
            mask |= 1 << KEYS[k]
        self.core._core.setKeys(self.core._core, mask)
        for _ in range(frames):
            self.core.run_frame()
            self.frame += 1
            if on_frame is not None:
                on_frame()
        self.core._core.setKeys(self.core._core, 0)

    def u8(self, addr: int) -> int:
        return self.core.memory.u8[addr]

    def u16(self, addr: int) -> int:
        return self.core.memory.u16[addr]

    def u32(self, addr: int) -> int:
        return self.core.memory.u32[addr]

    def write_u16(self, addr: int, value: int) -> None:
        # Not `memory.u16[addr] = value`: that path in the mgba bindings
        # (site-packages/mgba/memory.py:60) calls `rawWrite16` without the
        # `segment` argument the C signature requires and dies with a cffi
        # arity TypeError. `raw_write` (:68) passes segment=-1 properly.
        self.core.memory.u16.raw_write(addr, value)

    def read_bytes(self, addr: int, size: int) -> bytes:
        return bytes(self.core.memory.u8[addr : addr + size])

    def snapshot_state(self) -> bytes:
        """Serialize the whole core (CPU, RAM, PPU, ...) for a later
        `restore_state`.

        Exists so a caller can run the engine's own routines (e.g. an
        in-game save, see `stamp.dump_save_blocks`) mid-scenario and then
        rewind, without the caller's live emulator ending up perturbed by
        it. Cost is a full-state copy (~400KB), not a ROM reboot.
        """
        raw = self.core.save_raw_state()
        if raw is None:
            raise ScenarioError("core.save_raw_state() returned no state")
        return bytes(raw)

    def restore_state(self, state: bytes) -> None:
        """Rewind the core to a `snapshot_state()` capture."""
        if not self.core.load_raw_state(state):
            raise ScenarioError(
                "core.load_raw_state() failed to restore a snapshot "
                f"({len(state)} bytes)")

    def screenshot(self, name: str) -> Path | None:
        if self.screenshot_dir is None:
            return None
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / f"{name}_f{self.frame}.png"
        self.screen.to_pil().convert("RGB").save(path)
        return path

    def _frame_unreviewable(self) -> bool:
        """True while the screen shows nothing worth a human's eye — a fade to
        or from black, a transition wipe, a battle intro's blank stretch."""
        img = self.screen.to_pil().convert("RGB")
        pixels = img.size[0] * img.size[1]
        counts = img.getcolors(maxcolors=_BLANK_COLOR_CAP)  # None if more
        if counts is not None and max(n for n, _ in counts) >= pixels * _BLANK_DOMINANCE:
            return True
        luma = img.convert("L")
        return sum(i * n for i, n in enumerate(luma.histogram())) / pixels < _DARK_LUMA

    def _settle_frame(self, budget: int = _SETTLE_BUDGET) -> int:
        """Advance until there is something to look at; returns frames spent.

        Safe to do at a waypoint: scenarios poll state rather than count
        frames (this module's design rule), and the only thing being waited
        out is an animation the game is already running. Bounded — a
        genuinely dark scene must cost a fixed 4s, not a hang.
        """
        spent = 0
        while spent < budget and self._frame_unreviewable():
            self.run(_SETTLE_STEP)
            spent += _SETTLE_STEP
        return spent

    def note_text_frame(self) -> None:
        """Photograph the frame a message finishes drawing on.

        Called once per frame from `tap`, which is what every loop that mashes
        a script forward is built out of. Each capture overwrites the last, so
        what survives to the beat boundary is the *final* message of the scene
        — the payoff line ("You got the Running Shoes!"), not the greeting that
        opened it. See `waypoint`.

        The capture point is the **falling edge** of `text_showing`, which is
        the frame the last glyph lands on (see that method — the flag tracks
        drawing, not visibility). Two weaker rules were tried first and both
        are wrong:

        - *Any frame with `text_showing` true* photographs a half-typed
          message; the tile reads "See you later, R".
        - *`text_showing` and `text_ready`* almost never coincides, because a
          message that fits one page clears `text_showing` on the very frame
          its printer finishes. Every short line vanished from the sheet.

        Edge detection needs per-frame sampling — a short message finishes and
        is dismissed inside one 12-frame tap — hence `run`'s `on_frame` hook.
        A gap in sampling costs a missed capture, never a wrong one.
        """
        finished = self._text_was_drawing and not self.text_showing()
        self._text_was_drawing = self.text_showing()
        if self.screenshot_dir is None or not finished or self._frame_pinned:
            return
        # A box drawn over a fade is no more use for review than a plain black
        # tile, and `text_ready` asserts the page really is drawn.
        if not self.text_ready() or self._frame_unreviewable():
            return
        self._text_frame = self.screen.to_pil().convert("RGB")

    def mark_frame(self, force: bool = False) -> bool:
        """Pin *this* frame as the beat's contact-sheet tile.

        The automatic rules (`note_text_frame`'s last-completed-message, else
        the live frame at the beat boundary) fit beats that play dialogue and
        end when it does. They cannot serve a beat whose interesting moment is
        something else — a menu that is up, a cutscene's peak, an NPC standing
        somewhere before it walks off — or a beat that ends without advancing
        the emulator at all, whose live frame is then just the previous beat's
        tile over again.

        Call this at the instant worth reviewing and the beat's single tile
        becomes that frame. Pinning is **sticky**: later dialogue in the same
        beat will not silently overwrite an explicit choice, which would
        otherwise make the mark's effect depend on whether more text happened
        to follow. `waypoint` clears the pin, so it is per-beat.

        Returns whether the frame was taken. A blank/mid-fade frame is refused
        (`force=True` overrides), because pinning one would produce exactly the
        black tile `_settle_frame` exists to avoid — and silently, since a
        pinned frame skips settling.
        """
        if self.screenshot_dir is None:
            return False
        if not force and self._frame_unreviewable():
            return False
        self._text_frame = self.screen.to_pil().convert("RGB")
        self._frame_pinned = True
        return True

    def waypoint(self, beat: str, name: str = "", note: str = "",
                 failed: bool = False) -> Waypoint | None:
        """Capture a frame for the run's contact sheet (ROM_TEST_DEV §2).

        Distinct from `screenshot`, which is failure evidence: waypoints are
        the *by-eye review surface* — the frames a human scans for the
        cosmetic defect class state assertions can't see. The runner takes
        one at every beat boundary automatically; a beat calls this itself
        when something mid-beat is worth a look (a cutscene's peak, a room
        the player only passes through).

        **Which frame.** A beat that plays a scene only returns once the scene
        has been mashed to its end and the field controls are free again, so
        the live frame at the beat boundary is always the world *after* the
        event: Auntie's shoes line already dismissed, Theo's cameo already
        walked off. That is the wrong moment to review. So if any dialogue was
        seen while the beat ran (`note_text_frame`), that frame is used instead
        of the live one, and the emulator is not advanced at all. A beat with
        no dialogue (a warp, a re-cross that must *not* fire) has nothing
        stored and still captures live. A beat that wants a specific moment
        neither rule picks says so with `mark_frame`, which wins over both.

        Beat boundaries land on warps and battle transitions, so a live frame
        at that instant is often mid-fade and solid black. A live non-failure
        capture therefore waits for the screen to settle first
        (`_settle_frame`); if it never does, the frame is still captured and
        the note says so, so a blank tile on the sheet always reads as "this
        is what the game showed" rather than "the harness caught it at a bad
        moment". A *failure* waypoint never advances the emulator and never
        substitutes a stored frame — that frame is evidence.
        """
        if self.screenshot_dir is None:
            self._text_frame = None
            self._frame_pinned = False
            return None
        frame = None if failed else self._text_frame
        self._text_frame = None
        self._frame_pinned = False
        if frame is None and not failed:
            self._settle_frame()
            if self._frame_unreviewable():
                blank = f"screen still blank after {_SETTLE_BUDGET}f"
                note = f"{note} — {blank}" if note else blank
        wp_dir = self.screenshot_dir / "waypoints"
        wp_dir.mkdir(parents=True, exist_ok=True)
        slug = f"{len(self.waypoints):02d}_{beat}"
        if name:
            slug += f"_{name}"
        path = wp_dir / f"{slug}.png"
        (frame if frame is not None else self.screen.to_pil().convert("RGB")).save(path)
        wp = Waypoint(beat=beat, name=name or beat, note=note,
                      frame=self.frame, path=path, failed=failed,
                      at_text=frame is not None)
        self.waypoints.append(wp)
        return wp

    # -- game state ---------------------------------------------------------

    @property
    def sb1(self) -> int:
        return self.u32(self.symbols["gSaveBlock1Ptr"])

    def player_pos(self) -> tuple[int, int]:
        base = self.sb1 + self.offsets["off_sb1_pos"]
        return self.core.memory.u16[base], self.core.memory.u16[base + 2]

    def map_location(self) -> tuple[int, int]:
        base = self.sb1 + self.offsets["off_sb1_location"]
        return self.u8(base), self.u8(base + 1)

    def object_events(self) -> list[ObjectEventState]:
        """Every ACTIVE slot in `gObjectEvents` (`OBJECT_EVENTS_COUNT`
        slots, probed via `val_object_events_count`)."""
        base = self.symbols["gObjectEvents"]
        stride = self.offsets["sizeof_objevent"]
        count = self.offsets["val_object_events_count"]
        events = []
        for i in range(count):
            ev = _read_object_event_slot(self, base + i * stride)
            if ev is not None:
                events.append(ev)
        return events

    def object_event(self, local_id: int) -> ObjectEventState:
        """The active object event whose (compiled) local id is `local_id`.

        Raises `ScenarioError` naming the local ids that ARE active when
        `local_id` isn't among them -- the harness has no other way to see
        NPCs, so a caller debugging "which id is Theo again" needs that list
        on the spot, not a bare KeyError.
        """
        events = self.object_events()
        for ev in events:
            if ev.local_id == local_id:
                return ev
        present = sorted(ev.local_id for ev in events)
        raise ScenarioError(
            f"no active object event with local id {local_id} -- active "
            f"local ids present: {present}"
        )

    def observe_object_event(self, local_id: int, frames: int, *,
                             sample_every: int = 4) -> list[ObjectEventState]:
        """Step `frames` frames, sampling `local_id`'s state every
        `sample_every` frames.

        The primitive a "does this NPC actually pace/patrol?" assertion is
        built on: run a beat's worth of frames and inspect the trajectory,
        rather than polling once before/after. Sampling is counted from this
        call's own first frame (1-indexed), not the emulator's absolute frame
        counter, so the cadence is the same regardless of when in a scenario
        it's called.
        """
        samples: list[ObjectEventState] = []
        counter = 0

        def _sample() -> None:
            nonlocal counter
            counter += 1
            if counter % sample_every == 0:
                samples.append(self.object_event(local_id))

        self.run(frames, on_frame=_sample)
        return samples

    def resolve_constant(self, name: str) -> int:
        """Resolve one `FLAG_*`/`VAR_*` (or any C macro) name to its value.

        Cache miss costs one gcc invocation; for more than one name at a
        time use `resolve_constants` so scenarios don't pay one compile per
        name.
        """
        if name not in self._constants:
            self._constants.update(probe_constants(self.engine, [name]))
        return self._constants[name]

    def resolve_constants(self, names: Sequence[str]) -> dict[str, int]:
        """Resolve several names in a single probe compile; warms the cache
        `resolve_constant` reads from."""
        missing = [n for n in names if n not in self._constants]
        if missing:
            self._constants.update(probe_constants(self.engine, missing))
        return {n: self._constants[n] for n in names}

    def flag(self, flag: str | int) -> bool:
        flag_id = self.resolve_constant(flag) if isinstance(flag, str) else flag
        byte = self.u8(self.sb1 + self.offsets["off_sb1_flags"] + flag_id // 8)
        return bool(byte >> (flag_id % 8) & 1)

    def var(self, var: str | int) -> int:
        """Read a VAR_* value, following the engine's own VarGet/GetVarPointer
        (event_data.c): ids in [VARS_START, SPECIAL_VARS_START) index
        SaveBlock1's `vars` array directly; ids below VARS_START aren't
        stored (VarGet just echoes the id back) and ids at/above
        SPECIAL_VARS_START are the dynamic "special vars" table (pointers
        resolved per-id, not a flat array) — neither is representable by a
        flat offset read, so both are a scenario error here."""
        var_id = self.resolve_constant(var) if isinstance(var, str) else var
        vars_start = self.offsets["vars_start"]
        special_vars_start = self.resolve_constant("SPECIAL_VARS_START")
        if not (vars_start <= var_id < special_vars_start):
            raise ScenarioError(
                f"var id {var_id} is outside the stored-vars range "
                f"[{vars_start}, {special_vars_start}) — special/temp vars "
                "aren't readable via a flat offset"
            )
        addr = self.sb1 + self.offsets["off_sb1_vars"] + (var_id - vars_start) * 2
        return self.core.memory.u16[addr]

    def field_locked(self) -> bool:
        """True while a script/dialogue holds the overworld controls."""
        return self.u8(self._lock_addr) != 0

    def overworld_input_ready(self) -> bool:
        """True once the main loop is genuinely back on the overworld and
        processing field input -- not merely `not field_locked()`.

        Field input (including START) is only ever read by `DoCB1_Overworld`,
        and `CB1_Overworld` only calls it while `gMain.callback2 ==
        CB2_Overworld` (`engine/src/overworld.c:1641-1645`):

            void CB1_Overworld(void)
            {
                if (gMain.callback2 == CB2_Overworld)
                    DoCB1_Overworld(gMain.newKeys, gMain.heldKeys);
            }

        `field_locked()` alone is not the same gate: `CB2_LoadMap` calls
        `UnlockPlayerFieldControls()` on its way into the destination map
        (`overworld.c:1953`, well before the map is playable -- see
        `map_grid_loaded`'s docstring for the same "grid vs. map" gap), so
        the lock can read False for a stretch of a door-warp/fade transition
        during which `gMain.callback2` is still some intermediate load/fade
        callback, not `CB2_Overworld` -- a START press in that window never
        reaches `ProcessPlayerFieldInput` at all and is silently dropped.

        Follows `battle.py`'s `in_battle` pattern: `gMain.callback2` read via
        `off_main_callback2`, compared against the callback's own (thumb-
        tagged) function address.
        """
        o = self.offsets
        callback2 = self.u32(self.symbols["gMain"] + o["off_main_callback2"])
        return callback2 == (self.symbols["CB2_Overworld"] | 1)

    def yesno_prompt_up(self) -> bool:
        """True while a `yesnobox` prompt is on screen awaiting an answer.

        Scans `gTasks` exactly as `FuncIsActiveTask` (task.c) does, for the
        handler `ScriptMenu_YesNo` installs. The task is created with the menu
        and destroyed when a choice is committed, so its lifetime *is* the
        prompt's — no frame counting, and no dependence on text speed.

        This is deliberately not `gSpecialVar_Result == 0xFF`: multichoice
        sets that sentinel too, so it cannot tell a yes/no prompt from one of
        the quiz's `dynmultichoice` questions.

        Answering is still done by button (`advance_dialog`'s `key`) — which
        option is *highlighted* remains unobservable, and A always commits the
        default YES.
        """
        o = self.offsets
        base = self.symbols["gTasks"]
        stride = o["sizeof_task"]
        for i in range(o["val_num_tasks"]):
            task = base + i * stride
            if not self.u8(task + o["off_task_is_active"]):
                continue
            if self.u32(task + o["off_task_func"]) == self._yesno_task_fn:
                return True
        return False

    def text_showing(self) -> bool:
        """True while a field message box is *drawing*.

        `sFieldMessageBoxMode`, which is narrower than it sounds and narrower
        than `field_locked` (that one is also true through fades, warps,
        scripted walk routes and battle transitions). It is set by
        `ShowFieldMessage` and cleared by `Task_DrawFieldMessage` the moment
        `RunTextPrintersAndIsPrinter0Active()` goes false — that is, when the
        last glyph lands, *not* when the box leaves the screen. The box stays
        up after this goes false, holding the finished text while the script
        waits for the player's button press.

        So this is "text is still appearing", and its falling edge is the
        frame at which a complete message is on screen. `note_text_frame`
        photographs that edge.
        """
        return self.u8(self._msgbox_addr) != 0

    def text_ready(self, window_id: int = 0) -> bool:
        """True when no glyphs are currently being drawn into `window_id`.

        The question a waypoint asks is "is the text on screen finished?", and
        there are two ways for that to be true, which is why this is phrased
        negatively:

        - A printer exists but is parked — RENDER_STATE_WAIT / CLEAR /
          SCROLL_START all mean a complete page sitting on the down-arrow
          waiting for the player. Only RENDER_STATE_HANDLE_CHAR is the printer
          still consuming characters.
        - No printer exists at all. A *final* page hits RENDER_FINISH as its
          last glyph lands, which frees the node off the list — while the box
          stays up and the script waits for its button press. So "message box
          showing, no printer" is the fully-drawn end of a one-page message,
          the single most reviewable frame there is. Requiring a parked printer
          instead would silently drop every short message (it dropped B2's
          refusal line).

        Walks `sFirstTextPrinter` exactly as `IsTextPrinterActiveOnWindow`
        does, but reads `state` rather than `active`: `active` stays TRUE for a
        printer's whole life and clears only at RENDER_FINISH, on the way to
        being freed, so it says nothing about drawing progress.

        The 16-node cap guards against following a cycle out of a torn pointer;
        the real list is a handful of nodes.
        """
        o = self.offsets
        node = self.u32(self._printer_list)
        for _ in range(16):
            if node == 0:
                return True
            if (self.u8(node + o["off_printer_type"]) == o["val_window_text_printer"]
                    and self.u8(node + o["off_printer_window_id"]) == window_id):
                return (self.u8(node + o["off_printer_state"])
                        != o["val_render_state_handle_char"])
            node = self.u32(node + o["off_printer_next"])
        return True

    # -- primitives ---------------------------------------------------------

    def tap(self, key: str, hold: int = 6, release: int = 6) -> None:
        """Press `key` for `hold` frames, then wait `release`.

        Samples for a finished page of dialogue on *every* frame, not once per
        tap. The moment worth photographing is often shorter than a single tap:
        a short message finishes drawing and is dismissed inside the same
        12-frame press/release cycle, so per-tap sampling saw it as "still
        typing" and then as "gone" with nothing in between (that is exactly how
        B2's refusal line went missing). `note_text_frame` costs two memory
        reads when there is nothing to capture, so this is cheap.
        """
        self.run(hold, [key], on_frame=self.note_text_frame)
        self.run(release, on_frame=self.note_text_frame)

    def face(self, direction: str) -> None:
        # A sub-step press turns in place without moving.
        self.tap(direction, hold=3, release=8)

    def _walk_step(self, direction: str, x: int, y: int) -> tuple[bool, int]:
        """Attempt one grid step in `direction` from `(x, y)`.

        Step-granular: release the key the moment the coord ticks over, so
        a burst can never overshoot onto a warp/trigger tile beyond a
        target. Returns `(moved, frames_spent)`. 40-frame cap: a
        turn-in-place (~8f) plus one walk step (~16f) fits with margin; a
        blocked direction burns the cap without moving.
        """
        for frames in range(1, 41):
            self.run(1, [direction])
            if self.player_pos() != (x, y):
                return True, frames
        return False, 40

    # -- route planning -----------------------------------------------------

    def _grid_dims_for_current_map(self) -> tuple[int, int] | None:
        """The `(width, height)` `gBackupMapLayout` will carry once the
        *current* map's layout has finished loading, or None if the header
        isn't readable yet.

        `InitBackupMapLayout` (`engine/src/fieldmap.c:171-174`) sizes the grid
        as the layout's own dimensions plus the border margin
        (`MAP_OFFSET_W` / `MAP_OFFSET_H`), so the header's layout is the
        authority on what a fully-loaded grid must look like.
        """
        o = self.offsets
        layout = self.u32(self.symbols["gMapHeader"] + o["off_mapheader_maplayout"])
        if layout == 0:
            return None
        width = self.u32(layout + o["off_maplayout_width"])
        height = self.u32(layout + o["off_maplayout_height"])
        if not (0 < width < 1024 and 0 < height < 1024):
            return None
        off = o["val_map_offset"]
        return width + (off * 2 + 1), height + off * 2

    def map_grid_loaded(self) -> bool:
        """Whether `gBackupMapLayout` describes the map the game reports.

        A warp writes `SaveBlock1.location` in `ApplyCurrentWarp`
        (`engine/src/overworld.c:620`) and only rebuilds the grid much later,
        in the `InitMap` call inside `LoadMapFromWarp`
        (`engine/src/overworld.c:982`). In between, the game reports the
        *destination* map while the grid still holds the *departure* map — so
        "the map changed" and "the grid is usable" are different events, and
        anything planning over the grid must wait for this one.

        Waiting on the field lock instead does not work: `CB2_LoadMap` calls
        `UnlockPlayerFieldControls` on the way in (`overworld.c:1953`), so
        controls read *unlocked* for the whole window.
        """
        expected = self._grid_dims_for_current_map()
        if expected is None:
            return False
        base = self.symbols["gBackupMapLayout"]
        o = self.offsets
        return (self.u32(base + o["off_backup_width"]),
                self.u32(base + o["off_backup_height"])) == expected

    def wait_for_map_grid(self, frame_budget: int = 300) -> int:
        """Run until `map_grid_loaded()`; returns the frames spent.

        Fails loud rather than letting a caller plan over another map's grid.
        That mistake is silent and destructive: a mid-warp arrival tile is
        usually itself a warp tile, so a route planned in the wrong frame of
        reference walks straight back through it onto the map just left,
        and every later assertion is then made about the wrong map.
        """
        spent = 0
        while spent < frame_budget:
            if self.map_grid_loaded():
                return spent
            self.run(2)
            spent += 2
        base = self.symbols["gBackupMapLayout"]
        o = self.offsets
        raise ScenarioError(
            f"map grid never finished loading within {frame_budget} frames "
            f"(gBackupMapLayout {self.u32(base + o['off_backup_width'])}x"
            f"{self.u32(base + o['off_backup_height'])}, expected "
            f"{self._grid_dims_for_current_map()}, "
            f"map_location={self.map_location()})")

    def _map_grid(self) -> tuple[int, int, tuple[int, ...]]:
        """The engine's own map grid for the current map: `(width, height,
        blocks)`, blocks being the packed u16s `MapGridGetCollisionAt` reads.

        Read from `gBackupMapLayout` rather than the built `map.bin` so the
        planner sees what the *running game* sees — script-applied metatile
        changes included — and so it needs no knowledge of which layout file
        belongs to the current map. Grid coordinates carry `MAP_OFFSET`;
        `player_pos()` (SaveBlock1.pos) does not, hence `_grid_index`.

        Refuses a grid that belongs to a different map than the one the game
        reports being on — see `map_grid_loaded`.
        """
        base = self.symbols["gBackupMapLayout"]
        o = self.offsets
        width = self.u32(base + o["off_backup_width"])
        height = self.u32(base + o["off_backup_height"])
        ptr = self.u32(base + o["off_backup_map"])
        if not (0 < width < 1024 and 0 < height < 1024) or ptr == 0:
            raise ScenarioError(
                f"gBackupMapLayout looks unreadable (width={width} "
                f"height={height} map=0x{ptr:08x}) — is a map loaded?")
        expected = self._grid_dims_for_current_map()
        if expected is not None and (width, height) != expected:
            raise ScenarioError(
                f"gBackupMapLayout is {width}x{height} but map_location() "
                f"{self.map_location()} wants {expected[0]}x{expected[1]} — "
                "the map is still loading; call wait_for_map_grid() first")
        raw = self.read_bytes(ptr, width * height * 2)
        return width, height, struct.unpack(f"<{width * height}H", raw)

    def _warp_tiles(self) -> set[tuple[int, int]]:
        """Map-relative coordinates of the current map's warp events.

        A route must never *enter* one it wasn't aimed at: stepping on a warp
        relocates the scenario to another map, which is the one walk failure
        mode that corrupts every assertion after it rather than failing.
        """
        o = self.offsets
        events = self.u32(self.symbols["gMapHeader"] + o["off_mapheader_events"])
        if events == 0:
            return set()
        count = self.u8(events + o["off_mapevents_warpcount"])
        warps = self.u32(events + o["off_mapevents_warps"])
        if warps == 0:
            return set()
        stride = o["sizeof_warpevent"]
        return {
            (self.u16(warps + i * stride + o["off_warpevent_x"]),
             self.u16(warps + i * stride + o["off_warpevent_y"]))
            for i in range(count)
        }

    def _player_object_slot(self) -> int:
        """The `gObjectEvents` slot index (`gPlayerAvatar.objectEventId`) the
        player's own object occupies -- same accessor `stamp.py`'s
        `_verify_player_object_alive` uses. Not necessarily equal to that
        slot's `localId` field, and never assume slot 0: this is the only
        correct way to identify "the player" among active object events."""
        o = self.offsets
        avatar = self.symbols["gPlayerAvatar"]
        return self.u8(avatar + o["off_playeravatar_objecteventid"])

    def _occupied_object_tiles(self, goal: tuple[int, int]) -> set[tuple[int, int]]:
        """Map-relative tiles held by active object events, for `_plan_route`
        to treat as blocked.

        Excludes the player's own slot (identified via
        `_player_object_slot`, not by assuming a fixed index) and the goal
        tile itself -- a scenario very often walks *to* an NPC, and the
        route must still be planned onto that tile.

        One table read per call (no per-BFS-node cost, `_plan_route` calls
        this once). Degrades to an empty set -- terrain-only planning -- on
        any failure reading the table, rather than raising: this is a
        planning optimisation, never something that can fail a scenario.
        """
        try:
            player_slot = self._player_object_slot()
            base = self.symbols["gObjectEvents"]
            stride = self.offsets["sizeof_objevent"]
            count = self.offsets["val_object_events_count"]
            occupied: set[tuple[int, int]] = set()
            for i in range(count):
                if i == player_slot:
                    continue
                ev = _read_object_event_slot(self, base + i * stride)
                if ev is None:
                    continue
                tile = (ev.x, ev.y)
                if tile != goal:
                    occupied.add(tile)
            return occupied
        except Exception:
            logger.info(
                "_plan_route: failed to read object events, degrading to "
                "terrain-only planning", exc_info=True)
            return set()

    def _grass_cost_context(self) -> dict | None:
        """Everything `_plan_route` needs to price a tile's grass cost,
        fetched once per call rather than per BFS/Dijkstra node: the current
        map's primary/secondary tileset `metatileAttributes` pointers, the
        `isFrlg` attribute-format flag, and the resolved `MB_TALL_GRASS`/
        `NUM_METATILES_IN_PRIMARY`/mask constants.

        Mirrors the real engine's own `GetAttributeByMetatileIdAndMapLayout`
        (`engine/src/fieldmap.c`) pointer chain: `gMapHeader.mapLayout` ->
        `primaryTileset`/`secondaryTileset` -> each tileset's
        `metatileAttributes` (one packed `u16` per metatile, masked by
        `METATILE_ATTR_BEHAVIOR_MASK[_FRLG]` for the behavior byte). Reading
        `isFrlg` live rather than assuming Emerald format keeps this correct
        for any map, not just Route 1's.

        Degrades to `None` -- grass costs nothing, same as before this
        primitive existed -- on any failure resolving the pointer chain or
        constants, the same fail-soft shape `_occupied_object_tiles` uses:
        this is a path-preference optimisation, never something that can
        fail a scenario outright.
        """
        try:
            o = self.offsets
            layout = self.u32(self.symbols["gMapHeader"] + o["off_mapheader_maplayout"])
            is_frlg = self.u8(layout + o["off_maplayout_isfrlg"])
            primary = self.u32(layout + o["off_maplayout_primarytileset"])
            secondary = self.u32(layout + o["off_maplayout_secondarytileset"])
            primary_attrs = self.u32(primary + o["off_tileset_metatileattributes"])
            secondary_attrs = self.u32(secondary + o["off_tileset_metatileattributes"])
            consts = self.resolve_constants((
                "MB_TALL_GRASS", "NUM_METATILES_IN_PRIMARY",
                "METATILE_ATTR_BEHAVIOR_MASK", "METATILE_ATTR_BEHAVIOR_MASK_FRLG",
                "MAPGRID_METATILE_ID_MASK",
            ))
            return {
                "primary_attrs": primary_attrs,
                "secondary_attrs": secondary_attrs,
                "num_primary": consts["NUM_METATILES_IN_PRIMARY"],
                "behavior_mask": (consts["METATILE_ATTR_BEHAVIOR_MASK_FRLG"]
                                  if is_frlg else consts["METATILE_ATTR_BEHAVIOR_MASK"]),
                "mb_tall_grass": consts["MB_TALL_GRASS"],
                "metatile_id_mask": consts["MAPGRID_METATILE_ID_MASK"],
            }
        except Exception:
            logger.info(
                "_plan_route: failed to resolve the grass-behavior pointer "
                "chain, degrading to flat tile costs", exc_info=True)
            return None

    def tile_walkable(self, x: int, y: int) -> bool:
        """Whether `(x, y)` (map-relative) is collision-0 walkable terrain
        on the current map's live grid -- the same collision check
        `_plan_route` searches over, exposed as a one-off public query for
        callers that need to test a single tile without going through the
        whole route-planning machinery (e.g. route1.py's
        `_sight_lane_tiles`, picking a trainer's approach tile).

        Ignores warp/object-event exclusions -- those are `_plan_route`-
        specific routing concerns, not part of "is this tile walkable
        terrain" -- and, unlike `_plan_route`, never raises on an
        out-of-bounds coordinate; it simply reads as not walkable, since a
        caller probing a single tile has no route to fail.

        Shares its bit-twiddling with `_plan_route`'s internal `walkable()`
        via the module-level `_collision_walkable` -- see that function's
        docstring for why `_plan_route` doesn't call this method directly
        (it would re-run `_map_grid` per search node).
        """
        width, height, blocks = self._map_grid()
        off = self.offsets["val_map_offset"]
        map_w, map_h = width - (off * 2 + 1), height - off * 2
        return _collision_walkable(blocks, width, off, map_w, map_h, x, y)

    def _plan_route(self, start: tuple[int, int],
                    goal: tuple[int, int]) -> list[tuple[int, int]] | None:
        """Least-cost walkable route between two map-relative tiles, or
        None.

        Dijkstra (uniform-cost search) over collision-0 tiles, avoiding warp
        tiles other than the goal and tiles held by active object events
        (NPCs, item balls, solid Rock events on Route 1) other than the
        player's own object and the goal tile (see
        `_occupied_object_tiles`). Elevation is deliberately not modelled —
        mismatched-elevation edges (cliff rims) would be planned through; a
        leg that hits one gets locally stuck and re-planned, and ultimately
        fails loud, which is the same outcome as any other impassable
        route.

        Tall grass (`MB_TALL_GRASS`, via `_grass_cost_context`) costs
        `_GRASS_TRAVERSAL_COST` instead of the usual 1, so a route prefers a
        reasonable clear detour over a field but still crosses it when
        that's the only way through -- including when grass IS the
        destination (B4 deliberately walks onto grass cells; Flood himself
        stands in one). Cost only ever biases which route is chosen among
        walkable ones; it is never a reachability gate -- the plain BFS
        reachability semantics (a tile is either walkable or it isn't) are
        unchanged, just the tie-breaking among walkable routes. If the
        behavior pointer chain can't be resolved, every tile costs 1 and
        this is exactly the old plain-BFS behaviour.

        Object events are a snapshot taken once per call, not re-read per
        search node: a patrolling NPC can make a planned route stale the
        moment it steps, which is exactly what `walk_to`'s stuck/step-aside
        retry and re-plan loop exists to absorb -- this is an optimisation
        to avoid the common body-block case, not a replacement for that
        recovery path.

        Also not modelled: sideways staircases (`GetSidewaysStairsCollision`
        in `engine/src/event_object_movement.c`,
        `GetRightSideStairsDirection` in `engine/src/field_player_avatar.c`),
        where the engine turns an EAST/WEST press into a diagonal move. This
        search is 4-neighbour, so a destination reachable only across such a
        staircase is unroutable here and must be stepped manually by the
        scenario.

        A goal outside the grid's own bounds is not an unroutable target but
        a wrong grid, and raises — see `_route_waypoints`.
        """
        width, height, blocks = self._map_grid()
        off = self.offsets["val_map_offset"]
        map_w, map_h = width - (off * 2 + 1), height - off * 2
        if not (0 <= goal[0] < map_w and 0 <= goal[1] < map_h):
            raise ScenarioError(
                f"walk_to{goal} targets a tile outside the loaded map grid "
                f"({map_w}x{map_h}, map_location={self.map_location()}) — "
                "wrong map, or the grid belongs to another one")
        avoid = self._warp_tiles() - {goal}
        occupied = self._occupied_object_tiles(goal)
        # `_grass_cost_context` is undefined on the lightweight `_plan_route`
        # test fakes that predate this primitive (`test_plan_route_objects.
        # py`'s `_FakeRouteEmu`) -- degrade to flat costs for those, same
        # AttributeError-degrade shape `_walk_greedy` uses for `_in_battle`.
        try:
            grass_ctx = self._grass_cost_context()
        except AttributeError:
            grass_ctx = None
        grass_cache: dict[tuple[int, int], bool] = {}

        def walkable(x: int, y: int) -> bool:
            if (x, y) in avoid or (x, y) in occupied:
                return False
            return _collision_walkable(blocks, width, off, map_w, map_h, x, y)

        def is_grass(x: int, y: int) -> bool:
            if grass_ctx is None:
                return False
            key = (x, y)
            cached = grass_cache.get(key)
            if cached is not None:
                return cached
            metatile_id = (blocks[(x + off) + width * (y + off)]
                            & grass_ctx["metatile_id_mask"])
            if metatile_id < grass_ctx["num_primary"]:
                addr = grass_ctx["primary_attrs"] + metatile_id * 2
            else:
                addr = (grass_ctx["secondary_attrs"]
                        + (metatile_id - grass_ctx["num_primary"]) * 2)
            behavior = self.u16(addr) & grass_ctx["behavior_mask"]
            result = behavior == grass_ctx["mb_tall_grass"]
            grass_cache[key] = result
            return result

        def step_cost(x: int, y: int) -> int:
            return _GRASS_TRAVERSAL_COST if is_grass(x, y) else 1

        dist: dict[tuple[int, int], int] = {start: 0}
        prev: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        heap: list[tuple[int, tuple[int, int]]] = [(0, start)]
        while heap:
            d, cur = heapq.heappop(heap)
            if d > dist[cur]:
                continue  # a cheaper path to `cur` was already settled
            if cur == goal:
                path = []
                node: tuple[int, int] | None = cur
                while node is not None:
                    path.append(node)
                    node = prev[node]
                return path[::-1]
            cx, cy = cur
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nxt = (cx + dx, cy + dy)
                if not walkable(*nxt):
                    continue
                nd = d + step_cost(*nxt)
                if nd < dist.get(nxt, float("inf")):
                    dist[nxt] = nd
                    prev[nxt] = cur
                    heapq.heappush(heap, (nd, nxt))
        return None

    def _route_waypoints(self, tx: int, ty: int) -> list[tuple[int, int]]:
        """Turn a planned route into the corner tiles `_walk_greedy` can
        reach in a straight line, ending at the target.

        If the grid can't be planned over — no route found, or the tile data
        doesn't say what the engine really allows — this degrades to the bare
        target and lets the greedy walker try anyway, so an ordinary planner
        blind spot costs a slower failure rather than a wrong answer.

        The one shape that is *not* a blind spot is a target outside the
        grid's own bounds: that means the grid is not this map's, and walking
        greedily on it is exactly the destructive case `wait_for_map_grid`
        exists to prevent, so `_plan_route` raises instead.
        """
        start = self.player_pos()
        if start == (tx, ty):
            return [(tx, ty)]
        route = self._plan_route(start, (tx, ty))
        if route is None:
            logger.warning("walk_to(%d,%d): no planned route from %s — "
                           "falling back to greedy pathing", tx, ty, start)
            return [(tx, ty)]
        corners = [
            route[i] for i in range(1, len(route) - 1)
            if (route[i][0] - route[i - 1][0], route[i][1] - route[i - 1][1])
            != (route[i + 1][0] - route[i][0], route[i + 1][1] - route[i][1])
        ]
        return corners + [(tx, ty)]

    def walk_to(self, tx: int, ty: int, frame_budget: int = 3000,
                max_sidesteps: int = 8, *,
                resolve_interruptions: bool = False) -> None:
        """Walk to `(tx, ty)` on the current map, planning around walls.

        The route comes from the engine's own collision grid
        (`_route_waypoints`), and each leg between two corners is walked by
        the greedy stepper below, whose step-aside retry absorbs the
        transient obstacle the grid can't see: another actor standing in the
        way. A leg that stays stuck is not a failure yet — NPCs move — so the
        walk waits briefly and re-plans, up to `_MAX_REPLANS` times, before
        failing loud with the leg's own diagnosis.

        Waits for the destination map's grid to finish loading first: a beat
        that has just crossed a warp reaches here while `gBackupMapLayout`
        still holds the map it left (`map_grid_loaded`), and planning in that
        window silently walks back through the arrival warp.

        A sight/patrol trainer can ambush a route that crosses its cone at
        any point, on any map, in any chapter — the walk goes from unlocked
        to locked mid-route and `WalkInterrupted` is raised (see
        `_walk_greedy`). By default that propagates to the caller, same as
        any other `ScenarioError`. Pass `resolve_interruptions=True` to have
        this method resolve the interruption itself (`resolve_interruption`)
        and resume walking toward the original target, up to
        `_MAX_INTERRUPTION_RESOLUTIONS` times before failing loud — so a
        pathological repeat-interrupt case still can't hang the scenario.

        Each retry below passes the SAME `frame_budget` the caller gave this
        `walk_to` call — never a value decremented or otherwise carried over
        from a previous attempt. A resumed walk is a brand-new
        `_walk_to_once` call and gets a brand-new, fully fresh budget every
        time; the retry COUNT (`_MAX_INTERRUPTION_RESOLUTIONS`) is what
        bounds the loop, not a shrinking per-attempt allowance.
        """
        if not resolve_interruptions:
            _walk_to_once(self, tx, ty, frame_budget, max_sidesteps)
            return
        for attempt in range(_MAX_INTERRUPTION_RESOLUTIONS):
            try:
                _walk_to_once(self, tx, ty, frame_budget, max_sidesteps)
                return
            except WalkInterrupted as exc:
                logger.info(
                    "walk_to(%d,%d): interrupted by %s at %s, resolving "
                    "(attempt %d/%d)", tx, ty,
                    "a battle" if exc.battle else "a locked-field scene",
                    exc.stopped_at, attempt + 1, _MAX_INTERRUPTION_RESOLUTIONS)
                self.resolve_interruption()
        raise ScenarioError(
            f"walk_to({tx},{ty}) was still getting interrupted after "
            f"{_MAX_INTERRUPTION_RESOLUTIONS} resolve_interruption() attempts")

    def _in_battle(self) -> bool:
        """Whether a battle is currently running (`battle.in_battle`).

        Imported lazily -- same discipline as `battle.py`'s own lazy
        `Emulator` import under `TYPE_CHECKING` -- so this module stays
        importable without pulling in `battle.py` at load time.
        """
        from . import battle
        return battle.in_battle(self)

    def is_trainer_battle(self) -> bool:
        """Whether the in-progress battle is a trainer battle, as opposed
        to a wild encounter -- `gBattleTypeFlags & BATTLE_TYPE_TRAINER`
        (`include/constants/battle.h`), read the same late-bound way as
        every other engine fact in this file: the global resolved via
        `symbols`, the bit resolved via `resolve_constant` (a probe
        compile), never a hardcoded address or literal.

        A caller (e.g. `route1.py`'s B4, which must fight off an incidental
        trainer ambush but hand a wild encounter back untouched -- that's
        its actual objective) needs this the instant `WalkInterrupted`
        reports `battle=True`, so it fails loud rather than reading garbage
        if called with no battle running: the flag is only meaningful while
        `BattleMainCB2` owns the main loop.
        """
        if not self._in_battle():
            raise ScenarioError(
                "is_trainer_battle() called while no battle is in progress")
        flags = self.u32(self.symbols["gBattleTypeFlags"])
        trainer_bit = self.resolve_constant("BATTLE_TYPE_TRAINER")
        return bool(flags & trainer_bit)

    def resolve_interruption(self, *, dialogue_max_taps: int = 1500,
                             battle_settle_budget: int = _BATTLE_SETTLE_BUDGET,
                             dialogue_settle_budget: int = _DIALOGUE_SETTLE_BUDGET,
                             ) -> str:
        """Resolve whatever currently has the player interrupted, and report
        what it was: `"battle"`, `"dialogue"`, or `"none"` if neither is
        actually in progress.

        A battle in progress is won with `battle.win_battle` (the existing
        battle helper); a merely-locked field (a scene, an ambush's
        approach-and-battle intro) is mashed through with `advance_dialog`
        until it releases. Fails loud if the field is still locked after
        `dialogue_max_taps` -- an interruption this can't clear is a real
        bug, not something to paper over with a bigger budget.

        Either path can hand control back mid-transition -- a battle-end
        fade, or a dialogue release that was itself a warp/scene change --
        so both settle on the same post-condition before returning:
        `_wait_for_overworld_return` (field unlocked AND the map grid
        loaded and consistent with `map_location()`). Without that, the
        caller (typically `walk_to(resolve_interruptions=True)`, resuming
        toward its original target) can resume one frame into the wrong
        scene and get a confusing "wrong map" error out of `_plan_route`
        instead of the real, settling-took-too-long one raised here.
        """
        if self._in_battle():
            from . import battle
            battle.win_battle(self)
            self._wait_for_overworld_return(battle_settle_budget)
            return "battle"
        if self.field_locked():
            self.advance_dialog(max_taps=dialogue_max_taps)
            if self.field_locked():
                shot = self.screenshot("resolve_interruption_stuck")
                raise ScenarioError(
                    "resolve_interruption: field still locked after "
                    f"{dialogue_max_taps} dialogue taps ({shot})")
            self._wait_for_overworld_return(dialogue_settle_budget)
            return "dialogue"
        return "none"

    def _wait_for_overworld_return(self, budget: int) -> None:
        """Wait until the overworld is genuinely back: field unlocked AND
        the map grid loaded and consistent with `map_location()`
        (`map_grid_loaded`, the same check `walk_to` itself waits on before
        planning a route).

        Fails loud, naming the layer that's actually stuck (`field_locked`,
        `map_grid_loaded`, `map_location`) -- the alternative is silence
        here and a `ScenarioError` from `_plan_route` a moment later,
        correctly-worded but pointing at the wrong layer (see
        `resolve_interruption`'s docstring).
        """
        spent = 0
        while spent < budget:
            if not self.field_locked() and self.map_grid_loaded():
                return
            self.run(10)
            spent += 10
        shot = self.screenshot("resolve_interruption_overworld_not_back")
        raise ScenarioError(
            f"resolve_interruption: the overworld did not return within "
            f"{budget} frames after resolving (field_locked="
            f"{self.field_locked()}, map_grid_loaded={self.map_grid_loaded()}, "
            f"map_location={self.map_location()}) ({shot})")

    def _walk_greedy(self, tx: int, ty: int, frame_budget: int,
                     max_sidesteps: int, start_map: tuple[int, int],
                     *, start_locked: bool = False,
                     ) -> tuple[bool, int, str]:
        """Greedy two-axis walk with blocked-axis fallback and step-aside
        retry.

        When both preferred directions are blocked -- typically a randomly-
        walking NPC parked on the direct line, ROM_TEST_DEV.md C6 -- this
        does not fail immediately. It steps one tile perpendicular to the
        blocked axis and re-paths toward the target from there, alternating
        which perpendicular direction it prefers and avoiding a just-tried
        sidestep tile where an alternative exists, so it can't oscillate
        between the same two tiles forever. Attempts are bounded by
        `max_sidesteps`.

        Returns `(arrived, frames_spent, reason)`. A stuck leg is *reported*,
        not raised — `walk_to` owns the decision to re-plan or give up, and
        raises with this `reason` so the two stuck shapes (impassable target
        vs. plain budget timeout) still read distinctly. Two cases raise
        directly instead: a changed map identity (the scenario is already on
        the wrong map, and re-planning would compound it), and an ambush --
        see `start_locked` below.

        `start_locked` is whatever `field_locked()` read at the *start* of
        the whole `walk_to` call (not this leg) -- passed through unchanged
        across every leg and replan of one `walk_to`. If the field was
        already locked when the walk began, a lock seen here is nothing new
        and today's behaviour is preserved exactly: wait, then re-path from
        wherever the script leaves us.

        If the field started unlocked, a lock appearing here needs one more
        distinction: is it a *self-resolving* scene (a scripted autorun/
        cameo -- e.g. `moki.py` B4's Theo trigger -- that plays out with no
        input and releases the field on its own), or one that will never
        clear without help (a battle, or a msgbox waiting on a button the
        walk isn't pressing -- a sight trainer's approach-and-battle)? A
        battle raises `WalkInterrupted` immediately -- waiting is pointless.
        Anything else gets `_INTERRUPT_GRACE` frames to release on its own;
        if it does, the walk just continues toward the target, same as
        today. Only once the grace expires with the field still locked does
        this raise `WalkInterrupted`, so `resolve_interruption` can advance
        the dialogue it's stuck on.

        A wild encounter is a separate case again: it sets **no script
        lock at all** (2026-08-11 route1 B4 regression -- `field_locked()`
        stayed False through an entire wild battle, so the old lock-gated
        detection never fired, and the walk either burned its whole frame
        budget pressing into the battle screen or eventually re-planned
        against the battle scene's own stub map grid). So `_in_battle()` is
        polled on its own too, independently of `locked`, once per outer
        iteration -- each spans up to `_walk_step`'s own 40-frame cap, so
        this is a poll roughly every 40 frames rather than every single
        emulated one (cheap either way -- one u32 read -- but this avoids
        threading a battle check into `_walk_step`'s tight per-frame loop),
        while still catching a wild encounter within one step's latency.
        Gated on `start_locked` the same as the lock path: a battle that's
        part of an already-running scene the walk expected going in is not
        a new interruption.
        """
        spent = 0
        sidestep_count = 0
        visited_sidesteps: set[tuple[int, int]] = set()
        perp_toggle = 0

        while spent < frame_budget:
            if not start_locked:
                # A wild encounter: no script, no lock, just a battle. Catch
                # it here rather than only inside the `locked` branch below,
                # which a lock-free battle never enters. `_in_battle` is
                # undefined on the lightweight `walk_to` test fakes that
                # predate this poll (`test_playtest.py`'s `_FakeWalkEmu`,
                # which never sets a lock either) -- degrade to "not
                # battling" for those rather than erroring, the same
                # fake-degradation shape `_occupied_object_tiles` already
                # uses elsewhere in this file.
                try:
                    battling = self._in_battle()
                except AttributeError:
                    battling = False
                if battling:
                    raise WalkInterrupted((tx, ty), self.player_pos(), True)
            locked = self.field_locked()
            if locked:
                if start_locked:
                    # A script owns the player (scene auto-walk, dialogue we
                    # bumped into) and the walk already expected that going
                    # in. Don't fight it — wait, then re-path from wherever
                    # it leaves us. EXCEPT a battle: `start_locked` meant
                    # "some scene already owned the player when this walk
                    # began," never "and it is therefore fine to wait
                    # through a battle with zero button presses" — nothing
                    # ever submits a move in that case, so the scene can
                    # never complete on its own, and this loop used to just
                    # spend the whole `frame_budget` re-running `self.run
                    # (30)` before failing with a bare "frame budget
                    # exhausted" (2026-08-11 route1 B4 regression: a
                    # trainer's notice sequence was already mid-flight —
                    # locked but not yet `_in_battle()` — when a resumed
                    # `_walk_absorbing` retry issued a fresh `walk_to` call,
                    # so THAT call's own `start_locked` read True and this
                    # branch swallowed the battle it turned into). Same
                    # fake-degradation shape as the `not start_locked` poll
                    # above.
                    try:
                        battling = self._in_battle()
                    except AttributeError:
                        battling = False
                    if battling:
                        raise WalkInterrupted(
                            (tx, ty), self.player_pos(), True)
                    self.run(30)
                    spent += 30
                    continue
                if self._in_battle():
                    raise WalkInterrupted(
                        (tx, ty), self.player_pos(), True)
                # Unknown yet whether this is a self-resolving cameo or a
                # scene that's actually waiting on input/a battle. Give it
                # `_INTERRUPT_GRACE` to release on its own before treating
                # it as a real interruption.
                grace_spent = 0
                while grace_spent < _INTERRUPT_GRACE and self.field_locked():
                    if self._in_battle():
                        raise WalkInterrupted(
                            (tx, ty), self.player_pos(), True)
                    self.run(30)
                    grace_spent += 30
                    spent += 30
                if self.field_locked():
                    raise WalkInterrupted(
                        (tx, ty), self.player_pos(), self._in_battle())
                # Released within the grace -- a self-resolving scene, same
                # as moki.py B4's cameo. Resume walking toward the target.
                continue
            x, y = self.player_pos()
            if (x, y) == (tx, ty):
                # The coord ticks before the step animation finishes; settle
                # so a follow-up face/interact isn't eaten by the motion.
                self.run(16)
                # 2026-08-11 route1 B15 regression: a wild encounter rolled
                # by this very last step can declare itself (lock and/or
                # `_in_battle()`) partway through the settle above, not
                # before it -- `field_locked()` read False at the top of
                # THIS iteration (that's how we got into this branch at
                # all), so nothing upstream ever saw an interruption. This
                # used to return `True` unconditionally regardless of what
                # the settle revealed, so a caller's very next action (e.g.
                # `_collect_item`'s `face()`/`interact()`) pressed A into an
                # already-arriving wild battle transition it had no way to
                # know about: `interact()` saw `field_locked()` and assumed
                # its own script had started, `advance_dialog()` then mashed
                # blind through someone else's battle, and the item's flag
                # never got set. Re-check post-settle and raise the same way
                # every other interruption in this function does, so
                # `walk_to(resolve_interruptions=True)`/`_walk_absorbing`
                # get to apply their existing wild/trainer policy instead of
                # the caller finding out several actions later. Degrades
                # like the `not start_locked` poll above for fakes that
                # don't implement `_in_battle`.
                try:
                    battling = self._in_battle()
                except AttributeError:
                    battling = False
                if battling or self.field_locked():
                    raise WalkInterrupted((tx, ty), self.player_pos(), battling)
                return True, spent + 16, ""
            dx, dy = tx - x, ty - y
            axes = [("RIGHT" if dx > 0 else "LEFT") if dx else None,
                    ("DOWN" if dy > 0 else "UP") if dy else None]
            if abs(dy) > abs(dx):
                axes.reverse()
            axes = [a for a in axes if a]

            moved = False
            for d in axes:
                ok, frames = self._walk_step(d, x, y)
                spent += frames
                if ok:
                    moved = True
                    break
            if moved:
                self._require_same_map(start_map, tx, ty, "step")
                continue

            # Both greedy directions are blocked. Step off the direct line
            # and re-path, instead of failing on what's likely a transient
            # NPC body-block.
            if sidestep_count >= max_sidesteps:
                return False, spent, (
                    f"stuck after {sidestep_count} step-aside attempts at "
                    f"{x},{y} heading for {tx},{ty}")

            primary = axes[0]
            perp_a, perp_b = _PERPENDICULAR[primary]
            order = [perp_a, perp_b] if perp_toggle == 0 else [perp_b, perp_a]
            perp_toggle ^= 1
            # Prefer whichever perpendicular tile wasn't just tried, so a
            # persistently-blocked pair of directions can't bounce the
            # player between the same two tiles forever.
            order.sort(key=lambda d: (x + _DIR_DELTA[d][0],
                                       y + _DIR_DELTA[d][1]) in visited_sidesteps)

            stepped = False
            for d in order:
                ok, frames = self._walk_step(d, x, y)
                spent += frames
                if ok:
                    stepped = True
                    break
            sidestep_count += 1

            if not stepped:
                # Blocked on every side, not just body-blocked.
                return False, spent, (
                    f"stuck after {sidestep_count} step-aside attempts at "
                    f"{x},{y} heading for {tx},{ty}")

            visited_sidesteps.add(self.player_pos())
            self._require_same_map(start_map, tx, ty, "sidestep")

        shot = self.screenshot("walk_budget")
        raise ScenarioError(f"walk_to({tx},{ty}) frame budget exhausted ({shot})")

    def _require_same_map(self, start_map: tuple[int, int], tx: int, ty: int,
                          how: str) -> None:
        """Abort the walk if a step relocated the player to another map.

        Stepping onto a warp is the one walk mishap that doesn't fail on its
        own — the scenario would just carry on asserting against the wrong
        map — so it's checked after every move, not only after sidesteps.
        """
        here_map = self.map_location()
        if here_map != start_map:
            shot = self.screenshot("walk_map_changed")
            raise ScenarioError(
                f"walk_to({tx},{ty}) {how} changed map from "
                f"{start_map} to {here_map} — aborting ({shot})")

    def interact(self) -> None:
        """Press A; fail if no script picks up the field controls."""
        self.tap("A")
        self.run(30)
        if not self.field_locked():
            shot = self.screenshot("interact_noop")
            raise ScenarioError(f"interaction did not start a script ({shot})")

    def advance_dialog(self, key: str = "A", max_taps: int = 1500,
                       stop: Callable[[], bool] | None = None) -> int:
        """Mash `key` until the script releases the field controls.

        The single dialogue-advancing loop in the harness — every scenario and
        chapter beat goes through here, which is what makes the contact
        sheet's text-frame capture (`note_text_frame`) universal instead of
        something each beat has to remember to do.

        `key` is a parameter because a couple of beats must make a specific
        yes/no choice partway through an otherwise-uninterrupted locked
        script, and the harness has no probe for "a yesnobox is highlighted on
        option N". Two engine facts make button choice a reliable substitute,
        so this stays poll-driven rather than frame-counted:

        - Ordinary dialogue boxes advance on A or B identically throughout
          pokeemerald (the `JOY_NEW(A_BUTTON | B_BUTTON)` text-advance
          pattern), so holding one button for a whole stretch of plain
          msgboxes is safe.
        - `yesnobox` (asm/macros/event.inc): "Pressing B is equivalent to
          answering NO", and these prompts open via `ScriptMenu_YesNo` ->
          `DisplayYesNoMenuDefaultYes` (src/script_menu.c), so A commits
          whatever is highlighted, which is always YES.

        So "hold A through this stretch" deterministically answers YES at
        whichever yesnobox appears in it, and "hold B" answers NO, regardless
        of how many plain messages precede it.

        `stop` is an extra exit condition checked alongside the lock, for
        scripts that end in something other than a release — a battle gives no
        release to stop on, and mashing A into one resolves it by accident.
        """
        taps = 0
        while self.field_locked() and not (stop is not None and stop()):
            if taps >= max_taps:
                shot = self.screenshot("dialog_stuck")
                raise ScenarioError(
                    f"dialogue never released field controls ({shot})")
            self.tap(key)  # samples text frames on every frame it runs
            taps += 1
        self.note_text_frame()
        return taps


def _walk_to_once(emu: "Emulator", tx: int, ty: int, frame_budget: int,
                  max_sidesteps: int) -> None:
    """The body of `Emulator.walk_to`, without interruption resolution -- a
    single attempt that either arrives, raises `WalkInterrupted`, or fails
    loud with a stuck/budget diagnosis.

    Module-level (not a method) so `walk_to`'s `resolve_interruptions=True`
    loop can retry it directly, and so unit tests exercising `walk_to`
    against a bare fake object (no real `Emulator` instance -- see
    `tests/test_playtest.py`'s `_FakeWalkEmu` and
    `tests/test_walk_interruption.py`) don't need that fake to define a
    `_walk_to_once` method of its own -- there is nothing here `walk_to`
    itself doesn't already call directly.
    """
    spent = 0
    spent += emu.wait_for_map_grid()
    start_map = emu.map_location()
    # Captured once, for the whole walk (not per-leg): only a transition
    # from unlocked-at-start to locked-during-the-walk is an ambush. A walk
    # that begins already locked (a beat continuing a running scene) must
    # keep today's wait-it-out behaviour unchanged.
    start_locked = emu.field_locked()
    reason = f"walk_to({tx},{ty}) made no progress"
    for _ in range(_MAX_REPLANS):
        stuck = False
        for wx, wy in emu._route_waypoints(tx, ty):
            arrived, used, why = emu._walk_greedy(
                wx, wy, frame_budget - spent, max_sidesteps, start_map,
                start_locked=start_locked)
            spent += used
            if not arrived:
                stuck, reason = True, why
                break
        if not stuck:
            return
        if spent + _REPLAN_WAIT >= frame_budget:
            break
        emu.run(_REPLAN_WAIT)
        spent += _REPLAN_WAIT
    shot = emu.screenshot("walk_stuck")
    raise ScenarioError(f"{reason} ({shot})")
