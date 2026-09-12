"""Unit tests for the pushable-Strength-boulder native object-template idiom
(REDERIVATION_PLAN.md §15.1 item 8 — the third ``TF_KIND_*`` instance, after
item balls and berry trees).

``pbPushThisBoulder`` (``reference/scripts_dump/101__PField_Field.rb:2850``)
is a zero-arg predicate gated on ``$PokemonMap.strengthUsed``. The five
corpus rows currently staged (Map019 EV1/2/3, Map031 EV1/37 — verified
against ``output/uranium-build/transpile_unhandled.jsonl``, which lists
exactly 5 ``pbPushThisBoulder`` entries, matching the plan's claimed count)
are all single-page "Boulder" events whose entire body is a bare
``pbPushThisBoulder`` script call (code 355), sometimes followed by an SE
row, then the page terminator — the whole event IS the native object
placement, exactly like an item ball or berry tree.

The push itself is already native pokeemerald-expansion
(``OBJ_EVENT_GFX_PUSHABLE_BOULDER`` — ``engine/include/constants/
event_objects.h:113`` — and ``TryPushBoulder``/``Task_PushBoulder`` in
``engine/src/field_player_avatar.c``), so no ``engine/`` change is needed;
only the transpiler-side detector (``T.detect_push_boulder``) and its wiring
into ``T.resolve_native_object_template`` are this change's scope.

Builders mirror ``tests/test_transpiler_native.py`` (local per file-ownership
convention): an event is ``{id, name, x, y, pages:[...]}``, each page
``{trigger, list, ...}`` with ``list`` a sequence of ``{code, indent,
parameters}`` commands.
"""
from __future__ import annotations

from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

# ----------------------------------------------------------------------------
# builders
# ----------------------------------------------------------------------------


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def make_event(
    pages_cmds: list[list[dict]], trigger: int = 0, id: int = 5, name: str = "npc",
) -> dict:
    pages = [{"trigger": trigger, "list": cmds} for cmds in pages_cmds]
    return {"id": id, "name": name, "x": 0, "y": 0, "pages": pages}


def _boulder_event(*, id: int = 1, name: str = "Boulder", with_se: bool = False) -> dict:
    """Reproduces the real corpus shape exactly: a single page whose body is
    the bare script call, optionally an SE row (Map019's variant carries
    "037-Switch06"; Map031's does not), then the terminator."""
    page = [cmd(T.SCRIPT, ["pbPushThisBoulder"])]
    if with_se:
        page.append(cmd(250, [{"name": "037-Switch06", "volume": 80, "pitch": 150}]))
    page.append(cmd(0))
    return make_event([page], id=id, name=name)


def _resolve_ctx() -> T.TranspileContext:
    return T.TranspileContext(registry=FlagRegistry())


# ----------------------------------------------------------------------------
# T.detect_push_boulder
# ----------------------------------------------------------------------------


def test_detect_push_boulder_bare_call_matches() -> None:
    event = _boulder_event()
    assert T.detect_push_boulder(event) is True


def test_detect_push_boulder_with_se_row_still_matches() -> None:
    """Map019's variant (EV1/2/3) carries a Play SE row the Map031 variant
    (EV1/37) doesn't — detection must not key on the page's full command
    list, only on the presence of the bare call somewhere in it."""
    event = _boulder_event(with_se=True)
    assert T.detect_push_boulder(event) is True


def test_detect_push_boulder_kernel_prefix_variant_matches() -> None:
    event = make_event([[cmd(T.SCRIPT, ["Kernel.pbPushThisBoulder"]), cmd(0)]])
    assert T.detect_push_boulder(event) is True


def test_detect_push_boulder_absent_returns_false() -> None:
    event = make_event([[cmd(T.SHOW_TEXT, ["hi"])]])
    assert T.detect_push_boulder(event) is False


def test_detect_push_boulder_conditional_form_not_matched() -> None:
    """The corpus-wide `if pbPushThisBoulder ... end` conditional-branch
    shape (code 111) is a DIFFERENT idiom this work item deliberately does
    not claim (REDERIVATION_PLAN.md §15.1 item 8 scope: only the 5 bare-call
    rows currently queued). It must fall through undetected here, not be
    guessed at."""
    event = make_event([[
        cmd(T.CONDITIONAL_BRANCH, [12, "pbPushThisBoulder"]),
        cmd(T.CONTROL_SELF_SWITCH, ["A", 0], indent=1),
        cmd(0, indent=1),
        cmd(T.BRANCH_END),
        cmd(0),
    ]])
    assert T.detect_push_boulder(event) is False


def test_detect_push_boulder_near_miss_with_argument_still_false() -> None:
    """`pbPushThisBoulder` takes no arguments in the real Ruby def — a call
    carrying one is not this idiom and must not be guessed at."""
    event = make_event([[cmd(T.SCRIPT, ["pbPushThisBoulder(1)"]), cmd(0)]])
    assert T.detect_push_boulder(event) is False


def test_detect_push_boulder_substring_head_not_matched() -> None:
    """A different head that merely contains the boulder call as a substring
    (e.g. a hypothetical `pbPushThisBoulderTwice`) must not match — the regex
    is anchored end-to-end, same discipline as the item-ball/berry-tree
    detectors."""
    event = make_event([[cmd(T.SCRIPT, ["pbPushThisBoulderTwice"]), cmd(0)]])
    assert T.detect_push_boulder(event) is False


# ----------------------------------------------------------------------------
# T.resolve_native_object_template
# ----------------------------------------------------------------------------


def test_resolve_native_object_template_pushable_boulder_claims_event() -> None:
    ctx = _resolve_ctx()
    event = _boulder_event(id=1, name="Boulder")
    claimed = T.resolve_native_object_template(31, event, ctx)
    assert claimed is True
    assert ctx.template_fields[(31, 1)] == {"kind": "pushable_boulder"}


def test_resolve_native_object_template_pushable_boulder_no_fork_lookup_required() -> None:
    """Unlike item balls/berry trees, no item_id_map/fork_item_constants
    wiring is needed on ctx — the boulder idiom carries no per-event item
    symbol to resolve. A bare, unconfigured ctx must still claim the event
    cleanly (regression: a future change must not silently start requiring
    fork-item plumbing this idiom never needed)."""
    ctx = T.TranspileContext(registry=FlagRegistry())
    event = _boulder_event(id=2, name="Boulder", with_se=True)
    claimed = T.resolve_native_object_template(19, event, ctx)
    assert claimed is True
    assert ctx.template_fields[(19, 2)] == {"kind": "pushable_boulder"}


def test_resolve_native_object_template_five_corpus_events_all_claim() -> None:
    """Reproduces the exact 5 staged corpus rows (Map019 EV1/2/3 with the SE
    row, Map031 EV1/37 without) and asserts every one claims cleanly with no
    queue entry — the real regression this work item is closing."""
    ctx = _resolve_ctx()
    corpus = [
        (19, 1, True), (19, 2, True), (19, 3, True),
        (31, 1, False), (31, 37, False),
    ]
    for map_id, event_id, with_se in corpus:
        event = _boulder_event(id=event_id, name="Boulder", with_se=with_se)
        assert T.resolve_native_object_template(map_id, event, ctx) is True
        assert ctx.template_fields[(map_id, event_id)] == {"kind": "pushable_boulder"}
    assert len(ctx.template_fields) == 5


def test_resolve_native_object_template_unclaimed_by_boulder_returns_false() -> None:
    ctx = _resolve_ctx()
    event = make_event([[cmd(T.SHOW_TEXT, ["hi"])]])
    assert T.resolve_native_object_template(33, event, ctx) is False
    assert ctx.template_fields == {}
