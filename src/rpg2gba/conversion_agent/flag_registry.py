"""Single source of truth for FLAG_*/VAR_* name assignments (Phase 4 §4.1).

The registry assigns pokeemerald-expansion flag/var names to RPG Maker
switch/variable IDs. It is stateful during a pipeline run and persists
assignments across all map conversions. Every flag-name proposal from the
conversion agent passes through here before acceptance — the agent never mints a
name itself (CLAUDE.md §4.3, §6; reference/guides/flag_registry_policy.md).

Two name sources:
  * **pre-seed** — high-confidence hand-authored mappings in
    `reference/guides/essentials_to_emerald_map.md`, loaded before any run.
  * **proposed** — names the conversion agent derives from event context and the
    orchestrator commits here after validation.

The Phase 3 sidecars (`reference/uranium_switches.json` / `uranium_variables.json`)
are read for two things: detecting Essentials *script-switches* (names beginning
`s:` — runtime-evaluated, never minted) and carrying each switch's human label as
context for the agent. They are NOT bulk-minted.

Hard rule (CLAUDE.md §6): never hand-edit the persistent state file mid-run. If
the state is wrong, fix the input data or this logic — don't patch the output.

Usage:
    python -m rpg2gba.conversion_agent.flag_registry validate
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import click

from rpg2gba.pbs_converter._naming import load_fork_constants, to_constant

logger = logging.getLogger(__name__)

# A valid name is the prefix plus a SCREAMING_SNAKE_CASE body.
_FLAG_RE = re.compile(r"^FLAG_[A-Z][A-Z0-9_]*$")
_VAR_RE = re.compile(r"^VAR_[A-Z][A-Z0-9_]*$")
# Structurally-meaningless names the policy explicitly rejects: a bare ID, a
# placeholder, or a "name" that just echoes the switch number.
_JUNK_RE = re.compile(r"^(FLAG|VAR)_(SWITCH|VARIABLE|VAR)?_?\d+$")
_BLOCKLIST = {"FLAG_TODO", "VAR_TODO", "FLAG_DONE", "VAR_DONE", "FLAG_UNKNOWN", "VAR_UNKNOWN"}

# Fork headers the collision check reads (best-effort; absent fork → no check).
_FORK_FLAG_HEADER = Path("include/constants/flags.h")
_FORK_VAR_HEADER = Path("include/constants/vars.h")

# A small reserved floor used when the fork isn't reachable, so the most common
# vanilla names still can't be clobbered.
_RESERVED_FLOOR = {"FLAG_SYS_GAME_CLEAR", "FLAG_SYS_POKEMON_GET", "VAR_FACING"}

# Terminal-hide setflag placeholder (transpiler.py's
# `_insert_terminal_hide_removeobject`). The transpiler cannot name the real
# flag at transpile time: whether a hidden event needs a freshly-minted
# FLAG_HIDE_* or must REUSE an existing rock/hidden-actor FLAG_TEMP_* is a
# decision that depends on the WHOLE map's visibility-flag pool assignment
# (`metadata_wiring._assign_visibility_flags`), computed downstream during
# staging (CLAUDE.md §4.3: one source of truth, and it isn't this module).
# So the transpiler emits `setflag(<this placeholder>)` and
# `metadata_wiring.resolve_terminal_hide_setflags` (called from
# stage_slice_scripts.py, after `build_object_events` has decided every
# template's flag) substitutes the real name. NOT a valid FLAG_ name — never
# passed to `_validate`/`propose_flag`/etc, purely a text anchor.
TERMINAL_HIDE_FLAG_PLACEHOLDER = "__TERMINAL_HIDE_FLAG__"

_PRESEED_ROW = re.compile(
    r"^\|\s*(flag|var)\s*\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*([A-Z][A-Z0-9_]*)\s*\|"
)


def self_switch_flag_name(map_id: int, event_id: int, letter: str) -> str:
    """Deterministic per-event self-switch flag name (must match prompts/system.md).

    RPG Maker self-switches (A-D) are local to an event instance, so they have no
    global switch id — the name is derived from (map, event, letter): e.g.
    self-switch A on event 48 of map 31 -> ``FLAG_MAP031_EVENT048_SSA``.
    """
    return f"FLAG_MAP{int(map_id):03d}_EVENT{int(event_id):03d}_SS{letter.upper()}"


def hide_flag_name(map_id: int, event_id: int) -> str:
    """Deterministic per-event terminal-hide flag name (must match transpiler.py
    and tileset_converter/metadata_wiring.py — both mint through
    ``FlagRegistry.mint_hide_flag`` so they agree on the identical name).

    A move route that ends in RGSS Change-Opacity-0 with no later restore is a
    PERMANENT hide (``transpiler._insert_terminal_hide_removeobject``): the
    transpiler emits ``removeobject`` so the object stops blocking its tile,
    but ``RemoveObjectEventByLocalIdAndMap`` sets the object TEMPLATE's flag —
    which must be a persistent flag, not a ``FLAG_TEMP_*`` (those auto-clear on
    map re-entry and would respawn the NPC visible at its start tile on the
    next visit — CLAUDE.md's smashable-rock trap, deliberately NOT reused
    here). Hide flag on event 20 of map 50 -> ``FLAG_HIDE_MAP050_EV020``.
    """
    return f"FLAG_HIDE_MAP{int(map_id):03d}_EV{int(event_id):03d}"


def temp_switch_flag_name(map_id: int, event_id: int, key: str) -> str:
    """Deterministic per-event temp-switch flag name (must match prompts/system.md).

    Uranium temp-switches (``Game_Event#@tempSwitches``, set via ``setTempSwitchOn``
    / read via ``tsOn?``, RPG Maker script code 355) are per-map-visit state that is
    rebuilt every map load — pokeemerald auto-reset TEMP flag semantics, NOT a saved
    self-switch. Named like a self-switch but with a ``TS`` marker so the two idioms
    never collide: temp-switch A on event 11 of map 2 -> ``FLAG_MAP002_EVENT011_TSA``.
    """
    return f"FLAG_MAP{int(map_id):03d}_EVENT{int(event_id):03d}_TS{key.upper()}"


def resolve_switch_flag(registry: FlagRegistry, switch_id: int) -> str | None:
    """Resolve a Uranium switch id to a FLAG_* name, minting from the
    developer-given label when one exists. ``None`` = unnamed or script
    switch — caller queues/defers. Shared logic behind
    ``transpiler.TranspileContext.flag_for_switch`` and
    ``tileset_converter.metadata_wiring.build_page_dispatcher`` (CLAUDE.md §4.3:
    one resolution rule, not two copies of it)."""
    if registry.is_script_switch(switch_id):
        return None
    existing = registry.get_flag(switch_id)
    if existing is not None:
        return existing
    label = registry.label_for_switch(switch_id)
    if not label:
        return None
    try:
        return registry.propose_flag(switch_id, to_constant("FLAG", label))
    except RegistryError:
        return None


def resolve_variable_var(registry: FlagRegistry, variable_id: int) -> str | None:
    """Resolve a Uranium variable id to a VAR_* name, minting from the
    developer-given label when one exists. ``None`` = unnamed — caller
    queues/defers. Mirrors ``resolve_switch_flag`` (variables have no
    script-switch concept)."""
    existing = registry.get_var(variable_id)
    if existing is not None:
        return existing
    label = registry.label_for_var(variable_id)
    if not label:
        return None
    try:
        return registry.propose_var(variable_id, to_constant("VAR", label))
    except RegistryError:
        return None


class RegistryError(RuntimeError):
    """Raised on a validation failure, collision, or corrupt state."""


class FlagRegistry:
    """Stateful FLAG_*/VAR_* assigner. One instance per pipeline run."""

    def __init__(self, fork_path: Path | None = None) -> None:
        self._switch_names: dict[int, str] = {}
        self._var_names: dict[int, str] = {}
        # Per-event self-switch flags, keyed by (map_id, event_id, letter).
        self._selfswitch_names: dict[tuple[int, int, str], str] = {}
        # Per-event temp-switch flags (Uranium setTempSwitchOn), keyed the same way.
        self._tempswitch_names: dict[tuple[int, int, str], str] = {}
        # Per-event terminal-hide flags (removeobject after a permanent
        # opacity-0 route), keyed by (map_id, event_id).
        self._hideflag_names: dict[tuple[int, int], str] = {}
        # Reverse index name -> ("flag"|"var"|"selfswitch"|"tempswitch"|"hideflag", id_or_key).
        self._used: dict[str, tuple[str, object]] = {}
        self._sources: dict[str, str] = {}  # name -> "preseed" | "proposed"
        self._script_switches: set[int] = set()
        self._switch_labels: dict[int, str] = {}
        self._var_labels: dict[int, str] = {}
        self._fork_flags: set[str] = set()
        self._fork_vars: set[str] = set()
        if fork_path is not None:
            self._fork_flags = load_fork_constants(fork_path / _FORK_FLAG_HEADER, "FLAG")
            self._fork_vars = load_fork_constants(fork_path / _FORK_VAR_HEADER, "VAR")
            logger.debug(
                "loaded %d fork FLAG_ + %d fork VAR_ constants for collision check",
                len(self._fork_flags),
                len(self._fork_vars),
            )

    # -- lookups -----------------------------------------------------------

    def get_flag(self, switch_id: int) -> str | None:
        return self._switch_names.get(int(switch_id))

    def get_var(self, variable_id: int) -> str | None:
        return self._var_names.get(int(variable_id))

    def is_script_switch(self, switch_id: int) -> bool:
        return int(switch_id) in self._script_switches

    def label_for_switch(self, switch_id: int) -> str | None:
        return self._switch_labels.get(int(switch_id))

    def label_for_var(self, variable_id: int) -> str | None:
        return self._var_labels.get(int(variable_id))

    # -- proposals ---------------------------------------------------------

    def propose_flag(self, switch_id: int, name: str) -> str:
        """Validate + commit a FLAG_ name for a switch, or return the existing one.

        Raises RegistryError if the switch is a script-switch, the name is
        invalid, or it collides with another id / a fork constant.
        """
        sid = int(switch_id)
        if sid in self._script_switches:
            raise RegistryError(
                f"switch {sid} is an Essentials script-switch "
                f"({self._switch_labels.get(sid)!r}) — runtime-evaluated, never minted"
            )
        existing = self._switch_names.get(sid)
        if existing is not None:
            if name != existing:
                logger.debug("switch %d already %s; ignoring %s", sid, existing, name)
            return existing
        self._validate("flag", name)
        self._commit("flag", sid, name, "proposed")
        return name

    def propose_var(self, variable_id: int, name: str) -> str:
        """Validate + commit a VAR_ name for a variable, or return the existing one."""
        vid = int(variable_id)
        existing = self._var_names.get(vid)
        if existing is not None:
            if name != existing:
                logger.debug("var %d already named %s; ignoring proposal %s", vid, existing, name)
            return existing
        self._validate("var", name)
        self._commit("var", vid, name, "proposed")
        return name

    def mint_self_switch(self, map_id: int, event_id: int, letter: str) -> str:
        """Register the deterministic per-event self-switch flag (idempotent).

        Self-switches have no integer switch id, so the conversion agent emits
        their names directly without a registry proposal (prompts/system.md +
        few_shot/give_item_with_fanfare.md). The orchestrator calls this so the
        registry knows the flag exists and ``dump_header`` defines the constant —
        otherwise it's an undefined symbol at assembly. Keyed by (map, event,
        letter); re-minting the same key returns the existing name.
        """
        key = (int(map_id), int(event_id), letter.upper())
        existing = self._selfswitch_names.get(key)
        if existing is not None:
            return existing
        name = self_switch_flag_name(*key)
        self._validate("flag", name)
        prior = self._used.get(name)
        if prior is not None:
            raise RegistryError(
                f"self-switch name {name!r} collides with an existing {prior[0]} assignment"
            )
        self._selfswitch_names[key] = name
        self._used[name] = ("selfswitch", key)
        self._sources[name] = "selfswitch"
        return name

    def mint_temp_switch(self, map_id: int, event_id: int, key: str) -> str:
        """Register the deterministic per-event temp-switch flag (idempotent).

        Mirrors ``mint_self_switch`` but for Uranium temp-switches (``setTempSwitchOn``
        / ``tsOn?``, script code 355), which are per-map-visit state and so map to an
        auto-reset TEMP flag rather than a saved self-switch. The conversion agent
        emits the name directly (prompts/system.md); the orchestrator calls this so
        ``dump_header`` defines the constant — otherwise it's an undefined symbol at
        assembly. Keyed by (map, event, key); re-minting the same key is a no-op.
        """
        tkey = (int(map_id), int(event_id), key.upper())
        existing = self._tempswitch_names.get(tkey)
        if existing is not None:
            return existing
        name = temp_switch_flag_name(*tkey)
        self._validate("flag", name)
        prior = self._used.get(name)
        if prior is not None:
            raise RegistryError(
                f"temp-switch name {name!r} collides with an existing {prior[0]} assignment"
            )
        self._tempswitch_names[tkey] = name
        self._used[name] = ("tempswitch", tkey)
        self._sources[name] = "tempswitch"
        return name

    def mint_hide_flag(self, map_id: int, event_id: int) -> str:
        """Register the deterministic per-event terminal-hide flag (idempotent).

        Mirrors ``mint_self_switch``/``mint_temp_switch`` but backs the
        terminal-hide idiom (``transpiler._insert_terminal_hide_removeobject``):
        a persistent flag written onto the object template's ``"flag"`` field
        so pokeemerald's ``TrySpawnObjectEvents`` respawn gate
        (``!FlagGet(template->flagId)``) stays latched shut across camera
        updates/re-entries instead of respawning the NPC at its template
        coordinates.

        Only called from ``metadata_wiring.build_object_events`` — and only
        for a hidden event whose template would OTHERWISE carry the ``"0"``
        null-sentinel flag. An event that already has a real flag from the
        rock/hidden-actor visibility pool (``_assign_visibility_flags``) must
        REUSE that flag instead (one flag per template, never two); the
        transpiler never calls this directly, since it can't know which case
        applies until the whole map's flag-pool assignment is decided here
        (see ``TERMINAL_HIDE_FLAG_PLACEHOLDER`` and
        ``resolve_terminal_hide_setflags``). Keyed by (map, event); re-minting
        the same key returns the existing name.
        """
        key = (int(map_id), int(event_id))
        existing = self._hideflag_names.get(key)
        if existing is not None:
            return existing
        name = hide_flag_name(*key)
        self._validate("flag", name)
        prior = self._used.get(name)
        if prior is not None:
            raise RegistryError(
                f"hide-flag name {name!r} collides with an existing {prior[0]} assignment"
            )
        self._hideflag_names[key] = name
        self._used[name] = ("hideflag", key)
        self._sources[name] = "hideflag"
        return name

    # -- internals ---------------------------------------------------------

    def _validate(self, kind: str, name: str) -> None:
        rx = _FLAG_RE if kind == "flag" else _VAR_RE
        if not name or not rx.match(name):
            raise RegistryError(f"{name!r} is not a valid {kind.upper()}_ SNAKE_CASE name")
        if name in _BLOCKLIST or _JUNK_RE.match(name):
            raise RegistryError(f"{name!r} is a placeholder/structural name — derive from context")
        body = name.split("_", 1)[1]
        if len(body) < 3:
            raise RegistryError(f"{name!r} is too short to be meaningful")
        fork_set = self._fork_flags if kind == "flag" else self._fork_vars
        if name in fork_set or name in _RESERVED_FLOOR:
            raise RegistryError(f"{name!r} already exists in pokeemerald-expansion — pick another")

    def _commit(self, kind: str, id_: int, name: str, source: str) -> None:
        prior = self._used.get(name)
        if prior is not None and prior != (kind, id_):
            pk, pid = prior
            raise RegistryError(
                f"name collision: {name!r} already assigned to {pk} {pid}, "
                f"cannot reuse for {kind} {id_}"
            )
        if kind == "flag":
            self._switch_names[id_] = name
        else:
            self._var_names[id_] = name
        self._used[name] = (kind, id_)
        self._sources[name] = source

    # -- pre-seed ----------------------------------------------------------

    def seed_labels(self, switches_json: Path, variables_json: Path) -> None:
        """Load switch/variable labels and script-switch ids from the Phase 3
        sidecars (``reference/uranium_switches.json`` / ``uranium_variables.json``).

        Split out of ``pre_seed`` because ``FlagRegistry.load()`` restores mints
        and script-switch ids (both part of ``to_state()``) but NOT labels —
        labels are never persisted. Any pipeline stage that loads persisted
        state and then needs ``label_for_switch``/``label_for_var`` (e.g.
        ``tileset_converter.metadata_wiring.build_page_dispatcher``'s
        script-switch temp-switch carve-out) must call this explicitly after
        ``load()``, or every label lookup silently returns ``None``.
        """
        switches: dict[str, str] = json.loads(Path(switches_json).read_text(encoding="utf-8"))
        variables: dict[str, str] = json.loads(Path(variables_json).read_text(encoding="utf-8"))
        for k, v in switches.items():
            sid = int(k)
            self._switch_labels[sid] = v
            if v.startswith("s:"):
                self._script_switches.add(sid)
        for k, v in variables.items():
            self._var_labels[int(k)] = v

    def pre_seed(self, preseed_md: Path, switches_json: Path, variables_json: Path) -> None:
        """Populate from the sidecars (labels + script-switches) and the pre-seed map."""
        self.seed_labels(switches_json, variables_json)

        for kind, idx, constant in self._parse_preseed(Path(preseed_md)):
            if kind == "flag" and idx in self._script_switches:
                raise RegistryError(
                    f"pre-seed maps switch {idx} but it is a script-switch — remove the row"
                )
            self._validate(kind, constant)
            self._commit(kind, idx, constant, "preseed")
        logger.info(
            "pre-seeded %d flags + %d vars (%d script-switches blocked)",
            len(self._switch_names),
            len(self._var_names),
            len(self._script_switches),
        )

    @staticmethod
    def _parse_preseed(path: Path) -> list[tuple[str, int, str]]:
        """Parse the pipe table in essentials_to_emerald_map.md → (kind, index, constant)."""
        rows: list[tuple[str, int, str]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _PRESEED_ROW.match(line)
            if not m:
                continue
            kind, idx, _label, constant = m.group(1), int(m.group(2)), m.group(3), m.group(4)
            rows.append((kind, idx, constant))
        if not rows:
            raise RegistryError(f"no pre-seed rows parsed from {path}")
        return rows

    # -- persistence -------------------------------------------------------

    def to_state(self) -> dict:
        return {
            "switches": {str(k): v for k, v in sorted(self._switch_names.items())},
            "variables": {str(k): v for k, v in sorted(self._var_names.items())},
            "self_switches": {
                f"{m}:{e}:{letter}": name
                for (m, e, letter), name in sorted(self._selfswitch_names.items())
            },
            "temp_switches": {
                f"{m}:{e}:{key}": name
                for (m, e, key), name in sorted(self._tempswitch_names.items())
            },
            "hide_flags": {
                f"{m}:{e}": name
                for (m, e), name in sorted(self._hideflag_names.items())
            },
            "source": dict(sorted(self._sources.items())),
            "script_switches": sorted(self._script_switches),
        }

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_state(), indent=2) + "\n", encoding="utf-8")
        logger.debug("saved registry state -> %s", path)

    @classmethod
    def load(cls, path: Path, fork_path: Path | None = None) -> "FlagRegistry":
        reg = cls(fork_path=fork_path)
        state = json.loads(Path(path).read_text(encoding="utf-8"))
        reg._script_switches = set(state.get("script_switches", []))
        for k, v in state.get("switches", {}).items():
            reg._commit("flag", int(k), v, state["source"].get(v, "preseed"))
        for k, v in state.get("variables", {}).items():
            reg._commit("var", int(k), v, state["source"].get(v, "preseed"))
        for k, v in state.get("self_switches", {}).items():
            m, e, letter = k.split(":")
            key = (int(m), int(e), letter)
            reg._selfswitch_names[key] = v
            reg._used[v] = ("selfswitch", key)
            reg._sources[v] = state["source"].get(v, "selfswitch")
        for k, v in state.get("temp_switches", {}).items():
            m, e, tk = k.split(":")
            tkey = (int(m), int(e), tk)
            reg._tempswitch_names[tkey] = v
            reg._used[v] = ("tempswitch", tkey)
            reg._sources[v] = state["source"].get(v, "tempswitch")
        for k, v in state.get("hide_flags", {}).items():
            m, e = k.split(":")
            hkey = (int(m), int(e))
            reg._hideflag_names[hkey] = v
            reg._used[v] = ("hideflag", hkey)
            reg._sources[v] = state["source"].get(v, "hideflag")
        return reg

    # -- header emit -------------------------------------------------------

    def dump_header(
        self,
        out_path: str | Path,
        *,
        flag_base: int | str = 0x500,
        var_base: int | str = 0x40D0,
        selfswitch_base: int | str = 0x600,
        tempswitch_base: int | str = 0x700,
        capacities: dict[str, int] | None = None,
    ) -> None:
        """Emit a C header defining every assigned flag/var/self-switch/temp-switch.

        Each base is either a numeric placeholder (intermediate dumps under
        output/.../intermediate/ — the value only needs to be unique to *assemble*,
        not fork-safe) or, for the real fork header, the name of one of the engine's
        ``RPG2GBA_*_START`` range constants derived in ``include/constants/flags.h`` /
        ``vars.h`` from ``include/config/rpg2gba.h``. An ``int`` is emitted as
        ``0x{value:X}``; a ``str`` is emitted verbatim as the #define's value.

        ``capacities``, when provided, must carry exactly the keys "flags", "vars",
        "selfswitches", "tempswitches" — the region sizes from
        ``include/config/rpg2gba.h``. Each section's mint count is checked against
        its capacity before anything is written; exceeding it raises loud rather
        than silently overflowing into the next region.

        Hide flags (``mint_hide_flag``) have no dedicated region of their own —
        adding one would mean a new ``RPG2GBA_HIDEFLAG_*`` range in
        ``include/config/rpg2gba.h`` plus a matching call-site change in
        ``scripts/assemble_pathfinder.py``, both outside this module. They are
        persistent per-event flags exactly like self-switches (never
        auto-cleared — CLAUDE.md's smashable-rock TEMP-flag trap is the reason
        NOT to put them in the temp-switch region), so they're addressed in the
        SAME ``RPG2GBA_SELFSWITCH_BASE`` region, indexed immediately after the
        self-switches. The self-switch region has ample slack (1280 slots,
        engine default) for this.
        """
        if capacities is not None:
            expected = {"flags", "vars", "selfswitches", "tempswitches"}
            got = set(capacities)
            if got != expected:
                missing = expected - got
                extra = got - expected
                raise ValueError(
                    "dump_header capacities must have exactly the keys "
                    f"{sorted(expected)}; missing={sorted(missing)} extra={sorted(extra)}"
                )
            counts = {
                "flags": len(self._switch_names),
                "vars": len(self._var_names),
                "selfswitches": len(self._selfswitch_names) + len(self._hideflag_names),
                "tempswitches": len(self._tempswitch_names),
            }
            for section, count in counts.items():
                cap = capacities[section]
                if count > cap:
                    raise ValueError(
                        f"dump_header: {section} section has {count} minted names, "
                        f"exceeding its capacity of {cap} — the capacity comes from "
                        "include/config/rpg2gba.h; grow the region there, rebuild the "
                        "engine, and re-assemble"
                    )

        def _base_literal(base: int | str) -> str:
            return f"0x{base:X}" if isinstance(base, int) else base

        def _base_comment(base: int | str) -> str:
            if isinstance(base, int):
                return "// placeholder — intermediate dump only, not fork-safe"
            return "// engine range constant (config/rpg2gba.h)"

        def _def_line(macro_padded: str, base: int | str, tail_pad: str) -> str:
            return f"#define {macro_padded}{_base_literal(base)}{tail_pad}{_base_comment(base)}"

        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "#ifndef GUARD_RPG2GBA_FLAGS_H",
            "#define GUARD_RPG2GBA_FLAGS_H",
            "",
            "// Generated by rpg2gba flag_registry — do not hand-edit (CLAUDE.md §6).",
            _def_line("RPG2GBA_FLAG_BASE       ", flag_base, "   "),
            _def_line("RPG2GBA_VAR_BASE        ", var_base, "  "),
            _def_line("RPG2GBA_SELFSWITCH_BASE ", selfswitch_base, "   "),
            _def_line("RPG2GBA_TEMPSWITCH_BASE ", tempswitch_base, "   "),
            "",
        ]
        for i, (_id, name) in enumerate(sorted(self._switch_names.items())):
            lines.append(f"#define {name} (RPG2GBA_FLAG_BASE + {i})")
        lines.append("")
        for i, (_id, name) in enumerate(sorted(self._var_names.items())):
            lines.append(f"#define {name} (RPG2GBA_VAR_BASE + {i})")
        lines.append("")
        for i, (_key, name) in enumerate(sorted(self._selfswitch_names.items())):
            lines.append(f"#define {name} (RPG2GBA_SELFSWITCH_BASE + {i})")
        lines.append("")
        selfswitch_count = len(self._selfswitch_names)
        for i, (_key, name) in enumerate(sorted(self._hideflag_names.items())):
            lines.append(f"#define {name} (RPG2GBA_SELFSWITCH_BASE + {selfswitch_count + i})")
        lines.append("")
        for i, (_key, name) in enumerate(sorted(self._tempswitch_names.items())):
            lines.append(f"#define {name} (RPG2GBA_TEMPSWITCH_BASE + {i})")
        lines += ["", "#endif // GUARD_RPG2GBA_FLAGS_H", ""]
        out.write_text("\n".join(lines), encoding="utf-8")
        logger.info(
            "dumped %d flags + %d vars + %d self-switches + %d hide-flags + %d temp-switches -> %s",
            len(self._switch_names),
            len(self._var_names),
            len(self._selfswitch_names),
            len(self._hideflag_names),
            len(self._tempswitch_names),
            out,
        )

    # -- integrity ---------------------------------------------------------

    def check_integrity(self) -> None:
        """Re-run every invariant over the loaded state; raise on any violation."""
        seen: dict[str, tuple[str, int]] = {}
        for sid, name in self._switch_names.items():
            self._validate("flag", name)
            if name in seen:
                raise RegistryError(f"duplicate name {name!r}")
            seen[name] = ("flag", sid)
            if sid in self._script_switches:
                raise RegistryError(f"switch {sid} is both minted and a script-switch")
        for vid, name in self._var_names.items():
            self._validate("var", name)
            if name in seen:
                raise RegistryError(f"duplicate name {name!r}")
            seen[name] = ("var", vid)
        for key, name in self._selfswitch_names.items():
            self._validate("flag", name)
            if name in seen:
                raise RegistryError(f"duplicate name {name!r}")
            seen[name] = ("selfswitch", key)
        for key, name in self._tempswitch_names.items():
            self._validate("flag", name)
            if name in seen:
                raise RegistryError(f"duplicate name {name!r}")
            seen[name] = ("tempswitch", key)
        for key, name in self._hideflag_names.items():
            self._validate("flag", name)
            if name in seen:
                raise RegistryError(f"duplicate name {name!r}")
            seen[name] = ("hideflag", key)


@click.group()
def main() -> None:
    pass


@main.command()
@click.option(
    "--state",
    "state_path",
    default="output/uranium-build/flag_state.json",
    help="Path to the persisted registry state.",
)
def validate(state_path: str) -> None:
    """Validate the current registry state (exit non-zero on any violation)."""
    path = Path(state_path)
    if not path.is_file():
        raise click.ClickException(f"no registry state at {path} — run a conversion first")
    reg = FlagRegistry.load(path)
    reg.check_integrity()
    state = reg.to_state()
    click.echo(
        f"OK: {len(state['switches'])} flags, {len(state['variables'])} vars, "
        f"{len(state['script_switches'])} script-switches blocked"
    )


if __name__ == "__main__":
    main()
