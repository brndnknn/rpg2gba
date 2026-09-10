"""Tests for `rpg2gba.capability_sites` -- the derivation behind
`chapter_manifest.checker.CapabilityModel` (REDERIVATION_PLAN.md P8).

Every `blocked:<capability>` disposition has, until this module existed,
reported `capability_model_unenforced` unconditionally -- there was no
implementation of the `CapabilityModel` Protocol. This scans map JSON for
`code 121` (Control Switches) / `code 122` (Control Variables) writes and
answers, per capability token, where (if anywhere) it is granted.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.capability_sites import (
    AmbiguousTokenError,
    CapabilitySitesError,
    derive_capability_sites,
    token_for_label,
)


def _switch_cmd(sw_lo: int, value: int, sw_hi: int | None = None) -> dict:
    return {"code": 121, "parameters": [sw_lo, sw_hi if sw_hi is not None else sw_lo, value]}


def _var_cmd(var_id: int, operation: int, operand_type: int, operand: int) -> dict:
    return {"code": 122, "parameters": [var_id, var_id, operation, operand_type, operand]}


def _map(map_id: int, events: list[dict]) -> dict:
    return {
        "map_id": map_id,
        "tileset_id": 1,
        "width": 10,
        "height": 10,
        "events": events,
    }


def _event(event_id: int, pages: list[list[dict]]) -> dict:
    return {
        "id": event_id,
        "name": f"ev{event_id}",
        "x": 0,
        "y": 0,
        "pages": [{"trigger": 0, "list": cmds} for cmds in pages],
    }


def _write_maps(tmp_path: Path, maps: dict[int, dict]) -> Path:
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    for map_id, data in maps.items():
        (maps_dir / f"Map{map_id:03d}.json").write_text(json.dumps(data), encoding="utf-8")
    return maps_dir


def _write_sidecars(
    tmp_path: Path, switches: dict[int, str], variables: dict[int, str]
) -> tuple[Path, Path]:
    sw_path = tmp_path / "switches.json"
    var_path = tmp_path / "variables.json"
    sw_path.write_text(json.dumps({str(k): v for k, v in switches.items()}), encoding="utf-8")
    var_path.write_text(json.dumps({str(k): v for k, v in variables.items()}), encoding="utf-8")
    return sw_path, var_path


def _write_chapters(tmp_path: Path, chapters: list[dict]) -> Path:
    path = tmp_path / "chapters.json"
    path.write_text(json.dumps({"chapters": chapters}), encoding="utf-8")
    return path


# --- token_for_label ---------------------------------------------------------


def test_token_for_label_lowercases_and_collapses_separators() -> None:
    assert token_for_label("FINAL EVENT") == "final_event"
    assert token_for_label("Got Pokemon") == "got_pokemon"


def test_token_for_label_drops_apostrophes_and_periods() -> None:
    assert token_for_label("Mr. Mime's Bell") == "mr_mimes_bell"


def test_token_for_label_prefixes_a_leading_digit() -> None:
    assert token_for_label("1st Badge") == "c_1st_badge"


def test_token_for_label_rejects_all_punctuation() -> None:
    with pytest.raises(CapabilitySitesError):
        token_for_label("---")


# --- ON vs OFF direction ------------------------------------------------------


def test_on_write_grants_off_write_does_not(tmp_path: Path) -> None:
    maps_dir = _write_maps(tmp_path, {
        1: _map(1, [_event(1, [[_switch_cmd(10, 0)]])]),   # ON
        2: _map(2, [_event(2, [[_switch_cmd(10, 1)]])]),   # OFF, a reset
    })
    sw_json, var_json = _write_sidecars(tmp_path, {10: "Got Pokemon"}, {})
    chapters_json = _write_chapters(tmp_path, [])

    d = derive_capability_sites(maps_dir, sw_json, var_json, chapters_json)
    sites = d.grant_sites("got_pokemon")
    assert sites is not None
    assert len(sites) == 1
    assert sites[0].row_id == "map001/ev001/p0"

    # The OFF write is recorded (visible in switch_writes) but never counted
    # as a grant.
    off_writes = [w for w in d.switch_writes if w.direction == "off"]
    assert len(off_writes) == 1
    assert off_writes[0].row_id == "map002/ev002/p0"


def test_switch_never_turned_on_is_confidently_empty_not_undetermined(
    tmp_path: Path,
) -> None:
    maps_dir = _write_maps(tmp_path, {
        1: _map(1, [_event(1, [[_switch_cmd(20, 1)]])]),  # OFF only
    })
    sw_json, var_json = _write_sidecars(tmp_path, {20: "Never Granted"}, {})
    chapters_json = _write_chapters(tmp_path, [])

    d = derive_capability_sites(maps_dir, sw_json, var_json, chapters_json)
    assert d.grant_sites("never_granted") == ()


# --- s: prefix exclusion ------------------------------------------------------


def test_script_switch_is_excluded_entirely(tmp_path: Path) -> None:
    maps_dir = _write_maps(tmp_path, {
        1: _map(1, [_event(1, [[_switch_cmd(30, 0)]])]),
    })
    sw_json, var_json = _write_sidecars(
        tmp_path, {30: "s:tsOn?(\"A\")"}, {}
    )
    chapters_json = _write_chapters(tmp_path, [])

    d = derive_capability_sites(maps_dir, sw_json, var_json, chapters_json)
    assert d.switch_writes == ()
    assert d.tokens == ()


# --- ambiguous token collision -------------------------------------------------


def test_two_switches_with_the_same_label_raise(tmp_path: Path) -> None:
    maps_dir = _write_maps(tmp_path, {
        1: _map(1, [_event(1, [[_switch_cmd(40, 0)]])]),
        2: _map(2, [_event(2, [[_switch_cmd(41, 0)]])]),
    })
    sw_json, var_json = _write_sidecars(
        tmp_path, {40: "Duplicate Name", 41: "Duplicate Name"}, {}
    )
    chapters_json = _write_chapters(tmp_path, [])

    with pytest.raises(AmbiguousTokenError):
        derive_capability_sites(maps_dir, sw_json, var_json, chapters_json)


# --- code 122: constant set vs computed op ------------------------------------


def test_constant_set_grants_threshold_token(tmp_path: Path) -> None:
    maps_dir = _write_maps(tmp_path, {
        1: _map(1, [_event(1, [[_var_cmd(101, operation=0, operand_type=0, operand=4)]])]),
    })
    sw_json, var_json = _write_sidecars(tmp_path, {}, {101: "Quest Log"})
    chapters_json = _write_chapters(tmp_path, [])

    d = derive_capability_sites(maps_dir, sw_json, var_json, chapters_json)
    sites = d.grant_sites("quest_log_4")
    assert sites is not None
    assert len(sites) == 1
    assert sites[0].row_id == "map001/ev001/p0"


def test_computed_write_is_recorded_undetermined_and_mints_no_token(
    tmp_path: Path,
) -> None:
    """A relative (Add) write, or a Set whose operand is itself a variable,
    cannot be resolved to a known constant -- no threshold token is minted
    for it at all, so asking about a guessed threshold name resolves to
    `None` (undetermined), never a false negative `()`."""
    maps_dir = _write_maps(tmp_path, {
        1: _map(1, [_event(1, [[_var_cmd(101, operation=1, operand_type=0, operand=1)]])]),
        2: _map(2, [_event(2, [[_var_cmd(101, operation=0, operand_type=1, operand=5)]])]),
    })
    sw_json, var_json = _write_sidecars(tmp_path, {}, {101: "Quest Log"})
    chapters_json = _write_chapters(tmp_path, [])

    d = derive_capability_sites(maps_dir, sw_json, var_json, chapters_json)
    assert d.tokens == ()
    assert d.grant_sites("quest_log_1") is None

    determined = [w for w in d.variable_writes if w.determined]
    assert determined == []
    assert len(d.variable_writes) == 2


def test_a_variable_with_both_constant_and_computed_writes_still_grants(
    tmp_path: Path,
) -> None:
    """The threshold token derived from the constant write is granted at
    that constant site even though the same variable also carries an
    unresolved (computed) write elsewhere -- one real answer beats a
    manufactured "undetermined" when a real answer exists."""
    maps_dir = _write_maps(tmp_path, {
        1: _map(1, [_event(1, [[_var_cmd(101, operation=0, operand_type=0, operand=2)]])]),
        2: _map(2, [_event(2, [[_var_cmd(101, operation=1, operand_type=0, operand=1)]])]),
    })
    sw_json, var_json = _write_sidecars(tmp_path, {}, {101: "Quest Log"})
    chapters_json = _write_chapters(tmp_path, [])

    d = derive_capability_sites(maps_dir, sw_json, var_json, chapters_json)
    sites = d.grant_sites("quest_log_2")
    assert sites is not None
    assert len(sites) == 1
    assert sites[0].row_id == "map001/ev001/p0"


# --- undetermined for a name with no source at all ----------------------------


def test_unknown_token_with_no_switch_or_variable_source_is_undetermined(
    tmp_path: Path,
) -> None:
    maps_dir = _write_maps(tmp_path, {1: _map(1, [])})
    sw_json, var_json = _write_sidecars(tmp_path, {}, {})
    chapters_json = _write_chapters(tmp_path, [])

    d = derive_capability_sites(maps_dir, sw_json, var_json, chapters_json)
    assert d.grant_sites("rock_smash") is None
    assert d.grant_sites("surf") is None


# --- chapter ownership ---------------------------------------------------------


def test_grant_site_chapter_id_comes_from_chapters_json(tmp_path: Path) -> None:
    maps_dir = _write_maps(tmp_path, {
        1: _map(1, [_event(1, [[_switch_cmd(50, 0)]])]),
    })
    sw_json, var_json = _write_sidecars(tmp_path, {50: "Some Flag"}, {})
    chapters_json = _write_chapters(tmp_path, [
        {"id": "CH01", "maps": [1]},
    ])

    d = derive_capability_sites(maps_dir, sw_json, var_json, chapters_json)
    sites = d.grant_sites("some_flag")
    assert sites is not None
    assert sites[0].chapter_id == "CH01"


def test_grant_site_chapter_id_is_none_when_map_is_unowned(tmp_path: Path) -> None:
    maps_dir = _write_maps(tmp_path, {
        1: _map(1, [_event(1, [[_switch_cmd(50, 0)]])]),
    })
    sw_json, var_json = _write_sidecars(tmp_path, {50: "Some Flag"}, {})
    chapters_json = _write_chapters(tmp_path, [])

    d = derive_capability_sites(maps_dir, sw_json, var_json, chapters_json)
    sites = d.grant_sites("some_flag")
    assert sites is not None
    assert sites[0].chapter_id is None


# --- real corpus smoke test ---------------------------------------------------


def test_real_corpus_final_event_and_got_pokemon() -> None:
    """Pinned against the real corpus (2026-09-10): `FINAL EVENT` (switch
    125) is granted exactly once, from map199 -- the single most-gated
    switch in CH01's rederivation backlog. If this breaks because the
    corpus changed, that's real news; update the assertion."""
    d = derive_capability_sites()
    sites = d.grant_sites("final_event")
    assert sites is not None
    assert len(sites) == 1
    assert sites[0].row_id == "map199/ev001/p0"

    assert d.grant_sites("rock_smash") is None
    assert d.grant_sites("surf") is None


def test_an_unminted_threshold_is_computed_not_reported_undetermined() -> None:
    """`quest_log_1` must resolve even though nothing writes exactly 1.

    Threshold tokens are minted only for values the corpus actually writes,
    so var 101 ("Quest Log") mints `quest_log_2` and `quest_log_4` and not
    `quest_log_1` -- yet both of those writes satisfy `>= 1`, so the answer
    is knowable. Reporting None there would say "cannot tell" about a
    question with an answer, and would silently miss
    `RULE_BLOCKED_ALREADY_GRANTED` on the 12 CH01 rows gated `Quest Log >= 1`
    -- the exact error this model exists to catch.
    """
    derivation = derive_capability_sites()

    minted = derivation.grant_sites("quest_log_2")
    assert minted, "precondition: quest_log_2 is a minted token with sites"

    computed = derivation.grant_sites("quest_log_1")
    assert computed is not None, "quest_log_1 is answerable, not undetermined"
    # Every write satisfying >= 2 also satisfies >= 1, so >= 1 is a superset.
    assert {s.row_id for s in minted} <= {s.row_id for s in computed}


def test_a_threshold_no_constant_write_reaches_stays_undetermined() -> None:
    """`quest_log_5` must stay None, but for the right reason.

    No constant write to var 101 reaches 5 (the corpus's highest is 4), but
    the variable also carries computed writes (`map042/ev003/p0`,
    `map050/ev019/p0`) whose values this module cannot resolve without
    executing the game. One of those could reach 5, so the honest answer is
    "cannot tell" -- not `()`, which would assert nothing grants it.
    """
    derivation = derive_capability_sites()
    assert derivation.grant_sites("quest_log_5") is None
    assert derivation.grant_sites("quest_log_99") is None


def test_a_nonsense_threshold_token_is_not_invented() -> None:
    """A token whose base names no variable resolves to None, not to a
    fabricated empty grant set."""
    derivation = derive_capability_sites()
    assert derivation.grant_sites("not_a_real_variable_3") is None


def test_switch_and_variable_bases_that_collide_are_reported() -> None:
    """Five bases name BOTH a switch and a variable, so `<base>` and
    `<base>_<n>` are different game objects.

    `final_event` is switch 125 (granted at `map199/ev001/p0`, CH57) while
    `final_event_2` is variable 127 (CH56) -- they read as one capability at
    two thresholds and are unrelated. This is not `AmbiguousTokenError`: no
    two token strings collide and each resolves deterministically, so
    raising would break an otherwise-correct derivation. But it must not be
    silent, because a reviewer reading `blocked:final_event` next to
    `blocked:final_event_2` has no way to see they are different things.
    """
    derivation = derive_capability_sites()

    assert "final_event" in derivation.colliding_bases
    switch_id, var_id = derivation.colliding_bases["final_event"]
    assert (switch_id, var_id) == (125, 127)

    bare = derivation.grant_sites("final_event")
    suffixed = derivation.grant_sites("final_event_2")
    assert bare and suffixed
    assert {s.row_id for s in bare}.isdisjoint({s.row_id for s in suffixed})
