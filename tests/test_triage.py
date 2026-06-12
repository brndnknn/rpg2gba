"""Tests for src/rpg2gba/conversion_agent/triage.py.

Exercises the cluster-triage module introduced by FABLES_DECISIONS.md
Suggestion 3. All fixtures are synthetic (tmp_path only) — no real game data,
no external binaries, no network.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.conversion_agent.triage import (
    _sig_head,
    triage_queue,
)

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

_MAP001: dict = {
    "map_id": 1,
    "events": [
        {
            "id": 1,
            "name": "EV001",
            "x": 0,
            "y": 0,
            "pages": [
                {
                    "condition": {},
                    "list": [
                        # index 0 — move-route
                        {"code": 209, "indent": 0, "parameters": []},
                        # index 1 — warp fixed
                        {"code": 201, "indent": 0, "parameters": [0]},
                        # index 2 — needs-engine (exact table match)
                        {"code": 355, "indent": 0, "parameters": ["FakeEngine()"]},
                        # index 3 — novel (not in table)
                        {"code": 355, "indent": 0, "parameters": ["UnknownSig()"]},
                        # index 4 — phase8-custom-mode
                        {
                            "code": 111,
                            "indent": 0,
                            "parameters": [12, "$PokemonGlobal.randomizer > 0"],
                        },
                        # index 5 — novel conditional
                        {"code": 111, "indent": 0, "parameters": [12, "someCheck()"]},
                    ],
                }
            ],
        },
        {
            "id": 2,
            "name": "EV002",
            "x": 1,
            "y": 0,
            "pages": [
                {
                    "condition": {},
                    "list": [
                        # index 0 — same sig as EV001[2], for clustering
                        {"code": 355, "indent": 0, "parameters": ["FakeEngine()"]},
                        # index 1 — prefix match
                        {"code": 355, "indent": 0, "parameters": ["FakePrefixBar()"]},
                        # index 2 — Kernel.-stripped match
                        {
                            "code": 355,
                            "indent": 0,
                            "parameters": ["Kernel.FakeEngine()"],
                        },
                        # index 3 — alternative A
                        {"code": 355, "indent": 0, "parameters": ["AltSigA()"]},
                        # index 4 — alternative B
                        {"code": 355, "indent": 0, "parameters": ["AltSigB()"]},
                    ],
                }
            ],
        },
        {
            # Two same-code commands — exercises the line-hint logic.
            "id": 3,
            "name": "EV003",
            "x": 2,
            "y": 0,
            "pages": [
                {
                    "condition": {},
                    "list": [
                        # index 0
                        {"code": 355, "indent": 0, "parameters": ["FirstScript()"]},
                        # index 1
                        {"code": 355, "indent": 0, "parameters": ["SecondScript()"]},
                    ],
                }
            ],
        },
    ],
}

_COMMON_EVENTS: list[dict] = [
    # CE 4 — will be strip-listed
    {
        "id": 4,
        "name": "GTS/WT",
        "trigger": 0,
        "switch_id": 0,
        "list": [{"code": 355, "indent": 0, "parameters": ["FakeEngine()"]}],
    },
    # CE 5 — not strip-listed
    {
        "id": 5,
        "name": "OtherCE",
        "trigger": 0,
        "switch_id": 0,
        "list": [{"code": 355, "indent": 0, "parameters": ["UnknownSig()"]}],
    },
]

# Mini UNHANDLED section: exact, prefix pattern, and A/B alternative.
_SCRIPT_CALLS_MD = """\
# test reference

## MAP — emit the Poryscript equivalent

| Signature | Count | Poryscript equivalent | Notes |
|---|---|---|---|
| `notInUnhandled` | 1 | something | note |

---

## UNHANDLED — queue it (do not guess)

| Signature | Count | What it does | Why queue |
|---|---|---|---|
| `FakeEngine` | 1 | Fake engine feature | Engine not built |
| `FakePrefix*` | 1 | Fake prefix family | Engine not built |
| `AltSigA` / `AltSigB` | 1 | Alternatives | Engine not built |

---

## Ruby control-flow

(not part of the table)
"""

_STRIP_LIST: dict = {
    "feature": "test",
    "stub_message": "Not available",
    "common_events": [{"id": 4, "expect_name": "GTS/WT"}],
    "map_events": [],
}


def _write_fixtures(
    tmp_path: Path,
    *,
    entries: list[dict],
    include_strip: bool = True,
) -> tuple[Path, Path, Path]:
    """Write all fixture files and return (out_dir, ref_dir, unhandled_path)."""
    out_dir = tmp_path / "out"
    ref_dir = tmp_path / "ref"
    (out_dir / "maps").mkdir(parents=True)
    ref_dir.mkdir(parents=True)

    (out_dir / "maps" / "Map001.json").write_text(
        json.dumps(_MAP001), encoding="utf-8"
    )
    (out_dir / "common_events.json").write_text(
        json.dumps(_COMMON_EVENTS), encoding="utf-8"
    )
    (ref_dir / "uranium_script_calls.md").write_text(
        _SCRIPT_CALLS_MD, encoding="utf-8"
    )
    if include_strip:
        (ref_dir / "strip_list.json").write_text(
            json.dumps(_STRIP_LIST), encoding="utf-8"
        )

    unhandled = out_dir / "unhandled.jsonl"
    unhandled.write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n",
        encoding="utf-8",
    )
    return out_dir, ref_dir, unhandled


# ---------------------------------------------------------------------------
# 1. Move-route and warp codes
# ---------------------------------------------------------------------------


def test_move_route_no_line(tmp_path: Path) -> None:
    """code 209 → phase5-move-route even when the 'line' key is absent."""
    entries = [
        # No 'line' key — must not crash.
        {
            "map_id": 1,
            "event_id": 1,
            "event_name": "EV001",
            "reason": "agent-flagged unhandled",
            "command_code": 209,
            "description": "Set Move Route",
            "page": 1,
        },
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    assert report.total == 1
    assert report.clusters[0].disposition == "phase5-move-route"
    assert report.clusters[0].entries[0].joined  # unique code → joined fine


def test_warp_fixed(tmp_path: Path) -> None:
    """code 201 → phase5-warp."""
    entries = [
        {
            "map_id": 1,
            "event_id": 1,
            "event_name": "EV001",
            "reason": "agent-flagged unhandled",
            "command_code": 201,
            "description": "Transfer Player",
            "page": 1,
            "line": 2,
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    assert report.clusters[0].disposition == "phase5-warp"
    assert report.clusters[0].key == "201:fixed"


# ---------------------------------------------------------------------------
# 2. needs-engine: exact, prefix-pattern, Kernel.-stripped, novel fallback
# ---------------------------------------------------------------------------


def test_needs_engine_exact(tmp_path: Path) -> None:
    """355 whose sig is 'FakeEngine' → needs-engine (exact table match)."""
    entries = [
        {
            "map_id": 1,
            "event_id": 1,
            "command_code": 355,
            "description": "FakeEngine()",
            "page": 1,
            "line": 3,  # 1-based index 2 in list
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    assert report.clusters[0].disposition == "needs-engine"
    assert report.clusters[0].key == "355:FakeEngine"


def test_needs_engine_prefix(tmp_path: Path) -> None:
    """355 whose sig starts with the 'FakePrefix*' stem → needs-engine."""
    entries = [
        {
            "map_id": 1,
            "event_id": 2,
            "command_code": 355,
            "description": "FakePrefixBar()",
            "page": 1,
            "line": 2,
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    assert report.clusters[0].disposition == "needs-engine"


def test_needs_engine_kernel_stripped(tmp_path: Path) -> None:
    """355 with 'Kernel.FakeEngine' → needs-engine via Kernel.-stripped form."""
    entries = [
        {
            "map_id": 1,
            "event_id": 2,
            "command_code": 355,
            "description": "Kernel.FakeEngine()",
            "page": 1,
            "line": 3,
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    assert report.clusters[0].disposition == "needs-engine"


def test_needs_engine_alternative(tmp_path: Path) -> None:
    """355 whose sig is 'AltSigA' → needs-engine (alternative-cell match)."""
    entries = [
        {
            "map_id": 1,
            "event_id": 2,
            "command_code": 355,
            "description": "AltSigA()",
            "page": 1,
            "line": 4,
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    assert report.clusters[0].disposition == "needs-engine"


def test_novel_unknown_sig(tmp_path: Path) -> None:
    """355 whose sig is not in the table → novel."""
    entries = [
        {
            "map_id": 1,
            "event_id": 1,
            "command_code": 355,
            "description": "UnknownSig()",
            "page": 1,
            "line": 4,
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    assert report.clusters[0].disposition == "novel"
    assert report.clusters[0].key == "355:UnknownSig"


# ---------------------------------------------------------------------------
# 3. Strip-listed CE
# ---------------------------------------------------------------------------


def test_strip_listed_ce(tmp_path: Path) -> None:
    """CE 4 entry → superseded-by-strip when strip_list.json is present."""
    entries = [
        {
            "common_event_id": 4,
            "event_id": 4,
            "event_name": "GTS/WT",
            "reason": "agent-flagged unhandled",
            "command_code": 355,
            "description": "FakeEngine()",
            "page": 1,
            "line": 1,
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(
        tmp_path, entries=entries, include_strip=True
    )
    report = triage_queue(path, out_dir, ref_dir)
    assert report.clusters[0].disposition == "superseded-by-strip"


def test_strip_list_absent_falls_through(tmp_path: Path) -> None:
    """Same CE 4 entry without strip_list.json → falls through; sig in table → needs-engine."""
    entries = [
        {
            "common_event_id": 4,
            "event_id": 4,
            "event_name": "GTS/WT",
            "command_code": 355,
            "description": "FakeEngine()",
            "page": 1,
            "line": 1,
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(
        tmp_path, entries=entries, include_strip=False
    )
    report = triage_queue(path, out_dir, ref_dir)
    # No strip_list.json → rule 3 does not fire; rule 4 fires (sig in table).
    assert report.clusters[0].disposition == "needs-engine"


# ---------------------------------------------------------------------------
# 4. phase8-custom-mode vs novel conditional
# ---------------------------------------------------------------------------


def test_phase8_randomizer(tmp_path: Path) -> None:
    """111 type-12 whose text contains $PokemonGlobal.randomizer → phase8."""
    entries = [
        {
            "map_id": 1,
            "event_id": 1,
            "command_code": 111,
            "description": "conditional branch",
            "page": 1,
            "line": 5,
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    assert report.clusters[0].disposition == "phase8-custom-mode"


def test_novel_conditional_other(tmp_path: Path) -> None:
    """111 type-12 with a different script text → novel; key contains cond12 + sig."""
    entries = [
        {
            "map_id": 1,
            "event_id": 1,
            "command_code": 111,
            "description": "conditional branch other",
            "page": 1,
            "line": 6,
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    assert report.clusters[0].disposition == "novel"
    assert "cond12" in report.clusters[0].key
    assert "someCheck" in report.clusters[0].key


# ---------------------------------------------------------------------------
# 5. Line-hint robustness
# ---------------------------------------------------------------------------


def test_line_hint_picks_second(tmp_path: Path) -> None:
    """Two same-code commands; line=2 (1-based) selects the second one."""
    entries = [
        {
            "map_id": 1,
            "event_id": 3,
            "command_code": 355,
            "description": "SecondScript()",
            "page": 1,
            "line": 2,
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    assert report.clusters[0].key == "355:SecondScript"
    assert report.clusters[0].entries[0].joined


def test_out_of_range_line_falls_back_to_first(tmp_path: Path) -> None:
    """line=999 is out of range; join falls back to the first matching command."""
    entries = [
        {
            "map_id": 1,
            "event_id": 3,
            "command_code": 355,
            "description": "whatever",
            "page": 1,
            "line": 999,
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    # Falls back to index 0 → "FirstScript"
    assert report.clusters[0].key == "355:FirstScript"
    assert report.clusters[0].entries[0].joined


def test_dead_line_hint_resolved_by_description(tmp_path: Path) -> None:
    """A wrong line hint on a multi-355 page joins via the description naming the call.

    Measured live: CE4's GTS.open entries carried agent-invented line numbers and
    mis-keyed under the page's leading pbCallBub before this heuristic."""
    entries = [
        {
            "map_id": 1,
            "event_id": 3,
            "command_code": 355,
            "description": "SecondScript opens the second thing — no GBA equivalent",
            "page": 1,
            "line": 999,
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    assert report.clusters[0].key == "355:SecondScript"
    assert report.clusters[0].entries[0].joined


def test_missing_event_yields_unjoined_and_rule_still_fires(tmp_path: Path) -> None:
    """Missing event → joined=False, key '{code}:unjoined', rule 1 still fires."""
    entries = [
        {
            "map_id": 1,
            "event_id": 99,  # does not exist
            "command_code": 209,
            "description": "Move Route",
            "page": 1,
            "line": 1,
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    e = report.clusters[0].entries[0]
    assert not e.joined
    assert e.cluster_key == "209:unjoined"
    # Rule 1 (code 209) beats join failure.
    assert e.disposition == "phase5-move-route"


# ---------------------------------------------------------------------------
# 6. Clustering, totals, and report ordering
# ---------------------------------------------------------------------------


def test_identical_keys_cluster_together(tmp_path: Path) -> None:
    """Two entries with the same sig produce one Cluster with count=2."""
    entries = [
        # EV001 index 2 — FakeEngine
        {
            "map_id": 1,
            "event_id": 1,
            "command_code": 355,
            "description": "FakeEngine() call 1",
            "page": 1,
            "line": 3,
        },
        # EV002 index 0 — also FakeEngine
        {
            "map_id": 1,
            "event_id": 2,
            "command_code": 355,
            "description": "FakeEngine() call 2",
            "page": 1,
            "line": 1,
        },
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    assert report.total == 2
    fe_clusters = [c for c in report.clusters if c.key == "355:FakeEngine"]
    assert len(fe_clusters) == 1
    assert fe_clusters[0].count == 2
    assert fe_clusters[0].example_description == "FakeEngine() call 1"


def test_novel_first_ordering(tmp_path: Path) -> None:
    """novel clusters appear before non-novel ones in the sorted output."""
    entries = [
        # phase5-warp
        {
            "map_id": 1,
            "event_id": 1,
            "command_code": 201,
            "description": "warp",
            "page": 1,
            "line": 2,
        },
        # novel
        {
            "map_id": 1,
            "event_id": 1,
            "command_code": 355,
            "description": "UnknownSig()",
            "page": 1,
            "line": 4,
        },
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    assert report.clusters[0].disposition == "novel"


def test_report_totals(tmp_path: Path) -> None:
    """total and novel_total are correct across a mixed queue."""
    entries = [
        # novel
        {
            "map_id": 1,
            "event_id": 1,
            "command_code": 355,
            "page": 1,
            "line": 4,
            "description": "UnknownSig()",
        },
        # phase5-move-route
        {
            "map_id": 1,
            "event_id": 1,
            "command_code": 209,
            "page": 1,
            "description": "route",
        },
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    report = triage_queue(path, out_dir, ref_dir)
    assert report.total == 2
    assert report.novel_total == 1


def test_summary_lines_non_empty(tmp_path: Path) -> None:
    """summary_lines returns non-empty output with TOTAL row."""
    entries = [
        {
            "map_id": 1,
            "event_id": 1,
            "command_code": 209,
            "page": 1,
            "description": "route",
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    lines = triage_queue(path, out_dir, ref_dir).summary_lines()
    assert len(lines) >= 2
    assert any("TOTAL" in ln for ln in lines)
    assert any("phase5-move-route" in ln for ln in lines)


def test_novel_lines_non_empty(tmp_path: Path) -> None:
    """novel_lines returns at least one line per novel cluster entry."""
    entries = [
        {
            "map_id": 1,
            "event_id": 1,
            "command_code": 355,
            "page": 1,
            "line": 4,
            "description": "UnknownSig()",
        }
    ]
    out_dir, ref_dir, path = _write_fixtures(tmp_path, entries=entries)
    lines = triage_queue(path, out_dir, ref_dir).novel_lines()
    assert len(lines) >= 2  # header line + at least one entry line
    assert any("Map1/EV1" in ln for ln in lines)


# ---------------------------------------------------------------------------
# 7. Malformed JSONL
# ---------------------------------------------------------------------------


def test_malformed_jsonl_skipped(tmp_path: Path) -> None:
    """Malformed JSON lines are silently skipped; valid lines still process."""
    out_dir = tmp_path / "out"
    ref_dir = tmp_path / "ref"
    (out_dir / "maps").mkdir(parents=True)
    ref_dir.mkdir(parents=True)

    (out_dir / "maps" / "Map001.json").write_text(
        json.dumps(_MAP001), encoding="utf-8"
    )
    (out_dir / "common_events.json").write_text(
        json.dumps(_COMMON_EVENTS), encoding="utf-8"
    )
    (ref_dir / "uranium_script_calls.md").write_text(
        _SCRIPT_CALLS_MD, encoding="utf-8"
    )

    valid_entry = {
        "map_id": 1,
        "event_id": 1,
        "command_code": 209,
        "page": 1,
        "description": "route",
    }
    unhandled = out_dir / "unhandled.jsonl"
    unhandled.write_text(
        "{INVALID JSON\n" + json.dumps(valid_entry) + "\n",
        encoding="utf-8",
    )

    report = triage_queue(unhandled, out_dir, ref_dir)
    # The malformed line is skipped; only the valid entry is counted.
    assert report.total == 1
    assert report.clusters[0].disposition == "phase5-move-route"


# ---------------------------------------------------------------------------
# Unit: _sig_head
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Kernel.pbReceiveItem(:POTION,1)", "Kernel.pbReceiveItem"),
        ("GTS.open", "GTS.open"),
        ("$lobbyreset=true", "$lobbyreset"),
        ("$PokemonGlobal.randomizer > 0", "$PokemonGlobal.randomizer"),
        ("FakeEngine()", "FakeEngine"),
        ("", ""),
        ("  FakeEngine()", "FakeEngine"),  # leading whitespace stripped
    ],
)
def test_sig_head(text: str, expected: str) -> None:
    assert _sig_head(text) == expected
