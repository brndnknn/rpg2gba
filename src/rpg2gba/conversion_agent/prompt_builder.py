"""Assemble the per-event conversion prompt (Phase 4 §4.4).

The conversion agent's *frozen instructions* are `prompts/system.md` (passed to a
backend as its system prompt). This module builds the per-event **user** prompt
and loads the stable, cacheable chunks that go in it:

  - the current flag-registry state (names already assigned),
  - the Poryscript cheatsheet (`reference/poryscript_cheatsheet.md`),
  - 2–3 few-shot examples (`prompts/few_shot/*.md`),
  - the command-code reference (`reference/rgss_event_commands.md`),
  - the event JSON itself.

Stable chunks come first so a future caching backend can reuse them.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_PKG = Path(__file__).resolve().parent
_PROMPTS = _PKG / "prompts"

# A data row in reference/rgss_event_commands.md: `| 355 | Script | Adaptable | 12 |`.
_REF_ROW = re.compile(r"^\|\s*(\d+)\s*\|")


def load_system_prompt(prompts_dir: Path | None = None) -> str:
    """The frozen conversion-agent instruction set (prompts/system.md)."""
    return (prompts_dir or _PROMPTS).joinpath("system.md").read_text(encoding="utf-8")


def load_few_shots(prompts_dir: Path | None = None) -> list[str]:
    """Every few-shot example under prompts/few_shot/, sorted by filename."""
    fs_dir = (prompts_dir or _PROMPTS) / "few_shot"
    if not fs_dir.is_dir():
        return []
    return [p.read_text(encoding="utf-8") for p in sorted(fs_dir.glob("*.md"))]


def load_cheatsheet(reference_dir: Path) -> str:
    return (reference_dir / "poryscript_cheatsheet.md").read_text(encoding="utf-8")


def load_command_reference(reference_dir: Path) -> str:
    return (reference_dir / "rgss_event_commands.md").read_text(encoding="utf-8")


def load_script_call_reference(reference_dir: Path) -> str:
    """The Uranium `pbXxx`/Kernel/`$game_*` script-call disposition table.

    Stable, ~40-row chunk (see reference/uranium_script_calls.md). It tells the
    agent which script calls to MAP, STRIP, or queue as UNHANDLED — the real
    translation surface, since Uranium adds no custom command *codes*.
    """
    return (reference_dir / "uranium_script_calls.md").read_text(encoding="utf-8")


def filter_command_reference(full_text: str, codes: set[int]) -> str:
    """Keep only the command-code table rows whose code is used in this event.

    The full reference embeds the whole 59-code table plus the 250-signature
    script-call list — large, static, and re-billed on every cold spawn. The agent
    only needs the rows for codes actually present (and it gets the raw script-call
    text from the event JSON anyway), so we send a compact, per-event slice.
    """
    kept = [
        ln
        for ln in full_text.splitlines()
        if (m := _REF_ROW.match(ln)) and int(m.group(1)) in codes
    ]
    header = "| Code | Name | Tag | Count |\n|---|---|---|---|"
    body = "\n".join(kept) if kept else "| (no catalogued codes in this event) |"
    return "Command codes used in this event:\n\n" + header + "\n" + body


def _render_registry(registry_state: dict) -> str:
    flags = registry_state.get("flags", {})
    vars_ = registry_state.get("vars", {})
    script_switches = registry_state.get("script_switches", [])
    lines = ["Already-assigned names (reuse these; do not rename):"]
    for sid, name in sorted(flags.items(), key=lambda kv: int(kv[0])):
        lines.append(f"- switch {sid} -> {name}")
    for vid, name in sorted(vars_.items(), key=lambda kv: int(kv[0])):
        lines.append(f"- variable {vid} -> {name}")
    if not flags and not vars_:
        lines.append("- (none yet)")
    if script_switches:
        ids = ", ".join(str(s) for s in sorted(script_switches))
        lines.append(
            "\nScript-switches (Essentials runtime-evaluated — NEVER propose a FLAG_ "
            "for these; queue any conditional that tests them as unhandled): " + ids
        )
    return "\n".join(lines)


def build_prompt(
    event_json: dict,
    registry_state: dict,
    *,
    few_shots: list[str],
    cheatsheet: str,
    command_ref: str,
    script_call_ref: str,
) -> str:
    """Compose the per-event user prompt from its parts."""
    examples = "\n\n---\n\n".join(few_shots) if few_shots else "(no examples provided)"
    return "\n\n".join(
        [
            "# Poryscript cheatsheet\n\n" + cheatsheet,
            "# Command-code reference\n\n" + command_ref,
            "# Uranium script-call reference\n\n" + script_call_ref,
            "# Few-shot examples\n\n" + examples,
            "# Flag registry\n\n" + _render_registry(registry_state),
            "# Event to convert\n\n```json\n"
            + json.dumps(event_json, indent=2, ensure_ascii=False)
            + "\n```",
        ]
    )
