"""Tests for `derivation.derive_entry` -- the pure logic behind the
machine-derived sidecar and the checker's recompute.

Fixture idiom matches `test_chapter_manifest_checker.py`: build `ManifestRow`
objects directly, not through the generator. Fakes for `BeatModel`/
`BoundaryModel` stand in for the real adapters -- this module must not
import `checker.py`'s concrete `playtest`/`chapter_atlas`-backed
implementations.
"""
from __future__ import annotations

from rpg2gba.chapter_manifest.derivation import DerivedEntry, derive_entry
from rpg2gba.chapter_manifest.generator_status import GeneratorStatus
from rpg2gba.chapter_manifest.schema import Disposition, ManifestRow


def _row(row_id: str = "map001/ev001/p0", **overrides) -> ManifestRow:
    defaults = dict(
        row_id=row_id,
        kind="page",
        map_id=1,
        content_hash="deadbeef00000000",
        effects=(),
        reachability_consulted=True,
    )
    defaults.update(overrides)
    return ManifestRow(**defaults)


class _Beats:
    def __init__(self, claims: dict[str, tuple[str, ...]] | None = None) -> None:
        self._claims = claims or {}

    def is_registered(self, beat_id: str) -> bool:
        return True

    def deferral_reason(self, beat_id: str) -> str | None:
        return None

    def claiming_beats(self, row_id: str) -> tuple[str, ...]:
        return self._claims.get(row_id, ())


class _Boundary:
    def __init__(self, crossing: set[str] | None = None) -> None:
        self._crossing = crossing or set()

    def is_forward_crossing(self, row_id: str) -> bool:
        return row_id in self._crossing

    def successor_chapter_id(self) -> str | None:
        return None

    def successor_has_module(self) -> bool:
        return False

    def successor_claims(self, row_id: str) -> bool:
        return False


# --- each verdict, in isolation ---------------------------------------------


def test_derives_cosmetic():
    row = _row(content_hash="h1", unhandled=0)
    entry = derive_entry(row, beat_model=None, boundary_model=None)
    assert entry == DerivedEntry(disposition="cosmetic", derived_hash="h1")


def test_derives_beat_from_single_family():
    row = _row(content_hash="h1", unhandled=0)
    entry = derive_entry(
        row, beat_model=_Beats({row.row_id: ("B4_battle", "B4_retalk")}),
        boundary_model=None)
    assert entry == DerivedEntry(disposition="beat:B4", derived_hash="h1")


def test_derives_beat_from_bare_beat_id_with_no_underscore():
    row = _row(content_hash="h1", unhandled=0)
    entry = derive_entry(
        row, beat_model=_Beats({row.row_id: ("B4",)}), boundary_model=None)
    assert entry == DerivedEntry(disposition="beat:B4", derived_hash="h1")


def test_derives_boundary():
    row = _row(content_hash="h1", unhandled=0, effects=("warp",))
    entry = derive_entry(
        row, beat_model=None, boundary_model=_Boundary({row.row_id}))
    assert entry == DerivedEntry(disposition="boundary", derived_hash="h1")


def test_derives_blocked_as_a_proposal():
    row = _row(content_hash="h1", unhandled=0, requires=("rock_smash",))
    entry = derive_entry(row, beat_model=None, boundary_model=None)
    assert entry == DerivedEntry(
        disposition="blocked:rock_smash", derived_hash="h1", proposed=True)


def test_derives_blocked_and_semantics_for_multiple_requires():
    row = _row(content_hash="h1", unhandled=0, requires=("strength", "rock_smash"))
    entry = derive_entry(row, beat_model=None, boundary_model=None)
    assert entry is not None
    assert entry.disposition == "blocked:rock_smash+strength"
    assert entry.proposed is True


# --- precedence: boundary > beat > blocked > cosmetic -----------------------


def test_boundary_outranks_beat():
    row = _row(content_hash="h1", unhandled=0, effects=("warp",))
    entry = derive_entry(
        row,
        beat_model=_Beats({row.row_id: ("B4",)}),
        boundary_model=_Boundary({row.row_id}))
    assert entry == DerivedEntry(disposition="boundary", derived_hash="h1")


def test_beat_outranks_blocked():
    row = _row(content_hash="h1", unhandled=0, requires=("rock_smash",))
    entry = derive_entry(
        row, beat_model=_Beats({row.row_id: ("B4",)}), boundary_model=None)
    assert entry == DerivedEntry(disposition="beat:B4", derived_hash="h1")


def test_blocked_outranks_cosmetic():
    row = _row(content_hash="h1", unhandled=0, requires=("rock_smash",))
    entry = derive_entry(row, beat_model=None, boundary_model=None)
    assert entry is not None
    assert entry.disposition == "blocked:rock_smash"
    assert row.may_be_cosmetic and not row.may_be_derived


# --- undispositionable / needs-citation gate ---------------------------------


def test_undispositionable_row_derives_nothing():
    row = _row(content_hash="h1", unhandled=0, unrecognized_heads=("pbSomething",))
    assert derive_entry(row, beat_model=None, boundary_model=None) is None


def test_citation_owing_row_derives_nothing():
    row = _row(
        content_hash="h1", unhandled=0,
        condition_unclassified=("a || b",), script_typed_conditions=1)
    assert derive_entry(row, beat_model=None, boundary_model=None) is None


def test_needs_citation_gate_admits_only_the_generators_verdict():
    # A row owing a citation derives only from the generator (#124, operator
    # 2026-10-04): a beat claim stands in for the citation; a boundary read
    # off manifest structure does not.
    row = _row(
        content_hash="h1", unhandled=0, effects=("warp",),
        condition_unclassified=("a || b",), script_typed_conditions=1)
    entry = derive_entry(
        row,
        beat_model=_Beats({row.row_id: ("B4",)}),
        boundary_model=_Boundary({row.row_id}))
    assert entry is not None and entry.disposition == "beat:B4"
    assert derive_entry(row, beat_model=None, boundary_model=_Boundary({row.row_id})) is None


# --- beat family ambiguity ---------------------------------------------------


def test_multi_family_beat_claims_derive_nothing():
    row = _row(content_hash="h1", unhandled=0)
    entry = derive_entry(
        row, beat_model=_Beats({row.row_id: ("B4_battle", "B5_retalk")}),
        boundary_model=None)
    assert entry is None


def test_same_family_beat_claims_reduce_to_one_head():
    row = _row(content_hash="h1", unhandled=0)
    entry = derive_entry(
        row, beat_model=_Beats({row.row_id: ("B4_battle", "B4_retalk", "B4")}),
        boundary_model=None)
    assert entry == DerivedEntry(disposition="beat:B4", derived_hash="h1")


# --- ineligible-otherwise row derives nothing --------------------------------


def test_never_staged_row_derives_nothing():
    row = _row(content_hash="h1")  # unhandled defaults to None
    assert derive_entry(row, beat_model=None, boundary_model=None) is None


def test_state_writing_row_derives_nothing():
    row = _row(content_hash="h1", unhandled=0, effects=("giveitem",))
    assert derive_entry(row, beat_model=None, boundary_model=None) is None


# --- to_disposition -----------------------------------------------------------


def test_to_disposition_round_trips_a_clerical_entry():
    entry = DerivedEntry(disposition="beat:B4", derived_hash="h1")
    disp = entry.to_disposition("map001/ev001/p0")
    assert disp.verdict == "beat"
    assert disp.argument == "B4"


def test_to_disposition_round_trips_a_blocked_proposal():
    entry = DerivedEntry(disposition="blocked:rock_smash", derived_hash="h1", proposed=True)
    disp = entry.to_disposition("map001/ev001/p0")
    assert disp.verdict == "blocked"
    assert disp.argument == "rock_smash"


# --- generator status (PROJECT_TODO #124, 2026-10-04) --------------------------


_RID = "map001/ev001/p0"


def test_generator_status_fills_a_row_that_derived_none():
    row = _row(content_hash="h1", unhandled=0, effects=("giveitem",))
    assert derive_entry(row, beat_model=None, boundary_model=None) is None
    for spec in ("elsewhere:later: CH07", "refused:story-state: unmodelled_outcome",
                 "unreachable:beat_gen: the story model places it in no chapter"):
        status = GeneratorStatus(specs={_RID: spec})
        entry = derive_entry(row, beat_model=None, boundary_model=None,
                             generator_status=status)
        assert entry == DerivedEntry(disposition=spec, derived_hash="h1")
        assert not entry.proposed


def test_generator_status_never_overrides_an_existing_verdict():
    status = GeneratorStatus(specs={_RID: "elsewhere:empty_page: all empty"})
    cosmetic = _row(content_hash="h1", unhandled=0)
    assert derive_entry(cosmetic, beat_model=None, boundary_model=None,
                        generator_status=status).disposition == "cosmetic"
    blocked = _row(content_hash="h1", unhandled=0, requires=("rock_smash",))
    never = GeneratorStatus(specs={_RID: "elsewhere:never_fires: proof"})
    entry = derive_entry(blocked, beat_model=None, boundary_model=None,
                         generator_status=never)
    assert entry.disposition == "blocked:rock_smash" and entry.proposed
    beat = _row(content_hash="h1", unhandled=0, effects=("giveitem",))
    assert derive_entry(beat, beat_model=_Beats({_RID: ("B4",)}), boundary_model=None,
                        generator_status=status).disposition == "beat:B4"
    assert derive_entry(beat, beat_model=None, boundary_model=_Boundary({_RID}),
                        generator_status=status).disposition == "boundary"


def test_generator_status_answers_the_classification_gate():
    # #124 (operator 2026-10-04): the generator's record of an unrecognized-
    # head row is its classification -- derived, clerical.
    row = _row(content_hash="h1", unhandled=0, unrecognized_heads=("pbSomething",))
    status = GeneratorStatus(specs={_RID: "refused:C8: ruby"})
    entry = derive_entry(row, beat_model=None, boundary_model=None, generator_status=status)
    assert entry is not None and entry.disposition == "refused:C8: ruby"
    assert derive_entry(row, beat_model=None, boundary_model=None) is None


def test_generator_status_does_not_resolve_an_ambiguous_beat_claim():
    row = _row(content_hash="h1", unhandled=0, effects=("giveitem",))
    status = GeneratorStatus(specs={_RID: "elsewhere:later"})
    assert derive_entry(row, beat_model=_Beats({_RID: ("B4_a", "B5_b")}),
                        boundary_model=None, generator_status=status) is None


def test_generator_status_row_not_listed_derives_nothing():
    row = _row(content_hash="h1", unhandled=0, effects=("giveitem",))
    assert derive_entry(row, beat_model=None, boundary_model=None,
                        generator_status=GeneratorStatus(specs={})) is None


# --- branch-arm carve-out (operator ruling 2026-10-04, #124) -----------------

ARM = "map035/ev019/p0/b2"
PARENT = "map035/ev019/p0"


def _hand(spec: str) -> dict[str, Disposition]:
    return {PARENT: Disposition.parse(PARENT, spec, affirmed_hash="x")}


def test_arm_of_hand_blocked_parent_with_same_argument_is_clerical():
    row = _row(ARM, content_hash="h1", unhandled=0, requires=("rock_smash", "strength"))
    entry = derive_entry(row, beat_model=None, boundary_model=None,
                         hand_dispositions=_hand("blocked:rock_smash+strength"))
    assert entry == DerivedEntry(
        disposition="blocked:rock_smash+strength", derived_hash="h1", proposed=False)


def test_arm_with_different_parent_capability_stays_a_proposal():
    row = _row(ARM, content_hash="h1", unhandled=0, requires=("rock_smash",))
    entry = derive_entry(row, beat_model=None, boundary_model=None,
                         hand_dispositions=_hand("blocked:surf"))
    assert entry is not None and entry.proposed is True


def test_arm_with_non_blocked_parent_stays_a_proposal():
    row = _row(ARM, content_hash="h1", unhandled=0, requires=("rock_smash",))
    entry = derive_entry(row, beat_model=None, boundary_model=None,
                         hand_dispositions=_hand("boundary"))
    assert entry is not None and entry.proposed is True


def test_arm_with_no_hand_parent_stays_a_proposal():
    row = _row(ARM, content_hash="h1", unhandled=0, requires=("rock_smash",))
    for hand in (None, {}):
        entry = derive_entry(row, beat_model=None, boundary_model=None,
                             hand_dispositions=hand)
        assert entry is not None and entry.proposed is True


def test_non_arm_page_row_stays_a_proposal():
    row = _row(PARENT, content_hash="h1", unhandled=0, requires=("rock_smash",))
    # Even a hand entry on the row itself (or a "parent-like" sibling) is no carve-out.
    entry = derive_entry(row, beat_model=None, boundary_model=None,
                         hand_dispositions=_hand("blocked:rock_smash"))
    assert entry is not None and entry.proposed is True


def test_empty_page_outranks_a_requires_derived_block():
    """#63: a rock's empty post-smash page has nothing to block."""
    status = GeneratorStatus(specs={_RID: "elsewhere:empty_page: the obstacle's empty page"})
    blocked = _row(content_hash="h1", unhandled=0, requires=("rock_smash",))
    entry = derive_entry(blocked, beat_model=None, boundary_model=None, generator_status=status)
    assert entry.disposition == "elsewhere:empty_page: the obstacle's empty page"
    assert not entry.proposed
