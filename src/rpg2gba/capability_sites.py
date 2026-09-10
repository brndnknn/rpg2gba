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
A switch's token is the slug of its Uranium label (`FINAL EVENT` ->
`final_event`); a variable's token additionally embeds the threshold
achieved by some constant write in the corpus, because `blocked:` specs like
"Quest Log >= 4" are meaningless without a number (`Quest Log`, value `4` ->
`quest_log_4`). `s:`-prefixed switches (`uranium_switches.json`'s runtime
predicates -- self-switch checks, time-of-day) are excluded entirely, never
minting a token (`CLAUDE.md` §6). Two switches (or a switch and a variable
threshold) slugging to the same token is a fail-loud condition
(`AmbiguousTokenError`): an ambiguous capability token is worse than no
token at all, because it would silently conflate two different in-game
facts.

**Ownership.** Each site's `map_id` is looked up in `reference/
chapters.json` for its owning chapter -- `None` if no chapter claims that
map yet, never a hard failure (a map genuinely can be unowned at this stage
of the corpus).

**Known limit: field capabilities are invisible to this module, by nature
rather than by omission.** `rock_smash` and `surf` resolve to nothing here,
so CH04's 28 `blocked:rock_smash` rows and CH05's 4 `blocked:surf` rows stay
`capability_model_unenforced`. **Uranium has no HMs** (operator, 2026-09-10):
completing a gym unlocks the move, the badge permits using it in the field,
and for at least some capabilities an *item* grants the same ability -- so
the real gate is `badge AND (move OR item)`. None of that is a `code 121` or
`code 122` write, so extending the scan cannot reach it; and `blocked:a|b`
means AND-of-a-set with no OR, so the disjunction has no representation in
the verdict grammar either. Leaving these *unenforced* is the correct state:
it is an honest "not checked", not a silent pass. Do not make them green by
inventing a grant site. See `PROJECT_TODO.md` #92 and `MEMORY.md` ->
Uranium-Specific Discoveries.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from rpg2gba.chapter_manifest.schema import page_row_id
from rpg2gba.conversion_agent.flag_registry import load_label_tables

logger = logging.getLogger(__name__)

DEFAULT_MAPS_DIR = Path("output/uranium-build/maps")
DEFAULT_SWITCHES_JSON = Path("reference/uranium_switches.json")
DEFAULT_VARIABLES_JSON = Path("reference/uranium_variables.json")
DEFAULT_CHAPTERS_JSON = Path("reference/chapters.json")

SWITCH_WRITE_CODE = 121
VARIABLE_WRITE_CODE = 122

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


def _fold_accents(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def token_for_label(label: str) -> str:
    """Slug a Uranium switch/variable label into a `blocked:` capability
    token (`^[a-z][a-z0-9_]*$`).

    `"FINAL EVENT"` -> `"final_event"`, `"Got Pokemon"` -> `"got_pokemon"`.
    Mirrors `pbs_converter._naming.to_constant`'s cleaning rules (drop
    apostrophes/periods, fold accents, collapse non-alphanumeric runs to one
    underscore) but lowercases instead of upper-casing -- a `blocked:`
    capability token is a different vocabulary from a C constant, and
    `_CAPABILITY_TOKEN`'s grammar is lowercase-first, not `PREFIX_UPPER`.

    Raises `CapabilitySitesError` if the label slugs to nothing at all (a
    label that is only punctuation) -- that is not a valid token under any
    rule and must not silently become an empty string.
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
    return snake


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
    # Bases where a switch label and a variable label slug the same way, so
    # `<base>` names the switch and `<base>_<n>` names the VARIABLE -- two
    # unrelated game objects behind near-identical tokens. Not an
    # `AmbiguousTokenError`: no two tokens actually collide, each resolves
    # deterministically, and raising would break a derivation that is
    # otherwise correct. But `blocked:final_event` (switch 125) and
    # `blocked:final_event_2` (variable 127) read as one capability at two
    # thresholds and are not, so this is surfaced rather than left for a
    # reviewer to not notice (CLAUDE.md §4.5).
    colliding_bases: dict[str, tuple[int, int]] = field(default_factory=dict)

    def grant_sites(self, token: str) -> tuple[CapabilitySite, ...] | None:
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
        for map_id in chapter.get("maps", []):
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
) -> tuple[list[SwitchWriteSite], list[VariableWriteSite]]:
    switch_writes: list[SwitchWriteSite] = []
    variable_writes: list[VariableWriteSite] = []

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
    return switch_writes, variable_writes


def _switch_variable_base_collisions(
    token_sources: dict[str, list[tuple[str, int]]],
    variable_tokens: dict[str, int],
) -> dict[str, tuple[int, int]]:
    """Bases claimed by both a switch label and a variable label.

    Five exist in the Uranium corpus as of 2026-09-10 (`final_event`,
    `first_strike`, `gym_2_gempuzzle`, `gym_4_puzzle`,
    `dream_palace_grotto`). Reported, not raised -- see `colliding_bases`."""
    collisions: dict[str, tuple[int, int]] = {}
    for base, var_id in variable_tokens.items():
        switch_ids = [i for kind, i in token_sources.get(base, []) if kind == "switch"]
        if switch_ids:
            collisions[base] = (switch_ids[0], var_id)
    if collisions:
        logger.warning(
            "%d capability base token(s) name both a switch and a variable, "
            "so `<base>` and `<base>_<n>` refer to different game objects: %s",
            len(collisions), sorted(collisions),
        )
    return collisions


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

    switch_writes, variable_writes = _scan_writes(
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
        token = token_for_label(label)
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
        base_token = token_for_label(label)
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
        _grants={t: tuple(sites) for t, sites in grants.items()},
        _undetermined=undetermined,
        token_sources={t: tuple(s) for t, s in token_sources.items()},
        variable_tokens=variable_tokens,
        colliding_bases=_switch_variable_base_collisions(
            token_sources, variable_tokens),
    )
    return derivation


__all__ = [
    "AmbiguousTokenError",
    "CapabilityDerivation",
    "CapabilitySite",
    "CapabilitySitesError",
    "SwitchWriteSite",
    "VariableWriteSite",
    "derive_capability_sites",
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
