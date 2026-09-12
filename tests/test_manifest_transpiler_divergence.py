"""Guards against project issue #97: the manifest's hand-maintained lookup
tables (`_CODE_EFFECT`/`_HEAD_EFFECT` in `chapter_manifest/generator.py`,
`MECHANIC_BY_HEAD` in `chapter_atlas/census.py`) drifting from what the
transpiler (`conversion_agent/transpiler.py`) actually emits. #97 happened
because these two layers — recognition (manifest) and emission (transpiler)
— were never checked against each other; rows got flagged "unrecognized"
that the transpiler had handled all along (codes 104/116/221/222, just
closed).

Two independent failure modes are covered:

1. A duplicate key in one of the hand-maintained dict literals silently
   shadows an earlier entry (a real `pbRockSmash` duplicate in
   `MECHANIC_BY_HEAD` was just removed). Caught via `ast` on the *source
   text* — importing the module is useless here, since by the time the
   dict object exists Python has already silently resolved the collision.
2. The set of RMXP command codes the transpiler handles and the set the
   manifest tables classify diverging. Caught by deriving both sets
   structurally (not by hand-copying either list into this file) and
   diffing them.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CENSUS_PATH = REPO_ROOT / "src" / "rpg2gba" / "chapter_atlas" / "census.py"
GENERATOR_PATH = REPO_ROOT / "src" / "rpg2gba" / "chapter_manifest" / "generator.py"
TRANSPILER_PATH = REPO_ROOT / "src" / "rpg2gba" / "conversion_agent" / "transpiler.py"


def _dict_literal_assignments(source: Path, names: set[str]) -> dict[str, ast.Dict]:
    """Parse `source` and return {name: ast.Dict node} for every module-level
    `NAME: ... = {...}` (or bare `NAME = {...}`) assignment whose target is
    in `names`. Walks top-level `Assign` and `AnnAssign` nodes only — these
    tables are all plain module globals, not nested in a function/class."""
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    found: dict[str, ast.Dict] = {}
    for node in tree.body:
        target_name: str | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
        if target_name in names and isinstance(node.value, ast.Dict):
            found[target_name] = node.value
    return found


def _literal_key_text(key_node: ast.expr) -> str | int | None:
    """Best-effort literal rendering of a dict key node, for duplicate
    detection. Returns None for keys that aren't simple constants (nothing
    in the tables under test uses anything else, but a non-constant key
    should never silently pass as "no duplicate")."""
    if isinstance(key_node, ast.Constant):
        return key_node.value
    return None


def _assert_no_duplicate_keys(dict_node: ast.Dict, table_name: str, source: Path) -> None:
    seen: dict[object, int] = {}
    dupes: list[str] = []
    for key_node in dict_node.keys:
        if key_node is None:  # a `**spread` entry — not used by these tables
            continue
        key = _literal_key_text(key_node)
        if key is None:
            continue
        line = key_node.lineno
        if key in seen:
            dupes.append(
                f"{key!r} first at {source.name}:{seen[key]}, "
                f"repeated at {source.name}:{line}"
            )
        else:
            seen[key] = line
    assert not dupes, (
        f"{table_name} in {source} has duplicate literal keys — a later "
        f"entry silently shadows an earlier one:\n" + "\n".join(dupes)
    )


def test_no_duplicate_keys_in_head_and_code_tables() -> None:
    """AST-level duplicate-key guard for the three hand-maintained lookup
    tables. Must inspect source text, not the imported dict object: by
    import time Python has already collapsed any duplicate key to its last
    value, which is exactly the bug this test exists to catch."""
    census_tables = _dict_literal_assignments(CENSUS_PATH, {"MECHANIC_BY_HEAD"})
    assert "MECHANIC_BY_HEAD" in census_tables, (
        f"MECHANIC_BY_HEAD dict literal not found in {CENSUS_PATH} — "
        "either it moved or is no longer a plain module-level dict literal; "
        "update this test's discovery logic"
    )
    _assert_no_duplicate_keys(
        census_tables["MECHANIC_BY_HEAD"], "MECHANIC_BY_HEAD", CENSUS_PATH
    )

    generator_tables = _dict_literal_assignments(
        GENERATOR_PATH, {"_CODE_EFFECT", "_HEAD_EFFECT"}
    )
    for name in ("_CODE_EFFECT", "_HEAD_EFFECT"):
        assert name in generator_tables, (
            f"{name} dict literal not found in {GENERATOR_PATH} — "
            "either it moved or is no longer a plain module-level dict "
            "literal; update this test's discovery logic"
        )
        _assert_no_duplicate_keys(generator_tables[name], name, GENERATOR_PATH)


def _transpiler_handled_codes() -> dict[int, str]:
    """Enumerate the RMXP numeric command codes the transpiler actually
    handles, derived structurally from the module source rather than
    hand-copied here.

    Method: `transpiler.py` opens with a contiguous run of module-level
    `NAME = <int>` constants under a "RMXP command codes" header comment
    (e.g. `SHOW_TEXT = 101`, `PREPARE_TRANSITION = 221`). "Contiguous" is
    load-bearing and is what makes this robust rather than a hand-picked
    line range: we group same-kind assignments by consecutive source line
    number and take the first group, which isolates exactly that header
    block from unrelated later constants that are NOT page-level command
    codes but happen to also be `NAME = <int>` at module scope — e.g.
    `ACTION_BUTTON_TRIGGER = 0` (an event *trigger* value, not a command
    code) and `CHANGE_GRAPHIC = 41` (a move-route *sub-step* code, a
    different code namespace entirely). Both live outside the contiguous
    run and are correctly excluded by this grouping.

    A second filter removes constants that are defined but never actually
    dispatched on: `INPUT_NUMBER = 103` is declared in the block but has no
    other reference anywhere in the file, i.e. code 103 falls through to
    the transpiler's generic "outside the v1 deterministic tier" queue path
    just like any code with no constant at all. A constant only counts as
    "handled" if it is referenced at least once more after its own
    definition line.
    """
    source_text = TRANSPILER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source_text, filename=str(TRANSPILER_PATH))

    candidates: list[tuple[str, int, int]] = []  # (name, value, lineno)
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            continue
        name = node.targets[0].id
        if not (name.isupper() and not name.startswith("_")):
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, int):
            continue
        candidates.append((name, node.value.value, node.lineno))
    candidates.sort(key=lambda c: c[2])

    # Group by strict line-number contiguity; keep the first group.
    groups: list[list[tuple[str, int, int]]] = []
    for item in candidates:
        if groups and item[2] == groups[-1][-1][2] + 1:
            groups[-1].append(item)
        else:
            groups.append([item])
    assert groups, f"no module-level int constants found in {TRANSPILER_PATH}"
    header_block = groups[0]
    assert len(header_block) > 10, (
        "the contiguous header block of RMXP command-code constants looks "
        f"suspiciously short ({len(header_block)} entries) — "
        f"{TRANSPILER_PATH} may have been restructured; update this test"
    )

    handled: dict[int, str] = {}
    for name, value, lineno in header_block:
        # ast constant occurrences: a Name node for `name` anywhere else in
        # the module besides this definition line means it's dispatched on.
        other_refs = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Name) and n.id == name and n.lineno != lineno
        ]
        if other_refs:
            handled[value] = name
    return handled


def _manifest_known_codes() -> set[int]:
    """`_CODE_EFFECT` keys plus `_CODE_IGNORED` plus `_CODE_BRANCH` from
    `generator.py` — the full set of codes the manifest layer has an
    opinion about (classified into an effect tag, explicitly ignored, or
    treated as branch structure)."""
    import importlib

    generator = importlib.import_module("rpg2gba.chapter_manifest.generator")
    known: set[int] = set(generator._CODE_EFFECT.keys())
    known |= set(generator._CODE_IGNORED)
    known |= set(generator._CODE_BRANCH)
    return known


# Codes where the FORWARD (transpiler -> manifest) comparison disagrees
# with reality, and why. Every entry here was hand-verified against the
# actual dispatch code, not assumed. An entry here is a deliberate,
# reviewed judgment call, not a silent exclusion.
#
# 355 (SCRIPT), 655 (SCRIPT_CONT): NOT a gap. generator.py deliberately
#   special-cases these two codes outside `_CODE_EFFECT` (see
#   `_CODE_EFFECT`'s own docstring comment and the `CODE_SCRIPT`/
#   `CODE_SCRIPT_CONT` handling around generator.py:567 and :603) — a
#   script-call row's effect tag depends on its Ruby head, not the bare
#   command code, so it is resolved through `_HEAD_EFFECT`/
#   `MECHANIC_BY_HEAD` instead. Confirmed by reading generator.py directly.
# 0: NOT a real gap, a limitation of the enumeration method. Code 0 (the
#   RMXP command-list terminator) IS handled by the transpiler — see the
#   `elif code == 0:` arm around transpiler.py:1174 — but it has no *named*
#   constant inside the contiguous header block this test parses
#   (`ACTION_BUTTON_TRIGGER = 0` nearby is a trigger value, not this code,
#   and sits outside the contiguous run by construction — see the
#   docstring on `_transpiler_handled_codes`). Manifest's `_CODE_IGNORED`
#   already carries 0 with the same "ignored, not unrecognized" semantics.
#
# Codes 118 (LABEL) and 119 (JUMP_TO_LABEL) used to be allowlisted here
# pending a fix; generator.py now classifies both as "control_flow"
# (verified above by grepping generator.py), so they are no longer
# exceptions — they pass the forward check on their own merits.
_TRANSPILER_ONLY_ALLOWLIST: frozenset[int] = frozenset({0, 355, 655})


def test_transpiler_and_manifest_code_tables_do_not_diverge() -> None:
    """Issue #97 regression guard, FORWARD direction only: every RMXP
    command code the transpiler dispatches on must be classified by the
    manifest's `_CODE_EFFECT`/`_CODE_IGNORED`/`_CODE_BRANCH` tables. If it
    isn't, the row lands in `other_codes`, which reads as "we do not even
    know what this is" — that's exactly the #97 bug (codes 104/116/221/222
    were dispatched by the transpiler but invisible to the manifest). See
    `_transpiler_handled_codes` for how the transpiler side is derived, and
    the allowlist comment above for every currently-known, hand-reviewed
    exception to this direction.

    The REVERSE direction — codes the manifest classifies that the
    transpiler doesn't dispatch on — is deliberately NOT checked here, and
    that is not an oversight. `_CODE_EFFECT` is a semantic table: it answers
    "what does this RMXP command mean", not "can the transpiler emit this".
    Whether a given row was actually converted is a separate question,
    answered by the unhandled-queue mechanism: any command the transpiler
    can't handle falls through to `ctx.queue(...)` with the message
    "command {code} outside the v1 deterministic tier", which increments
    that row's `unhandled` count, and `RULE_ILLEGAL_COSMETIC` in
    checker.py vetoes a `cosmetic` disposition whenever `unhandled` is
    non-zero. So a manifest-only code (e.g. 125/Change Gold, 322/323
    graphic changes — real examples, all legitimately meaningful and all
    currently unhandled by the transpiler) is not a bug: the row it labels
    queues, and the `unhandled` counter protects it from being marked
    cosmetic. Testing the reverse direction would conflate "the manifest
    knows what this means" with "the transpiler emits it", which are
    different questions answered by different mechanisms.
    """
    transpiler_codes = _transpiler_handled_codes()
    manifest_codes = _manifest_known_codes()

    transpiler_only = set(transpiler_codes) - manifest_codes - _TRANSPILER_ONLY_ALLOWLIST

    assert not transpiler_only, (
        "transpiler.py handles these RMXP command codes but generator.py's "
        "_CODE_EFFECT/_CODE_IGNORED/_CODE_BRANCH tables don't classify "
        "them (issue #97 shape — add to the tables or to the reviewed "
        "allowlist with a reason): "
        + ", ".join(f"{c} ({transpiler_codes[c]})" for c in sorted(transpiler_only))
    )


# Test 3 (head-table divergence, same shape as test 2 but for Ruby
# script-call heads) is deliberately NOT implemented. The transpiler has no
# enumerable head registry to compare against: `_emit_script_call` and its
# helper methods dispatch purely via ad-hoc whole-string/substring regexes
# (`_DIALOGUE_STRIP_RE`, `_ROCK_SMASH_RE`, `_TRAINER_PC_RE`,
# `_SHOW_MAP_RE`, `_SET_TEMP_SWITCH_RE`, `_CANLOSE_CALL_ARGS_RE`, and
# roughly a dozen more), most of which are substring/shape matches rather
# than "does the head equal X" checks, with no shared dispatch table and no
# `_script_head`-style extraction anywhere in transpiler.py (that helper
# exists only in chapter_atlas/census.py, on the manifest side). Any
# "enumeration" of transpiler heads would mean hand-transcribing that
# regex list into this test — exactly the brittle, drift-prone duplication
# issue #97 is about in the first place, on the very axis this test is
# supposed to guard. Writing it would be a fake test; per instructions,
# skipping it and reporting the reason is the correct call.
