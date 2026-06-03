"""Assemble the conversion prompt, split for prompt-caching (Phase 4 §4.4 + dedup B).

The prompt is split across two channels by how often it varies:

  * **system prompt** = `load_system_prompt()` (frozen instructions, `prompts/system.md`)
    + `build_static_context(...)` — the event-invariant cheatsheet, script-call
      reference, and few-shot examples. Composed once in `pipeline._phase4_backend` and
      passed as `claude -p --system-prompt`, so back-to-back spawns hit the server-side
      prompt cache instead of re-billing it every event.
  * **user prompt** = `build_user_prompt(...)` — only the per-event-variable content:
    the filtered command-code reference, the current flag-registry state, and the
    event JSON.

The orchestrator builds the user prompt; the pipeline builds the system prompt.
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


def build_static_context(*, cheatsheet: str, script_call_ref: str, few_shots: list[str]) -> str:
    """The frozen, event-invariant block that rides in the cacheable system prompt.

    The cheatsheet, script-call reference, and few-shot examples are byte-identical
    for all 5,301 events. Moving them out of the per-event user message and into the
    `claude -p --system-prompt` (composed once in `pipeline._phase4_backend`) lets
    back-to-back spawns hit Anthropic's server-side prompt cache instead of re-billing
    this tonnage every time (dedup Phase B). Appended after `load_system_prompt()`.
    """
    examples = "\n\n---\n\n".join(few_shots) if few_shots else "(no examples provided)"
    return "\n\n".join(
        [
            "# Poryscript cheatsheet\n\n" + cheatsheet,
            "# Uranium script-call reference\n\n" + script_call_ref,
            "# Few-shot examples\n\n" + examples,
        ]
    )


def build_user_prompt(event_json: dict, registry_state: dict, *, command_ref: str) -> str:
    """The per-event **user** message: only content that varies per event.

    The filtered command-code reference (sliced to this event's codes), the current
    flag-registry state, and the event JSON. The event-invariant context (cheatsheet,
    script-call reference, few-shots) lives in the system prompt — see
    `build_static_context`."""
    return "\n\n".join(
        [
            "# Command-code reference\n\n" + command_ref,
            "# Flag registry\n\n" + _render_registry(registry_state),
            "# Event to convert\n\n```json\n"
            + json.dumps(event_json, indent=2, ensure_ascii=False)
            + "\n```",
        ]
    )
