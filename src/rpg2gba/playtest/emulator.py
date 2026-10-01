"""Headless mGBA core wrapper with poll-state input primitives.

Design rule (from the feasibility study): never frame-count a scripted input
tape — poll game state (coords, field-controls lock) and act on it, with
frame-budget timeouts that fail loud with a screenshot. That keeps scenarios
robust against text-length, timing, and converter changes.
"""
import functools
import heapq
import logging
import os
import re
import struct
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..text_validator.engine_metrics import load_charmap
from ..tileset_converter.map_constants import DEFAULT_STATE_PATH as _DEFAULT_MAP_CONSTANTS_STATE
from ..tileset_converter.map_constants import MapConstantRegistry
from ..traversal.graph import MapGraph, build_map_graph
from .charmap import invert_charmap_english_first
from .contact_sheet import Waypoint
from .contradictions import (
    KIND_REPLAY_FALLBACK,
    KIND_UNRESOLVED_MAP,
    KIND_WALKABILITY,
    Contradiction,
    ContradictionLedger,
)
from .divergence import WalkedTile
from .errors import RoutePlanningError, ScenarioError
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
    mart_info_layout,
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

# `walk_to(..., absorb_wild=True)`: how many wild battles one walk may fight
# off, and how long a lock that is not yet a battle gets to become one. The
# cap is `ch02.py`'s `_MAX_ABSORBED_INTERRUPTIONS` (sized there from Route 1's
# grass: P(>12 encounters in a 15-tile crossing at 25%) < 1e-6). The wait is
# input-free, so a scene waiting on a button is left exactly as it was.
_MAX_ABSORBED_WILD = 12
_WILD_BATTLE_WAIT = 600  # 10s

# `_walk_greedy`'s grace period for a mid-walk lock that might be a
# self-resolving scene -- an autorun cameo that plays out with no input and
# releases the field on its own (ch01.py B4: crossing the fence-row tile
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

# The metatile behaviours under which the engine will actually warp the player
# off a tile that carries a `warp_event`. EVERY trigger path in
# `engine/src/field_control_avatar.c` gates on two things, not one: a warp
# event at the position (`GetWarpEventAtMapPosition`) AND the tile's own
# behaviour. A `warp_event` sitting on plain floor (`MB_NORMAL`) fires
# nothing when it is stepped on.
#
# That is not a curiosity, it is the converter's normal output. Emerald has no
# free-coordinate landing: an inbound warp must name an index into the
# DESTINATION map's own warp table, so `metadata_wiring._resolve_all_warp_events`
# emits an "arrival" `warp_event` on B for every source warp A->B, at B's
# arrival coordinates, deliberately left as plain floor. `WARP_OVERRIDES`
# stamps door metatiles at SOURCE warp coordinates only. So a map reachable by
# a warp carries inert warp_events that a player walks straight over, and a
# router that treats the warp table as the hazard list seals corridors the game
# does not.
#
# Route 01's (15,7)/(16,7) Kevlar arrivals are the case that found this: they
# made B17's target (15,6) unreachable on both the live grid and the offline
# graph, while a human walks through them without a transition.
#
# Derived from the fork, not from memory (CLAUDE.md 4.7) -- the union of
# `IsWarpMetatileBehavior`, `IsArrowWarpMetatileBehavior`,
# `IsDirectionalStairWarpMetatileBehavior` (`field_screen_effect.c`) and
# `TryDoorWarp`'s secret-base branch, expanded through
# `engine/src/metatile_behavior.c`. Direction is deliberately NOT modelled:
# an arrow warp or a sideways stair only fires when entered from one side,
# but the planner has no committed approach direction at the time it builds
# the avoid-set, so all four are treated as hazards. Over-avoiding costs a
# detour or a loud unroutable; under-avoiding walks the scenario onto another
# map, which corrupts every assertion after it.
_WARP_TRIGGER_BEHAVIORS: tuple[str, ...] = (
    # IsWarpMetatileBehavior
    "MB_ANIMATED_DOOR",              # IsWarpDoor
    "MB_LADDER",
    "MB_UP_ESCALATOR", "MB_DOWN_ESCALATOR",
    "MB_NON_ANIMATED_DOOR", "MB_WATER_DOOR", "MB_DEEP_SOUTH_WARP",
    "MB_LAVARIDGE_GYM_B1F_WARP", "MB_LAVARIDGE_GYM_1F_WARP",
    "MB_AQUA_HIDEOUT_WARP", "MB_MT_PYRE_HOLE", "MB_MOSSDEEP_GYM_WARP",
    "MB_BRIDGE_OVER_OCEAN",          # IsUnionRoomWarp reuses this behaviour
    # IsArrowWarpMetatileBehavior
    "MB_NORTH_ARROW_WARP", "MB_STAIRS_OUTSIDE_ABANDONED_SHIP",
    "MB_SOUTH_ARROW_WARP", "MB_WATER_SOUTH_ARROW_WARP",
    "MB_SHOAL_CAVE_ENTRANCE",
    "MB_EAST_ARROW_WARP", "MB_WEST_ARROW_WARP",
    # IsDirectionalStairWarpMetatileBehavior
    "MB_UP_RIGHT_STAIR_WARP", "MB_UP_LEFT_STAIR_WARP",
    "MB_DOWN_RIGHT_STAIR_WARP", "MB_DOWN_LEFT_STAIR_WARP",
    # TryDoorWarp -> IsOpenSecretBaseDoor
    "MB_SECRET_BASE_SPOT_RED_CAVE_OPEN",
    "MB_SECRET_BASE_SPOT_BROWN_CAVE_OPEN",
    "MB_SECRET_BASE_SPOT_YELLOW_CAVE_OPEN",
    "MB_SECRET_BASE_SPOT_BLUE_CAVE_OPEN",
    "MB_SECRET_BASE_SPOT_TREE_LEFT_OPEN",
    "MB_SECRET_BASE_SPOT_TREE_RIGHT_OPEN",
    "MB_SECRET_BASE_SPOT_SHRUB_OPEN",
)

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
    mid-scene, e.g. `ch01.py` B5 handing a running autorun to B6) keeps
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
class Drain:
    """One script `Emulator.settle_field` drove to its release: the map it
    ran on (`map_location()`), every message it showed in order, and the bag
    (item id -> quantity) just before and just after. An arrival page's beat
    runs after the crossing that drained it, and reads this back to check
    what the page showed and granted (`generic_beat`, arrival pages)."""

    map_location: tuple[int, int]
    messages: tuple[str, ...]
    bag_before: dict[int, int]
    bag_after: dict[int, int]
    #: Every menu the drain answered: (answer, `gSpecialVar_Result` after,
    #: whether it was a yes/no box). Answer is the arm index (0 first, -1
    #: cancel), as `generic_beat(choice_answers=)` numbers them.
    menus: tuple[tuple[int, int, bool], ...] = ()


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
    #: that care (ch02.py's `_sight_lane_tiles`) only read it for objects
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


#: Control bytes (`include/constants/characters.h`), read out of the
#: TextPrinter's source buffer alongside literal glyph bytes.
_EOS = 0xFF
_CHAR_NEWLINE = 0xFE
_PLACEHOLDER_BEGIN = 0xFD
_EXT_CTRL_CODE_BEGIN = 0xFC
_CHAR_PROMPT_CLEAR = 0xFB  # waits for a button press, then clears -- page break
_CHAR_PROMPT_SCROLL = 0xFA  # waits for a button press, then scrolls -- line break

#: `EXT_CTRL_CODE_*` (characters.h) -> operand byte count, read directly out
#: of `RenderText`'s switch (`engine/src/text.c:1379-1535`): every opcode not
#: listed here is one this module has not verified an operand length for, and
#: decoding must fail loud rather than guess a length and silently desync the
#: rest of the string (CLAUDE.md §4.5).
_EXT_CTRL_OPERAND_LEN: dict[int, int] = {
    0x01: 1,  # COLOR
    0x02: 1,  # HIGHLIGHT
    0x03: 1,  # SHADOW
    0x04: 3,  # COLOR_HIGHLIGHT_SHADOW
    0x05: 1,  # PALETTE
    0x06: 1,  # FONT
    0x07: 0,  # RESET_FONT
    0x08: 1,  # PAUSE
    0x09: 0,  # PAUSE_UNTIL_PRESS
    0x0A: 0,  # WAIT_SE
    0x0B: 2,  # PLAY_BGM
    0x0C: 1,  # ESCAPE -- selects an extended-page glyph; that glyph isn't
              # rendered (this decoder only knows the first 256 charmap
              # bytes, matching engine_metrics), so the operand is consumed
              # and contributes no character, same as any other control code.
    0x0D: 1,  # SHIFT_RIGHT
    0x0E: 1,  # SHIFT_DOWN
    0x0F: 0,  # FILL_WINDOW
    0x10: 2,  # PLAY_SE
    0x11: 1,  # CLEAR
    0x12: 1,  # SKIP
    0x13: 1,  # CLEAR_TO
    0x14: 1,  # MIN_LETTER_SPACING
    0x15: 0,  # JPN
    0x16: 0,  # ENG
    0x17: 0,  # PAUSE_MUSIC
    0x18: 0,  # RESUME_MUSIC
    0x19: 1,  # SPEAKER
    0x1A: 1,  # ACCENT
    0x1B: 1,  # BACKGROUND
    0x1C: 3,  # TEXT_COLORS
}

#: `PLACEHOLDER_ID_*` (characters.h) -> a stable, comparable rendering for a
#: beat's expected-string literal. Field messages have already had these
#: resolved to real glyphs by `StringExpandPlaceholders` before printing
#: (`ShowFieldMessage`, field_message_box.c) -- reaching this table at all
#: means either a non-field-message printer (battle text etc., read via
#: `Emulator.active_printer_texts`) or an unresolved placeholder bug. An id
#: absent from this table renders as `{PLACEHOLDER_0x..}` rather than being
#: dropped, so an unrecognized placeholder is visible in the decoded string
#: instead of silently vanishing.
_PLACEHOLDER_TOKENS: dict[int, str] = {
    0x00: "{UNKNOWN}",
    0x01: "{PLAYER}",
    0x02: "{STR_VAR_1}",
    0x03: "{STR_VAR_2}",
    0x04: "{STR_VAR_3}",
    0x05: "{KUN}",
    0x06: "{RIVAL}",
    0x07: "{VERSION}",
    0x08: "{AQUA}",
    0x09: "{MAGMA}",
    0x0A: "{ARCHIE}",
    0x0B: "{MAXIE}",
    0x0C: "{KYOGRE}",
    0x0D: "{GROUDON}",
    0x0E: "{REGION}",
}

#: Cap on how many bytes `decode_text_bytes` will scan looking for `_EOS`
#: (`playtest/offsets.py`'s probe-first philosophy stops at struct layout;
#: this is a plain safety bound, not engine-derived) -- comfortably above
#: `gStringVar4`'s own 0x3E8-byte backing (`include/string_util.h`) is
#: unnecessary since no field message can legitimately exceed that buffer,
#: but this cap exists to stop a torn/garbage pointer from being read as an
#: unbounded string, not to match the buffer size exactly.
TEXT_DECODE_CAP = 512


def decode_text_bytes(data: bytes, byte_to_char: dict[int, str]) -> str:
    """Decode one pokeemerald source string out of already-fetched `data`.

    Pure and memory-free -- callers fetch a bounded byte range first (see
    `Emulator.current_field_message_text`) and hand it here, which is what
    makes this unit-testable without an emulator (`tests/test_playtest_text_
    read.py`).

    Terminates at `_EOS` (0xFF); raises `ScenarioError` if `data` runs out
    first (the bounded-read cap was hit with no terminator -- a torn pointer,
    not a real string). Control bytes render as stable, comparable tokens
    rather than being silently dropped, so a beat's expected-string assertion
    has something deterministic to compare against:

    - `_CHAR_NEWLINE` (0xFE) -> literal ``\\n`` (two characters: backslash,
      "n" -- matching Poryscript's own source-level escape, not an actual
      newline byte, so a decoded string reads the same as the `.pory` text
      an author would have written).
    - `_CHAR_PROMPT_SCROLL` (0xFA, "waits for a button press and scrolls") ->
      literal ``\\l``.
    - `_CHAR_PROMPT_CLEAR` (0xFB, "waits for a button press and clears") ->
      literal ``\\p``.
    - `_EXT_CTRL_CODE_BEGIN` (0xFC) -> zero-width; the opcode and its operand
      bytes are consumed and contribute nothing to the decoded string
      (matches `GetStringWidth`'s own zero-width treatment of these,
      `text_validator/engine_metrics.py`). An opcode absent from
      `_EXT_CTRL_OPERAND_LEN` raises rather than guessing an operand length.
    - `_PLACEHOLDER_BEGIN` (0xFD) -> a `{TOKEN}` string from
      `_PLACEHOLDER_TOKENS` (`{PLAYER}` etc.), or `{PLACEHOLDER_0x..}` for an
      id this module doesn't recognize.

    Any other byte absent from `byte_to_char` raises -- an unmapped glyph is
    reported, never silently dropped or substituted.
    """
    out: list[str] = []
    i = 0
    n = len(data)
    while True:
        if i >= n:
            raise ScenarioError(
                f"text decode: no EOS (0xFF) found within {n} bytes -- "
                "either raise the cap or this pointer is not a real string"
            )
        b = data[i]
        if b == _EOS:
            return "".join(out)
        if b == _CHAR_NEWLINE:
            out.append("\\n")
            i += 1
            continue
        if b == _CHAR_PROMPT_SCROLL:
            out.append("\\l")
            i += 1
            continue
        if b == _CHAR_PROMPT_CLEAR:
            out.append("\\p")
            i += 1
            continue
        if b == _EXT_CTRL_CODE_BEGIN:
            if i + 1 >= n:
                raise ScenarioError(
                    f"text decode: EXT_CTRL_CODE_BEGIN at offset {i} has no "
                    "opcode byte before the cap"
                )
            opcode = data[i + 1]
            operand_len = _EXT_CTRL_OPERAND_LEN.get(opcode)
            if operand_len is None:
                raise ScenarioError(
                    f"text decode: unrecognized EXT_CTRL_CODE_BEGIN opcode "
                    f"{opcode:#04x} at offset {i} -- operand length unknown, "
                    "refusing to guess"
                )
            i += 2 + operand_len
            continue
        if b == _PLACEHOLDER_BEGIN:
            if i + 1 >= n:
                raise ScenarioError(
                    f"text decode: PLACEHOLDER_BEGIN at offset {i} has no "
                    "id byte before the cap"
                )
            pid = data[i + 1]
            out.append(_PLACEHOLDER_TOKENS.get(pid, f"{{PLACEHOLDER_{pid:#04x}}}"))
            i += 2
            continue
        char = byte_to_char.get(b)
        if char is None:
            raise ScenarioError(
                f"text decode: byte {b:#04x} at offset {i} has no charmap "
                "entry -- unmapped glyph"
            )
        out.append(char)
        i += 1


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


class _MapGraphSource:
    """Lazily builds and caches the offline `MapGraph` (`rpg2gba.traversal`)
    for each Uranium map id `_plan_route` asks for.

    One `build_map_graph` call (a full decode-JSON parse) per map id for the
    lifetime of the `Emulator` -- not per search node, and not even once per
    `walk_to`, since a chapter walks the same map repeatedly. A callable
    rather than a dict so a test can inject a fake with the same call shape
    (`source(map_id) -> MapGraph`) without touching disk at all -- see
    `Emulator._map_graph_source`.
    """

    def __init__(
        self,
        maps_dir: Path | None = None,
        tilesets_json: Path | None = None,
        terrain_tag_map: Path | None = None,
    ) -> None:
        out = Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"
        self._maps_dir = maps_dir or (out / "maps")
        self._tilesets_json = tilesets_json or (out / "tilesets.json")
        self._terrain_tag_map = terrain_tag_map
        self._cache: dict[int, MapGraph] = {}

    def __call__(self, map_id: int) -> MapGraph:
        graph = self._cache.get(map_id)
        if graph is None:
            graph = build_map_graph(
                map_id,
                maps_dir=self._maps_dir,
                tilesets_json=self._tilesets_json,
                terrain_tag_map=self._terrain_tag_map,
            )
            self._cache[map_id] = graph
        return graph


_MAP_CONST_RE = re.compile(r"^\s*(MAP_[A-Z0-9_]+)\s*=", re.MULTILINE)


def _defined_map_constants(engine: Path) -> frozenset[str]:
    """Every `MAP_*` constant this build's headers declare.

    Read from `include/constants/map_groups.h`, which pokeemerald
    auto-generates from `data/maps/map_groups.json` -- so it names exactly
    the maps compiled into this ROM, vanilla and slice alike. Used to scope
    macro probes: the `MapConstantRegistry` is corpus-wide and will happily
    offer constants no slice build defines.
    """
    header = engine / "include" / "constants" / "map_groups.h"
    if not header.is_file():
        raise ScenarioError(
            f"_plan_route: {header} does not exist -- cannot tell which map "
            "constants this build defines (is --engine pointing at a built "
            "engine tree?)"
        )
    return frozenset(_MAP_CONST_RE.findall(header.read_text(encoding="utf-8")))


class _MapIdBridge:
    """Resolves a live `map_location()` (group, num) to the Uranium map id
    the offline `MapGraph` is keyed by, via the persisted
    `MapConstantRegistry` state -- the one source of truth for Uranium id ->
    `MAP_*` constant (CLAUDE.md §4.3, `tileset_converter/map_constants.py`)
    -- and the emulator's own `resolve_constant` for `MAP_GROUP()`/
    `MAP_NUM()` (same macro-probe pattern `assertions.at_map` uses).

    The whole minted-map table is resolved in ONE batched
    `resolve_constants` probe compile, the first time `resolve()` is called,
    and cached for the `Emulator`'s lifetime -- not a probe per map, and
    never a probe per search node. Failure to resolve is a `ScenarioError`,
    never a quiet `None`: a caller (`_plan_route`) that can't identify which
    map it's on has no static walkability to consult and must stop, not
    silently fall back to the live grid (that fallback is exactly the "two
    implementations of walkable" risk this bridge exists to close).
    """

    def __init__(self, emu: "Emulator", state_path: Path | None = None) -> None:
        self._emu = emu
        self._state_path = state_path or _DEFAULT_MAP_CONSTANTS_STATE
        self._table: dict[tuple[int, int], int] | None = None

    def resolve(self, group: int, num: int) -> int:
        if self._table is None:
            self._table = self._build_table()
        try:
            return self._table[(group, num)]
        except KeyError:
            raise ScenarioError(
                f"_plan_route: map_location() group={group} num={num} has no "
                f"minted Uranium map in the MapConstantRegistry state at "
                f"{self._state_path} -- cannot resolve the offline traversal "
                "graph for the current map"
            ) from None

    def _build_table(self) -> dict[tuple[int, int], int]:
        registry = MapConstantRegistry(self._state_path)
        registry.load()
        # The registry owns this reverse index (CLAUDE.md 4.3). This used to
        # walk the private `_by_id`, and `playtest/chapter.py` separately
        # hand-parsed the same persisted JSON -- two forks of one table,
        # promoted to `map_const_to_uranium_id` per Q6.
        by_const = registry.map_const_to_uranium_id()
        if not by_const:
            raise ScenarioError(
                f"_plan_route: MapConstantRegistry state at {self._state_path} "
                "has no minted maps -- cannot resolve the offline traversal "
                "graph for the current map"
            )
        # The registry is CORPUS-wide (every map the converter has minted a
        # constant for), but a slice build only DEFINES the maps it actually
        # builds -- `map_groups.h` is auto-generated from
        # `data/maps/map_groups.json`, so it is the authoritative list of
        # what this ROM's headers declare. Probing the full registry asks
        # gcc about ~180 constants this build does not have, and the whole
        # batched probe fails to compile, taking every map down with it
        # (`MAP_ROUTE_03` undeclared, and many more). Scope to the
        # intersection. Not a silent default: a map the player can stand on
        # is by definition built, and if one somehow is not, `resolve()`
        # still raises naming the group/num.
        built = _defined_map_constants(self._emu.engine)
        by_const = {c: uid for c, uid in by_const.items() if c in built}
        if not by_const:
            raise ScenarioError(
                f"_plan_route: no minted map constant in {self._state_path} "
                f"is defined by this build's map_groups.h ({len(built)} "
                "constants) -- the registry state and the engine build "
                "disagree about which maps exist"
            )

        names: list[str] = []
        for map_const in by_const:
            names.append(f"MAP_GROUP({map_const})")
            names.append(f"MAP_NUM({map_const})")
        resolved = self._emu.resolve_constants(names)
        table: dict[tuple[int, int], int] = {}
        for map_const, uid in by_const.items():
            g = resolved[f"MAP_GROUP({map_const})"]
            n = resolved[f"MAP_NUM({map_const})"]
            table[(g, n)] = uid
        return table


def _unwrap_message(text: str) -> str:
    """Collapse a decoded field message's line breaks so a substring check
    can span them.

    `decode_text` deliberately renders the break control codes as the
    LITERAL two-character sequences ``\\n`` (0xFE), ``\\l`` (0xFA) and
    ``\\p`` (0xFB) so a decoded string reads the same as the `.pory` source
    it came from. That is the right call for reading a failure message, but
    it means a raw `in` test compares across the break: CH04's B5 asserted
    "Nowtoch City" against a box reading "...roadblock, Nowtoch\\nCity may
    be reached..." and could never match, because the engine wrapped the
    line between the two words. The sign text was correct the whole time.

    Where the break falls is a *typesetting* detail -- it moves whenever the
    string, the font, or the box width changes -- so it must not be part of
    what a beat asserts. Breaks become single spaces and runs of whitespace
    collapse, on both sides of the comparison.

    BOTH comparison paths normalize. `exact=True` used to compare verbatim,
    breaks included, on the theory that a beat asking for equality wanted the
    typesetting too -- but its only caller is the trainer template's re-talk
    oracle, which is asserting what an NPC SAYS, and CH05's B3_retalk1 failed
    on nothing but a wrap: expected "...all my Pokemon fainted?..." against a
    box reading "...all my Pokemon\nfainted?...". Same string, same argument
    as B5's above. A beat that really does mean to pin the wrap says
    `verbatim=True` and says it on purpose.
    """
    for code in ("\\n", "\\l", "\\p"):
        text = text.replace(code, " ")
    return " ".join(text.split())


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
        # `Task_PokemonPicWindow` (script_menu.c): the task `showmonpic`'s
        # `ScriptMenu_ShowPokemonPic` creates, alive while the picture is up
        # (the starter selector's reveal, ruling 20). Same literal-pool trick.
        # The pool sits past the default span; its first code literal is the
        # task, the one `ScriptMenu_HidePokemonPic` also looks up (checked).
        self._monpic_task_fn = static_fn_via_literal_pool(
            engine / "pokeemerald.elf",
            self.symbols["ScriptMenu_ShowPokemonPic"], span=0xE0,
        )
        # Text-content decode (Emulator.current_field_message_text,
        # active_printer_texts) -- reuses text_validator.engine_metrics'
        # charmap.txt parser (one source of truth for the char<->byte table,
        # CLAUDE.md §4.3) rather than a second parser, then locally inverts
        # it; see `playtest.charmap` for why that inversion
        # can't be a blind dict-reverse.
        self._byte_to_char = invert_charmap_english_first(
            load_charmap(engine / "charmap.txt").char_to_byte
        )
        self._text_frame: "object | None" = None
        self._text_was_drawing = False
        self._frame_pinned = False
        #: Every field message that started drawing this boot, in order
        #: (`note_text_frame`), and every script `settle_field` drained.
        self.message_log: list[str] = []
        self._last_logged: str | None = None
        self.drains: list[Drain] = []
        #: map_location -> the answers still owed to menus drained on that
        #: map, in walk order (installed by the runner from the beats'
        #: `drain_answers`; `settle_field` consumes them).
        self.drain_answers: dict[tuple[int, int], list[int]] = {}
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
        # `_plan_route`'s static-walkability source (Q13 slice 2): a
        # callable `map_id -> MapGraph` and a `(group, num) -> map_id`
        # resolver, both lazily built and cached (see their classes'
        # docstrings). Public instance attributes, not name-mangled: a test
        # replaces either with a fake of the same call shape to inject a
        # synthetic graph without touching disk (`test_plan_route_graph.py`).
        self._map_graph_source = _MapGraphSource()
        self._map_id_bridge = _MapIdBridge(self)
        # Q13 slice 4. `_walk_path` is the tile sequence the walker
        # actually stood on since the last `clear_walk_path()` (the runner
        # clears it at every beat boundary), and it is what makes
        # planned-vs-observed comparable at all: `observed_beats/*.json`
        # used to hold enter/exit snapshots only -- two points per beat --
        # which cannot show that a walk crossed a trigger tile between
        # them. That is exactly what happened on CH04 B3, and the artifact
        # that would have shown it the first time is this list.
        self._walk_path: list[WalkedTile] = []
        # Q8's ledger (see `contradictions.py`). Public-ish instance
        # attribute so the runner can drain it into the run artifact and a
        # test can inspect it; nothing may branch on its contents.
        self.contradictions = ContradictionLedger()
        # The inherited beat currently running (`<owner>:<name>`), or None
        # for a beat the chapter under test owns. Set per beat by `runner`;
        # read only by `_walk_to_once`'s replay fallback, whose docstring
        # carries the rationale and the expiry.
        self.replay_beat: str | None = None
        # Q7's frame rule: how many times this beat explicitly pinned a
        # frame. `waypoint()` clears it, so it is per-beat exactly like
        # `_frame_pinned`.
        self._frames_marked = 0

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

    def write_u8(self, addr: int, value: int) -> None:
        # Same `raw_write` arity fix as `write_u16`/`write_u32`.
        self.core.memory.u8.raw_write(addr, value)

    def write_u16(self, addr: int, value: int) -> None:
        # Not `memory.u16[addr] = value`: that path in the mgba bindings
        # (site-packages/mgba/memory.py:60) calls `rawWrite16` without the
        # `segment` argument the C signature requires and dies with a cffi
        # arity TypeError. `raw_write` (:68) passes segment=-1 properly.
        self.core.memory.u16.raw_write(addr, value)

    def write_u32(self, addr: int, value: int) -> None:
        # Same `raw_write` arity fix as `write_u16`, for `set_money`.
        self.core.memory.u32.raw_write(addr, value)

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
        # Names are built from row ids, which carry slashes
        # (`map033/terrain/stairs/57,9`); one file, not a path (ROM run 51:
        # the save crashed and hid the stair beat's own failure).
        path = self.screenshot_dir / f"{name.replace('/', '_')}_f{self.frame}.png"
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
        drawing = self.text_showing()
        finished = self._text_was_drawing and not drawing
        started = drawing and not self._text_was_drawing
        self._text_was_drawing = drawing
        if started:
            # The transcript: `gStringVar4` holds the whole message from the
            # frame it starts drawing. A later page of the same message
            # re-raises the edge with the same text, so only a change logs
            # (two identical lines in a row log once).
            text = self.current_field_message_text()
            if text is not None and text != self._last_logged:
                self.message_log.append(text)
                self._last_logged = text
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
        # Q7's frame rule counts *explicit* pins, not the automatic
        # boundary waypoint every beat gets for free. The rule's whole
        # point is that a negative claim ("nothing runs") is only evidence
        # when someone chose the instant it is a claim about; the automatic
        # frame is taken after the beat returns, which is precisely the
        # wrong moment and is available to every beat regardless.
        self._frames_marked += 1
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
            self._frames_marked = 0
            return None
        frame = None if failed else self._text_frame
        self._text_frame = None
        self._frame_pinned = False
        # Per-beat, exactly like the pin: `waypoint` is the beat boundary.
        # The runner reads `frames_marked()` BEFORE calling this on a
        # failure, which is the only ordering that lets Q7's rule see what
        # the beat did.
        self._frames_marked = 0
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

    @property
    def sb2(self) -> int:
        return self.u32(self.symbols["gSaveBlock2Ptr"])

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

    def set_var(self, var: str | int, value: int) -> None:
        """Write a VAR_* value at the same address `var()` reads. Vars are
        NOT encrypted (unlike money/bag, which XOR against the save's
        encryption key -- see `_encryption_key`) -- a plain u16 write is
        correct here."""
        var_id = self.resolve_constant(var) if isinstance(var, str) else var
        vars_start = self.offsets["vars_start"]
        special_vars_start = self.resolve_constant("SPECIAL_VARS_START")
        if not (vars_start <= var_id < special_vars_start):
            raise ScenarioError(
                f"var id {var_id} is outside the stored-vars range "
                f"[{vars_start}, {special_vars_start}) — special/temp vars "
                "aren't writable via a flat offset"
            )
        addr = self.sb1 + self.offsets["off_sb1_vars"] + (var_id - vars_start) * 2
        self.write_u16(addr, value)

    def _encryption_key(self) -> int:
        """`gSaveBlock2Ptr->encryptionKey` -- both `money.c`'s GetMoney/
        SetMoney and `item.c`'s BagPocket_Get/SetSlotDataGeneric XOR their
        stored value against this before/after touching save state (see
        `money`/`set_money`/`bag_item_quantity`). Read fresh every call
        rather than cached -- nothing in this harness ever changes the key
        mid-scenario, but there is no primitive here that assumes it can't."""
        return self.u32(self.sb2 + self.offsets["off_sb2_encryptionkey"])

    def money(self) -> int:
        """The player's current money, decrypted exactly as `GetMoney`
        (`engine/src/money.c`) does: `SaveBlock1.money` is stored XOR'd
        against `gSaveBlock2Ptr->encryptionKey`, never plaintext -- a raw
        `u32` read here would be garbage."""
        raw = self.u32(self.sb1 + self.offsets["off_sb1_money"])
        return raw ^ self._encryption_key()

    def set_money(self, amount: int) -> None:
        """Write the player's money, encrypting it exactly as `SetMoney`
        (`engine/src/money.c`) does. Unlike `AddMoney`/`RemoveMoney`, this
        does not clamp to `MAX_MONEY` -- it is the same raw primitive those
        two are built on, so a caller that wants a scenario-only grant well
        past `MAX_MONEY` is not stopped by this call (it may still be
        stopped by whatever the game itself does with an out-of-range
        value, which is not this primitive's concern)."""
        addr = self.sb1 + self.offsets["off_sb1_money"]
        self.write_u32(addr, amount ^ self._encryption_key())

    #: `struct Bag`'s five pockets (`engine/include/global.h`), as
    #: (offset-into-Bag key, slot-count key) pairs for `bag_item_quantity`
    #: to scan. `POCKET_DUMMY` (PC storage, `gSaveBlock1Ptr->pcItems`) is
    #: deliberately absent -- it isn't part of `struct Bag` and its
    #: quantities aren't encrypted (`BagPocket_GetSlotDataPC`), a different
    #: primitive this module doesn't need yet.
    _BAG_POCKETS: tuple[tuple[str, str], ...] = (
        ("off_bag_items", "val_bag_items_count"),
        ("off_bag_keyitems", "val_bag_keyitems_count"),
        ("off_bag_pokeballs", "val_bag_pokeballs_count"),
        ("off_bag_tmshms", "val_bag_tmhm_count"),
        ("off_bag_berries", "val_bag_berries_count"),
    )

    def bag_item_quantity(self, item: str | int) -> int:
        """Total quantity of `item` (an `ITEM_*` constant name, or its
        already-resolved id) held in the bag -- mirrors
        `CountTotalItemQuantityInBag` (`engine/src/item.c`), reading
        `gSaveBlock1Ptr->bag` directly rather than through the
        `gBagPockets` runtime pointer view (same storage, one fewer
        indirection, and no dependency on `SetBagItemsPointers` having run
        this boot).

        Scans every pocket rather than resolving `item`'s own pocket via
        `GetItemPocket` first: `AddBagItem` only ever places an item in
        the one pocket its type maps to, so summing matches across all
        five pockets gives the same answer as looking the pocket up, with
        one fewer primitive to add. Quantities are stored XOR'd against
        the save's encryption key, same as money (`BagPocket_
        GetSlotDataGeneric`, `engine/src/item.c`) -- the raw `u16` is not
        the count.
        """
        item_id = self.resolve_constant(item) if isinstance(item, str) else item
        o = self.offsets
        key = self._encryption_key() & 0xFFFF
        bag_base = self.sb1 + o["off_sb1_bag"]
        stride = o["sizeof_itemslot"]
        total = 0
        for off_key, count_key in Emulator._BAG_POCKETS:
            pocket_base = bag_base + o[off_key]
            for i in range(o[count_key]):
                slot = pocket_base + i * stride
                if self.u16(slot + o["off_itemslot_itemid"]) != item_id:
                    continue
                total += self.u16(slot + o["off_itemslot_quantity"]) ^ key
        return total

    def bag_contents(self) -> dict[int, int]:
        """Every item in the bag: item id -> total quantity, read the same
        way as `bag_item_quantity` (all five pockets, decrypted)."""
        o = self.offsets
        key = self._encryption_key() & 0xFFFF
        bag_base = self.sb1 + o["off_sb1_bag"]
        stride = o["sizeof_itemslot"]
        out: dict[int, int] = {}
        for off_key, count_key in Emulator._BAG_POCKETS:
            pocket_base = bag_base + o[off_key]
            for i in range(o[count_key]):
                slot = pocket_base + i * stride
                item_id = self.u16(slot + o["off_itemslot_itemid"])
                if item_id == 0:
                    continue
                qty = self.u16(slot + o["off_itemslot_quantity"]) ^ key
                out[item_id] = out.get(item_id, 0) + qty
        return out

    def item_price(self, item: str | int) -> int:
        """`GetItemPrice` (`engine/src/item.c`): `gItemsInfo[item].price`.
        `gItemsInfo` is a plain `const` ROM table, not save state -- no
        encryption, no pointer indirection through a save block."""
        item_id = self.resolve_constant(item) if isinstance(item, str) else item
        o = self.offsets
        addr = (self.symbols["gItemsInfo"] + item_id * o["sizeof_iteminfo"]
                + o["off_iteminfo_price"])
        return self.u32(addr)

    #: `struct Song` (`engine/include/gba/m4a_internal.h`): a `SongHeader *`
    #: pointer followed by two `u16`s (`ms`/`me`) -- 4 + 2 + 2 = 8 bytes/entry,
    #: confirmed against that header rather than assumed.
    _SIZEOF_SONG = 8

    def bgm_song_id(self) -> int:
        """The `MUS_*` id of the song currently playing on the BGM music
        player (`gMPlayInfo_BGM`, `engine/include/gba/m4a_internal.h`'s
        `struct MusicPlayerInfo` -- `songHeader` is that struct's first
        field, so no offset lookup is needed to read it).

        `gSongTable` (same header: `extern const struct Song gSongTable[]`)
        is indexed by `MUS_*` id directly -- each `struct Song` is a
        `SongHeader *` followed by two `u16`s, confirmed against the struct
        definition rather than assumed a stride. This walks the table
        looking for the entry whose `header` pointer matches
        `gMPlayInfo_BGM->songHeader`, rather than trusting a caller-supplied
        id, so a `MUS_*` name can be verified against what is actually
        playing instead of just what was requested.

        Bounded by `LAST_PHONEME_SONG + 1` (`include/constants/songs.h`) --
        the last real id the table is defined over. Fails loud (CLAUDE.md
        §4.5) on a `songHeader` that matches no table entry, rather than
        returning a sentinel a caller could mistake for a real id.
        """
        header = self.u32(self.symbols["gMPlayInfo_BGM"])
        table = self.symbols["gSongTable"]
        count = self.resolve_constant("LAST_PHONEME_SONG") + 1
        for song_id in range(count):
            if self.u32(table + song_id * self._SIZEOF_SONG) == header:
                return song_id
        raise ScenarioError(
            f"bgm_song_id: gMPlayInfo_BGM.songHeader ({header:#010x}) "
            f"matches no entry in gSongTable[0:{count}] -- no MUS_* id "
            f"resolves to the song actually playing"
        )

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

    def _task_active(self, fn: int) -> bool:
        """`FuncIsActiveTask(fn)` over `gTasks`."""
        o = self.offsets
        base = self.symbols["gTasks"]
        for i in range(o["val_num_tasks"]):
            task = base + i * o["sizeof_task"]
            if self.u8(task + o["off_task_is_active"]) and \
                    self.u32(task + o["off_task_func"]) == fn:
                return True
        return False

    def monpic_up(self) -> bool:
        """True while a `showmonpic` picture window is on screen."""
        return self._task_active(self._monpic_task_fn)

    @functools.cached_property
    def _mart_layout(self) -> tuple[int, int, int]:
        """`symbols.mart_info_layout` for this build (ruling 20)."""
        return mart_info_layout(self.engine / "pokeemerald.elf",
                                self.symbols["CreatePokemartMenu"])

    def mart_items(self) -> list[int]:
        """The item ids the last-opened mart is selling (`sMartInfo`)."""
        anchor, list_off, count_off = self._mart_layout
        ptr = self.u32(anchor + list_off)
        if ptr == 0:
            return []
        return [self.u16(ptr + 2 * i) for i in range(self.u16(anchor + count_off))]

    def clear_mart_items(self) -> None:
        """Zero `sMartInfo`'s item list, so a mart opening afterwards is
        visible as the pointer being set again."""
        anchor, list_off, _ = self._mart_layout
        self.write_u32(anchor + list_off, 0)

    def match_call_registered(self, trainer: str | int) -> bool:
        """`register_matchcall`'s effect: `SetMatchCallRegisteredFlag`
        (pokenav_match_call_data.c) sets TRAINER_REGISTERED_FLAGS_START + the
        trainer's `gRematchTable` row (the row whose first id is the trainer).
        Fails loud for a trainer with no rematch row."""
        trainer_id = self.resolve_constant(trainer) if isinstance(trainer, str) else trainer
        o = self.offsets
        table = self.symbols["gRematchTable"]
        for row in range(o["val_rematch_table_entries"]):
            if self.u16(table + row * o["sizeof_rematchtrainer"]) == trainer_id:
                return self.flag(o["val_trainer_registered_flags_start"] + row)
        raise ScenarioError(f"trainer {trainer!r} has no gRematchTable row")

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

    def current_field_message_text(self) -> str | None:
        r"""The field message box's (window 0) full decoded source text, or
        `None` while no message box is up.

        Reads `gStringVar4` (`include/string_util.h`), not the printer's own
        `currentChar` -- deliberately, and not what
        `PLAYTEST_AUTHORING_IMPROVEMENT.md` §4.1 literally suggested.
        `ShowFieldMessage` (`field_message_box.c`) expands placeholders into
        `gStringVar4` once, before any printer exists, and printing only
        *reads* that buffer -- it never mutates it, only the printer's
        cursor into it. Two problems with `currentChar` instead, both fatal
        for this method's job:

        - It moves. `text.c`'s `RenderText` advances `currentChar` a byte (or
          control code) at a time as it draws, so by the time a page is
          fully drawn -- the moment worth reading -- `currentChar` points
          at whatever is left to print (the next page, or past-the-end),
          never at byte 0 of what's on screen.
        - It can not exist. `text_ready()`'s own docstring: a *final* page's
          printer is freed at `RENDER_FINISH`, right as the box "stays up
          ... holding the finished text" -- the single most reviewable
          frame there is, and precisely the frame with no printer node left
          to walk to.

        `gStringVar4` has neither problem: it is written once per message
        (all pages, already placeholder-expanded) and stays valid for as
        long as the box stays up, independent of printer lifecycle. This
        also means a multi-page message decodes in full regardless of which
        page is currently on screen -- useful for "which of several
        responses did the player get" (the CH04 self-switch A/B rematch
        case this primitive exists for), not just the page in front of you.

        Bounded read: fetches at most `TEXT_DECODE_CAP` bytes and raises
        (via `decode_text_bytes`) if no terminator turns up in that span,
        rather than following the pointer for an unbounded distance.

        **This does NOT gate on `sFieldMessageBoxMode` (`_msgbox_addr`), and
        must not** -- that byte answers "is a draw task still running", not
        "is a box on screen". `Task_DrawFieldMessage` clears it to
        FIELD_MESSAGE_BOX_HIDDEN the moment `RunTextPrintersRetIsActive`
        goes false, while the window stays drawn holding the finished text;
        `text_showing`'s own docstring says exactly this, and gating on it
        here contradicted that. Measured on ROM `b246127d` (2026-08-27),
        Route 2's B9 sign: mode reads 2 for frames 6-18, then 0 from frame
        24 through 240 with the box plainly on screen the whole time, while
        `gStringVar4` holds the correct text for all 240 frames. The gate
        made the read a race against message LENGTH -- B5's two-line sign
        (which ends on a `\l` pause, so its draw task never finishes) passed
        for the same reason B9's one-liner failed, which is luck, not a
        check.

        Freshness comes from `clear_field_message` instead: `interact` wipes
        the buffer before pressing A, and `advance_dialog` wipes it once the
        script releases, so text found here provably belongs to the action
        that just ran rather than to whatever spoke last.
        """
        addr = self.symbols["gStringVar4"]
        data = self.read_bytes(addr, TEXT_DECODE_CAP)
        text = decode_text_bytes(data, self._byte_to_char)
        return text or None

    def clear_field_message(self) -> None:
        """Wipe `gStringVar4` so a later `current_field_message_text` can
        only return text some later action actually produced.

        `gStringVar4` is written once per message and then left alone -- it
        stays valid long after its box is dismissed, which is what makes it
        the right buffer to READ (see `current_field_message_text`) and the
        reason a read needs an explicit freshness discipline rather than a
        liveness flag. Writing the terminator (0xFF) at byte 0 decodes as
        the empty string, which that method reports as `None`.
        """
        self.write_u16(self.symbols["gStringVar4"], 0xFFFF)
        self._last_logged = None

    _DISMISS_SETTLE_FRAMES = 10

    def dismiss_message(self, max_taps: int = 64) -> None:
        """Press A through every remaining page of the message on screen,
        then once more to dismiss its last page -- and no further.

        One tap is not "next message": `format()` wraps a long line onto a
        second page, and a single A only turns to it (2026-09-27: Map048's
        TV news line left the next `msgbox` unopened and the beat read
        None). `text_showing` stays true until the final page's last glyph
        lands, so tapping while it holds walks the pages, and the one tap
        after dismisses the box. Stopping there matters: a menu opening next
        would take a further A as its answer.
        """
        for _ in range(max_taps):
            if not self.text_showing():
                # The last glyph has landed, but `waitbuttonpress` only
                # starts on a later script tick and reads a NEW press; an A
                # already down by then is ignored (Auntie's third box stayed
                # up in the 2026-09-27 run). Let it get there first.
                self.run(self._DISMISS_SETTLE_FRAMES)
                self.tap("A")
                return
            self.tap("A")
        shot = self.screenshot("dismiss_message_stuck")
        raise ScenarioError(
            f"dismiss_message: the message box was still drawing after {max_taps} "
            f"A presses ({shot})")

    def active_printer_texts(self) -> dict[int, str]:
        """`window_id -> decoded text` for every live `WINDOW_TEXT_PRINTER`
        node on `sFirstTextPrinter`, covering windows besides the field
        message box (battle text, signposts, menus -- anything with its own
        printer).

        Unlike `current_field_message_text`, this reads each printer's own
        `currentChar` -- there is no equivalent of `gStringVar4` known to be
        stable for every window, so this is the best available source, and
        it is the **remaining** text from the printer's current read
        position onward, not the whole message from its start (see
        `current_field_message_text`'s docstring for why that distinction
        matters). For window 0 prefer `current_field_message_text`; this
        method exists for the other windows, and for enumerating everything
        that's live at once.

        Same 16-node cap as `text_ready` -- guards a torn-pointer cycle, not
        a real list length -- and the same bounded per-string read.
        """
        o = self.offsets
        node = self.u32(self._printer_list)
        result: dict[int, str] = {}
        for _ in range(16):
            if node == 0:
                break
            if self.u8(node + o["off_printer_type"]) == o["val_window_text_printer"]:
                window_id = self.u8(node + o["off_printer_window_id"])
                char_ptr = self.u32(node + o["off_printer_currentchar"])
                data = self.read_bytes(char_ptr, TEXT_DECODE_CAP)
                result[window_id] = decode_text_bytes(data, self._byte_to_char)
            node = self.u32(node + o["off_printer_next"])
        return result

    def wait_for_field_message(self, frame_budget: int = 180) -> str | None:
        """The field message box's decoded text, waiting up to `frame_budget`
        frames for a box to appear if none is up yet.

        `interact()` returns as soon as a script has taken the field controls
        (30 frames), which is NOT the same instant its first `msgbox` has
        rendered -- how long the gap is depends on what the script does
        first. Route 2's B9 sign (`Map035_EV002_Page1`) is the case that
        exposed this: its converted script runs `lock / faceplayer /
        setflag(FLAG_MENU_ON_EVENT) / lock` before `msgbox`, where B5's
        otherwise-identical sign (`Map035_EV013_Page1`) runs just `lock /
        faceplayer`. Sampling the box once, as `assert_text_contains` used
        to, failed B9 with `actual text was None` while the script was still
        working -- a false failure that says nothing about the content it
        was meant to check.

        Returns immediately when a box is already up, so beats that assert
        against an open box are unaffected; returns `None` if the budget
        runs out, leaving the caller to fail loud with its own diagnosis.
        """
        text = self.current_field_message_text()
        spent = 0
        while text is None and spent < frame_budget:
            self.run(6)
            spent += 6
            text = self.current_field_message_text()
        return text

    def assert_text_contains(self, expected: str, *, exact: bool = False,
                              verbatim: bool = False) -> None:
        """Assert the field message box currently shows `expected`.

        `exact=False` (default) checks substring containment -- the common
        case, since a checked phrase is usually shorter than its surrounding
        sentence. `exact=True` requires the whole decoded message (all
        pages) to equal `expected`.

        Both paths compare through `_unwrap_message`, so where the engine
        wrapped a line is not part of what is asserted -- it moves whenever
        the string, the font or the box width changes. `verbatim=True` (only
        meaningful with `exact=True`) turns that off for a beat that really
        is pinning the typesetting.

        Raises `ScenarioError` printing both `expected` and the actual
        decoded text on failure -- PLAYTEST_AUTHORING_IMPROVEMENT.md's
        complaint about a beat failure that doesn't show what actually
        happened costing a full debug cycle applies just as much here as it
        did to the proxy-oracle findings that document is about.
        """
        actual = self.wait_for_field_message()
        if exact and verbatim:
            ok = actual == expected
        elif exact:
            ok = (actual is not None
                  and _unwrap_message(actual) == _unwrap_message(expected))
        else:
            ok = (actual is not None
                  and _unwrap_message(expected) in _unwrap_message(actual))
        if not ok:
            verb = "equal" if exact else "contain"
            raise ScenarioError(
                f"expected field message text to {verb} {expected!r}; "
                f"actual text was {actual!r}"
            )

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
        # A sub-step press turns in place without moving -- but only when it
        # IS a turn: pressing the way the player already faces starts a step
        # at once. ROM run 45: the walk to the lab heal machine's west side
        # ended facing it, and "facing" it stepped onto the event's cell.
        player = self.object_event(self.resolve_constant("LOCALID_PLAYER"))
        if player.facing == direction:
            return
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

    def _warp_event_tiles(self) -> set[tuple[int, int]]:
        """Map-relative coordinates of every entry in the current map's warp
        event table, unfiltered -- including the ones that cannot fire.

        Callers that want the planner's hazard set want `_warp_tiles`, which
        is this minus the inert entries. This is the raw table, split out so
        the filter has something to filter and so a diagnosis can show both.
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

    def _warp_tiles(self) -> set[tuple[int, int]]:
        """Map-relative coordinates of the warp events that can actually
        WARP the player -- the planner's hazard set.

        A route must never *enter* one it wasn't aimed at: stepping on a live
        warp relocates the scenario to another map, which is the one walk
        failure mode that corrupts every assertion after it rather than
        failing.

        But the warp table is not the hazard list. The engine fires a warp
        only when a warp event and a warp-triggering metatile behaviour agree
        (`_WARP_TRIGGER_BEHAVIORS`), and the converter emits arrival warps on
        plain floor by design, so on any map reachable by a warp the raw table
        over-reports. Taking the table at face value blocked Route 01's
        (15,7)/(16,7) Kevlar arrivals and made B17's own target unreachable --
        latent since 2026-07-27, invisible until `_route_waypoints` stopped
        degrading to an unprotected greedy walk (f705b642).

        The degrade is deliberately in the OTHER direction from
        `_grass_cost_context`'s. If the behaviour of a tile cannot be read --
        no attribute pointer chain, a coordinate outside the loaded grid, a
        fake emulator that predates the primitive -- that tile stays in the
        hazard set. An unreadable behaviour must not quietly unblock a real
        door; over-avoiding costs a detour or a loud `RoutePlanningError`,
        under-avoiding walks the run onto another map.
        """
        coords = self._warp_event_tiles()
        if not coords:
            return set()
        try:
            ctx = self._grass_cost_context()
            if ctx is None:
                raise ScenarioError("no metatile-attribute pointer chain")
            triggers = set(self.resolve_constants(_WARP_TRIGGER_BEHAVIORS).values())
            width, _height, blocks = self._map_grid()
            off = self.offsets["val_map_offset"]
        except Exception:
            logger.info(
                "_warp_tiles: could not resolve metatile behaviours, treating "
                "all %d warp events as hazards", len(coords), exc_info=True)
            return coords

        live: set[tuple[int, int]] = set()
        inert: set[tuple[int, int]] = set()
        for x, y in coords:
            try:
                behavior = self._metatile_behavior(x, y, ctx, blocks, width, off)
            except Exception:
                live.add((x, y))
                continue
            (live if behavior in triggers else inert).add((x, y))
        if inert:
            logger.debug(
                "_warp_tiles: %d of %d warp events on this map sit on "
                "non-warping metatiles and are not avoided: %s",
                len(inert), len(coords), sorted(inert))
        return live

    def _metatile_behavior(self, x: int, y: int, ctx: dict,
                           blocks: tuple[int, ...], width: int,
                           off: int) -> int:
        """The behaviour byte of the metatile at map-relative `(x, y)`.

        Follows the engine's own `GetAttributeByMetatileIdAndMapLayout`
        (`engine/src/fieldmap.c`): mask the grid word down to a metatile id,
        index the primary or secondary tileset's `metatileAttributes` by it,
        and mask the packed `u16` for the behaviour. `ctx` is one
        `_grass_cost_context` result, hoisted by the caller so a per-node
        search loop doesn't re-walk the pointer chain.

        Raises (`IndexError`) for a coordinate outside the loaded grid rather
        than returning a behaviour read off some other tile's word.
        """
        idx = (x + off) + width * (y + off)
        if not (0 <= idx < len(blocks)):
            raise IndexError(f"({x},{y}) is outside the loaded map grid")
        metatile_id = blocks[idx] & ctx["metatile_id_mask"]
        if metatile_id < ctx["num_primary"]:
            addr = ctx["primary_attrs"] + metatile_id * 2
        else:
            addr = ctx["secondary_attrs"] + (metatile_id - ctx["num_primary"]) * 2
        return self.u16(addr) & ctx["behavior_mask"]

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
        whole route-planning machinery (e.g. ch02.py's
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

    # -- walked path (Q13 slice 4) -----------------------------------------

    def _record_walk_tile(self, x: int, y: int) -> None:
        """Append one tile the player actually stood on.

        Called once per step attempt from `_walk_greedy`, at the point it
        reads `player_pos()` -- which is also the point the arrival tile is
        read, so a completed walk's final tile is in the path too.

        **Consecutive duplicates are dropped**, because the walker reads
        its position again after a blocked step, after a sidestep it then
        undoes, and after the arrival settle. Recording those would turn a
        12-tile walk into 40 rows saying the same thing, and the question
        the path exists to answer -- "which tiles did this beat touch" --
        does not care how many frames were spent on each.

        **A tile whose map cannot be resolved is still recorded**, with
        `map_id=None` and a one-time contradiction, rather than dropped: an
        uncompared tile that is silently absent is indistinguishable from a
        compared-and-clean one, which is the silent-default failure §4.5
        exists to forbid.

        This must never raise. It is instrumentation running inside a walk
        that is doing real work; a failure to observe the walk is not a
        reason to fail the walk. `map_location()` on a mid-warp frame and
        `_map_id_bridge` on an unminted map are both expected, and both
        resolve to "record what we know, note what we don't".
        """
        try:
            group, num = self.map_location()
        except Exception:  # noqa: BLE001 - instrumentation never fails a walk
            logger.debug("_record_walk_tile: map_location() unreadable at "
                         "(%s, %s); tile not recorded", x, y)
            return
        prev = self._walk_path[-1] if self._walk_path else None
        if (prev is not None and prev.x == x and prev.y == y
                and prev.map_group == group and prev.map_num == num):
            return
        try:
            map_id: int | None = self._map_id_bridge.resolve(group, num)
        except ScenarioError:
            map_id = None
            self.contradictions.record(Contradiction(
                kind=KIND_UNRESOLVED_MAP,
                beat="",
                detail=(f"walked map_location() group={group} num={num} "
                        "resolves to no minted Uranium map, so no tile on "
                        "it can be compared against a route plan"),
                model="a minted Uranium map for every walkable location",
                measurement=f"group={group} num={num} is absent from the "
                            "MapConstantRegistry state",
                assumption="the tiles on this map are left uncompared",
            ))
        self._walk_path.append(
            WalkedTile(map_id=map_id, map_group=group, map_num=num, x=x, y=y))

    def walk_path(self) -> tuple[WalkedTile, ...]:
        """The tiles walked since the last `clear_walk_path()`."""
        return tuple(self._walk_path)

    def frames_marked(self) -> int:
        """Explicit `mark_frame()` calls since the last beat boundary (Q7)."""
        return self._frames_marked

    def map_graph(self, map_id: int) -> MapGraph:
        """The offline `MapGraph` for an arbitrary map id, cached.

        `_current_map_graph` answers "the map I am standing on"; slice 4's
        walked-path comparison needs graphs for every map a beat's path
        touched, which after a warp is more than one. Same source, same
        cache -- this exists so the runner asks through a named method
        rather than reaching into `_map_graph_source`."""
        return self._map_graph_source(map_id)

    def clear_walk_path(self) -> None:
        """Start a fresh path. The runner calls this at each beat boundary."""
        self._walk_path.clear()

    def _current_map_graph(self) -> MapGraph:
        """The offline `MapGraph` (`rpg2gba.traversal`) for whatever map
        `map_location()` currently reads.

        This is `_plan_route`'s bridge from a live runtime location to the
        offline graph's Uranium map id: resolve (group, num) via
        `_map_id_bridge`, then hand that id to `_map_graph_source`. Both are
        cached (per-bridge, per-map-id respectively; see their classes), so
        this costs nothing beyond a dict lookup after the first call for a
        given map.

        Deliberately has NO except clause of its own: a resolution failure
        (unminted map, missing/unbuildable decoded data) is a
        `ScenarioError` that propagates -- `_plan_route` must not plan on
        stale or absent static walkability. The lightweight test fakes that
        predate this method (`test_plan_route_objects.py`'s
        `_FakeRouteEmu`, `test_playtest.py`'s `_FakeWalkEmu`/`_FakeGridEmu`)
        simply don't define it, so the attribute lookup itself raises
        `AttributeError` -- `_plan_route` binds this method inside a `try`
        and calls it OUTSIDE, so only the missing-attribute case degrades to
        the old live-grid-only behaviour. An `AttributeError` raised while
        this method actually runs propagates loud; it must never be mistaken
        for "this fake has no graph".
        """
        group, num = self.map_location()
        map_id = self._map_id_bridge.resolve(group, num)
        return self._map_graph_source(map_id)

    def _plan_route(self, start: tuple[int, int],
                    goal: tuple[int, int]) -> list[tuple[int, int]] | None:
        """Least-cost walkable route between two map-relative tiles, or
        None.

        Static walkability -- collision, staircases, one-way ledges -- comes
        from the offline `MapGraph` for the current map (`_current_map_graph`,
        `rpg2gba.traversal`), not a re-derivation over the live
        `gBackupMapLayout` snapshot: PLAYTEST_AUTHORING_IMPROVEMENT_V2.md
        Q13 decision 2, closing the "two implementations of walkable" risk
        by construction. The live collision grid is still read (it must be,
        for bounds and for the divergence check below) but no longer
        decides which tiles are walkable; search proceeds over
        `MapGraph.neighbors()` edges, so stair-diagonal displacements and
        one-way ledge jumps are real graph edges here, not tile-adjacency
        guesses.

        Dynamic overlays the offline graph cannot know about stay live and
        are unchanged: warp tiles other than the goal, and tiles held by
        active object events (NPCs, item balls, solid Rock events on
        Route 1) other than the player's own object and the goal tile (see
        `_occupied_object_tiles`). Elevation is deliberately not modelled by
        the offline graph either (`MapGraph.elevation_modelled` is always
        False -- the decoded corpus carries no real height field, see
        `traversal.graph`'s module docstring); a leg that hits a
        mismatched-elevation edge gets locally stuck and re-planned, and
        ultimately fails loud, same as before.

        Tall grass (`MB_TALL_GRASS`, via `_grass_cost_context`) costs
        `_GRASS_TRAVERSAL_COST` instead of the usual 1, so a route prefers a
        reasonable clear detour over a field but still crosses it when
        that's the only way through -- including when grass IS the
        destination (B4 deliberately walks onto grass cells; Flood himself
        stands in one). Cost only ever biases which route is chosen among
        walkable ones; it is never a reachability gate. If the behavior
        pointer chain can't be resolved, every tile costs 1.

        Object events are a snapshot taken once per call, not re-read per
        search node: a patrolling NPC can make a planned route stale the
        moment it steps, which is exactly what `walk_to`'s stuck/step-aside
        retry and re-plan loop exists to absorb -- this is an optimisation
        to avoid the common body-block case, not a replacement for that
        recovery path.

        Sideways staircases (`GetSidewaysStairsCollision` in
        `engine/src/event_object_movement.c`, `GetRightSideStairsDirection`
        in `engine/src/field_player_avatar.c`) ARE now modelled and
        plannable: `MapGraph` represents an EAST/WEST press on a stair cell
        as the engine's own diagonal displacement (`Edge.kind ==
        "stair_diagonal"`), so a route across one can come out of this
        search. Ledge jumps are likewise real edges (one-way, landing two
        tiles past the ledge). What is still NOT modelled, by the offline
        graph itself: elevation (see above) -- a cliff-rim edge is still
        planned straight through it.

        Every static-walkability verdict the search actually consults is
        also checked against the live collision grid; a mismatch is logged
        at WARNING (map, cell, both verdicts) and NOT acted on -- a carried,
        non-blocking contradiction per Q13.1 (the offline graph can be wrong
        about the real engine; this is the evidence trail, not a gate). The
        chosen route always follows the offline graph's verdict.

        `_current_map_graph` raising `AttributeError` (the lightweight test
        fakes that predate the offline graph, e.g. `test_plan_route_objects.
        py`'s `_FakeRouteEmu`) degrades to the OLD plain 4-neighbour,
        live-grid-only search -- same AttributeError-degrade shape already
        used for `_grass_cost_context`. Any other failure resolving or
        building the graph (`ScenarioError` from `_map_id_bridge`/
        `_map_graph_source`) propagates: there is no silent fallback to
        live-grid-only walkability for a real `Emulator` that simply
        couldn't resolve its map.

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

        # Offline graph (Q13 decision 2). The degrade is scoped to the
        # ATTRIBUTE LOOKUP alone -- the fakes that predate this primitive
        # simply don't define the method. Binding first and calling outside
        # the `try` is deliberate: `_current_map_graph` resolves constants,
        # reads decoded JSON and builds a graph, and wrapping that whole
        # call would let a genuine `AttributeError` raised deep inside it
        # degrade this planner to live-grid walkability silently -- the
        # two-implementations bug this change exists to remove, in the
        # silent-wrong-answer shape CLAUDE.md §4.5/§11 forbid outright.
        try:
            current_map_graph = self._current_map_graph
        except AttributeError:
            graph = None
        else:
            graph = current_map_graph()

        # Q8's ledger, same fake-degrade shape: a fake emulator carrying an
        # injected graph (`test_plan_route_graph.py`) has no ledger, and a
        # findings record with nowhere to go is discarded rather than
        # crashing a planner test. Real `Emulator`s always have one.
        try:
            contradictions = self.contradictions
        except AttributeError:
            contradictions = ContradictionLedger()

        def live_walkable(x: int, y: int) -> bool:
            return _collision_walkable(blocks, width, off, map_w, map_h, x, y)

        def dynamic_blocked(cell: tuple[int, int]) -> bool:
            return cell in avoid or cell in occupied

        def log_divergence(cell: tuple[int, int]) -> None:
            """Record (never act on) a graph/live-grid disagreement about
            one cell the search actually looked at -- Q13.1's carried,
            non-blocking contradiction."""
            static = graph.is_walkable(cell)
            live = live_walkable(*cell)
            if static != live:
                # Slice 4: this used to be a bare `logger.warning`, which is
                # the "carried by someone remembering to read the log"
                # shape §1.5 disqualifies -- it never reached the artifact,
                # the viewer, or the gate stamp. The ledger carries it into
                # `observed_beats/<chapter>.json` instead, and it is also
                # the whole of Q7's conformance number: a live harness read
                # measured against the offline graph, the one oracle that
                # is not the harness itself.
                contradictions.record(Contradiction(
                    kind=KIND_WALKABILITY,
                    beat="",
                    detail=(f"map {graph.map_id} cell {cell}: offline graph "
                            f"walkable={static}, live collision grid "
                            f"walkable={live}"),
                    model=f"walkable={static}",
                    measurement=f"walkable={live}",
                    assumption="the offline graph's verdict was used for "
                               "planning",
                    map_id=graph.map_id,
                    cell=cell,
                ))

        def walkable(x: int, y: int) -> bool:
            """Plain live-grid walkability, only used on the no-graph
            (fake-emulator) degrade path."""
            if dynamic_blocked((x, y)):
                return False
            return live_walkable(x, y)

        def is_grass(x: int, y: int) -> bool:
            if grass_ctx is None:
                return False
            key = (x, y)
            cached = grass_cache.get(key)
            if cached is not None:
                return cached
            try:
                behavior = self._metatile_behavior(
                    x, y, grass_ctx, blocks, width, off)
            except IndexError:
                # Grass is a COST, never a gate (see this method's docstring),
                # so an out-of-grid cell prices as plain ground rather than
                # failing the plan. `_warp_tiles` degrades the other way on
                # the same error, because there it gates.
                behavior = -1
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

            if graph is not None:
                cx, cy = cur
                for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                    neighbor = (cx + dx, cy + dy)
                    if 0 <= neighbor[0] < map_w and 0 <= neighbor[1] < map_h:
                        log_divergence(neighbor)
                for edge in graph.neighbors(cur):
                    nxt = edge.target
                    if dynamic_blocked(nxt):
                        continue
                    nd = d + step_cost(*nxt)
                    if nd < dist.get(nxt, float("inf")):
                        dist[nxt] = nd
                        prev[nxt] = cur
                        heapq.heappush(heap, (nd, nxt))
                continue

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

    def _diagnose_unroutable(self, start: tuple[int, int],
                             goal: tuple[int, int]) -> str:
        """Why `_plan_route` found nothing, in the message itself.

        A bare "no route" sends the reader back to the emulator to work out
        which of several very different causes it was. The offline graph can
        separate them cheaply, and the distinction that matters most is
        PERMANENT vs TRANSIENT: if the graph says the goal is unreachable
        from `start` on static terrain alone, waiting will never help and the
        beat's coordinate or the chapter's route is wrong; if the graph says
        it IS reachable, then a dynamic obstacle (an NPC, an item ball, a
        Route 1 rock) is what blocked planning, and that is the case
        `walk_to`'s re-plan loop exists to absorb.

        Best-effort by construction: this runs on the failure path, so it
        must never raise and mask the failure it is describing. Anything it
        cannot determine is reported as unknown rather than guessed.
        """
        bits = [f"walk_to{goal}: no route from {start}"]
        try:
            bits.append(f"map={self.map_location()}")
        except Exception:  # noqa: BLE001 - diagnosis must not mask the failure
            bits.append("map=unknown")

        graph = None
        try:
            current_map_graph = self._current_map_graph
        except AttributeError:
            bits.append("offline graph: unavailable")
        else:
            try:
                graph = current_map_graph()
            except Exception as exc:  # noqa: BLE001 - see docstring
                bits.append(f"offline graph: unavailable ({exc})")

        if graph is not None:
            if not graph.is_walkable(goal):
                bits.append(
                    f"PERMANENT: the offline graph says {goal} is not a "
                    "walkable cell at all -- the declared coordinate is "
                    "wrong, or it is terrain the graph models as blocked")
            elif goal not in graph.reachable_from(start):
                bits.append(
                    f"PERMANENT: {goal} is walkable but NOT reachable from "
                    f"{start} on static terrain -- they are in different "
                    "connected components, so no amount of waiting helps "
                    "(a sealed room, or a capability-gated route)")
            else:
                bits.append(
                    f"TRANSIENT: the offline graph reaches {goal} from "
                    f"{start} on static terrain, so something in the "
                    "planner's avoid-set closed the route")

        # Both halves of the avoid-set, always, and neither named as the
        # cause. This message used to assert "an object event standing on
        # the only corridor, most likely" and then print object tiles alone,
        # while the avoid-set is warps UNION objects. On CH02's B17 the
        # objects were innocent and two inert warp tiles were the blocker,
        # and the templated guess sent two investigations the wrong way. A
        # diagnosis that runs on the failure path may report what it sees;
        # it may not pick a winner it never tested (CLAUDE.md 4.5).
        try:
            warps = self._warp_tiles()
        except Exception:  # noqa: BLE001 - see docstring
            bits.append("avoided warp tiles: unknown")
        else:
            shown = ", ".join(str(c) for c in sorted(warps))
            bits.append(f"avoided warp tiles: {shown or 'none'}")

        try:
            occupied = self._occupied_object_tiles(goal)
        except Exception:  # noqa: BLE001 - see docstring
            bits.append("object-held tiles: unknown")
        else:
            blockers = sorted(occupied)
            if not blockers:
                bits.append("object-held tiles: none")
            if blockers:
                shown = ", ".join(str(c) for c in blockers[:8])
                more = "" if len(blockers) <= 8 else f" (+{len(blockers) - 8} more)"
                bits.append(f"object-held tiles: {shown}{more}")

        return "; ".join(bits)

    def _route_waypoints(self, tx: int, ty: int) -> list[tuple[int, int]]:
        """Turn a planned route into the corner tiles `_walk_greedy` can
        reach in a straight line, ending at the target.

        A planning failure RAISES `RoutePlanningError`. It used to log a
        warning and return the bare target, handing the leg to `_walk_greedy`
        with none of the planner's avoid-set, on the stated rationale that
        "an ordinary planner blind spot costs a slower failure rather than a
        wrong answer". CH04's B3 refutes that directly: the unprotected
        greedy walk crossed Timothy's event-touch tile, the wrong trainer was
        fought, and both guards passed. It was a wrong answer, not a slow
        failure, and a silent fallback is a standing CLAUDE.md 4.5/11
        violation regardless.

        This is not interim code and slice 1 does not remove the need for it:
        the offline graph changes where walkability comes from, but planning
        can still fail -- occlusion, an unmodelled behaviour, a stale grid --
        and this lane would walk unprotected no matter the source.

        Raising does NOT mean a transient obstacle fails the walk. `walk_to`'s
        re-plan loop treats a planning failure the same way it treats a stuck
        leg: wait, re-plan, up to `_MAX_REPLANS` times. An NPC standing in the
        only corridor still recovers. What is gone is the unprotected greedy
        walk, not the retry.

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
            raise RoutePlanningError(self._diagnose_unroutable(start, (tx, ty)))
        corners = [
            route[i] for i in range(1, len(route) - 1)
            if (route[i][0] - route[i - 1][0], route[i][1] - route[i - 1][1])
            != (route[i + 1][0] - route[i][0], route[i + 1][1] - route[i][1])
        ]
        return corners + [(tx, ty)]

    def walk_to(self, tx: int, ty: int, frame_budget: int = 3000,
                max_sidesteps: int = 8, *,
                resolve_interruptions: bool = False,
                absorb_wild: bool = False) -> None:
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

        `absorb_wild=True` is the narrower policy the generated templates
        use (ROM run 55: two attempts, two random grass encounters): a wild
        battle is won and the walk resumes; anything else -- a trainer, a
        scene, a touch page -- re-raises the original `WalkInterrupted`
        untouched, because the caller decides whether that was its own
        event. Encounters are RNG, not a fact the generator can order.
        """
        if absorb_wild and not resolve_interruptions:
            for _ in range(_MAX_ABSORBED_WILD):
                try:
                    _walk_to_once(self, tx, ty, frame_budget, max_sidesteps)
                    return
                except WalkInterrupted as exc:
                    if not self._absorb_wild_battle(exc):
                        raise
            shot = self.screenshot("walk_to_wild_cap")
            raise ScenarioError(
                f"walk_to({tx},{ty}) absorbed {_MAX_ABSORBED_WILD} wild "
                f"battles without arriving ({shot})")
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

        A caller (e.g. `ch02.py`'s B4, which must fight off an incidental
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

    def opponent_trainer_id(self) -> int:
        """Which trainer the in-progress battle is against --
        `gTrainerBattleParameter.params.opponentA` (include/battle_setup.h),
        the same field `SetMapVarsToTrainerA` writes and `GetTrainerFlag`
        reads, so this is the engine's own answer rather than an inference
        from the enemy roster.

        `is_trainer_battle()` answers "is this a trainer battle"; it cannot
        answer "*which* trainer", and that gap cost CH04 three sessions:
        route2's `_trigger_trainer` walked the player from the map's south
        seam toward Hiker Larrie at (18,36), Youngster Timothy's event-touch
        page fired en route at (18,47), and the beat won Timothy while
        asserting Larrie's end state. Both guards passed the whole time --
        a trainer battle really had started.

        Fails loud with no battle running, for the same reason
        `is_trainer_battle` does: the parameter block is only meaningful
        while a battle owns the main loop.
        """
        if not self._in_battle():
            raise ScenarioError(
                "opponent_trainer_id() called while no battle is in progress")
        return self.u16(self.symbols["gTrainerBattleParameter"]
                        + self.offsets["off_tbp_opponenta"])

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

    def _absorb_wild_battle(self, exc: WalkInterrupted) -> bool:
        """Win `exc`'s battle if it is (or, within `_WILD_BATTLE_WAIT`
        input-free frames, becomes) a wild one, and settle the overworld.
        False -- nothing pressed, nothing resolved -- for anything else."""
        if not exc.battle:
            waited = 0
            while waited < _WILD_BATTLE_WAIT and not self._in_battle():
                if not self.field_locked():
                    return False
                self.run(30)
                waited += 30
            if not self._in_battle():
                shot = self.screenshot("walk_to_lock_not_a_battle")
                logger.info("walk_to: lock at %s is not a battle after %d "
                            "frames (%s)", exc.stopped_at, waited, shot)
                return False
        if self.is_trainer_battle():
            return False
        from . import battle
        logger.info("walk_to: absorbing a wild battle at %s", self.player_pos())
        battle.win_battle(self)
        self._wait_for_overworld_return(_BATTLE_SETTLE_BUDGET)
        return True

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
        cameo -- e.g. `ch01.py` B4's Theo trigger -- that plays out with no
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

        # Q13 slice 4's per-step append. Bound once, outside the loop, with
        # the same attribute-lookup degrade the rest of this function uses
        # for `_in_battle`/`_grass_cost_context`: the lightweight walk fakes
        # (`test_playtest.py`'s `_FakeWalkEmu`) call `Emulator._walk_greedy`
        # unbound against an object that has no walked-path state. Binding
        # here rather than calling inside a `try` keeps a genuine
        # `AttributeError` raised *inside* the recorder loud, instead of
        # silently turning every subsequent step into an unobserved one.
        try:
            record_tile = self._record_walk_tile
        except AttributeError:
            def record_tile(x: int, y: int) -> None:
                return None

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
                # as ch01.py B4's cameo. Resume walking toward the target.
                continue
            x, y = self.player_pos()
            record_tile(x, y)
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

    def interact(self, frame_budget: int = 30, *,
                 require_script: bool = True) -> bool:
        """Press A; fail if no script picks up the field controls.

        Returns whether a script actually started, so a caller that is
        asserting the ABSENCE of one can say so. `require_script=False`
        turns the failure off and leaves the verdict to the caller -- for a
        page the manifest proves is empty, "nothing happened" is the pass
        condition, not a fault. Nothing about the timing changes: the full
        budget is spent either way.

        Polls for the lock every frame rather than sampling once at the end
        of the window. A script that locks, does its work and releases
        entirely inside the budget is a *successful* interaction, but a
        single sample taken after the fact sees an unlocked field and cannot
        tell it apart from an A press that hit nothing.

        That false negative is not hypothetical: CH04's B11 (re-talking a
        defeated phone-rematch trainer) reported "interaction did not start
        a script" on ROM `b246127d` while the engine was in fact running
        `gotopostbattlescript` into a `register_matchcall` block -- headless,
        no msgbox, done well inside 30 frames. The harness blamed itself for
        what was really a converter bug (the trainer's post-defeat page was
        emitted but never dispatched to), and the misleading error is the
        reason that took a full debug cycle to find.

        A message that appeared counts as evidence too: `clear_field_message`
        wipes the buffer first, so text found afterwards can only have come
        from this interaction.

        The full budget is still spent either way -- callers rely on
        `interact` doubling as a settle, so this changes the VERDICT, not
        the timing.
        """
        self.clear_field_message()
        self.tap("A")
        picked_up = False
        for _ in range(frame_budget):
            self.run(1)
            if self.field_locked() or self.current_field_message_text() is not None:
                picked_up = True
        if not picked_up and require_script:
            shot = self.screenshot("interact_noop")
            raise ScenarioError(f"interaction did not start a script ({shot})")
        return picked_up

    #: `gSpecialVar_Result` while a multichoice waits for input.
    _MENU_WAITING = 0xFF

    def _menu_waiting(self) -> bool:
        return (self.yesno_prompt_up()
                or self.u16(self.symbols["gSpecialVar_Result"]) == Emulator._MENU_WAITING)

    def _answer_menu(self, answer: int) -> tuple[int, int, bool]:
        """Answer the open menu with arm `answer` (the same buttons
        `generic._handle_choice` presses) and read back what the script got."""
        yesno = self.yesno_prompt_up()
        if yesno:
            self.tap("A" if answer == 0 else "B")
        elif answer < 0:
            self.tap("B")
        else:
            for _ in range(answer):
                self.tap("DOWN")
            self.tap("A")
        return answer, self.u16(self.symbols["gSpecialVar_Result"]), yesno

    def advance_dialog(self, key: str = "A", max_taps: int = 1500,
                       stop: Callable[[], bool] | None = None,
                       answers: list[int] | None = None,
                       menus: list[tuple[int, int, bool]] | None = None) -> int:
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
            if menus is not None and (answers or key == "A") and self._menu_waiting():
                # `menus` given: answer each menu from `answers` (the first
                # option once they run out, which is what A would pick) and
                # record it.
                menus.append(self._answer_menu(answers.pop(0) if answers else 0))
                taps += 1
                continue
            self.tap(key)  # samples text frames on every frame it runs
            taps += 1
        self.note_text_frame()
        # The script is done talking: drop its text so the next assertion
        # cannot pass on this one's leftovers (see `clear_field_message`).
        self.clear_field_message()
        return taps

    def settle_field(self, *, quiet_frames: int = 60, max_rounds: int = 8,
                     key: str = "A") -> int:
        """Drain every script queued on the field, not just the first one,
        and return once the field has stayed released for `quiet_frames`.

        `advance_dialog` returns the instant one script releases, which is the
        wrong post-condition after a map entry: a converted map's OnFrame
        dispatcher tests its autorun guards in sequence, so one page setting
        its own guard flag on release is exactly what arms the *next* page.
        Map068 (Kevlar Town's Center) does this on arrival -- EV012's page 2
        runs, sets FLAG_MAP068_EVENT012_TSA, releases, and the following frame
        the dispatcher falls through to EV015's page 1. A beat that drained
        once walked away mid-chain and handed the lock to whichever beat came
        next, which read it as its own interaction misbehaving.

        Also handles the no-msgbox case `advance_dialog` cannot describe on
        its own: EV012's page 2 is `lockall` / `applymovement` / `setflag` /
        `releaseall` with no text in it at all, so there is nothing to advance
        and the release is purely time-based. Tapping through it is harmless
        (the taps land on no textbox) but the *waiting* is what matters.

        Returns the number of scripts drained. Fails loud once `max_rounds`
        iterations are spent -- an unbounded loop here would hang the suite
        instead of naming the map that never went quiet. Note that budget
        counts rounds of *either* kind: a drain and a quiet check that gets
        cut short by a re-lock each cost one, so a chain of N autoruns spends
        up to 2N of it, not N.
        """
        drained = 0
        for _ in range(max_rounds):
            if self.field_locked():
                where = self.map_location()
                bag_before = self.bag_contents()
                mark = len(self.message_log)
                # A message can finish drawing during frames nothing sampled
                # (the crossing's own walk): the buffer still holds it, and
                # only this script can have written it (`advance_dialog` and
                # `interact` clear it).
                up = self.current_field_message_text()
                if up is not None and up != self._last_logged:
                    self.message_log.append(up)
                    self._last_logged = up
                menus: list[tuple[int, int, bool]] = []
                self.advance_dialog(key=key, answers=self.drain_answers.get(tuple(where)),
                                    menus=menus)
                self.drains.append(Drain(
                    map_location=where, messages=tuple(self.message_log[mark:]),
                    bag_before=bag_before, bag_after=self.bag_contents(),
                    menus=tuple(menus)))
                drained += 1
                continue
            quiet = 0
            while quiet < quiet_frames:
                self.run(10)
                quiet += 10
                if self.field_locked():
                    break
            else:
                return drained
        shot = self.screenshot("settle_field_never_quiet")
        raise ScenarioError(
            f"settle_field: the field was still starting scripts after "
            f"{max_rounds} drains (map_location={self.map_location()}) "
            f"({shot})")


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
    plan_failed = False
    for _ in range(_MAX_REPLANS):
        stuck = False
        # A planning failure is a stuck iteration, not an instant abort: it
        # is most often an NPC standing in the only corridor, which is
        # exactly what this loop's wait-and-re-plan exists to absorb. What
        # no longer happens is the silent degrade to an unprotected greedy
        # walk on the bare target -- B3's mechanism. If planning still fails
        # after `_MAX_REPLANS`, the diagnosis below is raised.
        try:
            waypoints = emu._route_waypoints(tx, ty)
        except RoutePlanningError as exc:
            stuck, reason, waypoints = True, str(exc), ()
            plan_failed = True
        else:
            plan_failed = False
        for wx, wy in waypoints:
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
    if plan_failed and _replay_fallback_beat(emu):
        _walk_unplanned_for_replay(emu, tx, ty, frame_budget - spent,
                                   max_sidesteps, start_map, start_locked,
                                   reason)
        return
    shot = emu.screenshot("walk_stuck")
    raise ScenarioError(f"{reason} ({shot})")


def _replay_fallback_beat(emu: "Emulator") -> str | None:
    """The inherited beat currently running, if the replay fallback applies.

    `runner` sets `emu.replay_beat` to the beat's own name for a beat that
    came from `ChapterBuilder(predecessor=...)` and to `None` for a beat the
    chapter under test owns. `None`/absent means no fallback: the chapter
    being tested is always held to the strict planner.
    """
    return getattr(emu, "replay_beat", None)


def _walk_unplanned_for_replay(
    emu: "Emulator", tx: int, ty: int, frame_budget: int, max_sidesteps: int,
    start_map, start_locked: bool, reason: str,
) -> None:
    """Walk greedily at the bare target, with none of the planner's
    avoid-set -- the degrade f705b642 removed, restored for INHERITED beats
    only and recorded every time it fires.

    Why it is back at all: CH01-CH04's beats were authored while this degrade
    fired on every planning failure, so their declared coordinates have never
    been held to a strict planner. The router is new; CH05 is the run that
    proves it. Failing an inherited beat on a route its own chapter never
    committed to tests the wrong thing and blocks the replay that only exists
    to reach CH05's starting state. `_close_walk` already draws this exact
    line for the walked-path oracle, and for the same reason: an inherited
    beat is replayed to reach a state, it is not the artifact under test.

    Why it is narrow:

    - INHERITED ONLY. A beat the chapter owns never reaches here, so CH05's
      own 19 beats get the strict planner with no exception.
    - PLANNING FAILURES ONLY. A leg that planned fine and then got stuck is
      not this case and still fails loud; only `RoutePlanningError` after
      `_MAX_REPLANS` degrades.
    - AFTER the retry loop, never instead of it. A patrolling NPC still
      recovers by waiting and re-planning; this is the last resort.
    - RECORDED, never silent (`KIND_REPLAY_FALLBACK`). The finding lands in
      the run's ledger with the beat's name, so a green replay that leaned on
      it says so in its own artifact. What §4.5 forbids is the silence.

    Why it expires: the gate is `emu.replay_beat`, which the runner derives
    from the `<owner>:<name>` prefix `ChapterBuilder` puts on inherited beats.
    Re-derive CH01 and run it as its own chapter and its beats are unprefixed,
    so they get the strict planner automatically. Nothing here has to be
    remembered and removed -- when CH01-CH04 have been re-run through the new
    beat pipeline, this function is dead code and should be deleted.

    Standing hazard while it lives: this is the walk that crossed Timothy's
    event-touch tile in CH04's B3 and fought the wrong trainer while both
    guards passed. An inherited beat can still pass for the wrong reason. The
    ledger entry is where to look first when a CH05 beat fails for no reason
    its own code explains.
    """
    beat = _replay_fallback_beat(emu)
    logger.warning(
        "[replay fallback] %s: walk_to(%d,%d) could not be planned after %d "
        "re-plans (%s) -- walking greedily on the bare target with no "
        "avoid-set, because this is an INHERITED beat. Recorded as a carried "
        "finding; this beat's result is weaker evidence than a planned one.",
        beat, tx, ty, _MAX_REPLANS, reason)
    try:
        emu.contradictions.record(Contradiction(
            kind=KIND_REPLAY_FALLBACK,
            beat="",  # stamped at the beat boundary by `_close_walk`
            detail=(f"walk_to({tx},{ty}) was walked unplanned: {reason}"),
            model="the route planner found no route",
            measurement="walked greedily on the bare target",
            assumption=(
                "an inherited beat replays to reach state and predates the "
                "strict planner, so the walk proceeds unprotected"),
            cell=(tx, ty),
        ))
    except AttributeError:
        # Lightweight walk fakes predate the ledger -- same degrade shape
        # `_close_walk` uses for them. The WARNING above still fired.
        pass
    arrived, _used, why = emu._walk_greedy(
        tx, ty, frame_budget, max_sidesteps, start_map,
        start_locked=start_locked)
    if not arrived:
        # The fallback is a relaxation of PLANNING, not of arrival. A greedy
        # walk that still cannot reach the tile is a real failure and stays
        # loud -- otherwise this would be the silent-degrade shape twice over.
        shot = emu.screenshot("walk_stuck")
        raise ScenarioError(f"{why} ({shot})")
