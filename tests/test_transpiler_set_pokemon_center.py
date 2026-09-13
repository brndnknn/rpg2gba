"""Unit tests for `Kernel.pbSetPokemonCenter` (P8b item 3,
REDERIVATION_PLAN.md §15.2 item 3 / §15.6): the white-out respawn anchor.

Previously silently swallowed via `deterministic._DIALOGUE_STRIP_RE`
(reference/recon/uranium_script_calls.md:71 corrected the STRIP ruling
TWICE). Now a resolved call site (looked up in
`ctx.heal_locations[(map_id, event_id, page_index)]`, straight from
`rpg2gba.pbs_converter.heal_locations.call_site_heal_locations()`) emits the
fork-native `setrespawn(HEAL_LOCATION_*)`; an unresolved one queues instead of
being dropped (CLAUDE.md §4.5 fail loud).

Covers:
(a) Map068 EV001 page 0 shape resolves and the following message survives.
(b) An empty `ctx.heal_locations` table queues rather than silently dropping.
(c) `page_index` is 0-based: an entry keyed to page 0 does not leak into
    page 1 of the same event.
(d) The chapter-manifest generator tags a page carrying the call
    `respawn_write`, and `may_be_cosmetic` is False for it.

Builders mirror `tests/test_transpiler_native.py` (local per file-ownership
convention: an event is `{id, name, x, y, pages:[...]}`, each page
`{trigger, list, ...}` with `list` a sequence of `{code, indent, parameters}`
commands). Part (d) reuses the chapter_manifest generator fixtures from
`tests/test_chapter_manifest_generator.py` rather than duplicating them.
"""
from __future__ import annotations

from pathlib import Path

from rpg2gba.chapter_manifest.generator import generate_chapter_manifest
from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

# Reuse, don't duplicate (tests/test_observed_beats.py precedent for
# cross-test-module imports).
from tests.test_chapter_manifest_generator import _cmd as _mcmd
from tests.test_chapter_manifest_generator import _page, _setup_chapter

# ----------------------------------------------------------------------------
# builders (mirrors tests/test_transpiler_native.py)
# ----------------------------------------------------------------------------


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def make_event(
    pages_cmds: list[list[dict]], trigger: int = 0, id: int = 1, name: str = "npc",
) -> dict:
    pages = [{"trigger": trigger, "list": cmds} for cmds in pages_cmds]
    return {"id": id, "name": name, "x": 0, "y": 0, "pages": pages}


def run_event(
    ctx: T.TranspileContext,
    pages_cmds: list[list[dict]],
    trigger: int = 0,
    map_id: int = 68,
    event_id: int = 1,
    name: str = "npc",
) -> T.TranspiledEvent:
    ev = make_event(pages_cmds, trigger=trigger, id=event_id, name=name)
    return T.transpile_event(map_id, ev, ctx)


_KEVLAR_HEAL_LOCATION = "HEAL_LOCATION_KEVLAR_TOWN_POKEMON_CENTER"


def _ctx_with_heal_locations(table: dict[tuple[int, int, int], str]) -> T.TranspileContext:
    ctx = T.TranspileContext(registry=FlagRegistry())
    ctx.heal_locations = table
    return ctx


# ----------------------------------------------------------------------------
# (a) Map068 EV001 page 0 -- resolves, following message survives
# ----------------------------------------------------------------------------


def test_resolved_call_site_emits_setrespawn_and_keeps_following_message() -> None:
    ctx = _ctx_with_heal_locations({(68, 1, 0): _KEVLAR_HEAL_LOCATION})
    res = run_event(
        ctx,
        [[
            cmd(T.SCRIPT, ["Kernel.pbSetPokemonCenter"]),
            cmd(T.SHOW_TEXT, ["Welcome to the Pokemon Center!"]),
        ]],
        map_id=68, event_id=1,
    )
    assert res.unhandled == []
    assert f"setrespawn({_KEVLAR_HEAL_LOCATION})" in res.text
    assert "Welcome to the Pokemon Center!" in res.text


# ----------------------------------------------------------------------------
# (b) empty table -- queues, never silently drops
# ----------------------------------------------------------------------------


def test_unresolved_call_site_queues_not_drops() -> None:
    ctx = _ctx_with_heal_locations({})
    res = run_event(
        ctx, [[cmd(T.SCRIPT, ["Kernel.pbSetPokemonCenter"])]], map_id=68, event_id=1,
    )
    assert len(res.unhandled) == 1
    assert res.unhandled[0].command_code == T.SCRIPT
    assert "setrespawn(" not in res.text


# ----------------------------------------------------------------------------
# (c) page_index is 0-based -- page 1's call does not pick up page 0's entry
# ----------------------------------------------------------------------------


def test_page_index_is_0_based_page1_does_not_reuse_page0_entry() -> None:
    ctx = _ctx_with_heal_locations({(68, 1, 0): _KEVLAR_HEAL_LOCATION})
    res = run_event(
        ctx,
        [
            [cmd(T.SHOW_TEXT, ["page 0, no call"])],
            [cmd(T.SCRIPT, ["Kernel.pbSetPokemonCenter"])],
        ],
        map_id=68, event_id=1,
    )
    assert f"setrespawn({_KEVLAR_HEAL_LOCATION})" not in res.text
    assert len(res.unhandled) == 1
    assert res.unhandled[0].page == 1
    assert res.unhandled[0].command_code == T.SCRIPT


def test_bare_and_kernel_prefixed_forms_both_resolve() -> None:
    """`_SET_POKEMON_CENTER_RE` (imported from heal_locations._CALL_RE)
    accepts both the bare and `Kernel.`-prefixed call spellings."""
    ctx = _ctx_with_heal_locations({(68, 1, 0): _KEVLAR_HEAL_LOCATION})
    res = run_event(ctx, [[cmd(T.SCRIPT, ["pbSetPokemonCenter"])]], map_id=68, event_id=1)
    assert res.unhandled == []
    assert f"setrespawn({_KEVLAR_HEAL_LOCATION})" in res.text


def test_common_event_call_site_always_queues() -> None:
    """A common event has no single owning map/event to resolve a respawn
    tile against, so it queues even when the lookup table is non-empty."""
    ctx = _ctx_with_heal_locations({(68, 1, 0): _KEVLAR_HEAL_LOCATION})
    ce = {"id": 3, "name": "CE", "list": [cmd(T.SCRIPT, ["Kernel.pbSetPokemonCenter"])]}
    res = T.transpile_common_event(ce, ctx)
    assert len(res.unhandled) == 1
    assert "setrespawn(" not in res.text


# ----------------------------------------------------------------------------
# (d) manifest generator tags the page respawn_write / not cosmetic
# ----------------------------------------------------------------------------


def test_manifest_tags_respawn_write_and_blocks_cosmetic(tmp_path: Path) -> None:
    events = [{
        "id": 1, "name": "Nurse", "x": 0, "y": 0,
        "pages": [_page([_mcmd(T.SCRIPT, ["Kernel.pbSetPokemonCenter"])])],
    }]
    build_dir, chapters_path = _setup_chapter(tmp_path, 68, events)

    rows = generate_chapter_manifest("CHX", build_dir=build_dir, chapters_path=chapters_path)

    assert len(rows) == 1
    row = rows[0]
    assert row.script_heads == ("pbSetPokemonCenter",)
    assert row.unrecognized_heads == ()
    assert "respawn_write" in row.effects
    assert row.may_be_cosmetic is False
