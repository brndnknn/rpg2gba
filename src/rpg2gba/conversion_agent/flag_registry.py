"""Single source of truth for FLAG_*/VAR_* name assignments (Phase 4 §4.1).

The registry assigns pokeemerald-expansion flag/var names to RPG Maker
switch/variable IDs. It is stateful during a pipeline run and persists
assignments across all map conversions. Every flag-name proposal from the
conversion agent passes through here before acceptance — the agent never mints a
name itself (CLAUDE.md §4.3, §6; reference/flag_registry_policy.md).

Two name sources:
  * **pre-seed** — high-confidence hand-authored mappings in
    `reference/essentials_to_emerald_map.md`, loaded before any run.
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

from rpg2gba.pbs_converter._naming import load_fork_constants

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


class RegistryError(RuntimeError):
    """Raised on a validation failure, collision, or corrupt state."""


class FlagRegistry:
    """Stateful FLAG_*/VAR_* assigner. One instance per pipeline run."""

    def __init__(self, fork_path: Path | None = None) -> None:
        self._switch_names: dict[int, str] = {}
        self._var_names: dict[int, str] = {}
        # Per-event self-switch flags, keyed by (map_id, event_id, letter).
        self._selfswitch_names: dict[tuple[int, int, str], str] = {}
        # Reverse index name -> ("flag"|"var"|"selfswitch", id_or_key) for collisions.
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

    def pre_seed(self, preseed_md: Path, switches_json: Path, variables_json: Path) -> None:
        """Populate from the sidecars (labels + script-switches) and the pre-seed map."""
        switches: dict[str, str] = json.loads(Path(switches_json).read_text(encoding="utf-8"))
        variables: dict[str, str] = json.loads(Path(variables_json).read_text(encoding="utf-8"))
        for k, v in switches.items():
            sid = int(k)
            self._switch_labels[sid] = v
            if v.startswith("s:"):
                self._script_switches.add(sid)
        for k, v in variables.items():
            self._var_labels[int(k)] = v

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
        return reg

    # -- header emit -------------------------------------------------------

    def dump_header(
        self,
        out_path: str | Path,
        *,
        flag_base: int = 0x500,
        var_base: int = 0x40D0,
        selfswitch_base: int = 0x600,
    ) -> None:
        """Emit a C header defining every assigned flag/var/self-switch.

        The base offsets are placeholders by default (the values only need to be
        unique to *assemble*). Phase 7 passes real, free, reserved ranges when the
        header drops into the fork — see reference/flag_registry_policy.md on the
        flag-budget sizing (Uranium needs more saved flags than vanilla has free).
        """
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "#ifndef GUARD_RPG2GBA_FLAGS_H",
            "#define GUARD_RPG2GBA_FLAGS_H",
            "",
            "// Generated by rpg2gba flag_registry — do not hand-edit (CLAUDE.md §6).",
            "// Phase 7 assigns the real base offsets when these drop into the fork.",
            f"#define RPG2GBA_FLAG_BASE       0x{flag_base:X}   // TODO Phase 7: free flag range",
            f"#define RPG2GBA_VAR_BASE        0x{var_base:X}  // TODO Phase 7: free var range",
            f"#define RPG2GBA_SELFSWITCH_BASE 0x{selfswitch_base:X}   // TODO Phase 7: free range",
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
        lines += ["", "#endif // GUARD_RPG2GBA_FLAGS_H", ""]
        out.write_text("\n".join(lines), encoding="utf-8")
        logger.info(
            "dumped %d flags + %d vars + %d self-switches -> %s",
            len(self._switch_names),
            len(self._var_names),
            len(self._selfswitch_names),
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
