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

import hashlib
import json
import logging
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from rpg2gba.conversion_agent import deterministic, poryscript, prompt_builder
from rpg2gba.conversion_agent.backends import (
    BackendTransportError,
    BudgetReached,
    ConversionBackend,
    ConversionResult,
    RateLimitError,
)
from rpg2gba.conversion_agent.flag_registry import (
    FlagRegistry,
    RegistryError,
    self_switch_flag_name,
    temp_switch_flag_name,
)

logger = logging.getLogger(__name__)

CompileFn = Callable[[str], poryscript.CompileResult]


@dataclass
class MemoEntry:
    """One accepted conversion, reusable for a structurally identical event (dedup C).

    ``src_map`` / ``src_event`` are the identity of the event this script was first
    generated for; they let ``_reinstantiate`` rewrite the deterministic self/temp-switch
    flag names to a new map/event on reuse."""

    script: str
    src_map: int
    src_event: int
    new_flags: list[dict] = field(default_factory=list)
    new_vars: list[dict] = field(default_factory=list)
    unhandled: list[dict] = field(default_factory=list)


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
        # The command-code reference is sliced per event into the user prompt. The
        # event-invariant context (cheatsheet, script-call reference, few-shots) now
        # rides in the backend's system prompt (dedup Phase B) — composed once in
        # pipeline._phase4_backend — so it is not loaded or assembled here.
        self._command_ref = prompt_builder.load_command_reference(reference_dir)
        # Deterministic pre-filter lookup tables (item-ball / trainer classifiers).
        # Empty if the Phase-2 intermediates aren't present — those classifiers then
        # simply fall through; the dialogue/warp classifiers need no data.
        self._det_context = deterministic.load_context(
            reference_dir=Path(reference_dir), intermediate_dir=self.output_dir / "intermediate"
        )
        # Event memo (dedup C): structurally identical events reuse a prior conversion
        # instead of re-spawning. Persisted + fingerprinted by the system prompt so it
        # survives across runs but is discarded if the prompt changed.
        self.memo_path = self.output_dir / "memo_manifest.json"
        self._memo: dict[str, MemoEntry] = {}
        self._load_memo()

    # -- public -----------------------------------------------------------

    def convert_all(self, map_dir: Path) -> int:
        """Convert every MapNNN.json in `map_dir`. Returns the count processed."""
        maps = sorted(Path(map_dir).glob("Map*.json"))
        if not maps:
            raise FileNotFoundError(f"no MapNNN.json under {map_dir}")
        total = len(maps)
        done = sum(1 for p in maps if self._checkpoint(p.stem).exists())
        logger.info("maps: %d total, %d already converted — %d to go", total, done, total - done)
        n = 0
        for i, path in enumerate(maps, start=1):
            logger.info("[map %d/%d] %s", i, total, path.stem)
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
        n_events = len(m["events"])
        logger.info("=== %s: starting (%d events) ===", stem, n_events)
        # (Re-)converting this map re-logs its queue entries; drop the stale ones
        # first so resume/regen replaces rather than duplicates them (§4.2).
        self._prune_unhandled(map_id=map_id)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        out_pory = self.scripts_dir / f"{stem}.pory"
        out_pory.write_text("", encoding="utf-8")  # exists even if every event is skipped
        blocks: list[str] = []
        seen_labels: set[str] = set()
        for event in m["events"]:
            # Decorative/graphic-only events (no real commands) produce no script —
            # skip them without spawning the backend (saves budget across the corpus).
            if not _event_has_commands(event):
                logger.debug("%s event %s: no commands, skipping", stem, event.get("id"))
                continue
            script = self._convert_event(map_id, event)
            if script is not None:
                # Invariant (F1): every accepted script's labels are unique within the
                # map. _qualify_labels guarantees this by construction; a violation
                # means the qualification missed a path — abort loud rather than emit
                # a duplicate symbol the compile-gate can't see.
                labels = _script_labels(script)
                dup = labels & seen_labels
                if dup:
                    raise RuntimeError(
                        f"{stem} ev{event.get('id')}: duplicate script label(s) "
                        f"{sorted(dup)} — label qualification failed"
                    )
                seen_labels |= labels
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

        **Per-CE resumability:** unlike map events, common events are NOT memoized, so a
        run that aborts mid-pass (usage cap or ``--limit``) would otherwise re-spend every
        CE it had already converted on the next invocation — and since the ``.done``
        checkpoint is only written after the *whole* pass, a near-cap budget could loop
        forever re-doing the same CEs and never reach the maps. To prevent that, each CE we
        process is recorded in ``checkpoints/CommonEvents.blocks.json`` (its emitted script,
        or ``null`` if it was fully queued); a restart skips those and rebuilds the .pory
        from them, so bounded/interrupted rounds accumulate. The ``only_ids`` debug path is
        partial and intentionally stateless.
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

        use_progress = only_ids is None
        progress_path = self.checkpoint_dir / f"{stem}.blocks.json"
        done: dict[str, str | None] = {}
        if use_progress and progress_path.is_file():
            try:
                done = json.loads(progress_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                done = {}

        def _flush_pory() -> None:
            blocks = [done[str(ce.get("id"))] for ce in ces if done.get(str(ce.get("id")))]
            out_pory.write_text(
                ("\n\n".join(blocks) + "\n") if blocks else "", encoding="utf-8"
            )

        _flush_pory()  # exists even if every CE is skipped; reflects any prior progress

        # Only common events with real commands ever spawn; pre-filter so the heartbeat
        # below can show a true "N/total" against the work that actually costs budget.
        eligible = [ce for ce in ces if _event_has_commands(_common_event_payload(ce))]
        remaining = [
            ce for ce in eligible if not (use_progress and str(ce.get("id")) in done)
        ]
        logger.info(
            "%s: %d common events with commands, %d already done — converting %d this run",
            stem,
            len(eligible),
            len(eligible) - len(remaining),
            len(remaining),
        )
        n_processed = 0
        for idx, ce in enumerate(remaining, start=1):
            cid = str(ce.get("id"))
            payload = _common_event_payload(ce)
            n_processed += 1
            # Same §4.2 replace-don't-accumulate rule as convert_map: this CE is
            # about to re-log its queue entries (ledger-dropped or only_ids re-run).
            self._prune_unhandled(common_event_id=ce.get("id"))
            logger.info(
                "[CE %d/%d] CommonEvent %s (%s): converting…",
                idx,
                len(remaining),
                ce.get("id"),
                ce.get("name", ""),
            )
            script = self._convert_common_event(payload)  # may raise → abort (resumable)
            done[cid] = script
            if use_progress:
                self._save_ce_progress(progress_path, done)
            _flush_pory()
            self.registry.save(self.registry_state_path)
            logger.info(
                "[CE %d/%d] CommonEvent %s: %s",
                idx,
                len(remaining),
                ce.get("id"),
                "emitted" if script else "queued (unhandled)",
            )

        if only_ids is None:
            self._checkpoint(stem).parent.mkdir(parents=True, exist_ok=True)
            self._checkpoint(stem).write_text("ok\n", encoding="utf-8")
        emitted = sum(1 for v in done.values() if v)
        logger.info(
            "%s: %d processed this run, %d emitted total", stem, n_processed, emitted
        )

    def _save_ce_progress(self, path: Path, done: dict[str, str | None]) -> None:
        """Persist the per-common-event progress ledger (id → script-or-null)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(done, ensure_ascii=False) + "\n", encoding="utf-8")

    # -- per-event --------------------------------------------------------

    def _convert(
        self,
        payload: dict,
        ctx: dict,
        *,
        transform: Callable[[str], str] | None = None,
    ) -> ConversionResult | None:
        """Shared convert core: prompt → backend → commit → compile-gate → retry-once.

        Returns the accepted ``ConversionResult`` (script compiled), or ``None`` if the
        item was queued. The caller handles what differs between map events and common
        events: self/temp-switch minting and unhandled-command logging. ``ctx`` is the
        queue context (identifies the item in ``unhandled.jsonl``). ``transform`` is an
        optional deterministic script rewrite (label qualification, F1) applied to every
        backend result *before* the compile-gate, so what is gated, memoized, and emitted
        are the same text."""
        prompt = self._build_prompt(payload)
        try:
            result = self.backend.convert_event(payload, self._registry_state(), prompt)
        except (RateLimitError, BackendTransportError, BudgetReached):
            # Usage cap / transport failure / self-imposed --limit — the event is fine,
            # we just can't (or won't) spend right now. Abort the run (resumable) instead
            # of queuing good work as a permanent failure. The bulk runner decides what to
            # do next (pause, stop, or clean exit).
            raise
        except Exception as exc:  # backend/parse failure — queue, don't abort the run
            self._queue(ctx, reason=f"backend error: {exc}")
            return None

        if not self._commit_proposals(ctx, result):
            return None
        if transform is not None:
            result = replace(result, script=transform(result.script))

        compiled = self.compile_fn(result.script)
        if not compiled.ok:
            retry_prompt = self._retry_prompt(prompt, compiled.stderr)
            try:
                result = self.backend.convert_event(payload, self._registry_state(), retry_prompt)
            except (RateLimitError, BackendTransportError, BudgetReached):
                raise
            except Exception as exc:
                self._queue(ctx, reason=f"backend error on retry: {exc}")
                return None
            if not self._commit_proposals(ctx, result):
                return None
            if transform is not None:
                result = replace(result, script=transform(result.script))
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

        # Deterministic pre-filter (PHASE4_DETERMINISTIC_PLAN): fully-mechanical events
        # are translated by lookup, not by an LLM spawn. Fail-safe — a non-match or a
        # compile-gate failure returns None and falls through to the memo/LLM path below.
        det = self._try_deterministic(map_id, event, ctx)
        if det is not None:
            return det

        # Memo (dedup C): if a structurally identical event was already converted, reuse
        # its script instead of spawning. Any doubt (stale-token guard or compile-gate
        # failure) falls through to a real spawn below — the memo never relaxes a check.
        key = _memo_key(payload)
        entry = self._memo.get(key)
        if entry is not None:
            reused = self._try_reuse_memo(map_id, event, ctx, entry)
            if reused is not None:
                return reused

        logger.info(
            "--- ev%s (%s): converting ---", event.get("id"), event.get("name", "")
        )
        result = self._convert(
            payload,
            ctx,
            transform=lambda s: _qualify_labels(s, map_id, int(event["id"])),
        )
        if result is None:
            return None
        if not self._mint_event_switches(map_id, event, ctx):
            return None
        self._log_unhandled(ctx, result.unhandled)
        self._store_memo(key, map_id, event, result)
        logger.info("ev%s accepted:\n%s", event.get("id"), result.script)
        return result.script

    def _try_deterministic(self, map_id: int, event: dict, ctx: dict) -> str | None:
        """Translate a fully-mechanical event without an LLM spawn; None to fall through.

        Mirrors the accept path of ``_convert_event``: the candidate must pass the
        compile-gate and the self/temp-switch mint, exactly as an LLM result would, so
        a deterministic miss is indistinguishable downstream from an LLM conversion.
        A classifier may also carry queue entries (e.g. a warp's MAP_URANIUM_<N>
        placeholder that Phase 5 must resolve); these are logged to unhandled.jsonl
        exactly as an LLM result's would be. Any failure returns None and the caller
        proceeds to the memo/LLM path."""
        match = deterministic.try_deterministic(map_id, event, self._det_context)
        if match is None:
            return None
        script = _qualify_labels(match.script, map_id, int(event["id"]))
        if not self.compile_fn(script).ok:
            logger.debug(
                "ev%s deterministic output failed compile-gate — falling through",
                event.get("id"),
            )
            return None
        if not self._mint_event_switches(map_id, event, ctx):
            return None
        self._log_unhandled(ctx, match.unhandled)
        self._store_memo(
            _memo_key({"map_id": map_id, **event}),
            map_id,
            event,
            ConversionResult(script=script, unhandled=match.unhandled),
        )
        logger.info("ev%s deterministic:\n%s", event.get("id"), script)
        return script

    def _convert_common_event(self, payload: dict) -> str | None:
        """Convert one common event (already adapted to page-shape); None if queued.

        Common events have no per-event self/temp-switches, so the mint loops are
        skipped (Phase 4 dedup A); they are also not memoized (a fixed set of ~22)."""
        ctx = {"common_event_id": payload["common_event_id"], "event_name": payload.get("name")}
        result = self._convert(payload, ctx)
        if result is None:
            return None
        self._log_unhandled(ctx, result.unhandled)
        return result.script

    def _mint_event_switches(self, map_id: int, event: dict, ctx: dict) -> bool:
        """Mint the per-event self/temp-switch flags the accepted script relies on.

        The agent emits FLAG_MAP..SS*/..TS* names (system.md) but never proposes them,
        and the registry can't mint them itself — without this they are undefined symbols
        at assembly. Deterministic + idempotent; a mint failure would leave a dangling
        symbol, so fail loud and queue (returns False). Self-switches (code 123) are
        saved; Uranium temp-switches (setTempSwitchOn, code 355/655) come from the
        auto-reset TEMP range — distinct idioms, see prompts/system.md."""
        for letter in sorted(_event_self_switches(event)):
            try:
                self.registry.mint_self_switch(map_id, event["id"], letter)
            except RegistryError as exc:
                self._queue(ctx, reason=f"self-switch mint failed: {exc}")
                return False
        for key in sorted(_event_temp_switches(event)):
            try:
                self.registry.mint_temp_switch(map_id, event["id"], key)
            except RegistryError as exc:
                self._queue(ctx, reason=f"temp-switch mint failed: {exc}")
                return False
        return True

    def _log_unhandled(self, ctx: dict, unhandled: list[dict]) -> None:
        for u in unhandled:
            self._queue(ctx, reason="agent-flagged unhandled", extra=u)

    # -- memo (dedup C) ----------------------------------------------------

    def _try_reuse_memo(self, map_id: int, event: dict, ctx: dict, entry: MemoEntry) -> str | None:
        """Reuse a memoized conversion for a structurally identical event.

        Returns the re-instantiated script on success, or None to fall through to a real
        spawn (fail-safe). The script's deterministic self/temp-switch flag names are the
        only map/event-derived tokens, so rewriting them to the current map/event yields
        a correct reuse; the stale-token guard + compile-gate catch any divergence before
        acceptance, and the registry proposals/mints are replayed for the current event."""
        script = self._reinstantiate(entry, map_id, event)
        if script is None:  # stale-token guard failed
            return None
        # Qualify for the CURRENT event (F1). New-format entries arrive already
        # qualified (no-op); entries stored before the label fix arrive name-only and
        # gain the EV tag here, so old memo manifests replay correctly.
        script = _qualify_labels(script, map_id, int(event["id"]))
        if not self.compile_fn(script).ok:  # reused script must still compile
            logger.debug("memo hit failed compile-gate; re-spawning %s", ctx)
            return None
        # Validated. Replay the entry's proposals (idempotent — same global ids/names) and
        # this event's switch mints so the registry stays correct, then log its unhandled.
        if not self._commit_proposals(ctx, _entry_result(entry)):
            return None
        if not self._mint_event_switches(map_id, event, ctx):
            return None
        self._log_unhandled(ctx, entry.unhandled)
        logger.info(
            "ev%s memo hit (reused map%s ev%s):\n%s",
            event.get("id"),
            entry.src_map,
            entry.src_event,
            script,
        )
        return script

    @staticmethod
    def _reinstantiate(entry: MemoEntry, cur_map: int, event: dict) -> str | None:
        """Rewrite the source event's map/event-derived tokens to the current map/event.

        Two token families carry the source identity: the deterministic self/temp-switch
        flag names (``FLAG_MAP{m}_EVENT{e}_SS*``/``_TS*``), and the script-block **labels**.
        Labels come in two formats: post-F1 entries are EV-qualified
        (``Map{m}_EV{e}_<name>_Page<n>``) and rewrite whenever the (map, event) identity
        differs — *including same-map reuse between two copy-paste events, the case F1
        exists for*; pre-F1 entries are name-only (``Map{m}_<name>_Page<n>``) and keep the
        legacy cross-map prefix rewrite, with the caller's ``_qualify_labels`` adding the
        EV tag afterwards. The flag-name and label rewrites don't collide (``FLAG_MAP…``
        is upper-case, the label prefix ``Map…`` is mixed-case, so the case-sensitive
        replaces are disjoint).

        Returns the rewritten script, or None if any source-identity token survives the
        rewrite (stale-token guard → caller re-spawns). The guard only applies when the
        identities differ: a same-(map, event) replay — the regen/checkpoint-recovery
        case — keeps its own flag tokens by construction. The label-prefix rewrite is
        essential: poryscript validates each file in isolation, so a stale source label
        compiles fine but collides / dangles at assembly when the maps are linked."""
        cur_event = int(event["id"])
        script = entry.script
        for letter in _event_self_switches(event):
            src = self_switch_flag_name(entry.src_map, entry.src_event, letter)
            script = script.replace(src, self_switch_flag_name(cur_map, cur_event, letter))
        for k in _event_temp_switches(event):
            src = temp_switch_flag_name(entry.src_map, entry.src_event, k)
            script = script.replace(src, temp_switch_flag_name(cur_map, cur_event, k))
        same_identity = (entry.src_map, entry.src_event) == (cur_map, cur_event)
        if (
            not same_identity
            and f"FLAG_MAP{entry.src_map:03d}_EVENT{entry.src_event:03d}_" in script
        ):
            return None  # a source token the per-key rewrite missed — bail to a real spawn
        src_qualified = f"Map{entry.src_map:03d}_EV{entry.src_event:03d}_"
        if not same_identity:
            script = script.replace(
                src_qualified, f"Map{cur_map:03d}_EV{cur_event:03d}_"
            )
            if src_qualified in script:
                return None  # a source-identity label token survived — bail to a real spawn
        if entry.src_map != cur_map:
            script = script.replace(f"Map{entry.src_map:03d}_", f"Map{cur_map:03d}_")
            if f"Map{entry.src_map:03d}_" in script:
                return None  # a source-map label token survived — bail to a real spawn
        return script

    def _store_memo(self, key: str, map_id: int, event: dict, result: ConversionResult) -> None:
        self._memo[key] = MemoEntry(
            script=result.script,
            src_map=int(map_id),
            src_event=int(event["id"]),
            new_flags=result.new_flags,
            new_vars=result.new_vars,
            unhandled=result.unhandled,
        )
        self._save_memo()

    def _prompt_fingerprint(self) -> str:
        """12-hex digest of the backend's system prompt (system.md + static context).

        The memo manifest is keyed to this so outputs produced under one prompt are never
        reused under a different one (dedup C)."""
        sp = getattr(self.backend, "system_prompt", "") or ""
        return hashlib.sha256(sp.encode("utf-8")).hexdigest()[:12]

    def _save_memo(self) -> None:
        payload = {
            "prompt_fingerprint": self._prompt_fingerprint(),
            "entries": {
                k: {
                    "script": e.script,
                    "src_map": e.src_map,
                    "src_event": e.src_event,
                    "new_flags": e.new_flags,
                    "new_vars": e.new_vars,
                    "unhandled": e.unhandled,
                }
                for k, e in self._memo.items()
            },
        }
        self.memo_path.parent.mkdir(parents=True, exist_ok=True)
        self.memo_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def _load_memo(self) -> None:
        self._memo = {}
        if not self.memo_path.is_file():
            return
        try:
            data = json.loads(self.memo_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("memo manifest %s unreadable — ignoring", self.memo_path)
            return
        if data.get("prompt_fingerprint") != self._prompt_fingerprint():
            logger.info("memo manifest fingerprint mismatch — discarding (prompt changed)")
            return
        for k, e in data.get("entries", {}).items():
            self._memo[k] = MemoEntry(
                script=e["script"],
                src_map=e["src_map"],
                src_event=e["src_event"],
                new_flags=e.get("new_flags", []),
                new_vars=e.get("new_vars", []),
                unhandled=e.get("unhandled", []),
            )

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
        return prompt_builder.build_user_prompt(
            payload,
            self._registry_state(),
            command_ref=prompt_builder.filter_command_reference(
                self._command_ref, _event_codes(payload)
            ),
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
        # ctx (the artifact being converted NOW) must win over extra: a memo-reused
        # event replays the SOURCE conversion's unhandled[] items, whose embedded
        # event_id/event_name identify the source event — left to overwrite ctx they
        # mint phantom queue refs (seen live: map5's "Map" events logged as the
        # nonexistent map5 ev6, the memo source's id). extra still supplies the
        # command detail (command_code/page/line/description).
        entry = {**(extra or {}), **ctx, "reason": reason}
        logger.info("QUEUED %s — %s", ctx, reason)
        self.unhandled_path.parent.mkdir(parents=True, exist_ok=True)
        with self.unhandled_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _prune_unhandled(
        self, *, map_id: int | None = None, common_event_id: int | None = None
    ) -> None:
        """Drop a map's (or CE's) stale entries from unhandled.jsonl before re-converting.

        The queue is append-only at event level, so re-converting an artifact —
        interrupt-resume of an unfinished map, or a targeted regen — would duplicate
        every entry it re-logs (idempotence, CLAUDE.md §4.2). Pruning the artifact's
        old entries first makes re-conversion replace rather than accumulate. Exactly
        one selector must be given; map entries carry no ``common_event_id`` key and
        CE entries always do, so the filters cannot cross-match."""
        if not self.unhandled_path.is_file():
            return
        kept: list[str] = []
        dropped = 0
        for line in self.unhandled_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                kept.append(line)  # not ours to judge — leave malformed lines alone
                continue
            if map_id is not None and "common_event_id" not in entry:
                match = entry.get("map_id") == map_id
            elif common_event_id is not None:
                match = entry.get("common_event_id") == common_event_id
            else:
                match = False
            if match:
                dropped += 1
            else:
                kept.append(line)
        if dropped:
            self.unhandled_path.write_text(
                ("\n".join(kept) + "\n") if kept else "", encoding="utf-8"
            )
            logger.info(
                "pruned %d stale unhandled entr%s for %s",
                dropped,
                "y" if dropped == 1 else "ies",
                f"map {map_id}" if map_id is not None else f"CE {common_event_id}",
            )


def _qualify_labels(script: str, map_id: int, event_id: int) -> str:
    """Make a map event's script labels unique per event (F1 label-collision fix).

    The agent (and the deterministic classifiers, historically) derive labels from the
    event *name* (``Map{NNN}_{name}_Page{n}``), but RMXP names repeat freely — 103/199
    maps have same-named command-bearing events, so name-derived labels collide at
    assembly (duplicate symbols the per-event compile-gate can't see). Qualify every
    ``Map{NNN}_`` label token with the event id: ``Map{NNN}_EV{eee}_…``. Plain string
    rewrite, so definitions and goto references move together (the technique
    ``_reinstantiate`` proved); case-sensitive, so the upper-case ``FLAG_MAP…`` flag
    names are untouched.

    Idempotent: a token already qualified with *this* event's id is left alone — which
    also keeps default-named events (name ``EV011`` on event 11) at their natural
    ``Map002_EV011_Page1`` rather than ``Map002_EV011_EV011_Page1``."""
    prefix = f"Map{int(map_id):03d}_"
    tag = f"EV{int(event_id):03d}_"
    pattern = re.compile(re.escape(prefix) + f"(?!{re.escape(tag)})")
    return pattern.sub(prefix + tag, script)


_SCRIPT_LABEL_RE = re.compile(r"^\s*script\s+(\w+)", re.MULTILINE)


def _script_labels(script: str) -> set[str]:
    """The ``script <label>`` block names defined in a Poryscript fragment."""
    return set(_SCRIPT_LABEL_RE.findall(script))


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


def _memo_key(payload: dict) -> str:
    """Stable content hash of an event with its map/event identity removed (dedup C).

    Normalizes out **only** ``map_id`` and the event's own ``id`` — name, dialogue, and
    all command content stay in the key — so two copy-pasted events that differ only by
    where they live collapse to one key, while anything that could change the script keeps
    them distinct. The map/event-derived tokens in a stored script are the deterministic
    self/temp-switch flag names and the EV-qualified ``Map{m}_EV{e}_`` label prefixes
    (F1); ``_reinstantiate`` rewrites both exactly on reuse."""
    content = {k: v for k, v in payload.items() if k not in ("map_id", "id")}
    blob = json.dumps(content, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _entry_result(entry: MemoEntry) -> ConversionResult:
    """A ConversionResult view of a memo entry, for replaying proposals on reuse."""
    return ConversionResult(
        script=entry.script,
        new_flags=entry.new_flags,
        new_vars=entry.new_vars,
        unhandled=entry.unhandled,
    )


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
