"""Row and disposition types — the contract the generator and checker share.

Everything in this module is pure data plus the handful of rules that must have
exactly one implementation, because both halves of the manifest ask them:

* which effect tags forbid a ``cosmetic`` disposition (Q11),
* when a row owes a source citation (Q5),
* when a row cannot be dispositioned at all (Q2iii),
* how a row's content is hashed so a stored decision is invalidated when the
  content underneath it changes (Q6.1).

Keeping these here rather than in the checker is deliberate. A rule that lives
only in the checker can be forgotten by the renderer, and the two then disagree
about what the operator approved.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, fields
from typing import Any, Literal

# --- effect vocabulary -----------------------------------------------------
#
# Derived tags, not RGSS command codes. Most of these do not exist as numeric
# codes at all: `giveitem`, `givemon`, `trainerbattle`, `shop`, `heal` and `pc`
# are embedded Ruby inside code-355/655 Script commands, or inside a code-111
# conditional whose params[0] == 12 (script-typed). See census.py's note that
# the corpus contains not one code-301 Battle Processing command.
#
# `move_route`, `bgm`, `se`, `money`, `wild_battle` and `common_event` are here
# because CH03's late growth (B27-B33) was warp-arrival *facing* and *BGM*: a
# vocabulary without them would not have prompted the very beats whose omission
# motivated the manifest.
EFFECT_TAGS: frozenset[str] = frozenset({
    "giveitem",
    "givemon",
    "trainerbattle",
    "wild_battle",
    "warp",
    "switch_write",
    "var_write",
    "self_switch_write",
    "shop",
    "heal",
    "pc",
    "money",
    "common_event",
    "text",
    "choice",
    "move_route",
    "bgm",
    "se",
    "graphic",
    "bubble_ui",
    "animation",
    "screen_fx",
    "erase_event",
    "temp_switch_write",
    "control_flow",
})

# A row may be `cosmetic` only if its entire effect set is non-state-writing.
# `self_switch_write` is deliberately state-writing: a dialogue NPC that sets a
# self-switch is changing its own future behaviour, which is state, not decor.
#
# `erase_event` and `temp_switch_write` are state-writing for the same reason:
# `pbEraseThisEvent` calls `$PokemonMap.addErasedEvent` specifically so the
# erase survives a save/load, and `setTempSwitchOn` re-evaluates page
# conditions within the same visit even though it does not survive a map
# reload. `control_flow` is state-writing because `Exit Event Processing`
# (code 115) terminates the remainder of a page's command list — a page
# carrying it cannot honestly be called decoration, regardless of what
# commands precede it.
COSMETIC_SAFE_TAGS: frozenset[str] = frozenset({
    "text",
    "choice",
    "move_route",
    "bgm",
    "se",
    "graphic",
    "bubble_ui",
    "animation",
    "screen_fx",
})

STATE_WRITING_TAGS: frozenset[str] = EFFECT_TAGS - COSMETIC_SAFE_TAGS

Verdict = Literal["beat", "blocked", "cosmetic", "unreachable"]
_VERDICTS: frozenset[str] = frozenset({"beat", "blocked", "cosmetic", "unreachable"})

# Verdicts whose argument is mandatory. `cosmetic` takes none; `beat` names the
# beat, `blocked` the capability set (or tooling primitive) that unblocks it,
# `unreachable` the reason.
#
# `deferred` and geography-flavoured `unreachable:<reason>` collapsed into
# `blocked:<capability set>` (PLAYTEST_AUTHORING_IMPROVEMENT_V2.md Q3, DECIDED
# 2026-08-27): it answers exactly one question, what unblocks this row.
# `unreachable` survives, narrowed to content no chapter will ever reach (cut
# content, dead pages) -- it is no longer a synonym for "blocked and I gave up".
_ARGUMENT_REQUIRED: frozenset[str] = frozenset({"beat", "blocked", "unreachable"})

_BEAT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# `blocked:` argument shapes (Q3/Q10):
#
#   blocked:rock_smash                 -- one capability
#   blocked:rock_smash|strength        -- a minimal capability SET, spelled as
#                                          a "|"-joined list. "|" is chosen
#                                          because it already appears in
#                                          `traversal.reachability.BlockedVerdict
#                                          .as_disposition`'s own spelling
#                                          ("blocked:" + "|".join(...)) -- the
#                                          derivation layer and the authored
#                                          layer share one spelling, so a
#                                          derived value can be affirmed
#                                          verbatim. Sorted ascending and
#                                          deduplicated so the string form is
#                                          canonical (one row, one spelling,
#                                          stable round trip).
#   blocked:tooling:emulator_set_flag  -- Q10's third kind: blocked by the
#                                          conversion/playtest tooling rather
#                                          than an in-game capability. Never
#                                          combined with capability tokens --
#                                          it names exactly one missing
#                                          primitive.
_BLOCKED_TOOLING = re.compile(r"^tooling:[A-Za-z][A-Za-z0-9_]*$")
_CAPABILITY_TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")


def _validate_blocked_argument(row_id: str, argument: str) -> None:
    if _BLOCKED_TOOLING.match(argument):
        return
    tokens = argument.split("|")
    if not argument or any(not _CAPABILITY_TOKEN.match(t) for t in tokens):
        raise DispositionError(
            f"{row_id}: {argument!r} is not a valid 'blocked:' argument; expected "
            "'tooling:<primitive>' or a '|'-joined, sorted, deduplicated list of "
            "capability names, e.g. 'rock_smash' or 'rock_smash|strength'"
        )
    if tokens != sorted(tokens) or len(tokens) != len(set(tokens)):
        raise DispositionError(
            f"{row_id}: 'blocked:' argument {argument!r} must be sorted ascending "
            "and free of duplicates, e.g. 'rock_smash|strength', not "
            "'strength|rock_smash'"
        )


class DispositionError(ValueError):
    """A disposition string is malformed, or breaks a rule in this module."""


# --- rows ------------------------------------------------------------------


@dataclass(frozen=True)
class PageCondition:
    """An event page's appearance condition, in human terms.

    The raw RMXP values are a polarity trap — code-123 self-switch value ``0``
    means **ON** — and a prose misread of exactly that inverted a live sidequest
    into "dead content" once already. `describe` is what the review rendering
    shows; nothing downstream should re-derive meaning from the raw fields.
    """

    switch1_id: int | None = None
    switch1_name: str | None = None
    switch2_id: int | None = None
    switch2_name: str | None = None
    variable_id: int | None = None
    variable_name: str | None = None
    variable_min: int | None = None
    self_switch_ch: str | None = None

    @property
    def is_unconditional(self) -> bool:
        return not self.clauses()

    def clauses(self) -> list[str]:
        out: list[str] = []
        if self.switch1_id is not None:
            out.append(f"switch {self._switch(self.switch1_id, self.switch1_name)} is ON")
        if self.switch2_id is not None:
            out.append(f"switch {self._switch(self.switch2_id, self.switch2_name)} is ON")
        if self.variable_id is not None:
            name = self._switch(self.variable_id, self.variable_name)
            out.append(f"variable {name} >= {self.variable_min}")
        if self.self_switch_ch is not None:
            out.append(f"self-switch {self.self_switch_ch} is ON")
        return out

    def describe(self) -> str:
        clauses = self.clauses()
        return " and ".join(clauses) if clauses else "always"

    @staticmethod
    def _switch(ident: int, name: str | None) -> str:
        return f"{ident} ({name})" if name else str(ident)


@dataclass(frozen=True)
class SeamRef:
    """One side of an overland connection, as `connections.json` records it.

    Seams are not events, so an event-only manifest cannot see them — and CH04's
    entire chapter identity is two of them. Every outdoor route boundary in the
    corpus is invisible without this row kind.
    """

    map_id: int
    direction: str
    offset: int
    other_map_id: int
    other_direction: str
    other_offset: int


@dataclass(frozen=True)
class TerrainRef:
    """A traversal mechanic realized by a metatile behaviour, not a script.

    A diagonal-stair cell (`tileset_converter.stairs`) is converted to a
    NATIVE pokeemerald metatile behaviour and its RMXP event is dropped from
    the emitted output entirely — so, exactly like a `SeamRef`, an
    event-only manifest cannot see it. `source_event_id` keeps the row
    traceable back to the RMXP event it replaces, for citation and for
    cross-checking against `stairs.py`'s own detection.
    """

    x: int
    y: int
    behavior: str
    source_event_id: int


@dataclass(frozen=True)
class ManifestRow:
    """One generated row: an event page, an overland seam, or a terrain mechanic.

    Pure derivation from `output/uranium-build/`. Nothing here is authored, and
    re-running the generator must reproduce it byte for byte.
    """

    row_id: str
    kind: Literal["page", "seam", "terrain"]
    map_id: int
    content_hash: str
    effects: tuple[str, ...] = ()
    # Every script head found on the page, verbatim — recognized or not. The
    # manifest carries all of them because head recognition is open-ended: a
    # novel `pbSomething` absent from MECHANIC_BY_HEAD would otherwise produce
    # an untagged row that reads as cosmetic and gets waved through.
    script_heads: tuple[str, ...] = ()
    unrecognized_heads: tuple[str, ...] = ()
    # Command codes present on the page that the extractor has no rule for.
    # `_census_one_map` recognizes 10 of the 59 codes in use and has no fallback
    # bucket, so 49 codes are invisible to it today; this is that bucket.
    other_codes: tuple[int, ...] = ()
    # Capabilities the row needs before it can be asserted (`rock_smash`,
    # `strength`, ...), from script content. Reachability-derived requirements
    # are a second source and are not populated yet.
    requires: tuple[str, ...] = ()
    # Count of `transpile_unhandled.jsonl` entries joining to this row, three-
    # valued on purpose:
    #
    #   a positive int -- that many unhandled queue entries joined to this row.
    #   0              -- the row's map WAS staged (it has a `<map>.pory` in
    #                      the transpiler's own output) and this page produced
    #                      no queue entries: a real, measured clean result.
    #   None           -- the row's map was never staged at all, so the queue
    #                      says nothing whatsoever about this row; the veto
    #                      below cannot be evaluated and must not be read as
    #                      "clean" just because the count is falsy.
    #
    # A page with unhandled queue entries may not be dispositioned `cosmetic`:
    # that is the free check for a dead conversion with no beat written at
    # all. `None` exists so a never-transpiled map cannot pass that check
    # vacuously (see `generator._load_staged_map_ids`).
    unhandled: int | None = None
    # Whether the page carries a code-111 conditional with params[0] == 12, i.e.
    # a branch whose behaviour lives in Ruby rather than in structure.
    script_typed_conditions: int = 0

    event_id: int | None = None
    event_name: str | None = None
    page_idx: int | None = None
    condition: PageCondition | None = None
    trigger: str | None = None
    seam: SeamRef | None = None
    terrain: TerrainRef | None = None
    # Whether the offline reachability source (`traversal.reachability`) was
    # actually consulted while generating THIS row's `requires[]` -- i.e.
    # whether this row's map had a verified entry in
    # `generator._CHAPTER_MAP_START_CELLS` at generation time. False does NOT
    # mean "no capability gates exist here"; it means the terrain-gated half
    # of the capability model (surf, waterfall -- the half `_HEAD_REQUIRES`
    # structurally cannot express) was never even asked about this map, so an
    # absence of `requires` entries on an unconsulted row is not evidence of
    # anything. Recorded per row (duplicated across every row sharing a
    # `map_id`, same as `map_id` itself) rather than in a separate structure,
    # because that is the manifest's existing shape for a per-map fact.
    reachability_consulted: bool = False

    @property
    def is_dispositionable(self) -> bool:
        """False when a human must classify something before deciding.

        Fail loud (CLAUDE.md §4.5): an unrecognized head or command code is
        undispositionable, not untagged. Six of eleven heads were unrecognized
        on the very first map tested, so this arm is the common case early on.
        """
        return not self.unrecognized_heads and not self.other_codes

    @property
    def may_be_cosmetic(self) -> bool:
        if self.kind in ("seam", "terrain"):
            # A seam is a warp; a terrain row is a load-bearing traversal
            # behaviour realized by a metatile rather than a script. Neither
            # is ever decoration.
            return False
        if self.unhandled is None:
            # Unstaged, not clean. The whole point of the three-valued
            # `unhandled` field is that "never measured" must not read the
            # same as "measured and found nothing" -- an unstaged map's rows
            # would otherwise wave through `cosmetic` vacuously.
            return False
        if self.unhandled:
            return False
        if not self.is_dispositionable:
            return False
        return not (set(self.effects) & STATE_WRITING_TAGS)

    @property
    def needs_citation(self) -> bool:
        """Rows whose effect the manifest's structure does not determine.

        The trigger is mechanical on purpose. "Cite when the effect is
        non-obvious" fails by construction, because the author who misreads a
        design is the author who believes it is obvious.
        """
        return bool(self.unrecognized_heads) or self.script_typed_conditions > 0

    def blocking_tags(self) -> tuple[str, ...]:
        """The state-writing tags that forbid a `cosmetic` disposition."""
        return tuple(sorted(set(self.effects) & STATE_WRITING_TAGS))


# --- dispositions ----------------------------------------------------------


@dataclass(frozen=True)
class Disposition:
    """One authored decision about one row.

    Hand-edited and committed. The generator joins it by `row_id` and never
    writes to it, so re-running the generator cannot clobber a decision.
    """

    row_id: str
    verdict: Verdict
    argument: str | None = None
    # RMXP path plus the Essentials script or wiki page. Required whenever the
    # row's citation trigger fires.
    source: str | None = None
    # The row's `content_hash` at the time this decision was affirmed. On
    # mismatch the decision is invalidated and must be re-affirmed: detecting a
    # row's *disappearance* is the easy case, a row whose contents change
    # underneath a standing decision is the dangerous one.
    affirmed_hash: str | None = None
    note: str | None = None
    # Assertability (Q3 decision 3): whether a negative beat can be written
    # NOW for a `blocked:` row -- walk up to the blocked thing, press A,
    # assert the refusal. An authoring judgment, separate from the verdict
    # itself: the old vocabulary smuggled this into `deferred:` vs
    # `unreachable:`, which is exactly what made the CH07 debt uncountable.
    # None means "not judged" (or not applicable outside `blocked:`); only
    # meaningful when `verdict == "blocked"`.
    assertable: bool | None = None
    # The beat id (e.g. "B6") that asserts the refusal, if one has been
    # written. Optional even when `assertable` is True -- the judgment that a
    # negative beat CAN be written and the act of writing one are different
    # steps. Requires `assertable is True`.
    negative_beat: str | None = None

    def __post_init__(self) -> None:
        if self.verdict not in _VERDICTS:
            raise DispositionError(
                f"{self.row_id}: unknown verdict {self.verdict!r}; "
                f"expected one of {sorted(_VERDICTS)}"
            )
        if self.verdict in _ARGUMENT_REQUIRED and not self.argument:
            raise DispositionError(
                f"{self.row_id}: verdict {self.verdict!r} requires an argument, e.g. "
                f"{_EXAMPLE_BY_VERDICT[self.verdict]}"
            )
        if self.verdict == "cosmetic" and self.argument:
            raise DispositionError(
                f"{self.row_id}: verdict 'cosmetic' takes no argument, got {self.argument!r}"
            )
        if self.verdict == "beat" and not _BEAT_NAME.match(self.argument or ""):
            raise DispositionError(
                f"{self.row_id}: {self.argument!r} is not a beat name; beat ids are "
                "labels like 'B12' or 'N3'"
            )
        if self.verdict == "blocked":
            _validate_blocked_argument(self.row_id, self.argument or "")
        if self.assertable is not None and self.verdict != "blocked":
            raise DispositionError(
                f"{self.row_id}: 'assertable' only applies to verdict 'blocked', "
                f"got {self.verdict!r}"
            )
        if self.negative_beat is not None:
            if self.assertable is not True:
                raise DispositionError(
                    f"{self.row_id}: 'negative_beat' requires assertable=True"
                )
            if not _BEAT_NAME.match(self.negative_beat):
                raise DispositionError(
                    f"{self.row_id}: {self.negative_beat!r} is not a beat name; beat "
                    "ids are labels like 'B12' or 'N3'"
                )

    @property
    def spec(self) -> str:
        """The compact ``verdict:argument`` form used in the authored file."""
        return self.verdict if self.argument is None else f"{self.verdict}:{self.argument}"

    @classmethod
    def parse(cls, row_id: str, spec: str, **rest: Any) -> Disposition:
        """Parse ``beat:B12`` / ``blocked:rock_smash`` / ``cosmetic``."""
        verdict, _, argument = spec.partition(":")
        verdict = verdict.strip()
        argument = argument.strip()
        if verdict not in _VERDICTS:
            raise DispositionError(
                f"{row_id}: unknown verdict {verdict!r} in {spec!r}; "
                f"expected one of {sorted(_VERDICTS)}"
            )
        return cls(row_id=row_id, verdict=verdict, argument=argument or None, **rest)  # type: ignore[arg-type]


_EXAMPLE_BY_VERDICT = {
    "beat": "beat:B12",
    "blocked": "blocked:rock_smash",
    "unreachable": "unreachable:dev-only flag sw130, never set in the corpus",
}


# --- hashing ---------------------------------------------------------------


def content_hash(payload: Any) -> str:
    """Stable hash of a row's underlying content.

    Canonical JSON with sorted keys, so the hash tracks *meaning* rather than
    the deserializer's key ordering. Truncated to 16 hex characters: this
    guards against drift, not against an adversary.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# --- row serialization -----------------------------------------------------
#
# The round trip lives here rather than in the generator because the checker
# and the renderer read what the generator wrote, and a loader that tolerates
# missing keys quietly re-introduces the drift the manifest exists to kill: add
# a field to `ManifestRow`, the generator writes it, a lenient reader defaults
# it away, and the rules then evaluate on a row that is not the row on disk.
# Both directions are strict, so that failure is a loud one.


def row_to_dict(row: ManifestRow) -> dict[str, Any]:
    """Plain-JSON form of a row. Nested dataclasses recurse; tuples become lists."""
    return asdict(row)


def row_from_dict(data: dict[str, Any]) -> ManifestRow:
    """Rebuild a row, rejecting any key set that is not exactly the row's fields."""
    expected = {f.name for f in fields(ManifestRow)}
    got = set(data)
    if missing := expected - got:
        raise ValueError(
            f"manifest row {data.get('row_id', '<no row_id>')!r} is missing "
            f"{sorted(missing)}; regenerate the manifest rather than patching it"
        )
    if unknown := got - expected:
        raise ValueError(
            f"manifest row {data.get('row_id', '<no row_id>')!r} carries unknown "
            f"{sorted(unknown)}; the file was written by a newer schema"
        )

    condition = data["condition"]
    seam = data["seam"]
    terrain = data["terrain"]
    return ManifestRow(
        **{
            **data,
            "effects": tuple(data["effects"]),
            "script_heads": tuple(data["script_heads"]),
            "unrecognized_heads": tuple(data["unrecognized_heads"]),
            "other_codes": tuple(data["other_codes"]),
            "requires": tuple(data["requires"]),
            "condition": PageCondition(**condition) if condition is not None else None,
            "seam": SeamRef(**seam) if seam is not None else None,
            "terrain": TerrainRef(**terrain) if terrain is not None else None,
        }
    )


def page_row_id(map_id: int, event_id: int, page_idx: int) -> str:
    return f"map{map_id:03d}/ev{event_id:03d}/p{page_idx}"


def terrain_row_id(map_id: int, subkind: str, x: int, y: int) -> str:
    """Row id for a terrain row -- a traversal mechanic with no event of its
    own once absorbed (see `TerrainRef`).

    `subkind` slots in so later terrain kinds (ledges, water) don't collide
    with stairs at the same cell; pass `"stairs"` for diagonal-stair rows.
    """
    return f"map{map_id:03d}/terrain/{subkind}/{x},{y}"


def seam_row_id(map_id: int, direction: str, other_map_id: int) -> str:
    """Seam rows are keyed from the crossing map's side.

    A seam appears once per map it touches, so a chapter owning only one side
    still gets a row it must disposition, and the two sides can be
    dispositioned differently (one crossed in this chapter, one not).
    """
    return f"map{map_id:03d}/seam/{direction.upper()}/map{other_map_id:03d}"
