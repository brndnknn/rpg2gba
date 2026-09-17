"""The `item_ball` archetype beat template.

Page 0 is the grant; page 1 is the "already spent" re-touch, prescribed
`cosmetic` by `chapter_manifest.archetypes` (module docstring:
`ArchetypeMatch.prescribed`) -- the operator decision of 2026-09-01 is that
`cosmetic` means **no beat by default**. `negative_beat=True` promotes it to
a real "re-touch grants nothing a second time" beat.

The self-switch letter that gates the spent page is read from the manifest
row itself (`ManifestRow.condition.self_switch_ch`), not hardcoded to "A" --
`_match_item_ball` requires it to be set on the spent page for that page to be
claimed at all (`chapter_manifest/archetypes.py`). A single-page item ball
(loosened 2026-09-10, `map068/ev018/p0`-shaped: `pbItemBall` with no page-1
remainder at all) has no spent row to read a letter from, so `item_ball_beats`
demands `self_switch_letter=` from the author in that case rather than
defaulting one, and refuses `negative_beat=True` outright since there is no
spent row to assert against.

**Declared assertions (REDERIVATION_PLAN.md §16.3 C5).** Every registered
beat now carries `assertions=declare_assertions(...)`, so the checker's
⊇-floor rule can hold the beat's body to what the RMXP source actually says.
Two source facts this template must line up with the floor, not the other
way round:

* **The item.** `item=` is author-supplied (the manifest carries no item
  identity -- `chapter_manifest.archetypes._match_item_ball`'s `params={}`),
  so it is validated at registration against the grant page's own
  `item_grant` floor assertion: the source's internal item symbol
  (`Kernel.pbItemBall(::PBItems::SYMBOL)`) is looked up in
  `reference/uranium_id_map.json`'s `items` table (CLAUDE.md §4.3's single
  source of truth for Uranium-internal-name -> expansion-constant), and the
  result must equal `item=` exactly. A mismatch fails loud at registration,
  before any ROM time is spent. The grant's quantity is read the same way --
  the body no longer assumes a flat `+1`.
* **The bag-has-room branch.** `Kernel.pbItemBall`/`Kernel.pbReceiveItem`
  IS the guard: a code-111 `if` whose `then` arm is the ordinary walk (the
  call succeeds, item lands in the bag, the self-switch flips) and whose
  `else` arm is only reachable with a full bag -- `chapter_manifest.
  conditions`'s per-family outcome table tags those `then_outcome`/
  `else_outcome` as `"always"` and `"harness"` respectively (`"harness"`:
  C2 ruling (b), a real arm reachable only via a contrived setup the harness
  cannot yet produce). `_claim_self_switch_arm` below derives which
  concrete branch row (`.../p0/b0`, `.../p0/b1`, ...) is which from that
  table and the branch's own recorded `condition_text`/`arm_kind` --
  **never a hardcoded `bN`** -- and claims only the `"always"` arm. The
  `"harness"` arm is left unclaimed; it is not this template's beat to
  assert (there is no bag-fill harness primitive yet), so it is C6's or a
  future harness feature's business.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from ...chapter_manifest.conditions import classify_condition
from ...beat_floor.assertion import RowFloor
from .. import assertions
from ..cells import approach_to, event_cell
from ..errors import ScenarioError
from . import FloorLookup, declare_assertions, facing_toward, find_match, load_chapter_rows

if TYPE_CHECKING:  # runtime import is lazy so this module works without bindings
    from ...chapter_manifest.schema import ManifestRow
    from ..chapter import ChapterBuilder
    from ..emulator import Emulator

logger = logging.getLogger(__name__)

# -- Uranium internal item name -> expansion ITEM_* constant -----------------
#
# `reference/uranium_id_map.json`'s `items` table (CLAUDE.md §4.3): the one
# place that maps a Ruby `PBItems::SYMBOL` to the `ITEM_*` constant the
# converted engine actually defines. Cached once per process, same discipline
# as `archetypes.map_uranium_id`'s `_URANIUM_ID_CACHE`.
_ITEM_CONST_CACHE: dict[str, str] | None = None


def _uranium_item_constants() -> dict[str, str]:
    global _ITEM_CONST_CACHE
    if _ITEM_CONST_CACHE is None:
        path = Path("reference/uranium_id_map.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        _ITEM_CONST_CACHE = dict(data["items"])
    return _ITEM_CONST_CACHE


def _validate_item_constant(
    *, floor_item_symbol: str, stated_item: str, map_constant: str, event_id: int,
) -> None:
    """`stated_item` (the author's `item=`) must be exactly the expansion
    constant `reference/uranium_id_map.json` mints for the source's own
    internal item symbol. Fails loud on a missing mapping (needs_engine, or
    simply not staged yet) or a disagreement -- never guessed or defaulted."""
    id_map = _uranium_item_constants()
    expected = id_map.get(floor_item_symbol)
    if expected is None:
        raise ValueError(
            f"item_ball_beats: {map_constant} event {event_id}: source item "
            f"{floor_item_symbol!r} has no entry in "
            "reference/uranium_id_map.json's 'items' table -- mint it there "
            "before authoring this beat"
        )
    if expected != stated_item:
        raise ValueError(
            f"item_ball_beats: {map_constant} event {event_id}: "
            f"item={stated_item!r} disagrees with the source -- the grant "
            f"page grants {floor_item_symbol!r}, which "
            f"reference/uranium_id_map.json maps to {expected!r} -- fix "
            "item= (the manifest/floor is the source of truth)"
        )


# -- which branch arm is the ordinary "bag has room" walk ---------------------

def _claim_self_switch_arm(
    *,
    grant_row_id: str,
    grant_floor: RowFloor,
    rows: Sequence["ManifestRow"],
    floor_lookup: FloorLookup,
    map_constant: str,
    event_id: int,
) -> tuple[str | None, tuple[str, ...]]:
    """Which row on the grant page carries the self-switch write that gates
    the spent page: the grant row itself (an unconditional write, no branch
    at all) or exactly one of its branch arms -- the arm the corpus's
    per-family outcome table (`chapter_manifest.conditions`) marks
    `"always"`, derived from the branch's own recorded condition text and
    `arm_kind`, never a hardcoded `bN`.

    Returns `(claimed_row_id_or_None, unclaimed_row_ids)`. `unclaimed_row_ids`
    lists sibling arms this call deliberately does not claim -- the
    `"harness"` arm (bag full), reachable only via a contrived setup with no
    harness primitive yet (C2 ruling (b)) -- so a caller can report them
    rather than silently drop them.
    """
    if any(a.kind == "self_switch_write" for a in grant_floor.assertions):
        return grant_row_id, ()

    branch_rows = [
        r for r in rows if r.kind == "branch" and r.parent_row_id == grant_row_id
    ]
    if not branch_rows:
        return None, ()

    always_rows: list[str] = []
    unclaimed: list[str] = []
    for r in branch_rows:
        assert r.branch is not None
        family = classify_condition(r.branch.condition_text)
        if family is None:
            raise ValueError(
                f"item_ball_beats: {map_constant} event {event_id}: branch "
                f"{r.row_id!r}'s condition {r.branch.condition_text!r} does "
                "not classify against chapter_manifest.conditions -- the "
                "normal-walk arm cannot be derived"
            )
        outcome = (
            family.then_outcome if r.branch.arm_kind == "then" else family.else_outcome
        )
        if outcome.kind == "always":
            always_rows.append(r.row_id)
        else:
            unclaimed.append(r.row_id)

    if len(always_rows) != 1:
        raise ValueError(
            f"item_ball_beats: {map_constant} event {event_id}: grant page "
            f"{grant_row_id!r} has {len(always_rows)} branch arms whose "
            f"outcome is 'always' (expected exactly 1): {always_rows} -- "
            "the normal-walk arm is ambiguous"
        )
    claimed = always_rows[0]
    claimed_floor = floor_lookup(claimed)
    if not any(a.kind == "self_switch_write" for a in claimed_floor.assertions):
        raise ValueError(
            f"item_ball_beats: {map_constant} event {event_id}: the "
            f"normal-walk branch arm {claimed!r} carries no self_switch_write "
            "in its floor -- item_ball_beats cannot assert the spent-page "
            "gate from it"
        )
    return claimed, tuple(unclaimed)


def item_ball_beats(
    builder: ChapterBuilder,
    *,
    chapter_id: str,
    map_constant: str,
    map_id: int,
    event_id: int,
    item: str,
    beat_prefix: str,
    negative_beat: bool = False,
    self_switch_letter: str | None = None,
    approach_prefer: str | None = None,
    group: str | None = None,
    manifest_rows: "tuple[ManifestRow, ...] | None" = None,
    manifest_dir=None,
    floor_lookup: FloorLookup | None = None,
) -> None:
    """Register an `item_ball` archetype's grant beat, and its spent-page
    negative beat if `negative_beat=True`.

    `item` (a plain `ITEM_*` constant string) is author-supplied -- the
    manifest's `ArchetypeMatch.params` for `item_ball` is empty
    (`chapter_manifest/archetypes.py`), because which item a `giveitem`
    call grants is not something a `ManifestRow`'s effect tags carry, only
    that one is granted at all. It IS validated now (module docstring,
    "The item.") against the generic beat floor's own `item_grant`
    assertion, through `reference/uranium_id_map.json` -- only the
    self-switch gating and the approach/facing geometry were manifest-
    derived before this; the item identity itself now is too.

    `floor_lookup=` overrides `beat_floor.lookup.floor_for_row` (tests only,
    to avoid a real `output/uranium-build/` dependency); real chapter
    modules never pass it.

    `group=` defaults to `beat_prefix` when omitted: an archetype instance's
    beats belong to one route-solver stop, exactly as a hand-authored
    chapter groups them today (`ChapterBuilder.beat`'s `group=` docstring).
    The primary beat is named exactly `beat_prefix` (not `f"{beat_prefix}_grant"`)
    because the chapter manifest dispositions this stop as bare `beat:{beat_prefix}`,
    and `_check_route_approach` looks up a node's beats by that exact name
    (`chapter_manifest/checker.py`, `RouteModel.declared_beat_cell`) -- the
    primary beat *is* the stop the disposition names. The spent-page negative
    beat keeps its descriptive `_spent` suffix; it is a satellite of the stop,
    not the stop's own identity.
    """
    resolved_group = group if group is not None else beat_prefix
    resolved_lookup: FloorLookup
    if floor_lookup is not None:
        resolved_lookup = floor_lookup
    else:
        from ...beat_floor.lookup import floor_for_row
        resolved_lookup = floor_for_row

    match = find_match(
        chapter_id, map_id, event_id, "item_ball",
        rows=manifest_rows, manifest_dir=manifest_dir,
    )
    grant_row_id = next(rid for rid, role in match.roles.items() if role == "grant")
    spent_row_id = next(
        (rid for rid, role in match.roles.items() if role == "spent"), None)

    # All manifest rows for this chapter (page AND branch), needed regardless
    # of whether a spent page exists: `_claim_self_switch_arm` below has to
    # find the grant page's own branch arms even for a single-page ball.
    all_rows = manifest_rows if manifest_rows is not None else load_chapter_rows(
        chapter_id, manifest_dir=manifest_dir)
    row_by_id = {r.row_id: r for r in all_rows}

    # A single-page item ball (chapter_manifest.archetypes._match_item_ball,
    # loosened 2026-09-10 for map068/ev018/p0-shaped instances) has no
    # "spent" role at all -- there is no remainder page to gate a negative
    # beat against. `negative_beat=True` asks for exactly that beat, so it
    # cannot be honoured here; fail loud rather than silently skip it or
    # raise a bare KeyError from the `next()` below.
    if spent_row_id is None:
        if negative_beat:
            raise ValueError(
                f"item_ball_beats: {map_constant} event {event_id}: "
                "negative_beat=True requires a 'spent' page, but this "
                "item_ball match has none (a single-page item ball with no "
                "remainder page) -- omit negative_beat= for this event"
            )
        # No page-1 condition exists to read the self-switch letter off of
        # -- that is precisely what makes this a single-page item ball. The
        # letter a page *writes* is not in the manifest at all: `Condition`
        # carries `self_switch_ch`, the letter a page READS to gate itself
        # (`chapter_manifest/schema.py`), and a single-page ball has no such
        # page. So the letter is author-supplied here, and demanded rather
        # than defaulted (CLAUDE.md 4.5): guessing "A" would assert
        # FLAG_MAP..._SSA on a ball that actually writes B, and the beat
        # would then pass or fail for the wrong reason.
        if self_switch_letter is None:
            raise ValueError(
                f"item_ball_beats: {map_constant} event {event_id}: this is a "
                "single-page item ball (no spent page), so the self-switch "
                "letter cannot be read from the manifest -- pass "
                "self_switch_letter= explicitly, citing the event's own "
                "code-123 write in output/uranium-build/maps/"
                f"Map{map_id:03d}.json"
            )
        letter = self_switch_letter
        ssa = assertions.flag_ssa(map_id, event_id, letter)
        spent_page_is_empty = False
    else:
        spent_row = row_by_id.get(spent_row_id)
        if spent_row is None or spent_row.condition is None \
                or spent_row.condition.self_switch_ch is None:
            raise ValueError(
                f"item_ball_beats: {map_constant} event {event_id}: spent row "
                f"{spent_row_id!r} carries no self_switch_ch -- "
                "chapter_manifest.archetypes._match_item_ball should have "
                "refused to match this event at all if that's true; this is "
                "unreachable unless the manifest and the classifier disagree"
            )
        letter = spent_row.condition.self_switch_ch
        if self_switch_letter is not None and self_switch_letter != letter:
            raise ValueError(
                f"item_ball_beats: {map_constant} event {event_id}: stated "
                f"self_switch_letter={self_switch_letter!r} disagrees with the "
                f"spent row's own condition ({letter!r}) -- the manifest is the "
                "source of truth when a spent page exists; drop the argument"
            )
        ssa = assertions.flag_ssa(map_id, event_id, letter)

        # Does the spent page DO anything? Some are a "nothing here" message;
        # others are an empty page whose only job is to make the ball vanish
        # once the self-switch flips. CH05's Escape Rope ball (map036/ev003)
        # is the second kind: no graphic, a single terminator command, and a
        # manifest row that records it exactly -- no effects, no script
        # heads, no other codes, nothing unhandled.
        #
        # It matters because the two shapes have OPPOSITE pass conditions. On
        # an empty page an A press starts no script, and demanding one fails
        # a beat for behaving correctly. Read from the manifest rather than
        # assumed, so a chapter whose spent page does speak still gets the
        # stronger assertion. (Only reachable when a spent row exists at
        # all -- a single-page item ball sets `spent_page_is_empty = False`
        # above and never reaches this branch.)
        spent_page_is_empty = not (
            spent_row.effects or spent_row.script_heads
            or spent_row.other_codes or spent_row.unhandled
        )

    approach = approach_to(map_constant, event_id, prefer=approach_prefer)
    facing = facing_toward(
        approach, event_cell(map_constant, event_id), caller="item_ball_beats")

    # -- floor validation + declared assertions (REDERIVATION_PLAN.md §16.3 C5)

    grant_floor = resolved_lookup(grant_row_id)
    if grant_floor.refused:
        raise ValueError(
            f"item_ball_beats: {map_constant} event {event_id}: grant row "
            f"{grant_row_id!r}'s generic floor is refused "
            f"({grant_floor.refusals}) -- item= cannot be validated and no "
            "assertions can be declared until the refusal is fixed"
        )
    item_grant_floor_assertions = [
        a for a in grant_floor.assertions if a.kind == "item_grant"]
    if len(item_grant_floor_assertions) != 1:
        raise ValueError(
            f"item_ball_beats: {map_constant} event {event_id}: grant row "
            f"{grant_row_id!r}'s floor carries "
            f"{len(item_grant_floor_assertions)} item_grant assertions "
            "(expected exactly 1) -- this is not the plain single-item-ball "
            "shape item_ball_beats assumes"
        )
    item_grant_floor_assertion = item_grant_floor_assertions[0]
    floor_item_symbol = item_grant_floor_assertion.param("item")
    grant_quantity = item_grant_floor_assertion.param("quantity")
    _validate_item_constant(
        floor_item_symbol=floor_item_symbol, stated_item=item,
        map_constant=map_constant, event_id=event_id)

    claimed_arm_row_id, unclaimed_arm_row_ids = _claim_self_switch_arm(
        grant_row_id=grant_row_id, grant_floor=grant_floor, rows=all_rows,
        floor_lookup=resolved_lookup, map_constant=map_constant, event_id=event_id)
    if unclaimed_arm_row_ids:
        logger.debug(
            "item_ball_beats: %s event %s: leaving branch arm(s) %s "
            "unclaimed (full-bag / harness outcome, no harness primitive yet)",
            map_constant, event_id, unclaimed_arm_row_ids)

    # The grant beat walks the normal (bag-has-room) arm, so it claims that
    # arm row alongside the page and declares the arm's own floor (C5 shape
    # (f)). The arm rides along under no archetype, the same way trainer.py
    # claims a win arm. The full-bag arm stays unclaimed.
    claims_arm = claimed_arm_row_id is not None and claimed_arm_row_id != grant_row_id
    grant_rows: tuple[str, ...] = (
        (grant_row_id, claimed_arm_row_id) if claims_arm else (grant_row_id,))

    # `text`/`choice` are deliberately excluded: the body never checks a
    # message box's content, only that the script ran to completion (see
    # the `trigger`/`completes` kinds below). `audio`/`visual` are
    # completion-only per R11/C4 -- declaring them adds nothing the body
    # doesn't already cover by running the page to its end, so they are
    # folded in whenever the floor happens to carry them (none do in the
    # CH01-CH05 corpus today, but a future item ball with a jingle/emote
    # should not silently go undeclared for it).
    grant_present_kinds = {a.kind for a in grant_floor.assertions}
    grant_executed_kinds = frozenset(
        {"trigger", "completes", "item_grant"}
        | (grant_present_kinds & {"audio", "visual"})
    )

    if claims_arm:
        claimed_floor = resolved_lookup(claimed_arm_row_id)
        claimed_ssw = next(
            a for a in claimed_floor.assertions if a.kind == "self_switch_write")
        if (claimed_ssw.param("event_id"), claimed_ssw.param("letter"),
                claimed_ssw.param("value")) != (event_id, letter, True):
            raise ValueError(
                f"item_ball_beats: {map_constant} event {event_id}: the "
                f"normal-walk arm {claimed_arm_row_id!r}'s self_switch_write "
                f"({claimed_ssw.params}) does not match the letter this beat "
                f"derived ({letter!r}) -- the manifest and the floor disagree"
            )
    if claimed_arm_row_id is not None:
        # The body checks the self-switch after the pickup, on whichever row
        # (arm or page trunk) the source writes it.
        grant_executed_kinds = grant_executed_kinds | frozenset({"self_switch_write"})

    grant_assertions = declare_assertions(
        grant_rows, executed_kinds=grant_executed_kinds,
        template="item_ball_beats:grant", floor_lookup=resolved_lookup,
    )

    @builder.beat(
        beat_prefix,
        f"The item ball at {map_constant} event {event_id} grants "
        f"{item} once (manifest {grant_row_id})",
        map_constant=map_constant, at=approach,
        group=resolved_group,
        archetype={grant_row_id: "item_ball"} if claims_arm else "item_ball",
        rows=grant_rows,
        assertions=grant_assertions,
    )
    def grant_beat(emu: Emulator) -> None:
        if emu.flag(ssa):
            raise ScenarioError(
                f"{beat_prefix} precondition failed: {ssa} already "
                "set before the pickup"
            )
        bag_before = emu.bag_item_quantity(item)
        emu.walk_to(*approach)
        emu.face(facing)
        emu.interact()
        emu.advance_dialog()
        if not emu.flag(ssa):
            shot = emu.screenshot(f"{beat_prefix}_no_ssa")
            raise ScenarioError(
                f"{beat_prefix}: {ssa} not set after the pickup ({shot})"
            )
        bag_after = emu.bag_item_quantity(item)
        if bag_after != bag_before + grant_quantity:
            shot = emu.screenshot(f"{beat_prefix}_bag_unchanged")
            raise ScenarioError(
                f"{beat_prefix}: self-switch {ssa} was set but "
                f"{item} did not reach the bag as expected ({bag_before} -> "
                f"{bag_after}, expected +{grant_quantity}) ({shot})"
            )

    if negative_beat:
        # Non-empty spent page: running it to completion checks `trigger`/
        # `completes`. Empty spent page: in RMXP, touching it runs nothing and
        # returns control at once, and the converter emits no script for it.
        # The body's "no script started, field not locked, bag unchanged"
        # check is exactly that behaviour, so it declares the same two kinds.
        if spent_page_is_empty:
            spent_executed_kinds: frozenset[str] = frozenset({"trigger", "completes"})
        else:
            spent_floor = resolved_lookup(spent_row_id)
            spent_present_kinds = (
                {a.kind for a in spent_floor.assertions} if not spent_floor.refused
                else set()
            )
            spent_executed_kinds = frozenset(
                {"trigger", "completes"} | (spent_present_kinds & {"audio", "visual"})
            )
        spent_assertions = declare_assertions(
            (spent_row_id,), executed_kinds=spent_executed_kinds,
            template="item_ball_beats:spent", floor_lookup=resolved_lookup,
        )

        @builder.beat(
            f"{beat_prefix}_spent",
            f"Re-touching the spent item ball at {map_constant} event "
            f"{event_id} grants nothing (manifest {spent_row_id})",
            map_constant=map_constant, at=approach,
            group=resolved_group, archetype="item_ball", rows=(spent_row_id,),
            assertions=spent_assertions,
        )
        def spent_beat(emu: Emulator) -> None:
            if not emu.flag(ssa):
                raise ScenarioError(
                    f"{beat_prefix}_spent precondition failed: {ssa} not "
                    "set -- the grant beat must run first"
                )
            bag_before = emu.bag_item_quantity(item)
            emu.walk_to(*approach)
            emu.face(facing)
            started = emu.interact(require_script=not spent_page_is_empty)
            if spent_page_is_empty and started:
                # The absence IS the assertion here: the ball is gone, so an
                # A press at its tile must hit nothing. A script running means
                # the page was emitted with a body it should not have, or the
                # self-switch never flipped and page 1 answered again.
                shot = emu.screenshot(f"{beat_prefix}_spent_unexpected_script")
                raise ScenarioError(
                    f"{beat_prefix}_spent: {spent_row_id} is an empty page, "
                    f"but interacting started a script ({shot})"
                )
            if started:
                emu.advance_dialog()
            if emu.field_locked():
                shot = emu.screenshot(f"{beat_prefix}_spent_locked")
                raise ScenarioError(
                    f"{beat_prefix}_spent: control did not return after "
                    f"touching {spent_row_id} ({shot})"
                )
            bag_after = emu.bag_item_quantity(item)
            if bag_after != bag_before:
                shot = emu.screenshot(f"{beat_prefix}_spent_regranted")
                raise ScenarioError(
                    f"{beat_prefix}_spent: re-touching the spent ball "
                    f"changed {item} ({bag_before} -> {bag_after}), "
                    f"expected no change ({shot})"
                )

        del spent_beat
