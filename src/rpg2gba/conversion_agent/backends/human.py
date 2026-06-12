"""Interactive conversion backend: a human types the Poryscript instead of an LLM.

Drop-in alternative to ClaudeCodeBackend for the hand-conversion pass
(`scripts/run_human.py`). It spends zero Claude usage: the operator reads a
compact, mobile-friendly render of one event and types the Poryscript, which the
orchestrator then runs through the exact same compile-gate / registry / memo /
checkpoint machinery as an LLM result — so a hand conversion is indistinguishable
downstream and seeds the memo for every identical twin.

Carries the SAME frozen ``system_prompt`` as the production backend so the memo
manifest's prompt fingerprint matches: hand-seeded entries and Opus-seeded entries
share one memo, and work done by either is reused by the other.

Operator controls per event:
  <script> + a line ``EOF``  — accept this conversion
  ``opus``                   — punt to the bulk run (raises EventDeferred; not queued)
  ``?``                      — dump the full prompt (cheatsheet, refs, few-shots)
  ``quit`` / EOF (Ctrl-D)    — end the session cleanly (raises KeyboardInterrupt)

Global flags/vars are NOT collected here by design: the human lane excludes events
that mint new global switches/vars (code 121/122), so only the orchestrator-minted
self/temp-switch names appear — and those the operator merely pastes. A stray
``# UNHANDLED: ...`` line in the typed script is scraped into one queue entry,
mirroring the LLM breadcrumb idiom.
"""
from __future__ import annotations

import re
import textwrap
from collections.abc import Callable

from rpg2gba.conversion_agent.backends import (
    ConversionBackend,
    ConversionResult,
    EventDeferred,
)

# Hard cap on rendered line width so a phone terminal never soft-wraps one logical
# line onto two (the operator asked for 45). Long dialogue/params are word-wrapped
# with a continuation indent; long unbreakable tokens (flag names) are left intact.
_WIDTH = 45

# Human-readable labels for the RPG Maker command codes the human lane actually sees.
# Not exhaustive — an unlabeled code still prints its number + raw params, which is
# enough for an operator with the command reference open (`?`).
_CODE_LABELS: dict[int, str] = {
    101: "text",
    401: "  text (cont.)",
    102: "show choices",
    402: "  when choice",
    403: "  when cancel",
    404: "  end choices",
    111: "if (conditional branch)",
    411: "else",
    412: "end if",
    123: "set self-switch",
    106: "wait",
    117: "call common event",
    108: "comment (strip)",
    408: "  comment (cont.)",
    201: "transfer player (warp)",
    250: "play SE",
}

_UNHANDLED_RE = re.compile(r"#\s*UNHANDLED:\s*(.+)", re.IGNORECASE)
_END_SENTINEL = "EOF"
# Must match orchestrator._retry_prompt's header — how a retry is recognized.
_RETRY_MARKER = "# Previous attempt failed to compile"


class HumanBackend(ConversionBackend):
    def __init__(
        self,
        system_prompt: str,
        *,
        quickref: str = "",
        input_fn: Callable[[str], str] | None = None,
        output_fn: Callable[[str], None] | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        # Compact, lane-only reference (reference/human_quickref.md) shown by `?` — NOT
        # the giant system prompt. Searchable inline via `?term`.
        self.quickref = quickref
        # Injectable I/O so tests drive the loop with a scripted input iterator and
        # capture output, never touching a real terminal.
        self._input = input_fn or input
        self._output = output_fn or print

    def convert_event(
        self,
        event_json: dict,
        registry_state: dict,
        prompt: str,
    ) -> ConversionResult:
        # On a retry the orchestrator appends the compiler error to the prompt; surface it
        # so the operator sees why the last attempt was rejected before retyping.
        if _RETRY_MARKER in prompt:
            err = prompt.split(_RETRY_MARKER, 1)[1].strip()
            self._output("\n⚠ previous attempt did not compile:\n" + err)
        self._output(_render_event(event_json))
        self._output(_help_text())
        script_lines: list[str] = []
        while True:
            try:
                line = self._input("> ")  # visible prompt so it never looks frozen
            except EOFError:  # Ctrl-D on a phone keyboard / piped stdin exhausted
                raise KeyboardInterrupt("human session ended (EOF)") from None
            stripped = line.strip()
            low = stripped.lower()
            # All commands below work at ANY point — they preserve what you've already
            # typed — because none of these forms is a valid Poryscript line (`?`/`:` can't
            # start one, and bare `opus`/`quit` aren't statements either).
            if stripped.startswith("?"):  # `?` / `?term` — quick-reference lookup
                self._output(_filter_ref(self.quickref, stripped[1:].strip()))
                continue
            if low in ("q", "quit", ":q", ":quit"):
                raise KeyboardInterrupt("human session ended")
            if low in ("o", "opus", ":o", ":opus"):
                raise EventDeferred("operator punted this event to the bulk run")
            if low in (":undo", ":u"):  # drop the last line typed (poor-man's go-back)
                if script_lines:
                    self._output(f"  ↩ dropped: {script_lines.pop()}")
                else:
                    self._output("  (nothing to undo)")
                continue
            if low == ":clear":  # wipe the whole attempt and start over
                script_lines.clear()
                self._output("  (cleared — start over)")
                continue
            if stripped == _END_SENTINEL or low == ":done":
                break
            script_lines.append(line)
        script = "\n".join(script_lines).strip("\n")
        return ConversionResult(
            script=script,
            new_flags=[],
            new_vars=[],
            unhandled=_scrape_unhandled(script, event_json),
        )


def _render_event(event_json: dict) -> str:
    """Compact, phone-sized view of one event: header, per-page decoded commands, and
    the orchestrator-minted self/temp-switch names + the label prefix to use."""
    # Imported lazily to avoid a circular import (orchestrator imports backends).
    from rpg2gba.conversion_agent.orchestrator import (
        _event_self_switches,
        _event_temp_switches,
    )

    map_id = int(event_json.get("map_id", 0))
    ev_id = int(event_json.get("id", 0))
    name = event_json.get("name", "")
    pages = event_json.get("pages", [])
    lines = [
        "═" * _WIDTH,
        f" Map{map_id:03d}  ev{ev_id}  \"{name}\"",
        "═" * _WIDTH,
    ]
    for i, page in enumerate(pages, start=1):
        cond = _page_condition_summary(page)
        trig = _TRIGGERS.get(page.get("trigger"), str(page.get("trigger")))
        cmds = [c for c in page.get("list", []) if c.get("code", 0) != 0]
        head = f" PAGE {i}"
        if cond:
            head += f"  (when {cond})"
        head += f"   trigger: {trig}"
        lines.append(head)
        if not cmds:
            lines.append("   · empty (no commands)")
            continue
        for c in cmds:
            lines.append(f"   {_render_command(c)}")
    prefix = f"Map{map_id:03d}_EV{ev_id:03d}_"
    lines.append("─" * _WIDTH)
    lines.append(f" label prefix:  {prefix}Page<n>")
    ss = sorted(_event_self_switches(event_json))
    ts = sorted(_event_temp_switches(event_json))
    for letter in ss:
        lines.append(f" self-switch {letter}:  FLAG_MAP{map_id:03d}_EVENT{ev_id:03d}_SS{letter}")
    for key in ts:
        lines.append(f" temp-switch {key}:  FLAG_MAP{map_id:03d}_EVENT{ev_id:03d}_TS{key}")
    return _wrap("\n".join(lines))


def _filter_ref(quickref: str, term: str) -> str:
    """The quick-reference, optionally filtered to lines matching `term`.

    `?` (empty term) returns the whole sheet; `?choice` / `?111` / `?item` return just
    the matching lines so a phone screen isn't flooded. Match is case-insensitive
    substring over each line."""
    if not quickref.strip():
        return "(no quick-reference loaded)"
    if not term:
        return _wrap(quickref)
    low = term.lower()
    lines = quickref.split("\n")
    # Search only the reference BODY (from the first `## ` section), so the intro blurb —
    # which names `?111`/`?item` as examples — doesn't match every query.
    start = next((i for i, ln in enumerate(lines) if ln.startswith("## ")), 0)
    hits = [ln for ln in lines[start:] if low in ln.lower()]
    if not hits:
        return f"(no quickref line matches {term!r} — type ? for all)"
    return _wrap("\n".join(hits))


def _wrap(text: str, width: int = _WIDTH) -> str:
    """Hard-wrap each line to `width` cols so a phone terminal never soft-wraps.

    Wraps on word boundaries with a hanging indent that preserves the line's own
    leading whitespace; never splits a long unbreakable token (e.g. a flag name) or a
    hyphenated word, so identifiers the operator must copy stay on one piece."""
    out: list[str] = []
    for line in text.split("\n"):
        if len(line) <= width:
            out.append(line)
            continue
        lead = " " * (len(line) - len(line.lstrip()))
        wrapped = textwrap.wrap(
            line,
            width=width,
            subsequent_indent=lead + "  ",
            break_long_words=False,
            break_on_hyphens=False,
        )
        out.extend(wrapped or [line])
    return "\n".join(out)


_TRIGGERS = {0: "action", 1: "player touch", 2: "event touch", 3: "autorun", 4: "parallel"}


def _render_command(cmd: dict) -> str:
    """One decoded command line: indent + code label + a compact parameter preview."""
    code = cmd.get("code", 0)
    label = _CODE_LABELS.get(code, f"code {code}")
    indent = "  " * cmd.get("indent", 0)
    params = cmd.get("parameters", [])
    preview = ""
    if code in (101, 401):
        text = params[0] if params and isinstance(params[0], str) else ""
        preview = f': "{text}"'
    elif params:
        # Truncate so an unlabeled command with a big nested param (a move-route /
        # audio object) can't spill a wall of JSON — these are off-lane anyway.
        raw = repr(params)
        preview = ": " + (raw[:57] + "…" if len(raw) > 58 else raw)
    return f"{indent}{code:>3} {label}{preview}"


def _page_condition_summary(page: dict) -> str:
    """Short human description of a page's activation condition (what gates it)."""
    cond = page.get("condition", {})
    parts: list[str] = []
    if cond.get("self_switch_valid"):
        parts.append(f"self-switch {cond.get('self_switch_ch', '?')} is on")
    if cond.get("switch1_valid"):
        parts.append(f"global switch {cond.get('switch1_id')} is on")
    if cond.get("switch2_valid"):
        parts.append(f"global switch {cond.get('switch2_id')} is on")
    if cond.get("variable_valid"):
        parts.append(f"VAR {cond.get('variable_id')} >= {cond.get('variable_value')}")
    return ", ".join(parts)


def _help_text() -> str:
    return (
        "─" * _WIDTH
        + f"\n Write Poryscript. Submit: {_END_SENTINEL}"
        + "\n :undo drop line   :clear restart"
        + "\n ? refs   ?x search   opus punt   q quit"
        + "\n" + "─" * _WIDTH
    )


def _scrape_unhandled(script: str, event_json: dict) -> list[dict]:
    """Turn any ``# UNHANDLED: reason`` lines the operator left into queue entries."""
    out: list[dict] = []
    for m in _UNHANDLED_RE.finditer(script):
        out.append(
            {
                "command_code": None,
                "description": m.group(1).strip(),
                "event_id": event_json.get("id"),
                "page": None,
                "line": None,
            }
        )
    return out
