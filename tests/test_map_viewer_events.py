"""Coverage for scripts/map_viewer_events.py — the EVENTS-mode data layer
(trainer/item/warp identity, event-kind classification, playtest beat
markers) that sits behind map_viewer_common.build_map_data's "events" key.

Exercises the real output/ corpus (Map033 has trainer events; Map068 —
Kevlar Town's Pokémon Center — has warps, an item ball, and declared Kevlar
playtest beats) rather than synthetic fixtures, since the whole point of
this module is joining several real generated artifacts together. Skips
cleanly when those artifacts aren't present (CI / a fresh checkout), mirroring
the existing `pytest.skip("... not generated yet")` idiom used elsewhere in
this test suite (see tests/test_trainer_battles.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import map_viewer_common as mvc  # noqa: E402
import map_viewer_events as mve  # noqa: E402

MAPS_DIR = mvc._maps_dir()
TRAINER_MAP_ID = 33  # has trainer/rematch events (see deterministic.py smoke checks)
KEVLAR_CENTER_MAP_ID = 68  # MAP_KEVLAR_TOWN_POKEMON_CENTER: warps + item ball


def _require_map(map_id: int) -> dict:
    path = MAPS_DIR / f"Map{map_id:03d}.json"
    if not path.is_file():
        pytest.skip(f"{path} not generated yet")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    """Module-level mtime-fingerprinted caches (mirrors the
    _png_paths_cache-clearing fixture in test_map_viewer_fingerprint.py) —
    clear around every test so no test can be served a stale value left by
    another."""
    for name in (
        "_ctx_cache", "_item_names_cache", "_trainer_join_cache",
        "_map_registry_cache", "_map_groups_cache", "_switch_names_cache",
        "_variable_names_cache",
    ):
        setattr(mve, name, None)
    yield
    for name in (
        "_ctx_cache", "_item_names_cache", "_trainer_join_cache",
        "_map_registry_cache", "_map_groups_cache", "_switch_names_cache",
        "_variable_names_cache",
    ):
        setattr(mve, name, None)


# ---------------------------------------------------------------------------
# enrich_events
# ---------------------------------------------------------------------------


def test_enrich_events_preserves_legacy_keys_and_resolves_trainer() -> None:
    doc = _require_map(TRAINER_MAP_ID)
    events = mve.enrich_events(TRAINER_MAP_ID, doc["events"])
    by_id = {e["id"]: e for e in events}

    assert 9 in by_id, "Map033 event 9 (Marko the Fisherman) missing from fixture map"
    evt = by_id[9]

    # The seven pre-existing keys stay byte-compatible for the graphics frontend.
    for key in ("id", "name", "x", "y", "npages", "is_warp", "character_name"):
        assert key in evt

    assert evt["kind"] == "trainer"
    assert evt["is_warp"] is False
    assert evt["trainer"] is not None
    assert evt["trainer"]["trainer_constant"] == "TRAINER_MARKO_19"
    assert evt["trainer"]["display_name"] == "Marko"
    assert evt["trainer"]["kind"] == "sight"
    assert evt["label"] == "Marko"


def test_enrich_events_warp_and_item_ball_on_kevlar_center() -> None:
    doc = _require_map(KEVLAR_CENTER_MAP_ID)
    events = mve.enrich_events(KEVLAR_CENTER_MAP_ID, doc["events"])
    by_id = {e["id"]: e for e in events}

    warps = [e for e in by_id.values() if e["is_warp"]]
    assert warps, "expected at least one warp event on the Kevlar Center map"
    for w in warps:
        assert w["kind"] == "warp"

    items = [e for e in by_id.values() if e["kind"] == "item"]
    assert items, "expected an item-ball event on the Kevlar Center map"


def test_enrich_events_empty_list_is_empty() -> None:
    assert mve.enrich_events(TRAINER_MAP_ID, []) == []


# ---------------------------------------------------------------------------
# event_detail
# ---------------------------------------------------------------------------


def test_event_detail_full_trainer_record() -> None:
    _require_map(TRAINER_MAP_ID)
    detail = mve.event_detail(TRAINER_MAP_ID, 9)

    assert detail["trainer"]["trainer_constant"] == "TRAINER_MARKO_19"
    assert detail["trainer"]["party"], "expected a resolved party from trainers.json"
    assert detail["pages"], "expected per-page detail"
    assert detail["pages"][0]["dialogue"], "expected joined dialogue text on page 1"
    assert detail["warp"] is None


def test_event_detail_bad_event_id_raises_keyerror() -> None:
    _require_map(TRAINER_MAP_ID)
    with pytest.raises(KeyError):
        mve.event_detail(TRAINER_MAP_ID, 999999)


def test_event_detail_warp_resolves_destination() -> None:
    doc = _require_map(KEVLAR_CENTER_MAP_ID)
    warp_id = next(
        e["id"] for e in mve.enrich_events(KEVLAR_CENTER_MAP_ID, doc["events"]) if e["is_warp"]
    )
    detail = mve.event_detail(KEVLAR_CENTER_MAP_ID, warp_id)
    assert detail["warp"] is not None
    assert "map_id" in detail["warp"] or "raw_parameters" in detail["warp"]


# ---------------------------------------------------------------------------
# beat_markers
# ---------------------------------------------------------------------------


def test_beat_markers_declared_for_kevlar_center(monkeypatch: pytest.MonkeyPatch) -> None:
    registry_state = mvc._output_base() / "uranium-build" / "porymap" / "map_constants.json"
    if not registry_state.is_file():
        pytest.skip(f"{registry_state} not generated yet")

    # Force the "no observed-beats directory" branch regardless of real repo
    # state, so this assertion is stable: point _output_base at a location
    # with the porymap registry present but no playtest/observed_beats dir.
    result = mve.beat_markers(KEVLAR_CENTER_MAP_ID)

    assert result["map_id"] == KEVLAR_CENTER_MAP_ID
    assert isinstance(result["declared"], list)
    assert isinstance(result["observed"], list)
    assert isinstance(result["notes"], list)
    kevlar_beats = [b for b in result["declared"] if b["chapter"] == "kevlar"]
    assert kevlar_beats, "expected at least one declared Kevlar beat on this map"
    for b in kevlar_beats:
        assert b["map_constant"] == "MAP_KEVLAR_TOWN_POKEMON_CENTER"


def test_beat_markers_missing_observed_dir_degrades_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_state = mvc._output_base() / "uranium-build" / "porymap" / "map_constants.json"
    if not registry_state.is_file():
        pytest.skip(f"{registry_state} not generated yet")

    # Point _output_base() at an empty tmp dir that mirrors the real porymap
    # registry state but has no playtest/observed_beats/ directory at all.
    fake_output = tmp_path / "output"
    porymap_dir = fake_output / "uranium-build" / "porymap"
    porymap_dir.mkdir(parents=True)
    (porymap_dir / "map_constants.json").write_text(
        registry_state.read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setattr(mvc, "_output_base", lambda: fake_output)

    result = mve.beat_markers(KEVLAR_CENTER_MAP_ID)

    assert result["observed"] == []
    assert any("observed-beats directory" in n for n in result["notes"])
    # No exception, and declared beats still resolve since the registry copy is intact.
    assert isinstance(result["declared"], list)


def test_beat_markers_missing_registry_state_degrades_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mvc, "_output_base", lambda: tmp_path / "nonexistent_output")

    result = mve.beat_markers(KEVLAR_CENTER_MAP_ID)

    assert result["declared"] == []
    assert isinstance(result["notes"], list) and result["notes"]
