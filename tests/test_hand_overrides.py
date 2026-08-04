"""Tests for the hand-override layer (BUILD_PLAN §3 hand-conversion tail) —
``hand_overrides.py`` (loading/validation) and its wiring into
``transpile_driver.transpile_map``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.conversion_agent import (
    hand_overrides,
    queue_evidence,
    transpile_driver,
    transpiler,
)
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

# ----------------------------------------------------------------------------
# builders
# ----------------------------------------------------------------------------


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def make_event(
    pages_cmds_and_triggers: list[tuple[int, list[dict]]], *, id: int, name: str
) -> dict:
    pages = [{"trigger": trigger, "list": cmds} for trigger, cmds in pages_cmds_and_triggers]
    return {"id": id, "name": name, "x": 0, "y": 0, "pages": pages}


_PROVENANCE = "# hand conversion (2026-07-05): test fixture\n"


def valid_override_text(map_id: int, event_id: int, *, body: str = 'msgbox("hi")\n    end') -> str:
    label = f"Map{map_id:03d}_EV{event_id:03d}_Page1"
    return f"{_PROVENANCE}script {label} {{\n    {body}\n}}"


@pytest.fixture()
def ctx() -> transpiler.TranspileContext:
    return transpiler.TranspileContext(registry=FlagRegistry())


def write_ledger(path: Path, pairs: list[tuple[int, int]]) -> Path:
    """A triage ledger bucketing each `(map_id, event_id)` `hand` with a
    complete evidence record — what the ROM_TEST_DEV §E1 gate demands before
    an override file is allowed to exist."""
    entries = [
        queue_evidence.QueueEntry(
            raw={"map_id": m, "event_id": e, "page": 1, "command_code": 111},
            bucket="hand",
            evidence=queue_evidence.SearchEvidence(
                greps=(queue_evidence.GrepRecord(
                    command=f'grep -rn "thing" engine/  # for Map{m:03d}/EV{e:03d}',
                    result_summary="no matches"),),
                decomposition_attempted="split into native primitives",
                decomposition_failed_because="no native host for the composite",
            ),
        )
        for m, e in pairs
    ]
    queue_evidence.save_queue_jsonl(path, entries)
    return path


@pytest.fixture()
def overrides_dir(tmp_path: Path) -> Path:
    """The hand_conversions/ stand-in. A subdir of tmp_path, not tmp_path
    itself, so the test ledger can sit next to it without looking like a
    stray file inside the override directory."""
    d = tmp_path / "hand_conversions"
    d.mkdir()
    return d


@pytest.fixture()
def ledger(tmp_path: Path) -> Path:
    """Default ledger for these tests: justifies Map007/EV004."""
    return write_ledger(tmp_path / "ledger" / "hand_bucket_queue.jsonl", [(7, 4)])


# ----------------------------------------------------------------------------
# hand_overrides.load_hand_overrides
# ----------------------------------------------------------------------------


def test_load_valid_override_round_trips(overrides_dir: Path, ledger: Path) -> None:
    text = valid_override_text(7, 4)
    path = overrides_dir / "Map007_EV004.pory"
    path.write_text(text, encoding="utf-8")

    overrides = hand_overrides.load_hand_overrides(overrides_dir, ledger_path=ledger)

    assert set(overrides) == {(7, 4)}
    ov = overrides[(7, 4)]
    assert ov.map_id == 7
    assert ov.event_id == 4
    assert ov.path == path
    assert ov.text == text


def test_malformed_filename_raises(overrides_dir: Path, ledger: Path) -> None:
    (overrides_dir / "Map7_EV004.pory").write_text(valid_override_text(7, 4), encoding="utf-8")

    with pytest.raises(ValueError, match="malformed"):
        hand_overrides.load_hand_overrides(overrides_dir, ledger_path=ledger)


# -- the ROM_TEST_DEV §E1 evidence gate ---------------------------------------


def test_override_without_a_hand_bucketed_ledger_entry_raises(
        tmp_path: Path, overrides_dir: Path) -> None:
    """The load-bearing case: writing a file into hand_conversions/ IS the act
    of bucketing an event `hand`, so it must be justified like one."""
    ledger = write_ledger(tmp_path / "ledger" / "hand_bucket_queue.jsonl", [(99, 1)])
    (overrides_dir / "Map007_EV004.pory").write_text(
        valid_override_text(7, 4), encoding="utf-8")

    with pytest.raises(queue_evidence.QueueSchemaViolation,
                        match="no 'hand'-bucketed triage entry"):
        hand_overrides.load_hand_overrides(overrides_dir, ledger_path=ledger)


def test_override_whose_ledger_entry_has_a_blank_evidence_box_raises(
        tmp_path: Path, overrides_dir: Path) -> None:
    """A `hand` entry with an empty evidence box is a schema violation, not a
    judgment call — the box is visibly blank when nobody looked."""
    ledger_path = tmp_path / "ledger" / "hand_bucket_queue.jsonl"
    ledger_path.parent.mkdir()
    ledger_path.write_text(json.dumps({
        "raw": {"map_id": 7, "event_id": 4, "page": 1, "command_code": 111},
        "bucket": "hand",
        "evidence": {"greps": [], "decomposition_attempted": "",
                      "decomposition_failed_because": "", "legacy_unaudited": False},
    }) + "\n", encoding="utf-8")
    (overrides_dir / "Map007_EV004.pory").write_text(
        valid_override_text(7, 4), encoding="utf-8")

    with pytest.raises(queue_evidence.QueueSchemaViolation,
                        match="missing required evidence"):
        hand_overrides.load_hand_overrides(overrides_dir, ledger_path=ledger_path)


def test_legacy_unaudited_ledger_entry_warns_but_admits_the_override(
        tmp_path: Path, overrides_dir: Path,
        caplog: pytest.LogCaptureFixture) -> None:
    """The one escape hatch: a pre-schema entry that couldn't be honestly
    backfilled stays visible as a warning rather than blocking a build."""
    ledger_path = tmp_path / "ledger" / "hand_bucket_queue.jsonl"
    ledger_path.parent.mkdir()
    ledger_path.write_text(json.dumps({
        "raw": {"map_id": 7, "event_id": 4, "page": 1, "command_code": 111},
        "bucket": "hand",
        "evidence": {"greps": [], "decomposition_attempted": "",
                      "decomposition_failed_because": "", "legacy_unaudited": True},
    }) + "\n", encoding="utf-8")
    (overrides_dir / "Map007_EV004.pory").write_text(
        valid_override_text(7, 4), encoding="utf-8")

    with caplog.at_level("WARNING"):
        overrides = hand_overrides.load_hand_overrides(
            overrides_dir, ledger_path=ledger_path)

    assert set(overrides) == {(7, 4)}
    assert "legacy_unaudited" in caplog.text


def test_missing_ledger_raises(tmp_path: Path, overrides_dir: Path) -> None:
    (overrides_dir / "Map007_EV004.pory").write_text(
        valid_override_text(7, 4), encoding="utf-8")

    with pytest.raises(queue_evidence.QueueSchemaViolation, match="is missing"):
        hand_overrides.load_hand_overrides(
            tmp_path, ledger_path=tmp_path / "ledger" / "nope.jsonl")


def test_real_hand_conversions_are_all_justified_by_the_real_ledger() -> None:
    """Guards the committed state, not a fixture: every file actually in
    `hand_conversions/` must have its entry in the real ledger."""
    overrides = hand_overrides.load_hand_overrides()
    assert overrides, "expected committed hand conversions"


def test_foreign_label_definition_raises(overrides_dir: Path, ledger: Path) -> None:
    text = (
        _PROVENANCE
        + "script Map007_EV004_Page1 {\n    end\n}\n\n"
        + "script Map007_EV005_Page1 {\n    end\n}\n"
    )
    (overrides_dir / "Map007_EV004.pory").write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="Map007_EV005"):
        hand_overrides.load_hand_overrides(overrides_dir, ledger_path=ledger)


def test_empty_file_raises(overrides_dir: Path, ledger: Path) -> None:
    (overrides_dir / "Map007_EV004.pory").write_text("   \n", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        hand_overrides.load_hand_overrides(overrides_dir, ledger_path=ledger)


def test_readme_skipped(overrides_dir: Path, ledger: Path) -> None:
    (overrides_dir / "README.md").write_text("convention notes\n", encoding="utf-8")
    (overrides_dir / "Map007_EV004.pory").write_text(valid_override_text(7, 4), encoding="utf-8")

    overrides = hand_overrides.load_hand_overrides(overrides_dir, ledger_path=ledger)

    assert set(overrides) == {(7, 4)}


def test_stray_non_pory_file_raises(overrides_dir: Path, ledger: Path) -> None:
    (overrides_dir / "notes.txt").write_text("oops\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected file"):
        hand_overrides.load_hand_overrides(overrides_dir, ledger_path=ledger)


def test_missing_own_entry_script_raises(overrides_dir: Path, ledger: Path) -> None:
    # Only a `mart` block, no `script Map007_EV004_...` entry point.
    text = _PROVENANCE + "mart Map007_EV004_Mart {\n    ITEM_POTION\n}\n"
    (overrides_dir / "Map007_EV004.pory").write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="no 'script Map007_EV004_"):
        hand_overrides.load_hand_overrides(overrides_dir, ledger_path=ledger)


def test_non_namespaced_definition_raises(overrides_dir: Path, ledger: Path) -> None:
    text = (
        _PROVENANCE
        + "script Map007_EV004_Page1 {\n    end\n}\n\n"
        + "script HelperRoutine {\n    end\n}\n"
    )
    (overrides_dir / "Map007_EV004.pory").write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="not MapNNN_EVNNN-shaped"):
        hand_overrides.load_hand_overrides(overrides_dir, ledger_path=ledger)


def test_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert hand_overrides.load_hand_overrides(tmp_path / "does_not_exist") == {}


# ----------------------------------------------------------------------------
# transpile_driver.transpile_map wiring
# ----------------------------------------------------------------------------


def test_transpile_map_splices_override_verbatim_and_skips_transpiler(
    ctx: transpiler.TranspileContext,
) -> None:
    map_id = 12
    # Plain event: trigger 1 + empty body so no classifier claims it (all of
    # them require action-button trigger or specific command shapes) — it's
    # guaranteed to fall through to the general transpiler, so its output is
    # fully predictable.
    event1 = make_event([(1, [])], id=1, name="PlainNPC")
    # "Hard" event: if this were actually transpiled/classified instead of
    # overridden, it would (a) render differently from the override text and
    # (b) queue an unhandled entry (script call: 'pbItemBall(:POTION)') — so
    # this test also catches a regression that lets the override leak through
    # to the classifier/transpiler instead of short-circuiting it.
    event2 = make_event(
        [(1, [cmd(transpiler.SCRIPT, ["pbItemBall(:POTION)"])])], id=2, name="HardNPC"
    )
    map_json = {"map_id": map_id, "events": [event1, event2]}

    override_text = valid_override_text(map_id, 2, body='msgbox("Hand authored")\n    end')
    override = hand_overrides.HandOverride(
        map_id=map_id, event_id=2, path=Path("Map012_EV002.pory"), text=override_text
    )

    pory_text, queue_entries = transpile_driver.transpile_map(
        map_id, map_json, ctx, None, {(map_id, 2): override}
    )

    expected_event1 = "# PlainNPC\nscript Map012_EV001_Page1 {\n    end\n}"
    assert pory_text == "\n\n".join([expected_event1, override_text])
    assert queue_entries == []


def test_transpile_map_without_override_still_transpiles_and_queues(
    ctx: transpiler.TranspileContext,
) -> None:
    """Control case: the same "hard" event, with no override supplied, does
    fall through to the general transpiler and does queue — confirms the
    override in the test above is actually doing something, not just
    happening to match by coincidence."""
    map_id = 12
    event2 = make_event(
        [(1, [cmd(transpiler.SCRIPT, ["pbItemBall(:POTION)"])])], id=2, name="HardNPC"
    )
    map_json = {"map_id": map_id, "events": [event2]}

    pory_text, queue_entries = transpile_driver.transpile_map(map_id, map_json, ctx, None, {})

    assert len(queue_entries) == 1
    assert "pbItemBall" in queue_entries[0]["description"]
    assert 'msgbox("Hand authored")' not in pory_text


def test_transpile_map_other_events_still_transpile_alongside_override(
    ctx: transpiler.TranspileContext,
) -> None:
    map_id = 12
    event1 = make_event([(1, [])], id=1, name="PlainNPC")
    event2 = make_event([(1, [])], id=2, name="OverriddenNPC")
    override = hand_overrides.HandOverride(
        map_id=map_id,
        event_id=2,
        path=Path("Map012_EV002.pory"),
        text=valid_override_text(map_id, 2),
    )
    map_json = {"map_id": map_id, "events": [event1, event2]}

    pory_text, _queue = transpile_driver.transpile_map(
        map_id, map_json, ctx, None, {(map_id, 2): override}
    )

    assert "Map012_EV001_Page1" in pory_text


def test_transpile_map_stale_override_raises(ctx: transpiler.TranspileContext) -> None:
    map_id = 12
    event1 = make_event([(1, [])], id=1, name="PlainNPC")
    map_json = {"map_id": map_id, "events": [event1]}
    stale_override = hand_overrides.HandOverride(
        map_id=map_id,
        event_id=999,
        path=Path("Map012_EV999.pory"),
        text=valid_override_text(map_id, 999),
    )

    with pytest.raises(ValueError, match="stale"):
        transpile_driver.transpile_map(
            map_id, map_json, ctx, None, {(map_id, 999): stale_override}
        )


def test_transpile_map_overrides_default_to_none_unaffected(
    ctx: transpiler.TranspileContext,
) -> None:
    """Positional 4-arg call (no overrides) — the existing calling convention
    (e.g. scripts/oracle_harvest.py) must keep working unchanged."""
    map_id = 12
    event1 = make_event([(1, [])], id=1, name="PlainNPC")
    map_json = {"map_id": map_id, "events": [event1]}

    pory_text, queue_entries = transpile_driver.transpile_map(map_id, map_json, ctx, None)

    assert queue_entries == []
    assert "Map012_EV001_Page1" in pory_text


# ----------------------------------------------------------------------------
# transpile_driver.transpile_corpus — trait sidecar (rock-smash upstream
# signal; fixed-schema contract with the downstream FLAG_TEMP_* respawn-flag
# fix in metadata_wiring.py / stage_slice_scripts.py, owned by a different
# agent — do not change the schema here without updating that consumer too)
# ----------------------------------------------------------------------------


def _rock_smash_commands() -> list[dict]:
    return [
        cmd(transpiler.CONDITIONAL_BRANCH, [12, "Kernel.pbRockSmash"]),
        cmd(transpiler.CONTROL_SELF_SWITCH, ["A", 0], indent=1),
        cmd(transpiler.BRANCH_END),
    ]


def _run_corpus(tmp_path: Path, map_id: int, events: list[dict]) -> Path:
    """Run transpile_corpus over one synthetic map, isolated from the real
    committed hand-override set (an empty overrides_dir — the real
    hand_conversions/ tree references real corpus event ids that don't exist
    on a synthetic map and would otherwise raise a stale-override error)."""
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir(exist_ok=True)
    out_dir = tmp_path / "out"
    overrides_dir = tmp_path / "empty_overrides"
    overrides_dir.mkdir(exist_ok=True)
    (maps_dir / f"Map{map_id:03d}.json").write_text(
        json.dumps({"map_id": map_id, "events": events}), encoding="utf-8"
    )
    transpile_driver.transpile_corpus(
        [map_id],
        maps_dir=maps_dir,
        out_dir=out_dir,
        flag_state_path=out_dir / "flag_state.json",
        map_constants_path=out_dir / "porymap" / "map_constants.json",
        common_events=False,
        overrides_dir=overrides_dir,
    )
    return out_dir


def test_transpile_corpus_writes_traits_sidecar_for_rock_smash_event(tmp_path: Path) -> None:
    event = make_event([(0, _rock_smash_commands())], id=14, name="Rock")
    out_dir = _run_corpus(tmp_path, 32, [event])

    sidecar_path = out_dir / "scripts" / "Map032.traits.json"
    raw = sidecar_path.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert json.loads(raw) == {"events": {"14": ["smashable_rock"]}}


def test_transpile_corpus_writes_empty_traits_sidecar_when_no_traits(tmp_path: Path) -> None:
    event = make_event([(0, [])], id=1, name="PlainNPC")
    out_dir = _run_corpus(tmp_path, 33, [event])

    sidecar_path = out_dir / "scripts" / "Map033.traits.json"
    assert json.loads(sidecar_path.read_text(encoding="utf-8")) == {"events": {}}


def test_transpile_corpus_traits_sidecar_idempotent(tmp_path: Path) -> None:
    event = make_event([(0, _rock_smash_commands())], id=14, name="Rock")
    out_dir = _run_corpus(tmp_path, 32, [event])
    sidecar_path = out_dir / "scripts" / "Map032.traits.json"
    first = sidecar_path.read_bytes()

    _run_corpus(tmp_path, 32, [event])
    assert sidecar_path.read_bytes() == first


def test_transpile_corpus_resolves_switch_names_from_scratch(tmp_path: Path) -> None:
    """Regression: transpile_corpus must resolve a named Uranium switch to its
    deterministic FLAG_* on a completely FRESH run (no pre-existing
    flag_state.json) — it must not depend on some OTHER script (e.g.
    stage_slice_scripts.py's dispatcher pass) having already seeded labels
    and minted the name into a persisted state file first.

    Caught by a real incident: a from-scratch flag_state.json (after a
    legitimate wipe/reseed) sent a switch this test also exercises — real
    switch id 2, "Got Pokemon" in reference/uranium_switches.json — through
    the queue as "unnamed", even though its name is fully deterministic from
    that same static reference file. The fix is `transpile_corpus` calling
    `registry.seed_labels(...)` itself, mirroring what
    `stage_slice_scripts.py` already does — CLAUDE.md §4.2: a from-scratch
    run must reproduce identical results, not depend on accumulated state a
    different script happened to build up first."""
    branch = [
        cmd(transpiler.CONDITIONAL_BRANCH, [0, 2, 0]),
        cmd(transpiler.SHOW_TEXT, ["Nice!"], indent=1),
        cmd(transpiler.BRANCH_END),
    ]
    event = make_event([(0, branch)], id=1, name="SwitchCheck")
    out_dir = _run_corpus(tmp_path, 34, [event])

    pory_text = (out_dir / "scripts" / "Map034.pory").read_text(encoding="utf-8")
    assert "flag(FLAG_GOT_POKEMON)" in pory_text

    state = json.loads((out_dir / "flag_state.json").read_text(encoding="utf-8"))
    assert state["switches"]["2"] == "FLAG_GOT_POKEMON"
