"""Tests for `src/rpg2gba/playtest/text_source.py` -- resolving what
dialogue text an event page should display in the ROM, according to
Uranium's own source (not our own converter's emitted Poryscript).

Unit tests build synthetic `Map###.json` fixtures by hand (a `build_dir`
containing exactly one `maps/Map###.json` per test), matching this module's
own reading discipline (`page.get("list")`, codes 101/401). No mgba
dependency -- `text_source.py` never imports `playtest.emulator`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.playtest import text_source as ts

ENGINE = Path(__file__).resolve().parents[1] / "engine"


def _write_map(build_dir: Path, map_id: int, events: list[dict]) -> None:
    maps_dir = build_dir / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    (maps_dir / f"Map{map_id:03d}.json").write_text(
        json.dumps({"events": events}), encoding="utf-8"
    )


def _show_text(text: str) -> dict:
    return {"code": 101, "parameters": [text], "indent": 0}


def _show_text_cont(text: str) -> dict:
    return {"code": 401, "parameters": [text], "indent": 0}


def _other(code: int = 999) -> dict:
    return {"code": code, "parameters": [], "indent": 0}


def _event(event_id: int, pages: list[list[dict]]) -> dict:
    return {
        "id": event_id,
        "name": f"EV{event_id}",
        "x": 0,
        "y": 0,
        "pages": [{"list": commands} for commands in pages],
    }


@pytest.fixture(autouse=True)
def _clear_caches():
    ts._MAP_CACHE.clear()
    ts._charmap_cache.clear()
    yield
    ts._MAP_CACHE.clear()
    ts._charmap_cache.clear()


# -- shape: 101 alone, 101+401, two message boxes, no text -------------------


def test_single_101(tmp_path: Path) -> None:
    _write_map(tmp_path, 1, [_event(1, [[_show_text("Hello there.")]])])
    msgs = ts.page_messages(1, 1, 0, build_dir=tmp_path)
    assert len(msgs) == 1
    assert msgs[0].text == "Hello there."
    assert msgs[0].raw == "Hello there."
    assert msgs[0].map_id == 1
    assert msgs[0].event_id == 1
    assert msgs[0].page_idx == 0
    assert msgs[0].index == 0


def test_101_plus_401_continuations(tmp_path: Path) -> None:
    _write_map(
        tmp_path,
        1,
        [_event(1, [[
            _show_text("Two strong-"),
            _show_text_cont("looking trainers"),
            _show_text_cont("are approaching."),
        ]])],
    )
    msgs = ts.page_messages(1, 1, 0, build_dir=tmp_path)
    assert len(msgs) == 1
    # join_text_lines glues the hyphen without a space, but inserts one at
    # the ordinary word boundary.
    assert msgs[0].text == "Two strong-looking trainers are approaching."
    # raw preserves the original per-fragment line boundaries verbatim.
    assert msgs[0].raw == "Two strong-\nlooking trainers\nare approaching."


def test_two_message_boxes_one_page(tmp_path: Path) -> None:
    _write_map(
        tmp_path,
        1,
        [_event(1, [[
            _show_text("First box."),
            _other(),
            _show_text("Second box."),
            _show_text_cont("Continued."),
        ]])],
    )
    msgs = ts.page_messages(1, 1, 0, build_dir=tmp_path)
    assert len(msgs) == 2
    assert msgs[0].index == 0
    assert msgs[0].text == "First box."
    assert msgs[1].index == 1
    assert msgs[1].text == "Second box. Continued."


def test_page_with_no_text(tmp_path: Path) -> None:
    _write_map(tmp_path, 1, [_event(1, [[_other(), _other(code=201)]])])
    msgs = ts.page_messages(1, 1, 0, build_dir=tmp_path)
    assert msgs == ()


def test_expected_text_fails_loud_on_missing_index(tmp_path: Path) -> None:
    _write_map(tmp_path, 1, [_event(1, [[_show_text("Only one.")]])])
    with pytest.raises(ValueError, match="no message at index 1"):
        ts.expected_text(1, 1, 0, index=1, build_dir=tmp_path)


def test_expected_text_fails_loud_on_no_text_at_all(tmp_path: Path) -> None:
    _write_map(tmp_path, 1, [_event(1, [[_other()]])])
    with pytest.raises(ValueError, match="no message at index 0"):
        ts.expected_text(1, 1, 0, build_dir=tmp_path)


def test_unknown_event_id_fails_loud(tmp_path: Path) -> None:
    _write_map(tmp_path, 1, [_event(1, [[_show_text("hi")]])])
    with pytest.raises(ValueError, match="no event id 99"):
        ts.page_messages(1, 99, 0, build_dir=tmp_path)


def test_unknown_page_idx_fails_loud(tmp_path: Path) -> None:
    _write_map(tmp_path, 1, [_event(1, [[_show_text("hi")]])])
    with pytest.raises(ValueError, match="no page index 5"):
        ts.page_messages(1, 1, 5, build_dir=tmp_path)


def test_missing_map_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ts.page_messages(1, 1, 0, build_dir=tmp_path)


# -- normalization: apostrophe / U+2019 --------------------------------------


def test_ascii_apostrophe_normalizes_to_curly_quote(tmp_path: Path) -> None:
    """The real, load-bearing case (CLAUDE.md's brief): `engine/charmap.txt`
    defines byte 0xB4 for BOTH the ASCII apostrophe and U+2019, with the
    curly-quote entry listed first -- so a ROM text-decode of that byte
    canonically comes back as U+2019, not plain `'`. Uranium's own source
    data (as decoded today) writes plain ASCII apostrophes throughout; this
    is the normalization that makes source text ROM-comparable."""
    _write_map(
        tmp_path, 1, [_event(1, [[_show_text("I can't tell.")]])]
    )
    text = ts.expected_text(1, 1, 0, build_dir=tmp_path)
    assert text == "I can’t tell."
    assert "’" in text
    assert "'" not in text


def test_curly_quote_in_source_stays_curly(tmp_path: Path) -> None:
    _write_map(
        tmp_path, 1, [_event(1, [[_show_text("I can’t tell.")]])]
    )
    text = ts.expected_text(1, 1, 0, build_dir=tmp_path)
    assert text == "I can’t tell."


# -- normalization: straight double quote / asterisk (PROJECT_TODO #109) ----


def test_straight_double_quote_becomes_typographic_pair(tmp_path: Path) -> None:
    _write_map(
        tmp_path, 1, [_event(1, [[_show_text('He said "hello" to me.')]])]
    )
    text = ts.expected_text(1, 1, 0, build_dir=tmp_path)
    assert text == "He said “hello” to me."


def test_two_quoted_phrases_alternate_open_close(tmp_path: Path) -> None:
    _write_map(
        tmp_path,
        1,
        [_event(1, [[_show_text('"First one" and "second one".')]])],
    )
    text = ts.expected_text(1, 1, 0, build_dir=tmp_path)
    assert text == "“First one” and “second one”."


def test_asterisk_becomes_tilde(tmp_path: Path) -> None:
    _write_map(tmp_path, 1, [_event(1, [[_show_text("...*sniffle*...")]])])
    text = ts.expected_text(1, 1, 0, build_dir=tmp_path)
    assert text == "...~sniffle~..."


def test_quote_toggle_resets_per_message(tmp_path: Path) -> None:
    """Two separate message boxes each open with a straight quote -- the
    toggle must reset per message, not carry over from the previous box
    (each 101/401* run is a distinct `.pory` string literal at staging)."""
    _write_map(
        tmp_path,
        1,
        [_event(1, [[
            _show_text('"First box."'),
            _other(),
            _show_text('"Second box."'),
        ]])],
    )
    msgs = ts.page_messages(1, 1, 0, build_dir=tmp_path)
    assert len(msgs) == 2
    assert msgs[0].text == "“First box.”"
    assert msgs[1].text == "“Second box.”"


# -- control codes ------------------------------------------------------------


def test_player_name_placeholder(tmp_path: Path) -> None:
    _write_map(tmp_path, 1, [_event(1, [[_show_text("Hi, \\PN!")]])])
    text = ts.expected_text(1, 1, 0, build_dir=tmp_path)
    assert text == "Hi, {PLAYER}!"


def test_pause_code_becomes_zero_width(tmp_path: Path) -> None:
    _write_map(tmp_path, 1, [_event(1, [[_show_text("Wait\\wt[8] for it.")]])])
    text = ts.expected_text(1, 1, 0, build_dir=tmp_path)
    assert text == "Wait for it."
    assert "PAUSE" not in text
    assert "{" not in text


def test_color_code_dropped(tmp_path: Path) -> None:
    _write_map(tmp_path, 1, [_event(1, [[_show_text("\\c[1]Red text\\c[0]")]])])
    text = ts.expected_text(1, 1, 0, build_dir=tmp_path)
    assert text == "Red text"


def test_line_break_escapes_pass_through(tmp_path: Path) -> None:
    _write_map(tmp_path, 1, [_event(1, [[_show_text("Line one\\nLine two")]])])
    text = ts.expected_text(1, 1, 0, build_dir=tmp_path)
    assert text == "Line one\\nLine two"


def test_unrecognized_control_code_fails_loud(tmp_path: Path) -> None:
    _write_map(tmp_path, 1, [_event(1, [[_show_text("Your \\v[6] is doing fine.")]])])
    with pytest.raises(ValueError, match="does not recognize"):
        ts.page_messages(1, 1, 0, build_dir=tmp_path)


def test_unrepresentable_character_fails_loud(tmp_path: Path) -> None:
    _write_map(tmp_path, 1, [_event(1, [[_show_text("emoji \U0001F600 test")]])])
    with pytest.raises(ValueError, match="charmap.txt"):
        ts.page_messages(1, 1, 0, build_dir=tmp_path)


# -- module-level map JSON cache: idempotent, keyed on inputs ----------------


def test_map_cache_is_reused_across_calls(tmp_path: Path) -> None:
    _write_map(tmp_path, 1, [_event(1, [[_show_text("Cached.")]])])
    ts.page_messages(1, 1, 0, build_dir=tmp_path)
    assert len(ts._MAP_CACHE) == 1
    # Mutate the file on disk; the cached parse should NOT change (same
    # build_dir/map_id inputs -> same cached answer, per CLAUDE.md sec 4.2).
    (tmp_path / "maps" / "Map001.json").write_text(
        json.dumps({"events": [_event(1, [[_show_text("Different.")]])]}),
        encoding="utf-8",
    )
    text = ts.expected_text(1, 1, 0, build_dir=tmp_path)
    assert text == "Cached."


# -- real corpus (only if this build's decoded maps are present) ------------

_REAL_BUILD_DIR = Path(__file__).resolve().parents[1] / "output" / "uranium-build"
_HAS_REAL_MAP035 = (_REAL_BUILD_DIR / "maps" / "Map035.json").exists()


@pytest.mark.skipif(not _HAS_REAL_MAP035, reason="no decoded output/uranium-build corpus present")
def test_real_map035_event12_page0_pins_expected_text() -> None:
    """Map035 (Route 2, CH04) event 12 page 0 -- a trainer's pre-battle
    line, pinned against this build's real decoded map JSON. If this ever
    fails, either Uranium's source text or this build's decoded output
    changed -- both are real findings, not a flaky test."""
    text = ts.expected_text(35, 12, 0, build_dir=_REAL_BUILD_DIR)
    assert text == "I heard Owten nest in this area.\\nI’m trying to catch one!"
