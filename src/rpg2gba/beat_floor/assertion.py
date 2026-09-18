"""The generic beat floor's record types (REDERIVATION_PLAN.md §16.3 C4).

A row's floor is the *set* of assertions its RMXP source commands imply,
one extractor per command code (per call head for script 355/655, per
condition family for 111 type 12). Expected values come from the RMXP
source, never from converted Poryscript (R11's proxy-oracle rule).

This module is the contract every extractor module in the package shares:
`walk.py` (the per-row walker and plain-code extractors), `script.py`,
`condition.py` and `move_route.py`. It carries no logic beyond validation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

AssertionKind = Literal[
    "trigger",            # params: trigger ("action"|"touch"|"event_touch"|"autorun"|"parallel")
    "completes",          # the page runs to its end and returns control
    "text",               # params: index (message box within the row), text (normalized)
    "choice",             # params: options (tuple[str, ...], normalized)
    "switch_write",       # params: switch_id, value
    "var_write",          # params: var_id, op, value (story_state Assign/Adjust, rendered)
    "self_switch_write",  # params: event_id, letter, value
    "warp",               # params: map_id, x, y, direction, arrives_on_door (bool)
    "heal_party",
    "erase_event",        # params: event_id
    "item_grant",         # params: item (internal name), quantity
    "pokemon_grant",      # params: species (internal name), level
    "service",            # params: name (mart, pc, save, starter_select, …), plus literal args
    "battle",             # params: kind ("trainer"|"wild"), plus identity fields
    "displacement",       # params: target (-1 player, 0 this event, N event), dx, dy, facing|None
    "event_position",     # params: target, x, y, facing|None
    "audio",              # params: code, name  (tag "audio"; not checked until audio is mapped)
    "visual",             # params: code, detail (visual-only; asserts nothing beyond completes)
    # Row-level kinds for rows with no command list (C5): list_index -1, code None.
    "seam_crossing",      # params: map_id, direction, offset, other_map_id, other_direction, other_offset
    "stair_crossing",     # params: x, y, side ("left"|"right"), steps (((step_dir, dx, dy), ...))
]

AssertionTag = Literal["state", "text", "position", "flow", "audio", "visual", "service"]

OFFLINE_KINDS: frozenset[str] = frozenset({
    "trigger", "completes", "text", "choice", "switch_write", "self_switch_write",
    "warp", "heal_party", "erase_event", "item_grant", "pokemon_grant", "audio", "visual",
})
"""Kinds checkable without the emulator. `var_write`, `displacement`,
`event_position`, `battle`, `service`, `seam_crossing` and `stair_crossing` are ROM-only (R11: a `var_write` pulls a
flavour NPC into the ROM sample; a menu the player drives is not proven by its
call existing in the compiled script). `audio`/`visual` assert nothing a ROM walk
could fail beyond `completes`, so they do not block offline eligibility."""

Params = tuple[tuple[str, Any], ...]


def make_params(**values: Any) -> Params:
    """Canonical, hashable, byte-stable params (sorted keys; lists -> tuples)."""
    return tuple(sorted(
        (k, tuple(v) if isinstance(v, list) else v) for k, v in values.items()))


@dataclass(frozen=True)
class FloorAssertion:
    row_id: str
    kind: AssertionKind
    list_index: int      # position in the owning page's raw `list`; -1 for row-level kinds
    code: int | None     # source command code; None for row-level kinds
    params: Params = ()
    tag: AssertionTag = "flow"
    offline: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "offline", self.kind in OFFLINE_KINDS)

    def param(self, name: str) -> Any:
        return dict(self.params)[name]


@dataclass(frozen=True)
class FloorRefusal:
    """A command the floor could not derive an assertion for. Any refusal
    refuses the whole row (R11: a code with no extractor refuses the row).

    `reason` is a stable snake_case id (`no_extractor`, `unknown_script_head`,
    `unclassified_condition`, `story_state_refusal`, …); `detail` cites the
    source precisely."""

    row_id: str
    reason: str
    list_index: int
    code: int | None
    detail: str


@dataclass(frozen=True)
class RowFloor:
    row_id: str
    trigger: str
    assertions: frozenset[FloorAssertion]
    refusals: tuple[FloorRefusal, ...]

    @property
    def refused(self) -> bool:
        return bool(self.refusals)

    @property
    def offline_eligible(self) -> bool:
        return not self.refused and all(a.offline for a in self.assertions)


@dataclass(frozen=True)
class ExtractContext:
    """Everything an extractor may read. Extractors never load files."""

    map_id: int
    event_id: int
    page_idx: int
    row_id: str
    event: dict[str, Any]                       # the raw event (x, y, pages)
    map_data: dict[str, Any]
    common_events_by_id: dict[int, dict[str, Any]]
    # Uranium map id -> the cells the emitted layout stamps as door tiles
    # (`metadata_wiring.load_warp_overrides`, the build's
    # `warp_overrides.gen.json`) -- the `warp` extractor's `arrives_on_door`.
    # None = not supplied: the warp extractor fails loud rather than guess.
    door_cells: Mapping[int, frozenset[tuple[int, int]]] | None = None


ExtractResult = tuple[tuple[FloorAssertion, ...], tuple[FloorRefusal, ...]]


class LeafExtractor(Protocol):
    """One plain command code (`walk.CODE_EXTRACTORS[code]`)."""

    def __call__(self, cmd: dict[str, Any], list_index: int, ctx: ExtractContext) -> ExtractResult: ...


class ScriptHeadExtractor(Protocol):
    """One script call head (`script.SCRIPT_HEAD_EXTRACTORS[head]`). `text`
    is the whole 355+655* block joined with newlines."""

    def __call__(self, text: str, list_index: int, ctx: ExtractContext) -> ExtractResult: ...


class ConditionFamilyExtractor(Protocol):
    """One 111 type-12 family (`condition.CONDITION_FAMILY_EXTRACTORS[name]`).
    Contributes to the row *enclosing* the 111 (its condition runs there)."""

    def __call__(self, condition_text: str, list_index: int, ctx: ExtractContext) -> ExtractResult: ...
