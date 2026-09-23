"""Tests for Task 3 (assignments/C8/03_engine_audit_flags.md): `engine-audit`
checking every `ENGINE_ATTRIBUTES` flag against the fork-capability index.

This supersedes `test_engine_attribute_flags_exist_in_the_fork` in
`tests/test_ruby_subset_evaluate.py` -- that test greps header text (the
exact class of check CLAUDE.md §4.7 exists to replace); this file checks the
`engine_audit` module's own report, via a `ForkIndex`, per R4.

Design assumption (see R3): the spec deliberately leaves open whether the
check injects the fork index as a parameter or catches a build failure and
records a "could not verify" finding. These tests assume the injection
half of that choice -- `audit(..., engine_index: ForkIndex | None = None)`
-- because it is the only half testable without a real `engine/` tree or
monkeypatching a specific internal call name. If the landed implementation
instead only catches inside `run_real_audit` and never exposes an
`engine_index` parameter on `audit`, the `audit`-level tests here will need
updating to monkeypatch whatever function builds the index instead; the
*behavioural* assertions (finding names attribute+flag, `ok` is False,
skipped is visible and distinct from "verified clean") should still hold.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.conversion_agent.fork_index import ForkIndex, load_or_build
from rpg2gba.ruby_subset.builtins import ENGINE_ATTRIBUTES
from rpg2gba.story_state.engine_audit import AuditReport, audit, format_report

OUT_DIR = Path("output/uranium-build")
_ENGINE_DIR = Path("engine")

pytestmark = pytest.mark.skip(reason="assignments/C8/03_engine_audit_flags.md not started")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _empty_engine_tree(tmp_path: Path) -> Path:
    """A synthetic `engine_dir` with no fenced regions at all, so the
    non-flag parts of the report (undeclared/missing/owed/gaps) stay empty
    and don't interfere with the flag-specific assertions."""
    _write(tmp_path / "src" / "empty.c", "void F(void)\n{\n}\n")
    return tmp_path


def _complete_index() -> ForkIndex:
    """A synthetic ForkIndex whose `constants` set contains every flag
    ENGINE_ATTRIBUTES names -- the "everything resolves" case."""
    flags = {ea.flag for ea in ENGINE_ATTRIBUTES.values()}
    return ForkIndex(
        specials={"HealPlayerParty"},
        script_macros={"msgbox"},
        movement_tokens={"walk_up"},
        constants=flags | {"SOME_OTHER_CONSTANT"},
        tree_hash="synthetic",
    )


def _index_missing_one_flag(missing_flag: str) -> ForkIndex:
    """A synthetic ForkIndex with every ENGINE_ATTRIBUTES flag EXCEPT
    `missing_flag`."""
    flags = {ea.flag for ea in ENGINE_ATTRIBUTES.values() if ea.flag != missing_flag}
    return ForkIndex(
        specials={"HealPlayerParty"},
        script_macros={"msgbox"},
        movement_tokens={"walk_up"},
        constants=flags,
        tree_hash="synthetic",
    )


# --- R2: a missing flag produces one finding naming attribute AND flag -----


def test_missing_flag_produces_one_finding_naming_attribute_and_flag(tmp_path: Path) -> None:
    """R2: a synthetic index missing FLAG_SYS_POKEDEX_GET produces exactly
    one unresolved-flag finding, and that finding names both the attribute
    ($Trainer.pokedex) and the flag (FLAG_SYS_POKEDEX_GET)."""
    engine_dir = _empty_engine_tree(tmp_path)
    index = _index_missing_one_flag("FLAG_SYS_POKEDEX_GET")

    report = audit(
        engine_dir, flag_state={"switches": {}, "variables": {}},
        intro_end_state=(), chapter_read_keys=set(), engine_index=index,
    )

    assert len(report.unresolved_engine_flags) == 1
    finding = report.unresolved_engine_flags[0]
    detail = finding.detail
    assert "$Trainer" in detail and "pokedex" in detail
    assert "FLAG_SYS_POKEDEX_GET" in detail
    # Structured fields too, not just prose -- a caller shouldn't have to
    # regex the detail string to know what broke.
    assert finding.flag == "FLAG_SYS_POKEDEX_GET"
    assert finding.attribute == "pokedex"


# --- R1: a complete index produces no findings, and ok reflects it --------


def test_complete_index_produces_no_findings(tmp_path: Path) -> None:
    """R1: every ENGINE_ATTRIBUTES flag resolving in the index produces zero
    unresolved-flag findings, and does not by itself break `ok`."""
    engine_dir = _empty_engine_tree(tmp_path)
    index = _complete_index()

    report = audit(
        engine_dir, flag_state={"switches": {}, "variables": {}},
        intro_end_state=(), chapter_read_keys=set(), engine_index=index,
    )

    assert report.unresolved_engine_flags == ()
    assert report.engine_flag_check_skipped is None
    # Not `assert report.ok` here: a bare empty synthetic engine tree also
    # trips the module's OTHER checks (missing_transition_writes etc. against
    # the real TRANSITIONS/OBLIGATIONS tables) -- unrelated to this task.
    # What this test owns is that the flag check itself contributes nothing.


# --- R1: ok is False when a flag is unresolved (unlike the informational
# intro_seed_unread / deferred_obligations fields) --------------------------


def test_ok_is_false_when_a_flag_is_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R1: the new field counts toward `ok` -- an unresolved flag is a hard
    failure, unlike `intro_seed_unread`/`deferred_obligations` which are
    deliberately excluded. TRANSITIONS/OBLIGATIONS are emptied (matching
    the sibling file's isolation pattern) so `ok` flips solely because of
    the unresolved flag, not some unrelated real-table mismatch."""
    import rpg2gba.story_state.engine_audit as ea_mod

    monkeypatch.setattr(ea_mod, "TRANSITIONS", ())
    monkeypatch.setattr(ea_mod, "OBLIGATIONS", ())

    engine_dir = _empty_engine_tree(tmp_path)
    index = _index_missing_one_flag("FLAG_SYS_B_DASH")

    report = ea_mod.audit(
        engine_dir, flag_state={"switches": {}, "variables": {}},
        intro_end_state=(), chapter_read_keys=set(), engine_index=index,
    )

    assert report.unresolved_engine_flags != ()
    assert report.undeclared_writes == () and report.owed_obligations == ()
    assert not report.ok


def test_all_four_missing_reports_all_four(tmp_path: Path) -> None:
    """Sanity: the check iterates the whole ENGINE_ATTRIBUTES table, not
    just the first entry -- an index resolving nothing reports all four."""
    engine_dir = _empty_engine_tree(tmp_path)
    empty_index = ForkIndex(
        specials={"HealPlayerParty"}, script_macros={"msgbox"},
        movement_tokens={"walk_up"}, constants=set(), tree_hash="synthetic",
    )

    report = audit(
        engine_dir, flag_state={"switches": {}, "variables": {}},
        intro_end_state=(), chapter_read_keys=set(), engine_index=empty_index,
    )

    assert len(report.unresolved_engine_flags) == len(ENGINE_ATTRIBUTES)
    found_flags = {f.flag for f in report.unresolved_engine_flags}
    assert found_flags == {ea.flag for ea in ENGINE_ATTRIBUTES.values()}


# --- R1: format_report contains the new section -----------------------------


def test_format_report_contains_unresolved_engine_flags_section(tmp_path: Path) -> None:
    """R1: `format_report` surfaces the new check as its own section,
    matching the module's existing per-field style."""
    engine_dir = _empty_engine_tree(tmp_path)
    index = _index_missing_one_flag("FLAG_SYS_POKENAV_GET")

    report = audit(
        engine_dir, flag_state={"switches": {}, "variables": {}},
        intro_end_state=(), chapter_read_keys=set(), engine_index=index,
    )
    text = format_report(report)

    assert "unresolved_engine_flags" in text
    assert "FLAG_SYS_POKENAV_GET" in text
    assert "NOT OK" in text


def test_format_report_clean_case_still_names_the_section(tmp_path: Path) -> None:
    """The section header appears even with zero findings (count-in-parens
    style, matching every other AuditReport field) -- a reader shouldn't
    have to infer "the check ran and found nothing" from the section's
    absence."""
    engine_dir = _empty_engine_tree(tmp_path)
    report = audit(
        engine_dir, flag_state={"switches": {}, "variables": {}},
        intro_end_state=(), chapter_read_keys=set(), engine_index=_complete_index(),
    )
    text = format_report(report)
    assert "unresolved_engine_flags (0)" in text


# --- R3: the absent-fork path must be visible, never a silent pass ---------
#
# ASSUMPTION (documented at module top): audit() takes an `engine_index`
# parameter; omitting/None means "could not verify", per the injection half
# of R3's two options.


def test_engine_index_none_is_not_silently_treated_as_clean(tmp_path: Path) -> None:
    """R3: when the fork index is unavailable, the report must not claim the
    flags were verified. Concretely: `unresolved_engine_flags` stays empty
    (nothing WAS found unresolved -- the check didn't run), but a distinct,
    visible marker records that the check was skipped, so a reader can't
    mistake "empty" for "checked and clean"."""
    engine_dir = _empty_engine_tree(tmp_path)

    report = audit(
        engine_dir, flag_state={"switches": {}, "variables": {}},
        intro_end_state=(), chapter_read_keys=set(), engine_index=None,
    )

    assert report.unresolved_engine_flags == ()
    assert report.engine_flag_check_skipped is not None
    assert report.engine_flag_check_skipped != ""


def test_engine_index_none_skip_reason_is_visible_in_format_report(tmp_path: Path) -> None:
    """R3: the skip is not just a field nobody prints -- `format_report`'s
    text must say the engine-flag check did not run, not just stay silent
    about it (which would look identical to a clean pass at a glance)."""
    engine_dir = _empty_engine_tree(tmp_path)

    report = audit(
        engine_dir, flag_state={"switches": {}, "variables": {}},
        intro_end_state=(), chapter_read_keys=set(), engine_index=None,
    )
    text = format_report(report)

    assert report.engine_flag_check_skipped in text
    # And critically: a skipped check is not silently rolled into "0
    # findings, all good" -- the skip text is distinguishable from the
    # ordinary zero-findings section tested above.
    assert "unresolved_engine_flags (0)" in text  # still present, honest about the count
    assert "skipped" in text.lower()


def test_default_call_without_engine_index_also_skips(tmp_path: Path) -> None:
    """The default (no `engine_index` argument at all, matching every
    pre-existing caller of `audit()` in test_story_state_engine_audit.py)
    must degrade the same way as an explicit `engine_index=None` -- old
    call sites don't accidentally get a false "verified clean"."""
    engine_dir = _empty_engine_tree(tmp_path)

    report = audit(
        engine_dir, flag_state={"switches": {}, "variables": {}},
        intro_end_state=(), chapter_read_keys=set(),
    )

    assert report.engine_flag_check_skipped is not None
    assert report.unresolved_engine_flags == ()


# --- R4 note: no test here retires/keeps the old grep-based test; that's a
# judgment call the task file assigns to the implementer via Q4, not
# something this test file enforces either way.


# --- real-tree: all four ENGINE_ATTRIBUTES flags resolve in the vendored
# engine/, matching the 2026-09-23 measured fact and test_run_real_audit_is_
# clean's skipif style. --------------------------------------------------


@pytest.mark.skipif(not _ENGINE_DIR.is_dir(), reason="engine/ not present")
def test_all_engine_attribute_flags_resolve_in_the_real_fork() -> None:
    """R1/R2 real-tree: building a real ForkIndex from the vendored engine/
    and running it through `audit` finds every ENGINE_ATTRIBUTES flag,
    leaving the audit green on this check -- all four currently resolve
    (measured 2026-09-23), so a correct implementation must not turn this
    red."""
    index = load_or_build()
    report = audit(
        Path("engine"), flag_state={"switches": {}, "variables": {}},
        intro_end_state=(), chapter_read_keys=set(), engine_index=index,
    )
    assert report.unresolved_engine_flags == (), format_report(report)
    assert report.engine_flag_check_skipped is None
