"""Tests for the playtest harness's dialogue-text-content primitive
(`src/rpg2gba/playtest/emulator.py`'s `decode_text_bytes` /
`_invert_charmap_english_first`).

`decode_text_bytes` is a pure function -- bytes in, decoded string out, no
mgba/ROM/memory access -- specifically so it can be unit-tested hard without
booting a ROM (PLAYTEST_AUTHORING_IMPROVEMENT.md §4.1's build-order note).
It lives in `emulator.py`, though, and that module raises
`ModuleNotFoundError` unconditionally at import time when the mgba python
bindings aren't installed (see its module docstring) -- so, same convention
`tests/test_playtest.py` already uses for anything that touches that module
(`needs_mgba`, imports inside each test body), every test here is gated the
same way even though the function under test needs no emulator at all.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[1] / "engine"

needs_mgba = pytest.mark.skipif(
    importlib.util.find_spec("mgba") is None,
    reason="needs the mgba python bindings to import emulator.py",
)

# A small synthetic charmap for tests about control-byte handling, which
# don't need real glyph assignments -- only that ASCII-ish printable bytes
# decode to themselves and everything else is exercised deliberately.
_SYNTH_CHARMAP: dict[int, str] = {
    0x00: " ",
    0x41: "A",
    0x42: "B",
    0x43: "C",
}


@needs_mgba
def test_plain_ascii_range_text() -> None:
    from rpg2gba.playtest.emulator import decode_text_bytes

    assert decode_text_bytes(b"\x41\x42\x43\xff", _SYNTH_CHARMAP) == "ABC"


@needs_mgba
def test_terminator_alone_is_empty_string() -> None:
    from rpg2gba.playtest.emulator import decode_text_bytes

    assert decode_text_bytes(b"\xff", _SYNTH_CHARMAP) == ""


@needs_mgba
def test_line_and_page_breaks_render_as_stable_tokens() -> None:
    from rpg2gba.playtest.emulator import decode_text_bytes

    # 0xFE CHAR_NEWLINE, 0xFB CHAR_PROMPT_CLEAR (page break),
    # 0xFA CHAR_PROMPT_SCROLL (line break) -- constants/characters.h.
    data = b"\x41\xfe\x42\xfb\x43\xfa\xff"
    assert decode_text_bytes(data, _SYNTH_CHARMAP) == "A\\nB\\pC\\l"


@needs_mgba
def test_multibyte_ext_control_code_is_consumed_zero_width() -> None:
    from rpg2gba.playtest.emulator import decode_text_bytes

    # 0xFC 0x01 0x05 is EXT_CTRL_CODE_BEGIN + COLOR opcode + a 1-byte colour
    # operand (text.c's RenderText, EXT_CTRL_CODE_COLOR) -- three bytes,
    # zero characters, matching GetStringWidth's zero-width treatment.
    data = b"\x41\xfc\x01\x05\x42\xff"
    assert decode_text_bytes(data, _SYNTH_CHARMAP) == "AB"


@needs_mgba
def test_unknown_ext_control_opcode_fails_loud() -> None:
    from rpg2gba.playtest.emulator import decode_text_bytes
    from rpg2gba.playtest.errors import ScenarioError

    # 0xEE is not a recognized EXT_CTRL_CODE_* opcode -- decoding must not
    # guess an operand length and silently desync the rest of the string.
    data = b"\x41\xfc\xee\xff"
    with pytest.raises(ScenarioError, match="unrecognized EXT_CTRL_CODE_BEGIN"):
        decode_text_bytes(data, _SYNTH_CHARMAP)


@needs_mgba
def test_placeholder_renders_as_named_token() -> None:
    from rpg2gba.playtest.emulator import decode_text_bytes

    # 0xFD 0x01 is PLACEHOLDER_BEGIN + PLACEHOLDER_ID_PLAYER.
    data = b"\x41\xfd\x01\x42\xff"
    assert decode_text_bytes(data, _SYNTH_CHARMAP) == "A{PLAYER}B"


@needs_mgba
def test_placeholder_with_unrecognized_id_renders_deterministically() -> None:
    from rpg2gba.playtest.emulator import decode_text_bytes

    # 0x7f is not one of _PLACEHOLDER_TOKENS' known ids -- still a stable,
    # comparable rendering, not a dropped byte.
    data = b"\xfd\x7f\xff"
    assert decode_text_bytes(data, _SYNTH_CHARMAP) == "{PLACEHOLDER_0x7f}"


@needs_mgba
def test_unterminated_buffer_hits_cap_and_raises() -> None:
    from rpg2gba.playtest.emulator import decode_text_bytes
    from rpg2gba.playtest.errors import ScenarioError

    # No 0xFF anywhere in this buffer -- decode must not run off the end
    # silently; it has to report "no terminator found" within what it was
    # given, standing in for the bounded-read cap
    # (Emulator.current_field_message_text fetches at most TEXT_DECODE_CAP
    # bytes and hands the fixed-size slice here).
    data = b"\x41" * 10
    with pytest.raises(ScenarioError, match="no EOS"):
        decode_text_bytes(data, _SYNTH_CHARMAP)


@needs_mgba
def test_unmapped_byte_fails_loud_not_silently_dropped() -> None:
    from rpg2gba.playtest.emulator import decode_text_bytes
    from rpg2gba.playtest.errors import ScenarioError

    # 0x99 has no entry in the synthetic charmap.
    data = b"\x41\x99\xff"
    with pytest.raises(ScenarioError, match="no charmap entry"):
        decode_text_bytes(data, _SYNTH_CHARMAP)


# -- against the real engine charmap -----------------------------------

@pytest.fixture(scope="module")
def real_byte_to_char() -> dict[int, str]:
    if not (ENGINE / "charmap.txt").is_file():
        pytest.skip("engine/charmap.txt not present")
    from rpg2gba.playtest.emulator import _invert_charmap_english_first
    from rpg2gba.text_validator.engine_metrics import load_charmap

    return _invert_charmap_english_first(
        load_charmap(ENGINE / "charmap.txt").char_to_byte
    )


@needs_mgba
def test_decodes_real_charmap_ascii_word(real_byte_to_char: dict[int, str]) -> None:
    from rpg2gba.playtest.emulator import decode_text_bytes

    # 'H'=C2 'E'=BF 'L'=C6 'L'=C6 'O'=C9 '!'=AB, engine/charmap.txt.
    data = bytes([0xC2, 0xBF, 0xC6, 0xC6, 0xC9, 0xAB, 0xFF])
    assert decode_text_bytes(data, real_byte_to_char) == "HELLO!"


@needs_mgba
def test_charmap_inversion_prefers_latin_over_japanese_for_shared_byte(
    real_byte_to_char: dict[int, str],
) -> None:
    # engine/charmap.txt reuses byte 0x01 for both 'À' (Latin section) and
    # 'あ' (a later "@ Hiragana" section) -- a blind dict-reverse would keep
    # whichever was inserted last (Japanese). This build prints English, so
    # the inversion must resolve to the Latin glyph.
    assert real_byte_to_char[0x01] == "À"
