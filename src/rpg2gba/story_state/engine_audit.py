"""C3: the fenced-engine audit (REDERIVATION_PLAN.md §16, ruling R9, "C2 shape"
(d) and (e)).

The story-state model (`model.py`) proves what a chapter's *Uranium* rows do;
`transitions.py` declares what the ROM's fenced engine C is supposed to do on
top of that (an `EngineTransition`'s `engine_writes`, an `EngineObligation`'s
switch ids, a `HarnessOnlyWrite`). Nobody had verified the fenced code
actually matches those declarations -- this module does, by grepping the
vendored engine (`engine/`) for every `FlagSet`/`FlagClear`/`FlagToggle`/
`VarSet` call inside a sentinel-fenced region and comparing what it finds
against `transitions.py` and the flag registry.

Read-only: this module never touches `engine/` (CLAUDE.md's "do not edit
`engine/`") or the registry's persisted state file.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from rpg2gba.conversion_agent.flag_registry import FlagRegistry
from rpg2gba.conversion_agent.fork_index import ForkIndex, load_or_build
from rpg2gba.ruby_subset.builtins import ENGINE_ATTRIBUTES
from rpg2gba.story_state.extract import extract_map, extract_triggered_common_events
from rpg2gba.story_state.model import _state_key_repr
from rpg2gba.story_state.transitions import (
    HARNESS_ONLY,
    OBLIGATIONS,
    TRANSITIONS,
    EngineWrite,
)

logger = logging.getLogger(__name__)

SENTINELS: tuple[str, ...] = (
    "URANIUM PATHFINDER SLICE",
    "URANIUM MAP WALKER",
    "URANIUM EMBEDDED SAVE",
    "RPG2GBA EVENT RANGE EXPANSION",
)

_SENTINEL_ALT = "|".join(re.escape(s) for s in SENTINELS)
_BEGIN_RE = re.compile(rf"^\s*//\s*BEGIN\s+({_SENTINEL_ALT})\b")
_BARE_RE = re.compile(rf"^\s*//\s*({_SENTINEL_ALT}):")
_END_RE = re.compile(rf"^\s*//\s*END\s+({_SENTINEL_ALT})\b")

# A top-level (column-0) C function signature: return type + name + '(' ... ')'
# with no trailing ';' -- deliberately loose (this is a locator heuristic, not
# a C parser). The opening brace is expected on its own line immediately
# after (pokeemerald's brace style), which is what both known real sites
# (`DoWhiteOut`, `CB2_StartUraniumSlice`) look like.
_FUNC_SIG_RE = re.compile(r"^[A-Za-z_][\w \*]*?\b(\w+)\([^;{}]*\)\s*$")

_WRITE_CALL_RE = re.compile(
    r"\b(FlagSet|FlagClear|FlagToggle|VarSet)\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:,\s*([^)]*))?\)"
)

_SOURCE_GLOBS: tuple[str, ...] = ("src/**/*.c", "include/**/*.h")


@dataclass(frozen=True)
class FencedRegion:
    """One sentinel-fenced span of C source."""

    path: Path
    sentinel: str
    start_line: int  # 1-indexed, the opener comment line
    end_line: int  # 1-indexed, the `// END` line
    function: str | None  # enclosing C function, if determinable


@dataclass(frozen=True)
class FoundWrite:
    """One `FlagSet`/`FlagClear`/`FlagToggle`/`VarSet(...)` call found inside
    a `FencedRegion`."""

    call: str
    constant: str
    value: str | None  # VarSet's second argument, verbatim; None otherwise
    path: Path
    line: int
    function: str | None
    sentinel: str


@dataclass(frozen=True)
class UndeclaredWrite:
    write: FoundWrite
    detail: str


@dataclass(frozen=True)
class MissingTransitionWrite:
    transition: str
    write: EngineWrite
    detail: str


@dataclass(frozen=True)
class OwedObligation:
    obligation: str
    switch_id: int
    detail: str


@dataclass(frozen=True)
class IntroSeedGap:
    key: str
    label: str | None
    constant: str | None
    intro_values: tuple
    detail: str


@dataclass(frozen=True)
class UnresolvedEngineFlag:
    """One `ENGINE_ATTRIBUTES` entry whose `FLAG_SYS_*` did not resolve in
    the fork-capability index (CLAUDE.md §4.7's forward gate, applied to
    `ruby_subset.builtins.ENGINE_ATTRIBUTES` -- REDERIVATION_PLAN.md §16.3
    "C8 shape" ruling (b))."""

    namespace: str
    attribute: str
    flag: str
    detail: str


@dataclass(frozen=True)
class AuditReport:
    undeclared_writes: tuple[UndeclaredWrite, ...]
    missing_transition_writes: tuple[MissingTransitionWrite, ...]
    owed_obligations: tuple[OwedObligation, ...]
    intro_seed_gaps: tuple[IntroSeedGap, ...]
    intro_seed_unread: tuple[str, ...]
    # Informational, like `intro_seed_unread`: obligations no kept row reads yet.
    deferred_obligations: tuple[str, ...] = ()
    # ENGINE_ATTRIBUTES flags that don't resolve in the fork index -- a hard
    # failure (the pipeline would emit a symbol the fork doesn't define), so
    # this DOES count toward `ok`, unlike the informational fields above.
    unresolved_engine_flags: tuple[UnresolvedEngineFlag, ...] = ()
    # None when the flag check ran; a non-empty reason string when it could
    # not (no ForkIndex available) -- a visible "not verified" marker,
    # distinct from both "verified clean" and "verified and broken". Does
    # NOT count toward `ok`: "could not check" is not the same failure class
    # as "checked and broken".
    engine_flag_check_skipped: str | None = None

    @property
    def ok(self) -> bool:
        return not (
            self.undeclared_writes
            or self.missing_transition_writes
            or self.owed_obligations
            or self.intro_seed_gaps
            or self.unresolved_engine_flags
        )


# --- fence scanning ---------------------------------------------------------


def scan_fenced_regions(engine_dir: Path) -> list[FencedRegion]:
    """Every sentinel-fenced region under `engine_dir/src` and
    `engine_dir/include` (C/H files).

    Handles both fence forms (`// BEGIN S — why` / `// S: why`, both closed
    by `// END S`) and same-sentinel nesting (a stack, matched innermost-
    first). Two real-tree quirks (found by scanning the whole vendored
    engine, see this function's test): a BARE opener line that is really
    just an inline mention of a sentinel's name (never gets its own `END`)
    is silently discarded rather than turned into a bogus region spanning
    everything up to some LATER, unrelated `END` of the same sentinel; an
    unclosed BARE opener at end-of-file (a genuine one-line marker) is
    likewise discarded. Neither is a failure -- see this module's tests for
    the exact real-tree line numbers. A `BEGIN`...`END` pair skipped over
    non-LIFO by a bare marker is still reported as its own well-formed
    region. An unclosed `BEGIN` (a REAL fence with no matching `END` at all
    in the file) is a genuinely malformed fence and raises.
    """
    regions: list[FencedRegion] = []
    files: list[Path] = []
    for pattern in _SOURCE_GLOBS:
        files.extend(sorted(engine_dir.glob(pattern)))

    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        # (sentinel, start_line, kind) kind is "BEGIN" or "BARE"
        stack: list[tuple[str, int, str]] = []

        for i, line in enumerate(lines, start=1):
            # -- fence tracking --
            mb = _BEGIN_RE.match(line)
            mbare = _BARE_RE.match(line)
            me = _END_RE.match(line)
            if mb:
                stack.append((mb.group(1), i, "BEGIN"))
            elif mbare:
                stack.append((mbare.group(1), i, "BARE"))
            elif me:
                sentinel = me.group(1)
                found_idx = None
                for j in range(len(stack) - 1, -1, -1):
                    if stack[j][0] == sentinel:
                        found_idx = j
                        break
                if found_idx is None:
                    raise ValueError(
                        f"story_state.engine_audit: unmatched '// END {sentinel}' "
                        f"at {path}:{i} -- no open fence for this sentinel"
                    )
                skipped = stack[found_idx + 1:]
                for skipped_sentinel, skipped_line, skipped_kind in skipped:
                    if skipped_kind == "BEGIN":
                        raise ValueError(
                            f"story_state.engine_audit: '// BEGIN {skipped_sentinel}' "
                            f"at {path}:{skipped_line} is never closed by its own "
                            f"'// END {skipped_sentinel}' -- a real fence was skipped "
                            f"over when '// END {sentinel}' closed at {path}:{i}"
                        )
                    # A BARE entry skipped over is an inline mention of a
                    # sentinel's name, not a real fence -- discard silently.
                opened_sentinel, opened_line, _kind = stack[found_idx]
                stack = stack[:found_idx]
                # Enclosing function at the region's OPEN line (best guess;
                # good enough for the two real sites and any reasonable
                # fixture -- the function doesn't usually change mid-fence).
                regions.append(FencedRegion(
                    path=path, sentinel=opened_sentinel,
                    start_line=opened_line, end_line=i,
                    function=_function_at_line(lines, opened_line),
                ))

        # End of file: any remaining BEGIN entries are genuinely unclosed
        # fences. Remaining BARE entries are one-line markers -- discard.
        for sentinel, line_no, kind in stack:
            if kind == "BEGIN":
                raise ValueError(
                    f"story_state.engine_audit: '// BEGIN {sentinel}' at "
                    f"{path}:{line_no} has no matching '// END {sentinel}' "
                    "before end of file"
                )

    return regions


def _function_at_line(lines: list[str], line_no: int) -> str | None:
    """Best-effort: the nearest enclosing top-level C function signature
    above `line_no` (1-indexed) whose brace hasn't yet closed by `line_no`.

    A column-0 line matching `_FUNC_SIG_RE`, immediately followed by a
    line that is just `{` (pokeemerald's brace style), opens a function;
    `entry_depth` is the brace depth *before* that opening brace is
    counted, so the function is considered closed once depth returns to
    `entry_depth` on some later line strictly before `line_no`.
    """
    depth = 0
    current: str | None = None
    entry_depth: int | None = None
    pending: str | None = None
    for i, line in enumerate(lines, start=1):
        if i > line_no:
            break
        if pending is not None and line.strip() == "{":
            current = pending
            entry_depth = depth
            pending = None
        elif (
            current is None
            and pending is None
            and not line.startswith((" ", "\t"))
            and _FUNC_SIG_RE.match(line)
        ):
            pending = _FUNC_SIG_RE.match(line).group(1)
        depth += line.count("{") - line.count("}")
        if current is not None and entry_depth is not None and depth <= entry_depth and i < line_no:
            current = None
            entry_depth = None
    return current


# --- write scanning ----------------------------------------------------


def fenced_state_writes(regions: list[FencedRegion]) -> list[FoundWrite]:
    """Every `FlagSet|FlagClear|FlagToggle|VarSet(...)` call whose line falls
    inside one of `regions` (inclusive of the region's open/close lines)."""
    by_path: dict[Path, list[FencedRegion]] = {}
    for r in regions:
        by_path.setdefault(r.path, []).append(r)

    found: list[FoundWrite] = []
    for path, path_regions in by_path.items():
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines, start=1):
            for m in _WRITE_CALL_RE.finditer(line):
                call, constant, value = m.group(1), m.group(2), m.group(3)
                # Innermost enclosing region wins (narrowest span containing i).
                enclosing = [r for r in path_regions if r.start_line <= i <= r.end_line]
                if not enclosing:
                    continue
                region = min(enclosing, key=lambda r: r.end_line - r.start_line)
                found.append(FoundWrite(
                    call=call, constant=constant,
                    value=value.strip() if value is not None else None,
                    path=path, line=i, function=_function_at_line(lines, i),
                    sentinel=region.sentinel,
                ))
    return found


# --- the audit itself ----------------------------------------------------


def audit(
    engine_dir: Path,
    flag_state: dict,
    intro_end_state: tuple[tuple[str, tuple], ...],
    chapter_read_keys: set[str],
    engine_index: ForkIndex | None = None,
) -> AuditReport:
    """Cross-checks the fenced engine against `transitions.py`'s
    declarations and the flag registry.

    `flag_state` is a loaded registry's `to_state()` dict (or an equivalent
    `{"switches": {...}, "variables": {...}}` mapping id-string -> constant
    name or `None`). `intro_end_state` is `ChapterStory.end_state` for
    INTRO. `chapter_read_keys` is every key repr (`switch:N`/`var:N`) some
    in-scope chapter row reads -- see `chapter_read_keys` below.

    `engine_index` is the fork-capability index (CLAUDE.md §4.7) used to
    check every `ruby_subset.builtins.ENGINE_ATTRIBUTES` flag actually
    resolves in the fork. `audit()` stays pure over its inputs -- it never
    builds the index itself (`run_real_audit` does that); `None` means "not
    verified" and is reported as such, never silently treated as clean.
    """
    regions = scan_fenced_regions(engine_dir)
    writes = fenced_state_writes(regions)

    declared: set[tuple[str, str, str]] = set()  # (call, constant, function)
    write_by_transition: dict[tuple[str, str, str], str] = {}
    for t in TRANSITIONS:
        for w in t.engine_writes:
            key = (w.call, w.constant, w.function)
            declared.add(key)
            write_by_transition[key] = t.name
    harness: set[tuple[str, str, str]] = {
        (h.write.call, h.write.constant, h.write.function) for h in HARNESS_ONLY
    }

    # A new_game.c write that matches the Intro seed is declared by the model
    # itself (C2 shape (d)), so it is not an undeclared write.
    gaps, unread, seed_writes = _intro_seed_gaps(
        engine_dir, writes, flag_state, intro_end_state, chapter_read_keys)

    undeclared: list[UndeclaredWrite] = []
    found_keys: set[tuple[str, str, str]] = set()
    for w in writes:
        key = (w.call, w.constant, w.function or "")
        found_keys.add(key)
        if key in declared or key in harness or (w.path, w.line) in seed_writes:
            continue
        undeclared.append(UndeclaredWrite(
            write=w,
            detail=(
                f"{w.path}:{w.line} {w.call}({w.constant}) inside "
                f"{w.function or '<unknown function>'} (fenced {w.sentinel}) is "
                "neither a declared EngineTransition.engine_writes entry, a "
                "HARNESS_ONLY write, nor a new_game.c write matching the Intro seed"
            ),
        ))

    missing: list[MissingTransitionWrite] = []
    for t in TRANSITIONS:
        for w in t.engine_writes:
            key = (w.call, w.constant, w.function)
            if key not in found_keys:
                missing.append(MissingTransitionWrite(
                    transition=t.name, write=w,
                    detail=(
                        f"transition {t.name!r} declares {w.call}({w.constant}) inside "
                        f"{w.function}, but no fenced engine code matches"
                    ),
                ))

    # Which switch ids the fenced code actually writes with FlagSet/FlagClear.
    written_switch_constants: set[str] = {
        w.constant for w in writes if w.call in ("FlagSet", "FlagClear")
    }
    owed: list[OwedObligation] = []
    deferred: list[str] = []
    switches = flag_state.get("switches", {})
    for ob in OBLIGATIONS:
        # Owed only once a row the ROM keeps reads one of its switches
        # (operator, 2026-09-16: R13 -- build what the chapters need). A
        # reader-less obligation is reported, not failed.
        if not any(f"switch:{sid}" in chapter_read_keys for sid in ob.switch_ids):
            deferred.append(
                f"obligation {ob.name!r} ({ob.pseudo_row_id}): no unstripped in-scope row "
                f"reads switches {list(ob.switch_ids)} -- not owed yet"
            )
            continue
        for sid in ob.switch_ids:
            constant = switches.get(str(sid))
            if constant is None:
                owed.append(OwedObligation(
                    obligation=ob.name, switch_id=sid,
                    detail=(
                        f"obligation {ob.name!r} ({ob.pseudo_row_id}): switch {sid} has "
                        "no registry constant (never named) -- the ROM has nothing to write"
                    ),
                ))
            elif constant not in written_switch_constants:
                owed.append(OwedObligation(
                    obligation=ob.name, switch_id=sid,
                    detail=(
                        f"obligation {ob.name!r} ({ob.pseudo_row_id}): switch {sid} "
                        f"({constant}) is never written by fenced FlagSet/FlagClear -- "
                        "owed"
                    ),
                ))

    unresolved_flags, flag_check_skipped = _engine_attribute_flag_check(engine_index)

    return AuditReport(
        undeclared_writes=tuple(undeclared),
        missing_transition_writes=tuple(missing),
        owed_obligations=tuple(owed),
        intro_seed_gaps=tuple(gaps),
        intro_seed_unread=tuple(unread),
        deferred_obligations=tuple(deferred),
        unresolved_engine_flags=unresolved_flags,
        engine_flag_check_skipped=flag_check_skipped,
    )


def _engine_attribute_flag_check(
    engine_index: ForkIndex | None,
) -> tuple[tuple[UnresolvedEngineFlag, ...], str | None]:
    """Checks every `ruby_subset.builtins.ENGINE_ATTRIBUTES` flag against
    `engine_index.constants` (CLAUDE.md §4.7's forward gate). Returns the
    findings and a skip-reason (`None` when the check ran)."""
    if engine_index is None:
        return (), (
            "engine_flag_check_skipped: no ForkIndex was supplied -- the "
            f"{len(ENGINE_ATTRIBUTES)} ENGINE_ATTRIBUTES flags were NOT "
            "verified against the fork"
        )

    unresolved: list[UnresolvedEngineFlag] = []
    for (namespace, attribute), engine_attr in ENGINE_ATTRIBUTES.items():
        if engine_attr.flag in engine_index.constants:
            continue
        unresolved.append(UnresolvedEngineFlag(
            namespace=namespace, attribute=attribute, flag=engine_attr.flag,
            detail=(
                f"{namespace}.{attribute} maps to {engine_attr.flag}, but "
                "the fork-capability index does not define that constant -- "
                "the pipeline would emit a symbol the fork doesn't have"
            ),
        ))
    return tuple(unresolved), None


def _intro_seed_gaps(
    engine_dir: Path,
    writes: list[FoundWrite],
    flag_state: dict,
    intro_end_state: tuple[tuple[str, tuple], ...],
    chapter_read_keys: set[str],
) -> tuple[list[IntroSeedGap], list[str], set[tuple[Path, int]]]:
    """Returns the gaps, the unread seed keys, and the `(path, line)` of every
    new_game.c write that satisfies a seed key (read by a chapter or not)."""
    new_game_path = (engine_dir / "src" / "new_game.c").resolve()
    new_game_writes = [w for w in writes if w.path.resolve() == new_game_path]

    switch_labels_path = Path(__file__).resolve().parents[3] / "reference" / "uranium_switches.json"
    labels: dict[str, str] = {}
    if switch_labels_path.is_file():
        import json
        labels = json.loads(switch_labels_path.read_text(encoding="utf-8"))

    switches = flag_state.get("switches", {})
    variables = flag_state.get("variables", {})

    gaps: list[IntroSeedGap] = []
    unread: list[str] = []
    seed_writes: set[tuple[Path, int]] = set()

    for key, values in intro_end_state:
        if key.startswith("self_switch:") or key.startswith("temp_switch:") or key.startswith("engine:"):
            continue
        if key.startswith("switch:"):
            sid = int(key.split(":", 1)[1])
            default = (False,)
            constant = switches.get(str(sid))
        elif key.startswith("var:"):
            sid = int(key.split(":", 1)[1])
            default = (0,)
            constant = variables.get(str(sid))
        else:
            continue

        if tuple(values) == default or set(values) == set(default):
            continue  # INTRO leaves this at the default -- nothing to seed

        satisfied = False
        if constant is not None:
            for w in new_game_writes:
                if w.constant != constant:
                    continue
                if key.startswith("switch:") and w.call == "FlagSet" and True in values:
                    satisfied = True
                    seed_writes.add((w.path, w.line))
                    break
                if key.startswith("switch:") and w.call == "FlagClear" and False in values:
                    satisfied = True
                    seed_writes.add((w.path, w.line))
                    break

        if key not in chapter_read_keys:
            unread.append(key)
            continue

        if not satisfied:
            gaps.append(IntroSeedGap(
                key=key, label=labels.get(str(sid)), constant=constant,
                intro_values=tuple(values),
                detail=(
                    f"{key} ({labels.get(str(sid), '<no uranium label>')}, registry "
                    f"constant {constant or '<none>'}) is set to {tuple(values)} by "
                    "INTRO but no fenced write in new_game.c sets it to match, and it "
                    "is read by an in-scope chapter row"
                ),
            ))

    return gaps, unread, seed_writes


# --- chapter_read_keys ---------------------------------------------------


def chapter_read_keys(
    build_dir: Path,
    chapter_ids: list[str],
    reference_dir: Path | None = None,
) -> set[str]:
    """Every state key (`switch:N`/`var:N`/`self_switch:...`/`temp_switch:...`)
    some row on `chapter_ids`'s own maps reads: its page appearance tests
    (page_tests) plus its own/ancestor arm-guard tests, plus every triggered
    common event's gating switch. Events in `strip_list.json`'s `map_events`
    are skipped: the ROM never carries them, so nothing they read is owed."""
    import json

    from rpg2gba.chapter_atlas.binding import load_binding
    from rpg2gba.chapter_manifest.schema import parse_row_id
    from rpg2gba.conversion_agent.flag_registry import load_label_tables
    from rpg2gba.conversion_agent.orchestrator import load_map_event_strips

    ref_dir = reference_dir or Path(__file__).resolve().parents[3] / "reference"
    stripped = set(load_map_event_strips(ref_dir))
    chapters_path = ref_dir / "chapters.json"
    binding = load_binding(path=chapters_path)
    common_events = json.loads((build_dir / "common_events.json").read_text(encoding="utf-8"))
    switch_labels, _var_labels = load_label_tables(
        ref_dir / "uranium_switches.json", ref_dir / "uranium_variables.json")

    keys: set[str] = set()

    pseudo_rows = extract_triggered_common_events(common_events, switch_labels=switch_labels)
    for row in pseudo_rows.values():
        for t in row.page_tests:
            keys.add(_state_key_repr(t.key))
        if row.arm_guard is not None:
            for t in row.arm_guard.tests:
                keys.add(_state_key_repr(t.key))

    for chapter_id in chapter_ids:
        for map_id in binding.chapter(chapter_id).maps:
            map_path = build_dir / "maps" / f"Map{map_id:03d}.json"
            if not map_path.is_file():
                continue
            map_data = json.loads(map_path.read_text(encoding="utf-8"))
            rows = extract_map(
                map_id, map_data, common_events=common_events, switch_labels=switch_labels)
            for row in rows.values():
                ref = parse_row_id(row.row_id)
                if (ref.map_id, ref.event_id) in stripped:
                    continue
                for t in row.page_tests:
                    keys.add(_state_key_repr(t.key))
                if row.arm_guard is not None:
                    for t in row.arm_guard.tests:
                        keys.add(_state_key_repr(t.key))

    return keys


def run_real_audit(build_dir: Path | None = None) -> AuditReport:
    """Convenience: audits `engine/` against the registry state persisted at
    `<build_dir>/flag_state.json` (default `output/uranium-build`) and
    CH01..CH05's INTRO seed."""
    from rpg2gba.story_state.model import build_chapter_stories

    repo_root = Path(__file__).resolve().parents[3]
    engine_dir = repo_root / "engine"
    if build_dir is None:
        build_dir = repo_root / "output" / "uranium-build"
    chapters_path = repo_root / "reference" / "chapters.json"

    registry = FlagRegistry.load(build_dir / "flag_state.json")
    flag_state = registry.to_state()

    chapter_ids = ["CH01", "CH02", "CH03", "CH04", "CH05"]
    stories = build_chapter_stories(chapter_ids, build_dir=build_dir, chapters_path=chapters_path)
    intro_end_state = stories["INTRO"].end_state

    read_keys = chapter_read_keys(build_dir, chapter_ids)

    try:
        engine_index: ForkIndex | None = load_or_build(repo_root)
    except Exception:
        # A failure to build the fork-capability index (e.g. no `engine/`
        # tree, or a build-tool problem unrelated to this audit's own
        # checks) must not crash the whole engine-audit command -- it
        # degrades to a visible "not verified" marker instead (R3), so a
        # caller still sees the rest of the report rather than a traceback.
        logger.warning(
            "engine_audit: failed to build ForkIndex, engine-flag check "
            "will report as skipped", exc_info=True,
        )
        engine_index = None

    return audit(engine_dir, flag_state, intro_end_state, read_keys, engine_index=engine_index)


def format_report(report: AuditReport) -> str:
    lines: list[str] = []
    lines.append(f"engine audit: {'OK' if report.ok else 'NOT OK'}")

    lines.append(f"undeclared_writes ({len(report.undeclared_writes)}):")
    for u in report.undeclared_writes:
        lines.append(f"  - {u.detail}")

    lines.append(f"missing_transition_writes ({len(report.missing_transition_writes)}):")
    for m in report.missing_transition_writes:
        lines.append(f"  - {m.detail}")

    lines.append(f"owed_obligations ({len(report.owed_obligations)}):")
    for o in report.owed_obligations:
        lines.append(f"  - {o.detail}")

    lines.append(f"intro_seed_gaps ({len(report.intro_seed_gaps)}):")
    for g in report.intro_seed_gaps:
        lines.append(f"  - {g.detail}")

    lines.append(f"intro_seed_unread ({len(report.intro_seed_unread)}, informational):")
    for k in report.intro_seed_unread:
        lines.append(f"  - {k}")

    lines.append(f"deferred_obligations ({len(report.deferred_obligations)}, informational):")
    for d in report.deferred_obligations:
        lines.append(f"  - {d}")

    lines.append(f"unresolved_engine_flags ({len(report.unresolved_engine_flags)}):")
    for f in report.unresolved_engine_flags:
        lines.append(f"  - {f.detail}")
    if report.engine_flag_check_skipped is not None:
        lines.append(f"  - skipped: {report.engine_flag_check_skipped}")

    return "\n".join(lines)
