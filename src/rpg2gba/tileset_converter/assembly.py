"""S8 assembly helpers — prune orphan ``.pory`` script blocks before staging.

S5 (``metadata_wiring``) decides which of a map's events get *wired* into its
``map.json`` (``object_events`` with a ``script`` label, ``warp_events`` that run
no script). S6 (the conversion agent) converts **every** command-bearing event's
pages into ``.pory`` script blocks — including events S5 dropped, e.g. the
out-of-slice building/cave doors in a town hub. Those orphan blocks carry
``warp(MAP_URANIUM_<N>)`` placeholders for maps *outside* the slice, and the
slice alias header (S4) only defines the in-slice ``MAP_URANIUM_*``. Poryscript
compiles every block in a file whether or not anything references it, so the
orphan blocks drag undefined map constants into ``event_scripts.s`` and break
``make modern`` at assembly — a "compiles per-file, breaks at link" class the
pathfinder slice was built to surface.

This module computes the live event set from the wired ``map.json`` and drops the
``.pory`` blocks of every non-wired event. The pruning decision keys on the
**event id** embedded in each block label, not the full label, because the S5
``map.json`` references the un-named form ``Map{m}_EV{e}_Page{n}`` while the agent
emits name-qualified labels (``Map{m}_EV{e}_Chyinmunk_Page1``) — a separate S8
label-reconciliation concern that must not make the prune mis-fire.

Two fail-loud guards (CLAUDE.md §4.5) protect the result: no kept block may
reference a dropped label (a real cross-event reference is not silently severed),
and — when the caller supplies the allowed set — no out-of-slice ``MAP_URANIUM_*``
may survive in the kept text (a *wired* event warping out of the slice is a real
problem to surface, not to pass over).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# A top-level Poryscript block opens with ``script LABEL {`` at column 0; nested
# braces (``if (...) {``) and string text codes (``{PLAYER}``) are always
# indented, so anchoring on the start of line is unambiguous. The agent emits
# only ``script`` blocks (no ``text``/``movement``/``mart``/``raw``).
_BLOCK_START_RE = re.compile(r"(?m)^script[ \t]+(\w+)\b")
_EVENT_ID_RE = re.compile(r"^Map\d+_EV(\d+)_")
_URANIUM_MAP_RE = re.compile(r"\bMAP_URANIUM_(\d+)\b")

# A page-body label as the agent emits it: Map{m}_EV{e}_[<name>_]Page{n}. The
# optional ``<name>`` is the agent's sanitized event name — present
# inconsistently (EV009 "Trainer(6)" -> ...Trainer6_Page1, EV074 "Trainer(5)" ->
# ...Page1). Case-sensitive ``Map``/``EV`` keeps it disjoint from the upper-case
# ``FLAG_MAP…_EVENT…`` flag tokens. ``_Dispatch`` labels (S5-generated, no Page
# suffix) are intentionally not matched.
_PAGE_LABEL_RE = re.compile(r"\bMap(\d+)_EV(\d+)_(?:[A-Za-z0-9_]+?_)?Page(\d+)\b")
# Tokens in our script-label namespace, used to find references (goto/call args,
# map.json script fields) for the dangling-reference check.
_LABEL_REF_RE = re.compile(r"\b(?:Map\d+_EV\d+_\w+|CommonEvent_\d+)\b")


class AssemblyError(Exception):
    """An assembly-staging invariant was violated (fail loud, do not stage)."""


@dataclass(frozen=True)
class Block:
    """One top-level ``script`` block: its label and verbatim text.

    ``text`` spans from the block's ``script`` keyword through (and including) any
    trailing whitespace up to the next block, so ``preamble + "".join(texts)``
    reconstitutes the source byte-for-byte."""

    label: str
    text: str


@dataclass(frozen=True)
class PruneResult:
    text: str
    kept: list[str]
    dropped: list[str]


@dataclass(frozen=True)
class NormalizeResult:
    text: str
    renames: dict[str, str]  # old label -> canonical label, for the blocks that changed


def split_blocks(pory_text: str) -> tuple[str, list[Block]]:
    """Split a ``.pory`` file into ``(preamble, blocks)``.

    Blocks are delimited by ``^script LABEL`` at column 0. The preamble is any
    text before the first block (usually empty). Inter-block whitespace travels
    with the preceding block, so the split is lossless."""
    matches = list(_BLOCK_START_RE.finditer(pory_text))
    if not matches:
        return pory_text, []
    preamble = pory_text[: matches[0].start()]
    blocks: list[Block] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(pory_text)
        blocks.append(Block(label=m.group(1), text=pory_text[m.start() : end]))
    return preamble, blocks


def block_event_id(label: str) -> int | None:
    """The event id embedded in a ``Map{m}_EV{e}_…`` label, or None.

    Returns None for labels that carry no event id (e.g. ``CommonEvent_005``),
    which the prune treats as always-live (never an orphan map event)."""
    m = _EVENT_ID_RE.match(label)
    return int(m.group(1)) if m else None


def live_event_ids(map_json: dict) -> set[int]:
    """Event ids whose script blocks *this* map's ``map.json`` actually wires.

    Reads the ``script`` label of every event-bearing entry (``object_events`` and
    — if present — ``coord_events``/``bg_events``); ``warp_events`` run no script
    and are intentionally excluded. The label may be a page label
    (``Map{m}_EV{e}_Page1``) or a dispatcher (``Map{m}_EV{e}_Dispatch``); both
    yield event id ``e``."""
    ids: set[int] = set()
    for key in ("object_events", "coord_events", "bg_events"):
        for ev in map_json.get(key, []):
            label = ev.get("script")
            if not label:
                continue
            eid = block_event_id(label)
            if eid is not None:
                ids.add(eid)
    return ids


def prune_orphan_blocks(
    pory_text: str,
    live_ids: set[int],
    *,
    allowed_uranium_maps: set[int] | None = None,
) -> PruneResult:
    """Drop every block whose event is not in *live_ids*; keep the rest verbatim.

    A block is kept when its label carries no event id (defensive: non-map blocks
    such as ``CommonEvent_*`` are never orphans) or its event id is in *live_ids*.
    Pruning is idempotent — re-running on the result is a no-op.

    Raises ``AssemblyError`` if a kept block references a dropped label
    (cross-event reference — refusing to leave a dangling ``goto``), or if
    *allowed_uranium_maps* is given and any surviving ``MAP_URANIUM_<N>`` names a
    map outside it (the alias header cannot resolve it)."""
    _preamble, blocks = split_blocks(pory_text)
    kept_blocks: list[Block] = []
    dropped: list[str] = []
    for b in blocks:
        eid = block_event_id(b.label)
        if eid is None or eid in live_ids:
            kept_blocks.append(b)
        else:
            dropped.append(b.label)

    kept_text = _preamble + "".join(b.text for b in kept_blocks)

    dropped_set = set(dropped)
    for label in dropped_set:
        if re.search(r"\b" + re.escape(label) + r"\b", kept_text):
            raise AssemblyError(
                f"kept block references pruned label {label!r}: a live event "
                "points into an orphan block — refusing to create a dangling goto"
            )

    if allowed_uranium_maps is not None:
        survivors = {
            int(n) for n in _URANIUM_MAP_RE.findall(kept_text)
        } - allowed_uranium_maps
        if survivors:
            raise AssemblyError(
                "wired blocks still reference out-of-slice "
                f"MAP_URANIUM_{sorted(survivors)} — no alias resolves these; "
                "extend the slice, stub the map, or strip the warp"
            )

    return PruneResult(text=kept_text, kept=[b.label for b in kept_blocks], dropped=dropped)


def prune_map_pory(
    pory_text: str,
    map_json: dict,
    *,
    allowed_uranium_maps: set[int] | None = None,
) -> PruneResult:
    """Convenience: prune *pory_text* against the events *map_json* wires."""
    return prune_orphan_blocks(
        pory_text,
        live_event_ids(map_json),
        allowed_uranium_maps=allowed_uranium_maps,
    )


# ---------------------------------------------------------------------------
# Label reconciliation (Option A) — strip the agent's event-name component so the
# blocks match S5's un-named references, then verify nothing dangles.
# ---------------------------------------------------------------------------

def normalize_labels(pory_text: str) -> NormalizeResult:
    """Rewrite page labels to the canonical un-named ``Map{m}_EV{e}_Page{n}`` form.

    S5's ``map.json`` and dispatchers reference page bodies by
    ``Map{m}_EV{e}_Page{n}`` (``metadata_wiring.page_label``), but the agent
    embeds the event name inconsistently — so the two only agree once the name is
    stripped. The rewrite runs over the whole text, so a block's definition and
    every ``goto``/``call`` reference to it move together (the technique
    ``orchestrator._qualify_labels`` relies on). Idempotent: an already-un-named
    label is left unchanged.

    Only ``Page`` labels are touched; ``_Dispatch`` labels (S5-owned) and the
    upper-case ``FLAG_MAP…_EVENT…`` flag names are not."""
    renames: dict[str, str] = {}

    def _repl(m: re.Match[str]) -> str:
        old = m.group(0)
        new = f"Map{m.group(1)}_EV{m.group(2)}_Page{m.group(3)}"
        if old != new:
            renames[old] = new
        return new

    return NormalizeResult(text=_PAGE_LABEL_RE.sub(_repl, pory_text), renames=renames)


def script_definitions(*pory_texts: str) -> list[str]:
    """Every ``script LABEL`` block name defined across the given fragments."""
    out: list[str] = []
    for text in pory_texts:
        out.extend(_BLOCK_START_RE.findall(text))
    return out


def script_reference_labels(*pory_texts: str) -> set[str]:
    """Script-label-shaped tokens (``Map…_EV…``/``CommonEvent_…``) used in the text.

    Includes both definitions and references — callers diff against the defined
    set to isolate the dangling references."""
    out: set[str] = set()
    for text in pory_texts:
        out |= set(_LABEL_REF_RE.findall(text))
    return out


#: ``map.json`` ``script`` sentinels that mean "no script" (a static object), not
#: a label reference — see ``metadata_wiring.NO_SCRIPT``.
_NO_SCRIPT_SENTINELS = {"0x0", "0"}


def map_json_script_refs(map_json: dict) -> set[str]:
    """The script labels a ``map.json`` points at (object/coord/bg ``script``).

    The ``0x0``/``0`` no-script sentinels (static objects) are not references."""
    refs: set[str] = set()
    for key in ("object_events", "coord_events", "bg_events"):
        for ev in map_json.get(key, []):
            label = ev.get("script")
            if label and label not in _NO_SCRIPT_SENTINELS:
                refs.add(label)
    return refs


def find_dangling_references(
    staged_texts: list[str],
    map_jsons: list[dict] | None = None,
) -> set[str]:
    """Script labels referenced anywhere in the staged set but never defined.

    The staged set is the full collection of ``.pory`` that assemble together —
    normalized + pruned map scripts, dispatchers, and ``CommonEvents.pory``. A
    non-empty result is an undefined-reference build break: a ``map.json``
    ``script`` with no block (an EV074-style conversion gap), a dispatcher
    ``goto`` to a missing page, or a ``call CommonEvent_*`` with no common-event
    block."""
    defined = set(script_definitions(*staged_texts))
    referenced = script_reference_labels(*staged_texts)
    for mj in map_jsons or []:
        referenced |= map_json_script_refs(mj)
    return referenced - defined


_WARP_CALL_RE = re.compile(r"\bwarp\(MAP_URANIUM_(\d+),\s*\d+,\s*\d+\)")


def patch_out_of_slice_warps(pory_text: str, allowed_uranium_maps: set[int]) -> str:
    """Replace warp() calls that target out-of-slice maps with ``return``.

    CommonEvents can reference any map in the corpus; only the in-slice alias
    header is present at build time, so unresolvable MAP_URANIUM_<N> constants
    cause undefined-symbol link errors. Replacing with ``return`` is safe: the
    entire CE is unreachable from slice gameplay anyway."""
    def _repl(m: re.Match[str]) -> str:
        if int(m.group(1)) in allowed_uranium_maps:
            return m.group(0)
        return "return"
    return _WARP_CALL_RE.sub(_repl, pory_text)


# ---------------------------------------------------------------------------
# Undefined-symbol patches for deferred content (link-stage breaks).
# poryscript compiles every block regardless of reachability, so an agent
# reference to a not-yet-defined constant (a Phase-5/6 multichoice list) breaks
# `make modern` at link even when the block is unreachable in slice gameplay.
# ---------------------------------------------------------------------------

_MULTICHOICE_RE = re.compile(r"\bmultichoice\(([^)]*)\)")
_MULTI_CONST_RE = re.compile(r"\bMULTI_\w+\b")
_MULTI_DEFINE_RE = re.compile(r"^#define\s+(MULTI_\w+)\b")


def load_multi_constants(path: Path) -> set[str]:
    """The vanilla ``MULTI_*`` list constants defined in the fork
    (``include/constants/script_menu.h``)."""
    return {
        m.group(1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if (m := _MULTI_DEFINE_RE.match(line.strip()))
    }


def patch_undefined_multichoice(text: str, defined_multis: set[str]) -> str:
    """Stub ``multichoice(...)`` calls whose list constant the fork doesn't define.

    The agent invents ``MULTI_*`` names for Uranium choice menus it defers to
    Phase 5/6 (e.g. ``MULTI_DREAM_VISUALIZER`` in the dream CommonEvent). Those
    are undefined symbols at link. Replacing the call with ``setvar(VAR_RESULT,
    0)`` keeps the (unreachable) block linkable and deterministic — the menu is
    Phase-6 work, not slice gameplay."""
    def _repl(m: re.Match[str]) -> str:
        if any(c not in defined_multis for c in _MULTI_CONST_RE.findall(m.group(1))):
            return "setvar(VAR_RESULT, 0)"
        return m.group(0)
    return _MULTICHOICE_RE.sub(_repl, text)


# ---------------------------------------------------------------------------
# Self/temp-switch reference completeness (link-stage breaks).
# A self-switch flag named in one event's script but belonging to a *different*,
# bodyless event (the RMXP "set the next NPC's switch" idiom) is never minted by
# the orchestrator, so dump_header gives it no address -> undefined at link. This
# recovers the full referenced set from the final assembled scripts so the flag
# header is complete regardless of which event the switch is set from.
# ---------------------------------------------------------------------------

_SELF_SWITCH_REF_RE = re.compile(r"\bFLAG_MAP(\d+)_EVENT(\d+)_SS([A-Z])\b")
_TEMP_SWITCH_REF_RE = re.compile(r"\bFLAG_MAP(\d+)_EVENT(\d+)_TS(\w+)\b")


def referenced_switch_keys(
    texts: list[str],
) -> tuple[set[tuple[int, int, str]], set[tuple[int, int, str]]]:
    """``(self_switch_keys, temp_switch_keys)`` referenced anywhere in ``texts``,
    each as ``(map_id, event_id, channel)`` — the args ``mint_self_switch`` /
    ``mint_temp_switch`` take."""
    self_keys: set[tuple[int, int, str]] = set()
    temp_keys: set[tuple[int, int, str]] = set()
    for t in texts:
        for m in _SELF_SWITCH_REF_RE.finditer(t):
            self_keys.add((int(m.group(1)), int(m.group(2)), m.group(3)))
        for m in _TEMP_SWITCH_REF_RE.finditer(t):
            temp_keys.add((int(m.group(1)), int(m.group(2)), m.group(3)))
    return self_keys, temp_keys


# ---------------------------------------------------------------------------
# Charmap normalization — make agent/classifier dialogue representable on the GBA.
#
# poryscript passes string text and unknown commands straight through; the GBA
# charmap and the script macros are only enforced later by ``arm-as``. So
# charmap-illegal characters ("compiles per-file, breaks at link") reach the
# build. This is the systemic source of the recurring slice-build failures: the
# fix is one deterministic, fail-loud normalization pass over the agent output
# instead of a growing chain of per-character ``replace()`` band-aids.
# ---------------------------------------------------------------------------

# Characters Uranium dialogue uses that have no GBA charmap glyph -> the
# representable glyph we map each to. ``"`` is handled separately (open/close
# toggle to typographic quotes). Anything NOT here and NOT in the charmap fails
# loud — a new offender must be a deliberate decision, not a silent corruption.
_CHARMAP_SUBS = {"*": "~", "[": "(", "]": ")"}

_OPEN_QUOTE = "“"   # left double quotation mark (charmap B1)
_CLOSE_QUOTE = "”"  # right double quotation mark (charmap B2)

# A double-quoted string literal, escaped-quote aware: "(...)" with \" inside.
_STRING_LITERAL_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_TEXT_PLACEHOLDER_RE = re.compile(r"\{[^}]*\}")  # {PLAYER}, {STR_VAR_1}, {COLOR RED}
_TEXT_ESCAPE_RE = re.compile(r"\\[nlp]")          # \n \l \p line breaks
# The agent's invented one-liner heal command, on its own line.
_HEALPARTY_RE = re.compile(r"(?m)^([ \t]*)healparty\b[ \t]*$")
_CHARMAP_GLYPH_RE = re.compile(r"^'(.+?)'\s*=")


def load_charmap_chars(path: Path) -> set[str]:
    """Representable single-glyph characters from pokeemerald's ``charmap.txt``.

    Only single-character glyph entries (``'é' = 1B``) count as literal text
    characters; multi-byte control names and ``\\n``/``\\l``/``\\p`` are handled
    elsewhere. ``'\\''`` maps the apostrophe."""
    chars: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _CHARMAP_GLYPH_RE.match(line)
        if not m:
            continue
        body = m.group(1)
        if body == "\\'":
            chars.add("'")
        elif len(body) == 1:
            chars.add(body)
    return chars


def _assert_representable(content: str, allowed: set[str], context: str) -> None:
    probe = _TEXT_PLACEHOLDER_RE.sub("", content)
    probe = _TEXT_ESCAPE_RE.sub("", probe).replace("\\\\", "\\")
    for c in probe:
        if c not in allowed:
            raise ValueError(
                f"unrepresentable character U+{ord(c):04X} {c!r}: no charmap glyph "
                f"and no substitution. Add it to _CHARMAP_SUBS or fix the source. "
                f"Line: {context.strip()!r}"
            )


def _normalize_string_content(content: str, allowed: set[str], context: str) -> str:
    out: list[str] = []
    quote_open = True
    i, n = 0, len(content)
    while i < n:
        c = content[i]
        if c == "\\" and i + 1 < n:
            nxt = content[i + 1]
            if nxt == '"':  # escaped quote -> typographic open/close, alternating
                out.append(_OPEN_QUOTE if quote_open else _CLOSE_QUOTE)
                quote_open = not quote_open
            else:           # keep \n \l \p \\ escapes intact
                out += [c, nxt]
            i += 2
            continue
        out.append(_CHARMAP_SUBS.get(c, c))
        i += 1
    result = "".join(out)
    _assert_representable(result, allowed, context)
    return result


def normalize_pory(text: str, allowed: set[str]) -> str:
    """Rewrite agent/classifier ``.pory`` to be charmap- and poryscript-valid.

    Two deterministic fixes before the script is handed to poryscript:

    * **command alias** — the agent's invented ``healparty`` one-liner becomes the
      real ``special(HealPlayerParty)`` (a ``def_special`` in the fork). Emitted in
      ``special(...)`` form: poryscript splits the bare ``special HealPlayerParty``
      into two invalid asm lines.
    * **charmap normalization** of every double-quoted dialogue string: ``\\"`` ->
      typographic ``“``/``”`` (open/close toggle), plus ``_CHARMAP_SUBS`` (``*`` ->
      ``~``, ``[`` -> ``(``, ``]`` -> ``)``). Any remaining character with no
      charmap glyph **fails loud** (CLAUDE.md §4.5).

    Comment lines (``# ...``) are left untouched — poryscript strips them, and they
    legitimately contain characters (``[``, ``"``) that never reach the ROM.
    Idempotent: a second pass sees only already-representable glyphs."""
    text = _HEALPARTY_RE.sub(r"\1special(HealPlayerParty)", text)

    out_lines: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            out_lines.append(line)
            continue
        out_lines.append(
            _STRING_LITERAL_RE.sub(
                lambda m: '"' + _normalize_string_content(m.group(1), allowed, m.string) + '"',
                line,
            )
        )
    result = "\n".join(out_lines)
    return result + "\n" if text.endswith("\n") else result


def find_duplicate_definitions(staged_texts: list[str]) -> dict[str, int]:
    """Labels defined more than once across the staged set (duplicate-symbol break).

    Normalizing names away can, in principle, collapse two distinct blocks onto
    one label (same map/event/page, different agent names) — a real duplicate the
    per-file compile gate cannot see. Returns ``{label: count}`` for count > 1."""
    counts: dict[str, int] = {}
    for label in script_definitions(*staged_texts):
        counts[label] = counts.get(label, 0) + 1
    return {label: n for label, n in counts.items() if n > 1}
