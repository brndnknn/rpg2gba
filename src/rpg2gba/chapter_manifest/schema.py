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
    "respawn_write",
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
# `respawn_write` (pbSetPokemonCenter -> setrespawn(HEAL_LOCATION_*)) is
# likewise absent from COSMETIC_SAFE_TAGS below, hence state-writing via the
# derived STATE_WRITING_TAGS set. It is deliberately its own tag, not `heal`:
# pbSetPokemonCenter never heals the party (that is a separate pbHealAll/
# code-314 call with its own `heal` tag) — it only records a respawn anchor.
# That anchor is persistent state surviving a white-out AND a save/reload
# (heal_locations.py's docstring: it feeds $PokemonGlobal.pokecenterMapId/X/
# Y/Direction, read by Kernel.pbStartOver), so folding it into `heal` would
# both mislabel the effect and, worse, let a page carrying only this call
# read as `heal` and pass a reviewer's heal-is-usually-fine intuition when
# what actually changed is where the player wakes up after fainting.
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

Verdict = Literal["beat", "blocked", "boundary", "cosmetic", "unreachable"]
_VERDICTS: frozenset[str] = frozenset({"beat", "blocked", "boundary", "cosmetic", "unreachable"})

# Verdicts whose argument is mandatory. `cosmetic` and `boundary` take none;
# `beat` names the beat, `blocked` the capability set (or tooling primitive)
# that unblocks it, `unreachable` the reason.
#
# `deferred` and geography-flavoured `unreachable:<reason>` collapsed into
# `blocked:<capability set>` (PLAYTEST_AUTHORING_IMPROVEMENT_V2.md Q3, DECIDED
# 2026-08-27): it answers exactly one question, what unblocks this row.
# `unreachable` survives, narrowed to content no chapter will ever reach (cut
# content, dead pages) -- it is no longer a synonym for "blocked and I gave up".
#
# `boundary` (PROJECT_TODO #72/#73, operator ruling 2026-09-04) is the newest
# arrival and, like `cosmetic`, takes no argument -- deliberately, not an
# oversight. A row on a chapter's forward boundary (the event that carries the
# player into the next chapter's territory) is not the shipping chapter's to
# assert; the chapter that arrives claims it. A qualified form such as
# `boundary:CH05/B1` was considered and rejected: it would force the shipping
# chapter's dispositions to name a beat in a chapter that has not been staged
# yet -- the exact "authored against an unstaged neighbour" failure this
# verdict exists to prevent, just relocated from a beat id into a disposition
# argument. The shipping chapter would have to guess the successor's beat
# naming and be re-edited when it guessed wrong. A bare `boundary` says only
# "this row is not mine; whoever arrives claims it" -- *who* arrives is
# derived from the chapter chain (`chapter_atlas.binding`), which is already
# the one source of truth for chapter order, not re-stated here.
_ARGUMENT_REQUIRED: frozenset[str] = frozenset({"beat", "blocked", "unreachable"})

_BEAT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# `blocked:` argument shapes (Q3/Q10, grammar revised 2026-09-10):
#
#   blocked:rock_smash                 -- one capability
#   blocked:strength+surf              -- an AND: every member of ONE minimal
#                                          capability SET is required. "+"
#                                          joins tokens within a set.
#   blocked:rock_smash|surf            -- an OR: EITHER alternative set
#                                          suffices on its own. "|" separates
#                                          alternative sets. "+" binds tighter
#                                          than "|"; there is no grouping
#                                          syntax (none is needed: an
#                                          alternative is always a flat AND of
#                                          tokens).
#   blocked:rock_smash|strength+surf   -- rock_smash alone, OR strength and
#                                          surf together.
#
# This spelling matches `traversal.reachability.BlockedVerdict.as_disposition`'s
# own output verbatim -- the derivation layer and the authored layer share one
# grammar, so a derived value can be affirmed as-is. Canonical form: within
# each set, tokens sorted ascending and deduplicated; across sets, ordered by
# (size, then the sorted tuple of member values) and deduplicated; no set may
# be a proper superset of another (a non-minimal alternative is incoherent
# alongside the minimal one it's redundant with). One row, one spelling,
# stable round trip.
#
#   blocked:tooling:emulator_set_flag  -- Q10's third kind: blocked by the
#                                          conversion/playtest tooling rather
#                                          than an in-game capability. Never
#                                          combined with capability tokens --
#                                          it names exactly one missing
#                                          primitive.
_BLOCKED_TOOLING = re.compile(r"^tooling:[A-Za-z][A-Za-z0-9_]*$")
_CAPABILITY_TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")


def parse_blocked_argument(argument: str) -> tuple[frozenset[str], ...]:
    """Parse a `blocked:` capability argument into its alternative minimal
    sets: `"|"` separates alternatives (OR -- any ONE suffices), `"+"` joins
    capability tokens within one alternative (AND -- ALL are required). `+`
    binds tighter than `|`; there is no grouping syntax.

    Callers use this instead of re-splitting the string by hand. Does not
    accept the `tooling:<primitive>` form -- callers must detect and handle
    that prefix themselves before calling this, since it is never a
    capability set.

    Only parses: does not enforce canonical ordering, deduplication, or
    minimality-across-alternatives. `_validate_blocked_argument` enforces
    those on top of this for authored dispositions; a caller reading an
    already-validated `Disposition.argument` gets a canonical parse for
    free, but this function itself does not police that.

    Raises `DispositionError` if `argument` is empty, contains an empty
    alternative (e.g. ``"a||b"``), an empty token (e.g. ``"a++b"``), or any
    token that does not match `_CAPABILITY_TOKEN`.
    """
    if not argument:
        raise DispositionError("empty 'blocked:' capability argument")
    alternatives: list[frozenset[str]] = []
    for alt in argument.split("|"):
        if not alt:
            raise DispositionError(
                f"{argument!r} contains an empty alternative (stray '|')"
            )
        tokens = alt.split("+")
        if any(not t for t in tokens):
            raise DispositionError(
                f"{argument!r} contains an empty capability token (stray '+')"
            )
        for token in tokens:
            if not _CAPABILITY_TOKEN.match(token):
                raise DispositionError(
                    f"{argument!r}: {token!r} is not a valid capability token"
                )
        alternatives.append(frozenset(tokens))
    return tuple(alternatives)


def _validate_blocked_argument(row_id: str, argument: str) -> None:
    if _BLOCKED_TOOLING.match(argument):
        return
    try:
        alternatives = parse_blocked_argument(argument)
    except DispositionError as exc:
        raise DispositionError(
            f"{row_id}: {argument!r} is not a valid 'blocked:' argument ({exc}); "
            "expected 'tooling:<primitive>' or a '|'-joined list of '+'-joined "
            "capability sets, e.g. 'rock_smash', 'strength+surf', or "
            "'rock_smash|strength+surf'"
        ) from exc

    for alt in argument.split("|"):
        tokens = alt.split("+")
        if tokens != sorted(tokens) or len(tokens) != len(set(tokens)):
            raise DispositionError(
                f"{row_id}: 'blocked:' argument {argument!r} has capability set "
                f"{alt!r} that is not sorted ascending and free of duplicates, "
                "e.g. 'strength+surf', not 'surf+strength'"
            )

    def _sort_key(s: frozenset[str]) -> tuple[int, tuple[str, ...]]:
        return (len(s), tuple(sorted(s)))

    canonical = sorted(alternatives, key=_sort_key)
    if list(alternatives) != canonical:
        expected = "|".join("+".join(sorted(s)) for s in canonical)
        raise DispositionError(
            f"{row_id}: 'blocked:' argument {argument!r} alternatives are not "
            f"in canonical order (by set size, then sorted capability values); "
            f"expected {expected!r}"
        )
    if len(set(alternatives)) != len(alternatives):
        raise DispositionError(
            f"{row_id}: 'blocked:' argument {argument!r} lists the same "
            "capability set as an alternative more than once"
        )

    for i, superset_candidate in enumerate(alternatives):
        for j, other in enumerate(alternatives):
            if i != j and other < superset_candidate:
                raise DispositionError(
                    f"{row_id}: 'blocked:' argument {argument!r} lists "
                    f"{'+'.join(sorted(superset_candidate))!r} as an "
                    f"alternative, but {'+'.join(sorted(other))!r} alone "
                    "already suffices (it is a subset) -- a non-minimal set "
                    "is not a valid alternative alongside the minimal set it "
                    "is redundant with; drop it"
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
    # Idiom family names (see `conditions.py`) matched by this page's
    # script-typed condition texts, deduplicated and sorted. A row can carry
    # more than one code-111/type-12 branch (nested or sequential
    # conditionals), so this is the *set* of families recognized across all
    # of them, not a single verdict.
    #
    # REDERIVATION_PLAN.md §14.6 (Ruling 2): the generator used to discard
    # `params[1]` entirely once it had counted it, so a row's condition text
    # was invisible past `script_typed_conditions`'s bare count. This field
    # and `condition_unclassified` are what let `needs_citation` narrow from
    # "any script-typed condition at all" to "a condition this table cannot
    # explain."
    condition_families: tuple[str, ...] = ()
    # Normalized (`conditions._normalize`), deduplicated, sorted text of every
    # script-typed condition on this row that `classify_condition` could not
    # place in a family. Non-empty here is exactly the residual citation
    # burden after classification -- the plan's "15-25 rows of the 110"
    # estimate, now measurable per row instead of assumed.
    condition_unclassified: tuple[str, ...] = ()

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
    def may_be_derived(self) -> bool:
        """Whether `cosmetic` is this row's answer with no human decision --
        the population the machine-derived sidecar (`CHnn.derived.json`)
        covers, and that a dispositions file may therefore omit.

        Narrower than `may_be_cosmetic`, which only says `cosmetic` is *legal*.
        Precedence is `boundary` > `beat` > `blocked` > `cosmetic`
        (REDERIVATION_PLAN.md §14.4), so a row with a non-empty `requires` is a
        `blocked:` candidate, not a derived `cosmetic` -- CH04's gate-passed file
        chose `blocked:` on every such row. A row owing a citation needs a human
        `source`, which a derived row cannot carry. `beat` outranks `cosmetic`
        too, but beat claims live in the playtest modules, so that half is the
        checker's (`RULE_DERIVED_BEAT_CLAIMED`), not this property's. A
        forward-crossing row never gets here: a warp is state-writing.
        """
        return self.may_be_cosmetic and not self.requires and not self.needs_citation

    @property
    def needs_citation(self) -> bool:
        """Rows whose effect the manifest's structure does not determine.

        The trigger is mechanical on purpose. "Cite when the effect is
        non-obvious" fails by construction, because the author who misreads a
        design is the author who believes it is obvious.

        Narrowed 2026-09-12 (REDERIVATION_PLAN.md §14.6, Ruling 2): a
        script-typed condition no longer owes a citation on its own -- only
        an *unclassified* one does. A row whose every code-111/type-12
        condition lands in a known idiom family (`conditions.py`) needs no
        human judgment to explain; `condition_unclassified` is exactly the
        residue `classify_condition` could not place.
        """
        return bool(self.unrecognized_heads) or bool(self.condition_unclassified)

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
    # An instance can be genuinely special and legitimately refuse the
    # archetype `archetypes.classify_manifest` would otherwise prescribe for
    # it (RULE_ARCHETYPE_CONFORMANCE, checker.py). When set, this is the
    # REASON the row opts out -- not a boolean, because a boolean opt-out is
    # exactly the un-greppable rubber stamp this field exists to prevent: a
    # `True` says nothing about why, so nothing stops it from being pasted
    # onto the next row a human doesn't feel like arguing about. A row's
    # exemption is counted corpus-wide (checker.py), so growth in this field
    # is visible, not quiet drift.
    archetype_exempt: str | None = None

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
        if self.verdict == "boundary" and self.argument:
            raise DispositionError(
                f"{self.row_id}: verdict 'boundary' takes no argument, got "
                f"{self.argument!r} -- a boundary row does not name the "
                "arriving chapter or beat; see schema.py's _ARGUMENT_REQUIRED "
                "comment for why that form was rejected"
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
        if self.archetype_exempt is not None and not self.archetype_exempt.strip():
            raise DispositionError(
                f"{self.row_id}: 'archetype_exempt' must be a non-empty, non-"
                "whitespace reason, not the rubber stamp an empty string would be"
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


# Fields added 2026-09-12 (REDERIVATION_PLAN.md §14.6, Ruling 2). Every
# `reference/manifests/CHnn.manifest.json` committed before this change was
# written without them, and this branch is explicitly forbidden from
# regenerating those committed artifacts as a side effect of a schema change
# (a later, dedicated pass owns that regeneration). So this is a deliberate,
# narrow carve-out from the "both directions strict" rule stated above -- but
# it is conservative, not lenient: a missing pair of keys reads as
# "unclassified," not "classified." The actual pre-classification condition
# text is gone (the generator used to discard `params[1]` outright), so there
# is no way to recover a real verdict for these rows; defaulting
# `condition_unclassified` to empty would silently clear `needs_citation` on
# every legacy row carrying a script-typed condition, which is the opposite
# of fail-loud (CLAUDE.md §4.5) -- a stale artifact would quietly look more
# resolved than it is. Instead, a legacy row's citation obligation is
# preserved exactly as it was before this change: one placeholder residue
# entry per counted `script_typed_conditions`, until the row is regenerated
# and gets a real verdict. Any other missing field still fails loud; see
# `test_row_from_dict_rejects_a_missing_field`.
_LEGACY_UNCLASSIFIED_PLACEHOLDER = (
    "<pre-classifier manifest: condition text was discarded at generation "
    "time; regenerate this manifest to classify it>"
)


def _condition_classifier_legacy_defaults(data: dict[str, Any]) -> dict[str, list[str]]:
    script_typed_conditions = data.get("script_typed_conditions", 0) or 0
    unclassified = (
        [_LEGACY_UNCLASSIFIED_PLACEHOLDER] * script_typed_conditions
        if script_typed_conditions > 0
        else []
    )
    return {"condition_families": [], "condition_unclassified": unclassified}


def row_from_dict(data: dict[str, Any]) -> ManifestRow:
    """Rebuild a row, rejecting any key set that is not exactly the row's fields."""
    expected = {f.name for f in fields(ManifestRow)}
    if "condition_families" not in data and "condition_unclassified" not in data:
        data = {**data, **_condition_classifier_legacy_defaults(data)}
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
            "condition_families": tuple(data["condition_families"]),
            "condition_unclassified": tuple(data["condition_unclassified"]),
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
