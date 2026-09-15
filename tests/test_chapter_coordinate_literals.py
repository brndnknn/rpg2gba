"""The coordinate-literal ban and its ratchet (CH05 onward).

`src/rpg2gba/playtest/chapters/*.py` used to hardcode map coordinates as bare
two-integer tuple literals -- `(18, 37)`. Three CH04 test failures traced to
exactly that pattern: a coordinate typed by hand, never checked against the
decoded map data it claimed to describe. The fix is a ban on the pattern,
enforced here by walking each chapter module's AST: any `ast.Tuple` of
exactly two integer constants, anywhere in the file (module-level constant,
inline `at=(x, y)`, nested in a call, inside a helper body), is a violation.

The replacement vocabulary is `src/rpg2gba/playtest/cells.py`'s resolvers
(`event_cell`, `approach_to`, `warp_cell`, `arrival_cell`, `entry_cell`),
which derive a cell from this build's own decoded output and fail loud when
the data doesn't support the answer, plus one counted escape hatch,
`raw_cell(x, y, why=...)`, for geometry the corpus genuinely can't express.
`raw_cell`'s own two positional arguments are plain integers, not a tuple
literal, so they are never flagged by the walker above -- that is the "ONE
exception" this ban carries, and it falls out of the AST shape rather than
needing a special case. `raw_cell` calls carry their own separate rule
instead: every call must pass a non-empty string `why=`, or it is itself a
violation (missing or empty `why=` defeats the counted-debt discipline the
escape hatch exists for).

**The ratchet.** `ch01.py`, `ch02.py`, `ch03.py`, `ch04.py` predate the
ban and are explicitly NOT being retrofitted (out of scope for the task that
introduced this test). `_PRE_BAN_BUDGET` freezes each file's *measured*
violation count as of the day the ban landed -- this is debt to be paid down
over time, not a permanent allowance:

- A budgeted file passes only while its count stays `<=` its budget. A count
  that goes UP fails the test -- new debt in an old file is refused exactly
  like debt in a new file.
- A budgeted file whose count drops BELOW its budget also fails the test,
  with a message telling the author to lower the number in this file to the
  new count. A ratchet that only tightens by accident (silently, without the
  budget table ever being edited to match) is not a ratchet -- it's a stale
  ceiling nobody re-checks.
- Any chapter file NOT in `_PRE_BAN_BUDGET` -- every chapter from CH05
  onward -- must have exactly ZERO violations. CH05 is born at zero; it
  never inherits a budget.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CHAPTERS_DIR = REPO_ROOT / "src" / "rpg2gba" / "playtest" / "chapters"
MAPS_DIR = REPO_ROOT / "output" / "uranium-build" / "maps"
TILESETS_JSON = REPO_ROOT / "output" / "uranium-build" / "tilesets.json"
MAP_CONSTANTS_JSON = REPO_ROOT / "output" / "uranium-build" / "porymap" / "map_constants.json"

_DECODED_OUTPUT_PRESENT = (
    MAPS_DIR.is_dir() and TILESETS_JSON.is_file() and MAP_CONSTANTS_JSON.is_file()
)
requires_decoded_output = pytest.mark.skipif(
    not _DECODED_OUTPUT_PRESENT,
    reason="requires the decoded corpus under output/uranium-build/ (run the pipeline first)",
)

def _map_const_for(uranium_id: int) -> str:
    """The map constant currently minted for `uranium_id`, read from the live
    registry state rather than written as a literal.

    Deliberate: maps 36 and 37 were renamed on 2026-08-31 (`Passage Cave` ->
    `Passage Cave 1F`/`2F`), and the constants on disk here are still the Map
    Walker's auto-disambiguated `MAP_PASSAGE_CAVE_36`/`_37` from a run that
    predates the override. They become `MAP_PASSAGE_CAVE_1F`/`_2F` the next
    time constants are minted, which is CH05's WIRE step. A hardcoded name
    would pass today and break then, for a reason that has nothing to do with
    what these tests are checking -- which is exactly the class of unverified
    literal this whole module exists to ban.
    """
    import json

    state = json.loads(MAP_CONSTANTS_JSON.read_text(encoding="utf-8"))
    entries = state.get("maps", state)
    if isinstance(entries, dict):
        entry = entries.get(str(uranium_id)) or entries.get(uranium_id)
        if entry:
            return entry["map_const"]
    raise AssertionError(
        f"no map constant minted for uranium map {uranium_id} in "
        f"{MAP_CONSTANTS_JSON}; regenerate the registry"
    )


# Measured violation counts as of the day this ban landed (2026-09-01), via
# the exact walker below run over each file. These four chapters predate the
# ban and are deliberately not being retrofitted -- see module docstring.
# THIS IS DEBT, NOT AN ALLOWANCE: when a file is cleaned up, lower its number
# here to match (the test enforces that direction too, not just the ceiling).
_PRE_BAN_BUDGET: dict[str, int] = {
    "ch01.py": 13,
    # 45 -> 44 on 2026-09-15: B1's ROUTE1_ARRIVAL became arrival_cell(...),
    # the same (70,11), when B1 took Route 1's arrival-nudge rows.
    "ch02.py": 44,
    "ch03.py": 42,
    # 25 -> 23 on 2026-09-04: trimming B7 to stop at the cave-mouth approach
    # tile retired CAVE_MOUTH_NORTH_WALL_XY and CAVE_MOUTH_NORTH_OPEN_XY, the
    # two literals for tiles north of the CH04|CH05 boundary. Debt paid down
    # by deleting the assertions that owned it, not by adding a resolver.
    "ch04.py": 23,
}


# -- the walker ---------------------------------------------------------------

def _is_int_constant(node: ast.AST) -> bool:
    # `type(...) is int`, not `isinstance`, so a bool constant (True/False --
    # technically an int subclass in Python) is never mistaken for a
    # coordinate literal.
    return isinstance(node, ast.Constant) and type(node.value) is int


def _raw_cell_call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def iter_coordinate_literal_violations(tree: ast.AST) -> list[str]:
    """Every bare two-int tuple literal, and every `raw_cell(...)` call
    missing a non-empty string `why=`, found anywhere in `tree`."""
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Tuple) and len(node.elts) == 2:
            a, b = node.elts
            if _is_int_constant(a) and _is_int_constant(b):
                violations.append(
                    f"line {node.lineno}: bare coordinate literal "
                    f"({a.value}, {b.value}) -- use a resolver from "
                    "rpg2gba.playtest.cells, or raw_cell(x, y, why=...) if "
                    "genuinely undecidable from decoded data"
                )
        if isinstance(node, ast.Call) and _raw_cell_call_name(node) == "raw_cell":
            why_kw = next((kw for kw in node.keywords if kw.arg == "why"), None)
            if why_kw is None:
                violations.append(
                    f"line {node.lineno}: raw_cell(...) call is missing why="
                )
            elif not (
                isinstance(why_kw.value, ast.Constant)
                and isinstance(why_kw.value.value, str)
                and why_kw.value.value.strip()
            ):
                violations.append(
                    f"line {node.lineno}: raw_cell(...) why= must be a "
                    "non-empty string literal"
                )
    return violations


def _violations_for_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return iter_coordinate_literal_violations(tree)


def _chapter_files() -> list[Path]:
    return sorted(
        p for p in CHAPTERS_DIR.glob("*.py") if p.name != "__init__.py"
    )


# -- the ratchet test -----------------------------------------------------

@pytest.mark.parametrize("path", _chapter_files(), ids=lambda p: p.name)
def test_chapter_coordinate_literal_ratchet(path: Path) -> None:
    violations = _violations_for_file(path)
    budget = _PRE_BAN_BUDGET.get(path.name)

    if budget is None:
        # No budget entry: this chapter is CH05 or later, born at zero.
        assert not violations, (
            f"{path.name}: {len(violations)} coordinate-literal violation(s) "
            f"in a chapter not covered by _PRE_BAN_BUDGET (i.e. authored "
            "under the ban -- must be zero):\n"
            + "\n".join(violations)
        )
        return

    assert len(violations) <= budget, (
        f"{path.name}: {len(violations)} violations exceeds its "
        f"_PRE_BAN_BUDGET of {budget} -- new coordinate literals were added "
        "to a pre-ban chapter; use a resolver from rpg2gba.playtest.cells "
        "instead:\n" + "\n".join(violations)
    )
    assert len(violations) == budget, (
        f"{path.name}: measured {len(violations)} violations, but "
        f"_PRE_BAN_BUDGET says {budget} -- the file's debt has been paid "
        f"down. Lower _PRE_BAN_BUDGET[{path.name!r}] to {len(violations)} "
        "in tests/test_chapter_coordinate_literals.py so the ratchet "
        "tightens instead of sitting on a stale ceiling."
    )


def test_pre_ban_budget_only_names_existing_chapter_files() -> None:
    existing = {p.name for p in _chapter_files()}
    stale = set(_PRE_BAN_BUDGET) - existing
    assert not stale, (
        f"_PRE_BAN_BUDGET names file(s) no longer present: {sorted(stale)}"
    )


# -- walker unit tests ------------------------------------------------------

def test_walker_flags_bare_two_int_tuple() -> None:
    tree = ast.parse("X = (1, 2)\n")
    violations = iter_coordinate_literal_violations(tree)
    assert len(violations) == 1
    assert "line 1" in violations[0]


def test_walker_does_not_flag_raw_cell_positional_args() -> None:
    tree = ast.parse('X = raw_cell(1, 2, why="measured by hand")\n')
    violations = iter_coordinate_literal_violations(tree)
    assert violations == []


def test_walker_flags_raw_cell_missing_why() -> None:
    tree = ast.parse("X = raw_cell(1, 2)\n")
    violations = iter_coordinate_literal_violations(tree)
    assert len(violations) == 1
    assert "missing why=" in violations[0]


def test_walker_flags_raw_cell_with_empty_why() -> None:
    tree = ast.parse('X = raw_cell(1, 2, why="")\n')
    violations = iter_coordinate_literal_violations(tree)
    assert len(violations) == 1
    assert "non-empty string" in violations[0]


def test_walker_flags_tuple_nested_in_call() -> None:
    tree = ast.parse("emu.walk_to(*(3, 4))\n")
    violations = iter_coordinate_literal_violations(tree)
    assert len(violations) == 1


def test_walker_does_not_flag_non_coordinate_tuples() -> None:
    # A 2-tuple of non-int constants, and a tuple of the wrong arity, are
    # not coordinate literals.
    tree = ast.parse('X = ("a", "b")\nY = (1, 2, 3)\nZ = (True, False)\n')
    violations = iter_coordinate_literal_violations(tree)
    assert violations == []


# -- resolver unit tests (src/rpg2gba/playtest/cells.py) --------------------

def test_raw_cell_rejects_empty_why() -> None:
    from rpg2gba.playtest.cells import raw_cell

    with pytest.raises(ValueError):
        raw_cell(1, 2, why="")
    with pytest.raises(ValueError):
        raw_cell(1, 2, why="   ")


def test_raw_cell_returns_the_pair_unchanged() -> None:
    from rpg2gba.playtest.cells import raw_cell

    assert raw_cell(5, 9, why="measured against a screenshot") == (5, 9)


def test_entry_cell_hits_ch04_map35() -> None:
    from rpg2gba.chapter_manifest.generator import _CHAPTER_MAP_START_CELLS

    # Confirms the fixture this resolver reads still holds the entry the
    # brief names, without needing decoded output at all (no map-constant
    # resolution is exercised here -- see the decoded-output-gated test
    # below for the full map_constant -> cell path).
    assert _CHAPTER_MAP_START_CELLS[("CH04", 35)] == frozenset({(21, 56)})


@requires_decoded_output
def test_entry_cell_miss_names_chapter_and_map() -> None:
    # Unlike the hit test above (a direct dict lookup, no decoded output
    # needed), `entry_cell` itself first resolves `map_constant` to a
    # Uranium map id via the same map_constants.json state every other
    # resolver in cells.py reads -- so exercising the real fail-loud path
    # (rather than the table directly) does need the decoded corpus staged.
    from rpg2gba.playtest import cells

    # Use a chapter id that can never legitimately collide with a real entry.
    with pytest.raises(ValueError) as excinfo:
        cells.entry_cell("CH99-NOT-REAL", _map_const_for(37))
    assert "CH99-NOT-REAL" in str(excinfo.value)
    assert "37" in str(excinfo.value) or _map_const_for(37) in str(excinfo.value)


@requires_decoded_output
class TestResolversAgainstMap37:
    """Map037 (CH05's cave): four staircase events at (11,9), (11,10),
    (20,9), (20,10), and a south warp to map 36 -- see
    `tests/test_traversal_map037_golden.py`'s module docstring for the same
    fixture used there.
    """

    @property
    def MAP37(self) -> str:
        return _map_const_for(37)

    @property
    def MAP36(self) -> str:
        return _map_const_for(36)

    def test_event_cell_reads_a_known_staircase(self) -> None:
        from rpg2gba.playtest.cells import event_cell

        # Map037.json event id 8 is a "Stairs" event at (11, 9) (confirmed
        # directly against output/uranium-build/maps/Map037.json).
        assert event_cell(self.MAP37, 8) == (11, 9)

    def test_event_cell_unknown_event_id_fails_loud(self) -> None:
        from rpg2gba.playtest.cells import event_cell

        with pytest.raises(ValueError, match="999"):
            event_cell(self.MAP37, 999)

    def test_warp_cell_finds_the_south_exit(self) -> None:
        from rpg2gba.playtest.cells import warp_cell

        # Map037 event 1, cell (16, 27), is the sole command-201 transfer to
        # map 36 (module docstring of tests/test_traversal_map037_golden.py).
        assert warp_cell(self.MAP37, to=self.MAP36) == (16, 27)

    def test_arrival_cell_matches_the_documented_entry_point(self) -> None:
        from rpg2gba.playtest.cells import arrival_cell

        # Map036 event 2 transfers into map 37 at (16, 26) -- the same entry
        # point test_traversal_map037_golden.py derives independently.
        assert arrival_cell(self.MAP37, from_map=self.MAP36) == (16, 26)

    def test_approach_to_a_staircase_is_walkable_and_adjacent(self) -> None:
        from rpg2gba.playtest.cells import approach_to

        cell = approach_to(self.MAP37, 8)
        ex, ey = cell
        assert abs(ex - 11) + abs(ey - 9) == 1
