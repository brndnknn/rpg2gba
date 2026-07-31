# Chapter-document template and authoring contract

**Status:** live. This is the shape every document in `reference/chapters/`
follows, and the contract an author — human or agent — is held to. Written
2026-07-31 alongside the first batch of documents authored from it (CH02–CH06);
`01-moki.md` predates it and is the worked example the template was extracted
from.

**Why this exists.** 59 chapter documents will eventually live in this
directory, written across many sessions, several of them in parallel. If they
drift in structure, the census numbers stop being comparable and the
doc→ROM-test binding stops being mechanical. The template is what makes a
chapter document *promotable* — a `thin` document deepens into `medium` and then
`full` by filling sections in, never by restructuring.

---

## 1. The rule that governs everything

**The converted rxdata wins over the wiki, always.** Map membership, event
gates, item grants, encounter tables and warps are read out of
`output/uranium-build/`. The wiki is consulted **only** for §5, and every
disagreement is *recorded* there rather than silently resolved
(`ROM_TEST_DEV.md` Branch A1(b)). A wiki-sourced fact appearing anywhere outside
§5 is an error.

## 2. House style

* **Gates and effects only — no narrative content.** The document is a spec a
  test scenario gets written from. `Talk to event 12 → sets VAR_QUEST_LOG 3→4`
  is the register. No plot, no dialogue quoted for flavour, no character arcs.
* **Fail loud, don't guess** (`CLAUDE.md` §4.5). Anything undeterminable goes to
  §7 as an open question *with the reason*. Never write a number that was not
  read out of a file.
* **Cite everything.** `file:line`, or a greppable command, in parentheses.
  Paths in backticks, repo-root-relative, never absolute.
* **Tag provenance.** `[auto]` = regenerable by re-reading a cited artifact.
  `[eye]` = only checkable against a running ROM.
* `§N` inline for internal cross-references, not markdown anchors.

## 3. Sections

Filename: `NN-slug.md` — zero-padded chapter number, lowercased hyphenated
title (`02-route-1.md`, `06-nowtoch-city.md`).

| § | Heading | Contents |
|---|---|---|
| — | Title + **Status:** / **Method note:** front matter, then `---` | Tier, authoring basis, which artifacts were read and on what date, whether the chapter has been built |
| 1 | Purpose / scope | What the chapter is, its place in the act chain, the authoritative map roster, a mechanical summary of the playthrough |
| 2 | Map inventory | One row per map + a **Wiring** paragraph (parent maps, seams vs warps, the entry/exit warps that form the chapter boundary) |
| 3 | Story beat chain | Controlling variable(s), an ASCII arrow diagram of its writes, then the beat table(s) |
| 3.1 | Positive beats | `B1, B2, …` in play order — *full tier only; at medium §3 is one unnumbered beat table* |
| 3.2 | Negative beats | `N1, N2, …`, one per gated positive beat — **full tier only** |
| 4 | Coverage targets | Four subsections: 4.1 trainer battles, 4.2 item balls/given items, 4.3 wild encounters, 4.4 warps. The largest section |
| 5 | Wiki vs rxdata discrepancies | Numbered list. "No disagreements found, checked page X" is a real finding, not an empty section |
| 6 | Expected conversion work and risks | Mechanics→ledger binding table, unmapped script heads, known risks/gaps |
| 7 | Open items for the lead | Every "could not determine", each with what evidence would settle it |
| — | Closing `---` + italic companion-docs line | Files this document depends on |

**There is no §8 for an unbuilt chapter.** `01-moki.md` §8 is by-eye checks
drawn from `BOOT_WALK_CHECKLIST.md`, which only exists once a chapter has been
built and walked; §6 there is likewise a post-build bug ledger. For a chapter
that has not been converted, §6 records *expected* work and §8 is omitted. Both
convert to the `01-moki.md` shape when the chapter reaches its boot gate.

### Table columns (exact)

```
§2   | RMXP id | Uranium identity (`map_infos.json`) | Engine dir | porymap constant | Role in chapter |
§3.1 | Beat | Map | Gate | Player action (test) | Expected effect (observable) |
§3.2 | Beat | Map | Violation tested | Assert refusal fires | Assert no state advanced |
§4.1 | Map | Event | Trigger | In-chapter reachable? | Notes |
§4.2 | Map | Item | Event | Gate | In-chapter? |
§4.3 | Map | Table | Contents | In-chapter reachable? |
§4.4 | Map | Warp | Destination | Chapter-relevant? |
§6.1 | Mechanic | First appears here? | Disposition | Ledger row / notes |
```

**"In-chapter reachable?" is the load-bearing column.** A route's fishing table
is in the data but unreachable without a rod; a postgame-gated item ball is in
the map but not in the chapter. `Yes` (with the beat number) or a bolded **No**
with the reason.

## 4. Tier

Same sections at every tier. Only fill depth changes.

| | **full** | **medium** | **thin** |
|---|---|---|---|
| §3 beats | every beat, in play order | major variable/switch writes only — the state spine | roster + gates, no beat table |
| §3.2 | required | omitted | omitted |
| §4 | exhaustive | totals + notable/risky rows, with the routine remainder counted | totals only |
| §6 | full assessment per unmapped head | one line per head | census line, unassessed |
| §5, §7 | same at every tier | | |
| Length | ~250–320 lines | ~120–200 lines | ~60–90 lines |

Where a section is cheap to enumerate exhaustively at a lower tier — a two-map,
16-event chapter — do it and say so. The tier is a ceiling on effort, not a
floor on omission.

## 5. Data sources

| What | Where |
|---|---|
| Converted map events | `output/uranium-build/maps/Map###.json` |
| Map identities | `output/uranium-build/map_infos.json` |
| Seams | `output/uranium-build/connections.json` |
| Encounter tables | `output/uranium-build/intermediate/wild_encounters.json` |
| Flag/var registry state | `output/uranium-build/flag_state.json` |
| Transpiler unhandled queue | `output/uranium-build/transpile_unhandled.jsonl` |
| Common events | `output/uranium-build/common_events.json` |
| Cached wikitext | `output/uranium-build/wiki/<Page>.wiki` — fetch with `scripts/fetch_uranium_wiki.py` |
| Engine maps / constants | `engine/data/maps/`, `engine/include/constants/` |

Numbers come from the committed census, not from hand-tallying:

```bash
python -m rpg2gba.chapter_atlas census --chapter CHnn
```

A document that disagrees with the census must say so in §7 rather than quietly
printing a different number.

`unhandled: null` means **unmeasured**, not clean — only slice-1 maps are staged
with the transpiler (`00-atlas.md` §7 gap 1). Never report a conversion-
readiness figure for an unstaged map.

## 6. Two traps that have already cost this project time

**Trainer battles are invisible to a naïve search.** There is not one code-301
(Battle Processing) command in the entire Uranium corpus. All 317 trainer
battles are code-111 conditional branches with condition type 12, wrapping
`pbTrainerBattle(...)`. A census reading 301/355 reports zero trainers for the
whole game — the first version of the census tool did exactly that
(`src/rpg2gba/chapter_atlas/census.py:49-54`, pinned by
`tests/test_chapter_atlas.py::test_census_counts_trainer_battles_hidden_in_conditionals`).

**Never claim a mechanic needs new engine C without searching the fork**
(`CLAUDE.md` §4.7). Capability verdicts are owned centrally by
`reference/guides/command_pokeemerald_map.md`; a chapter document carries a thin
*binding* table pointing at it and must not re-derive or contradict a verdict.
A 2026-07-30 audit of that ledger found 2 missing symbols and 6 over-claims —
`healparty` was recommended in two mutually-reinforcing rows while
`special HealPlayerParty` existed the whole time. In the entire game only
**Voltorb Flip** and the **Nuclear type** are genuinely new C.

---

*Companion docs: `reference/chapters/00-atlas.md` (the corpus-wide atlas this
directory hangs off), `reference/chapters/01-moki.md` (the worked example),
`reference/findings/grill_chapter_atlas_2026-07-30.md` (the design record),
`ROM_TEST_DEV.md` (Branch A/B decisions this template implements), `CLAUDE.md`
§4.5/§4.7 (fail-loud and verify-against-the-fork).*
