# Grill session — chapter atlas (2026-07-30)

Interactive grill on *planning the full set of chapter documents for the
remaining slices*. Decisions are the user's; rationale and the evidence that
shaped each question are mine. Companion to `ROM_TEST_DEV.md`'s 2026-07-18
session, which settled the harness; this one settles the **planning layer above
it**.

Deliverables from this session: `reference/chapters.json` (the binding),
`src/rpg2gba/chapter_atlas/` (loader + census + CLI), `reference/chapters/00-atlas.md`
(the shallow corpus-wide document), 27 tests, and four corrected documents.

---

## Decisions

| # | Question | Decision |
|---|---|---|
| 1 | Planning depth across ~190 maps | **Shallow corpus-wide atlas + one document per chapter, detail decaying with distance from the frontier.** |
| 2 | Chapter boundary rule | **Wiki walkthrough sections** — after establishing the page is readable (see below). |
| 3 | Granularity, given sections span ~5 locations | **Two levels: Act = walkthrough section, Chapter = location unit.** Chapter ≡ slice ≡ §9 gate ≡ ROM-test scenario is preserved. |
| 4 | Detail gradient | **Distance tiers (full / medium / thin) + promote one tier where a mechanic first appears.** |
| 5 | Home of the "new C vs pokeemerald" analysis | **Central ledger is SoT; chapters carry a thin binding table.** One place to fix a wrong verdict. |
| 6 | Source of per-chapter facts | **Committed, re-runnable census tool; documents cite its output.** |
| 7 | Revisited locations | **Chapter = (location, visit).** A revisit is its own chapter over the same maps. |
| 8 | Session scope | **Foundation now** (fetch script, binding, census, atlas), chapter documents next. |
| 9 | Home of the chapter→map binding | **`reference/chapters.json` as §4.3 SoT**; `map_set.py` to derive `SLICE_MAP_IDS` from it at the slice-2 cutover. |

## Findings that changed the plan

**The wiki *is* reachable — only one route works.** `WebFetch` returns HTTP 402
for every `pokemon-uranium.fandom.com` URL including `api.php`; a bare `curl`
gets 403 from Cloudflare. The MediaWiki API **with a browser User-Agent** returns
200. Wrapped as `scripts/fetch_uranium_wiki.py`. This unblocked decision 2, which
had looked unexecutable. `ROM_TEST_DEV.md`'s "fandom returns 402 here, research
goes through WebSearch snippets" is now superseded.

**The walkthrough and the map tree agree; the skill file was the liar.**
`.claude/skills/pokemon-uranium-wiki/SKILL.md` invented Seaspray Town and Ara
City, omitted Burole Town and its Gym, and assigned Gyms to two towns that have
none. The walkthrough body and `map_infos.json` agree with each other on all
eight Gyms. Corrected.

**Every trainer battle in the game is hidden inside a conditional.** There is not
one code-301 (Battle Processing) command in the corpus; all 317 trainer battles
are code-111 branches with condition type 12, wrapping `pbTrainerBattle(...)`.
A census reading 301 and 355 reports **zero trainers for the entire game** — the
first version of the census tool did exactly that, and the error was only caught
because `01-moki.md` independently documented Theo's battle. Pinned by
`tests/test_chapter_atlas.py::test_census_counts_trainer_battles_hidden_in_conditionals`.

**The capability ledger was recommending the invented symbol.** `CLAUDE.md` §4.7
and `BUILD_PLAN.md` §4 both pointed the "native-analog ledger" at
`essentials_to_emerald_map.md`, which is the registry's flag/var pre-seed table.
The real ledger, `command_pokeemerald_map.md`, contained `healparty` in **two
mutually-reinforcing rows** — the second marked "✓ vocabulary" on the strength of
the first. A full audit against the engine found **2 missing symbols and 6
over-claims**:

| Row | Was | Is |
|---|---|---|
| 314 Recover All / `pbHealAll` | `healparty` | `special HealPlayerParty` (`specials.inc:20`) |
| `pbPushThisBoulder` | `MB_PUSHABLE_BOULDER` | `OBJ_EVENT_GFX_PUSHABLE_BOULDER` (`event_objects.h:113`) — object-driven, not metatile-driven |
| 207 Show Animation | "no clean field-script analogue" | `dofieldeffect` + ~40 `FLDEFF_*` (`event.inc:1426`) |
| 203 Scroll Map | "needs a special" | `SpawnCameraObject` / `RemoveCameraObject` (`specials.inc:298-299`) |
| 225 Screen Shake | "no clean field analogue" | `special ShakeCamera` (`specials.inc:332`) |
| `pbSlotMachine` | C | `playslotmachine` (`event.inc:1297`) |
| `pbLottery` | C | native Lottery Corner (`specials.inc:240-241,280-281`) |
| `pbPhoneRegister*` | C | likely native Match Call (`specials.inc:80-82,508`) |

The structural lesson is not the individual errors. Rows 111–115 got confident
`✓VERIFIED native` tags while rows 62/75/76 got hedged `C/JUDGE` tags for
features that were *equally easy to grep for*. **The asymmetry is the bug** —
the §4.7 discipline was applied to some rows and not others in the same file.

**The new-C set is small and localised.** After the corrections, the only
genuinely-absent engine features in the whole game are **Voltorb Flip** and the
**Nuclear type**. Voltorb Flip, the lottery and the slot machine are confined to
Bealbeach City, so the entire minigame question is one location's problem.

**Conversion-readiness is unmeasured for 195 of 199 maps.** The unhandled queue
covers only staged maps. A corpus survey aborts: the fork-index gate fails on
Map008 because Uranium `TRAINER_*` constants are staged for slice 1 only. The
census therefore reports `unhandled: null`, never a misleading `0`. Separately,
`transpile_driver.py:405` writes the queue file *outside* the `if write:` guard,
so `--dry-run` is not dry.

## Rejected / not pursued

* **Chapter = walkthrough section (9 chapters).** Would have made each chapter
  ~5 slices, breaking chapter ≡ slice and demoting `01-moki.md` to a fragment.
* **Full declarative beat schema.** The `moki.py` evidence says the interesting
  beats are exactly the ones needing custom frames, settles and prompt detection.
  Plain Python stands (C4a); what changes is a shared `playtest/beats.py`
  vocabulary and a deeper doc↔test binding.
* **Deep documents for all ~40 chapters up front.** Rejected in favour of the
  decaying gradient; the later half would be stale before use.

## Next

1. **Chapter documents**, frontier-first: CH02 Route 1 at full tier, then CH03–CH06 at medium.
2. **Gate-tolerant corpus transpile survey** — the highest-value follow-up; it is what turns "what needs new code per chapter" from inference into data.
3. **Fix the `--dry-run` write guard.**
4. **`playtest/beats.py`** extraction + deepen the doc↔test binding from ids/order to gates and coordinates.
5. **`map_set.SLICE_MAP_IDS` derives from `chapters.json`** at the slice-2 cutover.
