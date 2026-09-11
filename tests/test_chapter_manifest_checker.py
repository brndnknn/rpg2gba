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
    CapabilityGrant,
    CapabilityModel,
    PlannedApproach,
    RoutePrecedence,
    RULE_APPROACH_MODEL_UNENFORCED,
    RULE_ARCHETYPE_CONFORMANCE,
    RULE_ARCHETYPE_MODEL_UNENFORCED,
    RULE_BEAT_MODEL_UNENFORCED,
    RULE_BLOCKED_ALREADY_GRANTED,
    RULE_BLOCKED_MISSED_ASSERTION,
    RULE_BLOCKED_NO_GRANT_SITE,
    RULE_BOUNDARY_MODEL_UNENFORCED,
    RULE_BOUNDARY_NOT_CROSSING,
    RULE_BOUNDARY_UNCLAIMED,
    RULE_CAPABILITY_MODEL_UNENFORCED,
    RULE_ILLEGAL_COSMETIC,
    RULE_MISSING_CITATION,
    RULE_ORPHAN_DISPOSITION,
    RULE_REACHABILITY_UNENFORCED,
    RULE_ROUTE_APPROACH,
    RULE_ROUTE_MODEL_UNENFORCED,
    RULE_ROUTE_ORDER,
    RULE_STALE_DISPOSITION,
    RULE_TRIGGER_OVERLAY_MODEL_UNENFORCED,
    RULE_TRIGGER_OVERLAY_VACUOUS,
    RULE_UNAFFIRMED_DISPOSITION,
    RULE_UNDISPOSITIONABLE_ROW_DECIDED,
    RULE_UNDISPOSITIONED,
    RULE_UNREGISTERED_BEAT,
    check_chapter,
    check_trigger_overlay,
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
    # `unhandled=0`: this test isolates the state-writing-tags message from
    # the never-staged (`unhandled is None`) arm, which is checked first and
    # would otherwise produce a different message for the same row.
    row = _row(effects=("giveitem", "text"), content_hash="h1", unhandled=0)
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    illegal = next(f for f in findings if f.rule == RULE_ILLEGAL_COSMETIC)
    assert "giveitem" in illegal.message


def test_illegal_cosmetic_never_staged_reports_distinct_message():
    """`unhandled is None` -- the map was never transpiled at all -- takes
    priority over any other explanation, even when the row's effects would
    also independently block cosmetic."""
    row = _row(effects=(), content_hash="h1", unhandled=None)
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    illegal = next(f for f in findings if f.rule == RULE_ILLEGAL_COSMETIC)
    assert "never" in illegal.message.lower() and "transpiled" in illegal.message.lower()
    assert illegal.severity == "error"


def test_illegal_cosmetic_unhandled_calls_out_dead_conversion():
    row = _row(effects=(), unhandled=2, content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp})
    illegal = next(f for f in findings if f.rule == RULE_ILLEGAL_COSMETIC)
    assert "unhandled" in illegal.message.lower()


def test_legal_cosmetic_not_flagged():
    # `unhandled=0`: a staged, clean row -- otherwise the default `None`
    # ("never staged") would itself trip RULE_ILLEGAL_COSMETIC.
    row = _row(effects=("text", "bgm"), content_hash="h1", unhandled=0)
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


# --- rule 7: blocked with no grant site / already granted ----------------


class _FakeCapabilities:
    """`checker.CapabilityModel` test double.

    `grants` maps a capability token straight to its `grant_sites()` answer
    (`None` for undetermined, `()` for confidently-nothing-grants-it, a
    nonempty tuple for real sites); a token absent from `grants` defaults to
    `()` -- "this fake was never told anything about it," the same
    ungranted default the tests exercised before `grants_capability` was
    replaced by the three-state, site-keyed Protocol.

    `within` maps a token to its `granted_within()` answer, defaulting to
    `()` (not already granted in this chapter or a predecessor).
    """

    def __init__(
        self,
        grants: dict[str, tuple[CapabilityGrant, ...] | None] | None = None,
        within: dict[str, tuple[CapabilityGrant, ...]] | None = None,
    ) -> None:
        self._grants = grants or {}
        self._within = within or {}

    def grant_sites(self, name: str) -> tuple[CapabilityGrant, ...] | None:
        return self._grants.get(name, ())

    def granted_within(self, name: str) -> tuple[CapabilityGrant, ...]:
        return self._within.get(name, ())


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


def test_blocked_with_no_grant_site_is_error():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:nonexistent_capability", affirmed_hash="h1")
    grant = CapabilityGrant(row_id="map042/ev003/p0", map_id=42, chapter_id="CH06")
    caps = _FakeCapabilities({"rock_smash": (grant,)})
    findings = check_chapter([row], {row.row_id: disp}, capabilities=caps, approach=_FakeApproach(set()))
    rules = [f.rule for f in findings]
    assert RULE_BLOCKED_NO_GRANT_SITE in rules


def test_blocked_with_grant_site_ok():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1")
    grant = CapabilityGrant(row_id="map042/ev003/p0", map_id=42, chapter_id="CH06")
    caps = _FakeCapabilities({"rock_smash": (grant,)})
    findings = check_chapter([row], {row.row_id: disp}, capabilities=caps, approach=_FakeApproach(set()))
    assert all(f.rule not in (RULE_BLOCKED_NO_GRANT_SITE, RULE_CAPABILITY_MODEL_UNENFORCED,
                               RULE_BLOCKED_ALREADY_GRANTED) for f in findings)


def test_blocked_and_set_no_grant_site_for_one_member_is_error():
    # Re-pinned for the "+"-is-AND / "|"-is-OR grammar (2026-09-10): this is
    # ONE minimal set requiring both capabilities, spelled with "+". Since
    # it's the only alternative, a missing grant site for either member
    # makes the whole (only) alternative impossible.
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash+strength", affirmed_hash="h1")
    grant = CapabilityGrant(row_id="map042/ev003/p0", map_id=42, chapter_id="CH06")
    caps = _FakeCapabilities({"rock_smash": (grant,)})  # strength ungranted
    findings = check_chapter([row], {row.row_id: disp}, capabilities=caps, approach=_FakeApproach(set()))
    finding = next(f for f in findings if f.rule == RULE_BLOCKED_NO_GRANT_SITE)
    assert "strength" in finding.message


def test_blocked_tooling_form_skips_capability_check():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:tooling:emulator_set_flag", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp}, capabilities=None, approach=_FakeApproach(set()))
    assert all(f.rule not in (RULE_CAPABILITY_MODEL_UNENFORCED, RULE_BLOCKED_NO_GRANT_SITE)
               for f in findings)


def test_blocked_and_set_capability_undetermined_warns_unenforced():
    """`grant_sites` returning `None` for one member of a `blocked:a+b` AND
    set warns unenforced for the whole (only) alternative, even though the
    other member resolves fine -- re-pinned from the old `|`-is-AND spelling
    (2026-09-10)."""
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash+strength", affirmed_hash="h1")
    grant = CapabilityGrant(row_id="map042/ev003/p0", map_id=42, chapter_id="CH06")
    caps = _FakeCapabilities({"rock_smash": (grant,), "strength": None})
    findings = check_chapter([row], {row.row_id: disp}, capabilities=caps, approach=_FakeApproach(set()))
    finding = next(f for f in findings if f.rule == RULE_CAPABILITY_MODEL_UNENFORCED)
    assert finding.severity == "warning"
    assert "strength" in finding.message
    assert all(f.rule != RULE_BLOCKED_NO_GRANT_SITE for f in findings)


# --- OR semantics: alternative capability sets (2026-09-10 grammar) --------


def test_blocked_or_one_of_two_alternatives_satisfied_fires_already_granted():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash|surf", affirmed_hash="h1")
    rock_grant = CapabilityGrant(row_id="map042/ev003/p0", map_id=42, chapter_id="CH06")
    surf_grant = CapabilityGrant(row_id="map050/ev001/p0", map_id=50, chapter_id="CH07")
    caps = _FakeCapabilities(
        {"rock_smash": (rock_grant,), "surf": (surf_grant,)},
        within={"rock_smash": (rock_grant,)},  # only rock_smash already held
    )
    findings = check_chapter([row], {row.row_id: disp}, capabilities=caps, approach=_FakeApproach(set()))
    finding = next(f for f in findings if f.rule == RULE_BLOCKED_ALREADY_GRANTED)
    assert "rock_smash" in finding.message
    assert "map042/ev003/p0" in finding.message
    assert all(f.rule != RULE_BLOCKED_NO_GRANT_SITE for f in findings)


def test_blocked_or_one_impossible_one_viable_does_not_fire_no_grant_site():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash|surf", affirmed_hash="h1")
    surf_grant = CapabilityGrant(row_id="map050/ev001/p0", map_id=50, chapter_id="CH07")
    # rock_smash ungranted anywhere (impossible); surf has a real site but
    # isn't held yet within this chapter/predecessor (still viable-blocked).
    caps = _FakeCapabilities({"surf": (surf_grant,)})
    findings = check_chapter([row], {row.row_id: disp}, capabilities=caps, approach=_FakeApproach(set()))
    rules = [f.rule for f in findings]
    assert RULE_BLOCKED_NO_GRANT_SITE not in rules
    assert RULE_BLOCKED_ALREADY_GRANTED not in rules
    assert RULE_CAPABILITY_MODEL_UNENFORCED not in rules


def test_blocked_or_all_alternatives_impossible_fires_no_grant_site():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash|surf", affirmed_hash="h1")
    caps = _FakeCapabilities({})  # neither capability is granted anywhere
    findings = check_chapter([row], {row.row_id: disp}, capabilities=caps, approach=_FakeApproach(set()))
    finding = next(f for f in findings if f.rule == RULE_BLOCKED_NO_GRANT_SITE)
    assert "rock_smash" in finding.message
    assert "surf" in finding.message


def test_blocked_already_granted_in_this_chapter_or_predecessor_is_error():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1")
    grant = CapabilityGrant(row_id="map042/ev003/p0", map_id=42, chapter_id="CH06")
    caps = _FakeCapabilities({"rock_smash": (grant,)}, within={"rock_smash": (grant,)})
    findings = check_chapter([row], {row.row_id: disp}, capabilities=caps, approach=_FakeApproach(set()))
    finding = next(f for f in findings if f.rule == RULE_BLOCKED_ALREADY_GRANTED)
    assert finding.severity == "error"
    assert "map042/ev003/p0" in finding.message


def test_blocked_not_already_granted_when_granted_within_is_empty():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1")
    grant = CapabilityGrant(row_id="map042/ev003/p0", map_id=42, chapter_id="CH06")
    caps = _FakeCapabilities({"rock_smash": (grant,)})  # within defaults to ()
    findings = check_chapter([row], {row.row_id: disp}, capabilities=caps, approach=_FakeApproach(set()))
    assert all(f.rule != RULE_BLOCKED_ALREADY_GRANTED for f in findings)


# --- rule 8: blocked row with a missed assertion opportunity --------------


def test_blocked_without_approach_model_warns_unenforced():
    row = _row(effects=(), content_hash="h1")
    disp = _disp(row.row_id, "blocked:rock_smash", affirmed_hash="h1")
    grant = CapabilityGrant(row_id="map042/ev003/p0", map_id=42, chapter_id="CH06")
    caps = _FakeCapabilities({"rock_smash": (grant,)})
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
    # `unhandled=0`: a staged, clean cosmetic row -- see
    # test_legal_cosmetic_not_flagged's comment.
    row = _row(effects=("text",), content_hash="h1", unhandled=0)
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
    # `unhandled=0`: a staged, clean row -- this test isolates
    # RULE_REACHABILITY_UNENFORCED (a warning) from RULE_ILLEGAL_COSMETIC
    # (an error), which the default `unhandled=None` would also trip.
    row = _row(effects=("text",), content_hash="h1", reachability_consulted=False,
               unhandled=0)
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
                 precedence: tuple[RoutePrecedence, ...] = (),
                 approaches: tuple[PlannedApproach, ...] = (),
                 beat_cells: dict[str, tuple[int, int]] | None = None) -> None:
        self._planned = planned
        self._registered = registered
        self._precedence = precedence
        self._approaches = approaches
        self._beat_cells = beat_cells or {}

    def planned_group_order(self) -> tuple[str, ...]:
        return self._planned

    def registered_group_order(self) -> tuple[str, ...]:
        return self._registered

    def precedence_edges(self) -> tuple[RoutePrecedence, ...]:
        return self._precedence

    def planned_approaches(self) -> tuple[PlannedApproach, ...]:
        return self._approaches

    def declared_beat_cell(self, beat_id: str) -> tuple[int, int] | None:
        return self._beat_cells.get(beat_id)


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

    def planned_approaches(self) -> tuple[PlannedApproach, ...]:
        return ()

    def declared_beat_cell(self, beat_id: str) -> tuple[int, int] | None:
        return None


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


# --- rule: planned approach side must match the beat's declared cell ------


def _approach(group: str = "B1", cell: tuple[int, int] = (8, 6),
              beats: tuple[str, ...] = ("B1",), side: str = "east",
              resolver: str = "approach_to(MAP_PASSAGE_CAVE_2F, ev5, "
                               "prefer=\"east\")",
              map_id: int = 37) -> PlannedApproach:
    return PlannedApproach(group=group, map_id=map_id, cell=cell,
                            beats=beats, side=side, resolver=resolver)


def test_route_approach_matching_cell_no_finding():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    route = _FakeRoute(
        planned=("B1",), registered=("B1",),
        approaches=(_approach(cell=(8, 6)),),
        beat_cells={"B1": (8, 6)},
    )
    findings = check_chapter([row], {row.row_id: disp}, route=route)
    assert all(f.rule != RULE_ROUTE_APPROACH for f in findings)


def test_route_approach_mismatched_cell_is_error_naming_beat_side_and_resolver():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    route = _FakeRoute(
        planned=("B1",), registered=("B1",),
        approaches=(_approach(cell=(8, 6), side="east"),),
        beat_cells={"B1": (9, 6)},
    )
    findings = check_chapter([row], {row.row_id: disp}, route=route)
    approach_findings = [f for f in findings if f.rule == RULE_ROUTE_APPROACH]
    assert len(approach_findings) == 1
    finding = approach_findings[0]
    assert finding.severity == "error"
    assert "'B1'" in finding.message
    assert "(8, 6)" in finding.message
    assert "(9, 6)" in finding.message
    assert "'east'" in finding.message
    assert 'approach_to(MAP_PASSAGE_CAVE_2F, ev5, prefer="east")' in finding.message


def test_route_approach_absent_chosen_approach_no_finding():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    route = _FakeRoute(
        planned=("B1",), registered=("B1",),
        approaches=(),  # no chosen_approach anywhere in the plan
        beat_cells={"B1": (9, 6)},
    )
    findings = check_chapter([row], {row.row_id: disp}, route=route)
    assert all(f.rule not in (RULE_ROUTE_APPROACH, RULE_ROUTE_MODEL_UNENFORCED)
               for f in findings)


def test_route_approach_no_route_model_is_unenforced_warning_not_silence():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp}, route=None)
    unenforced = [f for f in findings if f.rule == RULE_ROUTE_MODEL_UNENFORCED]
    assert len(unenforced) == 1
    assert unenforced[0].severity == "warning"
    assert all(f.rule != RULE_ROUTE_APPROACH for f in findings)


def test_route_approach_no_registered_beat_available_is_unenforced_warning():
    """The plan committed to a side for group B1, but B1's beat is never
    registered with a declared location -- the mismatch cannot be checked,
    so it must degrade to the warning, not read as a silent pass."""
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    route = _FakeRoute(
        planned=("B1",), registered=("B1",),
        approaches=(_approach(beats=("B1",)),),
        beat_cells={},  # B1 registered (per registered_group_order) but no location
    )
    findings = check_chapter([row], {row.row_id: disp}, route=route)
    assert all(f.rule != RULE_ROUTE_APPROACH for f in findings)
    unenforced = [f for f in findings if f.rule == RULE_ROUTE_MODEL_UNENFORCED]
    assert len(unenforced) == 1
    assert unenforced[0].severity == "warning"
    assert "'B1'" in unenforced[0].message


def test_route_approach_only_the_mismatching_node_is_reported():
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    route = _FakeRoute(
        planned=("B1", "B2", "B3"), registered=("B1", "B2", "B3"),
        approaches=(
            _approach(group="B1", beats=("B1",), cell=(1, 1)),
            _approach(group="B2", beats=("B2",), cell=(2, 2)),
            _approach(group="B3", beats=("B3",), cell=(3, 3)),
        ),
        beat_cells={"B1": (1, 1), "B2": (9, 9), "B3": (3, 3)},
    )
    findings = check_chapter([row], {row.row_id: disp}, route=route)
    approach_findings = [f for f in findings if f.rule == RULE_ROUTE_APPROACH]
    assert len(approach_findings) == 1
    assert "'B2'" in approach_findings[0].message


# --- rule 11/12: archetype conformance -------------------------------------


def _trainer_row(row_id: str = "map010/ev001/p0", **overrides) -> ManifestRow:
    defaults = dict(
        row_id=row_id, kind="page", map_id=10, content_hash="th0",
        event_id=1, page_idx=0, script_heads=("pbTrainerBattle",),
        effects=(), trigger="action button", reachability_consulted=True,
    )
    defaults.update(overrides)
    return ManifestRow(**defaults)


def _item_ball_rows(
    map_id: int = 20, event_id: int = 2,
) -> tuple[ManifestRow, ManifestRow]:
    grant = ManifestRow(
        row_id=f"map{map_id:03d}/ev{event_id:03d}/p0", kind="page", map_id=map_id,
        content_hash="ih0", event_id=event_id, page_idx=0,
        script_heads=("pbItemBall",), effects=("giveitem",),
        trigger="action button", reachability_consulted=True,
    )
    spent = ManifestRow(
        row_id=f"map{map_id:03d}/ev{event_id:03d}/p1", kind="page", map_id=map_id,
        content_hash="ih1", event_id=event_id, page_idx=1,
        script_heads=(), effects=("text",),
        condition=PageCondition(self_switch_ch="A"),
        trigger="action button", reachability_consulted=True,
    )
    return grant, spent


class _FakeArchetypeModel:
    def __init__(self, claims: dict[str, str]) -> None:
        self._claims = claims

    def claimed_archetype(self, row_id: str) -> str | None:
        return self._claims.get(row_id)


def test_archetype_conformance_pass_no_finding():
    row = _trainer_row()
    disp = _disp(row.row_id, "beat:B1", affirmed_hash="th0")
    model = _FakeArchetypeModel({row.row_id: "trainer"})
    findings = check_chapter([row], {row.row_id: disp}, archetype_model=model)
    assert all(f.rule != RULE_ARCHETYPE_CONFORMANCE for f in findings)
    assert all(f.rule != RULE_ARCHETYPE_MODEL_UNENFORCED for f in findings)


def test_archetype_conformance_trainer_mismatch_dispositioned_cosmetic():
    row = _trainer_row()
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="th0")
    findings = check_chapter([row], {row.row_id: disp})
    finding = next(f for f in findings if f.rule == RULE_ARCHETYPE_CONFORMANCE)
    assert "trainer" in finding.message
    assert "'beat'" in finding.message
    assert "'cosmetic'" in finding.message


def test_archetype_conformance_item_ball_spent_page_may_be_a_negative_beat():
    """A prescription is a floor, not an equality: `beat` on a page
    prescribed `cosmetic` is the item-ball template's `negative_beat` arm --
    a real "re-touch grants nothing" assertion, strictly stronger than
    waving the spent page through as decoration. CH04's `map035/ev009/p1`
    is exactly this and was hand-reasoned into it on 2026-08-25.
    """
    grant, spent = _item_ball_rows()
    disp_grant = _disp(grant.row_id, "beat:B9", affirmed_hash="ih0")
    disp_spent = _disp(spent.row_id, "beat:N1", affirmed_hash="ih1")
    model = _FakeArchetypeModel({
        grant.row_id: "item_ball", spent.row_id: "item_ball",
    })
    findings = check_chapter(
        [grant, spent], {grant.row_id: disp_grant, spent.row_id: disp_spent},
        archetype_model=model,
    )
    assert all(f.rule != RULE_ARCHETYPE_CONFORMANCE for f in findings)


def test_archetype_conformance_negative_beat_still_needs_a_claiming_beat():
    """Promoting the spent page to a beat does not exempt it from the
    beat-claim half -- if it is a beat, a registered beat must own it.
    """
    grant, spent = _item_ball_rows()
    disp_grant = _disp(grant.row_id, "beat:B9", affirmed_hash="ih0")
    disp_spent = _disp(spent.row_id, "beat:N1", affirmed_hash="ih1")
    model = _FakeArchetypeModel({grant.row_id: "item_ball"})
    findings = check_chapter(
        [grant, spent], {grant.row_id: disp_grant, spent.row_id: disp_spent},
        archetype_model=model,
    )
    finding = next(
        f for f in findings
        if f.rule == RULE_ARCHETYPE_CONFORMANCE and f.row_id == spent.row_id
    )
    assert "no registered beat claims it" in finding.message


@pytest.mark.parametrize("spec", ["blocked:rock_smash", "unreachable:sealed room"])
def test_archetype_conformance_reachability_supersedes_the_prescription(spec):
    """An archetype says what kind of event a row is; it cannot demand a
    beat for a row no player can walk to. Eight CH04 rows north of Route
    2's rockslide gate are genuine trainers and item balls AND genuinely
    `blocked:rock_smash` until CH07 grants it.
    """
    row = _trainer_row()
    findings = check_chapter([row], {row.row_id: _disp(row.row_id, spec,
                                                       affirmed_hash="th0")})
    assert all(f.rule != RULE_ARCHETYPE_CONFORMANCE for f in findings)


def test_archetype_conformance_missing_disposition_is_flagged():
    row = _trainer_row()
    findings = check_chapter([row], {})
    finding = next(
        f for f in findings
        if f.rule == RULE_ARCHETYPE_CONFORMANCE and f.row_id == row.row_id
    )
    assert "no disposition at all" in finding.message


def test_archetype_exempt_row_skips_check_and_is_counted():
    row = _trainer_row()
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="th0",
                 archetype_exempt="genuinely not a standard trainer battle")
    findings = check_chapter([row], {row.row_id: disp})
    assert all(f.rule != RULE_ARCHETYPE_CONFORMANCE
               for f in findings if f.row_id == row.row_id)
    tally = next(f for f in findings
                 if f.rule == RULE_ARCHETYPE_CONFORMANCE and f.row_id == "chapter")
    assert "1 row" in tally.message
    assert tally.severity == "warning"


def test_archetype_conformance_severity_live_chapter_is_error():
    row = _trainer_row()
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="th0")
    findings = check_chapter([row], {row.row_id: disp}, live_chapter=True)
    finding = next(f for f in findings if f.rule == RULE_ARCHETYPE_CONFORMANCE)
    assert finding.severity == "error"


def test_archetype_conformance_severity_gated_chapter_is_warning():
    row = _trainer_row()
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="th0")
    findings = check_chapter([row], {row.row_id: disp}, live_chapter=False)
    finding = next(f for f in findings if f.rule == RULE_ARCHETYPE_CONFORMANCE)
    assert finding.severity == "warning"


def test_archetype_model_unenforced_without_model():
    row = _trainer_row()
    disp = _disp(row.row_id, "beat:B1", affirmed_hash="th0")
    findings = check_chapter([row], {row.row_id: disp}, archetype_model=None)
    finding = next(f for f in findings if f.rule == RULE_ARCHETYPE_MODEL_UNENFORCED)
    assert finding.severity == "warning"
    assert all(f.rule != RULE_ARCHETYPE_CONFORMANCE for f in findings)


def test_archetype_model_wrong_claim_is_flagged():
    row = _trainer_row()
    disp = _disp(row.row_id, "beat:B1", affirmed_hash="th0")
    model = _FakeArchetypeModel({row.row_id: "item_ball"})
    findings = check_chapter([row], {row.row_id: disp}, archetype_model=model)
    finding = next(f for f in findings if f.rule == RULE_ARCHETYPE_CONFORMANCE)
    assert "item_ball" in finding.message and "trainer" in finding.message


def test_archetype_model_missing_claim_is_flagged():
    row = _trainer_row()
    disp = _disp(row.row_id, "beat:B1", affirmed_hash="th0")
    model = _FakeArchetypeModel({})
    findings = check_chapter([row], {row.row_id: disp}, archetype_model=model)
    finding = next(f for f in findings if f.rule == RULE_ARCHETYPE_CONFORMANCE)
    assert "no registered beat claims it" in finding.message


# --- rule D2: beat: disposition must name a registered beat ---------------


class _FakeBeatModel:
    """A dict-backed `BeatModel` stand-in -- no import of the real
    `beat_model` module (owned by a different agent, may not exist yet)."""

    def __init__(self, registered: set[str], deferred: dict[str, str]) -> None:
        self._registered = registered
        self._deferred = deferred

    def is_registered(self, beat_id: str) -> bool:
        return beat_id in self._registered

    def deferral_reason(self, beat_id: str) -> str | None:
        return self._deferred.get(beat_id)


def test_beat_disposition_registered_no_finding():
    row = _row()
    disp = _disp(row.row_id, "beat:B8", affirmed_hash="deadbeef00000000")
    model = _FakeBeatModel(registered={"B8"}, deferred={})
    findings = check_chapter([row], {row.row_id: disp}, beat_model=model)
    assert all(f.rule not in (RULE_UNREGISTERED_BEAT, RULE_BEAT_MODEL_UNENFORCED)
               for f in findings)


def test_beat_disposition_deferred_reports_reason():
    row = _row()
    disp = _disp(row.row_id, "beat:B8", affirmed_hash="deadbeef00000000")
    model = _FakeBeatModel(
        registered=set(), deferred={"B8": "unreachable without harness primitive X"}
    )
    findings = check_chapter([row], {row.row_id: disp}, beat_model=model)
    finding = next(f for f in findings if f.rule == RULE_UNREGISTERED_BEAT)
    assert "unreachable without harness primitive X" in finding.message


def test_beat_disposition_unknown_reports_distinct_message():
    row = _row()
    disp = _disp(row.row_id, "beat:B99", affirmed_hash="deadbeef00000000")
    model = _FakeBeatModel(registered=set(), deferred={})
    findings = check_chapter([row], {row.row_id: disp}, beat_model=model)
    finding = next(f for f in findings if f.rule == RULE_UNREGISTERED_BEAT)
    assert "no playtest module registers" in finding.message
    assert "rename or a typo" in finding.message


def test_beat_model_unenforced_without_model():
    row = _row()
    disp = _disp(row.row_id, "beat:B8", affirmed_hash="deadbeef00000000")
    findings = check_chapter([row], {row.row_id: disp}, beat_model=None)
    finding = next(f for f in findings if f.rule == RULE_BEAT_MODEL_UNENFORCED)
    assert finding.severity == "warning"
    assert all(f.rule != RULE_UNREGISTERED_BEAT for f in findings)


@pytest.mark.parametrize("spec", ["cosmetic", "blocked:rock_smash", "unreachable:cut content"])
def test_non_beat_verdicts_untouched_by_beat_rules(spec):
    row = _row()
    disp = _disp(row.row_id, spec, affirmed_hash="deadbeef00000000")
    model = _FakeBeatModel(registered=set(), deferred={})
    findings = check_chapter([row], {row.row_id: disp}, beat_model=model)
    assert all(f.rule not in (RULE_UNREGISTERED_BEAT, RULE_BEAT_MODEL_UNENFORCED)
               for f in findings)


@pytest.mark.parametrize("live_chapter,expected", [(True, "error"), (False, "warning")])
def test_unregistered_beat_severity_follows_live_chapter(live_chapter, expected):
    row = _row()
    disp = _disp(row.row_id, "beat:B8", affirmed_hash="deadbeef00000000")
    model = _FakeBeatModel(registered=set(), deferred={"B8": "deferred for now"})
    findings = check_chapter([row], {row.row_id: disp}, beat_model=model,
                              live_chapter=live_chapter)
    finding = next(f for f in findings if f.rule == RULE_UNREGISTERED_BEAT)
    assert finding.severity == expected


def test_ch04_dispositions_round_trip_is_byte_identical(tmp_path: Path):
    """`archetype_exempt` must round-trip through `load_dispositions`/
    `write_dispositions` without disturbing a real, committed, all-bare-
    string disposition file -- no row in CH04 carries the field yet, so a
    correct round trip must reproduce the file byte for byte."""
    path = Path("reference/manifests/CH04.dispositions.json")
    original = path.read_text(encoding="utf-8")
    dispositions = load_dispositions(path)
    out_path = tmp_path / "CH04.dispositions.roundtrip.json"
    write_dispositions(dispositions, out_path)
    assert out_path.read_text(encoding="utf-8") == original


# --- rule 12 (PROJECT_TODO #72/#73): `boundary` disposition truthfulness --


class _FakeBoundaryModel:
    """A stand-in `BoundaryModel` -- no import of the real `boundary_model`
    module (built alongside this rule, not before it)."""

    def __init__(
        self,
        crossing: set[str],
        successor_id: str | None,
        successor_has_module: bool = True,
        claimed: set[str] | None = None,
    ) -> None:
        self._crossing = crossing
        self._successor_id = successor_id
        self._successor_has_module = successor_has_module
        self._claimed = claimed or set()

    def is_forward_crossing(self, row_id: str) -> bool:
        return row_id in self._crossing

    def successor_chapter_id(self) -> str | None:
        return self._successor_id

    def successor_has_module(self) -> bool:
        return self._successor_has_module

    def successor_claims(self, row_id: str) -> bool:
        return row_id in self._claimed


def test_boundary_model_unenforced_without_model():
    row = _row()
    disp = _disp(row.row_id, "boundary", affirmed_hash="deadbeef00000000")
    findings = check_chapter([row], {row.row_id: disp}, boundary_model=None)
    finding = next(f for f in findings if f.rule == RULE_BOUNDARY_MODEL_UNENFORCED)
    assert finding.severity == "warning"
    assert all(f.rule not in (RULE_BOUNDARY_NOT_CROSSING, RULE_BOUNDARY_UNCLAIMED)
               for f in findings)


def test_boundary_not_a_real_crossing_is_flagged():
    row = _row()
    disp = _disp(row.row_id, "boundary", affirmed_hash="deadbeef00000000")
    model = _FakeBoundaryModel(crossing=set(), successor_id="CH05")
    findings = check_chapter([row], {row.row_id: disp}, boundary_model=model)
    finding = next(f for f in findings if f.rule == RULE_BOUNDARY_NOT_CROSSING)
    assert "does not lead anywhere outside the chapter" in finding.message
    assert all(f.rule != RULE_BOUNDARY_UNCLAIMED for f in findings)


def test_boundary_terminal_chapter_is_unclaimed():
    row = _row()
    disp = _disp(row.row_id, "boundary", affirmed_hash="deadbeef00000000")
    model = _FakeBoundaryModel(crossing={row.row_id}, successor_id=None)
    findings = check_chapter([row], {row.row_id: disp}, boundary_model=model)
    finding = next(f for f in findings if f.rule == RULE_BOUNDARY_UNCLAIMED)
    assert "terminal" in finding.message
    assert "can never become true" in finding.message


def test_boundary_successor_with_no_module_is_unenforced():
    row = _row()
    disp = _disp(row.row_id, "boundary", affirmed_hash="deadbeef00000000")
    model = _FakeBoundaryModel(
        crossing={row.row_id}, successor_id="CH05", successor_has_module=False,
    )
    findings = check_chapter([row], {row.row_id: disp}, boundary_model=model)
    finding = next(f for f in findings if f.rule == RULE_BOUNDARY_MODEL_UNENFORCED)
    assert finding.severity == "warning"
    assert "CH05" in finding.message
    assert all(f.rule != RULE_BOUNDARY_UNCLAIMED for f in findings)


def test_boundary_unclaimed_by_successor_is_flagged():
    row = _row()
    disp = _disp(row.row_id, "boundary", affirmed_hash="deadbeef00000000")
    model = _FakeBoundaryModel(
        crossing={row.row_id}, successor_id="CH05",
        successor_has_module=True, claimed=set(),
    )
    findings = check_chapter([row], {row.row_id: disp}, boundary_model=model)
    finding = next(f for f in findings if f.rule == RULE_BOUNDARY_UNCLAIMED)
    assert "CH05" in finding.message
    assert "no beat" in finding.message


def test_boundary_fully_claimed_no_finding():
    row = _row()
    disp = _disp(row.row_id, "boundary", affirmed_hash="deadbeef00000000")
    model = _FakeBoundaryModel(
        crossing={row.row_id}, successor_id="CH05",
        successor_has_module=True, claimed={row.row_id},
    )
    findings = check_chapter([row], {row.row_id: disp}, boundary_model=model)
    assert all(
        f.rule not in (
            RULE_BOUNDARY_NOT_CROSSING, RULE_BOUNDARY_UNCLAIMED,
            RULE_BOUNDARY_MODEL_UNENFORCED,
        )
        for f in findings
    )


@pytest.mark.parametrize("live_chapter,expected", [(True, "error"), (False, "warning")])
def test_boundary_unclaimed_severity_follows_live_chapter(live_chapter, expected):
    row = _row()
    disp = _disp(row.row_id, "boundary", affirmed_hash="deadbeef00000000")
    model = _FakeBoundaryModel(crossing={row.row_id}, successor_id="CH05", claimed=set())
    findings = check_chapter([row], {row.row_id: disp}, boundary_model=model,
                              live_chapter=live_chapter)
    finding = next(f for f in findings if f.rule == RULE_BOUNDARY_UNCLAIMED)
    assert finding.severity == expected


@pytest.mark.parametrize("spec", ["cosmetic", "blocked:rock_smash", "beat:B1"])
def test_non_boundary_verdicts_untouched_by_boundary_rules(spec):
    row = _row()
    disp = _disp(row.row_id, spec, affirmed_hash="deadbeef00000000")
    model = _FakeBoundaryModel(crossing=set(), successor_id=None)
    findings = check_chapter([row], {row.row_id: disp}, boundary_model=model)
    assert all(
        f.rule not in (
            RULE_BOUNDARY_NOT_CROSSING, RULE_BOUNDARY_UNCLAIMED,
            RULE_BOUNDARY_MODEL_UNENFORCED,
        )
        for f in findings
    )


# --- rule 11: a vacuous trigger overlay must not read as a clean route -----
#
# PROJECT_TODO #75 / REDERIVATION_PLAN P1: CH05's first solve reported a
# clean 155-tile route (zero CROSSING lines) before the object events it
# needed even existed -- the trigger overlay had nothing to check against,
# not a genuinely clear path. These tests pin the sibling rule to
# RULE_ROUTE_MODEL_UNENFORCED that catches that class of false pass.


class _FakeTriggerOverlay:
    """A minimal `TriggerOverlayModel` for tests -- `seen` is the set of map
    ids the fake overlay actually found a TRAINER_SIGHT tile on; every other
    map id reads as vacuous, same as a real overlay with no trainer object
    events on it."""

    def __init__(self, seen: set[int]) -> None:
        self._seen = seen

    def has_trainer_sight_tiles(self, map_id: int) -> bool:
        return map_id in self._seen


def test_trigger_overlay_unenforced_without_model():
    row = _trainer_row("map001/ev001/p0")
    disp = _disp(row.row_id, "beat:B1", affirmed_hash="deadbeef00000000")
    findings = check_chapter([row], {row.row_id: disp}, trigger_overlay=None)
    unenforced = [f for f in findings if f.rule == RULE_TRIGGER_OVERLAY_MODEL_UNENFORCED]
    assert len(unenforced) == 1
    assert unenforced[0].severity == "warning"
    assert unenforced[0].row_id == "chapter"
    assert all(f.rule != RULE_TRIGGER_OVERLAY_VACUOUS for f in findings)


def test_trigger_overlay_vacuous_on_trainer_map_is_error():
    row = _trainer_row("map001/ev001/p0", map_id=7)
    disp = _disp(row.row_id, "beat:B1", affirmed_hash="deadbeef00000000")
    overlay = _FakeTriggerOverlay(seen=set())  # nothing seen anywhere
    findings = check_chapter([row], {row.row_id: disp}, trigger_overlay=overlay)
    finding = next(f for f in findings if f.rule == RULE_TRIGGER_OVERLAY_VACUOUS)
    assert finding.severity == "error"
    assert finding.row_id == "map007"
    assert "zero TRAINER_SIGHT tiles" in finding.message
    assert all(f.rule != RULE_TRIGGER_OVERLAY_MODEL_UNENFORCED for f in findings)


def test_trigger_overlay_present_on_trainer_map_no_finding():
    row = _trainer_row("map001/ev001/p0", map_id=7)
    disp = _disp(row.row_id, "beat:B1", affirmed_hash="deadbeef00000000")
    overlay = _FakeTriggerOverlay(seen={7})
    findings = check_chapter([row], {row.row_id: disp}, trigger_overlay=overlay)
    assert all(
        f.rule not in (RULE_TRIGGER_OVERLAY_VACUOUS, RULE_TRIGGER_OVERLAY_MODEL_UNENFORCED)
        for f in findings
    )


def test_trigger_overlay_no_trainer_rows_is_silent_even_without_model():
    """No trainer archetype anywhere -- the rule has nothing to check, so it
    must not manufacture an unenforced warning just because `trigger_overlay`
    is None (mirrors RULE_ROUTE_MODEL_UNENFORCED's own always-fires shape
    being the one thing this rule deliberately does NOT copy: that rule
    checks the whole chapter's walk, this one only maps with a trainer)."""
    row = _row(effects=("text",), content_hash="h1")
    disp = _disp(row.row_id, "cosmetic", affirmed_hash="h1")
    findings = check_chapter([row], {row.row_id: disp}, trigger_overlay=None)
    assert all(
        f.rule not in (RULE_TRIGGER_OVERLAY_VACUOUS, RULE_TRIGGER_OVERLAY_MODEL_UNENFORCED)
        for f in findings
    )


def test_trigger_overlay_undispositioned_trainer_row_not_counted():
    """A trainer row with no disposition on file yet is already covered by
    RULE_UNDISPOSITIONED/RULE_ARCHETYPE_CONFORMANCE -- it must not also
    force a trigger-overlay verdict for a battle nobody has confirmed is
    live content yet."""
    row = _trainer_row("map001/ev001/p0", map_id=7)
    overlay = _FakeTriggerOverlay(seen=set())
    findings = check_chapter([row], {}, trigger_overlay=overlay)
    assert all(
        f.rule not in (RULE_TRIGGER_OVERLAY_VACUOUS, RULE_TRIGGER_OVERLAY_MODEL_UNENFORCED)
        for f in findings
    )


def test_check_trigger_overlay_standalone_multiple_maps():
    """`check_trigger_overlay` is exported standalone so
    `routing.__main__.plan_cmd` can call it directly at the ROUTE step,
    without going through the rest of `check_chapter`'s rules (which need a
    disposition on every row, an unrelated concern for a bare routing
    solve). One vacuous map among several dispositioned trainer maps must
    report exactly that map, not all of them."""
    rows = [
        _trainer_row("map001/ev001/p0", map_id=1, event_id=1),
        _trainer_row("map002/ev001/p0", map_id=2, event_id=1),
    ]
    dispositions = {
        rows[0].row_id: _disp(rows[0].row_id, "beat:B1", affirmed_hash="deadbeef00000000"),
        rows[1].row_id: _disp(rows[1].row_id, "beat:B2", affirmed_hash="deadbeef00000000"),
    }
    overlay = _FakeTriggerOverlay(seen={1})  # map 2 is vacuous
    findings = check_trigger_overlay(rows, dispositions, trigger_overlay=overlay)
    assert len(findings) == 1
    assert findings[0].rule == RULE_TRIGGER_OVERLAY_VACUOUS
    assert findings[0].row_id == "map002"


# --- render: every schema verdict reaches the review view --------------


def test_render_expands_boundary_row():
    """A `boundary` row must appear in the rendered review.

    Regression guard for the gap the #72/#73 work opened: `boundary` was
    added to `schema._VERDICTS` while `render.py` still enumerated the four
    older verdicts by hand and bucketed with `setdefault`, so a
    `boundary`-dispositioned row was collected into a bucket nothing ever
    read -- present in the manifest and in the checker, invisible in the one
    artifact a human reviews.
    """
    row = _row(row_id="map035/ev001/p0", effects=("transfer",), content_hash="h1",
               condition=PageCondition())
    disp = _disp(row.row_id, "boundary", affirmed_hash="h1")
    md = render_review([row], {row.row_id: disp})
    assert "## Boundary (1)" in md
    assert f"### `{row.row_id}`" in md
    assert "- boundary: 1" in md


def test_render_covers_every_schema_verdict():
    """`render.py` renders every verdict the schema defines -- collapsed or
    expanded, but never dropped. The module raises at import if this is
    violated; this test states the invariant where a reader of the schema
    will find it, and fails at the same moment for the same reason."""
    from rpg2gba.chapter_manifest import render
    from rpg2gba.chapter_manifest.schema import _VERDICTS

    assert render._RENDERED_VERDICTS == _VERDICTS
