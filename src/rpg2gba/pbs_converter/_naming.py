"""Shared rule for turning a name into a pokeemerald-expansion constant.

This is the single source of truth for the *naming convention* every Phase 2
converter uses when it mints or references an expansion constant. It must live
in one place: §2.1 (species) references `MOVE_*`/`ABILITY_*`/`ITEM_*` in
learnsets and evolutions, while §2.2/§2.3/§2.4 mint those same constants. If
the two disagreed on, say, `ATTACKORDER` → `MOVE_ATTACKORDER` vs
`MOVE_ATTACK_ORDER`, `IdMap.add` would fail loud on the conflict. Routing both
through `to_constant()` keeps them in lockstep.

Two name sources exist per concept:
  * the **display name** from `messages.dat` ("Attack Order") — preferred,
    because expansion constants follow the spaced/canonical name.
  * the **internal name** from `Constants.rxdata` ("ATTACKORDER") — a fallback
    when no display string exists.

`to_constant("MOVE", "Attack Order")` → `"MOVE_ATTACK_ORDER"`.

The fork-defined constant sets (see `load_fork_constants`) are the ground truth
for whether a derived constant actually exists in pokeemerald-expansion; a
derived name that isn't in the set is a Uranium-original → `needs_engine`.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# Characters dropped entirely (apostrophes, periods): "Farfetch'd" → FARFETCHD,
# "Mr. Mime" → MR_MIME.
_DROP = re.compile(r"['.]")
# Any run of non-alphanumeric becomes a single underscore.
_SEP = re.compile(r"[^A-Za-z0-9]+")


def _fold_accents(name: str) -> str:
    """Strip diacritics so accented names match the ASCII expansion constants.

    "Poké Ball" → "Poke Ball" → ITEM_POKE_BALL (the fork constant), not
    ITEM_POK_BALL. NFKD decomposes "é" into "e" + combining acute; dropping the
    combining mark (category "Mn") leaves the base letter.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def to_constant(prefix: str, name: str) -> str:
    """Normalize a display/internal name into a `PREFIX_UPPER_SNAKE` constant.

    Mirrors the Pokémon Showdown / expansion naming convention closely enough
    for the vanilla overlap; Uranium-original names normalize cleanly too, they
    just won't resolve against the fork constant set (→ needs_engine).
    """
    cleaned = _DROP.sub("", _fold_accents(name))
    snake = _SEP.sub("_", cleaned).strip("_").upper()
    return f"{prefix}_{snake}"


# Constants appear either as `#define NAME value` or as an enum member
# (`NAME = 1,` / `NAME,` / `NAME = OTHER_NAME, // alias`). Catch both forms.
_CONST_RE = re.compile(r"^\s*(?:#define\s+)?([A-Z][A-Z0-9_]*)\b")


def load_fork_constants(header_path: Path, prefix: str) -> set[str]:
    """Collect every `<PREFIX>_*` constant from a fork header.

    Handles both `#define`d constants and `enum` members (the modern expansion
    declares species/moves/abilities/items as packed enums). Returns an empty
    set if the header is missing (best-effort: callers treat an empty set as
    "can't validate", not "nothing exists"). `prefix` filters to the family of
    interest (e.g. "MOVE", "ABILITY", "ITEM", "SPECIES").
    """
    if not header_path.is_file():
        return set()
    out: set[str] = set()
    want = f"{prefix}_"
    for line in header_path.read_text(encoding="utf-8").splitlines():
        m = _CONST_RE.match(line)
        if m and m.group(1).startswith(want):
            out.add(m.group(1))
    return out
