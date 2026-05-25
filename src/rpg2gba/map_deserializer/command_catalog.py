"""Command-code reference + script-call inventory + switch/var dump.

PHASE3_PLAN §3.2 / §3.3. Three derived artifacts, all from the deserialized JSON:

- `reference/rgss_event_commands.md` — every RPG Maker command code Uranium uses,
  with an Essentials→Poryscript tag (Direct / Adaptable / NeedsC / Strip) and the
  occurrence count. Plus a list of the distinct script-call signatures seen in
  Script commands (355/655) — the real Phase 4 translation surface (E2).
- `reference/uranium_switches.json` / `uranium_variables.json` — the named
  switch/variable tables from `System.rxdata`, the Phase 4 flag-registry seed (E6).

The tags are advisory and get human review at the §V5 gate; they are a starting
point, not gospel. The hard guarantee here is the **coverage assertion**: any
command code outside `CATALOG` is fail-loud (E7) — `map_inventory.md` shows zero
unknown codes today, so this locks that invariant.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

# code -> (name, tag). Tag ∈ {Direct, Adaptable, NeedsC, Strip}.
# Superset of the standard RGSS / RPG Maker XP command set (recon_maps.rb
# COMMON_CODES + continuations), so the coverage check is meaningful even for
# codes Uranium doesn't currently use. Names from the RMXP RGSS reference.
CATALOG: dict[int, tuple[str, str]] = {
    0: ("(blank / end of list)", "Direct"),
    # --- Messages ---
    101: ("Show Text", "Direct"),
    401: ("Show Text (continuation)", "Direct"),
    102: ("Show Choices", "Direct"),
    402: ("When [choice]", "Direct"),
    403: ("When Cancel", "Direct"),
    404: ("Show Choices (branch end)", "Direct"),
    103: ("Input Number", "Adaptable"),
    104: ("Change Text Options", "Strip"),
    105: ("Button Input Processing", "Adaptable"),
    106: ("Wait", "Direct"),
    108: ("Comment", "Direct"),
    408: ("Comment (continuation)", "Direct"),
    # --- Flow control ---
    111: ("Conditional Branch", "Direct"),
    411: ("Else", "Direct"),
    412: ("Branch End", "Direct"),
    413: ("Repeat Above (loop end)", "Adaptable"),
    112: ("Loop", "Adaptable"),
    113: ("Break Loop", "Adaptable"),
    115: ("Exit Event Processing", "Direct"),
    116: ("Erase Event", "Adaptable"),
    117: ("Call Common Event", "Direct"),
    118: ("Label", "Adaptable"),
    119: ("Jump to Label", "Adaptable"),
    # --- Game data ---
    121: ("Control Switches", "Direct"),
    122: ("Control Variables", "Direct"),
    123: ("Control Self Switch", "Direct"),
    124: ("Control Timer", "Adaptable"),
    125: ("Change Gold", "Adaptable"),
    126: ("Change Items", "Adaptable"),
    127: ("Change Weapons", "Strip"),
    128: ("Change Armor", "Strip"),
    129: ("Change Party Member", "Adaptable"),
    131: ("Change Windowskin", "Strip"),
    132: ("Change Battle BGM", "Adaptable"),
    133: ("Change Battle End ME", "Strip"),
    134: ("Change Save Access", "Adaptable"),
    135: ("Change Menu Access", "Adaptable"),
    136: ("Change Encounter", "Adaptable"),
    # --- Map / movement ---
    201: ("Transfer Player", "Direct"),
    202: ("Set Event Location", "Adaptable"),
    203: ("Scroll Map", "Adaptable"),
    204: ("Change Map Settings", "Adaptable"),
    205: ("Change Fog Color Tone", "Strip"),
    206: ("Change Fog Opacity", "Strip"),
    207: ("Show Animation", "Adaptable"),
    208: ("Change Transparent Flag", "Adaptable"),
    209: ("Set Move Route", "Adaptable"),
    210: ("Wait for Move Completion", "Direct"),
    # --- Screen effects ---
    221: ("Prepare for Transition", "Adaptable"),
    222: ("Execute Transition", "Adaptable"),
    223: ("Change Screen Color Tone", "Adaptable"),
    224: ("Screen Flash", "Adaptable"),
    225: ("Screen Shake", "Adaptable"),
    # --- Pictures / weather ---
    231: ("Show Picture", "NeedsC"),
    232: ("Move Picture", "NeedsC"),
    233: ("Rotate Picture", "NeedsC"),
    234: ("Change Picture Tone", "NeedsC"),
    235: ("Erase Picture", "NeedsC"),
    236: ("Set Weather Effects", "Adaptable"),
    # --- Audio ---
    241: ("Play BGM", "Direct"),
    242: ("Fade Out BGM", "Direct"),
    243: ("Play BGS", "Adaptable"),
    244: ("Fade Out BGS", "Adaptable"),
    245: ("Memorize BGM/BGS", "Adaptable"),
    246: ("Restore BGM/BGS", "Adaptable"),
    247: ("Memorize BGM/BGS (alt)", "Adaptable"),
    248: ("Restore BGM/BGS (alt)", "Adaptable"),
    249: ("Play ME", "Direct"),
    250: ("Play SE", "Direct"),
    251: ("Stop SE", "Direct"),
    261: ("Show Movie", "Strip"),
    # --- Scene control ---
    281: ("Map Name Display (toggle)", "Adaptable"),
    282: ("Change Tileset", "Adaptable"),
    283: ("Change Battleback", "Adaptable"),
    284: ("Change Foreground", "Strip"),
    285: ("Get Terrain Tag", "Adaptable"),
    301: ("Battle Processing", "Adaptable"),
    302: ("Shop Processing", "Adaptable"),
    303: ("Name Input Processing", "Adaptable"),
    # --- Actor / battler changes (mostly battle-test or RM-RPG concepts) ---
    311: ("Change HP", "Strip"),
    312: ("Change SP", "Strip"),
    313: ("Change State", "Strip"),
    314: ("Recover All", "Adaptable"),
    315: ("Change EXP", "Strip"),
    316: ("Change Level", "Strip"),
    317: ("Change Parameters", "Strip"),
    318: ("Change Skills", "Strip"),
    319: ("Change Equipment", "Strip"),
    320: ("Change Actor Name", "Adaptable"),
    321: ("Change Actor Class", "Strip"),
    322: ("Change Actor Graphic", "Adaptable"),
    331: ("Enemy: Change HP", "Strip"),
    332: ("Enemy: Change SP", "Strip"),
    333: ("Enemy: Change State", "Strip"),
    334: ("Enemy: Recover All", "Strip"),
    335: ("Enemy Appearance", "Strip"),
    336: ("Enemy Transform", "Strip"),
    337: ("Show Battle Animation", "Strip"),
    338: ("Deal Damage", "Strip"),
    339: ("Force Action", "Strip"),
    340: ("Abort Battle", "Adaptable"),
    351: ("Call Menu Screen", "Adaptable"),
    352: ("Call Save Screen", "Adaptable"),
    353: ("Game Over", "Adaptable"),
    354: ("Return to Title Screen", "Adaptable"),
    # --- Scripting (the Essentials custom-behaviour surface) ---
    355: ("Script", "NeedsC"),
    655: ("Script (continuation)", "NeedsC"),
    # --- Move-route sub-command (inside a Set Move Route list) ---
    509: ("Move Command", "Adaptable"),
}

# Leading identifier of a script line: optional $/@ sigil, then a dotted name
# (e.g. `Kernel.pbMessage`, `pbReceiveItem`, `$game_variables`).
_SIG_RE = re.compile(r"\s*([$@]?[A-Za-z_][\w.]*)")


def _script_signature(param: object) -> str | None:
    """Leading call/identifier of a 355/655 script line, or None if unparseable."""
    if not isinstance(param, str):
        return None
    m = _SIG_RE.match(param)
    return m.group(1) if m else "(non-identifier)"


def _iter_command_lists(out_dir: Path):
    """Yield every command list in maps + common events."""
    for path in sorted((out_dir / "maps").glob("Map*.json")):
        m = json.loads(path.read_text(encoding="utf-8"))
        for ev in m["events"]:
            for page in ev["pages"]:
                yield page["list"]
    ce_path = out_dir / "common_events.json"
    if ce_path.is_file():
        for ce in json.loads(ce_path.read_text(encoding="utf-8")):
            yield ce["list"]


def build(out_dir: Path, reference_dir: Path) -> None:
    """Emit the §3.2 command reference + script-call list and the §3.3 sidecars."""
    out_dir = Path(out_dir)
    reference_dir = Path(reference_dir)

    code_counts: Counter[int] = Counter()
    sig_counts: Counter[str] = Counter()

    for cmd_list in _iter_command_lists(out_dir):
        for cmd in cmd_list:
            code = cmd["code"]
            code_counts[code] += 1
            if code in (355, 655):
                params = cmd.get("parameters") or []
                sig = _script_signature(params[0] if params else None)
                if sig:
                    sig_counts[sig] += 1

    # E7 coverage guard: every code in use must be cataloged.
    unknown = sorted(c for c in code_counts if c not in CATALOG)
    if unknown:
        raise RuntimeError(
            f"command codes not in CATALOG (PHASE3_PLAN §3.2/E7): {unknown}. "
            f"Add them to command_catalog.CATALOG with a tag before proceeding."
        )

    _write_command_reference(reference_dir / "rgss_event_commands.md", code_counts, sig_counts)
    _write_switch_var_tables(out_dir / "system.json", reference_dir)


def _write_command_reference(
    path: Path, code_counts: Counter[int], sig_counts: Counter[str]
) -> None:
    lines = [
        "# RGSS Event Command Reference (Uranium)",
        "",
        "> Generated by `rpg2gba.map_deserializer.command_catalog` (Phase 3 §3.2).",
        "> Do not hand-edit — re-run `python -m rpg2gba.pipeline phase3`.",
        "",
        "Every RPG Maker XP event command code that appears in Uranium's maps or "
        "common events, with an **advisory** Essentials→Poryscript disposition. "
        "Tags get human review at the §9 / §V5 gate.",
        "",
        "- **Direct** — has a 1:1 Poryscript equivalent.",
        "- **Adaptable** — expressible in Poryscript with restructuring.",
        "- **NeedsC** — needs a custom engine feature or Poryscript macro.",
        "- **Strip** — no GBA analogue; drop on conversion.",
        "",
        f"Codes in use: **{len(code_counts)}**. Total command instances: "
        f"**{sum(code_counts.values())}**.",
        "",
        "| Code | Name | Tag | Count |",
        "|---|---|---|---|",
    ]
    for code in sorted(code_counts):
        name, tag = CATALOG[code]
        lines.append(f"| {code} | {name} | {tag} | {code_counts[code]} |")

    lines += [
        "",
        "## Script calls (Phase 4 input)",
        "",
        "Distinct leading signatures of Script commands (codes 355/655). Uranium "
        "adds **no custom command codes** — its custom behaviour lives here, as "
        "`pbXxx` / Kernel / `$game_*` calls. Per-signature Direct/Adaptable/etc. "
        "classification is deferred to Phase 4 start (PHASE3_PLAN §E2); this is the "
        "inventory.",
        "",
        f"Distinct signatures: **{len(sig_counts)}**. Total script-call lines: "
        f"**{sum(sig_counts.values())}**.",
        "",
        "| Signature | Count |",
        "|---|---|",
    ]
    for sig, n in sig_counts.most_common():
        lines.append(f"| `{sig}` | {n} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info(
        "wrote %s (%d codes, %d script signatures)", path, len(code_counts), len(sig_counts)
    )


def _write_switch_var_tables(system_json: Path, reference_dir: Path) -> None:
    """Dump named switches/variables from system.json (E6 — Phase 4 seed)."""
    sys = json.loads(system_json.read_text(encoding="utf-8"))
    fields = (("switches", "uranium_switches.json"), ("variables", "uranium_variables.json"))
    for field, out_name in fields:
        names = sys.get(field) or []
        # Index 0 is nil in RMXP; keep only entries with a real name.
        table = {
            str(i): name
            for i, name in enumerate(names)
            if isinstance(name, str) and name.strip()
        }
        out = reference_dir / out_name
        out.write_text(json.dumps(table, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        logger.info("wrote %s (%d named %s)", out, len(table), field)
