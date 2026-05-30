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
        blocks: list[str] = []
        for event in m["events"]:
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

    # -- per-event --------------------------------------------------------

    def _convert_event(self, map_id: int, event: dict) -> str | None:
        """Convert one event; return its Poryscript, or None if it was queued."""
        payload = {"map_id": map_id, **event}
        prompt = self._build_prompt(payload)
        try:
            result = self.backend.convert_event(payload, self._registry_state(), prompt)
        except Exception as exc:  # backend/parse failure — queue, don't abort the run
            self._queue(map_id, event, reason=f"backend error: {exc}")
            return None

        if not self._commit_proposals(map_id, event, result):
            return None

        compiled = self.compile_fn(result.script)
        if not compiled.ok:
            retry_prompt = self._retry_prompt(prompt, compiled.stderr)
            try:
                result = self.backend.convert_event(payload, self._registry_state(), retry_prompt)
            except Exception as exc:
                self._queue(map_id, event, reason=f"backend error on retry: {exc}")
                return None
            if not self._commit_proposals(map_id, event, result):
                return None
            compiled = self.compile_fn(result.script)
            if not compiled.ok:
                err = compiled.stderr.strip()
                self._queue(map_id, event, reason=f"compile failed twice: {err}")
                return None

        # Script accepted. Any agent-flagged unhandled commands are still logged.
        for u in result.unhandled:
            self._queue(map_id, event, reason="agent-flagged unhandled", extra=u)
        return result.script

    def _commit_proposals(self, map_id: int, event: dict, result: ConversionResult) -> bool:
        """Commit flag/var proposals; queue + return False if any is rejected."""
        try:
            for f in result.new_flags:
                self.registry.propose_flag(int(f["switch_id"]), f["name"])
            for v in result.new_vars:
                self.registry.propose_var(int(v["var_id"]), v["name"])
        except (RegistryError, KeyError, ValueError) as exc:
            self._queue(map_id, event, reason=f"bad flag/var proposal: {exc}")
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
        return {"flags": state["switches"], "vars": state["variables"]}

    def _checkpoint(self, stem: str) -> Path:
        return self.checkpoint_dir / f"{stem}.done"

    def _queue(self, map_id: int, event: dict, *, reason: str, extra: dict | None = None) -> None:
        entry = {
            "map_id": map_id,
            "event_id": event.get("id"),
            "event_name": event.get("name"),
            "reason": reason,
        }
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
