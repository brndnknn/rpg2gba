"""Bulk-run resilience: usage-limit detection, transport retries, abort-not-queue,
and the run_report tally. All hermetic — the claude subprocess is mocked, no binary
or network is touched.
"""
from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from rpg2gba.conversion_agent import orchestrator as orch
from rpg2gba.conversion_agent import poryscript, run_report
from rpg2gba.conversion_agent.backends import (
    BackendTransportError,
    BudgetReached,
    CappingBackend,
    ConversionBackend,
    ConversionResult,
    RateLimitError,
    claude_code,
)
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REPO_ROOT / "reference"

_GOOD = {"script": "script S { end }", "new_flags": [], "new_vars": [], "unhandled": []}


# ---- rate-limit classification ----------------------------------------------


def test_classify_rate_limit_detects_window() -> None:
    err = claude_code._classify_rate_limit("Claude AI usage limit reached. Resets at 4pm.")
    assert isinstance(err, RateLimitError)
    assert err.weekly is False
    assert err.reset_hint and "4pm" in err.reset_hint


def test_classify_rate_limit_detects_weekly() -> None:
    err = claude_code._classify_rate_limit("You have hit your weekly usage limit.")
    assert isinstance(err, RateLimitError)
    assert err.weekly is True


def test_classify_rate_limit_ignores_normal_output() -> None:
    assert claude_code._classify_rate_limit('{"result": "script S { end }"}') is None


def test_successful_envelope_with_429_telemetry_is_not_a_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a clean conversion whose envelope telemetry contains the digits
    '429' (a duration_ms, a session_id) must NOT be misread as a usage cap."""
    envelope = json.dumps(
        {
            "result": json.dumps(_GOOD),
            "is_error": False,
            "duration_ms": 14290,
            "session_id": "a429f001-dead-cafe-0000-000000000000",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    )

    def fake_run(cmd, **kw):
        return types.SimpleNamespace(returncode=0, stdout=envelope, stderr="")

    monkeypatch.setattr(claude_code.subprocess, "run", fake_run)
    backend = claude_code.ClaudeCodeBackend("SYSTEM")
    result = backend.convert_event({}, {}, "prompt")
    assert result.script == _GOOD["script"]


def test_is_error_envelope_with_cap_phrase_raises_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A returncode-0 envelope flagged is_error whose message is a cap is a real limit."""
    envelope = json.dumps(
        {"result": "Claude AI usage limit reached. Resets at 4pm.", "is_error": True}
    )

    def fake_run(cmd, **kw):
        return types.SimpleNamespace(returncode=0, stdout=envelope, stderr="")

    monkeypatch.setattr(claude_code.subprocess, "run", fake_run)
    backend = claude_code.ClaudeCodeBackend("SYSTEM")
    with pytest.raises(RateLimitError):
        backend.convert_event({}, {}, "prompt")


# ---- backend: raise vs retry ------------------------------------------------


def test_backend_raises_rate_limit_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_run(cmd, **kw):
        calls["n"] += 1
        return types.SimpleNamespace(
            returncode=1, stdout="", stderr="Claude usage limit reached; resets at 5pm"
        )

    monkeypatch.setattr(claude_code.subprocess, "run", fake_run)
    backend = claude_code.ClaudeCodeBackend("SYSTEM", max_attempts=3)
    with pytest.raises(RateLimitError):
        backend.convert_event({}, {}, "prompt")
    assert calls["n"] == 1  # never retried


def test_backend_retries_then_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_run(cmd, **kw):
        calls["n"] += 1
        return types.SimpleNamespace(returncode=2, stdout="", stderr="boom (network)")

    monkeypatch.setattr(claude_code.subprocess, "run", fake_run)
    monkeypatch.setattr(claude_code.time, "sleep", lambda *_: None)
    backend = claude_code.ClaudeCodeBackend("SYSTEM", max_attempts=3)
    with pytest.raises(BackendTransportError):
        backend.convert_event({}, {}, "prompt")
    assert calls["n"] == 3  # exhausted all attempts


def test_backend_writes_usage_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    envelope = json.dumps(
        {
            "result": json.dumps(_GOOD),
            "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100},
            "total_cost_usd": 0.0123,
        }
    )
    monkeypatch.setattr(
        claude_code.subprocess,
        "run",
        lambda cmd, **kw: types.SimpleNamespace(returncode=0, stdout=envelope, stderr=""),
    )
    log = tmp_path / "token_usage.jsonl"
    backend = claude_code.ClaudeCodeBackend("SYSTEM", usage_log_path=log)
    backend.convert_event({}, {}, "prompt")
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["input_tokens"] == 10
    assert rec["cache_read_input_tokens"] == 100
    assert rec["cost_usd"] == 0.0123


# ---- orchestrator: abort, don't queue ---------------------------------------


class _RaisingBackend(ConversionBackend):
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.system_prompt = ""

    def convert_event(self, event_json, registry_state, prompt) -> ConversionResult:
        raise self.exc


def _fake_compile(script: str) -> poryscript.CompileResult:
    return poryscript.CompileResult(ok=True, stdout="", stderr="")


def _write_map(maps_dir: Path, map_id: int) -> Path:
    maps_dir.mkdir(parents=True, exist_ok=True)
    m = {
        "map_id": map_id,
        "events": [
            {"id": 1, "name": "EV001", "x": 0, "y": 0,
             "pages": [{"list": [{"code": 101, "parameters": ["hi"]}]}]}
        ],
    }
    path = maps_dir / f"Map{map_id:03d}.json"
    path.write_text(json.dumps(m), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "exc",
    [
        RateLimitError("limit", weekly=False),
        BackendTransportError("net"),
        BudgetReached(5),
    ],
)
def test_orchestrator_reraises_and_does_not_queue(tmp_path: Path, exc: Exception) -> None:
    out = tmp_path / "out"
    o = orch.Orchestrator(
        _RaisingBackend(exc), FlagRegistry(), out, reference_dir=REFERENCE, compile_fn=_fake_compile
    )
    map_file = _write_map(out / "maps", 1)
    with pytest.raises(type(exc)):
        o.convert_map(map_file)
    # The good event must NOT be queued, and the map must NOT be checkpointed — so a
    # restart re-attempts it cleanly.
    assert not (out / "unhandled.jsonl").is_file()
    assert not (out / "checkpoints" / "Map001.done").is_file()


# ---- run_report tally -------------------------------------------------------


def test_collect_stats(tmp_path: Path) -> None:
    out = tmp_path / "out"
    (out / "maps").mkdir(parents=True)
    for i in (1, 2, 3):
        (out / "maps" / f"Map{i:03d}.json").write_text("{}", encoding="utf-8")
    (out / "checkpoints").mkdir()
    (out / "checkpoints" / "Map001.done").write_text("ok", encoding="utf-8")
    (out / "checkpoints" / "CommonEvents.done").write_text("ok", encoding="utf-8")
    (out / "scripts").mkdir()
    (out / "scripts" / "Map001.pory").write_text(
        "script A { end }\nscript B { end }\n", encoding="utf-8"
    )
    (out / "token_usage.jsonl").write_text(
        json.dumps({"input_tokens": 10, "output_tokens": 4, "cost_usd": 0.01}) + "\n"
        + json.dumps({"input_tokens": 20, "output_tokens": 6, "cost_usd": 0.02}) + "\n",
        encoding="utf-8",
    )
    (out / "unhandled.jsonl").write_text(
        json.dumps({"reason": "compile failed twice"}) + "\n", encoding="utf-8"
    )

    stats = run_report.collect_stats(out)
    assert stats["maps_total"] == 3
    assert stats["maps_done"] == 1
    assert stats["common_events_done"] is True
    assert stats["spawns"] == 2
    assert stats["script_blocks"] == 2
    assert stats["tokens"]["input"] == 30
    assert stats["cost_usd"] == pytest.approx(0.03)
    assert stats["queued"] == 1
    # format must not raise on a populated snapshot
    assert "maps:      1/3" in run_report.format_stats(stats)


# ---- --limit: bounded, resumable rounds -------------------------------------


class _CountingBackend(ConversionBackend):
    """Succeeds every call, counting spawns. ``fail_after`` raises a usage cap once the
    count exceeds it (simulating a mid-pass abort)."""

    def __init__(self, fail_after: int | None = None) -> None:
        self.system_prompt = ""
        self.calls = 0
        self.fail_after = fail_after

    def convert_event(self, event_json, registry_state, prompt) -> ConversionResult:
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise RateLimitError("cap")
        return ConversionResult(script="script CE { end }")


def test_capping_backend_stops_after_limit() -> None:
    inner = _CountingBackend()
    capped = CappingBackend(inner, 2)
    capped.convert_event({}, {}, "p")
    capped.convert_event({}, {}, "p")
    assert inner.calls == 2
    with pytest.raises(BudgetReached):
        capped.convert_event({}, {}, "p")
    assert inner.calls == 2  # the over-limit call never reached the inner backend


def test_capping_backend_rejects_bad_limit() -> None:
    with pytest.raises(ValueError):
        CappingBackend(_CountingBackend(), 0)


def test_capping_backend_delegates_system_prompt() -> None:
    inner = _CountingBackend()
    inner.system_prompt = "SP"
    assert CappingBackend(inner, 1).system_prompt == "SP"


def _write_common_events(out: Path, ids: list[int]) -> Path:
    ces = [
        {"id": i, "name": f"CE{i}", "list": [{"code": 101, "parameters": [f"hi{i}"]}]}
        for i in ids
    ]
    path = out / "common_events.json"
    path.write_text(json.dumps(ces), encoding="utf-8")
    return path


def test_common_events_resume_after_abort(tmp_path: Path) -> None:
    """A capped/rate-limited common-event pass must resume, not re-spend done CEs."""
    out = tmp_path / "out"
    out.mkdir()
    ce_file = _write_common_events(out, [1, 2, 3])

    # First run aborts after 2 CEs (no .done checkpoint written).
    b1 = _CountingBackend(fail_after=2)
    o1 = orch.Orchestrator(
        b1, FlagRegistry(), out, reference_dir=REFERENCE, compile_fn=_fake_compile
    )
    with pytest.raises(RateLimitError):
        o1.convert_common_events(ce_file)
    assert b1.calls == 3  # CE3 was attempted and raised
    assert not (out / "checkpoints" / "CommonEvents.done").is_file()
    progress = json.loads((out / "checkpoints" / "CommonEvents.blocks.json").read_text())
    assert set(progress) == {"1", "2"}  # only the two completed CEs are recorded

    # Resume with a fresh backend: CE1+CE2 are skipped (no spend), only CE3 re-spawns.
    b2 = _CountingBackend()
    o2 = orch.Orchestrator(
        b2, FlagRegistry(), out, reference_dir=REFERENCE, compile_fn=_fake_compile
    )
    o2.convert_common_events(ce_file)
    assert b2.calls == 1  # only the one unfinished CE
    assert (out / "checkpoints" / "CommonEvents.done").is_file()
    pory = (out / "scripts" / "CommonEvents.pory").read_text()
    assert pory.count("script CE { end }") == 3  # all three blocks present after resume
