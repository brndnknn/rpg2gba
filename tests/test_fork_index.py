"""Tests for the fork capability index + forward verification gate.

CLAUDE.md §4.7: the fork (`engine/`) is the source of truth for what the
engine can do, not memory of it. These tests pin the extraction against the
real vendored `pokeemerald-expansion` tree at `engine/` and exercise the
`verify_script` gate that's meant to make the `healparty`/`HealPlayerParty`
class of bug (an invented command shipped while the real special existed)
structurally impossible.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from rpg2gba.conversion_agent import fork_index as fi

_ORACLE_DIR = Path(__file__).resolve().parents[1] / "reference" / "archive" / "oracle_pory"


# ---------------------------------------------------------------------------
# Extraction golden counts (real repo)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def index() -> fi.ForkIndex:
    return fi.build()


def test_specials_unique_count(index: fi.ForkIndex) -> None:
    assert len(index.specials) == 620


def test_script_macros_count(index: fi.ForkIndex) -> None:
    assert len(index.script_macros) == 385


def test_movement_tokens_floor(index: fi.ForkIndex) -> None:
    # The vendored movement.inc declares 167 create_movement_action tokens
    # (BUILD_PLAN's "~172" estimate was approximate); assert a floor with
    # headroom rather than an exact count so small upstream additions don't
    # break this test.
    assert len(index.movement_tokens) >= 160


def test_constants_floor(index: fi.ForkIndex) -> None:
    assert len(index.constants) > 10_000


def test_gba_defines_resolve(index: fi.ForkIndex) -> None:
    # TRUE/FALSE live in include/gba/defines.h, outside include/constants/ —
    # scripts pass them as multichoice args, so the index must carry them.
    assert "TRUE" in index.constants
    assert "FALSE" in index.constants


def test_asm_constants_resolve(index: fi.ForkIndex) -> None:
    # `MSGBOX_SIGN = 3`-style assembler assignments in event.inc are
    # constants too, not C #defines — the extractor must catch them.
    assert "MSGBOX_SIGN" in index.constants
    assert "MSGBOX_YESNO" in index.constants
    assert "MSGBOX_NPC" in index.constants


def test_registry_extra_symbols(tmp_path: Path) -> None:
    flag_state = tmp_path / "flag_state.json"
    flag_state.write_text(
        json.dumps(
            {
                "switches": {"2": "FLAG_RECEIVED_STARTER"},
                "variables": {"1": "VAR_TEMP_POKEMON_CHOICE"},
                "self_switches": {"7:1:A": "FLAG_MAP007_EVENT001_SSA"},
                "temp_switches": {"1:2:A": "FLAG_MAP001_EVENT002_TSA"},
                "script_switches": [1, 4, 8],
                "source": {"FLAG_RECEIVED_STARTER": "proposed"},
            }
        ),
        encoding="utf-8",
    )
    map_constants = tmp_path / "map_constants.json"
    map_constants.write_text(
        json.dumps(
            {
                "49": {
                    "uranium_id": 49,
                    "map_const": "MAP_MOKI_TOWN_PLAYERS_HOUSE_1F",
                    "alias_const": "MAP_URANIUM_49",
                    "layout_const": "LAYOUT_MOKI_TOWN_PLAYERS_HOUSE_1F",
                    "mapsec_const": "MAPSEC_MOKI_TOWN_PLAYERS_HOUSE_1F",
                    "dir_name": "MokiTownPlayersHouse1F",
                    "display_name": "Moki Town Player's House 1F",
                }
            }
        ),
        encoding="utf-8",
    )

    extras = fi.registry_extra_symbols(flag_state, map_constants)
    assert extras == {
        "FLAG_RECEIVED_STARTER",
        "VAR_TEMP_POKEMON_CHOICE",
        "FLAG_MAP007_EVENT001_SSA",
        "FLAG_MAP001_EVENT002_TSA",
        "MAP_MOKI_TOWN_PLAYERS_HOUSE_1F",
        "MAP_URANIUM_49",
        "LAYOUT_MOKI_TOWN_PLAYERS_HOUSE_1F",
        "MAPSEC_MOKI_TOWN_PLAYERS_HOUSE_1F",
    }

    # Each side is optional.
    assert fi.registry_extra_symbols() == set()
    assert "MAP_URANIUM_49" in fi.registry_extra_symbols(map_constants_path=map_constants)


def test_cache_invalidated_on_format_bump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "fork_index.json"
    fi.load_or_build(cache_path=cache_path)

    calls = {"n": 0}
    real_build = fi.build

    def counting_build(repo_root: Path = fi._REPO_ROOT) -> fi.ForkIndex:
        calls["n"] += 1
        return real_build(repo_root)

    monkeypatch.setattr(fi, "build", counting_build)
    monkeypatch.setattr(fi, "_INDEX_FORMAT", fi._INDEX_FORMAT + 1)
    fi.load_or_build(cache_path=cache_path)
    assert calls["n"] == 1  # hash matched but format didn't — rebuilt


def test_known_symbols_resolve(index: fi.ForkIndex) -> None:
    assert "HealPlayerParty" in index.specials
    assert "MOVEMENT_ACTION_FACE_DOWN" in index.constants
    assert "FLAG_BADGE01_GET" in index.constants
    assert "MB_TALL_GRASS" in index.constants
    assert "walk_left" in index.movement_tokens
    assert "msgbox" in fi.PORYSCRIPT_BUILTINS
    assert "setflag" in fi.PORYSCRIPT_BUILTINS


# ---------------------------------------------------------------------------
# Cache round-trip
# ---------------------------------------------------------------------------


def test_cache_round_trip(tmp_path: Path, index: fi.ForkIndex) -> None:
    cache_path = tmp_path / "fork_index.json"
    cache_path.write_text(json.dumps(index.to_json(), indent=2), encoding="utf-8")

    loaded = fi.ForkIndex.from_json(json.loads(cache_path.read_text(encoding="utf-8")))

    assert loaded.specials == index.specials
    assert loaded.script_macros == index.script_macros
    assert loaded.movement_tokens == index.movement_tokens
    assert loaded.constants == index.constants
    assert loaded.tree_hash == index.tree_hash


def test_load_or_build_uses_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_path = tmp_path / "fork_index.json"
    calls = {"n": 0}
    real_build = fi.build

    def counting_build(repo_root: Path = fi._REPO_ROOT) -> fi.ForkIndex:
        calls["n"] += 1
        return real_build(repo_root)

    monkeypatch.setattr(fi, "build", counting_build)

    first = fi.load_or_build(cache_path=cache_path)
    assert calls["n"] == 1
    assert cache_path.is_file()

    second = fi.load_or_build(cache_path=cache_path)
    assert calls["n"] == 1  # cache hit, no rebuild
    assert second.specials == first.specials


def test_load_or_build_rebuilds_on_stale_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "fork_index.json"
    calls = {"n": 0}
    real_build = fi.build

    def counting_build(repo_root: Path = fi._REPO_ROOT) -> fi.ForkIndex:
        calls["n"] += 1
        return real_build(repo_root)

    monkeypatch.setattr(fi, "build", counting_build)
    fi.load_or_build(cache_path=cache_path)
    assert calls["n"] == 1

    # Simulate a stale cache: monkeypatch the hash fn to return something new.
    monkeypatch.setattr(fi, "tree_hash", lambda repo_root=fi._REPO_ROOT: "deadbeef")
    fi.load_or_build(cache_path=cache_path)
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# verify_script positives
# ---------------------------------------------------------------------------


def test_verify_script_clean_snippet(index: fi.ForkIndex) -> None:
    text = """
script Foo {
    lock
    setflag(FLAG_BADGE01_GET)
    special(HealPlayerParty)
    movement Foo_Movement {
        walk_left * 2
        face_up
    }
    applymovement(1, Foo_Movement)
    waitmovement(0)
    release
    end
}
"""
    assert fi.verify_script(text, index) == []


# ---------------------------------------------------------------------------
# verify_script negatives
# ---------------------------------------------------------------------------


def test_verify_script_invented_command(index: fi.ForkIndex) -> None:
    text = "script Foo {\n    healparty(1)\n    end\n}\n"
    violations = fi.verify_script(text, index)
    assert any(v.kind == "command" and v.symbol == "healparty" for v in violations)


def test_verify_script_invented_special(index: fi.ForkIndex) -> None:
    text = "script Foo {\n    special(HealParty)\n    end\n}\n"
    violations = fi.verify_script(text, index)
    assert any(v.kind == "special" and v.symbol == "HealParty" for v in violations)


def test_verify_script_invented_constant(index: fi.ForkIndex) -> None:
    text = "script Foo {\n    setflag(FLAG_TOTALLY_FAKE)\n    end\n}\n"
    violations = fi.verify_script(text, index)
    assert any(v.kind == "constant" and v.symbol == "FLAG_TOTALLY_FAKE" for v in violations)


def test_verify_script_bare_invented_command(index: fi.ForkIndex) -> None:
    # The exact historical bug: bare (no-paren) `healparty` as a statement
    # inside a script block. Rule 5 must report exactly one command violation.
    text = "script Foo {\n    lock\n    healparty\n    release\n    end\n}\n"
    violations = fi.verify_script(text, index)
    assert violations == [fi.Violation("healparty", "command", 3, "    healparty")]


def test_verify_script_bare_builtins_pass(index: fi.ForkIndex) -> None:
    text = (
        "script Foo {\n"
        "    lock\n"
        "    faceplayer\n"
        "    release\n"
        "    end\n"
        "}\n"
    )
    assert fi.verify_script(text, index) == []


def test_verify_script_fake_movement_token(index: fi.ForkIndex) -> None:
    text = (
        "script Foo {\n"
        "    movement Foo_Movement {\n"
        "        not_a_real_token\n"
        "    }\n"
        "    end\n"
        "}\n"
    )
    violations = fi.verify_script(text, index)
    assert any(v.kind == "movement" and v.symbol == "not_a_real_token" for v in violations)


# ---------------------------------------------------------------------------
# extras
# ---------------------------------------------------------------------------


def test_verify_script_registry_flag_needs_extras(index: fi.ForkIndex) -> None:
    text = "setflag(FLAG_MAP049_EVENT002_SSA)\n"

    # Default extra_patterns include the synthesized per-map-event flag shape.
    assert fi.verify_script(text, index) == []

    # Without any extras, it's a violation (registry state must be supplied).
    violations = fi.verify_script(text, index, extra_patterns=[])
    assert any(v.symbol == "FLAG_MAP049_EVENT002_SSA" for v in violations)


# ---------------------------------------------------------------------------
# string/comment immunity
# ---------------------------------------------------------------------------


def test_verify_script_ignores_strings_and_comments(index: fi.ForkIndex) -> None:
    text = (
        'msgbox("FAKE_CONSTANT is mentioned in a string") # FAKE_CONSTANT2 in a comment\n'
        "// FAKE_CONSTANT3 also in a comment\n"
    )
    assert fi.verify_script(text, index) == []


def test_verify_script_placeholder_in_string_is_fine(index: fi.ForkIndex) -> None:
    text = 'msgbox("{PLAYER}, sweetie!")\n'
    assert fi.verify_script(text, index) == []


# ---------------------------------------------------------------------------
# real-corpus smoke test
# ---------------------------------------------------------------------------


def test_verify_script_oracle_corpus_smoke(index: fi.ForkIndex) -> None:
    """Run the gate over a real oracle .pory file.

    We lack live flag-registry state here, so FLAG_/VAR_ names are broadly
    whitelisted per the task brief. Map049.pory also references pipeline-
    synthesized map-id constants (MAP_URANIUM_*) — those come from a
    working-tree-generated header (CLAUDE.md: the working tree under
    engine/ contains pipeline-generated headers with Uranium symbols; the
    index is built from git HEAD only, so they're never in the fork index by
    design). They're synthesized the same way FLAG_MAP*_EVENT*_* names are,
    so they get the same treatment: whitelisted here as a stand-in for
    registry/map-table state a real caller would supply.

    The archive preserves a real historical bug on purpose: Map049.pory uses
    the bare (no-parens) invented command `healparty` as a standalone
    statement at lines 46, 87, and 338 — the exact bug class this module
    exists to stop (the fork's real symbol is the special HealPlayerParty).
    The gate catching those three, and nothing else, IS the test: rule 5
    (bare-statement command resolution inside script blocks) must flag all
    three, and no other rule may produce false positives on the rest of the
    file.
    """
    path = _ORACLE_DIR / "Map049.pory"
    text = path.read_text(encoding="utf-8")

    extras = [re.compile(r"^(FLAG|VAR|MAP)_\w+$")]
    violations = fi.verify_script(text, index, extra_patterns=extras)

    expected = [
        ("command", "healparty", 46),
        ("command", "healparty", 87),
        ("command", "healparty", 338),
    ]
    found = sorted((v.kind, v.symbol, v.line_no) for v in violations)
    assert found == expected, (
        f"gate output on {path} diverged from the known archived healparty bug: "
        + ", ".join(f"{v.kind}:{v.symbol}@{v.line_no}" for v in violations)
    )
