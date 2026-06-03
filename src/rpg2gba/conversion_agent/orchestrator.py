"""Orchestrator — drives the per-event conversion loop (Phase 4 §4.5).

For each map JSON, for each event:
  1. Skip the map if its checkpoint says done + validated
  2. Build the per-event prompt (registry state + cheatsheet + few-shots + event)
  3. Call the configured backend → ConversionResult
  4. Commit any new flag/var proposals through the registry (validation gate)
  5. Compile the Poryscript immediately
  6. On compile failure: retry once with the compiler error appended
  7. On success: accumulate the event's script; on second failure or bad
     proposals: append to output/unhandled.jsonl and move on
  8. After the map: write MapNNN.pory, the checkpoint, and the registry state

Idempotent + resumable (F3): a completed map is skipped on re-run; partial
output never corrupts registry state (saved after each map).

`compile_fn` is injectable so tests exercise the loop with a fake compiler and a
MockBackend, never the real `poryscript`/`claude` binaries (F7).
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from rpg2gba.conversion_agent import poryscript, prompt_builder
from rpg2gba.conversion_agent.backends import ConversionBackend, ConversionResult
from rpg2gba.conversion_agent.flag_registry import FlagRegistry, RegistryError

logger = logging.getLogger(__name__)

CompileFn = Callable[[str], poryscript.CompileResult]


class Orchestrator:
    def __init__(
        self,
        backend: ConversionBackend,
        registry: FlagRegistry,
        output_dir: Path,
        *,
        reference_dir: Path = Path("reference"),
        compile_fn: CompileFn | None = None,
    ) -> None:
        self.backend = backend
        self.registry = registry
        self.output_dir = Path(output_dir)
        self.scripts_dir = self.output_dir / "scripts"
        self.checkpoint_dir = self.output_dir / "checkpoints"
        self.unhandled_path = self.output_dir / "unhandled.jsonl"
        self.registry_state_path = self.output_dir / "flag_state.json"
        self.compile_fn = compile_fn or poryscript.compile_script
        # Stable prompt chunks, loaded once.
        self._few_shots = prompt_builder.load_few_shots()
        self._cheatsheet = prompt_builder.load_cheatsheet(reference_dir)
        self._command_ref = prompt_builder.load_command_reference(reference_dir)
        self._script_call_ref = prompt_builder.load_script_call_reference(reference_dir)

    # -- public -----------------------------------------------------------

    def convert_all(self, map_dir: Path) -> int:
        """Convert every MapNNN.json in `map_dir`. Returns the count processed."""
        maps = sorted(Path(map_dir).glob("Map*.json"))
        if not maps:
            raise FileNotFoundError(f"no MapNNN.json under {map_dir}")
        n = 0
        for path in maps:
            self.convert_map(path)
            n += 1
        return n

    def convert_map(self, map_json_path: Path) -> None:
        map_json_path = Path(map_json_path)
        stem = map_json_path.stem  # "Map042"
        if self._checkpoint(stem).exists():
            logger.debug("%s already converted — skipping", stem)
            return

        m = json.loads(map_json_path.read_text(encoding="utf-8"))
        map_id = m["map_id"]
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        out_pory = self.scripts_dir / f"{stem}.pory"
        out_pory.write_text("", encoding="utf-8")  # exists even if every event is skipped
        blocks: list[str] = []
        for event in m["events"]:
            # Decorative/graphic-only events (no real commands) produce no script —
            # skip them without spawning the backend (saves budget across the corpus).
            if not _event_has_commands(event):
                logger.debug("%s event %s: no commands, skipping", stem, event.get("id"))
                continue
            script = self._convert_event(map_id, event)
            if script is not None:
                blocks.append(script)
            # Flush after every event so a mid-map stop never loses accepted work
            # (per-event LLM calls are slow + interruptible — ROADMAP §4.5).
            out_pory.write_text(("\n\n".join(blocks) + "\n") if blocks else "", encoding="utf-8")
            self.registry.save(self.registry_state_path)

        self._checkpoint(stem).parent.mkdir(parents=True, exist_ok=True)
        self._checkpoint(stem).write_text("ok\n", encoding="utf-8")
        logger.info("%s: %d/%d events converted", stem, len(blocks), len(m["events"]))

    def convert_common_events(
        self, common_events_path: Path, *, only_ids: set[int] | None = None
    ) -> None:
        """Convert every common event once → scripts/CommonEvents.pory (Phase 4 dedup A).

        Maps emit ``call CommonEvent_<NNN>`` for Call Common Event (117), but the
        per-map loop only sees ``Map*.json`` — nothing produces those targets, so
        every call is a dangling symbol at assembly. This pass converts the common
        events the calls point at. Each common event is a *flat* ``list`` (no
        ``pages``); we adapt it to the one-page shape the helpers expect, mark it with
        ``common_event_id`` so the agent emits a single ``CommonEvent_<NNN>`` block,
        and reuse the same convert core as map events — but with **no** self/temp-switch
        minting (common events use only global switches/vars).

        Idempotent like ``convert_map``: a ``CommonEvents.done`` checkpoint skips the
        whole pass on re-run. ``only_ids`` restricts the pass to specific ids for cheap
        single-shot iteration and intentionally does **not** write the checkpoint (it is
        a partial, debug-only run).
        """
        common_events_path = Path(common_events_path)
        stem = "CommonEvents"
        if only_ids is None and self._checkpoint(stem).exists():
            logger.debug("%s already converted — skipping", stem)
            return

        ces = json.loads(common_events_path.read_text(encoding="utf-8"))
        if only_ids is not None:
            ces = [ce for ce in ces if ce.get("id") in only_ids]
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        out_pory = self.scripts_dir / f"{stem}.pory"
        out_pory.write_text("", encoding="utf-8")  # exists even if every CE is skipped
        blocks: list[str] = []
        n_with_cmds = 0
        for ce in ces:
            payload = _common_event_payload(ce)
            # Decorative/empty common events produce no script — skip without spawning.
            if not _event_has_commands(payload):
                logger.debug("CommonEvent %s: no commands, skipping", ce.get("id"))
                continue
            n_with_cmds += 1
            script = self._convert_common_event(payload)
            if script is not None:
                blocks.append(script)
            out_pory.write_text(("\n\n".join(blocks) + "\n") if blocks else "", encoding="utf-8")
            self.registry.save(self.registry_state_path)

        if only_ids is None:
            self._checkpoint(stem).parent.mkdir(parents=True, exist_ok=True)
            self._checkpoint(stem).write_text("ok\n", encoding="utf-8")
        logger.info("%s: %d/%d common events converted", stem, len(blocks), n_with_cmds)

    # -- per-event --------------------------------------------------------

    def _convert(self, payload: dict, ctx: dict) -> ConversionResult | None:
        """Shared convert core: prompt → backend → commit → compile-gate → retry-once.

        Returns the accepted ``ConversionResult`` (script compiled), or ``None`` if the
        item was queued. The caller handles what differs between map events and common
        events: self/temp-switch minting and unhandled-command logging. ``ctx`` is the
        queue context (identifies the item in ``unhandled.jsonl``)."""
        prompt = self._build_prompt(payload)
        try:
            result = self.backend.convert_event(payload, self._registry_state(), prompt)
        except Exception as exc:  # backend/parse failure — queue, don't abort the run
            self._queue(ctx, reason=f"backend error: {exc}")
            return None

        if not self._commit_proposals(ctx, result):
            return None

        compiled = self.compile_fn(result.script)
        if not compiled.ok:
            retry_prompt = self._retry_prompt(prompt, compiled.stderr)
            try:
                result = self.backend.convert_event(payload, self._registry_state(), retry_prompt)
            except Exception as exc:
                self._queue(ctx, reason=f"backend error on retry: {exc}")
                return None
            if not self._commit_proposals(ctx, result):
                return None
            compiled = self.compile_fn(result.script)
            if not compiled.ok:
                err = compiled.stderr.strip()
                self._queue(ctx, reason=f"compile failed twice: {err}")
                return None
        return result

    def _convert_event(self, map_id: int, event: dict) -> str | None:
        """Convert one map event; return its Poryscript, or None if it was queued."""
        payload = {"map_id": map_id, **event}
        ctx = self._event_ctx(map_id, event)
        result = self._convert(payload, ctx)
        if result is None:
            return None

        # Script accepted. Register any per-event self-switch flags it relies on so
        # dump_header defines them: the agent emits FLAG_MAP..SS* names (system.md)
        # but never proposes them, and the registry can't mint them itself — without
        # this they're undefined symbols at assembly. Deterministic + idempotent; a
        # mint failure would leave a dangling symbol, so fail loud and queue.
        for letter in sorted(_event_self_switches(event)):
            try:
                self.registry.mint_self_switch(map_id, event["id"], letter)
            except RegistryError as exc:
                self._queue(ctx, reason=f"self-switch mint failed: {exc}")
                return None

        # Same for Uranium temp-switches (setTempSwitchOn, code 355): the agent emits
        # FLAG_MAP..TS* and the orchestrator mints it from the auto-reset TEMP range.
        # These are distinct from self-switches (per-map-visit, not saved) — see
        # _event_temp_switches and prompts/system.md.
        for key in sorted(_event_temp_switches(event)):
            try:
                self.registry.mint_temp_switch(map_id, event["id"], key)
            except RegistryError as exc:
                self._queue(ctx, reason=f"temp-switch mint failed: {exc}")
                return None

        # Any agent-flagged unhandled commands are still logged.
        for u in result.unhandled:
            self._queue(ctx, reason="agent-flagged unhandled", extra=u)
        return result.script

    def _convert_common_event(self, payload: dict) -> str | None:
        """Convert one common event (already adapted to page-shape); None if queued.

        Common events have no per-event self/temp-switches, so the mint loops are
        skipped (Phase 4 dedup A)."""
        ctx = {"common_event_id": payload["common_event_id"], "event_name": payload.get("name")}
        result = self._convert(payload, ctx)
        if result is None:
            return None
        for u in result.unhandled:
            self._queue(ctx, reason="agent-flagged unhandled", extra=u)
        return result.script

    def _commit_proposals(self, ctx: dict, result: ConversionResult) -> bool:
        """Commit flag/var proposals; queue + return False if any is rejected."""
        try:
            for f in result.new_flags:
                self.registry.propose_flag(int(f["switch_id"]), f["name"])
            for v in result.new_vars:
                self.registry.propose_var(int(v["var_id"]), v["name"])
        except (RegistryError, KeyError, ValueError) as exc:
            self._queue(ctx, reason=f"bad flag/var proposal: {exc}")
            return False
        return True

    # -- helpers ----------------------------------------------------------

    def _build_prompt(self, payload: dict) -> str:
        return prompt_builder.build_prompt(
            payload,
            self._registry_state(),
            few_shots=self._few_shots,
            cheatsheet=self._cheatsheet,
            command_ref=prompt_builder.filter_command_reference(
                self._command_ref, _event_codes(payload)
            ),
            script_call_ref=self._script_call_ref,
        )

    @staticmethod
    def _retry_prompt(prompt: str, stderr: str) -> str:
        return (
            prompt
            + "\n\n# Previous attempt failed to compile\n\n"
            + "The Poryscript compiler reported:\n\n```\n"
            + stderr.strip()
            + "\n```\n\nReturn corrected JSON in the same schema."
        )

    def _registry_state(self) -> dict:
        state = self.registry.to_state()
        return {
            "flags": state["switches"],
            "vars": state["variables"],
            "script_switches": state["script_switches"],
        }

    def _checkpoint(self, stem: str) -> Path:
        return self.checkpoint_dir / f"{stem}.done"

    @staticmethod
    def _event_ctx(map_id: int, event: dict) -> dict:
        """Queue context identifying a map event in unhandled.jsonl."""
        return {"map_id": map_id, "event_id": event.get("id"), "event_name": event.get("name")}

    def _queue(self, ctx: dict, *, reason: str, extra: dict | None = None) -> None:
        entry = {**ctx, "reason": reason}
        if extra:
            entry.update(extra)
        self.unhandled_path.parent.mkdir(parents=True, exist_ok=True)
        with self.unhandled_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _event_codes(event: dict) -> set[int]:
    """Every RPG Maker command code used in an event (page lists + move routes)."""
    codes: set[int] = set()
    for page in event.get("pages", []):
        for cmd in page.get("list", []):
            codes.add(cmd["code"])
        mr = page.get("move_route")
        if isinstance(mr, dict):
            for cmd in mr.get("list", []):
                codes.add(cmd["code"])
    return codes


def _event_has_commands(event: dict) -> bool:
    """True if any page has a real command (code != 0). Decorative/graphic-only
    events (empty or all-zero command lists) produce no script, so the orchestrator
    skips them without spawning the backend."""
    for page in event.get("pages", []):
        for cmd in page.get("list", []):
            if cmd.get("code", 0) != 0:
                return True
    return False


def _common_event_payload(ce: dict) -> dict:
    """Adapt a common event (flat ``list``, no ``pages``) into the one-page shape the
    per-event helpers expect, tagged with ``common_event_id`` so the agent emits a
    single ``CommonEvent_<NNN>`` block (prompts/system.md). ``common_events.json`` is a
    list of ``{id, name, trigger, switch_id, list}`` objects (Phase 3 §3.x)."""
    return {
        "common_event_id": ce["id"],
        "name": ce.get("name", ""),
        "pages": [{"list": ce.get("list", []), "condition": {}}],
    }


def _event_self_switches(event: dict) -> set[str]:
    """Self-switch letters an event uses — set via Control Self Switch (code 123)
    or gated on by a page condition (``self_switch_valid``). Each maps to a
    deterministic per-event FLAG_* the registry must mint so the assembler can
    resolve it (the agent emits the name but never proposes it)."""
    letters: set[str] = set()
    for page in event.get("pages", []):
        cond = page.get("condition", {})
        if cond.get("self_switch_valid"):
            ch = cond.get("self_switch_ch")
            if ch:
                letters.add(str(ch).upper())
        for cmd in page.get("list", []):
            if cmd.get("code") == 123:
                params = cmd.get("parameters", [])
                if params and isinstance(params[0], str):
                    letters.add(params[0].upper())
    return letters


# Uranium temp-switch script calls (code 355/655): set/clear and read forms, each
# keyed by a quoted string argument — e.g. setTempSwitchOn("A"), tsOff?("A").
_TEMP_SWITCH_RE = re.compile(
    r"(?:setTempSwitchOn|setTempSwitchOff|tsOn\?|tsOff\?|isTempSwitchOn\?|isTempSwitchOff\?)"
    r"""\(\s*["']([^"']+)["']\s*\)"""
)


def _event_temp_switches(event: dict) -> set[str]:
    """Temp-switch keys an event touches via Uranium's ``setTempSwitchOn`` / ``tsOn?``
    family (RPG Maker Script command, code 355/655). Unlike self-switches (code 123),
    these are per-map-visit runtime state (``Game_Event#@tempSwitches``, rebuilt every
    map load), so they map to pokeemerald auto-reset TEMP flags rather than saved
    self-switches. Each key maps to a deterministic per-event FLAG_* the registry mints
    so the assembler can resolve the name the agent emits (prompts/system.md)."""
    keys: set[str] = set()
    for page in event.get("pages", []):
        for cmd in page.get("list", []):
            if cmd.get("code") in (355, 655):
                params = cmd.get("parameters", [])
                if params and isinstance(params[0], str):
                    for m in _TEMP_SWITCH_RE.finditer(params[0]):
                        keys.add(m.group(1).upper())
    return keys


def triage(queue_path: Path) -> dict[str, int]:
    """Summarize output/unhandled.jsonl by reason (Phase 4 §4.6 review aid)."""
    path = Path(queue_path)
    if not path.is_file():
        return {}
    counts: Counter[str] = Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        counts[json.loads(line).get("reason", "unknown")] += 1
    return dict(counts)
