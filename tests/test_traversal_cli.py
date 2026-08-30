"""CLI smoke tests for `python -m rpg2gba.traversal` (slice 1's "Library + CLI
dump" deliverable). Skips if the decoded corpus isn't present.
"""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from rpg2gba.traversal.__main__ import cli
from rpg2gba.traversal.collision import DEFAULT_MAPS_DIR, DEFAULT_TILESETS_JSON

pytestmark = pytest.mark.skipif(
    not (DEFAULT_MAPS_DIR / "Map037.json").is_file() or not DEFAULT_TILESETS_JSON.is_file(),
    reason="requires the decoded corpus under output/uranium-build/ (run the pipeline first)",
)


def test_dump_ascii_smoke():
    result = CliRunner().invoke(cli, ["dump", "--map", "37"])
    assert result.exit_code == 0, result.output
    assert "map 37" in result.output
    assert "elevation modelled: False" in result.output


def test_dump_json_round_trips_stair_cells():
    result = CliRunner().invoke(cli, ["dump", "--map", "37", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["map_id"] == 37
    assert payload["stairs"]["11,9"] == "left"
    assert payload["stairs"]["20,10"] == "right"
    assert payload["elevation_modelled"] is False


def test_path_command_reports_step_count():
    result = CliRunner().invoke(cli, ["path", "--map", "37", "--from", "16,26", "--to", "23,10"])
    assert result.exit_code == 0, result.output
    assert "23 step" in result.output


def test_path_command_reports_unreachable_as_nonzero_exit():
    # (0,0) is void/blocked on Map037 — unreachable from the entry.
    result = CliRunner().invoke(cli, ["path", "--map", "37", "--from", "16,26", "--to", "0,0"])
    assert result.exit_code != 0
    assert "UNREACHABLE" in result.output or "Error" in result.output


def test_reachable_command_reports_count():
    result = CliRunner().invoke(cli, ["reachable", "--map", "37", "--from", "16,26"])
    assert result.exit_code == 0, result.output
    assert "reachable cell(s) from" in result.output


def test_triggers_command_json_reports_trigger_tiles():
    result = CliRunner().invoke(cli, ["triggers", "--map", "35", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["map_id"] == 35
    assert payload["tiles"], "map 35 should have at least one trigger tile"


def test_capabilities_command_json_reports_rock_smash_obstacles():
    result = CliRunner().invoke(cli, ["capabilities", "--map", "35", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["map_id"] == 35
    assert payload["obstacles"]["20,28"]["capability"] == "rock_smash"


def test_blocked_command_reports_capability_gated_target():
    result = CliRunner().invoke(
        cli, ["blocked", "--map", "35", "--from", "21,56", "--to", "16,0"],
    )
    assert result.exit_code == 0, result.output
    assert "blocked:rock_smash" in result.output


def test_blocked_command_event_target():
    result = CliRunner().invoke(
        cli, ["blocked", "--map", "35", "--from", "21,56", "--event", "14"],
    )
    assert result.exit_code == 0, result.output
    assert "reachable" in result.output


def test_blocked_command_requires_at_least_one_target():
    result = CliRunner().invoke(cli, ["blocked", "--map", "35", "--from", "21,56"])
    assert result.exit_code != 0
