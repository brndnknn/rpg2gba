"""Progress + token tally for a Phase 4 bulk run.

Reads the run's on-disk artifacts (no live process needed) so progress and spend
can be inspected at any time — mid-run from another terminal, or after the fact:

  checkpoints/*.done   one per fully-converted map (+ CommonEvents.done)
  token_usage.jsonl    one JSON line per backend spawn (written by ClaudeCodeBackend)
  scripts/*.pory       emitted Poryscript (one ``script`` block per page)
  unhandled.jsonl      the fail-loud queue (triaged by reason)
  run_state.json       the bulk runner's heartbeat (mode / window / status)

`scripts/run_stats.py` is a thin CLI over this; the bulk runner prints the same
summary on exit.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from rpg2gba.conversion_agent.orchestrator import triage
from rpg2gba.conversion_agent.triage import TriageReport, triage_queue

logger = logging.getLogger(__name__)

# The reference tree lives at the repo root (src layout: src/rpg2gba/conversion_agent/
# run_report.py → three parents up). Callers may override via collect_stats().
_DEFAULT_REFERENCE_DIR = Path(__file__).resolve().parents[3] / "reference"


def _count_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def collect_stats(out_dir: Path, reference_dir: Path | None = None) -> dict:
    """Gather a snapshot of bulk-run progress and token usage from `out_dir`."""
    out_dir = Path(out_dir)
    reference_dir = Path(reference_dir) if reference_dir else _DEFAULT_REFERENCE_DIR
    maps_dir = out_dir / "maps"
    checkpoints = out_dir / "checkpoints"
    usage_log = out_dir / "token_usage.jsonl"

    maps_total = len(list(maps_dir.glob("Map*.json"))) if maps_dir.is_dir() else 0
    done_stems = {p.stem for p in checkpoints.glob("*.done")} if checkpoints.is_dir() else set()
    maps_done = sum(1 for s in done_stems if s.startswith("Map"))

    tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    cost_usd = 0.0
    spawns = 0
    if usage_log.is_file():
        for line in usage_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            spawns += 1
            tokens["input"] += rec.get("input_tokens") or 0
            tokens["output"] += rec.get("output_tokens") or 0
            tokens["cache_read"] += rec.get("cache_read_input_tokens") or 0
            tokens["cache_creation"] += rec.get("cache_creation_input_tokens") or 0
            cost_usd += rec.get("cost_usd") or 0.0

    script_blocks = 0
    stripped_blocks = 0
    scripts_dir = out_dir / "scripts"
    if scripts_dir.is_dir():
        for pory in scripts_dir.glob("*.pory"):
            for ln in pory.read_text(encoding="utf-8").splitlines():
                if ln.lstrip().startswith("script "):
                    script_blocks += 1
                elif ln.lstrip().startswith("# STRIPPED:"):
                    stripped_blocks += 1

    queue_path = out_dir / "unhandled.jsonl"
    run_state_path = out_dir / "run_state.json"
    run_state = None
    if run_state_path.is_file():
        try:
            run_state = json.loads(run_state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            run_state = None

    # Clustered triage (FABLES_DECISIONS #3) is the primary view; the legacy
    # reason-grouped triage() stays as the fallback when the queue or the
    # reference tree is unavailable (e.g. tests with a bare out_dir).
    triage_report: TriageReport | None = None
    if queue_path.is_file():
        try:
            triage_report = triage_queue(queue_path, out_dir, reference_dir)
        except FileNotFoundError as exc:
            logger.warning("clustered triage unavailable (%s) — falling back", exc)

    return {
        "maps_total": maps_total,
        "maps_done": maps_done,
        "common_events_done": "CommonEvents" in done_stems,
        "spawns": spawns,
        "script_blocks": script_blocks,
        "stripped_blocks": stripped_blocks,
        "tokens": tokens,
        "cost_usd": round(cost_usd, 4),
        "queued": _count_lines(queue_path),
        "triage": triage(queue_path),
        "triage_clustered": triage_report,
        "run_state": run_state,
    }


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _window_line(run_state: dict) -> str | None:
    """A human-readable line about the 5-hour window, if the runner left one."""
    status = run_state.get("status")
    if status == "paused" and run_state.get("resume_at"):
        remaining = run_state["resume_at"] - time.time()
        if remaining > 0:
            mins = int(remaining // 60)
            return f"  window:    PAUSED — resuming in {mins // 60}h{mins % 60:02d}m"
        return "  window:    PAUSED — resume time reached"
    if status:
        return f"  status:    {status}"
    return None


def format_stats(stats: dict) -> str:
    t = stats["tokens"]
    ce = "done" if stats["common_events_done"] else "pending"
    lines = [
        "Phase 4 bulk-run progress",
        "-------------------------",
        f"  maps:      {stats['maps_done']}/{stats['maps_total']} converted"
        f"   (common events: {ce})",
        f"  emitted:   {_fmt_int(stats['script_blocks'])} script blocks"
        + (
            f"   ({stats['stripped_blocks']} stripped stubs)"
            if stats.get("stripped_blocks")
            else ""
        ),
        f"  spawns:    {_fmt_int(stats['spawns'])} backend calls (LLM)",
        f"  queued:    {_fmt_int(stats['queued'])} unhandled",
        "  tokens:    "
        f"in={_fmt_int(t['input'])} out={_fmt_int(t['output'])} "
        f"cache_read={_fmt_int(t['cache_read'])} cache_creation={_fmt_int(t['cache_creation'])}",
        f"  cost:      ${stats['cost_usd']:.2f} (provider-reported)",
    ]
    if stats["run_state"]:
        wl = _window_line(stats["run_state"])
        if wl:
            lines.append(wl)
    report = stats.get("triage_clustered")
    if report is not None and report.total:
        lines.append(
            f"  triage (clustered; novel = build-agent review queue,"
            f" {report.novel_total} entries):"
        )
        lines.extend(report.summary_lines())
    elif stats["triage"]:
        lines.append("  triage:")
        for reason, count in sorted(stats["triage"].items(), key=lambda kv: -kv[1]):
            lines.append(f"    {count:>4}  {reason}")
    return "\n".join(lines)
