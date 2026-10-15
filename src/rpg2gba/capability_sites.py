"""Derives, for every capability token, the map-event sites that GRANT it
(`REDERIVATION_PLAN.md` P8, the seam behind `chapter_manifest.checker
.CapabilityModel`).

A `blocked:<capability>` manifest disposition has never been checked against
anything -- `CapabilityModel` has existed as a `Protocol` since the manifest
checker was written, with no implementation, so every `blocked:` row in the
corpus (28 `blocked:rock_smash` and 4 `blocked:surf` in CH04/CH05 alone)
reports `capability_model_unenforced` unconditionally. This module is the
first real derivation.

**Design (operator-decided; this is the whole point of building it this
way, so it is worth stating in full):**

Grants are keyed to the map event that grants them, NOT to a chapter.
`reference/chapters.json` is a *plan* -- 5 of 60 chapters are built, and the
rest is a proposed carve-up of maps that will change as the corpus is
re-cut. "Unblocked by CH57" rots silently the moment CH57 is re-scoped or
renumbered; `map199/ev001/p0` is a fact about the game data itself and
survives any re-plan. A chapter *owning* a map is also not the same claim as
the specific event on it being the grant -- event-level granularity is what
makes "has this actually been implemented/verified" mechanically checkable,
where a chapter-level answer could not be. A grant site's identifier is
already first-class in this system: it is a manifest `row_id`
(`chapter_manifest.schema.page_row_id`), so this module reuses that format
rather than inventing a second one (`CLAUDE.md` §4.3).

**What counts as a grant.** Every map JSON is scanned for two RGSS command
codes:

* `code 121` (Control Switches), parameters `[switch_lo, switch_hi, value]`
  with `value == 0` meaning ON and `value == 1` meaning OFF. Only an ON write
  is a grant; an OFF write is almost certainly a reset (e.g. a new-game
  initializer clearing `Got Pokemon`) and is recorded, with its direction
  visible, but never treated as granting anything (§4.5 -- silently
  dropping OFF writers would hide exactly the distinction that makes
  `map051/ev002/p0`'s two OFF writes of `Got Pokemon` legible as a reset
  rather than a second grant).
* `code 122` (Control Variables), parameters
  `[var_lo, var_hi, operation, operand_type, operand]`. A site grants a
  variable-threshold token only when `operation == 0` (Set) and
  `operand_type == 0` (Constant) -- a literal assignment to a known value.
  Any other combination (Add/Sub/Mul/Div/Mod, or an operand that is itself
  another variable/random/actor-stat/etc.) is a *computed* write: the
  derivation cannot know what value it produces without executing the game,
  so it is recorded as `determined=False` and never used to satisfy a
  threshold -- guessing here would be exactly the silent-default failure
  mode §4.5 forbids.

**Capability tokens.** `blocked:` arguments are lowercase
`^[a-z][a-z0-9_]*$` tokens (`chapter_manifest.schema`'s `_CAPABILITY_TOKEN`).
A switch's token is the bare slug of its Uranium label (`FINAL EVENT` ->
`final_event`); a variable's token is `var_`-prefixed and additionally
embeds the threshold achieved by some constant write in the corpus, because
`blocked:` specs like "Quest Log >= 4" are meaningless without a number
(`Quest Log`, value `4` -> `var_quest_log_4`). The `var_` prefix
(`PROJECT_TODO.md` #93, `REDERIVATION_PLAN.md` §10 R1, operator ruling
2026-09-10) makes the *kind* of gate legible in the disposition itself and
resolves five bases in the Uranium corpus that would otherwise name both a
switch and a variable (`final_event`, `first_strike`, `gym_2_gempuzzle`,
`gym_4_puzzle`, `dream_palace_grotto`) -- without it, `blocked:final_event`
(switch 125) and `blocked:final_event_2` (variable 127) would read as one
capability at two thresholds when they are two unrelated game objects.
`token_for_label` fail-louds (`CapabilitySitesError`) if a *switch* label
would itself slug to something starting with the reserved `var_` prefix,
since minting it would re-open that exact collision; no label in the
current corpus trips this. `s:`-prefixed switches (`uranium_switches.json`'s
runtime predicates -- self-switch checks, time-of-day) are excluded
entirely, never minting a token (`CLAUDE.md` §6). Two switches (or two
variable thresholds) slugging to the same token is a fail-loud condition
(`AmbiguousTokenError`): an ambiguous capability token is worse than no
token at all, because it would silently conflate two different in-game
facts.

**Ownership.** Each site's `map_id` is looked up in `reference/
chapters.json` for its owning chapter -- `None` if no chapter claims that
map yet, never a hard failure (a map genuinely can be unowned at this stage
of the corpus).

**Known limit: field capabilities model only the badge half of their gate.**
Uranium gates `rock_smash`/`surf`/etc. on `badge AND (move OR item)`
(**Uranium has no HMs** -- operator, 2026-09-10): completing a gym unlocks
the move, the badge permits using it in the field, and for at least some
capabilities an *item* grants the same ability. The `move OR item` half is
not a `code 121`/`code 122` write and `blocked:a|b` has no OR in its verdict
grammar, so that half stays unmodelled -- deferred to CH06
(`REDERIVATION_PLAN.md` §15.2 item 4).

The `badge` half, by contrast, IS derivable: `$Trainer.badges[N]=true` is a
literal, monotonic (never `=false` in the corpus) fact written from `code
355`/`code 655` (Script/Script continuation) commands, and Uranium's
`HIDDENMOVESCOUNTBADGES=true` setting (`reference/scripts_dump/
002__Settings.rb:144-151`) gates each field move on a simple badge COUNT
(`BADGEFORROCKSMASH=1`, `BADGEFORSURF=5`, etc.) -- not on any specific badge.
`FIELD_CAPABILITY_BADGE_COUNT` models exactly that count, and
`grant_sites`/`field_badge_requirement` expose it below. **This is necessary,
NOT sufficient**: a field token's badge count being met never confirms the
capability is actually held, because the `move OR item` conjunct could still
be missing. `chapter_manifest.capability_model.ChapterCapabilityModel`
enforces that asymmetry -- it may use the badge model to confirm a `blocked:`
claim is still correct (badge not yet met) but must never use it alone to
raise `blocked_already_granted`. Do not make these fully green by modelling
the other conjunct here; that is CH06's job. See `PROJECT_TODO.md` #92 and
`MEMORY.md` -> Uranium-Specific Discoveries.

*(2026-10-15, CH08 §9: the ITEM half is now derived for the capabilities in
`FIELD_CAPABILITY_ITEMS` -- literal grants of the HM or the alternative item
(`item_grants`). The MOVE half stays a walk fact, not a game-data fact: the
move is taught by a generated setup beat (`teach_beat_name`), and
`ChapterCapabilityModel` confirms a field capability held only from the first
chapter whose suite teaches it. Still "Uranium has no HMs" above is wrong --
corrected 2026-10-14: HM01-HM08 exist.)*
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from rpg2gba.chapter_manifest.schema import page_row_id
from rpg2gba.conversion_agent.flag_registry import load_label_tables
from rpg2gba.map_split.spec import expand_split_ids

logger = logging.getLogger(__name__)

DEFAULT_MAPS_DIR = Path("output/uranium-build/maps")
DEFAULT_SWITCHES_JSON = Path("reference/uranium_switches.json")
DEFAULT_VARIABLES_JSON = Path("reference/uranium_variables.json")
DEFAULT_CHAPTERS_JSON = Path("reference/chapters.json")

SWITCH_WRITE_CODE = 121
VARIABLE_WRITE_CODE = 122
SCRIPT_CODE = 355
SCRIPT_CONTINUATION_CODE = 655
CONDITIONAL_CODE = 111
_CONDITION_SCRIPT = 12  # code 111 parameters[0]: a Ruby script condition

# Badge-count requirement for each Uranium field capability
# (`reference/scripts_dump/002__Settings.rb:144-151`, `HIDDENMOVESCOUNTBADGES
# = true`). This models ONLY the badge-count conjunct of Uranium's real gate
# (`badge AND (move OR item)`) -- the badge is NECESSARY, NOT SUFFICIENT. The
# `move OR item` conjunct is deferred to CH06
# (`REDERIVATION_PLAN.md` §15.2 item 4); see the module docstring.
FIELD_CAPABILITY_BADGE_COUNT: dict[str, int] = {
    "cut": 3,          # BADGEFORCUT
    "flash": 0,        # BADGEFORFLASH
    "rock_smash": 1,   # BADGEFORROCKSMASH
    "strength": 4,     # BADGEFORSTRENGTH
    "surf": 5,         # BADGEFORSURF
    "dive": 7,         # BADGEFORDIVE
    "fly": 8,          # BADGEFORFLY
    "waterfall": 8,    # BADGEFORWATERFALL
}

# The `move OR item` conjunct's ITEM half, per field capability: the bag
# items whose literal grant makes the capability obtainable (CH08 §9, operator
# ruling 2026-10-15 -- "held" is derived). The HM is the move's carrier (it is
# taught from the bag); the alternative item stands in for knowing the move
# (`traversal.capabilities.PREDICATES`). Only capabilities whose HM is verified
# against the corpus are listed (HM06 is Rock Smash: granted at Map040/14000-
# 14002, taught by CH08's suite). A token absent here keeps the badge-only
# model: undetermined once the badge count is met, never confirmed held.
FIELD_CAPABILITY_ITEMS: dict[str, frozenset[str]] = {
    "rock_smash": frozenset({"HM06", "BOXINGGLOVES"}),
}

# A literal item grant: `pbReceiveItem`/`pbItemBall` (optionally `Kernel.`-
# qualified) or `$PokemonBag.pbStoreItem`, first argument a PBItems symbol.
_ITEM_GRANT_RE = re.compile(
    r"(?:pbItemBall|pbReceiveItem|pbStoreItem)\s*\(?\s*(?:::)?(?:PBItems::|:)([A-Z][A-Z0-9_]*)"
)


def teach_beat_name(token: str) -> str:
    """The beat id a generated chapter suite gives the setup beat that teaches
    field capability `token` through the bag UI (CH08 §9). The capability is
    only modelled as HELD from the first chapter whose suite contains it: the
    walk, not the game data, decides when the move is actually taught."""
    return f"teach_{token}"

# RMXP Control Variables `operation` codes (parameters[2]). Only 0 (Set) can
# ever be resolved to a known constant by this module; the rest are relative
# to whatever the variable/actor/random source already holds and are always
# `determined=False`.
_VAR_OP_SET = 0
# `operand_type` (parameters[3]). Only 0 (a literal constant) is resolvable;
# 1 (another variable), 2 (random), and the rest (item/actor/enemy/
# character/other) all depend on runtime state this module cannot see.
_VAR_OPERAND_CONSTANT = 0


class CapabilitySitesError(RuntimeError):
    """A source file is malformed, or two distinct switches/variable-
    thresholds slug to the same capability token (an ambiguous token is
    worse than none -- CLAUDE.md §4.5)."""


class AmbiguousTokenError(CapabilitySitesError):
    """Two distinct capability sources (switch ids, or a switch and a
    variable-threshold) produced the same token string."""


_CAPABILITY_TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")
_DROP = re.compile(r"['.]")
_SEP = re.compile(r"[^A-Za-z0-9]+")

# `$Trainer.badges[N]=true` inside a code-355/655 Script command's text
# parameter. Whitespace-tolerant around `=` and the brackets; case is fixed
# by Uranium's own convention (`$Trainer`, `badges`) so not folded.
_BADGE_TRUE_RE = re.compile(r"\$Trainer\.badges\[\s*(\d+)\s*\]\s*=\s*true")
_BADGE_FALSE_RE = re.compile(r"\$Trainer\.badges\[\s*(\d+)\s*\]\s*=\s*false")


def _fold_accents(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


_VARIABLE_TOKEN_PREFIX = "var_"


def token_for_label(
    label: str, *, kind: Literal["switch", "variable"] = "switch"
) -> str:
    """Slug a Uranium switch/variable label into a `blocked:` capability
    token (`^[a-z][a-z0-9_]*$`).

    `"FINAL EVENT"` -> `"final_event"` (switch), `"Got Pokemon"` ->
    `"got_pokemon"` (switch), `"Quest Log"` -> `"var_quest_log"` (variable,
    before a threshold suffix is appended by the caller). Mirrors
    `pbs_converter._naming.to_constant`'s cleaning rules (drop apostrophes/
    periods, fold accents, collapse non-alphanumeric runs to one underscore)
    but lowercases instead of upper-casing -- a `blocked:` capability token
    is a different vocabulary from a C constant, and `_CAPABILITY_TOKEN`'s
    grammar is lowercase-first, not `PREFIX_UPPER`.

    `kind="variable"` prefixes the slug with `var_` (`PROJECT_TODO.md` #93,
    `REDERIVATION_PLAN.md` §10 R1): a switch's token names a boolean story
    gate directly, while a variable's token needs a threshold appended by
    the caller (`Quest Log` @ 4 -> `var_quest_log_4`) and the prefix makes
    the *kind* of gate legible in the disposition itself. `kind="switch"`
    (the default) keeps the bare slug -- switches are the common case and
    stay unprefixed so a plain boolean gate like `blocked:got_pokemon`
    reads with no noise.

    Raises `CapabilitySitesError` if the label slugs to nothing at all (a
    label that is only punctuation) -- that is not a valid token under any
    rule and must not silently become an empty string. Also raises for
    `kind="switch"` if the slug itself starts with the reserved `var_`
    prefix -- minting it would re-open the exact collision the prefix
    exists to prevent (a switch and a variable both claiming the same base
    name), so this fails loud rather than mint an ambiguous-looking token.
    """
    cleaned = _DROP.sub("", _fold_accents(label))
    snake = _SEP.sub("_", cleaned).strip("_").lower()
    if not snake:
        raise CapabilitySitesError(
            f"label {label!r} slugs to an empty capability token"
        )
    if not snake[0].isalpha():
        # `_CAPABILITY_TOKEN` requires a leading lowercase letter; a label
        # that starts with a digit (rare, but the sidecars are hand-authored
        # Uranium prose) would otherwise produce an invalid token silently.
        snake = f"c_{snake}"
    if kind == "switch":
        if snake.startswith(_VARIABLE_TOKEN_PREFIX):
            raise CapabilitySitesError(
                f"switch label {label!r} slugs to {snake!r}, which starts "
                f"with the reserved {_VARIABLE_TOKEN_PREFIX!r} prefix -- "
                "that prefix is reserved for variable-derived tokens "
                "(PROJECT_TODO.md #93) and minting it for a switch would "
                "re-open the exact base-name collision the prefix exists "
                "to prevent; rename the switch label"
            )
        return snake
    return f"{_VARIABLE_TOKEN_PREFIX}{snake}"


@dataclass(frozen=True)
class SwitchWriteSite:
    """One `code 121` Control Switches command."""

    row_id: str
    map_id: int
    event_id: int
    page_idx: int
    switch_id: int
    switch_label: str
    direction: str  # "on" | "off"
    chapter_id: str | None


@dataclass(frozen=True)
class VariableWriteSite:
    """One `code 122` Control Variables command."""

    row_id: str
    map_id: int
    event_id: int
    page_idx: int
    variable_id: int
    variable_label: str
    determined: bool
    value: int | None  # the constant assigned, only when `determined`
    chapter_id: str | None


@dataclass(frozen=True)
class BadgeWriteSite:
    """One `$Trainer.badges[N]=true` write, found inside a `code 355`
    (Script) or `code 655` (Script continuation) command's text. Badges are
    never revoked in the corpus (no `=false` write exists); a `=false` write,
    if ever found, raises `CapabilitySitesError` rather than silently
    breaking the monotonic-count assumption `FIELD_CAPABILITY_BADGE_COUNT`
    relies on."""

    row_id: str
    map_id: int
    event_id: int
    page_idx: int
    badge_index: int
    chapter_id: str | None


@dataclass(frozen=True)
class ItemGrantSite:
    """One literal grant of a `FIELD_CAPABILITY_ITEMS` item (an HM, or an
    alternative item such as BOXINGGLOVES) in a `code 355`/`655` script."""

    row_id: str
    map_id: int
    event_id: int
    page_idx: int
    item: str
    chapter_id: str | None


@dataclass(frozen=True)
class CapabilitySite:
    """One site that grants a capability token -- the row-level fact
    `chapter_manifest.checker.CapabilityGrant` is built from."""

    token: str
    row_id: str
    map_id: int
    chapter_id: str | None
    detail: str


@dataclass
class CapabilityDerivation:
    """The full result: every capability token discovered from the corpus,
    and, for each, either its grant sites or the fact that it is
    undetermined.

    `grant_sites(token)` is the three-state query
    `chapter_manifest.checker.CapabilityModel` needs:

      * `token` never traced back to any switch/variable at all (not in
        `_token_sources`) -> `None`: this module has no data source for it
        whatsoever (e.g. `rock_smash`/`surf` -- terrain-tag HM capabilities
        with no switch/variable representation in the corpus at all; see
        the module docstring's note on `_HEAD_REQUIRES`'s identical gap).
      * `token` traces to a source, but that source's writes never
        constant-satisfy it (a switch never turned ON anywhere, or a
        variable-threshold token whose only writes are computed) -- see the
        two sub-cases below.
      * non-empty -- the sites themselves.
    """

    switch_writes: tuple[SwitchWriteSite, ...] = field(default_factory=tuple)
    variable_writes: tuple[VariableWriteSite, ...] = field(default_factory=tuple)
    badge_writes: tuple[BadgeWriteSite, ...] = field(default_factory=tuple)
    item_grants: tuple[ItemGrantSite, ...] = field(default_factory=tuple)
    _grants: dict[str, tuple[CapabilitySite, ...]] = field(default_factory=dict)
    # token -> True if at least one source contributing to it had an
    # unresolved (computed) write that COULD have satisfied it but couldn't
    # be evaluated -- distinguishes "confidently nothing grants this" (empty
    # tuple, no such source) from "we cannot rule out that something does"
    # (None, a source exists but is inconclusive).
    _undetermined: set[str] = field(default_factory=set)
    # token -> the source(s) that produced it, for collision detection and
    # reporting; not consulted by grant_sites itself.
    token_sources: dict[str, tuple[tuple[str, int], ...]] = field(default_factory=dict)
    # base token (no threshold suffix) -> variable id, so `grant_sites` can
    # answer a threshold nobody happened to write. See `_resolve_threshold`.
    variable_tokens: dict[str, int] = field(default_factory=dict)
    # NOTE: a prior revision tracked `colliding_bases` here -- bases where a
    # switch label and a variable label slugged the same way, so `<base>`
    # named the switch and `<base>_<n>` named the VARIABLE (five such bases
    # existed: `final_event`, `first_strike`, `gym_2_gempuzzle`,
    # `gym_4_puzzle`, `dream_palace_grotto`). `token_for_label`'s `var_`
    # prefix on variable-derived tokens (`PROJECT_TODO.md` #93,
    # `REDERIVATION_PLAN.md` §10 R1) removed the collision by construction:
    # a variable's base is now always `var_<slug>`, and `token_for_label`
    # fail-louds if a switch label would itself slug to a `var_`-prefixed
    # string. With the guard in place, `<base>` (switch) and
    # `var_<base>_<n>` (variable) can no longer read as the same capability
    # at two thresholds, so there is nothing left to detect or report here.

    def grant_sites(self, token: str) -> tuple[CapabilitySite, ...] | None:
        if token in FIELD_CAPABILITY_BADGE_COUNT:
            return self._field_capability_grant_sites(token)
        if token in self._grants:
            return self._grants[token]
        if token in self._undetermined:
            return None
        if token in self.token_sources:
            # A known source exists (e.g. a switch that is only ever turned
            # OFF), and nothing marked it undetermined -- a confident
            # "nothing grants this."
            return ()
        # Not pre-minted. For a variable threshold that is still answerable:
        # tokens are minted only for thresholds the corpus actually writes,
        # so `quest_log_2` and `quest_log_4` exist (var 101 is set to 2 and
        # to 4) while `quest_log_1` does not -- even though both writes
        # satisfy >= 1 and the answer is therefore knowable. Returning None
        # there would report "cannot tell" for a question with an answer,
        # and would silently miss `RULE_BLOCKED_ALREADY_GRANTED` on the 12
        # CH01 rows gated `Quest Log >= 1`. Compute it instead.
        return self._resolve_threshold(token)

    def _field_capability_grant_sites(
        self, token: str
    ) -> tuple[CapabilitySite, ...]:
        """`grant_sites` for a field-capability token
        (`FIELD_CAPABILITY_BADGE_COUNT`).

        Corpus-wide only: every badge write anywhere is a candidate site,
        because ANY badge write grows the player's total badge count, and it
        is the COUNT (not a specific badge) the token's requirement is
        checked against. This module has no notion of "as of this chapter"
        -- that chain-scoped judgment belongs to
        `chapter_manifest.capability_model.ChapterCapabilityModel`, which
        decides, from these same sites plus its predecessor chain, whether
        the count is actually met yet.

        Returns `()` only when the corpus has zero badge writes at all
        (nothing could ever satisfy any field token) -- never based on the
        token's own required count, since even `flash`'s
        `BADGEFORFLASH == 0` requirement is still "met" by the existence of
        the badge-count mechanism itself; distinguishing "always met" from
        "not yet met" is the adapter's job (module docstring)."""
        required = FIELD_CAPABILITY_BADGE_COUNT[token]
        if not self.badge_writes:
            return ()
        return tuple(
            CapabilitySite(
                token=token,
                row_id=w.row_id,
                map_id=w.map_id,
                chapter_id=w.chapter_id,
                detail=(
                    f"badge {w.badge_index} -> true (field capability "
                    f"{token!r} needs >= {required} badge"
                    f"{'s' if required != 1 else ''})"
                ),
            )
            for w in self.badge_writes
        )

    def field_badge_requirement(self, token: str) -> int | None:
        """The required badge COUNT for a field-capability token, or `None`
        if `token` is not one of `FIELD_CAPABILITY_BADGE_COUNT`'s keys."""
        return FIELD_CAPABILITY_BADGE_COUNT.get(token)

    def field_item_requirement(self, token: str) -> frozenset[str] | None:
        """The items (any one suffices) that satisfy a field capability's
        item conjunct, or `None` when that conjunct is unmodelled for `token`
        (`FIELD_CAPABILITY_ITEMS`)."""
        return FIELD_CAPABILITY_ITEMS.get(token)

    def item_grant_sites(self, token: str) -> tuple[CapabilitySite, ...]:
        """Every literal grant of one of `token`'s items, as capability sites."""
        items = FIELD_CAPABILITY_ITEMS.get(token, frozenset())
        return tuple(
            CapabilitySite(
                token=token,
                row_id=g.row_id,
                map_id=g.map_id,
                chapter_id=g.chapter_id,
                detail=f"item {g.item} granted (field capability {token!r})",
            )
            for g in self.item_grants
            if g.item in items
        )

    def _resolve_threshold(self, token: str) -> tuple[CapabilitySite, ...] | None:
        """Answer an un-minted `<variable>_<threshold>` token from the raw
        writes, with the same three-state contract as `grant_sites`.

        None when no constant write reaches the threshold but the variable
        also has computed writes -- one of those could reach it and this
        module refuses to guess (§4.5). `()` only when no constant write
        reaches it and there are no computed writes either, which is a
        confident "nothing grants this"."""
        base, _, suffix = token.rpartition("_")
        if not base or not suffix.isdigit():
            return None
        var_id = self.variable_tokens.get(base)
        if var_id is None:
            return None
        threshold = int(suffix)
        writes = [w for w in self.variable_writes if w.variable_id == var_id]
        qualifying = tuple(
            CapabilitySite(
                token=token,
                row_id=w.row_id,
                map_id=w.map_id,
                chapter_id=w.chapter_id,
                detail=(
                    f"var {var_id} ({w.variable_label!r}) set to {w.value} "
                    f"(>= {threshold})"
                ),
            )
            for w in writes
            if w.determined and w.value is not None and w.value >= threshold
        )
        if qualifying:
            return qualifying
        if any(not w.determined for w in writes):
            return None
        return ()

    @property
    def tokens(self) -> tuple[str, ...]:
        return tuple(sorted(self.token_sources))

    @property
    def undetermined_tokens(self) -> frozenset[str]:
        return frozenset(self._undetermined)

    def format(self) -> str:
        """CLI report: token counts and every token this derivation could
        not resolve, plus which tokens have zero grant sites at all."""
        unreachable = sorted(
            t for t in self.tokens
            if t not in self._grants and t not in self._undetermined
        )
        lines = [
            f"{len(self.tokens)} capability token(s) derived from "
            f"{len(self.switch_writes)} switch write(s) and "
            f"{len(self.variable_writes)} variable write(s):",
            f"  {len(self._grants)} granted (at least one site)",
            f"  {len(unreachable)} with zero grant sites anywhere "
            "(unreachable, not undetermined)",
            f"  {len(self._undetermined)} undetermined (a computed write "
            "could not be resolved to a constant)",
        ]
        if unreachable:
            lines.append(f"  zero-grant-site tokens: {unreachable}")
        if self._undetermined:
            lines.append(f"  undetermined tokens: {sorted(self._undetermined)}")
        return "\n".join(lines)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _map_id_to_chapter(chapters_json: Path) -> dict[int, str | None]:
    """`{map_id: owning chapter_id}` for every map named anywhere in
    `chapters.json`; a map not named by any chapter is simply absent (looked
    up with `.get(map_id)`, defaulting to `None`, never a failure -- a
    corpus map genuinely can be unowned at this stage)."""
    data = _load_json(chapters_json)
    owner: dict[int, str] = {}
    for chapter in data.get("chapters", []):
        chapter_id = chapter["id"]
        for map_id in expand_split_ids(chapter.get("maps", [])):
            owner.setdefault(map_id, chapter_id)
    return owner


def _iter_map_files(maps_dir: Path) -> list[Path]:
    return sorted(maps_dir.glob("Map*.json"))


def _scan_writes(
    maps_dir: Path,
    switch_labels: dict[int, str],
    var_labels: dict[int, str],
    script_switches: frozenset[int],
    map_owner: dict[int, str | None],
) -> tuple[
    list[SwitchWriteSite], list[VariableWriteSite], list[BadgeWriteSite], list[ItemGrantSite]
]:
    switch_writes: list[SwitchWriteSite] = []
    variable_writes: list[VariableWriteSite] = []
    badge_writes: list[BadgeWriteSite] = []
    item_grants: list[ItemGrantSite] = []
    field_items = frozenset().union(*FIELD_CAPABILITY_ITEMS.values())

    for path in _iter_map_files(maps_dir):
        data = _load_json(path)
        for event in data.get("events", []):
            event_id = event.get("id")
            for page_idx, page in enumerate(event.get("pages", [])):
                for cmd in page.get("list", []) or []:
                    code = cmd.get("code")
                    params = cmd.get("parameters") or []
                    if code == SWITCH_WRITE_CODE:
                        if len(params) < 3:
                            continue
                        sw_lo, sw_hi, value = params[0], params[1], params[2]
                        row_id = page_row_id(data["map_id"], event_id, page_idx)
                        for switch_id in range(sw_lo, sw_hi + 1):
                            if switch_id in script_switches:
                                continue
                            label = switch_labels.get(switch_id)
                            if label is None:
                                continue
                            switch_writes.append(SwitchWriteSite(
                                row_id=row_id,
                                map_id=data["map_id"],
                                event_id=event_id,
                                page_idx=page_idx,
                                switch_id=switch_id,
                                switch_label=label,
                                direction="on" if value == 0 else "off",
                                chapter_id=map_owner.get(data["map_id"]),
                            ))
                    elif code == VARIABLE_WRITE_CODE:
                        if len(params) < 5:
                            continue
                        var_lo, var_hi, operation, operand_type, operand = params[:5]
                        row_id = page_row_id(data["map_id"], event_id, page_idx)
                        determined = (
                            operation == _VAR_OP_SET
                            and operand_type == _VAR_OPERAND_CONSTANT
                        )
                        for var_id in range(var_lo, var_hi + 1):
                            label = var_labels.get(var_id)
                            if label is None:
                                continue
                            variable_writes.append(VariableWriteSite(
                                row_id=row_id,
                                map_id=data["map_id"],
                                event_id=event_id,
                                page_idx=page_idx,
                                variable_id=var_id,
                                variable_label=label,
                                determined=determined,
                                value=operand if determined else None,
                                chapter_id=map_owner.get(data["map_id"]),
                            ))
                    elif code == CONDITIONAL_CODE:
                        # `if Kernel.pbReceiveItem(...)` -- the usual shape of
                        # an item grant (the call returns false on a full bag).
                        # Only item grants are read from conditions; badge
                        # writes are statements.
                        if len(params) < 2 or params[0] != _CONDITION_SCRIPT:
                            continue
                        if not isinstance(params[1], str):
                            continue
                        for m in _ITEM_GRANT_RE.finditer(params[1]):
                            if m.group(1) not in field_items:
                                continue
                            item_grants.append(ItemGrantSite(
                                row_id=page_row_id(data["map_id"], event_id, page_idx),
                                map_id=data["map_id"],
                                event_id=event_id,
                                page_idx=page_idx,
                                item=m.group(1),
                                chapter_id=map_owner.get(data["map_id"]),
                            ))
                    elif code in (SCRIPT_CODE, SCRIPT_CONTINUATION_CODE):
                        text = params[0] if params else None
                        if not isinstance(text, str):
                            continue
                        false_match = _BADGE_FALSE_RE.search(text)
                        if false_match:
                            row_id = page_row_id(data["map_id"], event_id, page_idx)
                            raise CapabilitySitesError(
                                f"{row_id}: writes "
                                f"badges[{false_match.group(1)}]=false -- the "
                                "field-capability badge-count model "
                                "(FIELD_CAPABILITY_BADGE_COUNT) assumes "
                                "badges are monotonic (never revoked); a "
                                "revocation must be handled explicitly, not "
                                "silently dropped"
                            )
                        for m in _BADGE_TRUE_RE.finditer(text):
                            row_id = page_row_id(data["map_id"], event_id, page_idx)
                            badge_writes.append(BadgeWriteSite(
                                row_id=row_id,
                                map_id=data["map_id"],
                                event_id=event_id,
                                page_idx=page_idx,
                                badge_index=int(m.group(1)),
                                chapter_id=map_owner.get(data["map_id"]),
                            ))
                        for m in _ITEM_GRANT_RE.finditer(text):
                            if m.group(1) not in field_items:
                                continue
                            item_grants.append(ItemGrantSite(
                                row_id=page_row_id(data["map_id"], event_id, page_idx),
                                map_id=data["map_id"],
                                event_id=event_id,
                                page_idx=page_idx,
                                item=m.group(1),
                                chapter_id=map_owner.get(data["map_id"]),
                            ))
    return switch_writes, variable_writes, badge_writes, item_grants


def _register_token(
    token_sources: dict[str, list[tuple[str, int]]],
    token: str,
    source: tuple[str, int],
) -> None:
    existing = token_sources.setdefault(token, [])
    if existing and existing[0] != source and source not in existing:
        raise AmbiguousTokenError(
            f"capability token {token!r} is produced by more than one source: "
            f"{existing[0]} and {source} -- an ambiguous token is worse than "
            "no token; rename one of the underlying switch/variable labels "
            "or handle the collision explicitly before trusting this "
            "derivation"
        )
    if source not in existing:
        existing.append(source)


def derive_capability_sites(
    maps_dir: Path = DEFAULT_MAPS_DIR,
    switches_json: Path = DEFAULT_SWITCHES_JSON,
    variables_json: Path = DEFAULT_VARIABLES_JSON,
    chapters_json: Path = DEFAULT_CHAPTERS_JSON,
) -> CapabilityDerivation:
    """The full derivation: scan every map JSON under `maps_dir` for `code
    121`/`code 122` writes, mint a capability token per switch and per
    variable-threshold achieved by a constant write, and resolve each
    token's grant sites (or mark it undetermined). See the module docstring
    for the full design.
    """
    switch_labels, var_labels = load_label_tables(switches_json, variables_json)
    script_switches = frozenset(
        sid for sid, label in switch_labels.items() if label.startswith("s:")
    )
    map_owner = _map_id_to_chapter(chapters_json)

    switch_writes, variable_writes, badge_writes, item_grants = _scan_writes(
        maps_dir, switch_labels, var_labels, script_switches, map_owner
    )

    token_sources: dict[str, list[tuple[str, int]]] = {}
    variable_tokens: dict[str, int] = {}
    grants: dict[str, list[CapabilitySite]] = {}
    undetermined: set[str] = set()

    # -- switches: one token per switch id, grant sites = every ON write ---
    by_switch: dict[int, list[SwitchWriteSite]] = {}
    for w in switch_writes:
        by_switch.setdefault(w.switch_id, []).append(w)

    for switch_id, writes in by_switch.items():
        label = writes[0].switch_label
        token = token_for_label(label, kind="switch")
        if token in FIELD_CAPABILITY_BADGE_COUNT:
            raise CapabilitySitesError(
                f"switch {switch_id} ({label!r}) slugs to {token!r}, which "
                "is a reserved field-capability token "
                "(FIELD_CAPABILITY_BADGE_COUNT) -- minting a switch-derived "
                "token with the same name would silently shadow the "
                "badge-count model; rename the switch label"
            )
        _register_token(token_sources, token, ("switch", switch_id))
        on_sites = [
            CapabilitySite(
                token=token,
                row_id=w.row_id,
                map_id=w.map_id,
                chapter_id=w.chapter_id,
                detail=f"switch {switch_id} ({label!r}) -> ON",
            )
            for w in writes if w.direction == "on"
        ]
        if on_sites:
            grants.setdefault(token, []).extend(on_sites)

    # -- variables: one token per (variable, achieved constant threshold) --
    by_variable: dict[int, list[VariableWriteSite]] = {}
    for w in variable_writes:
        by_variable.setdefault(w.variable_id, []).append(w)

    for var_id, writes in by_variable.items():
        label = writes[0].variable_label
        base_token = token_for_label(label, kind="variable")
        determined_values = sorted({
            w.value for w in writes if w.determined and w.value is not None
        })
        has_undetermined_write = any(not w.determined for w in writes)

        variable_tokens[base_token] = var_id

        for threshold in determined_values:
            token = f"{base_token}_{threshold}"
            _register_token(token_sources, token, ("variable", var_id))
            qualifying = [
                CapabilitySite(
                    token=token,
                    row_id=w.row_id,
                    map_id=w.map_id,
                    chapter_id=w.chapter_id,
                    detail=(
                        f"var {var_id} ({label!r}) set to {w.value} "
                        f"(>= {threshold})"
                    ),
                )
                for w in writes
                if w.determined and w.value is not None and w.value >= threshold
            ]
            if qualifying:
                grants.setdefault(token, []).extend(qualifying)
            elif has_undetermined_write:
                undetermined.add(token)

        # A variable that is ONLY ever written by computed operations (no
        # constant write at all, so `determined_values` is empty) still
        # needs its token space represented as inconclusive rather than
        # silently invisible -- but with no achieved constant, there is no
        # threshold to name a token after, so nothing is registered for it
        # here. Recorded only in `variable_writes` for visibility.

    derivation = CapabilityDerivation(
        switch_writes=tuple(switch_writes),
        variable_writes=tuple(variable_writes),
        badge_writes=tuple(badge_writes),
        item_grants=tuple(item_grants),
        _grants={t: tuple(sites) for t, sites in grants.items()},
        _undetermined=undetermined,
        token_sources={t: tuple(s) for t, s in token_sources.items()},
        variable_tokens=variable_tokens,
    )
    return derivation


__all__ = [
    "AmbiguousTokenError",
    "BadgeWriteSite",
    "CapabilityDerivation",
    "CapabilitySite",
    "CapabilitySitesError",
    "FIELD_CAPABILITY_BADGE_COUNT",
    "FIELD_CAPABILITY_ITEMS",
    "ItemGrantSite",
    "SwitchWriteSite",
    "VariableWriteSite",
    "derive_capability_sites",
    "teach_beat_name",
    "token_for_label",
]


# --- CLI ---------------------------------------------------------------------
#
# The command itself is defined once, in `pipeline.py` as
# `rpg2gba capability-sites` (§4.3), mirroring `slice_growth.py`/
# `seam_growth.py`. This module form just delegates, so both invocations are
# the same code path.

if __name__ == "__main__":  # pragma: no cover
    from rpg2gba.pipeline import capability_sites_cmd

    raise SystemExit(capability_sites_cmd(standalone_mode=True))
