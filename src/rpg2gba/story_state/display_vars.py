"""Display-only variable writes (operator ruling 2026-10-15,
reference/chapters/08-route-1-moki-revisit.md s9; PROJECT_TODO #127).

Ruling (b) refuses a row `party_model` when its script reads party/Pokedex
state. A script such as Prof. Bambo's `pbSet(2,$Trainer.pokedexSeen)` /
`pbSet(3,$Trainer.pokedexOwned)` exists only to feed a `\\v[2]` / `\\v[3]`
text code a couple of commands later. The operator ruled there is no party
model; such a write is dropped and its variable havoc'd, exactly like the
graphics-only exemption (`graphics_vars`).

Variables 1/2/3 are general scratch variables corpus-wide (conditional
branches, shop prices, Ruby helpers and page conditions all read them), so
unlike the graphics exemption no per-variable corpus verdict is possible. The
rule is per WRITE SITE, and local to the scope the search interprets.

A write `pbSet(N, e)` / `$game_variables[N] = e` (e reads party/dex state) in
command list L at position i is exempt iff, walking L from the write to the
end of the list, NO command reads N other than as a `\\v[N]` text code in a
message command (101/401/102/105/405), until a later always-executed write of
N (same or outer indent, a `=` write, no control flow in its script block).
The following all count as a read: a conditional branch or variable operation
on N, a `\\v[N]` inside a non-message string, a script's `pbGet(N)` /
`$game_variables[N]`, a call to a Ruby `def`/`class` of
`reference/scripts_dump/` whose body reads N (matched by name token, an
over-approximation), a `117` call to a common event that (transitively) reads
N non-display, and a read in the same script block as the write. Reads are
considered even after the write's branch ends (the dropped write is
path-conditional from the search's view). Lists with loops/labels
(112/113/118/119) are never exempt.

Why local suffices: the dropped write is havoc'd (`SearchResult.havoc`), and
the story model gives every downstream reader of a havoc'd variable "could be
anything" (TOP, `model.py` `_apply_havoc`), so reads in OTHER pages/events are
already handled soundly; the only reads the search could get wrong are those
it interprets in the same scope, which is what the walk above covers.

If the corpus build is absent the policy refuses every site.
"""
from __future__ import annotations

import functools
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rpg2gba.story_state.graphics_vars import (
    _REPO_ROOT, _command_reads, _string_reads, _strings,
)

__all__ = [
    "DisplayVarPolicy", "display_var_policy", "scan_display_policy",
]

_MESSAGE_CODES = frozenset({101, 401, 102, 402, 105, 405})
_LOOP_CODES = frozenset({112, 113, 118, 119})
_SCRIPT_CODES = frozenset({355, 655})

_PBSET = re.compile(r"(?<![\w.])pbSet\(\s*(\d+)\s*,")
_ASSIGN_N = re.compile(r"\$game_variables\[\s*(\d+)\s*\]\s*=(?!=)")
_CONTROL_FLOW = re.compile(
    r"\b(if|unless|while|until|for|case|begin|rescue|loop|times|each|and|or)\b|&&|\|\|"
)
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*[?!]?")
_HEADER = re.compile(r"^(\s*)(def|class|module)\s+(?:self\.)?([A-Za-z_][\w]*[?!]?)")


def _ruby_units(sources: Iterable[str]) -> dict[str, frozenset[int]]:
    """unit name (a `def`, or a `class`/`module` incl. its methods) -> the
    variables its body reads. Same-named units merge."""
    units: dict[str, set[int]] = {}
    for source in sources:
        lines = source.splitlines()
        headers = [(n, _HEADER.match(line)) for n, line in enumerate(lines)]
        headers = [(n, m) for n, m in headers if m]
        for k, (n, m) in enumerate(headers):
            kind, name = m.group(2), m.group(3)
            end = len(lines)
            for n2, m2 in headers[k + 1:]:
                if kind == "def" or not m2.group(1):  # class: ends at next top-level header
                    end = n2
                    break
            units.setdefault(name, set()).update(_string_reads("\n".join(lines[n:end])))
    return {name: frozenset(vs) for name, vs in units.items() if vs}


@dataclass(frozen=True)
class _Cmd:
    index: int
    indent: int
    reads: frozenset[int]          # non-display reads
    writes: frozenset[int]         # writes that dominate later reads
    stmt_writes: frozenset[int]    # every plain write (incl. conditional)
    control_flow: bool = False


def _group_script(commands: list[dict[str, Any]], i: int) -> tuple[str, int]:
    parts = [str((commands[i].get("parameters") or [""])[0])]
    j = i + 1
    while j < len(commands) and commands[j].get("code") == 655:
        parts.append(str((commands[j].get("parameters") or [""])[0]))
        j += 1
    return "\n".join(parts), j


def _call_reads(text: str, readers: dict[str, frozenset[int]]) -> set[int]:
    out: set[int] = set()
    if readers:
        for tok in set(_TOKEN.findall(text)):
            out |= readers.get(tok, frozenset())
    return out


def _walk(
    commands: list[dict[str, Any]], readers: dict[str, frozenset[int]],
    ce_reads: dict[int, frozenset[int]],
) -> list[_Cmd]:
    out: list[_Cmd] = []
    i = 0
    while i < len(commands):
        cmd = commands[i]
        code, p = cmd.get("code"), cmd.get("parameters") or []
        indent = cmd.get("indent", 0) or 0
        reads: set[int] = set()
        writes: set[int] = set()
        stmt: set[int] = set()
        flow = False
        nxt = i + 1
        if code == 355:
            text, nxt = _group_script(commands, i)
            reads = _string_reads(text) | _call_reads(text, readers)
            stmt = {int(m.group(1)) for m in _PBSET.finditer(text)}
            stmt |= {int(m.group(1)) for m in _ASSIGN_N.finditer(text)}
            flow = bool(_CONTROL_FLOW.search(text))
            if not flow:
                writes = set(stmt)
            # a write whose own block reads the variable (`pbSet(2,pbGet(2)+1)`)
            # keeps the read -- reads are checked before writes.
        elif code == 655:
            pass  # folded into its 355 group
        elif code in _MESSAGE_CODES:
            pass
        else:
            reads = set(_command_reads(cmd))
            if code == 117 and p:
                reads |= ce_reads.get(p[0], frozenset())
            texts = [t for t in _strings(p)]
            for t in texts:
                reads |= _call_reads(t, readers)
            if code == 122 and len(p) >= 5 and p[2] == 0:
                writes = set(range(p[0], p[1] + 1))
                stmt = set(writes)
                if p[3] == 1:
                    reads.add(p[4])
            elif code == 122 and len(p) >= 5:
                stmt = set(range(p[0], p[1] + 1))
        out.append(_Cmd(i, indent, frozenset(reads), frozenset(writes), frozenset(stmt), flow))
        i = nxt
    return out


def _has_loops(commands: list[dict[str, Any]]) -> bool:
    return any(c.get("code") in _LOOP_CODES for c in commands)


def _ce_nondisplay_reads(
    common_events: list[dict[str, Any]], readers: dict[str, frozenset[int]],
) -> dict[int, frozenset[int]]:
    """CE id -> variables it reads non-display (transitively through `117`)."""
    direct: dict[int, set[int]] = {}
    calls: dict[int, set[int]] = {}
    for ce in common_events:
        cid = ce.get("id")
        cmds = ce.get("list") or []
        direct[cid] = set().union(*(c.reads for c in _walk(cmds, readers, {})), set())
        calls[cid] = {c["parameters"][0] for c in cmds if c.get("code") == 117 and c.get("parameters")}
    out = {cid: set(v) for cid, v in direct.items()}
    changed = True
    while changed:
        changed = False
        for cid, callees in calls.items():
            for callee in callees:
                extra = out.get(callee, set()) - out[cid]
                if extra:
                    out[cid] |= extra
                    changed = True
    return {cid: frozenset(v) for cid, v in out.items()}


@dataclass(frozen=True)
class DisplayVarPolicy:
    """Decides which `pbSet` / `$game_variables[N] =` party writes are
    display-only (module docstring). `usable` is False when built without a
    corpus: then no site is exempt."""

    ce_reads: dict[int, frozenset[int]] = field(default_factory=dict, hash=False, compare=False)
    readers: dict[str, frozenset[int]] = field(default_factory=dict, hash=False, compare=False)
    usable: bool = False

    def write_ok(self, commands: list[dict[str, Any]], i: int, var_id: int) -> bool:
        if not self.usable or _has_loops(commands):
            return False
        walked = _walk(commands, self.readers, self.ce_reads)
        site = next((c for c in walked if c.index == i), None)
        if site is None:
            return False
        if var_id in site.reads:      # same block also reads N
            return False
        for c in walked:
            if c.index <= i:
                continue
            if var_id in c.reads:
                return False
            if var_id in c.writes and c.indent <= site.indent:
                return True           # re-written: later reads see that value
        return True


def scan_display_policy(
    common_events: Iterable[dict[str, Any]], ruby_sources: Iterable[str] = (),
) -> DisplayVarPolicy:
    """Build the policy from already-loaded common events and Ruby sources
    (the only corpus facts the local rule needs: which CEs / Ruby units read
    which variables)."""
    readers = _ruby_units(ruby_sources)
    ces = [ce for ce in common_events if ce]
    return DisplayVarPolicy(_ce_nondisplay_reads(ces, readers), readers, True)


@functools.cache
def display_var_policy(build_dir: Path | None = None) -> DisplayVarPolicy:
    """`scan_display_policy` over the decoded build and the scripts dump;
    unusable (no exemption) when the build has no decoded maps."""
    from rpg2gba.beat_floor.lookup import default_build_dir

    root = Path(build_dir) if build_dir is not None else default_build_dir()
    map_paths = sorted((root / "maps").glob("Map*.json"))
    ce_path = root / "common_events.json"
    if not map_paths or not ce_path.is_file():
        return DisplayVarPolicy()
    common_events = json.loads(ce_path.read_text(encoding="utf-8"))
    scripts = sorted((_REPO_ROOT / "reference" / "scripts_dump").glob("*.rb"))
    ruby = (p.read_text(encoding="utf-8", errors="replace") for p in scripts)
    return scan_display_policy(common_events, ruby)
