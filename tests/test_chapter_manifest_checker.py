"""Tests for the chapter manifest checker, disposition loader, and renderer.

Builds `ManifestRow`/`Disposition` objects directly rather than going
through the generator — the generator is owned by a different module and
this test only needs the shared contract in `schema.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.chapter_manifest.checker import (
    ApproachModel,
    CapabilityModel,
    RoutePrecedence,
    RULE_APPROACH_MODEL_UNENFORCED,
    RULE_BLOCKED_MISSED_ASSERTION,
    RULE_BLOCKED_NO_GRANTING_CHAPTER,
    RULE_CAPABILITY_MODEL_UNENFORCED,
    RULE_ILLEGAL_COSMETIC,
    RULE_MISSING_CITATION,
    RULE_ORPHAN_DISPOSITION,
    RULE_REACHABILITY_UNENFORCED,
    RULE_ROUTE_MODEL_UNENFORCED,
    RULE_ROUTE_ORDER,
    RULE_STALE_DISPOSITION,
    RULE_UNAFFIRMED_DISPOSITION,
    RULE_UNDISPOSITIONABLE_ROW_DECIDED,
    RULE_UNDISPOSITIONED,
    check_chapter,
    exit_code,
)
from rpg2gba.chapter_manifest.dispositions import (
    disposition_path,
    load_dispositions,
    write_dispositions,
)
from rpg2gba.chapter_manifest.render import render_review
from rpg2gba.chapter_manifest.schema import (
    Disposition,
    ManifestRow,
    PageCondition,
)


def _row(row_id: str = "map001/ev001/p0", **overrides) -> ManifestRow:
    defaults = dict(
        row_id=row_id,
        kind="page",
        map_id=1,
        content_hash="deadbeef00000000",
        effects=(),
        # Most tests here aren't exercising RULE_REACHABILITY_UNENFORCED, so
        # default to "consulted" and let that rule's own tests override this.
        reachability_consulted=True,
    )
    defaults.update(overrides)
    return ManifestRow(**defaults)


def _disp(row_id: str, spec: str, **rest) -> Disposition:
    return Disposition.parse(row_id, spec, **rest)


# --- rule 1: undispositioned row --------------------------------------


def test_undispositioned_row_is_error():
    row = _row()
    findings = check_chapter([row], {})
    # Filter out the unrelated route-model-unenforced warning that every
    # no-`route=` call now carries (rule 10) -- this test is about rule 1.
    relevant = [f for f in findings if f.rule != RULE_ROUTE_MODEL_UNENFORCED]
    assert len(relevant) == 1
    assert relevant[0].rule == RULE_UNDISPOSITIONED
    assert relevant[0].severity == "error"


def test_dispositioned_row_no_undispositioned_finding():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    assert all(f.rule != RULE_UNDISPOSITIONED for f in findings)


# --- rule 2: orphan disposition -----------------------------------------


def test_orphan_disposition_is_error():
    disp = _disp("map999/ev001/p0", "cosmetic", affirmed_hash="h1")
    findings = check_chapter([], {"map999/ev001/p0": disp})
    # Same filter as above -- rule 10's unenforced warning always shows up
    # without a `route=`, and this test is about rule 2.
    relevant = [f for f in findings if f.rule != RULE_ROUTE_MODEL_UNENFORCED]
    assert len(relevant) == 1
    assert relevant[0].rule == RULE_ORPHAN_DISPOSITION
    assert relevant[0].severity == "error"


def test_matching_disposition_not_orphan():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    assert all(f.rule != RULE_ORPHAN_DISPOSITION for f in findings)


# --- rule 3: stale / unaffirmed disposition -----------------------------


def test_stale_disposition_is_error():
    row = _row(effects=("text",), content_hash="new_hash")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="old_hash")
    findings = check_chapter([row], {row.row_id: disp})
    rules = [f.rule for f in findings]
    assert RULE_STALE_DISPOSITION in rules
    stale = next(f for f in findings if f.rule == RULE_STALE_DISPOSITION)
    assert stale.severity == "error"


def test_unaffirmed_disposition_is_distinct_from_stale():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic")  # no affirmed_hash at all
    findings = check_chapter([row], {row.row_id: disp})
    rules = [f.rule for f in findings]
    assert RULE_UNAFFIRMED_DISPOSITION in rules
    assert RULE_STALE_DISPOSITION not in rules


def test_matching_hash_not_stale():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    assert all(f.rule not in (RULE_STALE_DISPOSITION, RULE_UNAFFIRMED_DISPOSITION)
               for f in findings)


# --- rule 4: undispositionable row decided anyway -----------------------


def test_undispositionable_row_decided_is_error():
    row = _row(unrecognized_heads=("pbSomethingNovel",), content_hash="h1")
    disp = _disp(row.row_id, "beat:B1", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    rules = [f.rule for f in findings]
    assert RULE_UNDISPOSITIONABLE_ROW_DECIDED in rules


def test_dispositionable_row_not_flagged():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    assert all(f.rule != RULE_UNDISPOSITIONABLE_ROW_DECIDED for f in findings)


# --- rule 5: illegal cosmetic --------------------------------------------


def test_illegal_cosmetic_state_writing_names_blocking_tags():
    row = _row(effects=("giveitem", "text"), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    illegal = next(f for f in findings if f.rule == RULE_ILLEGAL_COSMETIC)
    assert "giveitem" in illegal.message


def test_illegal_cosmetic_unhandled_calls_out_dead_conversion():
    row = _row(effects=(), unhandled=2, content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    illegal = next(f for f in findings if f.rule == RULE_ILLEGAL_COSMETIC)
    assert "unhandled" in illegal.message.lower()


def test_legal_cosmetic_not_flagged():
    row = _row(effects=("text", "bgm"), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    assert all(f.rule != RULE_ILLEGAL_COSMETIC for f in findings)


# --- rule 6: missing citation --------------------------------------------


def test_missing_citation_when_script_typed_condition_present():
    row = _row(script_typed_conditions=1, effects=("giveitem",), content_hash="h1")
    disp = _disp(row.row_id, "beat:B1", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    rules = [f.rule for f in findings]
    assert RULE_MISSING_CITATION in rules


def test_citation_present_satisfies_rule():
    row = _row(script_typed_conditions=1, effects=("giveitem",), content_hash="h1")
    disp = _disp(row.row_id, "beat:B1", affirmed_hash="h1",
                 source="Data/Scripts.rxdata: pbReceiveItem")
    findings = check_chapter([row], {row.row_id: disp})
    assert all(f.rule != RULE_MISSING_CITATION for f in findings)


def test_no_citation_needed_when_trigger_absent():
    row = _row(effects=("giveitem",), content_hash="h1")
    disp = _disp(row.row_id, "beat:B1", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    assert all(f.rule != RULE_MISSING_CITATION for f in findings)


# --- rule 7: blocked with no granting chapter ---------------------------


class _FakeCapabilities:
    def __init__(self, grants: dict[str, str]) -> None:
        self._grants = grants

    def grants_capability(self, name: str) -> str | None:
        return self._grants.get(name)


class _FakeApproach:
    def __init__(self, walkable: set[str]) -> None:
        self._walkable = walkable

    def has_walkable_approach(self, row: ManifestRow) -> bool:
        return row.row_id in self._walkable


class _FakeApproachTristate:
    """Answers True/False/None per row_id, for testing the "can't tell" arm
    of the three-state Protocol."""

    def __init__(self, answers: dict[str, bool | None]) -> None:
        self._answers = answers

    def has_walkable_approach(self, row: ManifestRow) -> bool | None:
        return self._answers.get(row.row_id)


def test_blocked_without_capability_model_warns_unenforced():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp}, capabilities=None, approach=_FakeApproach(set()))
    rules = [f.rule for f in findings]
    assert RULE_CAPABILITY_MODEL_UNENFORCED in rules
    finding = next(f for f in findings if f.rule == RULE_CAPABILITY_MODEL_UNENFORCED)
    assert finding.severity == "warning"


def test_blocked_with_no_granting_chapter_is_error():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:nonexistent_capability", affirmed_hash="h1")
    caps = _FakeCapabilities({"rock_smash": "CH06"})
    findings = check_chapter([row], {row.row_id: disp}, capabilities=caps, approach=_FakeApproach(set()))
    rules = [f.rule for f in findings]
    assert RULE_BLOCKED_NO_GRANTING_CHAPTER in rules


def test_blocked_with_granting_chapter_ok():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1")
    caps = _FakeCapabilities({"rock_smash": "CH06"})
    findings = check_chapter([row], {row.row_id: disp}, capabilities=caps, approach=_FakeApproach(set()))
    assert all(f.rule not in (RULE_BLOCKED_NO_GRANTING_CHAPTER,
                               RULE_CAPABILITY_MODEL_UNENFORCED) for f in findings)


def test_blocked_multi_capability_set_checked_per_token():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash|strength", affirmed_hash="h1")
    caps = _FakeCapabilities({"rock_smash": "CH06"})  # strength ungranted
    findings = check_chapter([row], {row.row_id: disp}, capabilities=caps, approach=_FakeApproach(set()))
    finding = next(f for f in findings if f.rule == RULE_BLOCKED_NO_GRANTING_CHAPTER)
    assert "strength" in finding.message


def test_blocked_tooling_form_skips_capability_check():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:tooling:emulator_set_flag", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp}, capabilities=None, approach=_FakeApproach(set()))
    assert all(f.rule not in (RULE_CAPABILITY_MODEL_UNENFORCED, RULE_BLOCKED_NO_GRANTING_CHAPTER)
               for f in findings)


# --- rule 8: blocked row with a missed assertion opportunity --------------


def test_blocked_without_approach_model_warns_unenforced():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1")
    caps = _FakeCapabilities({"rock_smash": "CH06"})
    findings = check_chapter([row], {row.row_id: disp}, capabilities=caps, approach=None)
    rules = [f.rule for f in findings]
    assert RULE_APPROACH_MODEL_UNENFORCED in rules
    finding = next(f for f in findings if f.rule == RULE_APPROACH_MODEL_UNENFORCED)
    assert finding.severity == "warning"


def test_blocked_row_walkable_with_no_negative_beat_is_flagged():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1")
    approach = _FakeApproach({row.row_id})
    findings = check_chapter([row], {row.row_id: disp}, approach=approach)
    missed = next(f for f in findings if f.rule == RULE_BLOCKED_MISSED_ASSERTION)
    assert missed.severity == "warning"


def test_blocked_row_walkable_with_negative_beat_not_flagged():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1",
                 assertable=True, negative_beat="B6")
    approach = _FakeApproach({row.row_id})
    findings = check_chapter([row], {row.row_id: disp}, approach=approach)
    assert all(f.rule != RULE_BLOCKED_MISSED_ASSERTION for f in findings)


def test_blocked_row_not_walkable_not_flagged():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1")
    approach = _FakeApproach(set())
    findings = check_chapter([row], {row.row_id: disp}, approach=approach)
    assert all(f.rule != RULE_BLOCKED_MISSED_ASSERTION for f in findings)


# --- exit_code -------------------------------------------------------------


def test_exit_code_zero_when_no_errors():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    assert exit_code(findings) == 0


def test_exit_code_nonzero_on_error():
    findings = check_chapter([_row()], {})
    assert exit_code(findings) == 1


def test_exit_code_zero_when_only_warnings():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp}, capabilities=None, approach=None)
    assert all(f.severity == "warning" for f in findings)
    assert exit_code(findings) == 0


# --- disposition file round-trip -------------------------------------------


def test_disposition_path_convention():
    path = disposition_path("CH04")
    assert path == Path("reference/manifests") / "CH04.dispositions.json"


def test_dispositions_round_trip(tmp_path: Path):
    dispositions = {
        "map001/ev001/p0": Disposition(row_id="map001/ev001/p0", verdict="cosmetic"),
        "map001/ev002/p0": Disposition(
            row_id="map001/ev002/p0", verdict="beat", argument="B1",
            source="wiki: Moki Town", affirmed_hash="abc123", note="checked twice",
        ),
        "map001/ev003/p0": Disposition(
            row_id="map001/ev003/p0", verdict="blocked", argument="rock_smash",
            assertable=True, negative_beat="B6",
        ),
    }
    path = tmp_path / "CH01.dispositions.json"
    write_dispositions(dispositions, path)
    loaded = load_dispositions(path)
    assert loaded == dispositions


def test_dispositions_write_is_deterministic(tmp_path: Path):
    dispositions = {
        "b": Disposition(row_id="b", verdict="cosmetic"),
        "a": Disposition(row_id="a", verdict="unreachable", argument="dev-only flag"),
    }
    path = tmp_path / "out.json"
    write_dispositions(dispositions, path)
    text1 = path.read_text(encoding="utf-8")
    write_dispositions(dispositions, path)
    text2 = path.read_text(encoding="utf-8")
    assert text1 == text2
    assert text1.endswith("\n")
    keys = list(json.loads(text1).keys())
    assert keys == sorted(keys)


def test_dispositions_accepts_bare_string_form(tmp_path: Path):
    path = tmp_path / "CH02.dispositions.json"
    path.write_text(json.dumps({"map001/ev001/p0": "cosmetic"}), encoding="utf-8")
    loaded = load_dispositions(path)
    assert loaded["map001/ev001/p0"].verdict == "cosmetic"


def test_dispositions_accepts_object_form(tmp_path: Path):
    path = tmp_path / "CH02.dispositions.json"
    path.write_text(json.dumps({
        "map001/ev001/p0": {
            "disposition": "beat:B3",
            "source": "Essentials Scripts.rxdata",
            "affirmed_hash": "h1",
        }
    }), encoding="utf-8")
    loaded = load_dispositions(path)
    disp = loaded["map001/ev001/p0"]
    assert disp.verdict == "beat"
    assert disp.argument == "B3"
    assert disp.source == "Essentials Scripts.rxdata"
    assert disp.affirmed_hash == "h1"


def test_dispositions_rejects_malformed_entry(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"row1": 42}), encoding="utf-8")
    with pytest.raises(Exception):
        load_dispositions(path)


def test_dispositions_rejects_bad_verdict(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"row1": "not_a_real_verdict"}), encoding="utf-8")
    with pytest.raises(Exception):
        load_dispositions(path)


# --- render smoke tests ------------------------------------------------


def test_render_collapses_cosmetic_row():
    row = _row(row_id="map001/ev001/p0", effects=("text",), content_hash="h1",
               condition=PageCondition())
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    md = render_review([row], {row.row_id: disp})
    assert "## Cosmetic (1)" in md
    assert f"`{row.row_id}`" in md
    # Cosmetic row gets a one-liner, not an expanded "### `row_id`" section.
    assert f"### `{row.row_id}`" not in md


def test_render_expands_citation_owed_row():
    row = _row(row_id="map002/ev005/p0", script_typed_conditions=1,
               effects=("giveitem",), content_hash="h2", condition=PageCondition())
    disp = _disp(row.row_id, "beat:B7", affirmed_hash="h2",
                 source="Essentials pbReceiveItem")
    md = render_review([row], {row.row_id: disp})
    assert f"### `{row.row_id}`" in md
    assert "## Citation owed (1)" in md
    assert "Essentials pbReceiveItem" in md


def test_render_summary_counts():
    row1 = _row(row_id="map001/ev001/p0", effects=("text",), content_hash="h1",
                condition=PageCondition())
    row2 = _row(row_id="map001/ev002/p0", effects=(), content_hash="h2",
                condition=PageCondition())
    disp1 = _disp(row1.row_id, "cosmetic", affirmed_hash="h1")
    md = render_review([row1, row2], {row1.row_id: disp1})
    assert "total rows: 2" in md
    assert "undispositioned: 1" in md


# --- rule 9: reachability source not consulted for a map ------------------


def test_unconsulted_map_is_flagged_once():
    row1 = _row(row_id="map036/ev001/p0", map_id=36, effects=("text",),
                content_hash="h1", reachability_consulted=False)
    row2 = _row(row_id="map036/ev002/p0", map_id=36, effects=("text",),
                content_hash="h2", reachability_consulted=False)
    disp1 = _disp(row1.row_id, "cosmetic", affirmed_hash="h1")
    disp2 = _disp(row2.row_id, "cosmetic", affirmed_hash="h2")
    findings = check_chapter([row1, row2], {row1.row_id: disp1, row2.row_id: disp2})
    matches = [f for f in findings if f.rule == RULE_REACHABILITY_UNENFORCED]
    assert len(matches) == 1  # one finding per unconsulted MAP, not per row
    assert matches[0].severity == "warning"
    assert matches[0].row_id == "map036"
    assert "surf" in matches[0].message and "waterfall" in matches[0].message


def test_consulted_map_not_flagged():
    row = _row(effects=("text",), content_hash="h1", reachability_consulted=True)
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    assert all(f.rule != RULE_REACHABILITY_UNENFORCED for f in findings)


def test_unconsulted_map_flagged_even_when_no_blocked_rows_present():
    """The whole point: an unconsulted map's rows can look "clean" (no
    requires, no blocked verdicts) while the terrain-gated half of the
    capability model was simply never asked. This must surface regardless of
    verdict."""
    row = _row(effects=("text",), content_hash="h1", reachability_consulted=False)
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    assert any(f.rule == RULE_REACHABILITY_UNENFORCED for f in findings)


def test_unconsulted_map_finding_present_regardless_of_exit_code():
    row = _row(effects=("text",), content_hash="h1", reachability_consulted=False)
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    assert exit_code(findings) == 0  # warning only, never blocks


# --- rule 8 continued: three-state approach answer -------------------------


def test_blocked_row_approach_unanswerable_is_unenforced_not_suppressed():
    """None must never collapse into False -- an unanswerable row gets the
    honest "unenforced" warning, not silent approval (no missed-assertion
    warning, but also no false confidence that the approach is closed)."""
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1")
    approach = _FakeApproachTristate({row.row_id: None})
    findings = check_chapter([row], {row.row_id: disp}, approach=approach)
    rules = [f.rule for f in findings]
    assert RULE_APPROACH_MODEL_UNENFORCED in rules
    assert RULE_BLOCKED_MISSED_ASSERTION not in rules
    unenforced = next(f for f in findings if f.rule == RULE_APPROACH_MODEL_UNENFORCED)
    assert unenforced.severity == "warning"


def test_blocked_row_approach_false_is_silent():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1")
    approach = _FakeApproachTristate({row.row_id: False})
    findings = check_chapter([row], {row.row_id: disp}, approach=approach)
    rules = [f.rule for f in findings]
    assert RULE_APPROACH_MODEL_UNENFORCED not in rules
    assert RULE_BLOCKED_MISSED_ASSERTION not in rules


def test_blocked_row_approach_true_fires_missed_assertion():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1")
    approach = _FakeApproachTristate({row.row_id: True})
    findings = check_chapter([row], {row.row_id: disp}, approach=approach)
    rules = [f.rule for f in findings]
    assert RULE_BLOCKED_MISSED_ASSERTION in rules
    assert RULE_APPROACH_MODEL_UNENFORCED not in rules


# --- rule 10: registered beat-group order must match planned route order ---


class _FakeRoute:
    """A minimal `RouteModel` for tests that don't need a real `RoutePlan` --
    e.g. isolating the reorder-diff logic from the plan's own on-disk shape.
    """

    def __init__(self, planned: tuple[str, ...], registered: tuple[str, ...],
                 precedence: tuple[RoutePrecedence, ...] = ()) -> None:
        self._planned = planned
        self._registered = registered
        self._precedence = precedence

    def planned_group_order(self) -> tuple[str, ...]:
        return self._planned

    def registered_group_order(self) -> tuple[str, ...]:
        return self._registered

    def precedence_edges(self) -> tuple[RoutePrecedence, ...]:
        return self._precedence


def _plan_group_order(plan) -> tuple[str, ...]:
    return tuple(n.group for n in plan.nodes if n.kind == "group")


class _RealPlanRoute:
    """The shape the CLI's real adapter has: planned order and precedence
    come from an actual `RoutePlan`; registered order comes from wherever
    `Chapter.groups()` put it (a plain tuple here, since these tests don't
    need a real chapter module to exercise the diff logic)."""

    def __init__(self, plan, registered: tuple[str, ...]) -> None:
        self._plan = plan
        self._registered = registered

    def planned_group_order(self) -> tuple[str, ...]:
        return _plan_group_order(self._plan)

    def registered_group_order(self) -> tuple[str, ...]:
        return self._registered

    def precedence_edges(self) -> tuple[RoutePrecedence, ...]:
        return tuple(
            RoutePrecedence(before=e.before, after=e.after, reason=e.reason)
            for e in self._plan.precedence
        )


def _build_route_plan(group_order: tuple[str, ...], precedence=()):
    """A real `rpg2gba.routing.plan.RoutePlan` with one group node per name
    in `group_order`, entry/exit bookends, and trivial single-tile segments
    -- just enough to satisfy `RoutePlan.__post_init__`'s invariants."""
    from rpg2gba.routing.plan import (
        PrecedenceEdge,
        RouteLeg,
        RouteNode,
        RoutePlan,
        RouteSegment,
    )

    nodes = [RouteNode(index=0, kind="entry", map_id=1, cell=(0, 0))]
    for i, group_id in enumerate(group_order, start=1):
        nodes.append(RouteNode(index=i, kind="group", map_id=1, cell=(0, 0),
                                group=group_id, beats=(f"{group_id}:b0",)))
    nodes.append(RouteNode(index=len(nodes), kind="exit", map_id=1, cell=(0, 0)))

    segments = tuple(
        RouteSegment(from_index=i, to_index=i + 1,
                     legs=(RouteLeg(map_id=1, tiles=((0, 0),)),), tile_count=1)
        for i in range(len(nodes) - 1)
    )
    edges = tuple(PrecedenceEdge(before=b, after=a, reason=r) for b, a, r in precedence)

    return RoutePlan(chapter_id="CH04", chapter_module="test_chapter",
                      nodes=tuple(nodes), segments=segments, precedence=edges,
                      tile_cost=len(segments), solver_method="test")


def test_route_order_unenforced_without_route_model():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp}, route=None)
    unenforced = [f for f in findings if f.rule == RULE_ROUTE_MODEL_UNENFORCED]
    assert len(unenforced) == 1
    assert unenforced[0].severity == "warning"
    assert unenforced[0].row_id == "chapter"
    assert all(f.rule != RULE_ROUTE_ORDER for f in findings)


def test_route_order_matching_orders_no_finding():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    route = _FakeRoute(planned=("B1", "B2", "B3"), registered=("B1", "B2", "B3"))
    findings = check_chapter([row], {row.row_id: disp}, route=route)
    assert all(f.rule not in (RULE_ROUTE_ORDER, RULE_ROUTE_MODEL_UNENFORCED)
               for f in findings)


def test_route_order_transposed_pair_reports_swap_not_two_findings():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    route = _FakeRoute(planned=("B1", "B2", "B3"), registered=("B1", "B3", "B2"))
    findings = check_chapter([row], {row.row_id: disp}, route=route)
    order_findings = [f for f in findings if f.rule == RULE_ROUTE_ORDER]
    assert len(order_findings) == 1
    assert order_findings[0].severity == "error"
    assert "'B2'" in order_findings[0].message and "'B3'" in order_findings[0].message
    assert "transposed" in order_findings[0].message


def test_route_order_group_in_plan_not_registered_is_error():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    route = _FakeRoute(planned=("B1", "B2"), registered=("B1",))
    findings = check_chapter([row], {row.row_id: disp}, route=route)
    order_findings = [f for f in findings if f.rule == RULE_ROUTE_ORDER]
    assert len(order_findings) == 1
    assert order_findings[0].severity == "error"
    assert "'B2'" in order_findings[0].message
    assert "never registered" in order_findings[0].message


def test_route_order_group_registered_not_in_plan_is_error():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    route = _FakeRoute(planned=("B1",), registered=("B1", "B2"))
    findings = check_chapter([row], {row.row_id: disp}, route=route)
    order_findings = [f for f in findings if f.rule == RULE_ROUTE_ORDER]
    assert len(order_findings) == 1
    assert order_findings[0].severity == "error"
    assert "'B2'" in order_findings[0].message
    assert "does not appear anywhere in the planned route order" in order_findings[0].message


def test_route_order_precedence_violation_names_reason():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    # Orders match exactly -- only the precedence edge is violated, so this
    # isolates the precedence half of the rule from the reorder-diff half.
    edge = RoutePrecedence(before="B3", after="B1",
                            reason="B1 needs the item B3 grants")
    route = _FakeRoute(planned=("B1", "B2", "B3"), registered=("B1", "B2", "B3"),
                        precedence=(edge,))
    findings = check_chapter([row], {row.row_id: disp}, route=route)
    order_findings = [f for f in findings if f.rule == RULE_ROUTE_ORDER]
    assert len(order_findings) == 1
    assert order_findings[0].severity == "error"
    assert "B1 needs the item B3 grants" in order_findings[0].message
    assert "'B3'" in order_findings[0].message and "'B1'" in order_findings[0].message


def test_route_order_precedence_satisfied_no_finding():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    edge = RoutePrecedence(before="B1", after="B3", reason="B3 needs B1's item")
    route = _FakeRoute(planned=("B1", "B2", "B3"), registered=("B1", "B2", "B3"),
                        precedence=(edge,))
    findings = check_chapter([row], {row.row_id: disp}, route=route)
    assert all(f.rule != RULE_ROUTE_ORDER for f in findings)


def test_route_order_against_real_route_plan_transposed():
    """Drives a real `rpg2gba.routing.plan.RoutePlan` through `RouteModel`,
    so the rule is proven against the actual on-disk artifact type -- not
    only the `_FakeRoute` stand-in used above."""
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    plan = _build_route_plan(("B1", "B2", "B3"))
    route = _RealPlanRoute(plan, registered=("B1", "B3", "B2"))
    findings = check_chapter([row], {row.row_id: disp}, route=route)
    order_findings = [f for f in findings if f.rule == RULE_ROUTE_ORDER]
    assert len(order_findings) == 1
    assert "transposed" in order_findings[0].message


def test_route_order_against_real_route_plan_precedence_violation():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    plan = _build_route_plan(
        ("B1", "B2", "B3"),
        precedence=[("B3", "B1", "B1 needs the item B3 grants")],
    )
    route = _RealPlanRoute(plan, registered=("B1", "B2", "B3"))
    findings = check_chapter([row], {row.row_id: disp}, route=route)
    order_findings = [f for f in findings if f.rule == RULE_ROUTE_ORDER]
    assert len(order_findings) == 1
    assert order_findings[0].severity == "error"
    assert "B1 needs the item B3 grants" in order_findings[0].message
