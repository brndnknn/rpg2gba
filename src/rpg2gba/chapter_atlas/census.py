"""Mechanical per-chapter inventory over the converted corpus.

Chapter documents must never hand-derive their numbers: a converter change has
to refresh them, not silently stale them (that is how `01-moki.md` ended up
quoting a ceremony tile at (16,43) while `Map032.json` said (16,42)). Everything
here is read straight out of `output/uranium-build/`.

Inputs, all produced by earlier phases:

* ``maps/Map###.json``            — deserialized RMXP maps (events, pages, commands)
* ``map_infos.json``              — map names and the authors' own play-order tree
* ``connections.json``            — the 14 outdoor seams, as ``[a, dirA, offA, b, dirB, offB]``
* ``intermediate/wild_encounters.json`` — per-map encounter tables
* ``transpile_unhandled.jsonl``   — the transpiler's queue (see the caveat below)

**Queue caveat.** The unhandled queue currently only covers maps that have been
*staged*, i.e. slice 1. Until a gate-tolerant corpus survey exists, a zero in the
``unhandled`` column means "never transpiled", not "clean" — so it is reported as
``None`` for unstaged maps rather than 0, per §4.5.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# RMXP event-command codes we care about. Names match the RGSS docs; see
# reference/guides/rgss_event_commands.md.
CODE_TEXT = 101
CODE_CHOICE = 102
CODE_CONDITIONAL = 111
CODE_CONTROL_SWITCH = 121
CODE_CONTROL_VAR = 122
CODE_CHANGE_ITEMS = 126
CODE_TRANSFER = 201
CODE_MOVE_ROUTE = 209
CODE_BATTLE = 301
CODE_SHOP = 302
CODE_SCRIPT = 355
CODE_SCRIPT_CONT = 655

_SCRIPT_HEAD = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.]*)")

# Conditional-branch parameter[0] discriminator for "condition is a Ruby
# expression"; the expression itself is parameter[1]. This matters more than it
# looks: EVERY trainer battle in Uranium is a code-111/type-12 branch wrapping
# `pbTrainerBattle(...)` — there is not a single code-301 (Battle Processing)
# command in the corpus — so a census that only reads 301 and 355 reports zero
# trainers for the whole game.
COND_TYPE_SCRIPT = 12

# Ruby control-flow words that can legitimately open an embedded script block.
# They are real signal (they mark the branch-heavy tail the transpiler queues),
# but they are not *mechanics*, so they get counted separately from `pbXxx` heads.
RUBY_KEYWORDS = frozenset({
    "for", "if", "unless", "while", "until", "case", "begin", "end", "return",
    "next", "break", "do", "then", "else", "elsif", "when", "yield", "raise",
    "i", "j", "x", "y", "n", "list", "a", "b", "c", "e", "p", "s", "t", "v",
})

# Script-call head -> the player-facing mechanic it implements. Used to answer
# "what does this chapter need the engine to do", which is the question the
# capability ledger (reference/guides/command_pokeemerald_map.md) answers per row.
MECHANIC_BY_HEAD: dict[str, str] = {
    "pbTrainerBattle": "trainer battle",
    "pbDoubleTrainerBattle": "double trainer battle",
    "pbWildBattle": "scripted wild battle",
    "pbItemBall": "item ball",
    "pbReceiveItem": "item grant",
    "pbPokemonMart": "poke mart",
    "pbPokemonBerryMart": "berry mart",
    "pbPokeCenterPC": "PC access",
    "pbHealAll": "party heal",
    "pbSurf": "surf",
    "pbFishing": "fishing",
    "pbRockSmash": "rock smash",
    "pbStrength": "strength",
    "pbCutTree": "cut",
    "pbWaterfall": "waterfall",
    "pbDive": "dive",
    "pbBridge": "bridge layer",
    "pbSlotMachine": "slot machine",
    "pbVoltorbFlip": "voltorb flip",
    "pbLottery": "lottery",
    "pbDayCare": "day care",
    "pbMoveTutor": "move tutor",
    "pbMoveRelearner": "move relearner",
    "pbNicknameAndStore": "gift pokemon",
    "pbChooseNuclearCurePokemon": "nuclear cure",
    "pbPhoneRegisterBattle": "phone / rematch",
    "pbPhoneRegisterNPC": "phone / rematch",
    "pbPhoneIncrement": "phone / rematch",
    "pbPhoneBattleCount": "phone / rematch",
    "pbMetro": "metro fast travel",
    "pbRockSmash": "rock smash",
    "pbRockSmashRandomEncounter": "rock smash encounter",
    "pbCaveEntrance": "cave entry/exit",
    "pbCaveExit": "cave entry/exit",
    "pbBerryPlant": "berry plant",
    "pbPickBerry": "berry plant",
    "pbCancelVehicles": "vehicle state",
    "pbNoticePlayer": "trainer sight",
    "pbTrainerIntro": "trainer sight",
    "pbTrainerEnd": "trainer sight",
    "pbTrainerPC": "PC access",
    "pbShowMap": "region map",
    "pbAddPokemon": "gift pokemon",
    "pbHasSpecies": "party species check",
    "displayNinjaLetter": "bespoke letter UI",
}


@dataclass
class MapCensus:
    """Per-map mechanical inventory."""

    map_id: int
    name: str
    width: int
    height: int
    tileset_id: int
    events: int = 0
    pages: int = 0
    commands: int = 0
    warps_out: list[tuple[int, int, int]] = field(default_factory=list)
    trainer_battles: int = 0
    item_grants: int = 0
    shops: int = 0
    switch_writes: int = 0
    var_writes: int = 0
    choices: int = 0
    conditionals: int = 0
    move_routes: int = 0
    script_heads: Counter = field(default_factory=Counter)
    ruby_blocks: Counter = field(default_factory=Counter)
    encounter_tables: list[str] = field(default_factory=list)
    unhandled: int | None = None

    @property
    def warp_destinations(self) -> set[int]:
        return {d for d, _, _ in self.warps_out}


@dataclass
class ChapterCensus:
    """Aggregate of a chapter's maps, plus the chapter-level derived facts."""

    chapter_id: str
    title: str
    act: str
    visit: int
    tier: str
    maps: list[MapCensus] = field(default_factory=list)
    seams: list[list] = field(default_factory=list)

    @property
    def totals(self) -> dict[str, int]:
        return {
            "maps": len(self.maps),
            "events": sum(m.events for m in self.maps),
            "pages": sum(m.pages for m in self.maps),
            "commands": sum(m.commands for m in self.maps),
            "trainer_battles": sum(m.trainer_battles for m in self.maps),
            "item_grants": sum(m.item_grants for m in self.maps),
            "shops": sum(m.shops for m in self.maps),
            "switch_writes": sum(m.switch_writes for m in self.maps),
            "var_writes": sum(m.var_writes for m in self.maps),
            "choices": sum(m.choices for m in self.maps),
            "conditionals": sum(m.conditionals for m in self.maps),
            "move_routes": sum(m.move_routes for m in self.maps),
        }

    @property
    def script_heads(self) -> Counter:
        total: Counter = Counter()
        for m in self.maps:
            total.update(m.script_heads)
        return total

    @property
    def ruby_blocks(self) -> Counter:
        """Embedded-Ruby blocks opening on a control-flow keyword — the hard tail."""
        total: Counter = Counter()
        for m in self.maps:
            total.update(m.ruby_blocks)
        return total

    @property
    def mechanics(self) -> list[str]:
        """Player-facing mechanics this chapter needs, sorted."""
        found = {MECHANIC_BY_HEAD[h] for h in self.script_heads
                 if h in MECHANIC_BY_HEAD}
        if any(m.encounter_tables for m in self.maps):
            found.add("wild encounters")
        if any(m.shops for m in self.maps):
            found.add("poke mart")
        return sorted(found)

    @property
    def unknown_script_heads(self) -> list[str]:
        """Script heads with no mechanic mapping — the capability-ledger backlog."""
        return sorted(h for h in self.script_heads if h not in MECHANIC_BY_HEAD)

    @property
    def external_warp_destinations(self) -> set[int]:
        """Warp targets outside this chapter's own map set (chapter exits)."""
        own = {m.map_id for m in self.maps}
        return {d for m in self.maps for d in m.warp_destinations} - own


def _script_head(text: str) -> str | None:
    """Leading identifier of a Ruby expression, with `Kernel.` normalised away.

    Uranium's authors call the same helper both bare and `Kernel.`-qualified
    (`pbItemBall` and `Kernel.pbItemBall` both occur), so without normalising
    the prefix one mechanic shows up as two unrelated heads.
    """
    match = _SCRIPT_HEAD.match(text or "")
    if not match:
        return None
    head = match.group(1)
    return head[len("Kernel."):] if head.startswith("Kernel.") else head


def _census_one_map(
    map_id: int,
    maps_dir: Path,
    infos: dict,
    encounters: dict,
    queue_counts: Counter,
    staged: set[int],
) -> MapCensus:
    path = maps_dir / f"Map{map_id:03d}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"chapter census: no converted map for id {map_id} at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    info = infos.get(str(map_id), {})

    cen = MapCensus(
        map_id=map_id,
        name=info.get("name", "?"),
        width=data.get("width", 0),
        height=data.get("height", 0),
        tileset_id=data.get("tileset_id", 0),
        unhandled=queue_counts.get(map_id, 0) if map_id in staged else None,
    )

    table = encounters.get("maps", {}).get(str(map_id))
    if table:
        cen.encounter_tables = sorted(k for k in table if k != "uranium_extra")
        if "uranium_extra" in table:
            cen.encounter_tables.extend(
                f"uranium_extra:{k}" for k in sorted(table["uranium_extra"]))

    for event in data.get("events", []):
        cen.events += 1
        for page in event.get("pages", []):
            cen.pages += 1
            for cmd in (page.get("list") or []):
                code = cmd.get("code")
                if code == 0:
                    continue
                cen.commands += 1
                params = cmd.get("parameters", [])
                if code == CODE_TRANSFER and len(params) >= 4:
                    cen.warps_out.append((params[1], params[2], params[3]))
                elif code == CODE_BATTLE:
                    cen.trainer_battles += 1
                elif code == CODE_CHANGE_ITEMS:
                    cen.item_grants += 1
                elif code == CODE_SHOP:
                    cen.shops += 1
                elif code == CODE_CONTROL_SWITCH:
                    cen.switch_writes += 1
                elif code == CODE_CONTROL_VAR:
                    cen.var_writes += 1
                elif code == CODE_CHOICE:
                    cen.choices += 1
                elif code == CODE_CONDITIONAL:
                    cen.conditionals += 1
                    if (len(params) >= 2 and params[0] == COND_TYPE_SCRIPT
                            and isinstance(params[1], str)):
                        _record_script(cen, params[1])
                elif code == CODE_MOVE_ROUTE:
                    cen.move_routes += 1
                elif code == CODE_SCRIPT and params:
                    _record_script(cen, str(params[0]))
    return cen


def _record_script(cen: MapCensus, text: str) -> None:
    """Attribute one embedded-Ruby expression to a head, and to a mechanic."""
    head = _script_head(text)
    if not head:
        return
    if head in RUBY_KEYWORDS:
        cen.ruby_blocks[head] += 1
        return
    cen.script_heads[head] += 1
    if head in ("pbTrainerBattle", "pbDoubleTrainerBattle"):
        cen.trainer_battles += 1
    elif head in ("pbItemBall", "pbReceiveItem"):
        cen.item_grants += 1


def _load_queue_counts(out_dir: Path) -> tuple[Counter, set[int]]:
    """Per-map unhandled counts, plus the set of maps the queue actually covers."""
    path = out_dir / "transpile_unhandled.jsonl"
    counts: Counter = Counter()
    staged: set[int] = set()
    if not path.exists():
        logger.warning("no transpile_unhandled.jsonl at %s; queue columns blank", path)
        return counts, staged
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        map_id = row.get("map_id")
        if map_id is None:  # a CommonEvents entry, not attributable to a map
            continue
        counts[map_id] += 1
        staged.add(map_id)
    return counts, staged


def census_for_maps(
    map_ids: list[int],
    *,
    out_dir: Path,
    chapter_id: str = "",
    title: str = "",
    act: str = "",
    visit: int = 1,
    tier: str = "",
) -> ChapterCensus:
    """Census an explicit map list. The chapter fields are labels only."""
    maps_dir = out_dir / "maps"
    infos = json.loads((out_dir / "map_infos.json").read_text(encoding="utf-8"))
    enc_path = out_dir / "intermediate" / "wild_encounters.json"
    encounters = (json.loads(enc_path.read_text(encoding="utf-8"))
                  if enc_path.exists() else {})
    conn_path = out_dir / "connections.json"
    connections = (json.loads(conn_path.read_text(encoding="utf-8"))
                   if conn_path.exists() else [])
    queue_counts, staged = _load_queue_counts(out_dir)

    result = ChapterCensus(
        chapter_id=chapter_id, title=title, act=act, visit=visit, tier=tier)
    own = set(map_ids)
    for map_id in map_ids:
        result.maps.append(_census_one_map(
            map_id, maps_dir, infos, encounters, queue_counts, staged))
    result.seams = [c for c in connections
                    if len(c) >= 4 and (c[0] in own or c[3] in own)]
    return result
