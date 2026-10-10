"""Tests for `scripts/assemble_pathfinder.py`'s `ingame_trade_gate_symbols`.

The staging-time fork-index gate reads committed `engine/` only, so the
`INGAME_TRADE_*` members the S8b5b pass writes into a gitignored `.gen.h` must
reach it through the pass's manifest. Without this, every transpiled
`setvar(VAR_0x8005, INGAME_TRADE_...)` aborted assembly as an unresolved symbol.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import assemble_pathfinder as ap  # noqa: E402


def _write_manifest(out: Path, consts: list[str]) -> None:
    dest = out / "ingame_trades"
    dest.mkdir(parents=True)
    trades = [{"const": c, "map_id": 46, "event_id": 14, "page": 1} for c in consts]
    (dest / "ingame_trade_manifest.json").write_text(
        json.dumps({"version": 1, "generator": "rpg2gba.ingame_trades", "trades": trades}),
        encoding="utf-8",
    )


def test_manifest_consts_become_gate_symbols(tmp_path: Path) -> None:
    _write_manifest(tmp_path, ["INGAME_TRADE_MAP046_EV014", "INGAME_TRADE_MAP046_EV002"])
    assert ap.ingame_trade_gate_symbols(tmp_path) == {
        "INGAME_TRADE_MAP046_EV014",
        "INGAME_TRADE_MAP046_EV002",
    }


def test_zero_trades_yields_empty_set(tmp_path: Path) -> None:
    _write_manifest(tmp_path, [])
    assert ap.ingame_trade_gate_symbols(tmp_path) == set()


def test_missing_manifest_yields_empty_set(tmp_path: Path) -> None:
    assert ap.ingame_trade_gate_symbols(tmp_path) == set()
