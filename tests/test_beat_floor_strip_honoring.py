"""Tests for assignments/C8/02_strip_honoring.md: `beat_floor` honouring
strip-listed common events on code-117 the same way `story_state` already
does (`story_state/extract.py:extract_map`'s `stripped_ce_ids` parameter,
C8 stage 4, commit `bd80c080`).

Requirement tags used in the docstrings/comments below match the task file:
R1 -- thread `stripped_ce_ids` through the call chain, defaulting via
`stripped_ce_ids_for` exactly like `extract_map` does.
R2 -- in `_walk_common_event_call`, a stripped `ce_id` produces `((), ())`
and does not recurse, and the check happens BEFORE the missing-CE lookup.
R3 -- `beat_floor/lookup.py`'s cached entry point (`floor_for_map_cached`/
`floor_for_row`) gets the same behaviour.

This file was checked against a throwaway reference implementation kept
outside the repo (per the task file's instructions) before being added
here; a failure against the real (not-yet-implemented) `beat_floor` code
means the feature is not landed yet, not that the test is wrong.

The real-data test deliberately re-runs each staged call site's own `117`
command through the walker in isolation, rather than building the whole
`Map068` floor: the full map's result depends on the bodies of CEs 4/5/6
and on unrelated refusals elsewhere on that map, none of which this task
owns.

STATUS: implemented, skipped. DELETE the `pytestmark` line when you start
Task 2.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.beat_floor import lookup, walk

MAP_ID = 1
EVENT_ID = 1
PAGE_IDX = 0
ROW_ID = "map001/ev001/p0"

# A common event body that, if inlined, produces a visible, easy-to-spot
# assertion (`erase_event`, from code 116) -- the same shape
# `test_beat_floor_walk.py`'s own 117-inlining tests use, so a regression
# in either direction (over- or under-stripping) is obvious.
_CE_BODY = [{"code": 116, "parameters": []}]


def _map_data(commands: list[dict], *, trigger: int = 0) -> dict:
    return {
        "events": [
            {
                "id": EVENT_ID,
                "pages": [
                    {
                        "trigger": trigger,
                        "condition": {},
                        "list": commands,
                    }
                ],
            }
        ]
    }


def _floor(
    commands: list[dict], *, common_events: list[dict] | None = None,
    stripped_ce_ids: frozenset[int] | None = None,
):
    map_data = _map_data(commands)
    return walk.floor_for_map(
        MAP_ID, map_data, common_events=common_events or [], switch_labels={},
        door_cells={}, stripped_ce_ids=stripped_ce_ids,
    )


def _row(commands: list[dict], **kwargs):
    rows = _floor(commands, **kwargs)
    return rows[ROW_ID]


def _kinds(row) -> set[str]:
    return {a.kind for a in row.assertions}


# --- R2: the no-op, and its ordering vs. the missing-CE check --------------


def test_stripped_common_event_call_emits_nothing():
    """R2: a 117 call to an EXPLICITLY stripped CE produces no assertions
    and no refusals -- the CE body (which would assert `erase_event` if
    inlined) never runs."""
    ce = {"id": 6, "list": _CE_BODY}
    commands = [{"code": 117, "parameters": [6]}]
    row = _row(commands, common_events=[ce], stripped_ce_ids=frozenset({6}))
    assert not row.refused
    assert _kinds(row) == {"trigger", "completes"}
    assert "erase_event" not in _kinds(row)


def test_stripped_common_event_call_does_not_recurse():
    """R2: stripping a CE means its body is never walked at all -- not even
    to find further refusals. A stripped CE whose body contains an unknown
    command code (which would normally refuse `no_extractor`) produces no
    refusal, proving the body was never entered."""
    ce = {"id": 6, "list": [{"code": 9999, "parameters": []}]}
    commands = [{"code": 117, "parameters": [6]}]
    row = _row(commands, common_events=[ce], stripped_ce_ids=frozenset({6}))
    assert not row.refused


def test_non_stripped_common_event_call_still_inlines():
    """Regression guard: a 117 call to a CE that is NOT in the (explicit,
    non-empty) stripped set still inlines normally -- existing behaviour
    from `test_beat_floor_walk.py` must not change."""
    ce = {"id": 9, "list": _CE_BODY}
    commands = [{"code": 117, "parameters": [9]}]
    row = _row(commands, common_events=[ce], stripped_ce_ids=frozenset({6}))
    assert not row.refused
    erase = next(a for a in row.assertions if a.kind == "erase_event")
    assert erase.list_index == 0  # attributed to the call site, R11 C4 shape


def test_default_none_uses_real_strip_list_for_known_stripped_id():
    """R1: with `stripped_ce_ids` left at its default (`None`), a call to a
    real strip-listed id (6 -- LOBBY, `reference/strip_list.json`) is a
    no-op, exactly like `story_state.extract_map`'s own default. This is
    the "a caller who has not been updated still gets strip-honouring for
    free" half of the defaulting contract."""
    ce = {"id": 6, "list": _CE_BODY}
    commands = [{"code": 117, "parameters": [6]}]
    row = _row(commands, common_events=[ce])  # stripped_ce_ids omitted -> None
    assert not row.refused
    assert "erase_event" not in _kinds(row)


def test_explicit_empty_frozenset_disables_stripping():
    """R1 / the hinted "single most likely bug": an explicit
    `stripped_ce_ids=frozenset()` must NOT be treated the same as `None`.
    CE 6 is stripped by default (previous test), but passing an empty set
    here must force it to inline anyway."""
    ce = {"id": 6, "list": _CE_BODY}
    commands = [{"code": 117, "parameters": [6]}]
    row = _row(commands, common_events=[ce], stripped_ce_ids=frozenset())
    assert not row.refused
    assert "erase_event" in _kinds(row)


def test_stripped_and_missing_common_event_produces_no_refusal():
    """R2 ordering: a `ce_id` that is BOTH stripped AND absent from
    `common_events` must produce no `missing_common_event` refusal -- the
    stripped check runs before the missing-CE lookup, per the task file's
    "malformed -> cycle -> stripped -> missing -> inline" order."""
    commands = [{"code": 117, "parameters": [6]}]
    row = _row(commands, common_events=[], stripped_ce_ids=frozenset({6}))
    assert not row.refused
    assert not any(r.reason == "missing_common_event" for r in row.refusals)
    assert _kinds(row) == {"trigger", "completes"}


def test_missing_non_stripped_common_event_still_refuses():
    """Regression guard for the ordering fix: a `ce_id` that is missing but
    NOT stripped must still refuse `missing_common_event` -- R2's ordering
    change must not swallow this refusal for the general case."""
    commands = [{"code": 117, "parameters": [404]}]
    row = _row(commands, common_events=[], stripped_ce_ids=frozenset({6}))
    assert row.refused
    assert any(r.reason == "missing_common_event" for r in row.refusals)


# --- R3: the cached entry point (`lookup.py`) -------------------------------


def _write_cached_build_dir(tmp_path: Path, commands: list[dict], common_events: list[dict]) -> Path:
    build_dir = tmp_path / "build"
    (build_dir / "maps").mkdir(parents=True)
    (build_dir / "maps" / f"Map{MAP_ID:03d}.json").write_text(
        json.dumps(_map_data(commands)), encoding="utf-8")
    (build_dir / "common_events.json").write_text(
        json.dumps(common_events), encoding="utf-8")
    # `_door_cells` fails loud (CLAUDE.md §4.5) if this is absent.
    (build_dir / "warp_overrides.gen.json").write_text(
        json.dumps({"cells": {}}), encoding="utf-8")
    return build_dir


def test_floor_for_map_cached_honours_stripped_ce_ids(tmp_path: Path):
    """R3: `lookup.floor_for_map_cached` must accept and honour
    `stripped_ce_ids` too -- the second, cached entry point that bypasses
    `floor_for_chapter` entirely (the task file's "trap")."""
    ce = {"id": 6, "list": _CE_BODY}
    commands = [{"code": 117, "parameters": [6]}]
    build_dir = _write_cached_build_dir(tmp_path, commands, [ce])

    stripped_rows = lookup.floor_for_map_cached(
        str(build_dir), MAP_ID, stripped_ce_ids=frozenset({6}))
    assert "erase_event" not in _kinds(stripped_rows[ROW_ID])

    unstripped_rows = lookup.floor_for_map_cached(
        str(build_dir), MAP_ID, stripped_ce_ids=frozenset())
    assert "erase_event" in _kinds(unstripped_rows[ROW_ID])


def test_floor_for_row_honours_stripped_ce_ids(tmp_path: Path):
    """R3: `lookup.floor_for_row`, the row-id-keyed public entry point most
    external consumers actually call, must thread the same parameter down
    to `floor_for_map_cached`."""
    ce = {"id": 6, "list": _CE_BODY}
    commands = [{"code": 117, "parameters": [6]}]
    build_dir = _write_cached_build_dir(tmp_path, commands, [ce])

    stripped = lookup.floor_for_row(
        ROW_ID, build_dir=build_dir, stripped_ce_ids=frozenset({6}))
    assert "erase_event" not in _kinds(stripped)

    unstripped = lookup.floor_for_row(
        ROW_ID, build_dir=build_dir, stripped_ce_ids=frozenset())
    assert "erase_event" in _kinds(unstripped)


# --- real corpus: the three staged CH03 sites (skipped if absent) ----------

_BUILD_DIR = Path("output/uranium-build")


@pytest.mark.skipif(
    not (_BUILD_DIR / "maps" / "Map068.json").exists(),
    reason="no converted map corpus at output/uranium-build/maps/Map068.json",
)
@pytest.mark.parametrize(
    "event_id,ce_id",
    [(9, 4), (11, 5), (13, 6)],
    ids=["ev009-ce4-gts", "ev011-ce5-vt", "ev013-ce6-lobby"],
)
def test_real_map068_staged_sites_are_stripped(event_id: int, ce_id: int):
    """Pins the three measured staged code-117-to-stripped-CE sites (task
    file "Measured acceptance"): `Map068` (CH03) events 9, 11, 13, each at
    page 0 `list[0]`, calling common events 4, 5, 6 respectively.

    Confirms the real corpus command shape (code 117, that exact ce_id at
    list index 0) first, then re-runs that exact command through the floor
    walker with a synthetic CE body to confirm it is honoured as a no-op --
    deterministic, without depending on what CE 4/5/6's real bodies happen
    to contain today."""
    map_data = json.loads(
        (_BUILD_DIR / "maps" / "Map068.json").read_text(encoding="utf-8"))
    event = next(e for e in map_data["events"] if e["id"] == event_id)
    cmd = event["pages"][0]["list"][0]
    assert cmd["code"] == 117
    assert cmd["parameters"][0] == ce_id

    ce = {"id": ce_id, "list": _CE_BODY}
    row = _row([cmd], common_events=[ce], stripped_ce_ids=frozenset({4, 5, 6}))
    assert not row.refused
    assert "erase_event" not in _kinds(row)
