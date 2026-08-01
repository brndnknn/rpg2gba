"""Fork capability index + forward verification gate (BUILD_PLAN spine task #1).

The pipeline once emitted an invented command `healparty` while the vendored
engine had `HealPlayerParty` defined as a special the whole time (CLAUDE.md
§4.7). This module makes that class of bug structurally impossible to ship:
it extracts a symbol table (specials, script-command macros, movement tokens,
constants) from the PRISTINE git-tracked `engine/` source — never the working
tree, which may contain pipeline-generated headers with Uranium-specific
symbols — and exposes `verify_script()` to check emitted Poryscript against
that table before it ever reaches `make modern`.

A violation reported by `verify_script()` is OUR bug: the transpiler (or a
caller) emitted a symbol the fork doesn't define. Callers must abort loud —
never silently drop the offending line, never queue it for the LLM tail tool.
The tail tool's job is branch-heavy story logic and novel embedded Ruby, not
papering over a transpiler emitting nonexistent commands.

Usage:
    python -m rpg2gba.conversion_agent.fork_index build
    python -m rpg2gba.conversion_agent.fork_index check some.pory
    python -m rpg2gba.conversion_agent.fork_index resolve HealPlayerParty
    python -m rpg2gba.conversion_agent.fork_index search "heal.*party"
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import click

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (relative to the repo root, as recorded in git)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]

_SPECIALS_PATH = "engine/data/specials.inc"
_EVENT_MACROS_PATH = "engine/asm/macros/event.inc"
_CHARMAP_PATH = "engine/charmap.txt"
_MOVEMENT_PATH = "engine/asm/macros/movement.inc"
_CONSTANTS_DIR = "engine/include/constants"
# TRUE/FALSE (used by e.g. multichoice args) live outside include/constants/.
_EXTRA_CONSTANT_HEADERS = ["engine/include/gba/defines.h"]

# Bump whenever extraction logic changes — the cache is keyed on
# (tree_hash, format), so a logic change must invalidate hash-matching caches.
_INDEX_FORMAT = 4

# def_special invocations (excludes the .macro def_special line). 623 upstream
# + 1 rpg2gba addition (RPG2GBA_SetObjectEventGfx, the RMXP move-command 41
# live sprite swap). Bump deliberately when the fork gains a special — the
# whole point of the pin is that drift is noticed.
_EXPECTED_SPECIALS_DECLS = 624
_EXPECTED_MACROS = 385
_CONSTANTS_FLOOR = 10_000

# ---------------------------------------------------------------------------
# Extraction regexes
# ---------------------------------------------------------------------------

_DEF_SPECIAL_RE = re.compile(r"^\s*def_special[,\s]+([A-Za-z_]\w*)")
_MACRO_DEF_RE = re.compile(r"^\t\.macro\s+([A-Za-z_]\w*)")
_MOVEMENT_ACTION_RE = re.compile(r"^\s*create_movement_action\s+([A-Za-z_]\w*)\s*,")
# Assembler symbol assignments, e.g. `MSGBOX_SIGN = 3` in event.inc — these
# are constants scripts pass as args, but they're not C #defines.
_ASM_CONST_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=")

_LINE_COMMENT_RE = re.compile(r"//.*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

_DEFINE_RE = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)(\()?")
_GUARD_RE = re.compile(r"^GUARD_")
_ENUM_BLOCK_RE = re.compile(r"\benum\b[^{;]*\{([^{}]*)\}", re.DOTALL)
_ENUM_MEMBER_RE = re.compile(r"^\s*([A-Za-z_]\w*)")

# ---------------------------------------------------------------------------
# Poryscript builtin/keyword surface (reference/guides/poryscript_cheatsheet.md).
# Names that are both builtins and macros is fine — set union at check time.
# ---------------------------------------------------------------------------

PORYSCRIPT_BUILTINS: frozenset[str] = frozenset(
    {
        "script", "movement", "text", "mart", "if", "elif", "else", "switch",
        "case", "default", "while", "do", "break", "continue", "end", "return",
        "goto", "lock", "release", "faceplayer", "flag", "var", "defeated",
        "value", "format", "msgbox", "giveitem", "givemon", "checkitemspace",
        "additem", "removeitem", "givemoney", "removemoney",
        "trainerbattle_single", "trainerbattle_double", "setflag", "clearflag",
        "setvar", "addvar", "applymovement", "waitmovement", "warp", "special",
        "specialvar", "poryswitch",
    }
)

_SPECIAL_CALL_RE = re.compile(r"\bspecial\(\s*([A-Za-z_]\w*)\s*\)")
_SPECIALVAR_CALL_RE = re.compile(
    r"\bspecialvar\(\s*([A-Za-z_]\w*)\s*,\s*([A-Za-z_]\w*)\s*\)"
)
_ALL_CAPS_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_CALL_POSITION_RE = re.compile(r"\b([a-z][a-z0-9_]*)\s*\(")
_MOVEMENT_BLOCK_RE = re.compile(r"\bmovement\s+\w+\s*\{([^{}]*)\}", re.DOTALL)
_MOVEMENT_TOKEN_RE = re.compile(r"^\s*([a-z][a-z0-9_]*)")
_BLOCK_KEYWORD_RE = re.compile(r"\s*(script|movement|text|mart)\b")
_BARE_STATEMENT_RE = re.compile(r"^\s*([a-z][a-z0-9_]*)\s*(.?)")


# ---------------------------------------------------------------------------
# Git plumbing — content always comes from HEAD, never the working tree.
# ---------------------------------------------------------------------------


def _run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _git_show(repo_root: Path, path: str) -> str:
    return _run_git(repo_root, ["show", f"HEAD:{path}"])


def _git_ls_files(repo_root: Path, path: str) -> list[str]:
    out = _run_git(repo_root, ["ls-files", path])
    return [line for line in out.splitlines() if line]


def tree_hash(repo_root: Path = _REPO_ROOT) -> str:
    """Cache key: the git tree hash of the `engine/` subtree at HEAD."""
    out = _run_git(repo_root, ["rev-parse", "HEAD:engine"])
    return out.strip()


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def _strip_c_comments(text: str) -> str:
    text = _BLOCK_COMMENT_RE.sub(" ", text)
    text = _LINE_COMMENT_RE.sub("", text)
    return text


def _extract_specials(repo_root: Path) -> set[str]:
    text = _git_show(repo_root, _SPECIALS_PATH)
    names: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith(".macro"):
            continue  # the `.macro def_special, ptr:req, ...` definition line
        m = _DEF_SPECIAL_RE.match(line)
        if m:
            names.append(m.group(1))
    if len(names) != _EXPECTED_SPECIALS_DECLS:
        raise ValueError(
            f"expected {_EXPECTED_SPECIALS_DECLS} def_special declarations in "
            f"{_SPECIALS_PATH}, found {len(names)} — extraction regex or fork "
            f"file drifted, fix before trusting the index"
        )
    return set(names)


def _extract_script_macros(repo_root: Path) -> set[str]:
    text = _git_show(repo_root, _EVENT_MACROS_PATH)
    names = {m.group(1) for line in text.splitlines() if (m := _MACRO_DEF_RE.match(line))}
    if len(names) != _EXPECTED_MACROS:
        raise ValueError(
            f"expected {_EXPECTED_MACROS} script macros in {_EVENT_MACROS_PATH}, "
            f"found {len(names)} — extraction regex or fork file drifted"
        )
    return names


def _extract_movement_tokens(repo_root: Path) -> set[str]:
    text = _git_show(repo_root, _MOVEMENT_PATH)
    names: set[str] = set()
    for line in text.splitlines():
        if line.lstrip().startswith(".macro"):
            continue  # the create_movement_action meta-macro definition itself
        m = _MOVEMENT_ACTION_RE.match(line)
        if m:
            names.add(m.group(1))
    if not names:
        raise ValueError(
            f"found zero movement tokens in {_MOVEMENT_PATH} — extraction "
            f"regex or fork file drifted"
        )
    return names


def _extract_constants_from_header(text: str) -> set[str]:
    text = _strip_c_comments(text)
    names: set[str] = set()

    for line in text.splitlines():
        m = _DEFINE_RE.match(line)
        if not m:
            continue
        name, is_function_like = m.group(1), m.group(2)
        if is_function_like:
            continue  # function-like macro, e.g. #define FOO(x) ...
        if _GUARD_RE.match(name):
            continue  # header include-guard
        names.add(name)

    for block in _ENUM_BLOCK_RE.findall(text):
        for segment in block.split(","):
            m = _ENUM_MEMBER_RE.match(segment)
            if m:
                names.add(m.group(1))

    return names


def _extract_asm_constants(repo_root: Path) -> set[str]:
    """ALL_CAPS symbol assignments in event.inc (e.g. `MSGBOX_SIGN = 3`)."""
    text = _git_show(repo_root, _EVENT_MACROS_PATH)
    names = {m.group(1) for line in text.splitlines() if (m := _ASM_CONST_RE.match(line))}
    if "MSGBOX_SIGN" not in names:
        raise ValueError(
            f"MSGBOX_SIGN not found among asm constants in {_EVENT_MACROS_PATH} "
            f"— extraction regex or fork file drifted"
        )
    return names


def _extract_charmap_constants(repo_root: Path) -> set[str]:
    """Multi-character ALL_CAPS symbols assigned in `charmap.txt`.

    The string-var placeholders scripts pass to `buffer*` commands
    (`STR_VAR_1 = FD 02`) live only here — not in any `constants/*.h` and not
    in `event.inc` — so without this the gate rejects `bufferspeciesname
    STR_VAR_1, ...`, which is exactly what vanilla's own scripts do.

    Deliberately restricted to names of 2+ characters: charmap.txt also
    assigns every single letter and digit (`A = BB`), and admitting those
    would let a bare typo'd `A` sail through the gate.
    """
    text = _git_show(repo_root, _CHARMAP_PATH)
    names = {
        m.group(1)
        for line in text.splitlines()
        if (m := _ASM_CONST_RE.match(line)) and len(m.group(1)) > 1
    }
    if "STR_VAR_1" not in names:
        raise ValueError(
            f"STR_VAR_1 not found among charmap symbols in {_CHARMAP_PATH} "
            f"— extraction regex or fork file drifted"
        )
    return names


def _extract_constants(repo_root: Path) -> set[str]:
    headers = [
        p for p in _git_ls_files(repo_root, _CONSTANTS_DIR) if p.endswith(".h")
    ]
    headers += _EXTRA_CONSTANT_HEADERS
    names: set[str] = set()
    for header in headers:
        text = _git_show(repo_root, header)
        names |= _extract_constants_from_header(text)
    names |= _extract_charmap_constants(repo_root)
    if len(names) < _CONSTANTS_FLOOR:
        raise ValueError(
            f"expected >= {_CONSTANTS_FLOOR} constants across {len(headers)} "
            f"headers under {_CONSTANTS_DIR}, found {len(names)} — extraction "
            f"regex or fork tree drifted"
        )
    return names


# ---------------------------------------------------------------------------
# ForkIndex
# ---------------------------------------------------------------------------


@dataclass
class ForkIndex:
    """The fork's symbol surface, extracted from git-tracked `engine/` source.

    Never hand-edit this or its cache file. If a category looks wrong, fix
    the extraction regex/logic above and rebuild — the cache is a derived
    artifact, not a source of truth.
    """

    specials: set[str] = field(default_factory=set)
    script_macros: set[str] = field(default_factory=set)
    movement_tokens: set[str] = field(default_factory=set)
    constants: set[str] = field(default_factory=set)
    tree_hash: str = ""

    def to_json(self) -> dict:
        return {
            "format": _INDEX_FORMAT,
            "specials": sorted(self.specials),
            "script_macros": sorted(self.script_macros),
            "movement_tokens": sorted(self.movement_tokens),
            "constants": sorted(self.constants),
            "tree_hash": self.tree_hash,
        }

    @classmethod
    def from_json(cls, data: dict) -> ForkIndex:
        return cls(
            specials=set(data["specials"]),
            script_macros=set(data["script_macros"]),
            movement_tokens=set(data["movement_tokens"]),
            constants=set(data["constants"]),
            tree_hash=data["tree_hash"],
        )

    def validate(self) -> None:
        if not self.specials:
            raise ValueError("ForkIndex.specials is empty")
        if not self.script_macros:
            raise ValueError("ForkIndex.script_macros is empty")
        if not self.movement_tokens:
            raise ValueError("ForkIndex.movement_tokens is empty")
        if len(self.constants) < _CONSTANTS_FLOOR:
            raise ValueError(
                f"ForkIndex.constants has {len(self.constants)} entries, "
                f"below the {_CONSTANTS_FLOOR} sanity floor"
            )


def build(repo_root: Path = _REPO_ROOT) -> ForkIndex:
    """Build a fresh ForkIndex from git HEAD (never the working tree)."""
    return ForkIndex(
        specials=_extract_specials(repo_root),
        script_macros=_extract_script_macros(repo_root),
        movement_tokens=_extract_movement_tokens(repo_root),
        constants=_extract_constants(repo_root) | _extract_asm_constants(repo_root),
        tree_hash=tree_hash(repo_root),
    )


def _cache_path() -> Path:
    out_dir = Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"
    return out_dir / "fork_index.json"


def load_or_build(
    repo_root: Path = _REPO_ROOT, cache_path: Path | None = None
) -> ForkIndex:
    """Load the cached index if it matches the current tree hash, else rebuild."""
    path = cache_path if cache_path is not None else _cache_path()
    current_hash = tree_hash(repo_root)

    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("tree_hash") == current_hash and data.get("format") == _INDEX_FORMAT:
                index = ForkIndex.from_json(data)
                index.validate()
                logger.info("fork_index: loaded cache at %s (tree_hash=%s)", path, current_hash)
                return index
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("fork_index: cache at %s unreadable (%s), rebuilding", path, exc)

    logger.info("fork_index: cache stale or missing, rebuilding from git HEAD")
    index = build(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index.to_json(), indent=2), encoding="utf-8")
    return index


# ---------------------------------------------------------------------------
# Forward verification gate
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    symbol: str
    kind: str  # "constant" | "command" | "special" | "movement"
    line_no: int
    context: str


def _strip_line(line: str) -> str:
    """Strip double-quoted string literals and #/// comments from one line."""
    out: list[str] = []
    in_string = False
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if in_string:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        if c == "#":
            break
        if c == "/" and i + 1 < n and line[i + 1] == "/":
            break
        out.append(c)
        i += 1
    return "".join(out)


def verify_script(
    pory_text: str,
    index: ForkIndex,
    *,
    extra_symbols: set[str] | None = None,
    extra_patterns: list[re.Pattern] | None = None,
) -> list[Violation]:
    """Check emitted Poryscript against the fork's real symbol surface.

    A returned violation is OUR bug (§ module docstring) — callers abort
    loud, they never silently drop the line or route it to the LLM tail tool.
    """
    extra_symbols = extra_symbols if extra_symbols is not None else set()
    if extra_patterns is None:
        extra_patterns = [re.compile(r"^FLAG_MAP\d+_EVENT\d+_\w+$")]

    def _extra_ok(name: str) -> bool:
        if name in extra_symbols:
            return True
        return any(p.search(name) for p in extra_patterns)

    lines = pory_text.splitlines()
    stripped = [_strip_line(line) for line in lines]

    violations: list[Violation] = []

    for line_no, line in enumerate(stripped, start=1):
        raw = lines[line_no - 1]

        # Rule 3: special()/specialvar() argument names must resolve as specials.
        for m in _SPECIAL_CALL_RE.finditer(line):
            name = m.group(1)
            if name not in index.specials:
                violations.append(Violation(name, "special", line_no, raw))
        for m in _SPECIALVAR_CALL_RE.finditer(line):
            name = m.group(2)
            if name not in index.specials:
                violations.append(Violation(name, "special", line_no, raw))

        # Rule 1: ALL_CAPS identifiers must resolve as constants (or extras).
        for m in _ALL_CAPS_RE.finditer(line):
            name = m.group(0)
            if name in index.constants:
                continue
            if _extra_ok(name):
                continue
            violations.append(Violation(name, "constant", line_no, raw))

        # Rule 2: lowercase call-position identifiers must resolve as
        # script macros or poryscript builtins.
        for m in _CALL_POSITION_RE.finditer(line):
            name = m.group(1)
            if name in index.script_macros or name in PORYSCRIPT_BUILTINS:
                continue
            violations.append(Violation(name, "command", line_no, raw))

    # Rule 4: bare lowercase tokens inside movement { ... } blocks must
    # resolve as movement tokens.
    full_stripped = "\n".join(stripped)
    for block_match in _MOVEMENT_BLOCK_RE.finditer(full_stripped):
        block_start_line = full_stripped.count("\n", 0, block_match.start()) + 1
        block_text = block_match.group(1)
        for offset, block_line in enumerate(block_text.splitlines()):
            token_line = block_line.strip()
            if not token_line:
                continue
            token_line = token_line.split("*")[0].strip()
            m = _MOVEMENT_TOKEN_RE.match(token_line)
            if not m:
                continue
            name = m.group(1)
            if name not in index.movement_tokens:
                line_no = block_start_line + offset
                raw = lines[line_no - 1] if 0 <= line_no - 1 < len(lines) else block_line
                violations.append(Violation(name, "movement", line_no, raw))

    # Rule 5: inside `script <Label> { ... }` blocks (NOT movement/text/mart
    # blocks — rule 4 owns movement), a statement whose first token is a
    # lowercase identifier NOT followed by `(` must resolve as a script macro
    # or poryscript builtin. Catches bare no-paren invented commands like
    # `healparty` (the exact historical bug); bare `end`/`release`/`faceplayer`
    # pass via the builtin whitelist. Parenthesized statements are rule 2's
    # job — never double-reported here.
    block_stack: list[str] = []
    for line_no, line in enumerate(stripped, start=1):
        raw = lines[line_no - 1]
        kw_match = _BLOCK_KEYWORD_RE.match(line)
        line_kind = kw_match.group(1) if kw_match else None

        in_script = "script" in block_stack and not any(
            k in ("movement", "text", "mart") for k in block_stack
        )
        if in_script and line_kind is None:
            m = _BARE_STATEMENT_RE.match(line)
            if m:
                name, next_char = m.group(1), m.group(2)
                if next_char not in ("(", ":"):  # rule 2 owns calls; skip labels
                    if name not in index.script_macros and name not in PORYSCRIPT_BUILTINS:
                        violations.append(Violation(name, "command", line_no, raw))

        # Track block nesting: the first `{` on a script/movement/text/mart
        # header line opens that kind; any other `{` (if/elif/while/...) opens
        # a plain scope that inherits its parent.
        kind_pending = line_kind
        for ch in line:
            if ch == "{":
                block_stack.append(kind_pending if kind_pending is not None else "plain")
                kind_pending = None
            elif ch == "}":
                if block_stack:
                    block_stack.pop()

    return violations


# ---------------------------------------------------------------------------
# Reserved-var write guard.
#
# VAR_TEMP_F is reserved as the coord-event gate var (porymap coord events
# fire only while their var equals value; the pipeline gates every coord
# event on VAR_TEMP_F == 0) and must NEVER be written by any emitted script.
# VAR_TEMP_C is reserved as the ON_FRAME map-script guard var and may ONLY be
# written by the metadata_wiring map-script emitter (a separate module), never
# by transpiler output or hand overrides.
#
# This is intentionally NOT folded into verify_script(): the staging gate in
# assemble_pathfinder also calls verify_script over already-staged files,
# which legitimately contain the wiring emitter's own
# `setvar(VAR_TEMP_C, 1)`. The reserved-write check only runs at the
# transpile_driver conversion-time gate, before that legitimate write exists.
# ---------------------------------------------------------------------------

RESERVED_WRITE_VARS: tuple[str, ...] = ("VAR_TEMP_F", "VAR_TEMP_C")

# First-argument writers: setvar/copyvar/addvar/subvar/specialvar all write
# their first argument. (random() has no var argument of its own — its
# result is captured by a following copyvar(), already covered here.)
_RESERVED_WRITE_CALL_RE = re.compile(
    r"\b(?:setvar|copyvar|addvar|subvar|specialvar)\(\s*([A-Za-z_]\w*)"
)
# getplayerxy(x_var, y_var) writes both arguments.
_RESERVED_GETPLAYERXY_RE = re.compile(
    r"\bgetplayerxy\(\s*([A-Za-z_]\w*)\s*,\s*([A-Za-z_]\w*)"
)


def check_reserved_var_writes(
    pory_text: str, reserved: Sequence[str] = RESERVED_WRITE_VARS
) -> list[Violation]:
    """Flag any command that WRITES a reserved gate/guard var.

    Reuses `_strip_line` (string/comment masking) so msgbox text or comments
    that merely mention a reserved var name never false-positive. Matches
    the reserved name as a whole written operand (regex identifiers are
    matched in full via `\\w*`, so `VAR_TEMP_F2` never collides with
    `VAR_TEMP_F`) — a bare read like `var(VAR_TEMP_F) == 0` never matches
    since `var(` is not one of the writer command names.
    """
    reserved_set = set(reserved)
    lines = pory_text.splitlines()
    stripped = [_strip_line(line) for line in lines]

    violations: list[Violation] = []
    for line_no, line in enumerate(stripped, start=1):
        raw = lines[line_no - 1]
        for m in _RESERVED_WRITE_CALL_RE.finditer(line):
            name = m.group(1)
            if name in reserved_set:
                violations.append(Violation(name, "reserved_var", line_no, raw))
        for m in _RESERVED_GETPLAYERXY_RE.finditer(line):
            for name in (m.group(1), m.group(2)):
                if name in reserved_set:
                    violations.append(Violation(name, "reserved_var", line_no, raw))

    return violations


# ---------------------------------------------------------------------------
# Registry extras (grill D3: gate resolves index ∪ flag registry ∪
# map-constant registry — Uranium-minted namespaces come from their own
# single sources of truth, never from working-tree engine headers).
# ---------------------------------------------------------------------------


def registry_extra_symbols(
    flag_state_path: Path | None = None,
    map_constants_path: Path | None = None,
    species_manifest_path: Path | None = None,
    npc_gfx_map_path: Path | None = None,
) -> set[str]:
    """Collect Uranium-minted symbols the gate should accept beyond the index.

    - `flag_state_path`: the flag registry's persistent state
      (`output/uranium-build/flag_state.json`) — all minted FLAG_*/VAR_* names.
    - `map_constants_path`: the map-constant registry
      (`output/uranium-build/porymap/map_constants.json`) — minted MAP_*/
      MAP_URANIUM_*/LAYOUT_*/MAPSEC_* names.
    - `species_manifest_path`: the species staging manifest
      (`output/uranium-build/species/species_manifest.json`, written by
      `rpg2gba.species_converter.stage`) — SPECIES_*/NATIONAL_DEX_*/CRY_*
      constants for the species that have actually been staged into the
      fork. ONLY species listed here pass the gate — a Uranium species that
      merely appears in `reference/uranium_id_map.json` (e.g. under
      `needs_engine.species`) but hasn't been staged must still be rejected;
      this deliberately does not widen to the full id-map species table.
    - `npc_gfx_map_path`: the NPC sprite map (`reference/npc_gfx_map.json`,
      §4.3 SoT) — the `OBJ_EVENT_GFX_URANIUM_*` constants the sprite pass
      mints into `engine/**/uranium_*.gen.h`. Those headers are generated and
      gitignored, so the index (built from git-tracked `engine/` source) can
      never see them; without this the code-41 live sprite swap gates as an
      invented constant. Both the sheet's own `gfx` and every per-state
      constant under `states` contribute — the same table, and the same
      entries, the transpiler resolves through, so a sheet or state it would
      queue as unmapped cannot slip past the gate here.

    Missing categories inside any of these files fail loud (KeyError) — a
    shape drift there means the registry changed and this glue must follow.
    A `None` path (the manifest hasn't been generated yet, e.g. before the
    species converter has ever run) contributes no symbols and is not an
    error.
    """
    extras: set[str] = set()

    if flag_state_path is not None:
        state = json.loads(flag_state_path.read_text(encoding="utf-8"))
        # NOTE: "script_switches" is a list of s:-predicate ids (never minted
        # as flags — CLAUDE.md §6), so it contributes no symbols here.
        for category in ("switches", "variables", "self_switches", "temp_switches"):
            for name in state[category].values():
                if isinstance(name, str) and name:
                    extras.add(name)

    if map_constants_path is not None:
        consts = json.loads(map_constants_path.read_text(encoding="utf-8"))
        for entry in consts.values():
            for key in ("map_const", "alias_const", "layout_const", "mapsec_const"):
                extras.add(entry[key])

    if species_manifest_path is not None:
        manifest = json.loads(species_manifest_path.read_text(encoding="utf-8"))
        for entry in manifest["species"]:
            for key in ("species_constant", "national_dex_constant", "cry_constant"):
                extras.add(entry[key])

    if npc_gfx_map_path is not None:
        gfx_map = json.loads(npc_gfx_map_path.read_text(encoding="utf-8"))
        for entry in gfx_map.values():
            if not isinstance(entry, dict):
                continue
            if entry.get("gfx"):
                extras.add(entry["gfx"])
            # Multi-state sheets (large props) mint one constant per selectable
            # (direction, pattern); the code-41 swap targets those directly.
            for gfx in (entry.get("states") or {}).values():
                if gfx:
                    extras.add(gfx)

    return extras


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """Fork capability index — build, check scripts, resolve symbols, search."""


@cli.command(name="build")
def build_cmd() -> None:  # pragma: no cover - thin CLI wrapper
    """Force a rebuild of the fork index and print category counts."""
    index = build()
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index.to_json(), indent=2), encoding="utf-8")
    click.echo(f"tree_hash: {index.tree_hash}")
    click.echo(f"specials: {len(index.specials)}")
    click.echo(f"script_macros: {len(index.script_macros)}")
    click.echo(f"movement_tokens: {len(index.movement_tokens)}")
    click.echo(f"constants: {len(index.constants)}")
    click.echo(f"cached at: {path}")


@cli.command()
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--allow-flags-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="JSON list of extra allowed symbols.",
)
@click.option(
    "--flag-state",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Flag registry state file (flag_state.json).",
)
@click.option(
    "--map-constants",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Map-constant registry file (map_constants.json).",
)
@click.option(
    "--species-manifest",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Species staging manifest file (species_manifest.json).",
)
def check(
    files: tuple[Path, ...],
    allow_flags_file: Path | None,
    flag_state: Path | None,
    map_constants: Path | None,
    species_manifest: Path | None,
) -> None:  # pragma: no cover
    """Run verify_script over one or more .pory files."""
    index = load_or_build()
    extra_symbols = registry_extra_symbols(flag_state, map_constants, species_manifest)
    if allow_flags_file is not None:
        extra_symbols |= set(json.loads(allow_flags_file.read_text(encoding="utf-8")))

    any_violations = False
    for file_path in files:
        text = file_path.read_text(encoding="utf-8")
        violations = verify_script(text, index, extra_symbols=extra_symbols)
        for v in violations:
            any_violations = True
            click.echo(f"{file_path}:{v.line_no}: [{v.kind}] {v.symbol} — {v.context.strip()}")

    if any_violations:
        raise SystemExit(1)
    click.echo(f"OK — {len(files)} file(s), no violations")


@cli.command()
@click.argument("symbols", nargs=-1, required=True)
def resolve(symbols: tuple[str, ...]) -> None:  # pragma: no cover
    """Print which category each symbol resolves in."""
    index = load_or_build()
    any_miss = False
    for symbol in symbols:
        hits = []
        if symbol in index.specials:
            hits.append("special")
        if symbol in index.script_macros:
            hits.append("script_macro")
        if symbol in index.movement_tokens:
            hits.append("movement_token")
        if symbol in index.constants:
            hits.append("constant")
        if symbol in PORYSCRIPT_BUILTINS:
            hits.append("builtin")
        if hits:
            click.echo(f"{symbol}: {', '.join(hits)}")
        else:
            any_miss = True
            click.echo(f"{symbol}: NOT FOUND")
    if any_miss:
        raise SystemExit(1)


@cli.command()
@click.argument("term")
def search(term: str) -> None:  # pragma: no cover
    """Reverse-gate helper: grep the pristine engine/ tree for a term."""
    result = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "grep", "-n", "-i", term, "HEAD", "--", "engine/"],
        capture_output=True,
        text=True,
    )
    lines = result.stdout.splitlines()
    for line in lines[:200]:
        click.echo(line)
    if len(lines) > 200:
        click.echo(f"... truncated, {len(lines) - 200} more lines")


if __name__ == "__main__":  # pragma: no cover
    cli()
