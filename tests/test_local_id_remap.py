"""Unit tests for local_id_remap.py — staging-time RMXP-event-id -> compiled
object-local-id rewriting of already-transpiled .pory text."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from rpg2gba.tileset_converter.local_id_remap import (
    REMAP_COMMANDS,
    load_local_id_table,
    remap_pory_object_ids,
)

# ---------------------------------------------------------------------------
# load_local_id_table
# ---------------------------------------------------------------------------


def test_load_local_id_table_happy_path(tmp_path: Path) -> None:
    path = tmp_path / "Map049.json"
    path.write_text(json.dumps({"9": 1, "16": 2, "20": 3}), encoding="utf-8")

    table = load_local_id_table(path)

    assert table == {"9": 1, "16": 2, "20": 3}


def test_load_local_id_table_rejects_non_decimal_key(tmp_path: Path) -> None:
    path = tmp_path / "Map049.json"
    path.write_text(json.dumps({"nine": 1}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_local_id_table(path)


def test_load_local_id_table_rejects_non_int_value(tmp_path: Path) -> None:
    path = tmp_path / "Map049.json"
    path.write_text(json.dumps({"9": "one"}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_local_id_table(path)


def test_load_local_id_table_rejects_non_positive_value(tmp_path: Path) -> None:
    path = tmp_path / "Map049.json"
    path.write_text(json.dumps({"9": 0}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_local_id_table(path)


def test_load_local_id_table_rejects_bool_value(tmp_path: Path) -> None:
    """bool is a subclass of int in Python; must not slip past the int check."""
    path = tmp_path / "Map049.json"
    path.write_text(json.dumps({"9": True}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_local_id_table(path)


def test_load_local_id_table_rejects_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "Map049.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(ValueError):
        load_local_id_table(path)


# ---------------------------------------------------------------------------
# remap_pory_object_ids — one command per REMAP_COMMANDS entry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("command", REMAP_COMMANDS)
def test_each_remap_command_rewrites_first_arg(command: str) -> None:
    table = {"9": 1}
    text = f"{command}(9, 4, 5)\n"

    result = remap_pory_object_ids(text, table)

    assert result.text == f"{command}(1, 4, 5)\n"
    assert result.replacements == [(1, command, 9, 1)]
    assert result.warnings == []


def test_single_arg_form_rewrites() -> None:
    table = {"16": 2}
    text = "removeobject(16)\n"

    result = remap_pory_object_ids(text, table)

    assert result.text == "removeobject(2)\n"
    assert result.replacements == [(1, "removeobject", 16, 2)]


def test_whitespace_around_paren_and_comma_tolerated() -> None:
    table = {"16": 2}
    text = "applymovement ( 16 , Common_Movement_ExclamationMark)\n"

    result = remap_pory_object_ids(text, table)

    assert result.text == "applymovement ( 2 , Common_Movement_ExclamationMark)\n"
    assert result.replacements == [(1, "applymovement", 16, 2)]


# ---------------------------------------------------------------------------
# identifier first-args are left untouched, no warning
# ---------------------------------------------------------------------------


def test_obj_event_id_player_untouched_no_warning(caplog: pytest.LogCaptureFixture) -> None:
    table: dict[str, int] = {}
    text = "applymovement(OBJ_EVENT_ID_PLAYER, Map049_Move1)\n"

    with caplog.at_level(logging.WARNING):
        result = remap_pory_object_ids(text, table)

    assert result.text == text
    assert result.replacements == []
    assert result.warnings == []
    assert caplog.records == []


@pytest.mark.parametrize(
    "identifier", ["LOCALID_NPC_1", "VAR_TEMP_0", "LOCALID_PLAYER"]
)
def test_other_identifier_first_args_untouched(identifier: str) -> None:
    table: dict[str, int] = {}
    text = f"setobjectxy({identifier}, 18, 9)\n"

    result = remap_pory_object_ids(text, table)

    assert result.text == text
    assert result.replacements == []
    assert result.warnings == []


# ---------------------------------------------------------------------------
# string / comment masking
# ---------------------------------------------------------------------------


def test_integer_inside_msgbox_string_untouched() -> None:
    table = {"16": 2}
    text = 'msgbox("Say applymovement(16, foo) to me")\n'

    result = remap_pory_object_ids(text, table)

    assert result.text == text
    assert result.replacements == []
    assert result.warnings == []


def test_integer_inside_string_with_escaped_quote_untouched() -> None:
    table = {"16": 2}
    text = 'msgbox("She said \\"applymovement(16)\\" to me")\n'

    result = remap_pory_object_ids(text, table)

    assert result.text == text
    assert result.replacements == []


def test_real_msgbox_and_command_on_same_line_only_command_rewritten() -> None:
    """A string containing fake command text on the same line as a real command
    call must not confuse the scanner into over- or under-matching."""
    table = {"16": 2}
    text = 'msgbox("applymovement(16) is not real") applymovement(16, Move1)\n'

    result = remap_pory_object_ids(text, table)

    assert result.text == 'msgbox("applymovement(16) is not real") applymovement(2, Move1)\n'
    assert result.replacements == [(1, "applymovement", 16, 2)]


def test_full_line_comment_untouched() -> None:
    table = {"16": 2}
    text = "# audio (code 250): applymovement(16, foo)\napplymovement(16, Move1)\n"

    result = remap_pory_object_ids(text, table)

    assert result.text == "# audio (code 250): applymovement(16, foo)\napplymovement(2, Move1)\n"
    assert result.replacements == [(2, "applymovement", 16, 2)]


def test_trailing_comment_untouched() -> None:
    table = {"16": 2}
    text = "applymovement(16, Move1) # was applymovement(16, foo)\n"

    result = remap_pory_object_ids(text, table)

    assert result.text == "applymovement(2, Move1) # was applymovement(16, foo)\n"
    assert result.replacements == [(1, "applymovement", 16, 2)]


# ---------------------------------------------------------------------------
# unmapped ids
# ---------------------------------------------------------------------------


def test_unmapped_id_unchanged_and_warned(caplog: pytest.LogCaptureFixture) -> None:
    table: dict[str, int] = {}
    text = "applymovement(99, Move1)\n"

    with caplog.at_level(logging.WARNING):
        result = remap_pory_object_ids(text, table, source_name="Map099.pory")

    assert result.text == text
    assert result.replacements == []
    assert result.warnings == [(1, "applymovement", 99)]

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "Map099.pory" in message
    assert "applymovement" in message
    assert "99" in message


# ---------------------------------------------------------------------------
# shifting-table one-pass correctness
# ---------------------------------------------------------------------------


def test_shifting_table_one_pass_correctness() -> None:
    """{"4": 2, "9": 4}: old id 4 must become 2, and old id 9 must become 4 —
    the newly-produced 4 must NOT be re-rewritten to 2 by a later pass over
    the same table entry."""
    table = {"4": 2, "9": 4}
    text = "applymovement(4, Move1)\nsetobjectxy(9, 18, 9)\n"

    result = remap_pory_object_ids(text, table)

    assert result.text == "applymovement(2, Move1)\nsetobjectxy(4, 18, 9)\n"
    assert result.replacements == [
        (1, "applymovement", 4, 2),
        (2, "setobjectxy", 9, 4),
    ]
    assert result.warnings == []


def test_shifting_table_order_independent_of_dict_iteration() -> None:
    """Same as above but with the table entries in the opposite insertion
    order, to make sure iteration order of the dict can't matter."""
    table = {"9": 4, "4": 2}
    text = "setobjectxy(9, 18, 9)\napplymovement(4, Move1)\n"

    result = remap_pory_object_ids(text, table)

    assert result.text == "setobjectxy(4, 18, 9)\napplymovement(2, Move1)\n"


# ---------------------------------------------------------------------------
# realistic multi-line block
# ---------------------------------------------------------------------------


def test_realistic_multiline_block() -> None:
    """Mirrors real transpiler output (see Map049.pory EV018/EV021): several
    commands mixed with identifier-arg calls, comments, and movement blocks."""
    table = {"16": 2, "20": 3}
    text = (
        "lock\n"
        "applymovement(16, Common_Movement_ExclamationMark)\n"
        "waitmovement(0)\n"
        "setobjectxy(20, 18, 9)\n"
        "release\n"
    )

    result = remap_pory_object_ids(text, table, source_name="Map049.pory")

    expected_text = (
        "lock\n"
        "applymovement(2, Common_Movement_ExclamationMark)\n"
        "waitmovement(0)\n"
        "setobjectxy(3, 18, 9)\n"
        "release\n"
    )
    assert result.text == expected_text
    assert result.replacements == [
        (2, "applymovement", 16, 2),
        (4, "setobjectxy", 20, 3),
    ]
    assert result.warnings == []


# ---------------------------------------------------------------------------
# byte preservation
# ---------------------------------------------------------------------------


def test_byte_preservation_except_rewritten_integers() -> None:
    table = {"16": 2}
    text = (
        "script Map049_EV018_Page1 {   \n"
        "\n"
        "    applymovement(16, Move1)   \n"
        "\n"
        "    end\n"
        "}\n"
    )

    result = remap_pory_object_ids(text, table)

    expected = (
        "script Map049_EV018_Page1 {   \n"
        "\n"
        "    applymovement(2, Move1)   \n"
        "\n"
        "    end\n"
        "}\n"
    )
    assert result.text == expected
