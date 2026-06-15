"""Census of the Uranium command vocabulary, strict-filtered. Zero LLM.

Walks every command in all 199 maps + 100 common events (no handled/unhandled
filtering, no reference-doc trust) and splits the vocabulary into:

  * REAL mappable commands  -> reference/uranium_real_commands.md
  * excluded non-commands   -> reference/uranium_excluded_noncommands.md

A "command" is something the event DOES: a structural RMXP code (minus pure
scaffolding/continuation) OR a script-call head that is a named engine call.
Excluded: list terminator + continuation codes, Ruby keywords, anonymous
expressions, assignments / state-writes, local-variable receivers, and pure
branch-condition reads.

Run:  python3 scripts/count_unique_commands.py
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAPS = REPO / "output" / "uranium-build" / "maps"
COMMON = REPO / "output" / "uranium-build" / "common_events.json"
OUT_REAL = REPO / "reference" / "uranium_real_commands.md"
OUT_EXCL = REPO / "reference" / "uranium_excluded_noncommands.md"

SCRIPT_CODES = {355, 655}
CONDITIONAL = 111
COND_SCRIPT_KIND = 12

# Standard RMXP command-code names (fixed published spec, not a project doc).
CODE_NAME = {
    0: "(list terminator)", 101: "Show Text", 102: "Show Choices",
    103: "Input Number", 104: "Change Text Options", 106: "Wait",
    108: "Comment", 111: "Conditional Branch", 112: "Loop", 113: "Break Loop",
    115: "Exit Event Processing", 116: "Erase Event", 117: "Call Common Event",
    118: "Label", 119: "Jump to Label", 121: "Control Switches",
    122: "Control Variables", 123: "Control Self Switch", 124: "Control Timer",
    125: "Change Gold", 132: "Change Battle BGM", 135: "Change Menu Access",
    201: "Transfer Player", 202: "Set Event Location", 203: "Scroll Map",
    204: "Change Map Settings", 206: "Change Fog Opacity", 207: "Show Animation",
    208: "Change Transparent Flag", 209: "Set Move Route",
    210: "Wait for Move's Completion", 221: "Prepare for Transition",
    222: "Execute Transition", 223: "Change Screen Color Tone",
    224: "Screen Flash", 225: "Screen Shake", 231: "Show Picture",
    232: "Move Picture", 234: "Change Picture Color Tone", 235: "Erase Picture",
    241: "Play BGM", 242: "Fade Out BGM", 245: "Play BGS", 246: "Fade Out BGS",
    247: "Memorize BGM/BGS", 249: "Play ME", 250: "Play SE", 314: "Recover All",
    355: "Script", 401: "Show Text (cont.)", 402: "Show Choices [When]",
    403: "Show Choices [When Cancel]", 404: "Show Choices [Branch End]",
    408: "Comment (cont.)", 411: "Conditional Branch [Else]",
    412: "Conditional Branch [End]", 413: "Repeat Above", 509: "Move Command",
    655: "Script (cont.)",
}

# Codes that never need their own disposition: list terminator + continuations
# of a parent command (handled with the parent). 509 = move-route body of 209.
SCAFFOLD = {0, 401, 402, 403, 404, 408, 411, 412, 413, 509, 655}

KEYWORDS = {
    "if", "for", "while", "case", "when", "unless", "until", "raise", "begin",
    "return", "next", "break", "yield", "then", "do", "else", "elsif", "end", "rescue",
}

_HEAD_RE = re.compile(
    r"^\s*(?:Kernel\.|\$[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)"
)


def script_head(s: str) -> str:
    m = _HEAD_RE.match(s or "")
    return m.group(1) if m else "<expr>"


def stripped(s: str) -> str:
    """Drop a leading Kernel./$var. receiver so the head sits at index 0."""
    return re.sub(r"^\s*(?:Kernel\.|\$[A-Za-z_][A-Za-z0-9_]*\.)", "", s or "").lstrip()


# ---- classification of a script head over all its raw occurrences ----

def is_command(head: str, raws: list[str]) -> bool:
    # The head sits at index 0 of the stripped string, so anchor every test there.
    if head == "<expr>" or head in KEYWORDS:
        return False
    esc = re.escape(head)
    if re.match(r"(pb|jv|nuz)[A-Z]", head):  # engine-call naming convention
        return True
    for r in raws:
        s = stripped(r)
        if re.match(rf"{esc}\s*\??\s*\(", s):   # head( / head?(  -> call
            return True
        if re.match(rf"{esc}\?", s):            # predicate head?
            return True
        if re.match(rf"{esc}\s*(?:;|$)", s):    # bareword statement (no-arg call)
            return True
    if head[0].isupper():                       # Module.method API
        if any(re.match(rf"{esc}\.", stripped(r)) for r in raws):
            return True
    return False


_ASSIGN = r"\s*(?:\[[^\]]*\])?\s*(?<![<>=!+\-*/])(?:\+=|-=|=)(?!=)"


def excluded_reason(head: str, raws: list[str]) -> str:
    if head == "<expr>":
        return "anonymous expression"
    if head in KEYWORDS:
        return "Ruby keyword / control-flow"
    esc = re.escape(head)
    for r in raws:
        if re.match(rf"{esc}{_ASSIGN}", stripped(r)):
            # $Obj.field = … is a global game-state write (mappable to setflag/
            # setvar/give-*); a bare local = … is just scratch computation.
            return ("global state-write (mappable)" if r.lstrip().startswith("$")
                    else "local scratch variable")
    for r in raws:
        if re.match(rf"{esc}\.", stripped(r)):
            return "local-variable receiver"
    return "branch-condition read"


def walk(cmds, codes, runs_355, cond):
    pend: list[str] = []
    for c in cmds:
        code = c.get("code", 0)
        p = c.get("parameters") or []
        if code in SCRIPT_CODES:
            codes[code] += 1
            t = p[0] if p and isinstance(p[0], str) else ""
            if code == 355:
                if pend:
                    runs_355.append(" ; ".join(pend))
                pend = [t]
            else:
                pend.append(t)
            continue
        if pend:
            runs_355.append(" ; ".join(pend))
            pend = []
        codes[code] += 1
        if code == CONDITIONAL and p and p[0] == COND_SCRIPT_KIND:
            cond.append(p[1] if len(p) > 1 and isinstance(p[1], str) else "")
    if pend:
        runs_355.append(" ; ".join(pend))


def main() -> None:
    codes: Counter[int] = Counter()
    runs_355: list[str] = []
    cond: list[str] = []
    n_maps = n_events = n_pages = 0

    for mp in sorted(MAPS.glob("Map*.json")):
        n_maps += 1
        d = json.loads(mp.read_text(encoding="utf-8"))
        for ev in d.get("events", []):
            n_events += 1
            for pg in ev.get("pages", []):
                n_pages += 1
                walk(pg.get("list", []), codes, runs_355, cond)
    n_ce = 0
    if COMMON.exists():
        for ce in json.loads(COMMON.read_text(encoding="utf-8")):
            n_ce += 1
            walk(ce.get("list", []), codes, runs_355, cond)

    # head -> {count, raws, sources}
    heads: dict[str, dict] = defaultdict(lambda: {"n": 0, "raws": [], "src": set()})
    for src, runs in (("script", runs_355), ("cond", cond)):
        for r in runs:
            h = script_head(r)
            e = heads[h]
            e["n"] += 1
            e["src"].add(src)
            if len(e["raws"]) < 60:
                e["raws"].append(r)

    real_heads = {h: e for h, e in heads.items() if is_command(h, e["raws"])}
    excl_heads = {h: e for h, e in heads.items() if h not in real_heads}

    real_codes = sorted(c for c in codes if c not in SCAFFOLD and c != 355)

    # ---------- File 1: real mappable commands ----------
    L = []
    L.append("# Uranium — real mappable command vocabulary (data-derived)\n")
    L.append(f"> Generated by `scripts/count_unique_commands.py` from the deserialized corpus "
             f"({n_maps} maps, {n_events} events, {n_pages} pages, {n_ce} common events).\n"
             f"> No reference-doc input. A *command* is something an event DOES: a structural\n"
             f"> RMXP code (minus scaffolding) or a script-call head that names an engine call.\n")
    L.append(f"\n**Structural RMXP commands: {len(real_codes)}**  ·  "
             f"**script-call commands: {len(real_heads)}**  ·  "
             f"**TOTAL unique: {len(real_codes) + len(real_heads)}**\n")
    L.append("\n## A. Structural RMXP commands\n")
    L.append("| Code | Name | Occurrences |")
    L.append("|---|---|---|")
    for c in real_codes:
        L.append(f"| {c} | {CODE_NAME.get(c, '?')} | {codes[c]} |")
    L.append(f"\n## B. Script-call commands ({len(real_heads)})\n")
    L.append("Source: `script` = 355/655 Script command · `cond` = code-111 script branch (action-with-result).\n")
    L.append("| Head | Occurrences | Source |")
    L.append("|---|---|---|")
    for h, e in sorted(real_heads.items(), key=lambda kv: -kv[1]["n"]):
        L.append(f"| `{h}` | {e['n']} | {'+'.join(sorted(e['src']))} |")
    OUT_REAL.write_text("\n".join(L) + "\n", encoding="utf-8")

    # ---------- File 2: excluded non-commands ----------
    by_reason: dict[str, list[tuple[str, int, list[str]]]] = defaultdict(list)
    for h, e in excl_heads.items():
        by_reason[excluded_reason(h, e["raws"])].append((h, e["n"], e["raws"]))

    M = []
    M.append("# Uranium — excluded as NON-commands (data-derived)\n")
    M.append("> Generated by `scripts/count_unique_commands.py`. These tokens were counted by\n"
             "> a naive head-extractor but are NOT distinct *named* commands. Each section says\n"
             "> what they actually are, with real examples. NOTE: the first section (global\n"
             "> state-writes) *is* mappable to setflag/setvar/give-* — it's just not a named\n"
             "> command; the rest is genuine Ruby plumbing → Opus/JUDGE or handled with a parent.\n")

    # scaffolding codes
    scaff = sorted(c for c in codes if c in SCAFFOLD)
    M.append(f"\n## Scaffolding / continuation RMXP codes ({len(scaff)})\n")
    M.append("Continuations of a parent command (or the list terminator) — handled with the parent, no own disposition.\n")
    M.append("| Code | Name | Occurrences | Rides on |")
    M.append("|---|---|---|---|")
    rides = {0: "—", 401: "101", 402: "102", 403: "102", 404: "102", 408: "108",
             411: "111", 412: "111", 413: "112", 509: "209", 655: "355"}
    for c in scaff:
        M.append(f"| {c} | {CODE_NAME.get(c, '?')} | {codes[c]} | {rides.get(c, '?')} |")

    order = ["global state-write (mappable)", "Ruby keyword / control-flow",
             "anonymous expression", "local scratch variable",
             "local-variable receiver", "branch-condition read"]
    blurb = {
        "global state-write (mappable)": "**These ARE mappable** — `$Trainer.badges[0]=true` → give-badge flag, `$PokemonGlobal.runningShoes=true` → setflag, `$Trainer.money-=N` → removemoney. They fold into the conversion via setflag/setvar/give-*, but are raw assignments, not a distinct *named* command.",
        "Ruby keyword / control-flow": "Ruby control flow opening a script block; the real ops (if any) are the calls *inside* it → Opus/JUDGE.",
        "anonymous expression": "No callable head. A mix of `$game_variables[..]=` / `$game_switches[..]=` (these map to setvar/setflag) and one-off `$scene=...` pokes → mostly handled, some Opus/JUDGE.",
        "local scratch variable": "A Ruby local holding an intermediate value (`x=pbGet(1)`, `item=[...]`); the real ops are the calls that consume it → Opus/JUDGE.",
        "local-variable receiver": "Head is a local object the script then calls methods on; the real op is the method, buried mid-block → Opus/JUDGE.",
        "branch-condition read": "A property/state read used only as a conditional test (code 111). It tests, it doesn't act.",
    }
    total_excl = 0
    for reason in order:
        items = sorted(by_reason.get(reason, []), key=lambda t: -t[1])
        total_excl += len(items)
        M.append(f"\n## {reason} ({len(items)} heads)\n")
        M.append(blurb[reason] + "\n")
        M.append("| Head | Occ | Example |")
        M.append("|---|---|---|")
        for h, n, raws in items:
            ex = raws[0].replace("|", "\\|")[:90] if raws else ""
            M.append(f"| `{h}` | {n} | `{ex}` |")

    M.append(f"\n---\n\n**Excluded totals:** {len(scaff)} scaffolding codes + {total_excl} non-command heads.\n")
    OUT_EXCL.write_text("\n".join(M) + "\n", encoding="utf-8")

    # ---------- console summary ----------
    print(f"corpus: {n_maps} maps, {n_events} events, {n_pages} pages, {n_ce} common events")
    print(f"distinct RMXP codes: {len(codes)}  (scaffolding {len(scaff)}, real structural {len(real_codes)}, +Script umbrella)")
    print(f"distinct script heads: {len(heads)}  (REAL commands {len(real_heads)}, excluded {len(excl_heads)})")
    print()
    print(f"REAL MAPPABLE COMMANDS = {len(real_codes)} structural + {len(real_heads)} script = "
          f"{len(real_codes) + len(real_heads)}")
    print()
    for reason in order:
        print(f"  excluded[{reason}]: {len(by_reason.get(reason, []))}")
    print()
    print(f"wrote {OUT_REAL.relative_to(REPO)}")
    print(f"wrote {OUT_EXCL.relative_to(REPO)}")


if __name__ == "__main__":
    main()
